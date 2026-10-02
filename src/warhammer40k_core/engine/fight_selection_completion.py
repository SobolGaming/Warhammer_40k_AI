"""A consumed Fight selection is distinct from making melee attacks (04.03.05)."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.attack_sequence_model import AttackSequenceStep
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_order_records import (
    FightActivationSelection,
    FightActivationSelectionPayload,
)
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

FIGHT_SELECTION_COMPLETED = "fight_selection_completed"


def fight_selection_attack_evidence(
    *,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    activation: FightActivationSelection,
) -> tuple[str | None, bool]:
    """Require this selection's terminal declaration/executor, not another attack."""
    declarations: list[dict[str, JsonValue]] = []
    empty: list[EventRecord] = []
    for event in events:
        if not isinstance(event.payload, dict):
            continue
        payload = event.payload
        if (
            event.event_type == "melee_declaration_not_available"
            and payload.get("activation_selection") == activation.to_payload()
        ):
            empty.append(event)
        elif event.event_type == "melee_declaration_accepted":
            request_payload = _object(payload.get("proposal_request"))
            if request_payload.get("source_decision_result_id") == activation.result_id:
                declarations.append(payload)
    if not declarations:
        if len(empty) != 1:
            raise GameLifecycleError("Empty Fight completion requires its declaration boundary.")
        return None, False
    if len(declarations) != 1 or empty:
        raise GameLifecycleError("Fight completion has conflicting declaration evidence.")
    declaration = declarations[0]
    accepted = tuple(
        record
        for record in records
        if record.request.request_id == declaration.get("request_id")
        and record.result.result_id == declaration.get("result_id")
    )
    if len(accepted) != 1:
        raise GameLifecycleError("Fight completion requires its accepted melee decision.")
    request = MeleeDeclarationProposalRequest.from_decision_request(accepted[0].request)
    if (
        request.to_payload() != declaration.get("proposal_request")
        or request.source_decision_request_id != activation.request_id
        or request.source_decision_result_id != activation.result_id
        or request.actor_id != activation.player_id
        or request.battle_round != activation.battle_round
    ):
        raise GameLifecycleError("Fight completion melee selection identity drift.")
    sequence_id = declaration.get("attack_sequence_id")
    if not isinstance(sequence_id, str) or not sequence_id:
        raise GameLifecycleError("Fight completion requires its melee sequence identity.")
    sequence = completed_attack_sequence(event_records=events, sequence_id=sequence_id)
    if (
        sequence.source_phase is not BattlePhase.FIGHT
        or sequence.attacker_player_id != request.actor_id
        or sequence.attacking_unit_instance_id != request.unit_instance_id
    ):
        raise GameLifecycleError("Fight completion executor differs from its melee declaration.")
    # The executor emits HIT for attempts, including misses and automatic hits.
    # Declared/forgone pools and retained ranged sequences do not establish a fight.
    has_fought = any(
        event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence_id
        and event.payload.get("step") == AttackSequenceStep.HIT.value
        for event in events
    )
    return sequence_id, has_fought


def actual_fought_payload(completion: EventRecord) -> dict[str, JsonValue]:
    payload = _object(completion.payload)
    if completion.event_type != FIGHT_SELECTION_COMPLETED or payload.get("has_fought") is not True:
        raise GameLifecycleError("Actual fought status requires a completed melee selection.")
    return {
        **{key: value for key, value in payload.items() if key != "has_fought"},
        "phase_body_status": "unit_fought",
    }


def validate_fight_selection_completion_history(
    *, events: tuple[EventRecord, ...], records: tuple[DecisionRecord, ...]
) -> None:
    """Validate the new completion/status distinction on normal restore paths."""
    completed: dict[str, EventRecord] = {}
    fought: set[str] = set()
    for index, event in enumerate(events):
        if event.event_type not in (FIGHT_SELECTION_COMPLETED, "unit_has_fought"):
            continue
        payload = _object(event.payload)
        activation = FightActivationSelection.from_payload(
            cast(FightActivationSelectionPayload, _object(payload.get("activation_selection")))
        )
        key = activation.result_id
        if event.event_type == FIGHT_SELECTION_COMPLETED:
            if key in completed:
                raise GameLifecycleError("Fight selection completion was recorded twice.")
            sequence_id, has_fought = fight_selection_attack_evidence(
                events=events[:index], records=records, activation=activation
            )
            if (
                payload.get("has_fought") is not has_fought
                or payload.get("attack_sequence_id") != sequence_id
                or payload.get("battle_round") != activation.battle_round
                or payload.get("phase") != BattlePhase.FIGHT.value
                or payload.get("phase_body_status") != FIGHT_SELECTION_COMPLETED
            ):
                raise GameLifecycleError("Fight selection completion differs from actual attacks.")
            completed[key] = event
        else:
            completion = completed.get(key)
            if completion is None or key in fought or payload != actual_fought_payload(completion):
                raise GameLifecycleError("Actual fought event differs from selection completion.")
            fought.add(key)
    if fought != {
        key for key, event in completed.items() if _object(event.payload)["has_fought"] is True
    }:
        raise GameLifecycleError("Completed melee selection lacks its actual fought status.")


def _object(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Fight selection completion evidence must be an object.")
    return cast(dict[str, JsonValue], value)
