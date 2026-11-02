from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any, cast

import msgspec
import pytest
from tools.core_deadly_demise_catalog_overlay import (
    SOURCE_ARTIFACT,
    SOURCE_ID,
    with_current_deadly_demise,
)
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.core_ability_materialization import _deadly_demise_source_for_model
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionSource,
    DestructionReactionSourcePayload,
)
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_abilities import (
    DeadlyDemiseAbilityProfile,
    deadly_demise_profiles_for_unit,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as daemons_roster,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_abilities_2026_09,
    court_of_slaughter_anvanth_2026_08,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.chaos_daemons_roster_2026_07 import (  # noqa: E501
    _current_source,
)


@cache
def _deadly_demise_delta_audit() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            Path(
                "data/source_audits/deadly_demise_2026_11/catalog-description-delta.json"
            ).read_bytes()
        ),
    )


@cache
def _current_deadly_demise_packages() -> tuple[CanonicalCatalogPackage, ...]:
    return (
        _ability_support_catalog_package(),
        court_of_slaughter_anvanth_2026_08.catalog_package(),
        daemons_roster.catalog_package(),
    )


def _historical_deadly_demise_package(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    return replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(
                            ability,
                            effect_description=_deadly_demise_delta_audit()["historical_text"],
                        )
                        if ability.ability_id == "000008339"
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in package.army_catalog.datasheets
            ),
            source_ids=tuple(
                source for source in package.army_catalog.source_ids if source != SOURCE_ID
            ),
        ),
        source_artifacts=tuple(
            artifact
            for artifact in package.source_artifacts
            if artifact.artifact_name
            not in {SOURCE_ARTIFACT.artifact_name, daemons_roster.CURRENT_SOURCE_ARTIFACT[0]}
        ),
    )


def test_deadly_demise_all_thirty_current_descriptions_preserve_entire_baseline_payloads() -> None:
    audit = _deadly_demise_delta_audit()
    total = 0
    owners: set[str] = set()
    for package, surface in zip(_current_deadly_demise_packages(), audit["surfaces"], strict=True):
        assert package.army_catalog.catalog_id == surface["catalog_id"]
        assert len(package.army_catalog.datasheets) == surface["total_datasheets"]
        rows = tuple(
            (datasheet.datasheet_id, ability)
            for datasheet in package.army_catalog.datasheets
            for ability in datasheet.abilities
            if ability.ability_id == "000008339"
        )
        assert len(rows) == surface["affected_count"]
        for (owner, ability), prior in zip(rows, surface["affected_occurrences"], strict=True):
            owners.add(owner)
            assert owner == prior["datasheet_id"]
            assert ability.source_id == prior["source_id"]
            assert ability.parameter_tokens == tuple(prior["parameter_tokens"])
            assert (
                ability.effect_description
                == core_abilities_2026_09.source_rule_record().source_text
            )
            assert hashlib.sha256(ability.effect_description.encode()).hexdigest() == (
                "a5ca19362fe04090968372fe83f3398cfa1236d52d69a2a87ad6ca555f429ff4"
            )
        total += len(rows)
        # Includes every unrelated field, ability, geometry, source identity and support flag.
        assert _historical_deadly_demise_package(package).package_hash() == surface["package_hash"]
        assert package.source_artifacts.count(SOURCE_ARTIFACT) == 1
        assert package.army_catalog.source_ids.count(SOURCE_ID) == 1
        assert CanonicalCatalogPackage.from_payload(package.to_payload()) == package
    assert total == 30
    assert len(owners) == 22


def test_deadly_demise_preserves_historical_artifact_bytes_and_original_validator() -> None:
    audit = _deadly_demise_delta_audit()
    for row in (*audit["immutable_inputs"], audit["historical_court_artifact"]):
        assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]
    current = daemons_roster.catalog_package()
    reconciliation = daemons_roster.reconciliation_manifest()
    daemons_roster.validate_catalog_against_reconciliation(
        catalog=_historical_deadly_demise_package(current).army_catalog,
        reconciliation=reconciliation,
    )
    with pytest.raises(
        daemons_roster.ChaosDaemonsRosterReconciliationError, match="gameplay payload"
    ):
        daemons_roster.validate_catalog_against_reconciliation(
            catalog=current.army_catalog, reconciliation=reconciliation
        )
    daemons_roster.validate_current_catalog_against_reconciliation(
        catalog=current.army_catalog, reconciliation=reconciliation
    )


