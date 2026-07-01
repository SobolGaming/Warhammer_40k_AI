from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
    RandomCharacteristicRoll,
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
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    DamageProfile,
    DamageProfilePayload,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.core_stratagem_effects import (
    GO_TO_GROUND_EFFECT_KIND,
    unit_effect_hit_roll_modifier,
    unit_effect_invulnerable_save,
    unit_effects_deny_benefit_of_cover,
    unit_effects_grant_benefit_of_cover,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    AllocationGroup,
    AllocationGroupPayload,
    AllocationGroupRole,
    AllocationOrderDecision,
    AttackAllocation,
    AttackAllocationConstraint,
    AttackAllocationPayload,
    AttackAllocationRuleContext,
    AttackAllocationRuleContextPayload,
    DamageAllocationModelDecision,
    DamageApplication,
    DamageApplicationPayload,
    DamageKind,
    DestructionReactionDecision,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionReactionSourcePayload,
    FeelNoPainAttackCondition,
    FeelNoPainDecision,
    FeelNoPainResolution,
    FeelNoPainResolutionPayload,
    FeelNoPainSource,
    FeelNoPainSourcePayload,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
    allocation_context_for_unit,
    allocation_groups_for_context,
    apply_damage_to_model,
    build_allocation_order_request,
    build_damage_allocation_model_request,
    build_destruction_reaction_request,
    build_feel_no_pain_request,
    continue_mortal_wound_application,
    damage_kind_from_token,
    is_mortal_wound_feel_no_pain_request,
    legal_allocation_group_orders,
    model_by_id,
    remove_destroyed_model_from_battlefield,
    resolve_feel_no_pain_rolls,
    resolve_mortal_wound_feel_no_pain_decision,
    unit_by_id,
    unit_owner_player_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.hazard import (
    hazard_mortal_wounds_per_failed_roll,
    hazard_roll_failed,
    hazard_roll_spec,
)
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.opportunity_windows import (
    OPPORTUNITY_REQUEST_FAMILY,
    OPPORTUNITY_SUBMISSION_PAYLOAD_KEY,
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
    TriggerBatchingMode,
    opportunity_boundary_game_state_payload,
    opportunity_boundary_state_hash,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveOption,
    SaveOptionPayload,
    SavingThrow,
    mandatory_save_option,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_targets import (
    BENEFIT_OF_COVER_RULE_ID,
    PLUNGING_FIRE_RULE_ID,
    shooting_dynamic_model_blockers,
    shooting_visibility_cache_key,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DisembarkModeKind,
    DisembarkSelection,
    TransportCargoState,
    TransportMovementStatus,
    apply_destroyed_transport_disembark_to_battlefield,
    apply_transport_hazard_mortal_wounds,
    resolve_destroyed_transport_disembark,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    DEVASTATING_WOUNDS_RULE_ID,
    FIRE_OVERWATCH_RULE_ID,
    HAZARDOUS_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    LANCE_RULE_ID,
    MELTA_RULE_ID,
    PRECISION_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
    SUSTAINED_HITS_D3_VALUE,
    TWIN_LINKED_RULE_ID,
    DevastatingWoundsResolution,
    anti_keyword_critical_threshold,
    devastating_wounds_resolution,
    has_weapon_keyword,
    is_psychic_weapon_profile,
    lethal_hits_applies,
    melta_damage_bonus,
    sustained_hits_generated_hits,
    weapon_ability_value,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload
from warhammer40k_core.geometry.measurement import (
    DistanceMeasurementContext,
    objective_marker_controls_model,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    CoverSourceReason,
    CoverSourceRecord,
    TerrainVisibilityContext,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


ATTACK_ALLOCATION_DECISION_TYPES = frozenset(
    (
        "select_psychic_attack_modifier_ignores",
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    )
)
SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE = "select_resolve_target_unit"
SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE = "select_attack_weapon_group"
SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE = "select_psychic_attack_modifier_ignores"
KEEP_ALL_MODIFIERS_OPTION_ID = "keep-all-modifiers"
IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID = "ignore-detrimental-modifiers"
IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID = "ignore-beneficial-modifiers"
IGNORE_ALL_MODIFIERS_OPTION_ID = "ignore-all-modifiers"
ATTACK_RESOLUTION_SELECTION_DECISION_TYPES = frozenset(
    (
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    )
)
SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS = {
    "attack_sequence.hit": "hit_roll_state",
    "attack_sequence.wound": "wound_roll_state",
}
DAMAGE_ALLOCATION_RULE_ID = "core_rules_damage_allocation"
DEADLY_DEMISE_SOURCE_KIND = "deadly_demise"
HAZARDOUS_SOURCE_KIND = "hazardous"
_PRECISION_CHARACTER_GROUP_ROLES = frozenset(
    (
        AllocationGroupRole.CHARACTER,
        AllocationGroupRole.LEADER,
        AllocationGroupRole.SUPPORT,
    )
)


def attack_sequence_hit_roll_spec(
    *,
    weapon_profile_id: str,
    attack_context_id: str,
    attacker_player_id: str,
    reroll_forbidden_rule_ids: tuple[str, ...] = (),
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id=attacker_player_id,
        reroll_forbidden_rule_ids=reroll_forbidden_rule_ids,
    )


def attack_sequence_wound_roll_spec(
    *,
    weapon_profile_id: str,
    attack_context_id: str,
    attacker_player_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id=attacker_player_id,
    )


def deadly_demise_trigger_roll_spec(
    *,
    source: DestructionReactionSource,
    player_id: str,
    model_instance_id: str,
) -> DiceRollSpec:
    if type(source) is not DestructionReactionSource:
        raise GameLifecycleError("Deadly Demise trigger roll requires a source.")
    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE:
        raise GameLifecycleError("Deadly Demise trigger roll requires a Deadly Demise source.")
    actor_id = _validate_identifier("player_id", player_id)
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Deadly Demise trigger for {source.source_id} on {model_id}",
        roll_type="destruction_reaction.deadly_demise.trigger",
        actor_id=actor_id,
    )


def deadly_demise_mortal_wounds_roll_spec(
    *,
    source: DestructionReactionSource,
    player_id: str,
    target_unit_instance_id: str,
    sides: int,
) -> DiceRollSpec:
    if type(source) is not DestructionReactionSource:
        raise GameLifecycleError("Deadly Demise mortal-wound roll requires a source.")
    actor_id = _validate_identifier("player_id", player_id)
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=sides),
        reason=f"Deadly Demise mortal wounds for {source.source_id} into {target_unit_id}",
        roll_type="destruction_reaction.deadly_demise.mortal_wounds",
        actor_id=actor_id,
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


@dataclass(frozen=True, slots=True)
class PsychicAttackModifierIgnoreSelection:
    option_id: str
    skill_modifier: int
    hit_roll_modifier: int
    effective_skill_modifier: int
    effective_hit_roll_modifier: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_identifier("Psychic modifier option_id", self.option_id),
        )
        object.__setattr__(
            self,
            "skill_modifier",
            _validate_int("Psychic modifier skill_modifier", self.skill_modifier),
        )
        object.__setattr__(
            self,
            "hit_roll_modifier",
            _validate_int("Psychic modifier hit_roll_modifier", self.hit_roll_modifier),
        )
        object.__setattr__(
            self,
            "effective_skill_modifier",
            _validate_int(
                "Psychic modifier effective_skill_modifier",
                self.effective_skill_modifier,
            ),
        )
        object.__setattr__(
            self,
            "effective_hit_roll_modifier",
            _validate_int(
                "Psychic modifier effective_hit_roll_modifier",
                self.effective_hit_roll_modifier,
            ),
        )


class AttackSequencePayload(TypedDict):
    sequence_id: str
    source_phase: NotRequired[str]
    attacker_player_id: str
    attacking_unit_instance_id: str
    attack_pools: list[RangedAttackPoolPayload]
    used_pool_indices: list[int]
    selected_target_unit_instance_id: str | None
    current_gathered_group: GatheredAttackGroupPayload | None
    pool_index: int
    attack_index: int
    generated_hit_index: int
    current_hit_roll: HitRollPayload | None
    deferred_mortal_wounds: list[DeferredMortalWoundsPayload]
    pending_grouped_damage: PendingGroupedDamagePayload | None
    pending_destroyed_transport_disembark: PendingDestroyedTransportDisembarkPayload | None


class AttackResolutionContextPayload(TypedDict):
    sequence_id: str
    source_phase: str
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
    is_psychic_attack: bool
    selected_weapon_ability_ids: list[str]
    damage_profile: DamageProfilePayload
    hit_roll: HitRollPayload
    wound_roll: WoundRollPayload
    allocation: AttackAllocationPayload | None
    save_options: list[SaveOptionPayload]


class SaveDieEntryPayload(TypedDict):
    roll_state: DiceRollStatePayload
    value: int
    attack_context: AttackResolutionContextPayload


class PendingGroupedDamagePayload(TypedDict):
    sorted_save_dice: list[SaveDieEntryPayload]
    ordered_allocation_group_payloads: list[AllocationGroupPayload]
    allocation_context_payload: AttackAllocationRuleContextPayload
    allocated_model_ids: list[str]
    next_index: int


class PendingDestroyedTransportDisembarkPayload(TypedDict):
    attack_context: AttackResolutionContextPayload
    damage_application: DamageApplicationPayload
    saving_throw: JsonValue
    feel_no_pain: FeelNoPainResolutionPayload
    destroyed_model_controller_player_id: str
    transport_unit_instance_id: str
    pending_unit_instance_ids: list[str]
    resolved_disembarks: list[DestroyedTransportDisembarkPayload]
    pending_sources: list[DestructionReactionSourcePayload]


class LostWoundContextPayload(TypedDict):
    attack_context: AttackResolutionContextPayload
    allocated_model_id: str
    damage_kind: str
    requested_wounds: int
    saving_throw: JsonValue


class DestructionReactionContextPayload(TypedDict):
    context_kind: str
    attack_context: AttackResolutionContextPayload
    damage_application: JsonValue
    model_destroyed_event_id: str
    damage_event_id: str
    target_unit_instance_id: str
    model_instance_id: str
    destroyed_model_controller_player_id: str
    source_phase: str
    source_step: str
    removal_record: JsonValue
    transition_batch: JsonValue
    destroyed_model_rules_triggered: bool
    continuation: JsonValue


class DeferredMortalWoundsPayload(TypedDict):
    source_rule_id: str
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int


class HazardousMortalWoundSourceContextPayload(TypedDict):
    source_kind: str
    sequence_id: str
    attacking_unit_instance_id: str
    hazardous_weapon_profile_ids: list[str]
    hazardous_roll_state: DiceRollStatePayload
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


class IdenticalAttackSignaturePayload(TypedDict):
    attacker_model_instance_id: str
    target_visible_model_ids: list[str]
    target_in_range_model_ids: list[str]
    hit_basis: str
    hit_roll_modifier: int
    wound_roll_modifiers: list[str]
    strength: str
    armor_penetration: str
    damage: str
    weapon_rule_tokens: list[str]
    targeting_rule_ids: list[str]
    shooting_type: str
    firing_deck_source_unit_instance_id: str | None
    firing_deck_source_model_instance_id: str | None


class GatheredAttackContributionPayload(TypedDict):
    pool_index: int
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    attacks: int
    firing_deck_source_unit_instance_id: str | None
    firing_deck_source_model_instance_id: str | None


class GatheredAttackGroupPayload(TypedDict):
    group_id: str
    target_unit_instance_id: str
    signature: IdenticalAttackSignaturePayload
    pool_indices: list[int]
    total_attacks: int
    contributions: list[GatheredAttackContributionPayload]


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
class DestroyedModelEmission:
    damage_event_id: str
    model_destroyed_event_id: str
    removal_record: ModelRemovalRecord
    transition_batch: BattlefieldTransitionBatch

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "damage_event_id",
            _validate_identifier("DestroyedModelEmission damage_event_id", self.damage_event_id),
        )
        object.__setattr__(
            self,
            "model_destroyed_event_id",
            _validate_identifier(
                "DestroyedModelEmission model_destroyed_event_id",
                self.model_destroyed_event_id,
            ),
        )
        if type(self.removal_record) is not ModelRemovalRecord:
            raise GameLifecycleError("DestroyedModelEmission requires a removal record.")
        if type(self.transition_batch) is not BattlefieldTransitionBatch:
            raise GameLifecycleError("DestroyedModelEmission requires a transition batch.")


@dataclass(frozen=True, slots=True)
class PrecisionPoolSelection:
    selected_group_id: str | None
    selected_model_ids: tuple[str, ...]
    selection_recorded: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_group_id",
            _validate_optional_identifier(
                "PrecisionPoolSelection selected_group_id",
                self.selected_group_id,
            ),
        )
        object.__setattr__(
            self,
            "selected_model_ids",
            _validate_identifier_tuple(
                "PrecisionPoolSelection selected_model_ids",
                self.selected_model_ids,
            ),
        )
        if type(self.selection_recorded) is not bool:
            raise GameLifecycleError("PrecisionPoolSelection selection_recorded must be a bool.")
        if self.selected_group_id is not None and not self.selection_recorded:
            raise GameLifecycleError("Precision selected group requires a recorded selection.")
        if self.selected_model_ids and self.selected_group_id is None:
            raise GameLifecycleError("Precision selected models require a selected group.")


