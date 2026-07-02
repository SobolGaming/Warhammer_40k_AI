from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
HEX_DIGEST_PATTERN = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def test_active_code_tests_and_docs_do_not_reference_retired_edition_ids() -> None:
    violations: list[str] = []

    for path in _scanned_paths():
        text = _without_hex_digests(path.read_text(encoding="utf-8"))
        relative_path = path.relative_to(ROOT).as_posix()
        for token in _retired_identity_tokens():
            if token in text:
                violations.append(f"{relative_path}: contains {token!r}")

    assert not violations, (
        "Phase 14A requires active runtime, test, and docs identity to be 11th Edition-only:\n"
        + "\n".join(violations)
    )


def _scanned_paths() -> tuple[Path, ...]:
    roots = (
        ROOT / "src",
        ROOT / "tests",
        ROOT / "docs",
        ROOT / "README.md",
        ROOT / "ARCHITECTURE_V2.md",
    )
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
            continue
        paths.extend(path for path in root.rglob("*") if path.is_file())
    return tuple(
        sorted(
            (
                path
                for path in paths
                if path.suffix in {".md", ".py", ".json"}
                and "__pycache__" not in path.parts
                and path != THIS_FILE
            ),
            key=lambda path: path.as_posix(),
        )
    )


def _retired_identity_tokens() -> tuple[str, ...]:
    return (
        "warhammer_40000_" + "10th",
        "gw-" + "10e",
        "1" + "0" + "e",
        "1" + "0" + "th",
        "tenth",
        "Tenth",
        "TENTH",
        "11e" + "_" + "preview",
        "eleventh" + "_" + "preview",
        "ELEVENTH" + "_" + "PREVIEW",
    )


def _without_hex_digests(text: str) -> str:
    return HEX_DIGEST_PATTERN.sub("", text)
