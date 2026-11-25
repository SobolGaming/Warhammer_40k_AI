"""Opt-in applied-wound ranking for admitted, fixed-A melee declaration offers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import TypedDict, cast

from warhammer40k_core.adapters.projection import GameViewPayload, ModelDisplayPayload
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRegistration,
    PolicyRoute,
)
from warhammer40k_core.core.range_profiles import RangeProfileKind
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.attack_sequence_state import wound_roll_target_number
from warhammer40k_core.engine.decision_request import DecisionRequest, parameterized_decision_option
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.fight_resolution import (
    MELEE_DECLARATION_PROPOSAL_KIND,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
)
from warhammer40k_core.engine.melee_weapon_commitment import COMMITMENT_KEY
from warhammer40k_core.engine.weapon_selection_context import (
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
)

ORDINARY_MELEE_PROFILE_POLICY_ID = "ordinary-melee-applied-wounds-v2"
_MAX_PROFILES = 8
_MAX_TARGET_MODELS = 10
_MAX_ATTACKS = 24
_MAX_MODEL_WOUNDS = 32


class MeleeProfileGapReason(StrEnum):
    ROUTE = "no_melee_declaration"
    OBSERVATION = "unadmitted_observation"
    OFFER = "unsupported_offer"
    TARGET = "unsupported_target"
    PROFILE = "unsupported_profile"


class MeleeProfileGap(CandidateExhaustedError):
    def __init__(self, reason: MeleeProfileGapReason) -> None:
        super().__init__(f"Melee profile candidate gap: {reason.value}.")
        self.reason = reason


class _OfferedWeapon(TypedDict):
    model_instance_id: str
    weapon_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    engaged_target_unit_instance_ids: list[str]
    is_extra_attacks: bool
    required_weapon_ability_selections: list[object]
    weapon_ability_selection_context: WeaponSelectionContextPayload | None


@dataclass(frozen=True, slots=True)
class _Defense:
    toughness: int
    armour: int
    invulnerable: int
    starting_wounds: int


@dataclass(frozen=True, slots=True)
class MeleeProfileAdmission:
    """Identities read from the same reviewed actor-visible offer."""

    observation_hash: str
    weapon_selection_source_id: str


@dataclass(frozen=True, slots=True)
class MeleeProfileCandidate:
    profile_id: str
    expected_applied_wounds: Fraction
    action: PolicyAction


def ordinary_melee_profile_route(actor_id: str) -> PolicyRoute:
    return PolicyRoute(
        actor_id,
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        "battle",
        None,
        "fight",
        MELEE_DECLARATION_PROPOSAL_KIND,
    )


def _target_defense(model: ModelDisplayPayload) -> _Defense:
    stats = model["current_characteristics"]
    toughness = stats["T"]["final"]
    armour = stats["SV"]["final"]
    invulnerable = stats["InSv"]["final"]
    starting = model["starting_wounds"]
    if (
        model["visible_status"] != "visible"
        or toughness is None
        or toughness <= 0
        or armour is None
        or not 2 <= armour <= 7
        or invulnerable is None
        or not 0 <= invulnerable <= 7
        or starting is None
        or not 1 <= starting <= _MAX_MODEL_WOUNDS
        or any(stats[key]["applied_modifier_ids"] for key in ("T", "SV", "InSv", "W"))
    ):
        raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
    return _Defense(toughness, armour, invulnerable, starting)


def _target_wounds(
    view: GameViewPayload, actor_id: str, target_id: str
) -> tuple[_Defense, tuple[int, ...]]:
    target = view["unit_display_by_id"].get(target_id)
    field = view["battlefield_view"]
    if (
        target is None
        or target["owner_player_id"] not in view["player_ids"]
        or target["owner_player_id"] == actor_id
        or target["visible_status"] != "visible"
        or field is None
        or not 1 <= len(target["model_instance_ids"]) <= _MAX_TARGET_MODELS
    ):
        raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
    entities = field["authoritative"]["models_by_id"]
    members = {
        model_id
        for model_id, entity in entities.items()
        if entity["state"] == "placed" and entity["rules_unit_instance_id"] == target_id
    }
    if not members or not members <= set(target["model_instance_ids"]):
        raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
    defenses: set[_Defense] = set()
    wounds: list[int] = []
    for model_id in target["model_instance_ids"]:
        model = view["model_display_by_id"].get(model_id)
        if model is None or model["unit_instance_id"] != target_id:
            raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
        remaining = model["wounds_remaining"]
        if remaining == 0 and model_id not in members:
            continue
        defense = _target_defense(model)
        if (
            model_id not in members
            or remaining is None
            or not 1 <= remaining <= defense.starting_wounds
        ):
            raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
        defenses.add(defense)
        wounds.append(remaining)
    if len(defenses) != 1:
        raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
    (defense,) = defenses
    if sum(remaining < defense.starting_wounds for remaining in wounds) > 1:
        raise MeleeProfileGap(MeleeProfileGapReason.TARGET)
    return defense, tuple(sorted(wounds))


def _expected_applied_wounds(
    profile: WeaponProfile, defense: _Defense, wounds: tuple[int, ...]
) -> Fraction:
    attacks = profile.attack_profile.fixed_attacks
    skill = profile.skill.final
    strength = profile.strength.final
    ap = profile.armor_penetration.final
    if (
        profile.range_profile.kind is not RangeProfileKind.MELEE
        or profile.abilities
        or profile.keywords
        or attacks is None
        or not 1 <= attacks <= _MAX_ATTACKS
        or not 2 <= skill <= 6
        or strength <= 0
        or ap > 0
    ):
        raise MeleeProfileGap(MeleeProfileGapReason.PROFILE)

    damage = profile.damage_profile
    damage_faces: tuple[int, ...]
    if damage.fixed_damage is not None:
        damage_faces = (damage.fixed_damage,)
    else:
        expression = damage.dice_expression
        if expression is None or expression.quantity != 1 or expression.sides not in (3, 6):
            raise MeleeProfileGap(MeleeProfileGapReason.PROFILE)
        damage_faces = tuple(face + expression.modifier for face in range(1, expression.sides + 1))
    if not 1 <= min(damage_faces) <= max(damage_faces) <= _MAX_MODEL_WOUNDS:
        raise MeleeProfileGap(MeleeProfileGapReason.PROFILE)

    wound = wound_roll_target_number(strength=strength, toughness=defense.toughness)
    save = min(defense.armour - ap, defense.invulnerable or 7, 7)
    unsaved = Fraction((7 - skill) * (7 - wound) * (save - 1), 6**3)
    per_face = unsaved / len(damage_faces)
    states = {sum(wounds): Fraction(1)}
    # Each total has a unique wounded-first allocation when later models are full.
    # An ordinary attack can only remove wounds from the currently allocated model.
    for _ in range(attacks):
        next_states: defaultdict[int, Fraction] = defaultdict(Fraction)
        for remaining, chance in states.items():
            if not remaining:
                next_states[remaining] += chance
                continue
            next_states[remaining] += chance * (1 - unsaved)
            allocated = (remaining - 1) % defense.starting_wounds + 1
            for damage_face in damage_faces:
                next_states[remaining - min(allocated, damage_face)] += chance * per_face
        states = dict(next_states)
    expected_remaining = sum(
        (remaining * chance for remaining, chance in states.items()), Fraction()
    )
    return sum(wounds) - expected_remaining


def generate_ordinary_melee_profile_candidates(
    context: PlayerDecisionContext, *, admission: MeleeProfileAdmission
) -> tuple[MeleeProfileCandidate, ...]:
    """Compare the native alternatives of one previously qualified ordinary offer.

    The actor-visible binding scopes candidate generation. Automated dispatch
    also requires the trusted runner to match the reviewed session checkpoint.
    """
    actor = context.route.actor_id
    if context.route != ordinary_melee_profile_route(actor):
        raise MeleeProfileGap(MeleeProfileGapReason.ROUTE)
    if context.observation_hash != admission.observation_hash:
        raise MeleeProfileGap(MeleeProfileGapReason.OBSERVATION)
    request = context.request
    payload = request["payload"]
    if not isinstance(payload, dict) or COMMITMENT_KEY in payload:
        raise MeleeProfileGap(MeleeProfileGapReason.OFFER)
    offer = MeleeDeclarationProposalRequest.from_decision_request(
        DecisionRequest(
            request["request_id"],
            request["decision_type"],
            actor,
            payload,
            (parameterized_decision_option(),),
        )
    )
    view = context.observation
    unit = view["unit_display_by_id"].get(offer.unit_instance_id)
    if (
        offer.request_id != request["request_id"]
        or offer.actor_id != actor
        or offer.game_id != view["game_id"]
        or offer.battle_round != view["battle_round"]
        or unit is None
        or unit["owner_player_id"] != actor
        or len(unit["model_instance_ids"]) != 1
        or len(offer.target_unit_instance_ids) != 1
        or not 2 <= len(offer.available_weapons) <= _MAX_PROFILES
    ):
        raise MeleeProfileGap(MeleeProfileGapReason.OFFER)

    (attacker_id,) = unit["model_instance_ids"]
    (target_id,) = offer.target_unit_instance_ids
    defense, wounds = _target_wounds(view, actor, target_id)
    weapons = cast(tuple[_OfferedWeapon, ...], offer.available_weapons)
    if len({(row["weapon_instance_id"], row["wargear_id"]) for row in weapons}) != 1 or len(
        {row["weapon_profile_id"] for row in weapons}
    ) != len(weapons):
        raise MeleeProfileGap(MeleeProfileGapReason.OFFER)

    candidates: list[MeleeProfileCandidate] = []
    for row in weapons:
        selection = row["weapon_ability_selection_context"]
        if (
            row["model_instance_id"] != attacker_id
            or row["engaged_target_unit_instance_ids"] != [target_id]
            or row["is_extra_attacks"]
            or row["required_weapon_ability_selections"]
            or selection is None
        ):
            raise MeleeProfileGap(MeleeProfileGapReason.OFFER)
        inventory = WeaponSelectionContext.from_payload(selection)
        if (
            inventory.source_request_id != admission.weapon_selection_source_id
            or inventory.weapon_instance_id != row["weapon_instance_id"]
            or inventory.resolved_target_profiles
            or tuple(target for target, _profile in inventory.target_profiles) != (target_id,)
        ):
            raise MeleeProfileGap(MeleeProfileGapReason.OFFER)
        profile = inventory.raw_profile_for_target(target_id)
        if profile.profile_id != row["weapon_profile_id"]:
            raise MeleeProfileGap(MeleeProfileGapReason.OFFER)
        expected = _expected_applied_wounds(profile, defense, wounds)
        declaration = MeleeWeaponDeclaration(
            attacker_model_instance_id=attacker_id,
            weapon_instance_id=row["weapon_instance_id"],
            wargear_id=row["wargear_id"],
            weapon_profile_id=profile.profile_id,
            target_allocations=(MeleeTargetAllocation(target_id),),
        )
        proposal = MeleeDeclarationProposal(
            offer.request_id,
            offer.proposal_kind,
            actor,
            offer.battle_round,
            offer.unit_instance_id,
            offer.source_decision_request_id,
            offer.source_decision_result_id,
            (declaration,),
        )
        candidates.append(
            MeleeProfileCandidate(
                profile.profile_id,
                expected,
                context.propose(validate_json_value(proposal.to_payload())),
            )
        )
    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class _OrdinaryMeleeProfilePolicy:
    admission: MeleeProfileAdmission

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        candidates = generate_ordinary_melee_profile_candidates(context, admission=self.admission)
        return max(candidates, key=lambda candidate: candidate.expected_applied_wounds).action


def ordinary_melee_profile_registration(
    actor_id: str, *, admission: MeleeProfileAdmission, admitted_checkpoint_hash: str
) -> PolicyRegistration:
    """Register a comparison qualified by a trusted operator at the pending offer."""
    if type(admitted_checkpoint_hash) is not str:
        raise PolicyError("Melee profile registration requires a reviewed session checkpoint.")
    return PolicyRegistration(
        ordinary_melee_profile_route(actor_id),
        ORDINARY_MELEE_PROFILE_POLICY_ID,
        canonical_json(
            {
                "observation_hash": admission.observation_hash,
                "weapon_selection_source_id": admission.weapon_selection_source_id,
            }
        ),
        _OrdinaryMeleeProfilePolicy(admission),
        required_checkpoint_hash=admitted_checkpoint_hash,
    )
