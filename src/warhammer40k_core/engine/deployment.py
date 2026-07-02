from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZoneError,
    DeploymentZonePayload,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementPayload,
    ModelPlacementRecord,
    PlacementError,
    UnitPlacement,
    battlefield_placement_kind_from_token,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
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
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.unit_abilities import unit_has_infiltrators
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyContext,
    UnitCoherencyResult,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model

SELECT_DEPLOYMENT_UNIT_DECISION_TYPE = "select_deployment_unit"
SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE = "submit_deployment_placement"
DEPLOYMENT_PROPOSAL_KIND = "deployment_placement"
DEPLOY_ARMIES_SOURCE_RULE_ID = "core_rules_deploy_armies"

_INFILTRATORS_DISTANCE_INCHES = 8.0
_EPSILON = 1e-9


class DeploymentOrderPolicyKind(StrEnum):
    DEFENDER_FIRST_ALTERNATING = "defender_first_alternating"


class DeploymentPlacementViolationCode(StrEnum):
    STALE_PROPOSAL_REQUEST = "stale_proposal_request"
    PROPOSAL_KIND_DRIFT = "proposal_kind_drift"
    GAME_ID_DRIFT = "game_id_drift"
    RULESET_HASH_DRIFT = "ruleset_hash_drift"
    SETUP_STEP_DRIFT = "setup_step_drift"
    PLAYER_DRIFT = "player_drift"
    UNIT_DRIFT = "unit_drift"
    PLACEMENT_KIND_DRIFT = "placement_kind_drift"
    UNIT_NOT_DEPLOYABLE = "unit_not_deployable"
    MODEL_SET_DRIFT = "model_set_drift"
    WRONG_UNIT_MODEL = "wrong_unit_model"
    BATTLEFIELD_EDGE_CROSSED = "battlefield_edge_crossed"
    DEPLOYMENT_ZONE_VIOLATION = "deployment_zone_violation"
    INFILTRATORS_KEYWORD_REQUIRED = "infiltrators_keyword_required"
    INFILTRATORS_ENEMY_ZONE_DISTANCE = "infiltrators_enemy_zone_distance"
    INFILTRATORS_ENEMY_UNIT_DISTANCE = "infiltrators_enemy_unit_distance"
    MODEL_OVERLAP = "model_overlap"
    TERRAIN_ENDPOINT_ILLEGAL = "terrain_endpoint_illegal"
    OBJECTIVE_MARKER_ENDPOINT_OVERLAP = "objective_marker_endpoint_overlap"
    ENEMY_ENGAGEMENT_RANGE = "enemy_engagement_range"
    UNIT_COHERENCY_BROKEN = "unit_coherency_broken"
    FORTIFICATION_DEPLOYMENT_UNSUPPORTED = "fortification_deployment_unsupported"


class DeploymentSetupStatePayload(TypedDict):
    setup_step: str
    order_policy: str
    next_player_id: str | None
    remaining_unit_count_by_player: dict[str, int]


class DeploymentUnitSelectionPayload(TypedDict):
    submission_kind: str
    game_id: str
    player_id: str
    setup_step: str
    unit_instance_id: str
    is_attached_rules_unit: bool
    component_unit_instance_ids: list[str]
    model_instance_ids: list[str]
    deployment_zone_ids: list[str]
    mission_pack_id: str
    deployment_map_id: str
    terrain_layout_id: str
    ruleset_descriptor_hash: str


class DeploymentPlacementRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    setup_step: str
    player_id: str
    unit_instance_id: str
    component_unit_instance_ids: list[str]
    model_instance_ids: list[str]
    placement_kind: str
    deployment_zone_ids: list[str]
    legal_deployment_zones: list[DeploymentZonePayload]
    mission_pack_id: str
    source_id: str
    deployment_map_id: str
    terrain_layout_id: str
    mission_setup: MissionSetupPayload
    ruleset_descriptor_hash: str
    source_decision_request_id: str
    source_decision_result_id: str
    proposal_kind: str
    context: dict[str, JsonValue]


class DeploymentPlacementDecisionRequestPayload(TypedDict):
    proposal_request: DeploymentPlacementRequestPayload


class DeploymentPlacementProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    game_id: str
    ruleset_descriptor_hash: str
    setup_step: str
    player_id: str
    unit_instance_id: str
    placement_kind: str
    model_placements: list[ModelPlacementPayload]
    context: NotRequired[dict[str, JsonValue]]


class DeploymentPlacementViolationPayload(TypedDict):
    violation_code: str
    message: str
    field: str | None
    model_instance_id: str | None
    blocker_id: str | None


