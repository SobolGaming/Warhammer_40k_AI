from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.boundary_rule_flow import (
    prepare_phase_end_boundary,
    request_end_rules,
)
from warhammer40k_core.engine.boundary_sequencing import boundary_context, start_turn_context
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    apply_any_phase_once_per_battle_result,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_turn_end_sequencing import request_mission_turn_end_rules
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PhaseHandler,
)
from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_turn_start_evidence_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.primary_mission_action_interruptions import (
    reconcile_primary_mission_action_interruptions,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.runtime_timing_sequencing import resolve_runtime_timing_window
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlHookRegistry,
)
from warhammer40k_core.engine.timing_window_events import record_timing_window_boundary
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookRegistry,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedHookRegistry,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


_END_WINDOW_RESOLUTION_ORDER = ("non_mission_rules", "mission_rules")


class BattleRoundFlow:
    def __init__(
        self,
        *,
        phase_handlers: Mapping[BattlePhase, PhaseHandler],
        battle_round_start_hooks: BattleRoundStartHookRegistry | None = None,
        turn_end_hooks: TurnEndHookRegistry | None = None,
        phase_end_objective_control_hooks: PhaseEndObjectiveControlHookRegistry | None = None,
        unit_destroyed_hooks: UnitDestroyedHookRegistry | None = None,
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
        runtime_event_index: RuntimeContentEventIndex | None = None,
        ruleset_descriptor: RulesetDescriptor | None = None,
        army_catalog: ArmyCatalog | None = None,
    ) -> None:
        self._phase_handlers = dict(phase_handlers)
        self._battle_round_start_hooks = (
            BattleRoundStartHookRegistry.empty()
            if battle_round_start_hooks is None
            else battle_round_start_hooks
        )
        self._turn_end_hooks = (
            TurnEndHookRegistry.empty() if turn_end_hooks is None else turn_end_hooks
        )
        self._phase_end_objective_control_hooks = (
            PhaseEndObjectiveControlHookRegistry.empty()
            if phase_end_objective_control_hooks is None
            else phase_end_objective_control_hooks
        )
        from warhammer40k_core.engine.boundary_rule_flow import (
            compose_core_end_rule_registry,
        )

        self._turn_end_hooks = compose_core_end_rule_registry(
            self._turn_end_hooks, self._phase_end_objective_control_hooks
        )
        self._unit_destroyed_hooks = (
            UnitDestroyedHookRegistry.empty()
            if unit_destroyed_hooks is None
            else unit_destroyed_hooks
        )
        self._runtime_modifier_registry = (
            RuntimeModifierRegistry.empty()
            if runtime_modifier_registry is None
            else runtime_modifier_registry
        )
        self._runtime_event_index = (
            RuntimeContentEventIndex.empty() if runtime_event_index is None else runtime_event_index
        )
        self._ruleset_descriptor = ruleset_descriptor
        self._army_catalog = army_catalog
        if type(self._battle_round_start_hooks) is not BattleRoundStartHookRegistry:
            raise GameLifecycleError("BattleRoundFlow requires a battle-round start hook registry.")
        if type(self._turn_end_hooks) is not TurnEndHookRegistry:
            raise GameLifecycleError("BattleRoundFlow requires a turn-end hook registry.")
        if (
            type(self._phase_end_objective_control_hooks)
            is not PhaseEndObjectiveControlHookRegistry
        ):
            raise GameLifecycleError(
                "BattleRoundFlow requires a phase-end objective-control hook registry."
            )
        if type(self._unit_destroyed_hooks) is not UnitDestroyedHookRegistry:
            raise GameLifecycleError("BattleRoundFlow requires a unit-destroyed hook registry.")
        if type(self._runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError("BattleRoundFlow requires a runtime modifier registry.")
        if type(self._runtime_event_index) is not RuntimeContentEventIndex:
            raise GameLifecycleError("BattleRoundFlow requires a runtime event index.")
        if self._ruleset_descriptor is not None and type(self._ruleset_descriptor) is not (
            RulesetDescriptor
        ):
            raise GameLifecycleError("BattleRoundFlow ruleset_descriptor must be a descriptor.")
        if self._army_catalog is not None and type(self._army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("BattleRoundFlow army_catalog must be an ArmyCatalog.")

    def advance(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("BattleRoundFlow can advance only during battle.")
        current_phase = state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("BattleRoundFlow requires a current battle phase.")

        from warhammer40k_core.engine.model_destruction_triggers import (
            advance_model_destruction_triggers,
        )

        destruction_status = advance_model_destruction_triggers(
            state=state,
            decisions=decisions,
            registry=self._unit_destroyed_hooks,
        )
        if destruction_status is not None:
            return destruction_status
        handler = self._phase_handlers.get(current_phase)
        if handler is None:
            raise GameLifecycleError("BattleRoundFlow missing handler for current battle phase.")
        start_request = (
            self._battle_round_start_hooks.next_request_for(
                BattleRoundStartRequestContext(state=state, decisions=decisions)
            )
            if _is_start_of_battle_round(state)
            else None
        )
        if start_request is not None:
            decisions.request_decision(start_request)
            decisions.event_log.append(
                "battle_round_start_faction_rule_requested",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "request_id": start_request.request_id,
                    "decision_type": start_request.decision_type,
                    "actor_id": start_request.actor_id,
                },
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=start_request,
                payload={
                    "battle_round": state.battle_round,
                    "phase_body_status": "battle_round_start_faction_rule_required",
                    "request_id": start_request.request_id,
                },
            )
        timing_status = _emit_start_timing_windows(
            state=state,
            decisions=decisions,
            runtime_event_index=self._runtime_event_index,
            runtime_modifier_registry=self._runtime_modifier_registry,
            ruleset_descriptor=self._ruleset_descriptor,
            army_catalog=self._army_catalog,
        )
        if timing_status is not None:
            return timing_status
        pending_start_request = _pending_decision_request(decisions)
        if pending_start_request is not None:
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=pending_start_request,
                payload={
                    "battle_round": state.battle_round,
                    "phase": current_phase.value,
                    "phase_body_status": "start_timing_window_decision_required",
                    "request_id": pending_start_request.request_id,
                },
            )
        _emit_phase_start_objective_proximity_snapshot_if_available(
            state=state,
            decisions=decisions,
            registry=self._phase_end_objective_control_hooks,
            runtime_modifier_registry=self._runtime_modifier_registry,
        )
        status = handler.begin_phase(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
        )
        reconcile_primary_mission_action_interruptions(
            state=state,
            decisions=decisions,
        )
        if status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
            return status
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            return status
        if status.status_kind is LifecycleStatusKind.INVALID:
            return status
        if (
            status.status_kind is LifecycleStatusKind.UNSUPPORTED
            and not _is_placeholder_noop_status(status)
        ):
            return status

        from warhammer40k_core.engine.model_destruction_triggers import (
            record_model_destruction_occurrences,
        )
        from warhammer40k_core.engine.rule_trigger_state import rule_trigger_history

        record_model_destruction_occurrences(
            state=state, decisions=decisions, registry=self._unit_destroyed_hooks
        )
        if rule_trigger_history(decisions).ready():
            return LifecycleStatus.advanced(
                stage=state.stage,
                payload={"phase_body_status": "deferred_rules_ready"},
            )

        prepare_phase_end_boundary(
            state=state,
            decisions=decisions,
            runtime_modifier_registry=self._runtime_modifier_registry,
        )
        timing_status = request_end_rules(
            state=state,
            decisions=decisions,
            registry=self._turn_end_hooks,
            trigger_kind=TimingTriggerKind.END_PHASE,
            ruleset_descriptor=self._ruleset_descriptor,
            army_catalog=self._army_catalog,
            runtime_modifier_registry=self._runtime_modifier_registry,
            reaction_queue=reaction_queue,
        )
        if timing_status is not None:
            return timing_status
        from warhammer40k_core.engine.fight_phase_end_sequencing import (
            complete_fight_phase_boundary,
        )

        complete_fight_phase_boundary(state=state, decisions=decisions)
        record_timing_window_boundary(
            decisions=decisions,
            window=boundary_context(state, TimingTriggerKind.END_PHASE).timing_window,
            completed=True,
            resolution_order=_END_WINDOW_RESOLUTION_ORDER,
        )
        if _is_end_of_player_turn(state):
            turn_status = request_end_rules(
                state=state,
                decisions=decisions,
                registry=self._turn_end_hooks,
                trigger_kind=TimingTriggerKind.END_TURN,
                ruleset_descriptor=self._ruleset_descriptor,
                army_catalog=self._army_catalog,
                runtime_modifier_registry=self._runtime_modifier_registry,
                reaction_queue=reaction_queue,
            )
            if turn_status is not None:
                return turn_status
        objective_control_record_ids_before_advance = {
            record.record_id for record in state.objective_control_records
        }
        departure_ids_before_advance = tuple(
            value.departure_id for value in state.primary_battlefield_departure_states
        )
        destruction_ids_before_advance = tuple(
            value.destruction_id for value in state.primary_unit_destruction_states
        )
        objective_state_ids_before_advance = tuple(
            value.state_id for value in state.primary_objective_turn_start_states
        )
        snapshot_ids_before_advance = tuple(
            value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
        )
        if _is_end_of_player_turn(state):
            turn_end_record = state.prepare_current_turn_end_boundary(
                completed_phase=current_phase,
                runtime_modifier_registry=self._runtime_modifier_registry,
            )
            _emit_objective_control_boundary_event_if_missing(
                decisions=decisions,
                record=turn_end_record,
            )
            record_new_primary_battlefield_departure_events(
                state=state,
                event_log=decisions.event_log,
                departure_ids_before=departure_ids_before_advance,
            )
            record_new_primary_unit_destruction_events(
                state=state,
                event_log=decisions.event_log,
                destruction_ids_before=destruction_ids_before_advance,
            )
            reconcile_primary_mission_action_interruptions(
                state=state,
                decisions=decisions,
            )
            departure_ids_before_advance = tuple(
                value.departure_id for value in state.primary_battlefield_departure_states
            )
            destruction_ids_before_advance = tuple(
                value.destruction_id for value in state.primary_unit_destruction_states
            )
            mission_status = request_mission_turn_end_rules(
                state=state,
                decisions=decisions,
                runtime_modifier_registry=self._runtime_modifier_registry,
            )
            if mission_status is not None:
                return mission_status
        round_end_window: TimingWindow | None = None
        if _is_end_of_player_turn(state):
            record_timing_window_boundary(
                decisions=decisions,
                window=boundary_context(state, TimingTriggerKind.END_TURN).timing_window,
                completed=True,
                resolution_order=_END_WINDOW_RESOLUTION_ORDER,
            )
            if state.active_player_id == state.turn_order[-1]:
                round_end_window = boundary_context(
                    state, TimingTriggerKind.END_BATTLE_ROUND
                ).timing_window
                round_status = resolve_runtime_timing_window(
                    state=state,
                    decisions=decisions,
                    window=round_end_window,
                    index=self._runtime_event_index,
                    runtime_modifier_registry=self._runtime_modifier_registry,
                    ruleset_descriptor=self._ruleset_descriptor,
                    army_catalog=self._army_catalog,
                    resolution_order=_END_WINDOW_RESOLUTION_ORDER,
                    complete_window=False,
                )
                if round_status is not None:
                    return round_status
        completed_phase = state.advance_to_next_battle_phase(
            runtime_modifier_registry=self._runtime_modifier_registry,
            event_log=decisions.event_log,
        )
        if round_end_window is not None:
            record_timing_window_boundary(
                decisions=decisions,
                window=round_end_window,
                completed=True,
                resolution_order=_END_WINDOW_RESOLUTION_ORDER,
            )
        record_new_primary_battlefield_departure_events(
            state=state,
            event_log=decisions.event_log,
            departure_ids_before=departure_ids_before_advance,
        )
        record_new_primary_unit_destruction_events(
            state=state,
            event_log=decisions.event_log,
            destruction_ids_before=destruction_ids_before_advance,
        )
        record_new_primary_turn_start_evidence_events(
            state=state,
            event_log=decisions.event_log,
            objective_state_ids_before=objective_state_ids_before_advance,
            snapshot_ids_before=snapshot_ids_before_advance,
        )
        turn_end_records = tuple(
            record
            for record in state.objective_control_records
            if record.record_id not in objective_control_record_ids_before_advance
            and record.timing is ObjectiveControlTiming.TURN_END
        )
        if len(turn_end_records) > 1:
            raise GameLifecycleError(
                "Battle phase advance produced multiple turn-end objective-control records."
            )
        if turn_end_records:
            _emit_objective_control_boundary_event_if_missing(
                decisions=decisions,
                record=turn_end_records[0],
            )
        decisions.event_log.append(
            "battle_phase_completed",
            {
                "game_id": state.game_id,
                "completed_phase": completed_phase.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "next_phase": _current_battle_phase_payload(state),
                "phase_body_status": _phase_body_status(status),
            },
        )
        if _state_is_complete(state):
            decisions.event_log.append(
                "game_completed",
                state.game_result_payload(),
            )
            return LifecycleStatus.terminal(
                stage=GameLifecycleStage.COMPLETE,
                message="Game ended after configured battle rounds.",
                payload=state.game_result_payload(),
            )
        if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
            return LifecycleStatus.unsupported(
                stage=GameLifecycleStage.BATTLE,
                message="Phase body is a Phase 9B placeholder.",
                payload={
                    "completed_phase": completed_phase.value,
                    "phase_body_status": _phase_body_status(status),
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "current_phase": _current_battle_phase_payload(state),
                },
            )
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "completed_phase": completed_phase.value,
                "phase_body_status": _phase_body_status(status),
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "current_phase": _current_battle_phase_payload(state),
            },
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> None:
        if result.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE:
            apply_any_phase_once_per_battle_result(
                state=state,
                decisions=decisions,
                request=decisions.record_for_result(result).request,
                result=result,
            )
            return
        if result.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
            if result.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE:
                raise GameLifecycleError("BattleRoundFlow received unsupported decision_type.")
            if self._turn_end_hooks.apply_result(
                TurnEndResultContext(
                    state=state,
                    decisions=decisions,
                    request=decisions.record_for_result(result).request,
                    result=result,
                )
            ):
                return
            raise GameLifecycleError("Faction rule turn-end decision was not handled.")
        if self._battle_round_start_hooks.apply_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=decisions.record_for_result(result).request,
                result=result,
            )
        ):
            return
        raise GameLifecycleError("Faction rule battle-round decision was not handled.")


