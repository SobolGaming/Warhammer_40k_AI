"""Decode explicit source-linked model assignments at the catalog boundary."""

import json
from typing import cast

from warhammer40k_core.core.model_keywords import (
    ModelKeywordAssignment,
    ModelKeywordAssignmentPayload,
)
from warhammer40k_core.rules.catalog_generation_errors import CatalogGenerationError
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def model_keyword_assignments_from_rows(
    rows: tuple[NormalizedSourceRow, ...],
) -> tuple[ModelKeywordAssignment, ...]:
    assignments: list[ModelKeywordAssignment] = []
    for row in rows:
        fields = row.runtime_fields_payload()
        if "model_keyword_assignments" not in fields:
            continue
        raw = fields["model_keyword_assignments"]
        if not raw:
            continue  # This source row declares only shared datasheet keywords.
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CatalogGenerationError("Invalid model keyword assignment JSON.") from exc
        if type(payload) is not list:
            raise CatalogGenerationError(
                "Model keyword assignments must be a nonempty object list."
            )
        items = cast(list[object], payload)
        if not items or any(type(item) is not dict for item in items):
            raise CatalogGenerationError(
                "Model keyword assignments must be a nonempty object list."
            )
        for item in items:
            assignment = ModelKeywordAssignment.from_payload(
                cast(ModelKeywordAssignmentPayload, item)
            )
            if (assignment.datasheet_id, assignment.model_profile_id) != (
                fields["datasheet_id"],
                fields["model_profile_id"],
            ):
                raise CatalogGenerationError("Model keyword source row lineage drifted.")
            assignments.append(assignment)
    return tuple(assignments)
