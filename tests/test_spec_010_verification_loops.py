from __future__ import annotations

import time
from pathlib import Path

import pytest

from codesight.api import CodeSight
from codesight.config import ServerConfig
from codesight.llm import LLMResponse
from codesight.types import Answer, Citation, SearchResult
from codesight.verify import REFUSAL_TEXT, GroundingScorer


def _mk_result() -> SearchResult:
    return SearchResult(
        file_path="src/codesight/chunker.py",
        start_line=10,
        end_line=12,
        snippet="verification snippet",
        score=1.0,
        scope="function chunk_file",
        chunk_id="chunk-1",
    )


def _mk_citation() -> Citation:
    return Citation(chunk_id="chunk-1", cited_text="snippet", claim="claim")


class StubScorer:
    def __init__(self, values: list[float | None]) -> None:
        self.values = values
        self.calls = 0

    def score(self, *_args, **_kwargs) -> float | None:
        idx = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[idx]


class StrictScorer:
    def score(self, *_args, **_kwargs) -> float | None:  # pragma: no cover - should not be called
        raise AssertionError("Verifier should not run")


class StubLLM:
    def __init__(
        self,
        *,
        responses: list[LLMResponse],
        rewrite_responses: list[str] | None = None,
        rewrite_raises: bool = False,
    ) -> None:
        self.model_id = "stub:model"
        self._responses = list(responses)
        self._rewrite_responses = list(rewrite_responses or [])
        self._rewrite_raises = rewrite_raises

    def generate_with_citations(self, *_args, **_kwargs) -> LLMResponse:
        return self._responses.pop(0)

    def generate(self, *_args, **_kwargs) -> str:
        if self._rewrite_raises:
            raise RuntimeError("rewrite failed")
        if self._rewrite_responses:
            return self._rewrite_responses.pop(0)
        return "rewritten query"


def _mk_engine(tmp_path: Path, *, backend: str = "claude", verify: bool = True) -> CodeSight:
    cfg = ServerConfig(llm_backend=backend, verify=verify, verify_max_retries=2)
    return CodeSight(tmp_path, config=cfg)


def test_spec_010_001_grounding_score_added_to_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-010-001: ask() returns grounding_score when verification is enabled."""
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    result = _mk_result()
    monkeypatch.setattr(
        CodeSight,
        "search",
        lambda self, q, top_k=5, file_glob=None: [result],
    )
    engine._llm = StubLLM(
        responses=[
            LLMResponse(
                text="Grounded answer [Source 1]",
                citations=[_mk_citation()],
            )
        ]
    )
    engine._verifier = StubScorer([0.91])

    answer = engine.ask("What does chunk_file do?")
    assert answer.grounding_score == 0.91
    assert answer.confidence_level == "high"


def test_spec_010_002_claude_citations_attached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """SPEC-010-002: Claude path includes citations in Answer."""
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    result = _mk_result()
    monkeypatch.setattr(
        CodeSight,
        "search",
        lambda self, q, top_k=5, file_glob=None: [result],
    )
    engine._llm = StubLLM(
        responses=[
            LLMResponse(
                text="Cited answer [Source 1]",
                citations=[_mk_citation()],
            )
        ]
    )
    engine._verifier = StubScorer([0.95])

    answer = engine.ask("q")
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk_id == "chunk-1"


def test_spec_010_003_confidence_gate_retry_and_low_confidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-010-003: Retry low scores, warn on medium scores."""
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    result = _mk_result()
    query_log: list[str] = []

    def _search(self, query: str, top_k: int = 5, file_glob=None):
        query_log.append(query)
        return [result]

    monkeypatch.setattr(CodeSight, "search", _search)
    engine._llm = StubLLM(
        responses=[
            LLMResponse(text="Bad answer", citations=[_mk_citation()]),
            LLMResponse(
                text="Good answer [Source 1]",
                citations=[_mk_citation()],
            ),
        ],
        rewrite_responses=["better specific question"],
    )
    engine._verifier = StubScorer([0.4, 0.92])

    answer = engine.ask("original question")
    assert answer.retries == 1
    assert answer.confidence_level == "high"
    assert query_log[0] == "original question"
    assert query_log[1] == "better specific question"