@dataclass(frozen=True, slots=True)
class PendingGroupedDamage:
    sorted_save_dice: tuple[SaveDieEntryPayload, ...]
    ordered_allocation_group_payloads: tuple[AllocationGroupPayload, ...]
    allocation_context_payload: AttackAllocationRuleContextPayload
    allocated_model_ids: tuple[str, ...]
    next_index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sorted_save_dice",
            _validate_save_die_entry_tuple(self.sorted_save_dice),
        )
        object.__setattr__(
            self,
            "ordered_allocation_group_payloads",
            _validate_allocation_group_payload_tuple(self.ordered_allocation_group_payloads),
        )
        AttackAllocationRuleContext.from_payload(self.allocation_context_payload)
        object.__setattr__(
            self,
            "allocation_context_payload",
            validate_json_value(self.allocation_context_payload),
        )
        object.__setattr__(
            self,
            "allocated_model_ids",
            _validate_identifier_tuple(
                "PendingGroupedDamage allocated_model_ids",
                self.allocated_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "next_index",
            _validate_non_negative_int("PendingGroupedDamage next_index", self.next_index),
        )
        if self.next_index > len(self.sorted_save_dice):
            raise GameLifecycleError("PendingGroupedDamage next_index is outside save dice.")

    def to_payload(self) -> PendingGroupedDamagePayload:
        return {
            "sorted_save_dice": list(self.sorted_save_dice),
            "ordered_allocation_group_payloads": list(self.ordered_allocation_group_payloads),
            "allocation_context_payload": self.allocation_context_payload,
            "allocated_model_ids": list(self.allocated_model_ids),
            "next_index": self.next_index,
        }

    @classmethod
    def from_payload(cls, payload: PendingGroupedDamagePayload) -> Self:
        return cls(
            sorted_save_dice=tuple(payload["sorted_save_dice"]),
            ordered_allocation_group_payloads=tuple(payload["ordered_allocation_group_payloads"]),
            allocation_context_payload=payload["allocation_context_payload"],
            allocated_model_ids=tuple(payload["allocated_model_ids"]),
            next_index=payload["next_index"],
        )

    def allocation_context(self) -> AttackAllocationRuleContext:
        return AttackAllocationRuleContext.from_payload(self.allocation_context_payload)

    def ordered_allocation_groups(self) -> tuple[AllocationGroup, ...]:
        return tuple(
            AllocationGroup.from_payload(group_payload)
            for group_payload in self.ordered_allocation_group_payloads
        )

    def with_next_index(self, next_index: int) -> Self:
        return type(self)(
            sorted_save_dice=self.sorted_save_dice,
            ordered_allocation_group_payloads=self.ordered_allocation_group_payloads,
            allocation_context_payload=self.allocation_context_payload,
            allocated_model_ids=self.allocated_model_ids,
            next_index=next_index,
        )

    def with_allocated_model_ids(self, allocated_model_ids: tuple[str, ...]) -> Self:
        return type(self)(
            sorted_save_dice=self.sorted_save_dice,
            ordered_allocation_group_payloads=self.ordered_allocation_group_payloads,
            allocation_context_payload=self.allocation_context_payload,
            allocated_model_ids=allocated_model_ids,
            next_index=self.next_index,
        )

    def advanced_after_current_die(self) -> Self:
        return self.with_next_index(self.next_index + 1)


@dataclass(frozen=True, slots=True)
class PendingDestroyedTransportDisembark:
    attack_context: AttackResolutionContextPayload
    damage_application: DamageApplication
    saving_throw_payload: JsonValue
    feel_no_pain: FeelNoPainResolution
    destroyed_model_controller_player_id: str
    transport_unit_instance_id: str
    pending_unit_instance_ids: tuple[str, ...]
    resolved_disembarks: tuple[DestroyedTransportDisembark, ...] = ()
    pending_sources: tuple[DestructionReactionSource, ...] = ()

    def __post_init__(self) -> None:
        attack_context = validate_json_value(self.attack_context)
        if not isinstance(attack_context, dict):
            raise GameLifecycleError(
                "Pending destroyed Transport attack_context must be an object."
            )
        object.__setattr__(
            self,
            "attack_context",
            cast(AttackResolutionContextPayload, attack_context),
        )
        if type(self.damage_application) is not DamageApplication:
            raise GameLifecycleError(
                "Pending destroyed Transport damage_application must be DamageApplication."
            )
        if not self.damage_application.destroyed:
            raise GameLifecycleError("Pending destroyed Transport requires destroyed damage.")
        if (
            self.damage_application.target_unit_instance_id
            != self.attack_context["target_unit_instance_id"]
        ):
            raise GameLifecycleError("Pending destroyed Transport damage target drift.")
        object.__setattr__(
            self,
            "saving_throw_payload",
            validate_json_value(self.saving_throw_payload),
        )
        if type(self.feel_no_pain) is not FeelNoPainResolution:
            raise GameLifecycleError(
                "Pending destroyed Transport feel_no_pain must be FeelNoPainResolution."
            )
        object.__setattr__(
            self,
            "destroyed_model_controller_player_id",
            _validate_identifier(
                "Pending destroyed Transport controller",
                self.destroyed_model_controller_player_id,
            ),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "Pending destroyed Transport transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "pending_unit_instance_ids",
            _validate_identifier_tuple(
                "Pending destroyed Transport unit ids",
                self.pending_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "resolved_disembarks",
            _validate_destroyed_transport_disembark_tuple(self.resolved_disembarks),
        )
        object.__setattr__(
            self,
            "pending_sources",
            _validate_destruction_reaction_source_tuple(
                "Pending destroyed Transport pending_sources",
                self.pending_sources,
            ),
        )
        resolved_unit_ids = {disembark.unit_instance_id for disembark in self.resolved_disembarks}
        if resolved_unit_ids & set(self.pending_unit_instance_ids):
            raise GameLifecycleError("Pending destroyed Transport unit appears in both states.")
        for disembark in self.resolved_disembarks:
            if disembark.transport_unit_instance_id != self.transport_unit_instance_id:
                raise GameLifecycleError("Pending destroyed Transport disembark transport drift.")
            if disembark.battle_round < 1:
                raise GameLifecycleError("Pending destroyed Transport disembark round drift.")

    @property
    def next_unit_instance_id(self) -> str | None:
        if not self.pending_unit_instance_ids:
            return None
        return self.pending_unit_instance_ids[0]

    def with_resolved_disembark(self, disembark: DestroyedTransportDisembark) -> Self:
        if type(disembark) is not DestroyedTransportDisembark:
            raise GameLifecycleError("Resolved destroyed Transport disembark is invalid.")
        if self.next_unit_instance_id != disembark.unit_instance_id:
            raise GameLifecycleError("Resolved destroyed Transport disembark unit drift.")
        return type(self)(
            attack_context=self.attack_context,
            damage_application=self.damage_application,
            saving_throw_payload=self.saving_throw_payload,
            feel_no_pain=self.feel_no_pain,
            destroyed_model_controller_player_id=self.destroyed_model_controller_player_id,
            transport_unit_instance_id=self.transport_unit_instance_id,
            pending_unit_instance_ids=self.pending_unit_instance_ids[1:],
            resolved_disembarks=(*self.resolved_disembarks, disembark),
            pending_sources=self.pending_sources,
        )

    def to_payload(self) -> PendingDestroyedTransportDisembarkPayload:
        return {
            "attack_context": self.attack_context,
            "damage_application": self.damage_application.to_payload(),
            "saving_throw": self.saving_throw_payload,
            "feel_no_pain": self.feel_no_pain.to_payload(),
            "destroyed_model_controller_player_id": self.destroyed_model_controller_player_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "pending_unit_instance_ids": list(self.pending_unit_instance_ids),
            "resolved_disembarks": [
                disembark.to_payload() for disembark in self.resolved_disembarks
            ],
            "pending_sources": [source.to_payload() for source in self.pending_sources],
        }

    @classmethod
    def from_payload(cls, payload: PendingDestroyedTransportDisembarkPayload) -> Self:
        return cls(
            attack_context=payload["attack_context"],
            damage_application=DamageApplication.from_payload(payload["damage_application"]),
            saving_throw_payload=payload["saving_throw"],
            feel_no_pain=FeelNoPainResolution.from_payload(payload["feel_no_pain"]),
            destroyed_model_controller_player_id=payload["destroyed_model_controller_player_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            pending_unit_instance_ids=tuple(payload["pending_unit_instance_ids"]),
            resolved_disembarks=tuple(
                DestroyedTransportDisembark.from_payload(disembark)
                for disembark in payload["resolved_disembarks"]
            ),
            pending_sources=tuple(
                DestructionReactionSource.from_payload(source)
                for source in payload["pending_sources"]
            ),
        )


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
class IdenticalAttackSignature:
    attacker_model_instance_id: str
    target_visible_model_ids: tuple[str, ...]
    target_in_range_model_ids: tuple[str, ...]
    hit_basis: str
    hit_roll_modifier: int
    wound_roll_modifiers: tuple[str, ...]
    strength: str
    armor_penetration: str
    damage: str
    weapon_rule_tokens: tuple[str, ...]
    targeting_rule_ids: tuple[str, ...]
    shooting_type: str
    firing_deck_source_unit_instance_id: str | None = None
    firing_deck_source_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "IdenticalAttackSignature attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_visible_model_ids",
            _validate_ordered_identifier_tuple(
                "IdenticalAttackSignature target_visible_model_ids",
                self.target_visible_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "target_in_range_model_ids",
            _validate_ordered_identifier_tuple(
                "IdenticalAttackSignature target_in_range_model_ids",
                self.target_in_range_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "hit_basis",
            _validate_identifier("IdenticalAttackSignature hit_basis", self.hit_basis),
        )
        if type(self.hit_roll_modifier) is not int:
            raise GameLifecycleError("IdenticalAttackSignature hit_roll_modifier must be an int.")
        object.__setattr__(
            self,
            "wound_roll_modifiers",
            _validate_identifier_tuple(
                "IdenticalAttackSignature wound_roll_modifiers",
                self.wound_roll_modifiers,
            ),
        )
        object.__setattr__(
            self,
            "strength",
            _validate_identifier("IdenticalAttackSignature strength", self.strength),
        )
        object.__setattr__(
            self,
            "armor_penetration",
            _validate_identifier(
                "IdenticalAttackSignature armor_penetration",
                self.armor_penetration,
            ),
        )
        object.__setattr__(
            self,
            "damage",
            _validate_identifier("IdenticalAttackSignature damage", self.damage),
        )
        object.__setattr__(
            self,
            "weapon_rule_tokens",
            _validate_identifier_tuple(
                "IdenticalAttackSignature weapon_rule_tokens",
                self.weapon_rule_tokens,
            ),
        )
        object.__setattr__(
            self,
            "targeting_rule_ids",
            _validate_identifier_tuple(
                "IdenticalAttackSignature targeting_rule_ids",
                self.targeting_rule_ids,
            ),
        )
        object.__setattr__(
            self,
            "shooting_type",
            _validate_identifier("IdenticalAttackSignature shooting_type", self.shooting_type),
        )
        object.__setattr__(
            self,
            "firing_deck_source_unit_instance_id",
            _validate_optional_identifier(
                "IdenticalAttackSignature firing_deck_source_unit_instance_id",
                self.firing_deck_source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_model_instance_id",
            _validate_optional_identifier(
                "IdenticalAttackSignature firing_deck_source_model_instance_id",
                self.firing_deck_source_model_instance_id,
            ),
        )
        if (self.firing_deck_source_unit_instance_id is None) != (
            self.firing_deck_source_model_instance_id is None
        ):
            raise GameLifecycleError(
                "IdenticalAttackSignature Firing Deck source unit and model must be supplied "
                "together."
            )

    def stable_hash(self) -> str:
        encoded = canonical_json(self.to_payload()).encode("utf-8")
        return sha256(encoded).hexdigest()[:16]

    def to_payload(self) -> IdenticalAttackSignaturePayload:
        return {
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "target_visible_model_ids": list(self.target_visible_model_ids),
            "target_in_range_model_ids": list(self.target_in_range_model_ids),
            "hit_basis": self.hit_basis,
            "hit_roll_modifier": self.hit_roll_modifier,
            "wound_roll_modifiers": list(self.wound_roll_modifiers),
            "strength": self.strength,
            "armor_penetration": self.armor_penetration,
            "damage": self.damage,
            "weapon_rule_tokens": list(self.weapon_rule_tokens),
            "targeting_rule_ids": list(self.targeting_rule_ids),
            "shooting_type": self.shooting_type,
            "firing_deck_source_unit_instance_id": self.firing_deck_source_unit_instance_id,
            "firing_deck_source_model_instance_id": self.firing_deck_source_model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: IdenticalAttackSignaturePayload) -> Self:
        return cls(
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            target_visible_model_ids=tuple(payload["target_visible_model_ids"]),
            target_in_range_model_ids=tuple(payload["target_in_range_model_ids"]),
            hit_basis=payload["hit_basis"],
            hit_roll_modifier=payload["hit_roll_modifier"],
            wound_roll_modifiers=tuple(payload["wound_roll_modifiers"]),
            strength=payload["strength"],
            armor_penetration=payload["armor_penetration"],
            damage=payload["damage"],
            weapon_rule_tokens=tuple(payload["weapon_rule_tokens"]),
            targeting_rule_ids=tuple(payload["targeting_rule_ids"]),
            shooting_type=payload["shooting_type"],
            firing_deck_source_unit_instance_id=payload["firing_deck_source_unit_instance_id"],
            firing_deck_source_model_instance_id=payload["firing_deck_source_model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class GatheredAttackContribution:
    pool_index: int
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    attacks: int
    firing_deck_source_unit_instance_id: str | None = None
    firing_deck_source_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pool_index",
            _validate_non_negative_int("GatheredAttackContribution pool_index", self.pool_index),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "GatheredAttackContribution attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("GatheredAttackContribution wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "GatheredAttackContribution weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "GatheredAttackContribution target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacks",
            _validate_positive_int("GatheredAttackContribution attacks", self.attacks),
        )
        object.__setattr__(
            self,
            "firing_deck_source_unit_instance_id",
            _validate_optional_identifier(
                "GatheredAttackContribution firing_deck_source_unit_instance_id",
                self.firing_deck_source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_model_instance_id",
            _validate_optional_identifier(
                "GatheredAttackContribution firing_deck_source_model_instance_id",
                self.firing_deck_source_model_instance_id,
            ),
        )
        if (self.firing_deck_source_unit_instance_id is None) != (
            self.firing_deck_source_model_instance_id is None
        ):
            raise GameLifecycleError(
                "GatheredAttackContribution Firing Deck source unit and model must be supplied "
                "together."
            )

    def to_payload(self) -> GatheredAttackContributionPayload:
        return {
            "pool_index": self.pool_index,
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "attacks": self.attacks,
            "firing_deck_source_unit_instance_id": self.firing_deck_source_unit_instance_id,
            "firing_deck_source_model_instance_id": self.firing_deck_source_model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: GatheredAttackContributionPayload) -> Self:
        return cls(
            pool_index=payload["pool_index"],
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            attacks=payload["attacks"],
            firing_deck_source_unit_instance_id=payload["firing_deck_source_unit_instance_id"],
            firing_deck_source_model_instance_id=payload["firing_deck_source_model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class GatheredAttackGroup:
    group_id: str
    target_unit_instance_id: str
    signature: IdenticalAttackSignature
    pool_indices: tuple[int, ...]
    total_attacks: int
    contributions: tuple[GatheredAttackContribution, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "group_id",
            _validate_identifier("GatheredAttackGroup group_id", self.group_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "GatheredAttackGroup target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        if type(self.signature) is not IdenticalAttackSignature:
            raise GameLifecycleError(
                "GatheredAttackGroup signature must be an IdenticalAttackSignature."
            )
        object.__setattr__(
            self,
            "pool_indices",
            _validate_pool_index_tuple("GatheredAttackGroup pool_indices", self.pool_indices),
        )
        object.__setattr__(
            self,
            "total_attacks",
            _validate_positive_int("GatheredAttackGroup total_attacks", self.total_attacks),
        )
        object.__setattr__(
            self,
            "contributions",
            _validate_gathered_attack_contributions(self.contributions),
        )
        if tuple(contribution.pool_index for contribution in self.contributions) != (
            self.pool_indices
        ):
            raise GameLifecycleError("GatheredAttackGroup contribution pool indices drift.")
        if sum(contribution.attacks for contribution in self.contributions) != self.total_attacks:
            raise GameLifecycleError("GatheredAttackGroup total attacks drift.")
        if any(
            contribution.target_unit_instance_id != self.target_unit_instance_id
            for contribution in self.contributions
        ):
            raise GameLifecycleError("GatheredAttackGroup contribution target drift.")

    @property
    def primary_pool_index(self) -> int:
        return self.pool_indices[0]

    def to_payload(self) -> GatheredAttackGroupPayload:
        return {
            "group_id": self.group_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "signature": self.signature.to_payload(),
            "pool_indices": list(self.pool_indices),
            "total_attacks": self.total_attacks,
            "contributions": [contribution.to_payload() for contribution in self.contributions],
        }

    @classmethod
    def from_payload(cls, payload: GatheredAttackGroupPayload) -> Self:
        return cls(
            group_id=payload["group_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            signature=IdenticalAttackSignature.from_payload(payload["signature"]),
            pool_indices=tuple(payload["pool_indices"]),
            total_attacks=payload["total_attacks"],
            contributions=tuple(
                GatheredAttackContribution.from_payload(contribution)
                for contribution in payload["contributions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AttackSequence:
    sequence_id: str
    attacker_player_id: str
    attacking_unit_instance_id: str
    attack_pools: tuple[RangedAttackPool, ...]
    source_phase: BattlePhase = BattlePhase.SHOOTING
    used_pool_indices: tuple[int, ...] = ()
    selected_target_unit_instance_id: str | None = None
    current_gathered_group: GatheredAttackGroup | None = None
    pool_index: int = 0
    attack_index: int = 0
    generated_hit_index: int = 0
    current_hit_roll: HitRoll | None = None
    deferred_mortal_wounds: tuple[DeferredMortalWounds, ...] = ()
    pending_grouped_damage: PendingGroupedDamage | None = None
    pending_destroyed_transport_disembark: PendingDestroyedTransportDisembark | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence_id",
            _validate_identifier("AttackSequence sequence_id", self.sequence_id),
        )
        object.__setattr__(
            self,
            "source_phase",
            battle_phase_kind_from_token(self.source_phase),
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
            "used_pool_indices",
            _validate_pool_index_tuple("AttackSequence used_pool_indices", self.used_pool_indices),
        )
        _validate_pool_indices_within_attack_pools(
            field_name="AttackSequence used_pool_indices",
            pool_indices=self.used_pool_indices,
            attack_pools=self.attack_pools,
        )
        object.__setattr__(
            self,
            "selected_target_unit_instance_id",
            _validate_optional_identifier(
                "AttackSequence selected_target_unit_instance_id",
                self.selected_target_unit_instance_id,
            ),
        )
        if self.current_gathered_group is not None:
            if type(self.current_gathered_group) is not GatheredAttackGroup:
                raise GameLifecycleError(
                    "AttackSequence current_gathered_group must be a GatheredAttackGroup."
                )
            _validate_gathered_group_matches_attack_pools(
                attack_pools=self.attack_pools,
                used_pool_indices=self.used_pool_indices,
                gathered_group=self.current_gathered_group,
            )
            if (
                self.selected_target_unit_instance_id
                != self.current_gathered_group.target_unit_instance_id
            ):
                raise GameLifecycleError("AttackSequence gathered group target drift.")
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
        if self.pending_grouped_damage is not None:
            if type(self.pending_grouped_damage) is not PendingGroupedDamage:
                raise GameLifecycleError(
                    "AttackSequence pending_grouped_damage must be PendingGroupedDamage."
                )
            if self.attack_index != 0:
                raise GameLifecycleError(
                    "AttackSequence pending_grouped_damage requires attack_index 0."
                )
            if self.generated_hit_index != 0 or self.current_hit_roll is not None:
                raise GameLifecycleError(
                    "AttackSequence pending_grouped_damage requires no generated hit state."
                )
        if (
            self.pending_destroyed_transport_disembark is not None
            and type(self.pending_destroyed_transport_disembark)
            is not PendingDestroyedTransportDisembark
        ):
            raise GameLifecycleError(
                "AttackSequence pending_destroyed_transport_disembark must be "
                "PendingDestroyedTransportDisembark."
            )
        if self.pool_index > len(self.attack_pools):
            raise GameLifecycleError("AttackSequence pool_index is outside attack_pools.")
        if self.pool_index == len(self.attack_pools):
            if self.used_pool_indices and len(self.used_pool_indices) != len(self.attack_pools):
                raise GameLifecycleError("Completed AttackSequence has unresolved attack pools.")
            if self.selected_target_unit_instance_id is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have selected target state."
                )
            if self.current_gathered_group is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have current_gathered_group."
                )
            if self.pending_grouped_damage is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have pending_grouped_damage."
                )
            if self.pending_destroyed_transport_disembark is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have pending destroyed Transport state."
                )
            if self.attack_index != 0:
                raise GameLifecycleError("Completed AttackSequence must have attack_index 0.")
            if self.generated_hit_index != 0:
                raise GameLifecycleError("Completed AttackSequence must not track generated hits.")
            if self.current_hit_roll is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence must not include a current hit roll."
                )
            return
        if (
            self.current_gathered_group is not None
            and self.pool_index != self.current_gathered_group.primary_pool_index
        ):
            raise GameLifecycleError("AttackSequence pool_index must match gathered group.")
        if self.attack_index >= self.current_pool().attacks:
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
        source_phase: BattlePhase = BattlePhase.SHOOTING,
    ) -> Self:
        return cls(
            sequence_id=sequence_id,
            source_phase=source_phase,
            attacker_player_id=attacker_player_id,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attack_pools=attack_pools,
        )

    @property
    def is_complete(self) -> bool:
        return self.pool_index == len(self.attack_pools) or (
            len(self.used_pool_indices) == len(self.attack_pools)
            and self.current_gathered_group is None
        )

    def current_pool(self) -> RangedAttackPool:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence has no current pool.")
        if self.current_gathered_group is not None:
            return _synthetic_pool_for_gathered_group(
                attack_pools=self.attack_pools,
                gathered_group=self.current_gathered_group,
            )
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
        if self.pending_grouped_damage is not None:
            raise GameLifecycleError("AttackSequence cannot advance with pending grouped damage.")
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
                source_phase=self.source_phase,
                used_pool_indices=self.used_pool_indices,
                selected_target_unit_instance_id=self.selected_target_unit_instance_id,
                current_gathered_group=self.current_gathered_group,
                pool_index=self.pool_index,
                attack_index=next_attack_index,
                deferred_mortal_wounds=self.deferred_mortal_wounds,
                pending_grouped_damage=self.pending_grouped_damage,
                pending_destroyed_transport_disembark=(self.pending_destroyed_transport_disembark),
            )
        next_pool_index = self.pool_index + 1
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=next_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
        )

    def advanced_after_generated_hit(self, hit_roll: HitRoll) -> Self:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence cannot advance generated hits.")
        if self.pending_grouped_damage is not None:
            raise GameLifecycleError(
                "AttackSequence cannot advance generated hits with pending grouped damage."
            )
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
                source_phase=self.source_phase,
                used_pool_indices=self.used_pool_indices,
                selected_target_unit_instance_id=self.selected_target_unit_instance_id,
                current_gathered_group=self.current_gathered_group,
                pool_index=self.pool_index,
                attack_index=self.attack_index,
                deferred_mortal_wounds=self.deferred_mortal_wounds,
                pending_grouped_damage=self.pending_grouped_damage,
                pending_destroyed_transport_disembark=(self.pending_destroyed_transport_disembark),
            ).advanced_after_attack()
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=next_generated_hit_index,
            current_hit_roll=hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=(self.pending_destroyed_transport_disembark),
        )

    def with_deferred_mortal_wounds(self, deferred: DeferredMortalWounds) -> Self:
        if type(deferred) is not DeferredMortalWounds:
            raise GameLifecycleError("AttackSequence deferred mortal wounds are invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=(*self.deferred_mortal_wounds, deferred),
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
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
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
        )

    def with_pending_grouped_damage(self, pending: PendingGroupedDamage) -> Self:
        if type(pending) is not PendingGroupedDamage:
            raise GameLifecycleError("AttackSequence pending grouped damage is invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=pending,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
        )

    def without_pending_grouped_damage(self) -> Self:
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
        )

    def with_pending_destroyed_transport_disembark(
        self,
        pending: PendingDestroyedTransportDisembark,
    ) -> Self:
        if type(pending) is not PendingDestroyedTransportDisembark:
            raise GameLifecycleError("AttackSequence destroyed Transport pending state is invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=pending,
        )

    def without_pending_destroyed_transport_disembark(self) -> Self:
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
        )

    def with_selected_target_unit(self, target_unit_instance_id: str) -> Self:
        target_id = _validate_identifier("AttackSequence selected target", target_unit_instance_id)
        if target_id not in unresolved_target_unit_ids(self):
            raise GameLifecycleError("Selected resolve target has no unresolved attack pools.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=target_id,
            pool_index=_first_unresolved_pool_index_for_target(
                attack_sequence=self,
                target_unit_instance_id=target_id,
            ),
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
        )

    def without_selected_target_unit(self) -> Self:
        next_pool_index = _first_unresolved_pool_index(self)
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=None,
            pool_index=next_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
        )

    def with_current_gathered_group(self, gathered_group: GatheredAttackGroup) -> Self:
        if type(gathered_group) is not GatheredAttackGroup:
            raise GameLifecycleError("AttackSequence gathered group is invalid.")
        if self.selected_target_unit_instance_id != gathered_group.target_unit_instance_id:
            raise GameLifecycleError("Gathered attack group target drift.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=gathered_group,
            pool_index=gathered_group.primary_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
        )

    def to_payload(self) -> AttackSequencePayload:
        return {
            "sequence_id": self.sequence_id,
            "source_phase": self.source_phase.value,
            "attacker_player_id": self.attacker_player_id,
            "attacking_unit_instance_id": self.attacking_unit_instance_id,
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "used_pool_indices": list(self.used_pool_indices),
            "selected_target_unit_instance_id": self.selected_target_unit_instance_id,
            "current_gathered_group": (
                None
                if self.current_gathered_group is None
                else self.current_gathered_group.to_payload()
            ),
            "pool_index": self.pool_index,
            "attack_index": self.attack_index,
            "generated_hit_index": self.generated_hit_index,
            "current_hit_roll": (
                None if self.current_hit_roll is None else self.current_hit_roll.to_payload()
            ),
            "deferred_mortal_wounds": [
                deferred.to_payload() for deferred in self.deferred_mortal_wounds
            ],
            "pending_grouped_damage": (
                None
                if self.pending_grouped_damage is None
                else self.pending_grouped_damage.to_payload()
            ),
            "pending_destroyed_transport_disembark": (
                None
                if self.pending_destroyed_transport_disembark is None
                else self.pending_destroyed_transport_disembark.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: AttackSequencePayload) -> Self:
        pending_destroyed_transport_payload = payload.get("pending_destroyed_transport_disembark")
        return cls(
            sequence_id=payload["sequence_id"],
            source_phase=battle_phase_kind_from_token(
                payload.get("source_phase", BattlePhase.SHOOTING.value)
            ),
            attacker_player_id=payload["attacker_player_id"],
            attacking_unit_instance_id=payload["attacking_unit_instance_id"],
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            used_pool_indices=tuple(payload["used_pool_indices"]),
            selected_target_unit_instance_id=payload["selected_target_unit_instance_id"],
            current_gathered_group=(
                None
                if payload["current_gathered_group"] is None
                else GatheredAttackGroup.from_payload(payload["current_gathered_group"])
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
            pending_grouped_damage=(
                None
                if payload["pending_grouped_damage"] is None
                else PendingGroupedDamage.from_payload(payload["pending_grouped_damage"])
            ),
            pending_destroyed_transport_disembark=(
                None
                if pending_destroyed_transport_payload is None
                else PendingDestroyedTransportDisembark.from_payload(
                    pending_destroyed_transport_payload
                )
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


def _runtime_modifier_registry(
    registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if registry is None:
        return RuntimeModifierRegistry.empty()
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Attack sequence runtime modifier registry is invalid.")
    return registry


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


def apply_resolve_target_unit_decision(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
) -> AttackSequence:
    record = decisions.record_for_result(result)
    result.validate_for_request(record.request)
    return attack_sequence.with_selected_target_unit(selected_resolve_target_from_result(result))


def apply_attack_weapon_group_decision(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
) -> AttackSequence:
    record = decisions.record_for_result(result)
    result.validate_for_request(record.request)
    return attack_sequence.with_current_gathered_group(
        selected_attack_weapon_group_from_result(result)
    )


def resolve_attack_sequence_until_blocked(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    active_hooks = AttackSequenceHooks.empty() if hooks is None else hooks
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    allocated_model_ids = already_allocated_model_ids
    current = attack_sequence
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    while not current.is_complete:
        if current.pending_destroyed_transport_disembark is not None:
            next_current, allocated_model_ids, status = (
                _continue_pending_destroyed_transport_disembark(
                    state=state,
                    decisions=decisions,
                    ruleset_descriptor=ruleset_descriptor,
                    manager=manager,
                    attack_sequence=current,
                    allocated_model_ids=allocated_model_ids,
                    hooks=active_hooks,
                )
            )
            if status is not None:
                return next_current, allocated_model_ids, status
            if next_current is None:
                return None, allocated_model_ids, None
            current = next_current
            continue
        if current.pending_grouped_damage is not None:
            next_current, allocated_model_ids, status = _resolve_grouped_damage_from(
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                manager=manager,
                attack_sequence=current,
                hooks=active_hooks,
                stratagem_index=stratagem_index,
                runtime_modifier_registry=runtime_modifiers,
            )
            if status is not None:
                return next_current, allocated_model_ids, status
            if next_current is None:
                return None, allocated_model_ids, None
            current = next_current
            continue
        if current.current_gathered_group is None:
            current, status = _select_or_request_next_gathered_group(
                state=state,
                decisions=decisions,
                attack_sequence=current,
            )
            if status is not None:
                return current, allocated_model_ids, status
            if current.is_complete:
                break
        next_current, allocated_model_ids, status = _resolve_grouped_current_pool(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            manager=manager,
            attack_sequence=current,
            allocated_model_ids=allocated_model_ids,
            hooks=active_hooks,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifiers,
        )
        if status is not None:
            return next_current, allocated_model_ids, status
        if next_current is None:
            return None, allocated_model_ids, None
        current = next_current
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
    hazardous_status = _resolve_hazardous_tests(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=current,
    )
    if hazardous_status is not None:
        return current, allocated_model_ids, hazardous_status
    return None, allocated_model_ids, None


def is_destroyed_transport_disembark_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError(
            "Destroyed Transport disembark proposal routing requires a DecisionRequest."
        )
    if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    if proposal_request.proposal_kind is not ProposalKind.DISEMBARK:
        return False
    context = proposal_request.context or {}
    return context.get("destruction_timing") == "destroyed_transport"


def invalid_destroyed_transport_disembark_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    if not is_destroyed_transport_disembark_proposal_request(request):
        raise GameLifecycleError(
            "Destroyed Transport disembark prevalidation received unsupported request."
        )
    result.validate_for_request(request)
    pending = attack_sequence.pending_destroyed_transport_disembark
    if pending is None:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=MovementProposalRequest.from_decision_request_payload(request.payload),
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                violation_code="destroyed_transport_context_missing",
                message="Destroyed Transport placement has no pending attack context.",
                field=None,
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal has no pending context.",
        )
    parsed = _parse_destroyed_transport_disembark_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal_request, submission = parsed
    proposal_validation = submission.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal does not match request.",
        )
    field = _missing_destroyed_transport_disembark_field(submission)
    if field is not None:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="proposal_payload_missing_field",
                message=f"Destroyed Transport disembark proposal missing {field}.",
                field=field,
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal is incomplete.",
        )
    if submission.unit_instance_id != pending.next_unit_instance_id:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_unit_drift",
                message="Destroyed Transport disembark unit does not match pending cargo.",
                field="unit_instance_id",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal unit drifted.",
        )
    if submission.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_mode_drift",
                message="Destroyed Transport disembark must use Emergency Disembark mode.",
                field="disembark_mode",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal mode drifted.",
        )
    if submission.transport_unit_instance_id != pending.transport_unit_instance_id:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_transport_drift",
                message="Destroyed Transport disembark transport does not match pending context.",
                field="transport_unit_instance_id",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal transport drifted.",
        )
    if submission.transport_movement_status is not TransportMovementStatus.NOT_MOVED:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_status_drift",
                message="Destroyed Transport disembark must use destroyed timing.",
                field="transport_movement_status",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal timing drifted.",
        )
    return None


def apply_destroyed_transport_disembark_proposal_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_destroyed_transport_disembark_proposal_request(request):
        raise GameLifecycleError(
            "Destroyed Transport disembark apply received unsupported request."
        )
    pending = attack_sequence.pending_destroyed_transport_disembark
    if pending is None:
        raise GameLifecycleError("Destroyed Transport disembark apply requires pending state.")
    parsed = _parse_destroyed_transport_disembark_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return attack_sequence, already_allocated_model_ids, parsed
    proposal_request, submission = parsed
    if (
        submission.transport_unit_instance_id is None
        or submission.disembark_mode is None
        or submission.transport_movement_status is None
    ):
        raise GameLifecycleError("Destroyed Transport disembark submission drifted.")
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    disembark = _resolve_destroyed_transport_disembark_submission(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pending=pending,
        submission=submission,
        dice_manager=manager,
    )
    if not disembark.placement.is_valid:
        status = _destroyed_transport_placement_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            disembark=disembark,
        )
        _request_destroyed_transport_disembark_placement_retry(
            state=state,
            decisions=decisions,
            proposal_request=proposal_request,
            pending=pending,
            rejected_result=result,
        )
        return attack_sequence, already_allocated_model_ids, status
    _apply_valid_destroyed_transport_disembark(
        state=state,
        decisions=decisions,
        disembark=disembark,
        result=result,
        source_phase=attack_sequence.source_phase,
    )
    updated_pending = pending.with_resolved_disembark(disembark)
    updated_sequence = attack_sequence.with_pending_destroyed_transport_disembark(updated_pending)
    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=decisions,
        disembark=disembark,
        dice_manager=manager,
    )
    if routed.pending_mortal_wound_request is not None:
        return (
            updated_sequence,
            already_allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.pending_mortal_wound_request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "battle_round": state.battle_round,
                    "active_player_id": disembark.player_id,
                    "unit_instance_id": disembark.unit_instance_id,
                    "transport_unit_instance_id": disembark.transport_unit_instance_id,
                    "disembark_mode": disembark.disembark_mode.value,
                    "decision_type": routed.pending_mortal_wound_request.decision_type,
                    "phase_body_status": "destroyed_transport_hazard_feel_no_pain_required",
                },
            ),
        )
    return _continue_pending_destroyed_transport_disembark(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=updated_sequence,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
    )


def _continue_pending_destroyed_transport_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    pending = attack_sequence.pending_destroyed_transport_disembark
    if pending is None:
        raise GameLifecycleError("Destroyed Transport continuation requires pending state.")
    if pending.next_unit_instance_id is not None:
        request = _request_destroyed_transport_disembark_placement(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            pending=pending,
        )
        return (
            attack_sequence,
            allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": PLACEMENT_PROPOSAL_DECISION_TYPE,
                    "unit_instance_id": pending.next_unit_instance_id,
                    "transport_unit_instance_id": pending.transport_unit_instance_id,
                    "phase_body_status": "destroyed_transport_disembark_placement_required",
                },
            ),
        )

    sequence_without_pending = attack_sequence.without_pending_destroyed_transport_disembark()
    _remove_resolved_destroyed_transport_cargo_state(
        state=state,
        transport_unit_instance_id=pending.transport_unit_instance_id,
    )
    mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=sequence_without_pending,
        attack_context=pending.attack_context,
        damage=pending.damage_application,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
        sources=pending.pending_sources,
    )
    if mandatory_status is not None:
        return sequence_without_pending, allocated_model_ids, mandatory_status
    destroyed_model_placement = _destroyed_model_placement_payload(
        state=state,
        model_instance_id=pending.damage_application.model_instance_id,
    )
    remove_destroyed_model_from_battlefield(
        state=state,
        model_instance_id=pending.damage_application.model_instance_id,
    )
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=sequence_without_pending,
        damage=pending.damage_application,
        saving_throw=None,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_placement=destroyed_model_placement,
    )
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=sequence_without_pending,
        attack_context=pending.attack_context,
        damage=pending.damage_application,
        destroyed_emission=destroyed_emission,
        destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
    )
    if reaction_status is not None:
        return sequence_without_pending, allocated_model_ids, reaction_status
    if sequence_without_pending.pending_grouped_damage is not None:
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=sequence_without_pending,
            allocated_model_ids=allocated_model_ids,
            status=None,
            hooks=hooks,
            dice_manager=manager,
        )
    return (
        _advance_after_resolved_hit(
            attack_sequence=sequence_without_pending,
            attack_context=pending.attack_context,
        ),
        allocated_model_ids,
        None,
    )


def _remove_resolved_destroyed_transport_cargo_state(
    *,
    state: GameState,
    transport_unit_instance_id: str,
) -> None:
    cargo_state = state.transport_cargo_state_for_transport(transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Destroyed Transport cargo state is missing before removal.")
    if cargo_state.embarked_unit_instance_ids:
        raise GameLifecycleError("Destroyed Transport cargo state still has embarked units.")
    state.remove_transport_cargo_state(transport_unit_instance_id)


def _begin_destroyed_transport_disembark_if_needed(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str,
    sources: tuple[DestructionReactionSource, ...] = (),
) -> tuple[AttackSequence, LifecycleStatus | None]:
    if damage is None or not damage.destroyed:
        return attack_sequence, None
    cargo_state = _destroyed_transport_cargo_state_for_damage(state=state, damage=damage)
    if cargo_state is None or not cargo_state.embarked_unit_instance_ids:
        return attack_sequence, None
    pending = PendingDestroyedTransportDisembark(
        attack_context=attack_context,
        damage_application=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        transport_unit_instance_id=cargo_state.transport_unit_instance_id,
        pending_unit_instance_ids=cargo_state.embarked_unit_instance_ids,
        pending_sources=sources,
    )
    updated_sequence = attack_sequence.with_pending_destroyed_transport_disembark(pending)
    request = _request_destroyed_transport_disembark_placement(
        state=state,
        decisions=decisions,
        attack_sequence=updated_sequence,
        pending=pending,
    )
    return (
        updated_sequence,
        LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": attack_sequence.source_phase.value,
                "decision_type": PLACEMENT_PROPOSAL_DECISION_TYPE,
                "unit_instance_id": pending.next_unit_instance_id,
                "transport_unit_instance_id": pending.transport_unit_instance_id,
                "phase_body_status": "destroyed_transport_disembark_placement_required",
            },
        ),
    )


def _request_destroyed_transport_disembark_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    pending: PendingDestroyedTransportDisembark,
) -> DecisionRequest:
    unit_instance_id = pending.next_unit_instance_id
    if unit_instance_id is None:
        raise GameLifecycleError("Destroyed Transport placement request requires pending cargo.")
    attack_context_id = pending.attack_context["attack_context_id"]
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=pending.destroyed_model_controller_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=attack_sequence.source_phase.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=ProposalKind.DISEMBARK,
        source_decision_request_id=f"{attack_context_id}:destroyed-transport",
        source_decision_result_id=f"{attack_context_id}:destroyed-transport",
        placement_kinds=(BattlefieldPlacementKind.DISEMBARK,),
        context={
            "destruction_timing": "destroyed_transport",
            "transport_unit_instance_id": pending.transport_unit_instance_id,
            "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
            "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
            "attack_sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_context_id,
            "destroyed_model_instance_id": pending.damage_application.model_instance_id,
        },
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "destroyed_transport_disembark_placement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": attack_sequence.source_phase.value,
                "active_player_id": pending.destroyed_model_controller_player_id,
                "unit_instance_id": unit_instance_id,
                "transport_unit_instance_id": pending.transport_unit_instance_id,
                "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
                "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
                "request_id": request.request_id,
                "attack_sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_context_id,
                "destroyed_model_instance_id": pending.damage_application.model_instance_id,
                "remaining_embarked_unit_ids": list(pending.pending_unit_instance_ids),
                "phase_body_status": "destroyed_transport_disembark_placement_required",
            }
        ),
    )
    return request


def _parse_destroyed_transport_disembark_submission_or_invalid(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> tuple[MovementProposalRequest, PlacementProposalPayload] | LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    try:
        submission = PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, _payload_object(result.payload))
        )
    except (GameLifecycleError, PlacementError, KeyError, TypeError) as exc:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=_destroyed_transport_proposal_parse_failure(
                proposal_request=proposal_request,
                error=exc,
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal payload is malformed.",
        )
    return proposal_request, submission


def _destroyed_transport_proposal_parse_failure(
    *,
    proposal_request: MovementProposalRequest,
    error: GameLifecycleError | PlacementError | KeyError | TypeError,
) -> ProposalValidationResult:
    if type(error) is KeyError:
        missing = _key_error_field(error)
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="proposal_payload_missing_field",
            message=f"Proposal payload missing required field: {missing}.",
            field=missing,
        )
    message = str(error)
    field: str | None = "attempted_placement"
    violation_code = "proposal_payload_malformed"
    if "proposal_kind" in message:
        field = "proposal_kind"
    elif "disembark_mode" in message or "DisembarkModeKind" in message:
        field = "disembark_mode"
    elif "transport_movement_status" in message or "TransportMovementStatus" in message:
        field = "transport_movement_status"
    elif "transport_unit_instance_id" in message:
        field = "transport_unit_instance_id"
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=f"Proposal payload is malformed: {message}",
        field=field,
    )


def _key_error_field(error: KeyError) -> str:
    if len(error.args) != 1:
        return "payload"
    key = error.args[0]
    if type(key) is str and key.strip():
        return key.strip()
    return "payload"


def _missing_destroyed_transport_disembark_field(
    submission: PlacementProposalPayload,
) -> str | None:
    if submission.transport_unit_instance_id is None:
        return "transport_unit_instance_id"
    if submission.disembark_mode is None:
        return "disembark_mode"
    if submission.transport_movement_status is None:
        return "transport_movement_status"
    return None


def _destroyed_transport_proposal_invalid_status(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    proposal_validation: ProposalValidationResult,
    event_type: str,
    message: str,
) -> LifecycleStatus:
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": proposal_request.actor_id,
            "phase": proposal_request.phase,
            "unit_instance_id": proposal_request.unit_instance_id,
            "proposal_kind": proposal_request.proposal_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": proposal_validation.status,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        }
    )
    decisions.event_log.append(event_type, payload)
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload=payload,
    )


