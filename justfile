default:
    @just --list

inspect:
    uv run --offline python -m holusight --help

# Rescan source for duplication candidates and explicitly linked fact mismatches.
align:
    uv run --offline holus align .

lint:
    uv run --offline --extra dev ruff check src/ tests/

test:
    uv run --offline --extra dev pytest tests/ -q

check: lint test
