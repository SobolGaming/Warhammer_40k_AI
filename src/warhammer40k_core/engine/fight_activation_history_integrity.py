from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.battlefield_presence import (
    battlefield_scenario_for_state,
    rules_unit_has_placed_alive_model,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_model_authority_history import (
    ModelAuthorityTimeline,
    build_model_authority_timeline,
    historical_rules_unit_model_ids,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
    fight_movement_proposal_from_payload,
)
from warhammer40k_core.engine.fight_rules_unit_movement import (
    legal_rules_unit_consolidation_modes,
    legal_rules_unit_pile_in_target_unit_ids,
)
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    fight_rules_unit_movement_endpoint_from_completed_event,
    rules_unit_views_for_completed_move_event,
)
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    rules_unit_identities_share_lineage,
    rules_unit_identity_history_contains,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    ShootingTargetCandidatePayload,
    ShootingTargetViolationCode,
)
from warhammer40k_core.engine.weapon_declaration import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


_ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND = "attack_sequence_model_destroyed"
_MELEE_TARGET_AUTHORITY_ERROR = (
    "Melee target selection requires at least one placed living target model."
)
_RANGED_TARGET_AUTHORITY_ERROR = (
    f"{ShootingTargetViolationCode.TARGET_HAS_NO_PLACED_LIVING_MODELS.value}: "
    "Ranged target selection requires at least one placed living target model."
)
_FIGHT_MOVEMENT_TARGET_AUTHORITY_ERROR = (
    "Fight movement target requires at least one placed living model at its terminal event."
)


def battlefield_scenario_for_living_model_coherency(
    *,
    scenario: BattlefieldScenario,
    state: GameState,
) -> BattlefieldScenario:
    placed_model_ids = frozenset(scenario.battlefield_state.placed_model_ids())
    placed_destroyed_model_ids = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if not model.is_alive and model.model_instance_id in placed_model_ids
    }
    excluded_model_ids = tuple(
        sorted(
            {
                *scenario.present_destroyed_model_ids,
                *placed_destroyed_model_ids,
            }
        )
    )
    return replace(
        scenario,
        battlefield_state=scenario.battlefield_state.with_removed_models(excluded_model_ids),
        present_destroyed_model_ids=(),
    )


def validate_restore(
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    # Logical death owns the living-to-destroyed transition even when no later
    # Fight movement needs a historical liveness query.
    authority_timeline = (
        build_model_authority_timeline(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )
        if any(event.event_type == MODEL_LOGICAL_DEATH_RECORDED_EVENT for event in event_records)
        else None
    )
    _validate_activation_history(state=state)
    _validate_fight_on_death_authority_surfaces(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
        authority_timeline=authority_timeline,
    )


def _validate_activation_history(*, state: GameState) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return
    order_state = fight_state.fight_order_state
    selections = order_state.activation_selections
    result_ids = tuple(selection.result_id for selection in selections)
    if len(result_ids) != len(set(result_ids)):
        raise GameLifecycleError("Fight activation selection result IDs must be unique.")
    for selection in selections:
        if selection.battle_round != fight_state.battle_round:
            raise GameLifecycleError("Fight activation selection battle round drift.")
        if not rules_unit_identity_history_contains(
            state=state,
            identity_ids=order_state.selected_to_fight_unit_ids,
            unit_instance_id=selection.unit_instance_id,
        ):
            raise GameLifecycleError("Fight activation selection is missing from selected history.")
    selection_unit_ids = tuple(selection.unit_instance_id for selection in selections)
    for selected_unit_id in order_state.selected_to_fight_unit_ids:
        if not rules_unit_identity_history_contains(
            state=state,
            identity_ids=selection_unit_ids,
            unit_instance_id=selected_unit_id,
        ):
            raise GameLifecycleError("Fight selected history is missing an activation selection.")
    for index, selection in enumerate(selections):
        if any(
            rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=selection.unit_instance_id,
                second_unit_instance_id=prior.unit_instance_id,
            )
            for prior in selections[:index]
        ):
            raise GameLifecycleError("Fight activation selection repeats a rules-unit lineage.")
    active = fight_state.active_activation
    if active is None:
        return
    matching = tuple(
        selection for selection in selections if selection.result_id == active.result_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Active Fight activation must match exactly one selection.")
    if matching[0] != active:
        raise GameLifecycleError("Active Fight activation selection drift.")
    if not rules_unit_identity_history_contains(
        state=state,
        identity_ids=order_state.selected_to_fight_unit_ids,
        unit_instance_id=active.unit_instance_id,
    ):
        raise GameLifecycleError("Active Fight activation is missing from selected history.")


def _validate_fight_on_death_authority_surfaces(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
    authority_timeline: ModelAuthorityTimeline | None,
) -> None:
    from warhammer40k_core.engine.retained_destruction_state import retained_destructions

    has_retained_authority = any(
        record.is_retained for record in retained_destructions(state=state)
    )
    for request in pending_decision_requests:
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            movement_request = MovementProposalRequest.from_decision_request_payload(
                request.payload
            )
            if movement_request.proposal_kind not in {
                ProposalKind.PILE_IN,
                ProposalKind.CONSOLIDATE,
            }:
                continue
            if not rules_unit_has_placed_alive_model(
                state=state,
                rules_unit=rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=movement_request.unit_instance_id,
                ),
            ):
                raise GameLifecycleError(
                    "Fight movement request requires at least one placed living model."
                )
            _validate_pending_fight_movement_target_authority(
                state=state,
                movement_request=movement_request,
            )
            continue
        if not has_retained_authority:
            continue
        if request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            _validate_pending_shooting_targets(
                state=state,
                request=request,
            )
        elif request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            melee_request = MeleeDeclarationProposalRequest.from_decision_request(request)
            _validate_target_unit_ids(
                state=state,
                target_unit_ids=melee_request.target_unit_instance_ids,
                error_message=_MELEE_TARGET_AUTHORITY_ERROR,
            )
            for available_weapon in melee_request.available_weapons:
                weapon_payload = _payload_object(
                    available_weapon,
                    field_name="Melee declaration available weapon",
                )
                _validate_target_unit_ids(
                    state=state,
                    target_unit_ids=_payload_string_list(
                        weapon_payload,
                        key="engaged_target_unit_instance_ids",
                    ),
                    error_message=_MELEE_TARGET_AUTHORITY_ERROR,
                )
    _validate_recorded_fight_movement_witnesses(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        authority_timeline=authority_timeline,
    )


