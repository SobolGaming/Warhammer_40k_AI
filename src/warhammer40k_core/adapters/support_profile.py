from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypedDict, cast

from warhammer40k_core.core.datasheet import CatalogAbilitySupport
from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentSupportStatus
from warhammer40k_core.engine.faction_content.runtime import runtime_content_manifest_for_ruleset
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import GameLifecycleError

SUPPORT_PROFILE_SCHEMA_VERSION = "support-profile-v1-phase18e"

type AdapterSupportStatus = Literal["unsupported", "playable", "full"]


class SupportStatusCountsPayload(TypedDict):
    unsupported: int
    playable: int
    full: int


class MusteringSupportRowPayload(TypedDict):
    row_id: str
    player_id: str
    army_id: str
    faction_id: str
    detachment_ids: list[str]
    datasheet_ids: list[str]
    status: AdapterSupportStatus
    legality_status: str
    violation_count: int


class DatasheetAbilitySupportRowPayload(TypedDict):
    row_id: str
    datasheet_id: str
    ability_id: str
    display_name: str
    source_id: str
    catalog_support: str
    status: AdapterSupportStatus
    timing_tags: list[str]
    parameter_tokens: list[str]


class RuntimeSupportRowPayload(TypedDict):
    row_id: str
    content_id: str
    family: str
    source_ids: list[str]
    owner_faction_id: str | None
    owner_detachment_id: str | None
    runtime_support: str
    status: AdapterSupportStatus
    support_reason: str | None
    unsupported_reason: str | None
    required_for_matched_play: bool


class SupportProfilePayload(TypedDict):
    schema_version: str
    game_id: str
    catalog_id: str
    source_package_id: str
    ruleset_descriptor_hash: str
    overall_status: AdapterSupportStatus
    eligible_for_headless_self_play_smoke: bool
    status_counts: SupportStatusCountsPayload
    mustering_support_rows: list[MusteringSupportRowPayload]
    datasheet_support_rows: list[DatasheetAbilitySupportRowPayload]
    detachment_faction_support_rows: list[RuntimeSupportRowPayload]


def build_support_profile(*, config: GameConfig) -> SupportProfilePayload:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Support profile requires a GameConfig.")
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor,
        config=config,
    )
    selected_content_ids = _selected_runtime_content_ids(config=config)
    runtime_rows = manifest.reachable_rows_for_content_ids(selected_content_ids)
    runtime_support_rows = [
        _runtime_support_row(row.to_summary_payload())
        for row in runtime_rows
        if row.family.value in {"faction", "detachment"}
    ]
    datasheet_rows = _datasheet_support_rows(config=config)
    mustering_rows = _mustering_support_rows(
        config=config,
        armies=armies,
        datasheet_rows=datasheet_rows,
        runtime_rows=runtime_support_rows,
    )
    all_statuses: list[AdapterSupportStatus] = [
        *(row["status"] for row in mustering_rows),
        *(row["status"] for row in datasheet_rows),
        *(row["status"] for row in runtime_support_rows),
    ]
    overall_status = _overall_status(tuple(all_statuses))
    payload: SupportProfilePayload = {
        "schema_version": SUPPORT_PROFILE_SCHEMA_VERSION,
        "game_id": config.game_id,
        "catalog_id": config.army_catalog.catalog_id,
        "source_package_id": config.army_catalog.source_package_id,
        "ruleset_descriptor_hash": config.ruleset_descriptor.descriptor_hash,
        "overall_status": overall_status,
        "eligible_for_headless_self_play_smoke": _eligible_for_headless_self_play_smoke(
            config=config,
            overall_status=overall_status,
            armies=armies,
        ),
        "status_counts": _status_counts(tuple(all_statuses)),
        "mustering_support_rows": mustering_rows,
        "datasheet_support_rows": datasheet_rows,
        "detachment_faction_support_rows": runtime_support_rows,
    }
    return cast(SupportProfilePayload, validate_json_value(payload))


def _selected_runtime_content_ids(*, config: GameConfig) -> tuple[str, ...]:
    selected: set[str] = set()
    for request in config.army_muster_requests:
        selected.add(request.detachment_selection.faction_id)
        selected.update(request.detachment_selection.detachment_ids)
        selected.update(selection.datasheet_id for selection in request.unit_selections)
    return tuple(sorted(selected))


def _datasheet_support_rows(*, config: GameConfig) -> list[DatasheetAbilitySupportRowPayload]:
    selected_datasheet_ids = {
        selection.datasheet_id
        for request in config.army_muster_requests
        for selection in request.unit_selections
    }
    rows: list[DatasheetAbilitySupportRowPayload] = []
    for datasheet in config.army_catalog.datasheets:
        if datasheet.datasheet_id not in selected_datasheet_ids:
            continue
        for ability in datasheet.abilities:
            rows.append(
                {
                    "row_id": f"datasheet:{datasheet.datasheet_id}:ability:{ability.ability_id}",
                    "datasheet_id": datasheet.datasheet_id,
                    "ability_id": ability.ability_id,
                    "display_name": ability.name,
                    "source_id": ability.source_id,
                    "catalog_support": ability.support.value,
                    "status": _catalog_ability_status(ability.support),
                    "timing_tags": list(ability.timing_tags),
                    "parameter_tokens": list(ability.parameter_tokens),
                }
            )
    return sorted(rows, key=lambda row: row["row_id"])


