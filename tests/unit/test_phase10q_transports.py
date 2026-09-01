from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainSource,
    apply_damage_to_model,
    destroy_model_by_rule,
    is_mortal_wound_feel_no_pain_request,
    model_by_id,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.damage_allocation_targets import DamageKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import (
    EventRecordPayload,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.fight_on_death import restore_model_awaiting_fight_on_death
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.hazard import (
    HAZARD_ROLL_FAILURE_THRESHOLD,
    hazard_roll_spec,
)
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    apply_healing_model_decision,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_model_request,
    mortal_wound_resolution_source_context,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    DECLINE_EMBARK_OPTION_ID,
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FallBackModeKind,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementUnitSelection,
)
from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
    RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND,
    RulesUnitDisembarkSelection,
    apply_rules_unit_combat_disembark_feel_no_pain_decision,
    apply_rules_unit_combat_disembark_to_state,
    resolve_rules_unit_combat_disembark,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import (
    placed_alive_rules_unit_views,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.starting_attached_units import (
    starting_attached_unit_records_for_army,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.transport_state_integrity import (
    validate_transport_cargo_state_consistency,
)
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
    CombatDisembark,
    DestroyedTransportDisembark,
    DisembarkedUnitState,
    DisembarkModeKind,
    DisembarkResolution,
    DisembarkSelection,
    EmbarkResolution,
    EmbarkSelection,
    FiringDeckResolution,
    FiringDeckSelection,
    FiringDeckWeaponSelection,
    TransportCapacityProfile,
    TransportCargoState,
    TransportHazardMortalWounds,
    TransportHazardMortalWoundsPayload,
    TransportMovementStatus,
    TransportOperationViolation,
    TransportOperationViolationCode,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
    apply_combat_disembark_to_battlefield,
    apply_destroyed_transport_disembark_to_battlefield,
    apply_disembark_to_battlefield,
    apply_embark_to_battlefield,
    apply_transport_hazard_mortal_wound_feel_no_pain_decision,
    apply_transport_hazard_mortal_wounds,
    disembark_mode_kind_from_token,
    resolve_combat_disembark,
    resolve_destroyed_transport_disembark,
    resolve_disembark,
    resolve_embark,
    resolve_firing_deck_selection,
    transport_movement_status_from_token,
    transport_operation_violation_code_from_token,
    transport_restriction_override_kind_from_token,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_embark_removes_unit_to_transport_cargo_and_emits_records() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    cargo_state = _cargo_state(transport=transport)

    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=cargo_state,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )

    assert resolution.is_valid
    assert resolution.updated_cargo_state is not None
    assert resolution.updated_cargo_state.embarked_unit_instance_ids == (
        passenger.unit_instance_id,
    )
    assert resolution.transition_batch is not None
    assert {record.removal_kind for record in resolution.transition_batch.removals} == {
        BattlefieldRemovalKind.EMBARK
    }
    assert {record.destination_id for record in resolution.transition_batch.removals} == {
        transport.unit_instance_id
    }

    updated_battlefield = apply_embark_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        embark=resolution,
    )
    assert passenger.unit_instance_id not in {
        placement.unit_instance_id
        for army in updated_battlefield.placed_armies
        for placement in army.unit_placements
    }


def test_embark_rejects_unit_forbidden_by_persisting_effect() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    restriction_effect = PersistingEffect(
        effect_id="nomads:embark-forbidden",
        source_rule_id="aeldari:path-of-the-outcast:nomads-of-the-hidden-way",
        owner_player_id="player-a",
        target_unit_instance_ids=(passenger.unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
        effect_payload={
            "effect_kind": "aeldari_path_of_the_outcast_nomads_restriction",
            "embark_transport_forbidden": True,
        },
    )

    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=_cargo_state(transport=transport),
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
        persisting_effects=(restriction_effect,),
    )

    assert not resolution.is_valid
    assert {violation.violation_code for violation in resolution.violations} == {
        TransportOperationViolationCode.EMBARK_FORBIDDEN_BY_EFFECT
    }
    assert resolution.violations[0].source_rule_id == restriction_effect.source_rule_id


def test_embark_validates_distance_for_every_attached_rules_unit_model() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    far_leader_placement = _unit_placement_at(
        leader,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(25.0, 25.0),),
    )
    scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(far_leader_placement),
    )

    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=_cargo_state(transport=transport, max_model_count=6),
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=bodyguard.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(bodyguard.unit_instance_id),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )

    assert not resolution.is_valid
    assert resolution.updated_cargo_state is None
    assert resolution.transition_batch is None
    assert {
        (violation.violation_code, violation.model_instance_id)
        for violation in resolution.violations
    } == {
        (
            TransportOperationViolationCode.EMBARK_DISTANCE,
            leader.own_models[0].model_instance_id,
        )
    }


@pytest.mark.parametrize("destroyed_role", ["leader", "bodyguard"])
def test_embark_ignores_wholly_destroyed_attached_component(
    destroyed_role: str,
) -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    destroyed = leader if destroyed_role == "leader" else bodyguard
    living = bodyguard if destroyed_role == "leader" else leader
    scenario = _with_destroyed_attached_component(
        scenario,
        unit_instance_id=destroyed.unit_instance_id,
    )

    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=_cargo_state(transport=transport, max_model_count=6),
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=living.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(living.unit_instance_id),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )

    assert resolution.is_valid
    assert resolution.updated_cargo_state is not None
    assert resolution.updated_cargo_state.embarked_unit_instance_ids == (living.unit_instance_id,)
    assert resolution.transition_batch is not None
    assert {removal.model_instance_id for removal in resolution.transition_batch.removals} == {
        model.model_instance_id for model in living.own_models
    }


def test_post_loss_embark_then_disembark_restores_retained_rules_unit_presence() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    scenario = _with_destroyed_attached_component(
        scenario,
        unit_instance_id=leader.unit_instance_id,
    )
    state = _battle_state(scenario, game_id="phase10q-post-loss-embark-disembark")
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unplaced_models_marked_removed(
            tuple(model.model_instance_id for model in leader.own_models)
        )
    )
    state.record_transport_cargo_state(_cargo_state(transport=transport, max_model_count=6))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=bodyguard,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=0.5,
            result_id="phase10q-post-loss-normal-move",
        )
    )
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=embark_request,
            option_id=transport.unit_instance_id,
            result_id="phase10q-post-loss-embark",
        )
        is None
    )

    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == (bodyguard.unit_instance_id,)

    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    state.battle_round = 2
    state.replace_movement_phase_state(
        MovementPhaseState(battle_round=2, active_player_id="player-a")
    )
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert attached_id in {option.option_id for option in selection_request.options}
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=attached_id,
            result_id="phase10q-post-loss-select-passengers",
        )
        is None
    )
    disembark_action_request = _decision_request(
        handler.begin_phase(state=state, decisions=decisions)
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_action_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-post-loss-disembark-action",
        )
    )
    status = _submit_rules_unit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        placement=RulesUnitPlacement(
            rules_unit_instance_id=attached_id,
            component_unit_placements=(
                _unit_placement_at(
                    bodyguard,
                    army_id="army-alpha",
                    player_id="player-a",
                    poses=(
                        Pose.at(8.6, 13.0),
                        Pose.at(10.0, 13.0),
                        Pose.at(11.4, 13.0),
                        Pose.at(9.3, 14.2),
                        Pose.at(10.7, 14.2),
                    ),
                ),
            ),
        ),
        transport=transport,
        result_id="phase10q-post-loss-disembark-placement",
    )

    assert status is None
    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == ()
    present_views = {
        view.unit_instance_id: view for view in placed_alive_rules_unit_views(state=state)
    }
    assert attached_id in present_views
    assert present_views[attached_id].component_unit_instance_ids == tuple(
        sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
    )
    assert tuple(
        component.unit.unit_instance_id
        for component in present_views[attached_id].living_components
    ) == (bodyguard.unit_instance_id,)


@pytest.mark.parametrize("destruction_kind", ["damage", "rule"])
def test_destroying_last_model_of_embarked_component_reconciles_current_cargo(
    destruction_kind: str,
) -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id=f"phase10q-embarked-destruction-{destruction_kind}")
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(
            bodyguard.unit_instance_id
        ).without_unit_placement(leader.unit_instance_id)
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=component_ids,
            started_unit_ids=component_ids,
            battle_round=1,
            max_model_count=6,
        )
    )
    leader_model = leader.own_models[0]

    if destruction_kind == "damage":
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=leader.unit_instance_id,
            model_instance_id=leader_model.model_instance_id,
            damage=leader_model.wounds_remaining,
            damage_kind=DamageKind.MORTAL,
            remove_destroyed_model=False,
        )
    else:
        destroy_model_by_rule(
            state=state,
            model_instance_id=leader_model.model_instance_id,
            remove_from_battlefield=False,
        )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unplaced_models_marked_removed(
            (leader_model.model_instance_id,)
        )
    )

    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == (bodyguard.unit_instance_id,)
    assert cargo.started_phase_embarked_unit_instance_ids == component_ids
    assert cargo.disembarked_this_phase_unit_instance_ids == ()
    validate_transport_cargo_state_consistency(state=state)


def test_destroyed_embarked_component_reconciles_unarrived_transport_reserve_manifest() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-reserve-embarked-destruction")
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(bodyguard.unit_instance_id)
        .without_unit_placement(leader.unit_instance_id)
        .without_unit_placement(transport.unit_instance_id)
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=component_ids,
            max_model_count=6,
        )
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=transport.unit_instance_id,
            reserve_kind=ReserveKind.RESERVES,
            embarked_unit_instance_ids=component_ids,
        )
    )

    leader_model = leader.own_models[0]
    destroy_model_by_rule(
        state=state,
        model_instance_id=leader_model.model_instance_id,
        remove_from_battlefield=False,
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unplaced_models_marked_removed(
            (leader_model.model_instance_id,)
        )
    )

    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    reserve = state.reserve_state_for_unit(transport.unit_instance_id)
    assert cargo is not None
    assert reserve is not None
    assert cargo.embarked_unit_instance_ids == (bodyguard.unit_instance_id,)
    assert reserve.embarked_unit_instance_ids == cargo.embarked_unit_instance_ids
    validate_transport_cargo_state_consistency(state=state)


def test_transport_integrity_rejects_destroyed_component_retained_as_current_cargo() -> None:
    scenario, _bodyguard, leader, transport = _attached_embark_ready_scenario()
    scenario = _with_destroyed_attached_component(
        scenario,
        unit_instance_id=leader.unit_instance_id,
    )
    state = _battle_state(scenario, game_id="phase10q-stale-destroyed-cargo")
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unplaced_models_marked_removed(
            tuple(model.model_instance_id for model in leader.own_models)
        )
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=6,
                allowed_keywords=("INFANTRY", "MONSTER"),
            ),
            embarked_unit_instance_ids=(leader.unit_instance_id,),
        )
    )

    with pytest.raises(
        GameLifecycleError,
        match="must not retain a wholly destroyed component",
    ):
        validate_transport_cargo_state_consistency(state=state)


def test_embarked_units_are_available_for_unified_movement_selection() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    state = _battle_state(scenario)
    state.battlefield_state = scenario.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(cargo_state)
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    decisions = DecisionController()

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=state,
        decisions=decisions,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert {option.option_id for option in status.decision_request.options} == {
        passenger.unit_instance_id,
        transport.unit_instance_id,
    }
    passenger_option = status.decision_request.option_by_id(passenger.unit_instance_id)
    passenger_option_payload = cast(dict[str, JsonValue], passenger_option.payload)
    assert passenger_option_payload["unit_location"] == "embarked"
    assert passenger_option_payload["transport_unit_instance_id"] == (transport.unit_instance_id)
    assert passenger.unit_instance_id in state.movement_phase_state.legal_unit_ids(state)


def test_attached_rules_unit_is_one_complete_unified_movement_candidate() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-unified-candidate")
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    decisions = DecisionController()

    request = _decision_request(
        MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
            state=state,
            decisions=decisions,
        )
    )

    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    model_ids = tuple(
        sorted(model.model_instance_id for unit in (bodyguard, leader) for model in unit.own_models)
    )
    assert {option.option_id for option in request.options} == {
        attached_id,
        transport.unit_instance_id,
    }
    assert bodyguard.unit_instance_id not in {option.option_id for option in request.options}
    assert leader.unit_instance_id not in {option.option_id for option in request.options}
    payload = cast(dict[str, JsonValue], request.option_by_id(attached_id).payload)
    assert payload == {
        "unit_instance_id": attached_id,
        "component_unit_instance_ids": list(component_ids),
        "model_instance_ids": list(model_ids),
        "unit_location": "battlefield",
    }


@pytest.mark.parametrize(
    ("action", "movement_mode", "option_id", "dx"),
    [
        (
            MovementPhaseActionKind.REMAIN_STATIONARY,
            MovementMode.NORMAL,
            MovementPhaseActionKind.REMAIN_STATIONARY.value,
            0.0,
        ),
        (
            MovementPhaseActionKind.NORMAL_MOVE,
            MovementMode.NORMAL,
            MovementPhaseActionKind.NORMAL_MOVE.value,
            0.25,
        ),
        (
            MovementPhaseActionKind.ADVANCE,
            MovementMode.ADVANCE,
            MovementPhaseActionKind.ADVANCE.value,
            0.25,
        ),
        (
            MovementPhaseActionKind.FALL_BACK,
            MovementMode.FALL_BACK,
            f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}",
            3.0,
        ),
    ],
)
def test_attached_rules_unit_completes_one_grouped_movement_activation(
    action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    option_id: str,
    dx: float,
) -> None:
    scenario, bodyguard, leader, _transport = _attached_embark_ready_scenario()
    if action is MovementPhaseActionKind.FALL_BACK:
        enemy = scenario.armies[1].unit_by_id("army-beta:enemy-unit")
        scenario = BattlefieldScenario(
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state.with_unit_placement(
                _unit_placement_at(
                    enemy,
                    army_id="army-beta",
                    player_id="player-b",
                    poses=(
                        Pose.at(6.0, 13.0),
                        Pose.at(4.6, 13.0),
                        Pose.at(3.2, 13.0),
                        Pose.at(5.3, 14.2),
                        Pose.at(3.9, 14.2),
                    ),
                )
            ),
        )
    state = _battle_state(
        scenario,
        game_id=f"phase10q-attached-{action.value}-activation",
    )
    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    before_x = {
        model.model_instance_id: next(
            placed.pose.position.x
            for placed in scenario.battlefield_state.unit_placement_by_id(
                unit.unit_instance_id
            ).model_placements
            if placed.model_instance_id == model.model_instance_id
        )
        for unit in (bodyguard, leader)
        for model in unit.own_models
    }
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.active_selection is not None
    assert state.movement_phase_state.active_selection.unit_instance_id == attached_id

    if action is MovementPhaseActionKind.REMAIN_STATIONARY:
        status = _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=option_id,
            result_id=f"phase10q-attached-{action.value}",
        )
    else:
        status = _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=option_id,
            unit=bodyguard,
            movement_phase_action=action,
            movement_mode=movement_mode,
            dx=dx,
            fall_back_mode=(
                FallBackModeKind.ORDERED_RETREAT
                if action is MovementPhaseActionKind.FALL_BACK
                else None
            ),
            result_id=f"phase10q-attached-{action.value}",
        )

    assert status is None
    movement_state_after = state.movement_phase_state
    assert movement_state_after is not None
    assert movement_state_after.active_selection is None
    assert movement_state_after.selected_unit_ids == (attached_id,)
    assert movement_state_after.moved_unit_ids == (attached_id,)
    assert state.battlefield_state is not None
    for unit in (bodyguard, leader):
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        for model in placement.model_placements:
            assert model.pose.position.x == before_x[model.model_instance_id] + dx
    completion_payloads = [
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == "movement_activation_completed"
    ]
    assert len(completion_payloads) == 1
    assert completion_payloads[0]["unit_instance_id"] == attached_id
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    assert GameLifecycle.from_payload(payload).to_payload() == payload


