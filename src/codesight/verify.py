"""Verification loop for ask(): grounding score, citations, and confidence gating."""

from __future__ import annotations

import logging
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import Citation, SearchResult

if TYPE_CHECKING:
    from .llm import LLMBackend

logger = logging.getLogger(__name__)

HHEM_MODEL_NAME = "vectara/hallucination_evaluation_model"
HHEM_LOAD_WARNING = (
    "WARNING: HHEM model failed to load - grounding verification disabled. "
    "Install with: pip install codesight[verify]"
)

REFUSAL_TEXT = (
    "I couldn't find a confident answer to your question. Here are the most relevant "
    "sources I found - you may find the answer by reading them directly."
)


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class VerificationConfig:
    # NOTE: Field defaults are evaluated at import time, not instantiation.
    # api.py always overrides all fields from ServerConfig, so this is fine.
    verify_enabled: bool = _bool_env("CODESIGHT_VERIFY", True)
    high_threshold_claude: float = float(os.environ.get("CODESIGHT_VERIFY_HIGH_CLAUDE", "0.7"))
    high_threshold_other: float = float(os.environ.get("CODESIGHT_VERIFY_HIGH_OTHER", "0.8"))
    low_threshold: float = float(os.environ.get("CODESIGHT_VERIFY_LOW", "0.5"))
    max_retries: int = int(os.environ.get("CODESIGHT_VERIFY_MAX_RETRIES", "2"))
    timeout_seconds: float = float(os.environ.get("CODESIGHT_VERIFY_TIMEOUT_SECONDS", "5"))
    short_text_chars: int = int(os.environ.get("CODESIGHT_VERIFY_SHORT_TEXT_CHARS", "20"))


class GroundingScorer:
    def __init__(self, model_name: str = HHEM_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None
        self._disabled = False

    # SPEC-010-001: Lazy-load HHEM model once and reuse for process lifetime.
    def _load_model(self):
        if self._model is not None or self._disabled:
            return self._model
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        except Exception:
            # EDGE-010-001: Model load failure degrades verification gracefully.
            logger.warning(HHEM_LOAD_WARNING)
            self._disabled = True
        return self._model

    def score(
        self,
        answer_text: str,
        contexts: list[SearchResult],
        timeout_seconds: float,
        short_text_chars: int,
    ) -> float | None:
        if len(answer_text.strip()) < short_text_chars:
            # EDGE-010-004: Very short answers skip HHEM scoring.
            return None
        if not contexts:
            # EDGE-010-006: Empty context cannot be grounded.
            return None

        model = self._load_model()
        if model is None:
            return None

        context_blob = "\n\n".join(result.snippet for result in contexts)

        def _run_predict() -> float:
            value = model.predict([(answer_text, context_blob)])
            if isinstance(value, list):
                raw = float(value[0])
            else:
                raw = float(value[0]) if getattr(value, "__len__", lambda: 0)() else float(value)
            if raw < 0 or raw > 1:
                return float(1.0 / (1.0 + math.exp(-raw)))
            return raw

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_predict)
            try:
                return round(float(future.result(timeout=timeout_seconds)), 6)
            except TimeoutError:
                # EDGE-010-005: Timeout returns answer without score.
                logger.warning(
                    "HHEM scoring timed out after %ss - "
                    "returning answer without grounding verification",
                    int(timeout_seconds),
                )
                return None
            except Exception:
                return None


def parse_source_tag_citations(answer_text: str, sources: list[SearchResult]) -> list[Citation]:
    matches = sorted(set(re.findall(r"\[Source\s+(\d+)\]", answer_text)))
    citations: list[Citation] = []
    for tag in matches:
        idx = int(tag) - 1
        if idx < 0 or idx >= len(sources):
            continue
        source = sources[idx]
        citations.append(
            Citation(
                chunk_id=source.chunk_id,
                cited_text=source.snippet[:240],
                claim=f"Referenced by [Source {tag}]",
            )
        )
    return citations


def looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return "i don't know" in lowered or "no relevant documents found" in lowered


# SPEC-010-003: Confidence gate and retry/refuse decisions.
def confidence_decision(
    *,
    grounding_score: float | None,
    citations: list[Citation],
    answer_text: str,
    is_claude_backend: bool,
    config: VerificationConfig,
) -> tuple[str, str]:
    # EDGE-010-002: Non-Claude backends use stricter high-confidence threshold.
    high_threshold = (
        config.high_threshold_claude if is_claude_backend else config.high_threshold_other
    )
    has_citations = len(citations) > 0

    if grounding_score is None:
        if is_claude_backend and not has_citations and not looks_like_refusal(answer_text):
            return "retry", "low"
        return "pass", "medium" if has_citations else "low"

    if grounding_score < config.low_threshold:
        return "retry", "low"
    if is_claude_backend and not has_citations and not looks_like_refusal(answer_text):
        return "retry", "low"
    if grounding_score >= high_threshold and (has_citations or not is_claude_backend):
        return "pass", "high"
    if grounding_score < high_threshold:
        return "pass", "medium"
    return "retry", "low"


# SPEC-010-004: Retry path rewrites question before next retrieval attempt.
def rewrite_query(
    llm: "LLMBackend",
    original_question: str,
    low_confidence_answer: str,
    sources: list[SearchResult],
) -> str:
    source_hints = "\n".join(f"- {s.file_path}: {s.scope}" for s in sources[:5])
    prompt = (
        "Rewrite this question into one concise query that is more specific and easier to verify.\n"
        f"Original question: {original_question}\n"
        f"Low-confidence answer: {low_confidence_answer}\n"
        f"Available sources:\n{source_hints}\n"
        "Return only the rewritten query."
    )
    try:
        rewritten = llm.generate(
            "You rewrite retrieval questions for better document grounding.",
            prompt,
        ).strip()
    except Exception:
        # EDGE-010-007: Rewrite failure falls back to original query.
        logger.warning("Query rewrite failed - using original query for retry")
        return original_question
    if not rewritten:
        logger.warning("Query rewrite failed - using original query for retry")
        return original_question
    return rewritten
