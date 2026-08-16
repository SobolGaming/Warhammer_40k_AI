from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.actions import MissionActionState
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState


def validate_primary_battlefield_departure_states(
    values: object,
) -> tuple[PrimaryBattlefieldDepartureState, ...]:
    """Canonicalize the complete battlefield-departure history frozen for scoring."""
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence battlefield departures must be a tuple."
        )
    raw_values = cast(tuple[object, ...], values)
    departures: list[PrimaryBattlefieldDepartureState] = []
    seen_ids: set[str] = set()
    for value in raw_values:
        if type(value) is not PrimaryBattlefieldDepartureState:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence departures must contain typed states."
            )
        if value.departure_id in seen_ids:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence departure identities must be unique."
            )
        seen_ids.add(value.departure_id)
        departures.append(value)
    expected = tuple(sorted(departures, key=lambda departure: departure.departure_id))
    if raw_values != expected:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence battlefield departures must be sorted."
        )
    return expected


def validate_primary_mission_action_states(values: object) -> tuple[MissionActionState, ...]:
    """Canonicalize the assigned Primary Action history frozen for scoring."""
    from warhammer40k_core.engine.actions import MissionActionState

    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence mission Action states must be a tuple."
        )
    raw_values = cast(tuple[object, ...], values)
    actions: list[MissionActionState] = []
    seen_ids: set[str] = set()
    for value in raw_values:
        if type(value) is not MissionActionState:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence mission Action history must contain typed states."
            )
        if value.action_id in seen_ids:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence mission Action identities must be unique."
            )
        seen_ids.add(value.action_id)
        actions.append(value)
    expected = tuple(sorted(actions, key=lambda action: action.action_id))
    if raw_values != expected:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence mission Action history must be sorted."
        )
    return expected


def validate_primary_unit_destruction_state_ids(values: object) -> tuple[str, ...]:
    """Validate the content-addressed destruction-history membership of one boundary."""
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence destruction state IDs must be a tuple."
        )
    raw_values = cast(tuple[object, ...], values)
    identifiers = tuple(
        _validate_identifier("Primary scoring destruction state ID", value) for value in raw_values
    )
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence destruction state IDs must be unique."
        )
    expected = tuple(sorted(identifiers))
    if identifiers != expected:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence destruction state IDs must be sorted."
        )
    return expected


def primary_unit_destruction_state_ids_for_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> tuple[str, ...]:
    """Freeze destruction rows that can authoritatively precede one scoring boundary."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring destruction history requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring destruction history requires an ObjectiveControlRecord."
        )
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary scoring destruction end_of_battle must be a bool.")
    phase_sequence = tuple(phase.value for phase in state.battle_phase_sequence)
    record_key = _history_context_key(
        label="Primary scoring ObjectiveControlRecord",
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        turn_order=state.turn_order,
        battle_phase_sequence=phase_sequence,
    )
    included: list[str] = []
    for destruction in state.primary_unit_destruction_states:
        if type(destruction) is not PrimaryUnitDestructionState:
            raise GameLifecycleError(
                "Primary scoring destruction history must contain typed states."
            )
        row_key = _destruction_context_key(
            destruction=destruction,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        if row_key > record_key:
            continue
        if (
            row_key == record_key
            and not end_of_battle
            and destruction.unattributed_cause
            is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
        ):
            # The reserve deadline is resolved after ordinary turn-end Primary scoring.
            continue
        included.append(destruction.destruction_id)
    return validate_primary_unit_destruction_state_ids(tuple(sorted(included)))


def primary_unit_destruction_states_for_evidence(
    *,
    state: GameState,
    destruction_state_ids: tuple[str, ...],
) -> tuple[PrimaryUnitDestructionState, ...]:
    """Resolve only the destruction rows frozen into content-addressed evidence."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring destruction resolution requires GameState.")
    requested_ids = validate_primary_unit_destruction_state_ids(destruction_state_ids)
    authoritative_by_id: dict[str, PrimaryUnitDestructionState] = {}
    for destruction in state.primary_unit_destruction_states:
        if type(destruction) is not PrimaryUnitDestructionState:
            raise GameLifecycleError(
                "Primary scoring destruction authority must contain typed states."
            )
        if destruction.destruction_id in authoritative_by_id:
            raise GameLifecycleError(
                "Primary scoring destruction authority contains duplicate identities."
            )
        authoritative_by_id[destruction.destruction_id] = destruction
    missing = tuple(
        destruction_id
        for destruction_id in requested_ids
        if destruction_id not in authoritative_by_id
    )
    if missing:
        raise GameLifecycleError(
            "Primary scoring destruction evidence references a non-authoritative state."
        )
    return tuple(authoritative_by_id[destruction_id] for destruction_id in requested_ids)


