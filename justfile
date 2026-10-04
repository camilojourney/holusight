default:
    @just --list

# Check an existing Graphify graph against repository source. Never rebuilds.
inspect:
    uv run --offline python -m holusight --help

check-graph:
    uv run --offline python -m holusight check

# Rescan source for duplication candidates and explicitly linked fact mismatches.
align:
    uv run --offline holus align .

lint:
    uv run --offline --extra dev ruff check src/ tests/

test:
    uv run --offline --extra dev pytest tests/ -q

check: lint test
