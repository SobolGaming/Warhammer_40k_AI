from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.setup_completion_helpers import enter_battle_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attack_sequence import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
    CommandStepState,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    FeelNoPainSource,
    model_by_id,
)
from warhammer40k_core.engine.decision import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.phases.movement import (
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
    MovementPhaseState,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_stratagem_catalog_records,
    eleventh_edition_stratagem_index,
)
from warhammer40k_core.engine.stratagems import (
    COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY,
    COMMAND_REROLL_DICE_CONTEXT_KEY,
    CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY,
    CRUSHING_IMPACT_MODEL_CONTEXT_KEY,
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY,
    EXPLOSIVES_TARGET_CONTEXT_KEY,
    FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY,
    HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
    HEROIC_INTERVENTION_MODE_INTO_THE_FRAY,
    SELECTED_TARGET_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    StratagemUseRecord,
    _handler_unavailable_reason,
    create_stratagem_target_proposal_decision_request,
    create_stratagem_use_decision_request,
    invalid_heroic_intervention_charge_move_status,
    is_heroic_intervention_charge_move_request,
    is_stratagem_window_decline_result,
    request_stratagem_target_proposal,
    request_stratagem_use,
    request_stratagem_use_from_index,
    stratagem_availability_kind_from_token,
    stratagem_category_from_token,
    stratagem_decline_option,
    stratagem_decline_payload,
    stratagem_target_kind_from_token,
    stratagem_target_proposal_request_payload,
    stratagem_use_options,
    stratagem_window_context_from_request,
    stratagem_window_decline_allowed,
    stratagem_window_decline_event_payload,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.engine.weapon_abilities import SNAP_SHOOTING_RULE_ID
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_command_reroll_source_handler_resolves_via_restored_lifecycle() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    assert "advance_roll" in command_reroll.definition.eligible_roll_types
    assert "desperate_escape_roll" not in command_reroll.definition.eligible_roll_types
    assert "number_of_attacks_roll" in command_reroll.definition.eligible_roll_types
    assert "random_damage" not in command_reroll.definition.eligible_roll_types
    assert "battle_shock_roll" not in command_reroll.definition.eligible_roll_types
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-a")
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    restored_request = _decision_request(restored.advance_until_decision_or_terminal())

    restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll",
            request=restored_request,
            selected_option_id=request.options[0].option_id,
        )
    )
    restored_state = _state(restored)

    assert restored_state.command_point_total("player-a") == 0
    assert len(restored_state.stratagem_use_records) == 1
    assert restored_state.stratagem_use_records[0].handler_id == "core:command-reroll"
    assert _has_event(restored.decision_controller, "dice_reroll_resolved")
    assert (
        _last_event_payload(restored.decision_controller, "command_reroll_resolved")[
            "stratagem_use"
        ]
        == restored_state.stratagem_use_records[0].to_payload()
    )
    assert "<" not in json.dumps(restored.to_payload(), sort_keys=True)


def test_command_reroll_source_eligibility_rejects_unlisted_roll_type_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="validation_roll",
    )
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    assert (
        stratagem_use_options(
            state=state,
            catalog_records=(command_reroll,),
            context=context,
        )
        == ()
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            _handcrafted_stratagem_option(
                record=command_reroll,
                context=context,
                binding=StratagemTargetBinding.none(),
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll-ineligible-roll",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "ineligible_dice_roll_type"}
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_command_reroll_rejects_opponent_roll_actor_drift_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-b")
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    assert (
        stratagem_use_options(
            state=state,
            catalog_records=(command_reroll,),
            context=context,
        )
        == ()
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            _handcrafted_stratagem_option(
                record=command_reroll,
                context=context,
                binding=StratagemTargetBinding.none(),
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll-actor-drift",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "dice_roll_actor_drift"}
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


@pytest.mark.parametrize(
    "roll_spec",
    [
        attack_sequence_hit_roll_spec(
            weapon_profile_id="phase14i-bolt-rifle",
            attack_context_id="phase14i-hit:pool-001:attack-001",
            attacker_player_id="player-a",
        ),
        attack_sequence_wound_roll_spec(
            weapon_profile_id="phase14i-bolt-rifle",
            attack_context_id="phase14i-wound:pool-001:attack-001",
            attacker_player_id="player-a",
        ),
        saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-a",
            allocated_model_id="phase14i-intercessor-1",
            attack_context_id="phase14i-save:pool-001:attack-001",
        ),
    ],
)
def test_phase14i_command_reroll_accepts_real_attack_and_save_roll_specs(
    roll_spec: DiceRollSpec,
) -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate_from_spec(lifecycle, spec=roll_spec)
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"phase14i-command-reroll-{roll_spec.roll_type.replace('.', '-')}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert len(state.stratagem_use_records) == 1
    assert state.stratagem_use_records[-1].command_point_cost == 1
    assert state.stratagem_use_records[-1].command_point_transaction_id is not None
    assert _has_event(lifecycle.decision_controller, "command_reroll_resolved")


def test_command_reroll_allows_eleventh_edition_number_of_attacks_roll_for_actor() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="number_of_attacks_roll",
    )
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll-number-of-attacks",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert len(state.stratagem_use_records) == 1
    assert state.stratagem_use_records[-1].command_point_cost == 1
    assert state.stratagem_use_records[-1].command_point_transaction_id is not None
    assert _has_event(lifecycle.decision_controller, "command_reroll_resolved")


def test_phase14i_command_reroll_unlisted_roll_classes_are_domain_invalid() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    command_reroll = _source_stratagem_record("command-reroll")

    for roll_type in (
        "attack_sequence.allocation_order.no_save",
        "battle_shock_roll",
        "leadership_roll",
        "desperate_escape_roll",
    ):
        roll_state = _roll_command_reroll_candidate(
            lifecycle,
            actor_id="player-a",
            roll_type=roll_type,
        )
        context = _context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            trigger_payload=_command_reroll_trigger_payload(roll_state),
        )

        assert (
            _handler_unavailable_reason(
                state=state,
                definition=command_reroll.definition,
                context=context,
                target_binding=StratagemTargetBinding.none(),
                effect_selection=None,
                ruleset_descriptor=lifecycle.config.ruleset_descriptor,
            )
            == "ineligible_dice_roll_type"
        )


def test_phase14i_command_reroll_unlisted_roll_rejects_without_mutation() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_type = "battle_shock_roll"
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type=roll_type,
    )
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            _handcrafted_stratagem_option(
                record=command_reroll,
                context=context,
                binding=StratagemTargetBinding.none(),
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"phase14i-command-reroll-rejects-{roll_type}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "ineligible_dice_roll_type"}
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_phase14i_command_reroll_non_charge_multi_dice_roll_selects_one_die() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="number_of_attacks_roll",
        quantity=2,
        values=(1, 5),
    )
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)
    selection_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14i-command-reroll-multi-dice-source",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )
    selection_request = _decision_request(selection_status)
    permission = cast(
        dict[str, object], cast(dict[str, object], selection_request.payload)["permission"]
    )

    assert selection_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert tuple(option.option_id for option in selection_request.options) == (
        "decline",
        "reroll:0",
        "reroll:1",
    )
    assert permission["component_selection_policy"] == "component_selection"
    assert permission["allowed_component_selections"] == [[0], [1]]

    resolved = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14i-command-reroll-selected-die",
            request=selection_request,
            selected_option_id="reroll:0",
        )
    )
    payload = _last_event_payload(lifecycle.decision_controller, "command_reroll_resolved")
    updated_roll_state = cast(dict[str, object], payload["updated_roll_state"])
    rerolls = cast(list[dict[str, object]], updated_roll_state["rerolls"])

    assert resolved.status_kind is not LifecycleStatusKind.INVALID
    assert len(state.stratagem_use_records) == 1
    assert state.stratagem_use_records[-1].command_point_cost == 1
    assert state.stratagem_use_records[-1].command_point_transaction_id is not None
    assert cast(dict[str, object], payload["reroll_result"])["selected_option_id"] == "reroll:0"
    assert rerolls[0]["selected_indices"] == [0]


def test_phase14i_command_reroll_charge_roll_keeps_whole_roll_selection() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="charge_roll",
        quantity=2,
        values=(1, 2),
    )
    trigger_payload = _command_reroll_trigger_payload(roll_state)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)
    resolved = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14i-command-reroll-charge-roll",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )
    payload = _last_event_payload(lifecycle.decision_controller, "command_reroll_resolved")
    updated_roll_state = cast(dict[str, object], payload["updated_roll_state"])
    rerolls = cast(list[dict[str, object]], updated_roll_state["rerolls"])

    assert resolved.status_kind is not LifecycleStatusKind.INVALID
    assert not _has_event(lifecycle.decision_controller, "command_reroll_selection_requested")
    assert cast(dict[str, object], payload["reroll_result"])["selected_option_id"] == "reroll:0,1"
    assert rerolls[0]["selected_indices"] == [0, 1]


def test_command_reroll_requires_affected_unit_context_and_records_it() -> None:
    unit_id = "army-alpha:intercessor-unit-1"
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="charge_roll",
        quantity=2,
        values=(1, 2),
    )
    missing_unit_context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=validate_json_value(
            {COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload())}
        ),
    )

    assert (
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=(command_reroll,),
            context=missing_unit_context,
        ).status_kind
        is LifecycleStatusKind.UNSUPPORTED
    )

    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=_command_reroll_trigger_payload(roll_state, unit_instance_id=unit_id),
    )
    request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=(command_reroll,),
            context=context,
        )
    )
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14i-command-reroll-affected-unit",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    use_record = state.stratagem_use_records[0]
    assert use_record.affected_unit_instance_ids == (unit_id,)
    assert _last_event_payload(lifecycle.decision_controller, "stratagem_used")[
        "affected_unit_instance_ids"
    ] == [unit_id]


def test_command_reroll_rejects_unknown_affected_unit_context() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="charge_roll",
        quantity=2,
        values=(1, 2),
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=_command_reroll_trigger_payload(
            roll_state,
            unit_instance_id="army-alpha:missing-unit",
        ),
    )

    status = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert state.stratagem_use_records == []


def test_command_reroll_is_not_blocked_by_same_phase_unit_targeting() -> None:
    unit_id = "army-alpha:intercessor-unit-1"
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_stratagem_use(
        StratagemUseRecord(
            use_id="phase14i-prior-unit-stratagem",
            player_id="player-a",
            stratagem_id="heroic-intervention-placeholder",
            source_id="source:heroic-intervention-placeholder",
            battle_round=state.battle_round,
            phase=BattlePhase.CHARGE,
            active_player_id=state.active_player_id,
            timing_window_id=None,
            request_id="phase14i-prior-unit-stratagem-request",
            result_id="phase14i-prior-unit-stratagem-result",
            selected_option_id="phase14i-prior-unit-stratagem-option",
            target_binding=StratagemTargetBinding(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_player_id="player-a",
                target_unit_instance_id=unit_id,
            ),
            targeted_unit_instance_ids=(unit_id,),
            affected_unit_instance_ids=(unit_id,),
            command_point_cost=0,
            command_point_transaction_id=None,
            handler_id="record_only",
        )
    )
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="charge_roll",
        quantity=2,
        values=(1, 2),
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=_command_reroll_trigger_payload(roll_state, unit_instance_id=unit_id),
    )
    status = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(state.stratagem_use_records) == 1
    assert state.command_point_total("player-a") == 1


def test_command_reroll_source_handler_can_resume_reaction_parent() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-b", amount=1)
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-b")
    trigger_payload = _command_reroll_trigger_payload(
        roll_state,
        unit_instance_id="army-beta:enemy-unit",
    )
    context = _context(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )
    options = stratagem_use_options(
        state=state,
        catalog_records=(_source_stratagem_record("command-reroll"),),
        context=context,
    )
    assert len(options) == 1
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window(state, eligible_player_id="player-b"),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="movement_reaction_step",
        resume_token="phase12c_resume_token",
        actor_id="player-b",
        decision_type=STRATAGEM_DECISION_TYPE,
        options=options,
        payload=validate_json_value(
            {
                "stratagem_context": validate_json_value(context.to_payload()),
                "finite": True,
            }
        ),
    )

    pending = _decision_request(lifecycle.advance_until_decision_or_terminal())
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-reactive-command-reroll",
            request=pending,
            selected_option_id=options[0].option_id,
        )
    )

    assert state.command_point_total("player-b") == 0
    assert len(lifecycle.reaction_queue.frames) == 0
    resumed = _last_event_payload(lifecycle.decision_controller, "reaction_parent_resumed")
    assert resumed["resume_token"] == "phase12c_resume_token"
    assert _has_event(lifecycle.decision_controller, "command_reroll_resolved")


