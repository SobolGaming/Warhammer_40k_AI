from __future__ import annotations

# These context builders are shared with their authoritative boundary owners.
# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartRequestContext,
    _battle_round_sequencing_context,
)
from warhammer40k_core.engine.boundary_rule_flow import compose_core_end_rule_registry
from warhammer40k_core.engine.boundary_sequencing import boundary_context, start_turn_context
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartEffectContext
from warhammer40k_core.engine.command_phase_start_sequencing import (
    command_start_candidates,
    command_start_timing_context,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartRequestContext
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_timing_sequencing import runtime_timing_candidates
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.shooting_phase_start_hooks import ShootingPhaseStartRequestContext
from warhammer40k_core.engine.timing_batch_state import TimingBatch
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext

BOUNDARY_ORDER_TRIGGERS = frozenset(
    {
        TimingTriggerKind.START_BATTLE_ROUND,
        TimingTriggerKind.START_TURN,
        TimingTriggerKind.START_PHASE,
        TimingTriggerKind.END_PHASE,
        TimingTriggerKind.END_TURN,
        TimingTriggerKind.END_BATTLE_ROUND,
    }
)


def validate_boundary_order_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    batch: TimingBatch,
    bundle: RuntimeContentBundle,
    config: GameConfig,
    reaction_queue: ReactionQueue,
) -> None:
    kind = batch.context.timing_window.descriptor.trigger_kind
    if kind not in BOUNDARY_ORDER_TRIGGERS:
        raise GameLifecycleError("Boundary source authority requires a boundary trigger.")
    active, phase = state.active_player_id, state.current_battle_phase
    if active is None or phase is None:
        raise GameLifecycleError("Boundary source authority requires the current player turn.")
    candidates: tuple[TimingRuleCandidate, ...]
    authority: SequencingConflictContext
    if kind is TimingTriggerKind.START_BATTLE_ROUND:
        context = BattleRoundStartRequestContext(state=state, decisions=decisions)
        authority = _battle_round_sequencing_context(context)
        candidates = bundle.battle_round_start_hook_registry.candidates_for(context)
    elif kind is TimingTriggerKind.START_PHASE and phase is BattlePhase.COMMAND:
        authority = command_start_timing_context(
            state, battle_round=state.battle_round, active_player_id=active
        )
        candidates = command_start_candidates(
            CommandPhaseStartEffectContext(
                state=state,
                decisions=decisions,
                active_player_id=active,
                runtime_modifier_registry=bundle.runtime_modifier_registry,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            ),
            bundle.command_phase_start_hook_registry,
        )
    elif kind is TimingTriggerKind.START_PHASE and phase is BattlePhase.FIGHT:
        authority = phase_start_context(state)
        candidates = bundle.fight_phase_start_hook_registry.candidates_for(
            FightPhaseStartRequestContext(
                state=state,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
                runtime_modifier_registry=bundle.runtime_modifier_registry,
            )
        )
    elif kind is TimingTriggerKind.START_PHASE and phase is BattlePhase.SHOOTING:
        authority = phase_start_context(state)
        candidates = bundle.shooting_phase_start_hook_registry.candidates_for(
            ShootingPhaseStartRequestContext(
                state=state,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
                runtime_modifier_registry=bundle.runtime_modifier_registry,
                shooting_target_restriction_hooks=bundle.shooting_target_restriction_hook_registry,
            )
        )
    elif (
        kind is TimingTriggerKind.END_TURN
        and batch.context.timing_window.descriptor.source_step == "mission_rules"
    ):
        from warhammer40k_core.engine.mission_turn_end_sequencing import (
            mission_turn_end_candidates,
            mission_turn_end_context,
        )

        authority = mission_turn_end_context(state)
        candidates = mission_turn_end_candidates(
            state=state,
            decisions=decisions,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
        )
    elif kind in (TimingTriggerKind.END_PHASE, TimingTriggerKind.END_TURN):
        authority = boundary_context(state, kind)
        candidates = compose_core_end_rule_registry(
            bundle.turn_end_hook_registry, bundle.phase_end_objective_control_hook_registry
        ).candidates_for(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=phase,
                trigger_kind=kind,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
                runtime_modifier_registry=bundle.runtime_modifier_registry,
                reaction_queue=reaction_queue,
            )
        )
    else:
        authority = (
            boundary_context(state, kind)
            if kind is TimingTriggerKind.END_BATTLE_ROUND
            else phase_start_context(state)
            if kind is TimingTriggerKind.START_PHASE
            else start_turn_context(state)
        )
        candidates = runtime_timing_candidates(
            state=state,
            decisions=decisions,
            window=authority.timing_window,
            index=bundle.event_index,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            resolution_order=("non_mission_rules", "mission_rules")
            if kind is TimingTriggerKind.END_BATTLE_ROUND
            else (),
        )
    if batch.context != authority:
        raise GameLifecycleError("Boundary sequencing source context drift.")
    current = {
        candidate.participant.participant_id: candidate.participant for candidate in candidates
    }
    if len(current) != len(candidates) or any(
        current.get(participant.participant_id) != participant
        for participant in batch.participants
        if participant.participant_id not in batch.completed_participant_ids
    ):
        raise GameLifecycleError("Boundary sequencing source candidate authority drift.")
    if (
        batch.generation == 0
        and not batch.completed_participant_ids
        and (set(current) != {participant.participant_id for participant in batch.participants})
    ):
        raise GameLifecycleError("Boundary sequencing original source population drift.")
