from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
    RandomCharacteristicTiming,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.modifiers import (
    ModifierStack,
    ModifierStackPayload,
    RollModifier,
    RollModifierPayload,
)
from warhammer40k_core.core.ruleset_descriptor import (
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.weapon_profiles import (
    DamageProfile,
    DamageProfilePayload,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.core_stratagem_effects import (
    GO_TO_GROUND_EFFECT_KIND,
    unit_effect_hit_roll_modifier,
    unit_effect_invulnerable_save,
    unit_effects_grant_benefit_of_cover,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    AttackAllocation,
    AttackAllocationConstraint,
    AttackAllocationDecision,
    AttackAllocationPayload,
    AttackAllocationRuleContext,
    AttackAllocationRuleContextPayload,
    DamageApplication,
    DamageKind,
    FeelNoPainDecision,
    FeelNoPainResolution,
    FeelNoPainSource,
    FeelNoPainSourcePayload,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    allocation_context_for_unit,
    apply_damage_to_model,
    build_attack_allocation_request,
    build_feel_no_pain_request,
    continue_mortal_wound_application,
    damage_kind_from_token,
    is_mortal_wound_feel_no_pain_request,
    model_by_id,
    resolve_feel_no_pain_rolls,
    resolve_mortal_wound_feel_no_pain_decision,
    unit_by_id,
    unit_owner_player_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.saves import (
    SELECT_SAVING_THROW_KIND_DECISION_TYPE,
    SaveKind,
    SaveOption,
    SaveOptionPayload,
    SavingThrow,
    SavingThrowDecision,
    build_saving_throw_kind_request,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
    selected_save_option,
)
from warhammer40k_core.engine.shooting_targets import (
    shooting_dynamic_model_blockers,
    shooting_visibility_cache_key,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    DEVASTATING_WOUNDS_RULE_ID,
    FIRE_OVERWATCH_RULE_ID,
    HAZARDOUS_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
    MELTA_RULE_ID,
    PRECISION_RULE_ID,
    TWIN_LINKED_RULE_ID,
    DevastatingWoundsResolution,
    anti_keyword_critical_threshold,
    devastating_wounds_resolution,
    has_weapon_keyword,
    melta_damage_bonus,
    sustained_hits_generated_hits,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    CoverSourceReason,
    CoverSourceRecord,
    TerrainVisibilityContext,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


ATTACK_ALLOCATION_DECISION_TYPES = frozenset(
    (
        SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_SAVING_THROW_KIND_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    )
)


class AttackSequenceStep(StrEnum):
    HIT = "hit"
    CRITICAL_HIT = "critical_hit"
    WOUND = "wound"
    CRITICAL_WOUND = "critical_wound"
    ALLOCATE = "allocate"
    SAVE = "save"
    DAMAGE = "damage"


class AttackSequenceEventPayload(TypedDict):
    step: str
    sequence_id: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    payload: JsonValue


class HitRollPayload(TypedDict):
    target_number: int
    roll_state: DiceRollStatePayload | None
    unmodified_roll: int | None
    minimum_unmodified_success: int
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    skipped: bool
    generated_hits: int


class WoundRollPayload(TypedDict):
    strength: int
    toughness: int
    target_number: int
    roll_state: DiceRollStatePayload | None
    unmodified_roll: int | None
    critical_threshold: int
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    skipped: bool


class AttackSequencePayload(TypedDict):
    sequence_id: str
    attacker_player_id: str
    attacking_unit_instance_id: str
    attack_pools: list[RangedAttackPoolPayload]
    pool_index: int
    attack_index: int
    generated_hit_index: int
    current_hit_roll: HitRollPayload | None
    deferred_mortal_wounds: list[DeferredMortalWoundsPayload]


class AttackResolutionContextPayload(TypedDict):
    sequence_id: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    generated_hit_index: int
    attacker_player_id: str
    defender_player_id: str
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile_id: str
    damage_profile: DamageProfilePayload
    hit_roll: HitRollPayload
    wound_roll: WoundRollPayload
    allocation: AttackAllocationPayload | None
    save_options: list[SaveOptionPayload]


class LostWoundContextPayload(TypedDict):
    attack_context: AttackResolutionContextPayload
    allocated_model_id: str
    damage_kind: str
    requested_wounds: int
    saving_throw: JsonValue


class DeferredMortalWoundsPayload(TypedDict):
    source_rule_id: str
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int


class FastDiceGroupPayload(TypedDict):
    group_id: str
    attack_pool_ids: list[str]
    allowed: bool
    reason: str | None
    attacks: int


class AttackModifierStackSetPayload(TypedDict):
    attacks: ModifierStackPayload | None
    strength: ModifierStackPayload | None
    armor_penetration: ModifierStackPayload | None
    damage: ModifierStackPayload | None
    hit_roll_modifiers: list[RollModifierPayload]
    wound_roll_modifiers: list[RollModifierPayload]


@dataclass(frozen=True, slots=True)
class HitRoll:
    target_number: int
    roll_state: DiceRollState | None
    unmodified_roll: int | None
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    minimum_unmodified_success: int = 2
    skipped: bool = False
    generated_hits: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_number",
            _validate_d6_target("HitRoll target_number", self.target_number),
        )
        object.__setattr__(
            self,
            "minimum_unmodified_success",
            _validate_d6_minimum_success(
                "HitRoll minimum_unmodified_success",
                self.minimum_unmodified_success,
            ),
        )
        if type(self.modifier) is not int:
            raise GameLifecycleError("HitRoll modifier must be an integer.")
        if type(self.capped_modifier) is not int:
            raise GameLifecycleError("HitRoll capped_modifier must be an integer.")
        if self.capped_modifier != _cap_roll_modifier(self.modifier):
            raise GameLifecycleError("HitRoll capped_modifier does not match modifier cap.")
        if type(self.successful) is not bool:
            raise GameLifecycleError("HitRoll successful must be a bool.")
        if type(self.critical) is not bool:
            raise GameLifecycleError("HitRoll critical must be a bool.")
        if type(self.skipped) is not bool:
            raise GameLifecycleError("HitRoll skipped must be a bool.")
        object.__setattr__(
            self,
            "generated_hits",
            _validate_positive_int("HitRoll generated_hits", self.generated_hits),
        )
        if self.skipped:
            if self.roll_state is not None or self.unmodified_roll is not None:
                raise GameLifecycleError("Skipped HitRoll must not include a roll.")
            if self.final_roll is not None:
                raise GameLifecycleError("Skipped HitRoll must not include a final roll.")
            if not self.successful:
                raise GameLifecycleError("Skipped HitRoll must generate successful hits.")
            if self.critical:
                raise GameLifecycleError("Skipped HitRoll cannot be a Critical Hit.")
            return
        if self.roll_state is None:
            raise GameLifecycleError("HitRoll requires a roll_state unless skipped.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("HitRoll roll_state must be DiceRollState.")
        if type(self.unmodified_roll) is not int or not 1 <= self.unmodified_roll <= 6:
            raise GameLifecycleError("HitRoll unmodified_roll must be a D6 value.")
        if type(self.final_roll) is not int:
            raise GameLifecycleError("HitRoll final_roll must be an integer.")
        expected_success = self.unmodified_roll == 6 or (
            self.unmodified_roll >= self.minimum_unmodified_success
            and self.final_roll >= self.target_number
        )
        if self.successful != expected_success:
            raise GameLifecycleError("HitRoll success flag does not match roll semantics.")
        if self.critical != (self.unmodified_roll == 6):
            raise GameLifecycleError("HitRoll critical flag must track unmodified 6.")

    @classmethod
    def auto_hit(cls, *, target_number: int, generated_hits: int = 1) -> Self:
        return cls(
            target_number=target_number,
            roll_state=None,
            unmodified_roll=None,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=False,
            skipped=True,
            generated_hits=generated_hits,
        )

    def to_payload(self) -> HitRollPayload:
        return {
            "target_number": self.target_number,
            "roll_state": None if self.roll_state is None else self.roll_state.to_payload(),
            "unmodified_roll": self.unmodified_roll,
            "minimum_unmodified_success": self.minimum_unmodified_success,
            "modifier": self.modifier,
            "capped_modifier": self.capped_modifier,
            "final_roll": self.final_roll,
            "successful": self.successful,
            "critical": self.critical,
            "skipped": self.skipped,
            "generated_hits": self.generated_hits,
        }

    @classmethod
    def from_payload(cls, payload: HitRollPayload) -> Self:
        roll_state_payload = payload["roll_state"]
        return cls(
            target_number=payload["target_number"],
            roll_state=(
                None
                if roll_state_payload is None
                else DiceRollState.from_payload(roll_state_payload)
            ),
            unmodified_roll=payload["unmodified_roll"],
            modifier=payload["modifier"],
            capped_modifier=payload["capped_modifier"],
            final_roll=payload["final_roll"],
            successful=payload["successful"],
            critical=payload["critical"],
            minimum_unmodified_success=payload["minimum_unmodified_success"],
            skipped=payload["skipped"],
            generated_hits=payload["generated_hits"],
        )


@dataclass(frozen=True, slots=True)
class WoundRoll:
    strength: int
    toughness: int
    target_number: int
    roll_state: DiceRollState | None
    unmodified_roll: int | None
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    critical_threshold: int = 6
    skipped: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strength",
            _validate_positive_int("WoundRoll strength", self.strength),
        )
        object.__setattr__(
            self,
            "toughness",
            _validate_positive_int("WoundRoll toughness", self.toughness),
        )
        expected_target = wound_roll_target_number(strength=self.strength, toughness=self.toughness)
        if self.target_number != expected_target:
            raise GameLifecycleError("WoundRoll target_number does not match Strength/Toughness.")
        object.__setattr__(
            self,
            "critical_threshold",
            _validate_d6_target("WoundRoll critical_threshold", self.critical_threshold),
        )
        if type(self.modifier) is not int:
            raise GameLifecycleError("WoundRoll modifier must be an integer.")
        if self.capped_modifier != _cap_roll_modifier(self.modifier):
            raise GameLifecycleError("WoundRoll capped_modifier does not match modifier cap.")
        if type(self.successful) is not bool:
            raise GameLifecycleError("WoundRoll successful must be a bool.")
        if type(self.critical) is not bool:
            raise GameLifecycleError("WoundRoll critical must be a bool.")
        if type(self.skipped) is not bool:
            raise GameLifecycleError("WoundRoll skipped must be a bool.")
        if self.skipped:
            if self.roll_state is not None or self.unmodified_roll is not None:
                raise GameLifecycleError("Skipped WoundRoll must not include a roll.")
            if self.final_roll is not None:
                raise GameLifecycleError("Skipped WoundRoll must not include a final roll.")
            if not self.successful:
                raise GameLifecycleError("Skipped WoundRoll must be successful.")
            if self.critical:
                raise GameLifecycleError("Skipped WoundRoll cannot be a Critical Wound.")
            return
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("WoundRoll roll_state must be DiceRollState.")
        if type(self.unmodified_roll) is not int or not 1 <= self.unmodified_roll <= 6:
            raise GameLifecycleError("WoundRoll unmodified_roll must be a D6 value.")
        if type(self.final_roll) is not int:
            raise GameLifecycleError("WoundRoll final_roll must be an integer.")
        expected_critical = self.unmodified_roll >= self.critical_threshold
        expected_success = expected_critical or (
            self.unmodified_roll != 1 and self.final_roll >= self.target_number
        )
        if self.successful != expected_success:
            raise GameLifecycleError("WoundRoll success flag does not match roll semantics.")
        if self.critical != expected_critical:
            raise GameLifecycleError("WoundRoll critical flag must track critical threshold.")

    @classmethod
    def auto_wound(
        cls,
        *,
        strength: int,
        toughness: int,
        target_number: int,
    ) -> Self:
        return cls(
            strength=strength,
            toughness=toughness,
            target_number=target_number,
            roll_state=None,
            unmodified_roll=None,
            critical_threshold=6,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=False,
            skipped=True,
        )

    def to_payload(self) -> WoundRollPayload:
        return {
            "strength": self.strength,
            "toughness": self.toughness,
            "target_number": self.target_number,
            "roll_state": None if self.roll_state is None else self.roll_state.to_payload(),
            "unmodified_roll": self.unmodified_roll,
            "critical_threshold": self.critical_threshold,
            "modifier": self.modifier,
            "capped_modifier": self.capped_modifier,
            "final_roll": self.final_roll,
            "successful": self.successful,
            "critical": self.critical,
            "skipped": self.skipped,
        }


@dataclass(frozen=True, slots=True)
class AttackSequenceEvent:
    step: AttackSequenceStep
    sequence_id: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    payload: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "step", attack_sequence_step_from_token(self.step))
        object.__setattr__(
            self,
            "sequence_id",
            _validate_identifier("AttackSequenceEvent sequence_id", self.sequence_id),
        )
        object.__setattr__(
            self,
            "attack_context_id",
            _validate_identifier(
                "AttackSequenceEvent attack_context_id",
                self.attack_context_id,
            ),
        )
        object.__setattr__(
            self,
            "pool_index",
            _validate_non_negative_int("AttackSequenceEvent pool_index", self.pool_index),
        )
        object.__setattr__(
            self,
            "attack_index",
            _validate_non_negative_int("AttackSequenceEvent attack_index", self.attack_index),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def to_payload(self) -> AttackSequenceEventPayload:
        return {
            "step": self.step.value,
            "sequence_id": self.sequence_id,
            "attack_context_id": self.attack_context_id,
            "pool_index": self.pool_index,
            "attack_index": self.attack_index,
            "payload": self.payload,
        }


AttackSequenceEventHandler = Callable[[AttackSequenceEvent], AttackSequenceEvent]


@dataclass(frozen=True, slots=True)
class AttackSequenceHooks:
    handlers: tuple[AttackSequenceEventHandler, ...] = ()

    def __post_init__(self) -> None:
        if type(self.handlers) is not tuple:
            raise GameLifecycleError("AttackSequenceHooks handlers must be a tuple.")
        for handler in self.handlers:
            if not callable(handler):
                raise GameLifecycleError("AttackSequenceHooks handlers must be callable.")

    @classmethod
    def empty(cls) -> Self:
        return cls()

    def emit(self, event: AttackSequenceEvent) -> AttackSequenceEvent:
        if type(event) is not AttackSequenceEvent:
            raise GameLifecycleError("AttackSequenceHooks emit requires an event.")
        current = event
        for handler in self.handlers:
            updated = handler(current)
            if type(updated) is not AttackSequenceEvent:
                raise GameLifecycleError("Attack sequence hook must return a typed event.")
            if updated.step is not current.step:
                raise GameLifecycleError("Attack sequence hook cannot move timing windows.")
            current = updated
        return current


@dataclass(frozen=True, slots=True)
class AttackModifierStackSet:
    attacks: ModifierStack | None = None
    strength: ModifierStack | None = None
    armor_penetration: ModifierStack | None = None
    damage: ModifierStack | None = None
    hit_roll_modifiers: tuple[RollModifier, ...] = ()
    wound_roll_modifiers: tuple[RollModifier, ...] = ()

    def __post_init__(self) -> None:
        for stack in (self.attacks, self.strength, self.armor_penetration, self.damage):
            if stack is not None and type(stack) is not ModifierStack:
                raise GameLifecycleError("AttackModifierStackSet stacks must be ModifierStack.")
        object.__setattr__(
            self,
            "hit_roll_modifiers",
            _validate_roll_modifier_tuple(
                "AttackModifierStackSet hit_roll_modifiers",
                self.hit_roll_modifiers,
            ),
        )
        object.__setattr__(
            self,
            "wound_roll_modifiers",
            _validate_roll_modifier_tuple(
                "AttackModifierStackSet wound_roll_modifiers",
                self.wound_roll_modifiers,
            ),
        )

    def to_payload(self) -> AttackModifierStackSetPayload:
        return {
            "attacks": None if self.attacks is None else self.attacks.to_payload(),
            "strength": None if self.strength is None else self.strength.to_payload(),
            "armor_penetration": (
                None if self.armor_penetration is None else self.armor_penetration.to_payload()
            ),
            "damage": None if self.damage is None else self.damage.to_payload(),
            "hit_roll_modifiers": [modifier.to_payload() for modifier in self.hit_roll_modifiers],
            "wound_roll_modifiers": [
                modifier.to_payload() for modifier in self.wound_roll_modifiers
            ],
        }


@dataclass(frozen=True, slots=True)
class DeferredMortalWounds:
    source_rule_id: str
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DeferredMortalWounds source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "DeferredMortalWounds target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attack_context_id",
            _validate_identifier(
                "DeferredMortalWounds attack_context_id",
                self.attack_context_id,
            ),
        )
        object.__setattr__(
            self,
            "mortal_wounds",
            _validate_positive_int("DeferredMortalWounds mortal_wounds", self.mortal_wounds),
        )

    def to_payload(self) -> DeferredMortalWoundsPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "attack_context_id": self.attack_context_id,
            "mortal_wounds": self.mortal_wounds,
        }

    @classmethod
    def from_payload(cls, payload: DeferredMortalWoundsPayload) -> Self:
        return cls(
            source_rule_id=payload["source_rule_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            attack_context_id=payload["attack_context_id"],
            mortal_wounds=payload["mortal_wounds"],
        )


@dataclass(frozen=True, slots=True)
class AttackSequence:
    sequence_id: str
    attacker_player_id: str
    attacking_unit_instance_id: str
    attack_pools: tuple[RangedAttackPool, ...]
    pool_index: int = 0
    attack_index: int = 0
    generated_hit_index: int = 0
    current_hit_roll: HitRoll | None = None
    deferred_mortal_wounds: tuple[DeferredMortalWounds, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence_id",
            _validate_identifier("AttackSequence sequence_id", self.sequence_id),
        )
        object.__setattr__(
            self,
            "attacker_player_id",
            _validate_identifier("AttackSequence attacker_player_id", self.attacker_player_id),
        )
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "AttackSequence attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attack_pools",
            _validate_attack_pools(self.attack_pools),
        )
        object.__setattr__(
            self,
            "pool_index",
            _validate_non_negative_int("AttackSequence pool_index", self.pool_index),
        )
        object.__setattr__(
            self,
            "attack_index",
            _validate_non_negative_int("AttackSequence attack_index", self.attack_index),
        )
        object.__setattr__(
            self,
            "generated_hit_index",
            _validate_non_negative_int(
                "AttackSequence generated_hit_index",
                self.generated_hit_index,
            ),
        )
        if self.current_hit_roll is not None and type(self.current_hit_roll) is not HitRoll:
            raise GameLifecycleError("AttackSequence current_hit_roll must be a HitRoll.")
        object.__setattr__(
            self,
            "deferred_mortal_wounds",
            _validate_deferred_mortal_wounds(self.deferred_mortal_wounds),
        )
        if self.pool_index > len(self.attack_pools):
            raise GameLifecycleError("AttackSequence pool_index is outside attack_pools.")
        if self.pool_index == len(self.attack_pools):
            if self.attack_index != 0:
                raise GameLifecycleError("Completed AttackSequence must have attack_index 0.")
            if self.generated_hit_index != 0:
                raise GameLifecycleError("Completed AttackSequence must not track generated hits.")
            if self.current_hit_roll is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence must not include a current hit roll."
                )
            return
        if self.attack_index >= self.attack_pools[self.pool_index].attacks:
            raise GameLifecycleError("AttackSequence attack_index is outside current pool.")
        if self.generated_hit_index > 0:
            if self.current_hit_roll is None:
                raise GameLifecycleError("Generated hit continuation requires a hit roll.")
            if self.current_hit_roll.generated_hits <= self.generated_hit_index:
                raise GameLifecycleError("Generated hit index is outside generated hits.")
            if not self.current_hit_roll.successful:
                raise GameLifecycleError("Generated hit continuation requires a successful hit.")
        elif self.current_hit_roll is not None:
            raise GameLifecycleError("Initial attack must not store a current hit roll.")

    @classmethod
    def start(
        cls,
        *,
        sequence_id: str,
        attacker_player_id: str,
        attacking_unit_instance_id: str,
        attack_pools: tuple[RangedAttackPool, ...],
    ) -> Self:
        return cls(
            sequence_id=sequence_id,
            attacker_player_id=attacker_player_id,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attack_pools=attack_pools,
        )

    @property
    def is_complete(self) -> bool:
        return self.pool_index == len(self.attack_pools)

    def current_pool(self) -> RangedAttackPool:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence has no current pool.")
        return self.attack_pools[self.pool_index]

    def attack_context_id(self) -> str:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence has no attack context.")
        context_id = (
            f"{self.sequence_id}:pool-{self.pool_index + 1:03d}:attack-{self.attack_index + 1:03d}"
        )
        if self.generated_hit_index > 0:
            return f"{context_id}:generated-hit-{self.generated_hit_index + 1:03d}"
        return context_id

    def advanced_after_attack(self) -> Self:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence cannot advance.")
        if self.generated_hit_index != 0 or self.current_hit_roll is not None:
            raise GameLifecycleError("AttackSequence cannot skip unresolved generated hits.")
        pool = self.current_pool()
        next_attack_index = self.attack_index + 1
        if next_attack_index < pool.attacks:
            return type(self)(
                sequence_id=self.sequence_id,
                attacker_player_id=self.attacker_player_id,
                attacking_unit_instance_id=self.attacking_unit_instance_id,
                attack_pools=self.attack_pools,
                pool_index=self.pool_index,
                attack_index=next_attack_index,
                deferred_mortal_wounds=self.deferred_mortal_wounds,
            )
        next_pool_index = self.pool_index + 1
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            pool_index=next_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
        )

    def advanced_after_generated_hit(self, hit_roll: HitRoll) -> Self:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence cannot advance generated hits.")
        if type(hit_roll) is not HitRoll:
            raise GameLifecycleError("Generated hit advancement requires a HitRoll.")
        if not hit_roll.successful:
            raise GameLifecycleError("Generated hit advancement requires a successful hit.")
        next_generated_hit_index = self.generated_hit_index + 1
        if next_generated_hit_index >= hit_roll.generated_hits:
            return type(self)(
                sequence_id=self.sequence_id,
                attacker_player_id=self.attacker_player_id,
                attacking_unit_instance_id=self.attacking_unit_instance_id,
                attack_pools=self.attack_pools,
                pool_index=self.pool_index,
                attack_index=self.attack_index,
                deferred_mortal_wounds=self.deferred_mortal_wounds,
            ).advanced_after_attack()
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=next_generated_hit_index,
            current_hit_roll=hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
        )

    def with_deferred_mortal_wounds(self, deferred: DeferredMortalWounds) -> Self:
        if type(deferred) is not DeferredMortalWounds:
            raise GameLifecycleError("AttackSequence deferred mortal wounds are invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=(*self.deferred_mortal_wounds, deferred),
        )

    def without_deferred_mortal_wounds(self) -> Self:
        return self.with_pending_deferred_mortal_wounds(())

    def with_pending_deferred_mortal_wounds(
        self,
        deferred_mortal_wounds: tuple[DeferredMortalWounds, ...],
    ) -> Self:
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=deferred_mortal_wounds,
        )

    def to_payload(self) -> AttackSequencePayload:
        return {
            "sequence_id": self.sequence_id,
            "attacker_player_id": self.attacker_player_id,
            "attacking_unit_instance_id": self.attacking_unit_instance_id,
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "pool_index": self.pool_index,
            "attack_index": self.attack_index,
            "generated_hit_index": self.generated_hit_index,
            "current_hit_roll": (
                None if self.current_hit_roll is None else self.current_hit_roll.to_payload()
            ),
            "deferred_mortal_wounds": [
                deferred.to_payload() for deferred in self.deferred_mortal_wounds
            ],
        }

    @classmethod
    def from_payload(cls, payload: AttackSequencePayload) -> Self:
        return cls(
            sequence_id=payload["sequence_id"],
            attacker_player_id=payload["attacker_player_id"],
            attacking_unit_instance_id=payload["attacking_unit_instance_id"],
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            pool_index=payload["pool_index"],
            attack_index=payload["attack_index"],
            generated_hit_index=payload["generated_hit_index"],
            current_hit_roll=(
                None
                if payload["current_hit_roll"] is None
                else HitRoll.from_payload(payload["current_hit_roll"])
            ),
            deferred_mortal_wounds=tuple(
                DeferredMortalWounds.from_payload(deferred)
                for deferred in payload["deferred_mortal_wounds"]
            ),
        )


