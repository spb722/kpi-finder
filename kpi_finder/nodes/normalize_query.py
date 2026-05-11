import json

from langsmith import traceable
from openai import OpenAIError

from kpi_finder.llm_client import call_structured
from kpi_finder.models import NormalizedQuery
from kpi_finder.state import ConditionState


def _fallback_normalized_query(condition: str, current_group: str, reason: str) -> dict:
    """Best-effort fallback when structured LLM normalization fails."""
    return {
        "selected_group": current_group,
        "attribute": "",
        "operator": "",
        "value": "",
        "normalized_search_text": condition,
        "reasoning": reason,
    }


@traceable(name="normalize_query_for_group")
def normalize_query_for_group(state: ConditionState) -> ConditionState:
    condition = state["condition"]
    current_group = state["current_group"]
    group_context = state.get("current_group_context", "")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a telecom KPI query normalizer.\n\n"
                "Return exactly one JSON object matching the required schema.\n"
                "All fields are required strings: selected_group, attribute, operator, value, normalized_search_text, reasoning.\n"
                "Never return null. Use an empty string \"\" when a field is unknown or not present.\n"
                "Do not include markdown, code fences, comments, or text outside the JSON object.\n\n"
                "Your job is to rewrite the user's campaign condition into a short positive search text "
                "for semantic vector search inside the already-selected KPI group.\n\n"
                "Rules:\n"
                "- Do not change selected_group.\n"
                "- Use the group context to understand likely attributes, but do not invent unsupported facts.\n"
                "- Extract attribute, operator, and value when they are clear.\n"
                "- If the condition is vague, still produce a best-effort normalized_search_text.\n"
                "- Keep normalized_search_text concise and positive; avoid negations and exclusion language."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Condition:\n{condition}\n\n"
                f"Selected KPI Group:\n{current_group}\n\n"
                f"Group Context:\n{group_context}\n\n"
                "Return the JSON object now."
            ),
        },
    ]

    try:
        result = call_structured(NormalizedQuery, messages)
        return {"normalized_query": result.model_dump()}
    except OpenAIError:
        retry_messages = [
            {
                "role": "system",
                "content": (
                    "Return valid JSON only. No markdown. No explanation outside JSON.\n"
                    "All six string fields are required. Use \"\" if unknown.\n"
                    "Fields: selected_group, attribute, operator, value, normalized_search_text, reasoning."
                ),
            },
            {
                "role": "user",
                "content": (
                    "{\n"
                    f'  "selected_group": {json.dumps(current_group)},\n'
                    '  "attribute": "",\n'
                    '  "operator": "",\n'
                    '  "value": "",\n'
                    f'  "normalized_search_text": {json.dumps(condition)},\n'
                    '  "reasoning": ""\n'
                    "}\n\n"
                    "Rewrite this JSON with better attribute/operator/value/search text if clear from the condition. "
                    "Keep selected_group unchanged."
                ),
            },
        ]

        try:
            result = call_structured(NormalizedQuery, retry_messages)
            return {"normalized_query": result.model_dump()}
        except OpenAIError as exc:
            return {
                "normalized_query": _fallback_normalized_query(
                    condition,
                    current_group,
                    f"Structured normalization failed twice; used original condition as search text. Last error: {type(exc).__name__}",
                )
            }
