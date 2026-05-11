from openai import OpenAIError
from pydantic import BaseModel

from kpi_finder.models import NormalizedQuery
from kpi_finder.nodes import normalize_query as normalize_query_module


def _structured_output_error() -> OpenAIError:
    return OpenAIError("Failed to validate JSON")


def test_normalize_query_uses_primary_structured_result(monkeypatch):
    calls = []

    def fake_call_structured(model_cls: type[BaseModel], messages: list[dict]):
        calls.append(messages)
        return NormalizedQuery(
            selected_group="Profile_Cdr_group",
            attribute="nationality",
            operator="equals",
            value="India",
            normalized_search_text="subscriber registered nationality country India",
            reasoning="Nationality condition.",
        )

    monkeypatch.setattr(normalize_query_module, "call_structured", fake_call_structured)

    result = normalize_query_module.normalize_query_for_group({
        "condition": "customer is from India",
        "current_group": "Profile_Cdr_group",
        "current_group_context": "Profile fields.",
    })

    assert len(calls) == 1
    assert result["normalized_query"]["attribute"] == "nationality"
    assert "Return exactly one JSON object" in calls[0][0]["content"]


def test_normalize_query_retries_with_simple_prompt_after_structured_error(monkeypatch):
    calls = []

    def fake_call_structured(model_cls: type[BaseModel], messages: list[dict]):
        calls.append(messages)
        if len(calls) == 1:
            raise _structured_output_error()
        return NormalizedQuery(
            selected_group="Instant_cdr_group",
            attribute="revenue",
            operator="exists",
            value="",
            normalized_search_text="customer revenue activity",
            reasoning="Retry normalization.",
        )

    monkeypatch.setattr(normalize_query_module, "call_structured", fake_call_structured)

    result = normalize_query_module.normalize_query_for_group({
        "condition": 'customers with "revenue" movement',
        "current_group": "Instant_cdr_group",
        "current_group_context": "Instant CDR fields.",
    })

    assert len(calls) == 2
    assert result["normalized_query"]["normalized_search_text"] == "customer revenue activity"
    assert "Return valid JSON only" in calls[1][0]["content"]
    assert '\\"revenue\\"' in calls[1][1]["content"]


def test_normalize_query_falls_back_to_original_condition_after_two_errors(monkeypatch):
    def fake_call_structured(model_cls: type[BaseModel], messages: list[dict]):
        raise _structured_output_error()

    monkeypatch.setattr(normalize_query_module, "call_structured", fake_call_structured)

    result = normalize_query_module.normalize_query_for_group({
        "condition": "customers having some unclear behavior",
        "current_group": "Common_Seg_Fct",
        "current_group_context": "Common segment fields.",
    })

    normalized = result["normalized_query"]
    assert normalized["selected_group"] == "Common_Seg_Fct"
    assert normalized["attribute"] == ""
    assert normalized["operator"] == ""
    assert normalized["value"] == ""
    assert normalized["normalized_search_text"] == "customers having some unclear behavior"
    assert "failed twice" in normalized["reasoning"]