def test_attached_rules_unit_movement_rejects_cross_component_coherency_break() -> None:
    scenario, bodyguard, leader, _transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-coherency")
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    proposal_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase10q-attached-coherency-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert state.battlefield_state is not None
    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=proposal.unit_instance_id,
    )
    placement = RulesUnitPlacement.from_battlefield(
        view=rules_unit,
        battlefield_state=state.battlefield_state,
    )
    witness = PathWitness.for_paths(
        tuple(
            model_path
            for component in placement.component_unit_placements
            for model_path in _shift_witness(
                component,
                dx=5.0 if component.unit_instance_id == leader.unit_instance_id else 0.0,
            ).model_paths
        )
    )
    before_battlefield = state.battlefield_state
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        witness=witness,
        movement_mode=MovementMode.NORMAL.value,
    ).to_payload()

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=proposal_request,
        payload=validate_json_value(payload),
        result_id="phase10q-attached-coherency-invalid",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    invalid_payload = cast(dict[str, JsonValue], status.payload)
    assert invalid_payload["violation_code"] == "unit_coherency_broken"


def test_attached_rules_unit_partial_cargo_location_fails_closed() -> None:
    scenario, bodyguard, _leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-partial-cargo")
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        bodyguard.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(bodyguard.unit_instance_id,),
            started_unit_ids=(bodyguard.unit_instance_id,),
            battle_round=1,
        )
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )

    with pytest.raises(
        GameLifecycleError,
        match="exactly one authoritative movement location",
    ):
        MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
            state=state,
            decisions=DecisionController(),
        )


def test_lifecycle_replay_accepts_embarked_models_accounted_by_transport_cargo_state() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    lifecycle = GameLifecycle.from_payload(payload)

    assert lifecycle.state is not None
    assert lifecycle.state.embarked_model_ids() == tuple(
        model.model_instance_id for model in passenger.own_models
    )


def test_lifecycle_replay_accepts_damaged_embarked_unit_with_survivor_capacity() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario, game_id="phase10q-damaged-embarked-round-trip")
    destroyed_model = passenger.own_models[-1]
    damaged_passenger = replace(
        passenger,
        own_models=tuple(
            replace(model, wounds_remaining=0)
            if model.model_instance_id == destroyed_model.model_instance_id
            else model
            for model in passenger.own_models
        ),
    )
    alpha_army = state.army_definitions[0]
    state.army_definitions[0] = replace(
        alpha_army,
        units=tuple(
            damaged_passenger if unit.unit_instance_id == passenger.unit_instance_id else unit
            for unit in alpha_army.units
        ),
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (destroyed_model.model_instance_id,)
    ).without_unit_placement(passenger.unit_instance_id)
    alive_model_ids = tuple(
        model.model_instance_id for model in damaged_passenger.own_models if model.is_alive
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            max_model_count=len(alive_model_ids),
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    lifecycle = GameLifecycle.from_payload(payload)

    assert lifecycle.state is not None
    assert lifecycle.state.embarked_model_ids() == alive_model_ids
    assert lifecycle.to_payload() == payload

    omitted_casualty_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    omitted_casualty_state = omitted_casualty_payload["state"]
    assert isinstance(omitted_casualty_state, dict)
    battlefield_payload = omitted_casualty_state["battlefield_state"]
    assert isinstance(battlefield_payload, dict)
    removed_model_ids = battlefield_payload["removed_model_ids"]
    assert isinstance(removed_model_ids, list)
    removed_model_ids.remove(destroyed_model.model_instance_id)

    with pytest.raises(
        GameLifecycleError,
        match="destroyed embarked unit models must have exact removal state",
    ):
        GameLifecycle.from_payload(omitted_casualty_payload)


@pytest.mark.parametrize(
    ("capacity", "expected_kind", "expected_wounds", "remains_destroyed"),
    [
        (5, HealingStepKind.REVIVE_MODEL_EMBARKED, 1, False),
        (4, HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY, 0, True),
    ],
)
def test_embarked_model_revival_requires_remaining_transport_capacity_without_destroyed_trigger(
    capacity: int,
    expected_kind: HealingStepKind,
    expected_wounds: int,
    remains_destroyed: bool,
) -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario, game_id=f"phase10q-embarked-revival-{capacity}")
    destroyed_model = passenger.own_models[-1]
    revived_passenger = replace(
        passenger,
        own_models=tuple(
            replace(model, wounds_remaining=0)
            if model.model_instance_id == destroyed_model.model_instance_id
            else model
            for model in passenger.own_models
        ),
    )
    alpha_army = state.army_definitions[0]
    state.army_definitions[0] = replace(
        alpha_army,
        units=tuple(
            revived_passenger if unit.unit_instance_id == passenger.unit_instance_id else unit
            for unit in alpha_army.units
        ),
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (destroyed_model.model_instance_id,)
    ).without_unit_placement(passenger.unit_instance_id)
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            max_model_count=capacity,
        )
    )

    decisions = DecisionController()
    blocked, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=HealingEffect(
            effect_id=f"phase10q-embarked-revival-effect-{capacity}",
            target_unit_instance_id=passenger.unit_instance_id,
            amount=1,
            opposing_player_id="player-b",
            source_rule_id=(
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:"
                "01.02.03-embarked-model-return"
            ),
        ),
    )

    assert request is not None
    assert len(request.options) == 1
    resolved, follow_up = apply_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset(),
        effect=blocked,
        result=DecisionResult.for_request(
            result_id=f"phase10q-embarked-revival-result-{capacity}",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )
    assert follow_up is None
    assert resolved.resolved_steps[0].step_kind is expected_kind
    assert (
        model_by_id(
            state=state, model_instance_id=destroyed_model.model_instance_id
        ).wounds_remaining
        == expected_wounds
    )
    assert state.battlefield_state is not None
    assert (
        destroyed_model.model_instance_id in state.battlefield_state.removed_model_ids
    ) is remains_destroyed
    assert len(decisions.records) == 1
    assert not any(event.event_type == "model_destroyed" for event in decisions.event_log.records)


def test_normal_move_ending_near_transport_emits_embark_decision() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )

    status = _submit_action_and_movement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        unit=passenger,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        dx=6.0,
        result_id="phase10q-normal-move",
    )

    request = _decision_request(status)
    assert request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        DECLINE_EMBARK_OPTION_ID,
        transport.unit_instance_id,
    }


def test_lifecycle_embark_selection_updates_battlefield_and_cargo_atomically() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase10q-normal-move",
        )
    )

    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-embark",
    )

    assert result is None
    assert state.battlefield_state is not None
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == (passenger.unit_instance_id,)
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.moved_unit_ids == (passenger.unit_instance_id,)
    (departure,) = state.primary_battlefield_departure_states
    assert departure.rules_unit_instance_id == passenger.unit_instance_id
    assert departure.component_unit_instance_ids == (passenger.unit_instance_id,)
    assert departure.departed_component_unit_instance_ids == (passenger.unit_instance_id,)
    assert departure.removed_model_instance_ids == passenger.own_model_ids()
    assert departure.removal_kind is BattlefieldRemovalKind.EMBARK
    assert departure.source_id == "phase10q-embark"

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


@pytest.fixture(scope="module")
def authenticated_embark_lifecycle_payload() -> GameLifecyclePayload:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase17n-embark-integrity")
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase17n-embark-integrity-normal-move",
        )
    )
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=embark_request,
            option_id=transport.unit_instance_id,
            result_id="phase17n-embark-integrity-result",
        )
        is None
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    assert GameLifecycle.from_payload(payload).state is not None
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("mutation_payload", "Embark mutation event payload must be an object"),
        ("mutation_result_id", "Embark mutation result_id must be an identifier"),
        ("mutation_duplicate", "Embark mutation result identity is duplicated"),
        (
            "mutation_missing",
            "Primary EMBARK departure requires one authoritative transport mutation event",
        ),
        ("mutation_timing", "Primary battlefield departure mutation timing drift"),
        ("mutation_unit", "Primary EMBARK mutation selected-unit identity drift"),
        ("transition_object", "Embark transition_batch must be an object"),
        ("transition_fields", "Embark transition_batch fields are malformed"),
        ("transition_non_removal", "Primary EMBARK transition contains non-removal mutation"),
        ("removals_list", "Embark removals must be a list"),
        ("removal_object", "Embark removals item must be an object"),
        ("removal_fields", "Embark removal fields are malformed"),
        ("removal_model", "Embark model_instance_id must be an identifier"),
        ("removal_identity", "Primary EMBARK transition removal identity drift"),
        ("removed_models", "Primary EMBARK transition removed-model identity drift"),
        ("cargo_object", "Embark updated_cargo_state must be an object"),
        ("cargo_fields", "Embark updated_cargo_state fields are malformed"),
        ("cargo_ids_list", "Embark cargo unit IDs must be a string list"),
        ("cargo_ids_string", "Embark cargo unit IDs must be a string list"),
        ("cargo_ids_duplicate", "Embark cargo unit IDs must not contain duplicates"),
        ("cargo_identity", "Primary EMBARK cargo mutation identity drift"),
        ("request_id", "Primary EMBARK departure lacks its accepted transport decision"),
        ("decision_context", "Primary EMBARK decision mutation context drift"),
        (
            "provider_order",
            "Primary EMBARK departure was recorded before its authoritative mutation event",
        ),
    ],
)
def test_authenticated_embark_restore_rejects_integrity_corruption(
    authenticated_embark_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(authenticated_embark_lifecycle_payload, sort_keys=True)),
    )
    _corrupt_authenticated_embark_payload(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


def _corrupt_authenticated_embark_payload(
    *,
    payload: GameLifecyclePayload,
    corruption: str,
) -> None:
    events = payload["decisions"]["event_log"]
    mutation = next(event for event in events if event["event_type"] == "unit_embarked")
    derived = next(
        event for event in events if event["event_type"] == "primary_battlefield_departure_recorded"
    )
    if corruption == "mutation_payload":
        mutation["payload"] = None
        return
    mutation_payload = cast(dict[str, JsonValue], mutation["payload"])
    if corruption == "mutation_result_id":
        mutation_payload["result_id"] = ""
        return
    if corruption == "mutation_duplicate":
        duplicate = cast(
            dict[str, JsonValue],
            json.loads(json.dumps(mutation, sort_keys=True)),
        )
        duplicate["event_id"] = f"event-{len(events) + 1:06d}"
        events.append(cast(EventRecordPayload, duplicate))
        return
    if corruption == "mutation_missing":
        mutation["event_type"] = "unit_embarked_hidden"
        return
    if corruption == "mutation_timing":
        mutation_payload["battle_round"] = 2
        return
    if corruption == "mutation_unit":
        mutation_payload["unit_instance_id"] = "unit-forged"
        return
    transition = cast(dict[str, JsonValue], mutation_payload["transition_batch"])
    if corruption == "transition_object":
        mutation_payload["transition_batch"] = None
        return
    if corruption == "transition_fields":
        transition["forged"] = True
        return
    if corruption == "transition_non_removal":
        transition["placements"] = [{}]
        return
    if corruption == "removals_list":
        transition["removals"] = None
        return
    removals = cast(list[JsonValue], transition["removals"])
    if corruption == "removal_object":
        removals[0] = None
        return
    first_removal = cast(dict[str, JsonValue], removals[0])
    if corruption == "removal_fields":
        first_removal["forged"] = True
        return
    if corruption == "removal_model":
        first_removal["model_instance_id"] = ""
        return
    if corruption == "removal_identity":
        first_removal["removal_kind"] = BattlefieldRemovalKind.DESTROYED.value
        return
    if corruption == "removed_models":
        removals.pop()
        return
    cargo = cast(dict[str, JsonValue], mutation_payload["updated_cargo_state"])
    if corruption == "cargo_object":
        mutation_payload["updated_cargo_state"] = None
        return
    if corruption == "cargo_fields":
        cargo["forged"] = True
        return
    if corruption == "cargo_ids_list":
        cargo["embarked_unit_instance_ids"] = None
        return
    cargo_ids = cast(list[JsonValue], cargo["embarked_unit_instance_ids"])
    if corruption == "cargo_ids_string":
        cargo_ids[0] = 17
        return
    if corruption == "cargo_ids_duplicate":
        cargo_ids.append(cargo_ids[0])
        return
    if corruption == "cargo_identity":
        cargo["player_id"] = "player-b"
        return
    if corruption == "request_id":
        mutation_payload["request_id"] = "request-forged"
        return
    if corruption == "decision_context":
        result_id = cast(str, mutation_payload["result_id"])
        decision = next(
            record
            for record in payload["decisions"]["records"]
            if record["result"]["result_id"] == result_id
        )
        decision_payload = cast(dict[str, JsonValue], decision["result"]["payload"])
        decision_payload["transport_decision"] = "forged"
        selected_option_id = decision["result"]["selected_option_id"]
        selected_option = next(
            option
            for option in decision["request"]["options"]
            if option["option_id"] == selected_option_id
        )
        selected_option["payload"] = cast(JsonValue, decision_payload)
        request_event = next(
            event
            for event in events
            if event["event_type"] == "decision_requested"
            and cast(dict[str, JsonValue], event["payload"])["request_id"]
            == decision["request"]["request_id"]
        )
        request_event["payload"] = cast(JsonValue, decision["request"])
        decision_event = next(
            event
            for event in events
            if event["event_type"] == "decision_recorded"
            and _decision_event_result_id(event) == result_id
        )
        decision_event["payload"] = cast(JsonValue, decision)
        return
    if corruption == "provider_order":
        mutation["event_type"], derived["event_type"] = (
            derived["event_type"],
            mutation["event_type"],
        )
        mutation["payload"], derived["payload"] = derived["payload"], mutation["payload"]
        return
    raise AssertionError(f"unsupported authenticated Embark corruption: {corruption}")


def _decision_event_result_id(event: EventRecordPayload) -> str:
    event_payload = cast(dict[str, JsonValue], event["payload"])
    result_payload = cast(dict[str, JsonValue], event_payload["result"])
    return cast(str, result_payload["result_id"])


def test_lifecycle_attached_rules_unit_embarks_every_component_atomically() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-embark")
    state.record_transport_cargo_state(_cargo_state(transport=transport, max_model_count=6))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=bodyguard,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=0.5,
            result_id="phase10q-attached-normal-move",
        )
    )
    assert embark_request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE

    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-attached-embark-result",
    )

    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    model_ids = tuple(
        sorted(model.model_instance_id for unit in (bodyguard, leader) for model in unit.own_models)
    )
    assert result is None
    assert bodyguard.unit_instance_id not in _placed_unit_ids(state)
    assert leader.unit_instance_id not in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == component_ids
    assert state.embarked_model_ids() == model_ids
    embark_event = _last_event_payload(decisions, "unit_embarked")
    transition_payload = cast(dict[str, object], embark_event["transition_batch"])
    removal_payloads = cast(list[dict[str, object]], transition_payload["removals"])
    assert tuple(sorted(str(row["model_instance_id"]) for row in removal_payloads)) == model_ids
    (departure,) = state.primary_battlefield_departure_states
    assert departure.rules_unit_instance_id == (
        "attached-unit:army-alpha:attached-transport-passengers"
    )
    assert departure.component_unit_instance_ids == component_ids
    assert departure.departed_component_unit_instance_ids == component_ids
    assert departure.removed_model_instance_ids == model_ids
    assert departure.removal_kind is BattlefieldRemovalKind.EMBARK

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()
    restored_cargo = lifecycle.state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert restored_cargo is not None
    assert restored_cargo.embarked_unit_instance_ids == component_ids


