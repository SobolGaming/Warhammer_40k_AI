from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.deployment import (
    deployment_completion_accounted_model_ids,
    deployment_setup_state_for_state,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.prebattle import (
    prebattle_next_player_id_for_timing_state,
    prebattle_timing_state_for_state,
    redeploy_timing_state_for_state,
)
from warhammer40k_core.engine.reserve_declarations import (
    reserve_declaration_state_for_state,
    reserve_legality_context_for_player,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveStatus
from warhammer40k_core.engine.unit_coherency import assert_battlefield_units_in_coherency

SETUP_COMPLETION_GATE_SOURCE_ID = "core_rules_setup_completion_gate"


class SetupCompletionViolationCode(StrEnum):
    PENDING_DECISION_QUEUE = "pending_decision_queue"
    REACTION_QUEUE_NOT_DRAINED = "reaction_queue_not_drained"
    SETUP_SEQUENCE_INCOMPLETE = "setup_sequence_incomplete"
    MISSING_ARMY = "missing_army"
    MISSING_MISSION_SETUP = "missing_mission_setup"
    UNRESOLVED_SECONDARY_MISSIONS = "unresolved_secondary_missions"
    UNRESOLVED_ATTACKER_DEFENDER = "unresolved_attacker_defender"
    MISSING_BATTLEFIELD = "missing_battlefield"
    UNRESOLVED_BATTLE_FORMATIONS = "unresolved_battle_formations"
    UNRESOLVED_DEPLOYMENT = "unresolved_deployment"
    ILLEGAL_BATTLEFIELD_STATE = "illegal_battlefield_state"
    ILLEGAL_RESERVE_DECLARATION = "illegal_reserve_declaration"
    UNRESOLVED_REDEPLOY = "unresolved_redeploy"
    UNRESOLVED_PREBATTLE_ACTIONS = "unresolved_prebattle_actions"


class SetupCompletionViolationPayload(TypedDict):
    violation_code: str
    message: str
    field: str | None
    player_id: str | None
    unit_instance_id: str | None
    detail: JsonValue


class SetupDecisionDrainStatePayload(TypedDict):
    pending_decision_count: int
    pending_decision_request_ids: list[str]
    pending_decision_types: list[str]
    reaction_frame_count: int


class PreBattleReadinessSnapshotPayload(TypedDict):
    game_id: str
    stage: str
    current_setup_step: str | None
    setup_sequence_complete_after_current_step: bool
    ruleset_descriptor_hash: str
    player_ids: list[str]
    turn_order: list[str]
    missing_army_player_ids: list[str]
    missing_secondary_mission_player_ids: list[str]
    mission_setup_present: bool
    attacker_player_id: str | None
    defender_player_id: str | None
    battlefield_present: bool
    placed_model_count: int
    unplaced_model_count: int
    accounted_unavailable_model_count: int
    reserve_state_count: int
    unarrived_reserve_unit_count: int
    transport_cargo_state_count: int
    dedicated_transport_consequence_count: int
    redeploy_next_player_id: str | None
    prebattle_next_player_id: str | None


class SetupLegalityReportPayload(TypedDict):
    is_legal: bool
    violations: list[SetupCompletionViolationPayload]
    decision_drain_state: SetupDecisionDrainStatePayload
    readiness_snapshot: PreBattleReadinessSnapshotPayload


class SetupReplayCheckpointPayload(TypedDict):
    checkpoint_id: str
    game_id: str
    checkpoint_kind: str
    state_hash: str
    stage: str
    setup_step_index: int | None
    battle_round: int
    active_player_id: str | None
    current_setup_step: str | None
    current_battle_phase: str | None


class BattleStartRecordPayload(TypedDict):
    record_id: str
    game_id: str
    source_id: str
    completed_setup_step: str
    ruleset_descriptor_hash: str
    setup_sequence: list[str]
    battle_round: int
    active_player_id: str
    first_battle_phase: str
    turn_order: list[str]
    readiness_snapshot: PreBattleReadinessSnapshotPayload
    setup_legality_report: SetupLegalityReportPayload
    pre_battle_checkpoint: SetupReplayCheckpointPayload
    post_battle_start_checkpoint: SetupReplayCheckpointPayload


@dataclass(frozen=True, slots=True)
class SetupCompletionViolation:
    violation_code: SetupCompletionViolationCode
    message: str
    field: str | None = None
    player_id: str | None = None
    unit_instance_id: str | None = None
    detail: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            setup_completion_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_required_string("SetupCompletionViolation message", self.message),
        )
        object.__setattr__(
            self,
            "field",
            _validate_optional_string("SetupCompletionViolation field", self.field),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_optional_string("SetupCompletionViolation player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_optional_string(
                "SetupCompletionViolation unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(self, "detail", validate_json_value(self.detail))

    def to_payload(self) -> SetupCompletionViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "field": self.field,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class SetupDecisionDrainState:
    pending_decision_request_ids: tuple[str, ...]
    pending_decision_types: tuple[str, ...]
    reaction_frame_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pending_decision_request_ids",
            _validate_string_tuple(
                "SetupDecisionDrainState pending_decision_request_ids",
                self.pending_decision_request_ids,
            ),
        )
        object.__setattr__(
            self,
            "pending_decision_types",
            _validate_string_tuple(
                "SetupDecisionDrainState pending_decision_types",
                self.pending_decision_types,
            ),
        )
        if len(self.pending_decision_request_ids) != len(self.pending_decision_types):
            raise GameLifecycleError("SetupDecisionDrainState pending decision drift.")
        object.__setattr__(
            self,
            "reaction_frame_count",
            _validate_non_negative_int(
                "SetupDecisionDrainState reaction_frame_count",
                self.reaction_frame_count,
            ),
        )

    @classmethod
    def from_decisions(
        cls,
        *,
        decisions: DecisionController,
        reaction_frame_count: int,
    ) -> Self:
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("SetupDecisionDrainState requires DecisionController.")
        pending = decisions.queue.pending_requests
        return cls(
            pending_decision_request_ids=tuple(request.request_id for request in pending),
            pending_decision_types=tuple(request.decision_type for request in pending),
            reaction_frame_count=reaction_frame_count,
        )

    @property
    def pending_decision_count(self) -> int:
        return len(self.pending_decision_request_ids)

    @property
    def is_drained(self) -> bool:
        return self.pending_decision_count == 0 and self.reaction_frame_count == 0

    def to_payload(self) -> SetupDecisionDrainStatePayload:
        return {
            "pending_decision_count": self.pending_decision_count,
            "pending_decision_request_ids": list(self.pending_decision_request_ids),
            "pending_decision_types": list(self.pending_decision_types),
            "reaction_frame_count": self.reaction_frame_count,
        }


@dataclass(frozen=True, slots=True)
class PreBattleReadinessSnapshot:
    game_id: str
    stage: GameLifecycleStage
    current_setup_step: SetupStep | None
    setup_sequence_complete_after_current_step: bool
    ruleset_descriptor_hash: str
    player_ids: tuple[str, ...]
    turn_order: tuple[str, ...]
    missing_army_player_ids: tuple[str, ...]
    missing_secondary_mission_player_ids: tuple[str, ...]
    mission_setup_present: bool
    attacker_player_id: str | None
    defender_player_id: str | None
    battlefield_present: bool
    placed_model_count: int
    unplaced_model_count: int
    accounted_unavailable_model_count: int
    reserve_state_count: int
    unarrived_reserve_unit_count: int
    transport_cargo_state_count: int
    dedicated_transport_consequence_count: int
    redeploy_next_player_id: str | None
    prebattle_next_player_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_id",
            _validate_required_string("PreBattleReadinessSnapshot game_id", self.game_id),
        )
        if type(self.stage) is not GameLifecycleStage:
            raise GameLifecycleError("PreBattleReadinessSnapshot stage must be a lifecycle stage.")
        if self.current_setup_step is not None and type(self.current_setup_step) is not SetupStep:
            raise GameLifecycleError("PreBattleReadinessSnapshot setup step drift.")
        object.__setattr__(
            self,
            "setup_sequence_complete_after_current_step",
            _validate_bool(
                "PreBattleReadinessSnapshot setup_sequence_complete_after_current_step",
                self.setup_sequence_complete_after_current_step,
            ),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_required_string(
                "PreBattleReadinessSnapshot ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "player_ids",
            _validate_string_tuple("PreBattleReadinessSnapshot player_ids", self.player_ids),
        )
        object.__setattr__(
            self,
            "turn_order",
            _validate_string_tuple("PreBattleReadinessSnapshot turn_order", self.turn_order),
        )
        object.__setattr__(
            self,
            "missing_army_player_ids",
            _validate_string_tuple(
                "PreBattleReadinessSnapshot missing_army_player_ids",
                self.missing_army_player_ids,
            ),
        )
        object.__setattr__(
            self,
            "missing_secondary_mission_player_ids",
            _validate_string_tuple(
                "PreBattleReadinessSnapshot missing_secondary_mission_player_ids",
                self.missing_secondary_mission_player_ids,
            ),
        )
        object.__setattr__(
            self,
            "mission_setup_present",
            _validate_bool(
                "PreBattleReadinessSnapshot mission_setup_present",
                self.mission_setup_present,
            ),
        )
        object.__setattr__(
            self,
            "attacker_player_id",
            _validate_optional_string(
                "PreBattleReadinessSnapshot attacker_player_id",
                self.attacker_player_id,
            ),
        )
        object.__setattr__(
            self,
            "defender_player_id",
            _validate_optional_string(
                "PreBattleReadinessSnapshot defender_player_id",
                self.defender_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_present",
            _validate_bool(
                "PreBattleReadinessSnapshot battlefield_present",
                self.battlefield_present,
            ),
        )
        for field_name in (
            "placed_model_count",
            "unplaced_model_count",
            "accounted_unavailable_model_count",
            "reserve_state_count",
            "unarrived_reserve_unit_count",
            "transport_cargo_state_count",
            "dedicated_transport_consequence_count",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_non_negative_int(
                    f"PreBattleReadinessSnapshot {field_name}",
                    getattr(self, field_name),
                ),
            )
        object.__setattr__(
            self,
            "redeploy_next_player_id",
            _validate_optional_string(
                "PreBattleReadinessSnapshot redeploy_next_player_id",
                self.redeploy_next_player_id,
            ),
        )
        object.__setattr__(
            self,
            "prebattle_next_player_id",
            _validate_optional_string(
                "PreBattleReadinessSnapshot prebattle_next_player_id",
                self.prebattle_next_player_id,
            ),
        )

    @classmethod
    def from_state(
        cls,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
    ) -> Self:
        if type(state) is not GameState:
            raise GameLifecycleError("PreBattleReadinessSnapshot requires GameState.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("PreBattleReadinessSnapshot requires DecisionController.")
        if type(config) is not GameConfig:
            raise GameLifecycleError("PreBattleReadinessSnapshot requires GameConfig.")
        battlefield = state.battlefield_state
        mission_setup = state.mission_setup
        current_step = state.current_setup_step
        setup_complete_after_current = (
            current_step is not None
            and state.setup_step_index is not None
            and state.setup_step_index + 1 == len(state.setup_sequence)
        )
        unplaced_count = 0
        if battlefield is not None:
            unplaced_count = len(
                BattlefieldScenario(
                    armies=tuple(state.army_definitions),
                    battlefield_state=battlefield,
                ).unplaced_model_ids()
            )
        can_evaluate_prebattle_steps = (
            battlefield is not None
            and mission_setup is not None
            and not state.missing_army_player_ids()
        )
        redeploy_next_player_id = (
            None
            if not can_evaluate_prebattle_steps
            else _next_redeploy_player_id(state=state, decisions=decisions)
        )
        prebattle_next_player_id = (
            None
            if not can_evaluate_prebattle_steps
            else _next_prebattle_player_id(
                state=state,
                decisions=decisions,
                config=config,
            )
        )
        return cls(
            game_id=state.game_id,
            stage=state.stage,
            current_setup_step=current_step,
            setup_sequence_complete_after_current_step=setup_complete_after_current,
            ruleset_descriptor_hash=state.ruleset_descriptor_hash,
            player_ids=state.player_ids,
            turn_order=state.turn_order,
            missing_army_player_ids=state.missing_army_player_ids(),
            missing_secondary_mission_player_ids=state.missing_secondary_mission_player_ids(),
            mission_setup_present=mission_setup is not None,
            attacker_player_id=None if mission_setup is None else mission_setup.attacker_player_id,
            defender_player_id=None if mission_setup is None else mission_setup.defender_player_id,
            battlefield_present=battlefield is not None,
            placed_model_count=0 if battlefield is None else len(battlefield.placed_model_ids()),
            unplaced_model_count=unplaced_count,
            accounted_unavailable_model_count=len(deployment_completion_accounted_model_ids(state)),
            reserve_state_count=len(state.reserve_states),
            unarrived_reserve_unit_count=len(
                tuple(
                    reserve_state
                    for reserve_state in state.reserve_states
                    if reserve_state.status is ReserveStatus.IN_RESERVES
                )
            ),
            transport_cargo_state_count=len(state.transport_cargo_states),
            dedicated_transport_consequence_count=len(state.dedicated_transport_setup_consequences),
            redeploy_next_player_id=redeploy_next_player_id,
            prebattle_next_player_id=prebattle_next_player_id,
        )

    def to_payload(self) -> PreBattleReadinessSnapshotPayload:
        return {
            "game_id": self.game_id,
            "stage": self.stage.value,
            "current_setup_step": (
                None if self.current_setup_step is None else self.current_setup_step.value
            ),
            "setup_sequence_complete_after_current_step": (
                self.setup_sequence_complete_after_current_step
            ),
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "player_ids": list(self.player_ids),
            "turn_order": list(self.turn_order),
            "missing_army_player_ids": list(self.missing_army_player_ids),
            "missing_secondary_mission_player_ids": list(self.missing_secondary_mission_player_ids),
            "mission_setup_present": self.mission_setup_present,
            "attacker_player_id": self.attacker_player_id,
            "defender_player_id": self.defender_player_id,
            "battlefield_present": self.battlefield_present,
            "placed_model_count": self.placed_model_count,
            "unplaced_model_count": self.unplaced_model_count,
            "accounted_unavailable_model_count": self.accounted_unavailable_model_count,
            "reserve_state_count": self.reserve_state_count,
            "unarrived_reserve_unit_count": self.unarrived_reserve_unit_count,
            "transport_cargo_state_count": self.transport_cargo_state_count,
            "dedicated_transport_consequence_count": self.dedicated_transport_consequence_count,
            "redeploy_next_player_id": self.redeploy_next_player_id,
            "prebattle_next_player_id": self.prebattle_next_player_id,
        }


@dataclass(frozen=True, slots=True)
class SetupLegalityReport:
    decision_drain_state: SetupDecisionDrainState
    readiness_snapshot: PreBattleReadinessSnapshot
    violations: tuple[SetupCompletionViolation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.decision_drain_state) is not SetupDecisionDrainState:
            raise GameLifecycleError("SetupLegalityReport requires drain state.")
        if type(self.readiness_snapshot) is not PreBattleReadinessSnapshot:
            raise GameLifecycleError("SetupLegalityReport requires readiness snapshot.")
        object.__setattr__(
            self,
            "violations",
            _validate_violation_tuple("SetupLegalityReport violations", self.violations),
        )

    @property
    def is_legal(self) -> bool:
        return not self.violations

    def to_payload(self) -> SetupLegalityReportPayload:
        return {
            "is_legal": self.is_legal,
            "violations": [violation.to_payload() for violation in self.violations],
            "decision_drain_state": self.decision_drain_state.to_payload(),
            "readiness_snapshot": self.readiness_snapshot.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class SetupReplayCheckpoint:
    checkpoint_id: str
    game_id: str
    checkpoint_kind: str
    state_hash: str
    stage: GameLifecycleStage
    setup_step_index: int | None
    battle_round: int
    active_player_id: str | None
    current_setup_step: SetupStep | None
    current_battle_phase: BattlePhase | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "checkpoint_id",
            _validate_required_string("SetupReplayCheckpoint checkpoint_id", self.checkpoint_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_required_string("SetupReplayCheckpoint game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "checkpoint_kind",
            _validate_required_string(
                "SetupReplayCheckpoint checkpoint_kind",
                self.checkpoint_kind,
            ),
        )
        object.__setattr__(
            self,
            "state_hash",
            _validate_sha256("SetupReplayCheckpoint state_hash", self.state_hash),
        )
        if type(self.stage) is not GameLifecycleStage:
            raise GameLifecycleError("SetupReplayCheckpoint stage must be a lifecycle stage.")
        object.__setattr__(
            self,
            "setup_step_index",
            _validate_optional_non_negative_int(
                "SetupReplayCheckpoint setup_step_index",
                self.setup_step_index,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_non_negative_int("SetupReplayCheckpoint battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_string(
                "SetupReplayCheckpoint active_player_id",
                self.active_player_id,
            ),
        )
        if self.current_setup_step is not None and type(self.current_setup_step) is not SetupStep:
            raise GameLifecycleError("SetupReplayCheckpoint setup step drift.")
        if self.current_battle_phase is not None and type(self.current_battle_phase) is not (
            BattlePhase
        ):
            raise GameLifecycleError("SetupReplayCheckpoint battle phase drift.")

    @classmethod
    def from_state(cls, *, state: GameState, checkpoint_kind: str) -> Self:
        kind = _validate_required_string("checkpoint_kind", checkpoint_kind)
        return cls(
            checkpoint_id=f"setup-checkpoint:{state.game_id}:{kind}",
            game_id=state.game_id,
            checkpoint_kind=kind,
            state_hash=_stable_hash(cast(JsonValue, state.to_payload())),
            stage=state.stage,
            setup_step_index=state.setup_step_index,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            current_setup_step=state.current_setup_step,
            current_battle_phase=state.current_battle_phase,
        )

    def to_payload(self) -> SetupReplayCheckpointPayload:
        return {
            "checkpoint_id": self.checkpoint_id,
            "game_id": self.game_id,
            "checkpoint_kind": self.checkpoint_kind,
            "state_hash": self.state_hash,
            "stage": self.stage.value,
            "setup_step_index": self.setup_step_index,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "current_setup_step": (
                None if self.current_setup_step is None else self.current_setup_step.value
            ),
            "current_battle_phase": (
                None if self.current_battle_phase is None else self.current_battle_phase.value
            ),
        }


@dataclass(frozen=True, slots=True)
class BattleStartRecord:
    record_id: str
    game_id: str
    completed_setup_step: SetupStep
    ruleset_descriptor_hash: str
    setup_sequence: tuple[SetupStep, ...]
    battle_round: int
    active_player_id: str
    first_battle_phase: BattlePhase
    turn_order: tuple[str, ...]
    readiness_snapshot: PreBattleReadinessSnapshot
    setup_legality_report: SetupLegalityReport
    pre_battle_checkpoint: SetupReplayCheckpoint
    post_battle_start_checkpoint: SetupReplayCheckpoint
    source_id: str = SETUP_COMPLETION_GATE_SOURCE_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _validate_required_string("BattleStartRecord record_id", self.record_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_required_string("BattleStartRecord game_id", self.game_id),
        )
        if type(self.completed_setup_step) is not SetupStep:
            raise GameLifecycleError("BattleStartRecord completed setup step drift.")
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_required_string(
                "BattleStartRecord ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "setup_sequence",
            _validate_setup_step_tuple("BattleStartRecord setup_sequence", self.setup_sequence),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("BattleStartRecord battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_required_string("BattleStartRecord active_player_id", self.active_player_id),
        )
        if type(self.first_battle_phase) is not BattlePhase:
            raise GameLifecycleError("BattleStartRecord first battle phase drift.")
        object.__setattr__(
            self,
            "turn_order",
            _validate_string_tuple("BattleStartRecord turn_order", self.turn_order),
        )
        if self.active_player_id not in self.turn_order:
            raise GameLifecycleError("BattleStartRecord active player must be in turn order.")
        if type(self.readiness_snapshot) is not PreBattleReadinessSnapshot:
            raise GameLifecycleError("BattleStartRecord requires readiness snapshot.")
        if type(self.setup_legality_report) is not SetupLegalityReport:
            raise GameLifecycleError("BattleStartRecord requires setup legality report.")
        if not self.setup_legality_report.is_legal:
            raise GameLifecycleError("BattleStartRecord requires a legal setup report.")
        if type(self.pre_battle_checkpoint) is not SetupReplayCheckpoint:
            raise GameLifecycleError("BattleStartRecord requires pre-battle checkpoint.")
        if type(self.post_battle_start_checkpoint) is not SetupReplayCheckpoint:
            raise GameLifecycleError("BattleStartRecord requires post-battle checkpoint.")
        object.__setattr__(
            self,
            "source_id",
            _validate_required_string("BattleStartRecord source_id", self.source_id),
        )

    @classmethod
    def from_started_state(
        cls,
        *,
        state: GameState,
        completed_setup_step: SetupStep,
        report: SetupLegalityReport,
        pre_battle_checkpoint: SetupReplayCheckpoint,
    ) -> Self:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("BattleStartRecord requires a battle-stage GameState.")
        current_phase = state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("BattleStartRecord requires a current battle phase.")
        active_player_id = state.active_player_id
        if active_player_id is None:
            raise GameLifecycleError("BattleStartRecord requires an active player.")
        return cls(
            record_id=f"battle-start:{state.game_id}:round-{state.battle_round:02d}",
            game_id=state.game_id,
            completed_setup_step=completed_setup_step,
            ruleset_descriptor_hash=state.ruleset_descriptor_hash,
            setup_sequence=state.setup_sequence,
            battle_round=state.battle_round,
            active_player_id=active_player_id,
            first_battle_phase=current_phase,
            turn_order=state.turn_order,
            readiness_snapshot=report.readiness_snapshot,
            setup_legality_report=report,
            pre_battle_checkpoint=pre_battle_checkpoint,
            post_battle_start_checkpoint=SetupReplayCheckpoint.from_state(
                state=state,
                checkpoint_kind="post_battle_start",
            ),
        )

    def to_payload(self) -> BattleStartRecordPayload:
        return {
            "record_id": self.record_id,
            "game_id": self.game_id,
            "source_id": self.source_id,
            "completed_setup_step": self.completed_setup_step.value,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "setup_sequence": [step.value for step in self.setup_sequence],
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "first_battle_phase": self.first_battle_phase.value,
            "turn_order": list(self.turn_order),
            "readiness_snapshot": self.readiness_snapshot.to_payload(),
            "setup_legality_report": self.setup_legality_report.to_payload(),
            "pre_battle_checkpoint": self.pre_battle_checkpoint.to_payload(),
            "post_battle_start_checkpoint": self.post_battle_start_checkpoint.to_payload(),
        }


class SetupCompletionGate:
    def evaluate(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
        reaction_frame_count: int = 0,
    ) -> SetupLegalityReport:
        if type(state) is not GameState:
            raise GameLifecycleError("SetupCompletionGate requires GameState.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("SetupCompletionGate requires DecisionController.")
        if type(config) is not GameConfig:
            raise GameLifecycleError("SetupCompletionGate requires GameConfig.")
        drain_state = SetupDecisionDrainState.from_decisions(
            decisions=decisions,
            reaction_frame_count=reaction_frame_count,
        )
        snapshot = PreBattleReadinessSnapshot.from_state(
            state=state,
            decisions=decisions,
            config=config,
        )
        violations = _setup_completion_violations(
            state=state,
            decisions=decisions,
            config=config,
            drain_state=drain_state,
            snapshot=snapshot,
        )
        return SetupLegalityReport(
            decision_drain_state=drain_state,
            readiness_snapshot=snapshot,
            violations=violations,
        )

    def invalid_status_if_not_ready(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
        reaction_frame_count: int = 0,
    ) -> LifecycleStatus | None:
        report = self.evaluate(
            state=state,
            decisions=decisions,
            config=config,
            reaction_frame_count=reaction_frame_count,
        )
        if report.is_legal:
            return None
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Setup completion gate rejected battle start.",
            payload={
                "invalid_reason": "setup_completion_gate_failed",
                "setup_legality_report": cast(JsonValue, report.to_payload()),
            },
        )

    def complete_setup_and_enter_battle(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        config: GameConfig,
        reaction_frame_count: int = 0,
    ) -> BattleStartRecord:
        report = self.evaluate(
            state=state,
            decisions=decisions,
            config=config,
            reaction_frame_count=reaction_frame_count,
        )
        if not report.is_legal:
            raise GameLifecycleError("Setup completion gate cannot enter battle when illegal.")
        pre_checkpoint = SetupReplayCheckpoint.from_state(
            state=state,
            checkpoint_kind="pre_battle_start",
        )
        completed_setup_step = state.complete_final_setup_step_before_battle()
        state.enter_battle()
        return BattleStartRecord.from_started_state(
            state=state,
            completed_setup_step=completed_setup_step,
            report=report,
            pre_battle_checkpoint=pre_checkpoint,
        )


def setup_completion_violation_code_from_token(token: object) -> SetupCompletionViolationCode:
    if type(token) is SetupCompletionViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SetupCompletionViolationCode token must be a string.")
    try:
        return SetupCompletionViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported setup completion violation: {token}.") from exc


def _setup_completion_violations(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
    drain_state: SetupDecisionDrainState,
    snapshot: PreBattleReadinessSnapshot,
) -> tuple[SetupCompletionViolation, ...]:
    violations: list[SetupCompletionViolation] = []
    if state.stage is not GameLifecycleStage.SETUP:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.SETUP_SEQUENCE_INCOMPLETE,
                "Setup completion can run only during setup.",
                field="stage",
            )
        )
    if not snapshot.setup_sequence_complete_after_current_step:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.SETUP_SEQUENCE_INCOMPLETE,
                "Setup sequence has not reached its final setup step.",
                field="current_setup_step",
            )
        )
    if drain_state.pending_decision_count > 0:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.PENDING_DECISION_QUEUE,
                "Setup completion requires an empty decision queue.",
                field="decision_queue",
                detail=cast(JsonValue, drain_state.to_payload()),
            )
        )
    if drain_state.reaction_frame_count > 0:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.REACTION_QUEUE_NOT_DRAINED,
                "Setup completion requires an empty reaction queue.",
                field="reaction_queue",
                detail=cast(JsonValue, drain_state.to_payload()),
            )
        )
    for player_id in snapshot.missing_army_player_ids:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.MISSING_ARMY,
                "Setup completion requires a mustered army for every player.",
                field="army_definitions",
                player_id=player_id,
            )
        )
    if not snapshot.mission_setup_present:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.MISSING_MISSION_SETUP,
                "Setup completion requires source-backed mission setup.",
                field="mission_setup",
            )
        )
    if snapshot.attacker_player_id is None or snapshot.defender_player_id is None:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_ATTACKER_DEFENDER,
                "Setup completion requires attacker and defender assignments.",
                field="mission_setup",
            )
        )
    for player_id in snapshot.missing_secondary_mission_player_ids:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_SECONDARY_MISSIONS,
                "Setup completion requires every player to choose Secondary Missions.",
                field="secondary_mission_choices",
                player_id=player_id,
            )
        )
    if not snapshot.battlefield_present:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.MISSING_BATTLEFIELD,
                "Setup completion requires a source-backed battlefield.",
                field="battlefield_state",
            )
        )
    if state.battlefield_state is None:
        return tuple(violations)

    _append_reserve_declaration_violations(
        violations=violations,
        state=state,
        decisions=decisions,
        config=config,
    )
    _append_deployment_violations(
        violations=violations,
        state=state,
        config=config,
    )
    _append_prebattle_step_violations(
        violations=violations,
        snapshot=snapshot,
    )
    return tuple(violations)


