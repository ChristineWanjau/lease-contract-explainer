"""Retrieval-augmented Q&A over one contract, with clause citations.

Retrieved clauses are numbered [1]..[k] in the prompt. The model is asked to
cite those numbers; citations are then built from the referenced chunks, so the
quoted text always comes from the contract, never from the model. An answer
that cites no retrieved excerpt is treated as unsupported and replaced.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import InMemoryVectorStore

from lce.analysis import Citation
from lce.splitter import Chunk

TOP_K = 4
MAX_HISTORY_TURNS = 6  # question+answer pairs kept in the prompt

NOT_IN_CONTRACT = (
    "The contract doesn't say. I couldn't find anything in it that answers this question."
)

_SYSTEM = """You answer questions about one contract for the person about to sign it.
Answer ONLY from the numbered excerpts below. Use plain language and keep it short.
After each statement, cite the excerpt it comes from, like [1] or [2].
If the excerpts don't answer the question, reply exactly: "{not_found}"
Do not use outside knowledge and do not guess.

Excerpts:
{excerpts}"""

_REF = re.compile(r"(\s?)\[(\d+)\]")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class ContractIndex:
    """In-memory vector index of one contract's chunks."""

    def __init__(self, chunks: list[Chunk], embeddings: Embeddings) -> None:
        self._store = InMemoryVectorStore(embeddings)
        self._store.add_documents(
            [
                Document(page_content=c.text, metadata={"clause": c.clause, "page": c.page})
                for c in chunks
            ]
        )

    def search(self, question: str, k: int = TOP_K) -> list[Chunk]:
        docs = self._store.similarity_search(question, k=k)
        return [
            Chunk(text=d.page_content, clause=d.metadata["clause"], page=d.metadata["page"])
            for d in docs
        ]


def _excerpts(chunks: list[Chunk]) -> str:
    return "\n\n".join(
        f"[{i}] ({f'Clause {c.clause}' if c.clause else 'Preamble'}, p. {c.page})\n{c.text}"
        for i, c in enumerate(chunks, start=1)
    )


def build_messages(
    question: str, retrieved: list[Chunk], history: list[BaseMessage]
) -> list[BaseMessage]:
    system = SystemMessage(
        _SYSTEM.format(not_found=NOT_IN_CONTRACT, excerpts=_excerpts(retrieved))
    )
    return [system, *history[-2 * MAX_HISTORY_TURNS :], HumanMessage(question)]


def cited(answer: str, retrieved: list[Chunk]) -> tuple[str, list[Citation]]:
    """Resolve [n] references to citations, in first-mention order.

    Returns the answer renumbered so [1], [2]… match the returned citation list,
    with references to excerpts that weren't retrieved removed.
    """
    out: list[Citation] = []
    renumber: dict[int, int] = {}

    def sub(m: re.Match[str]) -> str:
        n = int(m.group(2))
        if not 1 <= n <= len(retrieved):
            return ""  # drop the reference and its leading space
        if n not in renumber:
            c = retrieved[n - 1]
            out.append(Citation(clause=c.clause, page=c.page, quote=c.text))
            renumber[n] = len(out)
        return f"{m.group(1)}[{renumber[n]}]"

    text = _REF.sub(sub, answer)
    return text.strip(), out


class StreamedAnswer:
    """Holds the final answer once the token stream is exhausted."""

    text: str = ""
    citations: list[Citation]
    supported: bool = False


def stream_answer(
    llm: BaseChatModel, messages: list[BaseMessage], retrieved: list[Chunk], result: StreamedAnswer
) -> Iterator[str]:
    """Yield answer tokens as they arrive, then fill ``result`` with the final answer."""
    raw = ""
    for piece in llm.stream(messages):
        token = str(piece.content)
        if token:
            raw += token
            yield token
    text = _THINK.sub("", raw).strip()
    text, result.citations = cited(text, retrieved)
    result.supported = bool(result.citations)
    result.text = text if result.supported else NOT_IN_CONTRACT


def remember(history: list[BaseMessage], question: str, answer: str) -> None:
    history.extend([HumanMessage(question), AIMessage(answer)])
