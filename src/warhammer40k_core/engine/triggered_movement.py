from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceRollState,
    DiceRollStatePayload,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    movement_mode_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import triggered_movement_validation as _validation
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_movement_source import ChargePlacement, charge_placement_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.move_ability_choices import chosen_move_keywords
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.physical_proposal_validation import (
    parse_movement_proposal_payload,
    physical_proposal_invalid_status,
)
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowPayload
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.take_to_the_skies import flight_selection
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    MovementRollbackRecordPayload,
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE = "select_triggered_movement"
DECLINE_TRIGGERED_MOVEMENT_OPTION_ID = "decline_triggered_movement"
TRIGGERED_MOVEMENT_PROPOSAL_ACTION = "surge_move"
TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND = "triggered_movement"
TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND = "triggered_movement_distance_reroll"


class TriggeredMovementKind(StrEnum):
    SURGE = "surge"
    TRIGGERED = "triggered"


class TriggeredMovementViolationCode(StrEnum):
    AIRCRAFT_INGRESS_ONLY = "aircraft_ingress_only"
    BATTLE_SHOCKED_SURGE_FORBIDDEN = "battle_shocked_surge_forbidden"
    ENGAGEMENT_RANGE_SURGE_FORBIDDEN = "engagement_range_surge_forbidden"
    SURGE_MOVE_ALREADY_USED_THIS_PHASE = "surge_move_already_used_this_phase"
    NORMAL_MOVE_ALREADY_USED_THIS_PHASE = "normal_move_already_used_this_phase"
    SURGE_NON_TARGET_ENGAGEMENT = "surge_non_target_engagement"
    SURGE_ENGAGEMENT_NOT_REACHED = "surge_engagement_not_reached"
    SURGE_MAXIMUM_APPROACH_NOT_REACHED = "surge_maximum_approach_not_reached"
    SURGE_REACHABILITY_UNRESOLVED = "surge_reachability_unresolved"


class TriggeredMovementDescriptorPayload(TypedDict):
    movement_kind: str
    source_rule_id: str
    trigger_timing: ReactionWindowPayload
    max_distance_inches: float
    movement_mode: str
    allow_battle_shocked: bool
    allow_within_engagement_range: bool
    one_per_phase: bool
    optional: bool


class TriggeredMovementViolationPayload(TypedDict):
    violation_code: str
    message: str


class TriggeredMovementResolutionPayload(TypedDict):
    unit_instance_id: str
    descriptor: TriggeredMovementDescriptorPayload
    attempted_placement: dict[str, JsonValue]
    witness: PathWitnessPayload
    restriction_violations: list[TriggeredMovementViolationPayload]
    path_validation_results: list[PathValidationResultPayload]
    terrain_path_legality_results: list[TerrainPathLegalityResultPayload]
    coherency_result: UnitCoherencyResultPayload
    rollback_record: MovementRollbackRecordPayload | None
    movement_payload: dict[str, JsonValue]


class TriggeredMovementEligibleUnitPayload(TypedDict):
    unit_instance_id: str
    hook_id: str
    source_id: str
    replay_payload: JsonValue
    decision_effect_payload: JsonValue
    distance_roll_state: DiceRollStatePayload | None
    distance_roll_bonus_inches: int
    distance_reroll_permission: RerollPermissionPayload | None


