from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.attack_sequence import (
    ATTACK_ALLOCATION_DECISION_TYPES,
    ATTACK_RESOLUTION_SELECTION_DECISION_TYPES,
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackSequence,
    AttackSequencePayload,
    AttackSequenceStep,
    apply_allocation_order_decision,
    apply_attack_weapon_group_decision,
    apply_damage_allocation_model_decision,
    apply_destroyed_transport_disembark_proposal_decision,
    apply_destruction_reaction_decision,
    apply_feel_no_pain_decision,
    apply_precision_allocation_decision,
    apply_resolve_target_unit_decision,
    apply_source_backed_attack_dice_reroll_decision,
    build_select_attack_weapon_group_request,
    build_select_resolve_target_unit_request,
    gathered_attack_groups_for_target,
    is_destroyed_transport_disembark_proposal_request,
    resolve_attack_sequence_until_blocked,
    selected_attack_weapon_group_from_result,
    selected_resolve_target_from_result,
    unresolved_target_unit_ids,
    validate_psychic_attack_modifier_ignore_decision,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
)
from warhammer40k_core.engine.movement_proposals import PLACEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.ranged_rule_effects import (
    detection_range_bonus_inches_for_effects,
    hidden_unit_effect_ids,
    ranged_attacks_keep_hidden_by_effects,
    unit_is_hidden_by_effects,
    weapon_profile_with_character_target_ap_effects,
)
from warhammer40k_core.engine.ranged_weapon_keyword_effects import (
    weapon_profile_with_ranged_keyword_effects,
)
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindow as TriggeredReactionWindow,
)
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindowKind,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_end_surge_hooks import (
    ShootingEndSurgeContext,
    ShootingEndSurgeGrant,
    ShootingEndSurgeHookRegistry,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
    shooting_target_candidates_for_unit,
    shooting_visibility_cache_key,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_types import ShootingType, shooting_type_from_token
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantPayload,
    ShootingUnitSelectedGrantRegistry,
    ShootingUnitSelectedHookRegistry,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.transports import (
    FiringDeckWeaponSelection,
    resolve_firing_deck_selection,
)
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_abilities import (
    firing_deck_value_for_unit as unit_firing_deck_value,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    ASSAULT_RULE_ID,
    CLOSE_QUARTERS_RULE_ID,
    FIRE_OVERWATCH_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
    blast_attack_bonus,
    blast_rule_id,
    has_close_quarters_weapon_keyword,
    has_weapon_keyword,
    heavy_rule_id,
    melta_damage_bonus,
    melta_rule_id,
    rapid_fire_attack_bonus,
    rapid_fire_rule_id,
    weapon_ability_selection_request,
)
from warhammer40k_core.engine.weapon_declaration import (
    SHOOTING_DECLARATION_PROPOSAL_KIND,
    AvailableWeaponPayload,
    RangedAttackPool,
    RangedAttackPoolPayload,
    ShootingDeclarationProposal,
    ShootingDeclarationProposalRequest,
    ShootingProposalValidationResult,
    WeaponDeclaration,
    attacks_for_profile,
    shooting_declaration_missing_field,
    shooting_declaration_proposal_from_json,
    unresolved_attacks_for_validation,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import (
        GameState,
        OneShotWeaponUseRecord,
        RangedAttackHistoryRecord,
    )
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import (
        StratagemCatalogIndex,
        StratagemEligibilityContext,
    )


SELECT_SHOOTING_UNIT_DECISION_TYPE = "select_shooting_unit"
SELECT_SHOOTING_TYPE_DECISION_TYPE = "select_shooting_type"
SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE = "submit_shooting_declaration"
COMPLETE_SHOOTING_PHASE_OPTION_ID = "complete_shooting_phase"
_COMPLETE_SHOOTING_PHASE_STATUS = "shooting_phase_complete"


def _default_stratagem_index() -> StratagemCatalogIndex:
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index

    return eleventh_edition_stratagem_index()


class ShootingUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class ShootingTypeSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    shooting_type: str
    request_id: str
    result_id: str


class ShootingPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    phase_complete: bool
    selected_unit_ids: list[str]
    shot_unit_ids: list[str]
    skipped_unit_ids: list[str]
    active_selection: ShootingUnitSelectionPayload | None
    selected_shooting_type: ShootingTypeSelectionPayload | None
    attack_pools: list[RangedAttackPoolPayload]
    attack_sequence: AttackSequencePayload | None
    allocated_model_ids_this_phase: list[str]


class OutOfPhaseShootingStatePayload(TypedDict):
    battle_round: int
    player_id: str
    parent_phase: str
    source_rule_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    source_context: JsonValue
    selected_unit_instance_id: str
    target_unit_ids: list[str] | None
    grant_effect_ids: list[str]
    attack_pools: list[RangedAttackPoolPayload]
    attack_sequence: AttackSequencePayload | None
    allocated_model_ids: list[str]


class ShootingDeclarationProposalRequestPayload(TypedDict):
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
    selected_shooting_type: str | None
    ruleset_descriptor_hash: str
    visibility_cache_key: str
    firing_deck_value: int | None
    available_weapons: list[AvailableWeaponPayload]
    target_candidates: list[JsonValue]


class ShootingDeclarationDecisionPayload(TypedDict):
    proposal_request: ShootingDeclarationProposalRequestPayload


class _AvailableWeapon(TypedDict):
    model_instance_id: str
    wargear_id: str
    weapon_profile: WeaponProfile
    firing_deck_source_unit_instance_id: NotRequired[str]
    firing_deck_source_model_instance_id: NotRequired[str]


type _ShootingUnitCandidateCacheKey = tuple[str, str, str, str, str]
type _ShootingModelCandidateCacheKey = tuple[
    str,
    str,
    str,
    str | None,
    str | None,
    str,
    str,
    bool,
    bool,
    int,
]
type _ShootingModelCandidateCache = dict[
    _ShootingModelCandidateCacheKey,
    ShootingTargetCandidate,
]


@dataclass(frozen=True, slots=True)
class ShootingUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ShootingUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ShootingUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ShootingUnitSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ShootingUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ShootingUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> ShootingUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ShootingUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class ShootingTypeSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    shooting_type: ShootingType
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ShootingTypeSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ShootingTypeSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ShootingTypeSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "shooting_type",
            shooting_type_from_token(self.shooting_type),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ShootingTypeSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ShootingTypeSelection result_id", self.result_id),
        )

    def to_payload(self) -> ShootingTypeSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "shooting_type": self.shooting_type.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ShootingTypeSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            shooting_type=shooting_type_from_token(payload["shooting_type"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class ShootingPhaseState:
    battle_round: int
    active_player_id: str
    phase_complete: bool = False
    selected_unit_ids: tuple[str, ...] = ()
    shot_unit_ids: tuple[str, ...] = ()
    skipped_unit_ids: tuple[str, ...] = ()
    active_selection: ShootingUnitSelection | None = None
    selected_shooting_type: ShootingTypeSelection | None = None
    attack_pools: tuple[RangedAttackPool, ...] = ()
    attack_sequence: AttackSequence | None = None
    allocated_model_ids_this_phase: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ShootingPhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("ShootingPhaseState active_player_id", self.active_player_id),
        )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("ShootingPhaseState phase_complete must be a bool.")
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "ShootingPhaseState selected_unit_ids",
                self.selected_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "shot_unit_ids",
            _validate_identifier_tuple("ShootingPhaseState shot_unit_ids", self.shot_unit_ids),
        )
        object.__setattr__(
            self,
            "skipped_unit_ids",
            _validate_identifier_tuple(
                "ShootingPhaseState skipped_unit_ids",
                self.skipped_unit_ids,
            ),
        )
        if set(self.skipped_unit_ids) & set(self.shot_unit_ids):
            raise GameLifecycleError("Shooting skipped units must not also count as shot.")
        if self.active_selection is not None:
            if type(self.active_selection) is not ShootingUnitSelection:
                raise GameLifecycleError(
                    "ShootingPhaseState active_selection must be ShootingUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError("Shooting active_selection active player drift.")
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError("Shooting active_selection battle round drift.")
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError("Shooting active_selection must be selected.")
            if self.active_selection.unit_instance_id in self.shot_unit_ids:
                raise GameLifecycleError("Shooting active_selection has already shot.")
            if self.active_selection.unit_instance_id in self.skipped_unit_ids:
                raise GameLifecycleError("Shooting active_selection has already been skipped.")
        if self.selected_shooting_type is not None:
            if type(self.selected_shooting_type) is not ShootingTypeSelection:
                raise GameLifecycleError(
                    "ShootingPhaseState selected_shooting_type must be ShootingTypeSelection."
                )
            if self.active_selection is None:
                raise GameLifecycleError(
                    "Shooting selected_shooting_type requires active_selection."
                )
            if self.selected_shooting_type.player_id != self.active_player_id:
                raise GameLifecycleError("Shooting selected_shooting_type active player drift.")
            if self.selected_shooting_type.battle_round != self.battle_round:
                raise GameLifecycleError("Shooting selected_shooting_type battle round drift.")
            if (
                self.selected_shooting_type.unit_instance_id
                != self.active_selection.unit_instance_id
            ):
                raise GameLifecycleError("Shooting selected_shooting_type unit drift.")
        object.__setattr__(
            self,
            "attack_pools",
            _validate_attack_pools(self.attack_pools),
        )
        if self.attack_sequence is not None:
            if type(self.attack_sequence) is not AttackSequence:
                raise GameLifecycleError(
                    "ShootingPhaseState attack_sequence must be an AttackSequence."
                )
            if self.active_selection is not None:
                raise GameLifecycleError("Shooting attack_sequence requires no active_selection.")
        object.__setattr__(
            self,
            "allocated_model_ids_this_phase",
            _validate_identifier_tuple(
                "ShootingPhaseState allocated_model_ids_this_phase",
                self.allocated_model_ids_this_phase,
            ),
        )
        if self.phase_complete and self.active_selection is not None:
            raise GameLifecycleError("Completed Shooting phase cannot have active_selection.")
        if self.phase_complete and self.attack_sequence is not None:
            raise GameLifecycleError("Completed Shooting phase cannot have attack_sequence.")

    def with_unit_selection(self, selection: ShootingUnitSelection) -> Self:
        if type(selection) is not ShootingUnitSelection:
            raise GameLifecycleError("Shooting selection must be ShootingUnitSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a shooting unit after phase completion.")
        if self.active_selection is not None:
            raise GameLifecycleError("Shooting unit selection requires no active selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Shooting selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Shooting selection battle round drift.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Shooting unit was already selected.")
        if selection.unit_instance_id in self.shot_unit_ids:
            raise GameLifecycleError("Shooting unit has already shot.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=selection,
            selected_shooting_type=None,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_shooting_type_selection(self, selection: ShootingTypeSelection) -> Self:
        if type(selection) is not ShootingTypeSelection:
            raise GameLifecycleError("Shooting type selection must be ShootingTypeSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a shooting type after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Shooting type selection requires active_selection.")
        if self.selected_shooting_type is not None:
            raise GameLifecycleError("Shooting type has already been selected.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Shooting type selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Shooting type selection battle round drift.")
        if selection.unit_instance_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Shooting type selection unit drift.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=self.active_selection,
            selected_shooting_type=selection,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_declaration(
        self,
        *,
        attack_pools: tuple[RangedAttackPool, ...],
        ineligible_unit_instance_ids: tuple[str, ...] = (),
        attack_sequence: AttackSequence | None = None,
    ) -> Self:
        if self.phase_complete:
            raise GameLifecycleError("Cannot record shooting declaration after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Shooting declaration requires active_selection.")
        if self.selected_shooting_type is None:
            raise GameLifecycleError("Shooting declaration requires selected_shooting_type.")
        for pool in attack_pools:
            if type(pool) is not RangedAttackPool:
                raise GameLifecycleError("Shooting declaration attack_pools must be attack pools.")
            if pool.shooting_type is not self.selected_shooting_type.shooting_type:
                raise GameLifecycleError("Shooting declaration attack pool type drift.")
        if attack_sequence is not None:
            if type(attack_sequence) is not AttackSequence:
                raise GameLifecycleError("Shooting declaration attack_sequence is invalid.")
            if attack_sequence.attack_pools != attack_pools:
                raise GameLifecycleError("Shooting declaration attack_sequence pool drift.")
            if attack_sequence.attacking_unit_instance_id != self.active_selection.unit_instance_id:
                raise GameLifecycleError("Shooting declaration attack_sequence unit drift.")
        ineligible_ids = _validate_identifier_tuple(
            "ineligible_unit_instance_ids",
            ineligible_unit_instance_ids,
        )
        completed_unit_id = self.active_selection.unit_instance_id
        shot_unit_ids = tuple(sorted({*self.shot_unit_ids, completed_unit_id, *ineligible_ids}))
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=None,
            selected_shooting_type=None,
            attack_pools=(*self.attack_pools, *attack_pools),
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_attack_sequence_update(
        self,
        *,
        attack_sequence: AttackSequence | None,
        allocated_model_ids_this_phase: tuple[str, ...],
    ) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=self.phase_complete,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=self.active_selection,
            selected_shooting_type=self.selected_shooting_type,
            attack_pools=self.attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids_this_phase,
        )

    def with_phase_complete(self, *, skipped_unit_ids: tuple[str, ...] = ()) -> Self:
        if self.active_selection is not None:
            raise GameLifecycleError("Shooting completion requires no active selection.")
        if self.selected_shooting_type is not None:
            raise GameLifecycleError("Shooting completion requires no selected shooting type.")
        if self.attack_sequence is not None:
            raise GameLifecycleError("Shooting completion requires no active attack sequence.")
        skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=True,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=tuple(sorted({*self.skipped_unit_ids, *skipped_ids})),
            active_selection=None,
            selected_shooting_type=None,
            attack_pools=self.attack_pools,
            attack_sequence=None,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def to_payload(self) -> ShootingPhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase_complete": self.phase_complete,
            "selected_unit_ids": list(self.selected_unit_ids),
            "shot_unit_ids": list(self.shot_unit_ids),
            "skipped_unit_ids": list(self.skipped_unit_ids),
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
            "selected_shooting_type": (
                None
                if self.selected_shooting_type is None
                else self.selected_shooting_type.to_payload()
            ),
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "attack_sequence": (
                None if self.attack_sequence is None else self.attack_sequence.to_payload()
            ),
            "allocated_model_ids_this_phase": list(self.allocated_model_ids_this_phase),
        }

    @classmethod
    def from_payload(cls, payload: ShootingPhaseStatePayload) -> Self:
        active_selection = payload["active_selection"]
        selected_shooting_type = payload["selected_shooting_type"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase_complete=payload["phase_complete"],
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            shot_unit_ids=tuple(payload["shot_unit_ids"]),
            skipped_unit_ids=tuple(payload["skipped_unit_ids"]),
            active_selection=(
                None
                if active_selection is None
                else ShootingUnitSelection.from_payload(active_selection)
            ),
            selected_shooting_type=(
                None
                if selected_shooting_type is None
                else ShootingTypeSelection.from_payload(selected_shooting_type)
            ),
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            attack_sequence=(
                None
                if payload["attack_sequence"] is None
                else AttackSequence.from_payload(payload["attack_sequence"])
            ),
            allocated_model_ids_this_phase=tuple(payload["allocated_model_ids_this_phase"]),
        )


@dataclass(frozen=True, slots=True)
class OutOfPhaseShootingState:
    battle_round: int
    player_id: str
    parent_phase: BattlePhase
    source_rule_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    source_context: JsonValue
    selected_unit_instance_id: str
    target_unit_ids: tuple[str, ...] | None = None
    grant_effect_ids: tuple[str, ...] = ()
    attack_pools: tuple[RangedAttackPool, ...] = ()
    attack_sequence: AttackSequence | None = None
    allocated_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("OutOfPhaseShootingState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("OutOfPhaseShootingState player_id", self.player_id),
        )
        object.__setattr__(self, "parent_phase", battle_phase_kind_from_token(self.parent_phase))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("OutOfPhaseShootingState source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "OutOfPhaseShootingState source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "OutOfPhaseShootingState source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(self, "source_context", validate_json_value(self.source_context))
        object.__setattr__(
            self,
            "selected_unit_instance_id",
            _validate_identifier(
                "OutOfPhaseShootingState selected_unit_instance_id",
                self.selected_unit_instance_id,
            ),
        )
        if self.target_unit_ids is not None:
            object.__setattr__(
                self,
                "target_unit_ids",
                _validate_identifier_tuple(
                    "OutOfPhaseShootingState target_unit_ids",
                    self.target_unit_ids,
                ),
            )
        object.__setattr__(
            self,
            "grant_effect_ids",
            _validate_identifier_tuple(
                "OutOfPhaseShootingState grant_effect_ids",
                self.grant_effect_ids,
            ),
        )
        object.__setattr__(self, "attack_pools", _validate_attack_pools(self.attack_pools))
        if self.attack_sequence is not None:
            if type(self.attack_sequence) is not AttackSequence:
                raise GameLifecycleError(
                    "OutOfPhaseShootingState attack_sequence must be an AttackSequence."
                )
            if self.attack_sequence.attack_pools != self.attack_pools:
                raise GameLifecycleError("Out-of-phase attack_sequence pool drift.")
            if self.attack_sequence.attacking_unit_instance_id != self.selected_unit_instance_id:
                raise GameLifecycleError("Out-of-phase attack_sequence unit drift.")
        object.__setattr__(
            self,
            "allocated_model_ids",
            _validate_identifier_tuple(
                "OutOfPhaseShootingState allocated_model_ids",
                self.allocated_model_ids,
            ),
        )

    def with_declaration(
        self,
        *,
        attack_pools: tuple[RangedAttackPool, ...],
        attack_sequence: AttackSequence,
    ) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            player_id=self.player_id,
            parent_phase=self.parent_phase,
            source_rule_id=self.source_rule_id,
            source_decision_request_id=self.source_decision_request_id,
            source_decision_result_id=self.source_decision_result_id,
            source_context=self.source_context,
            selected_unit_instance_id=self.selected_unit_instance_id,
            target_unit_ids=self.target_unit_ids,
            grant_effect_ids=self.grant_effect_ids,
            attack_pools=attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids=self.allocated_model_ids,
        )

    def with_grant_effect_ids(self, grant_effect_ids: tuple[str, ...]) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            player_id=self.player_id,
            parent_phase=self.parent_phase,
            source_rule_id=self.source_rule_id,
            source_decision_request_id=self.source_decision_request_id,
            source_decision_result_id=self.source_decision_result_id,
            source_context=self.source_context,
            selected_unit_instance_id=self.selected_unit_instance_id,
            target_unit_ids=self.target_unit_ids,
            grant_effect_ids=grant_effect_ids,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids=self.allocated_model_ids,
        )

    def with_attack_sequence_update(
        self,
        *,
        attack_sequence: AttackSequence | None,
        allocated_model_ids: tuple[str, ...],
    ) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            player_id=self.player_id,
            parent_phase=self.parent_phase,
            source_rule_id=self.source_rule_id,
            source_decision_request_id=self.source_decision_request_id,
            source_decision_result_id=self.source_decision_result_id,
            source_context=self.source_context,
            selected_unit_instance_id=self.selected_unit_instance_id,
            target_unit_ids=self.target_unit_ids,
            grant_effect_ids=self.grant_effect_ids,
            attack_pools=self.attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )

    def to_payload(self) -> OutOfPhaseShootingStatePayload:
        return {
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "parent_phase": self.parent_phase.value,
            "source_rule_id": self.source_rule_id,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "source_context": self.source_context,
            "selected_unit_instance_id": self.selected_unit_instance_id,
            "target_unit_ids": None if self.target_unit_ids is None else list(self.target_unit_ids),
            "grant_effect_ids": list(self.grant_effect_ids),
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "attack_sequence": (
                None if self.attack_sequence is None else self.attack_sequence.to_payload()
            ),
            "allocated_model_ids": list(self.allocated_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: OutOfPhaseShootingStatePayload) -> Self:
        target_unit_ids = payload["target_unit_ids"]
        return cls(
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            parent_phase=battle_phase_kind_from_token(payload["parent_phase"]),
            source_rule_id=payload["source_rule_id"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            source_context=payload["source_context"],
            selected_unit_instance_id=payload["selected_unit_instance_id"],
            target_unit_ids=None if target_unit_ids is None else tuple(target_unit_ids),
            grant_effect_ids=tuple(payload["grant_effect_ids"]),
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            attack_sequence=(
                None
                if payload["attack_sequence"] is None
                else AttackSequence.from_payload(payload["attack_sequence"])
            ),
            allocated_model_ids=tuple(payload["allocated_model_ids"]),
        )


@dataclass(frozen=True, slots=True)
class ShootingPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None
    army_catalog: ArmyCatalog | None = None
    stratagem_index: StratagemCatalogIndex = field(default_factory=_default_stratagem_index)
    shooting_unit_selected_hooks: ShootingUnitSelectedHookRegistry = field(
        default_factory=ShootingUnitSelectedHookRegistry.empty
    )
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry = field(
        default_factory=ShootingUnitSelectedGrantRegistry.empty
    )
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry = field(
        default_factory=ShootingTargetRestrictionHookRegistry.empty
    )
    shooting_end_surge_hooks: ShootingEndSurgeHookRegistry = field(
        default_factory=ShootingEndSurgeHookRegistry.empty
    )
    attack_sequence_completed_hooks: AttackSequenceCompletedHookRegistry = field(
        default_factory=AttackSequenceCompletedHookRegistry.empty
    )
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry = field(
        default_factory=StratagemCostModifierRegistry.empty
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "ShootingPhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )
        if self.army_catalog is not None and type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("ShootingPhaseHandler army_catalog must be an ArmyCatalog.")
        from warhammer40k_core.engine.stratagems import StratagemCatalogIndex

        if type(self.stratagem_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("ShootingPhaseHandler stratagem_index must be an index.")
        if type(self.shooting_unit_selected_hooks) is not ShootingUnitSelectedHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_unit_selected_hooks must be a registry."
            )
        if type(self.shooting_unit_selected_grant_hooks) is not ShootingUnitSelectedGrantRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_unit_selected_grant_hooks must be a registry."
            )
        if type(self.shooting_target_restriction_hooks) is not (
            ShootingTargetRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_target_restriction_hooks must be a registry."
            )
        if type(self.shooting_end_surge_hooks) is not ShootingEndSurgeHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_end_surge_hooks must be a registry."
            )
        if type(self.attack_sequence_completed_hooks) is not AttackSequenceCompletedHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler attack_sequence_completed_hooks must be a registry."
            )
        if type(self.stratagem_cost_modifier_registry) is not StratagemCostModifierRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler stratagem_cost_modifier_registry must be a registry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler runtime_modifier_registry must be a registry."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.SHOOTING

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        del reaction_queue
        _validate_shooting_phase_state(state)
        shooting_state = _ensure_shooting_phase_state(state=state)
        if shooting_state.attack_sequence is not None:
            completed_candidate = shooting_state.attack_sequence
            target_stratagem_status = _request_after_unit_selected_as_target_stratagem_if_available(
                state=state,
                decisions=decisions,
                stratagem_index=self.stratagem_index,
                stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
                attack_sequence=shooting_state.attack_sequence,
            )
            if target_stratagem_status is not None:
                return target_stratagem_status
            attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
                state=state,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                attack_sequence=shooting_state.attack_sequence,
                already_allocated_model_ids=shooting_state.allocated_model_ids_this_phase,
                stratagem_index=self.stratagem_index,
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
            shooting_state = shooting_state.with_attack_sequence_update(
                attack_sequence=attack_sequence,
                allocated_model_ids_this_phase=allocated_model_ids,
            )
            state.shooting_phase_state = shooting_state
            if status is not None:
                return status
            if attack_sequence is None:
                completion_hook_status = (
                    self.attack_sequence_completed_hooks.resolve_completed_sequence(
                        AttackSequenceCompletedContext(
                            state=state,
                            decisions=decisions,
                            dice_manager=DiceRollManager(
                                state.game_id,
                                event_log=decisions.event_log,
                            ),
                            runtime_modifier_registry=self.runtime_modifier_registry,
                            source_phase=BattlePhase.SHOOTING,
                            attack_sequence=completed_candidate,
                            attack_sequence_completed_event_id=(
                                attack_sequence_completed_event_id(
                                    decisions=decisions,
                                    attack_sequence=completed_candidate,
                                )
                            ),
                        )
                    )
                )
                if completion_hook_status is not None:
                    return completion_hook_status
                stratagem_status = _request_friendly_unit_has_shot_stratagem_if_available(
                    state=state,
                    decisions=decisions,
                    stratagem_index=self.stratagem_index,
                    stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
                    completed_sequence=completed_candidate,
                )
                if stratagem_status is not None:
                    return stratagem_status
                enemy_stratagem_status = _request_enemy_unit_has_shot_stratagem_if_available(
                    state=state,
                    decisions=decisions,
                    stratagem_index=self.stratagem_index,
                    stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
                    completed_sequence=completed_candidate,
                )
                if enemy_stratagem_status is not None:
                    return enemy_stratagem_status
                surge_status = _request_shooting_end_surge_if_available(
                    state=state,
                    decisions=decisions,
                    registry=self.shooting_end_surge_hooks,
                    completed_sequence=completed_candidate,
                )
                if surge_status is not None:
                    return surge_status
        if shooting_state.phase_complete:
            decisions.event_log.append(
                "shooting_phase_completed",
                _shooting_phase_status_payload(
                    state=state,
                    phase_body_status="complete",
                    skipped_unit_ids=shooting_state.skipped_unit_ids,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_shooting_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                    skipped_unit_ids=shooting_state.skipped_unit_ids,
                ),
            )
        if (
            shooting_state.active_selection is not None
            and shooting_state.selected_shooting_type is None
        ):
            return _request_shooting_type_selection(
                state=state,
                decisions=decisions,
                shooting_state=shooting_state,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
        if (
            shooting_state.active_selection is not None
            and shooting_state.selected_shooting_type is not None
        ):
            return _request_shooting_declaration(
                state=state,
                decisions=decisions,
                active_selection=shooting_state.active_selection,
                selected_shooting_type=shooting_state.selected_shooting_type.shooting_type,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )

        active_stratagem_status = _request_active_shooting_phase_stratagem_if_available(
            state=state,
            decisions=decisions,
            shooting_state=shooting_state,
            stratagem_index=self.stratagem_index,
            stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
        )
        if active_stratagem_status is not None:
            return active_stratagem_status

        legal_unit_ids = _legal_shooting_unit_ids(
            state=state,
            shooting_state=shooting_state,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
            shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
        )
        if not legal_unit_ids:
            state.shooting_phase_state = shooting_state.with_phase_complete()
            decisions.event_log.append(
                "shooting_phase_completed",
                _shooting_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_shooting_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                ),
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_SHOOTING_UNIT_DECISION_TYPE,
            actor_id=_active_player_id(state),
            payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": _active_player_id(state),
            },
            options=_shooting_unit_options(
                state=state,
                unit_ids=legal_unit_ids,
                include_complete=True,
            ),
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "legal_unit_count": len(legal_unit_ids),
            },
        )

    def advance_out_of_phase_shooting_if_needed(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        out_of_phase_state = state.out_of_phase_shooting_state
        if out_of_phase_state is None:
            return None
        if out_of_phase_state.attack_sequence is None:
            if out_of_phase_state.attack_pools:
                return _complete_out_of_phase_shooting(
                    state=state,
                    decisions=decisions,
                    completed_state=out_of_phase_state,
                )
            return None
        completed_candidate = out_of_phase_state.attack_sequence
        attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            attack_sequence=out_of_phase_state.attack_sequence,
            already_allocated_model_ids=out_of_phase_state.allocated_model_ids,
            stratagem_index=self.stratagem_index,
            runtime_modifier_registry=self.runtime_modifier_registry,
        )
        state.out_of_phase_shooting_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )
        if status is not None:
            return status
        completed_state = state.out_of_phase_shooting_state
        if completed_state.attack_sequence is not None:
            raise GameLifecycleError("Out-of-phase shooting completion state drift.")
        completion_hook_status = self.attack_sequence_completed_hooks.resolve_completed_sequence(
            AttackSequenceCompletedContext(
                state=state,
                decisions=decisions,
                dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
                runtime_modifier_registry=self.runtime_modifier_registry,
                source_phase=completed_candidate.source_phase,
                attack_sequence=completed_candidate,
                attack_sequence_completed_event_id=attack_sequence_completed_event_id(
                    decisions=decisions,
                    attack_sequence=completed_candidate,
                ),
            )
        )
        if completion_hook_status is not None:
            return completion_hook_status
        return _complete_out_of_phase_shooting(
            state=state,
            decisions=decisions,
            completed_state=completed_state,
        )

    def invalid_declaration_submission_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        del decisions
        if request.decision_type != SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            raise GameLifecycleError("Shooting prevalidation received unsupported decision_type.")
        missing = shooting_declaration_missing_field(result.payload)
        proposal_request = _proposal_request_from_decision_request(request)
        if missing is not None:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=ShootingProposalValidationResult.invalid(
                    proposal_request_id=proposal_request.request_id,
                    violation_code="proposal_payload_missing_field",
                    message=f"Shooting declaration proposal missing {missing}.",
                    field=missing,
                ),
                message="Shooting declaration proposal is malformed.",
            )
        try:
            proposal = shooting_declaration_proposal_from_json(result.payload)
        except GameLifecycleError as exc:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=ShootingProposalValidationResult.invalid(
                    proposal_request_id=proposal_request.request_id,
                    violation_code="proposal_schema_invalid",
                    message=str(exc),
                    field=None,
                ),
                message="Shooting declaration proposal is schema-invalid.",
            )
        proposal_validation = proposal.validation_result_for_request(proposal_request)
        if not proposal_validation.is_valid:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=proposal_validation,
                message="Shooting declaration proposal does not match the pending request.",
            )
        rule_validation = _validate_declaration_submission(
            state=state,
            proposal=proposal,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
            shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            runtime_modifier_registry=self.runtime_modifier_registry,
        )
        if not rule_validation.is_valid:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=rule_validation,
                message="Shooting declaration proposal is not currently legal.",
            )
        return None

    def invalid_shooting_type_selection_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type != SELECT_SHOOTING_TYPE_DECISION_TYPE:
            raise GameLifecycleError(
                "Shooting type prevalidation received unsupported decision_type."
            )
        shooting_state = state.shooting_phase_state
        if shooting_state is None or shooting_state.active_selection is None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting type selection requires an active shooting unit.",
                payload={"invalid_reason": "shooting_type_wrong_context"},
            )
        payload = _decision_payload_object(result.payload)
        unit_instance_id = _payload_string(payload, key="unit_instance_id")
        if unit_instance_id != shooting_state.active_selection.unit_instance_id:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting type selection unit drifted.",
                payload={"invalid_reason": "shooting_type_unit_drift"},
            )
        shooting_type = shooting_type_from_token(_payload_string(payload, key="shooting_type"))
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
        legal_types = _legal_shooting_types_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
            shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
        )
        if shooting_type not in legal_types:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting type selection is no longer legal.",
                payload={
                    "invalid_reason": "shooting_type_option_drift",
                    "unit_instance_id": unit_instance_id,
                    "shooting_type": shooting_type.value,
                    "legal_shooting_types": [legal.value for legal in legal_types],
                },
            )
        return None

    def invalid_shooting_unit_selected_grant_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type != SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
            raise GameLifecycleError(
                "Shooting unit grant prevalidation received unsupported decision_type."
            )
        try:
            result.validate_for_request(request)
            selection = _active_shooting_unit_selection(state)
            payload = _decision_payload_object(result.payload)
            _validate_shooting_unit_selected_grant_payload_context(
                payload=payload,
                selection=selection,
            )
            if result.selected_option_id == DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID:
                if _selected_shooting_unit_grants_from_payload(payload):
                    return LifecycleStatus.invalid(
                        stage=state.stage,
                        message="Declined shooting unit grant cannot carry selected grants.",
                        payload={
                            "invalid_reason": "shooting_unit_grant_decline_payload_drift",
                            "unit_instance_id": selection.unit_instance_id,
                        },
                    )
                return None
            selected_grants = _selected_shooting_unit_grants_from_payload(payload)
            _validate_selected_shooting_unit_grants(
                state=state,
                selection=selection,
                registry=self.shooting_unit_selected_grant_hooks,
                selected_grants=selected_grants,
            )
        except (DecisionError, GameLifecycleError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting unit grant result is invalid.",
                payload={
                    "invalid_reason": "shooting_unit_grant_invalid",
                    "detail": str(exc),
                },
            )
        return None

    def invalid_attack_sequence_selection_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type not in ATTACK_RESOLUTION_SELECTION_DECISION_TYPES:
            raise GameLifecycleError(
                "Attack sequence selection prevalidation received unsupported decision_type."
            )
        try:
            result.validate_for_request(request)
        except DecisionError as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Attack sequence selection result is malformed.",
                payload={
                    "invalid_reason": "attack_sequence_selection_malformed",
                    "detail": str(exc),
                },
            )
        attack_sequence = _attack_sequence_for_selection_request(state=state, request=request)
        if request.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
            selected_target_id = selected_resolve_target_from_result(result)
            if selected_target_id not in unresolved_target_unit_ids(attack_sequence):
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Resolve target selection is no longer legal.",
                    payload={
                        "invalid_reason": "resolve_target_option_drift",
                        "selected_target_unit_instance_id": selected_target_id,
                    },
                )
            expected_request = build_select_resolve_target_unit_request(
                request_id=request.request_id,
                state=state,
                attack_sequence=attack_sequence,
            )
            return _invalid_if_current_option_payload_drifted(
                state=state,
                result=result,
                expected_request=expected_request,
                invalid_reason="resolve_target_payload_drift",
            )
        selected_group = selected_attack_weapon_group_from_result(result)
        if (
            attack_sequence.selected_target_unit_instance_id
            != selected_group.target_unit_instance_id
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Attack weapon group target context drifted.",
                payload={
                    "invalid_reason": "attack_group_target_drift",
                    "selected_target_unit_instance_id": selected_group.target_unit_instance_id,
                },
            )
        current_groups = gathered_attack_groups_for_target(
            attack_sequence=attack_sequence,
            target_unit_instance_id=selected_group.target_unit_instance_id,
        )
        if selected_group.group_id not in {group.group_id for group in current_groups}:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Attack weapon group selection is no longer legal.",
                payload={
                    "invalid_reason": "attack_group_option_drift",
                    "selected_group_id": selected_group.group_id,
                },
            )
        expected_request = build_select_attack_weapon_group_request(
            request_id=request.request_id,
            state=state,
            attack_sequence=attack_sequence,
            target_unit_instance_id=selected_group.target_unit_instance_id,
        )
        return _invalid_if_current_option_payload_drifted(
            state=state,
            result=result,
            expected_request=expected_request,
            invalid_reason="attack_group_payload_drift",
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        if result.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
            return _apply_shooting_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_unit_selected_hooks=self.shooting_unit_selected_hooks,
                shooting_unit_selected_grant_hooks=self.shooting_unit_selected_grant_hooks,
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
        if result.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
            return _apply_shooting_unit_selected_grant_decision(
                state=state,
                result=result,
                decisions=decisions,
                registry=self.shooting_unit_selected_grant_hooks,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
        if result.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE:
            _apply_shooting_type_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
            return None
        if result.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            _apply_shooting_declaration_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
            return None
        if result.decision_type in ATTACK_RESOLUTION_SELECTION_DECISION_TYPES:
            _apply_attack_sequence_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
            return None
        if result.decision_type in ATTACK_ALLOCATION_DECISION_TYPES:
            return _apply_attack_sequence_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                stratagem_index=self.stratagem_index,
            )
        if result.decision_type == DICE_REROLL_DECISION_TYPE:
            return _apply_shooting_dice_reroll_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
        if result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_attack_sequence_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                stratagem_index=self.stratagem_index,
            )
        raise GameLifecycleError("ShootingPhaseHandler received unsupported decision_type.")


