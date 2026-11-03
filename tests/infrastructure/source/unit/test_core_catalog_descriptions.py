from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any

import msgspec
import pytest
from tools.core_deadly_demise_catalog_overlay import with_current_core_descriptions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.core_description_helpers import (
    before_core_description_correction,
    before_mandiblasters_correction,
    core_description_audit,
)
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetCatalogError,
)
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView
from warhammer40k_core.engine.stealth import (
    native_stealth_model_sources,
    rules_unit_has_native_stealth,
)
from warhammer40k_core.engine.unit_abilities import (
    LoneOperativeAbilityProfile,
    lone_operative_profile_for_unit,
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
    unit_has_fights_first,
    unit_has_infiltrators,
    unit_has_lone_operative,
    unit_has_scouts,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.source_evidence import (
    RuleEvidenceError,
    RuleEvidenceRecord,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07,
    core_fights_first_2026_09,
    core_stealth_2026_09,
    court_of_slaughter_anvanth_2026_08,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_descriptions_2026_11 as source,
)


@cache
def _packages() -> tuple[CanonicalCatalogPackage, ...]:
    return (
        _ability_support_catalog_package(),
        court_of_slaughter_anvanth_2026_08.catalog_package(),
        chaos_daemons_roster_2026_07.catalog_package(),
    )


def test_all_39_occurrences_close_35_replacements_and_four_preserved_stealth() -> None:
    audit = core_description_audit()
    changed = preserved = total = 0
    owners: set[str] = set()
    for package, surface in zip(_packages(), audit["surfaces"], strict=True):
        before = before_core_description_correction(package)
        for occurrence in surface["occurrences"]:
            owner = occurrence["datasheet_id"]
            owners.add(owner)
            old = occurrence["descriptor"]
            current = next(
                ability
                for ability in package.army_catalog.datasheet_by_id(owner).abilities
                if ability.ability_id == old["ability_id"]
            )
            changed += current.effect_description != old["effect_description"]
            preserved += current.effect_description == old["effect_description"]
            total += 1
        assert before.package_hash() == surface["package_hash"]
        assert CanonicalCatalogPackage.from_payload(package.to_payload()) == package
    assert (total, changed, preserved, len(owners)) == (39, 35, 4, 18)
    assert (
        _packages()[2].package_hash()
        == "b63c0805b6878daf2eef2d4145e407361f7848bde3095074022f1b850db183ab"
    )


def _mutate(package: CanonicalCatalogPackage, mutation: str) -> CanonicalCatalogPackage:
    target = package.army_catalog.datasheet_by_id("000000595")
    ability = next(row for row in target.abilities if row.ability_id == "000008344")
    if mutation == "text":
        changed = replace(ability, effect_description=ability.effect_description + " Drift.")
    elif mutation == "identity":
        changed = replace(ability, source_id=ability.source_id + ":drift")
    elif mutation == "id":
        changed = replace(ability, ability_id="unreviewed")
    elif mutation == "kind":
        changed = replace(ability, source_kind=CatalogAbilitySourceKind.DATASHEET)
    elif mutation == "parameter":
        changed = replace(ability, parameter_tokens=("6",))
    elif mutation == "timing":
        changed = replace(ability, timing_tags=("before_battle",))
    elif mutation == "support":
        changed = replace(ability, support=CatalogAbilitySupport.UNSUPPORTED)
    elif mutation == "wargear":
        changed = replace(
            ability, source_kind=CatalogAbilitySourceKind.WARGEAR, source_wargear_id="drift-wargear"
        )
    elif mutation == "rule_ir":
        changed = replace(ability, rule_ir_payload={"drift": True})
    elif mutation == "diagnostics":
        changed = replace(ability, rule_ir_diagnostics=({"drift": True},))
    elif mutation == "name":
        changed = replace(ability, name="Drift")
    else:
        changed = ability
    abilities = tuple(changed if row is ability else row for row in target.abilities)
    if mutation == "missing":
        abilities = tuple(row for row in abilities if row is not ability)
    elif mutation == "duplicate":
        abilities = (*abilities, replace(ability, source_id=ability.source_id + ":duplicate"))
    elif mutation == "other_prose":
        other = next(
            row for row in abilities if row.source_kind is not CatalogAbilitySourceKind.CORE
        )
        abilities = tuple(
            replace(row, effect_description="Unrelated drift.") if row is other else row
            for row in abilities
        )
    updated = replace(target, abilities=abilities)
    if mutation == "gameplay":
        updated = replace(updated, name="Unrelated datasheet change")
    return replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(
                updated if row is target else row for row in package.army_catalog.datasheets
            ),
        ),
    )


