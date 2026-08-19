from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    PlayerPrimaryMissionAssignment,
    PlayerPrimaryMissionAssignmentPayload,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_history_evidence import (
    primary_unit_destruction_states_for_evidence,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.primary_scoring_turn_scope import (
    primary_scoring_rule_applies_at_record,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    MissionScoringPolicyPayload,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.secondary_scoring_conditions import SecondaryScoringConditionContext
from warhammer40k_core.engine.unit_state import StartingStrengthRecord

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


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

    def scoring_player_ids_for_record(
        self,
        *,
        record: ObjectiveControlRecord,
        turn_order: tuple[str, ...],
        end_of_battle: bool,
    ) -> tuple[str, ...]:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("Primary scoring requires an ObjectiveControlRecord.")
        if type(end_of_battle) is not bool:
            raise GameLifecycleError("Primary scoring end_of_battle must be a bool.")
        if end_of_battle:
            return tuple(turn_order)
        return tuple(
            player_id
            for player_id in turn_order
            for policy in (self.policy_for_player(player_id),)
            if any(
                primary_scoring_rule_applies_at_record(
                    timing=rule.timing,
                    condition=rule.condition,
                    record=record,
                    scoring_player_id=policy.player_id,
                    primary_scoring_phase=policy.primary_scoring_phase,
                    primary_scoring_timing=policy.primary_scoring_timing,
                    game_length_battle_rounds=policy.game_length_battle_rounds,
                    end_of_battle=False,
                )
                for rule in policy.primary_scoring_rules
            )
        )

    def primary_awards_from_objective_control(
        self,
        *,
        record: ObjectiveControlRecord,
        authoritative_state: GameState,
        end_of_battle: bool = False,
    ) -> tuple[VictoryPointAward, ...]:
        from warhammer40k_core.engine.game_state import GameState
        from warhammer40k_core.engine.primary_scoring_state_evidence import (
            build_primary_scoring_state_evidence,
        )

        if type(authoritative_state) is not GameState:
            raise GameLifecycleError("Primary scoring authority requires GameState.")
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("Primary scoring requires an ObjectiveControlRecord.")
        if type(end_of_battle) is not bool:
            raise GameLifecycleError("Primary scoring end_of_battle must be a bool.")
        authoritative_setup = authoritative_state.mission_setup
        if type(authoritative_setup) is not MissionSetup:
            raise GameLifecycleError("Primary scoring authority requires MissionSetup.")
        self.validate_mission_setup(authoritative_setup)
        state_evidence = build_primary_scoring_state_evidence(
            state=authoritative_state,
            record=record,
            end_of_battle=end_of_battle,
        )
        return self.primary_awards_from_state_evidence(
            record=record,
            authoritative_state=authoritative_state,
            state_evidence=state_evidence,
        )

    def primary_awards_from_state_evidence(
        self,
        *,
        record: ObjectiveControlRecord,
        authoritative_state: GameState,
        state_evidence: PrimaryScoringStateEvidence,
    ) -> tuple[VictoryPointAward, ...]:
        """Re-evaluate one persisted Primary boundary through the normal policy path."""
        from warhammer40k_core.engine.game_state import GameState

        if type(authoritative_state) is not GameState:
            raise GameLifecycleError("Primary scoring authority requires GameState.")
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("Primary scoring requires an ObjectiveControlRecord.")
        if type(state_evidence) is not PrimaryScoringStateEvidence:
            raise GameLifecycleError("Primary scoring requires typed state evidence.")
        authoritative_setup = authoritative_state.mission_setup
        if type(authoritative_setup) is not MissionSetup:
            raise GameLifecycleError("Primary scoring authority requires MissionSetup.")
        self.validate_mission_setup(authoritative_setup)
        end_of_battle = (
            state_evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.END_OF_BATTLE
        )
        player_ids = self.scoring_player_ids_for_record(
            record=record,
            turn_order=tuple(authoritative_state.turn_order),
            end_of_battle=end_of_battle,
        )
        turn_start_states = tuple(
            value
            for value in authoritative_state.primary_objective_turn_start_states
            if _primary_history_row_is_not_after_boundary(
                battle_round=value.battle_round,
                active_player_id=value.active_player_id,
                phase=value.source_objective_control_record.phase,
                record=record,
                state=authoritative_state,
            )
        )
        terrain_trap_states = tuple(
            value
            for value in authoritative_state.primary_terrain_trap_states
            if _primary_history_row_is_not_after_boundary(
                battle_round=value.battle_round,
                active_player_id=value.active_player_id,
                phase=value.phase,
                record=record,
                state=authoritative_state,
            )
        )
        unit_destruction_states = primary_unit_destruction_states_for_evidence(
            state=authoritative_state,
            destruction_state_ids=state_evidence.primary_unit_destruction_state_ids,
        )
        awards: list[VictoryPointAward] = []
        for player_id in player_ids:
            policy = self.policy_for_player(player_id)
            if not policy.primary_scoring_supported:
                continue
            awards.extend(
                policy.primary_awards_from_objective_control(
                    record=record,
                    mission_setup=authoritative_setup,
                    turn_order=authoritative_state.turn_order,
                    turn_start_states=turn_start_states,
                    terrain_trap_states=terrain_trap_states,
                    unit_destruction_states=unit_destruction_states,
                    state_evidence=state_evidence,
                    spatial_evidence=next(
                        (
                            evidence
                            for evidence in (
                                state_evidence.primary_scoring_spatial_evidence_by_player_id
                            )
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
        condition_context: SecondaryScoringConditionContext | None = None,
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
            condition_context=condition_context,
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
        primary_scoring_state_evidence_records: tuple[PrimaryScoringStateEvidence, ...],
        turn_order: tuple[str, ...],
        current_active_player_id: str | None,
    ) -> tuple[int, JsonValue]:
        return self.policy_for_player(ledger.player_id).capped_award_for_ledger(
            ledger=ledger,
            award=award,
            objective_control_records=objective_control_records,
            primary_scoring_state_evidence_records=(primary_scoring_state_evidence_records),
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


def _primary_history_row_is_not_after_boundary(
    *,
    battle_round: int,
    active_player_id: str,
    phase: str,
    record: ObjectiveControlRecord,
    state: GameState,
) -> bool:
    """Compare one append-only Primary history row with a scoring boundary."""
    turn_index_by_player_id = {player_id: index for index, player_id in enumerate(state.turn_order)}
    if active_player_id not in turn_index_by_player_id:
        raise GameLifecycleError("Primary scoring history active player is not in turn_order.")
    if record.active_player_id not in turn_index_by_player_id:
        raise GameLifecycleError("Primary scoring boundary active player is not in turn_order.")
    phase_index_by_name = {
        battle_phase.value: index for index, battle_phase in enumerate(state.battle_phase_sequence)
    }
    if phase not in phase_index_by_name:
        raise GameLifecycleError("Primary scoring history phase is not in the battle sequence.")
    if record.phase not in phase_index_by_name:
        raise GameLifecycleError("Primary scoring boundary phase is not in the battle sequence.")
    return (
        battle_round,
        turn_index_by_player_id[active_player_id],
        phase_index_by_name[phase],
    ) <= (
        record.battle_round,
        turn_index_by_player_id[record.active_player_id],
        phase_index_by_name[record.phase],
    )


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


_identifier = IdentifierValidator(GameLifecycleError)