@dataclass(frozen=True, slots=True)
class TriggeredMovementDescriptor:
    movement_kind: TriggeredMovementKind
    source_rule_id: str
    trigger_timing: ReactionWindow
    max_distance_inches: float
    movement_mode: MovementMode = MovementMode.NORMAL
    allow_battle_shocked: bool = False
    allow_within_engagement_range: bool = False
    one_per_phase: bool = True
    optional: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "movement_kind",
            triggered_movement_kind_from_token(self.movement_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("TriggeredMovementDescriptor source_rule_id", self.source_rule_id),
        )
        if type(self.trigger_timing) is not ReactionWindow:
            raise GameLifecycleError(
                "TriggeredMovementDescriptor trigger_timing must be a ReactionWindow."
            )
        object.__setattr__(
            self,
            "max_distance_inches",
            _validation.validate_positive_number(
                "TriggeredMovementDescriptor max_distance_inches",
                self.max_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "movement_mode",
            movement_mode_from_token(self.movement_mode),
        )
        object.__setattr__(
            self,
            "allow_battle_shocked",
            _validation.validate_bool(
                "TriggeredMovementDescriptor allow_battle_shocked",
                self.allow_battle_shocked,
            ),
        )
        object.__setattr__(
            self,
            "allow_within_engagement_range",
            _validation.validate_bool(
                "TriggeredMovementDescriptor allow_within_engagement_range",
                self.allow_within_engagement_range,
            ),
        )
        object.__setattr__(
            self,
            "one_per_phase",
            _validation.validate_bool(
                "TriggeredMovementDescriptor one_per_phase", self.one_per_phase
            ),
        )
        object.__setattr__(
            self,
            "optional",
            _validation.validate_bool("TriggeredMovementDescriptor optional", self.optional),
        )

    @property
    def displacement_kind(self) -> ModelDisplacementKind:
        if self.movement_kind is TriggeredMovementKind.SURGE:
            return ModelDisplacementKind.SURGE_MOVE
        return ModelDisplacementKind.TRIGGERED_MOVE

    def to_payload(self) -> TriggeredMovementDescriptorPayload:
        return {
            "movement_kind": self.movement_kind.value,
            "source_rule_id": self.source_rule_id,
            "trigger_timing": self.trigger_timing.to_payload(),
            "max_distance_inches": self.max_distance_inches,
            "movement_mode": self.movement_mode.value,
            "allow_battle_shocked": self.allow_battle_shocked,
            "allow_within_engagement_range": self.allow_within_engagement_range,
            "one_per_phase": self.one_per_phase,
            "optional": self.optional,
        }

    @classmethod
    def from_payload(cls, payload: TriggeredMovementDescriptorPayload) -> Self:
        return cls(
            movement_kind=triggered_movement_kind_from_token(payload["movement_kind"]),
            source_rule_id=payload["source_rule_id"],
            trigger_timing=ReactionWindow.from_payload(payload["trigger_timing"]),
            max_distance_inches=payload["max_distance_inches"],
            movement_mode=movement_mode_from_token(payload["movement_mode"]),
            allow_battle_shocked=payload["allow_battle_shocked"],
            allow_within_engagement_range=payload["allow_within_engagement_range"],
            one_per_phase=payload["one_per_phase"],
            optional=payload["optional"],
        )


@dataclass(frozen=True, slots=True)
class TriggeredMovementViolation:
    violation_code: TriggeredMovementViolationCode
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            triggered_movement_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("TriggeredMovementViolation message", self.message),
        )

    def to_payload(self) -> TriggeredMovementViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
        }

    @classmethod
    def from_payload(cls, payload: TriggeredMovementViolationPayload) -> Self:
        return cls(
            violation_code=triggered_movement_violation_code_from_token(payload["violation_code"]),
            message=payload["message"],
        )


