from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    collect_battle_shock_test_requests,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartContext,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
    CommandPointSpendStatus,
    CommandStepState,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagems import (
    CORE_INSANE_BRAVERY_HANDLER_ID,
    CORE_NEW_ORDERS_HANDLER_ID,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    create_stratagem_use_decision_request,
    request_stratagem_target_proposal,
    stratagem_decline_option,
    stratagem_target_proposal_from_index,
    stratagem_use_options_for_handler_from_index,
    stratagem_window_declined_for_context,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_start_engagement import (
    record_turn_start_engagement_snapshot,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

TACTICAL_SECONDARY_DRAW_DECISION_TYPE = "draw_tactical_secondary_missions"
TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE = "replace_tactical_secondary_mission"
TACTICAL_SECONDARY_REPLACEMENT_DECLINE_OPTION_ID = "decline_tactical_secondary_replacement"
EVENT_COMPANION_MISSION_PACK_ID = "11e-warhammer-event-companion-2026-06"


def _empty_ability_indexes() -> Mapping[str, AbilityCatalogIndex]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class CommandPhaseHandler:
    stratagem_index: StratagemCatalogIndex = field(default_factory=eleventh_edition_stratagem_index)
    battle_shock_hooks: BattleShockHookRegistry = field(
        default_factory=BattleShockHookRegistry.empty
    )
    command_phase_start_hooks: CommandPhaseStartHookRegistry = field(
        default_factory=CommandPhaseStartHookRegistry.empty
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = field(
        default_factory=_empty_ability_indexes
    )

    def __post_init__(self) -> None:
        if type(self.stratagem_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("CommandPhaseHandler stratagem_index must be an index.")
        if type(self.battle_shock_hooks) is not BattleShockHookRegistry:
            raise GameLifecycleError("CommandPhaseHandler battle_shock_hooks must be a registry.")
        if type(self.command_phase_start_hooks) is not CommandPhaseStartHookRegistry:
            raise GameLifecycleError(
                "CommandPhaseHandler command_phase_start_hooks must be a registry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "CommandPhaseHandler runtime_modifier_registry must be a registry."
            )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_index_mapping(self.ability_indexes_by_player_id),
        )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.COMMAND

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("CommandPhaseHandler can run only during battle.")
        if state.current_battle_phase is not BattlePhase.COMMAND:
            raise GameLifecycleError("CommandPhaseHandler can run only in the COMMAND phase.")
        active_player_id = _active_player_id(state)
        record_turn_start_engagement_snapshot(
            state=state,
            player_id=active_player_id,
        )
        choice = state.secondary_mission_choice_for_player(active_player_id)
        if choice is None:
            raise GameLifecycleError("Command phase requires secondary mission choices.")

        command_state = _ensure_command_step_state(state, active_player_id=active_player_id)
        if not command_state.command_points_granted:
            command_start_status = _resolve_command_step_start(
                state=state,
                decisions=decisions,
                command_phase_start_hooks=self.command_phase_start_hooks,
            )
            if command_start_status is not None:
                return command_start_status
            command_state = _command_step_state(state)
        if not command_state.scoring_hooks_resolved:
            _resolve_command_phase_scoring_hooks(state=state, decisions=decisions)
            command_state = _command_step_state(state)

        if (
            not command_state.tactical_secondary_resolved
            and choice.mode is SecondaryMissionMode.TACTICAL
            and not state.has_tactical_secondary_draw(
                player_id=active_player_id,
                battle_round=state.battle_round,
            )
        ):
            return _request_tactical_secondary_draw(
                state=state,
                decisions=decisions,
                active_player_id=active_player_id,
            )

        if not command_state.tactical_secondary_resolved:
            state.command_step_state = command_state.with_tactical_secondary_resolved()
            command_state = _command_step_state(state)

        if not command_state.battle_shock_step_resolved:
            stratagem_status = _request_command_start_stratagem_if_available(
                state=state,
                decisions=decisions,
                stratagem_index=self.stratagem_index,
            )
            if stratagem_status is not None:
                return stratagem_status

        if not command_state.battle_shock_step_resolved:
            _resolve_battle_shock_step(
                state=state,
                decisions=decisions,
                battle_shock_hooks=self.battle_shock_hooks,
                runtime_modifier_registry=self.runtime_modifier_registry,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=active_player_id,
                ),
            )
            command_state = _command_step_state(state)

        if not command_state.tactical_secondary_replacement_resolved:
            replacement_status = _request_tactical_secondary_replacement_if_available(
                state=state,
                decisions=decisions,
                active_player_id=active_player_id,
            )
            if replacement_status is not None:
                return replacement_status
            state.command_step_state = command_state.with_tactical_secondary_replacement_resolved()

        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
                "phase_body_status": "command_phase_complete",
                "command_step": "complete",
                "battle_shock_step": "complete",
            },
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> None:
        if result.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE:
            _apply_tactical_secondary_draw(state=state, result=result, decisions=decisions)
            return
        if result.decision_type == TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE:
            _apply_tactical_secondary_replacement(
                state=state,
                result=result,
                decisions=decisions,
            )
            return
        if result.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE:
            active_player_id = _active_player_id(state)
            record = decisions.record_for_result(result)
            handled = self.command_phase_start_hooks.apply_result(
                CommandPhaseStartResultContext(
                    state=state,
                    decisions=decisions,
                    request=record.request,
                    result=result,
                    active_player_id=active_player_id,
                )
            )
            if not handled:
                raise GameLifecycleError("Command-phase start faction rule result was not handled.")
            return
        raise GameLifecycleError("CommandPhaseHandler received an unsupported decision_type.")


def invalid_command_phase_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE:
        return None
    if request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE:
        return _invalid_command_phase_start_faction_rule_status(
            state=state,
            request=request,
            result=result,
        )
    if request.decision_type != TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Command phase validator received unsupported decision_type.")
    payload = _decision_payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    secondary_mission_id = (
        None
        if result.selected_option_id == TACTICAL_SECONDARY_REPLACEMENT_DECLINE_OPTION_ID
        else _payload_string(payload, key="secondary_mission_id")
    )
    drift_reason = _tactical_secondary_replacement_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result=result,
    )
    if drift_reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Tactical secondary replacement option drifted.",
        payload={
            "game_id": state.game_id,
            "player_id": player_id,
            "secondary_mission_id": secondary_mission_id,
            "invalid_reason": drift_reason,
        },
    )


