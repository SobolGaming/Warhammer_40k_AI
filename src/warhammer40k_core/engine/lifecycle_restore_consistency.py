from __future__ import annotations

from warhammer40k_core.engine import attack_sequence_hazardous as _ash
from warhammer40k_core.engine import battle_shock_lifecycle_authority as _bsa
from warhammer40k_core.engine import destroyed_transport_pending as _destroyed_transport_pending
from warhammer40k_core.engine import fight_activation_history_integrity as _fahi
from warhammer40k_core.engine import lifecycle_state_queries as _lsq
from warhammer40k_core.engine import model_destruction_cause_producers as _mdcp
from warhammer40k_core.engine import primary_historical_event_integrity as _phei
from warhammer40k_core.engine import primary_mission_state_validation as _pmsv
from warhammer40k_core.engine import reserve_state_integrity as _rsi
from warhammer40k_core.engine import transport_state_integrity as _tsi
from warhammer40k_core.engine.attack_hit_authority import validate_attack_hit_authority
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lethal_hits import (
    validate_lethal_hit_history,
    validate_pending_lethal_hit_requests,
)
from warhammer40k_core.engine.lifecycle_battlefield_requirements import (
    state_allows_battlefield_state as _state_allows_battlefield_state,
)
from warhammer40k_core.engine.lifecycle_battlefield_requirements import (
    state_is_before_deploy_armies as _state_is_before_deploy_armies,
)
from warhammer40k_core.engine.lifecycle_battlefield_requirements import (
    state_requires_battlefield_state as _state_requires_battlefield_state,
)
from warhammer40k_core.engine.lifecycle_battlefield_requirements import (
    state_requires_deployed_battlefield_state as _state_requires_deployed_battlefield_state,
)
from warhammer40k_core.engine.lifecycle_payload_consistency import (
    validate_config_state_payload_consistency,
)
from warhammer40k_core.engine.lifecycle_state_validation import (
    canonical_rules_unit_identity_matches_physical_units,
    validate_disembarked_unit_state_consistency,
    validate_fight_phase_state_consistency,
    validate_movement_phase_state_consistency,
)
from warhammer40k_core.engine.normal_move_history import validate_normal_move_state_consistency
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.phase_movement_history import (
    validate_return_on_death_setup_authority,
)
from warhammer40k_core.engine.prebattle_integrity import validate_prebattle_alternation_restore
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.unit_coherency import assert_battlefield_units_in_coherency


