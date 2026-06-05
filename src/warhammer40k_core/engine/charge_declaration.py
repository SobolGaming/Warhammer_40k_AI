from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecPayload,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

CHARGE_DECLARATION_PROPOSAL_KIND = "charge_declaration"
CHARGE_ROLL_TYPE = "charge_roll"
CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID = "phase15a:charge-roll-command-reroll-forbidden"


class ChargeTargetCandidatePayload(TypedDict):
    target_unit_instance_id: str
    closest_distance_inches: float
    is_legal: bool
    violation_code: str | None


class ChargeEligibilityContextPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    target_candidates: list[ChargeTargetCandidatePayload]
    ineligible_reason: str | None


class ChargeDeclarationProposalRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    battle_round: int
    phase: str
    active_player_id: str
    unit_instance_id: str
    proposal_kind: str
    source_decision_request_id: str
    source_decision_result_id: str
    ruleset_descriptor_hash: str
    max_declaration_range_inches: float
    target_candidates: list[ChargeTargetCandidatePayload]


class ChargeDeclarationDecisionPayload(TypedDict):
    proposal_request: ChargeDeclarationProposalRequestPayload


class ChargeDeclarationProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    ruleset_descriptor_hash: str
    max_declaration_range_inches: float
    target_unit_instance_ids: list[str]


class ChargeProposalViolationPayload(TypedDict):
    violation_code: str
    message: str
    field: str | None


class ChargeProposalValidationResultPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    is_valid: bool
    status: str
    violations: list[ChargeProposalViolationPayload]


class ChargeRollRequestPayload(TypedDict):
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    target_unit_instance_ids: list[str]
    spec: DiceRollSpecPayload
    source_decision_request_id: str
    source_decision_result_id: str


class ChargeRollResultPayload(TypedDict):
    request: ChargeRollRequestPayload
    roll_state: DiceRollStatePayload
    value: int
    target_distances_inches: dict[str, float]
    succeeded: bool
    status: str


class ChargeDistanceStatePayload(TypedDict):
    roll_result: ChargeRollResultPayload
    source_decision_request_id: str
    source_decision_result_id: str


@dataclass(frozen=True, slots=True)
class ChargeTargetCandidate:
    target_unit_instance_id: str
    closest_distance_inches: float
    is_legal: bool
    violation_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "ChargeTargetCandidate target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "closest_distance_inches",
            _validate_non_negative_float(
                "ChargeTargetCandidate closest_distance_inches",
                self.closest_distance_inches,
            ),
        )
        if type(self.is_legal) is not bool:
            raise GameLifecycleError("ChargeTargetCandidate is_legal must be a bool.")
        object.__setattr__(
            self,
            "violation_code",
            _validate_optional_identifier(
                "ChargeTargetCandidate violation_code",
                self.violation_code,
            ),
        )
        if self.is_legal and self.violation_code is not None:
            raise GameLifecycleError("Legal ChargeTargetCandidate must not carry violation_code.")
        if not self.is_legal and self.violation_code is None:
            raise GameLifecycleError("Illegal ChargeTargetCandidate requires violation_code.")

    def to_payload(self) -> ChargeTargetCandidatePayload:
        return {
            "target_unit_instance_id": self.target_unit_instance_id,
            "closest_distance_inches": self.closest_distance_inches,
            "is_legal": self.is_legal,
            "violation_code": self.violation_code,
        }

    @classmethod
    def from_payload(cls, payload: ChargeTargetCandidatePayload) -> Self:
        missing = _candidate_missing_field(payload)
        if missing is not None:
            raise GameLifecycleError(f"ChargeTargetCandidate payload missing {missing}.")
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            closest_distance_inches=payload["closest_distance_inches"],
            is_legal=payload["is_legal"],
            violation_code=payload["violation_code"],
        )


@dataclass(frozen=True, slots=True)
class ChargeEligibilityContext:
    player_id: str
    battle_round: int
    unit_instance_id: str
    target_candidates: tuple[ChargeTargetCandidate, ...]
    ineligible_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ChargeEligibilityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargeEligibilityContext battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ChargeEligibilityContext unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_candidates",
            _validate_target_candidates(self.target_candidates),
        )
        object.__setattr__(
            self,
            "ineligible_reason",
            _validate_optional_identifier(
                "ChargeEligibilityContext ineligible_reason",
                self.ineligible_reason,
            ),
        )

    def to_payload(self) -> ChargeEligibilityContextPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "target_candidates": [candidate.to_payload() for candidate in self.target_candidates],
            "ineligible_reason": self.ineligible_reason,
        }


