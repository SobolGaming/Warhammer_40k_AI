from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import permutations, product
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
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
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_owner_player_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.game_state import GameState


SELECT_ALLOCATION_ORDER_DECISION_TYPE = "select_allocation_order"
SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE = "select_damage_allocation_model"
SELECT_PRECISION_ALLOCATION_DECISION_TYPE = "select_precision_allocation"
SELECT_FEEL_NO_PAIN_DECISION_TYPE = "select_feel_no_pain"
SELECT_DESTRUCTION_REACTION_DECISION_TYPE = "select_destruction_reaction"
MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND = "mortal_wound"


class FeelNoPainAttackCondition(StrEnum):
    PSYCHIC_ATTACK = "psychic_attack"


DECLINE_DESTRUCTION_REACTION_OPTION_ID = "decline_destruction_reaction"


class DamageKind(StrEnum):
    NORMAL = "normal"
    MORTAL = "mortal"


class DestructionReactionKind(StrEnum):
    SHOOT_ON_DEATH = "shoot_on_death"
    FIGHT_ON_DEATH = "fight_on_death"
    DEADLY_DEMISE = "deadly_demise"


class AllocationGroupRole(StrEnum):
    BODYGUARD = "bodyguard"
    CHARACTER = "character"
    LEADER = "leader"
    SUPPORT = "support"
    NON_CHARACTER = "non_character"


_CHARACTER_ALLOCATION_GROUP_ROLES = frozenset(
    (
        AllocationGroupRole.CHARACTER,
        AllocationGroupRole.LEADER,
        AllocationGroupRole.SUPPORT,
    )
)


class AttackAllocationConstraintPayload(TypedDict):
    source_rule_ids: list[str]
    allowed_model_ids: list[str] | None
    can_allocate_protected_characters: bool
    attacker_selected_model_id: str | None
    attacker_selected_group_id: str | None


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


class AllocationGroupPayload(TypedDict):
    group_id: str
    target_unit_instance_id: str
    model_ids: list[str]
    role: str
    wounds: int
    save: int | None
    invulnerable_save: int | None
    wounded_model_ids: list[str]
    already_allocated_model_ids: list[str]
    wounded: bool
    bodyguard_model_ids: list[str]
    character_model_ids: list[str]
    role_evidence: list[str]
    legality_reasons: list[str]


class AllocationOrderDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    ordered_group_ids: list[str]
    priority_group_ids: list[str]
    attack_context: JsonValue
    allocation_context: AttackAllocationRuleContextPayload
    allocation_groups: list[AllocationGroupPayload]


class DamageAllocationModelDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    selected_model_id: str
    attack_context: JsonValue
    allocation_context: AttackAllocationRuleContextPayload
    allocation_group: AllocationGroupPayload
    legal_model_ids: list[str]


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
    attack_condition: NotRequired[str]


class DestructionReactionSourcePayload(TypedDict):
    source_id: str
    reaction_kind: str
    source_rule_id: str
    payload: JsonValue
    optional: bool


class FeelNoPainDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    selected_source_id: str | None
    lost_wound_context: JsonValue


class DestructionReactionDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    selected_source_id: str | None
    selected_reaction_kind: str | None
    destruction_context: JsonValue


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


class MortalWoundFeelNoPainContextPayload(TypedDict):
    context_kind: str
    application_id: str
    source_rule_id: str
    source_context: JsonValue
    target_unit_instance_id: str
    defender_player_id: str
    model_instance_id: str
    mortal_wounds: int
    remaining_mortal_wounds: int
    spill_over: bool
    applications: list[DamageApplicationPayload]
    feel_no_pain_resolutions: list[FeelNoPainResolutionPayload]
    ignored_mortal_wounds: int
    remaining_mortal_wounds_lost: int


