from __future__ import annotations

import json
import math
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.objectives import Objective, ObjectiveMarker, ObjectiveMarkerPayload
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.endpoint_placement import (
    ObjectiveMarkerEndpointPlacementViolation,
    ObjectiveMarkerEndpointPlacementViolationPayload,
    objective_marker_endpoint_placement_violation,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlRecordPayload,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    ObjectiveMarkerEndpointViolation,
    ObjectiveMarkerEndpointViolationPayload,
    objective_control_status_from_token,
    objective_control_timing_from_token,
    objective_marker_endpoint_violations,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_objective_control_sums_oc_by_player_from_current_runtime_models() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0), (-2.0, 0.0)),
        player_b_offsets=((0.0, 2.0),),
    )
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
        )
    )
    result = _center_result(record)

    assert result.status is ObjectiveControlStatus.CONTROLLED
    assert result.controlled_by_player_id == "player-a"
    assert [(score.player_id, score.score) for score in result.scores] == [
        ("player-a", 4),
        ("player-b", 2),
    ]
    assert all(contribution.effective_objective_control > 0 for contribution in result.contributors)


def test_battle_shocked_unit_contributes_oc_zero() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0), (-2.0, 0.0)),
        player_b_offsets=((0.0, 2.0),),
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    result = _center_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert result.controlled_by_player_id == "player-b"
    assert [(score.player_id, score.score) for score in result.scores] == [("player-b", 2)]
    assert {
        contribution.model_instance_id: contribution.effective_objective_control
        for contribution in result.contributors
        if contribution.player_id == "player-a"
    } == {
        "army-alpha:intercessor-unit-1:core-intercessor-like:001": 0,
        "army-alpha:intercessor-unit-1:core-intercessor-like:002": 0,
    }
    assert all(
        contribution.battle_shocked
        for contribution in result.contributors
        if contribution.player_id == "player-a"
    )


def test_contested_objective_has_deterministic_uncontrolled_result() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((-2.0, 0.0),),
    )

    result = _center_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert result.status is ObjectiveControlStatus.CONTESTED
    assert result.controlled_by_player_id is None
    assert [(score.player_id, score.score) for score in result.scores] == [
        ("player-a", 2),
        ("player-b", 2),
    ]


def test_objective_without_controlling_models_is_uncontrolled() -> None:
    far_offsets = (
        (20.0, 20.0),
        (24.0, 20.0),
        (28.0, 20.0),
        (32.0, 20.0),
        (36.0, 20.0),
    )
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=far_offsets,
        player_b_offsets=far_offsets,
    )

    result = _center_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert result.status is ObjectiveControlStatus.UNCONTROLLED
    assert result.controlled_by_player_id is None
    assert result.scores == ()
    assert result.contributors == ()


def test_objective_marker_payloads_round_trip_with_default_geometry() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    marker = _center_marker_definition(state).to_objective_marker()
    payload = cast(
        ObjectiveMarkerPayload,
        json.loads(json.dumps(marker.to_payload(), sort_keys=True)),
    )

    restored = ObjectiveMarker.from_payload(payload)
    from_point_objective = ObjectiveMarker.from_objective(
        Objective.point(
            objective_id="point-objective",
            name="Point Objective",
            x=1.0,
            y=2.0,
            z=0.5,
            control_radius_inches=4.0,
        )
    )

    assert restored == marker
    assert marker.stable_identity() == f"objective-marker:{marker.objective_marker_id}"
    assert math.isclose(marker.marker_diameter_inches, 40.0 / 25.4, rel_tol=0.0, abs_tol=1e-12)
    assert from_point_objective.control_horizontal_inches == 4.0
    assert from_point_objective.control_vertical_inches == 5.0


def test_terrain_objective_control_policy_is_explicitly_unsupported() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=_ruleset(),
        terrain_objectives=(Objective.terrain("ruin-objective", "Ruin", "ruin-alpha"),),
    )

    result = resolve_objective_control(context).result_by_objective_id("ruin-objective")

    assert result.status is ObjectiveControlStatus.UNSUPPORTED
    assert result.unsupported_reason == "terrain_objective_control_policy_unsupported"
    assert result.scores == ()
    assert result.controlled_by_player_id is None


