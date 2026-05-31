from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.battle_shock import friendly_stratagem_target_permission
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointRefundStatus,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    timing_trigger_kind_from_token,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


STRATAGEM_DECISION_TYPE = "use_stratagem"
STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE = "submit_stratagem_target_proposal"
STRATAGEM_PROPOSAL_PAYLOAD_KIND = "stratagem_target_binding"


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


class StratagemTargetBindingPayload(TypedDict):
    target_kind: str
    target_player_id: str | None
    target_unit_instance_id: str | None


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
class StratagemEligibilityContext:
    game_id: str
    player_id: str
    battle_round: int
    phase: BattlePhaseKind
    active_player_id: str | None
    trigger_kind: TimingTriggerKind
    timing_window_id: str | None = None

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

    @classmethod
    def from_state(
        cls,
        *,
        state: GameState,
        player_id: str,
        trigger_kind: TimingTriggerKind,
        timing_window_id: str | None = None,
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
        )

    def to_payload(self) -> StratagemEligibilityContextPayload:
        return {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "active_player_id": self.active_player_id,
            "trigger_kind": self.trigger_kind.value,
            "timing_window_id": self.timing_window_id,
        }

    @classmethod
    def from_payload(cls, payload: StratagemEligibilityContextPayload) -> Self:
        return cls(
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=battle_phase_kind_from_token(payload["phase"]),
            active_player_id=payload["active_player_id"],
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            timing_window_id=payload["timing_window_id"],
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetBinding:
    target_kind: StratagemTargetKind
    target_player_id: str | None = None
    target_unit_instance_id: str | None = None

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
        if self.target_kind is StratagemTargetKind.NONE:
            if self.target_player_id is not None or self.target_unit_instance_id is not None:
                raise GameLifecycleError("Targetless StratagemTargetBinding cannot name a unit.")
            return
        if self.target_player_id is None or self.target_unit_instance_id is None:
            raise GameLifecycleError("Unit StratagemTargetBinding requires target unit fields.")

    @classmethod
    def none(cls) -> Self:
        return cls(target_kind=StratagemTargetKind.NONE)

    def to_payload(self) -> StratagemTargetBindingPayload:
        return {
            "target_kind": self.target_kind.value,
            "target_player_id": self.target_player_id,
            "target_unit_instance_id": self.target_unit_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTargetBindingPayload) -> Self:
        return cls(
            target_kind=stratagem_target_kind_from_token(payload["target_kind"]),
            target_player_id=payload["target_player_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
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
    options = stratagem_use_options(
        state=state,
        catalog_records=catalog_records,
        context=context,
    )
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


def stratagem_use_options(
    *,
    state: GameState,
    catalog_records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
) -> tuple[DecisionOption, ...]:
    records = _validate_catalog_records(catalog_records)
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
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem proposal requires a DecisionController.")
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
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
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.player_id,
        payload=validate_json_value({"proposal_request": proposal_request.to_payload()}),
        options=(parameterized_decision_option(),),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"pending_request_id": request.request_id},
    )


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
    except KeyError, GameLifecycleError:
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
    if not record.definition.timing.matches(context):
        return "timing_window_mismatch"
    if state.command_point_total(context.player_id) < record.definition.command_point_cost:
        return "insufficient_command_points"
    if not _detachment_gate_allows(state=state, record=record, player_id=context.player_id):
        return "detachment_gate_closed"
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
            selection.detachment_id == record.detachment_id
            and record.definition.stratagem_id in selection.stratagem_ids
        )
    return False


def _restriction_violation(
    *,
    state: GameState,
    player_id: str,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
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
    except KeyError, GameLifecycleError:
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
    except KeyError, GameLifecycleError:
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


def _next_stratagem_use_id(*, state: GameState, player_id: str) -> str:
    return (
        f"stratagem-use:{player_id}:round-{state.battle_round:02d}:"
        f"{len(state.stratagem_use_records) + 1:06d}"
    )


def _target_binding_token(binding: StratagemTargetBinding) -> str:
    if binding.target_kind is StratagemTargetKind.NONE:
        return "none"
    return _require_target_unit_id(binding)


def _require_target_unit_id(binding: StratagemTargetBinding) -> str:
    if binding.target_unit_instance_id is None:
        raise GameLifecycleError("Stratagem target binding requires a unit id.")
    return binding.target_unit_instance_id


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
