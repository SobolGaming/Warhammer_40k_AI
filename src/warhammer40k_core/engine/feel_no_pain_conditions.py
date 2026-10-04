"""Shared attack classification for ordinary and attack-attributed mortal wounds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.damage_allocation import FeelNoPainAttackCondition, FeelNoPainSource
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_abilities import is_psychic_weapon_profile

if TYPE_CHECKING:
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )


def feel_no_pain_source_applies_to_attack(
    *,
    source: FeelNoPainSource,
    is_psychic_attack: bool,
) -> bool:
    if type(source) is not FeelNoPainSource or type(is_psychic_attack) is not bool:
        raise GameLifecycleError(
            "Feel No Pain attack filtering requires a source and classification."
        )
    if source.attack_condition is None:
        return True
    if source.attack_condition is FeelNoPainAttackCondition.PSYCHIC_ATTACK:
        return is_psychic_attack
    raise GameLifecycleError("Unsupported Feel No Pain attack condition.")


def feel_no_pain_source_applies_to_mortal_wounds(
    *,
    source: FeelNoPainSource,
    destruction_evidence: MortalWoundDestructionEvidence | None,
) -> bool:
    if destruction_evidence is None:
        return source.attack_condition is None or source.mortal_wounds
    provenance = destruction_evidence.destruction_attribution.destruction_provenance
    if provenance.destruction_source_kind is not DestructionSourceKind.ATTACK:
        return source.attack_condition is None or source.mortal_wounds
    profile = provenance.source_weapon_profile
    if profile is None:
        raise GameLifecycleError("Attack-attributed mortal wounds require a weapon profile.")
    return source.mortal_wounds or feel_no_pain_source_applies_to_attack(
        source=source,
        is_psychic_attack=is_psychic_weapon_profile(profile),
    )
