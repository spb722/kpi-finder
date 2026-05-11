# Developer Handoff: Telecom KPI Mapping RAG + LangGraph Migration

## 1. Purpose

This project maps a user-provided natural-language campaign condition to the correct telecom KPI/feature and group/table.

Example input:

```json
{
  "conditions": ["customer is from India"],
  "check": true
}
```

Expected output:

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
      "confidence": 0.95,
      "reasoning": "The condition asks for the subscriber's registered nationality."
    }
  ],
  "unmatched": [],
  "mismatch_percentage": 0
}
```

The current n8n workflow works conceptually, but it is too large, duplicated, and difficult to test. The target design is a small, testable LangGraph implementation with LangSmith tracing.

---

## 2. Business Context

There are three broad lookup layers, in fixed priority order:

1. **Virtual Profile**
   - User-created or business-created composite logic.
   - A virtual profile may combine multiple conditions into one reusable condition.
   - This is not the same as the normal `Profile_Cdr_group`.

2. **Customer 360**
   - Ready-made customer-level derived features from `360_profile`.
   - Should be checked before normal KPI groups.

3. **Normal KPI Groups**
   - Examples:
     - `Profile_Cdr_group`
     - `Common_Seg_Fct`
     - `Recharge_Seg_Fct`
     - `LIFECYCLE_CDR`
     - `AUDIENCE_SEGMENT_CDR`
     - `Instant_cdr_group`
     - `Subscriptions`
     - `Manual_Segment_Group`

Important distinction:

```text
Virtual Profile != Profile_Cdr_group
```

`Profile_Cdr_group` is only one group inside the normal KPI group route.

---

## 3. Key Findings from Notebook Prototype

### 3.1 Existing Redis Indexes

The Redis Stack server has these RediSearch vector indexes:

```text
Virtual_profile_description
Recharge_Seg_Fct
AUDIENCE_SEGMENT_CDR
LIFECYCLE_CDR
Instant_cdr_group
Profile_Cdr_group
360_profile
Subscriptions
Common_Seg_Fct
```

The main schema across indexes:

```text
content_vector: VECTOR HNSW FLOAT32 DIM 768 COSINE
content: TEXT
metadata: TEXT
```

### 3.2 Original Group Routing Problem

For the query:

```text
customer is from India
```

Old `Group_detail` returned:

```text
Rank 1: Common_Seg_Fct
Rank 6: Profile_Cdr_group
```

This was wrong. The query is about nationality/country, so it belongs to `Profile_Cdr_group`.

### 3.3 Group_detail_v2 Fix

We created `Group_detail_v2`, an enriched group-routing index.

Important design rule:

```text
content = positive-only semantic routing text
metadata = structured debug/exclusion data
content_vector = embedding(content only)
```

Do not embed negative/exclusion terms like “do not use for nationality,” because vector search can still be attracted to the word “nationality.” Negative terms are kept only in metadata.

After creating `Group_detail_v2`, the same query returned:

```text
Rank 1: Profile_Cdr_group
```

This fixed group routing.

### 3.4 Feature-Level Retrieval Problem

After correctly routing to `Profile_Cdr_group`, raw feature search for:

```text
customer is from India
```

returned unrelated string fields first:

```text
Profile_Cdr_Handset_Manufacturer
Dealer
Business
Profile_Cdr_Nationality
```

The correct feature was `Profile_Cdr_Nationality`, but it was not rank 1.

### 3.5 Query Normalization Fix

We then injected the selected group context into an OpenAI-compatible Groq LLM call and asked it to produce structured output.

For:

```text
customer is from India
```

selected group:

```text
Profile_Cdr_group
```

expected normalized output:

```json
{
  "selected_group": "Profile_Cdr_group",
  "attribute": "nationality",
  "operator": "equals",
  "value": "India",
  "normalized_search_text": "subscriber registered nationality country India",
  "reasoning": "The query asks whether the customer is from a country, which maps to nationality in the profile group."
}
```

Then the normalized search text is used to search inside `Profile_Cdr_group`.

---

## 4. Final Target Flow

```text
START
  ↓
parse_request
  ↓
for each condition
  ↓
virtual_profile_retrieval
  ↓
virtual_profile_match
  ↓ if matched
finalize_condition
  ↓ if not matched
customer_360_retrieval
  ↓
customer_360_match
  ↓ if matched
finalize_condition
  ↓ if not matched
