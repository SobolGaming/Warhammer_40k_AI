from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.battle_shock import (
    collect_battle_shock_test_requests,
    friendly_stratagem_target_permission,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointRefundStatus,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.core_stratagem_effects import (
    GO_TO_GROUND_EFFECT_KIND,
    GO_TO_GROUND_INVULNERABLE_SAVE,
    SMOKESCREEN_EFFECT_KIND,
    SMOKESCREEN_HIT_ROLL_MODIFIER,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
    resolve_mortal_wound_feel_no_pain_decision,
    unit_owner_player_id,
)
from warhammer40k_core.engine.decision import (
    DICE_REROLL_DECISION_TYPE,
    DecisionError,
    DiceRollManager,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    FIGHTS_FIRST_EFFECT_KIND,
    FightActivationSelection,
    eligible_fight_contexts_for_player,
    legal_fight_types_for_context,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    ChargeMoveProposal,
    ChargeMoveProposalPayload,
    charge_move_invalid_message,
    charge_move_violation_code,
    charge_move_violation_field,
    resolve_charge_move,
)
from warhammer40k_core.engine.phases.shooting import (
    request_out_of_phase_shooting_declaration,
    shooting_unit_can_select_to_shoot,
    shooting_unit_has_legal_declaration_against_targets,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveState,
    ReserveStatus,
    apply_reinforcement_placement_to_battlefield,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    timing_trigger_kind_from_token,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import (
        StratagemHandlerRegistry,
    )
    from warhammer40k_core.engine.game_state import GameState


STRATAGEM_DECISION_TYPE = "use_stratagem"
STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE = "submit_stratagem_target_proposal"
STRATAGEM_PROPOSAL_PAYLOAD_KIND = "stratagem_target_binding"
DECLINE_STRATAGEM_WINDOW_OPTION_ID = "decline_stratagem_window"
DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND = "decline_stratagem_window"
STRATAGEM_WINDOW_DECLINED_EVENT_TYPE = "stratagem_window_declined"
UNSUPPORTED_STRATAGEM_HANDLER_PREFIX = "unsupported:"
CORE_COMMAND_REROLL_HANDLER_ID = "core:command-reroll"
CORE_INSANE_BRAVERY_HANDLER_ID = "core:insane-bravery"
CORE_RAPID_INGRESS_HANDLER_ID = "core:rapid-ingress"
CORE_NEW_ORDERS_HANDLER_ID = "core:new-orders"
CORE_FIRE_OVERWATCH_HANDLER_ID = FIRE_OVERWATCH_RULE_ID
CORE_GO_TO_GROUND_HANDLER_ID = "core:go-to-ground"
CORE_EXPLOSIVES_HANDLER_ID = "core:explosives"
CORE_SMOKESCREEN_HANDLER_ID = "core:smokescreen"
CORE_HEROIC_INTERVENTION_HANDLER_ID = "core:heroic-intervention"
CORE_COUNTEROFFENSIVE_HANDLER_ID = "core:counteroffensive"
CORE_CRUSHING_IMPACT_HANDLER_ID = "core:crushing-impact"
CORE_EPIC_CHALLENGE_HANDLER_ID = "core:epic-challenge"
GENERIC_RULE_IR_STRATAGEM_HANDLER_ID = "generic:rule-ir"
COMMAND_REROLL_DICE_CONTEXT_KEY = "dice_roll_state"
COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY = "affected_unit_instance_id"
INSANE_BRAVERY_TARGET_POLICY_ID = "battle_shock_test_unit"
RAPID_INGRESS_TARGET_POLICY_ID = "reserves_unit"
NEW_ORDERS_TARGET_POLICY_ID = "active_tactical_secondary_card"
FIRE_OVERWATCH_TARGET_POLICY_ID = "out_of_phase_shooting_unit"
GO_TO_GROUND_TARGET_POLICY_ID = "selected_target_infantry_unit"
EXPLOSIVES_TARGET_POLICY_ID = "explosives_unit_and_enemy_target"
SMOKESCREEN_TARGET_POLICY_ID = "selected_target_smoke_unit"
HEROIC_INTERVENTION_TARGET_POLICY_ID = "heroic_intervention_unit"
COUNTEROFFENSIVE_TARGET_POLICY_ID = "counteroffensive_unit"
CRUSHING_IMPACT_TARGET_POLICY_ID = "crushing_impact_unit"
EPIC_CHALLENGE_TARGET_POLICY_ID = "epic_challenge_unit"
EXPLOSIVES_TARGET_CONTEXT_KEY = "enemy_target_unit_instance_id"
CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY = "enemy_target_unit_instance_id"
CRUSHING_IMPACT_MODEL_CONTEXT_KEY = "model_instance_id"
EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY = "character_model_instance_id"
HEROIC_INTERVENTION_MODE_CONTEXT_KEY = "mode"
HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND = "leap_to_defend"
HEROIC_INTERVENTION_MODE_INTO_THE_FRAY = "into_the_fray"
SELECTED_TARGET_UNIT_CONTEXT_KEY = "selected_target_unit_instance_ids"
FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY = "moved_unit_instance_id"
FIRE_OVERWATCH_MAX_RANGE_INCHES = 24.0
HEROIC_INTERVENTION_TARGET_RANGE_INCHES = 12.0
HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES = 6.0
CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT = 6


class StratagemAvailabilityKind(StrEnum):
    CORE = "core"
    DETACHMENT = "detachment"


class StratagemCategory(StrEnum):
    BATTLE_TACTIC = "battle_tactic"
    EPIC_DEED = "epic_deed"
    STRATEGIC_PLOY = "strategic_ploy"
    WARGEAR = "wargear"


class StratagemTargetKind(StrEnum):
    NONE = "none"
    FRIENDLY_UNIT = "friendly_unit"
    ANY_UNIT = "any_unit"
    TACTICAL_SECONDARY_CARD = "tactical_secondary_card"


class StratagemUseRecordPayload(TypedDict):
    use_id: str
    player_id: str
    stratagem_id: str
    source_id: str
    battle_round: int
    phase: str
    active_player_id: str | None
    timing_window_id: str | None
    request_id: str
    result_id: str
    selected_option_id: str
    target_binding: StratagemTargetBindingPayload
    targeted_unit_instance_ids: list[str]
    affected_unit_instance_ids: list[str]
    command_point_cost: int
    command_point_transaction_id: str | None
    handler_id: str
    effect_selection: JsonValue
    effect_payload: JsonValue


class StratagemTimingDescriptorPayload(TypedDict):
    trigger_kind: str
    phase: str | None
    timing_window_id: str | None


class StratagemRestrictionPolicyPayload(TypedDict):
    same_stratagem_per_phase: bool
    same_unit_target_per_phase: bool
    once_per_turn: bool
    once_per_battle: bool
    once_per_target_per_phase: bool
    allow_battle_shocked_targets: bool


class StratagemTargetSpecPayload(TypedDict):
    target_kind: str
    enumerable: bool
    target_policy_id: str


class StratagemDefinitionPayload(TypedDict):
    stratagem_id: str
    name: str
    source_id: str
    command_point_cost: int
    category: str
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    timing: StratagemTimingDescriptorPayload
    restriction_policy: StratagemRestrictionPolicyPayload
    target_spec: StratagemTargetSpecPayload
    handler_id: str
    eligible_roll_types: list[str]
    effect_payload: JsonValue


class StratagemCatalogRecordPayload(TypedDict):
    record_id: str
    definition: StratagemDefinitionPayload
    availability_kind: str
    detachment_id: str | None
    disabled: bool


class StratagemEligibilityContextPayload(TypedDict):
    game_id: str
    player_id: str
    battle_round: int
    phase: str
    active_player_id: str | None
    trigger_kind: str
    timing_window_id: str | None
    trigger_payload: NotRequired[JsonValue]


class StratagemTargetBindingPayload(TypedDict):
    target_kind: str
    target_player_id: str | None
    target_unit_instance_id: str | None
    target_secondary_mission_id: NotRequired[str | None]


class StratagemTargetProposalPayload(TypedDict):
    request_id: NotRequired[str]
    decision_type: NotRequired[str]
    actor_id: NotRequired[str]
    proposal_kind: str
    context: StratagemEligibilityContextPayload
    catalog_record: StratagemCatalogRecordPayload
    target_binding: StratagemTargetBindingPayload | None
    effect_selection: JsonValue


@dataclass(frozen=True, slots=True)
class StratagemTimingDescriptor:
    trigger_kind: TimingTriggerKind
    phase: BattlePhaseKind | None = None
    timing_window_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("StratagemTimingDescriptor phase", self.phase),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "StratagemTimingDescriptor timing_window_id",
                self.timing_window_id,
            ),
        )

    def matches(self, context: StratagemEligibilityContext) -> bool:
        if type(context) is not StratagemEligibilityContext:
            raise GameLifecycleError("Stratagem timing requires a StratagemEligibilityContext.")
        if self.trigger_kind is not context.trigger_kind:
            return False
        if self.phase is not None and self.phase is not context.phase:
            return False
        return not (
            self.timing_window_id is not None and self.timing_window_id != context.timing_window_id
        )

    def to_payload(self) -> StratagemTimingDescriptorPayload:
        return {
            "trigger_kind": self.trigger_kind.value,
            "phase": None if self.phase is None else self.phase.value,
            "timing_window_id": self.timing_window_id,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTimingDescriptorPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            timing_window_id=payload["timing_window_id"],
        )


@dataclass(frozen=True, slots=True)
class StratagemRestrictionPolicy:
    same_stratagem_per_phase: bool = True
    same_unit_target_per_phase: bool = True
    once_per_turn: bool = False
    once_per_battle: bool = False
    once_per_target_per_phase: bool = False
    allow_battle_shocked_targets: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "same_stratagem_per_phase",
            _validate_bool(
                "StratagemRestrictionPolicy same_stratagem_per_phase",
                self.same_stratagem_per_phase,
            ),
        )
        object.__setattr__(
            self,
            "same_unit_target_per_phase",
            _validate_bool(
                "StratagemRestrictionPolicy same_unit_target_per_phase",
                self.same_unit_target_per_phase,
            ),
        )
        object.__setattr__(
            self,
            "once_per_turn",
            _validate_bool("StratagemRestrictionPolicy once_per_turn", self.once_per_turn),
        )
        object.__setattr__(
            self,
            "once_per_battle",
            _validate_bool("StratagemRestrictionPolicy once_per_battle", self.once_per_battle),
        )
        object.__setattr__(
            self,
            "once_per_target_per_phase",
            _validate_bool(
                "StratagemRestrictionPolicy once_per_target_per_phase",
                self.once_per_target_per_phase,
            ),
        )
        object.__setattr__(
            self,
            "allow_battle_shocked_targets",
            _validate_bool(
                "StratagemRestrictionPolicy allow_battle_shocked_targets",
                self.allow_battle_shocked_targets,
            ),
        )

    def to_payload(self) -> StratagemRestrictionPolicyPayload:
        return {
            "same_stratagem_per_phase": self.same_stratagem_per_phase,
            "same_unit_target_per_phase": self.same_unit_target_per_phase,
            "once_per_turn": self.once_per_turn,
            "once_per_battle": self.once_per_battle,
            "once_per_target_per_phase": self.once_per_target_per_phase,
            "allow_battle_shocked_targets": self.allow_battle_shocked_targets,
        }

    @classmethod
    def from_payload(cls, payload: StratagemRestrictionPolicyPayload) -> Self:
        return cls(
            same_stratagem_per_phase=payload["same_stratagem_per_phase"],
            same_unit_target_per_phase=payload["same_unit_target_per_phase"],
            once_per_turn=payload["once_per_turn"],
            once_per_battle=payload["once_per_battle"],
            once_per_target_per_phase=payload["once_per_target_per_phase"],
            allow_battle_shocked_targets=payload["allow_battle_shocked_targets"],
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetSpec:
    target_kind: StratagemTargetKind = StratagemTargetKind.NONE
    enumerable: bool = True
    target_policy_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_kind",
            stratagem_target_kind_from_token(self.target_kind),
        )
        object.__setattr__(
            self,
            "enumerable",
            _validate_bool("StratagemTargetSpec enumerable", self.enumerable),
        )
        object.__setattr__(
            self,
            "target_policy_id",
            _validate_target_policy_id(
                target_kind=self.target_kind,
                target_policy_id=self.target_policy_id,
            ),
        )
        if self.target_kind is StratagemTargetKind.NONE and not self.enumerable:
            raise GameLifecycleError("Targetless StratagemTargetSpec must be enumerable.")

    @property
    def requires_target(self) -> bool:
        return self.target_kind is not StratagemTargetKind.NONE

    def to_payload(self) -> StratagemTargetSpecPayload:
        return {
            "target_kind": self.target_kind.value,
            "enumerable": self.enumerable,
            "target_policy_id": self.target_policy_id,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTargetSpecPayload) -> Self:
        return cls(
            target_kind=stratagem_target_kind_from_token(payload["target_kind"]),
            enumerable=payload["enumerable"],
            target_policy_id=payload["target_policy_id"],
        )


@dataclass(frozen=True, slots=True)
class StratagemDefinition:
    stratagem_id: str
    name: str
    source_id: str
    command_point_cost: int
    category: StratagemCategory
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    timing: StratagemTimingDescriptor
    restriction_policy: StratagemRestrictionPolicy = field(
        default_factory=StratagemRestrictionPolicy
    )
    target_spec: StratagemTargetSpec = field(default_factory=StratagemTargetSpec)
    handler_id: str = "record_only"
    eligible_roll_types: tuple[str, ...] = ()
    effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stratagem_id",
            _validate_identifier("StratagemDefinition stratagem_id", self.stratagem_id),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("StratagemDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StratagemDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "command_point_cost",
            _validate_non_negative_int(
                "StratagemDefinition command_point_cost",
                self.command_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "category",
            stratagem_category_from_token(self.category),
        )
        object.__setattr__(
            self,
            "when_descriptor",
            _validate_identifier("StratagemDefinition when_descriptor", self.when_descriptor),
        )
        object.__setattr__(
            self,
            "target_descriptor",
            _validate_identifier("StratagemDefinition target_descriptor", self.target_descriptor),
        )
        object.__setattr__(
            self,
            "effect_descriptor",
            _validate_identifier("StratagemDefinition effect_descriptor", self.effect_descriptor),
        )
        object.__setattr__(
            self,
            "restrictions_descriptor",
            _validate_identifier(
                "StratagemDefinition restrictions_descriptor",
                self.restrictions_descriptor,
            ),
        )
        if type(self.timing) is not StratagemTimingDescriptor:
            raise GameLifecycleError("StratagemDefinition timing must be a descriptor.")
        if type(self.restriction_policy) is not StratagemRestrictionPolicy:
            raise GameLifecycleError("StratagemDefinition restriction_policy must be a policy.")
        if type(self.target_spec) is not StratagemTargetSpec:
            raise GameLifecycleError("StratagemDefinition target_spec must be a target spec.")
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("StratagemDefinition handler_id", self.handler_id),
        )
        object.__setattr__(
            self,
            "eligible_roll_types",
            _validate_identifier_tuple(
                "StratagemDefinition eligible_roll_types",
                self.eligible_roll_types,
            ),
        )
        object.__setattr__(self, "effect_payload", validate_json_value(self.effect_payload))

    def to_payload(self) -> StratagemDefinitionPayload:
        return {
            "stratagem_id": self.stratagem_id,
            "name": self.name,
            "source_id": self.source_id,
            "command_point_cost": self.command_point_cost,
            "category": self.category.value,
            "when_descriptor": self.when_descriptor,
            "target_descriptor": self.target_descriptor,
            "effect_descriptor": self.effect_descriptor,
            "restrictions_descriptor": self.restrictions_descriptor,
            "timing": self.timing.to_payload(),
            "restriction_policy": self.restriction_policy.to_payload(),
            "target_spec": self.target_spec.to_payload(),
            "handler_id": self.handler_id,
            "eligible_roll_types": list(self.eligible_roll_types),
            "effect_payload": self.effect_payload,
        }

    @classmethod
    def from_payload(cls, payload: StratagemDefinitionPayload) -> Self:
        return cls(
            stratagem_id=payload["stratagem_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            command_point_cost=payload["command_point_cost"],
            category=stratagem_category_from_token(payload["category"]),
            when_descriptor=payload["when_descriptor"],
            target_descriptor=payload["target_descriptor"],
            effect_descriptor=payload["effect_descriptor"],
            restrictions_descriptor=payload["restrictions_descriptor"],
            timing=StratagemTimingDescriptor.from_payload(payload["timing"]),
            restriction_policy=StratagemRestrictionPolicy.from_payload(
                payload["restriction_policy"]
            ),
            target_spec=StratagemTargetSpec.from_payload(payload["target_spec"]),
            handler_id=payload["handler_id"],
            eligible_roll_types=tuple(payload["eligible_roll_types"]),
            effect_payload=payload["effect_payload"],
        )


@dataclass(frozen=True, slots=True)
class StratagemCatalogRecord:
    record_id: str
    definition: StratagemDefinition
    availability_kind: StratagemAvailabilityKind = StratagemAvailabilityKind.CORE
    detachment_id: str | None = None
    disabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("StratagemCatalogRecord record_id", self.record_id),
        )
        if type(self.definition) is not StratagemDefinition:
            raise GameLifecycleError("StratagemCatalogRecord definition must be a definition.")
        object.__setattr__(
            self,
            "availability_kind",
            stratagem_availability_kind_from_token(self.availability_kind),
        )
        object.__setattr__(
            self,
            "detachment_id",
            _validate_optional_identifier(
                "StratagemCatalogRecord detachment_id",
                self.detachment_id,
            ),
        )
        object.__setattr__(
            self,
            "disabled",
            _validate_bool("StratagemCatalogRecord disabled", self.disabled),
        )
        if self.availability_kind is StratagemAvailabilityKind.CORE and self.detachment_id:
            raise GameLifecycleError("Core StratagemCatalogRecord cannot require detachment_id.")
        if (
            self.availability_kind is StratagemAvailabilityKind.DETACHMENT
            and not self.detachment_id
        ):
            raise GameLifecycleError("Detachment StratagemCatalogRecord requires detachment_id.")

    def to_payload(self) -> StratagemCatalogRecordPayload:
        return {
            "record_id": self.record_id,
            "definition": self.definition.to_payload(),
            "availability_kind": self.availability_kind.value,
            "detachment_id": self.detachment_id,
            "disabled": self.disabled,
        }

    @classmethod
    def from_payload(cls, payload: StratagemCatalogRecordPayload) -> Self:
        return cls(
            record_id=payload["record_id"],
            definition=StratagemDefinition.from_payload(payload["definition"]),
            availability_kind=stratagem_availability_kind_from_token(payload["availability_kind"]),
            detachment_id=payload["detachment_id"],
            disabled=payload["disabled"],
        )


