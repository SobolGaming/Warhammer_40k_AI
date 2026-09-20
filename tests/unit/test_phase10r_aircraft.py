from __future__ import annotations

import copy
import json
import math
from dataclasses import replace
from typing import cast

import pytest
from tests.aircraft_helpers import aircraft_session as _order66_session
from tests.movement_submission_helpers import (
    core_movement_handler,
    submit_default_handler_movement_proposal_if_pending,
)
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.aircraft import (
    AircraftMovementPolicy,
)
from warhammer40k_core.engine.aircraft_turn_end import AIRCRAFT_RETURN_EVENT
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvanceMoveResolution,
    AdvanceRollRequest,
    AdvanceRollResult,
    FallBackModeKind,
    MovementActionAvailabilityContext,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    NormalMoveResolution,
    _model_base_movement_inches,
    _model_movement_budget_inches,
    resolve_advance_move,
    resolve_normal_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_order66_aircraft_has_no_ordinary_movement_actions() -> None:
    _scenario, aircraft, _enemy = _aircraft_scenario()
    context = MovementActionAvailabilityContext(
        ruleset_descriptor_hash=_ruleset().descriptor_hash,
        unit_instance_id=aircraft.unit_instance_id,
        player_id="player-a",
        enemy_engagement_model_ids=(),
        aircraft_movement_policy=AircraftMovementPolicy.from_unit(
            unit=aircraft, ruleset_descriptor=_ruleset()
        ),
    )
    assert context.evaluate().available_actions == ()


def test_order66_hover_does_not_remove_aircraft_identity() -> None:
    _scenario, aircraft, _enemy = _aircraft_scenario()
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=_ruleset())
    assert "AIRCRAFT" in policy.effective_keywords
    assert not policy.can_declare_charge
    assert "hover_mode_active" not in policy.to_payload()


def test_order66_opponent_turn_end_returns_aircraft_and_restores() -> None:
    session = _order66_session()
    status = session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert not state.battlefield_state.is_unit_placed("army-alpha:aircraft")
    reserve = state.reserve_state_for_unit("army-alpha:aircraft")
    assert reserve is not None
    assert reserve.is_unarrived
    assert reserve.required_arrival_battle_round is None
    events = session.lifecycle.decision_controller.event_log.records
    assert len([e for e in events if e.event_type == AIRCRAFT_RETURN_EVENT]) == 1
    payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(copy.deepcopy(payload)).to_payload() == payload
    persisted = session.to_persistence_payload()
    clone = LocalGameSession.from_persistence_payload(persisted)
    assert clone.to_persistence_payload() == persisted
    for player in state.player_ids:
        assert clone.view(viewer_player_id=player) == session.view(viewer_player_id=player)
        assert clone.events_since(
            EventStreamCursor(), viewer_player_id=player
        ) == session.events_since(
            EventStreamCursor(),
            viewer_player_id=player,
        )
    assert "object at 0x" not in json.dumps(persisted)


def test_order66_own_turn_end_keeps_aircraft_on_battlefield() -> None:
    session = _order66_session(turn_owner="player-a")
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.battlefield_state.is_unit_placed("army-alpha:aircraft")
    assert not any(
        e.event_type == AIRCRAFT_RETURN_EVENT
        for e in session.lifecycle.decision_controller.event_log.records
    )


def test_order66_retired_hover_payload_fails_closed() -> None:
    session = _order66_session()
    payload = session.lifecycle.to_payload()
    assert payload["state"] is not None
    cast(dict[str, object], payload["state"])["hover_mode_states"] = []
    with pytest.raises(GameLifecycleError, match="Retired Hover"):
        GameLifecycle.from_payload(payload)