@dataclass(frozen=True, slots=True)
class AttackAllocationConstraint:
    source_rule_ids: tuple[str, ...] = ()
    allowed_model_ids: tuple[str, ...] | None = None
    can_allocate_protected_characters: bool = False
    attacker_selected_model_id: str | None = None
    attacker_selected_group_id: str | None = None

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
        object.__setattr__(
            self,
            "attacker_selected_group_id",
            _validate_optional_identifier(
                "AttackAllocationConstraint attacker_selected_group_id",
                self.attacker_selected_group_id,
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
            "attacker_selected_group_id": self.attacker_selected_group_id,
        }

    @classmethod
    def from_payload(cls, payload: AttackAllocationConstraintPayload) -> Self:
        allowed_model_ids = payload["allowed_model_ids"]
        return cls(
            source_rule_ids=tuple(payload["source_rule_ids"]),
            allowed_model_ids=None if allowed_model_ids is None else tuple(allowed_model_ids),
            can_allocate_protected_characters=payload["can_allocate_protected_characters"],
            attacker_selected_model_id=payload["attacker_selected_model_id"],
            attacker_selected_group_id=payload["attacker_selected_group_id"],
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

    def candidate_model_ids(self) -> tuple[str, ...]:
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
        return tuple(sorted(legal))

    def legal_model_ids(self) -> tuple[str, ...]:
        legal = self.candidate_model_ids()
        priority_ids = set(legal) & (
            set(self.wounded_model_ids) | set(self.already_allocated_model_ids)
        )
        if priority_ids:
            return tuple(sorted(priority_ids))
        return legal

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
class AllocationGroup:
    group_id: str
    target_unit_instance_id: str
    model_ids: tuple[str, ...]
    role: AllocationGroupRole
    wounds: int
    save: int | None
    invulnerable_save: int | None
    wounded_model_ids: tuple[str, ...] = ()
    already_allocated_model_ids: tuple[str, ...] = ()
    bodyguard_model_ids: tuple[str, ...] = ()
    character_model_ids: tuple[str, ...] = ()
    role_evidence: tuple[str, ...] = ()
    legality_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "group_id",
            _validate_identifier("AllocationGroup group_id", self.group_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "AllocationGroup target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        model_ids = _validate_identifier_tuple("AllocationGroup model_ids", self.model_ids)
        if not model_ids:
            raise GameLifecycleError("AllocationGroup requires models.")
        object.__setattr__(self, "model_ids", model_ids)
        object.__setattr__(self, "role", allocation_group_role_from_token(self.role))
        object.__setattr__(
            self,
            "wounds",
            _validate_positive_int("AllocationGroup wounds", self.wounds),
        )
        object.__setattr__(
            self,
            "save",
            _validate_optional_save("AllocationGroup save", self.save),
        )
        object.__setattr__(
            self,
            "invulnerable_save",
            _validate_optional_save(
                "AllocationGroup invulnerable_save",
                self.invulnerable_save,
            ),
        )
        object.__setattr__(
            self,
            "wounded_model_ids",
            _validate_identifier_tuple(
                "AllocationGroup wounded_model_ids",
                self.wounded_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "already_allocated_model_ids",
            _validate_identifier_tuple(
                "AllocationGroup already_allocated_model_ids",
                self.already_allocated_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_model_ids",
            _validate_identifier_tuple(
                "AllocationGroup bodyguard_model_ids",
                self.bodyguard_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "character_model_ids",
            _validate_identifier_tuple(
                "AllocationGroup character_model_ids",
                self.character_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "role_evidence",
            _validate_identifier_tuple("AllocationGroup role_evidence", self.role_evidence),
        )
        object.__setattr__(
            self,
            "legality_reasons",
            _validate_identifier_tuple(
                "AllocationGroup legality_reasons",
                self.legality_reasons,
            ),
        )
        _validate_subset(
            field_name="AllocationGroup wounded_model_ids",
            values=self.wounded_model_ids,
            universe=model_ids,
        )
        _validate_subset(
            field_name="AllocationGroup already_allocated_model_ids",
            values=self.already_allocated_model_ids,
            universe=model_ids,
        )

    @property
    def wounded(self) -> bool:
        return bool(self.wounded_model_ids)

    def ordered_model_ids_for_damage(self) -> tuple[str, ...]:
        priority_ids = tuple(
            model_id
            for model_id in self.model_ids
            if model_id in set(self.wounded_model_ids) | set(self.already_allocated_model_ids)
        )
        remaining_ids = tuple(
            model_id for model_id in self.model_ids if model_id not in priority_ids
        )
        return (*priority_ids, *remaining_ids)

    def to_payload(self) -> AllocationGroupPayload:
        return {
            "group_id": self.group_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "model_ids": list(self.model_ids),
            "role": self.role.value,
            "wounds": self.wounds,
            "save": self.save,
            "invulnerable_save": self.invulnerable_save,
            "wounded_model_ids": list(self.wounded_model_ids),
            "already_allocated_model_ids": list(self.already_allocated_model_ids),
            "wounded": self.wounded,
            "bodyguard_model_ids": list(self.bodyguard_model_ids),
            "character_model_ids": list(self.character_model_ids),
            "role_evidence": list(self.role_evidence),
            "legality_reasons": list(self.legality_reasons),
        }

    @classmethod
    def from_payload(cls, payload: AllocationGroupPayload) -> Self:
        return cls(
            group_id=payload["group_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            model_ids=tuple(payload["model_ids"]),
            role=allocation_group_role_from_token(payload["role"]),
            wounds=payload["wounds"],
            save=payload["save"],
            invulnerable_save=payload["invulnerable_save"],
            wounded_model_ids=tuple(payload["wounded_model_ids"]),
            already_allocated_model_ids=tuple(payload["already_allocated_model_ids"]),
            bodyguard_model_ids=tuple(payload["bodyguard_model_ids"]),
            character_model_ids=tuple(payload["character_model_ids"]),
            role_evidence=tuple(payload["role_evidence"]),
            legality_reasons=tuple(payload["legality_reasons"]),
        )


@dataclass(frozen=True, slots=True)
class AllocationOrderDecision:
    request_id: str
    result_id: str
    player_id: str
    ordered_group_ids: tuple[str, ...]
    attack_context: JsonValue
    allocation_context: AttackAllocationRuleContext
    allocation_groups: tuple[AllocationGroup, ...]
    priority_group_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("AllocationOrderDecision request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("AllocationOrderDecision result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AllocationOrderDecision player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "ordered_group_ids",
            _validate_ordered_identifier_tuple(
                "AllocationOrderDecision ordered_group_ids",
                self.ordered_group_ids,
            ),
        )
        object.__setattr__(self, "attack_context", validate_json_value(self.attack_context))
        if type(self.allocation_context) is not AttackAllocationRuleContext:
            raise GameLifecycleError(
                "AllocationOrderDecision allocation_context must be allocation context."
            )
        groups = _validate_allocation_groups(self.allocation_groups)
        object.__setattr__(self, "allocation_groups", groups)
        group_ids = tuple(group.group_id for group in groups)
        if set(self.ordered_group_ids) != set(group_ids):
            raise GameLifecycleError(
                "AllocationOrderDecision ordered groups must match legal groups."
            )
        priority_ids = _validate_identifier_tuple(
            "AllocationOrderDecision priority_group_ids",
            self.priority_group_ids,
        )
        object.__setattr__(self, "priority_group_ids", priority_ids)
        legal_orders = tuple(
            tuple(group.group_id for group in order)
            for order in legal_allocation_group_orders(
                groups,
                priority_group_ids=priority_ids,
            )
        )
        if self.ordered_group_ids not in legal_orders:
            raise GameLifecycleError(
                "AllocationOrderDecision ordered groups must match a legal allocation order."
            )

    @classmethod
    def from_result(cls, *, request: DecisionRequest, result: DecisionResult) -> Self:
        result.validate_for_request(request)
        payload = _payload_object(result.payload)
        ordered_group_ids = _payload_string_tuple(payload, key="ordered_group_ids")
        actor_id = result.actor_id
        if actor_id is None:
            raise GameLifecycleError("AllocationOrderDecision requires a defender actor.")
        request_payload = _payload_object(request.payload)
        group_payloads = request_payload["allocation_groups"]
        if not isinstance(group_payloads, list):
            raise GameLifecycleError("Allocation order request groups must be a list.")
        raw_priority_group_ids = request_payload["priority_group_ids"]
        if not isinstance(raw_priority_group_ids, list):
            raise GameLifecycleError("Allocation order priority_group_ids must be a list.")
        priority_group_ids = _validate_identifier_tuple(
            "Allocation order priority_group_ids",
            tuple(raw_priority_group_ids),
        )
        groups = tuple(
            AllocationGroup.from_payload(cast(AllocationGroupPayload, group_payload))
            for group_payload in group_payloads
        )
        return cls(
            request_id=request.request_id,
            result_id=result.result_id,
            player_id=actor_id,
            ordered_group_ids=ordered_group_ids,
            attack_context=validate_json_value(request_payload["attack_context"]),
            allocation_context=AttackAllocationRuleContext.from_payload(
                cast(AttackAllocationRuleContextPayload, request_payload["allocation_context"])
            ),
            allocation_groups=groups,
            priority_group_ids=priority_group_ids,
        )

    @property
    def selected_group_id(self) -> str:
        if not self.ordered_group_ids:
            raise GameLifecycleError("AllocationOrderDecision requires an ordered group.")
        return self.ordered_group_ids[0]

    def selected_group(self) -> AllocationGroup:
        return self.ordered_groups()[0]

    def ordered_groups(self) -> tuple[AllocationGroup, ...]:
        groups_by_id = {group.group_id: group for group in self.allocation_groups}
        ordered_groups: list[AllocationGroup] = []
        for group_id in self.ordered_group_ids:
            group = groups_by_id.get(group_id)
            if group is None:
                raise GameLifecycleError("Ordered allocation group is missing.")
            ordered_groups.append(group)
        return tuple(ordered_groups)

    def to_payload(self) -> AllocationOrderDecisionPayload:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "player_id": self.player_id,
            "ordered_group_ids": list(self.ordered_group_ids),
            "priority_group_ids": list(self.priority_group_ids),
            "attack_context": self.attack_context,
            "allocation_context": self.allocation_context.to_payload(),
            "allocation_groups": [group.to_payload() for group in self.allocation_groups],
        }


@dataclass(frozen=True, slots=True)
class DamageAllocationModelDecision:
    request_id: str
    result_id: str
    player_id: str
    selected_model_id: str
    attack_context: JsonValue
    allocation_context: AttackAllocationRuleContext
    allocation_group: AllocationGroup
    legal_model_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier(
                "DamageAllocationModelDecision request_id",
                self.request_id,
            ),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier(
                "DamageAllocationModelDecision result_id",
                self.result_id,
            ),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DamageAllocationModelDecision player_id", self.player_id),
        )
        selected_model_id = _validate_identifier(
            "DamageAllocationModelDecision selected_model_id",
            self.selected_model_id,
        )
        object.__setattr__(self, "selected_model_id", selected_model_id)
        object.__setattr__(self, "attack_context", validate_json_value(self.attack_context))
        if type(self.allocation_context) is not AttackAllocationRuleContext:
            raise GameLifecycleError(
                "DamageAllocationModelDecision allocation_context must be allocation context."
            )
        if type(self.allocation_group) is not AllocationGroup:
            raise GameLifecycleError(
                "DamageAllocationModelDecision allocation_group must be an AllocationGroup."
            )
        legal_model_ids = _validate_ordered_identifier_tuple(
            "DamageAllocationModelDecision legal_model_ids",
            self.legal_model_ids,
        )
        object.__setattr__(self, "legal_model_ids", legal_model_ids)
        if selected_model_id not in legal_model_ids:
            raise GameLifecycleError("DamageAllocationModelDecision selected model must be legal.")

    @classmethod
    def from_result(cls, *, request: DecisionRequest, result: DecisionResult) -> Self:
        result.validate_for_request(request)
        payload = _payload_object(result.payload)
        actor_id = result.actor_id
        if actor_id is None:
            raise GameLifecycleError("DamageAllocationModelDecision requires a defender actor.")
        request_payload = _payload_object(request.payload)
        return cls(
            request_id=request.request_id,
            result_id=result.result_id,
            player_id=actor_id,
            selected_model_id=_payload_string(payload, key="selected_model_id"),
            attack_context=validate_json_value(request_payload["attack_context"]),
            allocation_context=AttackAllocationRuleContext.from_payload(
                cast(AttackAllocationRuleContextPayload, request_payload["allocation_context"])
            ),
            allocation_group=AllocationGroup.from_payload(
                cast(AllocationGroupPayload, request_payload["allocation_group"])
            ),
            legal_model_ids=_payload_string_tuple(request_payload, key="legal_model_ids"),
        )

    def to_payload(self) -> DamageAllocationModelDecisionPayload:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "player_id": self.player_id,
            "selected_model_id": self.selected_model_id,
            "attack_context": self.attack_context,
            "allocation_context": self.allocation_context.to_payload(),
            "allocation_group": self.allocation_group.to_payload(),
            "legal_model_ids": list(self.legal_model_ids),
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

    @classmethod
    def from_payload(cls, payload: MortalWoundApplicationPayload) -> Self:
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            mortal_wounds=payload["mortal_wounds"],
            spill_over=payload["spill_over"],
            applications=tuple(
                DamageApplication.from_payload(application)
                for application in payload["applications"]
            ),
            feel_no_pain_resolutions=tuple(
                FeelNoPainResolution.from_payload(resolution)
                for resolution in payload["feel_no_pain_resolutions"]
            ),
            ignored_mortal_wounds=payload["ignored_mortal_wounds"],
            remaining_mortal_wounds_lost=payload["remaining_mortal_wounds_lost"],
        )


@dataclass(frozen=True, slots=True)
class MortalWoundApplicationProgress:
    application_id: str
    source_rule_id: str
    source_context: JsonValue
    target_unit_instance_id: str
    defender_player_id: str
    mortal_wounds: int
    remaining_mortal_wounds: int
    spill_over: bool
    applications: tuple[DamageApplication, ...] = ()
    feel_no_pain_resolutions: tuple[FeelNoPainResolution, ...] = ()
    ignored_mortal_wounds: int = 0
    remaining_mortal_wounds_lost: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "application_id",
            _validate_identifier(
                "MortalWoundApplicationProgress application_id",
                self.application_id,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "MortalWoundApplicationProgress source_rule_id",
                self.source_rule_id,
            ),
        )
        object.__setattr__(self, "source_context", validate_json_value(self.source_context))
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "MortalWoundApplicationProgress target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "defender_player_id",
            _validate_identifier(
                "MortalWoundApplicationProgress defender_player_id",
                self.defender_player_id,
            ),
        )
        object.__setattr__(
            self,
            "mortal_wounds",
            _validate_positive_int(
                "MortalWoundApplicationProgress mortal_wounds",
                self.mortal_wounds,
            ),
        )
        object.__setattr__(
            self,
            "remaining_mortal_wounds",
            _validate_non_negative_int(
                "MortalWoundApplicationProgress remaining_mortal_wounds",
                self.remaining_mortal_wounds,
            ),
        )
        if self.remaining_mortal_wounds > self.mortal_wounds:
            raise GameLifecycleError("MortalWoundApplicationProgress remaining wound drift.")
        if type(self.spill_over) is not bool:
            raise GameLifecycleError("MortalWoundApplicationProgress spill_over must be a bool.")
        object.__setattr__(self, "applications", _validate_damage_applications(self.applications))
        object.__setattr__(
            self,
            "feel_no_pain_resolutions",
            _validate_feel_no_pain_resolutions(self.feel_no_pain_resolutions),
        )
        object.__setattr__(
            self,
            "ignored_mortal_wounds",
            _validate_non_negative_int(
                "MortalWoundApplicationProgress ignored_mortal_wounds",
                self.ignored_mortal_wounds,
            ),
        )
        object.__setattr__(
            self,
            "remaining_mortal_wounds_lost",
            _validate_non_negative_int(
                "MortalWoundApplicationProgress remaining_mortal_wounds_lost",
                self.remaining_mortal_wounds_lost,
            ),
        )
        accounted = (
            sum(application.wounds_lost for application in self.applications)
            + self.ignored_mortal_wounds
            + self.remaining_mortal_wounds_lost
            + self.remaining_mortal_wounds
        )
        if accounted != self.mortal_wounds:
            raise GameLifecycleError("MortalWoundApplicationProgress wound accounting drift.")

    @classmethod
    def start(
        cls,
        *,
        application_id: str,
        source_rule_id: str,
        source_context: JsonValue,
        target_unit_instance_id: str,
        defender_player_id: str,
        mortal_wounds: int,
        spill_over: bool,
    ) -> Self:
        wounds = _validate_positive_int("mortal_wounds", mortal_wounds)
        return cls(
            application_id=application_id,
            source_rule_id=source_rule_id,
            source_context=source_context,
            target_unit_instance_id=target_unit_instance_id,
            defender_player_id=defender_player_id,
            mortal_wounds=wounds,
            remaining_mortal_wounds=wounds,
            spill_over=spill_over,
        )

    @classmethod
    def from_feel_no_pain_context(cls, payload: JsonValue) -> Self:
        context = _mortal_wound_context_from_payload(payload)
        return cls(
            application_id=context["application_id"],
            source_rule_id=context["source_rule_id"],
            source_context=context["source_context"],
            target_unit_instance_id=context["target_unit_instance_id"],
            defender_player_id=context["defender_player_id"],
            mortal_wounds=context["mortal_wounds"],
            remaining_mortal_wounds=context["remaining_mortal_wounds"],
            spill_over=context["spill_over"],
            applications=tuple(
                DamageApplication.from_payload(application)
                for application in context["applications"]
            ),
            feel_no_pain_resolutions=tuple(
                FeelNoPainResolution.from_payload(resolution)
                for resolution in context["feel_no_pain_resolutions"]
            ),
            ignored_mortal_wounds=context["ignored_mortal_wounds"],
            remaining_mortal_wounds_lost=context["remaining_mortal_wounds_lost"],
        )

    def to_feel_no_pain_context(
        self,
        *,
        model_instance_id: str,
    ) -> MortalWoundFeelNoPainContextPayload:
        return {
            "context_kind": MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND,
            "application_id": self.application_id,
            "source_rule_id": self.source_rule_id,
            "source_context": self.source_context,
            "target_unit_instance_id": self.target_unit_instance_id,
            "defender_player_id": self.defender_player_id,
            "model_instance_id": _validate_identifier(
                "MortalWoundApplicationProgress model_instance_id",
                model_instance_id,
            ),
            "mortal_wounds": self.mortal_wounds,
            "remaining_mortal_wounds": self.remaining_mortal_wounds,
            "spill_over": self.spill_over,
            "applications": [application.to_payload() for application in self.applications],
            "feel_no_pain_resolutions": [
                resolution.to_payload() for resolution in self.feel_no_pain_resolutions
            ],
            "ignored_mortal_wounds": self.ignored_mortal_wounds,
            "remaining_mortal_wounds_lost": self.remaining_mortal_wounds_lost,
        }

    def with_remaining_lost(self) -> Self:
        if self.remaining_mortal_wounds == 0:
            return self
        return type(self)(
            application_id=self.application_id,
            source_rule_id=self.source_rule_id,
            source_context=self.source_context,
            target_unit_instance_id=self.target_unit_instance_id,
            defender_player_id=self.defender_player_id,
            mortal_wounds=self.mortal_wounds,
            remaining_mortal_wounds=0,
            spill_over=self.spill_over,
            applications=self.applications,
            feel_no_pain_resolutions=self.feel_no_pain_resolutions,
            ignored_mortal_wounds=self.ignored_mortal_wounds,
            remaining_mortal_wounds_lost=(
                self.remaining_mortal_wounds_lost + self.remaining_mortal_wounds
            ),
        )

    def after_wound_resolution(
        self,
        *,
        state: GameState,
        model_instance_id: str,
        resolution: FeelNoPainResolution,
        remove_destroyed_model: bool = True,
    ) -> Self:
        if self.remaining_mortal_wounds < 1:
            raise GameLifecycleError("Mortal wound progress has no wound to resolve.")
        if type(resolution) is not FeelNoPainResolution:
            raise GameLifecycleError("Mortal wound progress requires Feel No Pain resolution.")
        if resolution.requested_wounds != 1:
            raise GameLifecycleError("Mortal wound Feel No Pain resolves one wound at a time.")
        if type(remove_destroyed_model) is not bool:
            raise GameLifecycleError("remove_destroyed_model must be a bool.")
        applications = list(self.applications)
        ignored = self.ignored_mortal_wounds
        remaining_lost = self.remaining_mortal_wounds_lost
        if resolution.remaining_wounds > 0:
            application = apply_damage_to_model(
                state=state,
                target_unit_instance_id=self.target_unit_instance_id,
                model_instance_id=model_instance_id,
                damage=1,
                damage_kind=DamageKind.MORTAL,
                remove_destroyed_model=remove_destroyed_model,
            )
            applications.append(application)
            if application.destroyed and not self.spill_over:
                remaining_lost += self.remaining_mortal_wounds - 1
        else:
            ignored += 1
        return type(self)(
            application_id=self.application_id,
            source_rule_id=self.source_rule_id,
            source_context=self.source_context,
            target_unit_instance_id=self.target_unit_instance_id,
            defender_player_id=self.defender_player_id,
            mortal_wounds=self.mortal_wounds,
            remaining_mortal_wounds=(
                0
                if remaining_lost != self.remaining_mortal_wounds_lost
                else self.remaining_mortal_wounds - 1
            ),
            spill_over=self.spill_over,
            applications=tuple(applications),
            feel_no_pain_resolutions=(*self.feel_no_pain_resolutions, resolution),
            ignored_mortal_wounds=ignored,
            remaining_mortal_wounds_lost=remaining_lost,
        )

    def to_application(self) -> MortalWoundApplication:
        if self.remaining_mortal_wounds != 0:
            raise GameLifecycleError("Incomplete mortal wound progress cannot be finalized.")
        return MortalWoundApplication(
            target_unit_instance_id=self.target_unit_instance_id,
            mortal_wounds=self.mortal_wounds,
            spill_over=self.spill_over,
            applications=self.applications,
            feel_no_pain_resolutions=self.feel_no_pain_resolutions,
            ignored_mortal_wounds=self.ignored_mortal_wounds,
            remaining_mortal_wounds_lost=self.remaining_mortal_wounds_lost,
        )


@dataclass(frozen=True, slots=True)
class MortalWoundRoutingResult:
    progress: MortalWoundApplicationProgress
    request: DecisionRequest | None = None
    application: MortalWoundApplication | None = None

    def __post_init__(self) -> None:
        if type(self.progress) is not MortalWoundApplicationProgress:
            raise GameLifecycleError("MortalWoundRoutingResult requires progress.")
        if self.request is not None and type(self.request) is not DecisionRequest:
            raise GameLifecycleError("MortalWoundRoutingResult request is invalid.")
        if self.application is not None and type(self.application) is not MortalWoundApplication:
            raise GameLifecycleError("MortalWoundRoutingResult application is invalid.")
        if (self.request is None) == (self.application is None):
            raise GameLifecycleError(
                "MortalWoundRoutingResult requires exactly one request or application."
            )


@dataclass(frozen=True, slots=True)
class FeelNoPainSource:
    source_id: str
    threshold: int
    attack_condition: FeelNoPainAttackCondition | None = None

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
        object.__setattr__(
            self,
            "attack_condition",
            feel_no_pain_attack_condition_from_token(self.attack_condition),
        )

    def to_payload(self) -> FeelNoPainSourcePayload:
        payload: FeelNoPainSourcePayload = {
            "source_id": self.source_id,
            "threshold": self.threshold,
        }
        if self.attack_condition is not None:
            payload["attack_condition"] = self.attack_condition.value
        return payload

    @classmethod
    def from_payload(cls, payload: FeelNoPainSourcePayload) -> Self:
        return cls(
            source_id=payload["source_id"],
            threshold=payload["threshold"],
            attack_condition=feel_no_pain_attack_condition_from_token(
                payload.get("attack_condition")
            ),
        )


@dataclass(frozen=True, slots=True)
class DestructionReactionSource:
    source_id: str
    reaction_kind: DestructionReactionKind
    source_rule_id: str
    payload: JsonValue = None
    optional: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DestructionReactionSource source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "reaction_kind",
            destruction_reaction_kind_from_token(self.reaction_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "DestructionReactionSource source_rule_id",
                self.source_rule_id,
            ),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))
        if type(self.optional) is not bool:
            raise GameLifecycleError("DestructionReactionSource optional must be a bool.")
        if self.reaction_kind is DestructionReactionKind.DEADLY_DEMISE and self.optional:
            raise GameLifecycleError("Deadly Demise destruction reactions must be mandatory.")

    def to_payload(self) -> DestructionReactionSourcePayload:
        return {
            "source_id": self.source_id,
            "reaction_kind": self.reaction_kind.value,
            "source_rule_id": self.source_rule_id,
            "payload": self.payload,
            "optional": self.optional,
        }

    @classmethod
    def from_payload(cls, payload: DestructionReactionSourcePayload) -> Self:
        return cls(
            source_id=payload["source_id"],
            reaction_kind=destruction_reaction_kind_from_token(payload["reaction_kind"]),
            source_rule_id=payload["source_rule_id"],
            payload=payload["payload"],
            optional=payload["optional"],
        )


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

    @classmethod
    def from_payload(cls, payload: FeelNoPainRollPayload) -> Self:
        return cls(
            source=FeelNoPainSource.from_payload(payload["source"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            successful=payload["successful"],
        )


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

    @classmethod
    def from_payload(cls, payload: FeelNoPainResolutionPayload) -> Self:
        source_payload = payload["source"]
        return cls(
            source=(
                None if source_payload is None else FeelNoPainSource.from_payload(source_payload)
            ),
            requested_wounds=payload["requested_wounds"],
            rolls=tuple(FeelNoPainRoll.from_payload(roll) for roll in payload["rolls"]),
        )


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


@dataclass(frozen=True, slots=True)
class DestructionReactionDecision:
    request_id: str
    result_id: str
    player_id: str
    selected_source_id: str | None
    selected_reaction_kind: DestructionReactionKind | None
    destruction_context: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("DestructionReactionDecision request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("DestructionReactionDecision result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DestructionReactionDecision player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "selected_source_id",
            _validate_optional_identifier(
                "DestructionReactionDecision selected_source_id",
                self.selected_source_id,
            ),
        )
        reaction_kind = self.selected_reaction_kind
        object.__setattr__(
            self,
            "selected_reaction_kind",
            None if reaction_kind is None else destruction_reaction_kind_from_token(reaction_kind),
        )
        if (self.selected_source_id is None) != (self.selected_reaction_kind is None):
            raise GameLifecycleError(
                "DestructionReactionDecision source and reaction kind must both be selected."
            )
        object.__setattr__(
            self,
            "destruction_context",
            validate_json_value(self.destruction_context),
        )

    @classmethod
    def from_result(cls, *, request: DecisionRequest, result: DecisionResult) -> Self:
        result.validate_for_request(request)
        payload = _payload_object(result.payload)
        source_id = payload.get("source_id")
        if source_id is not None and type(source_id) is not str:
            raise GameLifecycleError("Destruction reaction source_id must be a string or null.")
        raw_kind = payload.get("reaction_kind")
        reaction_kind = None if raw_kind is None else destruction_reaction_kind_from_token(raw_kind)
        actor_id = result.actor_id
        if actor_id is None:
            raise GameLifecycleError("DestructionReactionDecision requires an actor.")
        request_payload = _payload_object(request.payload)
        return cls(
            request_id=request.request_id,
            result_id=result.result_id,
            player_id=actor_id,
            selected_source_id=source_id,
            selected_reaction_kind=reaction_kind,
            destruction_context=validate_json_value(request_payload["destruction_context"]),
        )

    def to_payload(self) -> DestructionReactionDecisionPayload:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "player_id": self.player_id,
            "selected_source_id": self.selected_source_id,
            "selected_reaction_kind": (
                None if self.selected_reaction_kind is None else self.selected_reaction_kind.value
            ),
            "destruction_context": self.destruction_context,
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


def allocation_group_role_from_token(token: object) -> AllocationGroupRole:
    if type(token) is AllocationGroupRole:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AllocationGroupRole token must be a string.")
    try:
        return AllocationGroupRole(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported AllocationGroupRole token: {token}.") from exc


def destruction_reaction_kind_from_token(token: object) -> DestructionReactionKind:
    if type(token) is DestructionReactionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DestructionReactionKind token must be a string.")
    try:
        return DestructionReactionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported DestructionReactionKind token: {token}.") from exc


def feel_no_pain_attack_condition_from_token(
    token: object | None,
) -> FeelNoPainAttackCondition | None:
    if token is None:
        return None
    if type(token) is FeelNoPainAttackCondition:
        return token
    if type(token) is not str:
        raise GameLifecycleError("FeelNoPainAttackCondition token must be a string.")
    try:
        return FeelNoPainAttackCondition(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported FeelNoPainAttackCondition token: {token}.") from exc


def allocation_context_for_unit(
    *,
    state: GameState,
    target_unit_instance_id: str,
    already_allocated_model_ids: tuple[str, ...] = (),
    attacker_constraint: AttackAllocationConstraint | None = None,
) -> AttackAllocationRuleContext:
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    alive_models = alive_placed_models_for_rules_unit(state=state, rules_unit=rules_unit)
    bodyguard_model_ids, character_model_ids = _rules_unit_model_roles(
        state=state,
        rules_unit=rules_unit,
        alive_models=alive_models,
    )
    return AttackAllocationRuleContext(
        target_unit_instance_id=rules_unit.unit_instance_id,
        alive_model_ids=tuple(model.model_instance_id for model in alive_models),
        wounded_model_ids=tuple(
            model.model_instance_id
            for model in alive_models
            if model.wounds_remaining < model.starting_wounds
        ),
        already_allocated_model_ids=already_allocated_model_ids,
        attached_unit_bodyguard_model_ids=bodyguard_model_ids,
        attached_unit_character_model_ids=character_model_ids,
        attacker_constraint=attacker_constraint,
    )


def allocation_groups_for_context(
    *,
    state: GameState,
    allocation_context: AttackAllocationRuleContext,
    visible_model_ids: tuple[str, ...] | None = None,
    include_priority_tiers: bool = False,
) -> tuple[AllocationGroup, ...]:
    if type(allocation_context) is not AttackAllocationRuleContext:
        raise GameLifecycleError("Allocation groups require an allocation context.")
    if type(include_priority_tiers) is not bool:
        raise GameLifecycleError("include_priority_tiers must be a bool.")
    visible_id_set: set[str] | None = None
    if visible_model_ids is not None:
        visible_id_set = set(_validate_identifier_tuple("visible_model_ids", visible_model_ids))
    legal_model_ids = (
        allocation_context.candidate_model_ids()
        if include_priority_tiers
        else allocation_context.legal_model_ids()
    )
    if visible_id_set is not None:
        legal_model_ids = tuple(
            model_id for model_id in legal_model_ids if model_id in visible_id_set
        )
    if not legal_model_ids:
        return ()
    bodyguard_ids = set(allocation_context.attached_unit_bodyguard_model_ids)
    character_ids = set(allocation_context.attached_unit_character_model_ids)
    wounded_ids = set(allocation_context.wounded_model_ids)
    allocated_ids = set(allocation_context.already_allocated_model_ids)

    groups: list[AllocationGroup] = []
    non_character_models_by_profile: dict[
        tuple[int, int | None, int | None, AllocationGroupRole],
        list[ModelInstance],
    ] = {}
    for model_id in legal_model_ids:
        model = model_by_id(state=state, model_instance_id=model_id)
        wounds = model.starting_wounds
        save = _model_characteristic(model, Characteristic.SAVE)
        invulnerable = _model_characteristic(model, Characteristic.INVULNERABLE_SAVE)
        if model_id in character_ids:
            role = _character_allocation_role(model)
            groups.append(
                AllocationGroup(
                    group_id=_character_allocation_group_id(model_id),
                    target_unit_instance_id=allocation_context.target_unit_instance_id,
                    model_ids=(model_id,),
                    role=role,
                    wounds=wounds,
                    save=save,
                    invulnerable_save=invulnerable,
                    wounded_model_ids=(model_id,) if model_id in wounded_ids else (),
                    already_allocated_model_ids=(model_id,) if model_id in allocated_ids else (),
                    bodyguard_model_ids=tuple(sorted(bodyguard_ids & {model_id})),
                    character_model_ids=(model_id,),
                    role_evidence=_role_evidence_for_model(model=model, role=role),
                    legality_reasons=_allocation_group_legality_reasons(
                        model_ids=(model_id,),
                        wounded_ids=wounded_ids,
                        allocated_ids=allocated_ids,
                        bodyguard_ids=bodyguard_ids,
                        character_ids=character_ids,
                        attacker_constraint=allocation_context.attacker_constraint,
                    ),
                )
            )
            continue
        role = (
            AllocationGroupRole.BODYGUARD
            if model_id in bodyguard_ids
            else (AllocationGroupRole.NON_CHARACTER)
        )
        non_character_models_by_profile.setdefault((wounds, save, invulnerable, role), []).append(
            model
        )

    for (wounds, save, invulnerable, role), models in sorted(
        non_character_models_by_profile.items(),
        key=lambda item: (
            item[0][3].value,
            item[0][0],
            99 if item[0][1] is None else item[0][1],
            99 if item[0][2] is None else item[0][2],
            tuple(model.model_instance_id for model in item[1]),
        ),
    ):
        model_ids = tuple(model.model_instance_id for model in models)
        groups.append(
            AllocationGroup(
                group_id=_profile_allocation_group_id(
                    target_unit_instance_id=allocation_context.target_unit_instance_id,
                    role=role,
                    wounds=wounds,
                    save=save,
                    invulnerable_save=invulnerable,
                    model_ids=model_ids,
                ),
                target_unit_instance_id=allocation_context.target_unit_instance_id,
                model_ids=model_ids,
                role=role,
                wounds=wounds,
                save=save,
                invulnerable_save=invulnerable,
                wounded_model_ids=tuple(
                    model_id for model_id in model_ids if model_id in wounded_ids
                ),
                already_allocated_model_ids=tuple(
                    model_id for model_id in model_ids if model_id in allocated_ids
                ),
                bodyguard_model_ids=tuple(
                    model_id for model_id in model_ids if model_id in bodyguard_ids
                ),
                character_model_ids=tuple(
                    model_id for model_id in model_ids if model_id in character_ids
                ),
                role_evidence=_role_evidence_for_models(models=models, role=role),
                legality_reasons=_allocation_group_legality_reasons(
                    model_ids=model_ids,
                    wounded_ids=wounded_ids,
                    allocated_ids=allocated_ids,
                    bodyguard_ids=bodyguard_ids,
                    character_ids=character_ids,
                    attacker_constraint=allocation_context.attacker_constraint,
                ),
            )
        )
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                0 if group.wounded else 1,
                0 if group.already_allocated_model_ids else 1,
                group.role.value,
                group.group_id,
            ),
        )
    )


def legal_allocation_group_orders(
    allocation_groups: tuple[AllocationGroup, ...],
    *,
    priority_group_ids: tuple[str, ...] = (),
) -> tuple[tuple[AllocationGroup, ...], ...]:
    groups = _validate_allocation_groups(allocation_groups)
    priority_ids = _validate_identifier_tuple("priority_group_ids", priority_group_ids)
    if not groups:
        return ()
    group_by_id = {group.group_id: group for group in groups}
    missing_priority_ids = tuple(
        group_id for group_id in priority_ids if group_id not in group_by_id
    )
    if missing_priority_ids:
        raise GameLifecycleError("Priority allocation group is not legal.")
    priority_groups = tuple(group_by_id[group_id] for group_id in priority_ids)
    remaining_groups = tuple(group for group in groups if group.group_id not in set(priority_ids))
    tier_options = tuple(
        tuple(permutations(tier)) for tier in _allocation_order_tiers(remaining_groups) if tier
    )
    if not tier_options:
        return (priority_groups,)
    return tuple(
        (*priority_groups, *(group for tier in tier_order for group in tier))
        for tier_order in product(*tier_options)
    )


def build_allocation_order_request(
    *,
    request_id: str,
    defender_player_id: str,
    attack_context: JsonValue,
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
    attack_contexts: tuple[JsonValue, ...] = (),
    priority_group_ids: tuple[str, ...] = (),
) -> DecisionRequest:
    groups = _validate_allocation_groups(allocation_groups)
    ordered_group_options = legal_allocation_group_orders(
        groups,
        priority_group_ids=priority_group_ids,
    )
    if len(ordered_group_options) < 2:
        raise GameLifecycleError("Allocation order request requires at least two legal orders.")
    grouped_attack_contexts = tuple(validate_json_value(context) for context in attack_contexts)
    priority_ids = _validate_identifier_tuple("priority_group_ids", priority_group_ids)
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        actor_id=defender_player_id,
        payload=validate_json_value(
            {
                "attack_context": validate_json_value(attack_context),
                "attack_contexts": list(grouped_attack_contexts),
                "allocation_context": allocation_context.to_payload(),
                "allocation_groups": [group.to_payload() for group in groups],
                "priority_group_ids": list(priority_ids),
                "selection_kind": "allocation_group_order",
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=f"allocation-order-{option_index:03d}",
                label=f"allocation-order-{option_index:03d}",
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_ALLOCATION_ORDER_DECISION_TYPE,
                        "ordered_group_ids": [group.group_id for group in ordered_groups],
                        "ordered_groups": [group.to_payload() for group in ordered_groups],
                    }
                ),
            )
            for option_index, ordered_groups in enumerate(ordered_group_options, start=1)
        ),
    )


