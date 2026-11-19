"""Seam 1: risk flags with citations (#5)."""

import json
from importlib.resources import files

from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app
from lce.pdf import extract_pages

VALID_SUMMARY = {
    "parties": ["Landlord", "Tenant"],
    "key_dates": ["1 January 2027"],
    "payments": ["1,200 per month"],
    "duration": "12 months",
    "obligations": ["Pay rent"],
}

NO_FLAGS = json.dumps({"flags": []})


def flags(*items: dict) -> str:
    return json.dumps({"flags": list(items)})


RENEWAL_FLAG = {
    "category": "automatic_renewal",
    "severity": "high",
    "explanation": "You are locked in for another year unless you act 90 days early.",
    "question_to_ask": "Can the notice period be shortened to 30 days?",
}
FORFEIT_FLAG = {
    "category": "deposit_forfeiture",
    "severity": "high",
    "explanation": "You lose the whole deposit if you leave early.",
    "question_to_ask": "Can forfeiture be limited to actual damages?",
}


class RoutingFake(FakeListChatModel):
    """Answers the summary prompt with a summary, and each clause prompt by matching its text."""

    routes: dict[str, list[str]]
    summary_replies: list[str]

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = str(messages[-1].content)
        if prompt.startswith("Contract:"):
            return self.summary_replies.pop(0) if len(self.summary_replies) > 1 else self.summary_replies[0]
        for needle, replies in self.routes.items():
            if needle in prompt:
                return replies.pop(0) if len(replies) > 1 else replies[0]
        return NO_FLAGS


def make_client(routes: dict[str, list[str]], categories: list[dict] | None = None) -> TestClient:
    llm = RoutingFake(responses=["unused"], routes=routes, summary_replies=[json.dumps(VALID_SUMMARY)])
    packs = None
    if categories is not None:  # the General pack, with its checklist swapped out
        general = json.loads(files("lce").joinpath("data/packs/general.json").read_text())
        packs = [dict(general, risk_categories=categories)]
    app = create_app(
        llm=llm,
        embeddings=DeterministicFakeEmbedding(size=16),
        packs=packs,
    )
    return TestClient(app)


def read_events(client: TestClient, session_id: str) -> list[tuple[str, dict]]:
    with client.stream("GET", f"/api/sessions/{session_id}/analyze") as response:
        raw = "".join(response.iter_text())
    out = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def sample_text() -> str:
    return "\n".join(extract_pages(files("lce").joinpath("data/sample_lease.pdf").read_bytes()))


def test_risk_flags_stream_after_the_summary_and_before_done():
    client = make_client({
        "automatically renew": [flags(RENEWAL_FLAG)],
        "forfeit the entire": [flags(FORFEIT_FLAG)],
    })
    sid = client.post("/api/sample").json()["session_id"]

    names = [name for name, _ in read_events(client, sid)]

    assert names[0] == "summary"
    assert names[-1] == "done"
    assert names.count("risk_flag") == 2
    assert set(names[1:-1]) == {"risk_flag"}


def test_each_flag_has_category_severity_explanation_question_and_citation():
    client = make_client({"automatically renew": [flags(RENEWAL_FLAG)]})
    sid = client.post("/api/sample").json()["session_id"]

    flag = next(d for n, d in read_events(client, sid) if n == "risk_flag")

    assert flag["category"] == "automatic_renewal"
    assert flag["category_label"] == "Automatic renewal"
    assert flag["severity"] == "high"
    assert flag["explanation"] and flag["question_to_ask"]
    [citation] = flag["citations"]
    assert citation["clause"] == "4"
    assert citation["page"] == 2


def test_every_citation_quote_appears_verbatim_in_the_contract():
    client = make_client({
        "automatically renew": [flags(RENEWAL_FLAG)],
        "forfeit the entire": [flags(FORFEIT_FLAG)],
    })
    sid = client.post("/api/sample").json()["session_id"]
    source = sample_text()

    citations = [c for n, d in read_events(client, sid) if n == "risk_flag" for c in d["citations"]]

    assert citations
    assert all(c["quote"] and c["quote"] in source for c in citations)


def test_a_model_cannot_invent_a_quote():
    invented = dict(RENEWAL_FLAG, quote="The landlord will pay you a million.")
    client = make_client({"automatically renew": [flags(invented)]})
    sid = client.post("/api/sample").json()["session_id"]

    flag = next(d for n, d in read_events(client, sid) if n == "risk_flag")

    assert "million" not in flag["citations"][0]["quote"]


def test_flags_with_an_unknown_category_are_dropped():
    bogus = dict(RENEWAL_FLAG, category="made_up_category")
    client = make_client({"automatically renew": [flags(bogus)]})
    sid = client.post("/api/sample").json()["session_id"]

    assert "risk_flag" not in [n for n, _ in read_events(client, sid)]


def test_categories_come_from_configuration():
    custom = [{"id": "governing_law", "label": "Governing law", "description": "Which law applies"}]
    law_flag = dict(RENEWAL_FLAG, category="governing_law", severity="low")
    client = make_client(
        {"governed by the laws": [flags(law_flag)], "automatically renew": [flags(RENEWAL_FLAG)]},
        categories=custom,
    )
    sid = client.post("/api/sample").json()["session_id"]

    found = [d["category"] for n, d in read_events(client, sid) if n == "risk_flag"]

    assert found == ["governing_law"]  # automatic_renewal isn't configured, so it's dropped


def test_a_clause_with_invalid_output_is_retried_once():
    client = make_client({"automatically renew": ["not json", flags(RENEWAL_FLAG)]})
    sid = client.post("/api/sample").json()["session_id"]

    assert [n for n, _ in read_events(client, sid)].count("risk_flag") == 1


def test_a_clause_that_fails_twice_is_skipped_without_stopping_the_analysis():
    client = make_client({
        "automatically renew": ["bad", "still bad", flags(RENEWAL_FLAG)],
        "forfeit the entire": [flags(FORFEIT_FLAG)],
    })
    sid = client.post("/api/sample").json()["session_id"]

    events = read_events(client, sid)

    assert [d["category"] for n, d in events if n == "risk_flag"] == ["deposit_forfeiture"]
    assert events[-1][0] == "done"
    assert events[-1][1]["skipped_clauses"] == ["4"]
