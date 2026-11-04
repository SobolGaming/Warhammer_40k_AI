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

from tests.current_description_preimages import current_deep_strike_preimage
from tests.icon_provenance_helpers import before_icon_catalog
from tests.source_history import historical_icon_component, historical_packages
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
from warhammer40k_core.rules.wahapedia_bridge_rows import BridgeSourceArtifact


@cache
def packages() -> tuple[CanonicalCatalogPackage, ...]:
    return (_ability_support_catalog_package(), paired.catalog_package(), daemons.catalog_package())


@cache
def before_daemons_source_artifacts() -> tuple[BridgeSourceArtifact, ...]:
    from tools.ability_support_sources import load_before_daemons_native_sources

    # Frozen rows are shared; each adversarial case replaces only its own tuple/row.
    return load_before_daemons_native_sources(DEFAULT_SOURCE_JSON_DIR)


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

    for package, surface in zip(historical_packages(), correction_audit()["surfaces"], strict=True):
        assert before_starfang_deep_strike(package).package_hash() == surface["prior_package_hash"]


def test_selected_source_index_preserves_corrected_keyword_identity(tmp_path: Path) -> None:
    from warhammer40k_core.rules.selected_source_index import build_selected_source_index

    directory = tmp_path / "source-index"
    build_selected_source_index(
        directory,
        input_files=ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR),
        load_sources=lambda: load_ability_support_sources(DEFAULT_SOURCE_JSON_DIR),
    )
    selected = (
        "000004195",
        "000000600",
        "000000599",
        "000000598",
        "000000613",
        "000001148",
        "000001114",
        "000001115",
    )
    ordinary = _ability_support_catalog_package(datasheet_ids=selected)
    indexed = _ability_support_catalog_package(datasheet_ids=selected, source_index_dir=directory)
    assert indexed.to_payload() == ordinary.to_payload()
    assert "STARFANG" in indexed.army_catalog.datasheet_by_id("000004195").keywords.keywords
    assert "FRAME" in indexed.army_catalog.datasheet_by_id("000000599").keywords.keywords


def test_deep_strike_forward_is_exact_deterministic_and_once_only() -> None:
    current = packages()[2]
    prior = current_deep_strike_preimage(current)
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
    prior = current_deep_strike_preimage(packages()[2])
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
    native, paired_catalog, daemons_catalog = historical_packages()
    assert before_wave_frame(native).package_hash() == audit["prior_package_hash"]
    assert before_wave_frame(paired_catalog) == before_icon_catalog(paired_catalog)
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


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "preimage", "faction", "model"])
@pytest.mark.parametrize("datasheet_id", ["000001148", "000001114"])
def test_daemons_current_keyword_boundary_requires_exact_preimage(
    mutation: str, datasheet_id: str
) -> None:

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_native_2026_11 as current,
    )

    artifacts = before_daemons_source_artifacts()
    table = next(a for a in artifacts if a.source_table == "Datasheets_keywords")
    row = next(
        r
        for r in table.rows
        if r.source_row_id == next(x[1] for x in current.KEYWORD_PREIMAGES if x[0] == datasheet_id)
    )
    if mutation == "missing":
        rows = tuple(r for r in table.rows if r is not row)
    elif mutation == "duplicate":
        rows = (
            *table.rows,
            replace(row, source_row_id=row.source_row_id + ":duplicate", source_row_number=20000),
        )
    else:
        field, value = {
            "preimage": ("keyword", "SHADOW LEGION"),
            "faction": ("is_faction_keyword", "true"),
            "model": ("model", "unreviewed"),
        }[mutation]
        changed = replace(row, fields=tuple((k, value if k == field else v) for k, v in row.fields))
        rows = tuple(changed if r is row else r for r in table.rows)
    changed_table = replace(table, rows=rows)
    with pytest.raises(SourceOverlayError, match="keyword preimage"):
        current.apply_current_daemons(tuple(changed_table if a is table else a for a in artifacts))


