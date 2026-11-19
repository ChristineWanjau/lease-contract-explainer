"""Contract analysis: structured summary (and later, risk flags).

Structured output is done with a prompt + Pydantic validation rather than
``with_structured_output`` so the exact same code path runs against Ollama in
production and against LangChain's fake chat models in tests.
"""

from __future__ import annotations

import json
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from lce.splitter import Chunk

DISCLAIMER = (
    "This is an automated explanation, not legal advice. It may be incomplete or wrong. "
    "For important decisions, consult a qualified lawyer."
)

MAX_ATTEMPTS = 2  # first try + one retry


class Summary(BaseModel):
    parties: list[str] = Field(description="Who is bound by the contract, with their role")
    key_dates: list[str] = Field(description="Start, end, renewal and notice deadlines")
    payments: list[str] = Field(description="Rent, salary, fees, deposits and amounts")
    duration: str = Field(description="How long the contract lasts")
    obligations: list[str] = Field(description="Main things the signer must do")


class AnalysisError(Exception):
    """The model could not produce valid output."""


_SUMMARY_SYSTEM = """You explain contracts in plain language to the person about to sign.
Use only what the contract says. If something is not stated, write "Not stated".
Reply with a single JSON object and nothing else, matching this JSON schema:
{schema}"""

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _contract_text(chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        label = f"Clause {c.clause}" if c.clause else "Preamble"
        parts.append(f"[{label}, p. {c.page}]\n{c.text}")
    return "\n\n".join(parts)


def _parse_json(text: str) -> dict:
    text = _THINK.sub("", text).strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def summarize(llm: BaseChatModel, chunks: list[Chunk]) -> Summary:
    """Ask the model for a summary, validating against the schema with one retry."""
    messages = [
        SystemMessage(_SUMMARY_SYSTEM.format(schema=json.dumps(Summary.model_json_schema()))),
        HumanMessage(f"Contract:\n\n{_contract_text(chunks)}"),
    ]
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        reply = llm.invoke(messages)
        try:
            return Summary.model_validate(_parse_json(str(reply.content)))
        except (ValueError, ValidationError) as e:
            last_error = e
    raise AnalysisError("The model returned an invalid summary twice.") from last_error
