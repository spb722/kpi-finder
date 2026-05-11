"""
Per-condition LangGraph for telecom KPI mapping.

Flow:
  virtual_profile_retrieval
  → virtual_profile_match
  → [matched] finalize_condition
  → [not matched] customer_360_retrieval
  → customer_360_match
  → [matched] finalize_condition
  → [not matched] group_route_v2
  → select_next_group
  → [no group / max attempts] mark_unmatched
  → [group available] normalize_query_for_group
  → feature_search_in_group
  → dedupe_feature_candidates
  → feature_validate
  → [matched] finalize_condition
  → [not matched] select_next_group  (loops)
"""

from langgraph.graph import END, START, StateGraph

from kpi_finder.nodes.customer_360 import customer_360_match, customer_360_retrieval
from kpi_finder.nodes.feature_search import dedupe_feature_candidates, feature_search_in_group
from kpi_finder.nodes.feature_validate import feature_validate, should_finalize_feature
from kpi_finder.nodes.finalize import finalize_condition, mark_unmatched
from kpi_finder.nodes.group_route import group_route_v2, select_next_group, should_attempt_group
from kpi_finder.nodes.normalize_query import normalize_query_for_group
from kpi_finder.nodes.virtual_profile import virtual_profile_match, virtual_profile_retrieval
from kpi_finder.state import ConditionState


def _after_virtual_match(state: ConditionState) -> str:
    if state.get("virtual_match", {}).get("matched"):
        return "finalize_condition"
    return "customer_360_retrieval"


def _after_360_match(state: ConditionState) -> str:
    if state.get("profile360_match", {}).get("matched"):
        return "finalize_condition"
    return "group_route_v2"


def build_condition_graph() -> StateGraph:
    builder = StateGraph(ConditionState)

    # Add all nodes
    builder.add_node("virtual_profile_retrieval", virtual_profile_retrieval)
    builder.add_node("virtual_profile_match", virtual_profile_match)
    builder.add_node("customer_360_retrieval", customer_360_retrieval)
    builder.add_node("customer_360_match", customer_360_match)
    builder.add_node("group_route_v2", group_route_v2)
    builder.add_node("select_next_group", select_next_group)
    builder.add_node("normalize_query_for_group", normalize_query_for_group)
    builder.add_node("feature_search_in_group", feature_search_in_group)
    builder.add_node("dedupe_feature_candidates", dedupe_feature_candidates)
    builder.add_node("feature_validate", feature_validate)
    builder.add_node("finalize_condition", finalize_condition)
    builder.add_node("mark_unmatched", mark_unmatched)

    # Entry
    builder.add_edge(START, "virtual_profile_retrieval")
    builder.add_edge("virtual_profile_retrieval", "virtual_profile_match")

    # After virtual profile match
    builder.add_conditional_edges(
        "virtual_profile_match",
        _after_virtual_match,
        {"finalize_condition": "finalize_condition", "customer_360_retrieval": "customer_360_retrieval"},
    )

    builder.add_edge("customer_360_retrieval", "customer_360_match")

    # After 360 match
    builder.add_conditional_edges(
        "customer_360_match",
        _after_360_match,
        {"finalize_condition": "finalize_condition", "group_route_v2": "group_route_v2"},
    )

    builder.add_edge("group_route_v2", "select_next_group")

    # After selecting a group: proceed or mark unmatched
    builder.add_conditional_edges(
        "select_next_group",
        should_attempt_group,
        {"normalize_query_for_group": "normalize_query_for_group", "mark_unmatched": "mark_unmatched"},
    )

    builder.add_edge("normalize_query_for_group", "feature_search_in_group")
    builder.add_edge("feature_search_in_group", "dedupe_feature_candidates")
    builder.add_edge("dedupe_feature_candidates", "feature_validate")

    # After feature validation: finalize or retry next group
    builder.add_conditional_edges(
        "feature_validate",
        should_finalize_feature,
        {"finalize_condition": "finalize_condition", "select_next_group": "select_next_group"},
    )

    builder.add_edge("finalize_condition", END)
    builder.add_edge("mark_unmatched", END)

    return builder.compile()


# Module-level compiled graph (reused across requests)
condition_graph = build_condition_graph()
