from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.descriptor_hash import (
    canonical_payload_sha256,
    validate_sha256_hex,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    objective_control_timing_from_token,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    PrimaryBattlefieldDepartureStatePayload,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryMissionProgressState,
    PrimaryMissionProgressStatePayload,
)
from warhammer40k_core.engine.primary_scoring_action_policy import (
    PrimaryScoringActionPolicy,
    primary_scoring_action_policies_by_id,
)
from warhammer40k_core.engine.primary_scoring_history_evidence import (
    primary_unit_destruction_state_ids_for_boundary,
    validate_primary_battlefield_departure_states,
    validate_primary_mission_action_states,
    validate_primary_unit_destruction_state_ids,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitness,
    PrimaryScoringRulesUnitPositionWitnessPayload,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PrimaryScoringSpatialEvidence,
    PrimaryScoringSpatialEvidencePayload,
    build_primary_scoring_spatial_evidence,
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence_integrity import (
    validate_primary_scoring_action_boundary,
    validate_primary_scoring_boundary_context,
    validate_primary_scoring_progress_boundary,
    validate_primary_scoring_state_evidence_restore_authority,
)
from warhammer40k_core.engine.primary_scoring_state_evidence_spatial_integrity import (
    validate_primary_scoring_spatial_rows_context,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_views_from_armies

if TYPE_CHECKING:
    from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatePayload
    from warhammer40k_core.engine.game_state import GameState


PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA = "primary-scoring-state-evidence-v1"
_PRIMARY_SCORING_STATE_EVIDENCE_ID_PREFIX = "primary-scoring-state-evidence"


class PrimaryScoringBoundaryKind(StrEnum):
    ORDINARY = "ordinary"
    END_OF_BATTLE = "end_of_battle"


class PrimaryScoringStateEvidencePayload(TypedDict):
    schema_version: str
    game_id: str
    battlefield_id: str
    battle_round: int
    active_player_id: str
    phase: str
    timing: str
    scoring_boundary_kind: str
    objective_control_record_id: str
    objective_control_record_hash: str
    primary_mission_progress_state: PrimaryMissionProgressStatePayload
    primary_mission_action_states: list[MissionActionStatePayload]
    primary_battlefield_departure_states: list[PrimaryBattlefieldDepartureStatePayload]
    primary_unit_destruction_state_ids: list[str]
    current_rules_unit_position_witnesses: list[PrimaryScoringRulesUnitPositionWitnessPayload]
    primary_scoring_spatial_evidence_by_player_id: list[PrimaryScoringSpatialEvidencePayload]
    evidence_id: str
    evidence_hash: str


@dataclass(frozen=True, slots=True)
class PrimaryScoringStateEvidence:
    """Content-addressed authoritative state consumed by Primary scoring."""

    schema_version: str
    game_id: str
    battlefield_id: str
    battle_round: int
    active_player_id: str
    phase: str
    timing: ObjectiveControlTiming
    scoring_boundary_kind: PrimaryScoringBoundaryKind
    objective_control_record_id: str
    objective_control_record_hash: str
    primary_mission_progress_state: PrimaryMissionProgressState
    primary_mission_action_states: tuple[MissionActionState, ...]
    primary_battlefield_departure_states: tuple[PrimaryBattlefieldDepartureState, ...]
    primary_unit_destruction_state_ids: tuple[str, ...]
    current_rules_unit_position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...]
    primary_scoring_spatial_evidence_by_player_id: tuple[PrimaryScoringSpatialEvidence, ...]
    evidence_id: str
    evidence_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "game_id",
            "battlefield_id",
            "active_player_id",
            "phase",
            "objective_control_record_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(
                    f"PrimaryScoringStateEvidence {field_name}",
                    getattr(self, field_name),
                ),
            )
        if self.schema_version != PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA:
            raise GameLifecycleError("Primary scoring state evidence schema is unsupported.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "PrimaryScoringStateEvidence battle_round",
                self.battle_round,
            ),
        )
        if type(self.timing) is not ObjectiveControlTiming:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence timing must be ObjectiveControlTiming."
            )
        if type(self.scoring_boundary_kind) is not PrimaryScoringBoundaryKind:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence scoring_boundary_kind must be typed."
            )
        object.__setattr__(
            self,
            "objective_control_record_hash",
            validate_sha256_hex(
                self.objective_control_record_hash,
                field_name="PrimaryScoringStateEvidence objective_control_record_hash",
                error_type=GameLifecycleError,
            ),
        )
        if type(self.primary_mission_progress_state) is not PrimaryMissionProgressState:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence requires typed Primary mission progress."
            )
        object.__setattr__(
            self,
            "primary_mission_action_states",
            validate_primary_mission_action_states(self.primary_mission_action_states),
        )
        object.__setattr__(
            self,
            "primary_battlefield_departure_states",
            validate_primary_battlefield_departure_states(
                self.primary_battlefield_departure_states
            ),
        )
        object.__setattr__(
            self,
            "primary_unit_destruction_state_ids",
            validate_primary_unit_destruction_state_ids(self.primary_unit_destruction_state_ids),
        )
        object.__setattr__(
            self,
            "current_rules_unit_position_witnesses",
            _validate_position_witnesses(self.current_rules_unit_position_witnesses),
        )
        object.__setattr__(
            self,
            "primary_scoring_spatial_evidence_by_player_id",
            _validate_spatial_evidence_rows(self.primary_scoring_spatial_evidence_by_player_id),
        )
        object.__setattr__(
            self,
            "evidence_hash",
            validate_sha256_hex(
                self.evidence_hash,
                field_name="PrimaryScoringStateEvidence evidence_hash",
                error_type=GameLifecycleError,
            ),
        )
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("PrimaryScoringStateEvidence evidence_id", self.evidence_id),
        )
        expected_hash = canonical_payload_sha256(self._content_payload())
        if self.evidence_hash != expected_hash:
            raise GameLifecycleError("Primary scoring state evidence hash drifted.")
        if self.evidence_id != f"{_PRIMARY_SCORING_STATE_EVIDENCE_ID_PREFIX}:{expected_hash}":
            raise GameLifecycleError("Primary scoring state evidence identity drifted.")

    @classmethod
    def create(
        cls,
        *,
        game_id: str,
        battlefield_id: str,
        battle_round: int,
        active_player_id: str,
        phase: str,
        timing: ObjectiveControlTiming,
        scoring_boundary_kind: PrimaryScoringBoundaryKind,
        objective_control_record_id: str,
        objective_control_record_hash: str,
        primary_mission_progress_state: PrimaryMissionProgressState,
        primary_mission_action_states: tuple[MissionActionState, ...],
        primary_battlefield_departure_states: tuple[PrimaryBattlefieldDepartureState, ...],
        primary_unit_destruction_state_ids: tuple[str, ...],
        current_rules_unit_position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
        primary_scoring_spatial_evidence_by_player_id: tuple[PrimaryScoringSpatialEvidence, ...],
    ) -> Self:
        validated_game_id = _validate_identifier("game_id", game_id)
        validated_battlefield_id = _validate_identifier("battlefield_id", battlefield_id)
        validated_round = _validate_positive_int("battle_round", battle_round)
        validated_active_player = _validate_identifier("active_player_id", active_player_id)
        validated_phase = _validate_identifier("phase", phase)
        if type(timing) is not ObjectiveControlTiming:
            raise GameLifecycleError(
                "Primary scoring state evidence creation requires ObjectiveControlTiming."
            )
        if type(scoring_boundary_kind) is not PrimaryScoringBoundaryKind:
            raise GameLifecycleError(
                "Primary scoring state evidence creation requires a boundary kind."
            )
        validated_record_id = _validate_identifier(
            "objective_control_record_id",
            objective_control_record_id,
        )
        validated_record_hash = validate_sha256_hex(
            objective_control_record_hash,
            field_name="objective_control_record_hash",
            error_type=GameLifecycleError,
        )
        if type(primary_mission_progress_state) is not PrimaryMissionProgressState:
            raise GameLifecycleError(
                "Primary scoring state evidence creation requires typed progress."
            )
        actions = validate_primary_mission_action_states(primary_mission_action_states)
        departures = validate_primary_battlefield_departure_states(
            primary_battlefield_departure_states
        )
        destruction_state_ids = validate_primary_unit_destruction_state_ids(
            primary_unit_destruction_state_ids
        )
        positions = _validate_position_witnesses(current_rules_unit_position_witnesses)
        spatial_rows = _validate_spatial_evidence_rows(
            primary_scoring_spatial_evidence_by_player_id
        )
        content = _primary_scoring_state_content_payload(
            schema_version=PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA,
            game_id=validated_game_id,
            battlefield_id=validated_battlefield_id,
            battle_round=validated_round,
            active_player_id=validated_active_player,
            phase=validated_phase,
            timing=timing,
            scoring_boundary_kind=scoring_boundary_kind,
            objective_control_record_id=validated_record_id,
            objective_control_record_hash=validated_record_hash,
            primary_mission_progress_state=primary_mission_progress_state,
            primary_mission_action_states=actions,
            primary_battlefield_departure_states=departures,
            primary_unit_destruction_state_ids=destruction_state_ids,
            current_rules_unit_position_witnesses=positions,
            primary_scoring_spatial_evidence_by_player_id=spatial_rows,
        )
        digest = canonical_payload_sha256(content)
        return cls(
            schema_version=PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA,
            game_id=validated_game_id,
            battlefield_id=validated_battlefield_id,
            battle_round=validated_round,
            active_player_id=validated_active_player,
            phase=validated_phase,
            timing=timing,
            scoring_boundary_kind=scoring_boundary_kind,
            objective_control_record_id=validated_record_id,
            objective_control_record_hash=validated_record_hash,
            primary_mission_progress_state=primary_mission_progress_state,
            primary_mission_action_states=actions,
            primary_battlefield_departure_states=departures,
            primary_unit_destruction_state_ids=destruction_state_ids,
            current_rules_unit_position_witnesses=positions,
            primary_scoring_spatial_evidence_by_player_id=spatial_rows,
            evidence_id=f"{_PRIMARY_SCORING_STATE_EVIDENCE_ID_PREFIX}:{digest}",
            evidence_hash=digest,
        )

    def position_witness_for_rules_unit(
        self,
        rules_unit_instance_id: str,
    ) -> PrimaryScoringRulesUnitPositionWitness:
        requested_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
        for witness in self.current_rules_unit_position_witnesses:
            if witness.rules_unit_instance_id == requested_id:
                return witness
        raise GameLifecycleError(
            "Primary scoring state evidence has no current witness for the rules unit."
        )

    def _content_payload(self) -> dict[str, object]:
        return _primary_scoring_state_content_payload(
            schema_version=self.schema_version,
            game_id=self.game_id,
            battlefield_id=self.battlefield_id,
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase=self.phase,
            timing=self.timing,
            scoring_boundary_kind=self.scoring_boundary_kind,
            objective_control_record_id=self.objective_control_record_id,
            objective_control_record_hash=self.objective_control_record_hash,
            primary_mission_progress_state=self.primary_mission_progress_state,
            primary_mission_action_states=self.primary_mission_action_states,
            primary_battlefield_departure_states=self.primary_battlefield_departure_states,
            primary_unit_destruction_state_ids=self.primary_unit_destruction_state_ids,
            current_rules_unit_position_witnesses=(self.current_rules_unit_position_witnesses),
            primary_scoring_spatial_evidence_by_player_id=(
                self.primary_scoring_spatial_evidence_by_player_id
            ),
        )

    def to_payload(self) -> PrimaryScoringStateEvidencePayload:
        return cast(
            PrimaryScoringStateEvidencePayload,
            {
                **self._content_payload(),
                "evidence_id": self.evidence_id,
                "evidence_hash": self.evidence_hash,
            },
        )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _required_payload_mapping(
            payload,
            label="Primary scoring state evidence",
            required_keys=tuple(PrimaryScoringStateEvidencePayload.__annotations__),
        )
        return cls(
            schema_version=cast(str, raw["schema_version"]),
            game_id=cast(str, raw["game_id"]),
            battlefield_id=cast(str, raw["battlefield_id"]),
            battle_round=cast(int, raw["battle_round"]),
            active_player_id=cast(str, raw["active_player_id"]),
            phase=cast(str, raw["phase"]),
            timing=objective_control_timing_from_token(raw["timing"]),
            scoring_boundary_kind=_primary_scoring_boundary_kind_from_token(
                raw["scoring_boundary_kind"]
            ),
            objective_control_record_id=cast(str, raw["objective_control_record_id"]),
            objective_control_record_hash=cast(
                str,
                raw["objective_control_record_hash"],
            ),
            primary_mission_progress_state=PrimaryMissionProgressState.from_payload(
                raw["primary_mission_progress_state"]
            ),
            primary_mission_action_states=tuple(
                _primary_mission_action_state_from_payload(value)
                for value in _required_payload_list(
                    raw["primary_mission_action_states"],
                    label="Primary scoring state mission Actions",
                )
            ),
            primary_battlefield_departure_states=tuple(
                PrimaryBattlefieldDepartureState.from_payload(value)
                for value in _required_payload_list(
                    raw["primary_battlefield_departure_states"],
                    label="Primary scoring state battlefield departures",
                )
            ),
            primary_unit_destruction_state_ids=tuple(
                cast(str, value)
                for value in _required_payload_list(
                    raw["primary_unit_destruction_state_ids"],
                    label="Primary scoring state destruction state IDs",
                )
            ),
            current_rules_unit_position_witnesses=tuple(
                PrimaryScoringRulesUnitPositionWitness.from_payload(value)
                for value in _required_payload_list(
                    raw["current_rules_unit_position_witnesses"],
                    label="Primary scoring state current position witnesses",
                )
            ),
            primary_scoring_spatial_evidence_by_player_id=tuple(
                PrimaryScoringSpatialEvidence.from_payload(value)
                for value in _required_payload_list(
                    raw["primary_scoring_spatial_evidence_by_player_id"],
                    label="Primary scoring state spatial evidence",
                )
            ),
            evidence_id=cast(str, raw["evidence_id"]),
            evidence_hash=cast(str, raw["evidence_hash"]),
        )