def test_order66_source_rows_are_hash_pinned_and_authorized() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_aircraft_2026_09 as source,
    )

    assert {row.section_id for row in source.source_rules()} == {"23.01", "23.02", "23.03", "23.04"}
    assert (
        source.source_package().source_catalog.package_id.package_name == source.SOURCE_PACKAGE_ID
    )
    with pytest.raises(source.AircraftSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(b"{}")


@pytest.mark.parametrize("flying", [False, True])
def test_order66_charge_and_fight_targets_use_fly_not_skies_choice(flying: bool) -> None:
    from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind
    from warhammer40k_core.engine.charge_targets import charge_target_candidates
    from warhammer40k_core.engine.fight_movement_mode_authority import (
        legal_consolidation_modes,
        legal_pile_in_target_rules_unit_ids,
    )
    from warhammer40k_core.engine.fight_resolution import (
        legal_pile_in_target_unit_ids,
        melee_target_unit_ids,
    )
    from warhammer40k_core.engine.surge_movement import closest_surge_targets

    state, mover, enemy = _aircraft_engagement_battle_state(include_non_aircraft_enemy=True)
    if flying:
        state.army_definitions = [
            replace(
                army,
                units=tuple(
                    with_unit_keywords(unit, keywords=(*unit.keywords, "FLY"))
                    if unit.unit_instance_id == mover.unit_instance_id
                    else unit
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ]
    scenario = _scenario_from_state(state)
    candidates = charge_target_candidates(
        state=state,
        unit_instance_id=mover.unit_instance_id,
        ruleset_descriptor=_ruleset(),
    )
    aircraft = next(c for c in candidates if c.target_unit_instance_id == enemy.unit_instance_id)
    assert aircraft.is_legal is flying
    for targets in (
        legal_pile_in_target_unit_ids(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            unit_instance_id=mover.unit_instance_id,
        ),
        melee_target_unit_ids(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            unit_instance_id=mover.unit_instance_id,
        ),
    ):
        assert (enemy.unit_instance_id in targets) is flying
        assert "army-beta:enemy-infantry" in targets
    aircraft_targets = melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_instance_id=enemy.unit_instance_id,
    )
    assert (mover.unit_instance_id in aircraft_targets) is flying
    for targets in (
        legal_pile_in_target_rules_unit_ids(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            unit_instance_id=mover.unit_instance_id,
            state=state,
        ),
        closest_surge_targets(scenario=scenario, unit_instance_id=mover.unit_instance_id),
    ):
        assert (enemy.unit_instance_id in targets) is flying
        assert "army-beta:enemy-infantry" in targets
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement("army-beta:enemy-infantry")
    )
    assert legal_consolidation_modes(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_instance_id=mover.unit_instance_id,
        objective_markers=(),
        state=state,
    ) == ((ConsolidationModeKind.ONGOING,) if flying else ())


@pytest.mark.parametrize("action", ["normal", "advance", "charge"])
def test_order66_direct_movement_resolvers_cannot_move_aircraft(action: str) -> None:
    from warhammer40k_core.engine.charge_move_resolution import resolve_charge_move

    scenario, aircraft, enemy = _aircraft_scenario()
    placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    witness = _single_model_forward_witness(placement, movement_inches=1)
    result: NormalMoveResolution | AdvanceMoveResolution
    if action == "normal":
        result = resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            unit_placement=placement,
            path_witness=witness,
        )
    elif action == "advance":
        result = resolve_advance_move(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            unit_placement=placement,
            path_witness=witness,
            advance_roll=_advance_roll_result(aircraft.unit_instance_id),
        )
    else:
        with pytest.raises(GameLifecycleError, match="aircraft_ingress_only"):
            resolve_charge_move(
                scenario=scenario,
                ruleset_descriptor=_ruleset(),
                unit_placement=placement,
                path_witness=witness,
                selected_target_unit_instance_ids=(enemy.unit_instance_id,),
                maximum_distance_inches=12,
            )
        return
    assert not result.is_valid


def test_order66_mutation_guard_rejects_move_but_allows_departure() -> None:
    state, unit = _aircraft_battle_state(aircraft_pose=Pose.at(10, 10))
    scenario = _scenario_from_state(state)
    moved = _with_unit_first_model_pose(
        scenario=scenario, unit_instance_id=unit.unit_instance_id, pose=Pose.at(11, 10)
    )
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="aircraft_ingress_only"):
        state.replace_battlefield_state(moved.battlefield_state)
    assert state.to_payload() == before
    state.replace_battlefield_state(
        scenario.battlefield_state.without_unit_placement(unit.unit_instance_id)
    )
    assert state.battlefield_state is not None
    assert not state.battlefield_state.is_unit_placed(unit.unit_instance_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("active_player_id", "player-a"),
        ("source_rule_id", "invented"),
        ("component_unit_instance_ids", []),
        ("model_instance_ids", []),
    ],
)
def test_order66_restore_rejects_forged_aircraft_departure(field: str, value: object) -> None:
    session = _order66_session()
    session.advance_until_decision_or_terminal()
    payload = session.lifecycle.to_payload()
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] == AIRCRAFT_RETURN_EVENT:
            cast(dict[str, object], event["payload"])[field] = value
    with pytest.raises(GameLifecycleError, match="Aircraft departure"):
        GameLifecycle.from_payload(payload)