def _complete_out_of_phase_shooting(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_state: OutOfPhaseShootingState,
) -> LifecycleStatus:
    if type(completed_state) is not OutOfPhaseShootingState:
        raise GameLifecycleError("Out-of-phase shooting completion requires state.")
    if completed_state.attack_sequence is not None:
        raise GameLifecycleError("Out-of-phase shooting completion requires no sequence.")
    removed_grant_effects = (
        state.remove_persisting_effects_by_id(completed_state.grant_effect_ids)
        if completed_state.grant_effect_ids
        else ()
    )
    decisions.event_log.append(
        "out_of_phase_shooting_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "player_id": completed_state.player_id,
            "parent_phase": completed_state.parent_phase.value,
            "source_rule_id": completed_state.source_rule_id,
            "selected_unit_instance_id": completed_state.selected_unit_instance_id,
            "removed_grant_effects": [effect.to_payload() for effect in removed_grant_effects],
        },
    )
    state.out_of_phase_shooting_state = None
    return LifecycleStatus.advanced(
        stage=GameLifecycleStage.BATTLE,
        payload={
            "phase": completed_state.parent_phase.value,
            "phase_body_status": "out_of_phase_shooting_complete",
            "source_rule_id": completed_state.source_rule_id,
        },
    )


def _request_active_shooting_phase_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_state: ShootingPhaseState,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(shooting_state) is not ShootingPhaseState:
        raise GameLifecycleError("Active shooting stratagem trigger requires shooting state.")
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=shooting_state.active_player_id,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        timing_window_id=_active_shooting_phase_stratagem_timing_window_id(shooting_state),
        trigger_payload={
            "selected_unit_instance_ids": list(shooting_state.selected_unit_ids),
            "shot_unit_instance_ids": list(shooting_state.shot_unit_ids),
            "skipped_unit_instance_ids": list(shooting_state.skipped_unit_ids),
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    if _stratagem_used_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "active_shooting_phase_stratagem_window_opened",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": shooting_state.active_player_id,
                "stratagem_context": context.to_payload(),
                "request_id": request.request_id,
                "phase_body_status": "active_shooting_phase_stratagem_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": shooting_state.active_player_id,
            "phase_body_status": "active_shooting_phase_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _request_after_unit_selected_as_target_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        SELECTED_TARGET_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Selected-as-target trigger requires an AttackSequence.")
    target_unit_ids = _target_unit_ids_for_attack_sequence(attack_sequence)
    if not target_unit_ids:
        return None
    attacking_player_id = attack_sequence.attacker_player_id
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != attacking_player_id
    ):
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=reacting_player_id,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            timing_window_id=_selected_as_target_timing_window_id(
                sequence_id=attack_sequence.sequence_id,
                player_id=reacting_player_id,
            ),
            trigger_payload={
                SELECTED_TARGET_UNIT_CONTEXT_KEY: list(target_unit_ids),
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "attacking_player_id": attacking_player_id,
                "attack_sequence_id": attack_sequence.sequence_id,
            },
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        if _stratagem_used_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if not options:
            continue
        request = create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "unit_selected_as_target_stratagem_window_opened",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "player_id": reacting_player_id,
                    "attacking_player_id": attacking_player_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "selected_target_unit_instance_ids": list(target_unit_ids),
                    "attack_sequence_id": attack_sequence.sequence_id,
                    "stratagem_context": context.to_payload(),
                    "request_id": request.request_id,
                    "phase_body_status": "unit_selected_as_target_stratagem_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": reacting_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "phase_body_status": "unit_selected_as_target_stratagem_pending",
                "pending_request_id": request.request_id,
            },
        )
    return None


