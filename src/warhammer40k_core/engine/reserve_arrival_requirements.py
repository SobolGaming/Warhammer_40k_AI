from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    battlefield_placement_kind_from_token,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.reserves import ReserveDestructionTimingPolicy, ReserveState


def placement_kinds_for_reserve_state(
    reserve_state: ReserveState,
    *,
    all_components_have_deep_strike: bool,
) -> tuple[BattlefieldPlacementKind, ...]:
    from warhammer40k_core.engine.reserves import ReserveKind, ReserveState

    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("Reserve arrival placement kinds require ReserveState.")
    if type(all_components_have_deep_strike) is not bool:
        raise GameLifecycleError("Reserve arrival Deep Strike authority must be a bool.")
    if reserve_state.required_arrival_placement_kind is not None:
        return (
            battlefield_placement_kind_from_token(reserve_state.required_arrival_placement_kind),
        )
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        kinds = [BattlefieldPlacementKind.STRATEGIC_RESERVES]
        if all_components_have_deep_strike:
            kinds.append(BattlefieldPlacementKind.DEEP_STRIKE)
        return tuple(sorted(kinds, key=lambda kind: kind.value))
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return (BattlefieldPlacementKind.DEEP_STRIKE,)
    return (BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,)


def proposal_kind_for_reserve_state(reserve_state: ReserveState) -> ProposalKind:
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.reserves import ReserveKind, ReserveState

    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("Reserve arrival proposal kind requires ReserveState.")
    if (
        reserve_state.required_arrival_placement_kind == BattlefieldPlacementKind.DEEP_STRIKE.value
        or reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE
    ):
        return ProposalKind.DEEP_STRIKE
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        return ProposalKind.STRATEGIC_RESERVES
    return ProposalKind.REINFORCEMENT


def source_rule_id_for_placement_kind(
    placement_kind: BattlefieldPlacementKind,
) -> str:
    resolved_kind = battlefield_placement_kind_from_token(placement_kind)
    if resolved_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES:
        return "strategic_reserves"
    if resolved_kind is BattlefieldPlacementKind.DEEP_STRIKE:
        return "deep_strike"
    return "reserves"


def kind_token(
    value: BattlefieldPlacementKind | str | None,
) -> str | None:
    if value is None:
        return None
    return battlefield_placement_kind_from_token(value).value


def validate_fields(
    *,
    battle_round: int | None,
    phase: str | None,
    source_rule_id: str | None,
    placement_kind: str | None,
) -> None:
    required_arrival_fields = (battle_round, phase, source_rule_id)
    if any(value is None for value in required_arrival_fields) and any(
        value is not None for value in required_arrival_fields
    ):
        raise GameLifecycleError("ReserveState required arrival fields must be complete.")
    if placement_kind is not None and not all(
        value is not None for value in required_arrival_fields
    ):
        raise GameLifecycleError(
            "ReserveState required arrival placement kind requires required arrival."
        )


def validate_status_fields(state: ReserveState) -> None:
    from warhammer40k_core.engine.reserves import (
        LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS,
        ReserveStatus,
    )

    validate_fields(
        battle_round=state.required_arrival_battle_round,
        phase=state.required_arrival_phase,
        source_rule_id=state.required_arrival_source_rule_id,
        placement_kind=state.required_arrival_placement_kind,
    )
    if state.status is ReserveStatus.IN_RESERVES:
        if state.arrived_battle_round is not None or state.arrived_phase is not None:
            raise GameLifecycleError("Unarrived ReserveState must not have arrival fields.")
        if state.destroyed_battle_round is not None:
            raise GameLifecycleError("Unarrived ReserveState must not have destruction fields.")
    if state.status is ReserveStatus.ARRIVED:
        if state.arrived_battle_round is None or state.arrived_phase is None:
            raise GameLifecycleError("Arrived ReserveState requires arrival fields.")
        if state.destroyed_battle_round is not None:
            raise GameLifecycleError("Arrived ReserveState must not have destruction fields.")
        if state.has_required_arrival and (
            state.arrived_battle_round != state.required_arrival_battle_round
            or state.arrived_phase != state.required_arrival_phase
        ):
            raise GameLifecycleError("Arrived ReserveState must satisfy required arrival.")
    if state.status is ReserveStatus.DESTROYED:
        if state.destroyed_battle_round is None:
            raise GameLifecycleError("Destroyed ReserveState requires destroyed_battle_round.")
        if state.post_arrival_restrictions:
            raise GameLifecycleError("Destroyed ReserveState must not keep restrictions.")
    if state.post_arrival_restrictions and state.restriction_battle_round is None:
        raise GameLifecycleError("ReserveState restrictions require restriction_battle_round.")
    if (
        state.large_model_exception_used
        and state.post_arrival_restrictions
        and set(state.post_arrival_restrictions) != set(LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS)
    ):
        raise GameLifecycleError(
            "Large-model ReserveState must record all post-arrival restrictions."
        )


def reposition_destruction_policy(
    *,
    mission_setup: MissionSetup | None,
    destruction_deadline_policy: object,
) -> ReserveDestructionTimingPolicy:
    from warhammer40k_core.engine.missions import (
        mission_scoring_policies_from_setup,
        reserve_destruction_policy_from_scoring_policy,
    )
    from warhammer40k_core.engine.reserves import ReserveDestructionTimingPolicy

    if destruction_deadline_policy is None:
        if mission_setup is None:
            return ReserveDestructionTimingPolicy.core_rules_default()
        return reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(mission_setup).common_policy
        )
    if type(destruction_deadline_policy) is not ReserveDestructionTimingPolicy:
        raise GameLifecycleError("Repositioned unit destruction_deadline_policy must be a policy.")
    return destruction_deadline_policy
