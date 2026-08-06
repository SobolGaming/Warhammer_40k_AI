# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import Protocol

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.battlefield_state import ModelPlacementRecord
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
    apply_recorded_catalog_model_materialization_placement,
    invalid_catalog_model_materialization_placement_status,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.events import RuntimeContentEvent
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

PARAMETERIZED_DECISION_TYPES = frozenset(
    (SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,)
)


class MaterializationDecisionLifecycleHost(Protocol):
    decision_controller: DecisionController
    reaction_queue: ReactionQueue
    _runtime_content_bundle: RuntimeContentBundle | None
    _shooting_phase_handler: ShootingPhaseHandler

    def _require_state(self) -> GameState: ...

    def _require_config(self) -> GameConfig: ...

    def _result_resolves_active_reaction_frame(self, result: DecisionResult) -> bool: ...

    def _continue_or_resolve_fight_reaction(
        self,
        *,
        result: DecisionResult,
        status: LifecycleStatus,
    ) -> None: ...

    def advance_until_decision_or_terminal(self) -> LifecycleStatus: ...


def decision_dispatch_handlers(
    host: MaterializationDecisionLifecycleHost,
) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validator(
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        config = host._require_config()
        bundle = _require_runtime_content_bundle(host)
        if host._result_resolves_active_reaction_frame(result):
            host.reaction_queue.validate_result(result)
        return invalid_catalog_model_materialization_placement_status(
            state=host._require_state(),
            request=request,
            result=result,
            decisions=host.decision_controller,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )

    def applier(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        state = host._require_state()
        config = host._require_config()
        bundle = _require_runtime_content_bundle(host)
        resolves_reaction_frame = host._result_resolves_active_reaction_frame(result)
        action_phase = _request_phase_kind(record.request, "action_phase")
        placements = apply_recorded_catalog_model_materialization_placement(
            state=state,
            decisions=host.decision_controller,
            request=record.request,
            result=result,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )
        _dispatch_model_placed_events(
            state=state,
            config=config,
            decisions=host.decision_controller,
            runtime_content_bundle=host._runtime_content_bundle,
            source_unit_instance_id=_source_unit_instance_id(record.request),
            request_id=record.request.request_id,
            action_phase=_request_phase(record.request, "action_phase"),
            parent_battle_phase=_request_phase(record.request, "parent_battle_phase"),
            placements=placements,
            runtime_modifier_registry=host._shooting_phase_handler.runtime_modifier_registry,
        )
        advanced_status = host.advance_until_decision_or_terminal()
        if resolves_reaction_frame:
            _continue_or_resolve_materialization_reaction(
                host=host,
                result=result,
                status=advanced_status,
                action_phase=action_phase,
            )
        return advanced_status

    return (
        DecisionDispatchHandler(
            decision_type=SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
            pre_validator=pre_validator,
            applier=applier,
        ),
    )


def _continue_or_resolve_materialization_reaction(
    *,
    host: MaterializationDecisionLifecycleHost,
    result: DecisionResult,
    status: LifecycleStatus,
    action_phase: BattlePhase,
) -> None:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Catalog materialization reaction requires DecisionResult.")
    if type(status) is not LifecycleStatus:
        raise GameLifecycleError("Catalog materialization reaction requires LifecycleStatus.")
    if type(action_phase) is not BattlePhase:
        raise GameLifecycleError("Catalog materialization reaction requires BattlePhase.")
    if action_phase is BattlePhase.FIGHT:
        host._continue_or_resolve_fight_reaction(result=result, status=status)
        return
    if action_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("Catalog materialization reaction action phase drift.")
    if host._require_state().out_of_phase_shooting_state is not None:
        if status.decision_request is None:
            raise GameLifecycleError(
                "Out-of-phase materialization continuation requires a pending decision."
            )
        host.reaction_queue.continue_reaction(
            result=result,
            next_request_id=status.decision_request.request_id,
            decisions=host.decision_controller,
        )
        return
    host.reaction_queue.resolve_reaction(result=result, decisions=host.decision_controller)


def _dispatch_model_placed_events(
    *,
    state: GameState,
    config: GameConfig,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle | None,
    source_unit_instance_id: str,
    request_id: str,
    action_phase: str,
    parent_battle_phase: str,
    placements: tuple[ModelPlacementRecord, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    if runtime_content_bundle is None:
        return
    phase = (
        None
        if state.current_battle_phase is None
        else battle_phase_kind_from_token(state.current_battle_phase.value)
    )
    for placement in placements:
        for player_id in config.player_ids:
            event = RuntimeContentEvent(
                event_id=(f"{request_id}:placed:{placement.model_instance_id}:{player_id}"),
                game_id=state.game_id,
                player_id=player_id,
                battle_round=state.battle_round,
                trigger_kind=TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD,
                phase=phase,
                active_player_id=state.active_player_id,
                source_unit_instance_id=source_unit_instance_id,
                target_unit_instance_ids=(source_unit_instance_id,),
                event_payload=validate_json_value(
                    {
                        "placement_kind": "split_unit",
                        "source_phase": parent_battle_phase,
                        "action_phase": action_phase,
                        "parent_battle_phase": parent_battle_phase,
                        "model_instance_id": placement.model_instance_id,
                        "model_placement_record": placement.to_payload(),
                        "request_id": request_id,
                    }
                ),
            )
            for resolved in runtime_content_bundle.event_index.dispatch(
                event,
                state=state,
                decisions=decisions,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
                runtime_modifier_registry=runtime_modifier_registry,
            ):
                decisions.event_log.append(
                    "runtime_content_event_resolved",
                    {
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "player_id": player_id,
                        "trigger_kind": event.trigger_kind.value,
                        "runtime_event": event.to_payload(),
                        "result": resolved.to_payload(),
                    },
                )


def _source_unit_instance_id(request: DecisionRequest) -> str:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Materialization request payload is invalid.")
    value = payload.get("source_unit_instance_id")
    if type(value) is not str or not value:
        raise GameLifecycleError("Materialization request source unit is invalid.")
    return value


def _request_phase(request: DecisionRequest, key: str) -> str:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Materialization request payload is invalid.")
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Materialization request {key} is invalid.")
    return value


def _request_phase_kind(request: DecisionRequest, key: str) -> BattlePhase:
    value = _request_phase(request, key)
    try:
        return BattlePhase(value)
    except ValueError as exc:
        raise GameLifecycleError(f"Materialization request {key} is unsupported.") from exc


def _require_runtime_content_bundle(
    host: MaterializationDecisionLifecycleHost,
) -> RuntimeContentBundle:
    bundle = host._runtime_content_bundle
    if bundle is None:
        raise GameLifecycleError("Materialization decision requires runtime content.")
    return bundle


__all__ = (
    "PARAMETERIZED_DECISION_TYPES",
    "MaterializationDecisionLifecycleHost",
    "decision_dispatch_handlers",
)