def test_model_endpoint_on_objective_marker_is_rejected() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    scenario = _scenario_from_state(state)
    marker_definition = _center_marker_definition(state)
    marker = marker_definition.to_objective_marker()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    overlapping = _with_model_offsets(
        unit_placement,
        marker_definition,
        offsets=((0.0, 0.0),),
    )

    violations = objective_marker_endpoint_violations(
        scenario=scenario,
        objective_markers=(marker,),
        unit_placement=overlapping,
    )
    scenario_wide_violations = objective_marker_endpoint_violations(
        scenario=scenario,
        objective_markers=(marker,),
    )
    violation_payload = cast(
        ObjectiveMarkerEndpointViolationPayload,
        json.loads(json.dumps(violations[0].to_payload(), sort_keys=True)),
    )

    assert len(violations) == 1
    assert violations[0].objective_marker_id == marker.objective_marker_id
    assert violations[0].model_instance_id == overlapping.model_placements[0].model_instance_id
    assert violations[0].violation_code == "objective_marker_endpoint_overlap"
    assert scenario_wide_violations == ()
    assert ObjectiveMarkerEndpointViolation.from_payload(violation_payload) == violations[0]


def test_normal_move_endpoint_on_objective_marker_is_rejected_by_shared_resolver() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((4.0, 0.0), (4.0, 2.0), (4.0, 4.0), (4.0, 6.0), (4.0, 8.0)),
    )
    scenario = _scenario_from_state(state)
    marker = _center_marker_definition(state).to_objective_marker()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=_straight_line_witness(unit_placement, delta_x=-4.0),
        objective_markers=(marker,),
    )

    assert not resolution.is_valid
    assert any(
        violation.violation_code == "objective_marker_endpoint_overlap"
        and violation.blocker_id == marker.objective_marker_id
        for path_result in resolution.path_validation_results
        for violation in path_result.violations
    )


def test_setup_placement_endpoint_on_objective_marker_is_rejected_by_game_state() -> None:
    mission_setup = _mission_setup()
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11b-invalid-setup-battlefield",
        armies=armies,
    )
    marker = _center_marker_definition(state)
    player_a = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = scenario.battlefield_state.with_unit_placement(
        _with_model_offsets(player_a, marker, offsets=((0.0, 0.0),))
    )

    with pytest.raises(GameLifecycleError, match="objective marker"):
        state.record_battlefield_state(battlefield_state)


def test_objective_marker_endpoint_placement_violation_payload_round_trips() -> None:
    violation = ObjectiveMarkerEndpointPlacementViolation(
        violation_code="objective_marker_endpoint_overlap",
        message="Normal Move cannot end on an objective marker.",
        model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
        blocker_id="mission-a-center",
    )
    payload = cast(
        ObjectiveMarkerEndpointPlacementViolationPayload,
        json.loads(json.dumps(violation.to_payload(), sort_keys=True)),
    )

    assert ObjectiveMarkerEndpointPlacementViolation.from_payload(payload) == violation


def test_battlefield_state_replacement_requires_existing_battlefield_state() -> None:
    mission_setup = _mission_setup()
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="phase11b-replace-missing-battlefield",
        armies=armies,
    ).battlefield_state

    with pytest.raises(GameLifecycleError, match="BattlefieldRuntimeState"):
        state.replace_battlefield_state(cast(BattlefieldRuntimeState, object()))
    with pytest.raises(GameLifecycleError, match="does not exist"):
        state.replace_battlefield_state(battlefield_state)
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_mission_setup(_mission_setup())
    with pytest.raises(GameLifecycleError, match="geometry Model"):
        objective_marker_endpoint_placement_violation(
            model=cast(GeometryModel, object()),
            objective_markers=(),
            violation_code="objective_marker_endpoint_overlap",
            placement_label="Normal Move",
        )


