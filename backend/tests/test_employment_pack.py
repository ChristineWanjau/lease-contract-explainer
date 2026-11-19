"""Seam 1: choosing a contract type by hand, and the Kenyan employment pack (#16)."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app
from lce.packs import load_packs

EMPLOYMENT_SUMMARY = {
    "employer_and_employee": ["Example Ltd (employer)", "Jane Example (employee)"],
    "job_title": "Accounts Assistant",
    "start_date_and_term": "Starts 1 February 2027, permanent",
    "probation": "Six months",
    "salary": "KES 60,000 per month",
    "working_hours": "8am to 5pm, Monday to Saturday",
    "leave": ["14 days annual leave"],
    "notice_period": "7 days",
    "your_obligations": ["Keep company information confidential"],
}

GENERAL_SUMMARY = {
    "parties": ["A"],
    "duration": "1 year",
    "key_dates": ["1 Jan"],
    "payments": ["100"],
    "obligations": ["Pay"],
}


class PromptRouter(FakeListChatModel):
    """Summary replies chosen by which pack's schema is in the system prompt; clause replies by text."""

    routes: dict[str, str]

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        system, prompt = str(messages[0].content), str(messages[-1].content)
        if prompt.startswith("Contract:"):
            if "job_title" in system:
                return json.dumps(EMPLOYMENT_SUMMARY)
            return json.dumps(GENERAL_SUMMARY)
        for needle, reply in self.routes.items():
            if needle in prompt:
                return reply
        return json.dumps({"flags": []})


def make_client(routes: dict[str, str] | None = None) -> TestClient:
    llm = PromptRouter(responses=["unused"], routes=routes or {})
    return TestClient(create_app(llm=llm, embeddings=DeterministicFakeEmbedding(size=16)))


def read_events(client: TestClient, session_id: str) -> list[tuple[str, dict]]:
    with client.stream("GET", f"/api/sessions/{session_id}/analyze") as response:
        raw = "".join(response.iter_text())
    out = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_the_bundled_packs_are_general_then_kenyan_employment():
    assert [p.id for p in load_packs()] == ["general", "kenya_employment"]


def test_listing_packs_returns_each_pack_with_its_sample():
    client = make_client()

    packs = client.get("/api/packs").json()

    assert [(p["id"], p["name"]) for p in packs] == [
        ("general", "General contract"),
        ("kenya_employment", "Kenyan employment contract"),
    ]
    assert all(p["sample_label"] for p in packs)


def test_load_sample_defaults_to_the_general_pack_and_sample():
    client = make_client()

    body = client.post("/api/sample").json()

    assert body["pack"] == "general"
    assert "automatically renew" in " ".join(c["text"] for c in body["chunks"]).lower()


def test_load_sample_for_a_chosen_pack_uses_that_packs_sample_and_type():
    client = make_client()

    body = client.post("/api/sample", params={"pack": "kenya_employment"}).json()

    assert body["pack"] == "kenya_employment"
    text = " ".join(c["text"] for c in body["chunks"]).lower()
    assert "employer" in text and "employee" in text
    assert client.get(f"/api/sessions/{body['session_id']}").json()["pack"] == "kenya_employment"


def test_load_sample_for_an_unknown_pack_is_rejected():
    client = make_client()

    response = client.post("/api/sample", params={"pack": "mortgage"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_pack"


def test_uploads_start_as_the_general_pack():
    client = make_client()

    pdf = next(p for p in load_packs() if p.id == "kenya_employment").sample_bytes()
    body = client.post(
        "/api/upload", files={"file": ("contract.pdf", pdf, "application/pdf")}
    ).json()

    assert body["pack"] == "general"


def test_setting_the_pack_changes_the_analysis():
    client = make_client()
    sid = client.post("/api/sample", params={"pack": "kenya_employment"}).json()["session_id"]

    response = client.put(f"/api/sessions/{sid}/pack", json={"pack": "general"})

    assert response.status_code == 200
    assert response.json()["pack"] == "general"
    summary = dict(read_events(client, sid))["summary"]
    assert set(summary["summary"]) == set(GENERAL_SUMMARY)


def test_setting_an_unknown_pack_is_rejected_and_keeps_the_current_one():
    client = make_client()
    sid = client.post("/api/sample", params={"pack": "kenya_employment"}).json()["session_id"]

    response = client.put(f"/api/sessions/{sid}/pack", json={"pack": "mortgage"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_pack"
    assert client.get(f"/api/sessions/{sid}").json()["pack"] == "kenya_employment"


def test_setting_the_pack_on_an_unknown_session_is_a_404():
    client = make_client()

    response = client.put("/api/sessions/nope/pack", json={"pack": "general"})

    assert response.status_code == 404


def test_the_employment_pack_produces_the_employment_summary_fields():
    client = make_client()
    sid = client.post("/api/sample", params={"pack": "kenya_employment"}).json()["session_id"]

    summary = dict(read_events(client, sid))["summary"]

    names = [f["name"] for f in summary["fields"]]
    assert {"job_title", "salary", "working_hours", "leave"} <= set(names)
    assert summary["summary"]["job_title"] == "Accounts Assistant"


EMPLOYMENT_CATEGORIES = [
    "probation",
    "termination",
    "restrictive_covenant",
    "pay_deductions",
    "overtime",
    "transfer",
    "unilateral_changes",
    "work_ownership",
]


def test_the_employment_pack_has_the_agreed_risk_categories():
    pack = next(p for p in load_packs() if p.id == "kenya_employment")

    assert [c.id for c in pack.risk_categories] == EMPLOYMENT_CATEGORIES


@pytest.mark.parametrize("category", EMPLOYMENT_CATEGORIES)
def test_employment_flags_use_employment_categories_and_labels(category):
    flag = {
        "flags": [
            {"category": category, "severity": "high", "explanation": "x", "question_to_ask": "y"}
        ]
    }
    # every clause gets the same reply; only the first is asserted on
    client = make_client(routes={"": json.dumps(flag)})
    sid = client.post("/api/sample", params={"pack": "kenya_employment"}).json()["session_id"]

    flags = [d for n, d in read_events(client, sid) if n == "risk_flag"]

    pack = next(p for p in load_packs() if p.id == "kenya_employment")
    label = next(c.label for c in pack.risk_categories if c.id == category)
    assert flags and flags[0]["category"] == category and flags[0]["category_label"] == label


def test_a_general_category_is_not_accepted_under_the_employment_pack():
    flag = {
        "flags": [
            {
                "category": "automatic_renewal",
                "severity": "high",
                "explanation": "x",
                "question_to_ask": "y",
            }
        ]
    }
    client = make_client(routes={"": json.dumps(flag)})
    sid = client.post("/api/sample", params={"pack": "kenya_employment"}).json()["session_id"]

    assert "risk_flag" not in [n for n, _ in read_events(client, sid)]