def test_daemons_damaged_source_exact_fields_and_other_artifacts_unchanged() -> None:

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_native_2026_11 as current,
    )

    before = before_daemons_source_artifacts()
    after = current.apply_current_daemons(before)
    old = next(a for a in before if a.source_table == "Datasheets")
    new = next(a for a in after if a.source_table == "Datasheets")
    original = next(r for r in old.rows if r.source_row_id == "000001148")
    changed = next(r for r in new.rows if r.source_row_id == "000001148")
    expected = original.runtime_fields_payload()
    expected.update(
        damaged_w="1-7", damaged_description=expected["damaged_description"].replace("1-6", "1-7")
    )
    assert changed.runtime_fields_payload() == expected
    assert tuple(r for r in old.rows if r is not original) == tuple(
        r for r in new.rows if r is not changed
    )
    assert tuple(a for a in after if a is not new) == tuple(a for a in before if a is not old)
    (operation,) = current.overlay_pack().operations
    assert operation.source_row_id == "000001148"
    assert (
        operation.expected_preimage_hash
        == "20b54ffece9d7080f458d62b1f3af07d0675c168d1f7fc99bc2361651a821570"
    )
    assert {k for k, _v in operation.fields} == {"damaged_w", "damaged_description"}
    with pytest.raises(SourceOverlayError, match="target_drift"):
        current.apply_current_daemons(after)
    for mutation in ("missing", "preimage"):
        rows = (
            tuple(r for r in old.rows if r is not original)
            if mutation == "missing"
            else tuple(
                replace(r, fields=tuple((k, "1-5" if k == "damaged_w" else v) for k, v in r.fields))
                if r is original
                else r
                for r in old.rows
            )
        )
        mutated = replace(old, rows=rows)
        with pytest.raises(SourceOverlayError):
            current.apply_current_daemons(tuple(mutated if a is old else a for a in before))


def test_daemons_current_two_complete_pages_and_partial_support_scope() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_native_2026_11 as current,
    )

    audit = current.source_audit()
    assert len(audit.observations) == 2
    assert {o.source_id for o in audit.observations} == {
        source for _, source in current.KEYWORD_SOURCE_IDS
    }
    for row in audit.observations:
        assert row.content_kind == "datasheet"
        assert row.completeness == "complete_page"
        assert (
            current.source_package().source_catalog.source_text_by_id(row.source_id).raw_text
            == row.operative_text
        )
    assert all("detachment" not in source for source in audit.selected_source_ids)
    inputs = ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR)
    for filename in (current.ARTIFACT_NAME, current.AUDIT_ARTIFACT_NAME):
        assert Path(current.__file__).with_name(filename) in inputs
    for filename, loader, error in (
        (current.ARTIFACT_NAME, current.overlay_pack_from_json_bytes, SourceOverlayError),
        (current.AUDIT_ARTIFACT_NAME, current.source_audit_from_json_bytes, FactionSourceError),
    ):
        with pytest.raises(error, match="reviewed pin"):
            loader(Path(current.__file__).with_name(filename).read_bytes() + b" ")


