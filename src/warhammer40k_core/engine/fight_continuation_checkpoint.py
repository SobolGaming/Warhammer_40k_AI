"""Rebuild the completed ordinary Fight state from its phase and decision history."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import (
    FightPhaseStepKind,
    fight_ordering_band_kind_from_token,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightActivationSelectionPayload,
    FightPhaseState,
    FightPhaseStatePayload,
    current_eligible_pass_from_payload,
    current_fight_activation_selection_from_payload,
    fight_interrupt_request_from_payload,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import GameLifecycleError


def reconstruct_fight_continuation_checkpoint(
    *,
    state: GameState,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    boundary_index: int,
    battle_round: int,
    active_player_id: str,
) -> FightPhaseState:
    starts = tuple(
        (index, event)
        for index, event in enumerate(events[:boundary_index])
        if event.event_type == "fight_phase_started"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_round") == battle_round
        and event.payload.get("active_player_id") == active_player_id
    )
    if len(starts) != 1:
        raise GameLifecycleError("Consolidation requires one preceding ordinary Fight phase start.")
    start_index, start = starts[0]
    seed = FightPhaseState.from_payload(
        cast(FightPhaseStatePayload, _object(_object(start.payload).get("fight_phase_state")))
    )
    policy = state.runtime_ruleset_descriptor().fight_policy
    canonical = FightPhaseState.start(
        battle_round=battle_round,
        active_player_id=active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=seed.fight_order_state.engaged_at_fight_step_start_unit_ids,
        fights_first_registry=seed.fight_order_state.fights_first_registry,
    )
    if seed != canonical:
        raise GameLifecycleError("Ordinary Fight phase start contains continuation bookkeeping.")
    by_request = {record.request.request_id: record for record in records}
    active: FightActivationSelection | None = None
    sequences: set[str] = set()
    completed_sequences: set[str] = set()
    requested_activation_ids: set[str] = set()
    completed_activation_decision_ids: set[str] = set()
    effects = FightContinuationEffects()
    for event in events[start_index + 1 : boundary_index]:
        if not isinstance(event.payload, dict):
            continue
        payload = event.payload
        effects.consume(event, sequences=sequences)
        if event.event_type == "fight_activation_selection_requested":
            request_id = _identifier(payload.get("request_id"))
            if request_id not in by_request:
                raise GameLifecycleError(
                    "Completed Fight contains an unanswered activation request."
                )
            request = by_request[request_id].request
            requested_activation_ids.add(request_id)
            detail = _object(request.payload)
            if (
                detail.get("battle_round") != battle_round
                or detail.get("active_player_id") != active_player_id
                or request.actor_id != payload.get("player_id")
                or detail.get("ordering_band") != payload.get("ordering_band")
            ):
                raise GameLifecycleError("Ordinary Fight activation request context drift.")
            band = fight_ordering_band_kind_from_token(detail.get("ordering_band"))
            if canonical.current_ordering_band is not band:
                canonical = canonical.with_ordering_band(
                    ordering_band=band, next_player_id=_identifier(request.actor_id)
                )
            else:
                canonical = canonical.with_next_player(_identifier(request.actor_id))
        elif event.event_type in {
            "fight_activation_selected",
            "fight_interrupt_activation_selected",
        }:
            selected = FightActivationSelection.from_payload(
                cast(FightActivationSelectionPayload, _object(payload.get("activation_selection")))
            )
            record = _record(by_request, selected.request_id)
            expected = current_fight_activation_selection_from_payload(
                result_payload=record.result.payload,
                request_id=record.request.request_id,
                result_id=record.result.result_id,
                interrupt_id=selected.interrupt_id,
            )
            if selected != expected or active is not None:
                raise GameLifecycleError(
                    "Ordinary Fight activation differs from accepted decisions."
                )
            if expected.ordering_band is not canonical.current_ordering_band:
                raise GameLifecycleError("Ordinary Fight selection ordering band drift.")
            if event.event_type == "fight_activation_selected":
                if (
                    expected.request_id not in requested_activation_ids
                    or expected.player_id != canonical.fight_order_state.next_player_id
                ):
                    raise GameLifecycleError(
                        "Ordinary Fight selection lacks its preceding request."
                    )
                completed_activation_decision_ids.add(expected.request_id)
            canonical = canonical.with_activation(expected)
            active = expected
            if event.event_type == "fight_interrupt_activation_selected":
                interrupt = fight_interrupt_request_from_payload(record.result.payload)
                canonical = canonical.with_resolved_interrupt(
                    interrupt_id=interrupt.interrupt_id, source_effect_id=interrupt.source_effect_id
                )
            else:
                canonical = canonical.with_next_player(_next_player(state, expected.player_id))
        elif event.event_type == "eligible_to_fight_pass_recorded":
            detail = _object(payload.get("eligible_pass"))
            record = _record(by_request, detail.get("request_id"))
            passed = current_eligible_pass_from_payload(
                result_payload=record.result.payload,
                request_id=record.request.request_id,
                result_id=record.result.result_id,
            )
            if passed.to_payload() != detail:
                raise GameLifecycleError("Ordinary Fight pass differs from its accepted decision.")
            if passed.request_id not in requested_activation_ids:
                raise GameLifecycleError("Ordinary Fight pass lacks its preceding request.")
            completed_activation_decision_ids.add(passed.request_id)
            canonical = canonical.with_eligible_pass(passed).with_next_player(
                _next_player(state, passed.player_id)
            )
        elif event.event_type == "fight_interrupt_declined":
            detail = _object(payload.get("interrupt"))
            matches = tuple(
                record
                for record in records
                if isinstance(record.result.payload, dict)
                and record.result.payload.get("interrupt") == detail
            )
            if len(matches) != 1:
                raise GameLifecycleError("Ordinary Fight interrupt lacks its accepted decline.")
            interrupt = fight_interrupt_request_from_payload(matches[0].result.payload)
            canonical = canonical.with_resolved_interrupt(
                interrupt_id=interrupt.interrupt_id, source_effect_id=interrupt.source_effect_id
            )
        elif event.event_type == "unit_has_fought":
            if active is None or payload.get("activation_selection") != active.to_payload():
                raise GameLifecycleError("Ordinary Fight activation completion drift.")
            active = None
        elif event.event_type == "melee_declaration_accepted":
            sequences.add(_identifier(payload.get("attack_sequence_id")))
        elif event.event_type == "attack_sequence_completed":
            sequence_id = _identifier(payload.get("sequence_id"))
            if sequence_id in sequences:
                completed_sequences.add(sequence_id)
        elif event.event_type == "fight_movement_completed":
            record = _record(by_request, payload.get("request_id"))
            movement_request = MovementProposalRequest.from_decision_request_payload(
                record.request.payload
            )
            if record.result.result_id != payload.get("result_id"):
                raise GameLifecycleError("Ordinary Fight movement decision identity drift.")
            if (
                movement_request.context is not None
                and movement_request.context.get("fight_movement_timing") == "overrun"
            ):
                if active is None or active.result_id != movement_request.source_decision_result_id:
                    raise GameLifecycleError("Ordinary Overrun lacks its active selection.")
                canonical = canonical.with_overrun_pile_in_completed(
                    activation_result_id=active.result_id
                )
            else:
                if (
                    movement_request.proposal_kind is not ProposalKind.PILE_IN
                    or canonical.pile_in_state is None
                ):
                    raise GameLifecycleError("Pre-consolidation movement step drift.")
                movement = canonical.pile_in_state
                while movement.next_player_id != movement_request.actor_id:
                    movement = movement.with_completed_player(
                        next_player_id=_next_player(state, movement.next_player_id)
                    )
                canonical = canonical.with_pile_in_state(
                    movement.with_completed_unit(unit_instance_id=movement_request.unit_instance_id)
                )
        elif event.event_type == "overrun_pile_in_not_available":
            if active is None or payload.get("activation_selection") != active.to_payload():
                raise GameLifecycleError("Ordinary Overrun completion selection drift.")
            canonical = canonical.with_overrun_pile_in_completed(
                activation_result_id=active.result_id
            )
    if (
        active is not None
        or sequences != completed_sequences
        or requested_activation_ids != completed_activation_decision_ids
    ):
        raise GameLifecycleError("Consolidation cannot interrupt unfinished ordinary combat.")
    final_movement = canonical.pile_in_state
    if final_movement is None:
        raise GameLifecycleError("Ordinary Fight requires pile-in progress.")
    while len(final_movement.completed_player_ids) < len(state.player_ids):
        final_movement = final_movement.with_completed_player(
            next_player_id=_next_player(state, final_movement.next_player_id)
        )
    canonical = canonical.with_pile_in_state(final_movement)
    while canonical.fight_order_state.current_band_index + 1 < len(policy.ordering_bands):
        canonical = canonical.with_next_band()
    for _ in range(len(state.player_ids) - 1):
        canonical = canonical.with_next_player(
            _next_player(state, canonical.fight_order_state.next_player_id)
        )
    return replace(
        canonical.with_current_step(current_step=FightPhaseStepKind.CONSOLIDATE, policy=policy),
        allocated_model_ids_this_phase=tuple(sorted(effects.allocated_ids)),
    )


class FightContinuationEffects:
    """Fold concrete allocation effects; a group is used only when a save is resolved."""

    def __init__(self, allocated_ids: tuple[str, ...] = ()) -> None:
        self.allocated_ids = set(allocated_ids)
        self.groups: dict[str, tuple[str, ...]] = {}

    def consume(self, event: EventRecord, *, sequences: set[str]) -> None:
        if event.event_type != "attack_sequence_step" or not isinstance(event.payload, dict):
            return
        payload = event.payload
        if payload.get("sequence_id") not in sequences:
            return
        detail = _object(payload.get("payload"))
        if payload.get("step") == "allocate":
            groups = detail.get("allocation_groups")
            if isinstance(groups, list):
                for raw in groups:
                    group = _object(raw)
                    model_ids = group.get("model_ids")
                    if not isinstance(model_ids, list):
                        raise GameLifecycleError(
                            "Fight allocation group model inventory is malformed."
                        )
                    self.groups[_identifier(group.get("group_id"))] = tuple(
                        _identifier(model) for model in model_ids
                    )
            allocation = detail.get("allocation")
            if isinstance(allocation, dict):
                self.allocated_ids.add(_identifier(allocation.get("allocated_model_id")))
        elif payload.get("step") == "save":
            group_id = detail.get("allocation_group_id")
            if isinstance(group_id, str):
                if group_id not in self.groups:
                    raise GameLifecycleError("Fight save lacks its preceding allocation group.")
                self.allocated_ids.update(self.groups[group_id])


def _next_player(state: GameState, player_id: str) -> str:
    if player_id not in state.player_ids:
        raise GameLifecycleError("Fight continuation player is not in this game.")
    return state.player_ids[(state.player_ids.index(player_id) + 1) % len(state.player_ids)]


def _object(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Fight continuation history requires object payloads.")
    return cast(dict[str, JsonValue], value)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise GameLifecycleError("Fight continuation history requires an identifier.")
    return value


def _record(records: dict[str, DecisionRecord], request_id: object) -> DecisionRecord:
    key = _identifier(request_id)
    if key not in records:
        raise GameLifecycleError("Fight continuation history lacks an accepted decision.")
    return records[key]
