"""Authenticate Charge target commitments before movement and after restore."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import msgspec

from warhammer40k_core.engine.charge_budget_value import ChargeMovementBudget
from warhammer40k_core.engine.charge_declaration import (
    ChargeRollResult,
    ChargeRollResultPayload,
    phase15a_charge_roll_payload,
)
from warhammer40k_core.engine.charge_phase_state import ChargeTargetSelection
from warhammer40k_core.engine.charge_target_continuation import (
    SELECT_CHARGE_TARGETS_DECISION_TYPE,
    charge_target_selection_request,
    current_charge_targets,
    is_charge_target_replacement_request,
    next_charge_target_replacement,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.target_replacement import (
    SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
    TargetReplacementContext,
    replacement_request,
    replacement_selection,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_charge_2026_09 import (
    CHARGE_TARGET_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler


@dataclass(frozen=True, slots=True)
class ChargeSelectionAuthority:
    selection: ChargeTargetSelection
    action_id: str
    event_index: int
    roll: ChargeRollResult


class _RollPayload(msgspec.Struct, forbid_unknown_fields=True):
    request: dict[str, object]
    roll_state: dict[str, object]
    value: int
    modified_roll: dict[str, object]
    movement_budget: dict[str, object]
    reachable_target_distances_inches: dict[str, float]
    move_available: bool
    status: str


def charge_selection_history(
    *, event_records: tuple[EventRecord, ...], decision_records: tuple[DecisionRecord, ...]
) -> dict[str, ChargeSelectionAuthority]:
    history: dict[str, ChargeSelectionAuthority] = {}
    recorded_ids: list[str] = []
    charge_action_ids: set[str] = set()
    for index, event in enumerate(event_records):
        if event.event_type != "charge_targets_selected":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or set(payload) != {
            "unit_instance_id",
            "request_id",
            "result_id",
            "target_ids",
        }:
            raise GameLifecycleError("Charge target selection event shape drift.")
        unit_id = _identifier(payload, "unit_instance_id")
        selection = (
            None if payload["target_ids"] is None else ChargeTargetSelection.from_payload(payload)
        )
        request_id, result_id = (
            _identifier(payload, "request_id"),
            _identifier(payload, "result_id"),
        )
        record = validate_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=index,
            request_id=request_id,
            result_id=result_id,
        )
        if result_id in recorded_ids:
            raise GameLifecycleError("Duplicate Charge target selection event.")
        recorded_ids.append(result_id)
        option = record.request.option_by_id(record.result.selected_option_id).payload
        if not isinstance(option, dict) or option.get("target_ids") != payload["target_ids"]:
            raise GameLifecycleError("Charge target selection differs from its decision.")
        context = record.request.payload
        if not isinstance(context, dict):
            raise GameLifecycleError("Charge target selection requires context.")
        if record.request.decision_type == SELECT_CHARGE_TARGETS_DECISION_TYPE:
            roll = _charge_roll(context.get("charge_roll"))
            budget = ChargeMovementBudget.from_payload(context.get("movement_budget"))
            if (
                context.get("source_rule_id") != CHARGE_TARGET_SOURCE_ID
                or context.get("game_id") != roll.request.game_id
                or context.get("battle_round") != roll.request.battle_round
                or context.get("phase") != BattlePhase.CHARGE.value
                or context.get("unit_instance_id") != unit_id
                or record.request.actor_id != roll.request.player_id
                or unit_id != roll.request.unit_instance_id
                or budget.modified_roll.unmodified != roll.movement_budget.modified_roll.unmodified
            ):
                raise GameLifecycleError("Charge target selection roll or source context drift.")
            action_id = roll.request.request_id
            charge_action_ids.add(action_id)
            if context.get("action_id") != action_id:
                raise GameLifecycleError("Charge target selection action drift.")
            rolls = tuple(
                e
                for e in event_records[:index]
                if e.event_type == "charge_roll_resolved"
                and e.payload == phase15a_charge_roll_payload(roll_result=roll)
            )
            if len(rolls) != 1:
                raise GameLifecycleError("Charge target selection lacks its resolved roll.")
            reachable = context.get("reachable_target_distances_inches")
            if not isinstance(reachable, dict) or any(
                type(d) not in {int, float}
                or not 0 <= cast(float, d) <= min(12, budget.maximum_distance_inches)
                for d in reachable.values()
            ):
                raise GameLifecycleError("Charge target selection reachable distance drift.")
            if selection is not None and not set(selection.target_ids) <= set(reachable):
                raise GameLifecycleError("Charge target selection exceeds its budget.")
        elif record.request.decision_type == SELECT_TARGET_REPLACEMENT_DECISION_TYPE:
            replacement = TargetReplacementContext.from_payload(context)
            prior = history.get(replacement.selection_id)
            if prior is None or (
                prior.action_id != replacement.action_id
                or prior.selection.target_ids != replacement.original_target_ids
                or prior.selection.unit_instance_id != unit_id
            ):
                raise GameLifecycleError("Charge target replacement lost its prior selection.")
            target_ids = replacement_selection(
                request=record.request, result=record.result, current=replacement
            )
            expected = None if target_ids is None else list(target_ids)
            resolution = {
                "context": replacement.to_payload(),
                "source_decision_request_id": request_id,
                "source_decision_result_id": result_id,
                "replacement_target_ids": expected,
            }
            if (
                len(
                    tuple(
                        e
                        for e in event_records[prior.event_index + 1 : index]
                        if e.event_type == "target_replacement_resolved" and e.payload == resolution
                    )
                )
                != 1
            ):
                raise GameLifecycleError("Charge replacement resolution authority drift.")
            roll, action_id = prior.roll, prior.action_id
        else:
            raise GameLifecycleError("Charge target selection used an unsupported decision.")
        if selection is not None:
            history[result_id] = ChargeSelectionAuthority(selection, action_id, index, roll)
        else:
            history = {key: row for key, row in history.items() if row.action_id != action_id}
    expected_ids = {
        r.result.result_id
        for r in decision_records
        if r.request.decision_type == SELECT_CHARGE_TARGETS_DECISION_TYPE
        or (
            r.request.decision_type == SELECT_TARGET_REPLACEMENT_DECISION_TYPE
            and TargetReplacementContext.from_payload(r.request.payload).action_id
            in charge_action_ids
        )
    }
    if not expected_ids <= set(recorded_ids):
        raise GameLifecycleError("Charge target selection history is incomplete.")
    return history


def validate_charge_selection_reference(
    *,
    selection: ChargeTargetSelection,
    roll: ChargeRollResult,
    before_index: int,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    history = charge_selection_history(
        event_records=event_records, decision_records=decision_records
    )
    authority = history.get(selection.result_id)
    if (
        authority is None
        or authority.selection != selection
        or authority.roll != roll
        or authority.action_id != roll.request.request_id
        or authority.event_index >= before_index
    ):
        raise GameLifecycleError("Charge movement target selection authority drift.")
    later = tuple(
        row
        for row in history.values()
        if row.action_id == authority.action_id
        and authority.event_index < row.event_index < before_index
    )
    if later:
        raise GameLifecycleError("Charge movement uses superseded targets.")


def validate_restored_charge_targets(
    *, state: GameState, decisions: DecisionController, handler: ChargePhaseHandler
) -> None:
    from warhammer40k_core.engine.catalog_setup_reactive_charge_move import (
        is_catalog_setup_reactive_charge_move_request,
    )
    from warhammer40k_core.engine.charge_roll_dispatch import validate_restored_charge_rerolls
    from warhammer40k_core.engine.stratagems import is_heroic_intervention_charge_move_request

    validate_restored_charge_rerolls(state=state, decisions=decisions, handler=handler)
    history = charge_selection_history(
        event_records=decisions.event_log.records, decision_records=decisions.records
    )
    phase = state.charge_phase_state
    distance = None if phase is None else phase.move_pending_distance_state()
    if (
        phase is not None
        and distance is not None
        and phase.target_selection is None
        and any(
            row.action_id == distance.roll_result.request.request_id for row in history.values()
        )
    ):
        raise GameLifecycleError("Charge target commitment is missing from its recorded action.")
    if phase is not None and phase.target_selection is not None:
        if distance is None:
            raise GameLifecycleError("Charge targets have no pending roll.")
        validate_charge_selection_reference(
            selection=phase.target_selection,
            roll=distance.roll_result,
            before_index=len(decisions.event_log.records),
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
        )
    for request in decisions.queue.pending_requests:
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
            if (
                proposal.proposal_kind is ProposalKind.CHARGE_MOVE
                and not is_catalog_setup_reactive_charge_move_request(request)
                and not is_heroic_intervention_charge_move_request(request)
                and (
                    phase is None
                    or phase.target_selection is None
                    or distance is None
                    or proposal.context is None
                    or proposal.context.get("target_selection")
                    != phase.target_selection.to_payload()
                    or proposal.context.get("charge_roll") != distance.roll_result.to_payload()
                )
            ):
                raise GameLifecycleError("Charge movement target commitment authority drift.")
        elif request.decision_type == SELECT_CHARGE_TARGETS_DECISION_TYPE:
            budget, reachable = current_charge_targets(state=state, handler=handler)
            if (
                phase is None
                or phase.target_selection is not None
                or charge_target_selection_request(
                    state=state, request_id=request.request_id, budget=budget, reachable=reachable
                )
                != request
            ):
                raise GameLifecycleError("Restored Charge target request drift.")
        elif is_charge_target_replacement_request(state=state, request=request):
            context = next_charge_target_replacement(state=state, handler=handler)
            if (
                context is None
                or replacement_request(request_id=request.request_id, context=context) != request
            ):
                raise GameLifecycleError("Restored Charge replacement request drift.")
    from warhammer40k_core.engine.charge_endpoint_history import validate_charge_endpoint_history

    validate_charge_endpoint_history(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        ability_index_for_player=handler.ability_index_for_player,
    )
    # Every recorded target is checked above, including completed phases and declines.


def _identifier(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError("Charge target event requires an identifier.")
    return value


def _charge_roll(value: object) -> ChargeRollResult:
    try:
        decoded = msgspec.convert(value, type=_RollPayload, strict=True)
    except msgspec.ValidationError as exc:
        raise GameLifecycleError("Charge target selection roll payload is invalid.") from exc
    try:
        roll = ChargeRollResult.from_payload(
            cast(ChargeRollResultPayload, msgspec.to_builtins(decoded))
        )
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Charge target selection nested roll payload is invalid.") from exc
    if roll.to_payload() != value:
        raise GameLifecycleError("Charge target selection roll payload shape drift.")
    return roll
