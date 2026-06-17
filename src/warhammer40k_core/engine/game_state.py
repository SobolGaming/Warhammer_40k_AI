from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    AttachedUnitFormation,
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
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionSource,
    DestructionReactionSourcePayload,
    FeelNoPainSource,
    FeelNoPainSourcePayload,
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
from warhammer40k_core.engine.faction_rule_states import (
    FactionRuleState,
    FactionRuleStatePayload,
)
from warhammer40k_core.engine.fight_order import FightPhaseState, FightPhaseStatePayload
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
from warhammer40k_core.engine.phases.charge import (
    ChargePhaseState,
    ChargePhaseStatePayload,
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
    OutOfPhaseShootingState,
    OutOfPhaseShootingStatePayload,
    ShootingPhaseState,
    ShootingPhaseStatePayload,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionRecord,
    PreBattleActionRecordPayload,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatePayload,
    ReserveStatus,
    ReserveUnitPointValue,
    ReserveUnitPointValuePayload,
    StrategicReserveDeclaration,
    apply_reserve_destruction_to_battlefield,
    reserve_origin_from_token,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.scoring import (
    FinalScoringResult,
    PrimaryObjectiveTurnStartState,
    PrimaryObjectiveTurnStartStatePayload,
    PrimaryTerrainTrapState,
    PrimaryTerrainTrapStatePayload,
    PrimaryUnitDestructionState,
    PrimaryUnitDestructionStatePayload,
    ScoringWindowKind,
    ScoringWindowState,
    ScoringWindowStatePayload,
    SecondaryDestroyedModelState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatePayload,
    SecondaryMissionCardStatus,
    SecondaryObjectiveCleanseState,
    SecondaryObjectiveCleanseStatePayload,
    SecondaryTerrainPlunderState,
    SecondaryTerrainPlunderStatePayload,
    SecondaryUnitDestructionState,
    SecondaryUnitDestructionStatePayload,
    TacticalSecondaryAchievementContext,
    TacticalSecondaryAchievementContextPayload,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointLedgerPayload,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    initial_victory_point_ledgers,
    secondary_mission_card_mode_from_token,
)
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlState,
    StickyObjectiveControlStatePayload,
    apply_sticky_objective_control,
    sticky_objective_control_state_is_expired,
)
from warhammer40k_core.engine.stratagems import StratagemUseRecord, StratagemUseRecordPayload
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    DisembarkedUnitStatePayload,
    TransportCapacityProfile,
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
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as eleventh_ca_2026_27_source,
)


class SecondaryMissionMode(StrEnum):
    FIXED = "fixed"
    TACTICAL = "tactical"


class GameConfigPayload(TypedDict):
    game_id: str
    ruleset_descriptor: RulesetDescriptorPayload
    army_catalog: ArmyCatalogPayload
    army_muster_requests: list[ArmyMusterRequestPayload]
    allow_legacy_non_strict_rosters: bool
    player_ids: list[str]
    turn_order: list[str]
    fixed_secondary_mission_ids: list[str]
    tactical_secondary_draw_count: int
    mission_setup: MissionSetupPayload | None
    reserve_unit_points: list[ReserveUnitPointValuePayload]


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


DEDICATED_TRANSPORT_EMPTY_STARTING_CARGO_CONSEQUENCE = (
    "empty_starting_cargo_destroyed_first_battle_round"
)


class DedicatedTransportSetupConsequencePayload(TypedDict):
    player_id: str
    transport_unit_instance_id: str
    consequence_kind: str
    destroyed_battle_round: int
    source_id: str


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
    faction_rule_states: list[FactionRuleStatePayload]
    army_definitions: list[ArmyDefinitionPayload]
    starting_strength_records: list[StartingStrengthRecordPayload]
    battlefield_state: BattlefieldRuntimeStatePayload | None
    mission_setup: MissionSetupPayload | None
    movement_phase_state: MovementPhaseStatePayload | None
    charge_phase_state: ChargePhaseStatePayload | None
    fight_phase_state: FightPhaseStatePayload | None
    shooting_phase_state: ShootingPhaseStatePayload | None
    out_of_phase_shooting_state: OutOfPhaseShootingStatePayload | None
    feel_no_pain_sources_by_model_id: dict[str, list[FeelNoPainSourcePayload]]
    feel_no_pain_decline_allowed_model_ids: list[str]
    destruction_reaction_sources_by_model_id: dict[str, list[DestructionReactionSourcePayload]]
    reserve_states: list[ReserveStatePayload]
    hover_mode_states: list[HoverModeStatePayload]
    transport_cargo_states: list[TransportCargoStatePayload]
    dedicated_transport_setup_consequences: list[DedicatedTransportSetupConsequencePayload]
    disembarked_unit_states: list[DisembarkedUnitStatePayload]
    advanced_unit_states: list[AdvancedUnitStatePayload]
    fell_back_unit_states: list[FellBackUnitStatePayload]
    surge_move_states: list[SurgeMoveStatePayload]
    battle_shocked_unit_ids: list[str]
    battle_shocked_unit_states: list[BattleShockedUnitStatePayload]
    objective_control_records: list[ObjectiveControlRecordPayload]
    sticky_objective_control_states: list[StickyObjectiveControlStatePayload]
    primary_objective_turn_start_states: list[PrimaryObjectiveTurnStartStatePayload]
    primary_terrain_trap_states: list[PrimaryTerrainTrapStatePayload]
    primary_unit_destruction_states: list[PrimaryUnitDestructionStatePayload]
    secondary_unit_destruction_states: list[SecondaryUnitDestructionStatePayload]
    secondary_objective_cleanse_states: list[SecondaryObjectiveCleanseStatePayload]
    secondary_terrain_plunder_states: list[SecondaryTerrainPlunderStatePayload]
    mission_action_states: list[MissionActionStatePayload]
    end_turn_cleanup_states: list[EndTurnCleanupStatePayload]
    scoring_window_states: list[ScoringWindowStatePayload]
    persisting_effects: list[PersistingEffectPayload]
    secondary_mission_choices: list[SecondaryMissionChoicePayload]
    tactical_secondary_draws: list[TacticalSecondaryDrawPayload]
    prebattle_action_records: list[PreBattleActionRecordPayload]
    secondary_mission_card_states: list[SecondaryMissionCardStatePayload]
    tactical_secondary_achievement_contexts: list[TacticalSecondaryAchievementContextPayload]
    tactical_secondary_discard_cp_reward_window_ids: list[str]
    tactical_secondary_replacement_player_ids: list[str]


def _new_secondary_mission_choices() -> list[SecondaryMissionChoice]:
    return []


def _new_tactical_secondary_draws() -> list[TacticalSecondaryDraw]:
    return []


def _new_prebattle_action_records() -> list[PreBattleActionRecord]:
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


def _new_faction_rule_states() -> list[FactionRuleState]:
    return []


def _new_starting_strength_records() -> list[StartingStrengthRecord]:
    return []


def _new_reserve_states() -> list[ReserveState]:
    return []


def _new_hover_mode_states() -> list[HoverModeState]:
    return []


def _new_transport_cargo_states() -> list[TransportCargoState]:
    return []


def _new_dedicated_transport_setup_consequences() -> list[DedicatedTransportSetupConsequence]:
    return []


def _new_disembarked_unit_states() -> list[DisembarkedUnitState]:
    return []


def _new_battle_shocked_unit_ids() -> list[str]:
    return []


def _new_battle_shocked_unit_states() -> list[BattleShockedUnitState]:
    return []


def _new_objective_control_records() -> list[ObjectiveControlRecord]:
    return []


def _new_sticky_objective_control_states() -> list[StickyObjectiveControlState]:
    return []


def _new_primary_objective_turn_start_states() -> list[PrimaryObjectiveTurnStartState]:
    return []


def _new_primary_terrain_trap_states() -> list[PrimaryTerrainTrapState]:
    return []


def _new_primary_unit_destruction_states() -> list[PrimaryUnitDestructionState]:
    return []


def _new_secondary_unit_destruction_states() -> list[SecondaryUnitDestructionState]:
    return []


def _new_secondary_objective_cleanse_states() -> list[SecondaryObjectiveCleanseState]:
    return []


def _new_secondary_terrain_plunder_states() -> list[SecondaryTerrainPlunderState]:
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


def _new_tactical_secondary_achievement_contexts() -> list[TacticalSecondaryAchievementContext]:
    return []


def _new_tactical_secondary_discard_cp_reward_window_ids() -> list[str]:
    return []


def _new_tactical_secondary_replacement_player_ids() -> list[str]:
    return []


def _new_persisting_effects() -> list[PersistingEffect]:
    return []


def _new_feel_no_pain_sources_by_model_id() -> dict[str, tuple[FeelNoPainSource, ...]]:
    return {}


def _new_feel_no_pain_decline_allowed_model_ids() -> list[str]:
    return []


