from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.game_state import GameState


SELECT_ATTACK_ALLOCATION_DECISION_TYPE = "select_attack_allocation"
SELECT_FEEL_NO_PAIN_DECISION_TYPE = "select_feel_no_pain"


class DamageKind(StrEnum):
    NORMAL = "normal"
    MORTAL = "mortal"


class AttackAllocationConstraintPayload(TypedDict):
    source_rule_ids: list[str]
    allowed_model_ids: list[str] | None
    can_allocate_protected_characters: bool
    attacker_selected_model_id: str | None


class AttackAllocationRuleContextPayload(TypedDict):
    target_unit_instance_id: str
    alive_model_ids: list[str]
    wounded_model_ids: list[str]
    already_allocated_model_ids: list[str]
    attached_unit_bodyguard_model_ids: list[str]
    attached_unit_character_model_ids: list[str]
    attacker_constraint: AttackAllocationConstraintPayload | None


class AttackAllocationPayload(TypedDict):
    target_unit_instance_id: str
    allocated_model_id: str
    legal_model_ids: list[str]
    forced: bool
    source_rule_ids: list[str]
    rule_context: AttackAllocationRuleContextPayload


class AttackAllocationDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    selected_model_id: str
    attack_context: JsonValue


class DamageApplicationPayload(TypedDict):
    target_unit_instance_id: str
    model_instance_id: str
    damage_kind: str
    requested_damage: int
    wounds_lost: int
    excess_damage_lost: int
    starting_wounds_remaining: int
    final_wounds_remaining: int
    destroyed: bool


class MortalWoundApplicationPayload(TypedDict):
    target_unit_instance_id: str
    mortal_wounds: int
    spill_over: bool
    applications: list[DamageApplicationPayload]
    feel_no_pain_resolutions: list[FeelNoPainResolutionPayload]
    ignored_mortal_wounds: int
    remaining_mortal_wounds_lost: int


class FeelNoPainSourcePayload(TypedDict):
    source_id: str
    threshold: int


class FeelNoPainDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    selected_source_id: str | None
    lost_wound_context: JsonValue


class FeelNoPainRollPayload(TypedDict):
    source: FeelNoPainSourcePayload
    roll_state: DiceRollStatePayload
    successful: bool


class FeelNoPainResolutionPayload(TypedDict):
    source: FeelNoPainSourcePayload | None
    requested_wounds: int
    ignored_wounds: int
    remaining_wounds: int
    rolls: list[FeelNoPainRollPayload]


@dataclass(frozen=True, slots=True)
class AttackAllocationConstraint:
    source_rule_ids: tuple[str, ...] = ()
    allowed_model_ids: tuple[str, ...] | None = None
    can_allocate_protected_characters: bool = False
    attacker_selected_model_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_ids",
            _validate_identifier_tuple(
                "AttackAllocationConstraint source_rule_ids",
                self.source_rule_ids,
            ),
        )
        if self.allowed_model_ids is not None:
            object.__setattr__(
                self,
                "allowed_model_ids",
                _validate_identifier_tuple(
                    "AttackAllocationConstraint allowed_model_ids",
                    self.allowed_model_ids,
                ),
            )
        if type(self.can_allocate_protected_characters) is not bool:
            raise GameLifecycleError(
                "AttackAllocationConstraint can_allocate_protected_characters must be a bool."
            )
        object.__setattr__(
            self,
            "attacker_selected_model_id",
            _validate_optional_identifier(
                "AttackAllocationConstraint attacker_selected_model_id",
                self.attacker_selected_model_id,
            ),
        )
        if (
            self.attacker_selected_model_id is not None
            and self.allowed_model_ids is not None
            and self.attacker_selected_model_id not in self.allowed_model_ids
        ):
            raise GameLifecycleError(
                "AttackAllocationConstraint attacker selection must be allowed."
            )

    def to_payload(self) -> AttackAllocationConstraintPayload:
        return {
            "source_rule_ids": list(self.source_rule_ids),
            "allowed_model_ids": (
                None if self.allowed_model_ids is None else list(self.allowed_model_ids)
            ),
            "can_allocate_protected_characters": self.can_allocate_protected_characters,
            "attacker_selected_model_id": self.attacker_selected_model_id,
        }

    @classmethod
    def from_payload(cls, payload: AttackAllocationConstraintPayload) -> Self:
        allowed_model_ids = payload["allowed_model_ids"]
        return cls(
            source_rule_ids=tuple(payload["source_rule_ids"]),
            allowed_model_ids=None if allowed_model_ids is None else tuple(allowed_model_ids),
            can_allocate_protected_characters=payload["can_allocate_protected_characters"],
            attacker_selected_model_id=payload["attacker_selected_model_id"],
        )


