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

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, field_validator

from lce.analysis import (
    DISCLAIMER,
    AnalysisError,
    RiskScanResult,
    find_risks,
    summarize,
)
from lce.chat import (
    ContractIndex,
    StreamedAnswer,
    build_messages,
    remember,
    stream_answer,
)
from lce.packs import Pack, load_packs
from lce.pdf import MAX_BYTES, UploadRejected, extract_pages
from lce.splitter import Chunk, split_clauses

logger = logging.getLogger(__name__)


class ChunkOut(BaseModel):
    text: str
    clause: str | None
    page: int


class SessionOut(BaseModel):
    session_id: str
    pack: str
    chunks: list[ChunkOut]


class PackOut(BaseModel):
    id: str
    name: str
    sample_label: str


class PackIn(BaseModel):
    pack: str


@dataclass
class Session:
    id: str
    pack: Pack
    chunks: list[Chunk] = field(default_factory=list)
    index: ContractIndex | None = None  # built lazily on first question
    history: list[BaseMessage] = field(default_factory=list)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(
    llm: BaseChatModel,
    embeddings: Embeddings,
    allowed_origins: list[str] | None = None,
    packs: list[dict] | None = None,
) -> FastAPI:
    """Build the app. ``packs`` overrides the bundled packs (the first is the default)."""
    app = FastAPI(title="Lease & Contract Explainer")
    app.state.llm = llm
    app.state.embeddings = embeddings
    loaded_packs = load_packs(packs)  # raises InvalidPack, so a bad pack fails startup
    packs_by_id = {p.id: p for p in loaded_packs}
    default_pack = loaded_packs[0]
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
            pack=session.pack.id,
            chunks=[ChunkOut(text=c.text, clause=c.clause, page=c.page) for c in session.chunks],
        )

    def find_pack(pack_id: str) -> Pack:
        pack = packs_by_id.get(pack_id)
        if pack is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unknown_pack",
                    "message": f"Unknown contract type {pack_id!r}.",
                },
            )
        return pack

    def find_session(session_id: str) -> Session:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    def new_session(pdf_bytes: bytes, pack: Pack) -> SessionOut:
        session = Session(
            id=uuid.uuid4().hex,
            pack=pack,
            chunks=split_clauses(extract_pages(pdf_bytes)),
        )
        sessions[session.id] = session
        return to_out(session)

    @app.get("/api/packs", response_model=list[PackOut])
    def list_packs() -> list[PackOut]:
        return [PackOut(id=p.id, name=p.name, sample_label=p.sample_label) for p in loaded_packs]

    @app.post("/api/sample", response_model=SessionOut)
    def load_sample(pack: str | None = None) -> SessionOut:
        chosen = find_pack(pack) if pack is not None else default_pack
        return new_session(chosen.sample_bytes(), chosen)

    @app.post("/api/upload", response_model=SessionOut)
    async def upload(file: UploadFile) -> SessionOut:
        # Read one byte past the limit so oversized files are detected without reading them fully.
        data = await file.read(MAX_BYTES + 1)
        try:
            return new_session(data, default_pack)
        except UploadRejected as e:
            raise HTTPException(
                status_code=e.status, detail={"code": e.code, "message": e.message}
            ) from None

    @app.get("/api/sessions/{session_id}", response_model=SessionOut)
    def get_session(session_id: str) -> SessionOut:
        return to_out(find_session(session_id))

    @app.put("/api/sessions/{session_id}/pack", response_model=SessionOut)
    def set_pack(session_id: str, body: PackIn) -> SessionOut:
        session = find_session(session_id)
        session.pack = find_pack(body.pack)
        return to_out(session)

    @app.get("/api/sessions/{session_id}/analyze")
    def analyze(session_id: str) -> StreamingResponse:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        def events() -> Iterator[str]:
            pack = session.pack
            try:
                summary = summarize(llm, session.chunks, pack)
                yield _sse(
                    "summary",
                    {
                        "summary": summary,
                        "fields": [
                            {"name": f.name, "label": f.label, "kind": f.kind}
                            for f in pack.summary_fields
                        ],
                        "disclaimer": DISCLAIMER,
                    },
                )
                scan = RiskScanResult()
                for flag in find_risks(llm, session.chunks, pack.risk_categories, scan):
                    yield _sse("risk_flag", flag.model_dump())
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
            yield _sse("done", {"skipped_clauses": scan.skipped_clauses})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/sessions/{session_id}/chat")
    def chat(session_id: str, body: ChatIn) -> StreamingResponse:
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        def events() -> Iterator[str]:
            try:
                if session.index is None:
                    session.index = ContractIndex(session.chunks, embeddings)
                retrieved = session.index.search(body.question)
                messages = build_messages(body.question, retrieved, session.history)
                result = StreamedAnswer()
                for token in stream_answer(llm, messages, retrieved, result):
                    yield _sse("token", {"text": token})
            except Exception:
                logger.exception("chat failed")
                yield _sse(
                    "error",
                    {"message": "The local model couldn't be reached. Is Ollama running?"},
                )
                return
            remember(session.history, body.question, result.text)
            yield _sse(
                "answer",
                {
                    "text": result.text,
                    "supported": result.supported,
                    "citations": [c.model_dump() for c in result.citations],
                },
            )
            yield _sse("done", {})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
