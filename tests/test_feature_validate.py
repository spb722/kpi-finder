from kpi_finder.models import FeatureMatch
from kpi_finder.nodes import feature_validate as feature_validate_module


def test_feature_validate_prompt_requires_explicit_constraint_proof(monkeypatch):
    captured = {}

    def fake_call_structured(model_cls, messages):
        captured["model_cls"] = model_cls
        captured["messages"] = messages
        return FeatureMatch(
            matched=False,
            feature_name="",
            semantic_score=0,
            logical_score=0,
            confidence=0,
            reasoning="Missing explicit support for requested constraints.",
        )

    monkeypatch.setattr(feature_validate_module, "call_structured", fake_call_structured)

    state = {
        "condition": "Customers rolling revenue over the past 8 days",
        "current_group": "Instant_cdr_group",
        "current_group_context": "Instant CDR feature group for event-level customer behavior.",
        "normalized_query": {
            "attribute": "revenue",
            "operator": "sum_over_last_8_days",
            "value": "8 days",
            "normalized_search_text": "rolling revenue past 8 days",
        },
        "deduped_feature_candidates": [
            {
                "feature_name": "Total_Voice_Revenue",
                "content": "for kpi Total_Voice_Revenue the description is total voice revenue",
            }
        ],
    }

    result = feature_validate_module.feature_validate(state)

    assert result["feature_match"]["matched"] is False
    assert captured["model_cls"] is FeatureMatch

    system_prompt = captured["messages"][0]["content"]
    user_prompt = captured["messages"][1]["content"]

    assert "every explicit constraint" in system_prompt
    assert "Do not infer missing support" in system_prompt
    assert "Generic revenue must not match voice revenue" in system_prompt
    assert "Total_Voice_Revenue' is not a match" in system_prompt
    assert "KPI group context:" in user_prompt
    assert "Instant CDR feature group" in user_prompt
    assert "Customers rolling revenue over the past 8 days" in user_prompt
