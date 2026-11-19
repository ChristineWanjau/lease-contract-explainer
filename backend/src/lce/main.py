"""Production entrypoint: wires real Ollama models into the app factory."""

from __future__ import annotations

import os

from langchain_ollama import ChatOllama, OllamaEmbeddings

from lce.app import create_app

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("LCE_CHAT_MODEL", "qwen3:8b")
EMBED_MODEL = os.getenv("LCE_EMBED_MODEL", "nomic-embed-text")
ALLOWED_ORIGINS = os.getenv("LCE_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
# qwen3 "thinking" made the full sample analysis ~5.5 min vs ~1 min without it,
# with the same flags found. Set LCE_REASONING=true to turn it back on.
REASONING = os.getenv("LCE_REASONING", "false").lower() == "true"

app = create_app(
    llm=ChatOllama(
        model=CHAT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0, reasoning=REASONING
    ),
    embeddings=OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL),
    allowed_origins=ALLOWED_ORIGINS,
)