@dataclass(frozen=True, slots=True)
class FastDiceGroup:
    group_id: str
    attack_pool_ids: tuple[str, ...]
    allowed: bool
    reason: str | None
    attacks: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "group_id",
            _validate_identifier("FastDiceGroup group_id", self.group_id),
        )
        object.__setattr__(
            self,
            "attack_pool_ids",
            _validate_identifier_tuple("FastDiceGroup attack_pool_ids", self.attack_pool_ids),
        )
        if type(self.allowed) is not bool:
            raise GameLifecycleError("FastDiceGroup allowed must be a bool.")
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("FastDiceGroup reason", self.reason),
        )
        object.__setattr__(
            self,
            "attacks",
            _validate_non_negative_int("FastDiceGroup attacks", self.attacks),
        )
        if self.allowed and self.reason is not None:
            raise GameLifecycleError("Allowed FastDiceGroup must not include reason.")
        if not self.allowed and self.reason is None:
            raise GameLifecycleError("Rejected FastDiceGroup requires reason.")

    @classmethod
    def evaluate(
        cls,
        *,
        group_id: str,
        pools: tuple[RangedAttackPool, ...],
        allocation_order_can_affect_random_damage: bool,
    ) -> Self:
        pool_tuple = _validate_fast_dice_pools(pools)
        if not pool_tuple:
            return cls(
                group_id=group_id,
                attack_pool_ids=(),
                allowed=False,
                reason="empty_group",
                attacks=0,
            )
        first = pool_tuple[0]
        first_key = _fast_dice_pool_key(first)
        for pool in pool_tuple[1:]:
            if _fast_dice_pool_key(pool) != first_key:
                return cls(
                    group_id=group_id,
                    attack_pool_ids=tuple(_pool_id(pool) for pool in pool_tuple),
                    allowed=False,
                    reason="attack_characteristics_or_target_differ",
                    attacks=sum(pool.attacks for pool in pool_tuple),
                )
        if (
            allocation_order_can_affect_random_damage
            and first.weapon_profile.damage_profile.dice_expression is not None
        ):
            return cls(
                group_id=group_id,
                attack_pool_ids=tuple(_pool_id(pool) for pool in pool_tuple),
                allowed=False,
                reason="random_damage_order_can_affect_outcome",
                attacks=sum(pool.attacks for pool in pool_tuple),
            )
        return cls(
            group_id=group_id,
            attack_pool_ids=tuple(_pool_id(pool) for pool in pool_tuple),
            allowed=True,
            reason=None,
            attacks=sum(pool.attacks for pool in pool_tuple),
        )

    def to_payload(self) -> FastDiceGroupPayload:
        return {
            "group_id": self.group_id,
            "attack_pool_ids": list(self.attack_pool_ids),
            "allowed": self.allowed,
            "reason": self.reason,
            "attacks": self.attacks,
        }