group_route_v2
  ↓
select_next_group
  ↓
normalize_query_for_group
  ↓
feature_search_in_group
  ↓
dedupe_feature_candidates
  ↓
feature_validate
  ↓ if matched
finalize_condition
  ↓ if not matched and attempts remain
select_next_group
  ↓ if no attempts remain
mark_unmatched
  ↓
aggregate_results
  ↓
END
```

---

## 5. Why LangGraph

LangGraph should be used because this is not a simple single-chain workflow. It requires:

- fixed priority order,
- conditional routing,
- fallback loops,
- state tracking,
- group retry attempts,
- structured outputs,
- observability with LangSmith.

The LLM should not control the whole workflow. It should perform small, bounded tasks:

1. judge whether a virtual profile matches,
2. judge whether a 360 KPI matches,
3. normalize a query based on selected group context,
4. validate top feature candidates.

Retrieval, fallback, state, and aggregation should be deterministic.

---

## 6. What Each Step Should Do

### 6.1 `parse_request`

Input:

```json
{
  "conditions": ["customer is from India"],
  "check": true
}
```

Output state:

```json
{
  "conditions": ["customer is from India"],
  "matches": [],
  "unmatched": []
}
```

Responsibilities:

- Validate payload.
- Ensure `conditions` is a list.
- Preserve `check` if needed.

LangSmith metadata:

```json
{
  "node": "parse_request",
  "condition_count": 1
}
```

---

### 6.2 `virtual_profile_retrieval`

Search index:

```text
Virtual_profile_description
```

Input:

```json
{
  "condition": "customer is from India"
}
```

Output:

```json
{
  "virtual_candidates": [
    {
      "feature_name": "...",
      "score": 0.52,
      "content": "..."
    }
  ]
}
```

Responsibilities:

- Retrieve top-k virtual profile candidates.
- Do not finalize here.

LangSmith should log:

- index name,
- query,
- top-k candidate names,
- vector distances.

---

### 6.3 `virtual_profile_match`

LLM structured-output node.

Purpose:

- Determine whether the whole condition maps to an existing virtual profile.

Example output:

```json
{
  "matched": false,
  "virtual_profile": "",
  "reasoning": "No virtual profile directly represents this condition."
}
```

If matched:

```json
{
  "source": "virtual_profile",
  "feature_name": "<virtual profile name>",
  "table_name": "RE_VIRTUAL_PROFILE_DESCRIPTION"
}
```

---

### 6.4 `customer_360_retrieval`

Search index:

```text
360_profile
```

Purpose:

- Check whether Customer 360 already has a direct feature.

Important false-positive example:

```text
customer is from India
```

must not match:

```text
CUST_360_IDD_INDIA_CALLING_FLAG_30D
```

because that means “customer called India,” not “customer is from India.”

---

### 6.5 `customer_360_match`

LLM structured-output node.

Example output:

```json
{
  "matched": false,
  "kpi": "",
  "reasoning": "Candidates are about IDD calling or revenue, not nationality."
}
```

If matched:

```json
{
  "source": "customer_360",
  "group_name": "360_PROFILE",
  "feature_name": "CUST_360_DERIVED_NATIONALITY"
}
```

---

### 6.6 `group_route_v2`

Search index:

```text
Group_detail_v2
```

Input:

```json
{
  "condition": "customer is from India"
}
```

Output:

```json
{
  "ranked_groups": [
    {
      "group_name": "Profile_Cdr_group",
      "score": 0.516097,
      "content": "...positive-only group context...",
      "metadata": "..."
    },
    {
      "group_name": "Subscriptions",
      "score": 0.633893,
      "content": "..."
    }
  ]
}
```

Responsibilities:

- Retrieve ranked groups once.
- Do not ask LLM repeatedly for “next best group.”

LangSmith should log:

- selected top group,
- full ranked group list,
- top scores.

---

### 6.7 `select_next_group`

No LLM.

Input:

```json
{
  "ranked_groups": [...],
  "attempted_groups": []
}
```

Output:

```json
{
  "current_group": "Profile_Cdr_group",
  "current_group_context": "...",
  "attempted_groups": ["Profile_Cdr_group"]
}
```

Responsibilities:

- Select first group not already attempted.
- Track attempted groups.
- Stop after `max_group_attempts`, suggested default: `3`.

---

### 6.8 `normalize_query_for_group`

OpenAI-compatible Groq structured-output call.

Input:

```json
{
  "condition": "customer is from India",
  "current_group": "Profile_Cdr_group",
  "current_group_context": "..."
}
```

Output:

```json
{
  "selected_group": "Profile_Cdr_group",
  "attribute": "nationality",
  "operator": "equals",
  "value": "India",
  "normalized_search_text": "subscriber registered nationality country India",
  "reasoning": "The query asks whether the customer is from a country, which maps to nationality in the profile group."
}
```

Important requirements:

- Use OpenAI-compatible client.
- Groq base URL:

```python
base_url="https://api.groq.com/openai/v1"
```

- Use Pydantic structured output.
- Set `extra="forbid"` / `additionalProperties: false` for strict JSON Schema.
- Do not hardcode API keys.

---

### 6.9 `feature_search_in_group`

Search index:

```text
<current_group>
```

Example:

```text
Profile_Cdr_group
```

Search query:

```text
normalized_search_text
```

Output:

```json
{
  "feature_candidates": [
    {
      "feature_name": "Profile_Cdr_Nationality",
      "score": 0.42,
      "content": "for kpi Profile_Cdr_Nationality the description is subscriber profile CDR registered nationality"
    },
    {
      "feature_name": "Dealer",
      "score": 0.50,
      "content": "for kpi Dealer the description is subscriber acquisition dealer string"
    }
  ]
}
```

---

### 6.10 `dedupe_feature_candidates`

No LLM.

Purpose:

- Collapse repeated feature records by `feature_name`.
- Keep best score.
- Optionally merge descriptions.

Input:

```json
{
  "feature_candidates": [
    {"feature_name": "Profile_Cdr_Handset_Manufacturer", "score": 0.48},
    {"feature_name": "Profile_Cdr_Handset_Manufacturer", "score": 0.54},
    {"feature_name": "Profile_Cdr_Nationality", "score": 0.57}
  ]
}
```

Output:

```json
{
  "deduped_feature_candidates": [
    {"feature_name": "Profile_Cdr_Handset_Manufacturer", "score": 0.48},
    {"feature_name": "Profile_Cdr_Nationality", "score": 0.57}
  ]
}
```

---

### 6.11 `feature_validate`

LLM structured-output node over top 3-5 deduped candidates.

Purpose:

- Verify the candidate feature directly satisfies the normalized condition.
- Reject related-but-not-identical features.

Input:

```json
{
  "condition": "customer is from India",
  "normalized_query": {
    "attribute": "nationality",
    "operator": "equals",
    "value": "India"
  },
  "selected_group": "Profile_Cdr_group",
  "feature_candidates": [
    {
      "feature_name": "Profile_Cdr_Nationality",
      "description": "subscriber profile CDR registered nationality"
    },
    {
      "feature_name": "Dealer",
      "description": "subscriber acquisition dealer string"
    }
  ]
}
```

Output if matched:

```json
{
  "matched": true,
  "feature_name": "Profile_Cdr_Nationality",
  "semantic_score": 96,
  "logical_score": 98,
  "reasoning": "The condition asks for customer country/origin, which directly maps to registered nationality."
}
```

Output if not matched:

```json
{
  "matched": false,
  "feature_name": "",
  "semantic_score": 0,
  "logical_score": 0,
  "reasoning": "No candidate directly represents the requested business attribute."
}
```

---

### 6.12 `fallback_group_loop`

Conditional edge.

If feature validation fails:

```text
if attempted_groups < max_group_attempts:
    select_next_group