@dataclass(frozen=True, slots=True)
class AttackAllocationRuleContext:
    target_unit_instance_id: str
    alive_model_ids: tuple[str, ...]
    wounded_model_ids: tuple[str, ...] = ()
    already_allocated_model_ids: tuple[str, ...] = ()
    attached_unit_bodyguard_model_ids: tuple[str, ...] = ()
    attached_unit_character_model_ids: tuple[str, ...] = ()
    attacker_constraint: AttackAllocationConstraint | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "AttackAllocationRuleContext target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        alive_model_ids = _validate_identifier_tuple(
            "AttackAllocationRuleContext alive_model_ids",
            self.alive_model_ids,
        )
        if not alive_model_ids:
            raise GameLifecycleError("AttackAllocationRuleContext requires alive models.")
        object.__setattr__(self, "alive_model_ids", alive_model_ids)
        object.__setattr__(
            self,
            "wounded_model_ids",
            _validate_identifier_tuple(
                "AttackAllocationRuleContext wounded_model_ids",
                self.wounded_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "already_allocated_model_ids",
            _validate_identifier_tuple(
                "AttackAllocationRuleContext already_allocated_model_ids",
                self.already_allocated_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "attached_unit_bodyguard_model_ids",
            _validate_identifier_tuple(
                "AttackAllocationRuleContext attached_unit_bodyguard_model_ids",
                self.attached_unit_bodyguard_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "attached_unit_character_model_ids",
            _validate_identifier_tuple(
                "AttackAllocationRuleContext attached_unit_character_model_ids",
                self.attached_unit_character_model_ids,
            ),
        )
        if (
            self.attacker_constraint is not None
            and type(self.attacker_constraint) is not AttackAllocationConstraint
        ):
            raise GameLifecycleError(
                "AttackAllocationRuleContext attacker_constraint must be a constraint."
            )
        _validate_subset(
            field_name="wounded_model_ids",
            values=self.wounded_model_ids,
            universe=alive_model_ids,
        )
        _validate_subset(
            field_name="already_allocated_model_ids",
            values=self.already_allocated_model_ids,
            universe=alive_model_ids,
        )
        _validate_subset(
            field_name="attached_unit_bodyguard_model_ids",
            values=self.attached_unit_bodyguard_model_ids,
            universe=alive_model_ids,
        )
        _validate_subset(
            field_name="attached_unit_character_model_ids",
            values=self.attached_unit_character_model_ids,
            universe=alive_model_ids,
        )

    def legal_model_ids(self) -> tuple[str, ...]:
        legal = set(self.alive_model_ids)
        bodyguard_ids = set(self.attached_unit_bodyguard_model_ids)
        character_ids = set(self.attached_unit_character_model_ids)
        constraint = self.attacker_constraint
        if (
            bodyguard_ids
            and character_ids
            and not (constraint is not None and constraint.can_allocate_protected_characters)
        ):
            legal -= character_ids
        if constraint is not None and constraint.allowed_model_ids is not None:
            legal &= set(constraint.allowed_model_ids)
        if constraint is not None and constraint.attacker_selected_model_id is not None:
            selected = constraint.attacker_selected_model_id
            if selected not in legal:
                raise GameLifecycleError("Attacker-side allocation selection is not legal.")
            return (selected,)

        priority_ids = legal & (set(self.wounded_model_ids) | set(self.already_allocated_model_ids))
        if priority_ids:
            return tuple(sorted(priority_ids))
        return tuple(sorted(legal))

    def to_payload(self) -> AttackAllocationRuleContextPayload:
        return {
            "target_unit_instance_id": self.target_unit_instance_id,
            "alive_model_ids": list(self.alive_model_ids),
            "wounded_model_ids": list(self.wounded_model_ids),
            "already_allocated_model_ids": list(self.already_allocated_model_ids),
            "attached_unit_bodyguard_model_ids": list(self.attached_unit_bodyguard_model_ids),
            "attached_unit_character_model_ids": list(self.attached_unit_character_model_ids),
            "attacker_constraint": (
                None if self.attacker_constraint is None else self.attacker_constraint.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: AttackAllocationRuleContextPayload) -> Self:
        constraint_payload = payload["attacker_constraint"]
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            alive_model_ids=tuple(payload["alive_model_ids"]),
            wounded_model_ids=tuple(payload["wounded_model_ids"]),
            already_allocated_model_ids=tuple(payload["already_allocated_model_ids"]),
            attached_unit_bodyguard_model_ids=tuple(payload["attached_unit_bodyguard_model_ids"]),
            attached_unit_character_model_ids=tuple(payload["attached_unit_character_model_ids"]),
            attacker_constraint=(
                None
                if constraint_payload is None
                else AttackAllocationConstraint.from_payload(constraint_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class AttackAllocation:
    target_unit_instance_id: str
    allocated_model_id: str
    legal_model_ids: tuple[str, ...]
    forced: bool
    rule_context: AttackAllocationRuleContext
    source_rule_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "AttackAllocation target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "allocated_model_id",
            _validate_identifier("AttackAllocation allocated_model_id", self.allocated_model_id),
        )
        object.__setattr__(
            self,
            "legal_model_ids",
            _validate_identifier_tuple("AttackAllocation legal_model_ids", self.legal_model_ids),
        )
        if self.allocated_model_id not in self.legal_model_ids:
            raise GameLifecycleError("AttackAllocation allocated model must be legal.")
        if type(self.forced) is not bool:
            raise GameLifecycleError("AttackAllocation forced must be a bool.")
        if type(self.rule_context) is not AttackAllocationRuleContext:
            raise GameLifecycleError("AttackAllocation rule_context must be an allocation context.")
        object.__setattr__(
            self,
            "source_rule_ids",
            _validate_identifier_tuple("AttackAllocation source_rule_ids", self.source_rule_ids),
        )

    @classmethod
    def from_context(
        cls,
        context: AttackAllocationRuleContext,
        *,
        allocated_model_id: str,
        forced: bool,
    ) -> Self:
        legal_model_ids = context.legal_model_ids()
        return cls(
            target_unit_instance_id=context.target_unit_instance_id,
            allocated_model_id=allocated_model_id,
            legal_model_ids=legal_model_ids,
            forced=forced,
            rule_context=context,
            source_rule_ids=(
                ()
                if context.attacker_constraint is None
                else context.attacker_constraint.source_rule_ids
            ),
        )

    def to_payload(self) -> AttackAllocationPayload:
        return {
            "target_unit_instance_id": self.target_unit_instance_id,
            "allocated_model_id": self.allocated_model_id,
            "legal_model_ids": list(self.legal_model_ids),
            "forced": self.forced,
            "source_rule_ids": list(self.source_rule_ids),
            "rule_context": self.rule_context.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: AttackAllocationPayload) -> Self:
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            allocated_model_id=payload["allocated_model_id"],
            legal_model_ids=tuple(payload["legal_model_ids"]),
            forced=payload["forced"],
            source_rule_ids=tuple(payload["source_rule_ids"]),
            rule_context=AttackAllocationRuleContext.from_payload(payload["rule_context"]),
        )


@dataclass(frozen=True, slots=True)
class AttackAllocationDecision:
    request_id: str
    result_id: str
    player_id: str
    selected_model_id: str
    attack_context: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("AttackAllocationDecision request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("AttackAllocationDecision result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AttackAllocationDecision player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "selected_model_id",
            _validate_identifier(
                "AttackAllocationDecision selected_model_id",
                self.selected_model_id,
            ),
        )
        object.__setattr__(self, "attack_context", validate_json_value(self.attack_context))

    @classmethod
    def from_result(cls, *, request: DecisionRequest, result: DecisionResult) -> Self:
        result.validate_for_request(request)
        payload = _payload_object(result.payload)
        selected_model_id = _payload_string(payload, key="model_instance_id")
        actor_id = result.actor_id
        if actor_id is None:
            raise GameLifecycleError("AttackAllocationDecision requires a defender actor.")
        request_payload = _payload_object(request.payload)
        return cls(
            request_id=request.request_id,
            result_id=result.result_id,
            player_id=actor_id,
            selected_model_id=selected_model_id,
            attack_context=validate_json_value(request_payload["attack_context"]),
        )

    def to_payload(self) -> AttackAllocationDecisionPayload:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "player_id": self.player_id,
            "selected_model_id": self.selected_model_id,
            "attack_context": self.attack_context,
        }


@dataclass(frozen=True, slots=True)
class DamageApplication:
    target_unit_instance_id: str
    model_instance_id: str
    damage_kind: DamageKind
    requested_damage: int
    wounds_lost: int
    excess_damage_lost: int
    starting_wounds_remaining: int
    final_wounds_remaining: int
    destroyed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "DamageApplication target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("DamageApplication model_instance_id", self.model_instance_id),
        )
        object.__setattr__(self, "damage_kind", damage_kind_from_token(self.damage_kind))
        object.__setattr__(
            self,
            "requested_damage",
            _validate_positive_int("DamageApplication requested_damage", self.requested_damage),
        )
        object.__setattr__(
            self,
            "wounds_lost",
            _validate_non_negative_int("DamageApplication wounds_lost", self.wounds_lost),
        )
        object.__setattr__(
            self,
            "excess_damage_lost",
            _validate_non_negative_int(
                "DamageApplication excess_damage_lost",
                self.excess_damage_lost,
            ),
        )
        object.__setattr__(
            self,
            "starting_wounds_remaining",
            _validate_positive_int(
                "DamageApplication starting_wounds_remaining",
                self.starting_wounds_remaining,
            ),
        )
        object.__setattr__(
            self,
            "final_wounds_remaining",
            _validate_non_negative_int(
                "DamageApplication final_wounds_remaining",
                self.final_wounds_remaining,
            ),
        )
        if type(self.destroyed) is not bool:
            raise GameLifecycleError("DamageApplication destroyed must be a bool.")
        if self.wounds_lost + self.excess_damage_lost != self.requested_damage:
            raise GameLifecycleError("DamageApplication damage accounting drift.")
        if self.starting_wounds_remaining - self.wounds_lost != self.final_wounds_remaining:
            raise GameLifecycleError("DamageApplication wound total drift.")
        if self.destroyed != (self.final_wounds_remaining == 0):
            raise GameLifecycleError("DamageApplication destroyed flag drift.")

    def to_payload(self) -> DamageApplicationPayload:
        return {
            "target_unit_instance_id": self.target_unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "damage_kind": self.damage_kind.value,
            "requested_damage": self.requested_damage,
            "wounds_lost": self.wounds_lost,
            "excess_damage_lost": self.excess_damage_lost,
            "starting_wounds_remaining": self.starting_wounds_remaining,
            "final_wounds_remaining": self.final_wounds_remaining,
            "destroyed": self.destroyed,
        }

    @classmethod
    def from_payload(cls, payload: DamageApplicationPayload) -> Self:
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            damage_kind=damage_kind_from_token(payload["damage_kind"]),
            requested_damage=payload["requested_damage"],
            wounds_lost=payload["wounds_lost"],
            excess_damage_lost=payload["excess_damage_lost"],
            starting_wounds_remaining=payload["starting_wounds_remaining"],
            final_wounds_remaining=payload["final_wounds_remaining"],
            destroyed=payload["destroyed"],
        )


@dataclass(frozen=True, slots=True)
class MortalWoundApplication:
    target_unit_instance_id: str
    mortal_wounds: int
    spill_over: bool
    applications: tuple[DamageApplication, ...]
    feel_no_pain_resolutions: tuple[FeelNoPainResolution, ...] = ()
    ignored_mortal_wounds: int = 0
    remaining_mortal_wounds_lost: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "MortalWoundApplication target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "mortal_wounds",
            _validate_positive_int("MortalWoundApplication mortal_wounds", self.mortal_wounds),
        )
        if type(self.spill_over) is not bool:
            raise GameLifecycleError("MortalWoundApplication spill_over must be a bool.")
        applications = _validate_damage_applications(self.applications)
        object.__setattr__(self, "applications", applications)
        resolutions = _validate_feel_no_pain_resolutions(self.feel_no_pain_resolutions)
        object.__setattr__(self, "feel_no_pain_resolutions", resolutions)
        object.__setattr__(
            self,
            "ignored_mortal_wounds",
            _validate_non_negative_int(
                "MortalWoundApplication ignored_mortal_wounds",
                self.ignored_mortal_wounds,
            ),
        )
        object.__setattr__(
            self,
            "remaining_mortal_wounds_lost",
            _validate_non_negative_int(
                "MortalWoundApplication remaining_mortal_wounds_lost",
                self.remaining_mortal_wounds_lost,
            ),
        )
        accounted = (
            sum(application.wounds_lost for application in applications)
            + self.ignored_mortal_wounds
            + self.remaining_mortal_wounds_lost
        )
        if accounted != self.mortal_wounds:
            raise GameLifecycleError("MortalWoundApplication wound accounting drift.")

    def to_payload(self) -> MortalWoundApplicationPayload:
        return {
            "target_unit_instance_id": self.target_unit_instance_id,
            "mortal_wounds": self.mortal_wounds,
            "spill_over": self.spill_over,
            "applications": [application.to_payload() for application in self.applications],
            "feel_no_pain_resolutions": [
                resolution.to_payload() for resolution in self.feel_no_pain_resolutions
            ],
            "ignored_mortal_wounds": self.ignored_mortal_wounds,
            "remaining_mortal_wounds_lost": self.remaining_mortal_wounds_lost,
        }


