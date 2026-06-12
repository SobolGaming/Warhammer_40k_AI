from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACTION_CONTENT_ROOT = ROOT / "src" / "warhammer40k_core" / "engine" / "faction_content"
MAX_FACTION_CONTENT_FILE_LINES = 2000
FORBIDDEN_RUNTIME_IMPORT_TOKENS = (
    "html_sanitizer",
    "rule_compiler",
    "rule_parser",
    "wahapedia",
)


def test_faction_content_runtime_files_stay_below_line_limit() -> None:
    oversized: list[tuple[str, int]] = []
    for path in sorted(FACTION_CONTENT_ROOT.rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_FACTION_CONTENT_FILE_LINES:
            oversized.append((path.relative_to(ROOT).as_posix(), line_count))

    assert oversized == []


def test_faction_content_runtime_does_not_import_raw_source_or_parser_tooling() -> None:
    offenders: list[tuple[str, str]] = []
    for path in sorted(FACTION_CONTENT_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_IMPORT_TOKENS:
            if token in text:
                offenders.append((path.relative_to(ROOT).as_posix(), token))

    assert offenders == []
