from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from warhammer40k_core.engine.abilities import (
    CORE_DEADLY_DEMISE_HANDLER_ID,
    CORE_DEEP_STRIKE_HANDLER_ID,
    CORE_FEEL_NO_PAIN_HANDLER_ID,
    CORE_FIGHTS_FIRST_HANDLER_ID,
    CORE_INFILTRATORS_HANDLER_ID,
    CORE_LEADER_HANDLER_ID,
    CORE_LONE_OPERATIVE_HANDLER_ID,
    CORE_SCOUTS_HANDLER_ID,
)
from warhammer40k_core.engine.ability_coverage import (
    DEADLY_DEMISE_DESCRIPTOR_RUNTIME_CONSUMER_IDS,
    DEEP_STRIKE_DESCRIPTOR_RUNTIME_CONSUMER_IDS,
    FEEL_NO_PAIN_DESCRIPTOR_RUNTIME_CONSUMER_IDS,
    SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,
    WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,
)
from warhammer40k_core.engine.army_mustering import (
    ATTACHMENT_DECLARATION_MUSTERING_CONSUMER_ID,
    DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_MUSTERING_CONSUMER_ID,
    SPACE_MARINE_CHAPTERS_SOURCE_ID,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    catalog_descriptor_registered_runtime_consumer_ids,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    catalog_rule_ir_registered_hook_ids,
)
from warhammer40k_core.engine.core_descriptor_consumption import (
    CORE_FIGHTS_FIRST_CONSUMER_ID,
    CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID,
    CORE_LEADER_ATTACHMENT_CONSUMER_ID,
    CORE_LONE_OPERATIVE_SHOOTING_TARGET_CONSUMER_ID,
    CORE_SCOUTS_PREBATTLE_CONSUMER_ID,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.catalog_runtime_hooks import (
    CATALOG_IR_SHOOTING_PHASE_START_HOOK_ID,
)
from warhammer40k_core.engine.generic_target_restriction_effects import (
    GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
)
from warhammer40k_core.engine.phase import GameLifecycleError

_RUNTIME_EVIDENCE_SUMMARY_FIELDS: Final = (
    "ability_handler_ids",
    "stratagem_handler_ids",
    "rule_runtime_binding_ids",
    "battle_formation_hook_ids",
    "start_battle_hook_ids",
    "battle_round_start_hook_ids",
    "turn_end_hook_ids",
    "command_phase_start_hook_ids",
    "fight_phase_start_hook_ids",
    "fight_phase_end_hook_ids",
    "shooting_phase_start_hook_ids",
    "unit_destroyed_hook_ids",
    "battle_shock_hook_ids",
    "advance_eligibility_hook_ids",
    "advance_move_hook_ids",
    "fall_back_hook_ids",
    "movement_end_surge_hook_ids",
    "reserve_arrival_distance_hook_ids",
    "reserve_arrival_restriction_hook_ids",
    "unit_move_completed_mortal_wound_hook_ids",
    "unit_move_completed_battle_shock_hook_ids",
    "mortal_wound_feel_no_pain_hook_ids",
    "charge_declaration_hook_ids",
    "shooting_target_restriction_hook_ids",
    "charge_target_restriction_hook_ids",
    "shooting_unit_selected_hook_ids",
    "shooting_unit_selected_grant_hook_ids",
    "attack_sequence_completed_hook_ids",
    "shooting_end_surge_hook_ids",
    "enhancement_effect_binding_ids",
    "fight_activation_ability_hook_ids",
    "fight_unit_selected_hook_ids",
    "fight_unit_selected_grant_hook_ids",
    "phase_end_objective_control_hook_ids",
    "stratagem_cost_choice_hook_ids",
    "stratagem_cost_modifier_ids",
    "unit_characteristic_modifier_ids",
    "hit_roll_modifier_ids",
    "wound_roll_modifier_ids",
    "damage_roll_modifier_ids",
    "allocated_attack_damage_modifier_ids",
    "save_option_modifier_ids",
    "movement_budget_modifier_ids",
    "objective_control_modifier_ids",
    "advance_roll_modifier_ids",
    "charge_roll_modifier_ids",
    "weapon_profile_modifier_ids",
    "attack_reroll_permission_modifier_ids",
    "post_roll_weapon_profile_modifier_ids",
    "failed_save_damage_replacement_modifier_ids",
)
_EXPLICIT_EVIDENCE_ALIASES: Final = {
    **dict.fromkeys(DEEP_STRIKE_DESCRIPTOR_RUNTIME_CONSUMER_IDS, CORE_DEEP_STRIKE_HANDLER_ID),
    **dict.fromkeys(DEADLY_DEMISE_DESCRIPTOR_RUNTIME_CONSUMER_IDS, CORE_DEADLY_DEMISE_HANDLER_ID),
    **dict.fromkeys(FEEL_NO_PAIN_DESCRIPTOR_RUNTIME_CONSUMER_IDS, CORE_FEEL_NO_PAIN_HANDLER_ID),
    CORE_FIGHTS_FIRST_CONSUMER_ID: CORE_FIGHTS_FIRST_HANDLER_ID,
    CORE_LEADER_ATTACHMENT_CONSUMER_ID: CORE_LEADER_HANDLER_ID,
    CORE_LONE_OPERATIVE_SHOOTING_TARGET_CONSUMER_ID: CORE_LONE_OPERATIVE_HANDLER_ID,
    CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID: CORE_INFILTRATORS_HANDLER_ID,
    CORE_SCOUTS_PREBATTLE_CONSUMER_ID: CORE_SCOUTS_HANDLER_ID,
    CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID: (CATALOG_IR_SHOOTING_PHASE_START_HOOK_ID),
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID: (
        GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID
    ),
}
_ENGINE_GLOBAL_RUNTIME_CONSUMER_IDS: Final = frozenset(
    {
        ATTACHMENT_DECLARATION_MUSTERING_CONSUMER_ID,
        CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID,
        DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_MUSTERING_CONSUMER_ID,
        SPACE_MARINE_CHAPTERS_SOURCE_ID,
        SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,
        WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,
    }
)


def active_runtime_evidence_ids(bundle: RuntimeContentBundle) -> frozenset[str]:
    if type(bundle) is not RuntimeContentBundle:
        raise GameLifecycleError("Runtime evidence requires a RuntimeContentBundle.")
    payload = cast(Mapping[str, JsonValue], bundle.to_summary_payload())
    evidence_ids: set[str] = set()
    active_handler_ids: set[str] = set()
    for field_name in _RUNTIME_EVIDENCE_SUMMARY_FIELDS:
        values = payload[field_name]
        if not isinstance(values, list) or any(type(value) is not str for value in values):
            raise GameLifecycleError("Runtime bundle evidence summary shape drifted.")
        typed_values = cast(list[str], values)
        evidence_ids.update(typed_values)
        active_handler_ids.update(typed_values)
    event_subscriptions = payload["event_subscriptions"]
    if not isinstance(event_subscriptions, list):
        raise GameLifecycleError("Runtime bundle event evidence summary shape drifted.")
    for subscription in event_subscriptions:
        if not isinstance(subscription, dict):
            raise GameLifecycleError("Runtime bundle event evidence summary shape drifted.")
        for field_name in ("subscription_id", "source_rule_id", "handler_id"):
            value = subscription.get(field_name)
            if type(value) is not str or not value.strip():
                raise GameLifecycleError("Runtime bundle event evidence summary shape drifted.")
            evidence_ids.add(value)
            if field_name == "handler_id":
                active_handler_ids.add(value)
    evidence_ids.update(
        bundle.faction_rule_execution_registry.active_execution_record_ids(
            active_handler_ids=frozenset(active_handler_ids)
        )
    )
    return frozenset(evidence_ids)


def validate_active_runtime_consumer_ids(
    *,
    runtime_consumer_ids: tuple[str, ...],
    expected_active_evidence_ids: frozenset[str],
    active_evidence_ids: frozenset[str],
    context: str,
) -> None:
    if type(runtime_consumer_ids) is not tuple or any(
        type(consumer_id) is not str or not consumer_id.strip()
        for consumer_id in runtime_consumer_ids
    ):
        raise GameLifecycleError("Runtime consumer evidence IDs must be a tuple of strings.")
    if type(context) is not str or not context.strip():
        raise GameLifecycleError("Runtime consumer evidence context must be a string.")
    _validate_active_evidence_ids(
        expected_active_evidence_ids,
        field_name="Expected active runtime evidence IDs",
    )
    _validate_active_evidence_ids(
        active_evidence_ids,
        field_name="Active runtime evidence IDs",
    )
    registered_catalog_ids = frozenset(catalog_rule_ir_registered_hook_ids())
    registered_descriptor_ids = frozenset(catalog_descriptor_registered_runtime_consumer_ids())
    missing_ids: list[str] = []
    unregistered_ids: list[str] = []
    outside_activation_ids: list[str] = []
    for consumer_id in runtime_consumer_ids:
        required_evidence_id = _required_bundle_evidence_id(
            consumer_id=consumer_id,
            expected_active_evidence_ids=expected_active_evidence_ids,
            registered_catalog_ids=registered_catalog_ids,
            registered_descriptor_ids=registered_descriptor_ids,
        )
        if required_evidence_id is None:
            continue
        if required_evidence_id == "":
            unregistered_ids.append(consumer_id)
            continue
        if required_evidence_id not in expected_active_evidence_ids:
            outside_activation_ids.append(consumer_id)
            continue
        if required_evidence_id not in active_evidence_ids:
            missing_ids.append(
                consumer_id
                if required_evidence_id == consumer_id
                else f"{consumer_id} -> {required_evidence_id}"
            )
    if unregistered_ids:
        raise GameLifecycleError(
            f"{context} references unregistered runtime consumer evidence: "
            + ", ".join(sorted(unregistered_ids))
            + "."
        )
    if outside_activation_ids:
        raise GameLifecycleError(
            f"{context} references runtime consumer evidence outside canonical activation: "
            + ", ".join(sorted(outside_activation_ids))
            + "."
        )
    if missing_ids:
        raise GameLifecycleError(
            f"{context} references inactive runtime consumer evidence: "
            + ", ".join(sorted(missing_ids))
            + "."
        )


def _required_bundle_evidence_id(
    *,
    consumer_id: str,
    expected_active_evidence_ids: frozenset[str],
    registered_catalog_ids: frozenset[str],
    registered_descriptor_ids: frozenset[str],
) -> str | None:
    if consumer_id in expected_active_evidence_ids:
        return consumer_id
    alias_id = _EXPLICIT_EVIDENCE_ALIASES.get(consumer_id)
    if alias_id is not None:
        return alias_id
    if consumer_id.startswith(f"{CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID}:"):
        if consumer_id not in registered_catalog_ids:
            return ""
        return CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID
    if consumer_id in _ENGINE_GLOBAL_RUNTIME_CONSUMER_IDS:
        return None
    if consumer_id in registered_catalog_ids:
        # These consumers are invoked by engine-owned query/services rather than
        # installed into a per-selection runtime bundle.
        return None
    if consumer_id in registered_descriptor_ids:
        # Faction descriptor consumers are contribution-backed and must be in the
        # canonical activation. Core descriptor aliases were resolved above.
        return consumer_id
    return ""


def _validate_active_evidence_ids(
    evidence_ids: frozenset[str],
    *,
    field_name: str,
) -> None:
    if type(evidence_ids) is not frozenset or any(
        type(evidence_id) is not str or not evidence_id.strip() for evidence_id in evidence_ids
    ):
        raise GameLifecycleError(f"{field_name} must be a frozenset of strings.")


__all__ = ("active_runtime_evidence_ids", "validate_active_runtime_consumer_ids")
