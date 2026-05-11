"""
FastAPI entrypoint for the Telecom KPI Mapper.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8000
"""

import uuid
from contextlib import asynccontextmanager

import httpx
import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAIError
from pydantic import BaseModel, Field

load_dotenv()

from kpi_finder.graph import condition_graph  # noqa: E402 (after dotenv)


class KPIRequest(BaseModel):
    conditions: list[str] = Field(..., min_length=1)
    check: bool = True
    debug: bool = False


class KPIResponse(BaseModel):
    matches: list[dict]
    unmatched: list[dict]
    mismatch_percentage: float
    request_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Graph is built at import time; nothing special to start/stop
    yield


app = FastAPI(title="Telecom KPI Mapper", lifespan=lifespan)


@app.post("/map", response_model=KPIResponse)
def map_conditions(request: KPIRequest) -> KPIResponse:
    request_id = str(uuid.uuid4())
    matches = []
    unmatched = []

    for condition in request.conditions:
        initial_state = {
            "request_id": request_id,
            "condition": condition,
            "attempted_groups": [],
            "errors": [],
        }

        try:
            result = condition_graph.invoke(initial_state)
        except (httpx.HTTPError, redis.RedisError, OpenAIError, TimeoutError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"KPI mapper dependency unavailable or misconfigured: {type(exc).__name__}",
            ) from exc

        if result.get("match"):
            matches.append(result["match"])
        elif result.get("unmatched"):
            unmatched.append(result["unmatched"])
        else:
            unmatched.append({
                "condition": condition,
                "reason": "Unexpected graph termination.",
            })

    total = len(request.conditions)
    mismatch_pct = round(len(unmatched) / total * 100, 2) if total else 0.0

    return KPIResponse(
        matches=matches,
        unmatched=unmatched,
        mismatch_percentage=mismatch_pct,
        request_id=request_id,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
