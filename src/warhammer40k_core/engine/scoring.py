from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.mission_scoring_resolution import (
    MissionScoringResolutionMode,
    validate_mission_scoring_resolution_groups,
)
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import primary_scoring_state_evidence as _state
from warhammer40k_core.engine.destruction_provenance import (
    ModelDestructionAttribution,
    ModelDestructionAttributionPayload,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlRecordPayload,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    RulesUnitObjectiveProximityWitnessPayload,
    primary_unattributed_destruction_cause_from_token,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    PRIMARY_SCORING_TURN_START_OBJECTIVE_CONDITIONS,
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    home_objective_ids as _home_objective_ids,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    primary_score_count_evidence as _score_count_evidence,
)
from warhammer40k_core.engine.primary_scoring_resolution import (
    PrimaryScoringResolutionCandidate,
    PrimaryScoringResolutionMode,
    primary_scoring_resolution_mode_from_token,
    resolve_primary_scoring_candidates,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    PrimaryScoringSpatialEvidence,
)
from warhammer40k_core.engine.primary_scoring_timing import (
    SUPPORTED_PRIMARY_SCORING_TIMINGS,
    primary_scoring_timing_applies,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    PrimaryVictoryPointCapTreatment,
    validate_primary_victory_point_award,
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.secondary_scoring_provider import SecondaryScoringProviderKind
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
    player_id: str
    force_disposition_id: str
    mission_pack_id: str
    primary_mission_id: str
    primary_scoring_supported: bool
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
    resolution_mode: str
    resolution_group_id: str | None
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
    source_objective_control_record: ObjectiveControlRecordPayload
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
    destroying_player_id: str | None
    destruction_attribution: ModelDestructionAttributionPayload | None
    source_model_destroyed_event_id: str | None
    source_rules_unit_objective_proximity_witness: RulesUnitObjectiveProximityWitnessPayload | None
    source_battlefield_departure_ids: list[str]
    unattributed_cause: str | None
    source_mutation_id: str | None
    destroyed_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    destroyed_unit_instance_id: str
    started_turn_terrain_feature_ids: list[str]
    started_turn_objective_marker_ids: list[str]
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
    resolution_mode: MissionScoringResolutionMode
    resolution_group_id: str | None
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rule_id",
            _validate_identifier("PrimaryMissionScoringRule rule_id", self.rule_id),
        )
        timing = _validate_identifier("PrimaryMissionScoringRule timing", self.timing)
        if timing not in SUPPORTED_PRIMARY_SCORING_TIMINGS:
            raise GameLifecycleError("Unsupported primary scoring rule timing.")
        object.__setattr__(self, "timing", timing)
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
        resolution_mode = primary_scoring_resolution_mode_from_token(self.resolution_mode)
        resolution_group_id = _validate_optional_identifier(
            "PrimaryMissionScoringRule resolution_group_id",
            self.resolution_group_id,
        )
        if resolution_mode is PrimaryScoringResolutionMode.INDEPENDENT:
            if resolution_group_id is not None:
                raise GameLifecycleError(
                    "Independent PrimaryMissionScoringRule cannot have a resolution group."
                )
        elif resolution_group_id is None:
            raise GameLifecycleError(
                "Grouped PrimaryMissionScoringRule requires a resolution group."
            )
        object.__setattr__(self, "resolution_mode", resolution_mode)
        object.__setattr__(self, "resolution_group_id", resolution_group_id)
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
            "resolution_mode": self.resolution_mode.value,
            "resolution_group_id": self.resolution_group_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        expected_fields = {
            "rule_id",
            "timing",
            "source_kind",
            "victory_points",
            "cap",
            "condition",
            "resolution_mode",
            "resolution_group_id",
            "source_id",
        }
        if type(payload) is not dict:
            raise GameLifecycleError("PrimaryMissionScoringRule payload fields are invalid.")
        payload_mapping = cast(dict[str, object], payload)
        if set(payload_mapping) != expected_fields:
            raise GameLifecycleError("PrimaryMissionScoringRule payload fields are invalid.")
        raw_payload = cast(PrimaryMissionScoringRulePayload, payload_mapping)
        return cls(
            rule_id=raw_payload["rule_id"],
            timing=raw_payload["timing"],
            source_kind=victory_point_source_kind_from_token(raw_payload["source_kind"]),
            victory_points=raw_payload["victory_points"],
            cap=raw_payload["cap"],
            condition=raw_payload["condition"],
            resolution_mode=primary_scoring_resolution_mode_from_token(
                raw_payload["resolution_mode"]
            ),
            resolution_group_id=raw_payload["resolution_group_id"],
            source_id=raw_payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryObjectiveTurnStartState:
    state_id: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    source_objective_control_record: ObjectiveControlRecord
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
        source_record = self.source_objective_control_record
        if type(source_record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "Primary turn-start state source objective-control record must be typed."
            )
        if (
            source_record.game_id != self.game_id
            or source_record.active_player_id != self.active_player_id
            or source_record.battle_round != self.battle_round
            or source_record.timing is not ObjectiveControlTiming.TURN_START
        ):
            raise GameLifecycleError(
                "Primary turn-start state source objective-control identity drift."
            )
        object.__setattr__(self, "source_objective_control_record", source_record)
        expected_controlled_objective_ids = tuple(
            sorted(
                result.objective_id
                for result in source_record.results
                if result.controlled_by_player_id == self.player_id
            )
        )
        controlled_objective_ids = _validate_identifier_tuple(
            "PrimaryObjectiveTurnStartState controlled_objective_ids",
            self.controlled_objective_ids,
        )
        if controlled_objective_ids != expected_controlled_objective_ids:
            raise GameLifecycleError(
                "Primary turn-start controlled objectives drifted from source evidence."
            )
        object.__setattr__(
            self,
            "controlled_objective_ids",
            controlled_objective_ids,
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
            "source_objective_control_record": (self.source_objective_control_record.to_payload()),
            "controlled_objective_ids": list(self.controlled_objective_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryObjectiveTurnStartStatePayload) -> Self:
        payload_object = cast(object, payload)
        if not isinstance(payload_object, dict) or set(
            cast(dict[object, object], payload_object)
        ) != {
            "state_id",
            "game_id",
            "player_id",
            "active_player_id",
            "battle_round",
            "source_objective_control_record",
            "controlled_objective_ids",
            "source_id",
        }:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState payload fields are invalid.")
        return cls(
            state_id=payload["state_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            source_objective_control_record=ObjectiveControlRecord.from_payload(
                payload["source_objective_control_record"]
            ),
            controlled_objective_ids=_identifier_tuple_from_payload_list(
                "PrimaryObjectiveTurnStartState controlled_objective_ids",
                payload["controlled_objective_ids"],
            ),
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
    destroying_player_id: str | None
    destruction_attribution: ModelDestructionAttribution | None
    source_model_destroyed_event_id: str | None
    source_rules_unit_objective_proximity_witness: RulesUnitObjectiveProximityWitness | None
    source_battlefield_departure_ids: tuple[str, ...]
    unattributed_cause: PrimaryUnattributedDestructionCause | None
    source_mutation_id: str | None
    destroyed_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    destroyed_unit_instance_id: str
    started_turn_terrain_feature_ids: tuple[str, ...]
    started_turn_objective_marker_ids: tuple[str, ...]
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
        if self.destroying_player_id is not None:
            object.__setattr__(
                self,
                "destroying_player_id",
                _validate_identifier(
                    "PrimaryUnitDestructionState destroying_player_id",
                    self.destroying_player_id,
                ),
            )
        if (
            self.destruction_attribution is not None
            and type(self.destruction_attribution) is not ModelDestructionAttribution
        ):
            raise GameLifecycleError(
                "PrimaryUnitDestructionState destruction_attribution must be typed."
            )
        object.__setattr__(
            self,
            "source_model_destroyed_event_id",
            _validate_optional_identifier(
                "PrimaryUnitDestructionState source_model_destroyed_event_id",
                self.source_model_destroyed_event_id,
            ),
        )
        if (
            self.source_rules_unit_objective_proximity_witness is not None
            and type(self.source_rules_unit_objective_proximity_witness)
            is not RulesUnitObjectiveProximityWitness
        ):
            raise GameLifecycleError(
                "PrimaryUnitDestructionState source objective witness must be typed."
            )
        if self.unattributed_cause is not None:
            object.__setattr__(
                self,
                "unattributed_cause",
                primary_unattributed_destruction_cause_from_token(self.unattributed_cause),
            )
        object.__setattr__(
            self,
            "source_mutation_id",
            _validate_optional_identifier(
                "PrimaryUnitDestructionState source_mutation_id",
                self.source_mutation_id,
            ),
        )
        source_departure_ids = _validate_identifier_tuple(
            "PrimaryUnitDestructionState source_battlefield_departure_ids",
            self.source_battlefield_departure_ids,
        )
        if self.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE:
            if source_departure_ids:
                raise GameLifecycleError(
                    "Reserve-deadline Primary destruction cannot reference battlefield departures."
                )
        elif not source_departure_ids:
            raise GameLifecycleError(
                "Primary destruction requires source battlefield-departure evidence."
            )
        object.__setattr__(
            self,
            "source_battlefield_departure_ids",
            source_departure_ids,
        )
        attribution = self.destruction_attribution
        if attribution is None:
            if (
                self.destroying_player_id is not None
                or self.source_model_destroyed_event_id is not None
                or self.source_rules_unit_objective_proximity_witness is not None
                or self.unattributed_cause is None
                or self.source_mutation_id is None
            ):
                raise GameLifecycleError(
                    "Unattributed Primary destruction requires one explicit cause and no source."
                )
        else:
            if (
                self.destroying_player_id != attribution.destroying_player_id
                or self.source_model_destroyed_event_id is None
                or self.unattributed_cause is not None
                or self.source_mutation_id is not None
            ):
                raise GameLifecycleError(
                    "Attributed Primary destruction source evidence is inconsistent."
                )
            witness = self.source_rules_unit_objective_proximity_witness
            source_rules_unit_id = attribution.source_rules_unit_instance_id
            if (source_rules_unit_id is None) != (witness is None):
                raise GameLifecycleError(
                    "Primary destruction source objective evidence presence is inconsistent."
                )
            if witness is not None and witness.rules_unit_instance_id != source_rules_unit_id:
                raise GameLifecycleError(
                    "Primary destruction source objective evidence identity drift."
                )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier(
                "PrimaryUnitDestructionState destroyed_player_id",
                self.destroyed_player_id,
            ),
        )
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
            "started_turn_objective_marker_ids",
            _validate_identifier_tuple(
                "PrimaryUnitDestructionState started_turn_objective_marker_ids",
                self.started_turn_objective_marker_ids,
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
            "destruction_attribution": (
                None
                if self.destruction_attribution is None
                else self.destruction_attribution.to_payload()
            ),
            "source_model_destroyed_event_id": self.source_model_destroyed_event_id,
            "source_rules_unit_objective_proximity_witness": (
                None
                if self.source_rules_unit_objective_proximity_witness is None
                else self.source_rules_unit_objective_proximity_witness.to_payload()
            ),
            "source_battlefield_departure_ids": list(self.source_battlefield_departure_ids),
            "unattributed_cause": (
                None if self.unattributed_cause is None else self.unattributed_cause.value
            ),
            "source_mutation_id": self.source_mutation_id,
            "destroyed_player_id": self.destroyed_player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "destroyed_unit_instance_id": self.destroyed_unit_instance_id,
            "started_turn_terrain_feature_ids": list(self.started_turn_terrain_feature_ids),
            "started_turn_objective_marker_ids": list(self.started_turn_objective_marker_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryUnitDestructionStatePayload) -> Self:
        payload_object = cast(object, payload)
        if not isinstance(payload_object, dict) or set(
            cast(dict[object, object], payload_object)
        ) != {
            "destruction_id",
            "game_id",
            "destroying_player_id",
            "destruction_attribution",
            "source_model_destroyed_event_id",
            "source_rules_unit_objective_proximity_witness",
            "source_battlefield_departure_ids",
            "unattributed_cause",
            "source_mutation_id",
            "destroyed_player_id",
            "active_player_id",
            "battle_round",
            "phase",
            "destroyed_unit_instance_id",
            "started_turn_terrain_feature_ids",
            "started_turn_objective_marker_ids",
            "source_id",
        }:
            raise GameLifecycleError("PrimaryUnitDestructionState payload fields are invalid.")
        return cls(
            destruction_id=payload["destruction_id"],
            game_id=payload["game_id"],
            destroying_player_id=payload["destroying_player_id"],
            destruction_attribution=(
                None
                if payload["destruction_attribution"] is None
                else ModelDestructionAttribution.from_model_destroyed_payload(
                    payload["destruction_attribution"]
                )
            ),
            source_model_destroyed_event_id=payload["source_model_destroyed_event_id"],
            source_rules_unit_objective_proximity_witness=(
                None
                if payload["source_rules_unit_objective_proximity_witness"] is None
                else RulesUnitObjectiveProximityWitness.from_payload(
                    payload["source_rules_unit_objective_proximity_witness"]
                )
            ),
            source_battlefield_departure_ids=_identifier_tuple_from_payload_list(
                "PrimaryUnitDestructionState source_battlefield_departure_ids",
                payload["source_battlefield_departure_ids"],
            ),
            unattributed_cause=(
                None
                if payload["unattributed_cause"] is None
                else primary_unattributed_destruction_cause_from_token(
                    payload["unattributed_cause"]
                )
            ),
            source_mutation_id=payload["source_mutation_id"],
            destroyed_player_id=payload["destroyed_player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            destroyed_unit_instance_id=payload["destroyed_unit_instance_id"],
            started_turn_terrain_feature_ids=_identifier_tuple_from_payload_list(
                "PrimaryUnitDestructionState started_turn_terrain_feature_ids",
                payload["started_turn_terrain_feature_ids"],
            ),
            started_turn_objective_marker_ids=_identifier_tuple_from_payload_list(
                "PrimaryUnitDestructionState started_turn_objective_marker_ids",
                payload["started_turn_objective_marker_ids"],
            ),
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
class MissionScoringPolicy:
    player_id: str
    force_disposition_id: str
    mission_pack_id: str
    primary_mission_id: str
    primary_scoring_supported: bool
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
            "player_id",
            _validate_identifier("MissionScoringPolicy player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_identifier(
                "MissionScoringPolicy force_disposition_id", self.force_disposition_id
            ),
        )
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
            "primary_scoring_supported",
            _validate_bool(
                "MissionScoringPolicy primary_scoring_supported",
                self.primary_scoring_supported,
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
        primary_scoring_rules = _validate_primary_scoring_rule_tuple(self.primary_scoring_rules)
        if self.primary_scoring_supported != bool(primary_scoring_rules):
            raise GameLifecycleError(
                "MissionScoringPolicy Primary support status must match scoring rules."
            )
        object.__setattr__(
            self,
            "primary_scoring_rules",
            primary_scoring_rules,
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
        turn_order: tuple[str, ...],
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        state_evidence: _state.PrimaryScoringStateEvidence,
        spatial_evidence: PrimaryScoringSpatialEvidence | None = None,
        scoring_player_ids: tuple[str, ...] = (),
        end_of_battle: bool = False,
    ) -> tuple[VictoryPointAward, ...]:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("Primary scoring requires an ObjectiveControlRecord.")
        if type(mission_setup) is not MissionSetup:
            raise GameLifecycleError("Primary scoring requires MissionSetup.")
        from warhammer40k_core.engine.missions import validate_mission_setup_source_layout

        validate_mission_setup_source_layout(mission_setup)
        if mission_setup.mission_pack_id != self.mission_pack_id:
            raise GameLifecycleError("Primary scoring policy mission pack drifted from setup.")
        assignment = next(
            (
                candidate
                for candidate in mission_setup.primary_mission_assignments
                if candidate.player_id == self.player_id
            ),
            None,
        )
        if assignment is None:
            raise GameLifecycleError("Primary scoring player is missing from MissionSetup.")
        if (
            assignment.force_disposition_id != self.force_disposition_id
            or assignment.primary_mission_id != self.primary_mission_id
        ):
            raise GameLifecycleError("Primary scoring policy drifted from MissionSetup assignment.")
        if not self.primary_scoring_supported:
            raise GameLifecycleError(
                "Primary mission scoring source is known but engine implementation is pending."
            )
        ordered_players = _validate_identifier_tuple_ordered(
            "Primary scoring turn_order",
            turn_order,
            min_length=2,
        )
        if record.active_player_id not in ordered_players:
            raise GameLifecycleError("Primary scoring active player is missing from turn_order.")
        if not end_of_battle and record.active_player_id != self.player_id:
            raise GameLifecycleError("Ordinary Primary scoring requires active-player policy.")
        if end_of_battle and record.active_player_id != ordered_players[-1]:
            raise GameLifecycleError(
                "End-of-battle Primary scoring requires the last player's turn-end record."
            )
        _state.validate_primary_scoring_state_evidence_context(
            state_evidence,
            mission_setup=mission_setup,
            turn_order=ordered_players,
            record=record,
            end_of_battle=end_of_battle,
        )
        starts = _validate_primary_turn_start_state_tuple(turn_start_states)
        traps = _validate_primary_terrain_trap_state_tuple(terrain_trap_states)
        destructions = _validate_primary_unit_destruction_state_tuple(unit_destruction_states)
        _validate_primary_scoring_evidence_context(
            record=record,
            player_ids=ordered_players,
            turn_start_states=starts,
            terrain_trap_states=traps,
            unit_destruction_states=destructions,
        )
        player_ids = _validate_identifier_tuple("scoring_player_ids", scoring_player_ids)
        if not player_ids:
            player_ids = (record.active_player_id,)
        if any(player_id not in ordered_players for player_id in player_ids):
            raise GameLifecycleError("Primary scoring player is missing from turn_order.")
        if player_ids != (self.player_id,):
            raise GameLifecycleError("Primary scoring policy may score only its assigned player.")
        required_spatial_conditions = self.required_primary_spatial_conditions(
            record=record,
            end_of_battle=end_of_battle,
        )
        if required_spatial_conditions:
            if spatial_evidence is None:
                raise GameLifecycleError("Primary scoring policy requires spatial evidence.")
            if spatial_evidence.requested_condition_ids != required_spatial_conditions:
                raise GameLifecycleError(
                    "Primary scoring policy spatial evidence conditions drifted."
                )
        elif spatial_evidence is not None:
            raise GameLifecycleError("Unexpected Primary scoring spatial evidence.")
        achieved_awards_by_rule_id: dict[str, VictoryPointAward] = {}
        rule_by_id: dict[str, PrimaryMissionScoringRule] = {}
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
                    turn_order=ordered_players,
                    player_id=player_id,
                    turn_start_states=starts,
                    terrain_trap_states=traps,
                    unit_destruction_states=destructions,
                    state_evidence=state_evidence,
                    spatial_evidence=spatial_evidence,
                    end_of_battle=end_of_battle,
                )
                if award is not None:
                    if rule.rule_id in achieved_awards_by_rule_id:
                        raise GameLifecycleError(
                            "Primary scoring produced duplicate achieved rule IDs."
                        )
                    achieved_awards_by_rule_id[rule.rule_id] = award
                    rule_by_id[rule.rule_id] = rule
        resolved = resolve_primary_scoring_candidates(
            tuple(
                PrimaryScoringResolutionCandidate(
                    rule_id=rule_id,
                    amount=award.amount,
                    resolution_mode=rule_by_id[rule_id].resolution_mode,
                    resolution_group_id=rule_by_id[rule_id].resolution_group_id,
                )
                for rule_id, award in achieved_awards_by_rule_id.items()
            )
        )
        return tuple(
            replace(
                achieved_awards_by_rule_id[result.candidate.rule_id],
                metadata={
                    **cast(
                        dict[str, JsonValue],
                        achieved_awards_by_rule_id[result.candidate.rule_id].metadata,
                    ),
                    **result.metadata(),
                },
            )
            for result in resolved
        )

    def _primary_rule_applies_at_record(
        self,
        *,
        rule: PrimaryMissionScoringRule,
        record: ObjectiveControlRecord,
        end_of_battle: bool,
    ) -> bool:
        return primary_scoring_timing_applies(
            timing=rule.timing,
            battle_round=record.battle_round,
            phase=record.phase,
            objective_control_timing=record.timing,
            primary_scoring_phase=self.primary_scoring_phase,
            primary_scoring_timing=self.primary_scoring_timing,
            game_length_battle_rounds=self.game_length_battle_rounds,
            end_of_battle=end_of_battle,
        )

    def required_primary_spatial_conditions(
        self,
        *,
        record: ObjectiveControlRecord,
        end_of_battle: bool = False,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    rule.condition
                    for rule in self.primary_scoring_rules
                    if rule.condition in PRIMARY_SCORING_SPATIAL_CONDITIONS
                    and self._primary_rule_applies_at_record(
                        rule=rule,
                        record=record,
                        end_of_battle=end_of_battle,
                    )
                }
            )
        )

    def _primary_award_for_rule(
        self,
        *,
        rule: PrimaryMissionScoringRule,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        turn_order: tuple[str, ...],
        player_id: str,
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        state_evidence: _state.PrimaryScoringStateEvidence,
        spatial_evidence: PrimaryScoringSpatialEvidence | None,
        end_of_battle: bool,
    ) -> VictoryPointAward | None:
        evidence = self._primary_rule_evidence(
            rule=rule,
            record=record,
            mission_setup=mission_setup,
            turn_order=turn_order,
            player_id=player_id,
            turn_start_states=turn_start_states,
            terrain_trap_states=terrain_trap_states,
            unit_destruction_states=unit_destruction_states,
            state_evidence=state_evidence,
            spatial_evidence=spatial_evidence,
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
                "primary_scoring_state_evidence_id": state_evidence.evidence_id,
                "primary_scoring_state_evidence_hash": state_evidence.evidence_hash,
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
        turn_order: tuple[str, ...],
        player_id: str,
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        state_evidence: _state.PrimaryScoringStateEvidence,
        spatial_evidence: PrimaryScoringSpatialEvidence | None,
        end_of_battle: bool,
    ) -> dict[str, JsonValue]:
        requested_player = _validate_identifier("player_id", player_id)
        if rule.condition in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS:
            turn_start_controlled_objective_ids: tuple[str, ...] | None = None
            if rule.condition in PRIMARY_SCORING_TURN_START_OBJECTIVE_CONDITIONS:
                turn_start_controlled_objective_ids = _turn_start_state_for_player(
                    turn_start_states,
                    game_id=record.game_id,
                    player_id=requested_player,
                    battle_round=record.battle_round,
                ).controlled_objective_ids
            return evaluate_primary_scoring_condition(
                condition=rule.condition,
                context=PrimaryScoringConditionContext(
                    record=record,
                    mission_setup=mission_setup,
                    turn_order=turn_order,
                    player_id=requested_player,
                    turn_start_controlled_objective_ids=(turn_start_controlled_objective_ids),
                    destruction_evidence=tuple(
                        PrimaryUnitDestructionEvidence(
                            destruction_id=state.destruction_id,
                            battle_round=state.battle_round,
                            active_player_id=state.active_player_id,
                            destroying_player_id=state.destroying_player_id,
                            destroyed_player_id=state.destroyed_player_id,
                            destroyed_unit_instance_id=state.destroyed_unit_instance_id,
                            destruction_attribution=state.destruction_attribution,
                            source_rules_unit_objective_proximity_witness=(
                                state.source_rules_unit_objective_proximity_witness
                            ),
                            started_turn_terrain_feature_ids=(
                                state.started_turn_terrain_feature_ids
                            ),
                            started_turn_objective_marker_ids=(
                                state.started_turn_objective_marker_ids
                            ),
                        )
                        for state in unit_destruction_states
                    ),
                    state_evidence=state_evidence,
                    spatial_evidence=spatial_evidence,
                    end_of_battle=end_of_battle,
                ),
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
            enemy_destructions = _enemy_unit_destructions_this_turn(
                unit_destruction_states,
                player_id=requested_player,
                battle_round=record.battle_round,
                active_player_id=record.active_player_id,
            )
            matching = tuple(
                destruction
                for destruction in enemy_destructions
                if trap_ids.intersection(destruction.started_turn_terrain_feature_ids)
            )
            return _score_count_evidence(
                score_count=1 if matching else 0,
                destroyed_unit_instance_ids=tuple(
                    sorted({state.destroyed_unit_instance_id for state in matching})
                ),
                trapped_terrain_feature_ids=tuple(sorted(trap_ids)),
                destruction_ids=tuple(state.destruction_id for state in matching),
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
        requested_player_id = _validate_identifier("player_id", player_id)
        if requested_player_id != self.player_id:
            raise GameLifecycleError("Secondary scoring policy may score only its assigned player.")
        return VictoryPointAward(
            player_id=requested_player_id,
            battle_round=_validate_positive_int("battle_round", battle_round),
            phase=_validate_identifier("phase", phase),
            amount=rule.victory_points,
            source_kind=kind,
            source_id=requested_secondary_id,
            scoring_timing="secondary_mission_score",
            hidden=hidden,
            metadata={
                "secondary_scoring_provider_kind": (
                    SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                ),
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
        from warhammer40k_core.engine.missions import validate_mission_setup_source_layout

        validate_mission_setup_source_layout(mission_setup)
        if mission_setup.mission_pack_id != self.mission_pack_id:
            raise GameLifecycleError("Secondary scoring policy mission pack drifted from setup.")
        requested_player = _validate_identifier("player_id", player_id)
        if requested_player != self.player_id:
            raise GameLifecycleError("Secondary scoring policy may score only its assigned player.")
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
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.STATE_BACKED_OBJECTIVE_CONTROL.value
                    ),
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
        requested_player_id = _validate_identifier("player_id", player_id)
        if requested_player_id != self.player_id:
            raise GameLifecycleError(
                "Mission Action scoring policy may score only its assigned player."
            )
        return VictoryPointAward(
            player_id=requested_player_id,
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
        objective_control_records: tuple[ObjectiveControlRecord, ...],
        primary_scoring_state_evidence_records: tuple[_state.PrimaryScoringStateEvidence, ...],
        turn_order: tuple[str, ...],
        current_active_player_id: str | None,
    ) -> tuple[int, JsonValue]:
        if type(ledger) is not VictoryPointLedger:
            raise GameLifecycleError("VP cap resolution requires a VictoryPointLedger.")
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("VP cap resolution requires a VictoryPointAward.")
        if ledger.player_id != award.player_id:
            raise GameLifecycleError("VP cap resolution player_id drift.")
        if ledger.player_id != self.player_id:
            raise GameLifecycleError("VP cap policy does not belong to this player.")
        ledger_policy = validate_victory_point_ledger_policy(
            policy=self,
            ledger=ledger,
            objective_control_records=objective_control_records,
            primary_scoring_state_evidence_records=(primary_scoring_state_evidence_records),
            turn_order=turn_order,
        )
        cap_bucket = self.cap_bucket_for_victory_point_source(
            source_kind=award.source_kind,
            source_id=award.source_id,
        )
        primary_binding = None
        if award.source_kind is VictoryPointSourceKind.PRIMARY:
            if current_active_player_id is None:
                raise GameLifecycleError("Primary VP award validation requires an active player.")
            primary_binding = validate_primary_victory_point_award(
                policy=self,
                award=award,
                objective_control_records=objective_control_records,
                primary_scoring_state_evidence_records=(primary_scoring_state_evidence_records),
                turn_order=turn_order,
                expected_boundary_active_player_id=current_active_player_id,
            )
            if primary_binding.identity in ledger_policy.primary_binding_identities:
                raise GameLifecycleError(
                    "Primary VP ledger must not repeat a scoring rule at one boundary."
                )
        elif (
            cap_bucket is VictoryPointCapBucket.PRIMARY and award.scoring_timing == "end_of_battle"
        ):
            raise GameLifecycleError(
                "Only a source-backed Primary scoring rule may claim end-of-battle exemption."
            )
        end_of_battle_exempt = (
            primary_binding is not None
            and primary_binding.cap_treatment
            is PrimaryVictoryPointCapTreatment.END_OF_BATTLE_EXEMPT
        )
        from warhammer40k_core.engine.victory_point_cap_resolution import (
            resolve_victory_point_cap,
        )

        cap_resolution = resolve_victory_point_cap(
            policy=self,
            ledger=ledger,
            award=award,
            end_of_battle_transaction_ids=ledger_policy.end_of_battle_transaction_ids,
            end_of_battle_exempt=end_of_battle_exempt,
        )
        return cap_resolution.applied_amount, cap_resolution.metadata

    def to_payload(self) -> MissionScoringPolicyPayload:
        return {
            "player_id": self.player_id,
            "force_disposition_id": self.force_disposition_id,
            "mission_pack_id": self.mission_pack_id,
            "primary_mission_id": self.primary_mission_id,
            "primary_scoring_supported": self.primary_scoring_supported,
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
        if set(payload) != {
            "player_id",
            "force_disposition_id",
            "mission_pack_id",
            "primary_mission_id",
            "primary_scoring_supported",
            "game_length_battle_rounds",
            "primary_scoring_phase",
            "primary_scoring_timing",
            "primary_scoring_rule_id",
            "primary_scoring_rule_condition",
            "primary_scoring_rule_source_id",
            "primary_vp_per_controlled_objective",
            "primary_max_vp_per_turn",
            "primary_scoring_rules",
            "secondary_vp_per_score",
            "secondary_scoring_rules",
            "mission_action_scoring_rules",
            "mission_action_vp",
            "reserve_destruction_timing",
            "reserve_destruction_battle_round",
            "reserve_destruction_excludes_during_battle_strategic_reserves",
            "reserve_destruction_only_declare_battle_formations",
            "primary_vp_cap",
            "secondary_vp_cap",
            "battle_ready_vp",
            "total_vp_cap",
            "end_of_round_scoring_windows",
            "end_of_game_scoring_windows",
            "source_id",
        }:
            raise GameLifecycleError("MissionScoringPolicy payload fields are invalid.")
        return cls(
            player_id=payload["player_id"],
            force_disposition_id=payload["force_disposition_id"],
            mission_pack_id=payload["mission_pack_id"],
            primary_mission_id=payload["primary_mission_id"],
            primary_scoring_supported=payload["primary_scoring_supported"],
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
            if not self.primary_scoring_supported:
                raise GameLifecycleError(
                    "Primary mission scoring source is known but engine implementation is pending."
                )
            if _validate_identifier("source_id", source_id) != self.primary_mission_id:
                raise GameLifecycleError(
                    "Primary VP source does not match the player's assigned Primary mission."
                )
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


def _central_objective_ids(mission_setup: MissionSetup) -> tuple[str, ...]:
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_role is ObjectiveMarkerRole.CENTRAL
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


def _validate_primary_scoring_evidence_context(
    *,
    record: ObjectiveControlRecord,
    player_ids: tuple[str, ...],
    turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
    terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
    unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
) -> None:
    """Bind every Primary evidence row to this game and scoring boundary."""

    known_players = set(player_ids)
    for turn_start_state in turn_start_states:
        if turn_start_state.game_id != record.game_id:
            raise GameLifecycleError("Primary scoring turn-start evidence game_id drift.")
        if (
            turn_start_state.player_id not in known_players
            or turn_start_state.active_player_id not in known_players
        ):
            raise GameLifecycleError(
                "Primary scoring turn-start evidence references an unknown player."
            )
        if turn_start_state.battle_round > record.battle_round:
            raise GameLifecycleError(
                "Primary scoring turn-start evidence cannot come from a future battle round."
            )
    for terrain_trap_state in terrain_trap_states:
        if terrain_trap_state.game_id != record.game_id:
            raise GameLifecycleError("Primary scoring terrain-trap evidence game_id drift.")
        if (
            terrain_trap_state.player_id not in known_players
            or terrain_trap_state.active_player_id not in known_players
        ):
            raise GameLifecycleError(
                "Primary scoring terrain-trap evidence references an unknown player."
            )
        if terrain_trap_state.battle_round > record.battle_round:
            raise GameLifecycleError(
                "Primary scoring terrain-trap evidence cannot come from a future battle round."
            )
    for destruction_state in unit_destruction_states:
        if destruction_state.game_id != record.game_id:
            raise GameLifecycleError("Primary scoring destruction evidence game_id drift.")
        if (
            destruction_state.active_player_id not in known_players
            or destruction_state.destroyed_player_id not in known_players
            or (
                destruction_state.destroying_player_id is not None
                and destruction_state.destroying_player_id not in known_players
            )
        ):
            raise GameLifecycleError(
                "Primary scoring destruction evidence references an unknown player."
            )
        if destruction_state.battle_round > record.battle_round:
            raise GameLifecycleError(
                "Primary scoring destruction evidence cannot come from a future battle round."
            )


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
        if state.destroyed_player_id != requested_player
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
    validate_mission_scoring_resolution_groups(
        field_name="MissionScoringPolicy primary_scoring_rules",
        bindings=tuple(
            (
                value.rule_id,
                value.timing,
                value.source_kind.value,
                value.resolution_mode,
                value.resolution_group_id,
            )
            for value in validated
        ),
        error_factory=GameLifecycleError,
    )
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


def _identifier_tuple_from_payload_list(
    field_name: str,
    value: object,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise GameLifecycleError(f"{field_name} must be a list in serialized payloads.")
    return tuple(
        _validate_identifier(f"{field_name} value", item) for item in cast(list[object], value)
    )


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


_validate_identifier = IdentifierValidator(GameLifecycleError)


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