else:
    mark_unmatched
```

No repeated LLM group classification.

---

### 6.13 `finalize_condition`

Output:

```json
{
  "condition": "customer is from India",
  "source": "normal_kpi_group",
  "group_name": "Profile_Cdr_group",
  "feature_name": "Profile_Cdr_Nationality",
  "operator": "equals",
  "value": "India",
  "confidence": 0.96,
  "reasoning": "The condition asks for registered nationality."
}
```

---

### 6.14 `aggregate_results`

Input:

```json
{
  "matches": [...],
  "unmatched": [...]
}
```

Output:

```json
{
  "matches": [...],
  "unmatched": [],
  "mismatch_percentage": 0
}
```

---

## 7. LangSmith Monitoring Requirements

LangSmith should be enabled from the beginning.

Environment variables:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY="..."
export LANGSMITH_PROJECT="telecom-kpi-mapper"
```

Each node should log meaningful metadata.

Recommended trace metadata:

```json
{
  "request_id": "uuid",
  "condition": "customer is from India",
  "node": "group_route_v2",
  "selected_group": "Profile_Cdr_group",
  "ranked_groups": ["Profile_Cdr_group", "Subscriptions", "LIFECYCLE_CDR"],
  "normalized_search_text": "subscriber registered nationality country India",
  "feature_candidates": ["Profile_Cdr_Nationality", "Dealer", "Business"],
  "final_feature": "Profile_Cdr_Nationality",
  "source": "normal_kpi_group"
}
```