def _append_reserve_declaration_violations(
    *,
    violations: list[SetupCompletionViolation],
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    reserve_state = reserve_declaration_state_for_state(
        state=state,
        config=config,
        decisions=decisions,
        require_current_step=False,
    )
    if reserve_state.next_player_id is not None:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_BATTLE_FORMATIONS,
                "Setup completion requires Declare Battle Formations to be drained.",
                field="reserve_states",
                player_id=reserve_state.next_player_id,
                detail=cast(JsonValue, reserve_state.to_payload()),
            )
        )
    for player_id in state.player_ids:
        context = reserve_legality_context_for_player(
            state=state,
            config=config,
            player_id=player_id,
        )
        strategic_points = sum(
            reserve.points_contribution
            for reserve in state.reserve_states
            if reserve.player_id == player_id
            and reserve.reserve_kind is ReserveKind.STRATEGIC_RESERVES
            and reserve.status is ReserveStatus.IN_RESERVES
        )
        if strategic_points > context.strategic_reserves_points_limit:
            violations.append(
                SetupCompletionViolation(
                    SetupCompletionViolationCode.ILLEGAL_RESERVE_DECLARATION,
                    "Strategic Reserves points exceed the source-backed setup limit.",
                    field="reserve_states",
                    player_id=player_id,
                    detail={
                        "strategic_reserves_points": strategic_points,
                        "strategic_reserves_points_limit": context.strategic_reserves_points_limit,
                    },
                )
            )