def build_damage_allocation_model_request(
    *,
    request_id: str,
    defender_player_id: str,
    attack_context: JsonValue,
    allocation_context: AttackAllocationRuleContext,
    allocation_group: AllocationGroup,
    legal_model_ids: tuple[str, ...],
    save_die: JsonValue,
) -> DecisionRequest:
    if type(allocation_context) is not AttackAllocationRuleContext:
        raise GameLifecycleError("Damage allocation model request requires an allocation context.")
    if type(allocation_group) is not AllocationGroup:
        raise GameLifecycleError("Damage allocation model request requires an allocation group.")
    model_ids = _validate_ordered_identifier_tuple(
        "Damage allocation model legal_model_ids",
        legal_model_ids,
    )
    if len(model_ids) < 2:
        raise GameLifecycleError("Damage allocation model request requires a player choice.")
    _validate_subset(
        field_name="Damage allocation model legal_model_ids",
        values=model_ids,
        universe=allocation_group.model_ids,
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        actor_id=defender_player_id,
        payload=validate_json_value(
            {
                "attack_context": validate_json_value(attack_context),
                "allocation_context": allocation_context.to_payload(),
                "allocation_group": allocation_group.to_payload(),
                "legal_model_ids": list(model_ids),
                "save_die": validate_json_value(save_die),
                "selection_kind": "damage_allocation_model",
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=model_id,
                label=model_id,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
                        "selected_model_id": model_id,
                    }
                ),
            )
            for model_id in model_ids
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