def test_insane_bravery_target_proposal_spends_cp_and_auto_passes_battle_shock() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.FIXED,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_battle_shock(state)
    _grant_cp(state, player_id="player-a", amount=1)
    target_unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
        catalog_record=_source_stratagem_record("insane-bravery"),
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    submitted = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=target_unit_id,
        )
    )

    lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase12c-insane-bravery",
            proposal=submitted,
        )
    )

    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.stratagem_use_records[0].handler_id == "core:insane-bravery"
    assert (
        _last_event_payload(lifecycle.decision_controller, "stratagem_used")["handler_id"]
        == "core:insane-bravery"
    )
    assert _has_event(lifecycle.decision_controller, "insane_bravery_auto_pass_registered")
    auto_passed = _last_event_payload(lifecycle.decision_controller, "battle_shock_test_resolved")
    result_payload = cast(dict[str, JsonValue], auto_passed["battle_shock_result"])
    request_payload = cast(dict[str, JsonValue], result_payload["request"])
    assert request_payload["unit_instance_id"] == target_unit_id
    assert auto_passed["auto_passed"] is True
    assert target_unit_id not in state.battle_shocked_unit_ids


def test_parameterized_stratagem_decline_requires_engine_marked_optional_window() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.FIXED,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_battle_shock(state)
    _grant_cp(state, player_id="player-a", amount=1)
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
        catalog_record=_source_stratagem_record("insane-bravery"),
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)

    rejected = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-nondeclinable-insane-bravery",
            request_id=request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "decline_not_allowed"}
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []


def test_stratagem_decline_helpers_require_decline_results_and_marked_requests() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
        catalog_record=_source_stratagem_record("insane-bravery"),
    )
    declinable_payload = stratagem_target_proposal_request_payload(
        proposal_request,
        request_id="phase12c-declinable-proposal-request",
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.player_id,
        allow_decline=True,
    )
    assert isinstance(declinable_payload, dict)
    assert declinable_payload["declinable"] is True
    with pytest.raises(GameLifecycleError, match="decline allowance"):
        stratagem_target_proposal_request_payload(
            proposal_request,
            request_id="phase12c-declinable-proposal-request",
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=proposal_request.player_id,
            allow_decline=cast(bool, "yes"),
        )
    request = create_stratagem_target_proposal_decision_request(
        state=state,
        proposal_request=proposal_request,
        allow_decline=True,
    )
    decline_result = DecisionResult(
        result_id="phase12c-decline-helper",
        request_id=request.request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=stratagem_decline_payload(),
    )
    non_decline_result = DecisionResult(
        result_id="phase12c-nondecline-helper",
        request_id=request.request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value({"proposal": proposal_request.to_payload()}),
    )

    assert stratagem_window_decline_allowed(request=request, result=decline_result)
    assert not stratagem_window_decline_allowed(request=request, result=non_decline_result)
    event_payload = stratagem_window_decline_event_payload(
        request=request,
        result=decline_result,
    )
    assert isinstance(event_payload, dict)
    assert event_payload["trigger_kind"] == TimingTriggerKind.START_PHASE.value
    with pytest.raises(GameLifecycleError, match="decline result"):
        stratagem_window_decline_event_payload(request=request, result=non_decline_result)

    use_request = create_stratagem_use_decision_request(
        state=state,
        context=proposal_request.context,
        options=(stratagem_decline_option(),),
    )
    use_decline_result = DecisionResult(
        result_id="phase12c-use-decline-helper",
        request_id=use_request.request_id,
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id=use_request.actor_id,
        selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        payload=stratagem_decline_payload(),
    )

    assert is_stratagem_window_decline_result(use_decline_result)
    assert stratagem_window_decline_allowed(request=use_request, result=use_decline_result)
    assert stratagem_window_context_from_request(use_request) == proposal_request.context
    assert stratagem_window_context_from_request(request) == proposal_request.context

    with pytest.raises(GameLifecycleError, match="requires a DecisionResult"):
        is_stratagem_window_decline_result(cast(DecisionResult, object()))
    with pytest.raises(GameLifecycleError, match="requires a DecisionRequest"):
        stratagem_window_decline_allowed(
            request=cast(DecisionRequest, object()),
            result=use_decline_result,
        )
    with pytest.raises(GameLifecycleError, match="requires a DecisionRequest"):
        stratagem_window_context_from_request(cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        stratagem_window_context_from_request(
            DecisionRequest(
                request_id="phase12c-bad-use-context-payload",
                decision_type=STRATAGEM_DECISION_TYPE,
                actor_id="player-a",
                payload=None,
                options=(stratagem_decline_option(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="missing context"):
        stratagem_window_context_from_request(
            DecisionRequest(
                request_id="phase12c-missing-use-context",
                decision_type=STRATAGEM_DECISION_TYPE,
                actor_id="player-a",
                payload={},
                options=(stratagem_decline_option(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="payload is malformed"):
        stratagem_window_context_from_request(
            DecisionRequest(
                request_id="phase12c-malformed-use-context",
                decision_type=STRATAGEM_DECISION_TYPE,
                actor_id="player-a",
                payload={"stratagem_context": {}},
                options=(stratagem_decline_option(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="not a Stratagem window request"):
        stratagem_window_context_from_request(
            DecisionRequest(
                request_id="phase12c-non-stratagem-context",
                decision_type="not_stratagem",
                actor_id="player-a",
                payload={},
                options=(parameterized_decision_option(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="Stratagem use requires a DecisionController"):
        request_stratagem_use(
            state=state,
            decisions=cast(DecisionController, object()),
            catalog_records=(),
            context=proposal_request.context,
        )
    with pytest.raises(GameLifecycleError, match="Stratagem use requires a DecisionController"):
        request_stratagem_use_from_index(
            state=state,
            decisions=cast(DecisionController, object()),
            index=eleventh_edition_stratagem_index(),
            context=proposal_request.context,
        )


def test_command_phase_progression_offers_insane_bravery_from_index_before_battle_shock() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.FIXED,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_battle_shock(state)
    _grant_cp(state, player_id="player-a", amount=1)
    target_unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    proposal_request = _proposal_request_from_decision(request)
    assert proposal_request.stratagem_id == "insane-bravery"
    submitted = proposal_request.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=target_unit_id,
        )
    )

    lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase12c-progressed-insane-bravery",
            proposal=submitted,
        )
    )

    assert state.command_point_total("player-a") == 0
    assert state.stratagem_use_records[0].handler_id == "core:insane-bravery"
    auto_passed = _last_event_payload(lifecycle.decision_controller, "battle_shock_test_resolved")
    assert auto_passed["auto_passed"] is True
    assert target_unit_id not in state.battle_shocked_unit_ids


def test_command_phase_progression_declines_parameterized_stratagem_window() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.FIXED,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_battle_shock(state)
    _grant_cp(state, player_id="player-a", amount=1)
    _remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE

    declined = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-decline-insane-bravery",
            request_id=request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )

    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert _has_event(lifecycle.decision_controller, "stratagem_window_declined")
    declined_payload = _last_event_payload(
        lifecycle.decision_controller,
        "stratagem_window_declined",
    )
    assert declined_payload["timing_window_id"] == (
        "insane-bravery-battle-shock-round-1-player-player-a"
    )
    battle_shock = _last_event_payload(lifecycle.decision_controller, "battle_shock_test_resolved")
    assert battle_shock["auto_passed"] is False
    follow_up = _decision_request(declined)
    assert follow_up.decision_type == "select_movement_unit"


def test_new_orders_finite_source_handler_discards_and_draws_replacement_card() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.TACTICAL,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_tactical_secondary(state)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id="phase12c-initial-tactical-draw-request",
            result_id="phase12c-initial-tactical-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    initial_cards = state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id="phase12c-initial-tactical-draw",
    )
    target_card_id = initial_cards[0].secondary_mission_id

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(_source_stratagem_record("new-orders"),),
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )
    request = _decision_request(waiting)
    selected_option = next(
        option
        for option in request.options
        if option.option_id.endswith(f"target:{target_card_id}")
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-new-orders",
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )

    active_card_ids = {
        card.secondary_mission_id
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.status.value == "active"
    }
    discarded_matches = [
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.secondary_mission_id == target_card_id
    ]
    assert len(discarded_matches) == 1
    assert discarded_matches[0].status.value == "discarded"
    assert state.command_point_total("player-a") == 0
    assert target_card_id not in active_card_ids
    assert len(active_card_ids) == state.tactical_secondary_draw_count
    assert (
        _last_event_payload(lifecycle.decision_controller, "new_orders_resolved")[
            "discarded_secondary_mission_id"
        ]
        == target_card_id
    )


def test_phase14i_new_orders_rejects_second_use_in_same_game_before_cp_spend() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.TACTICAL,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    record = _source_stratagem_record("new-orders")
    state.record_stratagem_use(
        StratagemUseRecord(
            use_id="phase14i-previous-new-orders-use",
            player_id="player-a",
            stratagem_id=record.definition.stratagem_id,
            source_id=record.definition.source_id,
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id=state.active_player_id,
            timing_window_id=None,
            request_id="phase14i-previous-new-orders-request",
            result_id="phase14i-previous-new-orders-result",
            selected_option_id="phase14i-previous-new-orders-option",
            target_binding=StratagemTargetBinding(
                target_kind=StratagemTargetKind.TACTICAL_SECONDARY_CARD,
                target_player_id="player-a",
                target_secondary_mission_id="phase14i-prior-secondary-card",
            ),
            targeted_unit_instance_ids=(),
            affected_unit_instance_ids=(),
            command_point_cost=1,
            command_point_transaction_id="phase14i-previous-new-orders-cp",
            handler_id=record.definition.handler_id,
        )
    )
    state.battle_round = 2
    _set_command_step_ready_for_tactical_secondary(state)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id="phase14i-second-new-orders-draw-request",
            result_id="phase14i-second-new-orders-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    active_cards = state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id="phase14i-second-new-orders-draw",
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            _handcrafted_stratagem_option(
                record=record,
                context=context,
                binding=StratagemTargetBinding(
                    target_kind=StratagemTargetKind.TACTICAL_SECONDARY_CARD,
                    target_player_id="player-a",
                    target_secondary_mission_id=active_cards[1].secondary_mission_id,
                ),
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14i-new-orders-second-use",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "once_per_battle"}
    assert state.command_point_total("player-a") == 1
    assert len(state.stratagem_use_records) == 1
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_command_phase_progression_offers_new_orders_from_index() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.TACTICAL,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_tactical_secondary(state)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id="phase12c-progressed-new-orders-draw-request",
            result_id="phase12c-progressed-new-orders-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    initial_cards = state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id="phase12c-progressed-new-orders-draw",
    )
    target_card_id = initial_cards[0].secondary_mission_id

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    selected_option = next(
        option
        for option in request.options
        if option.option_id.endswith(f"target:{target_card_id}")
    )

    assert request.decision_type == STRATAGEM_DECISION_TYPE
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-progressed-new-orders",
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )

    assert state.command_point_total("player-a") == 0
    assert state.stratagem_use_records[0].handler_id == "core:new-orders"
    assert (
        _last_event_payload(lifecycle.decision_controller, "new_orders_resolved")[
            "discarded_secondary_mission_id"
        ]
        == target_card_id
    )


def test_command_phase_progression_declines_finite_stratagem_window() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.TACTICAL,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_tactical_secondary(state)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id="phase12c-decline-new-orders-draw-request",
            result_id="phase12c-decline-new-orders-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id="phase12c-decline-new-orders-draw",
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert request.decision_type == STRATAGEM_DECISION_TYPE
    assert request.option_by_id(DECLINE_STRATAGEM_WINDOW_OPTION_ID).option_id == (
        DECLINE_STRATAGEM_WINDOW_OPTION_ID
    )

    declined = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-decline-new-orders",
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )

    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert _has_event(lifecycle.decision_controller, "stratagem_window_declined")
    declined_payload = _last_event_payload(
        lifecycle.decision_controller,
        "stratagem_window_declined",
    )
    assert declined_payload["timing_window_id"] == ("new-orders-command-round-1-player-player-a")
    follow_up = _decision_request(declined)
    assert follow_up.decision_type == "select_movement_unit"


def test_command_phase_declining_new_orders_does_not_suppress_insane_bravery() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.TACTICAL,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_tactical_secondary(state)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id="phase12c-combined-window-draw-request",
            result_id="phase12c-combined-window-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id="phase12c-combined-window-draw",
    )
    target_unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)

    new_orders_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    new_orders_payload = cast(dict[str, JsonValue], new_orders_request.payload)
    new_orders_context_payload = cast(
        dict[str, JsonValue],
        new_orders_payload["stratagem_context"],
    )

    assert new_orders_request.decision_type == STRATAGEM_DECISION_TYPE
    assert new_orders_context_payload["timing_window_id"] == (
        "new-orders-command-round-1-player-player-a"
    )

    insane_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-decline-new-orders-before-insane-bravery",
            request=new_orders_request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )
    insane_request = _decision_request(insane_status)
    insane_payload = cast(dict[str, JsonValue], insane_request.payload)
    insane_proposal_request = _proposal_request_from_decision(insane_request)

    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert not _has_event(lifecycle.decision_controller, "new_orders_resolved")
    assert insane_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    assert insane_payload["declinable"] is True
    assert insane_proposal_request.stratagem_id == "insane-bravery"
    assert insane_proposal_request.context.timing_window_id == (
        "insane-bravery-battle-shock-round-1-player-player-a"
    )

    lifecycle.submit_decision(
        _target_proposal_result(
            request=insane_request,
            result_id="phase12c-accept-insane-after-new-orders-decline",
            proposal=insane_proposal_request.with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-a",
                    target_unit_instance_id=target_unit_id,
                )
            ),
        )
    )

    assert state.command_point_total("player-a") == 0
    assert [record.handler_id for record in state.stratagem_use_records] == ["core:insane-bravery"]
    battle_shock = _last_event_payload(lifecycle.decision_controller, "battle_shock_test_resolved")
    assert battle_shock["auto_passed"] is True
    assert target_unit_id not in state.battle_shocked_unit_ids


