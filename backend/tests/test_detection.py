"""Seam 1: automatic contract type detection (#18)."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lce.app import create_app
from lce.detect import CONFIDENCE_THRESHOLD
from lce.packs import load_packs


class DetectFake(FakeListChatModel):
    """Replies to the detection prompt with `detect` (in order); counts detection calls."""

    detect: list[str]
    calls: list[str]

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        system = str(messages[0].content)
        if "Which type of contract" in system:
            self.calls.append(system)
            return self.detect.pop(0) if len(self.detect) > 1 else self.detect[0]
        return json.dumps({"flags": []})


def make(*detect_replies: str, packs=None) -> tuple[TestClient, DetectFake]:
    llm = DetectFake(responses=["unused"], detect=list(detect_replies), calls=[])
    app = create_app(llm=llm, embeddings=DeterministicFakeEmbedding(size=16), packs=packs)
    return TestClient(app), llm


def reply(pack: str, confidence: float) -> str:
    return json.dumps({"pack": pack, "confidence": confidence})


def employment_pdf() -> bytes:
    return next(p for p in load_packs() if p.id == "kenya_employment").sample_bytes()


def upload(client: TestClient, data: bytes):
    return client.post("/api/upload", files={"file": ("c.pdf", data, "application/pdf")})


def test_a_confident_detection_sets_the_sessions_pack():
    client, _ = make(reply("kenya_employment", 0.9))

    body = upload(client, employment_pdf()).json()

    assert body["pack"] == "kenya_employment"
    assert body["detected"] == {"pack": "kenya_employment", "confidence": 0.9}
    assert client.get(f"/api/sessions/{body['session_id']}").json()["pack"] == "kenya_employment"


def test_low_confidence_falls_back_to_general():
    client, _ = make(reply("kenya_employment", CONFIDENCE_THRESHOLD - 0.01))

    body = upload(client, employment_pdf()).json()

    assert body["pack"] == "general"
    assert body["detected"]["pack"] == "general"


def test_confidence_exactly_at_the_threshold_is_accepted():
    client, _ = make(reply("kenya_employment", CONFIDENCE_THRESHOLD))

    assert upload(client, employment_pdf()).json()["pack"] == "kenya_employment"


def test_invalid_output_is_retried_once_then_used():
    client, llm = make("not json", reply("kenya_employment", 0.9))

    body = upload(client, employment_pdf()).json()

    assert body["pack"] == "kenya_employment"
    assert len(llm.calls) == 2


def test_invalid_output_twice_falls_back_to_general():
    client, llm = make("garbage", "still garbage", reply("kenya_employment", 0.9))

    body = upload(client, employment_pdf()).json()

    assert body["pack"] == "general"
    assert len(llm.calls) == 2


def test_an_unknown_pack_in_the_reply_falls_back_to_general():
    client, _ = make(reply("mortgage", 0.99))

    assert upload(client, employment_pdf()).json()["pack"] == "general"


@pytest.mark.parametrize("confidence", [-0.1, 1.5, "high"])
def test_an_out_of_range_confidence_counts_as_invalid(confidence):
    bad = json.dumps({"pack": "kenya_employment", "confidence": confidence})
    client, llm = make(bad, bad)

    assert upload(client, employment_pdf()).json()["pack"] == "general"
    assert len(llm.calls) == 2


def test_the_detection_prompt_offers_every_configured_pack():
    client, llm = make(reply("general", 0.9))

    upload(client, employment_pdf())

    for pack in load_packs():
        assert pack.id in llm.calls[0]
        assert pack.description in llm.calls[0]


def test_a_model_failure_during_detection_falls_back_to_general():
    class Broken(FakeListChatModel):
        def _call(self, *a, **k):
            raise ConnectionError("ollama down")

    app = create_app(llm=Broken(responses=["x"]), embeddings=DeterministicFakeEmbedding(size=16))
    client = TestClient(app)

    body = upload(client, employment_pdf())

    assert body.status_code == 200
    assert body.json()["pack"] == "general"


def test_with_only_one_pack_no_detection_call_is_made():
    general = next(p for p in load_packs() if p.id == "general").model_dump()
    client, llm = make(reply("general", 0.9), packs=[general])

    body = upload(client, employment_pdf()).json()

    assert body["pack"] == "general"
    assert body["detected"] is None
    assert llm.calls == []


@pytest.mark.parametrize("params", [{}, {"pack": "kenya_employment"}], ids=["default", "chosen"])
def test_loading_a_sample_skips_detection_because_its_type_is_known(params):
    client, llm = make(reply("kenya_employment", 0.99))

    body = client.post("/api/sample", params=params).json()

    assert body["pack"] == params.get("pack", "general")
    assert body["detected"] is None
    assert llm.calls == []


def test_changing_the_pack_after_detection_still_works():
    client, _ = make(reply("kenya_employment", 0.9))
    sid = upload(client, employment_pdf()).json()["session_id"]

    body = client.put(f"/api/sessions/{sid}/pack", json={"pack": "general"}).json()

    assert body["pack"] == "general"