@pytest.mark.parametrize(
    "mutation", ["text", "identity", "id", "kind", "parameter", "missing", "duplicate"]
)
def test_adapter_rejects_wrong_reviewed_input(mutation: str) -> None:
    historical = before_core_description_correction(_packages()[0])
    with pytest.raises(ValueError, match="Core description"):
        with_current_core_descriptions(_mutate(historical, mutation))


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "identity",
        "id",
        "kind",
        "parameter",
        "timing",
        "name",
        "support",
        "wargear",
        "rule_ir",
        "diagnostics",
        "missing",
        "duplicate",
        "other_prose",
        "gameplay",
    ],
)
def test_historical_projection_authenticates_all_payload_fields(mutation: str) -> None:
    with pytest.raises((AssertionError, KeyError)):
        before_core_description_correction(_mutate(_packages()[0], mutation))


def test_adapter_once_only_deterministic_absent_noop_and_wrong_owner() -> None:
    current = _packages()[0]
    before = before_core_description_correction(current)
    assert with_current_core_descriptions(before) == before_mandiblasters_correction(current)
    assert with_current_core_descriptions(before) == with_current_core_descriptions(before)
    with pytest.raises(ValueError, match="already applied"):
        with_current_core_descriptions(current)
    empty = _ability_support_catalog_package(datasheet_ids=("000001115",))
    assert with_current_core_descriptions(empty) is empty
    with pytest.raises(ValueError, match="owner is unreviewed"):
        with_current_core_descriptions(
            replace(
                before,
                package_id=DataPackageId(
                    namespace="core-v2", package_name="unreviewed", version="2026-11"
                ),
            )
        )


