"""Seam 1: streamed summary and disclaimer (#4)."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app

VALID_SUMMARY = {
    "parties": ["Acme Property Holdings Ltd (Landlord)", "Jane Example (Tenant)"],
    "key_dates": ["Starts 1 January 2027", "Ends 31 December 2027"],
    "payments": ["Rent 1,200 per month", "Deposit of three months rent"],
    "duration": "12 months",
    "obligations": ["Pay rent by the 1st", "Do all repairs"],
}


def make_client(*responses: str) -> TestClient:
    app = create_app(
        llm=FakeListChatModel(responses=list(responses)),
        embeddings=DeterministicFakeEmbedding(size=16),
    )
    return TestClient(app)


def read_events(client: TestClient, session_id: str) -> list[tuple[str, dict]]:
    """Parse a Server-Sent Events response into (event, data) pairs."""
    with client.stream("GET", f"/api/sessions/{session_id}/analyze") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())
    events = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_summary_is_streamed_first_then_done():
    client = make_client(json.dumps(VALID_SUMMARY))
    session_id = client.post("/api/sample").json()["session_id"]

    events = read_events(client, session_id)

    assert [name for name, _ in events] == ["summary", "done"]
    summary = events[0][1]["summary"]
    assert summary["duration"] == "12 months"
    assert summary["parties"] == VALID_SUMMARY["parties"]


def test_disclaimer_is_included_in_the_response():
    client = make_client(json.dumps(VALID_SUMMARY))
    session_id = client.post("/api/sample").json()["session_id"]

    events = dict(read_events(client, session_id))

    assert "not legal advice" in events["summary"]["disclaimer"].lower()


def test_json_wrapped_in_a_code_fence_or_thinking_is_still_accepted():
    reply = "<think>let me read</think>\n```json\n" + json.dumps(VALID_SUMMARY) + "\n```"
    client = make_client(reply)
    session_id = client.post("/api/sample").json()["session_id"]

    events = read_events(client, session_id)

    assert events[0][0] == "summary"


def test_malformed_output_is_retried_once_and_then_succeeds():
    client = make_client("not json at all", json.dumps(VALID_SUMMARY))
    session_id = client.post("/api/sample").json()["session_id"]

    events = read_events(client, session_id)

    assert [name for name, _ in events] == ["summary", "done"]


def test_output_missing_required_fields_counts_as_malformed():
    client = make_client(json.dumps({"parties": ["A"]}), json.dumps(VALID_SUMMARY))
    session_id = client.post("/api/sample").json()["session_id"]

    events = read_events(client, session_id)

    assert [name for name, _ in events] == ["summary", "done"]


def test_malformed_output_twice_yields_an_error_event():
    client = make_client("garbage", "still garbage", json.dumps(VALID_SUMMARY))
    session_id = client.post("/api/sample").json()["session_id"]

    events = read_events(client, session_id)

    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["message"]


def test_analyzing_an_unknown_session_is_a_404():
    client = make_client(json.dumps(VALID_SUMMARY))

    assert client.get("/api/sessions/nope/analyze").status_code == 404


@pytest.mark.parametrize("model_error", [ConnectionError("ollama is down")])
def test_a_model_failure_yields_an_error_event(model_error):
    class BrokenModel(FakeListChatModel):
        def _call(self, *args, **kwargs):
            raise model_error

    app = create_app(
        llm=BrokenModel(responses=["x"]), embeddings=DeterministicFakeEmbedding(size=16)
    )
    client = TestClient(app)
    session_id = client.post("/api/sample").json()["session_id"]

    events = read_events(client, session_id)

    assert [name for name, _ in events] == ["error"]
