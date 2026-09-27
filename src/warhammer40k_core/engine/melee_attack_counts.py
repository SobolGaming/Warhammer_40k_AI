"""Shared melee split arithmetic, independent of declaration transport."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.movement_proposals import ProposalValidationResult
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
    from warhammer40k_core.engine.fight_weapon_selection import (
        MeleeTargetAllocation,
        MeleeWeaponDeclaration,
    )
    from warhammer40k_core.engine.game_state import GameState


def _require_declared_melee_attacks(allocation: MeleeTargetAllocation) -> int:
    from warhammer40k_core.engine.fight_weapon_selection import MeleeTargetAllocation

    if type(allocation) is not MeleeTargetAllocation:
        raise GameLifecycleError("_require_declared_melee_attacks requires an allocation.")
    attacks = allocation.attacks
    if attacks is None:
        raise GameLifecycleError("Split melee attack allocation is missing attacks.")
    return attacks


def _validate_melee_target_allocation_counts(
    *,
    request: MeleeDeclarationProposalRequest,
    declaration: MeleeWeaponDeclaration,
    profile: WeaponProfile,
    scenario: BattlefieldScenario,
    state: GameState | None,
    resolved_attacks: int | None = None,
) -> ProposalValidationResult | None:
    from warhammer40k_core.engine.fight_resolution import (
        _cleave_attack_bonus_for_target,
        _invalid_melee_validation,
    )

    target_count_validation = _validate_melee_target_count_limit(
        request=request,
        declaration=declaration,
        profile=profile,
        resolved_attacks=resolved_attacks,
    )
    if target_count_validation is not None:
        return target_count_validation
    target_count = len(declaration.target_allocations)
    fixed_attacks = (
        profile.attack_profile.fixed_attacks if resolved_attacks is None else resolved_attacks
    )
    if target_count == 1:
        declared_attacks = declaration.target_allocations[0].attacks
        expected_attacks = fixed_attacks
        if expected_attacks is not None:
            expected_attacks += _cleave_attack_bonus_for_target(
                scenario=scenario,
                profile=profile,
                single_target=True,
                target_unit_instance_id=declaration.target_allocations[0].target_unit_instance_id,
                state=state,
            )
        if (
            declared_attacks is not None
            and expected_attacks is not None
            and declared_attacks != expected_attacks
        ):
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_attack_count_drift",
                message="Single-target melee declaration must allocate every weapon attack.",
                field="target_allocations",
            )
        if declared_attacks is not None and fixed_attacks is None:
            return _invalid_melee_validation(
                request=request,
                violation_code="random_melee_single_target_count_declared",
                message="Single-target random Attacks melee declarations must omit attacks.",
                field="target_allocations",
            )
        return None
    if fixed_attacks is None:
        return _invalid_melee_validation(
            request=request,
            violation_code="random_melee_commitment_required",
            message="Random melee splits require their committed per-weapon attack budget.",
            field="target_allocations",
        )
    if any(allocation.attacks is None for allocation in declaration.target_allocations):
        return _invalid_melee_validation(
            request=request,
            violation_code="split_melee_attack_count_required",
            message="Split melee declarations require attacks for every target.",
            field="target_allocations",
        )
    declared_total = sum(
        _require_declared_melee_attacks(allocation) for allocation in declaration.target_allocations
    )
    if declared_total != fixed_attacks:
        return _invalid_melee_validation(
            request=request,
            violation_code="split_melee_attack_count_drift",
            message="Split melee declarations must allocate exactly the weapon Attacks.",
            field="target_allocations",
        )
    return None


def _validate_melee_target_count_limit(
    *,
    request: MeleeDeclarationProposalRequest,
    declaration: MeleeWeaponDeclaration,
    profile: WeaponProfile,
    resolved_attacks: int | None = None,
) -> ProposalValidationResult | None:
    from warhammer40k_core.engine.fight_resolution import (
        _invalid_melee_validation,
        _maximum_attacks_for_profile,
    )

    maximum_attacks = (
        _maximum_attacks_for_profile(profile) if resolved_attacks is None else resolved_attacks
    )
    if len(declaration.target_allocations) > maximum_attacks:
        return _invalid_melee_validation(
            request=request,
            violation_code="melee_target_count_exceeds_attacks",
            message="Melee declaration cannot select more target units than weapon Attacks.",
            field="target_allocations",
        )
    return None


__all__ = (
    "_require_declared_melee_attacks",
    "_validate_melee_target_allocation_counts",
    "_validate_melee_target_count_limit",
)
