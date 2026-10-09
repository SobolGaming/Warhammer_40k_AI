"""Combat admission quantifies alternative whole-unit Tactical setups."""

import copy
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order128_helpers import assert_checkpoint
from tests.order135_transport_helpers import (
    CARRIER,
    cargo_proposal,
    reach_disembark,
    starting_cargo_session,
    submit_transport_choice,
    transport_config,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_resolution_request,
    mortal_wound_resolution_source_context,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
    _rules_unit_combat_hazard_context,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.transport_disembark_geometry import geometry_models_for_unit_placement
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    DisembarkModeKind,
    TransportHazardMortalWounds,
    TransportHazardMortalWoundsPayload,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition


def test_native_far_combat_is_atomic_when_another_tactical_setup_exists() -> None:
    session = starting_cargo_session()
    request = reach_disembark(session)
    tactical = cargo_proposal(session)
    assert tactical.attempted_placement is not None
    assert_checkpoint(session)

    # Establish actual Tactical legality from the same untouched public boundary.
    alternative = session.fork()
    accepted = alternative.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-combat:legal-tactical-alternative",
        payload=validate_json_value(tactical.to_payload()),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert_checkpoint(alternative)

    far = replace(
        tactical,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        attempted_placement=replace(
            tactical.attempted_placement,
            model_placements=tuple(
                replace(
                    model,
                    pose=Pose.at(model.pose.position.x + 2, model.pose.position.y),
                )
                for model in tactical.attempted_placement.model_placements
            ),
        ),
    )
    before = session.to_persistence_payload()
    denied = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-combat:illegal-far-alternative",
        payload=validate_json_value(far.to_payload()),
    )
    assert denied.status_kind is LifecycleStatusKind.INVALID, denied.to_payload()
    assert session.to_persistence_payload() == before
    assert session.advance_until_decision_or_terminal().decision_request == request
    assert_checkpoint(session)
    retry = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-combat:legal-tactical-alternative",
        payload=validate_json_value(tactical.to_payload()),
    )
    assert retry.status_kind is not LifecycleStatusKind.INVALID, retry.to_payload()
    assert session.to_persistence_payload() == alternative.to_persistence_payload()
    assert_checkpoint(session)


def test_native_combat_accepts_proven_impossible_tactical_height() -> None:
    # Synthetic predeclared Core FRAME geometry, not a faction/body certificate.
    # Free continuous height cannot fit this body inside the carrier's 3D band.
    height = 12.0
    session = starting_cargo_session(frame_height=height)
    request = reach_disembark(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    carrier = geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=state.battlefield_state.unit_placement_by_id(CARRIER),
    )[0]
    assert height > carrier.volume.height + 6
    proposal = cargo_proposal(session)
    assert proposal.attempted_placement is not None
    placement = replace(
        proposal.attempted_placement,
        model_placements=tuple(
            replace(
                row,
                pose=Pose.at(
                    row.pose.position.x,
                    row.pose.position.y,
                    carrier.pose.position.z + (carrier.volume.height - height) / 2,
                ),
            )
            for row in proposal.attempted_placement.model_placements
        ),
    )
    passenger = geometry_models_for_unit_placement(scenario=scenario, unit_placement=placement)[0]
    measurement = DistanceMeasurementContext.from_models(carrier, passenger)
    assert not measurement.target_wholly_within_distance(3)
    assert measurement.target_wholly_within_distance(6)
    proposal = replace(
        proposal, disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK, attempted_placement=placement
    )
    assert_checkpoint(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-combat:whole-height-proof",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert_checkpoint(session)
    completion = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE
    )
    payload = cast(TransportHazardMortalWoundsPayload, completion.payload)
    decoded = TransportHazardMortalWounds.from_payload(payload)
    assert decoded.to_payload() == payload
    for field, value in (
        ("disembark_payload_kind", "unknown"),
        ("disembark_mode", "emergency_disembark"),
        ("mortal_wounds", False),
        ("extra_unowned_field", "unexpected"),
    ):
        malformed = copy.deepcopy(cast(dict[str, object], payload))
        malformed[field] = value
        with pytest.raises(GameLifecycleError):
            TransportHazardMortalWounds.from_payload(
                cast(TransportHazardMortalWoundsPayload, malformed)
            )
    grouped = cast(dict[str, object], payload["disembark"])
    invalid_group_values: tuple[tuple[str, object], ...] = (
        ("model_rolls", []),
        ("mortal_wounds", True),
    )
    for group_field, group_value in invalid_group_values:
        malformed = copy.deepcopy(cast(dict[str, object], payload))
        malformed_group = copy.deepcopy(grouped)
        malformed_group[group_field] = group_value
        malformed["disembark"] = malformed_group
        with pytest.raises(GameLifecycleError):
            TransportHazardMortalWounds.from_payload(
                cast(TransportHazardMortalWoundsPayload, malformed)
            )