def _destroyed_transport_placement_invalid_status(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    disembark: DestroyedTransportDisembark,
) -> LifecycleStatus:
    first_violation = disembark.placement.violations[0]
    proposal_validation = ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=first_violation.violation_code.value,
        message=first_violation.message,
        field=None,
    )
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": disembark.player_id,
            "phase": proposal_request.phase,
            "unit_instance_id": disembark.unit_instance_id,
            "transport_unit_instance_id": disembark.transport_unit_instance_id,
            "disembark_mode": disembark.disembark_mode.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "invalid",
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
            "destroyed_transport_disembark": validate_json_value(disembark.to_payload()),
        }
    )
    decisions.event_log.append("destroyed_transport_disembark_placement_invalid", payload)
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Destroyed Transport disembark placement is not currently legal.",
        payload=payload,
    )


def _request_destroyed_transport_disembark_placement_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    pending: PendingDestroyedTransportDisembark,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    context = proposal_request.context or {}
    attack_sequence_id = context.get("attack_sequence_id")
    attack_context_id = context.get("attack_context_id")
    if type(attack_sequence_id) is not str or not attack_sequence_id:
        raise GameLifecycleError("Destroyed Transport retry missing attack_sequence_id.")
    if type(attack_context_id) is not str or not attack_context_id:
        raise GameLifecycleError("Destroyed Transport retry missing attack_context_id.")
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=proposal_request.phase,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        placement_kinds=proposal_request.placement_kinds,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "destroyed_transport_disembark_placement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": proposal_request.phase,
                "active_player_id": proposal_request.actor_id,
                "unit_instance_id": proposal_request.unit_instance_id,
                "transport_unit_instance_id": pending.transport_unit_instance_id,
                "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
                "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
                "request_id": request.request_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "attack_sequence_id": attack_sequence_id,
                "attack_context_id": attack_context_id,
                "destroyed_model_instance_id": pending.damage_application.model_instance_id,
                "remaining_embarked_unit_ids": list(pending.pending_unit_instance_ids),
                "phase_body_status": "destroyed_transport_disembark_placement_required",
            }
        ),
    )
    return request


def _resolve_destroyed_transport_disembark_submission(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pending: PendingDestroyedTransportDisembark,
    submission: PlacementProposalPayload,
    dice_manager: DiceRollManager,
) -> DestroyedTransportDisembark:
    if submission.transport_unit_instance_id is None or submission.disembark_mode is None:
        raise GameLifecycleError("Destroyed Transport disembark submission is incomplete.")
    cargo_state = state.transport_cargo_state_for_transport(submission.transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Destroyed Transport disembark cargo state is missing.")
    unit = unit_by_id(state=state, unit_instance_id=submission.unit_instance_id)
    transport_placement = _destroyed_transport_placement(
        state=state,
        pending=pending,
    )
    selection = DisembarkSelection(
        player_id=pending.destroyed_model_controller_player_id,
        battle_round=state.battle_round,
        unit_instance_id=submission.unit_instance_id,
        transport_unit_instance_id=submission.transport_unit_instance_id,
        attempted_placement=submission.attempted_placement,
        disembark_mode=submission.disembark_mode,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=submission.restriction_overrides,
    )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires battlefield_state.")
    return resolve_destroyed_transport_disembark(
        scenario=_battlefield_scenario_for_attack_sequence(state),
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=unit,
        transport_placement=transport_placement,
        dice_manager=dice_manager,
        battlefield_width_inches=battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        terrain_features=battlefield_state.terrain_features,
        objective_markers=_objective_markers_for_attack_sequence(state),
    )


def _apply_valid_destroyed_transport_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    disembark: DestroyedTransportDisembark,
    result: DecisionResult,
    source_phase: BattlePhase,
) -> None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires battlefield_state.")
    if disembark.placement.updated_cargo_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires updated cargo state.")
    if disembark.placement.disembarked_unit_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires disembarked state.")
    state.replace_battlefield_state(
        apply_destroyed_transport_disembark_to_battlefield(
            battlefield_state=battlefield_state,
            disembark=disembark,
        )
    )
    state.replace_transport_cargo_state(disembark.placement.updated_cargo_state)
    state.record_disembarked_unit_state(disembark.placement.disembarked_unit_state)
    decisions.event_log.append(
        "unit_disembarked",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": disembark.player_id,
                "phase": source_phase.value,
                "unit_instance_id": disembark.unit_instance_id,
                "transport_unit_instance_id": disembark.transport_unit_instance_id,
                "disembark_mode": disembark.disembark_mode.value,
                "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "destroyed_transport_unit_disembarked",
                "updated_cargo_state": validate_json_value(
                    disembark.placement.updated_cargo_state.to_payload()
                ),
                "disembarked_unit_state": validate_json_value(
                    disembark.placement.disembarked_unit_state.to_payload()
                ),
                "transition_batch": validate_json_value(
                    disembark.placement.transition_batch.to_payload()
                )
                if disembark.placement.transition_batch is not None
                else None,
                "destroyed_transport_disembark": validate_json_value(disembark.to_payload()),
            }
        ),
    )


def _destroyed_transport_cargo_state_for_damage(
    *,
    state: GameState,
    damage: DamageApplication,
) -> TransportCargoState | None:
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=damage.target_unit_instance_id,
    )
    if not any(
        model.model_instance_id == damage.model_instance_id
        for model in target_rules_unit.own_models
    ):
        raise GameLifecycleError("Destroyed model is not in the damaged unit.")
    target_unit = unit_by_id(
        state=state,
        unit_instance_id=target_rules_unit.component_unit_id_for_model(damage.model_instance_id),
    )
    for cargo_state in state.transport_cargo_states:
        if cargo_state.transport_unit_instance_id == target_unit.unit_instance_id:
            if len(target_unit.own_models) != 1:
                raise GameLifecycleError(
                    "Destroyed Transport orchestration currently requires one model per "
                    "Transport cargo state."
                )
            return cargo_state
    return None


def _destroyed_transport_placement(
    *,
    state: GameState,
    pending: PendingDestroyedTransportDisembark,
) -> UnitPlacement:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Destroyed Transport disembark requires battlefield_state.")
    try:
        return battlefield.unit_placement_by_id(pending.transport_unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Destroyed Transport must still be placed before removal."
        ) from exc


def _battlefield_scenario_for_attack_sequence(state: GameState) -> BattlefieldScenario:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Attack sequence requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )


def _objective_markers_for_attack_sequence(state: GameState) -> tuple[ObjectiveMarker, ...]:
    if state.mission_setup is None:
        return ()
    return tuple(marker.to_objective_marker() for marker in state.mission_setup.objective_markers)


def _select_or_request_next_gathered_group(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    current = attack_sequence
    while current.current_gathered_group is None and not current.is_complete:
        target_ids = unresolved_target_unit_ids(current)
        if not target_ids:
            return (
                AttackSequence(
                    sequence_id=current.sequence_id,
                    source_phase=current.source_phase,
                    attacker_player_id=current.attacker_player_id,
                    attacking_unit_instance_id=current.attacking_unit_instance_id,
                    attack_pools=current.attack_pools,
                    used_pool_indices=tuple(range(len(current.attack_pools))),
                    pool_index=len(current.attack_pools),
                    attack_index=0,
                    deferred_mortal_wounds=current.deferred_mortal_wounds,
                ),
                None,
            )
        if current.selected_target_unit_instance_id is None:
            request = build_select_resolve_target_unit_request(
                request_id=state.next_decision_request_id(),
                state=state,
                attack_sequence=current,
            )
            if len(target_ids) > 1:
                decisions.request_decision(request)
                return (
                    current,
                    LifecycleStatus.waiting_for_decision(
                        stage=GameLifecycleStage.BATTLE,
                        decision_request=request,
                        payload={
                            "phase": current.source_phase.value,
                            "decision_type": SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                            "sequence_id": current.sequence_id,
                        },
                    ),
                )
            target_id = next(iter(target_ids))
            _record_auto_attack_sequence_selection(
                decisions=decisions,
                request=request,
                option_id=_resolve_target_option_id(target_id),
            )
            current = current.with_selected_target_unit(target_id)
            continue
        target_unit_instance_id = current.selected_target_unit_instance_id
        groups = gathered_attack_groups_for_target(
            attack_sequence=current,
            target_unit_instance_id=target_unit_instance_id,
        )
        if not groups:
            current = current.without_selected_target_unit()
            continue
        request = build_select_attack_weapon_group_request(
            request_id=state.next_decision_request_id(),
            state=state,
            attack_sequence=current,
            target_unit_instance_id=target_unit_instance_id,
        )
        if len(groups) > 1:
            decisions.request_decision(request)
            return (
                current,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=request,
                    payload={
                        "phase": current.source_phase.value,
                        "decision_type": SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
                        "sequence_id": current.sequence_id,
                        "target_unit_instance_id": target_unit_instance_id,
                    },
                ),
            )
        group = next(iter(groups))
        _record_auto_attack_sequence_selection(
            decisions=decisions,
            request=request,
            option_id=group.group_id,
        )
        current = current.with_current_gathered_group(group)
    return current, None


def _record_auto_attack_sequence_selection(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
) -> DecisionResult:
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id=f"{request.request_id}:auto-result",
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    decisions.event_log.append(
        "attack_sequence_auto_selection_recorded",
        {
            "request_id": request.request_id,
            "result_id": result.result_id,
            "decision_type": request.decision_type,
            "selected_option_id": option_id,
        },
    )
    return result


def apply_allocation_order_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    decision = AllocationOrderDecision.from_result(request=request, result=result)
    request_payload = _payload_object(request.payload)
    raw_attack_contexts = request_payload["attack_contexts"]
    if not isinstance(raw_attack_contexts, list) or not raw_attack_contexts:
        raise GameLifecycleError("Pooled allocation order requires grouped attack contexts.")
    attack_contexts = tuple(
        cast(AttackResolutionContextPayload, raw_context) for raw_context in raw_attack_contexts
    )
    attack_context = cast(AttackResolutionContextPayload, request_payload["attack_context"])
    _validate_grouped_request_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Allocation order",
    )
    return _continue_after_grouped_allocation_order(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_sequence=attack_sequence,
        attack_contexts=attack_contexts,
        allocation_context=decision.allocation_context,
        allocation_groups=decision.ordered_groups(),
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        stratagem_index=stratagem_index,
    )


def apply_damage_allocation_model_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    decision = DamageAllocationModelDecision.from_result(request=request, result=result)
    attack_context = cast(AttackResolutionContextPayload, decision.attack_context)
    _validate_attack_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Damage allocation model",
    )
    if attack_sequence.pending_grouped_damage is None:
        raise GameLifecycleError("Damage allocation model decision requires grouped damage.")
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(
            attack_sequence.pending_grouped_damage.with_allocated_model_ids(
                already_allocated_model_ids
            )
        ),
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        selected_model_id=decision.selected_model_id,
        stratagem_index=stratagem_index,
    )


def current_legal_damage_allocation_model_ids(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
) -> tuple[str, ...] | None:
    if attack_sequence.pending_grouped_damage is None:
        raise GameLifecycleError("Damage allocation model legality requires grouped damage.")
    current_group = _current_allocation_group_for_order(
        state=state,
        allocation_groups=attack_sequence.pending_grouped_damage.ordered_allocation_groups(),
    )
    if current_group is None:
        return None
    return _legal_model_ids_for_allocation_group_damage(
        state=state,
        allocation_group=current_group,
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
    stratagem_index: StratagemCatalogIndex | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    result.validate_for_request(request)
    request_payload = _payload_object(request.payload)
    attack_context = cast(AttackResolutionContextPayload, request_payload["attack_context"])
    raw_attack_contexts = request_payload["attack_contexts"]
    if not isinstance(raw_attack_contexts, list) or not raw_attack_contexts:
        raise GameLifecycleError("Pooled Precision allocation requires grouped attack contexts.")
    _validate_grouped_request_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Precision allocation",
    )
    precision_selection = _precision_pool_selection(
        decisions=decisions,
        attack_sequence=attack_sequence,
    )
    allocation_context, allocation_groups, priority_group_ids = (
        _precision_grouped_allocation_context_and_groups(
            state=state,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            allocated_model_ids=already_allocated_model_ids,
            precision_selection=precision_selection,
        )
    )
    if not priority_group_ids:
        allocation_context = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            already_allocated_model_ids=_alive_allocated_model_ids(
                state=state,
                allocated_model_ids=already_allocated_model_ids,
            ),
        )
        allocation_groups = allocation_groups_for_context(
            state=state,
            allocation_context=allocation_context,
            include_priority_tiers=True,
        )
    return _continue_grouped_allocation_for_wound_contexts(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_sequence=attack_sequence,
        allocation_context=allocation_context,
        allocation_groups=allocation_groups,
        wounded_contexts=tuple(
            (
                _attack_sequence_for_context(
                    attack_sequence=attack_sequence,
                    attack_context=cast(AttackResolutionContextPayload, raw_context),
                ),
                cast(AttackResolutionContextPayload, raw_context),
            )
            for raw_context in raw_attack_contexts
        ),
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        priority_group_ids=priority_group_ids,
        stratagem_index=stratagem_index,
    )


def apply_feel_no_pain_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    if is_mortal_wound_feel_no_pain_request(request):
        decision_attack_sequence = attack_sequence
        if attack_sequence.pending_grouped_damage is not None:
            request_payload = _payload_object(request.payload)
            lost_wound_context = _payload_object(request_payload["lost_wound_context"])
            source_context = _payload_object(lost_wound_context["source_context"])
            if source_context["source_kind"] != DEADLY_DEMISE_SOURCE_KIND:
                raise GameLifecycleError(
                    "Pending grouped damage only supports Deadly Demise mortal wound FNP."
                )
            decision_attack_sequence = _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=_deadly_demise_attack_context_from_source_context(source_context),
            )
        updated_sequence, allocated_model_ids, status = (
            _apply_deferred_mortal_wound_feel_no_pain_decision(
                state=state,
                decisions=decisions,
                attack_sequence=decision_attack_sequence,
                result=result,
                request=request,
                already_allocated_model_ids=already_allocated_model_ids,
                dice_manager=dice_manager,
                hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
            )
        )
        if attack_sequence.pending_grouped_damage is None:
            return updated_sequence, allocated_model_ids, status
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
            status=status,
            hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
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
    lost_wound = _lost_wound_context_from_payload(decision.lost_wound_context)
    attack_context = lost_wound["attack_context"]
    _validate_lost_wound_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    )
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    damage_attack_sequence = (
        _attack_sequence_for_context(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        )
        if attack_sequence.pending_grouped_damage is not None
        else attack_sequence
    )
    if selected_source is None:
        resolution = FeelNoPainResolution.declined(requested_wounds=lost_wound["requested_wounds"])
    else:
        resolution = resolve_feel_no_pain_rolls(
            manager=manager,
            source=selected_source,
            player_id=attack_context["defender_player_id"],
            model_instance_id=lost_wound["allocated_model_id"],
            requested_wounds=lost_wound["requested_wounds"],
        )
    updated_sequence, allocated_model_ids, status = _apply_damage_after_feel_no_pain(
        state=state,
        decisions=decisions,
        attack_sequence=damage_attack_sequence,
        attack_context=attack_context,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        model_instance_id=lost_wound["allocated_model_id"],
        damage_kind=damage_kind_from_token(lost_wound["damage_kind"]),
        resolution=resolution,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        saving_throw_payload=lost_wound["saving_throw"],
        manager=manager,
    )
    if attack_sequence.pending_grouped_damage is None:
        return updated_sequence, allocated_model_ids, status
    return _continue_grouped_damage_after_interruption(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=attack_sequence,
        allocated_model_ids=allocated_model_ids,
        status=status,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        dice_manager=manager,
    )


def apply_destruction_reaction_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    dice_manager: DiceRollManager | None = None,
    hooks: AttackSequenceHooks | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    resolved_hooks = AttackSequenceHooks.empty() if hooks is None else hooks
    record = decisions.record_for_result(result)
    request = record.request
    decision = DestructionReactionDecision.from_result(request=request, result=result)
    selected_source = _selected_destruction_reaction_source_from_request(
        request=request,
        selected_source_id=decision.selected_source_id,
    )
    if selected_source is not None and selected_source.reaction_kind is not (
        decision.selected_reaction_kind
    ):
        raise GameLifecycleError("Selected destruction reaction kind drift.")
    context = _destruction_reaction_context_from_payload(decision.destruction_context)
    attack_context = context["attack_context"]
    _validate_attack_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Destruction reaction",
    )
    if decision.player_id != context["destroyed_model_controller_player_id"]:
        raise GameLifecycleError("Destruction reaction defender drift.")
    decisions.event_log.append(
        "destruction_reaction_resolved",
        {
            "decision": decision.to_payload(),
            "selected_source": None if selected_source is None else selected_source.to_payload(),
            "selected_reaction_kind": (
                None
                if decision.selected_reaction_kind is None
                else decision.selected_reaction_kind.value
            ),
            "action_host": _destruction_reaction_action_host(selected_source),
            "execution_status": (
                "declined" if selected_source is None else "recorded_for_action_host"
            ),
        },
    )
    continuation = context["continuation"]
    if _is_deadly_demise_continuation(continuation):
        manager = (
            DiceRollManager(state.game_id, event_log=decisions.event_log)
            if dice_manager is None
            else dice_manager
        )
        continuation_attack_sequence = attack_sequence
        if attack_sequence.pending_grouped_damage is not None:
            continuation_attack_sequence = _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=_deadly_demise_attack_context_from_source_context(
                    _payload_object(continuation)
                ),
            )
        updated_sequence, allocated_model_ids, status = (
            _continue_deadly_demise_after_secondary_destruction_reaction(
                state=state,
                decisions=decisions,
                manager=manager,
                hooks=resolved_hooks,
                attack_sequence=continuation_attack_sequence,
                already_allocated_model_ids=already_allocated_model_ids,
                continuation=continuation,
            )
        )
        if attack_sequence.pending_grouped_damage is None:
            return updated_sequence, allocated_model_ids, status
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
            status=status,
            hooks=resolved_hooks,
            dice_manager=manager,
        )
    if attack_sequence.pending_grouped_damage is not None:
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=already_allocated_model_ids,
            status=None,
            hooks=resolved_hooks,
            dice_manager=dice_manager,
        )
    updated_sequence = _advance_after_resolved_hit(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    )
    return updated_sequence, already_allocated_model_ids, None


def _continue_grouped_damage_after_interruption(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    allocated_model_ids: tuple[str, ...],
    status: LifecycleStatus | None,
    hooks: AttackSequenceHooks,
    dice_manager: DiceRollManager | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    pending = attack_sequence.pending_grouped_damage
    if pending is None:
        raise GameLifecycleError("Grouped damage interruption requires pending grouped damage.")
    updated_pending = pending.with_allocated_model_ids(allocated_model_ids)
    if status is not None:
        return (
            attack_sequence.with_pending_grouped_damage(updated_pending),
            allocated_model_ids,
            status,
        )
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(
            updated_pending.advanced_after_current_die()
        ),
        hooks=hooks,
        runtime_modifier_registry=runtime_modifiers,
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
    for deferred_index, deferred in enumerate(attack_sequence.deferred_mortal_wounds):
        sequence_after_current_target = attack_sequence.with_pending_deferred_mortal_wounds(
            attack_sequence.deferred_mortal_wounds[deferred_index + 1 :]
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{attack_sequence.sequence_id}:devastating-wounds:"
                f"{deferred.attack_context_id}:mortal-wounds"
            ),
            source_rule_id=DEVASTATING_WOUNDS_RULE_ID,
            source_context=validate_json_value(
                {
                    "source_kind": "devastating_wounds",
                    "sequence_id": attack_sequence.sequence_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "target_unit_instance_id": deferred.target_unit_instance_id,
                    "attack_context_ids": [deferred.attack_context_id],
                }
            ),
            target_unit_instance_id=deferred.target_unit_instance_id,
            defender_player_id=unit_owner_player_id(
                state=state,
                unit_instance_id=deferred.target_unit_instance_id,
            ),
            mortal_wounds=deferred.mortal_wounds,
            spill_over=False,
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
                        "phase": attack_sequence.source_phase.value,
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
            target_unit_id=deferred.target_unit_instance_id,
            attack_context_ids=(deferred.attack_context_id,),
            mortal_wounds=deferred.mortal_wounds,
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
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    request_payload = _payload_object(request.payload)
    lost_wound_context = _payload_object(request_payload["lost_wound_context"])
    request_source_context = _payload_object(lost_wound_context["source_context"])
    is_deadly_demise_request = (
        request_source_context.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND
    )
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
        remove_destroyed_models=not is_deadly_demise_request,
    )
    source_context = _payload_object(routed.progress.source_context)
    if source_context.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND:
        return _continue_deadly_demise_after_mortal_wound_feel_no_pain(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            already_allocated_model_ids=already_allocated_model_ids,
            routed=routed,
            hooks=hooks,
        )
    if source_context.get("source_kind") == HAZARDOUS_SOURCE_KIND:
        return _continue_hazardous_after_mortal_wound_feel_no_pain(
            decisions=decisions,
            attack_sequence=attack_sequence,
            already_allocated_model_ids=already_allocated_model_ids,
            routed=routed,
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
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
                },
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Deferred mortal wound Feel No Pain did not finish routing.")
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


def _continue_hazardous_after_mortal_wound_feel_no_pain(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    routed: MortalWoundRoutingResult,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    source_context = _hazardous_source_context_from_payload(routed.progress.source_context)
    if source_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError("Hazardous mortal wound source context sequence drift.")
    if source_context["attacking_unit_instance_id"] != attack_sequence.attacking_unit_instance_id:
        raise GameLifecycleError("Hazardous mortal wound source context attacker drift.")
    if source_context["mortal_wounds"] != routed.progress.mortal_wounds:
        raise GameLifecycleError("Hazardous mortal wound source context wound drift.")
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return (
            attack_sequence,
            already_allocated_model_ids,
            _hazardous_feel_no_pain_status(
                attack_sequence=attack_sequence,
                request=routed.request,
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Hazardous mortal wound Feel No Pain did not finish routing.")
    _emit_hazardous_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        source_context=source_context,
        application=routed.application,
    )
    return None, already_allocated_model_ids, None


def _continue_deadly_demise_after_mortal_wound_feel_no_pain(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    routed: MortalWoundRoutingResult,
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return (
            attack_sequence,
            already_allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": routed.progress.source_rule_id,
                    "source_kind": DEADLY_DEMISE_SOURCE_KIND,
                },
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Deadly Demise Feel No Pain did not finish routing.")
    source_context = _payload_object(routed.progress.source_context)
    attack_context = _deadly_demise_attack_context_from_source_context(source_context)
    damage = DamageApplication.from_payload(
        cast(DamageApplicationPayload, source_context["damage_application"])
    )
    feel_no_pain = FeelNoPainResolution.from_payload(
        cast(FeelNoPainResolutionPayload, source_context["feel_no_pain"])
    )
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, source_context["source"])
    )
    descriptor = _payload_object(source_context["descriptor"])
    destroyed_model_controller_player_id = _payload_string(
        source_context,
        key="destroyed_model_controller_player_id",
    )
    trigger_roll_payload = validate_json_value(source_context["trigger_roll"])
    affected_target_unit_ids = _payload_identifier_tuple(
        source_context,
        key="affected_target_unit_ids",
    )
    pending_target_unit_ids = _payload_identifier_tuple(
        source_context,
        key="pending_target_unit_ids",
    )
    pending_source_payloads = source_context.get("pending_sources")
    if not isinstance(pending_source_payloads, list):
        raise GameLifecycleError("Deadly Demise source context pending_sources must be a list.")
    pending_sources = tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, payload))
        for payload in pending_source_payloads
    )
    _emit_deadly_demise_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        source=source,
        target_unit_id=routed.progress.target_unit_instance_id,
        mortal_wounds=routed.progress.mortal_wounds,
        application=routed.application,
        wound_roll_payload=validate_json_value(source_context["mortal_wound_roll"]),
    )
    status = _resolve_deadly_demise_secondary_destroyed_models(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        source_damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        affected_target_unit_ids=affected_target_unit_ids,
        pending_target_unit_ids=pending_target_unit_ids,
        pending_sources=pending_sources,
        secondary_damage_applications=_destroyed_damage_applications(
            routed.application.applications
        ),
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    status = _route_deadly_demise_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        target_unit_ids=pending_target_unit_ids,
        pending_sources=pending_sources,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    _emit_mandatory_destruction_reaction_record(
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        execution_status="resolved",
        extra_payload={
            "deadly_demise": {
                "descriptor": validate_json_value(descriptor),
                "trigger_roll": trigger_roll_payload,
                "triggered": True,
                "affected_target_unit_ids": list(affected_target_unit_ids),
            },
        },
    )
    status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        sources=pending_sources,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    destroyed_model_placement = _destroyed_model_placement_payload(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    remove_destroyed_model_from_battlefield(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        destroyed_model_placement=destroyed_model_placement,
    )
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        destroyed_emission=destroyed_emission,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
    )
    if reaction_status is not None:
        return attack_sequence, already_allocated_model_ids, reaction_status
    return (
        _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        ),
        already_allocated_model_ids,
        None,
    )


def _grouped_precision_request_if_available(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    allocated_model_ids: tuple[str, ...],
) -> DecisionRequest | None:
    pool = attack_sequence.current_pool()
    if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION):
        return None
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
        ),
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        visible_model_ids=pool.target_visible_model_ids,
        include_priority_tiers=True,
    )
    eligible_character_groups = tuple(
        group for group in allocation_groups if group.role in _PRECISION_CHARACTER_GROUP_ROLES
    )
    if not eligible_character_groups:
        return None
    request = _build_precision_allocation_request(
        request_id=state.next_decision_request_id(),
        attacker_player_id=attack_context["attacker_player_id"],
        attack_context=validate_json_value(attack_context),
        allocation_context=allocation_context,
        eligible_character_groups=eligible_character_groups,
    )
    return DecisionRequest(
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=validate_json_value(
            {
                **cast(dict[str, JsonValue], request.payload),
                "attack_contexts": [validate_json_value(context) for context in attack_contexts],
            }
        ),
        options=request.options,
    )


def _precision_grouped_allocation_context_and_groups(
    *,
    state: GameState,
    target_unit_instance_id: str,
    allocated_model_ids: tuple[str, ...],
    precision_selection: PrecisionPoolSelection,
) -> tuple[AttackAllocationRuleContext, tuple[AllocationGroup, ...], tuple[str, ...]]:
    if type(precision_selection) is not PrecisionPoolSelection:
        raise GameLifecycleError("Precision grouped allocation selection is invalid.")
    alive_selected_model_ids = tuple(
        model_id
        for model_id in precision_selection.selected_model_ids
        if _model_is_alive(state=state, model_instance_id=model_id)
    )
    attacker_constraint = None
    priority_group_ids: tuple[str, ...] = ()
    if precision_selection.selected_group_id is not None and alive_selected_model_ids:
        attacker_constraint = AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
            attacker_selected_group_id=precision_selection.selected_group_id,
        )
        priority_group_ids = (precision_selection.selected_group_id,)
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=attacker_constraint,
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        include_priority_tiers=True,
    )
    if priority_group_ids and not any(
        group.group_id == priority_group_ids[0] for group in allocation_groups
    ):
        return _precision_grouped_allocation_context_and_groups(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            allocated_model_ids=allocated_model_ids,
            precision_selection=PrecisionPoolSelection(
                selected_group_id=None,
                selected_model_ids=(),
                selection_recorded=precision_selection.selection_recorded,
            ),
        )
    return allocation_context, allocation_groups, priority_group_ids


def _build_precision_allocation_request(
    *,
    request_id: str,
    attacker_player_id: str,
    attack_context: JsonValue,
    allocation_context: AttackAllocationRuleContext,
    eligible_character_groups: tuple[AllocationGroup, ...],
) -> DecisionRequest:
    character_groups = _validate_allocation_group_tuple(
        "Precision eligible_character_groups",
        eligible_character_groups,
    )
    if not character_groups:
        raise GameLifecycleError("Precision allocation request requires eligible characters.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        actor_id=attacker_player_id,
        payload=validate_json_value(
            {
                "attack_context": attack_context,
                "allocation_context": allocation_context.to_payload(),
                "eligible_character_groups": [group.to_payload() for group in character_groups],
                "decline_option_id": "decline_precision",
                "source_rule_id": PRECISION_RULE_ID,
            }
        ),
        options=(
            DecisionOption(
                option_id="decline_precision",
                label="Decline Precision",
                payload={"selected_group_id": None, "selected_model_ids": []},
            ),
            *(
                DecisionOption(
                    option_id=group.group_id,
                    label=group.group_id,
                    payload={
                        "selected_group_id": group.group_id,
                        "selected_model_ids": list(group.model_ids),
                        "role": group.role.value,
                    },
                )
                for group in character_groups
            ),
        ),
    )


