from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptorError,
    movement_mode_from_token,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    UnitPlacement,
    UnitPlacementPayload,
    battlefield_placement_kind_from_token,
)
from warhammer40k_core.engine.decision_request import (
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import (
    LargeModelReservePlacementException,
    LargeModelReservePlacementExceptionPayload,
)
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverridePayload,
    disembark_mode_kind_from_token,
    transport_movement_status_from_token,
)
from warhammer40k_core.geometry.pathing import PathWitness, PathWitnessPayload

MOVEMENT_PROPOSAL_DECISION_TYPE = "submit_movement_proposal"
PLACEMENT_PROPOSAL_DECISION_TYPE = "submit_placement_proposal"


class ProposalKind(StrEnum):
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"
    REINFORCEMENT = "reinforcement_placement"
    DEEP_STRIKE = "deep_strike_placement"
    STRATEGIC_RESERVES = "strategic_reserves_placement"
    DISEMBARK = "disembark_placement"


class ProposalViolationPayload(TypedDict):
    violation_code: str
    message: str
    field: str | None


class ProposalValidationResultPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    is_valid: bool
    status: str
    violations: list[ProposalViolationPayload]


class MovementProposalRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    battle_round: int
    phase: str
    unit_instance_id: str
    proposal_kind: str
    source_decision_request_id: str
    source_decision_result_id: str
    movement_phase_action: str | None
    placement_kinds: list[str]
    context: dict[str, JsonValue]


class DecisionRequestProposalPayload(TypedDict):
    proposal_request: MovementProposalRequestPayload


class ModelMovementProposalPayload(TypedDict):
    model_instance_id: str
    path: list[JsonValue]
    final_pose: JsonValue


class MovementProposalPayloadPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: NotRequired[str]
    fall_back_mode: NotRequired[str]
    witness: PathWitnessPayload
    model_movements: NotRequired[list[ModelMovementProposalPayload]]


class PlacementProposalPayloadPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    unit_instance_id: str
    placement_kind: str
    attempted_placement: UnitPlacementPayload
    large_model_exceptions: NotRequired[list[LargeModelReservePlacementExceptionPayload]]
    transport_unit_instance_id: NotRequired[str]
    disembark_mode: NotRequired[str]
    transport_movement_status: NotRequired[str]
    restriction_overrides: NotRequired[list[TransportRestrictionOverridePayload]]


@dataclass(frozen=True, slots=True)
class ProposalViolation:
    violation_code: str
    message: str
    field: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("ProposalViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_non_empty_string("ProposalViolation message", self.message),
        )
        object.__setattr__(
            self,
            "field",
            _validate_optional_identifier("ProposalViolation field", self.field),
        )

    def to_payload(self) -> ProposalViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "field": self.field,
        }

    @classmethod
    def from_payload(cls, payload: ProposalViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            field=payload["field"],
        )


