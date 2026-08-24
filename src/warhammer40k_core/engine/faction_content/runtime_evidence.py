from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Self, cast

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
from warhammer40k_core.engine.faction_content.datasheet_faction_access import (
    default_datasheet_faction_access_registry,
)
from warhammer40k_core.engine.generic_target_restriction_effects import (
    GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
)
from warhammer40k_core.engine.phase import GameLifecycleError


class RuntimeEvidenceProvider(StrEnum):
    ABILITY_HANDLER = "ability_handler_ids"
    STRATAGEM_HANDLER = "stratagem_handler_ids"
    RULE_RUNTIME_BINDING = "rule_runtime_binding_ids"
    BATTLE_FORMATION_HOOK = "battle_formation_hook_ids"
    START_BATTLE_HOOK = "start_battle_hook_ids"
    BATTLE_ROUND_START_HOOK = "battle_round_start_hook_ids"
    TURN_END_HOOK = "turn_end_hook_ids"
    COMMAND_PHASE_START_HOOK = "command_phase_start_hook_ids"
    FIGHT_PHASE_START_HOOK = "fight_phase_start_hook_ids"
    FIGHT_PHASE_END_HOOK = "fight_phase_end_hook_ids"
    SHOOTING_PHASE_START_HOOK = "shooting_phase_start_hook_ids"
    UNIT_DESTROYED_HOOK = "unit_destroyed_hook_ids"
    BATTLE_SHOCK_HOOK = "battle_shock_hook_ids"
    ADVANCE_ELIGIBILITY_HOOK = "advance_eligibility_hook_ids"
    ADVANCE_MOVE_HOOK = "advance_move_hook_ids"
    FALL_BACK_HOOK = "fall_back_hook_ids"
    MOVEMENT_END_SURGE_HOOK = "movement_end_surge_hook_ids"
    RESERVE_ARRIVAL_DISTANCE_HOOK = "reserve_arrival_distance_hook_ids"
    RESERVE_ARRIVAL_RESTRICTION_HOOK = "reserve_arrival_restriction_hook_ids"
    UNIT_MOVE_COMPLETED_MORTAL_WOUND_HOOK = "unit_move_completed_mortal_wound_hook_ids"
    UNIT_MOVE_COMPLETED_BATTLE_SHOCK_HOOK = "unit_move_completed_battle_shock_hook_ids"
    MORTAL_WOUND_FEEL_NO_PAIN_HOOK = "mortal_wound_feel_no_pain_hook_ids"
    CHARGE_DECLARATION_HOOK = "charge_declaration_hook_ids"
    SHOOTING_TARGET_RESTRICTION_HOOK = "shooting_target_restriction_hook_ids"
    CHARGE_TARGET_RESTRICTION_HOOK = "charge_target_restriction_hook_ids"
    SHOOTING_UNIT_SELECTED_HOOK = "shooting_unit_selected_hook_ids"
    SHOOTING_UNIT_SELECTED_GRANT_HOOK = "shooting_unit_selected_grant_hook_ids"
    ATTACK_SEQUENCE_COMPLETED_HOOK = "attack_sequence_completed_hook_ids"
    SHOOTING_END_SURGE_HOOK = "shooting_end_surge_hook_ids"
    ENHANCEMENT_EFFECT_BINDING = "enhancement_effect_binding_ids"
    FIGHT_ACTIVATION_ABILITY_HOOK = "fight_activation_ability_hook_ids"
    FIGHT_UNIT_SELECTED_HOOK = "fight_unit_selected_hook_ids"
    FIGHT_UNIT_SELECTED_GRANT_HOOK = "fight_unit_selected_grant_hook_ids"
    PHASE_END_OBJECTIVE_CONTROL_HOOK = "phase_end_objective_control_hook_ids"
    STRATAGEM_COST_CHOICE_HOOK = "stratagem_cost_choice_hook_ids"
    STRATAGEM_COST_MODIFIER = "stratagem_cost_modifier_ids"
    UNIT_CHARACTERISTIC_MODIFIER = "unit_characteristic_modifier_ids"
    HIT_ROLL_MODIFIER = "hit_roll_modifier_ids"
    WOUND_ROLL_MODIFIER = "wound_roll_modifier_ids"
    DAMAGE_ROLL_MODIFIER = "damage_roll_modifier_ids"
    ALLOCATED_ATTACK_DAMAGE_MODIFIER = "allocated_attack_damage_modifier_ids"
    SAVE_OPTION_MODIFIER = "save_option_modifier_ids"
    MOVEMENT_BUDGET_MODIFIER = "movement_budget_modifier_ids"
    OBJECTIVE_CONTROL_MODIFIER = "objective_control_modifier_ids"
    ADVANCE_ROLL_MODIFIER = "advance_roll_modifier_ids"
    CHARGE_ROLL_MODIFIER = "charge_roll_modifier_ids"
    WEAPON_PROFILE_MODIFIER = "weapon_profile_modifier_ids"
    ATTACK_REROLL_PERMISSION_MODIFIER = "attack_reroll_permission_modifier_ids"
    POST_ROLL_WEAPON_PROFILE_MODIFIER = "post_roll_weapon_profile_modifier_ids"
    FAILED_SAVE_DAMAGE_REPLACEMENT_MODIFIER = "failed_save_damage_replacement_modifier_ids"
    EVENT_SUBSCRIPTION = "event_subscription_id"
    EVENT_SOURCE_RULE = "event_source_rule_id"
    EVENT_HANDLER = "event_handler_id"
    FACTION_EXECUTION_RECORD = "faction_execution_record_id"