def _append_deployment_violations(
    *,
    violations: list[SetupCompletionViolation],
    state: GameState,
    config: GameConfig,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Setup deployment audit requires a battlefield state.")
    setup_state = deployment_setup_state_for_state(state)
    if setup_state.next_player_id is not None:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_DEPLOYMENT,
                "Setup completion requires every deployable unit to be deployed or accounted for.",
                field="battlefield_state",
                player_id=setup_state.next_player_id,
                detail=cast(JsonValue, setup_state.to_payload()),
            )
        )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    try:
        scenario.assert_all_mustered_models_placed_or_accounted(
            deployment_completion_accounted_model_ids(state)
        )
    except PlacementError as exc:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_DEPLOYMENT,
                "Setup completion found unplaced or unaccounted models.",
                field="battlefield_state",
                detail={"error": str(exc)},
            )
        )
    try:
        assert_battlefield_units_in_coherency(
            scenario=scenario,
            ruleset_descriptor=config.ruleset_descriptor,
        )
    except PlacementError as exc:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.ILLEGAL_BATTLEFIELD_STATE,
                "Setup completion found illegal battlefield coherency.",
                field="battlefield_state",
                detail={"error": str(exc)},
            )
        )


def _append_prebattle_step_violations(
    *,
    violations: list[SetupCompletionViolation],
    snapshot: PreBattleReadinessSnapshot,
) -> None:
    if snapshot.redeploy_next_player_id is not None:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_REDEPLOY,
                "Setup completion requires redeploy decisions to be drained.",
                field="prebattle_action_records",
                player_id=snapshot.redeploy_next_player_id,
            )
        )
    if snapshot.prebattle_next_player_id is not None:
        violations.append(
            SetupCompletionViolation(
                SetupCompletionViolationCode.UNRESOLVED_PREBATTLE_ACTIONS,
                "Setup completion requires pre-battle actions to be drained.",
                field="prebattle_action_records",
                player_id=snapshot.prebattle_next_player_id,
            )
        )


