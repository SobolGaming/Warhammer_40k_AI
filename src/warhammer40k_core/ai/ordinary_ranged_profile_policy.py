"""Opt-in expected wound comparison for an admitted Bolt of Change offer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import comb
from typing import TypedDict, cast

from warhammer40k_core.ai.normal_shooting_policy import MAX_TARGET_ROWS, normal_shooting_route
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRegistration,
)
from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.core.range_profiles import RangeProfileKind
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.attack_sequence_state import wound_roll_target_number
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.hazard import HAZARD_ROLL_FAILURE_THRESHOLD
from warhammer40k_core.engine.phases.shooting_model import ShootingDeclarationProposalRequestPayload
from warhammer40k_core.engine.shooting_targets import ShootingTargetCandidatePayload
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.engine.weapon_selection_context import (
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
)

ORDINARY_RANGED_PROFILE_POLICY_ID = "ordinary-bolt-of-change-applied-wounds-v1"
_LORD = "000001120"
_BOLT = f"{_LORD}:bolt-of-change"
_WITCHFIRE = f"{_BOLT}:witchfire"
_FOCUSED_WITCHFIRE = f"{_BOLT}:focused-witchfire"
_BASE_KEYWORDS = {WeaponKeyword.PSYCHIC, WeaponKeyword.IGNORES_COVER}


class RangedProfileGapReason(StrEnum):
    ROUTE = "no_ordinary_declaration"
    OBSERVATION = "unadmitted_observation"
    OFFER = "unsupported_offer"
    SHOOTER = "unsupported_shooter"
    TARGET = "unsupported_target"
    PROFILE = "unsupported_profile"


class RangedProfileGap(CandidateExhaustedError):
    def __init__(self, reason: RangedProfileGapReason) -> None:
        super().__init__(f"Ranged profile candidate gap: {reason.value}.")
        self.reason = reason


class _DeclarationRequest(TypedDict):
    proposal_request: ShootingDeclarationProposalRequestPayload


class _TargetRow(ShootingTargetCandidatePayload):
    weapon_instance_id: str
    weapon_ability_selection_context: WeaponSelectionContextPayload
    required_weapon_ability_selections: list[object]


@dataclass(frozen=True, slots=True)
class RangedProfileAdmission:
    """Actor-visible binding for a reviewed, fixed target and declaration offer."""

    observation_hash: str
    target_unit_instance_id: str


@dataclass(frozen=True, slots=True)
class RangedProfileCandidate:
    profile_id: str
    expected_target_wounds: Fraction
    expected_hazardous_wounds: Fraction
    action: PolicyAction

    @property
    def expected_net_wounds(self) -> Fraction:
        return self.expected_target_wounds - self.expected_hazardous_wounds


def _expected_target_wounds(
    profile: WeaponProfile, *, toughness: int, armour: int, invulnerable: int, wounds: int
) -> Fraction:
    attacks = profile.attack_profile.fixed_attacks
    damage = profile.damage_profile.fixed_damage
    if not all(
        type(stat) is CharacteristicValue and stat.is_numeric
        for stat in (profile.skill, profile.strength, profile.armor_penetration)
    ):
        raise RangedProfileGap(RangedProfileGapReason.PROFILE)
    skill = profile.skill.final
    strength = profile.strength.final
    ap = profile.armor_penetration.final
    keywords = (
        _BASE_KEYWORDS | {WeaponKeyword.HAZARDOUS}
        if profile.profile_id == _FOCUSED_WITCHFIRE
        else _BASE_KEYWORDS
    )
    if (
        profile.range_profile.kind is not RangeProfileKind.DISTANCE
        or profile.abilities
        or set(profile.keywords) != keywords
        or profile.skill_modifiers
        or profile.attack_profile.modifiers
        or profile.damage_profile.modifiers
        or attacks is None
        or not 1 <= attacks <= 24
        or damage is None
        or not 1 <= damage <= 18
        or not 2 <= skill <= 6
        or strength <= 0
        or ap > 0
    ):
        raise RangedProfileGap(RangedProfileGapReason.PROFILE)

    wound = wound_roll_target_number(strength=strength, toughness=toughness)
    # Ignores Cover leaves only the AP-adjusted armour and the invulnerable save.
    save = min(armour - ap, invulnerable)
    unsaved = Fraction((7 - skill) * (7 - wound) * (save - 1), 6**3)
    # Each unsaved attack contributes fixed damage, capped at the one models wounds.
    return sum(
        (
            min(wounds, count * damage)
            * comb(attacks, count)
            * unsaved**count
            * (1 - unsaved) ** (attacks - count)
            for count in range(1, attacks + 1)
        ),
        Fraction(),
    )


def generate_ordinary_ranged_profile_candidates(
    context: PlayerDecisionContext, *, admission: RangedProfileAdmission
) -> tuple[RangedProfileCandidate, ...]:
    """Compare one equipped Bolt of Change against the caller's admitted target."""
    actor = context.route.actor_id
    if context.route != normal_shooting_route(actor):
        raise RangedProfileGap(RangedProfileGapReason.ROUTE)
    if context.observation_hash != admission.observation_hash:
        raise RangedProfileGap(RangedProfileGapReason.OBSERVATION)
    view = context.observation
    request = context.request
    offer = cast(_DeclarationRequest, request["payload"])["proposal_request"]
    weapons = offer["available_weapons"]
    if (
        offer["request_id"] != request["request_id"]
        or offer["actor_id"] != actor
        or offer["active_player_id"] != actor
        or offer["game_id"] != view["game_id"]
        or offer["battle_round"] != view["battle_round"]
        or offer["selected_shooting_type"] != ShootingType.NORMAL.value
        or offer["firing_deck_value"] is not None
        or offer["shooting_weapon_selection_limits"]
        or offer.get("targetless_weapon_candidates")
        or len(offer["target_candidates"]) > MAX_TARGET_ROWS
        or len(weapons) != 2
        or {weapon["weapon_profile_id"] for weapon in weapons} != {_WITCHFIRE, _FOCUSED_WITCHFIRE}
        or len({weapon["weapon_instance_id"] for weapon in weapons}) != 1
        or any(weapon["wargear_id"] != _BOLT for weapon in weapons)
    ):
        raise RangedProfileGap(RangedProfileGapReason.OFFER)

    shooter_id = offer["unit_instance_id"]
    shooter = view["unit_display_by_id"].get(shooter_id)
    if (
        shooter is None
        or shooter["owner_player_id"] != actor
        or shooter["datasheet_id"] != _LORD
        or len(shooter["model_instance_ids"]) != 1
    ):
        raise RangedProfileGap(RangedProfileGapReason.SHOOTER)
    (attacker_id,) = shooter["model_instance_ids"]
    attacker = view["model_display_by_id"].get(attacker_id)
    if (
        attacker is None
        or attacker["unit_instance_id"] != shooter_id
        or attacker["visible_status"] != "visible"
        or "MONSTER" not in attacker["keywords"]
        or attacker["wounds_remaining"] != 18
        or attacker["starting_wounds"] != 18
        or any(weapon["model_instance_id"] != attacker_id for weapon in weapons)
    ):
        raise RangedProfileGap(RangedProfileGapReason.SHOOTER)

    target_id = admission.target_unit_instance_id
    target = view["unit_display_by_id"].get(target_id)
    field = view["battlefield_view"]
    if (
        target is None
        or target["visible_status"] != "visible"
        or target["owner_player_id"] not in view["player_ids"]
        or target["owner_player_id"] == actor
        or target["datasheet_id"] != _LORD
        or len(target["model_instance_ids"]) != 1
        or field is None
    ):
        raise RangedProfileGap(RangedProfileGapReason.TARGET)
    (target_model_id,) = target["model_instance_ids"]
    for unit_id, model_id in ((shooter_id, attacker_id), (target_id, target_model_id)):
        if {
            member_id
            for member_id, entity in field["authoritative"]["models_by_id"].items()
            if entity["state"] == "placed" and entity["rules_unit_instance_id"] == unit_id
        } != {model_id}:
            raise RangedProfileGap(RangedProfileGapReason.OFFER)
    model = view["model_display_by_id"].get(target_model_id)
    if (
        model is None
        or model["visible_status"] != "visible"
        or model["unit_instance_id"] != target_id
    ):
        raise RangedProfileGap(RangedProfileGapReason.TARGET)
    stats = model["current_characteristics"]
    toughness = stats["T"]["final"]
    armour = stats["SV"]["final"]
    invulnerable = stats["InSv"]["final"]
    wounds = model["wounds_remaining"]
    if (
        toughness is None
        or toughness <= 0
        or armour is None
        or not 2 <= armour <= 7
        or invulnerable is None
        or not 2 <= invulnerable <= 7
        or model["starting_wounds"] != 18
        or wounds is None
        or not 1 <= wounds <= 18
        or any(stats[key]["applied_modifier_ids"] for key in ("T", "SV", "InSv", "W"))
    ):
        raise RangedProfileGap(RangedProfileGapReason.TARGET)

    candidates: list[RangedProfileCandidate] = []
    rows = cast(list[_TargetRow], offer["target_candidates"])
    for weapon in weapons:
        profile_id = weapon["weapon_profile_id"]
        matches = [
            row
            for row in rows
            if row["target_unit_instance_id"] == target_id
            and row["weapon_profile_id"] == profile_id
        ]
        if len(matches) != 1:
            raise RangedProfileGap(RangedProfileGapReason.TARGET)
        (row,) = matches
        if (
            not row["is_legal"]
            or row["shooting_types"] != [ShootingType.NORMAL.value]
            or row["attacker_unit_instance_id"] != shooter_id
            or row["observer_model_id"] != attacker_id
            or row["weapon_instance_id"] != weapon["weapon_instance_id"]
            or row["target_visible_model_ids"] != [target_model_id]
            or row["target_in_range_model_ids"] != [target_model_id]
            or row["required_weapon_ability_selections"]
            or row["hit_roll_modifier"]
            or row["targeting_rule_ids"]
        ):
            raise RangedProfileGap(RangedProfileGapReason.OFFER)
        inventory = WeaponSelectionContext.from_payload(row["weapon_ability_selection_context"])
        if (
            inventory.weapon_instance_id != weapon["weapon_instance_id"]
            or inventory.resolved_target_profiles
            or not any(key == target_id for key, _ in inventory.target_profiles)
        ):
            raise RangedProfileGap(RangedProfileGapReason.OFFER)
        profile = inventory.selected_profile(target_id, ())
        if profile.profile_id != profile_id:
            raise RangedProfileGap(RangedProfileGapReason.OFFER)
        proposal = ShootingDeclarationProposal(
            proposal_request_id=offer["request_id"],
            proposal_kind=offer["proposal_kind"],
            player_id=actor,
            battle_round=offer["battle_round"],
            unit_instance_id=shooter_id,
            source_decision_request_id=offer["source_decision_request_id"],
            source_decision_result_id=offer["source_decision_result_id"],
            declarations=(
                WeaponDeclaration(
                    weapon["weapon_instance_id"],
                    attacker_id,
                    _BOLT,
                    profile_id,
                    target_id,
                    ShootingType.NORMAL,
                ),
            ),
            visibility_cache_key=offer["visibility_cache_key"],
        )
        candidates.append(
            RangedProfileCandidate(
                profile_id,
                _expected_target_wounds(
                    profile,
                    toughness=toughness,
                    armour=armour,
                    invulnerable=invulnerable,
                    wounds=wounds,
                ),
                Fraction(3 * HAZARD_ROLL_FAILURE_THRESHOLD, 6)
                if WeaponKeyword.HAZARDOUS in profile.keywords
                else Fraction(),
                context.propose(validate_json_value(proposal.to_payload())),
            )
        )
    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class _OrdinaryRangedProfilePolicy:
    admission: RangedProfileAdmission

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        candidates = generate_ordinary_ranged_profile_candidates(context, admission=self.admission)
        return max(candidates, key=lambda candidate: candidate.expected_net_wounds).action


def ordinary_ranged_profile_registration(
    actor_id: str, *, admission: RangedProfileAdmission, admitted_checkpoint_hash: str
) -> PolicyRegistration:
    """Bind a reviewed baseline to the exact pending session checkpoint.

    Admission requires an audit for contextual hit, wound, save and damage
    modifiers, rerolls, Feel No Pain, and reactions outside the visible offer.
    """
    if type(admitted_checkpoint_hash) is not str:
        raise PolicyError("Ranged profile registration requires a reviewed session checkpoint.")
    return PolicyRegistration(
        normal_shooting_route(actor_id),
        ORDINARY_RANGED_PROFILE_POLICY_ID,
        canonical_json(
            {
                "observation_hash": admission.observation_hash,
                "target_unit_instance_id": admission.target_unit_instance_id,
            }
        ),
        _OrdinaryRangedProfilePolicy(admission),
        required_checkpoint_hash=admitted_checkpoint_hash,
    )
