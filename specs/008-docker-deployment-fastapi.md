# Spec 008: Docker Deployment + FastAPI Production Server

**Status:** implemented (single-team subset)
**Phase:** v0.5 SMB pilot
**Author:** Juan Martinez
**Created:** 2026-02-28
**Updated:** 2026-08-13

## Problem

The current Streamlit web chat UI works for demos and small teams but has limitations for the single-team pilot deployment:

- Streamlit is not the deployment surface for the pilot
- No REST API — other tools can't call CodeSight programmatically
- No authentication — anyone who can reach the URL can search all documents
- No standard deployment package — each client deployment is manual setup

When a consultant deploys CodeSight for one team on the client's cloud (Azure, AWS, GCP), they need a Docker image they can `docker run` and a guarded HTTP server.

The end product for clients is still the **web chat UI** — they type questions, get answers. FastAPI is the backend that serves this UI for the pilot.

## Goals

- Dockerfile for single-command deployment: `docker run codesight`
- FastAPI backend serving the CodeSight API over HTTP + web chat UI
- Support the focused single-team pilot without promising a concurrency target
- Basic auth (API key) for access control
- Documents mounted as a read-only volume — container can never modify source files
- Index persists across container restarts (Docker volume)
- Deploy to any cloud (Azure App Service, AWS ECS, GCP Cloud Run) or on-prem

## Non-Goals

- SSO / OAuth / SAML — too complex for v0.4, planned for v1.0
- Multi-tenant (separate indexes per user/team) — one index per deployment
- Kubernetes / Helm charts — Docker is sufficient for consulting deployments
- Custom frontend framework (React, Vue) — minimal HTML/JS chat UI served by FastAPI
- Database migration from SQLite — keep SQLite + LanceDB, they scale fine for single deployments

## Solution

```
Client opens browser → https://codesight.client.com
        |
        v
   [Docker container on client's cloud]
   +--------------------------------------------------+
   |  FastAPI server (uvicorn, port 8000)              |
   |                                                   |
   |  GET  /              → web chat UI (HTML/JS)      |
   |  POST /api/search    → engine.search()            |
   |  POST /api/ask       → engine.ask()               |
   |  POST /api/index     → engine.index()             |
   |  GET  /api/status    → engine.status()            |
   |                                                   |
   |  Auth middleware: X-API-Key header required        |
   |                                                   |
   |  CodeSight engine (shared instance)               |
   |  LanceDB + SQLite files                           |
   +--------------------------------------------------+
        |                    |
   /data (read-only)     /index (persistent volume)
   Client's documents    Search index
```

### Deployment Flow (Consultant → Client)

```bash
# 1. Build (or pull from registry)
docker build -t codesight .

# 2. Deploy on client's cloud
docker run -d \
  -p 8000:8000 \
  -v /path/to/client-docs:/data:ro \
  -v codesight-index:/index \
  -e CODESIGHT_DATA_DIR=/index \
  -e CODESIGHT_LLM_BACKEND=azure \
  -e AZURE_OPENAI_ENDPOINT=https://client.openai.azure.com/ \
  -e AZURE_OPENAI_API_KEY=... \
  -e AZURE_OPENAI_DEPLOYMENT=gpt-4o \
  -e CODESIGHT_API_KEY=client-secret-key \
  codesight

# 3. Client opens browser → http://server:8000
# 4. Client sees chat UI, asks questions about their documents
```

## API Contract

```
POST /api/search
  Request:
    query: str — search query
    top_k: int (default 8) — number of results
    file_glob: str | null — optional file filter

  Response (200):
    results: list[SearchResult] — ranked chunks with file path, page, score, content

  Errors:
    401 — missing or invalid API key
    400 — empty query


POST /api/ask
  Request:
    question: str — natural language question
    top_k: int (default 5) — chunks to use for context

  Response (200):
    text: str — LLM-generated answer
    sources: list[SearchResult] — chunks that informed the answer
    model: str — which LLM backend + model was used

  Errors:
    401 — missing or invalid API key
    400 — empty question
    503 — LLM backend unavailable (Ollama not running, API key invalid)


POST /api/index
  Request:
    force_rebuild: bool (default false) — full rebuild vs incremental

  Response (200):
    total_files: int
    total_chunks: int
    duration_seconds: float

  Errors:
    401 — missing or invalid API key


GET /api/status
  Response (200):
    indexed: bool
    total_files: int
    total_chunks: int
    last_indexed_at: str | null
    is_stale: bool

  Errors:
    401 — missing or invalid API key


GET /
  Response (200): HTML — web chat UI
```

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Server port | 8000 | Standard for FastAPI/uvicorn |
| Workers | 1 | Smallest pilot deployment shape; no concurrency SLA |
| Request timeout | 60s | `ask()` can take 5-10s for LLM call |
| Max request body | 1MB | Queries are small, prevent abuse |
| API key header | `X-API-Key` or `Authorization: Bearer` | Industry standard |

### Dependencies