def test_tactical_secondary_target_binding_requires_card_fields() -> None:
    with pytest.raises(
        ValueError,
        match=r"Tactical secondary StratagemTargetBinding requires target card fields\.",
    ):
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.TACTICAL_SECONDARY_CARD,
            target_player_id="player-a",
        )


def test_stratagem_use_record_validates_phase_scoped_target_fields() -> None:
    record = StratagemUseRecord(
        use_id="use-a",
        player_id="player-a",
        stratagem_id="command-reroll",
        source_id="source-a",
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
        timing_window_id=None,
        request_id="request-a",
        result_id="result-a",
        selected_option_id="option-a",
        target_binding=StratagemTargetBinding.none(),
        targeted_unit_instance_ids=("unit-b", "unit-a"),
        affected_unit_instance_ids=("unit-b", "unit-a"),
        command_point_cost=0,
        command_point_transaction_id=None,
        handler_id="core:command-reroll",
        effect_selection={"mode": "test"},
        effect_payload={"effect": "payload"},
    )

    payload = record.to_payload()
    restored = StratagemUseRecord.from_payload(payload)

    assert restored.active_player_id == "player-b"
    assert restored.targeted_unit_instance_ids == ("unit-a", "unit-b")
    assert restored.affected_unit_instance_ids == ("unit-a", "unit-b")
    assert restored.effect_selection == {"mode": "test"}

    with pytest.raises(GameLifecycleError, match="target_binding"):
        replace(record, target_binding=cast(StratagemTargetBinding, object()))
    with pytest.raises(GameLifecycleError, match="active_player_id"):
        replace(record, active_player_id=cast(str | None, 1))
    with pytest.raises(GameLifecycleError, match="must be unique"):
        replace(record, affected_unit_instance_ids=("unit-a", "unit-a"))
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        replace(record, targeted_unit_instance_ids=cast(tuple[str, ...], ["unit-a"]))
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        replace(record, command_point_cost=-1)


def test_stratagem_target_proposal_round_trips_effect_selection() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
    )
    catalog_record = _source_stratagem_record("crushing-impact")
    proposal = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=catalog_record,
    )
    binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id="army-alpha:tank-unit",
    )

    assert proposal.game_id == state.game_id
    assert proposal.player_id == "player-a"
    assert proposal.battle_round == state.battle_round
    assert proposal.phase is state.current_battle_phase
    assert proposal.stratagem_id == "crushing-impact"
    assert proposal.target_spec == catalog_record.definition.target_spec

    bound = proposal.with_binding(
        binding,
        effect_selection={
            CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY: "army-beta:enemy-unit",
            CRUSHING_IMPACT_MODEL_CONTEXT_KEY: "army-alpha:tank-model-1",
        },
    )
    updated = bound.with_effect_selection(
        {
            CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY: "army-beta:enemy-unit-2",
            CRUSHING_IMPACT_MODEL_CONTEXT_KEY: "army-alpha:tank-model-2",
        }
    )
    restored = StratagemTargetProposal.from_payload(updated.to_payload())

    assert restored.target_binding == binding
    assert restored.effect_selection == {
        CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY: "army-beta:enemy-unit-2",
        CRUSHING_IMPACT_MODEL_CONTEXT_KEY: "army-alpha:tank-model-2",
    }


def test_stratagem_framework_token_parsers_are_strict() -> None:
    assert (
        stratagem_availability_kind_from_token(StratagemAvailabilityKind.CORE)
        is StratagemAvailabilityKind.CORE
    )
    assert stratagem_availability_kind_from_token("core") is StratagemAvailabilityKind.CORE
    with pytest.raises(GameLifecycleError, match="must be a string"):
        stratagem_availability_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported StratagemAvailabilityKind"):
        stratagem_availability_kind_from_token("unknown")

    assert (
        stratagem_category_from_token(StratagemCategory.BATTLE_TACTIC)
        is StratagemCategory.BATTLE_TACTIC
    )
    assert stratagem_category_from_token("battle_tactic") is StratagemCategory.BATTLE_TACTIC
    with pytest.raises(GameLifecycleError, match="must be a string"):
        stratagem_category_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported StratagemCategory"):
        stratagem_category_from_token("unknown")

    assert stratagem_target_kind_from_token(StratagemTargetKind.FRIENDLY_UNIT) is (
        StratagemTargetKind.FRIENDLY_UNIT
    )
    assert stratagem_target_kind_from_token("friendly_unit") is StratagemTargetKind.FRIENDLY_UNIT
    with pytest.raises(GameLifecycleError, match="must be a string"):
        stratagem_target_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported StratagemTargetKind"):
        stratagem_target_kind_from_token("unknown")


def test_phase15e_core_stratagem_descriptors_are_supported_and_window_scoped() -> None:
    phase15e_records = tuple(
        _source_stratagem_record(stratagem_id)
        for stratagem_id in (
            "counteroffensive",
            "crushing-impact",
            "epic-challenge",
            "heroic-intervention",
        )
    )
    assert {
        record.definition.stratagem_id: (
            record.definition.handler_id,
            record.definition.target_spec.target_policy_id,
        )
        for record in phase15e_records
    } == {
        "counteroffensive": ("core:counteroffensive", "counteroffensive_unit"),
        "crushing-impact": ("core:crushing-impact", "crushing_impact_unit"),
        "epic-challenge": ("core:epic-challenge", "epic_challenge_unit"),
        "heroic-intervention": ("core:heroic-intervention", "heroic_intervention_unit"),
    }
    assert all(record.availability_kind.value == "core" for record in phase15e_records)

    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
    )
    assert (
        stratagem_use_options(
            state=state,
            catalog_records=phase15e_records,
            context=context,
        )
        == ()
    )
    for record in phase15e_records:
        proposal_request = StratagemTargetProposal.for_request(
            context=context,
            catalog_record=record,
        )
        unavailable = request_stratagem_target_proposal(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=proposal_request,
        )
        assert unavailable.status_kind is LifecycleStatusKind.UNSUPPORTED
        payload = cast(dict[str, JsonValue], unavailable.payload)
        assert payload["player_id"] == "player-a"
        assert payload["stratagem_id"] == record.definition.stratagem_id
        assert payload["unavailable_reason"] != "unsupported_handler"
    assert len(lifecycle.decision_controller.queue.pending_requests) == 0


def test_phase15e_heroic_intervention_into_the_fray_spends_additional_cp() -> None:
    insufficient_lifecycle = _battle_lifecycle()
    insufficient_state = _state(insufficient_lifecycle)
    _set_current_battle_phase(insufficient_state, BattlePhase.CHARGE)
    insufficient_state.active_player_id = "player-b"
    _replace_unit_poses(
        insufficient_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(x=index * 2.0, y=0.0) for index in range(5)),
    )
    _replace_unit_poses(
        insufficient_state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=5.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _grant_cp(insufficient_state, player_id="player-a", amount=1)
    rejected = _submit_source_stratagem_target(
        insufficient_lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-insufficient-into-the-fray",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "insufficient_command_points"}
    assert insufficient_state.command_point_total("player-a") == 1
    assert insufficient_state.stratagem_use_records == []

    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(x=index * 2.0, y=0.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=5.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _grant_cp(state, player_id="player-a", amount=2)
    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-into-the-fray",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )
    request = _decision_request(status)
    request_payload = cast(dict[str, JsonValue], request.payload)
    proposal_payload = cast(dict[str, JsonValue], request_payload["proposal_request"])
    context_payload = cast(dict[str, JsonValue], proposal_payload["context"])

    assert request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert state.command_point_total("player-a") == 0
    assert state.stratagem_use_records[0].command_point_cost == 2
    assert state.stratagem_use_records[0].effect_selection == {
        HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
    }
    assert context_payload["mode"] == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
    maximum_distance = context_payload["maximum_distance_inches"]
    assert type(maximum_distance) is int
    assert maximum_distance <= 6


def test_phase15e_heroic_intervention_charge_move_applies_witness_and_fights_first() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    heroic_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:enemy-unit"
    _replace_unit_poses(
        state,
        unit_instance_id=heroic_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _clear_terrain(state)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    _grant_cp(state, player_id="player-a", amount=2)
    waiting = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id=heroic_unit_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-into-the-fray-charge",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )
    request = _decision_request(waiting)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    witness = _path_witness_for_unit_delta(
        state,
        unit_instance_id=heroic_unit_id,
        dy=2.0,
    )

    status = _submit_heroic_charge_move_proposal(
        lifecycle,
        request=request,
        result_id="phase15e-heroic-charge-move",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(enemy_unit_id,),
            witness=witness,
        ),
    )
    completed = _last_event_payload(
        lifecycle.decision_controller,
        "heroic_intervention_charge_move_completed",
    )
    transition_batch = cast(dict[str, JsonValue], completed["transition_batch"])
    displacements = cast(list[dict[str, JsonValue]], transition_batch["displacements"])
    persisting_effect = cast(dict[str, JsonValue], completed["persisting_effect"])
    effect_payload = cast(dict[str, JsonValue], persisting_effect["effect_payload"])

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() != before_battlefield
    assert len(displacements) == 5
    assert {cast(str, record["displacement_kind"]) for record in displacements} == {"charge_move"}
    assert effect_payload["effect_kind"] == "charge_grants_fights_first"
    assert effect_payload["stratagem_use_id"] == state.stratagem_use_records[0].use_id
    assert state.persisting_effects_for_unit(heroic_unit_id)


def test_phase15e_heroic_intervention_charge_move_rejects_missing_witness() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    heroic_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:enemy-unit"
    _replace_unit_poses(
        state,
        unit_instance_id=heroic_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=2)
    waiting = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id=heroic_unit_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-into-the-fray-missing-witness",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )
    request = _decision_request(waiting)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)

    status = _submit_heroic_charge_move_proposal(
        lifecycle,
        request=request,
        result_id="phase15e-heroic-charge-missing-witness",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(enemy_unit_id,),
            witness=None,
        ),
    )
    payload = cast(dict[str, JsonValue], status.payload)
    validation = cast(dict[str, JsonValue], payload["proposal_validation"])
    violations = cast(list[dict[str, JsonValue]], validation["violations"])

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert violations[0]["violation_code"] == "charge_move_witness_required"
    assert not _has_event(
        lifecycle.decision_controller,
        "heroic_intervention_charge_move_completed",
    )


def test_phase15e_heroic_intervention_charge_no_move_records_decline() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    heroic_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:enemy-unit"
    _replace_unit_poses(
        state,
        unit_instance_id=heroic_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _clear_terrain(state)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    _grant_cp(state, player_id="player-a", amount=2)
    waiting = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id=heroic_unit_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-into-the-fray-no-move",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )
    request = _decision_request(waiting)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)

    status = _submit_heroic_charge_move_proposal(
        lifecycle,
        request=request,
        result_id="phase15e-heroic-charge-no-move",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(),
            witness=None,
        ),
    )
    declined = _last_event_payload(
        lifecycle.decision_controller,
        "heroic_intervention_charge_move_declined",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert declined["proposal_request_id"] == proposal_request.request_id
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.persisting_effects_for_unit(heroic_unit_id) == ()


def test_phase15e_heroic_intervention_charge_rejects_endpoint_only_witness() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    heroic_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:enemy-unit"
    _replace_unit_poses(
        state,
        unit_instance_id=heroic_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _clear_terrain(state)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    _grant_cp(state, player_id="player-a", amount=2)
    waiting = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id=heroic_unit_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-into-the-fray-endpoint-only",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )
    request = _decision_request(waiting)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    witness = _path_witness_for_unit_delta(
        state,
        unit_instance_id=heroic_unit_id,
        dy=2.0,
        endpoint_only=True,
    )

    status = _submit_heroic_charge_move_proposal(
        lifecycle,
        request=request,
        result_id="phase15e-heroic-charge-endpoint-only",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(enemy_unit_id,),
            witness=witness,
        ),
    )
    invalid = _last_event_payload(
        lifecycle.decision_controller,
        "heroic_intervention_charge_move_invalid",
    )

    assert isinstance(status.payload, dict)
    status_payload = status.payload
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status_payload["violation_code"] == "endpoint_only_path"
    retry_request_id = status_payload["next_request_id"]
    assert type(retry_request_id) is str
    retry_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    retry_proposal_request = MovementProposalRequest.from_decision_request_payload(
        retry_request.payload
    )
    assert retry_request.request_id == retry_request_id
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert is_heroic_intervention_charge_move_request(retry_request)
    assert retry_proposal_request.context == proposal_request.context
    assert invalid["violation_code"] == "endpoint_only_path"
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.persisting_effects_for_unit(heroic_unit_id) == ()


def test_phase15e_heroic_intervention_reaction_invalid_charge_continues_to_retry() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    heroic_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:enemy-unit"
    _replace_unit_poses(
        state,
        unit_instance_id=heroic_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _clear_terrain(state)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    _grant_cp(state, player_id="player-a", amount=2)
    target_proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("heroic-intervention"),
    )
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window_for_trigger(
            state,
            eligible_player_id="player-a",
            trigger_kind=TimingTriggerKind.END_PHASE,
            source_rule_id="phase15e-heroic-retry-reaction",
            window_id="phase15e-heroic-retry-window",
            phase=BattlePhase.CHARGE,
        ),
        parent_phase=BattlePhase.CHARGE,
        parent_step="end_charge_phase_reactions",
        resume_token="phase15e_heroic_retry_resume_token",
        actor_id="player-a",
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        options=(parameterized_decision_option(),),
        payload=validate_json_value(
            {"proposal_request": validate_json_value(target_proposal_request.to_payload())}
        ),
    )
    target_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    target_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=target_request,
            result_id="phase15e-heroic-reaction-target",
            proposal=_proposal_request_from_decision(target_request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-a",
                    target_unit_instance_id=heroic_unit_id,
                ),
                effect_selection={
                    HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
                },
            ),
        )
    )
    movement_request = _decision_request(target_status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        movement_request.payload
    )
    witness = _path_witness_for_unit_delta(
        state,
        unit_instance_id=heroic_unit_id,
        dy=2.0,
        endpoint_only=True,
    )

    status = _submit_heroic_charge_move_proposal(
        lifecycle,
        request=movement_request,
        result_id="phase15e-heroic-reaction-invalid-charge",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(enemy_unit_id,),
            witness=witness,
        ),
    )
    retry_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["next_request_id"] == retry_request.request_id
    assert is_heroic_intervention_charge_move_request(retry_request)
    assert len(lifecycle.reaction_queue.frames) == 1
    assert lifecycle.reaction_queue.frames[0].request_id == retry_request.request_id
    assert not _has_event(lifecycle.decision_controller, "reaction_parent_resumed")
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.persisting_effects_for_unit(heroic_unit_id) == ()


