"""Canonical declaration ledger setup for focused post-attack executor fixtures.

These fixtures test later engine boundaries. Retain the typed request, proposal,
accepted result and declaration that precede the supplied executor; a completion
pair on its own is not a valid lifecycle history.
"""

from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightActivationSelection,
)
from warhammer40k_core.engine.game_state import GameState, RangedAttackHistoryRecord
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.weapon_declaration import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingDeclarationProposal,
    WeaponDeclaration,
)


def record_attack_completion_for_executor_fixture(
    *, state: GameState, decisions: DecisionController, sequence: AttackSequence
) -> EventRecord:
    from warhammer40k_core.engine.model_attack_history import (
        record_attack_sequence_completed,
        record_models_attacked,
    )

    record_models_attacked(state=state, decisions=decisions, sequence=sequence)
    record_attack_sequence_completed(state=state, decisions=decisions, sequence=sequence)
    return next(
        event
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
    )


def record_completed_shooting_for_executor_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    successful_hit_pool_indices: tuple[int, ...],
) -> str:
    """Record the canonical declaration and completion surrounding supplied hits."""
    from warhammer40k_core.engine.model_attack_history import (
        record_attack_sequence_completed,
        record_models_attacked,
    )

    assert sequence.is_complete
    prefix = (
        "out-of-phase-attack-sequence:"
        if state.current_battle_phase is not BattlePhase.SHOOTING
        or state.active_player_id != sequence.attacker_player_id
        else "attack-sequence:"
    )
    assert sequence.sequence_id.startswith(prefix)
    record_shooting_declaration_for_executor_fixture(
        state=state,
        decisions=decisions,
        sequence=sequence,
        result_id=sequence.sequence_id.removeprefix(prefix),
    )
    for pool_index in successful_hit_pool_indices:
        assert 0 <= pool_index < len(sequence.attack_pools)
        decisions.event_log.append(
            "attack_sequence_step",
            {
                "sequence_id": sequence.sequence_id,
                "step": "hit",
                "pool_index": pool_index,
                "payload": {"successful": True},
            },
        )
    record_models_attacked(state=state, decisions=decisions, sequence=sequence)
    record_attack_sequence_completed(state=state, decisions=decisions, sequence=sequence)
    from warhammer40k_core.engine.attack_sequence_completion_hooks import (
        attack_sequence_completed_event_id,
    )

    return attack_sequence_completed_event_id(decisions=decisions, attack_sequence=sequence)


