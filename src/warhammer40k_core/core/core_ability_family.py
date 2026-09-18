"""Canonical Core ability families, normalized once at catalog ingress."""

from __future__ import annotations

from enum import StrEnum


class CoreAbilityFamily(StrEnum):
    DEEP_STRIKE = "deep_strike"
    INFILTRATORS = "infiltrators"
    LEADER = "leader"
    SUPPORT = "support"
    SCOUTS = "scouts"
    FIRING_DECK = "firing_deck"
    DEADLY_DEMISE = "deadly_demise"
    FEEL_NO_PAIN = "feel_no_pain"
    FIGHTS_FIRST = "fights_first"
    LONE_OPERATIVE = "lone_operative"
    STEALTH = "stealth"


_SOURCE_IDS = {
    "000008343": CoreAbilityFamily.DEEP_STRIKE,
    "000008345": CoreAbilityFamily.INFILTRATORS,
    "000008346": CoreAbilityFamily.LEADER,
    "000008344": CoreAbilityFamily.SCOUTS,
    "000008340": CoreAbilityFamily.FIGHTS_FIRST,
    "000008336": CoreAbilityFamily.LONE_OPERATIVE,
    "000008337": CoreAbilityFamily.STEALTH,
    **{family.value.replace("_", "-"): family for family in CoreAbilityFamily},
    **{f"core-{family.value.replace('_', '-')}": family for family in CoreAbilityFamily},
}


def normalize_core_ability_family(*, ability_id: str, name: str) -> CoreAbilityFamily | None:
    """Normalize imported definition metadata; unknown families remain unsupported.

    Definition IDs are authoritative when present. Imported Core display text
    otherwise supplies the family at this boundary, never in an engine query.
    The original ID, name and source row remain unchanged for provenance.
    """
    identified = _SOURCE_IDS.get(ability_id)
    if identified is not None:
        return identified
    words = tuple(name.upper().replace("-", " ").replace("_", " ").replace('"', " ").split())
    if words and words[0] == "CORE":
        words = words[1:]
    for family in CoreAbilityFamily:
        family_words = tuple(family.value.upper().split("_"))
        if words[: len(family_words)] == family_words:
            return family
    return None
