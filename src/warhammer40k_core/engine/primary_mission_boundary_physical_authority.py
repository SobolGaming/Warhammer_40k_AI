from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementPayload,
    UnitPlacement,
    UnitPlacementPayload,
)
from warhammer40k_core.engine.battlefield_transition_history import (
    authoritative_battlefield_transition_batch_or_none,
)
from warhammer40k_core.engine.charge_move_event_authority import (
    validate_charge_move_completed_event_authority,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageApplicationPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.emergency_disembark import (
    transport_hazard_mortal_wounds_from_completion_event,
)
from warhammer40k_core.engine.event_log import EventLog, EventRecord
from warhammer40k_core.engine.mortal_wound_application_authority import (
    direct_mortal_wound_damage_snapshot_from_event,
    validate_direct_mortal_wound_application_event_authority,
)
from warhammer40k_core.engine.objective_control_record_authority import (
    objective_control_record_hash,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
)
from warhammer40k_core.engine.primary_mission_event_decision_authority import (
    validate_primary_mission_movement_event_decision_authority,
)
from warhammer40k_core.engine.primary_mission_fight_on_death_physical_history import (
    PhysicalAuthorityState as _PhysicalAuthority,
)
from warhammer40k_core.engine.primary_mission_fight_on_death_physical_history import (
    apply_fight_on_death_awaiting as _apply_fight_on_death_awaiting,
)
from warhammer40k_core.engine.primary_mission_fight_on_death_physical_history import (
    apply_fight_on_death_removed as _apply_fight_on_death_removed,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PrimaryScoringBoundaryStatus,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_BOUNDARY_KIND,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    primary_scoring_commit_checkpoint_from_events,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
)
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE,
    PendingReturnOnDeath,
    PendingReturnOnDeathPayload,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
)
from warhammer40k_core.engine.scoring import (
    PrimaryUnitDestructionState,
    PrimaryUnitDestructionStatePayload,
)
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DestroyedTransportHazardRolls,
    DisembarkModeKind,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    model_restoration_events_for_event_log_interval,
)
from warhammer40k_core.geometry.pose import Pose

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_DESPERATE_ESCAPE_DEPARTURE_SOURCE_PREFIX = "core-rules:desperate-escape:"
_EMERGENCY_DISEMBARK_DEPARTURE_SOURCE_PREFIX = "core-rules:emergency-disembark:"


@dataclass(frozen=True, slots=True)
class PhysicalModelAuthority:
    """Exact authenticated physical state for one model at an event boundary."""

    model_instance_id: str
    presence: str
    pose: Pose | None
    wounds_remaining: int

    def __post_init__(self) -> None:
        if type(self.model_instance_id) is not str or not self.model_instance_id:
            raise GameLifecycleError("Physical model authority identity is invalid.")
        if self.presence not in {
            "battlefield",
            "destroyed",
            "embarked",
            "reserves",
            "off_battlefield",
        }:
            raise GameLifecycleError("Physical model authority presence is invalid.")
        if type(self.wounds_remaining) is not int or self.wounds_remaining < 0:
            raise GameLifecycleError("Physical model authority wounds are invalid.")
        if self.presence == "battlefield":
            if type(self.pose) is not Pose or self.wounds_remaining < 1:
                raise GameLifecycleError(
                    "Battlefield physical model authority requires a living pose."
                )
        elif self.pose is not None:
            raise GameLifecycleError(
                "Off-battlefield physical model authority must not retain a pose."
            )


