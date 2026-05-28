from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.engine.army_mustering import ArmyMusteringError, muster_army
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PhaseHandler,
    PlaceholderPhaseHandler,
    SetupStep,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.phases.movement import (
    PLACE_REINFORCEMENT_UNIT_DECISION_TYPE,
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    MovementPhaseHandler,
)
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE, SetupFlow
from warhammer40k_core.engine.unit_coherency import assert_battlefield_units_in_coherency


class GameLifecyclePayload(TypedDict):
    config: GameConfigPayload | None
    state: GameStatePayload
    decisions: DecisionControllerPayload


MAX_LIFECYCLE_TRANSITIONS = 128
_MOVEMENT_DECISION_TYPES = frozenset(
    (
        SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
        SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
        PLACE_REINFORCEMENT_UNIT_DECISION_TYPE,
        DICE_REROLL_DECISION_TYPE,
    )
)


def _new_decision_controller() -> DecisionController:
    return DecisionController()


@dataclass(slots=True)
class GameLifecycle:
    decision_controller: DecisionController = field(default_factory=_new_decision_controller)
    state: GameState | None = None
    _config: GameConfig | None = None
    _setup_flow: SetupFlow = field(default_factory=SetupFlow)
    _command_phase_handler: CommandPhaseHandler = field(default_factory=CommandPhaseHandler)
    _movement_phase_handler: MovementPhaseHandler = field(default_factory=MovementPhaseHandler)
    _battle_round_flow: BattleRoundFlow | None = None

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("GameLifecycle config must be a GameConfig.")
        if self.state is not None:
            raise GameLifecycleError("GameLifecycle has already started.")
        self._config = config
        self._movement_phase_handler = MovementPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor
        )
        self.state = GameState.from_config(config)
        self._battle_round_flow = BattleRoundFlow(phase_handlers=self._phase_handlers())
        current_setup_step = self.state.current_setup_step
        if current_setup_step is None:
            raise GameLifecycleError("GameLifecycle start requires an initial setup step.")
        self.decision_controller.event_log.append(
            "lifecycle_started",
            {
                "game_id": self.state.game_id,
                "ruleset_descriptor_hash": self.state.ruleset_descriptor_hash,
                "setup_sequence": [step.value for step in self.state.setup_sequence],
                "battle_phase_sequence": [
                    phase.value for phase in self.state.battle_phase_sequence
                ],
            },
        )
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.SETUP,
            payload={
                "game_id": self.state.game_id,
                "current_setup_step": current_setup_step.value,
                "ruleset_descriptor_hash": self.state.ruleset_descriptor_hash,
            },
        )

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        for _transition_index in range(MAX_LIFECYCLE_TRANSITIONS):
            status = self._advance_once()
            if status.status_kind in (
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            ):
                return status
        raise GameLifecycleError("GameLifecycle exceeded deterministic transition guard.")

    def _advance_once(self) -> LifecycleStatus:
        state = self._require_state()
        pending_request = self._pending_decision_request()
        if pending_request is not None:
            return LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=pending_request,
                payload={
                    "game_id": state.game_id,
                    "pending_request_id": pending_request.request_id,
                },
            )
        if state.stage is GameLifecycleStage.COMPLETE:
            return LifecycleStatus.terminal(
                stage=GameLifecycleStage.COMPLETE,
                message="Game lifecycle is complete.",
                payload={"game_id": state.game_id},
            )
        if state.stage is GameLifecycleStage.SETUP:
            return self._setup_flow.advance(
                state=state,
                decisions=self.decision_controller,
                config=self._require_config(),
            )
        return self._require_battle_round_flow().advance(
            state=state,
            decisions=self.decision_controller,
        )

    def submit_decision(self, result: DecisionResult) -> LifecycleStatus:
        state = self._require_state()
        record = self.decision_controller.submit_result(result)
        if record.request.decision_type == SECONDARY_MISSION_DECISION_TYPE:
            self._setup_flow.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE:
            self._command_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            return self.advance_until_decision_or_terminal()
        if record.request.decision_type in _MOVEMENT_DECISION_TYPES:
            movement_status = self._movement_phase_handler.apply_decision(
                state=state,
                result=result,
                decisions=self.decision_controller,
            )
            if movement_status is not None:
                return movement_status
            return self.advance_until_decision_or_terminal()
        raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")

    def to_payload(self) -> GameLifecyclePayload:
        state = self._require_state()
        return {
            "config": None if self._config is None else self._config.to_payload(),
            "state": state.to_payload(),
            "decisions": self.decision_controller.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: GameLifecyclePayload) -> Self:
        config_payload = payload["config"]
        config = None if config_payload is None else GameConfig.from_payload(config_payload)
        lifecycle = cls(
            decision_controller=DecisionController.from_payload(payload["decisions"]),
            state=GameState.from_payload(payload["state"]),
            _config=config,
            _movement_phase_handler=MovementPhaseHandler(
                ruleset_descriptor=None if config is None else config.ruleset_descriptor
            ),
        )
        _validate_payload_consistency(state=lifecycle._require_state(), config=lifecycle._config)
        lifecycle._battle_round_flow = BattleRoundFlow(phase_handlers=lifecycle._phase_handlers())
        return lifecycle

    def _phase_handlers(self) -> Mapping[BattlePhase, PhaseHandler]:
        return {
            BattlePhase.COMMAND: self._command_phase_handler,
            BattlePhase.MOVEMENT: self._movement_phase_handler,
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
            BattlePhase.CHARGE: PlaceholderPhaseHandler(BattlePhase.CHARGE),
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        }

    def _pending_decision_request(self) -> DecisionRequest | None:
        pending_requests = self.decision_controller.queue.pending_requests
        if not pending_requests:
            return None
        return pending_requests[0]

    def _require_state(self) -> GameState:
        if self.state is None:
            raise GameLifecycleError("GameLifecycle has not started.")
        return self.state

    def _require_config(self) -> GameConfig:
        if self._config is None:
            raise GameLifecycleError("GameLifecycle config is unavailable.")
        return self._config

    def _require_battle_round_flow(self) -> BattleRoundFlow:
        if self._battle_round_flow is None:
            raise GameLifecycleError("GameLifecycle battle round flow is unavailable.")
        return self._battle_round_flow


