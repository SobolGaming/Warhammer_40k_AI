from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06,
)


@dataclass(frozen=True, slots=True)
class EventCompanionFaqPatch:
    patch_id: str
    target_id: str
    operation_kind: str
    behavior_descriptor: str
    source_page: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "patch_id": self.patch_id,
            "target_id": self.target_id,
            "operation_kind": self.operation_kind,
            "behavior_descriptor": self.behavior_descriptor,
            "source_page": self.source_page,
            "source_id": self.source_id,
        }


def faq_patch_rows() -> tuple[EventCompanionFaqPatch, ...]:
    source_package_id = event_companion_2026_06.SOURCE_PACKAGE_ID
    return (
        EventCompanionFaqPatch(
            patch_id="faq-operation-markers-removed-when-action-interrupted",
            target_id="mission-actions:operation-marker",
            operation_kind="remove_operation_markers",
            behavior_descriptor="operation_markers_removed_when_action_interrupted_or_completed",
            source_page=4,
            source_id=f"{source_package_id}:faq:operation-markers",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-death-trap-booby-trap-marker-removal",
            target_id="primary-death-trap",
            operation_kind="primary_mission_behavior",
            behavior_descriptor="booby_trap_marker_removed_when_area_loses_trapped_status",
            source_page=4,
            source_id=f"{source_package_id}:faq:death-trap",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-surveil-the-foe-marker-control-window",
            target_id="primary-surveil-the-foe",
            operation_kind="primary_mission_scoring",
            behavior_descriptor="surveil_marker_control_checked_at_scoring_window",
            source_page=4,
            source_id=f"{source_package_id}:faq:surveil-the-foe",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-vital-link-vp-limit",
            target_id="primary-vital-link",
            operation_kind="primary_mission_scoring",
            behavior_descriptor="vital_link_vp_limit_applies_to_total_mission_vp",
            source_page=4,
            source_id=f"{source_package_id}:faq:vital-link",
        ),
    )