@dataclass(frozen=True, slots=True)
class ProposalValidationResult:
    proposal_request_id: str
    proposal_kind: ProposalKind
    is_valid: bool
    status: str
    violations: tuple[ProposalViolation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ProposalValidationResult proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            proposal_kind_from_token(self.proposal_kind),
        )
        if type(self.is_valid) is not bool:
            raise GameLifecycleError("ProposalValidationResult is_valid must be a bool.")
        object.__setattr__(
            self,
            "status",
            _validate_identifier("ProposalValidationResult status", self.status),
        )
        object.__setattr__(
            self,
            "violations",
            _validate_proposal_violations(
                "ProposalValidationResult violations",
                self.violations,
            ),
        )
        if self.is_valid and self.violations:
            raise GameLifecycleError("Valid ProposalValidationResult must not include violations.")
        if not self.is_valid and not self.violations:
            raise GameLifecycleError("Invalid ProposalValidationResult requires violations.")

    @classmethod
    def valid(cls, *, proposal_request_id: str, proposal_kind: ProposalKind) -> Self:
        return cls(
            proposal_request_id=proposal_request_id,
            proposal_kind=proposal_kind,
            is_valid=True,
            status="valid",
        )

    @classmethod
    def invalid(
        cls,
        *,
        proposal_request_id: str,
        proposal_kind: ProposalKind,
        violation_code: str,
        message: str,
        field: str | None = None,
        status: str = "invalid",
    ) -> Self:
        return cls(
            proposal_request_id=proposal_request_id,
            proposal_kind=proposal_kind,
            is_valid=False,
            status=status,
            violations=(
                ProposalViolation(
                    violation_code=violation_code,
                    message=message,
                    field=field,
                ),
            ),
        )

    def to_payload(self) -> ProposalValidationResultPayload:
        return {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind.value,
            "is_valid": self.is_valid,
            "status": self.status,
            "violations": [violation.to_payload() for violation in self.violations],
        }

    @classmethod
    def from_payload(cls, payload: ProposalValidationResultPayload) -> Self:
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=proposal_kind_from_token(payload["proposal_kind"]),
            is_valid=payload["is_valid"],
            status=payload["status"],
            violations=tuple(
                ProposalViolation.from_payload(violation) for violation in payload["violations"]
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementProposalRequest:
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    battle_round: int
    phase: str
    unit_instance_id: str
    proposal_kind: ProposalKind
    source_decision_request_id: str
    source_decision_result_id: str
    movement_phase_action: str | None = None
    placement_kinds: tuple[BattlefieldPlacementKind, ...] = ()
    context: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("MovementProposalRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "decision_type",
            _validate_proposal_decision_type(self.decision_type),
        )
        object.__setattr__(
            self,
            "actor_id",
            _validate_identifier("MovementProposalRequest actor_id", self.actor_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("MovementProposalRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementProposalRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("MovementProposalRequest phase", self.phase),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "MovementProposalRequest unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            proposal_kind_from_token(self.proposal_kind),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "MovementProposalRequest source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "MovementProposalRequest source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            _validate_optional_identifier(
                "MovementProposalRequest movement_phase_action",
                self.movement_phase_action,
            ),
        )
        placement_kinds = _validate_placement_kind_tuple(
            "MovementProposalRequest placement_kinds",
            self.placement_kinds,
        )
        object.__setattr__(self, "placement_kinds", placement_kinds)
        context: dict[str, JsonValue] = {} if self.context is None else self.context
        context_payload = validate_json_value(context)
        if not isinstance(context_payload, dict):
            raise GameLifecycleError("MovementProposalRequest context must be a JSON object.")
        object.__setattr__(self, "context", context_payload)
        if self.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            if self.movement_phase_action is None:
                raise GameLifecycleError(
                    "Movement proposal requests require movement_phase_action."
                )
            if self.placement_kinds:
                raise GameLifecycleError(
                    "Movement proposal requests must not include placement_kinds."
                )
        if self.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE and not self.placement_kinds:
            raise GameLifecycleError("Placement proposal requests require placement_kinds.")

    def to_decision_request(self) -> DecisionRequest:
        return DecisionRequest(
            request_id=self.request_id,
            decision_type=self.decision_type,
            actor_id=self.actor_id,
            payload={"proposal_request": validate_json_value(self.to_payload())},
            options=(parameterized_decision_option(),),
        )

    def to_payload(self) -> MovementProposalRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "actor_id": self.actor_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "unit_instance_id": self.unit_instance_id,
            "proposal_kind": self.proposal_kind.value,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "movement_phase_action": self.movement_phase_action,
            "placement_kinds": [placement_kind.value for placement_kind in self.placement_kinds],
            "context": dict(self.context or {}),
        }

    @classmethod
    def from_payload(cls, payload: MovementProposalRequestPayload) -> Self:
        return cls(
            request_id=payload["request_id"],
            decision_type=payload["decision_type"],
            actor_id=payload["actor_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            unit_instance_id=payload["unit_instance_id"],
            proposal_kind=proposal_kind_from_token(payload["proposal_kind"]),
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            movement_phase_action=payload["movement_phase_action"],
            placement_kinds=tuple(
                battlefield_placement_kind_from_token(kind) for kind in payload["placement_kinds"]
            ),
            context=payload["context"],
        )

    @classmethod
    def from_decision_request_payload(cls, payload: object) -> Self:
        json_payload = validate_json_value(payload)
        if not isinstance(json_payload, dict):
            raise GameLifecycleError("Proposal DecisionRequest payload must be an object.")
        proposal_payload = json_payload.get("proposal_request")
        if not isinstance(proposal_payload, dict):
            raise GameLifecycleError("Proposal DecisionRequest payload missing proposal_request.")
        return cls.from_payload(cast(MovementProposalRequestPayload, proposal_payload))


@dataclass(frozen=True, slots=True)
class MovementProposalPayload:
    proposal_request_id: str
    proposal_kind: ProposalKind
    unit_instance_id: str
    movement_phase_action: str
    witness: PathWitness
    movement_mode: str | None = None
    fall_back_mode: str | None = None
    model_movements: tuple[ModelMovementProposalPayload, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "MovementProposalPayload proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            proposal_kind_from_token(self.proposal_kind),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementProposalPayload unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            _validate_identifier(
                "MovementProposalPayload movement_phase_action",
                self.movement_phase_action,
            ),
        )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("MovementProposalPayload witness must be a PathWitness.")
        if self.movement_mode is not None:
            try:
                movement_mode = movement_mode_from_token(self.movement_mode)
            except RulesetDescriptorError as exc:
                raise GameLifecycleError(
                    "MovementProposalPayload movement_mode is unsupported."
                ) from exc
            object.__setattr__(
                self,
                "movement_mode",
                movement_mode.value,
            )
        object.__setattr__(
            self,
            "fall_back_mode",
            _validate_optional_identifier(
                "MovementProposalPayload fall_back_mode",
                self.fall_back_mode,
            ),
        )
        object.__setattr__(
            self,
            "model_movements",
            _validate_model_movement_payloads(self.model_movements),
        )

    def validation_result_for_request(
        self,
        request: MovementProposalRequest,
    ) -> ProposalValidationResult:
        if type(request) is not MovementProposalRequest:
            raise GameLifecycleError("Movement proposal validation requires a request.")
        if self.proposal_request_id != request.request_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="stale_proposal_request",
                message="Movement proposal request_id does not match the pending request.",
                field="proposal_request_id",
                status="stale",
            )
        if self.proposal_kind is not request.proposal_kind:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_kind_drift",
                message="Movement proposal kind does not match the pending request.",
                field="proposal_kind",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_unit_drift",
                message="Movement proposal unit does not match the pending request.",
                field="unit_instance_id",
            )
        if self.movement_phase_action != request.movement_phase_action:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_action_drift",
                message="Movement proposal action does not match the pending request.",
                field="movement_phase_action",
            )
        movement_mode_result = _movement_proposal_context_match(
            request=request,
            submitted_value=self.movement_mode,
            context_key="movement_mode",
            violation_code="proposal_movement_mode_drift",
            message="Movement proposal mode does not match the pending request.",
        )
        if movement_mode_result is not None:
            return movement_mode_result
        fall_back_mode_result = _movement_proposal_context_match(
            request=request,
            submitted_value=self.fall_back_mode,
            context_key="fall_back_mode",
            violation_code="proposal_fall_back_mode_drift",
            message="Movement proposal Fall Back mode does not match the pending request.",
        )
        if fall_back_mode_result is not None:
            return fall_back_mode_result
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )

    def to_payload(self) -> MovementProposalPayloadPayload:
        payload: MovementProposalPayloadPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind.value,
            "unit_instance_id": self.unit_instance_id,
            "movement_phase_action": self.movement_phase_action,
            "witness": self.witness.to_payload(),
        }
        if self.movement_mode is not None:
            payload["movement_mode"] = self.movement_mode
        if self.fall_back_mode is not None:
            payload["fall_back_mode"] = self.fall_back_mode
        if self.model_movements:
            payload["model_movements"] = list(self.model_movements)
        return payload

    @classmethod
    def from_payload(cls, payload: MovementProposalPayloadPayload) -> Self:
        model_movements = payload.get("model_movements")
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=proposal_kind_from_token(payload["proposal_kind"]),
            unit_instance_id=payload["unit_instance_id"],
            movement_phase_action=payload["movement_phase_action"],
            witness=PathWitness.from_payload(payload["witness"]),
            movement_mode=payload.get("movement_mode"),
            fall_back_mode=payload.get("fall_back_mode"),
            model_movements=() if model_movements is None else tuple(model_movements),
        )