def _mustering_support_rows(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
    datasheet_rows: list[DatasheetAbilitySupportRowPayload],
    runtime_rows: list[RuntimeSupportRowPayload],
) -> list[MusteringSupportRowPayload]:
    army_by_id = {army.army_id: army for army in armies}
    datasheet_status_by_id = _most_severe_status_by_key(
        (row["datasheet_id"], row["status"]) for row in datasheet_rows
    )
    runtime_status_by_id = _most_severe_status_by_key(
        (row["content_id"], row["status"]) for row in runtime_rows
    )
    rows: list[MusteringSupportRowPayload] = []
    for request in config.army_muster_requests:
        army = army_by_id[request.army_id]
        datasheet_ids = tuple(selection.datasheet_id for selection in request.unit_selections)
        selected_statuses: list[AdapterSupportStatus] = [
            runtime_status_by_id.get(request.detachment_selection.faction_id, "playable"),
            *(
                runtime_status_by_id.get(detachment_id, "playable")
                for detachment_id in request.detachment_selection.detachment_ids
            ),
            *(
                datasheet_status_by_id.get(datasheet_id, "playable")
                for datasheet_id in datasheet_ids
            ),
        ]
        rows.append(
            {
                "row_id": f"mustering:{request.player_id}:{request.army_id}",
                "player_id": request.player_id,
                "army_id": request.army_id,
                "faction_id": request.detachment_selection.faction_id,
                "detachment_ids": list(request.detachment_selection.detachment_ids),
                "datasheet_ids": list(datasheet_ids),
                "status": _overall_status(tuple(selected_statuses)),
                "legality_status": _legality_status(army=army),
                "violation_count": len(army.roster_legality_report.violations),
            }
        )
    return sorted(rows, key=lambda row: row["row_id"])


def _legality_status(*, army: ArmyDefinition) -> str:
    if army.roster_legality_report.is_legal:
        return "legal"
    return "invalid"


def _runtime_support_row(row: dict[str, JsonValue]) -> RuntimeSupportRowPayload:
    runtime_support = _required_string(row, key="support_status")
    status = _runtime_support_status(runtime_support)
    family = _required_string(row, key="family")
    content_id = _required_string(row, key="content_id")
    return {
        "row_id": f"runtime:{family}:{content_id}",
        "content_id": content_id,
        "family": family,
        "source_ids": _required_string_list(row, key="source_ids"),
        "owner_faction_id": _optional_string(row, key="owner_faction_id"),
        "owner_detachment_id": _optional_string(row, key="owner_detachment_id"),
        "runtime_support": runtime_support,
        "status": status,
        "support_reason": _optional_string(row, key="support_reason"),
        "unsupported_reason": _optional_string(row, key="unsupported_reason"),
        "required_for_matched_play": _required_bool(row, key="required_for_matched_play"),
    }


def _catalog_ability_status(support: CatalogAbilitySupport) -> AdapterSupportStatus:
    if support is CatalogAbilitySupport.UNSUPPORTED:
        return "unsupported"
    if support in {
        CatalogAbilitySupport.GENERIC_RULE_IR,
        CatalogAbilitySupport.DESCRIPTOR_ONLY,
    }:
        return "playable"
    raise GameLifecycleError("Unknown CatalogAbilitySupport status.")


def _runtime_support_status(status: str) -> AdapterSupportStatus:
    try:
        runtime_status = RuntimeContentSupportStatus(status)
    except ValueError as exc:
        raise GameLifecycleError("Unknown RuntimeContentSupportStatus.") from exc
    if runtime_status is RuntimeContentSupportStatus.UNSUPPORTED:
        return "unsupported"
    if runtime_status is RuntimeContentSupportStatus.SUPPORTED:
        return "full"
    if runtime_status is RuntimeContentSupportStatus.SOURCE_ONLY:
        return "playable"
    raise GameLifecycleError("Unknown RuntimeContentSupportStatus.")


def _overall_status(statuses: tuple[AdapterSupportStatus, ...]) -> AdapterSupportStatus:
    if "unsupported" in statuses:
        return "unsupported"
    if "playable" in statuses or not statuses:
        return "playable"
    return "full"


def _status_counts(statuses: tuple[AdapterSupportStatus, ...]) -> SupportStatusCountsPayload:
    return {
        "unsupported": sum(1 for status in statuses if status == "unsupported"),
        "playable": sum(1 for status in statuses if status == "playable"),
        "full": sum(1 for status in statuses if status == "full"),
    }


def _eligible_for_headless_self_play_smoke(
    *,
    config: GameConfig,
    overall_status: AdapterSupportStatus,
    armies: tuple[ArmyDefinition, ...],
) -> bool:
    if overall_status == "unsupported":
        return False
    if config.mission_setup is None:
        return False
    if len(config.player_ids) != 2:
        return False
    if not config.allow_legacy_non_strict_rosters and any(
        not army.roster_legality_report.is_legal for army in armies
    ):
        return False
    selected_players = {request.player_id for request in config.army_muster_requests}
    if selected_players != set(config.player_ids):
        return False
    return all(request.unit_selections for request in config.army_muster_requests)


def _most_severe_status_by_key(
    rows: Iterable[tuple[str, AdapterSupportStatus]],
) -> dict[str, AdapterSupportStatus]:
    statuses: dict[str, list[AdapterSupportStatus]] = {}
    for key, status in rows:
        if status not in {"unsupported", "playable", "full"}:
            raise GameLifecycleError("Support profile status value is invalid.")
        statuses.setdefault(key, []).append(status)
    return {key: _overall_status(tuple(values)) for key, values in statuses.items()}


def _required_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Support profile payload key must be a string: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Support profile payload key must not be empty: {key}.")
    return stripped


def _optional_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Support profile payload key must be a string or null: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Support profile payload key must not be empty: {key}.")
    return stripped


def _required_string_list(payload: dict[str, JsonValue], *, key: str) -> list[str]:
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Support profile payload key must be a string list: {key}.")
    validated: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Support profile payload key must contain strings: {key}.")
        validated.append(item)
    return validated


def _required_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Support profile payload key must be a bool: {key}.")
    return value
