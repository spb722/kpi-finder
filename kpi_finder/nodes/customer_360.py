import os

from langsmith import traceable

from kpi_finder.llm_client import call_structured
from kpi_finder.models import KPIExistenceMatch
from kpi_finder.redis_client import vector_search
from kpi_finder.state import ConditionState

_TOP_K = int(os.environ.get("VECTOR_TOP_K", 5))


@traceable(name="customer_360_retrieval")
def customer_360_retrieval(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    candidates = vector_search("360_profile", condition, top_k=_TOP_K)
    return {"profile360_candidates": candidates}


@traceable(name="customer_360_match")
def customer_360_match(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    candidates = state.get("profile360_candidates", [])

    if not candidates:
        return {"profile360_match": {"matched": False, "kpi": "", "reasoning": "No candidates found."}}

    candidate_text = "\n".join(
        f"- {c['name']}: {c['content'][:200]}" for c in candidates
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a telecom KPI expert. Given a campaign condition and Customer 360 KPI candidates, "
                "determine if any KPI DIRECTLY and EXACTLY satisfies the condition. "
                "Be strict: 'customer called India' is NOT the same as 'customer is from India'. "
                "Only match if the KPI's meaning fully covers the condition."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Condition: {condition}\n\n"
                f"Customer 360 KPI Candidates:\n{candidate_text}\n\n"
                "Does any candidate directly satisfy this condition? Respond with matched=true only if certain."
            ),
        },
    ]

    result = call_structured(KPIExistenceMatch, messages)
    return {"profile360_match": result.model_dump()}