def build_primary_scoring_state_evidence(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> PrimaryScoringStateEvidence:
    """Freeze the authoritative scoring-facing state at one stored OC boundary."""
    from warhammer40k_core.engine.actions import MissionActionState
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_state_validation import (
        validate_primary_mission_progress_state,
    )
    from warhammer40k_core.engine.primary_turn_start_evidence import (
        build_current_primary_rules_unit_memberships,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring state evidence requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring state evidence requires an ObjectiveControlRecord."
        )
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary scoring end_of_battle must be a bool.")
    mission_setup = state.mission_setup
    battlefield_state = state.battlefield_state
    current_phase = state.current_battle_phase
    if (
        type(mission_setup) is not MissionSetup
        or type(battlefield_state) is not BattlefieldRuntimeState
        or state.active_player_id is None
        or current_phase is None
    ):
        raise GameLifecycleError(
            "Primary scoring state evidence requires an active mission battle boundary."
        )
    if (
        record.game_id != state.game_id
        or record.battlefield_id != battlefield_state.battlefield_id
        or record.battle_round != state.battle_round
        or record.active_player_id != state.active_player_id
        or record.phase != current_phase.value
    ):
        raise GameLifecycleError(
            "Primary scoring state ObjectiveControlRecord drifted from GameState."
        )
    stored_records = tuple(
        candidate
        for candidate in state.objective_control_records
        if candidate.record_id == record.record_id
    )
    if stored_records != (record,):
        raise GameLifecycleError(
            "Primary scoring state evidence requires the authoritative stored record."
        )
    progress = validate_primary_mission_progress_state(state)
    policies_by_id = primary_scoring_action_policies_by_id(mission_setup)
    assignment_by_player = {
        assignment.player_id: assignment.primary_mission_id
        for assignment in mission_setup.primary_mission_assignments
    }
    primary_actions = tuple(
        sorted(
            (
                action
                for action in state.mission_action_states
                if type(action) is MissionActionState
                and (
                    action.mission_action_id in policies_by_id
                    or action.mission_id == assignment_by_player.get(action.player_id)
                )
            ),
            key=lambda action: action.action_id,
        )
    )
    if any(type(action) is not MissionActionState for action in state.mission_action_states):
        raise GameLifecycleError(
            "Primary scoring state Mission Action history contains an untyped value."
        )
    departures = validate_primary_battlefield_departure_states(
        tuple(state.primary_battlefield_departure_states)
    )
    destruction_state_ids = primary_unit_destruction_state_ids_for_boundary(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
    )
    current_views = rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    current_memberships = build_current_primary_rules_unit_memberships(state=state)
    memberships_by_id = {
        membership.rules_unit_instance_id: membership for membership in current_memberships
    }
    if set(memberships_by_id) != {view.unit_instance_id for view in current_views}:
        raise GameLifecycleError("Primary scoring current position evidence omitted a rules unit.")
    positions = tuple(
        PrimaryScoringRulesUnitPositionWitness(
            owner_player_id=view.owner_player_id,
            rules_unit_membership=memberships_by_id[view.unit_instance_id],
        )
        for view in current_views
    )
    from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup

    scoring_policies = mission_scoring_policies_from_setup(mission_setup)
    scoring_player_ids = tuple(state.player_ids) if end_of_battle else (record.active_player_id,)
    spatial_rows = tuple(
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id=player_id,
            record=record,
            requested_condition_ids=required_conditions,
        )
        for player_id in scoring_player_ids
        for required_conditions in (
            scoring_policies.policy_for_player(player_id).required_primary_spatial_conditions(
                record=record,
                end_of_battle=end_of_battle,
            ),
        )
        if required_conditions
    )
    owner_by_rules_unit_id, components_by_rules_unit_id = _known_rules_unit_identity_maps(
        state=state
    )
    _validate_builder_record_rules_units(
        record=record,
        owner_by_rules_unit_id=owner_by_rules_unit_id,
    )
    _validate_builder_action_history(
        actions=primary_actions,
        policies_by_id=policies_by_id,
        mission_setup=mission_setup,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        battle_phase_sequence=tuple(phase.value for phase in state.battle_phase_sequence),
        record=record,
        owner_by_rules_unit_id=owner_by_rules_unit_id,
    )
    _validate_builder_departure_history(
        departures=departures,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        battle_phase_sequence=tuple(phase.value for phase in state.battle_phase_sequence),
        record=record,
        owner_by_rules_unit_id=owner_by_rules_unit_id,
        components_by_rules_unit_id=components_by_rules_unit_id,
    )
    _validate_builder_positions(positions=positions, current_views=current_views)
    evidence = PrimaryScoringStateEvidence.create(
        game_id=record.game_id,
        battlefield_id=record.battlefield_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        scoring_boundary_kind=(
            PrimaryScoringBoundaryKind.END_OF_BATTLE
            if end_of_battle
            else PrimaryScoringBoundaryKind.ORDINARY
        ),
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        primary_mission_progress_state=progress,
        primary_mission_action_states=primary_actions,
        primary_battlefield_departure_states=departures,
        primary_unit_destruction_state_ids=destruction_state_ids,
        current_rules_unit_position_witnesses=positions,
        primary_scoring_spatial_evidence_by_player_id=spatial_rows,
    )
    validate_primary_scoring_state_evidence_context(
        evidence,
        mission_setup=mission_setup,
        turn_order=state.turn_order,
        record=record,
        end_of_battle=end_of_battle,
    )
    validate_primary_scoring_state_evidence_restore_authority(
        evidence=evidence,
        state=state,
        record=record,
    )
    return evidence


