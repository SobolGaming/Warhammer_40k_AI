from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    PlayerPrimaryMissionAssignment,
    PlayerPrimaryMissionAssignmentPayload,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PrimaryScoringSpatialEvidence,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    MissionScoringPolicyPayload,
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


class MissionScoringPoliciesPayload(TypedDict):
    source_id: str
    mission_setup_source_id: str
    mission_pool_entry_id: str
    primary_mission_assignments: list[PlayerPrimaryMissionAssignmentPayload]
    player_policies: list[MissionScoringPolicyPayload]


@dataclass(frozen=True, slots=True)
class MissionScoringPolicies:
    """The two player-bound Primary policies plus their shared mission rules."""

    source_id: str
    mission_setup_source_id: str
    mission_pool_entry_id: str
    primary_mission_assignments: tuple[PlayerPrimaryMissionAssignment, ...]
    player_policies: tuple[MissionScoringPolicy, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _identifier("MissionScoringPolicies source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "mission_setup_source_id",
            _identifier(
                "MissionScoringPolicies mission_setup_source_id", self.mission_setup_source_id
            ),
        )
        object.__setattr__(
            self,
            "mission_pool_entry_id",
            _identifier("MissionScoringPolicies mission_pool_entry_id", self.mission_pool_entry_id),
        )
        assignments = _validate_assignments(self.primary_mission_assignments)
        policies = _validate_player_policies(self.player_policies)
        _validate_common_policy_fields(policies)
        _validate_policy_assignments(policies=policies, assignments=assignments)
        _validate_primary_resolution_group_ownership(policies)
        object.__setattr__(self, "primary_mission_assignments", assignments)
        object.__setattr__(self, "player_policies", policies)

    @property
    def common_policy(self) -> MissionScoringPolicy:
        return self.player_policies[0]

    @property
    def mission_pack_id(self) -> str:
        return self.common_policy.mission_pack_id

    @property
    def game_length_battle_rounds(self) -> int:
        return self.common_policy.game_length_battle_rounds

    @property
    def end_of_round_scoring_windows(self) -> tuple[str, ...]:
        return self.common_policy.end_of_round_scoring_windows

    @property
    def end_of_game_scoring_windows(self) -> tuple[str, ...]:
        return self.common_policy.end_of_game_scoring_windows

    def policy_for_player(self, player_id: str) -> MissionScoringPolicy:
        requested_player_id = _identifier("player_id", player_id)
        for policy in self.player_policies:
            if policy.player_id == requested_player_id:
                return policy
        raise GameLifecycleError("Mission scoring policy does not contain player_id.")

    def primary_awards_from_objective_control(
        self,
        *,
        record: ObjectiveControlRecord,
        mission_setup: MissionSetup,
        turn_order: tuple[str, ...],
        turn_start_states: tuple[PrimaryObjectiveTurnStartState, ...],
        terrain_trap_states: tuple[PrimaryTerrainTrapState, ...],
        unit_destruction_states: tuple[PrimaryUnitDestructionState, ...],
        spatial_evidence_by_player_id: tuple[PrimaryScoringSpatialEvidence, ...] = (),
        scoring_player_ids: tuple[str, ...] = (),
        end_of_battle: bool = False,
    ) -> tuple[VictoryPointAward, ...]:
        self.validate_mission_setup(mission_setup)
        player_ids = _validate_scoring_player_ids(
            scoring_player_ids,
            policies=self,
            default_player_id=record.active_player_id,
        )
        if not end_of_battle and player_ids != (record.active_player_id,):
            raise GameLifecycleError(
                "Ordinary Primary scoring must use the active player's policy."
            )
        spatial_evidence = _validate_spatial_evidence(
            spatial_evidence_by_player_id,
            scoring_player_ids=player_ids,
        )
        awards: list[VictoryPointAward] = []
        for player_id in player_ids:
            policy = self.policy_for_player(player_id)
            awards.extend(
                policy.primary_awards_from_objective_control(
                    record=record,
                    mission_setup=mission_setup,
                    turn_order=turn_order,
                    turn_start_states=turn_start_states,
                    terrain_trap_states=terrain_trap_states,
                    unit_destruction_states=unit_destruction_states,
                    spatial_evidence=next(
                        (
                            evidence
                            for evidence in spatial_evidence
                            if evidence.player_id == player_id
                        ),
                        None,
                    ),
                    scoring_player_ids=(policy.player_id,),
                    end_of_battle=end_of_battle,
                )
            )
        return tuple(awards)

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
        return self.policy_for_player(player_id).secondary_award(
            player_id=player_id,
            battle_round=battle_round,
            phase=phase,
            secondary_mission_id=secondary_mission_id,
            source_kind=source_kind,
            hidden=hidden,
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
        self.validate_mission_setup(mission_setup)
        return self.policy_for_player(player_id).secondary_award_from_mission_state(
            player_id=player_id,
            battle_round=battle_round,
            phase=phase,
            secondary_mission_id=secondary_mission_id,
            source_kind=source_kind,
            hidden=hidden,
            record=record,
            mission_setup=mission_setup,
            unit_destruction_states=unit_destruction_states,
            objective_cleanse_states=objective_cleanse_states,
            terrain_plunder_states=terrain_plunder_states,
            enemy_unit_ids_in_player_deployment_zone=enemy_unit_ids_in_player_deployment_zone,
            starting_strength_records=starting_strength_records,
        )

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
        return self.policy_for_player(player_id).mission_action_award(
            player_id=player_id,
            battle_round=battle_round,
            phase=phase,
            action_id=action_id,
            source_id=source_id,
            amount=amount,
        )

    def capped_award_for_ledger(
        self,
        *,
        ledger: VictoryPointLedger,
        award: VictoryPointAward,
        objective_control_records: tuple[ObjectiveControlRecord, ...],
        turn_order: tuple[str, ...],
        current_active_player_id: str | None,
    ) -> tuple[int, JsonValue]:
        return self.policy_for_player(ledger.player_id).capped_award_for_ledger(
            ledger=ledger,
            award=award,
            objective_control_records=objective_control_records,
            turn_order=turn_order,
            current_active_player_id=current_active_player_id,
        )

    def to_payload(self) -> MissionScoringPoliciesPayload:
        return {
            "source_id": self.source_id,
            "mission_setup_source_id": self.mission_setup_source_id,
            "mission_pool_entry_id": self.mission_pool_entry_id,
            "primary_mission_assignments": [
                assignment.to_payload() for assignment in self.primary_mission_assignments
            ],
            "player_policies": [policy.to_payload() for policy in self.player_policies],
        }

    @classmethod
    def from_payload(cls, payload: MissionScoringPoliciesPayload) -> Self:
        if set(payload) != {
            "source_id",
            "mission_setup_source_id",
            "mission_pool_entry_id",
            "primary_mission_assignments",
            "player_policies",
        }:
            raise GameLifecycleError("MissionScoringPolicies payload fields are invalid.")
        return cls(
            source_id=payload["source_id"],
            mission_setup_source_id=payload["mission_setup_source_id"],
            mission_pool_entry_id=payload["mission_pool_entry_id"],
            primary_mission_assignments=tuple(
                PlayerPrimaryMissionAssignment.from_payload(assignment)
                for assignment in payload["primary_mission_assignments"]
            ),
            player_policies=tuple(
                MissionScoringPolicy.from_payload(policy) for policy in payload["player_policies"]
            ),
        )

    def validate_mission_setup(self, mission_setup: MissionSetup) -> None:
        if type(mission_setup) is not MissionSetup:
            raise GameLifecycleError("Mission scoring requires MissionSetup.")
        if (
            mission_setup.mission_pack_id != self.mission_pack_id
            or mission_setup.source_id != self.mission_setup_source_id
            or mission_setup.mission_pool_entry_id != self.mission_pool_entry_id
            or mission_setup.primary_mission_assignments != self.primary_mission_assignments
        ):
            raise GameLifecycleError("Mission scoring policies drifted from MissionSetup.")
        from warhammer40k_core.engine.missions import validate_mission_setup_source_layout

        validate_mission_setup_source_layout(mission_setup)


def _validate_player_policies(values: object) -> tuple[MissionScoringPolicy, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MissionScoringPolicies player_policies must be a tuple.")
    validated: list[MissionScoringPolicy] = []
    seen_players: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not MissionScoringPolicy:
            raise GameLifecycleError(
                "MissionScoringPolicies player_policies must contain scoring policies."
            )
        if value.player_id in seen_players:
            raise GameLifecycleError(
                "MissionScoringPolicies player_policies must not duplicate players."
            )
        seen_players.add(value.player_id)
        validated.append(value)
    if len(validated) != 2:
        raise GameLifecycleError(
            "MissionScoringPolicies player_policies must contain exactly two players."
        )
    return tuple(sorted(validated, key=lambda policy: policy.player_id))


def _validate_common_policy_fields(policies: tuple[MissionScoringPolicy, ...]) -> None:
    first, second = policies
    common_fields = (
        "mission_pack_id",
        "game_length_battle_rounds",
        "primary_scoring_phase",
        "primary_scoring_timing",
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
    )
    for field_name in common_fields:
        if getattr(first, field_name) != getattr(second, field_name):
            raise GameLifecycleError(f"MissionScoringPolicies shared field drifted: {field_name}.")


def _validate_primary_resolution_group_ownership(
    policies: tuple[MissionScoringPolicy, ...],
) -> None:
    mission_id_by_group_id: dict[str, str] = {}
    for policy in policies:
        for rule in policy.primary_scoring_rules:
            group_id = rule.resolution_group_id
            if group_id is None:
                continue
            existing_mission_id = mission_id_by_group_id.get(group_id)
            if existing_mission_id is not None and existing_mission_id != policy.primary_mission_id:
                raise GameLifecycleError(
                    "Primary scoring resolution groups must not span mission cards."
                )
            mission_id_by_group_id[group_id] = policy.primary_mission_id


def _validate_assignments(
    values: object,
) -> tuple[PlayerPrimaryMissionAssignment, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "MissionScoringPolicies primary_mission_assignments must be a tuple."
        )
    assignments: list[PlayerPrimaryMissionAssignment] = []
    seen_players: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlayerPrimaryMissionAssignment:
            raise GameLifecycleError(
                "MissionScoringPolicies assignments must contain Primary assignments."
            )
        if value.player_id in seen_players:
            raise GameLifecycleError(
                "MissionScoringPolicies assignments must not duplicate players."
            )
        seen_players.add(value.player_id)
        assignments.append(value)
    if len(assignments) != 2:
        raise GameLifecycleError("MissionScoringPolicies requires exactly two assignments.")
    return tuple(sorted(assignments, key=lambda assignment: assignment.player_id))


def _validate_policy_assignments(
    *,
    policies: tuple[MissionScoringPolicy, ...],
    assignments: tuple[PlayerPrimaryMissionAssignment, ...],
) -> None:
    assignment_by_player = {assignment.player_id: assignment for assignment in assignments}
    if set(assignment_by_player) != {policy.player_id for policy in policies}:
        raise GameLifecycleError("MissionScoringPolicies assignment players drifted.")
    for policy in policies:
        assignment = assignment_by_player[policy.player_id]
        if (
            policy.force_disposition_id != assignment.force_disposition_id
            or policy.primary_mission_id != assignment.primary_mission_id
        ):
            raise GameLifecycleError("MissionScoringPolicies policy assignment drifted.")


def _validate_scoring_player_ids(
    values: object,
    *,
    policies: MissionScoringPolicies,
    default_player_id: str,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("scoring_player_ids must be a tuple.")
    requested_values = cast(tuple[object, ...], values)
    if not requested_values:
        return (policies.policy_for_player(default_player_id).player_id,)
    player_ids: list[str] = []
    seen: set[str] = set()
    for value in requested_values:
        player_id = _identifier("scoring_player_ids value", value)
        if player_id in seen:
            raise GameLifecycleError("scoring_player_ids must not contain duplicates.")
        policies.policy_for_player(player_id)
        seen.add(player_id)
        player_ids.append(player_id)
    return tuple(player_ids)


def _validate_spatial_evidence(
    values: object,
    *,
    scoring_player_ids: tuple[str, ...],
) -> tuple[PrimaryScoringSpatialEvidence, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Primary scoring spatial evidence must be a tuple.")
    evidence_rows: list[PrimaryScoringSpatialEvidence] = []
    seen_player_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryScoringSpatialEvidence:
            raise GameLifecycleError(
                "Primary scoring spatial evidence must contain typed evidence."
            )
        if value.player_id not in scoring_player_ids:
            raise GameLifecycleError(
                "Primary scoring spatial evidence belongs to a non-scoring player."
            )
        if value.player_id in seen_player_ids:
            raise GameLifecycleError("Primary scoring spatial evidence must not duplicate players.")
        seen_player_ids.add(value.player_id)
        evidence_rows.append(value)
    return tuple(sorted(evidence_rows, key=lambda evidence: evidence.player_id))


_identifier = IdentifierValidator(GameLifecycleError)