def test_order66_aircraft_policy_roundtrip_rejects_retired_hover() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=_ruleset())
    assert AircraftMovementPolicy.from_payload(policy.to_payload()) == policy
    from warhammer40k_core.engine.aircraft import aircraft_model_ids_for_scenario

    assert aircraft_model_ids_for_scenario(scenario=scenario) == tuple(
        m.model_instance_id for m in aircraft.own_models
    )
    payload = policy.to_payload()
    cast(dict[str, object], payload)["hover_mode_active"] = True
    with pytest.raises(GameLifecycleError, match="Retired Hover"):
        AircraftMovementPolicy.from_payload(payload)


def test_order66_returned_aircraft_uses_facade_ingress_and_retains_keyword() -> None:
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalRequest,
        MovementProposalRequestPayload,
        PlacementProposalPayload,
    )

    session = _order66_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id("army-alpha:aircraft")
    status = session.advance_until_decision_or_terminal()
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            result_id="select-returned",
            option_id="army-alpha:aircraft",
        )
    )
    assert {o.option_id for o in request.options} == {"ingress", "remain_stationary"}
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id, result_id="select-ingress", option_id="ingress"
        )
    )
    assert isinstance(request.payload, dict)
    context = MovementProposalRequest.from_payload(
        cast(MovementProposalRequestPayload, request.payload["proposal_request"])
    )
    attempted = before.with_model_placements(
        tuple(replace(m, pose=Pose.at(12, 3)) for m in before.model_placements)
    )
    proposal = PlacementProposalPayload(
        proposal_request_id=context.request_id,
        proposal_kind=context.proposal_kind,
        unit_instance_id=before.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=attempted,
    )
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="arrive-again",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome.payload
    assert state.battlefield_state.is_unit_placed(before.unit_instance_id)
    reserve = state.reserve_state_for_unit(before.unit_instance_id)
    assert reserve is not None
    assert not reserve.is_unarrived
    assert state.phase_movement_history[-1].is_ingress
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    assert (
        "AIRCRAFT"
        in rules_unit_view_by_id(state=state, unit_instance_id=before.unit_instance_id).keywords
    )
    saved = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(copy.deepcopy(saved)).to_payload() == saved

    returns: list[EventRecord] = []
    for index in range(20):
        returns = [
            row
            for row in session.lifecycle.decision_controller.event_log.records
            if row.event_type == AIRCRAFT_RETURN_EVENT
        ]
        if len(returns) == 2:
            break
        request = _decision_request(session.advance_until_decision_or_terminal())
        if request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"cycle:{index}",
                payload=stratagem_decline_payload(),
            )
            continue
        option = next(
            (
                row
                for row in request.options
                if row.option_id.startswith("complete_")
                or row.option_id == "remain_stationary"
                or "decline" in row.option_id
            ),
            request.options[0],
        )
        session.submit_option(
            request_id=request.request_id, result_id=f"cycle:{index}", option_id=option.option_id
        )
    assert len(returns) == 2
    assert returns[0].event_id != returns[1].event_id
    saved = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(copy.deepcopy(saved)).to_payload() == saved


def test_order66_mixed_fly_unit_melee_requires_individual_flying_model() -> None:
    from warhammer40k_core.engine.aircraft_rules import aircraft_melee_target_ids

    scenario, aircraft, infantry = _aircraft_scenario()
    first, *others = infantry.own_models
    first = replace(
        first,
        keyword_assignment=replace(first.keyword_assignment, keywords=(*first.keywords, "FLY")),
    )
    mixed = replace(infantry, own_models=(first, *others))
    scenario = replace(
        scenario,
        armies=tuple(
            replace(
                army,
                units=tuple(
                    mixed if unit.unit_instance_id == infantry.unit_instance_id else unit
                    for unit in army.units
                ),
            )
            for army in scenario.armies
        ),
    )
    for model in mixed.own_models:
        targets = aircraft_melee_target_ids(
            scenario=scenario,
            unit_instance_id=mixed.unit_instance_id,
            model_instance_id=model.model_instance_id,
            target_ids=(aircraft.unit_instance_id,),
        )
        assert bool(targets) is (model.model_instance_id == first.model_instance_id)