def attack_sequence_step_from_token(token: object) -> AttackSequenceStep:
    if type(token) is AttackSequenceStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AttackSequenceStep token must be a string.")
    try:
        return AttackSequenceStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported AttackSequenceStep token: {token}.") from exc


def wound_roll_target_number(*, strength: int, toughness: int) -> int:
    valid_strength = _validate_positive_int("strength", strength)
    valid_toughness = _validate_positive_int("toughness", toughness)
    if valid_strength >= 2 * valid_toughness:
        return 2
    if valid_strength > valid_toughness:
        return 3
    if valid_strength == valid_toughness:
        return 4
    if 2 * valid_strength <= valid_toughness:
        return 6
    return 5


def resolve_attack_sequence_until_blocked(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    active_hooks = AttackSequenceHooks.empty() if hooks is None else hooks
    allocated_model_ids = already_allocated_model_ids
    current = attack_sequence
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    while not current.is_complete:
        attack_context = _roll_hit_and_wound(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=current,
            hooks=active_hooks,
        )
        if attack_context is None:
            current = current.advanced_after_attack()
            continue
        if not attack_context["wound_roll"]["successful"]:
            current = _advance_after_resolved_hit(
                attack_sequence=current,
                attack_context=attack_context,
            )
            continue
        devastating_sequence = _defer_devastating_mortal_wounds_if_needed(
            decisions=decisions,
            manager=manager,
            attack_sequence=current,
            attack_context=attack_context,
            hooks=active_hooks,
        )
        if devastating_sequence is not None:
            current = devastating_sequence
            continue

        precision_request = _precision_request_if_available(
            state=state,
            attack_sequence=current,
            attack_context=attack_context,
            allocated_model_ids=allocated_model_ids,
        )
        if precision_request is not None:
            decisions.request_decision(precision_request)
            return (
                current,
                allocated_model_ids,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=precision_request,
                    payload={
                        "phase": BattlePhase.SHOOTING.value,
                        "decision_type": SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
                        "attack_context_id": current.attack_context_id(),
                    },
                ),
            )

        next_sequence, allocated_model_ids, status = _resolve_allocation_stage(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            manager=manager,
            attack_sequence=current,
            attack_context=attack_context,
            allocated_model_ids=allocated_model_ids,
            hooks=active_hooks,
            attacker_constraint=None,
        )
        if status is not None:
            return next_sequence, allocated_model_ids, status
        if next_sequence is None:
            return None, allocated_model_ids, None
        current = next_sequence
    current, status = _apply_deferred_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=current,
    )
    if status is not None:
        return current, allocated_model_ids, status
    decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": current.sequence_id,
            "attacker_player_id": current.attacker_player_id,
            "attacking_unit_instance_id": current.attacking_unit_instance_id,
        },
    )
    _resolve_hazardous_tests(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=current,
    )
    return None, allocated_model_ids, None


