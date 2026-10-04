"""Console-script alias for the read-only ``python -m holusight`` command."""

from __future__ import annotations

from .__main__ import main as _main


def main() -> None:
    raise SystemExit(_main())
