from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.stratagems import (
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_10th import (
    core_stratagems as source_data,
)

TENTH_EDITION_CORE_STRATAGEM_SOURCE_PACKAGE_ID = source_data.SOURCE_PACKAGE_ID


def tenth_edition_core_stratagem_catalog_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.core_stratagem_rows())


def tenth_edition_detachment_stratagem_catalog_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.detachment_stratagem_rows())


def tenth_edition_stratagem_catalog_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.stratagem_rows())


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
        ),
        availability_kind=StratagemAvailabilityKind(row.availability_kind),
        detachment_id=row.detachment_id,
        disabled=row.disabled,
    )