def _apply_tactical_secondary_draw(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Tactical secondary draws can be applied only during battle.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Tactical secondary draws can be applied only in command.")
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Tactical secondary draw actor must be the active player.")
    payload = _decision_payload_object(result.payload)
    battle_round = _payload_int(payload, key="battle_round")
    draw_count = _payload_int(payload, key="draw_count")
    if battle_round != state.battle_round:
        raise GameLifecycleError("Tactical secondary draw battle_round does not match state.")
    if draw_count != state.tactical_secondary_draw_count:
        raise GameLifecycleError("Tactical secondary draw_count does not match state.")
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id=active_player_id,
            battle_round=battle_round,
            request_id=result.request_id,
            result_id=result.result_id,
            draw_count=draw_count,
        )
    )
    card_states = state.draw_tactical_secondary_cards(
        player_id=active_player_id,
        source_result_id=result.result_id,
    )
    decisions.event_log.append(
        "tactical_secondary_missions_drawn",
        {
            "game_id": state.game_id,
            "player_id": active_player_id,
            "battle_round": battle_round,
            "draw_count": draw_count,
            "phase": BattlePhase.COMMAND.value,
            "secondary_mission_card_states": [
                validate_json_value(card_state.to_payload()) for card_state in card_states
            ],
        },
    )
    command_state = _command_step_state(state)
    state.command_step_state = command_state.with_tactical_secondary_resolved()


