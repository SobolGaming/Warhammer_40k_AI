from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZoneError,
    DeploymentZonePayload,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    ModelPlacementPayload,
    ModelPlacementRecord,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    battlefield_placement_kind_from_token,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_prebattle_redeploy import (
    catalog_redeploy_permission_for_view,
    catalog_redeploy_selection_options,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
    terrain_endpoint_placement_violation,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    MissionSetupError,
    MissionSetupPayload,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
    record_prebattle_action,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState, ReserveStatus
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    create_sequencing_decision_request,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_abilities import (
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyContext,
    UnitCoherencyResult,
    unit_placement_coherency_result,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    PathWitnessPayload,
    is_degenerate_endpoint_only_real_movement_path,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.volume import Model

SELECT_REDEPLOY_UNIT_DECISION_TYPE = "select_redeploy_unit"
SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE = "submit_redeploy_placement"
SELECT_PREBATTLE_ACTION_DECISION_TYPE = "select_prebattle_action"
SUBMIT_SCOUT_MOVE_DECISION_TYPE = "submit_scout_move"
SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE = "submit_scout_reserve_setup"

REDEPLOY_PROPOSAL_KIND = "redeploy_placement"
SCOUT_MOVE_PROPOSAL_KIND = "scout_move"
SCOUT_RESERVE_SETUP_PROPOSAL_KIND = "scout_reserve_setup"

CORE_REDEPLOY_SOURCE_RULE_ID = "core_rules:redeploy"
CORE_SCOUTS_SOURCE_RULE_ID = "core_rules:scouts"
SCOUT_ENEMY_DISTANCE_INCHES = 8.0
PREBATTLE_SEQUENCING_EVENT_TYPE = "sequencing_order_resolved"
_EPSILON = 1e-9


class PreBattleViolationCode(StrEnum):
    STALE_PROPOSAL_REQUEST = "stale_proposal_request"
    PROPOSAL_KIND_DRIFT = "proposal_kind_drift"
    GAME_ID_DRIFT = "game_id_drift"
    RULESET_HASH_DRIFT = "ruleset_hash_drift"
    SETUP_STEP_DRIFT = "setup_step_drift"
    PLAYER_DRIFT = "player_drift"
    UNIT_DRIFT = "unit_drift"
    ACTION_KIND_DRIFT = "action_kind_drift"
    PLACEMENT_KIND_DRIFT = "placement_kind_drift"
    SOURCE_RULE_DRIFT = "source_rule_drift"
    UNIT_NOT_ELIGIBLE = "unit_not_eligible"
    UNIT_NOT_PLACED = "unit_not_placed"
    RESERVE_STATE_NOT_UNARRIVED = "reserve_state_not_unarrived"
    RESERVE_KIND_MISMATCH = "reserve_kind_mismatch"
    MODEL_SET_DRIFT = "model_set_drift"
    WRONG_UNIT_MODEL = "wrong_unit_model"
    BATTLEFIELD_EDGE_CROSSED = "battlefield_edge_crossed"
    DEPLOYMENT_ZONE_VIOLATION = "deployment_zone_violation"
    MODEL_OVERLAP = "model_overlap"
    TERRAIN_ENDPOINT_ILLEGAL = "terrain_endpoint_illegal"
    OBJECTIVE_MARKER_ENDPOINT_OVERLAP = "objective_marker_endpoint_overlap"
    ENEMY_ENGAGEMENT_RANGE = "enemy_engagement_range"
    UNIT_COHERENCY_BROKEN = "unit_coherency_broken"
    WITNESS_REQUIRED = "witness_required"
    WITNESS_MODEL_SET_DRIFT = "witness_model_set_drift"
    WITNESS_START_DRIFT = "witness_start_drift"
    ENDPOINT_ONLY_PATH = "endpoint_only_path"
    PATH_VALIDATION_FAILED = "path_validation_failed"
    TERRAIN_PATH_VALIDATION_FAILED = "terrain_path_validation_failed"
    SCOUT_ENEMY_DISTANCE = "scout_enemy_distance"
    DEDICATED_TRANSPORT_REQUIRED = "dedicated_transport_required"
    TRANSPORT_CARGO_NOT_ALL_SCOUTS = "transport_cargo_not_all_scouts"


class ScoutAbilityInstancePayload(TypedDict):
    model_instance_id: str
    distance_inches: float
    source_id: str


class PreBattleTimingWindowStatePayload(TypedDict):
    setup_step: str
    next_player_id: str | None
    available_action_count_by_player: dict[str, int]
    completed_player_ids: list[str]


class PreBattleProposalRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    setup_step: str
    player_id: str
    unit_instance_id: str
    component_unit_instance_ids: list[str]
    model_instance_ids: list[str]
    proposal_kind: str
    action_kind: str
    source_rule_id: str
    placement_kind: str | None
    scout_distance_inches: float | None
    deployment_zone_ids: list[str]
    legal_deployment_zones: list[DeploymentZonePayload]
    mission_setup: MissionSetupPayload
    ruleset_descriptor_hash: str
    source_decision_request_id: str
    source_decision_result_id: str
    context: dict[str, JsonValue]


class PreBattlePlacementProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    game_id: str
    ruleset_descriptor_hash: str
    setup_step: str
    player_id: str
    unit_instance_id: str
    action_kind: str
    source_rule_id: str
    placement_kind: str
    model_placements: list[ModelPlacementPayload]
    context: NotRequired[dict[str, JsonValue]]


class ScoutMoveProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    game_id: str
    ruleset_descriptor_hash: str
    setup_step: str
    player_id: str
    unit_instance_id: str
    action_kind: str
    source_rule_id: str
    scout_distance_inches: float
    witness: PathWitnessPayload
    context: NotRequired[dict[str, JsonValue]]


class PreBattleViolationPayload(TypedDict):
    violation_code: str
    message: str
    field: str | None
    model_instance_id: str | None
    blocker_id: str | None


class PreBattleResolutionPayload(TypedDict):
    proposal: dict[str, JsonValue]
    is_valid: bool
    violations: list[PreBattleViolationPayload]
    coherency_result: dict[str, JsonValue] | None
    transition_batch: dict[str, JsonValue] | None
    removal_batch: dict[str, JsonValue] | None
    placement_batch: dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class ScoutAbilityInstance:
    model_instance_id: str
    distance_inches: float
    source_id: str = CORE_SCOUTS_SOURCE_RULE_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("ScoutAbilityInstance model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "distance_inches",
            _validate_positive_number("ScoutAbilityInstance distance_inches", self.distance_inches),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ScoutAbilityInstance source_id", self.source_id),
        )

    def to_payload(self) -> ScoutAbilityInstancePayload:
        return {
            "model_instance_id": self.model_instance_id,
            "distance_inches": self.distance_inches,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ScoutAbilityInstancePayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            distance_inches=payload["distance_inches"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PreBattleTimingWindowState:
    setup_step: SetupStep
    next_player_id: str | None
    available_action_count_by_player: dict[str, int]
    completed_player_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.setup_step not in {SetupStep.REDEPLOY_UNITS, SetupStep.RESOLVE_PREBATTLE_ACTIONS}:
            raise GameLifecycleError("PreBattleTimingWindowState requires a pre-battle step.")
        object.__setattr__(
            self,
            "next_player_id",
            _validate_optional_identifier(
                "PreBattleTimingWindowState next_player_id",
                self.next_player_id,
            ),
        )
        counts: dict[str, int] = {}
        for player_id, count in self.available_action_count_by_player.items():
            counts[_validate_identifier("PreBattleTimingWindowState player_id", player_id)] = (
                _validate_non_negative_int("PreBattleTimingWindowState action count", count)
            )
        object.__setattr__(self, "available_action_count_by_player", counts)
        object.__setattr__(
            self,
            "completed_player_ids",
            _validate_identifier_tuple(
                "PreBattleTimingWindowState completed_player_ids",
                self.completed_player_ids,
            ),
        )

    def to_payload(self) -> PreBattleTimingWindowStatePayload:
        return {
            "setup_step": self.setup_step.value,
            "next_player_id": self.next_player_id,
            "available_action_count_by_player": dict(self.available_action_count_by_player),
            "completed_player_ids": list(self.completed_player_ids),
        }


@dataclass(frozen=True, slots=True)
class PreBattleProposalRequest:
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    setup_step: SetupStep
    player_id: str
    unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    model_instance_ids: tuple[str, ...]
    proposal_kind: str
    action_kind: PreBattleActionKind
    source_rule_id: str
    deployment_zones: tuple[DeploymentZone, ...]
    mission_setup: MissionSetup
    ruleset_descriptor_hash: str
    source_decision_request_id: str
    source_decision_result_id: str
    placement_kind: BattlefieldPlacementKind | None = None
    scout_distance_inches: float | None = None
    context: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("PreBattleProposalRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "decision_type",
            _validate_prebattle_proposal_decision_type(self.decision_type),
        )
        object.__setattr__(
            self,
            "actor_id",
            _validate_identifier("PreBattleProposalRequest actor_id", self.actor_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PreBattleProposalRequest game_id", self.game_id),
        )
        object.__setattr__(self, "setup_step", _setup_step_from_token(self.setup_step))
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PreBattleProposalRequest player_id", self.player_id),
        )
        if self.actor_id != self.player_id:
            raise GameLifecycleError("PreBattleProposalRequest actor_id must match player_id.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "PreBattleProposalRequest unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "component_unit_instance_ids",
            _validate_identifier_tuple(
                "PreBattleProposalRequest component_unit_instance_ids",
                self.component_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "PreBattleProposalRequest model_instance_ids",
                self.model_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_prebattle_proposal_kind(self.proposal_kind),
        )
        object.__setattr__(
            self,
            "action_kind",
            _action_kind_from_token(self.action_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PreBattleProposalRequest source_rule_id", self.source_rule_id),
        )
        zones = _validate_deployment_zone_tuple(
            "PreBattleProposalRequest deployment_zones",
            self.deployment_zones,
        )
        if not zones:
            raise GameLifecycleError("PreBattleProposalRequest requires deployment zones.")
        for zone in zones:
            if zone.player_id != self.player_id:
                raise GameLifecycleError("PreBattleProposalRequest deployment zone player drift.")
        object.__setattr__(self, "deployment_zones", zones)
        if type(self.mission_setup) is not MissionSetup:
            raise GameLifecycleError("PreBattleProposalRequest mission_setup must be MissionSetup.")
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "PreBattleProposalRequest ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "PreBattleProposalRequest source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "PreBattleProposalRequest source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        placement_kind = None
        if self.placement_kind is not None:
            placement_kind = battlefield_placement_kind_from_token(self.placement_kind)
        object.__setattr__(self, "placement_kind", placement_kind)
        if (
            self.proposal_kind in {REDEPLOY_PROPOSAL_KIND, SCOUT_RESERVE_SETUP_PROPOSAL_KIND}
            and placement_kind is None
        ):
            raise GameLifecycleError("Placement pre-battle requests require placement_kind.")
        if self.proposal_kind == SCOUT_MOVE_PROPOSAL_KIND:
            if self.scout_distance_inches is None:
                raise GameLifecycleError("Scout Move requests require scout_distance_inches.")
            object.__setattr__(
                self,
                "scout_distance_inches",
                _validate_positive_number(
                    "PreBattleProposalRequest scout_distance_inches",
                    self.scout_distance_inches,
                ),
            )
        context = {} if self.context is None else self.context
        json_context = validate_json_value(context)
        if not isinstance(json_context, dict):
            raise GameLifecycleError("PreBattleProposalRequest context must be a JSON object.")
        object.__setattr__(self, "context", json_context)

    def to_decision_request(self) -> DecisionRequest:
        return DecisionRequest(
            request_id=self.request_id,
            decision_type=self.decision_type,
            actor_id=self.actor_id,
            payload={"proposal_request": validate_json_value(self.to_payload())},
            options=(parameterized_decision_option(),),
        )

    def to_payload(self) -> PreBattleProposalRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "actor_id": self.actor_id,
            "game_id": self.game_id,
            "setup_step": self.setup_step.value,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "model_instance_ids": list(self.model_instance_ids),
            "proposal_kind": self.proposal_kind,
            "action_kind": self.action_kind.value,
            "source_rule_id": self.source_rule_id,
            "placement_kind": None if self.placement_kind is None else self.placement_kind.value,
            "scout_distance_inches": self.scout_distance_inches,
            "deployment_zone_ids": [zone.deployment_zone_id for zone in self.deployment_zones],
            "legal_deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "mission_setup": self.mission_setup.to_payload(),
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "context": dict(self.context or {}),
        }

    @classmethod
    def from_decision_request_payload(cls, payload: object) -> Self:
        json_payload = validate_json_value(payload)
        if not isinstance(json_payload, dict):
            raise GameLifecycleError("Pre-battle DecisionRequest payload must be an object.")
        request_payload = json_payload.get("proposal_request")
        if not isinstance(request_payload, dict):
            raise GameLifecycleError("Pre-battle DecisionRequest payload missing request.")
        typed_payload = cast(PreBattleProposalRequestPayload, request_payload)
        return cls.from_payload(typed_payload)

    @classmethod
    def from_payload(cls, payload: PreBattleProposalRequestPayload) -> Self:
        raw_placement_kind = payload["placement_kind"]
        return cls(
            request_id=payload["request_id"],
            decision_type=payload["decision_type"],
            actor_id=payload["actor_id"],
            game_id=payload["game_id"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            component_unit_instance_ids=tuple(payload["component_unit_instance_ids"]),
            model_instance_ids=tuple(payload["model_instance_ids"]),
            proposal_kind=payload["proposal_kind"],
            action_kind=_action_kind_from_token(payload["action_kind"]),
            source_rule_id=payload["source_rule_id"],
            deployment_zones=tuple(
                DeploymentZone.from_payload(zone) for zone in payload["legal_deployment_zones"]
            ),
            mission_setup=MissionSetup.from_payload(payload["mission_setup"]),
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            placement_kind=(
                None
                if raw_placement_kind is None
                else battlefield_placement_kind_from_token(raw_placement_kind)
            ),
            scout_distance_inches=payload["scout_distance_inches"],
            context=payload["context"],
        )


@dataclass(frozen=True, slots=True)
class PreBattlePlacementProposal:
    proposal_request_id: str
    proposal_kind: str
    game_id: str
    ruleset_descriptor_hash: str
    setup_step: SetupStep
    player_id: str
    unit_instance_id: str
    action_kind: PreBattleActionKind
    source_rule_id: str
    placement_kind: BattlefieldPlacementKind
    model_placements: tuple[ModelPlacement, ...]
    context: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "PreBattlePlacementProposal proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_prebattle_proposal_kind(self.proposal_kind),
        )
        if self.proposal_kind not in {REDEPLOY_PROPOSAL_KIND, SCOUT_RESERVE_SETUP_PROPOSAL_KIND}:
            raise GameLifecycleError("PreBattlePlacementProposal requires a placement proposal.")
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PreBattlePlacementProposal game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "PreBattlePlacementProposal ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(self, "setup_step", _setup_step_from_token(self.setup_step))
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PreBattlePlacementProposal player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "PreBattlePlacementProposal unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(self, "action_kind", _action_kind_from_token(self.action_kind))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PreBattlePlacementProposal source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        object.__setattr__(
            self,
            "model_placements",
            _validate_model_placement_tuple(
                "PreBattlePlacementProposal model_placements",
                self.model_placements,
            ),
        )
        context = {} if self.context is None else self.context
        json_context = validate_json_value(context)
        if not isinstance(json_context, dict):
            raise GameLifecycleError("PreBattlePlacementProposal context must be a JSON object.")
        object.__setattr__(self, "context", json_context)

    def request_drift_violations(
        self,
        request: PreBattleProposalRequest,
    ) -> tuple[PreBattleViolation, ...]:
        violations = _common_request_drift_violations(self, request)
        if self.placement_kind is not request.placement_kind:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.PLACEMENT_KIND_DRIFT,
                    message="Pre-battle proposal placement kind does not match request.",
                    field="placement_kind",
                )
            )
        return tuple(violations)

    def grouped_unit_placements(self) -> tuple[UnitPlacement, ...]:
        by_unit: dict[str, list[ModelPlacement]] = {}
        for model_placement in self.model_placements:
            by_unit.setdefault(model_placement.unit_instance_id, []).append(model_placement)
        return tuple(
            UnitPlacement(
                army_id=placements[0].army_id,
                player_id=placements[0].player_id,
                unit_instance_id=unit_id,
                model_placements=tuple(placements),
            )
            for unit_id, placements in sorted(by_unit.items())
        )

    def to_payload(self) -> PreBattlePlacementProposalPayload:
        payload: PreBattlePlacementProposalPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "game_id": self.game_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "setup_step": self.setup_step.value,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "action_kind": self.action_kind.value,
            "source_rule_id": self.source_rule_id,
            "placement_kind": self.placement_kind.value,
            "model_placements": [placement.to_payload() for placement in self.model_placements],
        }
        if self.context:
            payload["context"] = dict(self.context)
        return payload

    @classmethod
    def from_payload(cls, payload: PreBattlePlacementProposalPayload) -> Self:
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=payload["proposal_kind"],
            game_id=payload["game_id"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            action_kind=_action_kind_from_token(payload["action_kind"]),
            source_rule_id=payload["source_rule_id"],
            placement_kind=battlefield_placement_kind_from_token(payload["placement_kind"]),
            model_placements=tuple(
                ModelPlacement.from_payload(placement) for placement in payload["model_placements"]
            ),
            context=payload.get("context"),
        )


@dataclass(frozen=True, slots=True)
class ScoutMoveProposal:
    proposal_request_id: str
    proposal_kind: str
    game_id: str
    ruleset_descriptor_hash: str
    setup_step: SetupStep
    player_id: str
    unit_instance_id: str
    action_kind: PreBattleActionKind
    source_rule_id: str
    scout_distance_inches: float
    witness: PathWitness
    context: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ScoutMoveProposal proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_prebattle_proposal_kind(self.proposal_kind),
        )
        if self.proposal_kind != SCOUT_MOVE_PROPOSAL_KIND:
            raise GameLifecycleError("ScoutMoveProposal requires scout_move proposal kind.")
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("ScoutMoveProposal game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "ScoutMoveProposal ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(self, "setup_step", _setup_step_from_token(self.setup_step))
        if self.setup_step is not SetupStep.RESOLVE_PREBATTLE_ACTIONS:
            raise GameLifecycleError("ScoutMoveProposal requires RESOLVE_PREBATTLE_ACTIONS.")
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ScoutMoveProposal player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ScoutMoveProposal unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(self, "action_kind", _action_kind_from_token(self.action_kind))
        if self.action_kind not in {
            PreBattleActionKind.SCOUT_MOVE,
            PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
        }:
            raise GameLifecycleError("ScoutMoveProposal requires a Scout Move action kind.")
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("ScoutMoveProposal source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "scout_distance_inches",
            _validate_positive_number(
                "ScoutMoveProposal scout_distance_inches",
                self.scout_distance_inches,
            ),
        )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("ScoutMoveProposal witness must be a PathWitness.")
        context = {} if self.context is None else self.context
        json_context = validate_json_value(context)
        if not isinstance(json_context, dict):
            raise GameLifecycleError("ScoutMoveProposal context must be a JSON object.")
        object.__setattr__(self, "context", json_context)

    def request_drift_violations(
        self,
        request: PreBattleProposalRequest,
    ) -> tuple[PreBattleViolation, ...]:
        violations = _common_request_drift_violations(self, request)
        if request.scout_distance_inches != self.scout_distance_inches:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.SOURCE_RULE_DRIFT,
                    message="Scout Move distance does not match the pending request.",
                    field="scout_distance_inches",
                )
            )
        return tuple(violations)

    def to_payload(self) -> ScoutMoveProposalPayload:
        payload: ScoutMoveProposalPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "game_id": self.game_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "setup_step": self.setup_step.value,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "action_kind": self.action_kind.value,
            "source_rule_id": self.source_rule_id,
            "scout_distance_inches": self.scout_distance_inches,
            "witness": self.witness.to_payload(),
        }
        if self.context:
            payload["context"] = dict(self.context)
        return payload

    @classmethod
    def from_payload(cls, payload: ScoutMoveProposalPayload) -> Self:
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=payload["proposal_kind"],
            game_id=payload["game_id"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            action_kind=_action_kind_from_token(payload["action_kind"]),
            source_rule_id=payload["source_rule_id"],
            scout_distance_inches=payload["scout_distance_inches"],
            witness=PathWitness.from_payload(payload["witness"]),
            context=payload.get("context"),
        )