@dataclass(frozen=True, slots=True)
class ChargeProposalViolation:
    violation_code: str
    message: str
    field: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("ChargeProposalViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("ChargeProposalViolation message", self.message),
        )
        object.__setattr__(
            self,
            "field",
            _validate_optional_identifier("ChargeProposalViolation field", self.field),
        )

    def to_payload(self) -> ChargeProposalViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True, slots=True)
class ChargeProposalValidationResult:
    proposal_request_id: str
    proposal_kind: str
    is_valid: bool
    status: str
    violations: tuple[ChargeProposalViolation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ChargeProposalValidationResult proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier(
                "ChargeProposalValidationResult proposal_kind",
                self.proposal_kind,
            ),
        )
        if self.proposal_kind != CHARGE_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("ChargeProposalValidationResult proposal_kind drift.")
        if type(self.is_valid) is not bool:
            raise GameLifecycleError("ChargeProposalValidationResult is_valid must be a bool.")
        object.__setattr__(
            self,
            "status",
            _validate_identifier("ChargeProposalValidationResult status", self.status),
        )
        object.__setattr__(
            self,
            "violations",
            _validate_charge_proposal_violations(self.violations),
        )
        if self.is_valid and self.violations:
            raise GameLifecycleError(
                "Valid ChargeProposalValidationResult must not include violations."
            )
        if not self.is_valid and not self.violations:
            raise GameLifecycleError("Invalid ChargeProposalValidationResult requires violations.")

    @classmethod
    def valid(cls, *, proposal_request_id: str) -> Self:
        return cls(
            proposal_request_id=proposal_request_id,
            proposal_kind=CHARGE_DECLARATION_PROPOSAL_KIND,
            is_valid=True,
            status="valid",
        )

    @classmethod
    def invalid(
        cls,
        *,
        proposal_request_id: str,
        violation_code: str,
        message: str,
        field: str | None = None,
        status: str = "invalid",
    ) -> Self:
        return cls(
            proposal_request_id=proposal_request_id,
            proposal_kind=CHARGE_DECLARATION_PROPOSAL_KIND,
            is_valid=False,
            status=status,
            violations=(
                ChargeProposalViolation(
                    violation_code=violation_code,
                    message=message,
                    field=field,
                ),
            ),
        )

    def to_payload(self) -> ChargeProposalValidationResultPayload:
        return {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "is_valid": self.is_valid,
            "status": self.status,
            "violations": [violation.to_payload() for violation in self.violations],
        }


@dataclass(frozen=True, slots=True)
class ChargeDeclarationProposalRequest:
    request_id: str
    active_player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    ruleset_descriptor_hash: str
    max_declaration_range_inches: float
    target_candidates: tuple[ChargeTargetCandidate, ...]
    proposal_kind: str = CHARGE_DECLARATION_PROPOSAL_KIND

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ChargeDeclarationProposalRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "ChargeDeclarationProposalRequest active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "ChargeDeclarationProposalRequest battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ChargeDeclarationProposalRequest unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "ChargeDeclarationProposalRequest source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "ChargeDeclarationProposalRequest source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "ChargeDeclarationProposalRequest ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "max_declaration_range_inches",
            _validate_positive_float(
                "ChargeDeclarationProposalRequest max_declaration_range_inches",
                self.max_declaration_range_inches,
            ),
        )
        object.__setattr__(
            self,
            "target_candidates",
            _validate_target_candidates(self.target_candidates),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier(
                "ChargeDeclarationProposalRequest proposal_kind",
                self.proposal_kind,
            ),
        )
        if self.proposal_kind != CHARGE_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("ChargeDeclarationProposalRequest proposal_kind drift.")

    def legal_target_unit_ids(self) -> tuple[str, ...]:
        return tuple(
            candidate.target_unit_instance_id
            for candidate in self.target_candidates
            if candidate.is_legal
        )


@dataclass(frozen=True, slots=True)
class ChargeDeclarationProposal:
    proposal_request_id: str
    proposal_kind: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    ruleset_descriptor_hash: str
    max_declaration_range_inches: float
    target_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ChargeDeclarationProposal proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier(
                "ChargeDeclarationProposal proposal_kind",
                self.proposal_kind,
            ),
        )
        if self.proposal_kind != CHARGE_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("ChargeDeclarationProposal has unsupported proposal_kind.")
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ChargeDeclarationProposal player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "ChargeDeclarationProposal battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ChargeDeclarationProposal unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "ChargeDeclarationProposal source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "ChargeDeclarationProposal source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "ChargeDeclarationProposal ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "max_declaration_range_inches",
            _validate_positive_float(
                "ChargeDeclarationProposal max_declaration_range_inches",
                self.max_declaration_range_inches,
            ),
        )
        target_ids = _validate_identifier_tuple(
            "ChargeDeclarationProposal target_unit_instance_ids",
            self.target_unit_instance_ids,
            min_length=1,
            sort_values=False,
        )
        if target_ids != tuple(sorted(target_ids)):
            raise GameLifecycleError(
                "ChargeDeclarationProposal target_unit_instance_ids must be sorted."
            )
        object.__setattr__(self, "target_unit_instance_ids", target_ids)

    def validation_result_for_request(
        self,
        request: ChargeDeclarationProposalRequest,
    ) -> ChargeProposalValidationResult:
        if type(request) is not ChargeDeclarationProposalRequest:
            raise GameLifecycleError("Charge declaration validation requires a proposal request.")
        if self.proposal_request_id != request.request_id:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_request_id_drift",
                message="Charge declaration proposal_request_id does not match request.",
                field="proposal_request_id",
            )
        if self.player_id != request.active_player_id:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_player_drift",
                message="Charge declaration player_id does not match request.",
                field="player_id",
            )
        if self.battle_round != request.battle_round:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_battle_round_drift",
                message="Charge declaration battle_round does not match request.",
                field="battle_round",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_unit_drift",
                message="Charge declaration unit does not match active selection.",
                field="unit_instance_id",
            )
        if self.source_decision_request_id != request.source_decision_request_id:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_source_request_drift",
                message="Charge declaration source_decision_request_id does not match request.",
                field="source_decision_request_id",
            )
        if self.source_decision_result_id != request.source_decision_result_id:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_source_result_drift",
                message="Charge declaration source_decision_result_id does not match request.",
                field="source_decision_result_id",
            )
        if self.ruleset_descriptor_hash != request.ruleset_descriptor_hash:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_ruleset_drift",
                message="Charge declaration ruleset hash does not match request.",
                field="ruleset_descriptor_hash",
            )
        if not math.isclose(
            self.max_declaration_range_inches,
            request.max_declaration_range_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_max_range_drift",
                message="Charge declaration max range does not match request.",
                field="max_declaration_range_inches",
            )
        legal_ids = set(request.legal_target_unit_ids())
        if not set(self.target_unit_instance_ids) <= legal_ids:
            return ChargeProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_target_not_in_request",
                message="Charge declaration includes a target not legal in the pending request.",
                field="target_unit_instance_ids",
            )
        return ChargeProposalValidationResult.valid(proposal_request_id=request.request_id)

    def to_payload(self) -> ChargeDeclarationProposalPayload:
        return {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "max_declaration_range_inches": self.max_declaration_range_inches,
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: ChargeDeclarationProposalPayload) -> Self:
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=payload["proposal_kind"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            max_declaration_range_inches=payload["max_declaration_range_inches"],
            target_unit_instance_ids=tuple(payload["target_unit_instance_ids"]),
        )


