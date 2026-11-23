"""Seam 1: contract type packs (#15).

With only the General pack configured, everything behaves as before (the
existing API tests cover that). These tests use their own packs.
"""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app
from lce.packs import InvalidPack, load_packs

TEST_PACK = {
    "id": "test_employment",
    "name": "Test employment",
    "description": "An employment contract",
    "summary_fields": [
        {"name": "job_title", "label": "Job title", "description": "The role", "kind": "single"},
        {"name": "benefits", "label": "Benefits", "description": "Extras", "kind": "list"},
    ],
    "risk_categories": [
        {"id": "overtime", "label": "Unpaid overtime", "description": "Extra hours without pay"},
    ],
    "sample": "sample_lease.pdf",
}


class RoutingFake(FakeListChatModel):
    """Answers the summary prompt with `summary` and each clause prompt via `routes`."""

    summary: str
    routes: dict[str, str]

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = str(messages[-1].content)
        if prompt.startswith("Contract:"):
            return self.summary
        for needle, reply in self.routes.items():
            if needle in prompt:
                return reply
        return json.dumps({"flags": []})


def make_client(summary: dict, routes: dict[str, str] | None = None, packs=None) -> TestClient:
    llm = RoutingFake(responses=["unused"], summary=json.dumps(summary), routes=routes or {})
    app = create_app(llm=llm, embeddings=DeterministicFakeEmbedding(size=16), packs=packs)
    return TestClient(app)


def read_events(client: TestClient, session_id: str) -> list[tuple[str, dict]]:
    with client.stream("GET", f"/api/sessions/{session_id}/analyze") as response:
        raw = "".join(response.iter_text())
    out = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_the_summary_uses_the_active_packs_fields():
    client = make_client(
        {"job_title": "Clerk", "benefits": ["Medical cover"]},
        packs=[TEST_PACK],
    )
    sid = client.post("/api/sample").json()["session_id"]

    data = dict(read_events(client, sid))["summary"]

    assert data["summary"] == {"job_title": "Clerk", "benefits": ["Medical cover"]}
    assert data["fields"] == [
        {"name": "job_title", "label": "Job title", "kind": "single"},
        {"name": "benefits", "label": "Benefits", "kind": "list"},
    ]


def test_a_summary_missing_a_pack_field_is_retried_then_errors():
    client = make_client({"job_title": "Clerk"}, packs=[TEST_PACK])  # no "benefits"
    sid = client.post("/api/sample").json()["session_id"]

    assert [n for n, _ in read_events(client, sid)] == ["error"]


def test_risk_flags_use_the_active_packs_categories():
    overtime = {
        "flags": [
            {
                "category": "overtime",
                "severity": "medium",
                "explanation": "x",
                "question_to_ask": "y",
            }
        ]
    }
    client = make_client(
        {"job_title": "Clerk", "benefits": []},
        routes={"automatically renew": json.dumps(overtime)},
        packs=[TEST_PACK],
    )
    sid = client.post("/api/sample").json()["session_id"]

    flags = [d for n, d in read_events(client, sid) if n == "risk_flag"]

    assert [(f["category"], f["category_label"]) for f in flags] == [
        ("overtime", "Unpaid overtime")
    ]


def test_general_is_the_default_pack_and_keeps_the_original_summary_fields():
    general_summary = {
        "parties": ["A"],
        "key_dates": ["1 Jan"],
        "payments": ["100"],
        "duration": "1 year",
        "obligations": ["Pay"],
    }
    client = make_client(general_summary)
    sid = client.post("/api/sample").json()["session_id"]

    data = dict(read_events(client, sid))["summary"]

    assert data["summary"] == general_summary
    assert [f["name"] for f in data["fields"]] == [
        "parties",
        "duration",
        "key_dates",
        "payments",
        "obligations",
    ]


@pytest.mark.parametrize(
    "broken",
    [
        {k: v for k, v in TEST_PACK.items() if k != "summary_fields"},
        dict(TEST_PACK, summary_fields=[]),
        dict(TEST_PACK, risk_categories=[]),
        dict(TEST_PACK, sample="does_not_exist.pdf"),
        dict(
            TEST_PACK,
            summary_fields=[TEST_PACK["summary_fields"][0], TEST_PACK["summary_fields"][0]],
        ),
        dict(TEST_PACK, summary_fields=[dict(TEST_PACK["summary_fields"][0], kind="table")]),
    ],
    ids=[
        "no-summary-fields",
        "empty-summary-fields",
        "no-categories",
        "missing-sample",
        "duplicate-field",
        "bad-kind",
    ],
)
def test_an_invalid_pack_is_rejected_when_the_app_is_built(broken):
    with pytest.raises(InvalidPack):
        create_app(
            llm=FakeListChatModel(responses=["x"]),
            embeddings=DeterministicFakeEmbedding(size=16),
            packs=[broken],
        )


def test_duplicate_pack_ids_are_rejected():
    with pytest.raises(InvalidPack):
        load_packs([TEST_PACK, TEST_PACK])


def test_the_bundled_packs_are_valid_and_general_is_the_default():
    packs = load_packs()

    assert packs[0].id == "general"


def test_a_pack_needs_at_least_one_example_question():
    with pytest.raises(InvalidPack):
        load_packs([dict(TEST_PACK, example_questions=[])])