def test_phase15e_heroic_intervention_charge_prevalidation_rejects_malformed_and_drift() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-b"
    heroic_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:enemy-unit"
    _replace_unit_poses(
        state,
        unit_instance_id=heroic_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=2)
    waiting = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id=heroic_unit_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-into-the-fray-prevalidation",
        effect_selection={
            HEROIC_INTERVENTION_MODE_CONTEXT_KEY: HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
        },
    )
    request = _decision_request(waiting)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)

    bad_option = invalid_heroic_intervention_charge_move_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase15e-heroic-bad-option",
            request_id=request.request_id,
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id="bad-option",
            payload=None,
        ),
    )
    bad_payload = invalid_heroic_intervention_charge_move_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase15e-heroic-bad-payload",
            request_id=request.request_id,
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=None,
        ),
    )
    _replace_unit_poses(
        state,
        unit_instance_id=enemy_unit_id,
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=50.0) for index in range(5)),
    )
    stale_reachable = invalid_heroic_intervention_charge_move_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase15e-heroic-stale-reachable",
            request_id=request.request_id,
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                ChargeMoveProposal(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=proposal_request.proposal_kind,
                    unit_instance_id=proposal_request.unit_instance_id,
                    movement_phase_action="charge_move",
                    movement_mode=MovementMode.CHARGE,
                    charge_target_unit_instance_ids=(),
                    witness=None,
                ).to_payload()
            ),
        ),
    )

    assert bad_option is not None
    assert bad_option.payload == {"invalid_reason": "malformed"}
    assert bad_payload is not None
    assert bad_payload.payload == {"invalid_reason": "malformed"}
    assert stale_reachable is not None
    assert stale_reachable.payload == {
        "invalid_reason": "heroic_intervention_reachable_targets_drift"
    }


def test_phase15e_core_stratagem_effect_selection_rejects_malformed_payloads() -> None:
    heroic_lifecycle = _battle_lifecycle()
    heroic_state = _state(heroic_lifecycle)
    _set_current_battle_phase(heroic_state, BattlePhase.CHARGE)
    heroic_state.active_player_id = "player-b"
    _grant_cp(heroic_state, player_id="player-a", amount=2)
    heroic_status = _submit_source_stratagem_target(
        heroic_lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-unknown-mode",
        effect_selection={HEROIC_INTERVENTION_MODE_CONTEXT_KEY: "unsupported-mode"},
    )

    crushing_lifecycle = _battle_lifecycle()
    crushing_state = _state(crushing_lifecycle)
    _set_current_battle_phase(crushing_state, BattlePhase.CHARGE)
    crushing_state.active_player_id = "player-a"
    _grant_cp(crushing_state, player_id="player-a", amount=1)
    crushing_status = _submit_source_stratagem_target(
        crushing_lifecycle,
        stratagem_id="crushing-impact",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        result_id="phase15e-crushing-missing-model",
        effect_selection={CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY: "army-beta:enemy-unit"},
    )

    epic_lifecycle = _battle_lifecycle()
    epic_state = _state(epic_lifecycle)
    _set_current_battle_phase(epic_state, BattlePhase.FIGHT)
    epic_state.active_player_id = "player-a"
    _grant_cp(epic_state, player_id="player-a", amount=1)
    epic_status = _submit_source_stratagem_target(
        epic_lifecycle,
        stratagem_id="epic-challenge",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        result_id="phase15e-epic-malformed-effect-selection",
        trigger_payload={"selected_unit_instance_id": "army-alpha:intercessor-unit-1"},
        effect_selection="bad-effect-selection",
    )

    assert heroic_status.status_kind is LifecycleStatusKind.INVALID
    assert heroic_status.payload == {"invalid_reason": "heroic_intervention_mode_unknown"}
    assert heroic_state.command_point_total("player-a") == 2
    assert crushing_status.status_kind is LifecycleStatusKind.INVALID
    assert crushing_status.payload == {"invalid_reason": "model_instance_id_required"}
    assert crushing_state.command_point_total("player-a") == 1
    assert epic_status.status_kind is LifecycleStatusKind.INVALID
    assert epic_status.payload == {"invalid_reason": "effect_selection_malformed"}
    assert epic_state.command_point_total("player-a") == 1


def test_phase15e_core_stratagem_target_policies_reject_invalid_official_contexts() -> None:
    heroic_vehicle_lifecycle = _battle_lifecycle()
    heroic_vehicle_state = _state(heroic_vehicle_lifecycle)
    _set_current_battle_phase(heroic_vehicle_state, BattlePhase.CHARGE)
    heroic_vehicle_state.active_player_id = "player-b"
    _replace_unit_keywords(
        heroic_vehicle_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Vehicle",),
    )
    _replace_unit_poses(
        heroic_vehicle_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        heroic_vehicle_state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=24.0) for index in range(5)),
    )
    _grant_cp(heroic_vehicle_state, player_id="player-a", amount=1)
    heroic_vehicle = _submit_source_stratagem_target(
        heroic_vehicle_lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-vehicle",
    )

    heroic_range_lifecycle = _battle_lifecycle()
    heroic_range_state = _state(heroic_range_lifecycle)
    _set_current_battle_phase(heroic_range_state, BattlePhase.CHARGE)
    heroic_range_state.active_player_id = "player-b"
    _replace_unit_poses(
        heroic_range_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=20.0) for index in range(5)),
    )
    _replace_unit_poses(
        heroic_range_state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + (index * 2.0), y=50.0) for index in range(5)),
    )
    _grant_cp(heroic_range_state, player_id="player-a", amount=1)
    heroic_range = _submit_source_stratagem_target(
        heroic_range_lifecycle,
        stratagem_id="heroic-intervention",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.END_PHASE,
        result_id="phase15e-heroic-range",
    )

    crushing_missing_lifecycle = _battle_lifecycle()
    crushing_missing_state = _state(crushing_missing_lifecycle)
    _set_current_battle_phase(crushing_missing_state, BattlePhase.CHARGE)
    crushing_missing_state.active_player_id = "player-a"
    _replace_unit_keywords(
        crushing_missing_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Monster",),
    )
    _grant_cp(crushing_missing_state, player_id="player-a", amount=1)
    crushing_missing = _submit_source_stratagem_target(
        crushing_missing_lifecycle,
        stratagem_id="crushing-impact",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        result_id="phase15e-crushing-missing-enemy",
    )

    crushing_model_lifecycle = _battle_lifecycle()
    crushing_model_state = _state(crushing_model_lifecycle)
    _set_current_battle_phase(crushing_model_state, BattlePhase.CHARGE)
    crushing_model_state.active_player_id = "player-a"
    _replace_unit_keywords(
        crushing_model_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Vehicle",),
    )
    _grant_cp(crushing_model_state, player_id="player-a", amount=1)
    crushing_model = _submit_source_stratagem_target(
        crushing_model_lifecycle,
        stratagem_id="crushing-impact",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        result_id="phase15e-crushing-model-not-in-unit",
        effect_selection={
            CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY: "army-beta:enemy-unit",
            CRUSHING_IMPACT_MODEL_CONTEXT_KEY: _first_model_id(
                crushing_model_state,
                unit_instance_id="army-beta:enemy-unit",
            ),
        },
    )

    epic_selected_lifecycle = _battle_lifecycle()
    epic_selected_state = _state(epic_selected_lifecycle)
    _set_current_battle_phase(epic_selected_state, BattlePhase.FIGHT)
    epic_selected_state.active_player_id = "player-a"
    _replace_unit_keywords(
        epic_selected_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Character",),
    )
    _grant_cp(epic_selected_state, player_id="player-a", amount=1)
    epic_selected = _submit_source_stratagem_target(
        epic_selected_lifecycle,
        stratagem_id="epic-challenge",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        result_id="phase15e-epic-wrong-selected-unit",
        trigger_payload={"selected_unit_instance_id": "army-beta:enemy-unit"},
        effect_selection={
            EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY: _first_model_id(
                epic_selected_state,
                unit_instance_id="army-alpha:intercessor-unit-1",
            )
        },
    )

    epic_character_lifecycle = _battle_lifecycle()
    epic_character_state = _state(epic_character_lifecycle)
    _set_current_battle_phase(epic_character_state, BattlePhase.FIGHT)
    epic_character_state.active_player_id = "player-a"
    _grant_cp(epic_character_state, player_id="player-a", amount=1)
    epic_character = _submit_source_stratagem_target(
        epic_character_lifecycle,
        stratagem_id="epic-challenge",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        result_id="phase15e-epic-not-character",
        trigger_payload={"selected_unit_instance_id": "army-alpha:intercessor-unit-1"},
        effect_selection={
            EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY: _first_model_id(
                epic_character_state,
                unit_instance_id="army-alpha:intercessor-unit-1",
            )
        },
    )

    counteroffensive_lifecycle = _battle_lifecycle()
    counteroffensive_state = _state(counteroffensive_lifecycle)
    _set_current_battle_phase(counteroffensive_state, BattlePhase.FIGHT)
    counteroffensive_state.active_player_id = "player-a"
    _grant_cp(counteroffensive_state, player_id="player-b", amount=2)
    counteroffensive = _submit_source_stratagem_target(
        counteroffensive_lifecycle,
        stratagem_id="counteroffensive",
        player_id="player-b",
        target_unit_id="army-beta:enemy-unit",
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
        result_id="phase15e-counteroffensive-no-fight-state",
        trigger_payload={
            "fought_unit_instance_id": "army-alpha:intercessor-unit-1",
            "eligible_unit_instance_ids": ["army-beta:enemy-unit"],
        },
    )

    assert heroic_vehicle.payload == {
        "invalid_reason": "heroic_intervention_vehicle_not_character_or_walker"
    }
    assert heroic_range.payload == {"invalid_reason": "heroic_intervention_unit_not_within_12"}
    assert crushing_missing.payload == {"invalid_reason": "missing_crushing_impact_enemy_target"}
    assert crushing_model.payload == {"invalid_reason": "crushing_impact_model_not_in_unit"}
    assert epic_selected.payload == {"invalid_reason": "epic_challenge_unit_not_selected_to_fight"}
    assert epic_character.payload == {"invalid_reason": "epic_challenge_unit_not_character"}
    assert counteroffensive.payload == {
        "invalid_reason": "counteroffensive_requires_fight_phase_state"
    }