def build_destruction_reaction_request(
    *,
    request_id: str,
    defender_player_id: str,
    destruction_context: JsonValue,
    sources: tuple[DestructionReactionSource, ...],
) -> DecisionRequest:
    source_tuple = _validate_destruction_reaction_sources(sources)
    if not source_tuple:
        raise GameLifecycleError(
            "Destruction reaction request requires at least one optional source."
        )
    for source in source_tuple:
        if not source.optional:
            raise GameLifecycleError(
                "Destruction reaction request sources must require a player choice."
            )
    options: list[DecisionOption] = [
        DecisionOption(
            option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
            label="Decline Destruction Reaction",
            payload={"source_id": None, "reaction_kind": None},
        )
    ]
    for source in source_tuple:
        options.append(
            DecisionOption(
                option_id=source.source_id,
                label=source.source_id,
                payload={
                    "source_id": source.source_id,
                    "reaction_kind": source.reaction_kind.value,
                    "optional": source.optional,
                },
            )
        )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        actor_id=defender_player_id,
        payload=validate_json_value(
            {
                "destruction_context": validate_json_value(destruction_context),
                "sources": [source.to_payload() for source in source_tuple],
                "decline_option_id": DECLINE_DESTRUCTION_REACTION_OPTION_ID,
            }
        ),
        options=tuple(options),
    )


