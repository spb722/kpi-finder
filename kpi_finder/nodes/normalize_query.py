from langsmith import traceable

from kpi_finder.llm_client import call_structured
from kpi_finder.models import NormalizedQuery
from kpi_finder.state import ConditionState


@traceable(name="normalize_query_for_group")
def normalize_query_for_group(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    current_group = state["current_group"]
    group_context = state.get("current_group_context", "")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a telecom data expert. Given a campaign condition and a KPI group context, "
                "extract the structured attributes and produce a normalized search text optimized "
                "for semantic vector search within that group's feature index."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Condition: {condition}\n\n"
                f"Selected KPI Group: {current_group}\n\n"
                f"Group Context:\n{group_context}\n\n"
                "Extract: attribute, operator, value, and produce a normalized_search_text "
                "that describes the feature semantically (positive terms only, no negations)."
            ),
        },
    ]

    result = call_structured(NormalizedQuery, messages)
    return {"normalized_query": result.model_dump()}