def _new_destruction_reaction_sources_by_model_id() -> dict[
    str,
    tuple[DestructionReactionSource, ...],
]:
    return {}


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
    reserve_unit_points: tuple[ReserveUnitPointValue, ...] = ()
    allow_legacy_non_strict_rosters: bool = False

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
            "allow_legacy_non_strict_rosters",
            _validate_bool(
                "GameConfig allow_legacy_non_strict_rosters",
                self.allow_legacy_non_strict_rosters,
            ),
        )
        if not self.allow_legacy_non_strict_rosters:
            _validate_strict_roster_legality_requests(self.army_muster_requests)
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
        object.__setattr__(
            self,
            "reserve_unit_points",
            _validate_reserve_unit_points(
                self.reserve_unit_points,
                army_muster_requests=self.army_muster_requests,
            ),
        )
        _validate_lifecycle_sequences(self.ruleset_descriptor)

    def to_payload(self) -> GameConfigPayload:
        return {
            "game_id": self.game_id,
            "ruleset_descriptor": self.ruleset_descriptor.to_payload(),
            "army_catalog": self.army_catalog.to_payload(),
            "army_muster_requests": [request.to_payload() for request in self.army_muster_requests],
            "allow_legacy_non_strict_rosters": self.allow_legacy_non_strict_rosters,
            "player_ids": list(self.player_ids),
            "turn_order": list(self.turn_order),
            "fixed_secondary_mission_ids": list(self.fixed_secondary_mission_ids),
            "tactical_secondary_draw_count": self.tactical_secondary_draw_count,
            "mission_setup": (
                None if self.mission_setup is None else self.mission_setup.to_payload()
            ),
            "reserve_unit_points": [entry.to_payload() for entry in self.reserve_unit_points],
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
            allow_legacy_non_strict_rosters=payload["allow_legacy_non_strict_rosters"],
            player_ids=tuple(payload["player_ids"]),
            turn_order=tuple(payload["turn_order"]),
            fixed_secondary_mission_ids=tuple(payload["fixed_secondary_mission_ids"]),
            tactical_secondary_draw_count=payload["tactical_secondary_draw_count"],
            mission_setup=(
                None
                if payload["mission_setup"] is None
                else MissionSetup.from_payload(payload["mission_setup"])
            ),
            reserve_unit_points=tuple(
                ReserveUnitPointValue.from_payload(entry)
                for entry in payload["reserve_unit_points"]
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


@dataclass(frozen=True, slots=True)
class DedicatedTransportSetupConsequence:
    player_id: str
    transport_unit_instance_id: str
    consequence_kind: str
    destroyed_battle_round: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DedicatedTransportSetupConsequence player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DedicatedTransportSetupConsequence transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "consequence_kind",
            _validate_identifier(
                "DedicatedTransportSetupConsequence consequence_kind",
                self.consequence_kind,
            ),
        )
        if self.consequence_kind != DEDICATED_TRANSPORT_EMPTY_STARTING_CARGO_CONSEQUENCE:
            raise GameLifecycleError("DedicatedTransportSetupConsequence kind is unsupported.")
        object.__setattr__(
            self,
            "destroyed_battle_round",
            _validate_positive_int(
                "DedicatedTransportSetupConsequence destroyed_battle_round",
                self.destroyed_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DedicatedTransportSetupConsequence source_id", self.source_id),
        )

    @classmethod
    def empty_dedicated_transport(
        cls,
        *,
        player_id: str,
        transport_unit_instance_id: str,
        source_id: str,
    ) -> Self:
        return cls(
            player_id=player_id,
            transport_unit_instance_id=transport_unit_instance_id,
            consequence_kind=DEDICATED_TRANSPORT_EMPTY_STARTING_CARGO_CONSEQUENCE,
            destroyed_battle_round=1,
            source_id=source_id,
        )

    def to_payload(self) -> DedicatedTransportSetupConsequencePayload:
        return {
            "player_id": self.player_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "consequence_kind": self.consequence_kind,
            "destroyed_battle_round": self.destroyed_battle_round,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: DedicatedTransportSetupConsequencePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            consequence_kind=payload["consequence_kind"],
            destroyed_battle_round=payload["destroyed_battle_round"],
            source_id=payload["source_id"],
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
    faction_rule_states: list[FactionRuleState] = field(default_factory=_new_faction_rule_states)
    army_definitions: list[ArmyDefinition] = field(default_factory=_new_army_definitions)
    starting_strength_records: list[StartingStrengthRecord] = field(
        default_factory=_new_starting_strength_records
    )
    battlefield_state: BattlefieldRuntimeState | None = None
    mission_setup: MissionSetup | None = None
    movement_phase_state: MovementPhaseState | None = None
    charge_phase_state: ChargePhaseState | None = None
    fight_phase_state: FightPhaseState | None = None
    shooting_phase_state: ShootingPhaseState | None = None
    out_of_phase_shooting_state: OutOfPhaseShootingState | None = None
    feel_no_pain_sources_by_model_id: dict[str, tuple[FeelNoPainSource, ...]] = field(
        default_factory=_new_feel_no_pain_sources_by_model_id
    )
    feel_no_pain_decline_allowed_model_ids: list[str] = field(
        default_factory=_new_feel_no_pain_decline_allowed_model_ids
    )
    destruction_reaction_sources_by_model_id: dict[
        str,
        tuple[DestructionReactionSource, ...],
    ] = field(default_factory=_new_destruction_reaction_sources_by_model_id)
    reserve_states: list[ReserveState] = field(default_factory=_new_reserve_states)
    hover_mode_states: list[HoverModeState] = field(default_factory=_new_hover_mode_states)
    transport_cargo_states: list[TransportCargoState] = field(
        default_factory=_new_transport_cargo_states
    )
    dedicated_transport_setup_consequences: list[DedicatedTransportSetupConsequence] = field(
        default_factory=_new_dedicated_transport_setup_consequences
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
    sticky_objective_control_states: list[StickyObjectiveControlState] = field(
        default_factory=_new_sticky_objective_control_states
    )
    primary_objective_turn_start_states: list[PrimaryObjectiveTurnStartState] = field(
        default_factory=_new_primary_objective_turn_start_states
    )
    primary_terrain_trap_states: list[PrimaryTerrainTrapState] = field(
        default_factory=_new_primary_terrain_trap_states
    )
    primary_unit_destruction_states: list[PrimaryUnitDestructionState] = field(
        default_factory=_new_primary_unit_destruction_states
    )
    secondary_unit_destruction_states: list[SecondaryUnitDestructionState] = field(
        default_factory=_new_secondary_unit_destruction_states
    )
    secondary_objective_cleanse_states: list[SecondaryObjectiveCleanseState] = field(
        default_factory=_new_secondary_objective_cleanse_states
    )
    secondary_terrain_plunder_states: list[SecondaryTerrainPlunderState] = field(
        default_factory=_new_secondary_terrain_plunder_states
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
    prebattle_action_records: list[PreBattleActionRecord] = field(
        default_factory=_new_prebattle_action_records
    )
    secondary_mission_card_states: list[SecondaryMissionCardState] = field(
        default_factory=_new_secondary_mission_card_states
    )
    tactical_secondary_achievement_contexts: list[TacticalSecondaryAchievementContext] = field(
        default_factory=_new_tactical_secondary_achievement_contexts
    )
    tactical_secondary_discard_cp_reward_window_ids: list[str] = field(
        default_factory=_new_tactical_secondary_discard_cp_reward_window_ids
    )
    tactical_secondary_replacement_player_ids: list[str] = field(
        default_factory=_new_tactical_secondary_replacement_player_ids
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
        self.faction_rule_states = _validate_faction_rule_states(
            self.faction_rule_states,
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
        self.charge_phase_state = _validate_optional_charge_phase_state(self.charge_phase_state)
        self.fight_phase_state = _validate_optional_fight_phase_state(self.fight_phase_state)
        self.shooting_phase_state = _validate_optional_shooting_phase_state(
            self.shooting_phase_state
        )
        self.out_of_phase_shooting_state = _validate_optional_out_of_phase_shooting_state(
            self.out_of_phase_shooting_state
        )
        self.feel_no_pain_sources_by_model_id = _validate_feel_no_pain_sources_by_model_id(
            self.feel_no_pain_sources_by_model_id,
            army_definitions=self.army_definitions,
        )
        self.feel_no_pain_decline_allowed_model_ids = list(
            _validate_feel_no_pain_decline_allowed_model_ids(
                self.feel_no_pain_decline_allowed_model_ids,
                source_model_ids=tuple(self.feel_no_pain_sources_by_model_id),
            )
        )
        self.destruction_reaction_sources_by_model_id = (
            _validate_destruction_reaction_sources_by_model_id(
                self.destruction_reaction_sources_by_model_id,
                army_definitions=self.army_definitions,
            )
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
        self.dedicated_transport_setup_consequences = (
            _validate_dedicated_transport_setup_consequences(
                self.dedicated_transport_setup_consequences,
                army_definitions=self.army_definitions,
                player_ids=self.player_ids,
            )
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
        self.sticky_objective_control_states = _validate_sticky_objective_control_states(
            self.sticky_objective_control_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.primary_objective_turn_start_states = _validate_primary_objective_turn_start_states(
            self.primary_objective_turn_start_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.primary_terrain_trap_states = _validate_primary_terrain_trap_states(
            self.primary_terrain_trap_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.primary_unit_destruction_states = _validate_primary_unit_destruction_states(
            self.primary_unit_destruction_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.secondary_unit_destruction_states = _validate_secondary_unit_destruction_states(
            self.secondary_unit_destruction_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.secondary_objective_cleanse_states = _validate_secondary_objective_cleanse_states(
            self.secondary_objective_cleanse_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.secondary_terrain_plunder_states = _validate_secondary_terrain_plunder_states(
            self.secondary_terrain_plunder_states,
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
        self.prebattle_action_records = _validate_prebattle_action_records(
            self.prebattle_action_records,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.secondary_mission_card_states = _validate_secondary_mission_card_states(
            self.secondary_mission_card_states,
            player_ids=self.player_ids,
        )
        self.tactical_secondary_achievement_contexts = (
            _validate_tactical_secondary_achievement_contexts(
                self.tactical_secondary_achievement_contexts,
                game_id=self.game_id,
                player_ids=self.player_ids,
            )
        )
        self.tactical_secondary_discard_cp_reward_window_ids = list(
            _validate_identifier_tuple(
                "GameState tactical_secondary_discard_cp_reward_window_ids",
                tuple(self.tactical_secondary_discard_cp_reward_window_ids),
                min_length=0,
                sort_values=True,
            )
        )
        self.tactical_secondary_replacement_player_ids = list(
            _validate_identifier_tuple(
                "GameState tactical_secondary_replacement_player_ids",
                tuple(self.tactical_secondary_replacement_player_ids),
                min_length=0,
                sort_values=True,
            )
        )
        for player_id in self.tactical_secondary_replacement_player_ids:
            if player_id not in self.player_ids:
                raise GameLifecycleError(
                    "GameState tactical_secondary_replacement_player_ids must be player IDs."
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

    def effective_active_player_id(self) -> str | None:
        out_of_phase_shooting = self.out_of_phase_shooting_state
        if out_of_phase_shooting is not None:
            return out_of_phase_shooting.player_id
        shooting_state = self.shooting_phase_state
        if shooting_state is not None and shooting_state.active_selection is not None:
            return shooting_state.active_selection.player_id
        charge_state = self.charge_phase_state
        if charge_state is not None and charge_state.active_selection is not None:
            return charge_state.active_selection.player_id
        movement_state = self.movement_phase_state
        if movement_state is not None and movement_state.active_selection is not None:
            return movement_state.active_selection.player_id
        return self.active_player_id

    def effective_opposing_player_ids(self) -> tuple[str, ...]:
        effective_active_player_id = self.effective_active_player_id()
        if effective_active_player_id is None:
            return ()
        return tuple(
            player_id for player_id in self.player_ids if player_id != effective_active_player_id
        )

    def next_decision_request_id(self) -> str:
        self.decision_request_count += 1
        return f"decision-request-{self.decision_request_count:06d}"

    def record_model_feel_no_pain_sources(
        self,
        *,
        model_instance_id: str,
        sources: tuple[FeelNoPainSource, ...],
        decline_allowed: bool = False,
    ) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        source_tuple = _validate_feel_no_pain_source_tuple(
            "Feel No Pain sources",
            sources,
        )
        if type(decline_allowed) is not bool:
            raise GameLifecycleError("Feel No Pain decline_allowed must be a bool.")
        updated_sources = dict(self.feel_no_pain_sources_by_model_id)
        updated_sources[model_id] = source_tuple
        self.feel_no_pain_sources_by_model_id = _validate_feel_no_pain_sources_by_model_id(
            updated_sources,
            army_definitions=self.army_definitions,
        )
        decline_ids = set(self.feel_no_pain_decline_allowed_model_ids)
        if decline_allowed:
            decline_ids.add(model_id)
        else:
            decline_ids.discard(model_id)
        self.feel_no_pain_decline_allowed_model_ids = list(
            _validate_feel_no_pain_decline_allowed_model_ids(
                tuple(decline_ids),
                source_model_ids=tuple(self.feel_no_pain_sources_by_model_id),
            )
        )

    def clear_model_feel_no_pain_sources(self, *, model_instance_id: str) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        updated_sources = dict(self.feel_no_pain_sources_by_model_id)
        updated_sources.pop(model_id, None)
        self.feel_no_pain_sources_by_model_id = _validate_feel_no_pain_sources_by_model_id(
            updated_sources,
            army_definitions=self.army_definitions,
        )
        self.feel_no_pain_decline_allowed_model_ids = list(
            _validate_feel_no_pain_decline_allowed_model_ids(
                tuple(
                    model_id_value
                    for model_id_value in self.feel_no_pain_decline_allowed_model_ids
                    if model_id_value != model_id
                ),
                source_model_ids=tuple(self.feel_no_pain_sources_by_model_id),
            )
        )

    def feel_no_pain_sources_for_model(
        self,
        *,
        model_instance_id: str,
    ) -> tuple[FeelNoPainSource, ...]:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        return self.feel_no_pain_sources_by_model_id.get(model_id, ())

    def feel_no_pain_decline_allowed_for_model(
        self,
        *,
        model_instance_id: str,
    ) -> bool:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        return model_id in self.feel_no_pain_decline_allowed_model_ids

    def record_model_destruction_reaction_sources(
        self,
        *,
        model_instance_id: str,
        sources: tuple[DestructionReactionSource, ...],
    ) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        source_tuple = _validate_destruction_reaction_source_tuple(
            "Destruction reaction sources",
            sources,
        )
        if not source_tuple:
            raise GameLifecycleError("Destruction reaction registration requires sources.")
        updated_sources = dict(self.destruction_reaction_sources_by_model_id)
        updated_sources[model_id] = source_tuple
        self.destruction_reaction_sources_by_model_id = (
            _validate_destruction_reaction_sources_by_model_id(
                updated_sources,
                army_definitions=self.army_definitions,
            )
        )

    def clear_model_destruction_reaction_sources(self, *, model_instance_id: str) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        updated_sources = dict(self.destruction_reaction_sources_by_model_id)
        updated_sources.pop(model_id, None)
        self.destruction_reaction_sources_by_model_id = (
            _validate_destruction_reaction_sources_by_model_id(
                updated_sources,
                army_definitions=self.army_definitions,
            )
        )

    def destruction_reaction_sources_for_model(
        self,
        *,
        model_instance_id: str,
    ) -> tuple[DestructionReactionSource, ...]:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        return self.destruction_reaction_sources_by_model_id.get(model_id, ())

    def complete_current_setup_step(self) -> SetupStep:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can complete setup steps only during setup.")
        current = self.current_setup_step
        if current is None or self.setup_step_index is None:
            raise GameLifecycleError("GameState has no current setup step.")
        if self.setup_step_index + 1 < len(self.setup_sequence):
            self.setup_step_index += 1
            return current
        raise GameLifecycleError("Final setup step completion requires the setup completion gate.")

    def complete_final_setup_step_before_battle(self) -> SetupStep:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can complete setup steps only during setup.")
        current = self.current_setup_step
        if current is None or self.setup_step_index is None:
            raise GameLifecycleError("GameState has no current setup step.")
        if self.setup_step_index + 1 < len(self.setup_sequence):
            raise GameLifecycleError("GameState final setup gate requires the final setup step.")
        self.setup_step_index = None
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
        self._record_primary_objective_turn_start_boundary_if_available()
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
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=self.battle_round,
                phase=completed_phase,
                player_id=completed_player_id,
            )
        )
        phase_end_record = self._record_objective_control_boundary(
            completed_phase=completed_phase,
            timing=ObjectiveControlTiming.PHASE_END,
        )
        self._score_objective_control_boundary(phase_end_record)
        if self.battle_phase_index + 1 < len(self.battle_phase_sequence):
            if completed_phase is BattlePhase.COMMAND:
                self.command_step_state = None
            if completed_phase is BattlePhase.MOVEMENT:
                self.movement_phase_state = None
            if completed_phase is BattlePhase.SHOOTING:
                self.shooting_phase_state = None
            if completed_phase is BattlePhase.CHARGE:
                self.charge_phase_state = None
            if completed_phase is BattlePhase.FIGHT:
                self.fight_phase_state = None
            self.out_of_phase_shooting_state = None
            self.battle_phase_index += 1
            self._expire_persisting_effects_at_current_phase_start()
            return completed_phase
        self._clear_turn_action_states(
            player_id=completed_player_id,
            battle_round=self.battle_round,
        )
        self._resolve_end_turn_cleanup_boundary(completed_phase=completed_phase)
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.turn_end(
                battle_round=self.battle_round,
                player_id=completed_player_id,
            )
        )
        turn_end_record = self._record_objective_control_boundary(
            completed_phase=completed_phase,
            timing=ObjectiveControlTiming.TURN_END,
        )
        self._score_objective_control_boundary(turn_end_record)
        if completed_phase is BattlePhase.COMMAND:
            self.command_step_state = None
        if completed_phase is BattlePhase.MOVEMENT:
            self.movement_phase_state = None
        if completed_phase is BattlePhase.SHOOTING:
            self.shooting_phase_state = None
        if completed_phase is BattlePhase.CHARGE:
            self.charge_phase_state = None
        if completed_phase is BattlePhase.FIGHT:
            self.fight_phase_state = None
        self.out_of_phase_shooting_state = None
        completed_round = self.battle_round
        battle_round_ended = self._active_player_is_last_in_round(completed_player_id)
        if battle_round_ended:
            self.expire_persisting_effects_at_boundary(
                EffectExpirationBoundary.battle_round_end(battle_round=completed_round)
            )
            self._resolve_unarrived_reserve_destruction_boundary(end_of_battle=False)
            self._record_scoring_windows_boundary(ScoringWindowKind.END_OF_ROUND)
        if battle_round_ended and self._game_ends_after_completed_round(completed_round):
            self._resolve_unarrived_reserve_destruction_boundary(end_of_battle=True)
            self._record_scoring_windows_boundary(ScoringWindowKind.END_OF_GAME)
            self._score_end_of_battle_primary_boundary(turn_end_record)
            self.expire_persisting_effects_at_boundary(EffectExpirationBoundary.battle_end())
            self.stage = GameLifecycleStage.COMPLETE
            self.battle_phase_index = None
            self.active_player_id = None
            self.command_step_state = None
            self.movement_phase_state = None
            self.shooting_phase_state = None
            self.charge_phase_state = None
            self.fight_phase_state = None
            self.out_of_phase_shooting_state = None
            return completed_phase
        self.battle_phase_index = 0
        self._advance_active_player_after_completed_turn()
        if battle_round_ended:
            self._expire_persisting_effects_at_current_battle_round_start()
        self._expire_persisting_effects_at_current_turn_start()
        self._record_primary_objective_turn_start_boundary_if_available()
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

    def record_faction_rule_state(self, state: FactionRuleState) -> None:
        if type(state) is not FactionRuleState:
            raise GameLifecycleError("GameState faction rule state must be FactionRuleState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("FactionRuleState player_id is not in this game.")
        if any(stored.state_id == state.state_id for stored in self.faction_rule_states):
            raise GameLifecycleError("FactionRuleState already exists for state_id.")
        self.faction_rule_states.append(state)
        self.faction_rule_states = _validate_faction_rule_states(
            self.faction_rule_states,
            player_ids=self.player_ids,
        )

    def faction_rule_states_for_player(
        self,
        *,
        player_id: str,
        state_kind: str | None = None,
    ) -> tuple[FactionRuleState, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_kind = None
        if state_kind is not None:
            requested_kind = _validate_identifier("FactionRuleState state_kind", state_kind)
        return tuple(
            state
            for state in self.faction_rule_states
            if state.player_id == requested_player_id
            and (requested_kind is None or state.state_kind == requested_kind)
        )

    def add_unit_to_army(
        self,
        *,
        player_id: str,
        unit: UnitInstance,
        source_id: str,
    ) -> StartingStrengthRecord:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("GameState added unit must be a UnitInstance.")
        record_source_id = _validate_identifier("source_id", source_id)
        existing_unit_ids = {
            existing.unit_instance_id for army in self.army_definitions for existing in army.units
        }
        existing_record_ids = {record.unit_instance_id for record in self.starting_strength_records}
        if (
            unit.unit_instance_id in existing_unit_ids
            or unit.unit_instance_id in existing_record_ids
        ):
            raise GameLifecycleError("Added unit already exists in this game.")

        updated_armies: list[ArmyDefinition] = []
        added = False
        for army_definition in self.army_definitions:
            if army_definition.player_id != requested_player_id:
                updated_armies.append(army_definition)
                continue
            updated_armies.append(
                replace(
                    army_definition,
                    units=tuple(
                        sorted(
                            (*army_definition.units, unit),
                            key=lambda stored: stored.unit_instance_id,
                        )
                    ),
                )
            )
            added = True
        if not added:
            raise GameLifecycleError("Cannot add a unit before the player's army is mustered.")

        record = StartingStrengthRecord.from_unit(
            player_id=requested_player_id,
            unit=unit,
            source_id=record_source_id,
        )
        self.army_definitions = sorted(updated_armies, key=lambda stored: stored.player_id)
        self.starting_strength_records.append(record)
        self.starting_strength_records.sort(key=lambda stored: stored.unit_instance_id)
        return record

    def apply_strategic_reserve_declarations(
        self,
        *,
        declarations: tuple[StrategicReserveDeclaration, ...],
        destruction_deadline_policy: ReserveDestructionTimingPolicy,
    ) -> tuple[ReserveState, ...]:
        if type(declarations) is not tuple:
            raise GameLifecycleError("strategic reserve declarations must be a tuple.")
        if not declarations:
            return ()
        if type(destruction_deadline_policy) is not ReserveDestructionTimingPolicy:
            raise GameLifecycleError(
                "strategic reserve destruction_deadline_policy must be "
                "ReserveDestructionTimingPolicy."
            )
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        existing_reserved_ids = {
            state.unit_instance_id
            for state in self.reserve_states
            if state.status is ReserveStatus.IN_RESERVES
        }
        declared_unit_ids: set[str] = set()
        declared_embarked_ids: set[str] = set()
        points_by_player: dict[str, int] = {}
        cap_by_player: dict[str, int] = {}
        reserve_states: list[ReserveState] = []
        for declaration in declarations:
            if type(declaration) is not StrategicReserveDeclaration:
                raise GameLifecycleError(
                    "strategic reserve declarations must contain "
                    "StrategicReserveDeclaration values."
                )
            requested_player_id = _validate_player_id(
                declaration.player_id,
                player_ids=self.player_ids,
            )
            owner = unit_owner_by_id.get(declaration.unit_instance_id)
            if owner is None:
                raise GameLifecycleError("Strategic Reserve declaration unit is unknown.")
            if owner != requested_player_id:
                raise GameLifecycleError("Strategic Reserve declaration player_id drift.")
            if declaration.unit_instance_id in existing_reserved_ids:
                raise GameLifecycleError("Strategic Reserve declaration unit is already reserved.")
            if declaration.unit_instance_id in declared_unit_ids:
                raise GameLifecycleError("Strategic Reserve declarations must not duplicate units.")
            declared_unit_ids.add(declaration.unit_instance_id)
            for embarked_unit_id in declaration.embarked_unit_instance_ids:
                embarked_owner = unit_owner_by_id.get(embarked_unit_id)
                if embarked_owner is None:
                    raise GameLifecycleError(
                        "Strategic Reserve declaration embarked unit is unknown."
                    )
                if embarked_owner != requested_player_id:
                    raise GameLifecycleError(
                        "Strategic Reserve declaration embarked unit player_id drift."
                    )
                if embarked_unit_id in declared_embarked_ids:
                    raise GameLifecycleError(
                        "Strategic Reserve declarations must not duplicate embarked units."
                    )
                declared_embarked_ids.add(embarked_unit_id)
            previous_cap = cap_by_player.get(requested_player_id)
            if previous_cap is not None and previous_cap != declaration.points_limit:
                raise GameLifecycleError(
                    "Strategic Reserve declarations must use one points limit per player."
                )
            cap_by_player[requested_player_id] = declaration.points_limit
            points_by_player.setdefault(
                requested_player_id,
                sum(
                    state.points_contribution
                    for state in self.reserve_states
                    if state.player_id == requested_player_id
                    and state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
                    and state.status is ReserveStatus.IN_RESERVES
                ),
            )
            points_by_player[requested_player_id] += (
                declaration.unit_points + declaration.embarked_unit_points
            )
            reserve_states.append(
                declaration.to_reserve_state(
                    destruction_deadline_policy=destruction_deadline_policy
                )
            )
        overlap = declared_unit_ids & declared_embarked_ids
        if overlap:
            raise GameLifecycleError(
                "Strategic Reserve declarations must not also declare embarked units separately."
            )
        for player_id, points in points_by_player.items():
            if points > cap_by_player[player_id]:
                raise GameLifecycleError(
                    "Strategic Reserve declarations exceed the player's points limit."
                )
        self.reserve_states.extend(reserve_states)
        self.reserve_states.sort(key=lambda state: state.unit_instance_id)
        return tuple(sorted(reserve_states, key=lambda state: state.unit_instance_id))

    def declare_battle_formation_embarkation(
        self,
        *,
        player_id: str,
        transport_unit_instance_id: str,
        embarked_unit_instance_ids: tuple[str, ...],
        capacity_profile: TransportCapacityProfile,
    ) -> TransportCargoState:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        embarked_ids = _validate_identifier_tuple(
            "embarked_unit_instance_ids",
            embarked_unit_instance_ids,
            min_length=1,
            sort_values=True,
        )
        if type(capacity_profile) is not TransportCapacityProfile:
            raise GameLifecycleError(
                "battle formation embarkation capacity_profile must be TransportCapacityProfile."
            )
        if self.battlefield_state is not None and (
            self.battlefield_state.placed_armies or self.battlefield_state.removed_model_ids
        ):
            raise GameLifecycleError(
                "Battle formation embarkation must be declared before deployment."
            )
        if self.transport_cargo_state_for_transport(requested_transport_id) is not None:
            raise GameLifecycleError("Battle formation embarkation Transport already has cargo.")
        if (
            self.dedicated_transport_setup_consequence_for_transport(requested_transport_id)
            is not None
        ):
            raise GameLifecycleError(
                "Battle formation embarkation Transport already has a setup consequence."
            )
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        transport_owner = unit_owner_by_id.get(requested_transport_id)
        if transport_owner is None:
            raise GameLifecycleError("Battle formation embarkation Transport is unknown.")
        if transport_owner != requested_player_id:
            raise GameLifecycleError("Battle formation embarkation Transport player_id drift.")
        transport = self._unit_by_id(requested_transport_id)
        if not _unit_has_keyword(transport, "TRANSPORT"):
            raise GameLifecycleError("Battle formation embarkation requires a TRANSPORT unit.")
        if capacity_profile.transport_datasheet_id != transport.datasheet_id:
            raise GameLifecycleError(
                "Battle formation embarkation capacity profile datasheet drift."
            )
        embarked_units: list[UnitInstance] = []
        for unit_id in embarked_ids:
            if unit_id == requested_transport_id:
                raise GameLifecycleError("Battle formation embarkation cannot embark itself.")
            owner = unit_owner_by_id.get(unit_id)
            if owner is None:
                raise GameLifecycleError("Battle formation embarkation unit is unknown.")
            if owner != requested_player_id:
                raise GameLifecycleError("Battle formation embarkation unit player_id drift.")
            if any(
                unit_id in cargo.embarked_unit_instance_ids for cargo in self.transport_cargo_states
            ):
                raise GameLifecycleError("Battle formation embarkation unit is already embarked.")
            embarked_units.append(self._unit_by_id(unit_id))
        disallowed = tuple(
            unit.unit_instance_id
            for unit in embarked_units
            if not capacity_profile.allows_unit(unit)
        )
        if disallowed:
            raise GameLifecycleError(
                "Battle formation embarkation unit is not eligible for this Transport."
            )
        embarked_model_count = sum(len(unit.own_models) for unit in embarked_units)
        if embarked_model_count > capacity_profile.max_model_count:
            raise GameLifecycleError("Battle formation embarkation exceeds Transport capacity.")
        cargo_state = TransportCargoState(
            player_id=requested_player_id,
            transport_unit_instance_id=requested_transport_id,
            capacity_profile=capacity_profile,
            embarked_unit_instance_ids=embarked_ids,
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=embarked_ids,
            disembarked_this_phase_unit_instance_ids=(),
        )
        self.transport_cargo_states.append(cargo_state)
        self.transport_cargo_states.sort(key=lambda state: state.transport_unit_instance_id)
        return cargo_state

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
        if use_record.active_player_id != self.active_player_id:
            raise GameLifecycleError("StratagemUseRecord active_player_id drift.")
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
        if action_state.unit_instance_id in self.battle_shocked_unit_ids:
            raise GameLifecycleError("Battle-shocked units cannot complete actions.")
        if action_state.victory_points == 0:
            if action_state.scoring_source_id == "cleanse":
                self._validate_cleanse_action_completion(action_state, completion_phase)
            completed_without_award = action_state.complete_without_award(
                battle_round=self.battle_round,
                phase=completion_phase.value,
                completion_timing=action_state.completion_timing,
                battle_shocked_unit_ids=tuple(self.battle_shocked_unit_ids),
            )
            self.replace_mission_action_state(completed_without_award)
            if completed_without_award.scoring_source_id == "cleanse":
                self.record_secondary_objective_cleanse(
                    player_id=completed_without_award.player_id,
                    objective_marker_id=completed_without_award.target_id,
                    action_id=completed_without_award.action_id,
                    phase=completion_phase,
                    source_id=completed_without_award.scoring_source_id,
                )
            return completed_without_award
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
            battle_shocked_unit_ids=tuple(self.battle_shocked_unit_ids),
        )
        self.replace_mission_action_state(completed)
        return completed

    def interrupt_mission_action(self, *, action_id: str, reason: str) -> MissionActionState:
        action_state = self.mission_action_state_by_id(action_id)
        interrupted = action_state.interrupt(reason=reason)
        self.replace_mission_action_state(interrupted)
        return interrupted

    def _validate_cleanse_action_completion(
        self,
        action_state: MissionActionState,
        completion_phase: BattlePhase,
    ) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Cleanse completion requires MissionSetup.")
        if type(action_state) is not MissionActionState:
            raise GameLifecycleError("Cleanse completion requires MissionActionState.")
        if type(completion_phase) is not BattlePhase:
            raise GameLifecycleError("Cleanse completion requires BattlePhase.")
        record = resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                self,
                timing=ObjectiveControlTiming.TURN_END,
                phase=completion_phase,
                ruleset_descriptor=self._ruleset_descriptor_for_runtime_policy(),
            )
        )
        for result in record.results:
            if result.objective_id != action_state.target_id:
                continue
            if result.controlled_by_player_id != action_state.player_id:
                raise GameLifecycleError("Cleanse completion requires controlling the objective.")
            return
        raise GameLifecycleError("Cleanse completion objective is unknown.")

    def record_primary_objective_turn_start_state(
        self,
        state: PrimaryObjectiveTurnStartState,
    ) -> None:
        if type(state) is not PrimaryObjectiveTurnStartState:
            raise GameLifecycleError(
                "primary_objective_turn_start_state must be a PrimaryObjectiveTurnStartState."
            )
        if state.game_id != self.game_id:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState game_id drift.")
        if state.player_id not in self.player_ids or state.active_player_id not in self.player_ids:
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState player_id is not in this game."
            )
        if any(
            stored.state_id == state.state_id for stored in self.primary_objective_turn_start_states
        ):
            raise GameLifecycleError("PrimaryObjectiveTurnStartState already exists.")
        if any(
            stored.player_id == state.player_id and stored.battle_round == state.battle_round
            for stored in self.primary_objective_turn_start_states
        ):
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState already exists for this player turn."
            )
        self.primary_objective_turn_start_states.append(state)
        self.primary_objective_turn_start_states.sort(key=lambda stored: stored.state_id)

    def record_primary_terrain_trap(
        self,
        *,
        player_id: str,
        terrain_feature_id: str,
        action_id: str,
        phase: BattlePhase,
        source_id: str,
    ) -> PrimaryTerrainTrapState:
        if self.mission_setup is None:
            raise GameLifecycleError("Primary terrain trap tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError("Primary terrain trap tracking requires an active player.")
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Primary terrain trap tracking requires a BattlePhase.")
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player_id != self.active_player_id:
            raise GameLifecycleError("Primary terrain trap must be recorded during owner's turn.")
        requested_feature_id = _validate_identifier("terrain_feature_id", terrain_feature_id)
        if requested_feature_id not in {
            feature.feature_id for feature in self.mission_setup.terrain_features
        }:
            raise GameLifecycleError("Primary terrain trap references an unknown terrain feature.")
        if any(
            state.player_id == requested_player_id
            and state.terrain_feature_id == requested_feature_id
            for state in self.primary_terrain_trap_states
        ):
            raise GameLifecycleError("Primary terrain trap already exists for this player.")
        state = PrimaryTerrainTrapState(
            trap_id=(
                f"primary-terrain-trap:{self.game_id}:round-{self.battle_round:02d}:"
                f"{requested_player_id}:{requested_feature_id}"
            ),
            game_id=self.game_id,
            player_id=requested_player_id,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            terrain_feature_id=requested_feature_id,
            is_objective=self._terrain_feature_contains_objective_marker(requested_feature_id),
            action_id=_validate_identifier("action_id", action_id),
            source_id=_validate_identifier("source_id", source_id),
        )
        self.primary_terrain_trap_states.append(state)
        self.primary_terrain_trap_states.sort(key=lambda stored: stored.trap_id)
        return state

    def record_primary_unit_destruction(
        self,
        *,
        destroying_player_id: str,
        destroyed_unit_instance_id: str,
        started_turn_terrain_feature_ids: tuple[str, ...],
        source_id: str,
    ) -> PrimaryUnitDestructionState:
        if self.mission_setup is None:
            raise GameLifecycleError("Primary unit destruction tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError("Primary unit destruction tracking requires an active player.")
        phase = self.current_battle_phase
        if phase is None:
            raise GameLifecycleError("Primary unit destruction tracking requires a battle phase.")
        requested_destroyer = _validate_player_id(destroying_player_id, player_ids=self.player_ids)
        requested_unit = _validate_identifier(
            "destroyed_unit_instance_id", destroyed_unit_instance_id
        )
        owner_by_unit_id = _unit_owner_by_id(self.army_definitions)
        if requested_unit not in owner_by_unit_id:
            raise GameLifecycleError("Primary unit destruction references an unknown unit.")
        destroyed_player_id = owner_by_unit_id[requested_unit]
        if destroyed_player_id == requested_destroyer:
            raise GameLifecycleError("Primary unit destruction must target an enemy unit.")
        terrain_ids = _validate_identifier_tuple(
            "started_turn_terrain_feature_ids",
            started_turn_terrain_feature_ids,
            min_length=0,
            sort_values=True,
        )
        known_terrain_ids = {feature.feature_id for feature in self.mission_setup.terrain_features}
        if any(terrain_id not in known_terrain_ids for terrain_id in terrain_ids):
            raise GameLifecycleError(
                "Primary unit destruction references an unknown started-turn terrain feature."
            )
        if any(
            state.destroyed_unit_instance_id == requested_unit
            for state in self.primary_unit_destruction_states
        ):
            raise GameLifecycleError("Primary unit destruction already exists for this unit.")
        state = PrimaryUnitDestructionState(
            destruction_id=(
                f"primary-unit-destruction:{self.game_id}:round-{self.battle_round:02d}:"
                f"{self.active_player_id}:{requested_unit}"
            ),
            game_id=self.game_id,
            destroying_player_id=requested_destroyer,
            destroyed_player_id=destroyed_player_id,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            destroyed_unit_instance_id=requested_unit,
            started_turn_terrain_feature_ids=terrain_ids,
            source_id=_validate_identifier("source_id", source_id),
        )
        self.primary_unit_destruction_states.append(state)
        self.primary_unit_destruction_states.sort(key=lambda stored: stored.destruction_id)
        return state

    def record_secondary_unit_destruction(
        self,
        *,
        destroying_player_id: str,
        destroyed_unit_instance_id: str,
        destroyed_model_instance_ids: tuple[str, ...],
        started_turn_objective_marker_ids: tuple[str, ...],
        source_id: str,
    ) -> SecondaryUnitDestructionState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary unit destruction tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError(
                "Secondary unit destruction tracking requires an active player."
            )
        phase = self.current_battle_phase
        if phase is None:
            raise GameLifecycleError("Secondary unit destruction tracking requires a battle phase.")
        requested_destroyer = _validate_player_id(destroying_player_id, player_ids=self.player_ids)
        requested_unit = _validate_identifier(
            "destroyed_unit_instance_id", destroyed_unit_instance_id
        )
        owner_by_unit_id = _unit_owner_by_id(self.army_definitions)
        if requested_unit not in owner_by_unit_id:
            raise GameLifecycleError("Secondary unit destruction references an unknown unit.")
        destroyed_player_id = owner_by_unit_id[requested_unit]
        if destroyed_player_id == requested_destroyer:
            raise GameLifecycleError("Secondary unit destruction must target an enemy unit.")
        destroyed_unit = self._unit_by_id(requested_unit)
        requested_model_ids = _validate_identifier_tuple(
            "destroyed_model_instance_ids",
            destroyed_model_instance_ids,
            min_length=0,
            sort_values=True,
        )
        model_by_id = {model.model_instance_id: model for model in destroyed_unit.own_models}
        if any(model_id not in model_by_id for model_id in requested_model_ids):
            raise GameLifecycleError(
                "Secondary unit destruction references a model outside the destroyed unit."
            )
        objective_ids = _validate_identifier_tuple(
            "started_turn_objective_marker_ids",
            started_turn_objective_marker_ids,
            min_length=0,
            sort_values=True,
        )
        known_objective_ids = {
            marker.objective_marker_id for marker in self.mission_setup.objective_markers
        }
        if any(objective_id not in known_objective_ids for objective_id in objective_ids):
            raise GameLifecycleError(
                "Secondary unit destruction references an unknown started-turn objective."
            )
        if any(
            state.destroyed_unit_instance_id == requested_unit
            for state in self.secondary_unit_destruction_states
        ):
            raise GameLifecycleError("Secondary unit destruction already exists for this unit.")
        state = SecondaryUnitDestructionState(
            destruction_id=(
                f"secondary-unit-destruction:{self.game_id}:round-{self.battle_round:02d}:"
                f"{self.active_player_id}:{requested_unit}"
            ),
            game_id=self.game_id,
            destroying_player_id=requested_destroyer,
            destroyed_player_id=destroyed_player_id,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            destroyed_unit_instance_id=requested_unit,
            destroyed_models=tuple(
                SecondaryDestroyedModelState(
                    model_instance_id=model_id,
                    starting_wounds=model_by_id[model_id].starting_wounds,
                )
                for model_id in requested_model_ids
            ),
            started_turn_objective_marker_ids=objective_ids,
            source_id=_validate_identifier("source_id", source_id),
        )
        self.secondary_unit_destruction_states.append(state)
        self.secondary_unit_destruction_states.sort(key=lambda stored: stored.destruction_id)
        return state

    def record_secondary_objective_cleanse(
        self,
        *,
        player_id: str,
        objective_marker_id: str,
        action_id: str,
        phase: BattlePhase,
        source_id: str,
    ) -> SecondaryObjectiveCleanseState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary objective cleanse tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError(
                "Secondary objective cleanse tracking requires an active player."
            )
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Secondary objective cleanse tracking requires a phase.")
        requested_player = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player != self.active_player_id:
            raise GameLifecycleError("Secondary objective cleanse must happen on owner's turn.")
        requested_objective = _validate_identifier("objective_marker_id", objective_marker_id)
        known_objective_ids = {
            marker.objective_marker_id for marker in self.mission_setup.objective_markers
        }
        if requested_objective not in known_objective_ids:
            raise GameLifecycleError("Secondary objective cleanse references an unknown objective.")
        requested_action = _validate_identifier("action_id", action_id)
        if any(
            state.player_id == requested_player
            and state.battle_round == self.battle_round
            and state.active_player_id == self.active_player_id
            and state.objective_marker_id == requested_objective
            for state in self.secondary_objective_cleanse_states
        ):
            raise GameLifecycleError(
                "Secondary objective cleanse already exists for this objective turn."
            )
        state = SecondaryObjectiveCleanseState(
            cleanse_id=(
                f"secondary-objective-cleanse:{self.game_id}:round-{self.battle_round:02d}:"
                f"{requested_player}:{requested_objective}"
            ),
            game_id=self.game_id,
            player_id=requested_player,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            objective_marker_id=requested_objective,
            action_id=requested_action,
            source_id=_validate_identifier("source_id", source_id),
        )
        self.secondary_objective_cleanse_states.append(state)
        self.secondary_objective_cleanse_states.sort(key=lambda stored: stored.cleanse_id)
        return state

    def record_secondary_terrain_plunder(
        self,
        *,
        player_id: str,
        terrain_feature_id: str,
        action_id: str,
        phase: BattlePhase,
        source_id: str,
    ) -> SecondaryTerrainPlunderState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary terrain plunder tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError(
                "Secondary terrain plunder tracking requires an active player."
            )
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Secondary terrain plunder tracking requires a phase.")
        requested_player = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player != self.active_player_id:
            raise GameLifecycleError("Secondary terrain plunder must happen on owner's turn.")
        requested_feature = _validate_identifier("terrain_feature_id", terrain_feature_id)
        if requested_feature not in {
            feature.feature_id for feature in self.mission_setup.terrain_features
        }:
            raise GameLifecycleError(
                "Secondary terrain plunder references an unknown terrain area."
            )
        if any(
            state.player_id == requested_player
            and state.battle_round == self.battle_round
            and state.active_player_id == self.active_player_id
            for state in self.secondary_terrain_plunder_states
        ):
            raise GameLifecycleError(
                "Secondary terrain plunder already exists for this player turn."
            )
        state = SecondaryTerrainPlunderState(
            plunder_id=(
                f"secondary-terrain-plunder:{self.game_id}:round-{self.battle_round:02d}:"
                f"{requested_player}:{requested_feature}"
            ),
            game_id=self.game_id,
            player_id=requested_player,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            terrain_feature_id=requested_feature,
            action_id=_validate_identifier("action_id", action_id),
            source_id=_validate_identifier("source_id", source_id),
        )
        self.secondary_terrain_plunder_states.append(state)
        self.secondary_terrain_plunder_states.sort(key=lambda stored: stored.plunder_id)
        return state

    def runtime_ruleset_descriptor(self) -> RulesetDescriptor:
        return self._ruleset_descriptor_for_runtime_policy()

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

    def remove_persisting_effects_by_id(
        self,
        effect_ids: tuple[str, ...],
    ) -> tuple[PersistingEffect, ...]:
        requested_effect_ids = _validate_identifier_tuple(
            "effect_ids",
            effect_ids,
            min_length=0,
            sort_values=True,
        )
        if not requested_effect_ids:
            return ()
        by_id = {effect.effect_id: effect for effect in self.persisting_effects}
        missing_ids = tuple(
            effect_id for effect_id in requested_effect_ids if effect_id not in by_id
        )
        if missing_ids:
            raise GameLifecycleError("Cannot remove unknown PersistingEffect IDs.")
        removed = tuple(by_id[effect_id] for effect_id in requested_effect_ids)
        removed_ids = {effect.effect_id for effect in removed}
        self.persisting_effects = [
            effect for effect in self.persisting_effects if effect.effect_id not in removed_ids
        ]
        return tuple(sorted(removed, key=lambda effect: effect.effect_id))

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
        self._remove_attached_unit_formation(attached_unit_instance_id=requested_attached_unit_id)
        replaced_ids = {*surviving_ids, requested_attached_unit_id}
        self.starting_strength_records = [
            record
            for record in self.starting_strength_records
            if record.unit_instance_id not in replaced_ids
        ]
        self.starting_strength_records.extend(recovered_records)
        self.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
        return tuple(sorted(recovered_records, key=lambda record: record.unit_instance_id))

    def _remove_attached_unit_formation(self, *, attached_unit_instance_id: str) -> None:
        requested_attached_unit_id = _validate_identifier(
            "attached_unit_instance_id",
            attached_unit_instance_id,
        )
        updated_armies: list[ArmyDefinition] = []
        for army_definition in self.army_definitions:
            remaining_attached_units = tuple(
                attached_unit
                for attached_unit in army_definition.attached_units
                if attached_unit.attached_unit_instance_id != requested_attached_unit_id
            )
            if remaining_attached_units == army_definition.attached_units:
                updated_armies.append(army_definition)
                continue
            updated_armies.append(replace(army_definition, attached_units=remaining_attached_units))
        self.army_definitions = sorted(updated_armies, key=lambda stored: stored.player_id)

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

    def record_prebattle_action(self, record: PreBattleActionRecord) -> None:
        if type(record) is not PreBattleActionRecord:
            raise GameLifecycleError("prebattle action record must be a PreBattleActionRecord.")
        if record.game_id != self.game_id:
            raise GameLifecycleError("PreBattleActionRecord game_id drift.")
        if record.player_id not in self.player_ids:
            raise GameLifecycleError("PreBattleActionRecord player_id is not in this game.")
        if record.setup_step not in self.setup_sequence:
            raise GameLifecycleError("PreBattleActionRecord setup_step is not in this game.")
        if any(stored.action_id == record.action_id for stored in self.prebattle_action_records):
            raise GameLifecycleError("PreBattleActionRecord action_id already exists.")
        self.prebattle_action_records.append(record)
        self.prebattle_action_records.sort(key=lambda stored: stored.action_id)

    def prebattle_action_records_for_step(
        self,
        *,
        player_id: str,
        setup_step: SetupStep,
    ) -> tuple[PreBattleActionRecord, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if type(setup_step) is not SetupStep:
            raise GameLifecycleError("setup_step must be a SetupStep.")
        return tuple(
            record
            for record in self.prebattle_action_records
            if record.player_id == requested_player_id and record.setup_step is setup_step
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
        if requested_mode is SecondaryMissionCardMode.FIXED:
            return card_state
        scored = card_state.score(transaction_id=transaction.transaction_id)
        self._replace_secondary_mission_card_state(scored)
        return scored

    def score_secondary_mission_from_state(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        mode: SecondaryMissionCardMode,
        phase: BattlePhase,
    ) -> SecondaryMissionCardState:
        if self.mission_setup is None:
            raise GameLifecycleError("State-backed secondary scoring requires MissionSetup.")
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("State-backed secondary scoring phase must be a BattlePhase.")
        requested_mode = secondary_mission_card_mode_from_token(mode)
        card_state = self.secondary_mission_card_state(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=requested_mode,
        )
        if card_state is None:
            raise GameLifecycleError("Secondary mission card is not active.")
        record = resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                self,
                timing=ObjectiveControlTiming.TURN_END,
                phase=phase,
                ruleset_descriptor=self._ruleset_descriptor_for_runtime_policy(),
            )
        )
        self._record_objective_control_record_if_absent(record)
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        source_kind = (
            VictoryPointSourceKind.FIXED_SECONDARY
            if requested_mode is SecondaryMissionCardMode.FIXED
            else VictoryPointSourceKind.TACTICAL_SECONDARY
        )
        award = policy.secondary_award_from_mission_state(
            player_id=card_state.player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            secondary_mission_id=card_state.secondary_mission_id,
            source_kind=source_kind,
            hidden=False,
            record=record,
            mission_setup=self.mission_setup,
            unit_destruction_states=tuple(self.secondary_unit_destruction_states),
            objective_cleanse_states=tuple(self.secondary_objective_cleanse_states),
            terrain_plunder_states=tuple(self.secondary_terrain_plunder_states),
            enemy_unit_ids_in_player_deployment_zone=(
                self._enemy_unit_ids_in_player_deployment_zone(card_state.player_id)
            ),
            starting_strength_records=tuple(self.starting_strength_records),
        )
        if award is None:
            raise GameLifecycleError("State-backed secondary mission requirements are not met.")
        transaction = self.award_victory_points(award)
        if requested_mode is SecondaryMissionCardMode.FIXED:
            return card_state
        scored = card_state.score(transaction_id=transaction.transaction_id)
        self._replace_secondary_mission_card_state(scored)
        return scored

    def record_tactical_secondary_achievement_context(
        self,
        context: TacticalSecondaryAchievementContext,
    ) -> None:
        if type(context) is not TacticalSecondaryAchievementContext:
            raise GameLifecycleError("context must be a TacticalSecondaryAchievementContext.")
        self._validate_current_tactical_secondary_achievement_context(context)
        if any(
            stored.achievement_id == context.achievement_id
            for stored in self.tactical_secondary_achievement_contexts
        ):
            raise GameLifecycleError("Tactical secondary achievement context already exists.")
        if any(
            stored.player_id == context.player_id
            and stored.secondary_mission_id == context.secondary_mission_id
            and stored.card_battle_round == context.card_battle_round
            for stored in self.tactical_secondary_achievement_contexts
        ):
            raise GameLifecycleError(
                "Tactical secondary achievement context already exists for this card."
            )
        self.tactical_secondary_achievement_contexts.append(context)
        self.tactical_secondary_achievement_contexts.sort(
            key=lambda stored: (
                stored.player_id,
                stored.card_battle_round,
                stored.secondary_mission_id,
            )
        )

    def tactical_secondary_achievement_context(
        self,
        achievement_id: str,
    ) -> TacticalSecondaryAchievementContext | None:
        requested_achievement_id = _validate_identifier("achievement_id", achievement_id)
        matches = [
            context
            for context in self.tactical_secondary_achievement_contexts
            if context.achievement_id == requested_achievement_id
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise GameLifecycleError("Multiple Tactical secondary achievement contexts found.")
        return matches[0]

    def consume_tactical_secondary_achievement_context(
        self,
        achievement_id: str,
    ) -> TacticalSecondaryAchievementContext:
        requested_achievement_id = _validate_identifier("achievement_id", achievement_id)
        for index, context in enumerate(self.tactical_secondary_achievement_contexts):
            if context.achievement_id == requested_achievement_id:
                return self.tactical_secondary_achievement_contexts.pop(index)
        raise GameLifecycleError("Tactical secondary achievement context does not exist.")

    def _validate_current_tactical_secondary_achievement_context(
        self,
        context: TacticalSecondaryAchievementContext,
    ) -> None:
        if context.game_id != self.game_id:
            raise GameLifecycleError("Tactical secondary achievement context game_id drift.")
        if context.player_id not in self.player_ids:
            raise GameLifecycleError(
                "Tactical secondary achievement context player_id is not in this game."
            )
        if context.active_player_id != self.active_player_id:
            raise GameLifecycleError(
                "Tactical secondary achievement context active_player_id drift."
            )
        if context.battle_round != self.battle_round:
            raise GameLifecycleError("Tactical secondary achievement context battle_round drift.")
        current_phase = self.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("Tactical secondary achievement context requires a phase.")
        if context.phase != current_phase.value:
            raise GameLifecycleError("Tactical secondary achievement context phase drift.")
        card_state = self.secondary_mission_card_state(
            player_id=context.player_id,
            secondary_mission_id=context.secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        if card_state is None:
            raise GameLifecycleError(
                "Tactical secondary achievement context requires an active card."
            )
        if context.card_battle_round != card_state.battle_round:
            raise GameLifecycleError(
                "Tactical secondary achievement context card battle_round drift."
            )
        if self.mission_setup is None:
            raise GameLifecycleError(
                "Tactical secondary achievement context requires MissionSetup."
            )
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        award = policy.secondary_award(
            player_id=context.player_id,
            battle_round=self.battle_round,
            phase=current_phase.value,
            secondary_mission_id=context.secondary_mission_id,
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
        )
        metadata = cast(dict[str, JsonValue], award.metadata)
        if context.victory_points != award.amount:
            raise GameLifecycleError("Tactical secondary achievement context VP drift.")
        if context.scoring_rule_id != metadata["scoring_rule_id"]:
            raise GameLifecycleError("Tactical secondary achievement context rule ID drift.")
        if context.scoring_rule_condition != metadata["scoring_rule_condition"]:
            raise GameLifecycleError("Tactical secondary achievement context condition drift.")
        if context.scoring_rule_source_id != metadata["scoring_rule_source_id"]:
            raise GameLifecycleError("Tactical secondary achievement context source ID drift.")
        if context.scoring_timing != award.scoring_timing:
            raise GameLifecycleError("Tactical secondary achievement context timing drift.")

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

    def has_tactical_secondary_discard_cp_reward_window(self, window_id: str) -> bool:
        requested_window_id = _validate_identifier("window_id", window_id)
        return requested_window_id in self.tactical_secondary_discard_cp_reward_window_ids

    def record_tactical_secondary_discard_cp_reward_window(self, window_id: str) -> None:
        requested_window_id = _validate_identifier("window_id", window_id)
        if requested_window_id in self.tactical_secondary_discard_cp_reward_window_ids:
            raise GameLifecycleError("Tactical secondary discard CP reward window already used.")
        self.tactical_secondary_discard_cp_reward_window_ids.append(requested_window_id)
        self.tactical_secondary_discard_cp_reward_window_ids.sort()

    def has_tactical_secondary_replacement_use(self, player_id: str) -> bool:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return requested_player_id in self.tactical_secondary_replacement_player_ids

    def record_tactical_secondary_replacement_use(self, player_id: str) -> None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player_id in self.tactical_secondary_replacement_player_ids:
            raise GameLifecycleError("Tactical secondary replacement was already used.")
        self.tactical_secondary_replacement_player_ids.append(requested_player_id)
        self.tactical_secondary_replacement_player_ids.sort()

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

    def record_sticky_objective_control_state(
        self,
        state: StickyObjectiveControlState,
    ) -> None:
        if type(state) is not StickyObjectiveControlState:
            raise GameLifecycleError(
                "GameState sticky_objective_control_state must be a sticky state."
            )
        if state.game_id != self.game_id:
            raise GameLifecycleError("StickyObjectiveControlState game_id drift.")
        if state.player_id not in self.player_ids or state.active_player_id not in self.player_ids:
            raise GameLifecycleError("StickyObjectiveControlState player_id is not in this game.")
        if any(
            stored.state_id == state.state_id for stored in self.sticky_objective_control_states
        ):
            raise GameLifecycleError("StickyObjectiveControlState already exists.")
        active_for_objective = tuple(
            stored
            for stored in self.sticky_objective_control_states
            if stored.objective_id == state.objective_id
        )
        if any(stored.player_id != state.player_id for stored in active_for_objective):
            raise GameLifecycleError("Sticky objective control cannot be held by multiple players.")
        self.sticky_objective_control_states.append(state)
        self.sticky_objective_control_states.sort(key=lambda stored: stored.state_id)

    def _record_objective_control_record_if_absent(
        self,
        record: ObjectiveControlRecord,
    ) -> None:
        if any(stored.record_id == record.record_id for stored in self.objective_control_records):
            return
        self.record_objective_control_record(record)

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

    def reposition_unit_to_strategic_reserves(
        self,
        *,
        player_id: str,
        unit_instance_id: str,
        reserve_origin: ReserveOrigin = ReserveOrigin.DURING_BATTLE_OTHER,
        destruction_deadline_policy: ReserveDestructionTimingPolicy | None = None,
        required_arrival_battle_round: int | None = None,
        required_arrival_phase: BattlePhase | str | None = None,
        required_arrival_source_rule_id: str | None = None,
    ) -> ReserveState:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("Repositioned units can only enter reserves during battle.")
        current_phase = self.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("Repositioned units require a current battle phase.")
        if self.battlefield_state is None:
            raise GameLifecycleError("Repositioned units require battlefield_state.")
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        origin = reserve_origin_from_token(reserve_origin)
        if origin not in {
            ReserveOrigin.DURING_BATTLE_ABILITY,
            ReserveOrigin.DURING_BATTLE_STRATAGEM,
            ReserveOrigin.DURING_BATTLE_OTHER,
        }:
            raise GameLifecycleError("Repositioned units require a during-battle reserve origin.")
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        owner = unit_owner_by_id.get(requested_unit_id)
        if owner is None:
            raise GameLifecycleError("Repositioned unit is unknown.")
        if owner != requested_player_id:
            raise GameLifecycleError("Repositioned unit player_id drift.")
        if self.reserve_state_for_unit(requested_unit_id) is not None:
            raise GameLifecycleError("Repositioned unit already has a ReserveState.")
        try:
            unit_placement = self.battlefield_state.unit_placement_by_id(requested_unit_id)
        except PlacementError as exc:
            raise GameLifecycleError(
                "Repositioned unit must be on the battlefield before entering reserves."
            ) from exc
        if unit_placement.player_id != requested_player_id:
            raise GameLifecycleError("Repositioned unit placement player_id drift.")
        cargo_state = self.transport_cargo_state_for_transport(requested_unit_id)
        policy = destruction_deadline_policy
        if policy is None:
            policy = (
                reserve_destruction_policy_from_scoring_policy(
                    mission_scoring_policy_from_setup(self.mission_setup)
                )
                if self.mission_setup is not None
                else ReserveDestructionTimingPolicy.core_rules_default()
            )
        if type(policy) is not ReserveDestructionTimingPolicy:
            raise GameLifecycleError(
                "Repositioned unit destruction_deadline_policy must be a policy."
            )
        reserve_state = ReserveState.entered_during_battle(
            player_id=requested_player_id,
            unit_instance_id=requested_unit_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            battle_round=self.battle_round,
            phase=current_phase,
            reserve_origin=origin,
            destruction_deadline_policy=policy,
            embarked_unit_instance_ids=(
                () if cargo_state is None else cargo_state.embarked_unit_instance_ids
            ),
            required_arrival_battle_round=required_arrival_battle_round,
            required_arrival_phase=required_arrival_phase,
            required_arrival_source_rule_id=required_arrival_source_rule_id,
        )
        try:
            updated_battlefield = self.battlefield_state.without_unit_placement(requested_unit_id)
        except PlacementError as exc:
            raise GameLifecycleError("Repositioned unit battlefield removal failed.") from exc
        self.record_reserve_state(reserve_state)
        self.battlefield_state = updated_battlefield
        return reserve_state

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
        return tuple(
            sorted(
                (
                    *self.unarrived_reserve_model_ids(),
                    *self.embarked_model_ids(),
                    *self.dedicated_transport_setup_consequence_model_ids(),
                )
            )
        )

    def dedicated_transport_setup_consequence_model_ids(self) -> tuple[str, ...]:
        if not self.dedicated_transport_setup_consequences:
            return ()
        unit_by_id = {
            unit.unit_instance_id: unit for army in self.army_definitions for unit in army.units
        }
        model_ids: list[str] = []
        for consequence in self.dedicated_transport_setup_consequences:
            unit = unit_by_id.get(consequence.transport_unit_instance_id)
            if unit is None:
                raise GameLifecycleError(
                    "DedicatedTransportSetupConsequence references an unknown Transport."
                )
            model_ids.extend(model.model_instance_id for model in unit.own_models)
        return tuple(sorted(model_ids))

    def record_dedicated_transport_setup_consequence(
        self,
        consequence: DedicatedTransportSetupConsequence,
    ) -> None:
        if type(consequence) is not DedicatedTransportSetupConsequence:
            raise GameLifecycleError("consequence must be a DedicatedTransportSetupConsequence.")
        if consequence.player_id not in self.player_ids:
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence player_id is not in this game."
            )
        if (
            self.dedicated_transport_setup_consequence_for_transport(
                consequence.transport_unit_instance_id
            )
            is not None
        ):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence already exists for Transport."
            )
        if self.transport_cargo_state_for_transport(consequence.transport_unit_instance_id):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence Transport already has cargo."
            )
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        owner = unit_owner_by_id.get(consequence.transport_unit_instance_id)
        if owner is None:
            raise GameLifecycleError("DedicatedTransportSetupConsequence Transport is unknown.")
        if owner != consequence.player_id:
            raise GameLifecycleError("DedicatedTransportSetupConsequence player_id drift.")
        transport = self._unit_by_id(consequence.transport_unit_instance_id)
        if not _unit_has_keyword(transport, "DEDICATED TRANSPORT"):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence requires a DEDICATED TRANSPORT unit."
            )
        self.dedicated_transport_setup_consequences.append(consequence)
        self.dedicated_transport_setup_consequences.sort(
            key=lambda record: record.transport_unit_instance_id
        )

    def dedicated_transport_setup_consequence_for_transport(
        self,
        transport_unit_instance_id: str,
    ) -> DedicatedTransportSetupConsequence | None:
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        for consequence in self.dedicated_transport_setup_consequences:
            if consequence.transport_unit_instance_id == requested_transport_id:
                return consequence
        return None

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
        if (
            self.dedicated_transport_setup_consequence_for_transport(
                cargo_state.transport_unit_instance_id
            )
            is not None
        ):
            raise GameLifecycleError("TransportCargoState Transport already has a consequence.")
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

    def remove_transport_cargo_state(self, transport_unit_instance_id: str) -> TransportCargoState:
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        for index, stored in enumerate(self.transport_cargo_states):
            if stored.transport_unit_instance_id == requested_transport_id:
                return self.transport_cargo_states.pop(index)
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
            "faction_rule_states": [state.to_payload() for state in self.faction_rule_states],
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
            "charge_phase_state": (
                None if self.charge_phase_state is None else self.charge_phase_state.to_payload()
            ),
            "fight_phase_state": (
                None if self.fight_phase_state is None else self.fight_phase_state.to_payload()
            ),
            "shooting_phase_state": (
                None
                if self.shooting_phase_state is None
                else self.shooting_phase_state.to_payload()
            ),
            "out_of_phase_shooting_state": (
                None
                if self.out_of_phase_shooting_state is None
                else self.out_of_phase_shooting_state.to_payload()
            ),
            "feel_no_pain_sources_by_model_id": {
                model_id: [source.to_payload() for source in sources]
                for model_id, sources in self.feel_no_pain_sources_by_model_id.items()
            },
            "feel_no_pain_decline_allowed_model_ids": list(
                self.feel_no_pain_decline_allowed_model_ids
            ),
            "destruction_reaction_sources_by_model_id": {
                model_id: [source.to_payload() for source in sources]
                for model_id, sources in self.destruction_reaction_sources_by_model_id.items()
            },
            "reserve_states": [state.to_payload() for state in self.reserve_states],
            "hover_mode_states": [state.to_payload() for state in self.hover_mode_states],
            "transport_cargo_states": [state.to_payload() for state in self.transport_cargo_states],
            "dedicated_transport_setup_consequences": [
                consequence.to_payload()
                for consequence in self.dedicated_transport_setup_consequences
            ],
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
            "sticky_objective_control_states": [
                state.to_payload() for state in self.sticky_objective_control_states
            ],
            "primary_objective_turn_start_states": [
                state.to_payload() for state in self.primary_objective_turn_start_states
            ],
            "primary_terrain_trap_states": [
                state.to_payload() for state in self.primary_terrain_trap_states
            ],
            "primary_unit_destruction_states": [
                state.to_payload() for state in self.primary_unit_destruction_states
            ],
            "secondary_unit_destruction_states": [
                state.to_payload() for state in self.secondary_unit_destruction_states
            ],
            "secondary_objective_cleanse_states": [
                state.to_payload() for state in self.secondary_objective_cleanse_states
            ],
            "secondary_terrain_plunder_states": [
                state.to_payload() for state in self.secondary_terrain_plunder_states
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
            "prebattle_action_records": [
                record.to_payload() for record in self.prebattle_action_records
            ],
            "secondary_mission_card_states": [
                state.to_payload() for state in self.secondary_mission_card_states
            ],
            "tactical_secondary_achievement_contexts": [
                context.to_payload() for context in self.tactical_secondary_achievement_contexts
            ],
            "tactical_secondary_discard_cp_reward_window_ids": list(
                self.tactical_secondary_discard_cp_reward_window_ids
            ),
            "tactical_secondary_replacement_player_ids": list(
                self.tactical_secondary_replacement_player_ids
            ),
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
        payload["prebattle_action_records"] = cast(
            JsonValue,
            [cast(JsonValue, record.to_payload()) for record in self.prebattle_action_records],
        )
        payload["secondary_unit_destruction_states"] = cast(
            JsonValue,
            [
                cast(JsonValue, state.to_payload())
                for state in self.secondary_unit_destruction_states
                if secondary_mission_choices_revealed or state.destroying_player_id == viewer
            ],
        )
        payload["secondary_objective_cleanse_states"] = cast(
            JsonValue,
            [
                cast(JsonValue, state.to_payload())
                for state in self.secondary_objective_cleanse_states
                if secondary_mission_choices_revealed or state.player_id == viewer
            ],
        )
        payload["secondary_terrain_plunder_states"] = cast(
            JsonValue,
            [
                cast(JsonValue, state.to_payload())
                for state in self.secondary_terrain_plunder_states
                if secondary_mission_choices_revealed or state.player_id == viewer
            ],
        )
        payload["tactical_secondary_achievement_contexts"] = []
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
            faction_rule_states=[
                FactionRuleState.from_payload(state) for state in payload["faction_rule_states"]
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
            charge_phase_state=(
                None
                if payload["charge_phase_state"] is None
                else ChargePhaseState.from_payload(payload["charge_phase_state"])
            ),
            fight_phase_state=(
                None
                if payload["fight_phase_state"] is None
                else FightPhaseState.from_payload(payload["fight_phase_state"])
            ),
            shooting_phase_state=(
                None
                if payload["shooting_phase_state"] is None
                else ShootingPhaseState.from_payload(payload["shooting_phase_state"])
            ),
            out_of_phase_shooting_state=(
                None
                if payload["out_of_phase_shooting_state"] is None
                else OutOfPhaseShootingState.from_payload(payload["out_of_phase_shooting_state"])
            ),
            feel_no_pain_sources_by_model_id={
                model_id: tuple(FeelNoPainSource.from_payload(source) for source in sources)
                for model_id, sources in payload["feel_no_pain_sources_by_model_id"].items()
            },
            feel_no_pain_decline_allowed_model_ids=list(
                payload["feel_no_pain_decline_allowed_model_ids"]
            ),
            destruction_reaction_sources_by_model_id={
                model_id: tuple(
                    DestructionReactionSource.from_payload(source) for source in sources
                )
                for model_id, sources in payload["destruction_reaction_sources_by_model_id"].items()
            },
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
            dedicated_transport_setup_consequences=[
                DedicatedTransportSetupConsequence.from_payload(consequence)
                for consequence in payload["dedicated_transport_setup_consequences"]
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
            sticky_objective_control_states=[
                StickyObjectiveControlState.from_payload(state)
                for state in payload["sticky_objective_control_states"]
            ],
            primary_objective_turn_start_states=[
                PrimaryObjectiveTurnStartState.from_payload(state)
                for state in payload["primary_objective_turn_start_states"]
            ],
            primary_terrain_trap_states=[
                PrimaryTerrainTrapState.from_payload(state)
                for state in payload["primary_terrain_trap_states"]
            ],
            primary_unit_destruction_states=[
                PrimaryUnitDestructionState.from_payload(state)
                for state in payload["primary_unit_destruction_states"]
            ],
            secondary_unit_destruction_states=[
                SecondaryUnitDestructionState.from_payload(state)
                for state in payload["secondary_unit_destruction_states"]
            ],
            secondary_objective_cleanse_states=[
                SecondaryObjectiveCleanseState.from_payload(state)
                for state in payload["secondary_objective_cleanse_states"]
            ],
            secondary_terrain_plunder_states=[
                SecondaryTerrainPlunderState.from_payload(state)
                for state in payload["secondary_terrain_plunder_states"]
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
            prebattle_action_records=[
                PreBattleActionRecord.from_payload(record)
                for record in payload["prebattle_action_records"]
            ],
            secondary_mission_card_states=[
                SecondaryMissionCardState.from_payload(state)
                for state in payload["secondary_mission_card_states"]
            ],
            tactical_secondary_achievement_contexts=[
                TacticalSecondaryAchievementContext.from_payload(context)
                for context in payload["tactical_secondary_achievement_contexts"]
            ],
            tactical_secondary_discard_cp_reward_window_ids=list(
                payload["tactical_secondary_discard_cp_reward_window_ids"]
            ),
            tactical_secondary_replacement_player_ids=list(
                payload["tactical_secondary_replacement_player_ids"]
            ),
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
        records = _starting_strength_records_for_army(army_definition)
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
                ruleset_descriptor=self._ruleset_descriptor_for_runtime_policy(),
            )
        )
        retained_record = apply_sticky_objective_control(
            record=record,
            states=tuple(self.sticky_objective_control_states),
        )
        self._expire_sticky_objective_control_states(record)
        self.record_objective_control_record(retained_record)
        return retained_record

    def _expire_sticky_objective_control_states(
        self,
        record: ObjectiveControlRecord,
    ) -> None:
        retained: list[StickyObjectiveControlState] = []
        for state in self.sticky_objective_control_states:
            if sticky_objective_control_state_is_expired(
                state=state,
                record=record,
                player_ids=tuple(self.player_ids),
            ):
                continue
            retained.append(state)
        self.sticky_objective_control_states = sorted(
            retained,
            key=lambda state: state.state_id,
        )

    def _record_primary_objective_turn_start_boundary_if_available(self) -> None:
        if self.mission_setup is None or self.battlefield_state is None:
            return
        if self.active_player_id is None:
            raise GameLifecycleError("Primary turn-start tracking requires an active player.")
        current_phase = self.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("Primary turn-start tracking requires a battle phase.")
        record = resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                self,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=current_phase,
                ruleset_descriptor=self._ruleset_descriptor_for_runtime_policy(),
            )
        )
        controlled_objective_ids = tuple(
            sorted(
                result.objective_id
                for result in record.results
                if result.controlled_by_player_id == self.active_player_id
            )
        )
        state = PrimaryObjectiveTurnStartState(
            state_id=(
                f"primary-turn-start:{self.game_id}:round-{self.battle_round:02d}:"
                f"{self.active_player_id}"
            ),
            game_id=self.game_id,
            player_id=self.active_player_id,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            controlled_objective_ids=controlled_objective_ids,
            source_id=(
                f"{self.game_id}:primary-turn-start:round-{self.battle_round:02d}:"
                f"{self.active_player_id}"
            ),
        )
        self.record_primary_objective_turn_start_state(state)

    def _score_objective_control_boundary(self, record: ObjectiveControlRecord) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Mission scoring requires MissionSetup.")
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        for award in policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=self.mission_setup,
            turn_start_states=tuple(self.primary_objective_turn_start_states),
            terrain_trap_states=tuple(self.primary_terrain_trap_states),
            unit_destruction_states=tuple(self.primary_unit_destruction_states),
        ):
            self.award_victory_points(award)

    def _score_end_of_battle_primary_boundary(self, record: ObjectiveControlRecord) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Mission scoring requires MissionSetup.")
        policy = mission_scoring_policy_from_setup(self.mission_setup)
        for award in policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=self.mission_setup,
            turn_start_states=tuple(self.primary_objective_turn_start_states),
            terrain_trap_states=tuple(self.primary_terrain_trap_states),
            unit_destruction_states=tuple(self.primary_unit_destruction_states),
            scoring_player_ids=self.player_ids,
            end_of_battle=True,
        ):
            self.award_victory_points(award)

    def _terrain_feature_contains_objective_marker(self, terrain_feature_id: str) -> bool:
        if self.mission_setup is None:
            raise GameLifecycleError("Terrain objective lookup requires MissionSetup.")
        requested_feature_id = _validate_identifier("terrain_feature_id", terrain_feature_id)
        for feature in self.mission_setup.terrain_features:
            if feature.feature_id != requested_feature_id:
                continue
            min_x, min_y, max_x, max_y = feature.bounds()
            return any(
                min_x <= marker.x_inches <= max_x and min_y <= marker.y_inches <= max_y
                for marker in self.mission_setup.objective_markers
            )
        raise GameLifecycleError("Terrain objective lookup references an unknown terrain feature.")

    def _enemy_unit_ids_in_player_deployment_zone(self, player_id: str) -> tuple[str, ...]:
        if self.mission_setup is None:
            raise GameLifecycleError("Deployment-zone secondary scoring requires MissionSetup.")
        if self.battlefield_state is None:
            raise GameLifecycleError(
                "Deployment-zone secondary scoring requires battlefield_state."
            )
        requested_player = _validate_player_id(player_id, player_ids=self.player_ids)
        zones = tuple(
            zone
            for zone in self.mission_setup.deployment_zones
            if zone.player_id == requested_player
        )
        if not zones:
            raise GameLifecycleError("Deployment-zone secondary scoring requires player zone.")
        scenario = BattlefieldScenario(
            armies=tuple(self.army_definitions),
            battlefield_state=self.battlefield_state,
        )
        enemy_unit_ids: set[str] = set()
        for placed_army in self.battlefield_state.placed_armies:
            if placed_army.player_id == requested_player:
                continue
            for unit_placement in placed_army.unit_placements:
                for model_placement in unit_placement.model_placements:
                    model = geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(model_placement),
                        placement=model_placement,
                    )
                    if any(
                        shapely_backend.base_footprint_intersects_deployment_zone(
                            model.base,
                            model.pose,
                            zone,
                        )
                        for zone in zones
                    ):
                        enemy_unit_ids.add(unit_placement.unit_instance_id)
                        break
        return tuple(sorted(enemy_unit_ids))

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
            self.mission_setup.mission_pack_id == eleventh_ca_2026_27_source.MISSION_PACK_ID
        ):
            return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27()
        return RulesetDescriptor.warhammer_40000_eleventh()

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


def _validate_strict_roster_legality_requests(
    values: tuple[ArmyMusterRequest, ...],
) -> None:
    non_strict_player_ids = tuple(
        request.player_id for request in values if not request.roster_legality_required
    )
    if non_strict_player_ids:
        raise GameLifecycleError(
            "GameConfig production path requires roster_legality_required for every "
            "ArmyMusterRequest. Legacy smoke fixtures must set "
            "allow_legacy_non_strict_rosters explicitly."
        )


def _validate_reserve_unit_points(
    values: object,
    *,
    army_muster_requests: tuple[ArmyMusterRequest, ...],
) -> tuple[ReserveUnitPointValue, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameConfig reserve_unit_points must be a tuple.")
    known_unit_ids = {
        f"{request.army_id}:{selection.unit_selection_id}"
        for request in army_muster_requests
        for selection in request.unit_selections
    }
    validated: list[ReserveUnitPointValue] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ReserveUnitPointValue:
            raise GameLifecycleError(
                "GameConfig reserve_unit_points must contain ReserveUnitPointValue values."
            )
        if value.unit_instance_id not in known_unit_ids:
            raise GameLifecycleError("ReserveUnitPointValue unit_instance_id is not mustered.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameConfig reserve_unit_points must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda entry: entry.unit_instance_id))


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


def _validate_optional_charge_phase_state(
    value: object | None,
) -> ChargePhaseState | None:
    if value is None:
        return None
    if type(value) is not ChargePhaseState:
        raise GameLifecycleError("GameState charge_phase_state must be a ChargePhaseState.")
    return value


def _validate_optional_fight_phase_state(
    value: object | None,
) -> FightPhaseState | None:
    if value is None:
        return None
    if type(value) is not FightPhaseState:
        raise GameLifecycleError("GameState fight_phase_state must be a FightPhaseState.")
    return value


def _validate_optional_shooting_phase_state(
    value: object | None,
) -> ShootingPhaseState | None:
    if value is None:
        return None
    if type(value) is not ShootingPhaseState:
        raise GameLifecycleError("GameState shooting_phase_state must be a ShootingPhaseState.")
    return value


def _validate_optional_out_of_phase_shooting_state(
    value: object | None,
) -> OutOfPhaseShootingState | None:
    if value is None:
        return None
    if type(value) is not OutOfPhaseShootingState:
        raise GameLifecycleError(
            "GameState out_of_phase_shooting_state must be an OutOfPhaseShootingState."
        )
    return value


def _validate_feel_no_pain_sources_by_model_id(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
) -> dict[str, tuple[FeelNoPainSource, ...]]:
    if not isinstance(values, dict):
        raise GameLifecycleError("GameState Feel No Pain sources must be a dict.")
    known_model_ids = _model_instance_ids(army_definitions)
    validated: dict[str, tuple[FeelNoPainSource, ...]] = {}
    for raw_model_id, raw_sources in cast(dict[object, object], values).items():
        model_id = _validate_identifier("Feel No Pain model_instance_id", raw_model_id)
        if known_model_ids and model_id not in known_model_ids:
            raise GameLifecycleError("Feel No Pain source model is unknown.")
        source_tuple = _validate_feel_no_pain_source_tuple(
            "Feel No Pain sources",
            raw_sources,
        )
        if not source_tuple:
            raise GameLifecycleError("Feel No Pain source model requires at least one source.")
        validated[model_id] = source_tuple
    return dict(sorted(validated.items()))


def _validate_destruction_reaction_sources_by_model_id(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
) -> dict[str, tuple[DestructionReactionSource, ...]]:
    if not isinstance(values, dict):
        raise GameLifecycleError("GameState destruction reaction sources must be a dict.")
    known_model_ids = _model_instance_ids(army_definitions)
    validated: dict[str, tuple[DestructionReactionSource, ...]] = {}
    for raw_model_id, raw_sources in cast(dict[object, object], values).items():
        model_id = _validate_identifier("Destruction reaction model_instance_id", raw_model_id)
        if known_model_ids and model_id not in known_model_ids:
            raise GameLifecycleError("Destruction reaction source model is unknown.")
        source_tuple = _validate_destruction_reaction_source_tuple(
            "Destruction reaction sources",
            raw_sources,
        )
        if not source_tuple:
            raise GameLifecycleError(
                "Destruction reaction source model requires at least one source."
            )
        validated[model_id] = source_tuple
    return dict(sorted(validated.items()))


def _validate_feel_no_pain_decline_allowed_model_ids(
    values: object,
    *,
    source_model_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise GameLifecycleError("GameState Feel No Pain decline model IDs must be a list.")
    source_ids = set(source_model_ids)
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(list[object] | tuple[object, ...], values):
        model_id = _validate_identifier("Feel No Pain decline model_instance_id", value)
        if model_id not in source_ids:
            raise GameLifecycleError("Feel No Pain decline model requires sources.")
        if model_id in seen:
            raise GameLifecycleError("Feel No Pain decline model IDs must be unique.")
        seen.add(model_id)
        validated.append(model_id)
    return tuple(sorted(validated))


def _validate_feel_no_pain_source_tuple(
    field_name: str,
    values: object,
) -> tuple[FeelNoPainSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    sources: list[FeelNoPainSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not FeelNoPainSource:
            raise GameLifecycleError(f"{field_name} must contain FeelNoPainSource values.")
        if value.source_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _validate_destruction_reaction_source_tuple(
    field_name: str,
    values: object,
) -> tuple[DestructionReactionSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    sources: list[DestructionReactionSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestructionReactionSource:
            raise GameLifecycleError(f"{field_name} must contain DestructionReactionSource values.")
        if value.source_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _validate_model_instance_id_for_state(
    *,
    state: GameState,
    model_instance_id: str,
) -> str:
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    if model_id not in _model_instance_ids(state.army_definitions):
        raise GameLifecycleError("model_instance_id is unknown.")
    return model_id


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


def _validate_faction_rule_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[FactionRuleState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState faction_rule_states must be a list.")
    validated: list[FactionRuleState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not FactionRuleState:
            raise GameLifecycleError(
                "GameState faction_rule_states must contain FactionRuleState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("FactionRuleState player_id is not in this game.")
        if value.state_id in seen:
            raise GameLifecycleError("GameState faction_rule_states must be unique.")
        seen.add(value.state_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.state_id)


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
            derived.extend(_starting_strength_records_for_army(army_definition))
        return sorted(derived, key=lambda record: record.unit_instance_id)

    expected_record_owner_by_id = _starting_strength_record_owner_by_id(army_definitions)
    validated: list[StartingStrengthRecord] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StartingStrengthRecord:
            raise GameLifecycleError(
                "GameState starting_strength_records must contain StartingStrengthRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StartingStrengthRecord player_id is not in this game.")
        owner = expected_record_owner_by_id.get(value.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("StartingStrengthRecord unit is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("StartingStrengthRecord player_id drift.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState starting_strength_records must be unique.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    if set(expected_record_owner_by_id) != seen:
        raise GameLifecycleError("GameState starting_strength_records must include every unit.")
    return sorted(validated, key=lambda record: record.unit_instance_id)


def _starting_strength_records_for_army(
    army_definition: ArmyDefinition,
) -> tuple[StartingStrengthRecord, ...]:
    if type(army_definition) is not ArmyDefinition:
        raise GameLifecycleError("StartingStrengthRecord derivation requires an ArmyDefinition.")
    attached_component_ids = {
        component_id
        for attached_unit in army_definition.attached_units
        for component_id in attached_unit.component_unit_instance_ids
    }
    records = [
        StartingStrengthRecord.from_unit(player_id=army_definition.player_id, unit=unit)
        for unit in army_definition.units
        if unit.unit_instance_id not in attached_component_ids
    ]
    unit_by_id = {unit.unit_instance_id: unit for unit in army_definition.units}
    for attached_unit in army_definition.attached_units:
        records.append(
            _starting_strength_record_for_attached_unit(
                player_id=army_definition.player_id,
                attached_unit=attached_unit,
                unit_by_id=unit_by_id,
            )
        )
    return tuple(sorted(records, key=lambda record: record.unit_instance_id))


def _starting_strength_record_for_attached_unit(
    *,
    player_id: str,
    attached_unit: AttachedUnitFormation,
    unit_by_id: dict[str, UnitInstance],
) -> StartingStrengthRecord:
    if type(attached_unit) is not AttachedUnitFormation:
        raise GameLifecycleError("Attached starting strength requires an AttachedUnitFormation.")
    starting_model_count = 0
    for unit_id in attached_unit.component_unit_instance_ids:
        unit = unit_by_id.get(unit_id)
        if unit is None:
            raise GameLifecycleError("Attached starting strength component unit is unknown.")
        starting_model_count += len(unit.own_models)
    return StartingStrengthRecord(
        player_id=player_id,
        unit_instance_id=attached_unit.attached_unit_instance_id,
        starting_model_count=starting_model_count,
        single_model_starting_wounds=None,
        source_id=attached_unit.source_id,
    )


def _starting_strength_record_owner_by_id(
    army_definitions: list[ArmyDefinition],
) -> dict[str, str]:
    owner_by_id: dict[str, str] = {}
    for army_definition in army_definitions:
        attached_component_ids = {
            component_id
            for attached_unit in army_definition.attached_units
            for component_id in attached_unit.component_unit_instance_ids
        }
        for unit in army_definition.units:
            if unit.unit_instance_id not in attached_component_ids:
                owner_by_id[unit.unit_instance_id] = army_definition.player_id
        for attached_unit in army_definition.attached_units:
            owner_by_id[attached_unit.attached_unit_instance_id] = army_definition.player_id
    return owner_by_id


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


def _validate_dedicated_transport_setup_consequences(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    player_ids: tuple[str, ...],
) -> list[DedicatedTransportSetupConsequence]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState dedicated_transport_setup_consequences must be a list.")
    unit_owner_by_id = _unit_owner_by_id(army_definitions)
    unit_by_id = {unit.unit_instance_id: unit for army in army_definitions for unit in army.units}
    validated: list[DedicatedTransportSetupConsequence] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not DedicatedTransportSetupConsequence:
            raise GameLifecycleError(
                "GameState dedicated_transport_setup_consequences must contain "
                "DedicatedTransportSetupConsequence values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence player_id is not in this game."
            )
        if value.transport_unit_instance_id in seen:
            raise GameLifecycleError(
                "GameState dedicated_transport_setup_consequences must be unique."
            )
        owner = unit_owner_by_id.get(value.transport_unit_instance_id)
        if owner is None:
            raise GameLifecycleError("DedicatedTransportSetupConsequence Transport is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("DedicatedTransportSetupConsequence player_id drift.")
        transport = unit_by_id[value.transport_unit_instance_id]
        if not _unit_has_keyword(transport, "DEDICATED TRANSPORT"):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence requires a DEDICATED TRANSPORT unit."
            )
        seen.add(value.transport_unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda consequence: consequence.transport_unit_instance_id)


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


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("unit keyword check requires a UnitInstance.")
    requested_keyword = (
        _validate_identifier("unit keyword", keyword)
        .upper()
        .replace(
            " ",
            "_",
        )
        .replace("-", "_")
    )
    unit_keywords = {
        _validate_identifier("unit keyword", value).upper().replace(" ", "_").replace("-", "_")
        for value in unit.keywords
    }
    return requested_keyword in unit_keywords


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


def _validate_prebattle_action_records(
    records: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[PreBattleActionRecord]:
    if not isinstance(records, list):
        raise GameLifecycleError("GameState prebattle_action_records must be a list.")
    validated_game_id = _validate_identifier("game_id", game_id)
    validated: list[PreBattleActionRecord] = []
    seen: set[str] = set()
    for record in cast(list[object], records):
        if type(record) is not PreBattleActionRecord:
            raise GameLifecycleError(
                "GameState prebattle_action_records must contain PreBattleActionRecord values."
            )
        if record.game_id != validated_game_id:
            raise GameLifecycleError("PreBattleActionRecord game_id drift.")
        if record.player_id not in player_ids:
            raise GameLifecycleError("PreBattleActionRecord player_id is not in this game.")
        if record.action_id in seen:
            raise GameLifecycleError("GameState prebattle_action_records must be unique.")
        seen.add(record.action_id)
        validated.append(record)
    return sorted(validated, key=lambda stored: stored.action_id)


def _unit_owner_by_id(army_definitions: list[ArmyDefinition]) -> dict[str, str]:
    return {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }


def _model_instance_ids(army_definitions: list[ArmyDefinition]) -> set[str]:
    return {
        model.model_instance_id
        for army in army_definitions
        for unit in army.units
        for model in unit.own_models
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


def _validate_sticky_objective_control_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[StickyObjectiveControlState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState sticky objective-control states must be a list.")
    player_id_set = set(player_ids)
    validated: list[StickyObjectiveControlState] = []
    seen_ids: set[str] = set()
    holder_by_objective: dict[str, str] = {}
    for state in cast(list[object], states):
        if type(state) is not StickyObjectiveControlState:
            raise GameLifecycleError(
                "GameState sticky objective-control states must contain sticky states."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("StickyObjectiveControlState game_id drift.")
        if state.player_id not in player_id_set or state.active_player_id not in player_id_set:
            raise GameLifecycleError("StickyObjectiveControlState player_id is not in this game.")
        if state.state_id in seen_ids:
            raise GameLifecycleError("GameState sticky objective-control states must be unique.")
        current_holder = holder_by_objective.get(state.objective_id)
        if current_holder is not None and current_holder != state.player_id:
            raise GameLifecycleError(
                "Sticky objective-control states cannot have multiple holders per objective."
            )
        seen_ids.add(state.state_id)
        holder_by_objective[state.objective_id] = state.player_id
        validated.append(state)
    return sorted(validated, key=lambda stored: stored.state_id)


def _validate_primary_objective_turn_start_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[PrimaryObjectiveTurnStartState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary turn-start states must be a list.")
    validated: list[PrimaryObjectiveTurnStartState] = []
    seen_ids: set[str] = set()
    seen_turns: set[tuple[str, int]] = set()
    for state in cast(list[object], states):
        if type(state) is not PrimaryObjectiveTurnStartState:
            raise GameLifecycleError(
                "GameState primary turn-start states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState player_id is not in this game."
            )
        if state.state_id in seen_ids:
            raise GameLifecycleError("GameState primary turn-start states must be unique.")
        turn_key = (state.player_id, state.battle_round)
        if turn_key in seen_turns:
            raise GameLifecycleError(
                "GameState primary turn-start states must be unique per player turn."
            )
        seen_ids.add(state.state_id)
        seen_turns.add(turn_key)
        validated.append(state)
    return sorted(validated, key=lambda state: state.state_id)


def _validate_primary_terrain_trap_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[PrimaryTerrainTrapState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary terrain trap states must be a list.")
    validated: list[PrimaryTerrainTrapState] = []
    seen_ids: set[str] = set()
    seen_traps: set[tuple[str, str]] = set()
    for state in cast(list[object], states):
        if type(state) is not PrimaryTerrainTrapState:
            raise GameLifecycleError(
                "GameState primary terrain trap states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryTerrainTrapState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError("PrimaryTerrainTrapState player_id is not in this game.")
        if state.trap_id in seen_ids:
            raise GameLifecycleError("GameState primary terrain trap states must be unique.")
        trap_key = (state.player_id, state.terrain_feature_id)
        if trap_key in seen_traps:
            raise GameLifecycleError(
                "GameState primary terrain trap states must be unique per player and terrain."
            )
        seen_ids.add(state.trap_id)
        seen_traps.add(trap_key)
        validated.append(state)
    return sorted(validated, key=lambda state: state.trap_id)


def _validate_primary_unit_destruction_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[PrimaryUnitDestructionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary unit destruction states must be a list.")
    validated: list[PrimaryUnitDestructionState] = []
    seen_ids: set[str] = set()
    seen_units: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not PrimaryUnitDestructionState:
            raise GameLifecycleError(
                "GameState primary unit destruction states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryUnitDestructionState game_id drift.")
        if (
            state.destroying_player_id not in player_ids
            or state.destroyed_player_id not in player_ids
            or state.active_player_id not in player_ids
        ):
            raise GameLifecycleError("PrimaryUnitDestructionState player_id is not in this game.")
        if state.destruction_id in seen_ids:
            raise GameLifecycleError("GameState primary unit destruction states must be unique.")
        if state.destroyed_unit_instance_id in seen_units:
            raise GameLifecycleError(
                "GameState primary unit destruction states must be unique per destroyed unit."
            )
        seen_ids.add(state.destruction_id)
        seen_units.add(state.destroyed_unit_instance_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.destruction_id)


def _validate_secondary_unit_destruction_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[SecondaryUnitDestructionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary unit destruction states must be a list.")
    validated: list[SecondaryUnitDestructionState] = []
    seen_ids: set[str] = set()
    seen_units: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not SecondaryUnitDestructionState:
            raise GameLifecycleError(
                "GameState secondary unit destruction states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("SecondaryUnitDestructionState game_id drift.")
        if (
            state.destroying_player_id not in player_ids
            or state.destroyed_player_id not in player_ids
            or state.active_player_id not in player_ids
        ):
            raise GameLifecycleError("SecondaryUnitDestructionState player_id is not in this game.")
        if state.destruction_id in seen_ids:
            raise GameLifecycleError("GameState secondary unit destruction states must be unique.")
        if state.destroyed_unit_instance_id in seen_units:
            raise GameLifecycleError(
                "GameState secondary unit destruction states must be unique per destroyed unit."
            )
        seen_ids.add(state.destruction_id)
        seen_units.add(state.destroyed_unit_instance_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.destruction_id)


def _validate_secondary_objective_cleanse_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[SecondaryObjectiveCleanseState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary objective cleanse states must be a list.")
    validated: list[SecondaryObjectiveCleanseState] = []
    seen_ids: set[str] = set()
    seen_actions: set[str] = set()
    seen_objective_turns: set[tuple[str, int, str, str]] = set()
    for state in cast(list[object], states):
        if type(state) is not SecondaryObjectiveCleanseState:
            raise GameLifecycleError(
                "GameState secondary objective cleanse states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("SecondaryObjectiveCleanseState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError(
                "SecondaryObjectiveCleanseState player_id is not in this game."
            )
        if state.cleanse_id in seen_ids:
            raise GameLifecycleError("GameState secondary objective cleanse states must be unique.")
        if state.action_id in seen_actions:
            raise GameLifecycleError(
                "GameState secondary objective cleanse states must be unique per action."
            )
        objective_key = (
            state.player_id,
            state.battle_round,
            state.active_player_id,
            state.objective_marker_id,
        )
        if objective_key in seen_objective_turns:
            raise GameLifecycleError(
                "GameState secondary objective cleanse states must be unique per objective turn."
            )
        seen_ids.add(state.cleanse_id)
        seen_actions.add(state.action_id)
        seen_objective_turns.add(objective_key)
        validated.append(state)
    return sorted(validated, key=lambda state: state.cleanse_id)


def _validate_secondary_terrain_plunder_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[SecondaryTerrainPlunderState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary terrain plunder states must be a list.")
    validated: list[SecondaryTerrainPlunderState] = []
    seen_ids: set[str] = set()
    seen_actions: set[str] = set()
    seen_player_turns: set[tuple[str, int, str]] = set()
    for state in cast(list[object], states):
        if type(state) is not SecondaryTerrainPlunderState:
            raise GameLifecycleError(
                "GameState secondary terrain plunder states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("SecondaryTerrainPlunderState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError("SecondaryTerrainPlunderState player_id is not in this game.")
        if state.plunder_id in seen_ids:
            raise GameLifecycleError("GameState secondary terrain plunder states must be unique.")
        if state.action_id in seen_actions:
            raise GameLifecycleError(
                "GameState secondary terrain plunder states must be unique per action."
            )
        player_turn_key = (state.player_id, state.battle_round, state.active_player_id)
        if player_turn_key in seen_player_turns:
            raise GameLifecycleError(
                "GameState secondary terrain plunder states must be unique per player turn."
            )
        seen_ids.add(state.plunder_id)
        seen_actions.add(state.action_id)
        seen_player_turns.add(player_turn_key)
        validated.append(state)
    return sorted(validated, key=lambda state: state.plunder_id)


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


def _validate_tactical_secondary_achievement_contexts(
    contexts: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[TacticalSecondaryAchievementContext]:
    if not isinstance(contexts, list):
        raise GameLifecycleError(
            "GameState tactical_secondary_achievement_contexts must be a list."
        )
    requested_game_id = _validate_identifier("game_id", game_id)
    validated: list[TacticalSecondaryAchievementContext] = []
    seen_ids: set[str] = set()
    seen_cards: set[tuple[str, str, int]] = set()
    for context in cast(list[object], contexts):
        if type(context) is not TacticalSecondaryAchievementContext:
            raise GameLifecycleError(
                "GameState tactical_secondary_achievement_contexts must contain contexts."
            )
        if context.game_id != requested_game_id:
            raise GameLifecycleError("TacticalSecondaryAchievementContext game_id drift.")
        if context.player_id not in player_ids:
            raise GameLifecycleError(
                "TacticalSecondaryAchievementContext player_id is not in this game."
            )
        if context.active_player_id not in player_ids:
            raise GameLifecycleError(
                "TacticalSecondaryAchievementContext active_player_id is not in this game."
            )
        if context.achievement_id in seen_ids:
            raise GameLifecycleError(
                "GameState tactical_secondary_achievement_contexts must not duplicate IDs."
            )
        card_key = (
            context.player_id,
            context.secondary_mission_id,
            context.card_battle_round,
        )
        if card_key in seen_cards:
            raise GameLifecycleError(
                "GameState tactical_secondary_achievement_contexts must not duplicate cards."
            )
        seen_ids.add(context.achievement_id)
        seen_cards.add(card_key)
        validated.append(context)
    return sorted(
        validated,
        key=lambda context: (
            context.player_id,
            context.card_battle_round,
            context.secondary_mission_id,
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


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a boolean.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
