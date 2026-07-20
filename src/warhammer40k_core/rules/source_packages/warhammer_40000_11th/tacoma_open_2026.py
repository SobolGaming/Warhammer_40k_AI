from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor

RULES_OVERLAY_ID = "warhammer_40000_11th:event_overlay:tacoma_open_2026"
SOURCE_PACKAGE_ID = "gw-11e-tacoma-open-2026-event-faq"
CULT_AMBUSH_ATTACHED_CHARACTER_EXCLUSION_SOURCE_ID = (
    "warhammer_40000_11th:event_faq:tacoma_2026:cult_ambush_attached_character_exclusions"
)
FRAME_KEYWORD_ADDITIONS_SOURCE_ID = (
    "warhammer_40000_11th:event_faq:tacoma_2026:frame_keyword_additions"
)
SOURCE_PDF_FILENAME = "faq-warhammer-open-tacoma-2026-dtb3ingprd-cvcl2agtfd.pdf"
SOURCE_PDF_SHA256 = "5beadb2c29e100a31bb7ee54f429498555e07430997063111aa4694556568f97"


def apply_rules_overlay(descriptor: RulesetDescriptor) -> RulesetDescriptor:
    if type(descriptor) is not RulesetDescriptor:
        raise TypeError("Tacoma Open 2026 overlay requires RulesetDescriptor.")
    if RULES_OVERLAY_ID in descriptor.rules_overlay_ids:
        raise ValueError("Tacoma Open 2026 overlay is already active.")
    return replace(
        descriptor,
        rules_overlay_ids=(*descriptor.rules_overlay_ids, RULES_OVERLAY_ID),
        descriptor_hash="",
    )


def is_active(rules_overlay_ids: tuple[str, ...]) -> bool:
    if type(rules_overlay_ids) is not tuple:
        raise TypeError("Tacoma Open 2026 overlay lookup requires a tuple.")
    return RULES_OVERLAY_ID in rules_overlay_ids
