# Spec 006: Pluggable LLM Backend

**Status:** implemented
**Phase:** v0.3
**Author:** Juan Martinez
**Created:** 2026-02-28
**Updated:** 2026-02-28

## Problem

Currently `ask()` is hardcoded to the Claude API (Anthropic). In consulting engagements, different clients have different security and vendor requirements:

- **"We can't send data outside our Azure tenant"** → needs Azure OpenAI
- **"No data can leave our network, period"** → needs local LLM (Ollama)
- **"We already have an OpenAI contract"** → needs OpenAI API
- **"We want the best answers possible"** → Claude API is fine

The consultant must be able to configure the LLM backend per client without changing code. The web chat UI and CLI should work identically regardless of which backend is selected.

## Goals

- Support 4 LLM backends: Claude API, Azure OpenAI, OpenAI, Ollama (local)
- Single env var (`CODESIGHT_LLM_BACKEND`) selects the backend
- `search()` remains 100% local — never touches the LLM
- Same system prompt and answer format across all backends
- Clear error messages when credentials are missing
- Web chat UI and CLI work identically regardless of backend

## Non-Goals

- Supporting every LLM provider (Gemini, Mistral, Cohere, etc.) — add later by request
- Streaming responses — separate improvement, works with any backend
- Different prompts per backend — same prompt, same output expectations
- LLM quality benchmarking — client chooses based on security, not quality comparison

## Solution

```
ask(question)
    |
    v
search(question) → top 5 chunks              [ALWAYS LOCAL]
    |
    v
Format system prompt + context + question     [SAME FOR ALL BACKENDS]
    |
    v
LLM Backend (pluggable)                      [CLIENT'S CHOICE]
    ├── claude  → Anthropic API
    ├── azure   → Azure OpenAI (client's tenant)
    ├── openai  → OpenAI API
    └── ollama  → Local model (localhost:11434)
    |
    v
Answer(text, sources, model)
```

### Backend Adapter

```python
class LLMBackend(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send prompt, return response text."""

def get_backend(config: ServerConfig) -> LLMBackend:
    match config.llm_backend:
        case "claude":  return ClaudeBackend(...)
        case "azure":   return AzureOpenAIBackend(...)
        case "openai":  return OpenAIBackend(...)
        case "ollama":  return OllamaBackend(...)
        case _:         raise ValueError(f"Unknown backend: {config.llm_backend}")
```

## API Contract

No change to the Python API. Configuration is via environment variables.

```bash
# Claude (default)
CODESIGHT_LLM_BACKEND=claude
ANTHROPIC_API_KEY=sk-ant-...

# Azure OpenAI (data stays in client's Azure tenant)
CODESIGHT_LLM_BACKEND=azure
AZURE_OPENAI_ENDPOINT=https://mycompany.openai.azure.com/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# OpenAI
CODESIGHT_LLM_BACKEND=openai
OPENAI_API_KEY=sk-...

# Ollama (100% local, zero network)
CODESIGHT_LLM_BACKEND=ollama
OLLAMA_MODEL=llama3.1           # optional, default: llama3.1
OLLAMA_BASE_URL=http://localhost:11434  # optional
```

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Default backend | `claude` | Best answer quality, existing implementation |
| Claude model | `claude-sonnet-4-20250514` | Balance quality/speed/cost |
| Ollama default model | `llama3.1` | Good quality, runs on 8GB RAM |
| Request timeout | 30 seconds | Prevents hanging on slow backends |
| Max retries | 1 (API), 0 (Ollama) | One retry for transient API errors |

### Dependencies

| Backend | Dependency | Status |
|---------|-----------|--------|
| Claude | `anthropic>=0.40` | Already installed |
| Azure OpenAI | `openai>=1.0` | New — add as optional: `pip install codesight[azure]` |
| OpenAI | `openai>=1.0` | Same package as Azure |
| Ollama | `httpx` or `requests` | Already available (httpx via anthropic) |

