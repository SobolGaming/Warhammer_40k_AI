"""Delayed secondary Action completion at the retained mission turn boundary."""

from __future__ import annotations

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_battle_shock import (
    action_battle_shock_permission_sources,
)
from warhammer40k_core.engine.mission_action_options import mission_action_for_state
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)


def pending_secondary_mission_actions_at_turn_end(
    state: GameState,
) -> tuple[MissionActionState, ...]:
    return tuple(
        action
        for action in state.mission_action_states
        if action.status is MissionActionStatus.STARTED
        and action.player_id == state.active_player_id
        and action.battle_round_started == state.battle_round
        and action.completion_timing == "turn_end"
        and mission_action_for_state(
            state=state, mission_action_id=action.mission_action_id
        ).mission_kind
        == "secondary"
    )


def resolve_secondary_mission_action_at_turn_end(
    *,
    state: GameState,
    decisions: DecisionController,
    action_id: str,
    turn_end_record: ObjectiveControlRecord,
) -> None:
    if (
        state.current_battle_phase is not BattlePhase.FIGHT
        or turn_end_record.game_id != state.game_id
        or turn_end_record.battle_round != state.battle_round
        or turn_end_record.active_player_id != state.active_player_id
        or turn_end_record.phase != BattlePhase.FIGHT.value
        or turn_end_record.timing is not ObjectiveControlTiming.TURN_END
        or turn_end_record not in state.objective_control_records
    ):
        raise GameLifecycleError("Secondary Action completion requires its retained turn boundary.")
    pending = tuple(
        a for a in pending_secondary_mission_actions_at_turn_end(state) if a.action_id == action_id
    )
    if len(pending) != 1:
        raise GameLifecycleError("Selected secondary Action is not pending at this boundary.")
    action = pending[0]
    source = mission_action_for_state(state=state, mission_action_id=action.mission_action_id)
    # The current delayed secondary family records an objective effect, which is
    # subsequently consumed by the existing secondary scoring owner. Immediate
    # terrain effects keep their existing start-decision resolution path.
    if source.target_policy != "objective_marker" or source.victory_points != 0:
        raise GameLifecycleError("Delayed secondary Action effect policy is unsupported.")
    if (
        source.completion_timing != action.completion_timing
        or source.mission_id != action.mission_id
        or source.scoring_source_id != action.scoring_source_id
        or action.victory_points != source.victory_points
    ):
        raise GameLifecycleError("Secondary Action completion source identity drifted.")
    matches = tuple(r for r in turn_end_record.results if r.objective_id == action.target_id)
    if len(matches) != 1:
        raise GameLifecycleError("Secondary Action target is absent from its objective boundary.")
    completed = (
        action.complete_without_award(
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            completion_timing=source.completion_timing,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            battle_shock_permission_source_ids=action_battle_shock_permission_sources(
                state=state, unit_instance_id=action.unit_instance_id
            ),
        )
        if matches[0].controlled_by_player_id == action.player_id
        else action.fail_completion()
    )
    state.replace_mission_action_state(completed)
    if completed.status is MissionActionStatus.COMPLETED:
        state.record_secondary_objective_cleanse(
            player_id=completed.player_id,
            objective_marker_id=completed.target_id,
            action_id=completed.action_id,
            phase=BattlePhase.FIGHT,
            source_id=source.source_id,
        )
    decisions.event_log.append(
        "mission_action_completed"
        if completed.status is MissionActionStatus.COMPLETED
        else "mission_action_completion_failed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": completed.player_id,
            "phase": BattlePhase.FIGHT.value,
            "mission_action_id": completed.mission_action_id,
            "action_id": completed.action_id,
            "unit_instance_id": completed.unit_instance_id,
            "target_id": completed.target_id,
            "target_policy": source.target_policy,
            "source_id": source.source_id,
            "objective_control_record_id": turn_end_record.record_id,
            "mission_action_state": validate_json_value(completed.to_payload()),
        },
    )


def secondary_action_completions_after_control(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    earlier_action_ids: frozenset[str],
) -> tuple[MissionActionState, ...]:
    """Authenticate delayed completions against uses frozen before mission rules.

    The control snapshot cannot already contain an Action that completes later
    in the same boundary. Its prior-use witness still pins the accepted Action,
    player, physical identity and target. Terminal event history is independently
    authenticated by the shared Action restoration authority.
    """
    from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
        primary_mission_action_prior_use_evidence,
    )
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        mission_action_prior_uses_from_checkpoint,
    )

    prior = mission_action_prior_uses_from_checkpoint(checkpoint)
    result: list[MissionActionState] = []
    for action in state.mission_action_states:
        if (
            action.action_id in earlier_action_ids
            or action.status is not MissionActionStatus.COMPLETED
        ):
            continue
        source = mission_action_for_state(state=state, mission_action_id=action.mission_action_id)
        if source.mission_kind != "secondary" or source.completion_timing != "turn_end":
            continue
        if (action.completed_battle_round, action.player_id, action.completed_phase) != (
            record.battle_round,
            record.active_player_id,
            record.phase,
        ):
            continue
        use = primary_mission_action_prior_use_evidence(state=state, actions=(action,))[0]
        if use not in prior or action.battle_round_started != record.battle_round:
            raise GameLifecycleError(
                "Secondary scoring state evidence drifted from authoritative boundary state: "
                "secondary Action completion is absent from its frozen prior-use authority."
            )
        controls = tuple(r for r in record.results if r.objective_id == action.target_id)
        if len(controls) != 1 or controls[0].controlled_by_player_id != action.player_id:
            raise GameLifecycleError(
                "Secondary scoring state evidence drifted from authoritative boundary state: "
                "secondary Action completion lacks retained objective control."
            )
        result.append(action)
    return tuple(sorted(result, key=lambda a: a.action_id))
