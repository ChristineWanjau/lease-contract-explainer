"""Seam 1: legal rules and missing items (#17).

The bundled employment rules are placeholders until their figures and sections
are filled in from the Employment Act, so these tests use a test pack whose
rules are fictional ("TEST" in every requirement) and active.
"""

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from lce.app import create_app
from lce.packs import PLACEHOLDER, InvalidPack, load_packs

EMPLOYMENT_SUMMARY = {
    "employer_and_employee": ["Example Traders Ltd", "Jane Example"],
    "job_title": "Accounts Assistant",
    "start_date_and_term": "1 February 2027",
    "probation": "Twelve months",
    "salary": "KES 60,000 per month",
    "working_hours": "8am to 5pm",
    "leave": ["14 days annual leave"],
    "notice_period": "7 days",
    "your_obligations": ["Confidentiality"],
}

TEST_ACT = "Test Employment Act (fictional)"
TEST_LINK = "https://example.org/test-act"

LEAVE_RULE = {
    "id": "test_annual_leave",
    "topic": "Annual leave",
    "check": "contradiction",
    "severity": "high",
    "act": TEST_ACT,
    "section": "s. 1",
    "requirement": "TEST: annual leave must be at least 30 working days a year.",
    "question": "TEST: Can the leave be raised to the legal minimum?",
    "link": TEST_LINK,
    "status": "active",
}
SICK_RULE = {
    "id": "test_sick_leave",
    "topic": "Sick leave",
    "check": "missing",
    "severity": "medium",
    "act": TEST_ACT,
    "section": "s. 2",
    "requirement": "TEST: the contract must state the employee's sick leave.",
    "question": "TEST: How much paid sick leave do I get?",
    "link": TEST_LINK,
    "status": "active",
}
PARENTAL_RULE = dict(
    SICK_RULE,
    id="test_parental_leave",
    topic="Parental leave",
    section="s. 3",
    requirement="TEST: the contract must state maternity and paternity leave.",
    question="TEST: What parental leave do I get?",
)
PLACEHOLDER_RULE = dict(
    LEAVE_RULE,
    id="test_placeholder",
    topic="Notice",
    section=PLACEHOLDER,
    requirement=PLACEHOLDER,
    status="placeholder",
)


def employment_pack_with(rules: list[dict]) -> dict:
    base = next(p for p in load_packs() if p.id == "kenya_employment").model_dump(mode="json")
    return dict(base, id="test_employment", legal_rules=rules)


def general_pack() -> dict:
    return next(p for p in load_packs() if p.id == "general").model_dump(mode="json")


class RuleFake(FakeListChatModel):
    """Routes by prompt: summary, detection, missing-item check, or per-clause review."""

    clause_replies: dict[str, str]
    missing_replies: list[str]
    prompts: list[str]

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        system, prompt = str(messages[0].content), str(messages[-1].content)
        self.prompts.append(system + "\n----\n" + prompt)
        if prompt.startswith("Contract:"):
            return json.dumps(EMPLOYMENT_SUMMARY)
        if "Which type of contract" in system:
            return json.dumps({"pack": "test_employment", "confidence": 0.99})
        if "says nothing about" in system:
            if len(self.missing_replies) > 1:
                return self.missing_replies.pop(0)
            return self.missing_replies[0]
        for needle, reply in self.clause_replies.items():
            if needle in prompt:
                return reply
        return json.dumps({"flags": [], "rules": []})


def make(
    rules: list[dict],
    clause_replies: dict[str, str] | None = None,
    missing_replies: list[str] | None = None,
) -> tuple[TestClient, RuleFake]:
    llm = RuleFake(
        responses=["unused"],
        clause_replies=clause_replies or {},
        missing_replies=missing_replies or [json.dumps({"missing": []})],
        prompts=[],
    )
    packs = [general_pack(), employment_pack_with(rules)]
    app = create_app(llm=llm, embeddings=DeterministicFakeEmbedding(size=16), packs=packs)
    return TestClient(app), llm


def read_events(client: TestClient, session_id: str) -> list[tuple[str, dict]]:
    with client.stream("GET", f"/api/sessions/{session_id}/analyze") as response:
        raw = "".join(response.iter_text())
    out = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def load(client: TestClient) -> str:
    return client.post("/api/sample", params={"pack": "test_employment"}).json()["session_id"]