def _validate_pending_shooting_targets(
    *,
    state: GameState,
    request: DecisionRequest,
) -> None:
    request_payload = _payload_object(
        request.payload,
        field_name="Shooting declaration request payload",
    )
    proposal_payload = _payload_object(
        request_payload.get("proposal_request"),
        field_name="Shooting declaration proposal request",
    )
    raw_candidates = proposal_payload.get("target_candidates")
    if not isinstance(raw_candidates, list) or not all(
        isinstance(row, dict) for row in raw_candidates
    ):
        raise GameLifecycleError("Shooting declaration target candidates are invalid.")
    for raw_candidate in cast(list[dict[str, JsonValue]], raw_candidates):
        candidate = ShootingTargetCandidate.from_payload(
            cast(ShootingTargetCandidatePayload, raw_candidate)
        )
        from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield

        target = rules_unit_view_by_id(
            state=state, unit_instance_id=candidate.target_unit_instance_id
        )
        present_ids = {
            model.model_instance_id
            for model in target.own_models
            if model_is_present_on_battlefield(
                state=state, model_instance_id=model.model_instance_id
            )
        }
        if (
            not set(candidate.target_visible_model_ids + candidate.target_in_range_model_ids)
            <= present_ids
        ):
            raise GameLifecycleError("Ranged target model inventory authority drift.")
        if candidate.is_legal:
            _validate_target_unit_ids(
                state=state,
                target_unit_ids=(candidate.target_unit_instance_id,),
                error_message=_RANGED_TARGET_AUTHORITY_ERROR,
            )


def _validate_target_unit_ids(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
    error_message: str,
) -> None:
    from warhammer40k_core.engine.battlefield_presence import rules_unit_has_present_model

    for target_unit_id in target_unit_ids:
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
        if not rules_unit_has_present_model(state=state, rules_unit=rules_unit):
            raise GameLifecycleError(error_message)


def _validate_pending_fight_movement_target_authority(
    *,
    state: GameState,
    movement_request: MovementProposalRequest,
) -> None:
    context = _payload_object(
        movement_request.context,
        field_name="Fight movement request context",
    )
    scenario = battlefield_scenario_for_state(state=state)
    if movement_request.proposal_kind is ProposalKind.PILE_IN:
        recorded_target_ids = _payload_string_list(
            context,
            key="legal_target_unit_instance_ids",
        )
        expected_target_ids = legal_rules_unit_pile_in_target_unit_ids(
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_instance_id=movement_request.unit_instance_id,
            state=state,
        )
        if recorded_target_ids != expected_target_ids:
            raise GameLifecycleError("Fight movement request target authority drift.")
        return
    recorded_modes = _payload_string_list(
        context,
        key="legal_consolidation_modes",
    )
    objective_markers: tuple[ObjectiveMarker, ...] = (
        ()
        if state.mission_setup is None
        else tuple(marker.to_objective_marker() for marker in state.mission_setup.objective_markers)
    )
    expected_modes = tuple(
        mode.value
        for mode in legal_rules_unit_consolidation_modes(
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_instance_id=movement_request.unit_instance_id,
            objective_markers=objective_markers,
            state=state,
        )
    )
    if recorded_modes != expected_modes:
        raise GameLifecycleError("Fight movement request target authority drift.")