@dataclass(frozen=True, slots=True)
class StratagemCatalogIndex:
    _records_by_trigger: Mapping[TimingTriggerKind, tuple[StratagemCatalogRecord, ...]]
    _records: tuple[StratagemCatalogRecord, ...]

    @classmethod
    def from_records(cls, records: tuple[StratagemCatalogRecord, ...]) -> Self:
        validated = _validate_catalog_records(records)
        grouped: dict[TimingTriggerKind, list[StratagemCatalogRecord]] = {}
        for record in validated:
            grouped.setdefault(record.definition.timing.trigger_kind, []).append(record)
        records_by_trigger = {
            trigger_kind: tuple(records_for_trigger)
            for trigger_kind, records_for_trigger in grouped.items()
        }
        return cls(
            _records_by_trigger=MappingProxyType(records_by_trigger),
            _records=validated,
        )

    def records_for(
        self,
        trigger_kind: TimingTriggerKind,
    ) -> tuple[StratagemCatalogRecord, ...]:
        if type(trigger_kind) is not TimingTriggerKind:
            raise GameLifecycleError("StratagemCatalogIndex lookup requires a TimingTriggerKind.")
        return self._records_by_trigger.get(trigger_kind, ())

    def all_records(self) -> tuple[StratagemCatalogRecord, ...]:
        return self._records