New optional dependency group `[server]`:
```toml
[project.optional-dependencies]
server = ["fastapi>=0.110", "uvicorn>=0.30"]
```

- Depends on: Spec 001 (core engine), Spec 006 (pluggable LLM — backend configured via env vars)
- Depended on by: None (this is a deployment layer)

### New Files

| File | Purpose |
|------|---------|
| `src/codesight/web/server.py` | FastAPI app, routes, auth middleware |
| `src/codesight/web/static/` | Minimal HTML/JS/CSS chat UI |
| `Dockerfile` | Container build |
| `docker-compose.yml` | Dev/demo compose with example config |

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e ".[server]"

# Pre-download embedding model (no download on first run)
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000
ENV CODESIGHT_DATA_DIR=/index

CMD ["uvicorn", "codesight.web.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Web Chat UI

A minimal HTML/JS page served as a FastAPI static file. No build step, no React, no npm. Features:
- Chat input + message history
- Each answer shows expandable source cards (file, page, snippet)
- "Indexing..." spinner when re-index is triggered
- Responsive design (works on mobile)

This replaces Streamlit for the single-team pilot deployment. Streamlit stays for local development (`python -m codesight demo`).

### Auth Middleware

```python
# Simple API key auth — good enough for v0.4
CODESIGHT_API_KEY = os.environ.get("CODESIGHT_API_KEY")

@app.middleware("http")
async def auth_middleware(request, call_next):
    if CODESIGHT_API_KEY and request.url.path.startswith("/api/"):
        key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix("Bearer ")
        if key != CODESIGHT_API_KEY:
            return JSONResponse(status_code=401, content={"error": "Invalid API key"})
    return await call_next(request)
```

The web chat UI at `/` includes the API key in its fetch calls (injected via a config endpoint or environment).

## Alternatives Considered

### Alternative A: Keep Streamlit, add nginx reverse proxy

Trade-off: Simpler, reuse existing UI code. But Streamlit's single-threaded model limits throughput, and nginx adds deployment complexity.
Rejected because: FastAPI handles async natively, auto-generates OpenAPI docs, and we need a proper REST API anyway.

### Alternative B: Flask

Trade-off: Simpler than FastAPI, but no async, no automatic API docs, no built-in data validation.
Rejected because: FastAPI gives us async (important for concurrent LLM calls) + Pydantic validation + OpenAPI docs for free.

### Alternative C: Full React frontend

Trade-off: Better UX, component ecosystem. But requires npm, build step, separate dev server, more complexity.
Rejected because: A minimal HTML/JS chat UI is sufficient for v0.4. The main interaction is "type question, read answer." If clients want a custom frontend later, they can use the REST API.

## Edge Cases & Failure Modes

- Documents folder empty → `/api/index` returns 0 chunks, `/api/search` returns empty, `/api/ask` says "no documents indexed"
- Large PDF (100MB) → skip with warning, configurable max file size
- API key not set (`CODESIGHT_API_KEY` missing) → production startup fails; unauthenticated mode is limited to explicit local development configuration
- Docker volume not mounted → clear error on startup: "No documents found at /data. Mount your documents: -v /path/to/docs:/data:ro"
- Multiple concurrent `/api/index` requests → lock to prevent double-indexing, return "indexing in progress" to second request
- Container restart → index persists in `/index` volume, no re-indexing needed
- Embedding model not pre-downloaded → Dockerfile handles this, but if custom model: auto-download on first index

## Observability

- Structured JSON logs via Python `logging` (uvicorn default)
- Log events: startup, index start/complete, search query, ask query, errors
- `/api/status` endpoint doubles as a health check
- Request timing logged for each API call

## Open Questions

- [ ] Should the web chat UI be a separate static SPA or server-rendered HTML? Static is simpler but less dynamic. — @juan
- [ ] Should we support WebSocket for streaming LLM responses? Or stick with regular HTTP for v0.4? — @juan
- [ ] Docker image size — embedding model adds ~500MB. Pre-download in image or download on first run? — @juan
- [ ] Should `/api/index` be admin-only (separate API key)? Prevents users from triggering expensive rebuilds. — @juan

## Acceptance Criteria

- [ ] `docker build -t codesight .` builds successfully
- [ ] `docker run` with mounted documents starts FastAPI server on port 8000
- [ ] `GET /` serves the web chat UI — user can type questions and see answers
- [ ] `POST /api/search` returns search results as JSON
- [ ] `POST /api/ask` returns Answer with text and sources as JSON
- [ ] `POST /api/index` triggers indexing of mounted document folder
- [ ] `GET /api/status` returns index stats as JSON (also serves as health check)
- [ ] Requests without valid `X-API-Key` return 401
- [x] Pilot search and citation behavior covered by executable API tests
- [ ] Documents mounted read-only — container cannot modify source files
- [ ] Index persists across container restarts via Docker volume
- [ ] Embedding model pre-downloaded in image (no internet needed on first run)
- [ ] Works with all LLM backends (Claude, Azure, OpenAI, Ollama) via env vars
