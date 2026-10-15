from __future__ import annotations

from tests.shared.category_migration.phase11e_mission_scoring_cleanup_bindings import (
    SECONDARY_MISSION_DECISION_TYPE,
    SEEDED_TACTICAL_DRAW_REQUEST_ID,
    SEEDED_TACTICAL_DRAW_RESULT_ID,
    BattlePhase,
    GameLifecycle,
    GameState,
    JsonValue,
    LifecycleStatus,
    ObjectiveControlTiming,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionMode,
    TacticalSecondaryAchievementContext,
    TacticalSecondaryDraw,
    VictoryPointTransaction,
    expected_tactical_secondary_award_from_state,
    replace,
    score_primary_objective_control_boundary,
    seed_completed_fight_phase,
    seed_resolved_secondary_mission_selections,
    tactical_secondary_achievement_context_from_award,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_configuration import (
    _battle_state_from_config,
    _config_with_player_b_vehicles,
    _event_companion_mission_setup,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_history_and_reserves import (
    _record_secondary_vehicle_destruction,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_mission_lifecycle import (
    _battle_lifecycle,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_state_primitives import (
    _record_active_tactical_secondary,
)


def _public_ledger(payload: dict[str, JsonValue], *, player_id: str) -> dict[str, JsonValue]:
    ledgers = payload["victory_point_ledgers"]
    assert isinstance(ledgers, list)
    for ledger_value in ledgers:
        assert isinstance(ledger_value, dict)
        ledger = ledger_value
        if ledger["player_id"] == player_id:
            return ledger
    raise AssertionError(f"missing public ledger for {player_id}")


def _transaction_metadata(transaction: VictoryPointTransaction) -> dict[str, JsonValue]:
    metadata = transaction.metadata
    assert isinstance(metadata, dict)
    return metadata


def _public_card_states(payload: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    card_states = payload["secondary_mission_card_states"]
    assert isinstance(card_states, list)
    public_states: list[dict[str, JsonValue]] = []
    for card_state_value in card_states:
        assert isinstance(card_state_value, dict)
        public_states.append(card_state_value)
    return public_states


def _public_secondary_choice(
    payload: dict[str, JsonValue],
    *,
    player_id: str,
) -> dict[str, JsonValue]:
    choices = payload["secondary_mission_choices"]
    assert isinstance(choices, list)
    for choice_value in choices:
        assert isinstance(choice_value, dict)
        if choice_value["player_id"] == player_id:
            return choice_value
    raise AssertionError(f"missing public secondary choice for {player_id}")


def _advance_to_secondary_request(lifecycle: GameLifecycle) -> LifecycleStatus:
    for _index in range(32):
        status = lifecycle.advance_until_decision_or_terminal()
        request = status.decision_request
        if request is not None and request.decision_type == SECONDARY_MISSION_DECISION_TYPE:
            return status
    raise AssertionError("lifecycle did not reach secondary mission selection")


def _battle_lifecycle_with_active_tactical_cards() -> GameLifecycle:
    config = _config_with_player_b_vehicles(("vehicle-unit-3",))
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    _seed_player_a_tactical_secondary_cards(state)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    seed_completed_fight_phase(state)
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-3",
        event_log=lifecycle.decision_controller.event_log,
    )
    from tests.destruction_occurrence_fixture_helpers import finish_core_destructions_for_fixture

    finish_core_destructions_for_fixture(state=state, decisions=lifecycle.decision_controller)
    from tests.mission_action_history_helpers import prepare_turn_end_control_for_fixture

    prepare_turn_end_control_for_fixture(state=state, decisions=lifecycle.decision_controller)
    record = next(
        record
        for record in state.objective_control_records
        if record.timing is ObjectiveControlTiming.TURN_END
        and record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    return lifecycle


def _event_companion_battle_lifecycle_with_active_tactical_cards() -> GameLifecycle:
    lifecycle = _battle_lifecycle(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        mission_setup=_event_companion_mission_setup(),
    )
    state = lifecycle.state
    assert state is not None
    _seed_player_a_tactical_secondary_cards(state)
    return lifecycle


def _seed_player_a_tactical_secondary_cards(state: GameState) -> None:
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id=SEEDED_TACTICAL_DRAW_REQUEST_ID,
            result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    _record_active_tactical_secondary(state, secondary_mission_id="bring-it-down")
    _record_active_tactical_secondary(state, secondary_mission_id="no-prisoners")
    seed_resolved_secondary_mission_selections(state, player_id="player-a")


def _active_tactical_card(state: GameState) -> SecondaryMissionCardState:
    return next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )


def _record_tactical_secondary_achievement_context(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    achievement_id: str,
) -> TacticalSecondaryAchievementContext:
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id=achievement_id,
    )
    state.record_tactical_secondary_achievement_context(context)
    return context


def _tactical_secondary_achievement_context_for_card(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    achievement_id: str,
) -> TacticalSecondaryAchievementContext:
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise AssertionError("Tactical secondary achievement fixture requires a phase.")
    records = tuple(
        record
        for record in state.objective_control_records
        if record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
        and record.phase == current_phase.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )
    if len(records) != 1:
        raise AssertionError("Tactical secondary achievement fixture requires one turn-end record.")
    award = expected_tactical_secondary_award_from_state(state=state, card_state=card)
    if award is None:
        raise AssertionError("Tactical secondary achievement fixture requires a current award.")
    return replace(
        tactical_secondary_achievement_context_from_award(
            state=state,
            card=card,
            record=records[0],
            award=award,
        ),
        achievement_id=achievement_id,
    )


__all__: list[str] = []
__all__ += ["BattlePhase", "GameLifecycle", "GameState", "JsonValue", "LifecycleStatus"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "ObjectiveControlTiming"]
__all__ += ["SEEDED_TACTICAL_DRAW_REQUEST_ID", "SEEDED_TACTICAL_DRAW_RESULT_ID"]
__all__ += ["SecondaryMissionCardMode", "SecondaryMissionCardState", "SecondaryMissionCardStatus"]
__all__ += ["SecondaryMissionMode", "TacticalSecondaryAchievementContext"]
__all__ += ["TacticalSecondaryDraw", "VictoryPointTransaction", "_active_tactical_card"]
__all__ += ["_advance_to_secondary_request", "_battle_lifecycle"]
__all__ += ["_battle_lifecycle_with_active_tactical_cards", "_battle_state_from_config"]
__all__ += ["_config_with_player_b_vehicles"]
__all__ += ["_event_companion_battle_lifecycle_with_active_tactical_cards"]
__all__ += ["_event_companion_mission_setup", "_public_card_states", "_public_ledger"]
__all__ += ["_public_secondary_choice", "_record_active_tactical_secondary"]
__all__ += ["_record_secondary_vehicle_destruction"]
__all__ += ["_record_tactical_secondary_achievement_context"]
__all__ += ["_seed_player_a_tactical_secondary_cards"]
__all__ += ["_tactical_secondary_achievement_context_for_card", "_transaction_metadata"]
__all__ += ["expected_tactical_secondary_award_from_state", "replace"]
__all__ += ["score_primary_objective_control_boundary", "seed_completed_fight_phase"]
__all__ += ["seed_resolved_secondary_mission_selections"]
__all__ += ["tactical_secondary_achievement_context_from_award"]
