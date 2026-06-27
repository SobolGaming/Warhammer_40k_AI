from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
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
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookRegistry,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookRegistry,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


_LIFECYCLE_TIMING_RULE_ID = "core-rules-lifecycle-timing"
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

        handler = self._phase_handlers.get(current_phase)
        if handler is None:
            raise GameLifecycleError("BattleRoundFlow missing handler for current battle phase.")
        _emit_start_timing_windows(
            state=state,
            decisions=decisions,
            runtime_event_index=self._runtime_event_index,
            runtime_modifier_registry=self._runtime_modifier_registry,
            ruleset_descriptor=self._ruleset_descriptor,
            army_catalog=self._army_catalog,
        )
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

        _emit_end_timing_windows(
            state=state,
            decisions=decisions,
            runtime_event_index=self._runtime_event_index,
            runtime_modifier_registry=self._runtime_modifier_registry,
            ruleset_descriptor=self._ruleset_descriptor,
            army_catalog=self._army_catalog,
        )
        _apply_phase_end_objective_control_hooks(
            state=state,
            decisions=decisions,
            registry=self._phase_end_objective_control_hooks,
            runtime_modifier_registry=self._runtime_modifier_registry,
        )
        _apply_phase_end_unit_destroyed_hooks(
            state=state,
            decisions=decisions,
            registry=self._unit_destroyed_hooks,
        )
        turn_end_request = self._turn_end_hooks.next_request_for(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=current_phase,
            )
        )
        if turn_end_request is not None:
            decisions.request_decision(turn_end_request)
            decisions.event_log.append(
                "turn_end_faction_rule_requested",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": _active_player_id(state),
                    "phase": current_phase.value,
                    "request_id": turn_end_request.request_id,
                    "decision_type": turn_end_request.decision_type,
                    "actor_id": turn_end_request.actor_id,
                },
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=turn_end_request,
                payload={
                    "battle_round": state.battle_round,
                    "phase": current_phase.value,
                    "phase_body_status": "turn_end_faction_rule_required",
                    "request_id": turn_end_request.request_id,
                },
            )
        completed_phase = state.advance_to_next_battle_phase(
            runtime_modifier_registry=self._runtime_modifier_registry
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


def _state_is_complete(state: GameState) -> bool:
    return state.stage is GameLifecycleStage.COMPLETE


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
) -> None:
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Start timing windows require a current battle phase.")
    battle_phase_index = state.battle_phase_index
    if battle_phase_index is None:
        raise GameLifecycleError("Start timing windows require a battle phase index.")
    active_player_id = _active_player_id(state)
    if battle_phase_index == 0 and active_player_id == state.turn_order[0]:
        _emit_timing_window_if_missing(
            state=state,
            decisions=decisions,
            trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
            active_player_id=None,
            phase=None,
            source_step="battle_round",
            window_id=(
                f"timing-window:{state.game_id}:round-{state.battle_round:02d}:battle-round:start"
            ),
            runtime_event_index=runtime_event_index,
            runtime_modifier_registry=runtime_modifier_registry,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
    if battle_phase_index == 0:
        _emit_timing_window_if_missing(
            state=state,
            decisions=decisions,
            trigger_kind=TimingTriggerKind.START_TURN,
            active_player_id=active_player_id,
            phase=None,
            source_step="player_turn",
            window_id=(
                f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
                f"turn:{active_player_id}:start"
            ),
            runtime_event_index=runtime_event_index,
            runtime_modifier_registry=runtime_modifier_registry,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=active_player_id,
        phase=current_phase,
        source_step=current_phase.value,
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:phase:{current_phase.value}:start"
        ),
        runtime_event_index=runtime_event_index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )


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