@pytest.mark.parametrize(
    ("faction", "detachment", "grants"),
    [
        ("chaos-daemons", "shadow-legion", True),
        ("chaos-daemons", "daemonic-incursion", False),
        ("emperors-children", "shadow-legion", False),
    ],
)
def test_daemons_native_base_keywords_and_real_conditional_grant_kernel(
    faction: str, detachment: str, grants: bool, selected_army_source_index: Path | None
) -> None:
    from tests.daemons_native_source_helpers import native_definitions
    from warhammer40k_core.engine.army_mustering import (
        ArmyMusterRequest,
        _apply_shadow_legion_keyword_grants,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.list_validation import DetachmentSelection
    from warhammer40k_core.engine.unit_keyword_queries import unit_has_roster_keyword

    package = native_definitions(selected_army_source_index).package
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    selections: list[UnitMusterSelection] = []
    units: list[UnitInstance] = []
    for uid in ("000001148", "000001114", "000001115"):
        sheet = package.army_catalog.datasheet_by_id(uid)
        assert "SHADOW LEGION" not in sheet.keywords.keywords
        assert sheet.keywords.faction_keywords == ("LEGIONES DAEMONICA",)
        selection = UnitMusterSelection(
            unit_selection_id=uid,
            datasheet_id=uid,
            model_profile_selections=tuple(
                ModelProfileSelection(c.model_profile_id, c.min_models) for c in sheet.composition
            ),
        )
        unit = factory.instantiate_unit(
            army_id="source-grants", selection=selection, datasheet=sheet
        )
        assert not unit_has_roster_keyword(unit, "SHADOW LEGION")
        assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit
        selections.append(selection)
        units.append(unit)
    # Exact production grant kernel with explicitly constructed request metadata;
    # this does not assert full native provider/list-mustering admission.
    request = ArmyMusterRequest(
        army_id="source-grants",
        player_id="owner",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(faction, (detachment,)),
        force_disposition_id="constructed-source-grant",
        unit_selections=tuple(selections),
    )
    result = _apply_shadow_legion_keyword_grants(request=request, units=tuple(units))
    if not grants:
        assert result == tuple(units)
    for unit in result:
        assert unit_has_roster_keyword(unit, "SHADOW LEGION") is grants
        assert unit_has_roster_keyword(unit, "UNDIVIDED") is (
            grants and unit.datasheet_id == "000001148"
        )
        assert unit.faction_keywords == ("LEGIONES DAEMONICA",)
        assert all(model.faction_keywords == ("LEGIONES DAEMONICA",) for model in unit.own_models)
        assert not unit_has_roster_keyword(unit, "LEGIONES DAEMONICA")
        assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit


def test_daemons_native_full_sixty_exact_delta_and_counterparts() -> None:
    from tests.daemons_native_source_preservation import before_daemons_native, daemons_audit

    native, paired_catalog, standalone = historical_packages()
    audit = daemons_audit("catalog-delta")
    assert len(native.army_catalog.datasheets) == 60
    prior = before_daemons_native(native)
    assert prior.package_hash() == audit["prior_package_hash"]
    assert before_daemons_native(paired_catalog) == before_icon_catalog(paired_catalog)
    assert before_daemons_native(standalone) is standalone
    from tests.daemons_next_three_preservation import before_daemons_next_three

    historical_native = before_daemons_next_three(native)
    for uid in audit["unchanged_queued_keywords"]:
        row = historical_native.army_catalog.datasheet_by_id(uid)
        assert "SHADOW LEGION" in row.keywords.keywords
        assert row == prior.army_catalog.datasheet_by_id(uid)
    assert native.army_catalog.datasheet_by_id("000001115") == prior.army_catalog.datasheet_by_id(
        "000001115"
    )
    belakor = native.army_catalog.datasheet_by_id("000001148")
    drift = replace(
        native,
        army_catalog=replace(
            native.army_catalog,
            datasheets=tuple(
                replace(row, name=row.name + " drift") if row is belakor else row
                for row in native.army_catalog.datasheets
            ),
        ),
    )
    with pytest.raises(AssertionError):
        before_daemons_native(drift)


@pytest.mark.parametrize(
    "datasheet_id",
    ["000001112", "000001120", "000001132", "000002582", "000001149", "000002758", "000001151"],
)
@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "alias", "identity", "faction", "model"]
)
def test_daemons_current_exact_keyword_guard(datasheet_id: str, mutation: str) -> None:

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_native_2026_11 as current,
    )

    artifacts = before_daemons_source_artifacts()
    table = next(a for a in artifacts if a.source_table == "Datasheets_keywords")
    row = next(
        r
        for r in table.rows
        if r.runtime_fields_payload()["datasheet_id"] == datasheet_id
        and r.runtime_fields_payload()["keyword"] == "Shadow Legion"
    )
    rows = table.rows
    if mutation == "missing":
        rows = tuple(r for r in rows if r is not row)
    elif mutation in {"duplicate", "alias"}:
        fields = tuple(
            (k, " SHADOW LEGION " if k == "keyword" and mutation == "alias" else v)
            for k, v in row.fields
        )
        rows = (
            *rows,
            replace(
                row,
                fields=fields,
                source_row_id=row.source_row_id + ":duplicate",
                source_row_number=20000,
            ),
        )
    else:
        field, value = {
            "identity": ("keyword", "SHADOW LEGION"),
            "faction": ("is_faction_keyword", "true"),
            "model": ("model", "unreviewed"),
        }[mutation]
        changed = replace(row, fields=tuple((k, value if k == field else v) for k, v in row.fields))
        rows = tuple(changed if r is row else r for r in rows)
    mutated = replace(table, rows=rows)
    with pytest.raises(SourceOverlayError, match="keyword preimage"):
        current.apply_current_daemons(tuple(mutated if a is table else a for a in artifacts))


