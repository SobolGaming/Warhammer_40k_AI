from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock_hooks import BattleShockForcedTestApplication
from warhammer40k_core.engine.battle_shock_state_history import (
    battle_shock_state_authority_before_event,
)
from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    CommandBattleShockCandidatePayload,
    CommandBattleShockEligibilityReason,
    forced_test_applications_from_candidate_inventory,
)
from warhammer40k_core.engine.command_battle_shock_forced_provider_authority import (
    validate_command_forced_test_applications,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    PhysicalModelAuthority,
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState

_SNAPSHOT_EVENT = "battle_shock_step_snapshot_created"


def validate_historical_command_candidate_inventory(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    battle_round: int,
    active_player_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    candidates: tuple[CommandBattleShockCandidate, ...],
) -> None:
    """Bind a retained snapshot to the complete event-bound physical inventory."""
    expected = _historical_command_candidate_inventory(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        snapshot_index=snapshot_index,
        active_player_id=active_player_id,
        forced_applications=forced_test_applications_from_candidate_inventory(candidates),
    )
    if (
        candidates != expected
        or tuple(
            candidate.unit_instance_id for candidate in candidates if candidate.is_battle_shocked
        )
        != phase_start_battle_shocked_unit_ids
        or battle_round < 1
    ):
        raise GameLifecycleError(
            "Command Battle-shock candidate inventory lacks exact historical authority."
        )


def validate_loaded_command_battle_shock_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Bind every retained forced-test application to the loaded hook registry."""
    for snapshot_index, event in enumerate(event_records):
        if event.event_type != _SNAPSHOT_EVENT:
            continue
        payload = _object(event.payload)
        if payload.get("game_id") != state.game_id:
            continue
        battle_round = _positive_int(payload.get("battle_round"), field="battle_round")
        active_player_id = _player_id(
            payload.get("active_player_id"),
            state=state,
        )
        if payload.get("phase") != BattlePhase.COMMAND.value:
            raise GameLifecycleError("Command Battle-shock snapshot phase authority drifted.")
        _identifier_list(
            payload.get("battle_shock_phase_start_unit_ids"),
            field="phase-start Battle-shocked units",
        )
        candidates = _candidates(payload.get("battle_shock_candidate_inventory"))
        validate_command_forced_test_applications(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            snapshot_index=snapshot_index,
            battle_round=battle_round,
            active_player_id=active_player_id,
            candidates=candidates,
            battle_shock_hook_registry=runtime_content_bundle.battle_shock_hook_registry,
            ability_indexes_by_player_id=runtime_content_bundle.ability_indexes_by_player_id,
        )


def _historical_command_candidate_inventory(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    active_player_id: str,
    forced_applications: tuple[BattleShockForcedTestApplication, ...],
) -> tuple[CommandBattleShockCandidate, ...]:
    applications = forced_applications
    physical_rows = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=snapshot_index,
    )
    physical_by_model_id = {row.model_instance_id: row for row in physical_rows}
    state_authority = battle_shock_state_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=snapshot_index,
    )
    active_attached_ids = set(state_authority.active_attached_unit_ids)
    shocked_ids = set(state_authority.battle_shocked_unit_ids)
    applications_by_unit_id = _forced_applications_by_unit_id(applications)
    identity_rows = _historical_rules_unit_identity_rows(
        state=state,
        active_attached_ids=active_attached_ids,
    )
    candidates = tuple(
        _candidate_from_historical_rows(
            state=state,
            unit_instance_id=unit_instance_id,
            owner_player_id=owner_player_id,
            component_unit_instance_ids=component_unit_instance_ids,
            all_model_instance_ids=model_instance_ids,
            physical_by_model_id=physical_by_model_id,
            is_battle_shocked=unit_instance_id in shocked_ids,
            forced_applications=applications_by_unit_id.get(unit_instance_id, ()),
        )
        for (
            unit_instance_id,
            owner_player_id,
            component_unit_instance_ids,
            model_instance_ids,
        ) in identity_rows
        if owner_player_id == active_player_id
        and any(_is_alive(physical_by_model_id.get(model_id)) for model_id in model_instance_ids)
    )
    expected_forced_ids = set(applications_by_unit_id)
    if expected_forced_ids - {candidate.unit_instance_id for candidate in candidates}:
        raise GameLifecycleError("Command Battle-shock forced-test target is not a candidate.")
    return candidates


def _historical_rules_unit_identity_rows(
    *,
    state: GameState,
    active_attached_ids: set[str],
) -> tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...]:
    physical = {
        unit.unit_instance_id: (
            army.player_id,
            tuple(model.model_instance_id for model in unit.own_models),
        )
        for army in state.army_definitions
        for unit in army.units
    }
    grouped_component_ids: set[str] = set()
    rows: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = []
    for record in state.starting_attached_unit_records:
        if record.attached_unit_instance_id not in active_attached_ids:
            continue
        grouped_component_ids.update(record.component_unit_instance_ids)
        model_ids = tuple(
            model_id
            for component_id in record.component_unit_instance_ids
            for model_id in physical[component_id][1]
        )
        rows.append(
            (
                record.attached_unit_instance_id,
                record.player_id,
                tuple(sorted(record.component_unit_instance_ids)),
                model_ids,
            )
        )
    rows.extend(
        (unit_id, owner_id, (unit_id,), model_ids)
        for unit_id, (owner_id, model_ids) in physical.items()
        if unit_id not in grouped_component_ids
    )
    return tuple(sorted(rows))


def _candidate_from_historical_rows(
    *,
    state: GameState,
    unit_instance_id: str,
    owner_player_id: str,
    component_unit_instance_ids: tuple[str, ...],
    all_model_instance_ids: tuple[str, ...],
    physical_by_model_id: dict[str, PhysicalModelAuthority],
    is_battle_shocked: bool,
    forced_applications: tuple[BattleShockForcedTestApplication, ...],
) -> CommandBattleShockCandidate:
    applications = forced_applications
    alive_model_ids = tuple(
        sorted(
            model_id
            for model_id in all_model_instance_ids
            if _is_alive(physical_by_model_id.get(model_id))
        )
    )
    starting_model_count, single_model_starting_wounds = _starting_strength(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    single_model_wounds_remaining = None
    if starting_model_count == 1:
        row = physical_by_model_id[all_model_instance_ids[0]]
        single_model_wounds_remaining = row.wounds_remaining
    context = BelowHalfStrengthContext(
        player_id=owner_player_id,
        unit_instance_id=unit_instance_id,
        starting_model_count=starting_model_count,
        current_model_count=len(alive_model_ids),
        single_model_starting_wounds=single_model_starting_wounds,
        single_model_wounds_remaining=single_model_wounds_remaining,
    )
    reasons: list[CommandBattleShockEligibilityReason] = []
    if is_battle_shocked:
        reasons.append(CommandBattleShockEligibilityReason.CURRENTLY_BATTLE_SHOCKED)
    if context.is_at_or_below_half_strength:
        reasons.append(CommandBattleShockEligibilityReason.AT_OR_BELOW_HALF_STRENGTH)
    if applications:
        reasons.append(CommandBattleShockEligibilityReason.BELOW_STARTING_STRENGTH_FORCED)
    return CommandBattleShockCandidate(
        unit_instance_id=unit_instance_id,
        component_unit_instance_ids=tuple(sorted(component_unit_instance_ids)),
        is_battle_shocked=is_battle_shocked,
        forced_test_applications=applications,
        below_half_strength_context=context,
        eligibility_reasons=tuple(reasons),
    )


def _starting_strength(*, state: GameState, unit_instance_id: str) -> tuple[int, int | None]:
    records = tuple(
        record
        for record in state.starting_strength_records
        if record.unit_instance_id == unit_instance_id
    )
    if len(records) == 1:
        return records[0].starting_model_count, records[0].single_model_starting_wounds
    attached = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == unit_instance_id
    )
    if len(attached) != 1:
        raise GameLifecycleError("Command Battle-shock starting-strength authority drifted.")
    return attached[0].starting_model_count, None


def _forced_applications_by_unit_id(
    applications: tuple[BattleShockForcedTestApplication, ...],
) -> dict[str, tuple[BattleShockForcedTestApplication, ...]]:
    grouped: dict[str, list[BattleShockForcedTestApplication]] = {}
    for application in applications:
        for unit_id in application.unit_instance_ids:
            grouped.setdefault(unit_id, []).append(
                BattleShockForcedTestApplication(
                    hook_id=application.hook_id,
                    source_id=application.source_id,
                    unit_instance_ids=(unit_id,),
                )
            )
    return {unit_id: tuple(rows) for unit_id, rows in grouped.items()}


def _is_alive(row: PhysicalModelAuthority | None) -> bool:
    return row is not None and row.presence != "destroyed" and row.wounds_remaining > 0


def _candidates(value: JsonValue) -> tuple[CommandBattleShockCandidate, ...]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise GameLifecycleError("Command Battle-shock candidate payload is invalid.")
    try:
        return tuple(
            CommandBattleShockCandidate.from_payload(cast(CommandBattleShockCandidatePayload, row))
            for row in value
            if isinstance(row, dict)
        )
    except KeyError as exc:
        raise GameLifecycleError("Command Battle-shock candidate payload is incomplete.") from exc


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Command Battle-shock snapshot payload must be an object.")
    return value


def _positive_int(value: JsonValue, *, field: str) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Command Battle-shock {field} is invalid.")
    return value


def _player_id(value: JsonValue, *, state: GameState) -> str:
    if type(value) is not str or value not in state.player_ids:
        raise GameLifecycleError("Command Battle-shock active player is invalid.")
    return value


def _identifier_list(value: JsonValue, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise GameLifecycleError(f"Command Battle-shock {field} is invalid.")
    identifiers = tuple(cast(list[str], value))
    if identifiers != tuple(sorted(set(identifiers))):
        raise GameLifecycleError(f"Command Battle-shock {field} must be sorted and unique.")
    return identifiers


__all__ = (
    "validate_historical_command_candidate_inventory",
    "validate_loaded_command_battle_shock_authority",
)
