from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceRollSpecError,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.battle_shock import (
    collect_battle_shock_test_requests,
    friendly_stratagem_target_permission,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointRefundStatus,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.decision import DiceRollManager
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
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
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
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    timing_trigger_kind_from_token,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
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
COMMAND_REROLL_DICE_CONTEXT_KEY = "dice_roll_state"
INSANE_BRAVERY_TARGET_POLICY_ID = "battle_shock_test_unit"
RAPID_INGRESS_TARGET_POLICY_ID = "reserves_unit"
NEW_ORDERS_TARGET_POLICY_ID = "active_tactical_secondary_card"


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
    timing_window_id: str | None
    request_id: str
    result_id: str
    selected_option_id: str
    target_binding: StratagemTargetBindingPayload
    command_point_cost: int
    command_point_transaction_id: str | None
    handler_id: str
    effect_payload: JsonValue


class StratagemTimingDescriptorPayload(TypedDict):
    trigger_kind: str
    phase: str | None
    timing_window_id: str | None


class StratagemRestrictionPolicyPayload(TypedDict):
    same_stratagem_per_phase: bool
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
    proposal_kind: str
    context: StratagemEligibilityContextPayload
    catalog_record: StratagemCatalogRecordPayload
    target_binding: StratagemTargetBindingPayload | None


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
            "once_per_turn": self.once_per_turn,
            "once_per_battle": self.once_per_battle,
            "once_per_target_per_phase": self.once_per_target_per_phase,
            "allow_battle_shocked_targets": self.allow_battle_shocked_targets,
        }

    @classmethod
    def from_payload(cls, payload: StratagemRestrictionPolicyPayload) -> Self:
        return cls(
            same_stratagem_per_phase=payload["same_stratagem_per_phase"],
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

    def with_binding(self, binding: StratagemTargetBinding) -> Self:
        return type(self)(
            proposal_kind=self.proposal_kind,
            context=self.context,
            catalog_record=self.catalog_record,
            target_binding=binding,
        )

    def to_payload(self) -> StratagemTargetProposalPayload:
        return {
            "proposal_kind": self.proposal_kind,
            "context": self.context.to_payload(),
            "catalog_record": self.catalog_record.to_payload(),
            "target_binding": (
                None if self.target_binding is None else self.target_binding.to_payload()
            ),
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
    timing_window_id: str | None
    request_id: str
    result_id: str
    selected_option_id: str
    target_binding: StratagemTargetBinding
    command_point_cost: int
    command_point_transaction_id: str | None
    handler_id: str
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
        object.__setattr__(self, "effect_payload", validate_json_value(self.effect_payload))

    def to_payload(self) -> StratagemUseRecordPayload:
        return {
            "use_id": self.use_id,
            "player_id": self.player_id,
            "stratagem_id": self.stratagem_id,
            "source_id": self.source_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "timing_window_id": self.timing_window_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "selected_option_id": self.selected_option_id,
            "target_binding": self.target_binding.to_payload(),
            "command_point_cost": self.command_point_cost,
            "command_point_transaction_id": self.command_point_transaction_id,
            "handler_id": self.handler_id,
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
            timing_window_id=payload["timing_window_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            selected_option_id=payload["selected_option_id"],
            target_binding=StratagemTargetBinding.from_payload(payload["target_binding"]),
            command_point_cost=payload["command_point_cost"],
            command_point_transaction_id=payload["command_point_transaction_id"],
            handler_id=payload["handler_id"],
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
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.player_id,
        payload=stratagem_target_proposal_request_payload(
            proposal_request,
            allow_decline=allow_decline,
        ),
        options=(parameterized_decision_option(),),
    )


def stratagem_target_proposal_request_payload(
    proposal_request: StratagemTargetProposal,
    *,
    allow_decline: bool = False,
) -> JsonValue:
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    payload: dict[str, JsonValue] = {
        "proposal_request": validate_json_value(proposal_request.to_payload())
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
    )
    if violation is not None:
        return _invalid(state, "Stratagem decision is no longer legal.", violation)
    return None


def apply_stratagem_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> StratagemUseRecord:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem application requires a DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem application requires a DecisionController.")
    selection = _require_stratagem_selection(result.payload)
    context, catalog_record, target_binding = selection
    return _apply_stratagem_use(
        state=state,
        result=result,
        decisions=decisions,
        context=context,
        catalog_record=catalog_record,
        target_binding=target_binding,
    )


def _apply_stratagem_use(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    catalog_record: StratagemCatalogRecord,
    target_binding: StratagemTargetBinding,
) -> StratagemUseRecord:
    definition = catalog_record.definition
    if _stratagem_handler_is_unsupported(definition):
        raise GameLifecycleError("Unsupported stratagem handler cannot be applied.")
    use_id = _next_stratagem_use_id(state=state, player_id=context.player_id)
    spend_result: CommandPointSpendResult | None = None
    transaction_id: str | None = None
    if definition.command_point_cost > 0:
        spend_result = state.spend_command_points(
            player_id=context.player_id,
            amount=definition.command_point_cost,
            source_id=use_id,
        )
        if spend_result.status is not CommandPointSpendStatus.APPLIED:
            raise GameLifecycleError("Prevalidated stratagem spend failed.")
        if spend_result.transaction is None:
            raise GameLifecycleError("Applied stratagem spend is missing transaction.")
        transaction_id = spend_result.transaction.transaction_id
        decisions.event_log.append("command_points_spent", spend_result.to_payload())
    use_record = StratagemUseRecord(
        use_id=use_id,
        player_id=context.player_id,
        stratagem_id=definition.stratagem_id,
        source_id=definition.source_id,
        battle_round=context.battle_round,
        phase=context.phase,
        timing_window_id=context.timing_window_id,
        request_id=result.request_id,
        result_id=result.result_id,
        selected_option_id=result.selected_option_id,
        target_binding=target_binding,
        command_point_cost=definition.command_point_cost,
        command_point_transaction_id=transaction_id,
        handler_id=definition.handler_id,
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
    )
    return use_record


def invalid_stratagem_target_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
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
    )
    if violation is not None:
        return _invalid(state, "Stratagem target proposal is not legal.", violation)
    return None


def apply_stratagem_target_proposal(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
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
            }
        ),
    )