def _apply_tactical_secondary_replacement(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Tactical secondary replacement can be applied only in battle.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Tactical secondary replacement can be applied only in command.")
    active_player_id = _active_player_id(state)
    payload = _decision_payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    if player_id != active_player_id:
        raise GameLifecycleError("Tactical secondary replacement player must be active player.")
    if result.selected_option_id == TACTICAL_SECONDARY_REPLACEMENT_DECLINE_OPTION_ID:
        _validate_tactical_secondary_replacement_context(
            state=state,
            payload=payload,
            player_id=player_id,
            secondary_mission_id=None,
            result=result,
        )
        state.command_step_state = _command_step_state(
            state
        ).with_tactical_secondary_replacement_resolved()
        decisions.event_log.append(
            "tactical_secondary_replacement_declined",
            {
                "game_id": state.game_id,
                "player_id": player_id,
                "active_player_id": active_player_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "timing": "end_of_command_phase",
                "source_id": _tactical_secondary_procedure_source_id(state),
            },
        )
        return

    secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
    _validate_tactical_secondary_replacement_context(
        state=state,
        payload=payload,
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result=result,
    )
    spend = state.spend_command_points(
        player_id=player_id,
        amount=1,
        source_id=(
            f"{_tactical_secondary_procedure_source_id(state)}:replacement:"
            f"{result.result_id}:cp-spend"
        ),
    )
    if spend.status is not CommandPointSpendStatus.APPLIED:
        raise GameLifecycleError("Tactical secondary replacement CP spend failed.")
    spend_payload = validate_json_value(spend.to_payload())
    decisions.event_log.append("command_points_spent", spend_payload)
    state.record_tactical_secondary_replacement_use(player_id)
    discarded = state.discard_tactical_secondary(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result_id=result.result_id,
    )
    drawn = state.draw_tactical_secondary_cards(
        player_id=player_id,
        source_result_id=result.result_id,
        draw_count=1,
    )
    state.command_step_state = _command_step_state(
        state
    ).with_tactical_secondary_replacement_resolved()
    decisions.event_log.append(
        "tactical_secondary_mission_replaced",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "active_player_id": active_player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "timing": "end_of_command_phase",
            "replacement_cost_cp": 1,
            "discarded_secondary_mission_id": secondary_mission_id,
            "discarded_secondary_mission_card_state": validate_json_value(discarded.to_payload()),
            "drawn_secondary_mission_card_states": [
                validate_json_value(card.to_payload()) for card in drawn
            ],
            "command_point_spend": spend_payload,
            "source_id": _tactical_secondary_procedure_source_id(state),
        },
    )


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle state requires an active player.")
    return state.active_player_id


def _validate_player_id(field_name: str, value: object) -> str:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("Player identifier validation requires a field name.")
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be a non-empty string.")
    return value


