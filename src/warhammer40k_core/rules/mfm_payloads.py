from __future__ import annotations

from typing import NotRequired, TypedDict


class MfmIndexFactionPayload(TypedDict):
    faction_id: str
    raw_name: str
    name: str
    url_path: str


class MfmUnitCostRowPayload(TypedDict):
    raw_label: str
    label: str
    model_count: int | None
    model_name: str | None
    model_id: str | None
    model_component_counts: list[int]
    model_component_names: list[str]
    model_component_ids: list[str]
    additional_model_count: int | None
    additional_model_name: str | None
    additional_model_id: str | None
    points: int
    source_id: str


class MfmUnitCostBracketPayload(TypedDict):
    raw_label: str
    label: str
    unit_number_min: int
    unit_number_max: int | None
    rows: list[MfmUnitCostRowPayload]
    source_id: str


class MfmWargearCostPayload(TypedDict):
    raw_name: str
    name: str
    wargear_id: str
    points_per_item: int
    source_id: str


class MfmLeaderAllowancePayload(TypedDict):
    allowed_bodyguard_unit_ids: list[str]
    allowed_bodyguard_names: list[str]
    source_id: str


class MfmUnitRecordPayload(TypedDict):
    record_id: str
    unit_id: str
    raw_name: str
    name: str
    source_section_id: str | None
    source_section_name: str | None
    cost_brackets: list[MfmUnitCostBracketPayload]
    wargear_costs: list[MfmWargearCostPayload]
    leader_allowance: MfmLeaderAllowancePayload | None
    support_allowance: MfmLeaderAllowancePayload | None
    source_id: str


class MfmEnhancementRecordPayload(TypedDict):
    support_allowance: NotRequired[MfmLeaderAllowancePayload]
    enhancement_id: str
    raw_name: str
    name: str
    points: int
    is_upgrade: bool
    leader_allowance: MfmLeaderAllowancePayload | None
    source_id: str


class MfmDetachmentRecordPayload(TypedDict):
    force_disposition_ids: NotRequired[list[str]]
    detachment_id: str
    raw_name: str
    name: str
    force_disposition_id: str | None
    detachment_point_cost: int | None
    enhancements: list[MfmEnhancementRecordPayload]
    source_id: str


class MfmFactionRecordPayload(TypedDict):
    faction_id: str
    raw_name: str
    name: str
    url_path: str
    detachments: list[MfmDetachmentRecordPayload]
    units: list[MfmUnitRecordPayload]
    source_id: str


class MfmSourcePackagePayload(TypedDict):
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    source_url: str
    excluded_faction_ids: list[str]
    factions: list[MfmFactionRecordPayload]
    source_payload_checksum_sha256: str