@dataclass(frozen=True, slots=True)
class PlacementProposalPayload:
    proposal_request_id: str
    proposal_kind: ProposalKind
    unit_instance_id: str
    placement_kind: BattlefieldPlacementKind
    attempted_placement: UnitPlacement
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...] = ()
    transport_unit_instance_id: str | None = None
    disembark_mode: DisembarkModeKind | None = None
    transport_movement_status: TransportMovementStatus | None = None
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "PlacementProposalPayload proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            proposal_kind_from_token(self.proposal_kind),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "PlacementProposalPayload unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "PlacementProposalPayload attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("PlacementProposalPayload attempted_placement unit drift.")
        object.__setattr__(
            self,
            "large_model_exceptions",
            _validate_large_model_exception_tuple(
                "PlacementProposalPayload large_model_exceptions",
                self.large_model_exceptions,
            ),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_optional_identifier(
                "PlacementProposalPayload transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        if self.disembark_mode is not None:
            object.__setattr__(
                self,
                "disembark_mode",
                disembark_mode_kind_from_token(self.disembark_mode),
            )
        if self.transport_movement_status is not None:
            object.__setattr__(
                self,
                "transport_movement_status",
                transport_movement_status_from_token(self.transport_movement_status),
            )
        object.__setattr__(
            self,
            "restriction_overrides",
            _validate_transport_override_tuple(
                "PlacementProposalPayload restriction_overrides",
                self.restriction_overrides,
            ),
        )

    def validation_result_for_request(
        self,
        request: MovementProposalRequest,
    ) -> ProposalValidationResult:
        if type(request) is not MovementProposalRequest:
            raise GameLifecycleError("Placement proposal validation requires a request.")
        if self.proposal_request_id != request.request_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="stale_proposal_request",
                message="Placement proposal request_id does not match the pending request.",
                field="proposal_request_id",
                status="stale",
            )
        if self.proposal_kind is not request.proposal_kind:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_kind_drift",
                message="Placement proposal kind does not match the pending request.",
                field="proposal_kind",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_unit_drift",
                message="Placement proposal unit does not match the pending request.",
                field="unit_instance_id",
            )
        if self.placement_kind not in request.placement_kinds:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_placement_kind_drift",
                message="Placement kind is not allowed by the pending request.",
                field="placement_kind",
            )
        disembark_mode_result = _placement_proposal_context_match(
            request=request,
            submitted_value=None if self.disembark_mode is None else self.disembark_mode.value,
            context_key="disembark_mode",
            violation_code="proposal_disembark_mode_drift",
            message="Disembark proposal mode does not match the pending request.",
        )
        if disembark_mode_result is not None:
            return disembark_mode_result
        transport_status_result = _placement_proposal_context_match(
            request=request,
            submitted_value=None
            if self.transport_movement_status is None
            else self.transport_movement_status.value,
            context_key="transport_movement_status",
            violation_code="proposal_transport_movement_status_drift",
            message=(
                "Disembark proposal transport movement status does not match the pending request."
            ),
        )
        if transport_status_result is not None:
            return transport_status_result
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )

    def to_payload(self) -> PlacementProposalPayloadPayload:
        payload: PlacementProposalPayloadPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind.value,
            "unit_instance_id": self.unit_instance_id,
            "placement_kind": self.placement_kind.value,
            "attempted_placement": self.attempted_placement.to_payload(),
        }
        if self.large_model_exceptions:
            payload["large_model_exceptions"] = [
                exception.to_payload() for exception in self.large_model_exceptions
            ]
        if self.transport_unit_instance_id is not None:
            payload["transport_unit_instance_id"] = self.transport_unit_instance_id
        if self.disembark_mode is not None:
            payload["disembark_mode"] = self.disembark_mode.value
        if self.transport_movement_status is not None:
            payload["transport_movement_status"] = self.transport_movement_status.value
        if self.restriction_overrides:
            payload["restriction_overrides"] = [
                override.to_payload() for override in self.restriction_overrides
            ]
        return payload

    @classmethod
    def from_payload(cls, payload: PlacementProposalPayloadPayload) -> Self:
        large_exceptions_payload = payload.get("large_model_exceptions")
        disembark_mode_payload = payload.get("disembark_mode")
        movement_status_payload = payload.get("transport_movement_status")
        overrides_payload = payload.get("restriction_overrides")
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=proposal_kind_from_token(payload["proposal_kind"]),
            unit_instance_id=payload["unit_instance_id"],
            placement_kind=battlefield_placement_kind_from_token(payload["placement_kind"]),
            attempted_placement=UnitPlacement.from_payload(payload["attempted_placement"]),
            large_model_exceptions=()
            if large_exceptions_payload is None
            else tuple(
                LargeModelReservePlacementException.from_payload(exception)
                for exception in large_exceptions_payload
            ),
            transport_unit_instance_id=payload.get("transport_unit_instance_id"),
            disembark_mode=None
            if disembark_mode_payload is None
            else disembark_mode_kind_from_token(disembark_mode_payload),
            transport_movement_status=None
            if movement_status_payload is None
            else transport_movement_status_from_token(movement_status_payload),
            restriction_overrides=()
            if overrides_payload is None
            else tuple(
                TransportRestrictionOverride.from_payload(override)
                for override in overrides_payload
            ),
        )


