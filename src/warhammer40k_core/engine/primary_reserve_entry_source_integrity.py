from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY,
    reserve_entry_evidence_payload,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
    primary_reserve_entry_requirements_from_evidence,
    validate_primary_reserve_entry_source_terminal_identity,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_primary_reserve_entry_source_terminal_semantics(
    *,
    state: GameState,
    provider: PrimaryReserveEntryProvider,
    decision: DecisionRecord,
    reserve_entry: dict[str, JsonValue],
    source_terminal: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    """Bind a provider terminal to authoritative decision, timing, and source context."""
    from warhammer40k_core.engine.game_state import GameState

    if (
        type(state) is not GameState
        or type(provider) is not PrimaryReserveEntryProvider
        or type(decision) is not DecisionRecord
        or type(source_terminal) is not EventRecord
    ):
        raise GameLifecycleError("Reserve-entry source semantics require typed authority.")
    payload = _json_object(
        source_terminal.payload,
        field_name="Reserve-entry source terminal payload",
    )
    entry_round = _required_positive_int(
        reserve_entry.get("entered_reserves_battle_round"),
        field_name="Reserve-entry battle round",
    )
    entry_phase = _required_identifier(
        reserve_entry.get("entered_reserves_phase"),
        field_name="Reserve-entry phase",
    )
    if provider.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        request_payload = _json_object(
            decision.request.payload,
            field_name="Ability reserve request",
        )
        expected_active_player_id = _required_identifier(
            request_payload.get("active_player_id"),
            field_name="Ability reserve active player",
        )
        request_player_id = request_payload.get("player_id")
        if (
            decision.request.actor_id != provider.player_id
            or request_payload.get("game_id") != state.game_id
            or request_payload.get("battle_round") != entry_round
            or request_payload.get("phase") != entry_phase
            or (request_player_id is not None and request_player_id != provider.player_id)
        ):
            raise GameLifecycleError("Ability reserve request timing or owner drift.")
    else:
        if provider.stratagem_use_id is None:
            raise GameLifecycleError("Stratagem reserve source terminal use identity is missing.")
        uses = tuple(
            use for use in state.stratagem_use_records if use.use_id == provider.stratagem_use_id
        )
        if len(uses) != 1:
            raise GameLifecycleError("Stratagem reserve source terminal use identity is missing.")
        use = uses[0]
        expected_active_player_id = _required_identifier(
            use.active_player_id,
            field_name="Stratagem reserve active player",
        )
        if (
            payload.get("stratagem_use") != use.to_payload()
            or payload.get("stratagem_effect_payload") != use.effect_payload
        ):
            raise GameLifecycleError("Stratagem reserve source terminal use context drift.")
        executed_events = tuple(
            event
            for event in event_records
            if event.event_type == "rule_execution_effect_applied"
            and event.payload == payload.get("generic_rule_effect")
        )
        if len(executed_events) != 1:
            raise GameLifecycleError("Stratagem reserve source terminal execution evidence drift.")
    if (
        expected_active_player_id not in state.player_ids
        or provider.player_id not in state.player_ids
    ):
        raise GameLifecycleError("Reserve-entry source terminal player identity drift.")
    if (
        payload.get("game_id") != state.game_id
        or payload.get("battle_round") != entry_round
        or payload.get("active_player_id") != expected_active_player_id
        or payload.get("phase") != entry_phase
        or payload.get("player_id") != provider.player_id
    ):
        raise GameLifecycleError("Reserve-entry source terminal timing drift.")
    _validate_source_terminal_reserve_state(
        payload=payload,
        reserve_entry=reserve_entry,
    )
    if provider.provider_kind is not PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        return
    expected_binding: JsonValue = {
        "occurrence_id": provider.occurrence_id,
        "provider": provider.to_payload(),
        "reserve_entry_state": reserve_entry,
    }
    if payload.get(PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY) != [expected_binding]:
        raise GameLifecycleError("Ability reserve source terminal binding cardinality drift.")
    selected_target_id = _ability_target_id(payload)
    from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage

    if (
        payload.get("source_rule_id") != provider.source_rule_id
        or payload.get("hook_id") != provider.provider_id
        or payload.get("request_id") != provider.decision_request_id
        or payload.get("result_id") != provider.decision_result_id
        or payload.get("selected_option_id") != decision.result.selected_option_id
        or payload.get("use_ability") is not True
        or not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=selected_target_id,
            second_unit_instance_id=provider.target_rules_unit_instance_id,
        )
    ):
        raise GameLifecycleError("Ability reserve source terminal context drift.")
    validate_primary_reserve_entry_source_terminal_identity(
        state=state,
        provider=provider,
        decision=decision,
        terminal_payload=payload,
        reserve_entry=reserve_entry,
    )