def _validate_ability_index_mapping(indexes: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("ability_indexes_by_player_id must be a mapping.")
    mapped_indexes = cast(Mapping[object, object], indexes)
    validated: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in mapped_indexes.items():
        player_id = _validate_player_id("ability_indexes_by_player_id key", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "ability_indexes_by_player_id values must be AbilityCatalogIndex."
            )
        validated[player_id] = raw_index
    return MappingProxyType(validated)


def _ability_index_for_player(
    indexes: object,
    *,
    player_id: str,
) -> AbilityCatalogIndex:
    player = _validate_player_id("player_id", player_id)
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("ability_indexes_by_player_id must be a mapping.")
    mapped_indexes = cast(Mapping[str, AbilityCatalogIndex], indexes)
    index = mapped_indexes.get(player)
    if index is None:
        return AbilityCatalogIndex.from_records(())
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("ability index mapping contained an invalid value.")
    return index


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload key must be an integer: {key}.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Decision payload key must not be empty: {key}.")
    return stripped


def _unit_owner_and_instance_by_id(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str | None, UnitInstance | None]:
    requested_unit_id = _validate_player_id("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id, unit
    return None, None


def _active_tactical_secondary_cards(
    *,
    state: GameState,
    player_id: str,
) -> tuple[SecondaryMissionCardState, ...]:
    return tuple(
        sorted(
            (
                card
                for card in state.secondary_mission_card_states
                if card.player_id == player_id
                and card.mode is SecondaryMissionCardMode.TACTICAL
                and card.status is SecondaryMissionCardStatus.ACTIVE
            ),
            key=lambda card: card.secondary_mission_id,
        )
    )


def _event_companion_tactical_replacement_enabled(state: GameState) -> bool:
    mission_setup = state.mission_setup
    return (
        mission_setup is not None
        and mission_setup.mission_pack_id == EVENT_COMPANION_MISSION_PACK_ID
    )


def _tactical_secondary_procedure_source_id(state: GameState) -> str:
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Tactical secondary procedure requires MissionSetup.")
    return f"{mission_setup.source_id}:secondary:tactical-procedure"


def _validate_tactical_secondary_replacement_context(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    secondary_mission_id: str | None,
    result: DecisionResult,
) -> None:
    drift_reason = _tactical_secondary_replacement_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result=result,
    )
    if drift_reason is not None:
        raise GameLifecycleError(f"Tactical secondary replacement drift: {drift_reason}.")


def _tactical_secondary_replacement_drift_reason(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    secondary_mission_id: str | None,
    result: DecisionResult,
) -> str | None:
    if result.actor_id != player_id:
        return "actor_player_drift"
    if _payload_string(payload, key="game_id") != state.game_id:
        return "game_id_drift"
    if _payload_string(payload, key="active_player_id") != _active_player_id(state):
        return "active_player_id_drift"
    if _payload_int(payload, key="battle_round") != state.battle_round:
        return "battle_round_drift"
    if _payload_string(payload, key="phase") != BattlePhase.COMMAND.value:
        return "payload_phase_drift"
    if state.current_battle_phase is not BattlePhase.COMMAND:
        return "phase_drift"
    if player_id != _active_player_id(state):
        return "player_not_active"
    if not _event_companion_tactical_replacement_enabled(state):
        return "tactical_replacement_not_enabled"
    choice = state.secondary_mission_choice_for_player(player_id)
    if choice is None or choice.mode is not SecondaryMissionMode.TACTICAL:
        return "player_not_using_tactical_secondaries"
    command_state = state.command_step_state
    if command_state is None:
        return "command_step_state_missing"
    if command_state.active_player_id != player_id:
        return "command_step_active_player_drift"
    if command_state.battle_round != state.battle_round:
        return "command_step_battle_round_drift"
    if not command_state.battle_shock_step_resolved:
        return "battle_shock_not_resolved"
    if command_state.tactical_secondary_replacement_resolved:
        return "replacement_already_resolved_this_phase"
    if state.has_tactical_secondary_replacement_use(player_id):
        return "replacement_already_used"
    if _payload_string(
        payload, key="replacement_source_id"
    ) != _tactical_secondary_procedure_source_id(state):
        return "replacement_source_id_drift"
    if _payload_int(payload, key="replacement_cost_cp") != 1:
        return "replacement_cost_cp_drift"
    if _payload_int(payload, key="replacement_discard_count") != 1:
        return "replacement_discard_count_drift"
    if _payload_int(payload, key="replacement_draw_count") != 1:
        return "replacement_draw_count_drift"
    if secondary_mission_id is None:
        return None
    if result.selected_option_id != f"replace:{secondary_mission_id}":
        return "selected_option_id_drift"
    if state.command_point_total(player_id) < 1:
        return "insufficient_command_points"
    active_ids = {
        card.secondary_mission_id
        for card in _active_tactical_secondary_cards(state=state, player_id=player_id)
    }
    if secondary_mission_id not in active_ids:
        return "card_not_active"
    return None


def _invalid_command_phase_start_faction_rule_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    payload = _decision_payload_object(result.payload)
    drift_reason = _command_phase_start_faction_rule_drift_reason(
        state=state,
        request=request,
        result=result,
        payload=payload,
    )
    if drift_reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Command phase start faction rule option drifted.",
        payload={
            "game_id": state.game_id,
            "player_id": result.actor_id,
            "battle_round": state.battle_round,
            "phase": (
                None if state.current_battle_phase is None else state.current_battle_phase.value
            ),
            "invalid_reason": drift_reason,
        },
    )


