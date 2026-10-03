"""Ordered ordinary Movement selection rights, independent of rollback snapshots."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.mutation_decision_authority import validate_record_event_closure
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import MovementUnitSelection
from warhammer40k_core.engine.phases.movement_state import MovementPhaseState
from warhammer40k_core.engine.transport_source_embark_history import validate_source_embark_event
from warhammer40k_core.engine.transports import DisembarkModeKind
from warhammer40k_core.geometry.pathing import PathWitness, PathWitnessPayload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_movement_phase_2026_08


class MovementSelectionHistory:
    def __init__(
        self, *, records: tuple[DecisionRecord, ...], events: tuple[EventRecord, ...], game_id: str
    ) -> None:
        self._records = records
        self._events = events
        self._event_positions = {event.event_id: index for index, event in enumerate(events)}
        self._game_id = game_id
        self._by_result = {record.result.result_id: record for record in records}
        self._positions = {record.result.result_id: index for index, record in enumerate(records)}
        self._phases: dict[tuple[int, str], MovementPhaseState] = {}

    def observe(self, *, event: EventRecord, prior_event: EventRecord | None) -> None:
        payload = event.payload
        if not isinstance(payload, dict) or payload.get("phase") != BattlePhase.MOVEMENT.value:
            return
        if event.event_type not in {
            "movement_unit_selected",
            "movement_activation_completed",
            "unit_disembarked",
            "unit_embarked",
            "reinforcement_unit_arrived",
            "move_units_completed",
        }:
            return
        if event.event_type == "unit_embarked":
            selection = payload.get("embark_selection")
            if not isinstance(selection, dict) or "source_context" not in selection:
                return
        round_number = payload.get("battle_round")
        if type(round_number) is not int or round_number < 1:
            raise GameLifecycleError("Movement selection history requires a positive round.")
        player_id = _string(payload, "active_player_id")
        key = (round_number, player_id)
        phase = self._phases.get(key, MovementPhaseState(round_number, player_id))
        if event.event_type == "move_units_completed":
            self._phases[key] = phase.with_move_units_completed()
            return
        if event.event_type == "unit_disembarked" and payload.get("disembark_mode") not in {
            DisembarkModeKind.RAPID_DISEMBARK.value,
            DisembarkModeKind.ASSAULT_DISEMBARK.value,
            DisembarkModeKind.SHOCK_DISEMBARK.value,
            DisembarkModeKind.COMBAT_DISEMBARK.value,
        }:
            return
        if event.event_type == "reinforcement_unit_arrived" and payload.get("step") not in {
            "move_units",
            "rapid_ingress",
        }:
            return
        record = self._by_result.get(_string(payload, "result_id"))
        if record is None or record.request.request_id != payload.get("request_id"):
            raise GameLifecycleError("Movement selection history decision closure drift.")
        unit_id = _string(payload, "unit_instance_id")
        if event.event_type == "unit_embarked":
            validate_source_embark_event(record, payload)
            if phase.active_selection is not None and (
                phase.active_selection.unit_instance_id == unit_id
            ):
                self._phases[key] = phase.with_activation_complete(
                    unit_id,
                    maximum_model_distance_inches=0.0,
                    maximum_model_horizontal_distance_inches=0.0,
                )
            return
        if (
            event.event_type == "reinforcement_unit_arrived"
            and payload.get("step") == "rapid_ingress"
        ):
            proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
            context = proposal.context or {}
            if context.get("mark_movement_phase_reinforcement_arrival") is True:
                self._phases[key] = phase.with_end_movement_ingress_arrival(unit_id)
            return
        if record.request.actor_id != player_id:
            raise GameLifecycleError("Movement selection history actor drift.")
        if event.event_type == "movement_unit_selected":
            validate_record_event_closure(
                event_records=self._events,
                mutation_index=self._event_positions[event.event_id],
                record=record,
            )
            if (
                prior_event is None
                or prior_event.event_type != "decision_recorded"
                or prior_event.payload != validate_json_value(record.to_payload())
                or record.request.decision_type != "select_movement_unit"
                or not isinstance(record.result.payload, dict)
                or record.result.payload.get("unit_instance_id") != unit_id
                or record.request.payload
                != self._selection_request_payload(round_number, player_id)
            ):
                raise GameLifecycleError("Movement selection history selection closure drift.")
            self._phases[key] = phase.with_unit_selection(
                MovementUnitSelection(
                    player_id=player_id,
                    battle_round=round_number,
                    unit_instance_id=unit_id,
                    request_id=record.request.request_id,
                    result_id=record.result.result_id,
                )
            )
            return
        witness_raw = payload.get("witness")
        witness = None
        if witness_raw is not None:
            if not isinstance(witness_raw, dict):
                raise GameLifecycleError("Movement selection completion requires a witness object.")
            witness = PathWitness.from_payload(cast(PathWitnessPayload, witness_raw))
        from warhammer40k_core.engine.phases.movement_fall_back_embark import (
            _maximum_model_distance_inches_from_witness,
            _maximum_model_horizontal_distance_inches_from_witness,
        )

        self._phases[key] = phase.with_activation_complete(
            unit_id,
            maximum_model_distance_inches=_maximum_model_distance_inches_from_witness(witness),
            maximum_model_horizontal_distance_inches=_maximum_model_horizontal_distance_inches_from_witness(
                witness
            ),
        )

    def assert_projection(self, phase: MovementPhaseState) -> None:
        expected = self._phases.get((phase.battle_round, phase.active_player_id))
        if expected is None or (
            phase.selected_unit_ids != expected.selected_unit_ids
            or phase.moved_unit_ids != expected.moved_unit_ids
            or phase.movement_distance_records != expected.movement_distance_records
            or phase.active_selection != expected.active_selection
            or phase.move_units_completed is not expected.move_units_completed
        ):
            raise GameLifecycleError("Failed setup Movement selection projection drift.")

    def rollback(self, before: MovementPhaseState) -> None:
        if before.active_selection is None:
            raise GameLifecycleError("Failed setup history requires active selection.")
        key = (before.battle_round, before.active_player_id)
        self._phases[key] = self._phases[key].without_failed_setup_selection(
            before.active_selection.unit_instance_id
        )

    def assert_action_order(
        self,
        *,
        selection: MovementUnitSelection,
        action: DecisionRecord | None,
        rejected: DecisionRecord,
        mutation_index: int,
    ) -> None:
        if action is None:
            raise GameLifecycleError("Failed setup history has no selected action.")
        selected = self._by_result[selection.result_id]
        for record in (selected, action, rejected):
            validate_record_event_closure(
                event_records=self._events,
                mutation_index=mutation_index,
                record=record,
            )
            if (
                record.request.actor_id != selection.player_id
                or record.result.actor_id != selection.player_id
            ):
                raise GameLifecycleError("Failed setup selected action actor drift.")
        expected_action = {
            **self._selection_request_payload(selection.battle_round, selection.player_id),
            "unit_instance_id": selection.unit_instance_id,
        }
        if action.request.payload != expected_action:
            raise GameLifecycleError("Failed setup selected action context drift.")
        ordered_events = (
            ("decision_recorded", selected.to_payload()),
            ("decision_requested", action.request.to_payload()),
            ("decision_recorded", action.to_payload()),
            ("decision_requested", rejected.request.to_payload()),
            ("decision_recorded", rejected.to_payload()),
        )
        indices = tuple(
            next(
                index
                for index, event in enumerate(self._events[:mutation_index])
                if event.event_type == event_type and event.payload == payload
            )
            for event_type, payload in ordered_events
        )
        if tuple(sorted(indices)) != indices or len(set(indices)) != len(indices):
            raise GameLifecycleError("Failed setup selected action event order drift.")
        selected_index = self._positions[selection.result_id]
        action_index = self._positions[action.result.result_id]
        rejected_index = self._positions[rejected.result.result_id]
        action_records = tuple(
            record
            for record in self._records[selected_index + 1 : rejected_index]
            if record.request.decision_type == "select_movement_action"
        )
        if (
            not selected_index < action_index < rejected_index
            or not action_records
            or action_records[-1] != action
        ):
            raise GameLifecycleError("Failed setup latest selected action order drift.")

    def _selection_request_payload(self, round_number: int, player_id: str) -> dict[str, JsonValue]:
        return {
            "game_id": self._game_id,
            "battle_round": round_number,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": player_id,
            "source_rule_id": core_movement_phase_2026_08.MOVE_UNITS_STEP_SOURCE_ID,
        }


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Movement selection history requires string {key}.")
    return value