@pytest.mark.parametrize("datasheet_id", ["000001112", "000001120", "000001132"])
@pytest.mark.parametrize(
    ("detachment", "grants"), [("shadow-legion", True), ("daemonic-incursion", False)]
)
def test_daemons_next_three_native_keyword_grant_roundtrip(
    datasheet_id: str, detachment: str, grants: bool
) -> None:
    from warhammer40k_core.engine.army_mustering import (
        ArmyMusterRequest,
        _apply_shadow_legion_keyword_grants,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.list_validation import DetachmentSelection
    from warhammer40k_core.engine.unit_keyword_queries import unit_has_roster_keyword

    package = packages()[0]
    sheet = package.army_catalog.datasheet_by_id(datasheet_id)
    assert "SHADOW LEGION" not in sheet.keywords.keywords
    assert sheet.keywords.faction_keywords == ("LEGIONES DAEMONICA",)
    selection = UnitMusterSelection(
        unit_selection_id=datasheet_id,
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(c.model_profile_id, c.min_models) for c in sheet.composition
        ),
    )
    unit = UnitFactory(
        catalog=package.army_catalog, model_geometries=package.model_geometries
    ).instantiate_unit(army_id="next-three", selection=selection, datasheet=sheet)
    assert not unit_has_roster_keyword(unit, "SHADOW LEGION")
    assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit
    # Real native construction and grant kernel; Lord/Plague physical admission remains blocked
    # by missing geometry. This is not full army admission or facade/ReplayRunner evidence.
    request = ArmyMusterRequest(
        army_id="next-three",
        player_id="owner",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection("chaos-daemons", (detachment,)),
        force_disposition_id="constructed-source-grant",
        unit_selections=(selection,),
    )
    (result,) = _apply_shadow_legion_keyword_grants(request=request, units=(unit,))
    assert unit_has_roster_keyword(result, "SHADOW LEGION") is grants
    assert not unit_has_roster_keyword(result, "UNDIVIDED")
    assert result.faction_keywords == ("LEGIONES DAEMONICA",)
    assert all(("SHADOW LEGION" in m.keywords) is grants for m in result.own_models)
    assert UnitInstance.from_payload(json.loads(json.dumps(result.to_payload()))) == result
    if not grants:
        assert result == unit


def test_daemons_next_three_full_catalog_delta_and_pinned_source() -> None:
    from tests.daemons_final_four_preservation import before_daemons_final_four
    from tests.daemons_next_three_preservation import before_daemons_next_three, daemons_audit
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_next_three_2026_11 as current,
    )

    native, paired_catalog, standalone = historical_packages()
    native = before_daemons_final_four(native)
    audit = daemons_audit("catalog-delta")
    before = before_daemons_next_three(native)
    assert len(native.army_catalog.datasheets) == 60
    assert before.package_hash() == audit["prior_package_hash"]
    assert before_daemons_next_three(paired_catalog) == before_icon_catalog(paired_catalog)
    assert before_daemons_next_three(standalone) is standalone
    changed = {"000001112", "000001120", "000001132"}
    for old, new in zip(
        before.army_catalog.datasheets, native.army_catalog.datasheets, strict=True
    ):
        if old.datasheet_id not in changed:
            assert old == new
        else:
            assert (
                tuple(k for k in old.keywords.keywords if k != "SHADOW LEGION")
                == new.keywords.keywords
            )
            assert old.keywords.faction_keywords == new.keywords.faction_keywords
    source = current.source_audit()
    assert len(source.observations) == 3
    assert set(source.selected_source_ids) == {s for _, s in current.KEYWORD_SOURCE_IDS}
    for row in source.observations:
        assert row.completeness == "complete_page"
        assert (
            current.source_package().source_catalog.source_text_by_id(row.source_id).raw_text
            == row.operative_text
        )
    raw = Path(current.__file__).with_name(current.AUDIT_ARTIFACT_NAME).read_bytes()
    with pytest.raises(FactionSourceError, match="reviewed pin"):
        current.source_audit_from_json_bytes(raw + b" ")
    assert Path(current.__file__).with_name(
        current.AUDIT_ARTIFACT_NAME
    ) in ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR)


@pytest.mark.parametrize("duplicate", [False, True])
def test_daemons_next_three_requires_one_keyword_table(duplicate: bool) -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import daemons_native_2026_11

    artifacts = before_daemons_source_artifacts()
    table = next(a for a in artifacts if a.source_table == "Datasheets_keywords")
    changed = (*artifacts, table) if duplicate else tuple(a for a in artifacts if a is not table)
    with pytest.raises(SourceOverlayError, match="one keyword table"):
        daemons_native_2026_11.apply_current_daemons(changed)