def _command_phase_start_faction_rule_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    payload: dict[str, JsonValue],
) -> str | None:
    if result.actor_id is None:
        return "actor_missing"
    if request.actor_id != result.actor_id:
        return "actor_player_drift"
    if _payload_string(payload, key="game_id") != state.game_id:
        return "game_id_drift"
    if _payload_int(payload, key="battle_round") != state.battle_round:
        return "battle_round_drift"
    if _payload_string(payload, key="phase") != BattlePhase.COMMAND.value:
        return "payload_phase_drift"
    if state.current_battle_phase is not BattlePhase.COMMAND:
        return "phase_drift"
    if result.actor_id != _active_player_id(state):
        return "player_not_active"
    request_payload = _decision_payload_object(request.payload)
    if _payload_string(request_payload, key="game_id") != state.game_id:
        return "request_game_id_drift"
    if _payload_int(request_payload, key="battle_round") != state.battle_round:
        return "request_battle_round_drift"
    if _payload_string(request_payload, key="phase") != BattlePhase.COMMAND.value:
        return "request_phase_drift"
    if _payload_string(request_payload, key="active_player_id") != result.actor_id:
        return "request_active_player_drift"
    command_state = state.command_step_state
    if command_state is None:
        return "command_step_state_missing"
    if command_state.active_player_id != result.actor_id:
        return "command_step_active_player_drift"
    if command_state.battle_round != state.battle_round:
        return "command_step_battle_round_drift"
    if not command_state.command_points_granted:
        return "command_points_not_granted"
    if command_state.scoring_hooks_resolved:
        return "command_phase_start_window_closed"
    target_unit_id = payload.get("target_unit_instance_id")
    target_owner_id = payload.get("target_owner_player_id")
    if target_unit_id is None and target_owner_id is None:
        return None
    if type(target_unit_id) is not str or not target_unit_id.strip():
        return "target_unit_instance_id_invalid"
    if type(target_owner_id) is not str or not target_owner_id.strip():
        return "target_owner_player_id_invalid"
    owner_id, target_unit = _unit_owner_and_instance_by_id(
        state=state,
        unit_instance_id=target_unit_id,
    )
    if owner_id is None or target_unit is None:
        return "target_unit_missing"
    if owner_id != target_owner_id:
        return "target_owner_drift"
    if owner_id == result.actor_id:
        return "target_not_opponent"
    if not target_unit.alive_own_models():
        return "target_unit_destroyed"
    return None


def _ensure_command_step_state(
    state: GameState,
    *,
    active_player_id: str,
) -> CommandStepState:
    if state.command_step_state is None:
        state.command_step_state = CommandStepState.start(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
        )
        return state.command_step_state
    command_state = state.command_step_state
    if command_state.active_player_id != active_player_id:
        raise GameLifecycleError("CommandStepState active player drift.")
    if command_state.battle_round != state.battle_round:
        raise GameLifecycleError("CommandStepState battle round drift.")
    return command_state


def _command_step_state(state: GameState) -> CommandStepState:
    if state.command_step_state is None:
        raise GameLifecycleError("Command phase requires CommandStepState.")
    return state.command_step_state


def _resolve_command_step_start(
    *,
    state: GameState,
    decisions: DecisionController,
    command_phase_start_hooks: CommandPhaseStartHookRegistry,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    cleared_battle_shocked_unit_ids = state.clear_battle_shock_for_player(active_player_id)
    gain_payloads: list[JsonValue] = []
    for player_id in state.player_ids:
        gain = state.gain_command_points(
            player_id=player_id,
            amount=1,
            source_id=(
                f"command-phase-start:round-{state.battle_round:02d}:active-{active_player_id}"
            ),
            source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
            cap_exempt=True,
        )
        if gain.status is not CommandPointGainStatus.APPLIED:
            raise GameLifecycleError("Command phase CP gain must not be capped.")
        gain_payload = validate_json_value(gain.to_payload())
        gain_payloads.append(gain_payload)
        decisions.event_log.append("command_points_gained", gain_payload)
    command_phase_start_hooks.resolve(
        CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id=active_player_id,
        )
    )
    state.command_step_state = _command_step_state(state).with_command_points_granted()
    decisions.event_log.append(
        "command_step_started",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "command_point_gains": gain_payloads,
            "cleared_battle_shocked_unit_ids": list(cleared_battle_shocked_unit_ids),
        },
    )
    faction_rule_request = command_phase_start_hooks.next_request_for(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id=active_player_id,
        )
    )
    if faction_rule_request is None:
        return None
    decisions.request_decision(faction_rule_request)
    decisions.event_log.append(
        "command_phase_start_faction_rule_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "decision_type": faction_rule_request.decision_type,
            "request_id": faction_rule_request.request_id,
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=faction_rule_request,
        payload={
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": active_player_id,
            "phase_body_status": "command_phase_start_faction_rule_pending",
        },
    )


