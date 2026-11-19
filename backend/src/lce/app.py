"""Backend app factory.

The chat model and embeddings are injected (primary test seam): production
passes Ollama models, tests pass LangChain fakes. Nothing in here constructs a
model itself.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from importlib.resources import files

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from lce.analysis import DISCLAIMER, AnalysisError, summarize
from lce.pdf import MAX_BYTES, UploadRejected, extract_pages
from lce.splitter import Chunk, split_clauses

logger = logging.getLogger(__name__)


class ChunkOut(BaseModel):
    text: str
    clause: str | None
    page: int


class SessionOut(BaseModel):
    session_id: str
    chunks: list[ChunkOut]


@dataclass
class Session:
    id: str
    chunks: list[Chunk] = field(default_factory=list)


def _load_sample_pdf() -> bytes:
    return files("lce").joinpath("data/sample_lease.pdf").read_bytes()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(
    llm: BaseChatModel,
    embeddings: Embeddings,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Lease & Contract Explainer")
    app.state.llm = llm
    app.state.embeddings = embeddings
    sessions: dict[str, Session] = {}  # in memory only, by design

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def to_out(session: Session) -> SessionOut:
        return SessionOut(
            session_id=session.id,
            chunks=[ChunkOut(text=c.text, clause=c.clause, page=c.page) for c in session.chunks],
        )

    def new_session(pdf_bytes: bytes) -> SessionOut:
        session = Session(id=uuid.uuid4().hex, chunks=split_clauses(extract_pages(pdf_bytes)))
        sessions[session.id] = session
        return to_out(session)

    @app.post("/api/sample", response_model=SessionOut)
    def load_sample() -> SessionOut:
        return new_session(_load_sample_pdf())

    @app.post("/api/upload", response_model=SessionOut)
    async def upload(file: UploadFile) -> SessionOut:
        # Read one byte past the limit so oversized files are detected without reading them fully.
        data = await file.read(MAX_BYTES + 1)
        try:
            return new_session(data)
        except UploadRejected as e:
            raise HTTPException(
                status_code=e.status, detail={"code": e.code, "message": e.message}
            ) from None

    @app.get("/api/sessions/{session_id}", response_model=SessionOut)
    def get_session(session_id: str) -> SessionOut:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return to_out(session)

    @app.get("/api/sessions/{session_id}/analyze")
    def analyze(session_id: str) -> StreamingResponse:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        def events() -> Iterator[str]:
            try:
                summary = summarize(llm, session.chunks)
            except AnalysisError as e:
                yield _sse("error", {"message": str(e)})
                return
            except Exception:
                logger.exception("analysis failed")
                yield _sse(
                    "error",
                    {"message": "The local model couldn't be reached. Is Ollama running?"},
                )
                return
            yield _sse("summary", {"summary": summary.model_dump(), "disclaimer": DISCLAIMER})
            yield _sse("done", {})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