def _mutate_deadly_demise(
    package: CanonicalCatalogPackage, mutation: str
) -> CanonicalCatalogPackage:
    target = next(
        row
        for row in package.army_catalog.datasheets
        if any(ability.ability_id == "000008339" for ability in row.abilities)
    )
    ability = next(row for row in target.abilities if row.ability_id == "000008339")
    if mutation == "text":
        changed = replace(ability, effect_description="Wrong current description.")
    elif mutation == "parameter":
        changed = replace(ability, parameter_tokens=("2",))
    elif mutation == "identity":
        changed = replace(ability, source_id=ability.source_id + ":unlisted")
    elif mutation == "kind":
        changed = replace(ability, source_kind=CatalogAbilitySourceKind.DATASHEET)
    elif mutation == "timing":
        changed = replace(ability, timing_tags=("after_unit_destroyed",))
    else:
        changed = ability
    abilities = tuple(changed if row is ability else row for row in target.abilities)
    if mutation == "missing":
        abilities = tuple(row for row in abilities if row.ability_id != "000008339")
    elif mutation == "duplicate":
        abilities = (*abilities, replace(ability, source_id=ability.source_id + ":duplicate"))
    elif mutation == "other_prose":
        other = next(row for row in abilities if row.ability_id != "000008339")
        abilities = tuple(
            replace(row, effect_description="Changed unrelated prose.") if row is other else row
            for row in abilities
        )
    updated = replace(target, abilities=abilities)
    if mutation == "gameplay":
        updated = replace(updated, name="Changed datasheet")
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
    "mutation", ["text", "parameter", "identity", "kind", "missing", "duplicate"]
)
def test_deadly_demise_current_adapter_rejects_unreviewed_inputs(mutation: str) -> None:
    historical = _historical_deadly_demise_package(_current_deadly_demise_packages()[0])
    with pytest.raises(ValueError, match="Deadly Demise"):
        with_current_deadly_demise(_mutate_deadly_demise(historical, mutation))


def test_deadly_demise_adapter_is_once_only_deterministic_and_noop_without_occurrences() -> None:
    current = _current_deadly_demise_packages()[0]
    historical = _historical_deadly_demise_package(current)
    assert with_current_deadly_demise(historical) == current
    assert with_current_deadly_demise(historical) == with_current_deadly_demise(historical)
    with pytest.raises(ValueError, match="already applied"):
        with_current_deadly_demise(current)
    unrelated = _ability_support_catalog_package(datasheet_ids=("000001115",))
    assert with_current_deadly_demise(unrelated) is unrelated