@dataclass(frozen=True, slots=True)
class FeelNoPainSource:
    source_id: str
    threshold: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("FeelNoPainSource source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "threshold",
            _validate_d6_target("FeelNoPainSource threshold", self.threshold),
        )

    def to_payload(self) -> FeelNoPainSourcePayload:
        return {"source_id": self.source_id, "threshold": self.threshold}

    @classmethod
    def from_payload(cls, payload: FeelNoPainSourcePayload) -> Self:
        return cls(source_id=payload["source_id"], threshold=payload["threshold"])


@dataclass(frozen=True, slots=True)
class FeelNoPainRoll:
    source: FeelNoPainSource
    roll_state: DiceRollState
    successful: bool

    def __post_init__(self) -> None:
        if type(self.source) is not FeelNoPainSource:
            raise GameLifecycleError("FeelNoPainRoll source must be a FeelNoPainSource.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("FeelNoPainRoll roll_state must be DiceRollState.")
        if type(self.successful) is not bool:
            raise GameLifecycleError("FeelNoPainRoll successful must be a bool.")
        expected_success = self.roll_state.current_total >= self.source.threshold
        if self.successful != expected_success:
            raise GameLifecycleError("FeelNoPainRoll success flag drift.")

    def to_payload(self) -> FeelNoPainRollPayload:
        return {
            "source": self.source.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "successful": self.successful,
        }


@dataclass(frozen=True, slots=True)
class FeelNoPainResolution:
    source: FeelNoPainSource | None
    requested_wounds: int
    rolls: tuple[FeelNoPainRoll, ...] = ()

    def __post_init__(self) -> None:
        if self.source is not None and type(self.source) is not FeelNoPainSource:
            raise GameLifecycleError("FeelNoPainResolution source must be a FeelNoPainSource.")
        object.__setattr__(
            self,
            "requested_wounds",
            _validate_positive_int(
                "FeelNoPainResolution requested_wounds",
                self.requested_wounds,
            ),
        )
        rolls = _validate_feel_no_pain_rolls(self.rolls)
        object.__setattr__(self, "rolls", rolls)
        if self.source is None and rolls:
            raise GameLifecycleError("Declined Feel No Pain must not include rolls.")
        if self.source is not None and len(rolls) != self.requested_wounds:
            raise GameLifecycleError("Feel No Pain rolls must match requested wounds.")
        for roll in rolls:
            if roll.source != self.source:
                raise GameLifecycleError("Feel No Pain roll source drift.")

    @classmethod
    def declined(cls, *, requested_wounds: int) -> Self:
        return cls(source=None, requested_wounds=requested_wounds, rolls=())

    @property
    def ignored_wounds(self) -> int:
        return sum(1 for roll in self.rolls if roll.successful)

    @property
    def remaining_wounds(self) -> int:
        return self.requested_wounds - self.ignored_wounds

    def to_payload(self) -> FeelNoPainResolutionPayload:
        return {
            "source": None if self.source is None else self.source.to_payload(),
            "requested_wounds": self.requested_wounds,
            "ignored_wounds": self.ignored_wounds,
            "remaining_wounds": self.remaining_wounds,
            "rolls": [roll.to_payload() for roll in self.rolls],
        }


@dataclass(frozen=True, slots=True)
class FeelNoPainDecision:
    request_id: str
    result_id: str
    player_id: str
    selected_source_id: str | None
    lost_wound_context: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("FeelNoPainDecision request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("FeelNoPainDecision result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FeelNoPainDecision player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "selected_source_id",
            _validate_optional_identifier(
                "FeelNoPainDecision selected_source_id",
                self.selected_source_id,
            ),
        )
        object.__setattr__(self, "lost_wound_context", validate_json_value(self.lost_wound_context))

    @classmethod
    def from_result(cls, *, request: DecisionRequest, result: DecisionResult) -> Self:
        result.validate_for_request(request)
        payload = _payload_object(result.payload)
        source_id = payload.get("source_id")
        if source_id is not None and type(source_id) is not str:
            raise GameLifecycleError("Feel No Pain source_id must be a string or null.")
        actor_id = result.actor_id
        if actor_id is None:
            raise GameLifecycleError("FeelNoPainDecision requires a defender actor.")
        request_payload = _payload_object(request.payload)
        return cls(
            request_id=request.request_id,
            result_id=result.result_id,
            player_id=actor_id,
            selected_source_id=source_id,
            lost_wound_context=validate_json_value(request_payload["lost_wound_context"]),
        )

    def to_payload(self) -> FeelNoPainDecisionPayload:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "player_id": self.player_id,
            "selected_source_id": self.selected_source_id,
            "lost_wound_context": self.lost_wound_context,
        }