@dataclass(frozen=True, slots=True)
class TriggeredMovementResolution:
    unit_instance_id: str
    descriptor: TriggeredMovementDescriptor
    attempted_placement: ChargePlacement
    witness: PathWitness
    restriction_violations: tuple[TriggeredMovementViolation, ...]
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "TriggeredMovementResolution unit_instance_id",
                self.unit_instance_id,
            ),
        )
        if type(self.descriptor) is not TriggeredMovementDescriptor:
            raise GameLifecycleError("TriggeredMovementResolution descriptor must be a descriptor.")
        if type(self.attempted_placement) not in {UnitPlacement, RulesUnitPlacement}:
            raise GameLifecycleError(
                "TriggeredMovementResolution attempted_placement must be a UnitPlacement."
            )
        if charge_placement_id(self.attempted_placement) != self.unit_instance_id:
            raise GameLifecycleError("TriggeredMovementResolution attempted placement drift.")
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("TriggeredMovementResolution witness must be a PathWitness.")
        object.__setattr__(
            self,
            "restriction_violations",
            _validate_triggered_movement_violations(self.restriction_violations),
        )
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(self.path_validation_results),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(self.terrain_path_legality_results),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "TriggeredMovementResolution coherency_result must be UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "TriggeredMovementResolution rollback_record must be MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "TriggeredMovementResolution movement_payload",
                self.movement_payload,
            ),
        )

    @property
    def is_valid(self) -> bool:
        return (
            not self.restriction_violations
            and all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.coherency_result.is_coherent
            and self.rollback_record is None
        )

    def transition_batch(self, *, before: ChargePlacement) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid triggered movement cannot emit displacement records.")
        before_poses = {
            placement.model_instance_id: placement.pose for placement in before.model_placements
        }
        displacement_records: list[ModelDisplacementRecord] = []
        for placement in self.attempted_placement.model_placements:
            if placement.model_instance_id not in before_poses:
                raise GameLifecycleError("Triggered movement references an unknown model.")
            if placement.pose == before_poses[placement.model_instance_id]:
                continue
            model_path = self.witness.poses_for_model(placement.model_instance_id)
            displacement_records.append(
                ModelDisplacementRecord(
                    model_instance_id=placement.model_instance_id,
                    displacement_kind=self.descriptor.displacement_kind,
                    start_pose=before_poses[placement.model_instance_id],
                    end_pose=placement.pose,
                    path_witness=PathWitness.for_paths(
                        ((placement.model_instance_id, model_path),)
                    ),
                    source_phase=self.descriptor.trigger_timing.phase.value,
                    source_step=self.descriptor.trigger_timing.source_step,
                    source_rule_id=self.descriptor.source_rule_id,
                    source_event_id=self.descriptor.trigger_timing.source_event_id,
                )
            )
        return BattlefieldTransitionBatch(displacements=tuple(displacement_records))

    def selected_payload_drift_code(self, payload: dict[str, JsonValue]) -> str | None:
        selected_payload = _validate_json_object("Triggered movement selected payload", payload)
        if selected_payload.get("descriptor") != self.descriptor.to_payload():
            return "triggered_movement_descriptor_drift"
        if selected_payload.get("witness") != self.witness.to_payload():
            return "triggered_movement_witness_drift"
        expected_aircraft_policy = self.movement_payload.get("aircraft_movement_policies")
        if selected_payload.get("aircraft_movement_policies") != expected_aircraft_policy:
            return "triggered_movement_aircraft_policy_drift"
        if selected_payload.get("model_movements") != self.movement_payload["model_movements"]:
            return "triggered_movement_model_movement_witness_drift"
        if self.descriptor.movement_kind is TriggeredMovementKind.SURGE and any(
            selected_payload.get(key) != self.movement_payload[key]
            for key in ("surge_target_unit_instance_id", "surge_model_endpoints")
        ):
            return "surge_endpoint_authority_drift"
        return None

    def to_payload(self) -> TriggeredMovementResolutionPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "descriptor": self.descriptor.to_payload(),
            "attempted_placement": cast(
                dict[str, JsonValue],
                self.attempted_placement.to_payload(),
            ),
            "witness": self.witness.to_payload(),
            "restriction_violations": [
                violation.to_payload() for violation in self.restriction_violations
            ],
            "path_validation_results": [
                result.to_payload() for result in self.path_validation_results
            ],
            "terrain_path_legality_results": [
                result.to_payload() for result in self.terrain_path_legality_results
            ],
            "coherency_result": self.coherency_result.to_payload(),
            "rollback_record": (
                None if self.rollback_record is None else self.rollback_record.to_payload()
            ),
            "movement_payload": self.movement_payload,
        }


@dataclass(frozen=True, slots=True)
class TriggeredMovementEligibleUnit:
    unit_instance_id: str
    hook_id: str
    source_id: str
    replay_payload: JsonValue = None
    decision_effect_payload: JsonValue = None
    distance_roll_state: DiceRollState | None = None
    distance_roll_bonus_inches: int = 0
    distance_reroll_permission: RerollPermission | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "TriggeredMovementEligibleUnit unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "hook_id",
            _validate_identifier("TriggeredMovementEligibleUnit hook_id", self.hook_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TriggeredMovementEligibleUnit source_id", self.source_id),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        object.__setattr__(
            self,
            "decision_effect_payload",
            validate_json_value(self.decision_effect_payload),
        )
        if self.distance_roll_state is not None and type(self.distance_roll_state) is not (
            DiceRollState
        ):
            raise GameLifecycleError(
                "Triggered movement distance_roll_state must be DiceRollState."
            )
        object.__setattr__(
            self,
            "distance_roll_bonus_inches",
            _validation.validate_non_negative_int(
                "TriggeredMovementEligibleUnit distance_roll_bonus_inches",
                self.distance_roll_bonus_inches,
            ),
        )
        if (
            self.distance_reroll_permission is not None
            and type(self.distance_reroll_permission) is not RerollPermission
        ):
            raise GameLifecycleError(
                "Triggered movement distance reroll permission must be RerollPermission."
            )
        if (self.distance_roll_state is None) != (self.distance_reroll_permission is None):
            raise GameLifecycleError(
                "Triggered movement distance roll and reroll permission must be paired."
            )
        if self.distance_roll_state is None and self.distance_roll_bonus_inches != 0:
            raise GameLifecycleError(
                "Triggered movement distance roll bonus requires a distance roll."
            )

    def to_payload(self) -> TriggeredMovementEligibleUnitPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
            "distance_roll_state": (
                None if self.distance_roll_state is None else self.distance_roll_state.to_payload()
            ),
            "distance_roll_bonus_inches": self.distance_roll_bonus_inches,
            "distance_reroll_permission": (
                None
                if self.distance_reroll_permission is None
                else self.distance_reroll_permission.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: TriggeredMovementEligibleUnitPayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            hook_id=payload["hook_id"],
            source_id=payload["source_id"],
            replay_payload=payload["replay_payload"],
            decision_effect_payload=payload["decision_effect_payload"],
            distance_roll_state=(
                None
                if payload["distance_roll_state"] is None
                else DiceRollState.from_payload(payload["distance_roll_state"])
            ),
            distance_roll_bonus_inches=payload["distance_roll_bonus_inches"],
            distance_reroll_permission=(
                None
                if payload["distance_reroll_permission"] is None
                else RerollPermission.from_payload(payload["distance_reroll_permission"])
            ),
        )