@pytest.mark.parametrize("module", [source, core_stealth_2026_09, core_fights_first_2026_09])
def test_adapter_rejects_wrong_source_pin(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    historical = before_core_description_correction(_packages()[0])
    monkeypatch.setattr(module, "EXPECTED_ARTIFACT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="source pin"):
        with_current_core_descriptions(historical)


def test_adapter_rejects_current_source_text_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    historical = before_core_description_correction(_packages()[0])
    rules = source.source_rules()
    monkeypatch.setattr(
        source,
        "source_rules",
        lambda: (msgspec.structs.replace(rules[0], source_text="Drift"), *rules[1:]),
    )
    with pytest.raises(ValueError, match="source pin"):
        with_current_core_descriptions(historical)


@pytest.mark.parametrize(
    "mutation", ["truncated", "text", "source", "missing", "duplicate", "status", "dependency"]
)
def test_new_source_rejects_unreviewed_artifact_bytes(mutation: str) -> None:
    raw = package_artifact_bytes(source.__name__, "artifacts/package.json")
    payload = json.loads(raw)
    if mutation == "truncated":
        raw = raw[:-10]
    else:
        if mutation == "text":
            payload["rules"][0]["source_text"] = "Truncated rule."
        elif mutation == "source":
            payload["rules"][0]["source_id"] = "wrong-source"
        elif mutation == "missing":
            payload["rules"].pop()
        elif mutation == "duplicate":
            payload["rules"].append(payload["rules"][0])
        elif mutation == "status":
            payload["rules"][0]["semantic_execution_status"] = "executable_engine_runtime"
        else:
            payload["rules"][2]["dependency_source_ids"] = []
        raw = json.dumps(payload).encode()
    with pytest.raises(source.CoreDescriptionSourceError, match="bytes drifted"):
        source.validate_source_artifact_bytes(raw)


@pytest.mark.parametrize(
    "field",
    [
        "provider_name",
        "project_authority_policy_id",
        "observed_at",
        "review_audit_source_observation_sha256",
        "rule_source_id",
    ],
)
def test_new_source_rejects_wrong_governed_tuple(field: str) -> None:
    payload = dict(source.source_evidence_records()[1].to_payload())
    payload[field] = (
        "2026-11-04T00:00:00Z"
        if field == "observed_at"
        else ("0" * 64 if "sha256" in field else "wrong")
    )
    payload["observation_sha256"] = hashlib.sha256(
        json.dumps(
            {**payload, "observation_sha256": "", "load_support_status": "not_loaded"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(RuleEvidenceError):
        replace(
            source.source_package(),
            source_evidence_catalog=SourceEvidenceCatalog(
                records=(
                    source.source_evidence_records()[0],
                    RuleEvidenceRecord.from_payload(payload),
                    *source.source_evidence_records()[2:],
                )
            ),
        )


def test_source_admission_truth_and_complete_scouts_dependency() -> None:
    package = source.source_package()
    assert len(package.source_catalog.documents[0].source_texts) == 4
    for rule, evidence in zip(
        source.source_rules(), source.source_evidence_records()[1::2], strict=True
    ):
        assert (
            rule.load_support_status,
            rule.semantic_execution_status,
            rule.runtime_consumer_ids,
        ) == ("loaded", "not_certified", ())
        assert evidence.authority == "project_authoritative_app_mirror"
        assert evidence.app_build is evidence.app_version is evidence.capture_sha256 is None
        assert evidence.observed_at == "2026-11-03T01:12:44.736Z"
        assert (
            hashlib.sha256(rule.source_text.encode()).hexdigest() == evidence.transcription_sha256
        )
    scouts = source.source_rules()[2]
    assert scouts.dependency_source_ids == (source.SCOUT_MOVE_SOURCE_ID,)
    assert "strategic reserves" in scouts.source_text
    assert "DEDICATED TRANSPORT" in scouts.source_text
    assert 'more than 8"' in source.source_rules()[3].source_text
    audit = core_description_audit()
    ff = next(row for row in audit["wording"] if row["family"] == "Fights First")
    assert "12.04" in ff["current_app_major_text"]
    assert "12.04" not in ff["proposed_description"]


@pytest.mark.parametrize(
    ("identity", "distance"), [("000000595", 7.0), ("000000612", 9.0), ("000004080", 6.0)]
)
def test_scouts_parameters_and_native_factory_persistence_are_preserved(
    identity: str, distance: float
) -> None:
    current = _packages()[0]
    results: list[tuple[tuple[str, tuple[str, ...]], ...]] = []
    for package in (before_core_description_correction(current), current):
        datasheet = package.army_catalog.datasheet_by_id(identity)
        unit = UnitFactory(
            catalog=package.army_catalog, model_geometries=package.model_geometries
        ).instantiate_unit(
            army_id="description-control",
            datasheet=datasheet,
            selection=UnitMusterSelection(
                unit_selection_id="selected-" + identity,
                datasheet_id=identity,
                model_profile_selections=tuple(
                    ModelProfileSelection(part.model_profile_id, part.min_models)
                    for part in datasheet.composition
                    if part.min_models > 0
                ),
            ),
        )
        restored = UnitInstance.from_payload(unit.to_payload())
        assert restored.to_payload() == unit.to_payload()
        assert unit_has_scouts(unit)
        assert unit_has_scouts(restored)
        descriptors = scouts_ability_descriptors_for_unit(unit)
        assert tuple(scouts_distance_inches_from_descriptor(row) for row in descriptors) == (
            distance,
        )
        results.append(tuple((row.source_id, row.parameter_tokens) for row in descriptors))
    assert results[0] == results[1]


@pytest.mark.parametrize("identity", ["000000592", "000000594", "000002538"])
def test_other_core_recognition_and_lone_operative_identity_are_preserved(identity: str) -> None:
    current = _packages()[0]
    results: list[
        tuple[
            tuple[bool, bool, bool, LoneOperativeAbilityProfile | None],
            dict[str, tuple[str, ...]],
        ]
    ] = []
    for package in (before_core_description_correction(current), current):
        datasheet = package.army_catalog.datasheet_by_id(identity)
        unit = UnitFactory(
            catalog=package.army_catalog, model_geometries=package.model_geometries
        ).instantiate_unit(
            army_id="description-control",
            datasheet=datasheet,
            selection=UnitMusterSelection(
                unit_selection_id="selected-" + identity,
                datasheet_id=identity,
                model_profile_selections=tuple(
                    ModelProfileSelection(part.model_profile_id, part.min_models)
                    for part in datasheet.composition
                    if part.min_models > 0
                ),
            ),
        )
        restored = UnitInstance.from_payload(unit.to_payload())
        assert restored.to_payload() == unit.to_payload()
        result = (
            unit_has_infiltrators(unit),
            unit_has_fights_first(unit),
            unit_has_lone_operative(unit),
            lone_operative_profile_for_unit(unit),
        )
        assert any(result[:3])
        view = RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id="player-a",
            components=(RulesUnitComponent(unit=unit, role="unit"),),
        )
        native = native_stealth_model_sources(view)
        assert set(native) == {model.model_instance_id for model in unit.own_models}
        if identity == "000000592":
            assert rules_unit_has_native_stealth(view)
            assert all(native.values())
        results.append((result, native))
    assert results[0] == results[1]


def test_adapter_rejects_unreviewed_owner_occurrence() -> None:
    before = before_core_description_correction(_packages()[0])
    ability = next(
        row
        for row in before.army_catalog.datasheet_by_id("000000595").abilities
        if row.ability_id == "000008344"
    )
    owner = before.army_catalog.datasheet_by_id("000001115")
    changed = replace(
        owner, abilities=(*owner.abilities, replace(ability, source_id="unreviewed:scouts"))
    )
    package = replace(
        before,
        army_catalog=replace(
            before.army_catalog,
            datasheets=tuple(
                changed if row is owner else row for row in before.army_catalog.datasheets
            ),
        ),
    )
    with pytest.raises(ValueError, match="occurrence closure"):
        with_current_core_descriptions(package)


def test_new_source_rejects_conflicting_same_observation_transcription() -> None:
    records = source.source_evidence_records()
    payload = dict(records[1].to_payload())
    payload["evidence_id"] = "conflicting-same-observation"
    payload["transcription_sha256"] = hashlib.sha256(b"Conflicting complete text.").hexdigest()
    payload["observation_sha256"] = hashlib.sha256(
        json.dumps(
            {**payload, "observation_sha256": "", "load_support_status": "not_loaded"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    conflicting = RuleEvidenceRecord.from_payload(payload)
    with pytest.raises(RuleEvidenceError):
        replace(
            source.source_package(),
            source_evidence_catalog=SourceEvidenceCatalog(records=(*records, conflicting)),
        )


def test_source_registry_keeps_every_historical_registration_and_source_byte() -> None:
    root = Path(__file__).resolve().parents[4]
    base = "b27c5d4e5f75dd7f89353a968a88d1b24b2681a4"
    registry_path = "src/warhammer40k_core/rules/source_authority_registry.json"
    prior = json.loads(
        subprocess.check_output(["git", "show", base + ":" + registry_path], cwd=root)
    )
    current = json.loads((root / registry_path).read_bytes())
    assert current["scopes"][1:] == prior["scopes"][1:]
    old_scope, new_scope = prior["scopes"][0], current["scopes"][0]
    for field, value in old_scope.items():
        if field in {"audit_rows", "source_package_extensions"}:
            assert new_scope[field][: len(value)] == value
        else:
            assert new_scope[field] == value
    assert len(new_scope["audit_rows"]) - len(old_scope["audit_rows"]) == 4
    assert (
        len(new_scope["source_package_extensions"]) - len(old_scope["source_package_extensions"])
        == 1
    )
    for module in (core_stealth_2026_09, core_fights_first_2026_09):
        module_file = module.__file__
        assert module_file is not None
        artifact = Path(module_file).parent / "artifacts/package.json"
        historical = subprocess.check_output(
            ["git", "show", base + ":" + artifact.relative_to(root).as_posix()], cwd=root
        )
        assert artifact.read_bytes() == historical


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "identity",
        "rule_ir",
        "gate",
        "missing",
        "duplicate",
        "artifact",
        "other_artifact",
        "other_descriptor",
    ],
)
def test_mandiblasters_successor_projection_rejects_unreviewed_bytes(mutation: str) -> None:
    from copy import deepcopy

    package = _packages()[0]
    owner = package.army_catalog.datasheet_by_id("000000595")
    ability = next(a for a in owner.abilities if a.ability_id == "000000595:mandiblasters")
    changed = ability
    if mutation == "text":
        changed = replace(ability, effect_description=ability.effect_description + " Drift.")
    elif mutation == "identity":
        changed = replace(ability, source_id=ability.source_id + ":drift")
    elif mutation in {"rule_ir", "gate"}:
        payload = deepcopy(ability.rule_ir_payload)
        assert payload is not None
        if mutation == "rule_ir":
            payload["ir_hash"] = "0" * 64
        else:
            from typing import cast

            raw = cast(dict[str, Any], payload)
            raw["clauses"][0]["effects"][0]["parameters"] = [
                p
                for p in raw["clauses"][0]["effects"][0]["parameters"]
                if p["key"] != "requires_charge_move_this_turn"
            ]
        changed = replace(ability, rule_ir_payload=payload)
    abilities = tuple(changed if a is ability else a for a in owner.abilities)
    if mutation == "missing":
        abilities = tuple(a for a in abilities if a is not ability)
    elif mutation == "duplicate":
        abilities = (*abilities, replace(ability, source_id=ability.source_id + ":duplicate"))
        # The real typed catalog rejects this malformed duplicate before a
        # package can reach the historical projection. Preserve that boundary.
        with pytest.raises(DatasheetCatalogError, match="duplicate ability IDs"):
            replace(owner, abilities=abilities)
        return
    package = replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(
                replace(row, abilities=abilities) if row is owner else row
                for row in package.army_catalog.datasheets
            ),
        ),
    )
    if mutation in {"artifact", "other_artifact"}:
        target = next(
            a
            for a in package.source_artifacts
            if (a.artifact_name == "Datasheets_abilities.json") is (mutation == "artifact")
        )
        package = replace(
            package,
            source_artifacts=tuple(
                replace(a, artifact_hash="0" * 64) if a is target else a
                for a in package.source_artifacts
            ),
        )
    elif mutation == "other_descriptor":
        package = _mutate(package, "gameplay")
    with pytest.raises(AssertionError):
        before_core_description_correction(package)