def damage_kind_from_token(token: object) -> DamageKind:
    if type(token) is DamageKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DamageKind token must be a string.")
    try:
        return DamageKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported DamageKind token: {token}.") from exc


def allocation_context_for_unit(
    *,
    state: GameState,
    target_unit_instance_id: str,
    already_allocated_model_ids: tuple[str, ...] = (),
    attacker_constraint: AttackAllocationConstraint | None = None,
) -> AttackAllocationRuleContext:
    unit = unit_by_id(state=state, unit_instance_id=target_unit_instance_id)
    alive_models = alive_placed_models(state=state, unit=unit)
    return AttackAllocationRuleContext(
        target_unit_instance_id=target_unit_instance_id,
        alive_model_ids=tuple(model.model_instance_id for model in alive_models),
        wounded_model_ids=tuple(
            model.model_instance_id
            for model in alive_models
            if model.wounds_remaining < model.starting_wounds
        ),
        already_allocated_model_ids=already_allocated_model_ids,
        attacker_constraint=attacker_constraint,
    )


def build_attack_allocation_request(
    *,
    request_id: str,
    defender_player_id: str,
    attack_context: JsonValue,
    allocation_context: AttackAllocationRuleContext,
) -> DecisionRequest:
    legal_model_ids = allocation_context.legal_model_ids()
    if len(legal_model_ids) < 2:
        raise GameLifecycleError("Attack allocation request requires at least two legal models.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        actor_id=defender_player_id,
        payload=validate_json_value(
            {
                "attack_context": validate_json_value(attack_context),
                "allocation_context": allocation_context.to_payload(),
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=model_id,
                label=model_id,
                payload={"model_instance_id": model_id},
            )
            for model_id in legal_model_ids
        ),
    )


