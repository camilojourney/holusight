# Structure

Holusight is a read-only Graphify graph/source consistency helper. Current architecture and supported interfaces are in `ARCHITECTURE.md` and `specs/028-graphify-consistency-helper.md`.

- `src/holusight/consistency.py`: graph loading, provenance, mismatch checks.
- `src/holusight/api.py`: `Holusight.check()` and `.status()`.
- `src/holusight/__main__.py` and `cli_axi.py`: `python -m holusight` and `holus` commands.
- `tests/test_consistency.py` and `tests/test_cli_axi.py`: behavioral and public-command checks.
- `specs/NNN-*.md`: numbered specifications; older ones are historical.
- `docs/decisions/`: immutable accepted ADRs; `docs/playbooks/`: current development guide and marked historical playbooks.
- `landing/`: static public page.

Do not create ad-hoc docs or root files. Never write to a repository being checked. Graphify builds happen outside this tool and are never implicit.
