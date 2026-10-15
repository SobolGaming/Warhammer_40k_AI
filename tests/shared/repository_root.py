"""Stable repository anchor for relocated test source artifacts."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


__all__: list[str] = []
__all__ += ["Path"]