Minimum tracked steps:

1. input payload,
2. virtual profile retrieval results,
3. virtual profile match decision,
4. 360 retrieval results,
5. 360 match decision,
6. group retrieval from `Group_detail_v2`,
7. selected group,
8. normalized query structured output,
9. feature retrieval candidates,
10. feature validation structured output,
11. fallback attempts,
12. final output.

---

## 8. OpenAI-Compatible Structured Output Pattern

Use this pattern for all Groq LLM calls.

```python
from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

class NormalizedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_group: str = Field(...)
    attribute: str = Field(...)
    operator: str = Field(...)
    value: str = Field(...)
    normalized_search_text: str = Field(...)
    reasoning: str = Field(...)

schema = NormalizedQuery.model_json_schema()
schema["additionalProperties"] = False

response = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[...],
    temperature=0.1,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "normalized_query",
            "schema": schema,
            "strict": True,
        },
    },
)

normalized = NormalizedQuery.model_validate_json(
    response.choices[0].message.content
)
```

Important: Groq strict structured outputs require `additionalProperties: false` on object schemas. The tested notebook failed until this was added.

---

## 9. Data Files in This Package

### `vp_rag_tested_notebook_sanitized.py`

Sanitized notebook export containing the tested Redis, embedding, group routing, feature retrieval, and Groq structured-output code.

### `vp_rag_tested_notebook_sanitized.ipynb`

Notebook version generated from the sanitized Python export.

### `group_detail_v2_normal_source.jsonl`

The source records used to build the new group routing index. This excludes `360_PROFILE` because Customer 360 is handled earlier as a priority path.

### `group_detail_v2_all_source.jsonl`

Same as above but includes `360_PROFILE` for review.

### `group_detail_v2_metadata.json`

Structured metadata for group records.

### `group_detail_v2_review.csv`

Human-readable review sheet for group routing docs.

### `group_detail_v2_preview.md`

Preview of enriched group documents.

### `telecom_table_knowledge_base.json`

Curated table knowledge base used to build enriched group docs.

### `RE_FEATURE_DETAILS - RE_PROFILE_DESCRIPTION.csv`

Original KPI/feature catalog.

---

## 10. Recommended Implementation Order

Do not implement the full graph at once.

### Phase 1: Minimal LangGraph slice

Implement:

```text
group_route_v2
→ select_next_group
→ normalize_query_for_group
→ feature_search_in_group
→ return top candidates
```

Goal:

- Convert the notebook flow to LangGraph.
- Confirm trace visibility in LangSmith.

### Phase 2: Feature validation

Add:

```text
dedupe_feature_candidates
→ feature_validate
→ finalize_condition
```

Goal:

- Return final feature instead of raw candidates.

### Phase 3: Fallback loop

Add:

```text
if feature_validate fails → next ranked group → retry
```

Goal:

- Match current n8n fallback behavior without repeated group-classification LLM calls.

### Phase 4: Priority paths

Add:

```text
virtual_profile_retrieval
virtual_profile_match
customer_360_retrieval
customer_360_match
```

Goal:

- Restore full priority order.

### Phase 5: Multi-condition aggregation

Add:

```text
process all input conditions
aggregate matches/unmatched
calculate mismatch_percentage
```

Goal:

- Production API output.

---

## 11. Keep It Simple

Avoid overcomplication:

- Do not add cross-encoder reranking yet.
- Do not rebuild feature indexes yet unless feature retrieval remains poor.
- Do not ask the LLM repeatedly for the next best group.
- Do not use the LLM for tasks that deterministic state can handle.
- Use structured outputs for every LLM call.
- Use LangSmith for observability, not for business logic.

Current best architecture:

```text
Redis RAG handles retrieval.
LangGraph handles state and control flow.
Groq 20B handles small structured tasks.
LangSmith monitors every step.
```