def _validate_recorded_fight_movement_witnesses(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    authority_timeline: ModelAuthorityTimeline | None,
) -> None:
    fight_movement_records: list[tuple[DecisionRecord, MovementProposalRequest]] = []
    for record in decision_records:
        if record.request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
            continue
        proposal_request = MovementProposalRequest.from_decision_request_payload(
            record.request.payload
        )
        if (
            proposal_request.proposal_kind in {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}
            and proposal_request.phase == BattlePhaseKind.FIGHT.value
        ):
            fight_movement_records.append((record, proposal_request))
    if not fight_movement_records:
        return
    if authority_timeline is None:
        authority_timeline = build_model_authority_timeline(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )
    for record, proposal_request in fight_movement_records:
        proposal = fight_movement_proposal_from_payload(record.result.payload)
        rules_units = rules_unit_views_for_completed_move_event(
            state=state,
            event_type="fight_movement_completed",
            unit_instance_id=proposal_request.unit_instance_id,
        )
        witness_model_ids = () if proposal.witness is None else proposal.witness.model_ids()
        lineage_model_ids = historical_rules_unit_model_ids(
            state=state,
            event_records=event_records,
            unit_instance_id=proposal_request.unit_instance_id,
        )
        decision_event_index = _authoritative_decision_event_index(
            event_records=event_records,
            record=record,
        )
        completed_events = _matching_fight_movement_events(
            event_records=event_records,
            event_type="fight_movement_completed",
            record=record,
            proposal_request=proposal_request,
            expected_terminal_event_index=decision_event_index + 1,
        )
        invalid_events = _matching_fight_movement_events(
            event_records=event_records,
            event_type="fight_movement_invalid",
            record=record,
            proposal_request=proposal_request,
            expected_terminal_event_index=decision_event_index + 1,
        )
        if not completed_events and len(invalid_events) == 1:
            invalid_index, invalid_payload = invalid_events[0]
            _validate_recorded_fight_movement_target_authority(
                state=state,
                event_records=event_records,
                terminal_payload=invalid_payload,
                target_unit_instance_ids=proposal.target_unit_instance_ids,
                terminal_event_index=invalid_index,
                authority_timeline=authority_timeline,
            )
            if proposal.witness is not None:
                _validate_retained_fight_movement_model_ids(
                    model_ids=witness_model_ids,
                    terminal_event_index=invalid_index,
                    authority_timeline=authority_timeline,
                )
            continue
        if len(completed_events) != 1 or invalid_events:
            raise GameLifecycleError(
                "Fight movement result must bind to one authoritative terminal event."
            )
        completed_index, completed_payload = completed_events[0]
        completed_resolution = _payload_object(
            completed_payload.get("resolution"),
            field_name="Fight movement completed resolution",
        )
        endpoint_witness = _payload_object(
            completed_resolution.get("endpoint_witness"),
            field_name="Fight movement completed endpoint witness",
        )
        endpoint_target_ids = _payload_string_list(
            endpoint_witness,
            key="target_unit_instance_ids",
        )
        if endpoint_target_ids != proposal.target_unit_instance_ids:
            raise GameLifecycleError("Fight movement completed target identity drift.")
        _validate_recorded_fight_movement_target_authority(
            state=state,
            event_records=event_records,
            terminal_payload=completed_payload,
            target_unit_instance_ids=proposal.target_unit_instance_ids,
            terminal_event_index=completed_index,
            authority_timeline=authority_timeline,
        )
        component_ids = tuple(
            sorted(
                component_id
                for rules_unit in rules_units
                for component_id in rules_unit.component_unit_instance_ids
            )
        )
        endpoint = fight_rules_unit_movement_endpoint_from_completed_event(
            payload=completed_payload,
            component_unit_instance_ids=component_ids,
        )
        event_time_model_ids = tuple(
            sorted(placement.model_instance_id for placement in endpoint.model_placements)
        )
        _validate_retained_fight_movement_model_ids(
            model_ids=(*witness_model_ids, *event_time_model_ids),
            terminal_event_index=completed_index,
            authority_timeline=authority_timeline,
        )
        if proposal.witness is not None and tuple(sorted(witness_model_ids)) != (
            event_time_model_ids
        ):
            raise GameLifecycleError(
                "Fight movement witness must contain every placed living model exactly once."
            )
        if proposal.witness is None:
            expected_event_time_model_ids = {
                model_id
                for model_id in lineage_model_ids
                if authority_timeline.has_placed_living_model_before_event(
                    model_instance_id=model_id,
                    event_index=completed_index,
                )
            }
            if event_time_model_ids != tuple(sorted(expected_event_time_model_ids)):
                raise GameLifecycleError(
                    "Fight no-move completion must contain every placed living model exactly once."
                )


