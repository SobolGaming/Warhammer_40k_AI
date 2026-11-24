"""Opt-in focused volleys from an actor's ordinary shooting declaration offer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyRegistration,
    PolicyRoute,
    payload_digest,
)
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phases.shooting_model import ShootingDeclarationProposalRequestPayload
from warhammer40k_core.engine.shooting_targets import ShootingTargetCandidatePayload
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_declaration import (
    SHOOTING_DECLARATION_PROPOSAL_KIND,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingDeclarationProposal,
    WeaponDeclaration,
)

NORMAL_SHOOTING_POLICY_ID = "ordinary-normal-shooting-focus-v1"
MAX_TARGET_ROWS = 256
MAX_TARGET_UNITS = 32


class NormalShootingGapReason(StrEnum):
    NO_ORDINARY_DECLARATION = "no_ordinary_declaration"
    UNSUPPORTED_OFFER = "unsupported_offer"
    CANDIDATE_LIMIT = "candidate_limit"
    NO_FOCUSED_VOLLEY = "no_focused_volley"


class NormalShootingGap(CandidateExhaustedError):
    def __init__(self, reason: NormalShootingGapReason) -> None:
        super().__init__(f"Normal Shooting candidate gap: {reason.value}.")
        self.reason = reason


class _TargetRow(ShootingTargetCandidatePayload):
    weapon_instance_id: str
    required_weapon_ability_selections: list[object]


class _DeclarationRequest(TypedDict):
    proposal_request: ShootingDeclarationProposalRequestPayload


@dataclass(frozen=True, slots=True)
class NormalShootingCandidate:
    candidate_id: str
    target_unit_instance_id: str | None
    declaration_count: int
    action: PolicyAction


def normal_shooting_route(actor_id: str) -> PolicyRoute:
    return PolicyRoute(
        actor_id,
        SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        "battle",
        None,
        "shooting",
        SHOOTING_DECLARATION_PROPOSAL_KIND,
    )


def generate_normal_shooting_candidates(
    context: PlayerDecisionContext,
) -> tuple[NormalShootingCandidate, ...]:
    """Emit one focused volley per target and the ordinary empty declaration."""
    actor = context.route.actor_id
    if context.route != normal_shooting_route(actor):
        raise NormalShootingGap(NormalShootingGapReason.NO_ORDINARY_DECLARATION)
    request = context.request
    offer = cast(_DeclarationRequest, request["payload"])["proposal_request"]
    if (
        offer["actor_id"] != actor
        or offer["active_player_id"] != actor
        or offer["selected_shooting_type"] != ShootingType.NORMAL.value
    ):
        raise NormalShootingGap(NormalShootingGapReason.NO_ORDINARY_DECLARATION)
    weapons = offer["available_weapons"]
    rows = offer["target_candidates"]
    if len(rows) > MAX_TARGET_ROWS:
        raise NormalShootingGap(NormalShootingGapReason.CANDIDATE_LIMIT)
    if (
        offer["firing_deck_value"] is not None
        or offer["shooting_weapon_selection_limits"]
        or offer.get("targetless_weapon_candidates")
        or len({weapon["weapon_instance_id"] for weapon in weapons}) != len(weapons)
        or len({weapon["model_instance_id"] for weapon in weapons}) != len(weapons)
    ):
        raise NormalShootingGap(NormalShootingGapReason.UNSUPPORTED_OFFER)

    # Preserve the native equipment order within each submission. Declaration
    # order is part of the attack sequence.
    weapon_order = {weapon["weapon_instance_id"]: i for i, weapon in enumerate(weapons)}
    targets: dict[str, dict[int, WeaponDeclaration]] = {}
    for row in cast(list[_TargetRow], rows):
        if not row["is_legal"] or ShootingType.NORMAL.value not in row["shooting_types"]:
            continue
        target_id = row["target_unit_instance_id"]
        index = weapon_order.get(row["weapon_instance_id"])
        if index is None:
            raise NormalShootingGap(NormalShootingGapReason.UNSUPPORTED_OFFER)
        weapon = weapons[index]
        declarations = targets.setdefault(target_id, {})
        if (
            row["attacker_unit_instance_id"] != offer["unit_instance_id"]
            or row["observer_model_id"] != weapon["model_instance_id"]
            or row["weapon_profile_id"] != weapon["weapon_profile_id"]
            or row["required_weapon_ability_selections"]
            or index in declarations
        ):
            raise NormalShootingGap(NormalShootingGapReason.UNSUPPORTED_OFFER)
        declarations[index] = WeaponDeclaration(
            weapon["weapon_instance_id"],
            weapon["model_instance_id"],
            weapon["wargear_id"],
            weapon["weapon_profile_id"],
            target_id,
            ShootingType.NORMAL,
        )
    if len(targets) > MAX_TARGET_UNITS:
        raise NormalShootingGap(NormalShootingGapReason.CANDIDATE_LIMIT)

    request_id = request["request_id"]
    observation_hash = context.observation_hash

    def candidate(
        target_id: str | None, declarations: tuple[WeaponDeclaration, ...]
    ) -> NormalShootingCandidate:
        proposal = ShootingDeclarationProposal(
            proposal_request_id=offer["request_id"],
            proposal_kind=SHOOTING_DECLARATION_PROPOSAL_KIND,
            player_id=actor,
            battle_round=offer["battle_round"],
            unit_instance_id=offer["unit_instance_id"],
            source_decision_request_id=offer["source_decision_request_id"],
            source_decision_result_id=offer["source_decision_result_id"],
            declarations=declarations,
            visibility_cache_key=offer["visibility_cache_key"],
        ).to_payload()
        candidate_id = payload_digest(
            [NORMAL_SHOOTING_POLICY_ID, offer["unit_instance_id"], proposal["declarations"]]
        )
        return NormalShootingCandidate(
            candidate_id,
            target_id,
            len(declarations),
            PolicyAction(actor, request_id, observation_hash, None, canonical_json(proposal)),
        )

    return (
        *(
            candidate(target_id, tuple(declarations[index] for index in sorted(declarations)))
            for target_id, declarations in sorted(targets.items())
        ),
        candidate(None, ()),
    )


def rank_normal_shooting_candidates(
    candidates: tuple[NormalShootingCandidate, ...],
) -> tuple[NormalShootingCandidate, ...]:
    """Rank by number of declarable weapons with stable target-ID ties."""
    return tuple(
        sorted(
            candidates, key=lambda row: (-row.declaration_count, row.target_unit_instance_id or "")
        )
    )


class _NormalShootingPolicy:
    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        ranked = rank_normal_shooting_candidates(generate_normal_shooting_candidates(context))
        if ranked[0].target_unit_instance_id is None:
            raise NormalShootingGap(NormalShootingGapReason.NO_FOCUSED_VOLLEY)
        return ranked[0].action


def normal_shooting_registration(actor_id: str) -> PolicyRegistration:
    return PolicyRegistration(
        normal_shooting_route(actor_id),
        NORMAL_SHOOTING_POLICY_ID,
        '{"rank":"declaration-count-descending,target-id-ascending"}',
        _NormalShootingPolicy(),
    )
