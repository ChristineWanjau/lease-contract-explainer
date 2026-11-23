"""The hosted demo's recordings must stay in step with the backend.

If a change alters the packs, the samples or the shape of an event, these
fail; re-record with `make record-demo`.
"""

import json
from pathlib import Path

import pytest

from lce.analysis import MissingItem, RiskFlag
from lce.packs import load_packs
from lce.pdf import extract_pages
from lce.splitter import split_clauses

RECORDINGS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "demo" / "recordings.json"
DATA = json.loads(RECORDINGS.read_text())
PACKS = load_packs()

ANALYSIS_EVENTS = {"summary", "risk_flag", "missing_item", "done"}
CHAT_EVENTS = {"token", "answer", "done"}


def test_every_bundled_pack_is_recorded_with_its_current_details():
    assert [p["id"] for p in DATA["packs"]] == [p.id for p in PACKS]
    for recorded, pack in zip(DATA["packs"], PACKS, strict=True):
        assert recorded == {
            "id": pack.id,
            "name": pack.name,
            "sample_label": pack.sample_label,
            "example_questions": pack.example_questions,
        }
    assert set(DATA["samples"]) == {p.id for p in PACKS}


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.id)
def test_the_recorded_session_matches_the_current_sample(pack):
    session = DATA["samples"][pack.id]["session"]
    chunks = split_clauses(extract_pages(pack.sample_bytes()))

    assert session["session_id"] == f"demo-{pack.id}"
    assert session["pack"] == pack.id
    assert [(c["text"], c["clause"], c["page"]) for c in session["chunks"]] == [
        (c.text, c.clause, c.page) for c in chunks
    ]


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.id)
def test_the_recorded_analysis_has_the_current_event_shapes(pack):
    events = DATA["samples"][pack.id]["analysis"]
    names = [e["event"] for e in events]

    assert set(names) <= ANALYSIS_EVENTS
    assert names[0] == "summary" and names[-1] == "done"
    summary = events[0]["data"]
    assert [f["name"] for f in summary["fields"]] == [f.name for f in pack.summary_fields]
    assert set(summary["summary"]) == {f.name for f in pack.summary_fields}
    assert "not legal advice" in summary["disclaimer"].lower()
    quotes = {c["text"] for c in DATA["samples"][pack.id]["session"]["chunks"]}
    for e in events:
        if e["event"] == "risk_flag":
            flag = RiskFlag.model_validate(e["data"])
            assert all(c.quote in quotes for c in flag.citations)
        elif e["event"] == "missing_item":
            MissingItem.model_validate(e["data"])
    assert set(events[-1]["data"]) == {"skipped_clauses", "skipped_rules"}


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.id)
def test_each_example_question_and_one_unanswered_question_is_recorded(pack):
    chat = DATA["samples"][pack.id]["chat"]
    quotes = {c["text"] for c in DATA["samples"][pack.id]["session"]["chunks"]}

    assert set(pack.example_questions) < set(chat)
    unsupported = 0
    for events in chat.values():
        names = [e["event"] for e in events]
        assert set(names) <= CHAT_EVENTS and names[-2:] == ["answer", "done"]
        answer = events[-2]["data"]
        assert all(c["quote"] in quotes for c in answer["citations"])
        unsupported += not answer["supported"]
    assert unsupported >= 1
