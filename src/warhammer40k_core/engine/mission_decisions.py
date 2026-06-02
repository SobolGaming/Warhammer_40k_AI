from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.missions import MissionActionDefinition
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack

TACTICAL_SECONDARY_DISCARD_DECISION_TYPE = "discard_tactical_secondary_mission"
START_MISSION_ACTION_DECISION_TYPE = "start_mission_action"
MISSION_DECISION_TYPES = frozenset(
    (TACTICAL_SECONDARY_DISCARD_DECISION_TYPE, START_MISSION_ACTION_DECISION_TYPE)
)


@dataclass(frozen=True, slots=True)
class MissionActionStartOption:
    action: MissionActionDefinition
    unit_instance_id: str
    target_id: str
    eligible_unit_instance_ids: tuple[str, ...]

    def option_id(self) -> str:
        return f"start:{self.action.mission_action_id}:{self.unit_instance_id}:{self.target_id}"

    def payload(
        self,
        *,
        state: GameState,
        player_id: str,
        phase: BattlePhase,
    ) -> JsonValue:
        return {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "mission_action_id": self.action.mission_action_id,
            "mission_id": self.action.mission_id,
            "mission_kind": self.action.mission_kind,
            "unit_instance_id": self.unit_instance_id,
            "target_id": self.target_id,
            "start_timing": self.action.start_timing,
            "completion_timing": self.action.completion_timing,
            "eligible_unit_instance_ids": list(self.eligible_unit_instance_ids),
            "interruption_conditions": list(self.action.interruption_conditions),
            "scoring_source_id": self.action.scoring_source_id,
            "victory_points": self.action.victory_points,
        }


def request_tactical_secondary_discard(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
) -> LifecycleStatus:
    _assert_battle_state(state)
    requested_player = _validate_player_id(state=state, player_id=player_id)
    phase = _current_phase(state)
    active_cards = _active_tactical_secondary_cards(state=state, player_id=requested_player)
    if not active_cards:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="No active Tactical secondary mission cards can be discarded.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "decision_type": TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
            },
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
        actor_id=requested_player,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "legal_secondary_mission_ids": [card.secondary_mission_id for card in active_cards],
        },
        options=tuple(
            DecisionOption(
                option_id=f"discard:{card.secondary_mission_id}",
                label=f"Discard {card.secondary_mission_id}",
                payload={
                    "game_id": state.game_id,
                    "player_id": requested_player,
                    "battle_round": state.battle_round,
                    "phase": phase.value,
                    "secondary_mission_id": card.secondary_mission_id,
                },
            )
            for card in active_cards
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "decision_type": TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
        },
    )


def request_mission_action_start(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    mission_action_id: str,
) -> LifecycleStatus:
    _assert_battle_state(state)
    requested_player = _validate_player_id(state=state, player_id=player_id)
    phase = _current_phase(state)
    mission_action = _mission_action_for_state(state=state, mission_action_id=mission_action_id)
    if mission_action.target_policy != "objective_marker":
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Mission Action target selection is not implemented for this target policy.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
                "target_policy": mission_action.target_policy,
            },
        )
    if phase.value != mission_action.start_phase:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Mission Action cannot start in the current battle phase.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
                "current_phase": phase.value,
                "required_phase": mission_action.start_phase,
            },
        )
    options = _mission_action_start_options(
        state=state,
        player_id=requested_player,
        action=mission_action,
    )
    if not options:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="No legal Mission Action start options are available.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
            },
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=START_MISSION_ACTION_DECISION_TYPE,
        actor_id=requested_player,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "mission_action_id": mission_action.mission_action_id,
            "legal_option_ids": [option.option_id() for option in options],
        },
        options=tuple(
            DecisionOption(
                option_id=option.option_id(),
                label=f"Start {option.action.mission_action_id}",
                payload=option.payload(
                    state=state,
                    player_id=requested_player,
                    phase=phase,
                ),
            )
            for option in options
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "decision_type": START_MISSION_ACTION_DECISION_TYPE,
        },
    )


