import os

from langsmith import traceable

from kpi_finder.redis_client import vector_search
from kpi_finder.state import ConditionState

_TOP_K = int(os.environ.get("VECTOR_TOP_K", 5))


@traceable(name="feature_search_in_group")
def feature_search_in_group(state: ConditionState) -> ConditionState:
    """Search the current group's feature index using the normalized search text."""
    current_group = state["current_group"]
    normalized_query = state.get("normalized_query", {})
    search_text = normalized_query.get("normalized_search_text", state["condition"])

    raw = vector_search(current_group, search_text, top_k=_TOP_K)

    feature_candidates = [
        {
            "feature_name": r["name"],
            "score": r["score"],
            "content": r["content"],
            "metadata": r["metadata"],
        }
        for r in raw
    ]

    return {"feature_candidates": feature_candidates}


@traceable(name="dedupe_feature_candidates")
def dedupe_feature_candidates(state: ConditionState) -> ConditionState:
    """Collapse duplicate feature_name entries, keeping the best (lowest cosine distance) score."""
    candidates = state.get("feature_candidates", [])

    seen: dict[str, dict] = {}
    for c in candidates:
        name = c["feature_name"]
        if name not in seen or c["score"] < seen[name]["score"]:
            seen[name] = c

    deduped = sorted(seen.values(), key=lambda x: x["score"])
    return {"deduped_feature_candidates": deduped}
