from __future__ import annotations

from typing import cast

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    StratagemAvailabilityKind,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_stratagems as source_data,
)

ELEVENTH_EDITION_CORE_STRATAGEM_SOURCE_PACKAGE_ID = source_data.SOURCE_PACKAGE_ID


def eleventh_edition_core_stratagem_catalog_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.core_stratagem_rows())


def eleventh_edition_core_stratagem_index() -> StratagemCatalogIndex:
    return StratagemCatalogIndex.from_records(eleventh_edition_core_stratagem_catalog_records())


def eleventh_edition_detachment_stratagem_catalog_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.detachment_stratagem_rows())


def eleventh_edition_stratagem_catalog_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.stratagem_rows())


def eleventh_edition_stratagem_index() -> StratagemCatalogIndex:
    return StratagemCatalogIndex.from_records(eleventh_edition_stratagem_catalog_records())


def build_player_stratagem_index(
    records: tuple[StratagemCatalogRecord, ...],
    *,
    detachment_id: str | None,
    stratagem_ids: tuple[str, ...],
) -> StratagemCatalogIndex:
    validated_records = StratagemCatalogIndex.from_records(records).all_records()
    selected_detachment_id = _validate_optional_identifier(
        "Player Stratagem index detachment_id",
        detachment_id,
    )
    selected_stratagem_ids = frozenset(
        _validate_identifier_tuple("Player Stratagem index stratagem_ids", stratagem_ids)
    )
    player_records: list[StratagemCatalogRecord] = []
    for record in validated_records:
        if record.availability_kind is StratagemAvailabilityKind.CORE:
            player_records.append(record)
            continue
        if (
            selected_detachment_id is not None
            and record.detachment_id == selected_detachment_id
            and record.definition.stratagem_id in selected_stratagem_ids
        ):
            player_records.append(record)
    return StratagemCatalogIndex.from_records(tuple(player_records))


def _record_from_source_row(row: source_data.SourceStratagemRow) -> StratagemCatalogRecord:
    return StratagemCatalogRecord(
        record_id=f"{source_data.SOURCE_PACKAGE_ID}:{row.availability_kind}:{row.stratagem_id}",
        definition=StratagemDefinition(
            stratagem_id=row.stratagem_id,
            name=row.name,
            source_id=row.source_id,
            command_point_cost=row.command_point_cost,
            category=StratagemCategory(row.category),
            when_descriptor=row.when_descriptor,
            target_descriptor=row.target_descriptor,
            effect_descriptor=row.effect_descriptor,
            restrictions_descriptor=row.restrictions_descriptor,
            timing=StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind(row.trigger_kind),
                phase=None if row.phase is None else battle_phase_kind_from_token(row.phase),
            ),
            restriction_policy=StratagemRestrictionPolicy(
                same_unit_target_per_phase=row.same_unit_target_per_phase,
                once_per_turn=row.once_per_turn,
                once_per_battle=row.once_per_battle,
                once_per_target_per_phase=row.once_per_target_per_phase,
                allow_battle_shocked_targets=row.allow_battle_shocked_targets,
            ),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind(row.target_kind),
                enumerable=row.enumerable,
                target_policy_id=row.target_policy_id,
            ),
            handler_id=row.handler_id,
            eligible_roll_types=row.eligible_roll_types,
            effect_payload=validate_json_value(row.effect_payload),
        ),
        availability_kind=StratagemAvailabilityKind(row.availability_kind),
        detachment_id=row.detachment_id,
        disabled=row.disabled,
    )


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