def build_feel_no_pain_request(
    *,
    request_id: str,
    defender_player_id: str,
    lost_wound_context: JsonValue,
    sources: tuple[FeelNoPainSource, ...],
    decline_allowed: bool,
) -> DecisionRequest:
    source_tuple = _validate_feel_no_pain_sources(sources)
    if len(source_tuple) < 2 and not decline_allowed:
        raise GameLifecycleError("Feel No Pain request requires a player choice.")
    options: list[DecisionOption] = []
    if decline_allowed:
        options.append(
            DecisionOption(
                option_id="decline",
                label="Decline Feel No Pain",
                payload={"source_id": None},
            )
        )
    for source in source_tuple:
        options.append(
            DecisionOption(
                option_id=source.source_id,
                label=source.source_id,
                payload={"source_id": source.source_id},
            )
        )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        actor_id=defender_player_id,
        payload=validate_json_value(
            {
                "lost_wound_context": validate_json_value(lost_wound_context),
                "sources": [source.to_payload() for source in source_tuple],
                "decline_allowed": decline_allowed,
            }
        ),
        options=tuple(options),
    )


def feel_no_pain_roll_spec(
    *,
    source: FeelNoPainSource,
    player_id: str,
    model_instance_id: str,
    wound_index: int,
) -> DiceRollSpec:
    if type(source) is not FeelNoPainSource:
        raise GameLifecycleError("Feel No Pain roll requires a FeelNoPainSource.")
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Feel No Pain {source.source_id} for {model_instance_id} wound {wound_index}",
        roll_type="attack_sequence.feel_no_pain",
        actor_id=player_id,
    )


