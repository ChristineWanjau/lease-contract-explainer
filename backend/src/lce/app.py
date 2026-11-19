"""Backend app factory.

The chat model and embeddings are injected (primary test seam): production
passes Ollama models, tests pass LangChain fakes. Nothing in here constructs a
model itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from importlib.resources import files

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from lce.pdf import extract_pages
from lce.splitter import Chunk, split_clauses


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

    @app.post("/api/sample", response_model=SessionOut)
    def load_sample() -> SessionOut:
        session = Session(id=uuid.uuid4().hex, chunks=split_clauses(extract_pages(_load_sample_pdf())))
        sessions[session.id] = session
        return to_out(session)

    @app.get("/api/sessions/{session_id}", response_model=SessionOut)
    def get_session(session_id: str) -> SessionOut:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return to_out(session)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
