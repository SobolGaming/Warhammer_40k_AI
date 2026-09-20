from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.volume import Model

_AIRCRAFT_KEYWORD = "AIRCRAFT"
_FLY_KEYWORD = "FLY"


class AircraftMovementViolationCode(StrEnum):
    UNIT_NOT_AIRCRAFT = "unit_not_aircraft"
    INGRESS_ONLY = "aircraft_ingress_only"


class AircraftMovementPolicyPayload(TypedDict):
    ruleset_descriptor_hash: str
    unit_instance_id: str
    model_instance_ids: list[str]
    original_keywords: list[str]
    effective_keywords: list[str]
    has_aircraft_keyword: bool
    uses_aircraft_rules: bool
    can_move_over_other_models: bool
    other_models_can_move_over_this_aircraft: bool
    can_declare_charge: bool
    fight_phase_restriction_exposed: bool


class AircraftMovementViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_instance_id: str | None


@dataclass(frozen=True, slots=True)
class AircraftMovementPolicy:
    ruleset_descriptor_hash: str
    unit_instance_id: str
    model_instance_ids: tuple[str, ...]
    original_keywords: tuple[str, ...]
    effective_keywords: tuple[str, ...]
    has_aircraft_keyword: bool
    uses_aircraft_rules: bool
    can_move_over_other_models: bool
    other_models_can_move_over_this_aircraft: bool
    can_declare_charge: bool
    fight_phase_restriction_exposed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "AircraftMovementPolicy ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AircraftMovementPolicy unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "AircraftMovementPolicy model_instance_ids",
                self.model_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "original_keywords",
            _validate_keyword_tuple(
                "AircraftMovementPolicy original_keywords",
                self.original_keywords,
            ),
        )
        object.__setattr__(
            self,
            "effective_keywords",
            _validate_keyword_tuple(
                "AircraftMovementPolicy effective_keywords",
                self.effective_keywords,
            ),
        )
        for field_name, value in (
            ("has_aircraft_keyword", self.has_aircraft_keyword),
            ("uses_aircraft_rules", self.uses_aircraft_rules),
            ("can_move_over_other_models", self.can_move_over_other_models),
            (
                "other_models_can_move_over_this_aircraft",
                self.other_models_can_move_over_this_aircraft,
            ),
            ("can_declare_charge", self.can_declare_charge),
            ("fight_phase_restriction_exposed", self.fight_phase_restriction_exposed),
        ):
            _validate_bool(f"AircraftMovementPolicy {field_name}", value)
        has_aircraft = _AIRCRAFT_KEYWORD in self.original_keywords
        if (
            self.effective_keywords != self.original_keywords
            or self.has_aircraft_keyword != has_aircraft
            or self.uses_aircraft_rules != has_aircraft
            or self.can_declare_charge == has_aircraft
            or self.fight_phase_restriction_exposed != has_aircraft
            or self.other_models_can_move_over_this_aircraft != has_aircraft
            or self.can_move_over_other_models
            != (has_aircraft or _FLY_KEYWORD in self.original_keywords)
        ):
            raise GameLifecycleError("AircraftMovementPolicy derived keyword authority drift.")

    @classmethod
    def from_unit(
        cls,
        *,
        unit: UnitInstance,
        ruleset_descriptor: RulesetDescriptor,
    ) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("AircraftMovementPolicy requires a UnitInstance.")
        if type(ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("AircraftMovementPolicy requires a RulesetDescriptor.")
        original_keywords = _validate_keyword_tuple(
            "AircraftMovementPolicy unit keywords",
            unit.keywords,
        )
        has_aircraft = _AIRCRAFT_KEYWORD in original_keywords
        effective_keywords = original_keywords
        uses_aircraft_rules = has_aircraft
        return cls(
            ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
            unit_instance_id=unit.unit_instance_id,
            model_instance_ids=tuple(model.model_instance_id for model in unit.own_models),
            original_keywords=original_keywords,
            effective_keywords=effective_keywords,
            has_aircraft_keyword=has_aircraft,
            uses_aircraft_rules=uses_aircraft_rules,
            can_move_over_other_models=uses_aircraft_rules or _FLY_KEYWORD in effective_keywords,
            other_models_can_move_over_this_aircraft=uses_aircraft_rules,
            can_declare_charge=not uses_aircraft_rules,
            fight_phase_restriction_exposed=uses_aircraft_rules,
        )

    def validate_normal_move_witness(
        self,
        *,
        moving_model: Model,
        witness: PathWitness,
    ) -> tuple[AircraftMovementViolation, ...]:
        if type(moving_model) is not Model:
            raise GameLifecycleError("Aircraft movement validation requires a Model.")
        if type(witness) is not PathWitness:
            raise GameLifecycleError("Aircraft movement validation requires a PathWitness.")
        if moving_model.model_id not in set(self.model_instance_ids):
            raise GameLifecycleError("Aircraft movement validation model is not in policy.")
        if not self.has_aircraft_keyword:
            return (
                AircraftMovementViolation(
                    violation_code=AircraftMovementViolationCode.UNIT_NOT_AIRCRAFT,
                    message="Unit does not have the AIRCRAFT keyword.",
                    model_instance_id=moving_model.model_id,
                ),
            )
        return (
            AircraftMovementViolation(
                violation_code=AircraftMovementViolationCode.INGRESS_ONLY,
                message="AIRCRAFT units may only make ingress moves.",
                model_instance_id=moving_model.model_id,
            ),
        )

    def to_payload(self) -> AircraftMovementPolicyPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_ids": list(self.model_instance_ids),
            "original_keywords": list(self.original_keywords),
            "effective_keywords": list(self.effective_keywords),
            "has_aircraft_keyword": self.has_aircraft_keyword,
            "uses_aircraft_rules": self.uses_aircraft_rules,
            "can_move_over_other_models": self.can_move_over_other_models,
            "other_models_can_move_over_this_aircraft": (
                self.other_models_can_move_over_this_aircraft
            ),
            "can_declare_charge": self.can_declare_charge,
            "fight_phase_restriction_exposed": self.fight_phase_restriction_exposed,
        }

    @classmethod
    def from_payload(cls, payload: AircraftMovementPolicyPayload) -> Self:
        if "hover_mode_active" in payload:
            raise GameLifecycleError("Retired Hover mode policy requires contract migration.")
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_ids=tuple(payload["model_instance_ids"]),
            original_keywords=tuple(payload["original_keywords"]),
            effective_keywords=tuple(payload["effective_keywords"]),
            has_aircraft_keyword=payload["has_aircraft_keyword"],
            uses_aircraft_rules=payload["uses_aircraft_rules"],
            can_move_over_other_models=payload["can_move_over_other_models"],
            other_models_can_move_over_this_aircraft=payload[
                "other_models_can_move_over_this_aircraft"
            ],
            can_declare_charge=payload["can_declare_charge"],
            fight_phase_restriction_exposed=payload["fight_phase_restriction_exposed"],
        )