def _precision_pool_selection(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> PrecisionPoolSelection:
    selected_group_id: str | None = None
    selected_model_ids: tuple[str, ...] = ()
    selection_recorded = False
    for record in decisions.records:
        if record.request.decision_type != SELECT_PRECISION_ALLOCATION_DECISION_TYPE:
            continue
        request_payload = _payload_object(record.request.payload)
        attack_context = cast(
            AttackResolutionContextPayload,
            request_payload["attack_context"],
        )
        if attack_context["sequence_id"] != attack_sequence.sequence_id:
            continue
        if attack_context["pool_index"] != attack_sequence.pool_index:
            continue
        current_selected_group_id = _precision_selected_group_id(record.result.payload)
        current_selected_model_ids = _precision_selected_model_ids(record.result.payload)
        if selection_recorded:
            if selected_group_id != current_selected_group_id:
                raise GameLifecycleError("Precision selection must be unique for an attack pool.")
            continue
        selected_group_id = current_selected_group_id
        selected_model_ids = current_selected_model_ids
        selection_recorded = True
    return PrecisionPoolSelection(
        selected_group_id=selected_group_id,
        selected_model_ids=selected_model_ids,
        selection_recorded=selection_recorded,
    )


def _resolve_grouped_current_pool(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if attack_sequence.attack_index != 0:
        raise GameLifecycleError("Pooled attack resolution must enter pools at attack_index 0.")
    if attack_sequence.generated_hit_index != 0 or attack_sequence.current_hit_roll is not None:
        raise GameLifecycleError("Pooled attack resolution cannot start with generated hit state.")
    pool = attack_sequence.current_pool()
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=None,
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        include_priority_tiers=True,
    )
    if not allocation_groups:
        raise GameLifecycleError("Pooled attack resolution has no legal allocation groups.")

    wounded_contexts, status = _grouped_wounded_contexts_for_pool(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    if not wounded_contexts:
        return (
            _advance_after_current_pool(attack_sequence=attack_sequence),
            allocated_model_ids,
            None,
        )
    attack_sequence, normal_wounded_contexts, status = _defer_grouped_devastating_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        wounded_contexts=wounded_contexts,
        hooks=hooks,
        stratagem_index=stratagem_index,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    if not normal_wounded_contexts:
        return (
            _advance_after_current_pool(attack_sequence=attack_sequence),
            allocated_model_ids,
            None,
        )
    return _continue_grouped_allocation_for_wound_contexts(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence,
        allocation_context=allocation_context,
        allocation_groups=allocation_groups,
        wounded_contexts=normal_wounded_contexts,
        allocated_model_ids=allocated_model_ids,
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def _grouped_wounded_contexts_for_pool(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    pool = attack_sequence.current_pool()
    wounded_contexts: list[tuple[AttackSequence, AttackResolutionContextPayload]] = []
    for attack_index in range(pool.attacks):
        current = AttackSequence(
            sequence_id=attack_sequence.sequence_id,
            source_phase=attack_sequence.source_phase,
            attacker_player_id=attack_sequence.attacker_player_id,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attack_pools=attack_sequence.attack_pools,
            used_pool_indices=attack_sequence.used_pool_indices,
            selected_target_unit_instance_id=attack_sequence.selected_target_unit_instance_id,
            current_gathered_group=attack_sequence.current_gathered_group,
            pool_index=attack_sequence.pool_index,
            attack_index=attack_index,
            deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
        )
        while True:
            attack_context, status = _roll_hit_and_wound(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=current,
                hooks=hooks,
                stratagem_index=stratagem_index,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            if status is not None:
                return (), status
            if attack_context is None:
                break
            if attack_context["wound_roll"]["successful"]:
                wounded_contexts.append((current, attack_context))
            hit_roll = HitRoll.from_payload(attack_context["hit_roll"])
            if current.generated_hit_index + 1 >= hit_roll.generated_hits:
                break
            next_sequence = current.advanced_after_generated_hit(hit_roll)
            if (
                next_sequence.pool_index != current.pool_index
                or next_sequence.attack_index != current.attack_index
            ):
                break
            current = next_sequence
    return tuple(wounded_contexts), None


def _defer_grouped_devastating_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
) -> tuple[
    AttackSequence,
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    current = attack_sequence
    normal_contexts: list[tuple[AttackSequence, AttackResolutionContextPayload]] = []
    pool = attack_sequence.current_pool()
    for wounded_sequence, attack_context in wounded_contexts:
        resolution = _devastating_wounds_resolution_for_attack(
            pool=pool,
            attack_context=attack_context,
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=attack_context["target_unit_instance_id"],
            ).keywords,
        )
        if resolution is not DevastatingWoundsResolution.MORTAL_WOUNDS:
            normal_contexts.append((wounded_sequence, attack_context))
            continue
        damage_value, status = _damage_value(
            state=state,
            decisions=decisions,
            manager=manager,
            profile=pool.weapon_profile.damage_profile,
            attack_context_id=attack_context["attack_context_id"],
            attacker_player_id=attack_sequence.attacker_player_id,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
        )
        if status is not None:
            return current, (), status
        if damage_value is None:
            raise GameLifecycleError("Damage roll did not resolve a value.")
        mortal_wounds = damage_value + _melta_damage_modifier(
            pool,
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=attack_context["target_unit_instance_id"],
            ).keywords,
        )
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
                sequence_id=wounded_sequence.sequence_id,
                attack_context_id=attack_context["attack_context_id"],
                pool_index=wounded_sequence.pool_index,
                attack_index=wounded_sequence.attack_index,
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
        current = current.with_deferred_mortal_wounds(deferred)
    return current, tuple(normal_contexts), None


def _continue_grouped_allocation_for_wound_contexts(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    priority_group_ids: tuple[str, ...] = (),
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if not wounded_contexts:
        raise GameLifecycleError("Grouped allocation requires wounded contexts.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    pool = attack_sequence.current_pool()
    grouped_attack_context = _grouped_attack_context_payload(
        attack_sequence=attack_sequence,
        attack_contexts=tuple(context for _, context in wounded_contexts),
        pool=pool,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ),
    )
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION):
        precision_selection = _precision_pool_selection(
            decisions=decisions,
            attack_sequence=attack_sequence,
        )
        if not precision_selection.selection_recorded:
            precision_request = _grouped_precision_request_if_available(
                state=state,
                attack_sequence=attack_sequence,
                attack_context=grouped_attack_context,
                attack_contexts=tuple(context for _, context in wounded_contexts),
                allocated_model_ids=allocated_model_ids,
            )
            if precision_request is not None:
                decisions.request_decision(precision_request)
                return (
                    attack_sequence,
                    allocated_model_ids,
                    LifecycleStatus.waiting_for_decision(
                        stage=GameLifecycleStage.BATTLE,
                        decision_request=precision_request,
                        payload={
                            "phase": attack_sequence.source_phase.value,
                            "decision_type": SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
                            "attack_context_id": grouped_attack_context["attack_context_id"],
                        },
                    ),
                )
        if precision_selection.selected_group_id is not None:
            allocation_context, allocation_groups, priority_group_ids = (
                _precision_grouped_allocation_context_and_groups(
                    state=state,
                    target_unit_instance_id=pool.target_unit_instance_id,
                    allocated_model_ids=allocated_model_ids,
                    precision_selection=precision_selection,
                )
            )
    allocation_orders = legal_allocation_group_orders(
        allocation_groups,
        priority_group_ids=priority_group_ids,
    )
    if not allocation_orders:
        raise GameLifecycleError("Grouped allocation has no legal group order.")
    if len(allocation_orders) > 1:
        request = build_allocation_order_request(
            request_id=state.next_decision_request_id(),
            defender_player_id=grouped_attack_context["defender_player_id"],
            attack_context=validate_json_value(grouped_attack_context),
            attack_contexts=tuple(validate_json_value(context) for _, context in wounded_contexts),
            allocation_context=allocation_context,
            allocation_groups=allocation_groups,
            priority_group_ids=priority_group_ids,
        )
        decisions.request_decision(request)
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.ALLOCATE,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=grouped_attack_context["attack_context_id"],
                pool_index=attack_sequence.pool_index,
                attack_index=0,
                payload=validate_json_value(
                    {
                        "allocation_context": allocation_context.to_payload(),
                        "allocation_groups": [group.to_payload() for group in allocation_groups],
                        "priority_group_ids": list(priority_group_ids),
                        "attack_context_ids": [
                            context["attack_context_id"] for _, context in wounded_contexts
                        ],
                        "forced": False,
                        "grouped_save_before_allocation": True,
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
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_ALLOCATION_ORDER_DECISION_TYPE,
                    "attack_context_id": grouped_attack_context["attack_context_id"],
                },
            ),
        )
    ordered_groups = _first_allocation_group_order(
        "Grouped allocation orders",
        allocation_orders,
    )
    _emit_grouped_allocation_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        attack_contexts=tuple(context for _, context in wounded_contexts),
        allocation_context=allocation_context,
        allocation_groups=ordered_groups,
    )
    save_results, status = _roll_grouped_saves(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        wounded_contexts=wounded_contexts,
        allocation_group=_first_allocation_group("Grouped allocation order", ordered_groups),
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    pending = PendingGroupedDamage(
        sorted_save_dice=save_results,
        ordered_allocation_group_payloads=tuple(group.to_payload() for group in ordered_groups),
        allocation_context_payload=allocation_context.to_payload(),
        allocated_model_ids=allocated_model_ids,
    )
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(pending),
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )


def _continue_after_grouped_allocation_order(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if not attack_contexts:
        raise GameLifecycleError("Grouped allocation order requires attack contexts.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    ordered_groups = _validate_ordered_allocation_group_tuple(
        "Grouped allocation order allocation_groups",
        allocation_groups,
    )
    wounded_contexts = tuple(
        (
            _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=attack_context,
            ),
            attack_context,
        )
        for attack_context in attack_contexts
    )
    _emit_grouped_allocation_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        attack_contexts=attack_contexts,
        allocation_context=allocation_context,
        allocation_groups=ordered_groups,
    )
    save_results, status = _roll_grouped_saves(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        wounded_contexts=wounded_contexts,
        allocation_group=_first_allocation_group("Grouped allocation order", ordered_groups),
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    pending = PendingGroupedDamage(
        sorted_save_dice=save_results,
        ordered_allocation_group_payloads=tuple(group.to_payload() for group in ordered_groups),
        allocation_context_payload=allocation_context.to_payload(),
        allocated_model_ids=allocated_model_ids,
    )
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(pending),
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )


def _resolve_grouped_damage_from(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    selected_model_id: str | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if attack_sequence.pending_grouped_damage is None:
        raise GameLifecycleError("Grouped damage resume requires pending grouped damage.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    pool = attack_sequence.current_pool()
    current_pending = attack_sequence.pending_grouped_damage
    while current_pending.next_index < len(current_pending.sorted_save_dice):
        save_die = current_pending.sorted_save_dice[current_pending.next_index]
        attack_context = save_die["attack_context"]
        save_attack_sequence = _attack_sequence_for_context(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        )
        ordered_groups = current_pending.ordered_allocation_groups()
        current_group = _current_allocation_group_for_order(
            state=state,
            allocation_groups=ordered_groups,
        )
        if current_group is None:
            return (
                _advance_after_current_pool(
                    attack_sequence=attack_sequence.without_pending_grouped_damage()
                ),
                current_pending.allocated_model_ids,
                None,
            )
        base_allocation_context = current_pending.allocation_context()
        allocation_context = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
            already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
                state=state,
                target_unit_instance_id=pool.target_unit_instance_id,
                allocated_model_ids=current_pending.allocated_model_ids,
            ),
            attacker_constraint=base_allocation_context.attacker_constraint,
        )
        legal_group_model_ids = _legal_model_ids_for_allocation_group_damage(
            state=state,
            allocation_group=current_group,
        )
        if not legal_group_model_ids:
            raise GameLifecycleError("Allocation group has no alive legal damage models.")
        if selected_model_id is not None:
            current_model_id = _validate_identifier(
                "selected_model_id",
                selected_model_id,
            )
            if current_model_id not in legal_group_model_ids:
                raise GameLifecycleError("Selected damage allocation model is not legal.")
            allocation_forced = False
            selected_model_id = None
        elif len(legal_group_model_ids) > 1:
            request = build_damage_allocation_model_request(
                request_id=state.next_decision_request_id(),
                defender_player_id=attack_context["defender_player_id"],
                attack_context=validate_json_value(attack_context),
                allocation_context=allocation_context,
                allocation_group=current_group,
                legal_model_ids=legal_group_model_ids,
                save_die=validate_json_value(save_die),
            )
            decisions.request_decision(request)
            return (
                attack_sequence.with_pending_grouped_damage(current_pending),
                current_pending.allocated_model_ids,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=request,
                    payload={
                        "phase": attack_sequence.source_phase.value,
                        "decision_type": SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
                        "attack_context_id": attack_context["attack_context_id"],
                        "allocation_group_id": current_group.group_id,
                    },
                ),
            )
        else:
            current_model_id = next(iter(legal_group_model_ids))
            allocation_forced = True
        updated_allocated_ids = tuple(
            sorted({*current_pending.allocated_model_ids, *current_group.model_ids})
        )
        allocation = AttackAllocation(
            target_unit_instance_id=allocation_context.target_unit_instance_id,
            allocated_model_id=current_model_id,
            legal_model_ids=legal_group_model_ids,
            forced=allocation_forced,
            rule_context=allocation_context,
            source_rule_ids=(
                ()
                if allocation_context.attacker_constraint is None
                else allocation_context.attacker_constraint.source_rule_ids
            ),
        )
        damage_attack_context: AttackResolutionContextPayload = {
            **attack_context,
            "allocation": allocation.to_payload(),
            "save_options": [],
        }
        save_options = _save_options_for_allocation(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=save_attack_sequence,
            attack_context=attack_context,
            allocated_model_id=current_model_id,
            runtime_modifier_registry=runtime_modifiers,
        )
        if save_options:
            damage_attack_context = {
                **damage_attack_context,
                "save_options": [option.to_payload() for option in save_options],
            }
        roll_state = DiceRollState.from_payload(save_die["roll_state"])
        saving_throw = (
            None
            if not save_options
            else resolve_saving_throw(options=save_options, roll_state=roll_state)
        )
        _emit_grouped_save_die_event(
            decisions=decisions,
            hooks=hooks,
            attack_sequence=save_attack_sequence,
            attack_context=attack_context,
            roll_state=roll_state,
            saving_throw=saving_throw,
            save_options=save_options,
            allocation_group=current_group,
            allocated_model_id=current_model_id,
        )
        pending_for_die = current_pending.with_allocated_model_ids(updated_allocated_ids)
        if saving_throw is not None and saving_throw.successful:
            _emit_damage_event(
                state=state,
                decisions=decisions,
                hooks=hooks,
                attack_sequence=save_attack_sequence,
                damage=None,
                saving_throw=saving_throw,
            )
            current_pending = pending_for_die.advanced_after_current_die()
            continue
        damage_value, status = _damage_value(
            state=state,
            decisions=decisions,
            manager=manager,
            profile=pool.weapon_profile.damage_profile,
            attack_context_id=damage_attack_context["attack_context_id"],
            attacker_player_id=attack_sequence.attacker_player_id,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
        )
        if status is not None:
            return (
                attack_sequence.with_pending_grouped_damage(pending_for_die),
                pending_for_die.allocated_model_ids,
                status,
            )
        if damage_value is None:
            raise GameLifecycleError("Damage roll did not resolve a value.")
        damage_amount = damage_value + _melta_damage_modifier(
            pool,
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=pool.target_unit_instance_id,
            ).keywords,
        )
        _next_sequence, resolved_allocated_ids, status = _resolve_lost_wound_stage(
            state=state,
            decisions=decisions,
            attack_sequence=save_attack_sequence,
            target_unit_instance_id=pool.target_unit_instance_id,
            model_instance_id=current_model_id,
            requested_wounds=damage_amount,
            damage_kind=DamageKind.NORMAL,
            saving_throw=saving_throw,
            attack_context=damage_attack_context,
            allocated_model_ids=updated_allocated_ids,
            hooks=hooks,
            manager=manager,
        )
        pending_for_die = pending_for_die.with_allocated_model_ids(resolved_allocated_ids)
        if status is not None:
            interrupted_sequence = attack_sequence.with_pending_grouped_damage(pending_for_die)
            if (
                _next_sequence is not None
                and _next_sequence.pending_destroyed_transport_disembark is not None
            ):
                interrupted_sequence = (
                    interrupted_sequence.with_pending_destroyed_transport_disembark(
                        _next_sequence.pending_destroyed_transport_disembark
                    )
                )
            return (
                interrupted_sequence,
                pending_for_die.allocated_model_ids,
                status,
            )
        current_pending = pending_for_die.advanced_after_current_die()
    return (
        _advance_after_current_pool(
            attack_sequence=attack_sequence.without_pending_grouped_damage()
        ),
        current_pending.allocated_model_ids,
        None,
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


def _alive_allocated_model_ids_for_target_unit(
    *,
    state: GameState,
    target_unit_instance_id: str,
    allocated_model_ids: tuple[str, ...],
) -> tuple[str, ...]:
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    target_model_ids = {model.model_instance_id for model in target_rules_unit.own_models}
    return tuple(
        model_id
        for model_id in allocated_model_ids
        if model_id in target_model_ids and _model_is_alive(state=state, model_instance_id=model_id)
    )


def _advance_after_current_pool(*, attack_sequence: AttackSequence) -> AttackSequence:
    if attack_sequence.is_complete:
        raise GameLifecycleError("Completed AttackSequence cannot advance pool.")
    used_pool_indices = attack_sequence.used_pool_indices
    selected_target_unit_instance_id = attack_sequence.selected_target_unit_instance_id
    current_group = attack_sequence.current_gathered_group
    if current_group is not None:
        used_pool_indices = tuple(sorted({*used_pool_indices, *current_group.pool_indices}))
        if any(
            pool_index not in used_pool_indices
            and pool.target_unit_instance_id == current_group.target_unit_instance_id
            for pool_index, pool in enumerate(attack_sequence.attack_pools)
        ):
            selected_target_unit_instance_id = current_group.target_unit_instance_id
        else:
            selected_target_unit_instance_id = None
    if selected_target_unit_instance_id is None:
        next_pool_index = _first_unresolved_pool_index_from(
            attack_pools=attack_sequence.attack_pools,
            used_pool_indices=used_pool_indices,
        )
    else:
        next_pool_index = _first_unresolved_pool_index_for_target_from(
            attack_pools=attack_sequence.attack_pools,
            used_pool_indices=used_pool_indices,
            target_unit_instance_id=selected_target_unit_instance_id,
        )
    return AttackSequence(
        sequence_id=attack_sequence.sequence_id,
        source_phase=attack_sequence.source_phase,
        attacker_player_id=attack_sequence.attacker_player_id,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=used_pool_indices,
        selected_target_unit_instance_id=selected_target_unit_instance_id,
        pool_index=next_pool_index,
        attack_index=0,
        deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
    )


def _attack_sequence_for_context(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> AttackSequence:
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError("Grouped attack context sequence drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError("Grouped attack context pool drift.")
    return AttackSequence(
        sequence_id=attack_sequence.sequence_id,
        source_phase=attack_sequence.source_phase,
        attacker_player_id=attack_sequence.attacker_player_id,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
        selected_target_unit_instance_id=attack_sequence.selected_target_unit_instance_id,
        current_gathered_group=attack_sequence.current_gathered_group,
        pool_index=attack_context["pool_index"],
        attack_index=attack_context["attack_index"],
        generated_hit_index=attack_context["generated_hit_index"],
        current_hit_roll=(
            None
            if attack_context["generated_hit_index"] == 0
            else HitRoll.from_payload(attack_context["hit_roll"])
        ),
        deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
    )


def _grouped_attack_context_payload(
    *,
    attack_sequence: AttackSequence,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    pool: RangedAttackPool,
    defender_player_id: str,
) -> AttackResolutionContextPayload:
    if not attack_contexts:
        raise GameLifecycleError("Grouped attack context requires wound contexts.")
    first_context = attack_contexts[0]
    return {
        **first_context,
        "attack_context_id": (
            f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:grouped"
        ),
        "attack_index": 0,
        "generated_hit_index": 0,
        "defender_player_id": _validate_identifier("defender_player_id", defender_player_id),
        "target_unit_instance_id": pool.target_unit_instance_id,
        "allocation": None,
        "save_options": [],
    }


def _emit_grouped_allocation_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
) -> None:
    ordered_groups = _validate_ordered_allocation_group_tuple(
        "Grouped allocation event allocation_groups",
        allocation_groups,
    )
    first_group = _first_allocation_group(
        "Grouped allocation event allocation_groups", ordered_groups
    )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.ALLOCATE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=(
                f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:grouped"
            ),
            pool_index=attack_sequence.pool_index,
            attack_index=0,
            payload=validate_json_value(
                {
                    "allocation_group": first_group.to_payload(),
                    "allocation_order_group_ids": [group.group_id for group in ordered_groups],
                    "allocation_groups": [group.to_payload() for group in ordered_groups],
                    "allocation_context": allocation_context.to_payload(),
                    "attack_context_ids": [
                        context["attack_context_id"] for context in attack_contexts
                    ],
                    "forced": True,
                    "grouped_save_before_allocation": True,
                }
            ),
        ),
    )


def _roll_grouped_saves(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    allocation_group: AllocationGroup,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[tuple[SaveDieEntryPayload, ...], LifecycleStatus | None]:
    results: list[SaveDieEntryPayload] = []
    for wounded_sequence, attack_context in wounded_contexts:
        current_model_id = _current_model_id_for_allocation_group(
            state=state,
            allocation_group=allocation_group,
        )
        save_options = _save_options_for_allocation(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=wounded_sequence,
            attack_context=attack_context,
            allocated_model_id=current_model_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        save_roll_option = mandatory_save_option(save_options)
        if save_roll_option is None:
            roll_state = _roll_or_reuse_state(
                manager,
                _no_save_damage_order_roll_spec(
                    player_id=attack_context["defender_player_id"],
                    allocated_model_id=current_model_id,
                    attack_context_id=attack_context["attack_context_id"],
                ),
            )
        else:
            roll_state = _roll_or_reuse_state(
                manager,
                saving_throw_roll_spec(
                    save_kind=save_roll_option.save_kind,
                    player_id=attack_context["defender_player_id"],
                    allocated_model_id=current_model_id,
                    attack_context_id=attack_context["attack_context_id"],
                ),
            )
            status = _request_command_reroll_for_attack_roll_if_available(
                state=state,
                decisions=decisions,
                roll_state=roll_state,
                affected_unit_instance_id=attack_context["target_unit_instance_id"],
                source_phase=battle_phase_kind_from_token(attack_context["source_phase"]),
                stratagem_index=stratagem_index,
                phase_body_status="attack_save_command_reroll_pending",
            )
            if status is not None:
                return (), status
        results.append(
            {
                "roll_state": roll_state.to_payload(),
                "value": roll_state.current_total,
                "attack_context": attack_context,
            }
        )
    return tuple(
        sorted(
            results,
            key=lambda entry: (
                entry["value"],
                entry["attack_context"]["attack_index"],
                entry["attack_context"]["attack_context_id"],
            ),
        )
    ), None


def _emit_grouped_save_die_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    roll_state: DiceRollState,
    saving_throw: SavingThrow | None,
    save_options: tuple[SaveOption, ...],
    allocation_group: AllocationGroup,
    allocated_model_id: str,
) -> None:
    save_option_payloads = [option.to_payload() for option in save_options]
    if saving_throw is None:
        payload = validate_json_value(
            {
                "save_kind": None,
                "target_number": None,
                "roll_state": roll_state.to_payload(),
                "unmodified_roll": roll_state.current_total,
                "final_roll": roll_state.current_total,
                "successful": False,
                "option": None,
                "save_options": save_option_payloads,
                "weapon_profile_id": attack_context["weapon_profile_id"],
                "allocation_group_id": allocation_group.group_id,
                "allocated_model_id": allocated_model_id,
            }
        )
    else:
        payload = validate_json_value(
            {
                **saving_throw.to_payload(),
                "save_options": save_option_payloads,
                "weapon_profile_id": attack_context["weapon_profile_id"],
                "allocation_group_id": allocation_group.group_id,
                "allocated_model_id": allocated_model_id,
            }
        )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.SAVE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context["attack_context_id"],
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=payload,
        ),
    )


def _no_save_damage_order_roll_spec(
    *,
    player_id: str,
    allocated_model_id: str,
    attack_context_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"No-save damage order die for {allocated_model_id} from {attack_context_id}",
        roll_type="attack_sequence.allocation_order.no_save",
        actor_id=player_id,
    )


def _save_options_for_allocation(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    allocated_model_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[SaveOption, ...]:
    pool = attack_sequence.current_pool()
    cover_result = _cover_for_allocated_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pool=pool,
        allocated_model_id=allocated_model_id,
    )
    if has_weapon_keyword(
        pool.weapon_profile,
        WeaponKeyword.IGNORES_COVER,
    ) or _target_has_effect_cover_denial(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
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
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=attack_context["target_unit_instance_id"],
            ).keywords,
        )
        is DevastatingWoundsResolution.NO_SAVES
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    save_options = runtime_modifiers.modified_save_options(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
            save_options=save_options_for_model(
                model=model_by_id(state=state, model_instance_id=allocated_model_id),
                armor_penetration=pool.weapon_profile.armor_penetration.final,
                cover_result=cover_result,
                no_saves_allowed=no_saves_allowed,
            ),
        )
    )
    return _save_options_with_effect_invulnerable(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        armor_penetration=pool.weapon_profile.armor_penetration.final,
        save_options=save_options,
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
    sources = _feel_no_pain_sources_for_attack(
        state=state,
        model_instance_id=model_instance_id,
        attack_context=attack_context,
    )
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
            manager=manager,
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
            manager=manager,
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
                "phase": attack_sequence.source_phase.value,
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
    manager: DiceRollManager,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    damage: DamageApplication | None = None
    if resolution.remaining_wounds > 0:
        damage = apply_damage_to_model(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage=resolution.remaining_wounds,
            damage_kind=damage_kind,
            remove_destroyed_model=False,
        )
    destroyed_model_controller_player_id = attack_context["defender_player_id"]
    attack_sequence, destroyed_transport_status = _begin_destroyed_transport_disembark_if_needed(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        sources=tuple(
            source
            for source in _state_destruction_reaction_sources(
                state=state,
                model_instance_id=model_instance_id,
            )
            if not source.optional
        ),
    )
    if destroyed_transport_status is not None:
        return attack_sequence, allocated_model_ids, destroyed_transport_status
    mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
    )
    if mandatory_status is not None:
        return attack_sequence, allocated_model_ids, mandatory_status
    if damage is not None and damage.destroyed:
        destroyed_model_placement = _destroyed_model_placement_payload(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
        remove_destroyed_model_from_battlefield(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
    else:
        destroyed_model_placement = None
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
        destroyed_model_placement=destroyed_model_placement,
    )
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        destroyed_emission=destroyed_emission,
    )
    if reaction_status is not None:
        return attack_sequence, allocated_model_ids, reaction_status
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
    if attack_sequence.current_gathered_group is not None:
        return attack_sequence
    return attack_sequence.advanced_after_generated_hit(hit_roll)


