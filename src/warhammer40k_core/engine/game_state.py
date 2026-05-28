from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogPayload
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    RulesetDescriptor,
    RulesetDescriptorPayload,
    SetupStepKind,
    battle_phase_kind_from_token,
    setup_step_kind_from_token,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
    ArmyMusterRequest,
    ArmyMusterRequestPayload,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldRuntimeStatePayload,
    PlacementError,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    SetupStep,
    game_lifecycle_stage_from_token,
)
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    AdvancedUnitStatePayload,
    FellBackUnitState,
    FellBackUnitStatePayload,
    MovementPhaseState,
    MovementPhaseStatePayload,
)
from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload, ReserveStatus


class SecondaryMissionMode(StrEnum):
    FIXED = "fixed"
    TACTICAL = "tactical"


class GameConfigPayload(TypedDict):
    game_id: str
    ruleset_descriptor: RulesetDescriptorPayload
    army_catalog: ArmyCatalogPayload
    army_muster_requests: list[ArmyMusterRequestPayload]
    player_ids: list[str]
    turn_order: list[str]
    fixed_secondary_mission_ids: list[str]
    tactical_secondary_draw_count: int


class SecondaryMissionChoicePayload(TypedDict):
    player_id: str
    mode: str
    fixed_mission_ids: list[str]


class TacticalSecondaryDrawPayload(TypedDict):
    player_id: str
    battle_round: int
    request_id: str
    result_id: str
    draw_count: int


class GameStatePayload(TypedDict):
    game_id: str
    ruleset_descriptor_hash: str
    stage: str
    setup_sequence: list[str]
    battle_phase_sequence: list[str]
    setup_step_index: int | None
    battle_phase_index: int | None
    battle_round: int
    active_player_id: str | None
    player_ids: list[str]
    turn_order: list[str]
    decision_request_count: int
    tactical_secondary_draw_count: int
    army_definitions: list[ArmyDefinitionPayload]
    battlefield_state: BattlefieldRuntimeStatePayload | None
    movement_phase_state: MovementPhaseStatePayload | None
    reserve_states: list[ReserveStatePayload]
    advanced_unit_states: list[AdvancedUnitStatePayload]
    fell_back_unit_states: list[FellBackUnitStatePayload]
    battle_shocked_unit_ids: list[str]
    secondary_mission_choices: list[SecondaryMissionChoicePayload]
    tactical_secondary_draws: list[TacticalSecondaryDrawPayload]


def _new_secondary_mission_choices() -> list[SecondaryMissionChoice]:
    return []


def _new_tactical_secondary_draws() -> list[TacticalSecondaryDraw]:
    return []


def _new_advanced_unit_states() -> list[AdvancedUnitState]:
    return []


def _new_fell_back_unit_states() -> list[FellBackUnitState]:
    return []


def _new_reserve_states() -> list[ReserveState]:
    return []


def _new_battle_shocked_unit_ids() -> list[str]:
    return []


def _new_army_definitions() -> list[ArmyDefinition]:
    return []