def _validate_recorded_fight_movement_target_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    terminal_payload: dict[str, JsonValue],
    target_unit_instance_ids: tuple[str, ...],
    terminal_event_index: int,
    authority_timeline: ModelAuthorityTimeline,
) -> None:
    from warhammer40k_core.engine.retained_destruction_history import (
        retained_model_ids_before_event,
    )

    retained_ids = retained_model_ids_before_event(
        event_records=event_records, event_index=terminal_event_index
    )
    raw_witness = terminal_payload.get("target_authority_witness")
    if not isinstance(raw_witness, list) or not all(isinstance(row, dict) for row in raw_witness):
        raise GameLifecycleError("Fight movement target authority witness is invalid.")
    witness_rows = cast(list[dict[str, JsonValue]], raw_witness)
    witnessed_target_ids = tuple(
        _payload_string(row, key="target_unit_instance_id") for row in witness_rows
    )
    if witnessed_target_ids != target_unit_instance_ids:
        raise GameLifecycleError("Fight movement target authority witness identity drift.")
    witnessed_model_ids: set[str] = set()
    for target_unit_id, row in zip(target_unit_instance_ids, witness_rows, strict=True):
        if set(row) != {
            "target_unit_instance_id",
            "present_model_instance_ids",
        }:
            raise GameLifecycleError("Fight movement target authority witness shape drift.")
        placed_living_model_ids = _payload_string_list(
            row,
            key="present_model_instance_ids",
        )
        if (
            not placed_living_model_ids
            or placed_living_model_ids != tuple(sorted(set(placed_living_model_ids)))
            or witnessed_model_ids.intersection(placed_living_model_ids)
        ):
            raise GameLifecycleError(_FIGHT_MOVEMENT_TARGET_AUTHORITY_ERROR)
        target_lineage_model_ids = historical_rules_unit_model_ids(
            state=state,
            event_records=event_records,
            unit_instance_id=target_unit_id,
        )
        expected_placed_living_model_ids = tuple(
            sorted(
                model_id
                for model_id in target_lineage_model_ids
                if authority_timeline.has_placed_living_model_before_event(
                    model_instance_id=model_id,
                    event_index=terminal_event_index,
                )
                or model_id in retained_ids
            )
        )
        if not expected_placed_living_model_ids:
            raise GameLifecycleError(_FIGHT_MOVEMENT_TARGET_AUTHORITY_ERROR)
        if placed_living_model_ids != expected_placed_living_model_ids:
            raise GameLifecycleError("Fight movement target authority witness inventory drift.")
        witnessed_model_ids.update(placed_living_model_ids)


def _validate_retained_fight_movement_model_ids(
    *,
    model_ids: tuple[str, ...],
    terminal_event_index: int,
    authority_timeline: ModelAuthorityTimeline,
) -> None:
    if any(
        not authority_timeline.has_placed_living_model_before_event(
            model_instance_id=model_id,
            event_index=terminal_event_index,
        )
        for model_id in model_ids
    ):
        raise GameLifecycleError("Fight movement witness includes a retained destroyed model.")


def _matching_fight_movement_events(
    *,
    event_records: tuple[EventRecord, ...],
    event_type: str,
    record: DecisionRecord,
    proposal_request: MovementProposalRequest,
    expected_terminal_event_index: int,
) -> tuple[tuple[int, dict[str, JsonValue]], ...]:
    matches = tuple(
        (index, event.payload)
        for index, event in enumerate(event_records)
        if event.event_type == event_type
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == record.result.request_id
        and event.payload.get("result_id") == record.result.result_id
        and event.payload.get("proposal_request_id") == proposal_request.request_id
        and event.payload.get("proposal_kind") == proposal_request.proposal_kind.value
        and event.payload.get("unit_instance_id") == proposal_request.unit_instance_id
    )
    if any(index != expected_terminal_event_index for index, _payload in matches):
        raise GameLifecycleError(
            "Fight movement terminal event must immediately follow its decision record."
        )
    return matches


def _authoritative_decision_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    record: DecisionRecord,
) -> int:
    expected_payload = record.to_payload()
    matches = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_recorded" and event.payload == expected_payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Fight movement decision requires one authoritative recorded event."
        )
    return matches[0]


def _payload_object(value: JsonValue | None, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list) or not all(
        type(value) is str and bool(value.strip()) for value in values
    ):
        raise GameLifecycleError(f"{key} must be a list of strings.")
    if len(values) != len(set(values)):
        raise GameLifecycleError(f"{key} must contain unique strings.")
    return tuple(cast(list[str], values))


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Fight On Death {key} must be a string.")
    return value


__all__ = ("validate_restore",)