def test_daemons_next_three_all_nine_native_construction_variants() -> None:
    from warhammer40k_core.engine.wargear_selections import WargearSelection

    package = packages()[0]
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    count = 0
    for uid in ("000001112", "000001120", "000001132"):
        sheet = package.army_catalog.datasheet_by_id(uid)
        sizes = sorted(
            {
                tuple(c.min_models for c in sheet.composition),
                tuple(c.max_models for c in sheet.composition),
            }
        )
        optional = tuple(o for o in sheet.wargear_options if o.min_selections == 0)
        choices: list[tuple[WargearSelection, ...]] = [()]
        for option in optional:
            choices.extend(
                (WargearSelection(option.option_id, option.model_profile_id, (w,)),)
                for w in option.allowed_wargear_ids
            )
        if uid == "000001132":
            choices.append(
                tuple(
                    WargearSelection(o.option_id, o.model_profile_id, o.allowed_wargear_ids)
                    for o in optional
                )
            )
        for size in sizes:
            for gear in choices:
                selection = UnitMusterSelection(
                    unit_selection_id="variant-" + str(count),
                    datasheet_id=uid,
                    model_profile_selections=tuple(
                        ModelProfileSelection(c.model_profile_id, n)
                        for c, n in zip(sheet.composition, size, strict=True)
                    ),
                    wargear_selections=gear,
                )
                unit = factory.instantiate_unit(
                    army_id="next-three", selection=selection, datasheet=sheet
                )
                assert "SHADOW LEGION" not in unit.keywords
                assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit
                count += 1
    assert count == 9


def test_daemons_final_four_full_catalog_delta_and_pinned_source() -> None:
    from tests.daemons_final_four_preservation import before_daemons_final_four, daemons_audit
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_final_four_2026_11 as current,
    )

    native, paired_catalog, standalone = historical_packages()
    native = before_icon_catalog(native)
    audit = daemons_audit("catalog-delta")
    before = before_daemons_final_four(native)
    assert len(native.army_catalog.datasheets) == 60
    assert before.package_hash() == audit["prior_package_hash"]
    assert before_daemons_final_four(paired_catalog) == before_icon_catalog(paired_catalog)
    assert before_daemons_final_four(standalone) is standalone
    changed = {"000002582", "000001149", "000002758", "000001151"}
    for old, new in zip(
        before.army_catalog.datasheets, native.army_catalog.datasheets, strict=True
    ):
        if old.datasheet_id not in changed:
            assert old == new
        else:
            assert (
                tuple(k for k in old.keywords.keywords if k != "SHADOW LEGION")
                == new.keywords.keywords
            )
            assert old.keywords.faction_keywords == new.keywords.faction_keywords
    source = current.source_audit()
    assert len(source.observations) == 4
    assert set(source.selected_source_ids) == {s for _, s in current.KEYWORD_SOURCE_IDS}
    for row in source.observations:
        assert row.completeness == "complete_page"
        assert (
            current.source_package().source_catalog.source_text_by_id(row.source_id).raw_text
            == row.operative_text
        )
    raw = Path(current.__file__).with_name(current.AUDIT_ARTIFACT_NAME).read_bytes()
    with pytest.raises(FactionSourceError, match="reviewed pin"):
        current.source_audit_from_json_bytes(raw + b" ")
    assert Path(current.__file__).with_name(
        current.AUDIT_ARTIFACT_NAME
    ) in ability_support_index_inputs(DEFAULT_SOURCE_JSON_DIR)


