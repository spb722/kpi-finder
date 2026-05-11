from typing import Optional, TypedDict


class ConditionState(TypedDict, total=False):
    """State for processing a single condition through the KPI matching graph."""
    request_id: str
    condition: str

    # Priority path 1: Virtual Profile
    virtual_candidates: list[dict]
    virtual_match: Optional[dict]

    # Priority path 2: Customer 360
    profile360_candidates: list[dict]
    profile360_match: Optional[dict]

    # Normal KPI group path
    ranked_groups: list[dict]
    attempted_groups: list[str]
    current_group: Optional[str]
    current_group_context: Optional[str]
    normalized_query: Optional[dict]

    # Feature retrieval
    feature_candidates: list[dict]
    deduped_feature_candidates: list[dict]
    feature_match: Optional[dict]

    # Final result for this condition
    match: Optional[dict]
    unmatched: Optional[dict]
    errors: list[dict]
