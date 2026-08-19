from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    TacticalSecondaryAchievementContext,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.secondary_scoring_context import (
    secondary_mission_selection_for_card,
    secondary_scoring_condition_context_from_state,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(GameLifecycleError)


def tactical_secondary_achievement_context_from_award(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
    award: VictoryPointAward,
) -> TacticalSecondaryAchievementContext:
    if type(award) is not VictoryPointAward:
        raise GameLifecycleError("Tactical secondary achievement requires a VictoryPointAward.")
    if state.active_player_id is None:
        raise GameLifecycleError("Tactical secondary achievement requires an active player.")
    metadata = _metadata_object(award.metadata)
    rule_ids = _string_tuple(metadata.get("scoring_rule_ids"), field_name="scoring_rule_ids")
    conditions = _string_tuple(
        metadata.get("scoring_rule_conditions"),
        field_name="scoring_rule_conditions",
    )
    source_ids = _string_tuple(
        metadata.get("scoring_rule_source_ids"),
        field_name="scoring_rule_source_ids",
    )
    if not rule_ids or not conditions or not source_ids:
        raise GameLifecycleError("Tactical secondary achievement requires scoring-rule metadata.")
    return TacticalSecondaryAchievementContext(
        achievement_id=(
            f"tactical-secondary-achievement:{state.game_id}:{card.player_id}:"
            f"{card.secondary_mission_id}:{record.record_id}"
        ),
        game_id=state.game_id,
        player_id=card.player_id,
        active_player_id=state.active_player_id,
        secondary_mission_id=card.secondary_mission_id,
        battle_round=state.battle_round,
        phase=record.phase,
        card_battle_round=card.battle_round,
        victory_points=award.amount,
        scoring_rule_id=rule_ids[0],
        scoring_rule_condition=conditions[0],
        scoring_rule_source_id=source_ids[0],
        scoring_timing=award.scoring_timing,
        source_id=card.secondary_mission_id,
        evidence=award.metadata,
    )


def validate_tactical_secondary_achievement_context(
    *,
    state: GameState,
    context: TacticalSecondaryAchievementContext,
) -> None:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Tactical secondary achievement validation requires GameState.")
    if type(context) is not TacticalSecondaryAchievementContext:
        raise GameLifecycleError(
            "Tactical secondary achievement validation requires "
            "TacticalSecondaryAchievementContext."
        )
    if context.game_id != state.game_id:
        raise GameLifecycleError("Tactical secondary achievement context game_id drift.")
    if context.player_id not in state.player_ids:
        raise GameLifecycleError(
            "Tactical secondary achievement context player_id is not in this game."
        )
    if context.active_player_id != state.active_player_id:
        raise GameLifecycleError("Tactical secondary achievement context active_player_id drift.")
    if context.battle_round != state.battle_round:
        raise GameLifecycleError("Tactical secondary achievement context battle_round drift.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Tactical secondary achievement context requires a phase.")
    if context.phase != current_phase.value:
        raise GameLifecycleError("Tactical secondary achievement context phase drift.")
    card_state = state.secondary_mission_card_state(
        player_id=context.player_id,
        secondary_mission_id=context.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card_state is None:
        raise GameLifecycleError("Tactical secondary achievement context requires an active card.")
    if context.card_battle_round != card_state.battle_round:
        raise GameLifecycleError("Tactical secondary achievement context card battle_round drift.")
    expected = expected_tactical_secondary_award_from_state(
        state=state,
        card_state=card_state,
    )
    if expected is None:
        raise GameLifecycleError("Tactical secondary achievement context has no current award.")
    metadata = _metadata_object(expected.metadata)
    rule_ids = _string_tuple(metadata.get("scoring_rule_ids"), field_name="scoring_rule_ids")
    conditions = _string_tuple(
        metadata.get("scoring_rule_conditions"),
        field_name="scoring_rule_conditions",
    )
    source_ids = _string_tuple(
        metadata.get("scoring_rule_source_ids"),
        field_name="scoring_rule_source_ids",
    )
    if context.victory_points != expected.amount:
        raise GameLifecycleError("Tactical secondary achievement context VP drift.")
    if not rule_ids or context.scoring_rule_id != rule_ids[0]:
        raise GameLifecycleError("Tactical secondary achievement context rule ID drift.")
    if not conditions or context.scoring_rule_condition != conditions[0]:
        raise GameLifecycleError("Tactical secondary achievement context condition drift.")
    if not source_ids or context.scoring_rule_source_id != source_ids[0]:
        raise GameLifecycleError("Tactical secondary achievement context source ID drift.")
    if context.scoring_timing != expected.scoring_timing:
        raise GameLifecycleError("Tactical secondary achievement context timing drift.")


def expected_tactical_secondary_award_from_state(
    *,
    state: GameState,
    card_state: SecondaryMissionCardState,
) -> VictoryPointAward | None:
    if state.mission_setup is None:
        raise GameLifecycleError("Tactical secondary achievement context requires MissionSetup.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Tactical secondary achievement context requires a phase.")
    records = tuple(
        record
        for record in state.objective_control_records
        if record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
        and record.phase == current_phase.value
        and record.timing.value == "turn_end"
    )
    if len(records) != 1:
        raise GameLifecycleError(
            "Tactical secondary achievement requires one current turn-end objective record."
        )
    record = records[0]
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    context = secondary_scoring_condition_context_from_state(
        state=state,
        player_id=card_state.player_id,
        record=record,
        selection=secondary_mission_selection_for_card(card_state),
    )
    return policies.secondary_award_from_mission_state(
        player_id=card_state.player_id,
        battle_round=state.battle_round,
        phase=current_phase.value,
        secondary_mission_id=card_state.secondary_mission_id,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
        record=record,
        mission_setup=state.mission_setup,
        unit_destruction_states=tuple(state.secondary_unit_destruction_states),
        objective_cleanse_states=tuple(state.secondary_objective_cleanse_states),
        terrain_plunder_states=tuple(state.secondary_terrain_plunder_states),
        enemy_unit_ids_in_player_deployment_zone=context.enemy_unit_ids_in_player_deployment_zone,
        starting_strength_records=tuple(state.starting_strength_records),
        condition_context=context,
    )


def apply_tactical_secondary_score_result(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    from warhammer40k_core.engine.mission_decisions import tactical_secondary_score_drift_reason

    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
    achievement_id = _payload_string(payload, key="achievement_id")
    drift_reason = tactical_secondary_score_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result=result,
    )
    if drift_reason is not None:
        raise GameLifecycleError(f"Tactical secondary score option drifted: {drift_reason}.")
    achievement_context = state.tactical_secondary_achievement_context(achievement_id)
    if achievement_context is None:
        raise GameLifecycleError("Tactical secondary achievement context is missing.")
    achievement_payload = validate_json_value(achievement_context.to_payload())
    if _payload_bool(payload, key="score"):
        scored = state.score_secondary_mission_from_state(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=_current_phase(state),
            event_log=decisions.event_log,
        )
        if scored.scored_transaction_id is None:
            raise GameLifecycleError("Scored Tactical secondary requires a transaction ID.")
        transaction = _victory_point_transaction_by_id(
            state=state,
            player_id=player_id,
            transaction_id=scored.scored_transaction_id,
        )
        decisions.event_log.append(
            "tactical_secondary_mission_scored",
            {
                "game_id": state.game_id,
                "player_id": player_id,
                "active_player_id": _active_player_id(state),
                "battle_round": state.battle_round,
                "phase": _current_phase(state).value,
                "achievement_context": achievement_payload,
                "secondary_mission_card_state": validate_json_value(scored.to_payload()),
                "victory_point_transaction": validate_json_value(transaction.to_payload()),
                "discarded_after_score": True,
            },
        )
        if state.tactical_secondary_achievement_context(achievement_id) is not None:
            state.consume_tactical_secondary_achievement_context(achievement_id)
        return
    card_state = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card_state is None:
        raise GameLifecycleError("Retained Tactical secondary card is not active.")
    decisions.event_log.append(
        "tactical_secondary_mission_score_declined",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "active_player_id": _active_player_id(state),
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "achievement_context": achievement_payload,
            "secondary_mission_card_state": validate_json_value(card_state.to_payload()),
            "retained": True,
        },
    )
    state.consume_tactical_secondary_achievement_context(achievement_id)


def _assert_battle_state(state: GameState) -> None:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Tactical secondary score requires GameState.")
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Tactical secondary score can be applied only during battle.")


def _current_phase(state: GameState) -> BattlePhase:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Tactical secondary score requires a battle phase.")
    return phase


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Tactical secondary score requires an active player.")
    return active_player_id


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Tactical secondary score payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    return _validate_identifier(key, payload[key])


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Tactical secondary score payload key must be a bool: {key}.")
    return value


def _victory_point_transaction_by_id(
    *,
    state: GameState,
    player_id: str,
    transaction_id: str,
) -> VictoryPointTransaction:
    requested_transaction_id = _validate_identifier("transaction_id", transaction_id)
    ledger = state.victory_point_ledger_for_player(player_id)
    for transaction in ledger.transactions:
        if transaction.transaction_id == requested_transaction_id:
            return transaction
    raise GameLifecycleError("Victory point transaction was not found.")


def _metadata_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Tactical secondary achievement metadata must be an object.")
    return value


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{field_name} must be a list.")
    items: list[str] = []
    for item in cast(list[object], value):
        if type(item) is not str or not item:
            raise GameLifecycleError(f"{field_name} must contain identifiers.")
        items.append(item)
    return tuple(items)