def test_spec_010_004_query_rewrite_changes_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-010-004: Retry uses rewritten query text."""
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    result = _mk_result()
    queries: list[str] = []

    def _search(self, query: str, top_k: int = 5, file_glob=None):
        queries.append(query)
        return [result]

    monkeypatch.setattr(CodeSight, "search", _search)
    engine._llm = StubLLM(
        responses=[
            LLMResponse(text="Low confidence", citations=[_mk_citation()]),
            LLMResponse(
                text="Recovered [Source 1]",
                citations=[_mk_citation()],
            ),
        ],
        rewrite_responses=["rewritten specific query"],
    )
    engine._verifier = StubScorer([0.2, 0.9])

    engine.ask("rewrite me")
    assert queries[0] == "rewrite me"
    assert queries[1] == "rewritten specific query"


def test_spec_010_005_answer_model_extension_defaults():
    """SPEC-010-005: New Answer fields are optional/backward compatible."""
    answer = Answer(text="x", sources=[], model="demo")
    assert answer.grounding_score is None
    assert answer.citations == []
    assert answer.confidence_level == "high"
    assert answer.retries == 0


def test_spec_010_006_verification_toggle_disables_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-010-006: Verification disabled path has no verifier overhead."""
    engine = _mk_engine(tmp_path, backend="claude", verify=False)
    result = _mk_result()
    monkeypatch.setattr(
        CodeSight,
        "search",
        lambda self, q, top_k=5, file_glob=None: [result],
    )
    engine._llm = StubLLM(
        responses=[LLMResponse(text="Answer [Source 1]", citations=[_mk_citation()])]
    )
    engine._verifier = StrictScorer()

    answer = engine.ask("q")
    assert answer.grounding_score is None
    assert answer.citations == []
    assert answer.confidence_level == "high"


def test_edge_010_001_hhem_model_load_failure_returns_none(tmp_path: Path):
    scorer = GroundingScorer()
    scorer._disabled = True
    score = scorer.score(
        "Long enough answer text for scoring",
        [_mk_result()],
        timeout_seconds=0.1,
        short_text_chars=20,
    )
    assert score is None


def test_edge_010_002_non_claude_uses_higher_high_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    engine = _mk_engine(tmp_path, backend="ollama", verify=True)
    result = _mk_result()
    monkeypatch.setattr(
        CodeSight,
        "search",
        lambda self, q, top_k=5, file_glob=None: [result],
    )
    engine._llm = StubLLM(responses=[LLMResponse(text="answer", citations=[])])
    engine._verifier = StubScorer([0.75])
    answer = engine.ask("q")
    # 0.75 is below non-Claude high threshold (0.8) but above low (0.5) → medium
    assert answer.confidence_level == "medium"


def test_edge_010_003_retries_exhausted_returns_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    result = _mk_result()
    monkeypatch.setattr(
        CodeSight,
        "search",
        lambda self, q, top_k=5, file_glob=None: [result],
    )
    engine._llm = StubLLM(
        responses=[
            LLMResponse(text="bad", citations=[_mk_citation()]),
            LLMResponse(text="still bad", citations=[_mk_citation()]),
            LLMResponse(text="still bad 2", citations=[_mk_citation()]),
        ],
        rewrite_responses=["q2", "q3"],
    )
    engine._verifier = StubScorer([0.1, 0.2, 0.3])
    answer = engine.ask("q")
    assert answer.text == REFUSAL_TEXT
    assert answer.confidence_level == "refused"
    assert answer.retries == 2


def test_edge_010_004_short_answer_skips_hhem_model_load():
    scorer = GroundingScorer()
    scorer._load_model = lambda: (_ for _ in ()).throw(RuntimeError("should not load"))
    score = scorer.score("yes", [_mk_result()], timeout_seconds=0.1, short_text_chars=20)
    assert score is None


def test_edge_010_005_hhem_timeout_returns_none_and_does_not_block(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    class SlowModel:
        def predict(self, _pairs):
            time.sleep(0.2)
            return [0.9]

    scorer = GroundingScorer()
    monkeypatch.setattr(scorer, "_load_model", lambda: SlowModel())
    score = scorer.score(
        "This answer is long enough to trigger scoring",
        [_mk_result()],
        timeout_seconds=0.01,
        short_text_chars=20,
    )
    assert score is None
    assert "timed out" in caplog.text


def test_edge_010_006_empty_context_skips_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    monkeypatch.setattr(CodeSight, "search", lambda self, q, top_k=5, file_glob=None: [])
    engine._llm = StubLLM(
        responses=[LLMResponse(text="No relevant documents found.", citations=[])]
    )
    engine._verifier = StrictScorer()
    answer = engine.ask("q")
    assert answer.grounding_score is None
    assert answer.confidence_level == "low"


def test_edge_010_007_query_rewrite_failure_falls_back_to_original_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    engine = _mk_engine(tmp_path, backend="claude", verify=True)
    result = _mk_result()
    seen_queries: list[str] = []

    def _search(self, query: str, top_k: int = 5, file_glob=None):
        seen_queries.append(query)
        return [result]

    monkeypatch.setattr(CodeSight, "search", _search)
    engine._llm = StubLLM(
        responses=[
            LLMResponse(text="bad", citations=[_mk_citation()]),
            LLMResponse(text="still bad", citations=[_mk_citation()]),
            LLMResponse(text="still bad 2", citations=[_mk_citation()]),
        ],
        rewrite_raises=True,
    )
    engine._verifier = StubScorer([0.1, 0.1, 0.1])
    answer = engine.ask("original q")
    assert answer.confidence_level == "refused"
    assert seen_queries == ["original q", "original q", "original q"]
    assert "Query rewrite failed - using original query for retry" in caplog.text
