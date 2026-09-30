default:
    @just --list

# Check an existing Graphify graph against repository source. Never rebuilds.
inspect:
    uv run --offline python -m holusight --help

check-graph:
    uv run --offline python -m holusight check

lint:
    uv run --offline --extra dev ruff check src/ tests/

test:
    uv run --offline --extra dev pytest tests/ -q

check: lint test
