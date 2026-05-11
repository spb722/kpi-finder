import httpx
from fastapi.testclient import TestClient

import api


class _FailingGraph:
    def invoke(self, state):
        raise httpx.ConnectTimeout("timed out")


def test_map_conditions_returns_503_for_dependency_failure(monkeypatch):
    monkeypatch.setattr(api, "condition_graph", _FailingGraph())

    client = TestClient(api.app)
    response = client.post("/map", json={"conditions": ["customer is from India"]})

    assert response.status_code == 503
    assert "dependency unavailable" in response.json()["detail"]
