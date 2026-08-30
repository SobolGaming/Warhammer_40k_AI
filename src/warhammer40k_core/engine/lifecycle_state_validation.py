from __future__ import annotations

from warhammer40k_core.engine import lifecycle_state_queries as _lsq
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_views_from_armies,
)


def validate_movement_phase_state_consistency(*, state: GameState) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("movement_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("movement_phase_state requires MOVEMENT phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("movement_phase_state requires active player.")
    if movement_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("movement_phase_state active player drift.")
    if movement_state.battle_round != state.battle_round:
        raise GameLifecycleError("movement_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("movement_phase_state requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state movement_phase_state is invalid.") from exc

    placed_army = scenario.battlefield_state.placed_army_for_player_or_none(state.active_player_id)
    if placed_army is None:
        active_player_unit_ids: set[str] = set()
    else:
        active_player_unit_ids = {
            placement.unit_instance_id for placement in placed_army.unit_placements
        }
    active_player_embarked_unit_ids = _lsq.embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_reserve_unit_ids = _lsq.unarrived_reserve_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _lsq.fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    allowed_physical_unit_ids = (
        active_player_unit_ids
        | fully_removed_active_player_unit_ids
        | active_player_embarked_unit_ids
        | active_player_reserve_unit_ids
    )
    for unit_id in (*movement_state.selected_unit_ids, *movement_state.moved_unit_ids):
        if not canonical_rules_unit_identity_matches_physical_units(
            state=state,
            player_id=state.active_player_id,
            unit_instance_id=unit_id,
            physical_unit_ids=allowed_physical_unit_ids,
        ):
            raise GameLifecycleError(
                "movement_phase_state selected unit is not active player's unit."
            )
    if movement_state.active_selection is None:
        return
    active_unit_id = movement_state.active_selection.unit_instance_id
    if active_unit_id not in movement_state.selected_unit_ids:
        raise GameLifecycleError("movement_phase_state active selection drift.")
    if not canonical_rules_unit_identity_matches_physical_units(
        state=state,
        player_id=state.active_player_id,
        unit_instance_id=active_unit_id,
        physical_unit_ids=allowed_physical_unit_ids,
    ):
        raise GameLifecycleError(
            "movement_phase_state active selection is not active player's unit."
        )


def canonical_rules_unit_identity_matches_physical_units(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    physical_unit_ids: set[str],
) -> bool:
    known_canonical_ids = {
        view.unit_instance_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    } | {record.attached_unit_instance_id for record in state.starting_attached_unit_records}
    if unit_instance_id not in known_canonical_ids:
        return False
    views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    return all(view.owner_player_id == player_id for view in views) and any(
        set(view.component_unit_instance_ids).intersection(physical_unit_ids) for view in views
    )


def validate_disembarked_unit_state_consistency(*, state: GameState) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Disembarked unit state validation requires GameState.")
    if not state.disembarked_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("disembarked_unit_states require battle stage.")
    for disembarked_state in state.disembarked_unit_states:
        views = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=disembarked_state.unit_instance_id,
        )
        if any(view.owner_player_id != disembarked_state.player_id for view in views):
            raise GameLifecycleError("disembarked_unit_states player drift.")
        transport_views = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=disembarked_state.transport_unit_instance_id,
        )
        if any(view.owner_player_id != disembarked_state.player_id for view in transport_views):
            raise GameLifecycleError("disembarked_unit_states transport owner drift.")
