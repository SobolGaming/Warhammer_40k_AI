from __future__ import annotations

from warhammer40k_core.engine.abilities import AbilityCatalogRecord
from warhammer40k_core.engine.faction_content import bundle_validation
from warhammer40k_core.engine.phase import GameLifecycleError

AbilityGameplayKey = tuple[str, str | None, str | None, str | None, str | None, str | None, str]

_validate_tuple = bundle_validation.validate_tuple


def merge_ability_records_with_contribution_overrides(
    base_ability_records: object,
    contribution_ability_records: tuple[AbilityCatalogRecord, ...],
) -> tuple[AbilityCatalogRecord, ...]:
    base_records = _validate_tuple(
        "base ability_records",
        base_ability_records,
        AbilityCatalogRecord,
    )
    contribution_records = _validate_tuple(
        "contribution ability_records",
        contribution_ability_records,
        AbilityCatalogRecord,
    )
    contribution_keys = frozenset(_ability_gameplay_key(record) for record in contribution_records)
    merged = (
        *(
            record
            for record in base_records
            if _ability_gameplay_key(record) not in contribution_keys
        ),
        *contribution_records,
    )
    record_ids = tuple(record.record_id for record in merged)
    if len(record_ids) != len(set(record_ids)):
        raise GameLifecycleError("Merged ability catalog record IDs must be unique.")
    return merged


def _ability_gameplay_key(record: AbilityCatalogRecord) -> AbilityGameplayKey:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Ability gameplay key requires a catalog record.")
    return (
        record.source_kind.value,
        record.faction_id,
        record.detachment_id,
        record.datasheet_id,
        record.wargear_id,
        record.weapon_profile_id,
        record.definition.ability_id,
    )