- Depends on: Spec 001 (core search engine)
- Depended on by: Spec 008 (Docker deployment — backend configured per container)

### Scaling per Backend

| Backend | Concurrent users | Cost/question | Data leaves? |
|---------|-----------------|---------------|-------------|
| Claude API | Unlimited | $0.01-0.03 | Yes (chunks → Anthropic) |
| Azure OpenAI | Per quota | $0.01-0.03 | No (client's tenant) |
| OpenAI API | Unlimited | $0.01-0.03 | Yes (chunks → OpenAI) |
| Ollama | ~1-5 on single GPU | Free | No (localhost) |

### File Changes

| File | Change |
|------|--------|
| `src/codesight/llm.py` | NEW — `LLMBackend` protocol + 4 implementations |
| `src/codesight/api.py` | Modify `_call_claude()` → `_call_llm()` using backend adapter |
| `src/codesight/config.py` | Add `llm_backend`, Azure/Ollama env vars |
| `pyproject.toml` | Add `[azure]` and `[openai]` optional dep groups |

## Alternatives Considered

### Alternative A: LiteLLM wrapper library

Trade-off: Abstracts 100+ providers behind one API, saves implementation time.
Rejected because: Heavy dependency with many transitive deps. We only need 4 backends. Each adapter is ~30-50 lines.

### Alternative B: LangChain

Trade-off: Massive ecosystem, many integrations.
Rejected because: We need `send_prompt() → string`. LangChain's abstraction layers are extreme overkill.

### Alternative C: Only support Claude + Ollama

Trade-off: Fewer backends to maintain, covers "best quality" and "fully local" cases.
Rejected because: Azure OpenAI is critical for enterprise clients who are already on Azure. OpenAI is trivial to add since it uses the same `openai` package.

## Edge Cases & Failure Modes

- Ollama not running → clear error: "Ollama server not found at localhost:11434. Start it with: ollama serve"
- Ollama model not downloaded → clear error: "Model 'llama3.1' not found. Download it with: ollama pull llama3.1"
- Azure deployment name wrong → surface Azure error with added context about checking deployment name
- API rate limit → retry once with 2s delay, then raise with message suggesting reducing concurrent usage
- Network timeout → 30s timeout, clear error: "LLM request timed out. Check network or try CODESIGHT_LLM_BACKEND=ollama for local inference"
- Missing API key → clear error naming the exact env var needed for the selected backend
- `search()` called with no backend configured → works fine (search never uses LLM)
- `ask()` called with no backend configured → defaults to Claude, fails with clear API key error if missing

## Open Questions

- [ ] Should we support model override per-call? e.g., `engine.ask(question, model="gpt-4o")` — @juan
- [ ] Should Ollama timeout be longer than API timeout? Local inference is slower. — @juan
- [ ] Should we validate Azure endpoint URL format on startup? — @juan

## Acceptance Criteria

- [ ] `CODESIGHT_LLM_BACKEND=claude` works with `ANTHROPIC_API_KEY` (existing behavior)
- [ ] `CODESIGHT_LLM_BACKEND=azure` works with Azure OpenAI env vars
- [ ] `CODESIGHT_LLM_BACKEND=openai` works with `OPENAI_API_KEY`
- [ ] `CODESIGHT_LLM_BACKEND=ollama` works with local Ollama server
- [ ] Invalid backend name raises `ValueError` listing valid options
- [ ] Missing credentials produce error naming the exact env var required
- [ ] `search()` works with no LLM backend configured (100% local)
- [ ] `Answer.model` reports which backend + model was used (e.g., "claude:claude-sonnet-4-20250514")
- [ ] Same system prompt used across all backends — same answer quality expectations
- [ ] Web chat UI works identically with any backend
- [ ] `uv run --extra dev pytest tests/ -x -v` passes (API tests mocked, Ollama test optional)
