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


def test_phase17b_docs_capture_model_geometry_override_contract() -> None:
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    phase17b_section = architecture.split(
        "## Phase 17B: canonical 11th Edition catalog generation from patched source data",
        maxsplit=1,
    )[1].split("\n## Phase 17C:", maxsplit=1)[0]

    assert "CORE V1's `data/model_geometry_overrides.json`" in phase17b_section
    assert "`Use model`" in phase17b_section
    assert "flying-base" in phase17b_section
    assert "representative model height" in phase17b_section
    assert "runtime engine code consumes only accepted catalog geometry" in phase17b_section
    assert "representative model height with provenance" in readme