def test_phase15e_counteroffensive_selects_next_fight_activation() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    state.active_player_id = "player-a"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(x=index * 2.0, y=0.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=2.0 + index * 2.0, y=0.0) for index in range(5)),
    )
    policy = RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="phase15e-counteroffensive-test"
    ).fight_policy
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(
            "army-alpha:intercessor-unit-1",
            "army-beta:enemy-unit",
        ),
        fights_first_registry=FightsFirstRegistry(),
    ).with_next_band()
    _grant_cp(state, player_id="player-b", amount=2)
    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="counteroffensive",
        player_id="player-b",
        target_unit_id="army-beta:enemy-unit",
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
        result_id="phase15e-counteroffensive",
        trigger_payload={
            "fought_unit_instance_id": "army-alpha:intercessor-unit-1",
            "eligible_unit_instance_ids": ["army-beta:enemy-unit"],
        },
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("player-b") == 0
    assert state.fight_phase_state is not None
    activation = state.fight_phase_state.fight_order_state.activation_selections[-1]
    assert activation.unit_instance_id == "army-beta:enemy-unit"
    assert activation.interrupt_id is not None
    assert activation.interrupt_id.startswith("counteroffensive:")
    effect_payload = cast(dict[str, JsonValue], state.persisting_effects[-1].effect_payload)
    assert effect_payload["effect_kind"] == "fights_first"
    assert _last_event_payload(
        lifecycle.decision_controller,
        "counteroffensive_activation_selected",
    )


def test_phase15e_crushing_impact_uses_selected_enemy_and_model() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Vehicle", "Monster"),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(x=index * 4.0, y=0.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=2.0 + index * 4.0, y=0.0) for index in range(5)),
    )
    source_model_id = _first_model_id(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    _grant_cp(state, player_id="player-a", amount=1)
    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="crushing-impact",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        result_id="phase15e-crushing-impact",
        effect_selection={
            CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY: "army-beta:enemy-unit",
            CRUSHING_IMPACT_MODEL_CONTEXT_KEY: source_model_id,
        },
    )
    event = _last_event_payload(lifecycle.decision_controller, "crushing_impact_resolved")

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("player-a") == 0
    assert state.stratagem_use_records[0].targeted_unit_instance_ids == (
        "army-alpha:intercessor-unit-1",
    )
    assert state.stratagem_use_records[0].affected_unit_instance_ids == (
        "army-alpha:intercessor-unit-1",
        "army-beta:enemy-unit",
    )
    assert event["source_model_instance_id"] == source_model_id
    assert event["target_unit_instance_id"] == "army-beta:enemy-unit"
    assert 0 <= cast(int, event["enemy_mortal_wounds"]) <= 6


def test_phase15e_epic_challenge_registers_selected_character_model_precision() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Character", "Infantry"),
    )
    character_model_id = _first_model_id(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    _grant_cp(state, player_id="player-a", amount=1)
    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="epic-challenge",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        result_id="phase15e-epic-challenge",
        trigger_payload={"selected_unit_instance_id": "army-alpha:intercessor-unit-1"},
        effect_selection={EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY: character_model_id},
    )
    event = _last_event_payload(
        lifecycle.decision_controller,
        "epic_challenge_precision_registered",
    )
    persisted = cast(dict[str, JsonValue], event["persisting_effect"])
    effect_payload = cast(dict[str, JsonValue], persisted["effect_payload"])

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.stratagem_use_records[0].command_point_cost == 1
    assert effect_payload["effect_kind"] == "epic_challenge_precision"
    assert effect_payload["model_instance_id"] == character_model_id
    assert effect_payload["weapon_keyword"] == "Precision"


def test_phase13d_fire_overwatch_requests_out_of_phase_shooting_declaration() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=1)
    record = _source_stratagem_record("fire-overwatch")
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.END_PHASE,
        trigger_payload=_fire_overwatch_trigger_payload(),
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )

    unavailable = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(unavailable)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    shooting_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-supported",
            proposal=proposal,
        )
    )
    shooting_request = _decision_request(shooting_status)

    assert record.definition.handler_id == "core:fire-overwatch"
    assert record.definition.target_spec.target_policy_id == "out_of_phase_shooting_unit"
    assert shooting_request.decision_type == "submit_shooting_declaration"
    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.player_id == "player-a"
    assert (
        state.out_of_phase_shooting_state.selected_unit_instance_id
        == "army-alpha:intercessor-unit-1"
    )
    assert state.out_of_phase_shooting_state.parent_phase is BattlePhase.MOVEMENT
    assert _has_event(lifecycle.decision_controller, "fire_overwatch_shooting_requested")
    assert not _has_event(lifecycle.decision_controller, "persisting_effect_recorded")
    request_payload = cast(dict[str, object], shooting_request.payload)
    proposal_payload = cast(dict[str, object], request_payload["proposal_request"])
    target_candidates = cast(list[dict[str, object]], proposal_payload["target_candidates"])
    assert {
        tuple(cast(list[str], candidate["shooting_types"])) for candidate in target_candidates
    } == {(ShootingType.SNAP.value,)}

    declaration = _shooting_declaration_from_request(
        request=shooting_request,
        target_unit_id="army-beta:enemy-unit",
    )
    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13d-fire-overwatch-declaration",
            request_id=shooting_request.request_id,
            decision_type=shooting_request.decision_type,
            actor_id=shooting_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(declaration.to_payload()),
        )
    )
    for index in range(12):
        if _state(lifecycle).out_of_phase_shooting_state is None:
            break
        request = _decision_request(status)
        assert request.decision_type in {
            SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
            "select_feel_no_pain",
            "select_precision_allocation",
        }
        option = request.options[0]
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase13d-fire-overwatch-attack-{index}",
                request=request,
                selected_option_id=option.option_id,
            )
        )

    assert _state(lifecycle).out_of_phase_shooting_state is None
    assert _has_event(lifecycle.decision_controller, "out_of_phase_shooting_declaration_accepted")
    assert _has_event(lifecycle.decision_controller, "out_of_phase_shooting_completed")
    accepted = _last_event_payload(
        lifecycle.decision_controller,
        "out_of_phase_shooting_declaration_accepted",
    )
    attack_pools = cast(list[dict[str, object]], accepted["attack_pools"])
    assert SNAP_SHOOTING_RULE_ID in cast(list[str], attack_pools[0]["targeting_rule_ids"])
    assert "<" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


def test_phase13d_fire_overwatch_rejects_invalid_declaration_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=1)
    record = _source_stratagem_record("fire-overwatch")
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.END_PHASE,
        trigger_payload=_fire_overwatch_trigger_payload(),
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )
    target_request = _decision_request(
        request_stratagem_target_proposal(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=proposal_request,
        )
    )
    target_proposal = _proposal_request_from_decision(target_request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )
    shooting_request = _decision_request(
        lifecycle.submit_decision(
            _target_proposal_result(
                request=target_request,
                result_id="phase13d-fire-overwatch-invalid-target",
                proposal=target_proposal,
            )
        )
    )
    declaration = _shooting_declaration_from_request(
        request=shooting_request,
        target_unit_id="army-beta:enemy-unit",
    )
    valid_payload = declaration.to_payload()
    missing_payload = cast(dict[str, JsonValue], dict(valid_payload))
    del missing_payload["declarations"]

    missing_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13d-fire-overwatch-missing-declaration",
            request_id=shooting_request.request_id,
            decision_type=shooting_request.decision_type,
            actor_id=shooting_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(missing_payload),
        )
    )

    assert missing_status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (shooting_request,)
    assert state.command_point_total("player-a") == 0
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.attack_sequence is None

    drifted_state = replace(state.out_of_phase_shooting_state, player_id="player-b")
    state.out_of_phase_shooting_state = drifted_state
    drift_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13d-fire-overwatch-player-drift",
            request_id=shooting_request.request_id,
            decision_type=shooting_request.decision_type,
            actor_id=shooting_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(valid_payload),
        )
    )

    assert drift_status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (shooting_request,)
    assert state.command_point_total("player-a") == 0
    assert state.out_of_phase_shooting_state.attack_sequence is None


def test_phase13d_fire_overwatch_rejects_unit_more_than_24_before_cp_spend() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=80.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-too-far",
            proposal=proposal,
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {
        "invalid_reason": "fire_overwatch_unit_not_within_24",
    }
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []


def test_phase13d_fire_overwatch_rejects_titanic_selected_unit_before_cp_spend() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("TITANIC", "VEHICLE"),
    )
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-titanic",
            proposal=proposal,
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "fire_overwatch_unit_titanic"}
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert state.out_of_phase_shooting_state is None


def test_phase13d_fire_overwatch_allows_titanic_triggering_enemy_unit() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_keywords(
        state,
        unit_instance_id="army-beta:enemy-unit",
        keywords=("TITANIC", "VEHICLE"),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    shooting_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-titanic-trigger",
            proposal=proposal,
        )
    )
    shooting_request = _decision_request(shooting_status)

    assert shooting_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert shooting_request.decision_type == "submit_shooting_declaration"
    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.out_of_phase_shooting_state is not None


def test_phase13d_fire_overwatch_rejects_engaged_selected_unit_before_cp_spend() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=1.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-engaged",
            proposal=proposal,
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "fire_overwatch_unit_engaged"}
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert state.out_of_phase_shooting_state is None