@dataclass(frozen=True, slots=True)
class PreBattleViolation:
    violation_code: PreBattleViolationCode
    message: str
    field: str | None = None
    model_instance_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            prebattle_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_non_empty_string("PreBattleViolation message", self.message),
        )
        object.__setattr__(
            self,
            "field",
            _validate_optional_identifier("PreBattleViolation field", self.field),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "PreBattleViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier("PreBattleViolation blocker_id", self.blocker_id),
        )

    def to_payload(self) -> PreBattleViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "field": self.field,
            "model_instance_id": self.model_instance_id,
            "blocker_id": self.blocker_id,
        }


@dataclass(frozen=True, slots=True)
class PreBattleResolution:
    proposal: PreBattlePlacementProposal | ScoutMoveProposal
    violations: tuple[PreBattleViolation, ...]
    coherency_result: UnitCoherencyResult | None = None
    transition_batch: BattlefieldTransitionBatch | None = None
    removal_batch: BattlefieldTransitionBatch | None = None
    placement_batch: BattlefieldTransitionBatch | None = None

    def __post_init__(self) -> None:
        if type(self.proposal) not in {PreBattlePlacementProposal, ScoutMoveProposal}:
            raise GameLifecycleError("PreBattleResolution proposal must be a pre-battle proposal.")
        object.__setattr__(
            self,
            "violations",
            _validate_prebattle_violation_tuple(
                "PreBattleResolution violations",
                self.violations,
            ),
        )
        if self.coherency_result is not None and type(self.coherency_result) is not (
            UnitCoherencyResult
        ):
            raise GameLifecycleError("PreBattleResolution coherency_result drift.")
        for batch in (self.transition_batch, self.removal_batch, self.placement_batch):
            if batch is not None and type(batch) is not BattlefieldTransitionBatch:
                raise GameLifecycleError("PreBattleResolution transition batch drift.")
        if self.violations and any(
            batch is not None
            for batch in (self.transition_batch, self.removal_batch, self.placement_batch)
        ):
            raise GameLifecycleError("Invalid pre-battle resolution cannot have transitions.")
        if not self.violations and not any(
            batch is not None
            for batch in (self.transition_batch, self.removal_batch, self.placement_batch)
        ):
            raise GameLifecycleError("Valid pre-battle resolution requires a transition batch.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> PreBattleResolutionPayload:
        return {
            "proposal": cast(dict[str, JsonValue], self.proposal.to_payload()),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "coherency_result": None
            if self.coherency_result is None
            else cast(dict[str, JsonValue], self.coherency_result.to_payload()),
            "transition_batch": None
            if self.transition_batch is None
            else cast(dict[str, JsonValue], self.transition_batch.to_payload()),
            "removal_batch": None
            if self.removal_batch is None
            else cast(dict[str, JsonValue], self.removal_batch.to_payload()),
            "placement_batch": None
            if self.placement_batch is None
            else cast(dict[str, JsonValue], self.placement_batch.to_payload()),
        }


def prebattle_violation_code_from_token(token: object) -> PreBattleViolationCode:
    if type(token) is PreBattleViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("PreBattleViolationCode token must be a string.")
    try:
        return PreBattleViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported PreBattleViolationCode token: {token}.") from exc


def scout_distance_inches_for_model_ids(
    *,
    model_instance_ids: tuple[str, ...],
    ability_instances: tuple[ScoutAbilityInstance, ...],
) -> float:
    model_ids = _validate_identifier_tuple("model_instance_ids", model_instance_ids)
    if not model_ids:
        raise GameLifecycleError("Scouts distance selection requires model IDs.")
    by_model: dict[str, list[ScoutAbilityInstance]] = {model_id: [] for model_id in model_ids}
    for instance in _validate_scout_ability_instances(ability_instances):
        if instance.model_instance_id not in by_model:
            raise GameLifecycleError("ScoutAbilityInstance model is outside the selected unit.")
        by_model[instance.model_instance_id].append(instance)
    missing_model_ids = tuple(model_id for model_id, instances in by_model.items() if not instances)
    if missing_model_ids:
        raise GameLifecycleError("Every model must have a Scouts ability instance.")
    return min(
        max(instance.distance_inches for instance in instances) for instances in by_model.values()
    )


def redeploy_timing_state_for_state(state: GameState) -> PreBattleTimingWindowState:
    return _timing_state_for_step(state=state, setup_step=SetupStep.REDEPLOY_UNITS)


def prebattle_timing_state_for_state(
    state: GameState,
    *,
    army_catalog: ArmyCatalog,
) -> PreBattleTimingWindowState:
    return _timing_state_for_step(
        state=state,
        setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
        army_catalog=army_catalog,
    )


def prebattle_sequencing_request_for_timing_state(
    *,
    state: GameState,
    decisions: DecisionController,
    timing_state: PreBattleTimingWindowState,
) -> DecisionRequest | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Pre-battle sequencing requires a DecisionController.")
    participants = _prebattle_sequencing_participants(timing_state)
    if len(participants) < 2:
        return None
    conflict_id = _prebattle_sequencing_conflict_id(timing_state.setup_step)
    if (
        _resolved_prebattle_sequencing_order(
            decisions=decisions,
            conflict_id=conflict_id,
        )
        is not None
    ):
        return None
    return create_sequencing_decision_request(
        request_id=state.next_decision_request_id(),
        context=SequencingConflictContext(
            conflict_id=conflict_id,
            game_id=state.game_id,
            timing_window=_prebattle_timing_window(state=state, setup_step=timing_state.setup_step),
            player_ids=tuple(participant.player_id for participant in participants),
            active_player_id=None,
        ),
        participants=participants,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )


def prebattle_next_player_id_for_timing_state(
    *,
    decisions: DecisionController,
    timing_state: PreBattleTimingWindowState,
) -> str | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Pre-battle sequencing requires a DecisionController.")
    resolved_order = _resolved_prebattle_sequencing_order(
        decisions=decisions,
        conflict_id=_prebattle_sequencing_conflict_id(timing_state.setup_step),
    )
    if resolved_order is None:
        return timing_state.next_player_id
    participants_by_id = {
        participant.participant_id: participant
        for participant in _prebattle_sequencing_participants(timing_state)
    }
    if not set(participants_by_id).issubset(set(resolved_order)):
        raise GameLifecycleError("Pre-battle sequencing order drift.")
    for participant_id in resolved_order:
        participant = participants_by_id.get(participant_id)
        if participant is None:
            continue
        if participant.player_id in timing_state.completed_player_ids:
            continue
        if timing_state.available_action_count_by_player[participant.player_id] > 0:
            return participant.player_id
    return None


def redeploy_unit_selection_request(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> DecisionRequest:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Redeploy selection requires RulesetDescriptor.")
    requested_player_id = _validate_identifier("player_id", player_id)
    mission_setup = _require_mission_setup(state)
    candidates = redeploy_unit_views_for_player(state=state, player_id=requested_player_id)
    options = list(
        catalog_redeploy_selection_options(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            mission_setup=mission_setup,
            player_id=requested_player_id,
            candidates=candidates,
            core_source_rule_id=CORE_REDEPLOY_SOURCE_RULE_ID,
            proposal_kind=REDEPLOY_PROPOSAL_KIND,
            payload_factory=_prebattle_selection_payload,
        )
    )
    options.append(
        DecisionOption(
            option_id="complete_redeploys",
            label="Complete Redeploys",
            payload={
                "submission_kind": SELECT_REDEPLOY_UNIT_DECISION_TYPE,
                "game_id": state.game_id,
                "setup_step": SetupStep.REDEPLOY_UNITS.value,
                "player_id": requested_player_id,
                "action_kind": PreBattleActionKind.COMPLETE_REDEPLOYS.value,
                "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
            },
        )
    )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_REDEPLOY_UNIT_DECISION_TYPE,
        actor_id=requested_player_id,
        payload={
            "game_id": state.game_id,
            "setup_step": SetupStep.REDEPLOY_UNITS.value,
            "player_id": requested_player_id,
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
        options=tuple(options),
    )


def prebattle_action_selection_request(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> DecisionRequest:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Pre-battle action selection requires RulesetDescriptor.")
    requested_player_id = _validate_identifier("player_id", player_id)
    mission_setup = _require_mission_setup(state)
    options: list[DecisionOption] = []
    for candidate in scout_reserve_setup_candidates_for_player(
        state=state,
        army_catalog=army_catalog,
        player_id=requested_player_id,
    ):
        options.append(
            DecisionOption(
                option_id=f"scout_reserve_setup:{candidate.unit_instance_id}",
                label=f"Scout Reserve Setup {candidate.unit_instance_id}",
                payload=_prebattle_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=candidate,
                    setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
                    action_kind=PreBattleActionKind.SCOUT_RESERVE_SETUP,
                    source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
                    proposal_kind=SCOUT_RESERVE_SETUP_PROPOSAL_KIND,
                ),
            )
        )
    for candidate in scout_move_candidates_for_player(
        state=state,
        army_catalog=army_catalog,
        player_id=requested_player_id,
    ):
        options.append(
            DecisionOption(
                option_id=f"scout_move:{candidate.unit_instance_id}",
                label=f"Scout Move {candidate.unit_instance_id}",
                payload=_prebattle_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=candidate,
                    setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
                    action_kind=PreBattleActionKind.SCOUT_MOVE,
                    source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
                    proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
                ),
            )
        )
    for candidate in dedicated_transport_scout_move_candidates_for_player(
        state=state,
        army_catalog=army_catalog,
        player_id=requested_player_id,
    ):
        options.append(
            DecisionOption(
                option_id=f"dedicated_transport_scout_move:{candidate.unit_instance_id}",
                label=f"Dedicated Transport Scout Move {candidate.unit_instance_id}",
                payload=_prebattle_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    mission_setup=mission_setup,
                    view=candidate,
                    setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
                    action_kind=PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
                    source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
                    proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
                ),
            )
        )
    options.append(
        DecisionOption(
            option_id="complete_prebattle_actions",
            label="Complete Pre-battle Actions",
            payload={
                "submission_kind": SELECT_PREBATTLE_ACTION_DECISION_TYPE,
                "game_id": state.game_id,
                "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                "player_id": requested_player_id,
                "action_kind": PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS.value,
                "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
            },
        )
    )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        actor_id=requested_player_id,
        payload={
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": requested_player_id,
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
        options=tuple(options),
    )


