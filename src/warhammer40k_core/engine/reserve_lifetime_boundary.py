"""Apply Core reserve exemptions and the independent final-turn cleanup."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.reserve_destruction import (
    final_turn_cleanup_policy,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def reserve_round_deadline_exempt_ids(state: GameState) -> frozenset[str]:
    """Read accepted ingress and actual battlefield departures, never just origin labels.

    A newly created replacement may enter reserves during battle without being
    repositioned. Cargo on a carrier is destroyed only through that carrier's
    reserve route; an ingressed or repositioned carrier therefore protects it.
    """
    ingress_ids = {row.unit_instance_id for row in state.phase_movement_history if row.is_ingress}
    ingress_models = {
        mid
        for row in state.phase_movement_history
        if row.is_ingress
        for mid in row.model_instance_ids
    }
    departures = tuple(
        row
        for row in state.primary_battlefield_departure_states
        if row.removal_kind is BattlefieldRemovalKind.INTO_RESERVES
    )
    repositioned_ids = {row.rules_unit_instance_id for row in departures}
    repositioned_models = {mid for row in departures for mid in row.removed_model_instance_ids}
    exempt: set[str] = set()
    for reserve in state.reserve_states:
        view = rules_unit_view_by_id(state=state, unit_instance_id=reserve.unit_instance_id)
        models = {model.model_instance_id for model in view.alive_models()}
        if view.unit_instance_id in ingress_ids | repositioned_ids or models.intersection(
            ingress_models | repositioned_models
        ):
            exempt.add(reserve.unit_instance_id)
    return frozenset(exempt)


def resolve_boundary(state: GameState, *, end_of_battle: bool) -> None:
    if state.mission_setup is None or state.battlefield_state is None:
        raise GameLifecycleError("Reserve destruction requires mission and battlefield authority.")
    policy = (
        final_turn_cleanup_policy()
        if end_of_battle
        else reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(state.mission_setup).common_policy
        )
    )
    destruction = resolve_unarrived_reserve_destruction(
        reserve_states=tuple(state.reserve_states),
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
        policy=policy,
        battle_round=state.battle_round,
        end_of_battle=end_of_battle,
        exempt_unit_instance_ids=(
            frozenset() if end_of_battle else reserve_round_deadline_exempt_ids(state)
        ),
    )
    if destruction.destroyed_model_instance_ids:
        state._apply_unarrived_reserve_destruction(destruction=destruction)


def validate_final_turn_destruction(state: GameState) -> None:
    """A saved terminal flag cannot authorize cleanup before the actual final turn."""
    terminal = tuple(row for row in state.reserve_states if row.destroyed_at_end_of_battle)
    if not terminal:
        return
    if state.mission_setup is None or state.stage is not GameLifecycleStage.COMPLETE:
        raise GameLifecycleError("Final-turn reserve destruction requires a completed battle.")
    final_round = mission_scoring_policies_from_setup(
        state.mission_setup
    ).common_policy.game_length_battle_rounds
    if state.battle_round != final_round or any(
        row.destroyed_battle_round != final_round for row in terminal
    ):
        raise GameLifecycleError("Final-turn reserve destruction round drift.")