def test_phase13d_fire_overwatch_declaration_is_bound_to_triggering_enemy() -> None:
    lifecycle = _battle_lifecycle(
        config=_config(beta_unit_selection_ids=("enemy-unit", "enemy-unit-2"))
    )
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit-2",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=12.0) for index in range(5)),
    )
    _clear_terrain(state)
    _grant_cp(state, player_id="player-a", amount=1)
    target_request = _request_fire_overwatch_target_proposal(
        lifecycle,
        moved_unit_instance_id="army-beta:enemy-unit",
    )
    target_proposal = _proposal_request_from_decision(target_request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )
    shooting_request = _decision_request(
        lifecycle.submit_decision(
            _target_proposal_result(
                request=target_request,
                result_id="phase13d-fire-overwatch-bound-target",
                proposal=target_proposal,
            )
        )
    )
    request_payload = cast(dict[str, object], shooting_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    assert {candidate["target_unit_instance_id"] for candidate in target_candidates} == {
        "army-beta:enemy-unit"
    }
    available_weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    selected_weapon = available_weapons[0]
    invalid_declaration = ShootingDeclarationProposal(
        proposal_request_id=cast(str, proposal_request["request_id"]),
        proposal_kind="shooting_declaration",
        player_id=cast(str, proposal_request["active_player_id"]),
        battle_round=cast(int, proposal_request["battle_round"]),
        unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
        source_decision_request_id=cast(str, proposal_request["source_decision_request_id"]),
        source_decision_result_id=cast(str, proposal_request["source_decision_result_id"]),
        declarations=(
            WeaponDeclaration(
                attacker_model_instance_id=cast(str, selected_weapon["model_instance_id"]),
                wargear_id=cast(str, selected_weapon["wargear_id"]),
                weapon_profile_id=cast(str, selected_weapon["weapon_profile_id"]),
                target_unit_instance_id="army-beta:enemy-unit-2",
                shooting_type=_first_shooting_type(target_candidates[0]),
            ),
        ),
        visibility_cache_key=cast(str, proposal_request["visibility_cache_key"]),
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13d-fire-overwatch-wrong-target",
            request_id=shooting_request.request_id,
            decision_type=shooting_request.decision_type,
            actor_id=shooting_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(invalid_declaration.to_payload()),
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    validation = cast(dict[str, object], status.payload)["proposal_validation"]
    violations = cast(list[dict[str, object]], cast(dict[str, object], validation)["violations"])
    assert violations[0]["violation_code"] == "out_of_phase_target_unit_drift"
    assert lifecycle.decision_controller.queue.pending_requests == (shooting_request,)
    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.attack_sequence is None


def test_phase13d_fire_overwatch_rejects_fell_back_unit_before_cp_spend() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _clear_terrain(state)
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id="army-alpha:intercessor-unit-1",
            can_shoot=False,
        )
    )
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-fell-back",
            proposal=proposal,
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "fire_overwatch_unit_ineligible_to_shoot"}
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert state.out_of_phase_shooting_state is None


def test_phase13d_fire_overwatch_rejects_advanced_unit_without_assault_before_cp_spend() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    non_assault_profile = replace(
        base_profile,
        profile_id="phase13d-fire-overwatch-non-assault-rifle",
        keywords=tuple(
            keyword for keyword in base_profile.keywords if keyword is not WeaponKeyword.ASSAULT
        ),
    )
    lifecycle = _battle_lifecycle(
        config=_config(catalog=_catalog_with_replaced_bolt_profiles((non_assault_profile,)))
    )
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _clear_terrain(state)
    state.record_advanced_unit_state(
        _advanced_unit_state(
            state=state,
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            can_shoot=False,
        )
    )
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-advanced-no-assault",
            proposal=proposal,
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "fire_overwatch_unit_ineligible_to_shoot"}
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert state.out_of_phase_shooting_state is None


def test_phase13d_fire_overwatch_advanced_unit_exposes_only_assault_weapons() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    non_assault_profile = replace(
        base_profile,
        profile_id="phase13d-fire-overwatch-non-assault-filtered-rifle",
        keywords=tuple(
            keyword for keyword in base_profile.keywords if keyword is not WeaponKeyword.ASSAULT
        ),
    )
    assault_profile = replace(
        base_profile,
        profile_id="phase13d-fire-overwatch-assault-rifle",
    )
    lifecycle = _battle_lifecycle(
        config=_config(
            catalog=_catalog_with_replaced_bolt_profiles((non_assault_profile, assault_profile))
        )
    )
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        poses=tuple(Pose.at(index * 2.0, y=6.0) for index in range(5)),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(x=20.0 + index * 2.0, y=6.0) for index in range(5)),
    )
    _clear_terrain(state)
    state.record_advanced_unit_state(
        _advanced_unit_state(
            state=state,
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            can_shoot=False,
        )
    )
    _grant_cp(state, player_id="player-a", amount=1)
    request = _request_fire_overwatch_target_proposal(lifecycle)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    )

    shooting_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-fire-overwatch-advanced-assault",
            proposal=proposal,
        )
    )
    shooting_request = _decision_request(shooting_status)
    request_payload = cast(dict[str, object], shooting_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    available_weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])

    assert shooting_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert shooting_request.decision_type == "submit_shooting_declaration"
    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.out_of_phase_shooting_state is not None
    assert {weapon["weapon_profile_id"] for weapon in available_weapons} == {
        assault_profile.profile_id
    }


def test_phase13d_smokescreen_registers_defensive_effects() -> None:
    smoke_lifecycle = _battle_lifecycle()
    smoke_state = _state(smoke_lifecycle)
    _set_current_battle_phase(smoke_state, BattlePhase.SHOOTING)
    smoke_state.active_player_id = "player-b"
    _replace_unit_keywords(
        smoke_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Smoke"),
    )
    _grant_cp(smoke_state, player_id="player-a", amount=1)

    smoke_status = _submit_source_stratagem_target(
        smoke_lifecycle,
        stratagem_id="smokescreen",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        result_id="phase13d-smokescreen",
        trigger_payload={
            SELECTED_TARGET_UNIT_CONTEXT_KEY: ["army-alpha:intercessor-unit-1"],
        },
    )

    smoke_event = _last_event_payload(
        smoke_lifecycle.decision_controller,
        "smokescreen_effect_registered",
    )
    smoke_effect = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], smoke_event["persisting_effect"])["effect_payload"],
    )
    smoke_persisting_effect = cast(dict[str, JsonValue], smoke_event["persisting_effect"])
    smoke_expiration = cast(dict[str, JsonValue], smoke_persisting_effect["expiration"])
    assert smoke_status.status_kind is not LifecycleStatusKind.INVALID
    assert smoke_state.stratagem_use_records[-1].command_point_cost == 1
    assert smoke_state.stratagem_use_records[-1].command_point_transaction_id is not None
    assert smoke_effect["effect_kind"] == "core_stratagem:smokescreen"
    assert smoke_effect["benefit_of_cover"] is True
    assert smoke_effect["hit_roll_modifier"] == -1
    assert smoke_expiration["player_id"] == "player-b"

    invalid_lifecycle = _battle_lifecycle()
    invalid_state = _state(invalid_lifecycle)
    _set_current_battle_phase(invalid_state, BattlePhase.SHOOTING)
    invalid_state.active_player_id = "player-b"
    _grant_cp(invalid_state, player_id="player-a", amount=1)

    invalid_status = _submit_source_stratagem_target(
        invalid_lifecycle,
        stratagem_id="smokescreen",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        result_id="phase13d-smokescreen-wrong-target",
        trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: ["army-beta:enemy-unit"]},
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {"invalid_reason": "unit_not_selected_as_target"}
    assert invalid_state.command_point_total("player-a") == 1
    assert invalid_state.stratagem_use_records == []


def test_phase13d_explosives_resolves_mortal_wounds_and_rejects_invalid_context() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    _grant_cp(state, player_id="player-a", amount=1)

    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="explosives",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.START_PHASE,
        result_id="phase13d-explosives",
        trigger_payload={EXPLOSIVES_TARGET_CONTEXT_KEY: "army-beta:enemy-unit"},
    )

    explosives_payload = _last_event_payload(lifecycle.decision_controller, "explosives_resolved")
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("player-a") == 0
    use_record = state.stratagem_use_records[0]
    assert use_record.handler_id == "core:explosives"
    assert use_record.affected_unit_instance_ids == (
        "army-alpha:intercessor-unit-1",
        "army-beta:enemy-unit",
    )
    assert explosives_payload["explosives_unit_instance_id"] == ("army-alpha:intercessor-unit-1")
    assert explosives_payload["target_unit_instance_id"] == "army-beta:enemy-unit"
    mortal_wounds = explosives_payload["mortal_wounds"]
    assert isinstance(mortal_wounds, int)
    assert 0 <= mortal_wounds <= 6
    assert "<" not in json.dumps(lifecycle.to_payload(), sort_keys=True)

    invalid_lifecycle = _battle_lifecycle()
    invalid_state = _state(invalid_lifecycle)
    _set_current_battle_phase(invalid_state, BattlePhase.SHOOTING)
    invalid_state.active_player_id = "player-a"
    _replace_unit_keywords(
        invalid_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _grant_cp(invalid_state, player_id="player-a", amount=1)
    record = _source_stratagem_record("explosives")
    context = _context(
        state=invalid_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )
    waiting = request_stratagem_target_proposal(
        state=invalid_state,
        decisions=invalid_lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    invalid_status = invalid_lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-invalid-explosives",
            proposal=_proposal_request_from_decision(request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-a",
                    target_unit_instance_id="army-alpha:intercessor-unit-1",
                )
            ),
        )
    )
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {"invalid_reason": "missing_explosives_target"}
    assert invalid_state.command_point_total("player-a") == 1
    assert invalid_state.stratagem_use_records == []
    assert invalid_lifecycle.decision_controller.queue.pending_requests == (request,)

    shot_lifecycle = _battle_lifecycle()
    shot_state = _state(shot_lifecycle)
    _set_current_battle_phase(shot_state, BattlePhase.SHOOTING)
    shot_state.active_player_id = "player-a"
    _replace_unit_keywords(
        shot_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _replace_unit_poses(
        shot_state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    shot_state.shooting_phase_state = ShootingPhaseState(
        battle_round=shot_state.battle_round,
        active_player_id="player-a",
        shot_unit_ids=("army-alpha:intercessor-unit-1",),
    )
    _grant_cp(shot_state, player_id="player-a", amount=1)

    shot_status = _submit_source_stratagem_target(
        shot_lifecycle,
        stratagem_id="explosives",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.START_PHASE,
        result_id="phase13d-explosives-after-shooting",
        trigger_payload={EXPLOSIVES_TARGET_CONTEXT_KEY: "army-beta:enemy-unit"},
    )

    assert shot_status.status_kind is LifecycleStatusKind.INVALID
    assert shot_status.payload == {"invalid_reason": "explosives_unit_already_shot"}
    assert shot_state.command_point_total("player-a") == 1
    assert shot_state.stratagem_use_records == []


def test_phase13d_explosives_enemy_effect_does_not_block_opponent_targeting() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    _grant_cp(state, player_id="player-a", amount=1)
    _grant_cp(state, player_id="player-b", amount=1)

    explosives_status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="explosives",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.START_PHASE,
        result_id="phase13d-explosives-blocks-enemy",
        trigger_payload={EXPLOSIVES_TARGET_CONTEXT_KEY: "army-beta:enemy-unit"},
    )
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-b")
    context = _context(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=_command_reroll_trigger_payload(
            roll_state,
            unit_instance_id="army-beta:enemy-unit",
        ),
    )
    command_reroll_status = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )

    assert explosives_status.status_kind is not LifecycleStatusKind.INVALID
    assert state.stratagem_use_records[0].targeted_unit_instance_ids == (
        "army-alpha:intercessor-unit-1",
    )
    assert state.stratagem_use_records[0].affected_unit_instance_ids == (
        "army-alpha:intercessor-unit-1",
        "army-beta:enemy-unit",
    )
    assert command_reroll_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(state.stratagem_use_records) == 1
    assert state.command_point_total("player-b") == 1


def test_phase13d_explosives_canonicalizes_attached_enemy_component_target() -> None:
    attached_id = "attached-unit:army-beta:enemy-command-unit"
    lifecycle = _battle_lifecycle(
        config=_config(beta_unit_selection_ids=("enemy-unit", "enemy-unit-2"))
    )
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    _mark_attached_unit_join(
        state,
        player_id="player-b",
        attached_unit_instance_id=attached_id,
        component_unit_instance_ids=("army-beta:enemy-unit", "army-beta:enemy-unit-2"),
    )
    _grant_cp(state, player_id="player-a", amount=1)

    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="explosives",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.START_PHASE,
        result_id="phase13d-explosives-attached-enemy-target",
        trigger_payload={EXPLOSIVES_TARGET_CONTEXT_KEY: "army-beta:enemy-unit"},
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.stratagem_use_records[0].affected_unit_instance_ids == (
        "army-alpha:intercessor-unit-1",
        attached_id,
    )


