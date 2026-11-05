from __future__ import annotations

import hashlib
from functools import cache

import msgspec

from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

from .event_companion_full_artifact_errors import EventCompanionBattlefieldArtifactError
from .event_companion_full_artifact_types import ObjectiveArtifact

EXPECTED_ASSOCIATION_SHA256 = "e5422e499b1b77863450f84e8afad58e6c58cfc819af4b31568239993389d9f8"
_PACKAGE = (
    "warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layouts_2026_06"
)


class ObjectiveAssociation(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    terrain_area_ids: tuple[str, ...]
    runtime_reference_inches: tuple[float, float]
    illustration_center_inches: tuple[float, float]
    runtime_reference_basis: str


class ObjectiveAssociationTable(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    schema: str
    source_pdf_sha256: str
    source_review_sha256: str
    objectives: dict[str, ObjectiveAssociation]


@cache
def reviewed_objective_associations() -> dict[str, ObjectiveAssociation]:
    raw = package_artifact_bytes(_PACKAGE, "artifacts/event-companion-objective-associations.json")
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ASSOCIATION_SHA256:
        raise EventCompanionBattlefieldArtifactError(
            "Reviewed objective association bytes drifted."
        )
    table = msgspec.json.decode(raw, type=ObjectiveAssociationTable)
    if table.schema != "reviewed-event-objective-terrain-associations-v1" or (
        len(table.objectives) != 249
        or sum(len(row.terrain_area_ids) for row in table.objectives.values()) != 270
        or any(not row.terrain_area_ids for row in table.objectives.values())
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Reviewed objective association inventory drifted."
        )
    return table.objectives


def validate_reviewed_objective_association(objective: ObjectiveArtifact) -> None:
    expected = reviewed_objective_associations().get(objective.objective_id)
    if expected is None or tuple(sorted(objective.terrain_area_ids)) != expected.terrain_area_ids:
        raise EventCompanionBattlefieldArtifactError(
            "Event objective must retain its exact reviewed logical terrain group."
        )
    if (objective.x_inches, objective.y_inches) != expected.runtime_reference_inches or (
        (objective.illustration_x_inches, objective.illustration_y_inches)
        != expected.illustration_center_inches
        or objective.runtime_reference_basis != expected.runtime_reference_basis
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event objective illustration and semantic reference evidence drifted."
        )