def _destruction_reaction_status_if_needed(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    destroyed_emission: DestroyedModelEmission | None,
    destroyed_model_controller_player_id: str | None = None,
    continuation: JsonValue = None,
) -> LifecycleStatus | None:
    if damage is None or not damage.destroyed:
        return None
    if destroyed_emission is None:
        raise GameLifecycleError("Destroyed damage requires a destroyed model event.")
    sources = _state_destruction_reaction_sources(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    if not sources:
        return None
    controller_player_id = (
        attack_context["defender_player_id"]
        if destroyed_model_controller_player_id is None
        else _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        )
    )
    destruction_context = validate_json_value(
        _destruction_reaction_context_payload(
            attack_context=attack_context,
            damage=damage,
            destroyed_emission=destroyed_emission,
            destroyed_model_controller_player_id=controller_player_id,
            continuation=continuation,
        )
    )
    optional_sources = _optional_destruction_reaction_sources_after_trigger_rolls(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        destroyed_emission=destroyed_emission,
        sources=tuple(source for source in sources if source.optional),
        destroyed_model_controller_player_id=controller_player_id,
    )
    if not optional_sources:
        return None
    request = build_destruction_reaction_request(
        request_id=state.next_decision_request_id(),
        defender_player_id=controller_player_id,
        destruction_context=destruction_context,
        sources=optional_sources,
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "destruction_reaction_window_opened",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_sequence.attack_context_id(),
            "model_instance_id": damage.model_instance_id,
            "target_unit_instance_id": damage.target_unit_instance_id,
            "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
            "sources": [source.to_payload() for source in optional_sources],
            "request_id": request.request_id,
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": attack_sequence.source_phase.value,
            "decision_type": SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
            "attack_context_id": attack_sequence.attack_context_id(),
            "model_instance_id": damage.model_instance_id,
        },
    )


def _optional_destruction_reaction_sources_after_trigger_rolls(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    destroyed_emission: DestroyedModelEmission,
    sources: tuple[DestructionReactionSource, ...],
    destroyed_model_controller_player_id: str,
) -> tuple[DestructionReactionSource, ...]:
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("Destruction reaction trigger rolls require DiceRollManager.")
    active_sources: list[DestructionReactionSource] = []
    for source in sources:
        descriptor = _optional_destruction_reaction_trigger_descriptor(source)
        if descriptor is None:
            active_sources.append(source)
            continue
        if not _optional_destruction_reaction_trigger_conditions_met(
            state=state,
            attack_sequence=attack_sequence,
            damage=damage,
            descriptor=descriptor,
        ):
            decisions.event_log.append(
                "destruction_reaction_trigger_not_applicable",
                {
                    "sequence_id": attack_sequence.sequence_id,
                    "attack_context_id": attack_sequence.attack_context_id(),
                    "model_instance_id": damage.model_instance_id,
                    "target_unit_instance_id": damage.target_unit_instance_id,
                    "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
                    "selected_source": source.to_payload(),
                    "descriptor": descriptor,
                },
            )
            continue
        threshold = _destruction_reaction_trigger_threshold(descriptor)
        roll_state = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Destruction reaction trigger",
                roll_type=_optional_destruction_reaction_trigger_roll_type(descriptor),
                actor_id=destroyed_model_controller_player_id,
            )
        )
        triggered = roll_state.current_total >= threshold
        decisions.event_log.append(
            "destruction_reaction_trigger_rolled",
            {
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "model_instance_id": damage.model_instance_id,
                "target_unit_instance_id": damage.target_unit_instance_id,
                "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
                "selected_source": source.to_payload(),
                "descriptor": descriptor,
                "trigger_roll": roll_state.to_payload(),
                "trigger_roll_threshold": threshold,
                "triggered": triggered,
                "attacker_player_id": attack_context["attacker_player_id"],
                "defender_player_id": attack_context["defender_player_id"],
            },
        )
        if triggered:
            active_sources.append(source)
    return tuple(active_sources)


def _optional_destruction_reaction_trigger_descriptor(
    source: DestructionReactionSource,
) -> dict[str, JsonValue] | None:
    if type(source) is not DestructionReactionSource:
        raise GameLifecycleError("Destruction reaction trigger source drift.")
    if not source.optional:
        raise GameLifecycleError("Optional destruction reaction trigger received mandatory source.")
    if source.payload is None:
        return None
    payload = _payload_object(source.payload)
    if "trigger_roll_threshold" not in payload:
        return None
    return payload


def _optional_destruction_reaction_trigger_conditions_met(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
    descriptor: dict[str, JsonValue],
) -> bool:
    if not _optional_destruction_reaction_trigger_battle_round_is_current(
        state=state,
        descriptor=descriptor,
    ):
        return False
    if not _optional_destruction_reaction_active_effect_requirement_is_met(
        state=state,
        descriptor=descriptor,
    ):
        return False
    if (
        descriptor.get("requires_destroyed_by_melee_attack") is True
        and attack_sequence.source_phase is not BattlePhase.FIGHT
    ):
        return False
    if descriptor.get("requires_not_fought_this_phase") is True:
        fight_state = state.fight_phase_state
        if (
            fight_state is not None
            and damage.target_unit_instance_id
            in fight_state.fight_order_state.selected_to_fight_unit_ids
        ):
            return False
    return True


def _optional_destruction_reaction_trigger_battle_round_is_current(
    *,
    state: GameState,
    descriptor: dict[str, JsonValue],
) -> bool:
    if "battle_round" not in descriptor:
        return True
    return _payload_positive_int(descriptor, key="battle_round") == state.battle_round


def _optional_destruction_reaction_active_effect_requirement_is_met(
    *,
    state: GameState,
    descriptor: dict[str, JsonValue],
) -> bool:
    raw_requirement = descriptor.get("requires_active_persisting_effect")
    if raw_requirement is None:
        return True
    requirement = _payload_object(raw_requirement)
    required_owner_id = _optional_payload_string(requirement, key="owner_player_id")
    required_source_rule_id = _optional_payload_string(requirement, key="source_rule_id")
    required_effect_kind = _optional_payload_string(requirement, key="effect_kind")
    required_target_unit_id = _optional_payload_string(requirement, key="target_unit_instance_id")
    required_battle_round = (
        _payload_positive_int(requirement, key="battle_round")
        if "battle_round" in requirement
        else None
    )
    required_selected_id = _optional_payload_string(requirement, key="selected_blessing_id")
    for effect in state.persisting_effects:
        if required_owner_id is not None and effect.owner_player_id != required_owner_id:
            continue
        if required_source_rule_id is not None and effect.source_rule_id != required_source_rule_id:
            continue
        if required_target_unit_id is not None and not effect.applies_to_unit(
            required_target_unit_id
        ):
            continue
        payload = _payload_object(effect.effect_payload)
        if required_effect_kind is not None and payload.get("effect_kind") != required_effect_kind:
            continue
        if required_battle_round is not None and payload.get("battle_round") != (
            required_battle_round
        ):
            continue
        if required_selected_id is not None and required_selected_id not in _payload_string_list(
            payload,
            key="selected_blessing_ids",
        ):
            continue
        return True
    return False


def _destruction_reaction_trigger_threshold(descriptor: dict[str, JsonValue]) -> int:
    threshold = _payload_positive_int(descriptor, key="trigger_roll_threshold")
    if threshold > 6:
        raise GameLifecycleError("Destruction reaction trigger threshold must be on a D6.")
    return threshold


def _optional_destruction_reaction_trigger_roll_type(
    descriptor: dict[str, JsonValue],
) -> str:
    raw_roll_type = descriptor.get("trigger_roll_type")
    if raw_roll_type is None:
        return "destruction_reaction_trigger"
    if type(raw_roll_type) is not str or not raw_roll_type.strip():
        raise GameLifecycleError("Destruction reaction trigger_roll_type must be a string.")
    return raw_roll_type


def _resolve_mandatory_destruction_reactions_before_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str | None = None,
    sources: tuple[DestructionReactionSource, ...] | None = None,
) -> LifecycleStatus | None:
    if damage is None or not damage.destroyed:
        return None
    controller_player_id = (
        attack_context["defender_player_id"]
        if destroyed_model_controller_player_id is None
        else _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        )
    )
    active_sources = (
        _state_destruction_reaction_sources(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
        if sources is None
        else sources
    )
    mandatory_sources = tuple(source for source in active_sources if not source.optional)
    for source_index, source in enumerate(mandatory_sources):
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
            status = _resolve_deadly_demise_before_removal(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=attack_sequence,
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                destroyed_model_controller_player_id=controller_player_id,
                pending_sources=mandatory_sources[source_index + 1 :],
            )
            if status is not None:
                return status
            continue
        _emit_mandatory_destruction_reaction_record(
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            destroyed_model_controller_player_id=controller_player_id,
            execution_status="recorded_for_action_host",
        )
    return None


def _emit_mandatory_destruction_reaction_record(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    destroyed_model_controller_player_id: str,
    execution_status: str,
    extra_payload: dict[str, JsonValue] | None = None,
) -> None:
    if source.optional:
        raise GameLifecycleError("Mandatory destruction reaction source was optional.")
    payload = {
        "resolution_kind": "mandatory",
        "decision": None,
        "selected_source": source.to_payload(),
        "selected_reaction_kind": source.reaction_kind.value,
        "action_host": _destruction_reaction_action_host(source),
        "execution_status": execution_status,
        "destruction_context": validate_json_value(
            _pre_removal_destruction_reaction_context_payload(
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            )
        ),
        "sequence_id": attack_sequence.sequence_id,
        "attack_context_id": attack_sequence.attack_context_id(),
        "model_instance_id": damage.model_instance_id,
        "target_unit_instance_id": damage.target_unit_instance_id,
        "model_destroyed_event_id": None,
    }
    if extra_payload is not None:
        payload.update(extra_payload)
    decisions.event_log.append("destruction_reaction_resolved", validate_json_value(payload))


def _resolve_deadly_demise_before_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    destroyed_model_controller_player_id: str,
    pending_sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    descriptor = _deadly_demise_descriptor(source)
    trigger_roll_threshold = _payload_positive_int(descriptor, key="trigger_roll_threshold")
    range_inches = _payload_positive_number(descriptor, key="range_inches")
    trigger_roll = manager.roll(
        deadly_demise_trigger_roll_spec(
            source=source,
            player_id=destroyed_model_controller_player_id,
            model_instance_id=damage.model_instance_id,
        )
    )
    trigger_roll_payload = validate_json_value(trigger_roll.to_payload())
    triggered = trigger_roll.current_total >= trigger_roll_threshold
    if not triggered:
        _emit_mandatory_destruction_reaction_record(
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            execution_status="resolved_no_effect",
            extra_payload={
                "deadly_demise": {
                    "descriptor": validate_json_value(descriptor),
                    "trigger_roll": trigger_roll_payload,
                    "triggered": False,
                    "affected_target_unit_ids": [],
                },
            },
        )
        return None
    target_unit_ids = _deadly_demise_target_unit_ids(
        state=state,
        source_model_instance_id=damage.model_instance_id,
        range_inches=range_inches,
    )
    status = _route_deadly_demise_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        target_unit_ids=target_unit_ids,
        pending_sources=pending_sources,
    )
    if status is not None:
        return status
    _emit_mandatory_destruction_reaction_record(
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        source=source,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        execution_status="resolved",
        extra_payload={
            "deadly_demise": {
                "descriptor": validate_json_value(descriptor),
                "trigger_roll": trigger_roll_payload,
                "triggered": True,
                "affected_target_unit_ids": list(target_unit_ids),
            },
        },
    )
    return None


def _route_deadly_demise_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    for target_index, target_unit_id in enumerate(target_unit_ids):
        mortal_wounds, wound_roll_payload = _deadly_demise_mortal_wounds_for_target(
            manager=manager,
            source=source,
            descriptor=descriptor,
            player_id=destroyed_model_controller_player_id,
            target_unit_instance_id=target_unit_id,
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{attack_sequence.sequence_id}:deadly-demise:{source.source_id}:"
                f"{target_unit_id}:mortal-wounds"
            ),
            source_rule_id=source.source_rule_id,
            source_context=_deadly_demise_source_context_payload(
                attack_sequence=attack_sequence,
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                descriptor=descriptor,
                destroyed_model_controller_player_id=destroyed_model_controller_player_id,
                trigger_roll_payload=trigger_roll_payload,
                affected_target_unit_ids=target_unit_ids,
                pending_target_unit_ids=target_unit_ids[target_index + 1 :],
                pending_sources=pending_sources,
                wound_roll_payload=wound_roll_payload,
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
            remove_destroyed_models=False,
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": source.source_rule_id,
                    "source_kind": DEADLY_DEMISE_SOURCE_KIND,
                },
            )
        if routed.application is None:
            raise GameLifecycleError("Deadly Demise mortal wounds did not produce application.")
        _emit_deadly_demise_mortal_wounds_applied(
            decisions=decisions,
            attack_sequence=attack_sequence,
            source=source,
            target_unit_id=target_unit_id,
            mortal_wounds=mortal_wounds,
            application=routed.application,
            wound_roll_payload=wound_roll_payload,
        )
        status = _resolve_deadly_demise_secondary_destroyed_models(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            source_damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            descriptor=descriptor,
            destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            trigger_roll_payload=trigger_roll_payload,
            affected_target_unit_ids=target_unit_ids,
            pending_target_unit_ids=target_unit_ids[target_index + 1 :],
            pending_sources=pending_sources,
            secondary_damage_applications=_destroyed_damage_applications(
                routed.application.applications
            ),
        )
        if status is not None:
            return status
    return None


def _resolve_deadly_demise_secondary_destroyed_models(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    secondary_damage_applications: tuple[DamageApplication, ...],
) -> LifecycleStatus | None:
    for damage_index, secondary_damage in enumerate(secondary_damage_applications):
        secondary_controller_player_id = unit_owner_player_id(
            state=state,
            unit_instance_id=secondary_damage.target_unit_instance_id,
        )
        secondary_feel_no_pain = FeelNoPainResolution.declined(
            requested_wounds=secondary_damage.requested_damage
        )
        mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=secondary_damage,
            saving_throw_payload=None,
            feel_no_pain=secondary_feel_no_pain,
            destroyed_model_controller_player_id=secondary_controller_player_id,
        )
        if mandatory_status is not None:
            return mandatory_status
        destroyed_model_placement = _destroyed_model_placement_payload(
            state=state,
            model_instance_id=secondary_damage.model_instance_id,
        )
        remove_destroyed_model_from_battlefield(
            state=state,
            model_instance_id=secondary_damage.model_instance_id,
        )
        destroyed_emission = _emit_damage_event(
            state=state,
            decisions=decisions,
            hooks=AttackSequenceHooks.empty(),
            attack_sequence=attack_sequence,
            damage=secondary_damage,
            saving_throw=None,
            saving_throw_payload=None,
            feel_no_pain=secondary_feel_no_pain,
            destroyed_model_placement=destroyed_model_placement,
        )
        reaction_status = _destruction_reaction_status_if_needed(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=secondary_damage,
            destroyed_emission=destroyed_emission,
            destroyed_model_controller_player_id=secondary_controller_player_id,
            continuation=_deadly_demise_secondary_continuation_payload(
                attack_context=attack_context,
                source_damage=source_damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                descriptor=descriptor,
                destroyed_model_controller_player_id=destroyed_model_controller_player_id,
                trigger_roll_payload=trigger_roll_payload,
                affected_target_unit_ids=affected_target_unit_ids,
                pending_target_unit_ids=pending_target_unit_ids,
                pending_sources=pending_sources,
                pending_secondary_damage_applications=secondary_damage_applications[
                    damage_index + 1 :
                ],
            ),
        )
        if reaction_status is not None:
            return reaction_status
    return None


def _continue_deadly_demise_after_secondary_destruction_reaction(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    continuation: JsonValue,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    source_context = _payload_object(continuation)
    attack_context = _deadly_demise_attack_context_from_source_context(source_context)
    damage = DamageApplication.from_payload(
        cast(DamageApplicationPayload, source_context["damage_application"])
    )
    feel_no_pain = FeelNoPainResolution.from_payload(
        cast(FeelNoPainResolutionPayload, source_context["feel_no_pain"])
    )
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, source_context["source"])
    )
    descriptor = _payload_object(source_context["descriptor"])
    destroyed_model_controller_player_id = _payload_string(
        source_context,
        key="destroyed_model_controller_player_id",
    )
    trigger_roll_payload = validate_json_value(source_context["trigger_roll"])
    affected_target_unit_ids = _payload_identifier_tuple(
        source_context,
        key="affected_target_unit_ids",
    )
    pending_target_unit_ids = _payload_identifier_tuple(
        source_context,
        key="pending_target_unit_ids",
    )
    pending_source_payloads = source_context.get("pending_sources")
    if not isinstance(pending_source_payloads, list):
        raise GameLifecycleError("Deadly Demise continuation pending_sources must be a list.")
    pending_sources = tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, payload))
        for payload in pending_source_payloads
    )
    pending_secondary_payloads = source_context.get("pending_secondary_damage_applications")
    if not isinstance(pending_secondary_payloads, list):
        raise GameLifecycleError(
            "Deadly Demise continuation pending secondary damage must be a list."
        )
    pending_secondary_damage = tuple(
        DamageApplication.from_payload(cast(DamageApplicationPayload, payload))
        for payload in pending_secondary_payloads
    )
    status = _resolve_deadly_demise_secondary_destroyed_models(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        source_damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        affected_target_unit_ids=affected_target_unit_ids,
        pending_target_unit_ids=pending_target_unit_ids,
        pending_sources=pending_sources,
        secondary_damage_applications=pending_secondary_damage,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    status = _route_deadly_demise_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        target_unit_ids=pending_target_unit_ids,
        pending_sources=pending_sources,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    _emit_mandatory_destruction_reaction_record(
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        execution_status="resolved",
        extra_payload={
            "deadly_demise": {
                "descriptor": validate_json_value(descriptor),
                "trigger_roll": trigger_roll_payload,
                "triggered": True,
                "affected_target_unit_ids": list(affected_target_unit_ids),
            },
        },
    )
    status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        sources=pending_sources,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    destroyed_model_placement = _destroyed_model_placement_payload(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    remove_destroyed_model_from_battlefield(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        destroyed_model_placement=destroyed_model_placement,
    )
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        destroyed_emission=destroyed_emission,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
    )
    if reaction_status is not None:
        return attack_sequence, already_allocated_model_ids, reaction_status
    return (
        _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        ),
        already_allocated_model_ids,
        None,
    )


def _deadly_demise_secondary_continuation_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    pending_secondary_damage_applications: tuple[DamageApplication, ...],
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": DEADLY_DEMISE_SOURCE_KIND,
            "continuation_kind": "secondary_destroyed_model_reaction",
            "attack_context": attack_context,
            "damage_application": source_damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "source": source.to_payload(),
            "descriptor": validate_json_value(descriptor),
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "trigger_roll": validate_json_value(trigger_roll_payload),
            "affected_target_unit_ids": list(affected_target_unit_ids),
            "pending_target_unit_ids": list(pending_target_unit_ids),
            "pending_sources": [pending_source.to_payload() for pending_source in pending_sources],
            "pending_secondary_damage_applications": [
                application.to_payload() for application in pending_secondary_damage_applications
            ],
        }
    )


def _is_deadly_demise_continuation(payload: JsonValue) -> bool:
    if payload is None:
        return False
    if not isinstance(payload, dict):
        raise GameLifecycleError("Destruction reaction continuation must be an object.")
    return (
        payload.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND
        and payload.get("continuation_kind") == "secondary_destroyed_model_reaction"
    )


def _destroyed_damage_applications(
    applications: tuple[DamageApplication, ...],
) -> tuple[DamageApplication, ...]:
    return tuple(application for application in applications if application.destroyed)


def _deadly_demise_mortal_wounds_for_target(
    *,
    manager: DiceRollManager,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    player_id: str,
    target_unit_instance_id: str,
) -> tuple[int, JsonValue]:
    wound_descriptor = _payload_object(descriptor["mortal_wounds"])
    kind = _payload_string(wound_descriptor, key="kind")
    if kind == "fixed":
        return _payload_positive_int(wound_descriptor, key="value"), None
    if kind == "d3":
        reason = (
            f"Deadly Demise mortal wounds for {source.source_id} into {target_unit_instance_id}"
        )
        result = manager.roll_d3(
            reason=reason,
            roll_type="destruction_reaction.deadly_demise.mortal_wounds",
            actor_id=player_id,
        )
        return result.value, validate_json_value(result.to_payload())
    if kind == "d6":
        roll = manager.roll(
            deadly_demise_mortal_wounds_roll_spec(
                source=source,
                player_id=player_id,
                target_unit_instance_id=target_unit_instance_id,
                sides=6,
            )
        )
        return roll.current_total, validate_json_value(roll.to_payload())
    raise GameLifecycleError("Unsupported Deadly Demise mortal-wound descriptor.")


def _emit_deadly_demise_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    source: DestructionReactionSource,
    target_unit_id: str,
    mortal_wounds: int,
    application: MortalWoundApplication,
    wound_roll_payload: JsonValue,
) -> None:
    decisions.event_log.append(
        "deadly_demise_mortal_wounds_applied",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_sequence.attack_context_id(),
            "source": source.to_payload(),
            "source_rule_id": source.source_rule_id,
            "target_unit_instance_id": target_unit_id,
            "mortal_wounds": mortal_wounds,
            "mortal_wound_roll": wound_roll_payload,
            "mortal_wound_application": application.to_payload(),
        },
    )


def _deadly_demise_target_unit_ids(
    *,
    state: GameState,
    source_model_instance_id: str,
    range_inches: float,
) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deadly Demise requires battlefield_state.")
    source_model_id = _validate_identifier("source_model_instance_id", source_model_instance_id)
    try:
        source_placement = battlefield.model_placement_by_id(source_model_id)
    except PlacementError as exc:
        raise GameLifecycleError("Deadly Demise source model must remain placed.") from exc
    source_model = geometry_model_for_placement(
        model=model_by_id(state=state, model_instance_id=source_model_id),
        placement=source_placement,
    )
    placed_model_ids = set(battlefield.placed_model_ids())
    target_unit_ids: list[str] = []
    for army in state.army_definitions:
        for unit in army.units:
            if _unit_has_model_within_deadly_demise_range(
                state=state,
                unit=unit,
                source_model_id=source_model_id,
                source_model=source_model,
                placed_model_ids=placed_model_ids,
                range_inches=range_inches,
            ):
                target_unit_ids.append(unit.unit_instance_id)
    return tuple(sorted(target_unit_ids))


def _unit_has_model_within_deadly_demise_range(
    *,
    state: GameState,
    unit: UnitInstance,
    source_model_id: str,
    source_model: GeometryModel,
    placed_model_ids: set[str],
    range_inches: float,
) -> bool:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deadly Demise requires battlefield_state.")
    for model in unit.own_models:
        if model.model_instance_id == source_model_id:
            continue
        if not model.is_alive or model.model_instance_id not in placed_model_ids:
            continue
        try:
            placement = battlefield.model_placement_by_id(model.model_instance_id)
        except PlacementError as exc:
            raise GameLifecycleError("Deadly Demise target model placement drift.") from exc
        target_model = geometry_model_for_placement(model=model, placement=placement)
        distance = DistanceMeasurementContext.from_models(source_model, target_model)
        if distance.closest_distance_inches() <= range_inches:
            return True
    return False


def _deadly_demise_descriptor(source: DestructionReactionSource) -> dict[str, JsonValue]:
    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE:
        raise GameLifecycleError("Deadly Demise descriptor requires a Deadly Demise source.")
    payload = _payload_object(source.payload)
    range_inches = _payload_positive_number(payload, key="range_inches")
    mortal_wounds = _payload_object(payload["mortal_wounds"])
    kind = _payload_string(mortal_wounds, key="kind")
    if kind == "fixed":
        _payload_positive_int(mortal_wounds, key="value")
    elif kind not in {"d3", "d6"}:
        raise GameLifecycleError("Unsupported Deadly Demise mortal-wound descriptor.")
    return {
        "trigger_roll_threshold": _validate_d6_target(
            "Deadly Demise trigger_roll_threshold",
            payload["trigger_roll_threshold"],
        ),
        "range_inches": range_inches,
        "mortal_wounds": validate_json_value(mortal_wounds),
    }


def _deadly_demise_source_context_payload(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    wound_roll_payload: JsonValue,
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": DEADLY_DEMISE_SOURCE_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attack_context": attack_context,
            "damage_application": damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "source": source.to_payload(),
            "descriptor": validate_json_value(descriptor),
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "trigger_roll": validate_json_value(trigger_roll_payload),
            "affected_target_unit_ids": list(affected_target_unit_ids),
            "pending_target_unit_ids": list(pending_target_unit_ids),
            "pending_sources": [pending_source.to_payload() for pending_source in pending_sources],
            "mortal_wound_roll": validate_json_value(wound_roll_payload),
        }
    )


def _deadly_demise_attack_context_from_source_context(
    source_context: dict[str, JsonValue],
) -> AttackResolutionContextPayload:
    raw_attack_context = source_context["attack_context"]
    if not isinstance(raw_attack_context, dict):
        raise GameLifecycleError("Deadly Demise source context attack_context must be an object.")
    return cast(AttackResolutionContextPayload, raw_attack_context)


def _pre_removal_destruction_reaction_context_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "context_kind": "attack_sequence_model_destroyed_pre_removal",
            "attack_context": attack_context,
            "damage_application": damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "target_unit_instance_id": damage.target_unit_instance_id,
            "model_instance_id": damage.model_instance_id,
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "source_phase": attack_context["source_phase"],
            "source_step": AttackSequenceStep.DAMAGE.value,
            "destroyed_model_rules_triggered": True,
        }
    )


def _destruction_reaction_context_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    destroyed_emission: DestroyedModelEmission,
    destroyed_model_controller_player_id: str,
    continuation: JsonValue,
) -> DestructionReactionContextPayload:
    if type(damage) is not DamageApplication:
        raise GameLifecycleError("Destruction reaction context requires damage.")
    if not damage.destroyed:
        raise GameLifecycleError("Destruction reaction context requires destroyed damage.")
    return {
        "context_kind": "attack_sequence_model_destroyed",
        "attack_context": attack_context,
        "damage_application": validate_json_value(damage.to_payload()),
        "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
        "damage_event_id": destroyed_emission.damage_event_id,
        "target_unit_instance_id": damage.target_unit_instance_id,
        "model_instance_id": damage.model_instance_id,
        "destroyed_model_controller_player_id": _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        ),
        "source_phase": attack_context["source_phase"],
        "source_step": AttackSequenceStep.DAMAGE.value,
        "removal_record": validate_json_value(destroyed_emission.removal_record.to_payload()),
        "transition_batch": validate_json_value(destroyed_emission.transition_batch.to_payload()),
        "destroyed_model_rules_triggered": True,
        "continuation": validate_json_value(continuation),
    }