def _resolve_command_phase_scoring_hooks(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    active_player_id = _active_player_id(state)
    decisions.event_log.append(
        "command_phase_scoring_hooks_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "timing": "command_step_after_cp_before_battle_shock",
        },
    )
    state.command_step_state = _command_step_state(state).with_scoring_hooks_resolved()


def _request_tactical_secondary_draw(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
) -> LifecycleStatus:
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
        actor_id=active_player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "draw_count": state.tactical_secondary_draw_count,
        },
        options=(
            DecisionOption(
                option_id="draw",
                label="Draw tactical secondary missions",
                payload={
                    "battle_round": state.battle_round,
                    "draw_count": state.tactical_secondary_draw_count,
                },
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": active_player_id,
            "phase_body_status": "tactical_secondary_draw_pending",
        },
    )


def _request_tactical_secondary_replacement_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
) -> LifecycleStatus | None:
    if not _event_companion_tactical_replacement_enabled(state):
        return None
    choice = state.secondary_mission_choice_for_player(active_player_id)
    if choice is None or choice.mode is not SecondaryMissionMode.TACTICAL:
        return None
    if state.has_tactical_secondary_replacement_use(active_player_id):
        return None
    if state.command_point_total(active_player_id) < 1:
        return None
    active_cards = _active_tactical_secondary_cards(state=state, player_id=active_player_id)
    if not active_cards:
        return None
    source_id = _tactical_secondary_procedure_source_id(state)
    common_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": active_player_id,
        "active_player_id": active_player_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "timing": "end_of_command_phase",
        "replacement_source_id": source_id,
        "replacement_cost_cp": 1,
        "replacement_discard_count": 1,
        "replacement_draw_count": 1,
    }
    legal_secondary_ids = tuple(card.secondary_mission_id for card in active_cards)
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
        actor_id=active_player_id,
        payload={
            **common_payload,
            "legal_secondary_mission_ids": list(legal_secondary_ids),
            "replacement_used": False,
        },
        options=(
            *(
                DecisionOption(
                    option_id=f"replace:{card.secondary_mission_id}",
                    label=f"Replace {card.secondary_mission_id}",
                    payload={
                        **common_payload,
                        "secondary_mission_id": card.secondary_mission_id,
                    },
                )
                for card in active_cards
            ),
            DecisionOption(
                option_id=TACTICAL_SECONDARY_REPLACEMENT_DECLINE_OPTION_ID,
                label="Decline tactical secondary replacement",
                payload=common_payload,
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": active_player_id,
            "phase_body_status": "tactical_secondary_replacement_pending",
        },
    )


def _request_command_start_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    new_orders_context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=active_player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
        timing_window_id=_new_orders_timing_window_id(
            state=state,
            active_player_id=active_player_id,
        ),
    )
    if not stratagem_window_declined_for_context(decisions=decisions, context=new_orders_context):
        finite_options = stratagem_use_options_for_handler_from_index(
            state=state,
            index=stratagem_index,
            context=new_orders_context,
            handler_id=CORE_NEW_ORDERS_HANDLER_ID,
        )
        if finite_options:
            request = create_stratagem_use_decision_request(
                state=state,
                context=new_orders_context,
                options=(*finite_options, stratagem_decline_option()),
            )
            decisions.request_decision(request)
            return LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=request,
                payload={"pending_request_id": request.request_id},
            )

    insane_bravery_context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=active_player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
        timing_window_id=_insane_bravery_timing_window_id(
            state=state,
            active_player_id=active_player_id,
        ),
    )
    if stratagem_window_declined_for_context(
        decisions=decisions,
        context=insane_bravery_context,
    ):
        return None
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=stratagem_index,
        context=insane_bravery_context,
        handler_id=CORE_INSANE_BRAVERY_HANDLER_ID,
    )
    if proposal is None:
        return None
    return request_stratagem_target_proposal(
        state=state,
        decisions=decisions,
        proposal_request=proposal,
        allow_decline=True,
    )