def validate_primary_reserve_entry_source_requirements(
    *,
    state: GameState,
    provider: PrimaryReserveEntryProvider,
    reserve_entry: dict[str, JsonValue],
    source_terminal: EventRecord,
) -> None:
    """Recompute entry-time arrival requirements and destruction policy from source authority."""
    from warhammer40k_core.engine import reserve_arrival_requirements as arrival_requirements
    from warhammer40k_core.engine.game_state import GameState

    if (
        type(state) is not GameState
        or type(provider) is not PrimaryReserveEntryProvider
        or type(source_terminal) is not EventRecord
    ):
        raise GameLifecycleError("Reserve-entry source requirements require typed authority.")
    source_payload = _json_object(
        source_terminal.payload,
        field_name="Reserve-entry source terminal payload",
    )
    executed_effect: JsonValue = None
    if provider.provider_kind is PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM:
        executed_effect = source_payload.get("generic_rule_effect")
    expected = primary_reserve_entry_requirements_from_evidence(
        state=state,
        provider=provider,
        executed_effect_payload=executed_effect,
        entry_battle_round=_required_positive_int(
            reserve_entry.get("entered_reserves_battle_round"),
            field_name="Reserve-entry battle round",
        ),
        entry_active_player_id=_required_identifier(
            source_payload.get("active_player_id"),
            field_name="Reserve-entry active player",
        ),
    )
    expected_policy = arrival_requirements.reposition_destruction_policy(
        mission_setup=state.mission_setup,
        destruction_deadline_policy=None,
    )
    if (
        reserve_entry.get("required_arrival_battle_round") != expected.required_arrival_battle_round
        or reserve_entry.get("required_arrival_phase") != expected.required_arrival_phase
        or reserve_entry.get("required_arrival_source_rule_id")
        != expected.required_arrival_source_rule_id
        or reserve_entry.get("required_arrival_placement_kind")
        != expected.required_arrival_placement_kind
        or reserve_entry.get("destruction_deadline_policy") != expected_policy.to_payload()
    ):
        raise GameLifecycleError("Reserve-entry source requirements drift.")


def _ability_target_id(payload: dict[str, JsonValue]) -> str:
    targets = tuple(
        value
        for key in ("target_unit_instance_id", "target_rules_unit_instance_id")
        if type(value := payload.get(key)) is str
    )
    if len(targets) != 1:
        raise GameLifecycleError("Ability reserve target identity is ambiguous.")
    return targets[0]


def _validate_source_terminal_reserve_state(
    *,
    payload: dict[str, JsonValue],
    reserve_entry: dict[str, JsonValue],
) -> None:
    from warhammer40k_core.engine.reserves import (
        ReserveState,
        ReserveStatePayload,
        ReserveStatus,
    )

    raw_single = payload.get("reserve_state")
    raw_multiple = payload.get("reserve_states")
    if (raw_single is None) == (raw_multiple is None):
        raise GameLifecycleError("Reserve-entry source terminal reserve-state shape drift.")
    raw_states: list[JsonValue]
    if raw_single is not None:
        raw_states = [raw_single]
    elif isinstance(raw_multiple, list) and raw_multiple:
        raw_states = raw_multiple
    else:
        raise GameLifecycleError("Reserve-entry source terminal reserve states are malformed.")
    matching = 0
    for raw_state in raw_states:
        if not isinstance(raw_state, dict):
            raise GameLifecycleError("Reserve-entry source terminal ReserveState is malformed.")
        try:
            reserve_state = ReserveState.from_payload(cast(ReserveStatePayload, raw_state))
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError(
                "Reserve-entry source terminal ReserveState is invalid."
            ) from exc
        if (
            reserve_state.status is not ReserveStatus.IN_RESERVES
            or reserve_state.arrived_battle_round is not None
            or reserve_state.arrived_phase is not None
            or reserve_state.destroyed_battle_round is not None
            or reserve_state.post_arrival_restrictions
            or reserve_state.restriction_battle_round is not None
            or reserve_state.large_model_exception_used
        ):
            raise GameLifecycleError(
                "Reserve-entry source terminal must preserve its entry-time ReserveState."
            )
        if reserve_entry_evidence_payload(reserve_state) == reserve_entry:
            matching += 1
    if matching != 1:
        raise GameLifecycleError("Reserve-entry source terminal ReserveState identity drift.")


def _json_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _required_identifier(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


def _required_positive_int(value: object, *, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


__all__ = (
    "validate_primary_reserve_entry_source_requirements",
    "validate_primary_reserve_entry_source_terminal_semantics",
)