def proposal_kind_from_token(token: object) -> ProposalKind:
    if type(token) is ProposalKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ProposalKind token must be a string.")
    try:
        return ProposalKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ProposalKind token: {token}.") from exc


def _validate_proposal_decision_type(value: object) -> str:
    decision_type = _validate_identifier("MovementProposalRequest decision_type", value)
    if decision_type not in {MOVEMENT_PROPOSAL_DECISION_TYPE, PLACEMENT_PROPOSAL_DECISION_TYPE}:
        raise GameLifecycleError(f"Unsupported proposal decision_type: {decision_type}.")
    return decision_type


def _movement_proposal_context_match(
    *,
    request: MovementProposalRequest,
    submitted_value: str | None,
    context_key: str,
    violation_code: str,
    message: str,
) -> ProposalValidationResult | None:
    context = request.context or {}
    expected = context.get(context_key)
    if expected is None:
        if submitted_value is None:
            return None
        return ProposalValidationResult.invalid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            violation_code=violation_code,
            message=message,
            field=context_key,
        )
    if type(expected) is not str:
        raise GameLifecycleError(f"Movement proposal context {context_key} must be a string.")
    if submitted_value != expected:
        return ProposalValidationResult.invalid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            violation_code=violation_code,
            message=message,
            field=context_key,
        )
    return None