def test_phase13d_explosives_unknown_enemy_target_rejects_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _grant_cp(state, player_id="player-a", amount=1)
    record = _source_stratagem_record("explosives")
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
        trigger_payload={EXPLOSIVES_TARGET_CONTEXT_KEY: "army-beta:missing-unit"},
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    invalid_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase13d-explosives-unknown-enemy-target",
            proposal=_proposal_request_from_decision(request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-a",
                    target_unit_instance_id="army-alpha:intercessor-unit-1",
                )
            ),
        )
    )

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {"invalid_reason": "unknown_explosives_target"}
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_phase13d_explosives_mortal_wounds_route_decline_allowed_feel_no_pain() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    state.active_player_id = "player-a"
    _replace_unit_keywords(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Infantry", "Battleline", "Grenades"),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(
            Pose.at(x=20.0 + index * 2.0, y=6.0, facing_degrees=180.0) for index in range(5)
        ),
    )
    target_model = model_by_id(
        state=state,
        model_instance_id="army-beta:enemy-unit:core-intercessor-like:001",
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=target_model.model_instance_id,
        sources=(FeelNoPainSource(source_id="phase13d-explosives-fnp", threshold=5),),
        decline_allowed=True,
    )
    _grant_cp(state, player_id="player-a", amount=1)

    status = _submit_source_stratagem_target(
        lifecycle,
        stratagem_id="explosives",
        player_id="player-a",
        target_unit_id="army-alpha:intercessor-unit-1",
        trigger_kind=TimingTriggerKind.START_PHASE,
        result_id="phase13d-explosives-fnp",
        trigger_payload={EXPLOSIVES_TARGET_CONTEXT_KEY: "army-beta:enemy-unit"},
    )
    request = _decision_request(status)
    stale_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13d-explosives-stale-fnp",
            request_id="phase13d-not-the-pending-fnp",
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="decline",
            payload={"selected_source_id": None},
        )
    )

    assert request.decision_type == "select_feel_no_pain"
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_status.payload == {
        "invalid_reason": "invalid_mortal_wound_feel_no_pain_result",
        "field": "request_id",
    }
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert not _has_event(lifecycle.decision_controller, "explosives_resolved")
    assert (
        model_by_id(state=state, model_instance_id=target_model.model_instance_id).wounds_remaining
        == target_model.wounds_remaining
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13d-explosives-valid-fnp-decline",
            request=request,
            selected_option_id="decline",
        )
    )
    assert state.command_point_total("player-a") == 0


def test_rapid_ingress_target_and_placement_proposals_resolve_through_lifecycle() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )
    assert state.command_point_total("player-b") == 0
    assert len(state.stratagem_use_records) == 1

    placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=placement,
    )

    lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(reserve_state.unit_instance_id) == placement
    assert _has_event(lifecycle.decision_controller, "reinforcement_unit_arrived")
    assert (
        _last_event_payload(lifecycle.decision_controller, "rapid_ingress_resolved")[
            "stratagem_use"
        ]
        == state.stratagem_use_records[0].to_payload()
    )
    assert "<" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


def test_rapid_ingress_reaction_target_and_placement_restore_before_parent_resumes() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, _reserve_unit, _reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("rapid-ingress"),
    )
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window_for_trigger(
            state,
            eligible_player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
            source_rule_id="phase12c-rapid-ingress-reaction",
            window_id="phase12c-rapid-ingress-window",
        ),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token="phase12c_rapid_ingress_resume_token",
        actor_id="player-b",
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        options=(parameterized_decision_option(),),
        payload=validate_json_value(
            {"proposal_request": validate_json_value(proposal_request.to_payload())}
        ),
    )
    restored_target = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    target_request = _decision_request(restored_target.advance_until_decision_or_terminal())

    target_status = restored_target.submit_decision(
        _target_proposal_result(
            request=target_request,
            result_id="phase12c-rapid-ingress-reaction-target",
            proposal=_proposal_request_from_decision(target_request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)

    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert len(restored_target.reaction_queue.frames) == 1
    assert restored_target.reaction_queue.frames[0].request_id == placement_request.request_id
    assert not _has_event(restored_target.decision_controller, "reaction_parent_resumed")
    assert _has_event(restored_target.decision_controller, "reaction_window_continued")

    restored_placement = GameLifecycle.from_payload(_lifecycle_payload_copy(restored_target))
    restored_state = _state(restored_placement)
    restored_reserve_state = restored_state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert restored_reserve_state is not None
    restored_army = restored_state.army_definition_for_player("player-b")
    assert restored_army is not None
    restored_reserve_unit = restored_army.unit_by_id(reserve_state.unit_instance_id)
    restored_placement_request = _decision_request(
        restored_placement.advance_until_decision_or_terminal()
    )
    placement = _reserve_placement(
        army=restored_army,
        reserve_unit=restored_reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(restored_reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=restored_placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=restored_reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=placement,
    )

    resumed = restored_placement.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-reaction-placement",
            request_id=restored_placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=restored_placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    assert restored_placement.reaction_queue.frames == ()
    assert resumed.status_kind is not LifecycleStatusKind.INVALID
    resumed_payload = _last_event_payload(
        restored_placement.decision_controller,
        "reaction_parent_resumed",
    )
    assert resumed_payload["resume_token"] == "phase12c_rapid_ingress_resume_token"
    assert _has_event(restored_placement.decision_controller, "rapid_ingress_resolved")
    arrived_state = restored_state.reserve_state_for_unit(restored_reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED


def test_movement_phase_progression_offers_rapid_ingress_reaction_from_index() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, _reserve_unit, _reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        reinforcements_completed=True,
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        moved_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    target_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert target_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    assert len(lifecycle.reaction_queue.frames) == 1
    proposal_request = _proposal_request_from_decision(target_request)
    assert proposal_request.stratagem_id == "rapid-ingress"
    assert proposal_request.player_id == "player-b"

    target_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=target_request,
            result_id="phase12c-progressed-rapid-ingress-target",
            proposal=proposal_request.with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    restored_state = _state(restored)
    restored_reserve_state = restored_state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert restored_reserve_state is not None
    restored_army = restored_state.army_definition_for_player("player-b")
    assert restored_army is not None
    restored_reserve_unit = restored_army.unit_by_id(reserve_state.unit_instance_id)
    restored_placement_request = _decision_request(restored.advance_until_decision_or_terminal())
    assert restored_placement_request.request_id == placement_request.request_id
    placement = _reserve_placement(
        army=restored_army,
        reserve_unit=restored_reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(restored_reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=restored_placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=restored_reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=placement,
    )

    restored.submit_decision(
        DecisionResult(
            result_id="phase12c-progressed-rapid-ingress-placement",
            request_id=restored_placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=restored_placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    assert restored.reaction_queue.frames == ()
    assert (
        _last_event_payload(restored.decision_controller, "reaction_parent_resumed")["resume_token"]
        == "rapid-ingress-end-movement-round-02-player-player-b-resume"
    )
    assert _has_event(restored.decision_controller, "rapid_ingress_resolved")
    arrived_state = restored_state.reserve_state_for_unit(restored_reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED


def test_movement_phase_progression_declines_rapid_ingress_reaction_from_index() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, _reserve_unit, _reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        reinforcements_completed=True,
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        moved_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    target_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert target_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    restored_request = _decision_request(restored.advance_until_decision_or_terminal())

    declined = restored.submit_decision(
        DecisionResult(
            result_id="phase12c-decline-rapid-ingress",
            request_id=restored_request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=restored_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )

    restored_state = _state(restored)
    restored_reserve_state = restored_state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert restored_reserve_state is not None
    assert restored_reserve_state.status is ReserveStatus.IN_RESERVES
    assert restored_state.command_point_total("player-b") == 2
    assert restored_state.stratagem_use_records == []
    assert restored.reaction_queue.frames == ()
    assert _has_event(restored.decision_controller, "stratagem_window_declined")
    assert (
        _last_event_payload(restored.decision_controller, "reaction_parent_resumed")["resume_token"]
        == "rapid-ingress-end-movement-round-02-player-player-b-resume"
    )
    declined_request = _decision_request(declined)
    assert declined_request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    assert not _has_event(restored.decision_controller, "rapid_ingress_resolved")


def test_rapid_ingress_invalid_placement_is_typed_invalid_without_arrival() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )
    invalid_placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=8.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=invalid_placement,
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-invalid-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["phase_body_status"] == "rapid_ingress_placement_invalid"
    next_request_id = status.payload["next_request_id"]
    assert type(next_request_id) is str
    retry_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert retry_request.request_id == next_request_id
    assert retry_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state
    assert state.battlefield_state is not None
    assert not any(
        unit_placement.unit_instance_id == reserve_state.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    assert _has_event(lifecycle.decision_controller, "rapid_ingress_placement_invalid")


def test_rapid_ingress_reaction_invalid_placement_keeps_parent_blocked_for_retry() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_reaction_placement(lifecycle)
    )
    invalid_placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=8.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=invalid_placement,
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-reaction-invalid-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )
    retry_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["next_request_id"] == retry_request.request_id
    assert len(lifecycle.reaction_queue.frames) == 1
    assert lifecycle.reaction_queue.frames[0].request_id == retry_request.request_id
    assert not _has_event(lifecycle.decision_controller, "reaction_parent_resumed")
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_rapid_ingress_stale_placement_proposal_rejects_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )
    stale_placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    stale_payload = PlacementProposalPayload(
        proposal_request_id="phase12c-stale-placement-request",
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=stale_placement,
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-stale-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(stale_payload.to_payload()),
        )
    )
    still_pending = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    validation_payload = cast(dict[str, JsonValue], status.payload["proposal_validation"])
    violations = cast(list[JsonValue], validation_payload["violations"])
    violation_payload = cast(dict[str, JsonValue], violations[0])
    assert violation_payload["violation_code"] == "stale_proposal_request"
    assert still_pending == placement_request
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_rapid_ingress_malformed_placement_payload_rejects_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, _reserve_unit, _reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-malformed-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=None,
        )
    )
    still_pending = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "malformed"}
    assert still_pending == placement_request
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def _source_stratagem_record(stratagem_id: str) -> StratagemCatalogRecord:
    for record in eleventh_edition_stratagem_catalog_records():
        if record.definition.stratagem_id == stratagem_id:
            return record
    raise AssertionError(f"Missing source stratagem record: {stratagem_id}")


def _roll_command_reroll_candidate(
    lifecycle: GameLifecycle,
    *,
    actor_id: str,
    roll_type: str = "advance_roll",
    quantity: int = 1,
    values: tuple[int, ...] | None = None,
) -> DiceRollState:
    return _roll_command_reroll_candidate_from_spec(
        lifecycle,
        DiceRollSpec(
            expression=DiceExpression(quantity=quantity, sides=6),
            reason="Phase 12C Command Re-roll candidate",
            roll_type=roll_type,
            actor_id=actor_id,
        ),
        values=values,
    )


def _roll_command_reroll_candidate_from_spec(
    lifecycle: GameLifecycle,
    spec: DiceRollSpec,
    *,
    values: tuple[int, ...] | None = None,
) -> DiceRollState:
    state = _state(lifecycle)
    roll_values = (1,) if values is None else values
    return DiceRollManager(
        state.game_id,
        event_log=lifecycle.decision_controller.event_log,
    ).roll_fixed(
        spec,
        roll_values,
    )


def _command_reroll_trigger_payload(
    roll_state: DiceRollState,
    *,
    unit_instance_id: str = "army-alpha:intercessor-unit-1",
) -> JsonValue:
    return validate_json_value(
        {
            COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload()),
            COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY: unit_instance_id,
        }
    )


def _context(
    *,
    state: GameState,
    player_id: str,
    trigger_kind: TimingTriggerKind,
    trigger_payload: JsonValue = None,
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext.from_state(
        state=state,
        player_id=player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )


def _fire_overwatch_trigger_payload(
    moved_unit_instance_id: str = "army-beta:enemy-unit",
) -> JsonValue:
    return validate_json_value(
        {
            FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY: moved_unit_instance_id,
            "movement_phase_action": "normal_move",
            "movement_payload": {
                "unit_instance_id": moved_unit_instance_id,
                "movement_phase_action": "normal_move",
            },
        }
    )


def _request_fire_overwatch_target_proposal(
    lifecycle: GameLifecycle,
    *,
    moved_unit_instance_id: str = "army-beta:enemy-unit",
) -> DecisionRequest:
    state = _state(lifecycle)
    record = _source_stratagem_record("fire-overwatch")
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.END_PHASE,
        trigger_payload=_fire_overwatch_trigger_payload(moved_unit_instance_id),
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )
    return _decision_request(
        request_stratagem_target_proposal(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=proposal_request,
        )
    )


def _advanced_unit_state(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    can_shoot: bool,
) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:advance-roll",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase12c-advanced-state").roll_fixed(request.spec, [3])
    return AdvancedUnitState(
        player_id=player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id=player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
        can_shoot=can_shoot,
    )


def _reaction_window(state: GameState, *, eligible_player_id: str) -> ReactionWindow:
    return _reaction_window_for_trigger(
        state=state,
        eligible_player_id=eligible_player_id,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        source_rule_id="phase12c-command-reroll-reaction",
        window_id="phase12c-reaction-window-instance",
    )