class DeploymentPlacementResolutionPayload(TypedDict):
    proposal: DeploymentPlacementProposalPayload
    is_valid: bool
    violations: list[DeploymentPlacementViolationPayload]
    coherency_result: dict[str, JsonValue]
    transition_batch: dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class DeploymentSetupState:
    setup_step: SetupStep
    order_policy: DeploymentOrderPolicyKind
    next_player_id: str | None
    remaining_unit_count_by_player: dict[str, int]

    def __post_init__(self) -> None:
        if self.setup_step is not SetupStep.DEPLOY_ARMIES:
            raise GameLifecycleError("DeploymentSetupState requires DEPLOY_ARMIES.")
        object.__setattr__(
            self,
            "order_policy",
            deployment_order_policy_kind_from_token(self.order_policy),
        )
        object.__setattr__(
            self,
            "next_player_id",
            _validate_optional_identifier(
                "DeploymentSetupState next_player_id",
                self.next_player_id,
            ),
        )
        counts: dict[str, int] = {}
        for player_id, count in self.remaining_unit_count_by_player.items():
            counts[_validate_identifier("DeploymentSetupState player_id", player_id)] = (
                _validate_non_negative_int("DeploymentSetupState remaining count", count)
            )
        object.__setattr__(self, "remaining_unit_count_by_player", counts)

    def to_payload(self) -> DeploymentSetupStatePayload:
        return {
            "setup_step": self.setup_step.value,
            "order_policy": self.order_policy.value,
            "next_player_id": self.next_player_id,
            "remaining_unit_count_by_player": dict(self.remaining_unit_count_by_player),
        }


@dataclass(frozen=True, slots=True)
class DeploymentOrderPolicy:
    policy_kind: DeploymentOrderPolicyKind = DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
    source_rule_id: str = DEPLOY_ARMIES_SOURCE_RULE_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_kind",
            deployment_order_policy_kind_from_token(self.policy_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DeploymentOrderPolicy source_rule_id", self.source_rule_id),
        )

    @classmethod
    def core_rules(cls) -> Self:
        return cls()

    def next_player_id(self, state: GameState) -> str | None:
        if type(state) is not GameState:
            raise GameLifecycleError("Deployment order requires GameState.")
        mission_setup = _require_mission_setup(state)
        remaining = {
            player_id: deployment_unit_views_for_player(state=state, player_id=player_id)
            for player_id in state.player_ids
        }
        if not any(remaining.values()):
            return None
        if len(state.player_ids) != 2:
            raise GameLifecycleError("Deployment order currently supports two-player games.")
        defender = mission_setup.defender_player_id
        attacker = mission_setup.attacker_player_id
        deployed_counts = _deployed_rules_unit_count_by_player(state)
        preferred = (
            defender
            if deployed_counts.get(defender, 0) <= deployed_counts.get(attacker, 0)
            else attacker
        )
        if remaining[preferred]:
            return preferred
        alternate = attacker if preferred == defender else defender
        if remaining[alternate]:
            return alternate
        return None