def test_attached_rules_unit_embark_then_unified_disembark_is_atomic_and_resumable() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-embark-disembark")
    state.record_transport_cargo_state(_cargo_state(transport=transport, max_model_count=6))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=bodyguard,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=0.5,
            result_id="phase10q-attached-sequence-normal-move",
        )
    )
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=embark_request,
            option_id=transport.unit_instance_id,
            result_id="phase10q-attached-sequence-embark",
        )
        is None
    )

    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    state.battle_round = 2
    state.replace_movement_phase_state(
        MovementPhaseState(battle_round=2, active_player_id="player-a")
    )
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert {option.option_id for option in selection_request.options} == {
        attached_id,
        transport.unit_instance_id,
    }
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=attached_id,
            result_id="phase10q-attached-sequence-select-passengers",
        )
        is None
    )
    disembark_action_request = _decision_request(
        handler.begin_phase(state=state, decisions=decisions)
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_action_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-attached-sequence-disembark-action",
        )
    )
    grouped_placement = RulesUnitPlacement(
        rules_unit_instance_id=attached_id,
        component_unit_placements=(
            _unit_placement_at(
                bodyguard,
                army_id="army-alpha",
                player_id="player-a",
                poses=(
                    Pose.at(8.6, 13.0),
                    Pose.at(10.0, 13.0),
                    Pose.at(11.4, 13.0),
                    Pose.at(9.3, 14.2),
                    Pose.at(10.7, 14.2),
                ),
            ),
            _unit_placement_at(
                leader,
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(12.6, 11.8),),
            ),
        ),
    )
    status = _submit_rules_unit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        placement=grouped_placement,
        transport=transport,
        result_id="phase10q-attached-sequence-disembark-placement",
    )

    assert status is None
    assert set(component_ids) <= _placed_unit_ids(state)
    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == ()
    disembarked = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=2,
        unit_instance_id=attached_id,
    )
    assert disembarked is not None
    assert disembarked.unit_instance_id == attached_id
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.active_selection is not None
    pending_setup_event_id = state.movement_phase_state.pending_setup_event_id
    assert pending_setup_event_id is not None
    disembark_event = next(
        event for event in decisions.event_log.records if event.event_id == pending_setup_event_id
    )
    assert disembark_event.event_type == "unit_disembarked"

    lifecycle_payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    restored = GameLifecycle.from_payload(lifecycle_payload)
    assert restored.state is not None
    follow_up = _decision_request(
        handler.begin_phase(
            state=restored.state,
            decisions=restored.decision_controller,
        )
    )
    assert follow_up.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert {option.option_id for option in follow_up.options} == {
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    }
    assert restored.state.movement_phase_state is not None
    assert restored.state.movement_phase_state.pending_setup_event_id is None


def test_attached_rules_unit_combat_disembark_is_atomic_and_group_hazardous() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-combat-disembark")
    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(
            bodyguard.unit_instance_id
        ).without_unit_placement(leader.unit_instance_id)
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=component_ids,
            started_unit_ids=component_ids,
            battle_round=1,
            max_model_count=6,
        )
    )
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-attached-combat-disembark-action",
        )
    )
    grouped_placement = RulesUnitPlacement(
        rules_unit_instance_id=attached_id,
        component_unit_placements=(
            _unit_placement_at(
                bodyguard,
                army_id="army-alpha",
                player_id="player-a",
                poses=(
                    Pose.at(11.6, 13.0),
                    Pose.at(13.0, 13.0),
                    Pose.at(14.4, 13.0),
                    Pose.at(12.3, 14.2),
                    Pose.at(13.7, 14.2),
                ),
            ),
            _unit_placement_at(
                leader,
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(15.6, 11.8),),
            ),
        ),
    )

    status = _submit_rules_unit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        placement=grouped_placement,
        transport=transport,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        result_id="phase10q-attached-combat-disembark-placement",
    )
    mortal_wound_request = _decision_request(status)
    for decision_index in range(128):
        mortal_wound_result = DecisionResult.for_request(
            result_id=f"phase10q-attached-combat-disembark-model-{decision_index}",
            request=mortal_wound_request,
            selected_option_id=mortal_wound_request.options[0].option_id,
        )
        decisions.submit_result(mortal_wound_result)
        next_request = apply_rules_unit_combat_disembark_feel_no_pain_decision(
            state=state,
            result=mortal_wound_result,
            decisions=decisions,
        )
        if next_request is None:
            break
        mortal_wound_request = next_request
    else:
        raise AssertionError("Combat disembark mortal wound model choices did not drain.")

    assert set(component_ids) <= _placed_unit_ids(state)
    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == ()
    disembarked = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=attached_id,
    )
    assert disembarked is not None
    assert disembarked.disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.moved_unit_ids == (attached_id,)
    hazard_event = _last_event_payload(
        decisions,
        TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    )
    combat_payload = cast(dict[str, object], hazard_event["disembark"])
    model_rolls = cast(list[dict[str, object]], combat_payload["model_rolls"])
    assert {str(roll["component_unit_instance_id"]) for roll in model_rolls} == set(component_ids)
    assert {
        str(cast(dict[str, object], roll["roll"])["model_instance_id"]) for roll in model_rolls
    } == {model.model_instance_id for unit in (bodyguard, leader) for model in unit.own_models}
    disembark_event = _last_event_payload(decisions, "unit_disembarked")
    tactical_violations = cast(
        list[dict[str, object]],
        disembark_event["tactical_fallback_violations"],
    )
    assert TransportOperationViolationCode.DISEMBARK_DISTANCE.value in {
        violation["violation_code"] for violation in tactical_violations
    }
    lifecycle_payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    restored = GameLifecycle.from_payload(lifecycle_payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_attached_combat_disembark_hazard_fnp_round_trips_and_resumes() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-combat-fnp")
    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    grouped_placement = RulesUnitPlacement(
        rules_unit_instance_id=attached_id,
        component_unit_placements=(
            _unit_placement_at(
                bodyguard,
                army_id="army-alpha",
                player_id="player-a",
                poses=(
                    Pose.at(11.6, 13.0),
                    Pose.at(13.0, 13.0),
                    Pose.at(14.4, 13.0),
                    Pose.at(12.3, 14.2),
                    Pose.at(13.7, 14.2),
                ),
            ),
            _unit_placement_at(
                leader,
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(15.6, 11.8),),
            ),
        ),
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(
            bodyguard.unit_instance_id
        ).without_unit_placement(leader.unit_instance_id)
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=component_ids,
            started_unit_ids=component_ids,
            battle_round=1,
            max_model_count=6,
        )
    )
    state.replace_movement_phase_state(
        MovementPhaseState(battle_round=1, active_player_id="player-a").with_unit_selection(
            MovementUnitSelection(
                player_id="player-a",
                battle_round=1,
                unit_instance_id=attached_id,
                request_id="phase10q-attached-combat-fnp-selection-request",
                result_id="phase10q-attached-combat-fnp-selection-result",
            )
        )
    )
    for unit in (bodyguard, leader):
        for model in unit.own_models:
            state.record_model_feel_no_pain_sources(
                model_instance_id=model.model_instance_id,
                sources=(
                    FeelNoPainSource(
                        source_id=f"phase10q-attached-combat-fnp:{model.model_instance_id}",
                        threshold=5,
                    ),
                ),
                decline_allowed=True,
            )
    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=attached_id,
    )
    injected_results = (
        *_combat_hazard_roll_results(
            grouped_placement.component_unit_placements[0],
            values=(1, 1, 6, 6, 6),
            roll_id_prefix="phase10q-attached-combat-fnp-bodyguard",
        ),
        *_combat_hazard_roll_results(
            grouped_placement.component_unit_placements[1],
            values=(6,),
            roll_id_prefix="phase10q-attached-combat-fnp-leader",
        ),
    )
    cargo_state = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo_state is not None
    combat_result = resolve_rules_unit_combat_disembark(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=RulesUnitDisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=attached_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=grouped_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        rules_unit=rules_unit,
        transport_placement=state.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase10q-attached-combat-fnp-rolls",
            injected_results=injected_results,
        ),
    )
    assert combat_result.is_valid
    assert combat_result.mortal_wounds == 2
    lifecycle = GameLifecycle(state=state)
    request = apply_rules_unit_combat_disembark_to_state(
        state=state,
        decisions=lifecycle.decision_controller,
        combat_disembark=combat_result,
        result=DecisionResult(
            result_id="phase10q-attached-combat-fnp-placement-result",
            request_id="phase10q-attached-combat-fnp-placement-request",
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id="player-a",
            selected_option_id="submit_parameterized_payload",
            payload={},
        ),
        dice_manager=DiceRollManager(
            "phase10q-attached-combat-fnp-route",
            event_log=lifecycle.decision_controller.event_log,
        ),
    )

    assert request is not None
    assert is_mortal_wound_model_request(request)
    source_context = mortal_wound_resolution_source_context(request)
    assert isinstance(source_context, dict)
    assert source_context["disembark_payload_kind"] == (RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND)
    assert source_context["unit_instance_id"] == attached_id
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    restored_request = restored.decision_controller.queue.peek_next()
    assert restored_request.to_payload() == request.to_payload()
    restored_state = restored.state
    assert restored_state is not None
    status = restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase10q-attached-combat-fnp-model",
            request=restored_request,
            selected_option_id=restored_request.options[0].option_id,
        )
    )
    fnp_request = _decision_request(status)
    assert is_mortal_wound_feel_no_pain_request(fnp_request)
    assert mortal_wound_feel_no_pain_source_context(fnp_request) == source_context
    before_wounds = sum(
        int(model.wounds_remaining)
        for army in restored_state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in component_ids
        for model in unit.own_models
    )

    status = restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase10q-attached-combat-fnp-decline",
            request=fnp_request,
            selected_option_id="decline",
        )
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    second_request = _decision_request(status)
    assert is_mortal_wound_feel_no_pain_request(second_request)
    second_result = DecisionResult.for_request(
        result_id="phase10q-attached-combat-fnp-second-decline",
        request=second_request,
        selected_option_id="decline",
    )
    restored.decision_controller.submit_result(second_result)
    assert (
        apply_rules_unit_combat_disembark_feel_no_pain_decision(
            state=restored_state,
            result=second_result,
            decisions=restored.decision_controller,
        )
        is None
    )
    after_wounds = sum(
        int(model.wounds_remaining)
        for army in restored_state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in component_ids
        for model in unit.own_models
    )
    assert after_wounds == before_wounds - 2
    hazard_event = _last_event_payload(
        restored.decision_controller,
        TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    )
    application = cast(dict[str, object], hazard_event["mortal_wound_application"])
    assert application["target_unit_instance_id"] == attached_id
    assert hazard_event["mortal_wounds"] == 2


def test_tactical_disembark_setup_destruction_prevents_stale_follow_up_move() -> None:
    state, handler, decisions, bodyguard, leader = _attached_tactical_disembark_setup_boundary()
    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    assert state.movement_phase_state is not None
    pending_setup_event_id = state.movement_phase_state.pending_setup_event_id
    assert pending_setup_event_id is not None
    trigger_event = next(
        event for event in decisions.event_log.records if event.event_id == pending_setup_event_id
    )
    destroyed_model_ids = tuple(
        model.model_instance_id for unit in (bodyguard, leader) for model in unit.own_models
    )
    alpha = state.army_definitions[0]
    destroyed_units = {
        unit.unit_instance_id: replace(
            unit,
            own_models=tuple(replace(model, wounds_remaining=0) for model in unit.own_models),
        )
        for unit in (bodyguard, leader)
    }
    state.replace_army_definitions(
        [
            replace(
                alpha,
                units=tuple(
                    destroyed_units.get(unit.unit_instance_id, unit) for unit in alpha.units
                ),
            ),
            state.army_definitions[1],
        ]
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    decisions.event_log.append(
        "unit_move_completed_mortal_wounds_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": "player-a",
            "trigger_event_id": trigger_event.event_id,
            "unit_instance_id": attached_id,
            "mortal_wounds": 99,
        },
    )

    status = handler.begin_phase(
        state=state,
        decisions=decisions,
    )

    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert attached_id not in {option.option_id for option in request.options}
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.active_selection is None
    assert state.movement_phase_state.pending_setup_event_id is None
    assert state.movement_phase_state.moved_unit_ids == (attached_id,)
    completion = _last_event_payload(decisions, "movement_activation_completed")
    assert completion["unit_instance_id"] == attached_id
    assert completion["movement_phase_action"] == MovementPhaseActionKind.DISEMBARK.value
    assert completion["setup_boundary_event_id"] == trigger_event.event_id