@dataclass(frozen=True, slots=True)
class AircraftMovementViolation:
    violation_code: AircraftMovementViolationCode
    message: str
    model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            aircraft_movement_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("AircraftMovementViolation message", self.message),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "AircraftMovementViolation model_instance_id",
                self.model_instance_id,
            ),
        )

    def to_payload(self) -> AircraftMovementViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "model_instance_id": self.model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: AircraftMovementViolationPayload) -> Self:
        return cls(
            violation_code=aircraft_movement_violation_code_from_token(payload["violation_code"]),
            message=payload["message"],
            model_instance_id=payload["model_instance_id"],
        )


def aircraft_model_ids_for_scenario(
    scenario: BattlefieldScenario,
) -> tuple[str, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("aircraft_model_ids_for_scenario requires a scenario.")
    aircraft_model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            aircraft_model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if _AIRCRAFT_KEYWORD in scenario.model_instance_for_placement(placement).keywords
            )
    return tuple(sorted(aircraft_model_ids))


def aircraft_movement_violation_code_from_token(token: object) -> AircraftMovementViolationCode:
    if type(token) is AircraftMovementViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AircraftMovementViolationCode token must be a string.")
    try:
        return AircraftMovementViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported AircraftMovementViolationCode token: {token}."
        ) from exc


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = _validate_identifier(f"{field_name} value", value)
        if keyword in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