def _request_friendly_unit_has_shot_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
        DESTROYED_TARGET_UNIT_CONTEXT_KEY,
        HIT_TARGET_UNIT_CONTEXT_KEY,
        JUST_SHOT_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Friendly-unit-has-shot trigger requires an AttackSequence.")
    completed_event_id = _attack_sequence_completed_event_id(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if completed_event_id is None:
        raise GameLifecycleError("Completed shooting sequence missing completion event.")
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=completed_sequence.attacker_player_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        timing_window_id=_friendly_unit_has_shot_timing_window_id(completed_event_id),
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: completed_sequence.attacking_unit_instance_id,
            HIT_TARGET_UNIT_CONTEXT_KEY: list(
                _successful_hit_target_unit_ids_for_sequence(
                    decisions=decisions,
                    sequence=completed_sequence,
                )
            ),
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: list(
                _destroyed_target_unit_ids_for_sequence(
                    decisions=decisions,
                    sequence=completed_sequence,
                )
            ),
            DESTROYED_ENEMY_UNIT_CONTEXT_KEY: list(
                _destroyed_enemy_unit_ids_for_sequence(
                    state=state,
                    decisions=decisions,
                    sequence=completed_sequence,
                )
            ),
            "attack_sequence_id": completed_sequence.sequence_id,
            "attack_sequence_completed_event_id": completed_event_id,
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    if _stratagem_used_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "friendly_unit_has_shot_stratagem_window_opened",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "player_id": completed_sequence.attacker_player_id,
            "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
            "attack_sequence_id": completed_sequence.sequence_id,
            "trigger_event_id": completed_event_id,
            "stratagem_context": context.to_payload(),
            "request_id": request.request_id,
            "phase_body_status": "friendly_unit_has_shot_stratagem_pending",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "player_id": completed_sequence.attacker_player_id,
            "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
            "phase_body_status": "friendly_unit_has_shot_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _request_enemy_unit_has_shot_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
        DESTROYED_TARGET_UNIT_CONTEXT_KEY,
        HIT_TARGET_UNIT_CONTEXT_KEY,
        JUST_SHOT_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Enemy-unit-has-shot trigger requires an AttackSequence.")
    completed_event_id = _attack_sequence_completed_event_id(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if completed_event_id is None:
        raise GameLifecycleError("Completed shooting sequence missing completion event.")
    shooting_player_id = completed_sequence.attacker_player_id
    hit_target_ids = _successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=completed_sequence,
    )
    destroyed_target_ids = _destroyed_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=completed_sequence,
    )
    destroyed_enemy_unit_ids = _destroyed_enemy_unit_ids_for_sequence(
        state=state,
        decisions=decisions,
        sequence=completed_sequence,
    )
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != shooting_player_id
    ):
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=reacting_player_id,
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
            timing_window_id=_enemy_unit_has_shot_timing_window_id(
                trigger_event_id=completed_event_id,
                player_id=reacting_player_id,
            ),
            trigger_payload={
                JUST_SHOT_UNIT_CONTEXT_KEY: completed_sequence.attacking_unit_instance_id,
                HIT_TARGET_UNIT_CONTEXT_KEY: list(hit_target_ids),
                DESTROYED_TARGET_UNIT_CONTEXT_KEY: list(destroyed_target_ids),
                DESTROYED_ENEMY_UNIT_CONTEXT_KEY: list(destroyed_enemy_unit_ids),
                "shooting_player_id": shooting_player_id,
                "attack_sequence_id": completed_sequence.sequence_id,
                "attack_sequence_completed_event_id": completed_event_id,
            },
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        if _stratagem_used_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if not options:
            continue
        request = create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "enemy_unit_has_shot_stratagem_window_opened",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "player_id": reacting_player_id,
                    "shooting_player_id": shooting_player_id,
                    "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                    "attack_sequence_id": completed_sequence.sequence_id,
                    "trigger_event_id": completed_event_id,
                    "stratagem_context": context.to_payload(),
                    "request_id": request.request_id,
                    "phase_body_status": "enemy_unit_has_shot_stratagem_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "player_id": reacting_player_id,
                "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                "phase_body_status": "enemy_unit_has_shot_stratagem_pending",
                "pending_request_id": request.request_id,
            },
        )
    return None


def _request_shooting_end_surge_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: ShootingEndSurgeHookRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    if type(registry) is not ShootingEndSurgeHookRegistry:
        raise GameLifecycleError("Shooting-end surge trigger requires a registry.")
    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Shooting-end surge trigger requires an AttackSequence.")
    if not registry.all_bindings():
        return None
    completed_event_id = _attack_sequence_completed_event_id(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if completed_event_id is None:
        raise GameLifecycleError("Completed shooting sequence missing completion event.")
    if _shooting_end_surge_event_already_processed(
        decisions=decisions,
        trigger_event_id=completed_event_id,
    ):
        return None
    hit_target_ids = _successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if not hit_target_ids:
        return None
    shooting_player_id = completed_sequence.attacker_player_id
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != shooting_player_id
    ):
        context = ShootingEndSurgeContext(
            state=state,
            shooting_unit_instance_id=completed_sequence.attacking_unit_instance_id,
            shooting_player_id=shooting_player_id,
            reacting_player_id=reacting_player_id,
            trigger_event_id=completed_event_id,
            hit_target_unit_instance_ids=hit_target_ids,
        )
        grants = registry.grants_for(context)
        if not grants:
            continue
        max_distance_bonus_inches = _shooting_end_surge_grant_distance_bonus(grants)
        roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
            _shooting_end_surge_distance_roll_spec(
                source_rule_id=grants[0].source_id,
                player_id=reacting_player_id,
                shooting_unit_instance_id=completed_sequence.attacking_unit_instance_id,
                trigger_event_id=completed_event_id,
            )
        )
        descriptor = TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id=grants[0].source_id,
            trigger_timing=TriggeredReactionWindow(
                phase=BattlePhase.SHOOTING,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step="just_after_enemy_unit_has_shot",
                source_event_id=completed_event_id,
            ),
            max_distance_inches=float(roll_state.current_total + max_distance_bonus_inches),
            movement_mode=MovementMode.NORMAL,
            allow_battle_shocked=False,
            allow_within_engagement_range=False,
            one_per_phase=True,
            optional=True,
        )
        request = triggered_movement_unit_selection_request(
            state=state,
            player_id=reacting_player_id,
            descriptor=descriptor,
            eligible_units=_eligible_triggered_movement_units_from_shooting_grants(grants),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "shooting_end_surge_triggered",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "shooting_player_id": shooting_player_id,
                    "reacting_player_id": reacting_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                    "trigger_event_id": completed_event_id,
                    "hit_target_unit_instance_ids": list(hit_target_ids),
                    "surge_distance_roll": roll_state.to_payload(),
                    "max_distance_bonus_inches": max_distance_bonus_inches,
                    "descriptor": descriptor.to_payload(),
                    "grants": [grant.to_payload() for grant in grants],
                    "request_id": request.request_id,
                    "phase_body_status": "shooting_end_surge_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "reacting_player_id": reacting_player_id,
                "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                "decision_type": request.decision_type,
                "phase_body_status": "shooting_end_surge_pending",
            },
        )
    return None


def _eligible_triggered_movement_units_from_shooting_grants(
    grants: tuple[ShootingEndSurgeGrant, ...],
) -> tuple[TriggeredMovementEligibleUnit, ...]:
    return tuple(
        TriggeredMovementEligibleUnit(
            unit_instance_id=grant.unit_instance_id,
            hook_id=grant.hook_id,
            source_id=grant.source_id,
            replay_payload=grant.replay_payload,
            decision_effect_payload=grant.decision_effect_payload,
        )
        for grant in grants
    )


def _shooting_end_surge_grant_distance_bonus(
    grants: tuple[ShootingEndSurgeGrant, ...],
) -> int:
    if type(grants) is not tuple:
        raise GameLifecycleError("Shooting-end surge distance bonus requires grant tuple.")
    for grant in grants:
        if type(grant) is not ShootingEndSurgeGrant:
            raise GameLifecycleError(
                "Shooting-end surge distance bonus requires ShootingEndSurgeGrant values."
            )
    bonuses = {grant.max_distance_bonus_inches for grant in grants}
    if len(bonuses) != 1:
        raise GameLifecycleError("Shooting-end surge grants must share one distance bonus.")
    return bonuses.pop()


def _shooting_end_surge_distance_roll_spec(
    *,
    source_rule_id: str,
    player_id: str,
    shooting_unit_instance_id: str,
    trigger_event_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            "Shooting-end surge distance "
            f"{source_rule_id} for {shooting_unit_instance_id} from {trigger_event_id}"
        ),
        roll_type="shooting_end_surge.distance",
        actor_id=player_id,
    )


def _attack_sequence_completed_event_id(
    *,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> str | None:
    for record in reversed(decisions.event_log.records):
        if record.event_type != "attack_sequence_completed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("sequence_id") == sequence.sequence_id:
            return record.event_id
    return None


def _friendly_unit_has_shot_timing_window_id(trigger_event_id: str) -> str:
    return f"friendly-unit-has-shot:{_validate_identifier('trigger_event_id', trigger_event_id)}"


def _active_shooting_phase_stratagem_timing_window_id(
    shooting_state: ShootingPhaseState,
) -> str:
    if type(shooting_state) is not ShootingPhaseState:
        raise GameLifecycleError("Active shooting stratagem timing requires shooting state.")
    return (
        f"active-shooting-stratagem:round-{shooting_state.battle_round}:"
        f"player-{shooting_state.active_player_id}:selected-{len(shooting_state.selected_unit_ids)}:"
        f"shot-{len(shooting_state.shot_unit_ids)}:skipped-{len(shooting_state.skipped_unit_ids)}"
    )


def _selected_as_target_timing_window_id(*, sequence_id: str, player_id: str) -> str:
    return (
        "selected-as-target:"
        f"{_validate_identifier('sequence_id', sequence_id)}:"
        f"player-{_validate_identifier('player_id', player_id)}"
    )


def _enemy_unit_has_shot_timing_window_id(*, trigger_event_id: str, player_id: str) -> str:
    return (
        "enemy-unit-has-shot:"
        f"{_validate_identifier('trigger_event_id', trigger_event_id)}:"
        f"player-{_validate_identifier('player_id', player_id)}"
    )


def _target_unit_ids_for_attack_sequence(attack_sequence: AttackSequence) -> tuple[str, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Attack sequence target ids require an AttackSequence.")
    return tuple(sorted({pool.target_unit_instance_id for pool in attack_sequence.attack_pools}))


def _stratagem_used_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    context_payload = context.to_payload()
    for record in decisions.event_log.records:
        if record.event_type != "stratagem_used":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Stratagem use event payload must be an object.")
        payload_object = cast(dict[str, object], payload)
        if (
            payload_object.get("game_id") == context_payload.get("game_id")
            and payload_object.get("player_id") == context_payload.get("player_id")
            and payload_object.get("battle_round") == context_payload.get("battle_round")
            and payload_object.get("phase") == context_payload.get("phase")
            and payload_object.get("active_player_id") == context_payload.get("active_player_id")
            and payload_object.get("timing_window_id") == context_payload.get("timing_window_id")
        ):
            return True
    return False


def _successful_hit_target_unit_ids_for_sequence(
    *,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[str, ...]:
    target_ids: set[str] = set()
    for record in decisions.event_log.records:
        if record.event_type != "attack_sequence_step":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("sequence_id") != sequence.sequence_id:
            continue
        if payload.get("step") != AttackSequenceStep.HIT.value:
            continue
        step_payload = payload.get("payload")
        if not isinstance(step_payload, dict):
            raise GameLifecycleError("Attack sequence hit payload must be an object.")
        if step_payload.get("successful") is not True:
            continue
        pool_index = payload.get("pool_index")
        if type(pool_index) is not int:
            raise GameLifecycleError("Attack sequence hit event pool_index must be an int.")
        if pool_index < 0 or pool_index >= len(sequence.attack_pools):
            raise GameLifecycleError("Attack sequence hit event pool_index is out of range.")
        target_ids.add(sequence.attack_pools[pool_index].target_unit_instance_id)
    return tuple(sorted(target_ids))


def _destroyed_target_unit_ids_for_sequence(
    *,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[str, ...]:
    target_ids: set[str] = set()
    for record in decisions.event_log.records:
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Model destroyed payload must be an object.")
        if payload.get("sequence_id") != sequence.sequence_id:
            continue
        target_unit_id = payload.get("target_unit_instance_id")
        if type(target_unit_id) is not str:
            raise GameLifecycleError("Model destroyed payload requires target unit id.")
        target_ids.add(_validate_identifier("target_unit_instance_id", target_unit_id))
    return tuple(sorted(target_ids))


def _destroyed_enemy_unit_ids_for_sequence(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[str, ...]:
    return tuple(
        unit_id
        for unit_id in _destroyed_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=sequence,
        )
        if not rules_unit_view_by_id(state=state, unit_instance_id=unit_id).alive_models()
    )


def _shooting_end_surge_event_already_processed(
    *,
    decisions: DecisionController,
    trigger_event_id: str,
) -> bool:
    requested_event_id = _validate_identifier("trigger_event_id", trigger_event_id)
    for record in decisions.event_log.records:
        if record.event_type not in {
            "shooting_end_surge_triggered",
            "triggered_movement_declined",
            "triggered_movement_unit_selected",
            "triggered_movement_resolved",
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("trigger_event_id") == requested_event_id:
            return True
        trigger_timing = payload.get("trigger_timing")
        if isinstance(trigger_timing, dict) and trigger_timing.get("source_event_id") == (
            requested_event_id
        ):
            return True
    return False


def _request_shooting_type_selection(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_state: ShootingPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
) -> LifecycleStatus:
    active_selection = shooting_state.active_selection
    if active_selection is None:
        raise GameLifecycleError("Shooting type request requires active_selection.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
    )
    legal_types = _legal_shooting_types_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    if not legal_types:
        raise GameLifecycleError("Selected shooting unit has no legal shooting types.")
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_SHOOTING_TYPE_DECISION_TYPE,
        actor_id=active_selection.player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": active_selection.player_id,
                "unit_instance_id": active_selection.unit_instance_id,
                "source_decision_request_id": active_selection.request_id,
                "source_decision_result_id": active_selection.result_id,
                "legal_shooting_types": [shooting_type.value for shooting_type in legal_types],
            }
        ),
        options=_shooting_type_options(
            state=state,
            active_selection=active_selection,
            legal_types=legal_types,
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_type_selection_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": active_selection.request_id,
                "source_decision_result_id": active_selection.result_id,
                "legal_shooting_types": [shooting_type.value for shooting_type in legal_types],
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "legal_shooting_type_count": len(legal_types),
        },
    )


def _request_shooting_declaration(
    *,
    state: GameState,
    decisions: DecisionController,
    active_selection: ShootingUnitSelection,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    selected_shooting_type: ShootingType | None = None,
    phase: BattlePhase = BattlePhase.SHOOTING,
    request_context: JsonValue | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    forced_shooting_type: ShootingType | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus:
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
    )
    available_weapons = _available_weapons_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=active_selection.player_id,
        selected_shooting_type=selected_shooting_type,
    )
    candidate_target_unit_ids = (
        _enemy_placed_unit_ids(
            state=state,
            player_id=active_selection.player_id,
        )
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting target_unit_ids", target_unit_ids)
    )
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=candidate_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=candidate_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=candidate_target_unit_ids,
    )
    detection_context_fingerprint = _targeting_detection_context_fingerprint(
        hidden_target_unit_ids=hidden_target_unit_ids,
        target_unit_ids_with_recent_ranged_attacks=target_unit_ids_with_recent_ranged_attacks,
        detection_range_bonus_by_target_id=detection_range_bonus_by_target_id,
    )
    target_candidates: list[JsonValue] = []
    target_candidate_cache: dict[
        _ShootingUnitCandidateCacheKey,
        tuple[ShootingTargetCandidate, ...],
    ] = {}
    for weapon in available_weapons:
        profile = weapon["weapon_profile"]
        attacker_unit = _component_unit_for_available_weapon(
            rules_unit=rules_unit,
            weapon=weapon,
        )
        candidate_cache_key = _shooting_unit_candidate_cache_key(
            weapon=weapon,
            attacker_unit=attacker_unit,
            detection_context_fingerprint=detection_context_fingerprint,
        )
        if candidate_cache_key not in target_candidate_cache:
            target_candidate_cache[candidate_cache_key] = tuple(
                _shooting_candidate_with_target_restrictions(
                    candidate=candidate,
                    state=state,
                    player_id=active_selection.player_id,
                    attacking_unit_instance_id=attacker_unit.unit_instance_id,
                    target_unit_instance_id=candidate.target_unit_instance_id,
                    registry=shooting_target_restriction_hooks,
                    attacker_model_instance_id=candidate.observer_model_id,
                    shooting_type=forced_shooting_type or selected_shooting_type,
                )
                for candidate in shooting_target_candidates_for_unit(
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    attacker_unit=attacker_unit,
                    weapon_profile=profile,
                    target_unit_ids=candidate_target_unit_ids,
                    terrain_features=terrain_features,
                    hidden_target_unit_ids=hidden_target_unit_ids,
                    target_unit_ids_with_recent_ranged_attacks=(
                        target_unit_ids_with_recent_ranged_attacks
                    ),
                    target_detection_range_bonus_inches_by_unit_id=(
                        detection_range_bonus_by_target_id
                    ),
                )
            )
        candidates = target_candidate_cache[candidate_cache_key]
        target_candidates.extend(
            _target_candidate_payload_for_request(
                state=state,
                scenario=scenario,
                candidate=cast(dict[str, JsonValue], candidate.to_payload()),
                unit=attacker_unit,
                rules_unit=rules_unit,
                weapon_profile=profile,
                player_id=active_selection.player_id,
                army_catalog=army_catalog,
                selected_shooting_type=selected_shooting_type,
                forced_shooting_type=forced_shooting_type,
            )
            for candidate in candidates
        )
    visibility_cache_key = shooting_visibility_cache_key(
        scenario=scenario,
        terrain_features=terrain_features,
    )
    request_id = state.next_decision_request_id()
    proposal_request: ShootingDeclarationProposalRequestPayload = {
        "request_id": request_id,
        "decision_type": SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        "actor_id": active_selection.player_id,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "active_player_id": active_selection.player_id,
        "unit_instance_id": active_selection.unit_instance_id,
        "proposal_kind": SHOOTING_DECLARATION_PROPOSAL_KIND,
        "source_decision_request_id": active_selection.request_id,
        "source_decision_result_id": active_selection.result_id,
        "selected_shooting_type": (
            None if selected_shooting_type is None else selected_shooting_type.value
        ),
        "ruleset_descriptor_hash": state.ruleset_descriptor_hash,
        "visibility_cache_key": visibility_cache_key,
        "firing_deck_value": _firing_deck_value_for_rules_unit(
            rules_unit=rules_unit,
            army_catalog=army_catalog,
        ),
        "available_weapons": [_available_weapon_to_payload(weapon) for weapon in available_weapons],
        "target_candidates": target_candidates,
    }
    request = DecisionRequest(
        request_id=request_id,
        decision_type=SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        actor_id=active_selection.player_id,
        payload=validate_json_value(
            {
                "proposal_request": proposal_request,
                "request_context": request_context,
            }
        ),
        options=(parameterized_decision_option(),),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_declaration_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": phase.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": active_selection.request_id,
                "source_decision_result_id": active_selection.result_id,
                "selected_shooting_type": (
                    None if selected_shooting_type is None else selected_shooting_type.value
                ),
                "available_weapon_count": len(available_weapons),
                "target_candidate_count": len(target_candidates),
                "visibility_cache_key": visibility_cache_key,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": phase.value,
            "battle_round": state.battle_round,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "proposal_kind": SHOOTING_DECLARATION_PROPOSAL_KIND,
        },
    )


