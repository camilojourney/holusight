# Docker deployment playbook

Deploy Holusight as a single-team pilot on the customer's infrastructure.

## Prerequisites

- Docker 24+ and Docker Compose v2
- Read-only folder of documents (or git checkout mounted `:ro`)
- API key for the deployment (`CODESIGHT_API_KEY`)
- Optional: LLM provider credentials for **Ask** mode (Search works without any LLM)

## Quick start (pilot)

```bash
git clone https://github.com/camilojourney/holusight.git
cd holusight

export CODESIGHT_API_KEY=$(openssl rand -hex 24)
export CODESIGHT_LLM_BACKEND=claude   # or azure, openai, ollama
export ANTHROPIC_API_KEY=sk-ant-...   # if using Claude

# Edit docker-compose.yml volumes to point at customer docs:
#   - /path/to/customer/docs:/data:ro

docker compose up --build -d
```

Open `http://<server>:8000`, enter the API key in the sidebar, click **Re-index**, then search.

## What runs where

| Process | Stops when… |
|---------|-------------|
| `uvicorn` (FastAPI) | Container stops or `docker compose down` |
| LanceDB + SQLite index | Persisted in Docker volume `holusight-index` |
| Embedding model | Loaded in container memory on first search/index |
| Source documents | Never modified — mounted read-only at `/data` |

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `CODESIGHT_API_KEY` | **Yes** (production) | Shared team API key |
| `CODESIGHT_DOCUMENTS_DIR` | Default `/data` | Read-only document root inside container |
| `CODESIGHT_DATA_DIR` | Default `/index` | Persistent index volume |
| `CODESIGHT_PRODUCTION` | `1` in image | Enforces API key |
| `CODESIGHT_LLM_BACKEND` | For Ask | `claude`, `azure`, `openai`, `ollama` |
| `CODESIGHT_ALLOW_UNAUTHENTICATED` | Dev only | Never use in customer production |

## Health & operations

```bash
# Health (no auth)
curl -s http://localhost:8000/api/health | jq

# Status (auth required)
curl -s -H "X-API-Key: $CODESIGHT_API_KEY" http://localhost:8000/api/status | jq

# Trigger re-index
curl -s -X POST -H "X-API-Key: $CODESIGHT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"force_rebuild":false}' \
  http://localhost:8000/api/index | jq
```

## Backup

Back up the index volume — it contains LanceDB tables and SQLite FTS data:

```bash
docker run --rm -v holusight-index:/index -v $(pwd):/backup alpine \
  tar czf /backup/holusight-index-$(date +%Y%m%d).tar.gz -C /index .
```

Restore by extracting into a new volume before starting the container.

## Rotate credentials

1. Generate new `CODESIGHT_API_KEY`
2. Update compose env and `docker compose up -d`
3. Distribute new key to team (browser session storage clears on new key entry)

## Upgrade

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

Index format is compatible within v0.3.x; force rebuild if embedding model changes.

## Remove deployment

```bash
docker compose down -v   # -v deletes index volume — backup first if needed
```

Source documents on the host are untouched.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| 401 on API | API key header; `CODESIGHT_PRODUCTION=1` requires key |
| 503 on Ask | LLM env vars for chosen backend; Search still works |
| Empty search results | Run `/api/index`; verify `/data` mount |
| Container exits on start | Logs: missing `CODESIGHT_API_KEY` or `/data` not mounted |

## Local dev (without Docker)

```bash
pip install -e ".[server,dev]"
export CODESIGHT_DOCUMENTS_DIR=./tests/fixtures/pilot_docs
export CODESIGHT_API_KEY=dev-key
export CODESIGHT_ALLOW_UNAUTHENTICATED=true  # local only
python -m codesight serve ./tests/fixtures/pilot_docs
```