LEAVE_CLAUSE = "14 working days"  # text of clause 5 in the employment sample


def test_a_clause_that_contradicts_a_rule_is_flagged_with_the_act_from_config():
    # The model also returns made-up legal details; none of them may be used.
    reply = json.dumps(
        {
            "flags": [],
            "rules": ["test_annual_leave"],
            "act": "Invented Act",
            "section": "s. 999",
        }
    )
    client, _ = make([LEAVE_RULE], clause_replies={LEAVE_CLAUSE: reply})

    flags = [d for n, d in read_events(client, load(client)) if n == "risk_flag"]

    [flag] = flags
    assert flag["kind"] == "legal_rule"
    assert flag["category"] == "test_annual_leave"
    assert flag["category_label"] == "Annual leave"
    assert flag["severity"] == "high"
    assert flag["explanation"] == LEAVE_RULE["requirement"]
    assert flag["question_to_ask"] == LEAVE_RULE["question"]
    assert flag["legal"] == {
        "act": TEST_ACT,
        "section": "s. 1",
        "link": TEST_LINK,
        "verified": False,
        "last_reviewed": None,
    }
    [citation] = flag["citations"]
    assert citation["clause"] == "5"
    assert LEAVE_CLAUSE in citation["quote"]


def test_contract_risk_flags_are_marked_as_contract_risks_without_legal_details():
    reply = json.dumps(
        {
            "flags": [
                {
                    "category": "overtime",
                    "severity": "medium",
                    "explanation": "x",
                    "question_to_ask": "y",
                }
            ],
            "rules": [],
        }
    )
    client, _ = make([LEAVE_RULE], clause_replies={"additional hours": reply})

    [flag] = [d for n, d in read_events(client, load(client)) if n == "risk_flag"]

    assert flag["kind"] == "contract_risk"
    assert flag["legal"] is None


def test_unknown_and_missing_type_rule_ids_from_the_clause_review_are_ignored():
    reply = json.dumps({"flags": [], "rules": ["made_up", "test_sick_leave"]})
    client, _ = make([LEAVE_RULE, SICK_RULE], clause_replies={LEAVE_CLAUSE: reply})

    names = [n for n, _ in read_events(client, load(client))]

    assert "risk_flag" not in names


def test_placeholder_rules_are_never_sent_to_the_model_or_reported():
    reply = json.dumps({"flags": [], "rules": ["test_placeholder"]})
    client, llm = make(
        [LEAVE_RULE, PLACEHOLDER_RULE],
        clause_replies={LEAVE_CLAUSE: reply},
        missing_replies=[json.dumps({"missing": ["test_placeholder"]})],
    )

    events = read_events(client, load(client))

    assert all(PLACEHOLDER not in p and "test_placeholder" not in p for p in llm.prompts)
    assert [d["category"] for n, d in events if n == "risk_flag"] == []
    assert "missing_item" not in [n for n, _ in events]


def test_missing_items_stream_after_risk_flags_and_before_done_with_an_act_citation():
    leave = json.dumps({"flags": [], "rules": ["test_annual_leave"]})
    client, _ = make(
        [LEAVE_RULE, SICK_RULE, PARENTAL_RULE],
        clause_replies={LEAVE_CLAUSE: leave},
        missing_replies=[json.dumps({"missing": ["test_sick_leave", "made_up"]})],
    )

    events = read_events(client, load(client))

    names = [n for n, _ in events]
    assert names[0] == "summary"
    assert names[-1] == "done"
    first_missing = names.index("missing_item")
    assert all(n == "missing_item" for n in names[first_missing:-1])
    assert max(i for i, n in enumerate(names) if n == "risk_flag") < first_missing
    [item] = [d for n, d in events if n == "missing_item"]
    assert item == {
        "rule": "test_sick_leave",
        "topic": "Sick leave",
        "severity": "medium",
        "requirement": SICK_RULE["requirement"],
        "question_to_ask": SICK_RULE["question"],
        "legal": {
            "act": TEST_ACT,
            "section": "s. 2",
            "link": TEST_LINK,
            "verified": False,
            "last_reviewed": None,
        },
    }
    assert "citations" not in item


