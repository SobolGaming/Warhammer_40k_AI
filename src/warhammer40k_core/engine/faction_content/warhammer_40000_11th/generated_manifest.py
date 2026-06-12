from __future__ import annotations

from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifestRow,
    RuntimeContentModuleFamily,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)

_BASE = "warhammer40k_core.engine.faction_content.warhammer_40000_11th"
_SOURCE_HASH = faction_execution_2026_27.source_package_identity_payload()[
    "source_payload_checksum_sha256"
]
_EXECUTION_RECORDS = faction_execution_2026_27.execution_records()


def generated_runtime_content_rows() -> tuple[RuntimeContentManifestRow, ...]:
    return (
        _row(
            content_id="death-guard",
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=_source_ids_for(faction_id="death-guard", detachment_id=None),
            owner_faction_id="death-guard",
            owner_detachment_id=None,
            execution_record_ids=_execution_ids_for(faction_id="death-guard", detachment_id=None),
            module_path=f"{_BASE}.death_guard.manifest",
        ),
        _row(
            content_id="flyblown-host",
            family=RuntimeContentModuleFamily.DETACHMENT,
            source_ids=_source_ids_for(faction_id="death-guard", detachment_id="flyblown-host"),
            owner_faction_id="death-guard",
            owner_detachment_id="flyblown-host",
            execution_record_ids=_execution_ids_for(
                faction_id="death-guard",
                detachment_id="flyblown-host",
            ),
            module_path=f"{_BASE}.death_guard.detachments.flyblown_host.manifest",
        ),
        _row(
            content_id="tallyband-summoners",
            family=RuntimeContentModuleFamily.DETACHMENT,
            source_ids=_source_ids_for(
                faction_id="death-guard",
                detachment_id="tallyband-summoners",
            ),
            owner_faction_id="death-guard",
            owner_detachment_id="tallyband-summoners",
            execution_record_ids=_execution_ids_for(
                faction_id="death-guard",
                detachment_id="tallyband-summoners",
            ),
            module_path=f"{_BASE}.death_guard.detachments.tallyband_summoners.manifest",
        ),
        _row(
            content_id="plague-marines",
            family=RuntimeContentModuleFamily.DATASHEET,
            source_ids=_source_ids_for(faction_id="death-guard", detachment_id=None),
            owner_faction_id="death-guard",
            owner_detachment_id=None,
            execution_record_ids=_execution_ids_matching("death-guard:datasheet-intake"),
            module_path=f"{_BASE}.death_guard.units.plague_marines",
        ),
        _row(
            content_id="typhus",
            family=RuntimeContentModuleFamily.DATASHEET,
            source_ids=_source_ids_for(faction_id="death-guard", detachment_id=None),
            owner_faction_id="death-guard",
            owner_detachment_id=None,
            execution_record_ids=_execution_ids_matching("death-guard:datasheet-intake"),
            module_path=f"{_BASE}.death_guard.units.typhus",
        ),
        _row(
            content_id="plague-weapons",
            family=RuntimeContentModuleFamily.WARGEAR,
            source_ids=_source_ids_for(faction_id="death-guard", detachment_id=None),
            owner_faction_id="death-guard",
            owner_detachment_id=None,
            execution_record_ids=_execution_ids_matching("death-guard:datasheet-intake"),
            module_path=f"{_BASE}.death_guard.wargear.plague_weapons",
            dependency_ids=("plague-weapons:standard",),
        ),
        _row(
            content_id="plague-weapons:standard",
            family=RuntimeContentModuleFamily.WEAPON_PROFILE,
            source_ids=_source_ids_for(faction_id="death-guard", detachment_id=None),
            owner_faction_id="death-guard",
            owner_detachment_id=None,
            execution_record_ids=_execution_ids_matching("death-guard:datasheet-intake"),
            module_path=f"{_BASE}.death_guard.wargear.plague_weapons",
        ),
    )


def _row(
    *,
    content_id: str,
    family: RuntimeContentModuleFamily,
    source_ids: tuple[str, ...],
    owner_faction_id: str | None,
    owner_detachment_id: str | None,
    execution_record_ids: tuple[str, ...],
    module_path: str,
    dependency_ids: tuple[str, ...] = (),
) -> RuntimeContentManifestRow:
    return RuntimeContentManifestRow(
        content_id=content_id,
        family=family,
        source_ids=source_ids,
        owner_faction_id=owner_faction_id,
        owner_detachment_id=owner_detachment_id,
        source_package_hash=_SOURCE_HASH,
        execution_record_ids=execution_record_ids,
        module_path=module_path,
        support_status=RuntimeContentSupportStatus.SUPPORTED,
        dependency_ids=dependency_ids,
    )


def _execution_ids_for(
    *,
    faction_id: str,
    detachment_id: str | None,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            record.execution_id
            for record in _EXECUTION_RECORDS
            if record.faction_id == faction_id and record.detachment_id == detachment_id
        )
    )


def _execution_ids_matching(token: str) -> tuple[str, ...]:
    return tuple(
        sorted(record.execution_id for record in _EXECUTION_RECORDS if token in record.execution_id)
    )


def _source_ids_for(
    *,
    faction_id: str,
    detachment_id: str | None,
) -> tuple[str, ...]:
    source_ids = {
        source_id
        for record in _EXECUTION_RECORDS
        if record.faction_id == faction_id and record.detachment_id == detachment_id
        for source_id in record.source_ids
    }
    return tuple(sorted(source_ids))
