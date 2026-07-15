from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.tracked_targets import (
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
)


def canonical_rules_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> str:
    return rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=unit_instance_id,
    ).unit_instance_id


def canonical_tracked_target_source_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
    model_instance_id: str | None,
    owner_scope: TrackedTargetOwnerScope,
) -> str:
    rules_unit = rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=unit_instance_id,
    )
    if owner_scope is TrackedTargetOwnerScope.THIS_UNIT:
        return rules_unit.unit_instance_id
    if model_instance_id is None:
        raise GameLifecycleError("THIS_MODEL tracked target requires a source model.")
    return rules_unit.component_unit_id_for_model(model_instance_id)


def validate_canonical_tracked_target_record(
    *,
    armies: tuple[ArmyDefinition, ...],
    record: TrackedTargetRecord,
) -> None:
    source_unit_id = canonical_tracked_target_source_unit_id(
        armies=armies,
        unit_instance_id=record.source_unit_instance_id,
        model_instance_id=record.source_model_instance_id,
        owner_scope=record.owner_scope,
    )
    if record.source_unit_instance_id != source_unit_id:
        raise GameLifecycleError("Tracked target source unit is not canonical.")
    target_unit_id = canonical_rules_unit_id(
        armies=armies,
        unit_instance_id=record.target_unit_instance_id,
    )
    if record.target_unit_instance_id != target_unit_id:
        raise GameLifecycleError("Tracked target target unit is not canonical.")


def active_tracked_target_for(
    *,
    armies: tuple[ArmyDefinition, ...],
    records: list[TrackedTargetRecord],
    source_rule_id: str,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
    owner_scope: TrackedTargetOwnerScope,
    role: TrackedTargetRole,
) -> TrackedTargetRecord | None:
    requested_rule = _validate_identifier("source_rule_id", source_rule_id)
    requested_unit = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    requested_model = (
        None
        if source_model_instance_id is None
        else _validate_identifier("source_model_instance_id", source_model_instance_id)
    )
    if type(owner_scope) is not TrackedTargetOwnerScope:
        raise GameLifecycleError("Tracked target owner_scope must be TrackedTargetOwnerScope.")
    if type(role) is not TrackedTargetRole:
        raise GameLifecycleError("Tracked target role must be TrackedTargetRole.")
    source_unit_id = canonical_tracked_target_source_unit_id(
        armies=armies,
        unit_instance_id=requested_unit,
        model_instance_id=requested_model,
        owner_scope=owner_scope,
    )
    matches = tuple(
        record
        for record in records
        if record.active
        and record.source_rule_id == requested_rule
        and record.source_unit_instance_id == source_unit_id
        and record.source_model_instance_id == requested_model
        and record.owner_scope is owner_scope
        and record.role is role
    )
    if len(matches) > 1:
        raise GameLifecycleError("Tracked target active source key is duplicated.")
    return matches[0] if matches else None


def tracked_targets_for_destroyed_unit(
    *,
    armies: tuple[ArmyDefinition, ...],
    records: list[TrackedTargetRecord],
    destroyed_unit_instance_id: str,
    destroyed_rules_unit_instance_ids: set[str],
) -> tuple[TrackedTargetRecord, ...]:
    requested_unit = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    destroyed_rules_unit_id = canonical_rules_unit_id(
        armies=armies,
        unit_instance_id=requested_unit,
    )
    if destroyed_rules_unit_id not in destroyed_rules_unit_instance_ids:
        return ()
    return tuple(
        sorted(
            (
                record
                for record in records
                if record.active and record.target_unit_instance_id == destroyed_rules_unit_id
            ),
            key=lambda record: record.record_id,
        )
    )


def attached_rules_unit_ids(armies: tuple[ArmyDefinition, ...]) -> set[str]:
    return {
        attached_unit.attached_unit_instance_id
        for army in armies
        for attached_unit in army.attached_units
    }


def attached_rules_unit_owner_ids(armies: tuple[ArmyDefinition, ...]) -> dict[str, str]:
    return {
        attached_unit.attached_unit_instance_id: army.player_id
        for army in armies
        for attached_unit in army.attached_units
    }


def destroyed_attached_rules_unit_ids(
    *,
    armies: tuple[ArmyDefinition, ...],
    removed_model_ids: set[str],
) -> set[str]:
    destroyed: set[str] = set()
    for army in armies:
        for attached_unit in army.attached_units:
            model_ids = {
                model.model_instance_id
                for unit in army.units
                if unit.unit_instance_id in attached_unit.component_unit_instance_ids
                for model in unit.own_models
            }
            if model_ids and model_ids <= removed_model_ids:
                destroyed.add(attached_unit.attached_unit_instance_id)
    return destroyed


_validate_identifier = IdentifierValidator(GameLifecycleError)