def _next_redeploy_player_id(
    *,
    state: GameState,
    decisions: DecisionController,
) -> str | None:
    timing_state = redeploy_timing_state_for_state(state)
    return prebattle_next_player_id_for_timing_state(
        decisions=decisions,
        timing_state=timing_state,
    )


def _next_prebattle_player_id(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> str | None:
    timing_state = prebattle_timing_state_for_state(
        state,
        army_catalog=config.army_catalog,
    )
    return prebattle_next_player_id_for_timing_state(
        decisions=decisions,
        timing_state=timing_state,
    )


def _stable_hash(payload: JsonValue) -> str:
    encoded = json.dumps(
        validate_json_value(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


def _validate_required_string(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_string(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_required_string(field_name, value)


def _validate_string_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    tuple_values = cast(tuple[object, ...], values)
    return tuple(_validate_required_string(field_name, value) for value in tuple_values)


def _validate_setup_step_tuple(field_name: str, values: object) -> tuple[SetupStep, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    tuple_values = cast(tuple[object, ...], values)
    steps: list[SetupStep] = []
    for value in tuple_values:
        if type(value) is not SetupStep:
            raise GameLifecycleError(f"{field_name} must contain setup steps.")
        steps.append(value)
    if not steps:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(steps)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must be non-negative.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    result = _validate_non_negative_int(field_name, value)
    if result <= 0:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return result


def _validate_optional_non_negative_int(field_name: str, value: object) -> int | None:
    if value is None:
        return None
    return _validate_non_negative_int(field_name, value)


def _validate_sha256(field_name: str, value: object) -> str:
    text = _validate_required_string(field_name, value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise GameLifecycleError(f"{field_name} must be a SHA-256 hex digest.")
    return text


def _validate_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[SetupCompletionViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    tuple_values = cast(tuple[object, ...], values)
    violations: list[SetupCompletionViolation] = []
    for value in tuple_values:
        if type(value) is not SetupCompletionViolation:
            raise GameLifecycleError(f"{field_name} must contain setup violations.")
        violations.append(value)
    return tuple(violations)