def redeploy_placement_request_from_selection(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    selection_request: DecisionRequest,
    result: DecisionResult,
) -> PreBattleProposalRequest:
    return _proposal_request_from_selection(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        selection_request=selection_request,
        result=result,
        setup_step=SetupStep.REDEPLOY_UNITS,
        decision_type=SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        placement_kind=BattlefieldPlacementKind.REDEPLOY,
    )


def prebattle_proposal_request_from_selection(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    selection_request: DecisionRequest,
    result: DecisionResult,
) -> PreBattleProposalRequest:
    if not isinstance(result.payload, dict):
        raise GameLifecycleError("Pre-battle action selection payload must be an object.")
    action_kind = _action_kind_from_token(_payload_string(result.payload, "action_kind"))
    if action_kind in {
        PreBattleActionKind.SCOUT_MOVE,
        PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
    }:
        decision_type = SUBMIT_SCOUT_MOVE_DECISION_TYPE
        placement_kind = None
    elif action_kind is PreBattleActionKind.SCOUT_RESERVE_SETUP:
        decision_type = SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE
        placement_kind = BattlefieldPlacementKind.STRATEGIC_RESERVES
    else:
        raise GameLifecycleError("Pre-battle action selection does not require a proposal.")
    return _proposal_request_from_selection(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        selection_request=selection_request,
        result=result,
        setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
        decision_type=decision_type,
        placement_kind=placement_kind,
    )


def is_prebattle_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Pre-battle request check requires DecisionRequest.")
    return request.decision_type in {
        SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        SUBMIT_SCOUT_MOVE_DECISION_TYPE,
        SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
    }