@dataclass(frozen=True, slots=True)
class StratagemEligibilityContext:
    game_id: str
    player_id: str
    battle_round: int
    phase: BattlePhaseKind
    active_player_id: str | None
    trigger_kind: TimingTriggerKind
    timing_window_id: str | None = None
    trigger_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("StratagemEligibilityContext game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StratagemEligibilityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "StratagemEligibilityContext battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            battle_phase_kind_from_token(self.phase),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "StratagemEligibilityContext active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "StratagemEligibilityContext timing_window_id",
                self.timing_window_id,
            ),
        )
        object.__setattr__(self, "trigger_payload", validate_json_value(self.trigger_payload))

    @classmethod
    def from_state(
        cls,
        *,
        state: GameState,
        player_id: str,
        trigger_kind: TimingTriggerKind,
        timing_window_id: str | None = None,
        trigger_payload: JsonValue = None,
    ) -> Self:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("StratagemEligibilityContext requires battle stage.")
        current_phase = state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("StratagemEligibilityContext requires a battle phase.")
        return cls(
            game_id=state.game_id,
            player_id=player_id,
            battle_round=state.battle_round,
            phase=current_phase,
            active_player_id=state.active_player_id,
            trigger_kind=trigger_kind,
            timing_window_id=timing_window_id,
            trigger_payload=trigger_payload,
        )

    def to_payload(self) -> StratagemEligibilityContextPayload:
        payload: StratagemEligibilityContextPayload = {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "active_player_id": self.active_player_id,
            "trigger_kind": self.trigger_kind.value,
            "timing_window_id": self.timing_window_id,
        }
        if self.trigger_payload is not None:
            payload["trigger_payload"] = self.trigger_payload
        return payload

    @classmethod
    def from_payload(cls, payload: StratagemEligibilityContextPayload) -> Self:
        trigger_payload: JsonValue = None
        if "trigger_payload" in payload:
            trigger_payload = payload["trigger_payload"]
        return cls(
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=battle_phase_kind_from_token(payload["phase"]),
            active_player_id=payload["active_player_id"],
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            timing_window_id=payload["timing_window_id"],
            trigger_payload=trigger_payload,
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetBinding:
    target_kind: StratagemTargetKind
    target_player_id: str | None = None
    target_unit_instance_id: str | None = None
    target_secondary_mission_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_kind",
            stratagem_target_kind_from_token(self.target_kind),
        )
        object.__setattr__(
            self,
            "target_player_id",
            _validate_optional_identifier(
                "StratagemTargetBinding target_player_id",
                self.target_player_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_optional_identifier(
                "StratagemTargetBinding target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_secondary_mission_id",
            _validate_optional_identifier(
                "StratagemTargetBinding target_secondary_mission_id",
                self.target_secondary_mission_id,
            ),
        )
        if self.target_kind is StratagemTargetKind.NONE:
            if (
                self.target_player_id is not None
                or self.target_unit_instance_id is not None
                or self.target_secondary_mission_id is not None
            ):
                raise GameLifecycleError("Targetless StratagemTargetBinding cannot name a target.")
            return
        if self.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
            if self.target_player_id is None or self.target_secondary_mission_id is None:
                raise GameLifecycleError(
                    "Tactical secondary StratagemTargetBinding requires target card fields."
                )
            if self.target_unit_instance_id is not None:
                raise GameLifecycleError(
                    "Tactical secondary StratagemTargetBinding cannot name a unit."
                )
            return
        if self.target_player_id is None or self.target_unit_instance_id is None:
            raise GameLifecycleError("Unit StratagemTargetBinding requires target unit fields.")
        if self.target_secondary_mission_id is not None:
            raise GameLifecycleError("Unit StratagemTargetBinding cannot name a secondary card.")

    @classmethod
    def none(cls) -> Self:
        return cls(target_kind=StratagemTargetKind.NONE)

    def to_payload(self) -> StratagemTargetBindingPayload:
        payload: StratagemTargetBindingPayload = {
            "target_kind": self.target_kind.value,
            "target_player_id": self.target_player_id,
            "target_unit_instance_id": self.target_unit_instance_id,
        }
        if self.target_secondary_mission_id is not None:
            payload["target_secondary_mission_id"] = self.target_secondary_mission_id
        return payload

    @classmethod
    def from_payload(cls, payload: StratagemTargetBindingPayload) -> Self:
        target_secondary_mission_id = None
        if "target_secondary_mission_id" in payload:
            target_secondary_mission_id = payload["target_secondary_mission_id"]
        return cls(
            target_kind=stratagem_target_kind_from_token(payload["target_kind"]),
            target_player_id=payload["target_player_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            target_secondary_mission_id=target_secondary_mission_id,
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetProposal:
    proposal_kind: str
    context: StratagemEligibilityContext
    catalog_record: StratagemCatalogRecord
    target_binding: StratagemTargetBinding | None = None
    effect_selection: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier("StratagemTargetProposal proposal_kind", self.proposal_kind),
        )
        if self.proposal_kind != STRATAGEM_PROPOSAL_PAYLOAD_KIND:
            raise GameLifecycleError("StratagemTargetProposal proposal_kind is unsupported.")
        if type(self.context) is not StratagemEligibilityContext:
            raise GameLifecycleError(
                "StratagemTargetProposal context must be an eligibility context."
            )
        if type(self.catalog_record) is not StratagemCatalogRecord:
            raise GameLifecycleError(
                "StratagemTargetProposal catalog_record must be a catalog record."
            )
        if self.catalog_record.definition.target_spec.enumerable:
            raise GameLifecycleError(
                "StratagemTargetProposal catalog_record must require parameterized targets."
            )
        if (
            self.target_binding is not None
            and type(self.target_binding) is not StratagemTargetBinding
        ):
            raise GameLifecycleError(
                "StratagemTargetProposal target_binding must be a target binding."
            )
        object.__setattr__(self, "effect_selection", validate_json_value(self.effect_selection))

    @property
    def game_id(self) -> str:
        return self.context.game_id

    @property
    def player_id(self) -> str:
        return self.context.player_id

    @property
    def battle_round(self) -> int:
        return self.context.battle_round

    @property
    def phase(self) -> BattlePhaseKind:
        return self.context.phase

    @property
    def stratagem_id(self) -> str:
        return self.catalog_record.definition.stratagem_id

    @property
    def target_spec(self) -> StratagemTargetSpec:
        return self.catalog_record.definition.target_spec

    @classmethod
    def for_request(
        cls,
        *,
        context: StratagemEligibilityContext,
        catalog_record: StratagemCatalogRecord,
    ) -> Self:
        return cls(
            proposal_kind=STRATAGEM_PROPOSAL_PAYLOAD_KIND,
            context=context,
            catalog_record=catalog_record,
        )

    def with_binding(
        self,
        binding: StratagemTargetBinding,
        *,
        effect_selection: JsonValue = None,
    ) -> Self:
        return type(self)(
            proposal_kind=self.proposal_kind,
            context=self.context,
            catalog_record=self.catalog_record,
            target_binding=binding,
            effect_selection=effect_selection,
        )

    def with_effect_selection(self, effect_selection: JsonValue) -> Self:
        return type(self)(
            proposal_kind=self.proposal_kind,
            context=self.context,
            catalog_record=self.catalog_record,
            target_binding=self.target_binding,
            effect_selection=effect_selection,
        )

    def to_payload(self) -> StratagemTargetProposalPayload:
        return {
            "proposal_kind": self.proposal_kind,
            "context": self.context.to_payload(),
            "catalog_record": self.catalog_record.to_payload(),
            "target_binding": (
                None if self.target_binding is None else self.target_binding.to_payload()
            ),
            "effect_selection": self.effect_selection,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTargetProposalPayload) -> Self:
        binding_payload = payload["target_binding"]
        return cls(
            proposal_kind=payload["proposal_kind"],
            context=StratagemEligibilityContext.from_payload(payload["context"]),
            catalog_record=StratagemCatalogRecord.from_payload(payload["catalog_record"]),
            target_binding=(
                None
                if binding_payload is None
                else StratagemTargetBinding.from_payload(binding_payload)
            ),
            effect_selection=payload["effect_selection"],
        )


@dataclass(frozen=True, slots=True)
class StratagemUseRequest:
    context: StratagemEligibilityContext
    request: DecisionRequest

    def __post_init__(self) -> None:
        if type(self.context) is not StratagemEligibilityContext:
            raise GameLifecycleError("StratagemUseRequest context must be an eligibility context.")
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError("StratagemUseRequest request must be a DecisionRequest.")
        if self.request.decision_type != STRATAGEM_DECISION_TYPE:
            raise GameLifecycleError("StratagemUseRequest request decision_type drift.")


@dataclass(frozen=True, slots=True)
class StratagemUseRecord:
    use_id: str
    player_id: str
    stratagem_id: str
    source_id: str
    battle_round: int
    phase: BattlePhaseKind
    active_player_id: str | None
    timing_window_id: str | None
    request_id: str
    result_id: str
    selected_option_id: str
    target_binding: StratagemTargetBinding
    targeted_unit_instance_ids: tuple[str, ...]
    affected_unit_instance_ids: tuple[str, ...]
    command_point_cost: int
    command_point_transaction_id: str | None
    handler_id: str
    effect_selection: JsonValue = None
    effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "use_id",
            _validate_identifier("StratagemUseRecord use_id", self.use_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StratagemUseRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "stratagem_id",
            _validate_identifier("StratagemUseRecord stratagem_id", self.stratagem_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StratagemUseRecord source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("StratagemUseRecord battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", battle_phase_kind_from_token(self.phase))
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "StratagemUseRecord active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "StratagemUseRecord timing_window_id",
                self.timing_window_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("StratagemUseRecord request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("StratagemUseRecord result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "selected_option_id",
            _validate_identifier(
                "StratagemUseRecord selected_option_id",
                self.selected_option_id,
            ),
        )
        if type(self.target_binding) is not StratagemTargetBinding:
            raise GameLifecycleError("StratagemUseRecord target_binding must be a binding.")
        targeted_unit_ids = _validate_stratagem_affected_unit_ids(self.targeted_unit_instance_ids)
        object.__setattr__(self, "targeted_unit_instance_ids", targeted_unit_ids)
        affected_unit_ids = _validate_stratagem_affected_unit_ids(self.affected_unit_instance_ids)
        object.__setattr__(self, "affected_unit_instance_ids", affected_unit_ids)
        object.__setattr__(
            self,
            "command_point_cost",
            _validate_non_negative_int(
                "StratagemUseRecord command_point_cost",
                self.command_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "command_point_transaction_id",
            _validate_optional_identifier(
                "StratagemUseRecord command_point_transaction_id",
                self.command_point_transaction_id,
            ),
        )
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("StratagemUseRecord handler_id", self.handler_id),
        )
        object.__setattr__(self, "effect_selection", validate_json_value(self.effect_selection))
        object.__setattr__(self, "effect_payload", validate_json_value(self.effect_payload))

    def to_payload(self) -> StratagemUseRecordPayload:
        return {
            "use_id": self.use_id,
            "player_id": self.player_id,
            "stratagem_id": self.stratagem_id,
            "source_id": self.source_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "active_player_id": self.active_player_id,
            "timing_window_id": self.timing_window_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "selected_option_id": self.selected_option_id,
            "target_binding": self.target_binding.to_payload(),
            "targeted_unit_instance_ids": list(self.targeted_unit_instance_ids),
            "affected_unit_instance_ids": list(self.affected_unit_instance_ids),
            "command_point_cost": self.command_point_cost,
            "command_point_transaction_id": self.command_point_transaction_id,
            "handler_id": self.handler_id,
            "effect_selection": self.effect_selection,
            "effect_payload": self.effect_payload,
        }

    @classmethod
    def from_payload(cls, payload: StratagemUseRecordPayload) -> Self:
        return cls(
            use_id=payload["use_id"],
            player_id=payload["player_id"],
            stratagem_id=payload["stratagem_id"],
            source_id=payload["source_id"],
            battle_round=payload["battle_round"],
            phase=battle_phase_kind_from_token(payload["phase"]),
            active_player_id=payload["active_player_id"],
            timing_window_id=payload["timing_window_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            selected_option_id=payload["selected_option_id"],
            target_binding=StratagemTargetBinding.from_payload(payload["target_binding"]),
            targeted_unit_instance_ids=tuple(payload["targeted_unit_instance_ids"]),
            affected_unit_instance_ids=tuple(payload["affected_unit_instance_ids"]),
            command_point_cost=payload["command_point_cost"],
            command_point_transaction_id=payload["command_point_transaction_id"],
            handler_id=payload["handler_id"],
            effect_selection=payload["effect_selection"],
            effect_payload=payload["effect_payload"],
        )


def request_stratagem_use(
    *,
    state: GameState,
    decisions: DecisionController,
    catalog_records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem use requires a DecisionController.")
    records = _validate_catalog_records(catalog_records)
    options = _stratagem_use_options_for_records(
        state=state,
        records=records,
        context=context,
    )
    return _request_stratagem_use_with_options(
        state=state,
        decisions=decisions,
        context=context,
        options=options,
    )


def request_stratagem_use_from_index(
    *,
    state: GameState,
    decisions: DecisionController,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem use requires a DecisionController.")
    options = stratagem_use_options_from_index(state=state, index=index, context=context)
    return _request_stratagem_use_with_options(
        state=state,
        decisions=decisions,
        context=context,
        options=options,
    )


def _request_stratagem_use_with_options(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    options: tuple[DecisionOption, ...],
) -> LifecycleStatus:
    if not options:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="No stratagems are available for this timing window.",
            payload={"player_id": context.player_id, "trigger_kind": context.trigger_kind.value},
        )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=options,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"pending_request_id": request.request_id},
    )


def create_stratagem_use_decision_request(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    options: tuple[DecisionOption, ...],
) -> DecisionRequest:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem decision requires an eligibility context.")
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id=context.player_id,
        payload=validate_json_value(
            {
                "stratagem_context": context.to_payload(),
                "finite": True,
            }
        ),
        options=options,
    )


def stratagem_decline_option() -> DecisionOption:
    return DecisionOption(
        option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        label="Decline Stratagem Window",
        payload=stratagem_decline_payload(),
    )


def stratagem_decline_payload() -> JsonValue:
    return validate_json_value({"submission_kind": DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND})


def is_stratagem_window_decline_result(result: DecisionResult) -> bool:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem decline check requires a DecisionResult.")
    return (
        result.decision_type in (STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE)
        and isinstance(result.payload, dict)
        and result.payload.get("submission_kind") == DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND
    )


def stratagem_window_decline_allowed(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem decline allowance requires a DecisionRequest.")
    if not is_stratagem_window_decline_result(result):
        return False
    if request.decision_type == STRATAGEM_DECISION_TYPE:
        return any(
            option.option_id == DECLINE_STRATAGEM_WINDOW_OPTION_ID for option in request.options
        )
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        if not isinstance(request.payload, dict):
            return False
        return request.payload.get("declinable") is True
    return False


def stratagem_window_context_from_request(request: DecisionRequest) -> StratagemEligibilityContext:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem window context requires a DecisionRequest.")
    if request.decision_type == STRATAGEM_DECISION_TYPE:
        if not isinstance(request.payload, dict):
            raise GameLifecycleError("Stratagem decision request payload must be an object.")
        context_payload = request.payload.get("stratagem_context")
        if not isinstance(context_payload, dict):
            raise GameLifecycleError("Stratagem decision request is missing context.")
        try:
            return StratagemEligibilityContext.from_payload(
                cast(StratagemEligibilityContextPayload, context_payload)
            )
        except KeyError as exc:
            raise GameLifecycleError("Stratagem decision context payload is malformed.") from exc
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        proposal = _proposal_from_request_payload(request.payload)
        if proposal is None:
            raise GameLifecycleError("Stratagem proposal request is missing proposal context.")
        return proposal.context
    raise GameLifecycleError("DecisionRequest is not a Stratagem window request.")


def stratagem_window_decline_event_payload(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> JsonValue:
    if not is_stratagem_window_decline_result(result):
        raise GameLifecycleError("Stratagem decline event requires a decline result.")
    context = stratagem_window_context_from_request(request)
    return validate_json_value(
        {
            "game_id": context.game_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": context.phase.value,
            "active_player_id": context.active_player_id,
            "trigger_kind": context.trigger_kind.value,
            "timing_window_id": context.timing_window_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "decision_type": result.decision_type,
        }
    )


def stratagem_window_declined_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem decline lookup requires a DecisionController.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem decline lookup requires an eligibility context.")
    for event in decisions.event_log.records:
        if event.event_type != STRATAGEM_WINDOW_DECLINED_EVENT_TYPE:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Stratagem decline event payload must be an object.")
        payload = event.payload
        _require_decline_event_fields(payload)
        if (
            payload["game_id"] == context.game_id
            and payload["player_id"] == context.player_id
            and payload["battle_round"] == context.battle_round
            and payload["phase"] == context.phase.value
            and payload["active_player_id"] == context.active_player_id
            and payload["trigger_kind"] == context.trigger_kind.value
            and payload["timing_window_id"] == context.timing_window_id
        ):
            return True
    return False


def stratagem_use_options(
    *,
    state: GameState,
    catalog_records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
) -> tuple[DecisionOption, ...]:
    records = _validate_catalog_records(catalog_records)
    return _stratagem_use_options_for_records(state=state, records=records, context=context)


def stratagem_use_options_from_index(
    *,
    state: GameState,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
) -> tuple[DecisionOption, ...]:
    if type(index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Stratagem options require a StratagemCatalogIndex.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem options require an eligibility context.")
    return _stratagem_use_options_for_records(
        state=state,
        records=index.records_for(context.trigger_kind),
        context=context,
    )


def stratagem_use_options_for_handler_from_index(
    *,
    state: GameState,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    handler_id: str,
) -> tuple[DecisionOption, ...]:
    if type(index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Stratagem options require a StratagemCatalogIndex.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem options require an eligibility context.")
    requested_handler_id = _validate_identifier("handler_id", handler_id)
    return _stratagem_use_options_for_records(
        state=state,
        records=tuple(
            record
            for record in index.records_for(context.trigger_kind)
            if record.definition.handler_id == requested_handler_id
        ),
        context=context,
    )


def _stratagem_use_options_for_records(
    *,
    state: GameState,
    records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
) -> tuple[DecisionOption, ...]:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem options require an eligibility context.")
    options: list[DecisionOption] = []
    for record in records:
        if not _record_is_available_for_context(state=state, record=record, context=context):
            continue
        definition = record.definition
        if not definition.target_spec.enumerable:
            continue
        bindings = _enumerated_target_bindings(
            state=state,
            player_id=context.player_id,
            definition=definition,
        )
        for binding in bindings:
            if (
                _restriction_violation(
                    state=state,
                    player_id=context.player_id,
                    definition=definition,
                    context=context,
                    target_binding=binding,
                )
                is not None
            ):
                continue
            options.append(
                _stratagem_decision_option(
                    record=record,
                    context=context,
                    target_binding=binding,
                )
            )
    return tuple(sorted(options, key=lambda option: option.option_id))


def request_stratagem_target_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: StratagemTargetProposal,
    allow_decline: bool = False,
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem proposal requires a DecisionController.")
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    if proposal_request.target_binding is not None:
        raise GameLifecycleError("Stratagem proposal request cannot include a target binding.")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=proposal_request.catalog_record,
        context=proposal_request.context,
        target_binding=None,
    )
    if violation is not None:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Stratagem target proposal is not available for this timing window.",
            payload={
                "player_id": proposal_request.player_id,
                "stratagem_id": proposal_request.stratagem_id,
                "unavailable_reason": violation,
            },
        )
    request = create_stratagem_target_proposal_decision_request(
        state=state,
        proposal_request=proposal_request,
        allow_decline=allow_decline,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"pending_request_id": request.request_id},
    )


def create_stratagem_target_proposal_decision_request(
    *,
    state: GameState,
    proposal_request: StratagemTargetProposal,
    allow_decline: bool = False,
) -> DecisionRequest:
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    request_id = state.next_decision_request_id()
    return DecisionRequest(
        request_id=request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.player_id,
        payload=stratagem_target_proposal_request_payload(
            proposal_request,
            request_id=request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=proposal_request.player_id,
            allow_decline=allow_decline,
        ),
        options=(parameterized_decision_option(),),
    )


def stratagem_target_proposal_request_payload(
    proposal_request: StratagemTargetProposal,
    *,
    request_id: str,
    decision_type: str,
    actor_id: str,
    allow_decline: bool = False,
) -> JsonValue:
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    validated_request_id = _validate_identifier("Stratagem proposal request_id", request_id)
    validated_decision_type = _validate_identifier(
        "Stratagem proposal decision_type",
        decision_type,
    )
    validated_actor_id = _validate_identifier("Stratagem proposal actor_id", actor_id)
    if validated_decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Stratagem proposal decision_type is unsupported.")
    if validated_actor_id != proposal_request.player_id:
        raise GameLifecycleError("Stratagem proposal actor_id must match proposal player.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    proposal_payload = validate_json_value(proposal_request.to_payload())
    if not isinstance(proposal_payload, dict):
        raise GameLifecycleError("Stratagem proposal payload must be an object.")
    payload: dict[str, JsonValue] = {
        "proposal_request": {
            "request_id": validated_request_id,
            "decision_type": validated_decision_type,
            "actor_id": validated_actor_id,
            **proposal_payload,
        }
    }
    if allow_decline:
        payload["declinable"] = True
    return validate_json_value(payload)


def stratagem_target_proposal_from_index(
    *,
    state: GameState,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    handler_id: str,
) -> StratagemTargetProposal | None:
    if type(index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Stratagem target proposal requires a StratagemCatalogIndex.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem target proposal requires an eligibility context.")
    requested_handler_id = _validate_identifier("handler_id", handler_id)
    matches: list[StratagemCatalogRecord] = []
    for record in index.records_for(context.trigger_kind):
        definition = record.definition
        if definition.handler_id != requested_handler_id:
            continue
        if definition.target_spec.enumerable:
            continue
        if _record_is_available_for_context(state=state, record=record, context=context):
            matches.append(record)
    if not matches:
        return None
    if len(matches) > 1:
        raise GameLifecycleError("Stratagem target proposal index matched multiple records.")
    return StratagemTargetProposal.for_request(context=context, catalog_record=matches[0])


def invalid_stratagem_use_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    selection = _stratagem_selection_from_result_payload(result.payload)
    if selection is None:
        return _invalid(state, "Malformed stratagem decision payload.", "malformed_payload")
    context = selection[0]
    record = selection[1]
    target_binding = selection[2]
    effect_selection = selection[3]
    drift = _context_state_drift(state=state, context=context)
    if drift is not None:
        return _invalid(state, "Stale stratagem decision context.", drift)
    if request.actor_id != context.player_id or result.actor_id != context.player_id:
        return _invalid(state, "Stratagem decision actor drift.", "wrong_context")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=record,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
    )
    if violation is not None:
        return _invalid(state, "Stratagem decision is no longer legal.", violation)
    return None


def apply_stratagem_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None = None,
) -> StratagemUseRecord:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem application requires a DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem application requires a DecisionController.")
    selection = _require_stratagem_selection(result.payload)
    context, catalog_record, target_binding, effect_selection = selection
    return _apply_stratagem_use(
        state=state,
        result=result,
        decisions=decisions,
        context=context,
        catalog_record=catalog_record,
        target_binding=target_binding,
        effect_selection=effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
    )


def _apply_stratagem_use(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    catalog_record: StratagemCatalogRecord,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
) -> StratagemUseRecord:
    definition = catalog_record.definition
    if _stratagem_handler_is_unsupported(definition):
        raise GameLifecycleError("Unsupported stratagem handler cannot be applied.")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=catalog_record,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if violation is not None:
        raise GameLifecycleError(f"Prevalidated stratagem is no longer legal: {violation}.")
    use_id = _next_stratagem_use_id(state=state, player_id=context.player_id)
    command_point_cost = _selected_command_point_cost(
        definition=definition,
        effect_selection=effect_selection,
    )
    _validate_supported_stratagem_handler_available(
        definition=definition,
        stratagem_handler_registry=stratagem_handler_registry,
    )
    spend_result: CommandPointSpendResult | None = None
    transaction_id: str | None = None
    if command_point_cost > 0:
        spend_result = state.spend_command_points(
            player_id=context.player_id,
            amount=command_point_cost,
            source_id=use_id,
        )
        if spend_result.status is not CommandPointSpendStatus.APPLIED:
            raise GameLifecycleError("Prevalidated stratagem spend failed.")
        if spend_result.transaction is None:
            raise GameLifecycleError("Applied stratagem spend is missing transaction.")
        transaction_id = spend_result.transaction.transaction_id
        decisions.event_log.append("command_points_spent", spend_result.to_payload())
    try:
        targeted_unit_ids = _stratagem_targeted_unit_ids(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
        )
        affected_unit_ids = _stratagem_affected_unit_ids(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
        )
    except GameLifecycleError as exc:
        raise GameLifecycleError(
            "Prevalidated stratagem affected-unit context is invalid."
        ) from exc
    use_record = StratagemUseRecord(
        use_id=use_id,
        player_id=context.player_id,
        stratagem_id=definition.stratagem_id,
        source_id=definition.source_id,
        battle_round=context.battle_round,
        phase=context.phase,
        active_player_id=context.active_player_id,
        timing_window_id=context.timing_window_id,
        request_id=result.request_id,
        result_id=result.result_id,
        selected_option_id=result.selected_option_id,
        target_binding=target_binding,
        targeted_unit_instance_ids=targeted_unit_ids,
        affected_unit_instance_ids=affected_unit_ids,
        command_point_cost=command_point_cost,
        command_point_transaction_id=transaction_id,
        handler_id=definition.handler_id,
        effect_selection=effect_selection,
        effect_payload=definition.effect_payload,
    )
    state.record_stratagem_use(use_record)
    decisions.event_log.append("stratagem_used", use_record.to_payload())
    _apply_command_point_effects(
        state=state,
        decisions=decisions,
        player_id=context.player_id,
        source_id=use_id,
        effect_payload=definition.effect_payload,
    )
    _apply_supported_stratagem_handler(
        state=state,
        decisions=decisions,
        result=result,
        context=context,
        definition=definition,
        target_binding=target_binding,
        use_record=use_record,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
    )
    return use_record


def invalid_stratagem_target_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(state, "Stratagem target proposal selected invalid option.", "malformed")
    request_proposal = _proposal_from_request_payload(request.payload)
    if request_proposal is None:
        return _invalid(state, "Malformed stratagem target proposal request.", "malformed_request")
    submitted_proposal = _proposal_from_result_payload(result.payload)
    if submitted_proposal is None:
        return _invalid(state, "Malformed stratagem target proposal payload.", "malformed_payload")
    context_error = _proposal_context_error(
        state=state,
        request_proposal=request_proposal,
        submitted_proposal=submitted_proposal,
    )
    if context_error is not None:
        return _invalid(state, "Stratagem target proposal context drift.", context_error)
    if submitted_proposal.target_binding is None:
        return _invalid(state, "Stratagem target proposal requires target binding.", "schema")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=request_proposal.catalog_record,
        context=request_proposal.context,
        target_binding=submitted_proposal.target_binding,
        effect_selection=submitted_proposal.effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if violation is not None:
        return _invalid(state, "Stratagem target proposal is not legal.", violation)
    return None


def apply_stratagem_target_proposal(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None = None,
) -> StratagemUseRecord:
    proposal = _proposal_from_result_payload(result.payload)
    if proposal is None or proposal.target_binding is None:
        raise GameLifecycleError("Stratagem target proposal was not prevalidated.")
    decisions.event_log.append(
        "stratagem_target_proposal_accepted",
        {
            "request_id": result.request_id,
            "result_id": result.result_id,
            "proposal": proposal.to_payload(),
        },
    )
    return _apply_stratagem_use(
        state=state,
        result=result,
        decisions=decisions,
        context=proposal.context,
        catalog_record=proposal.catalog_record,
        target_binding=proposal.target_binding,
        effect_selection=proposal.effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
    )


def is_stratagem_placement_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem placement proposal check requires a request.")
    if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    return proposal_request is not None and _proposal_request_is_rapid_ingress(proposal_request)


def invalid_stratagem_placement_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(state, "Stratagem placement proposal selected invalid option.", "malformed")
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not _proposal_request_is_rapid_ingress(proposal_request):
        return _invalid(state, "Malformed stratagem placement proposal request.", "malformed")
    submitted = _placement_proposal_from_result_payload(result.payload)
    if submitted is None:
        return _invalid(state, "Malformed stratagem placement proposal payload.", "malformed")
    validation = submitted.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Stratagem placement proposal context drift.",
            payload=validate_json_value(
                {"proposal_validation": validate_json_value(validation.to_payload())}
            ),
        )
    reserve_state = state.reserve_state_for_unit(submitted.unit_instance_id)
    if reserve_state is None or reserve_state.status is not ReserveStatus.IN_RESERVES:
        return _invalid(state, "Stratagem placement proposal reserve drift.", "reserve_drift")
    return None


def apply_stratagem_placement_proposal(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not _proposal_request_is_rapid_ingress(proposal_request):
        raise GameLifecycleError("Stratagem placement proposal was not prevalidated.")
    submitted = _placement_proposal_from_result_payload(result.payload)
    if submitted is None:
        raise GameLifecycleError("Stratagem placement proposal payload was not prevalidated.")
    return _apply_rapid_ingress_placement(
        state=state,
        decisions=decisions,
        result=result,
        proposal_request=proposal_request,
        submitted=submitted,
        ruleset_descriptor=ruleset_descriptor,
    )


def is_heroic_intervention_charge_move_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Heroic Intervention proposal check requires a request.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    return (
        proposal_request is not None
        and proposal_request.context is not None
        and proposal_request.context.get("stratagem_handler_id")
        == CORE_HEROIC_INTERVENTION_HANDLER_ID
    )


def invalid_heroic_intervention_charge_move_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(state, "Heroic Intervention proposal selected invalid option.", "malformed")
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not is_heroic_intervention_charge_move_request(request):
        return _invalid(state, "Malformed Heroic Intervention proposal request.", "malformed")
    submitted = _heroic_intervention_charge_move_from_result_payload(result.payload)
    if submitted is None:
        return _invalid(state, "Malformed Heroic Intervention proposal payload.", "malformed")
    validation = submitted.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Heroic Intervention proposal context drift.",
            payload={"proposal_validation": validate_json_value(validation.to_payload())},
        )
    request_error = _heroic_intervention_charge_move_request_error(
        state=state,
        proposal_request=proposal_request,
        proposal=submitted,
    )
    if request_error is not None:
        return _invalid(
            state,
            "Heroic Intervention charge move is not legal.",
            request_error,
        )
    return None


def apply_heroic_intervention_charge_move(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not is_heroic_intervention_charge_move_request(request):
        raise GameLifecycleError("Heroic Intervention proposal was not prevalidated.")
    proposal = _heroic_intervention_charge_move_from_result_payload(result.payload)
    if proposal is None:
        raise GameLifecycleError("Heroic Intervention proposal payload was not prevalidated.")
    if proposal.is_no_move_choice:
        decisions.event_log.append(
            "heroic_intervention_charge_move_declined",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
            },
        )
        return None
    if proposal.witness is None:
        raise GameLifecycleError("Validated Heroic Intervention proposal requires a witness.")
    use_record = _stratagem_use_from_proposal_context(proposal_request)
    maximum_distance = _heroic_intervention_maximum_distance(proposal_request)
    scenario = _battlefield_scenario_for_stratagem(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=proposal.charge_target_unit_instance_ids,
        maximum_distance_inches=maximum_distance,
        path_witness=proposal.witness,
        hover_mode_states=tuple(state.hover_mode_states),
        terrain_features=_stratagem_terrain_features(state),
    )
    violation = charge_move_violation_code(
        resolution=resolution,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=maximum_distance,
    )
    if violation is not None:
        message = charge_move_invalid_message(violation)
        invalid_validation = ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code=violation,
            message=message,
            field=charge_move_violation_field(violation),
        )
        payload = validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "heroic_intervention_charge_move_invalid",
                "unit_instance_id": resolution.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
                "violation_code": violation,
                "proposal_validation": invalid_validation.to_payload(),
                **resolution.movement_payload,
            }
        )
        decisions.event_log.append("heroic_intervention_charge_move_invalid", payload)
        retry_request = _request_heroic_intervention_charge_move_retry(
            state=state,
            decisions=decisions,
            proposal_request=proposal_request,
            rejected_result=result,
        )
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=message,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "heroic_intervention_charge_move_invalid",
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "unit_instance_id": resolution.unit_instance_id,
                "movement_phase_action": CHARGE_MOVE_ACTION,
                "violation_code": violation,
                "next_request_id": retry_request.request_id,
                "proposal_validation": validate_json_value(invalid_validation.to_payload()),
            },
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Heroic Intervention requires battlefield_state.")
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(resolution.attempted_placement)
    )
    effect = PersistingEffect(
        effect_id=f"{result.result_id}:heroic-intervention:fights-first",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(proposal.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.CHARGE,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=state.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": "charge_grants_fights_first",
            "source_rule_id": use_record.source_id,
            "stratagem_use_id": use_record.use_id,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "heroic_intervention_charge_move_completed",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "proposal_request_id": proposal_request.request_id,
            "transition_batch": transition_batch.to_payload(),
            "persisting_effect": effect.to_payload(),
            **resolution.movement_payload,
        },
    )
    return None