def request_out_of_phase_shooting_declaration(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
    unit_instance_id: str,
    parent_phase: BattlePhase,
    source_rule_id: str,
    source_decision_request_id: str,
    source_decision_result_id: str,
    source_context: JsonValue,
    target_unit_ids: tuple[str, ...] | None = None,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None = None,
) -> LifecycleStatus:
    if state.out_of_phase_shooting_state is not None:
        raise GameLifecycleError("Out-of-phase shooting state is already active.")
    selected_rules_unit_id = rules_unit_id_for_unit_id(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    selection = ShootingUnitSelection(
        player_id=player_id,
        battle_round=state.battle_round,
        unit_instance_id=selected_rules_unit_id,
        request_id=source_decision_request_id,
        result_id=source_decision_result_id,
    )
    state.out_of_phase_shooting_state = OutOfPhaseShootingState(
        battle_round=state.battle_round,
        player_id=player_id,
        parent_phase=parent_phase,
        source_rule_id=source_rule_id,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        source_context=source_context,
        selected_unit_instance_id=selected_rules_unit_id,
        target_unit_ids=target_unit_ids,
    )
    grant_status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=(
            ShootingUnitSelectedGrantRegistry.empty()
            if shooting_unit_selected_grant_hooks is None
            else shooting_unit_selected_grant_hooks
        ),
    )
    if grant_status is not None:
        return grant_status
    return _request_shooting_declaration(
        state=state,
        decisions=decisions,
        active_selection=selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        phase=parent_phase,
        request_context=validate_json_value(
            {
                "request_kind": "out_of_phase_shooting",
                "source_rule_id": source_rule_id,
                "source_context": source_context,
            }
        ),
        target_unit_ids=target_unit_ids,
        forced_shooting_type=(
            ShootingType.SNAP if source_rule_id == FIRE_OVERWATCH_RULE_ID else None
        ),
    )


def _target_candidate_payload_for_request(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    candidate: dict[str, JsonValue],
    unit: UnitInstance,
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    player_id: str,
    army_catalog: ArmyCatalog,
    selected_shooting_type: ShootingType | None,
    forced_shooting_type: ShootingType | None,
) -> JsonValue:
    payload = dict(candidate)
    payload["required_weapon_ability_selections"] = _required_weapon_ability_selections_for_target(
        state=state,
        proposal_request_id=_embedded_weapon_ability_request_prefix(
            state=state,
            attacker_unit_id=rules_unit.unit_instance_id,
            weapon_profile=weapon_profile,
        ),
        weapon_profile=weapon_profile,
        target_unit_id=_payload_string(
            cast(dict[str, object], payload), key="target_unit_instance_id"
        ),
        player_id=player_id,
    )
    payload["shooting_types"] = [
        shooting_type.value
        for shooting_type in _shooting_types_for_candidate_payload(
            state=state,
            scenario=scenario,
            candidate=candidate,
            unit=unit,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            player_id=player_id,
            army_catalog=army_catalog,
            selected_shooting_type=selected_shooting_type,
            forced_shooting_type=forced_shooting_type,
        )
    ]
    return validate_json_value(payload)


def _embedded_weapon_ability_request_prefix(
    *,
    state: GameState,
    attacker_unit_id: str,
    weapon_profile: WeaponProfile,
) -> str:
    return f"{state.game_id}:shooting-declaration:{attacker_unit_id}:{weapon_profile.profile_id}"


def _required_weapon_ability_selections_for_target(
    *,
    state: GameState,
    proposal_request_id: str,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    player_id: str,
) -> list[JsonValue]:
    target_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    selection_request = weapon_ability_selection_request(
        weapon_profile,
        AbilityKind.ANTI_KEYWORD,
        target_keywords=target_rules_unit.keywords,
        actor_id=player_id,
        request_id=f"{proposal_request_id}:{target_unit_id}:anti-keyword",
        source_context={
            "phase": BattlePhase.SHOOTING.value,
            "target_unit_instance_id": target_unit_id,
        },
    )
    if selection_request is None:
        return []
    return [validate_json_value(selection_request.to_payload())]


def _shooting_types_for_candidate_payload(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    candidate: dict[str, JsonValue],
    unit: UnitInstance,
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    player_id: str,
    army_catalog: ArmyCatalog,
    selected_shooting_type: ShootingType | None,
    forced_shooting_type: ShootingType | None,
) -> tuple[ShootingType, ...]:
    if candidate.get("is_legal") is not True:
        return ()
    raw_types = candidate.get("shooting_types")
    if not isinstance(raw_types, list):
        raise GameLifecycleError("Shooting target candidate payload missing shooting_types.")
    base_types = tuple(shooting_type_from_token(value) for value in raw_types)
    target_unit_id = _payload_string(
        cast(dict[str, object], candidate),
        key="target_unit_instance_id",
    )
    if forced_shooting_type is not None:
        if forced_shooting_type is not ShootingType.SNAP:
            raise GameLifecycleError("Unsupported forced shooting type.")
        if _snap_shooting_type_allowed_for_unit_target(
            scenario=scenario,
            candidate=candidate,
            unit=unit,
            target_unit_id=target_unit_id,
        ):
            return (ShootingType.SNAP,)
        return ()
    if selected_shooting_type is not None:
        return _shooting_types_for_selected_type_for_rules_unit(
            state=state,
            base_types=base_types,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            selected_shooting_type=selected_shooting_type,
            player_id=player_id,
            army_catalog=army_catalog,
        )
    if _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        if ShootingType.NORMAL in base_types and has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.ASSAULT,
        ):
            return (ShootingType.ASSAULT,)
        return ()
    return base_types


def _shooting_types_for_selected_type(
    *,
    state: GameState,
    base_types: tuple[ShootingType, ...],
    unit: UnitInstance,
    weapon_profile: WeaponProfile,
    selected_shooting_type: ShootingType,
    player_id: str,
    army_catalog: ArmyCatalog,
) -> tuple[ShootingType, ...]:
    return _shooting_types_for_selected_type_for_rules_unit(
        state=state,
        base_types=base_types,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        weapon_profile=weapon_profile,
        selected_shooting_type=selected_shooting_type,
        player_id=player_id,
        army_catalog=army_catalog,
    )


def _shooting_types_for_selected_type_for_rules_unit(
    *,
    state: GameState,
    base_types: tuple[ShootingType, ...],
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    selected_shooting_type: ShootingType,
    player_id: str,
    army_catalog: ArmyCatalog,
) -> tuple[ShootingType, ...]:
    shooting_type = shooting_type_from_token(selected_shooting_type)
    advanced = _rules_unit_advanced_this_turn(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    )
    if shooting_type is ShootingType.NORMAL:
        if advanced:
            return ()
        if ShootingType.NORMAL in base_types:
            return (ShootingType.NORMAL,)
        return ()
    if shooting_type is ShootingType.ASSAULT:
        if not advanced:
            return ()
        if ShootingType.NORMAL in base_types and has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.ASSAULT,
        ):
            return (ShootingType.ASSAULT,)
        return ()
    if shooting_type is ShootingType.CLOSE_QUARTERS:
        if advanced or ShootingType.CLOSE_QUARTERS not in base_types:
            return ()
        if _rules_unit_has_vehicle_or_monster_keyword(
            rules_unit
        ) or has_close_quarters_weapon_keyword(weapon_profile):
            return (ShootingType.CLOSE_QUARTERS,)
        return ()
    if shooting_type is ShootingType.INDIRECT:
        if advanced or not _rules_unit_has_indirect_ranged_weapon(
            rules_unit=rules_unit,
            army_catalog=army_catalog,
        ):
            return ()
        if not has_weapon_keyword(weapon_profile, WeaponKeyword.INDIRECT_FIRE):
            return ()
        if ShootingType.INDIRECT in base_types or ShootingType.NORMAL in base_types:
            return (ShootingType.INDIRECT,)
        return ()
    if shooting_type is ShootingType.SNAP:
        return ()
    raise GameLifecycleError("Unsupported selected shooting type.")


def _apply_shooting_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_hooks: ShootingUnitSelectedHookRegistry,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    _validate_shooting_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Shooting unit selection actor must be the active player.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Shooting unit selection requires shooting_phase_state.")
    if result.selected_option_id == COMPLETE_SHOOTING_PHASE_OPTION_ID:
        skipped_unit_ids = _legal_shooting_unit_ids(
            state=state,
            shooting_state=shooting_state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        )
        state.shooting_phase_state = shooting_state.with_phase_complete(
            skipped_unit_ids=skipped_unit_ids,
        )
        decisions.event_log.append(
            "shooting_phase_completion_declared",
            _shooting_phase_status_payload(
                state=state,
                phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                skipped_unit_ids=skipped_unit_ids,
            ),
        )
        return None

    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    legal_unit_ids = _legal_shooting_unit_ids(
        state=state,
        shooting_state=shooting_state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    if unit_instance_id not in legal_unit_ids:
        raise GameLifecycleError("Shooting unit selection is not currently legal.")
    selection = ShootingUnitSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.shooting_phase_state = shooting_state.with_unit_selection(selection)
    decisions.event_log.append(
        "shooting_unit_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "unit_instance_id": unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_selected",
        },
    )
    _apply_shooting_unit_selected_effect_grants(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=shooting_unit_selected_hooks,
    )
    return _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=shooting_unit_selected_grant_hooks,
    )


def _apply_shooting_unit_selected_effect_grants(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    registry: ShootingUnitSelectedHookRegistry,
) -> None:
    if type(registry) is not ShootingUnitSelectedHookRegistry:
        raise GameLifecycleError("Shooting-unit-selected effect grants require a registry.")
    context = ShootingUnitSelectedContext(
        state=state,
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        request_id=selection.request_id,
        result_id=selection.result_id,
    )
    for grant in registry.grants_for(context):
        state.record_persisting_effect(grant.persisting_effect)
        decisions.event_log.append(
            grant.event_type,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "player_id": selection.player_id,
                    "shooting_unit_instance_id": selection.unit_instance_id,
                    "request_id": selection.request_id,
                    "result_id": selection.result_id,
                    "grant": grant.to_payload(),
                    "persisting_effect": grant.persisting_effect.to_payload(),
                }
            ),
        )


def _request_shooting_unit_selected_grant_decision_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    registry: ShootingUnitSelectedGrantRegistry,
) -> LifecycleStatus | None:
    if type(registry) is not ShootingUnitSelectedGrantRegistry:
        raise GameLifecycleError("Shooting-unit-selected grants require a registry.")
    context = _shooting_unit_selected_context(state=state, selection=selection)
    grants = registry.grants_for(context)
    if not grants:
        return None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
        actor_id=selection.player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "source_decision_request_id": selection.request_id,
                "source_decision_result_id": selection.result_id,
                "available_shooting_unit_grants": [grant.to_payload() for grant in grants],
            }
        ),
        options=_shooting_unit_selected_grant_options(selection=selection, grants=grants),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_unit_selected_grant_decision_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": selection.request_id,
                "source_decision_result_id": selection.result_id,
                "available_shooting_unit_grants": [grant.to_payload() for grant in grants],
                "phase_body_status": "shooting_unit_selected_grant_decision_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "phase_body_status": "shooting_unit_selected_grant_decision_pending",
            "battle_round": state.battle_round,
            "active_player_id": selection.player_id,
            "unit_instance_id": selection.unit_instance_id,
            "decision_type": request.decision_type,
        },
    )


def _shooting_unit_selected_grant_options(
    *,
    selection: ShootingUnitSelection,
    grants: tuple[ShootingUnitSelectedGrant, ...],
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id=DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
            label="Decline Shooting Unit Grant",
            payload=validate_json_value(
                {
                    "submission_kind": SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
                    "unit_instance_id": selection.unit_instance_id,
                    "source_decision_request_id": selection.request_id,
                    "source_decision_result_id": selection.result_id,
                    "selected_shooting_unit_grants": [],
                }
            ),
        )
    ]
    for grant in grants:
        options.append(
            DecisionOption(
                option_id=grant.hook_id,
                label=grant.label,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
                        "unit_instance_id": selection.unit_instance_id,
                        "source_decision_request_id": selection.request_id,
                        "source_decision_result_id": selection.result_id,
                        "selected_shooting_unit_grants": [grant.to_payload()],
                    }
                ),
            )
        )
    return tuple(options)


def _apply_shooting_unit_selected_grant_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    registry: ShootingUnitSelectedGrantRegistry,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus | None:
    selection = _active_shooting_unit_selection(state)
    if state.out_of_phase_shooting_state is None:
        _validate_shooting_phase_state(state)
    if result.actor_id != selection.player_id:
        raise GameLifecycleError("Shooting unit grant actor must be the selected unit player.")
    payload = _decision_payload_object(result.payload)
    _validate_shooting_unit_selected_grant_payload_context(payload=payload, selection=selection)
    if result.selected_option_id == DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID:
        selected_grants: tuple[ShootingUnitSelectedGrant, ...] = ()
    else:
        selected_grants = _selected_shooting_unit_grants_from_payload(payload)
        _validate_selected_shooting_unit_grants(
            state=state,
            selection=selection,
            registry=registry,
            selected_grants=selected_grants,
        )
    persisting_effects = tuple(
        effect
        for grant in selected_grants
        for effect in _record_shooting_unit_selected_grant_effects(
            state=state,
            result=result,
            selection=selection,
            grant=grant,
        )
    )
    decisions.event_log.append(
        "shooting_unit_selected_grant_decision_resolved",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "selected_option_id": result.selected_option_id,
                "selected_shooting_unit_grants": [grant.to_payload() for grant in selected_grants],
                "persisting_effects": [effect.to_payload() for effect in persisting_effects],
                "phase_body_status": "shooting_unit_selected_grant_decision_resolved",
            }
        ),
    )
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and out_of_phase_state.selected_unit_instance_id == selection.unit_instance_id
        and not out_of_phase_state.attack_pools
        and out_of_phase_state.attack_sequence is None
    ):
        state.out_of_phase_shooting_state = out_of_phase_state.with_grant_effect_ids(
            tuple(effect.effect_id for effect in persisting_effects)
        )
        if ruleset_descriptor is None or army_catalog is None:
            return None
        return _request_shooting_declaration(
            state=state,
            decisions=decisions,
            active_selection=selection,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            phase=out_of_phase_state.parent_phase,
            request_context=validate_json_value(
                {
                    "request_kind": "out_of_phase_shooting",
                    "source_rule_id": out_of_phase_state.source_rule_id,
                    "source_context": out_of_phase_state.source_context,
                }
            ),
            target_unit_ids=out_of_phase_state.target_unit_ids,
            forced_shooting_type=(
                ShootingType.SNAP
                if out_of_phase_state.source_rule_id == FIRE_OVERWATCH_RULE_ID
                else None
            ),
            shooting_target_restriction_hooks=(
                ShootingTargetRestrictionHookRegistry.empty()
                if shooting_target_restriction_hooks is None
                else shooting_target_restriction_hooks
            ),
        )
    return None


def _selected_shooting_unit_grants_from_payload(
    payload: dict[str, object],
) -> tuple[ShootingUnitSelectedGrant, ...]:
    raw_grants = payload.get("selected_shooting_unit_grants")
    if not isinstance(raw_grants, list):
        raise GameLifecycleError("Shooting unit grant payload missing selected grants.")
    raw_grant_payloads = cast(list[object], raw_grants)
    grants: list[ShootingUnitSelectedGrant] = []
    for raw_grant in raw_grant_payloads:
        if not isinstance(raw_grant, dict):
            raise GameLifecycleError("Shooting unit selected grants must be objects.")
        grants.append(
            ShootingUnitSelectedGrant.from_payload(
                cast(ShootingUnitSelectedGrantPayload, raw_grant)
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_selected_shooting_unit_grants(
    *,
    state: GameState,
    selection: ShootingUnitSelection,
    registry: ShootingUnitSelectedGrantRegistry,
    selected_grants: tuple[ShootingUnitSelectedGrant, ...],
) -> None:
    if not selected_grants:
        raise GameLifecycleError("Shooting unit grant selection requires a selected grant.")
    available_payloads = {
        grant.hook_id: grant.to_payload()
        for grant in registry.grants_for(
            _shooting_unit_selected_context(state=state, selection=selection)
        )
    }
    for grant in selected_grants:
        expected = available_payloads.get(grant.hook_id)
        if expected is None:
            raise GameLifecycleError("Selected shooting unit grant is not available.")
        if grant.to_payload() != expected:
            raise GameLifecycleError("Selected shooting unit grant payload drift.")


def _record_shooting_unit_selected_grant_effects(
    *,
    state: GameState,
    result: DecisionResult,
    selection: ShootingUnitSelection,
    grant: ShootingUnitSelectedGrant,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    if grant.decision_effect_payload is not None:
        resource_spend_result = apply_faction_resource_spend_effect(
            state=state,
            player_id=selection.player_id,
            source_id=f"{grant.source_id}:{result.request_id}:{result.result_id}:spend",
            effect_payload=grant.decision_effect_payload,
        )
        spend_effect = PersistingEffect(
            effect_id=f"{result.result_id}:{grant.hook_id}:decision",
            source_rule_id=grant.source_id,
            owner_player_id=selection.player_id,
            target_unit_instance_ids=(selection.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.SHOOTING,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=faction_resource_result_enriched_payload(
                effect_payload=grant.decision_effect_payload,
                result=resource_spend_result,
            ),
        )
        state.record_persisting_effect(spend_effect)
        effects.append(spend_effect)
    if grant.unit_effect_payload is None:
        if not effects:
            raise GameLifecycleError("Shooting unit selected grant has no effect to record.")
        return tuple(effects)
    unit_effect = PersistingEffect(
        effect_id=f"{result.result_id}:{grant.hook_id}:unit",
        source_rule_id=grant.source_id,
        owner_player_id=selection.player_id,
        target_unit_instance_ids=_shooting_unit_selected_grant_unit_effect_target_ids(
            unit_instance_id=selection.unit_instance_id,
            effect_payload=grant.unit_effect_payload,
        ),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=_shooting_unit_selected_grant_effect_expiration(
            state=state,
            selection=selection,
            grant=grant,
        ),
        effect_payload=grant.unit_effect_payload,
    )
    state.record_persisting_effect(unit_effect)
    effects.append(unit_effect)
    return tuple(effects)


def _shooting_unit_selected_context(
    *,
    state: GameState,
    selection: ShootingUnitSelection,
) -> ShootingUnitSelectedContext:
    return ShootingUnitSelectedContext(
        state=state,
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        request_id=selection.request_id,
        result_id=selection.result_id,
    )


def _active_shooting_unit_selection(state: GameState) -> ShootingUnitSelection:
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and shooting_state.active_selection is not None:
        return shooting_state.active_selection
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and not out_of_phase_state.attack_pools
        and out_of_phase_state.attack_sequence is None
    ):
        return ShootingUnitSelection(
            player_id=out_of_phase_state.player_id,
            battle_round=out_of_phase_state.battle_round,
            unit_instance_id=out_of_phase_state.selected_unit_instance_id,
            request_id=out_of_phase_state.source_decision_request_id,
            result_id=out_of_phase_state.source_decision_result_id,
        )
    raise GameLifecycleError("Shooting unit grant requires an active selection.")


def _validate_shooting_unit_selected_grant_payload_context(
    *,
    payload: dict[str, object],
    selection: ShootingUnitSelection,
) -> None:
    if _payload_string(payload, key="submission_kind") != SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
        raise GameLifecycleError("Shooting unit grant payload has invalid submission_kind.")
    if _payload_string(payload, key="unit_instance_id") != selection.unit_instance_id:
        raise GameLifecycleError("Shooting unit grant unit drift.")
    if (
        _payload_string(payload, key="source_decision_request_id") != selection.request_id
        or _payload_string(payload, key="source_decision_result_id") != selection.result_id
    ):
        raise GameLifecycleError("Shooting unit grant source decision drift.")


def _shooting_unit_selected_grant_unit_effect_target_ids(
    *,
    unit_instance_id: str,
    effect_payload: JsonValue,
) -> tuple[str, ...]:
    if not isinstance(effect_payload, dict):
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    if raw_target_ids is None:
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Shooting unit grant target_unit_instance_ids must be a list.")
    target_ids = tuple(
        _validate_identifier("target_unit_instance_ids", raw_id) for raw_id in raw_target_ids
    )
    if not target_ids:
        raise GameLifecycleError("Shooting unit grant target_unit_instance_ids is empty.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Shooting unit grant target_unit_instance_ids are duplicated.")
    return target_ids


def _shooting_unit_selected_grant_effect_expiration(
    *,
    state: GameState,
    selection: ShootingUnitSelection,
    grant: ShootingUnitSelectedGrant,
) -> EffectExpiration:
    expiration = grant.unit_effect_expiration
    if expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=selection.player_id,
        )
    if expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=selection.player_id,
        )
    raise GameLifecycleError("Shooting unit grant has unsupported expiration.")


def _apply_shooting_dice_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    _validate_shooting_phase_state(state)
    shooting_state = _ensure_shooting_phase_state(state=state)
    attack_sequence = shooting_state.attack_sequence
    if attack_sequence is None:
        raise GameLifecycleError("Shooting dice reroll requires an active attack sequence.")
    apply_source_backed_attack_dice_reroll_decision(
        state=state,
        result=result,
        decisions=decisions,
        attack_sequence=attack_sequence,
        expected_phase=BattlePhase.SHOOTING,
        phase_label="Shooting",
    )
    return None


def _apply_shooting_type_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
) -> None:
    _validate_shooting_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Shooting type selection actor must be the active player.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        raise GameLifecycleError("Shooting type selection requires active_selection.")
    if shooting_state.selected_shooting_type is not None:
        raise GameLifecycleError("Shooting type has already been selected.")
    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    if unit_instance_id != shooting_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Shooting type selection unit drift.")
    shooting_type = shooting_type_from_token(_payload_string(payload, key="shooting_type"))
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    legal_types = _legal_shooting_types_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    if shooting_type not in legal_types:
        raise GameLifecycleError("Shooting type selection is not currently legal.")
    selection = ShootingTypeSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        shooting_type=shooting_type,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.shooting_phase_state = shooting_state.with_shooting_type_selection(selection)
    decisions.event_log.append(
        "shooting_type_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": unit_instance_id,
                "shooting_type": shooting_type.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "shooting_type_selected",
            }
        ),
    )


