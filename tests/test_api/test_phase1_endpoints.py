"""
Tests for Phase-1 REST API Endpoints
"""

from fastapi.testclient import TestClient
import pytest

from apps.api.main import app

client = TestClient(app)


def test_api_health_and_info():
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_info = client.get("/info")
    assert res_info.status_code == 200
    data = res_info.json()
    assert "version" in data
    assert data["project_name"] == "Engineering Intelligence Hub"


def test_api_ingest_and_retrieve_file():
    # 1. Ingest a file
    ingest_payload = {
        "repository": "test/repo",
        "file_path": "src/module.py",
        "content": "def process_data(x: int) -> int:\n    return x + 42\n",
        "artifact_type": "source_code",
        "collection_name": "eih_api_test_coll",
    }
    res_ingest = client.post("/ingest/file", json=ingest_payload)
    if res_ingest.status_code == 500 and "connection" in res_ingest.text.lower():
        pytest.skip("Docker Qdrant not running on localhost:6333")
    assert res_ingest.status_code == 200
    assert res_ingest.json()["status"] == "completed"

    # 2. Retrieve from collection
    retrieve_payload = {
        "query": "process_data addition",
        "repository": "test/repo",
        "top_k": 3,
    }
    res_ret = client.post("/retrieve", json=retrieve_payload)
    assert res_ret.status_code == 200
    ret_data = res_ret.json()
    assert "chunks" in ret_data
    assert "task_id" in ret_data


def test_api_query_endpoint():
    query_payload = {
        "task_id": "api-task-001",
        "query": "Explain how routing works in Flask",
        "repository": "pallets/flask",
    }
    res = client.post("/query", json=query_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["task_id"] == "api-task-001"
    assert "answer" in data
    assert "latency_ms" in data
    assert "energy_joules" in data
    assert "cost_usd" in data
    assert "co2e_grams" in data