def invalid_mission_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE:
        payload = _payload_object(result.payload)
        player_id = _payload_string(payload, key="player_id")
        secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
        if (
            state.secondary_mission_card_state(
                player_id=player_id,
                secondary_mission_id=secondary_mission_id,
                mode=SecondaryMissionCardMode.TACTICAL,
            )
            is None
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Tactical secondary discard option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "secondary_mission_id": secondary_mission_id,
                },
            )
        return None
    if request.decision_type == START_MISSION_ACTION_DECISION_TYPE:
        payload = _payload_object(result.payload)
        player_id = _payload_string(payload, key="player_id")
        mission_action_id = _payload_string(payload, key="mission_action_id")
        unit_instance_id = _payload_string(payload, key="unit_instance_id")
        target_id = _payload_string(payload, key="target_id")
        try:
            action = _mission_action_for_state(
                state=state,
                mission_action_id=mission_action_id,
            )
            option_ids = {
                option.option_id()
                for option in _mission_action_start_options(
                    state=state,
                    player_id=player_id,
                    action=action,
                )
            }
        except PlacementError as exc:
            raise GameLifecycleError("Mission Action drift validation failed.") from exc
        if f"start:{mission_action_id}:{unit_instance_id}:{target_id}" not in option_ids:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Mission Action start option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "mission_action_id": mission_action_id,
                    "unit_instance_id": unit_instance_id,
                    "target_id": target_id,
                },
            )
        return None
    raise GameLifecycleError("Mission decision validator received unsupported decision_type.")


def apply_mission_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    if result.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE:
        _apply_tactical_secondary_discard(state=state, result=result, decisions=decisions)
        return
    if result.decision_type == START_MISSION_ACTION_DECISION_TYPE:
        _apply_start_mission_action(state=state, result=result, decisions=decisions)
        return
    raise GameLifecycleError("Mission decision handler received unsupported decision_type.")


def _apply_tactical_secondary_discard(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
    _validate_decision_context(state=state, payload=payload, player_id=player_id, result=result)
    discarded = state.discard_tactical_secondary(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result_id=result.result_id,
    )
    decisions.event_log.append(
        "tactical_secondary_mission_discarded",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "secondary_mission_card_state": validate_json_value(discarded.to_payload()),
        },
    )


def _apply_start_mission_action(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    _validate_decision_context(state=state, payload=payload, player_id=player_id, result=result)
    mission_action = _mission_action_for_state(
        state=state,
        mission_action_id=_payload_string(payload, key="mission_action_id"),
    )
    action_state = MissionActionState.start(
        action_id=f"mission-action:{result.result_id}",
        player_id=player_id,
        unit_instance_id=_payload_string(payload, key="unit_instance_id"),
        target_id=_payload_string(payload, key="target_id"),
        mission_id=mission_action.mission_id,
        battle_round=state.battle_round,
        phase=_current_phase(state).value,
        start_timing=mission_action.start_timing,
        completion_timing=mission_action.completion_timing,
        eligible_unit_instance_ids=tuple(
            _payload_string_list(payload, key="eligible_unit_instance_ids")
        ),
        interruption_conditions=mission_action.interruption_conditions,
        scoring_source_id=mission_action.scoring_source_id,
        victory_points=mission_action.victory_points,
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )
    state.record_mission_action_state(action_state)
    decisions.event_log.append(
        "mission_action_started",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "mission_action_id": mission_action.mission_action_id,
            "target_id": _payload_string(payload, key="target_id"),
            "mission_action_state": validate_json_value(action_state.to_payload()),
        },
    )


def _mission_action_start_options(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
) -> tuple[MissionActionStartOption, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Mission Action start requires battlefield_state.")
    if state.mission_setup is None:
        raise GameLifecycleError("Mission Action start requires MissionSetup.")
    if action.target_policy != "objective_marker":
        raise GameLifecycleError("Unsupported Mission Action target policy.")
    try:
        placed_army = battlefield_state.placed_army_for_player(player_id)
    except PlacementError:
        return ()
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )
    eligible_unit_ids = _eligible_unit_instance_ids_for_action(
        scenario=scenario,
        unit_placements=placed_army.unit_placements,
        action=action,
    )
    target_ids_by_unit = _objective_marker_target_ids_by_unit(
        state=state,
        player_id=player_id,
    )
    eligible_target_pairs = tuple(
        (unit_id, target_id)
        for unit_id in eligible_unit_ids
        for target_id in target_ids_by_unit.get(unit_id, ())
        if unit_id not in state.battle_shocked_unit_ids
    )
    if not eligible_target_pairs:
        return ()
    return tuple(
        MissionActionStartOption(
            action=action,
            unit_instance_id=unit_id,
            target_id=target_id,
            eligible_unit_instance_ids=eligible_unit_ids,
        )
        for unit_id, target_id in eligible_target_pairs
    )