def apply_attack_allocation_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    decision = AttackAllocationDecision.from_result(request=request, result=result)
    request_payload = _payload_object(request.payload)
    allocation_context = AttackAllocationRuleContext.from_payload(
        cast(AttackAllocationRuleContextPayload, request_payload["allocation_context"])
    )
    allocation = AttackAllocation.from_context(
        allocation_context,
        allocated_model_id=decision.selected_model_id,
        forced=False,
    )
    return _continue_after_allocation(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_sequence=attack_sequence,
        attack_context=cast(AttackResolutionContextPayload, decision.attack_context),
        allocation=allocation,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
    )


def apply_precision_allocation_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    result.validate_for_request(request)
    request_payload = _payload_object(request.payload)
    attack_context = cast(AttackResolutionContextPayload, request_payload["attack_context"])
    _validate_lost_wound_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    )
    selected_model_id = _precision_selected_model_id(result.payload)
    eligible_character_ids = _precision_eligible_character_ids(request_payload)
    attacker_constraint = None
    if selected_model_id is not None:
        if selected_model_id not in eligible_character_ids:
            raise GameLifecycleError("Precision selected model is not eligible.")
        attacker_constraint = AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            allowed_model_ids=(selected_model_id,),
            can_allocate_protected_characters=True,
            attacker_selected_model_id=selected_model_id,
        )
    return _resolve_allocation_stage(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        attacker_constraint=attacker_constraint,
    )


def apply_saving_throw_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    decision = SavingThrowDecision.from_result(request=request, result=result)
    request_payload = _payload_object(request.payload)
    raw_options = request_payload["save_options"]
    if not isinstance(raw_options, list):
        raise GameLifecycleError("Saving throw request save_options must be a list.")
    options = tuple(
        SaveOption.from_payload(cast(SaveOptionPayload, option)) for option in raw_options
    )
    option = selected_save_option(
        options=options,
        selected_save_kind=decision.selected_save_kind,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    return _resolve_save_and_damage(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=cast(AttackResolutionContextPayload, decision.attack_context),
        save_option=option,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
    )


def apply_feel_no_pain_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    if is_mortal_wound_feel_no_pain_request(request):
        return _apply_deferred_mortal_wound_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
            request=request,
            already_allocated_model_ids=already_allocated_model_ids,
            dice_manager=dice_manager,
        )
    decision = FeelNoPainDecision.from_result(request=request, result=result)
    request_payload = _payload_object(request.payload)
    source_payloads = request_payload["sources"]
    if not isinstance(source_payloads, list):
        raise GameLifecycleError("Feel No Pain request sources must be a list.")
    sources = tuple(
        FeelNoPainSource.from_payload(cast(FeelNoPainSourcePayload, source_payload))
        for source_payload in source_payloads
    )
    selected_source: FeelNoPainSource | None = None
    if decision.selected_source_id is not None:
        for source in sources:
            if source.source_id == decision.selected_source_id:
                selected_source = source
                break
        if selected_source is None:
            raise GameLifecycleError("Selected Feel No Pain source is not in the request.")
    lost_wound_context = _lost_wound_context_from_payload(decision.lost_wound_context)
    attack_context = lost_wound_context["attack_context"]
    _validate_lost_wound_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    )
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    if selected_source is None:
        resolution = FeelNoPainResolution.declined(
            requested_wounds=lost_wound_context["requested_wounds"]
        )
    else:
        resolution = resolve_feel_no_pain_rolls(
            manager=manager,
            source=selected_source,
            player_id=attack_context["defender_player_id"],
            model_instance_id=lost_wound_context["allocated_model_id"],
            requested_wounds=lost_wound_context["requested_wounds"],
        )
    return _apply_damage_after_feel_no_pain(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        model_instance_id=lost_wound_context["allocated_model_id"],
        damage_kind=damage_kind_from_token(lost_wound_context["damage_kind"]),
        resolution=resolution,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        saving_throw_payload=lost_wound_context["saving_throw"],
    )


def _defer_devastating_mortal_wounds_if_needed(
    *,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    hooks: AttackSequenceHooks,
) -> AttackSequence | None:
    pool = attack_sequence.current_pool()
    resolution = _devastating_wounds_resolution_for_attack(
        pool=pool,
        attack_context=attack_context,
    )
    if resolution is not DevastatingWoundsResolution.MORTAL_WOUNDS:
        return None
    mortal_wounds = _damage_value(
        manager=manager,
        profile=pool.weapon_profile.damage_profile,
        attack_context_id=attack_context["attack_context_id"],
        attacker_player_id=attack_sequence.attacker_player_id,
    ) + _melta_damage_modifier(pool)
    deferred = DeferredMortalWounds(
        source_rule_id=DEVASTATING_WOUNDS_RULE_ID,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        attack_context_id=attack_context["attack_context_id"],
        mortal_wounds=mortal_wounds,
    )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.DAMAGE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_sequence.attack_context_id(),
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=validate_json_value(
                {
                    "saving_throw": None,
                    "damage_application": None,
                    "feel_no_pain": None,
                    "deferred_mortal_wounds": deferred.to_payload(),
                }
            ),
        ),
    )
    decisions.event_log.append(
        "devastating_wounds_deferred",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_context["attack_context_id"],
            "target_unit_instance_id": attack_context["target_unit_instance_id"],
            "mortal_wounds": mortal_wounds,
            "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
        },
    )
    return _advance_after_resolved_hit(
        attack_sequence=attack_sequence.with_deferred_mortal_wounds(deferred),
        attack_context=attack_context,
    )


def _apply_deferred_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    if not attack_sequence.deferred_mortal_wounds:
        return attack_sequence, None
    target_order: list[str] = []
    mortal_wounds_by_target: dict[str, int] = {}
    attack_context_ids_by_target: dict[str, list[str]] = {}
    for deferred in attack_sequence.deferred_mortal_wounds:
        if deferred.target_unit_instance_id not in mortal_wounds_by_target:
            target_order.append(deferred.target_unit_instance_id)
        current = mortal_wounds_by_target.get(deferred.target_unit_instance_id, 0)
        mortal_wounds_by_target[deferred.target_unit_instance_id] = current + deferred.mortal_wounds
        attack_context_ids_by_target.setdefault(deferred.target_unit_instance_id, []).append(
            deferred.attack_context_id
        )
    for target_index, target_unit_id in enumerate(target_order):
        mortal_wounds = mortal_wounds_by_target[target_unit_id]
        remaining_target_ids = frozenset(target_order[target_index + 1 :])
        sequence_after_current_target = attack_sequence.with_pending_deferred_mortal_wounds(
            tuple(
                deferred
                for deferred in attack_sequence.deferred_mortal_wounds
                if deferred.target_unit_instance_id in remaining_target_ids
            )
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{attack_sequence.sequence_id}:devastating-wounds:{target_unit_id}:mortal-wounds"
            ),
            source_rule_id=DEVASTATING_WOUNDS_RULE_ID,
            source_context=validate_json_value(
                {
                    "source_kind": "devastating_wounds",
                    "sequence_id": attack_sequence.sequence_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "target_unit_instance_id": target_unit_id,
                    "attack_context_ids": attack_context_ids_by_target[target_unit_id],
                }
            ),
            target_unit_instance_id=target_unit_id,
            defender_player_id=unit_owner_player_id(
                state=state,
                unit_instance_id=target_unit_id,
            ),
            mortal_wounds=mortal_wounds,
            spill_over=True,
        )
        routed = continue_mortal_wound_application(
            state=state,
            request_id=state.next_decision_request_id(),
            progress=progress,
            dice_manager=manager,
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return (
                sequence_after_current_target,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=routed.request,
                    payload={
                        "phase": BattlePhase.SHOOTING.value,
                        "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
                    },
                ),
            )
        if routed.application is None:
            raise GameLifecycleError("Deferred mortal wounds did not produce application.")
        _emit_deferred_mortal_wounds_applied(
            decisions=decisions,
            attack_sequence=attack_sequence,
            target_unit_id=target_unit_id,
            attack_context_ids=tuple(attack_context_ids_by_target[target_unit_id]),
            mortal_wounds=mortal_wounds,
            application=routed.application,
        )
    return attack_sequence.without_deferred_mortal_wounds(), None


def _emit_deferred_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    target_unit_id: str,
    attack_context_ids: tuple[str, ...],
    mortal_wounds: int,
    application: MortalWoundApplication,
) -> None:
    decisions.event_log.append(
        "devastating_wounds_mortal_wounds_applied",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "target_unit_instance_id": target_unit_id,
            "attack_context_ids": list(attack_context_ids),
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": application.to_payload(),
            "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
        },
    )


