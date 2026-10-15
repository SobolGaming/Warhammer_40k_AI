from __future__ import annotations

from tests.shared.category_migration.phase11e_mission_scoring_cleanup_bindings import (
    GameState,
    ObjectiveMarkerDefinition,
    Pose,
    SecondaryMissionCardState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    UnitPlacement,
    replace,
    resolved_secondary_mission_selection_for_card,
)


def _with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
    start_index: int = 0,
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement_index = start_index + index
        placement = placements[placement_index]
        placements[placement_index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def _place_unit_near_point(
    state: GameState,
    *,
    unit_instance_id: str,
    x_inches: float,
    y_inches: float,
) -> None:
    if state.mission_setup is None or not state.mission_setup.objective_markers:
        raise AssertionError("test state requires an objective marker")
    marker = replace(
        state.mission_setup.objective_markers[0],
        x_inches=x_inches,
        y_inches=y_inches,
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    offsets = tuple(
        (float(index) * 0.75, 0.0) for index in range(len(unit_placement.model_placements))
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit_placement, marker, offsets=offsets)
    )


def _record_active_tactical_secondary(
    state: GameState,
    *,
    secondary_mission_id: str,
) -> None:
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id=secondary_mission_id,
        battle_round=state.battle_round,
        source_result_id=f"phase11e-hold-{secondary_mission_id}",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )


def _secondary_choice(
    *,
    player_id: str,
    mode: SecondaryMissionMode,
    fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=fixed_mission_ids,
    )


__all__: list[str] = []
__all__ += ["GameState", "ObjectiveMarkerDefinition", "Pose", "SecondaryMissionCardState"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "UnitPlacement"]
__all__ += ["_place_unit_near_point", "_record_active_tactical_secondary", "_secondary_choice"]
__all__ += ["_with_model_offsets", "replace", "resolved_secondary_mission_selection_for_card"]
