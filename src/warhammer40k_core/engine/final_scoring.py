from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import (
    PlayerPrimaryMissionAssignment,
    PlayerPrimaryMissionAssignmentPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    ScoringWindowKind,
    ScoringWindowState,
    ScoringWindowStatePayload,
    VictoryPointCapBucket,
    VictoryPointLedger,
)


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
    primary_mission_assignments: list[PlayerPrimaryMissionAssignmentPayload]
    game_length_battle_rounds: int
    final_scores: list[FinalScorePayload]
    winner_player_ids: list[str]
    is_draw: bool
    scoring_audit: FinalScoringAuditPayload


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
        for field_name in (
            "victory_points",
            "raw_victory_points",
            "raw_primary_vp",
            "raw_secondary_vp",
            "raw_battle_ready_vp",
            "raw_other_vp",
            "capped_primary_vp",
            "capped_secondary_vp",
            "capped_battle_ready_vp",
            "capped_other_vp",
            "cap_adjustment",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_int(
                    f"FinalScoreLine {field_name}",
                    getattr(self, field_name),
                ),
            )
        capped_total = (
            self.capped_primary_vp
            + self.capped_secondary_vp
            + self.capped_battle_ready_vp
            + self.capped_other_vp
        )
        if capped_total != self.victory_points:
            raise GameLifecycleError("FinalScoreLine victory_points must match capped totals.")
        raw_total = (
            self.raw_primary_vp
            + self.raw_secondary_vp
            + self.raw_battle_ready_vp
            + self.raw_other_vp
        )
        if raw_total != self.raw_victory_points:
            raise GameLifecycleError("FinalScoreLine raw_victory_points must match raw totals.")
        raw_and_capped_components = (
            (self.raw_primary_vp, self.capped_primary_vp),
            (self.raw_secondary_vp, self.capped_secondary_vp),
            (self.raw_battle_ready_vp, self.capped_battle_ready_vp),
            (self.raw_other_vp, self.capped_other_vp),
        )
        if any(capped > raw for raw, capped in raw_and_capped_components):
            raise GameLifecycleError("FinalScoreLine components cannot be capped upward.")
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
        if ledger.player_id != policy.player_id:
            raise GameLifecycleError(
                "FinalScoreLine ledger and MissionScoringPolicy players must match."
            )
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
    primary_mission_assignments: tuple[PlayerPrimaryMissionAssignment, ...]
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
            "primary_mission_assignments",
            _validate_primary_mission_assignments(self.primary_mission_assignments),
        )
        object.__setattr__(
            self,
            "game_length_battle_rounds",
            _validate_positive_int(
                "FinalScoringResult game_length_battle_rounds",
                self.game_length_battle_rounds,
            ),
        )
        object.__setattr__(self, "final_scores", _validate_final_score_tuple(self.final_scores))
        object.__setattr__(
            self,
            "winner_player_ids",
            _validate_identifier_tuple_ordered(
                "FinalScoringResult winner_player_ids",
                self.winner_player_ids,
                min_length=1,
            ),
        )
        object.__setattr__(self, "is_draw", _validate_bool("is_draw", self.is_draw))
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
        if {assignment.player_id for assignment in self.primary_mission_assignments} != {
            score.player_id for score in self.final_scores
        }:
            raise GameLifecycleError(
                "FinalScoringResult player Primary missions must match final-score players."
            )
        expected_result_id = f"final-scoring:{self.game_id}:round-{self.battle_round:02d}"
        if self.result_id != expected_result_id:
            raise GameLifecycleError("FinalScoringResult result_id drifted from game and round.")
        _validate_canonical_policy_binding(self)

    @classmethod
    def from_ledgers(
        cls,
        *,
        game_id: str,
        battle_round: int,
        policies: MissionScoringPolicies,
        ledgers: tuple[VictoryPointLedger, ...],
        scoring_windows: tuple[ScoringWindowState, ...],
    ) -> Self:
        if type(policies) is not MissionScoringPolicies:
            raise GameLifecycleError("Final scoring requires MissionScoringPolicies.")
        policy = policies.common_policy
        requested_game_id = _validate_identifier("game_id", game_id)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_policy_source_id = _validate_identifier("policy_source_id", policies.source_id)
        validated_assignments = policies.primary_mission_assignments
        validated_windows = _validate_required_final_scoring_windows(
            scoring_windows=scoring_windows,
            policy=policy,
            game_id=requested_game_id,
            battle_round=requested_round,
        )
        final_score_lines: list[FinalScoreLine] = []
        for ledger in ledgers:
            player_policy = policies.policy_for_player(ledger.player_id)
            assignment = next(
                (
                    candidate
                    for candidate in validated_assignments
                    if candidate.player_id == ledger.player_id
                ),
                None,
            )
            if assignment is None:
                raise GameLifecycleError(
                    "Final scoring ledger player is missing a Primary mission assignment."
                )
            if (
                player_policy.player_id != assignment.player_id
                or player_policy.force_disposition_id != assignment.force_disposition_id
                or player_policy.primary_mission_id != assignment.primary_mission_id
                or player_policy.mission_pack_id != policy.mission_pack_id
            ):
                raise GameLifecycleError(
                    "Final scoring player policy drifted from the Primary mission assignment."
                )
            final_score_lines.append(
                FinalScoreLine.from_ledger(ledger=ledger, policy=player_policy)
            )
        final_scores = tuple(sorted(final_score_lines, key=lambda score: score.player_id))
        if not final_scores:
            raise GameLifecycleError("Final scoring requires at least one player score.")
        winner_ids = _winner_player_ids_from_scores(final_scores)
        return cls(
            result_id=f"final-scoring:{requested_game_id}:round-{requested_round:02d}",
            game_id=requested_game_id,
            battle_round=requested_round,
            mission_pack_id=policy.mission_pack_id,
            primary_mission_assignments=validated_assignments,
            game_length_battle_rounds=policy.game_length_battle_rounds,
            final_scores=final_scores,
            winner_player_ids=winner_ids,
            is_draw=len(winner_ids) != 1,
            policy_source_id=requested_policy_source_id,
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
            "primary_mission_assignments": [
                assignment.to_payload() for assignment in self.primary_mission_assignments
            ],
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
        if set(payload) != {
            "result_id",
            "game_id",
            "battle_round",
            "mission_pack_id",
            "primary_mission_assignments",
            "game_length_battle_rounds",
            "final_scores",
            "winner_player_ids",
            "is_draw",
            "scoring_audit",
        }:
            raise GameLifecycleError("FinalScoringResult payload fields are invalid.")
        audit = payload["scoring_audit"]
        if set(audit) != {
            "policy_source_id",
            "primary_vp_cap",
            "secondary_vp_cap",
            "battle_ready_vp_cap",
            "total_vp_cap",
            "scoring_windows",
            "player_scores",
        }:
            raise GameLifecycleError("FinalScoringResult scoring audit fields are invalid.")
        result = cls(
            result_id=payload["result_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            mission_pack_id=payload["mission_pack_id"],
            primary_mission_assignments=tuple(
                PlayerPrimaryMissionAssignment.from_payload(row)
                for row in payload["primary_mission_assignments"]
            ),
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


def _validate_canonical_policy_binding(result: FinalScoringResult) -> None:
    from warhammer40k_core.engine.missions import (
        mission_pack_for_id,
        primary_scoring_rules_from_definition,
    )

    mission_pack = mission_pack_for_id(result.mission_pack_id)
    scoring = mission_pack.scoring
    expected_common_fields = (
        ("policy_source_id", result.policy_source_id, f"{mission_pack.source_id}:scoring"),
        (
            "game_length_battle_rounds",
            result.game_length_battle_rounds,
            scoring.game_length_battle_rounds,
        ),
        ("primary_vp_cap", result.primary_vp_cap, scoring.primary_vp_cap),
        ("secondary_vp_cap", result.secondary_vp_cap, scoring.secondary_vp_cap),
        (
            "battle_ready_vp_cap",
            result.battle_ready_vp_cap,
            mission_pack.scoring_caps.battle_ready_vp,
        ),
        ("total_vp_cap", result.total_vp_cap, scoring.total_vp_cap),
    )
    for field_name, actual, expected in expected_common_fields:
        if actual != expected:
            raise GameLifecycleError(f"FinalScoringResult {field_name} drifted from source policy.")

    primary_by_id = {
        primary.primary_mission_id: primary for primary in mission_pack.primary_missions
    }
    assignments = result.primary_mission_assignments
    for assignment in assignments:
        opponent = next(
            candidate for candidate in assignments if candidate.player_id != assignment.player_id
        )
        expected_cell = mission_pack.primary_mission_matrix_cell(
            player_force_disposition_id=assignment.force_disposition_id,
            opponent_force_disposition_id=opponent.force_disposition_id,
        )
        if assignment.primary_mission_id != expected_cell.primary_mission_id:
            raise GameLifecycleError(
                "FinalScoringResult Primary assignment drifted from directional matrix."
            )
        primary = primary_by_id.get(assignment.primary_mission_id)
        if primary is None:
            raise GameLifecycleError(
                "FinalScoringResult Primary assignment is missing from mission pack."
            )
        primary_scoring_rules_from_definition(primary)

    _validate_required_scoring_windows(
        scoring_windows=result.scoring_windows,
        game_id=result.game_id,
        battle_round=result.battle_round,
        end_of_round_scoring_windows=scoring.end_of_round_scoring_windows,
        end_of_game_scoring_windows=scoring.end_of_game_scoring_windows,
    )
    for window in result.scoring_windows:
        expected_window_id = (
            f"scoring-window:{result.game_id}:round-{window.battle_round:02d}:"
            f"{window.window_kind.value}:{window.window}"
        )
        expected_source_id = (
            f"{result.policy_source_id}:window:{window.window_kind.value}:{window.window}"
        )
        if window.window_id != expected_window_id or window.source_id != expected_source_id:
            raise GameLifecycleError(
                "FinalScoringResult scoring window identity drifted from source policy."
            )
    for score in result.final_scores:
        expected_primary = min(score.raw_primary_vp, result.primary_vp_cap)
        expected_secondary = min(score.raw_secondary_vp, result.secondary_vp_cap)
        expected_battle_ready = min(
            score.raw_battle_ready_vp,
            result.battle_ready_vp_cap,
        )
        expected_pre_total = (
            expected_primary + expected_secondary + expected_battle_ready + score.raw_other_vp
        )
        expected_total = min(expected_pre_total, result.total_vp_cap)
        expected_other = (
            expected_total - expected_primary - expected_secondary - expected_battle_ready
        )
        if expected_other < 0:
            raise GameLifecycleError("FinalScoreLine source caps exceed total VP cap.")
        if (
            score.capped_primary_vp != expected_primary
            or score.capped_secondary_vp != expected_secondary
            or score.capped_battle_ready_vp != expected_battle_ready
            or score.capped_other_vp != expected_other
            or score.victory_points != expected_total
            or score.cap_adjustment != score.raw_victory_points - expected_total
        ):
            raise GameLifecycleError("FinalScoreLine cap transform drifted from source policy.")


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


def _validate_primary_mission_assignments(
    values: object,
) -> tuple[PlayerPrimaryMissionAssignment, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("primary_mission_assignments must be a tuple.")
    validated: list[PlayerPrimaryMissionAssignment] = []
    seen_players: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlayerPrimaryMissionAssignment:
            raise GameLifecycleError(
                "primary_mission_assignments must contain PlayerPrimaryMissionAssignment values."
            )
        if value.player_id in seen_players:
            raise GameLifecycleError("primary_mission_assignments must not duplicate players.")
        seen_players.add(value.player_id)
        validated.append(value)
    if len(validated) != 2:
        raise GameLifecycleError("primary_mission_assignments must contain exactly two players.")
    return tuple(sorted(validated, key=lambda assignment: assignment.player_id))


def _validate_required_final_scoring_windows(
    *,
    scoring_windows: tuple[ScoringWindowState, ...],
    policy: MissionScoringPolicy,
    game_id: str,
    battle_round: int,
) -> tuple[ScoringWindowState, ...]:
    if type(policy) is not MissionScoringPolicy:
        raise GameLifecycleError("Final scoring window validation requires MissionScoringPolicy.")
    return _validate_required_scoring_windows(
        scoring_windows=scoring_windows,
        game_id=game_id,
        battle_round=battle_round,
        end_of_round_scoring_windows=policy.end_of_round_scoring_windows,
        end_of_game_scoring_windows=policy.end_of_game_scoring_windows,
    )


def _validate_required_scoring_windows(
    *,
    scoring_windows: tuple[ScoringWindowState, ...],
    game_id: str,
    battle_round: int,
    end_of_round_scoring_windows: tuple[str, ...],
    end_of_game_scoring_windows: tuple[str, ...],
) -> tuple[ScoringWindowState, ...]:
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
        for window in end_of_round_scoring_windows
    } | {
        (ScoringWindowKind.END_OF_GAME, window, requested_round)
        for window in end_of_game_scoring_windows
    }
    drifted = tuple(sorted(required ^ recorded, key=lambda item: (item[0].value, item[1], item[2])))
    if drifted:
        drifted_text = ", ".join(
            f"{kind.value}:{window}:round-{round_number:02d}"
            for kind, window, round_number in drifted
        )
        raise GameLifecycleError(
            f"Final scoring requires recorded policy windows exactly: {drifted_text}."
        )
    return validated_windows


def _validate_identifier_tuple_ordered(
    field_name: str,
    values: object,
    *,
    min_length: int,
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
    return tuple(validated)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative integer.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "FinalScoreLine",
    "FinalScoreLinePayload",
    "FinalScorePayload",
    "FinalScoringAuditPayload",
    "FinalScoringResult",
    "FinalScoringResultPayload",
)