def invalid_prebattle_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
    if not is_prebattle_proposal_request(request):
        return None
    result.validate_for_request(request)
    try:
        request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
        if request.decision_type == SUBMIT_SCOUT_MOVE_DECISION_TYPE:
            proposal: PreBattlePlacementProposal | ScoutMoveProposal = (
                ScoutMoveProposal.from_payload(cast(ScoutMoveProposalPayload, result.payload))
            )
        else:
            proposal = PreBattlePlacementProposal.from_payload(
                cast(PreBattlePlacementProposalPayload, result.payload)
            )
    except (
        KeyError,
        TypeError,
        DeploymentZoneError,
        GameLifecycleError,
        GeometryError,
        MissionSetupError,
        PlacementError,
    ) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Pre-battle proposal submission is malformed.",
            payload={
                "invalid_reason": "malformed_prebattle_proposal",
                "detail": str(exc),
                "request_id": request.request_id,
            },
        )
    drift_violations = proposal.request_drift_violations(request_context)
    if drift_violations:
        return _invalid_prebattle_status(
            state=state,
            request_id=request.request_id,
            invalid_reason="prebattle_request_drift",
            violations=drift_violations,
            resolution=None,
        )
    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        request=request_context,
        proposal=proposal,
    )
    if not resolution.is_valid:
        return _invalid_prebattle_status(
            state=state,
            request_id=request.request_id,
            invalid_reason="prebattle_proposal_invalid",
            violations=resolution.violations,
            resolution=resolution,
        )
    return None


def apply_redeploy_placement(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> PreBattleResolution:
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    proposal = PreBattlePlacementProposal.from_payload(
        cast(PreBattlePlacementProposalPayload, result.payload)
    )
    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        request=request_context,
        proposal=proposal,
        source_event_id=result.result_id,
    )
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid redeploy placement cannot mutate state.")
    if resolution.removal_batch is None or resolution.placement_batch is None:
        raise GameLifecycleError("Redeploy placement requires removal and placement batches.")
    battlefield = _require_battlefield_state(state)
    for unit_placement in _current_grouped_unit_placements(state, request_context.unit_instance_id):
        battlefield = battlefield.without_unit_placement(unit_placement.unit_instance_id)
    for unit_placement in proposal.grouped_unit_placements():
        battlefield = battlefield.with_added_unit_placement(unit_placement)
    state.replace_battlefield_state(battlefield)
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=PreBattleActionKind.REDEPLOY,
        unit_instance_id=request_context.unit_instance_id,
        source_rule_id=request_context.source_rule_id,
        payload=validate_json_value(resolution.to_payload()),
    )
    decisions.event_log.append(
        "prebattle_redeploy_completed",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.REDEPLOY_UNITS.value,
            "player_id": request_context.player_id,
            "unit_instance_id": request_context.unit_instance_id,
            "resolution": resolution.to_payload(),
        },
    )
    return resolution


def apply_scout_reserve_setup(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> PreBattleResolution:
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    proposal = PreBattlePlacementProposal.from_payload(
        cast(PreBattlePlacementProposalPayload, result.payload)
    )
    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        request=request_context,
        proposal=proposal,
        source_event_id=result.result_id,
    )
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid Scout reserve setup cannot mutate state.")
    if resolution.transition_batch is None:
        raise GameLifecycleError("Scout reserve setup requires a transition batch.")
    battlefield = _require_battlefield_state(state)
    for unit_placement in proposal.grouped_unit_placements():
        battlefield = battlefield.with_added_unit_placement(unit_placement)
    state.replace_battlefield_state(battlefield)
    reserve_state = _require_reserve_state(state, request_context.unit_instance_id)
    state.replace_reserve_state(
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=1,
            arrived_phase=SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
            restriction_battle_round=None,
        )
    )
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=PreBattleActionKind.SCOUT_RESERVE_SETUP,
        unit_instance_id=request_context.unit_instance_id,
        source_rule_id=request_context.source_rule_id,
        payload=validate_json_value(resolution.to_payload()),
    )
    decisions.event_log.append(
        "prebattle_scout_reserve_setup_completed",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": request_context.player_id,
            "unit_instance_id": request_context.unit_instance_id,
            "resolution": resolution.to_payload(),
        },
    )
    return resolution


def apply_scout_move(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> PreBattleResolution:
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    proposal = ScoutMoveProposal.from_payload(cast(ScoutMoveProposalPayload, result.payload))
    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        request=request_context,
        proposal=proposal,
        source_event_id=result.result_id,
    )
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid Scout Move cannot mutate state.")
    if resolution.transition_batch is None:
        raise GameLifecycleError("Scout Move requires a transition batch.")
    battlefield = _require_battlefield_state(state)
    current = battlefield.unit_placement_by_id(request_context.unit_instance_id)
    moved_placements = tuple(
        placement.with_pose(proposal.witness.final_pose_for_model(placement.model_instance_id))
        for placement in current.model_placements
    )
    state.replace_battlefield_state(
        battlefield.with_unit_placement(current.with_model_placements(moved_placements))
    )
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=proposal.action_kind,
        unit_instance_id=request_context.unit_instance_id,
        source_rule_id=request_context.source_rule_id,
        payload=validate_json_value(resolution.to_payload()),
    )
    decisions.event_log.append(
        "prebattle_scout_move_completed",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": request_context.player_id,
            "unit_instance_id": request_context.unit_instance_id,
            "action_kind": proposal.action_kind.value,
            "resolution": resolution.to_payload(),
        },
    )
    return resolution


def resolve_prebattle_proposal(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    request: PreBattleProposalRequest,
    proposal: PreBattlePlacementProposal | ScoutMoveProposal,
    source_event_id: str | None = None,
) -> PreBattleResolution:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Pre-battle proposal requires RulesetDescriptor.")
    if request.proposal_kind == SCOUT_MOVE_PROPOSAL_KIND:
        if type(proposal) is not ScoutMoveProposal:
            raise GameLifecycleError("Scout Move resolution requires ScoutMoveProposal.")
        return _resolve_scout_move(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            request=request,
            proposal=proposal,
            source_event_id=source_event_id,
        )
    if type(proposal) is not PreBattlePlacementProposal:
        raise GameLifecycleError("Pre-battle placement resolution requires placement proposal.")
    return _resolve_prebattle_placement(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        request=request,
        proposal=proposal,
        source_event_id=source_event_id,
    )


def apply_redeploy_completion(
    *,
    state: GameState,
    result: DecisionResult,
    request: DecisionRequest,
    decisions: DecisionController,
) -> None:
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=PreBattleActionKind.COMPLETE_REDEPLOYS,
        unit_instance_id=None,
        source_rule_id=CORE_REDEPLOY_SOURCE_RULE_ID,
        payload={
            "game_id": state.game_id,
            "setup_step": SetupStep.REDEPLOY_UNITS.value,
            "player_id": result.actor_id,
        },
    )
    decisions.event_log.append(
        "prebattle_redeploys_completed",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.REDEPLOY_UNITS.value,
            "player_id": result.actor_id,
        },
    )


def apply_prebattle_completion(
    *,
    state: GameState,
    result: DecisionResult,
    request: DecisionRequest,
    decisions: DecisionController,
) -> None:
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS,
        unit_instance_id=None,
        source_rule_id=CORE_SCOUTS_SOURCE_RULE_ID,
        payload={
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": result.actor_id,
        },
    )
    decisions.event_log.append(
        "prebattle_actions_completed",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": result.actor_id,
        },
    )


def redeploy_unit_views_for_player(
    *,
    state: GameState,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if _completed_step_for_player(
        state=state,
        player_id=requested_player_id,
        setup_step=SetupStep.REDEPLOY_UNITS,
        complete_kind=PreBattleActionKind.COMPLETE_REDEPLOYS,
    ):
        return ()
    battlefield = _require_battlefield_state(state)
    available: list[RulesUnitView] = []
    for view in _rules_unit_views_for_player(state=state, player_id=requested_player_id):
        permission = catalog_redeploy_permission_for_view(
            state=state,
            player_id=requested_player_id,
            view=view,
        )
        if permission is None and not _rules_unit_all_components_have_keyword(view, "REDEPLOY"):
            continue
        if _unit_action_record_exists(
            state=state,
            setup_step=SetupStep.REDEPLOY_UNITS,
            unit_instance_id=view.unit_instance_id,
        ):
            continue
        if _rules_unit_is_placed(battlefield=battlefield, view=view):
            available.append(view)
    return tuple(sorted(available, key=lambda view: view.unit_instance_id))


def scout_reserve_setup_candidates_for_player(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if _completed_step_for_player(
        state=state,
        player_id=requested_player_id,
        setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
        complete_kind=PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS,
    ):
        return ()
    candidates: list[RulesUnitView] = []
    for reserve_state in state.unarrived_reserve_states_for_player(requested_player_id):
        if reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES:
            continue
        view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions),
            unit_instance_id=reserve_state.unit_instance_id,
        )
        if not _rules_unit_all_components_have_scouts(view=view, army_catalog=army_catalog):
            continue
        if _unit_action_record_exists(
            state=state,
            setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
            unit_instance_id=view.unit_instance_id,
        ):
            continue
        candidates.append(view)
    return tuple(sorted(candidates, key=lambda view: view.unit_instance_id))