def test_objective_control_records_update_at_phase_and_turn_end() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))

    completed_phase = state.advance_to_next_battle_phase()

    assert completed_phase is BattlePhase.COMMAND
    assert len(state.objective_control_records) == 1
    assert state.objective_control_records[0].timing is ObjectiveControlTiming.PHASE_END
    assert state.objective_control_records[0].phase == BattlePhase.COMMAND.value

    while state.current_battle_phase is not BattlePhase.FIGHT:
        state.advance_to_next_battle_phase()
    state.advance_to_next_battle_phase()

    assert [record.timing for record in state.objective_control_records[-2:]] == [
        ObjectiveControlTiming.PHASE_END,
        ObjectiveControlTiming.TURN_END,
    ]
    assert state.objective_control_records[-1].phase == BattlePhase.FIGHT.value
    assert state.objective_control_records[-1].active_player_id == "player-a"


def test_objective_control_boundary_requires_mission_setup() -> None:
    state = GameState.from_config(_config(mission_setup=None))
    state.enter_battle()

    with pytest.raises(GameLifecycleError, match="MissionSetup"):
        state.advance_to_next_battle_phase()


def test_objective_control_payloads_round_trip_without_object_reprs() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((-2.0, 0.0),),
    )
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
        )
    )
    state.record_objective_control_record(record)
    record_payload = cast(
        ObjectiveControlRecordPayload,
        json.loads(json.dumps(record.to_payload(), sort_keys=True)),
    )
    state_payload = cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    blob = json.dumps({"record": record_payload, "state": state_payload}, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert ObjectiveControlRecord.from_payload(record_payload).to_payload() == record.to_payload()
    assert GameState.from_payload(state_payload).to_payload() == state.to_payload()


def test_objective_control_validation_is_fail_fast() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    scenario = _scenario_from_state(state)
    marker = _center_marker_definition(state).to_objective_marker()
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
        )
    )
    score_a = ObjectiveControlScore(player_id="player-a", score=2)
    score_b = ObjectiveControlScore(player_id="player-b", score=1)

    with pytest.raises(GameLifecycleError, match="ObjectiveControlTiming token"):
        objective_control_timing_from_token(10)
    with pytest.raises(GameLifecycleError, match="Unsupported ObjectiveControlTiming"):
        objective_control_timing_from_token("bad-timing")
    with pytest.raises(GameLifecycleError, match="ObjectiveControlStatus token"):
        objective_control_status_from_token(10)
    with pytest.raises(GameLifecycleError, match="Unsupported ObjectiveControlStatus"):
        objective_control_status_from_token("bad-status")
    with pytest.raises(GameLifecycleError, match="Unsupported battle phase token"):
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase="psychic",
        )
    with pytest.raises(GameLifecycleError, match="phase must be a BattlePhase token"):
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=cast(BattlePhase | str, 10),
        )
    with pytest.raises(GameLifecycleError, match="ObjectiveControlRecord objective_id"):
        record.result_by_objective_id("missing-objective")
    with pytest.raises(GameLifecycleError, match="resolve_objective_control requires"):
        resolve_objective_control(cast(ObjectiveControlContext, object()))
    with pytest.raises(GameLifecycleError, match="objective marker endpoint validation"):
        objective_marker_endpoint_violations(
            scenario=cast(BattlefieldScenario, object()),
            objective_markers=(marker,),
        )
    with pytest.raises(GameLifecycleError, match="unit_placement must be"):
        objective_marker_endpoint_violations(
            scenario=scenario,
            objective_markers=(marker,),
            unit_placement=cast(UnitPlacement, object()),
        )
    with pytest.raises(GameLifecycleError, match="battle_shocked must be a bool"):
        ObjectiveControlContribution(
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
            objective_control=2,
            effective_objective_control=2,
            battle_shocked=cast(bool, "yes"),
            horizontal_distance_inches=0.0,
            vertical_gap_inches=0.0,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported objective control requires"):
        ObjectiveControlResult(
            objective_id="unsupported-objective",
            status=ObjectiveControlStatus.UNSUPPORTED,
            controlled_by_player_id=None,
            scores=(),
        )
    with pytest.raises(GameLifecycleError, match="Uncontrolled objective results"):
        ObjectiveControlResult(
            objective_id="uncontrolled-objective",
            status=ObjectiveControlStatus.UNCONTROLLED,
            controlled_by_player_id=None,
            scores=(score_a,),
        )
    with pytest.raises(GameLifecycleError, match="Contested objective results cannot"):
        ObjectiveControlResult(
            objective_id="contested-with-controller",
            status=ObjectiveControlStatus.CONTESTED,
            controlled_by_player_id="player-a",
            scores=(
                ObjectiveControlScore(player_id="player-a", score=2),
                ObjectiveControlScore(player_id="player-b", score=2),
            ),
        )
    with pytest.raises(GameLifecycleError, match="Contested objective results require"):
        ObjectiveControlResult(
            objective_id="contested-objective",
            status=ObjectiveControlStatus.CONTESTED,
            controlled_by_player_id=None,
            scores=(score_a, score_b),
        )
    with pytest.raises(GameLifecycleError, match="Controlled objective results require"):
        ObjectiveControlResult(
            objective_id="controlled-without-controller",
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id=None,
            scores=(score_a,),
        )
    with pytest.raises(GameLifecycleError, match="Controlled objective controller must"):
        ObjectiveControlResult(
            objective_id="controlled-unknown-controller",
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id="player-c",
            scores=(score_a,),
        )
    with pytest.raises(GameLifecycleError, match="Controlled objective controller score"):
        ObjectiveControlResult(
            objective_id="controlled-objective",
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id="player-b",
            scores=(score_a, score_b),
        )


def _battle_state_with_center_objective_positions(
    *,
    player_a_offsets: tuple[tuple[float, float], ...],
    player_b_offsets: tuple[tuple[float, float], ...] = (),
    battle_shocked_unit_ids: tuple[str, ...] = (),
) -> GameState:
    mission_setup = _mission_setup()
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11b-battlefield",
        armies=armies,
    )
    marker = _center_marker_definition(state)
    battlefield_state = scenario.battlefield_state
    if player_a_offsets:
        player_a = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
        battlefield_state = battlefield_state.with_unit_placement(
            _with_model_offsets(player_a, marker, offsets=player_a_offsets)
        )
    if player_b_offsets:
        player_b = battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-3")
        battlefield_state = battlefield_state.with_unit_placement(
            _with_model_offsets(player_b, marker, offsets=player_b_offsets)
        )
    state.record_battlefield_state(battlefield_state)
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    state.battle_shocked_unit_ids = list(battle_shocked_unit_ids)
    return state