def _apply_deferred_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    request: DecisionRequest,
    already_allocated_model_ids: tuple[str, ...],
    dice_manager: DiceRollManager | None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return (
            attack_sequence,
            already_allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.request,
                payload={
                    "phase": BattlePhase.SHOOTING.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
                },
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Deferred mortal wound Feel No Pain did not finish routing.")
    source_context = _payload_object(routed.progress.source_context)
    raw_attack_context_ids = source_context.get("attack_context_ids")
    if not isinstance(raw_attack_context_ids, list):
        raise GameLifecycleError("Deferred mortal wound source context is missing attacks.")
    attack_context_ids = tuple(
        _validate_identifier("Deferred mortal wound attack_context_id", value)
        for value in raw_attack_context_ids
    )
    _emit_deferred_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        target_unit_id=routed.progress.target_unit_instance_id,
        attack_context_ids=attack_context_ids,
        mortal_wounds=routed.progress.mortal_wounds,
        application=routed.application,
    )
    next_sequence, status = _apply_deferred_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
    )
    return next_sequence, already_allocated_model_ids, status


def _precision_request_if_available(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    allocated_model_ids: tuple[str, ...],
) -> DecisionRequest | None:
    pool = attack_sequence.current_pool()
    if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION):
        return None
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        already_allocated_model_ids=_alive_allocated_model_ids(
            state=state,
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=None,
    )
    eligible_character_ids = tuple(
        sorted(
            set(allocation_context.attached_unit_character_model_ids)
            & set(pool.target_visible_model_ids)
        )
    )
    if not eligible_character_ids:
        return None
    return _build_precision_allocation_request(
        request_id=state.next_decision_request_id(),
        attacker_player_id=attack_context["attacker_player_id"],
        attack_context=validate_json_value(attack_context),
        allocation_context=allocation_context,
        eligible_character_ids=eligible_character_ids,
    )


def _build_precision_allocation_request(
    *,
    request_id: str,
    attacker_player_id: str,
    attack_context: JsonValue,
    allocation_context: AttackAllocationRuleContext,
    eligible_character_ids: tuple[str, ...],
) -> DecisionRequest:
    character_ids = _validate_identifier_tuple(
        "Precision eligible_character_ids",
        eligible_character_ids,
    )
    if not character_ids:
        raise GameLifecycleError("Precision allocation request requires eligible characters.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        actor_id=attacker_player_id,
        payload=validate_json_value(
            {
                "attack_context": attack_context,
                "allocation_context": allocation_context.to_payload(),
                "eligible_character_model_ids": list(character_ids),
                "decline_option_id": "decline_precision",
                "source_rule_id": PRECISION_RULE_ID,
            }
        ),
        options=(
            DecisionOption(
                option_id="decline_precision",
                label="Decline Precision",
                payload={"selected_model_id": None},
            ),
            *(
                DecisionOption(
                    option_id=model_id,
                    label=model_id,
                    payload={"selected_model_id": model_id},
                )
                for model_id in character_ids
            ),
        ),
    )


def _resolve_allocation_stage(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    attacker_constraint: AttackAllocationConstraint | None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        already_allocated_model_ids=_alive_allocated_model_ids(
            state=state,
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=attacker_constraint,
    )
    legal_model_ids = allocation_context.legal_model_ids()
    if not legal_model_ids:
        raise GameLifecycleError("Attack allocation has no legal target models.")
    if len(legal_model_ids) > 1:
        request = build_attack_allocation_request(
            request_id=state.next_decision_request_id(),
            defender_player_id=attack_context["defender_player_id"],
            attack_context=validate_json_value(attack_context),
            allocation_context=allocation_context,
        )
        decisions.request_decision(request)
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.ALLOCATE,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=attack_sequence.attack_context_id(),
                pool_index=attack_sequence.pool_index,
                attack_index=attack_sequence.attack_index,
                payload=validate_json_value(
                    {
                        "allocation_context": allocation_context.to_payload(),
                        "forced": False,
                    }
                ),
            ),
        )
        return (
            attack_sequence,
            allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": BattlePhase.SHOOTING.value,
                    "decision_type": SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
                    "attack_context_id": attack_sequence.attack_context_id(),
                },
            ),
        )

    if len(legal_model_ids) != 1:
        raise GameLifecycleError("Forced allocation requires exactly one legal model.")
    allocation = AttackAllocation.from_context(
        allocation_context,
        allocated_model_id=legal_model_ids[0],
        forced=True,
    )
    return _continue_after_allocation(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        allocation=allocation,
        allocated_model_ids=allocated_model_ids,
        hooks=hooks,
    )


def _alive_allocated_model_ids(
    *,
    state: GameState,
    allocated_model_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        model_id
        for model_id in allocated_model_ids
        if _model_is_alive(state=state, model_instance_id=model_id)
    )


def _continue_after_allocation(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    allocation: AttackAllocation,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.ALLOCATE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_sequence.attack_context_id(),
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=validate_json_value(allocation.to_payload()),
        ),
    )
    updated_allocated_ids = tuple(sorted({*allocated_model_ids, allocation.allocated_model_id}))
    allocated_model = model_by_id(state=state, model_instance_id=allocation.allocated_model_id)
    pool = attack_sequence.current_pool()
    cover_result = _cover_for_allocated_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pool=pool,
        allocated_model_id=allocation.allocated_model_id,
    )
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.IGNORES_COVER):
        cover_result = None
    elif _target_has_effect_cover(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        cover_result = _cover_result_with_effect_source(
            ruleset_descriptor=ruleset_descriptor,
            current_cover_result=cover_result,
            source_rule_id=GO_TO_GROUND_EFFECT_KIND,
            los_cache_key=f"{attack_context['attack_context_id']}:effect-cover",
        )
    elif INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids:
        cover_result = _cover_result_with_effect_source(
            ruleset_descriptor=ruleset_descriptor,
            current_cover_result=cover_result,
            source_rule_id=INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
            los_cache_key=f"{attack_context['attack_context_id']}:indirect-cover",
        )
    no_saves_allowed = (
        _devastating_wounds_resolution_for_attack(
            pool=pool,
            attack_context=attack_context,
        )
        is DevastatingWoundsResolution.NO_SAVES
    )
    save_options = save_options_for_model(
        model=allocated_model,
        armor_penetration=pool.weapon_profile.armor_penetration.final,
        cover_result=cover_result,
        no_saves_allowed=no_saves_allowed,
    )
    save_options = _save_options_with_effect_invulnerable(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        armor_penetration=pool.weapon_profile.armor_penetration.final,
        save_options=save_options,
    )
    updated_attack_context: AttackResolutionContextPayload = {
        **attack_context,
        "allocation": allocation.to_payload(),
        "save_options": [option.to_payload() for option in save_options],
    }
    if len(save_options) > 1:
        defender_player_id = updated_attack_context["defender_player_id"]
        request = build_saving_throw_kind_request(
            request_id=state.next_decision_request_id(),
            defender_player_id=defender_player_id,
            attack_context=validate_json_value(updated_attack_context),
            options=save_options,
        )
        decisions.request_decision(request)
        return (
            attack_sequence,
            updated_allocated_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": BattlePhase.SHOOTING.value,
                    "decision_type": SELECT_SAVING_THROW_KIND_DECISION_TYPE,
                    "attack_context_id": attack_sequence.attack_context_id(),
                },
            ),
        )
    if len(save_options) == 1:
        return _resolve_save_and_damage(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=updated_attack_context,
            save_option=save_options[0],
            allocated_model_ids=updated_allocated_ids,
            hooks=hooks,
        )
    damage_amount = _damage_value(
        manager=manager,
        profile=pool.weapon_profile.damage_profile,
        attack_context_id=attack_context["attack_context_id"],
        attacker_player_id=attack_sequence.attacker_player_id,
    ) + _melta_damage_modifier(pool)
    return _resolve_lost_wound_stage(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        target_unit_instance_id=pool.target_unit_instance_id,
        model_instance_id=allocation.allocated_model_id,
        requested_wounds=damage_amount,
        damage_kind=DamageKind.NORMAL,
        saving_throw=None,
        attack_context=updated_attack_context,
        allocated_model_ids=updated_allocated_ids,
        hooks=hooks,
        manager=manager,
    )


def _resolve_save_and_damage(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    save_option: SaveOption,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    allocation = AttackAllocation.from_payload(
        cast(AttackAllocationPayload, attack_context["allocation"])
    )
    roll_state = manager.roll(
        saving_throw_roll_spec(
            save_kind=save_option.save_kind,
            player_id=attack_context["defender_player_id"],
            allocated_model_id=allocation.allocated_model_id,
            attack_context_id=attack_context["attack_context_id"],
        )
    )
    saving_throw = resolve_saving_throw(option=save_option, roll_state=roll_state)
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.SAVE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context["attack_context_id"],
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=validate_json_value(saving_throw.to_payload()),
        ),
    )
    damage: DamageApplication | None = None
    if not saving_throw.successful:
        pool = attack_sequence.current_pool()
        damage_amount = _damage_value(
            manager=manager,
            profile=pool.weapon_profile.damage_profile,
            attack_context_id=attack_context["attack_context_id"],
            attacker_player_id=attack_sequence.attacker_player_id,
        ) + _melta_damage_modifier(pool)
        return _resolve_lost_wound_stage(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            model_instance_id=allocation.allocated_model_id,
            requested_wounds=damage_amount,
            damage_kind=DamageKind.NORMAL,
            saving_throw=saving_throw,
            attack_context=attack_context,
            allocated_model_ids=allocated_model_ids,
            hooks=hooks,
            manager=manager,
        )
    _emit_damage_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=saving_throw,
    )
    return (
        _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        ),
        allocated_model_ids,
        None,
    )


