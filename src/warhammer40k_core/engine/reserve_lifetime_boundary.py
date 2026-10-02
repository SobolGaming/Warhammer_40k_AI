"""Apply Core reserve exemptions and the independent final-turn cleanup."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.reserve_destruction import (
    final_turn_cleanup_policy,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionResult,
    ReserveStatus,
    apply_reserve_destruction_to_battlefield,
)
from warhammer40k_core.engine.rule_model_destruction_unplaced import (
    destroy_unplaced_model_without_reactions,
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


def apply_destruction(state: GameState, *, destruction: ReserveDestructionResult) -> None:
    """Keep logical health, reserve routes and battlefield removals consistent."""
    from warhammer40k_core.engine.primary_destruction_evidence import (
        PrimaryUnattributedDestructionCause,
    )
    from warhammer40k_core.engine.primary_unit_destruction_tracking import (
        record_primary_unit_destructions_for_destroyed_models,
    )

    if state.battlefield_state is None:
        raise GameLifecycleError("Reserve destruction requires battlefield_state.")
    terminal_reserve_states = tuple(
        prior_state
        for prior_state, updated_state in zip(
            state.reserve_states,
            destruction.updated_reserve_states,
            strict=True,
        )
        if prior_state.status is ReserveStatus.IN_RESERVES
        and updated_state.status is ReserveStatus.DESTROYED
    )
    for reserve_state in terminal_reserve_states:
        cargo_state = state.transport_cargo_state_for_transport(reserve_state.unit_instance_id)
        if cargo_state is None:
            if reserve_state.embarked_unit_instance_ids:
                raise GameLifecycleError(
                    "transport_cargo_states unarrived reserve route cargo drift."
                )
            continue
        if cargo_state.embarked_unit_instance_ids != reserve_state.embarked_unit_instance_ids:
            raise GameLifecycleError("transport_cargo_states unarrived reserve route cargo drift.")
    terminal_transport_ids = {
        reserve_state.unit_instance_id for reserve_state in terminal_reserve_states
    }
    updated_battlefield_state = apply_reserve_destruction_to_battlefield(
        battlefield_state=state.battlefield_state,
        destruction=destruction,
    )
    updated_transport_cargo_states = [
        cargo_state
        for cargo_state in state.transport_cargo_states
        if cargo_state.transport_unit_instance_id not in terminal_transport_ids
    ]
    # Reserve deadlines remove models without invoking destroyed-model rules.
    # Previously destroyed members remain part of the removal/lineage record.
    for model_id in destruction.destroyed_model_instance_ids:
        if model_by_id(state=state, model_instance_id=model_id).is_alive:
            destroy_unplaced_model_without_reactions(state=state, model_instance_id=model_id)
    state.battlefield_state = updated_battlefield_state
    state.reserve_states = list(destruction.updated_reserve_states)
    state.transport_cargo_states = updated_transport_cargo_states
    record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=destruction.destroyed_model_instance_ids,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        destroyed_rules_unit_objective_proximity_witness=None,
        unattributed_cause=PrimaryUnattributedDestructionCause.RESERVE_DEADLINE,
        source_mutation_id=(
            f"{destruction.policy.source_id}:round-{destruction.battle_round:02d}:"
            f"{'end-of-battle' if destruction.end_of_battle else 'round-boundary'}"
        ),
        left_battlefield=False,
        source_id=(
            f"{destruction.policy.source_id}:round-{destruction.battle_round:02d}:"
            f"{'end-of-battle' if destruction.end_of_battle else 'round-boundary'}"
        ),
    )
