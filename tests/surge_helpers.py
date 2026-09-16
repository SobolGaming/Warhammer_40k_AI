"""Canonical real models for Surge eligibility and per-model endpoint tests."""

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

SOURCE = "army-alpha:source"
TARGET = "army-beta:enemy"


def surge_lifecycle(*, target_y: float = 30.0) -> GameLifecycle:
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, target_y), model_count=5),
        game_id="order52-surge",
    )
    assert lifecycle.state is not None
    lifecycle.state.battle_phase_index = lifecycle.state.battle_phase_sequence.index(
        BattlePhase.SHOOTING
    )
    return lifecycle


def surge_descriptor(
    *, maximum: float = 3, lifecycle: GameLifecycle | None = None
) -> TriggeredMovementDescriptor:
    event_id = "surge-source-event"
    if lifecycle is not None:
        assert lifecycle.state is not None
        state = lifecycle.state
        event_id = lifecycle.decision_controller.event_log.append(
            "source_rule_triggered",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": "shooting",
                "active_player_id": state.active_player_id,
                "source_rule_id": "test:source-backed-surge",
            },
        ).event_id
    return TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.SURGE,
        source_rule_id="test:source-backed-surge",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.SHOOTING,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="just_after_enemy_unit_has_shot",
            source_event_id=event_id,
        ),
        max_distance_inches=maximum,
    )


def surge_path(
    lifecycle: GameLifecycle,
    distances: tuple[float, ...],
    *,
    unit_id: str = SOURCE,
) -> PathWitness:
    state = lifecycle.state
    assert state is not None
    from warhammer40k_core.engine.triggered_movement_physical_authority import (
        triggered_movement_placement,
    )

    placement = triggered_movement_placement(
        scenario=battlefield_scenario_for_state(state=state),
        unit_instance_id=unit_id,
    )
    return PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (model.pose, Pose.at(model.pose.position.x, model.pose.position.y + distance)),
            )
            for model, distance in zip(placement.model_placements, distances, strict=True)
        )
    )