def test_deadly_demise_current_adapter_rejects_wrong_current_source_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical = _historical_deadly_demise_package(_current_deadly_demise_packages()[0])
    monkeypatch.setattr(core_abilities_2026_09, "EXPECTED_ARTIFACT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="source pin"):
        with_current_deadly_demise(historical)


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "parameter",
        "identity",
        "kind",
        "timing",
        "missing",
        "duplicate",
        "other_prose",
        "gameplay",
    ],
)
def test_deadly_demise_current_daemons_derivation_rejects_every_unlisted_delta(
    mutation: str,
) -> None:
    with pytest.raises(daemons_roster.ChaosDaemonsRosterReconciliationError):
        daemons_roster.validate_current_catalog_against_reconciliation(
            catalog=_mutate_deadly_demise(daemons_roster.catalog_package(), mutation).army_catalog,
            reconciliation=daemons_roster.reconciliation_manifest(),
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unlisted", "source_pin"])
def test_deadly_demise_derivation_manifest_rejects_altered_mapping(mutation: str) -> None:
    raw = package_artifact_bytes(daemons_roster.__name__, _current_source.ARTIFACT_PATH)
    payload = json.loads(raw)
    if mutation == "missing":
        payload["deltas"].pop()
    elif mutation == "duplicate":
        payload["deltas"].append(payload["deltas"][0])
    elif mutation == "unlisted":
        payload["deltas"][0]["datasheet_id"] = "000001115"
    else:
        payload["core_artifact_sha256"] = "0" * 64
    with pytest.raises(daemons_roster.ChaosDaemonsRosterReconciliationError, match="bytes drifted"):
        _current_source.current_source_from_json_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize(
    ("identity", "token", "damage"),
    [
        ("000000613", "1", {"kind": "fixed", "value": 1}),
        ("000000611", "D3", {"kind": "d3"}),
        ("000004077", "D6", {"kind": "d6"}),
    ],
)
def test_deadly_demise_description_preserves_native_profiles_and_typed_persistence(
    identity: str, token: str, damage: dict[str, Any]
) -> None:
    current = court_of_slaughter_anvanth_2026_08.catalog_package()
    results: list[
        tuple[tuple[DeadlyDemiseAbilityProfile, ...], DestructionReactionSourcePayload]
    ] = []
    for package in (_historical_deadly_demise_package(current), current):
        datasheet = package.army_catalog.datasheet_by_id(identity)
        unit = UnitFactory(
            catalog=package.army_catalog, model_geometries=package.model_geometries
        ).instantiate_unit(
            army_id="description-control",
            datasheet=datasheet,
            selection=UnitMusterSelection(
                unit_selection_id="selected-" + identity,
                datasheet_id=identity,
                model_profile_selections=(
                    ModelProfileSelection(datasheet.model_profiles[0].model_profile_id, 1),
                ),
            ),
        )
        restored = UnitInstance.from_payload(unit.to_payload())
        assert restored.to_payload() == unit.to_payload()
        profiles = deadly_demise_profiles_for_unit(unit)
        assert deadly_demise_profiles_for_unit(restored) == profiles
        assert tuple(profile.mortal_wounds_token for profile in profiles) == (token,)
        source = _deadly_demise_source_for_model(
            profile=profiles[0], model_instance_id=unit.own_models[0].model_instance_id
        )
        assert source.payload == {
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": damage,
        }
        assert DestructionReactionSource.from_payload(source.to_payload()) == source
        results.append((profiles, source.to_payload()))
    assert results[0] == results[1]


def test_deadly_demise_adapter_rejects_wrong_catalog_owner() -> None:
    historical = _historical_deadly_demise_package(_current_deadly_demise_packages()[0])
    wrong_owner = replace(
        historical,
        package_id=DataPackageId(namespace="core-v2", package_name="unreviewed", version="2026-11"),
    )
    with pytest.raises(ValueError, match="owner is unreviewed"):
        with_current_deadly_demise(wrong_owner)


def test_deadly_demise_adapter_rejects_wrong_current_source_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical = _historical_deadly_demise_package(_current_deadly_demise_packages()[0])
    rule = core_abilities_2026_09.source_rule_record()
    wrong_rule = msgspec.structs.replace(rule, source_text=rule.source_text + " Changed.")
    monkeypatch.setattr(core_abilities_2026_09, "source_rule_record", lambda: wrong_rule)
    with pytest.raises(ValueError, match="source pin"):
        with_current_deadly_demise(historical)


def test_deadly_demise_adapter_rejects_unlisted_occurrence() -> None:
    historical = _historical_deadly_demise_package(_current_deadly_demise_packages()[0])
    ability = next(
        ability
        for row in historical.army_catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == "000008339"
    )
    target = next(
        row
        for row in historical.army_catalog.datasheets
        if all(ability.ability_id != "000008339" for ability in row.abilities)
    )
    changed = replace(
        target, abilities=(*target.abilities, replace(ability, source_id="unlisted:deadly-demise"))
    )
    package = replace(
        historical,
        army_catalog=replace(
            historical.army_catalog,
            datasheets=tuple(
                changed if row is target else row for row in historical.army_catalog.datasheets
            ),
        ),
    )
    with pytest.raises(ValueError, match="occurrence closure"):
        with_current_deadly_demise(package)