def _apply_shooting_declaration_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    if _apply_out_of_phase_shooting_declaration_decision(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    ):
        return
    _validate_shooting_phase_state(state)
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        raise GameLifecycleError("Shooting declaration requires active_selection.")
    proposal = shooting_declaration_proposal_from_json(result.payload)
    attack_pools, ineligible_unit_ids = _attack_pools_for_proposal(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        result_id=result.result_id,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    one_shot_records = _record_one_shot_weapon_uses_for_attack_pools(
        state=state,
        attack_pools=attack_pools,
        source_phase=BattlePhase.SHOOTING,
        result_id=result.result_id,
    )
    attack_sequence = AttackSequence.start(
        sequence_id=f"attack-sequence:{result.result_id}",
        attacker_player_id=_active_player_id(state),
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=attack_pools,
    )
    state.shooting_phase_state = shooting_state.with_declaration(
        attack_pools=attack_pools,
        ineligible_unit_instance_ids=ineligible_unit_ids,
        attack_sequence=attack_sequence,
    )
    ranged_attack_history_record = _record_ranged_attack_history_for_declaration(
        state=state,
        player_id=_active_player_id(state),
        unit_instance_id=proposal.unit_instance_id,
        phase=BattlePhase.SHOOTING,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    apply_hidden_status_loss_after_ranged_attacks(
        state=state,
        decisions=decisions,
        unit_instance_id=proposal.unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
        ruleset_descriptor=ruleset_descriptor,
        event_type="unit_hidden_status_lost_after_shooting",
    )
    decisions.event_log.append(
        "shooting_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": proposal.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal.proposal_request_id,
                "visibility_cache_key": proposal.visibility_cache_key,
                "attack_pools": [pool.to_payload() for pool in attack_pools],
                "one_shot_weapon_use_records": [record.to_payload() for record in one_shot_records],
                "ranged_attack_history_record": ranged_attack_history_record.to_payload(),
                "ineligible_unit_instance_ids": list(ineligible_unit_ids),
                "phase_body_status": "declaration_accepted",
            }
        ),
    )


def _apply_out_of_phase_shooting_declaration_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> bool:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is None:
        return False
    proposal = shooting_declaration_proposal_from_json(result.payload)
    if (
        proposal.source_decision_request_id != out_of_phase_state.source_decision_request_id
        or proposal.source_decision_result_id != out_of_phase_state.source_decision_result_id
    ):
        return False
    attack_pools, ineligible_unit_ids = _attack_pools_for_proposal(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        result_id=result.result_id,
        shooting_player_id=out_of_phase_state.player_id,
        out_of_phase_state=out_of_phase_state,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if ineligible_unit_ids:
        raise GameLifecycleError("Out-of-phase shooting cannot mark extra units as shot.")
    one_shot_records = _record_one_shot_weapon_uses_for_attack_pools(
        state=state,
        attack_pools=attack_pools,
        source_phase=out_of_phase_state.parent_phase,
        result_id=result.result_id,
    )
    attack_sequence = AttackSequence.start(
        sequence_id=f"out-of-phase-attack-sequence:{result.result_id}",
        attacker_player_id=out_of_phase_state.player_id,
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=attack_pools,
    )
    state.out_of_phase_shooting_state = out_of_phase_state.with_declaration(
        attack_pools=attack_pools,
        attack_sequence=attack_sequence,
    )
    ranged_attack_history_record = _record_ranged_attack_history_for_declaration(
        state=state,
        player_id=out_of_phase_state.player_id,
        unit_instance_id=proposal.unit_instance_id,
        phase=out_of_phase_state.parent_phase,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    apply_hidden_status_loss_after_ranged_attacks(
        state=state,
        decisions=decisions,
        unit_instance_id=proposal.unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
        ruleset_descriptor=ruleset_descriptor,
        event_type="unit_hidden_status_lost_after_out_of_phase_shooting",
    )
    decisions.event_log.append(
        "out_of_phase_shooting_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "player_id": out_of_phase_state.player_id,
                "parent_phase": out_of_phase_state.parent_phase.value,
                "source_rule_id": out_of_phase_state.source_rule_id,
                "unit_instance_id": proposal.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal.proposal_request_id,
                "visibility_cache_key": proposal.visibility_cache_key,
                "attack_pools": [pool.to_payload() for pool in attack_pools],
                "one_shot_weapon_use_records": [record.to_payload() for record in one_shot_records],
                "ranged_attack_history_record": ranged_attack_history_record.to_payload(),
            }
        ),
    )
    return True


def _record_ranged_attack_history_for_declaration(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    phase: BattlePhase,
    request_id: str,
    result_id: str,
) -> RangedAttackHistoryRecord:
    from warhammer40k_core.engine.game_state import RangedAttackHistoryRecord

    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Ranged attack history requires an active player turn.")
    record = RangedAttackHistoryRecord(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=phase,
        request_id=request_id,
        result_id=result_id,
    )
    state.record_ranged_attack_history(record)
    return record


def _record_one_shot_weapon_uses_for_attack_pools(
    *,
    state: GameState,
    attack_pools: tuple[RangedAttackPool, ...],
    source_phase: BattlePhase,
    result_id: str,
) -> tuple[OneShotWeaponUseRecord, ...]:
    records: list[OneShotWeaponUseRecord] = []
    for pool_index, pool in enumerate(attack_pools, start=1):
        if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.ONE_SHOT):
            continue
        model_instance_id = (
            pool.attacker_model_instance_id
            if pool.firing_deck_source_model_instance_id is None
            else pool.firing_deck_source_model_instance_id
        )
        records.append(
            state.record_one_shot_weapon_selected(
                model_instance_id=model_instance_id,
                wargear_id=pool.wargear_id,
                weapon_profile_id=pool.weapon_profile_id,
                source_phase=source_phase,
                selection_id=f"{result_id}:one-shot-pool-{pool_index:03d}",
            )
        )
    return tuple(records)


def apply_hidden_status_loss_after_ranged_attacks(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    request_id: str,
    result_id: str,
    ruleset_descriptor: RulesetDescriptor,
    event_type: str,
) -> None:
    if not ruleset_descriptor.terrain_visibility_policy.hidden_lost_after_shooting:
        return
    effects = state.persisting_effects_for_unit(unit_instance_id)
    hidden_effect_ids = hidden_unit_effect_ids(effects)
    if not hidden_effect_ids:
        return
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Hidden shooting status loss requires a battle phase.")
    if ranged_attacks_keep_hidden_by_effects(effects):
        decisions.event_log.append(
            "unit_hidden_status_preserved_after_shooting",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": current_phase.value,
                    "unit_instance_id": unit_instance_id,
                    "request_id": request_id,
                    "result_id": result_id,
                    "hidden_effect_ids": list(hidden_effect_ids),
                    "phase_body_status": "hidden_status_preserved",
                }
            ),
        )
        return
    removed_effects = state.remove_persisting_effects_by_id(hidden_effect_ids)
    decisions.event_log.append(
        event_type,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": current_phase.value,
                "unit_instance_id": unit_instance_id,
                "request_id": request_id,
                "result_id": result_id,
                "removed_persisting_effects": [effect.to_payload() for effect in removed_effects],
                "phase_body_status": "hidden_status_lost",
            }
        ),
    )


def _apply_attack_sequence_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    stratagem_index: StratagemCatalogIndex,
) -> LifecycleStatus | None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        attack_sequence, allocated_model_ids, status = _apply_attack_sequence_decision_to_sequence(
            state=state,
            result=result,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=out_of_phase_state.attack_sequence,
            already_allocated_model_ids=out_of_phase_state.allocated_model_ids,
            stratagem_index=stratagem_index,
        )
        state.out_of_phase_shooting_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )
        return status
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.attack_sequence is None:
        raise GameLifecycleError("Attack sequence decision requires active attack_sequence.")
    attack_sequence, allocated_model_ids, status = _apply_attack_sequence_decision_to_sequence(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=shooting_state.attack_sequence,
        already_allocated_model_ids=shooting_state.allocated_model_ids_this_phase,
        stratagem_index=stratagem_index,
    )
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=attack_sequence,
        allocated_model_ids_this_phase=allocated_model_ids,
    )
    return status


def _apply_attack_sequence_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        state.out_of_phase_shooting_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=_apply_attack_sequence_selection_to_sequence(
                attack_sequence=out_of_phase_state.attack_sequence,
                result=result,
                decisions=decisions,
            ),
            allocated_model_ids=out_of_phase_state.allocated_model_ids,
        )
        return
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.attack_sequence is None:
        raise GameLifecycleError("Attack sequence selection requires active attack_sequence.")
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=_apply_attack_sequence_selection_to_sequence(
            attack_sequence=shooting_state.attack_sequence,
            result=result,
            decisions=decisions,
        ),
        allocated_model_ids_this_phase=shooting_state.allocated_model_ids_this_phase,
    )


def _apply_attack_sequence_selection_to_sequence(
    *,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    decisions: DecisionController,
) -> AttackSequence:
    if result.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        return apply_resolve_target_unit_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
    if result.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        return apply_attack_weapon_group_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
    raise GameLifecycleError("Unsupported attack sequence selection decision type.")


def _apply_attack_sequence_decision_to_sequence(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    stratagem_index: StratagemCatalogIndex,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    updated_sequence: AttackSequence | None
    allocated_model_ids: tuple[str, ...]
    status: LifecycleStatus | None
    if result.decision_type == SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
        validate_psychic_attack_modifier_ignore_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
        updated_sequence = attack_sequence
        allocated_model_ids = already_allocated_model_ids
        status = None
    elif result.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_allocation_order_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            stratagem_index=stratagem_index,
        )
    elif result.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_damage_allocation_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            stratagem_index=stratagem_index,
        )
    elif result.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_precision_allocation_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            stratagem_index=stratagem_index,
        )
    elif result.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    elif result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_destruction_reaction_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    elif (
        result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and is_destroyed_transport_disembark_proposal_request(
            decisions.record_for_result(result).request
        )
    ):
        updated_sequence, allocated_model_ids, status = (
            apply_destroyed_transport_disembark_proposal_decision(
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                attack_sequence=attack_sequence,
                result=result,
                already_allocated_model_ids=already_allocated_model_ids,
            )
        )
    else:
        raise GameLifecycleError("Unsupported attack sequence decision type.")
    return updated_sequence, allocated_model_ids, status


def _validate_declaration_submission(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ShootingProposalValidationResult:
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and proposal.source_decision_request_id == out_of_phase_state.source_decision_request_id
        and proposal.source_decision_result_id == out_of_phase_state.source_decision_result_id
    ):
        return _validate_out_of_phase_declaration_submission(
            state=state,
            proposal=proposal,
            out_of_phase_state=out_of_phase_state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_target_restriction_hooks=shooting_target_restriction_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="wrong_context",
            message="Shooting declaration requires an active shooting selection.",
            field=None,
        )
    active_selection = shooting_state.active_selection
    if proposal.unit_instance_id != active_selection.unit_instance_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="proposal_unit_drift",
            message="Shooting declaration unit does not match active selection.",
            field="unit_instance_id",
        )
    if shooting_state.selected_shooting_type is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="shooting_type_not_selected",
            message="Shooting declaration requires a selected shooting type.",
            field="declarations",
        )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    if not _rules_unit_can_select_to_shoot(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
    ):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="shooting_unit_ineligible",
            message="Selected shooting unit is no longer eligible to shoot.",
            field="unit_instance_id",
        )
    attack_validation = _attack_pools_or_validation(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if isinstance(attack_validation, ShootingProposalValidationResult):
        return attack_validation
    return ShootingProposalValidationResult.valid(proposal_request_id=proposal.proposal_request_id)


def _validate_out_of_phase_declaration_submission(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    out_of_phase_state: OutOfPhaseShootingState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ShootingProposalValidationResult:
    if proposal.player_id != out_of_phase_state.player_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="proposal_player_drift",
            message="Out-of-phase shooting declaration player drift.",
            field="player_id",
        )
    if proposal.unit_instance_id != out_of_phase_state.selected_unit_instance_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="proposal_unit_drift",
            message="Out-of-phase shooting declaration unit drift.",
            field="unit_instance_id",
        )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    if not _rules_unit_can_select_to_shoot(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=out_of_phase_state.player_id,
    ):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="shooting_unit_ineligible",
            message="Out-of-phase shooting unit is no longer eligible to shoot.",
            field="unit_instance_id",
        )
    attack_validation = _attack_pools_or_validation(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_player_id=out_of_phase_state.player_id,
        out_of_phase_state=out_of_phase_state,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if isinstance(attack_validation, ShootingProposalValidationResult):
        return attack_validation
    return ShootingProposalValidationResult.valid(proposal_request_id=proposal.proposal_request_id)


def _attack_pools_for_proposal(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    decisions: DecisionController,
    result_id: str,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    shooting_player_id: str | None = None,
    out_of_phase_state: OutOfPhaseShootingState | None = None,
) -> tuple[tuple[RangedAttackPool, ...], tuple[str, ...]]:
    result = _attack_pools_or_validation(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        attack_count_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_count_scope_prefix=result_id,
        shooting_player_id=shooting_player_id,
        out_of_phase_state=out_of_phase_state,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if isinstance(result, ShootingProposalValidationResult):
        raise GameLifecycleError("Accepted shooting declaration failed revalidation.")
    return result


type _AttackPoolValidationResult = (
    tuple[tuple[RangedAttackPool, ...], tuple[str, ...]] | ShootingProposalValidationResult
)


def _attack_pools_or_validation(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    attack_count_manager: DiceRollManager | None = None,
    attack_count_scope_prefix: str | None = None,
    shooting_player_id: str | None = None,
    out_of_phase_state: OutOfPhaseShootingState | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> _AttackPoolValidationResult:
    player_id = proposal.player_id if shooting_player_id is None else shooting_player_id
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    selected_shooting_type = _selected_shooting_type_for_declaration(
        state=state,
        out_of_phase_state=out_of_phase_state,
    )
    available_weapon_by_key = _available_weapon_by_declaration_key_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=player_id,
        selected_shooting_type=selected_shooting_type,
    )
    firing_deck_validation = _validate_firing_deck_selection(
        state=state,
        proposal=proposal,
        army_catalog=army_catalog,
    )
    if isinstance(firing_deck_validation, ShootingProposalValidationResult):
        return firing_deck_validation
    ineligible_unit_ids = firing_deck_validation
    allowed_out_of_phase_target_ids = _out_of_phase_allowed_target_unit_ids(
        state,
        out_of_phase_state,
    )
    proposal_target_unit_ids = tuple(
        sorted({declaration.target_unit_instance_id for declaration in proposal.declarations})
    )
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=proposal_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=proposal_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=proposal_target_unit_ids,
    )
    attack_pools: list[RangedAttackPool] = []
    seen_declaration_keys: set[tuple[str, str, str, str | None, str | None]] = set()
    model_pistol_declaration_kind: dict[tuple[str, str], bool] = {}
    snap_target_unit_ids: set[str] = set()
    for declaration_index, declaration in enumerate(proposal.declarations, start=1):
        key = _declaration_available_weapon_key(declaration)
        if key in seen_declaration_keys:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="duplicate_weapon_declaration",
                message="Each model/wargear/profile/source declaration may be used once.",
                field="declarations",
            )
        seen_declaration_keys.add(key)
        weapon = available_weapon_by_key.get(key)
        if weapon is None:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_declaration_unavailable",
                message="Declared weapon is not available to the selected shooting unit.",
                field="declarations",
            )
        weapon_profile = weapon["weapon_profile"]
        if declaration.shooting_type is ShootingType.INDIRECT and not has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.INDIRECT_FIRE,
        ):
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="shooting_type_unavailable",
                message="Indirect shooting requires an Indirect Fire weapon profile.",
                field="declarations",
            )
        if (
            allowed_out_of_phase_target_ids is not None
            and declaration.target_unit_instance_id not in allowed_out_of_phase_target_ids
        ):
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="out_of_phase_target_unit_drift",
                message="Out-of-phase shooting declaration target is not allowed by its source.",
                field="declarations",
            )
        source_unit = _component_unit_for_declaration(
            rules_unit=rules_unit,
            declaration=declaration,
        )
        pistol_validation = _validate_model_pistol_exclusivity(
            state=state,
            selected_unit=source_unit,
            declaration=declaration,
            weapon_profile=weapon_profile,
            model_pistol_declaration_kind=model_pistol_declaration_kind,
            proposal_request_id=proposal.proposal_request_id,
        )
        if pistol_validation is not None:
            return pistol_validation
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            attacker_unit=source_unit,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            weapon_profile=weapon_profile,
            target_unit_id=declaration.target_unit_instance_id,
            terrain_features=terrain_features,
            hidden_target_unit_ids=hidden_target_unit_ids,
            target_unit_ids_with_recent_ranged_attacks=target_unit_ids_with_recent_ranged_attacks,
            target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                declaration.target_unit_instance_id,
                0,
            ),
        )
        candidate = _shooting_candidate_with_target_restrictions(
            candidate=candidate,
            state=state,
            player_id=player_id,
            attacking_unit_instance_id=source_unit.unit_instance_id,
            target_unit_instance_id=declaration.target_unit_instance_id,
            registry=shooting_target_restriction_hooks,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            shooting_type=declaration.shooting_type,
        )
        if not candidate.is_legal:
            violation = candidate.violation_code
            if violation is None:
                raise GameLifecycleError("Illegal target candidate requires violation_code.")
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code=f"target_{violation.value}",
                message=candidate.message or "Declared target is not legal.",
                field="declarations",
            )
        target_rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=declaration.target_unit_instance_id,
        )
        weapon_profile = weapon_profile_with_character_target_ap_effects(
            weapon_profile,
            state.persisting_effects_for_unit(source_unit.unit_instance_id),
            owner_player_id=player_id,
            target_keywords=target_rules_unit.keywords,
        )
        weapon_profile = _modified_shooting_weapon_profile(
            state=state,
            runtime_modifier_registry=_runtime_modifier_registry(runtime_modifier_registry),
            attacking_unit_instance_id=source_unit.unit_instance_id,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            target_unit_instance_id=declaration.target_unit_instance_id,
            profile=weapon_profile,
        )
        ability_selection_validation = _validate_duplicate_weapon_ability_selection(
            proposal=proposal,
            declaration=declaration,
            declaration_index=declaration_index,
            weapon_profile=weapon_profile,
            target_rules_unit=target_rules_unit,
            player_id=player_id,
        )
        if ability_selection_validation is not None:
            return ability_selection_validation
        allowed_shooting_types = _shooting_types_for_declaration_candidate(
            state=state,
            scenario=scenario,
            candidate=candidate,
            declaration=declaration,
            unit=source_unit,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            player_id=player_id,
            out_of_phase_state=out_of_phase_state,
            selected_shooting_type=selected_shooting_type,
            army_catalog=army_catalog,
        )
        if declaration.shooting_type not in allowed_shooting_types:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="shooting_type_unavailable",
                message="Declared shooting type is not available for this weapon and target.",
                field="declarations",
            )
        if declaration.shooting_type is ShootingType.SNAP:
            snap_target_unit_ids.add(declaration.target_unit_instance_id)
        if attack_count_manager is None:
            attacks = unresolved_attacks_for_validation(weapon_profile)
        else:
            if attack_count_scope_prefix is None:
                raise GameLifecycleError("Random Attacks resolution requires a scope prefix.")
            attacks = attacks_for_profile(
                weapon_profile,
                manager=attack_count_manager,
                scope_id=(
                    f"{attack_count_scope_prefix}:declaration-{declaration_index:03d}:"
                    f"{declaration.attacker_model_instance_id}:{declaration.wargear_id}:"
                    f"{declaration.weapon_profile_id}:{declaration.target_unit_instance_id}:"
                    "attacks"
                ),
                actor_id=proposal.player_id,
            )
        target_within_half_range = _target_within_half_weapon_range(
            scenario=scenario,
            declaration=declaration,
            weapon_profile=weapon_profile,
            target_in_range_model_ids=candidate.target_in_range_model_ids,
        )
        attacks, targeting_rule_ids, hit_roll_modifier = _apply_phase13d_weapon_modifiers(
            state=state,
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            rules_unit=rules_unit,
            target_rules_unit=target_rules_unit,
            weapon_profile=weapon_profile,
            shooting_type=declaration.shooting_type,
            base_attacks=attacks,
            base_targeting_rule_ids=candidate.targeting_rule_ids,
            base_hit_roll_modifier=candidate.hit_roll_modifier,
            target_within_half_range=target_within_half_range,
            terrain_features=terrain_features,
            player_id=player_id,
            out_of_phase_state=out_of_phase_state,
        )
        if _out_of_phase_uses_fire_overwatch(out_of_phase_state):
            targeting_rule_ids = (*targeting_rule_ids, FIRE_OVERWATCH_RULE_ID)
        targeting_rule_ids = _targeting_rule_ids_with_shooting_type(
            shooting_type=declaration.shooting_type,
            targeting_rule_ids=targeting_rule_ids,
        )
        attack_pools.append(
            RangedAttackPool.from_declaration(
                declaration=declaration,
                weapon_profile=weapon_profile,
                attacks=attacks,
                target_visible_model_ids=candidate.target_visible_model_ids,
                target_in_range_model_ids=candidate.target_in_range_model_ids,
                hit_roll_modifier=hit_roll_modifier,
                targeting_rule_ids=targeting_rule_ids,
            )
        )
    if len(snap_target_unit_ids) > 1:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="snap_shooting_multiple_targets",
            message="Snap Shooting declarations must target one enemy unit.",
            field="declarations",
        )
    return (tuple(attack_pools), ineligible_unit_ids)


