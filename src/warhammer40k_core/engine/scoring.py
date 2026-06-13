from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


class VictoryPointSourceKind(StrEnum):
    PRIMARY = "primary"
    FIXED_SECONDARY = "fixed_secondary"
    TACTICAL_SECONDARY = "tactical_secondary"
    MISSION_ACTION = "mission_action"
    BATTLE_READY = "battle_ready"


class VictoryPointCapBucket(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    BATTLE_READY = "battle_ready"


FIXED_SECONDARY_MISSION_VP_CAP = 20


class ScoringWindowKind(StrEnum):
    END_OF_ROUND = "end_of_round"
    END_OF_GAME = "end_of_game"


class SecondaryMissionCardStatus(StrEnum):
    ACTIVE = "active"
    SCORED = "scored"
    DISCARDED = "discarded"


class SecondaryMissionCardMode(StrEnum):
    FIXED = "fixed"
    TACTICAL = "tactical"


_SUPPORTED_SECONDARY_SCORING_RULE_CONDITIONS = frozenset(
    {
        "fixed_secondary_condition",
        "tactical_secondary_condition",
        "each_enemy_model_w10_or_more_destroyed_this_turn",
        "control_home_objective",
        "no_enemy_units_within_own_deployment_zone",
        "each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn",
        "each_enemy_unit_destroyed_this_turn",
        "each_enemy_unit_started_turn_in_range_of_objective_destroyed",
        "one_or_more_objectives_cleansed_this_turn",
        "two_or_more_objectives_cleansed_this_turn",
        "one_or_more_terrain_areas_plundered_this_turn",
        "control_two_or_more_no_mans_land_objectives_excluding_home",
    }
)


class VictoryPointTransactionPayload(TypedDict):
    transaction_id: str
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: str
    source_id: str
    scoring_timing: str
    hidden: bool
    metadata: JsonValue


class VictoryPointLedgerPayload(TypedDict):
    player_id: str
    victory_points: int
    transactions: list[VictoryPointTransactionPayload]


class VictoryPointAwardPayload(TypedDict):
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: str
    source_id: str
    scoring_timing: str
    hidden: bool
    metadata: JsonValue


class MissionScoringPolicyPayload(TypedDict):
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: str
    primary_scoring_rule_id: str | None
    primary_scoring_rule_condition: str | None
    primary_scoring_rule_source_id: str | None
    primary_vp_per_controlled_objective: int | None
    primary_max_vp_per_turn: int | None
    primary_scoring_rules: list[PrimaryMissionScoringRulePayload]
    secondary_vp_per_score: int
    secondary_scoring_rules: list[SecondaryMissionScoringRulePayload]
    mission_action_scoring_rules: list[MissionActionScoringRulePayload]
    mission_action_vp: int
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
    end_of_round_scoring_windows: list[str]
    end_of_game_scoring_windows: list[str]
    source_id: str


class PrimaryMissionScoringRulePayload(TypedDict):
    rule_id: str
    timing: str
    source_kind: str
    victory_points: int
    cap: int | None
    condition: str
    source_id: str


class SecondaryMissionScoringRulePayload(TypedDict):
    secondary_mission_id: str
    source_kind: str
    timing: str
    victory_points: int
    cap: int | None
    condition: str
    rule_id: str
    source_id: str


class MissionActionScoringRulePayload(TypedDict):
    mission_action_id: str
    mission_id: str
    mission_kind: str
    scoring_source_id: str
    victory_points: int
    cap_bucket: str
    source_id: str


class PrimaryObjectiveTurnStartStatePayload(TypedDict):
    state_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    controlled_objective_ids: list[str]
    source_id: str


class PrimaryTerrainTrapStatePayload(TypedDict):
    trap_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    terrain_feature_id: str
    is_objective: bool
    action_id: str
    source_id: str


class PrimaryUnitDestructionStatePayload(TypedDict):
    destruction_id: str
    game_id: str
    destroying_player_id: str
    destroyed_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    destroyed_unit_instance_id: str
    started_turn_terrain_feature_ids: list[str]
    source_id: str


class SecondaryDestroyedModelStatePayload(TypedDict):
    model_instance_id: str
    starting_wounds: int


class SecondaryUnitDestructionStatePayload(TypedDict):
    destruction_id: str
    game_id: str
    destroying_player_id: str
    destroyed_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    destroyed_unit_instance_id: str
    destroyed_models: list[SecondaryDestroyedModelStatePayload]
    started_turn_objective_marker_ids: list[str]
    source_id: str


class SecondaryObjectiveCleanseStatePayload(TypedDict):
    cleanse_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    objective_marker_id: str
    action_id: str
    source_id: str


class SecondaryTerrainPlunderStatePayload(TypedDict):
    plunder_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    terrain_feature_id: str
    action_id: str
    source_id: str


class SecondaryMissionCardStatePayload(TypedDict):
    player_id: str
    secondary_mission_id: str
    mode: str
    battle_round: int
    status: str
    source_result_id: str | None
    scored_transaction_id: str | None
    discarded_result_id: str | None


class TacticalSecondaryAchievementContextPayload(TypedDict):
    achievement_id: str
    game_id: str
    player_id: str
    active_player_id: str
    secondary_mission_id: str
    mode: str
    battle_round: int
    phase: str
    card_battle_round: int
    victory_points: int
    scoring_rule_id: str
    scoring_rule_condition: str
    scoring_rule_source_id: str
    scoring_timing: str
    source_id: str
    evidence: JsonValue


class ScoringWindowStatePayload(TypedDict):
    window_id: str
    game_id: str
    battle_round: int
    window_kind: str
    window: str
    source_id: str


class FinalScorePayload(TypedDict):
    player_id: str
    victory_points: int


class FinalScoreLinePayload(TypedDict):
    player_id: str
    victory_points: int
    raw_victory_points: int
    raw_primary_vp: int
    raw_secondary_vp: int
    raw_battle_ready_vp: int
    raw_other_vp: int
    capped_primary_vp: int
    capped_secondary_vp: int
    capped_battle_ready_vp: int
    capped_other_vp: int
    cap_adjustment: int


class FinalScoringAuditPayload(TypedDict):
    policy_source_id: str
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp_cap: int
    total_vp_cap: int
    scoring_windows: list[ScoringWindowStatePayload]
    player_scores: list[FinalScoreLinePayload]


class FinalScoringResultPayload(TypedDict):
    result_id: str
    game_id: str
    battle_round: int
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    final_scores: list[FinalScorePayload]
    winner_player_ids: list[str]
    is_draw: bool
    scoring_audit: FinalScoringAuditPayload


@dataclass(frozen=True, slots=True)
class VictoryPointTransaction:
    transaction_id: str
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: VictoryPointSourceKind
    source_id: str
    scoring_timing: str
    hidden: bool = False
    metadata: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _validate_identifier("VictoryPointTransaction transaction_id", self.transaction_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("VictoryPointTransaction player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("VictoryPointTransaction battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("VictoryPointTransaction phase", self.phase),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_non_negative_int("VictoryPointTransaction amount", self.amount),
        )
        object.__setattr__(
            self,
            "source_kind",
            victory_point_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("VictoryPointTransaction source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "scoring_timing",
            _validate_identifier(
                "VictoryPointTransaction scoring_timing",
                self.scoring_timing,
            ),
        )
        object.__setattr__(
            self,
            "hidden",
            _validate_bool("VictoryPointTransaction hidden", self.hidden),
        )
        object.__setattr__(self, "metadata", validate_json_value(self.metadata))

    def to_payload(self) -> VictoryPointTransactionPayload:
        return {
            "transaction_id": self.transaction_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "amount": self.amount,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "scoring_timing": self.scoring_timing,
            "hidden": self.hidden,
            "metadata": self.metadata,
        }

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        viewer = _validate_identifier("viewer_player_id", viewer_player_id)
        choices_revealed = _validate_bool(
            "secondary_mission_choices_revealed",
            secondary_mission_choices_revealed,
        )
        if (
            self.hidden
            and viewer != self.player_id
            and not (
                choices_revealed
                and self.source_kind
                in {
                    VictoryPointSourceKind.FIXED_SECONDARY,
                    VictoryPointSourceKind.TACTICAL_SECONDARY,
                }
            )
        ):
            return {
                "transaction_id": self.transaction_id,
                "player_id": self.player_id,
                "battle_round": self.battle_round,
                "phase": self.phase,
                "amount": self.amount,
                "hidden": True,
            }
        payload = cast(dict[str, JsonValue], self.to_payload())
        if self.hidden and viewer != self.player_id:
            payload["hidden"] = False
        return payload

    @classmethod
    def from_payload(cls, payload: VictoryPointTransactionPayload) -> Self:
        return cls(
            transaction_id=payload["transaction_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            amount=payload["amount"],
            source_kind=victory_point_source_kind_from_token(payload["source_kind"]),
            source_id=payload["source_id"],
            scoring_timing=payload["scoring_timing"],
            hidden=payload["hidden"],
            metadata=payload["metadata"],
        )


@dataclass(frozen=True, slots=True)
class VictoryPointAward:
    player_id: str
    battle_round: int
    phase: str
    amount: int
    source_kind: VictoryPointSourceKind
    source_id: str
    scoring_timing: str
    hidden: bool = False
    metadata: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("VictoryPointAward player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("VictoryPointAward battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("VictoryPointAward phase", self.phase),
        )
        object.__setattr__(
            self,
            "amount",
            _validate_positive_int("VictoryPointAward amount", self.amount),
        )
        object.__setattr__(
            self, "source_kind", victory_point_source_kind_from_token(self.source_kind)
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("VictoryPointAward source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "scoring_timing",
            _validate_identifier("VictoryPointAward scoring_timing", self.scoring_timing),
        )
        object.__setattr__(self, "hidden", _validate_bool("VictoryPointAward hidden", self.hidden))
        object.__setattr__(self, "metadata", validate_json_value(self.metadata))

    def to_payload(self) -> VictoryPointAwardPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "amount": self.amount,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "scoring_timing": self.scoring_timing,
            "hidden": self.hidden,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class VictoryPointLedger:
    player_id: str
    victory_points: int = 0
    transactions: tuple[VictoryPointTransaction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("VictoryPointLedger player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_non_negative_int("VictoryPointLedger victory_points", self.victory_points),
        )
        transactions = _validate_victory_point_transaction_tuple(
            "VictoryPointLedger transactions",
            self.transactions,
            player_id=self.player_id,
        )
        total = sum(transaction.amount for transaction in transactions)
        if total != self.victory_points:
            raise GameLifecycleError("VictoryPointLedger points must match transactions.")
        object.__setattr__(self, "transactions", transactions)

    @classmethod
    def initial(cls, *, player_id: str) -> Self:
        return cls(player_id=player_id)

    def award(
        self,
        award: VictoryPointAward,
        *,
        applied_amount: int | None = None,
        metadata: JsonValue | None = None,
    ) -> tuple[Self, VictoryPointTransaction]:
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("VictoryPointLedger award must be a VictoryPointAward.")
        if award.player_id != self.player_id:
            raise GameLifecycleError("VictoryPointLedger award player_id drift.")
        transaction_amount = (
            award.amount
            if applied_amount is None
            else _validate_non_negative_int("VictoryPointLedger applied_amount", applied_amount)
        )
        if transaction_amount > award.amount:
            raise GameLifecycleError("VictoryPointLedger applied_amount exceeds award amount.")
        transaction_metadata = award.metadata if metadata is None else validate_json_value(metadata)
        transaction = VictoryPointTransaction(
            transaction_id=(
                f"victory-point:{self.player_id}:round-{award.battle_round:02d}:"
                f"{len(self.transactions) + 1:06d}"
            ),
            player_id=self.player_id,
            battle_round=award.battle_round,
            phase=award.phase,
            amount=transaction_amount,
            source_kind=award.source_kind,
            source_id=award.source_id,
            scoring_timing=award.scoring_timing,
            hidden=award.hidden,
            metadata=transaction_metadata,
        )
        return (
            type(self)(
                player_id=self.player_id,
                victory_points=self.victory_points + transaction_amount,
                transactions=(*self.transactions, transaction),
            ),
            transaction,
        )

    def points_from_source_kind(self, source_kind: VictoryPointSourceKind) -> int:
        requested_kind = victory_point_source_kind_from_token(source_kind)
        return sum(
            transaction.amount
            for transaction in self.transactions
            if transaction.source_kind is requested_kind
        )

    def to_payload(self) -> VictoryPointLedgerPayload:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
            "transactions": [transaction.to_payload() for transaction in self.transactions],
        }

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
            "transactions": [
                transaction.to_public_payload(
                    viewer_player_id=viewer_player_id,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
                for transaction in self.transactions
            ],
        }

    @classmethod
    def from_payload(cls, payload: VictoryPointLedgerPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            victory_points=payload["victory_points"],
            transactions=tuple(
                VictoryPointTransaction.from_payload(transaction)
                for transaction in payload["transactions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionScoringRule:
    rule_id: str
    timing: str
    source_kind: VictoryPointSourceKind
    victory_points: int
    cap: int | None
    condition: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rule_id",
            _validate_identifier("PrimaryMissionScoringRule rule_id", self.rule_id),
        )
        object.__setattr__(
            self,
            "timing",
            _validate_identifier("PrimaryMissionScoringRule timing", self.timing),
        )
        source_kind = victory_point_source_kind_from_token(self.source_kind)
        if source_kind is not VictoryPointSourceKind.PRIMARY:
            raise GameLifecycleError("PrimaryMissionScoringRule source_kind must be primary.")
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(
            self,
            "victory_points",
            _validate_positive_int(
                "PrimaryMissionScoringRule victory_points",
                self.victory_points,
            ),
        )
        object.__setattr__(
            self,
            "cap",
            _validate_optional_positive_int("PrimaryMissionScoringRule cap", self.cap),
        )
        object.__setattr__(
            self,
            "condition",
            _validate_identifier("PrimaryMissionScoringRule condition", self.condition),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryMissionScoringRule source_id", self.source_id),
        )

    def to_payload(self) -> PrimaryMissionScoringRulePayload:
        return {
            "rule_id": self.rule_id,
            "timing": self.timing,
            "source_kind": self.source_kind.value,
            "victory_points": self.victory_points,
            "cap": self.cap,
            "condition": self.condition,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryMissionScoringRulePayload) -> Self:
        return cls(
            rule_id=payload["rule_id"],
            timing=payload["timing"],
            source_kind=victory_point_source_kind_from_token(payload["source_kind"]),
            victory_points=payload["victory_points"],
            cap=payload["cap"],
            condition=payload["condition"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryObjectiveTurnStartState:
    state_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    controlled_objective_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state_id",
            _validate_identifier("PrimaryObjectiveTurnStartState state_id", self.state_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PrimaryObjectiveTurnStartState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PrimaryObjectiveTurnStartState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "PrimaryObjectiveTurnStartState active_player_id",
                self.active_player_id,
            ),
        )
        if self.player_id != self.active_player_id:
            raise GameLifecycleError("Primary turn-start state must belong to active player.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "PrimaryObjectiveTurnStartState battle_round", self.battle_round
            ),
        )
        object.__setattr__(
            self,
            "controlled_objective_ids",
            _validate_identifier_tuple(
                "PrimaryObjectiveTurnStartState controlled_objective_ids",
                self.controlled_objective_ids,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryObjectiveTurnStartState source_id", self.source_id),
        )

    def to_payload(self) -> PrimaryObjectiveTurnStartStatePayload:
        return {
            "state_id": self.state_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "controlled_objective_ids": list(self.controlled_objective_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryObjectiveTurnStartStatePayload) -> Self:
        return cls(
            state_id=payload["state_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            controlled_objective_ids=tuple(payload["controlled_objective_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryTerrainTrapState:
    trap_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    terrain_feature_id: str
    is_objective: bool
    action_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trap_id",
            _validate_identifier("PrimaryTerrainTrapState trap_id", self.trap_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PrimaryTerrainTrapState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PrimaryTerrainTrapState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("PrimaryTerrainTrapState active_player_id", self.active_player_id),
        )
        if self.player_id != self.active_player_id:
            raise GameLifecycleError("Primary terrain trap must be recorded during owner's turn.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("PrimaryTerrainTrapState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("PrimaryTerrainTrapState phase", self.phase),
        )
        object.__setattr__(
            self,
            "terrain_feature_id",
            _validate_identifier(
                "PrimaryTerrainTrapState terrain_feature_id",
                self.terrain_feature_id,
            ),
        )
        object.__setattr__(
            self,
            "is_objective",
            _validate_bool("PrimaryTerrainTrapState is_objective", self.is_objective),
        )
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("PrimaryTerrainTrapState action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryTerrainTrapState source_id", self.source_id),
        )

    def to_payload(self) -> PrimaryTerrainTrapStatePayload:
        return {
            "trap_id": self.trap_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "terrain_feature_id": self.terrain_feature_id,
            "is_objective": self.is_objective,
            "action_id": self.action_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryTerrainTrapStatePayload) -> Self:
        return cls(
            trap_id=payload["trap_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            terrain_feature_id=payload["terrain_feature_id"],
            is_objective=payload["is_objective"],
            action_id=payload["action_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryUnitDestructionState:
    destruction_id: str
    game_id: str
    destroying_player_id: str
    destroyed_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    destroyed_unit_instance_id: str
    started_turn_terrain_feature_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "destruction_id",
            _validate_identifier("PrimaryUnitDestructionState destruction_id", self.destruction_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PrimaryUnitDestructionState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_identifier(
                "PrimaryUnitDestructionState destroying_player_id",
                self.destroying_player_id,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier(
                "PrimaryUnitDestructionState destroyed_player_id",
                self.destroyed_player_id,
            ),
        )
        if self.destroying_player_id == self.destroyed_player_id:
            raise GameLifecycleError("Primary unit destruction must target an enemy unit.")
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "PrimaryUnitDestructionState active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("PrimaryUnitDestructionState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("PrimaryUnitDestructionState phase", self.phase),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier(
                "PrimaryUnitDestructionState destroyed_unit_instance_id",
                self.destroyed_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "started_turn_terrain_feature_ids",
            _validate_identifier_tuple(
                "PrimaryUnitDestructionState started_turn_terrain_feature_ids",
                self.started_turn_terrain_feature_ids,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryUnitDestructionState source_id", self.source_id),
        )

    def to_payload(self) -> PrimaryUnitDestructionStatePayload:
        return {
            "destruction_id": self.destruction_id,
            "game_id": self.game_id,
            "destroying_player_id": self.destroying_player_id,
            "destroyed_player_id": self.destroyed_player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "destroyed_unit_instance_id": self.destroyed_unit_instance_id,
            "started_turn_terrain_feature_ids": list(self.started_turn_terrain_feature_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryUnitDestructionStatePayload) -> Self:
        return cls(
            destruction_id=payload["destruction_id"],
            game_id=payload["game_id"],
            destroying_player_id=payload["destroying_player_id"],
            destroyed_player_id=payload["destroyed_player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            destroyed_unit_instance_id=payload["destroyed_unit_instance_id"],
            started_turn_terrain_feature_ids=tuple(payload["started_turn_terrain_feature_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class SecondaryDestroyedModelState:
    model_instance_id: str
    starting_wounds: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "SecondaryDestroyedModelState model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "starting_wounds",
            _validate_positive_int(
                "SecondaryDestroyedModelState starting_wounds",
                self.starting_wounds,
            ),
        )

    def to_payload(self) -> SecondaryDestroyedModelStatePayload:
        return {
            "model_instance_id": self.model_instance_id,
            "starting_wounds": self.starting_wounds,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryDestroyedModelStatePayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            starting_wounds=payload["starting_wounds"],
        )


@dataclass(frozen=True, slots=True)
class SecondaryUnitDestructionState:
    destruction_id: str
    game_id: str
    destroying_player_id: str
    destroyed_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    destroyed_unit_instance_id: str
    destroyed_models: tuple[SecondaryDestroyedModelState, ...]
    started_turn_objective_marker_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "destruction_id",
            _validate_identifier(
                "SecondaryUnitDestructionState destruction_id",
                self.destruction_id,
            ),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("SecondaryUnitDestructionState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_identifier(
                "SecondaryUnitDestructionState destroying_player_id",
                self.destroying_player_id,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier(
                "SecondaryUnitDestructionState destroyed_player_id",
                self.destroyed_player_id,
            ),
        )
        if self.destroying_player_id == self.destroyed_player_id:
            raise GameLifecycleError("Secondary unit destruction must target an enemy unit.")
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "SecondaryUnitDestructionState active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("SecondaryUnitDestructionState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("SecondaryUnitDestructionState phase", self.phase),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier(
                "SecondaryUnitDestructionState destroyed_unit_instance_id",
                self.destroyed_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_models",
            _validate_secondary_destroyed_model_state_tuple(self.destroyed_models),
        )
        object.__setattr__(
            self,
            "started_turn_objective_marker_ids",
            _validate_identifier_tuple(
                "SecondaryUnitDestructionState started_turn_objective_marker_ids",
                self.started_turn_objective_marker_ids,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SecondaryUnitDestructionState source_id", self.source_id),
        )

    def to_payload(self) -> SecondaryUnitDestructionStatePayload:
        return {
            "destruction_id": self.destruction_id,
            "game_id": self.game_id,
            "destroying_player_id": self.destroying_player_id,
            "destroyed_player_id": self.destroyed_player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "destroyed_unit_instance_id": self.destroyed_unit_instance_id,
            "destroyed_models": [model.to_payload() for model in self.destroyed_models],
            "started_turn_objective_marker_ids": list(self.started_turn_objective_marker_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryUnitDestructionStatePayload) -> Self:
        return cls(
            destruction_id=payload["destruction_id"],
            game_id=payload["game_id"],
            destroying_player_id=payload["destroying_player_id"],
            destroyed_player_id=payload["destroyed_player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            destroyed_unit_instance_id=payload["destroyed_unit_instance_id"],
            destroyed_models=tuple(
                SecondaryDestroyedModelState.from_payload(model)
                for model in payload["destroyed_models"]
            ),
            started_turn_objective_marker_ids=tuple(payload["started_turn_objective_marker_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class SecondaryObjectiveCleanseState:
    cleanse_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    objective_marker_id: str
    action_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cleanse_id",
            _validate_identifier("SecondaryObjectiveCleanseState cleanse_id", self.cleanse_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("SecondaryObjectiveCleanseState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SecondaryObjectiveCleanseState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "SecondaryObjectiveCleanseState active_player_id",
                self.active_player_id,
            ),
        )
        if self.player_id != self.active_player_id:
            raise GameLifecycleError("Secondary objective cleanse must happen on owner's turn.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "SecondaryObjectiveCleanseState battle_round", self.battle_round
            ),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("SecondaryObjectiveCleanseState phase", self.phase),
        )
        object.__setattr__(
            self,
            "objective_marker_id",
            _validate_identifier(
                "SecondaryObjectiveCleanseState objective_marker_id",
                self.objective_marker_id,
            ),
        )
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("SecondaryObjectiveCleanseState action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SecondaryObjectiveCleanseState source_id", self.source_id),
        )

    def to_payload(self) -> SecondaryObjectiveCleanseStatePayload:
        return {
            "cleanse_id": self.cleanse_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "objective_marker_id": self.objective_marker_id,
            "action_id": self.action_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryObjectiveCleanseStatePayload) -> Self:
        return cls(
            cleanse_id=payload["cleanse_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            objective_marker_id=payload["objective_marker_id"],
            action_id=payload["action_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class SecondaryTerrainPlunderState:
    plunder_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    terrain_feature_id: str
    action_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plunder_id",
            _validate_identifier("SecondaryTerrainPlunderState plunder_id", self.plunder_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("SecondaryTerrainPlunderState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SecondaryTerrainPlunderState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "SecondaryTerrainPlunderState active_player_id",
                self.active_player_id,
            ),
        )
        if self.player_id != self.active_player_id:
            raise GameLifecycleError("Secondary terrain plunder must happen on owner's turn.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("SecondaryTerrainPlunderState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("SecondaryTerrainPlunderState phase", self.phase),
        )
        object.__setattr__(
            self,
            "terrain_feature_id",
            _validate_identifier(
                "SecondaryTerrainPlunderState terrain_feature_id",
                self.terrain_feature_id,
            ),
        )
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("SecondaryTerrainPlunderState action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SecondaryTerrainPlunderState source_id", self.source_id),
        )

    def to_payload(self) -> SecondaryTerrainPlunderStatePayload:
        return {
            "plunder_id": self.plunder_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "terrain_feature_id": self.terrain_feature_id,
            "action_id": self.action_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryTerrainPlunderStatePayload) -> Self:
        return cls(
            plunder_id=payload["plunder_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            terrain_feature_id=payload["terrain_feature_id"],
            action_id=payload["action_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class SecondaryMissionScoringRule:
    secondary_mission_id: str
    source_kind: VictoryPointSourceKind
    timing: str
    victory_points: int
    cap: int | None
    condition: str
    rule_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier(
                "SecondaryMissionScoringRule secondary_mission_id",
                self.secondary_mission_id,
            ),
        )
        source_kind = victory_point_source_kind_from_token(self.source_kind)
        if source_kind not in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            raise GameLifecycleError(
                "SecondaryMissionScoringRule source_kind must be a secondary source kind."
            )
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(
            self,
            "timing",
            _validate_identifier("SecondaryMissionScoringRule timing", self.timing),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_positive_int(
                "SecondaryMissionScoringRule victory_points",
                self.victory_points,
            ),
        )
        object.__setattr__(
            self,
            "cap",
            _validate_optional_positive_int("SecondaryMissionScoringRule cap", self.cap),
        )
        object.__setattr__(
            self,
            "condition",
            _validate_identifier("SecondaryMissionScoringRule condition", self.condition),
        )
        object.__setattr__(
            self,
            "rule_id",
            _validate_identifier("SecondaryMissionScoringRule rule_id", self.rule_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SecondaryMissionScoringRule source_id", self.source_id),
        )
        if self.condition not in _SUPPORTED_SECONDARY_SCORING_RULE_CONDITIONS:
            raise GameLifecycleError("Unsupported secondary scoring rule condition.")

    def to_payload(self) -> SecondaryMissionScoringRulePayload:
        return {
            "secondary_mission_id": self.secondary_mission_id,
            "source_kind": self.source_kind.value,
            "timing": self.timing,
            "victory_points": self.victory_points,
            "cap": self.cap,
            "condition": self.condition,
            "rule_id": self.rule_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryMissionScoringRulePayload) -> Self:
        return cls(
            secondary_mission_id=payload["secondary_mission_id"],
            source_kind=victory_point_source_kind_from_token(payload["source_kind"]),
            timing=payload["timing"],
            victory_points=payload["victory_points"],
            cap=payload["cap"],
            condition=payload["condition"],
            rule_id=payload["rule_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionActionScoringRule:
    mission_action_id: str
    mission_id: str
    mission_kind: str
    scoring_source_id: str
    victory_points: int
    cap_bucket: VictoryPointCapBucket
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_action_id",
            _validate_identifier(
                "MissionActionScoringRule mission_action_id",
                self.mission_action_id,
            ),
        )
        object.__setattr__(
            self,
            "mission_id",
            _validate_identifier("MissionActionScoringRule mission_id", self.mission_id),
        )
        mission_kind = _validate_identifier(
            "MissionActionScoringRule mission_kind",
            self.mission_kind,
        )
        if mission_kind not in {"primary", "secondary"}:
            raise GameLifecycleError("MissionActionScoringRule mission_kind is unsupported.")
        object.__setattr__(self, "mission_kind", mission_kind)
        object.__setattr__(
            self,
            "scoring_source_id",
            _validate_identifier(
                "MissionActionScoringRule scoring_source_id",
                self.scoring_source_id,
            ),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_non_negative_int(
                "MissionActionScoringRule victory_points",
                self.victory_points,
            ),
        )
        cap_bucket = victory_point_cap_bucket_from_token(self.cap_bucket)
        expected_bucket = (
            VictoryPointCapBucket.PRIMARY
            if mission_kind == "primary"
            else VictoryPointCapBucket.SECONDARY
        )
        if cap_bucket is not expected_bucket:
            raise GameLifecycleError("MissionActionScoringRule cap_bucket does not match kind.")
        object.__setattr__(self, "cap_bucket", cap_bucket)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionActionScoringRule source_id", self.source_id),
        )

    def to_payload(self) -> MissionActionScoringRulePayload:
        return {
            "mission_action_id": self.mission_action_id,
            "mission_id": self.mission_id,
            "mission_kind": self.mission_kind,
            "scoring_source_id": self.scoring_source_id,
            "victory_points": self.victory_points,
            "cap_bucket": self.cap_bucket.value,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionActionScoringRulePayload) -> Self:
        return cls(
            mission_action_id=payload["mission_action_id"],
            mission_id=payload["mission_id"],
            mission_kind=payload["mission_kind"],
            scoring_source_id=payload["scoring_source_id"],
            victory_points=payload["victory_points"],
            cap_bucket=victory_point_cap_bucket_from_token(payload["cap_bucket"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ScoringWindowState:
    window_id: str
    game_id: str
    battle_round: int
    window_kind: ScoringWindowKind
    window: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _validate_identifier("ScoringWindowState window_id", self.window_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("ScoringWindowState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ScoringWindowState battle_round", self.battle_round),
        )
        object.__setattr__(self, "window_kind", scoring_window_kind_from_token(self.window_kind))
        object.__setattr__(
            self,
            "window",
            _validate_identifier("ScoringWindowState window", self.window),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ScoringWindowState source_id", self.source_id),
        )

    def to_payload(self) -> ScoringWindowStatePayload:
        return {
            "window_id": self.window_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "window_kind": self.window_kind.value,
            "window": self.window,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ScoringWindowStatePayload) -> Self:
        return cls(
            window_id=payload["window_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            window_kind=scoring_window_kind_from_token(payload["window_kind"]),
            window=payload["window"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class FinalScoreLine:
    player_id: str
    victory_points: int
    raw_victory_points: int
    raw_primary_vp: int
    raw_secondary_vp: int
    raw_battle_ready_vp: int
    raw_other_vp: int
    capped_primary_vp: int
    capped_secondary_vp: int
    capped_battle_ready_vp: int
    capped_other_vp: int
    cap_adjustment: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FinalScoreLine player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_non_negative_int("FinalScoreLine victory_points", self.victory_points),
        )
        object.__setattr__(
            self,
            "raw_victory_points",
            _validate_non_negative_int(
                "FinalScoreLine raw_victory_points", self.raw_victory_points
            ),
        )
        object.__setattr__(
            self,
            "raw_primary_vp",
            _validate_non_negative_int("FinalScoreLine raw_primary_vp", self.raw_primary_vp),
        )
        object.__setattr__(
            self,
            "raw_secondary_vp",
            _validate_non_negative_int("FinalScoreLine raw_secondary_vp", self.raw_secondary_vp),
        )
        object.__setattr__(
            self,
            "raw_battle_ready_vp",
            _validate_non_negative_int(
                "FinalScoreLine raw_battle_ready_vp", self.raw_battle_ready_vp
            ),
        )
        object.__setattr__(
            self,
            "raw_other_vp",
            _validate_non_negative_int("FinalScoreLine raw_other_vp", self.raw_other_vp),
        )
        object.__setattr__(
            self,
            "capped_primary_vp",
            _validate_non_negative_int("FinalScoreLine capped_primary_vp", self.capped_primary_vp),
        )
        object.__setattr__(
            self,
            "capped_secondary_vp",
            _validate_non_negative_int(
                "FinalScoreLine capped_secondary_vp", self.capped_secondary_vp
            ),
        )
        object.__setattr__(
            self,
            "capped_battle_ready_vp",
            _validate_non_negative_int(
                "FinalScoreLine capped_battle_ready_vp", self.capped_battle_ready_vp
            ),
        )
        object.__setattr__(
            self,
            "capped_other_vp",
            _validate_non_negative_int("FinalScoreLine capped_other_vp", self.capped_other_vp),
        )
        object.__setattr__(
            self,
            "cap_adjustment",
            _validate_non_negative_int("FinalScoreLine cap_adjustment", self.cap_adjustment),
        )
        capped_total = (
            self.capped_primary_vp
            + self.capped_secondary_vp
            + self.capped_battle_ready_vp
            + self.capped_other_vp
        )
        if capped_total != self.victory_points:
            raise GameLifecycleError("FinalScoreLine victory_points must match capped totals.")
        if self.raw_victory_points < self.victory_points:
            raise GameLifecycleError("FinalScoreLine raw_victory_points cannot be capped upward.")
        if self.raw_victory_points - self.victory_points != self.cap_adjustment:
            raise GameLifecycleError("FinalScoreLine cap_adjustment drift.")

    @classmethod
    def from_ledger(cls, *, ledger: VictoryPointLedger, policy: MissionScoringPolicy) -> Self:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("FinalScoreLine requires a VictoryPointLedger.")
        if type(policy) is not MissionScoringPolicy:
            raise GameLifecycleError("FinalScoreLine requires a MissionScoringPolicy.")
        raw_primary = policy.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=VictoryPointCapBucket.PRIMARY,
        )
        raw_secondary = policy.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=VictoryPointCapBucket.SECONDARY,
        )
        raw_battle_ready = policy.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=VictoryPointCapBucket.BATTLE_READY,
        )
        raw_other = ledger.victory_points - raw_primary - raw_secondary - raw_battle_ready
        if raw_other < 0:
            raise GameLifecycleError("FinalScoreLine source totals exceed raw ledger total.")
        capped_primary = min(raw_primary, policy.primary_vp_cap)
        capped_secondary = min(raw_secondary, policy.secondary_vp_cap)
        capped_battle_ready = min(raw_battle_ready, policy.battle_ready_vp)
        capped_pre_total = capped_primary + capped_secondary + capped_battle_ready + raw_other
        capped_total = min(capped_pre_total, policy.total_vp_cap)
        capped_other = capped_total - capped_primary - capped_secondary - capped_battle_ready
        if capped_other < 0:
            raise GameLifecycleError("FinalScoreLine total cap is below source-capped score.")
        return cls(
            player_id=ledger.player_id,
            victory_points=capped_total,
            raw_victory_points=ledger.victory_points,
            raw_primary_vp=raw_primary,
            raw_secondary_vp=raw_secondary,
            raw_battle_ready_vp=raw_battle_ready,
            raw_other_vp=raw_other,
            capped_primary_vp=capped_primary,
            capped_secondary_vp=capped_secondary,
            capped_battle_ready_vp=capped_battle_ready,
            capped_other_vp=capped_other,
            cap_adjustment=ledger.victory_points - capped_total,
        )

    def to_public_score_payload(self) -> FinalScorePayload:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
        }

    def to_payload(self) -> FinalScoreLinePayload:
        return {
            "player_id": self.player_id,
            "victory_points": self.victory_points,
            "raw_victory_points": self.raw_victory_points,
            "raw_primary_vp": self.raw_primary_vp,
            "raw_secondary_vp": self.raw_secondary_vp,
            "raw_battle_ready_vp": self.raw_battle_ready_vp,
            "raw_other_vp": self.raw_other_vp,
            "capped_primary_vp": self.capped_primary_vp,
            "capped_secondary_vp": self.capped_secondary_vp,
            "capped_battle_ready_vp": self.capped_battle_ready_vp,
            "capped_other_vp": self.capped_other_vp,
            "cap_adjustment": self.cap_adjustment,
        }

    @classmethod
    def from_payload(cls, payload: FinalScoreLinePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            victory_points=payload["victory_points"],
            raw_victory_points=payload["raw_victory_points"],
            raw_primary_vp=payload["raw_primary_vp"],
            raw_secondary_vp=payload["raw_secondary_vp"],
            raw_battle_ready_vp=payload["raw_battle_ready_vp"],
            raw_other_vp=payload["raw_other_vp"],
            capped_primary_vp=payload["capped_primary_vp"],
            capped_secondary_vp=payload["capped_secondary_vp"],
            capped_battle_ready_vp=payload["capped_battle_ready_vp"],
            capped_other_vp=payload["capped_other_vp"],
            cap_adjustment=payload["cap_adjustment"],
        )


@dataclass(frozen=True, slots=True)
class FinalScoringResult:
    result_id: str
    game_id: str
    battle_round: int
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    final_scores: tuple[FinalScoreLine, ...]
    winner_player_ids: tuple[str, ...]
    is_draw: bool
    policy_source_id: str
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp_cap: int
    total_vp_cap: int
    scoring_windows: tuple[ScoringWindowState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("FinalScoringResult result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("FinalScoringResult game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FinalScoringResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_identifier("FinalScoringResult mission_pack_id", self.mission_pack_id),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier("FinalScoringResult primary_mission_id", self.primary_mission_id),
        )
        object.__setattr__(
            self,
            "game_length_battle_rounds",
            _validate_positive_int(
                "FinalScoringResult game_length_battle_rounds",
                self.game_length_battle_rounds,
            ),
        )
        object.__setattr__(
            self,
            "final_scores",
            _validate_final_score_tuple(self.final_scores),
        )
        object.__setattr__(
            self,
            "winner_player_ids",
            _validate_identifier_tuple_ordered(
                "FinalScoringResult winner_player_ids",
                self.winner_player_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "is_draw",
            _validate_bool("FinalScoringResult is_draw", self.is_draw),
        )
        object.__setattr__(
            self,
            "policy_source_id",
            _validate_identifier("FinalScoringResult policy_source_id", self.policy_source_id),
        )
        object.__setattr__(
            self,
            "primary_vp_cap",
            _validate_positive_int("FinalScoringResult primary_vp_cap", self.primary_vp_cap),
        )
        object.__setattr__(
            self,
            "secondary_vp_cap",
            _validate_positive_int("FinalScoringResult secondary_vp_cap", self.secondary_vp_cap),
        )
        object.__setattr__(
            self,
            "battle_ready_vp_cap",
            _validate_non_negative_int(
                "FinalScoringResult battle_ready_vp_cap", self.battle_ready_vp_cap
            ),
        )
        object.__setattr__(
            self,
            "total_vp_cap",
            _validate_positive_int("FinalScoringResult total_vp_cap", self.total_vp_cap),
        )
        object.__setattr__(
            self,
            "scoring_windows",
            _validate_scoring_window_tuple(self.scoring_windows, game_id=self.game_id),
        )
        expected_winners = _winner_player_ids_from_scores(self.final_scores)
        if self.winner_player_ids != expected_winners:
            raise GameLifecycleError("FinalScoringResult winner_player_ids drift.")
        if self.is_draw != (len(expected_winners) != 1):
            raise GameLifecycleError("FinalScoringResult is_draw drift.")
        if self.battle_round != self.game_length_battle_rounds:
            raise GameLifecycleError("FinalScoringResult battle_round must match game length.")

    @classmethod
    def from_ledgers(
        cls,
        *,
        game_id: str,
        battle_round: int,
        policy: MissionScoringPolicy,
        ledgers: tuple[VictoryPointLedger, ...],
        scoring_windows: tuple[ScoringWindowState, ...],
    ) -> Self:
        if type(policy) is not MissionScoringPolicy:
            raise GameLifecycleError("Final scoring requires a MissionScoringPolicy.")
        requested_game_id = _validate_identifier("game_id", game_id)
        requested_round = _validate_positive_int("battle_round", battle_round)
        validated_windows = _validate_required_final_scoring_windows(
            scoring_windows=scoring_windows,
            policy=policy,
            game_id=requested_game_id,
            battle_round=requested_round,
        )
        final_scores = tuple(
            sorted(
                (FinalScoreLine.from_ledger(ledger=ledger, policy=policy) for ledger in ledgers),
                key=lambda score: score.player_id,
            )
        )
        if not final_scores:
            raise GameLifecycleError("Final scoring requires at least one player score.")
        winner_ids = _winner_player_ids_from_scores(final_scores)
        return cls(
            result_id=f"final-scoring:{requested_game_id}:round-{requested_round:02d}",
            game_id=requested_game_id,
            battle_round=requested_round,
            mission_pack_id=policy.mission_pack_id,
            primary_mission_id=policy.primary_mission_id,
            game_length_battle_rounds=policy.game_length_battle_rounds,
            final_scores=final_scores,
            winner_player_ids=winner_ids,
            is_draw=len(winner_ids) != 1,
            policy_source_id=policy.source_id,
            primary_vp_cap=policy.primary_vp_cap,
            secondary_vp_cap=policy.secondary_vp_cap,
            battle_ready_vp_cap=policy.battle_ready_vp,
            total_vp_cap=policy.total_vp_cap,
            scoring_windows=validated_windows,
        )

    def to_payload(self) -> FinalScoringResultPayload:
        return {
            "result_id": self.result_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "mission_pack_id": self.mission_pack_id,
            "primary_mission_id": self.primary_mission_id,
            "game_length_battle_rounds": self.game_length_battle_rounds,
            "final_scores": [score.to_public_score_payload() for score in self.final_scores],
            "winner_player_ids": list(self.winner_player_ids),
            "is_draw": self.is_draw,
            "scoring_audit": {
                "policy_source_id": self.policy_source_id,
                "primary_vp_cap": self.primary_vp_cap,
                "secondary_vp_cap": self.secondary_vp_cap,
                "battle_ready_vp_cap": self.battle_ready_vp_cap,
                "total_vp_cap": self.total_vp_cap,
                "scoring_windows": [window.to_payload() for window in self.scoring_windows],
                "player_scores": [score.to_payload() for score in self.final_scores],
            },
        }

    @classmethod
    def from_payload(cls, payload: FinalScoringResultPayload) -> Self:
        audit = payload["scoring_audit"]
        result = cls(
            result_id=payload["result_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            mission_pack_id=payload["mission_pack_id"],
            primary_mission_id=payload["primary_mission_id"],
            game_length_battle_rounds=payload["game_length_battle_rounds"],
            final_scores=tuple(
                FinalScoreLine.from_payload(score) for score in audit["player_scores"]
            ),
            winner_player_ids=tuple(payload["winner_player_ids"]),
            is_draw=payload["is_draw"],
            policy_source_id=audit["policy_source_id"],
            primary_vp_cap=audit["primary_vp_cap"],
            secondary_vp_cap=audit["secondary_vp_cap"],
            battle_ready_vp_cap=audit["battle_ready_vp_cap"],
            total_vp_cap=audit["total_vp_cap"],
            scoring_windows=tuple(
                ScoringWindowState.from_payload(window) for window in audit["scoring_windows"]
            ),
        )
        if [score.to_public_score_payload() for score in result.final_scores] != payload[
            "final_scores"
        ]:
            raise GameLifecycleError("FinalScoringResult final_scores drift from scoring audit.")
        return result


@dataclass(frozen=True, slots=True)
class MissionScoringPolicy:
    mission_pack_id: str
    primary_mission_id: str
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: ObjectiveControlTiming
    primary_scoring_rule_id: str | None
    primary_scoring_rule_condition: str | None
    primary_scoring_rule_source_id: str | None
    primary_vp_per_controlled_objective: int | None
    primary_max_vp_per_turn: int | None
    primary_scoring_rules: tuple[PrimaryMissionScoringRule, ...]
    secondary_vp_per_score: int
    secondary_scoring_rules: tuple[SecondaryMissionScoringRule, ...]
    mission_action_scoring_rules: tuple[MissionActionScoringRule, ...]
    mission_action_vp: int
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
    end_of_round_scoring_windows: tuple[str, ...]
    end_of_game_scoring_windows: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_identifier("MissionScoringPolicy mission_pack_id", self.mission_pack_id),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier(
                "MissionScoringPolicy primary_mission_id",
                self.primary_mission_id,
            ),
        )
        object.__setattr__(
            self,
            "game_length_battle_rounds",
            _validate_positive_int(
                "MissionScoringPolicy game_length_battle_rounds",
                self.game_length_battle_rounds,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_phase",
            _validate_identifier(
                "MissionScoringPolicy primary_scoring_phase",
                self.primary_scoring_phase,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_timing",
            objective_control_timing_from_token(self.primary_scoring_timing),
        )
        object.__setattr__(
            self,
            "primary_scoring_rule_id",
            _validate_optional_identifier(
                "MissionScoringPolicy primary_scoring_rule_id",
                self.primary_scoring_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_rule_condition",
            _validate_optional_identifier(
                "MissionScoringPolicy primary_scoring_rule_condition",
                self.primary_scoring_rule_condition,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_rule_source_id",
            _validate_optional_identifier(
                "MissionScoringPolicy primary_scoring_rule_source_id",
                self.primary_scoring_rule_source_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_vp_per_controlled_objective",
            _validate_optional_positive_int(
                "MissionScoringPolicy primary_vp_per_controlled_objective",
                self.primary_vp_per_controlled_objective,
            ),
        )
        object.__setattr__(
            self,
            "primary_max_vp_per_turn",
            _validate_optional_positive_int(
                "MissionScoringPolicy primary_max_vp_per_turn",
                self.primary_max_vp_per_turn,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_rules",
            _validate_primary_scoring_rule_tuple(self.primary_scoring_rules),
        )
        object.__setattr__(
            self,
            "secondary_vp_per_score",
            _validate_positive_int(
                "MissionScoringPolicy secondary_vp_per_score",
                self.secondary_vp_per_score,
            ),
        )
        object.__setattr__(
            self,
            "secondary_scoring_rules",
            _validate_secondary_scoring_rule_tuple(self.secondary_scoring_rules),
        )
        object.__setattr__(
            self,
            "mission_action_scoring_rules",
            _validate_mission_action_scoring_rule_tuple(self.mission_action_scoring_rules),
        )
        object.__setattr__(
            self,
            "mission_action_vp",
            _validate_positive_int(
                "MissionScoringPolicy mission_action_vp", self.mission_action_vp
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_timing",
            _validate_identifier(
                "MissionScoringPolicy reserve_destruction_timing",
                self.reserve_destruction_timing,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_battle_round",
            _validate_optional_positive_int(
                "MissionScoringPolicy reserve_destruction_battle_round",
                self.reserve_destruction_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_excludes_during_battle_strategic_reserves",
            _validate_bool(
                "MissionScoringPolicy "
                "reserve_destruction_excludes_during_battle_strategic_reserves",
                self.reserve_destruction_excludes_during_battle_strategic_reserves,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_only_declare_battle_formations",
            _validate_bool(
                "MissionScoringPolicy reserve_destruction_only_declare_battle_formations",
                self.reserve_destruction_only_declare_battle_formations,
            ),
        )
        object.__setattr__(
            self,
            "primary_vp_cap",
            _validate_positive_int("MissionScoringPolicy primary_vp_cap", self.primary_vp_cap),
        )
        object.__setattr__(
            self,
            "secondary_vp_cap",
            _validate_positive_int(
                "MissionScoringPolicy secondary_vp_cap",
                self.secondary_vp_cap,
            ),
        )
        object.__setattr__(
            self,
            "battle_ready_vp",
            _validate_non_negative_int(
                "MissionScoringPolicy battle_ready_vp",
                self.battle_ready_vp,
            ),
        )
        object.__setattr__(
            self,
            "total_vp_cap",
            _validate_positive_int("MissionScoringPolicy total_vp_cap", self.total_vp_cap),
        )
        object.__setattr__(
            self,
            "end_of_round_scoring_windows",
            _validate_identifier_tuple_ordered(
                "MissionScoringPolicy end_of_round_scoring_windows",
                self.end_of_round_scoring_windows,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "end_of_game_scoring_windows",
            _validate_identifier_tuple_ordered(
                "MissionScoringPolicy end_of_game_scoring_windows",
                self.end_of_game_scoring_windows,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionScoringPolicy source_id", self.source_id),
        )

    def primary_awards_from_objective_control(
        self,
        *,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        scoring_player_ids: tuple[str, ...] = (),
        end_of_battle: bool = False,
    ) -> tuple[VictoryPointAward, ...]:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("Primary scoring requires an ObjectiveControlRecord.")
        if type(mission_setup) is not MissionSetup:
            raise GameLifecycleError("Primary scoring requires MissionSetup.")
        starts = _validate_primary_turn_start_state_tuple(turn_start_states)
        traps = _validate_primary_terrain_trap_state_tuple(terrain_trap_states)
        destructions = _validate_primary_unit_destruction_state_tuple(unit_destruction_states)
        player_ids = (
            _validate_identifier_tuple("scoring_player_ids", scoring_player_ids)
            if scoring_player_ids
            else (record.active_player_id,)
        )
        awards: list[VictoryPointAward] = []
        for rule in self.primary_scoring_rules:
            if not self._primary_rule_applies_at_record(
                rule=rule,
                record=record,
                end_of_battle=end_of_battle,
            ):
                continue
            for player_id in player_ids:
                award = self._primary_award_for_rule(
                    rule=rule,
                    record=record,
                    mission_setup=mission_setup,
                    player_id=player_id,
                    turn_start_states=starts,
                    terrain_trap_states=traps,
                    unit_destruction_states=destructions,
                    end_of_battle=end_of_battle,
                )
                if award is not None:
                    awards.append(award)
        return tuple(awards)

    def _primary_rule_applies_at_record(
        self,
        *,
        rule: PrimaryMissionScoringRule,
        record: ObjectiveControlRecord,
        end_of_battle: bool,
    ) -> bool:
        if end_of_battle:
            return rule.timing == "end_of_battle"
        if rule.timing == "end_of_battle":
            return False
        if rule.timing == "command_phase":
            return record.phase == self.primary_scoring_phase and (
                record.timing is self.primary_scoring_timing
            )
        if rule.timing == "turn_end":
            return record.timing is ObjectiveControlTiming.TURN_END
        if rule.timing == "command_phase_or_round_five_turn_end":
            return (
                record.phase == self.primary_scoring_phase
                and record.timing is self.primary_scoring_timing
            ) or (
                record.battle_round == self.game_length_battle_rounds
                and record.timing is ObjectiveControlTiming.TURN_END
            )
        raise GameLifecycleError("Unsupported primary scoring rule timing.")

    def _primary_award_for_rule(
        self,
        *,
        rule: PrimaryMissionScoringRule,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        player_id: str,
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        end_of_battle: bool,
    ) -> VictoryPointAward | None:
        evidence = self._primary_rule_evidence(
            rule=rule,
            record=record,
            mission_setup=mission_setup,
            player_id=player_id,
            turn_start_states=turn_start_states,
            terrain_trap_states=terrain_trap_states,
            unit_destruction_states=unit_destruction_states,
            end_of_battle=end_of_battle,
        )
        score_count = _metadata_score_count(evidence)
        if score_count == 0:
            return None
        amount = score_count * rule.victory_points
        if rule.cap is not None:
            amount = min(amount, rule.cap)
        return VictoryPointAward(
            player_id=player_id,
            battle_round=record.battle_round,
            phase=record.phase,
            amount=amount,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=self.primary_mission_id,
            scoring_timing="end_of_battle" if end_of_battle else record.timing.value,
            hidden=False,
            metadata={
                **evidence,
                "objective_control_record_id": record.record_id,
                "scoring_rule_id": rule.rule_id,
                "scoring_rule_condition": rule.condition,
                "scoring_rule_source_id": rule.source_id,
                "victory_points_per_count": rule.victory_points,
            },
        )

    def _primary_rule_evidence(
        self,
        *,
        rule: PrimaryMissionScoringRule,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        player_id: str,
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        end_of_battle: bool,
    ) -> dict[str, JsonValue]:
        requested_player = _validate_identifier("player_id", player_id)
        controlled_objective_ids = _controlled_objective_ids(record, player_id=requested_player)
        home_objective_ids = _home_objective_ids(mission_setup, player_id=requested_player)
        central_objective_ids = _central_objective_ids(mission_setup)
        non_home_objective_ids = tuple(
            objective_id
            for objective_id in controlled_objective_ids
            if objective_id not in home_objective_ids
        )
        if rule.condition == "each_controlled_objective":
            return _score_count_evidence(
                score_count=len(controlled_objective_ids),
                controlled_objective_ids=controlled_objective_ids,
            )
        if rule.condition == "each_controlled_objective_from_battle_round_two":
            if record.battle_round < 2:
                return _score_count_evidence(score_count=0)
            return _score_count_evidence(
                score_count=len(controlled_objective_ids),
                controlled_objective_ids=controlled_objective_ids,
            )
        if rule.condition == "control_one_or_more_central_objectives":
            central_ids = tuple(
                objective_id
                for objective_id in controlled_objective_ids
                if objective_id in central_objective_ids
            )
            return _score_count_evidence(
                score_count=1 if central_ids else 0,
                controlled_objective_ids=central_ids,
            )
        if rule.condition == "each_non_home_objective_controlled_battle_rounds_two_to_four":
            if record.battle_round < 2 or record.battle_round > 4:
                return _score_count_evidence(score_count=0)
            return _score_count_evidence(
                score_count=len(non_home_objective_ids),
                controlled_objective_ids=non_home_objective_ids,
                home_objective_ids=home_objective_ids,
            )
        if rule.condition == "each_non_home_objective_controlled_round_five":
            if record.battle_round != self.game_length_battle_rounds:
                return _score_count_evidence(score_count=0)
            return _score_count_evidence(
                score_count=len(non_home_objective_ids),
                controlled_objective_ids=non_home_objective_ids,
                home_objective_ids=home_objective_ids,
            )
        if rule.condition == "one_or_more_enemy_units_destroyed_this_turn":
            matching = _enemy_unit_destructions_this_turn(
                unit_destruction_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            return _score_count_evidence(
                score_count=1 if matching else 0,
                destroyed_unit_instance_ids=tuple(
                    state.destroyed_unit_instance_id for state in matching
                ),
            )
        if rule.condition == "each_non_home_objective_controlled_from_battle_round_two":
            if record.battle_round < 2:
                return _score_count_evidence(score_count=0)
            return _score_count_evidence(
                score_count=len(non_home_objective_ids),
                controlled_objective_ids=non_home_objective_ids,
                home_objective_ids=home_objective_ids,
            )
        if rule.condition == "control_one_or_more_new_non_home_objectives":
            start_state = _turn_start_state_for_player(
                turn_start_states,
                game_id=record.game_id,
                player_id=requested_player,
                battle_round=record.battle_round,
            )
            new_ids = tuple(
                objective_id
                for objective_id in non_home_objective_ids
                if objective_id not in start_state.controlled_objective_ids
            )
            return _score_count_evidence(
                score_count=1 if new_ids else 0,
                controlled_objective_ids=new_ids,
                turn_start_controlled_objective_ids=start_state.controlled_objective_ids,
            )
        if rule.condition == "control_one_or_more_central_objectives_end_of_battle":
            if not end_of_battle:
                return _score_count_evidence(score_count=0)
            central_ids = tuple(
                objective_id
                for objective_id in controlled_objective_ids
                if objective_id in central_objective_ids
            )
            return _score_count_evidence(
                score_count=1 if central_ids else 0,
                controlled_objective_ids=central_ids,
            )
        if rule.condition == "each_terrain_area_trapped_this_turn":
            traps = _terrain_traps_this_turn(
                terrain_trap_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            return _score_count_evidence(
                score_count=len(traps),
                trapped_terrain_feature_ids=tuple(trap.terrain_feature_id for trap in traps),
            )
        if rule.condition == "each_trapped_objective_terrain_area_this_turn":
            traps = tuple(
                trap
                for trap in _terrain_traps_this_turn(
                    terrain_trap_states,
                    player_id=requested_player,
                    battle_round=record.battle_round,
                    active_player_id=record.active_player_id,
                )
                if trap.is_objective
            )
            return _score_count_evidence(
                score_count=len(traps),
                trapped_terrain_feature_ids=tuple(trap.terrain_feature_id for trap in traps),
            )
        if (
            rule.condition
            == "one_or_more_enemy_units_destroyed_after_starting_turn_in_trapped_terrain"
        ):
            trap_ids = {
                trap.terrain_feature_id
                for trap in terrain_trap_states
                if trap.player_id == requested_player
            }
            matching = tuple(
                destruction
                for destruction in _enemy_unit_destructions_this_turn(
                    unit_destruction_states,
                    player_id=requested_player,
                    battle_round=record.battle_round,
                    active_player_id=record.active_player_id,
                )
                if trap_ids.intersection(destruction.started_turn_terrain_feature_ids)
            )
            return _score_count_evidence(
                score_count=1 if matching else 0,
                destroyed_unit_instance_ids=tuple(
                    state.destroyed_unit_instance_id for state in matching
                ),
                trapped_terrain_feature_ids=tuple(sorted(trap_ids)),
            )
        if rule.condition == "control_one_or_more_non_home_objectives_from_battle_round_two":
            if record.battle_round < 2:
                return _score_count_evidence(score_count=0)
            return _score_count_evidence(
                score_count=1 if non_home_objective_ids else 0,
                controlled_objective_ids=non_home_objective_ids,
                home_objective_ids=home_objective_ids,
            )
        raise GameLifecycleError("Unsupported primary scoring rule condition.")

    def secondary_award(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: str,
        secondary_mission_id: str,
        source_kind: VictoryPointSourceKind,
        hidden: bool,
    ) -> VictoryPointAward:
        kind = victory_point_source_kind_from_token(source_kind)
        if kind not in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            raise GameLifecycleError("Secondary scoring requires a secondary source kind.")
        requested_secondary_id = _validate_identifier("secondary_mission_id", secondary_mission_id)
        rule = self._secondary_scoring_rule(
            secondary_mission_id=requested_secondary_id,
            source_kind=kind,
        )
        return VictoryPointAward(
            player_id=_validate_identifier("player_id", player_id),
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=rule.victory_points,
            source_kind=kind,
            source_id=requested_secondary_id,
            scoring_timing="secondary_mission_score",
            hidden=hidden,
            metadata={
                "secondary_mission_id": requested_secondary_id,
                "scoring_rule_id": rule.rule_id,
                "scoring_rule_condition": rule.condition,
                "scoring_rule_source_id": rule.source_id,
            },
        )

    def secondary_award_from_mission_state(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: str,
        secondary_mission_id: str,
        source_kind: VictoryPointSourceKind,
        hidden: bool,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        unit_destruction_states: tuple[SecondaryUnitDestructionState, ...],
        objective_cleanse_states: tuple[SecondaryObjectiveCleanseState, ...],
        terrain_plunder_states: tuple[SecondaryTerrainPlunderState, ...],
        enemy_unit_ids_in_player_deployment_zone: tuple[str, ...],
        starting_strength_records: tuple[StartingStrengthRecord, ...] = (),
    ) -> VictoryPointAward | None:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("State-backed secondary scoring requires objective record.")
        if type(mission_setup) is not MissionSetup:
            raise GameLifecycleError("State-backed secondary scoring requires MissionSetup.")
        requested_player = _validate_identifier("player_id", player_id)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_phase = _validate_identifier("phase", phase)
        requested_secondary = _validate_identifier("secondary_mission_id", secondary_mission_id)
        kind = victory_point_source_kind_from_token(source_kind)
        if kind not in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            raise GameLifecycleError("State-backed secondary scoring requires secondary kind.")
        destructions = _validate_secondary_unit_destruction_state_tuple(unit_destruction_states)
        cleanses = _validate_secondary_objective_cleanse_state_tuple(objective_cleanse_states)
        plunders = _validate_secondary_terrain_plunder_state_tuple(terrain_plunder_states)
        starting_strength_by_unit_id = _starting_strength_record_by_unit_id(
            starting_strength_records
        )
        enemy_zone_unit_ids = _validate_identifier_tuple(
            "enemy_unit_ids_in_player_deployment_zone",
            enemy_unit_ids_in_player_deployment_zone,
        )
        if record.battle_round != requested_round or record.phase != requested_phase:
            raise GameLifecycleError("State-backed secondary scoring record timing drift.")
        matching_rules = tuple(
            rule
            for rule in self.secondary_scoring_rules
            if rule.secondary_mission_id == requested_secondary
            and rule.source_kind is kind
            and self._secondary_rule_applies_at_record(
                rule=rule,
                record=record,
                player_id=player_id,
            )
        )
        if not matching_rules:
            raise GameLifecycleError("State-backed secondary scoring rule is not source-backed.")

        total = 0
        rule_ids: list[str] = []
        rule_conditions: list[str] = []
        rule_source_ids: list[str] = []
        score_count_by_rule: dict[str, int] = {}
        victory_points_by_rule: dict[str, int] = {}
        evidence_by_rule: dict[str, JsonValue] = {}
        for rule in matching_rules:
            evidence = self._secondary_rule_evidence(
                rule=rule,
                record=record,
                mission_setup=mission_setup,
                player_id=requested_player,
                unit_destruction_states=destructions,
                objective_cleanse_states=cleanses,
                terrain_plunder_states=plunders,
                enemy_unit_ids_in_player_deployment_zone=enemy_zone_unit_ids,
                starting_strength_by_unit_id=starting_strength_by_unit_id,
            )
            score_count = _metadata_score_count(evidence)
            if score_count == 0:
                continue
            amount = score_count * rule.victory_points
            if rule.cap is not None:
                amount = min(amount, rule.cap)
            total += amount
            rule_ids.append(rule.rule_id)
            rule_conditions.append(rule.condition)
            rule_source_ids.append(rule.source_id)
            score_count_by_rule[rule.rule_id] = score_count
            victory_points_by_rule[rule.rule_id] = amount
            evidence_by_rule[rule.rule_id] = validate_json_value(evidence)
        if total == 0:
            return None
        return VictoryPointAward(
            player_id=requested_player,
            battle_round=requested_round,
            phase=requested_phase,
            amount=total,
            source_kind=kind,
            source_id=requested_secondary,
            scoring_timing=record.timing.value,
            hidden=hidden,
            metadata=validate_json_value(
                {
                    "secondary_mission_id": requested_secondary,
                    "objective_control_record_id": record.record_id,
                    "scoring_rule_ids": rule_ids,
                    "scoring_rule_conditions": rule_conditions,
                    "scoring_rule_source_ids": rule_source_ids,
                    "score_count_by_rule": score_count_by_rule,
                    "victory_points_by_rule": victory_points_by_rule,
                    "evidence_by_rule": evidence_by_rule,
                }
            ),
        )

    def _secondary_rule_applies_at_record(
        self,
        *,
        rule: SecondaryMissionScoringRule,
        record: ObjectiveControlRecord,
        player_id: str,
    ) -> bool:
        requested_player = _validate_identifier("player_id", player_id)
        if rule.timing == "mission_condition_met":
            return True
        if rule.timing == "turn_end":
            return record.timing is ObjectiveControlTiming.TURN_END
        if rule.timing == "your_turn_end":
            return (
                record.timing is ObjectiveControlTiming.TURN_END
                and record.active_player_id == requested_player
            )
        if rule.timing == "opponent_turn_end_or_round_five_turn_end":
            return record.timing is ObjectiveControlTiming.TURN_END and (
                record.active_player_id != requested_player
                or record.battle_round == self.game_length_battle_rounds
            )
        raise GameLifecycleError("Unsupported secondary scoring rule timing.")

    def _secondary_rule_evidence(
        self,
        *,
        rule: SecondaryMissionScoringRule,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        player_id: str,
        unit_destruction_states: tuple[SecondaryUnitDestructionState, ...],
        objective_cleanse_states: tuple[SecondaryObjectiveCleanseState, ...],
        terrain_plunder_states: tuple[SecondaryTerrainPlunderState, ...],
        enemy_unit_ids_in_player_deployment_zone: tuple[str, ...],
        starting_strength_by_unit_id: dict[str, StartingStrengthRecord],
    ) -> dict[str, JsonValue]:
        requested_player = _validate_identifier("player_id", player_id)
        controlled_objective_ids = _controlled_objective_ids(record, player_id=requested_player)
        home_objective_ids = _home_objective_ids(mission_setup, player_id=requested_player)
        central_objective_ids = _central_objective_ids(mission_setup)
        if rule.condition == "each_enemy_model_w10_or_more_destroyed_this_turn":
            matching = _secondary_enemy_unit_destructions_this_turn(
                unit_destruction_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            model_ids = tuple(
                model.model_instance_id
                for state in matching
                for model in state.destroyed_models
                if model.starting_wounds >= 10
            )
            return _secondary_score_count_evidence(
                score_count=len(model_ids),
                destroyed_unit_instance_ids=tuple(
                    state.destroyed_unit_instance_id for state in matching
                ),
                destroyed_model_instance_ids=model_ids,
            )
        if rule.condition == "each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn":
            matching = tuple(
                state
                for state in _secondary_enemy_unit_destructions_this_turn(
                    unit_destruction_states,
                    player_id=requested_player,
                    battle_round=record.battle_round,
                    active_player_id=record.active_player_id,
                )
                if _starting_strength_for_destroyed_unit(
                    state.destroyed_unit_instance_id,
                    starting_strength_by_unit_id=starting_strength_by_unit_id,
                )
                >= 13
            )
            return _secondary_score_count_evidence(
                score_count=len(matching),
                destroyed_unit_instance_ids=tuple(
                    state.destroyed_unit_instance_id for state in matching
                ),
            )
        if rule.condition == "each_enemy_unit_destroyed_this_turn":
            matching = _secondary_enemy_unit_destructions_this_turn(
                unit_destruction_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            return _secondary_score_count_evidence(
                score_count=len(matching),
                destroyed_unit_instance_ids=tuple(
                    state.destroyed_unit_instance_id for state in matching
                ),
            )
        if rule.condition == "control_home_objective":
            controlled_home_ids = tuple(
                objective_id
                for objective_id in controlled_objective_ids
                if objective_id in home_objective_ids
            )
            return _secondary_score_count_evidence(
                score_count=1 if controlled_home_ids else 0,
                controlled_objective_ids=controlled_home_ids,
                home_objective_ids=home_objective_ids,
            )
        if rule.condition == "no_enemy_units_within_own_deployment_zone":
            return _secondary_score_count_evidence(
                score_count=0 if enemy_unit_ids_in_player_deployment_zone else 1,
                enemy_unit_instance_ids=enemy_unit_ids_in_player_deployment_zone,
            )
        if rule.condition == "each_enemy_unit_started_turn_in_range_of_objective_destroyed":
            matching = tuple(
                state
                for state in _secondary_enemy_unit_destructions_this_turn(
                    unit_destruction_states,
                    player_id=requested_player,
                    battle_round=record.battle_round,
                    active_player_id=record.active_player_id,
                )
                if state.started_turn_objective_marker_ids
            )
            objective_ids = tuple(
                sorted(
                    {
                        objective_id
                        for state in matching
                        for objective_id in state.started_turn_objective_marker_ids
                    }
                )
            )
            return _secondary_score_count_evidence(
                score_count=len(matching),
                destroyed_unit_instance_ids=tuple(
                    state.destroyed_unit_instance_id for state in matching
                ),
                objective_marker_ids=objective_ids,
            )
        if rule.condition == "control_two_or_more_no_mans_land_objectives_excluding_home":
            no_mans_land_objective_ids = tuple(
                objective_id
                for objective_id in controlled_objective_ids
                if objective_id in central_objective_ids
            )
            return _secondary_score_count_evidence(
                score_count=1 if len(no_mans_land_objective_ids) >= 2 else 0,
                controlled_objective_ids=no_mans_land_objective_ids,
                home_objective_ids=home_objective_ids,
            )
        if rule.condition == "one_or_more_objectives_cleansed_this_turn":
            cleanses = _secondary_objective_cleanses_this_turn(
                objective_cleanse_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            return _secondary_score_count_evidence(
                score_count=1 if cleanses else 0,
                objective_marker_ids=tuple(state.objective_marker_id for state in cleanses),
            )
        if rule.condition == "two_or_more_objectives_cleansed_this_turn":
            cleanses = _secondary_objective_cleanses_this_turn(
                objective_cleanse_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            return _secondary_score_count_evidence(
                score_count=1 if len(cleanses) >= 2 else 0,
                objective_marker_ids=tuple(state.objective_marker_id for state in cleanses),
            )
        if rule.condition == "one_or_more_terrain_areas_plundered_this_turn":
            plunders = _secondary_terrain_plunders_this_turn(
                terrain_plunder_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            return _secondary_score_count_evidence(
                score_count=1 if plunders else 0,
                terrain_feature_ids=tuple(state.terrain_feature_id for state in plunders),
            )
        if rule.condition in {"fixed_secondary_condition", "tactical_secondary_condition"}:
            return _secondary_score_count_evidence(score_count=1)
        raise GameLifecycleError("Unsupported secondary scoring rule condition.")

    def mission_action_award(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: str,
        action_id: str,
        source_id: str,
        amount: int | None = None,
    ) -> VictoryPointAward:
        source_rule = self._mission_action_scoring_rule_for_source_id(source_id)
        requested_amount = (
            source_rule.victory_points
            if amount is None
            else _validate_positive_int("amount", amount)
        )
        return VictoryPointAward(
            player_id=_validate_identifier("player_id", player_id),
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=requested_amount,
            source_kind=VictoryPointSourceKind.MISSION_ACTION,
            source_id=source_rule.scoring_source_id,
            scoring_timing="mission_action_complete",
            hidden=False,
            metadata={"action_id": _validate_identifier("action_id", action_id)},
        )

    def capped_award_for_ledger(
        self,
        *,
        ledger: VictoryPointLedger,
        award: VictoryPointAward,
    ) -> tuple[int, JsonValue]:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("VP cap resolution requires a VictoryPointLedger.")
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("VP cap resolution requires a VictoryPointAward.")
        if ledger.player_id != award.player_id:
            raise GameLifecycleError("VP cap resolution player_id drift.")

        cap_bucket = self.cap_bucket_for_victory_point_source(
            source_kind=award.source_kind,
            source_id=award.source_id,
        )
        source_points_before = self.ledger_points_from_cap_bucket(
            ledger=ledger,
            cap_bucket=cap_bucket,
        )
        source_cap = self._source_cap_for_bucket(cap_bucket)
        source_remaining = max(source_cap - source_points_before, 0)
        fixed_secondary_points_before = 0
        fixed_secondary_remaining = award.amount
        fixed_secondary_cap = None
        if award.source_kind is VictoryPointSourceKind.FIXED_SECONDARY:
            fixed_secondary_cap = FIXED_SECONDARY_MISSION_VP_CAP
            fixed_secondary_points_before = _ledger_points_from_source(
                ledger=ledger,
                source_kind=award.source_kind,
                source_id=award.source_id,
            )
            fixed_secondary_remaining = max(
                fixed_secondary_cap - fixed_secondary_points_before,
                0,
            )
        total_remaining = max(self.total_vp_cap - ledger.victory_points, 0)
        applied_amount = min(
            award.amount,
            source_remaining,
            fixed_secondary_remaining,
            total_remaining,
        )
        if applied_amount == award.amount:
            return applied_amount, award.metadata

        capped_reasons: list[str] = []
        if source_remaining < award.amount:
            capped_reasons.append(self._source_cap_reason(cap_bucket))
        if fixed_secondary_remaining < award.amount:
            capped_reasons.append("fixed_secondary_mission_vp_cap")
        if total_remaining < award.amount:
            capped_reasons.append("total_vp_cap")
        return (
            applied_amount,
            _metadata_with_vp_cap_audit(
                award.metadata,
                requested_amount=award.amount,
                applied_amount=applied_amount,
                source_cap=source_cap,
                source_points_before=source_points_before,
                source_points_after=source_points_before + applied_amount,
                total_cap=self.total_vp_cap,
                total_points_before=ledger.victory_points,
                total_points_after=ledger.victory_points + applied_amount,
                capped_reasons=tuple(capped_reasons),
                fixed_secondary_mission_cap=fixed_secondary_cap,
                fixed_secondary_mission_points_before=fixed_secondary_points_before,
                fixed_secondary_mission_points_after=(
                    fixed_secondary_points_before + applied_amount
                ),
            ),
        )

    def to_payload(self) -> MissionScoringPolicyPayload:
        return {
            "mission_pack_id": self.mission_pack_id,
            "primary_mission_id": self.primary_mission_id,
            "game_length_battle_rounds": self.game_length_battle_rounds,
            "primary_scoring_phase": self.primary_scoring_phase,
            "primary_scoring_timing": self.primary_scoring_timing.value,
            "primary_scoring_rule_id": self.primary_scoring_rule_id,
            "primary_scoring_rule_condition": self.primary_scoring_rule_condition,
            "primary_scoring_rule_source_id": self.primary_scoring_rule_source_id,
            "primary_vp_per_controlled_objective": self.primary_vp_per_controlled_objective,
            "primary_max_vp_per_turn": self.primary_max_vp_per_turn,
            "primary_scoring_rules": [rule.to_payload() for rule in self.primary_scoring_rules],
            "secondary_vp_per_score": self.secondary_vp_per_score,
            "secondary_scoring_rules": [rule.to_payload() for rule in self.secondary_scoring_rules],
            "mission_action_scoring_rules": [
                rule.to_payload() for rule in self.mission_action_scoring_rules
            ],
            "mission_action_vp": self.mission_action_vp,
            "reserve_destruction_timing": self.reserve_destruction_timing,
            "reserve_destruction_battle_round": self.reserve_destruction_battle_round,
            "reserve_destruction_excludes_during_battle_strategic_reserves": (
                self.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            "reserve_destruction_only_declare_battle_formations": (
                self.reserve_destruction_only_declare_battle_formations
            ),
            "primary_vp_cap": self.primary_vp_cap,
            "secondary_vp_cap": self.secondary_vp_cap,
            "battle_ready_vp": self.battle_ready_vp,
            "total_vp_cap": self.total_vp_cap,
            "end_of_round_scoring_windows": list(self.end_of_round_scoring_windows),
            "end_of_game_scoring_windows": list(self.end_of_game_scoring_windows),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionScoringPolicyPayload) -> Self:
        return cls(
            mission_pack_id=payload["mission_pack_id"],
            primary_mission_id=payload["primary_mission_id"],
            game_length_battle_rounds=payload["game_length_battle_rounds"],
            primary_scoring_phase=payload["primary_scoring_phase"],
            primary_scoring_timing=objective_control_timing_from_token(
                payload["primary_scoring_timing"]
            ),
            primary_scoring_rule_id=payload["primary_scoring_rule_id"],
            primary_scoring_rule_condition=payload["primary_scoring_rule_condition"],
            primary_scoring_rule_source_id=payload["primary_scoring_rule_source_id"],
            primary_vp_per_controlled_objective=payload["primary_vp_per_controlled_objective"],
            primary_max_vp_per_turn=payload["primary_max_vp_per_turn"],
            primary_scoring_rules=tuple(
                PrimaryMissionScoringRule.from_payload(rule)
                for rule in payload["primary_scoring_rules"]
            ),
            secondary_vp_per_score=payload["secondary_vp_per_score"],
            secondary_scoring_rules=tuple(
                SecondaryMissionScoringRule.from_payload(rule)
                for rule in payload["secondary_scoring_rules"]
            ),
            mission_action_scoring_rules=tuple(
                MissionActionScoringRule.from_payload(rule)
                for rule in payload["mission_action_scoring_rules"]
            ),
            mission_action_vp=payload["mission_action_vp"],
            reserve_destruction_timing=payload["reserve_destruction_timing"],
            reserve_destruction_battle_round=payload["reserve_destruction_battle_round"],
            reserve_destruction_excludes_during_battle_strategic_reserves=payload[
                "reserve_destruction_excludes_during_battle_strategic_reserves"
            ],
            reserve_destruction_only_declare_battle_formations=payload[
                "reserve_destruction_only_declare_battle_formations"
            ],
            primary_vp_cap=payload["primary_vp_cap"],
            secondary_vp_cap=payload["secondary_vp_cap"],
            battle_ready_vp=payload["battle_ready_vp"],
            total_vp_cap=payload["total_vp_cap"],
            end_of_round_scoring_windows=tuple(payload["end_of_round_scoring_windows"]),
            end_of_game_scoring_windows=tuple(payload["end_of_game_scoring_windows"]),
            source_id=payload["source_id"],
        )

    def cap_bucket_for_victory_point_source(
        self,
        *,
        source_kind: VictoryPointSourceKind,
        source_id: str,
    ) -> VictoryPointCapBucket:
        kind = victory_point_source_kind_from_token(source_kind)
        if kind is VictoryPointSourceKind.PRIMARY:
            return VictoryPointCapBucket.PRIMARY
        if kind in {
            VictoryPointSourceKind.FIXED_SECONDARY,
            VictoryPointSourceKind.TACTICAL_SECONDARY,
        }:
            return VictoryPointCapBucket.SECONDARY
        if kind is VictoryPointSourceKind.MISSION_ACTION:
            return self._mission_action_scoring_rule_for_source_id(source_id).cap_bucket
        if kind is VictoryPointSourceKind.BATTLE_READY:
            return VictoryPointCapBucket.BATTLE_READY
        raise GameLifecycleError("Unsupported VictoryPointSourceKind for cap policy.")

    def ledger_points_from_cap_bucket(
        self,
        *,
        ledger: VictoryPointLedger,
        cap_bucket: VictoryPointCapBucket,
    ) -> int:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("VP cap bucket accounting requires a VictoryPointLedger.")
        requested_bucket = victory_point_cap_bucket_from_token(cap_bucket)
        return sum(
            transaction.amount
            for transaction in ledger.transactions
            if self.cap_bucket_for_victory_point_source(
                source_kind=transaction.source_kind,
                source_id=transaction.source_id,
            )
            is requested_bucket
        )

    def _source_cap_for_bucket(self, cap_bucket: VictoryPointCapBucket) -> int:
        bucket = victory_point_cap_bucket_from_token(cap_bucket)
        if bucket is VictoryPointCapBucket.PRIMARY:
            return self.primary_vp_cap
        if bucket is VictoryPointCapBucket.SECONDARY:
            return self.secondary_vp_cap
        if bucket is VictoryPointCapBucket.BATTLE_READY:
            return self.battle_ready_vp
        raise GameLifecycleError("Unsupported VictoryPointCapBucket for cap policy.")

    def _source_cap_reason(self, cap_bucket: VictoryPointCapBucket) -> str:
        bucket = victory_point_cap_bucket_from_token(cap_bucket)
        if bucket is VictoryPointCapBucket.PRIMARY:
            return "primary_vp_cap"
        if bucket is VictoryPointCapBucket.SECONDARY:
            return "secondary_vp_cap"
        if bucket is VictoryPointCapBucket.BATTLE_READY:
            return "battle_ready_vp_cap"
        raise GameLifecycleError("Unsupported VictoryPointCapBucket for cap policy.")

    def _mission_action_scoring_rule_for_source_id(
        self,
        source_id: str,
    ) -> MissionActionScoringRule:
        requested_source_id = _validate_identifier("source_id", source_id)
        match: MissionActionScoringRule | None = None
        for rule in self.mission_action_scoring_rules:
            if rule.scoring_source_id != requested_source_id:
                continue
            if match is not None:
                raise GameLifecycleError("Multiple Mission Action scoring rules matched.")
            match = rule
        if match is None:
            raise GameLifecycleError("Mission Action scoring source is not source-backed.")
        if (
            match.cap_bucket is VictoryPointCapBucket.PRIMARY
            and match.mission_id != self.primary_mission_id
        ):
            raise GameLifecycleError(
                "Primary Mission Action scoring source does not match active primary mission."
            )
        return match

    def _secondary_scoring_rule(
        self,
        *,
        secondary_mission_id: str,
        source_kind: VictoryPointSourceKind,
    ) -> SecondaryMissionScoringRule:
        match: SecondaryMissionScoringRule | None = None
        for rule in self.secondary_scoring_rules:
            if rule.secondary_mission_id != secondary_mission_id or rule.source_kind is not (
                source_kind
            ):
                continue
            if match is not None:
                raise GameLifecycleError("Multiple secondary scoring rules matched.")
            match = rule
        if match is None:
            raise GameLifecycleError("Secondary scoring rule is not source-backed.")
        return match


@dataclass(frozen=True, slots=True)
class SecondaryMissionCardState:
    player_id: str
    secondary_mission_id: str
    mode: SecondaryMissionCardMode
    battle_round: int
    status: SecondaryMissionCardStatus = SecondaryMissionCardStatus.ACTIVE
    source_result_id: str | None = None
    scored_transaction_id: str | None = None
    discarded_result_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SecondaryMissionCardState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier(
                "SecondaryMissionCardState secondary_mission_id",
                self.secondary_mission_id,
            ),
        )
        object.__setattr__(self, "mode", secondary_mission_card_mode_from_token(self.mode))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("SecondaryMissionCardState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "status",
            secondary_mission_card_status_from_token(self.status),
        )
        object.__setattr__(
            self,
            "source_result_id",
            _validate_optional_identifier(
                "SecondaryMissionCardState source_result_id",
                self.source_result_id,
            ),
        )
        object.__setattr__(
            self,
            "scored_transaction_id",
            _validate_optional_identifier(
                "SecondaryMissionCardState scored_transaction_id",
                self.scored_transaction_id,
            ),
        )
        object.__setattr__(
            self,
            "discarded_result_id",
            _validate_optional_identifier(
                "SecondaryMissionCardState discarded_result_id",
                self.discarded_result_id,
            ),
        )
        if self.status is SecondaryMissionCardStatus.SCORED and self.scored_transaction_id is None:
            raise GameLifecycleError("Scored secondary card requires scored_transaction_id.")
        if self.status is SecondaryMissionCardStatus.DISCARDED and self.discarded_result_id is None:
            raise GameLifecycleError("Discarded secondary card requires discarded_result_id.")
        if self.status is SecondaryMissionCardStatus.ACTIVE and (
            self.scored_transaction_id is not None or self.discarded_result_id is not None
        ):
            raise GameLifecycleError("Active secondary card must not have terminal IDs.")

    @classmethod
    def active_fixed(cls, *, player_id: str, secondary_mission_id: str) -> Self:
        return cls(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.FIXED,
            battle_round=1,
        )

    @classmethod
    def active_tactical(
        cls,
        *,
        player_id: str,
        secondary_mission_id: str,
        battle_round: int,
        source_result_id: str,
    ) -> Self:
        return cls(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            battle_round=battle_round,
            source_result_id=source_result_id,
        )

    def score(self, *, transaction_id: str) -> Self:
        if self.status is not SecondaryMissionCardStatus.ACTIVE:
            raise GameLifecycleError("Only active secondary cards can be scored.")
        return type(self)(
            player_id=self.player_id,
            secondary_mission_id=self.secondary_mission_id,
            mode=self.mode,
            battle_round=self.battle_round,
            status=SecondaryMissionCardStatus.SCORED,
            source_result_id=self.source_result_id,
            scored_transaction_id=transaction_id,
            discarded_result_id=None,
        )

    def discard(self, *, result_id: str) -> Self:
        if self.status is not SecondaryMissionCardStatus.ACTIVE:
            raise GameLifecycleError("Only active secondary cards can be discarded.")
        if self.mode is not SecondaryMissionCardMode.TACTICAL:
            raise GameLifecycleError("Only tactical secondary cards can be discarded.")
        return type(self)(
            player_id=self.player_id,
            secondary_mission_id=self.secondary_mission_id,
            mode=self.mode,
            battle_round=self.battle_round,
            status=SecondaryMissionCardStatus.DISCARDED,
            source_result_id=self.source_result_id,
            scored_transaction_id=None,
            discarded_result_id=result_id,
        )

    def to_payload(self) -> SecondaryMissionCardStatePayload:
        return {
            "player_id": self.player_id,
            "secondary_mission_id": self.secondary_mission_id,
            "mode": self.mode.value,
            "battle_round": self.battle_round,
            "status": self.status.value,
            "source_result_id": self.source_result_id,
            "scored_transaction_id": self.scored_transaction_id,
            "discarded_result_id": self.discarded_result_id,
        }

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        viewer = _validate_identifier("viewer_player_id", viewer_player_id)
        choices_revealed = _validate_bool(
            "secondary_mission_choices_revealed",
            secondary_mission_choices_revealed,
        )
        if viewer != self.player_id and not choices_revealed:
            return {
                "player_id": self.player_id,
                "hidden": True,
            }
        payload = cast(dict[str, JsonValue], self.to_payload())
        payload["hidden"] = False
        return payload

    @classmethod
    def from_payload(cls, payload: SecondaryMissionCardStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            secondary_mission_id=payload["secondary_mission_id"],
            mode=secondary_mission_card_mode_from_token(payload["mode"]),
            battle_round=payload["battle_round"],
            status=secondary_mission_card_status_from_token(payload["status"]),
            source_result_id=payload["source_result_id"],
            scored_transaction_id=payload["scored_transaction_id"],
            discarded_result_id=payload["discarded_result_id"],
        )


@dataclass(frozen=True, slots=True)
class TacticalSecondaryAchievementContext:
    achievement_id: str
    game_id: str
    player_id: str
    active_player_id: str
    secondary_mission_id: str
    battle_round: int
    phase: str
    card_battle_round: int
    victory_points: int
    scoring_rule_id: str
    scoring_rule_condition: str
    scoring_rule_source_id: str
    scoring_timing: str
    source_id: str
    evidence: JsonValue
    mode: SecondaryMissionCardMode = SecondaryMissionCardMode.TACTICAL

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "achievement_id",
            _validate_identifier(
                "TacticalSecondaryAchievementContext achievement_id",
                self.achievement_id,
            ),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("TacticalSecondaryAchievementContext game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("TacticalSecondaryAchievementContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "TacticalSecondaryAchievementContext active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier(
                "TacticalSecondaryAchievementContext secondary_mission_id",
                self.secondary_mission_id,
            ),
        )
        object.__setattr__(self, "mode", secondary_mission_card_mode_from_token(self.mode))
        if self.mode is not SecondaryMissionCardMode.TACTICAL:
            raise GameLifecycleError("Tactical achievement context requires Tactical mode.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "TacticalSecondaryAchievementContext battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("TacticalSecondaryAchievementContext phase", self.phase),
        )
        object.__setattr__(
            self,
            "card_battle_round",
            _validate_positive_int(
                "TacticalSecondaryAchievementContext card_battle_round",
                self.card_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_positive_int(
                "TacticalSecondaryAchievementContext victory_points",
                self.victory_points,
            ),
        )
        object.__setattr__(
            self,
            "scoring_rule_id",
            _validate_identifier(
                "TacticalSecondaryAchievementContext scoring_rule_id",
                self.scoring_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "scoring_rule_condition",
            _validate_identifier(
                "TacticalSecondaryAchievementContext scoring_rule_condition",
                self.scoring_rule_condition,
            ),
        )
        object.__setattr__(
            self,
            "scoring_rule_source_id",
            _validate_identifier(
                "TacticalSecondaryAchievementContext scoring_rule_source_id",
                self.scoring_rule_source_id,
            ),
        )
        object.__setattr__(
            self,
            "scoring_timing",
            _validate_identifier(
                "TacticalSecondaryAchievementContext scoring_timing",
                self.scoring_timing,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TacticalSecondaryAchievementContext source_id", self.source_id),
        )
        object.__setattr__(self, "evidence", validate_json_value(self.evidence))

    def to_payload(self) -> TacticalSecondaryAchievementContextPayload:
        return {
            "achievement_id": self.achievement_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "active_player_id": self.active_player_id,
            "secondary_mission_id": self.secondary_mission_id,
            "mode": self.mode.value,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "card_battle_round": self.card_battle_round,
            "victory_points": self.victory_points,
            "scoring_rule_id": self.scoring_rule_id,
            "scoring_rule_condition": self.scoring_rule_condition,
            "scoring_rule_source_id": self.scoring_rule_source_id,
            "scoring_timing": self.scoring_timing,
            "source_id": self.source_id,
            "evidence": self.evidence,
        }

    @classmethod
    def from_payload(cls, payload: TacticalSecondaryAchievementContextPayload) -> Self:
        return cls(
            achievement_id=payload["achievement_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            active_player_id=payload["active_player_id"],
            secondary_mission_id=payload["secondary_mission_id"],
            mode=secondary_mission_card_mode_from_token(payload["mode"]),
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            card_battle_round=payload["card_battle_round"],
            victory_points=payload["victory_points"],
            scoring_rule_id=payload["scoring_rule_id"],
            scoring_rule_condition=payload["scoring_rule_condition"],
            scoring_rule_source_id=payload["scoring_rule_source_id"],
            scoring_timing=payload["scoring_timing"],
            source_id=payload["source_id"],
            evidence=payload["evidence"],
        )


def initial_victory_point_ledgers(player_ids: tuple[str, ...]) -> list[VictoryPointLedger]:
    return [VictoryPointLedger.initial(player_id=player_id) for player_id in player_ids]


def victory_point_source_kind_from_token(token: object) -> VictoryPointSourceKind:
    if type(token) is VictoryPointSourceKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("VictoryPointSourceKind token must be a string.")
    try:
        return VictoryPointSourceKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported VictoryPointSourceKind token: {token}.") from exc


def victory_point_cap_bucket_from_token(token: object) -> VictoryPointCapBucket:
    if type(token) is VictoryPointCapBucket:
        return token
    if type(token) is not str:
        raise GameLifecycleError("VictoryPointCapBucket token must be a string.")
    try:
        return VictoryPointCapBucket(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported VictoryPointCapBucket token: {token}.") from exc


def secondary_mission_card_status_from_token(token: object) -> SecondaryMissionCardStatus:
    if type(token) is SecondaryMissionCardStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SecondaryMissionCardStatus token must be a string.")
    try:
        return SecondaryMissionCardStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SecondaryMissionCardStatus token: {token}.") from exc


def secondary_mission_card_mode_from_token(token: object) -> SecondaryMissionCardMode:
    if type(token) is SecondaryMissionCardMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SecondaryMissionCardMode token must be a string.")
    try:
        return SecondaryMissionCardMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SecondaryMissionCardMode token: {token}.") from exc


def scoring_window_kind_from_token(token: object) -> ScoringWindowKind:
    if type(token) is ScoringWindowKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ScoringWindowKind token must be a string.")
    try:
        return ScoringWindowKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ScoringWindowKind token: {token}.") from exc


def objective_control_timing_from_token(token: object) -> ObjectiveControlTiming:
    if type(token) is ObjectiveControlTiming:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ObjectiveControlTiming token must be a string.")
    try:
        return ObjectiveControlTiming(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ObjectiveControlTiming token: {token}.") from exc


def _controlled_objective_ids(
    record: ObjectiveControlRecord,
    *,
    player_id: str,
) -> tuple[str, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    return tuple(
        result.objective_id
        for result in record.results
        if result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == requested_player
    )


def _home_objective_ids(
    mission_setup: MissionSetup,
    *,
    player_id: str,
) -> tuple[str, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    home_zones = tuple(
        zone for zone in mission_setup.deployment_zones if zone.player_id == requested_player
    )
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if any(zone.contains_point(marker.x_inches, marker.y_inches) for zone in home_zones)
        )
    )


def _central_objective_ids(mission_setup: MissionSetup) -> tuple[str, ...]:
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if not any(
                zone.contains_point(marker.x_inches, marker.y_inches)
                for zone in mission_setup.deployment_zones
            )
        )
    )


def _turn_start_state_for_player(
    states: tuple[PrimaryObjectiveTurnStartState, ...],
    *,
    game_id: str,
    player_id: str,
    battle_round: int,
) -> PrimaryObjectiveTurnStartState:
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    matches = tuple(
        state
        for state in states
        if state.game_id == requested_game_id
        and state.player_id == requested_player
        and state.battle_round == requested_round
    )
    if len(matches) != 1:
        raise GameLifecycleError("Primary scoring requires exactly one turn-start snapshot.")
    return matches[0]


def _enemy_unit_destructions_this_turn(
    states: tuple[PrimaryUnitDestructionState, ...],
    *,
    player_id: str,
    battle_round: int,
    active_player_id: str,
) -> tuple[PrimaryUnitDestructionState, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_active = _validate_identifier("active_player_id", active_player_id)
    return tuple(
        state
        for state in states
        if state.destroying_player_id == requested_player
        and state.destroyed_player_id != requested_player
        and state.active_player_id == requested_active
        and state.battle_round == requested_round
    )


def _secondary_enemy_unit_destructions_this_turn(
    states: tuple[SecondaryUnitDestructionState, ...],
    *,
    player_id: str,
    battle_round: int,
    active_player_id: str,
) -> tuple[SecondaryUnitDestructionState, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_active = _validate_identifier("active_player_id", active_player_id)
    return tuple(
        state
        for state in states
        if state.destroying_player_id == requested_player
        and state.destroyed_player_id != requested_player
        and state.active_player_id == requested_active
        and state.battle_round == requested_round
    )


def _terrain_traps_this_turn(
    states: tuple[PrimaryTerrainTrapState, ...],
    *,
    player_id: str,
    battle_round: int,
    active_player_id: str,
) -> tuple[PrimaryTerrainTrapState, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_active = _validate_identifier("active_player_id", active_player_id)
    return tuple(
        state
        for state in states
        if state.player_id == requested_player
        and state.active_player_id == requested_active
        and state.battle_round == requested_round
    )


def _secondary_objective_cleanses_this_turn(
    states: tuple[SecondaryObjectiveCleanseState, ...],
    *,
    player_id: str,
    battle_round: int,
    active_player_id: str,
) -> tuple[SecondaryObjectiveCleanseState, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_active = _validate_identifier("active_player_id", active_player_id)
    return tuple(
        state
        for state in states
        if state.player_id == requested_player
        and state.active_player_id == requested_active
        and state.battle_round == requested_round
    )


def _secondary_terrain_plunders_this_turn(
    states: tuple[SecondaryTerrainPlunderState, ...],
    *,
    player_id: str,
    battle_round: int,
    active_player_id: str,
) -> tuple[SecondaryTerrainPlunderState, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_active = _validate_identifier("active_player_id", active_player_id)
    return tuple(
        state
        for state in states
        if state.player_id == requested_player
        and state.active_player_id == requested_active
        and state.battle_round == requested_round
    )


def _starting_strength_record_by_unit_id(
    records: tuple[StartingStrengthRecord, ...],
) -> dict[str, StartingStrengthRecord]:
    if type(records) is not tuple:
        raise GameLifecycleError("starting_strength_records must be a tuple.")
    mapped: dict[str, StartingStrengthRecord] = {}
    for record in records:
        if type(record) is not StartingStrengthRecord:
            raise GameLifecycleError(
                "starting_strength_records must contain StartingStrengthRecord values."
            )
        if record.unit_instance_id in mapped:
            raise GameLifecycleError("starting_strength_records must not duplicate units.")
        mapped[record.unit_instance_id] = record
    return mapped


def _starting_strength_for_destroyed_unit(
    unit_instance_id: str,
    *,
    starting_strength_by_unit_id: dict[str, StartingStrengthRecord],
) -> int:
    requested_unit = _validate_identifier("unit_instance_id", unit_instance_id)
    record = starting_strength_by_unit_id.get(requested_unit)
    if record is None:
        raise GameLifecycleError("Secondary scoring missing StartingStrengthRecord.")
    return record.starting_model_count


def _score_count_evidence(
    *,
    score_count: int,
    controlled_objective_ids: tuple[str, ...] = (),
    home_objective_ids: tuple[str, ...] = (),
    turn_start_controlled_objective_ids: tuple[str, ...] = (),
    trapped_terrain_feature_ids: tuple[str, ...] = (),
    destroyed_unit_instance_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    return {
        "score_count": _validate_non_negative_int("score_count", score_count),
        "controlled_objective_ids": list(
            _validate_identifier_tuple("controlled_objective_ids", controlled_objective_ids)
        ),
        "home_objective_ids": list(
            _validate_identifier_tuple("home_objective_ids", home_objective_ids)
        ),
        "turn_start_controlled_objective_ids": list(
            _validate_identifier_tuple(
                "turn_start_controlled_objective_ids",
                turn_start_controlled_objective_ids,
            )
        ),
        "trapped_terrain_feature_ids": list(
            _validate_identifier_tuple("trapped_terrain_feature_ids", trapped_terrain_feature_ids)
        ),
        "destroyed_unit_instance_ids": list(
            _validate_identifier_tuple("destroyed_unit_instance_ids", destroyed_unit_instance_ids)
        ),
    }


def _secondary_score_count_evidence(
    *,
    score_count: int,
    controlled_objective_ids: tuple[str, ...] = (),
    home_objective_ids: tuple[str, ...] = (),
    objective_marker_ids: tuple[str, ...] = (),
    terrain_feature_ids: tuple[str, ...] = (),
    destroyed_unit_instance_ids: tuple[str, ...] = (),
    destroyed_model_instance_ids: tuple[str, ...] = (),
    enemy_unit_instance_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    return {
        "score_count": _validate_non_negative_int("score_count", score_count),
        "controlled_objective_ids": list(
            _validate_identifier_tuple("controlled_objective_ids", controlled_objective_ids)
        ),
        "home_objective_ids": list(
            _validate_identifier_tuple("home_objective_ids", home_objective_ids)
        ),
        "objective_marker_ids": list(
            _validate_identifier_tuple("objective_marker_ids", objective_marker_ids)
        ),
        "terrain_feature_ids": list(
            _validate_identifier_tuple("terrain_feature_ids", terrain_feature_ids)
        ),
        "destroyed_unit_instance_ids": list(
            _validate_identifier_tuple("destroyed_unit_instance_ids", destroyed_unit_instance_ids)
        ),
        "destroyed_model_instance_ids": list(
            _validate_identifier_tuple("destroyed_model_instance_ids", destroyed_model_instance_ids)
        ),
        "enemy_unit_instance_ids": list(
            _validate_identifier_tuple("enemy_unit_instance_ids", enemy_unit_instance_ids)
        ),
    }


def _metadata_score_count(metadata: dict[str, JsonValue]) -> int:
    score_count = metadata.get("score_count")
    return _validate_non_negative_int("score_count", score_count)


def _validate_victory_point_transaction_tuple(
    field_name: str,
    values: object,
    *,
    player_id: str,
) -> tuple[VictoryPointTransaction, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[VictoryPointTransaction] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not VictoryPointTransaction:
            raise GameLifecycleError(f"{field_name} must contain transactions.")
        if value.player_id != player_id:
            raise GameLifecycleError(f"{field_name} player_id drift.")
        if value.transaction_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.transaction_id)
        validated.append(value)
    return tuple(validated)


def _validate_primary_scoring_rule_tuple(
    values: object,
) -> tuple[PrimaryMissionScoringRule, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MissionScoringPolicy primary_scoring_rules must be a tuple.")
    validated: list[PrimaryMissionScoringRule] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryMissionScoringRule:
            raise GameLifecycleError(
                "MissionScoringPolicy primary_scoring_rules must contain scoring rules."
            )
        if value.rule_id in seen:
            raise GameLifecycleError(
                "MissionScoringPolicy primary_scoring_rules must not contain duplicates."
            )
        seen.add(value.rule_id)
        validated.append(value)
    if not validated:
        raise GameLifecycleError("MissionScoringPolicy primary_scoring_rules must not be empty.")
    return tuple(sorted(validated, key=lambda rule: rule.rule_id))


def _validate_primary_turn_start_state_tuple(
    values: object,
) -> tuple[PrimaryObjectiveTurnStartState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("primary turn-start states must be a tuple.")
    states: list[PrimaryObjectiveTurnStartState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryObjectiveTurnStartState:
            raise GameLifecycleError("primary turn-start states must contain state values.")
        if value.state_id in seen:
            raise GameLifecycleError("primary turn-start states must not duplicate IDs.")
        seen.add(value.state_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.state_id))


def _validate_primary_terrain_trap_state_tuple(
    values: object,
) -> tuple[PrimaryTerrainTrapState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("primary terrain trap states must be a tuple.")
    states: list[PrimaryTerrainTrapState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryTerrainTrapState:
            raise GameLifecycleError("primary terrain trap states must contain state values.")
        if value.trap_id in seen:
            raise GameLifecycleError("primary terrain trap states must not duplicate IDs.")
        seen.add(value.trap_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.trap_id))


def _validate_primary_unit_destruction_state_tuple(
    values: object,
) -> tuple[PrimaryUnitDestructionState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("primary unit destruction states must be a tuple.")
    states: list[PrimaryUnitDestructionState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryUnitDestructionState:
            raise GameLifecycleError("primary unit destruction states must contain state values.")
        if value.destruction_id in seen:
            raise GameLifecycleError("primary unit destruction states must not duplicate IDs.")
        seen.add(value.destruction_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.destruction_id))


def _validate_secondary_destroyed_model_state_tuple(
    values: object,
) -> tuple[SecondaryDestroyedModelState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("secondary destroyed model states must be a tuple.")
    states: list[SecondaryDestroyedModelState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not SecondaryDestroyedModelState:
            raise GameLifecycleError(
                "secondary destroyed model states must contain model state values."
            )
        if value.model_instance_id in seen:
            raise GameLifecycleError("secondary destroyed model states must not duplicate IDs.")
        seen.add(value.model_instance_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.model_instance_id))


def _validate_secondary_unit_destruction_state_tuple(
    values: object,
) -> tuple[SecondaryUnitDestructionState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("secondary unit destruction states must be a tuple.")
    states: list[SecondaryUnitDestructionState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not SecondaryUnitDestructionState:
            raise GameLifecycleError("secondary unit destruction states must contain state values.")
        if value.destruction_id in seen:
            raise GameLifecycleError("secondary unit destruction states must not duplicate IDs.")
        seen.add(value.destruction_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.destruction_id))


def _validate_secondary_objective_cleanse_state_tuple(
    values: object,
) -> tuple[SecondaryObjectiveCleanseState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("secondary objective cleanse states must be a tuple.")
    states: list[SecondaryObjectiveCleanseState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not SecondaryObjectiveCleanseState:
            raise GameLifecycleError(
                "secondary objective cleanse states must contain state values."
            )
        if value.cleanse_id in seen:
            raise GameLifecycleError("secondary objective cleanse states must not duplicate IDs.")
        seen.add(value.cleanse_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.cleanse_id))


def _validate_secondary_terrain_plunder_state_tuple(
    values: object,
) -> tuple[SecondaryTerrainPlunderState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("secondary terrain plunder states must be a tuple.")
    states: list[SecondaryTerrainPlunderState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not SecondaryTerrainPlunderState:
            raise GameLifecycleError("secondary terrain plunder states must contain state values.")
        if value.plunder_id in seen:
            raise GameLifecycleError("secondary terrain plunder states must not duplicate IDs.")
        seen.add(value.plunder_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.plunder_id))


def _validate_secondary_scoring_rule_tuple(
    values: object,
) -> tuple[SecondaryMissionScoringRule, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MissionScoringPolicy secondary_scoring_rules must be a tuple.")
    validated: list[SecondaryMissionScoringRule] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not SecondaryMissionScoringRule:
            raise GameLifecycleError(
                "MissionScoringPolicy secondary_scoring_rules must contain scoring rules."
            )
        if value.rule_id in seen:
            raise GameLifecycleError(
                "MissionScoringPolicy secondary_scoring_rules must not contain duplicates."
            )
        seen.add(value.rule_id)
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda rule: (rule.secondary_mission_id, rule.source_kind.value, rule.rule_id),
        )
    )


def _validate_mission_action_scoring_rule_tuple(
    values: object,
) -> tuple[MissionActionScoringRule, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "MissionScoringPolicy mission_action_scoring_rules must be a tuple."
        )
    validated: list[MissionActionScoringRule] = []
    seen_action_ids: set[str] = set()
    seen_scoring_source_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not MissionActionScoringRule:
            raise GameLifecycleError(
                "MissionScoringPolicy mission_action_scoring_rules must contain scoring rules."
            )
        if value.mission_action_id in seen_action_ids:
            raise GameLifecycleError(
                "MissionScoringPolicy mission_action_scoring_rules must not duplicate action IDs."
            )
        if value.scoring_source_id in seen_scoring_source_ids:
            raise GameLifecycleError(
                "MissionScoringPolicy mission_action_scoring_rules must not duplicate scoring "
                "source IDs."
            )
        seen_action_ids.add(value.mission_action_id)
        seen_scoring_source_ids.add(value.scoring_source_id)
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda rule: rule.mission_action_id,
        )
    )


def _validate_scoring_window_tuple(
    values: object,
    *,
    game_id: str,
) -> tuple[ScoringWindowState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FinalScoringResult scoring_windows must be a tuple.")
    requested_game_id = _validate_identifier("game_id", game_id)
    validated: list[ScoringWindowState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ScoringWindowState:
            raise GameLifecycleError("FinalScoringResult scoring_windows must contain states.")
        if value.game_id != requested_game_id:
            raise GameLifecycleError("ScoringWindowState game_id drift.")
        if value.window_id in seen:
            raise GameLifecycleError("FinalScoringResult scoring_windows must not duplicate IDs.")
        seen.add(value.window_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda window: window.window_id))


def _validate_final_score_tuple(values: object) -> tuple[FinalScoreLine, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FinalScoringResult final_scores must be a tuple.")
    validated: list[FinalScoreLine] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not FinalScoreLine:
            raise GameLifecycleError("FinalScoringResult final_scores must contain score lines.")
        if value.player_id in seen:
            raise GameLifecycleError("FinalScoringResult final_scores must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    if not validated:
        raise GameLifecycleError("FinalScoringResult final_scores must not be empty.")
    return tuple(sorted(validated, key=lambda score: score.player_id))


def _winner_player_ids_from_scores(scores: tuple[FinalScoreLine, ...]) -> tuple[str, ...]:
    final_scores = _validate_final_score_tuple(scores)
    max_score = max(score.victory_points for score in final_scores)
    return tuple(score.player_id for score in final_scores if score.victory_points == max_score)


def _validate_required_final_scoring_windows(
    *,
    scoring_windows: tuple[ScoringWindowState, ...],
    policy: MissionScoringPolicy,
    game_id: str,
    battle_round: int,
) -> tuple[ScoringWindowState, ...]:
    if type(policy) is not MissionScoringPolicy:
        raise GameLifecycleError("Final scoring window validation requires MissionScoringPolicy.")
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    validated_windows = _validate_scoring_window_tuple(
        scoring_windows,
        game_id=requested_game_id,
    )
    recorded = {
        (window.window_kind, window.window, window.battle_round) for window in validated_windows
    }
    required = {
        (ScoringWindowKind.END_OF_ROUND, window, requested_round)
        for window in policy.end_of_round_scoring_windows
    } | {
        (ScoringWindowKind.END_OF_GAME, window, requested_round)
        for window in policy.end_of_game_scoring_windows
    }
    missing = tuple(sorted(required - recorded, key=lambda item: (item[0].value, item[1], item[2])))
    if missing:
        missing_text = ", ".join(
            f"{kind.value}:{window}:round-{round_number:02d}"
            for kind, window, round_number in missing
        )
        raise GameLifecycleError(f"Final scoring requires recorded policy windows: {missing_text}.")
    return validated_windows


def _metadata_with_vp_cap_audit(
    metadata: JsonValue,
    *,
    requested_amount: int,
    applied_amount: int,
    source_cap: int,
    source_points_before: int,
    source_points_after: int,
    total_cap: int,
    total_points_before: int,
    total_points_after: int,
    capped_reasons: tuple[str, ...],
    fixed_secondary_mission_cap: int | None = None,
    fixed_secondary_mission_points_before: int = 0,
    fixed_secondary_mission_points_after: int = 0,
) -> JsonValue:
    audit = {
        "requested_amount": _validate_positive_int("requested_amount", requested_amount),
        "applied_amount": _validate_non_negative_int("applied_amount", applied_amount),
        "source_cap": _validate_non_negative_int("source_cap", source_cap),
        "source_points_before": _validate_non_negative_int(
            "source_points_before", source_points_before
        ),
        "source_points_after": _validate_non_negative_int(
            "source_points_after", source_points_after
        ),
        "total_cap": _validate_positive_int("total_cap", total_cap),
        "total_points_before": _validate_non_negative_int(
            "total_points_before", total_points_before
        ),
        "total_points_after": _validate_non_negative_int("total_points_after", total_points_after),
        "capped_reasons": list(
            _validate_identifier_tuple_ordered(
                "capped_reasons",
                capped_reasons,
                min_length=1,
            )
        ),
    }
    if fixed_secondary_mission_cap is not None:
        audit["fixed_secondary_mission_cap"] = _validate_positive_int(
            "fixed_secondary_mission_cap",
            fixed_secondary_mission_cap,
        )
        audit["fixed_secondary_mission_points_before"] = _validate_non_negative_int(
            "fixed_secondary_mission_points_before",
            fixed_secondary_mission_points_before,
        )
        audit["fixed_secondary_mission_points_after"] = _validate_non_negative_int(
            "fixed_secondary_mission_points_after",
            fixed_secondary_mission_points_after,
        )
    validated_metadata = validate_json_value(metadata)
    if validated_metadata is None:
        return {"vp_cap_audit": validate_json_value(audit)}
    if isinstance(validated_metadata, dict):
        if "vp_cap_audit" in validated_metadata:
            raise GameLifecycleError("Victory point metadata already contains vp_cap_audit.")
        updated = dict(validated_metadata)
        updated["vp_cap_audit"] = validate_json_value(audit)
        return updated
    return {
        "original_metadata": validated_metadata,
        "vp_cap_audit": validate_json_value(audit),
    }


def _ledger_points_from_source(
    *,
    ledger: VictoryPointLedger,
    source_kind: VictoryPointSourceKind,
    source_id: str,
) -> int:
    if type(ledger) is not VictoryPointLedger:
        raise GameLifecycleError("VP source accounting requires a VictoryPointLedger.")
    requested_kind = victory_point_source_kind_from_token(source_kind)
    requested_source_id = _validate_identifier("source_id", source_id)
    return sum(
        transaction.amount
        for transaction in ledger.transactions
        if transaction.source_kind is requested_kind
        and transaction.source_id == requested_source_id
    )


def _validate_identifier_tuple_ordered(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(identifiers)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
    sort_values: bool = True,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