def test_aircraft_movement_budget_helpers_fail_fast() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    model = scenario.model_instance_for_placement(model_placement)
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=_ruleset())

    with pytest.raises(GameLifecycleError, match="Movement model must be"):
        _model_base_movement_inches(
            model=cast(ModelInstance, object()),
            aircraft_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="AircraftMovementPolicy"):
        _model_base_movement_inches(
            model=model,
            aircraft_policy=cast(AircraftMovementPolicy, object()),
        )
    with pytest.raises(GameLifecycleError, match="movement_phase_action"):
        _model_movement_budget_inches(
            model=model,
            aircraft_policy=policy,
            ruleset_descriptor=_ruleset(),
            movement_bonus_inches=0,
            movement_mode=MovementMode.NORMAL,
            movement_phase_action=cast(MovementPhaseActionKind, object()),
        )


def test_other_models_can_transit_aircraft_but_not_end_on_them() -> None:
    mover = _geometry_model("mover", x=1.0, y=1.0)
    enemy_aircraft = _geometry_model("enemy-aircraft", x=3.0, y=1.0)
    transit_witness = PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(6.2, 1.0))),))
    blocked = PathValidationContext(
        moving_model=mover,
        witness=transit_witness,
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_engagement_horizontal_inches=_engagement_horizontal_inches(),
        enemy_engagement_vertical_inches=_engagement_vertical_inches(),
        enemy_models=(enemy_aircraft,),
    ).validate()
    allowed = PathValidationContext(
        moving_model=mover,
        witness=transit_witness,
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_engagement_horizontal_inches=_engagement_horizontal_inches(),
        enemy_engagement_vertical_inches=_engagement_vertical_inches(),
        enemy_models=(enemy_aircraft,),
        aircraft_model_ids=(enemy_aircraft.model_id,),
    ).validate()
    endpoint = PathValidationContext(
        moving_model=mover,
        witness=PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(3.0, 1.0))),)),
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_engagement_horizontal_inches=_engagement_horizontal_inches(),
        enemy_engagement_vertical_inches=_engagement_vertical_inches(),
        enemy_models=(enemy_aircraft,),
        aircraft_model_ids=(enemy_aircraft.model_id,),
    ).validate()

    assert not blocked.is_valid
    assert blocked.violations[0].violation_code == "enemy_model_base_crossed"
    assert allowed.is_valid
    assert not endpoint.is_valid
    assert endpoint.violations[0].violation_code == "end_on_model_overlap"


def test_non_aircraft_engaged_only_by_enemy_aircraft_can_normal_move_and_advance() -> None:
    state, mover, _aircraft = _aircraft_engagement_battle_state(include_non_aircraft_enemy=False)
    _handler, _decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=mover.unit_instance_id,
    )

    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    }


def test_non_aircraft_engaged_by_aircraft_and_enemy_unit_must_remain_or_fall_back() -> None:
    state, mover, _aircraft = _aircraft_engagement_battle_state(include_non_aircraft_enemy=True)
    _handler, _decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=mover.unit_instance_id,
    )

    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}",
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}",
    }


def test_normal_and_advance_can_transit_enemy_aircraft_but_not_end_in_engagement() -> None:
    state, mover, enemy_aircraft = _aircraft_transit_battle_state()
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(mover.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    aircraft_placement = scenario.battlefield_state.unit_placement_by_id(
        enemy_aircraft.unit_instance_id
    ).model_placements[0]

    transit_witness = PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(14.0, model_placement.pose.position.y),
            ),
        )
    )
    endpoint_witness = PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(
                    aircraft_placement.pose.position.x,
                    model_placement.pose.position.y,
                ),
            ),
        )
    )

    normal_result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=transit_witness,
    )
    advance_result = resolve_advance_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        advance_roll=_advance_roll_result(mover.unit_instance_id),
        path_witness=transit_witness,
    )
    endpoint_result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=endpoint_witness,
    )

    assert normal_result.is_valid
    assert advance_result.is_valid
    assert not endpoint_result.is_valid
    assert endpoint_result.path_validation_results[0].violations[0].violation_code == (
        "enemy_engagement_range_end_forbidden"
    )


