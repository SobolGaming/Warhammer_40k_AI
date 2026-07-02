from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.phase import GameLifecycleError


class RuntimeContentModuleFamily(StrEnum):
    FACTION = "faction"
    DETACHMENT = "detachment"
    ENHANCEMENT = "enhancement"
    STRATAGEM = "stratagem"
    DATASHEET = "datasheet"
    WARGEAR = "wargear"
    WEAPON_PROFILE = "weapon_profile"


class RuntimeContentSupportStatus(StrEnum):
    """Manifest load-support status, not semantic gameplay execution coverage.

    SUPPORTED means a selected content row has an importable runtime module path.
    Semantic rule execution remains owned by source-backed execution records,
    handler bindings, and contribution records. Scaffold modules can therefore
    be load-supported while contributing no gameplay effects yet.
    """

    SUPPORTED = "supported"
    SOURCE_ONLY = "source_only"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class RuntimeContentManifestRow:
    content_id: str
    family: RuntimeContentModuleFamily
    source_ids: tuple[str, ...]
    owner_faction_id: str | None
    owner_detachment_id: str | None
    source_package_id: str
    source_package_hash: str | None
    execution_record_ids: tuple[str, ...]
    module_path: str | None
    support_status: RuntimeContentSupportStatus
    dependency_ids: tuple[str, ...] = ()
    support_reason: str | None = None
    unsupported_reason: str | None = None
    required_for_matched_play: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_id", _validate_identifier("content_id", self.content_id))
        object.__setattr__(self, "family", _module_family_from_token(self.family))
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )
        object.__setattr__(
            self,
            "owner_faction_id",
            _validate_optional_identifier("owner_faction_id", self.owner_faction_id),
        )
        object.__setattr__(
            self,
            "owner_detachment_id",
            _validate_optional_identifier("owner_detachment_id", self.owner_detachment_id),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("source_package_id", self.source_package_id),
        )
        object.__setattr__(
            self,
            "source_package_hash",
            _validate_optional_identifier("source_package_hash", self.source_package_hash),
        )
        object.__setattr__(
            self,
            "execution_record_ids",
            _validate_identifier_tuple("execution_record_ids", self.execution_record_ids),
        )
        object.__setattr__(
            self,
            "module_path",
            _validate_optional_module_path("module_path", self.module_path),
        )
        object.__setattr__(
            self,
            "support_status",
            _support_status_from_token(self.support_status),
        )
        object.__setattr__(
            self,
            "dependency_ids",
            _validate_identifier_tuple("dependency_ids", self.dependency_ids),
        )
        object.__setattr__(
            self,
            "support_reason",
            _validate_optional_identifier("support_reason", self.support_reason),
        )
        object.__setattr__(
            self,
            "unsupported_reason",
            _validate_optional_identifier("unsupported_reason", self.unsupported_reason),
        )
        if type(self.required_for_matched_play) is not bool:
            raise GameLifecycleError(
                "Runtime content manifest required_for_matched_play must be a bool."
            )
        if (
            self.support_status is RuntimeContentSupportStatus.SUPPORTED
            and self.module_path is None
        ):
            raise GameLifecycleError("Supported runtime manifest rows require module_path.")
        if (
            self.support_status is not RuntimeContentSupportStatus.SUPPORTED
            and self.module_path is not None
        ):
            raise GameLifecycleError("Non-supported runtime manifest rows must not import code.")
        if (
            self.support_status is RuntimeContentSupportStatus.UNSUPPORTED
            and self.unsupported_reason is None
        ):
            raise GameLifecycleError(
                "Unsupported runtime manifest rows require unsupported_reason."
            )
        if (
            self.support_status is not RuntimeContentSupportStatus.UNSUPPORTED
            and self.unsupported_reason is not None
        ):
            raise GameLifecycleError(
                "Supported and source-only runtime manifest rows cannot include unsupported_reason."
            )

    def to_summary_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "content_id": self.content_id,
                    "family": self.family.value,
                    "source_ids": list(self.source_ids),
                    "owner_faction_id": self.owner_faction_id,
                    "owner_detachment_id": self.owner_detachment_id,
                    "source_package_id": self.source_package_id,
                    "source_package_hash": self.source_package_hash,
                    "execution_record_ids": list(self.execution_record_ids),
                    "module_path": self.module_path,
                    "support_status": self.support_status.value,
                    "dependency_ids": list(self.dependency_ids),
                    "support_reason": self.support_reason,
                    "unsupported_reason": self.unsupported_reason,
                    "required_for_matched_play": self.required_for_matched_play,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeContentManifest:
    rows: tuple[RuntimeContentManifestRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", _validate_rows(self.rows))

    @classmethod
    def from_catalog(
        cls,
        *,
        catalog: ArmyCatalog,
        generated_rows: tuple[RuntimeContentManifestRow, ...],
    ) -> Self:
        if type(catalog) is not ArmyCatalog:
            raise GameLifecycleError("Runtime content manifest generation requires ArmyCatalog.")
        catalog_rows = _catalog_manifest_rows(catalog)
        rows_by_id: dict[str, RuntimeContentManifestRow] = {
            row.content_id: row for row in catalog_rows
        }
        for generated_row in _validate_rows(generated_rows):
            existing = rows_by_id.get(generated_row.content_id)
            if existing is None:
                rows_by_id[generated_row.content_id] = generated_row
                continue
            rows_by_id[generated_row.content_id] = _merge_generated_row(existing, generated_row)
        return cls(rows=tuple(rows_by_id.values()))

    def row_for_content_id(self, content_id: str) -> RuntimeContentManifestRow:
        requested_id = _validate_identifier("content_id", content_id)
        for row in self.rows:
            if row.content_id == requested_id:
                return row
        raise GameLifecycleError(
            f"Runtime content manifest is missing selected support for {requested_id}."
        )

    def reachable_rows_for_content_ids(
        self,
        content_ids: tuple[str, ...],
    ) -> tuple[RuntimeContentManifestRow, ...]:
        pending = list(_validate_identifier_tuple("content_ids", content_ids))
        seen: set[str] = set()
        reachable: list[RuntimeContentManifestRow] = []
        while pending:
            content_id = pending.pop(0)
            if content_id in seen:
                continue
            row = self.row_for_content_id(content_id)
            seen.add(content_id)
            reachable.append(row)
            for dependency_id in row.dependency_ids:
                if dependency_id not in seen:
                    pending.append(dependency_id)
        return tuple(sorted(reachable, key=lambda row: row.content_id))

    def resolve_activation(
        self,
        activation: RuntimeContentActivation,
        *,
        fail_on_required_unsupported: bool = True,
    ) -> RuntimeContentActivation:
        if type(activation) is not RuntimeContentActivation:
            raise GameLifecycleError("Runtime content manifest resolution requires activation.")
        if type(fail_on_required_unsupported) is not bool:
            raise GameLifecycleError("Runtime content manifest unsupported policy must be a bool.")
        reachable_rows = self.reachable_rows_for_content_ids(activation.roster_content_ids())
        unsupported_rows = tuple(
            row
            for row in reachable_rows
            if row.support_status is RuntimeContentSupportStatus.UNSUPPORTED
        )
        if fail_on_required_unsupported:
            required_unsupported = tuple(
                row for row in unsupported_rows if row.required_for_matched_play
            )
            if required_unsupported:
                details = ", ".join(
                    f"{row.content_id}:{row.unsupported_reason}" for row in required_unsupported
                )
                raise GameLifecycleError(
                    f"Runtime content activation includes unsupported required content: {details}."
                )
        selected_module_paths = tuple(
            sorted(
                {
                    row.module_path
                    for row in reachable_rows
                    if row.support_status is RuntimeContentSupportStatus.SUPPORTED
                    and row.module_path is not None
                }
            )
        )
        return activation.with_reachable_content(
            reachable_content_ids=tuple(row.content_id for row in reachable_rows),
            selected_module_paths=selected_module_paths,
            source_package_ids=tuple(sorted({row.source_package_id for row in reachable_rows})),
            source_package_hashes=tuple(
                sorted(
                    {
                        row.source_package_hash
                        for row in reachable_rows
                        if row.source_package_hash is not None
                    }
                )
            ),
            selected_execution_record_ids=tuple(
                sorted(
                    {
                        execution_record_id
                        for row in reachable_rows
                        for execution_record_id in row.execution_record_ids
                    }
                )
            ),
            unsupported_content_ids=tuple(row.content_id for row in unsupported_rows),
            unsupported_reasons_by_content_id={
                row.content_id: _unsupported_reason(row) for row in unsupported_rows
            },
        )

    def to_module_index(self) -> RuntimeContentModuleIndexPayload:
        mappings: dict[RuntimeContentModuleFamily, dict[str, str]] = {
            family: {} for family in RuntimeContentModuleFamily
        }
        for row in self.rows:
            if row.support_status is RuntimeContentSupportStatus.SUPPORTED:
                if row.module_path is None:
                    raise GameLifecycleError("Supported runtime manifest row lacks module_path.")
                mappings[row.family][row.content_id] = row.module_path
        return RuntimeContentModuleIndexPayload(
            faction_modules=mappings[RuntimeContentModuleFamily.FACTION],
            detachment_modules=mappings[RuntimeContentModuleFamily.DETACHMENT],
            enhancement_modules=mappings[RuntimeContentModuleFamily.ENHANCEMENT],
            stratagem_modules=mappings[RuntimeContentModuleFamily.STRATAGEM],
            datasheet_modules=mappings[RuntimeContentModuleFamily.DATASHEET],
            wargear_modules=mappings[RuntimeContentModuleFamily.WARGEAR],
            weapon_profile_modules=mappings[RuntimeContentModuleFamily.WEAPON_PROFILE],
        )


@dataclass(frozen=True, slots=True)
class RuntimeContentModuleIndexPayload:
    faction_modules: Mapping[str, str]
    detachment_modules: Mapping[str, str]
    enhancement_modules: Mapping[str, str]
    stratagem_modules: Mapping[str, str]
    datasheet_modules: Mapping[str, str]
    wargear_modules: Mapping[str, str]
    weapon_profile_modules: Mapping[str, str]


def _catalog_manifest_rows(catalog: ArmyCatalog) -> tuple[RuntimeContentManifestRow, ...]:
    source_package_id = catalog.source_package_id
    rows: list[RuntimeContentManifestRow] = []
    rows.extend(
        RuntimeContentManifestRow(
            content_id=faction.faction_id,
            family=RuntimeContentModuleFamily.FACTION,
            source_ids=faction.source_ids or (faction.stable_identity(),),
            owner_faction_id=faction.faction_id,
            owner_detachment_id=None,
            source_package_id=source_package_id,
            source_package_hash=None,
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
            dependency_ids=(),
        )
        for faction in catalog.factions
    )
    rows.extend(
        RuntimeContentManifestRow(
            content_id=detachment.detachment_id,
            family=RuntimeContentModuleFamily.DETACHMENT,
            source_ids=detachment.source_ids
            or detachment.rule_source_ids
            or (detachment.stable_identity(),),
            owner_faction_id=detachment.faction_id,
            owner_detachment_id=detachment.detachment_id,
            source_package_id=source_package_id,
            source_package_hash=None,
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
            dependency_ids=(*detachment.enhancement_ids, *detachment.stratagem_ids),
        )
        for detachment in catalog.detachments
    )
    rows.extend(
        RuntimeContentManifestRow(
            content_id=enhancement.enhancement_id,
            family=RuntimeContentModuleFamily.ENHANCEMENT,
            source_ids=(enhancement.source_id,),
            owner_faction_id=None,
            owner_detachment_id=_detachment_owner_for_content(
                enhancement.enhancement_id,
                {
                    detachment.detachment_id: detachment.enhancement_ids
                    for detachment in catalog.detachments
                },
            ),
            source_package_id=source_package_id,
            source_package_hash=None,
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
        for enhancement in catalog.enhancements
    )
    rows.extend(
        RuntimeContentManifestRow(
            content_id=stratagem.stratagem_id,
            family=RuntimeContentModuleFamily.STRATAGEM,
            source_ids=(stratagem.source_id,),
            owner_faction_id=None,
            owner_detachment_id=_detachment_owner_for_content(
                stratagem.stratagem_id,
                {
                    detachment.detachment_id: detachment.stratagem_ids
                    for detachment in catalog.detachments
                },
            ),
            source_package_id=source_package_id,
            source_package_hash=None,
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
        for stratagem in catalog.stratagems
    )
    rows.extend(
        RuntimeContentManifestRow(
            content_id=datasheet.datasheet_id,
            family=RuntimeContentModuleFamily.DATASHEET,
            source_ids=datasheet.source_ids or (datasheet.stable_identity(),),
            owner_faction_id=None,
            owner_detachment_id=None,
            source_package_id=source_package_id,
            source_package_hash=None,
            execution_record_ids=(),
            module_path=None,
            support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
        )
        for datasheet in catalog.datasheets
    )
    for wargear in catalog.wargear:
        rows.append(
            RuntimeContentManifestRow(
                content_id=wargear.wargear_id,
                family=RuntimeContentModuleFamily.WARGEAR,
                source_ids=(wargear.stable_identity(),),
                owner_faction_id=None,
                owner_detachment_id=None,
                source_package_id=source_package_id,
                source_package_hash=None,
                execution_record_ids=(),
                module_path=None,
                support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
                dependency_ids=tuple(profile.profile_id for profile in wargear.weapon_profiles),
            )
        )
        rows.extend(
            RuntimeContentManifestRow(
                content_id=profile.profile_id,
                family=RuntimeContentModuleFamily.WEAPON_PROFILE,
                source_ids=(f"{wargear.stable_identity()}:weapon-profile:{profile.profile_id}",),
                owner_faction_id=None,
                owner_detachment_id=None,
                source_package_id=source_package_id,
                source_package_hash=None,
                execution_record_ids=(),
                module_path=None,
                support_status=RuntimeContentSupportStatus.SOURCE_ONLY,
            )
            for profile in wargear.weapon_profiles
        )
    return tuple(rows)


def _merge_generated_row(
    catalog_row: RuntimeContentManifestRow,
    generated_row: RuntimeContentManifestRow,
) -> RuntimeContentManifestRow:
    return replace(
        catalog_row,
        source_ids=generated_row.source_ids or catalog_row.source_ids,
        owner_faction_id=generated_row.owner_faction_id or catalog_row.owner_faction_id,
        owner_detachment_id=generated_row.owner_detachment_id or catalog_row.owner_detachment_id,
        source_package_id=generated_row.source_package_id,
        source_package_hash=generated_row.source_package_hash,
        execution_record_ids=generated_row.execution_record_ids,
        module_path=generated_row.module_path,
        support_status=generated_row.support_status,
        dependency_ids=tuple(sorted({*catalog_row.dependency_ids, *generated_row.dependency_ids})),
        support_reason=generated_row.support_reason,
        unsupported_reason=generated_row.unsupported_reason,
        required_for_matched_play=generated_row.required_for_matched_play,
    )


def _detachment_owner_for_content(
    content_id: str,
    detachment_content_ids: Mapping[str, tuple[str, ...]],
) -> str | None:
    owners = tuple(
        sorted(
            detachment_id
            for detachment_id, content_ids in detachment_content_ids.items()
            if content_id in content_ids
        )
    )
    if len(owners) > 1:
        raise GameLifecycleError("Runtime content manifest content has multiple owners.")
    return None if not owners else owners[0]


def _validate_rows(rows: object) -> tuple[RuntimeContentManifestRow, ...]:
    if type(rows) is not tuple:
        raise GameLifecycleError("Runtime content manifest rows must be a tuple.")
    seen: set[str] = set()
    validated: list[RuntimeContentManifestRow] = []
    for row in cast(tuple[object, ...], rows):
        if type(row) is not RuntimeContentManifestRow:
            raise GameLifecycleError(
                "Runtime content manifest rows must contain RuntimeContentManifestRow values."
            )
        if row.content_id in seen:
            raise GameLifecycleError("Runtime content manifest content IDs must be unique.")
        seen.add(row.content_id)
        validated.append(row)
    return tuple(sorted(validated, key=lambda row: row.content_id))


def _module_family_from_token(token: object) -> RuntimeContentModuleFamily:
    if type(token) is RuntimeContentModuleFamily:
        return token
    if type(token) is not str:
        raise GameLifecycleError("RuntimeContentModuleFamily token must be a string.")
    try:
        return RuntimeContentModuleFamily(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported RuntimeContentModuleFamily token: {token}.") from exc


def _support_status_from_token(token: object) -> RuntimeContentSupportStatus:
    if type(token) is RuntimeContentSupportStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("RuntimeContentSupportStatus token must be a string.")
    try:
        return RuntimeContentSupportStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported RuntimeContentSupportStatus token: {token}."
        ) from exc


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Runtime content manifest {field_name} must be a tuple.")
    seen: set[str] = set()
    identifiers: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(
                f"Runtime content manifest {field_name} must not contain duplicates."
            )
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_optional_module_path(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    module_path = _validate_identifier(field_name, value)
    if module_path.startswith(".") or module_path.endswith(".") or ".." in module_path:
        raise GameLifecycleError("Runtime content module path must be absolute and normalized.")
    return module_path


def _unsupported_reason(row: RuntimeContentManifestRow) -> str:
    if row.unsupported_reason is None:
        raise GameLifecycleError("Unsupported runtime manifest row lacks unsupported_reason.")
    return row.unsupported_reason