def scout_move_candidates_for_player(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if _completed_step_for_player(
        state=state,
        player_id=requested_player_id,
        setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
        complete_kind=PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS,
    ):
        return ()
    battlefield = _require_battlefield_state(state)
    mission_setup = _require_mission_setup(state)
    zones = _deployment_zones_for_player(mission_setup, requested_player_id)
    unavailable_ids = set(state.unarrived_reserve_model_ids()) | set(state.embarked_model_ids())
    candidates: list[RulesUnitView] = []
    for view in _rules_unit_views_for_player(state=state, player_id=requested_player_id):
        if not _rules_unit_all_components_have_scouts(view=view, army_catalog=army_catalog):
            continue
        if _unit_action_record_exists(
            state=state,
            setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
            unit_instance_id=view.unit_instance_id,
        ):
            continue
        if any(model.model_instance_id in unavailable_ids for model in view.alive_models()):
            continue
        if not _rules_unit_is_placed(battlefield=battlefield, view=view):
            continue
        if _rules_unit_wholly_within_zones(
            state=state,
            battlefield=battlefield,
            view=view,
            zones=zones,
        ):
            candidates.append(view)
    return tuple(sorted(candidates, key=lambda view: view.unit_instance_id))


def dedicated_transport_scout_move_candidates_for_player(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    if _completed_step_for_player(
        state=state,
        player_id=requested_player_id,
        setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
        complete_kind=PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS,
    ):
        return ()
    battlefield = _require_battlefield_state(state)
    mission_setup = _require_mission_setup(state)
    zones = _deployment_zones_for_player(mission_setup, requested_player_id)
    candidates: list[RulesUnitView] = []
    for view in _rules_unit_views_for_player(state=state, player_id=requested_player_id):
        if not _rules_unit_any_component_has_keyword(view, "DEDICATED_TRANSPORT"):
            continue
        cargo_state = state.transport_cargo_state_for_transport(view.unit_instance_id)
        if cargo_state is None or not cargo_state.embarked_unit_instance_ids:
            continue
        if not _transport_cargo_all_scouts(
            state=state,
            army_catalog=army_catalog,
            cargo_state=cargo_state,
        ):
            continue
        if _unit_action_record_exists(
            state=state,
            setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
            unit_instance_id=view.unit_instance_id,
        ):
            continue
        if not _rules_unit_is_placed(battlefield=battlefield, view=view):
            continue
        if _rules_unit_wholly_within_zones(
            state=state,
            battlefield=battlefield,
            view=view,
            zones=zones,
        ):
            candidates.append(view)
    return tuple(sorted(candidates, key=lambda view: view.unit_instance_id))


def _timing_state_for_step(
    *,
    state: GameState,
    setup_step: SetupStep,
    army_catalog: ArmyCatalog | None = None,
) -> PreBattleTimingWindowState:
    counts = {
        player_id: len(
            _available_action_views_for_step(
                state=state,
                setup_step=setup_step,
                player_id=player_id,
                army_catalog=army_catalog,
            )
        )
        for player_id in state.player_ids
    }
    completed = tuple(
        player_id
        for player_id in state.player_ids
        if _completed_kind_for_step_player(state=state, setup_step=setup_step, player_id=player_id)
        is not None
    )
    next_player_id = None
    for player_id in state.turn_order:
        if player_id in completed:
            continue
        if counts[player_id] > 0:
            next_player_id = player_id
            break
    return PreBattleTimingWindowState(
        setup_step=setup_step,
        next_player_id=next_player_id,
        available_action_count_by_player=counts,
        completed_player_ids=completed,
    )


def _prebattle_sequencing_participants(
    timing_state: PreBattleTimingWindowState,
) -> tuple[SequencingParticipant, ...]:
    source_rule_id = (
        CORE_REDEPLOY_SOURCE_RULE_ID
        if timing_state.setup_step is SetupStep.REDEPLOY_UNITS
        else CORE_SCOUTS_SOURCE_RULE_ID
    )
    participants: list[SequencingParticipant] = []
    for player_id, action_count in timing_state.available_action_count_by_player.items():
        if player_id in timing_state.completed_player_ids:
            continue
        if action_count <= 0:
            continue
        participants.append(
            SequencingParticipant(
                participant_id=_prebattle_sequencing_participant_id(
                    setup_step=timing_state.setup_step,
                    player_id=player_id,
                ),
                player_id=player_id,
                source_rule_id=source_rule_id,
                payload={
                    "setup_step": timing_state.setup_step.value,
                    "available_action_count": action_count,
                },
            )
        )
    return tuple(participants)


def _prebattle_sequencing_participant_id(
    *,
    setup_step: SetupStep,
    player_id: str,
) -> str:
    return f"prebattle:{setup_step.value}:{_validate_identifier('player_id', player_id)}"


def _prebattle_sequencing_conflict_id(setup_step: SetupStep) -> str:
    resolved_step = _setup_step_from_token(setup_step)
    if resolved_step not in {SetupStep.REDEPLOY_UNITS, SetupStep.RESOLVE_PREBATTLE_ACTIONS}:
        raise GameLifecycleError("Pre-battle sequencing requires a pre-battle setup step.")
    return f"prebattle-sequencing:{resolved_step.value}"


def _prebattle_timing_window(*, state: GameState, setup_step: SetupStep) -> TimingWindow:
    resolved_step = _setup_step_from_token(setup_step)
    return TimingWindow(
        window_id=f"prebattle-window:{state.game_id}:{resolved_step.value}",
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"prebattle-window-descriptor:{resolved_step.value}",
            trigger_kind=TimingTriggerKind.BEFORE_BATTLE,
            source_rule_id="core_rules:prebattle",
            source_step=resolved_step.value,
            metadata={"setup_step": resolved_step.value},
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=None,
        phase=None,
        trigger_event_id=None,
    )


def _resolved_prebattle_sequencing_order(
    *,
    decisions: DecisionController,
    conflict_id: str,
) -> tuple[str, ...] | None:
    requested_conflict_id = _validate_identifier("conflict_id", conflict_id)
    for event in reversed(decisions.event_log.records):
        if event.event_type != PREBATTLE_SEQUENCING_EVENT_TYPE:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Sequencing event payload must be an object.")
        if event.payload.get("conflict_id") != requested_conflict_id:
            continue
        raw_order = event.payload.get("ordered_participant_ids")
        if not isinstance(raw_order, list):
            raise GameLifecycleError("Sequencing event ordered_participant_ids must be a list.")
        ordered: list[str] = []
        for participant_id in raw_order:
            ordered.append(_validate_identifier("ordered_participant_id", participant_id))
        return tuple(ordered)
    return None


def _available_action_views_for_step(
    *,
    state: GameState,
    setup_step: SetupStep,
    player_id: str,
    army_catalog: ArmyCatalog | None,
) -> tuple[RulesUnitView, ...]:
    if setup_step is SetupStep.REDEPLOY_UNITS:
        return redeploy_unit_views_for_player(state=state, player_id=player_id)
    if setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS:
        if type(army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("Pre-battle Scout actions require an ArmyCatalog.")
        return (
            *scout_reserve_setup_candidates_for_player(
                state=state,
                army_catalog=army_catalog,
                player_id=player_id,
            ),
            *scout_move_candidates_for_player(
                state=state,
                army_catalog=army_catalog,
                player_id=player_id,
            ),
            *dedicated_transport_scout_move_candidates_for_player(
                state=state,
                army_catalog=army_catalog,
                player_id=player_id,
            ),
        )
    raise GameLifecycleError("Unsupported pre-battle setup step.")


def _resolve_prebattle_placement(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    request: PreBattleProposalRequest,
    proposal: PreBattlePlacementProposal,
    source_event_id: str | None,
) -> PreBattleResolution:
    _validate_prebattle_state(state, request.setup_step)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=_require_battlefield_state(state),
    )
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=request.unit_instance_id,
    )
    placement_source_event_id = (
        request.source_decision_result_id
        if source_event_id is None
        else _validate_identifier("source_event_id", source_event_id)
    )
    violations: list[PreBattleViolation] = []
    _append_action_eligibility_violations(
        violations=violations,
        state=state,
        army_catalog=army_catalog,
        request=request,
        view=view,
    )
    coherency_result, models = _validate_placement_models(
        violations=violations,
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        request=request,
        proposal=proposal,
        view=view,
    )
    _append_setup_geometry_violations(
        violations=violations,
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        view=view,
        models=models,
        deployment_zones=request.deployment_zones,
    )
    if violations:
        return PreBattleResolution(
            proposal=proposal,
            violations=tuple(violations),
            coherency_result=coherency_result,
        )
    if request.proposal_kind == REDEPLOY_PROPOSAL_KIND:
        removal_batch = BattlefieldTransitionBatch(
            removals=tuple(
                ModelRemovalRecord(
                    model_instance_id=model_id,
                    removal_kind=BattlefieldRemovalKind.TEMPORARILY_REMOVED,
                    source_phase=None,
                    source_step=SetupStep.REDEPLOY_UNITS.value,
                    source_rule_id=request.source_rule_id,
                    source_event_id=placement_source_event_id,
                )
                for model_id in request.model_instance_ids
            )
        )
        placement_batch = BattlefieldTransitionBatch(
            placements=tuple(
                ModelPlacementRecord(
                    model_instance_id=placement.model_instance_id,
                    placement_kind=BattlefieldPlacementKind.REDEPLOY,
                    pose=placement.pose,
                    source_phase=None,
                    source_step=SetupStep.REDEPLOY_UNITS.value,
                    source_rule_id=request.source_rule_id,
                    source_event_id=placement_source_event_id,
                )
                for placement in proposal.model_placements
            )
        )
        return PreBattleResolution(
            proposal=proposal,
            violations=(),
            coherency_result=coherency_result,
            removal_batch=removal_batch,
            placement_batch=placement_batch,
        )
    transition_batch = BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                pose=placement.pose,
                source_phase=None,
                source_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                source_rule_id=request.source_rule_id,
                source_event_id=placement_source_event_id,
            )
            for placement in proposal.model_placements
        )
    )
    return PreBattleResolution(
        proposal=proposal,
        violations=(),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
    )


def _resolve_scout_move(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    request: PreBattleProposalRequest,
    proposal: ScoutMoveProposal,
    source_event_id: str | None,
) -> PreBattleResolution:
    _validate_prebattle_state(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=_require_battlefield_state(state),
    )
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=request.unit_instance_id,
    )
    current = _require_battlefield_state(state).unit_placement_by_id(request.unit_instance_id)
    violations: list[PreBattleViolation] = []
    _append_action_eligibility_violations(
        violations=violations,
        state=state,
        army_catalog=army_catalog,
        request=request,
        view=view,
    )
    if not _start_is_eligible_for_scout_move(state=state, view=view):
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION,
                message=(
                    "Scout Move requires the selected unit to start wholly in its deployment zone."
                ),
                field="unit_instance_id",
            )
        )
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in current.model_placements)
    )
    if tuple(sorted(proposal.witness.model_ids())) != expected_model_ids:
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.WITNESS_MODEL_SET_DRIFT,
                message="Scout Move witness must include every alive placed model in the unit.",
                field="witness",
            )
        )
    for placement in current.model_placements:
        if placement.model_instance_id not in proposal.witness.model_ids():
            continue
        poses = proposal.witness.poses_for_model(placement.model_instance_id)
        if poses[0] != placement.pose:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.WITNESS_START_DRIFT,
                    message="Scout Move witness must start at the current model pose.",
                    field="witness",
                    model_instance_id=placement.model_instance_id,
                )
            )
        if is_degenerate_endpoint_only_real_movement_path(poses):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.ENDPOINT_ONLY_PATH,
                    message="Scout Move witness must not repeat only endpoint poses.",
                    field="witness",
                    model_instance_id=placement.model_instance_id,
                )
            )
    if violations:
        return PreBattleResolution(
            proposal=proposal,
            violations=tuple(violations),
        )
    moved_placements = tuple(
        placement.with_pose(proposal.witness.final_pose_for_model(placement.model_instance_id))
        for placement in current.model_placements
        if placement.model_instance_id in proposal.witness.model_ids()
    )
    attempted_placement = current.with_model_placements(moved_placements)
    if not violations:
        _append_scout_path_violations(
            violations=violations,
            state=state,
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            current=current,
            attempted=attempted_placement,
            witness=proposal.witness,
            scout_distance_inches=proposal.scout_distance_inches,
        )
    coherency_result = unit_placement_coherency_result(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=attempted_placement,
    )
    if not coherency_result.is_coherent:
        for model_id in coherency_result.offending_model_instance_ids:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_COHERENCY_BROKEN,
                    message="Scout Move endpoint breaks unit coherency.",
                    field="witness",
                    model_instance_id=model_id,
                )
            )
    _append_scout_enemy_distance_violations(
        violations=violations,
        state=state,
        scenario=scenario,
        attempted=attempted_placement,
    )
    if violations:
        return PreBattleResolution(
            proposal=proposal,
            violations=tuple(violations),
            coherency_result=coherency_result,
        )
    event_id = (
        request.source_decision_result_id
        if source_event_id is None
        else _validate_identifier("source_event_id", source_event_id)
    )
    transition_batch = BattlefieldTransitionBatch(
        displacements=tuple(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.SCOUT_MOVE,
                start_pose=placement.pose,
                end_pose=proposal.witness.final_pose_for_model(placement.model_instance_id),
                path_witness=PathWitness.for_paths(
                    (
                        (
                            placement.model_instance_id,
                            proposal.witness.poses_for_model(placement.model_instance_id),
                        ),
                    )
                ),
                source_phase=None,
                source_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                source_rule_id=request.source_rule_id,
                source_event_id=event_id,
            )
            for placement in current.model_placements
            if placement.pose != proposal.witness.final_pose_for_model(placement.model_instance_id)
        )
    )
    return PreBattleResolution(
        proposal=proposal,
        violations=(),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
    )


