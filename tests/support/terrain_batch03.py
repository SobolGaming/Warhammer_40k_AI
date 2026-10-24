"""Native EC terrain consumers; immutable definitions, fresh component scenes.

These are non-strict selected rosters at a constructed Movement checkpoint. The
ordinary lifecycle loads catalog and Court providers; no earlier phases or full
army legality are claimed. Only instantiated unit graphs are copied per scene.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from functools import cache
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import pytest
from tests.support.faction_batch01 import (
    FACTIONS,
    INFRACTORS,
    RANGERS,
    Scene,
    anchor,
    digest,
    locate,
    request,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.stratagems import (
    StratagemEligibilityContext,
    create_stratagem_use_decision_request,
    stratagem_decline_option,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

FULGRIM = "000004077"
DEFILER = "000004208"
MAULERFIEND = "000004091"
SINUOUS = "000010655004"
IDS = (FULGRIM, DEFILER, MAULERFIEND, INFRACTORS, RANGERS)


@pytest.fixture(scope="session")
def terrain_definitions(selected_army_source_index: Path | None) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    catalog = package.army_catalog
    factions: list[FactionDefinition] = []
    detachments: list[DetachmentDefinition] = []
    for source in catalog.factions:
        faction_id, detachment_id = FACTIONS[source.faction_id]
        row = next(r for r in identities.faction_rows() if r.faction_id == faction_id)
        detachment = next(
            r for r in identities.detachment_rows() if r.detachment_id == detachment_id
        )
        factions.append(
            FactionDefinition(
                faction_id=row.faction_id,
                name=row.name,
                faction_keywords=source.faction_keywords,
                source_ids=(*row.source_ids, *source.source_ids),
            )
        )
        detachments.append(
            DetachmentDefinition(
                canonical_detachment_id=detachment.detachment_id,
                detachment_id=detachment.detachment_id,
                name=detachment.name,
                faction_id=faction_id,
                detachment_point_cost=detachment.detachment_point_cost,
                unit_datasheet_ids=tuple(
                    sheet.datasheet_id
                    for sheet in catalog.datasheets
                    if set(sheet.keywords.faction_keywords) & set(source.faction_keywords)
                ),
                force_disposition_ids=tuple(
                    sorted({detachment.force_disposition_id, "take-and-hold", "purge-the-foe"})
                ),
                source_ids=detachment.source_ids,
            )
        )
    package = replace(
        package,
        army_catalog=replace(catalog, factions=tuple(factions), detachments=tuple(detachments)),
    )
    before = digest(package.to_payload())
    seconds = perf_counter() - start
    print(f"Terrain batch03 preparation: {seconds:.6f}s; one package, {len(IDS)} real sheets")
    yield Section02Definitions(package, seconds)
    assert digest(package.to_payload()) == before, "Shared terrain catalog was mutated"


@cache
def barrier(height: float) -> TerrainFeatureDefinition:
    """Shared immutable wall; start/end are clear, only the swept path crosses it."""
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=14,
        center_y_inches=10,
        width_inches=0.25,
        depth_inches=12,
        display_template_id="batch03:wall",
    )
    return TerrainFeatureDefinition(
        feature_id="batch03:wall",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        footprint_center_x_inches=14,
        footprint_center_y_inches=10,
        footprint_width_inches=0.25,
        footprint_depth_inches=12,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        classification=TerrainAreaClassification.DENSE,
        walls=(
            TerrainWallDefinition(
                wall_id="batch03:crossed-section",
                center_x_inches=14,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=0.25,
                depth_inches=12,
                height_inches=height,
            ),
        ),
    )


def terrain_scene(d: Section02Definitions, sheet: str, height: float) -> Scene:
    s = scene(
        d,
        (selection(d, sheet, "mover"), selection(d, INFRACTORS, "observer")),
        (selection(d, RANGERS, "target"),),
        seed="batch03-terrain",
        terrain_features=(barrier(height),),
    )
    locate(s, "own:mover", (Pose.at(10, 10),))
    anchor(s)
    return s


def breach_request(s: Scene) -> DecisionRequest:
    """Explicit existing native start-phase window; automatic scheduling is separate."""
    s.state.gain_command_points(
        player_id="owner",
        amount=1,
        source_id="batch03:cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    context = StratagemEligibilityContext.from_state(
        state=s.state, player_id="owner", trigger_kind=TimingTriggerKind.START_PHASE
    )
    options = stratagem_use_options_from_index(
        state=s.state,
        index=bundle.stratagem_indexes_by_player_id["owner"],
        context=context,
        stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
    )
    assert options
    r = create_stratagem_use_decision_request(
        state=s.state, context=context, options=(*options, stratagem_decline_option())
    )
    s.session.lifecycle.decision_controller.request_decision(r)
    assert request(s.session.advance_until_decision_or_terminal()) == r
    return r


def breach_options(r: DecisionRequest) -> dict[str, str]:
    return {
        cast(dict[str, Any], o.payload)["target_binding"]["target_unit_instance_id"]: o.option_id
        for o in r.options
        if isinstance(o.payload, dict)
        and isinstance(o.payload.get("catalog_record"), dict)
        and cast(dict[str, Any], o.payload)["catalog_record"]["definition"]["stratagem_id"]
        == SINUOUS
    }


def movement_request(s: Scene, action: str = "normal_move") -> DecisionRequest:
    r = request(s.session.advance_until_decision_or_terminal(), "select_movement_unit")
    r = request(
        s.session.submit_option(
            request_id=r.request_id, option_id="own:mover", result_id="b03:unit"
        ),
        "select_movement_action",
    )
    status = s.session.submit_option(
        request_id=r.request_id, option_id=action, result_id="b03:action"
    )
    for i in range(3):
        r = request(status)
        if r.decision_type == "submit_movement_proposal":
            return r
        assert r.decision_type == "select_dice_reroll", r.to_payload()
        status = s.session.submit_option(
            request_id=r.request_id, option_id="decline", result_id=f"b03:advance-keep:{i}"
        )
    raise AssertionError("Movement proposal not reached after native Advance dice")


def path_payload(s: Scene, r: DecisionRequest, end_x: float, *, via_z: float = 0) -> JsonValue:
    assert s.state.battlefield_state is not None
    model = s.state.battlefield_state.unit_placement_by_id("own:mover").model_placements[0]
    context = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert context.movement_phase_action is not None
    assert context.context is not None
    mode = context.context.get("movement_mode")
    assert mode is None or isinstance(mode, str)
    poses: tuple[Pose, ...] = (model.pose, Pose.at(end_x, 10))
    if via_z:
        poses = (model.pose, Pose.at(14, 10, via_z), Pose.at(end_x, 10))
    witness = PathWitness.for_paths(((model.model_instance_id, poses),))
    payload = MovementProposalPayload(
        r.request_id,
        context.proposal_kind,
        "own:mover",
        context.movement_phase_action,
        witness,
        movement_mode=mode,
    )
    return validate_json_value(payload.to_payload())


def submit_path(s: Scene, r: DecisionRequest, end_x: float, *, via_z: float = 0) -> LifecycleStatus:
    return s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=path_payload(s, r, end_x, via_z=via_z),
        result_id=f"{r.request_id}:b03:path",
    )


def terrain_capability(s: Scene, mode: str = "normal") -> MovementCapabilitySet:
    unit = s.units["own:mover"]
    model = unit.own_models[0]
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return MovementCapabilitySet.from_keywords(
        model.keywords,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        ability_index=bundle.ability_indexes_by_player_id["owner"],
        movement_mode=mode,
        unit=unit,
        model_instance_id=model.model_instance_id,
        current_model_instance_ids=unit.own_model_ids(),
        unit_persisting_effects=tuple(
            e
            for e in s.state.persisting_effects
            if unit.unit_instance_id in e.target_unit_instance_ids
        ),
        owner_player_id="owner",
    )