def _new_orders_timing_window_id(
    *,
    state: GameState,
    active_player_id: str,
) -> str:
    return f"new-orders-command-round-{state.battle_round}-player-{active_player_id}"


def _insane_bravery_timing_window_id(
    *,
    state: GameState,
    active_player_id: str,
) -> str:
    return f"insane-bravery-battle-shock-round-{state.battle_round}-player-{active_player_id}"


def _battle_shock_auto_pass_effect(
    *,
    state: GameState,
    unit_instance_id: str,
) -> PersistingEffect | None:
    matched_effect: PersistingEffect | None = None
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        if not isinstance(effect.effect_payload, dict):
            continue
        if effect.effect_payload.get("effect_kind") != "battle_shock_auto_pass":
            continue
        if matched_effect is not None:
            raise GameLifecycleError("Multiple Battle-shock auto-pass effects matched.")
        matched_effect = effect
    return matched_effect


def _resolve_battle_shock_step(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_index: AbilityCatalogIndex,
) -> None:
    active_player_id = _active_player_id(state)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Battle-shock step requires battlefield_state.")
    army = state.army_definition_for_player(active_player_id)
    if army is None:
        raise GameLifecycleError("Battle-shock step requires active player's army.")

    state.command_step_state = _command_step_state(state).enter_battle_shock_step()
    phase_start_battle_shocked_unit_ids = tuple(state.battle_shocked_unit_ids)
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=active_player_id,
        army=army,
        battlefield_state=battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        state=state,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    result_payloads: list[JsonValue] = []
    for request in requests:
        decisions.event_log.append(
            "battle_shock_test_requested",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "battle_shock_test_request": validate_json_value(request.to_payload()),
            },
        )
        auto_pass_effect = _battle_shock_auto_pass_effect(
            state=state,
            unit_instance_id=request.unit_instance_id,
        )
        if auto_pass_effect is None:
            roll_state = manager.roll(request.spec)
        else:
            roll_state = manager.roll_fixed(request.spec, [6, 6])
            decisions.event_log.append(
                "battle_shock_test_auto_passed",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.COMMAND.value,
                    "unit_instance_id": request.unit_instance_id,
                    "persisting_effect": validate_json_value(auto_pass_effect.to_payload()),
                },
            )
        result = BattleShockResult.from_roll_state(
            result_id=f"{request.request_id}:result",
            request=request,
            roll_state=roll_state,
            modifiers=battle_shock_hooks.modifiers_for(
                BattleShockModifierContext(
                    state=state,
                    request=request,
                    active_player_id=active_player_id,
                    phase=BattlePhase.COMMAND,
                    phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
                )
            ),
        )
        state.record_battle_shock_result(result)
        result_payload = validate_json_value(result.to_payload())
        result_payloads.append(result_payload)
        decisions.event_log.append(
            "battle_shock_test_resolved",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "battle_shock_result": result_payload,
                "auto_passed": auto_pass_effect is not None,
            },
        )
        battle_shock_hooks.resolve_outcomes(
            BattleShockOutcomeContext(
                state=state,
                decisions=decisions,
                dice_manager=manager,
                result=result,
                active_player_id=active_player_id,
                phase=BattlePhase.COMMAND,
                auto_passed=auto_pass_effect is not None,
                phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
            )
        )
    state.command_step_state = _command_step_state(state).with_battle_shock_step_resolved()
    decisions.event_log.append(
        "battle_shock_step_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "battle_shock_test_count": len(requests),
            "battle_shock_results": result_payloads,
        },
    )