def _placement_proposal_context_match(
    *,
    request: MovementProposalRequest,
    submitted_value: str | None,
    context_key: str,
    violation_code: str,
    message: str,
) -> ProposalValidationResult | None:
    context = request.context or {}
    expected = context.get(context_key)
    if expected is None:
        if submitted_value is None:
            return None
        return ProposalValidationResult.invalid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            violation_code=violation_code,
            message=message,
            field=context_key,
        )
    if type(expected) is not str:
        raise GameLifecycleError(f"Placement proposal context {context_key} must be a string.")
    if submitted_value != expected:
        return ProposalValidationResult.invalid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            violation_code=violation_code,
            message=message,
            field=context_key,
        )
    return None


def _validate_proposal_violations(
    field_name: str,
    values: object,
) -> tuple[ProposalViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    violations: list[ProposalViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not ProposalViolation:
            raise GameLifecycleError(f"{field_name} must contain ProposalViolation values.")
        violations.append(value)
    return tuple(violations)


def _validate_placement_kind_tuple(
    field_name: str,
    values: object,
) -> tuple[BattlefieldPlacementKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    placement_kinds = tuple(
        battlefield_placement_kind_from_token(value) for value in cast(tuple[object, ...], values)
    )
    if len(set(placement_kinds)) != len(placement_kinds):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(placement_kinds, key=lambda kind: kind.value))


def _validate_model_movement_payloads(
    values: object,
) -> tuple[ModelMovementProposalPayload, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MovementProposalPayload model_movements must be a tuple.")
    validated: list[ModelMovementProposalPayload] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        json_value = validate_json_value(value)
        if not isinstance(json_value, dict):
            raise GameLifecycleError(
                "MovementProposalPayload model_movements must contain objects."
            )
        model_id = json_value.get("model_instance_id")
        if type(model_id) is not str or not model_id.strip():
            raise GameLifecycleError(
                "MovementProposalPayload model_movements require model_instance_id."
            )
        if model_id in seen:
            raise GameLifecycleError(
                "MovementProposalPayload model_movements must not contain duplicates."
            )
        seen.add(model_id)
        validated.append(cast(ModelMovementProposalPayload, json_value))
    return tuple(validated)


def _validate_large_model_exception_tuple(
    field_name: str,
    values: object,
) -> tuple[LargeModelReservePlacementException, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    exceptions: list[LargeModelReservePlacementException] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not LargeModelReservePlacementException:
            raise GameLifecycleError(
                f"{field_name} must contain LargeModelReservePlacementException values."
            )
        if value.model_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(value.model_instance_id)
        exceptions.append(value)
    return tuple(sorted(exceptions, key=lambda exception: exception.model_instance_id))


def _validate_transport_override_tuple(
    field_name: str,
    values: object,
) -> tuple[TransportRestrictionOverride, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    overrides: list[TransportRestrictionOverride] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TransportRestrictionOverride:
            raise GameLifecycleError(
                f"{field_name} must contain TransportRestrictionOverride values."
            )
        overrides.append(value)
    return tuple(sorted(overrides, key=lambda override: override.override_kind.value))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    return _validate_non_empty_string(field_name, value)


def _validate_non_empty_string(field_name: str, value: object) -> str:
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