def _aircraft_battle_state(*, aircraft_pose: Pose) -> tuple[GameState, UnitInstance]:
    scenario, aircraft, _enemy = _aircraft_scenario()
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=aircraft.unit_instance_id,
        pose=aircraft_pose,
    )
    return _battle_state_from_scenario(scenario), aircraft


def _aircraft_engagement_battle_state(
    *,
    include_non_aircraft_enemy: bool,
) -> tuple[GameState, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="mover-unit",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    beta_selections = [
        _unit_selection(
            unit_selection_id="enemy-aircraft",
            datasheet_id="core-vehicle-monster",
            model_profile_id="core-vehicle-monster",
            model_count=1,
        )
    ]
    if include_non_aircraft_enemy:
        beta_selections.append(
            _unit_selection(
                unit_selection_id="enemy-infantry",
                datasheet_id="core-vehicle-monster",
                model_profile_id="core-vehicle-monster",
                model_count=1,
            )
        )
    beta = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=tuple(beta_selections),
        ),
    )
    enemy_aircraft = with_unit_keywords(
        beta.unit_by_id("army-beta:enemy-aircraft"), keywords=("Aircraft", "Fly", "Vehicle")
    )
    beta = replace(
        beta,
        units=tuple(
            enemy_aircraft if unit.unit_instance_id == enemy_aircraft.unit_instance_id else unit
            for unit in beta.units
        ),
    )
    mover = alpha.unit_by_id("army-alpha:mover-unit")
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10r-engagement-battlefield",
        armies=(alpha, beta),
    )
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=mover.unit_instance_id,
        pose=Pose.at(20.0, 20.0),
    )
    scenario = _place_unit_in_engagement_of_mover(
        scenario=scenario,
        mover=mover,
        enemy=enemy_aircraft,
        direction=1.0,
    )
    if include_non_aircraft_enemy:
        enemy_infantry = beta.unit_by_id("army-beta:enemy-infantry")
        scenario = _place_unit_in_engagement_of_mover(
            scenario=scenario,
            mover=mover,
            enemy=enemy_infantry,
            direction=-1.0,
        )
    return _battle_state_from_scenario(scenario), mover, enemy_aircraft


def _aircraft_transit_battle_state() -> tuple[GameState, UnitInstance, UnitInstance]:
    state, mover, enemy_aircraft = _aircraft_engagement_battle_state(
        include_non_aircraft_enemy=False
    )
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=mover.unit_instance_id,
        pose=Pose.at(6.0, 20.0),
    )
    mover_radius = _first_model_radius_x(mover)
    aircraft_radius = _first_model_radius_x(enemy_aircraft)
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=enemy_aircraft.unit_instance_id,
        pose=Pose.at(9.0, 20.0 + mover_radius + aircraft_radius + 0.5),
    )
    state.battlefield_state = scenario.battlefield_state
    return state, mover, enemy_aircraft


def _battle_state_from_scenario(scenario: BattlefieldScenario) -> GameState:
    ruleset = _ruleset()
    return GameState(
        game_id="phase10r-game",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(scenario.armies),
        battlefield_state=scenario.battlefield_state,
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    assert state.battlefield_state is not None
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _single_model_forward_witness(
    unit_placement: UnitPlacement,
    *,
    movement_inches: float,
) -> PathWitness:
    model_placement = unit_placement.model_placements[0]
    facing_radians = math.radians(model_placement.pose.facing.degrees)
    return PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(
                    model_placement.pose.position.x + (movement_inches * math.cos(facing_radians)),
                    model_placement.pose.position.y + (movement_inches * math.sin(facing_radians)),
                    z=model_placement.pose.position.z,
                    facing_degrees=model_placement.pose.facing.degrees,
                ),
            ),
        )
    )


def _movement_action_request_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    handler = core_movement_handler(state=state, ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert selection_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=unit_instance_id,
        result_id=f"{unit_instance_id}:select-move",
    )
    assert selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return handler, decisions, action_request


def _submit_handler_decision(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    status = handler.apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )
    return submit_default_handler_movement_proposal_if_pending(
        handler=handler,
        state=state,
        decisions=decisions,
        status=status,
        result_id=f"{result_id}-proposal",
    )


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _with_unit_first_model_pose(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    pose: Pose,
) -> BattlefieldScenario:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    first_placement = unit_placement.model_placements[0].with_pose(pose)
    updated_placement = unit_placement.with_model_placements(
        (first_placement, *unit_placement.model_placements[1:])
    )
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_placement),
    )


def _place_unit_in_engagement_of_mover(
    *,
    scenario: BattlefieldScenario,
    mover: UnitInstance,
    enemy: UnitInstance,
    direction: float,
) -> BattlefieldScenario:
    mover_placement = scenario.battlefield_state.unit_placement_by_id(mover.unit_instance_id)
    mover_pose = mover_placement.model_placements[0].pose
    gap_inches = _first_model_radius_x(mover) + _first_model_radius_x(enemy) + 0.5
    return _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=enemy.unit_instance_id,
        pose=Pose.at(
            mover_pose.position.x + (direction * gap_inches),
            mover_pose.position.y,
        ),
    )


def _first_model_radius_x(unit: UnitInstance) -> float:
    return unit.own_models[0].geometry.primary_part().radius_x_inches


def _advance_roll_result(unit_instance_id: str) -> AdvanceRollResult:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10r-advance-roll-request",
        game_id="phase10r-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_result = DiceRollResult.from_values(
        roll_id="phase10r-advance-roll",
        spec=request.spec,
        values=[1],
        source="fixed",
    )
    return AdvanceRollResult.from_roll_state(
        request=request,
        roll_state=DiceRollState.from_result(roll_result),
    )


def _aircraft_scenario() -> tuple[BattlefieldScenario, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="aircraft-unit",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    beta = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="enemy-unit",
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
            ),
        ),
    )
    aircraft = with_unit_keywords(
        alpha.unit_by_id("army-alpha:aircraft-unit"),
        keywords=("Aircraft", "Fly", "Hover", "Vehicle"),
    )
    alpha = replace(
        alpha,
        units=tuple(
            aircraft if unit.unit_instance_id == aircraft.unit_instance_id else unit
            for unit in alpha.units
        ),
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10r-battlefield",
        armies=(alpha, beta),
    )
    return scenario, aircraft, beta.unit_by_id("army-beta:enemy-unit")


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=unit_selections,
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _geometry_model(model_id: str, *, x: float, y: float) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x, y),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase10r-test")


def _engagement_horizontal_inches() -> float:
    return _ruleset().engagement_policy.horizontal_inches


def _engagement_vertical_inches() -> float:
    return _ruleset().engagement_policy.vertical_inches


@pytest.mark.parametrize("mode", list(MovementMode))
@pytest.mark.parametrize("friendly", [False, True])
def test_order66_every_move_transits_aircraft_and_preserves_endpoint_collision(
    mode: MovementMode, friendly: bool
) -> None:
    from warhammer40k_core.engine.movement_legality import MovementLegalityContext

    mover = _geometry_model("mover", x=5, y=10)
    blocker = _geometry_model("aircraft", x=8, y=10)
    context = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY", "FLY"),
        ruleset_descriptor=_ruleset(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind="normal_move",
    )
    for endpoint, legal in ((14, True), (8, False)):
        witness = PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(endpoint, 10))),))
        result = context.to_path_validation_context(
            moving_model=mover,
            witness=witness,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            friendly_models=(blocker,) if friendly else (),
            enemy_models=() if friendly else (blocker,),
            aircraft_model_ids=(blocker.model_id,),
        ).validate()
        assert result.is_valid is legal


def test_order66_end_turn_returns_every_aircraft_once() -> None:
    session = _order66_session(fleet_size=2)
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert {row.unit_instance_id for row in state.reserve_states if row.is_unarrived} == {
        "army-alpha:aircraft",
        "army-alpha:aircraft-2",
    }
    events = [
        row
        for row in session.lifecycle.decision_controller.event_log.records
        if row.event_type == AIRCRAFT_RETURN_EVENT
    ]
    assert len(events) == 2
    assert len({row.event_id for row in events}) == 2
    payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(copy.deepcopy(payload)).to_payload() == payload


def test_order66_aircraft_cannot_pile_in_or_consolidate_in_direct_path_owner() -> None:
    from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
    from warhammer40k_core.engine.fight_movement_paths import validate_fight_paths

    scenario, aircraft, _enemy = _aircraft_scenario()
    placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    witness = _single_model_forward_witness(placement, movement_inches=1)
    for mode, kind in (
        (MovementMode.PILE_IN, ModelDisplacementKind.PILE_IN),
        (MovementMode.CONSOLIDATE, ModelDisplacementKind.CONSOLIDATE),
    ):
        paths, _terrain = validate_fight_paths(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            before=placement,
            after=placement,
            witness=witness,
            movement_mode=mode,
            displacement_kind=kind,
            distance_budget_inches=3,
        )
        assert not paths[0].is_valid
        assert paths[0].violations[0].violation_code == "aircraft_ingress_only"


def test_order66_return_preserves_embarked_transport_cargo_and_restore() -> None:
    session = _order66_session(loaded_transport=True)
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    reserve = state.reserve_state_for_unit("army-alpha:aircraft")
    assert reserve is not None
    assert reserve.embarked_unit_instance_ids == ("army-alpha:passenger",)
    cargo = state.transport_cargo_state_for_transport("army-alpha:aircraft")
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == reserve.embarked_unit_instance_ids
    assert state.battlefield_state is not None
    assert not state.battlefield_state.is_unit_placed("army-alpha:passenger")
    saved = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(copy.deepcopy(saved)).to_payload() == saved


def test_order66_engagement_exception_uses_aircraft_unit_not_contacting_model() -> None:
    from warhammer40k_core.engine.aircraft import aircraft_model_ids_for_scenario
    from warhammer40k_core.engine.phases.movement import _movement_action_availability_context

    scenario, aircraft, infantry = _aircraft_scenario()
    ground = with_unit_keywords(aircraft, keywords=("VEHICLE",))
    first, *others = infantry.own_models
    first = replace(
        first,
        keyword_assignment=replace(
            first.keyword_assignment, keywords=(*first.keywords, "AIRCRAFT")
        ),
    )
    mixed = replace(infantry, own_models=(first, *others))
    scenario = replace(
        scenario,
        armies=tuple(
            replace(
                army,
                units=tuple(
                    ground
                    if u.unit_instance_id == ground.unit_instance_id
                    else mixed
                    if u.unit_instance_id == mixed.unit_instance_id
                    else u
                    for u in army.units
                ),
            )
            for army in scenario.armies
        ),
    )
    scenario = _with_unit_first_model_pose(
        scenario=scenario, unit_instance_id=ground.unit_instance_id, pose=Pose.at(10, 10)
    )
    enemy_placement = scenario.battlefield_state.unit_placement_by_id(mixed.unit_instance_id)
    enemy_placement = enemy_placement.with_model_placements(
        tuple(
            replace(m, pose=Pose.at(30, 30) if index == 0 else Pose.at(14, 10 + (index - 1) * 1.3))
            for index, m in enumerate(enemy_placement.model_placements)
        )
    )
    scenario = replace(
        scenario, battlefield_state=scenario.battlefield_state.with_unit_placement(enemy_placement)
    )
    context = _movement_action_availability_context(
        scenario=scenario,
        unit_placement=scenario.battlefield_state.unit_placement_by_id(ground.unit_instance_id),
        ruleset_descriptor=_ruleset(),
    )
    assert context.enemy_aircraft_engagement_model_ids
    assert not context.enemy_engagement_model_ids
    assert MovementPhaseActionKind.NORMAL_MOVE in context.evaluate().available_actions
    assert MovementPhaseActionKind.ADVANCE in context.evaluate().available_actions
    assert aircraft_model_ids_for_scenario(scenario) == (first.model_instance_id,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("effective_keywords", ["FLY"]),
        ("has_aircraft_keyword", False),
        ("uses_aircraft_rules", False),
        ("can_declare_charge", True),
        ("fight_phase_restriction_exposed", False),
        ("other_models_can_move_over_this_aircraft", False),
        ("can_move_over_other_models", False),
    ],
)
def test_order66_policy_rejects_forged_derived_permissions(field: str, value: object) -> None:
    _scenario, aircraft, _enemy = _aircraft_scenario()
    payload = AircraftMovementPolicy.from_unit(
        unit=aircraft, ruleset_descriptor=_ruleset()
    ).to_payload()
    cast(dict[str, object], payload)[field] = value
    with pytest.raises(GameLifecycleError, match="derived keyword authority drift"):
        AircraftMovementPolicy.from_payload(payload)
