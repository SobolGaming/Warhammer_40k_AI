"""Current Shock source does not rewrite its historical source/assertion receipts."""

import hashlib
import json
from pathlib import Path

import pytest
from tools import core_rules_order97_inventory, v963_shock_source
from tools.core_rules_order95_audit import RETIRED_REFERENCE_SUCCESSORS, validate_owner_reference
from tools.core_rules_order97_history import MAPPING, historical_evidence_path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_transports_2026_09 as source,
)


def test_v963_full_observation_reproduces_and_qualifies_version_and_supersession() -> None:
    v963_shock_source.verify_source_observation()
    assert json.loads(v963_shock_source.AUDIT_PATH.read_bytes()) == v963_shock_source.build_audit()
    evidence = source.source_package().source_evidence_catalog.records_for_source_id(
        source.SHOCK_DISEMBARK_MOVE_SOURCE_ID
    )
    mirror = next(row for row in evidence if row.authority == "project_authoritative_app_mirror")
    assert mirror.provider_name == "Game Datamissions"
    assert mirror.source_url == v963_shock_source.SOURCE_URL
    assert mirror.app_version is None
    assert mirror.observed_at == v963_shock_source.OBSERVED_AT
    assert mirror.provider_non_affiliation_recorded
    assert mirror.official_corroborating_source_ids == ()
    historical = historical_evidence_path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_transports_2026_09/artifacts/package.json",
        root=v963_shock_source.ROOT,
    )
    assert historical is not None
    old = json.loads(historical.read_bytes())
    current = source.source_rule_records()
    assert old["rules"][0]["source_text"] == current[0].source_text
    assert old["rules"][1]["source_text"] == current[1].source_text
    assert "your opponent must select each" in old["rules"][2]["source_text"]
    assert "your opponent must select each" not in current[2].source_text
    assert "not eligible to declare a charge until the end of the turn" in current[2].source_text
    inventory = core_rules_order97_inventory.load_inventory()
    assert inventory.reviewed_commit == "8007555ef23e85c11d39b294acec02bd83fc3271"
    assert any(
        row.requirement_id == "18.07-post-placement-forced-fights" for row in inventory.requirements
    )


def test_v963_historical_mapping_rejects_missing_or_changed_archive(tmp_path: Path) -> None:
    root = v963_shock_source.ROOT
    mapping = json.loads((root / MAPPING).read_bytes())
    mapping_path = tmp_path / MAPPING
    mapping_path.parent.mkdir(parents=True)
    mapping_path.write_bytes((root / MAPPING).read_bytes())
    row = mapping["files"][0]
    with pytest.raises(FileNotFoundError):
        historical_evidence_path(row["path"], root=tmp_path)
    archived = tmp_path / row["historical_path"]
    archived.parent.mkdir(parents=True)
    archived.write_bytes((root / row["historical_path"]).read_bytes())
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == row["sha256"]
    assert historical_evidence_path(row["path"], root=tmp_path) == archived
    archived.write_bytes(archived.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="immutable historical input drifted"):
        historical_evidence_path(row["path"], root=tmp_path)


def test_v963_order95_retirement_keeps_old_proof_and_requires_current_controls(
    tmp_path: Path,
) -> None:
    reference = (
        "tests/unit/test_phase10q_transports.py::"
        "test_shock_disembark_routes_opponent_through_canonical_fight_activation_and_replay"
    )
    relative, _, symbol = reference.replace("::", ":").partition(":")
    historical = historical_evidence_path(relative, root=v963_shock_source.ROOT)
    assert historical is not None
    assert f"def {symbol}(" in historical.read_text()
    successors = RETIRED_REFERENCE_SUCCESSORS[reference]
    for successor in successors:
        path, _, _ = successor.replace("::", ":").partition(":")
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((v963_shock_source.ROOT / path).read_text())
    validate_owner_reference(reference, tmp_path)
    for successor in successors:
        path, _, current_symbol = successor.replace("::", ":").partition(":")
        target = tmp_path / path
        original = target.read_text()
        target.write_text(
            original.replace(f"def {current_symbol}(", f"def retired_{current_symbol}(")
        )
        with pytest.raises(ValueError, match="reference is absent"):
            validate_owner_reference(reference, tmp_path)
        target.write_text(original)
    old_target = tmp_path / relative
    old_target.parent.mkdir(parents=True, exist_ok=True)
    old_target.write_text(f"def {symbol}(): pass\n")
    with pytest.raises(ValueError, match="retired owner was reintroduced"):
        validate_owner_reference(reference, tmp_path)