@dataclass(frozen=True, slots=True)
class DeploymentPlacementRequest:
    request_id: str
    actor_id: str
    game_id: str
    player_id: str
    unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    model_instance_ids: tuple[str, ...]
    deployment_zones: tuple[DeploymentZone, ...]
    mission_setup: MissionSetup
    ruleset_descriptor_hash: str
    source_decision_request_id: str
    source_decision_result_id: str
    placement_kind: BattlefieldPlacementKind = BattlefieldPlacementKind.DEPLOYMENT
    proposal_kind: str = DEPLOYMENT_PROPOSAL_KIND
    context: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("DeploymentPlacementRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "actor_id",
            _validate_identifier("DeploymentPlacementRequest actor_id", self.actor_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("DeploymentPlacementRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DeploymentPlacementRequest player_id", self.player_id),
        )
        if self.actor_id != self.player_id:
            raise GameLifecycleError("DeploymentPlacementRequest actor_id must match player_id.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DeploymentPlacementRequest unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "component_unit_instance_ids",
            _validate_identifier_tuple(
                "DeploymentPlacementRequest component_unit_instance_ids",
                self.component_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "DeploymentPlacementRequest model_instance_ids",
                self.model_instance_ids,
            ),
        )
        zones = _validate_deployment_zone_tuple(
            "DeploymentPlacementRequest deployment_zones",
            self.deployment_zones,
        )
        if not zones:
            raise GameLifecycleError("DeploymentPlacementRequest requires deployment zones.")
        for zone in zones:
            if zone.player_id != self.player_id:
                raise GameLifecycleError("DeploymentPlacementRequest deployment zone player drift.")
        object.__setattr__(self, "deployment_zones", zones)
        if type(self.mission_setup) is not MissionSetup:
            raise GameLifecycleError(
                "DeploymentPlacementRequest mission_setup must be MissionSetup."
            )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "DeploymentPlacementRequest ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "DeploymentPlacementRequest source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "DeploymentPlacementRequest source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        if self.placement_kind is not BattlefieldPlacementKind.DEPLOYMENT:
            raise GameLifecycleError("DeploymentPlacementRequest requires deployment placement.")
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_deployment_proposal_kind(self.proposal_kind),
        )
        context = {} if self.context is None else self.context
        json_context = validate_json_value(context)
        if not isinstance(json_context, dict):
            raise GameLifecycleError("DeploymentPlacementRequest context must be a JSON object.")
        object.__setattr__(self, "context", json_context)

    def to_decision_request(self) -> DecisionRequest:
        return DecisionRequest(
            request_id=self.request_id,
            decision_type=SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
            actor_id=self.actor_id,
            payload={"proposal_request": validate_json_value(self.to_payload())},
            options=(parameterized_decision_option(),),
        )

    def to_payload(self) -> DeploymentPlacementRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
            "actor_id": self.actor_id,
            "game_id": self.game_id,
            "setup_step": SetupStep.DEPLOY_ARMIES.value,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "model_instance_ids": list(self.model_instance_ids),
            "placement_kind": self.placement_kind.value,
            "deployment_zone_ids": [zone.deployment_zone_id for zone in self.deployment_zones],
            "legal_deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "mission_pack_id": self.mission_setup.mission_pack_id,
            "source_id": self.mission_setup.source_id,
            "deployment_map_id": self.mission_setup.deployment_map_id,
            "terrain_layout_id": self.mission_setup.terrain_layout_id,
            "mission_setup": self.mission_setup.to_payload(),
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "proposal_kind": self.proposal_kind,
            "context": dict(self.context or {}),
        }

    @classmethod
    def from_payload(cls, payload: DeploymentPlacementRequestPayload) -> Self:
        return cls(
            request_id=payload["request_id"],
            actor_id=payload["actor_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            component_unit_instance_ids=tuple(payload["component_unit_instance_ids"]),
            model_instance_ids=tuple(payload["model_instance_ids"]),
            deployment_zones=tuple(
                DeploymentZone.from_payload(zone) for zone in payload["legal_deployment_zones"]
            ),
            mission_setup=MissionSetup.from_payload(payload["mission_setup"]),
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            placement_kind=battlefield_placement_kind_from_token(payload["placement_kind"]),
            proposal_kind=payload["proposal_kind"],
            context=payload["context"],
        )

    @classmethod
    def from_decision_request_payload(cls, payload: object) -> Self:
        json_payload = validate_json_value(payload)
        if not isinstance(json_payload, dict):
            raise GameLifecycleError("Deployment DecisionRequest payload must be an object.")
        request_payload = json_payload.get("proposal_request")
        if not isinstance(request_payload, dict):
            raise GameLifecycleError("Deployment DecisionRequest payload missing request.")
        typed_payload = cast(DeploymentPlacementRequestPayload, request_payload)
        return cls(
            request_id=typed_payload["request_id"],
            actor_id=typed_payload["actor_id"],
            game_id=typed_payload["game_id"],
            player_id=typed_payload["player_id"],
            unit_instance_id=typed_payload["unit_instance_id"],
            component_unit_instance_ids=tuple(typed_payload["component_unit_instance_ids"]),
            model_instance_ids=tuple(typed_payload["model_instance_ids"]),
            deployment_zones=tuple(
                DeploymentZone.from_payload(zone)
                for zone in typed_payload["legal_deployment_zones"]
            ),
            mission_setup=MissionSetup.from_payload(typed_payload["mission_setup"]),
            ruleset_descriptor_hash=typed_payload["ruleset_descriptor_hash"],
            source_decision_request_id=typed_payload["source_decision_request_id"],
            source_decision_result_id=typed_payload["source_decision_result_id"],
            placement_kind=battlefield_placement_kind_from_token(typed_payload["placement_kind"]),
            proposal_kind=typed_payload["proposal_kind"],
            context=typed_payload["context"],
        )


@dataclass(frozen=True, slots=True)
class DeploymentPlacementProposal:
    proposal_request_id: str
    proposal_kind: str
    game_id: str
    ruleset_descriptor_hash: str
    setup_step: SetupStep
    player_id: str
    unit_instance_id: str
    placement_kind: BattlefieldPlacementKind
    model_placements: tuple[ModelPlacement, ...]
    context: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "DeploymentPlacementProposal proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_deployment_proposal_kind(self.proposal_kind),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("DeploymentPlacementProposal game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "DeploymentPlacementProposal ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        if self.setup_step is not SetupStep.DEPLOY_ARMIES:
            raise GameLifecycleError("DeploymentPlacementProposal requires DEPLOY_ARMIES.")
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DeploymentPlacementProposal player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DeploymentPlacementProposal unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        placements = _validate_model_placement_tuple(
            "DeploymentPlacementProposal model_placements",
            self.model_placements,
        )
        object.__setattr__(self, "model_placements", placements)
        context = {} if self.context is None else self.context
        json_context = validate_json_value(context)
        if not isinstance(json_context, dict):
            raise GameLifecycleError("DeploymentPlacementProposal context must be a JSON object.")
        object.__setattr__(self, "context", json_context)

    def request_drift_violations(
        self,
        request: DeploymentPlacementRequest,
    ) -> tuple[DeploymentPlacementViolation, ...]:
        if type(request) is not DeploymentPlacementRequest:
            raise GameLifecycleError("Deployment placement validation requires a request.")
        checks = (
            (
                self.proposal_request_id != request.request_id,
                DeploymentPlacementViolationCode.STALE_PROPOSAL_REQUEST,
                "Deployment proposal request_id does not match the pending request.",
                "proposal_request_id",
            ),
            (
                self.proposal_kind != request.proposal_kind,
                DeploymentPlacementViolationCode.PROPOSAL_KIND_DRIFT,
                "Deployment proposal kind does not match the pending request.",
                "proposal_kind",
            ),
            (
                self.game_id != request.game_id,
                DeploymentPlacementViolationCode.GAME_ID_DRIFT,
                "Deployment proposal game_id does not match the pending request.",
                "game_id",
            ),
            (
                self.ruleset_descriptor_hash != request.ruleset_descriptor_hash,
                DeploymentPlacementViolationCode.RULESET_HASH_DRIFT,
                "Deployment proposal ruleset hash does not match the pending request.",
                "ruleset_descriptor_hash",
            ),
            (
                self.setup_step is not SetupStep.DEPLOY_ARMIES,
                DeploymentPlacementViolationCode.SETUP_STEP_DRIFT,
                "Deployment proposal setup step does not match the pending request.",
                "setup_step",
            ),
            (
                self.player_id != request.player_id,
                DeploymentPlacementViolationCode.PLAYER_DRIFT,
                "Deployment proposal player does not match the pending request.",
                "player_id",
            ),
            (
                self.unit_instance_id != request.unit_instance_id,
                DeploymentPlacementViolationCode.UNIT_DRIFT,
                "Deployment proposal unit does not match the pending request.",
                "unit_instance_id",
            ),
            (
                self.placement_kind is not request.placement_kind,
                DeploymentPlacementViolationCode.PLACEMENT_KIND_DRIFT,
                "Deployment proposal placement kind does not match the pending request.",
                "placement_kind",
            ),
        )
        violations: list[DeploymentPlacementViolation] = []
        for failed, code, message, field in checks:
            if failed:
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=code,
                        message=message,
                        field=field,
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

    def to_payload(self) -> DeploymentPlacementProposalPayload:
        payload: DeploymentPlacementProposalPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "game_id": self.game_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "setup_step": self.setup_step.value,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "placement_kind": self.placement_kind.value,
            "model_placements": [placement.to_payload() for placement in self.model_placements],
        }
        if self.context:
            payload["context"] = dict(self.context)
        return payload

    @classmethod
    def from_payload(cls, payload: DeploymentPlacementProposalPayload) -> Self:
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=payload["proposal_kind"],
            game_id=payload["game_id"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            placement_kind=battlefield_placement_kind_from_token(payload["placement_kind"]),
            model_placements=tuple(
                ModelPlacement.from_payload(placement) for placement in payload["model_placements"]
            ),
            context=payload.get("context"),
        )