def _reaction_window_for_trigger(
    state: GameState,
    *,
    eligible_player_id: str,
    trigger_kind: TimingTriggerKind,
    source_rule_id: str,
    window_id: str,
    phase: BattlePhase = BattlePhase.MOVEMENT,
) -> ReactionWindow:
    descriptor = TimingWindowDescriptor(
        descriptor_id="phase12c-reaction-window",
        trigger_kind=trigger_kind,
        source_rule_id=source_rule_id,
        phase=phase,
    )
    window = TimingWindow(
        window_id=window_id,
        descriptor=descriptor,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        trigger_event_id="phase12c-trigger-event",
    )
    return ReactionWindow(
        timing_window=window,
        eligible_player_ids=(eligible_player_id,),
    )


def _target_proposal_result(
    *,
    request: DecisionRequest,
    result_id: str,
    proposal: StratagemTargetProposal,
) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )


def _submit_heroic_charge_move_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    proposal: ChargeMoveProposal,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(proposal.to_payload()),
        )
    )


def _submit_source_stratagem_target(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    player_id: str,
    target_unit_id: str,
    trigger_kind: TimingTriggerKind,
    result_id: str,
    trigger_payload: JsonValue = None,
    effect_selection: JsonValue = None,
) -> LifecycleStatus:
    state = _state(lifecycle)
    record = _source_stratagem_record(stratagem_id)
    context = _context(
        state=state,
        player_id=player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    proposal = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=player_id,
            target_unit_instance_id=target_unit_id,
        ),
        effect_selection=effect_selection,
    )
    return lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id=result_id,
            proposal=proposal,
        )
    )


def _handcrafted_stratagem_option(
    *,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    binding: StratagemTargetBinding,
) -> DecisionOption:
    return DecisionOption(
        option_id=f"use-stratagem:{record.definition.stratagem_id}:target:handcrafted",
        label=record.definition.name,
        payload=validate_json_value(
            {
                "submission_kind": STRATAGEM_DECISION_TYPE,
                "context": context.to_payload(),
                "catalog_record": record.to_payload(),
                "target_binding": binding.to_payload(),
                "effect_selection": None,
            }
        ),
    )


def _replace_unit_keywords(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = tuple(
            replace(unit, keywords=keywords) if unit.unit_instance_id == unit_instance_id else unit
            for unit in army.units
        )
        if units != army.units:
            state.army_definitions[army_index] = replace(army, units=units)
            return
    raise AssertionError(f"Missing unit {unit_instance_id}.")


def _replace_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    assert len(placement.model_placements) == len(poses)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement.with_pose(pose)
                    for model_placement, pose in zip(placement.model_placements, poses, strict=True)
                )
            )
        )
    )


def _path_witness_for_unit_delta(
    state: GameState,
    *,
    unit_instance_id: str,
    dx: float = 0.0,
    dy: float = 0.0,
    endpoint_only: bool = False,
) -> PathWitness:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for model_placement in placement.model_placements:
        start = model_placement.pose
        midpoint = Pose.at(
            x=start.position.x + (dx / 2.0),
            y=start.position.y + (dy / 2.0),
            z=start.position.z,
            facing_degrees=start.facing.degrees,
        )
        end = Pose.at(
            x=start.position.x + dx,
            y=start.position.y + dy,
            z=start.position.z,
            facing_degrees=start.facing.degrees,
        )
        if endpoint_only:
            model_paths.append((model_placement.model_instance_id, (start, end, end)))
            continue
        model_paths.append((model_placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _first_model_id(state: GameState, *, unit_instance_id: str) -> str:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit.own_models[0].model_instance_id
    raise AssertionError(f"Missing unit {unit_instance_id}.")


def _mark_attached_unit_join(
    state: GameState,
    *,
    player_id: str,
    attached_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> None:
    source_id = f"attached-unit-join:{attached_unit_instance_id}"
    component_id_set = set(component_unit_instance_ids)
    component_starting_model_count = 0
    updated_records: list[StartingStrengthRecord] = []
    for record in state.starting_strength_records:
        if record.unit_instance_id not in component_id_set:
            updated_records.append(record)
            continue
        component_starting_model_count += record.starting_model_count
        updated_records.append(replace(record, source_id=source_id))
    if component_starting_model_count == 0:
        raise AssertionError("Attached-unit test fixture did not find component records.")
    updated_records.append(
        StartingStrengthRecord(
            player_id=player_id,
            unit_instance_id=attached_unit_instance_id,
            starting_model_count=component_starting_model_count,
            single_model_starting_wounds=None,
            source_id=source_id,
        )
    )
    state.starting_strength_records = sorted(
        updated_records,
        key=lambda record: record.unit_instance_id,
    )


def _clear_terrain(state: GameState) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.battlefield_state = replace(battlefield_state, terrain_features=())


def _proposal_request_from_decision(request: DecisionRequest) -> StratagemTargetProposal:
    payload = cast(dict[str, JsonValue], request.payload)
    return StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, payload["proposal_request"])
    )


def _shooting_declaration_from_request(
    *,
    request: DecisionRequest,
    target_unit_id: str,
) -> ShootingDeclarationProposal:
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    target_candidate = next(
        candidate
        for candidate in target_candidates
        if candidate["target_unit_instance_id"] == target_unit_id and candidate["is_legal"] is True
    )
    observer_model_id = target_candidate["observer_model_id"]
    selected_weapon = next(
        weapon for weapon in weapons if weapon["model_instance_id"] == observer_model_id
    )
    return ShootingDeclarationProposal(
        proposal_request_id=cast(str, proposal_request["request_id"]),
        proposal_kind="shooting_declaration",
        player_id=cast(str, proposal_request["active_player_id"]),
        battle_round=cast(int, proposal_request["battle_round"]),
        unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
        source_decision_request_id=cast(str, proposal_request["source_decision_request_id"]),
        source_decision_result_id=cast(str, proposal_request["source_decision_result_id"]),
        declarations=(
            WeaponDeclaration(
                attacker_model_instance_id=cast(str, selected_weapon["model_instance_id"]),
                wargear_id=cast(str, selected_weapon["wargear_id"]),
                weapon_profile_id=cast(str, selected_weapon["weapon_profile_id"]),
                target_unit_instance_id=target_unit_id,
                shooting_type=_first_shooting_type(target_candidate),
            ),
        ),
        visibility_cache_key=cast(str, target_candidate["visibility_cache_key"]),
    )


def _first_shooting_type(target_candidate: dict[str, object]) -> ShootingType:
    shooting_types = cast(list[str], target_candidate["shooting_types"])
    if not shooting_types:
        raise AssertionError("Target candidate has no shooting types.")
    return ShootingType(shooting_types[0])


def _move_unit_to_reserves(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> tuple[ReserveState, UnitInstance, ArmyDefinition]:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.replace_battlefield_state(battlefield_state.without_unit_placement(unit_instance_id))
    reserve_state = ReserveState.declared_before_battle(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_kind=ReserveKind.RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.chapter_approved_2026_27(),
    )
    state.record_reserve_state(reserve_state)
    army = state.army_definition_for_player(player_id)
    assert army is not None
    return reserve_state, army.unit_by_id(unit_instance_id), army


def _request_rapid_ingress_placement(
    lifecycle: GameLifecycle,
) -> tuple[GameState, ReserveState, UnitInstance, ArmyDefinition, DecisionRequest]:
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, reserve_unit, reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("rapid-ingress"),
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    target_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase12c-rapid-ingress-target",
            proposal=_proposal_request_from_decision(request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    return state, reserve_state, reserve_unit, reserve_army, placement_request


def _request_rapid_ingress_reaction_placement(
    lifecycle: GameLifecycle,
) -> tuple[GameState, ReserveState, UnitInstance, ArmyDefinition, DecisionRequest]:
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, reserve_unit, reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("rapid-ingress"),
    )
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window_for_trigger(
            state,
            eligible_player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
            source_rule_id="phase12c-rapid-ingress-retry-reaction",
            window_id="phase12c-rapid-ingress-retry-window",
        ),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token="phase12c_rapid_ingress_retry_resume_token",
        actor_id="player-b",
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        options=(parameterized_decision_option(),),
        payload=validate_json_value(
            {"proposal_request": validate_json_value(proposal_request.to_payload())}
        ),
    )
    target_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    target_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=target_request,
            result_id="phase12c-rapid-ingress-reaction-retry-target",
            proposal=_proposal_request_from_decision(target_request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert lifecycle.reaction_queue.frames[0].request_id == placement_request.request_id
    return state, reserve_state, reserve_unit, reserve_army, placement_request


def _reserve_placement(
    *,
    army: ArmyDefinition,
    reserve_unit: UnitInstance,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(reserve_unit.own_models, poses, strict=True)
        ),
    )


def _remove_first_models(state: GameState, *, unit_instance_id: str, count: int) -> None:
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    removed_ids = tuple(
        placement.model_instance_id for placement in unit_placement.model_placements[:count]
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(removed_ids)


def _record_secondary_choices(
    state: GameState,
    *,
    player_a_mode: SecondaryMissionMode,
    player_b_mode: SecondaryMissionMode,
) -> None:
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=player_a_mode)
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=player_b_mode)
    )


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "cleanse"),
    )


def _set_command_step_ready_for_battle_shock(state: GameState) -> None:
    command_state = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    state.command_step_state = (
        command_state.with_command_points_granted()
        .with_scoring_hooks_resolved()
        .with_tactical_secondary_resolved()
    )


def _set_command_step_ready_for_tactical_secondary(state: GameState) -> None:
    command_state = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    state.command_step_state = (
        command_state.with_command_points_granted().with_scoring_hooks_resolved()
    )


def _battle_lifecycle(config: GameConfig | None = None) -> GameLifecycle:
    config = _config() if config is None else config
    state = _battle_state(config=config)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )


def _battle_state(config: GameConfig | None = None) -> GameState:
    resolved_config = _config() if config is None else config
    armies = _mustered_armies(resolved_config)
    state = GameState.from_config(resolved_config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase12c-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    enter_battle_for_fixture(state)
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _config(
    *,
    beta_unit_selection_ids: tuple[str, ...] = ("enemy-unit",),
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id="phase12c-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase12c-test"
        ),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=beta_unit_selection_ids,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _weapon_profile_by_wargear(
    *,
    wargear_id: str,
    weapon_profile_id: str,
) -> WeaponProfile:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    for wargear in catalog.wargear:
        if wargear.wargear_id != wargear_id:
            continue
        for profile in wargear.weapon_profiles:
            if profile.profile_id == weapon_profile_id:
                return profile
    raise AssertionError(f"Missing weapon profile {weapon_profile_id}.")


def _catalog_with_replaced_bolt_profiles(
    weapon_profiles: tuple[WeaponProfile, ...],
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    updated_wargear: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id == "core-bolt-rifle":
            updated_wargear.append(replace(wargear, weapon_profiles=weapon_profiles))
            continue
        updated_wargear.append(wargear)
    return replace(catalog, wargear=tuple(updated_wargear))


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str | None = None,
    unit_selection_ids: tuple[str, ...] | None = None,
) -> ArmyMusterRequest:
    if unit_selection_id is not None and unit_selection_ids is not None:
        raise AssertionError("Use unit_selection_id or unit_selection_ids, not both.")
    resolved_unit_selection_ids: tuple[str, ...]
    if unit_selection_ids is None:
        if unit_selection_id is None:
            raise AssertionError("Expected at least one unit selection id.")
        resolved_unit_selection_ids = (unit_selection_id,)
    else:
        resolved_unit_selection_ids = unit_selection_ids
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
        unit_selections=(
            *(
                UnitMusterSelection(
                    unit_selection_id=resolved_unit_selection_id,
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_selections=(
                        ModelProfileSelection(
                            model_profile_id="core-intercessor-like",
                            model_count=5,
                        ),
                    ),
                )
                for resolved_unit_selection_id in resolved_unit_selection_ids
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"phase12c-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    if phase is not BattlePhase.COMMAND:
        _record_default_fixed_secondary_choices_for_missing_players(state)


def _record_default_fixed_secondary_choices_for_missing_players(state: GameState) -> None:
    for player_id in state.missing_secondary_mission_player_ids():
        state.record_secondary_mission_choice(
            _secondary_choice(player_id=player_id, mode=SecondaryMissionMode.FIXED)
        )


def _lifecycle_payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _has_event(decisions: DecisionController, event_type: str) -> bool:
    return any(event.event_type == event_type for event in decisions.event_log.records)


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
