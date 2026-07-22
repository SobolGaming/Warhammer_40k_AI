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
            patch_id="faq-end-of-battle-vp-round-cap-exemption",
            target_id="mission-scoring:end-of-battle",
            operation_kind="faq_behavior",
            behavior_descriptor="end_of_battle_vp_exempt_from_battle_round_cap",
            source_page=4,
            source_id=f"{source_package_id}:faq:end-of-battle-vp-cap",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-operation-marker-removal-clears-status",
            target_id="mission-actions:operation-marker-status",
            operation_kind="faq_behavior",
            behavior_descriptor="operation_marker_removal_clears_applied_status",
            source_page=4,
            source_id=f"{source_package_id}:faq:operation-marker-status",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-operation-marker-removal-requires-card-permission",
            target_id="mission-actions:operation-marker",
            operation_kind="faq_behavior",
            behavior_descriptor="operation_marker_removal_requires_primary_card_permission",
            source_page=4,
            source_id=f"{source_package_id}:faq:operation-markers",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-death-trap-trapped-area-scoring-window",
            target_id="primary-death-trap",
            operation_kind="faq_behavior",
            behavior_descriptor="death_trap_trapped_area_checked_at_scoring_not_destruction_time",
            source_page=4,
            source_id=f"{source_package_id}:faq:death-trap",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-surveil-the-foe-same-turn-marker-removal",
            target_id="primary-surveil-the-foe",
            operation_kind="faq_behavior",
            behavior_descriptor="surveil_the_foe_same_turn_marker_removal_allows_scoring",
            source_page=4,
            source_id=f"{source_package_id}:faq:surveil-the-foe",
        ),
        EventCompanionFaqPatch(
            patch_id="faq-vital-link-multiple-central-objectives",
            target_id="primary-vital-link",
            operation_kind="faq_behavior",
            behavior_descriptor=(
                "vital_link_multiple_central_objectives_marker_control_allows_cumulative_vp"
            ),
            source_page=4,
            source_id=f"{source_package_id}:faq:vital-link",
        ),
    )
