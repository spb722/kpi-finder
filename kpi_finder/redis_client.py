import os
import re
import struct

import httpx
import redis
from redis.commands.search.query import Query

VECTOR_DIM = 768


def _get_redis() -> redis.Redis:
    return redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ.get("REDIS_PASSWORD") or None,
        decode_responses=False,
        socket_connect_timeout=float(os.environ.get("REDIS_CONNECT_TIMEOUT", 5)),
        socket_timeout=float(os.environ.get("REDIS_SOCKET_TIMEOUT", 30)),
    )


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _extract_kpi_name(content: str) -> str:
    match = re.search(
        r"for kpi\s+(.+?)\s+the description is",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _embed(text: str) -> bytes:
    """Get embedding from Ollama and return as FLOAT32 bytes."""
    base_url = os.environ["OLLAMA_BASE_URL"].rstrip("/")
    model = os.environ["EMBED_MODEL"]

    resp = httpx.post(
        base_url + "/api/embeddings",
        json={"model": model, "prompt": text},
        timeout=float(os.environ.get("OLLAMA_TIMEOUT", 60)),
    )

    vector = None
    if resp.status_code == 200:
        vector = resp.json().get("embedding")

    if not vector:
        resp = httpx.post(
            base_url + "/api/embed",
            json={"model": model, "input": text},
            timeout=float(os.environ.get("OLLAMA_TIMEOUT", 60)),
        )
        resp.raise_for_status()
        vector = resp.json()["embeddings"][0]

    if len(vector) != VECTOR_DIM:
        raise ValueError(f"Expected embedding dim {VECTOR_DIM}, got {len(vector)}")

    return struct.pack(f"{len(vector)}f", *vector)


def vector_search(index: str, query: str, top_k: int = 5) -> list[dict]:
    """KNN vector search against a RediSearch index.

    Returns list of dicts with keys: feature_name (or group_name), score, content, metadata.
    """
    r = _get_redis()
    vec_bytes = _embed(query)
    k = top_k

    q = (
        Query(f"*=>[KNN {k} @content_vector $vec AS vector_score]")
        .return_fields("content", "metadata", "group_name", "vector_score")
        .sort_by("vector_score")
        .dialect(2)
    )
    results = r.ft(index).search(q, query_params={"vec": vec_bytes})

    docs = []
    for doc in results.docs:
        raw_meta = _decode(getattr(doc, "metadata", "{}"))
        try:
            import json
            meta = json.loads(raw_meta) if isinstance(raw_meta, (str, bytes)) else raw_meta
        except Exception:
            meta = {}

        content = _decode(getattr(doc, "content", b"")) or ""
        group_name = _decode(getattr(doc, "group_name", "")) or ""

        # score is cosine distance (lower = more similar)
        score = float(getattr(doc, "vector_score", 1.0))

        # derive name: prefer metadata keys, fall back to doc id
        name = (
            meta.get("table_name")
            or meta.get("group_name")
            or group_name
            or meta.get("feature_name")
            or meta.get("name")
            or _extract_kpi_name(content)
            or doc.id
        )

        docs.append({
            "name": name,
            "score": score,
            "content": content,
            "metadata": meta,
        })

    return docs
