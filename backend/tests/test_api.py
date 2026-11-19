"""Seam 1: the backend HTTP API, built with injected fake models."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        llm=FakeListChatModel(responses=["unused"]),
        embeddings=DeterministicFakeEmbedding(size=16),
    )
    return TestClient(app)


def test_loading_the_sample_returns_a_session_with_its_clauses(client):
    response = client.post("/api/sample")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    clauses = [c["clause"] for c in body["chunks"]]
    assert len(clauses) >= 5
    assert all(c["page"] >= 1 for c in body["chunks"])
    text = " ".join(c["text"] for c in body["chunks"]).lower()
    # planted risky clauses from the spec
    assert "automatically renew" in text
    assert "forfeit" in text
    assert "early termination" in text


def test_a_loaded_session_can_be_fetched_again_by_id(client):
    session_id = client.post("/api/sample").json()["session_id"]

    response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id
    assert response.json()["chunks"]


def test_unknown_session_is_a_404(client):
    assert client.get("/api/sessions/does-not-exist").status_code == 404


def test_each_sample_load_creates_a_separate_session(client):
    first = client.post("/api/sample").json()["session_id"]
    second = client.post("/api/sample").json()["session_id"]

    assert first != second