def _validate_payload_consistency(*, state: GameState, config: GameConfig | None) -> None:
    _validate_reserve_state_consistency(state=state)
    _validate_transport_cargo_state_consistency(state=state)
    _validate_battlefield_state_consistency(state=state, config=config)
    _validate_movement_phase_state_consistency(state=state)
    _validate_disembarked_unit_state_consistency(state=state)
    _validate_advanced_unit_state_consistency(state=state)
    _validate_fell_back_unit_state_consistency(state=state)
    if config is None:
        return
    if state.game_id != config.game_id:
        raise GameLifecycleError("Lifecycle state game_id does not match config.")
    if state.player_ids != config.player_ids:
        raise GameLifecycleError("Lifecycle state player_ids do not match config.")
    if state.turn_order != config.turn_order:
        raise GameLifecycleError("Lifecycle state turn_order does not match config.")
    if state.tactical_secondary_draw_count != config.tactical_secondary_draw_count:
        raise GameLifecycleError(
            "Lifecycle state tactical secondary draw count does not match config."
        )
    expected_hash = config.ruleset_descriptor.descriptor_hash
    if state.ruleset_descriptor_hash != expected_hash:
        raise GameLifecycleError("Lifecycle state ruleset hash does not match config.")
    expected_setup = tuple(config.ruleset_descriptor.setup_sequence.steps)
    if state.setup_sequence != expected_setup:
        raise GameLifecycleError("Lifecycle state setup sequence does not match config.")
    expected_battle = tuple(config.ruleset_descriptor.battle_phase_sequence.phases)
    if state.battle_phase_sequence != expected_battle:
        raise GameLifecycleError("Lifecycle state battle phase sequence does not match config.")
    _validate_mustered_army_consistency(state=state, config=config)


def _validate_mustered_army_consistency(*, state: GameState, config: GameConfig) -> None:
    if not state.army_definitions and not _state_requires_mustered_armies(state):
        return
    try:
        expected_armies = tuple(
            sorted(
                (
                    muster_army(catalog=config.army_catalog, request=request)
                    for request in config.army_muster_requests
                ),
                key=lambda army: army.player_id,
            )
        )
    except ArmyMusteringError as exc:
        raise GameLifecycleError("Lifecycle config army muster requests are invalid.") from exc
    expected_payloads = [army.to_payload() for army in expected_armies]
    state_payloads = [army.to_payload() for army in state.army_definitions]
    if _state_requires_mustered_armies(state) and not state_payloads:
        raise GameLifecycleError("Lifecycle state is missing mustered army definitions.")
    if state_payloads and state_payloads != expected_payloads:
        raise GameLifecycleError("Lifecycle state army definitions do not match config.")


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
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        if _state_requires_battlefield_state(state):
            scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
        if config is not None:
            assert_battlefield_units_in_coherency(
                scenario=scenario,
                ruleset_descriptor=config.ruleset_descriptor,
            )
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state battlefield_state is invalid.") from exc


def _validate_reserve_state_consistency(*, state: GameState) -> None:
    if not state.reserve_states:
        return
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    for reserve_state in state.reserve_states:
        owner = unit_owner_by_id.get(reserve_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("reserve_states unit is unknown.")
        if owner != reserve_state.player_id:
            raise GameLifecycleError("reserve_states player_id does not match unit owner.")
        for embarked_unit_id in reserve_state.embarked_unit_instance_ids:
            embarked_owner = unit_owner_by_id.get(embarked_unit_id)
            if embarked_owner is None:
                raise GameLifecycleError("reserve_states embarked unit is unknown.")
            if embarked_owner != reserve_state.player_id:
                raise GameLifecycleError("reserve_states embarked unit owner drift.")

    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for reserve_state in state.reserve_states:
        reserve_model_ids = set(model_ids_by_unit_id[reserve_state.unit_instance_id])
        embarked_model_ids = {
            model_id
            for embarked_unit_id in reserve_state.embarked_unit_instance_ids
            for model_id in model_ids_by_unit_id[embarked_unit_id]
        }
        if reserve_state.status is ReserveStatus.IN_RESERVES:
            if (reserve_model_ids | embarked_model_ids) & placed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be placed.")
            if (reserve_model_ids | embarked_model_ids) & removed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be removed.")
        if reserve_state.status is ReserveStatus.ARRIVED:
            if not reserve_model_ids <= placed_model_ids:
                raise GameLifecycleError("arrived reserve unit models must be placed.")
            if reserve_model_ids & removed_model_ids:
                raise GameLifecycleError("arrived reserve unit models must not be removed.")
        if (
            reserve_state.status is ReserveStatus.DESTROYED
            and not (reserve_model_ids | embarked_model_ids) <= removed_model_ids
        ):
            raise GameLifecycleError("destroyed reserve models must be removed.")


def _validate_transport_cargo_state_consistency(*, state: GameState) -> None:
    if not state.transport_cargo_states:
        return
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    embarked_unit_ids: set[str] = set()
    for cargo_state in state.transport_cargo_states:
        transport = unit_by_id.get(cargo_state.transport_unit_instance_id)
        if transport is None:
            raise GameLifecycleError("transport_cargo_states transport unit is unknown.")
        if owner_by_unit_id[cargo_state.transport_unit_instance_id] != cargo_state.player_id:
            raise GameLifecycleError("transport_cargo_states player_id does not match owner.")
        if transport.datasheet_id != cargo_state.capacity_profile.transport_datasheet_id:
            raise GameLifecycleError("transport_cargo_states transport datasheet drift.")
        cargo_model_count = 0
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            embarked_unit = unit_by_id.get(embarked_unit_id)
            if embarked_unit is None:
                raise GameLifecycleError("transport_cargo_states embarked unit is unknown.")
            if owner_by_unit_id[embarked_unit_id] != cargo_state.player_id:
                raise GameLifecycleError("transport_cargo_states embarked unit owner drift.")
            if embarked_unit_id in embarked_unit_ids:
                raise GameLifecycleError("unit cannot be embarked in more than one Transport.")
            embarked_unit_ids.add(embarked_unit_id)
            if not cargo_state.capacity_profile.allows_unit(embarked_unit):
                raise GameLifecycleError("transport_cargo_states capacity profile rejects cargo.")
            cargo_model_count += len(embarked_unit.own_models)
        if cargo_model_count > cargo_state.capacity_profile.max_model_count:
            raise GameLifecycleError("transport_cargo_states capacity is exceeded.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    for cargo_state in state.transport_cargo_states:
        for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
            model_ids = set(model_ids_by_unit_id[embarked_unit_id])
            if model_ids & placed_model_ids:
                raise GameLifecycleError("embarked unit models must not be placed.")
            if model_ids & removed_model_ids:
                raise GameLifecycleError("embarked unit models must not be removed.")


def _validate_movement_phase_state_consistency(*, state: GameState) -> None:
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

    try:
        placed_army = scenario.battlefield_state.placed_army_for_player(state.active_player_id)
        active_player_unit_ids: set[str] = {
            placement.unit_instance_id for placement in placed_army.unit_placements
        }
    except PlacementError:
        active_player_unit_ids = set()
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    fully_removed_active_player_unit_ids: set[str] = set()
    for army_definition in state.army_definitions:
        if army_definition.player_id != state.active_player_id:
            continue
        for unit in army_definition.units:
            unit_model_ids = {model.model_instance_id for model in unit.own_models}
            if unit_model_ids and unit_model_ids <= removed_model_ids:
                fully_removed_active_player_unit_ids.add(unit.unit_instance_id)
    for unit_id in (*movement_state.selected_unit_ids, *movement_state.moved_unit_ids):
        if (
            unit_id not in active_player_unit_ids
            and unit_id not in fully_removed_active_player_unit_ids
        ):
            raise GameLifecycleError(
                "movement_phase_state selected unit is not active player's unit."
            )
    if movement_state.active_selection is None:
        return
    active_unit_id = movement_state.active_selection.unit_instance_id
    if active_unit_id not in movement_state.selected_unit_ids:
        raise GameLifecycleError("movement_phase_state active selection drift.")
    if active_unit_id not in active_player_unit_ids:
        raise GameLifecycleError(
            "movement_phase_state active selection is not active player's unit."
        )


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
    for advanced_state in state.advanced_unit_states:
        if advanced_state.player_id != state.active_player_id:
            raise GameLifecycleError("advanced_unit_states player drift.")
        if advanced_state.battle_round != state.battle_round:
            raise GameLifecycleError("advanced_unit_states battle round drift.")
        if advanced_state.unit_instance_id not in active_player_unit_ids:
            raise GameLifecycleError("advanced_unit_states unit is not active player's unit.")


def _validate_disembarked_unit_state_consistency(*, state: GameState) -> None:
    if not state.disembarked_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("disembarked_unit_states require battle stage.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for disembarked_state in state.disembarked_unit_states:
        owner = unit_owner_by_id.get(disembarked_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("disembarked_unit_states unit is unknown.")
        if owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states player drift.")
        transport_owner = unit_owner_by_id.get(disembarked_state.transport_unit_instance_id)
        if transport_owner is None:
            raise GameLifecycleError("disembarked_unit_states transport unit is unknown.")
        if transport_owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states transport owner drift.")


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
    for fell_back_state in state.fell_back_unit_states:
        if fell_back_state.player_id != state.active_player_id:
            raise GameLifecycleError("fell_back_unit_states player drift.")
        if fell_back_state.battle_round != state.battle_round:
            raise GameLifecycleError("fell_back_unit_states battle round drift.")
        if fell_back_state.unit_instance_id not in active_player_unit_ids:
            raise GameLifecycleError("fell_back_unit_states unit is not active player's unit.")


def _state_requires_mustered_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        muster_step_index = state.setup_sequence.index(SetupStep.MUSTER_ARMIES)
    except ValueError as exc:
        raise GameLifecycleError(
            "Lifecycle state setup sequence must include MUSTER_ARMIES."
        ) from exc
    return state.setup_step_index > muster_step_index


def _state_requires_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        deploy_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    except ValueError:
        return False
    return state.setup_step_index > deploy_step_index


def _state_allows_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    try:
        deploy_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    except ValueError:
        return False
    return state.setup_step_index > deploy_step_index
