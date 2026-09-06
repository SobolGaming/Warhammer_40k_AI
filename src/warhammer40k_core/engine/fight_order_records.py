from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    FightEligibilityKind,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightPolicyDescriptor,
    FightTypeKind,
    fight_eligibility_kind_from_token,
    fight_ordering_band_kind_from_token,
    fight_phase_step_kind_from_token,
    fight_type_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.fights_first import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND as CHARGE_FIGHTS_FIRST_EFFECT_KIND,
)
from warhammer40k_core.engine.fights_first import (
    FIGHTS_FIRST_EFFECT_KIND as FIGHTS_FIRST_EFFECT_KIND,
)
from warhammer40k_core.engine.fights_first import (
    FightsFirstRegistry as FightsFirstRegistry,
)
from warhammer40k_core.engine.fights_first import (
    FightsFirstRegistryPayload,
)
from warhammer40k_core.engine.fights_first import (
    FightsFirstSource as FightsFirstSource,
)
from warhammer40k_core.engine.forced_fight_context import (
    ForcedFightActivationContext as ForcedFightActivationContext,
)
from warhammer40k_core.engine.forced_fight_context import (
    ForcedFightActivationContextPayload as ForcedFightActivationContextPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError


class FightEligibilityContextPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    ordering_band: str
    eligibility_reasons: list[str]
    closest_enemy_distance_inches: float | None
    more_than_pass_distance_from_all_enemies: bool


class FightActivationSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    ordering_band: str
    fight_type: str
    eligibility_reasons: list[str]
    request_id: str
    result_id: str
    interrupt_id: str | None


class EligibleToFightPassPayload(TypedDict):
    player_id: str
    battle_round: int
    ordering_band: str
    request_id: str
    result_id: str
    pass_distance_inches: float
    eligible_unit_ids: list[str]


class FightInterruptRequestPayload(TypedDict):
    interrupt_id: str
    source_effect_id: str
    source_rule_id: str
    player_id: str
    battle_round: int
    ordering_band: str
    trigger_event_id: str
    eligible_unit_ids: list[str]


class ResolvedFightInterruptPayload(TypedDict):
    interrupt_id: str
    source_effect_id: str


class FightStepStatePayload(TypedDict):
    step: str
    status: str


class FightMovementStepStatePayload(TypedDict):
    step: str
    next_player_id: str
    completed_player_ids: list[str]
    completed_unit_ids: list[str]


class FightOrderStatePayload(TypedDict):
    ordering_bands: list[str]
    current_band_index: int
    next_player_id: str
    engaged_at_fight_step_start_unit_ids: list[str]
    selected_to_fight_unit_ids: list[str]
    passed_player_ids: list[str]
    remaining_combats_activation_since_band_entry: bool
    activation_selections: list[FightActivationSelectionPayload]
    eligible_passes: list[EligibleToFightPassPayload]
    resolved_interrupts: list[ResolvedFightInterruptPayload]
    fights_first_registry: FightsFirstRegistryPayload


@dataclass(frozen=True, slots=True)
class FightEligibilityContext:
    player_id: str
    battle_round: int
    unit_instance_id: str
    ordering_band: FightOrderingBandKind
    eligibility_reasons: tuple[FightEligibilityKind, ...]
    closest_enemy_distance_inches: float | None
    pass_distance_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FightEligibilityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            validate_positive_int("FightEligibilityContext battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "FightEligibilityContext unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "ordering_band",
            fight_ordering_band_kind_from_token(self.ordering_band),
        )
        object.__setattr__(
            self,
            "eligibility_reasons",
            _validate_fight_eligibility_reasons(self.eligibility_reasons),
        )
        object.__setattr__(
            self,
            "closest_enemy_distance_inches",
            _validate_optional_non_negative_float(
                "FightEligibilityContext closest_enemy_distance_inches",
                self.closest_enemy_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "pass_distance_inches",
            validate_positive_float(
                "FightEligibilityContext pass_distance_inches",
                self.pass_distance_inches,
            ),
        )

    @property
    def more_than_pass_distance_from_all_enemies(self) -> bool:
        if self.closest_enemy_distance_inches is None:
            return False
        return self.closest_enemy_distance_inches > self.pass_distance_inches

    def to_payload(self) -> FightEligibilityContextPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "ordering_band": self.ordering_band.value,
            "eligibility_reasons": [reason.value for reason in self.eligibility_reasons],
            "closest_enemy_distance_inches": self.closest_enemy_distance_inches,
            "more_than_pass_distance_from_all_enemies": (
                self.more_than_pass_distance_from_all_enemies
            ),
        }


@dataclass(frozen=True, slots=True)
class FightActivationSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    ordering_band: FightOrderingBandKind
    fight_type: FightTypeKind
    eligibility_reasons: tuple[FightEligibilityKind, ...]
    request_id: str
    result_id: str
    interrupt_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FightActivationSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            validate_positive_int("FightActivationSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "FightActivationSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "ordering_band",
            fight_ordering_band_kind_from_token(self.ordering_band),
        )
        object.__setattr__(self, "fight_type", fight_type_kind_from_token(self.fight_type))
        object.__setattr__(
            self,
            "eligibility_reasons",
            _validate_fight_eligibility_reasons(self.eligibility_reasons),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("FightActivationSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("FightActivationSelection result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "interrupt_id",
            _validate_optional_identifier(
                "FightActivationSelection interrupt_id",
                self.interrupt_id,
            ),
        )

    def to_payload(self) -> FightActivationSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "ordering_band": self.ordering_band.value,
            "fight_type": self.fight_type.value,
            "eligibility_reasons": [reason.value for reason in self.eligibility_reasons],
            "request_id": self.request_id,
            "result_id": self.result_id,
            "interrupt_id": self.interrupt_id,
        }

    @classmethod
    def from_payload(cls, payload: FightActivationSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            ordering_band=fight_ordering_band_kind_from_token(payload["ordering_band"]),
            fight_type=fight_type_kind_from_token(payload["fight_type"]),
            eligibility_reasons=tuple(
                fight_eligibility_kind_from_token(reason)
                for reason in payload["eligibility_reasons"]
            ),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            interrupt_id=payload["interrupt_id"],
        )


@dataclass(frozen=True, slots=True)
class EligibleToFightPass:
    player_id: str
    battle_round: int
    ordering_band: FightOrderingBandKind
    request_id: str
    result_id: str
    pass_distance_inches: float
    eligible_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("EligibleToFightPass player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            validate_positive_int("EligibleToFightPass battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "ordering_band",
            fight_ordering_band_kind_from_token(self.ordering_band),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("EligibleToFightPass request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("EligibleToFightPass result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "pass_distance_inches",
            validate_positive_float(
                "EligibleToFightPass pass_distance_inches",
                self.pass_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "eligible_unit_ids",
            validate_identifier_tuple(
                "EligibleToFightPass eligible_unit_ids",
                self.eligible_unit_ids,
            ),
        )

    def to_payload(self) -> EligibleToFightPassPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "ordering_band": self.ordering_band.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "pass_distance_inches": self.pass_distance_inches,
            "eligible_unit_ids": list(self.eligible_unit_ids),
        }

    @classmethod
    def from_payload(cls, payload: EligibleToFightPassPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            ordering_band=fight_ordering_band_kind_from_token(payload["ordering_band"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            pass_distance_inches=payload["pass_distance_inches"],
            eligible_unit_ids=tuple(payload["eligible_unit_ids"]),
        )


@dataclass(frozen=True, slots=True)
class FightInterruptRequest:
    interrupt_id: str
    source_effect_id: str
    source_rule_id: str
    player_id: str
    battle_round: int
    ordering_band: FightOrderingBandKind
    trigger_event_id: str
    eligible_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interrupt_id",
            _validate_identifier("FightInterruptRequest interrupt_id", self.interrupt_id),
        )
        object.__setattr__(
            self,
            "source_effect_id",
            _validate_identifier(
                "FightInterruptRequest source_effect_id",
                self.source_effect_id,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("FightInterruptRequest source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FightInterruptRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            validate_positive_int("FightInterruptRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "ordering_band",
            fight_ordering_band_kind_from_token(self.ordering_band),
        )
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("FightInterruptRequest trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "eligible_unit_ids",
            validate_identifier_tuple(
                "FightInterruptRequest eligible_unit_ids",
                self.eligible_unit_ids,
                min_length=1,
            ),
        )

    def to_payload(self) -> FightInterruptRequestPayload:
        return {
            "interrupt_id": self.interrupt_id,
            "source_effect_id": self.source_effect_id,
            "source_rule_id": self.source_rule_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "ordering_band": self.ordering_band.value,
            "trigger_event_id": self.trigger_event_id,
            "eligible_unit_ids": list(self.eligible_unit_ids),
        }

    @classmethod
    def from_payload(cls, payload: FightInterruptRequestPayload) -> Self:
        return cls(
            interrupt_id=payload["interrupt_id"],
            source_effect_id=payload["source_effect_id"],
            source_rule_id=payload["source_rule_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            ordering_band=fight_ordering_band_kind_from_token(payload["ordering_band"]),
            trigger_event_id=payload["trigger_event_id"],
            eligible_unit_ids=tuple(payload["eligible_unit_ids"]),
        )


@dataclass(frozen=True, slots=True)
class ResolvedFightInterrupt:
    interrupt_id: str
    source_effect_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interrupt_id",
            _validate_identifier("ResolvedFightInterrupt interrupt_id", self.interrupt_id),
        )
        object.__setattr__(
            self,
            "source_effect_id",
            _validate_identifier(
                "ResolvedFightInterrupt source_effect_id",
                self.source_effect_id,
            ),
        )

    def to_payload(self) -> ResolvedFightInterruptPayload:
        return {
            "interrupt_id": self.interrupt_id,
            "source_effect_id": self.source_effect_id,
        }

    @classmethod
    def from_payload(cls, payload: ResolvedFightInterruptPayload) -> Self:
        return cls(
            interrupt_id=payload["interrupt_id"],
            source_effect_id=payload["source_effect_id"],
        )


@dataclass(frozen=True, slots=True)
class FightStepState:
    step: FightPhaseStepKind
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "step", fight_phase_step_kind_from_token(self.step))
        object.__setattr__(
            self,
            "status",
            _validate_identifier("FightStepState status", self.status),
        )

    def to_payload(self) -> FightStepStatePayload:
        return {"step": self.step.value, "status": self.status}

    @classmethod
    def from_payload(cls, payload: FightStepStatePayload) -> Self:
        return cls(
            step=fight_phase_step_kind_from_token(payload["step"]),
            status=payload["status"],
        )


@dataclass(frozen=True, slots=True)
class FightMovementStepState:
    step: FightPhaseStepKind
    next_player_id: str
    completed_player_ids: tuple[str, ...] = ()
    completed_unit_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "step", _fight_movement_step_kind(self.step))
        object.__setattr__(
            self,
            "next_player_id",
            _validate_identifier("FightMovementStepState next_player_id", self.next_player_id),
        )
        completed_player_ids = validate_identifier_tuple(
            "FightMovementStepState completed_player_ids",
            self.completed_player_ids,
        )
        completed_unit_ids = validate_identifier_tuple(
            "FightMovementStepState completed_unit_ids",
            self.completed_unit_ids,
        )
        _validate_unique_unit_ids(completed_player_ids)
        _validate_unique_unit_ids(completed_unit_ids)
        object.__setattr__(self, "completed_player_ids", completed_player_ids)
        object.__setattr__(self, "completed_unit_ids", completed_unit_ids)

    @classmethod
    def start(cls, *, step: FightPhaseStepKind, next_player_id: str) -> Self:
        return cls(step=step, next_player_id=next_player_id)

    def with_completed_unit(self, *, unit_instance_id: str) -> Self:
        unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if unit_id in self.completed_unit_ids:
            raise GameLifecycleError("Fight movement unit has already completed this step.")
        return type(self)(
            step=self.step,
            next_player_id=self.next_player_id,
            completed_player_ids=self.completed_player_ids,
            completed_unit_ids=(*self.completed_unit_ids, unit_id),
        )

    def with_completed_player(self, *, next_player_id: str) -> Self:
        player_id = self.next_player_id
        if player_id in self.completed_player_ids:
            raise GameLifecycleError("Fight movement player has already completed this step.")
        return type(self)(
            step=self.step,
            next_player_id=next_player_id,
            completed_player_ids=(*self.completed_player_ids, player_id),
            completed_unit_ids=self.completed_unit_ids,
        )

    def to_payload(self) -> FightMovementStepStatePayload:
        return {
            "step": self.step.value,
            "next_player_id": self.next_player_id,
            "completed_player_ids": list(self.completed_player_ids),
            "completed_unit_ids": list(self.completed_unit_ids),
        }

    @classmethod
    def from_payload(cls, payload: FightMovementStepStatePayload) -> Self:
        return cls(
            step=fight_phase_step_kind_from_token(payload["step"]),
            next_player_id=payload["next_player_id"],
            completed_player_ids=tuple(payload["completed_player_ids"]),
            completed_unit_ids=tuple(payload["completed_unit_ids"]),
        )


@dataclass(frozen=True, slots=True)
class FightOrderState:
    ordering_bands: tuple[FightOrderingBandKind, ...]
    current_band_index: int
    next_player_id: str
    engaged_at_fight_step_start_unit_ids: tuple[str, ...]
    selected_to_fight_unit_ids: tuple[str, ...] = ()
    passed_player_ids: tuple[str, ...] = ()
    remaining_combats_activation_since_band_entry: bool = False
    activation_selections: tuple[FightActivationSelection, ...] = ()
    eligible_passes: tuple[EligibleToFightPass, ...] = ()
    resolved_interrupts: tuple[ResolvedFightInterrupt, ...] = ()
    fights_first_registry: FightsFirstRegistry = field(default_factory=FightsFirstRegistry)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ordering_bands",
            _validate_ordering_bands(self.ordering_bands),
        )
        object.__setattr__(
            self,
            "current_band_index",
            _validate_band_index(self.current_band_index, self.ordering_bands),
        )
        object.__setattr__(
            self,
            "next_player_id",
            _validate_identifier("FightOrderState next_player_id", self.next_player_id),
        )
        object.__setattr__(
            self,
            "engaged_at_fight_step_start_unit_ids",
            validate_identifier_tuple(
                "FightOrderState engaged_at_fight_step_start_unit_ids",
                self.engaged_at_fight_step_start_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "selected_to_fight_unit_ids",
            validate_identifier_tuple(
                "FightOrderState selected_to_fight_unit_ids",
                self.selected_to_fight_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "passed_player_ids",
            validate_identifier_tuple(
                "FightOrderState passed_player_ids",
                self.passed_player_ids,
            ),
        )
        if type(self.remaining_combats_activation_since_band_entry) is not bool:
            raise GameLifecycleError(
                "FightOrderState remaining_combats_activation_since_band_entry must be a bool."
            )
        object.__setattr__(
            self,
            "activation_selections",
            _validate_activation_selections(self.activation_selections),
        )
        object.__setattr__(
            self,
            "eligible_passes",
            _validate_eligible_passes(self.eligible_passes),
        )
        object.__setattr__(
            self,
            "resolved_interrupts",
            _validate_resolved_interrupts(self.resolved_interrupts),
        )
        if type(self.fights_first_registry) is not FightsFirstRegistry:
            raise GameLifecycleError(
                "FightOrderState fights_first_registry must be FightsFirstRegistry."
            )
        _validate_unique_unit_ids(self.selected_to_fight_unit_ids)
        _validate_unique_unit_ids(self.engaged_at_fight_step_start_unit_ids)
        _validate_unique_interrupt_ids(self.resolved_interrupt_ids)
        _validate_unique_interrupt_source_effect_ids(self.resolved_interrupt_source_effect_ids)

    @classmethod
    def start(
        cls,
        *,
        policy: FightPolicyDescriptor,
        next_player_id: str,
        engaged_at_fight_step_start_unit_ids: tuple[str, ...],
        fights_first_registry: FightsFirstRegistry,
    ) -> Self:
        if type(policy) is not FightPolicyDescriptor:
            raise GameLifecycleError("FightOrderState start requires a FightPolicyDescriptor.")
        return cls(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id=next_player_id,
            engaged_at_fight_step_start_unit_ids=engaged_at_fight_step_start_unit_ids,
            fights_first_registry=fights_first_registry,
        )

    @property
    def current_ordering_band(self) -> FightOrderingBandKind:
        return self.ordering_bands[self.current_band_index]

    @property
    def resolved_interrupt_ids(self) -> tuple[str, ...]:
        return tuple(interrupt.interrupt_id for interrupt in self.resolved_interrupts)

    @property
    def resolved_interrupt_source_effect_ids(self) -> tuple[str, ...]:
        return tuple(interrupt.source_effect_id for interrupt in self.resolved_interrupts)

    def with_next_player(self, player_id: str) -> Self:
        return type(self)(
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=_validate_identifier("player_id", player_id),
            engaged_at_fight_step_start_unit_ids=self.engaged_at_fight_step_start_unit_ids,
            selected_to_fight_unit_ids=self.selected_to_fight_unit_ids,
            passed_player_ids=self.passed_player_ids,
            remaining_combats_activation_since_band_entry=(
                self.remaining_combats_activation_since_band_entry
            ),
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupts=self.resolved_interrupts,
            fights_first_registry=self.fights_first_registry,
        )

    def with_next_band(self, *, next_player_id: str) -> Self:
        return self.with_ordering_band(
            current_band_index=self.current_band_index + 1,
            next_player_id=next_player_id,
        )

    def with_ordering_band(self, *, current_band_index: int, next_player_id: str) -> Self:
        return type(self)(
            ordering_bands=self.ordering_bands,
            current_band_index=_validate_band_index(current_band_index, self.ordering_bands),
            next_player_id=_validate_identifier("next_player_id", next_player_id),
            engaged_at_fight_step_start_unit_ids=self.engaged_at_fight_step_start_unit_ids,
            selected_to_fight_unit_ids=self.selected_to_fight_unit_ids,
            passed_player_ids=(),
            remaining_combats_activation_since_band_entry=False,
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupts=self.resolved_interrupts,
            fights_first_registry=self.fights_first_registry,
        )

    def with_activation(self, selection: FightActivationSelection) -> Self:
        if type(selection) is not FightActivationSelection:
            raise GameLifecycleError("Fight activation requires FightActivationSelection.")
        if selection.unit_instance_id in self.selected_to_fight_unit_ids:
            raise GameLifecycleError("Fight activation unit already activated.")
        return type(self)(
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            engaged_at_fight_step_start_unit_ids=self.engaged_at_fight_step_start_unit_ids,
            selected_to_fight_unit_ids=(
                *self.selected_to_fight_unit_ids,
                selection.unit_instance_id,
            ),
            passed_player_ids=tuple(
                player_id
                for player_id in self.passed_player_ids
                if player_id != selection.player_id
            ),
            remaining_combats_activation_since_band_entry=(
                self.remaining_combats_activation_since_band_entry
                or selection.ordering_band is FightOrderingBandKind.REMAINING_COMBATS
            ),
            activation_selections=(*self.activation_selections, selection),
            eligible_passes=self.eligible_passes,
            resolved_interrupts=self.resolved_interrupts,
            fights_first_registry=self.fights_first_registry,
        )

    def with_eligible_pass(self, eligible_pass: EligibleToFightPass) -> Self:
        if type(eligible_pass) is not EligibleToFightPass:
            raise GameLifecycleError("Fight pass requires EligibleToFightPass.")
        if eligible_pass.ordering_band is not self.current_ordering_band:
            raise GameLifecycleError("Fight pass ordering band drift.")
        return type(self)(
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            engaged_at_fight_step_start_unit_ids=self.engaged_at_fight_step_start_unit_ids,
            selected_to_fight_unit_ids=self.selected_to_fight_unit_ids,
            passed_player_ids=tuple(sorted({*self.passed_player_ids, eligible_pass.player_id})),
            remaining_combats_activation_since_band_entry=(
                self.remaining_combats_activation_since_band_entry
            ),
            activation_selections=self.activation_selections,
            eligible_passes=(*self.eligible_passes, eligible_pass),
            resolved_interrupts=self.resolved_interrupts,
            fights_first_registry=self.fights_first_registry,
        )

    def with_resolved_interrupt(self, *, interrupt_id: str, source_effect_id: str) -> Self:
        resolved_interrupt = ResolvedFightInterrupt(
            interrupt_id=interrupt_id,
            source_effect_id=source_effect_id,
        )
        if resolved_interrupt.interrupt_id in self.resolved_interrupt_ids:
            raise GameLifecycleError("Fight interrupt has already resolved.")
        if resolved_interrupt.source_effect_id in self.resolved_interrupt_source_effect_ids:
            raise GameLifecycleError("Fight interrupt source has already resolved.")
        return type(self)(
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            engaged_at_fight_step_start_unit_ids=self.engaged_at_fight_step_start_unit_ids,
            selected_to_fight_unit_ids=self.selected_to_fight_unit_ids,
            passed_player_ids=self.passed_player_ids,
            remaining_combats_activation_since_band_entry=(
                self.remaining_combats_activation_since_band_entry
            ),
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupts=(*self.resolved_interrupts, resolved_interrupt),
            fights_first_registry=self.fights_first_registry,
        )

    def to_payload(self) -> FightOrderStatePayload:
        return {
            "ordering_bands": [band.value for band in self.ordering_bands],
            "current_band_index": self.current_band_index,
            "next_player_id": self.next_player_id,
            "engaged_at_fight_step_start_unit_ids": list(self.engaged_at_fight_step_start_unit_ids),
            "selected_to_fight_unit_ids": list(self.selected_to_fight_unit_ids),
            "passed_player_ids": list(self.passed_player_ids),
            "remaining_combats_activation_since_band_entry": (
                self.remaining_combats_activation_since_band_entry
            ),
            "activation_selections": [
                selection.to_payload() for selection in self.activation_selections
            ],
            "eligible_passes": [
                eligible_pass.to_payload() for eligible_pass in self.eligible_passes
            ],
            "resolved_interrupts": [
                resolved_interrupt.to_payload() for resolved_interrupt in self.resolved_interrupts
            ],
            "fights_first_registry": self.fights_first_registry.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: FightOrderStatePayload) -> Self:
        return cls(
            ordering_bands=tuple(
                fight_ordering_band_kind_from_token(band) for band in payload["ordering_bands"]
            ),
            current_band_index=payload["current_band_index"],
            next_player_id=payload["next_player_id"],
            engaged_at_fight_step_start_unit_ids=tuple(
                payload["engaged_at_fight_step_start_unit_ids"]
            ),
            selected_to_fight_unit_ids=tuple(payload["selected_to_fight_unit_ids"]),
            passed_player_ids=tuple(payload["passed_player_ids"]),
            remaining_combats_activation_since_band_entry=payload[
                "remaining_combats_activation_since_band_entry"
            ],
            activation_selections=tuple(
                FightActivationSelection.from_payload(selection)
                for selection in payload["activation_selections"]
            ),
            eligible_passes=tuple(
                EligibleToFightPass.from_payload(eligible_pass)
                for eligible_pass in payload["eligible_passes"]
            ),
            resolved_interrupts=tuple(
                ResolvedFightInterrupt.from_payload(resolved_interrupt)
                for resolved_interrupt in payload["resolved_interrupts"]
            ),
            fights_first_registry=FightsFirstRegistry.from_payload(
                payload["fights_first_registry"]
            ),
        )


def step_states_for_current_step(
    *,
    steps: tuple[FightPhaseStepKind, ...],
    current_step: FightPhaseStepKind,
    phase_complete: bool,
) -> tuple[FightStepState, ...]:
    if not steps:
        raise GameLifecycleError("FightPolicyDescriptor steps must not be empty.")
    selected_step = fight_phase_step_kind_from_token(current_step)
    step_values = tuple(fight_phase_step_kind_from_token(step) for step in steps)
    if selected_step not in step_values:
        raise GameLifecycleError("FightPhaseState current_step is not in policy steps.")
    if phase_complete:
        return tuple(FightStepState(step=step, status="complete") for step in step_values)
    current_index = step_values.index(selected_step)
    states: list[FightStepState] = []
    for index, step in enumerate(step_values):
        if index < current_index:
            status = "complete"
        elif index == current_index:
            status = "active"
        else:
            status = "pending"
        states.append(FightStepState(step=step, status=status))
    return tuple(states)


def _fight_movement_step_kind(step: object) -> FightPhaseStepKind:
    step_kind = fight_phase_step_kind_from_token(step)
    if step_kind not in {FightPhaseStepKind.PILE_IN, FightPhaseStepKind.CONSOLIDATE}:
        raise GameLifecycleError("Fight movement step must be Pile In or Consolidate.")
    return step_kind


def validate_step_states(values: object) -> tuple[FightStepState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightPhaseState step_states must be a tuple.")
    states = tuple(_validate_step_state(value) for value in cast(tuple[object, ...], values))
    if not states:
        raise GameLifecycleError("FightPhaseState step_states must not be empty.")
    return states


def _validate_step_state(value: object) -> FightStepState:
    if type(value) is not FightStepState:
        raise GameLifecycleError("FightPhaseState step_states must contain FightStepState.")
    return value


def _validate_ordering_bands(values: object) -> tuple[FightOrderingBandKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightOrderState ordering_bands must be a tuple.")
    bands = tuple(
        fight_ordering_band_kind_from_token(value) for value in cast(tuple[object, ...], values)
    )
    if not bands:
        raise GameLifecycleError("FightOrderState ordering_bands must not be empty.")
    return bands


def _validate_band_index(index: object, bands: tuple[FightOrderingBandKind, ...]) -> int:
    if type(index) is not int:
        raise GameLifecycleError("FightOrderState current_band_index must be an int.")
    if index < 0 or index >= len(bands):
        raise GameLifecycleError("FightOrderState current_band_index is out of range.")
    return index


def _validate_activation_selections(values: object) -> tuple[FightActivationSelection, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightOrderState activation_selections must be a tuple.")
    return tuple(
        _validate_activation_selection(value) for value in cast(tuple[object, ...], values)
    )


def _validate_activation_selection(value: object) -> FightActivationSelection:
    if type(value) is not FightActivationSelection:
        raise GameLifecycleError(
            "FightOrderState activation_selections must contain FightActivationSelection."
        )
    return value


def _validate_eligible_passes(values: object) -> tuple[EligibleToFightPass, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightOrderState eligible_passes must be a tuple.")
    return tuple(_validate_eligible_pass(value) for value in cast(tuple[object, ...], values))


def _validate_eligible_pass(value: object) -> EligibleToFightPass:
    if type(value) is not EligibleToFightPass:
        raise GameLifecycleError(
            "FightOrderState eligible_passes must contain EligibleToFightPass."
        )
    return value


def _validate_resolved_interrupts(values: object) -> tuple[ResolvedFightInterrupt, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightOrderState resolved_interrupts must be a tuple.")
    return tuple(_validate_resolved_interrupt(value) for value in cast(tuple[object, ...], values))


def _validate_resolved_interrupt(value: object) -> ResolvedFightInterrupt:
    if type(value) is not ResolvedFightInterrupt:
        raise GameLifecycleError(
            "FightOrderState resolved_interrupts must contain ResolvedFightInterrupt."
        )
    return value


def _validate_fight_eligibility_reasons(
    values: object,
) -> tuple[FightEligibilityKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Fight eligibility reasons must be a tuple.")
    reasons = tuple(
        fight_eligibility_kind_from_token(value) for value in cast(tuple[object, ...], values)
    )
    if not reasons:
        raise GameLifecycleError("Fight eligibility reasons must not be empty.")
    return reasons


def validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(f"{field_name} item", value)
        for value in cast(tuple[object, ...], values)
    )
    if len(validated) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} value(s).")
    return tuple(sorted(validated))


def _validate_unique_unit_ids(unit_ids: tuple[str, ...]) -> None:
    if len(set(unit_ids)) != len(unit_ids):
        raise GameLifecycleError("FightOrderState unit IDs must be unique.")


def _validate_unique_interrupt_ids(interrupt_ids: tuple[str, ...]) -> None:
    if len(set(interrupt_ids)) != len(interrupt_ids):
        raise GameLifecycleError("FightOrderState interrupt IDs must be unique.")


def _validate_unique_interrupt_source_effect_ids(source_effect_ids: tuple[str, ...]) -> None:
    if len(set(source_effect_ids)) != len(source_effect_ids):
        raise GameLifecycleError("FightOrderState interrupt source effect IDs must be unique.")


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def validate_positive_float(field_name: str, value: object) -> float:
    if type(value) not in {float, int}:
        raise GameLifecycleError(f"{field_name} must be numeric.")
    numeric = float(cast(float | int, value))
    if numeric <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return numeric


def _validate_optional_non_negative_float(field_name: str, value: object | None) -> float | None:
    if value is None:
        return None
    if type(value) not in {float, int}:
        raise GameLifecycleError(f"{field_name} must be numeric.")
    numeric = float(cast(float | int, value))
    if numeric < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return numeric


_validate_identifier = IdentifierValidator(GameLifecycleError)