def _roll_hit_and_wound(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[AttackResolutionContextPayload | None, LifecycleStatus | None]:
    pool = attack_sequence.current_pool()
    attack_context_id = attack_sequence.attack_context_id()
    is_psychic_attack = is_psychic_weapon_profile(pool.weapon_profile)
    if attack_sequence.generated_hit_index == 0:
        psychic_modifier_selection = _psychic_attack_modifier_ignore_selection_for_attack(
            decisions=decisions,
            attack_context_id=attack_context_id,
        )
        if psychic_modifier_selection is None:
            request = _psychic_attack_modifier_ignore_request(
                state=state,
                pool=pool,
                attacker_player_id=attack_sequence.attacker_player_id,
                attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
                attack_context_id=attack_context_id,
                source_phase=attack_sequence.source_phase,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            if request is not None:
                decisions.request_decision(request)
                return (
                    None,
                    LifecycleStatus.waiting_for_decision(
                        stage=GameLifecycleStage.BATTLE,
                        decision_request=request,
                        payload={
                            "phase": attack_sequence.source_phase.value,
                            "phase_body_status": "psychic_attack_modifier_ignore_pending",
                            "attack_context_id": attack_context_id,
                            "weapon_profile_id": pool.weapon_profile_id,
                        },
                    ),
                )
        hit_roll = _roll_hit(
            state=state,
            manager=manager,
            pool=pool,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
            source_phase=attack_sequence.source_phase,
            runtime_modifier_registry=runtime_modifier_registry,
            psychic_modifier_selection=psychic_modifier_selection,
        )
        status = _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=hit_roll.roll_state,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            attack_context_id=attack_context_id,
            source_phase=attack_sequence.source_phase,
            weapon_profile_id=pool.weapon_profile_id,
        )
        if status is not None:
            return None, status
        status = _request_command_reroll_for_attack_roll_if_available(
            state=state,
            decisions=decisions,
            roll_state=hit_roll.roll_state,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
            phase_body_status="attack_hit_command_reroll_pending",
        )
        if status is not None:
            return None, status
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.HIT,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=attack_context_id,
                pool_index=attack_sequence.pool_index,
                attack_index=attack_sequence.attack_index,
                payload=validate_json_value(
                    {
                        **hit_roll.to_payload(),
                        "weapon_profile_id": pool.weapon_profile_id,
                        "is_psychic_attack": is_psychic_attack,
                        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                    }
                ),
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
                    payload=validate_json_value(
                        {
                            **hit_roll.to_payload(),
                            "weapon_profile_id": pool.weapon_profile_id,
                            "is_psychic_attack": is_psychic_attack,
                            "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                        }
                    ),
                ),
            )
    else:
        if attack_sequence.current_hit_roll is None:
            raise GameLifecycleError("Generated hit resolution requires a hit roll.")
        hit_roll = attack_sequence.current_hit_roll
    if not hit_roll.successful:
        return None, None

    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    )
    toughness = _target_unit_toughness(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if (
        attack_sequence.generated_hit_index == 0
        and hit_roll.critical
        and lethal_hits_applies(pool.weapon_profile, target_keywords=target_rules_unit.keywords)
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
            target_keywords=target_rules_unit.keywords,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
            wound_modifier=_wound_roll_modifier(
                state=state,
                pool=pool,
                source_phase=attack_sequence.source_phase,
                toughness=toughness,
                runtime_modifier_registry=runtime_modifier_registry,
            ),
        )
        status = _request_source_backed_wound_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=wound_roll.roll_state,
            pool=pool,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            attacker_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=attack_sequence.attacking_unit_instance_id,
            ).keywords,
            attack_context_id=attack_context_id,
            source_phase=attack_sequence.source_phase,
        )
        if status is not None:
            return None, status
        status = _request_command_reroll_for_attack_roll_if_available(
            state=state,
            decisions=decisions,
            roll_state=wound_roll.roll_state,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
            phase_body_status="attack_wound_command_reroll_pending",
        )
        if status is not None:
            return None, status
        wound_roll = _reroll_wound_for_twin_linked_if_needed(
            manager=manager,
            decisions=decisions,
            pool=pool,
            initial_wound_roll=wound_roll,
            toughness=toughness,
            target_keywords=target_rules_unit.keywords,
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
            payload=validate_json_value(
                {
                    **wound_roll.to_payload(),
                    "weapon_profile_id": pool.weapon_profile_id,
                    "is_psychic_attack": is_psychic_attack,
                    "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                }
            ),
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
                payload=validate_json_value(
                    {
                        **wound_roll.to_payload(),
                        "weapon_profile_id": pool.weapon_profile_id,
                        "is_psychic_attack": is_psychic_attack,
                        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                    }
                ),
            ),
        )
    return {
        "sequence_id": attack_sequence.sequence_id,
        "source_phase": attack_sequence.source_phase.value,
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
        "is_psychic_attack": is_psychic_attack,
        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
        "damage_profile": pool.weapon_profile.damage_profile.to_payload(),
        "hit_roll": hit_roll.to_payload(),
        "wound_roll": wound_roll.to_payload(),
        "allocation": None,
        "save_options": [],
    }, None


def _roll_or_reuse_state(manager: DiceRollManager, spec: DiceRollSpec) -> DiceRollState:
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("Roll reuse requires a DiceRollManager.")
    if type(spec) is not DiceRollSpec:
        raise GameLifecycleError("Roll reuse requires a DiceRollSpec.")
    spec_payload = spec.to_payload()
    original_state: DiceRollState | None = None
    for event in manager.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("dice_rolled event payload must be an object.")
        result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if result.spec.to_payload() == spec_payload:
            original_state = DiceRollState.from_result(result)
            break
    if original_state is None:
        return manager.roll(spec)
    return _latest_reroll_state_for_original_roll(
        manager=manager,
        original_state=original_state,
    )


def _latest_reroll_state_for_original_roll(
    *,
    manager: DiceRollManager,
    original_state: DiceRollState,
) -> DiceRollState:
    current = original_state
    roll_id = original_state.original_result.roll_id
    for event in manager.event_log.records:
        if event.event_type not in {"dice_reroll_resolved", "command_reroll_resolved"}:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Reroll event payload must be an object.")
        if event.event_type == "command_reroll_resolved":
            updated_payload = event.payload.get("updated_roll_state")
            if not isinstance(updated_payload, dict):
                raise GameLifecycleError("Command Re-roll event missing updated roll state.")
            updated_state = DiceRollState.from_payload(cast(DiceRollStatePayload, updated_payload))
        else:
            updated_state = DiceRollState.from_payload(cast(DiceRollStatePayload, event.payload))
        if updated_state.original_result.roll_id == roll_id:
            current = updated_state
    return current


def _request_command_reroll_for_attack_roll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    affected_unit_instance_id: str,
    source_phase: BattlePhase,
    stratagem_index: StratagemCatalogIndex | None,
    phase_body_status: str,
) -> LifecycleStatus | None:
    if roll_state is not None and roll_state.rerolls:
        return None
    if roll_state is None or stratagem_index is None:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    from warhammer40k_core.engine.stratagems import (
        COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY,
        COMMAND_REROLL_DICE_CONTEXT_KEY,
        CORE_COMMAND_REROLL_HANDLER_ID,
        DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_for_handler_from_index,
        stratagem_window_declined_for_context,
    )

    phase = battle_phase_kind_from_token(source_phase)
    window_id = (
        f"command-reroll-{phase.value}-round-{state.battle_round:02d}-"
        f"{roll_state.original_result.roll_id}"
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=actor_id,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        timing_window_id=window_id,
        trigger_payload=validate_json_value(
            {
                COMMAND_REROLL_DICE_CONTEXT_KEY: roll_state.to_payload(),
                COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY: affected_unit_instance_id,
                "source_phase": phase.value,
                "roll_id": roll_state.original_result.roll_id,
                "roll_type": roll_state.original_result.spec.roll_type,
            }
        ),
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_for_handler_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        handler_id=CORE_COMMAND_REROLL_HANDLER_ID,
    )
    if not options:
        return None
    request_id = state.next_decision_request_id()
    opportunity_window = _command_reroll_opportunity_window(
        state=state,
        decisions=decisions,
        window_id=window_id,
        roll_state=roll_state,
        actor_id=actor_id,
        affected_unit_instance_id=affected_unit_instance_id,
        phase=phase,
        use_option_ids=tuple(option.option_id for option in options),
        decline_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    )
    enriched_options = _command_reroll_opportunity_options(
        window=opportunity_window,
        player_id=actor_id,
        use_options=options,
        decline_option=stratagem_decline_option(),
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=enriched_options,
        request_id=request_id,
        payload_extra={
            "submission_family": OPPORTUNITY_REQUEST_FAMILY,
            "opportunity_window": cast(JsonValue, opportunity_window.to_payload()),
            "opportunity_window_id": opportunity_window.window_id,
            "legal_action_fingerprint": opportunity_window.legal_action_fingerprint(actor_id),
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": phase.value,
            "phase_body_status": phase_body_status,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": affected_unit_instance_id,
            "pending_request_id": request.request_id,
        },
    )


def _request_source_backed_hit_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None = None,
    target_unit_instance_id: str | None = None,
    attack_context_id: str,
    source_phase: BattlePhase,
    weapon_profile_id: str,
) -> LifecycleStatus | None:
    if roll_state is None:
        return None
    if source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return None
    if roll_state.rerolls:
        return None
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=actor_id,
        unit_instance_id=attacking_unit_instance_id,
        model_instance_id=attacker_model_instance_id,
        roll_type=roll_state.original_result.spec.roll_type,
        timing_window="attack_sequence.hit",
        attack_kind=_source_backed_attack_kind_for_phase(source_phase),
        target_unit_instance_id=target_unit_instance_id,
    )
    if permission_context is None:
        return None
    permission = _source_backed_hit_permission_for_attack(
        permission_context=permission_context,
        roll_state=roll_state,
    )
    if permission is None:
        return None
    if _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        source_id=permission.source_id,
    ):
        return None
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=actor_id,
        permission=permission,
        extra_payload={
            "source_rule_id": permission.source_id,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "unit_instance_id": attacking_unit_instance_id,
                "attack_context_id": attack_context_id,
                "weapon_profile_id": weapon_profile_id,
                "hit_roll_state": validate_json_value(roll_state.to_payload()),
                "source_payload": validate_json_value(permission_context.source_payload),
            },
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": source_phase.value,
            "phase_body_status": "attack_hit_source_backed_reroll_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": attacking_unit_instance_id,
            "attack_context_id": attack_context_id,
            "pending_request_id": request.request_id,
        },
    )


def _source_backed_hit_permission_for_attack(
    *,
    permission_context: SourceBackedRerollPermissionContext,
    roll_state: DiceRollState,
) -> RerollPermission | None:
    source_payload = permission_context.source_payload
    conditional = source_payload.get("conditional_hit_reroll")
    if conditional is None:
        return permission_context.permission
    if not isinstance(conditional, dict):
        raise GameLifecycleError("Conditional hit reroll payload must be an object.")
    reroll_values = conditional.get("reroll_unmodified_values")
    if not isinstance(reroll_values, list) or not all(
        type(value) is int for value in reroll_values
    ):
        raise GameLifecycleError("Conditional hit reroll requires integer reroll values.")
    selections = tuple(
        (index,)
        for index, value in enumerate(roll_state.current_values)
        if value in cast(list[int], reroll_values)
    )
    if not selections:
        return None
    return replace(
        permission_context.permission,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=selections,
    )


def apply_source_backed_attack_dice_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    expected_phase: BattlePhase,
    phase_label: str,
) -> None:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError(f"{phase_label} dice reroll requires an active attack sequence.")
    if attack_sequence.source_phase is not expected_phase:
        raise GameLifecycleError(f"{phase_label} dice reroll context must be for the phase.")
    if result.actor_id != attack_sequence.attacker_player_id:
        raise GameLifecycleError(f"{phase_label} dice reroll actor must match attacking player.")
    record = decisions.record_for_result(result)
    request_payload = _payload_object(record.request.payload)
    roll_type = _payload_string(request_payload, key="roll_type")
    roll_state_key = SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS.get(roll_type)
    if roll_state_key is None:
        raise GameLifecycleError(
            f"{phase_label} dice reroll must target an attack hit or wound roll."
        )
    source_rule_id = _payload_string(request_payload, key="source_rule_id")
    permission_payload = _nested_payload_object(request_payload, key="permission")
    if _payload_string(permission_payload, key="source_id") != source_rule_id:
        raise GameLifecycleError(f"{phase_label} dice reroll source context drift.")
    if _payload_string(permission_payload, key="timing_window") != roll_type:
        raise GameLifecycleError(f"{phase_label} dice reroll timing window drift.")
    if _payload_string(permission_payload, key="eligible_roll_type") != roll_type:
        raise GameLifecycleError(f"{phase_label} dice reroll permission roll type drift.")
    if (
        _payload_string(permission_payload, key="owning_player_id")
        != attack_sequence.attacker_player_id
    ):
        raise GameLifecycleError(f"{phase_label} dice reroll permission player drift.")
    attack_context = _nested_payload_object(request_payload, key="attack_context")
    if _payload_string(attack_context, key="phase") != expected_phase.value:
        raise GameLifecycleError(f"{phase_label} dice reroll context must be for the phase.")
    if (
        _payload_string(attack_context, key="unit_instance_id")
        != attack_sequence.attacking_unit_instance_id
    ):
        raise GameLifecycleError(
            f"{phase_label} dice reroll unit must match active attack sequence."
        )
    attack_context_id = _payload_string(attack_context, key="attack_context_id")
    if not _source_backed_attack_context_id_matches_active_pool(
        attack_sequence=attack_sequence,
        attack_context_id=attack_context_id,
    ):
        raise GameLifecycleError(f"{phase_label} dice reroll attack context drift.")
    current_pool = attack_sequence.current_pool()
    if _payload_string(attack_context, key="weapon_profile_id") != current_pool.weapon_profile_id:
        raise GameLifecycleError(f"{phase_label} dice reroll weapon profile drift.")
    _validate_current_source_backed_attack_reroll_context_if_required(
        state=state,
        attack_sequence=attack_sequence,
        current_pool=current_pool,
        roll_type=roll_type,
        attack_kind=_source_backed_attack_kind_for_phase(expected_phase),
        source_rule_id=source_rule_id,
        attack_context=attack_context,
        phase_label=phase_label,
    )
    initial_roll_payload = _nested_payload_object(attack_context, key=roll_state_key)
    initial_roll_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, initial_roll_payload)
    )
    if initial_roll_state.original_result.spec.roll_type != roll_type:
        raise GameLifecycleError(f"{phase_label} dice reroll initial roll type drift.")
    if initial_roll_state.original_result.spec.actor_id != attack_sequence.attacker_player_id:
        raise GameLifecycleError(f"{phase_label} dice reroll initial roll actor drift.")
    DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
    ).resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )


def _validate_current_source_backed_attack_reroll_context_if_required(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    current_pool: RangedAttackPool,
    roll_type: str,
    attack_kind: str,
    source_rule_id: str,
    attack_context: dict[str, JsonValue],
    phase_label: str,
) -> None:
    source_payload_value = attack_context.get("source_payload")
    if source_payload_value is None:
        return
    source_payload = _payload_object(source_payload_value)
    current_permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=attack_sequence.attacker_player_id,
        unit_instance_id=attack_sequence.attacking_unit_instance_id,
        model_instance_id=current_pool.attacker_model_instance_id,
        roll_type=roll_type,
        timing_window=roll_type,
        attack_kind=attack_kind,
        target_unit_instance_id=current_pool.target_unit_instance_id,
    )
    if current_permission_context is None:
        raise GameLifecycleError(f"{phase_label} dice reroll source context drift.")
    if current_permission_context.permission.source_id != source_rule_id:
        raise GameLifecycleError(f"{phase_label} dice reroll source context drift.")
    if (
        source_payload.get("effect_kind") == "tracked_target_reroll"
        and current_permission_context.source_payload != source_payload
    ):
        raise GameLifecycleError(f"{phase_label} dice reroll source payload drift.")


def _source_backed_attack_context_id_matches_active_pool(
    *,
    attack_sequence: AttackSequence,
    attack_context_id: str,
) -> bool:
    current_pool = attack_sequence.current_pool()
    pool_prefix = f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:"
    for attack_index in range(current_pool.attacks):
        base_context_id = f"{pool_prefix}attack-{attack_index + 1:03d}"
        if attack_context_id == base_context_id:
            return True
        generated_prefix = f"{base_context_id}:generated-hit-"
        if not attack_context_id.startswith(generated_prefix):
            continue
        generated_hit_number = attack_context_id.removeprefix(generated_prefix)
        if generated_hit_number.isdecimal() and int(generated_hit_number) >= 2:
            return True
    return False


def _source_backed_attack_kind_for_phase(source_phase: BattlePhase) -> str:
    if source_phase is BattlePhase.SHOOTING:
        return "ranged"
    if source_phase is BattlePhase.FIGHT:
        return "melee"
    raise GameLifecycleError("Source-backed attack rerolls require Shooting or Fight phase.")


def _request_source_backed_wound_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    pool: RangedAttackPool,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None = None,
    attacker_keywords: tuple[str, ...],
    attack_context_id: str,
    source_phase: BattlePhase,
) -> LifecycleStatus | None:
    if roll_state is None:
        return None
    if source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return None
    if roll_state.rerolls:
        return None
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=actor_id,
        unit_instance_id=attacking_unit_instance_id,
        model_instance_id=attacker_model_instance_id,
        roll_type=roll_state.original_result.spec.roll_type,
        timing_window="attack_sequence.wound",
        attack_kind=_source_backed_attack_kind_for_phase(source_phase),
        target_unit_instance_id=pool.target_unit_instance_id,
    )
    if permission_context is None:
        return None
    permission = _source_backed_wound_permission_for_attack(
        state=state,
        permission_context=permission_context,
        roll_state=roll_state,
        target_unit_instance_id=pool.target_unit_instance_id,
        attacker_keywords=attacker_keywords,
    )
    if permission is None:
        return None
    if _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        source_id=permission.source_id,
    ):
        return None
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=actor_id,
        permission=permission,
        extra_payload={
            "source_rule_id": permission.source_id,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "unit_instance_id": attacking_unit_instance_id,
                "target_unit_instance_id": pool.target_unit_instance_id,
                "attack_context_id": attack_context_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "wound_roll_state": validate_json_value(roll_state.to_payload()),
                "source_payload": validate_json_value(permission_context.source_payload),
            },
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": source_phase.value,
            "phase_body_status": "attack_wound_source_backed_reroll_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": attacking_unit_instance_id,
            "target_unit_instance_id": pool.target_unit_instance_id,
            "attack_context_id": attack_context_id,
            "pending_request_id": request.request_id,
        },
    )


def _source_backed_wound_permission_for_attack(
    *,
    state: GameState,
    permission_context: SourceBackedRerollPermissionContext,
    roll_state: DiceRollState,
    target_unit_instance_id: str,
    attacker_keywords: tuple[str, ...],
) -> RerollPermission | None:
    source_payload = permission_context.source_payload
    conditional = source_payload.get("conditional_wound_reroll")
    if conditional is None:
        return permission_context.permission
    if not isinstance(conditional, dict):
        raise GameLifecycleError("Conditional wound reroll payload must be an object.")
    if _conditional_wound_full_reroll_applies(
        state=state,
        conditional=conditional,
        target_unit_instance_id=target_unit_instance_id,
        attacker_keywords=attacker_keywords,
    ):
        return replace(
            permission_context.permission,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            allowed_component_selections=None,
        )
    reroll_values = conditional.get("reroll_unmodified_values")
    if not isinstance(reroll_values, list) or not all(
        type(value) is int for value in reroll_values
    ):
        raise GameLifecycleError("Conditional wound reroll requires integer reroll values.")
    if roll_state.current_total not in cast(list[int], reroll_values):
        return None
    return replace(
        permission_context.permission,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )


def _conditional_wound_full_reroll_applies(
    *,
    state: GameState,
    conditional: dict[str, JsonValue],
    target_unit_instance_id: str,
    attacker_keywords: tuple[str, ...],
) -> bool:
    if conditional.get("full_reroll_if_target_within_objective_range") is not True:
        return False
    required_keyword = conditional.get("full_reroll_required_attacker_keyword")
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError("Conditional wound reroll required keyword must be a string.")
        canonical_required = _canonical_keyword(required_keyword)
        if canonical_required not in {_canonical_keyword(keyword) for keyword in attacker_keywords}:
            return False
    return _target_unit_within_any_objective_marker_range(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
    )