def _request_heroic_intervention_charge_move_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    use_record = _stratagem_use_from_proposal_context(proposal_request)
    context = _heroic_intervention_request_context(proposal_request)
    reachable = _heroic_intervention_requested_reachable_distances(proposal_request)
    decisions.event_log.append(
        "heroic_intervention_charge_move_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "mode": _heroic_intervention_mode_from_request(proposal_request),
            "charge_roll_state": context["charge_roll_state"],
            "maximum_distance_inches": _heroic_intervention_maximum_distance(proposal_request),
            "reachable_target_unit_instance_ids": list(reachable),
            "reachable_target_distances_inches": reachable,
            "request_id": request.request_id,
            "previous_proposal_request_id": proposal_request.request_id,
            "rejected_result_id": rejected_result.result_id,
            "phase_body_status": "heroic_intervention_charge_move_proposal_required",
        },
    )
    return request


def stratagem_availability_kind_from_token(token: object) -> StratagemAvailabilityKind:
    if type(token) is StratagemAvailabilityKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemAvailabilityKind token must be a string.")
    try:
        return StratagemAvailabilityKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported StratagemAvailabilityKind token: {token}.") from exc


def stratagem_category_from_token(token: object) -> StratagemCategory:
    if type(token) is StratagemCategory:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemCategory token must be a string.")
    try:
        return StratagemCategory(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported StratagemCategory token: {token}.") from exc


def stratagem_target_kind_from_token(token: object) -> StratagemTargetKind:
    if type(token) is StratagemTargetKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemTargetKind token must be a string.")
    try:
        return StratagemTargetKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported StratagemTargetKind token: {token}.") from exc


def _stratagem_decision_option(
    *,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> DecisionOption:
    definition = record.definition
    option_id = (
        f"use-stratagem:{definition.stratagem_id}:target:{_target_binding_token(target_binding)}"
    )
    return DecisionOption(
        option_id=option_id,
        label=definition.name,
        payload=validate_json_value(
            {
                "submission_kind": STRATAGEM_DECISION_TYPE,
                "context": context.to_payload(),
                "catalog_record": record.to_payload(),
                "target_binding": target_binding.to_payload(),
                "effect_selection": None,
            }
        ),
    )


def _stratagem_selection_from_result_payload(
    payload: JsonValue,
) -> (
    tuple[
        StratagemEligibilityContext,
        StratagemCatalogRecord,
        StratagemTargetBinding,
        JsonValue,
    ]
    | None
):
    if not isinstance(payload, dict):
        return None
    if payload.get("submission_kind") != STRATAGEM_DECISION_TYPE:
        return None
    context_payload = payload.get("context")
    record_payload = payload.get("catalog_record")
    binding_payload = payload.get("target_binding")
    effect_selection = payload.get("effect_selection")
    if not isinstance(context_payload, dict):
        return None
    if not isinstance(record_payload, dict):
        return None
    if not isinstance(binding_payload, dict):
        return None
    try:
        return (
            StratagemEligibilityContext.from_payload(
                cast(StratagemEligibilityContextPayload, context_payload)
            ),
            StratagemCatalogRecord.from_payload(
                cast(StratagemCatalogRecordPayload, record_payload)
            ),
            StratagemTargetBinding.from_payload(
                cast(StratagemTargetBindingPayload, binding_payload)
            ),
            validate_json_value(effect_selection),
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _require_stratagem_selection(
    payload: JsonValue,
) -> tuple[StratagemEligibilityContext, StratagemCatalogRecord, StratagemTargetBinding, JsonValue]:
    selection = _stratagem_selection_from_result_payload(payload)
    if selection is None:
        raise GameLifecycleError("Stratagem decision payload was not prevalidated.")
    return selection


def _record_is_available_for_context(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
) -> bool:
    return (
        _stratagem_unavailable_reason(
            state=state,
            record=record,
            context=context,
            target_binding=None,
        )
        is None
    )


def _stratagem_unavailable_reason(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue = None,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
) -> str | None:
    if state.stage is not GameLifecycleStage.BATTLE:
        return "not_battle_stage"
    drift = _context_state_drift(state=state, context=context)
    if drift is not None:
        return drift
    if record.disabled:
        return "stratagem_disabled"
    if _stratagem_handler_is_unsupported(record.definition):
        return "unsupported_handler"
    if not record.definition.timing.matches(context):
        return "timing_window_mismatch"
    effect_selection_error = _effect_selection_error(
        definition=record.definition,
        effect_selection=effect_selection,
    )
    if effect_selection_error is not None:
        return effect_selection_error
    command_point_cost = _selected_command_point_cost(
        definition=record.definition,
        effect_selection=effect_selection,
    )
    if state.command_point_total(context.player_id) < command_point_cost:
        return "insufficient_command_points"
    if not _detachment_gate_allows(state=state, record=record, player_id=context.player_id):
        return "detachment_gate_closed"
    handler_reason = _handler_unavailable_reason(
        state=state,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        ruleset_descriptor=ruleset_descriptor,
    )
    if handler_reason is not None:
        return handler_reason
    if target_binding is not None:
        target_error = _target_binding_error(
            state=state,
            player_id=context.player_id,
            target_spec=record.definition.target_spec,
            policy=record.definition.restriction_policy,
            target_binding=target_binding,
            context=context,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
        if target_error is not None:
            return target_error
    restriction = _restriction_violation(
        state=state,
        player_id=context.player_id,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
    )
    if restriction is not None:
        return restriction
    return None


def _context_state_drift(*, state: GameState, context: StratagemEligibilityContext) -> str | None:
    if state.game_id != context.game_id:
        return "wrong_context"
    if state.battle_round != context.battle_round:
        return "stale_battle_round"
    if state.current_battle_phase is not context.phase:
        return "stale_phase"
    if state.active_player_id != context.active_player_id:
        return "stale_active_player"
    if context.player_id not in state.player_ids:
        return "unknown_player"
    return None


def _detachment_gate_allows(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    player_id: str,
) -> bool:
    if record.availability_kind is StratagemAvailabilityKind.CORE:
        return True
    for army in state.army_definitions:
        if army.player_id != player_id:
            continue
        selection = army.detachment_selection
        return (
            record.detachment_id in selection.detachment_ids
            and record.definition.stratagem_id in selection.stratagem_ids
        )
    return False


def _effect_selection_error(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> str | None:
    if definition.handler_id == CORE_HEROIC_INTERVENTION_HANDLER_ID:
        return _heroic_intervention_mode_error(
            definition=definition,
            effect_selection=effect_selection,
        )
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID:
        if effect_selection is None:
            return None
        return _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(
                CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY,
                CRUSHING_IMPACT_MODEL_CONTEXT_KEY,
            ),
        )
    if definition.handler_id == CORE_EPIC_CHALLENGE_HANDLER_ID:
        if effect_selection is None:
            return None
        return _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY,),
        )
    if effect_selection is not None:
        return "effect_selection_not_supported"
    return None


def _selected_command_point_cost(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> int:
    if definition.handler_id != CORE_HEROIC_INTERVENTION_HANDLER_ID:
        return definition.command_point_cost
    return definition.command_point_cost + _heroic_intervention_mode_additional_cost(
        definition=definition,
        effect_selection=effect_selection,
    )


def _heroic_intervention_mode_error(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> str | None:
    if effect_selection is None:
        return None
    mode = _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
    )
    if mode is None:
        return "heroic_intervention_mode_required"
    if mode not in _heroic_intervention_mode_costs(definition):
        return "heroic_intervention_mode_unknown"
    return None


def _heroic_intervention_mode(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> str:
    if effect_selection is None:
        return HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND
    mode = _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
    )
    if mode is None or mode not in _heroic_intervention_mode_costs(definition):
        raise GameLifecycleError("Heroic Intervention mode was not prevalidated.")
    return mode


def _heroic_intervention_mode_additional_cost(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> int:
    mode = _heroic_intervention_mode(definition=definition, effect_selection=effect_selection)
    return _heroic_intervention_mode_costs(definition)[mode]


def _heroic_intervention_mode_costs(definition: StratagemDefinition) -> Mapping[str, int]:
    payload = definition.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Heroic Intervention source payload requires modes.")
    modes = payload.get("modes")
    if not isinstance(modes, list):
        raise GameLifecycleError("Heroic Intervention source payload modes must be a list.")
    costs: dict[str, int] = {}
    for mode_payload in modes:
        if not isinstance(mode_payload, dict):
            raise GameLifecycleError("Heroic Intervention mode payload must be an object.")
        mode = mode_payload.get("mode")
        cost = mode_payload.get("additional_command_point_cost")
        if type(mode) is not str or type(cost) is not int:
            raise GameLifecycleError("Heroic Intervention mode payload is malformed.")
        costs[_validate_identifier("Heroic Intervention mode", mode)] = _validate_non_negative_int(
            "Heroic Intervention additional CP cost",
            cost,
        )
    if HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND not in costs:
        raise GameLifecycleError("Heroic Intervention modes require Leap to Defend.")
    return MappingProxyType(dict(sorted(costs.items())))


def _required_effect_selection_fields_error(
    *,
    effect_selection: JsonValue,
    field_names: tuple[str, ...],
) -> str | None:
    if not isinstance(effect_selection, dict):
        return "effect_selection_malformed"
    for field_name in field_names:
        if type(effect_selection.get(field_name)) is not str:
            return f"{field_name}_required"
    return None


def _effect_selection_string_or_none(
    *,
    effect_selection: JsonValue,
    key: str,
) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    value = effect_selection.get(key)
    if type(value) is not str:
        return None
    return _validate_identifier(key, value)


def _handler_unavailable_reason(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue,
    ruleset_descriptor: RulesetDescriptor | None,
) -> str | None:
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        return _command_reroll_context_error(
            state=state,
            definition=definition,
            context=context,
        )
    if definition.handler_id == CORE_INSANE_BRAVERY_HANDLER_ID:
        if target_binding is None:
            if _battle_shock_test_unit_ids(state=state, player_id=context.player_id):
                return None
            return "no_eligible_battle_shock_test"
        return None
    if definition.handler_id == CORE_RAPID_INGRESS_HANDLER_ID:
        if context.active_player_id == context.player_id:
            return "rapid_ingress_requires_opponent_turn"
        if target_binding is None:
            return (
                None
                if _rapid_ingress_unit_ids(state=state, player_id=context.player_id)
                else ("no_eligible_reserve_unit")
            )
        return None
    if definition.handler_id == CORE_NEW_ORDERS_HANDLER_ID:
        if target_binding is None:
            return (
                None
                if _active_tactical_secondary_cards(
                    state=state,
                    player_id=context.player_id,
                )
                else "no_active_tactical_secondary_card"
            )
        return None
    if definition.handler_id == CORE_FIRE_OVERWATCH_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.END_PHASE:
            return "fire_overwatch_requires_end_opponent_movement_phase"
        if context.phase is not BattlePhase.MOVEMENT:
            return "fire_overwatch_requires_movement_phase"
        if context.active_player_id == context.player_id:
            return "fire_overwatch_requires_opponent_turn"
        if _fire_overwatch_triggering_enemy_unit_id_or_none(context) is None:
            return "missing_fire_overwatch_trigger_unit"
        return None
    if definition.handler_id in {
        CORE_GO_TO_GROUND_HANDLER_ID,
        CORE_SMOKESCREEN_HANDLER_ID,
    }:
        if context.active_player_id == context.player_id:
            return "defensive_stratagem_requires_opponent_turn"
        selected_context_error = _selected_target_context_error(
            context=context,
            target_binding=target_binding,
        )
        if selected_context_error is not None:
            return selected_context_error
        return None
    if definition.handler_id == CORE_EXPLOSIVES_HANDLER_ID:
        if target_binding is None:
            return None
        return _explosives_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
        )
    if definition.handler_id == CORE_HEROIC_INTERVENTION_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.END_PHASE:
            return "heroic_intervention_requires_end_charge_phase"
        if context.phase is not BattlePhase.CHARGE:
            return "heroic_intervention_requires_charge_phase"
        if context.active_player_id == context.player_id:
            return "heroic_intervention_requires_opponent_turn"
        return None
    if definition.handler_id == CORE_COUNTEROFFENSIVE_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT:
            return "counteroffensive_requires_enemy_fought_trigger"
        if context.phase is not BattlePhase.FIGHT:
            return "counteroffensive_requires_fight_phase"
        if context.active_player_id is None:
            return "counteroffensive_requires_active_player"
        if target_binding is not None:
            return _counteroffensive_target_context_error(
                state=state,
                context=context,
                target_binding=target_binding,
                ruleset_descriptor=ruleset_descriptor,
            )
        return None
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE:
            return "crushing_impact_requires_charge_move_trigger"
        if context.phase is not BattlePhase.CHARGE:
            return "crushing_impact_requires_charge_phase"
        if context.active_player_id != context.player_id:
            return "crushing_impact_requires_own_charge_phase"
        if target_binding is None:
            return None
        return _crushing_impact_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
        )
    if definition.handler_id == CORE_EPIC_CHALLENGE_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT:
            return "epic_challenge_requires_selected_to_fight_trigger"
        if context.phase is not BattlePhase.FIGHT:
            return "epic_challenge_requires_fight_phase"
        if target_binding is None:
            return None
        return _epic_challenge_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
        )
    if definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        _generic_rule_ir_from_stratagem_payload(definition.effect_payload)
        return None
    return None


def _restriction_violation(
    *,
    state: GameState,
    player_id: str,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    policy = definition.restriction_policy
    previous_uses = state.stratagem_use_records_for_player(player_id)
    if policy.same_stratagem_per_phase and any(
        use.stratagem_id == definition.stratagem_id
        and _same_stratagem_phase(use=use, context=context)
        for use in previous_uses
    ):
        return "same_stratagem_per_phase"
    if policy.once_per_turn and any(
        use.stratagem_id == definition.stratagem_id
        and use.battle_round == context.battle_round
        and use.player_id == player_id
        for use in previous_uses
    ):
        return "once_per_turn"
    if policy.once_per_battle and any(
        use.stratagem_id == definition.stratagem_id for use in previous_uses
    ):
        return "once_per_battle"
    if (
        policy.once_per_target_per_phase
        and target_binding is not None
        and target_binding.target_unit_instance_id is not None
        and any(
            use.stratagem_id == definition.stratagem_id
            and _same_stratagem_phase(use=use, context=context)
            and use.target_binding.target_unit_instance_id == target_binding.target_unit_instance_id
            for use in previous_uses
        )
    ):
        return "once_per_target_per_phase"
    targeted_unit_ids = _stratagem_targeted_unit_ids(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
    )
    if policy.same_unit_target_per_phase and targeted_unit_ids:
        targeted_unit_id_set = set(targeted_unit_ids)
        if any(
            _same_stratagem_phase(use=use, context=context)
            and targeted_unit_id_set.intersection(use.targeted_unit_instance_ids)
            for use in previous_uses
        ):
            return "targeted_unit_already_stratagem_target"
    return None


def _same_stratagem_phase(*, use: StratagemUseRecord, context: StratagemEligibilityContext) -> bool:
    return (
        use.battle_round == context.battle_round
        and use.phase is context.phase
        and use.active_player_id == context.active_player_id
    )


def _stratagem_targeted_unit_ids(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> tuple[str, ...]:
    raw_unit_ids: list[str] = []
    if target_binding is not None and target_binding.target_unit_instance_id is not None:
        raw_unit_ids.append(target_binding.target_unit_instance_id)
    if not raw_unit_ids:
        return ()
    return _validate_stratagem_affected_unit_ids(
        tuple(
            _canonical_stratagem_affected_unit_id(
                state=state,
                unit_instance_id=unit_instance_id,
            )
            for unit_instance_id in raw_unit_ids
        )
    )


def _stratagem_affected_unit_ids(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue = None,
) -> tuple[str, ...]:
    raw_unit_ids: list[str] = []
    if target_binding is not None and target_binding.target_unit_instance_id is not None:
        raw_unit_ids.append(target_binding.target_unit_instance_id)
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        raw_unit_ids.append(_command_reroll_affected_unit_id(context))
    if definition.handler_id == CORE_EXPLOSIVES_HANDLER_ID and target_binding is not None:
        explosives_target_id = _explosives_target_unit_id_or_none(context)
        if explosives_target_id is not None:
            raw_unit_ids.append(explosives_target_id)
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID and target_binding is not None:
        crushing_target_id = _crushing_impact_enemy_target_id_or_none(effect_selection)
        if crushing_target_id is not None:
            raw_unit_ids.append(crushing_target_id)
    if not raw_unit_ids:
        return ()
    return _validate_stratagem_affected_unit_ids(
        tuple(
            _canonical_stratagem_affected_unit_id(
                state=state,
                unit_instance_id=unit_instance_id,
            )
            for unit_instance_id in raw_unit_ids
        )
    )


def _canonical_stratagem_affected_unit_id(
    *,
    state: GameState,
    unit_instance_id: str,
) -> str:
    requested_unit_id = _validate_identifier("affected_unit_instance_id", unit_instance_id)
    owner = _rules_unit_owner(state=state, unit_instance_id=requested_unit_id)
    if owner is None:
        raise GameLifecycleError("Stratagem affected unit is unknown.")
    if requested_unit_id.startswith("attached-unit:"):
        return requested_unit_id
    attached_unit_id = _attached_unit_id_for_component(
        state=state,
        unit_instance_id=requested_unit_id,
    )
    if attached_unit_id is not None:
        return attached_unit_id
    unit = _unit_by_id_or_none(state=state, unit_instance_id=requested_unit_id)
    if unit is not None and _unit_has_keyword(unit, "ATTACHED_UNIT"):
        return requested_unit_id
    if unit is not None and _unit_has_runtime_attached_role(unit):
        raise GameLifecycleError("Runtime attached unit requires attached-unit identity.")
    return requested_unit_id


def _attached_unit_id_for_component(
    *,
    state: GameState,
    unit_instance_id: str,
) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matched_attached_ids = tuple(
        attached_unit.attached_unit_instance_id
        for army_definition in state.army_definitions
        for attached_unit in army_definition.attached_units
        if requested_unit_id in attached_unit.component_unit_instance_ids
    )
    if len(matched_attached_ids) > 1:
        raise GameLifecycleError("Attached component has multiple attached identities.")
    if matched_attached_ids:
        return matched_attached_ids[0]
    component_record = None
    for record in state.starting_strength_records:
        if record.unit_instance_id == requested_unit_id:
            component_record = record
            break
    if component_record is None:
        return None
    attached_unit_ids = tuple(
        record.unit_instance_id
        for record in state.starting_strength_records
        if record.player_id == component_record.player_id
        and record.source_id == component_record.source_id
        and record.unit_instance_id.startswith("attached-unit:")
    )
    if len(attached_unit_ids) > 1:
        raise GameLifecycleError("Attached-unit source has multiple attached identities.")
    if attached_unit_ids:
        return attached_unit_ids[0]
    return None


def _unit_has_runtime_attached_role(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Attached-role lookup requires a UnitInstance.")
    return any(
        source_id.startswith(("runtime-attached-unit:", "attached-role:"))
        for model in unit.own_models
        for source_id in model.source_ids
    )


def _rules_unit_owner(*, state: GameState, unit_instance_id: str) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    owner = _unit_owner(state=state, unit_instance_id=requested_unit_id)
    if owner is not None:
        return owner
    for record in state.starting_strength_records:
        if record.unit_instance_id == requested_unit_id:
            return record.player_id
    return None


def _enumerated_target_bindings(
    *,
    state: GameState,
    player_id: str,
    definition: StratagemDefinition,
) -> tuple[StratagemTargetBinding, ...]:
    target_spec = definition.target_spec
    if target_spec.target_kind is StratagemTargetKind.NONE:
        return (StratagemTargetBinding.none(),)
    if target_spec.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        return tuple(
            StratagemTargetBinding(
                target_kind=StratagemTargetKind.TACTICAL_SECONDARY_CARD,
                target_player_id=card.player_id,
                target_secondary_mission_id=card.secondary_mission_id,
            )
            for card in _active_tactical_secondary_cards(state=state, player_id=player_id)
        )
    bindings: list[StratagemTargetBinding] = []
    for army in state.army_definitions:
        if (
            target_spec.target_kind is StratagemTargetKind.FRIENDLY_UNIT
            and army.player_id != player_id
        ):
            continue
        for unit in army.units:
            binding = StratagemTargetBinding(
                target_kind=target_spec.target_kind,
                target_player_id=army.player_id,
                target_unit_instance_id=unit.unit_instance_id,
            )
            if (
                _target_binding_error(
                    state=state,
                    player_id=player_id,
                    target_spec=target_spec,
                    policy=definition.restriction_policy,
                    target_binding=binding,
                    context=None,
                    ruleset_descriptor=None,
                    army_catalog=None,
                )
                is None
            ):
                bindings.append(binding)
    return tuple(
        sorted(
            bindings,
            key=lambda binding: (
                "" if binding.target_player_id is None else binding.target_player_id,
                "" if binding.target_unit_instance_id is None else binding.target_unit_instance_id,
                ""
                if binding.target_secondary_mission_id is None
                else binding.target_secondary_mission_id,
            ),
        )
    )


def _target_binding_error(
    *,
    state: GameState,
    player_id: str,
    target_spec: StratagemTargetSpec,
    policy: StratagemRestrictionPolicy,
    target_binding: StratagemTargetBinding,
    context: StratagemEligibilityContext | None,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> str | None:
    if target_spec.target_kind is StratagemTargetKind.NONE:
        if target_binding.target_kind is not StratagemTargetKind.NONE:
            return "target_not_allowed"
        return None
    if target_binding.target_kind is StratagemTargetKind.NONE:
        return "target_required"
    if target_spec.target_policy_id.startswith("unsupported:"):
        return "unsupported_target_policy"
    if target_spec.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        if target_binding.target_kind is not StratagemTargetKind.TACTICAL_SECONDARY_CARD:
            return "target_kind_mismatch"
        if target_binding.target_player_id != player_id:
            return "target_not_controlled_by_player"
        if _target_secondary_mission_id(target_binding) not in {
            card.secondary_mission_id
            for card in _active_tactical_secondary_cards(state=state, player_id=player_id)
        }:
            return "tactical_secondary_card_not_active"
        if target_spec.target_policy_id != NEW_ORDERS_TARGET_POLICY_ID:
            return "unsupported_target_policy"
        return None
    if target_binding.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        return "target_kind_mismatch"
    if (
        target_spec.target_kind is StratagemTargetKind.FRIENDLY_UNIT
        and target_binding.target_player_id != player_id
    ):
        return "target_not_friendly"
    target_owner = _target_unit_owner(state=state, target_binding=target_binding)
    if target_owner is None:
        return "unknown_target_unit"
    if target_owner != target_binding.target_player_id:
        return "target_owner_drift"
    permission = friendly_stratagem_target_permission(
        player_id=player_id,
        target_player_id=target_owner,
        target_unit_instance_id=_require_target_unit_id(target_binding),
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        allow_battle_shocked=policy.allow_battle_shocked_targets,
    )
    if not permission.is_allowed:
        if permission.denial_reason is None:
            raise GameLifecycleError("Denied stratagem target permission must explain denial.")
        return permission.denial_reason
    if target_spec.target_policy_id == INSANE_BRAVERY_TARGET_POLICY_ID:
        if _require_target_unit_id(target_binding) not in _battle_shock_test_unit_ids(
            state=state,
            player_id=player_id,
        ):
            return "unit_not_pending_battle_shock_test"
        return None
    if target_spec.target_policy_id == RAPID_INGRESS_TARGET_POLICY_ID:
        if _require_target_unit_id(target_binding) not in _rapid_ingress_unit_ids(
            state=state,
            player_id=player_id,
        ):
            return "unit_not_eligible_for_rapid_ingress"
        return None
    if target_spec.target_policy_id == GO_TO_GROUND_TARGET_POLICY_ID:
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="INFANTRY",
        ):
            return "unit_not_infantry"
        return None
    if target_spec.target_policy_id == SMOKESCREEN_TARGET_POLICY_ID:
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="SMOKE",
        ):
            return "unit_not_smoke"
        return None
    if target_spec.target_policy_id == EXPLOSIVES_TARGET_POLICY_ID:
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="GRENADES",
        ):
            return "unit_not_grenades"
        return None
    if target_spec.target_policy_id == FIRE_OVERWATCH_TARGET_POLICY_ID:
        if context is None:
            return None
        return _fire_overwatch_target_binding_error(
            state=state,
            player_id=player_id,
            context=context,
            target_binding=target_binding,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
    if target_spec.target_policy_id == HEROIC_INTERVENTION_TARGET_POLICY_ID:
        if context is None:
            return None
        return _heroic_intervention_target_binding_error(
            state=state,
            player_id=player_id,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == COUNTEROFFENSIVE_TARGET_POLICY_ID:
        return None
    if target_spec.target_policy_id == CRUSHING_IMPACT_TARGET_POLICY_ID:
        if not (
            _target_unit_has_keyword(state=state, target_binding=target_binding, keyword="MONSTER")
            or _target_unit_has_keyword(
                state=state,
                target_binding=target_binding,
                keyword="VEHICLE",
            )
        ):
            return "unit_not_monster_or_vehicle"
        return None
    if target_spec.target_policy_id == EPIC_CHALLENGE_TARGET_POLICY_ID:
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="CHARACTER",
        ):
            return "unit_not_character"
        return None
    if target_spec.target_policy_id not in {"friendly_unit", "any_unit"}:
        return "unsupported_target_policy"
    return None


def _target_unit_owner(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
) -> str | None:
    target_unit_id = target_binding.target_unit_instance_id
    if target_unit_id is None:
        return None
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == target_unit_id:
                return army.player_id
    return None


def _target_unit_has_keyword(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    keyword: str,
) -> bool:
    target_unit_id = _require_target_unit_id(target_binding)
    canonical = _canonical_keyword(keyword)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id != target_unit_id:
                continue
            return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}
    raise GameLifecycleError("Stratagem target unit is unknown.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Stratagem keyword lookup requires a UnitInstance.")
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str:
        raise GameLifecycleError("Stratagem keyword must be a string.")
    stripped = keyword.strip()
    if not stripped:
        raise GameLifecycleError("Stratagem keyword must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _active_tactical_secondary_cards(
    *,
    state: GameState,
    player_id: str,
) -> tuple[SecondaryMissionCardState, ...]:
    return tuple(
        sorted(
            (
                card
                for card in state.secondary_mission_card_states
                if card.player_id == player_id
                and card.mode is SecondaryMissionCardMode.TACTICAL
                and card.status is SecondaryMissionCardStatus.ACTIVE
            ),
            key=lambda card: card.secondary_mission_id,
        )
    )


def _battle_shock_test_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return ()
    army = state.army_definition_for_player(player_id)
    if army is None:
        return ()
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        army=army,
        battlefield_state=battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
    )
    return tuple(sorted({request.unit_instance_id for request in requests}))


def _rapid_ingress_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            reserve_state.unit_instance_id
            for reserve_state in state.unarrived_reserve_states_for_player(player_id)
            if reserve_state.status is ReserveStatus.IN_RESERVES
        )
    )


