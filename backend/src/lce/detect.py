"""Automatic contract type detection.

The model is shown the start of the contract and the configured packs'
descriptions, and returns a pack id and a confidence. Anything doubtful
(low confidence, an unknown pack, invalid output twice, or a model error)
falls back to the default pack rather than guessing.
"""

from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from lce.analysis import MAX_ATTEMPTS, parse_json
from lce.packs import Pack
from lce.splitter import Chunk

logger = logging.getLogger(__name__)

# Chosen for a local 8B model: it reports high confidence (>= 0.9) on clear
# contracts, so 0.7 leaves room for messy real documents while still rejecting
# "maybe" answers. Below this, the default (General) pack is used.
CONFIDENCE_THRESHOLD = 0.7

# The type of a contract is almost always clear from its title and first clauses.
DETECTION_CHARS = 3000

_SYSTEM = """Which type of contract is this? Choose exactly one of these types:
{packs}

Choose "{default}" if none of the others clearly fits.
Give your confidence from 0 to 1 that the type you chose is correct.
Reply with a single JSON object and nothing else, matching this JSON schema:
{schema}"""


class _Detection(BaseModel):
    pack: str
    confidence: float = Field(ge=0, le=1)


class Detected(BaseModel):
    pack: str
    confidence: float


def detect_pack(
    llm: BaseChatModel, chunks: list[Chunk], packs: list[Pack]
) -> tuple[Pack, Detected]:
    """Return the pack to use and what was detected. ``packs[0]`` is the fallback."""
    default = packs[0]
    by_id = {p.id: p for p in packs}
    opening = "\n\n".join(c.text for c in chunks)[:DETECTION_CHARS]
    messages = [
        SystemMessage(
            _SYSTEM.format(
                packs="\n".join(f"- {p.id}: {p.description}" for p in packs),
                default=default.id,
                schema=json.dumps(_Detection.model_json_schema()),
            )
        ),
        HumanMessage(f"Start of the contract:\n\n{opening}"),
    ]
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = llm.invoke(messages)
        except Exception:  # model unreachable: detection is optional, don't fail the upload
            logger.exception("type detection failed")
            break
        try:
            result = _Detection.model_validate(parse_json(str(reply.content)))
        except (ValueError, ValidationError):
            continue
        pack = by_id.get(result.pack)
        if pack is not None and result.confidence >= CONFIDENCE_THRESHOLD:
            return pack, Detected(pack=pack.id, confidence=result.confidence)
        break  # a valid but doubtful answer: don't ask again
    return default, Detected(pack=default.id, confidence=0.0)