def test_the_missing_item_check_offers_only_active_missing_rules():
    client, llm = make([LEAVE_RULE, SICK_RULE, PARENTAL_RULE, PLACEHOLDER_RULE])

    read_events(client, load(client))

    [prompt] = [p for p in llm.prompts if "says nothing about" in p]
    assert "test_sick_leave" in prompt and "test_parental_leave" in prompt
    assert "test_annual_leave" not in prompt.split("----")[0]


def test_an_invalid_missing_item_check_is_retried_once_then_reported_as_skipped():
    client, llm = make(
        [SICK_RULE, PARENTAL_RULE], missing_replies=["not json", "still not json"]
    )

    events = read_events(client, load(client))

    assert len([p for p in llm.prompts if "says nothing about" in p]) == 2
    assert "missing_item" not in [n for n, _ in events]
    assert events[-1] == (
        "done",
        {"skipped_clauses": [], "skipped_rules": ["test_sick_leave", "test_parental_leave"]},
    )


def test_a_pack_without_active_rules_makes_no_rule_calls_and_reports_as_before():
    client, llm = make([PLACEHOLDER_RULE])

    events = read_events(client, load(client))

    assert not any("says nothing about" in p for p in llm.prompts)
    assert not any("legal requirements" in p for p in llm.prompts)
    assert events[-1] == ("done", {"skipped_clauses": [], "skipped_rules": []})


def _long_contract_pdf(clauses: int = 10, words: int = 420) -> bytes:
    """A text PDF long enough to exceed the whole-contract missing-item check."""
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    filler = ("The employee shall perform the duties of the role diligently. " * 20).split()
    for n in range(1, clauses + 1):
        y = 800
        pdf.drawString(50, y, f"{n}. Duties Part {n}")
        line: list[str] = []
        for i in range(words):
            line.append(filler[i % len(filler)])
            if len(line) == 12:
                y -= 14
                pdf.drawString(50, y, " ".join(line))
                line = []
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def test_a_long_contract_checks_each_missing_rule_against_retrieved_clauses():
    client, llm = make([SICK_RULE, PARENTAL_RULE])
    upload = client.post(
        "/api/upload", files={"file": ("long.pdf", _long_contract_pdf(), "application/pdf")}
    )
    assert upload.status_code == 200
    sid = upload.json()["session_id"]

    events = read_events(client, sid)

    missing_prompts = [p for p in llm.prompts if "says nothing about" in p]
    assert len(missing_prompts) == 2  # one per rule
    assert all("Relevant excerpts:" in p for p in missing_prompts)
    assert not any("Full contract:" in p for p in missing_prompts)
    assert events[-1][0] == "done"


@pytest.mark.parametrize(
    "rule",
    [
        dict(LEAVE_RULE, requirement=f"Leave must be {PLACEHOLDER}."),
        dict(LEAVE_RULE, section=PLACEHOLDER),
        dict(LEAVE_RULE, link="http://example.org/not-https"),
        dict(LEAVE_RULE, verified=True),  # verified without a review date
        dict(PLACEHOLDER_RULE, verified=True, last_reviewed="2026-11-19"),
        dict(LEAVE_RULE, id="overtime"),  # clashes with a risk category id
    ],
    ids=[
        "active-with-placeholder-requirement",
        "active-with-placeholder-section",
        "non-https-link",
        "verified-without-review-date",
        "verified-placeholder",
        "id-clash-with-category",
    ],
)
def test_an_invalid_rule_is_rejected_when_the_app_is_built(rule):
    with pytest.raises(InvalidPack):
        load_packs([general_pack(), employment_pack_with([rule])])


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(InvalidPack):
        load_packs([general_pack(), employment_pack_with([LEAVE_RULE, LEAVE_RULE])])


def test_the_bundled_employment_rules_cover_the_agreed_topics_and_are_all_placeholders():
    pack = next(p for p in load_packs() if p.id == "kenya_employment")

    assert [r.id for r in pack.legal_rules] == [
        "annual_leave",
        "sick_leave",
        "maternity_paternity_leave",
        "termination_notice",
        "probation_length",
        "written_particulars",
    ]
    assert all(r.status == "placeholder" and not r.verified for r in pack.legal_rules)
    assert all(r.act == "Employment Act, 2007" for r in pack.legal_rules)