def resolve_feel_no_pain_rolls(
    *,
    manager: DiceRollManager,
    source: FeelNoPainSource,
    player_id: str,
    model_instance_id: str,
    requested_wounds: int,
) -> FeelNoPainResolution:
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("Feel No Pain resolution requires a DiceRollManager.")
    if type(source) is not FeelNoPainSource:
        raise GameLifecycleError("Feel No Pain resolution requires a source.")
    wounds = _validate_positive_int("requested_wounds", requested_wounds)
    actor_id = _validate_identifier("player_id", player_id)
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    rolls: list[FeelNoPainRoll] = []
    for wound_index in range(1, wounds + 1):
        roll_state = manager.roll(
            feel_no_pain_roll_spec(
                source=source,
                player_id=actor_id,
                model_instance_id=model_id,
                wound_index=wound_index,
            )
        )
        rolls.append(
            FeelNoPainRoll(
                source=source,
                roll_state=roll_state,
                successful=roll_state.current_total >= source.threshold,
            )
        )
    return FeelNoPainResolution(source=source, requested_wounds=wounds, rolls=tuple(rolls))


def apply_damage_to_model(
    *,
    state: GameState,
    target_unit_instance_id: str,
    model_instance_id: str,
    damage: int,
    damage_kind: DamageKind,
) -> DamageApplication:
    requested_damage = _validate_positive_int("damage", damage)
    kind = damage_kind_from_token(damage_kind)
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if not model.is_alive:
        raise GameLifecycleError("Damage cannot be applied to a destroyed model.")
    wounds_lost = min(model.wounds_remaining, requested_damage)
    final_wounds = model.wounds_remaining - wounds_lost
    application = DamageApplication(
        target_unit_instance_id=target_unit_instance_id,
        model_instance_id=model_instance_id,
        damage_kind=kind,
        requested_damage=requested_damage,
        wounds_lost=wounds_lost,
        excess_damage_lost=requested_damage - wounds_lost,
        starting_wounds_remaining=model.wounds_remaining,
        final_wounds_remaining=final_wounds,
        destroyed=final_wounds == 0,
    )
    _replace_model_wounds(
        state=state,
        model_instance_id=model_instance_id,
        wounds_remaining=final_wounds,
    )
    if application.destroyed:
        _remove_destroyed_model(state=state, model_instance_id=model_instance_id)
    return application