def _resolve_lost_wound_stage(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    model_instance_id: str,
    requested_wounds: int,
    damage_kind: DamageKind,
    saving_throw: SavingThrow | None,
    attack_context: AttackResolutionContextPayload,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    manager: DiceRollManager,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    wounds = _validate_positive_int("requested_wounds", requested_wounds)
    sources = _state_feel_no_pain_sources(state=state, model_instance_id=model_instance_id)
    decline_allowed = _state_feel_no_pain_decline_allowed(
        state=state,
        model_instance_id=model_instance_id,
    )
    lost_wound_context = _lost_wound_context_payload(
        attack_context=attack_context,
        allocated_model_id=model_instance_id,
        damage_kind=damage_kind,
        requested_wounds=wounds,
        saving_throw=saving_throw,
    )
    if not sources:
        return _apply_damage_after_feel_no_pain(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage_kind=damage_kind,
            resolution=FeelNoPainResolution.declined(requested_wounds=wounds),
            allocated_model_ids=allocated_model_ids,
            hooks=hooks,
            saving_throw_payload=lost_wound_context["saving_throw"],
        )
    if len(sources) == 1 and not decline_allowed:
        resolution = resolve_feel_no_pain_rolls(
            manager=manager,
            source=sources[0],
            player_id=attack_context["defender_player_id"],
            model_instance_id=model_instance_id,
            requested_wounds=wounds,
        )
        return _apply_damage_after_feel_no_pain(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage_kind=damage_kind,
            resolution=resolution,
            allocated_model_ids=allocated_model_ids,
            hooks=hooks,
            saving_throw_payload=lost_wound_context["saving_throw"],
        )

    request = build_feel_no_pain_request(
        request_id=state.next_decision_request_id(),
        defender_player_id=attack_context["defender_player_id"],
        lost_wound_context=validate_json_value(lost_wound_context),
        sources=sources,
        decline_allowed=decline_allowed,
    )
    decisions.request_decision(request)
    return (
        attack_sequence,
        allocated_model_ids,
        LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "attack_context_id": attack_sequence.attack_context_id(),
            },
        ),
    )


def _apply_damage_after_feel_no_pain(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    target_unit_instance_id: str,
    model_instance_id: str,
    damage_kind: DamageKind,
    resolution: FeelNoPainResolution,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    saving_throw_payload: JsonValue,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    damage: DamageApplication | None = None
    if resolution.remaining_wounds > 0:
        damage = apply_damage_to_model(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage=resolution.remaining_wounds,
            damage_kind=damage_kind,
        )
    _emit_damage_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
    )
    return (
        _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        ),
        allocated_model_ids,
        None,
    )


def _advance_after_resolved_hit(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> AttackSequence:
    hit_roll = HitRoll.from_payload(attack_context["hit_roll"])
    if hit_roll.generated_hits <= attack_sequence.generated_hit_index:
        raise GameLifecycleError("Resolved hit context has invalid generated hits.")
    return attack_sequence.advanced_after_generated_hit(hit_roll)


def _roll_hit_and_wound(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
) -> AttackResolutionContextPayload | None:
    pool = attack_sequence.current_pool()
    attack_context_id = attack_sequence.attack_context_id()
    if attack_sequence.generated_hit_index == 0:
        hit_roll = _roll_hit(
            state=state,
            manager=manager,
            pool=pool,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
        )
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.HIT,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=attack_context_id,
                pool_index=attack_sequence.pool_index,
                attack_index=attack_sequence.attack_index,
                payload=validate_json_value(hit_roll.to_payload()),
            ),
        )
        if hit_roll.critical:
            _emit_event(
                decisions=decisions,
                hooks=hooks,
                event=AttackSequenceEvent(
                    step=AttackSequenceStep.CRITICAL_HIT,
                    sequence_id=attack_sequence.sequence_id,
                    attack_context_id=attack_context_id,
                    pool_index=attack_sequence.pool_index,
                    attack_index=attack_sequence.attack_index,
                    payload=validate_json_value(hit_roll.to_payload()),
                ),
            )
    else:
        if attack_sequence.current_hit_roll is None:
            raise GameLifecycleError("Generated hit resolution requires a hit roll.")
        hit_roll = attack_sequence.current_hit_roll
    if not hit_roll.successful:
        return None

    target_unit = unit_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    toughness = _target_unit_toughness(target_unit)
    if (
        attack_sequence.generated_hit_index == 0
        and hit_roll.critical
        and has_weapon_keyword(pool.weapon_profile, WeaponKeyword.LETHAL_HITS)
    ):
        wound_roll = WoundRoll.auto_wound(
            strength=pool.weapon_profile.strength.final,
            toughness=toughness,
            target_number=wound_roll_target_number(
                strength=pool.weapon_profile.strength.final,
                toughness=toughness,
            ),
        )
    else:
        wound_roll = _roll_wound(
            manager=manager,
            pool=pool,
            toughness=toughness,
            target_keywords=target_unit.keywords,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
        )
        wound_roll = _reroll_wound_for_twin_linked_if_needed(
            manager=manager,
            decisions=decisions,
            pool=pool,
            initial_wound_roll=wound_roll,
            toughness=toughness,
            target_keywords=target_unit.keywords,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
        )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.WOUND,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context_id,
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=validate_json_value(wound_roll.to_payload()),
        ),
    )
    if wound_roll.critical:
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.CRITICAL_WOUND,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=attack_context_id,
                pool_index=attack_sequence.pool_index,
                attack_index=attack_sequence.attack_index,
                payload=validate_json_value(wound_roll.to_payload()),
            ),
        )
    return {
        "sequence_id": attack_sequence.sequence_id,
        "attack_context_id": attack_context_id,
        "pool_index": attack_sequence.pool_index,
        "attack_index": attack_sequence.attack_index,
        "generated_hit_index": attack_sequence.generated_hit_index,
        "attacker_player_id": attack_sequence.attacker_player_id,
        "defender_player_id": unit_owner_player_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ),
        "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
        "attacker_model_instance_id": pool.attacker_model_instance_id,
        "target_unit_instance_id": pool.target_unit_instance_id,
        "weapon_profile_id": pool.weapon_profile_id,
        "damage_profile": pool.weapon_profile.damage_profile.to_payload(),
        "hit_roll": hit_roll.to_payload(),
        "wound_roll": wound_roll.to_payload(),
        "allocation": None,
        "save_options": [],
    }


def _roll_hit(
    *,
    state: GameState,
    manager: DiceRollManager,
    pool: RangedAttackPool,
    attacker_player_id: str,
    attack_context_id: str,
) -> HitRoll:
    skill = _hit_skill(pool.weapon_profile)
    is_fire_overwatch = FIRE_OVERWATCH_RULE_ID in pool.targeting_rule_ids
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TORRENT):
        return HitRoll.auto_hit(target_number=skill)
    modifier = pool.hit_roll_modifier + _persisting_hit_roll_modifier(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    )
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Hit roll for {pool.weapon_profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.hit",
            actor_id=attacker_player_id,
        )
    )
    unmodified = roll_state.current_total
    capped_modifier = _cap_roll_modifier(modifier)
    final_roll = unmodified + capped_modifier
    if is_fire_overwatch:
        minimum_success = 6
    elif INDIRECT_FIRE_NO_VISIBLE_RULE_ID in pool.targeting_rule_ids:
        minimum_success = 4
    else:
        minimum_success = 2
    generated_hits = sustained_hits_generated_hits(
        pool.weapon_profile,
        critical_hit=unmodified == 6,
    )
    return HitRoll(
        target_number=skill,
        roll_state=roll_state,
        unmodified_roll=unmodified,
        modifier=modifier,
        capped_modifier=capped_modifier,
        final_roll=final_roll,
        successful=unmodified == 6 or (unmodified >= minimum_success and final_roll >= skill),
        critical=unmodified == 6,
        minimum_unmodified_success=minimum_success,
        generated_hits=generated_hits,
    )


def _roll_wound(
    *,
    manager: DiceRollManager,
    pool: RangedAttackPool,
    toughness: int,
    target_keywords: tuple[str, ...],
    attacker_player_id: str,
    attack_context_id: str,
    wound_modifier: int = 0,
) -> WoundRoll:
    strength = pool.weapon_profile.strength.final
    target_number = wound_roll_target_number(strength=strength, toughness=toughness)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Wound roll for {pool.weapon_profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.wound",
            actor_id=attacker_player_id,
        )
    )
    unmodified = roll_state.current_total
    capped_modifier = _cap_roll_modifier(wound_modifier)
    final_roll = unmodified + capped_modifier
    critical_threshold = anti_keyword_critical_threshold(
        profile=pool.weapon_profile,
        target_keywords=target_keywords,
    )
    if critical_threshold is None:
        critical_threshold = 6
    critical = unmodified >= critical_threshold
    return WoundRoll(
        strength=strength,
        toughness=toughness,
        target_number=target_number,
        roll_state=roll_state,
        unmodified_roll=unmodified,
        modifier=wound_modifier,
        capped_modifier=capped_modifier,
        final_roll=final_roll,
        successful=critical or (unmodified != 1 and final_roll >= target_number),
        critical=critical,
        critical_threshold=critical_threshold,
    )