def _validate_duplicate_weapon_ability_selection(
    *,
    proposal: ShootingDeclarationProposal,
    declaration: WeaponDeclaration,
    declaration_index: int,
    weapon_profile: WeaponProfile,
    target_rules_unit: RulesUnitView,
    player_id: str,
) -> ShootingProposalValidationResult | None:
    ability_by_id: dict[str, AbilityDescriptor] = {
        ability.ability_id: ability for ability in weapon_profile.abilities
    }
    selected_abilities: list[AbilityDescriptor] = []
    for selected_id in declaration.selected_weapon_ability_ids:
        selected_ability = ability_by_id.get(selected_id)
        if selected_ability is None:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_ability_selection_unavailable",
                message="Selected weapon ability ID is not on the declared weapon profile.",
                field="declarations",
            )
        if selected_ability.ability_kind is not AbilityKind.ANTI_KEYWORD:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_ability_selection_unsupported",
                message="This shooting declaration only supports duplicate Anti selections.",
                field="declarations",
            )
        selected_abilities.append(selected_ability)

    selected_anti_ids: tuple[str, ...] = tuple(
        ability.ability_id
        for ability in selected_abilities
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD
    )
    selection_request = weapon_ability_selection_request(
        weapon_profile,
        AbilityKind.ANTI_KEYWORD,
        target_keywords=target_rules_unit.keywords,
        actor_id=player_id,
        request_id=(
            f"{proposal.proposal_request_id}:declaration-{declaration_index:03d}:anti-keyword"
        ),
        source_context={
            "phase": BattlePhase.SHOOTING.value,
            "proposal_request_id": proposal.proposal_request_id,
            "declaration_index": declaration_index,
            "target_unit_instance_id": target_rules_unit.unit_instance_id,
        },
    )
    if selection_request is None:
        if selected_anti_ids:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_ability_selection_not_required",
                message="Selected Anti ability ID was supplied when no duplicate choice exists.",
                field="declarations",
            )
        return None

    legal_ids = {option.option_id for option in selection_request.options}
    if len(selected_anti_ids) != 1:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="weapon_ability_selection_required",
            message="Duplicate matching Anti abilities require exactly one selected ability ID.",
            field="declarations",
        )
    if selected_anti_ids[0] not in legal_ids:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="weapon_ability_selection_invalid",
            message="Selected Anti ability ID is not legal for this target.",
            field="declarations",
        )
    return None


def _shooting_candidate_with_target_restrictions(
    *,
    candidate: ShootingTargetCandidate,
    state: GameState,
    player_id: str,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    registry: ShootingTargetRestrictionHookRegistry | None,
    attacker_model_instance_id: str | None = None,
    shooting_type: ShootingType | None = None,
) -> ShootingTargetCandidate:
    if type(candidate) is not ShootingTargetCandidate:
        raise GameLifecycleError("Shooting target restriction requires a target candidate.")
    if not candidate.is_legal:
        return candidate
    if registry is None:
        return candidate
    if type(registry) is not ShootingTargetRestrictionHookRegistry:
        raise GameLifecycleError("Shooting target restriction requires a registry.")
    restrictions = registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id=player_id,
            battle_round=state.battle_round,
            attacking_unit_instance_id=attacking_unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            shooting_type=shooting_type,
        )
    )
    if not restrictions:
        return candidate
    restriction = restrictions[0]
    return ShootingTargetCandidate.invalid(
        attacker_unit_instance_id=candidate.attacker_unit_instance_id,
        weapon_profile_id=candidate.weapon_profile_id,
        target_unit_instance_id=candidate.target_unit_instance_id,
        violation_code=ShootingTargetViolationCode.RUNTIME_TARGET_RESTRICTION,
        message=restriction.message,
        visibility_cache_key=candidate.visibility_cache_key,
        target_visible_model_ids=candidate.target_visible_model_ids,
        target_in_range_model_ids=candidate.target_in_range_model_ids,
        line_of_sight_witness=candidate.line_of_sight_witness,
        observer_model_id=candidate.observer_model_id,
        hit_roll_modifier=candidate.hit_roll_modifier,
        targeting_rule_ids=(*candidate.targeting_rule_ids, restriction.hook_id),
    )


def _modified_shooting_weapon_profile(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    profile: WeaponProfile,
) -> WeaponProfile:
    return runtime_modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            weapon_profile=profile,
        )
    )


def _runtime_modifier_registry(
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if runtime_modifier_registry is None:
        return RuntimeModifierRegistry.empty()
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Runtime modifier registry must be a registry.")
    return runtime_modifier_registry


def _out_of_phase_allowed_target_unit_ids(
    state: GameState,
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> tuple[str, ...] | None:
    if not _out_of_phase_uses_fire_overwatch(out_of_phase_state):
        return None
    if out_of_phase_state is None:
        raise GameLifecycleError("Fire Overwatch out-of-phase state is missing.")
    source_context = out_of_phase_state.source_context
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Fire Overwatch source context must be an object.")
    triggering_unit_id = source_context.get("triggering_enemy_unit_instance_id")
    if type(triggering_unit_id) is not str:
        raise GameLifecycleError("Fire Overwatch source context is missing triggering unit id.")
    return (
        rules_unit_id_for_unit_id(
            armies=tuple(state.army_definitions),
            unit_instance_id=_validate_identifier(
                "Fire Overwatch triggering unit id",
                triggering_unit_id,
            ),
        ),
    )


def _out_of_phase_uses_fire_overwatch(
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> bool:
    return (
        out_of_phase_state is not None
        and out_of_phase_state.source_rule_id == FIRE_OVERWATCH_RULE_ID
    )


def _forced_shooting_type_for_out_of_phase(
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> ShootingType | None:
    if _out_of_phase_uses_fire_overwatch(out_of_phase_state):
        return ShootingType.SNAP
    return None


def _selected_shooting_type_for_declaration(
    *,
    state: GameState,
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> ShootingType | None:
    forced = _forced_shooting_type_for_out_of_phase(out_of_phase_state)
    if forced is not None:
        return forced
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        return None
    if shooting_state.selected_shooting_type is None:
        return None
    return shooting_state.selected_shooting_type.shooting_type


def _shooting_types_for_declaration_candidate(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    candidate: ShootingTargetCandidate,
    declaration: WeaponDeclaration,
    unit: UnitInstance,
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    player_id: str,
    out_of_phase_state: OutOfPhaseShootingState | None,
    selected_shooting_type: ShootingType | None,
    army_catalog: ArmyCatalog,
) -> tuple[ShootingType, ...]:
    forced_shooting_type = _forced_shooting_type_for_out_of_phase(out_of_phase_state)
    if forced_shooting_type is not None:
        if forced_shooting_type is not ShootingType.SNAP:
            raise GameLifecycleError("Unsupported forced shooting type.")
        if candidate.target_visible_model_ids and _declaration_target_within_max_range(
            scenario=scenario,
            declaration=declaration,
            target_in_range_model_ids=candidate.target_visible_model_ids,
            range_inches=24,
        ):
            return (ShootingType.SNAP,)
        return ()
    if selected_shooting_type is not None:
        return _shooting_types_for_selected_type_for_rules_unit(
            state=state,
            base_types=candidate.shooting_types,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            selected_shooting_type=selected_shooting_type,
            player_id=player_id,
            army_catalog=army_catalog,
        )
    if _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        if ShootingType.NORMAL in candidate.shooting_types and has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.ASSAULT,
        ):
            return (ShootingType.ASSAULT,)
        return ()
    return candidate.shooting_types


def _targeting_rule_ids_with_shooting_type(
    *,
    shooting_type: ShootingType,
    targeting_rule_ids: tuple[str, ...],
) -> tuple[str, ...]:
    rule_ids = list(targeting_rule_ids)
    if shooting_type is ShootingType.ASSAULT:
        rule_ids.append(ASSAULT_RULE_ID)
    elif shooting_type is ShootingType.CLOSE_QUARTERS:
        rule_ids.append(CLOSE_QUARTERS_RULE_ID)
    elif shooting_type is ShootingType.SNAP:
        rule_ids.append(SNAP_SHOOTING_RULE_ID)
    elif shooting_type in {ShootingType.NORMAL, ShootingType.INDIRECT}:
        pass
    else:
        raise GameLifecycleError("Unsupported shooting type for targeting rule IDs.")
    return tuple(dict.fromkeys(rule_ids))


def _validate_model_pistol_exclusivity(
    *,
    state: GameState,
    selected_unit: UnitInstance,
    declaration: WeaponDeclaration,
    weapon_profile: WeaponProfile,
    model_pistol_declaration_kind: dict[tuple[str, str], bool],
    proposal_request_id: str,
) -> ShootingProposalValidationResult | None:
    source_unit = _declaration_source_unit(
        state=state,
        selected_unit=selected_unit,
        declaration=declaration,
    )
    if _unit_has_vehicle_or_monster_keyword(source_unit):
        return None
    source_model_id = _declaration_source_model_id(declaration)
    model_key = (source_unit.unit_instance_id, source_model_id)
    is_close_quarters = has_close_quarters_weapon_keyword(weapon_profile)
    existing = model_pistol_declaration_kind.get(model_key)
    if existing is not None and existing != is_close_quarters:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="mixed_close_quarters_non_close_quarters_declaration",
            message=(
                "A non-Monster/Vehicle model cannot shoot close-quarters and "
                "non-close-quarters weapons together."
            ),
            field="declarations",
        )
    model_pistol_declaration_kind[model_key] = is_close_quarters
    return None


def _apply_phase13d_weapon_modifiers(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    target_rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    shooting_type: ShootingType,
    base_attacks: int,
    base_targeting_rule_ids: tuple[str, ...],
    base_hit_roll_modifier: int,
    target_within_half_range: bool,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    player_id: str | None = None,
    out_of_phase_state: OutOfPhaseShootingState | None = None,
) -> tuple[int, tuple[str, ...], int]:
    attacks = base_attacks
    hit_roll_modifier = base_hit_roll_modifier
    targeting_rule_ids: list[str] = list(base_targeting_rule_ids)

    rapid_bonus = rapid_fire_attack_bonus(
        weapon_profile,
        target_within_half_range=target_within_half_range,
    )
    if rapid_bonus > 0:
        attacks += rapid_bonus
        targeting_rule_ids.append(rapid_fire_rule_id(rapid_bonus))

    if has_weapon_keyword(weapon_profile, WeaponKeyword.BLAST):
        blast_bonus = blast_attack_bonus(target_model_count=len(target_rules_unit.alive_models()))
        if blast_bonus > 0:
            attacks += blast_bonus
            targeting_rule_ids.append(blast_rule_id(blast_bonus))

    melta_bonus = melta_damage_bonus(
        weapon_profile,
        target_within_half_range=target_within_half_range,
    )
    if melta_bonus > 0:
        targeting_rule_ids.append(melta_rule_id(melta_bonus))

    if has_weapon_keyword(
        weapon_profile,
        WeaponKeyword.HEAVY,
    ) and _heavy_hit_roll_modifier_applies(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        player_id=player_id,
        out_of_phase_state=out_of_phase_state,
    ):
        hit_roll_modifier += 1
        targeting_rule_ids.append(heavy_rule_id())

    if shooting_type is ShootingType.INDIRECT and has_weapon_keyword(
        weapon_profile, WeaponKeyword.INDIRECT_FIRE
    ):
        if INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID not in targeting_rule_ids:
            targeting_rule_ids.append(INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID)
        targeting_rule_ids.append(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID)
        if _rules_unit_remained_stationary(
            state=state,
            rules_unit=rules_unit,
            player_id=player_id,
        ) and (
            _target_visible_to_friendly_unit(
                state=state,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                target_unit_instance_id=target_rules_unit.unit_instance_id,
                terrain_features=terrain_features,
                player_id=player_id,
            )
        ):
            targeting_rule_ids.append(INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID)

    return attacks, tuple(dict.fromkeys(targeting_rule_ids)), hit_roll_modifier


def _target_within_half_weapon_range(
    *,
    scenario: BattlefieldScenario,
    declaration: WeaponDeclaration,
    weapon_profile: WeaponProfile,
    target_in_range_model_ids: tuple[str, ...],
) -> bool:
    range_inches = weapon_profile.range_profile.distance_inches
    if range_inches is None:
        raise GameLifecycleError("Half-range weapon modifier requires a ranged weapon.")
    if not target_in_range_model_ids:
        return False
    battlefield = scenario.battlefield_state
    attacker_placement = battlefield.model_placement_by_id(declaration.attacker_model_instance_id)
    attacker_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(attacker_placement),
        placement=attacker_placement,
    )
    half_range = float(range_inches) / 2.0
    for target_model_id in target_in_range_model_ids:
        target_placement = battlefield.model_placement_by_id(target_model_id)
        target_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(target_placement),
            placement=target_placement,
        )
        distance = DistanceMeasurementContext.from_models(
            attacker_model,
            target_model,
        ).closest_distance_inches()
        if distance <= half_range:
            return True
    return False


def _snap_shooting_type_allowed_for_unit_target(
    *,
    scenario: BattlefieldScenario,
    candidate: dict[str, JsonValue],
    unit: UnitInstance,
    target_unit_id: str,
) -> bool:
    target_visible_model_ids = candidate.get("target_visible_model_ids")
    if not isinstance(target_visible_model_ids, list) or not target_visible_model_ids:
        return False
    return _unit_target_within_max_range(
        scenario=scenario,
        unit=unit,
        target_unit_id=target_unit_id,
        range_inches=24,
    )


def _declaration_target_within_max_range(
    *,
    scenario: BattlefieldScenario,
    declaration: WeaponDeclaration,
    target_in_range_model_ids: tuple[str, ...],
    range_inches: int,
) -> bool:
    if not target_in_range_model_ids:
        return False
    battlefield = scenario.battlefield_state
    attacker_placement = battlefield.model_placement_by_id(declaration.attacker_model_instance_id)
    attacker_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(attacker_placement),
        placement=attacker_placement,
    )
    for target_model_id in target_in_range_model_ids:
        target_placement = battlefield.model_placement_by_id(target_model_id)
        target_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(target_placement),
            placement=target_placement,
        )
        if DistanceMeasurementContext.from_models(
            attacker_model,
            target_model,
        ).closest_distance_inches() <= float(range_inches):
            return True
    return False


def _unit_target_within_max_range(
    *,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    target_unit_id: str,
    range_inches: int,
) -> bool:
    battlefield = scenario.battlefield_state
    unit_placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
    target_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=target_unit_id,
    )
    target_placements = _unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if target_placements is None:
        return False
    for attacker_model_placement in unit_placement.model_placements:
        attacker_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(attacker_model_placement),
            placement=attacker_model_placement,
        )
        for target_placement in target_placements:
            for target_model_placement in target_placement.model_placements:
                target_model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(target_model_placement),
                    placement=target_model_placement,
                )
                if DistanceMeasurementContext.from_models(
                    attacker_model,
                    target_model,
                ).closest_distance_inches() <= float(range_inches):
                    return True
    return False


