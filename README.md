# KPI Finder — Telecom KPI Mapper

Maps natural-language campaign conditions to the exact KPI feature and database table using LangGraph, Redis vector search, and Groq LLM.

**Example:** `"customer is from India"` → `Profile_Cdr_group / Profile_Cdr_Nationality = India`

For a plain-English explanation of how the system works and all the scenarios it handles, see [SIMPLE_EXPLANATION.md](./SIMPLE_EXPLANATION.md).

---

## Prerequisites

| Dependency | Purpose |
|---|---|
| Python 3.11+ | Runtime |
| Redis Stack (with RediSearch) | Vector index storage |
| Ollama | Local embedding model (`sachin_telecom-kpi-embedding`) |
| Groq API key | LLM structured output |
| LangSmith API key | Tracing (optional but recommended) |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/spb722/kpi-finder.git
cd kpi-finder
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```bash
# Redis
REDIS_HOST=10.0.11.179
REDIS_PORT=6378
REDIS_PASSWORD=your_redis_password

# Ollama (embedding model)
OLLAMA_BASE_URL=http://10.0.6.103:11434
EMBED_MODEL=sachin_telecom-kpi-embedding:latest

# Groq (LLM)
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

# LangSmith tracing (optional)
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=telecom-kpi-mapper

# Fallback attempts (optional, default: 3)
MAX_GROUP_ATTEMPTS=3
```

> Never commit `.env` to source control — it is already in `.gitignore`.

### 3. Start the API server

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

---

## API Reference

### `POST /map`

Maps one or more plain-English conditions to KPI features.

**Request body:**

```json
{
  "conditions": ["your condition here"],
  "check": true,
  "debug": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `conditions` | `string[]` | Yes | One or more plain-English campaign conditions |
| `check` | `bool` | No | Kept for compatibility (default: `true`) |
| `debug` | `bool` | No | Return intermediate candidates (default: `false`) |

**Response:**

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
  "mismatch_percentage": 0.0,
  "request_id": "uuid"
}
```

### `GET /health`

Returns `{"status": "ok"}` when the server is running.

---

## Testing the API — Sample Conditions

You can test using `curl`, the interactive docs at `http://localhost:8000/docs`, or any HTTP client.

### Test 1 — Nationality (Profile)

```bash
curl -s -X POST http://localhost:8000/map \
  -H "Content-Type: application/json" \
  -d '{"conditions": ["customer is from India"]}' | python -m json.tool
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

---

### Test 2 — IDD Calling (should NOT match nationality)

```bash
curl -s -X POST http://localhost:8000/map \
  -H "Content-Type: application/json" \
  -d '{"conditions": ["customer called India in last 30 days"]}' | python -m json.tool
```

Expected: matches an IDD/calling-related KPI — **not** `Profile_Cdr_Nationality`.

---

### Test 3 — Recharge Amount

```bash
curl -s -X POST http://localhost:8000/map \
  -H "Content-Type: application/json" \
  -d '{"conditions": ["customers who recharged more than 5 OMR"]}' | python -m json.tool
```

Expected:
```json
{
  "group_name": "Recharge_Seg_Fct"
}
```

---

### Test 4 — Bonus Received

```bash
curl -s -X POST http://localhost:8000/map \
  -H "Content-Type: application/json" \
  -d '{"conditions": ["customers who received bonus in last 7 days"]}' | python -m json.tool
```

Expected:
```json
{
  "group_name": "LIFECYCLE_CDR"
}
```

---

### Test 5 — Data Usage

```bash
curl -s -X POST http://localhost:8000/map \
  -H "Content-Type: application/json" \
  -d '{"conditions": ["customers with total data usage above 1GB"]}' | python -m json.tool
```

Expected:
```json
{
  "group_name": "Common_Seg_Fct"
}
```

---

### Test 6 — Multiple Conditions in One Request

```bash
curl -s -X POST http://localhost:8000/map \
  -H "Content-Type: application/json" \
  -d '{
    "conditions": [
      "customer is from India",
      "customers who recharged more than 5 OMR",
      "customers with total data usage above 1GB"
    ]
  }' | python -m json.tool
```

Each condition is processed independently. The response will contain one entry per condition in `matches` or `unmatched`, plus an overall `mismatch_percentage`.

---

## Running the Automated Acceptance Tests

The acceptance tests require live Redis, Ollama, and Groq connections.

```bash
RUN_LIVE_ACCEPTANCE=1 pytest tests/test_acceptance.py -v
```

The tests will be **skipped automatically** if:
- `RUN_LIVE_ACCEPTANCE=1` is not set, or
- Redis or Ollama are not reachable at the configured addresses.

To run all tests (including unit tests that do not need live services):

```bash
pytest tests/ -v
```

---

## Project Structure

```
kpi-finder/
├── api.py                        # FastAPI entrypoint (POST /map)
├── requirements.txt
├── .env                          # Local config (not committed)
├── kpi_finder/
│   ├── graph.py                  # LangGraph workflow definition
│   ├── state.py                  # ConditionState TypedDict
│   ├── models.py                 # Pydantic models for LLM structured output
│   ├── redis_client.py           # vector_search() using Ollama embeddings
│   ├── llm_client.py             # call_structured() using Groq
│   └── nodes/
│       ├── virtual_profile.py    # Layer 1: Virtual Profile retrieval + match
│       ├── customer_360.py       # Layer 2: Customer 360 retrieval + match
│       ├── group_route.py        # Layer 3: Group routing via Group_detail_v2
│       ├── normalize_query.py    # LLM query normalization per group
│       ├── feature_search.py     # Feature search + deduplication
│       ├── feature_validate.py   # LLM feature validation
│       └── finalize.py           # finalize_condition + mark_unmatched
├── tests/
│   ├── test_acceptance.py        # 5 live end-to-end acceptance tests
│   ├── test_api.py               # FastAPI endpoint tests
│   ├── test_feature_validate.py  # Unit tests for feature validation
│   └── test_redis_client.py      # Unit tests for Redis client
├── SIMPLE_EXPLANATION.md         # Non-technical explanation with all scenarios
├── DEVELOPER_HANDOFF.md          # Full technical design and architecture
└── IMPLEMENTATION_PLAN.md        # LangGraph node specifications
```

---

## How It Works (Short Version)

The system checks three layers in priority order for each condition:

1. **Virtual Profiles** — pre-built named condition bundles
2. **Customer 360** — pre-computed customer-level summary KPIs
3. **Normal KPI Groups** — raw feature columns, searched via group routing → query normalization → feature validation, with up to 3 fallback group attempts

See [SIMPLE_EXPLANATION.md](./SIMPLE_EXPLANATION.md) for a full walkthrough with examples.