def validate_payload_consistency(
    *,
    state: GameState,
    config: GameConfig | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    from warhammer40k_core.engine.activity_restriction_restore import (
        validate_activity_restriction_inventory,
    )

    validate_attack_hit_authority(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )
    validate_pending_lethal_hit_requests(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )
    validate_lethal_hit_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )
    validate_activity_restriction_inventory(
        state=state, event_records=event_records, decision_records=decision_records
    )
    _rsi.validate_reserve_state_consistency(state=state)
    _tsi.validate_transport_cargo_state_consistency(state=state)
    validate_prebattle_alternation_restore(
        state=state,
        army_catalog=None if config is None else config.army_catalog,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )
    _mdcp.validate_model_destruction_cause_restore(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )
    validate_return_on_death_setup_authority(
        state=state, event_records=event_records, decision_records=decision_records
    )
    _validate_battlefield_state_consistency(state=state, config=config)
    _rsi.validate_initial_reserve_destruction_policy_authority(
        state=state,
        event_records=event_records,
    )
    validate_movement_phase_state_consistency(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_shooting_phase_state_consistency(state=state)
    _validate_charge_phase_state_consistency(state=state)
    validate_fight_phase_state_consistency(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _ash.validate_pending_hazardous_mortal_wound_requests(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )
    _destroyed_transport_pending.validate_pending_destroyed_transport_restore(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )
    _bsa.validate_restore(state, event_records, decision_records, pending_decision_requests)
    _fahi.validate_restore(state, event_records, decision_records, pending_decision_requests)
    validate_disembarked_unit_state_consistency(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_advanced_unit_state_consistency(state=state)
    _validate_fell_back_unit_state_consistency(state=state)
    validate_normal_move_state_consistency(state=state)
    validate_config_state_payload_consistency(
        state=state,
        config=config,
        event_records=event_records,
        decision_records=decision_records,
    )
    _phei.validate_primary_historical_event_integrity(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        require_muster_event_provenance=config is not None,
    )
    _pmsv.validate_primary_mission_progress_state(
        state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )


def _validate_battlefield_state_consistency(
    *,
    state: GameState,
    config: GameConfig | None,
) -> None:
    if state.battlefield_state is None:
        if _state_requires_battlefield_state(state):
            raise GameLifecycleError("Lifecycle state is missing battlefield_state.")
        return
    if not _state_allows_battlefield_state(state):
        raise GameLifecycleError(
            "Lifecycle state battlefield_state must be absent before DEPLOY_ARMIES."
        )
    if _state_is_before_deploy_armies(state) and (
        state.battlefield_state.placed_armies or state.battlefield_state.removed_model_ids
    ):
        raise GameLifecycleError(
            "Lifecycle state battlefield_state must not contain placed or removed models "
            "before DEPLOY_ARMIES."
        )
    try:
        scenario = battlefield_scenario_for_state(state=state)
        if _state_requires_deployed_battlefield_state(state):
            scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
        if config is not None and _state_requires_deployed_battlefield_state(state):
            assert_battlefield_units_in_coherency(
                scenario=_fahi.battlefield_scenario_for_living_model_coherency(
                    scenario=scenario,
                    state=state,
                ),
                ruleset_descriptor=config.ruleset_descriptor,
            )
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state battlefield_state is invalid.") from exc


def _validate_shooting_phase_state_consistency(*, state: GameState) -> None:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("shooting_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("shooting_phase_state requires SHOOTING phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("shooting_phase_state requires active player.")
    if shooting_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("shooting_phase_state active player drift.")
    if shooting_state.battle_round != state.battle_round:
        raise GameLifecycleError("shooting_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("shooting_phase_state requires battlefield_state.")
    unit_owner_by_id = {
        rules_unit.unit_instance_id: rules_unit.owner_player_id
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    }
    active_player_embarked_unit_ids = _lsq.embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_unit_ids = {
        unit_id
        for unit_id, player_id in unit_owner_by_id.items()
        if player_id == state.active_player_id
    }
    for unit_id in (
        *shooting_state.selected_unit_ids,
        *shooting_state.shot_unit_ids,
        *shooting_state.skipped_unit_ids,
    ):
        if unit_id not in active_player_unit_ids and unit_id not in active_player_embarked_unit_ids:
            raise GameLifecycleError(
                "shooting_phase_state selected unit is not active player's unit."
            )
    active_selection = shooting_state.active_selection
    if active_selection is None:
        return
    if active_selection.unit_instance_id not in shooting_state.selected_unit_ids:
        raise GameLifecycleError("shooting_phase_state active selection drift.")
    if active_selection.unit_instance_id not in active_player_unit_ids:
        raise GameLifecycleError(
            "shooting_phase_state active selection is not active player's unit."
        )


def _validate_charge_phase_state_consistency(*, state: GameState) -> None:
    charge_state = state.charge_phase_state
    if charge_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("charge_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.CHARGE:
        raise GameLifecycleError("charge_phase_state requires CHARGE phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("charge_phase_state requires active player.")
    parent = (
        charge_state
        if charge_state.interruption is None
        else charge_state.interruption.suspended_phase
    )
    if parent.active_player_id != state.active_player_id:
        raise GameLifecycleError("charge_phase_state active player drift.")
    if charge_state.battle_round != state.battle_round:
        raise GameLifecycleError("charge_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("charge_phase_state requires battlefield_state.")
    unit_owner_by_id = {
        rules_unit.unit_instance_id: rules_unit.owner_player_id
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    }
    active_player_unit_ids = {
        unit_id
        for unit_id, player_id in unit_owner_by_id.items()
        if player_id == charge_state.active_player_id
    }
    for unit_id in charge_state.selected_unit_ids:
        if unit_id not in active_player_unit_ids:
            raise GameLifecycleError(
                "charge_phase_state selected unit is not active player's unit."
            )
    active_selection = charge_state.active_selection
    if active_selection is not None:
        if active_selection.unit_instance_id not in charge_state.selected_unit_ids:
            raise GameLifecycleError("charge_phase_state active selection drift.")
        if active_selection.unit_instance_id not in active_player_unit_ids:
            raise GameLifecycleError(
                "charge_phase_state active selection is not active player's unit."
            )
    for distance_state in charge_state.distance_states:
        roll_result = distance_state.roll_result
        charging_unit_id = roll_result.request.unit_instance_id
        if charging_unit_id not in charge_state.selected_unit_ids:
            raise GameLifecycleError("charge_phase_state roll unit was not selected.")
        if charging_unit_id not in active_player_unit_ids:
            raise GameLifecycleError("charge_phase_state roll unit is not active player's unit.")
        for target_unit_id in roll_result.reachable_target_distances_inches:
            target_owner = unit_owner_by_id.get(target_unit_id)
            if target_owner is None:
                raise GameLifecycleError("charge_phase_state target unit is unknown.")
            if target_owner == charge_state.active_player_id:
                raise GameLifecycleError("charge_phase_state target unit is not an enemy.")


def _validate_advanced_unit_state_consistency(*, state: GameState) -> None:
    if not state.advanced_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("advanced_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("advanced_unit_states require active player.")
    if state.battlefield_state is None:
        raise GameLifecycleError("advanced_unit_states require battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state advanced_unit_states are invalid.") from exc

    active_player_unit_ids = {
        placement.unit_instance_id for placement in placed_army.unit_placements
    }
    active_player_embarked_unit_ids = _lsq.embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _lsq.fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for advanced_state in state.advanced_unit_states:
        if advanced_state.player_id != state.active_player_id:
            raise GameLifecycleError("advanced_unit_states player drift.")
        if advanced_state.battle_round != state.battle_round:
            raise GameLifecycleError("advanced_unit_states battle round drift.")
        if not canonical_rules_unit_identity_matches_physical_units(
            state=state,
            player_id=state.active_player_id,
            unit_instance_id=advanced_state.unit_instance_id,
            physical_unit_ids=(
                active_player_unit_ids
                | active_player_embarked_unit_ids
                | fully_removed_active_player_unit_ids
            ),
        ):
            raise GameLifecycleError("advanced_unit_states unit is not active player's unit.")


def _validate_fell_back_unit_state_consistency(*, state: GameState) -> None:
    if not state.fell_back_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("fell_back_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("fell_back_unit_states require active player.")
    if state.battlefield_state is None:
        raise GameLifecycleError("fell_back_unit_states require battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state fell_back_unit_states are invalid.") from exc

    active_player_unit_ids = {
        placement.unit_instance_id for placement in placed_army.unit_placements
    }
    active_player_embarked_unit_ids = _lsq.embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _lsq.fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    for fell_back_state in state.fell_back_unit_states:
        if fell_back_state.player_id != state.active_player_id:
            raise GameLifecycleError("fell_back_unit_states player drift.")
        if fell_back_state.battle_round != state.battle_round:
            raise GameLifecycleError("fell_back_unit_states battle round drift.")
        if not canonical_rules_unit_identity_matches_physical_units(
            state=state,
            player_id=state.active_player_id,
            unit_instance_id=fell_back_state.unit_instance_id,
            physical_unit_ids=(
                active_player_unit_ids
                | active_player_embarked_unit_ids
                | fully_removed_active_player_unit_ids
            ),
        ):
            raise GameLifecycleError("fell_back_unit_states unit is not active player's unit.")
