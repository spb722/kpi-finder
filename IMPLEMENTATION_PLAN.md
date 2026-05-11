# Implementation Plan: LangGraph Telecom KPI Mapper

## Goal

Build a LangGraph-based service that maps natural-language telecom campaign conditions to the correct KPI/feature and group/table.

The design should stay simple and directly follow the proven notebook flow.

---

## Runtime Components

```text
FastAPI or service entrypoint
  ↓
LangGraph workflow
  ↓
Redis Stack / RediSearch vector indexes
  ↓
Ollama embedding model
  ↓
Groq OpenAI-compatible chat completions with structured output
  ↓
LangSmith tracing
```

---

## Required Environment Variables

```bash
REDIS_HOST=10.0.11.179
REDIS_PORT=6378
REDIS_PASSWORD=...
OLLAMA_BASE_URL=http://10.0.6.103:11434
EMBED_MODEL=sachin_telecom-kpi-embedding:latest
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-20b
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=telecom-kpi-mapper
```

Never hardcode API keys.

---

## Input Contract

```json
{
  "conditions": [
    "customer is from India"
  ],
  "check": true,
  "debug": false
}
```

Notes:

- `conditions` must be a list of strings.
- `check` can be kept for compatibility.
- `debug` can optionally return intermediate candidates.

---

## Output Contract

```json
{
  "matches": [
    {
      "condition": "customer is from India",
      "source": "normal_kpi_group",
      "group_name": "Profile_Cdr_group",
      "feature_name": "Profile_Cdr_Nationality",
      "operator": "equals",
      "value": "India",
      "confidence": 0.96,
      "reasoning": "The condition asks for the subscriber's registered nationality."
    }
  ],
  "unmatched": [],
  "mismatch_percentage": 0,
  "trace_id": "optional-langsmith-run-id"
}
```

---

## LangGraph State

```python
from typing import TypedDict, Optional, Any

class ConditionState(TypedDict, total=False):
    request_id: str
    condition: str

    # Priority path
    virtual_candidates: list[dict]
    virtual_match: Optional[dict]
    profile360_candidates: list[dict]
    profile360_match: Optional[dict]

    # Normal KPI group path
    ranked_groups: list[dict]
    attempted_groups: list[str]
    current_group: Optional[str]
    current_group_context: Optional[str]
    normalized_query: Optional[dict]

    feature_candidates: list[dict]
    deduped_feature_candidates: list[dict]
    feature_match: Optional[dict]

    # Result
    match: Optional[dict]
    unmatched: Optional[dict]
    errors: list[dict]
```

For multi-condition processing, run `ConditionState` subgraph per condition and aggregate.

---

## Graph Nodes

### Node 1: `virtual_profile_retrieval`

Search:

```text
Virtual_profile_description
```

Input:

```json
{"condition": "..."}
```

Output:

```json
{"virtual_candidates": [...]}
```

LangSmith metadata:

```json
{"node": "virtual_profile_retrieval", "index": "Virtual_profile_description", "top_k": 5}
```

---

### Node 2: `virtual_profile_match`

Structured LLM output:

```python
class VirtualProfileMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched: bool
    virtual_profile: str
    reasoning: str
```

Conditional edge:

```text
matched → finalize_condition
not matched → customer_360_retrieval
```

---

### Node 3: `customer_360_retrieval`

Search:

```text
360_profile
```

Output:

```json
{"profile360_candidates": [...]}
```

---

### Node 4: `customer_360_match`

Structured LLM output:

```python
class KPIExistenceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched: bool
    kpi: str
    reasoning: str
```

Conditional edge:

```text
matched → finalize_condition
not matched → group_route_v2
```

---

### Node 5: `group_route_v2`

Search:

```text
Group_detail_v2
```

Output:

```json
{
  "ranked_groups": [
    {"group_name": "Profile_Cdr_group", "score": 0.516, "content": "..."}
  ],
  "attempted_groups": []
}
```

Do not use LLM here.

---

### Node 6: `select_next_group`

Select the first unattempted group.

Output:

```json
{
  "current_group": "Profile_Cdr_group",
  "current_group_context": "...",
  "attempted_groups": ["Profile_Cdr_group"]
}
```

If no unattempted group or max attempts reached, go to `mark_unmatched`.

---

### Node 7: `normalize_query_for_group`

Structured LLM call using OpenAI-compatible Groq API.

Pydantic model:

```python
class NormalizedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_group: str
    attribute: str
    operator: str
    value: str
    normalized_search_text: str
    reasoning: str
```

Input prompt includes:

- original condition,
- selected group,
- selected group context from `Group_detail_v2`.

Output example:

```json
{
  "selected_group": "Profile_Cdr_group",
  "attribute": "nationality",
  "operator": "equals",
  "value": "India",
  "normalized_search_text": "subscriber registered nationality country India",
  "reasoning": "The query asks whether the customer is from a country."
}
```

---

### Node 8: `feature_search_in_group`

Search index:

```text
current_group
```

Search text:

```text
normalized_query.normalized_search_text
```

Output:

```json
{"feature_candidates": [...]}
```

---

### Node 9: `dedupe_feature_candidates`

No LLM.

Collapse by `feature_name`, keep best score.

---

### Node 10: `feature_validate`

Structured LLM output:

```python
class FeatureMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched: bool
    feature_name: str
    semantic_score: float
    logical_score: float
    confidence: float
    reasoning: str
```

Use only top 3-5 deduped candidates.

Conditional edge:

```text
matched → finalize_condition
not matched → select_next_group or mark_unmatched
```

---

### Node 11: `finalize_condition`

Create final match object.

---

### Node 12: `mark_unmatched`

Create unmatched object:

```json
{
  "condition": "...",
  "reason": "No KPI found after virtual profile, 360, and top normal groups."
}
```

---

## OpenAI-Compatible Structured Output Helper

```python
from openai import OpenAI
from pydantic import BaseModel, ConfigDict
import os

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

def call_structured(model_cls: type[BaseModel], messages: list[dict], model: str):
    schema = model_cls.model_json_schema()
    schema["additionalProperties"] = False

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": model_cls.__name__,
                "schema": schema,
                "strict": True,
            },
        },
    )

    return model_cls.model_validate_json(response.choices[0].message.content)
```

---

## LangSmith Tracing

Set environment variables:

```bash
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=telecom-kpi-mapper
LANGSMITH_API_KEY=...
```

Each node should add structured metadata, for example:

```python
from langsmith import traceable

@traceable(name="group_route_v2")
def group_route_v2(state):
    ...
```

Log:

- input condition,
- index searched,
- top-k results,
- selected group,
- normalized query,
- feature candidates,
- final result,
- fallback attempts.

---

## Minimal First Build

Start with only this path:

```text
group_route_v2
→ select_next_group
→ normalize_query_for_group
→ feature_search_in_group
→ dedupe_feature_candidates
→ feature_validate
→ finalize_condition
```

Then add:

```text
virtual_profile
360_profile
fallback loop
multi-condition aggregation
```

---

## Acceptance Tests

### Test 1

Input:

```text
customer is from India
```

Expected:

```json
{
  "group_name": "Profile_Cdr_group",
  "feature_name": "Profile_Cdr_Nationality",
  "operator": "equals",
  "value": "India"
}
```

### Test 2

Input:

```text
customer called India in last 30 days
```

Expected:

```text
Should not map to Profile_Cdr_Nationality.
Should map to IDD/calling-related usage/revenue group or 360 if available.
```

### Test 3

Input:

```text
customers who recharged more than 5 OMR
```

Expected group:

```text
Recharge_Seg_Fct
```

### Test 4

Input:

```text
customers who received bonus in last 7 days
```

Expected group:

```text
LIFECYCLE_CDR
```

### Test 5

Input:

```text
customers with total data usage above 1GB
```

Expected group:

```text
Common_Seg_Fct
```

---

## Notes

- Do not overcomplicate this with cross-encoder reranking yet.
- Keep `Group_detail_v2` as the routing index.
- Keep feature indexes as-is initially.
- Use normalization before feature search.
- Add feature-index enrichment only if feature retrieval remains unreliable.