def apply_mortal_wounds_to_unit(
    *,
    state: GameState,
    target_unit_instance_id: str,
    mortal_wounds: int,
    spill_over: bool = True,
    dice_manager: DiceRollManager | None = None,
    defender_player_id: str | None = None,
) -> MortalWoundApplication:
    remaining = _validate_positive_int("mortal_wounds", mortal_wounds)
    if type(spill_over) is not bool:
        raise GameLifecycleError("spill_over must be a bool.")
    applications: list[DamageApplication] = []
    feel_no_pain_resolutions: list[FeelNoPainResolution] = []
    ignored_mortal_wounds = 0
    remaining_lost = 0
    while remaining > 0:
        context = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            already_allocated_model_ids=(),
        )
        legal_model_ids = context.legal_model_ids()
        if not legal_model_ids:
            remaining_lost = remaining
            break
        model_id = legal_model_ids[0]
        sources = _state_feel_no_pain_sources(state=state, model_instance_id=model_id)
        decline_allowed = _state_feel_no_pain_decline_allowed(
            state=state,
            model_instance_id=model_id,
        )
        if len(sources) > 0:
            if len(sources) > 1 or decline_allowed:
                raise GameLifecycleError(
                    "Mortal wound Feel No Pain choices require lifecycle routing."
                )
            source = sources[0]
            if dice_manager is None or defender_player_id is None:
                raise GameLifecycleError(
                    "Mortal wound Feel No Pain resolution requires dice manager and defender."
                )
            resolution = resolve_feel_no_pain_rolls(
                manager=dice_manager,
                source=source,
                player_id=defender_player_id,
                model_instance_id=model_id,
                requested_wounds=1,
            )
            feel_no_pain_resolutions.append(resolution)
            if resolution.ignored_wounds == 1:
                ignored_mortal_wounds += 1
                remaining -= 1
                continue
        application = apply_damage_to_model(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_id,
            damage=1,
            damage_kind=DamageKind.MORTAL,
        )
        applications.append(application)
        remaining -= 1
        if application.destroyed and not spill_over:
            remaining_lost = remaining
            remaining = 0
    return MortalWoundApplication(
        target_unit_instance_id=target_unit_instance_id,
        mortal_wounds=mortal_wounds,
        spill_over=spill_over,
        applications=tuple(applications),
        feel_no_pain_resolutions=tuple(feel_no_pain_resolutions),
        ignored_mortal_wounds=ignored_mortal_wounds,
        remaining_mortal_wounds_lost=remaining_lost,
    )


def unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("unit_instance_id is unknown.")


def model_by_id(*, state: GameState, model_instance_id: str) -> ModelInstance:
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_id:
                    return model
    raise GameLifecycleError("model_instance_id is unknown.")


def model_owner_player_id(*, state: GameState, model_instance_id: str) -> str:
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == requested_id for model in unit.own_models):
                return army.player_id
    raise GameLifecycleError("model_instance_id is unknown.")


def unit_owner_player_id(*, state: GameState, unit_instance_id: str) -> str:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        if any(unit.unit_instance_id == requested_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("unit_instance_id is unknown.")


def alive_placed_models(*, state: GameState, unit: UnitInstance) -> tuple[ModelInstance, ...]:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("alive_placed_models requires a UnitInstance.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Damage allocation requires battlefield_state.")
    placed_model_ids = set(battlefield.placed_model_ids())
    return tuple(
        model
        for model in unit.own_models
        if model.is_alive and model.model_instance_id in placed_model_ids
    )


def _replace_model_wounds(
    *,
    state: GameState,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    _validate_non_negative_int("wounds_remaining", wounds_remaining)
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != model_instance_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                did_update = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise GameLifecycleError("Cannot update wounds for unknown model.")
    state.army_definitions = updated_armies


def _remove_destroyed_model(*, state: GameState, model_instance_id: str) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Destroyed model removal requires battlefield_state.")
    try:
        state.battlefield_state = battlefield.with_removed_models((model_instance_id,))
    except PlacementError as exc:
        raise GameLifecycleError("Destroyed model removal failed.") from exc


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload {key} must be a string.")
    return value


def _validate_damage_applications(values: object) -> tuple[DamageApplication, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Damage applications must be a tuple.")
    applications: list[DamageApplication] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not DamageApplication:
            raise GameLifecycleError("Damage applications must contain DamageApplication values.")
        applications.append(value)
    return tuple(applications)


def _validate_feel_no_pain_rolls(values: object) -> tuple[FeelNoPainRoll, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Feel No Pain rolls must be a tuple.")
    rolls: list[FeelNoPainRoll] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not FeelNoPainRoll:
            raise GameLifecycleError("Feel No Pain rolls must contain FeelNoPainRoll values.")
        rolls.append(value)
    return tuple(rolls)


def _validate_feel_no_pain_resolutions(values: object) -> tuple[FeelNoPainResolution, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Feel No Pain resolutions must be a tuple.")
    resolutions: list[FeelNoPainResolution] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not FeelNoPainResolution:
            raise GameLifecycleError(
                "Feel No Pain resolutions must contain FeelNoPainResolution values."
            )
        resolutions.append(value)
    return tuple(resolutions)


def _validate_feel_no_pain_sources(values: object) -> tuple[FeelNoPainSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Feel No Pain sources must be a tuple.")
    sources: list[FeelNoPainSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not FeelNoPainSource:
            raise GameLifecycleError("Feel No Pain sources must contain FeelNoPainSource values.")
        if value.source_id in seen:
            raise GameLifecycleError("Feel No Pain sources must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _state_feel_no_pain_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[FeelNoPainSource, ...]:
    lookup = state.feel_no_pain_sources_for_model
    sources = lookup(model_instance_id=model_instance_id)
    return _validate_feel_no_pain_sources(sources)


def _state_feel_no_pain_decline_allowed(
    *,
    state: GameState,
    model_instance_id: str,
) -> bool:
    lookup = state.feel_no_pain_decline_allowed_for_model
    value = lookup(model_instance_id=model_instance_id)
    if type(value) is not bool:
        raise GameLifecycleError("Feel No Pain decline state must be a bool.")
    return value


def _validate_subset(
    *,
    field_name: str,
    values: tuple[str, ...],
    universe: tuple[str, ...],
) -> None:
    missing = set(values) - set(universe)
    if missing:
        raise GameLifecycleError(f"{field_name} contains models outside alive_model_ids.")


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
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_d6_target(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value