@pytest.mark.parametrize(
    ("datasheet_id", "expected"),
    [("000002582", 3), ("000001149", 4), ("000002758", 4), ("000001151", 8)],
)
def test_daemons_final_four_all_native_variants(datasheet_id: str, expected: int) -> None:
    from tests.daemons_final_four_preservation import before_daemons_final_four
    from warhammer40k_core.engine.army_mustering import (
        ArmyMusterRequest,
        RosterLegalityViolation,
        _append_shadow_legion_forbidden_unit_violations,  # pyright: ignore[reportPrivateUsage]
        _apply_shadow_legion_keyword_grants,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.list_validation import (
        DetachmentSelection,
        MusteringOptionSelection,
    )
    from warhammer40k_core.engine.unit_keyword_queries import unit_has_roster_keyword
    from warhammer40k_core.engine.wargear_selections import WargearSelection

    package = packages()[0]
    historical = historical_packages()[0]
    prior = before_daemons_final_four(historical)
    sheet = package.army_catalog.datasheet_by_id(datasheet_id)
    historical_sheet = historical.army_catalog.datasheet_by_id(datasheet_id)
    old_sheet = prior.army_catalog.datasheet_by_id(datasheet_id)
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    historical_factory = UnitFactory(
        catalog=historical.army_catalog, model_geometries=historical.model_geometries
    )
    old_factory = UnitFactory(catalog=prior.army_catalog, model_geometries=prior.model_geometries)
    allegiances: list[tuple[MusteringOptionSelection, ...]] = [
        (MusteringOptionSelection(o.option_id),) for o in sheet.mustering_options
    ] or [()]
    gears: list[tuple[WargearSelection, ...]] = [()]
    gears.extend(
        (WargearSelection(o.option_id, o.model_profile_id, o.allowed_wargear_ids),)
        for o in sheet.wargear_options
        if o.min_selections == 0
    )
    removed_sources = set(old_sheet.source_ids) - set(historical_sheet.source_ids)
    added_sources = set(historical_sheet.source_ids) - set(old_sheet.source_ids)
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        daemons_final_four_2026_11 as current,
    )

    assert not removed_sources  # Historical row ancestry remains retained.
    assert added_sources == {
        "data-package:pdf:source-corrections:reviewed-2026-11-04:PdfCorrections:"
        + datasheet_id
        + ":keyword-correction",
        dict(current.KEYWORD_SOURCE_IDS)[datasheet_id],
    }

    def assert_source_delta(old: list[str], new: list[str]) -> None:
        assert set(old) - set(new) <= removed_sources
        assert set(new) - set(old) <= added_sources

    count = 0
    for allegiance in allegiances:
        for gear in gears:
            selection = UnitMusterSelection(
                unit_selection_id=datasheet_id,
                datasheet_id=datasheet_id,
                model_profile_selections=tuple(
                    ModelProfileSelection(c.model_profile_id, c.min_models)
                    for c in sheet.composition
                ),
                mustering_option_selections=allegiance,
                wargear_selections=gear,
            )
            unit = factory.instantiate_unit(
                army_id="final-four", datasheet=sheet, selection=selection
            )
            previous = old_factory.instantiate_unit(
                army_id="final-four", datasheet=old_sheet, selection=selection
            )
            assert not unit_has_roster_keyword(unit, "SHADOW LEGION")
            assert all("SHADOW LEGION" not in m.keywords for m in unit.own_models)
            assert unit.faction_keywords == ("LEGIONES DAEMONICA",)
            assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit
            # Catalog proof binds the exact correction record and new reviewed source ID.
            # Unit/model provenance carries that same delta; all other payload fields agree.
            old_payload = previous.to_payload()
            new_payload = historical_factory.instantiate_unit(
                army_id="final-four", datasheet=historical_sheet, selection=selection
            ).to_payload()
            old_payload["keywords"].remove("SHADOW LEGION")
            assert_source_delta(
                old_payload["datasheet_source_ids"], new_payload["datasheet_source_ids"]
            )
            old_payload["datasheet_source_ids"] = new_payload["datasheet_source_ids"]
            for old_model, new_model in zip(
                old_payload["own_models"], new_payload["own_models"], strict=True
            ):
                old_model["keyword_assignment"]["keywords"].remove("SHADOW LEGION")
                assert_source_delta(
                    old_model["keyword_assignment"]["source_ids"],
                    new_model["keyword_assignment"]["source_ids"],
                )
                old_model["keyword_assignment"]["source_ids"] = new_model["keyword_assignment"][
                    "source_ids"
                ]
                assert_source_delta(old_model["source_ids"], new_model["source_ids"])
                old_model["source_ids"] = new_model["source_ids"]
            assert old_payload == new_payload
            # Native package has no admitted detachments. These are real factory and existing
            # grant/prohibition-owner controls, not a fabricated full army/session certification.
            for faction, detachment in (
                ("chaos-daemons", "daemonic-incursion"),
                ("aeldari", "shadow-legion"),
                ("chaos-daemons", "shadow-legion"),
            ):
                request = ArmyMusterRequest(
                    army_id="final-four",
                    player_id="owner",
                    catalog_id=package.army_catalog.catalog_id,
                    source_package_id=package.army_catalog.source_package_id,
                    ruleset_id=package.army_catalog.ruleset_id,
                    detachment_selection=DetachmentSelection(faction, (detachment,)),
                    force_disposition_id="constructed-source-grant",
                    unit_selections=(selection,),
                )
                is_shadow = faction == "chaos-daemons" and detachment == "shadow-legion"
                if is_shadow and datasheet_id in {"000001149", "000002758"}:
                    violations: list[RosterLegalityViolation] = []
                    _append_shadow_legion_forbidden_unit_violations(
                        datasheets_by_selection_id={datasheet_id: sheet}, violations=violations
                    )
                    assert len(violations) == 1
                    assert (
                        violations[0].violation_code
                        == "shadow_legion_forbidden_daemon_prince_or_epic_hero"
                    )
                    continue
                (result,) = _apply_shadow_legion_keyword_grants(request=request, units=(unit,))
                assert unit_has_roster_keyword(result, "SHADOW LEGION") is is_shadow
                assert all(("SHADOW LEGION" in m.keywords) is is_shadow for m in result.own_models)
                assert not unit_has_roster_keyword(result, "UNDIVIDED")
                assert (
                    UnitInstance.from_payload(json.loads(json.dumps(result.to_payload()))) == result
                )
                if not is_shadow:
                    assert result == unit
            count += 1
    assert count == expected


