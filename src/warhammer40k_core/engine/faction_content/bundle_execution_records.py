from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle_validation import (
    validate_identifier_tuple,
    validate_tuple,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)


def selected_faction_execution_records(
    available_records: tuple[Phase17FExecutionRecord, ...],
    selected_execution_record_ids: tuple[str, ...],
) -> tuple[Phase17FExecutionRecord, ...]:
    ids = validate_identifier_tuple(
        "selected_execution_record_ids",
        selected_execution_record_ids,
    )
    selected_ids = set(ids)
    if not selected_ids:
        return ()
    records_by_id: dict[str, Phase17FExecutionRecord] = {}
    records = validate_tuple(
        "faction_execution_records",
        available_records,
        Phase17FExecutionRecord,
    )
    for record in records:
        if record.execution_id in records_by_id:
            raise GameLifecycleError("Runtime content faction execution record IDs must be unique.")
        records_by_id[record.execution_id] = record
    missing_ids = tuple(sorted(selected_ids.difference(records_by_id)))
    if missing_ids:
        raise GameLifecycleError(
            f"Runtime content selected unknown faction execution records: {', '.join(missing_ids)}."
        )
    return tuple(records_by_id[execution_id] for execution_id in sorted(selected_ids))