def _reroll_wound_for_twin_linked_if_needed(
    *,
    manager: DiceRollManager,
    decisions: DecisionController,
    pool: RangedAttackPool,
    initial_wound_roll: WoundRoll,
    toughness: int,
    target_keywords: tuple[str, ...],
    attacker_player_id: str,
    attack_context_id: str,
) -> WoundRoll:
    if initial_wound_roll.successful:
        return initial_wound_roll
    if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TWIN_LINKED):
        return initial_wound_roll
    if initial_wound_roll.roll_state is None:
        raise GameLifecycleError("Twin-linked reroll requires a wound roll state.")
    permission = RerollPermission(
        source_id=TWIN_LINKED_RULE_ID,
        timing_window="attack_sequence.wound",
        owning_player_id=attacker_player_id,
        eligible_roll_type=initial_wound_roll.roll_state.original_result.spec.roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    request = manager.build_reroll_request(
        initial_wound_roll.roll_state,
        request_id=f"{attack_context_id}:twin-linked-reroll-request",
        actor_id=attacker_player_id,
        permission=permission,
        extra_payload={
            "source_rule_id": TWIN_LINKED_RULE_ID,
            "attack_context_id": attack_context_id,
            "weapon_profile_id": pool.weapon_profile_id,
        },
    )
    reroll_option_ids = tuple(
        option.option_id for option in request.options if option.option_id != "decline"
    )
    if len(reroll_option_ids) != 1:
        raise GameLifecycleError("Twin-linked reroll must resolve exactly one option.")
    result = DecisionResult.for_request(
        result_id=f"{attack_context_id}:twin-linked-reroll-result",
        request=request,
        selected_option_id=reroll_option_ids[0],
    )
    updated_state = manager.resolve_reroll(
        initial_wound_roll.roll_state,
        request=request,
        result=result,
        record_decision=False,
    )
    unmodified = updated_state.current_total
    capped_modifier = _cap_roll_modifier(initial_wound_roll.modifier)
    final_roll = unmodified + capped_modifier
    critical_threshold = anti_keyword_critical_threshold(
        profile=pool.weapon_profile,
        target_keywords=target_keywords,
    )
    if critical_threshold is None:
        critical_threshold = 6
    critical = unmodified >= critical_threshold
    wound_roll = WoundRoll(
        strength=pool.weapon_profile.strength.final,
        toughness=toughness,
        target_number=initial_wound_roll.target_number,
        roll_state=updated_state,
        unmodified_roll=unmodified,
        modifier=initial_wound_roll.modifier,
        capped_modifier=capped_modifier,
        final_roll=final_roll,
        successful=critical or (unmodified != 1 and final_roll >= initial_wound_roll.target_number),
        critical=critical,
        critical_threshold=critical_threshold,
    )
    decisions.event_log.append(
        "weapon_ability_reroll_resolved",
        {
            "source_rule_id": TWIN_LINKED_RULE_ID,
            "attack_context_id": attack_context_id,
            "weapon_profile_id": pool.weapon_profile_id,
            "reroll_request": request.to_payload(),
            "reroll_result": result.to_payload(),
            "wound_roll": wound_roll.to_payload(),
        },
    )
    return wound_roll


def _emit_damage_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    damage: DamageApplication | None,
    saving_throw: SavingThrow | None,
    saving_throw_payload: JsonValue | None = None,
    feel_no_pain: FeelNoPainResolution | None = None,
) -> None:
    if saving_throw is not None and saving_throw_payload is not None:
        raise GameLifecycleError("Damage event saving throw payload is ambiguous.")
    resolved_saving_throw: JsonValue
    if saving_throw_payload is not None:
        resolved_saving_throw = saving_throw_payload
    elif saving_throw is not None:
        resolved_saving_throw = validate_json_value(saving_throw.to_payload())
    else:
        resolved_saving_throw = None
    payload = validate_json_value(
        {
            "saving_throw": resolved_saving_throw,
            "damage_application": None if damage is None else damage.to_payload(),
            "feel_no_pain": None if feel_no_pain is None else feel_no_pain.to_payload(),
        }
    )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.DAMAGE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_sequence.attack_context_id(),
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=payload,
        ),
    )
    if damage is not None and damage.destroyed:
        decisions.event_log.append(
            "model_destroyed",
            {
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "target_unit_instance_id": damage.target_unit_instance_id,
                "model_instance_id": damage.model_instance_id,
                "damage_kind": damage.damage_kind.value,
            },
        )


def _emit_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    event: AttackSequenceEvent,
) -> None:
    emitted = hooks.emit(event)
    decisions.event_log.append("attack_sequence_step", emitted.to_payload())


def _target_has_effect_cover(*, state: GameState, target_unit_instance_id: str) -> bool:
    return unit_effects_grant_benefit_of_cover(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )


def _persisting_hit_roll_modifier(*, state: GameState, target_unit_instance_id: str) -> int:
    return unit_effect_hit_roll_modifier(state.persisting_effects_for_unit(target_unit_instance_id))


def _save_options_with_effect_invulnerable(
    *,
    state: GameState,
    target_unit_instance_id: str,
    armor_penetration: int,
    save_options: tuple[SaveOption, ...],
) -> tuple[SaveOption, ...]:
    effect_save = unit_effect_invulnerable_save(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )
    if effect_save is None:
        return save_options
    if any(
        option.save_kind is SaveKind.INVULNERABLE and option.target_number <= effect_save
        for option in save_options
    ):
        return save_options
    return tuple(
        sorted(
            (
                *(
                    option
                    for option in save_options
                    if option.save_kind is not SaveKind.INVULNERABLE
                ),
                SaveOption(
                    save_kind=SaveKind.INVULNERABLE,
                    target_number=effect_save,
                    characteristic_target_number=effect_save,
                    armor_penetration=armor_penetration,
                    source_rule_ids=(GO_TO_GROUND_EFFECT_KIND,),
                ),
            ),
            key=lambda option: option.save_kind.value,
        )
    )


def _cover_result_with_effect_source(
    *,
    ruleset_descriptor: RulesetDescriptor,
    current_cover_result: BenefitOfCoverResult | None,
    source_rule_id: str,
    los_cache_key: str,
) -> BenefitOfCoverResult:
    if current_cover_result is not None and current_cover_result.has_benefit:
        return current_cover_result
    cover_policy = ruleset_descriptor.terrain_visibility_policy.cover_policy
    source = CoverSourceRecord(
        feature_id=source_rule_id,
        feature_kind=TerrainFeatureKind.RUINS,
        policy_kind=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
        reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
    )
    return BenefitOfCoverResult(
        has_benefit=True,
        cover_effect=cover_policy.cover_effect,
        source_feature_ids=(source_rule_id,),
        source_policy_kinds=(LineOfSightPolicy.TRUE_LINE_OF_SIGHT,),
        source_records=(source,),
        los_cache_key=los_cache_key,
        target_unit_visible=False,
        target_unit_fully_visible=False,
        non_stacking=cover_policy.non_stacking,
        ap_zero_save_bonus_excluded_for_save_3_plus_or_better=(
            cover_policy.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
        ),
    )


def _melta_damage_modifier(pool: RangedAttackPool) -> int:
    if not any(rule_id.startswith(MELTA_RULE_ID) for rule_id in pool.targeting_rule_ids):
        return 0
    return melta_damage_bonus(pool.weapon_profile, target_within_half_range=True)


def _devastating_wounds_resolution_for_attack(
    *,
    pool: RangedAttackPool,
    attack_context: AttackResolutionContextPayload,
) -> DevastatingWoundsResolution | None:
    if not bool(attack_context["wound_roll"]["critical"]):
        return None
    return devastating_wounds_resolution(pool.weapon_profile)


def _resolve_hazardous_tests(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> None:
    hazardous_pools = tuple(
        pool
        for pool in attack_sequence.attack_pools
        if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.HAZARDOUS)
    )
    seen: set[tuple[str, str, str]] = set()
    for pool in hazardous_pools:
        key = (pool.attacker_model_instance_id, pool.wargear_id, pool.weapon_profile_id)
        if key in seen:
            continue
        seen.add(key)
        roll_state = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"Hazardous test for {pool.weapon_profile_id} after shooting",
                roll_type="hazardous_test",
                actor_id=attack_sequence.attacker_player_id,
            )
        )
        damage_application = None
        if roll_state.current_total == 1:
            model = model_by_id(state=state, model_instance_id=pool.attacker_model_instance_id)
            if model.is_alive:
                damage_application = apply_damage_to_model(
                    state=state,
                    target_unit_instance_id=attack_sequence.attacking_unit_instance_id,
                    model_instance_id=pool.attacker_model_instance_id,
                    damage=_hazardous_damage_for_attacker(
                        state=state,
                        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
                        model_wounds_remaining=model.wounds_remaining,
                    ),
                    damage_kind=DamageKind.MORTAL,
                )
        decisions.event_log.append(
            "hazardous_test_resolved",
            {
                "source_rule_id": HAZARDOUS_RULE_ID,
                "sequence_id": attack_sequence.sequence_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "attacker_model_instance_id": pool.attacker_model_instance_id,
                "wargear_id": pool.wargear_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "roll_state": roll_state.to_payload(),
                "successful": roll_state.current_total != 1,
                "damage_application": (
                    None if damage_application is None else damage_application.to_payload()
                ),
            },
        )


def _hazardous_damage_for_attacker(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
    model_wounds_remaining: int,
) -> int:
    unit = unit_by_id(state=state, unit_instance_id=attacking_unit_instance_id)
    if (
        _unit_has_keyword(unit, "CHARACTER")
        or _unit_has_keyword(unit, "MONSTER")
        or _unit_has_keyword(unit, "VEHICLE")
    ):
        return 3
    return model_wounds_remaining


def _cover_for_allocated_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pool: RangedAttackPool,
    allocated_model_id: str,
) -> BenefitOfCoverResult | None:
    mission_setup = state.mission_setup
    if mission_setup is None or not mission_setup.terrain_features:
        return None
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Allocated-model cover requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield,
        )
        attacker_model = model_by_id(
            state=state,
            model_instance_id=pool.attacker_model_instance_id,
        )
        allocated_model = model_by_id(state=state, model_instance_id=allocated_model_id)
        observer_placement = battlefield.model_placement_by_id(pool.attacker_model_instance_id)
        target_placement = battlefield.model_placement_by_id(allocated_model_id)
        observer_geometry = geometry_model_for_placement(
            model=attacker_model,
            placement=observer_placement,
        )
        target_geometry = geometry_model_for_placement(
            model=allocated_model,
            placement=target_placement,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Allocated-model cover context is invalid.") from exc
    terrain_features = mission_setup.terrain_features
    terrain_volumes = tuple(
        volume for feature in terrain_features for volume in feature.terrain_volumes()
    )
    attacking_unit_id = attack_pool_attacker_unit_id(state=state, pool=pool)
    dynamic_blockers = shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacking_unit_id,
        target_unit_id=pool.target_unit_instance_id,
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=terrain_features,
        ),
        observer_model=observer_geometry,
        target_models=(target_geometry,),
        terrain_features=terrain_features,
        terrain_volumes=terrain_volumes,
        dynamic_model_blockers=dynamic_blockers,
        observer_keywords=unit_by_id(
            state=state,
            unit_instance_id=attacking_unit_id,
        ).keywords,
        target_keywords=unit_by_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ).keywords,
    )
    return context.benefit_of_cover(context.resolve_line_of_sight())


