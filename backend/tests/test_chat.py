"""Seam 1: Q&A chat with citations and memory (#6)."""

import json

from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app


class RecordingFake(FakeListChatModel):
    """Returns canned replies in order and records every prompt it was sent."""

    seen: list

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        return super()._call(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        # FakeListChatModel._stream calls _call itself; avoid recording twice.
        seen, self.seen = self.seen, []
        try:
            yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        finally:
            self.seen = seen


def make(*replies: str) -> tuple[TestClient, RecordingFake]:
    llm = RecordingFake(responses=list(replies), seen=[])
    app = create_app(llm=llm, embeddings=DeterministicFakeEmbedding(size=32))
    return TestClient(app), llm


def ask(client: TestClient, session_id: str, question: str) -> list[tuple[str, dict]]:
    with client.stream(
        "POST", f"/api/sessions/{session_id}/chat", json={"question": question}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())
    events = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_answer_streams_as_tokens_then_a_final_answer_event_then_done():
    client, _ = make("The deposit is three months rent [1].")
    sid = client.post("/api/sample").json()["session_id"]

    events = ask(client, sid, "How big is the deposit?")

    names = [n for n, _ in events]
    assert names.count("token") > 1
    assert names[-2:] == ["answer", "done"]
    streamed = "".join(d["text"] for n, d in events if n == "token")
    assert streamed == "The deposit is three months rent [1]."


def test_citations_are_the_excerpts_the_answer_refers_to_quoted_verbatim():
    # Fake embeddings don't rank by meaning, so read which clause was given as [2]
    # from the prompt itself and check the citation matches that clause.
    client, llm = make("It is three months rent [2].")
    sid = client.post("/api/sample").json()["session_id"]
    chunks = client.get(f"/api/sessions/{sid}").json()["chunks"]

    answer = dict(ask(client, sid, "How big is the deposit?"))["answer"]

    prompt = str(llm.seen[0][0].content)
    second_excerpt = prompt.split("\n[2] (", 1)[1].split("\n", 1)[0]  # e.g. "Clause 3, p. 1)"
    assert answer["supported"] is True
    [cite] = answer["citations"]
    expected = f"{'Clause ' + cite['clause'] if cite['clause'] else 'Preamble'}, p. {cite['page']})"
    assert second_excerpt == expected
    assert cite["quote"] in {c["text"] for c in chunks}


def test_an_answer_that_cites_nothing_is_replaced_with_contract_doesnt_say():
    client, _ = make("Probably your landlord allows pets.")
    sid = client.post("/api/sample").json()["session_id"]

    answer = dict(ask(client, sid, "Can I keep a cat?"))["answer"]

    assert answer["supported"] is False
    assert answer["citations"] == []
    assert "contract doesn't say" in answer["text"].lower()


def test_references_to_excerpts_that_were_not_retrieved_are_ignored():
    client, _ = make("See [99].")
    sid = client.post("/api/sample").json()["session_id"]

    answer = dict(ask(client, sid, "anything"))["answer"]

    assert answer["supported"] is False
    assert answer["citations"] == []


def test_follow_up_questions_include_the_earlier_conversation():
    client, llm = make("Rent is 1,200 per month [1].", "It can rise with 14 days notice [1].")
    sid = client.post("/api/sample").json()["session_id"]

    ask(client, sid, "How much is the rent?")
    ask(client, sid, "And can it go up?")

    second_prompt = "\n".join(str(m.content) for m in llm.seen[1])
    assert "How much is the rent?" in second_prompt
    assert "Rent is 1,200 per month" in second_prompt


def test_each_session_has_its_own_history():
    client, llm = make("A [1].", "B [1].")
    first = client.post("/api/sample").json()["session_id"]
    second = client.post("/api/sample").json()["session_id"]

    ask(client, first, "secret question one")
    ask(client, second, "question two")

    assert "secret question one" not in "\n".join(str(m.content) for m in llm.seen[1])


def test_empty_question_is_rejected():
    client, _ = make("unused")
    sid = client.post("/api/sample").json()["session_id"]

    response = client.post(f"/api/sessions/{sid}/chat", json={"question": "   "})

    assert response.status_code == 422


def test_chat_on_unknown_session_is_a_404():
    client, _ = make("unused")

    response = client.post("/api/sessions/nope/chat", json={"question": "hi"})

    assert response.status_code == 404


def test_a_model_failure_yields_an_error_event():
    class Broken(FakeListChatModel):
        def _call(self, *a, **k):
            raise ConnectionError("down")

        def _stream(self, *a, **k):
            raise ConnectionError("down")

    app = create_app(llm=Broken(responses=["x"]), embeddings=DeterministicFakeEmbedding(size=32))
    client = TestClient(app)
    sid = client.post("/api/sample").json()["session_id"]

    events = ask(client, sid, "hi")

    assert [n for n, _ in events] == ["error"]


def test_answer_references_are_renumbered_to_match_the_citation_list():
    client, _ = make("Deposit [3]. Forfeit [2]. Again [3]. Bogus [9].")
    sid = client.post("/api/sample").json()["session_id"]

    answer = dict(ask(client, sid, "deposit?"))["answer"]

    assert answer["text"] == "Deposit [1]. Forfeit [2]. Again [1]. Bogus."
    assert len(answer["citations"]) == 2
