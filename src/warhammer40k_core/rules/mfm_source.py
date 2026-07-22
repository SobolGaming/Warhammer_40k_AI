from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.rules.mfm_html_tree import (
    HtmlNode as _HtmlNode,
)
from warhammer40k_core.rules.mfm_html_tree import (
    direct_node_children as _direct_node_children,
)
from warhammer40k_core.rules.mfm_html_tree import (
    first_direct_node_child as _first_direct_node_child,
)
from warhammer40k_core.rules.mfm_html_tree import (
    node_contains_template as _node_contains_template,
)
from warhammer40k_core.rules.mfm_html_tree import (
    node_has_class_token as _node_has_class_token,
)
from warhammer40k_core.rules.mfm_html_tree import (
    node_has_class_tokens as _node_has_class_tokens,
)
from warhammer40k_core.rules.mfm_html_tree import (
    node_text as _node_text,
)
from warhammer40k_core.rules.mfm_html_tree import (
    parse_html as _parse_html,
)
from warhammer40k_core.rules.mfm_html_tree import (
    walk as _walk,
)
from warhammer40k_core.rules.mfm_sections import (
    mfm_section_is_supported as _mfm_section_is_supported,
)
from warhammer40k_core.rules.mfm_validation import (
    MfmSourceError as MfmSourceError,
)
from warhammer40k_core.rules.mfm_validation import (
    normalize_wargear_cost_label as _normalize_wargear_cost_label,
)
from warhammer40k_core.rules.mfm_validation import (
    split_attachment_names as _split_attachment_names,
)
from warhammer40k_core.rules.mfm_validation import (
    strip_upgrade_suffix as _strip_upgrade_suffix,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_identifier as _validate_identifier,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_identifier_tuple as _validate_identifier_tuple,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_non_negative_int as _validate_non_negative_int,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_optional_identifier as _validate_optional_identifier,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_optional_non_negative_int as _validate_optional_non_negative_int,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_optional_positive_int as _validate_optional_positive_int,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_positive_int as _validate_positive_int,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_raw_label as _validate_raw_label,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_source_id as _validate_source_id,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_source_url as _validate_source_url,
)
from warhammer40k_core.rules.mfm_validation import (
    validate_url_path as _validate_url_path,
)
from warhammer40k_core.rules.text_normalization import normalize_source_label


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
    enhancement_id: str
    raw_name: str
    name: str
    points: int
    is_upgrade: bool
    leader_allowance: MfmLeaderAllowancePayload | None
    source_id: str


class MfmDetachmentRecordPayload(TypedDict):
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


_NON_IDENTIFIER_TEXT_RE = re.compile(r"[^a-z0-9]+")
_MODEL_COUNT_RE = re.compile(r"^(?P<count>[1-9][0-9]*)\s+models?$", re.IGNORECASE)
_MODEL_NAME_COUNT_RE = re.compile(r"^(?P<count>[1-9][0-9]*)\s+(?P<name>.+)$")
_ADDITIONAL_MODEL_RE = re.compile(r"^\+\s*(?P<count>[1-9][0-9]*)\s+(?P<name>.+)$")
_VALUE_CHANGE_PREFIX = r"(?:[▲▼]\s+\([+-][0-9][0-9,]*\)\s+)?"
_POINTS_RE = re.compile(
    rf"^{_VALUE_CHANGE_PREFIX}(?P<points>[0-9][0-9,]*)\s+pts$",
    re.IGNORECASE,
)
_DETACHMENT_POINTS_RE = re.compile(
    rf"^{_VALUE_CHANGE_PREFIX}(?P<points>[0-9][0-9,]*)\s*DP(?:\s+[▲▼]+)?$",
    re.IGNORECASE,
)
_MFM_VERSION_RE = re.compile(r"^v[0-9]+(?:\.[0-9]+)*$", re.IGNORECASE)
_ORDINAL_RE = re.compile(r"^(?P<number>[1-9][0-9]*)(?:st|nd|rd|th)$", re.IGNORECASE)
_COST_BRACKET_SINGLE_RE = re.compile(
    r"^YOUR (?P<ordinal>[1-9][0-9]*(?:ST|ND|RD|TH)) UNIT COSTS?$",
    re.IGNORECASE,
)
_COST_BRACKET_RANGE_RE = re.compile(
    r"^YOUR (?P<start>[1-9][0-9]*(?:ST|ND|RD|TH)) TO "
    r"(?P<end>[1-9][0-9]*(?:ST|ND|RD|TH)) UNITS COSTS?$",
    re.IGNORECASE,
)
_COST_BRACKET_OPEN_RE = re.compile(
    r"^YOUR (?P<start>[1-9][0-9]*(?:ST|ND|RD|TH)) \+ UNIT COSTS?$",
    re.IGNORECASE,
)
_CARD_CLASS_TOKENS = frozenset(("flex", "flex-col", "space-y-1", "m-1"))
_UNIT_TITLE_CLASS_TOKENS = frozenset(("font-bold", "text-white"))
_DETACHMENT_TITLE_CLASS_TOKENS = frozenset(("flex-row", "justify-between", "text-white"))
_ATTACHMENT_SECTION_HEADERS = frozenset(("LEADER", "SUPPORT"))


@dataclass(frozen=True, slots=True)
class MfmIndexFaction:
    faction_id: str
    raw_name: str
    url_path: str

    def __post_init__(self) -> None:
        name = normalize_source_label(self.raw_name)
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        object.__setattr__(self, "raw_name", _validate_raw_label("raw_name", self.raw_name))
        if self.faction_id != source_label_slug(name):
            raise MfmSourceError("MfmIndexFaction faction_id must match raw_name.")
        object.__setattr__(self, "url_path", _validate_url_path(self.url_path))

    @property
    def name(self) -> str:
        return normalize_source_label(self.raw_name)

    def to_payload(self) -> MfmIndexFactionPayload:
        return {
            "faction_id": self.faction_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "url_path": self.url_path,
        }

    @classmethod
    def from_payload(cls, payload: MfmIndexFactionPayload) -> Self:
        return cls(
            faction_id=payload["faction_id"],
            raw_name=payload["raw_name"],
            url_path=payload["url_path"],
        )


