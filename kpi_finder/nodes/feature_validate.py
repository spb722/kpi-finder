from langsmith import traceable

from kpi_finder.llm_client import call_structured
from kpi_finder.models import FeatureMatch
from kpi_finder.state import ConditionState


@traceable(name="feature_validate")
def feature_validate(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    normalized_query = state.get("normalized_query", {})
    current_group = state.get("current_group", "")
    current_group_context = state.get("current_group_context", "")
    candidates = state.get("deduped_feature_candidates", [])[:5]

    if not candidates:
        no_match = FeatureMatch(
            matched=False,
            feature_name="",
            semantic_score=0.0,
            logical_score=0.0,
            confidence=0.0,
            reasoning="No feature candidates available.",
        )
        return {"feature_match": no_match.model_dump()}

    candidate_text = "\n".join(
        f"- {c['feature_name']}: {c['content'][:200]}" for c in candidates
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict telecom KPI validation expert.\n\n"
                "Your job is to decide whether one candidate feature directly satisfies the user's campaign condition.\n"
                "You must be conservative. A semantically related feature is not enough.\n\n"
                "Validation rules:\n"
                "1. Before returning matched=true, verify that every explicit constraint in the user condition is proven by the candidate feature evidence or by the KPI group context.\n"
                "2. Explicit constraints may include metric type, service scope, aggregation meaning, time window, comparison direction, and requested value.\n"
                "3. Do not infer missing support. If the user asks for a time window such as last N days, past N days, rolling N days, daily, monthly, weekly, or a specific period, the candidate must explicitly support that period, or the KPI group context must clearly indicate runtime filtering over event dates is allowed.\n"
                "4. Generic revenue must not match voice revenue, data revenue, SMS revenue, IDD revenue, roaming revenue, or any other service-specific revenue unless the user explicitly asks for that service.\n"
                "5. Generic usage must not match voice usage, data usage, SMS usage, IDD usage, roaming usage, or any other service-specific usage unless the user explicitly asks for that service.\n"
                "6. A subset feature cannot satisfy a total, all, overall, generic, or unspecified-scope request.\n"
                "7. Total, sum, count, average, maximum, and minimum are different aggregation meanings. Do not substitute one for another.\n"
                "8. If the condition asks for a threshold or comparison, the candidate must represent the measured attribute; the threshold itself may be applied downstream only if the attribute is correct.\n"
                "9. If the candidate is only the closest available feature but does not prove all explicit constraints, return matched=false.\n\n"
                "Examples:\n"
                "- User asks for 'rolling revenue over the past 8 days'. Candidate 'Total_Voice_Revenue' is not a match because it is voice-only revenue and does not prove rolling 8-day support.\n"
                "- User asks for 'voice revenue over the past 8 days'. Candidate 'Total_Voice_Revenue' may match only if the group context proves runtime date filtering or the candidate evidence supports that window.\n"
                "- User asks for 'customer is from India'. Candidate 'Profile_Cdr_Nationality' can match because there is no aggregation or time-window constraint.\n"
                "- User asks for 'customer called India'. Candidate 'Profile_Cdr_Nationality' is not a match because nationality is not calling behavior.\n\n"
                "Return matched=true only when the selected feature fully satisfies the condition. Otherwise return matched=false."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Original condition:\n{condition}\n\n"
                "Normalized query:\n"
                f"- attribute: {normalized_query.get('attribute', '')}\n"
                f"- operator: {normalized_query.get('operator', '')}\n"
                f"- value: {normalized_query.get('value', '')}\n"
                f"- normalized_search_text: {normalized_query.get('normalized_search_text', '')}\n\n"
                f"KPI group:\n{current_group}\n\n"
                f"KPI group context:\n{current_group_context}\n\n"
                f"Feature candidates:\n{candidate_text}\n\n"
                "Choose the single best feature only if it fully satisfies every explicit constraint in the original condition. "
                "If none fully satisfy the condition, return matched=false."
            ),
        },
    ]

    result = call_structured(FeatureMatch, messages)
    return {"feature_match": result.model_dump()}


def should_finalize_feature(state: ConditionState) -> str:
    """Conditional edge after feature_validate."""
    feature_match = state.get("feature_match", {})
    if feature_match.get("matched"):
        return "finalize_condition"
    return "select_next_group"