def test_native_grouped_combat_pending_hazard_preserves_strict_context_and_replay() -> None:
    # The Core descriptor and analytical body are declared before start.
    # No runtime grant, hazard result, pending request or replay history is replaced.
    config = transport_config(frame_height=12)
    ability = DatasheetAbilityDescriptor(
        ability_id="core-feel-no-pain",
        name="Feel No Pain 5+",
        source_id="order135-combat:core-feel-no-pain",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.CORE,
        effect_description="CORE Feel No Pain descriptor.",
        timing_tags=("lost_wound", "feel_no_pain"),
        parameter_tokens=("5+",),
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                abilities=(
                    *sheet.abilities,
                    ability,
                    replace(
                        ability,
                        ability_id="core-feel-no-pain-second",
                        name="Feel No Pain 6+",
                        source_id="order135-combat:second-core-feel-no-pain",
                        parameter_tokens=("6+",),
                    ),
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
    )
    session = LocalGameSession()
    session.start(replace(config, game_id="order135-combat-pending-03", army_catalog=catalog))
    request = reach_disembark(session)
    proposal = cargo_proposal(session)
    assert proposal.attempted_placement is not None
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    carrier = geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=state.battlefield_state.unit_placement_by_id(CARRIER),
    )[0]
    placement = replace(
        proposal.attempted_placement,
        model_placements=tuple(
            replace(
                row,
                pose=Pose.at(
                    row.pose.position.x,
                    row.pose.position.y,
                    carrier.pose.position.z + (carrier.volume.height - 12) / 2,
                ),
            )
            for row in proposal.attempted_placement.model_placements
        ),
    )
    proposal = replace(
        proposal, disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK, attempted_placement=placement
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-combat:pending-hazard",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    pending = pending_request(session)
    assert is_mortal_wound_resolution_request(pending), (
        pending.to_payload(),
        [
            event.to_payload()
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type in {TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE, "dice_rolled"}
        ],
    )
    context = mortal_wound_resolution_source_context(pending)
    assert isinstance(context, dict)
    assert _rules_unit_combat_hazard_context(context)[1] > 0
    before = session.to_persistence_payload()
    for invalid_round in (True, 1.0, False, "1"):
        malformed = copy.deepcopy(context)
        malformed["battle_round"] = invalid_round
        with pytest.raises(GameLifecycleError, match="battle_round drift"):
            _rules_unit_combat_hazard_context(malformed)
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    restored = LocalGameSession.from_persistence_payload(before)
    forked = session.fork()
    for branch in (session, restored, forked):
        for _ in range(10):
            current = pending_request(branch)
            if not is_mortal_wound_resolution_request(current):
                break
            submit_fixture_request(branch, current)
        else:
            raise AssertionError("Grouped Combat hazard did not finish.")
        assert_checkpoint(branch)
    assert session.to_persistence_payload() == restored.to_persistence_payload()
    assert session.to_persistence_payload() == forked.to_persistence_payload()


@pytest.mark.parametrize("top_width", [4, 8])
def test_native_combat_accepts_ordinary_terrain_constrained_tactical_impossibility(
    top_width: int,
) -> None:
    # Ordinary canonical bases/heights; the predeclared hill has a supported
    # carrier-sized top. The larger terrain footprint forbids unsupported
    # elevated endpoints. No ground-only restriction is assumed.
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10,
        center_y_inches=10,
        width_inches=10,
        depth_inches=10,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        feature_id="order135-combat-platform",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=10,
        footprint_center_y_inches=10,
        footprint_width_inches=10,
        footprint_depth_inches=10,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="carrier-top",
                center_x_inches=10,
                center_y_inches=10,
                bottom_z_inches=5.5,
                width_inches=top_width,
                depth_inches=top_width,
                thickness_inches=0.12,
            ),
        ),
    )
    config = transport_config()
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        deployment_map_id="order135-custom-platform-deployment",
        terrain_layout_id="order135-custom-platform-terrain",
        terrain_features=(feature,),
    )
    config = replace(
        config,
        game_id="order135-combat-platform",
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    session = LocalGameSession()
    session.start(config)
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "submit_placement_proposal":
            break
        if request.decision_type == "submit_deployment_placement":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:platform",
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, owner, _model: Pose.at(
                        10 if owner == "player-a" else 50, 10, 5.5 if owner == "player-a" else 0
                    ),
                ),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        else:
            submit_transport_choice(session, request)
    else:
        raise AssertionError("Elevated carrier did not reach public disembark.")
    proposal = cargo_proposal(session)
    assert proposal.attempted_placement is not None
    placement = replace(
        proposal.attempted_placement,
        model_placements=tuple(
            replace(row, pose=Pose.at(15.8, 10, 0))
            for row in proposal.attempted_placement.model_placements
        ),
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    passenger = geometry_models_for_unit_placement(scenario=scenario, unit_placement=placement)[0]
    carrier = geometry_models_for_unit_placement(
        scenario=scenario, unit_placement=state.battlefield_state.unit_placement_by_id(CARRIER)
    )[0]
    assert not passenger.measures_every_part
    assert not carrier.measures_every_part
    assert carrier.pose.position.z - passenger.volume.height > 3
    assert DistanceMeasurementContext.from_models(carrier, passenger).target_wholly_within_distance(
        6
    )
    assert_checkpoint(session)
    before = session.to_persistence_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-combat:platform-exit",
        payload=validate_json_value(
            replace(
                proposal,
                attempted_placement=placement,
                disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            ).to_payload()
        ),
    )
    if top_width == 4:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    else:
        assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
        assert status.message is not None
        assert "Tactical setup passes" in status.message
        assert session.to_persistence_payload() == before
        assert session.advance_until_decision_or_terminal().decision_request == request
    assert_checkpoint(session)
