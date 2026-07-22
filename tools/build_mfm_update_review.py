from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from warhammer40k_core.rules.mfm_source import (
    MfmDetachmentRecord,
    MfmEnhancementRecord,
    MfmFactionRecord,
    MfmSourcePackage,
    MfmUnitRecord,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    mfm_2026_06,
    mfm_2026_07,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "source_manifests" / "mfm_2026_07_review.json"
REVIEW_SCHEMA = "core-v2-mfm-update-review-v1"


class MfmReviewError(ValueError):
    """Raised when the committed MFM update review is missing or stale."""


def main() -> None:
    args = _parse_args()
    payload = build_review_payload(
        previous=mfm_2026_06.source_package(),
        current=mfm_2026_07.source_package(),
    )
    rendered = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if args.check:
        if not args.output.is_file():
            raise MfmReviewError("Committed MFM update review is missing.")
        if args.output.read_text(encoding="utf-8") != rendered:
            raise MfmReviewError("Committed MFM update review is stale.")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


def build_review_payload(
    *,
    previous: MfmSourcePackage,
    current: MfmSourcePackage,
) -> dict[str, object]:
    previous_factions = {faction.faction_id: faction for faction in previous.factions}
    current_factions = {faction.faction_id: faction for faction in current.factions}
    if set(previous_factions) != set(current_factions):
        raise MfmReviewError("MFM update review requires identical supported faction sets.")
    if previous.excluded_faction_ids != current.excluded_faction_ids:
        raise MfmReviewError("MFM update review requires identical excluded faction sets.")

    faction_payloads = {
        faction_id: _faction_review(
            previous=previous_factions[faction_id],
            current=current_factions[faction_id],
        )
        for faction_id in sorted(current_factions)
    }
    return {
        "review_schema": REVIEW_SCHEMA,
        "source_url": current.source_url,
        "previous_source_package_id": previous.source_package_id,
        "previous_source_version": previous.source_version,
        "previous_source_payload_checksum_sha256": previous.source_payload_checksum_sha256(),
        "current_source_package_id": current.source_package_id,
        "current_source_version": current.source_version,
        "current_source_date": current.source_date,
        "current_source_payload_checksum_sha256": current.source_payload_checksum_sha256(),
        "excluded_faction_ids": list(current.excluded_faction_ids),
        "reviewed_faction_ids": sorted(current_factions),
        "summary": _review_summary(faction_payloads),
        "factions": faction_payloads,
    }


def _faction_review(
    *,
    previous: MfmFactionRecord,
    current: MfmFactionRecord,
) -> dict[str, object]:
    previous_units = {unit.record_id: unit for unit in previous.units}
    current_units = {unit.record_id: unit for unit in current.units}
    previous_detachments = {row.detachment_id: row for row in previous.detachments}
    current_detachments = {row.detachment_id: row for row in current.detachments}
    previous_enhancements = _enhancements_by_id(previous)
    current_enhancements = _enhancements_by_id(current)

    unit_records_added = sorted(set(current_units) - set(previous_units))
    unit_records_removed = sorted(set(previous_units) - set(current_units))
    detachment_records_added = sorted(set(current_detachments) - set(previous_detachments))
    detachment_records_removed = sorted(set(previous_detachments) - set(current_detachments))
    review = {
        "previous_unit_record_count": len(previous_units),
        "current_unit_record_count": len(current_units),
        "unit_records_added": unit_records_added,
        "unit_records_removed": unit_records_removed,
        "unit_point_rows_changed": _changed_ids(
            previous_units,
            current_units,
            _unit_cost_signature,
        ),
        "wargear_costs_changed": _changed_ids(
            previous_units,
            current_units,
            _wargear_cost_signature,
        ),
        "leader_assignments_changed": _changed_ids(
            previous_units,
            current_units,
            _leader_signature,
        ),
        "support_assignments_captured": sorted(
            unit.record_id for unit in current.units if unit.support_allowance is not None
        ),
        "previous_detachment_record_count": len(previous_detachments),
        "current_detachment_record_count": len(current_detachments),
        "detachment_records_added": detachment_records_added,
        "detachment_records_removed": detachment_records_removed,
        "detachment_rules_changed": _changed_ids(
            previous_detachments,
            current_detachments,
            _detachment_rule_signature,
        ),
        "enhancement_points_changed": _changed_ids(
            previous_enhancements,
            current_enhancements,
            _enhancement_points_signature,
        ),
    }
    review["status"] = (
        "changed"
        if any(
            value
            for key, value in review.items()
            if key.endswith(("_added", "_removed", "_changed", "_captured"))
        )
        else "unchanged"
    )
    return review


def _changed_ids[RecordT](
    previous: dict[str, RecordT],
    current: dict[str, RecordT],
    signature: Callable[[RecordT], object],
) -> list[str]:
    return [
        record_id
        for record_id in sorted(set(previous).intersection(current))
        if signature(previous[record_id]) != signature(current[record_id])
    ]


def _unit_cost_signature(unit: MfmUnitRecord) -> object:
    return tuple(
        (
            bracket.unit_number_min,
            bracket.unit_number_max,
            tuple(
                (
                    row.model_count,
                    row.model_component_counts,
                    row.model_component_ids,
                    row.additional_model_count,
                    row.additional_model_id,
                    row.points,
                )
                for row in bracket.rows
            ),
        )
        for bracket in unit.cost_brackets
    )


def _wargear_cost_signature(unit: MfmUnitRecord) -> object:
    return tuple((cost.wargear_id, cost.points_per_item) for cost in unit.wargear_costs)


def _leader_signature(unit: MfmUnitRecord) -> object:
    if unit.leader_allowance is None:
        return None
    return unit.leader_allowance.allowed_bodyguard_unit_ids


def _detachment_rule_signature(detachment: MfmDetachmentRecord) -> object:
    return detachment.detachment_point_cost, detachment.force_disposition_id


def _enhancements_by_id(faction: MfmFactionRecord) -> dict[str, MfmEnhancementRecord]:
    return {
        f"{detachment.detachment_id}:{enhancement.enhancement_id}": enhancement
        for detachment in faction.detachments
        for enhancement in detachment.enhancements
    }


def _enhancement_points_signature(enhancement: MfmEnhancementRecord) -> object:
    return enhancement.points


def _review_summary(factions: dict[str, dict[str, object]]) -> dict[str, int]:
    list_fields = (
        "unit_records_added",
        "unit_records_removed",
        "unit_point_rows_changed",
        "wargear_costs_changed",
        "leader_assignments_changed",
        "support_assignments_captured",
        "detachment_records_added",
        "detachment_records_removed",
        "detachment_rules_changed",
        "enhancement_points_changed",
    )
    summary = {
        "reviewed_faction_count": len(factions),
        "changed_faction_count": sum(row["status"] == "changed" for row in factions.values()),
    }
    for field_name in list_fields:
        summary[field_name] = sum(len(_required_list(row[field_name])) for row in factions.values())
    return summary


def _required_list(value: object) -> list[object]:
    if type(value) is not list:
        raise MfmReviewError("MFM review summary field must be a list.")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the committed MFM v1.0 to v1.1 review.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    main()