_RUNTIME_EVIDENCE_SUMMARY_PROVIDERS: Final = tuple(
    provider
    for provider in RuntimeEvidenceProvider
    if provider
    not in {
        RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING,
        RuntimeEvidenceProvider.EVENT_SUBSCRIPTION,
        RuntimeEvidenceProvider.EVENT_SOURCE_RULE,
        RuntimeEvidenceProvider.EVENT_HANDLER,
        RuntimeEvidenceProvider.FACTION_EXECUTION_RECORD,
    }
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
        *default_datasheet_faction_access_registry().runtime_consumer_ids,
    }
)


@dataclass(frozen=True, slots=True)
class ActiveRuntimeEvidenceRecord:
    evidence_id: str
    provider: RuntimeEvidenceProvider
    owner_content_id: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _validated_evidence_id(self.evidence_id))
        if type(self.provider) is not RuntimeEvidenceProvider:
            raise GameLifecycleError("Runtime evidence record provider is invalid.")
        if self.owner_content_id is not None:
            object.__setattr__(
                self,
                "owner_content_id",
                _validated_evidence_id(self.owner_content_id),
            )
        if self.source_id is not None:
            object.__setattr__(self, "source_id", _validated_evidence_id(self.source_id))


@dataclass(frozen=True, slots=True)
class ActiveRuntimeEvidenceInventory:
    records: tuple[ActiveRuntimeEvidenceRecord, ...]

    def __post_init__(self) -> None:
        if type(self.records) is not tuple or any(
            type(record) is not ActiveRuntimeEvidenceRecord for record in self.records
        ):
            raise GameLifecycleError("Runtime evidence inventory requires typed records.")
        expected_order = tuple(sorted(self.records, key=_evidence_record_sort_key))
        if self.records != expected_order or len(set(self.records)) != len(self.records):
            raise GameLifecycleError(
                "Runtime evidence inventory records must be unique and sorted."
            )

    @classmethod
    def from_records(cls, records: set[ActiveRuntimeEvidenceRecord]) -> Self:
        if type(records) is not set or any(
            type(record) is not ActiveRuntimeEvidenceRecord for record in records
        ):
            raise GameLifecycleError("Runtime evidence inventory requires a record set.")
        return cls(records=tuple(sorted(records, key=_evidence_record_sort_key)))

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset(record.evidence_id for record in self.records)

    def records_for_evidence_id(
        self,
        evidence_id: str,
    ) -> frozenset[ActiveRuntimeEvidenceRecord]:
        validated_id = _validated_evidence_id(evidence_id)
        return frozenset(record for record in self.records if record.evidence_id == validated_id)


def active_runtime_evidence_inventory(
    bundle: RuntimeContentBundle,
) -> ActiveRuntimeEvidenceInventory:
    if type(bundle) is not RuntimeContentBundle:
        raise GameLifecycleError("Runtime evidence requires a RuntimeContentBundle.")
    payload = cast(Mapping[str, JsonValue], bundle.to_summary_payload())
    records: set[ActiveRuntimeEvidenceRecord] = set()
    active_handler_ids: set[str] = set()
    for provider in _RUNTIME_EVIDENCE_SUMMARY_PROVIDERS:
        values = payload[provider.value]
        if not isinstance(values, list) or any(type(value) is not str for value in values):
            raise GameLifecycleError("Runtime bundle evidence summary shape drifted.")
        typed_values = cast(list[str], values)
        active_handler_ids.update(typed_values)
        records.update(
            ActiveRuntimeEvidenceRecord(evidence_id=value, provider=provider)
            for value in typed_values
        )

    enhancement_bindings = bundle.enhancement_effect_registry.all_bindings()
    enhancement_binding_ids = [binding.effect_id for binding in enhancement_bindings]
    if payload[RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING.value] != (
        enhancement_binding_ids
    ):
        raise GameLifecycleError("Runtime bundle enhancement evidence summary drifted.")
    active_handler_ids.update(enhancement_binding_ids)
    records.update(
        ActiveRuntimeEvidenceRecord(
            evidence_id=binding.effect_id,
            provider=RuntimeEvidenceProvider.ENHANCEMENT_EFFECT_BINDING,
            owner_content_id=binding.enhancement_id,
            source_id=binding.source_id,
        )
        for binding in enhancement_bindings
    )

    event_subscriptions = payload["event_subscriptions"]
    if not isinstance(event_subscriptions, list):
        raise GameLifecycleError("Runtime bundle event evidence summary shape drifted.")
    for subscription in event_subscriptions:
        if not isinstance(subscription, dict):
            raise GameLifecycleError("Runtime bundle event evidence summary shape drifted.")
        for field_name, provider in (
            ("subscription_id", RuntimeEvidenceProvider.EVENT_SUBSCRIPTION),
            ("source_rule_id", RuntimeEvidenceProvider.EVENT_SOURCE_RULE),
            ("handler_id", RuntimeEvidenceProvider.EVENT_HANDLER),
        ):
            value = subscription.get(field_name)
            if type(value) is not str or not value.strip():
                raise GameLifecycleError("Runtime bundle event evidence summary shape drifted.")
            records.add(ActiveRuntimeEvidenceRecord(evidence_id=value, provider=provider))
            if field_name == "handler_id":
                active_handler_ids.add(value)
    active_execution_ids = bundle.faction_rule_execution_registry.active_execution_record_ids(
        active_handler_ids=frozenset(active_handler_ids)
    )
    records.update(
        ActiveRuntimeEvidenceRecord(
            evidence_id=execution_id,
            provider=RuntimeEvidenceProvider.FACTION_EXECUTION_RECORD,
            owner_content_id=(
                bundle.faction_rule_execution_registry.record_by_execution_id(execution_id).rule_id
            ),
        )
        for execution_id in active_execution_ids
    )
    return ActiveRuntimeEvidenceInventory.from_records(records)