def test_lifecycle_attached_embark_capacity_drift_mutates_nothing() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-embark-capacity")
    state.record_transport_cargo_state(_cargo_state(transport=transport, max_model_count=6))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=bodyguard,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=0.5,
            result_id="phase10q-attached-capacity-normal-move",
        )
    )
    state.replace_transport_cargo_state(_cargo_state(transport=transport, max_model_count=5))
    before_state_payload = state.to_payload()

    status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-attached-capacity-invalid",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before_state_payload
    assert {bodyguard.unit_instance_id, leader.unit_instance_id} <= _placed_unit_ids(state)
    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == ()
    assert state.primary_battlefield_departure_states == []
    invalid_event = _last_event_payload(decisions, "embark_selection_invalid")
    violation_payloads = cast(list[dict[str, object]], invalid_event["violations"])
    assert TransportOperationViolationCode.CAPACITY_EXCEEDED.value in {
        row["violation_code"] for row in violation_payloads
    }


def test_lifecycle_attached_embark_honors_component_targeted_restriction() -> None:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-attached-embark-effect")
    state.record_transport_cargo_state(_cargo_state(transport=transport, max_model_count=6))
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase10q:leader-embark-forbidden",
            source_rule_id="phase10q:leader-embark-forbidden-source",
            owner_player_id="player-a",
            target_unit_instance_ids=(leader.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhase.MOVEMENT,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
            effect_payload={"embark_transport_forbidden": True},
        )
    )
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )

    status = _submit_action_and_movement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        unit=bodyguard,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        dx=0.5,
        result_id="phase10q-attached-effect-normal-move",
    )

    assert status is None
    assert {bodyguard.unit_instance_id, leader.unit_instance_id} <= _placed_unit_ids(state)
    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == ()
    assert state.primary_battlefield_departure_states == []
    assert not any(event.event_type == "unit_embarked" for event in decisions.event_log.records)


def test_lifecycle_advance_then_embark_replay_preserves_advanced_state() -> None:
    scenario, passenger, transport, _enemy, _catalog = _advance_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-advance-embark-newer-0002")
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )

    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.ADVANCE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            movement_mode=MovementMode.ADVANCE,
            dx=7.0,
            result_id="phase10q-advance",
        )
    )
    assert embark_request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE
    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-advance-embark",
    )

    assert result is None
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    assert (
        state.advanced_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
        )
        is not None
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_lifecycle_fall_back_then_embark_replay_preserves_fell_back_state() -> None:
    scenario, passenger, transport, _enemy, _catalog = _fall_back_embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    fall_back_option_id = (
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
    )
    assert fall_back_option_id in {option.option_id for option in action_request.options}

    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=fall_back_option_id,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.FALL_BACK,
            movement_mode=MovementMode.FALL_BACK,
            fall_back_mode=FallBackModeKind.ORDERED_RETREAT,
            dy=6.0,
            result_id="phase10q-fall-back",
        )
    )
    assert embark_request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE
    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-fall-back-embark",
    )

    assert result is None
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
        )
        is not None
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_lifecycle_embark_decline_leaves_unit_placed_and_completes_activation() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase10q-normal-move",
        )
    )

    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=DECLINE_EMBARK_OPTION_ID,
        result_id="phase10q-decline-embark",
    )

    assert result is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.active_selection is None
    assert state.movement_phase_state.moved_unit_ids == (passenger.unit_instance_id,)


def test_invalid_lifecycle_embark_returns_invalid_without_embark_mutation() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase10q-normal-move",
        )
    )
    state.replace_transport_cargo_state(
        replace(
            _cargo_state(transport=transport, battle_round=1),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=1,
                allowed_keywords=("INFANTRY",),
            ),
        )
    )
    before_battlefield = state.battlefield_state
    before_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)

    status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-invalid-embark",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    assert state.transport_cargo_state_for_transport(transport.unit_instance_id) == before_cargo
    assert passenger.unit_instance_id in _placed_unit_ids(state)


def test_started_embarked_unit_disembarks_through_movement_decision_lifecycle() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()

    unit_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert unit_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    passenger_payload = cast(
        dict[str, object],
        unit_request.option_by_id(passenger.unit_instance_id).payload,
    )
    assert passenger_payload == {
        "unit_instance_id": passenger.unit_instance_id,
        "component_unit_instance_ids": [passenger.unit_instance_id],
        "model_instance_ids": [model.model_instance_id for model in passenger.own_models],
        "unit_location": "embarked",
        "transport_unit_instance_id": transport.unit_instance_id,
    }
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=unit_request,
            option_id=passenger.unit_instance_id,
            result_id="phase09a-select-embarked-unit",
        )
        is None
    )
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.DISEMBARK.value,
    }
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-select-disembark-move",
        )
    )
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        result_id="phase10q-place-disembark",
    )

    assert status is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    assert stored_cargo.disembarked_this_phase_unit_instance_ids == (passenger.unit_instance_id,)
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
    )
    assert disembarked_state is not None
    assert disembarked_state.disembark_mode is DisembarkModeKind.TACTICAL_DISEMBARK

    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert MovementPhaseActionKind.REMAIN_STATIONARY.value not in {
        option.option_id for option in action_request.options
    }
    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    }

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_movement_phase_combat_disembark_requires_tactical_impossible_evidence() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario, game_id="phase14h-movement-combat-disembark")
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()

    handler, decisions, disembark_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    disembark_option = disembark_request.option_by_id(MovementPhaseActionKind.DISEMBARK.value)
    disembark_option_payload = cast(dict[str, JsonValue], disembark_option.payload)
    assert disembark_option_payload["disembark_mode"] == (
        DisembarkModeKind.TACTICAL_DISEMBARK.value
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase14h-select-combat-disembark-fallback",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)
    assert proposal.context is not None
    assert proposal.context["allowed_disembark_modes"] == [
        DisembarkModeKind.TACTICAL_DISEMBARK.value,
        DisembarkModeKind.COMBAT_DISEMBARK.value,
    ]

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        poses=tuple(Pose.at(pose.position.x + 3.0, pose.position.y) for pose in _disembark_poses()),
        result_id="phase14h-place-combat-disembark-fallback",
    )
    mortal_wound_request = _decision_request(status)
    for decision_index in range(128):
        mortal_wound_result = DecisionResult.for_request(
            result_id=f"phase14h-combat-disembark-model-{decision_index}",
            request=mortal_wound_request,
            selected_option_id=mortal_wound_request.options[0].option_id,
        )
        decisions.submit_result(mortal_wound_result)
        next_request = apply_rules_unit_combat_disembark_feel_no_pain_decision(
            state=state,
            result=mortal_wound_result,
            decisions=decisions,
        )
        if next_request is None:
            status = None
            break
        mortal_wound_request = next_request
    else:
        raise AssertionError("Combat disembark mortal wound model choices did not drain.")

    assert status is None
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
    )
    assert disembarked_state is not None
    assert disembarked_state.disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK
    assert disembarked_state.battle_shocked_until == "end_of_turn"
    assert disembarked_state.can_declare_charge is False
    assert state.movement_phase_state is not None
    assert passenger.unit_instance_id in state.movement_phase_state.selected_unit_ids
    assert passenger.unit_instance_id in state.movement_phase_state.moved_unit_ids
    disembark_event = _last_event_payload(decisions, "unit_disembarked")
    tactical_violations = cast(
        list[dict[str, object]],
        disembark_event["tactical_fallback_violations"],
    )
    assert {violation["violation_code"] for violation in tactical_violations} == {
        TransportOperationViolationCode.DISEMBARK_DISTANCE.value
    }
    hazard_event = _last_event_payload(decisions, TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE)
    assert hazard_event["source_kind"] == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND
    assert hazard_event["disembark_mode"] == DisembarkModeKind.COMBAT_DISEMBARK.value


def test_movement_phase_combat_disembark_rejects_when_tactical_placement_is_legal() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario, game_id="phase14h-combat-disembark-tactical-available")
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler, decisions, disembark_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase14h-select-combat-disembark-reject",
        )
    )
    before_battlefield = state.battlefield_state
    before_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        result_id="phase14h-place-combat-disembark-reject",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    assert state.transport_cargo_state_for_transport(transport.unit_instance_id) == before_cargo
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    invalid_event = _last_event_payload(decisions, "combat_disembark_tactical_available")
    violations = cast(list[dict[str, object]], invalid_event["violations"])
    assert violations[0]["violation_code"] == (
        TransportOperationViolationCode.COMBAT_DISEMBARK_TACTICAL_AVAILABLE.value
    )


def test_movement_phase_combat_disembark_rejects_invalid_combat_placement() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario, game_id="phase14h-combat-disembark-invalid-placement")
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler, decisions, disembark_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase14h-select-combat-disembark-invalid-placement",
        )
    )
    before_battlefield = state.battlefield_state
    before_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        poses=tuple(Pose.at(pose.position.x + 8.0, pose.position.y) for pose in _disembark_poses()),
        result_id="phase14h-place-combat-disembark-invalid-placement",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    assert state.transport_cargo_state_for_transport(transport.unit_instance_id) == before_cargo
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    invalid_event = _last_event_payload(decisions, "combat_disembark_placement_invalid")
    violations = cast(list[dict[str, object]], invalid_event["violations"])
    assert TransportOperationViolationCode.DISEMBARK_DISTANCE.value in {
        violation["violation_code"] for violation in violations
    }


def test_disembark_selection_does_not_depend_on_engine_built_placement() -> None:
    scenario, passenger, transport, enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id="army-beta",
            player_id="player-b",
            poses=_disembark_poses()[: len(enemy.own_models)],
        )
    )
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    state.record_transport_cargo_state(cargo_state)
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler, decisions, disembark_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )

    blocked_scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    transport_placement = blocked_scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    blocked_right_side_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses()[: len(passenger.own_models)],
    )
    blocked_resolution = resolve_disembark(
        scenario=blocked_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state.for_movement_phase(battle_round=1),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=blocked_right_side_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=transport_placement,
    )
    assert not blocked_resolution.is_valid

    assert disembark_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert MovementPhaseActionKind.DISEMBARK.value in {
        option.option_id for option in disembark_request.options
    }

    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-select-placement-agnostic-disembark",
        )
    )
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        poses=_left_side_disembark_poses()[: len(passenger.own_models)],
        result_id="phase10q-place-placement-agnostic-disembark",
    )

    assert status is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    assert _last_event_payload(decisions, "unit_disembarked")["phase_body_status"] == (
        "unit_disembarked"
    )


def test_transport_normal_move_emits_post_move_disembark_decision_after_pre_move_decline() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )

    handler, decisions, post_move_disembark_request = (
        _rapid_disembark_request_after_transport_normal_move(
            state=state,
            passenger=passenger,
            transport=transport,
        )
    )

    assert handler is not None
    assert decisions is not None
    assert post_move_disembark_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    post_move_option = post_move_disembark_request.option_by_id(
        MovementPhaseActionKind.DISEMBARK.value
    )
    post_move_option_payload = cast(dict[str, JsonValue], post_move_option.payload)
    assert post_move_option_payload["transport_movement_status"] == (
        TransportMovementStatus.NORMAL_MOVE.value
    )
    assert post_move_option_payload["disembark_mode"] == (DisembarkModeKind.RAPID_DISEMBARK.value)
    assert post_move_option_payload["transport_unit_instance_id"] == transport.unit_instance_id
    assert {option.option_id for option in post_move_disembark_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.DISEMBARK.value,
    }
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.moved_unit_ids == (transport.unit_instance_id,)


def test_post_transport_normal_move_disembark_lifecycle_records_restrictions_and_replay() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    handler, decisions, post_move_disembark_request = (
        _rapid_disembark_request_after_transport_normal_move(
            state=state,
            passenger=passenger,
            transport=transport,
        )
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=post_move_disembark_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-select-post-normal-disembark",
        )
    )
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        result_id="phase10q-place-post-normal-disembark",
    )

    assert status is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    assert stored_cargo.disembarked_this_phase_unit_instance_ids == (passenger.unit_instance_id,)
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
    )
    assert disembarked_state is not None
    assert disembarked_state.disembark_mode is DisembarkModeKind.RAPID_DISEMBARK
    assert not disembarked_state.can_move_further
    assert not disembarked_state.can_declare_charge
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.selected_unit_ids == (
        transport.unit_instance_id,
        passenger.unit_instance_id,
    )
    assert state.movement_phase_state.moved_unit_ids == (
        transport.unit_instance_id,
        passenger.unit_instance_id,
    )
    assert passenger.unit_instance_id not in state.movement_phase_state.legal_unit_ids(state)

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_replay_rejects_transport_cargo_when_transport_is_not_placed() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    ).without_unit_placement(transport.unit_instance_id)
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="transport unit must be placed"):
        GameLifecycle.from_payload(payload)


def test_replay_rejects_transport_cargo_when_transport_model_is_removed() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    transport_model_id = transport.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    ).with_removed_models((transport_model_id,))
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="transport unit must be placed"):
        GameLifecycle.from_payload(payload)


def test_replay_rejects_advanced_state_for_unplaced_unremoved_unembarked_unit() -> None:
    scenario, passenger, _transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    decisions = _record_declared_reserve_for_replay_fixture(
        state=state,
        player_id="player-a",
        unit_instance_id=passenger.unit_instance_id,
    )
    state.record_advanced_unit_state(_advanced_unit_state(passenger.unit_instance_id))
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="advanced_unit_states unit"):
        GameLifecycle.from_payload(payload)


def test_replay_rejects_fell_back_state_for_unplaced_unremoved_unembarked_unit() -> None:
    scenario, passenger, _transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    decisions = _record_declared_reserve_for_replay_fixture(
        state=state,
        player_id="player-a",
        unit_instance_id=passenger.unit_instance_id,
    )
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="fell_back_unit_states unit"):
        GameLifecycle.from_payload(payload)


def test_disembark_places_unit_and_applies_after_normal_move_restrictions() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(),
    )

    resolution = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )

    assert resolution.is_valid
    assert resolution.disembarked_unit_state is not None
    assert resolution.disembarked_unit_state.disembark_mode is (DisembarkModeKind.RAPID_DISEMBARK)
    assert not resolution.disembarked_unit_state.can_move_further
    assert not resolution.disembarked_unit_state.can_declare_charge
    assert resolution.transition_batch is not None
    assert {record.placement_kind for record in resolution.transition_batch.placements} == {
        BattlefieldPlacementKind.DISEMBARK
    }

    updated_battlefield = apply_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=resolution,
    )
    assert updated_battlefield.unit_placement_by_id(passenger.unit_instance_id)