@dataclass(frozen=True, slots=True)
class DeploymentPlacementViolation:
    violation_code: DeploymentPlacementViolationCode
    message: str
    field: str | None = None
    model_instance_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            deployment_placement_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_non_empty_string("DeploymentPlacementViolation message", self.message),
        )
        object.__setattr__(
            self,
            "field",
            _validate_optional_identifier("DeploymentPlacementViolation field", self.field),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "DeploymentPlacementViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier(
                "DeploymentPlacementViolation blocker_id",
                self.blocker_id,
            ),
        )

    def to_payload(self) -> DeploymentPlacementViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "field": self.field,
            "model_instance_id": self.model_instance_id,
            "blocker_id": self.blocker_id,
        }


@dataclass(frozen=True, slots=True)
class DeploymentPlacementResolution:
    proposal: DeploymentPlacementProposal
    violations: tuple[DeploymentPlacementViolation, ...]
    coherency_result: UnitCoherencyResult
    transition_batch: BattlefieldTransitionBatch | None

    def __post_init__(self) -> None:
        if type(self.proposal) is not DeploymentPlacementProposal:
            raise GameLifecycleError("DeploymentPlacementResolution proposal must be a proposal.")
        object.__setattr__(
            self,
            "violations",
            _validate_deployment_placement_violation_tuple(
                "DeploymentPlacementResolution violations",
                self.violations,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "DeploymentPlacementResolution coherency_result must be UnitCoherencyResult."
            )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "DeploymentPlacementResolution transition_batch must be BattlefieldTransitionBatch."
            )
        if self.violations and self.transition_batch is not None:
            raise GameLifecycleError("Invalid deployment placement cannot have transitions.")
        if not self.violations and self.transition_batch is None:
            raise GameLifecycleError("Valid deployment placement requires transitions.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> DeploymentPlacementResolutionPayload:
        return {
            "proposal": self.proposal.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "coherency_result": cast(
                dict[str, JsonValue],
                self.coherency_result.to_payload(),
            ),
            "transition_batch": None
            if self.transition_batch is None
            else cast(dict[str, JsonValue], self.transition_batch.to_payload()),
        }


def deployment_order_policy_kind_from_token(token: object) -> DeploymentOrderPolicyKind:
    if type(token) is DeploymentOrderPolicyKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DeploymentOrderPolicyKind token must be a string.")
    try:
        return DeploymentOrderPolicyKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported DeploymentOrderPolicyKind token: {token}.") from exc


def deployment_placement_violation_code_from_token(
    token: object,
) -> DeploymentPlacementViolationCode:
    if type(token) is DeploymentPlacementViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DeploymentPlacementViolationCode token must be a string.")
    try:
        return DeploymentPlacementViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported DeploymentPlacementViolationCode token: {token}."
        ) from exc


def create_empty_deployment_battlefield_state(*, state: GameState) -> BattlefieldRuntimeState:
    if type(state) is not GameState:
        raise GameLifecycleError("Deployment battlefield creation requires GameState.")
    mission_setup = _require_mission_setup(state)
    return BattlefieldRuntimeState(
        battlefield_id=f"{state.game_id}:{mission_setup.deployment_map_id}:battlefield",
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
        placed_armies=(),
    )