def _command_reroll_context_error(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
) -> str | None:
    try:
        roll_state = _command_reroll_state(context)
        if roll_state.original_result.spec.actor_id != context.player_id:
            return "dice_roll_actor_drift"
        roll_type = roll_state.original_result.spec.roll_type
        if _command_reroll_roll_class(roll_type) not in definition.eligible_roll_types:
            return "ineligible_dice_roll_type"
        if roll_state.original_result.spec.reroll_forbidden_rule_ids:
            return "dice_roll_reroll_forbidden"
        affected_unit_id = _command_reroll_affected_unit_id(context)
        if _rules_unit_owner(state=state, unit_instance_id=affected_unit_id) != context.player_id:
            return "affected_unit_owner_drift"
        _canonical_stratagem_affected_unit_id(
            state=state,
            unit_instance_id=affected_unit_id,
        )
        permission = _command_reroll_permission(
            source_id=CORE_COMMAND_REROLL_HANDLER_ID,
            context=context,
            roll_state=roll_state,
        )
        permission.legal_selections_for_state(roll_state)
    except (DiceRollSpecError, GameLifecycleError):  # fmt: skip
        return "invalid_dice_roll_context"
    return None


def _command_reroll_roll_class(roll_type: str) -> str:
    if roll_type == "attack_sequence.hit":
        return "hit_roll"
    if roll_type == "attack_sequence.wound":
        return "wound_roll"
    if roll_type.startswith("attack_sequence.save."):
        return "save_roll"
    if roll_type.startswith("attack_sequence.damage"):
        return "damage_roll"
    if roll_type.startswith("random_characteristic.damage."):
        return "damage_roll"
    return roll_type


def _command_reroll_state(context: StratagemEligibilityContext) -> DiceRollState:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice roll trigger payload.")
    roll_payload = trigger_payload.get(COMMAND_REROLL_DICE_CONTEXT_KEY)
    if not isinstance(roll_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice_roll_state payload.")
    return DiceRollState.from_payload(cast(DiceRollStatePayload, roll_payload))


def _command_reroll_affected_unit_id(context: StratagemEligibilityContext) -> str:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice roll trigger payload.")
    unit_id = trigger_payload.get(COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY)
    if type(unit_id) is not str:
        raise GameLifecycleError("Command Re-roll requires affected unit context.")
    return _validate_identifier("Command Re-roll affected unit id", unit_id)


def _command_reroll_permission(
    *,
    source_id: str,
    context: StratagemEligibilityContext,
    roll_state: DiceRollState,
) -> RerollPermission:
    roll_type = roll_state.original_result.spec.roll_type
    if roll_type == "charge_roll" or len(roll_state.current_values) == 1:
        return RerollPermission(
            source_id=source_id,
            timing_window=context.timing_window_id or context.trigger_kind.value,
            owning_player_id=context.player_id,
            eligible_roll_type=roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
    already_rerolled = set(roll_state.rerolled_indices())
    return RerollPermission(
        source_id=source_id,
        timing_window=context.timing_window_id or context.trigger_kind.value,
        owning_player_id=context.player_id,
        eligible_roll_type=roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=tuple(
            (index,)
            for index, _value in enumerate(roll_state.current_values)
            if index not in already_rerolled
        ),
    )


def _selected_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind is not TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET:
        return "selected_target_requires_target_selection_trigger"
    if context.phase is not BattlePhase.SHOOTING:
        return "selected_target_requires_shooting_phase"
    selected_unit_ids = _selected_target_unit_ids_or_none(context)
    if selected_unit_ids is None:
        return "missing_selected_target_context"
    if not selected_unit_ids:
        return "no_selected_target_units"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) not in selected_unit_ids:
        return "unit_not_selected_as_target"
    return None


def _selected_target_unit_ids_or_none(
    context: StratagemEligibilityContext,
) -> tuple[str, ...] | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_ids = trigger_payload.get(SELECTED_TARGET_UNIT_CONTEXT_KEY)
    if not isinstance(raw_unit_ids, list):
        return None
    unit_ids: list[str] = []
    seen: set[str] = set()
    for raw_unit_id in raw_unit_ids:
        if type(raw_unit_id) is not str:
            return None
        unit_id = _validate_identifier("Selected target unit id", raw_unit_id)
        if unit_id in seen:
            return None
        seen.add(unit_id)
        unit_ids.append(unit_id)
    return tuple(sorted(unit_ids))


def _fire_overwatch_target_binding_error(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> str | None:
    triggering_unit_id = _fire_overwatch_triggering_enemy_unit_id_or_none(context)
    if triggering_unit_id is None:
        return "missing_fire_overwatch_trigger_unit"
    triggering_owner = _unit_owner(state=state, unit_instance_id=triggering_unit_id)
    if triggering_owner is None:
        return "unknown_fire_overwatch_trigger_unit"
    if triggering_owner == player_id:
        return "fire_overwatch_trigger_unit_not_enemy"
    if state.battlefield_state is None:
        return "fire_overwatch_requires_battlefield"
    shooting_unit_id = _require_target_unit_id(target_binding)
    if not _units_are_within_range_inches(
        state=state,
        first_unit_instance_id=shooting_unit_id,
        second_unit_instance_id=triggering_unit_id,
        distance_inches=FIRE_OVERWATCH_MAX_RANGE_INCHES,
    ):
        return "fire_overwatch_unit_not_within_24"
    if ruleset_descriptor is None or army_catalog is None:
        return "fire_overwatch_requires_shooting_rules_context"
    shooting_unit = _unit_by_id(state=state, unit_instance_id=shooting_unit_id)
    if _unit_has_keyword(shooting_unit, "TITANIC"):
        return "fire_overwatch_unit_titanic"
    if _unit_is_within_enemy_engagement_range(
        state=state,
        player_id=player_id,
        unit_instance_id=shooting_unit_id,
    ):
        return "fire_overwatch_unit_engaged"
    if not shooting_unit_can_select_to_shoot(
        state=state,
        unit=shooting_unit,
        army_catalog=army_catalog,
        player_id=player_id,
    ):
        return "fire_overwatch_unit_ineligible_to_shoot"
    if not shooting_unit_has_legal_declaration_against_targets(
        state=state,
        unit=shooting_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=player_id,
        target_unit_ids=(triggering_unit_id,),
    ):
        return "fire_overwatch_no_legal_shooting_declaration"
    return None


def _fire_overwatch_triggering_enemy_unit_id(
    context: StratagemEligibilityContext,
) -> str:
    unit_id = _fire_overwatch_triggering_enemy_unit_id_or_none(context)
    if unit_id is None:
        raise GameLifecycleError("Fire Overwatch trigger payload requires moved unit id.")
    return unit_id


def _fire_overwatch_triggering_enemy_unit_id_or_none(
    context: StratagemEligibilityContext,
) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    unit_id = trigger_payload.get(FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY)
    if type(unit_id) is not str:
        return None
    return _validate_identifier("Fire Overwatch moved unit id", unit_id)


def _heroic_intervention_target_binding_error(
    *,
    state: GameState,
    player_id: str,
    target_binding: StratagemTargetBinding,
) -> str | None:
    target_unit_id = _require_target_unit_id(target_binding)
    target_unit = _unit_by_id(state=state, unit_instance_id=target_unit_id)
    if _unit_has_keyword(target_unit, "VEHICLE") and not (
        _unit_has_keyword(target_unit, "CHARACTER") or _unit_has_keyword(target_unit, "WALKER")
    ):
        return "heroic_intervention_vehicle_not_character_or_walker"
    if _unit_is_within_enemy_engagement_range(
        state=state,
        player_id=player_id,
        unit_instance_id=target_unit_id,
    ):
        return "heroic_intervention_unit_engaged"
    if not _friendly_unit_within_enemy_range(
        state=state,
        player_id=player_id,
        unit_instance_id=target_unit_id,
        distance_inches=HEROIC_INTERVENTION_TARGET_RANGE_INCHES,
    ):
        return "heroic_intervention_unit_not_within_12"
    return None


def _crushing_impact_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
) -> str | None:
    source_unit_id = _require_target_unit_id(target_binding)
    enemy_unit_id = _crushing_impact_enemy_target_id_or_none(effect_selection)
    if enemy_unit_id is None:
        return "missing_crushing_impact_enemy_target"
    enemy_owner = _unit_owner(state=state, unit_instance_id=enemy_unit_id)
    if enemy_owner is None:
        return "unknown_crushing_impact_enemy_target"
    if enemy_owner == context.player_id:
        return "crushing_impact_target_not_enemy"
    model_id = _crushing_impact_model_id_or_none(effect_selection)
    if model_id is None:
        return "missing_crushing_impact_model"
    if model_id not in _unit_by_id(state=state, unit_instance_id=source_unit_id).own_model_ids():
        return "crushing_impact_model_not_in_unit"
    if not _model_is_alive_and_placed(state=state, model_instance_id=model_id):
        return "crushing_impact_model_not_alive_and_placed"
    if not _units_are_engaged(
        state=state,
        first_unit_instance_id=source_unit_id,
        second_unit_instance_id=enemy_unit_id,
    ):
        return "crushing_impact_units_not_engaged"
    if not _model_engaged_with_unit(
        state=state,
        model_instance_id=model_id,
        target_unit_instance_id=enemy_unit_id,
    ):
        return "crushing_impact_model_not_engaged_with_target"
    if _model_toughness(state=state, model_instance_id=model_id) is None:
        return "crushing_impact_model_missing_toughness"
    return None


def _counteroffensive_target_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    ruleset_descriptor: RulesetDescriptor | None,
) -> str | None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return "counteroffensive_requires_fight_phase_state"
    descriptor = (
        _stratagem_ruleset_descriptor() if ruleset_descriptor is None else ruleset_descriptor
    )
    target_unit_id = _require_target_unit_id(target_binding)
    contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=context.player_id,
        policy=descriptor.fight_policy,
    )
    for fight_context in contexts:
        if fight_context.unit_instance_id != target_unit_id:
            continue
        if legal_fight_types_for_context(
            context=fight_context,
            policy=descriptor.fight_policy,
        ):
            return None
        return "counteroffensive_target_has_no_legal_fight_type"
    return "counteroffensive_target_not_eligible_to_fight"