def validate_primary_scoring_destruction_history_authority(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    destruction_state_ids: tuple[str, ...],
    end_of_battle: bool,
) -> None:
    """Bind frozen membership to complete earlier history and valid same-context rows."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring destruction authority requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring destruction authority requires an ObjectiveControlRecord."
        )
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary scoring destruction end_of_battle must be a bool.")
    requested_ids = validate_primary_unit_destruction_state_ids(destruction_state_ids)
    resolved = primary_unit_destruction_states_for_evidence(
        state=state,
        destruction_state_ids=requested_ids,
    )
    resolved_ids = {destruction.destruction_id for destruction in resolved}
    phase_sequence = tuple(phase.value for phase in state.battle_phase_sequence)
    record_key = _history_context_key(
        label="Primary scoring ObjectiveControlRecord",
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        turn_order=state.turn_order,
        battle_phase_sequence=phase_sequence,
    )
    required_ids: set[str] = set()
    for destruction in state.primary_unit_destruction_states:
        row_key = _destruction_context_key(
            destruction=destruction,
            turn_order=state.turn_order,
            battle_phase_sequence=phase_sequence,
        )
        if row_key < record_key or (
            row_key == record_key
            and (
                end_of_battle
                or destruction.unattributed_cause
                is not PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
            )
        ):
            required_ids.add(destruction.destruction_id)
        if row_key > record_key and destruction.destruction_id in resolved_ids:
            raise GameLifecycleError(
                "Primary scoring destruction evidence cannot reference future history."
            )
        if (
            row_key == record_key
            and not end_of_battle
            and destruction.unattributed_cause
            is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
            and destruction.destruction_id in resolved_ids
        ):
            raise GameLifecycleError(
                "Ordinary Primary scoring cannot reference a post-boundary reserve destruction."
            )
    if not required_ids <= resolved_ids:
        raise GameLifecycleError(
            "Primary scoring destruction history is incomplete for authoritative GameState."
        )


def _destruction_context_key(
    *,
    destruction: PrimaryUnitDestructionState,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int]:
    from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

    if type(destruction) is not PrimaryUnitDestructionState:
        raise GameLifecycleError("Primary scoring destruction history requires typed states.")
    return _history_context_key(
        label="Primary scoring destruction state",
        battle_round=destruction.battle_round,
        active_player_id=destruction.active_player_id,
        phase=destruction.phase,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )


def _history_context_key(
    *,
    label: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int]:
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError(f"{label} battle_round must be a positive integer.")
    if active_player_id not in turn_order:
        raise GameLifecycleError(f"{label} references an unknown active player.")
    if phase not in battle_phase_sequence:
        raise GameLifecycleError(f"{label} references an unknown battle phase.")
    return (
        battle_round,
        turn_order.index(active_player_id),
        battle_phase_sequence.index(phase),
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "primary_unit_destruction_state_ids_for_boundary",
    "primary_unit_destruction_states_for_evidence",
    "validate_primary_battlefield_departure_states",
    "validate_primary_mission_action_states",
    "validate_primary_scoring_destruction_history_authority",
    "validate_primary_unit_destruction_state_ids",
)