@dataclass(frozen=True, slots=True)
class MfmUnitCostRow:
    raw_label: str
    points: int
    source_id: str
    model_count: int | None = field(init=False)
    model_name: str | None = field(init=False)
    model_id: str | None = field(init=False)
    model_component_counts: tuple[int, ...] = field(init=False)
    model_component_names: tuple[str, ...] = field(init=False)
    model_component_ids: tuple[str, ...] = field(init=False)
    additional_model_count: int | None = field(init=False)
    additional_model_name: str | None = field(init=False)
    additional_model_id: str | None = field(init=False)

    def __post_init__(self) -> None:
        label = normalize_source_label(self.raw_label)
        (
            model_count,
            model_name,
            model_component_counts,
            model_component_names,
            additional_model_count,
            additional_model_name,
        ) = unit_cost_row_label_details(label)
        object.__setattr__(self, "raw_label", _validate_raw_label("raw_label", self.raw_label))
        object.__setattr__(self, "model_count", model_count)
        object.__setattr__(self, "model_name", model_name)
        object.__setattr__(
            self,
            "model_id",
            None if model_name is None else source_label_slug(model_name),
        )
        object.__setattr__(self, "model_component_counts", model_component_counts)
        object.__setattr__(self, "model_component_names", model_component_names)
        object.__setattr__(
            self,
            "model_component_ids",
            tuple(source_label_slug(name) for name in model_component_names),
        )
        object.__setattr__(self, "additional_model_count", additional_model_count)
        object.__setattr__(self, "additional_model_name", additional_model_name)
        object.__setattr__(
            self,
            "additional_model_id",
            None if additional_model_name is None else source_label_slug(additional_model_name),
        )
        object.__setattr__(self, "points", _validate_non_negative_int("points", self.points))
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    @property
    def label(self) -> str:
        return normalize_source_label(self.raw_label)

    def to_payload(self) -> MfmUnitCostRowPayload:
        return {
            "raw_label": self.raw_label,
            "label": self.label,
            "model_count": self.model_count,
            "model_name": self.model_name,
            "model_id": self.model_id,
            "model_component_counts": list(self.model_component_counts),
            "model_component_names": list(self.model_component_names),
            "model_component_ids": list(self.model_component_ids),
            "additional_model_count": self.additional_model_count,
            "additional_model_name": self.additional_model_name,
            "additional_model_id": self.additional_model_id,
            "points": self.points,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmUnitCostRowPayload) -> Self:
        row = cls(
            raw_label=payload["raw_label"],
            points=payload["points"],
            source_id=payload["source_id"],
        )
        if (
            row.label != payload["label"]
            or row.model_count != payload["model_count"]
            or row.model_name != payload["model_name"]
            or row.model_id != payload["model_id"]
            or list(row.model_component_counts) != payload["model_component_counts"]
            or list(row.model_component_names) != payload["model_component_names"]
            or list(row.model_component_ids) != payload["model_component_ids"]
            or row.additional_model_count != payload["additional_model_count"]
            or row.additional_model_name != payload["additional_model_name"]
            or row.additional_model_id != payload["additional_model_id"]
        ):
            raise MfmSourceError("MfmUnitCostRow payload normalized fields are stale.")
        return row


@dataclass(frozen=True, slots=True)
class MfmUnitCostBracket:
    raw_label: str
    unit_number_min: int
    unit_number_max: int | None
    rows: tuple[MfmUnitCostRow, ...]
    source_id: str

    def __post_init__(self) -> None:
        label = normalize_source_label(self.raw_label)
        expected_min, expected_max = unit_cost_bracket_bounds(label)
        object.__setattr__(self, "raw_label", _validate_raw_label("raw_label", self.raw_label))
        object.__setattr__(
            self,
            "unit_number_min",
            _validate_positive_int("unit_number_min", self.unit_number_min),
        )
        object.__setattr__(
            self,
            "unit_number_max",
            _validate_optional_positive_int("unit_number_max", self.unit_number_max),
        )
        if (self.unit_number_min, self.unit_number_max) != (expected_min, expected_max):
            raise MfmSourceError("MfmUnitCostBracket bounds must match raw_label.")
        if self.unit_number_max is not None and self.unit_number_max < self.unit_number_min:
            raise MfmSourceError("MfmUnitCostBracket unit_number_max must not be lower than min.")
        rows = _validate_cost_rows(self.rows)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    @property
    def label(self) -> str:
        return normalize_source_label(self.raw_label)

    def applies_to_unit_number(self, unit_number: int) -> bool:
        selected = _validate_positive_int("unit_number", unit_number)
        if selected < self.unit_number_min:
            return False
        if self.unit_number_max is None:
            return True
        return selected <= self.unit_number_max

    def points_for_model_count(self, model_count: int) -> int:
        selected = _validate_positive_int("model_count", model_count)
        for row in self.rows:
            if row.model_count == selected:
                return row.points
        raise MfmSourceError("MfmUnitCostBracket has no row for model_count.")

    def to_payload(self) -> MfmUnitCostBracketPayload:
        return {
            "raw_label": self.raw_label,
            "label": self.label,
            "unit_number_min": self.unit_number_min,
            "unit_number_max": self.unit_number_max,
            "rows": [row.to_payload() for row in self.rows],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmUnitCostBracketPayload) -> Self:
        return cls(
            raw_label=payload["raw_label"],
            unit_number_min=payload["unit_number_min"],
            unit_number_max=payload["unit_number_max"],
            rows=tuple(MfmUnitCostRow.from_payload(row) for row in payload["rows"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MfmWargearCost:
    raw_name: str
    points_per_item: int
    source_id: str

    def __post_init__(self) -> None:
        name = _normalize_wargear_cost_label(self.raw_name)
        object.__setattr__(self, "raw_name", _validate_raw_label("raw_name", self.raw_name))
        object.__setattr__(
            self,
            "points_per_item",
            _validate_non_negative_int("points_per_item", self.points_per_item),
        )
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))
        if self.wargear_id != source_label_slug(name):
            raise MfmSourceError("MfmWargearCost wargear_id drift.")

    @property
    def name(self) -> str:
        return _normalize_wargear_cost_label(self.raw_name)

    @property
    def wargear_id(self) -> str:
        return source_label_slug(self.name)

    def to_payload(self) -> MfmWargearCostPayload:
        return {
            "raw_name": self.raw_name,
            "name": self.name,
            "wargear_id": self.wargear_id,
            "points_per_item": self.points_per_item,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmWargearCostPayload) -> Self:
        cost = cls(
            raw_name=payload["raw_name"],
            points_per_item=payload["points_per_item"],
            source_id=payload["source_id"],
        )
        if cost.name != payload["name"] or cost.wargear_id != payload["wargear_id"]:
            raise MfmSourceError("MfmWargearCost payload normalized fields are stale.")
        return cost


@dataclass(frozen=True, slots=True)
class MfmLeaderAllowance:
    allowed_bodyguard_unit_ids: tuple[str, ...]
    allowed_bodyguard_names: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        names = _validate_name_tuple("allowed_bodyguard_names", self.allowed_bodyguard_names)
        expected_ids = tuple(source_label_slug(name) for name in names)
        ids = _validate_identifier_tuple(
            "allowed_bodyguard_unit_ids", self.allowed_bodyguard_unit_ids
        )
        if ids != expected_ids:
            raise MfmSourceError("MfmLeaderAllowance IDs must match normalized names.")
        object.__setattr__(self, "allowed_bodyguard_unit_ids", ids)
        object.__setattr__(self, "allowed_bodyguard_names", names)
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    def to_payload(self) -> MfmLeaderAllowancePayload:
        return {
            "allowed_bodyguard_unit_ids": list(self.allowed_bodyguard_unit_ids),
            "allowed_bodyguard_names": list(self.allowed_bodyguard_names),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmLeaderAllowancePayload) -> Self:
        return cls(
            allowed_bodyguard_unit_ids=tuple(payload["allowed_bodyguard_unit_ids"]),
            allowed_bodyguard_names=tuple(payload["allowed_bodyguard_names"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MfmUnitRecord:
    record_id: str
    unit_id: str
    raw_name: str
    source_section_id: str | None
    source_section_name: str | None
    cost_brackets: tuple[MfmUnitCostBracket, ...]
    wargear_costs: tuple[MfmWargearCost, ...] = ()
    leader_allowance: MfmLeaderAllowance | None = None
    support_allowance: MfmLeaderAllowance | None = None
    source_id: str = ""

    def __post_init__(self) -> None:
        name = normalize_source_label(self.raw_name)
        object.__setattr__(self, "record_id", _validate_identifier("record_id", self.record_id))
        object.__setattr__(self, "unit_id", _validate_identifier("unit_id", self.unit_id))
        if self.unit_id != source_label_slug(name):
            raise MfmSourceError("MfmUnitRecord unit_id must match raw_name.")
        object.__setattr__(self, "raw_name", _validate_raw_label("raw_name", self.raw_name))
        section_name = (
            None
            if self.source_section_name is None
            else _validate_raw_label("source_section_name", self.source_section_name)
        )
        section_id = _validate_optional_identifier("source_section_id", self.source_section_id)
        if section_name is None and section_id is not None:
            raise MfmSourceError("MfmUnitRecord source_section_id requires source_section_name.")
        if section_name is not None and section_id != source_label_slug(section_name):
            raise MfmSourceError("MfmUnitRecord source_section_id must match section name.")
        object.__setattr__(self, "source_section_id", section_id)
        object.__setattr__(self, "source_section_name", section_name)
        object.__setattr__(self, "cost_brackets", _validate_cost_brackets(self.cost_brackets))
        object.__setattr__(self, "wargear_costs", _validate_wargear_costs(self.wargear_costs))
        if (
            self.leader_allowance is not None
            and type(self.leader_allowance) is not MfmLeaderAllowance
        ):
            raise MfmSourceError("MfmUnitRecord leader_allowance must be MfmLeaderAllowance.")
        if (
            self.support_allowance is not None
            and type(self.support_allowance) is not MfmLeaderAllowance
        ):
            raise MfmSourceError("MfmUnitRecord support_allowance must be MfmLeaderAllowance.")
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    @property
    def name(self) -> str:
        return normalize_source_label(self.raw_name)

    def cost_bracket_for_unit_number(self, unit_number: int) -> MfmUnitCostBracket:
        selected = _validate_positive_int("unit_number", unit_number)
        for bracket in self.cost_brackets:
            if bracket.applies_to_unit_number(selected):
                return bracket
        raise MfmSourceError("MfmUnitRecord has no cost bracket for unit_number.")

    def to_payload(self) -> MfmUnitRecordPayload:
        return {
            "record_id": self.record_id,
            "unit_id": self.unit_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "source_section_id": self.source_section_id,
            "source_section_name": self.source_section_name,
            "cost_brackets": [bracket.to_payload() for bracket in self.cost_brackets],
            "wargear_costs": [cost.to_payload() for cost in self.wargear_costs],
            "leader_allowance": (
                None if self.leader_allowance is None else self.leader_allowance.to_payload()
            ),
            "support_allowance": (
                None if self.support_allowance is None else self.support_allowance.to_payload()
            ),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmUnitRecordPayload) -> Self:
        record = cls(
            record_id=payload["record_id"],
            unit_id=payload["unit_id"],
            raw_name=payload["raw_name"],
            source_section_id=payload["source_section_id"],
            source_section_name=payload["source_section_name"],
            cost_brackets=tuple(
                MfmUnitCostBracket.from_payload(bracket) for bracket in payload["cost_brackets"]
            ),
            wargear_costs=tuple(
                MfmWargearCost.from_payload(cost) for cost in payload["wargear_costs"]
            ),
            leader_allowance=(
                None
                if payload["leader_allowance"] is None
                else MfmLeaderAllowance.from_payload(payload["leader_allowance"])
            ),
            support_allowance=(
                None
                if payload["support_allowance"] is None
                else MfmLeaderAllowance.from_payload(payload["support_allowance"])
            ),
            source_id=payload["source_id"],
        )
        if record.name != payload["name"]:
            raise MfmSourceError("MfmUnitRecord payload name is stale.")
        return record


@dataclass(frozen=True, slots=True)
class MfmEnhancementRecord:
    enhancement_id: str
    raw_name: str
    points: int
    is_upgrade: bool
    leader_allowance: MfmLeaderAllowance | None = None
    source_id: str = ""

    def __post_init__(self) -> None:
        name = normalize_source_label(self.raw_name)
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        if self.enhancement_id != source_label_slug(_strip_upgrade_suffix(name)):
            raise MfmSourceError("MfmEnhancementRecord enhancement_id must match raw_name.")
        object.__setattr__(self, "raw_name", _validate_raw_label("raw_name", self.raw_name))
        object.__setattr__(self, "points", _validate_non_negative_int("points", self.points))
        if type(self.is_upgrade) is not bool:
            raise MfmSourceError("MfmEnhancementRecord is_upgrade must be a boolean.")
        if (
            self.leader_allowance is not None
            and type(self.leader_allowance) is not MfmLeaderAllowance
        ):
            raise MfmSourceError(
                "MfmEnhancementRecord leader_allowance must be MfmLeaderAllowance."
            )
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    @property
    def name(self) -> str:
        return normalize_source_label(self.raw_name)

    def to_payload(self) -> MfmEnhancementRecordPayload:
        return {
            "enhancement_id": self.enhancement_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "points": self.points,
            "is_upgrade": self.is_upgrade,
            "leader_allowance": (
                None if self.leader_allowance is None else self.leader_allowance.to_payload()
            ),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmEnhancementRecordPayload) -> Self:
        record = cls(
            enhancement_id=payload["enhancement_id"],
            raw_name=payload["raw_name"],
            points=payload["points"],
            is_upgrade=payload["is_upgrade"],
            leader_allowance=(
                None
                if payload["leader_allowance"] is None
                else MfmLeaderAllowance.from_payload(payload["leader_allowance"])
            ),
            source_id=payload["source_id"],
        )
        if record.name != payload["name"]:
            raise MfmSourceError("MfmEnhancementRecord payload name is stale.")
        return record


@dataclass(frozen=True, slots=True)
class MfmDetachmentRecord:
    detachment_id: str
    raw_name: str
    force_disposition_id: str | None
    detachment_point_cost: int | None
    enhancements: tuple[MfmEnhancementRecord, ...]
    source_id: str

    def __post_init__(self) -> None:
        name = normalize_source_label(self.raw_name)
        object.__setattr__(
            self,
            "detachment_id",
            _validate_identifier("detachment_id", self.detachment_id),
        )
        if self.detachment_id != source_label_slug(name):
            raise MfmSourceError("MfmDetachmentRecord detachment_id must match raw_name.")
        object.__setattr__(self, "raw_name", _validate_raw_label("raw_name", self.raw_name))
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_optional_identifier("force_disposition_id", self.force_disposition_id),
        )
        object.__setattr__(
            self,
            "detachment_point_cost",
            _validate_optional_non_negative_int(
                "detachment_point_cost",
                self.detachment_point_cost,
            ),
        )
        object.__setattr__(self, "enhancements", _validate_enhancements(self.enhancements))
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    @property
    def name(self) -> str:
        return normalize_source_label(self.raw_name)

    def to_payload(self) -> MfmDetachmentRecordPayload:
        return {
            "detachment_id": self.detachment_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "force_disposition_id": self.force_disposition_id,
            "detachment_point_cost": self.detachment_point_cost,
            "enhancements": [enhancement.to_payload() for enhancement in self.enhancements],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmDetachmentRecordPayload) -> Self:
        record = cls(
            detachment_id=payload["detachment_id"],
            raw_name=payload["raw_name"],
            force_disposition_id=payload["force_disposition_id"],
            detachment_point_cost=payload["detachment_point_cost"],
            enhancements=tuple(
                MfmEnhancementRecord.from_payload(enhancement)
                for enhancement in payload["enhancements"]
            ),
            source_id=payload["source_id"],
        )
        if record.name != payload["name"]:
            raise MfmSourceError("MfmDetachmentRecord payload name is stale.")
        return record


@dataclass(frozen=True, slots=True)
class MfmFactionRecord:
    faction_id: str
    raw_name: str
    url_path: str
    detachments: tuple[MfmDetachmentRecord, ...]
    units: tuple[MfmUnitRecord, ...]
    source_id: str

    def __post_init__(self) -> None:
        name = normalize_source_label(self.raw_name)
        object.__setattr__(self, "faction_id", _validate_identifier("faction_id", self.faction_id))
        if self.faction_id != source_label_slug(name):
            raise MfmSourceError("MfmFactionRecord faction_id must match raw_name.")
        object.__setattr__(self, "raw_name", _validate_raw_label("raw_name", self.raw_name))
        object.__setattr__(self, "url_path", _validate_url_path(self.url_path))
        object.__setattr__(self, "detachments", _validate_detachments(self.detachments))
        object.__setattr__(self, "units", _validate_units(self.units))
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))

    @property
    def name(self) -> str:
        return normalize_source_label(self.raw_name)

    def unit_by_id(self, unit_id: str) -> MfmUnitRecord:
        requested_id = _validate_identifier("unit_id", unit_id)
        for unit in self.units:
            if unit.record_id == requested_id:
                return unit
        matches = tuple(unit for unit in self.units if unit.unit_id == requested_id)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise MfmSourceError("MfmFactionRecord unit_id is ambiguous; use record_id.")
        raise MfmSourceError("MfmFactionRecord unit_id was not found.")

    def unit_by_record_id(self, record_id: str) -> MfmUnitRecord:
        requested_id = _validate_identifier("record_id", record_id)
        for unit in self.units:
            if unit.record_id == requested_id:
                return unit
        raise MfmSourceError("MfmFactionRecord record_id was not found.")

    def unit_records_by_unit_id(self, unit_id: str) -> tuple[MfmUnitRecord, ...]:
        requested_id = _validate_identifier("unit_id", unit_id)
        return tuple(unit for unit in self.units if unit.unit_id == requested_id)

    def enhancement_by_id(self, enhancement_id: str) -> MfmEnhancementRecord:
        requested_id = _validate_identifier("enhancement_id", enhancement_id)
        for detachment in self.detachments:
            for enhancement in detachment.enhancements:
                if enhancement.enhancement_id == requested_id:
                    return enhancement
        raise MfmSourceError("MfmFactionRecord enhancement_id was not found.")

    def to_payload(self) -> MfmFactionRecordPayload:
        return {
            "faction_id": self.faction_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "url_path": self.url_path,
            "detachments": [detachment.to_payload() for detachment in self.detachments],
            "units": [unit.to_payload() for unit in self.units],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MfmFactionRecordPayload) -> Self:
        record = cls(
            faction_id=payload["faction_id"],
            raw_name=payload["raw_name"],
            url_path=payload["url_path"],
            detachments=tuple(
                MfmDetachmentRecord.from_payload(detachment)
                for detachment in payload["detachments"]
            ),
            units=tuple(MfmUnitRecord.from_payload(unit) for unit in payload["units"]),
            source_id=payload["source_id"],
        )
        if record.name != payload["name"]:
            raise MfmSourceError("MfmFactionRecord payload name is stale.")
        return record


@dataclass(frozen=True, slots=True)
class MfmSourcePackage:
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    source_url: str
    excluded_faction_ids: tuple[str, ...]
    factions: tuple[MfmFactionRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("source_package_id", self.source_package_id),
        )
        object.__setattr__(
            self,
            "source_title",
            _validate_raw_label("source_title", self.source_title),
        )
        object.__setattr__(
            self,
            "source_version",
            _validate_raw_label("source_version", self.source_version),
        )
        object.__setattr__(
            self,
            "source_date",
            _validate_raw_label("source_date", self.source_date),
        )
        object.__setattr__(
            self,
            "source_url",
            _validate_source_url(self.source_url),
        )
        object.__setattr__(
            self,
            "excluded_faction_ids",
            _validate_identifier_tuple("excluded_faction_ids", self.excluded_faction_ids),
        )
        object.__setattr__(self, "factions", _validate_factions(self.factions))

    def faction_by_id(self, faction_id: str) -> MfmFactionRecord:
        requested_id = _validate_identifier("faction_id", faction_id)
        for faction in self.factions:
            if faction.faction_id == requested_id:
                return faction
        raise MfmSourceError("MfmSourcePackage faction_id was not found.")

    def source_payload_checksum_sha256(self) -> str:
        encoded = json.dumps(
            self._payload_for_hash(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_payload(self) -> MfmSourcePackagePayload:
        payload = self._payload_for_hash()
        payload["source_payload_checksum_sha256"] = self.source_payload_checksum_sha256()
        return payload

    @classmethod
    def from_payload(cls, payload: MfmSourcePackagePayload) -> Self:
        package = cls(
            source_package_id=payload["source_package_id"],
            source_title=payload["source_title"],
            source_version=payload["source_version"],
            source_date=payload["source_date"],
            source_url=payload["source_url"],
            excluded_faction_ids=tuple(payload["excluded_faction_ids"]),
            factions=tuple(
                MfmFactionRecord.from_payload(faction) for faction in payload["factions"]
            ),
        )
        if package.source_payload_checksum_sha256() != payload["source_payload_checksum_sha256"]:
            raise MfmSourceError("MfmSourcePackage payload checksum is stale.")
        return package

    def _payload_for_hash(self) -> MfmSourcePackagePayload:
        return {
            "source_package_id": self.source_package_id,
            "source_title": self.source_title,
            "source_version": self.source_version,
            "source_date": self.source_date,
            "source_url": self.source_url,
            "excluded_faction_ids": list(self.excluded_faction_ids),
            "factions": [faction.to_payload() for faction in self.factions],
            "source_payload_checksum_sha256": "",
        }


def parse_mfm_index_html(html: str) -> tuple[MfmIndexFaction, ...]:
    root = _parse_html(html)
    rows: list[MfmIndexFaction] = []
    seen: set[str] = set()
    for anchor in _walk(root, tag="a"):
        href = anchor.attrs.get("href")
        if href is None or not href.startswith("/en/"):
            continue
        raw_name = _node_text(anchor)
        faction_id = source_label_slug(raw_name)
        if faction_id in seen:
            continue
        seen.add(faction_id)
        rows.append(
            MfmIndexFaction(
                faction_id=faction_id,
                raw_name=raw_name,
                url_path=href,
            )
        )
    if not rows:
        raise MfmSourceError("MFM index did not contain faction links.")
    return tuple(sorted(rows, key=lambda row: row.faction_id))


def parse_mfm_version_html(html: str) -> str:
    root = _parse_html(html)
    versions = {
        text
        for heading in _walk(root, tag="h2")
        if (text := _node_text(heading)) and _MFM_VERSION_RE.fullmatch(text) is not None
    }
    if len(versions) != 1:
        raise MfmSourceError("MFM page did not contain exactly one version label.")
    return versions.pop()


def parse_mfm_faction_html(
    *,
    html: str,
    faction: MfmIndexFaction,
    source_package_id: str,
) -> MfmFactionRecord:
    requested_source_package_id = _validate_identifier("source_package_id", source_package_id)
    root = _parse_html(html)
    template_nodes = _template_nodes(root)
    template_texts = _template_texts(template_nodes)
    units = _parse_unit_cards(
        root=root,
        template_nodes=template_nodes,
        template_texts=template_texts,
        faction_id=faction.faction_id,
        source_package_id=requested_source_package_id,
    )
    detachments = _parse_detachment_cards(
        root=root,
        faction_id=faction.faction_id,
        source_package_id=requested_source_package_id,
    )
    if not units:
        raise MfmSourceError("MFM faction page did not contain unit cards.")
    return MfmFactionRecord(
        faction_id=faction.faction_id,
        raw_name=faction.raw_name,
        url_path=faction.url_path,
        detachments=detachments,
        units=units,
        source_id=f"{requested_source_package_id}:faction:{faction.faction_id}",
    )


def source_label_slug(label: str) -> str:
    normalized = normalize_source_label(label).lower()
    normalized = normalized.replace("'", "")
    normalized = _NON_IDENTIFIER_TEXT_RE.sub("-", normalized).strip("-")
    return _validate_identifier("source label slug", normalized)


def unit_cost_bracket_bounds(label: str) -> tuple[int, int | None]:
    normalized = normalize_source_label(label)
    if normalized.upper() == "YOUR UNIT COSTS":
        return 1, None
    single_match = _COST_BRACKET_SINGLE_RE.fullmatch(normalized)
    if single_match is not None:
        ordinal = _ordinal_to_int(single_match.group("ordinal"))
        return ordinal, ordinal
    range_match = _COST_BRACKET_RANGE_RE.fullmatch(normalized)
    if range_match is not None:
        start = _ordinal_to_int(range_match.group("start"))
        end = _ordinal_to_int(range_match.group("end"))
        if end < start:
            raise MfmSourceError("MFM unit cost bracket range is descending.")
        return start, end
    open_match = _COST_BRACKET_OPEN_RE.fullmatch(normalized)
    if open_match is not None:
        return _ordinal_to_int(open_match.group("start")), None
    raise MfmSourceError("MFM unit cost bracket label is unsupported.")


def parse_points_label(label: str) -> int:
    normalized = normalize_source_label(label)
    match = _POINTS_RE.fullmatch(normalized)
    if match is None:
        raise MfmSourceError("MFM points label is invalid.")
    return int(match.group("points").replace(",", ""))


def parse_model_count_label(label: str) -> int:
    normalized = normalize_source_label(label)
    match = _MODEL_COUNT_RE.fullmatch(normalized)
    if match is None:
        raise MfmSourceError("MFM model count label is invalid.")
    return int(match.group("count"))


def unit_cost_row_label_details(
    label: str,
) -> tuple[int | None, str | None, tuple[int, ...], tuple[str, ...], int | None, str | None]:
    normalized = normalize_source_label(label)
    model_count_match = _MODEL_COUNT_RE.fullmatch(normalized)
    if model_count_match is not None:
        return int(model_count_match.group("count")), None, (), (), None, None
    additional_model_match = _ADDITIONAL_MODEL_RE.fullmatch(normalized)
    if additional_model_match is not None:
        return (
            None,
            None,
            (),
            (),
            int(additional_model_match.group("count")),
            normalize_source_label(additional_model_match.group("name")),
        )
    component_counts, component_names = _model_components_from_label(normalized)
    if component_counts:
        return (
            sum(component_counts),
            normalize_source_label(", ".join(component_names)),
            component_counts,
            component_names,
            None,
            None,
        )
    raise MfmSourceError("MFM unit cost row label is invalid.")


def _model_components_from_label(label: str) -> tuple[tuple[int, ...], tuple[str, ...]]:
    counts: list[int] = []
    names: list[str] = []
    for raw_part in normalize_source_label(label).split(","):
        part = normalize_source_label(raw_part)
        if _MODEL_COUNT_RE.fullmatch(part) is not None:
            return (), ()
        match = _MODEL_NAME_COUNT_RE.fullmatch(part)
        if match is None:
            return (), ()
        counts.append(int(match.group("count")))
        names.append(normalize_source_label(match.group("name")))
    return tuple(counts), tuple(names)


def _parse_unit_cards(
    *,
    root: _HtmlNode,
    template_nodes: dict[str, _HtmlNode],
    template_texts: dict[str, str],
    faction_id: str,
    source_package_id: str,
) -> tuple[MfmUnitRecord, ...]:
    records: dict[str, MfmUnitRecord] = {}
    for card, section_id, section_name in _card_nodes_with_sections(root):
        title_node = _unit_title_node(card, template_nodes=template_nodes)
        if title_node is None:
            continue
        unit_name = _node_text(title_node)
        unit_id = source_label_slug(unit_name)
        record_id = unit_id if section_id is None else f"{section_id}-{unit_id}"
        source_prefix = f"{source_package_id}:faction:{faction_id}:unit:{record_id}"
        cost_brackets: list[MfmUnitCostBracket] = []
        wargear_costs: list[MfmWargearCost] = []
        leader_allowance: MfmLeaderAllowance | None = None
        support_allowance: MfmLeaderAllowance | None = None
        for section in _direct_node_children(card):
            if section is title_node or not _node_has_class_token(section, "space-y-1"):
                continue
            header = _first_direct_node_child(section)
            if header is None:
                continue
            header_text = _node_text(header)
            if header_text.upper().startswith("YOUR ") and "COST" in header_text.upper():
                cost_brackets.append(
                    _unit_cost_bracket_from_section(
                        section=section,
                        label=header_text,
                        template_nodes=template_nodes,
                        template_texts=template_texts,
                        source_prefix=source_prefix,
                    )
                )
            elif header_text.upper() == "WARGEAR OPTIONS":
                wargear_costs.extend(
                    _wargear_costs_from_section(
                        section=section,
                        template_nodes=template_nodes,
                        template_texts=template_texts,
                        source_prefix=source_prefix,
                    )
                )
            elif header_text.upper() in _ATTACHMENT_SECTION_HEADERS:
                attachment_role = header_text.lower()
                parsed_allowance = _attachment_allowance_from_section(
                    section=section,
                    template_texts=template_texts,
                    attachment_role=attachment_role,
                    source_id=f"{source_prefix}:{attachment_role}",
                )
                if parsed_allowance is not None and attachment_role == "leader":
                    leader_allowance = parsed_allowance
                elif parsed_allowance is not None:
                    support_allowance = parsed_allowance
        if not cost_brackets:
            if _node_contains_template(card):
                continue
            raise MfmSourceError(f"MFM unit card {source_prefix} is missing cost brackets.")
        record = MfmUnitRecord(
            record_id=record_id,
            unit_id=unit_id,
            raw_name=unit_name,
            source_section_id=section_id,
            source_section_name=section_name,
            cost_brackets=tuple(cost_brackets),
            wargear_costs=tuple(wargear_costs),
            leader_allowance=leader_allowance,
            support_allowance=support_allowance,
            source_id=source_prefix,
        )
        previous = records.get(record_id)
        if previous is None:
            records[record_id] = record
        else:
            records[record_id] = _merge_duplicate_unit_record(previous=previous, current=record)
    return tuple(records[record_id] for record_id in sorted(records))


def _parse_detachment_cards(
    *,
    root: _HtmlNode,
    faction_id: str,
    source_package_id: str,
) -> tuple[MfmDetachmentRecord, ...]:
    records: dict[str, MfmDetachmentRecord] = {}
    for card in _card_nodes(root):
        title_node = _detachment_title_node(card)
        if title_node is None:
            continue
        title_spans = [_node_text(span) for span in _walk(title_node, tag="span")]
        if len(title_spans) < 2:
            raise MfmSourceError("MFM detachment title is missing name or DP value.")
        detachment_name = title_spans[0]
        detachment_id = source_label_slug(detachment_name)
        source_prefix = f"{source_package_id}:faction:{faction_id}:detachment:{detachment_id}"
        force_disposition_id: str | None = None
        detachment_point_cost = _parse_detachment_points(title_spans[1])
        enhancements: list[MfmEnhancementRecord] = []
        for section in _direct_node_children(card):
            if section is title_node or section.tag != "div":
                continue
            section_text = _node_text(section)
            if not section_text:
                continue
            if section_text.upper() == "ENHANCEMENTS":
                continue
            if _node_has_class_token(section, "space-y-1"):
                header = _first_direct_node_child(section)
                if header is not None and _node_text(header).upper() == "ENHANCEMENTS":
                    enhancements.extend(
                        _enhancements_from_section(section=section, source_prefix=source_prefix)
                    )
                continue
            if section_text.upper().startswith("UNIQUE:"):
                continue
            if force_disposition_id is None:
                force_disposition_id = source_label_slug(section_text)
        record = MfmDetachmentRecord(
            detachment_id=detachment_id,
            raw_name=detachment_name,
            force_disposition_id=force_disposition_id,
            detachment_point_cost=detachment_point_cost,
            enhancements=tuple(enhancements),
            source_id=source_prefix,
        )
        previous = records.get(detachment_id)
        if previous is not None and previous.to_payload() != record.to_payload():
            raise MfmSourceError(
                "MFM faction page contains conflicting duplicate detachment cards."
            )
        records[detachment_id] = record
    return tuple(records[detachment_id] for detachment_id in sorted(records))


def _unit_cost_bracket_from_section(
    *,
    section: _HtmlNode,
    label: str,
    template_nodes: dict[str, _HtmlNode],
    template_texts: dict[str, str],
    source_prefix: str,
) -> MfmUnitCostBracket:
    unit_min, unit_max = unit_cost_bracket_bounds(label)
    label_slug = source_label_slug(label)
    rows: list[MfmUnitCostRow] = []
    for index, li in enumerate(_section_li_nodes(section, template_nodes=template_nodes), start=1):
        row_label = ""
        try:
            row_label, points = _row_label_and_points(li=li, template_texts=template_texts)
            unit_cost_row_label_details(row_label)
        except MfmSourceError as exc:
            raise MfmSourceError(
                f"MFM unit cost section {source_prefix}:{label_slug} has invalid row "
                f"label={row_label!r}."
            ) from exc
        rows.append(
            MfmUnitCostRow(
                raw_label=row_label,
                points=points,
                source_id=f"{source_prefix}:cost:{label_slug}:{index}",
            )
        )
    if not rows:
        raise MfmSourceError(f"MFM unit cost section {source_prefix}:{label_slug} has no rows.")
    return MfmUnitCostBracket(
        raw_label=label,
        unit_number_min=unit_min,
        unit_number_max=unit_max,
        rows=tuple(rows),
        source_id=f"{source_prefix}:cost:{label_slug}",
    )


def _wargear_costs_from_section(
    *,
    section: _HtmlNode,
    template_nodes: dict[str, _HtmlNode],
    template_texts: dict[str, str],
    source_prefix: str,
) -> tuple[MfmWargearCost, ...]:
    costs: list[MfmWargearCost] = []
    for index, li in enumerate(_section_li_nodes(section, template_nodes=template_nodes), start=1):
        raw_name, points = _row_label_and_points(li=li, template_texts=template_texts)
        costs.append(
            MfmWargearCost(
                raw_name=raw_name,
                points_per_item=points,
                source_id=f"{source_prefix}:wargear:{source_label_slug(raw_name)}:{index}",
            )
        )
    return tuple(costs)


def _enhancements_from_section(
    *,
    section: _HtmlNode,
    source_prefix: str,
) -> tuple[MfmEnhancementRecord, ...]:
    enhancements: list[MfmEnhancementRecord] = []
    wrappers = [
        node
        for node in _walk(section, tag="div")
        if any(child.tag == "li" for child in _direct_node_children(node))
    ]
    for wrapper in wrappers:
        li = next(child for child in _direct_node_children(wrapper) if child.tag == "li")
        spans = [_node_text(span) for span in _walk(li, tag="span")]
        if len(spans) < 2:
            raise MfmSourceError("MFM enhancement row is missing name or points.")
        raw_name = spans[0]
        points = parse_points_label(spans[1])
        name = normalize_source_label(raw_name)
        enhancement_id = source_label_slug(_strip_upgrade_suffix(name))
        leader_allowance = _enhancement_leader_allowance_from_wrapper(
            wrapper=wrapper,
            source_id=f"{source_prefix}:enhancement:{enhancement_id}:leader",
        )
        enhancements.append(
            MfmEnhancementRecord(
                enhancement_id=enhancement_id,
                raw_name=raw_name,
                points=points,
                is_upgrade=name.lower().endswith(" (upgrade)"),
                leader_allowance=leader_allowance,
                source_id=f"{source_prefix}:enhancement:{enhancement_id}",
            )
        )
    return tuple(enhancements)


def _attachment_allowance_from_section(
    *,
    section: _HtmlNode,
    template_texts: dict[str, str],
    attachment_role: str,
    source_id: str,
) -> MfmLeaderAllowance | None:
    if attachment_role.upper() not in _ATTACHMENT_SECTION_HEADERS:
        raise MfmSourceError("MFM attachment allowance role is unsupported.")
    header = _first_direct_node_child(section)
    names: list[str] = []
    for child in _direct_node_children(section):
        if child is header:
            continue
        if child.tag == "span":
            names.extend(_split_attachment_names(_node_text(child)))
        elif child.tag == "template":
            template_id = child.attrs.get("id")
            if template_id is not None and template_id in template_texts:
                template_text = template_texts[template_id]
                if (
                    template_text.upper() not in _ATTACHMENT_SECTION_HEADERS
                    and _POINTS_RE.fullmatch(template_text) is None
                ):
                    names.extend(_split_attachment_names(template_text))
    if not names:
        if any(child.tag == "template" for child in _direct_node_children(section)):
            return None
        raise MfmSourceError(f"MFM {attachment_role.upper()} section has no bodyguard names.")
    normalized_names = tuple(normalize_source_label(name) for name in names)
    return MfmLeaderAllowance(
        allowed_bodyguard_unit_ids=tuple(source_label_slug(name) for name in normalized_names),
        allowed_bodyguard_names=normalized_names,
        source_id=source_id,
    )


def _merge_duplicate_unit_record(
    *,
    previous: MfmUnitRecord,
    current: MfmUnitRecord,
) -> MfmUnitRecord:
    if previous.to_payload() == current.to_payload():
        return previous
    if (
        previous.record_id == current.record_id
        and previous.unit_id == current.unit_id
        and previous.raw_name == current.raw_name
        and previous.source_section_id == current.source_section_id
        and previous.source_section_name == current.source_section_name
        and previous.cost_brackets == current.cost_brackets
        and previous.wargear_costs == current.wargear_costs
        and previous.source_id == current.source_id
    ):
        leader_allowance = _merged_attachment_allowance(
            previous=previous.leader_allowance,
            current=current.leader_allowance,
        )
        support_allowance = _merged_attachment_allowance(
            previous=previous.support_allowance,
            current=current.support_allowance,
        )
        return MfmUnitRecord(
            record_id=previous.record_id,
            unit_id=previous.unit_id,
            raw_name=previous.raw_name,
            source_section_id=previous.source_section_id,
            source_section_name=previous.source_section_name,
            cost_brackets=previous.cost_brackets,
            wargear_costs=previous.wargear_costs,
            leader_allowance=leader_allowance,
            support_allowance=support_allowance,
            source_id=previous.source_id,
        )
    raise MfmSourceError(
        f"MFM faction page contains conflicting duplicate unit cards for {previous.record_id}."
    )


def _merged_attachment_allowance(
    *,
    previous: MfmLeaderAllowance | None,
    current: MfmLeaderAllowance | None,
) -> MfmLeaderAllowance | None:
    if previous is None:
        return current
    if current is None or current == previous:
        return previous
    raise MfmSourceError("MFM duplicate unit cards contain conflicting attachment allowances.")


def _enhancement_leader_allowance_from_wrapper(
    *,
    wrapper: _HtmlNode,
    source_id: str,
) -> MfmLeaderAllowance | None:
    for div in _walk(wrapper, tag="div"):
        spans = [_node_text(span) for span in _walk(div, tag="span")]
        if len(spans) >= 2 and spans[0].upper() == "LEADER:":
            names = tuple(
                normalize_source_label(name) for name in _split_attachment_names(spans[1])
            )
            return MfmLeaderAllowance(
                allowed_bodyguard_unit_ids=tuple(source_label_slug(name) for name in names),
                allowed_bodyguard_names=names,
                source_id=source_id,
            )
    return None


def _row_label_and_points(*, li: _HtmlNode, template_texts: dict[str, str]) -> tuple[str, int]:
    values = [_node_text(span) for span in _direct_node_children(li) if span.tag == "span"]
    for template in (child for child in _direct_node_children(li) if child.tag == "template"):
        template_id = template.attrs.get("id")
        if template_id is None:
            raise MfmSourceError("MFM row template is missing id.")
        try:
            values.append(template_texts[template_id])
        except KeyError as exc:
            raise MfmSourceError("MFM row template did not resolve to text.") from exc
    if len(values) < 2:
        raise MfmSourceError("MFM row is missing a label or points value.")
    return values[0], parse_points_label(values[1])


def _template_nodes(root: _HtmlNode) -> dict[str, _HtmlNode]:
    nodes: dict[str, _HtmlNode] = {}
    for node in _walk(root, tag="div"):
        node_id = node.attrs.get("id")
        if node_id is None or not node_id.startswith("S:"):
            continue
        nodes["P:" + node_id.split(":", 1)[1]] = node
    if not nodes:
        raise MfmSourceError("MFM page did not contain streamed template nodes.")
    return nodes


def _template_texts(template_nodes: dict[str, _HtmlNode]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for template_id, node in template_nodes.items():
        text = _node_text(node)
        if not text:
            continue
        texts[template_id] = text
    if not texts:
        raise MfmSourceError("MFM page did not contain streamed template values.")
    return texts


def _section_li_nodes(
    section: _HtmlNode,
    *,
    template_nodes: dict[str, _HtmlNode],
) -> tuple[_HtmlNode, ...]:
    rows = list(_walk(section, tag="li"))
    for template in _walk(section, tag="template"):
        template_id = template.attrs.get("id")
        if template_id is None:
            raise MfmSourceError("MFM section template is missing id.")
        template_node = template_nodes.get(template_id)
        if template_node is None:
            raise MfmSourceError("MFM section template did not resolve to a node.")
        rows.extend(_walk(template_node, tag="li"))
    return tuple(rows)


def _card_nodes(root: _HtmlNode) -> tuple[_HtmlNode, ...]:
    return tuple(card for card, _section_id, _section_name in _card_nodes_with_sections(root))


def _card_nodes_with_sections(
    root: _HtmlNode,
) -> tuple[tuple[_HtmlNode, str | None, str | None], ...]:
    cards: list[tuple[_HtmlNode, str | None, str | None]] = []
    section_state = _SectionState(section_id=None, section_name=None, include_cards=None)
    _collect_card_nodes_with_sections(
        node=root,
        section_state=section_state,
        cards=cards,
    )
    return tuple(cards)


@dataclass(slots=True)
class _SectionState:
    section_id: str | None
    section_name: str | None
    include_cards: bool | None


def _collect_card_nodes_with_sections(
    *,
    node: _HtmlNode,
    section_state: _SectionState,
    cards: list[tuple[_HtmlNode, str | None, str | None]],
) -> None:
    for child in _direct_node_children(node):
        if child.tag == "h3":
            section_name = _node_text(child)
            if not section_name:
                raise MfmSourceError("MFM page contains an empty section heading.")
            section_id = source_label_slug(section_name)
            section_state.section_name = section_name
            section_state.section_id = section_id
            section_state.include_cards = _mfm_section_is_supported(section_id)
            continue
        if section_state.include_cards is False:
            continue
        if _node_has_class_tokens(child, _CARD_CLASS_TOKENS):
            if section_state.include_cards is None:
                raise MfmSourceError("MFM card appears outside a classified section.")
            cards.append((child, section_state.section_id, section_state.section_name))
        _collect_card_nodes_with_sections(
            node=child,
            section_state=section_state,
            cards=cards,
        )


def _unit_title_node(
    card: _HtmlNode,
    *,
    template_nodes: dict[str, _HtmlNode],
) -> _HtmlNode | None:
    for child in _direct_node_children(card):
        title_content = _unit_title_content_node(child)
        if title_content is not None:
            return title_content
    for template in (child for child in _direct_node_children(card) if child.tag == "template"):
        template_id = template.attrs.get("id")
        if template_id is None:
            raise MfmSourceError("MFM unit title template is missing id.")
        template_node = template_nodes.get(template_id)
        if template_node is None:
            raise MfmSourceError("MFM unit title template did not resolve to a node.")
        for candidate in _walk(template_node, tag="div"):
            title_content = _unit_title_content_node(candidate)
            if title_content is not None:
                return title_content
    return None


def _unit_title_content_node(candidate: _HtmlNode) -> _HtmlNode | None:
    if not _node_has_class_tokens(candidate, _UNIT_TITLE_CLASS_TOKENS):
        return None
    if any(
        _DETACHMENT_POINTS_RE.fullmatch(_node_text(span)) is not None
        for span in _walk(candidate, tag="span")
    ):
        return None
    if _node_has_class_token(candidate, "text-xl") and _node_text(candidate):
        return candidate
    for span in _walk(candidate, tag="span"):
        if _node_has_class_token(span, "text-xl") and _node_text(span):
            return span
    return None


def _detachment_title_node(card: _HtmlNode) -> _HtmlNode | None:
    for child in _direct_node_children(card):
        if _node_has_class_tokens(child, _DETACHMENT_TITLE_CLASS_TOKENS):
            spans = [_node_text(span) for span in _walk(child, tag="span")]
            if len(spans) >= 2 and _DETACHMENT_POINTS_RE.fullmatch(spans[1]) is not None:
                return child
    return None


def _parse_detachment_points(label: str) -> int:
    normalized = normalize_source_label(label)
    match = _DETACHMENT_POINTS_RE.fullmatch(normalized)
    if match is None:
        raise MfmSourceError("MFM detachment point label is invalid.")
    return _validate_non_negative_int(
        "detachment points",
        int(match.group("points").replace(",", "")),
    )


def _ordinal_to_int(value: str) -> int:
    normalized = normalize_source_label(value)
    match = _ORDINAL_RE.fullmatch(normalized)
    if match is None:
        raise MfmSourceError("MFM ordinal label is invalid.")
    return int(match.group("number"))


def _validate_factions(values: tuple[MfmFactionRecord, ...]) -> tuple[MfmFactionRecord, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmSourcePackage factions must be a tuple.")
    if not values:
        raise MfmSourceError("MfmSourcePackage factions must not be empty.")
    seen: set[str] = set()
    for value in values:
        if type(value) is not MfmFactionRecord:
            raise MfmSourceError("MfmSourcePackage factions must contain MfmFactionRecord values.")
        if value.faction_id in seen:
            raise MfmSourceError("MfmSourcePackage factions must not contain duplicates.")
        seen.add(value.faction_id)
    return tuple(sorted(values, key=lambda value: value.faction_id))


def _validate_detachments(
    values: tuple[MfmDetachmentRecord, ...],
) -> tuple[MfmDetachmentRecord, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmFactionRecord detachments must be a tuple.")
    seen: set[str] = set()
    for value in values:
        if type(value) is not MfmDetachmentRecord:
            raise MfmSourceError(
                "MfmFactionRecord detachments must contain MfmDetachmentRecord values."
            )
        if value.detachment_id in seen:
            raise MfmSourceError("MfmFactionRecord detachments must not contain duplicates.")
        seen.add(value.detachment_id)
    return tuple(sorted(values, key=lambda value: value.detachment_id))


def _validate_units(values: tuple[MfmUnitRecord, ...]) -> tuple[MfmUnitRecord, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmFactionRecord units must be a tuple.")
    if not values:
        raise MfmSourceError("MfmFactionRecord units must not be empty.")
    seen: set[str] = set()
    for value in values:
        if type(value) is not MfmUnitRecord:
            raise MfmSourceError("MfmFactionRecord units must contain MfmUnitRecord values.")
        if value.record_id in seen:
            raise MfmSourceError("MfmFactionRecord units must not contain duplicates.")
        seen.add(value.record_id)
    return tuple(sorted(values, key=lambda value: value.record_id))


def _validate_cost_brackets(
    values: tuple[MfmUnitCostBracket, ...],
) -> tuple[MfmUnitCostBracket, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmUnitRecord cost_brackets must be a tuple.")
    if not values:
        raise MfmSourceError("MfmUnitRecord cost_brackets must not be empty.")
    seen: set[tuple[int, int | None]] = set()
    for value in values:
        if type(value) is not MfmUnitCostBracket:
            raise MfmSourceError(
                "MfmUnitRecord cost_brackets must contain MfmUnitCostBracket values."
            )
        key = (value.unit_number_min, value.unit_number_max)
        if key in seen:
            raise MfmSourceError("MfmUnitRecord cost_brackets must not contain duplicates.")
        seen.add(key)
    return tuple(
        sorted(values, key=lambda value: (value.unit_number_min, value.unit_number_max or 0))
    )


def _validate_cost_rows(values: tuple[MfmUnitCostRow, ...]) -> tuple[MfmUnitCostRow, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmUnitCostBracket rows must be a tuple.")
    if not values:
        raise MfmSourceError("MfmUnitCostBracket rows must not be empty.")
    seen: set[tuple[int, str | None]] = set()
    for value in values:
        if type(value) is not MfmUnitCostRow:
            raise MfmSourceError("MfmUnitCostBracket rows must contain MfmUnitCostRow values.")
        if value.model_count is None:
            continue
        key = (value.model_count, value.model_id)
        if key in seen:
            raise MfmSourceError("MfmUnitCostBracket rows must not contain duplicate counts.")
        seen.add(key)
    return tuple(
        sorted(
            values,
            key=lambda value: (
                value.model_count is None,
                value.model_count or 0,
                value.model_id or "",
                value.additional_model_id or "",
            ),
        )
    )


def _validate_wargear_costs(values: tuple[MfmWargearCost, ...]) -> tuple[MfmWargearCost, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmUnitRecord wargear_costs must be a tuple.")
    seen: set[str] = set()
    for value in values:
        if type(value) is not MfmWargearCost:
            raise MfmSourceError("MfmUnitRecord wargear_costs must contain MfmWargearCost values.")
        if value.wargear_id in seen:
            raise MfmSourceError("MfmUnitRecord wargear_costs must not contain duplicates.")
        seen.add(value.wargear_id)
    return tuple(sorted(values, key=lambda value: value.wargear_id))


def _validate_enhancements(
    values: tuple[MfmEnhancementRecord, ...],
) -> tuple[MfmEnhancementRecord, ...]:
    if type(values) is not tuple:
        raise MfmSourceError("MfmDetachmentRecord enhancements must be a tuple.")
    seen: set[str] = set()
    for value in values:
        if type(value) is not MfmEnhancementRecord:
            raise MfmSourceError(
                "MfmDetachmentRecord enhancements must contain MfmEnhancementRecord values."
            )
        if value.enhancement_id in seen:
            raise MfmSourceError("MfmDetachmentRecord enhancements must not contain duplicates.")
        seen.add(value.enhancement_id)
    return tuple(sorted(values, key=lambda value: value.enhancement_id))


def _validate_name_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise MfmSourceError(f"{field_name} must be a tuple.")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = normalize_source_label(value)
        if source_label_slug(name) in seen:
            raise MfmSourceError(f"{field_name} must not contain duplicates.")
        seen.add(source_label_slug(name))
        normalized.append(name)
    if not normalized:
        raise MfmSourceError(f"{field_name} must not be empty.")
    return tuple(normalized)