def validate_active_runtime_consumer_ids(
    *,
    runtime_consumer_ids: tuple[str, ...],
    expected_active_evidence: ActiveRuntimeEvidenceInventory,
    active_evidence: ActiveRuntimeEvidenceInventory,
    context: str,
) -> None:
    if type(runtime_consumer_ids) is not tuple or any(
        type(consumer_id) is not str or not consumer_id.strip()
        for consumer_id in runtime_consumer_ids
    ):
        raise GameLifecycleError("Runtime consumer evidence IDs must be a tuple of strings.")
    if type(context) is not str or not context.strip():
        raise GameLifecycleError("Runtime consumer evidence context must be a string.")
    _validate_active_evidence_inventory(
        expected_active_evidence,
        field_name="Expected active runtime evidence",
    )
    _validate_active_evidence_inventory(
        active_evidence,
        field_name="Active runtime evidence",
    )
    registered_catalog_ids = frozenset(catalog_rule_ir_registered_hook_ids())
    registered_descriptor_ids = frozenset(catalog_descriptor_registered_runtime_consumer_ids())
    missing_ids: list[str] = []
    unregistered_ids: list[str] = []
    outside_activation_ids: list[str] = []
    for consumer_id in runtime_consumer_ids:
        required_evidence_id = _required_bundle_evidence_id(
            consumer_id=consumer_id,
            expected_active_evidence_ids=expected_active_evidence.evidence_ids,
            registered_catalog_ids=registered_catalog_ids,
            registered_descriptor_ids=registered_descriptor_ids,
        )
        if required_evidence_id is None:
            continue
        if required_evidence_id == "":
            unregistered_ids.append(consumer_id)
            continue
        if required_evidence_id not in expected_active_evidence.evidence_ids:
            outside_activation_ids.append(consumer_id)
            continue
        expected_records = expected_active_evidence.records_for_evidence_id(required_evidence_id)
        active_records = active_evidence.records_for_evidence_id(required_evidence_id)
        for missing_record in sorted(
            expected_records - active_records,
            key=_evidence_record_sort_key,
        ):
            evidence_reference = (
                consumer_id
                if required_evidence_id == consumer_id
                else f"{consumer_id} -> {required_evidence_id}"
            )
            owner_reference = (
                ""
                if missing_record.owner_content_id is None
                else f" owner={missing_record.owner_content_id}"
            )
            source_reference = (
                "" if missing_record.source_id is None else f" source={missing_record.source_id}"
            )
            missing_ids.append(
                f"{evidence_reference} "
                f"[{missing_record.provider.value}{owner_reference}{source_reference}]"
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


def _validate_active_evidence_inventory(
    inventory: ActiveRuntimeEvidenceInventory,
    *,
    field_name: str,
) -> None:
    if type(inventory) is not ActiveRuntimeEvidenceInventory:
        raise GameLifecycleError(f"{field_name} must be an ActiveRuntimeEvidenceInventory.")


def _evidence_record_sort_key(
    record: ActiveRuntimeEvidenceRecord,
) -> tuple[str, str, str, str]:
    return (
        record.evidence_id,
        record.provider.value,
        record.owner_content_id or "",
        record.source_id or "",
    )


def _validated_evidence_id(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError("Runtime evidence IDs must be non-empty strings.")
    return value


__all__ = (
    "ActiveRuntimeEvidenceInventory",
    "ActiveRuntimeEvidenceRecord",
    "RuntimeEvidenceProvider",
    "active_runtime_evidence_inventory",
    "validate_active_runtime_consumer_ids",
)