@dataclass(frozen=True, slots=True)
class TriggeredMovementRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    active_player_id: str
    current_phase: str
    unit_instance_id: str
    descriptor: TriggeredMovementDescriptor
    resolutions: tuple[TriggeredMovementResolution, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("TriggeredMovementRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("TriggeredMovementRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("TriggeredMovementRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("TriggeredMovementRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "TriggeredMovementRequest active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "current_phase",
            _validate_identifier("TriggeredMovementRequest current_phase", self.current_phase),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "TriggeredMovementRequest unit_instance_id",
                self.unit_instance_id,
            ),
        )
        if type(self.descriptor) is not TriggeredMovementDescriptor:
            raise GameLifecycleError(
                "TriggeredMovementRequest descriptor must be a TriggeredMovementDescriptor."
            )
        object.__setattr__(
            self,
            "resolutions",
            _validate_triggered_movement_resolutions(
                self.resolutions,
                unit_instance_id=self.unit_instance_id,
                descriptor=self.descriptor,
            ),
        )

    def to_decision_request(self) -> DecisionRequest:
        return DecisionRequest(
            request_id=self.request_id,
            decision_type=SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
            actor_id=self.player_id,
            payload={
                "game_id": self.game_id,
                "battle_round": self.battle_round,
                "active_player_id": self.active_player_id,
                "current_phase": self.current_phase,
                "player_id": self.player_id,
                "unit_instance_id": self.unit_instance_id,
                "descriptor": validate_json_value(self.descriptor.to_payload()),
                "triggered_movement_kind": self.descriptor.movement_kind.value,
                "source_rule_id": self.descriptor.source_rule_id,
                "trigger_timing": validate_json_value(self.descriptor.trigger_timing.to_payload()),
            },
            options=self._decision_options(),
        )

    def _decision_options(self) -> tuple[DecisionOption, ...]:
        options: list[DecisionOption] = []
        if self.descriptor.optional:
            options.append(
                DecisionOption(
                    option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
                    label="Decline Triggered Movement",
                    payload=validate_json_value(
                        {
                            "triggered_movement_kind": self.descriptor.movement_kind.value,
                            "displacement_kind": self.descriptor.displacement_kind.value,
                            "unit_instance_id": self.unit_instance_id,
                            "descriptor": self.descriptor.to_payload(),
                            "source_rule_id": self.descriptor.source_rule_id,
                            "trigger_timing": self.descriptor.trigger_timing.to_payload(),
                            "movement_phase_action": None,
                            "declined": True,
                        }
                    ),
                )
            )
        for index, resolution in enumerate(self.resolutions, start=1):
            option_id = f"{self.descriptor.movement_kind.value}_move_{index:03d}"
            options.append(
                DecisionOption(
                    option_id=option_id,
                    label=(
                        f"{self.descriptor.movement_kind.value.title()} Move {index}"
                        + (
                            " - Take to the Skies"
                            if flight_selection(resolution.movement_payload)
                            else ""
                        )
                        + (
                            " - gain " + ", ".join(keywords)
                            if (keywords := chosen_move_keywords(resolution.movement_payload))
                            else ""
                        )
                    ),
                    payload=validate_json_value(
                        {
                            "triggered_movement_kind": self.descriptor.movement_kind.value,
                            "displacement_kind": self.descriptor.displacement_kind.value,
                            "unit_instance_id": self.unit_instance_id,
                            "descriptor": self.descriptor.to_payload(),
                            "witness": resolution.witness.to_payload(),
                            **resolution.movement_payload,
                        }
                    ),
                )
            )
        return tuple(options)


@dataclass(frozen=True, slots=True)
class TriggeredMovementHandler:
    ruleset_descriptor: RulesetDescriptor | None = None

    def request_from_state(
        self,
        *,
        state: GameState,
        unit_instance_id: str,
        descriptor: TriggeredMovementDescriptor,
        candidate_witnesses: tuple[PathWitness, ...],
        decisions: DecisionController | None = None,
    ) -> DecisionRequest:
        from warhammer40k_core.engine.triggered_movement_handler_impl import request_from_state

        return request_from_state(
            handler=self,
            state=state,
            unit_instance_id=unit_instance_id,
            descriptor=descriptor,
            candidate_witnesses=candidate_witnesses,
            decisions=decisions,
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.triggered_movement_handler_impl import apply_decision

        return apply_decision(
            handler=self,
            state=state,
            result=result,
            decisions=decisions,
        )

    def apply_proposal_decision(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.triggered_movement_handler_impl import (
            apply_proposal_decision,
        )

        return apply_proposal_decision(
            handler=self,
            state=state,
            request=request,
            result=result,
            decisions=decisions,
        )


def is_triggered_movement_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Triggered movement proposal check requires a DecisionRequest.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    proposal_payload = payload.get("proposal_request")
    if not isinstance(proposal_payload, dict):
        return False
    context = proposal_payload.get("context")
    if not isinstance(context, dict):
        return False
    return context.get("context_kind") == TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND


def invalid_triggered_movement_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    if not is_triggered_movement_proposal_request(request):
        raise GameLifecycleError("Triggered movement proposal validation received wrong request.")
    from warhammer40k_core.engine.surge_authority import invalid_surge_authority

    authority = invalid_surge_authority(
        state=state, decisions=decisions, request=request, result=result
    )
    if authority is not None:
        return authority
    proposal_request = _triggered_movement_proposal_request_from_request(request)
    submission = parse_movement_proposal_payload(
        proposal_request=proposal_request,
        payload=result.payload,
    )
    if isinstance(submission, ProposalValidationResult):
        return _reject_invalid_triggered_movement_proposal(
            state=state,
            result=result,
            proposal_validation=submission,
            message="Triggered movement proposal is malformed.",
        )
    proposal_validation = submission.validation_result_for_request(proposal_request)
    if proposal_validation.is_valid:
        return None
    return _reject_invalid_triggered_movement_proposal(
        state=state,
        result=result,
        proposal_validation=proposal_validation,
        message="Triggered movement proposal does not match the pending request.",
    )


def triggered_movement_kind_from_token(token: object) -> TriggeredMovementKind:
    if type(token) is TriggeredMovementKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TriggeredMovementKind token must be a string.")
    try:
        return TriggeredMovementKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported TriggeredMovementKind token: {token}.") from exc


def triggered_movement_violation_code_from_token(
    token: object,
) -> TriggeredMovementViolationCode:
    if type(token) is TriggeredMovementViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TriggeredMovementViolationCode token must be a string.")
    try:
        return TriggeredMovementViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported TriggeredMovementViolationCode token: {token}."
        ) from exc


def is_triggered_movement_distance_reroll_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Triggered movement reroll query requires DecisionRequest.")
    return (
        request.decision_type == DICE_REROLL_DECISION_TYPE
        and isinstance(request.payload, dict)
        and request.payload.get("context_kind") == TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND
    )


def _triggered_movement_proposal_request_from_request(
    request: DecisionRequest,
) -> MovementProposalRequest:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    if proposal_request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Triggered movement requires a movement proposal request.")
    if proposal_request.proposal_kind is not ProposalKind.SURGE_MOVE:
        raise GameLifecycleError("Triggered movement proposal kind drift.")
    context = proposal_request.context or {}
    if context.get("context_kind") != TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND:
        raise GameLifecycleError("Triggered movement proposal context drift.")
    _descriptor_from_proposal_request(proposal_request)
    return proposal_request


def _descriptor_from_proposal_request(
    proposal_request: MovementProposalRequest,
) -> TriggeredMovementDescriptor:
    context = proposal_request.context or {}
    descriptor_payload = context.get("descriptor")
    if not isinstance(descriptor_payload, dict):
        raise GameLifecycleError("Triggered movement proposal missing descriptor context.")
    return TriggeredMovementDescriptor.from_payload(
        cast(TriggeredMovementDescriptorPayload, descriptor_payload)
    )


def _triggered_movement_proposal_retry_request(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    return MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=proposal_request.game_id,
        battle_round=proposal_request.battle_round,
        phase=proposal_request.phase,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=rejected_result.result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action=proposal_request.movement_phase_action,
        context=proposal_request.context,
    ).to_decision_request()


def _reject_invalid_triggered_movement_proposal(
    *,
    state: GameState,
    result: DecisionResult,
    proposal_validation: ProposalValidationResult,
    message: str,
) -> LifecycleStatus:
    return physical_proposal_invalid_status(
        state=state,
        result=result,
        proposal_validation=proposal_validation,
        message=message,
        phase_body_status="triggered_movement_proposal_invalid",
    )


def _triggered_movement_unit_selection_declined_payload(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    result: DecisionResult,
    descriptor: TriggeredMovementDescriptor,
    eligible_units: tuple[TriggeredMovementEligibleUnit, ...],
) -> dict[str, JsonValue]:
    return _validate_json_object(
        "triggered movement unit selection declined payload",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": _current_battle_phase_value(state),
            "triggered_movement_kind": descriptor.movement_kind.value,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_timing": descriptor.trigger_timing.to_payload(),
            "descriptor": descriptor.to_payload(),
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "triggered_movement_declined",
            "movement_phase_action": None,
            "declined": True,
            "eligible_units": [unit.to_payload() for unit in eligible_units],
        },
    )


def _eligible_units_from_request_payload(  # pyright: ignore[reportUnusedFunction]
    payload: dict[str, JsonValue],
) -> tuple[TriggeredMovementEligibleUnit, ...]:
    raw_units = payload.get("eligible_units")
    if not isinstance(raw_units, list):
        raise GameLifecycleError("Triggered movement unit selection missing eligible units.")
    units: list[TriggeredMovementEligibleUnit] = []
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            raise GameLifecycleError("Triggered movement eligible units must be objects.")
        units.append(
            TriggeredMovementEligibleUnit.from_payload(
                cast(TriggeredMovementEligibleUnitPayload, raw_unit)
            )
        )
    return _validate_eligible_units(tuple(units))


def _eligible_unit_by_id(  # pyright: ignore[reportUnusedFunction]
    eligible_units: tuple[TriggeredMovementEligibleUnit, ...],
    *,
    unit_instance_id: str,
) -> TriggeredMovementEligibleUnit:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matching = tuple(unit for unit in eligible_units if unit.unit_instance_id == requested_unit_id)
    if len(matching) != 1:
        raise GameLifecycleError("Triggered movement selected unit is not eligible.")
    return matching[0]


def _validate_eligible_units(
    values: object,
) -> tuple[TriggeredMovementEligibleUnit, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Triggered movement eligible units must be a tuple.")
    units: list[TriggeredMovementEligibleUnit] = []
    seen_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TriggeredMovementEligibleUnit:
            raise GameLifecycleError(
                "Triggered movement eligible units must contain eligible units."
            )
        if value.unit_instance_id in seen_ids:
            raise GameLifecycleError("Triggered movement eligible unit IDs must be unique.")
        seen_ids.add(value.unit_instance_id)
        units.append(value)
    return tuple(sorted(units, key=lambda unit: unit.unit_instance_id))


def _triggered_movement_invalid_payload(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    result: DecisionResult,
    unit_instance_id: str,
    descriptor: TriggeredMovementDescriptor,
    resolution: TriggeredMovementResolution,
    violation_code: str,
) -> dict[str, JsonValue]:
    return _validate_json_object(
        "triggered movement invalid payload",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": _current_battle_phase_value(state),
            "unit_instance_id": unit_instance_id,
            "triggered_movement_kind": descriptor.movement_kind.value,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_timing": descriptor.trigger_timing.to_payload(),
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "triggered_movement_invalid",
            "violation_code": violation_code,
            **resolution.movement_payload,
        },
    )


def _triggered_movement_resolved_payload(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    result: DecisionResult,
    unit_instance_id: str,
    descriptor: TriggeredMovementDescriptor,
    resolution: TriggeredMovementResolution,
    transition_batch: BattlefieldTransitionBatch,
) -> dict[str, JsonValue]:
    return _validate_json_object(
        "triggered movement resolved payload",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": _current_battle_phase_value(state),
            "unit_instance_id": unit_instance_id,
            "triggered_movement_kind": descriptor.movement_kind.value,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_timing": descriptor.trigger_timing.to_payload(),
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "triggered_movement_resolved",
            "transition_batch": validate_json_value(transition_batch.to_payload()),
            **resolution.movement_payload,
        },
    )