def _eligible_unit_instance_ids_for_action(
    *,
    scenario: BattlefieldScenario,
    unit_placements: tuple[object, ...],
    action: MissionActionDefinition,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.battlefield_state import UnitPlacement

    eligible_ids: list[str] = []
    for placement in unit_placements:
        if type(placement) is not UnitPlacement:
            raise GameLifecycleError("Mission Action options require UnitPlacement values.")
        unit = scenario.unit_instance_for_placement(placement)
        if _unit_matches_eligible_policy(unit.keywords, action.eligible_unit_policy):
            eligible_ids.append(placement.unit_instance_id)
    return tuple(sorted(eligible_ids))


def _unit_matches_eligible_policy(
    keywords: tuple[str, ...],
    eligible_unit_policy: str,
) -> bool:
    policy = _validate_identifier("eligible_unit_policy", eligible_unit_policy)
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    if policy == "active_player_unit":
        return True
    if policy == "active_player_infantry_or_battleline_unit":
        return bool(keyword_set.intersection({"INFANTRY", "BATTLELINE"}))
    raise GameLifecycleError("Unsupported Mission Action eligible unit policy.")


def _objective_marker_target_ids_by_unit(
    *,
    state: GameState,
    player_id: str,
) -> dict[str, tuple[str, ...]]:
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=_current_phase(state),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    )
    targets_by_unit: dict[str, set[str]] = {}
    for result in record.results:
        for contribution in result.contributors:
            if contribution.player_id != player_id:
                continue
            targets_by_unit.setdefault(contribution.unit_instance_id, set()).add(
                result.objective_id
            )
    return {
        unit_id: tuple(sorted(target_ids))
        for unit_id, target_ids in sorted(targets_by_unit.items(), key=lambda item: item[0])
    }


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).replace("-", " ").replace("_", " ").upper()


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


def _mission_action_for_state(
    *,
    state: GameState,
    mission_action_id: str,
) -> MissionActionDefinition:
    if state.mission_setup is None:
        raise GameLifecycleError("Mission Action start requires MissionSetup.")
    mission_pack = chapter_approved_2025_26_mission_pack()
    if state.mission_setup.mission_pack_id != mission_pack.mission_pack_id:
        raise GameLifecycleError("Unsupported mission pack for Mission Action start.")
    return mission_pack.mission_action(mission_action_id)


def _validate_decision_context(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    result: DecisionResult,
) -> None:
    if result.actor_id != player_id:
        raise GameLifecycleError("Mission decision actor/player drift.")
    if _payload_string(payload, key="game_id") != state.game_id:
        raise GameLifecycleError("Mission decision game_id drift.")
    if _payload_int(payload, key="battle_round") != state.battle_round:
        raise GameLifecycleError("Mission decision battle_round drift.")
    if _payload_string(payload, key="phase") != _current_phase(state).value:
        raise GameLifecycleError("Mission decision phase drift.")


def _assert_battle_state(state: GameState) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Mission decision requires GameState.")
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Mission decision can be applied only during battle.")


def _current_phase(state: GameState) -> BattlePhase:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Mission decision requires a battle phase.")
    return phase


def _validate_player_id(*, state: GameState, player_id: str) -> str:
    requested_player = _validate_identifier("player_id", player_id)
    if requested_player not in state.player_ids:
        raise GameLifecycleError("Mission decision player_id is not in this game.")
    if state.active_player_id != requested_player:
        raise GameLifecycleError("Mission decision player_id must be the active player.")
    return requested_player


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Mission decision payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    return _validate_identifier(key, value)


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> list[str]:
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Mission decision payload key must be a list: {key}.")
    return [_validate_identifier(f"{key} value", item) for item in cast(list[object], value)]


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Mission decision payload key must be an integer: {key}.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