def _with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement = placements[index]
        placements[index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def _straight_line_witness(
    unit_placement: UnitPlacement,
    *,
    delta_x: float,
) -> PathWitness:
    return PathWitness.for_straight_line_endpoints(
        tuple(
            (
                placement.model_instance_id,
                placement.pose,
                Pose.at(
                    placement.pose.position.x + delta_x,
                    placement.pose.position.y,
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
            for placement in unit_placement.model_placements
        )
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if marker.objective_marker_id.endswith("-center"):
            return marker
    raise AssertionError("missing center objective marker")


def _center_result(record: ObjectiveControlRecord) -> ObjectiveControlResult:
    for result in record.results:
        if result.objective_id.endswith("-center"):
            return result
    raise AssertionError("missing center objective control result")


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _config(*, mission_setup: MissionSetup | None) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase11b-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
        descriptor_version="core-v2-phase11b-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    assert all(
        _model_objective_control(model.characteristics) == 2
        for army in armies
        for unit in army.units
        for model in unit.own_models
    )
    return armies


def _model_objective_control(characteristics: tuple[CharacteristicValue, ...]) -> int:
    if type(characteristics) is not tuple:
        raise AssertionError("model characteristics must be a tuple")
    for characteristic in characteristics:
        if characteristic.characteristic is Characteristic.OBJECTIVE_CONTROL:
            return characteristic.final
    raise AssertionError("model missing Objective Control")
