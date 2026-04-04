"""Pluggable LLM backend for answer synthesis.

Supports 4 backends, selected via CODESIGHT_LLM_BACKEND env var:
  - claude  (default) — Anthropic API
  - azure   — Azure OpenAI (data stays in client's tenant)
  - openai  — OpenAI API
  - ollama  — Local model via Ollama (zero network)

Search is always 100% local. Only ask() touches the LLM.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)

# System prompt shared across ALL backends — same answer quality expectations.
SYSTEM_PROMPT = (
    "You are a helpful document assistant. Answer questions based ONLY on the "
    "provided source documents. If the answer is not in the sources, say so. "
    "Always cite which source(s) your answer comes from using [Source N] notation."
)

REQUEST_TIMEOUT = 30  # seconds


class LLMBackend(Protocol):
    """Protocol for LLM backends. Each backend implements generate()."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send prompt, return response text."""
        ...

    @property
    def model_id(self) -> str:
        """Return identifier like 'claude:claude-sonnet-4-20250514'."""
        ...


# ---------------------------------------------------------------------------
# Claude (Anthropic API)
# ---------------------------------------------------------------------------

class ClaudeBackend:
    """Anthropic Claude API backend."""

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required for the Claude backend. "
                "Set it or switch to a different backend: CODESIGHT_LLM_BACKEND=ollama"
            )
        self._model = model
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        """Lazy-loaded Anthropic client (cached for process lifetime)."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key, timeout=REQUEST_TIMEOUT)
        return self._client

    @property
    def model_id(self) -> str:
        return f"claude:{self._model}"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        message = self.client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

class AzureOpenAIBackend:
    """Azure OpenAI backend — data stays in client's Azure tenant."""

    def __init__(self) -> None:
        self._endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        self._api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        self._deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        self._api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        self._client = None

        if not self._endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT environment variable is required for the Azure backend. "
                "Example: https://mycompany.openai.azure.com/"
            )
        if not self._api_key:
            raise ValueError(
                "AZURE_OPENAI_API_KEY environment variable is required for the Azure backend."
            )

    @property
    def client(self):
        """Lazy-loaded Azure OpenAI client (cached for process lifetime)."""
        if self._client is None:
            from openai import AzureOpenAI

            self._client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
                timeout=REQUEST_TIMEOUT,
            )
        return self._client

    @property
    def model_id(self) -> str:
        return f"azure:{self._deployment}"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIBackend:
    """OpenAI API backend."""

    def __init__(self, model: str = "gpt-4o") -> None:
        self._api_key = os.environ.get("OPENAI_API_KEY")
        self._model = model
        self._client = None

        if not self._api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for the OpenAI backend."
            )

    @property
    def client(self):
        """Lazy-loaded OpenAI client (cached for process lifetime)."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, timeout=REQUEST_TIMEOUT)
        return self._client

    @property
    def model_id(self) -> str:
        return f"openai:{self._model}"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaBackend:
    """Ollama local inference — zero network, 100% private."""

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        import httpx

        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=60.0)
        except httpx.ConnectError:
            raise ConnectionError(
                f"Ollama server not found at {self._base_url}. "
                "Start it with: ollama serve"
            ) from None

        if resp.status_code == 404:
            raise ValueError(
                f"Model '{self._model}' not found in Ollama. "
                f"Download it with: ollama pull {self._model}"
            )

        resp.raise_for_status()
        return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_VALID_BACKENDS = {"claude", "azure", "openai", "ollama"}


def get_backend(
    backend_name: str,
    model: str | None = None,
) -> LLMBackend:
    """Create an LLM backend by name.

    Args:
        backend_name: One of 'claude', 'azure', 'openai', 'ollama'.
        model: Optional model override. Meaning depends on backend:
            - claude: Anthropic model ID (default: claude-sonnet-4-20250514)
            - azure: ignored (deployment name from AZURE_OPENAI_DEPLOYMENT)
            - openai: OpenAI model ID (default: gpt-4o)
            - ollama: Ollama model name (default: llama3.1)
    """
    if backend_name not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown LLM backend: '{backend_name}'. "
            f"Valid options: {', '.join(sorted(_VALID_BACKENDS))}"
        )

    match backend_name:
        case "claude":
            return ClaudeBackend(model=model or "claude-sonnet-4-20250514")
        case "azure":
            return AzureOpenAIBackend()
        case "openai":
            return OpenAIBackend(model=model or "gpt-4o")
        case "ollama":
            ollama_model = model or os.environ.get("OLLAMA_MODEL", "llama3.1")
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            return OllamaBackend(model=ollama_model, base_url=base_url)