def is_mortal_wound_feel_no_pain_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Mortal wound Feel No Pain check requires a request.")
    if request.decision_type != SELECT_FEEL_NO_PAIN_DECISION_TYPE:
        return False
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    lost_wound_context = payload.get("lost_wound_context")
    if not isinstance(lost_wound_context, dict):
        return False
    return lost_wound_context.get("context_kind") == MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND


def mortal_wound_feel_no_pain_source_context(request: DecisionRequest) -> JsonValue:
    payload = _mortal_wound_context_from_request(request)
    return payload["source_context"]


def continue_mortal_wound_application(
    *,
    state: GameState,
    request_id: str,
    progress: MortalWoundApplicationProgress,
    dice_manager: DiceRollManager | None = None,
    remove_destroyed_models: bool = True,
) -> MortalWoundRoutingResult:
    if type(remove_destroyed_models) is not bool:
        raise GameLifecycleError("remove_destroyed_models must be a bool.")
    current = progress
    while current.remaining_mortal_wounds > 0:
        allocation_context = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=current.target_unit_instance_id,
            already_allocated_model_ids=(),
        )
        legal_model_ids = allocation_context.legal_model_ids()
        if not legal_model_ids:
            completed = current.with_remaining_lost()
            return MortalWoundRoutingResult(
                progress=completed,
                application=completed.to_application(),
            )
        model_id = legal_model_ids[0]
        sources = _state_feel_no_pain_sources(state=state, model_instance_id=model_id)
        decline_allowed = _state_feel_no_pain_decline_allowed(
            state=state,
            model_instance_id=model_id,
        )
        if len(sources) > 1 or (sources and decline_allowed):
            request = build_feel_no_pain_request(
                request_id=request_id,
                defender_player_id=current.defender_player_id,
                lost_wound_context=validate_json_value(
                    current.to_feel_no_pain_context(model_instance_id=model_id)
                ),
                sources=sources,
                decline_allowed=decline_allowed,
            )
            return MortalWoundRoutingResult(progress=current, request=request)
        if sources:
            if dice_manager is None:
                raise GameLifecycleError(
                    "Mortal wound Feel No Pain resolution requires dice manager."
                )
            resolution = resolve_feel_no_pain_rolls(
                manager=dice_manager,
                source=sources[0],
                player_id=current.defender_player_id,
                model_instance_id=model_id,
                requested_wounds=1,
            )
        else:
            resolution = FeelNoPainResolution.declined(requested_wounds=1)
        current = current.after_wound_resolution(
            state=state,
            model_instance_id=model_id,
            resolution=resolution,
            remove_destroyed_model=remove_destroyed_models,
        )
    return MortalWoundRoutingResult(progress=current, application=current.to_application())