def _unit_placements_for_rules_unit_or_none(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[UnitPlacement, ...] | None:
    placements: list[UnitPlacement] = []
    for component in rules_unit.components:
        try:
            placements.append(
                scenario.battlefield_state.unit_placement_by_id(component.unit.unit_instance_id)
            )
        except PlacementError as exc:
            if not any(model.is_alive for model in component.unit.own_models):
                continue
            raise GameLifecycleError("Shooting rules-unit component is not placed.") from exc
    if not placements:
        return None
    return tuple(sorted(placements, key=lambda placement: placement.unit_instance_id))


def _rules_unit_remained_stationary(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    unit_ids = _rules_unit_state_unit_ids(rules_unit)
    if _rules_unit_set_up_this_turn(
        state=state,
        unit_ids=unit_ids,
        player_id=actor_id,
    ):
        return False
    for unit_id in unit_ids:
        advanced_state = state.advanced_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if advanced_state is not None:
            return False
        fell_back_state = state.fell_back_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if fell_back_state is not None:
            return False
    movement_state = state.movement_phase_state
    if movement_state is None:
        return True
    movement_unit_ids = set(movement_state.moved_unit_ids)
    if not movement_unit_ids.intersection(unit_ids):
        return True
    for record in movement_state.movement_distance_records:
        if record.unit_instance_id in unit_ids:
            return record.maximum_model_distance_inches <= 3.0
    return False


def _heavy_hit_roll_modifier_applies(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    player_id: str | None,
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    if out_of_phase_state is not None:
        return False
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return False
    if _active_player_id(state) != actor_id:
        return False
    if _rules_unit_within_enemy_engagement_range(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        player_id=actor_id,
    ):
        return False
    return _rules_unit_remained_stationary(
        state=state,
        rules_unit=rules_unit,
        player_id=actor_id,
    )


def _rules_unit_set_up_this_turn(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    player_id: str,
) -> bool:
    for unit_id in unit_ids:
        reserve_state = state.reserve_state_for_unit(unit_id)
        if (
            reserve_state is not None
            and reserve_state.player_id == player_id
            and reserve_state.arrived_battle_round == state.battle_round
        ):
            return True
        disembarked_state = state.disembarked_unit_state_for_unit(
            player_id=player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if disembarked_state is not None and not disembarked_state.can_choose_remain_stationary:
            return True
    return False


def _rules_unit_within_enemy_engagement_range(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    player_id: str,
) -> bool:
    unit_placements = _unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if unit_placements is None:
        return False
    policy = ruleset_descriptor.engagement_policy
    friendly_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for unit_placement in unit_placements
        for model_placement in unit_placement.model_placements
    )
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        for enemy_unit_placement in placed_army.unit_placements:
            for enemy_model_placement in enemy_unit_placement.model_placements:
                enemy_model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(enemy_model_placement),
                    placement=enemy_model_placement,
                )
                if any(
                    friendly_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=policy.horizontal_inches,
                        vertical_inches=policy.vertical_inches,
                    )
                    for friendly_model in friendly_models
                ):
                    return True
    return False


def _target_visible_to_friendly_unit(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    target_unit_instance_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Friendly visibility query requires battlefield_state.")
    try:
        placed_army = battlefield.placed_army_for_player(actor_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Friendly visibility query requires placed friendly units."
        ) from exc
    for unit_placement in placed_army.unit_placements:
        if unit_placement.unit_instance_id == target_unit_instance_id:
            raise GameLifecycleError("Friendly visibility query included the target unit.")
        friendly_unit = _unit_by_id(state=state, unit_instance_id=unit_placement.unit_instance_id)
        if unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            observing_unit=friendly_unit,
            target_unit_id=target_unit_instance_id,
            terrain_features=terrain_features,
        ):
            return True
    return False


def _declaration_source_unit(
    *,
    state: GameState,
    selected_unit: UnitInstance,
    declaration: WeaponDeclaration,
) -> UnitInstance:
    source_unit_id = declaration.firing_deck_source_unit_instance_id
    if source_unit_id is None:
        return selected_unit
    return _unit_by_id(state=state, unit_instance_id=source_unit_id)


def _declaration_source_model_id(declaration: WeaponDeclaration) -> str:
    source_model_id = declaration.firing_deck_source_model_instance_id
    if source_model_id is not None:
        return source_model_id
    return declaration.attacker_model_instance_id


def _validate_firing_deck_selection(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    army_catalog: ArmyCatalog,
) -> tuple[str, ...] | ShootingProposalValidationResult:
    firing_deck_declarations = tuple(
        declaration for declaration in proposal.declarations if declaration.uses_firing_deck
    )
    if not firing_deck_declarations:
        if proposal.firing_deck_selection is not None:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="firing_deck_selection_without_declaration",
                message="Firing Deck selection requires Firing Deck declarations.",
                field="firing_deck_selection",
            )
        return ()
    selection = proposal.firing_deck_selection
    if selection is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_selection_missing",
            message="Firing Deck declarations require a Firing Deck selection payload.",
            field="firing_deck_selection",
        )
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Firing Deck validation requires shooting_phase_state.")
    if selection.player_id != _active_player_id(state):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_player_drift",
            message="Firing Deck selection player_id does not match active player.",
            field="firing_deck_selection",
        )
    if selection.battle_round != state.battle_round:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_battle_round_drift",
            message="Firing Deck selection battle_round does not match current round.",
            field="firing_deck_selection",
        )
    if selection.transport_unit_instance_id != proposal.unit_instance_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_transport_drift",
            message="Firing Deck selection transport does not match shooting unit.",
            field="firing_deck_selection",
        )
    transport_unit = _unit_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    firing_deck_value = _firing_deck_value_for_unit(
        unit=transport_unit,
        army_catalog=army_catalog,
    )
    if firing_deck_value is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_ability_missing",
            message="Firing Deck declarations require a Firing Deck ability descriptor.",
            field="firing_deck_selection",
        )
    if selection.firing_deck_value != firing_deck_value:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_value_drift",
            message="Firing Deck selection value does not match engine rules.",
            field="firing_deck_selection",
        )
    if selection.already_shot_unit_instance_ids != shooting_state.shot_unit_ids:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_shot_state_drift",
            message="Firing Deck selection shot-state evidence does not match engine state.",
            field="firing_deck_selection",
        )
    weapon_selection_keys = {
        (
            weapon_selection.embarked_unit_instance_id,
            weapon_selection.model_instance_id,
            weapon_selection.wargear_id,
            weapon_selection.weapon_profile.profile_id,
        )
        for weapon_selection in selection.weapon_selections
    }
    declaration_keys = {
        (
            declaration.firing_deck_source_unit_instance_id,
            declaration.firing_deck_source_model_instance_id,
            declaration.wargear_id,
            declaration.weapon_profile_id,
        )
        for declaration in firing_deck_declarations
    }
    if weapon_selection_keys != declaration_keys:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_weapon_selection_drift",
            message="Firing Deck selected weapons do not match declarations.",
            field="firing_deck_selection",
        )
    for weapon_selection in selection.weapon_selections:
        validation = _validate_firing_deck_weapon_against_catalog(
            state=state,
            weapon_selection=weapon_selection,
            army_catalog=army_catalog,
            proposal_request_id=proposal.proposal_request_id,
        )
        if validation is not None:
            return validation
    cargo_state = state.transport_cargo_state_for_transport(proposal.unit_instance_id)
    if cargo_state is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_transport_cargo_missing",
            message="Firing Deck requires a Transport cargo state.",
            field="firing_deck_selection",
        )
    resolution = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=selection,
        embarked_units=tuple(
            _unit_by_id(state=state, unit_instance_id=unit_id)
            for unit_id in cargo_state.embarked_unit_instance_ids
        ),
    )
    if not resolution.is_valid:
        violation = resolution.violations[0]
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code=violation.violation_code.value,
            message=violation.message,
            field="firing_deck_selection",
        )
    return resolution.ineligible_unit_instance_ids


def _validate_firing_deck_weapon_against_catalog(
    *,
    state: GameState,
    weapon_selection: FiringDeckWeaponSelection,
    army_catalog: ArmyCatalog,
    proposal_request_id: str,
) -> ShootingProposalValidationResult | None:
    embarked_unit = _unit_by_id(
        state=state, unit_instance_id=weapon_selection.embarked_unit_instance_id
    )
    model = _model_by_id(embarked_unit, weapon_selection.model_instance_id)
    if model is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="firing_deck_model_drift",
            message="Firing Deck selected model is not in the embarked unit.",
            field="firing_deck_selection",
        )
    if not _model_has_wargear_id(embarked_unit, model, weapon_selection.wargear_id):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="firing_deck_wargear_drift",
            message="Firing Deck selected wargear is not equipped by the embarked model.",
            field="firing_deck_selection",
        )
    catalog_profile = _weapon_profile_for_wargear(
        army_catalog=army_catalog,
        wargear_id=weapon_selection.wargear_id,
        weapon_profile_id=weapon_selection.weapon_profile.profile_id,
    )
    if catalog_profile != weapon_selection.weapon_profile:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="firing_deck_weapon_profile_drift",
            message="Firing Deck selected weapon profile does not match the catalog.",
            field="firing_deck_selection",
        )
    return None


def _available_weapon_by_declaration_key_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> dict[tuple[str, str, str, str | None, str | None], _AvailableWeapon]:
    return {
        _available_weapon_key(weapon): weapon
        for weapon in _available_weapons_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
            army_catalog=army_catalog,
            player_id=player_id,
            selected_shooting_type=selected_shooting_type,
        )
    }


def _available_weapon_key(
    weapon: _AvailableWeapon,
) -> tuple[str, str, str, str | None, str | None]:
    return (
        weapon["model_instance_id"],
        weapon["wargear_id"],
        weapon["weapon_profile"].profile_id,
        weapon.get("firing_deck_source_unit_instance_id"),
        weapon.get("firing_deck_source_model_instance_id"),
    )


def _component_unit_for_available_weapon(
    *,
    rules_unit: RulesUnitView,
    weapon: _AvailableWeapon,
) -> UnitInstance:
    return _component_unit_by_id(
        rules_unit=rules_unit,
        unit_instance_id=rules_unit.component_unit_id_for_model(weapon["model_instance_id"]),
    )


def _component_unit_for_declaration(
    *,
    rules_unit: RulesUnitView,
    declaration: WeaponDeclaration,
) -> UnitInstance:
    return _component_unit_by_id(
        rules_unit=rules_unit,
        unit_instance_id=rules_unit.component_unit_id_for_model(
            declaration.attacker_model_instance_id
        ),
    )