@dataclass(frozen=True, slots=True)
class ChargeRollRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    target_unit_instance_ids: tuple[str, ...]
    source_decision_request_id: str
    source_decision_result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ChargeRollRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("ChargeRollRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargeRollRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ChargeRollRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ChargeRollRequest unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeRollRequest target_unit_instance_ids",
                self.target_unit_instance_ids,
                min_length=1,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "ChargeRollRequest source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "ChargeRollRequest source_decision_result_id",
                self.source_decision_result_id,
            ),
        )

    @property
    def spec(self) -> DiceRollSpec:
        return DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Charge distance for {self.unit_instance_id}",
            roll_type=CHARGE_ROLL_TYPE,
            actor_id=self.player_id,
            reroll_forbidden_rule_ids=(CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID,),
        )

    def to_payload(self) -> ChargeRollRequestPayload:
        return {
            "request_id": self.request_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
            "spec": self.spec.to_payload(),
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
        }

    @classmethod
    def from_payload(cls, payload: ChargeRollRequestPayload) -> Self:
        request = cls(
            request_id=payload["request_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            target_unit_instance_ids=tuple(payload["target_unit_instance_ids"]),
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
        )
        if DiceRollSpec.from_payload(payload["spec"]) != request.spec:
            raise GameLifecycleError("ChargeRollRequest spec payload drift.")
        return request


@dataclass(frozen=True, slots=True)
class ChargeRollResult:
    request: ChargeRollRequest
    roll_state: DiceRollState
    value: int
    target_distances_inches: dict[str, float]
    succeeded: bool
    status: str

    def __post_init__(self) -> None:
        if type(self.request) is not ChargeRollRequest:
            raise GameLifecycleError("ChargeRollResult request must be ChargeRollRequest.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("ChargeRollResult roll_state must be DiceRollState.")
        if self.roll_state.original_result.spec != self.request.spec:
            raise GameLifecycleError("ChargeRollResult roll_state spec must match request.")
        if self.value != self.roll_state.current_total:
            raise GameLifecycleError("ChargeRollResult value must match roll_state total.")
        if self.value < 2 or self.value > 12:
            raise GameLifecycleError("ChargeRollResult value must be between 2 and 12.")
        object.__setattr__(
            self,
            "target_distances_inches",
            _validate_target_distance_mapping(
                self.target_distances_inches,
                target_unit_instance_ids=self.request.target_unit_instance_ids,
            ),
        )
        if type(self.succeeded) is not bool:
            raise GameLifecycleError("ChargeRollResult succeeded must be a bool.")
        object.__setattr__(
            self,
            "status",
            _validate_identifier("ChargeRollResult status", self.status),
        )
        expected_success = all(
            distance <= self.value for distance in self.target_distances_inches.values()
        )
        if self.succeeded != expected_success:
            raise GameLifecycleError("ChargeRollResult success flag drift.")
        expected_status = "move_pending" if self.succeeded else "failed"
        if self.status != expected_status:
            raise GameLifecycleError("ChargeRollResult status drift.")

    @classmethod
    def from_roll_state(
        cls,
        *,
        request: ChargeRollRequest,
        roll_state: DiceRollState,
        target_distances_inches: dict[str, float],
    ) -> Self:
        succeeded = all(
            distance <= roll_state.current_total for distance in target_distances_inches.values()
        )
        return cls(
            request=request,
            roll_state=roll_state,
            value=roll_state.current_total,
            target_distances_inches=target_distances_inches,
            succeeded=succeeded,
            status="move_pending" if succeeded else "failed",
        )

    def to_payload(self) -> ChargeRollResultPayload:
        return {
            "request": self.request.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
            "target_distances_inches": dict(sorted(self.target_distances_inches.items())),
            "succeeded": self.succeeded,
            "status": self.status,
        }

    @classmethod
    def from_payload(cls, payload: ChargeRollResultPayload) -> Self:
        return cls(
            request=ChargeRollRequest.from_payload(payload["request"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
            target_distances_inches=dict(payload["target_distances_inches"]),
            succeeded=payload["succeeded"],
            status=payload["status"],
        )


@dataclass(frozen=True, slots=True)
class ChargeDistanceState:
    roll_result: ChargeRollResult
    source_decision_request_id: str
    source_decision_result_id: str

    def __post_init__(self) -> None:
        if type(self.roll_result) is not ChargeRollResult:
            raise GameLifecycleError("ChargeDistanceState roll_result must be ChargeRollResult.")
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "ChargeDistanceState source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "ChargeDistanceState source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        if self.source_decision_request_id != self.roll_result.request.source_decision_request_id:
            raise GameLifecycleError("ChargeDistanceState source request drift.")
        if self.source_decision_result_id != self.roll_result.request.source_decision_result_id:
            raise GameLifecycleError("ChargeDistanceState source result drift.")

    def to_payload(self) -> ChargeDistanceStatePayload:
        return {
            "roll_result": self.roll_result.to_payload(),
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
        }

    @classmethod
    def from_payload(cls, payload: ChargeDistanceStatePayload) -> Self:
        return cls(
            roll_result=ChargeRollResult.from_payload(payload["roll_result"]),
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
        )


def charge_declaration_missing_field(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "payload"
    raw_payload = cast(dict[str, object], payload)
    required_fields = (
        "proposal_request_id",
        "proposal_kind",
        "player_id",
        "battle_round",
        "unit_instance_id",
        "source_decision_request_id",
        "source_decision_result_id",
        "ruleset_descriptor_hash",
        "max_declaration_range_inches",
        "target_unit_instance_ids",
    )
    for field in required_fields:
        if field not in raw_payload:
            return field
    return None


def charge_declaration_proposal_from_json(payload: object) -> ChargeDeclarationProposal:
    missing = charge_declaration_missing_field(payload)
    if missing is not None:
        raise GameLifecycleError(f"Charge declaration proposal missing {missing}.")
    raw_payload = cast(ChargeDeclarationProposalPayload, payload)
    target_ids = raw_payload["target_unit_instance_ids"]
    if type(target_ids) is not list:
        raise GameLifecycleError("Charge declaration target_unit_instance_ids must be a list.")
    return ChargeDeclarationProposal.from_payload(raw_payload)


def phase15a_charge_roll_payload(
    *,
    roll_result: ChargeRollResult,
    phase: BattlePhase = BattlePhase.CHARGE,
) -> dict[str, object]:
    return cast(
        dict[str, object],
        validate_json_value(
            {
                "phase": phase.value,
                "unit_instance_id": roll_result.request.unit_instance_id,
                "target_unit_instance_ids": list(roll_result.request.target_unit_instance_ids),
                "roll_result": roll_result.to_payload(),
                "phase_body_status": roll_result.status,
            }
        ),
    )


def _candidate_missing_field(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "candidate"
    raw_payload = cast(dict[str, object], payload)
    required_fields = (
        "target_unit_instance_id",
        "closest_distance_inches",
        "is_legal",
        "violation_code",
    )
    for field in required_fields:
        if field not in raw_payload:
            return field
    return None


def _validate_target_candidates(values: object) -> tuple[ChargeTargetCandidate, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Charge target candidates must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    candidates: list[ChargeTargetCandidate] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ChargeTargetCandidate:
            raise GameLifecycleError("Charge target candidates must be ChargeTargetCandidate.")
        if value.target_unit_instance_id in seen:
            raise GameLifecycleError("Charge target candidates must not contain duplicates.")
        seen.add(value.target_unit_instance_id)
        candidates.append(value)
    return tuple(sorted(candidates, key=lambda candidate: candidate.target_unit_instance_id))


def _validate_charge_proposal_violations(
    values: object,
) -> tuple[ChargeProposalViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ChargeProposalValidationResult violations must be a tuple.")
    violations = cast(tuple[object, ...], values)
    validated: list[ChargeProposalViolation] = []
    for value in violations:
        if type(value) is not ChargeProposalViolation:
            raise GameLifecycleError(
                "ChargeProposalValidationResult violations must contain "
                "ChargeProposalViolation values."
            )
        validated.append(value)
    return tuple(validated)


def _validate_target_distance_mapping(
    values: object,
    *,
    target_unit_instance_ids: tuple[str, ...],
) -> dict[str, float]:
    if type(values) is not dict:
        raise GameLifecycleError("ChargeRollResult target distances must be a dict.")
    raw_values = cast(dict[object, object], values)
    expected_ids = set(target_unit_instance_ids)
    actual_ids: set[str] = set()
    validated: dict[str, float] = {}
    for key, value in raw_values.items():
        target_id = _validate_identifier("ChargeRollResult target distance key", key)
        actual_ids.add(target_id)
        validated[target_id] = _validate_non_negative_float(
            "ChargeRollResult target distance",
            value,
        )
    if actual_ids != expected_ids:
        raise GameLifecycleError("ChargeRollResult target distance keys drift.")
    return dict(sorted(validated.items()))


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    if type(min_length) is not int:
        raise GameLifecycleError("min_length must be an int.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(validated) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    if sort_values:
        return tuple(sorted(validated))
    return validated


def _validate_identifier(field_name: str, value: object) -> str:
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


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_positive_float(field_name: str, value: object) -> float:
    number = _validate_non_negative_float(field_name, value)
    if number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return number


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return number
