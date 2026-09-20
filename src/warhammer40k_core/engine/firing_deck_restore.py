"""Authenticate Firing Deck restrictions against accepted declaration snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.effects import EffectExpirationBoundary, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.firing_deck_restrictions import (
    build_firing_deck_restriction,
    firing_deck_restriction_payload,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState


def validate_firing_deck_restrictions(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
    army_catalog: ArmyCatalog | None,
) -> None:
    from warhammer40k_core.engine.phases.shooting_firing_deck import firing_deck_cargo_snapshot

    for pending in pending_decision_requests:
        if pending.decision_type != "submit_shooting_declaration":
            continue
        if army_catalog is None:
            raise GameLifecycleError("Firing Deck pending declaration requires the catalog.")
        request = _object(_object(pending.payload).get("proposal_request"))
        unit_id = request.get("unit_instance_id")
        if type(unit_id) is not str:
            raise GameLifecycleError("Firing Deck pending declaration has no unit identity.")
        expected_ids = list(
            firing_deck_cargo_snapshot(
                state=state,
                unit_instance_id=unit_id,
                army_catalog=army_catalog,
            )
        )
        expected_snapshot = expected_ids if request["firing_deck_value"] is not None else None
        if request.get("firing_deck_embarked_unit_instance_ids") != expected_snapshot:
            raise GameLifecycleError("Firing Deck pending cargo snapshot drifted.")
    decisions = {record.result.result_id: record for record in decision_records}
    expected: dict[str, PersistingEffect] = {}
    completed_declarations: set[str] = set()
    for event in event_records:
        if event.event_type not in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
        }:
            continue
        payload = _object(event.payload)
        result_id = payload.get("result_id")
        if not isinstance(result_id, str) or result_id not in decisions:
            raise GameLifecycleError("Firing Deck history lacks its accepted declaration.")
        record = decisions[result_id]
        if result_id in completed_declarations:
            raise GameLifecycleError("Firing Deck history repeats a declaration.")
        completed_declarations.add(result_id)
        if event.event_type == "out_of_phase_shooting_declaration_accepted":
            continue
        request = _object(_object(record.request.payload).get("proposal_request"))
        ids = request.get("firing_deck_embarked_unit_instance_ids")
        if request["firing_deck_value"] is None and ids is None:
            if payload.get("ineligible_unit_instance_ids") != []:
                raise GameLifecycleError("Non-Firing Deck declaration cannot restrict cargo.")
            continue
        if not isinstance(ids, list) or any(type(value) is not str for value in ids):
            raise GameLifecycleError("Firing Deck declaration lacks its cargo snapshot.")
        embarked_ids = tuple(value for value in ids if isinstance(value, str))
        if payload.get("ineligible_unit_instance_ids") != ids:
            raise GameLifecycleError("Firing Deck declaration cargo snapshot drifted.")
        if not embarked_ids:
            continue
        transport_id = payload.get("unit_instance_id")
        battle_round = payload.get("battle_round")
        if (
            type(transport_id) is not str
            or type(battle_round) is not int
            or record.request.actor_id is None
            or record.request.decision_type != "submit_shooting_declaration"
            or payload.get("request_id") != record.request.request_id
            or payload.get("active_player_id") != record.request.actor_id
            or request.get("unit_instance_id") != transport_id
            or request.get("battle_round") != battle_round
            or request.get("active_player_id") != record.request.actor_id
            or request.get("phase") != "shooting"
            or payload.get("phase") != "shooting"
            or payload.get("game_id") != state.game_id
        ):
            raise GameLifecycleError("Firing Deck declaration identity or timing drifted.")
        for unit_id in (transport_id, *embarked_ids):
            if (
                rules_unit_view_by_id(state=state, unit_instance_id=unit_id).owner_player_id
                != record.request.actor_id
            ):
                raise GameLifecycleError("Firing Deck cargo snapshot ownership drifted.")
        effect = build_firing_deck_restriction(
            player_id=record.request.actor_id,
            battle_round=battle_round,
            transport_unit_instance_id=transport_id,
            embarked_unit_instance_ids=embarked_ids,
            result_id=result_id,
        )
        if effect.effect_id in expected:
            raise GameLifecycleError("Firing Deck history repeats a declaration.")
        expected[effect.effect_id] = effect
    if completed_declarations != {
        row.result.result_id
        for row in decision_records
        if row.request.decision_type == "submit_shooting_declaration"
    }:
        raise GameLifecycleError("Firing Deck declaration completion history is incomplete.")
    for boundary_record in state.objective_control_records:
        if boundary_record.timing is ObjectiveControlTiming.TURN_END:
            boundary = EffectExpirationBoundary.turn_end(
                battle_round=boundary_record.battle_round,
                player_id=boundary_record.active_player_id,
            )
            expected = {
                key: effect for key, effect in expected.items() if not effect.expires_at(boundary)
            }
    actual = {
        effect.effect_id: effect
        for effect in state.persisting_effects
        if firing_deck_restriction_payload(effect) is not None
    }
    if actual != expected:
        raise GameLifecycleError(
            "Firing Deck restriction inventory differs from declaration history."
        )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Firing Deck history requires an object.")
    return value