@dataclass(frozen=True, slots=True)
class GameConfig:
    game_id: str
    ruleset_descriptor: RulesetDescriptor
    army_catalog: ArmyCatalog
    army_muster_requests: tuple[ArmyMusterRequest, ...]
    player_ids: tuple[str, ...]
    turn_order: tuple[str, ...]
    fixed_secondary_mission_ids: tuple[str, ...]
    tactical_secondary_draw_count: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("GameConfig game_id", self.game_id),
        )
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("GameConfig ruleset_descriptor must be a RulesetDescriptor.")
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("GameConfig army_catalog must be an ArmyCatalog.")
        object.__setattr__(
            self,
            "player_ids",
            _validate_identifier_tuple(
                "GameConfig player_ids",
                self.player_ids,
                min_length=2,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "army_muster_requests",
            _validate_army_muster_requests(
                self.army_muster_requests,
                player_ids=self.player_ids,
            ),
        )
        object.__setattr__(
            self,
            "turn_order",
            _validate_turn_order(self.turn_order, player_ids=self.player_ids),
        )
        object.__setattr__(
            self,
            "fixed_secondary_mission_ids",
            _validate_identifier_tuple(
                "GameConfig fixed_secondary_mission_ids",
                self.fixed_secondary_mission_ids,
                min_length=2,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "tactical_secondary_draw_count",
            _validate_positive_int(
                "GameConfig tactical_secondary_draw_count",
                self.tactical_secondary_draw_count,
            ),
        )
        _validate_lifecycle_sequences(self.ruleset_descriptor)

    def to_payload(self) -> GameConfigPayload:
        return {
            "game_id": self.game_id,
            "ruleset_descriptor": self.ruleset_descriptor.to_payload(),
            "army_catalog": self.army_catalog.to_payload(),
            "army_muster_requests": [request.to_payload() for request in self.army_muster_requests],
            "player_ids": list(self.player_ids),
            "turn_order": list(self.turn_order),
            "fixed_secondary_mission_ids": list(self.fixed_secondary_mission_ids),
            "tactical_secondary_draw_count": self.tactical_secondary_draw_count,
        }

    @classmethod
    def from_payload(cls, payload: GameConfigPayload) -> Self:
        return cls(
            game_id=payload["game_id"],
            ruleset_descriptor=RulesetDescriptor.from_payload(payload["ruleset_descriptor"]),
            army_catalog=ArmyCatalog.from_payload(payload["army_catalog"]),
            army_muster_requests=tuple(
                _army_muster_request_from_payload(request)
                for request in payload["army_muster_requests"]
            ),
            player_ids=tuple(payload["player_ids"]),
            turn_order=tuple(payload["turn_order"]),
            fixed_secondary_mission_ids=tuple(payload["fixed_secondary_mission_ids"]),
            tactical_secondary_draw_count=payload["tactical_secondary_draw_count"],
        )


@dataclass(frozen=True, slots=True)
class SecondaryMissionChoice:
    player_id: str
    mode: SecondaryMissionMode
    fixed_mission_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SecondaryMissionChoice player_id", self.player_id),
        )
        object.__setattr__(self, "mode", secondary_mission_mode_from_token(self.mode))
        fixed_mission_ids = _validate_identifier_tuple(
            "SecondaryMissionChoice fixed_mission_ids",
            self.fixed_mission_ids,
            min_length=0,
            sort_values=True,
        )
        if self.mode is SecondaryMissionMode.FIXED and len(fixed_mission_ids) != 2:
            raise GameLifecycleError(
                "SecondaryMissionChoice fixed mode requires exactly two fixed missions."
            )
        if self.mode is SecondaryMissionMode.TACTICAL and fixed_mission_ids:
            raise GameLifecycleError(
                "SecondaryMissionChoice tactical mode must not include fixed missions."
            )
        object.__setattr__(self, "fixed_mission_ids", fixed_mission_ids)

    def to_payload(self) -> SecondaryMissionChoicePayload:
        return {
            "player_id": self.player_id,
            "mode": self.mode.value,
            "fixed_mission_ids": list(self.fixed_mission_ids),
        }

    @classmethod
    def from_payload(cls, payload: SecondaryMissionChoicePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            mode=secondary_mission_mode_from_token(payload["mode"]),
            fixed_mission_ids=tuple(payload["fixed_mission_ids"]),
        )

    def to_public_payload(self, *, viewer_player_id: str) -> dict[str, JsonValue]:
        if self.player_id != viewer_player_id:
            return {
                "player_id": self.player_id,
                "selected": True,
                "hidden": True,
            }
        return {
            "player_id": self.player_id,
            "selected": True,
            "hidden": False,
            "mode": self.mode.value,
            "fixed_mission_ids": list(self.fixed_mission_ids),
        }


@dataclass(frozen=True, slots=True)
class TacticalSecondaryDraw:
    player_id: str
    battle_round: int
    request_id: str
    result_id: str
    draw_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("TacticalSecondaryDraw player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("TacticalSecondaryDraw battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("TacticalSecondaryDraw request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("TacticalSecondaryDraw result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "draw_count",
            _validate_positive_int("TacticalSecondaryDraw draw_count", self.draw_count),
        )

    def to_payload(self) -> TacticalSecondaryDrawPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "draw_count": self.draw_count,
        }

    @classmethod
    def from_payload(cls, payload: TacticalSecondaryDrawPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            draw_count=payload["draw_count"],
        )


@dataclass(slots=True)
class GameState:
    game_id: str
    ruleset_descriptor_hash: str
    stage: GameLifecycleStage
    setup_sequence: tuple[SetupStep, ...]
    battle_phase_sequence: tuple[BattlePhase, ...]
    player_ids: tuple[str, ...]
    turn_order: tuple[str, ...]
    tactical_secondary_draw_count: int
    setup_step_index: int | None = 0
    battle_phase_index: int | None = None
    battle_round: int = 0
    active_player_id: str | None = None
    decision_request_count: int = 0
    army_definitions: list[ArmyDefinition] = field(default_factory=_new_army_definitions)
    battlefield_state: BattlefieldRuntimeState | None = None
    movement_phase_state: MovementPhaseState | None = None
    reserve_states: list[ReserveState] = field(default_factory=_new_reserve_states)
    advanced_unit_states: list[AdvancedUnitState] = field(default_factory=_new_advanced_unit_states)
    fell_back_unit_states: list[FellBackUnitState] = field(
        default_factory=_new_fell_back_unit_states
    )
    battle_shocked_unit_ids: list[str] = field(default_factory=_new_battle_shocked_unit_ids)
    secondary_mission_choices: list[SecondaryMissionChoice] = field(
        default_factory=_new_secondary_mission_choices
    )
    tactical_secondary_draws: list[TacticalSecondaryDraw] = field(
        default_factory=_new_tactical_secondary_draws
    )

    def __post_init__(self) -> None:
        self.game_id = _validate_identifier("GameState game_id", self.game_id)
        self.ruleset_descriptor_hash = _validate_descriptor_hash(
            "GameState ruleset_descriptor_hash",
            self.ruleset_descriptor_hash,
        )
        self.stage = game_lifecycle_stage_from_token(self.stage)
        self.setup_sequence = _validate_setup_sequence(self.setup_sequence)
        self.battle_phase_sequence = _validate_battle_phase_sequence(self.battle_phase_sequence)
        self.player_ids = _validate_identifier_tuple(
            "GameState player_ids",
            self.player_ids,
            min_length=2,
            sort_values=False,
        )
        self.turn_order = _validate_turn_order(self.turn_order, player_ids=self.player_ids)
        self.tactical_secondary_draw_count = _validate_positive_int(
            "GameState tactical_secondary_draw_count",
            self.tactical_secondary_draw_count,
        )
        self.setup_step_index = _validate_optional_index(
            "GameState setup_step_index",
            self.setup_step_index,
            length=len(self.setup_sequence),
        )
        self.battle_phase_index = _validate_optional_index(
            "GameState battle_phase_index",
            self.battle_phase_index,
            length=len(self.battle_phase_sequence),
        )
        self.battle_round = _validate_non_negative_int(
            "GameState battle_round",
            self.battle_round,
        )
        self.active_player_id = _validate_optional_player_id(
            "GameState active_player_id",
            self.active_player_id,
            player_ids=self.player_ids,
        )
        self.decision_request_count = _validate_non_negative_int(
            "GameState decision_request_count",
            self.decision_request_count,
        )
        self.army_definitions = _validate_army_definitions(
            self.army_definitions,
            player_ids=self.player_ids,
        )
        self.battlefield_state = _validate_optional_battlefield_state(self.battlefield_state)
        self.movement_phase_state = _validate_optional_movement_phase_state(
            self.movement_phase_state
        )
        self.reserve_states = _validate_reserve_states(
            self.reserve_states,
            player_ids=self.player_ids,
        )
        self.advanced_unit_states = _validate_advanced_unit_states(
            self.advanced_unit_states,
            player_ids=self.player_ids,
        )
        self.fell_back_unit_states = _validate_fell_back_unit_states(
            self.fell_back_unit_states,
            player_ids=self.player_ids,
        )
        self.battle_shocked_unit_ids = list(
            _validate_identifier_tuple(
                "GameState battle_shocked_unit_ids",
                tuple(self.battle_shocked_unit_ids),
                min_length=0,
                sort_values=True,
            )
        )
        self.secondary_mission_choices = _validate_secondary_choices(
            self.secondary_mission_choices,
            player_ids=self.player_ids,
        )
        self.tactical_secondary_draws = _validate_tactical_draws(
            self.tactical_secondary_draws,
            player_ids=self.player_ids,
        )
        _validate_state_stage_indexes(self)

    @classmethod
    def from_config(cls, config: GameConfig) -> Self:
        return cls(
            game_id=config.game_id,
            ruleset_descriptor_hash=config.ruleset_descriptor.descriptor_hash,
            stage=GameLifecycleStage.SETUP,
            setup_sequence=tuple(config.ruleset_descriptor.setup_sequence.steps),
            battle_phase_sequence=tuple(config.ruleset_descriptor.battle_phase_sequence.phases),
            player_ids=config.player_ids,
            turn_order=config.turn_order,
            tactical_secondary_draw_count=config.tactical_secondary_draw_count,
        )

    @property
    def current_setup_step(self) -> SetupStep | None:
        if self.setup_step_index is None:
            return None
        return self.setup_sequence[self.setup_step_index]

    @property
    def current_battle_phase(self) -> BattlePhase | None:
        if self.battle_phase_index is None:
            return None
        return self.battle_phase_sequence[self.battle_phase_index]

    def next_decision_request_id(self) -> str:
        self.decision_request_count += 1
        return f"decision-request-{self.decision_request_count:06d}"

    def complete_current_setup_step(self) -> SetupStep:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can complete setup steps only during setup.")
        current = self.current_setup_step
        if current is None or self.setup_step_index is None:
            raise GameLifecycleError("GameState has no current setup step.")
        if self.setup_step_index + 1 < len(self.setup_sequence):
            self.setup_step_index += 1
            return current
        self.setup_step_index = None
        self.enter_battle()
        return current

    def enter_battle(self) -> None:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can enter battle only from setup.")
        self.stage = GameLifecycleStage.BATTLE
        self.battle_round = 1
        self.active_player_id = self.turn_order[0]
        self.battle_phase_index = 0

    def advance_to_next_battle_phase(self) -> BattlePhase:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can advance battle phases only during battle.")
        if self.battle_phase_index is None:
            raise GameLifecycleError("GameState has no current battle phase.")
        completed_phase = self.battle_phase_sequence[self.battle_phase_index]
        if self.battle_phase_index + 1 < len(self.battle_phase_sequence):
            if completed_phase is BattlePhase.MOVEMENT:
                self.movement_phase_state = None
            self.battle_phase_index += 1
            return completed_phase
        completed_player_id = self.active_player_id
        if completed_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        self._clear_turn_action_states(
            player_id=completed_player_id,
            battle_round=self.battle_round,
        )
        if completed_phase is BattlePhase.MOVEMENT:
            self.movement_phase_state = None
        self.battle_phase_index = 0
        self._advance_active_player_after_completed_turn()
        return completed_phase

    def record_secondary_mission_choice(self, choice: SecondaryMissionChoice) -> None:
        if choice.player_id not in self.player_ids:
            raise GameLifecycleError("SecondaryMissionChoice player_id is not in this game.")
        if self.secondary_mission_choice_for_player(choice.player_id) is not None:
            raise GameLifecycleError("SecondaryMissionChoice already exists for player.")
        self.secondary_mission_choices.append(choice)
        self.secondary_mission_choices.sort(key=lambda stored: stored.player_id)

    def secondary_mission_choice_for_player(
        self,
        player_id: str,
    ) -> SecondaryMissionChoice | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for choice in self.secondary_mission_choices:
            if choice.player_id == requested_player_id:
                return choice
        return None

    def missing_secondary_mission_player_ids(self) -> tuple[str, ...]:
        selected = {choice.player_id for choice in self.secondary_mission_choices}
        return tuple(player_id for player_id in self.player_ids if player_id not in selected)

    def record_army_definition(self, army_definition: ArmyDefinition) -> None:
        if type(army_definition) is not ArmyDefinition:
            raise GameLifecycleError("GameState army_definition must be an ArmyDefinition.")
        if army_definition.player_id not in self.player_ids:
            raise GameLifecycleError("ArmyDefinition player_id is not in this game.")
        if self.army_definition_for_player(army_definition.player_id) is not None:
            raise GameLifecycleError("ArmyDefinition already exists for player.")
        self.army_definitions.append(army_definition)
        self.army_definitions.sort(key=lambda stored: stored.player_id)

    def army_definition_for_player(self, player_id: str) -> ArmyDefinition | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for army_definition in self.army_definitions:
            if army_definition.player_id == requested_player_id:
                return army_definition
        return None

    def missing_army_player_ids(self) -> tuple[str, ...]:
        mustered = {army_definition.player_id for army_definition in self.army_definitions}
        return tuple(player_id for player_id in self.player_ids if player_id not in mustered)

    def record_battlefield_state(self, battlefield_state: BattlefieldRuntimeState) -> None:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError(
                "GameState battlefield_state must be a BattlefieldRuntimeState."
            )
        if self.battlefield_state is not None:
            raise GameLifecycleError("GameState battlefield_state already exists.")
        self.battlefield_state = battlefield_state

    def record_tactical_secondary_draw(self, draw: TacticalSecondaryDraw) -> None:
        if draw.player_id not in self.player_ids:
            raise GameLifecycleError("TacticalSecondaryDraw player_id is not in this game.")
        if self.has_tactical_secondary_draw(
            player_id=draw.player_id,
            battle_round=draw.battle_round,
        ):
            raise GameLifecycleError("TacticalSecondaryDraw already exists for player and round.")
        self.tactical_secondary_draws.append(draw)
        self.tactical_secondary_draws.sort(
            key=lambda stored: (stored.battle_round, stored.player_id)
        )

    def has_tactical_secondary_draw(self, *, player_id: str, battle_round: int) -> bool:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        return any(
            draw.player_id == requested_player_id and draw.battle_round == requested_round
            for draw in self.tactical_secondary_draws
        )

    def record_reserve_state(self, reserve_state: ReserveState) -> None:
        if type(reserve_state) is not ReserveState:
            raise GameLifecycleError("reserve_state must be a ReserveState.")
        if reserve_state.player_id not in self.player_ids:
            raise GameLifecycleError("ReserveState player_id is not in this game.")
        if self.reserve_state_for_unit(reserve_state.unit_instance_id) is not None:
            raise GameLifecycleError("ReserveState already exists for unit.")
        self.reserve_states.append(reserve_state)
        self.reserve_states.sort(key=lambda state: state.unit_instance_id)

    def reserve_state_for_unit(self, unit_instance_id: str) -> ReserveState | None:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for reserve_state in self.reserve_states:
            if reserve_state.unit_instance_id == requested_unit_id:
                return reserve_state
        return None

    def replace_reserve_state(self, reserve_state: ReserveState) -> None:
        if type(reserve_state) is not ReserveState:
            raise GameLifecycleError("reserve_state must be a ReserveState.")
        for index, stored in enumerate(self.reserve_states):
            if stored.unit_instance_id == reserve_state.unit_instance_id:
                self.reserve_states[index] = reserve_state
                self.reserve_states.sort(key=lambda state: state.unit_instance_id)
                return
        raise GameLifecycleError("ReserveState does not exist for unit.")

    def unarrived_reserve_states_for_player(self, player_id: str) -> tuple[ReserveState, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return tuple(
            reserve_state
            for reserve_state in self.reserve_states
            if reserve_state.player_id == requested_player_id
            and reserve_state.status is ReserveStatus.IN_RESERVES
        )

    def unarrived_reserve_model_ids(self) -> tuple[str, ...]:
        if not self.reserve_states:
            return ()
        unit_by_id = {
            unit.unit_instance_id: unit for army in self.army_definitions for unit in army.units
        }
        model_ids: list[str] = []
        for reserve_state in self.reserve_states:
            if reserve_state.status is not ReserveStatus.IN_RESERVES:
                continue
            impacted_unit_ids = (
                reserve_state.unit_instance_id,
                *reserve_state.embarked_unit_instance_ids,
            )
            for unit_id in impacted_unit_ids:
                unit = unit_by_id.get(unit_id)
                if unit is None:
                    raise GameLifecycleError("ReserveState references an unknown unit.")
                model_ids.extend(model.model_instance_id for model in unit.own_models)
        return tuple(sorted(model_ids))

    def record_advanced_unit_state(self, state: AdvancedUnitState) -> None:
        if type(state) is not AdvancedUnitState:
            raise GameLifecycleError("Advanced unit state must be an AdvancedUnitState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("AdvancedUnitState player_id is not in this game.")
        if (
            self.advanced_unit_state_for_unit(
                player_id=state.player_id,
                battle_round=state.battle_round,
                unit_instance_id=state.unit_instance_id,
            )
            is not None
        ):
            raise GameLifecycleError("AdvancedUnitState already exists for unit and turn.")
        self.advanced_unit_states.append(state)
        self.advanced_unit_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.player_id,
                stored.unit_instance_id,
            )
        )

    def advanced_unit_state_for_unit(
        self,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
    ) -> AdvancedUnitState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for state in self.advanced_unit_states:
            if (
                state.player_id == requested_player_id
                and state.battle_round == requested_round
                and state.unit_instance_id == requested_unit_id
            ):
                return state
        return None

    def record_fell_back_unit_state(self, state: FellBackUnitState) -> None:
        if type(state) is not FellBackUnitState:
            raise GameLifecycleError("Fell Back unit state must be a FellBackUnitState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("FellBackUnitState player_id is not in this game.")
        if (
            self.fell_back_unit_state_for_unit(
                player_id=state.player_id,
                battle_round=state.battle_round,
                unit_instance_id=state.unit_instance_id,
            )
            is not None
        ):
            raise GameLifecycleError("FellBackUnitState already exists for unit and turn.")
        self.fell_back_unit_states.append(state)
        self.fell_back_unit_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.player_id,
                stored.unit_instance_id,
            )
        )

    def fell_back_unit_state_for_unit(
        self,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
    ) -> FellBackUnitState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for state in self.fell_back_unit_states:
            if (
                state.player_id == requested_player_id
                and state.battle_round == requested_round
                and state.unit_instance_id == requested_unit_id
            ):
                return state
        return None

    def to_payload(self) -> GameStatePayload:
        return {
            "game_id": self.game_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "stage": self.stage.value,
            "setup_sequence": [step.value for step in self.setup_sequence],
            "battle_phase_sequence": [phase.value for phase in self.battle_phase_sequence],
            "setup_step_index": self.setup_step_index,
            "battle_phase_index": self.battle_phase_index,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "player_ids": list(self.player_ids),
            "turn_order": list(self.turn_order),
            "decision_request_count": self.decision_request_count,
            "tactical_secondary_draw_count": self.tactical_secondary_draw_count,
            "army_definitions": [army.to_payload() for army in self.army_definitions],
            "battlefield_state": (
                None if self.battlefield_state is None else self.battlefield_state.to_payload()
            ),
            "movement_phase_state": (
                None
                if self.movement_phase_state is None
                else self.movement_phase_state.to_payload()
            ),
            "reserve_states": [state.to_payload() for state in self.reserve_states],
            "advanced_unit_states": [state.to_payload() for state in self.advanced_unit_states],
            "fell_back_unit_states": [state.to_payload() for state in self.fell_back_unit_states],
            "battle_shocked_unit_ids": list(self.battle_shocked_unit_ids),
            "secondary_mission_choices": [
                choice.to_payload() for choice in self.secondary_mission_choices
            ],
            "tactical_secondary_draws": [
                draw.to_payload() for draw in self.tactical_secondary_draws
            ],
        }

    def to_public_payload(self, *, viewer_player_id: str) -> dict[str, JsonValue]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        public_choices: list[dict[str, JsonValue]] = []
        for player_id in self.player_ids:
            choice = self.secondary_mission_choice_for_player(player_id)
            if choice is None:
                public_choices.append(
                    {
                        "player_id": player_id,
                        "selected": False,
                        "hidden": player_id != viewer,
                    }
                )
                continue
            public_choices.append(choice.to_public_payload(viewer_player_id=viewer))

        payload = cast(dict[str, JsonValue], self.to_payload())
        payload["secondary_mission_choices"] = cast(JsonValue, public_choices)
        validate_json_value(payload)
        return payload

    @classmethod
    def from_payload(cls, payload: GameStatePayload) -> Self:
        return cls(
            game_id=payload["game_id"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            stage=game_lifecycle_stage_from_token(payload["stage"]),
            setup_sequence=tuple(
                setup_step_kind_from_token(step) for step in payload["setup_sequence"]
            ),
            battle_phase_sequence=tuple(
                battle_phase_kind_from_token(phase) for phase in payload["battle_phase_sequence"]
            ),
            player_ids=tuple(payload["player_ids"]),
            turn_order=tuple(payload["turn_order"]),
            tactical_secondary_draw_count=payload["tactical_secondary_draw_count"],
            setup_step_index=payload["setup_step_index"],
            battle_phase_index=payload["battle_phase_index"],
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            decision_request_count=payload["decision_request_count"],
            army_definitions=[
                _army_definition_from_payload(army) for army in payload["army_definitions"]
            ],
            battlefield_state=(
                None
                if payload["battlefield_state"] is None
                else _battlefield_state_from_payload(payload["battlefield_state"])
            ),
            movement_phase_state=(
                None
                if payload["movement_phase_state"] is None
                else MovementPhaseState.from_payload(payload["movement_phase_state"])
            ),
            reserve_states=[
                ReserveState.from_payload(state) for state in payload["reserve_states"]
            ],
            advanced_unit_states=[
                AdvancedUnitState.from_payload(state) for state in payload["advanced_unit_states"]
            ],
            fell_back_unit_states=[
                FellBackUnitState.from_payload(state) for state in payload["fell_back_unit_states"]
            ],
            battle_shocked_unit_ids=list(payload["battle_shocked_unit_ids"]),
            secondary_mission_choices=[
                SecondaryMissionChoice.from_payload(choice)
                for choice in payload["secondary_mission_choices"]
            ],
            tactical_secondary_draws=[
                TacticalSecondaryDraw.from_payload(draw)
                for draw in payload["tactical_secondary_draws"]
            ],
        )

    def _advance_active_player_after_completed_turn(self) -> None:
        if self.active_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        active_index = self.turn_order.index(self.active_player_id)
        if active_index + 1 < len(self.turn_order):
            self.active_player_id = self.turn_order[active_index + 1]
            return
        self.active_player_id = self.turn_order[0]
        self.battle_round += 1

    def _clear_turn_action_states(self, *, player_id: str, battle_round: int) -> None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        self.advanced_unit_states = [
            state
            for state in self.advanced_unit_states
            if not (
                state.player_id == requested_player_id and state.battle_round == requested_round
            )
        ]
        self.fell_back_unit_states = [
            state
            for state in self.fell_back_unit_states
            if not (
                state.player_id == requested_player_id and state.battle_round == requested_round
            )
        ]
        self.reserve_states = [
            state.clear_expired_post_arrival_restrictions(
                player_id=requested_player_id,
                battle_round=requested_round,
            )
            for state in self.reserve_states
        ]


def secondary_mission_mode_from_token(token: object) -> SecondaryMissionMode:
    if type(token) is SecondaryMissionMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SecondaryMissionMode token must be a string.")
    try:
        return SecondaryMissionMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SecondaryMissionMode token: {token}.") from exc


def _army_muster_request_from_payload(payload: ArmyMusterRequestPayload) -> ArmyMusterRequest:
    try:
        return ArmyMusterRequest.from_payload(payload)
    except ArmyMusteringError as exc:
        raise GameLifecycleError("GameConfig army_muster_request payload is invalid.") from exc


def _army_definition_from_payload(payload: ArmyDefinitionPayload) -> ArmyDefinition:
    try:
        return ArmyDefinition.from_payload(payload)
    except ArmyMusteringError as exc:
        raise GameLifecycleError("GameState army_definition payload is invalid.") from exc


def _battlefield_state_from_payload(
    payload: BattlefieldRuntimeStatePayload,
) -> BattlefieldRuntimeState:
    try:
        return BattlefieldRuntimeState.from_payload(payload)
    except PlacementError as exc:
        raise GameLifecycleError("GameState battlefield_state payload is invalid.") from exc


def _validate_lifecycle_sequences(ruleset_descriptor: RulesetDescriptor) -> None:
    setup_steps = ruleset_descriptor.setup_sequence.steps
    phases = ruleset_descriptor.battle_phase_sequence.phases
    if SetupStepKind.MUSTER_ARMIES not in setup_steps:
        raise GameLifecycleError("GameConfig setup_sequence must include MUSTER_ARMIES.")
    if SetupStepKind.SELECT_SECONDARY_MISSIONS not in setup_steps:
        raise GameLifecycleError(
            "GameConfig setup_sequence must include SELECT_SECONDARY_MISSIONS."
        )
    if SetupStepKind.DETERMINE_FIRST_TURN not in setup_steps:
        raise GameLifecycleError("GameConfig setup_sequence must include DETERMINE_FIRST_TURN.")
    if phases[0] is not BattlePhaseKind.COMMAND:
        raise GameLifecycleError("GameConfig battle_phase_sequence must start with COMMAND.")
    if BattlePhaseKind.FIGHT not in phases:
        raise GameLifecycleError("GameConfig battle_phase_sequence must include FIGHT.")
    if phases[-1] is not BattlePhaseKind.FIGHT:
        raise GameLifecycleError("GameConfig battle_phase_sequence must end with FIGHT.")


def _validate_army_muster_requests(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> tuple[ArmyMusterRequest, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameConfig army_muster_requests must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if len(raw_values) != len(player_ids):
        raise GameLifecycleError(
            "GameConfig army_muster_requests must include every player exactly once."
        )
    validated: list[ArmyMusterRequest] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ArmyMusterRequest:
            raise GameLifecycleError(
                "GameConfig army_muster_requests must contain ArmyMusterRequest values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("ArmyMusterRequest player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameConfig army_muster_requests must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError(
            "GameConfig army_muster_requests must include every player exactly once."
        )
    return tuple(sorted(validated, key=lambda request: request.player_id))


def _validate_army_definitions(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[ArmyDefinition]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState army_definitions must be a list.")
    validated: list[ArmyDefinition] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not ArmyDefinition:
            raise GameLifecycleError(
                "GameState army_definitions must contain ArmyDefinition values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("ArmyDefinition player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameState army_definitions must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    return sorted(validated, key=lambda stored: stored.player_id)


def _validate_optional_battlefield_state(
    value: object | None,
) -> BattlefieldRuntimeState | None:
    if value is None:
        return None
    if type(value) is not BattlefieldRuntimeState:
        raise GameLifecycleError("GameState battlefield_state must be a BattlefieldRuntimeState.")
    return value


def _validate_optional_movement_phase_state(
    value: object | None,
) -> MovementPhaseState | None:
    if value is None:
        return None
    if type(value) is not MovementPhaseState:
        raise GameLifecycleError("GameState movement_phase_state must be a MovementPhaseState.")
    return value


def _validate_reserve_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[ReserveState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState reserve_states must be a list.")
    validated: list[ReserveState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not ReserveState:
            raise GameLifecycleError("GameState reserve_states must contain ReserveState values.")
        if value.player_id not in player_ids:
            raise GameLifecycleError("ReserveState player_id is not in this game.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState reserve_states must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.unit_instance_id)


def _validate_advanced_unit_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[AdvancedUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState advanced_unit_states must be a list.")
    validated: list[AdvancedUnitState] = []
    seen: set[tuple[int, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not AdvancedUnitState:
            raise GameLifecycleError(
                "GameState advanced_unit_states must contain AdvancedUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("AdvancedUnitState player_id is not in this game.")
        key = (value.battle_round, value.player_id, value.unit_instance_id)
        if key in seen:
            raise GameLifecycleError("GameState advanced_unit_states must be unique.")
        seen.add(key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (state.battle_round, state.player_id, state.unit_instance_id),
    )


def _validate_fell_back_unit_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[FellBackUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState fell_back_unit_states must be a list.")
    validated: list[FellBackUnitState] = []
    seen: set[tuple[int, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not FellBackUnitState:
            raise GameLifecycleError(
                "GameState fell_back_unit_states must contain FellBackUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("FellBackUnitState player_id is not in this game.")
        key = (value.battle_round, value.player_id, value.unit_instance_id)
        if key in seen:
            raise GameLifecycleError("GameState fell_back_unit_states must be unique.")
        seen.add(key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (state.battle_round, state.player_id, state.unit_instance_id),
    )


def _validate_state_stage_indexes(state: GameState) -> None:
    if state.stage is GameLifecycleStage.SETUP:
        if state.setup_step_index is None:
            raise GameLifecycleError("GameState setup stage requires a setup_step_index.")
        if state.battle_phase_index is not None:
            raise GameLifecycleError("GameState setup stage must not have a battle_phase_index.")
        if state.battle_round != 0:
            raise GameLifecycleError("GameState setup stage must have battle_round 0.")
        if state.active_player_id is not None:
            raise GameLifecycleError("GameState setup stage must not have an active player.")
        return
    if state.stage is GameLifecycleStage.BATTLE:
        if state.setup_step_index is not None:
            raise GameLifecycleError("GameState battle stage must not have a setup_step_index.")
        if state.battle_phase_index is None:
            raise GameLifecycleError("GameState battle stage requires a battle_phase_index.")
        if state.battle_round < 1:
            raise GameLifecycleError("GameState battle stage requires battle_round >= 1.")
        if state.active_player_id is None:
            raise GameLifecycleError("GameState battle stage requires an active player.")
        return
    if state.setup_step_index is not None or state.battle_phase_index is not None:
        raise GameLifecycleError("GameState complete stage must not have active indexes.")


def _validate_setup_sequence(values: object) -> tuple[SetupStep, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameState setup_sequence must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    steps = tuple(setup_step_kind_from_token(step) for step in raw_values)
    if not steps:
        raise GameLifecycleError("GameState setup_sequence must not be empty.")
    return steps


def _validate_battle_phase_sequence(values: object) -> tuple[BattlePhase, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameState battle_phase_sequence must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    phases = tuple(battle_phase_kind_from_token(phase) for phase in raw_values)
    if not phases:
        raise GameLifecycleError("GameState battle_phase_sequence must not be empty.")
    if phases[-1] is not BattlePhaseKind.FIGHT:
        raise GameLifecycleError("GameState battle_phase_sequence must end with FIGHT.")
    return phases


def _validate_turn_order(values: object, *, player_ids: tuple[str, ...]) -> tuple[str, ...]:
    turn_order = _validate_identifier_tuple(
        "turn_order",
        values,
        min_length=len(player_ids),
        sort_values=False,
    )
    if len(turn_order) != len(player_ids):
        raise GameLifecycleError("turn_order must include every player exactly once.")
    if set(turn_order) != set(player_ids):
        raise GameLifecycleError("turn_order must match player_ids.")
    return turn_order


def _validate_secondary_choices(
    choices: object,
    *,
    player_ids: tuple[str, ...],
) -> list[SecondaryMissionChoice]:
    if not isinstance(choices, list):
        raise GameLifecycleError("GameState secondary_mission_choices must be a list.")
    validated: list[SecondaryMissionChoice] = []
    seen: set[str] = set()
    for choice in cast(list[object], choices):
        if type(choice) is not SecondaryMissionChoice:
            raise GameLifecycleError(
                "GameState secondary_mission_choices must contain SecondaryMissionChoice values."
            )
        if choice.player_id not in player_ids:
            raise GameLifecycleError("SecondaryMissionChoice player_id is not in this game.")
        if choice.player_id in seen:
            raise GameLifecycleError("GameState secondary_mission_choices must be unique.")
        seen.add(choice.player_id)
        validated.append(choice)
    return sorted(validated, key=lambda stored: stored.player_id)


def _validate_tactical_draws(
    draws: object,
    *,
    player_ids: tuple[str, ...],
) -> list[TacticalSecondaryDraw]:
    if not isinstance(draws, list):
        raise GameLifecycleError("GameState tactical_secondary_draws must be a list.")
    validated: list[TacticalSecondaryDraw] = []
    seen: set[tuple[int, str]] = set()
    for draw in cast(list[object], draws):
        if type(draw) is not TacticalSecondaryDraw:
            raise GameLifecycleError(
                "GameState tactical_secondary_draws must contain TacticalSecondaryDraw values."
            )
        if draw.player_id not in player_ids:
            raise GameLifecycleError("TacticalSecondaryDraw player_id is not in this game.")
        key = (draw.battle_round, draw.player_id)
        if key in seen:
            raise GameLifecycleError("GameState tactical_secondary_draws must be unique.")
        seen.add(key)
        validated.append(draw)
    return sorted(validated, key=lambda stored: (stored.battle_round, stored.player_id))


def _validate_optional_index(field_name: str, value: object | None, *, length: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer or null.")
    if value < 0 or value >= length:
        raise GameLifecycleError(f"{field_name} is outside the sequence.")
    return value


def _validate_optional_player_id(
    field_name: str,
    value: object | None,
    *,
    player_ids: tuple[str, ...],
) -> str | None:
    if value is None:
        return None
    player_id = _validate_identifier(field_name, value)
    if player_id not in player_ids:
        raise GameLifecycleError(f"{field_name} must be in player_ids.")
    return player_id


def _validate_player_id(value: object, *, player_ids: tuple[str, ...]) -> str:
    player_id = _validate_identifier("player_id", value)
    if player_id not in player_ids:
        raise GameLifecycleError("player_id is not in this game.")
    return player_id


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_descriptor_hash(field_name: str, value: object) -> str:
    descriptor_hash = _validate_identifier(field_name, value)
    if len(descriptor_hash) != 64:
        raise GameLifecycleError(f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in descriptor_hash):
        raise GameLifecycleError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return descriptor_hash


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
