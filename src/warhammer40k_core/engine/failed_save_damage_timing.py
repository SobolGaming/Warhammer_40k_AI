"""Source-authorized incoming Damage-to-0 replacement after a failed save."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    FailedSaveDamageReplacement,
    FailedSaveDamageReplacementContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.saves import SavingThrow
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_failed_save_damage_timing_2026_09 as failed_save_damage_timing_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID = (
    failed_save_damage_timing_source.FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID
)
TIMING_POLICY = failed_save_damage_timing_source.TIMING_POLICY
FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE = "failed_save_damage_replaced"


def unused_failed_save_damage_replacement(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    runtime_modifiers: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    allocated_model_instance_id: str,
    source_phase: BattlePhase,
    saving_throw: SavingThrow,
) -> FailedSaveDamageReplacement | None:
    _assert_post_save_policy(saving_throw=saving_throw)
    if type(runtime_modifiers) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Failed-save damage replacement requires a modifier registry.")
    replacement = runtime_modifiers.failed_save_damage_replacement(
        FailedSaveDamageReplacementContext(
            state=state,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            allocated_model_instance_id=allocated_model_instance_id,
            source_phase=source_phase,
        )
    )
    if replacement is None:
        return None
    if replacement.replacement_damage != TIMING_POLICY.replacement_damage:
        raise GameLifecycleError(
            "Failed-save damage replacement must set incoming attack Damage to zero."
        )
    if _replacement_already_used(
        event_records=_typed_event_records(event_records),
        state=state,
        replacement=replacement,
    ):
        return None
    return replacement


def _assert_post_save_policy(*, saving_throw: SavingThrow) -> None:
    if (
        TIMING_POLICY.source_rule_id != FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID
        or TIMING_POLICY.applies_after_saving_throw is not True
        or TIMING_POLICY.applies_before_saving_throw is not False
        or TIMING_POLICY.replacement_damage != 0
    ):
        raise GameLifecycleError("Failed-save Damage-to-0 timing policy drifted.")
    if type(saving_throw) is not SavingThrow:
        raise GameLifecycleError("Failed-save damage replacement requires a saving throw.")
    if saving_throw.successful:
        raise GameLifecycleError("Failed-save damage replacement applies after a failed save.")


def _replacement_already_used(
    *,
    event_records: tuple[EventRecord, ...],
    state: GameState,
    replacement: FailedSaveDamageReplacement,
) -> bool:
    for event in event_records:
        if event.event_type != FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Failed-save damage replacement event must be an object.")
        if (
            payload.get("battle_round") == state.battle_round
            and payload.get("active_player_id") == state.active_player_id
            and payload.get("source_id") == replacement.source_id
            and payload.get("source_unit_instance_id") == replacement.source_unit_instance_id
        ):
            return True
    return False


def _typed_event_records(value: object) -> tuple[EventRecord, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "Failed-save damage replacement event_records must contain EventRecord values."
        )
    items = cast(tuple[object, ...], value)
    if any(type(item) is not EventRecord for item in items):
        raise GameLifecycleError(
            "Failed-save damage replacement event_records must contain EventRecord values."
        )
    return cast(tuple[EventRecord, ...], items)


__all__ = (
    "FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE",
    "FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID",
    "TIMING_POLICY",
    "unused_failed_save_damage_replacement",
)