def validate_primary_scoring_state_evidence_context(
    evidence: PrimaryScoringStateEvidence,
    *,
    mission_setup: MissionSetup,
    turn_order: tuple[str, ...],
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> None:
    """Validate intrinsic evidence context; authority requires the GameState validator."""
    if type(evidence) is not PrimaryScoringStateEvidence:
        raise GameLifecycleError("Primary scoring state context requires typed state evidence.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary scoring state context requires MissionSetup.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring state context requires an ObjectiveControlRecord."
        )
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary scoring state context end_of_battle must be a bool.")
    expected_boundary_kind = (
        PrimaryScoringBoundaryKind.END_OF_BATTLE
        if end_of_battle
        else PrimaryScoringBoundaryKind.ORDINARY
    )
    if evidence.scoring_boundary_kind is not expected_boundary_kind:
        raise GameLifecycleError("Primary scoring state boundary kind drifted.")
    ordered_players = _validate_turn_order(turn_order)
    setup_players = {
        mission_setup.attacker_player_id,
        mission_setup.defender_player_id,
    }
    if set(ordered_players) != setup_players:
        raise GameLifecycleError(
            "Primary scoring state turn_order must match MissionSetup players."
        )
    assignment_by_player = {
        assignment.player_id: assignment.primary_mission_id
        for assignment in mission_setup.primary_mission_assignments
    }
    if set(assignment_by_player) != setup_players:
        raise GameLifecycleError(
            "Primary scoring state assignments must match MissionSetup players."
        )
    if (
        evidence.game_id != record.game_id
        or evidence.battlefield_id != record.battlefield_id
        or evidence.battle_round != record.battle_round
        or evidence.active_player_id != record.active_player_id
        or evidence.phase != record.phase
        or evidence.timing is not record.timing
        or evidence.objective_control_record_id != record.record_id
        or evidence.objective_control_record_hash != objective_control_record_hash(record)
    ):
        raise GameLifecycleError(
            "Primary scoring state evidence drifted from its ObjectiveControlRecord."
        )
    if record.active_player_id not in ordered_players:
        raise GameLifecycleError("Primary scoring state active player is missing from turn_order.")
    validate_primary_scoring_boundary_context(
        mission_setup=mission_setup,
        turn_order=ordered_players,
        record=record,
        end_of_battle=end_of_battle,
    )
    _validate_record_for_setup(
        record=record,
        mission_setup=mission_setup,
        player_ids=ordered_players,
    )
    _validate_progress_context(
        progress=evidence.primary_mission_progress_state,
        game_id=evidence.game_id,
        assignment_by_player=assignment_by_player,
        player_ids=ordered_players,
    )
    canonical_phase_sequence = tuple(phase.value for phase in BattlePhase)
    validate_primary_scoring_progress_boundary(
        progress=evidence.primary_mission_progress_state,
        record=record,
        turn_order=ordered_players,
        battle_phase_sequence=canonical_phase_sequence,
    )
    validate_primary_scoring_spatial_rows_context(
        evidence.primary_scoring_spatial_evidence_by_player_id,
        mission_setup=mission_setup,
        turn_order=ordered_players,
        record=record,
        end_of_battle=end_of_battle,
    )
    policies_by_id = primary_scoring_action_policies_by_id(mission_setup)
    for action in evidence.primary_mission_action_states:
        policy = policies_by_id.get(action.mission_action_id)
        if policy is None:
            raise GameLifecycleError("Primary scoring state Action policy is not registered.")
        _validate_action_policy_and_assignment(
            action=action,
            policy=policy,
            assignment_by_player=assignment_by_player,
        )
        validate_primary_scoring_action_boundary(
            action=action,
            policy=policy,
            record=record,
            turn_order=ordered_players,
            battle_phase_sequence=canonical_phase_sequence,
        )
    for departure in evidence.primary_battlefield_departure_states:
        if departure.game_id != evidence.game_id:
            raise GameLifecycleError("Primary scoring state battlefield departure game_id drift.")
        if (
            departure.owner_player_id not in ordered_players
            or departure.active_player_id not in ordered_players
        ):
            raise GameLifecycleError(
                "Primary scoring state battlefield departure references an unknown player."
            )
        if departure.battle_round > record.battle_round:
            raise GameLifecycleError(
                "Primary scoring state departure cannot come from a future battle round."
            )
    if any(
        witness.owner_player_id not in ordered_players
        for witness in evidence.current_rules_unit_position_witnesses
    ):
        raise GameLifecycleError(
            "Primary scoring state position witness references an unknown player."
        )


def validate_primary_scoring_state_evidence_authority(
    evidence: PrimaryScoringStateEvidence,
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> None:
    """Require evidence to equal the canonical projection of authoritative state."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring state authority requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring state authority requires an ObjectiveControlRecord."
        )
    expected = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
    )
    if evidence != expected:
        raise GameLifecycleError(
            "Primary scoring state evidence drifted from authoritative GameState."
        )


def record_primary_scoring_state_evidence(
    *,
    state: GameState,
    evidence: PrimaryScoringStateEvidence,
) -> None:
    """Persist one canonical boundary witness, allowing exact boundary reuse."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring state recording requires GameState.")
    if type(evidence) is not PrimaryScoringStateEvidence:
        raise GameLifecycleError("Primary scoring state recording requires typed state evidence.")
    record_matches = tuple(
        record
        for record in state.objective_control_records
        if record.record_id == evidence.objective_control_record_id
    )
    if len(record_matches) != 1:
        raise GameLifecycleError(
            "Primary scoring state recording requires one authoritative boundary."
        )
    validate_primary_scoring_state_evidence_authority(
        evidence,
        state=state,
        record=record_matches[0],
        end_of_battle=(evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.END_OF_BATTLE),
    )
    boundary_matches = tuple(
        stored
        for stored in state.primary_scoring_state_evidence_records
        if stored.objective_control_record_id == evidence.objective_control_record_id
        and stored.scoring_boundary_kind is evidence.scoring_boundary_kind
    )
    if boundary_matches:
        if boundary_matches == (evidence,):
            return
        raise GameLifecycleError("Primary scoring boundary already has different state evidence.")
    if any(
        stored.evidence_id == evidence.evidence_id
        for stored in state.primary_scoring_state_evidence_records
    ):
        raise GameLifecycleError("Primary scoring state evidence identity is duplicated.")
    state.primary_scoring_state_evidence_records.append(evidence)


def validate_primary_scoring_state_evidence_records(
    values: object,
    *,
    game_id: str,
    mission_setup: MissionSetup | None,
    turn_order: tuple[str, ...],
    objective_control_records: tuple[ObjectiveControlRecord, ...],
) -> list[PrimaryScoringStateEvidence]:
    """Validate the persisted authority registry used by Primary VP records."""
    if not isinstance(values, list):
        raise GameLifecycleError("GameState primary_scoring_state_evidence_records must be a list.")
    raw_values = cast(list[object], values)
    if mission_setup is None:
        if raw_values:
            raise GameLifecycleError("Primary scoring state evidence requires a MissionSetup.")
        return []
    validated_game_id = _validate_identifier("game_id", game_id)
    boundaries_by_id = {record.record_id: record for record in objective_control_records}
    validated: list[PrimaryScoringStateEvidence] = []
    seen_evidence_ids: set[str] = set()
    seen_boundary_keys: set[tuple[str, PrimaryScoringBoundaryKind]] = set()
    for value in raw_values:
        if type(value) is not PrimaryScoringStateEvidence:
            raise GameLifecycleError(
                "GameState Primary scoring evidence registry requires typed records."
            )
        evidence = value
        if evidence.game_id != validated_game_id:
            raise GameLifecycleError("Primary scoring state evidence game_id drift.")
        if evidence.evidence_id in seen_evidence_ids:
            raise GameLifecycleError(
                "GameState Primary scoring evidence identities must be unique."
            )
        boundary_key = (
            evidence.objective_control_record_id,
            evidence.scoring_boundary_kind,
        )
        if boundary_key in seen_boundary_keys:
            raise GameLifecycleError(
                "GameState Primary scoring boundaries must have unique state evidence."
            )
        boundary = boundaries_by_id.get(evidence.objective_control_record_id)
        if boundary is None:
            raise GameLifecycleError(
                "Primary scoring state evidence does not identify an authoritative boundary."
            )
        validate_primary_scoring_state_evidence_context(
            evidence,
            mission_setup=mission_setup,
            turn_order=turn_order,
            record=boundary,
            end_of_battle=(
                evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.END_OF_BATTLE
            ),
        )
        seen_evidence_ids.add(evidence.evidence_id)
        seen_boundary_keys.add(boundary_key)
        validated.append(evidence)
    return validated


def validate_primary_scoring_state_evidence_records_authority(
    values: list[PrimaryScoringStateEvidence],
    *,
    state: GameState,
) -> None:
    """Bind validated persisted rows to authoritative history and identities."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring evidence authority requires GameState.")
    boundaries_by_id = {record.record_id: record for record in state.objective_control_records}
    for evidence in values:
        validate_primary_scoring_state_evidence_restore_authority(
            evidence=evidence,
            state=state,
            record=boundaries_by_id[evidence.objective_control_record_id],
        )


def _primary_scoring_state_content_payload(
    *,
    schema_version: str,
    game_id: str,
    battlefield_id: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    timing: ObjectiveControlTiming,
    scoring_boundary_kind: PrimaryScoringBoundaryKind,
    objective_control_record_id: str,
    objective_control_record_hash: str,
    primary_mission_progress_state: PrimaryMissionProgressState,
    primary_mission_action_states: tuple[MissionActionState, ...],
    primary_battlefield_departure_states: tuple[PrimaryBattlefieldDepartureState, ...],
    primary_unit_destruction_state_ids: tuple[str, ...],
    current_rules_unit_position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
    primary_scoring_spatial_evidence_by_player_id: tuple[PrimaryScoringSpatialEvidence, ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "game_id": game_id,
        "battlefield_id": battlefield_id,
        "battle_round": battle_round,
        "active_player_id": active_player_id,
        "phase": phase,
        "timing": timing.value,
        "scoring_boundary_kind": scoring_boundary_kind.value,
        "objective_control_record_id": objective_control_record_id,
        "objective_control_record_hash": objective_control_record_hash,
        "primary_mission_progress_state": primary_mission_progress_state.to_payload(),
        "primary_mission_action_states": [
            action.to_payload() for action in primary_mission_action_states
        ],
        "primary_battlefield_departure_states": [
            departure.to_payload() for departure in primary_battlefield_departure_states
        ],
        "primary_unit_destruction_state_ids": list(primary_unit_destruction_state_ids),
        "current_rules_unit_position_witnesses": [
            witness.to_payload() for witness in current_rules_unit_position_witnesses
        ],
        "primary_scoring_spatial_evidence_by_player_id": [
            evidence.to_payload() for evidence in primary_scoring_spatial_evidence_by_player_id
        ],
    }


def _validate_position_witnesses(
    values: object,
) -> tuple[PrimaryScoringRulesUnitPositionWitness, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence current position witnesses must be a tuple."
        )
    raw_values = cast(tuple[object, ...], values)
    witnesses: list[PrimaryScoringRulesUnitPositionWitness] = []
    seen_ids: set[str] = set()
    for value in raw_values:
        if type(value) is not PrimaryScoringRulesUnitPositionWitness:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence positions must contain typed witnesses."
            )
        if value.rules_unit_instance_id in seen_ids:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence rules-unit positions must be unique."
            )
        seen_ids.add(value.rules_unit_instance_id)
        witnesses.append(value)
    expected = tuple(sorted(witnesses, key=lambda witness: witness.rules_unit_instance_id))
    if raw_values != expected:
        raise GameLifecycleError("PrimaryScoringStateEvidence rules-unit positions must be sorted.")
    return expected


def _validate_spatial_evidence_rows(
    values: object,
) -> tuple[PrimaryScoringSpatialEvidence, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("PrimaryScoringStateEvidence spatial evidence must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    rows: list[PrimaryScoringSpatialEvidence] = []
    seen_players: set[str] = set()
    for value in raw_values:
        if type(value) is not PrimaryScoringSpatialEvidence:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence spatial evidence must contain typed rows."
            )
        if value.player_id in seen_players:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence spatial evidence must not duplicate players."
            )
        seen_players.add(value.player_id)
        rows.append(value)
    expected = tuple(sorted(rows, key=lambda row: row.player_id))
    if raw_values != expected:
        raise GameLifecycleError("PrimaryScoringStateEvidence spatial evidence must be sorted.")
    return expected


def _primary_mission_action_state_from_payload(payload: object) -> MissionActionState:
    from warhammer40k_core.engine.actions import (
        MissionActionState,
        MissionActionStatePayload,
    )

    raw = _required_payload_mapping(
        payload,
        label="Primary scoring state Mission Action",
        required_keys=tuple(MissionActionStatePayload.__annotations__),
    )
    return MissionActionState.from_payload(cast(MissionActionStatePayload, raw))


def _validate_builder_action_history(
    *,
    actions: tuple[MissionActionState, ...],
    policies_by_id: dict[str, PrimaryScoringActionPolicy],
    mission_setup: MissionSetup,
    player_ids: tuple[str, ...],
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
    record: ObjectiveControlRecord,
    owner_by_rules_unit_id: dict[str, str],
) -> None:
    from warhammer40k_core.engine.actions import MissionActionStatus

    known_players = set(player_ids)
    assignment_by_player = {
        assignment.player_id: assignment.primary_mission_id
        for assignment in mission_setup.primary_mission_assignments
    }
    for action in actions:
        policy = policies_by_id.get(action.mission_action_id)
        if policy is None:
            raise GameLifecycleError("Primary scoring state Action policy is not registered.")
        _validate_action_policy_and_assignment(
            action=action,
            policy=policy,
            assignment_by_player=assignment_by_player,
        )
        if action.player_id not in known_players:
            raise GameLifecycleError("Primary scoring state Action references an unknown player.")
        if owner_by_rules_unit_id.get(action.unit_instance_id) != action.player_id:
            raise GameLifecycleError("Primary scoring state Action unit identity or owner drift.")
        if any(
            owner_by_rules_unit_id.get(unit_id) != action.player_id
            for unit_id in action.eligible_unit_instance_ids
        ):
            raise GameLifecycleError(
                "Primary scoring state Action eligibility references an unknown friendly unit."
            )
        _reject_future_boundary(
            label="Primary scoring state Action start",
            row_battle_round=action.battle_round_started,
            row_active_player_id=action.player_id,
            row_phase=action.phase_started,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
            record=record,
        )
        if action.completed_battle_round is not None and action.completed_phase is not None:
            _reject_future_boundary(
                label="Primary scoring state Action completion",
                row_battle_round=action.completed_battle_round,
                row_active_player_id=action.player_id,
                row_phase=action.completed_phase,
                turn_order=turn_order,
                battle_phase_sequence=battle_phase_sequence,
                record=record,
            )
        if (
            record.timing is ObjectiveControlTiming.TURN_END
            and action.status is MissionActionStatus.STARTED
            and action.player_id == record.active_player_id
            and action.battle_round_started == record.battle_round
        ):
            raise GameLifecycleError(
                "Primary scoring turn-end state cannot retain the current player's started Action."
            )


def _validate_action_policy_and_assignment(
    *,
    action: MissionActionState,
    policy: PrimaryScoringActionPolicy,
    assignment_by_player: dict[str, str],
) -> None:
    assigned_mission = assignment_by_player.get(action.player_id)
    if assigned_mission is None or action.mission_id != assigned_mission:
        raise GameLifecycleError(
            "Primary scoring state Action does not match its player's assigned Primary."
        )
    if (
        action.mission_id != policy.primary_mission_id
        or action.phase_started != policy.start_phase
        or action.start_timing != policy.start_timing
        or action.completion_timing != policy.completion_timing
        or action.interruption_conditions != policy.interruption_conditions
        or action.scoring_source_id != policy.scoring_source_id
        or action.victory_points != policy.victory_points
    ):
        raise GameLifecycleError("Primary scoring state Action drifted from its registered policy.")


def _validate_builder_record_rules_units(
    *,
    record: ObjectiveControlRecord,
    owner_by_rules_unit_id: dict[str, str],
) -> None:
    for result in record.results:
        for contribution in result.contributors:
            if owner_by_rules_unit_id.get(contribution.unit_instance_id) != (
                contribution.player_id
            ):
                raise GameLifecycleError(
                    "Primary scoring objective-control contribution references an unknown "
                    "rules unit or owner."
                )


def _validate_builder_departure_history(
    *,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    player_ids: tuple[str, ...],
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
    record: ObjectiveControlRecord,
    owner_by_rules_unit_id: dict[str, str],
    components_by_rules_unit_id: dict[str, tuple[str, ...]],
) -> None:
    known_players = set(player_ids)
    for departure in departures:
        if departure.game_id != record.game_id:
            raise GameLifecycleError("Primary scoring state battlefield departure game_id drift.")
        if (
            departure.owner_player_id not in known_players
            or departure.active_player_id not in known_players
        ):
            raise GameLifecycleError(
                "Primary scoring state battlefield departure references an unknown player."
            )
        if owner_by_rules_unit_id.get(departure.rules_unit_instance_id) != (
            departure.owner_player_id
        ):
            raise GameLifecycleError(
                "Primary scoring state battlefield departure rules-unit owner drift."
            )
        if components_by_rules_unit_id.get(departure.rules_unit_instance_id) != (
            departure.component_unit_instance_ids
        ):
            raise GameLifecycleError(
                "Primary scoring state battlefield departure component identity drift."
            )
        _reject_future_boundary(
            label="Primary scoring state battlefield departure",
            row_battle_round=departure.battle_round,
            row_active_player_id=departure.active_player_id,
            row_phase=departure.phase,
            turn_order=turn_order,
            battle_phase_sequence=battle_phase_sequence,
            record=record,
        )


def _validate_builder_positions(
    *,
    positions: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
    current_views: tuple[RulesUnitView, ...],
) -> None:
    views_by_id = {view.unit_instance_id: view for view in current_views}
    if len(views_by_id) != len(current_views) or len(positions) != len(current_views):
        raise GameLifecycleError(
            "Primary scoring current positions require every rules unit exactly once."
        )
    for witness in positions:
        view = views_by_id.get(witness.rules_unit_instance_id)
        if view is None:
            raise GameLifecycleError(
                "Primary scoring current position references an unknown rules unit."
            )
        if (
            witness.owner_player_id != view.owner_player_id
            or witness.rules_unit_membership.component_unit_instance_ids
            != tuple(sorted(view.component_unit_instance_ids))
        ):
            raise GameLifecycleError("Primary scoring current position rules-unit identity drift.")


def _known_rules_unit_identity_maps(
    *,
    state: GameState,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    owner_by_id: dict[str, str] = {}
    components_by_id: dict[str, tuple[str, ...]] = {}
    for army in state.army_definitions:
        for unit in army.units:
            _record_known_rules_unit(
                rules_unit_instance_id=unit.unit_instance_id,
                owner_player_id=army.player_id,
                component_unit_instance_ids=(unit.unit_instance_id,),
                owner_by_id=owner_by_id,
                components_by_id=components_by_id,
            )
        for formation in army.attached_units:
            _record_known_rules_unit(
                rules_unit_instance_id=formation.attached_unit_instance_id,
                owner_player_id=army.player_id,
                component_unit_instance_ids=formation.component_unit_instance_ids,
                owner_by_id=owner_by_id,
                components_by_id=components_by_id,
            )
    for record in state.starting_attached_unit_records:
        _record_known_rules_unit(
            rules_unit_instance_id=record.attached_unit_instance_id,
            owner_player_id=record.player_id,
            component_unit_instance_ids=record.component_unit_instance_ids,
            owner_by_id=owner_by_id,
            components_by_id=components_by_id,
        )
    return owner_by_id, components_by_id


def _record_known_rules_unit(
    *,
    rules_unit_instance_id: str,
    owner_player_id: str,
    component_unit_instance_ids: tuple[str, ...],
    owner_by_id: dict[str, str],
    components_by_id: dict[str, tuple[str, ...]],
) -> None:
    rules_unit_id = _validate_identifier(
        "known rules_unit_instance_id",
        rules_unit_instance_id,
    )
    owner_id = _validate_identifier("known owner_player_id", owner_player_id)
    components = _validate_sorted_identifier_tuple(
        "known component_unit_instance_ids",
        component_unit_instance_ids,
        require_non_empty=True,
    )
    existing_owner = owner_by_id.get(rules_unit_id)
    existing_components = components_by_id.get(rules_unit_id)
    if existing_owner is not None and existing_owner != owner_id:
        raise GameLifecycleError("Primary scoring known rules-unit owner is ambiguous.")
    if existing_components is not None and existing_components != components:
        raise GameLifecycleError("Primary scoring known rules-unit components are ambiguous.")
    owner_by_id[rules_unit_id] = owner_id
    components_by_id[rules_unit_id] = components


def _reject_future_boundary(
    *,
    label: str,
    row_battle_round: int,
    row_active_player_id: str,
    row_phase: str,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
    record: ObjectiveControlRecord,
) -> None:
    row_key = _boundary_order_key(
        label=label,
        battle_round=row_battle_round,
        active_player_id=row_active_player_id,
        phase=row_phase,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )
    record_key = _boundary_order_key(
        label="Primary scoring ObjectiveControlRecord",
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        turn_order=turn_order,
        battle_phase_sequence=battle_phase_sequence,
    )
    if row_key > record_key:
        raise GameLifecycleError(f"{label} cannot come from a future boundary.")


def _boundary_order_key(
    *,
    label: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    turn_order: tuple[str, ...],
    battle_phase_sequence: tuple[str, ...],
) -> tuple[int, int, int]:
    requested_round = _validate_positive_int(f"{label} battle_round", battle_round)
    requested_player = _validate_identifier(f"{label} active_player_id", active_player_id)
    requested_phase = _validate_identifier(f"{label} phase", phase)
    if requested_player not in turn_order:
        raise GameLifecycleError(f"{label} references an unknown active player.")
    if requested_phase not in battle_phase_sequence:
        raise GameLifecycleError(f"{label} references an unknown battle phase.")
    return (
        requested_round,
        turn_order.index(requested_player),
        battle_phase_sequence.index(requested_phase),
    )


def _validate_progress_context(
    *,
    progress: PrimaryMissionProgressState,
    game_id: str,
    assignment_by_player: dict[str, str],
    player_ids: tuple[str, ...],
) -> None:
    known_players = set(player_ids)
    for owner_player_id, mission_id, row_game_id, active_player_ids in (
        *(
            (
                marker.owner_player_id,
                marker.mission_id,
                marker.game_id,
                (
                    marker.created_active_player_id,
                    marker.removed_active_player_id,
                ),
            )
            for marker in progress.markers
        ),
        *(
            (
                selection.owner_player_id,
                selection.mission_id,
                selection.game_id,
                (selection.active_player_id,),
            )
            for selection in progress.condemned_selections
        ),
        *(
            (
                designation.owner_player_id,
                designation.mission_id,
                designation.game_id,
                (
                    designation.created_active_player_id,
                    designation.consumed_active_player_id,
                ),
            )
            for designation in progress.consecration_designations
        ),
    ):
        if row_game_id != game_id:
            raise GameLifecycleError("Primary scoring mission progress game_id drift.")
        if assignment_by_player.get(owner_player_id) != mission_id:
            raise GameLifecycleError(
                "Primary scoring mission progress drifted from its owner's assignment."
            )
        if any(
            active_player_id is not None and active_player_id not in known_players
            for active_player_id in active_player_ids
        ):
            raise GameLifecycleError(
                "Primary scoring mission progress references an unknown active player."
            )


def _validate_record_for_setup(
    *,
    record: ObjectiveControlRecord,
    mission_setup: MissionSetup,
    player_ids: tuple[str, ...],
) -> None:
    expected_objective_ids = tuple(
        marker.objective_marker_id for marker in mission_setup.objective_markers
    )
    if tuple(result.objective_id for result in record.results) != expected_objective_ids:
        raise GameLifecycleError(
            "Primary scoring state record must contain exactly the MissionSetup objectives."
        )
    known_players = set(player_ids)
    for result in record.results:
        if result.status is ObjectiveControlStatus.UNSUPPORTED:
            raise GameLifecycleError(
                "Primary scoring state cannot consume unsupported objective control."
            )
        if (
            result.controlled_by_player_id is not None
            and result.controlled_by_player_id not in known_players
        ):
            raise GameLifecycleError(
                "Primary scoring state record references an unknown controlling player."
            )
        if any(score.player_id not in known_players for score in result.scores):
            raise GameLifecycleError(
                "Primary scoring state record score references an unknown player."
            )
        if any(contribution.player_id not in known_players for contribution in result.contributors):
            raise GameLifecycleError(
                "Primary scoring state record contribution references an unknown player."
            )


def _validate_turn_order(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Primary scoring state turn_order must be a tuple.")
    ordered = tuple(
        _validate_identifier("Primary scoring state turn_order value", item)
        for item in cast(tuple[object, ...], value)
    )
    if len(ordered) != 2 or len(set(ordered)) != len(ordered):
        raise GameLifecycleError(
            "Primary scoring state turn_order must contain exactly two unique players."
        )
    return ordered


def _validate_sorted_identifier_tuple(
    label: str,
    value: object,
    *,
    require_non_empty: bool,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    raw_values = cast(tuple[object, ...], value)
    identifiers = tuple(_validate_identifier(f"{label} value", item) for item in raw_values)
    if require_non_empty and not identifiers:
        raise GameLifecycleError(f"{label} must not be empty.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{label} must not contain duplicates.")
    expected = tuple(sorted(identifiers))
    if identifiers != expected:
        raise GameLifecycleError(f"{label} must be sorted.")
    return expected


def _required_payload_mapping(
    payload: object,
    *,
    label: str,
    required_keys: tuple[str, ...],
) -> dict[str, object]:
    if type(payload) is not dict:
        raise GameLifecycleError(f"{label} payload must be an object.")
    raw = cast(dict[str, object], payload)
    missing = tuple(key for key in required_keys if key not in raw)
    if missing:
        raise GameLifecycleError(f"{label} payload is missing required field: {missing[0]}.")
    unexpected = tuple(sorted(set(raw).difference(required_keys)))
    if unexpected:
        raise GameLifecycleError(f"{label} payload contains unexpected field: {unexpected[0]}.")
    return raw


def _required_payload_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise GameLifecycleError(f"{label} payload must be a list.")
    return cast(list[object], value)


def _validate_positive_int(label: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{label} must be a positive integer.")
    return value


def _primary_scoring_boundary_kind_from_token(
    value: object,
) -> PrimaryScoringBoundaryKind:
    if value == PrimaryScoringBoundaryKind.ORDINARY.value:
        return PrimaryScoringBoundaryKind.ORDINARY
    if value == PrimaryScoringBoundaryKind.END_OF_BATTLE.value:
        return PrimaryScoringBoundaryKind.END_OF_BATTLE
    raise GameLifecycleError("Primary scoring state boundary kind is invalid.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "PRIMARY_SCORING_STATE_EVIDENCE_SCHEMA",
    "PrimaryScoringBoundaryKind",
    "PrimaryScoringRulesUnitPositionWitness",
    "PrimaryScoringRulesUnitPositionWitnessPayload",
    "PrimaryScoringStateEvidence",
    "PrimaryScoringStateEvidencePayload",
    "build_primary_scoring_state_evidence",
    "record_primary_scoring_state_evidence",
    "validate_primary_scoring_state_evidence_authority",
    "validate_primary_scoring_state_evidence_context",
    "validate_primary_scoring_state_evidence_records",
    "validate_primary_scoring_state_evidence_records_authority",
)
