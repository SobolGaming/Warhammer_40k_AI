"""A current source observation cannot relabel or overwrite its predecessor."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.support import section08_native_mission_source as source
from tests.support.faction_batch01 import faction_definitions
from tests.support.section02_fixtures import Section02Definitions

ROOT = Path(__file__).resolve().parents[2]
__all__ = ("faction_definitions",)


def test_native_mission_current_mirror_crosswalk_keeps_exact_predecessor() -> None:
    row = source.validate_observation((ROOT / source.PATH).read_bytes())
    assert row["app_version"] == "995"
    assert row["identity_crosswalk"]["runtime_source_id"] == source.SOURCE_ID
    assert row["historical_lineage"]["bridge_ability_sha256"] == source.PREDECESSOR
    assert row["provider_owned_by_games_workshop"] is False
    assert (
        row["version_evidence"]["meaning"] == "current App-data snapshot; not last changed version"
    )


@pytest.mark.parametrize(
    "field", ["captured_text", "ability_text", "identity_crosswalk", "historical_lineage"]
)
def test_native_mission_source_pin_rejects_tamper(field: str) -> None:
    row = json.loads((ROOT / source.PATH).read_bytes())
    row[field] = "changed"
    with pytest.raises(ValueError, match="reviewed source observation changed"):
        source.validate_observation(json.dumps(row).encode())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("edition", "wrong-edition"),
        ("provider_name", "other-provider"),
        ("provider_owned_by_games_workshop", True),
        ("datasheet_id", "000004080"),
        ("app_version", "946"),
        ("url", "https://www.40k.app/factions/aeldari/units/tormentors"),
    ],
)
def test_native_mission_source_semantics_reject_even_a_blind_repin(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    row = json.loads((ROOT / source.PATH).read_bytes())
    row[field] = value
    raw = json.dumps(row).encode()
    monkeypatch.setattr(source, "SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="provider/edition/page ownership changed"):
        source.validate_observation(raw)


def test_native_mission_factory_changes_only_the_reviewed_ability_identity(
    faction_definitions: Section02Definitions,
) -> None:
    before = faction_definitions.package.to_payload()
    updated = source.source_backed_command_definitions(faction_definitions)
    sheet = faction_definitions.package.army_catalog.datasheet_by_id("000004079")
    current = updated.package.army_catalog.datasheet_by_id("000004079")
    row = source.validate_observation((ROOT / source.PATH).read_bytes())
    target = row["ability_id"]
    prior = next(a for a in sheet.abilities if a.ability_id == target)
    active = next(a for a in current.abilities if a.ability_id == target)
    assert replace(active, source_id=prior.source_id) == prior
    assert active.source_id == source.SOURCE_ID
    assert current.source_ids == tuple(
        sorted(
            {
                *sheet.source_ids,
                prior.source_id,
                source.SOURCE_ID,
                row["identity_crosswalk"]["page_source_id"],
            }
        )
    )
    assert replace(current, abilities=sheet.abilities, source_ids=sheet.source_ids) == sheet
    assert tuple(
        d for d in updated.package.army_catalog.datasheets if d.datasheet_id != sheet.datasheet_id
    ) == tuple(
        d
        for d in faction_definitions.package.army_catalog.datasheets
        if d.datasheet_id != sheet.datasheet_id
    )
    assert faction_definitions.package.to_payload() == before


def test_native_mission_factory_rejects_wrong_predecessor_identity(
    faction_definitions: Section02Definitions,
) -> None:
    package = faction_definitions.package
    sheet = package.army_catalog.datasheet_by_id("000004079")
    altered = replace(
        sheet,
        abilities=tuple(
            replace(a, source_id="wrong-edition:source")
            if a.ability_id == "000004079:objective-defiled"
            else a
            for a in sheet.abilities
        ),
    )
    catalog = replace(
        package.army_catalog,
        datasheets=tuple(
            altered if d.datasheet_id == sheet.datasheet_id else d
            for d in package.army_catalog.datasheets
        ),
    )
    definitions = replace(faction_definitions, package=replace(package, army_catalog=catalog))
    with pytest.raises(ValueError, match="predecessor identity or semantics changed"):
        source.source_backed_command_definitions(definitions)


def test_sticky_binding_accepts_authenticated_icon_predecessor_and_current() -> None:
    from tests.icon_provenance_helpers import before_icon_component
    from tests.source_history import historical_icon_component
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

    row = source.validate_observation((ROOT / source.PATH).read_bytes())
    current = historical_icon_component()
    previous = before_icon_component(current)
    source.validate_sticky_binding(previous, row)
    source.validate_sticky_binding(current, row)
    approved = faction_pack_rule_ir.source_package_artifact(source.PACKAGE)
    approved.validate_generated_artifact_bytes(json.dumps(approved.payload()).encode())
    with pytest.raises(faction_pack_rule_ir.FactionPackRuleIrRegistryError, match="registry pin"):
        approved.validate_generated_artifact_bytes(json.dumps(previous).encode())


@pytest.mark.parametrize(
    "mutation",
    [
        "package",
        "schema",
        "owner",
        "missing",
        "name",
        "text_hash",
        "source",
        "rule",
        "ir",
        "dependency",
        "document",
        "malformed",
    ],
)
def test_sticky_binding_rejects_selected_dependency_or_identity_drift(mutation: str) -> None:
    from tests.source_history import historical_icon_component

    component = historical_icon_component()
    row = json.loads((ROOT / source.PATH).read_bytes())
    record = component["records"]["000004079:3"]
    if mutation == "package":
        component["source_package_id"] += ":drift"
    elif mutation == "schema":
        component["artifact_schema"] += ":drift"
    elif mutation == "owner":
        component["datasheets"]["000004079"] = "Infractors"
    elif mutation == "missing":
        del component["records"]["000004079:3"]
    elif mutation == "name":
        record["ability_name"] += " drift"
    elif mutation == "text_hash":
        record["normalized_text_sha256"] = "0" * 64
    elif mutation == "source":
        record["rule_ir"]["source_id"] += ":drift"
    elif mutation == "rule":
        record["rule_ir"]["rule_id"] += ":drift"
    elif mutation == "ir":
        record["rule_ir"]["clauses"][0]["effects"][0]["parameters"][0]["value"] = "drift"
    elif mutation == "dependency":
        record["rule_ir"]["dependency_source_ids"] = ["unreviewed"]
    elif mutation == "document":
        component["official_document_sha256"] = "0" * 64
    else:
        component["records"] = []
    with pytest.raises(ValueError, match="complete Sticky record, ownership or source binding"):
        source.validate_sticky_binding(component, row)
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_pack_rule_ir._artifacts import (  # noqa: E501
        canonical_package_hash,
    )

    approved = faction_pack_rule_ir.source_package_artifact(source.PACKAGE)
    component["package_hash"] = canonical_package_hash(component)
    with pytest.raises(faction_pack_rule_ir.FactionPackRuleIrRegistryError):
        approved.validate_generated_artifact_bytes(json.dumps(component).encode())


@pytest.mark.parametrize(
    "field", ["source_snapshot_sha256", "source_artifact_hash", "overlay_package_hash"]
)
def test_current_component_loader_retains_broad_source_authentication(field: str) -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_pack_rule_ir._artifacts import (  # noqa: E501
        canonical_package_hash,
    )

    approved = faction_pack_rule_ir.source_package_artifact(source.PACKAGE)
    component = approved.payload()
    component[field] = "0" * 64
    component["package_hash"] = canonical_package_hash(component)
    with pytest.raises(faction_pack_rule_ir.FactionPackRuleIrRegistryError, match="registry pin"):
        approved.validate_generated_artifact_bytes(json.dumps(component).encode())


@pytest.mark.parametrize("mutation", ["payload", "manifest", "extra", "missing"])
def test_fixed_source_history_rejects_corruption_before_closure(
    tmp_path: Path, mutation: str
) -> None:
    import shutil

    from tests.source_history import HISTORY, validate_source_history

    target = tmp_path / "history"
    shutil.copytree(HISTORY, target)
    if mutation == "payload":
        path = target / "native.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "manifest":
        path = target / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "extra":
        (target / "unlisted.json").write_text("{}")
    else:
        (target / "paired.json").unlink()
    with pytest.raises(ValueError, match="Historical source roots"):
        validate_source_history(target)


def test_source_history_guard_precedes_index_and_covered_pytest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    step = workflow.split("- name: Run behavioral coverage shard", 1)[1].split(
        "- name: Upload shard test report", 1
    )[0]
    assert (
        step.index("scripts.validate_source_history")
        < step.index("tools.ability_support_sources")
        < step.index("--cov=warhammer40k_core")
    )
    assert "timeout-minutes: 12" in step


def test_source_history_rejects_optimized_interpreter() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-O", "-m", "scripts.validate_source_history"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "optimized Python is unsupported" in result.stderr