def _append_action_eligibility_violations(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    army_catalog: ArmyCatalog,
    request: PreBattleProposalRequest,
    view: RulesUnitView,
) -> None:
    if view.owner_player_id != request.player_id:
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.PLAYER_DRIFT,
                message="Pre-battle selected unit belongs to another player.",
                field="unit_instance_id",
                blocker_id=view.owner_player_id,
            )
        )
    if _unit_action_record_exists(
        state=state,
        setup_step=request.setup_step,
        unit_instance_id=request.unit_instance_id,
    ):
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.UNIT_NOT_ELIGIBLE,
                message="Pre-battle unit has already resolved an action in this step.",
                field="unit_instance_id",
            )
        )
    if request.action_kind in {
        PreBattleActionKind.REDEPLOY,
        PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES,
    }:
        permission = catalog_redeploy_permission_for_view(
            state=state,
            player_id=request.player_id,
            view=view,
        )
        source_is_catalog_permission = (
            permission is not None and permission.source_rule_id == request.source_rule_id
        )
        if not source_is_catalog_permission and not _rules_unit_all_components_have_keyword(
            view, "REDEPLOY"
        ):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_NOT_ELIGIBLE,
                    message="Redeploy requires a current source-backed permission.",
                    field="unit_instance_id",
                )
            )
        if not _rules_unit_is_placed(battlefield=_require_battlefield_state(state), view=view):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_NOT_PLACED,
                    message="Redeploy requires the selected unit to be on the battlefield.",
                    field="unit_instance_id",
                )
            )
    elif request.action_kind is PreBattleActionKind.SCOUT_RESERVE_SETUP:
        reserve_state = state.reserve_state_for_unit(request.unit_instance_id)
        if reserve_state is None or reserve_state.status is not ReserveStatus.IN_RESERVES:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.RESERVE_STATE_NOT_UNARRIVED,
                    message="Scout reserve setup requires an unarrived ReserveState.",
                    field="unit_instance_id",
                )
            )
        elif reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.RESERVE_KIND_MISMATCH,
                    message="Scout reserve setup requires Strategic Reserves.",
                    field="unit_instance_id",
                )
            )
        if not _rules_unit_all_components_have_scouts(view=view, army_catalog=army_catalog):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_NOT_ELIGIBLE,
                    message="Scout reserve setup requires every component unit to have Scouts.",
                    field="unit_instance_id",
                )
            )
    elif request.action_kind is PreBattleActionKind.SCOUT_MOVE:
        if not _rules_unit_all_components_have_scouts(view=view, army_catalog=army_catalog):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_NOT_ELIGIBLE,
                    message="Scout Move requires every component unit to have Scouts.",
                    field="unit_instance_id",
                )
            )
    elif request.action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE:
        if not _rules_unit_any_component_has_keyword(view, "DEDICATED_TRANSPORT"):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.DEDICATED_TRANSPORT_REQUIRED,
                    message="Dedicated Transport Scout Move requires a Dedicated Transport.",
                    field="unit_instance_id",
                )
            )
        cargo_state = state.transport_cargo_state_for_transport(request.unit_instance_id)
        if cargo_state is None or not _transport_cargo_all_scouts(
            state=state,
            army_catalog=army_catalog,
            cargo_state=cargo_state,
        ):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.TRANSPORT_CARGO_NOT_ALL_SCOUTS,
                    message=(
                        "Dedicated Transport Scout Move requires every embarked unit to have "
                        "Scouts."
                    ),
                    field="unit_instance_id",
                )
            )


def _validate_placement_models(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    request: PreBattleProposalRequest,
    proposal: PreBattlePlacementProposal,
    view: RulesUnitView,
) -> tuple[UnitCoherencyResult, tuple[Model, ...]]:
    model_by_id = {model.model_instance_id: model for model in view.alive_models()}
    placement_by_id = {
        placement.model_instance_id: placement for placement in proposal.model_placements
    }
    expected_model_ids = tuple(sorted(model_by_id))
    submitted_model_ids = tuple(sorted(placement_by_id))
    if submitted_model_ids != expected_model_ids:
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.MODEL_SET_DRIFT,
                message="Pre-battle placement must include every alive model in the rules unit.",
                field="model_placements",
            )
        )
    models: list[Model] = []
    for placement in proposal.model_placements:
        model = model_by_id.get(placement.model_instance_id)
        if model is None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.WRONG_UNIT_MODEL,
                    message="Pre-battle placement model is not in the selected rules unit.",
                    field="model_placements",
                    model_instance_id=placement.model_instance_id,
                )
            )
            continue
        if placement.player_id != request.player_id:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.PLAYER_DRIFT,
                    message="Pre-battle placement model player does not match request.",
                    field="model_placements",
                    model_instance_id=placement.model_instance_id,
                )
            )
        if placement.unit_instance_id not in view.component_unit_instance_ids:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.WRONG_UNIT_MODEL,
                    message="Pre-battle placement component unit is not in the rules unit.",
                    field="model_placements",
                    model_instance_id=placement.model_instance_id,
                    blocker_id=placement.unit_instance_id,
                )
            )
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    coherency_result = UnitCoherencyContext.from_ruleset_descriptor(
        ruleset_descriptor,
        unit_instance_id=request.unit_instance_id,
    ).validate_models(tuple(models))
    if not coherency_result.is_coherent:
        for model_id in coherency_result.offending_model_instance_ids:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_COHERENCY_BROKEN,
                    message="Pre-battle placement breaks unit coherency.",
                    field="model_placements",
                    model_instance_id=model_id,
                )
            )
    return coherency_result, tuple(models)


def _append_setup_geometry_violations(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    view: RulesUnitView,
    models: tuple[Model, ...],
    deployment_zones: tuple[DeploymentZone, ...],
) -> None:
    mission_setup = _require_mission_setup(state)
    battlefield_state = scenario.battlefield_state
    placed_models = scenario.placed_geometry_models()
    enemy_models = tuple(
        model
        for model in placed_models
        if _model_owner_player_id(scenario=scenario, model_instance_id=model.model_id)
        != view.owner_player_id
    )
    own_model_ids = {model.model_id for model in models}
    own_model_ids.update(model.model_instance_id for model in view.alive_models())
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    markers = tuple(marker.to_objective_marker() for marker in mission_setup.objective_markers)
    any_outside_zone = False
    for model in models:
        if not _model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        ):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Pre-battle placement crosses the battlefield edge.",
                    model_instance_id=model.model_id,
                )
            )
        in_deployment_zone = any(
            shapely_backend.base_footprint_within_deployment_zone(
                model.base,
                model.pose,
                zone,
            )
            for zone in deployment_zones
        )
        if not in_deployment_zone:
            any_outside_zone = True
        for blocker in blockers:
            if _models_overlap_with_volume(model, blocker):
                violations.append(
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode.MODEL_OVERLAP,
                        message="Pre-battle placement overlaps another model.",
                        model_instance_id=model.model_id,
                        blocker_id=blocker.model_id,
                    )
                )
        for enemy_model in enemy_models:
            if model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                violations.append(
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode.ENEMY_ENGAGEMENT_RANGE,
                        message="Pre-battle placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=_unit_for_model(view=view, model_instance_id=model.model_id),
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=battlefield_state.terrain_features,
            violation_code=PreBattleViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Pre-battle placement",
        )
        if terrain_violation is not None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
                    message=terrain_violation.message,
                    model_instance_id=terrain_violation.model_instance_id,
                    blocker_id=terrain_violation.blocker_id,
                )
            )
        objective_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=markers,
            violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Pre-battle placement",
        )
        if objective_violation is not None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP,
                    message=objective_violation.message,
                    model_instance_id=objective_violation.model_instance_id,
                    blocker_id=objective_violation.blocker_id,
                )
            )
    overlap = _moving_models_overlap(models)
    if overlap is not None:
        first_id, second_id = overlap
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.MODEL_OVERLAP,
                message="Pre-battle placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )
    if any_outside_zone:
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION,
                message="Pre-battle placement must be wholly within the player's deployment zone.",
                field="model_placements",
            )
        )


def _append_scout_path_violations(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    current: UnitPlacement,
    attempted: UnitPlacement,
    witness: PathWitness,
    scout_distance_inches: float,
) -> None:
    mission_setup = _require_mission_setup(state)
    battlefield_state = scenario.battlefield_state
    terrain_volumes = tuple(
        volume
        for feature in battlefield_state.terrain_features
        for volume in feature.terrain_volumes()
    )
    aircraft_model_ids: tuple[str, ...] = ()
    for placement in current.model_placements:
        model = scenario.model_instance_for_placement(placement)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=scenario.unit_instance_for_placement(current).keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=MovementMode.NORMAL,
            movement_phase_action=None,
            displacement_kind=ModelDisplacementKind.SCOUT_MOVE,
        )
        path_result = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_path(
                scenario=scenario,
                unit_placement=current,
                attempted_placement=attempted,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=current.player_id,
            ),
            terrain=terrain_volumes,
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=current.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_vehicle_monster_model_ids=_enemy_vehicle_monster_model_ids_for_player(
                scenario=scenario,
                player_id=current.player_id,
            ),
            aircraft_model_ids=aircraft_model_ids,
            movement_distance_budget_inches=scout_distance_inches,
        ).validate()
        if not path_result.is_valid:
            first_violation = path_result.violations[0]
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.PATH_VALIDATION_FAILED,
                    message=first_violation.message,
                    field="witness",
                    model_instance_id=first_violation.model_id,
                    blocker_id=first_violation.blocker_id,
                )
            )
        terrain_result = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain_volumes,
            terrain_features=battlefield_state.terrain_features,
        ).validate()
        if not terrain_result.is_valid:
            first_terrain_violation = terrain_result.violations[0]
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.TERRAIN_PATH_VALIDATION_FAILED,
                    message=first_terrain_violation.message,
                    field="witness",
                    model_instance_id=placement.model_instance_id,
                    blocker_id=first_terrain_violation.terrain_id,
                )
            )
        end_model = geometry_model_for_placement(
            model=model,
            placement=placement.with_pose(
                witness.final_pose_for_model(placement.model_instance_id)
            ),
        )
        objective_violation = objective_marker_endpoint_placement_violation(
            model=end_model,
            objective_markers=tuple(
                marker.to_objective_marker() for marker in mission_setup.objective_markers
            ),
            violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Scout Move endpoint",
        )
        if objective_violation is not None:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP,
                    message=objective_violation.message,
                    field="witness",
                    model_instance_id=objective_violation.model_instance_id,
                    blocker_id=objective_violation.blocker_id,
                )
            )


