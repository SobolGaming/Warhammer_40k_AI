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
from warhammer40k_core.core.modifiers import (
    RollModifier,
    RollModifierOperation,
    RollModifierPayload,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

CHARGE_ROLL_TYPE = "charge_roll"
CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID = "phase15a:charge-roll-command-reroll-forbidden"
CHARGE_MOVE_PENDING_STATUS = "move_pending"
CHARGE_NO_MOVE_POSSIBLE_STATUS = "no_move_possible"


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


class ChargeRollRequestPayload(TypedDict):
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpecPayload
    roll_modifiers: list[RollModifierPayload]
    source_decision_request_id: str
    source_decision_result_id: str


class ChargeRollResultPayload(TypedDict):
    request: ChargeRollRequestPayload
    roll_state: DiceRollStatePayload
    value: int
    reachable_target_distances_inches: dict[str, float]
    move_available: bool
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
class ChargeRollRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    roll_modifiers: tuple[RollModifier, ...] = ()

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
        object.__setattr__(
            self,
            "roll_modifiers",
            _validate_charge_roll_modifiers(self.roll_modifiers),
        )

    @property
    def spec(self) -> DiceRollSpec:
        return DiceRollSpec(
            expression=DiceExpression(
                quantity=2,
                sides=6,
                modifier=sum(modifier.operand for modifier in self.roll_modifiers),
            ),
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
            "spec": self.spec.to_payload(),
            "roll_modifiers": [modifier.to_payload() for modifier in self.roll_modifiers],
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
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            roll_modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["roll_modifiers"]
            ),
        )
        if DiceRollSpec.from_payload(payload["spec"]) != request.spec:
            raise GameLifecycleError("ChargeRollRequest spec payload drift.")
        return request


@dataclass(frozen=True, slots=True)
class ChargeRollResult:
    request: ChargeRollRequest
    roll_state: DiceRollState
    value: int
    reachable_target_distances_inches: dict[str, float]
    move_available: bool
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
        min_value = self.request.spec.expression.quantity + self.request.spec.expression.modifier
        max_value = (
            self.request.spec.expression.quantity * self.request.spec.expression.sides
            + self.request.spec.expression.modifier
        )
        if self.value < min_value or self.value > max_value:
            raise GameLifecycleError("ChargeRollResult value must match request expression bounds.")
        object.__setattr__(
            self,
            "reachable_target_distances_inches",
            _validate_reachable_target_distances(
                self.reachable_target_distances_inches,
                maximum_distance_inches=self.value,
            ),
        )
        if type(self.move_available) is not bool:
            raise GameLifecycleError("ChargeRollResult move_available must be a bool.")
        expected_move_available = bool(self.reachable_target_distances_inches)
        if self.move_available != expected_move_available:
            raise GameLifecycleError("ChargeRollResult move_available flag drift.")
        object.__setattr__(
            self,
            "status",
            _validate_identifier("ChargeRollResult status", self.status),
        )
        expected_status = (
            CHARGE_MOVE_PENDING_STATUS if self.move_available else CHARGE_NO_MOVE_POSSIBLE_STATUS
        )
        if self.status != expected_status:
            raise GameLifecycleError("ChargeRollResult status drift.")

    @classmethod
    def from_roll_state(
        cls,
        *,
        request: ChargeRollRequest,
        roll_state: DiceRollState,
        reachable_target_distances_inches: dict[str, float],
    ) -> Self:
        move_available = bool(reachable_target_distances_inches)
        return cls(
            request=request,
            roll_state=roll_state,
            value=roll_state.current_total,
            reachable_target_distances_inches=reachable_target_distances_inches,
            move_available=move_available,
            status=CHARGE_MOVE_PENDING_STATUS if move_available else CHARGE_NO_MOVE_POSSIBLE_STATUS,
        )

    def to_payload(self) -> ChargeRollResultPayload:
        return {
            "request": self.request.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
            "reachable_target_distances_inches": dict(
                sorted(self.reachable_target_distances_inches.items())
            ),
            "move_available": self.move_available,
            "status": self.status,
        }

    @classmethod
    def from_payload(cls, payload: ChargeRollResultPayload) -> Self:
        return cls(
            request=ChargeRollRequest.from_payload(payload["request"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
            reachable_target_distances_inches=dict(payload["reachable_target_distances_inches"]),
            move_available=payload["move_available"],
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
                "maximum_distance_inches": roll_result.value,
                "charge_roll_modifiers": [
                    modifier.to_payload() for modifier in roll_result.request.roll_modifiers
                ],
                "reachable_target_unit_instance_ids": list(
                    roll_result.reachable_target_distances_inches
                ),
                "reachable_target_distances_inches": dict(
                    sorted(roll_result.reachable_target_distances_inches.items())
                ),
                "charge_move_available": roll_result.move_available,
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


def _validate_charge_roll_modifiers(
    modifiers: tuple[RollModifier, ...],
) -> tuple[RollModifier, ...]:
    if type(modifiers) is not tuple:
        raise GameLifecycleError("ChargeRollRequest roll_modifiers must be a tuple.")
    seen_ids: set[str] = set()
    validated: list[RollModifier] = []
    for modifier in modifiers:
        if type(modifier) is not RollModifier:
            raise GameLifecycleError("ChargeRollRequest roll_modifiers must contain RollModifier.")
        if modifier.operation is not RollModifierOperation.ADD:
            raise GameLifecycleError("Charge roll modifiers must be additive.")
        if modifier.modifier_id in seen_ids:
            raise GameLifecycleError("ChargeRollRequest roll_modifiers must not duplicate IDs.")
        seen_ids.add(modifier.modifier_id)
        validated.append(modifier)
    return tuple(sorted(validated, key=lambda modifier: modifier.modifier_id))


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


def _validate_reachable_target_distances(
    values: object,
    *,
    maximum_distance_inches: int,
) -> dict[str, float]:
    if type(values) is not dict:
        raise GameLifecycleError("ChargeRollResult reachable target distances must be a dict.")
    raw_values = cast(dict[object, object], values)
    validated: dict[str, float] = {}
    for key, value in raw_values.items():
        target_id = _validate_identifier("ChargeRollResult reachable target key", key)
        if target_id in validated:
            raise GameLifecycleError("ChargeRollResult reachable targets must not duplicate.")
        distance = _validate_non_negative_float(
            "ChargeRollResult reachable target distance",
            value,
        )
        if distance > maximum_distance_inches:
            raise GameLifecycleError("ChargeRollResult reachable target exceeds roll.")
        validated[target_id] = distance
    return dict(sorted(validated.items()))


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


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return number