def deployment_setup_state_for_state(state: GameState) -> DeploymentSetupState:
    policy = DeploymentOrderPolicy.core_rules()
    remaining = {
        player_id: len(deployment_unit_views_for_player(state=state, player_id=player_id))
        for player_id in state.player_ids
    }
    return DeploymentSetupState(
        setup_step=SetupStep.DEPLOY_ARMIES,
        order_policy=policy.policy_kind,
        next_player_id=policy.next_player_id(state),
        remaining_unit_count_by_player=remaining,
    )


def deployment_unit_selection_request(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    player_id: str,
) -> DecisionRequest:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Deployment unit selection requires RulesetDescriptor.")
    requested_player_id = _validate_identifier("player_id", player_id)
    mission_setup = _require_mission_setup(state)
    views = deployment_unit_views_for_player(state=state, player_id=requested_player_id)
    zones = _deployment_zones_for_player(mission_setup, requested_player_id)
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        actor_id=requested_player_id,
        payload={
            "game_id": state.game_id,
            "setup_step": SetupStep.DEPLOY_ARMIES.value,
            "player_id": requested_player_id,
            "deployment_order_policy": DeploymentOrderPolicy.core_rules().policy_kind.value,
            "mission_pack_id": mission_setup.mission_pack_id,
            "deployment_map_id": mission_setup.deployment_map_id,
            "terrain_layout_id": mission_setup.terrain_layout_id,
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
            "deployment_zone_ids": cast(JsonValue, [zone.deployment_zone_id for zone in zones]),
            "deployment_zones": cast(JsonValue, [zone.to_payload() for zone in zones]),
        },
        options=tuple(
            DecisionOption(
                option_id=f"deploy:{view.unit_instance_id}",
                label=f"Deploy {view.unit_instance_id}",
                payload=_deployment_unit_selection_payload(
                    state=state,
                    ruleset_descriptor=ruleset_descriptor,
                    mission_setup=mission_setup,
                    zones=zones,
                    view=view,
                ),
            )
            for view in views
        ),
    )
    if not request.options:
        raise GameLifecycleError("Deployment unit selection request requires options.")
    return request


def deployment_unit_views_for_player(
    *,
    state: GameState,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Deployment unit options require GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Deployment unit options require a mustered army.")
    unavailable_component_ids = _unavailable_component_unit_ids(state)
    deployed_component_ids = _deployed_component_unit_ids(state)
    removed_model_ids = set(
        () if state.battlefield_state is None else state.battlefield_state.removed_model_ids
    )
    views = _rules_unit_views_for_army(state=state, player_id=requested_player_id)
    available: list[RulesUnitView] = []
    for view in views:
        component_ids = set(view.component_unit_instance_ids)
        if component_ids & unavailable_component_ids:
            continue
        if component_ids & deployed_component_ids:
            continue
        if any(model.model_instance_id in removed_model_ids for model in view.alive_models()):
            continue
        available.append(view)
    return tuple(sorted(available, key=lambda view: view.unit_instance_id))


def deployment_placement_request_from_selection(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    selection_request: DecisionRequest,
    result: DecisionResult,
) -> DeploymentPlacementRequest:
    if result.decision_type != SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
        raise GameLifecycleError("Deployment placement request requires unit selection.")
    if result.actor_id is None:
        raise GameLifecycleError("Deployment unit selection requires actor_id.")
    if not isinstance(result.payload, dict):
        raise GameLifecycleError("Deployment unit selection payload must be an object.")
    unit_instance_id = _payload_string(result.payload, "unit_instance_id")
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    if view.owner_player_id != result.actor_id:
        raise GameLifecycleError("Deployment unit selection owner drift.")
    mission_setup = _require_mission_setup(state)
    return DeploymentPlacementRequest(
        request_id=state.next_decision_request_id(),
        actor_id=result.actor_id,
        game_id=state.game_id,
        player_id=result.actor_id,
        unit_instance_id=view.unit_instance_id,
        component_unit_instance_ids=view.component_unit_instance_ids,
        model_instance_ids=tuple(model.model_instance_id for model in view.alive_models()),
        deployment_zones=_deployment_zones_for_player(mission_setup, result.actor_id),
        mission_setup=mission_setup,
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        source_decision_request_id=selection_request.request_id,
        source_decision_result_id=result.result_id,
        context={
            "is_attached_rules_unit": view.is_attached_rules_unit,
            "source_rule_id": DEPLOY_ARMIES_SOURCE_RULE_ID,
        },
    )


def is_deployment_placement_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Deployment request check requires DecisionRequest.")
    return request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE


def invalid_deployment_placement_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    if not is_deployment_placement_request(request):
        return None
    result.validate_for_request(request)
    try:
        request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
        proposal = DeploymentPlacementProposal.from_payload(
            cast(DeploymentPlacementProposalPayload, result.payload)
        )
    except (
        KeyError,
        TypeError,
        DeploymentZoneError,
        GameLifecycleError,
        MissionSetupError,
        PlacementError,
    ) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Deployment placement submission is malformed.",
            payload={
                "invalid_reason": "malformed_deployment_placement",
                "detail": str(exc),
                "request_id": request.request_id,
            },
        )
    drift_violations = proposal.request_drift_violations(request_context)
    if drift_violations:
        return _invalid_deployment_status(
            state=state,
            request_id=request.request_id,
            invalid_reason="deployment_request_drift",
            violations=drift_violations,
            resolution=None,
        )
    resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        request=request_context,
        proposal=proposal,
    )
    if not resolution.is_valid:
        return _invalid_deployment_status(
            state=state,
            request_id=request.request_id,
            invalid_reason="deployment_placement_invalid",
            violations=resolution.violations,
            resolution=resolution,
        )
    return None


