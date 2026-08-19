from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary,
    enemy_unit_ids_in_player_deployment_zone_from_battlefield,
)
from warhammer40k_core.engine.secondary_mission_selection import (
    SecondaryMissionSelection,
    secondary_mission_selection_from_json,
)
from warhammer40k_core.engine.secondary_scoring_conditions import SecondaryScoringConditionContext
from warhammer40k_core.engine.secondary_scoring_occupancy import (
    build_secondary_battlefield_occupancy,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.scoring import SecondaryMissionCardState


def secondary_mission_selection_for_card(
    card_state: SecondaryMissionCardState,
) -> SecondaryMissionSelection | None:
    return secondary_mission_selection_from_json(card_state.selection_payload)


def secondary_scoring_condition_context_from_state(
    *,
    state: GameState,
    player_id: str,
    record: ObjectiveControlRecord,
    selection: SecondaryMissionSelection | None,
) -> SecondaryScoringConditionContext:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Secondary scoring context requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Secondary scoring context requires an ObjectiveControlRecord.")
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Secondary scoring context requires MissionSetup.")
    occupancy = None
    authorities = tuple(
        authority
        for authority in state.objective_control_record_authorities
        if authority.objective_control_record_id == record.record_id
    )
    if state.battlefield_state is not None:
        occupancy = build_secondary_battlefield_occupancy(
            state=state,
            player_id=player_id,
            record=record,
            selection=selection,
            model_placements=_model_placements_for_secondary_scoring(
                state=state,
                record=record,
                authorities=authorities,
            ),
        )
    player_zones = tuple(
        zone for zone in mission_setup.deployment_zones if zone.player_id == player_id
    )
    if not player_zones:
        enemy_zone_ids: tuple[str, ...] = ()
    elif len(authorities) == 1:
        enemy_zone_ids = enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
            state=state,
            record=record,
            player_id=player_id,
        )
    elif state.battlefield_state is not None:
        enemy_zone_ids = enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=state,
            player_id=player_id,
        )
    else:
        raise GameLifecycleError(
            "Secondary scoring context requires deployment-zone occupancy evidence."
        )
    return SecondaryScoringConditionContext(
        record=record,
        mission_setup=mission_setup,
        player_id=player_id,
        unit_destruction_states=tuple(state.secondary_unit_destruction_states),
        objective_cleanse_states=tuple(state.secondary_objective_cleanse_states),
        terrain_plunder_states=tuple(state.secondary_terrain_plunder_states),
        enemy_unit_ids_in_player_deployment_zone=enemy_zone_ids,
        starting_strength_records=tuple(state.starting_strength_records),
        occupancy=occupancy,
        game_length_battle_rounds=(
            None if state.mission_setup is None else _game_length_battle_rounds(state)
        ),
    )


def _game_length_battle_rounds(state: GameState) -> int:
    from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup

    if state.mission_setup is None:
        raise GameLifecycleError("Secondary scoring context requires MissionSetup.")
    policy = mission_scoring_policies_from_setup(state.mission_setup).policy_for_player(
        state.player_ids[0]
    )
    return policy.game_length_battle_rounds


def _model_placements_for_secondary_scoring(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    authorities: tuple[object, ...],
) -> tuple[ModelPlacement, ...]:
    if len(authorities) == 1:
        from warhammer40k_core.engine.objective_control_record_authority import (
            ObjectiveControlRecordAuthority,
        )
        from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
            primary_mission_model_placements_from_checkpoint,
        )

        authority = authorities[0]
        if type(authority) is not ObjectiveControlRecordAuthority:
            raise GameLifecycleError(
                "Secondary occupancy requires ObjectiveControlRecordAuthority."
            )
        return primary_mission_model_placements_from_checkpoint(
            state=state,
            checkpoint=authority.boundary_checkpoint,
        )
    if state.battlefield_state is None:
        raise GameLifecycleError("Secondary occupancy requires battlefield state.")
    return tuple(
        placement
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
        for placement in unit_placement.model_placements
    )