def _stratagem_selection_from_result_payload(
    payload: JsonValue,
) -> tuple[StratagemEligibilityContext, StratagemCatalogRecord, StratagemTargetBinding] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("submission_kind") != STRATAGEM_DECISION_TYPE:
        return None
    context_payload = payload.get("context")
    record_payload = payload.get("catalog_record")
    binding_payload = payload.get("target_binding")
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
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _require_stratagem_selection(
    payload: JsonValue,
) -> tuple[StratagemEligibilityContext, StratagemCatalogRecord, StratagemTargetBinding]:
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
    if state.command_point_total(context.player_id) < record.definition.command_point_cost:
        return "insufficient_command_points"
    if not _detachment_gate_allows(state=state, record=record, player_id=context.player_id):
        return "detachment_gate_closed"
    handler_reason = _handler_unavailable_reason(
        state=state,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
    )
    if handler_reason is not None:
        return handler_reason
    restriction = _restriction_violation(
        state=state,
        player_id=context.player_id,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
    )
    if restriction is not None:
        return restriction
    if target_binding is not None:
        target_error = _target_binding_error(
            state=state,
            player_id=context.player_id,
            target_spec=record.definition.target_spec,
            policy=record.definition.restriction_policy,
            target_binding=target_binding,
        )
        if target_error is not None:
            return target_error
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
            selection.detachment_id == record.detachment_id
            and record.definition.stratagem_id in selection.stratagem_ids
        )
    return False


def _handler_unavailable_reason(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        return _command_reroll_context_error(definition=definition, context=context)
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
        and use.battle_round == context.battle_round
        and use.phase is context.phase
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
            and use.battle_round == context.battle_round
            and use.phase is context.phase
            and use.target_binding.target_unit_instance_id == target_binding.target_unit_instance_id
            for use in previous_uses
        )
    ):
        return "once_per_target_per_phase"
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
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
) -> str | None:
    try:
        roll_state = _command_reroll_state(context)
        if roll_state.original_result.spec.actor_id != context.player_id:
            return "dice_roll_actor_drift"
        roll_type = roll_state.original_result.spec.roll_type
        if roll_type not in definition.eligible_roll_types:
            return "ineligible_dice_roll_type"
        permission = RerollPermission(
            source_id=CORE_COMMAND_REROLL_HANDLER_ID,
            timing_window=context.timing_window_id or context.trigger_kind.value,
            owning_player_id=context.player_id,
            eligible_roll_type=roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
        permission.legal_selections_for_state(roll_state)
    except (DiceRollSpecError, GameLifecycleError):  # fmt: skip
        return "invalid_dice_roll_context"
    return None


def _command_reroll_state(context: StratagemEligibilityContext) -> DiceRollState:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice roll trigger payload.")
    roll_payload = trigger_payload.get(COMMAND_REROLL_DICE_CONTEXT_KEY)
    if not isinstance(roll_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice_roll_state payload.")
    return DiceRollState.from_payload(cast(DiceRollStatePayload, roll_payload))


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
) -> None:
    if definition.handler_id == "record_only":
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
    raise GameLifecycleError("Stratagem handler is not supported.")


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
    if roll_type not in definition.eligible_roll_types:
        raise GameLifecycleError("Command Re-roll roll type was not prevalidated.")
    permission = RerollPermission(
        source_id=use_record.source_id,
        timing_window=context.timing_window_id or context.trigger_kind.value,
        owning_player_id=context.player_id,
        eligible_roll_type=roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=f"{use_record.use_id}:command-reroll-request",
        actor_id=context.player_id,
        permission=permission,
        extra_payload={
            "stratagem_use_id": use_record.use_id,
            "stratagem_source_id": use_record.source_id,
        },
    )
    reroll_option_ids = tuple(
        option.option_id for option in request.options if option.option_id != "decline"
    )
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
