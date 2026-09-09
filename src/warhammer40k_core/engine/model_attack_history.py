"""Model participation at the shared attack executor's completed-attacks boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState

MODELS_ATTACKED_EVENT_TYPE = "attack_sequence_models_attacked"


def record_attack_sequence_completed(
    *, state: GameState, decisions: DecisionController, sequence: AttackSequence
) -> None:
    payload = {
        "sequence_id": sequence.sequence_id,
        "attacker_player_id": sequence.attacker_player_id,
        "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
    }
    prior = [
        event
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
    ]
    if prior:
        if len(prior) != 1 or prior[0].payload != payload:
            raise GameLifecycleError("Attack sequence completion history drift.")
        return
    from warhammer40k_core.engine.activity_restrictions import record_completed_shooting_restriction

    record_completed_shooting_restriction(state=state, sequence=sequence)
    decisions.event_log.append("attack_sequence_completed", payload)


def record_models_attacked(
    *, state: GameState, decisions: DecisionController, sequence: AttackSequence
) -> None:
    if not sequence.is_complete or state.current_battle_phase is None:
        raise GameLifecycleError("Model attack history requires completed attacks in a phase.")
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": state.current_battle_phase.value,
            "sequence_id": sequence.sequence_id,
            "attack_phase": sequence.source_phase.value,
            "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
            "model_instance_ids": sorted(
                {pool.attacker_model_instance_id for pool in sequence.attack_pools}
            ),
        }
    )
    prior = [
        event
        for event in decisions.event_log.records
        if event.event_type == MODELS_ATTACKED_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
    ]
    if prior:
        if len(prior) != 1 or prior[0].payload != payload:
            raise GameLifecycleError("Model attack participation boundary drift.")
        return
    decisions.event_log.append(MODELS_ATTACKED_EVENT_TYPE, payload)


def model_has_attacked_this_phase(
    *,
    event_records: tuple[EventRecord, ...],
    model_instance_id: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
) -> bool:
    for event in event_records:
        payload = event.payload
        if event.event_type != MODELS_ATTACKED_EVENT_TYPE:
            continue
        if not isinstance(payload, dict) or set(payload) != {
            "game_id",
            "battle_round",
            "active_player_id",
            "phase",
            "sequence_id",
            "attack_phase",
            "attacking_unit_instance_id",
            "model_instance_ids",
        }:
            raise GameLifecycleError("Model attack participation history fields drift.")
        model_ids = payload["model_instance_ids"]
        if not isinstance(model_ids, list) or not all(
            type(model_id) is str for model_id in model_ids
        ):
            raise GameLifecycleError("Model attack participation IDs are invalid.")
        if (
            payload["battle_round"] == battle_round
            and payload["active_player_id"] == active_player_id
            and payload["phase"] == phase
            and model_instance_id in model_ids
        ):
            return True
    return False


def validate_retained_model_attack_history(
    *, event_records: tuple[EventRecord, ...], model_instance_ids: frozenset[str]
) -> None:
    """Bind prior-action restrictions to the declared models and executor boundary."""
    if not model_instance_ids:
        return
    declarations: dict[str, dict[str, JsonValue]] = {}
    participations: set[str] = set()
    for event in event_records:
        if event.event_type in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
            "melee_declaration_accepted",
        }:
            expected = _participation_for_declaration(event)
            declared_ids = _model_ids(expected["model_instance_ids"])
            if not declared_ids.intersection(model_instance_ids):
                continue
            sequence_id = _identifier(expected["sequence_id"])
            if sequence_id in declarations:
                raise GameLifecycleError("Model attack history has duplicate declarations.")
            declarations[sequence_id] = expected
        elif event.event_type == MODELS_ATTACKED_EVENT_TYPE:
            payload = _object(event.payload)
            sequence_id = _identifier(payload.get("sequence_id"))
            if sequence_id not in declarations:
                if _model_ids(payload.get("model_instance_ids")).intersection(model_instance_ids):
                    raise GameLifecycleError("Model attack history lacks its declaration.")
                continue
            if sequence_id in participations or payload != declarations[sequence_id]:
                raise GameLifecycleError("Model attack history differs from its declaration.")
            participations.add(sequence_id)
        elif event.event_type in {"attack_sequence_completed", "attack_sequence_attacks_resolved"}:
            payload = _object(event.payload)
            sequence_id = _identifier(payload.get("sequence_id"))
            if sequence_id in declarations and sequence_id not in participations:
                raise GameLifecycleError("Model attack history is missing its completed attacks.")


def _participation_for_declaration(event: EventRecord) -> dict[str, JsonValue]:
    payload = _object(event.payload)
    if event.event_type == "melee_declaration_accepted":
        request = _object(payload.get("proposal_request"))
        proposal = _object(payload.get("proposal"))
        entries = proposal.get("declarations")
        sequence_id = payload.get("attack_sequence_id")
        phase = "fight"
        active_player_id = request.get("active_player_id")
        unit_id = proposal.get("unit_instance_id")
        attack_phase = "fight"
    else:
        entries = payload.get("attack_pools")
        result_id = _identifier(payload.get("result_id"))
        out_of_phase = event.event_type == "out_of_phase_shooting_declaration_accepted"
        sequence_id = f"{'out-of-phase-' if out_of_phase else ''}attack-sequence:{result_id}"
        phase = _identifier(payload.get("parent_phase") if out_of_phase else payload.get("phase"))
        active_player_id = (
            _object(payload.get("ranged_attack_history_record")).get("active_player_id")
            if out_of_phase
            else payload.get("active_player_id")
        )
        unit_id = payload.get("unit_instance_id")
        attack_phase = "shooting"
    if not isinstance(entries, list):
        raise GameLifecycleError("Model attack declaration requires weapon entries.")
    return {
        "game_id": payload.get("game_id"),
        "battle_round": payload.get("battle_round"),
        "active_player_id": _identifier(active_player_id),
        "phase": _identifier(phase),
        "sequence_id": _identifier(sequence_id),
        "attack_phase": attack_phase,
        "attacking_unit_instance_id": _identifier(unit_id),
        "model_instance_ids": validate_json_value(
            sorted(
                {_identifier(_object(entry).get("attacker_model_instance_id")) for entry in entries}
            )
        ),
    }


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Model attack history requires an object.")
    return value


def _identifier(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError("Model attack history requires an identifier.")
    return value


def _model_ids(value: JsonValue) -> frozenset[str]:
    if not isinstance(value, list):
        raise GameLifecycleError("Model attack history requires model identifiers.")
    return frozenset(_identifier(model_id) for model_id in value)


def validate_declared_model_attack_completions(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Require every shooting participation to retain its original declaration.

    Mid-executor checkpoints retain the accepted declaration prefix. An omitted
    declaration is not evidence of an authenticated executor starting boundary.
    """
    shooting = frozenset(
        _identifier(_object(event.payload).get("sequence_id"))
        for event in event_records
        if event.event_type == MODELS_ATTACKED_EVENT_TYPE
        and _object(event.payload).get("attack_phase") == "shooting"
    )
    relevant = tuple(
        event
        for event in event_records
        if event.event_type
        in {"shooting_declaration_accepted", "out_of_phase_shooting_declaration_accepted"}
        or (
            event.event_type
            in {
                MODELS_ATTACKED_EVENT_TYPE,
                "attack_sequence_completed",
                "attack_sequence_attacks_resolved",
            }
            and _identifier(_object(event.payload).get("sequence_id")) in shooting
        )
    )
    model_ids = frozenset(
        model_id
        for event in relevant
        if event.event_type == MODELS_ATTACKED_EVENT_TYPE
        for model_id in _model_ids(_object(event.payload).get("model_instance_ids"))
    )
    validate_retained_model_attack_history(event_records=relevant, model_instance_ids=model_ids)

    from warhammer40k_core.engine.primary_mission_event_decision_authority import (
        validate_primary_mission_shooting_event_decision_authority,
    )
    from warhammer40k_core.engine.weapon_declaration import shooting_declaration_proposal_from_json

    records = {record.result.result_id: record for record in decision_records}
    ranged_history = {record.result_id: record for record in state.ranged_attack_history_records}
    for index, event in enumerate(event_records):
        if event.event_type not in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
        }:
            continue
        expected = _participation_for_declaration(event)
        if expected["sequence_id"] not in shooting:
            continue
        payload = _object(event.payload)
        authority_payload = dict(payload)
        if event.event_type == "out_of_phase_shooting_declaration_accepted":
            authority_payload["active_player_id"] = payload.get("player_id")
        validate_primary_mission_shooting_event_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=index,
            payload=authority_payload,
        )
        result_id = _identifier(payload.get("result_id"))
        ranged = ranged_history.get(result_id)
        if ranged is None or (
            ranged.player_id != authority_payload.get("active_player_id")
            or ranged.request_id != payload.get("request_id")
            or ranged.unit_instance_id != expected["attacking_unit_instance_id"]
            or ranged.battle_round != expected["battle_round"]
            or ranged.active_player_id != expected["active_player_id"]
            or ranged.phase.value != expected["phase"]
        ):
            raise GameLifecycleError("Model attack history lacks its original ranged activation.")
        if event.event_type == "out_of_phase_shooting_declaration_accepted":
            if payload.get("ranged_attack_history_record") != ranged.to_payload():
                raise GameLifecycleError("Model attack history parent timing authority drifted.")
        elif payload.get("phase") != "shooting":
            raise GameLifecycleError("Model attack history ordinary shooting phase drifted.")
        record = records[result_id]
        proposal = shooting_declaration_proposal_from_json(record.result.payload)
        if (
            sorted({entry.attacker_model_instance_id for entry in proposal.declarations})
            != expected["model_instance_ids"]
        ):
            raise GameLifecycleError("Model attack history declaration model authority drifted.")