def apply_deployment_placement(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> DeploymentPlacementResolution:
    if not is_deployment_placement_request(request):
        raise GameLifecycleError("Deployment placement apply requires deployment request.")
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
    proposal = DeploymentPlacementProposal.from_payload(
        cast(DeploymentPlacementProposalPayload, result.payload)
    )
    resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        request=request_context,
        proposal=proposal,
        source_event_id=result.result_id,
    )
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid deployment placement cannot mutate state.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Deployment placement requires battlefield_state.")
    battlefield = state.battlefield_state
    for unit_placement in proposal.grouped_unit_placements():
        battlefield = battlefield.with_added_unit_placement(unit_placement)
    state.replace_battlefield_state(battlefield)
    return resolution


def resolve_deployment_placement(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    request: DeploymentPlacementRequest,
    proposal: DeploymentPlacementProposal,
    source_event_id: str | None = None,
) -> DeploymentPlacementResolution:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Deployment placement requires RulesetDescriptor.")
    placement_source_event_id = (
        request.source_decision_result_id
        if source_event_id is None
        else _validate_identifier("source_event_id", source_event_id)
    )
    _validate_deployment_state(state)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=_require_battlefield_state(state),
    )
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=request.unit_instance_id,
    )
    model_by_id = {model.model_instance_id: model for model in view.alive_models()}
    placement_by_id = {
        placement.model_instance_id: placement for placement in proposal.model_placements
    }
    violations: list[DeploymentPlacementViolation] = []
    _append_unit_availability_violations(
        violations=violations,
        state=state,
        view=view,
        player_id=request.player_id,
    )
    expected_model_ids = tuple(sorted(model_by_id))
    submitted_model_ids = tuple(sorted(placement_by_id))
    if submitted_model_ids != expected_model_ids:
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.MODEL_SET_DRIFT,
                message="Deployment placement must include every alive model in the rules unit.",
                field="model_placements",
            )
        )
    models: list[Model] = []
    for placement in proposal.model_placements:
        model = model_by_id.get(placement.model_instance_id)
        if model is None:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.WRONG_UNIT_MODEL,
                    message="Deployment placement model is not in the selected rules unit.",
                    field="model_placements",
                    model_instance_id=placement.model_instance_id,
                )
            )
            continue
        if placement.player_id != request.player_id:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.PLAYER_DRIFT,
                    message="Deployment placement model player does not match request.",
                    field="model_placements",
                    model_instance_id=placement.model_instance_id,
                )
            )
        if placement.unit_instance_id not in view.component_unit_instance_ids:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.WRONG_UNIT_MODEL,
                    message="Deployment placement component unit is not in the rules unit.",
                    field="model_placements",
                    model_instance_id=placement.model_instance_id,
                    blocker_id=placement.unit_instance_id,
                )
            )
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    geometry_models = tuple(models)
    coherency_result = UnitCoherencyContext.from_ruleset_descriptor(
        ruleset_descriptor,
        unit_instance_id=request.unit_instance_id,
    ).validate_models(geometry_models)
    if not coherency_result.is_coherent:
        for model_id in coherency_result.offending_model_instance_ids:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.UNIT_COHERENCY_BROKEN,
                    message="Deployment placement breaks unit coherency.",
                    field="model_placements",
                    model_instance_id=model_id,
                )
            )
    _append_geometry_violations(
        violations=violations,
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        view=view,
        models=geometry_models,
        deployment_zones=request.deployment_zones,
    )
    transition_batch = None
    if not violations:
        transition_batch = BattlefieldTransitionBatch(
            placements=tuple(
                ModelPlacementRecord(
                    model_instance_id=placement.model_instance_id,
                    placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
                    pose=placement.pose,
                    source_phase=None,
                    source_step=SetupStep.DEPLOY_ARMIES.value,
                    source_rule_id=DEPLOY_ARMIES_SOURCE_RULE_ID,
                    source_event_id=placement_source_event_id,
                )
                for placement in proposal.model_placements
            )
        )
    return DeploymentPlacementResolution(
        proposal=proposal,
        violations=tuple(violations),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
    )


