from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE_PATH = ROOT / "ARCHITECTURE_V2.md"
README_PATH = ROOT / "README.md"


def test_phase17a1_docs_mark_transition_patch_packages_complete() -> None:
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    phase17a1_section = architecture.split(
        "## Phase 17A.1: official 11th Edition transition patch packages",
        maxsplit=1,
    )[1].split("\n## Phase 17B:", maxsplit=1)[0]

    assert "Status: Complete." in phase17a1_section
    assert "Phase 17A.1 is complete" in architecture
    assert "Phase 17A.1 is complete" in readme
    assert "| 17A.1 | Complete |" in architecture
    assert "| 17A.1-17G | Planned |" not in architecture
    assert "target-drift diagnostics" in phase17a1_section
    assert "FAQ classifications" in phase17a1_section
    assert "PatchedSourceArtifact" in phase17a1_section