def _append_scout_enemy_distance_violations(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    scenario: BattlefieldScenario,
    attempted: UnitPlacement,
) -> None:
    enemy_models = _enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=attempted.player_id,
    )
    for placement in attempted.model_placements:
        model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for enemy_model in enemy_models:
            if model.base_distance_to(enemy_model) <= SCOUT_ENEMY_DISTANCE_INCHES + _EPSILON:
                violations.append(
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode.SCOUT_ENEMY_DISTANCE,
                        message="Scout Move must end more than 8 inches from all enemy units.",
                        field="witness",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )


def _prebattle_selection_payload(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    mission_setup: MissionSetup,
    view: RulesUnitView,
    setup_step: SetupStep,
    action_kind: PreBattleActionKind,
    source_rule_id: str,
    proposal_kind: str,
) -> JsonValue:
    if action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE:
        cargo_instances = _dedicated_transport_cargo_scout_instances(
            state=state,
            army_catalog=army_catalog,
            transport_view=view,
        )
        scout_instances = _dedicated_transport_move_scout_instances_for_transport(
            transport_view=view,
            cargo_instances=cargo_instances,
        )
    else:
        scout_instances = scout_ability_instances_for_rules_unit(
            view=view,
            army_catalog=army_catalog,
        )
    scout_distance_inches = (
        None
        if not scout_instances
        else scout_distance_inches_for_model_ids(
            model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
            ability_instances=scout_instances,
        )
    )
    payload = {
        "submission_kind": SELECT_REDEPLOY_UNIT_DECISION_TYPE
        if setup_step is SetupStep.REDEPLOY_UNITS
        else SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        "game_id": state.game_id,
        "player_id": view.owner_player_id,
        "setup_step": setup_step.value,
        "unit_instance_id": view.unit_instance_id,
        "is_attached_rules_unit": view.is_attached_rules_unit,
        "component_unit_instance_ids": list(view.component_unit_instance_ids),
        "model_instance_ids": [model.model_instance_id for model in view.alive_models()],
        "deployment_zone_ids": [
            zone.deployment_zone_id
            for zone in _deployment_zones_for_player(mission_setup, view.owner_player_id)
        ],
        "mission_pack_id": mission_setup.mission_pack_id,
        "deployment_map_id": mission_setup.deployment_map_id,
        "terrain_layout_id": mission_setup.terrain_layout_id,
        "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        "action_kind": action_kind.value,
        "source_rule_id": source_rule_id,
        "proposal_kind": proposal_kind,
        "scout_distance_inches": scout_distance_inches,
        "scout_ability_instances": [instance.to_payload() for instance in scout_instances],
    }
    return validate_json_value(payload)


def scout_ability_instances_for_rules_unit(
    *,
    view: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> tuple[ScoutAbilityInstance, ...]:
    if type(view) is not RulesUnitView:
        raise GameLifecycleError("Scouts ability lookup requires a RulesUnitView.")
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Scouts ability lookup requires an ArmyCatalog.")
    instances: list[ScoutAbilityInstance] = []
    for component in view.components:
        descriptors = scouts_ability_descriptors_for_unit(component.unit)
        if not descriptors:
            if _unit_has_keyword(component.unit, "SCOUTS"):
                raise GameLifecycleError(
                    "Scouts keyword requires a structured datasheet ability descriptor."
                )
            return ()
        for model in component.unit.alive_own_models():
            for descriptor in descriptors:
                instances.append(
                    ScoutAbilityInstance(
                        model_instance_id=model.model_instance_id,
                        distance_inches=scouts_distance_inches_from_descriptor(descriptor),
                        source_id=descriptor.source_id,
                    )
                )
    return tuple(
        sorted(
            instances,
            key=lambda instance: (
                instance.model_instance_id,
                instance.distance_inches,
                instance.source_id,
            ),
        )
    )


def _proposal_request_from_selection(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    selection_request: DecisionRequest,
    result: DecisionResult,
    setup_step: SetupStep,
    decision_type: str,
    placement_kind: BattlefieldPlacementKind | None,
) -> PreBattleProposalRequest:
    if result.actor_id is None:
        raise GameLifecycleError("Pre-battle selection requires actor_id.")
    if not isinstance(result.payload, dict):
        raise GameLifecycleError("Pre-battle selection payload must be an object.")
    unit_instance_id = _payload_string(result.payload, "unit_instance_id")
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    if view.owner_player_id != result.actor_id:
        raise GameLifecycleError("Pre-battle selection owner drift.")
    mission_setup = _require_mission_setup(state)
    action_kind = _action_kind_from_token(_payload_string(result.payload, "action_kind"))
    source_rule_id = _payload_string(result.payload, "source_rule_id")
    proposal_kind = _payload_string(result.payload, "proposal_kind")
    scout_distance_inches = None
    if action_kind in {
        PreBattleActionKind.SCOUT_MOVE,
        PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE,
    }:
        instances = scout_ability_instances_for_rules_unit(
            view=view,
            army_catalog=army_catalog,
        )
        if action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE:
            instances = _dedicated_transport_cargo_scout_instances(
                state=state,
                army_catalog=army_catalog,
                transport_view=view,
            )
        scout_distance_inches = scout_distance_inches_for_model_ids(
            model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
            ability_instances=(
                scout_ability_instances_for_rules_unit(
                    view=view,
                    army_catalog=army_catalog,
                )
                if action_kind is PreBattleActionKind.SCOUT_MOVE
                else _dedicated_transport_move_scout_instances_for_transport(
                    transport_view=view,
                    cargo_instances=instances,
                )
            ),
        )
        if action_kind is PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE:
            cargo_distance = min(instance.distance_inches for instance in instances)
            scout_distance_inches = min(scout_distance_inches, cargo_distance)
    return PreBattleProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=decision_type,
        actor_id=result.actor_id,
        game_id=state.game_id,
        setup_step=setup_step,
        player_id=result.actor_id,
        unit_instance_id=view.unit_instance_id,
        component_unit_instance_ids=view.component_unit_instance_ids,
        model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
        proposal_kind=proposal_kind,
        action_kind=action_kind,
        source_rule_id=source_rule_id,
        deployment_zones=_deployment_zones_for_player(mission_setup, result.actor_id),
        mission_setup=mission_setup,
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        source_decision_request_id=selection_request.request_id,
        source_decision_result_id=result.result_id,
        placement_kind=placement_kind,
        scout_distance_inches=scout_distance_inches,
        context={
            "is_attached_rules_unit": view.is_attached_rules_unit,
            "source_rule_id": source_rule_id,
            "action_kind": action_kind.value,
        },
    )


def _common_request_drift_violations(
    proposal: PreBattlePlacementProposal | ScoutMoveProposal,
    request: PreBattleProposalRequest,
) -> list[PreBattleViolation]:
    checks = (
        (
            proposal.proposal_request_id != request.request_id,
            PreBattleViolationCode.STALE_PROPOSAL_REQUEST,
            "Pre-battle proposal request_id does not match the pending request.",
            "proposal_request_id",
        ),
        (
            proposal.proposal_kind != request.proposal_kind,
            PreBattleViolationCode.PROPOSAL_KIND_DRIFT,
            "Pre-battle proposal kind does not match the pending request.",
            "proposal_kind",
        ),
        (
            proposal.game_id != request.game_id,
            PreBattleViolationCode.GAME_ID_DRIFT,
            "Pre-battle proposal game_id does not match the pending request.",
            "game_id",
        ),
        (
            proposal.ruleset_descriptor_hash != request.ruleset_descriptor_hash,
            PreBattleViolationCode.RULESET_HASH_DRIFT,
            "Pre-battle proposal ruleset hash does not match the pending request.",
            "ruleset_descriptor_hash",
        ),
        (
            proposal.setup_step is not request.setup_step,
            PreBattleViolationCode.SETUP_STEP_DRIFT,
            "Pre-battle proposal setup step does not match the pending request.",
            "setup_step",
        ),
        (
            proposal.player_id != request.player_id,
            PreBattleViolationCode.PLAYER_DRIFT,
            "Pre-battle proposal player does not match the pending request.",
            "player_id",
        ),
        (
            proposal.unit_instance_id != request.unit_instance_id,
            PreBattleViolationCode.UNIT_DRIFT,
            "Pre-battle proposal unit does not match the pending request.",
            "unit_instance_id",
        ),
        (
            proposal.action_kind is not request.action_kind,
            PreBattleViolationCode.ACTION_KIND_DRIFT,
            "Pre-battle proposal action kind does not match the pending request.",
            "action_kind",
        ),
        (
            proposal.source_rule_id != request.source_rule_id,
            PreBattleViolationCode.SOURCE_RULE_DRIFT,
            "Pre-battle proposal source rule does not match the pending request.",
            "source_rule_id",
        ),
    )
    violations: list[PreBattleViolation] = []
    for failed, code, message, field in checks:
        if failed:
            violations.append(
                PreBattleViolation(
                    violation_code=code,
                    message=message,
                    field=field,
                )
            )
    return violations


def _invalid_prebattle_status(
    *,
    state: GameState,
    request_id: str,
    invalid_reason: str,
    violations: tuple[PreBattleViolation, ...],
    resolution: PreBattleResolution | None,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Pre-battle proposal submission is invalid.",
        payload={
            "invalid_reason": invalid_reason,
            "request_id": request_id,
            "violations": cast(JsonValue, [violation.to_payload() for violation in violations]),
            "resolution": cast(JsonValue, None if resolution is None else resolution.to_payload()),
        },
    )


def _completed_kind_for_step_player(
    *,
    state: GameState,
    setup_step: SetupStep,
    player_id: str,
) -> PreBattleActionKind | None:
    complete_kinds = {
        SetupStep.REDEPLOY_UNITS: PreBattleActionKind.COMPLETE_REDEPLOYS,
        SetupStep.RESOLVE_PREBATTLE_ACTIONS: PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS,
    }
    complete_kind = complete_kinds[setup_step]
    for record in state.prebattle_action_records_for_step(
        player_id=player_id,
        setup_step=setup_step,
    ):
        if record.action_kind is complete_kind:
            return complete_kind
    return None


def _completed_step_for_player(
    *,
    state: GameState,
    player_id: str,
    setup_step: SetupStep,
    complete_kind: PreBattleActionKind,
) -> bool:
    return any(
        record.action_kind is complete_kind
        for record in state.prebattle_action_records_for_step(
            player_id=player_id,
            setup_step=setup_step,
        )
    )