def deployment_completion_accounted_model_ids(state: GameState) -> tuple[str, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Deployment completion requires GameState.")
    return state.unavailable_model_ids()


def _deployment_unit_selection_payload(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    mission_setup: MissionSetup,
    zones: tuple[DeploymentZone, ...],
    view: RulesUnitView,
) -> JsonValue:
    payload: DeploymentUnitSelectionPayload = {
        "submission_kind": SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        "game_id": state.game_id,
        "player_id": view.owner_player_id,
        "setup_step": SetupStep.DEPLOY_ARMIES.value,
        "unit_instance_id": view.unit_instance_id,
        "is_attached_rules_unit": view.is_attached_rules_unit,
        "component_unit_instance_ids": list(view.component_unit_instance_ids),
        "model_instance_ids": [model.model_instance_id for model in view.alive_models()],
        "deployment_zone_ids": [zone.deployment_zone_id for zone in zones],
        "mission_pack_id": mission_setup.mission_pack_id,
        "deployment_map_id": mission_setup.deployment_map_id,
        "terrain_layout_id": mission_setup.terrain_layout_id,
        "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
    }
    return validate_json_value(payload)


def _append_unit_availability_violations(
    *,
    violations: list[DeploymentPlacementViolation],
    state: GameState,
    view: RulesUnitView,
    player_id: str,
) -> None:
    if view.owner_player_id != player_id:
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.PLAYER_DRIFT,
                message="Selected deployment unit belongs to another player.",
                field="unit_instance_id",
                blocker_id=view.owner_player_id,
            )
        )
    available_ids = {
        candidate.unit_instance_id
        for candidate in deployment_unit_views_for_player(state=state, player_id=player_id)
    }
    if view.unit_instance_id not in available_ids:
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.UNIT_NOT_DEPLOYABLE,
                message="Selected unit is not currently deployable.",
                field="unit_instance_id",
                blocker_id=view.unit_instance_id,
            )
        )


def _append_geometry_violations(
    *,
    violations: list[DeploymentPlacementViolation],
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
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    markers = tuple(marker.to_objective_marker() for marker in mission_setup.objective_markers)
    all_infiltrators = _rules_unit_has_infiltrators(view)
    any_outside_zone = False
    for model in models:
        if not _model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        ):
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Deployment placement crosses the battlefield edge.",
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
                    DeploymentPlacementViolation(
                        violation_code=DeploymentPlacementViolationCode.MODEL_OVERLAP,
                        message="Deployment placement overlaps another model.",
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
                    DeploymentPlacementViolation(
                        violation_code=DeploymentPlacementViolationCode.ENEMY_ENGAGEMENT_RANGE,
                        message="Deployment placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
            if all_infiltrators and model.base_distance_to(enemy_model) <= (
                _INFILTRATORS_DISTANCE_INCHES + _EPSILON
            ):
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=(
                            DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_UNIT_DISTANCE
                        ),
                        message="INFILTRATORS deployment must be more than 8 inches from enemies.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=_unit_for_model(view=view, model_instance_id=model.model_id),
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=battlefield_state.terrain_features,
            violation_code=DeploymentPlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Deployment placement",
        )
        if terrain_violation is not None:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
                    message=terrain_violation.message,
                    model_instance_id=terrain_violation.model_instance_id,
                    blocker_id=terrain_violation.blocker_id,
                )
            )
        objective_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=markers,
            violation_code=(
                DeploymentPlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value
            ),
            placement_label="Deployment placement",
        )
        if objective_violation is not None:
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=(
                        DeploymentPlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP
                    ),
                    message=objective_violation.message,
                    model_instance_id=objective_violation.model_instance_id,
                    blocker_id=objective_violation.blocker_id,
                )
            )
    overlap = _moving_models_overlap(models)
    if overlap is not None:
        first_id, second_id = overlap
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.MODEL_OVERLAP,
                message="Deployment placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )
    if any_outside_zone and not all_infiltrators:
        violations.append(
            DeploymentPlacementViolation(
                violation_code=DeploymentPlacementViolationCode.DEPLOYMENT_ZONE_VIOLATION,
                message="Deployment placement must be wholly within the player's deployment zone.",
                field="model_placements",
            )
        )
        if _rules_unit_has_mixed_infiltrators(view):
            violations.append(
                DeploymentPlacementViolation(
                    violation_code=DeploymentPlacementViolationCode.INFILTRATORS_KEYWORD_REQUIRED,
                    message=(
                        "INFILTRATORS deployment requires every component unit to have the ability."
                    ),
                    field="unit_instance_id",
                )
            )
    if all_infiltrators:
        _append_infiltrator_enemy_zone_violations(
            violations=violations,
            state=state,
            models=models,
        )
    if _rules_unit_has_keyword(view, "FORTIFICATION"):
        violations.append(
            DeploymentPlacementViolation(
                violation_code=(
                    DeploymentPlacementViolationCode.FORTIFICATION_DEPLOYMENT_UNSUPPORTED
                ),
                message="Fortification deployment restrictions are not yet source-backed.",
                field="unit_instance_id",
            )
        )


def _append_infiltrator_enemy_zone_violations(
    *,
    violations: list[DeploymentPlacementViolation],
    state: GameState,
    models: tuple[Model, ...],
) -> None:
    mission_setup = _require_mission_setup(state)
    for model in models:
        for zone in mission_setup.enemy_deployment_zones_for_player(
            _model_owner_player_id_from_state(state=state, model_instance_id=model.model_id)
        ):
            distance = shapely_backend.base_footprint_distance_to_deployment_zone(
                model.base,
                model.pose,
                zone,
            )
            if distance <= _INFILTRATORS_DISTANCE_INCHES + _EPSILON:
                violations.append(
                    DeploymentPlacementViolation(
                        violation_code=(
                            DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_ZONE_DISTANCE
                        ),
                        message=(
                            "INFILTRATORS deployment must be more than 8 inches from the "
                            "enemy deployment zone."
                        ),
                        model_instance_id=model.model_id,
                        blocker_id=zone.deployment_zone_id,
                    )
                )