def record_shooting_declaration_for_executor_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    result_id: str,
) -> None:
    out_of_phase = (
        state.current_battle_phase is not BattlePhase.SHOOTING
        or state.active_player_id != sequence.attacker_player_id
    )
    prefix = "out-of-phase-" if out_of_phase else ""
    if sequence.sequence_id != f"{prefix}attack-sequence:{result_id}":
        raise AssertionError("Executor fixture requires its exact declaration sequence ID")
    request_id = f"kakophonist-declaration-request:{result_id}"
    visibility_cache_key = f"kakophonist-visibility:{result_id}"
    source_request_id = f"kakophonist-unit-selection-request:{result_id}"
    source_result_id = f"kakophonist-unit-selection-result:{result_id}"
    proposal_request = {
        "request_id": request_id,
        "active_player_id": sequence.attacker_player_id,
        "battle_round": state.battle_round,
        "unit_instance_id": sequence.attacking_unit_instance_id,
        "source_decision_request_id": source_request_id,
        "source_decision_result_id": source_result_id,
        "visibility_cache_key": visibility_cache_key,
        "proposal_kind": "shooting_declaration",
    }
    request = DecisionRequest(
        request_id=request_id,
        decision_type=SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        actor_id=sequence.attacker_player_id,
        payload=validate_json_value(
            {
                "proposal_request": proposal_request,
                "request_context": {},
                "nested_interaction_requests": [],
            }
        ),
        options=(parameterized_decision_option(),),
    )
    decisions.request_decision(request)
    proposal = ShootingDeclarationProposal(
        proposal_request_id=request_id,
        proposal_kind="shooting_declaration",
        player_id=sequence.attacker_player_id,
        battle_round=state.battle_round,
        unit_instance_id=sequence.attacking_unit_instance_id,
        source_decision_request_id=source_request_id,
        source_decision_result_id=source_result_id,
        declarations=tuple(
            WeaponDeclaration(
                weapon_instance_id=pool.weapon_instance_id,
                attacker_model_instance_id=pool.attacker_model_instance_id,
                wargear_id=pool.wargear_id,
                weapon_profile_id=pool.weapon_profile_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                shooting_type=pool.shooting_type,
                selected_weapon_ability_ids=pool.selected_weapon_ability_ids,
                firing_deck_source_unit_instance_id=(pool.firing_deck_source_unit_instance_id),
                firing_deck_source_model_instance_id=(pool.firing_deck_source_model_instance_id),
            )
            for pool in sequence.attack_pools
        ),
        visibility_cache_key=visibility_cache_key,
    )
    decisions.submit_result(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(proposal.to_payload()),
        )
    )
    assert state.active_player_id is not None
    assert state.current_battle_phase is not None
    ranged = RangedAttackHistoryRecord(
        player_id=sequence.attacker_player_id,
        unit_instance_id=sequence.attacking_unit_instance_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=state.current_battle_phase,
        request_id=request.request_id,
        result_id=result_id,
    )
    state.record_ranged_attack_history(ranged)
    payload: dict[str, object] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": sequence.attacker_player_id,
        "phase": BattlePhase.SHOOTING.value,
        "unit_instance_id": sequence.attacking_unit_instance_id,
        "request_id": request.request_id,
        "result_id": result_id,
        "proposal_request_id": request.request_id,
        "visibility_cache_key": visibility_cache_key,
        "attack_pools": [pool.to_payload() for pool in sequence.attack_pools],
        "ineligible_unit_instance_ids": [],
    }
    if out_of_phase:
        assert state.current_battle_phase is not None
        payload.pop("active_player_id")
        payload.pop("phase")
        payload.update(
            {
                "player_id": sequence.attacker_player_id,
                "parent_phase": state.current_battle_phase.value,
                "ranged_attack_history_record": ranged.to_payload(),
            }
        )
    decisions.event_log.append(
        "out_of_phase_shooting_declaration_accepted"
        if out_of_phase
        else "shooting_declaration_accepted",
        validate_json_value(payload),
    )


def record_melee_declaration_for_executor_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    result_id: str,
) -> None:
    from warhammer40k_core.engine.fight_resolution import (
        MELEE_DECLARATION_PROPOSAL_KIND,
        MeleeDeclarationProposal,
        MeleeDeclarationProposalRequest,
        MeleeTargetAllocation,
        MeleeWeaponDeclaration,
        build_melee_declaration_request,
    )

    expected_id = (
        f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
        f"{sequence.attacking_unit_instance_id}:{result_id}"
    )
    if sequence.source_phase is not BattlePhase.FIGHT or sequence.sequence_id != expected_id:
        raise AssertionError("Melee executor fixture requires its exact declaration sequence ID")
    assert state.active_player_id is not None
    request = build_melee_declaration_request(
        request_id=f"melee-fixture-request:{result_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        actor_id=sequence.attacker_player_id,
        unit_instance_id=sequence.attacking_unit_instance_id,
        source_decision_request_id=f"melee-fixture-activation-request:{result_id}",
        source_decision_result_id=f"melee-fixture-activation-result:{result_id}",
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        available_weapons=tuple(
            validate_json_value(pool.to_payload()) for pool in sequence.attack_pools
        ),
        target_unit_instance_ids=tuple(
            sorted({pool.target_unit_instance_id for pool in sequence.attack_pools})
        ),
    )
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(request)
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=MELEE_DECLARATION_PROPOSAL_KIND,
        player_id=sequence.attacker_player_id,
        battle_round=state.battle_round,
        unit_instance_id=sequence.attacking_unit_instance_id,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        declarations=tuple(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=pool.attacker_model_instance_id,
                wargear_id=pool.wargear_id,
                weapon_profile_id=pool.weapon_profile_id,
                target_allocations=(
                    MeleeTargetAllocation(target_unit_instance_id=pool.target_unit_instance_id),
                ),
            )
            for pool in sequence.attack_pools
        ),
    )
    decisions.request_decision(request)
    decisions.submit_result(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(proposal.to_payload()),
        )
    )
    decisions.event_log.append(
        "melee_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": "melee_declaration_accepted",
                "request_id": request.request_id,
                "result_id": result_id,
                "proposal_request": proposal_request.to_payload(),
                "proposal": proposal.to_payload(),
                "attack_sequence_id": sequence.sequence_id,
                "one_shot_weapon_use_records": [],
            }
        ),
    )


