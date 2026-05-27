from __future__ import annotations

from itertools import combinations

from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusteringError, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    ModelPlacementRecord,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    secondary_mission_mode_from_token,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario

SECONDARY_MISSION_DECISION_TYPE = "select_secondary_missions"


class SetupFlow:
    def advance(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("SetupFlow can advance only during setup.")
        current_step = state.current_setup_step
        if current_step is None:
            raise GameLifecycleError("SetupFlow requires a current setup step.")

        if current_step is SetupStep.SELECT_SECONDARY_MISSIONS:
            next_player_id = self._next_secondary_mission_player_id(state)
            if next_player_id is not None:
                request = self._secondary_mission_request(
                    state=state,
                    config=config,
                    player_id=next_player_id,
                )
                decisions.request_decision(request)
                return LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.SETUP,
                    decision_request=request,
                    payload={
                        "setup_step": current_step.value,
                        "player_id": next_player_id,
                    },
                )
        elif current_step is SetupStep.MUSTER_ARMIES:
            self._muster_armies(state=state, decisions=decisions, config=config)
        elif current_step is SetupStep.DEPLOY_ARMIES:
            self._place_mustered_armies(state=state, decisions=decisions)

        completed_step = state.complete_current_setup_step()
        decisions.event_log.append(
            "setup_step_completed",
            {
                "game_id": state.game_id,
                "step": completed_step.value,
                "stage": state.stage.value,
                "next_setup_step": (
                    None if state.current_setup_step is None else state.current_setup_step.value
                ),
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "battle_phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
            },
        )
        return LifecycleStatus.advanced(
            stage=state.stage,
            payload={
                "completed_setup_step": completed_step.value,
                "current_setup_step": (
                    None if state.current_setup_step is None else state.current_setup_step.value
                ),
                "battle_phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
            },
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> None:
        if result.decision_type != SECONDARY_MISSION_DECISION_TYPE:
            raise GameLifecycleError("SetupFlow received an unsupported decision_type.")
        if state.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("Secondary mission decisions can be applied only in setup.")
        if state.current_setup_step is not SetupStep.SELECT_SECONDARY_MISSIONS:
            raise GameLifecycleError(
                "Secondary mission decisions can be applied only during SELECT_SECONDARY_MISSIONS."
            )
        if result.actor_id is None:
            raise GameLifecycleError("Secondary mission decisions require an actor_id.")
        payload = _decision_payload_object(result.payload)
        mode = secondary_mission_mode_from_token(_payload_string(payload, key="mode"))
        fixed_mission_ids = _payload_string_list(payload, key="fixed_mission_ids")
        choice = SecondaryMissionChoice(
            player_id=result.actor_id,
            mode=mode,
            fixed_mission_ids=fixed_mission_ids,
        )
        state.record_secondary_mission_choice(choice)
        decisions.event_log.append(
            "secondary_mission_choice_recorded",
            {
                "game_id": state.game_id,
                "player_id": result.actor_id,
                "setup_step": SetupStep.SELECT_SECONDARY_MISSIONS.value,
                "mode_recorded": True,
                "fixed_choice_count": len(choice.fixed_mission_ids),
            },
        )

    def _next_secondary_mission_player_id(self, state: GameState) -> str | None:
        missing_players = state.missing_secondary_mission_player_ids()
        if not missing_players:
            return None
        return missing_players[0]

    def _muster_armies(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> None:
        missing_player_ids = set(state.missing_army_player_ids())
        if not missing_player_ids:
            return
        army_definitions: list[ArmyDefinition] = []
        for request in config.army_muster_requests:
            if request.player_id not in missing_player_ids:
                continue
            try:
                army_definitions.append(muster_army(catalog=config.army_catalog, request=request))
            except ArmyMusteringError as exc:
                raise GameLifecycleError("MUSTER_ARMIES failed during army mustering.") from exc
        for army_definition in army_definitions:
            state.record_army_definition(army_definition)
            decisions.event_log.append(
                "army_mustered",
                {
                    "game_id": state.game_id,
                    "setup_step": SetupStep.MUSTER_ARMIES.value,
                    "player_id": army_definition.player_id,
                    "army_id": army_definition.army_id,
                    "unit_count": len(army_definition.units),
                },
            )
        if state.missing_army_player_ids():
            raise GameLifecycleError("MUSTER_ARMIES requires an army for every player.")

    def _place_mustered_armies(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> None:
        if state.battlefield_state is not None:
            return
        if state.missing_army_player_ids():
            raise GameLifecycleError("DEPLOY_ARMIES requires mustered armies for every player.")
        scenario = create_deterministic_battlefield_scenario(
            battlefield_id=f"{state.game_id}:phase10a-battlefield",
            armies=tuple(state.army_definitions),
        )
        state.record_battlefield_state(scenario.battlefield_state)
        transition_batch = BattlefieldTransitionBatch(
            placements=tuple(
                ModelPlacementRecord(
                    model_instance_id=model_placement.model_instance_id,
                    placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
                    pose=model_placement.pose,
                    source_phase=None,
                    source_step=SetupStep.DEPLOY_ARMIES.value,
                    source_rule_id="phase10a_deterministic_bridge",
                    source_event_id=None,
                )
                for placed_army in scenario.battlefield_state.placed_armies
                for unit_placement in placed_army.unit_placements
                for model_placement in unit_placement.model_placements
            )
        )
        decisions.event_log.append(
            "battlefield_placement_created",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DEPLOY_ARMIES.value,
                "battlefield_id": scenario.battlefield_state.battlefield_id,
                "placed_army_count": len(scenario.battlefield_state.placed_armies),
                "placed_model_count": len(scenario.battlefield_state.placed_model_ids()),
                "placement_source": "phase10a_deterministic_bridge",
            },
        )
        decisions.event_log.append(
            "battlefield_models_placed",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DEPLOY_ARMIES.value,
                "battlefield_id": scenario.battlefield_state.battlefield_id,
                "placement_kind": BattlefieldPlacementKind.DEPLOYMENT.value,
                "placed_model_count": len(scenario.battlefield_state.placed_model_ids()),
                "transition_batch": transition_batch.to_payload(),
            },
        )

    def _secondary_mission_request(
        self,
        *,
        state: GameState,
        config: GameConfig,
        player_id: str,
    ) -> DecisionRequest:
        return DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SECONDARY_MISSION_DECISION_TYPE,
            actor_id=player_id,
            payload={
                "game_id": state.game_id,
                "setup_step": SetupStep.SELECT_SECONDARY_MISSIONS.value,
                "secret": True,
                "fixed_choices_required": 2,
            },
            options=_secondary_mission_options(config.fixed_secondary_mission_ids),
        )


def _secondary_mission_options(
    fixed_secondary_mission_ids: tuple[str, ...],
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id="tactical",
            label="Tactical",
            payload={
                "mode": SecondaryMissionMode.TACTICAL.value,
                "fixed_mission_ids": [],
            },
        )
    ]
    for first_id, second_id in combinations(fixed_secondary_mission_ids, 2):
        options.append(
            DecisionOption(
                option_id=f"fixed:{first_id}:{second_id}",
                label=f"Fixed {first_id} {second_id}",
                payload={
                    "mode": SecondaryMissionMode.FIXED.value,
                    "fixed_mission_ids": [first_id, second_id],
                },
            )
        )
    return tuple(options)


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload key must be a string list: {key}.")
    strings: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Decision payload key must contain strings: {key}.")
        strings.append(item)
    return tuple(strings)