def _triggered_movement_declined_payload(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    result: DecisionResult,
    unit_instance_id: str,
    descriptor: TriggeredMovementDescriptor,
) -> dict[str, JsonValue]:
    return _validate_json_object(
        "triggered movement declined payload",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": _current_battle_phase_value(state),
            "unit_instance_id": unit_instance_id,
            "triggered_movement_kind": descriptor.movement_kind.value,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_timing": descriptor.trigger_timing.to_payload(),
            "descriptor": descriptor.to_payload(),
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "triggered_movement_declined",
            "movement_phase_action": None,
            "declined": True,
        },
    )


def _triggered_movement_violation_code(  # pyright: ignore[reportUnusedFunction]
    resolution: TriggeredMovementResolution,
) -> str:
    if resolution.restriction_violations:
        return resolution.restriction_violations[0].violation_code.value
    for path_result in resolution.path_validation_results:
        if path_result.violations:
            return path_result.violations[0].violation_code
    for terrain_result in resolution.terrain_path_legality_results:
        if terrain_result.violations:
            return terrain_result.violations[0].violation_code
    if resolution.rollback_record is not None:
        return "unit_coherency_broken"
    return "triggered_movement_invalid"


def _request_payload_for_result(  # pyright: ignore[reportUnusedFunction]
    *,
    decisions: DecisionController,
    result: DecisionResult,
) -> dict[str, JsonValue]:
    for request in decisions.queue.pending_requests:
        if request.request_id == result.request_id:
            return _decision_payload_object(request.payload)
    for record in reversed(decisions.records):
        if record.result == result:
            return _decision_payload_object(record.request.payload)
    raise GameLifecycleError("DecisionResult does not match a known triggered movement request.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:  # pyright: ignore[reportUnusedFunction]
    return battlefield_scenario_for_state(state=state)


def _current_battle_phase_value(state: GameState) -> str | None:
    current_phase = state.current_battle_phase
    return None if current_phase is None else current_phase.value


def _validate_triggered_movement_state_ready(state: GameState) -> None:  # pyright: ignore[reportUnusedFunction]
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Triggered movement requires battle stage.")
    if state.current_battle_phase is None:
        raise GameLifecycleError("Triggered movement requires current battle phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("Triggered movement requires active_player_id.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Triggered movement requires battlefield_state.")


def _validate_reaction_window_matches_state(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    descriptor: TriggeredMovementDescriptor,
) -> None:
    if type(descriptor) is not TriggeredMovementDescriptor:
        raise GameLifecycleError("Triggered movement requires a descriptor.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Triggered movement requires current battle phase.")
    if descriptor.trigger_timing.phase is not current_phase:
        raise GameLifecycleError(
            "Triggered movement trigger phase must match current battle phase."
        )


def _ruleset_descriptor_for_handler(  # pyright: ignore[reportUnusedFunction]
    handler: TriggeredMovementHandler,
) -> RulesetDescriptor:
    if type(handler) is not TriggeredMovementHandler:
        raise GameLifecycleError("Triggered movement requires a TriggeredMovementHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Triggered movement requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_object(  # pyright: ignore[reportUnusedFunction]
    payload: dict[str, JsonValue], key: str
) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be an object: {key}.")
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:  # pyright: ignore[reportUnusedFunction]
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


def _payload_optional_bool(payload: dict[str, JsonValue], key: str) -> bool:  # pyright: ignore[reportUnusedFunction]
    if key not in payload:
        return False
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Decision payload key must be a bool: {key}.")
    return value


def _payload_path_witness(  # pyright: ignore[reportUnusedFunction]
    payload: dict[str, JsonValue], key: str
) -> PathWitness:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be a PathWitness payload: {key}.")
    return PathWitness.from_payload(cast(PathWitnessPayload, value))


def _validate_triggered_movement_declined_payload(  # pyright: ignore[reportUnusedFunction]
    *,
    payload: dict[str, JsonValue],
    descriptor: TriggeredMovementDescriptor,
    unit_instance_id: str,
) -> None:
    if payload.get("triggered_movement_kind") != descriptor.movement_kind.value:
        raise GameLifecycleError("Declined triggered movement kind drift.")
    if payload.get("displacement_kind") != descriptor.displacement_kind.value:
        raise GameLifecycleError("Declined triggered movement displacement drift.")
    if payload.get("unit_instance_id") != unit_instance_id:
        raise GameLifecycleError("Declined triggered movement unit drift.")
    if payload.get("descriptor") != descriptor.to_payload():
        raise GameLifecycleError("Declined triggered movement descriptor drift.")
    if payload.get("source_rule_id") != descriptor.source_rule_id:
        raise GameLifecycleError("Declined triggered movement source rule drift.")
    if payload.get("trigger_timing") != descriptor.trigger_timing.to_payload():
        raise GameLifecycleError("Declined triggered movement trigger timing drift.")
    if payload.get("movement_phase_action") is not None:
        raise GameLifecycleError("Declined triggered movement cannot include a movement action.")


def _validate_triggered_movement_resolutions(
    values: object,
    *,
    unit_instance_id: str,
    descriptor: TriggeredMovementDescriptor,
) -> tuple[TriggeredMovementResolution, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("TriggeredMovementRequest resolutions must be a tuple.")
    if not values:
        raise GameLifecycleError("TriggeredMovementRequest requires at least one resolution.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    validated: list[TriggeredMovementResolution] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TriggeredMovementResolution:
            raise GameLifecycleError(
                "TriggeredMovementRequest resolutions must contain resolutions."
            )
        if value.unit_instance_id != requested_unit_id:
            raise GameLifecycleError("TriggeredMovementRequest resolution unit drift.")
        if value.descriptor != descriptor:
            raise GameLifecycleError("TriggeredMovementRequest resolution descriptor drift.")
        if not value.is_valid:
            raise GameLifecycleError("TriggeredMovementRequest options must be valid choices.")
        validated.append(value)
    return tuple(validated)


def _validate_triggered_movement_violations(
    values: object,
) -> tuple[TriggeredMovementViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Triggered movement violations must be a tuple.")
    return tuple(
        _validate_triggered_movement_violation(value) for value in cast(tuple[object, ...], values)
    )


def _validate_triggered_movement_violation(value: object) -> TriggeredMovementViolation:
    if type(value) is not TriggeredMovementViolation:
        raise GameLifecycleError("Triggered movement violations must contain violations.")
    return value


def _validate_path_validation_result_tuple(
    values: object,
) -> tuple[PathValidationResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("path_validation_results must be a tuple.")
    return tuple(
        _validate_path_validation_result(value) for value in cast(tuple[object, ...], values)
    )


def _validate_path_validation_result(value: object) -> PathValidationResult:
    if type(value) is not PathValidationResult:
        raise GameLifecycleError("path_validation_results must contain PathValidationResult.")
    return value


def _validate_terrain_path_legality_result_tuple(
    values: object,
) -> tuple[TerrainPathLegalityResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("terrain_path_legality_results must be a tuple.")
    return tuple(
        _validate_terrain_path_legality_result(value) for value in cast(tuple[object, ...], values)
    )


def _validate_terrain_path_legality_result(value: object) -> TerrainPathLegalityResult:
    if type(value) is not TerrainPathLegalityResult:
        raise GameLifecycleError(
            "terrain_path_legality_results must contain TerrainPathLegalityResult."
        )
    return value


def _validate_path_witness_tuple(  # pyright: ignore[reportUnusedFunction]
    values: object,
) -> tuple[PathWitness, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("candidate_witnesses must be a tuple.")
    return tuple(_validate_path_witness(value) for value in cast(tuple[object, ...], values))


def _validate_path_witness(value: object) -> PathWitness:
    if type(value) is not PathWitness:
        raise GameLifecycleError("candidate_witnesses must contain PathWitness values.")
    return value


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    validated = validate_json_value(value)
    if not isinstance(validated, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(  # pyright: ignore[reportUnusedFunction]
    field_name: str, values: object
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(field_name, value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate values.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value
