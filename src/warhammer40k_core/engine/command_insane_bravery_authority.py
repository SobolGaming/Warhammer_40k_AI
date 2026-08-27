from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import BattleShockResult
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    PersistingEffectPayload,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagem_use_history_authority import (
    StratagemUseHistoryAuthority,
    validate_parameterized_stratagem_use_history,
)
from warhammer40k_core.engine.stratagems_model import (
    CORE_INSANE_BRAVERY_HANDLER_ID,
    INSANE_BRAVERY_TARGET_POLICY_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemTargetKind,
    StratagemUseRecord,
    StratagemUseRecordPayload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState

_INSANE_BRAVERY_STRATAGEM_ID = "insane-bravery"
_REGISTRATION_KEYS = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "stratagem_use",
        "persisting_effect",
    }
)
_AUTO_PASS_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "unit_instance_id",
        "persisting_effect",
    }
)


def validate_command_auto_pass_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    segment_start_index: int,
    resolved_index: int,
    result: BattleShockResult,
    auto_passed: bool,
    battle_round: int,
    active_player_id: str,
) -> None:
    auto_pass_rows = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if segment_start_index <= index < resolved_index
        and event.event_type == "battle_shock_test_auto_passed"
    )
    if not auto_passed:
        if auto_pass_rows:
            raise GameLifecycleError("Command Battle-shock auto-pass history drift.")
        return
    if len(auto_pass_rows) != 1 or not result.passed:
        raise GameLifecycleError("Command Battle-shock auto-pass history drift.")
    auto_pass_index, auto_pass_event = auto_pass_rows[0]
    payload = _object(auto_pass_event.payload, context="auto-pass event")
    raw_effect = _object(payload.get("persisting_effect"), context="auto-pass effect")
    effect = _persisting_effect(raw_effect)
    if frozenset(payload) != _AUTO_PASS_KEYS or payload != validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "unit_instance_id": result.request.unit_instance_id,
            "persisting_effect": effect.to_payload(),
        }
    ):
        raise GameLifecycleError("Command Battle-shock auto-pass context drift.")
    registration_rows = tuple(
        (index, event)
        for index, event in enumerate(event_records[:auto_pass_index])
        if event.event_type == "insane_bravery_auto_pass_registered"
        and isinstance(event.payload, dict)
        and event.payload.get("persisting_effect") == raw_effect
    )
    if len(registration_rows) != 1:
        raise GameLifecycleError("Command Battle-shock auto-pass provenance drift.")
    registration_index, registration = registration_rows[0]
    registered_effect, _authority = _validate_registration(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        registration_index=registration_index,
        registration=registration,
        expected_target_unit_instance_id=result.request.unit_instance_id,
        expected_battle_round=battle_round,
        expected_player_id=active_player_id,
    )
    if registered_effect != effect:
        raise GameLifecycleError("Command Battle-shock auto-pass effect authority drifted.")


def validate_loaded_command_auto_pass_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    registrations = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "insane_bravery_auto_pass_registered"
    )
    for registration_index, registration in registrations:
        _validate_registration(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            registration_index=registration_index,
            registration=registration,
            expected_target_unit_instance_id=None,
            expected_battle_round=None,
            expected_player_id=None,
        )