def _epic_challenge_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
) -> str | None:
    target_unit_id = _require_target_unit_id(target_binding)
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return "missing_epic_challenge_trigger_context"
    selected_unit_id = trigger_payload.get("selected_unit_instance_id")
    if selected_unit_id != target_unit_id:
        return "epic_challenge_unit_not_selected_to_fight"
    model_id = _epic_challenge_character_model_id_or_none(effect_selection)
    if model_id is None:
        return "missing_epic_challenge_character_model"
    unit = _unit_by_id(state=state, unit_instance_id=target_unit_id)
    if model_id not in unit.own_model_ids():
        return "epic_challenge_model_not_in_unit"
    if not _unit_has_keyword(unit, "CHARACTER"):
        return "epic_challenge_unit_not_character"
    if not _model_is_alive_and_placed(state=state, model_instance_id=model_id):
        return "epic_challenge_model_not_alive_and_placed"
    return None


def _units_are_within_range_inches(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
    distance_inches: float,
) -> bool:
    first_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    if not first_models or not second_models:
        return False
    for first_model in first_models:
        for second_model in second_models:
            if first_model.range_to(second_model) <= distance_inches:
                return True
    return False


def _friendly_unit_within_enemy_range(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    distance_inches: float,
) -> bool:
    for army in state.army_definitions:
        if army.player_id == player_id:
            continue
        for unit in army.units:
            if _units_are_within_range_inches(
                state=state,
                first_unit_instance_id=unit_instance_id,
                second_unit_instance_id=unit.unit_instance_id,
                distance_inches=distance_inches,
            ):
                return True
    return False


def _units_are_engaged(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> bool:
    return _any_models_within_engagement_range(
        first_models=_geometry_models_for_unit(
            state=state,
            unit_instance_id=first_unit_instance_id,
        ),
        second_models=_geometry_models_for_unit(
            state=state,
            unit_instance_id=second_unit_instance_id,
        ),
    )


def _model_engaged_with_unit(
    *,
    state: GameState,
    model_instance_id: str,
    target_unit_instance_id: str,
) -> bool:
    model = _geometry_model_for_model_id(state=state, model_instance_id=model_instance_id)
    return _any_models_within_engagement_range(
        first_models=(model,),
        second_models=_geometry_models_for_unit(
            state=state,
            unit_instance_id=target_unit_instance_id,
        ),
    )


def _geometry_model_for_model_id(*, state: GameState, model_instance_id: str) -> Model:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem model geometry requires battlefield_state.")
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    continue
                try:
                    return geometry_model_for_placement(
                        model=model,
                        placement=battlefield_state.model_placement_by_id(model.model_instance_id),
                    )
                except PlacementError as exc:
                    raise GameLifecycleError("Stratagem model placement is invalid.") from exc
    raise GameLifecycleError("model_instance_id is unknown.")


def _model_is_alive_and_placed(*, state: GameState, model_instance_id: str) -> bool:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem model placement requires battlefield_state.")
    placed_model_ids = set(battlefield_state.placed_model_ids())
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model.is_alive and requested_model_id in placed_model_ids
    raise GameLifecycleError("model_instance_id is unknown.")


def _model_toughness(*, state: GameState, model_instance_id: str) -> int | None:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    continue
                for value in model.characteristics:
                    if value.characteristic is Characteristic.TOUGHNESS:
                        return value.final
                return None
    raise GameLifecycleError("model_instance_id is unknown.")


def _crushing_impact_enemy_target_id_or_none(
    effect_selection: JsonValue,
) -> str | None:
    return _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY,
    )


def _crushing_impact_model_id_or_none(effect_selection: JsonValue) -> str | None:
    return _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=CRUSHING_IMPACT_MODEL_CONTEXT_KEY,
    )


def _epic_challenge_character_model_id_or_none(
    effect_selection: JsonValue,
) -> str | None:
    return _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY,
    )


def _explosives_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> str | None:
    if not _target_unit_has_keyword(state=state, target_binding=target_binding, keyword="GRENADES"):
        return "unit_not_grenades"
    explosives_unit_id = _require_target_unit_id(target_binding)
    if (
        state.advanced_unit_state_for_unit(
            player_id=context.player_id,
            battle_round=context.battle_round,
            unit_instance_id=explosives_unit_id,
        )
        is not None
    ):
        return "explosives_unit_advanced"
    if (
        state.fell_back_unit_state_for_unit(
            player_id=context.player_id,
            battle_round=context.battle_round,
            unit_instance_id=explosives_unit_id,
        )
        is not None
    ):
        return "explosives_unit_fell_back"
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and explosives_unit_id in shooting_state.shot_unit_ids:
        return "explosives_unit_already_shot"
    target_unit_id = _explosives_target_unit_id_or_none(context)
    if target_unit_id is None:
        return "missing_explosives_target"
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_id)
    if target_owner is None:
        return "unknown_explosives_target"
    if target_owner == context.player_id:
        return "explosives_target_not_enemy"
    if state.battlefield_state is None:
        return "explosives_requires_battlefield"
    if state.mission_setup is None:
        return "explosives_requires_mission_setup"
    if _unit_is_within_enemy_engagement_range(
        state=state,
        player_id=context.player_id,
        unit_instance_id=explosives_unit_id,
    ):
        return "explosives_unit_in_engagement_range"
    if _enemy_unit_is_within_friendly_engagement_range(
        state=state,
        player_id=context.player_id,
        target_unit_instance_id=target_unit_id,
    ):
        return "explosives_target_engaged_with_friendly_unit"
    if not _explosives_target_is_visible_and_in_range(
        state=state,
        explosives_unit_instance_id=explosives_unit_id,
        target_unit_instance_id=target_unit_id,
    ):
        return "explosives_target_not_visible_and_within_range"
    return None


def _explosives_target_unit_id(context: StratagemEligibilityContext) -> str:
    target_unit_id = _explosives_target_unit_id_or_none(context)
    if target_unit_id is None:
        raise GameLifecycleError("Explosives trigger payload requires enemy target unit id.")
    return target_unit_id


def _explosives_target_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    target_unit_id = trigger_payload.get(EXPLOSIVES_TARGET_CONTEXT_KEY)
    if type(target_unit_id) is not str:
        return None
    return _validate_identifier("Explosives target unit id", target_unit_id)


def _explosives_target_is_visible_and_in_range(
    *,
    state: GameState,
    explosives_unit_instance_id: str,
    target_unit_instance_id: str,
) -> bool:
    scenario = _battlefield_scenario_for_stratagem(state)
    unit = _unit_by_id(state=state, unit_instance_id=explosives_unit_instance_id)
    terrain_features = _stratagem_terrain_features(state)
    profile = _explosives_visibility_profile()
    for model in unit.own_models:
        if not model.is_alive:
            continue
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=_stratagem_ruleset_descriptor(),
            attacker_unit=unit,
            attacker_model_instance_id=model.model_instance_id,
            weapon_profile=profile,
            target_unit_id=target_unit_instance_id,
            terrain_features=terrain_features,
        )
        if candidate.is_legal:
            return True
    return False


def _unit_is_within_enemy_engagement_range(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    unit_models = _geometry_models_for_unit(state=state, unit_instance_id=unit_instance_id)
    for army in state.army_definitions:
        if army.player_id == player_id:
            continue
        for unit in army.units:
            if _any_models_within_engagement_range(
                first_models=unit_models,
                second_models=_geometry_models_for_unit(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                ),
            ):
                return True
    return False


def _enemy_unit_is_within_friendly_engagement_range(
    *,
    state: GameState,
    player_id: str,
    target_unit_instance_id: str,
) -> bool:
    target_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    for army in state.army_definitions:
        if army.player_id != player_id:
            continue
        for unit in army.units:
            if _any_models_within_engagement_range(
                first_models=_geometry_models_for_unit(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                ),
                second_models=target_models,
            ):
                return True
    return False


def _any_models_within_engagement_range(
    *,
    first_models: tuple[Model, ...],
    second_models: tuple[Model, ...],
) -> bool:
    policy = _stratagem_ruleset_descriptor().engagement_policy
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(
                second_model,
                horizontal_inches=policy.horizontal_inches,
                vertical_inches=policy.vertical_inches,
            ):
                return True
    return False


def _geometry_models_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[Model, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem geometry requires battlefield_state.")
    unit = _unit_by_id(state=state, unit_instance_id=unit_instance_id)
    try:
        models = tuple(
            geometry_model_for_placement(
                model=model,
                placement=battlefield_state.model_placement_by_id(model.model_instance_id),
            )
            for model in unit.own_models
            if model.is_alive
        )
    except PlacementError as exc:
        raise GameLifecycleError("Stratagem geometry placement is invalid.") from exc
    return models


def _battlefield_scenario_for_stratagem(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem battlefield scenario requires battlefield_state.")
    try:
        return BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Stratagem battlefield scenario is invalid.") from exc


def _stratagem_terrain_features(state: GameState) -> tuple[TerrainFeatureDefinition, ...]:
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Stratagem terrain requires mission_setup.")
    return mission_setup.terrain_features


def _stratagem_ruleset_descriptor() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh()


def _explosives_visibility_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="core-stratagem:explosives:visibility-range",
        name="Explosives Stratagem Visibility Range",
        range_profile=RangeProfile.distance(8),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
    )


def _unit_owner(*, state: GameState, unit_instance_id: str) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id
    return None


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("unit_instance_id is unknown.")


def _unit_by_id_or_none(*, state: GameState, unit_instance_id: str) -> UnitInstance | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    return None


def _reserve_state_for_target(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
) -> ReserveState:
    reserve_state = state.reserve_state_for_unit(_require_target_unit_id(target_binding))
    if reserve_state is None:
        raise GameLifecycleError("Stratagem reserve target requires ReserveState.")
    if reserve_state.status is not ReserveStatus.IN_RESERVES:
        raise GameLifecycleError("Stratagem reserve target must be unarrived.")
    return reserve_state


def _unit_for_reserve_state(*, state: GameState, reserve_state: ReserveState) -> UnitInstance:
    army = state.army_definition_for_player(reserve_state.player_id)
    if army is None:
        raise GameLifecycleError("ReserveState player has no army definition.")
    for unit in army.units:
        if unit.unit_instance_id == reserve_state.unit_instance_id:
            return unit
    raise GameLifecycleError("ReserveState references an unknown unit.")


def _reserve_placement_kinds_for_unit(
    *,
    reserve_state: ReserveState,
    unit: UnitInstance,
) -> tuple[BattlefieldPlacementKind, ...]:
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        kinds = [BattlefieldPlacementKind.STRATEGIC_RESERVES]
        if _unit_has_deep_strike_keyword(unit):
            kinds.append(BattlefieldPlacementKind.DEEP_STRIKE)
        return tuple(kinds)
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return (BattlefieldPlacementKind.DEEP_STRIKE,)
    return (BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,)


def _reserve_proposal_kind(reserve_state: ReserveState) -> ProposalKind:
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return ProposalKind.DEEP_STRIKE
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        return ProposalKind.STRATEGIC_RESERVES
    return ProposalKind.REINFORCEMENT


def _unit_has_deep_strike_keyword(unit: UnitInstance) -> bool:
    return any(
        keyword.replace("-", " ").replace("_", " ").upper() == "DEEP STRIKE"
        for keyword in unit.keywords
    )


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem placement requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )


def _proposal_from_request_payload(payload: JsonValue) -> StratagemTargetProposal | None:
    if not isinstance(payload, dict):
        return None
    proposal_payload = payload.get("proposal_request")
    if not isinstance(proposal_payload, dict):
        return None
    try:
        proposal = StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, proposal_payload)
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None
    if proposal.target_binding is not None:
        return None
    return proposal


def _proposal_from_result_payload(payload: JsonValue) -> StratagemTargetProposal | None:
    if not isinstance(payload, dict):
        return None
    proposal_payload = payload.get("proposal")
    if not isinstance(proposal_payload, dict):
        return None
    try:
        return StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, proposal_payload)
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _proposal_context_error(
    *,
    state: GameState,
    request_proposal: StratagemTargetProposal,
    submitted_proposal: StratagemTargetProposal,
) -> str | None:
    if submitted_proposal.proposal_kind != request_proposal.proposal_kind:
        return "wrong_context"
    if submitted_proposal.game_id != request_proposal.game_id:
        return "wrong_context"
    if submitted_proposal.player_id != request_proposal.player_id:
        return "wrong_context"
    if submitted_proposal.stratagem_id != request_proposal.stratagem_id:
        return "wrong_context"
    if submitted_proposal.catalog_record != request_proposal.catalog_record:
        return "wrong_context"
    if submitted_proposal.battle_round != request_proposal.battle_round:
        return "stale_battle_round"
    if submitted_proposal.phase is not request_proposal.phase:
        return "stale_phase"
    return _context_state_drift(state=state, context=request_proposal.context)


def _movement_proposal_request_from_payload(payload: JsonValue) -> MovementProposalRequest | None:
    try:
        return MovementProposalRequest.from_decision_request_payload(payload)
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _heroic_intervention_charge_move_from_result_payload(
    payload: JsonValue,
) -> ChargeMoveProposal | None:
    if not isinstance(payload, dict):
        return None
    try:
        return ChargeMoveProposal.from_payload(cast(ChargeMoveProposalPayload, payload))
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _heroic_intervention_charge_move_request_error(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    proposal: ChargeMoveProposal,
) -> str | None:
    use_record = _stratagem_use_from_proposal_context(proposal_request)
    if use_record.player_id != proposal_request.actor_id:
        return "heroic_intervention_actor_drift"
    if use_record.stratagem_id != "heroic-intervention":
        return "heroic_intervention_use_drift"
    maximum_distance = _heroic_intervention_maximum_distance(proposal_request)
    mode = _heroic_intervention_mode_from_request(proposal_request)
    current_reachable = _heroic_intervention_reachable_target_distances(
        state=state,
        player_id=use_record.player_id,
        heroic_unit_id=proposal.unit_instance_id,
        mode=mode,
        maximum_distance_inches=maximum_distance,
    )
    requested_reachable = _heroic_intervention_requested_reachable_distances(proposal_request)
    if current_reachable != requested_reachable:
        return "heroic_intervention_reachable_targets_drift"
    if proposal.is_no_move_choice:
        return None
    if proposal.witness is None:
        return "heroic_intervention_witness_required"
    if not set(proposal.charge_target_unit_instance_ids).issubset(set(current_reachable)):
        return "heroic_intervention_target_not_reachable"
    return None


def _heroic_intervention_maximum_distance(proposal_request: MovementProposalRequest) -> int:
    context = _heroic_intervention_request_context(proposal_request)
    value = context.get("maximum_distance_inches")
    if type(value) is not int:
        raise GameLifecycleError("Heroic Intervention request requires maximum distance.")
    if value < 2 or value > 12:
        raise GameLifecycleError("Heroic Intervention maximum distance is invalid.")
    return value


def _heroic_intervention_mode_from_request(proposal_request: MovementProposalRequest) -> str:
    context = _heroic_intervention_request_context(proposal_request)
    value = context.get("mode")
    if type(value) is not str:
        raise GameLifecycleError("Heroic Intervention request requires mode.")
    return _validate_identifier("Heroic Intervention mode", value)


def _heroic_intervention_requested_reachable_distances(
    proposal_request: MovementProposalRequest,
) -> dict[str, float]:
    context = _heroic_intervention_request_context(proposal_request)
    value = context.get("reachable_target_distances_inches")
    if not isinstance(value, dict):
        raise GameLifecycleError("Heroic Intervention request requires reachable target map.")
    distances: dict[str, float] = {}
    for unit_id, distance in value.items():
        if type(unit_id) is not str:
            raise GameLifecycleError("Heroic Intervention reachable target map is malformed.")
        if type(distance) is int:
            distance_value = float(distance)
        elif type(distance) is float:
            distance_value = distance
        else:
            raise GameLifecycleError("Heroic Intervention reachable target map is malformed.")
        distances[_validate_identifier("Heroic Intervention target id", unit_id)] = float(
            distance_value
        )
    return dict(sorted(distances.items()))


def _heroic_intervention_request_context(
    proposal_request: MovementProposalRequest,
) -> dict[str, JsonValue]:
    context = proposal_request.context
    if context is None:
        raise GameLifecycleError("Heroic Intervention request requires context.")
    return context


def _placement_proposal_from_result_payload(payload: JsonValue) -> PlacementProposalPayload | None:
    if not isinstance(payload, dict):
        return None
    try:
        return PlacementProposalPayload.from_payload(cast(PlacementProposalPayloadPayload, payload))
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _proposal_request_is_rapid_ingress(proposal_request: MovementProposalRequest) -> bool:
    context = proposal_request.context or {}
    handler = context.get("stratagem_handler_id")
    return handler == CORE_RAPID_INGRESS_HANDLER_ID


