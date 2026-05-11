import json

import pytest

from kpi_finder import redis_client


class _Doc:
    def __init__(self, doc_id: str, **fields):
        self.id = doc_id
        for key, value in fields.items():
            setattr(self, key, value)


class _SearchResult:
    def __init__(self, docs):
        self.docs = docs


class _FakeFt:
    def __init__(self, docs):
        self.docs = docs

    def search(self, query, query_params):
        return _SearchResult(self.docs)


class _FakeRedis:
    def __init__(self, docs):
        self.docs = docs

    def ft(self, index):
        return _FakeFt(self.docs)


def test_vector_search_prefers_table_name_then_group_field(monkeypatch):
    docs = [
        _Doc(
            "doc:Group_detail_v2:ignored",
            content=b"group context",
            metadata=json.dumps({"table_name": "Profile_Cdr_group"}).encode(),
            group_name=b"Wrong_Group",
            vector_score="0.42",
        )
    ]

    monkeypatch.setattr(redis_client, "_get_redis", lambda: _FakeRedis(docs))
    monkeypatch.setattr(redis_client, "_embed", lambda text: b"vector")

    result = redis_client.vector_search("Group_detail_v2", "customer is from India")

    assert result[0]["name"] == "Profile_Cdr_group"
    assert result[0]["score"] == 0.42
    assert result[0]["content"] == "group context"


def test_vector_search_extracts_feature_name_from_content(monkeypatch):
    docs = [
        _Doc(
            "doc:Profile_Cdr_group:1",
            content=b"for kpi Profile_Cdr_Nationality the description is subscriber registered nationality",
            metadata=b"{}",
            vector_score="0.1",
        )
    ]

    monkeypatch.setattr(redis_client, "_get_redis", lambda: _FakeRedis(docs))
    monkeypatch.setattr(redis_client, "_embed", lambda text: b"vector")

    result = redis_client.vector_search("Profile_Cdr_group", "nationality")

    assert result[0]["name"] == "Profile_Cdr_Nationality"


def test_embed_falls_back_to_newer_ollama_endpoint(monkeypatch):
    calls = []

    class _Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.payload = payload

        def json(self):
            return self.payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("unexpected HTTP error")

    def fake_post(url, json, timeout):
        calls.append(url)
        if url.endswith("/api/embeddings"):
            return _Response(200, {"embedding": None})
        return _Response(200, {"embeddings": [[0.0] * redis_client.VECTOR_DIM]})

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local")
    monkeypatch.setenv("EMBED_MODEL", "embedding-model")
    monkeypatch.setattr(redis_client.httpx, "post", fake_post)

    assert len(redis_client._embed("hello")) == redis_client.VECTOR_DIM * 4
    assert calls == [
        "http://ollama.local/api/embeddings",
        "http://ollama.local/api/embed",
    ]


def test_embed_rejects_wrong_dimension(monkeypatch):
    class _Response:
        status_code = 200

        def json(self):
            return {"embedding": [0.0, 1.0]}

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local")
    monkeypatch.setenv("EMBED_MODEL", "embedding-model")
    monkeypatch.setattr(redis_client.httpx, "post", lambda *args, **kwargs: _Response())

    with pytest.raises(ValueError, match="Expected embedding dim"):
        redis_client._embed("hello")
