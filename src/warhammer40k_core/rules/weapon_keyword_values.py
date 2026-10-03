"""Structured valued weapon keywords at the source ingestion boundary."""

from __future__ import annotations

import re

from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword


def valued_weapon_keyword(
    ability_text: str, *, target_keywords: tuple[str, ...]
) -> tuple[WeaponKeyword, AbilityDescriptor] | None:
    match = re.fullmatch(
        r"(?P<name>rapid[\s-]+fire|sustained[\s-]+hits|melta|cleave|blast)\s+"
        r"(?P<value>\d+)\+?",
        ability_text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    value = int(match.group("value"))
    key = re.sub(r"[\s-]+", "-", match.group("name").strip().casefold())
    builders = {
        "rapid-fire": (WeaponKeyword.RAPID_FIRE, AbilityDescriptor.rapid_fire),
        "sustained-hits": (WeaponKeyword.SUSTAINED_HITS, AbilityDescriptor.sustained_hits),
        "melta": (WeaponKeyword.MELTA, AbilityDescriptor.melta),
        "cleave": (WeaponKeyword.CLEAVE, AbilityDescriptor.cleave),
        "blast": (WeaponKeyword.BLAST, AbilityDescriptor.blast),
    }
    keyword, builder = builders[key]
    return keyword, builder(value, target_keywords=target_keywords)
