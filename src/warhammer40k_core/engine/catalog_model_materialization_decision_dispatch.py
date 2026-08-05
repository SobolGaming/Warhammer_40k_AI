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
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

PARAMETERIZED_DECISION_TYPES = frozenset(
    (SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,)
)


class MaterializationDecisionLifecycleHost(Protocol):
    decision_controller: DecisionController
    _runtime_content_bundle: RuntimeContentBundle | None
    _shooting_phase_handler: ShootingPhaseHandler

    def _require_state(self) -> GameState: ...

    def _require_config(self) -> GameConfig: ...

    def advance_until_decision_or_terminal(self) -> LifecycleStatus: ...


def decision_dispatch_handlers(
    host: MaterializationDecisionLifecycleHost,
) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validator(
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        config = host._require_config()
        return invalid_catalog_model_materialization_placement_status(
            state=host._require_state(),
            request=request,
            result=result,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )

    def applier(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        state = host._require_state()
        config = host._require_config()
        placements = apply_recorded_catalog_model_materialization_placement(
            state=state,
            decisions=host.decision_controller,
            request=record.request,
            result=result,
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
            placements=placements,
            runtime_modifier_registry=host._shooting_phase_handler.runtime_modifier_registry,
        )
        return host.advance_until_decision_or_terminal()

    return (
        DecisionDispatchHandler(
            decision_type=SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
            pre_validator=pre_validator,
            applier=applier,
        ),
    )


def _dispatch_model_placed_events(
    *,
    state: GameState,
    config: GameConfig,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle | None,
    source_unit_instance_id: str,
    request_id: str,
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


__all__ = (
    "PARAMETERIZED_DECISION_TYPES",
    "MaterializationDecisionLifecycleHost",
    "decision_dispatch_handlers",
)