def _current_battle_phase_payload(state: GameState) -> str | None:
    current_phase = state.current_battle_phase
    if current_phase is None:
        return None
    return current_phase.value


def _is_start_of_battle_round(state: GameState) -> bool:
    return (
        state.stage is GameLifecycleStage.BATTLE
        and state.current_battle_phase is BattlePhase.COMMAND
        and state.battle_phase_index == 0
        and bool(state.turn_order)
        and state.active_player_id == state.turn_order[0]
    )


def _is_end_of_player_turn(state: GameState) -> bool:
    return state.battle_phase_index is not None and state.battle_phase_index + 1 == len(
        state.battle_phase_sequence
    )


def _emit_objective_control_boundary_event_if_missing(
    *,
    decisions: DecisionController,
    record: ObjectiveControlRecord,
) -> None:
    if any(
        event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload.get("record_ids") == [record.record_id]
        for event in decisions.event_log.records
    ):
        return
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )


def _state_is_complete(state: GameState) -> bool:
    return state.stage is GameLifecycleStage.COMPLETE


def _pending_decision_request(decisions: DecisionController) -> DecisionRequest | None:
    pending_requests = decisions.queue.pending_requests
    return pending_requests[0] if pending_requests else None


def _is_placeholder_noop_status(status: LifecycleStatus) -> bool:
    return _phase_body_status(status) == "placeholder_noop"


