from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from tools.canonical_json_hash import canonical_json_sha256
from tools.generate_ability_support_matrix import (
    faction_support_markdown_files,
)

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
)

ROOT = Path(__file__).resolve().parents[2]
FACTION_DOCS_DIR = ROOT / "docs" / "factions"
FACTION_DOCUMENT_FILENAMES = tuple(
    f"{row.faction_id}.md" for row in faction_detachments_2026_27.faction_rows()
)


@pytest.mark.parametrize("filename", FACTION_DOCUMENT_FILENAMES)
def test_generated_faction_documents_are_current(filename: str) -> None:
    generated = _generated_faction_documents()
    committed_filenames = {path.name for path in FACTION_DOCS_DIR.glob("*.md")}

    assert tuple(generated) == FACTION_DOCUMENT_FILENAMES
    assert set(generated) == committed_filenames == set(FACTION_DOCUMENT_FILENAMES)
    assert generated[filename] == (FACTION_DOCS_DIR / filename).read_text(encoding="utf-8")


def test_generated_json_dependency_hashes_ignore_checkout_line_endings(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.json"
    crlf_path = tmp_path / "crlf.json"
    payload = b'{\n  "rows": [\n    {"id": "source-row"}\n  ]\n}\n'
    lf_path.write_bytes(payload)
    crlf_path.write_bytes(payload.replace(b"\n", b"\r\n"))

    assert canonical_json_sha256(lf_path) == canonical_json_sha256(crlf_path)


@cache
def _generated_faction_documents() -> dict[str, str]:
    return faction_support_markdown_files()