def _validate_registration(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    registration_index: int,
    registration: EventRecord,
    expected_target_unit_instance_id: str | None,
    expected_battle_round: int | None,
    expected_player_id: str | None,
) -> tuple[PersistingEffect, StratagemUseHistoryAuthority]:
    payload = _object(registration.payload, context="registration event")
    raw_use = _object(payload.get("stratagem_use"), context="registration use")
    raw_effect = _object(payload.get("persisting_effect"), context="registration effect")
    use = _stratagem_use(raw_use)
    effect = _persisting_effect(raw_effect)
    authority = validate_parameterized_stratagem_use_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        use_record=use,
        mutation_index=registration_index,
    )
    target_id = use.target_binding.target_unit_instance_id
    expected_record = _insane_bravery_catalog_record()
    expected_effect = PersistingEffect(
        effect_id=f"{use.use_id}:insane-bravery-auto-pass",
        source_rule_id=use.source_id,
        owner_player_id=use.player_id,
        target_unit_instance_ids=(cast(str, target_id),),
        started_battle_round=use.battle_round,
        started_phase=use.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use.battle_round,
            phase=use.phase,
            player_id=use.player_id,
        ),
        effect_payload={
            "effect_kind": "battle_shock_auto_pass",
            "stratagem_use_id": use.use_id,
        },
    )
    if (
        frozenset(payload) != _REGISTRATION_KEYS
        or authority.catalog_record != expected_record
        or use.stratagem_id != _INSANE_BRAVERY_STRATAGEM_ID
        or use.source_id != expected_record.definition.source_id
        or use.handler_id != CORE_INSANE_BRAVERY_HANDLER_ID
        or use.command_point_cost != 1
        or use.command_point_modifier_ids
        or use.command_point_modifier_source_ids
        or use.effect_selection is not None
        or use.effect_payload is not None
        or use.phase is not BattlePhase.COMMAND
        or use.active_player_id != use.player_id
        or (expected_battle_round is not None and use.battle_round != expected_battle_round)
        or (expected_player_id is not None and use.player_id != expected_player_id)
        or use.timing_window_id
        != f"insane-bravery-battle-shock-round-{use.battle_round}-player-{use.player_id}"
        or authority.proposal_request.context.trigger_kind is not TimingTriggerKind.START_PHASE
        or authority.proposal_request.context.trigger_payload is not None
        or authority.catalog_record.availability_kind is not StratagemAvailabilityKind.CORE
        or authority.catalog_record.definition.target_spec.target_kind
        is not StratagemTargetKind.FRIENDLY_UNIT
        or authority.catalog_record.definition.target_spec.target_policy_id
        != INSANE_BRAVERY_TARGET_POLICY_ID
        or use.target_binding.target_kind is not StratagemTargetKind.FRIENDLY_UNIT
        or use.target_binding.target_player_id != use.player_id
        or target_id is None
        or use.targeted_unit_instance_ids != (target_id,)
        or use.affected_unit_instance_ids != (target_id,)
        or (
            expected_target_unit_instance_id is not None
            and target_id != expected_target_unit_instance_id
        )
        or effect != expected_effect
        or payload
        != validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": use.player_id,
                "battle_round": use.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "stratagem_use": use.to_payload(),
                "persisting_effect": effect.to_payload(),
            }
        )
    ):
        raise GameLifecycleError("Insane Bravery registration authority drifted.")
    return effect, authority


def _insane_bravery_catalog_record() -> StratagemCatalogRecord:
    matches = tuple(
        record
        for record in eleventh_edition_core_stratagem_catalog_records()
        if record.definition.stratagem_id == _INSANE_BRAVERY_STRATAGEM_ID
    )
    if len(matches) != 1 or matches[0].disabled:
        raise GameLifecycleError("Insane Bravery source catalog authority is unavailable.")
    return matches[0]


def _stratagem_use(payload: dict[str, JsonValue]) -> StratagemUseRecord:
    try:
        use = StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, payload))
    except KeyError as exc:
        raise GameLifecycleError("Insane Bravery use payload is incomplete.") from exc
    if payload != validate_json_value(use.to_payload()):
        raise GameLifecycleError("Insane Bravery use payload shape drifted.")
    return use


def _persisting_effect(payload: dict[str, JsonValue]) -> PersistingEffect:
    try:
        effect = PersistingEffect.from_payload(cast(PersistingEffectPayload, payload))
    except KeyError as exc:
        raise GameLifecycleError("Insane Bravery effect payload is incomplete.") from exc
    if payload != validate_json_value(effect.to_payload()):
        raise GameLifecycleError("Insane Bravery effect payload shape drifted.")
    return effect


def _object(value: JsonValue, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Insane Bravery {context} must be an object.")
    return value


__all__ = (
    "validate_command_auto_pass_history",
    "validate_loaded_command_auto_pass_authority",
)