def _apply_rapid_ingress_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    reserve_state = state.reserve_state_for_unit(submitted.unit_instance_id)
    if reserve_state is None:
        raise GameLifecycleError("Rapid Ingress placement requires ReserveState.")
    if reserve_state.status is not ReserveStatus.IN_RESERVES:
        raise GameLifecycleError("Rapid Ingress placement requires an unarrived ReserveState.")
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Rapid Ingress placement requires MissionSetup.")
    placement = resolve_reserve_arrival(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        reserve_state=reserve_state,
        attempted_placement=submitted.attempted_placement,
        battle_round=state.battle_round,
        placement_kind=submitted.placement_kind,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
        objective_markers=tuple(
            marker.to_objective_marker() for marker in mission_setup.objective_markers
        ),
        enemy_deployment_zones=mission_setup.enemy_deployment_zones_for_player(
            reserve_state.player_id
        ),
        large_model_exceptions=submitted.large_model_exceptions,
    )
    if not placement.is_valid:
        invalid_payload = {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": reserve_state.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": proposal_request.proposal_kind.value,
            "placement_kind": submitted.placement_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "rapid_ingress_placement_invalid",
            "violations": [violation.to_payload() for violation in placement.violations],
            "coherency_result": placement.coherency_result.to_payload(),
        }
        decisions.event_log.append(
            "rapid_ingress_placement_invalid",
            validate_json_value(invalid_payload),
        )
        retry_request = _request_rapid_ingress_placement_retry(
            state=state,
            decisions=decisions,
            proposal_request=proposal_request,
            rejected_result=result,
        )
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Rapid Ingress placement is invalid.",
            payload=validate_json_value(
                {**invalid_payload, "next_request_id": retry_request.request_id}
            ),
        )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Rapid Ingress placement requires battlefield_state.")
    state.replace_battlefield_state(
        apply_reinforcement_placement_to_battlefield(
            battlefield_state=battlefield_state,
            placement=placement,
        )
    )
    arrived_state = placement.arrived_reserve_state()
    state.replace_reserve_state(arrived_state)
    stratagem_use = _stratagem_use_from_proposal_context(proposal_request)
    event_payload = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "player_id": arrived_state.player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "step": "rapid_ingress",
        "unit_instance_id": arrived_state.unit_instance_id,
        "placement_kind": placement.candidate.placement_kind.value,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "phase_body_status": "rapid_ingress_unit_arrived",
        "transition_batch": validate_json_value(placement.transition_batch.to_payload())
        if placement.transition_batch is not None
        else None,
        "large_model_exception_used": placement.large_model_exception_used,
        "post_arrival_restrictions": [
            restriction.value for restriction in placement.post_arrival_restrictions
        ],
        "stratagem_use": stratagem_use.to_payload(),
    }
    decisions.event_log.append("reinforcement_unit_arrived", validate_json_value(event_payload))
    decisions.event_log.append("rapid_ingress_resolved", validate_json_value(event_payload))
    return None


def _request_rapid_ingress_placement_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
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
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": retry_proposal.actor_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": retry_proposal.unit_instance_id,
            "proposal_kind": retry_proposal.proposal_kind.value,
            "placement_kinds": [kind.value for kind in retry_proposal.placement_kinds],
            "request_id": request.request_id,
            "source_decision_request_id": retry_proposal.source_decision_request_id,
            "source_decision_result_id": retry_proposal.source_decision_result_id,
            "previous_proposal_request_id": proposal_request.request_id,
            "rejected_result_id": rejected_result.result_id,
            "phase_body_status": "rapid_ingress_placement_proposal_required",
        },
    )
    return request


def _stratagem_use_from_proposal_context(
    proposal_request: MovementProposalRequest,
) -> StratagemUseRecord:
    context = proposal_request.context or {}
    use_payload = context.get("stratagem_use")
    if not isinstance(use_payload, dict):
        raise GameLifecycleError("Rapid Ingress placement context requires stratagem_use.")
    return StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, use_payload))


def _apply_supported_stratagem_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
) -> None:
    if definition.handler_id == "record_only":
        return
    if stratagem_handler_registry is not None:
        from warhammer40k_core.engine.faction_content.stratagem_handlers import (
            StratagemHandlerContext,
            StratagemHandlerExecutionStatus,
            StratagemHandlerRegistry,
        )

        if type(stratagem_handler_registry) is not StratagemHandlerRegistry:
            raise GameLifecycleError("Stratagem handler registry is invalid.")
        if stratagem_handler_registry.has_handler(definition.handler_id):
            handler_result = stratagem_handler_registry.execute(
                handler_id=definition.handler_id,
                context=StratagemHandlerContext(
                    state=state,
                    decisions=decisions,
                    result=result,
                    eligibility_context=context,
                    definition=definition,
                    target_binding=target_binding,
                    use_record=use_record,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                ),
            )
            if handler_result.status is not StratagemHandlerExecutionStatus.APPLIED:
                if handler_result.reason is None:
                    raise GameLifecycleError("Stratagem handler failed without reason.")
                raise GameLifecycleError(f"Stratagem handler failed: {handler_result.reason}.")
            decisions.event_log.append("stratagem_handler_applied", handler_result.to_payload())
            return
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        _apply_command_reroll_handler(
            state=state,
            decisions=decisions,
            context=context,
            definition=definition,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_INSANE_BRAVERY_HANDLER_ID:
        _apply_insane_bravery_handler(
            state=state,
            decisions=decisions,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_RAPID_INGRESS_HANDLER_ID:
        _apply_rapid_ingress_handler(
            state=state,
            decisions=decisions,
            result=result,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_NEW_ORDERS_HANDLER_ID:
        _apply_new_orders_handler(
            state=state,
            decisions=decisions,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_FIRE_OVERWATCH_HANDLER_ID:
        _apply_fire_overwatch_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
        return
    if definition.handler_id == CORE_GO_TO_GROUND_HANDLER_ID:
        _apply_go_to_ground_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_EXPLOSIVES_HANDLER_ID:
        _apply_explosives_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_SMOKESCREEN_HANDLER_ID:
        _apply_smokescreen_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_COUNTEROFFENSIVE_HANDLER_ID:
        _apply_counteroffensive_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
        )
        return
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID:
        _apply_crushing_impact_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_EPIC_CHALLENGE_HANDLER_ID:
        _apply_epic_challenge_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_HEROIC_INTERVENTION_HANDLER_ID:
        _apply_heroic_intervention_handler(
            state=state,
            decisions=decisions,
            result=result,
            context=context,
            definition=definition,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        _apply_generic_rule_ir_stratagem_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            definition=definition,
            use_record=use_record,
        )
        return
    raise GameLifecycleError("Stratagem handler is not supported.")


def _validate_supported_stratagem_handler_available(
    *,
    definition: StratagemDefinition,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
) -> None:
    if definition.handler_id == "record_only":
        return
    if stratagem_handler_registry is not None:
        from warhammer40k_core.engine.faction_content.stratagem_handlers import (
            StratagemHandlerRegistry,
        )

        if type(stratagem_handler_registry) is not StratagemHandlerRegistry:
            raise GameLifecycleError("Stratagem handler registry is invalid.")
        if stratagem_handler_registry.has_handler(definition.handler_id):
            return
    if definition.handler_id in {
        CORE_COMMAND_REROLL_HANDLER_ID,
        CORE_INSANE_BRAVERY_HANDLER_ID,
        CORE_RAPID_INGRESS_HANDLER_ID,
        CORE_NEW_ORDERS_HANDLER_ID,
        CORE_FIRE_OVERWATCH_HANDLER_ID,
        CORE_GO_TO_GROUND_HANDLER_ID,
        CORE_EXPLOSIVES_HANDLER_ID,
        CORE_SMOKESCREEN_HANDLER_ID,
        CORE_COUNTEROFFENSIVE_HANDLER_ID,
        CORE_CRUSHING_IMPACT_HANDLER_ID,
        CORE_EPIC_CHALLENGE_HANDLER_ID,
        CORE_HEROIC_INTERVENTION_HANDLER_ID,
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    }:
        return
    raise GameLifecycleError("Stratagem handler is not supported.")


def _generic_rule_ir_from_stratagem_payload(effect_payload: JsonValue) -> object:
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    return rule_ir_from_execution_payload(effect_payload)


def _apply_generic_rule_ir_stratagem_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
) -> None:
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionContext,
        RuleExecutionStatus,
        execute_rule_ir,
        rule_ir_from_execution_payload,
    )

    rule_ir = rule_ir_from_execution_payload(definition.effect_payload)
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
            timing_window_id=context.timing_window_id,
            target_unit_instance_ids=use_record.targeted_unit_instance_ids,
            target_player_id=target_binding.target_player_id,
            trigger_payload={
                "stratagem_id": definition.stratagem_id,
                "stratagem_use_id": use_record.use_id,
                "effect_selection": use_record.effect_selection,
            },
            state=state,
            event_log=decisions.event_log,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        if result.reason is None:
            raise GameLifecycleError("Generic Stratagem rule execution failed without reason.")
        raise GameLifecycleError(f"Generic Stratagem rule execution failed: {result.reason}.")


def _apply_command_reroll_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
) -> None:
    roll_state = _command_reroll_state(context)
    if roll_state.original_result.spec.actor_id != context.player_id:
        raise GameLifecycleError("Command Re-roll roll actor was not prevalidated.")
    roll_type = roll_state.original_result.spec.roll_type
    if _command_reroll_roll_class(roll_type) not in definition.eligible_roll_types:
        raise GameLifecycleError("Command Re-roll roll type was not prevalidated.")
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        raise GameLifecycleError("Command Re-roll forbidden roll was not prevalidated.")
    permission = _command_reroll_permission(
        source_id=use_record.source_id,
        context=context,
        roll_state=roll_state,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=f"{use_record.use_id}:command-reroll-request",
        actor_id=context.player_id,
        permission=permission,
        extra_payload={
            "command_reroll_context": validate_json_value(
                {
                    "stratagem_use": use_record.to_payload(),
                    "stratagem_context": context.to_payload(),
                    "roll_state": roll_state.to_payload(),
                }
            ),
        },
    )
    reroll_option_ids = tuple(
        option.option_id for option in request.options if option.option_id != "decline"
    )
    if len(reroll_option_ids) > 1:
        decisions.request_decision(request)
        decisions.event_log.append(
            "command_reroll_selection_requested",
            {
                "game_id": state.game_id,
                "player_id": context.player_id,
                "battle_round": context.battle_round,
                "phase": context.phase.value,
                "stratagem_use": use_record.to_payload(),
                "reroll_request": request.to_payload(),
            },
        )
        return
    if len(reroll_option_ids) != 1:
        raise GameLifecycleError("Command Re-roll must resolve exactly one reroll option.")
    reroll_result = DecisionResult.for_request(
        result_id=f"{use_record.use_id}:command-reroll-result",
        request=request,
        selected_option_id=reroll_option_ids[0],
    )
    updated_state = manager.resolve_reroll(
        roll_state,
        request=request,
        result=reroll_result,
        record_decision=False,
    )
    decisions.event_log.append(
        "command_reroll_resolved",
        {
            "game_id": state.game_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": context.phase.value,
            "stratagem_use": use_record.to_payload(),
            "reroll_request": request.to_payload(),
            "reroll_result": reroll_result.to_payload(),
            "updated_roll_state": updated_state.to_payload(),
        },
    )


def is_command_reroll_decision_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Command Re-roll request check requires a DecisionRequest.")
    if request.decision_type != DICE_REROLL_DECISION_TYPE:
        return False
    payload = request.payload
    return isinstance(payload, dict) and isinstance(payload.get("command_reroll_context"), dict)


def invalid_command_reroll_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if not is_command_reroll_decision_request(request):
        return _invalid(state, "Command Re-roll decision is malformed.", "malformed_request")
    try:
        result.validate_for_request(request)
        context, _use_record, _roll_state = _command_reroll_request_context(request)
    except (DecisionError, GameLifecycleError, KeyError):  # fmt: skip
        return _invalid(state, "Command Re-roll decision context is invalid.", "malformed")
    drift = _context_state_drift(state=state, context=context)
    if drift is not None:
        return _invalid(state, "Command Re-roll decision context drifted.", drift)
    return None


def apply_command_reroll_decision(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    context, use_record, roll_state = _command_reroll_request_context(request)
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    updated_state = manager.resolve_reroll(
        roll_state,
        request=request,
        result=result,
        record_decision=False,
    )
    decisions.event_log.append(
        "command_reroll_resolved",
        {
            "game_id": state.game_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": context.phase.value,
            "stratagem_use": use_record.to_payload(),
            "reroll_request": request.to_payload(),
            "reroll_result": result.to_payload(),
            "updated_roll_state": updated_state.to_payload(),
        },
    )


def _command_reroll_request_context(
    request: DecisionRequest,
) -> tuple[StratagemEligibilityContext, StratagemUseRecord, DiceRollState]:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Command Re-roll decision payload must be an object.")
    context_payload = payload.get("command_reroll_context")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Command Re-roll decision payload missing context.")
    stratagem_context_payload = context_payload.get("stratagem_context")
    use_record_payload = context_payload.get("stratagem_use")
    roll_state_payload = context_payload.get("roll_state")
    if not isinstance(stratagem_context_payload, dict):
        raise GameLifecycleError("Command Re-roll stratagem context is invalid.")
    if not isinstance(use_record_payload, dict):
        raise GameLifecycleError("Command Re-roll stratagem use is invalid.")
    if not isinstance(roll_state_payload, dict):
        raise GameLifecycleError("Command Re-roll roll state is invalid.")
    return (
        StratagemEligibilityContext.from_payload(
            cast(StratagemEligibilityContextPayload, stratagem_context_payload)
        ),
        StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, use_record_payload)),
        DiceRollState.from_payload(cast(DiceRollStatePayload, roll_state_payload)),
    )


def _apply_insane_bravery_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:insane-bravery-auto-pass",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=use_record.player_id,
        ),
        effect_payload={
            "effect_kind": "battle_shock_auto_pass",
            "stratagem_use_id": use_record.use_id,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "insane_bravery_auto_pass_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_rapid_ingress_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    reserve_state = _reserve_state_for_target(state=state, target_binding=target_binding)
    unit = _unit_for_reserve_state(state=state, reserve_state=reserve_state)
    placement_kinds = _reserve_placement_kinds_for_unit(reserve_state=reserve_state, unit=unit)
    proposal_kind = _reserve_proposal_kind(reserve_state)
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=context.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=reserve_state.unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        placement_kinds=placement_kinds,
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": CORE_RAPID_INGRESS_HANDLER_ID,
                    "stratagem_use": validate_json_value(use_record.to_payload()),
                    "reserve_state": validate_json_value(reserve_state.to_payload()),
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": context.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": proposal_kind.value,
            "placement_kinds": [kind.value for kind in placement_kinds],
            "request_id": request.request_id,
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "stratagem_use_id": use_record.use_id,
            "phase_body_status": "rapid_ingress_placement_proposal_required",
        },
    )


def _apply_new_orders_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    secondary_mission_id = _target_secondary_mission_id(target_binding)
    discarded = state.discard_tactical_secondary(
        player_id=use_record.player_id,
        secondary_mission_id=secondary_mission_id,
        result_id=f"{use_record.result_id}:new-orders-discard",
    )
    drawn = state.draw_tactical_secondary_cards(
        player_id=use_record.player_id,
        source_result_id=f"{use_record.result_id}:new-orders-draw",
        draw_count=1,
    )
    decisions.event_log.append(
        "tactical_secondary_mission_discarded",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "secondary_mission_card_state": validate_json_value(discarded.to_payload()),
            "source_stratagem_use_id": use_record.use_id,
        },
    )
    decisions.event_log.append(
        "tactical_secondary_missions_drawn",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "draw_count": 1,
            "phase": use_record.phase.value,
            "secondary_mission_card_states": [
                validate_json_value(card_state.to_payload()) for card_state in drawn
            ],
            "source_stratagem_use_id": use_record.use_id,
        },
    )
    decisions.event_log.append(
        "new_orders_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "discarded_secondary_mission_id": secondary_mission_id,
            "drawn_secondary_mission_ids": [
                card_state.secondary_mission_id for card_state in drawn
            ],
        },
    )


def _apply_fire_overwatch_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> None:
    if context.trigger_kind is not TimingTriggerKind.END_PHASE:
        raise GameLifecycleError("Fire Overwatch requires the end of opponent Movement phase.")
    if context.phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("Fire Overwatch requires the Movement phase.")
    shooting_unit_id = _require_target_unit_id(target_binding)
    triggering_unit_id = _fire_overwatch_triggering_enemy_unit_id(context)
    request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=use_record.player_id,
        unit_instance_id=shooting_unit_id,
        parent_phase=context.phase,
        source_rule_id=CORE_FIRE_OVERWATCH_HANDLER_ID,
        source_decision_request_id=use_record.request_id,
        source_decision_result_id=use_record.result_id,
        source_context=validate_json_value(
            {
                "source_kind": "fire_overwatch",
                "triggering_enemy_unit_instance_id": triggering_unit_id,
                "stratagem_use": use_record.to_payload(),
                "trigger_kind": context.trigger_kind.value,
                "trigger_payload": context.trigger_payload,
            }
        ),
        target_unit_ids=(triggering_unit_id,),
    )
    decisions.event_log.append(
        "fire_overwatch_shooting_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "shooting_unit_instance_id": shooting_unit_id,
        },
    )