def resolve_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    next_request_id: str,
    dice_manager: DiceRollManager | None = None,
    remove_destroyed_models: bool = True,
) -> MortalWoundRoutingResult:
    if type(remove_destroyed_models) is not bool:
        raise GameLifecycleError("remove_destroyed_models must be a bool.")
    decision = FeelNoPainDecision.from_result(request=request, result=result)
    context = _mortal_wound_context_from_payload(decision.lost_wound_context)
    progress = MortalWoundApplicationProgress.from_feel_no_pain_context(decision.lost_wound_context)
    selected_source = _selected_feel_no_pain_source_from_request(
        request=request,
        selected_source_id=decision.selected_source_id,
    )
    if decision.player_id != context["defender_player_id"]:
        raise GameLifecycleError("Mortal wound Feel No Pain defender drift.")
    model_id = context["model_instance_id"]
    if selected_source is None:
        resolution = FeelNoPainResolution.declined(requested_wounds=1)
    else:
        if dice_manager is None:
            raise GameLifecycleError("Mortal wound Feel No Pain decision requires dice manager.")
        resolution = resolve_feel_no_pain_rolls(
            manager=dice_manager,
            source=selected_source,
            player_id=decision.player_id,
            model_instance_id=model_id,
            requested_wounds=1,
        )
    updated = progress.after_wound_resolution(
        state=state,
        model_instance_id=model_id,
        resolution=resolution,
        remove_destroyed_model=remove_destroyed_models,
    )
    return continue_mortal_wound_application(
        state=state,
        request_id=next_request_id,
        progress=updated,
        dice_manager=dice_manager,
        remove_destroyed_models=remove_destroyed_models,
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
    remove_destroyed_model: bool = True,
) -> DamageApplication:
    requested_damage = _validate_positive_int("damage", damage)
    kind = damage_kind_from_token(damage_kind)
    if type(remove_destroyed_model) is not bool:
        raise GameLifecycleError("remove_destroyed_model must be a bool.")
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
    if application.destroyed and remove_destroyed_model:
        remove_destroyed_model_from_battlefield(state=state, model_instance_id=model_instance_id)
    return application