def _target_unit_within_any_objective_marker_range(
    *,
    state: GameState,
    target_unit_instance_id: str,
) -> bool:
    if state.mission_setup is None or state.battlefield_state is None:
        return False
    try:
        unit_placement = state.battlefield_state.unit_placement_by_id(target_unit_instance_id)
    except PlacementError:
        return False
    target_models = tuple(
        geometry_model_for_placement(
            model=model_by_id(state=state, model_instance_id=placement.model_instance_id),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )
    return any(
        objective_marker_controls_model(
            marker_pose=Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
            model=target_model,
            marker_id=marker.objective_marker_id,
            horizontal_inches=marker.control_horizontal_inches,
            vertical_inches=marker.control_vertical_inches,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        for marker in (
            mission_marker.to_objective_marker()
            for mission_marker in state.mission_setup.objective_markers
        )
        for target_model in target_models
    )


def _canonical_keyword(keyword: str) -> str:
    return keyword.replace("_", " ").replace("-", " ").upper()


def _source_backed_reroll_already_answered(
    *,
    decisions: DecisionController,
    roll_id: str,
    source_id: str,
) -> bool:
    requested_roll_id = _validate_identifier("roll_id", roll_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    for record in decisions.records:
        if record.request.decision_type != DICE_REROLL_DECISION_TYPE:
            continue
        if not isinstance(record.request.payload, dict):
            raise GameLifecycleError("Dice reroll request payload must be an object.")
        if record.request.payload.get("roll_id") != requested_roll_id:
            continue
        permission_payload = record.request.payload.get("permission")
        if not isinstance(permission_payload, dict):
            continue
        if permission_payload.get("source_id") == requested_source_id:
            return True
    return False


def _command_reroll_opportunity_window(
    *,
    state: GameState,
    decisions: DecisionController,
    window_id: str,
    roll_state: DiceRollState,
    actor_id: str,
    affected_unit_instance_id: str,
    phase: BattlePhase,
    use_option_ids: tuple[str, ...],
    decline_option_id: str,
) -> OpportunityWindow:
    sequence_number = len(decisions.event_log.records)
    anchor_event_id = _dice_rolled_event_id_for_roll(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
    )
    timing_window = TimingWindow(
        window_id=window_id,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{window_id}:descriptor",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_rule_id="core:command-reroll",
            phase=phase,
            source_step=roll_state.original_result.spec.roll_type,
            metadata={
                "roll_id": roll_state.original_result.roll_id,
                "roll_type": roll_state.original_result.spec.roll_type,
                "affected_unit_instance_id": affected_unit_instance_id,
            },
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        trigger_event_id=anchor_event_id,
    )
    legal_actions = (
        OpportunityLegalAction(
            action_id=decline_option_id,
            source_id="core:pass",
            action_kind=OpportunityActionKind.PASS,
            controller_id=None,
            label="Decline Command Re-roll",
            batching_mode=TriggerBatchingMode.NONE,
            payload={"pass": True},
        ),
        *(
            OpportunityLegalAction(
                action_id=option_id,
                source_id="core:command-reroll",
                action_kind=OpportunityActionKind.REROLL,
                controller_id=actor_id,
                label="Command Re-roll",
                cost=({"resource": "cp", "amount": 1},),
                target_ids=(roll_state.original_result.roll_id,),
                target_spec={
                    "roll_id": roll_state.original_result.roll_id,
                    "roll_type": roll_state.original_result.spec.roll_type,
                    "affected_unit_instance_id": affected_unit_instance_id,
                },
                batching_mode=TriggerBatchingMode.ONE_OF,
                payload={
                    "stratagem_id": "command-reroll",
                    "option_id": option_id,
                    "roll_state": cast(JsonValue, roll_state.to_payload()),
                },
            )
            for option_id in use_option_ids
        ),
    )
    return OpportunityWindow(
        window_id=window_id,
        timing_window=timing_window,
        state_hash=_command_reroll_opportunity_state_hash(state=state, decisions=decisions),
        sequence_number=sequence_number,
        revision=1,
        anchor_event_ids=(anchor_event_id,),
        acting_player_id=state.active_player_id,
        eligible_player_ids=(actor_id,),
        priority_order=(actor_id,),
        legal_actions=legal_actions,
        default_action_id=decline_option_id,
        metadata={
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "phase": phase.value,
        },
    )


def _command_reroll_opportunity_options(
    *,
    window: OpportunityWindow,
    player_id: str,
    use_options: tuple[DecisionOption, ...],
    decline_option: DecisionOption,
) -> tuple[DecisionOption, ...]:
    return tuple(
        _command_reroll_opportunity_option(
            window=window,
            player_id=player_id,
            option=option,
        )
        for option in (*use_options, decline_option)
    )


def _command_reroll_opportunity_option(
    *,
    window: OpportunityWindow,
    player_id: str,
    option: DecisionOption,
) -> DecisionOption:
    action = window.action_by_id(option.option_id)
    if not isinstance(option.payload, dict):
        raise GameLifecycleError("Command Re-roll opportunity option payload must be an object.")
    fingerprint = window.legal_action_fingerprint(player_id)
    payload = dict(option.payload)
    payload[OPPORTUNITY_SUBMISSION_PAYLOAD_KEY] = window.submission_payload_for_action(
        action=action,
        player_id=player_id,
        legal_action_fingerprint=fingerprint,
    )
    return DecisionOption(
        option_id=option.option_id,
        label=option.label,
        payload=validate_json_value(payload),
    )


def _command_reroll_opportunity_state_hash(
    *,
    state: GameState,
    decisions: DecisionController,
) -> str:
    records = decisions.event_log.records
    return opportunity_boundary_state_hash(
        state_payload=_command_reroll_opportunity_boundary_state_payload(state),
        event_count=len(records),
        last_event_id=None if not records else records[-1].event_id,
    )


def _command_reroll_opportunity_boundary_state_payload(state: GameState) -> JsonValue:
    return opportunity_boundary_game_state_payload(
        game_id=state.game_id,
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        stage=state.stage.value,
        battle_phase_index=state.battle_phase_index,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        decision_request_count=state.decision_request_count,
        command_point_ledgers=cast(
            JsonValue,
            [ledger.to_payload() for ledger in state.command_point_ledgers],
        ),
        stratagem_use_records=cast(
            JsonValue,
            [record.to_payload() for record in state.stratagem_use_records],
        ),
        faction_rule_states=cast(
            JsonValue,
            [record.to_payload() for record in state.faction_rule_states],
        ),
    )


def _dice_rolled_event_id_for_roll(*, decisions: DecisionController, roll_id: str) -> str:
    requested_roll_id = _validate_identifier("roll_id", roll_id)
    for event in decisions.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("dice_rolled event payload must be an object.")
        result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if result.roll_id == requested_roll_id:
            return event.event_id
    raise GameLifecycleError("Command Re-roll opportunity requires a recorded dice roll.")


def _random_characteristic_roll_spec(
    *,
    characteristic: Characteristic,
    timing: RandomCharacteristicTiming,
    scope_id: str,
    expression: DiceExpression,
    reason: str,
    actor_id: str | None,
) -> DiceRollSpec:
    if type(characteristic) is not Characteristic:
        raise GameLifecycleError("Random characteristic requires a Characteristic.")
    if type(timing) is not RandomCharacteristicTiming:
        raise GameLifecycleError("Random characteristic requires a timing.")
    if type(expression) is not DiceExpression:
        raise GameLifecycleError("Random characteristic requires a DiceExpression.")
    scope = _validate_identifier("Random characteristic scope_id", scope_id)
    return DiceRollSpec(
        expression=expression,
        reason=reason,
        roll_type=f"random_characteristic.{characteristic.value}.{timing.value}.{scope}",
        actor_id=actor_id,
    )


def _append_replay_resume_unique_event_once(
    *,
    decisions: DecisionController,
    event_type: str,
    payload: JsonValue,
) -> EventRecord:
    """Append one logical replay event whose payload carries a stable unique identity.

    This is only for attack-sequence resume paths where rerunning a resolver can
    revisit an already-emitted event with the same roll, attack context, or
    characteristic scope. Do not use it for events whose payloads can be
    legitimately identical across separate game happenings.
    """

    event_payload = validate_json_value(payload)
    for event in decisions.event_log.records:
        if event.event_type == event_type and event.payload == event_payload:
            return event
    return decisions.event_log.append(event_type, event_payload)


def _psychic_attack_modifier_ignore_request(
    *,
    state: GameState,
    pool: RangedAttackPool,
    attacker_player_id: str,
    attacking_unit_instance_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> DecisionRequest | None:
    if not is_psychic_weapon_profile(pool.weapon_profile):
        return None
    skill_modifier = _hit_skill_modifier(state=state, pool=pool)
    hit_roll_modifier = _hit_roll_modifier(
        state=state,
        pool=pool,
        source_phase=source_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if skill_modifier == 0 and hit_roll_modifier == 0:
        return None
    options = _psychic_attack_modifier_ignore_options(
        attack_context_id=attack_context_id,
        weapon_profile_id=pool.weapon_profile_id,
        skill_modifier=skill_modifier,
        hit_roll_modifier=hit_roll_modifier,
    )
    if len(options) <= 1:
        return None
    request_id = state.next_decision_request_id()
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
        actor_id=attacker_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
                "attack_context_id": attack_context_id,
                "attacking_unit_instance_id": attacking_unit_instance_id,
                "attacker_model_instance_id": pool.attacker_model_instance_id,
                "target_unit_instance_id": pool.target_unit_instance_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "source_phase": source_phase.value,
                "skill_modifier": skill_modifier,
                "hit_roll_modifier": hit_roll_modifier,
            }
        ),
        options=options,
    )


def _psychic_attack_modifier_ignore_options(
    *,
    attack_context_id: str,
    weapon_profile_id: str,
    skill_modifier: int,
    hit_roll_modifier: int,
) -> tuple[DecisionOption, ...]:
    candidates: list[tuple[str, str, int, int]] = [
        (
            KEEP_ALL_MODIFIERS_OPTION_ID,
            "Keep all modifiers",
            skill_modifier,
            hit_roll_modifier,
        )
    ]
    if _has_detrimental_psychic_modifier(
        skill_modifier=skill_modifier,
        hit_roll_modifier=hit_roll_modifier,
    ):
        candidates.append(
            (
                IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID,
                "Ignore detrimental modifiers",
                0 if skill_modifier > 0 else skill_modifier,
                0 if hit_roll_modifier < 0 else hit_roll_modifier,
            )
        )
    if _has_beneficial_psychic_modifier(
        skill_modifier=skill_modifier,
        hit_roll_modifier=hit_roll_modifier,
    ):
        candidates.append(
            (
                IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID,
                "Ignore beneficial modifiers",
                0 if skill_modifier < 0 else skill_modifier,
                0 if hit_roll_modifier > 0 else hit_roll_modifier,
            )
        )
    candidates.append((IGNORE_ALL_MODIFIERS_OPTION_ID, "Ignore all modifiers", 0, 0))
    options: list[DecisionOption] = []
    seen_effective_values: set[tuple[int, int]] = set()
    for option_id, label, effective_skill_modifier, effective_hit_roll_modifier in candidates:
        effective_key = (effective_skill_modifier, effective_hit_roll_modifier)
        if effective_key in seen_effective_values:
            continue
        seen_effective_values.add(effective_key)
        options.append(
            DecisionOption(
                option_id=option_id,
                label=label,
                payload=validate_json_value(
                    {
                        "submission_kind": (SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE),
                        "attack_context_id": attack_context_id,
                        "weapon_profile_id": weapon_profile_id,
                        "option_id": option_id,
                        "skill_modifier": skill_modifier,
                        "hit_roll_modifier": hit_roll_modifier,
                        "effective_skill_modifier": effective_skill_modifier,
                        "effective_hit_roll_modifier": effective_hit_roll_modifier,
                        "ignored_skill_modifier": (skill_modifier - effective_skill_modifier),
                        "ignored_hit_roll_modifier": (
                            hit_roll_modifier - effective_hit_roll_modifier
                        ),
                    }
                ),
            )
        )
    return tuple(options)


def _psychic_attack_modifier_ignore_selection_for_attack(
    *,
    decisions: DecisionController,
    attack_context_id: str,
) -> PsychicAttackModifierIgnoreSelection | None:
    requested_attack_context_id = _validate_identifier("attack_context_id", attack_context_id)
    for record in reversed(decisions.records):
        if record.request.decision_type != SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
            continue
        request_payload = _payload_object(record.request.payload)
        if _payload_string(request_payload, key="attack_context_id") != requested_attack_context_id:
            continue
        payload = _payload_object(record.result.payload)
        return PsychicAttackModifierIgnoreSelection(
            option_id=_payload_string(payload, key="option_id"),
            skill_modifier=_payload_int(payload, key="skill_modifier"),
            hit_roll_modifier=_payload_int(payload, key="hit_roll_modifier"),
            effective_skill_modifier=_payload_int(payload, key="effective_skill_modifier"),
            effective_hit_roll_modifier=_payload_int(
                payload,
                key="effective_hit_roll_modifier",
            ),
        )
    return None


def validate_psychic_attack_modifier_ignore_decision(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
) -> None:
    record = decisions.record_for_result(result)
    if record.request.decision_type != SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
        raise GameLifecycleError("Psychic modifier ignore decision has wrong request type.")
    request_payload = _payload_object(record.request.payload)
    attack_context_id = _payload_string(request_payload, key="attack_context_id")
    if attack_context_id != attack_sequence.attack_context_id():
        raise GameLifecycleError("Psychic modifier ignore decision attack context drift.")
    payload = _payload_object(result.payload)
    selection = PsychicAttackModifierIgnoreSelection(
        option_id=_payload_string(payload, key="option_id"),
        skill_modifier=_payload_int(payload, key="skill_modifier"),
        hit_roll_modifier=_payload_int(payload, key="hit_roll_modifier"),
        effective_skill_modifier=_payload_int(payload, key="effective_skill_modifier"),
        effective_hit_roll_modifier=_payload_int(payload, key="effective_hit_roll_modifier"),
    )
    if selection.option_id != result.selected_option_id:
        raise GameLifecycleError("Psychic modifier ignore decision option drift.")


def _has_detrimental_psychic_modifier(*, skill_modifier: int, hit_roll_modifier: int) -> bool:
    return skill_modifier > 0 or hit_roll_modifier < 0


def _has_beneficial_psychic_modifier(*, skill_modifier: int, hit_roll_modifier: int) -> bool:
    return skill_modifier < 0 or hit_roll_modifier > 0


def _roll_hit(
    *,
    state: GameState,
    manager: DiceRollManager,
    pool: RangedAttackPool,
    attacker_player_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    psychic_modifier_selection: PsychicAttackModifierIgnoreSelection | None = None,
) -> HitRoll:
    skill_modifier = _hit_skill_modifier(state=state, pool=pool)
    modifier = _hit_roll_modifier(
        state=state,
        pool=pool,
        source_phase=source_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if psychic_modifier_selection is not None:
        if (
            psychic_modifier_selection.skill_modifier != skill_modifier
            or psychic_modifier_selection.hit_roll_modifier != modifier
        ):
            raise GameLifecycleError("Psychic modifier ignore selection context drift.")
        skill_modifier = psychic_modifier_selection.effective_skill_modifier
        modifier = psychic_modifier_selection.effective_hit_roll_modifier
    skill = _hit_skill(pool.weapon_profile) + skill_modifier
    skill = max(2, min(skill, 6))
    is_snap_shooting = (
        FIRE_OVERWATCH_RULE_ID in pool.targeting_rule_ids
        or SNAP_SHOOTING_RULE_ID in pool.targeting_rule_ids
    )
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TORRENT):
        return HitRoll.auto_hit(target_number=skill)
    roll_state = _roll_or_reuse_state(
        manager,
        attack_sequence_hit_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id=attacker_player_id,
            reroll_forbidden_rule_ids=_hit_reroll_forbidden_rule_ids(
                is_snap_shooting=is_snap_shooting,
                targeting_rule_ids=pool.targeting_rule_ids,
            ),
        ),
    )
    unmodified = roll_state.current_total
    capped_modifier = _cap_roll_modifier(modifier)
    final_roll = unmodified + capped_modifier
    if is_snap_shooting:
        minimum_success = 6
    elif INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in pool.targeting_rule_ids:
        minimum_success = (
            4 if INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in pool.targeting_rule_ids else 6
        )
    else:
        minimum_success = 2
    target_keywords = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    ).keywords
    sustained_hits_d3_value: int | None = None
    if unmodified == 6 and (
        weapon_ability_value(
            pool.weapon_profile,
            AbilityKind.SUSTAINED_HITS,
            target_keywords=target_keywords,
        )
        == SUSTAINED_HITS_D3_VALUE
    ):
        sustained_hits_d3_value = manager.roll_d3(
            reason=(
                "Sustained Hits D3 generated hits for "
                f"{pool.weapon_profile_id} attack {attack_context_id}"
            ),
            roll_type="attack_sequence.sustained_hits.generated_hits",
            actor_id=attacker_player_id,
        ).value
    generated_hits = sustained_hits_generated_hits(
        pool.weapon_profile,
        critical_hit=unmodified == 6,
        target_keywords=target_keywords,
        d3_value=sustained_hits_d3_value,
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


def _hit_reroll_forbidden_rule_ids(
    *,
    is_snap_shooting: bool,
    targeting_rule_ids: tuple[str, ...],
) -> tuple[str, ...]:
    rule_ids: list[str] = []
    if is_snap_shooting:
        rule_ids.append(SNAP_SHOOTING_RULE_ID)
    if INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in targeting_rule_ids:
        rule_ids.append(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID)
    return tuple(dict.fromkeys(rule_ids))


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
    roll_state = _roll_or_reuse_state(
        manager,
        attack_sequence_wound_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id=attacker_player_id,
        ),
    )
    unmodified = roll_state.current_total
    capped_modifier = _cap_roll_modifier(wound_modifier)
    final_roll = unmodified + capped_modifier
    critical_threshold = anti_keyword_critical_threshold(
        profile=pool.weapon_profile,
        target_keywords=target_keywords,
        selected_ability_id=_selected_anti_keyword_ability_id(pool),
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


def _wound_roll_modifier(
    *,
    state: GameState,
    pool: RangedAttackPool,
    source_phase: BattlePhase,
    toughness: int,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> int:
    if type(pool) is not RangedAttackPool:
        raise GameLifecycleError("Wound roll modifier requires a RangedAttackPool.")
    modifier = 0
    if LANCE_RULE_ID in pool.targeting_rule_ids:
        modifier += 1
    modifier += _runtime_modifier_registry(runtime_modifier_registry).wound_roll_modifier(
        WoundRollModifierContext(
            state=state,
            source_phase=source_phase,
            attacking_unit_instance_id=_unit_instance_id_for_model(
                state=state,
                model_instance_id=pool.attacker_model_instance_id,
            ),
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            weapon_profile=pool.weapon_profile,
            strength=pool.weapon_profile.strength.final,
            toughness=toughness,
        )
    )
    return modifier


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
        selected_ability_id=_selected_anti_keyword_ability_id(pool),
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


def _selected_anti_keyword_ability_id(pool: RangedAttackPool) -> str | None:
    ability_by_id = {ability.ability_id: ability for ability in pool.weapon_profile.abilities}
    selected_ids: list[str] = []
    for ability_id in pool.selected_weapon_ability_ids:
        ability = ability_by_id.get(ability_id)
        if ability is None:
            raise GameLifecycleError(
                "Selected weapon ability ID is not on the attack pool profile."
            )
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD:
            selected_ids.append(ability_id)
    if len(selected_ids) > 1:
        raise GameLifecycleError("Attack pool must not select multiple Anti ability IDs.")
    if not selected_ids:
        return None
    return selected_ids[0]


def _emit_damage_event(
    *,
    state: GameState,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    damage: DamageApplication | None,
    saving_throw: SavingThrow | None,
    saving_throw_payload: JsonValue | None = None,
    feel_no_pain: FeelNoPainResolution | None = None,
    destroyed_model_placement: JsonValue | None = None,
) -> DestroyedModelEmission | None:
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
            "weapon_profile_id": attack_sequence.current_pool().weapon_profile_id,
        }
    )
    damage_event = _emit_event(
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
        removal_record = _destroyed_model_removal_record(
            model_instance_id=damage.model_instance_id,
            source_phase=attack_sequence.source_phase.value,
            source_event_id=damage_event.event_id,
        )
        transition_batch = BattlefieldTransitionBatch(removals=(removal_record,))
        destroyed_event = decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": attack_sequence.source_phase.value,
                "destroying_player_id": attack_sequence.attacker_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "target_unit_instance_id": damage.target_unit_instance_id,
                "model_instance_id": damage.model_instance_id,
                "damage_kind": damage.damage_kind.value,
                "damage_event_id": damage_event.event_id,
                "removal_record": removal_record.to_payload(),
                "transition_batch": transition_batch.to_payload(),
                "destroyed_model_placement": validate_json_value(destroyed_model_placement),
                "destroyed_model_rules_triggered": True,
            },
        )
        return DestroyedModelEmission(
            damage_event_id=damage_event.event_id,
            model_destroyed_event_id=destroyed_event.event_id,
            removal_record=removal_record,
            transition_batch=transition_batch,
        )
    return None


def _destroyed_model_removal_record(
    *,
    model_instance_id: str,
    source_phase: str,
    source_event_id: str,
) -> ModelRemovalRecord:
    return ModelRemovalRecord(
        model_instance_id=model_instance_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        source_phase=source_phase,
        source_step=AttackSequenceStep.DAMAGE.value,
        source_rule_id=DAMAGE_ALLOCATION_RULE_ID,
        source_event_id=source_event_id,
    )


def _destroyed_model_placement_payload(
    *,
    state: GameState,
    model_instance_id: str,
) -> JsonValue:
    if state.battlefield_state is None:
        raise GameLifecycleError("Destroyed model placement capture requires battlefield state.")
    try:
        placement = state.battlefield_state.model_placement_by_id(model_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Destroyed model placement capture requires placed model."
        ) from exc
    return validate_json_value(placement.to_payload())


def _emit_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    event: AttackSequenceEvent,
) -> EventRecord:
    emitted = hooks.emit(event)
    return _append_replay_resume_unique_event_once(
        decisions=decisions,
        event_type="attack_sequence_step",
        payload=validate_json_value(emitted.to_payload()),
    )


def _target_has_effect_cover(*, state: GameState, target_unit_instance_id: str) -> bool:
    return unit_effects_grant_benefit_of_cover(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )


def _target_has_effect_cover_denial(*, state: GameState, target_unit_instance_id: str) -> bool:
    return unit_effects_deny_benefit_of_cover(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )


def _benefit_of_cover_ballistic_skill_penalty(
    *,
    state: GameState,
    pool: RangedAttackPool,
) -> int:
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.IGNORES_COVER):
        return 0
    if _target_has_effect_cover_denial(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        return 0
    if BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids:
        return 1
    if INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids:
        return 1
    if _target_has_effect_cover(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        return 1
    return 0


def _hit_skill_modifier(*, state: GameState, pool: RangedAttackPool) -> int:
    return _benefit_of_cover_ballistic_skill_penalty(
        state=state,
        pool=pool,
    ) - _plunging_fire_ballistic_skill_improvement(pool=pool)


def _hit_roll_modifier(
    *,
    state: GameState,
    pool: RangedAttackPool,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> int:
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    return (
        pool.hit_roll_modifier
        + _persisting_hit_roll_modifier(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
        )
        + runtime_modifiers.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=_unit_instance_id_for_model(
                    state=state,
                    model_instance_id=pool.attacker_model_instance_id,
                ),
                attacker_model_instance_id=pool.attacker_model_instance_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                weapon_profile=pool.weapon_profile,
                source_phase=source_phase,
            )
        )
    )


def _plunging_fire_ballistic_skill_improvement(*, pool: RangedAttackPool) -> int:
    if PLUNGING_FIRE_RULE_ID in pool.targeting_rule_ids:
        return 1
    return 0


def _persisting_hit_roll_modifier(*, state: GameState, target_unit_instance_id: str) -> int:
    return unit_effect_hit_roll_modifier(state.persisting_effects_for_unit(target_unit_instance_id))


def _unit_instance_id_for_model(*, state: GameState, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == requested_model_id for model in unit.own_models):
                return unit.unit_instance_id
    raise GameLifecycleError("Attack modifier model is not in any unit.")


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


def _melta_damage_modifier(
    pool: RangedAttackPool,
    *,
    target_keywords: tuple[str, ...],
) -> int:
    if not any(rule_id.startswith(MELTA_RULE_ID) for rule_id in pool.targeting_rule_ids):
        return 0
    return melta_damage_bonus(
        pool.weapon_profile,
        target_within_half_range=True,
        target_keywords=target_keywords,
    )


def _devastating_wounds_resolution_for_attack(
    *,
    pool: RangedAttackPool,
    attack_context: AttackResolutionContextPayload,
    target_keywords: tuple[str, ...],
) -> DevastatingWoundsResolution | None:
    if not bool(attack_context["wound_roll"]["critical"]):
        return None
    return devastating_wounds_resolution(pool.weapon_profile, target_keywords=target_keywords)


def _resolve_hazardous_tests(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    hazardous_pools = tuple(
        pool
        for pool in attack_sequence.attack_pools
        if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.HAZARDOUS)
    )
    if not hazardous_pools:
        return None
    hazardous_weapon_profile_ids = tuple(
        sorted({pool.weapon_profile_id for pool in hazardous_pools})
    )
    roll_state = manager.roll(
        hazard_roll_spec(
            reason=(
                f"Hazardous test for {attack_sequence.attacking_unit_instance_id} after shooting"
            ),
            roll_type="hazardous_test",
            actor_id=attack_sequence.attacking_unit_instance_id,
        )
    )
    hazardous_failed = hazard_roll_failed(roll_state)
    mortal_wounds = 0
    if not hazardous_failed:
        _emit_hazardous_test_resolved(
            decisions=decisions,
            attack_sequence=attack_sequence,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            roll_state=roll_state,
            successful=True,
            mortal_wounds=mortal_wounds,
            mortal_wound_application=None,
            pending_mortal_wound_request_id=None,
        )
        return None

    mortal_wounds = _hazardous_mortal_wounds_for_attacker(
        state=state,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
    )
    progress = MortalWoundApplicationProgress.start(
        application_id=f"{attack_sequence.sequence_id}:hazardous:mortal-wounds",
        source_rule_id=HAZARDOUS_RULE_ID,
        source_context=_hazardous_source_context_payload(
            attack_sequence=attack_sequence,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            roll_state=roll_state,
            mortal_wounds=mortal_wounds,
        ),
        target_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=attack_sequence.attacking_unit_instance_id,
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
        _emit_hazardous_test_resolved(
            decisions=decisions,
            attack_sequence=attack_sequence,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            roll_state=roll_state,
            successful=False,
            mortal_wounds=mortal_wounds,
            mortal_wound_application=None,
            pending_mortal_wound_request_id=routed.request.request_id,
        )
        return _hazardous_feel_no_pain_status(
            attack_sequence=attack_sequence,
            request=routed.request,
        )
    if routed.application is None:
        raise GameLifecycleError("Hazardous mortal wounds did not produce application.")
    _emit_hazardous_test_resolved(
        decisions=decisions,
        attack_sequence=attack_sequence,
        hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
        roll_state=roll_state,
        successful=False,
        mortal_wounds=mortal_wounds,
        mortal_wound_application=routed.application,
        pending_mortal_wound_request_id=None,
    )
    _emit_hazardous_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        source_context=_hazardous_source_context_from_payload(progress.source_context),
        application=routed.application,
    )
    return None


def _emit_hazardous_test_resolved(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    hazardous_weapon_profile_ids: tuple[str, ...],
    roll_state: DiceRollState,
    successful: bool,
    mortal_wounds: int,
    mortal_wound_application: MortalWoundApplication | None,
    pending_mortal_wound_request_id: str | None,
) -> None:
    decisions.event_log.append(
        "hazardous_test_resolved",
        {
            "source_rule_id": HAZARDOUS_RULE_ID,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "hazardous_weapon_profile_ids": list(hazardous_weapon_profile_ids),
            "roll_state": roll_state.to_payload(),
            "successful": successful,
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": (
                None if mortal_wound_application is None else mortal_wound_application.to_payload()
            ),
            "pending_mortal_wound_request_id": pending_mortal_wound_request_id,
        },
    )


def _emit_hazardous_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    source_context: HazardousMortalWoundSourceContextPayload,
    application: MortalWoundApplication,
) -> None:
    decisions.event_log.append(
        "hazardous_mortal_wounds_applied",
        {
            "source_rule_id": HAZARDOUS_RULE_ID,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "hazardous_weapon_profile_ids": source_context["hazardous_weapon_profile_ids"],
            "hazardous_roll_state": source_context["hazardous_roll_state"],
            "mortal_wounds": source_context["mortal_wounds"],
            "mortal_wound_application": application.to_payload(),
        },
    )


def _hazardous_feel_no_pain_status(
    *,
    attack_sequence: AttackSequence,
    request: DecisionRequest,
) -> LifecycleStatus:
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": attack_sequence.source_phase.value,
            "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
            "sequence_id": attack_sequence.sequence_id,
            "source_rule_id": HAZARDOUS_RULE_ID,
            "source_kind": HAZARDOUS_SOURCE_KIND,
        },
    )


def _hazardous_source_context_payload(
    *,
    attack_sequence: AttackSequence,
    hazardous_weapon_profile_ids: tuple[str, ...],
    roll_state: DiceRollState,
    mortal_wounds: int,
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": HAZARDOUS_SOURCE_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "hazardous_weapon_profile_ids": list(hazardous_weapon_profile_ids),
            "hazardous_roll_state": roll_state.to_payload(),
            "mortal_wounds": mortal_wounds,
        }
    )


def _hazardous_source_context_from_payload(
    payload: JsonValue,
) -> HazardousMortalWoundSourceContextPayload:
    raw = _payload_object(payload)
    if raw.get("source_kind") != HAZARDOUS_SOURCE_KIND:
        raise GameLifecycleError("Hazardous mortal wound source context kind is invalid.")
    weapon_profile_ids = raw.get("hazardous_weapon_profile_ids")
    if not isinstance(weapon_profile_ids, list):
        raise GameLifecycleError(
            "Hazardous mortal wound source context weapon profile IDs must be a list."
        )
    hazardous_roll_state = raw.get("hazardous_roll_state")
    if not isinstance(hazardous_roll_state, dict):
        raise GameLifecycleError(
            "Hazardous mortal wound source context roll state must be an object."
        )
    return {
        "source_kind": HAZARDOUS_SOURCE_KIND,
        "sequence_id": _payload_string(raw, key="sequence_id"),
        "attacking_unit_instance_id": _payload_string(raw, key="attacking_unit_instance_id"),
        "hazardous_weapon_profile_ids": list(
            _validate_identifier_tuple(
                "Hazardous mortal wound weapon_profile_ids",
                tuple(weapon_profile_ids),
            )
        ),
        "hazardous_roll_state": cast(
            DiceRollStatePayload,
            validate_json_value(hazardous_roll_state),
        ),
        "mortal_wounds": _payload_positive_int(raw, key="mortal_wounds"),
    }


def _hazardous_mortal_wounds_for_attacker(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
) -> int:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=attacking_unit_instance_id,
    )
    component_wound_values = tuple(
        hazard_mortal_wounds_per_failed_roll(component.unit) for component in rules_unit.components
    )
    if not component_wound_values:
        raise GameLifecycleError("Hazardous attacker requires at least one component.")
    return min(component_wound_values)


def _cover_for_allocated_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pool: RangedAttackPool,
    allocated_model_id: str,
) -> BenefitOfCoverResult | None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Allocated-model cover requires battlefield_state.")
    if not battlefield.terrain_features:
        return None
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
    terrain_features = battlefield.terrain_features
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
        target_keywords=rules_unit_view_by_id(
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


def _target_unit_toughness(
    *,
    state: GameState,
    target_unit_instance_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> int:
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    alive_model_ids = allocation_context.alive_model_ids
    if (
        allocation_context.attached_unit_bodyguard_model_ids
        or allocation_context.attached_unit_character_model_ids
    ):
        model_ids = (
            allocation_context.attached_unit_bodyguard_model_ids
            if allocation_context.attached_unit_bodyguard_model_ids
            else alive_model_ids
        )
        base_toughness = _highest_toughness_for_models(
            state=state,
            model_instance_ids=model_ids,
        )
        return runtime_modifiers.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=target_unit_instance_id,
                characteristic=Characteristic.TOUGHNESS,
                base_value=base_toughness,
                current_value=base_toughness,
            )
        )
    toughness_values = _toughness_values_for_models(
        state=state,
        model_instance_ids=alive_model_ids,
    )
    if len(toughness_values) != 1:
        raise GameLifecycleError("Mixed Toughness target units are deferred to Phase 14H/16D.")
    base_toughness = next(iter(toughness_values))
    return runtime_modifiers.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=target_unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=base_toughness,
            current_value=base_toughness,
        )
    )


def _highest_toughness_for_models(
    *,
    state: GameState,
    model_instance_ids: tuple[str, ...],
) -> int:
    toughness_values = _toughness_values_for_models(
        state=state,
        model_instance_ids=model_instance_ids,
    )
    return max(toughness_values)


def _toughness_values_for_models(
    *,
    state: GameState,
    model_instance_ids: tuple[str, ...],
) -> set[int]:
    model_ids = _validate_identifier_tuple("target toughness model IDs", model_instance_ids)
    if not model_ids:
        raise GameLifecycleError("Target unit has no alive models.")
    toughness_values: set[int] = set()
    for model_id in model_ids:
        model = model_by_id(state=state, model_instance_id=model_id)
        for value in model.characteristics:
            if value.characteristic is Characteristic.TOUGHNESS:
                toughness_values.add(value.final)
                break
        else:
            raise GameLifecycleError("Target unit models require Toughness.")
    return toughness_values


def _damage_value(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    profile: DamageProfile,
    attack_context_id: str,
    attacker_player_id: str,
    affected_unit_instance_id: str,
    source_phase: BattlePhase,
    stratagem_index: StratagemCatalogIndex | None,
) -> tuple[int | None, LifecycleStatus | None]:
    if type(profile) is not DamageProfile:
        raise GameLifecycleError("Damage resolution requires a DamageProfile.")
    if profile.fixed_damage is not None:
        return profile.fixed_damage, None
    if profile.dice_expression is None:
        raise GameLifecycleError("DamageProfile requires fixed damage or a dice expression.")
    scope_id = f"{attack_context_id}:damage"
    timing = RandomCharacteristicTiming.PER_ATTACK
    roll_state = _roll_or_reuse_state(
        manager,
        _random_characteristic_roll_spec(
            characteristic=Characteristic.DAMAGE,
            timing=timing,
            scope_id=scope_id,
            expression=profile.dice_expression,
            reason="Phase 13C random Damage roll",
            actor_id=attacker_player_id,
        ),
    )
    status = _request_command_reroll_for_attack_roll_if_available(
        state=state,
        decisions=decisions,
        roll_state=roll_state,
        affected_unit_instance_id=affected_unit_instance_id,
        source_phase=source_phase,
        stratagem_index=stratagem_index,
        phase_body_status="attack_damage_command_reroll_pending",
    )
    if status is not None:
        return None, status
    random_roll = RandomCharacteristicRoll(
        characteristic=Characteristic.DAMAGE,
        timing=timing,
        scope_id=scope_id,
        roll_state=roll_state,
        value=roll_state.current_total,
    )
    _append_replay_resume_unique_event_once(
        decisions=decisions,
        event_type="random_characteristic_rolled",
        payload=validate_json_value(random_roll.to_payload()),
    )
    return random_roll.value, None


def _model_is_alive(*, state: GameState, model_instance_id: str) -> bool:
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if not model.is_alive:
        return False
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Alive model lookup requires battlefield_state.")
    return model_instance_id in set(battlefield.placed_model_ids())


def _current_model_id_for_allocation_group(
    *,
    state: GameState,
    allocation_group: AllocationGroup,
) -> str:
    if type(allocation_group) is not AllocationGroup:
        raise GameLifecycleError("Current allocation group must be an AllocationGroup.")
    for model_id in allocation_group.ordered_model_ids_for_damage():
        if _model_is_alive(state=state, model_instance_id=model_id):
            return model_id
    raise GameLifecycleError("Allocation group has no alive models.")


def _legal_model_ids_for_allocation_group_damage(
    *,
    state: GameState,
    allocation_group: AllocationGroup,
) -> tuple[str, ...]:
    if type(allocation_group) is not AllocationGroup:
        raise GameLifecycleError("Damage allocation group must be an AllocationGroup.")
    alive_models = tuple(
        model_by_id(state=state, model_instance_id=model_id)
        for model_id in allocation_group.model_ids
        if _model_is_alive(state=state, model_instance_id=model_id)
    )
    wounded_model_ids = tuple(
        model.model_instance_id
        for model in alive_models
        if model.wounds_remaining < model.starting_wounds
    )
    if wounded_model_ids:
        return wounded_model_ids
    return tuple(model.model_instance_id for model in alive_models)


def _current_allocation_group_for_order(
    *,
    state: GameState,
    allocation_groups: tuple[AllocationGroup, ...],
) -> AllocationGroup | None:
    ordered_groups = _validate_ordered_allocation_group_tuple(
        "Current allocation order allocation_groups",
        allocation_groups,
    )
    for group in ordered_groups:
        if any(
            _model_is_alive(state=state, model_instance_id=model_id) for model_id in group.model_ids
        ):
            return group
    return None