def _unit_action_record_exists(
    *,
    state: GameState,
    setup_step: SetupStep,
    unit_instance_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for player_id in state.player_ids:
        for record in state.prebattle_action_records_for_step(
            player_id=player_id,
            setup_step=setup_step,
        ):
            if record.unit_instance_id == requested_unit_id:
                return True
    return False


def _current_grouped_unit_placements(
    state: GameState,
    unit_instance_id: str,
) -> tuple[UnitPlacement, ...]:
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    battlefield = _require_battlefield_state(state)
    return tuple(
        battlefield.unit_placement_by_id(component_id)
        for component_id in view.component_unit_instance_ids
    )


def _rules_unit_views_for_player(*, state: GameState, player_id: str) -> tuple[RulesUnitView, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Pre-battle options require a mustered army.")
    attached_component_ids = {
        unit_id
        for attached in army.attached_units
        for unit_id in attached.component_unit_instance_ids
    }
    views: list[RulesUnitView] = []
    for attached in army.attached_units:
        views.append(
            rules_unit_view_from_armies(
                armies=tuple(state.army_definitions),
                unit_instance_id=attached.attached_unit_instance_id,
            )
        )
    for unit in army.units:
        if unit.unit_instance_id in attached_component_ids:
            continue
        views.append(
            rules_unit_view_from_armies(
                armies=tuple(state.army_definitions),
                unit_instance_id=unit.unit_instance_id,
            )
        )
    return tuple(sorted(views, key=lambda view: view.unit_instance_id))


def _rules_unit_is_placed(*, battlefield: BattlefieldRuntimeState, view: RulesUnitView) -> bool:
    placed_ids = {
        unit_placement.unit_instance_id
        for placed_army in battlefield.placed_armies
        for unit_placement in placed_army.unit_placements
    }
    return set(view.component_unit_instance_ids) <= placed_ids


def _rules_unit_wholly_within_zones(
    *,
    state: GameState,
    battlefield: BattlefieldRuntimeState,
    view: RulesUnitView,
    zones: tuple[DeploymentZone, ...],
) -> bool:
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    for component_id in view.component_unit_instance_ids:
        unit_placement = battlefield.unit_placement_by_id(component_id)
        for placement in unit_placement.model_placements:
            model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            )
            if not any(
                shapely_backend.base_footprint_within_deployment_zone(
                    model.base,
                    model.pose,
                    zone,
                )
                for zone in zones
            ):
                return False
    return True


def _start_is_eligible_for_scout_move(*, state: GameState, view: RulesUnitView) -> bool:
    mission_setup = _require_mission_setup(state)
    battlefield = _require_battlefield_state(state)
    return _rules_unit_wholly_within_zones(
        state=state,
        battlefield=battlefield,
        view=view,
        zones=_deployment_zones_for_player(mission_setup, view.owner_player_id),
    )


def _transport_cargo_all_scouts(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
    cargo_state: object,
) -> bool:
    from warhammer40k_core.engine.transports import TransportCargoState

    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("Dedicated Transport Scouts check requires cargo state.")
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Dedicated Transport Scouts check requires an ArmyCatalog.")
    if not cargo_state.embarked_unit_instance_ids:
        return False
    for unit_id in cargo_state.embarked_unit_instance_ids:
        view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions),
            unit_instance_id=unit_id,
        )
        if not _rules_unit_all_components_have_scouts(view=view, army_catalog=army_catalog):
            return False
    return True


def _dedicated_transport_cargo_scout_instances(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
    transport_view: RulesUnitView,
) -> tuple[ScoutAbilityInstance, ...]:
    cargo_state = state.transport_cargo_state_for_transport(transport_view.unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Dedicated Transport Scout Move requires cargo.")
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Dedicated Transport Scout Move requires an ArmyCatalog.")
    instances: list[ScoutAbilityInstance] = []
    for unit_id in cargo_state.embarked_unit_instance_ids:
        view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions),
            unit_instance_id=unit_id,
        )
        instances.extend(
            scout_ability_instances_for_rules_unit(view=view, army_catalog=army_catalog)
        )
    if not instances:
        raise GameLifecycleError("Dedicated Transport Scout Move requires Scouts cargo.")
    return tuple(instances)


def _dedicated_transport_move_scout_instances_for_transport(
    *,
    transport_view: RulesUnitView,
    cargo_instances: tuple[ScoutAbilityInstance, ...],
) -> tuple[ScoutAbilityInstance, ...]:
    cargo_distance = min(instance.distance_inches for instance in cargo_instances)
    return tuple(
        ScoutAbilityInstance(
            model_instance_id=model.model_instance_id,
            distance_inches=cargo_distance,
            source_id=CORE_SCOUTS_SOURCE_RULE_ID,
        )
        for model in transport_view.alive_models()
    )


def _friendly_geometry_models_for_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    attempted_placement: UnitPlacement,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            placements = (
                attempted_placement.model_placements
                if current_unit_placement.unit_instance_id == unit_placement.unit_instance_id
                else current_unit_placement.model_placements
            )
            for placement in placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return tuple(friendly_models)


def _enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[Model, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    enemy_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(enemy_models)


def _friendly_vehicle_monster_model_ids(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    moving_model_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
            )
    return tuple(sorted(model_ids))


def _enemy_vehicle_monster_model_ids_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id for placement in unit_placement.model_placements
            )
    return tuple(sorted(model_ids))


def _unit_for_model(*, view: RulesUnitView, model_instance_id: str) -> UnitInstance:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for component in view.components:
        if any(
            model.model_instance_id == requested_model_id for model in component.unit.own_models
        ):
            return component.unit
    raise GameLifecycleError("model_instance_id is not in the rules unit.")


def _unit_has_vehicle_or_monster_keyword(keywords: tuple[str, ...]) -> bool:
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    return "VEHICLE" in keyword_set or "MONSTER" in keyword_set


def _rules_unit_all_components_have_keyword(view: RulesUnitView, keyword: str) -> bool:
    return all(_unit_has_keyword(component.unit, keyword) for component in view.components)


def _rules_unit_all_components_have_scouts(
    *,
    view: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> bool:
    return bool(scout_ability_instances_for_rules_unit(view=view, army_catalog=army_catalog))


def _rules_unit_any_component_has_keyword(view: RulesUnitView, keyword: str) -> bool:
    return any(_unit_has_keyword(component.unit, keyword) for component in view.components)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested = _canonical_keyword(keyword)
    return requested in {_canonical_keyword(value) for value in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).upper().replace(" ", "_").replace("-", "_")


def _model_is_within_battlefield(
    model: Model,
    *,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    return (
        min_x >= -_EPSILON
        and min_y >= -_EPSILON
        and max_x <= battlefield_width_inches + _EPSILON
        and max_y <= battlefield_depth_inches + _EPSILON
    )


def _models_overlap_with_volume(first: Model, second: Model) -> bool:
    if not first.base_overlaps(second):
        return False
    return first.volume.vertical_gap_to(first.pose, second.volume, second.pose) <= _EPSILON


def _moving_models_overlap(models: tuple[Model, ...]) -> tuple[str, str] | None:
    for first_index, first in enumerate(models):
        for second in models[first_index + 1 :]:
            if _models_overlap_with_volume(first, second):
                return first.model_id, second.model_id
    return None


def _model_owner_player_id(*, scenario: BattlefieldScenario, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                if model_placement.model_instance_id == requested_model_id:
                    return placed_army.player_id
    raise GameLifecycleError("model_instance_id is not placed.")


def _validate_prebattle_state(state: GameState, setup_step: SetupStep) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Pre-battle proposal requires GameState.")
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Pre-battle proposal requires setup stage.")
    if state.current_setup_step is not setup_step:
        raise GameLifecycleError("Pre-battle proposal setup step drift.")
    _require_mission_setup(state)
    _require_battlefield_state(state)


def _require_mission_setup(state: GameState) -> MissionSetup:
    if state.mission_setup is None:
        raise GameLifecycleError("Pre-battle rules require source-backed MissionSetup.")
    return state.mission_setup


def _require_battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise GameLifecycleError("Pre-battle rules require battlefield_state.")
    return state.battlefield_state


def _require_reserve_state(state: GameState, unit_instance_id: str) -> ReserveState:
    reserve_state = state.reserve_state_for_unit(unit_instance_id)
    if reserve_state is None:
        raise GameLifecycleError("Pre-battle reserve setup requires ReserveState.")
    return reserve_state


def _deployment_zones_for_player(
    mission_setup: MissionSetup,
    player_id: str,
) -> tuple[DeploymentZone, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    zones = tuple(
        zone for zone in mission_setup.deployment_zones if zone.player_id == requested_player_id
    )
    if not zones:
        raise GameLifecycleError("Mission setup has no deployment zone for player.")
    return tuple(sorted(zones, key=lambda zone: zone.deployment_zone_id))


def _validate_deployment_zone_tuple(
    field_name: str,
    values: object,
) -> tuple[DeploymentZone, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    zones: list[DeploymentZone] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeploymentZone:
            raise GameLifecycleError(f"{field_name} must contain DeploymentZone values.")
        if value.deployment_zone_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate zones.")
        seen.add(value.deployment_zone_id)
        zones.append(value)
    return tuple(sorted(zones, key=lambda zone: zone.deployment_zone_id))


def _validate_model_placement_tuple(
    field_name: str,
    values: object,
) -> tuple[ModelPlacement, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    placements: list[ModelPlacement] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ModelPlacement:
            raise GameLifecycleError(f"{field_name} must contain ModelPlacement values.")
        if value.model_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate models.")
        seen.add(value.model_instance_id)
        placements.append(value)
    if not placements:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def _validate_prebattle_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[PreBattleViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    violations: list[PreBattleViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not PreBattleViolation:
            raise GameLifecycleError(f"{field_name} must contain PreBattleViolation values.")
        violations.append(value)
    return tuple(violations)


def _validate_scout_ability_instances(
    values: object,
) -> tuple[ScoutAbilityInstance, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Scout ability instances must be a tuple.")
    instances: list[ScoutAbilityInstance] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not ScoutAbilityInstance:
            raise GameLifecycleError("Scout ability instances must contain ScoutAbilityInstance.")
        instances.append(value)
    return tuple(instances)


def _validate_prebattle_proposal_decision_type(value: object) -> str:
    decision_type = _validate_identifier("prebattle proposal decision_type", value)
    if decision_type not in {
        SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        SUBMIT_SCOUT_MOVE_DECISION_TYPE,
        SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
    }:
        raise GameLifecycleError("Unsupported pre-battle proposal decision type.")
    return decision_type


def _validate_prebattle_proposal_kind(value: object) -> str:
    kind = _validate_identifier("prebattle proposal kind", value)
    if kind not in {
        REDEPLOY_PROPOSAL_KIND,
        SCOUT_MOVE_PROPOSAL_KIND,
        SCOUT_RESERVE_SETUP_PROPOSAL_KIND,
    }:
        raise GameLifecycleError("Unsupported pre-battle proposal kind.")
    return kind


def _setup_step_from_token(token: object) -> SetupStep:
    if type(token) is SetupStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SetupStep token must be a string.")
    try:
        return SetupStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SetupStep token: {token}.") from exc


def _action_kind_from_token(token: object) -> PreBattleActionKind:
    if type(token) is PreBattleActionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("PreBattleActionKind token must be a string.")
    try:
        return PreBattleActionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported PreBattleActionKind token: {token}.") from exc


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(field_name, value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_non_empty_string(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"{field_name} must be a number.")
    typed_value = cast(int | float, value)
    number = float(typed_value)
    if not math.isfinite(number) or number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be a positive finite number.")
    return number