def _invalid_deployment_status(
    *,
    state: GameState,
    request_id: str,
    invalid_reason: str,
    violations: tuple[DeploymentPlacementViolation, ...],
    resolution: DeploymentPlacementResolution | None,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Deployment placement submission is invalid.",
        payload={
            "invalid_reason": invalid_reason,
            "request_id": request_id,
            "violations": cast(
                JsonValue,
                [violation.to_payload() for violation in violations],
            ),
            "resolution": cast(
                JsonValue,
                None if resolution is None else resolution.to_payload(),
            ),
        },
    )


def _rules_unit_views_for_army(*, state: GameState, player_id: str) -> tuple[RulesUnitView, ...]:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise GameLifecycleError("Deployment requires a mustered army.")
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


def _deployed_rules_unit_count_by_player(state: GameState) -> dict[str, int]:
    if state.battlefield_state is None:
        return dict.fromkeys(state.player_ids, 0)
    by_player: dict[str, set[str]] = {player_id: set() for player_id in state.player_ids}
    for placed_army in state.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=tuple(state.army_definitions),
                unit_instance_id=unit_placement.unit_instance_id,
            )
            by_player.setdefault(placed_army.player_id, set()).add(rules_unit_id)
    return {player_id: len(unit_ids) for player_id, unit_ids in by_player.items()}


def _deployed_component_unit_ids(state: GameState) -> set[str]:
    if state.battlefield_state is None:
        return set()
    return {
        unit_placement.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    }


def _unavailable_component_unit_ids(state: GameState) -> set[str]:
    unavailable = {
        reserve_state.unit_instance_id
        for reserve_state in state.reserve_states
        if reserve_state.is_unarrived
    }
    for reserve_state in state.reserve_states:
        if reserve_state.is_unarrived:
            unavailable.update(reserve_state.embarked_unit_instance_ids)
    for cargo_state in state.transport_cargo_states:
        unavailable.update(cargo_state.embarked_unit_instance_ids)
    unavailable.update(
        consequence.transport_unit_instance_id
        for consequence in state.dedicated_transport_setup_consequences
    )
    return unavailable


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


def _model_owner_player_id_from_state(*, state: GameState, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == requested_model_id for model in unit.own_models):
                return army.player_id
    raise GameLifecycleError("model_instance_id is unknown.")


def _unit_for_model(*, view: RulesUnitView, model_instance_id: str) -> UnitInstance:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for component in view.components:
        if any(
            model.model_instance_id == requested_model_id for model in component.unit.own_models
        ):
            return component.unit
    raise GameLifecycleError("model_instance_id is not in the rules unit.")


def _rules_unit_has_infiltrators(view: RulesUnitView) -> bool:
    return all(unit_has_infiltrators(component.unit) for component in view.components)


def _rules_unit_has_mixed_infiltrators(view: RulesUnitView) -> bool:
    states = tuple(unit_has_infiltrators(component.unit) for component in view.components)
    return any(states) and not all(states)


def _rules_unit_has_keyword(view: RulesUnitView, keyword: str) -> bool:
    return any(_unit_has_keyword(component.unit, keyword) for component in view.components)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested = _canonical_keyword(keyword)
    return requested in {_canonical_keyword(value) for value in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).upper().replace(" ", "_").replace("-", "_")


def _validate_deployment_state(state: GameState) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Deployment placement requires GameState.")
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Deployment placement requires setup stage.")
    if state.current_setup_step is not SetupStep.DEPLOY_ARMIES:
        raise GameLifecycleError("Deployment placement requires DEPLOY_ARMIES.")
    _require_mission_setup(state)
    _require_battlefield_state(state)


def _require_mission_setup(state: GameState) -> MissionSetup:
    if state.mission_setup is None:
        raise GameLifecycleError("Deployment requires source-backed MissionSetup.")
    return state.mission_setup


def _require_battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise GameLifecycleError("Deployment requires battlefield_state.")
    return state.battlefield_state


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


def _validate_deployment_placement_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[DeploymentPlacementViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    violations: list[DeploymentPlacementViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeploymentPlacementViolation:
            raise GameLifecycleError(
                f"{field_name} must contain DeploymentPlacementViolation values."
            )
        violations.append(value)
    return tuple(violations)


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


def _validate_deployment_proposal_kind(value: object) -> str:
    kind = _validate_identifier("deployment proposal kind", value)
    if kind != DEPLOYMENT_PROPOSAL_KIND:
        raise GameLifecycleError(f"Unsupported deployment proposal kind: {kind}.")
    return kind


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_non_empty_string(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Deployment payload {key} must be a string.")
    return value


def _setup_step_from_token(token: object) -> SetupStep:
    if type(token) is SetupStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SetupStep token must be a string.")
    try:
        return SetupStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SetupStep token: {token}.") from exc