def remove_destroyed_model_from_battlefield(
    *,
    state: GameState,
    model_instance_id: str,
) -> None:
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if model.is_alive:
        raise GameLifecycleError("Only destroyed models can be removed from battlefield.")
    _remove_destroyed_model(state=state, model_instance_id=model_instance_id)


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
    return rules_unit_owner_player_id(state=state, unit_instance_id=unit_instance_id)


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


def alive_placed_models_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[ModelInstance, ...]:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("alive_placed_models_for_rules_unit requires a RulesUnitView.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Damage allocation requires battlefield_state.")
    placed_model_ids = set(battlefield.placed_model_ids())
    return tuple(
        model
        for model in rules_unit.own_models
        if model.is_alive and model.model_instance_id in placed_model_ids
    )


def _rules_unit_model_roles(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    alive_models: tuple[ModelInstance, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if rules_unit.is_attached_rules_unit:
        bodyguard_model_ids = rules_unit.bodyguard_model_ids(alive_models)
        character_model_ids = rules_unit.character_model_ids(alive_models)
        return bodyguard_model_ids, character_model_ids
    return _attached_unit_model_roles(
        state=state,
        unit=rules_unit.components[0].unit,
        alive_models=alive_models,
    )


def _attached_unit_model_roles(
    *,
    state: GameState,
    unit: UnitInstance,
    alive_models: tuple[ModelInstance, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not _unit_has_keyword(unit, "ATTACHED_UNIT"):
        return (), ()
    character_datasheet_ids = {
        candidate.datasheet_id
        for army in state.army_definitions
        for candidate in army.units
        if _unit_has_keyword(candidate, "CHARACTER")
    }
    character_model_ids = tuple(
        model.model_instance_id
        for model in alive_models
        if "attached-role:character" in model.source_ids
        or "attached-role:leader" in model.source_ids
        or "attached-role:support" in model.source_ids
        or "runtime-attached-unit:leader" in model.source_ids
        or "runtime-attached-unit:support" in model.source_ids
        or model.datasheet_id in character_datasheet_ids
        or any(
            source_id == f"datasheet:{datasheet_id}"
            for source_id in model.source_ids
            for datasheet_id in character_datasheet_ids
        )
    )
    if not character_model_ids or len(character_model_ids) == len(alive_models):
        return (), ()
    character_id_set = set(character_model_ids)
    bodyguard_model_ids = tuple(
        model.model_instance_id
        for model in alive_models
        if model.model_instance_id not in character_id_set
    )
    return tuple(sorted(bodyguard_model_ids)), tuple(sorted(character_model_ids))


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


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _character_allocation_role(model: ModelInstance) -> AllocationGroupRole:
    if "attached-role:leader" in model.source_ids:
        return AllocationGroupRole.LEADER
    if "attached-role:support" in model.source_ids:
        return AllocationGroupRole.SUPPORT
    return AllocationGroupRole.CHARACTER


def _role_evidence_for_model(
    *,
    model: ModelInstance,
    role: AllocationGroupRole,
) -> tuple[str, ...]:
    evidence = {
        source_id
        for source_id in model.source_ids
        if source_id.startswith(("attached-role:", "datasheet:", "runtime-attached-unit:"))
    }
    evidence.add(f"allocation-role:{role.value}")
    return tuple(sorted(evidence))


def _role_evidence_for_models(
    *,
    models: list[ModelInstance],
    role: AllocationGroupRole,
) -> tuple[str, ...]:
    evidence = {f"allocation-role:{role.value}"}
    for model in models:
        evidence.update(
            source_id
            for source_id in model.source_ids
            if source_id.startswith(("attached-role:", "datasheet:", "runtime-attached-unit:"))
        )
    return tuple(sorted(evidence))


def _allocation_group_legality_reasons(
    *,
    model_ids: tuple[str, ...],
    wounded_ids: set[str],
    allocated_ids: set[str],
    bodyguard_ids: set[str],
    character_ids: set[str],
    attacker_constraint: AttackAllocationConstraint | None,
) -> tuple[str, ...]:
    reasons = {"legal_allocation_group"}
    model_id_set = set(model_ids)
    if model_id_set & wounded_ids:
        reasons.add("wounded_group_priority")
    if model_id_set & allocated_ids:
        reasons.add("already_allocated_group_priority")
    if bodyguard_ids and character_ids and model_id_set <= bodyguard_ids:
        reasons.add("bodyguard_protects_character_groups")
    if attacker_constraint is not None:
        reasons.update(attacker_constraint.source_rule_ids)
        if attacker_constraint.attacker_selected_group_id is not None:
            reasons.add("attacker_selected_allocation_group")
        if attacker_constraint.can_allocate_protected_characters:
            reasons.add("protected_character_allocation_allowed")
    return tuple(sorted(reasons))


def _allocation_order_tiers(
    allocation_groups: tuple[AllocationGroup, ...],
) -> tuple[tuple[AllocationGroup, ...], ...]:
    groups = _validate_allocation_groups(allocation_groups)
    wounded_non_character: list[AllocationGroup] = []
    unwounded_non_character: list[AllocationGroup] = []
    wounded_character: list[AllocationGroup] = []
    unwounded_character: list[AllocationGroup] = []
    for group in groups:
        is_character_group = group.role in _CHARACTER_ALLOCATION_GROUP_ROLES
        if is_character_group and group.wounded:
            wounded_character.append(group)
        elif is_character_group:
            unwounded_character.append(group)
        elif group.wounded:
            wounded_non_character.append(group)
        else:
            unwounded_non_character.append(group)
    return tuple(
        tuple(tier)
        for tier in (
            wounded_non_character,
            unwounded_non_character,
            wounded_character,
            unwounded_character,
        )
        if tier
    )


def _character_allocation_group_id(model_instance_id: str) -> str:
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    return f"allocation-group:character:{model_id}"


def _profile_allocation_group_id(
    *,
    target_unit_instance_id: str,
    role: AllocationGroupRole,
    wounds: int,
    save: int | None,
    invulnerable_save: int | None,
    model_ids: tuple[str, ...],
) -> str:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    model_part = "-".join(_validate_identifier_tuple("model_ids", model_ids))
    save_part = "none" if save is None else str(save)
    invulnerable_part = "none" if invulnerable_save is None else str(invulnerable_save)
    return (
        f"allocation-group:{target_id}:{role.value}:w{wounds}:sv{save_part}:"
        f"inv{invulnerable_part}:{model_part}"
    )


def _model_characteristic(model: ModelInstance, characteristic: Characteristic) -> int | None:
    for value in model.characteristics:
        if value.characteristic is characteristic:
            if value.is_dash:
                return None
            return value.final
    return None


def _canonical_keyword(keyword: str) -> str:
    return keyword.upper().replace(" ", "_").replace("-", "_")


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


def _payload_string_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload {key} must be a list.")
    return _validate_ordered_identifier_tuple(key, tuple(value))


def _mortal_wound_context_from_request(
    request: DecisionRequest,
) -> MortalWoundFeelNoPainContextPayload:
    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError("DecisionRequest does not contain mortal wound context.")
    payload = _payload_object(request.payload)
    return _mortal_wound_context_from_payload(payload["lost_wound_context"])


def _mortal_wound_context_from_payload(payload: JsonValue) -> MortalWoundFeelNoPainContextPayload:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Mortal wound Feel No Pain context must be an object.")
    if payload.get("context_kind") != MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND:
        raise GameLifecycleError("Mortal wound Feel No Pain context kind is invalid.")
    source_context = validate_json_value(payload.get("source_context"))
    applications = payload.get("applications")
    resolutions = payload.get("feel_no_pain_resolutions")
    if not isinstance(applications, list):
        raise GameLifecycleError("Mortal wound applications must be a list.")
    if not isinstance(resolutions, list):
        raise GameLifecycleError("Mortal wound Feel No Pain resolutions must be a list.")
    return {
        "context_kind": MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND,
        "application_id": _payload_string(payload, key="application_id"),
        "source_rule_id": _payload_string(payload, key="source_rule_id"),
        "source_context": source_context,
        "target_unit_instance_id": _payload_string(payload, key="target_unit_instance_id"),
        "defender_player_id": _payload_string(payload, key="defender_player_id"),
        "model_instance_id": _payload_string(payload, key="model_instance_id"),
        "mortal_wounds": _payload_positive_int(payload, key="mortal_wounds"),
        "remaining_mortal_wounds": _payload_non_negative_int(
            payload,
            key="remaining_mortal_wounds",
        ),
        "spill_over": _payload_bool(payload, key="spill_over"),
        "applications": cast(list[DamageApplicationPayload], applications),
        "feel_no_pain_resolutions": cast(list[FeelNoPainResolutionPayload], resolutions),
        "ignored_mortal_wounds": _payload_non_negative_int(
            payload,
            key="ignored_mortal_wounds",
        ),
        "remaining_mortal_wounds_lost": _payload_non_negative_int(
            payload,
            key="remaining_mortal_wounds_lost",
        ),
    }


def _selected_feel_no_pain_source_from_request(
    *,
    request: DecisionRequest,
    selected_source_id: str | None,
) -> FeelNoPainSource | None:
    request_payload = _payload_object(request.payload)
    source_payloads = request_payload["sources"]
    if not isinstance(source_payloads, list):
        raise GameLifecycleError("Feel No Pain request sources must be a list.")
    sources = tuple(
        FeelNoPainSource.from_payload(cast(FeelNoPainSourcePayload, source_payload))
        for source_payload in source_payloads
    )
    if selected_source_id is None:
        return None
    for source in sources:
        if source.source_id == selected_source_id:
            return source
    raise GameLifecycleError("Selected Feel No Pain source is not in the request.")


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload {key} must be an integer.")
    return _validate_positive_int(f"Decision payload {key}", value)


def _payload_non_negative_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload {key} must be an integer.")
    return _validate_non_negative_int(f"Decision payload {key}", value)


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Decision payload {key} must be a bool.")
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


def _validate_allocation_groups(values: object) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Allocation groups must be a tuple.")
    groups: list[AllocationGroup] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not AllocationGroup:
            raise GameLifecycleError("Allocation groups must contain AllocationGroup values.")
        if value.group_id in seen:
            raise GameLifecycleError("Allocation groups must not duplicate group IDs.")
        seen.add(value.group_id)
        groups.append(value)
    return tuple(sorted(groups, key=lambda group: group.group_id))


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


def _validate_destruction_reaction_sources(
    values: object,
) -> tuple[DestructionReactionSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Destruction reaction sources must be a tuple.")
    sources: list[DestructionReactionSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestructionReactionSource:
            raise GameLifecycleError(
                "Destruction reaction sources must contain DestructionReactionSource values."
            )
        if value.source_id in seen:
            raise GameLifecycleError("Destruction reaction sources must not duplicate source IDs.")
        if value.source_id == DECLINE_DESTRUCTION_REACTION_OPTION_ID:
            raise GameLifecycleError("Destruction reaction source ID conflicts with decline.")
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
    return tuple(
        source
        for source in _validate_feel_no_pain_sources(sources)
        if source.attack_condition is None
    )


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


def _validate_ordered_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
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
    if not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(identifiers)


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


def _validate_optional_save(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_d6_target(field_name, value)


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