def _emit_end_timing_windows(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_event_index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> None:
    completed_phase = state.current_battle_phase
    if completed_phase is None:
        raise GameLifecycleError("End timing windows require a current battle phase.")
    battle_phase_index = state.battle_phase_index
    if battle_phase_index is None:
        raise GameLifecycleError("End timing windows require a battle phase index.")
    active_player_id = _active_player_id(state)
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_PHASE,
        active_player_id=active_player_id,
        phase=completed_phase,
        source_step=completed_phase.value,
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:phase:{completed_phase.value}:end"
        ),
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
        runtime_event_index=runtime_event_index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if battle_phase_index + 1 < len(state.battle_phase_sequence):
        return
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_TURN,
        active_player_id=active_player_id,
        phase=None,
        source_step="player_turn",
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:end"
        ),
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
        runtime_event_index=runtime_event_index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if state.turn_order.index(active_player_id) + 1 < len(state.turn_order):
        return
    _emit_timing_window_if_missing(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
        active_player_id=None,
        phase=None,
        source_step="battle_round",
        window_id=(
            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:battle-round:end"
        ),
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
        runtime_event_index=runtime_event_index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )


def _apply_phase_end_objective_control_hooks(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: PhaseEndObjectiveControlHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    if type(registry) is not PhaseEndObjectiveControlHookRegistry:
        raise GameLifecycleError("Phase-end objective-control hooks require a registry.")
    if not registry.all_bindings():
        return
    completed_phase = state.current_battle_phase
    if completed_phase is None:
        raise GameLifecycleError("Phase-end objective-control hooks require a current phase.")
    context = PhaseEndObjectiveControlContext(
        state=state,
        event_log=decisions.event_log,
        completed_phase=completed_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    for sticky_state in registry.states_for(context):
        if _sticky_objective_control_state_exists(state=state, state_id=sticky_state.state_id):
            continue
        state.record_sticky_objective_control_state(sticky_state)
        decisions.event_log.append(
            "sticky_objective_control_state_recorded",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": completed_phase.value,
                "sticky_objective_control_state": sticky_state.to_payload(),
            },
        )


def _sticky_objective_control_state_exists(*, state: GameState, state_id: str) -> bool:
    requested_state_id = _validate_identifier("sticky_objective_control_state_id", state_id)
    return any(
        sticky_state.state_id == requested_state_id
        for sticky_state in state.sticky_objective_control_states
    )


def _apply_phase_end_unit_destroyed_hooks(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: UnitDestroyedHookRegistry,
) -> None:
    if type(registry) is not UnitDestroyedHookRegistry:
        raise GameLifecycleError("Unit-destroyed hooks require a registry.")
    if not registry.all_bindings():
        return
    completed_phase = state.current_battle_phase
    if completed_phase is None:
        raise GameLifecycleError("Unit-destroyed hooks require a current phase.")
    for event_id, payload in _unit_destruction_completion_events_for_phase(
        state=state,
        decisions=decisions,
        completed_phase=completed_phase,
    ):
        destroying_player_id = _payload_string(payload, key="destroying_player_id")
        destroyed_unit_id = _payload_string(payload, key="target_unit_instance_id")
        destroyed_player_id = _player_id_for_unit(state=state, unit_instance_id=destroyed_unit_id)
        if destroying_player_id == destroyed_player_id:
            continue
        registry.resolve(
            UnitDestroyedContext(
                state=state,
                decisions=decisions,
                completed_phase=completed_phase,
                model_destroyed_event_id=event_id,
                model_destroyed_payload=payload,
                destroying_player_id=destroying_player_id,
                destroyed_unit_instance_id=destroyed_unit_id,
                destroyed_player_id=destroyed_player_id,
            )
        )


def _unit_destruction_completion_events_for_phase(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    if state.battlefield_state is None:
        return ()
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    events_by_unit: dict[str, list[tuple[int, str, dict[str, JsonValue]]]] = {}
    for event_order, record in enumerate(decisions.event_log.records):
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        event_payload = validate_json_value(payload)
        if not isinstance(event_payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        if event_payload.get("game_id") != state.game_id:
            continue
        if event_payload.get("battle_round") != state.battle_round:
            continue
        if event_payload.get("active_player_id") != state.active_player_id:
            continue
        if event_payload.get("phase") != completed_phase.value:
            continue
        target_unit_id = _payload_string(event_payload, key="target_unit_instance_id")
        events_by_unit.setdefault(target_unit_id, []).append(
            (event_order, record.event_id, dict(event_payload))
        )
    completions: list[tuple[int, str, dict[str, JsonValue]]] = []
    for target_unit_id, events in events_by_unit.items():
        model_ids = _model_instance_ids_for_unit(state=state, unit_instance_id=target_unit_id)
        if not model_ids:
            continue
        if not model_ids <= removed_model_ids:
            continue
        completions.append(sorted(events, key=lambda item: item[0])[-1])
    return tuple((event_id, payload) for _order, event_id, payload in sorted(completions))


def _player_id_for_unit(*, state: GameState, unit_instance_id: str) -> str:
    requested_unit = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        if any(unit.unit_instance_id == requested_unit for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Unit owner lookup failed for unit-destroyed hook.")


def _model_instance_ids_for_unit(*, state: GameState, unit_instance_id: str) -> set[str]:
    requested_unit = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit:
                return {model.model_instance_id for model in unit.own_models}
    raise GameLifecycleError("Model lookup failed for unit-destroyed hook.")


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Unit-destroyed event payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _emit_timing_window_if_missing(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger_kind: TimingTriggerKind,
    active_player_id: str | None,
    phase: BattlePhase | None,
    source_step: str,
    window_id: str,
    resolution_order: tuple[str, ...] = (),
    runtime_event_index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> None:
    if _timing_window_event_exists(
        decisions=decisions,
        event_type="timing_window_resolved",
        window_id=window_id,
    ):
        return
    window = TimingWindow(
        window_id=window_id,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{window_id}:descriptor",
            trigger_kind=trigger_kind,
            source_rule_id=_LIFECYCLE_TIMING_RULE_ID,
            phase=phase,
            source_step=source_step,
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=phase,
    )
    payload_value = validate_json_value(
        {
            "timing_window": window.to_payload(),
            "resolution_order": list(resolution_order),
        }
    )
    if not isinstance(payload_value, dict):
        raise GameLifecycleError("Timing window payload must be an object.")
    payload = payload_value
    decisions.event_log.append("timing_window_opened", payload)
    decisions.event_log.append("timing_window_resolved", payload)
    _dispatch_runtime_timing_window_event(
        state=state,
        decisions=decisions,
        runtime_event_index=runtime_event_index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        trigger_kind=trigger_kind,
        active_player_id=active_player_id,
        phase=phase,
        window_payload=payload,
    )


def _dispatch_runtime_timing_window_event(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_event_index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
    trigger_kind: TimingTriggerKind,
    active_player_id: str | None,
    phase: BattlePhase | None,
    window_payload: dict[str, JsonValue],
) -> None:
    if not runtime_event_index.subscriptions_for(trigger_kind):
        return
    if ruleset_descriptor is None:
        raise GameLifecycleError("Runtime timing events require ruleset_descriptor.")
    if army_catalog is None:
        raise GameLifecycleError("Runtime timing events require army_catalog.")
    timing_window_payload = window_payload.get("timing_window")
    if not isinstance(timing_window_payload, dict):
        raise GameLifecycleError("Runtime timing event requires timing_window payload.")
    window_id = _payload_string(timing_window_payload, key="window_id")
    for player_id in _runtime_event_player_ids(state):
        event = RuntimeContentEvent(
            event_id=f"{window_id}:runtime:{player_id}",
            game_id=state.game_id,
            player_id=player_id,
            battle_round=state.battle_round,
            trigger_kind=trigger_kind,
            phase=phase,
            active_player_id=active_player_id,
            event_payload=window_payload,
        )
        for result in runtime_event_index.dispatch(
            event,
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            runtime_modifier_registry=runtime_modifier_registry,
        ):
            decisions.event_log.append(
                "runtime_content_event_resolved",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "player_id": player_id,
                    "trigger_kind": trigger_kind.value,
                    "runtime_event": event.to_payload(),
                    "result": result.to_payload(),
                },
            )


def _runtime_event_player_ids(state: GameState) -> tuple[str, ...]:
    player_ids = tuple(army.player_id for army in state.army_definitions)
    if player_ids:
        return tuple(sorted(player_ids))
    return tuple(sorted(state.player_ids))


def _timing_window_event_exists(
    *,
    decisions: DecisionController,
    event_type: str,
    window_id: str,
) -> bool:
    for record in decisions.event_log.records:
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        timing_window_payload = payload.get("timing_window")
        if not isinstance(timing_window_payload, dict):
            continue
        if timing_window_payload.get("window_id") == window_id:
            return True
    return False


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


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
