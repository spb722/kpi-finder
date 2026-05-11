import os

from langsmith import traceable

from kpi_finder.llm_client import call_structured
from kpi_finder.models import VirtualProfileMatch
from kpi_finder.redis_client import vector_search
from kpi_finder.state import ConditionState

_TOP_K = int(os.environ.get("VECTOR_TOP_K", 5))


@traceable(name="virtual_profile_retrieval")
def virtual_profile_retrieval(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    candidates = vector_search("Virtual_profile_description", condition, top_k=_TOP_K)
    return {"virtual_candidates": candidates}


@traceable(name="virtual_profile_match")
def virtual_profile_match(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    candidates = state.get("virtual_candidates", [])

    if not candidates:
        return {"virtual_match": {"matched": False, "virtual_profile": "", "reasoning": "No candidates found."}}

    candidate_text = "\n".join(
        f"- {c['name']}: {c['content'][:200]}" for c in candidates
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a telecom KPI expert. Given a campaign condition and a list of virtual profile candidates, "
                "determine if any virtual profile EXACTLY represents the entire condition. "
                "Only match if the virtual profile is a direct, complete representation—not a partial match."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Condition: {condition}\n\n"
                f"Virtual Profile Candidates:\n{candidate_text}\n\n"
                "Does any candidate exactly represent this condition? Respond with matched=true only if certain."
            ),
        },
    ]

    result = call_structured(VirtualProfileMatch, messages)
    return {"virtual_match": result.model_dump()}
