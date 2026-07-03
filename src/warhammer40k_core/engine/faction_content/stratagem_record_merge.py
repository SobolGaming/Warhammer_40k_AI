from __future__ import annotations

from warhammer40k_core.engine.faction_content import bundle_validation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import StratagemCatalogRecord

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


def _stratagem_gameplay_key(record: StratagemCatalogRecord) -> StratagemGameplayKey:
    if type(record) is not StratagemCatalogRecord:
        raise GameLifecycleError("Stratagem gameplay key requires a catalog record.")
    return (
        record.availability_kind.value,
        record.detachment_id,
        record.definition.stratagem_id,
    )
