import os

from langsmith import traceable

from kpi_finder.redis_client import vector_search
from kpi_finder.state import ConditionState

_TOP_K = int(os.environ.get("VECTOR_TOP_K", 5))
_MAX_GROUP_ATTEMPTS = int(os.environ.get("MAX_GROUP_ATTEMPTS", 3))


@traceable(name="group_route_v2")
def group_route_v2(state: ConditionState) -> ConditionState:
    """Retrieve ranked KPI groups from Group_detail_v2 index. No LLM."""
    condition = state["condition"]
    raw = vector_search("Group_detail_v2", condition, top_k=_TOP_K)

    ranked_groups = [
        {
            "group_name": r["name"],
            "score": r["score"],
            "content": r["content"],
            "metadata": r["metadata"],
        }
        for r in raw
    ]

    return {
        "ranked_groups": ranked_groups,
        "attempted_groups": [],
    }


@traceable(name="select_next_group")
def select_next_group(state: ConditionState) -> ConditionState:
    """Pick the next unattempted group from ranked_groups. No LLM."""
    ranked_groups = state.get("ranked_groups", [])
    attempted = state.get("attempted_groups", [])

    for group in ranked_groups:
        gname = group["group_name"]
        if gname not in attempted:
            return {
                "current_group": gname,
                "current_group_context": group["content"],
                "attempted_groups": attempted + [gname],
            }

    # All ranked groups attempted — signal no group available
    return {
        "current_group": None,
        "current_group_context": None,
    }


def should_attempt_group(state: ConditionState) -> str:
    """Conditional edge: proceed to normalize or mark unmatched."""
    attempted = state.get("attempted_groups", [])
    current = state.get("current_group")

    if current is None or len(attempted) > _MAX_GROUP_ATTEMPTS:
        return "mark_unmatched"
    return "normalize_query_for_group"
