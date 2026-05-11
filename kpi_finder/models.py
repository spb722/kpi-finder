from pydantic import BaseModel, ConfigDict, Field


class VirtualProfileMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched: bool
    virtual_profile: str
    reasoning: str


class KPIExistenceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched: bool
    kpi: str
    reasoning: str


class NormalizedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_group: str
    attribute: str
    operator: str
    value: str
    normalized_search_text: str
    reasoning: str


class FeatureMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched: bool
    feature_name: str
    semantic_score: float = Field(ge=0, le=100)
    logical_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reasoning: str
