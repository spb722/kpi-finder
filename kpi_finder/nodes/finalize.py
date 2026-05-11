from langsmith import traceable

from kpi_finder.state import ConditionState


@traceable(name="finalize_condition")
def finalize_condition(state: ConditionState) -> ConditionState:
    """Build the final match object from whichever path succeeded."""
    condition = state["condition"]

    # Virtual profile path
    virtual_match = state.get("virtual_match", {})
    if virtual_match and virtual_match.get("matched"):
        return {
            "match": {
                "condition": condition,
                "source": "virtual_profile",
                "group_name": "RE_VIRTUAL_PROFILE_DESCRIPTION",
                "feature_name": virtual_match["virtual_profile"],
                "operator": None,
                "value": None,
                "confidence": 1.0,
                "reasoning": virtual_match.get("reasoning", ""),
            }
        }

    # Customer 360 path
    profile360_match = state.get("profile360_match", {})
    if profile360_match and profile360_match.get("matched"):
        return {
            "match": {
                "condition": condition,
                "source": "customer_360",
                "group_name": "360_PROFILE",
                "feature_name": profile360_match["kpi"],
                "operator": None,
                "value": None,
                "confidence": 0.95,
                "reasoning": profile360_match.get("reasoning", ""),
            }
        }

    # Normal KPI group path
    feature_match = state.get("feature_match", {})
    normalized_query = state.get("normalized_query", {})
    current_group = state.get("current_group", "")

    return {
        "match": {
            "condition": condition,
            "source": "normal_kpi_group",
            "group_name": current_group,
            "feature_name": feature_match.get("feature_name", ""),
            "operator": normalized_query.get("operator"),
            "value": normalized_query.get("value"),
            "confidence": feature_match.get("confidence", 0.0),
            "reasoning": feature_match.get("reasoning", ""),
        }
    }


@traceable(name="mark_unmatched")
def mark_unmatched(state: ConditionState) -> ConditionState:
    return {
        "unmatched": {
            "condition": state["condition"],
            "reason": "No KPI found after checking virtual profile, Customer 360, and top normal KPI groups.",
        }
    }