@pytest.mark.parametrize("datasheet_id", ["000001149", "000002758", "000001151"])
def test_daemons_final_four_allegiance_remains_mandatory(datasheet_id: str) -> None:
    from warhammer40k_core.engine.unit_factory import UnitFactoryError

    package = packages()[0]
    sheet = package.army_catalog.datasheet_by_id(datasheet_id)
    selection = UnitMusterSelection(
        unit_selection_id=datasheet_id,
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(c.model_profile_id, c.min_models) for c in sheet.composition
        ),
    )
    with pytest.raises(UnitFactoryError):
        UnitFactory(
            catalog=package.army_catalog, model_geometries=package.model_geometries
        ).instantiate_unit(army_id="final-four", datasheet=sheet, selection=selection)


def test_icon_successor_preserves_complete_historical_catalogs_and_rejects_drift() -> None:
    from tests.icon_provenance_helpers import icon_successor_audit

    audit = icon_successor_audit()
    for package in historical_packages():
        previous = before_icon_catalog(package)
        assert before_icon_catalog(previous) is previous
        surface = next(
            (
                s
                for s in audit["catalog_surfaces"]
                if s["catalog_id"] == package.army_catalog.catalog_id
            ),
            None,
        )
        if surface is None:
            assert previous is package
        else:
            assert package.package_hash() == surface["current_hash"]
            assert previous.package_hash() == surface["prior_hash"]
            changed = [
                current.datasheet_id
                for current, old in zip(
                    package.army_catalog.datasheets, previous.army_catalog.datasheets, strict=True
                )
                if current != old
            ]
            assert changed == ["000004079", "000004080"]
        sheet = package.army_catalog.datasheets[0]
        drift = replace(
            package,
            army_catalog=replace(
                package.army_catalog,
                datasheets=(
                    replace(sheet, name=sheet.name + " drift"),
                    *package.army_catalog.datasheets[1:],
                ),
            ),
        )
        with pytest.raises(AssertionError):
            before_icon_catalog(drift)


def test_icon_component_successor_keeps_sticky_exact_and_rejects_partial_or_source_drift() -> None:
    from copy import deepcopy

    from tests.icon_provenance_helpers import before_icon_component

    current = historical_icon_component()
    previous = before_icon_component(current)
    assert previous["records"]["000004079:3"] == current["records"]["000004079:3"]
    for path in (
        ("records", "000004079:3", "rule_ir", "normalized_text"),
        ("records", "000004079:3", "rule_ir", "source_id"),
        ("records", "000004079:4", "rule_ir", "clauses", 1, "trigger", "parameters", 1, "value"),
    ):
        changed = deepcopy(current)
        cursor: Any = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = "unreviewed"
        with pytest.raises(AssertionError):
            before_icon_component(changed)
    with pytest.raises(AssertionError):
        before_icon_component(previous)
