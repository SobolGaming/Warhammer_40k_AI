from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.command_points import (
    CommandPointGainResult,
    CommandPointGainResultPayload,
    CommandPointGainStatus,
    CommandPointSourceKind,
    CommandPointTransaction,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_command_phase_2026_08,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_core_command_point_anchor(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    anchor_index: int,
    payload: dict[str, JsonValue],
) -> None:
    if len(state.player_ids) != 2:
        raise GameLifecycleError("Core CP Command step requires exactly two players.")
    battle_round = _payload_int(payload, "battle_round")
    active_player_id = _payload_string(payload, "active_player_id")
    source_id = (
        f"{core_command_phase_2026_08.GAIN_CORE_CP_SOURCE_ID}:"
        f"round-{battle_round:02d}:active-{active_player_id}"
    )
    raw_gains = payload.get("command_point_gains")
    if (
        not isinstance(raw_gains, list)
        or len(raw_gains) != 2
        or any(not isinstance(raw_gain, dict) for raw_gain in raw_gains)
    ):
        raise GameLifecycleError("Command step anchor requires exactly two Core CP gains.")
    gains = tuple(
        CommandPointGainResult.from_payload(cast(CommandPointGainResultPayload, raw_gain))
        for raw_gain in raw_gains
        if isinstance(raw_gain, dict)
    )
    if raw_gains != [gain.to_payload() for gain in gains]:
        raise GameLifecycleError("Command step Core CP gain payload drifted.")
    transactions: list[CommandPointTransaction] = []
    for player_id, gain in zip(state.player_ids, gains, strict=True):
        transaction = gain.transaction
        if (
            gain.player_id != player_id
            or gain.battle_round != battle_round
            or gain.requested_amount != 1
            or gain.applied_amount != 1
            or gain.status is not CommandPointGainStatus.APPLIED
            or gain.source_id != source_id
            or gain.source_kind is not CommandPointSourceKind.COMMAND_PHASE_START
            or gain.capped_reason is not None
            or transaction is None
            or transaction.player_id != player_id
            or transaction.battle_round != battle_round
            or transaction.amount != 1
            or transaction.source_id != source_id
            or transaction.source_kind is not CommandPointSourceKind.COMMAND_PHASE_START
            or not transaction.cap_exempt
        ):
            raise GameLifecycleError("Command step Core CP gain authority drifted.")
        ledger = state.command_point_ledger_for_player(player_id)
        if sum(stored == transaction for stored in ledger.transactions) != 1 or (
            ledger.command_points != sum(stored.amount for stored in ledger.transactions)
        ):
            raise GameLifecycleError("Command step Core CP ledger authority drifted.")
        transactions.append(transaction)
    occurrence_transactions = tuple(
        transaction
        for ledger in state.command_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_id == source_id
        and transaction.source_kind is CommandPointSourceKind.COMMAND_PHASE_START
    )
    if set(occurrence_transactions) != set(transactions) or len(occurrence_transactions) != 2:
        raise GameLifecycleError("Command step Core CP transaction inventory drifted.")
    if anchor_index < 2:
        raise GameLifecycleError("Command step Core CP events do not precede their anchor.")
    preceding = event_records[anchor_index - 2 : anchor_index]
    if (
        tuple(event.event_type for event in preceding)
        != ("command_points_gained", "command_points_gained")
        or [event.payload for event in preceding] != raw_gains
    ):
        raise GameLifecycleError("Command step Core CP events are not the exact anchor prefix.")
    source_events = tuple(
        event
        for event in event_records
        if event.event_type == "command_points_gained"
        and isinstance(event.payload, dict)
        and event.payload.get("source_id") == source_id
        and event.payload.get("source_kind") == CommandPointSourceKind.COMMAND_PHASE_START.value
    )
    if source_events != preceding:
        raise GameLifecycleError("Command step Core CP event inventory drifted.")


def expected_core_command_occurrence_keys(state: GameState) -> tuple[tuple[int, str], ...]:
    """Derive every Command occurrence whose Core CP grant must exist from final state."""
    if state.stage is GameLifecycleStage.SETUP:
        return ()
    if state.stage is GameLifecycleStage.COMPLETE:
        return tuple(
            (battle_round, player_id)
            for battle_round in range(1, state.battle_round + 1)
            for player_id in state.turn_order
        )
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Core CP occurrence authority requires a lifecycle stage.")
    active_player_id = state.active_player_id
    current_phase = state.current_battle_phase
    if active_player_id is None or current_phase is None:
        raise GameLifecycleError("Battle Core CP occurrence authority requires turn context.")
    completed = [
        (battle_round, player_id)
        for battle_round in range(1, state.battle_round)
        for player_id in state.turn_order
    ]
    active_index = state.turn_order.index(active_player_id)
    completed.extend(
        (state.battle_round, player_id) for player_id in state.turn_order[:active_index]
    )
    try:
        command_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
        current_phase_index = state.battle_phase_sequence.index(current_phase)
    except ValueError as exc:
        raise GameLifecycleError("Core CP occurrence phase authority drifted.") from exc
    command_state = state.command_step_state
    current_granted = current_phase_index > command_phase_index or (
        current_phase is BattlePhase.COMMAND
        and command_state is not None
        and command_state.active_player_id == active_player_id
        and command_state.battle_round == state.battle_round
        and command_state.command_points_granted
    )
    if current_granted:
        completed.append((state.battle_round, active_player_id))
    return tuple(completed)


def expected_restored_core_command_occurrence_keys(
    state: GameState,
    *,
    event_records: tuple[EventRecord, ...],
) -> tuple[tuple[int, str], ...]:
    """Require complete occurrence history only after an authoritative Command route exists.

    Engine-created lifecycles retain the setup-to-battle event, while focused domain
    fixtures may intentionally construct a mid-battle state without claiming that the
    preceding phases ran.  A canonical battle origin closes the complete inventory;
    otherwise each evidenced Command occurrence is still validated exactly.
    """
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Core CP restore authority requires typed events.")
    expected_keys = expected_core_command_occurrence_keys(state)
    if _has_canonical_battle_origin(state=state, event_records=event_records):
        return expected_keys
    evidenced_keys = _command_history_evidence_keys(
        state=state,
        event_records=event_records,
        expected_keys=expected_keys,
    )
    return tuple(key for key in expected_keys if key in evidenced_keys)


def _has_canonical_battle_origin(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> bool:
    for event in event_records:
        if event.event_type != "battle_started":
            continue
        if not isinstance(event.payload, dict) or event.payload.get("game_id") != state.game_id:
            raise GameLifecycleError("Battle-start Command history authority drifted.")
        return True
    return False


def _command_history_evidence_keys(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    expected_keys: tuple[tuple[int, str], ...],
) -> frozenset[tuple[int, str]]:
    evidenced: set[tuple[int, str]] = set()
    command_state = state.command_step_state
    if command_state is not None and command_state.command_points_granted:
        evidenced.add((command_state.battle_round, command_state.active_player_id))
    for battle_round, active_player_id in expected_keys:
        source_id = (
            f"{core_command_phase_2026_08.GAIN_CORE_CP_SOURCE_ID}:"
            f"round-{battle_round:02d}:active-{active_player_id}"
        )
        if any(
            transaction.source_kind is CommandPointSourceKind.COMMAND_PHASE_START
            and transaction.source_id == source_id
            for ledger in state.command_point_ledgers
            for transaction in ledger.transactions
        ):
            evidenced.add((battle_round, active_player_id))
    relevant_event_types = {
        "command_step_started",
        "battle_shock_step_snapshot_created",
        "battle_shock_step_completed",
    }
    for event in event_records:
        key: tuple[int, str] | None = None
        if (
            event.event_type in relevant_event_types
            or event.event_type.startswith("command_phase_start_")
            or (
                event.event_type == "command_points_gained"
                and isinstance(event.payload, dict)
                and event.payload.get("source_kind")
                == CommandPointSourceKind.COMMAND_PHASE_START.value
            )
        ):
            key = _command_event_key_or_none(event)
        if key is not None:
            evidenced.add(key)
    return frozenset(evidenced.intersection(expected_keys))


def _command_event_key_or_none(event: EventRecord) -> tuple[int, str] | None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Command restore history payload is invalid.")
    battle_round = event.payload.get("battle_round")
    active_player_id = event.payload.get("active_player_id")
    if type(battle_round) is not int or type(active_player_id) is not str:
        return None
    return battle_round, active_player_id


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Command step anchor {key} must be a string.")
    return value


def _payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Command step anchor {key} must be an integer.")
    return value


__all__ = (
    "expected_core_command_occurrence_keys",
    "expected_restored_core_command_occurrence_keys",
    "validate_core_command_point_anchor",
)