def test_disembark_endpoint_honors_terrain_top_restrictions() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(z_inches=1.0),
    )

    result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        terrain_features=(
            _support_feature(
                feature_id="phase10q-barricade",
                feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
                center_x_inches=13.5,
                center_y_inches=10.5,
                z_inches=1.0,
                width_inches=6.0,
                depth_inches=5.0,
            ),
        ),
    )

    assert not result.is_valid
    assert TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL in {
        violation.violation_code for violation in result.violations
    }
    with pytest.raises(GameLifecycleError, match="Invalid DisembarkResolution"):
        apply_disembark_to_battlefield(
            battlefield_state=disembark_scenario.battlefield_state,
            disembark=result,
        )


def test_disembark_ruins_upper_floor_requires_full_base_support() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario(
        passenger_datasheet_id="core-character-leader",
        passenger_model_profile_id="core-character-leader",
        passenger_model_count=1,
        passenger_unit_selection_id="character-passenger",
    )
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(13.5, 10.0, 3.0),),
    )

    result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        terrain_features=(
            _ruins_floor_feature(
                feature_id="phase10q-ruins",
                center_x_inches=13.5,
                center_y_inches=10.0,
                upper_width_inches=0.75,
                upper_depth_inches=0.75,
            ),
        ),
    )

    assert not result.is_valid
    assert TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL in {
        violation.violation_code for violation in result.violations
    }


def test_disembark_mode_status_pairs_are_fail_fast_and_round_trip() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(),
    )

    tactical_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    rapid_normal_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
    )
    rapid_ingress_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.INGRESS_MOVE,
    )
    combat_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=_unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=tuple(
                Pose.at(pose.position.x + 3.0, pose.position.y) for pose in _disembark_poses()
            ),
        ),
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    tactical_stationary_selection = replace(
        tactical_selection,
        transport_movement_status=TransportMovementStatus.REMAIN_STATIONARY,
    )

    assert DisembarkSelection.from_payload(tactical_selection.to_payload()) == tactical_selection
    assert (
        DisembarkSelection.from_payload(tactical_stationary_selection.to_payload())
        == tactical_stationary_selection
    )
    assert (
        DisembarkSelection.from_payload(rapid_normal_selection.to_payload())
        == rapid_normal_selection
    )
    assert (
        DisembarkSelection.from_payload(rapid_ingress_selection.to_payload())
        == rapid_ingress_selection
    )
    assert DisembarkSelection.from_payload(combat_selection.to_payload()) == combat_selection
    with pytest.raises(GameLifecycleError, match="requires resolve_combat_disembark"):
        resolve_disembark(
            scenario=disembark_scenario,
            ruleset_descriptor=_ruleset(),
            cargo_state=cargo_state,
            selection=combat_selection,
            unit=passenger,
            transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
                transport.unit_instance_id
            ),
        )
    combat_state = DisembarkedUnitState.for_mode(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )

    assert combat_state.battle_shocked_until == "end_of_turn"
    assert combat_state.can_declare_charge is False

    with pytest.raises(GameLifecycleError, match="Tactical Disembark requires an unmoved"):
        resolve_disembark(
            scenario=disembark_scenario,
            ruleset_descriptor=_ruleset(),
            cargo_state=cargo_state,
            selection=DisembarkSelection(
                player_id="player-a",
                battle_round=1,
                unit_instance_id=passenger.unit_instance_id,
                transport_unit_instance_id=transport.unit_instance_id,
                attempted_placement=attempted_placement,
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
            ),
            unit=passenger,
            transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
                transport.unit_instance_id
            ),
        )
    with pytest.raises(GameLifecycleError, match="Rapid Disembark requires Normal or Ingress"):
        DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        )
    with pytest.raises(GameLifecycleError, match="Combat Disembark requires an unmoved"):
        DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        )


def test_embark_after_disembark_needs_explicit_override() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembarked_cargo = _cargo_state(
        transport=transport,
        embarked_unit_ids=(),
        started_unit_ids=(),
        disembarked_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    blocked_embark = resolve_embark(
        scenario=scenario,
        cargo_state=disembarked_cargo,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )
    allowed_embark = resolve_embark(
        scenario=scenario,
        cargo_state=disembarked_cargo,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
            restriction_overrides=(
                TransportRestrictionOverride(
                    override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                    source_rule_id="phase10q_override",
                ),
            ),
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )

    assert TransportOperationViolationCode.EMBARK_AFTER_DISEMBARK_FORBIDDEN in {
        violation.violation_code for violation in blocked_embark.violations
    }
    assert allowed_embark.is_valid


def test_embark_reports_all_local_validation_failures_without_mutation_records() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(
            Pose.at(35.0 + index * 2.0, 10.0) for index in range(len(passenger.own_models))
        ),
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    result = resolve_embark(
        scenario=scenario,
        cargo_state=TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=4,
                allowed_keywords=("MONSTER",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        ),
        selection=EmbarkSelection(
            player_id="player-b",
            battle_round=1,
            unit_instance_id="army-alpha:wrong-passenger",
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )

    assert not result.is_valid
    assert result.updated_cargo_state is None
    assert result.transition_batch is None
    assert {
        TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
        TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
        TransportOperationViolationCode.UNIT_ALREADY_EMBARKED,
        TransportOperationViolationCode.CAPACITY_EXCEEDED,
        TransportOperationViolationCode.EMBARK_DISTANCE,
    } <= {violation.violation_code for violation in result.violations}
    with pytest.raises(GameLifecycleError, match="Invalid EmbarkResolution"):
        apply_embark_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            embark=result,
        )


def test_disembark_reports_enemy_range_edge_overlap_and_membership_failures() -> None:
    scenario, passenger, transport, enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    enemy_placement = _unit_placement_at(
        enemy,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(Pose.at(1.0 + index * 1.0, 1.0) for index in range(len(enemy.own_models))),
    )
    disembark_scenario = BattlefieldScenario(
        armies=disembark_scenario.armies,
        battlefield_state=disembark_scenario.battlefield_state.with_unit_placement(enemy_placement),
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(0.25, 1.0), Pose.at(0.25, 1.0)),
    )

    result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(transport=transport),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=enemy,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )

    assert not result.is_valid
    assert {
        TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
        TransportOperationViolationCode.UNIT_NOT_EMBARKED,
        TransportOperationViolationCode.UNIT_DID_NOT_START_PHASE_EMBARKED,
        TransportOperationViolationCode.DISEMBARK_DISTANCE,
        TransportOperationViolationCode.BATTLEFIELD_EDGE_CROSSED,
        TransportOperationViolationCode.MODEL_OVERLAP,
        TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
    } <= {violation.violation_code for violation in result.violations}


def test_combat_disembark_rolls_hazard_for_each_model_and_round_trips() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(pose.position.x + 3.0, pose.position.y) for pose in _disembark_poses()),
    )
    selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    injected_results = tuple(
        DiceRollResult.from_values(
            roll_id=f"phase10q-combat-hazard-{index:03d}",
            spec=hazard_roll_spec(
                reason=f"Combat Disembark hazard roll for {model_placement.model_instance_id}",
                roll_type="combat_disembark.hazard_roll",
                actor_id=model_placement.model_instance_id,
            ),
            values=(roll_value,),
            source="injected",
        )
        for index, (model_placement, roll_value) in enumerate(
            zip(attempted_placement.model_placements, (1, 2, 3, 6, 6), strict=True),
            start=1,
        )
    )

    result = resolve_combat_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=selection,
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase10q-combat-disembark",
            injected_results=injected_results,
        ),
    )

    assert result.placement.is_valid
    assert result.roll_threshold == HAZARD_ROLL_FAILURE_THRESHOLD
    assert result.mortal_wounds_per_failed_roll == 1
    assert len(result.model_rolls) == len(passenger.own_models)
    assert result.mortal_wound_count == 2
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.battle_shocked_until == "end_of_turn"
    assert result.disembarked_unit_state.can_declare_charge is False
    assert result.disembarked_unit_state.disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK
    assert CombatDisembark.from_payload(result.to_payload()) == result

    updated_battlefield = apply_combat_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=result,
    )
    assert (
        updated_battlefield.unit_placement_by_id(passenger.unit_instance_id) == attempted_placement
    )


def test_combat_disembark_hazard_mortal_wounds_use_shared_damage_service() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(pose.position.x + 3.0, pose.position.y) for pose in _disembark_poses()),
    )
    combat_result = resolve_combat_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase14h-transport-hazard-combat",
            injected_results=_combat_hazard_roll_results(
                attempted_placement,
                values=(1, 6, 6, 6, 6),
                roll_id_prefix="phase14h-transport-hazard-combat",
            ),
        ),
    )
    updated_battlefield = apply_combat_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=combat_result,
    )
    state = _battle_state(disembark_scenario, game_id="phase14h-transport-hazard")
    state.battlefield_state = updated_battlefield
    decisions = DecisionController()
    target_model = passenger.own_models[0]

    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=decisions,
        disembark=combat_result,
        dice_manager=DiceRollManager("phase14h-transport-hazard", event_log=decisions.event_log),
    )

    assert routed.mortal_wounds == 1
    request = routed.pending_mortal_wound_request
    assert request is not None
    assert is_mortal_wound_model_request(request)
    model_result = DecisionResult.for_request(
        result_id="phase14h-transport-hazard-model",
        request=request,
        selected_option_id=target_model.model_instance_id,
    )
    decisions.submit_result(model_result)
    assert (
        apply_transport_hazard_mortal_wound_feel_no_pain_decision(
            state=state,
            result=model_result,
            decisions=decisions,
        )
        is None
    )
    assert (
        model_by_id(state=state, model_instance_id=target_model.model_instance_id).wounds_remaining
        == target_model.wounds_remaining - 1
    )
    event_payloads = [
        record.payload
        for record in decisions.event_log.records
        if record.event_type == TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE
    ]
    assert len(event_payloads) == 1
    resolved = TransportHazardMortalWounds.from_payload(
        cast(TransportHazardMortalWoundsPayload, event_payloads[0])
    )
    assert resolved.mortal_wound_application is not None
    assert resolved.mortal_wound_application.target_unit_instance_id == (passenger.unit_instance_id)
    assert TransportHazardMortalWounds.from_payload(resolved.to_payload()) == resolved


def test_transport_hazard_mortal_wounds_resume_decline_allowed_feel_no_pain() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(pose.position.x + 3.0, pose.position.y) for pose in _disembark_poses()),
    )
    combat_result = resolve_combat_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase14h-transport-hazard-fnp",
            injected_results=_combat_hazard_roll_results(
                attempted_placement,
                values=(1, 6, 6, 6, 6),
                roll_id_prefix="phase14h-transport-hazard-fnp",
            ),
        ),
    )
    updated_battlefield = apply_combat_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=combat_result,
    )
    state = _battle_state(disembark_scenario, game_id="phase14h-transport-hazard-fnp")
    state.battlefield_state = updated_battlefield
    target_model = passenger.own_models[0]
    state.record_model_feel_no_pain_sources(
        model_instance_id=target_model.model_instance_id,
        sources=(FeelNoPainSource(source_id="phase14h-transport-fnp", threshold=5),),
        decline_allowed=True,
    )
    decisions = DecisionController()

    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=decisions,
        disembark=combat_result,
        dice_manager=DiceRollManager(
            "phase14h-transport-hazard-fnp-route",
            event_log=decisions.event_log,
        ),
    )
    request = routed.pending_mortal_wound_request

    assert request is not None
    assert routed.mortal_wound_application is None
    assert is_mortal_wound_model_request(request)
    model_result = DecisionResult.for_request(
        result_id="phase14h-transport-fnp-model",
        request=request,
        selected_option_id=target_model.model_instance_id,
    )
    decisions.submit_result(model_result)
    model_status = apply_transport_hazard_mortal_wound_feel_no_pain_decision(
        state=state,
        result=model_result,
        decisions=decisions,
    )
    request = _decision_request(model_status)
    assert is_mortal_wound_feel_no_pain_request(request)
    assert {option.option_id for option in request.options} == {
        "decline",
        "phase14h-transport-fnp",
    }
    assert (
        model_by_id(state=state, model_instance_id=target_model.model_instance_id).wounds_remaining
        == target_model.wounds_remaining
    )
    assert TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE not in {
        record.event_type for record in decisions.event_log.records
    }

    decline_result = DecisionResult.for_request(
        result_id="phase14h-transport-fnp-decline",
        request=request,
        selected_option_id="decline",
    )
    decisions.submit_result(decline_result)
    resume_status = apply_transport_hazard_mortal_wound_feel_no_pain_decision(
        state=state,
        result=decline_result,
        decisions=decisions,
    )
    event_payloads = [
        record.payload
        for record in decisions.event_log.records
        if record.event_type == TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE
    ]

    assert resume_status is None
    assert (
        model_by_id(state=state, model_instance_id=target_model.model_instance_id).wounds_remaining
        == target_model.wounds_remaining - 1
    )
    assert len(event_payloads) == 1
    final_payload = cast(TransportHazardMortalWoundsPayload, event_payloads[0])
    assert final_payload["source_kind"] == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND
    assert final_payload["pending_mortal_wound_request_id"] is None
    assert final_payload["mortal_wounds"] == 1
    assert final_payload["mortal_wound_application"] is not None