def _phase_body_status(status: LifecycleStatus) -> str:
    payload = status.payload
    if isinstance(payload, dict):
        value = payload.get("phase_body_status")
        if type(value) is str:
            return value
    return "complete"


def _emit_start_timing_windows(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_event_index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> LifecycleStatus | None:
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Start timing windows require a current battle phase.")
    battle_phase_index = state.battle_phase_index
    if battle_phase_index is None:
        raise GameLifecycleError("Start timing windows require a battle phase index.")
    if battle_phase_index == 0:
        status = resolve_runtime_timing_window(
            state=state,
            decisions=decisions,
            window=start_turn_context(state).timing_window,
            index=runtime_event_index,
            runtime_modifier_registry=runtime_modifier_registry,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
        if status is not None:
            return status
    if current_phase in (BattlePhase.COMMAND, BattlePhase.FIGHT, BattlePhase.SHOOTING):
        return None
    status = resolve_runtime_timing_window(
        state=state,
        decisions=decisions,
        window=phase_start_context(state).timing_window,
        index=runtime_event_index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if status is not None:
        return status
    return None


def _emit_phase_start_objective_proximity_snapshot_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: PhaseEndObjectiveControlHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    if type(registry) is not PhaseEndObjectiveControlHookRegistry:
        raise GameLifecycleError("Objective proximity snapshot requires a registry.")
    if not registry.all_bindings():
        return
    if state.mission_setup is None or state.battlefield_state is None:
        return
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Objective proximity snapshot requires a current phase.")
    active_player_id = _active_player_id(state)
    snapshot_id = (
        f"objective-proximity:{state.game_id}:round-{state.battle_round:02d}:"
        f"turn:{active_player_id}:phase:{current_phase.value}:start"
    )
    if _event_with_payload_id_exists(
        decisions=decisions,
        event_type="objective_marker_phase_start_proximity_snapshot",
        key="snapshot_id",
        value=snapshot_id,
    ):
        return
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=current_phase,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    objective_ids_by_unit: dict[str, set[str]] = {}
    for result in record.results:
        for contribution in result.contributors:
            objective_ids_by_unit.setdefault(contribution.unit_instance_id, set()).add(
                result.objective_id
            )
    decisions.event_log.append(
        "objective_marker_phase_start_proximity_snapshot",
        {
            "snapshot_id": snapshot_id,
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": current_phase.value,
            "objective_ids_by_unit_instance_id": {
                unit_id: sorted(objective_ids)
                for unit_id, objective_ids in sorted(objective_ids_by_unit.items())
            },
            "removed_model_ids": sorted(state.battlefield_state.removed_model_ids),
            "source_objective_control_record": record.to_payload(),
        },
    )


def _event_with_payload_id_exists(
    *,
    decisions: DecisionController,
    event_type: str,
    key: str,
    value: str,
) -> bool:
    for record in decisions.event_log.records:
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get(key) == value:
            return True
    return False


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("BattleRoundFlow requires an active player.")
    return state.active_player_id


_validate_identifier = IdentifierValidator(GameLifecycleError)
