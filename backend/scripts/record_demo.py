"""Record the hosted demo from the real backend running on local Ollama.

For each bundled pack's sample this saves, as the frontend will see them:
the session (POST /api/sample?pack=...), every analysis event, and the chat
events for the pack's example questions plus one the contract doesn't cover.
Output: frontend/src/demo/recordings.json (consumed by the demo build).

Run: make record-demo  (needs Ollama running with the configured models)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from lce.main import CHAT_MODEL, app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "demo" / "recordings.json"

# A question none of the samples answers, so the demo shows the refusal path.
UNANSWERED = "Am I allowed to keep a pet?"


def sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append({"event": fields["event"], "data": json.loads(fields["data"])})
    return events


def main() -> None:
    client = TestClient(app)
    packs = client.get("/api/packs").json()
    recorded = {"model": CHAT_MODEL, "recorded_at": time.strftime("%Y-%m-%d"), "packs": packs,
                "samples": {}}
    for pack in packs:
        start = time.time()
        session = client.post("/api/sample", params={"pack": pack["id"]}).json()
        sid = session["session_id"]
        with client.stream("GET", f"/api/sessions/{sid}/analyze") as r:
            analysis = sse("".join(r.iter_text()))
        chat = {}
        for q in [*pack["example_questions"], UNANSWERED]:
            with client.stream("POST", f"/api/sessions/{sid}/chat", json={"question": q}) as r:
                chat[q] = sse("".join(r.iter_text()))
        names = [e["event"] for e in analysis]
        if "error" in names or any(e["event"] == "error" for v in chat.values() for e in v):
            raise SystemExit(f"{pack['id']}: the model returned an error; is Ollama running?")
        recorded["samples"][pack["id"]] = {
            "session": {**session, "session_id": f"demo-{pack['id']}"},
            "analysis": analysis,
            "chat": chat,
        }
        print(f"{pack['id']}: {names.count('risk_flag')} flags, "
              f"{names.count('missing_item')} missing, {len(chat)} answers, "
              f"{time.time() - start:.0f}s")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(recorded, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
