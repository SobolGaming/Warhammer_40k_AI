"""Bounded current source corrections: canonical keyword and complete Core prose."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from tools.ability_support_sources import ability_support_index_inputs, load_ability_support_sources
from tools.core_deep_strike_catalog_overlay import with_current_deep_strike
from tools.generate_ability_support_matrix import (
    DEFAULT_SOURCE_JSON_DIR,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.abilities import KeywordGate
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_keyword_queries import (
    unit_datasheet_name_keywords,
    unit_has_keyword,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.core_deep_strike_successor import (
    ABILITY_ID,
    CURRENT_TEXT,
    before_deep_strike_catalog,
)
from warhammer40k_core.rules.faction_source_governance import FactionSourceError
from warhammer40k_core.rules.source_evidence import RuleEvidenceError
from warhammer40k_core.rules.source_overlay import SourceOverlayError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as daemons,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_deep_strike_description_2026_11 as source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    court_of_slaughter_anvanth_2026_08 as paired,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    starfang_keyword_2026_11 as starfang,
)


@cache
def packages() -> tuple[CanonicalCatalogPackage, ...]:
    return (_ability_support_catalog_package(), paired.catalog_package(), daemons.catalog_package())


@pytest.mark.parametrize("count", [1, 2])
def test_starfang_native_canonical_keyword_retains_plural_name_and_roundtrip(count: int) -> None:
    package = packages()[0]
    datasheet = package.army_catalog.datasheet_by_id("000004195")
    assert datasheet.name == "Starfangs"
    assert "STARFANG" in datasheet.keywords.keywords
    assert "STARFANGS" not in datasheet.keywords.keywords
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    unit = factory.instantiate_unit(
        army_id="source-correction",
        selection=UnitMusterSelection(
            unit_selection_id="starfangs",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(ModelProfileSelection("000004195:starfangs", count),),
        ),
        datasheet=datasheet,
    )
    assert len(unit.own_models) == count
    for model in unit.own_models:
        assignment = model.keyword_assignment
        assert assignment.name_keyword == "STARFANGS"
        assert assignment.name_is_ordinary_keyword is False
        assert "STARFANG" in model.keywords
    for query in ("STARFANG", "Starfang", "STARFANGS", "Starfangs"):
        assert unit_has_keyword(unit, query)
        assert KeywordGate(required_keywords=(query,)).matches(
            unit.keywords, name_keywords=unit_datasheet_name_keywords(unit)
        )
    assert not unit_has_keyword(unit, "VYPERS")
    assert not KeywordGate(required_keywords=("STARFANG",)).matches(("VEHICLE", "VYPERS"))
    restored = UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload())))
    assert restored.to_payload() == unit.to_payload()
    assert unit_has_keyword(restored, "STARFANG")
    assert unit_has_keyword(restored, "STARFANGS")


def test_three_surfaces_exact_28_complete_descriptions_and_catalog_roundtrip() -> None:
    counts: list[int] = []
    owners: set[str] = set()
    for package in packages():
        before = before_deep_strike_catalog(package.army_catalog)
        occurrences = [
            (row.datasheet_id, a)
            for row in package.army_catalog.datasheets
            for a in row.abilities
            if a.ability_id == ABILITY_ID
        ]
        counts.append(len(occurrences))
        owners.update(owner for owner, _ in occurrences)
        for owner, ability in occurrences:
            assert ability.effect_description == CURRENT_TEXT
            assert ability.parameter_tokens == ()
            prior = next(
                a for a in before.datasheet_by_id(owner).abilities if a.ability_id == ABILITY_ID
            )
            assert {
                **prior.to_payload(),
                "effect_description": CURRENT_TEXT,
            } == ability.to_payload()
        assert (
            CanonicalCatalogPackage.from_payload(json.loads(json.dumps(package.to_payload())))
            == package
        )
    assert counts == [17, 6, 5]
    assert len(owners) == 17


@pytest.mark.parametrize(
    "mutation", ["description", "parameters", "source", "missing", "duplicate"]
)
def test_exact_deep_strike_successor_rejects_unreviewed_delta(mutation: str) -> None:
    catalog = packages()[2].army_catalog
    row = catalog.datasheets[0]
    ability = next(a for a in row.abilities if a.ability_id == ABILITY_ID)
    changed = ability
    if mutation == "description":
        changed = replace(ability, effect_description=ability.effect_description + " Drift.")
    elif mutation == "parameters":
        changed = replace(ability, parameter_tokens=("1",))
    elif mutation == "source":
        changed = replace(ability, source_id=ability.source_id + ":drift")
    abilities = tuple(changed if a is ability else a for a in row.abilities)
    if mutation == "missing":
        abilities = tuple(a for a in abilities if a is not ability)
    elif mutation == "duplicate":
        # A duplicated reviewed occurrence on another real owner must fail closure.
        other = catalog.datasheets[1]
        catalog = replace(
            catalog,
            datasheets=(
                row,
                replace(
                    other,
                    abilities=(
                        *other.abilities,
                        replace(ability, source_id=ability.source_id + ":duplicate"),
                    ),
                ),
                *catalog.datasheets[2:],
            ),
        )
    else:
        catalog = replace(
            catalog, datasheets=(replace(row, abilities=abilities), *catalog.datasheets[1:])
        )
    if mutation == "missing":
        catalog = replace(
            catalog, datasheets=(replace(row, abilities=abilities), *catalog.datasheets[1:])
        )
    with pytest.raises(ValueError, match="Deep Strike successor"):
        before_deep_strike_catalog(catalog)


def test_source_only_admission_and_complete_dependency() -> None:
    (rule,) = source.source_rules()
    assert rule.source_id == "gw-11e-core-abilities:core:deep-strike"
    assert rule.source_text == CURRENT_TEXT
    assert rule.dependency_source_ids == ("gw-11e-core-reserve-lifetimes:ingress",)
    assert (
        rule.load_support_status,
        rule.semantic_execution_status,
        rule.runtime_consumer_ids,
    ) == ("loaded", "not_certified", ())
    assert (
        source.source_package().source_catalog.source_text_by_id(rule.source_id).raw_text
        == CURRENT_TEXT
    )
    assert (
        starfang.source_package()
        .source_catalog.source_text_by_id("faction-app:aeldari:datasheet:starfangs")
        .raw_text
        == starfang.source_audit().observations[0].operative_text
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_name", "unreviewed"),
        ("source_url", "https://www.40k.app/rules/20-strategic-reserves"),
        ("observed_at", "2026-11-02T17:17:33.254Z"),
        ("transcription_sha256", "0" * 64),
        ("review_audit_source_observation_sha256", "0" * 64),
    ],
)
def test_new_source_authority_tuple_fails_closed(field: str, value: str) -> None:
    record = next(r for r in source.source_evidence_records() if r.provider_name == "40k.app")
    changes: dict[str, Any] = {field: value}
    with pytest.raises(RuleEvidenceError):
        replace(record, **changes)


@pytest.mark.parametrize("which", ["core", "keyword", "overlay"])
def test_new_source_bytes_are_immutable(which: str) -> None:
    if which == "core":
        raw = Path(source.__file__).with_name("artifacts").joinpath("package.json").read_bytes()
        with pytest.raises(source.CoreDescriptionSourceError):
            source.validate_source_artifact_bytes(raw + b" ")
    elif which == "keyword":
        raw = Path(starfang.__file__).with_name(starfang.AUDIT_ARTIFACT_NAME).read_bytes()
        with pytest.raises(FactionSourceError):
            starfang.source_audit_from_json_bytes(raw + b" ")
    else:
        raw = Path(starfang.__file__).with_name(starfang.ARTIFACT_NAME).read_bytes()
        with pytest.raises(SourceOverlayError):
            starfang.overlay_pack_from_json_bytes(raw + b" ")


def test_keyword_overlay_explicit_identity_lineage_and_index_inputs() -> None:
    pack = starfang.overlay_pack()
    retire, add = pack.operations
    assert retire.source_row_id == "000004195:Starfangs:global:false:15639"
    assert (
        retire.expected_preimage_hash
        == "055b20e2b17f63cd0abb28aef0691b11ffb99c7f11df66f68298ac5018582aac"
    )
    assert add.source_row_id == "000004195:Starfang:global:false:15639"
    assert add.order_index == 15637
    assert add.expected_preimage_hash is None
    assert dict(add.fields) == {
        "datasheet_id": "000004195",
        "is_faction_keyword": "false",
        "keyword": "Starfang",
        "model": "",
    }
    inputs = ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR)
    assert Path(starfang.__file__).with_name(starfang.ARTIFACT_NAME) in inputs
    assert Path(starfang.__file__).with_name(starfang.AUDIT_ARTIFACT_NAME) in inputs


def test_exact_three_surface_delta_reconstructs_all_original_payload_hashes() -> None:
    from tests.starfang_deep_strike_helpers import before_starfang_deep_strike, correction_audit

    for package, surface in zip(packages(), correction_audit()["surfaces"], strict=True):
        assert before_starfang_deep_strike(package).package_hash() == surface["prior_package_hash"]


def test_selected_source_index_preserves_corrected_keyword_identity(tmp_path: Path) -> None:
    from warhammer40k_core.rules.selected_source_index import build_selected_source_index

    directory = tmp_path / "source-index"
    build_selected_source_index(
        directory,
        input_files=ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR),
        load_sources=lambda: load_ability_support_sources(DEFAULT_SOURCE_JSON_DIR),
    )
    selected = ("000004195", "000000600", "000000599", "000000598", "000000613")
    ordinary = _ability_support_catalog_package(datasheet_ids=selected)
    indexed = _ability_support_catalog_package(datasheet_ids=selected, source_index_dir=directory)
    assert indexed.to_payload() == ordinary.to_payload()
    assert "STARFANG" in indexed.army_catalog.datasheet_by_id("000004195").keywords.keywords
    assert "FRAME" in indexed.army_catalog.datasheet_by_id("000000599").keywords.keywords


def test_deep_strike_forward_is_exact_deterministic_and_once_only() -> None:
    from tests.starfang_deep_strike_helpers import before_starfang_deep_strike

    current = packages()[2]
    prior = before_starfang_deep_strike(current)
    assert with_current_deep_strike(prior) == current
    assert with_current_deep_strike(prior) == with_current_deep_strike(prior)
    with pytest.raises(ValueError, match="already applied"):
        with_current_deep_strike(current)
    empty = _ability_support_catalog_package(datasheet_ids=("000004195",))
    assert with_current_deep_strike(empty) is empty
    owner = replace(prior, army_catalog=replace(prior.army_catalog, catalog_id="unreviewed"))
    with pytest.raises(ValueError, match="owner is unreviewed"):
        with_current_deep_strike(owner)


@pytest.mark.parametrize("mutation", ["text", "parameters", "source", "missing"])
def test_forward_deep_strike_boundary_rejects_unreviewed_inputs(mutation: str) -> None:
    from tests.starfang_deep_strike_helpers import before_starfang_deep_strike

    prior = before_starfang_deep_strike(packages()[2])
    owner = prior.army_catalog.datasheets[0]
    ability = next(a for a in owner.abilities if a.ability_id == ABILITY_ID)
    changed = ability
    if mutation == "text":
        changed = replace(ability, effect_description=ability.effect_description + " Drift.")
    elif mutation == "parameters":
        changed = replace(ability, parameter_tokens=("1",))
    elif mutation == "source":
        changed = replace(ability, source_id=ability.source_id + ":drift")
    abilities = tuple(
        changed if a is ability else a
        for a in owner.abilities
        if mutation != "missing" or a is not ability
    )
    catalog = replace(
        prior.army_catalog,
        datasheets=(replace(owner, abilities=abilities), *prior.army_catalog.datasheets[1:]),
    )
    with pytest.raises(ValueError, match="Deep Strike reviewed"):
        with_current_deep_strike(replace(prior, army_catalog=catalog))


def test_keyword_source_supersedes_exact_history_and_rejects_identity_rewrite() -> None:
    from tools.ability_support_sources import load_source_artifacts

    from warhammer40k_core.rules.source_overlay import (
        SourceOverlayOperationKind,
        apply_source_release_overlays,
    )

    artifacts = load_source_artifacts(DEFAULT_SOURCE_JSON_DIR)
    pack = starfang.overlay_pack()
    table = next(a for a in artifacts if a.source_table == "Datasheets_keywords")
    old = next(r for r in table.rows if r.source_row_id == pack.operations[0].source_row_id)
    overlaid = apply_source_release_overlays(
        source_artifacts=artifacts,
        release_manifest=starfang.source_release_manifest(),
        overlay_packs=(pack,),
    )
    current = next(a for a in overlaid if a.source_table == "Datasheets_keywords")
    retired = next(r for r in current.rows if r.source_row_id == old.source_row_id)
    assert retired.runtime_fields_payload()["keyword"] == "Starfangs"
    assert retired.runtime_fields_payload()["core_v2_superseded_by"] == pack.operations[0].op_id
    successor = next(r for r in current.rows if r.source_row_id == pack.operations[1].source_row_id)
    assert successor.runtime_fields_payload() == dict(pack.operations[1].fields)
    assert successor.source_package_id == old.source_package_id
    update = replace(
        pack.operations[0],
        operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
        fields=(("keyword", "Starfang"),),
    )
    with pytest.raises(SourceOverlayError, match="changed source row identity"):
        apply_source_release_overlays(
            source_artifacts=artifacts,
            release_manifest=starfang.source_release_manifest(),
            overlay_packs=(replace(pack, operations=(update,)),),
        )
    stale = replace(
        pack,
        operations=(
            replace(pack.operations[0], expected_preimage_hash="0" * 64),
            pack.operations[1],
        ),
    )
    with pytest.raises(SourceOverlayError, match="target_drift"):
        apply_source_release_overlays(
            source_artifacts=artifacts,
            release_manifest=starfang.source_release_manifest(),
            overlay_packs=(stale,),
        )


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_current_deep_strike_preserves_native_8_inch_unrestricted_placement_policy(
    round_number: int,
) -> None:
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.ingress_placement_restrictions import restrictions_for_arrival

    policy = restrictions_for_arrival(
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        battle_round=round_number,
        strategic_rule=None,
        deep_strike_enemy_distance=None,
        source_restrictions=(),
        distance_grants=(),
    )
    assert policy.enemy_distance_inches == 8
    assert policy.edge_distance_inches is None
    assert policy.excludes_enemy_deployment_zone is False


def test_package_owned_successor_artifact_is_typed_pinned_and_complete() -> None:
    from warhammer40k_core.rules.core_deep_strike_successor import successor_from_json_bytes

    raw = Path(source.__file__).parent.joinpath("artifacts/catalog-successor.json").read_bytes()
    artifact = successor_from_json_bytes(raw)
    assert len(artifact.occurrences) == 28
    assert len({row.datasheet_id for row in artifact.occurrences}) == 17
    assert artifact.current_text == CURRENT_TEXT
    with pytest.raises(ValueError, match="successor artifact bytes"):
        successor_from_json_bytes(raw + b" ")


@pytest.mark.parametrize(
    ("datasheet_id", "expected"), [("000000599", True), ("000000598", False), ("000000613", False)]
)
def test_wave_serpent_frame_native_factory_roundtrip_and_measurement_selector(
    datasheet_id: str, expected: bool
) -> None:
    from warhammer40k_core.engine.battlefield_state import geometry_model_at_pose
    from warhammer40k_core.geometry.pose import Pose

    package = packages()[0]
    sheet = package.army_catalog.datasheet_by_id(datasheet_id)
    assert ("FRAME" in sheet.keywords.keywords) is expected
    assert sheet.keywords.faction_keywords == ("ASURYANI",)
    if expected:
        assert sheet.keywords.keywords == (
            "AELDARI",
            "DEDICATED TRANSPORT",
            "FLY",
            "FRAME",
            "TRANSPORT",
            "VEHICLE",
            "WAVE SERPENT",
        )
    profile = sheet.composition[0]
    selection = UnitMusterSelection(
        unit_selection_id="frame-source-" + datasheet_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(profile.model_profile_id, profile.min_models),
        ),
    )
    selection = UnitMusterSelection.from_payload(json.loads(json.dumps(selection.to_payload())))
    unit = UnitFactory(
        catalog=package.army_catalog, model_geometries=package.model_geometries
    ).instantiate_unit(army_id="frame-source", selection=selection, datasheet=sheet)
    restored = UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload())))
    assert restored.to_payload() == unit.to_payload()
    for model in restored.own_models:
        assert ("FRAME" in model.keywords) is expected
        assert (
            geometry_model_at_pose(model=model, pose=Pose.at(10, 10)).measures_every_part
            is expected
        )
    # This selects the existing geometry policy; no measured Wave hull is invented.


def test_wave_serpent_frame_source_guards_and_exact_addition() -> None:
    from tools.ability_support_sources import load_before_wave_frame_sources

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        wave_serpent_frame_2026_11 as frame,
    )

    before = load_before_wave_frame_sources(DEFAULT_SOURCE_JSON_DIR)
    current = frame.apply_current_frame(before)
    old = next(a for a in before if a.source_table == "Datasheets_keywords")
    new = next(a for a in current if a.source_table == "Datasheets_keywords")
    (operation,) = frame.overlay_pack().operations
    assert operation.source_row_id == "000000599:Frame:global:false:15879"
    assert operation.order_index == 15877
    assert tuple(r for r in new.rows if r.source_row_id != operation.source_row_id) == old.rows
    added = tuple(r for r in new.rows if r.source_row_id == operation.source_row_id)
    assert len(added) == 1
    assert new.rows.index(added[0]) == 2313
    assert added[0].runtime_fields_payload() == {
        "datasheet_id": "000000599",
        "keyword": "Frame",
        "model": "",
        "is_faction_keyword": "false",
    }
    for prior, after in zip(before, current, strict=True):
        if prior is not old:
            assert after is prior
    with pytest.raises(SourceOverlayError, match="keyword absence"):
        frame.apply_current_frame(current)
    drift = replace(old, rows=old.rows[:-1])
    with pytest.raises(SourceOverlayError, match="predecessor drifted"):
        frame.apply_current_frame(tuple(drift if a is old else a for a in before))
    with pytest.raises(SourceOverlayError, match="one keyword predecessor"):
        frame.apply_current_frame(tuple(a for a in before if a is not old))
    with pytest.raises(SourceOverlayError, match="one keyword predecessor"):
        frame.apply_current_frame((*before, old))


@pytest.mark.parametrize("which", ["audit", "overlay"])
def test_wave_serpent_frame_admission_bytes_are_pinned(which: str) -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        wave_serpent_frame_2026_11 as frame,
    )

    if which == "audit":
        raw = Path(frame.__file__).with_name(frame.AUDIT_ARTIFACT_NAME).read_bytes()
        with pytest.raises(FactionSourceError, match="reviewed pin"):
            frame.source_audit_from_json_bytes(raw + b" ")
    else:
        raw = Path(frame.__file__).with_name(frame.ARTIFACT_NAME).read_bytes()
        with pytest.raises(SourceOverlayError, match="reviewed pin"):
            frame.overlay_pack_from_json_bytes(raw + b" ")


def test_wave_serpent_frame_source_admission_and_index_inputs() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        wave_serpent_frame_2026_11 as frame,
    )

    assert (
        frame.source_package()
        .source_catalog.source_text_by_id("faction-app:aeldari:datasheet:wave-serpent")
        .raw_text
        == frame.source_audit().observations[0].operative_text
    )
    inputs = ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR)
    assert Path(frame.__file__).with_name(frame.ARTIFACT_NAME) in inputs
    assert Path(frame.__file__).with_name(frame.AUDIT_ARTIFACT_NAME) in inputs


def test_wave_serpent_frame_exact_native_delta_and_unchanged_counterparts() -> None:
    from tests.wave_serpent_frame_helpers import before_wave_frame, frame_audit

    audit = frame_audit("catalog-delta")
    native, paired_catalog, daemons_catalog = packages()
    assert before_wave_frame(native).package_hash() == audit["prior_package_hash"]
    assert before_wave_frame(paired_catalog) is paired_catalog
    assert before_wave_frame(daemons_catalog) is daemons_catalog
    wave = native.army_catalog.datasheet_by_id("000000599")
    changed = replace(wave, name=wave.name + " drift")
    drift = replace(
        native,
        army_catalog=replace(
            native.army_catalog,
            datasheets=tuple(
                changed if row is wave else row for row in native.army_catalog.datasheets
            ),
        ),
    )
    with pytest.raises(AssertionError):
        before_wave_frame(drift)