def identical_attack_signature(pool: RangedAttackPool) -> IdenticalAttackSignature:
    if type(pool) is not RangedAttackPool:
        raise GameLifecycleError("identical_attack_signature requires a RangedAttackPool.")
    profile = pool.weapon_profile
    _validate_weapon_profile_signature_shape(profile)
    hit_basis = (
        "auto_hit:torrent"
        if WeaponKeyword.TORRENT in profile.keywords
        else f"hit_target:{_hit_skill(profile)}"
    )
    return IdenticalAttackSignature(
        attacker_model_instance_id=pool.attacker_model_instance_id,
        target_visible_model_ids=pool.target_visible_model_ids,
        target_in_range_model_ids=pool.target_in_range_model_ids,
        hit_basis=hit_basis,
        hit_roll_modifier=pool.hit_roll_modifier,
        wound_roll_modifiers=(),
        strength=canonical_json(profile.strength.to_payload()),
        armor_penetration=canonical_json(profile.armor_penetration.to_payload()),
        damage=canonical_json(profile.damage_profile.to_payload()),
        weapon_rule_tokens=(
            *_weapon_rule_tokens_for_signature(profile),
            *(
                f"selected-weapon-ability:{ability_id}"
                for ability_id in pool.selected_weapon_ability_ids
            ),
        ),
        targeting_rule_ids=tuple(sorted(pool.targeting_rule_ids)),
        shooting_type=pool.shooting_type.value,
        firing_deck_source_unit_instance_id=pool.firing_deck_source_unit_instance_id,
        firing_deck_source_model_instance_id=pool.firing_deck_source_model_instance_id,
    )


def unresolved_target_unit_ids(attack_sequence: AttackSequence) -> tuple[str, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Unresolved target lookup requires an AttackSequence.")
    used = set(attack_sequence.used_pool_indices)
    target_ids = {
        pool.target_unit_instance_id
        for pool_index, pool in enumerate(attack_sequence.attack_pools)
        if pool_index not in used
    }
    return tuple(sorted(target_ids))


def gathered_attack_groups_for_target(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> tuple[GatheredAttackGroup, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Gathered attack grouping requires an AttackSequence.")
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    used = set(attack_sequence.used_pool_indices)
    grouped_indices: dict[IdenticalAttackSignature, list[int]] = {}
    for pool_index, pool in enumerate(attack_sequence.attack_pools):
        if pool_index in used or pool.target_unit_instance_id != target_id:
            continue
        signature = identical_attack_signature(pool)
        grouped_indices.setdefault(signature, []).append(pool_index)
    groups = tuple(
        _gathered_attack_group_from_indices(
            attack_sequence=attack_sequence,
            target_unit_instance_id=target_id,
            signature=signature,
            pool_indices=tuple(indices),
        )
        for signature, indices in grouped_indices.items()
    )
    return tuple(sorted(groups, key=lambda group: group.group_id))


def build_select_resolve_target_unit_request(
    *,
    request_id: str,
    state: GameState,
    attack_sequence: AttackSequence,
) -> DecisionRequest:
    target_ids = unresolved_target_unit_ids(attack_sequence)
    if not target_ids:
        raise GameLifecycleError("Resolve target selection requires unresolved target units.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        actor_id=attack_sequence.attacker_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": attack_sequence.source_phase.value,
                "sequence_id": attack_sequence.sequence_id,
                "attacker_player_id": attack_sequence.attacker_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "target_unit_instance_ids": list(target_ids),
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=_resolve_target_option_id(target_id),
                label=target_id,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "target_unit_instance_id": target_id,
                    }
                ),
            )
            for target_id in target_ids
        ),
    )


def build_select_attack_weapon_group_request(
    *,
    request_id: str,
    state: GameState,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> DecisionRequest:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    groups = gathered_attack_groups_for_target(
        attack_sequence=attack_sequence,
        target_unit_instance_id=target_id,
    )
    if not groups:
        raise GameLifecycleError("Attack weapon group selection requires unresolved groups.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        actor_id=attack_sequence.attacker_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": attack_sequence.source_phase.value,
                "sequence_id": attack_sequence.sequence_id,
                "attacker_player_id": attack_sequence.attacker_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "target_unit_instance_id": target_id,
                "group_ids": [group.group_id for group in groups],
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=group.group_id,
                label=group.group_id,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "target_unit_instance_id": target_id,
                        "gathered_group": group.to_payload(),
                    }
                ),
            )
            for group in groups
        ),
    )


def selected_resolve_target_from_result(result: DecisionResult) -> str:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Resolve target selection requires a DecisionResult.")
    payload = _payload_object(result.payload)
    if payload.get("submission_kind") != SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        raise GameLifecycleError("Resolve target selection payload kind is invalid.")
    return _payload_string(payload, key="target_unit_instance_id")


def selected_attack_weapon_group_from_result(result: DecisionResult) -> GatheredAttackGroup:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Attack weapon group selection requires a DecisionResult.")
    payload = _payload_object(result.payload)
    if payload.get("submission_kind") != SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        raise GameLifecycleError("Attack weapon group selection payload kind is invalid.")
    gathered_payload = payload["gathered_group"]
    if not isinstance(gathered_payload, dict):
        raise GameLifecycleError("Attack weapon group payload must contain gathered_group.")
    return GatheredAttackGroup.from_payload(cast(GatheredAttackGroupPayload, gathered_payload))


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
        pool.selected_weapon_ability_ids,
        pool.shooting_type.value,
        pool.hit_roll_modifier,
        pool.targeting_rule_ids,
    )


def _pool_id(pool: RangedAttackPool) -> str:
    return (
        f"{pool.attacker_model_instance_id}:{pool.wargear_id}:"
        f"{pool.weapon_profile_id}:{pool.target_unit_instance_id}"
    )


def _resolve_target_option_id(target_unit_instance_id: str) -> str:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return f"resolve-target:{target_id}"


def _gathered_attack_group_from_indices(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    signature: IdenticalAttackSignature,
    pool_indices: tuple[int, ...],
) -> GatheredAttackGroup:
    _validate_pool_indices_within_attack_pools(
        field_name="Gathered attack pool_indices",
        pool_indices=pool_indices,
        attack_pools=attack_sequence.attack_pools,
    )
    contributions = tuple(
        _gathered_attack_contribution(
            pool_index=pool_index,
            pool=attack_sequence.attack_pools[pool_index],
        )
        for pool_index in pool_indices
    )
    total_attacks = sum(contribution.attacks for contribution in contributions)
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return GatheredAttackGroup(
        group_id=_gathered_attack_group_id(
            target_unit_instance_id=target_id,
            signature=signature,
            pool_indices=pool_indices,
        ),
        target_unit_instance_id=target_id,
        signature=signature,
        pool_indices=pool_indices,
        total_attacks=total_attacks,
        contributions=contributions,
    )


def _gathered_attack_contribution(
    *,
    pool_index: int,
    pool: RangedAttackPool,
) -> GatheredAttackContribution:
    return GatheredAttackContribution(
        pool_index=pool_index,
        attacker_model_instance_id=pool.attacker_model_instance_id,
        wargear_id=pool.wargear_id,
        weapon_profile_id=pool.weapon_profile_id,
        target_unit_instance_id=pool.target_unit_instance_id,
        attacks=pool.attacks,
        firing_deck_source_unit_instance_id=pool.firing_deck_source_unit_instance_id,
        firing_deck_source_model_instance_id=pool.firing_deck_source_model_instance_id,
    )


def _gathered_attack_group_id(
    *,
    target_unit_instance_id: str,
    signature: IdenticalAttackSignature,
    pool_indices: tuple[int, ...],
) -> str:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    indices = _validate_pool_index_tuple("GatheredAttackGroup pool_indices", pool_indices)
    encoded = canonical_json(
        {
            "target_unit_instance_id": target_id,
            "signature": signature.to_payload(),
            "pool_indices": list(indices),
        }
    ).encode("utf-8")
    return f"attack-group:{sha256(encoded).hexdigest()[:16]}"


def _synthetic_pool_for_gathered_group(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    gathered_group: GatheredAttackGroup,
) -> RangedAttackPool:
    _validate_pool_indices_within_attack_pools(
        field_name="GatheredAttackGroup pool_indices",
        pool_indices=gathered_group.pool_indices,
        attack_pools=attack_pools,
    )
    base_pool = attack_pools[gathered_group.primary_pool_index]
    wargear_id = base_pool.wargear_id
    weapon_profile = base_pool.weapon_profile
    weapon_profile_id = base_pool.weapon_profile_id
    if len(gathered_group.pool_indices) > 1:
        wargear_id = f"gathered-wargear:{gathered_group.group_id}"
        weapon_profile_id = f"gathered-profile:{gathered_group.group_id}"
        weapon_profile = replace(
            base_pool.weapon_profile,
            profile_id=weapon_profile_id,
            name=f"Gathered weapon pool {gathered_group.group_id}",
        )
    return RangedAttackPool(
        attacker_model_instance_id=base_pool.attacker_model_instance_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon_profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=gathered_group.target_unit_instance_id,
        shooting_type=base_pool.shooting_type,
        attacks=gathered_group.total_attacks,
        target_visible_model_ids=base_pool.target_visible_model_ids,
        target_in_range_model_ids=base_pool.target_in_range_model_ids,
        hit_roll_modifier=base_pool.hit_roll_modifier,
        targeting_rule_ids=base_pool.targeting_rule_ids,
        selected_weapon_ability_ids=base_pool.selected_weapon_ability_ids,
        firing_deck_source_unit_instance_id=base_pool.firing_deck_source_unit_instance_id,
        firing_deck_source_model_instance_id=base_pool.firing_deck_source_model_instance_id,
    )


def _first_unresolved_pool_index(attack_sequence: AttackSequence) -> int:
    return _first_unresolved_pool_index_from(
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
    )


def _first_unresolved_pool_index_from(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    used_pool_indices: tuple[int, ...],
) -> int:
    used = set(used_pool_indices)
    for pool_index in range(len(attack_pools)):
        if pool_index not in used:
            return pool_index
    return len(attack_pools)


def _first_unresolved_pool_index_for_target(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> int:
    return _first_unresolved_pool_index_for_target_from(
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
        target_unit_instance_id=target_unit_instance_id,
    )


def _first_unresolved_pool_index_for_target_from(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    used_pool_indices: tuple[int, ...],
    target_unit_instance_id: str,
) -> int:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    used = set(used_pool_indices)
    for pool_index, pool in enumerate(attack_pools):
        if pool_index not in used and pool.target_unit_instance_id == target_id:
            return pool_index
    raise GameLifecycleError("Target unit has no unresolved attack pools.")


def _weapon_rule_tokens_for_signature(profile: WeaponProfile) -> tuple[str, ...]:
    _validate_weapon_profile_signature_shape(profile)
    tokens: list[str] = [f"keyword:{keyword.value}" for keyword in profile.keywords]
    tokens.extend(
        f"ability:{canonical_json(ability.to_payload())}" for ability in profile.abilities
    )
    return tuple(sorted(tokens))


def _validate_weapon_profile_signature_shape(profile: WeaponProfile) -> None:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Identical attack signature requires a WeaponProfile.")
    ability_kinds = {ability.ability_kind for ability in profile.abilities}
    required_ability_kinds_by_keyword = {
        WeaponKeyword.SUSTAINED_HITS: AbilityKind.SUSTAINED_HITS,
        WeaponKeyword.LETHAL_HITS: AbilityKind.LETHAL_HITS,
        WeaponKeyword.RAPID_FIRE: AbilityKind.RAPID_FIRE,
        WeaponKeyword.MELTA: AbilityKind.MELTA,
        WeaponKeyword.CLEAVE: AbilityKind.CLEAVE,
        WeaponKeyword.HUNTER: AbilityKind.HUNTER,
        WeaponKeyword.DEVASTATING_WOUNDS: AbilityKind.DEVASTATING_WOUNDS,
        WeaponKeyword.HEAVY: AbilityKind.HEAVY,
    }
    for keyword, ability_kind in required_ability_kinds_by_keyword.items():
        if keyword in profile.keywords and ability_kind not in ability_kinds:
            raise GameLifecycleError(
                f"{keyword.value} requires a structured ability descriptor for identical attacks."
            )
    for ability in profile.abilities:
        if ability.ability_kind is AbilityKind.DEVASTATING_WOUNDS:
            devastating_wounds_resolution(profile)
            continue
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD:
            continue
        if ability.ability_kind in required_ability_kinds_by_keyword.values():
            continue
        raise GameLifecycleError("Unsupported weapon ability kind for identical attacks.")


def _validate_gathered_group_matches_attack_pools(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    used_pool_indices: tuple[int, ...],
    gathered_group: GatheredAttackGroup,
) -> None:
    _validate_pool_indices_within_attack_pools(
        field_name="GatheredAttackGroup pool_indices",
        pool_indices=gathered_group.pool_indices,
        attack_pools=attack_pools,
    )
    used = set(used_pool_indices)
    if any(pool_index in used for pool_index in gathered_group.pool_indices):
        raise GameLifecycleError("GatheredAttackGroup contains already used attack pools.")
    for contribution in gathered_group.contributions:
        pool = attack_pools[contribution.pool_index]
        expected = _gathered_attack_contribution(
            pool_index=contribution.pool_index,
            pool=pool,
        )
        if contribution != expected:
            raise GameLifecycleError("GatheredAttackGroup contribution pool drift.")
        if pool.target_unit_instance_id != gathered_group.target_unit_instance_id:
            raise GameLifecycleError("GatheredAttackGroup target pool drift.")
        if identical_attack_signature(pool) != gathered_group.signature:
            raise GameLifecycleError("GatheredAttackGroup signature drift.")


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


def _validate_pool_index_tuple(field_name: str, values: object) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    indices: list[int] = []
    seen: set[int] = set()
    for value in cast(tuple[object, ...], values):
        index = _validate_non_negative_int(f"{field_name} value", value)
        if index in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(index)
        indices.append(index)
    return tuple(sorted(indices))


def _validate_pool_indices_within_attack_pools(
    *,
    field_name: str,
    pool_indices: tuple[int, ...],
    attack_pools: tuple[RangedAttackPool, ...],
) -> None:
    _validate_pool_index_tuple(field_name, pool_indices)
    _validate_attack_pools(attack_pools)
    for pool_index in pool_indices:
        if pool_index >= len(attack_pools):
            raise GameLifecycleError(f"{field_name} contains an index outside attack_pools.")


def _validate_gathered_attack_contributions(
    values: object,
) -> tuple[GatheredAttackContribution, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GatheredAttackGroup contributions must be a tuple.")
    contributions: list[GatheredAttackContribution] = []
    seen: set[int] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not GatheredAttackContribution:
            raise GameLifecycleError(
                "GatheredAttackGroup contributions must contain gathered attack contributions."
            )
        if value.pool_index in seen:
            raise GameLifecycleError("GatheredAttackGroup contributions duplicate pool indices.")
        seen.add(value.pool_index)
        contributions.append(value)
    if not contributions:
        raise GameLifecycleError("GatheredAttackGroup contributions must not be empty.")
    return tuple(sorted(contributions, key=lambda contribution: contribution.pool_index))


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


def _validate_destroyed_transport_disembark_tuple(
    values: object,
) -> tuple[DestroyedTransportDisembark, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Destroyed Transport disembarks must be a tuple.")
    disembarks: list[DestroyedTransportDisembark] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestroyedTransportDisembark:
            raise GameLifecycleError(
                "Destroyed Transport disembarks must contain DestroyedTransportDisembark."
            )
        if value.unit_instance_id in seen:
            raise GameLifecycleError("Destroyed Transport disembarks duplicate units.")
        seen.add(value.unit_instance_id)
        disembarks.append(value)
    return tuple(disembarks)


def _validate_destruction_reaction_source_tuple(
    field_name: str,
    values: object,
) -> tuple[DestructionReactionSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    sources: list[DestructionReactionSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestructionReactionSource:
            raise GameLifecycleError(f"{field_name} must contain DestructionReactionSource.")
        if value.source_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sources)


def _validate_save_die_entry_tuple(values: object) -> tuple[SaveDieEntryPayload, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("PendingGroupedDamage sorted_save_dice must be a tuple.")
    entries: list[SaveDieEntryPayload] = []
    seen_context_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        entry = _validate_save_die_entry_payload(value)
        context_id = entry["attack_context"]["attack_context_id"]
        if context_id in seen_context_ids:
            raise GameLifecycleError("PendingGroupedDamage save dice must not duplicate attacks.")
        seen_context_ids.add(context_id)
        entries.append(entry)
    return tuple(entries)


def _validate_save_die_entry_payload(value: object) -> SaveDieEntryPayload:
    if not isinstance(value, dict):
        raise GameLifecycleError("Save die entry payload must be an object.")
    payload = validate_json_value(cast(JsonValue, value))
    if not isinstance(payload, dict):
        raise GameLifecycleError("Save die entry payload must be an object.")
    roll_state_payload = payload["roll_state"]
    if not isinstance(roll_state_payload, dict):
        raise GameLifecycleError("Save die entry roll_state must be an object.")
    roll_state = DiceRollState.from_payload(cast(DiceRollStatePayload, roll_state_payload))
    die_value = _validate_d6_value("Save die entry value", payload["value"])
    if die_value != roll_state.current_total:
        raise GameLifecycleError("Save die entry value must match roll_state.")
    attack_context_payload = payload["attack_context"]
    if not isinstance(attack_context_payload, dict):
        raise GameLifecycleError("Save die entry attack_context must be an object.")
    attack_context = cast(
        AttackResolutionContextPayload,
        validate_json_value(attack_context_payload),
    )
    _validate_identifier("Save die entry sequence_id", attack_context["sequence_id"])
    _validate_identifier("Save die entry attack_context_id", attack_context["attack_context_id"])
    _validate_non_negative_int("Save die entry pool_index", attack_context["pool_index"])
    _validate_non_negative_int("Save die entry attack_index", attack_context["attack_index"])
    _validate_non_negative_int(
        "Save die entry generated_hit_index",
        attack_context["generated_hit_index"],
    )
    return {
        "roll_state": roll_state.to_payload(),
        "value": die_value,
        "attack_context": attack_context,
    }


def _validate_allocation_group_payload_tuple(
    values: object,
) -> tuple[AllocationGroupPayload, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PendingGroupedDamage ordered_allocation_group_payloads must be a tuple."
        )
    group_payloads: list[AllocationGroupPayload] = []
    seen_group_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if not isinstance(value, dict):
            raise GameLifecycleError("PendingGroupedDamage allocation group must be an object.")
        payload = cast(AllocationGroupPayload, validate_json_value(cast(JsonValue, value)))
        group = AllocationGroup.from_payload(payload)
        if group.group_id in seen_group_ids:
            raise GameLifecycleError("PendingGroupedDamage allocation groups duplicate IDs.")
        seen_group_ids.add(group.group_id)
        group_payloads.append(group.to_payload())
    if not group_payloads:
        raise GameLifecycleError("PendingGroupedDamage allocation groups must not be empty.")
    return tuple(group_payloads)


def _validate_allocation_group_tuple(
    field_name: str,
    values: object,
) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    groups: list[AllocationGroup] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not AllocationGroup:
            raise GameLifecycleError(f"{field_name} must contain AllocationGroup values.")
        if value.group_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate group IDs.")
        seen.add(value.group_id)
        groups.append(value)
    return tuple(sorted(groups, key=lambda group: group.group_id))


def _validate_ordered_allocation_group_tuple(
    field_name: str,
    values: object,
) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    groups: list[AllocationGroup] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not AllocationGroup:
            raise GameLifecycleError(f"{field_name} must contain AllocationGroup values.")
        if value.group_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate group IDs.")
        seen.add(value.group_id)
        groups.append(value)
    if not groups:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(groups)


def _first_allocation_group(field_name: str, values: object) -> AllocationGroup:
    groups = _validate_ordered_allocation_group_tuple(field_name, values)
    for group in groups:
        return group
    raise GameLifecycleError(f"{field_name} must not be empty.")


def _first_allocation_group_order(
    field_name: str,
    values: tuple[tuple[AllocationGroup, ...], ...],
) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    for order in values:
        return _validate_ordered_allocation_group_tuple(field_name, order)
    raise GameLifecycleError(f"{field_name} must not be empty.")


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


def _nested_payload_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    return _payload_object(payload[key])


def _precision_selected_group_id(payload: JsonValue) -> str | None:
    value = _payload_object(payload).get("selected_group_id")
    if value is None:
        return None
    return _validate_identifier("Precision selected_group_id", value)


def _precision_selected_model_ids(payload: JsonValue) -> tuple[str, ...]:
    raw_ids = _payload_object(payload).get("selected_model_ids")
    if not isinstance(raw_ids, list):
        raise GameLifecycleError("Precision selected_model_ids must be a list.")
    return _validate_identifier_tuple(
        "Precision selected_model_ids",
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
    _validate_attack_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Feel No Pain",
    )


def _validate_grouped_request_context_matches_sequence(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    context_name: str,
) -> None:
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError(f"{context_name} attack context sequence drift.")
    if (
        battle_phase_kind_from_token(attack_context["source_phase"])
        is not attack_sequence.source_phase
    ):
        raise GameLifecycleError(f"{context_name} source phase drift.")
    if attack_context["attack_context_id"] != (
        f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:grouped"
    ):
        raise GameLifecycleError(f"{context_name} grouped attack context ID drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError(f"{context_name} pool index drift.")
    if attack_context["attack_index"] != 0:
        raise GameLifecycleError(f"{context_name} grouped attack index drift.")
    if attack_context["generated_hit_index"] != 0:
        raise GameLifecycleError(f"{context_name} grouped generated hit index drift.")


def _validate_attack_context_matches_sequence(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    context_name: str,
) -> None:
    if _attack_context_matches_pending_grouped_damage(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    ):
        return
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError(f"{context_name} attack context sequence drift.")
    if (
        battle_phase_kind_from_token(attack_context["source_phase"])
        is not attack_sequence.source_phase
    ):
        raise GameLifecycleError(f"{context_name} source phase drift.")
    if attack_context["attack_context_id"] != attack_sequence.attack_context_id():
        raise GameLifecycleError(f"{context_name} attack context ID drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError(f"{context_name} pool index drift.")
    if attack_context["attack_index"] != attack_sequence.attack_index:
        raise GameLifecycleError(f"{context_name} attack index drift.")
    if attack_context["generated_hit_index"] != attack_sequence.generated_hit_index:
        raise GameLifecycleError(f"{context_name} generated hit index drift.")


def _attack_context_matches_pending_grouped_damage(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> bool:
    pending = attack_sequence.pending_grouped_damage
    if pending is None:
        return False
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        return False
    if (
        battle_phase_kind_from_token(attack_context["source_phase"])
        is not attack_sequence.source_phase
    ):
        return False
    if attack_context["pool_index"] != attack_sequence.pool_index:
        return False
    if pending.next_index >= len(pending.sorted_save_dice):
        raise GameLifecycleError("Pending grouped damage has no current die.")
    current_context = pending.sorted_save_dice[pending.next_index]["attack_context"]
    return (
        attack_context["attack_context_id"] == current_context["attack_context_id"]
        and attack_context["source_phase"] == current_context["source_phase"]
        and attack_context["attack_index"] == current_context["attack_index"]
        and attack_context["generated_hit_index"] == current_context["generated_hit_index"]
    )


def _destruction_reaction_context_from_payload(
    payload: JsonValue,
) -> DestructionReactionContextPayload:
    raw = _payload_object(payload)
    if raw.get("context_kind") != "attack_sequence_model_destroyed":
        raise GameLifecycleError("Destruction reaction context kind is invalid.")
    attack_context = raw["attack_context"]
    if not isinstance(attack_context, dict):
        raise GameLifecycleError("Destruction reaction context attack_context must be an object.")
    return {
        "context_kind": "attack_sequence_model_destroyed",
        "attack_context": cast(AttackResolutionContextPayload, attack_context),
        "damage_application": validate_json_value(raw["damage_application"]),
        "model_destroyed_event_id": _payload_string(raw, key="model_destroyed_event_id"),
        "damage_event_id": _payload_string(raw, key="damage_event_id"),
        "target_unit_instance_id": _payload_string(raw, key="target_unit_instance_id"),
        "model_instance_id": _payload_string(raw, key="model_instance_id"),
        "destroyed_model_controller_player_id": _payload_string(
            raw,
            key="destroyed_model_controller_player_id",
        ),
        "source_phase": _payload_string(raw, key="source_phase"),
        "source_step": _payload_string(raw, key="source_step"),
        "removal_record": validate_json_value(raw["removal_record"]),
        "transition_batch": validate_json_value(raw["transition_batch"]),
        "destroyed_model_rules_triggered": _payload_bool(
            raw,
            key="destroyed_model_rules_triggered",
        ),
        "continuation": validate_json_value(raw["continuation"]),
    }


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


def _feel_no_pain_sources_for_attack(
    *,
    state: GameState,
    model_instance_id: str,
    attack_context: AttackResolutionContextPayload,
) -> tuple[FeelNoPainSource, ...]:
    sources = _state_feel_no_pain_sources(state=state, model_instance_id=model_instance_id)
    return tuple(
        source
        for source in sources
        if _feel_no_pain_source_applies_to_attack(
            source=source,
            attack_context=attack_context,
        )
    )


def _feel_no_pain_source_applies_to_attack(
    *,
    source: FeelNoPainSource,
    attack_context: AttackResolutionContextPayload,
) -> bool:
    if type(source) is not FeelNoPainSource:
        raise GameLifecycleError("Feel No Pain source filtering requires a source.")
    if source.attack_condition is None:
        return True
    if source.attack_condition is FeelNoPainAttackCondition.PSYCHIC_ATTACK:
        is_psychic_attack = attack_context["is_psychic_attack"]
        if type(is_psychic_attack) is not bool:
            raise GameLifecycleError("Attack context is_psychic_attack must be a bool.")
        return is_psychic_attack
    raise GameLifecycleError("Unsupported Feel No Pain attack condition.")


def _state_destruction_reaction_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[DestructionReactionSource, ...]:
    lookup = state.destruction_reaction_sources_for_model
    sources = lookup(model_instance_id=model_instance_id)
    if type(sources) is not tuple:
        raise GameLifecycleError("Destruction reaction source lookup must return a tuple.")
    for source in sources:
        if type(source) is not DestructionReactionSource:
            raise GameLifecycleError(
                "Destruction reaction source lookup returned an invalid source."
            )
    return sources


def _selected_destruction_reaction_source_from_request(
    *,
    request: DecisionRequest,
    selected_source_id: str | None,
) -> DestructionReactionSource | None:
    request_payload = _payload_object(request.payload)
    source_payloads = request_payload["sources"]
    if not isinstance(source_payloads, list):
        raise GameLifecycleError("Destruction reaction request sources must be a list.")
    sources = tuple(
        DestructionReactionSource.from_payload(
            cast(DestructionReactionSourcePayload, source_payload)
        )
        for source_payload in source_payloads
    )
    if selected_source_id is None:
        return None
    for source in sources:
        if source.source_id == selected_source_id:
            return source
    raise GameLifecycleError("Selected destruction reaction source is not in the request.")


def _destruction_reaction_action_host(source: DestructionReactionSource | None) -> str | None:
    if source is None:
        return None
    if source.reaction_kind is DestructionReactionKind.SHOOT_ON_DEATH:
        return BattlePhase.SHOOTING.value
    if source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH:
        return BattlePhase.FIGHT.value
    if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
        return "destruction_reaction"
    raise GameLifecycleError("Unsupported destruction reaction kind.")


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


def _optional_payload_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    if key not in payload:
        return None
    return _payload_string(payload, key=key)


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Attack sequence payload {key} must be an integer.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Attack sequence payload {key} must be a list.")
    strings: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Attack sequence payload {key} must contain strings.")
        strings.append(item)
    return tuple(strings)


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Attack sequence payload {key} must be a bool.")
    return value


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    return _validate_positive_int(key, payload[key])


def _payload_positive_number(payload: dict[str, JsonValue], *, key: str) -> float:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not int and type(value) is not float:
        raise GameLifecycleError(f"Attack sequence payload {key} must be a number.")
    if value <= 0:
        raise GameLifecycleError(f"Attack sequence payload {key} must be positive.")
    return float(value)


def _payload_identifier_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    raw_values = payload[key]
    if not isinstance(raw_values, list):
        raise GameLifecycleError(f"Attack sequence payload {key} must be a list.")
    return tuple(_validate_identifier(key, value) for value in raw_values)


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


def _validate_d6_value(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 1 and 6.")
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
    return tuple(identifiers)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    return value


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
