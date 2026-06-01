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
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatePayload
from warhammer40k_core.engine.aircraft import HoverModeState, HoverModeStatePayload
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
    ArmyMusterRequest,
    ArmyMusterRequestPayload,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockedUnitStatePayload,
    BattleShockResult,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldRuntimeStatePayload,
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainResult,
    CommandPointLedger,
    CommandPointLedgerPayload,
    CommandPointRefundResult,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandStepState,
    CommandStepStatePayload,
    initial_command_point_ledgers,
)
from warhammer40k_core.engine.effects import (
    EffectExpirationBoundary,
    PersistingEffect,
    PersistingEffectPayload,
)
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup, MissionSetupPayload
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_scoring_policy_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlRecordPayload,
    ObjectiveControlTiming,
    resolve_objective_control,
)
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
from warhammer40k_core.engine.phases.shooting import (
    ShootingPhaseState,
    ShootingPhaseStatePayload,
)
from warhammer40k_core.engine.reserves import (
    ReserveState,
    ReserveStatePayload,
    ReserveStatus,
    apply_reserve_destruction_to_battlefield,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.scoring import (
    FinalScoringResult,
    ScoringWindowKind,
    ScoringWindowState,
    ScoringWindowStatePayload,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatePayload,
    SecondaryMissionCardStatus,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointLedgerPayload,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    initial_victory_point_ledgers,
    secondary_mission_card_mode_from_token,
)
from warhammer40k_core.engine.stratagems import StratagemUseRecord, StratagemUseRecordPayload
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    DisembarkedUnitStatePayload,
    TransportCargoState,
    TransportCargoStatePayload,
)
from warhammer40k_core.engine.triggered_movement import SurgeMoveState, SurgeMoveStatePayload
from warhammer40k_core.engine.turn_cleanup import (
    EndTurnCleanupState,
    EndTurnCleanupStatePayload,
    resolve_end_turn_cleanup,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import (
    StartingStrengthRecord,
    StartingStrengthRecordPayload,
    starting_strength_records_for_units,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_10th import (
    chapter_approved_2025_26 as tenth_ca_2025_26_source,
)


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
    mission_setup: MissionSetupPayload | None


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
    command_step_state: CommandStepStatePayload | None
    command_point_ledgers: list[CommandPointLedgerPayload]
    victory_point_ledgers: list[VictoryPointLedgerPayload]
    stratagem_use_records: list[StratagemUseRecordPayload]
    army_definitions: list[ArmyDefinitionPayload]
    starting_strength_records: list[StartingStrengthRecordPayload]
    battlefield_state: BattlefieldRuntimeStatePayload | None
    mission_setup: MissionSetupPayload | None
    movement_phase_state: MovementPhaseStatePayload | None
    shooting_phase_state: ShootingPhaseStatePayload | None
    reserve_states: list[ReserveStatePayload]
    hover_mode_states: list[HoverModeStatePayload]
    transport_cargo_states: list[TransportCargoStatePayload]
    disembarked_unit_states: list[DisembarkedUnitStatePayload]
    advanced_unit_states: list[AdvancedUnitStatePayload]
    fell_back_unit_states: list[FellBackUnitStatePayload]
    surge_move_states: list[SurgeMoveStatePayload]
    battle_shocked_unit_ids: list[str]
    battle_shocked_unit_states: list[BattleShockedUnitStatePayload]
    objective_control_records: list[ObjectiveControlRecordPayload]
    mission_action_states: list[MissionActionStatePayload]
    end_turn_cleanup_states: list[EndTurnCleanupStatePayload]
    scoring_window_states: list[ScoringWindowStatePayload]
    persisting_effects: list[PersistingEffectPayload]
    secondary_mission_choices: list[SecondaryMissionChoicePayload]
    tactical_secondary_draws: list[TacticalSecondaryDrawPayload]
    secondary_mission_card_states: list[SecondaryMissionCardStatePayload]


def _new_secondary_mission_choices() -> list[SecondaryMissionChoice]:
    return []


def _new_tactical_secondary_draws() -> list[TacticalSecondaryDraw]:
    return []


def _new_advanced_unit_states() -> list[AdvancedUnitState]:
    return []


def _new_fell_back_unit_states() -> list[FellBackUnitState]:
    return []


def _new_surge_move_states() -> list[SurgeMoveState]:
    return []


def _new_command_point_ledgers() -> list[CommandPointLedger]:
    return []


def _new_victory_point_ledgers() -> list[VictoryPointLedger]:
    return []


def _new_stratagem_use_records() -> list[StratagemUseRecord]:
    return []


def _new_starting_strength_records() -> list[StartingStrengthRecord]:
    return []


def _new_reserve_states() -> list[ReserveState]:
    return []


def _new_hover_mode_states() -> list[HoverModeState]:
    return []


def _new_transport_cargo_states() -> list[TransportCargoState]:
    return []


def _new_disembarked_unit_states() -> list[DisembarkedUnitState]:
    return []


def _new_battle_shocked_unit_ids() -> list[str]:
    return []


def _new_battle_shocked_unit_states() -> list[BattleShockedUnitState]:
    return []


def _new_objective_control_records() -> list[ObjectiveControlRecord]:
    return []


def _new_mission_action_states() -> list[MissionActionState]:
    return []


def _new_end_turn_cleanup_states() -> list[EndTurnCleanupState]:
    return []


def _new_scoring_window_states() -> list[ScoringWindowState]:
    return []


def _new_army_definitions() -> list[ArmyDefinition]:
    return []


def _new_secondary_mission_card_states() -> list[SecondaryMissionCardState]:
    return []


def _new_persisting_effects() -> list[PersistingEffect]:
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
    mission_setup: MissionSetup | None = None

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
        object.__setattr__(
            self,
            "mission_setup",
            _validate_optional_mission_setup(
                self.mission_setup,
                player_ids=self.player_ids,
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
            "mission_setup": (
                None if self.mission_setup is None else self.mission_setup.to_payload()
            ),
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
            mission_setup=(
                None
                if payload["mission_setup"] is None
                else MissionSetup.from_payload(payload["mission_setup"])
            ),
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

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        if self.player_id != viewer_player_id and not secondary_mission_choices_revealed:
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
    command_step_state: CommandStepState | None = None
    command_point_ledgers: list[CommandPointLedger] = field(
        default_factory=_new_command_point_ledgers
    )
    victory_point_ledgers: list[VictoryPointLedger] = field(
        default_factory=_new_victory_point_ledgers
    )
    stratagem_use_records: list[StratagemUseRecord] = field(
        default_factory=_new_stratagem_use_records
    )
    army_definitions: list[ArmyDefinition] = field(default_factory=_new_army_definitions)
    starting_strength_records: list[StartingStrengthRecord] = field(
        default_factory=_new_starting_strength_records
    )
    battlefield_state: BattlefieldRuntimeState | None = None
    mission_setup: MissionSetup | None = None
    movement_phase_state: MovementPhaseState | None = None
    shooting_phase_state: ShootingPhaseState | None = None
    reserve_states: list[ReserveState] = field(default_factory=_new_reserve_states)
    hover_mode_states: list[HoverModeState] = field(default_factory=_new_hover_mode_states)
    transport_cargo_states: list[TransportCargoState] = field(
        default_factory=_new_transport_cargo_states
    )
    disembarked_unit_states: list[DisembarkedUnitState] = field(
        default_factory=_new_disembarked_unit_states
    )
    advanced_unit_states: list[AdvancedUnitState] = field(default_factory=_new_advanced_unit_states)
    fell_back_unit_states: list[FellBackUnitState] = field(
        default_factory=_new_fell_back_unit_states
    )
    surge_move_states: list[SurgeMoveState] = field(default_factory=_new_surge_move_states)
    battle_shocked_unit_ids: list[str] = field(default_factory=_new_battle_shocked_unit_ids)
    battle_shocked_unit_states: list[BattleShockedUnitState] = field(
        default_factory=_new_battle_shocked_unit_states
    )
    objective_control_records: list[ObjectiveControlRecord] = field(
        default_factory=_new_objective_control_records
    )
    mission_action_states: list[MissionActionState] = field(
        default_factory=_new_mission_action_states
    )
    end_turn_cleanup_states: list[EndTurnCleanupState] = field(
        default_factory=_new_end_turn_cleanup_states
    )
    scoring_window_states: list[ScoringWindowState] = field(
        default_factory=_new_scoring_window_states
    )
    persisting_effects: list[PersistingEffect] = field(default_factory=_new_persisting_effects)
    secondary_mission_choices: list[SecondaryMissionChoice] = field(
        default_factory=_new_secondary_mission_choices
    )
    tactical_secondary_draws: list[TacticalSecondaryDraw] = field(
        default_factory=_new_tactical_secondary_draws
    )
    secondary_mission_card_states: list[SecondaryMissionCardState] = field(
        default_factory=_new_secondary_mission_card_states
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
        self.command_step_state = _validate_optional_command_step_state(self.command_step_state)
        self.command_point_ledgers = _validate_command_point_ledgers(
            self.command_point_ledgers,
            player_ids=self.player_ids,
        )
        self.victory_point_ledgers = _validate_victory_point_ledgers(
            self.victory_point_ledgers,
            player_ids=self.player_ids,
        )
        self.stratagem_use_records = _validate_stratagem_use_records(
            self.stratagem_use_records,
            player_ids=self.player_ids,
        )
        self.army_definitions = _validate_army_definitions(
            self.army_definitions,
            player_ids=self.player_ids,
        )
        self.starting_strength_records = _validate_starting_strength_records(
            self.starting_strength_records,
            army_definitions=self.army_definitions,
            player_ids=self.player_ids,
        )
        self.battlefield_state = _validate_optional_battlefield_state(self.battlefield_state)
        self.mission_setup = _validate_optional_mission_setup(
            self.mission_setup,
            player_ids=self.player_ids,
        )
        self.movement_phase_state = _validate_optional_movement_phase_state(
            self.movement_phase_state
        )
        self.shooting_phase_state = _validate_optional_shooting_phase_state(
            self.shooting_phase_state
        )
        self.reserve_states = _validate_reserve_states(
            self.reserve_states,
            player_ids=self.player_ids,
        )
        self.hover_mode_states = _validate_hover_mode_states(
            self.hover_mode_states,
            player_ids=self.player_ids,
        )
        self.transport_cargo_states = _validate_transport_cargo_states(
            self.transport_cargo_states,
            player_ids=self.player_ids,
        )
        self.disembarked_unit_states = _validate_disembarked_unit_states(
            self.disembarked_unit_states,
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
        self.surge_move_states = _validate_surge_move_states(
            self.surge_move_states,
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
        self.battle_shocked_unit_states = _validate_battle_shocked_unit_states(
            self.battle_shocked_unit_states,
            army_definitions=self.army_definitions,
            battle_shocked_unit_ids=tuple(self.battle_shocked_unit_ids),
            player_ids=self.player_ids,
        )
        self.objective_control_records = _validate_objective_control_records(
            self.objective_control_records,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.mission_action_states = _validate_mission_action_states(
            self.mission_action_states,
            player_ids=self.player_ids,
        )
        self.end_turn_cleanup_states = _validate_end_turn_cleanup_states(
            self.end_turn_cleanup_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.scoring_window_states = _validate_scoring_window_states(
            self.scoring_window_states,
            game_id=self.game_id,
        )
        self.persisting_effects = _validate_persisting_effects(
            self.persisting_effects,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        self.secondary_mission_choices = _validate_secondary_choices(
            self.secondary_mission_choices,
            player_ids=self.player_ids,
        )
        self.tactical_secondary_draws = _validate_tactical_draws(
            self.tactical_secondary_draws,
            player_ids=self.player_ids,
        )
        self.secondary_mission_card_states = _validate_secondary_mission_card_states(
            self.secondary_mission_card_states,
            player_ids=self.player_ids,
        )
        _validate_hover_mode_state_references(self)
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
            command_point_ledgers=initial_command_point_ledgers(config.player_ids),
            victory_point_ledgers=initial_victory_point_ledgers(config.player_ids),
            mission_setup=config.mission_setup,
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
        self._expire_persisting_effects_at_current_battle_round_start()
        self._expire_persisting_effects_at_current_turn_start()
        self._expire_persisting_effects_at_current_phase_start()

    def advance_to_next_battle_phase(self) -> BattlePhase:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can advance battle phases only during battle.")
        if self.battle_phase_index is None:
            raise GameLifecycleError("GameState has no current battle phase.")
        completed_phase = self.battle_phase_sequence[self.battle_phase_index]
        completed_player_id = self.active_player_id
        if completed_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        phase_end_record = self._record_objective_control_boundary(
            completed_phase=completed_phase,
            timing=ObjectiveControlTiming.PHASE_END,
        )
        self._score_objective_control_boundary(phase_end_record)
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=self.battle_round,
                phase=completed_phase,
                player_id=completed_player_id,
            )
        )
        if self.battle_phase_index + 1 < len(self.battle_phase_sequence):
            if completed_phase is BattlePhase.COMMAND:
                self.command_step_state = None
            if completed_phase is BattlePhase.MOVEMENT:
                self.movement_phase_state = None
            if completed_phase is BattlePhase.SHOOTING:
                self.shooting_phase_state = None
            self.battle_phase_index += 1
            self._expire_persisting_effects_at_current_phase_start()
            return completed_phase
        self._clear_turn_action_states(
            player_id=completed_player_id,
            battle_round=self.battle_round,
        )
        turn_end_record = self._record_objective_control_boundary(
            completed_phase=completed_phase,
            timing=ObjectiveControlTiming.TURN_END,
        )
        self._score_objective_control_boundary(turn_end_record)
        self._resolve_end_turn_cleanup_boundary(completed_phase=completed_phase)
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.turn_end(
                battle_round=self.battle_round,
                player_id=completed_player_id,
            )
        )
        if completed_phase is BattlePhase.COMMAND:
            self.command_step_state = None
        if completed_phase is BattlePhase.MOVEMENT:
            self.movement_phase_state = None
        if completed_phase is BattlePhase.SHOOTING:
            self.shooting_phase_state = None
        completed_round = self.battle_round
        battle_round_ended = self._active_player_is_last_in_round(completed_player_id)
        if battle_round_ended:
            self._record_scoring_windows_boundary(ScoringWindowKind.END_OF_ROUND)
            self._resolve_unarrived_reserve_destruction_boundary(end_of_battle=False)
            self.expire_persisting_effects_at_boundary(
                EffectExpirationBoundary.battle_round_end(battle_round=completed_round)
            )
        if battle_round_ended and self._game_ends_after_completed_round(completed_round):
            self._resolve_unarrived_reserve_destruction_boundary(end_of_battle=True)
            self._record_scoring_windows_boundary(ScoringWindowKind.END_OF_GAME)
            self.expire_persisting_effects_at_boundary(EffectExpirationBoundary.battle_end())
            self.stage = GameLifecycleStage.COMPLETE
            self.battle_phase_index = None
            self.active_player_id = None
            self.command_step_state = None
            self.movement_phase_state = None
            self.shooting_phase_state = None
            return completed_phase
        self.battle_phase_index = 0
        self._advance_active_player_after_completed_turn()
        if battle_round_ended:
            self._expire_persisting_effects_at_current_battle_round_start()
        self._expire_persisting_effects_at_current_turn_start()
        self._expire_persisting_effects_at_current_phase_start()
        return completed_phase

    def record_secondary_mission_choice(self, choice: SecondaryMissionChoice) -> None:
        if choice.player_id not in self.player_ids:
            raise GameLifecycleError("SecondaryMissionChoice player_id is not in this game.")
        if self.secondary_mission_choice_for_player(choice.player_id) is not None:
            raise GameLifecycleError("SecondaryMissionChoice already exists for player.")
        self.secondary_mission_choices.append(choice)
        self.secondary_mission_choices.sort(key=lambda stored: stored.player_id)
        self.record_fixed_secondary_cards_for_choice(choice)

    def secondary_mission_choice_for_player(
        self,
        player_id: str,
    ) -> SecondaryMissionChoice | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for choice in self.secondary_mission_choices:
            if choice.player_id == requested_player_id:
                return choice
        return None

    def secondary_mission_choices_are_revealed(self) -> bool:
        return not self.missing_secondary_mission_player_ids()

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
        self._record_starting_strength_records_for_army(army_definition)

    def army_definition_for_player(self, player_id: str) -> ArmyDefinition | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for army_definition in self.army_definitions:
            if army_definition.player_id == requested_player_id:
                return army_definition
        return None

    def missing_army_player_ids(self) -> tuple[str, ...]:
        mustered = {army_definition.player_id for army_definition in self.army_definitions}
        return tuple(player_id for player_id in self.player_ids if player_id not in mustered)

    def command_point_ledger_for_player(self, player_id: str) -> CommandPointLedger:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for ledger in self.command_point_ledgers:
            if ledger.player_id == requested_player_id:
                return ledger
        raise GameLifecycleError("CommandPointLedger player_id was not found.")

    def command_point_total(self, player_id: str) -> int:
        return self.command_point_ledger_for_player(player_id).command_points

    def gain_command_points(
        self,
        *,
        player_id: str,
        amount: int,
        source_id: str,
        source_kind: CommandPointSourceKind,
        cap_exempt: bool = False,
    ) -> CommandPointGainResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.command_point_ledger_for_player(requested_player_id)
        updated, result = ledger.gain(
            battle_round=self.battle_round,
            amount=amount,
            source_id=source_id,
            source_kind=source_kind,
            cap_exempt=cap_exempt,
        )
        if updated is not ledger:
            self.command_point_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.command_point_ledgers
            ]
            self.command_point_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def spend_command_points(
        self,
        *,
        player_id: str,
        amount: int,
        source_id: str,
    ) -> CommandPointSpendResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.command_point_ledger_for_player(requested_player_id)
        updated, result = ledger.spend(
            battle_round=self.battle_round,
            amount=amount,
            source_id=source_id,
        )
        if updated is not ledger:
            self.command_point_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.command_point_ledgers
            ]
            self.command_point_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def refund_command_points(
        self,
        *,
        player_id: str,
        amount: int,
        source_id: str,
        cap_exempt: bool = False,
    ) -> CommandPointRefundResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.command_point_ledger_for_player(requested_player_id)
        updated, result = ledger.refund(
            battle_round=self.battle_round,
            amount=amount,
            source_id=source_id,
            cap_exempt=cap_exempt,
        )
        if updated is not ledger:
            self.command_point_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.command_point_ledgers
            ]
            self.command_point_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def record_stratagem_use(self, use_record: StratagemUseRecord) -> None:
        if type(use_record) is not StratagemUseRecord:
            raise GameLifecycleError("GameState stratagem use must be a StratagemUseRecord.")
        if use_record.player_id not in self.player_ids:
            raise GameLifecycleError("StratagemUseRecord player_id is not in this game.")
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("StratagemUseRecord can be recorded only during battle.")
        if use_record.battle_round != self.battle_round:
            raise GameLifecycleError("StratagemUseRecord battle_round drift.")
        if use_record.phase is not self.current_battle_phase:
            raise GameLifecycleError("StratagemUseRecord phase drift.")
        if any(stored.use_id == use_record.use_id for stored in self.stratagem_use_records):
            raise GameLifecycleError("StratagemUseRecord use_id must be unique.")
        self.stratagem_use_records.append(use_record)
        self.stratagem_use_records.sort(key=lambda stored: stored.use_id)

    def stratagem_use_records_for_player(
        self,
        player_id: str,
    ) -> tuple[StratagemUseRecord, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return tuple(
            record
            for record in self.stratagem_use_records
            if record.player_id == requested_player_id
        )

    def victory_point_ledger_for_player(self, player_id: str) -> VictoryPointLedger:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for ledger in self.victory_point_ledgers:
            if ledger.player_id == requested_player_id:
                return ledger
        raise GameLifecycleError("VictoryPointLedger player_id was not found.")

    def victory_point_total(self, player_id: str) -> int:
        return self.victory_point_ledger_for_player(player_id).victory_points

    def award_victory_points(self, award: VictoryPointAward) -> VictoryPointTransaction:
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("GameState award must be a VictoryPointAward.")
        requested_player_id = _validate_player_id(award.player_id, player_ids=self.player_ids)
        ledger = self.victory_point_ledger_for_player(requested_player_id)
        applied_amount = award.amount
        transaction_metadata = award.metadata
        if self.mission_setup is not None:
            policy = mission_scoring_policy_from_setup(self.mission_setup)
            applied_amount, transaction_metadata = policy.capped_award_for_ledger(
                ledger=ledger,
                award=award,
            )
        updated, transaction = ledger.award(
            award,
            applied_amount=applied_amount,
            metadata=transaction_metadata,
        )
        self.victory_point_ledgers = [
            updated if stored.player_id == requested_player_id else stored
            for stored in self.victory_point_ledgers
        ]
        self.victory_point_ledgers.sort(key=lambda stored: stored.player_id)
        return transaction

    def record_mission_action_state(self, action_state: MissionActionState) -> None:
        if type(action_state) is not MissionActionState:
            raise GameLifecycleError("mission_action_state must be a MissionActionState.")
        if action_state.player_id not in self.player_ids:
            raise GameLifecycleError("MissionActionState player_id is not in this game.")
        if any(stored.action_id == action_state.action_id for stored in self.mission_action_states):
            raise GameLifecycleError("MissionActionState already exists for action_id.")
        self.mission_action_states.append(action_state)
        self.mission_action_states.sort(key=lambda state: state.action_id)

    def mission_action_state_by_id(self, action_id: str) -> MissionActionState:
        requested_action_id = _validate_identifier("action_id", action_id)
        for action_state in self.mission_action_states:
            if action_state.action_id == requested_action_id:
                return action_state
        raise GameLifecycleError("MissionActionState action_id was not found.")

    def replace_mission_action_state(self, action_state: MissionActionState) -> None:
        if type(action_state) is not MissionActionState:
            raise GameLifecycleError("mission_action_state must be a MissionActionState.")
        for index, stored in enumerate(self.mission_action_states):
            if stored.action_id == action_state.action_id:
                self.mission_action_states[index] = action_state
                self.mission_action_states.sort(key=lambda state: state.action_id)
                return
        raise GameLifecycleError("MissionActionState does not exist for action_id.")

    def complete_mission_action(
        self,
        *,
        action_id: str,
        completion_phase: BattlePhase,
    ) -> MissionActionState:
        if self.mission_setup is None:
            raise GameLifecycleError("Mission Action scoring requires MissionSetup.")
        if type(completion_phase) is not BattlePhase:
            raise GameLifecycleError("completion_phase must be a BattlePhase.")
        action_state = self.mission_action_state_by_id(action_id)
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        award = policy.mission_action_award(
            player_id=action_state.player_id,
            battle_round=self.battle_round,
            phase=completion_phase.value,
            action_id=action_state.action_id,
            source_id=action_state.scoring_source_id,
            amount=action_state.victory_points,
        )
        transaction = self.award_victory_points(award)
        completed = action_state.complete(
            battle_round=self.battle_round,
            phase=completion_phase.value,
            completion_timing=action_state.completion_timing,
            award=award,
            transaction_id=transaction.transaction_id,
        )
        self.replace_mission_action_state(completed)
        return completed

    def interrupt_mission_action(self, *, action_id: str, reason: str) -> MissionActionState:
        action_state = self.mission_action_state_by_id(action_id)
        interrupted = action_state.interrupt(reason=reason)
        self.replace_mission_action_state(interrupted)
        return interrupted

    def record_persisting_effect(self, effect: PersistingEffect) -> None:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("persisting_effect must be a PersistingEffect.")
        if effect.owner_player_id not in self.player_ids:
            raise GameLifecycleError("PersistingEffect owner_player_id is not in this game.")
        unit_ids = _known_rules_unit_ids(
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
        )
        if not unit_ids:
            raise GameLifecycleError("PersistingEffect requires mustered army definitions.")
        if any(unit_id not in unit_ids for unit_id in effect.target_unit_instance_ids):
            raise GameLifecycleError("PersistingEffect target unit is unknown.")
        if any(stored.effect_id == effect.effect_id for stored in self.persisting_effects):
            raise GameLifecycleError("PersistingEffect already exists for effect_id.")
        self.persisting_effects.append(effect)
        self.persisting_effects.sort(key=lambda stored: stored.effect_id)

    def persisting_effects_for_unit(self, unit_instance_id: str) -> tuple[PersistingEffect, ...]:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return tuple(
            effect
            for effect in self.persisting_effects
            if effect.applies_to_unit(requested_unit_id)
        )

    def expire_persisting_effects_at_boundary(
        self,
        boundary: EffectExpirationBoundary,
    ) -> tuple[PersistingEffect, ...]:
        if type(boundary) is not EffectExpirationBoundary:
            raise GameLifecycleError("effect expiration boundary must be EffectExpirationBoundary.")
        expired = tuple(effect for effect in self.persisting_effects if effect.expires_at(boundary))
        if not expired:
            return ()
        expired_ids = {effect.effect_id for effect in expired}
        self.persisting_effects = [
            effect for effect in self.persisting_effects if effect.effect_id not in expired_ids
        ]
        return tuple(sorted(expired, key=lambda effect: effect.effect_id))

    def transfer_persisting_effects_after_attached_unit_split(
        self,
        *,
        attached_unit_instance_id: str,
        surviving_unit_instance_ids: tuple[str, ...],
    ) -> tuple[PersistingEffect, ...]:
        requested_attached_id = _validate_identifier(
            "attached_unit_instance_id",
            attached_unit_instance_id,
        )
        survivor_ids = _validate_identifier_tuple(
            "surviving_unit_instance_ids",
            surviving_unit_instance_ids,
            min_length=1,
            sort_values=True,
        )
        unit_ids = _known_rules_unit_ids(
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
        )
        if requested_attached_id not in unit_ids:
            raise GameLifecycleError("Attached-unit split source unit is unknown.")
        if any(unit_id not in unit_ids for unit_id in survivor_ids):
            raise GameLifecycleError("Attached-unit split survivor unit is unknown.")
        updated: list[PersistingEffect] = []
        changed: list[PersistingEffect] = []
        for effect in self.persisting_effects:
            replacement = effect.with_attached_unit_split(
                attached_unit_instance_id=requested_attached_id,
                surviving_unit_instance_ids=survivor_ids,
            )
            updated.append(replacement)
            if replacement is not effect:
                changed.append(replacement)
        self.persisting_effects = sorted(updated, key=lambda effect: effect.effect_id)
        return tuple(sorted(changed, key=lambda effect: effect.effect_id))

    def starting_strength_record_for_unit(self, unit_instance_id: str) -> StartingStrengthRecord:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for record in self.starting_strength_records:
            if record.unit_instance_id == requested_unit_id:
                return record
        raise GameLifecycleError("StartingStrengthRecord unit_instance_id was not found.")

    def recover_starting_strength_after_attached_unit_split(
        self,
        *,
        player_id: str,
        attached_unit_instance_id: str,
        surviving_unit_instance_ids: tuple[str, ...],
    ) -> tuple[StartingStrengthRecord, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_attached_unit_id = _validate_identifier(
            "attached_unit_instance_id",
            attached_unit_instance_id,
        )
        surviving_ids = _validate_identifier_tuple(
            "surviving_unit_instance_ids",
            surviving_unit_instance_ids,
            min_length=1,
            sort_values=True,
        )
        if requested_attached_unit_id in surviving_ids:
            raise GameLifecycleError(
                "Attached-unit split survivors must not include attached_unit_instance_id."
            )
        attached_record = None
        for record in self.starting_strength_records:
            if record.unit_instance_id == requested_attached_unit_id:
                attached_record = record
                break
        if attached_record is None:
            raise GameLifecycleError(
                "Attached-unit split requires an existing StartingStrengthRecord for "
                "attached_unit_instance_id."
            )
        if attached_record.player_id != requested_player_id:
            raise GameLifecycleError("Attached-unit split attached record player_id drift.")
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        recovered_records: list[StartingStrengthRecord] = []
        for unit_id in surviving_ids:
            owner = unit_owner_by_id.get(unit_id)
            if owner is None:
                raise GameLifecycleError("Attached-unit split survivor unit is unknown.")
            if owner != requested_player_id:
                raise GameLifecycleError("Attached-unit split survivor player_id drift.")
            recovered_records.append(
                StartingStrengthRecord.from_unit(
                    player_id=requested_player_id,
                    unit=self._unit_by_id(unit_id),
                )
            )
        self.transfer_persisting_effects_after_attached_unit_split(
            attached_unit_instance_id=requested_attached_unit_id,
            surviving_unit_instance_ids=surviving_ids,
        )
        replaced_ids = {*surviving_ids, requested_attached_unit_id}
        self.starting_strength_records = [
            record
            for record in self.starting_strength_records
            if record.unit_instance_id not in replaced_ids
        ]
        self.starting_strength_records.extend(recovered_records)
        self.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
        return tuple(sorted(recovered_records, key=lambda record: record.unit_instance_id))

    def clear_battle_shock_for_player(self, player_id: str) -> tuple[str, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        cleared_ids = tuple(
            unit_id
            for unit_id in self.battle_shocked_unit_ids
            if unit_owner_by_id.get(unit_id) == requested_player_id
        )
        if not cleared_ids:
            return ()
        cleared_set = set(cleared_ids)
        self.battle_shocked_unit_ids = [
            unit_id for unit_id in self.battle_shocked_unit_ids if unit_id not in cleared_set
        ]
        self.battle_shocked_unit_states = [
            state
            for state in self.battle_shocked_unit_states
            if state.unit_instance_id not in cleared_set
        ]
        return tuple(sorted(cleared_ids))

    def record_battle_shock_result(self, result: BattleShockResult) -> None:
        if type(result) is not BattleShockResult:
            raise GameLifecycleError("GameState battle_shock_result must be a BattleShockResult.")
        if result.request.game_id != self.game_id:
            raise GameLifecycleError("BattleShockResult game_id drift.")
        if result.request.battle_round != self.battle_round:
            raise GameLifecycleError("BattleShockResult battle_round drift.")
        if result.request.player_id not in self.player_ids:
            raise GameLifecycleError("BattleShockResult player_id is not in this game.")
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        owner = unit_owner_by_id.get(result.request.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("BattleShockResult unit is unknown.")
        if owner != result.request.player_id:
            raise GameLifecycleError("BattleShockResult unit owner drift.")
        unit = self._unit_by_id(result.request.unit_instance_id)
        if not result.passed:
            if result.request.unit_instance_id in self.battle_shocked_unit_ids:
                raise GameLifecycleError("Battle-shocked unit is already marked.")
            shocked_state = BattleShockedUnitState.from_result(result=result, unit=unit)
            self.battle_shocked_unit_ids.append(result.request.unit_instance_id)
            self.battle_shocked_unit_ids.sort()
            self.battle_shocked_unit_states.append(shocked_state)
            self.battle_shocked_unit_states.sort(key=lambda state: state.unit_instance_id)

    def record_battlefield_state(self, battlefield_state: BattlefieldRuntimeState) -> None:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError(
                "GameState battlefield_state must be a BattlefieldRuntimeState."
            )
        if self.battlefield_state is not None:
            raise GameLifecycleError("GameState battlefield_state already exists.")
        self._assert_battlefield_state_clear_of_objective_markers(battlefield_state)
        self.battlefield_state = battlefield_state

    def replace_battlefield_state(self, battlefield_state: BattlefieldRuntimeState) -> None:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError(
                "GameState battlefield_state must be a BattlefieldRuntimeState."
            )
        if self.battlefield_state is None:
            raise GameLifecycleError("GameState battlefield_state does not exist.")
        self._assert_battlefield_state_clear_of_objective_markers(battlefield_state)
        self.battlefield_state = battlefield_state

    def record_mission_setup(self, mission_setup: MissionSetup) -> None:
        if self.mission_setup is not None:
            raise GameLifecycleError("GameState mission_setup already exists.")
        self.mission_setup = _validate_optional_mission_setup(
            mission_setup,
            player_ids=self.player_ids,
        )

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

    def draw_tactical_secondary_cards(
        self,
        *,
        player_id: str,
        source_result_id: str,
        draw_count: int | None = None,
    ) -> tuple[SecondaryMissionCardState, ...]:
        if self.mission_setup is None:
            raise GameLifecycleError("Tactical secondary draw requires MissionSetup.")
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        result_id = _validate_identifier("source_result_id", source_result_id)
        requested_draw_count = (
            self.tactical_secondary_draw_count
            if draw_count is None
            else _validate_positive_int("draw_count", draw_count)
        )
        excluded_ids = tuple(
            state.secondary_mission_id
            for state in self.secondary_mission_card_states
            if state.player_id == requested_player_id
        )
        secondary_ids = deterministic_tactical_secondary_draw(
            mission_setup=self.mission_setup,
            player_id=requested_player_id,
            battle_round=self.battle_round,
            draw_count=requested_draw_count,
            excluded_secondary_mission_ids=excluded_ids,
        )
        card_states = tuple(
            SecondaryMissionCardState.active_tactical(
                player_id=requested_player_id,
                secondary_mission_id=secondary_id,
                battle_round=self.battle_round,
                source_result_id=result_id,
            )
            for secondary_id in secondary_ids
        )
        for card_state in card_states:
            self.record_secondary_mission_card_state(card_state)
        return card_states

    def record_fixed_secondary_cards_for_choice(self, choice: SecondaryMissionChoice) -> None:
        if type(choice) is not SecondaryMissionChoice:
            raise GameLifecycleError("choice must be a SecondaryMissionChoice.")
        if choice.mode is not SecondaryMissionMode.FIXED:
            return
        for secondary_id in choice.fixed_mission_ids:
            if (
                self.secondary_mission_card_state(
                    player_id=choice.player_id,
                    secondary_mission_id=secondary_id,
                    mode=SecondaryMissionCardMode.FIXED,
                )
                is not None
            ):
                continue
            self.record_secondary_mission_card_state(
                SecondaryMissionCardState.active_fixed(
                    player_id=choice.player_id,
                    secondary_mission_id=secondary_id,
                )
            )

    def record_secondary_mission_card_state(
        self,
        card_state: SecondaryMissionCardState,
    ) -> None:
        if type(card_state) is not SecondaryMissionCardState:
            raise GameLifecycleError("card_state must be a SecondaryMissionCardState.")
        if card_state.player_id not in self.player_ids:
            raise GameLifecycleError("SecondaryMissionCardState player_id is not in this game.")
        key = (
            card_state.player_id,
            card_state.secondary_mission_id,
            card_state.mode,
            card_state.battle_round,
        )
        if any(
            (
                stored.player_id,
                stored.secondary_mission_id,
                stored.mode,
                stored.battle_round,
            )
            == key
            for stored in self.secondary_mission_card_states
        ):
            raise GameLifecycleError("SecondaryMissionCardState already exists.")
        self.secondary_mission_card_states.append(card_state)
        self.secondary_mission_card_states.sort(
            key=lambda state: (
                state.player_id,
                state.battle_round,
                state.mode.value,
                state.secondary_mission_id,
            )
        )

    def secondary_mission_card_state(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        mode: SecondaryMissionCardMode,
    ) -> SecondaryMissionCardState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_secondary_id = _validate_identifier("secondary_mission_id", secondary_mission_id)
        requested_mode = secondary_mission_card_mode_from_token(mode)
        active_matches = [
            state
            for state in self.secondary_mission_card_states
            if state.player_id == requested_player_id
            and state.secondary_mission_id == requested_secondary_id
            and state.mode is requested_mode
            and state.status is SecondaryMissionCardStatus.ACTIVE
        ]
        if not active_matches:
            return None
        if len(active_matches) > 1:
            raise GameLifecycleError("Multiple active secondary card states found.")
        return active_matches[0]

    def score_secondary_mission(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        mode: SecondaryMissionCardMode,
        phase: BattlePhase,
    ) -> SecondaryMissionCardState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary mission scoring requires MissionSetup.")
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Secondary mission scoring phase must be a BattlePhase.")
        requested_mode = secondary_mission_card_mode_from_token(mode)
        card_state = self.secondary_mission_card_state(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=requested_mode,
        )
        if card_state is None:
            raise GameLifecycleError("Secondary mission card is not active.")
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        source_kind = (
            VictoryPointSourceKind.FIXED_SECONDARY
            if requested_mode is SecondaryMissionCardMode.FIXED
            else VictoryPointSourceKind.TACTICAL_SECONDARY
        )
        transaction = self.award_victory_points(
            policy.secondary_award(
                player_id=card_state.player_id,
                battle_round=self.battle_round,
                phase=phase.value,
                secondary_mission_id=card_state.secondary_mission_id,
                source_kind=source_kind,
                hidden=False,
            )
        )
        scored = card_state.score(transaction_id=transaction.transaction_id)
        self._replace_secondary_mission_card_state(scored)
        return scored

    def discard_tactical_secondary(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        result_id: str,
    ) -> SecondaryMissionCardState:
        card_state = self.secondary_mission_card_state(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        if card_state is None:
            raise GameLifecycleError("Tactical secondary card is not active.")
        discarded = card_state.discard(result_id=result_id)
        self._replace_secondary_mission_card_state(discarded)
        return discarded

    def _replace_secondary_mission_card_state(
        self,
        card_state: SecondaryMissionCardState,
    ) -> None:
        if type(card_state) is not SecondaryMissionCardState:
            raise GameLifecycleError("card_state must be a SecondaryMissionCardState.")
        key = (
            card_state.player_id,
            card_state.secondary_mission_id,
            card_state.mode,
            card_state.battle_round,
        )
        for index, stored in enumerate(self.secondary_mission_card_states):
            stored_key = (
                stored.player_id,
                stored.secondary_mission_id,
                stored.mode,
                stored.battle_round,
            )
            if stored_key == key:
                self.secondary_mission_card_states[index] = card_state
                self.secondary_mission_card_states.sort(
                    key=lambda state: (
                        state.player_id,
                        state.battle_round,
                        state.mode.value,
                        state.secondary_mission_id,
                    )
                )
                return
        raise GameLifecycleError("SecondaryMissionCardState does not exist.")

    def record_objective_control_record(self, record: ObjectiveControlRecord) -> None:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "GameState objective_control_record must be an ObjectiveControlRecord."
            )
        if record.game_id != self.game_id:
            raise GameLifecycleError("ObjectiveControlRecord game_id drift.")
        if record.active_player_id not in self.player_ids:
            raise GameLifecycleError("ObjectiveControlRecord active_player_id is not in this game.")
        if record.battle_round != self.battle_round:
            raise GameLifecycleError("ObjectiveControlRecord battle_round drift.")
        if record.phase not in {phase.value for phase in self.battle_phase_sequence}:
            raise GameLifecycleError("ObjectiveControlRecord phase is not in this game.")
        if any(stored.record_id == record.record_id for stored in self.objective_control_records):
            raise GameLifecycleError("ObjectiveControlRecord already exists.")
        self.objective_control_records.append(record)

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

    def record_hover_mode_state(self, hover_mode_state: HoverModeState) -> None:
        if type(hover_mode_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_state must be a HoverModeState.")
        if hover_mode_state.player_id not in self.player_ids:
            raise GameLifecycleError("HoverModeState player_id is not in this game.")
        if self.hover_mode_state_for_unit(hover_mode_state.unit_instance_id) is not None:
            raise GameLifecycleError("HoverModeState already exists for unit.")
        _validate_hover_mode_state_reference(self, hover_mode_state)
        self.hover_mode_states.append(hover_mode_state)
        self.hover_mode_states.sort(key=lambda state: state.unit_instance_id)

    def hover_mode_state_for_unit(self, unit_instance_id: str) -> HoverModeState | None:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for hover_mode_state in self.hover_mode_states:
            if hover_mode_state.unit_instance_id == requested_unit_id:
                return hover_mode_state
        return None

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

    def embarked_model_ids(self) -> tuple[str, ...]:
        if not self.transport_cargo_states:
            return ()
        unit_by_id = {
            unit.unit_instance_id: unit for army in self.army_definitions for unit in army.units
        }
        model_ids: list[str] = []
        for cargo_state in self.transport_cargo_states:
            for unit_id in cargo_state.embarked_unit_instance_ids:
                unit = unit_by_id.get(unit_id)
                if unit is None:
                    raise GameLifecycleError("TransportCargoState references an unknown unit.")
                model_ids.extend(model.model_instance_id for model in unit.own_models)
        return tuple(sorted(model_ids))

    def unavailable_model_ids(self) -> tuple[str, ...]:
        return tuple(sorted((*self.unarrived_reserve_model_ids(), *self.embarked_model_ids())))

    def record_transport_cargo_state(self, cargo_state: TransportCargoState) -> None:
        if type(cargo_state) is not TransportCargoState:
            raise GameLifecycleError("cargo_state must be a TransportCargoState.")
        if cargo_state.player_id not in self.player_ids:
            raise GameLifecycleError("TransportCargoState player_id is not in this game.")
        if (
            self.transport_cargo_state_for_transport(cargo_state.transport_unit_instance_id)
            is not None
        ):
            raise GameLifecycleError("TransportCargoState already exists for transport.")
        self.transport_cargo_states.append(cargo_state)
        self.transport_cargo_states.sort(key=lambda state: state.transport_unit_instance_id)

    def transport_cargo_state_for_transport(
        self,
        transport_unit_instance_id: str,
    ) -> TransportCargoState | None:
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        for cargo_state in self.transport_cargo_states:
            if cargo_state.transport_unit_instance_id == requested_transport_id:
                return cargo_state
        return None

    def replace_transport_cargo_state(self, cargo_state: TransportCargoState) -> None:
        if type(cargo_state) is not TransportCargoState:
            raise GameLifecycleError("cargo_state must be a TransportCargoState.")
        for index, stored in enumerate(self.transport_cargo_states):
            if stored.transport_unit_instance_id == cargo_state.transport_unit_instance_id:
                self.transport_cargo_states[index] = cargo_state
                self.transport_cargo_states.sort(key=lambda state: state.transport_unit_instance_id)
                return
        raise GameLifecycleError("TransportCargoState does not exist for transport.")

    def record_disembarked_unit_state(self, state: DisembarkedUnitState) -> None:
        if type(state) is not DisembarkedUnitState:
            raise GameLifecycleError("Disembarked unit state must be a DisembarkedUnitState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("DisembarkedUnitState player_id is not in this game.")
        if (
            self.disembarked_unit_state_for_unit(
                player_id=state.player_id,
                battle_round=state.battle_round,
                unit_instance_id=state.unit_instance_id,
            )
            is not None
        ):
            raise GameLifecycleError("DisembarkedUnitState already exists for unit and turn.")
        self.disembarked_unit_states.append(state)
        self.disembarked_unit_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.player_id,
                stored.unit_instance_id,
            )
        )

    def disembarked_unit_state_for_unit(
        self,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
    ) -> DisembarkedUnitState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for state in self.disembarked_unit_states:
            if (
                state.player_id == requested_player_id
                and state.battle_round == requested_round
                and state.unit_instance_id == requested_unit_id
            ):
                return state
        return None

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

    def record_surge_move_state(self, state: SurgeMoveState) -> None:
        if type(state) is not SurgeMoveState:
            raise GameLifecycleError("Surge move state must be a SurgeMoveState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("SurgeMoveState player_id is not in this game.")
        if any(stored.result_id == state.result_id for stored in self.surge_move_states):
            raise GameLifecycleError("SurgeMoveState already exists for result_id.")
        if any(
            stored.same_phase_key() == state.same_phase_key() for stored in self.surge_move_states
        ):
            raise GameLifecycleError("SurgeMoveState already exists for unit in this phase.")
        self.surge_move_states.append(state)
        self.surge_move_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.phase,
                stored.player_id,
                stored.unit_instance_id,
                stored.result_id,
            )
        )

    def surge_move_states_for_unit_phase(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: str,
        unit_instance_id: str,
    ) -> tuple[SurgeMoveState, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_phase = _validate_identifier("phase", phase)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return tuple(
            state
            for state in self.surge_move_states
            if state.player_id == requested_player_id
            and state.battle_round == requested_round
            and state.phase == requested_phase
            and state.unit_instance_id == requested_unit_id
        )

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
            "command_step_state": (
                None if self.command_step_state is None else self.command_step_state.to_payload()
            ),
            "command_point_ledgers": [ledger.to_payload() for ledger in self.command_point_ledgers],
            "victory_point_ledgers": [ledger.to_payload() for ledger in self.victory_point_ledgers],
            "stratagem_use_records": [record.to_payload() for record in self.stratagem_use_records],
            "army_definitions": [army.to_payload() for army in self.army_definitions],
            "starting_strength_records": [
                record.to_payload() for record in self.starting_strength_records
            ],
            "battlefield_state": (
                None if self.battlefield_state is None else self.battlefield_state.to_payload()
            ),
            "mission_setup": None
            if self.mission_setup is None
            else self.mission_setup.to_payload(),
            "movement_phase_state": (
                None
                if self.movement_phase_state is None
                else self.movement_phase_state.to_payload()
            ),
            "shooting_phase_state": (
                None
                if self.shooting_phase_state is None
                else self.shooting_phase_state.to_payload()
            ),
            "reserve_states": [state.to_payload() for state in self.reserve_states],
            "hover_mode_states": [state.to_payload() for state in self.hover_mode_states],
            "transport_cargo_states": [state.to_payload() for state in self.transport_cargo_states],
            "disembarked_unit_states": [
                state.to_payload() for state in self.disembarked_unit_states
            ],
            "advanced_unit_states": [state.to_payload() for state in self.advanced_unit_states],
            "fell_back_unit_states": [state.to_payload() for state in self.fell_back_unit_states],
            "surge_move_states": [state.to_payload() for state in self.surge_move_states],
            "battle_shocked_unit_ids": list(self.battle_shocked_unit_ids),
            "battle_shocked_unit_states": [
                state.to_payload() for state in self.battle_shocked_unit_states
            ],
            "objective_control_records": [
                record.to_payload() for record in self.objective_control_records
            ],
            "mission_action_states": [state.to_payload() for state in self.mission_action_states],
            "end_turn_cleanup_states": [
                state.to_payload() for state in self.end_turn_cleanup_states
            ],
            "scoring_window_states": [state.to_payload() for state in self.scoring_window_states],
            "persisting_effects": [effect.to_payload() for effect in self.persisting_effects],
            "secondary_mission_choices": [
                choice.to_payload() for choice in self.secondary_mission_choices
            ],
            "tactical_secondary_draws": [
                draw.to_payload() for draw in self.tactical_secondary_draws
            ],
            "secondary_mission_card_states": [
                state.to_payload() for state in self.secondary_mission_card_states
            ],
        }

    def to_public_payload(self, *, viewer_player_id: str) -> dict[str, JsonValue]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        secondary_mission_choices_revealed = self.secondary_mission_choices_are_revealed()
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
            public_choices.append(
                choice.to_public_payload(
                    viewer_player_id=viewer,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
            )

        payload = cast(dict[str, JsonValue], self.to_payload())
        payload["secondary_mission_choices"] = cast(JsonValue, public_choices)
        payload["victory_point_ledgers"] = [
            ledger.to_public_payload(
                viewer_player_id=viewer,
                secondary_mission_choices_revealed=secondary_mission_choices_revealed,
            )
            for ledger in self.victory_point_ledgers
        ]
        payload["command_point_ledgers"] = [
            cast(JsonValue, ledger.to_payload()) for ledger in self.command_point_ledgers
        ]
        payload["stratagem_use_records"] = [
            cast(JsonValue, record.to_payload()) for record in self.stratagem_use_records
        ]
        payload["secondary_mission_card_states"] = cast(
            JsonValue,
            self.public_secondary_mission_card_states(viewer_player_id=viewer),
        )
        payload["tactical_secondary_draws"] = cast(
            JsonValue,
            self.public_tactical_secondary_draws(viewer_player_id=viewer),
        )
        payload["mission_action_states"] = cast(
            JsonValue,
            self.public_mission_action_states(viewer_player_id=viewer),
        )
        validate_json_value(payload)
        return payload

    def public_secondary_mission_card_states(
        self,
        *,
        viewer_player_id: str,
    ) -> list[dict[str, JsonValue]]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        secondary_mission_choices_revealed = self.secondary_mission_choices_are_revealed()
        return [
            state.to_public_payload(
                viewer_player_id=viewer,
                secondary_mission_choices_revealed=secondary_mission_choices_revealed,
            )
            for state in self.secondary_mission_card_states
            if secondary_mission_choices_revealed or state.player_id == viewer
        ]

    def public_tactical_secondary_draws(
        self,
        *,
        viewer_player_id: str,
    ) -> list[dict[str, JsonValue]]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        secondary_mission_choices_revealed = self.secondary_mission_choices_are_revealed()
        return [
            cast(dict[str, JsonValue], draw.to_payload())
            for draw in self.tactical_secondary_draws
            if secondary_mission_choices_revealed or draw.player_id == viewer
        ]

    def public_mission_action_states(
        self,
        *,
        viewer_player_id: str,
    ) -> list[dict[str, JsonValue]]:
        _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        return [
            cast(dict[str, JsonValue], action_state.to_payload())
            for action_state in self.mission_action_states
        ]

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
            command_step_state=(
                None
                if payload["command_step_state"] is None
                else CommandStepState.from_payload(payload["command_step_state"])
            ),
            command_point_ledgers=[
                CommandPointLedger.from_payload(ledger)
                for ledger in payload["command_point_ledgers"]
            ],
            victory_point_ledgers=[
                VictoryPointLedger.from_payload(ledger)
                for ledger in payload["victory_point_ledgers"]
            ],
            stratagem_use_records=[
                StratagemUseRecord.from_payload(record)
                for record in payload["stratagem_use_records"]
            ],
            army_definitions=[
                _army_definition_from_payload(army) for army in payload["army_definitions"]
            ],
            starting_strength_records=[
                StartingStrengthRecord.from_payload(record)
                for record in payload["starting_strength_records"]
            ],
            battlefield_state=(
                None
                if payload["battlefield_state"] is None
                else _battlefield_state_from_payload(payload["battlefield_state"])
            ),
            mission_setup=(
                None
                if payload["mission_setup"] is None
                else MissionSetup.from_payload(payload["mission_setup"])
            ),
            movement_phase_state=(
                None
                if payload["movement_phase_state"] is None
                else MovementPhaseState.from_payload(payload["movement_phase_state"])
            ),
            shooting_phase_state=(
                None
                if payload["shooting_phase_state"] is None
                else ShootingPhaseState.from_payload(payload["shooting_phase_state"])
            ),
            reserve_states=[
                ReserveState.from_payload(state) for state in payload["reserve_states"]
            ],
            hover_mode_states=[
                HoverModeState.from_payload(state) for state in payload["hover_mode_states"]
            ],
            transport_cargo_states=[
                TransportCargoState.from_payload(state)
                for state in payload["transport_cargo_states"]
            ],
            disembarked_unit_states=[
                DisembarkedUnitState.from_payload(state)
                for state in payload["disembarked_unit_states"]
            ],
            advanced_unit_states=[
                AdvancedUnitState.from_payload(state) for state in payload["advanced_unit_states"]
            ],
            fell_back_unit_states=[
                FellBackUnitState.from_payload(state) for state in payload["fell_back_unit_states"]
            ],
            surge_move_states=[
                SurgeMoveState.from_payload(state) for state in payload["surge_move_states"]
            ],
            battle_shocked_unit_ids=list(payload["battle_shocked_unit_ids"]),
            battle_shocked_unit_states=[
                BattleShockedUnitState.from_payload(state)
                for state in payload["battle_shocked_unit_states"]
            ],
            objective_control_records=[
                ObjectiveControlRecord.from_payload(record)
                for record in payload["objective_control_records"]
            ],
            mission_action_states=[
                MissionActionState.from_payload(state) for state in payload["mission_action_states"]
            ],
            end_turn_cleanup_states=[
                EndTurnCleanupState.from_payload(state)
                for state in payload["end_turn_cleanup_states"]
            ],
            scoring_window_states=[
                ScoringWindowState.from_payload(state) for state in payload["scoring_window_states"]
            ],
            persisting_effects=[
                PersistingEffect.from_payload(effect) for effect in payload["persisting_effects"]
            ],
            secondary_mission_choices=[
                SecondaryMissionChoice.from_payload(choice)
                for choice in payload["secondary_mission_choices"]
            ],
            tactical_secondary_draws=[
                TacticalSecondaryDraw.from_payload(draw)
                for draw in payload["tactical_secondary_draws"]
            ],
            secondary_mission_card_states=[
                SecondaryMissionCardState.from_payload(state)
                for state in payload["secondary_mission_card_states"]
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

    def _expire_persisting_effects_at_current_battle_round_start(self) -> None:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can expire battle-round effects only in battle.")
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.battle_round_start(battle_round=self.battle_round)
        )

    def _expire_persisting_effects_at_current_turn_start(self) -> None:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can expire turn effects only in battle.")
        if self.active_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.turn_start(
                battle_round=self.battle_round,
                player_id=self.active_player_id,
            )
        )

    def _expire_persisting_effects_at_current_phase_start(self) -> None:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can expire phase effects only in battle.")
        if self.active_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        current_phase = self.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("GameState has no current battle phase.")
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_start(
                battle_round=self.battle_round,
                phase=current_phase,
                player_id=self.active_player_id,
            )
        )

    def _record_starting_strength_records_for_army(
        self,
        army_definition: ArmyDefinition,
    ) -> None:
        records = starting_strength_records_for_units(
            player_id=army_definition.player_id,
            units=army_definition.units,
        )
        existing_unit_ids = {record.unit_instance_id for record in self.starting_strength_records}
        for record in records:
            if record.unit_instance_id in existing_unit_ids:
                raise GameLifecycleError("StartingStrengthRecord already exists for unit.")
            self.starting_strength_records.append(record)
        self.starting_strength_records.sort(key=lambda record: record.unit_instance_id)

    def _unit_by_id(self, unit_instance_id: str) -> UnitInstance:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for army_definition in self.army_definitions:
            for unit in army_definition.units:
                if unit.unit_instance_id == requested_unit_id:
                    return unit
        raise GameLifecycleError("GameState unit_instance_id was not found.")

    def _record_objective_control_boundary(
        self,
        *,
        completed_phase: BattlePhase,
        timing: ObjectiveControlTiming,
    ) -> ObjectiveControlRecord:
        if self.mission_setup is None:
            raise GameLifecycleError("Objective control updates require MissionSetup.")
        if self.battlefield_state is None:
            raise GameLifecycleError("Objective control updates require battlefield_state.")
        if self.active_player_id is None:
            raise GameLifecycleError("Objective control updates require an active player.")
        record = resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                self,
                timing=timing,
                phase=completed_phase,
            )
        )
        self.record_objective_control_record(record)
        return record

    def _score_objective_control_boundary(self, record: ObjectiveControlRecord) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Mission scoring requires MissionSetup.")
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        award = policy.primary_award_from_objective_control(record)
        if award is None:
            return
        self.award_victory_points(award)

    def _resolve_end_turn_cleanup_boundary(self, *, completed_phase: BattlePhase) -> None:
        if self.battlefield_state is None:
            raise GameLifecycleError("End-turn cleanup requires battlefield_state.")
        if self.active_player_id is None:
            raise GameLifecycleError("End-turn cleanup requires an active player.")
        scenario = BattlefieldScenario(
            armies=tuple(self.army_definitions),
            battlefield_state=self.battlefield_state,
        )
        cleanup, updated_battlefield = resolve_end_turn_cleanup(
            game_id=self.game_id,
            scenario=scenario,
            ruleset_descriptor=self._ruleset_descriptor_for_runtime_policy(),
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase=completed_phase,
        )
        self.battlefield_state = updated_battlefield
        self.end_turn_cleanup_states.append(cleanup)
        self.end_turn_cleanup_states.sort(key=lambda state: state.cleanup_id)

    def _resolve_unarrived_reserve_destruction_boundary(self, *, end_of_battle: bool) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Reserve destruction requires MissionSetup.")
        if self.battlefield_state is None:
            raise GameLifecycleError("Reserve destruction requires battlefield_state.")
        policy = reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policy_from_setup(self.mission_setup)
        )
        destruction = resolve_unarrived_reserve_destruction(
            reserve_states=tuple(self.reserve_states),
            armies=tuple(self.army_definitions),
            battlefield_state=self.battlefield_state,
            policy=policy,
            battle_round=self.battle_round,
            end_of_battle=end_of_battle,
        )
        if not destruction.destroyed_model_instance_ids:
            return
        self.battlefield_state = apply_reserve_destruction_to_battlefield(
            battlefield_state=self.battlefield_state,
            destruction=destruction,
        )
        self.reserve_states = list(destruction.updated_reserve_states)

    def _ruleset_descriptor_for_runtime_policy(self) -> RulesetDescriptor:
        if self.mission_setup is not None and (
            self.mission_setup.mission_pack_id == tenth_ca_2025_26_source.MISSION_PACK_ID
        ):
            return RulesetDescriptor.warhammer_40000_tenth_chapter_approved_2025_26()
        return RulesetDescriptor.warhammer_40000_tenth()

    def _active_player_is_last_in_round(self, player_id: str) -> bool:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return self.turn_order.index(requested_player_id) + 1 == len(self.turn_order)

    def _game_ends_after_completed_round(self, battle_round: int) -> bool:
        requested_round = _validate_positive_int("battle_round", battle_round)
        if self.mission_setup is None:
            raise GameLifecycleError("Game-end policy requires MissionSetup.")
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        return requested_round >= policy.game_length_battle_rounds

    def game_result_payload(self) -> dict[str, JsonValue]:
        if self.stage is not GameLifecycleStage.COMPLETE:
            raise GameLifecycleError("Game result requires complete stage.")
        if self.mission_setup is None:
            raise GameLifecycleError("Game result requires MissionSetup.")
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        result = FinalScoringResult.from_ledgers(
            game_id=self.game_id,
            battle_round=self.battle_round,
            policy=policy,
            ledgers=tuple(self.victory_point_ledgers),
            scoring_windows=tuple(self.scoring_window_states),
        )
        return cast(dict[str, JsonValue], result.to_payload())

    def _record_scoring_windows_boundary(self, window_kind: ScoringWindowKind) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Scoring windows require MissionSetup.")
        kind = ScoringWindowKind(window_kind)
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        windows = (
            policy.end_of_round_scoring_windows
            if kind is ScoringWindowKind.END_OF_ROUND
            else policy.end_of_game_scoring_windows
        )
        for window in windows:
            state = ScoringWindowState(
                window_id=(
                    f"scoring-window:{self.game_id}:round-{self.battle_round:02d}:"
                    f"{kind.value}:{window}"
                ),
                game_id=self.game_id,
                battle_round=self.battle_round,
                window_kind=kind,
                window=window,
                source_id=f"{policy.source_id}:window:{kind.value}:{window}",
            )
            if self._has_scoring_window_state(state.window_id):
                continue
            self.scoring_window_states.append(state)
        self.scoring_window_states.sort(key=lambda state: state.window_id)

    def _has_scoring_window_state(self, window_id: str) -> bool:
        requested_id = _validate_identifier("window_id", window_id)
        return any(state.window_id == requested_id for state in self.scoring_window_states)

    def _assert_battlefield_state_clear_of_objective_markers(
        self,
        battlefield_state: BattlefieldRuntimeState,
    ) -> None:
        if self.mission_setup is None:
            return
        markers = tuple(
            marker.to_objective_marker() for marker in self.mission_setup.objective_markers
        )
        if not markers:
            return
        scenario = BattlefieldScenario(
            armies=tuple(self.army_definitions),
            battlefield_state=battlefield_state,
        )
        for placed_army in battlefield_state.placed_armies:
            for unit_placement in placed_army.unit_placements:
                for model_placement in unit_placement.model_placements:
                    model = geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(model_placement),
                        placement=model_placement,
                    )
                    violation = objective_marker_endpoint_placement_violation(
                        model=model,
                        objective_markers=markers,
                        violation_code="objective_marker_endpoint_overlap",
                        placement_label="Battlefield placement",
                    )
                    if violation is not None:
                        raise GameLifecycleError(
                            "Battlefield placement cannot end on an objective marker."
                        )

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
        self.disembarked_unit_states = [
            state
            for state in self.disembarked_unit_states
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


def _validate_optional_mission_setup(
    value: object | None,
    *,
    player_ids: tuple[str, ...],
) -> MissionSetup | None:
    if value is None:
        return None
    if type(value) is not MissionSetup:
        raise GameLifecycleError("mission_setup must be a MissionSetup.")
    if value.attacker_player_id not in player_ids:
        raise GameLifecycleError("mission_setup attacker_player_id is not in this game.")
    if value.defender_player_id not in player_ids:
        raise GameLifecycleError("mission_setup defender_player_id is not in this game.")
    return value


def _validate_optional_movement_phase_state(
    value: object | None,
) -> MovementPhaseState | None:
    if value is None:
        return None
    if type(value) is not MovementPhaseState:
        raise GameLifecycleError("GameState movement_phase_state must be a MovementPhaseState.")
    return value


def _validate_optional_shooting_phase_state(
    value: object | None,
) -> ShootingPhaseState | None:
    if value is None:
        return None
    if type(value) is not ShootingPhaseState:
        raise GameLifecycleError("GameState shooting_phase_state must be a ShootingPhaseState.")
    return value


def _validate_optional_command_step_state(
    value: object | None,
) -> CommandStepState | None:
    if value is None:
        return None
    if type(value) is not CommandStepState:
        raise GameLifecycleError("GameState command_step_state must be a CommandStepState.")
    return value


def _validate_command_point_ledgers(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[CommandPointLedger]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState command_point_ledgers must be a list.")
    if not values:
        return initial_command_point_ledgers(player_ids)
    validated: list[CommandPointLedger] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not CommandPointLedger:
            raise GameLifecycleError(
                "GameState command_point_ledgers must contain CommandPointLedger values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("CommandPointLedger player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameState command_point_ledgers must be unique.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError("GameState command_point_ledgers must include every player.")
    return sorted(validated, key=lambda ledger: ledger.player_id)


def _validate_victory_point_ledgers(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[VictoryPointLedger]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState victory_point_ledgers must be a list.")
    if not values:
        return initial_victory_point_ledgers(player_ids)
    validated: list[VictoryPointLedger] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not VictoryPointLedger:
            raise GameLifecycleError(
                "GameState victory_point_ledgers must contain VictoryPointLedger values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("VictoryPointLedger player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameState victory_point_ledgers must be unique.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError("GameState victory_point_ledgers must include every player.")
    return sorted(validated, key=lambda ledger: ledger.player_id)


def _validate_stratagem_use_records(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[StratagemUseRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState stratagem_use_records must be a list.")
    validated: list[StratagemUseRecord] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StratagemUseRecord:
            raise GameLifecycleError(
                "GameState stratagem_use_records must contain StratagemUseRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StratagemUseRecord player_id is not in this game.")
        if value.use_id in seen:
            raise GameLifecycleError("GameState stratagem_use_records must be unique.")
        seen.add(value.use_id)
        validated.append(value)
    return sorted(validated, key=lambda record: record.use_id)


def _validate_starting_strength_records(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    player_ids: tuple[str, ...],
) -> list[StartingStrengthRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState starting_strength_records must be a list.")
    if not values and army_definitions:
        derived: list[StartingStrengthRecord] = []
        for army_definition in army_definitions:
            derived.extend(
                starting_strength_records_for_units(
                    player_id=army_definition.player_id,
                    units=army_definition.units,
                )
            )
        return sorted(derived, key=lambda record: record.unit_instance_id)

    unit_owner_by_id = _unit_owner_by_id(army_definitions)
    validated: list[StartingStrengthRecord] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StartingStrengthRecord:
            raise GameLifecycleError(
                "GameState starting_strength_records must contain StartingStrengthRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StartingStrengthRecord player_id is not in this game.")
        owner = unit_owner_by_id.get(value.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("StartingStrengthRecord unit is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("StartingStrengthRecord player_id drift.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState starting_strength_records must be unique.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    if set(unit_owner_by_id) != seen:
        raise GameLifecycleError("GameState starting_strength_records must include every unit.")
    return sorted(validated, key=lambda record: record.unit_instance_id)


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


def _validate_hover_mode_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[HoverModeState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState hover_mode_states must be a list.")
    validated: list[HoverModeState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not HoverModeState:
            raise GameLifecycleError(
                "GameState hover_mode_states must contain HoverModeState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("HoverModeState player_id is not in this game.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState hover_mode_states must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.unit_instance_id)


def _validate_hover_mode_state_references(state: GameState) -> None:
    if not state.hover_mode_states:
        return
    for hover_mode_state in state.hover_mode_states:
        _validate_hover_mode_state_reference(state, hover_mode_state)


def _validate_hover_mode_state_reference(
    state: GameState,
    hover_mode_state: HoverModeState,
) -> None:
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    unit = unit_by_id.get(hover_mode_state.unit_instance_id)
    if unit is None:
        raise GameLifecycleError("hover_mode_states unit is unknown.")
    if unit_owner_by_id[hover_mode_state.unit_instance_id] != hover_mode_state.player_id:
        raise GameLifecycleError("hover_mode_states player_id does not match unit owner.")
    if hover_mode_state.source_id != "hover":
        raise GameLifecycleError("hover_mode_states source_id drift.")
    if hover_mode_state.active and not _unit_has_aircraft_hover_keywords(unit.keywords):
        raise GameLifecycleError("hover_mode_states active unit must have AIRCRAFT and HOVER.")


def _validate_transport_cargo_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[TransportCargoState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState transport_cargo_states must be a list.")
    validated: list[TransportCargoState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not TransportCargoState:
            raise GameLifecycleError(
                "GameState transport_cargo_states must contain TransportCargoState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("TransportCargoState player_id is not in this game.")
        if value.transport_unit_instance_id in seen:
            raise GameLifecycleError("GameState transport_cargo_states must be unique.")
        seen.add(value.transport_unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.transport_unit_instance_id)


def _validate_disembarked_unit_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[DisembarkedUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState disembarked_unit_states must be a list.")
    validated: list[DisembarkedUnitState] = []
    seen: set[tuple[int, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not DisembarkedUnitState:
            raise GameLifecycleError(
                "GameState disembarked_unit_states must contain DisembarkedUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("DisembarkedUnitState player_id is not in this game.")
        key = (value.battle_round, value.player_id, value.unit_instance_id)
        if key in seen:
            raise GameLifecycleError("GameState disembarked_unit_states must be unique.")
        seen.add(key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (state.battle_round, state.player_id, state.unit_instance_id),
    )


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


def _validate_surge_move_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[SurgeMoveState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState surge_move_states must be a list.")
    validated: list[SurgeMoveState] = []
    seen_result_ids: set[str] = set()
    seen_same_phase_keys: set[tuple[int, str, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not SurgeMoveState:
            raise GameLifecycleError(
                "GameState surge_move_states must contain SurgeMoveState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("SurgeMoveState player_id is not in this game.")
        if value.result_id in seen_result_ids:
            raise GameLifecycleError("GameState surge_move_states must be unique by result.")
        seen_result_ids.add(value.result_id)
        same_phase_key = value.same_phase_key()
        if same_phase_key in seen_same_phase_keys:
            raise GameLifecycleError("GameState surge_move_states must be unique by unit phase.")
        seen_same_phase_keys.add(same_phase_key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (
            state.battle_round,
            state.phase,
            state.player_id,
            state.unit_instance_id,
            state.result_id,
        ),
    )


def _validate_battle_shocked_unit_states(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    battle_shocked_unit_ids: tuple[str, ...],
    player_ids: tuple[str, ...],
) -> list[BattleShockedUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState battle_shocked_unit_states must be a list.")
    unit_owner_by_id = _unit_owner_by_id(army_definitions)
    shocked_ids = set(battle_shocked_unit_ids)
    validated: list[BattleShockedUnitState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not BattleShockedUnitState:
            raise GameLifecycleError(
                "GameState battle_shocked_unit_states must contain BattleShockedUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("BattleShockedUnitState player_id is not in this game.")
        owner = unit_owner_by_id.get(value.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("BattleShockedUnitState unit is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("BattleShockedUnitState player_id drift.")
        if value.unit_instance_id not in shocked_ids:
            raise GameLifecycleError("BattleShockedUnitState missing battle_shocked_unit_id.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState battle_shocked_unit_states must be unique.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    if seen != shocked_ids:
        raise GameLifecycleError(
            "GameState battle_shocked_unit_ids must match BattleShockedUnitState records."
        )
    return sorted(validated, key=lambda state: state.unit_instance_id)


def _unit_has_aircraft_hover_keywords(keywords: tuple[str, ...]) -> bool:
    keyword_set = {
        _validate_identifier("unit keyword", keyword).upper().replace(" ", "_").replace("-", "_")
        for keyword in keywords
    }
    return "AIRCRAFT" in keyword_set and "HOVER" in keyword_set


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
        if (
            state.command_step_state is not None
            and state.current_battle_phase is not BattlePhase.COMMAND
        ):
            raise GameLifecycleError("command_step_state requires COMMAND phase.")
        if state.command_step_state is not None:
            if state.command_step_state.active_player_id != state.active_player_id:
                raise GameLifecycleError("command_step_state active player drift.")
            if state.command_step_state.battle_round != state.battle_round:
                raise GameLifecycleError("command_step_state battle round drift.")
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


def _unit_owner_by_id(army_definitions: list[ArmyDefinition]) -> dict[str, str]:
    return {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }


def _validate_objective_control_records(
    records: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[ObjectiveControlRecord]:
    if not isinstance(records, list):
        raise GameLifecycleError("GameState objective_control_records must be a list.")
    validated: list[ObjectiveControlRecord] = []
    seen: set[str] = set()
    for record in cast(list[object], records):
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "GameState objective_control_records must contain ObjectiveControlRecord values."
            )
        if record.game_id != game_id:
            raise GameLifecycleError("ObjectiveControlRecord game_id drift.")
        if record.active_player_id not in player_ids:
            raise GameLifecycleError("ObjectiveControlRecord active_player_id is not in this game.")
        if record.record_id in seen:
            raise GameLifecycleError("GameState objective_control_records must be unique.")
        seen.add(record.record_id)
        validated.append(record)
    return validated


def _validate_mission_action_states(
    states: object,
    *,
    player_ids: tuple[str, ...],
) -> list[MissionActionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState mission_action_states must be a list.")
    validated: list[MissionActionState] = []
    seen: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not MissionActionState:
            raise GameLifecycleError(
                "GameState mission_action_states must contain MissionActionState values."
            )
        if state.player_id not in player_ids:
            raise GameLifecycleError("MissionActionState player_id is not in this game.")
        if state.action_id in seen:
            raise GameLifecycleError("GameState mission_action_states must be unique.")
        seen.add(state.action_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.action_id)


def _validate_end_turn_cleanup_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[EndTurnCleanupState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState end_turn_cleanup_states must be a list.")
    validated: list[EndTurnCleanupState] = []
    seen: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not EndTurnCleanupState:
            raise GameLifecycleError(
                "GameState end_turn_cleanup_states must contain EndTurnCleanupState values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("EndTurnCleanupState game_id drift.")
        if state.active_player_id not in player_ids:
            raise GameLifecycleError("EndTurnCleanupState active_player_id is not in this game.")
        if state.cleanup_id in seen:
            raise GameLifecycleError("GameState end_turn_cleanup_states must be unique.")
        seen.add(state.cleanup_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.cleanup_id)


def _validate_scoring_window_states(
    states: object,
    *,
    game_id: str,
) -> list[ScoringWindowState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState scoring_window_states must be a list.")
    requested_game_id = _validate_identifier("game_id", game_id)
    validated: list[ScoringWindowState] = []
    seen: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not ScoringWindowState:
            raise GameLifecycleError(
                "GameState scoring_window_states must contain ScoringWindowState values."
            )
        if state.game_id != requested_game_id:
            raise GameLifecycleError("ScoringWindowState game_id drift.")
        if state.window_id in seen:
            raise GameLifecycleError("GameState scoring_window_states must be unique.")
        seen.add(state.window_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.window_id)


def _validate_persisting_effects(
    effects: object,
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
    player_ids: tuple[str, ...],
) -> list[PersistingEffect]:
    if not isinstance(effects, list):
        raise GameLifecycleError("GameState persisting_effects must be a list.")
    unit_ids = _known_rules_unit_ids(
        army_definitions=army_definitions,
        starting_strength_records=starting_strength_records,
    )
    validated: list[PersistingEffect] = []
    seen: set[str] = set()
    for effect in cast(list[object], effects):
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError(
                "GameState persisting_effects must contain PersistingEffect values."
            )
        if effect.owner_player_id not in player_ids:
            raise GameLifecycleError("PersistingEffect owner_player_id is not in this game.")
        if not unit_ids:
            raise GameLifecycleError("PersistingEffect requires mustered army definitions.")
        if any(unit_id not in unit_ids for unit_id in effect.target_unit_instance_ids):
            raise GameLifecycleError("PersistingEffect target unit is unknown.")
        if effect.effect_id in seen:
            raise GameLifecycleError("GameState persisting_effects must be unique.")
        seen.add(effect.effect_id)
        validated.append(effect)
    return sorted(validated, key=lambda effect: effect.effect_id)


def _known_rules_unit_ids(
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
) -> set[str]:
    return {unit.unit_instance_id for army in army_definitions for unit in army.units} | {
        record.unit_instance_id for record in starting_strength_records
    }


def _validate_secondary_mission_card_states(
    states: object,
    *,
    player_ids: tuple[str, ...],
) -> list[SecondaryMissionCardState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary_mission_card_states must be a list.")
    validated: list[SecondaryMissionCardState] = []
    seen: set[tuple[str, str, SecondaryMissionCardMode, int]] = set()
    for state in cast(list[object], states):
        if type(state) is not SecondaryMissionCardState:
            raise GameLifecycleError(
                "GameState secondary_mission_card_states must contain card states."
            )
        if state.player_id not in player_ids:
            raise GameLifecycleError("SecondaryMissionCardState player_id is not in this game.")
        key = (
            state.player_id,
            state.secondary_mission_id,
            state.mode,
            state.battle_round,
        )
        if key in seen:
            raise GameLifecycleError("GameState secondary_mission_card_states must be unique.")
        seen.add(key)
        validated.append(state)
    return sorted(
        validated,
        key=lambda state: (
            state.player_id,
            state.battle_round,
            state.mode.value,
            state.secondary_mission_id,
        ),
    )


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