def test_lifecycle_transport_hazard_fnp_continues_reaction_frame() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(pose.position.x + 3.0, pose.position.y) for pose in _disembark_poses()),
    )
    combat_result = resolve_combat_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase14h-transport-hazard-reaction-fnp",
            injected_results=_combat_hazard_roll_results(
                attempted_placement,
                values=(1, 1, 6, 6, 6),
                roll_id_prefix="phase14h-transport-hazard-reaction-fnp",
            ),
        ),
    )
    updated_battlefield = apply_combat_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=combat_result,
    )
    state = _battle_state(disembark_scenario, game_id="phase14h-transport-hazard-reaction-fnp")
    state.battlefield_state = updated_battlefield
    target_model = passenger.own_models[0]
    state.record_model_feel_no_pain_sources(
        model_instance_id=target_model.model_instance_id,
        sources=(FeelNoPainSource(source_id="phase14h-transport-reaction-fnp", threshold=5),),
        decline_allowed=True,
    )
    lifecycle = GameLifecycle(state=state)
    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=lifecycle.decision_controller,
        disembark=combat_result,
        dice_manager=DiceRollManager(
            "phase14h-transport-hazard-reaction-route",
            event_log=lifecycle.decision_controller.event_log,
        ),
    )
    seed_request = routed.pending_mortal_wound_request
    assert seed_request is not None
    lifecycle.decision_controller.queue.remove_by_id(seed_request.request_id)
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_transport_reaction_window(state=state, eligible_player_id="player-a"),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="phase14h_transport_hazard_reaction",
        resume_token="phase14h_transport_hazard_reaction_resume",
        actor_id="player-a",
        decision_type=seed_request.decision_type,
        options=seed_request.options,
        payload=seed_request.payload,
    )
    reaction_request = lifecycle.decision_controller.queue.peek_next()
    assert is_mortal_wound_model_request(reaction_request)

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14h-transport-hazard-reaction-model",
            request=reaction_request,
            selected_option_id=target_model.model_instance_id,
        )
    )
    follow_up_request = lifecycle.decision_controller.queue.peek_next()
    continued_event = cast(
        dict[str, object],
        [
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "reaction_window_continued"
        ][-1],
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request == follow_up_request
    assert follow_up_request.decision_type == "select_feel_no_pain"
    assert lifecycle.reaction_queue.frames[-1].request_id == follow_up_request.request_id
    assert continued_event["next_request_id"] == follow_up_request.request_id
    assert not any(
        record.event_type == "reaction_parent_resumed"
        for record in lifecycle.decision_controller.event_log.records
    )


def test_emergency_disembark_hazard_mortal_wounds_use_shared_damage_service() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(),
    )
    emergency_result = resolve_destroyed_transport_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase14h-transport-hazard-emergency",
            injected_results=_destroyed_transport_hazard_roll_results(
                attempted_placement,
                values=(1, 6, 6, 6, 6),
                roll_id_prefix="phase14h-transport-hazard-emergency",
            ),
        ),
    )
    updated_battlefield = apply_destroyed_transport_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=emergency_result,
    )
    state = _battle_state(disembark_scenario, game_id="phase14h-emergency-hazard")
    state.battlefield_state = updated_battlefield
    decisions = DecisionController()
    target_model = passenger.own_models[0]

    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=decisions,
        disembark=emergency_result,
        dice_manager=DiceRollManager("phase14h-emergency-hazard", event_log=decisions.event_log),
    )
    assert emergency_result.disembark_mode is DisembarkModeKind.EMERGENCY_DISEMBARK
    assert emergency_result.roll_threshold == HAZARD_ROLL_FAILURE_THRESHOLD
    assert emergency_result.mortal_wound_count == 1
    assert routed.mortal_wounds == 1
    request = routed.pending_mortal_wound_request
    assert request is not None
    assert is_mortal_wound_model_request(request)
    model_result = DecisionResult.for_request(
        result_id="phase14h-emergency-hazard-model",
        request=request,
        selected_option_id=target_model.model_instance_id,
    )
    decisions.submit_result(model_result)
    assert (
        apply_transport_hazard_mortal_wound_feel_no_pain_decision(
            state=state,
            result=model_result,
            decisions=decisions,
        )
        is None
    )
    assert (
        model_by_id(state=state, model_instance_id=target_model.model_instance_id).wounds_remaining
        == target_model.wounds_remaining - 1
    )
    event_payloads = [
        record.payload
        for record in decisions.event_log.records
        if record.event_type == TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE
    ]
    assert len(event_payloads) == 1
    final_payload = cast(TransportHazardMortalWoundsPayload, event_payloads[0])
    resolved = TransportHazardMortalWounds.from_payload(final_payload)
    assert resolved.mortal_wound_application is not None
    assert resolved.mortal_wound_application.target_unit_instance_id == (passenger.unit_instance_id)
    assert TransportHazardMortalWounds.from_payload(resolved.to_payload()) == resolved
    assert final_payload["source_kind"] == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND
    assert final_payload["disembark_mode"] == DisembarkModeKind.EMERGENCY_DISEMBARK.value
    assert final_payload == resolved.to_payload()


def test_combat_disembark_can_only_set_up_engaged_with_transport_engagement() -> None:
    scenario, passenger, transport, enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    enemy_placement = _unit_placement_at(
        enemy,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(13.2, 10.0),
            *tuple(Pose.at(35.0 + index * 2.0, 35.0) for index in range(4)),
        ),
    )
    disembark_scenario = BattlefieldScenario(
        armies=disembark_scenario.armies,
        battlefield_state=disembark_scenario.battlefield_state.with_unit_placement(enemy_placement),
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(
            Pose.at(14.85, 10.0),
            Pose.at(16.2, 10.0),
            Pose.at(16.2, 11.3),
            Pose.at(14.85, 11.35),
            Pose.at(14.85, 8.65),
        ),
    )
    tactical_result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )
    combat_result = resolve_combat_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(
            "phase10q-combat-engaged",
            injected_results=tuple(
                DiceRollResult.from_values(
                    roll_id=f"phase10q-combat-engaged-{index:03d}",
                    spec=hazard_roll_spec(
                        reason=(
                            f"Combat Disembark hazard roll for {model_placement.model_instance_id}"
                        ),
                        roll_type="combat_disembark.hazard_roll",
                        actor_id=model_placement.model_instance_id,
                    ),
                    values=(6,),
                    source="injected",
                )
                for index, model_placement in enumerate(
                    attempted_placement.model_placements,
                    start=1,
                )
            ),
        ),
    )

    assert TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE in {
        violation.violation_code for violation in tactical_result.violations
    }
    assert combat_result.placement.is_valid

    blocked_enemy_placement = _unit_placement_at(
        enemy,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(16.4, 10.0),
            *tuple(Pose.at(35.0 + index * 2.0, 35.0) for index in range(4)),
        ),
    )
    blocked_scenario = BattlefieldScenario(
        armies=disembark_scenario.armies,
        battlefield_state=disembark_scenario.battlefield_state.with_unit_placement(
            blocked_enemy_placement
        ),
    )
    blocked_attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(
            Pose.at(14.85, 10.0),
            Pose.at(13.5, 10.0),
            Pose.at(13.5, 11.3),
            Pose.at(14.85, 11.35),
            Pose.at(14.85, 8.65),
        ),
    )
    blocked_result = resolve_combat_disembark(
        scenario=blocked_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=blocked_attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=blocked_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager("phase10q-combat-non-transport-engagement"),
    )

    assert not blocked_result.placement.is_valid
    assert TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE in {
        violation.violation_code for violation in blocked_result.placement.violations
    }


def test_combat_disembark_uses_retained_attached_engagement_as_canonical_permission() -> None:
    scenario, passenger, transport, bodyguard, _catalog = _transport_scenario(enemy_attached=True)
    leader = scenario.armies[1].unit_by_id("army-beta:enemy-leader")
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    bodyguard_placement = _unit_placement_at(
        bodyguard,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(16.4, 10.0),
            *tuple(Pose.at(35.0 + index * 2.0, 35.0) for index in range(4)),
        ),
    )
    leader_placement = _unit_placement_at(
        leader,
        army_id="army-beta",
        player_id="player-b",
        poses=(Pose.at(10.0, 13.2),),
    )
    disembark_scenario = BattlefieldScenario(
        armies=disembark_scenario.armies,
        battlefield_state=(
            disembark_scenario.battlefield_state.with_unit_placement(
                bodyguard_placement
            ).with_unit_placement(leader_placement)
        ),
    )
    state = _battle_state(
        disembark_scenario,
        game_id="phase10q-combat-disembark-retained-attached",
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    leader_model = leader.own_models[0]
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=leader.unit_instance_id,
        model_instance_id=leader_model.model_instance_id,
        damage=leader_model.wounds_remaining,
        damage_kind=DamageKind.NORMAL,
    )
    assert damage.destroyed
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=leader_placement.model_placements[0],
        effect_id="phase10q-combat-disembark-retained-attached-leader",
        source_rule_id="phase10q-test-fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )
    retained_scenario = battlefield_scenario_for_state(state=state)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(
            Pose.at(14.85, 10.0),
            Pose.at(13.5, 10.0),
            Pose.at(13.5, 11.3),
            Pose.at(14.85, 11.35),
            Pose.at(14.85, 8.65),
        ),
    )
    selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )

    result = resolve_combat_disembark(
        scenario=retained_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=selection,
        unit=passenger,
        transport_placement=retained_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager("phase10q-combat-disembark-retained-attached"),
    )
    without_retained_presence = BattlefieldScenario(
        armies=retained_scenario.armies,
        battlefield_state=retained_scenario.battlefield_state,
    )
    without_retained_result = resolve_combat_disembark(
        scenario=without_retained_presence,
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=selection,
        unit=passenger,
        transport_placement=without_retained_presence.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager("phase10q-combat-disembark-no-retained-authority"),
    )

    assert retained_scenario.present_destroyed_model_ids == (leader_model.model_instance_id,)
    assert result.placement.is_valid
    assert not without_retained_result.placement.is_valid
    assert TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE in {
        violation.violation_code for violation in without_retained_result.placement.violations
    }


def test_destroyed_transport_emergency_destroys_unplaceable_models_and_battleshocks_unit() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    partial_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses()[:-1],
    )

    result = resolve_destroyed_transport_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=partial_placement,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(10),
    )

    assert result.placement.is_valid
    assert result.roll_threshold == HAZARD_ROLL_FAILURE_THRESHOLD
    assert result.mortal_wounds_per_failed_roll == 1
    assert len(result.model_rolls) == len(passenger.own_models)
    assert result.destroyed_model_instance_ids == (passenger.own_models[-1].model_instance_id,)
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.battle_shocked_until == "end_of_turn"
    assert result.disembarked_unit_state.disembark_mode is (DisembarkModeKind.EMERGENCY_DISEMBARK)
    updated_battlefield = apply_destroyed_transport_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=result,
    )
    assert passenger.own_models[-1].model_instance_id in updated_battlefield.removed_model_ids


def test_firing_deck_selects_ranged_non_one_shot_weapons_and_marks_units_ineligible() -> None:
    _scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    profile = _first_weapon_profile(catalog, passenger)
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    selection = FiringDeckSelection(
        player_id="player-a",
        battle_round=1,
        transport_unit_instance_id=transport.unit_instance_id,
        firing_deck_value=1,
        weapon_selections=(
            FiringDeckWeaponSelection(
                embarked_unit_instance_id=passenger.unit_instance_id,
                model_instance_id=passenger.own_models[0].model_instance_id,
                weapon_instance_id=next(
                    instance.weapon_instance_id
                    for instance in equipped_weapon_instances_for_model(passenger.own_models[0])
                    if instance.wargear_id == passenger.wargear_selections[0].wargear_ids[0]
                ),
                wargear_id=passenger.wargear_selections[0].wargear_ids[0],
                weapon_profile=profile,
            ),
        ),
    )

    result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=selection,
        embarked_units=(passenger,),
    )
    duplicate_model_result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=replace(
            selection,
            firing_deck_value=2,
            weapon_selections=(selection.weapon_selections[0], selection.weapon_selections[0]),
        ),
        embarked_units=(passenger,),
    )
    one_shot_result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=replace(
            selection,
            weapon_selections=(
                replace(
                    selection.weapon_selections[0],
                    weapon_profile=replace(
                        profile,
                        keywords=(*profile.keywords, WeaponKeyword.ONE_SHOT),
                    ),
                ),
            ),
        ),
        embarked_units=(passenger,),
    )
    forged_instance_result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=replace(
            selection,
            weapon_selections=(
                replace(
                    selection.weapon_selections[0],
                    weapon_instance_id="weapon-instance:forged",
                ),
            ),
        ),
        embarked_units=(passenger,),
    )

    assert result.is_valid
    assert result.temporary_weapon_profiles == (profile,)
    assert result.ineligible_unit_instance_ids == (passenger.unit_instance_id,)
    assert TransportOperationViolationCode.FIRING_DECK_DUPLICATE_MODEL_SELECTION in {
        violation.violation_code for violation in duplicate_model_result.violations
    }
    assert TransportOperationViolationCode.FIRING_DECK_ONE_SHOT_WEAPON in {
        violation.violation_code for violation in one_shot_result.violations
    }
    assert TransportOperationViolationCode.FIRING_DECK_WEAPON_INSTANCE_DRIFT in {
        violation.violation_code for violation in forged_instance_result.violations
    }


def test_firing_deck_reports_capacity_membership_shot_model_and_melee_failures() -> None:
    _scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    ranged_profile = _first_weapon_profile(catalog, passenger)
    melee_profile = _wargear_by_id(catalog, "core-leader-blade").weapon_profiles[0]

    result = resolve_firing_deck_selection(
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=FiringDeckSelection(
            player_id="player-a",
            battle_round=1,
            transport_unit_instance_id=transport.unit_instance_id,
            firing_deck_value=1,
            weapon_selections=(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id="army-alpha:not-embarked",
                    model_instance_id="army-alpha:not-embarked:model-001",
                    weapon_instance_id="weapon-instance:test:not-embarked:001",
                    wargear_id="core-bolt-rifle",
                    weapon_profile=ranged_profile,
                ),
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=passenger.unit_instance_id,
                    model_instance_id="army-alpha:passenger-unit:model-999",
                    weapon_instance_id="weapon-instance:test:unknown-model:001",
                    wargear_id="core-leader-blade",
                    weapon_profile=melee_profile,
                ),
            ),
            already_shot_unit_instance_ids=(passenger.unit_instance_id,),
        ),
        embarked_units=(passenger,),
    )

    assert not result.is_valid
    assert {
        TransportOperationViolationCode.FIRING_DECK_CAPACITY_EXCEEDED,
        TransportOperationViolationCode.FIRING_DECK_UNIT_NOT_EMBARKED,
        TransportOperationViolationCode.FIRING_DECK_UNIT_ALREADY_SHOT,
        TransportOperationViolationCode.FIRING_DECK_MODEL_DRIFT,
        TransportOperationViolationCode.FIRING_DECK_MELEE_WEAPON,
    } <= {violation.violation_code for violation in result.violations}