def cover_for_allocated_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pool: RangedAttackPool,
    allocated_model_id: str,
) -> BenefitOfCoverResult | None:
    return _cover_for_allocated_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pool=pool,
        allocated_model_id=allocated_model_id,
    )


def attack_pool_attacker_unit_id(*, state: GameState, pool: RangedAttackPool) -> str:
    for army in state.army_definitions:
        for unit in army.units:
            if any(
                model.model_instance_id == pool.attacker_model_instance_id
                for model in unit.own_models
            ):
                return unit.unit_instance_id
    raise GameLifecycleError("Attack pool attacker model is unknown.")


def _hit_skill(profile: WeaponProfile) -> int:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Hit roll requires a WeaponProfile.")
    expected = (
        Characteristic.WEAPON_SKILL
        if profile.range_profile.kind is RangeProfileKind.MELEE
        else Characteristic.BALLISTIC_SKILL
    )
    if profile.skill.characteristic is not expected:
        raise GameLifecycleError("Weapon skill characteristic does not match attack kind.")
    return _validate_d6_target("Weapon skill target", profile.skill.final)


def _target_unit_toughness(unit: UnitInstance) -> int:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Target unit must be a UnitInstance.")
    alive_models = unit.alive_own_models()
    if not alive_models:
        raise GameLifecycleError("Target unit has no alive models.")
    toughness_values: set[int] = set()
    for model in alive_models:
        for value in model.characteristics:
            if value.characteristic is Characteristic.TOUGHNESS:
                toughness_values.add(value.final)
    if not toughness_values:
        raise GameLifecycleError("Target unit models require Toughness.")
    if len(toughness_values) != 1:
        raise GameLifecycleError("Mixed Toughness target units are deferred to Phase 13E.")
    return next(iter(toughness_values))


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str:
        raise GameLifecycleError("Unit keyword must be a string.")
    stripped = keyword.strip()
    if not stripped:
        raise GameLifecycleError("Unit keyword must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _damage_value(
    *,
    manager: DiceRollManager,
    profile: DamageProfile,
    attack_context_id: str,
    attacker_player_id: str,
) -> int:
    if type(profile) is not DamageProfile:
        raise GameLifecycleError("Damage resolution requires a DamageProfile.")
    if profile.fixed_damage is not None:
        return profile.fixed_damage
    if profile.dice_expression is None:
        raise GameLifecycleError("DamageProfile requires fixed damage or a dice expression.")
    roll = manager.roll_random_characteristic(
        characteristic=Characteristic.DAMAGE,
        timing=RandomCharacteristicTiming.PER_ATTACK,
        scope_id=f"{attack_context_id}:damage",
        expression=profile.dice_expression,
        reason="Phase 13C random Damage roll",
        actor_id=attacker_player_id,
    )
    return roll.value


def _model_is_alive(*, state: GameState, model_instance_id: str) -> bool:
    return model_by_id(state=state, model_instance_id=model_instance_id).is_alive


def _fast_dice_pool_key(pool: RangedAttackPool) -> tuple[object, ...]:
    profile = pool.weapon_profile
    return (
        pool.target_unit_instance_id,
        profile.skill.final,
        profile.strength.final,
        profile.armor_penetration.final,
        profile.damage_profile.to_payload(),
        tuple(keyword.value for keyword in profile.keywords),
        tuple(ability.to_payload() for ability in profile.abilities),
        pool.hit_roll_modifier,
        pool.targeting_rule_ids,
    )


def _pool_id(pool: RangedAttackPool) -> str:
    return (
        f"{pool.attacker_model_instance_id}:{pool.wargear_id}:"
        f"{pool.weapon_profile_id}:{pool.target_unit_instance_id}"
    )


def _validate_attack_pools(values: object) -> tuple[RangedAttackPool, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("AttackSequence attack_pools must be a tuple.")
    pools: list[RangedAttackPool] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not RangedAttackPool:
            raise GameLifecycleError("AttackSequence attack_pools must contain attack pools.")
        pools.append(value)
    if not pools:
        raise GameLifecycleError("AttackSequence requires at least one attack pool.")
    return tuple(pools)


def _validate_deferred_mortal_wounds(values: object) -> tuple[DeferredMortalWounds, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("AttackSequence deferred_mortal_wounds must be a tuple.")
    deferred: list[DeferredMortalWounds] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeferredMortalWounds:
            raise GameLifecycleError(
                "AttackSequence deferred_mortal_wounds must contain deferred mortal wounds."
            )
        deferred.append(value)
    return tuple(deferred)


def _validate_fast_dice_pools(values: object) -> tuple[RangedAttackPool, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FastDiceGroup pools must be a tuple.")
    pools: list[RangedAttackPool] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not RangedAttackPool:
            raise GameLifecycleError("FastDiceGroup pools must contain attack pools.")
        pools.append(value)
    return tuple(pools)


def _validate_roll_modifier_tuple(field_name: str, values: object) -> tuple[RollModifier, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    modifiers: list[RollModifier] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not RollModifier:
            raise GameLifecycleError(f"{field_name} must contain RollModifier values.")
        if value.modifier_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate modifier IDs.")
        seen.add(value.modifier_id)
        modifiers.append(value)
    return tuple(sorted(modifiers, key=lambda modifier: (modifier.priority, modifier.modifier_id)))


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Attack sequence payload must be an object.")
    return payload


def _precision_selected_model_id(payload: JsonValue) -> str | None:
    value = _payload_object(payload).get("selected_model_id")
    if value is None:
        return None
    return _validate_identifier("Precision selected_model_id", value)


def _precision_eligible_character_ids(payload: dict[str, JsonValue]) -> tuple[str, ...]:
    raw_ids = payload.get("eligible_character_model_ids")
    if not isinstance(raw_ids, list):
        raise GameLifecycleError("Precision request eligible characters must be a list.")
    return _validate_identifier_tuple(
        "Precision eligible_character_model_ids",
        tuple(raw_ids),
    )


def _lost_wound_context_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    allocated_model_id: str,
    damage_kind: DamageKind,
    requested_wounds: int,
    saving_throw: SavingThrow | None,
) -> LostWoundContextPayload:
    return {
        "attack_context": attack_context,
        "allocated_model_id": _validate_identifier("allocated_model_id", allocated_model_id),
        "damage_kind": damage_kind_from_token(damage_kind).value,
        "requested_wounds": _validate_positive_int("requested_wounds", requested_wounds),
        "saving_throw": (
            None if saving_throw is None else validate_json_value(saving_throw.to_payload())
        ),
    }


def _lost_wound_context_from_payload(payload: JsonValue) -> LostWoundContextPayload:
    raw = _payload_object(payload)
    attack_context = raw["attack_context"]
    if not isinstance(attack_context, dict):
        raise GameLifecycleError("Feel No Pain context attack_context must be an object.")
    return {
        "attack_context": cast(AttackResolutionContextPayload, attack_context),
        "allocated_model_id": _payload_string(raw, key="allocated_model_id"),
        "damage_kind": damage_kind_from_token(raw["damage_kind"]).value,
        "requested_wounds": _payload_positive_int(raw, key="requested_wounds"),
        "saving_throw": validate_json_value(raw["saving_throw"]),
    }


def _validate_lost_wound_context_matches_sequence(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> None:
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError("Feel No Pain attack context sequence drift.")
    if attack_context["attack_context_id"] != attack_sequence.attack_context_id():
        raise GameLifecycleError("Feel No Pain attack context ID drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError("Feel No Pain pool index drift.")
    if attack_context["attack_index"] != attack_sequence.attack_index:
        raise GameLifecycleError("Feel No Pain attack index drift.")
    if attack_context["generated_hit_index"] != attack_sequence.generated_hit_index:
        raise GameLifecycleError("Feel No Pain generated hit index drift.")


def _state_feel_no_pain_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[FeelNoPainSource, ...]:
    lookup = state.feel_no_pain_sources_for_model
    sources = lookup(model_instance_id=model_instance_id)
    if type(sources) is not tuple:
        raise GameLifecycleError("Feel No Pain source lookup must return a tuple.")
    for source in sources:
        if type(source) is not FeelNoPainSource:
            raise GameLifecycleError("Feel No Pain source lookup returned an invalid source.")
    return sources


def _state_feel_no_pain_decline_allowed(
    *,
    state: GameState,
    model_instance_id: str,
) -> bool:
    lookup = state.feel_no_pain_decline_allowed_for_model
    value = lookup(model_instance_id=model_instance_id)
    if type(value) is not bool:
        raise GameLifecycleError("Feel No Pain decline lookup must return a bool.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Attack sequence payload {key} must be a string.")
    return value


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    return _validate_positive_int(key, payload[key])


def _cap_roll_modifier(modifier: int) -> int:
    if type(modifier) is not int:
        raise GameLifecycleError("Roll modifier must be an integer.")
    return max(-1, min(1, modifier))


def _validate_d6_target(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value


def _validate_d6_minimum_success(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


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
