from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    ModelPlacementRecord,
)
from warhammer40k_core.engine.command_core_cp_history import (
    expected_core_command_occurrence_keys,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    record_new_primary_turn_start_evidence_events,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.setup_flow import army_mustered_event_payload
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index


def record_current_battlefield_placements_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Deployment-history fixture requires battlefield state.")
    mustered_model_ids = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    placed_model_ids = set(battlefield.placed_model_ids())
    if battlefield.removed_model_ids or placed_model_ids != mustered_model_ids:
        raise AssertionError(
            "Deployment-history fixture requires every mustered model to be placed."
        )
    placements = tuple(
        ModelPlacementRecord(
            model_instance_id=model_placement.model_instance_id,
            placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
            pose=model_placement.pose,
            source_phase="setup",
            source_step="deploy_armies",
        )
        for placed_army in battlefield.placed_armies
        for unit_placement in placed_army.unit_placements
        for model_placement in unit_placement.model_placements
    )
    transition = BattlefieldTransitionBatch(
        placements=tuple(sorted(placements, key=lambda value: value.model_instance_id))
    )
    decisions.event_log.append(
        "battlefield_models_placed",
        {
            "game_id": state.game_id,
            "setup_step": "deploy_armies",
            "battlefield_id": battlefield.battlefield_id,
            "placement_kind": BattlefieldPlacementKind.DEPLOYMENT.value,
            "placed_model_count": len(transition.placements),
            "transition_batch": transition.to_payload(),
        },
    )


def ensure_army_mustered_events_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController,
) -> None:
    armies_by_id = {army.army_id: army for army in state.army_definitions}
    players_requiring_provenance = {
        record.player_id for record in state.starting_attached_unit_records
    }
    recorded_army_ids: set[str] = set()
    for event in decisions.event_log.records:
        if event.event_type != "army_mustered":
            continue
        payload = event.payload
        if not isinstance(payload, dict) or type(payload.get("army_id")) is not str:
            raise AssertionError("Fixture army_mustered event payload is malformed.")
        army_id = payload["army_id"]
        if army_id not in armies_by_id:
            raise AssertionError("Fixture army_mustered event references an unknown army.")
        if army_id in recorded_army_ids:
            raise AssertionError("Fixture army_mustered event is duplicated.")
        recorded_army_ids.add(army_id)
    for army in state.army_definitions:
        if army.player_id not in players_requiring_provenance or army.army_id in recorded_army_ids:
            continue
        decisions.event_log.append(
            "army_mustered",
            army_mustered_event_payload(state=state, army_definition=army),
        )


def record_primary_turn_start_evidence_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController | None = None,
) -> DecisionController:
    resolved_decisions = DecisionController() if decisions is None else decisions
    ensure_army_mustered_events_for_fixture(state, decisions=resolved_decisions)
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record_primary_turn_start_evidence(state=state)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=resolved_decisions.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    return resolved_decisions


def record_existing_primary_turn_start_evidence_events_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    if any(
        event.event_type == PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT
        for event in decisions.event_log.records
    ):
        raise AssertionError("Fixture primary turn-start evidence event is already recorded.")
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=(),
        snapshot_ids_before=(),
    )


def record_completed_command_occurrences_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController,
    config: object,
) -> None:
    from warhammer40k_core.engine.game_state import GameConfig

    if type(config) is not GameConfig:
        raise AssertionError("Command-history fixture requires GameConfig.")
    occurrence_keys = expected_core_command_occurrence_keys(state)
    recorded_keys: list[tuple[int, str]] = []
    for event in decisions.event_log.records:
        if event.event_type != "command_step_started":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise TypeError("Command-history fixture anchor payload is malformed.")
        battle_round = payload.get("battle_round")
        active_player_id = payload.get("active_player_id")
        if type(battle_round) is not int or type(active_player_id) is not str:
            raise AssertionError("Command-history fixture anchor context is malformed.")
        recorded_keys.append((battle_round, active_player_id))
    if len(recorded_keys) != len(set(recorded_keys)):
        raise AssertionError("Command-history fixture anchor is duplicated.")
    if not set(recorded_keys) <= set(occurrence_keys):
        raise AssertionError("Command-history fixture anchor escaped final state authority.")
    missing_occurrence_keys = tuple(key for key in occurrence_keys if key not in set(recorded_keys))
    if not missing_occurrence_keys:
        return
    if state.command_step_state is not None:
        raise AssertionError("Command-history fixture requires no active Command step.")
    original_battle_round = state.battle_round
    original_active_player_id = state.active_player_id
    original_battle_phase_index = state.battle_phase_index
    bundle = build_runtime_content_bundle_for_armies(
        config=config,
        armies=tuple(state.army_definitions),
    )
    handler = CommandPhaseHandler(
        stratagem_index=eleventh_edition_stratagem_index(),
        stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
        battle_shock_hooks=bundle.battle_shock_hook_registry,
        command_phase_start_hooks=bundle.command_phase_start_hook_registry,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
    )
    for battle_round, active_player_id in missing_occurrence_keys:
        state.battle_round = battle_round
        state.active_player_id = active_player_id
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
        completed = handler.begin_phase(state=state, decisions=decisions)
        if completed.status_kind is not LifecycleStatusKind.ADVANCED:
            raise AssertionError("Command-history fixture unexpectedly requires a player decision.")
        state.command_step_state = None
    state.battle_round = original_battle_round
    state.active_player_id = original_active_player_id
    state.battle_phase_index = original_battle_phase_index


def enter_battle_for_fixture(
    state: GameState,
    *,
    decisions: DecisionController | None = None,
) -> DecisionController:
    resolved_decisions = DecisionController() if decisions is None else decisions
    ensure_army_mustered_events_for_fixture(state, decisions=resolved_decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    state.complete_final_setup_step_before_battle()
    state.enter_battle()
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=resolved_decisions.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    return resolved_decisions