def resolve_catalog_attack_children_for_executor_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    ability_indexes: Mapping[str, AbilityCatalogIndex],
) -> None:
    """Finish newly triggered catalog rules after the supplied parent executor."""
    from warhammer40k_core.engine.battle_shock_outcome_triggers import resolve_battle_shock_trigger
    from warhammer40k_core.engine.catalog_command_point_runtime import CatalogCommandPointRuntime
    from warhammer40k_core.engine.model_destruction_triggers import (
        record_model_destruction_occurrences,
        resolve_model_destruction_trigger,
    )
    from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history
    from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookRegistry

    destruction_hooks = UnitDestroyedHookRegistry.from_bindings(
        CatalogCommandPointRuntime(
            ability_indexes_by_player_id=ability_indexes,
            armies=tuple(state.army_definitions),
        ).unit_destroyed_hook_bindings()
    )
    record_model_destruction_occurrences(
        state=state, decisions=decisions, registry=destruction_hooks
    )
    while ready := rule_trigger_history(decisions).ready():
        trigger = ready[0]
        if trigger.kind is RuleTriggerKind.BATTLE_SHOCK_OUTCOME:
            status = resolve_battle_shock_trigger(
                state=state, decisions=decisions, trigger=trigger, registry=battle_shock_hooks
            )
        elif trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION:
            status = resolve_model_destruction_trigger(
                state=state, decisions=decisions, trigger=trigger, registry=destruction_hooks
            )
        else:
            raise AssertionError("Catalog executor fixture received an unrelated child trigger")
        assert status is None or status.status_kind is LifecycleStatusKind.ADVANCED
        assert not decisions.queue.pending_requests


def resolve_core_attack_completion_for_executor_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence_id: str,
    dice_manager: DiceRollManager,
) -> LifecycleStatus | None:
    """Follow a completed Core executor into its shared after-attacks rule batch."""
    from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
    from warhammer40k_core.engine.attack_sequence_completion_hooks import (
        AttackSequenceCompletedContext,
        AttackSequenceCompletedHookRegistry,
        attack_sequence_completed_event_id,
    )
    from warhammer40k_core.engine.model_destruction_triggers import (
        resolve_model_destruction_trigger,
    )
    from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookRegistry

    # Core attack casualties precede the after-attacks occurrence. These isolated
    # executor fixtures have no additional unit-destruction ability providers.
    sequence = completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence_id
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=sequence.source_phase,
        attack_sequence=sequence,
        attack_sequence_completed_event_id=attack_sequence_completed_event_id(
            decisions=decisions, attack_sequence=sequence
        ),
    )
    for _ in range(32):
        while ready := rule_trigger_history(decisions).ready():
            if ready[0].kind is RuleTriggerKind.ATTACK_COMPLETION:
                break
            assert ready[0].kind is RuleTriggerKind.MODEL_DESTRUCTION
            status = resolve_model_destruction_trigger(
                state=state,
                decisions=decisions,
                trigger=ready[0],
                registry=UnitDestroyedHookRegistry.empty(),
            )
            assert status is None
        status = AttackSequenceCompletedHookRegistry.empty().resolve_completed_sequence(context)
        if status is None or status.status_kind is not LifecycleStatusKind.ADVANCED:
            return status
    raise AssertionError("Core attack completion did not finish its deferred children")


def record_fight_selection_for_executor_fixture(
    *, decisions: DecisionController, selection: FightActivationSelection
) -> None:
    """Retain the accepted selection before an isolated melee executor runs."""
    request = DecisionRequest(
        request_id=selection.request_id,
        decision_type=FIGHT_ACTIVATION_DECISION_TYPE,
        actor_id=selection.player_id,
        payload=validate_json_value(selection.to_payload()),
        options=(
            DecisionOption(
                option_id=selection.unit_instance_id,
                label="Select fixture attacker",
                payload=validate_json_value(selection.to_payload()),
            ),
        ),
    )
    decisions.request_decision(request)
    decisions.submit_result(
        DecisionResult.for_request(
            request=request,
            result_id=selection.result_id,
            selected_option_id=selection.unit_instance_id,
        )
    )