def _apply_go_to_ground_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:go-to-ground",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": GO_TO_GROUND_EFFECT_KIND,
            "stratagem_use_id": use_record.use_id,
            "benefit_of_cover": True,
            "invulnerable_save": GO_TO_GROUND_INVULNERABLE_SAVE,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "go_to_ground_effect_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_smokescreen_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:smokescreen",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": SMOKESCREEN_EFFECT_KIND,
            "stratagem_use_id": use_record.use_id,
            "benefit_of_cover": True,
            "hit_roll_modifier": SMOKESCREEN_HIT_ROLL_MODIFIER,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "smokescreen_effect_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_explosives_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _explosives_target_unit_id(context)
    context_error = _explosives_context_error(
        state=state,
        context=context,
        target_binding=target_binding,
    )
    if context_error is not None:
        raise GameLifecycleError("Prevalidated Explosives context failed.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=6, sides=6),
            reason=f"Explosives mortal wounds for {use_record.use_id}",
            roll_type="stratagem.explosives",
            actor_id=use_record.player_id,
        )
    )
    mortal_wounds = sum(1 for value in roll_state.current_values if value >= 4)
    mortal_application = None
    if mortal_wounds > 0:
        progress = MortalWoundApplicationProgress.start(
            application_id=f"{use_record.use_id}:explosives:mortal-wounds",
            source_rule_id=CORE_EXPLOSIVES_HANDLER_ID,
            source_context=validate_json_value(
                {
                    "source_kind": "explosives",
                    "stratagem_use": use_record.to_payload(),
                    "explosives_unit_instance_id": _require_target_unit_id(target_binding),
                    "target_unit_instance_id": target_unit_id,
                    "roll_state": roll_state.to_payload(),
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
            return
        if routed.application is None:
            raise GameLifecycleError("Explosives mortal wounds did not produce application.")
        mortal_application = routed.application
    _emit_explosives_resolved(
        decisions=decisions,
        state=state,
        use_record=use_record,
        explosives_unit_instance_id=_require_target_unit_id(target_binding),
        target_unit_instance_id=target_unit_id,
        roll_state=validate_json_value(roll_state.to_payload()),
        mortal_wounds=mortal_wounds,
        mortal_application=mortal_application,
    )


def apply_explosives_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError("Explosives Feel No Pain requires mortal wound context.")
    source_context = mortal_wound_feel_no_pain_source_context(request)
    if not isinstance(source_context, dict) or source_context.get("source_kind") != "explosives":
        raise GameLifecycleError("Explosives Feel No Pain source context is invalid.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=routed.request,
            payload={
                "phase": state.current_battle_phase.value
                if state.current_battle_phase is not None
                else None,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": CORE_EXPLOSIVES_HANDLER_ID,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Explosives Feel No Pain did not finish routing.")
    use_record = StratagemUseRecord.from_payload(
        cast(StratagemUseRecordPayload, source_context["stratagem_use"])
    )
    roll_state_payload = source_context["roll_state"]
    if not isinstance(roll_state_payload, dict):
        raise GameLifecycleError("Explosives source context roll_state is invalid.")
    _emit_explosives_resolved(
        decisions=decisions,
        state=state,
        use_record=use_record,
        explosives_unit_instance_id=_validate_identifier(
            "explosives_unit_instance_id",
            source_context["explosives_unit_instance_id"],
        ),
        target_unit_instance_id=routed.progress.target_unit_instance_id,
        roll_state=validate_json_value(roll_state_payload),
        mortal_wounds=routed.progress.mortal_wounds,
        mortal_application=routed.application,
    )
    return None


def _emit_explosives_resolved(
    *,
    decisions: DecisionController,
    state: GameState,
    use_record: StratagemUseRecord,
    explosives_unit_instance_id: str,
    target_unit_instance_id: str,
    roll_state: JsonValue,
    mortal_wounds: int,
    mortal_application: MortalWoundApplication | None,
) -> None:
    decisions.event_log.append(
        "explosives_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "explosives_unit_instance_id": explosives_unit_instance_id,
            "target_unit_instance_id": target_unit_instance_id,
            "roll_state": roll_state,
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": (
                None if mortal_application is None else mortal_application.to_payload()
            ),
        },
    )


def _apply_counteroffensive_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Counteroffensive requires fight_phase_state.")
    contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=use_record.player_id,
        policy=ruleset_descriptor.fight_policy,
    )
    fight_context = next(
        (candidate for candidate in contexts if candidate.unit_instance_id == target_unit_id),
        None,
    )
    if fight_context is None:
        raise GameLifecycleError("Counteroffensive target was not prevalidated.")
    fight_types = legal_fight_types_for_context(
        context=fight_context,
        policy=ruleset_descriptor.fight_policy,
    )
    if not fight_types:
        raise GameLifecycleError("Counteroffensive target has no legal fight type.")
    interrupt_id = f"counteroffensive:{use_record.use_id}"
    selection = FightActivationSelection(
        player_id=use_record.player_id,
        battle_round=use_record.battle_round,
        unit_instance_id=target_unit_id,
        ordering_band=fight_context.ordering_band,
        fight_type=fight_types[0],
        eligibility_reasons=fight_context.eligibility_reasons,
        request_id=use_record.request_id,
        result_id=use_record.result_id,
        interrupt_id=interrupt_id,
    )
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:counteroffensive:fights-first",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": FIGHTS_FIRST_EFFECT_KIND,
            "source_rule_id": use_record.source_id,
            "stratagem_use_id": use_record.use_id,
        },
    )
    state.record_persisting_effect(effect)
    state.fight_phase_state = fight_state.with_activation(selection).with_active_activation(
        selection
    )
    decisions.event_log.append(
        "counteroffensive_activation_selected",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
            "activation_selection": selection.to_payload(),
        },
    )


def _apply_crushing_impact_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    context_error = _crushing_impact_context_error(
        state=state,
        context=context,
        target_binding=target_binding,
        effect_selection=use_record.effect_selection,
    )
    if context_error is not None:
        raise GameLifecycleError("Prevalidated Crushing Impact context failed.")
    source_unit_id = _require_target_unit_id(target_binding)
    enemy_unit_id = _crushing_impact_enemy_target_id_or_none(use_record.effect_selection)
    model_id = _crushing_impact_model_id_or_none(use_record.effect_selection)
    if enemy_unit_id is None or model_id is None:
        raise GameLifecycleError("Crushing Impact selection was not prevalidated.")
    toughness = _model_toughness(state=state, model_instance_id=model_id)
    if toughness is None:
        raise GameLifecycleError("Crushing Impact model Toughness was not prevalidated.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=toughness, sides=6),
            reason=f"Crushing Impact mortal wounds for {use_record.use_id}",
            roll_type="stratagem.crushing_impact",
            actor_id=use_record.player_id,
        )
    )
    source_mortal_wounds = sum(1 for value in roll_state.current_values if value == 1)
    enemy_mortal_wounds = min(
        CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT,
        sum(1 for value in roll_state.current_values if value >= 5),
    )
    source_application = _apply_stratagem_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        use_record=use_record,
        application_id=f"{use_record.use_id}:crushing-impact:self",
        target_unit_instance_id=source_unit_id,
        mortal_wounds=source_mortal_wounds,
        source_context=validate_json_value(
            {
                "source_kind": "crushing_impact_self",
                "stratagem_use": use_record.to_payload(),
                "roll_state": roll_state.to_payload(),
            }
        ),
    )
    if decisions.queue.pending_requests:
        return
    enemy_application = _apply_stratagem_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        use_record=use_record,
        application_id=f"{use_record.use_id}:crushing-impact:enemy",
        target_unit_instance_id=enemy_unit_id,
        mortal_wounds=enemy_mortal_wounds,
        source_context=validate_json_value(
            {
                "source_kind": "crushing_impact_enemy",
                "stratagem_use": use_record.to_payload(),
                "roll_state": roll_state.to_payload(),
            }
        ),
    )
    decisions.event_log.append(
        "crushing_impact_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "source_unit_instance_id": source_unit_id,
            "source_model_instance_id": model_id,
            "target_unit_instance_id": enemy_unit_id,
            "roll_state": roll_state.to_payload(),
            "source_mortal_wounds": source_mortal_wounds,
            "enemy_mortal_wounds": enemy_mortal_wounds,
            "source_mortal_wound_application": (
                None if source_application is None else source_application.to_payload()
            ),
            "enemy_mortal_wound_application": (
                None if enemy_application is None else enemy_application.to_payload()
            ),
        },
    )


def _apply_epic_challenge_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    context_error = _epic_challenge_context_error(
        state=state,
        context=context,
        target_binding=target_binding,
        effect_selection=use_record.effect_selection,
    )
    if context_error is not None:
        raise GameLifecycleError("Prevalidated Epic Challenge context failed.")
    target_unit_id = _require_target_unit_id(target_binding)
    model_id = _epic_challenge_character_model_id_or_none(use_record.effect_selection)
    if model_id is None:
        raise GameLifecycleError("Epic Challenge model was not prevalidated.")
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:epic-challenge:precision",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": "epic_challenge_precision",
            "source_rule_id": use_record.source_id,
            "stratagem_use_id": use_record.use_id,
            "model_instance_id": model_id,
            "weapon_keyword": "Precision",
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "epic_challenge_precision_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_heroic_intervention_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    mode = _heroic_intervention_mode(
        definition=definition,
        effect_selection=use_record.effect_selection,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Heroic Intervention charge roll for {use_record.use_id}",
            roll_type="charge_roll",
            actor_id=use_record.player_id,
            reroll_forbidden_rule_ids=(CORE_COMMAND_REROLL_HANDLER_ID,),
        )
    )
    maximum_distance = roll_state.current_total
    if mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY and maximum_distance > 6:
        maximum_distance = 6
    reachable = _heroic_intervention_reachable_target_distances(
        state=state,
        player_id=use_record.player_id,
        heroic_unit_id=target_unit_id,
        mode=mode,
        maximum_distance_inches=maximum_distance,
    )
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=context.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=target_unit_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": CORE_HEROIC_INTERVENTION_HANDLER_ID,
                    "stratagem_use": use_record.to_payload(),
                    "mode": mode,
                    "movement_mode": MovementMode.CHARGE.value,
                    "charge_roll_state": roll_state.to_payload(),
                    "maximum_distance_inches": maximum_distance,
                    "reachable_target_unit_instance_ids": list(reachable),
                    "reachable_target_distances_inches": reachable,
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "heroic_intervention_charge_move_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "mode": mode,
            "charge_roll_state": roll_state.to_payload(),
            "maximum_distance_inches": maximum_distance,
            "reachable_target_unit_instance_ids": list(reachable),
            "reachable_target_distances_inches": reachable,
            "request_id": request.request_id,
        },
    )


def _apply_stratagem_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    use_record: StratagemUseRecord,
    application_id: str,
    target_unit_instance_id: str,
    mortal_wounds: int,
    source_context: JsonValue,
) -> MortalWoundApplication | None:
    if mortal_wounds <= 0:
        return None
    progress = MortalWoundApplicationProgress.start(
        application_id=application_id,
        source_rule_id=use_record.handler_id,
        source_context=validate_json_value(source_context),
        target_unit_instance_id=target_unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=target_unit_instance_id,
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
        return None
    if routed.application is None:
        raise GameLifecycleError("Stratagem mortal wounds did not produce application.")
    return routed.application


def _heroic_intervention_reachable_target_distances(
    *,
    state: GameState,
    player_id: str,
    heroic_unit_id: str,
    mode: str,
    maximum_distance_inches: int,
) -> dict[str, float]:
    distances: dict[str, float] = {}
    for enemy_unit_id in _enemy_unit_ids_for_player(state=state, player_id=player_id):
        distance = _closest_unit_distance_inches(
            state=state,
            first_unit_instance_id=heroic_unit_id,
            second_unit_instance_id=enemy_unit_id,
        )
        if distance > float(maximum_distance_inches):
            continue
        if (
            mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
            and distance > HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES
        ):
            continue
        if mode == HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND and not _unit_made_charge_move(
            state=state,
            unit_instance_id=enemy_unit_id,
        ):
            continue
        distances[enemy_unit_id] = distance
    return dict(sorted(distances.items()))


def _enemy_unit_ids_for_player(*, state: GameState, player_id: str) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    ids: list[str] = []
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            continue
        ids.extend(unit.unit_instance_id for unit in army.units)
    return tuple(sorted(ids))


def _closest_unit_distance_inches(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> float:
    first_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    if not first_models or not second_models:
        raise GameLifecycleError("Stratagem unit distance requires placed models.")
    return min(
        first_model.range_to(second_model)
        for first_model in first_models
        for second_model in second_models
    )


def _unit_made_charge_move(*, state: GameState, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") == "charge_grants_fights_first":
            return True
    return False


def _apply_command_point_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    source_id: str,
    effect_payload: JsonValue,
) -> None:
    if not isinstance(effect_payload, dict):
        return
    gain_payload = effect_payload.get("command_point_gain")
    if isinstance(gain_payload, dict):
        amount = gain_payload.get("amount")
        cap_exempt = gain_payload.get("cap_exempt", False)
        if type(amount) is not int:
            raise GameLifecycleError("command_point_gain amount must be an integer.")
        if type(cap_exempt) is not bool:
            raise GameLifecycleError("command_point_gain cap_exempt must be a bool.")
        gain = state.gain_command_points(
            player_id=player_id,
            amount=amount,
            source_id=f"{source_id}:cp-gain",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=cap_exempt,
        )
        event_type = (
            "command_points_gained"
            if gain.status is CommandPointGainStatus.APPLIED
            else "command_points_gain_capped"
        )
        decisions.event_log.append(event_type, gain.to_payload())
    refund_payload = effect_payload.get("command_point_refund")
    if isinstance(refund_payload, dict):
        amount = refund_payload.get("amount")
        cap_exempt = refund_payload.get("cap_exempt", False)
        if type(amount) is not int:
            raise GameLifecycleError("command_point_refund amount must be an integer.")
        if type(cap_exempt) is not bool:
            raise GameLifecycleError("command_point_refund cap_exempt must be a bool.")
        refund = state.refund_command_points(
            player_id=player_id,
            amount=amount,
            source_id=f"{source_id}:cp-refund",
            cap_exempt=cap_exempt,
        )
        event_type = (
            "command_points_refunded"
            if refund.status is CommandPointRefundStatus.APPLIED
            else "command_points_refund_capped"
        )
        decisions.event_log.append(event_type, refund.to_payload())


def _stratagem_handler_is_unsupported(definition: StratagemDefinition) -> bool:
    if type(definition) is not StratagemDefinition:
        raise GameLifecycleError("Stratagem handler support check requires a definition.")
    return definition.handler_id.startswith(UNSUPPORTED_STRATAGEM_HANDLER_PREFIX)


def _next_stratagem_use_id(*, state: GameState, player_id: str) -> str:
    return (
        f"stratagem-use:{player_id}:round-{state.battle_round:02d}:"
        f"{len(state.stratagem_use_records) + 1:06d}"
    )


def _target_binding_token(binding: StratagemTargetBinding) -> str:
    if binding.target_kind is StratagemTargetKind.NONE:
        return "none"
    if binding.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        return _target_secondary_mission_id(binding)
    return _require_target_unit_id(binding)


def _require_target_unit_id(binding: StratagemTargetBinding) -> str:
    if binding.target_unit_instance_id is None:
        raise GameLifecycleError("Stratagem target binding requires a unit id.")
    return binding.target_unit_instance_id


def _target_secondary_mission_id(binding: StratagemTargetBinding) -> str:
    if binding.target_secondary_mission_id is None:
        raise GameLifecycleError("Stratagem target binding requires a secondary mission id.")
    return binding.target_secondary_mission_id


def _validate_catalog_records(
    values: object,
) -> tuple[StratagemCatalogRecord, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Stratagem catalog records must be a tuple.")
    validated: list[StratagemCatalogRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not StratagemCatalogRecord:
            raise GameLifecycleError(
                "Stratagem catalog records must contain StratagemCatalogRecord values."
            )
        if value.record_id in seen:
            raise GameLifecycleError("Stratagem catalog records must not contain duplicate IDs.")
        seen.add(value.record_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda record: record.record_id))


def _require_decline_event_fields(payload: Mapping[str, JsonValue]) -> None:
    for field_name in (
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "active_player_id",
        "trigger_kind",
        "timing_window_id",
        "request_id",
        "result_id",
        "decision_type",
    ):
        if field_name not in payload:
            raise GameLifecycleError("Stratagem decline event payload is malformed.")


def _invalid(state: GameState, message: str, reason: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload={"invalid_reason": reason},
    )


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


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )


def _validate_stratagem_affected_unit_ids(values: object) -> tuple[str, ...]:
    affected_unit_ids = _validate_identifier_tuple(
        "StratagemUseRecord affected_unit_instance_ids",
        values,
    )
    if len(set(affected_unit_ids)) != len(affected_unit_ids):
        raise GameLifecycleError("StratagemUseRecord affected_unit_instance_ids must be unique.")
    return tuple(sorted(affected_unit_ids))


def _validate_optional_phase(field_name: str, value: object | None) -> BattlePhaseKind | None:
    if value is None:
        return None
    return battle_phase_kind_from_token(value)


def _validate_target_policy_id(
    *,
    target_kind: StratagemTargetKind,
    target_policy_id: object | None,
) -> str:
    if target_policy_id is None or target_policy_id == "":
        if target_kind is StratagemTargetKind.NONE:
            return "none"
        if target_kind is StratagemTargetKind.FRIENDLY_UNIT:
            return "friendly_unit"
        if target_kind is StratagemTargetKind.ANY_UNIT:
            return "any_unit"
        if target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
            return NEW_ORDERS_TARGET_POLICY_ID
        raise GameLifecycleError("StratagemTargetSpec target_kind is unsupported.")
    policy_id = _validate_identifier("StratagemTargetSpec target_policy_id", target_policy_id)
    if target_kind is StratagemTargetKind.NONE and policy_id != "none":
        raise GameLifecycleError("Targetless StratagemTargetSpec requires none target_policy_id.")
    if target_kind is not StratagemTargetKind.NONE and policy_id == "none":
        raise GameLifecycleError("Targeted StratagemTargetSpec cannot use none target_policy_id.")
    return policy_id


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


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