def test_transport_payloads_round_trip_without_python_reprs() -> None:
    scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    profile = _first_weapon_profile(catalog, passenger)
    override = TransportRestrictionOverride(
        override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
        source_rule_id="phase10q_override",
    )
    violation = TransportOperationViolation(
        violation_code=TransportOperationViolationCode.EMBARK_DISTANCE,
        message="Payload test violation.",
        unit_instance_id=passenger.unit_instance_id,
        model_instance_id=passenger.own_models[0].model_instance_id,
        blocker_id=transport.unit_instance_id,
        source_rule_id="phase10q_payload",
    )
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    selection = FiringDeckSelection(
        player_id="player-a",
        battle_round=1,
        transport_unit_instance_id=transport.unit_instance_id,
        firing_deck_value=1,
        weapon_selections=(
            FiringDeckWeaponSelection(
                embarked_unit_instance_id=passenger.unit_instance_id,
                model_instance_id=passenger.own_models[0].model_instance_id,
                weapon_instance_id=next(
                    instance.weapon_instance_id
                    for instance in equipped_weapon_instances_for_model(passenger.own_models[0])
                    if instance.wargear_id == passenger.wargear_selections[0].wargear_ids[0]
                ),
                wargear_id=passenger.wargear_selections[0].wargear_ids[0],
                weapon_profile=profile,
            ),
        ),
    )
    embark_resolution = resolve_embark(
        scenario=scenario,
        cargo_state=_cargo_state(transport=transport),
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(passenger.unit_instance_id),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )
    disembark_resolution = resolve_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=_unit_placement_at(
                passenger,
                army_id="army-alpha",
                player_id="player-a",
                poses=_disembark_poses(),
            ),
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )
    destroyed_resolution = resolve_destroyed_transport_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=replace(
            disembark_resolution.selection,
            disembark_mode=DisembarkModeKind.DESTROYED_TRANSPORT,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(10),
    )
    firing_deck_resolution = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=selection,
        embarked_units=(passenger,),
    )

    cargo_blob = json.dumps(cargo_state.to_payload(), sort_keys=True)
    selection_blob = json.dumps(selection.to_payload(), sort_keys=True)
    violation_blob = json.dumps(violation.to_payload(), sort_keys=True)

    assert "<" not in cargo_blob
    assert "object at 0x" not in cargo_blob
    assert "<" not in selection_blob
    assert "object at 0x" not in selection_blob
    assert "<" not in violation_blob
    assert "object at 0x" not in violation_blob
    assert TransportRestrictionOverride.from_payload(override.to_payload()) == override
    assert TransportOperationViolation.from_payload(violation.to_payload()) == violation
    assert TransportCargoState.from_payload(cargo_state.to_payload()) == cargo_state
    assert FiringDeckSelection.from_payload(selection.to_payload()) == selection
    assert EmbarkResolution.from_payload(embark_resolution.to_payload()) == embark_resolution
    assert DisembarkResolution.from_payload(disembark_resolution.to_payload()) == (
        disembark_resolution
    )
    assert (
        DestroyedTransportDisembark.from_payload(destroyed_resolution.to_payload())
        == destroyed_resolution
    )
    assert (
        FiringDeckResolution.from_payload(firing_deck_resolution.to_payload())
        == firing_deck_resolution
    )
    assert EmbarkSelection.from_payload(
        EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
            restriction_overrides=(override,),
        ).to_payload()
    ).restriction_overrides == (override,)
    assert (
        DisembarkSelection.from_payload(
            DisembarkSelection(
                player_id="player-a",
                battle_round=1,
                unit_instance_id=passenger.unit_instance_id,
                transport_unit_instance_id=transport.unit_instance_id,
                attempted_placement=_unit_placement_at(
                    passenger,
                    army_id="army-alpha",
                    player_id="player-a",
                    poses=_disembark_poses(),
                ),
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ).transport_movement_status
        is TransportMovementStatus.NOT_MOVED
    )


def test_resolution_payloads_reject_destroyed_transport_and_firing_deck_drift() -> None:
    scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    disembark_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=_unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=_disembark_poses(),
        ),
        disembark_mode=DisembarkModeKind.DESTROYED_TRANSPORT,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    destroyed_resolution = resolve_destroyed_transport_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=disembark_selection,
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(10),
    )
    bad_mortal_wound_roll = replace(
        destroyed_resolution.model_rolls[0],
        mortal_wound_inflicted=not destroyed_resolution.model_rolls[0].mortal_wound_inflicted,
    )
    with pytest.raises(GameLifecycleError, match="mortal wound roll drift"):
        DestroyedTransportDisembark(
            player_id=destroyed_resolution.player_id,
            battle_round=destroyed_resolution.battle_round,
            unit_instance_id=destroyed_resolution.unit_instance_id,
            transport_unit_instance_id=destroyed_resolution.transport_unit_instance_id,
            disembark_mode=destroyed_resolution.disembark_mode,
            placement=destroyed_resolution.placement,
            roll_threshold=destroyed_resolution.roll_threshold,
            model_rolls=(bad_mortal_wound_roll, *destroyed_resolution.model_rolls[1:]),
            destroyed_model_instance_ids=destroyed_resolution.destroyed_model_instance_ids,
        )
    bad_model_roll = replace(
        destroyed_resolution.model_rolls[0],
        model_instance_id="army-alpha:passenger-unit:model-999",
    )
    with pytest.raises(GameLifecycleError, match="roll model drift"):
        DestroyedTransportDisembark(
            player_id=destroyed_resolution.player_id,
            battle_round=destroyed_resolution.battle_round,
            unit_instance_id=destroyed_resolution.unit_instance_id,
            transport_unit_instance_id=destroyed_resolution.transport_unit_instance_id,
            disembark_mode=destroyed_resolution.disembark_mode,
            placement=destroyed_resolution.placement,
            roll_threshold=destroyed_resolution.roll_threshold,
            model_rolls=(bad_model_roll, *destroyed_resolution.model_rolls[1:]),
            destroyed_model_instance_ids=destroyed_resolution.destroyed_model_instance_ids,
        )
    destroyed_payload = destroyed_resolution.to_payload()
    destroyed_payload["mortal_wound_count"] += 1
    with pytest.raises(GameLifecycleError, match="mortal wound count drift"):
        DestroyedTransportDisembark.from_payload(destroyed_payload)

    profile = _first_weapon_profile(catalog, passenger)
    firing_deck_resolution = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=FiringDeckSelection(
            player_id="player-a",
            battle_round=1,
            transport_unit_instance_id=transport.unit_instance_id,
            firing_deck_value=1,
            weapon_selections=(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=passenger.unit_instance_id,
                    model_instance_id=passenger.own_models[0].model_instance_id,
                    weapon_instance_id=next(
                        instance.weapon_instance_id
                        for instance in equipped_weapon_instances_for_model(passenger.own_models[0])
                        if instance.wargear_id == passenger.wargear_selections[0].wargear_ids[0]
                    ),
                    wargear_id=passenger.wargear_selections[0].wargear_ids[0],
                    weapon_profile=profile,
                ),
            ),
        ),
        embarked_units=(passenger,),
    )
    firing_payload = firing_deck_resolution.to_payload()
    firing_payload["temporary_weapon_profiles"][0] = {
        **firing_payload["temporary_weapon_profiles"][0],
        "name": "Drifted Temporary Weapon",
    }
    with pytest.raises(GameLifecycleError, match="weapon profile drift"):
        FiringDeckResolution.from_payload(firing_payload)


def test_transport_token_parsers_reject_invalid_values() -> None:
    with pytest.raises(GameLifecycleError, match="TransportMovementStatus token"):
        transport_movement_status_from_token(123)
    with pytest.raises(GameLifecycleError, match="Unsupported TransportMovementStatus"):
        transport_movement_status_from_token("bad-status")
    with pytest.raises(GameLifecycleError, match="TransportRestrictionOverrideKind token"):
        transport_restriction_override_kind_from_token(None)
    with pytest.raises(GameLifecycleError, match="Unsupported TransportRestrictionOverrideKind"):
        transport_restriction_override_kind_from_token("bad-override")
    with pytest.raises(GameLifecycleError, match="DisembarkModeKind token"):
        disembark_mode_kind_from_token(False)
    with pytest.raises(GameLifecycleError, match="Unsupported DisembarkModeKind"):
        disembark_mode_kind_from_token("bad-disembark")
    with pytest.raises(GameLifecycleError, match="TransportOperationViolationCode token"):
        transport_operation_violation_code_from_token(3.14)
    with pytest.raises(GameLifecycleError, match="Unsupported TransportOperationViolationCode"):
        transport_operation_violation_code_from_token("bad-violation")


def test_transport_cargo_state_rejects_invalid_direct_operations() -> None:
    _scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
    )

    with pytest.raises(GameLifecycleError, match="already embarked"):
        cargo_state.with_embarked_unit(passenger.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="not embarked"):
        _cargo_state(transport=transport).with_disembarked_unit(passenger.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="UnitInstance"):
        cargo_state.capacity_profile.allows_unit(cast(UnitInstance, object()))


def test_transport_resolvers_fail_fast_on_wrong_domain_objects() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    cargo_state = _cargo_state(transport=transport)
    embark_selection = EmbarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
    )

    with pytest.raises(GameLifecycleError, match="BattlefieldScenario"):
        resolve_embark(
            scenario=cast(BattlefieldScenario, object()),
            cargo_state=cargo_state,
            selection=embark_selection,
            unit_placement=passenger_placement,
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="TransportCargoState"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cast(TransportCargoState, object()),
            selection=embark_selection,
            unit_placement=passenger_placement,
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="EmbarkSelection"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=cast(EmbarkSelection, object()),
            unit_placement=passenger_placement,
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="unit_placement"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=embark_selection,
            unit_placement=cast(UnitPlacement, object()),
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="transport_placement"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=embark_selection,
            unit_placement=passenger_placement,
            transport_placement=cast(UnitPlacement, object()),
        )


def test_disembarked_units_use_shared_movement_decision_path_restrictions() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    disembarked_state = resolve_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=scenario.battlefield_state.unit_placement_by_id(
                passenger.unit_instance_id
            ),
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    ).disembarked_unit_state
    assert disembarked_state is not None
    state.record_disembarked_unit_state(disembarked_state)
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=(passenger.unit_instance_id,),
        active_selection=MovementUnitSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            request_id="phase10q-select-passenger",
            result_id="phase10q-select-passenger-result",
        ),
    )

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=state,
        decisions=DecisionController(),
    )

    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert MovementPhaseActionKind.REMAIN_STATIONARY.value not in {
        option.option_id for option in status.decision_request.options
    }


def _embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    ArmyCatalog,
]:
    scenario, passenger, transport, enemy, catalog = _transport_scenario()
    post_move_poses = (
        Pose.at(8.6, 13.0),
        Pose.at(10.0, 13.0),
        Pose.at(11.4, 13.0),
        Pose.at(9.3, 14.2),
        Pose.at(10.7, 14.2),
    )
    battlefield = scenario.battlefield_state.with_unit_placement(
        _unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=tuple(
                Pose.at(
                    pose.position.x - 6.0,
                    pose.position.y,
                    pose.position.z,
                    facing_degrees=pose.facing.degrees,
                )
                for pose in post_move_poses
            ),
        )
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _attached_embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="attached-bodyguard",
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
                _unit_selection(
                    unit_selection_id="attached-leader",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
                _unit_selection(
                    unit_selection_id="transport-1",
                    datasheet_id="core-transport",
                    model_profile_id="core-transport",
                    model_count=1,
                ),
            ),
        ),
    )
    bodyguard = alpha.unit_by_id("army-alpha:attached-bodyguard")
    leader = alpha.unit_by_id("army-alpha:attached-leader")
    transport = alpha.unit_by_id("army-alpha:transport-1")
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    alpha = replace(
        alpha,
        attached_units=(
            AttachedUnitFormation(
                attached_unit_instance_id=(
                    "attached-unit:army-alpha:attached-transport-passengers"
                ),
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(leader.unit_instance_id,),
                component_unit_instance_ids=component_ids,
                source_id="test:phase10q-attached-embark",
                attachment_source_ids=("test:phase10q-attached-embark-eligibility",),
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
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10q-attached-embark-battlefield",
        armies=(alpha, beta),
    )
    enemy = beta.unit_by_id("army-beta:enemy-unit")
    battlefield = (
        scenario.battlefield_state.with_unit_placement(
            _unit_placement_at(
                bodyguard,
                army_id=alpha.army_id,
                player_id=alpha.player_id,
                poses=(
                    Pose.at(8.1, 13.0),
                    Pose.at(9.5, 13.0),
                    Pose.at(10.9, 13.0),
                    Pose.at(8.8, 14.2),
                    Pose.at(10.2, 14.2),
                ),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                leader,
                army_id=alpha.army_id,
                player_id=alpha.player_id,
                poses=(Pose.at(12.3, 14.4),),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                transport,
                army_id=alpha.army_id,
                player_id=alpha.player_id,
                poses=(Pose.at(10.0, 10.0),),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                enemy,
                army_id=beta.army_id,
                player_id=beta.player_id,
                poses=tuple(Pose.at(35.0 + index * 2.0, 35.0) for index in range(5)),
            )
        )
    )
    return (
        BattlefieldScenario(armies=(alpha, beta), battlefield_state=battlefield),
        bodyguard,
        leader,
        transport,
    )


def _advance_embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    ArmyCatalog,
]:
    scenario, passenger, transport, enemy, catalog = _transport_scenario()
    battlefield = scenario.battlefield_state.with_unit_placement(
        _unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=(
                Pose.at(1.6, 9.0),
                Pose.at(3.0, 9.0),
                Pose.at(4.4, 9.0),
                Pose.at(2.3, 10.2),
                Pose.at(3.7, 10.2),
            ),
        )
    ).with_unit_placement(
        _unit_placement_at(
            transport,
            army_id="army-alpha",
            player_id="player-a",
            poses=(Pose.at(14.0, 10.0),),
        )
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _fall_back_embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    ArmyCatalog,
]:
    scenario, passenger, transport, enemy, catalog = _transport_scenario()
    battlefield = (
        scenario.battlefield_state.with_unit_placement(
            _unit_placement_at(
                passenger,
                army_id="army-alpha",
                player_id="player-a",
                poses=(
                    Pose.at(2.6, 9.0),
                    Pose.at(4.0, 9.0),
                    Pose.at(5.4, 9.0),
                    Pose.at(3.3, 10.2),
                    Pose.at(4.7, 10.2),
                ),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                transport,
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(4.0, 19.0),),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                enemy,
                army_id="army-beta",
                player_id="player-b",
                poses=(
                    Pose.at(2.6, 7.5),
                    Pose.at(35.0, 35.0),
                    Pose.at(37.0, 35.0),
                    Pose.at(39.0, 35.0),
                    Pose.at(41.0, 35.0),
                ),
            )
        )
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
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
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert selection_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    selected_option_id = next(
        option.option_id
        for option in selection_request.options
        if option.option_id == unit_instance_id
        or _movement_option_contains_component(option.payload, unit_instance_id)
    )
    selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=selected_option_id,
        result_id=f"{unit_instance_id}:select-move",
    )
    assert selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return handler, decisions, action_request


def _movement_option_contains_component(payload: JsonValue, unit_instance_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    component_ids = payload.get("component_unit_instance_ids")
    return isinstance(component_ids, list) and unit_instance_id in component_ids


def _rapid_disembark_request_after_transport_normal_move(
    *,
    state: GameState,
    passenger: UnitInstance,
    transport: UnitInstance,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    movement_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert movement_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    transport_selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=movement_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-select-transport-normal-move",
    )
    assert transport_selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    post_move_disembark_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10q-transport-normal-move",
    )
    movement_proposal_request = _decision_request(post_move_disembark_status)
    assert movement_proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    post_move_disembark_status = _submit_transport_normal_move_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=movement_proposal_request,
        transport=transport,
        result_id="phase10q-transport-normal-move-proposal",
    )
    assert post_move_disembark_status is None
    passenger_selection_request = _decision_request(
        handler.begin_phase(state=state, decisions=decisions)
    )
    assert passenger_selection_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert (
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=passenger_selection_request,
            option_id=passenger.unit_instance_id,
            result_id="phase10q-select-passenger-after-transport",
        )
        is None
    )
    return (
        handler,
        decisions,
        _decision_request(handler.begin_phase(state=state, decisions=decisions)),
    )


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
    return handler.apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )


def _submit_action_and_movement_payload(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    unit: UnitInstance,
    movement_phase_action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    dx: float = 0.0,
    dy: float = 0.0,
    fall_back_mode: FallBackModeKind | None = None,
    result_id: str,
) -> LifecycleStatus | None:
    proposal_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=request,
        option_id=option_id,
        result_id=result_id,
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert state.battlefield_state is not None
    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=proposal.unit_instance_id,
    )
    rules_unit_placement = RulesUnitPlacement.from_battlefield(
        view=rules_unit,
        battlefield_state=state.battlefield_state,
    )
    witness = PathWitness.for_paths(
        tuple(
            model_path
            for component in rules_unit_placement.component_unit_placements
            for model_path in _shift_witness(component, dx=dx, dy=dy).model_paths
        )
    )
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=movement_phase_action.value,
        witness=witness,
        movement_mode=movement_mode.value,
        fall_back_mode=None if fall_back_mode is None else fall_back_mode.value,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=proposal_request,
        payload=validate_json_value(payload),
        result_id=f"{result_id}-proposal",
    )


def _submit_transport_normal_move_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    transport: UnitInstance,
    result_id: str,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert state.battlefield_state is not None
    transport_placement = state.battlefield_state.unit_placement_by_id(transport.unit_instance_id)
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=transport.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        witness=_shift_witness(transport_placement, dx=-0.5),
        movement_mode=MovementMode.NORMAL.value,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_disembark_placement_payload(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    passenger: UnitInstance,
    transport: UnitInstance,
    disembark_mode: DisembarkModeKind,
    transport_movement_status: TransportMovementStatus,
    result_id: str,
    poses: tuple[Pose, ...] | None = None,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    placement_poses = _disembark_poses()[: len(passenger.own_models)] if poses is None else poses
    if transport_movement_status is TransportMovementStatus.NORMAL_MOVE:
        placement_poses = tuple(
            Pose.at(
                pose.position.x - 0.5,
                pose.position.y,
                pose.position.z,
                facing_degrees=pose.facing.degrees,
            )
            for pose in placement_poses
        )
    placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=placement_poses,
    )
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=placement,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=disembark_mode,
        transport_movement_status=transport_movement_status,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_rules_unit_disembark_placement_payload(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    placement: RulesUnitPlacement,
    transport: UnitInstance,
    disembark_mode: DisembarkModeKind = DisembarkModeKind.TACTICAL_DISEMBARK,
    result_id: str,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=placement.rules_unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_rules_unit_placement=placement,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=disembark_mode,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="submit_parameterized_payload",
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, result=result, decisions=decisions)


def _attached_tactical_disembark_setup_boundary() -> tuple[
    GameState,
    MovementPhaseHandler,
    DecisionController,
    UnitInstance,
    UnitInstance,
]:
    scenario, bodyguard, leader, transport = _attached_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-disembark-setup-destruction")
    attached_id = "attached-unit:army-alpha:attached-transport-passengers"
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(
            bodyguard.unit_instance_id
        ).without_unit_placement(leader.unit_instance_id)
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=component_ids,
            started_unit_ids=component_ids,
            battle_round=1,
            max_model_count=6,
        )
    )
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.DISEMBARK.value,
            result_id="phase10q-destruction-disembark-action",
        )
    )
    placement = RulesUnitPlacement(
        rules_unit_instance_id=attached_id,
        component_unit_placements=(
            _unit_placement_at(
                bodyguard,
                army_id="army-alpha",
                player_id="player-a",
                poses=(
                    Pose.at(8.6, 13.0),
                    Pose.at(10.0, 13.0),
                    Pose.at(11.4, 13.0),
                    Pose.at(9.3, 14.2),
                    Pose.at(10.7, 14.2),
                ),
            ),
            _unit_placement_at(
                leader,
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(12.6, 11.8),),
            ),
        ),
    )
    assert (
        _submit_rules_unit_disembark_placement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=placement_request,
            placement=placement,
            transport=transport,
            result_id="phase10q-destruction-disembark-placement",
        )
        is None
    )
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.pending_setup_event_id is not None
    return state, handler, decisions, bodyguard, leader


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _last_event_payload(decisions: DecisionController, event_type: str) -> dict[str, object]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _placed_unit_ids(state: GameState) -> set[str]:
    assert state.battlefield_state is not None
    return {
        placement.unit_instance_id
        for army in state.battlefield_state.placed_armies
        for placement in army.unit_placements
    }


def _advanced_unit_state(unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10q-invalid-advanced-state-roll",
        game_id="phase10q-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase10q-invalid-advanced-state").roll_fixed(
        request.spec,
        [3],
    )
    advance_roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=advance_roll,
        ),
    )


def _record_declared_reserve_for_replay_fixture(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> DecisionController:
    decisions = DecisionController()
    reserve_state = ReserveState.declared_before_battle(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_kind=ReserveKind.RESERVES,
        destruction_deadline_policy=reposition_destruction_policy(
            mission_setup=state.mission_setup,
            destruction_deadline_policy=None,
        ),
    )
    state.record_reserve_state(reserve_state)
    decisions.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "unit_instance_id": unit_instance_id,
            "reserve_state": reserve_state.to_payload(),
        },
    )
    return decisions


def _transport_scenario(
    *,
    passenger_datasheet_id: str = "core-intercessor-like-infantry",
    passenger_model_profile_id: str = "core-intercessor-like",
    passenger_model_count: int = 5,
    passenger_unit_selection_id: str = "passenger-unit",
    enemy_attached: bool = False,
) -> tuple[BattlefieldScenario, UnitInstance, UnitInstance, UnitInstance, ArmyCatalog]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha_request = _army_muster_request(
        catalog=catalog,
        player_id="player-a",
        army_id="army-alpha",
        unit_selections=(
            _unit_selection(
                unit_selection_id=passenger_unit_selection_id,
                datasheet_id=passenger_datasheet_id,
                model_profile_id=passenger_model_profile_id,
                model_count=passenger_model_count,
            ),
            _unit_selection(
                unit_selection_id="transport-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )
    beta_request = _army_muster_request(
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
            *(
                (
                    _unit_selection(
                        unit_selection_id="enemy-leader",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                )
                if enemy_attached
                else ()
            ),
        ),
    )
    alpha = muster_army(catalog=catalog, request=alpha_request)
    beta = muster_army(catalog=catalog, request=beta_request)
    if enemy_attached:
        enemy_bodyguard = beta.unit_by_id("army-beta:enemy-unit")
        enemy_leader = beta.unit_by_id("army-beta:enemy-leader")
        component_ids = tuple(
            sorted((enemy_bodyguard.unit_instance_id, enemy_leader.unit_instance_id))
        )
        beta = replace(
            beta,
            attached_units=(
                AttachedUnitFormation(
                    attached_unit_instance_id="attached-unit:army-beta:enemy-attached",
                    bodyguard_unit_instance_id=enemy_bodyguard.unit_instance_id,
                    leader_unit_instance_ids=(enemy_leader.unit_instance_id,),
                    component_unit_instance_ids=component_ids,
                    source_id="test:phase10q-combat-disembark-attached-enemy",
                    attachment_source_ids=("test:phase10q-combat-disembark-attached-eligibility",),
                ),
            ),
        )
    armies = (alpha, beta)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10q-battlefield",
        armies=armies,
    )
    passenger = armies[0].unit_by_id(f"army-alpha:{passenger_unit_selection_id}")
    transport = armies[0].unit_by_id("army-alpha:transport-1")
    enemy = armies[1].unit_by_id("army-beta:enemy-unit")
    battlefield = scenario.battlefield_state
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=_disembark_poses()[: len(passenger.own_models)],
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            transport,
            army_id="army-alpha",
            player_id="player-a",
            poses=(Pose.at(10.0, 10.0),),
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id="army-beta",
            player_id="player-b",
            poses=tuple(
                Pose.at(35.0 + index * 2.0, 35.0) for index in range(len(enemy.own_models))
            ),
        )
    )
    return (
        BattlefieldScenario(armies=armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh()


def _battle_state(
    scenario: BattlefieldScenario,
    *,
    game_id: str = "phase10q-game",
) -> GameState:
    ruleset = _ruleset()
    return GameState(
        game_id=game_id,
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
        starting_attached_unit_records=[
            record
            for army in scenario.armies
            for record in starting_attached_unit_records_for_army(army)
        ],
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


def _transport_reaction_window(
    *,
    state: GameState,
    eligible_player_id: str,
) -> ReactionWindow:
    return ReactionWindow(
        timing_window=TimingWindow(
            window_id="phase14h-transport-hazard-reaction-window",
            descriptor=TimingWindowDescriptor(
                descriptor_id="phase14h-transport-hazard-reaction-descriptor",
                trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
                source_rule_id="phase14h-transport-hazard-reaction-rule",
                phase=BattlePhase.MOVEMENT,
                source_step="phase14h_transport_hazard_reaction",
            ),
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            phase=BattlePhase.MOVEMENT,
            trigger_event_id=None,
        ),
        eligible_player_ids=(eligible_player_id,),
    )


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


def _cargo_state(
    *,
    transport: UnitInstance,
    embarked_unit_ids: tuple[str, ...] = (),
    started_unit_ids: tuple[str, ...] = (),
    disembarked_unit_ids: tuple[str, ...] = (),
    battle_round: int | None = None,
    max_model_count: int = 10,
) -> TransportCargoState:
    return TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=max_model_count,
            allowed_keywords=("INFANTRY",),
        ),
        embarked_unit_instance_ids=embarked_unit_ids,
        phase_battle_round=battle_round,
        started_phase_embarked_unit_instance_ids=started_unit_ids,
        disembarked_this_phase_unit_instance_ids=disembarked_unit_ids,
    )


def _without_unit(scenario: BattlefieldScenario, unit_instance_id: str) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(unit_instance_id),
    )


def _with_destroyed_attached_component(
    scenario: BattlefieldScenario,
    *,
    unit_instance_id: str,
) -> BattlefieldScenario:
    updated_armies = tuple(
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    keywords=("MONSTER",),
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
                if unit.unit_instance_id == unit_instance_id
                else unit
                for unit in army.units
            ),
        )
        if any(unit.unit_instance_id == unit_instance_id for unit in army.units)
        else army
        for army in scenario.armies
    )
    return BattlefieldScenario(
        armies=updated_armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(unit_instance_id),
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) > len(unit.own_models):
        raise AssertionError("Test placement has too many poses.")
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=False)
        ),
    )


def _combat_hazard_roll_results(
    attempted_placement: UnitPlacement,
    *,
    values: tuple[int, ...],
    roll_id_prefix: str,
) -> tuple[DiceRollResult, ...]:
    if len(values) != len(attempted_placement.model_placements):
        raise AssertionError("Combat hazard roll values must match placed models.")
    return tuple(
        DiceRollResult.from_values(
            roll_id=f"{roll_id_prefix}-{index:03d}",
            spec=hazard_roll_spec(
                reason=f"Combat Disembark hazard roll for {model_placement.model_instance_id}",
                roll_type="combat_disembark.hazard_roll",
                actor_id=model_placement.model_instance_id,
            ),
            values=(roll_value,),
            source="injected",
        )
        for index, (model_placement, roll_value) in enumerate(
            zip(attempted_placement.model_placements, values, strict=True),
            start=1,
        )
    )


def _destroyed_transport_hazard_roll_results(
    attempted_placement: UnitPlacement,
    *,
    values: tuple[int, ...],
    roll_id_prefix: str,
) -> tuple[DiceRollResult, ...]:
    if len(values) != len(attempted_placement.model_placements):
        raise AssertionError("Destroyed Transport hazard roll values must match placed models.")
    return tuple(
        DiceRollResult.from_values(
            roll_id=f"{roll_id_prefix}-{index:03d}",
            spec=hazard_roll_spec(
                reason=(
                    f"Destroyed Transport disembark roll for {model_placement.model_instance_id}"
                ),
                roll_type="destroyed_transport_disembark",
                actor_id=model_placement.model_instance_id,
            ),
            values=(roll_value,),
            source="injected",
        )
        for index, (model_placement, roll_value) in enumerate(
            zip(attempted_placement.model_placements, values, strict=True),
            start=1,
        )
    )


def _shift_witness(
    unit_placement: UnitPlacement,
    *,
    dx: float,
    dy: float = 0.0,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _disembark_poses(*, z_inches: float = 0.0) -> tuple[Pose, ...]:
    return (
        Pose.at(13.1, 8.5, z_inches),
        Pose.at(14.0, 9.8, z_inches),
        Pose.at(14.0, 11.2, z_inches),
        Pose.at(13.1, 12.5, z_inches),
        Pose.at(12.8, 10.5, z_inches),
    )


def _left_side_disembark_poses(*, z_inches: float = 0.0) -> tuple[Pose, ...]:
    return (
        Pose.at(6.9, 8.5, z_inches),
        Pose.at(6.0, 9.8, z_inches),
        Pose.at(6.0, 11.2, z_inches),
        Pose.at(6.9, 12.5, z_inches),
        Pose.at(7.2, 10.5, z_inches),
    )


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _support_feature(
    *,
    feature_id: str,
    feature_kind: TerrainFeatureKind,
    center_x_inches: float,
    center_y_inches: float,
    z_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=feature_kind,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=width_inches,
        footprint_depth_inches=depth_inches,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=width_inches,
            depth_inches=depth_inches,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=width_inches,
            depth_inches=depth_inches,
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="top",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=z_inches,
                width_inches=width_inches,
                depth_inches=depth_inches,
                thickness_inches=0.12,
            ),
        ),
    )


def _ruins_floor_feature(
    *,
    feature_id: str,
    center_x_inches: float,
    center_y_inches: float,
    upper_width_inches: float,
    upper_depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=6.0,
            depth_inches=6.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=6.0,
            depth_inches=6.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="north-wall",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches + 2.94,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=0.12,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
            TerrainFloorDefinition(
                floor_id="upper",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=3.0,
                width_inches=upper_width_inches,
                depth_inches=upper_depth_inches,
                thickness_inches=0.12,
            ),
        ),
    )


def _first_weapon_profile(catalog: ArmyCatalog, unit: UnitInstance) -> WeaponProfile:
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    wargear = _wargear_by_id(catalog, wargear_id)
    return wargear.weapon_profiles[0]


def _wargear_by_id(catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            return wargear
    raise AssertionError(f"Missing test wargear: {wargear_id}")
