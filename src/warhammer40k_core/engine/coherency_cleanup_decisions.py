"""Controlling-player casualties at the mandatory turn-end coherency boundary."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Protocol

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_unit_destructions_for_end_turn_cleanup,
)
from warhammer40k_core.engine.rule_model_destruction_unplaced import (
    destroy_end_turn_coherency_models,
)
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.turn_cleanup import resolve_end_turn_cleanup
from warhammer40k_core.engine.unit_coherency import rules_unit_coherency_result

SELECT_COHERENCY_CASUALTY_DECISION_TYPE = "select_coherency_casualty"
COHERENCY_CASUALTY_EVENT = "coherency_cleanup_model_removed"


def cleanup_id_for_state(state: GameState) -> str:
    return (
        f"end-turn-cleanup:{state.game_id}:round-{state.battle_round:02d}:{state.active_player_id}"
    )


def next_coherency_request(*, state: GameState) -> DecisionRequest | None:
    if state.battlefield_state is None or state.active_player_id is None:
        raise GameLifecycleError("Coherency cleanup requires battlefield and active player.")
    phase = state.current_battle_phase
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or phase is None
        or state.battle_phase_index is None
        or state.battle_phase_index + 1 != len(state.battle_phase_sequence)
    ):
        raise GameLifecycleError("Coherency cleanup requires the final battle phase.")
    if any(
        row.completes_boundary
        and row.battle_round == state.battle_round
        and row.active_player_id == state.active_player_id
        and row.phase == phase.value
        for row in state.end_turn_cleanup_states
    ):
        return None
    scenario = BattlefieldScenario(tuple(state.army_definitions), state.battlefield_state)
    descriptor = state.ruleset_descriptor_for_runtime_policy()
    views = sorted(
        rules_unit_views_from_armies(armies=tuple(state.army_definitions)),
        key=lambda view: (view.owner_player_id != state.active_player_id, view.unit_instance_id),
    )
    actor_id: str | None = None
    broken_contexts: list[JsonValue] = []
    model_ids: list[str] = []
    for view in views:
        if not any(
            state.battlefield_state.model_placement_or_none(model.model_instance_id) is not None
            for model in view.alive_models()
        ):
            continue
        result = rules_unit_coherency_result(
            scenario=scenario, ruleset_descriptor=descriptor, rules_unit=view
        )
        if result.is_coherent:
            continue
        if actor_id is not None and view.owner_player_id != actor_id:
            break
        actor_id = view.owner_player_id
        # Bind the finite request to physical geometry, wounds and group membership.
        context = validate_json_value(
            {
                "cleanup_id": cleanup_id_for_state(state),
                "phase": phase.value,
                "coherency": result.to_payload(),
                "components": list(view.component_unit_instance_ids),
                "models": [model.to_payload() for model in view.own_models],
                "placements": [
                    placement.to_payload()
                    for component_id in view.component_unit_instance_ids
                    if (placement := state.battlefield_state.unit_placement_or_none(component_id))
                    is not None
                ],
            }
        )
        broken_contexts.append(context)
        model_ids.extend(result.model_instance_ids)
    if actor_id is None:
        return None
    context = validate_json_value(
        {
            "cleanup_id": cleanup_id_for_state(state),
            "phase": phase.value,
            "rules_units": broken_contexts,
        }
    )
    digest = hashlib.sha256(canonical_json(context).encode()).hexdigest()
    return DecisionRequest(
        request_id=f"{cleanup_id_for_state(state)}:choice:{digest}",
        decision_type=SELECT_COHERENCY_CASUALTY_DECISION_TYPE,
        actor_id=actor_id,
        payload=context,
        options=tuple(
            DecisionOption(
                option_id=model_id,
                label=f"Remove {model_id}",
                payload={"model_instance_id": model_id},
            )
            for model_id in sorted(model_ids)
        ),
    )


def request_coherency_cleanup(
    *, state: GameState, decisions: DecisionController | None
) -> LifecycleStatus | None:
    request = next_coherency_request(state=state)
    if request is None:
        return None
    if decisions is not None:
        if decisions.queue.pending_requests:
            if decisions.queue.pending_requests != (request,):
                raise GameLifecycleError("Coherency cleanup pending request drift.")
        else:
            decisions.request_decision(request)
        from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
            PRIMARY_SCORING_PENDING_WINDOW_COHERENCY_CASUALTY,
            mark_pending_primary_scoring_boundaries,
        )

        mark_pending_primary_scoring_boundaries(
            state=state,
            pending_window=PRIMARY_SCORING_PENDING_WINDOW_COHERENCY_CASUALTY,
            pending_decision_request_id=request.request_id,
        )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"phase_body_status": "coherency_casualty_required"},
    )


def apply_coherency_result(
    *, state: GameState, decisions: DecisionController, record: DecisionRecord
) -> None:
    if record not in decisions.records or record.request != next_coherency_request(state=state):
        raise GameLifecycleError("Coherency casualty requires the current owner decision receipt.")
    record.result.validate_for_request(record.request)
    phase = state.current_battle_phase
    battlefield = state.battlefield_state
    if phase is None or battlefield is None or state.active_player_id is None:
        raise GameLifecycleError("Coherency casualty context drift.")
    cleanup, updated = resolve_end_turn_cleanup(
        game_id=state.game_id,
        scenario=BattlefieldScenario(tuple(state.army_definitions), battlefield),
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        chosen_model_instance_ids=(record.result.selected_option_id,),
    )
    cleanup = replace(cleanup, cleanup_id=record.request.request_id, completes_boundary=False)
    departure_ids = tuple(row.departure_id for row in state.primary_battlefield_departure_states)
    destruction_ids = tuple(row.destruction_id for row in state.primary_unit_destruction_states)
    destroy_end_turn_coherency_models(state=state, cleanup=cleanup)
    state.replace_battlefield_state(updated)
    record_primary_unit_destructions_for_end_turn_cleanup(state=state, cleanup=cleanup)
    state.end_turn_cleanup_states.append(cleanup)
    state.end_turn_cleanup_states.sort(key=lambda row: row.cleanup_id)
    decisions.event_log.append(
        COHERENCY_CASUALTY_EVENT,
        {
            "cleanup_id": cleanup.cleanup_id,
            "decision_record_id": record.record_id,
            "cleanup": validate_json_value(cleanup.to_payload()),
        },
    )
    record_new_primary_battlefield_departure_events(
        state=state, event_log=decisions.event_log, departure_ids_before=departure_ids
    )
    record_new_primary_unit_destruction_events(
        state=state, event_log=decisions.event_log, destruction_ids_before=destruction_ids
    )


def validate_restored_coherency_choices(*, state: GameState, decisions: DecisionController) -> None:
    """Authenticate casualty receipts and the current finite continuation before restore."""
    records = {
        record.request.request_id: record
        for record in decisions.records
        if record.request.decision_type == SELECT_COHERENCY_CASUALTY_DECISION_TYPE
    }
    steps = {
        row.cleanup_id: row for row in state.end_turn_cleanup_states if not row.completes_boundary
    }
    if records.keys() != steps.keys():
        raise GameLifecycleError("Coherency casualty decision/cleanup inventory drift.")
    events = decisions.event_log.records
    for request_id, record in records.items():
        cleanup = steps[request_id]
        record.result.validate_for_request(record.request)
        if (
            cleanup.removed_model_instance_ids != (record.result.selected_option_id,)
            or len(cleanup.removals) != 1
            or cleanup.removals[0].player_id != record.request.actor_id
            or not isinstance(record.request.payload, dict)
            or record.request.payload.get("cleanup_id")
            != (
                f"end-turn-cleanup:{cleanup.game_id}:round-{cleanup.battle_round:02d}:"
                f"{cleanup.active_player_id}"
            )
        ):
            raise GameLifecycleError("Coherency casualty receipt authority drift.")
        chosen = [
            i
            for i, event in enumerate(events)
            if event.event_type == "decision_recorded" and event.payload == record.to_payload()
        ]
        applied = [
            i
            for i, event in enumerate(events)
            if event.event_type == COHERENCY_CASUALTY_EVENT
            and event.payload
            == {
                "cleanup_id": request_id,
                "decision_record_id": record.record_id,
                "cleanup": cleanup.to_payload(),
            }
        ]
        if len(chosen) != 1 or len(applied) != 1 or chosen[0] >= applied[0]:
            raise GameLifecycleError("Coherency casualty requires one preceding owner decision.")
    for pending in decisions.queue.pending_requests:
        if (
            pending.decision_type == SELECT_COHERENCY_CASUALTY_DECISION_TYPE
            and pending != next_coherency_request(state=state)
        ):
            raise GameLifecycleError("Coherency casualty restored pending request drift.")


class CleanupLifecycleHost(Protocol):
    decision_controller: DecisionController

    def _require_state(self) -> GameState: ...

    def advance_until_decision_or_terminal(self) -> LifecycleStatus: ...


def decision_dispatch_handlers(host: CleanupLifecycleHost) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validator(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        state = host._require_state()  # pyright: ignore[reportPrivateUsage]
        try:
            if request != next_coherency_request(state=state):
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Coherency casualty pending request drift.",
                    payload={"reason": "invalid_coherency_casualty"},
                )
            result.validate_for_request(request)
        except (GameLifecycleError, DecisionError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={"reason": "invalid_coherency_casualty"},
            )
        return None

    def applier(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        apply_coherency_result(
            state=host._require_state(),  # pyright: ignore[reportPrivateUsage]
            decisions=host.decision_controller,
            record=record,
        )
        return host.advance_until_decision_or_terminal()

    return (
        DecisionDispatchHandler(
            decision_type=SELECT_COHERENCY_CASUALTY_DECISION_TYPE,
            pre_validator=pre_validator,
            applier=applier,
        ),
    )