def physical_model_authority_before_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
) -> tuple[PhysicalModelAuthority, ...]:
    """Reconstruct exact physical rows before one event and bind them to final state."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Physical event-bound authority requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Physical event-bound authority requires events.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Physical event-bound authority requires decisions.")
    if type(event_index) is not int or not 0 <= event_index < len(event_records):
        raise GameLifecycleError("Physical event-bound authority index is invalid.")

    validate_direct_mortal_wound_application_event_authority(
        state=state,
        event_records=event_records,
    )
    _validate_model_restoration_event_decision_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_physical_transition_decision_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    if any(event.event_type == "fight_on_death_model_awaiting_attack" for event in event_records):
        from warhammer40k_core.engine.fight_model_authority_history import (
            build_model_authority_timeline,
        )

        build_model_authority_timeline(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
        )

    current = _current_authority_by_model(state=state)
    current_model_ids = frozenset(current)
    initial_model_ids = _initial_model_ids(state=state)
    if not initial_model_ids <= current_model_ids:
        raise GameLifecycleError("Physical event-bound initial model inventory drifted.")
    model_ids_by_rules_unit_id = _model_ids_by_rules_unit_id(state=state)
    starting_wounds_by_model_id = _starting_wounds_by_model_id(state=state)
    destruction_by_id = _primary_unit_destruction_by_id(state=state)
    departure_by_id = _primary_battlefield_departure_by_id(state=state)
    no_trigger_destroyed_departure_ids = _no_trigger_destroyed_departure_ids(state=state)
    before = _physical_authority_before_event(
        event_records=event_records,
        event_index=event_index,
        expected_game_id=state.game_id,
        expected_battlefield_id=_current_battlefield_id(state=state),
        allowed_model_ids=current_model_ids,
        initial_model_ids=initial_model_ids,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )
    if not frozenset(before) <= current_model_ids:
        raise GameLifecycleError("Physical event-bound model inventory drifted.")
    replay_start_index = event_index
    forward_anchor = _forward_scoring_commit_anchor_or_none(
        state=state,
        event_records=event_records,
        event_index=event_index,
        expected_game_id=state.game_id,
        expected_battlefield_id=_current_battlefield_id(state=state),
        allowed_model_ids=current_model_ids,
        initial_model_ids=initial_model_ids,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )
    if forward_anchor is not None:
        anchor_index, checkpoint, anchor_authority = forward_anchor
        for row in checkpoint.model_states:
            preceding = before.get(row.model_instance_id)
            if preceding is not None:
                _validate_row_against_authority(
                    row=row,
                    authority=preceding,
                    context="preceding",
                )
        before.update(anchor_authority)
        replay_start_index = anchor_index + 1
    later_without_initial = _physical_authority_by_model(
        event_records[replay_start_index:],
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )
    for model_instance_id, current_authority in current.items():
        prior = before.get(model_instance_id)
        if (
            prior is not None
            and prior.presence is not None
            and prior.wounds_remaining is not None
            and (prior.presence != "battlefield" or prior.pose is not None)
        ):
            continue
        if model_instance_id in later_without_initial:
            raise GameLifecycleError(
                "Physical event-bound history lacks an exact pre-mutation anchor."
            )
        before[model_instance_id] = current_authority
    later = _physical_authority_by_model(
        event_records[replay_start_index:],
        initial=before,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )
    for model_instance_id, authority in later.items():
        terminal_authority = current.get(model_instance_id)
        if terminal_authority is None:
            raise GameLifecycleError("Physical event-bound model inventory drifted.")
        _validate_authority_against_current(
            model_instance_id=model_instance_id,
            authority=authority,
            current=terminal_authority,
        )

    rows: list[PhysicalModelAuthority] = []
    for model_instance_id, authority in sorted(before.items()):
        if authority.presence is None or authority.wounds_remaining is None:
            raise GameLifecycleError("Physical event-bound authority is incomplete.")
        if authority.presence == "battlefield" and authority.pose is None:
            raise GameLifecycleError(
                "Physical event-bound battlefield model lacks exact pose authority."
            )
        rows.append(
            PhysicalModelAuthority(
                model_instance_id=model_instance_id,
                presence=authority.presence,
                pose=authority.pose,
                wounds_remaining=authority.wounds_remaining,
            )
        )
    return tuple(rows)


def _forward_scoring_commit_anchor_or_none(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    expected_game_id: str,
    expected_battlefield_id: str,
    allowed_model_ids: frozenset[str],
    initial_model_ids: frozenset[str],
    model_ids_by_rules_unit_id: dict[str, tuple[str, ...]],
    starting_wounds_by_model_id: dict[str, int],
    destruction_by_id: dict[str, PrimaryUnitDestructionState],
    departure_by_id: dict[str, PrimaryBattlefieldDepartureState],
    no_trigger_destroyed_departure_ids: frozenset[str],
) -> (
    tuple[
        int,
        PrimaryMissionBoundaryCheckpoint,
        dict[str, _PhysicalAuthority],
    ]
    | None
):
    """Return the first exact scoring checkpoint before any later physical mutation."""

    for anchor_index, event in enumerate(
        event_records[event_index:],
        start=event_index,
    ):
        if _physical_authority_by_model(
            (event,),
            model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
            starting_wounds_by_model_id=starting_wounds_by_model_id,
            destruction_by_id=destruction_by_id,
            departure_by_id=departure_by_id,
            no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
        ):
            return None
        if event.event_type != PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT:
            continue
        checkpoint = _authenticated_scoring_commit_checkpoint(
            state=state,
            event_records=event_records,
            anchor_index=anchor_index,
        )
        authority = _checkpoint_authority(
            checkpoint=checkpoint,
            expected_game_id=expected_game_id,
            expected_battlefield_id=expected_battlefield_id,
            allowed_model_ids=allowed_model_ids,
            required_model_ids=initial_model_ids,
        )
        if frozenset(authority) != allowed_model_ids:
            raise GameLifecycleError("Primary scoring-commit physical anchor inventory drifted.")
        return anchor_index, checkpoint, authority
    return None


def _authenticated_scoring_commit_checkpoint(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    anchor_index: int,
) -> PrimaryMissionBoundaryCheckpoint:
    event = event_records[anchor_index]
    if event.event_id != f"event-{anchor_index + 1:06d}":
        raise GameLifecycleError("Primary scoring-commit physical anchor event order drifted.")
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary scoring-commit physical anchor payload is invalid.")
    raw_record_id = event.payload.get("objective_control_record_id")
    raw_boundary_kind = event.payload.get("scoring_boundary_kind")
    if type(raw_record_id) is not str or not raw_record_id:
        raise GameLifecycleError(
            "Primary scoring-commit physical anchor record identity is invalid."
        )
    if raw_boundary_kind not in {
        PrimaryScoringBoundaryKind.ORDINARY.value,
        PrimaryScoringBoundaryKind.END_OF_BATTLE.value,
    }:
        raise GameLifecycleError("Primary scoring-commit physical anchor boundary kind is invalid.")
    boundary_kind = PrimaryScoringBoundaryKind(raw_boundary_kind)
    bound_index, checkpoint = primary_scoring_commit_checkpoint_from_events(
        event_records=event_records,
        objective_control_record_id=raw_record_id,
        scoring_boundary_kind=boundary_kind.value,
    )
    if bound_index != anchor_index:
        raise GameLifecycleError("Primary scoring-commit physical anchor occurrence drifted.")
    records = tuple(
        record for record in state.objective_control_records if record.record_id == raw_record_id
    )
    if len(records) != 1:
        raise GameLifecycleError(
            "Primary scoring-commit physical anchor Objective Control record drifted."
        )
    record = records[0]
    evidences = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.objective_control_record_id == raw_record_id
        and evidence.scoring_boundary_kind is boundary_kind
    )
    lifecycles = tuple(
        lifecycle
        for lifecycle in state.primary_scoring_boundary_lifecycles
        if lifecycle.objective_control_record_id == raw_record_id
        and lifecycle.scoring_boundary_kind is boundary_kind
    )
    if len(evidences) != 1 or len(lifecycles) != 1:
        raise GameLifecycleError(
            "Primary scoring-commit physical anchor retained authority drifted."
        )
    evidence = evidences[0]
    lifecycle = lifecycles[0]
    if (
        lifecycle.status is not PrimaryScoringBoundaryStatus.RESOLVED
        or lifecycle.scoring_commit_checkpoint_id != checkpoint.checkpoint_id
        or lifecycle.scoring_commit_checkpoint_hash != checkpoint.checkpoint_hash
        or evidence.scoring_commit_checkpoint_id != checkpoint.checkpoint_id
        or evidence.scoring_commit_checkpoint_hash != checkpoint.checkpoint_hash
        or evidence.objective_control_record_hash != objective_control_record_hash(record)
    ):
        raise GameLifecycleError("Primary scoring-commit physical anchor hash binding drifted.")
    if (
        checkpoint.boundary_kind != PRIMARY_SCORING_COMMIT_BOUNDARY_KIND
        or checkpoint.game_id != record.game_id
        or checkpoint.player_id != record.active_player_id
        or checkpoint.active_player_id != record.active_player_id
        or checkpoint.battle_round != record.battle_round
        or checkpoint.phase != record.phase
        or checkpoint.battlefield_id != record.battlefield_id
        or evidence.game_id != record.game_id
        or evidence.active_player_id != record.active_player_id
        or evidence.battle_round != record.battle_round
        or evidence.phase != record.phase
        or evidence.battlefield_id != record.battlefield_id
    ):
        raise GameLifecycleError("Primary scoring-commit physical anchor context drifted.")
    return checkpoint


def primary_mission_model_placements_from_checkpoint(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[ModelPlacement, ...]:
    """Return exact placements frozen by one authenticated boundary checkpoint."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary mission checkpoint positions require GameState.")
    if type(checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError("Primary mission checkpoint positions require a typed checkpoint.")
    current_model_ids = frozenset(_current_authority_by_model(state=state))
    initial_model_ids = _initial_model_ids(state=state)
    if not initial_model_ids <= current_model_ids:
        raise GameLifecycleError("Primary mission initial model inventory drifted.")
    authority = _checkpoint_authority(
        checkpoint=checkpoint,
        expected_game_id=state.game_id,
        expected_battlefield_id=_current_battlefield_id(state=state),
        allowed_model_ids=current_model_ids,
        required_model_ids=initial_model_ids,
    )
    return _model_placements_from_authority(state=state, authority=authority)


def _model_placements_from_authority(
    *,
    state: GameState,
    authority: dict[str, _PhysicalAuthority],
) -> tuple[ModelPlacement, ...]:
    identity_by_model_id = {
        model.model_instance_id: (
            army.army_id,
            army.player_id,
            unit.unit_instance_id,
        )
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    placements: list[ModelPlacement] = []
    for model_instance_id, row in sorted(authority.items()):
        identity = identity_by_model_id.get(model_instance_id)
        if identity is None:
            raise GameLifecycleError("Primary scoring position history model inventory drifted.")
        if row.presence != "battlefield":
            continue
        if row.pose is None:
            raise GameLifecycleError(
                "Primary scoring position history battlefield model lacks a pose."
            )
        army_id, player_id, unit_instance_id = identity
        placements.append(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                model_instance_id=model_instance_id,
                pose=row.pose,
            )
        )
    return tuple(placements)


def validate_primary_mission_boundary_physical_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    validate_direct_mortal_wound_application_event_authority(
        state=state,
        event_records=event_records,
    )
    _validate_model_restoration_event_decision_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_physical_transition_decision_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    current = _current_authority_by_model(state=state)
    current_model_ids = frozenset(current)
    initial_model_ids = _initial_model_ids(state=state)
    model_ids_by_rules_unit_id = _model_ids_by_rules_unit_id(state=state)
    starting_wounds_by_model_id = _starting_wounds_by_model_id(state=state)
    destruction_by_id = _primary_unit_destruction_by_id(state=state)
    departure_by_id = _primary_battlefield_departure_by_id(state=state)
    no_trigger_destroyed_departure_ids = _no_trigger_destroyed_departure_ids(state=state)
    if not initial_model_ids <= current_model_ids:
        raise GameLifecycleError("Primary mission initial model inventory drifted.")
    before = _physical_authority_before_checkpoint(
        event_records=event_records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
        allowed_model_ids=current_model_ids,
        initial_model_ids=initial_model_ids,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )
    checkpoint_authority = _checkpoint_authority(
        checkpoint=checkpoint,
        expected_game_id=state.game_id,
        expected_battlefield_id=_current_battlefield_id(state=state),
        allowed_model_ids=current_model_ids,
        required_model_ids=frozenset(before) | initial_model_ids,
    )
    later_records = event_records[checkpoint_index + 1 :]
    later = _physical_authority_by_model(
        later_records,
        initial=checkpoint_authority,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )
    for row in checkpoint.model_states:
        preceding = before.get(row.model_instance_id)
        if preceding is not None:
            _validate_row_against_authority(row=row, authority=preceding, context="preceding")
    for model_instance_id, authority in later.items():
        current_authority = current.get(model_instance_id)
        if current_authority is None:
            raise GameLifecycleError("Primary mission physical history model inventory drifted.")
        _validate_authority_against_current(
            model_instance_id=model_instance_id,
            authority=authority,
            current=current_authority,
        )


def primary_mission_boundary_physical_event_model_ids(event: EventRecord) -> tuple[str, ...]:
    """Return model IDs mutated by an authenticated physical event family."""

    return tuple(sorted(_physical_authority_by_model((event,))))


def _validate_model_restoration_event_decision_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if not any(
        event.event_type
        in {
            "healing_step_resolved",
            RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE,
        }
        for event in event_records
    ):
        return
    event_log = EventLog.from_payload([event.to_payload() for event in event_records])
    model_restoration_events_for_event_log_interval(
        state=state,
        event_log=event_log,
        start_order_exclusive=-1,
        decision_records=decision_records,
    )


def _physical_authority_by_model(
    event_records: tuple[EventRecord, ...],
    *,
    initial: dict[str, _PhysicalAuthority] | None = None,
    model_ids_by_rules_unit_id: dict[str, tuple[str, ...]] | None = None,
    starting_wounds_by_model_id: dict[str, int] | None = None,
    destruction_by_id: dict[str, PrimaryUnitDestructionState] | None = None,
    departure_by_id: dict[str, PrimaryBattlefieldDepartureState] | None = None,
    no_trigger_destroyed_departure_ids: frozenset[str] = frozenset(),
) -> dict[str, _PhysicalAuthority]:
    authority = {} if initial is None else dict(initial)
    applied_fall_back_transitions: dict[tuple[str, str], BattlefieldTransitionBatch] = {}
    applied_direct_mortal_wound_damage: dict[str, set[DamageApplication]] = {}
    for event in event_records:
        damage_snapshot = direct_mortal_wound_damage_snapshot_from_event(event)
        if damage_snapshot is not None:
            application_id, applications = damage_snapshot
            applied = applied_direct_mortal_wound_damage.setdefault(application_id, set())
            for damage in applications:
                if damage in applied:
                    continue
                _apply_damage_application(authority=authority, damage=damage)
                applied.add(damage)
        transport_hazard = transport_hazard_mortal_wounds_from_completion_event(event)
        if (
            transport_hazard is not None
            and type(transport_hazard.disembark) is DestroyedTransportHazardRolls
            and transport_hazard.mortal_wound_application is not None
        ):
            for damage in transport_hazard.mortal_wound_application.applications:
                _apply_damage_application(authority=authority, damage=damage)
        transition = authoritative_battlefield_transition_batch_or_none(event=event)
        if event.event_type == "fall_back_move_applied":
            transition = authoritative_battlefield_transition_batch_or_none(
                event=EventRecord(
                    event_id=event.event_id,
                    event_type="movement_activation_completed",
                    payload=event.payload,
                )
            )
            event_key = _movement_event_key(event)
            if transition is None or event_key in applied_fall_back_transitions:
                raise GameLifecycleError("Fall Back applied transition authority drifted.")
            applied_fall_back_transitions[event_key] = transition
        elif event.event_type == "movement_activation_completed":
            event_key = _movement_event_key(event)
            applied_transition = applied_fall_back_transitions.get(event_key)
            if applied_transition is not None:
                if transition != applied_transition:
                    raise GameLifecycleError("Fall Back terminal transition authority drifted.")
                transition = None
            elif (
                isinstance(event.payload, dict)
                and event.payload.get("fall_back_applied_event_id") is not None
            ):
                transition = None
        if transition is not None:
            _apply_transition(
                authority=authority,
                transition=transition,
                starting_wounds_by_model_id=starting_wounds_by_model_id,
                preserve_destroyed_wounds_for_model_ids=(
                    _desperate_escape_transition_model_ids(
                        event=event,
                        departure_by_id=departure_by_id,
                    )
                ),
            )
        if event.event_type == "unit_disembarked":
            _apply_destroyed_transport_disembark_omitted_model_destruction(
                authority=authority,
                event=event,
            )
        if event.event_type == "attack_sequence_step":
            _apply_damage_step(authority=authority, event=event)
        elif event.event_type == "healing_step_resolved":
            _apply_healing_step(
                authority=authority,
                event=event,
                starting_wounds_by_model_id=starting_wounds_by_model_id,
            )
        elif event.event_type == "model_destroyed":
            _apply_model_destroyed(authority=authority, event=event)
        elif event.event_type == "fight_on_death_model_awaiting_attack":
            _apply_fight_on_death_awaiting(authority=authority, event=event)
        elif event.event_type == "fight_on_death_models_removed":
            _apply_fight_on_death_removed(authority=authority, event=event)
        elif event.event_type == "primary_battlefield_departure_recorded":
            _apply_departure(
                authority=authority,
                event=event,
                departure_by_id=departure_by_id,
                no_trigger_destroyed_departure_ids=(no_trigger_destroyed_departure_ids),
            )
        elif event.event_type == "primary_unit_destruction_recorded":
            _apply_primary_unit_destruction(
                authority=authority,
                event=event,
                model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
                destruction_by_id=destruction_by_id,
            )
        elif event.event_type == RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE:
            _apply_return_on_death_restoration(
                authority=authority,
                event=event,
                starting_wounds_by_model_id=starting_wounds_by_model_id,
            )
    return authority


def _apply_destroyed_transport_disembark_omitted_model_destruction(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Destroyed Transport disembark authority payload is invalid.")
    raw_disembark = event.payload.get("destroyed_transport_disembark")
    if raw_disembark is None:
        return
    if not isinstance(raw_disembark, dict):
        raise GameLifecycleError("Destroyed Transport disembark authority is invalid.")
    try:
        disembark = DestroyedTransportDisembark.from_payload(
            cast(DestroyedTransportDisembarkPayload, raw_disembark)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Destroyed Transport disembark authority is invalid.") from exc
    if not disembark.destroyed_model_instance_ids:
        return
    if disembark.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
        raise GameLifecycleError("Destroyed Transport omitted-model authority mode drift.")
    placed_model_ids = {
        placement.model_instance_id
        for placement in disembark.placement.selection.attempted_placement.model_placements
    }
    if placed_model_ids.intersection(disembark.destroyed_model_instance_ids):
        raise GameLifecycleError("Destroyed Transport omitted-model authority overlaps placement.")
    for model_id in disembark.destroyed_model_instance_ids:
        prior = authority.get(model_id)
        if prior is not None and prior.presence == "battlefield":
            raise GameLifecycleError("Destroyed Transport omitted-model history is discontinuous.")
        authority[model_id] = _PhysicalAuthority(
            presence="destroyed",
            pose=None,
            wounds_remaining=0,
        )


def _physical_authority_before_checkpoint(
    *,
    event_records: tuple[EventRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    allowed_model_ids: frozenset[str],
    initial_model_ids: frozenset[str],
    model_ids_by_rules_unit_id: dict[str, tuple[str, ...]],
    starting_wounds_by_model_id: dict[str, int],
    destruction_by_id: dict[str, PrimaryUnitDestructionState],
    departure_by_id: dict[str, PrimaryBattlefieldDepartureState],
    no_trigger_destroyed_departure_ids: frozenset[str],
) -> dict[str, _PhysicalAuthority]:
    return _physical_authority_before_event(
        event_records=event_records,
        event_index=checkpoint_index,
        expected_game_id=checkpoint.game_id,
        expected_battlefield_id=checkpoint.battlefield_id,
        allowed_model_ids=allowed_model_ids,
        initial_model_ids=initial_model_ids,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )


def _physical_authority_before_event(
    *,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    expected_game_id: str,
    expected_battlefield_id: str,
    allowed_model_ids: frozenset[str],
    initial_model_ids: frozenset[str],
    model_ids_by_rules_unit_id: dict[str, tuple[str, ...]],
    starting_wounds_by_model_id: dict[str, int],
    destruction_by_id: dict[str, PrimaryUnitDestructionState],
    departure_by_id: dict[str, PrimaryBattlefieldDepartureState],
    no_trigger_destroyed_departure_ids: frozenset[str],
) -> dict[str, _PhysicalAuthority]:
    authority: dict[str, _PhysicalAuthority] = {}
    segment_start = 0
    for prior_index, event in enumerate(event_records[:event_index]):
        if event.event_type != PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT:
            continue
        authority = _physical_authority_by_model(
            event_records[segment_start:prior_index],
            initial=authority,
            model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
            starting_wounds_by_model_id=starting_wounds_by_model_id,
            destruction_by_id=destruction_by_id,
            departure_by_id=departure_by_id,
            no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
        )
        prior_checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(event.payload)
        seeded = _checkpoint_authority(
            checkpoint=prior_checkpoint,
            expected_game_id=expected_game_id,
            expected_battlefield_id=expected_battlefield_id,
            allowed_model_ids=allowed_model_ids,
            required_model_ids=frozenset(authority) | initial_model_ids,
        )
        for row in prior_checkpoint.model_states:
            preceding = authority.get(row.model_instance_id)
            if preceding is not None:
                _validate_row_against_authority(
                    row=row,
                    authority=preceding,
                    context="preceding",
                )
        authority.update(seeded)
        segment_start = prior_index + 1
    return _physical_authority_by_model(
        event_records[segment_start:event_index],
        initial=authority,
        model_ids_by_rules_unit_id=model_ids_by_rules_unit_id,
        starting_wounds_by_model_id=starting_wounds_by_model_id,
        destruction_by_id=destruction_by_id,
        departure_by_id=departure_by_id,
        no_trigger_destroyed_departure_ids=no_trigger_destroyed_departure_ids,
    )


def _checkpoint_authority(
    *,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    expected_game_id: str,
    expected_battlefield_id: str,
    allowed_model_ids: frozenset[str],
    required_model_ids: frozenset[str],
) -> dict[str, _PhysicalAuthority]:
    if (
        checkpoint.game_id != expected_game_id
        or checkpoint.battlefield_id != expected_battlefield_id
    ):
        raise GameLifecycleError("Primary mission checkpoint physical context drifted.")
    authority = {
        row.model_instance_id: _PhysicalAuthority(
            presence=row.presence,
            pose=_checkpoint_pose(row),
            wounds_remaining=row.wounds_remaining,
        )
        for row in checkpoint.model_states
    }
    if len(authority) != len(checkpoint.model_states):
        raise GameLifecycleError("Primary mission checkpoint model authority is duplicated.")
    checkpoint_model_ids = frozenset(authority)
    if not checkpoint_model_ids <= allowed_model_ids:
        raise GameLifecycleError("Primary mission checkpoint model authority inventory drifted.")
    if not required_model_ids <= checkpoint_model_ids:
        raise GameLifecycleError("Primary mission checkpoint model authority inventory regressed.")
    return authority


def _apply_transition(
    *,
    authority: dict[str, _PhysicalAuthority],
    transition: BattlefieldTransitionBatch,
    starting_wounds_by_model_id: dict[str, int] | None = None,
    preserve_destroyed_wounds_for_model_ids: frozenset[str] = frozenset(),
) -> None:
    for placement in transition.placements:
        prior = authority.get(placement.model_instance_id)
        if prior is not None and prior.presence == "battlefield":
            raise GameLifecycleError("Primary mission placement history starts on battlefield.")
        authority[placement.model_instance_id] = _PhysicalAuthority(
            presence="battlefield",
            pose=placement.pose,
            wounds_remaining=(
                _starting_wounds_for_initial_placement(
                    model_instance_id=placement.model_instance_id,
                    starting_wounds_by_model_id=starting_wounds_by_model_id,
                )
                if prior is None
                else prior.wounds_remaining
            ),
        )
    for displacement in transition.displacements:
        prior = authority.get(displacement.model_instance_id)
        if prior is not None and (
            prior.presence != "battlefield" or prior.pose != displacement.start_pose
        ):
            raise GameLifecycleError("Primary mission displacement history is discontinuous.")
        authority[displacement.model_instance_id] = _PhysicalAuthority(
            presence="battlefield",
            pose=displacement.end_pose,
            wounds_remaining=None if prior is None else prior.wounds_remaining,
        )
    for removal in transition.removals:
        prior = authority.get(removal.model_instance_id)
        preserve_destroyed_wounds = (
            removal.removal_kind is BattlefieldRemovalKind.DESTROYED
            and removal.model_instance_id in preserve_destroyed_wounds_for_model_ids
        )
        if (
            prior is not None
            and prior.presence != "battlefield"
            and not (preserve_destroyed_wounds and prior.presence == "off_battlefield")
        ):
            raise GameLifecycleError("Primary mission removal history is discontinuous.")
        if preserve_destroyed_wounds and prior is not None and prior.presence == "off_battlefield":
            continue
        authority[removal.model_instance_id] = _authority_after_removal(
            prior=prior,
            removal_kind=removal.removal_kind,
            preserve_wounds_on_destroyed=preserve_destroyed_wounds,
        )


def _starting_wounds_for_initial_placement(
    *,
    model_instance_id: str,
    starting_wounds_by_model_id: dict[str, int] | None,
) -> int | None:
    if starting_wounds_by_model_id is None:
        return None
    wounds = starting_wounds_by_model_id.get(model_instance_id)
    if wounds is None:
        raise GameLifecycleError("Physical placement model lacks starting-wounds authority.")
    return wounds


def _desperate_escape_transition_model_ids(
    *,
    event: EventRecord,
    departure_by_id: dict[str, PrimaryBattlefieldDepartureState] | None,
) -> frozenset[str]:
    if event.event_type not in {"fall_back_move_applied", "movement_activation_completed"}:
        return frozenset()
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission movement event payload is invalid.")
    movement_payload = event.payload
    if event.event_type == "fall_back_move_applied":
        raw_movement_payload = event.payload.get("movement_payload")
        if not isinstance(raw_movement_payload, dict):
            raise GameLifecycleError("Primary mission Fall Back applied payload is invalid.")
        movement_payload = raw_movement_payload
    mutation_id = movement_payload.get("desperate_escape_source_mutation_id")
    if mutation_id is None:
        return frozenset()
    if type(mutation_id) is not str or not mutation_id:
        raise GameLifecycleError("Primary mission Desperate Escape mutation identity is invalid.")
    raw_model_ids = movement_payload.get("destroyed_model_ids")
    if not isinstance(raw_model_ids, list) or any(
        type(model_id) is not str or not model_id for model_id in raw_model_ids
    ):
        raise GameLifecycleError("Primary mission Desperate Escape model evidence is invalid.")
    event_model_ids = frozenset(cast(list[str], raw_model_ids))
    if len(event_model_ids) != len(raw_model_ids):
        raise GameLifecycleError("Primary mission Desperate Escape model evidence is duplicated.")
    if departure_by_id is None:
        return event_model_ids
    expected_source_prefix = f"{_DESPERATE_ESCAPE_DEPARTURE_SOURCE_PREFIX}{mutation_id}:"
    departure_model_ids = frozenset(
        model_id
        for departure in departure_by_id.values()
        if departure.source_id.startswith(expected_source_prefix)
        for model_id in departure.removed_model_instance_ids
    )
    if event_model_ids != departure_model_ids:
        raise GameLifecycleError("Primary mission Desperate Escape departure evidence drifted.")
    return event_model_ids


def _movement_event_key(event: EventRecord) -> tuple[str, str]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Physical movement event payload is invalid.")
    request_id = event.payload.get("request_id")
    result_id = event.payload.get("result_id")
    if type(request_id) is not str or not request_id or type(result_id) is not str or not result_id:
        raise GameLifecycleError("Physical movement event decision identity is invalid.")
    return request_id, result_id


def _apply_damage_step(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict) or event.payload.get("step") != "damage":
        return
    step_payload = event.payload.get("payload")
    if not isinstance(step_payload, dict):
        raise GameLifecycleError("Primary mission damage-step payload is invalid.")
    raw_damage = step_payload.get("damage_application")
    if raw_damage is None:
        return
    if not isinstance(raw_damage, dict):
        raise GameLifecycleError("Primary mission damage authority payload is invalid.")
    damage = DamageApplication.from_payload(cast(DamageApplicationPayload, raw_damage))
    _apply_damage_application(authority=authority, damage=damage)


def _apply_damage_application(
    *,
    authority: dict[str, _PhysicalAuthority],
    damage: DamageApplication,
) -> None:
    prior = authority.get(damage.model_instance_id)
    if prior is not None and (
        prior.wounds_remaining == damage.final_wounds_remaining
        and prior.presence in ({"destroyed"} if damage.destroyed else {None, "battlefield"})
    ):
        return
    if prior is not None and (
        (
            prior.wounds_remaining is not None
            and prior.wounds_remaining != damage.starting_wounds_remaining
        )
        or (prior.presence is not None and prior.presence != "battlefield")
    ):
        raise GameLifecycleError("Primary mission damage history is discontinuous.")
    authority[damage.model_instance_id] = _PhysicalAuthority(
        presence="destroyed" if damage.destroyed else None if prior is None else prior.presence,
        pose=None if damage.destroyed else None if prior is None else prior.pose,
        wounds_remaining=damage.final_wounds_remaining,
    )


def _apply_healing_step(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
    starting_wounds_by_model_id: dict[str, int] | None,
) -> None:
    from warhammer40k_core.engine.healing import (
        HealingStep,
        HealingStepKind,
        HealingStepPayload,
    )

    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission healing-step payload is invalid.")
    raw_step = event.payload.get("step")
    if not isinstance(raw_step, dict):
        raise GameLifecycleError("Primary mission healing authority payload is invalid.")
    step = HealingStep.from_payload(cast(HealingStepPayload, raw_step))
    prior = None if step.model_instance_id is None else authority.get(step.model_instance_id)
    if (
        prior is not None
        and step.starting_wounds_remaining is not None
        and prior.wounds_remaining is not None
        and prior.wounds_remaining != step.starting_wounds_remaining
    ):
        raise GameLifecycleError("Primary mission healing history is discontinuous.")
    if step.transition_batch is not None:
        _apply_transition(
            authority=authority,
            transition=step.transition_batch,
            starting_wounds_by_model_id=starting_wounds_by_model_id,
        )
    if step.model_instance_id is None or step.final_wounds_remaining is None:
        return
    updated = authority.get(step.model_instance_id)
    presence = None if updated is None else updated.presence
    pose = None if updated is None else updated.pose
    if step.step_kind is HealingStepKind.REVIVE_MODEL_EMBARKED:
        presence, pose = "embarked", None
    elif step.step_kind is HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY:
        presence, pose = "destroyed", None
    authority[step.model_instance_id] = _PhysicalAuthority(
        presence=presence,
        pose=pose,
        wounds_remaining=step.final_wounds_remaining,
    )


def _apply_model_destroyed(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission destroyed-model payload is invalid.")
    model_id = event.payload.get("model_instance_id")
    if type(model_id) is not str:
        raise GameLifecycleError("Primary mission destroyed-model identity is invalid.")
    authority[model_id] = _PhysicalAuthority(
        presence="destroyed",
        pose=None,
        wounds_remaining=0,
    )


def _apply_departure(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
    departure_by_id: dict[str, PrimaryBattlefieldDepartureState] | None,
    no_trigger_destroyed_departure_ids: frozenset[str],
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission departure payload is invalid.")
    departure = PrimaryBattlefieldDepartureState.from_payload(
        event.payload.get("primary_battlefield_departure_state")
    )
    if departure_by_id is not None and departure_by_id.get(departure.departure_id) != departure:
        raise GameLifecycleError("Primary mission departure event authority drifted.")
    for model_id in departure.removed_model_instance_ids:
        prior = authority.get(model_id)
        authority[model_id] = _authority_after_removal(
            prior=prior,
            removal_kind=departure.removal_kind,
            preserve_wounds_on_destroyed=(
                departure.departure_id in no_trigger_destroyed_departure_ids
            ),
        )


def _apply_primary_unit_destruction(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
    model_ids_by_rules_unit_id: dict[str, tuple[str, ...]] | None,
    destruction_by_id: dict[str, PrimaryUnitDestructionState] | None,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission unit-destruction payload is invalid.")
    raw_destruction = event.payload.get("primary_unit_destruction_state")
    if not isinstance(raw_destruction, dict):
        raise GameLifecycleError("Primary mission unit-destruction authority payload is invalid.")
    destruction = PrimaryUnitDestructionState.from_payload(
        cast(PrimaryUnitDestructionStatePayload, raw_destruction)
    )
    if destruction_by_id is not None and (
        destruction_by_id.get(destruction.destruction_id) != destruction
    ):
        raise GameLifecycleError("Primary mission unit-destruction event authority drifted.")
    if destruction.unattributed_cause is not PrimaryUnattributedDestructionCause.RESERVE_DEADLINE:
        return
    if model_ids_by_rules_unit_id is None:
        return
    model_ids = model_ids_by_rules_unit_id.get(destruction.destroyed_unit_instance_id)
    if model_ids is None:
        raise GameLifecycleError("Primary mission reserve destruction unit inventory drifted.")
    for model_id in model_ids:
        authority[model_id] = _authority_after_removal(
            prior=authority.get(model_id),
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            preserve_wounds_on_destroyed=True,
        )


def _apply_return_on_death_restoration(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
    starting_wounds_by_model_id: dict[str, int] | None,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission return-on-death payload is invalid.")
    raw_pending = event.payload.get("pending")
    raw_placement = event.payload.get("placement")
    if not isinstance(raw_pending, dict) or not isinstance(raw_placement, dict):
        raise GameLifecycleError("Primary mission return-on-death authority payload is invalid.")
    pending = PendingReturnOnDeath.from_payload(cast(PendingReturnOnDeathPayload, raw_pending))
    placement = UnitPlacement.from_payload(cast(UnitPlacementPayload, raw_placement))
    if not pending.resolved or placement.unit_instance_id != pending.destroyed_unit_instance_id:
        raise GameLifecycleError("Primary mission return-on-death restoration identity drifted.")
    placement_model_ids = {
        model_placement.model_instance_id for model_placement in placement.model_placements
    }
    if pending.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL and (
        placement_model_ids != {pending.destroyed_model_instance_id}
    ):
        raise GameLifecycleError("Primary mission return-on-death model inventory drifted.")
    for model_placement in placement.model_placements:
        model_id = model_placement.model_instance_id
        prior = authority.get(model_id)
        if prior is not None and prior.presence == "battlefield":
            raise GameLifecycleError("Primary mission restoration history starts on battlefield.")
        wounds_remaining = _restored_wounds_remaining(
            pending=pending,
            model_instance_id=model_id,
            starting_wounds_by_model_id=starting_wounds_by_model_id,
            prior=prior,
        )
        authority[model_id] = _PhysicalAuthority(
            presence="battlefield",
            pose=model_placement.pose,
            wounds_remaining=wounds_remaining,
        )


def _restored_wounds_remaining(
    *,
    pending: PendingReturnOnDeath,
    model_instance_id: str,
    starting_wounds_by_model_id: dict[str, int] | None,
    prior: _PhysicalAuthority | None,
) -> int | None:
    if pending.restore_wounds_mode is ReturnRestoreWoundsMode.FIXED_REMAINING:
        if pending.wounds_remaining is None:
            raise GameLifecycleError("Primary mission return-on-death wounds authority is missing.")
        return pending.wounds_remaining
    if starting_wounds_by_model_id is None:
        return None if prior is None else prior.wounds_remaining
    starting_wounds = starting_wounds_by_model_id.get(model_instance_id)
    if starting_wounds is None:
        raise GameLifecycleError("Primary mission return-on-death model inventory drifted.")
    return starting_wounds


def _authority_after_removal(
    *,
    prior: _PhysicalAuthority | None,
    removal_kind: BattlefieldRemovalKind,
    preserve_wounds_on_destroyed: bool = False,
) -> _PhysicalAuthority:
    if removal_kind is not BattlefieldRemovalKind.DESTROYED:
        return _PhysicalAuthority(
            presence=_presence_for_removal(removal_kind),
            pose=None,
            wounds_remaining=None if prior is None else prior.wounds_remaining,
        )
    if not preserve_wounds_on_destroyed:
        return _PhysicalAuthority(presence="destroyed", pose=None, wounds_remaining=0)
    if prior is None:
        return _PhysicalAuthority(presence="off_battlefield", pose=None, wounds_remaining=None)
    return _PhysicalAuthority(
        presence="destroyed" if prior.wounds_remaining == 0 else "off_battlefield",
        pose=None,
        wounds_remaining=prior.wounds_remaining,
    )


def _current_authority_by_model(*, state: GameState) -> dict[str, _PhysicalAuthority]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary mission physical authority requires battlefield state.")
    reserve_ids = set(state.unarrived_reserve_model_ids())
    embarked_ids = set(state.embarked_model_ids())
    current: dict[str, _PhysicalAuthority] = {}
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                placement = battlefield.model_placement_or_none(model.model_instance_id)
                if placement is not None:
                    presence, pose = "battlefield", placement.pose
                elif model.wounds_remaining == 0:
                    presence, pose = "destroyed", None
                elif model.model_instance_id in embarked_ids:
                    presence, pose = "embarked", None
                elif model.model_instance_id in reserve_ids:
                    presence, pose = "reserves", None
                else:
                    presence, pose = "off_battlefield", None
                current[model.model_instance_id] = _PhysicalAuthority(
                    presence=presence,
                    pose=pose,
                    wounds_remaining=model.wounds_remaining,
                )
    return current


def _starting_wounds_by_model_id(*, state: GameState) -> dict[str, int]:
    values = {
        model.model_instance_id: model.starting_wounds
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if len(values) != sum(
        len(unit.own_models) for army in state.army_definitions for unit in army.units
    ):
        raise GameLifecycleError("Primary mission physical model inventory is duplicated.")
    return values


def _model_ids_by_rules_unit_id(*, state: GameState) -> dict[str, tuple[str, ...]]:
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    values = dict(model_ids_by_unit_id)
    for record in state.starting_attached_unit_records:
        if record.attached_unit_instance_id in values:
            raise GameLifecycleError("Primary mission rules-unit model inventory is duplicated.")
        values[record.attached_unit_instance_id] = tuple(
            model_id
            for _component_id, model_ids in record.starting_model_instance_ids_by_component
            for model_id in model_ids
        )
    return values


def _primary_unit_destruction_by_id(
    *,
    state: GameState,
) -> dict[str, PrimaryUnitDestructionState]:
    values = {
        destruction.destruction_id: destruction
        for destruction in state.primary_unit_destruction_states
    }
    if len(values) != len(state.primary_unit_destruction_states):
        raise GameLifecycleError("Primary mission unit-destruction authority is duplicated.")
    return values


def _primary_battlefield_departure_by_id(
    *,
    state: GameState,
) -> dict[str, PrimaryBattlefieldDepartureState]:
    values = {
        departure.departure_id: departure
        for departure in state.primary_battlefield_departure_states
    }
    if len(values) != len(state.primary_battlefield_departure_states):
        raise GameLifecycleError("Primary mission departure authority is duplicated.")
    return values


def _no_trigger_destroyed_departure_ids(*, state: GameState) -> frozenset[str]:
    cleanup_removals_by_source_id: dict[str, list[str]] = {}
    for cleanup in state.end_turn_cleanup_states:
        for removal in cleanup.removals:
            if removal.destroyed_model_rules_triggered:
                continue
            cleanup_removals_by_source_id.setdefault(
                f"{cleanup.cleanup_id}:{removal.unit_instance_id}",
                [],
            ).append(removal.model_instance_id)
    departure_ids: set[str] = set()
    for departure in state.primary_battlefield_departure_states:
        if departure.removal_kind is not BattlefieldRemovalKind.DESTROYED:
            continue
        if departure.source_id.startswith(
            _DESPERATE_ESCAPE_DEPARTURE_SOURCE_PREFIX
        ) or departure.source_id.startswith(_EMERGENCY_DISEMBARK_DEPARTURE_SOURCE_PREFIX):
            departure_ids.add(departure.departure_id)
            continue
        expected_model_ids = cleanup_removals_by_source_id.get(departure.source_id)
        if expected_model_ids is None:
            continue
        if departure.removed_model_instance_ids != tuple(sorted(expected_model_ids)):
            raise GameLifecycleError("Primary mission no-trigger departure model drifted.")
        departure_ids.add(departure.departure_id)
    return frozenset(departure_ids)


def _initial_model_ids(*, state: GameState) -> frozenset[str]:
    attached_component_ids = {
        component_id
        for army in state.army_definitions
        for formation in army.attached_units
        for component_id in formation.component_unit_instance_ids
    }
    starting_strength_by_unit_id = {
        record.unit_instance_id: record for record in state.starting_strength_records
    }
    if len(starting_strength_by_unit_id) != len(state.starting_strength_records):
        raise GameLifecycleError("Primary mission starting-strength inventory is duplicated.")
    initial_ids: set[str] = set()
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id not in attached_component_ids:
                record = starting_strength_by_unit_id.get(unit.unit_instance_id)
                if record is None:
                    raise GameLifecycleError(
                        "Primary mission model inventory lacks starting-strength authority."
                    )
                if record.source_id != f"army-muster:{unit.unit_instance_id}":
                    continue
            initial_ids.update(model.model_instance_id for model in unit.own_models)
    return frozenset(initial_ids)


def _current_battlefield_id(*, state: GameState) -> str:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary mission physical authority requires battlefield state.")
    return battlefield.battlefield_id


def _validate_row_against_authority(
    *,
    row: PrimaryMissionBoundaryModelState,
    authority: _PhysicalAuthority,
    context: str,
) -> None:
    if authority.presence is not None and row.presence != authority.presence:
        raise GameLifecycleError(
            f"Primary mission boundary contradicts {context} physical history."
        )
    if authority.pose is not None and _checkpoint_pose(row) != authority.pose:
        raise GameLifecycleError(
            f"Primary mission boundary contradicts {context} movement history."
        )
    if authority.wounds_remaining is not None and (
        row.wounds_remaining != authority.wounds_remaining
        or row.alive is not (authority.wounds_remaining > 0)
    ):
        raise GameLifecycleError(f"Primary mission boundary contradicts {context} wound history.")


def _validate_authority_against_current(
    *,
    model_instance_id: str,
    authority: _PhysicalAuthority,
    current: _PhysicalAuthority,
) -> None:
    if (
        (authority.presence is not None and authority.presence != current.presence)
        or (authority.pose is not None and authority.pose != current.pose)
        or (
            authority.wounds_remaining is not None
            and authority.wounds_remaining != current.wounds_remaining
        )
    ):
        raise GameLifecycleError(
            f"Primary mission physical history for {model_instance_id} drifted from restored state."
        )


def _checkpoint_pose(row: PrimaryMissionBoundaryModelState) -> Pose | None:
    if row.model_placement_json is None:
        return None
    decoded: object = json.loads(row.model_placement_json)
    if not isinstance(decoded, dict):
        raise GameLifecycleError("Primary mission boundary placement payload is invalid.")
    return ModelPlacement.from_payload(cast(ModelPlacementPayload, decoded)).pose


def _presence_for_removal(removal_kind: BattlefieldRemovalKind) -> str:
    return {
        BattlefieldRemovalKind.DESTROYED: "destroyed",
        BattlefieldRemovalKind.EMBARK: "embarked",
        BattlefieldRemovalKind.INTO_RESERVES: "reserves",
        BattlefieldRemovalKind.TEMPORARILY_REMOVED: "off_battlefield",
    }[removal_kind]


def _validate_physical_transition_decision_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    for event_index, event in enumerate(event_records):
        if event.event_type not in {
            "movement_activation_completed",
            "charge_move_completed",
        }:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Physical movement event payload is invalid.")
        if event.event_type == "movement_activation_completed":
            validate_primary_mission_movement_event_decision_authority(
                event_records=event_records,
                decision_records=decision_records,
                mutation_index=event_index,
                payload=event.payload,
            )
            continue
        validate_charge_move_completed_event_authority(
            event_records=event_records,
            decision_records=decision_records,
            event_index=event_index,
            payload=event.payload,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )


__all__ = (
    "PhysicalModelAuthority",
    "physical_model_authority_before_event",
    "primary_mission_boundary_physical_event_model_ids",
    "primary_mission_model_placements_from_checkpoint",
    "validate_primary_mission_boundary_physical_authority",
)
