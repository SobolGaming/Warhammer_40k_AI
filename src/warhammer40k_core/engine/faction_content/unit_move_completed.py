from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
    catalog_movement_target_pair_move_completed_bindings,
)
from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_runtime import (
    catalog_unit_move_completed_battle_shock_hook_bindings,
)
from warhammer40k_core.engine.catalog_unit_move_completed_mortal_wounds_runtime import (
    catalog_unit_move_completed_mortal_wound_hook_bindings,
)
from warhammer40k_core.engine.move_completion_rule_hooks import (
    MoveCompletionRuleBinding,
    MoveCompletionRuleRegistry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundHookBinding,
    UnitMoveCompletedMortalWoundHookRegistry,
)


def move_completion_rule_registry() -> MoveCompletionRuleRegistry:
    from warhammer40k_core.engine.cult_ambush import SOURCE_RULE_ID
    from warhammer40k_core.engine.cult_ambush_marker_capture import (
        cult_marker_participants_at_trigger,
    )
    from warhammer40k_core.engine.mission_action_policies import primary_mission_state_rule_for_id
    from warhammer40k_core.engine.surveil_move_capture import surveil_participants_at_trigger

    return MoveCompletionRuleRegistry(
        (
            MoveCompletionRuleBinding(
                hook_id=f"{SOURCE_RULE_ID}:marker-removal",
                source_rule_id=SOURCE_RULE_ID,
                candidates=_cult_marker_candidates,
                participants_at_trigger=cult_marker_participants_at_trigger,
                resume=_resume_cult_marker,
            ),
            MoveCompletionRuleBinding(
                hook_id="primary:surveil:move-marker-removal",
                source_rule_id=primary_mission_state_rule_for_id(
                    "surveil-remove-operation-markers-after-move"
                ).source_id,
                candidates=_surveil_marker_candidates,
                participants_at_trigger=surveil_participants_at_trigger,
                resume=_resume_surveil_marker,
            ),
        )
    )


def _resume_cult_marker(
    context: UnitMoveCompletedContext, participant: SequencingParticipant
) -> TimingRuleCandidate | None:
    from warhammer40k_core.engine.cult_ambush_marker_removal import resume_cult_marker_candidate

    if context.decisions is None:
        raise GameLifecycleError("Cult marker continuation requires decisions.")
    return resume_cult_marker_candidate(
        state=context.state,
        decisions=context.decisions,
        completed_phase=context.completed_phase,
        trigger_event_id=context.trigger_event_id,
        participant=participant,
    )


def _resume_surveil_marker(
    context: UnitMoveCompletedContext, participant: SequencingParticipant
) -> TimingRuleCandidate | None:
    from warhammer40k_core.engine.primary_mission_state_runtime import (
        resume_surveil_marker_candidate,
    )

    if context.decisions is None:
        raise GameLifecycleError("Surveil marker continuation requires decisions.")
    if participant.player_id != context.triggering_player_id:
        raise GameLifecycleError("Surveil marker continuation owner differs from its mover.")
    return resume_surveil_marker_candidate(
        state=context.state,
        decisions=context.decisions,
        completed_phase=context.completed_phase,
        trigger_event_id=context.trigger_event_id,
        participant=participant,
    )


def _cult_marker_candidates(context: UnitMoveCompletedContext) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.cult_ambush_marker_removal import (
        cult_ambush_marker_removal_candidates,
    )

    if context.decisions is None:
        raise GameLifecycleError("Cult Ambush marker rule requires decisions.")
    return cult_ambush_marker_removal_candidates(
        state=context.state,
        decisions=context.decisions,
        completed_phase=context.completed_phase,
        trigger_event_id=context.trigger_event_id,
    )


def _surveil_marker_candidates(
    context: UnitMoveCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.primary_mission_state_runtime import (
        surveil_move_marker_candidates,
    )

    if context.decisions is None:
        raise GameLifecycleError("Surveil marker rule requires decisions.")
    return surveil_move_marker_candidates(
        state=context.state,
        decisions=context.decisions,
        completed_phase=context.completed_phase,
        runtime_modifier_registry=context.runtime_modifier_registry,
        trigger_event_id=context.trigger_event_id,
    )


class UnitMoveCompletedContribution(Protocol):
    @property
    def unit_move_completed_mortal_wound_hook_bindings(
        self,
    ) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]: ...


def unit_move_completed_mortal_wound_hook_registry(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    contributions: tuple[UnitMoveCompletedContribution, ...],
) -> UnitMoveCompletedMortalWoundHookRegistry:
    return UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        (
            *catalog_unit_move_completed_mortal_wound_hook_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=armies,
            ),
            *catalog_movement_target_pair_move_completed_bindings(
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=armies,
            ),
            *_unit_move_completed_mortal_wound_contribution_bindings(contributions),
        )
    )


def catalog_unit_move_completed_battle_shock_hook_registry(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> UnitMoveCompletedBattleShockHookRegistry:
    return UnitMoveCompletedBattleShockHookRegistry.from_bindings(
        catalog_unit_move_completed_battle_shock_hook_bindings(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        )
    )


def _unit_move_completed_mortal_wound_contribution_bindings(
    contributions: tuple[UnitMoveCompletedContribution, ...],
) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
    return tuple(
        binding
        for contribution in contributions
        for binding in contribution.unit_move_completed_mortal_wound_hook_bindings
    )