def _component_unit_by_id(*, rules_unit: RulesUnitView, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("component unit_instance_id", unit_instance_id)
    for component in rules_unit.components:
        if component.unit.unit_instance_id == requested_id:
            return component.unit
    raise GameLifecycleError("Rules-unit component unit_instance_id is unknown.")


def _declaration_available_weapon_key(
    declaration: WeaponDeclaration,
) -> tuple[str, str, str, str | None, str | None]:
    return (
        declaration.attacker_model_instance_id,
        declaration.wargear_id,
        declaration.weapon_profile_id,
        declaration.firing_deck_source_unit_instance_id,
        declaration.firing_deck_source_model_instance_id,
    )


def _available_weapons_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> tuple[_AvailableWeapon, ...]:
    weapons: list[_AvailableWeapon] = []
    for model in unit.own_models:
        weapons.extend(
            _available_own_weapons_for_model(
                state=state,
                model=model,
                unit=unit,
                army_catalog=army_catalog,
                player_id=player_id,
            )
        )
    weapons.extend(
        _available_firing_deck_weapons(
            state=state,
            transport_unit=unit,
            army_catalog=army_catalog,
        )
    )
    if (
        selected_shooting_type is ShootingType.ASSAULT
        or _advanced_unit_is_restricted_to_assault_weapons(
            state=state,
            unit=unit,
            player_id=player_id,
        )
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    if (
        selected_shooting_type is ShootingType.CLOSE_QUARTERS
        and not _unit_has_vehicle_or_monster_keyword(unit)
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_close_quarters_weapon_keyword(weapon["weapon_profile"])
        ]
    if selected_shooting_type is ShootingType.INDIRECT:
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.INDIRECT_FIRE)
        ]
    if selected_shooting_type is ShootingType.NORMAL and _unit_advanced_this_turn(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is ShootingType.INDIRECT and _unit_advanced_this_turn(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is None and _advanced_unit_is_restricted_to_assault_weapons(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    return tuple(
        sorted(
            weapons,
            key=lambda weapon: (
                weapon.get("firing_deck_source_unit_instance_id") or "",
                weapon.get("firing_deck_source_model_instance_id") or "",
                weapon["model_instance_id"],
                weapon["wargear_id"],
                weapon["weapon_profile"].profile_id,
            ),
        )
    )


def _available_weapons_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> tuple[_AvailableWeapon, ...]:
    weapons: list[_AvailableWeapon] = []
    for component in rules_unit.components:
        weapons.extend(
            _available_weapons_for_unit(
                state=state,
                unit=component.unit,
                army_catalog=army_catalog,
                player_id=player_id,
                selected_shooting_type=selected_shooting_type,
            )
        )
    if (
        selected_shooting_type is ShootingType.ASSAULT
        or _rules_unit_advanced_is_restricted_to_assault_weapons(
            state=state,
            rules_unit=rules_unit,
            player_id=player_id,
        )
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    if (
        selected_shooting_type is ShootingType.CLOSE_QUARTERS
        and not _rules_unit_has_vehicle_or_monster_keyword(rules_unit)
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_close_quarters_weapon_keyword(weapon["weapon_profile"])
        ]
    if selected_shooting_type is ShootingType.INDIRECT:
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.INDIRECT_FIRE)
        ]
    if selected_shooting_type is ShootingType.NORMAL and _rules_unit_advanced_this_turn(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is ShootingType.INDIRECT and _rules_unit_advanced_this_turn(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is None and _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    return tuple(
        sorted(
            weapons,
            key=lambda weapon: (
                weapon.get("firing_deck_source_unit_instance_id") or "",
                weapon.get("firing_deck_source_model_instance_id") or "",
                weapon["model_instance_id"],
                weapon["wargear_id"],
                weapon["weapon_profile"].profile_id,
            ),
        )
    )


def _available_weapons_for_model(
    *,
    model: ModelInstance,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
) -> tuple[_AvailableWeapon, ...]:
    weapons: list[_AvailableWeapon] = []
    for selection in unit.wargear_selections:
        if selection.model_profile_id != model.model_profile_id:
            continue
        for wargear_id in selection.wargear_ids:
            wargear = _wargear_by_id(army_catalog=army_catalog, wargear_id=wargear_id)
            for profile in wargear.weapon_profiles:
                if profile.range_profile.kind is RangeProfileKind.MELEE:
                    continue
                weapons.append(
                    {
                        "model_instance_id": model.model_instance_id,
                        "wargear_id": wargear_id,
                        "weapon_profile": profile,
                    }
                )
    return tuple(weapons)


def _available_own_weapons_for_model(
    *,
    state: GameState,
    model: ModelInstance,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None,
) -> tuple[_AvailableWeapon, ...]:
    owner_player_id = (
        rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id).owner_player_id
        if player_id is None
        else player_id
    )
    effects = state.persisting_effects_for_unit(unit.unit_instance_id)
    weapons: list[_AvailableWeapon] = []
    for weapon in _available_weapons_for_model(
        model=model,
        unit=unit,
        army_catalog=army_catalog,
    ):
        weapon_profile = weapon_profile_with_ranged_keyword_effects(
            weapon["weapon_profile"],
            effects,
            owner_player_id=owner_player_id,
        )
        if has_weapon_keyword(weapon_profile, WeaponKeyword.ONE_SHOT) and not (
            state.one_shot_weapon_available(
                model_instance_id=weapon["model_instance_id"],
                wargear_id=weapon["wargear_id"],
                weapon_profile_id=weapon_profile.profile_id,
            )
        ):
            continue
        weapons.append(
            {
                "model_instance_id": weapon["model_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile": weapon_profile,
            }
        )
    return tuple(weapons)


def _available_firing_deck_weapons(
    *,
    state: GameState,
    transport_unit: UnitInstance,
    army_catalog: ArmyCatalog,
) -> tuple[_AvailableWeapon, ...]:
    cargo_state = state.transport_cargo_state_for_transport(transport_unit.unit_instance_id)
    if cargo_state is None or not cargo_state.embarked_unit_instance_ids:
        return ()
    if not _unit_has_keyword(transport_unit, "TRANSPORT"):
        return ()
    if _firing_deck_value_for_unit(unit=transport_unit, army_catalog=army_catalog) is None:
        return ()
    transport_model = _transport_firing_deck_model(transport_unit)
    weapons: list[_AvailableWeapon] = []
    for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
        if _unit_has_already_shot(state=state, unit_instance_id=embarked_unit_id):
            continue
        embarked_unit = _unit_by_id(state=state, unit_instance_id=embarked_unit_id)
        for source_model in embarked_unit.own_models:
            for weapon in _available_weapons_for_model(
                model=source_model,
                unit=embarked_unit,
                army_catalog=army_catalog,
            ):
                if WeaponKeyword.ONE_SHOT in weapon["weapon_profile"].keywords:
                    continue
                weapons.append(
                    {
                        "model_instance_id": transport_model.model_instance_id,
                        "wargear_id": weapon["wargear_id"],
                        "weapon_profile": weapon["weapon_profile"],
                        "firing_deck_source_unit_instance_id": embarked_unit.unit_instance_id,
                        "firing_deck_source_model_instance_id": source_model.model_instance_id,
                    }
                )
    return tuple(weapons)


def _transport_firing_deck_model(unit: UnitInstance) -> ModelInstance:
    if not unit.own_models:
        raise GameLifecycleError("Transport unit requires at least one model.")
    return unit.own_models[0]


def _available_weapon_to_payload(weapon: _AvailableWeapon) -> AvailableWeaponPayload:
    payload: AvailableWeaponPayload = {
        "model_instance_id": weapon["model_instance_id"],
        "wargear_id": weapon["wargear_id"],
        "weapon_profile_id": weapon["weapon_profile"].profile_id,
        "weapon_profile": weapon["weapon_profile"].to_payload(),
    }
    source_unit_id = weapon.get("firing_deck_source_unit_instance_id")
    source_model_id = weapon.get("firing_deck_source_model_instance_id")
    if source_unit_id is not None and source_model_id is not None:
        payload["firing_deck_source_unit_instance_id"] = source_unit_id
        payload["firing_deck_source_model_instance_id"] = source_model_id
    return payload


def _legal_shooting_unit_ids(
    *,
    state: GameState,
    shooting_state: ShootingPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> tuple[str, ...]:
    scenario = _battlefield_scenario(state)
    active_player_id = _active_player_id(state)
    placed_unit_ids = _active_player_placed_unit_ids(state=state, player_id=active_player_id)
    legal: list[str] = []
    for unit_id in placed_unit_ids:
        if (
            unit_id in shooting_state.selected_unit_ids
            or unit_id in shooting_state.shot_unit_ids
            or unit_id in shooting_state.skipped_unit_ids
        ):
            continue
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        if not _rules_unit_can_select_to_shoot(
            state=state,
            rules_unit=rules_unit,
            army_catalog=army_catalog,
        ):
            continue
        if _rules_unit_has_legal_shooting_declaration(
            state=state,
            scenario=scenario,
            rules_unit=rules_unit,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        ):
            legal.append(rules_unit.unit_instance_id)
    return tuple(sorted(legal))


def _rules_unit_has_legal_shooting_declaration(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    selected_shooting_type: ShootingType | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    terrain_features = _terrain_features_for_state(state)
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    candidate_cache: _ShootingModelCandidateCache = {}
    for weapon in _available_weapons_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=actor_id,
        selected_shooting_type=selected_shooting_type,
    ):
        attacker_unit = _component_unit_for_available_weapon(
            rules_unit=rules_unit,
            weapon=weapon,
        )
        for target_unit_id in resolved_target_unit_ids:
            candidate = _cached_shooting_target_candidate_for_model(
                cache=candidate_cache,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                attacker_unit=attacker_unit,
                weapon=weapon,
                target_unit_id=target_unit_id,
                terrain_features=terrain_features,
                hidden_target_unit_ids=hidden_target_unit_ids,
                target_unit_ids_with_recent_ranged_attacks=(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                    target_unit_id,
                    0,
                ),
                shooting_target_restriction_hooks=shooting_target_restriction_hooks,
                state=state,
                player_id=actor_id,
            )
            if not candidate.is_legal:
                continue
            if selected_shooting_type is None:
                return True
            if _shooting_types_for_selected_type_for_rules_unit(
                state=state,
                base_types=candidate.shooting_types,
                rules_unit=rules_unit,
                weapon_profile=weapon["weapon_profile"],
                selected_shooting_type=selected_shooting_type,
                player_id=actor_id,
                army_catalog=army_catalog,
            ):
                return True
    return False


def _hidden_target_unit_ids(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            target_unit_id
            for target_unit_id in _validate_identifier_tuple(
                "hidden target target_unit_ids",
                target_unit_ids,
            )
            if unit_is_hidden_by_effects(state.persisting_effects_for_unit(target_unit_id))
        )
    )


def _detection_range_bonus_inches_by_target_id(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
) -> dict[str, int]:
    shot_source_unit_ids = _shot_source_unit_ids_for_detection_effects(state)
    bonuses: dict[str, int] = {}
    for target_unit_id in _validate_identifier_tuple(
        "detection range target_unit_ids",
        target_unit_ids,
    ):
        bonus_inches = detection_range_bonus_inches_for_effects(
            state.persisting_effects_for_unit(target_unit_id),
            shot_source_unit_ids=shot_source_unit_ids,
        )
        if bonus_inches > 0:
            bonuses[target_unit_id] = bonus_inches
    return bonuses


def _shot_source_unit_ids_for_detection_effects(state: GameState) -> tuple[str, ...]:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return ()
    return shooting_state.shot_unit_ids


def _target_unit_ids_with_recent_ranged_attacks(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            target_unit_id
            for target_unit_id in _validate_identifier_tuple(
                "recent ranged attack target_unit_ids",
                target_unit_ids,
            )
            if state.unit_made_ranged_attacks_current_or_previous_turn(
                unit_instance_id=target_unit_id,
            )
        )
    )


def _targeting_detection_context_fingerprint(
    *,
    hidden_target_unit_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    detection_range_bonus_by_target_id: dict[str, int],
) -> str:
    return canonical_json(
        validate_json_value(
            {
                "hidden_target_unit_ids": list(hidden_target_unit_ids),
                "target_unit_ids_with_recent_ranged_attacks": list(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                "detection_range_bonus_by_target_id": detection_range_bonus_by_target_id,
            }
        )
    )


def _unit_has_legal_shooting_declaration(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    selected_shooting_type: ShootingType | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    terrain_features = _terrain_features_for_state(state)
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    candidate_cache: _ShootingModelCandidateCache = {}
    for weapon in _available_weapons_for_unit(
        state=state,
        unit=unit,
        army_catalog=army_catalog,
        player_id=actor_id,
        selected_shooting_type=selected_shooting_type,
    ):
        for target_unit_id in resolved_target_unit_ids:
            candidate = _cached_shooting_target_candidate_for_model(
                cache=candidate_cache,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                attacker_unit=unit,
                weapon=weapon,
                target_unit_id=target_unit_id,
                terrain_features=terrain_features,
                hidden_target_unit_ids=hidden_target_unit_ids,
                target_unit_ids_with_recent_ranged_attacks=(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                    target_unit_id,
                    0,
                ),
                shooting_target_restriction_hooks=shooting_target_restriction_hooks,
                state=state,
                player_id=actor_id,
            )
            if not candidate.is_legal:
                continue
            if selected_shooting_type is None:
                return True
            if _shooting_types_for_selected_type(
                state=state,
                base_types=candidate.shooting_types,
                unit=unit,
                weapon_profile=weapon["weapon_profile"],
                selected_shooting_type=selected_shooting_type,
                player_id=actor_id,
                army_catalog=army_catalog,
            ):
                return True
    return False


def _legal_shooting_types_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> tuple[ShootingType, ...]:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    candidate_cache: _ShootingModelCandidateCache = {}
    legal_types: set[ShootingType] = set()
    for shooting_type in (
        ShootingType.NORMAL,
        ShootingType.ASSAULT,
        ShootingType.CLOSE_QUARTERS,
        ShootingType.INDIRECT,
    ):
        for weapon in _available_weapons_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
            army_catalog=army_catalog,
            player_id=actor_id,
            selected_shooting_type=shooting_type,
        ):
            attacker_unit = _component_unit_for_available_weapon(
                rules_unit=rules_unit,
                weapon=weapon,
            )
            for target_unit_id in resolved_target_unit_ids:
                candidate = _cached_shooting_target_candidate_for_model(
                    cache=candidate_cache,
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    attacker_unit=attacker_unit,
                    weapon=weapon,
                    target_unit_id=target_unit_id,
                    terrain_features=terrain_features,
                    hidden_target_unit_ids=hidden_target_unit_ids,
                    target_unit_ids_with_recent_ranged_attacks=(
                        target_unit_ids_with_recent_ranged_attacks
                    ),
                    target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                        target_unit_id,
                        0,
                    ),
                    shooting_target_restriction_hooks=shooting_target_restriction_hooks,
                    state=state,
                    player_id=actor_id,
                )
                if not candidate.is_legal:
                    continue
                if _shooting_types_for_selected_type_for_rules_unit(
                    state=state,
                    base_types=candidate.shooting_types,
                    rules_unit=rules_unit,
                    weapon_profile=weapon["weapon_profile"],
                    selected_shooting_type=shooting_type,
                    player_id=actor_id,
                    army_catalog=army_catalog,
                ):
                    legal_types.add(shooting_type)
                    break
            if shooting_type in legal_types:
                break
    return tuple(
        shooting_type
        for shooting_type in (
            ShootingType.NORMAL,
            ShootingType.ASSAULT,
            ShootingType.CLOSE_QUARTERS,
            ShootingType.INDIRECT,
        )
        if shooting_type in legal_types
    )


def _cached_shooting_target_candidate_for_model(
    *,
    cache: _ShootingModelCandidateCache,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    weapon: _AvailableWeapon,
    target_unit_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    hidden_target_unit_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    target_detection_range_bonus_inches: int,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
    state: GameState | None = None,
    player_id: str | None = None,
) -> ShootingTargetCandidate:
    cache_key = _shooting_model_candidate_cache_key(
        weapon=weapon,
        target_unit_id=target_unit_id,
        target_is_hidden=target_unit_id in hidden_target_unit_ids,
        target_made_recent_ranged_attacks=(
            target_unit_id in target_unit_ids_with_recent_ranged_attacks
        ),
        target_detection_range_bonus_inches=target_detection_range_bonus_inches,
    )
    if cache_key not in cache:
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            attacker_unit=attacker_unit,
            attacker_model_instance_id=weapon["model_instance_id"],
            weapon_profile=weapon["weapon_profile"],
            target_unit_id=target_unit_id,
            terrain_features=terrain_features,
            hidden_target_unit_ids=hidden_target_unit_ids,
            target_unit_ids_with_recent_ranged_attacks=(target_unit_ids_with_recent_ranged_attacks),
            target_detection_range_bonus_inches=target_detection_range_bonus_inches,
        )
        if shooting_target_restriction_hooks is not None:
            if state is None or player_id is None:
                raise GameLifecycleError("Shooting target restriction requires state/player.")
            candidate = _shooting_candidate_with_target_restrictions(
                candidate=candidate,
                state=state,
                player_id=player_id,
                attacking_unit_instance_id=attacker_unit.unit_instance_id,
                target_unit_instance_id=target_unit_id,
                registry=shooting_target_restriction_hooks,
                attacker_model_instance_id=weapon["model_instance_id"],
                shooting_type=None,
            )
        cache[cache_key] = candidate
    return cache[cache_key]


def _shooting_unit_candidate_cache_key(
    weapon: _AvailableWeapon,
    attacker_unit: UnitInstance,
    detection_context_fingerprint: str,
) -> _ShootingUnitCandidateCacheKey:
    profile = weapon["weapon_profile"]
    return (
        attacker_unit.unit_instance_id,
        weapon["wargear_id"],
        profile.profile_id,
        _weapon_profile_cache_fingerprint(profile),
        detection_context_fingerprint,
    )


def _shooting_model_candidate_cache_key(
    *,
    weapon: _AvailableWeapon,
    target_unit_id: str,
    target_is_hidden: bool,
    target_made_recent_ranged_attacks: bool,
    target_detection_range_bonus_inches: int,
) -> _ShootingModelCandidateCacheKey:
    profile = weapon["weapon_profile"]
    return (
        weapon["model_instance_id"],
        weapon["wargear_id"],
        profile.profile_id,
        weapon.get("firing_deck_source_unit_instance_id"),
        weapon.get("firing_deck_source_model_instance_id"),
        _weapon_profile_cache_fingerprint(profile),
        target_unit_id,
        target_is_hidden,
        target_made_recent_ranged_attacks,
        target_detection_range_bonus_inches,
    )


def _weapon_profile_cache_fingerprint(weapon_profile: WeaponProfile) -> str:
    return canonical_json(weapon_profile.to_payload())


def shooting_unit_can_select_to_shoot(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> bool:
    return _unit_can_select_to_shoot(
        state=state,
        unit=unit,
        army_catalog=army_catalog,
        player_id=player_id,
    )


def shooting_unit_has_legal_declaration_against_targets(
    *,
    state: GameState,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
    target_unit_ids: tuple[str, ...],
) -> bool:
    return _unit_has_legal_shooting_declaration(
        state=state,
        scenario=_battlefield_scenario(state),
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
    )


def _rules_unit_state_unit_ids(rules_unit: RulesUnitView) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )


def _unit_can_select_to_shoot(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    advanced_state = state.advanced_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    if (
        advanced_state is not None
        and not advanced_state.can_shoot
        and not _unit_has_assault_ranged_weapon(
            state=state,
            unit=unit,
            army_catalog=army_catalog,
            player_id=actor_id,
        )
    ):
        return False
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    return not (fell_back_state is not None and not fell_back_state.can_shoot)


def _rules_unit_can_select_to_shoot(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    if _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=actor_id,
    ) and not _rules_unit_has_assault_ranged_weapon(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=actor_id,
    ):
        return False
    for unit_id in _rules_unit_state_unit_ids(rules_unit):
        fell_back_state = state.fell_back_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if fell_back_state is not None and not fell_back_state.can_shoot:
            return False
    return True


def _advanced_unit_is_restricted_to_assault_weapons(
    *,
    state: GameState,
    unit: UnitInstance,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    advanced_state = state.advanced_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    return advanced_state is not None and not advanced_state.can_shoot


def _rules_unit_advanced_is_restricted_to_assault_weapons(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    return any(
        (
            advanced_state := state.advanced_unit_state_for_unit(
                player_id=actor_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
        )
        is not None
        and not advanced_state.can_shoot
        for unit_id in _rules_unit_state_unit_ids(rules_unit)
    )


def _unit_advanced_this_turn(
    *,
    state: GameState,
    unit: UnitInstance,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    return (
        state.advanced_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
        )
        is not None
    )


def _rules_unit_advanced_this_turn(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    return any(
        state.advanced_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        is not None
        for unit_id in _rules_unit_state_unit_ids(rules_unit)
    )


def _unit_has_assault_ranged_weapon(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> bool:
    for model in unit.own_models:
        for weapon in _available_own_weapons_for_model(
            state=state,
            model=model,
            unit=unit,
            army_catalog=army_catalog,
            player_id=player_id,
        ):
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT):
                return True
    return False


def _rules_unit_has_assault_ranged_weapon(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> bool:
    return any(
        _unit_has_assault_ranged_weapon(
            state=state,
            unit=component.unit,
            army_catalog=army_catalog,
            player_id=player_id,
        )
        for component in rules_unit.components
    )


def _unit_has_indirect_ranged_weapon(*, unit: UnitInstance, army_catalog: ArmyCatalog) -> bool:
    for model in unit.own_models:
        for weapon in _available_weapons_for_model(
            model=model,
            unit=unit,
            army_catalog=army_catalog,
        ):
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.INDIRECT_FIRE):
                return True
    return False


def _rules_unit_has_indirect_ranged_weapon(
    *,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> bool:
    return any(
        _unit_has_indirect_ranged_weapon(unit=component.unit, army_catalog=army_catalog)
        for component in rules_unit.components
    )


def _unit_has_already_shot(*, state: GameState, unit_instance_id: str) -> bool:
    shooting_state = state.shooting_phase_state
    return shooting_state is not None and unit_instance_id in shooting_state.shot_unit_ids


def _attack_sequence_for_selection_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> AttackSequence:
    payload = _decision_payload_object(request.payload)
    sequence_id = _payload_string(payload, key="sequence_id")
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and out_of_phase_state.attack_sequence is not None
        and out_of_phase_state.attack_sequence.sequence_id == sequence_id
    ):
        return out_of_phase_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if (
        shooting_state is not None
        and shooting_state.attack_sequence is not None
        and shooting_state.attack_sequence.sequence_id == sequence_id
    ):
        return shooting_state.attack_sequence
    raise GameLifecycleError("Attack sequence selection request has no active sequence.")


def _invalid_if_current_option_payload_drifted(
    *,
    state: GameState,
    result: DecisionResult,
    expected_request: DecisionRequest,
    invalid_reason: str,
) -> LifecycleStatus | None:
    try:
        expected_option = expected_request.option_by_id(result.selected_option_id)
    except DecisionError:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Attack sequence selection option is no longer legal.",
            payload={
                "invalid_reason": invalid_reason,
                "selected_option_id": result.selected_option_id,
            },
        )
    if result.payload != expected_option.payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Attack sequence selection payload drifted.",
            payload={
                "invalid_reason": invalid_reason,
                "selected_option_id": result.selected_option_id,
            },
        )
    return None


def _proposal_request_from_decision_request(
    request: DecisionRequest,
) -> ShootingDeclarationProposalRequest:
    if request.decision_type != SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
        raise GameLifecycleError("Shooting proposal request has wrong decision_type.")
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Shooting proposal DecisionRequest payload must be an object.")
    proposal_request = payload.get("proposal_request")
    if not isinstance(proposal_request, dict):
        raise GameLifecycleError("Shooting proposal DecisionRequest missing proposal_request.")
    raw = cast(dict[str, object], proposal_request)
    return ShootingDeclarationProposalRequest(
        request_id=_payload_string(raw, key="request_id"),
        active_player_id=_payload_string(raw, key="active_player_id"),
        battle_round=_payload_int(raw, key="battle_round"),
        unit_instance_id=_payload_string(raw, key="unit_instance_id"),
        source_decision_request_id=_payload_string(raw, key="source_decision_request_id"),
        source_decision_result_id=_payload_string(raw, key="source_decision_result_id"),
        visibility_cache_key=_payload_string(raw, key="visibility_cache_key"),
        proposal_kind=_payload_string(raw, key="proposal_kind"),
    )


def _reject_invalid_declaration(
    *,
    state: GameState,
    proposal_validation: ShootingProposalValidationResult,
    message: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload={"proposal_validation": validate_json_value(proposal_validation.to_payload())},
    )


def _ensure_shooting_phase_state(*, state: GameState) -> ShootingPhaseState:
    current = state.shooting_phase_state
    active_player_id = _active_player_id(state)
    if current is not None:
        return current
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    return state.shooting_phase_state


def _validate_shooting_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Shooting phase requires battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("Shooting phase requires SHOOTING phase.")
    _active_player_id(state)
    if state.battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    if state.shooting_phase_state is None:
        return
    shooting_state = state.shooting_phase_state
    if shooting_state.battle_round != state.battle_round:
        raise GameLifecycleError("shooting_phase_state battle round drift.")
    if shooting_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("shooting_phase_state active player drift.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Shooting battlefield scenario is invalid.") from exc
    return scenario


def _terrain_features_for_state(state: GameState) -> tuple[TerrainFeatureDefinition, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    return battlefield_state.terrain_features


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Shooting phase requires active_player_id.")
    return state.active_player_id


def _active_player_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    try:
        placed_army = battlefield_state.placed_army_for_player(player_id)
    except PlacementError:
        return ()
    unit_ids: list[str] = []
    seen: set[str] = set()
    armies = tuple(state.army_definitions)
    for placement in placed_army.unit_placements:
        rules_unit_id = rules_unit_id_for_unit_id(
            armies=armies,
            unit_instance_id=placement.unit_instance_id,
        )
        if rules_unit_id in seen:
            continue
        seen.add(rules_unit_id)
        unit_ids.append(rules_unit_id)
    return tuple(sorted(unit_ids))


def _enemy_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    unit_ids: list[str] = []
    seen: set[str] = set()
    armies = tuple(state.army_definitions)
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        for placement in placed_army.unit_placements:
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=armies,
                unit_instance_id=placement.unit_instance_id,
            )
            if rules_unit_id in seen:
                continue
            seen.add(rules_unit_id)
            unit_ids.append(rules_unit_id)
    return tuple(sorted(unit_ids))


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Shooting unit_instance_id is unknown.")


def _model_by_id(unit: UnitInstance, model_instance_id: str) -> ModelInstance | None:
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for model in unit.own_models:
        if model.model_instance_id == requested_id:
            return model
    return None


def _model_has_wargear_id(unit: UnitInstance, model: ModelInstance, wargear_id: str) -> bool:
    requested_wargear_id = _validate_identifier("wargear_id", wargear_id)
    for selection in unit.wargear_selections:
        if selection.model_profile_id == model.model_profile_id:
            return requested_wargear_id in selection.wargear_ids
    return False


def _wargear_by_id(*, army_catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_wargear_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in army_catalog.wargear:
        if wargear.wargear_id == requested_wargear_id:
            return wargear
    raise GameLifecycleError("Shooting wargear_id is not in the ArmyCatalog.")


def _weapon_profile_for_wargear(
    *,
    army_catalog: ArmyCatalog,
    wargear_id: str,
    weapon_profile_id: str,
) -> WeaponProfile:
    wargear = _wargear_by_id(army_catalog=army_catalog, wargear_id=wargear_id)
    requested_profile_id = _validate_identifier("weapon_profile_id", weapon_profile_id)
    for profile in wargear.weapon_profiles:
        if profile.profile_id == requested_profile_id:
            return profile
    raise GameLifecycleError("Shooting weapon_profile_id is not in the selected Wargear.")


def _shooting_unit_options(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    include_complete: bool,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        options.append(
            DecisionOption(
                option_id=rules_unit.unit_instance_id,
                label=_rules_unit_label(rules_unit),
                payload={"unit_instance_id": rules_unit.unit_instance_id},
            )
        )
    if include_complete:
        options.append(
            DecisionOption(
                option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
                label="Complete Shooting Phase",
                payload={
                    "submission_kind": COMPLETE_SHOOTING_PHASE_OPTION_ID,
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": state.active_player_id,
                    "phase_body_status": _COMPLETE_SHOOTING_PHASE_STATUS,
                    "skipped_unit_ids": list(unit_ids),
                },
            )
        )
    return tuple(options)


def _shooting_type_options(
    *,
    state: GameState,
    active_selection: ShootingUnitSelection,
    legal_types: tuple[ShootingType, ...],
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for shooting_type in legal_types:
        options.append(
            DecisionOption(
                option_id=shooting_type.value,
                label=f"{shooting_type.value.replace('_', ' ').title()} Shooting",
                payload={
                    "submission_kind": SELECT_SHOOTING_TYPE_DECISION_TYPE,
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": active_selection.player_id,
                    "unit_instance_id": active_selection.unit_instance_id,
                    "shooting_type": shooting_type.value,
                    "source_decision_request_id": active_selection.request_id,
                    "source_decision_result_id": active_selection.result_id,
                },
            )
        )
    return tuple(options)


def _shooting_phase_status_payload(
    *,
    state: GameState,
    phase_body_status: str,
    skipped_unit_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": BattlePhase.SHOOTING.value,
        "phase_body_status": phase_body_status,
        "skipped_unit_ids": list(skipped_ids),
    }


def _decision_payload_object(payload: JsonValue) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return cast(dict[str, object], payload)


def _payload_string(payload: dict[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Payload field {key} must be a string.")
    return _validate_identifier(key, value)


def _payload_int(payload: dict[str, object], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Payload field {key} must be an int.")
    return value


def _army_catalog_for_handler(handler: ShootingPhaseHandler) -> ArmyCatalog:
    if type(handler) is not ShootingPhaseHandler:
        raise GameLifecycleError("Shooting army catalog requires a ShootingPhaseHandler.")
    if handler.army_catalog is None:
        raise GameLifecycleError("Shooting phase requires an ArmyCatalog.")
    return handler.army_catalog


def _ruleset_descriptor_for_handler(handler: ShootingPhaseHandler) -> RulesetDescriptor:
    if type(handler) is not ShootingPhaseHandler:
        raise GameLifecycleError("Shooting ruleset descriptor requires a ShootingPhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Shooting phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _firing_deck_value_for_unit(
    *,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
) -> int | None:
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Firing Deck lookup requires an ArmyCatalog.")
    return unit_firing_deck_value(unit)


def _firing_deck_value_for_rules_unit(
    *,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> int | None:
    values: list[int] = []
    for component in rules_unit.components:
        value = _firing_deck_value_for_unit(
            unit=component.unit,
            army_catalog=army_catalog,
        )
        if value is not None:
            values.append(value)
    if not values:
        return None
    if len(values) > 1:
        raise GameLifecycleError("Attached rules unit cannot expose multiple Firing Deck values.")
    return values[0]


def _unit_has_vehicle_or_monster_keyword(unit: UnitInstance) -> bool:
    return _unit_has_keyword(unit, "VEHICLE") or _unit_has_keyword(unit, "MONSTER")


def _rules_unit_has_vehicle_or_monster_keyword(rules_unit: RulesUnitView) -> bool:
    return any(
        _canonical_keyword(keyword) in {"VEHICLE", "MONSTER"} for keyword in rules_unit.keywords
    )


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    if not rules_unit.is_attached_rules_unit:
        component = next(iter(rules_unit.components))
        return component.unit.name
    return "Attached Unit: " + " / ".join(
        component.unit.name for component in rules_unit.components
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_").replace("-", "_")


def _validate_attack_pools(values: object) -> tuple[RangedAttackPool, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ShootingPhaseState attack_pools must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    pools: list[RangedAttackPool] = []
    for value in raw_values:
        if type(value) is not RangedAttackPool:
            raise GameLifecycleError("ShootingPhaseState attack_pools must be RangedAttackPool.")
        pools.append(value)
    return tuple(pools)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated
