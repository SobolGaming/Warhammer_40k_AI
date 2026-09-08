"""Source-backed model keyword ownership, independent of runtime presence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, Self, TypedDict

from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.validation import IdentifierValidator, canonical_keyword_token


class ModelKeywordError(ValueError):
    """Model keyword ownership is incomplete, ambiguous, or malformed."""


class ModelKeywordAssignmentPayload(TypedDict):
    datasheet_id: str
    model_profile_id: str
    keywords: list[str]
    faction_keywords: list[str]
    source_ids: list[str]
    materialization_descriptor_id: NotRequired[str]


@dataclass(frozen=True, slots=True)
class ModelKeywordAssignment:
    datasheet_id: str
    model_profile_id: str
    keywords: tuple[str, ...]
    faction_keywords: tuple[str, ...]
    source_ids: tuple[str, ...]
    materialization_descriptor_id: str | None = None

    def __post_init__(self) -> None:
        if self.materialization_descriptor_id is not None:
            object.__setattr__(
                self,
                "materialization_descriptor_id",
                _identifier("materialization_descriptor_id", self.materialization_descriptor_id),
            )
        for name in ("datasheet_id", "model_profile_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        for name, values in (
            ("keywords", self.keywords),
            ("faction_keywords", self.faction_keywords),
            ("source_ids", self.source_ids),
        ):
            if type(values) is not tuple:
                raise ModelKeywordError(f"Model keyword {name} must be a tuple.")
            tokens = tuple(_identifier(name, value) for value in values)
            if name != "source_ids":
                tokens = tuple(canonical_keyword_token(value) for value in tokens)
            if len(set(tokens)) != len(tokens):
                raise ModelKeywordError(f"Model keyword {name} contains duplicate values.")
            if name == "source_ids" and not tokens:
                raise ModelKeywordError("Model keyword assignment requires source_ids.")
            object.__setattr__(self, name, tuple(sorted(tokens)))

    def to_payload(self) -> ModelKeywordAssignmentPayload:
        payload: ModelKeywordAssignmentPayload = {
            "datasheet_id": self.datasheet_id,
            "model_profile_id": self.model_profile_id,
            "keywords": list(self.keywords),
            "faction_keywords": list(self.faction_keywords),
            "source_ids": list(self.source_ids),
        }
        if self.materialization_descriptor_id is not None:
            payload["materialization_descriptor_id"] = self.materialization_descriptor_id
        return payload

    @classmethod
    def from_payload(cls, payload: ModelKeywordAssignmentPayload) -> Self:
        if set(payload) - {"materialization_descriptor_id"} != {
            "datasheet_id",
            "model_profile_id",
            "keywords",
            "faction_keywords",
            "source_ids",
        }:
            raise ModelKeywordError("Model keyword assignment payload fields are invalid.")
        for values in (payload["keywords"], payload["faction_keywords"], payload["source_ids"]):
            if type(values) is not list or any(type(value) is not str for value in values):
                raise ModelKeywordError("Model keyword payload inventories must be string lists.")
        return cls(
            datasheet_id=payload["datasheet_id"],
            model_profile_id=payload["model_profile_id"],
            keywords=tuple(payload["keywords"]),
            faction_keywords=tuple(payload["faction_keywords"]),
            source_ids=tuple(payload["source_ids"]),
            materialization_descriptor_id=(
                _identifier(
                    "materialization_descriptor_id", payload["materialization_descriptor_id"]
                )
                if "materialization_descriptor_id" in payload
                else None
            ),
        )


def validate_model_keyword_assignments(
    assignments: tuple[ModelKeywordAssignment, ...],
    datasheets: tuple[DatasheetDefinition, ...],
) -> tuple[ModelKeywordAssignment, ...]:
    if type(assignments) is not tuple or any(
        type(row) is not ModelKeywordAssignment for row in assignments
    ):
        raise ModelKeywordError("Catalog model keyword assignments must be typed tuples.")
    by_sheet = {sheet.datasheet_id: sheet for sheet in datasheets}
    seen: set[tuple[str, str, str | None]] = set()
    for row in assignments:
        key = (row.datasheet_id, row.model_profile_id, row.materialization_descriptor_id)
        if key in seen:
            raise ModelKeywordError("Catalog model keyword assignments contain duplicate profiles.")
        seen.add(key)
        sheet = by_sheet.get(row.datasheet_id)
        if sheet is None or row.model_profile_id not in {
            p.model_profile_id for p in sheet.model_profiles
        }:
            raise ModelKeywordError("Catalog model keyword assignment has unknown lineage.")
    for sheet_id in {row.datasheet_id for row in assignments}:
        sheet = by_sheet[sheet_id]
        rows = tuple(row for row in assignments if row.datasheet_id == sheet_id)
        if {row.model_profile_id for row in rows if row.materialization_descriptor_id is None} != {
            p.model_profile_id for p in sheet.model_profiles
        }:
            raise ModelKeywordError(
                "Catalog model keyword assignments must be complete for a datasheet."
            )
        if {k for row in rows for k in row.keywords} != set(sheet.keywords.keywords) or {
            k for row in rows for k in row.faction_keywords
        } != set(sheet.keywords.faction_keywords):
            raise ModelKeywordError(
                "Catalog model keyword union must match the datasheet inventory."
            )
    return tuple(
        sorted(
            assignments,
            key=lambda row: (
                row.datasheet_id,
                row.model_profile_id,
                row.materialization_descriptor_id or "",
            ),
        )
    )


def model_keyword_assignment(
    *,
    datasheet: DatasheetDefinition,
    model_profile_id: str,
    assignments: tuple[ModelKeywordAssignment, ...],
    materialization_descriptor_id: str | None = None,
) -> ModelKeywordAssignment:
    """Unscoped datasheet keywords apply to every model; scoped rows are exhaustive."""
    profile = datasheet.model_profile_by_id(model_profile_id)
    rows = tuple(row for row in assignments if row.datasheet_id == datasheet.datasheet_id)
    if rows:
        profile_rows = tuple(row for row in rows if row.model_profile_id == model_profile_id)
        variants = tuple(
            row for row in profile_rows if row.materialization_descriptor_id is not None
        )
        if materialization_descriptor_id is not None and variants:
            for row in variants:
                if row.materialization_descriptor_id == materialization_descriptor_id:
                    return row
            raise ModelKeywordError("Model keyword assignment has an unknown materialization ID.")
        for row in rows:
            if (
                row.model_profile_id == model_profile_id
                and row.materialization_descriptor_id is None
            ):
                return row
        raise ModelKeywordError("Model keyword assignment is missing its profile.")
    return ModelKeywordAssignment(
        datasheet_id=datasheet.datasheet_id,
        model_profile_id=model_profile_id,
        keywords=datasheet.keywords.keywords,
        faction_keywords=datasheet.keywords.faction_keywords,
        source_ids=tuple(sorted({*datasheet.source_ids, *profile.source_ids})),
    )


_identifier = IdentifierValidator(ModelKeywordError)
