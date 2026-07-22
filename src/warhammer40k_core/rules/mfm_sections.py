from __future__ import annotations

from warhammer40k_core.rules.mfm_validation import MfmSourceError

SUPPORTED_MFM_SECTION_IDS = frozenset(
    (
        "blood-legions",
        "detachments",
        "every-model-has-the-imperium-keyword",
        "harlequins",
        "imperial-fists",
        "iron-hands",
        "legions-of-excess",
        "plague-legions",
        "raven-guard",
        "salamanders",
        "scintillating-legions",
        "space-marines",
        "ultramarines",
        "units",
        "white-scars",
        "ynnari",
    )
)

EXCLUDED_MFM_SECTION_IDS = frozenset(
    (
        "boarding-action",
        "boarding-actions",
        "combat-patrol",
        "crusade",
        "forge-world",
        "forge-worlds",
        "kill-team",
        "legends",
        "warhammer-legends",
    )
)


def mfm_section_is_supported(section_id: str) -> bool:
    if type(section_id) is not str:
        raise MfmSourceError("MFM section_id must be a string.")
    if section_id in SUPPORTED_MFM_SECTION_IDS:
        return True
    if section_id in EXCLUDED_MFM_SECTION_IDS:
        return False
    raise MfmSourceError(f"MFM page contains unknown section heading {section_id!r}.")
