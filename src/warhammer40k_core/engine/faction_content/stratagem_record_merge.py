from __future__ import annotations

from warhammer40k_core.engine.faction_content import bundle_validation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemCatalogRecord

StratagemGameplayKey = tuple[str, str | None, str]

_validate_tuple = bundle_validation.validate_tuple


def merge_stratagem_records_with_contribution_overrides(
    base_stratagem_records: object,
    contribution_stratagem_records: tuple[StratagemCatalogRecord, ...],
) -> tuple[StratagemCatalogRecord, ...]:
    base_records = _validate_tuple(
        "base stratagem_records",
        base_stratagem_records,
        StratagemCatalogRecord,
    )
    contribution_records = _validate_tuple(
        "contribution stratagem_records",
        contribution_stratagem_records,
        StratagemCatalogRecord,
    )
    contribution_keys = frozenset(
        _stratagem_gameplay_key(record) for record in contribution_records
    )
    return (
        *(
            record
            for record in base_records
            if _stratagem_gameplay_key(record) not in contribution_keys
        ),
        *contribution_records,
    )


def combine_stratagem_indexes_with_runtime_overrides(
    *,
    base_indexes: tuple[StratagemCatalogIndex, ...],
    runtime_indexes: tuple[StratagemCatalogIndex, ...],
) -> StratagemCatalogIndex:
    base_records = _records_by_id(
        indexes=base_indexes,
        field_name="base indexes",
        drift_message="Base Stratagem record ID drift across phase indexes.",
    )
    runtime_records = _records_by_id(
        indexes=runtime_indexes,
        field_name="runtime indexes",
        drift_message="Runtime Stratagem record ID drift across player indexes.",
    )
    return StratagemCatalogIndex.from_records(
        merge_stratagem_records_with_contribution_overrides(
            tuple(base_records.values()),
            tuple(runtime_records.values()),
        )
    )


def _records_by_id(
    *,
    indexes: object,
    field_name: str,
    drift_message: str,
) -> dict[str, StratagemCatalogRecord]:
    validated_indexes = _validate_tuple(field_name, indexes, StratagemCatalogIndex)
    records_by_id: dict[str, StratagemCatalogRecord] = {}
    for index in validated_indexes:
        for record in index.all_records():
            existing = records_by_id.get(record.record_id)
            if existing is not None and existing != record:
                raise GameLifecycleError(drift_message)
            records_by_id[record.record_id] = record
    return records_by_id


def _stratagem_gameplay_key(record: StratagemCatalogRecord) -> StratagemGameplayKey:
    if type(record) is not StratagemCatalogRecord:
        raise GameLifecycleError("Stratagem gameplay key requires a catalog record.")
    return (
        record.availability_kind.value,
        record.detachment_id,
        record.definition.stratagem_id,
    )
