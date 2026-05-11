"""
Acceptance tests from the Implementation Plan.

These tests require live Redis + Ollama + Groq connections.
Run with: pytest tests/test_acceptance.py -v

Set environment variables (or use .env file) before running.
"""

import os
import socket
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

load_dotenv()

# Skip all tests if env is not configured
def _tcp_reachable(host: str | None, port: int | None, timeout: float = 2.0) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ollama_reachable() -> bool:
    raw_url = os.environ.get("OLLAMA_BASE_URL")
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return _tcp_reachable(parsed.hostname, port)


_CONFIGURED = all([
    os.environ.get("REDIS_HOST"),
    os.environ.get("GROQ_API_KEY"),
    os.environ.get("OLLAMA_BASE_URL"),
])
_LIVE_SERVICES_REACHABLE = (
    _CONFIGURED
    and os.environ.get("RUN_LIVE_ACCEPTANCE") == "1"
    and _tcp_reachable(os.environ.get("REDIS_HOST"), int(os.environ.get("REDIS_PORT", "6379")))
    and _ollama_reachable()
)


@pytest.fixture(scope="module")
def graph():
    from kpi_finder.graph import condition_graph
    return condition_graph


def run_condition(graph, condition: str) -> dict:
    result = graph.invoke({
        "request_id": "test",
        "condition": condition,
        "attempted_groups": [],
        "errors": [],
    })
    return result


@pytest.mark.skipif(
    not _LIVE_SERVICES_REACHABLE,
    reason="Set RUN_LIVE_ACCEPTANCE=1 and ensure Redis/Ollama/Groq are reachable",
)
class TestAcceptance:

    def test_customer_from_india(self, graph):
        """Test 1: nationality condition routes to Profile_Cdr_group."""
        result = run_condition(graph, "customer is from India")
        match = result.get("match")
        assert match is not None, "Expected a match"
        assert match["group_name"] == "Profile_Cdr_group"
        assert match["feature_name"] == "Profile_Cdr_Nationality"
        assert match["operator"] == "equals"
        assert match["value"] == "India"

    def test_customer_called_india_not_nationality(self, graph):
        """Test 2: IDD/calling condition should NOT route to Profile_Cdr_Nationality."""
        result = run_condition(graph, "customer called India in last 30 days")
        match = result.get("match")
        # Must not match nationality
        if match:
            assert match.get("feature_name") != "Profile_Cdr_Nationality", (
                "IDD calling condition incorrectly matched to nationality"
            )

    def test_recharge_condition(self, graph):
        """Test 3: recharge condition routes to Recharge_Seg_Fct."""
        result = run_condition(graph, "customers who recharged more than 5 OMR")
        match = result.get("match")
        assert match is not None, "Expected a match"
        assert match["group_name"] == "Recharge_Seg_Fct"

    def test_bonus_condition(self, graph):
        """Test 4: bonus condition routes to LIFECYCLE_CDR."""
        result = run_condition(graph, "customers who received bonus in last 7 days")
        match = result.get("match")
        assert match is not None, "Expected a match"
        assert match["group_name"] == "LIFECYCLE_CDR"

    def test_data_usage_condition(self, graph):
        """Test 5: data usage condition routes to Common_Seg_Fct."""
        result = run_condition(graph, "customers with total data usage above 1GB")
        match = result.get("match")
        assert match is not None, "Expected a match"
        assert match["group_name"] == "Common_Seg_Fct"
