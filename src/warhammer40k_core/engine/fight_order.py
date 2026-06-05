from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
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
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


FIGHT_ACTIVATION_DECISION_TYPE = "select_fight_activation"
FIGHT_INTERRUPT_DECISION_TYPE = "resolve_fight_interrupt"
ELIGIBLE_TO_FIGHT_PASS_OPTION_ID = "eligible_to_fight_pass"
DECLINE_FIGHT_INTERRUPT_OPTION_ID = "decline_fight_interrupt"
FIGHT_INTERRUPT_EFFECT_KIND = "fight_interrupt"
FIGHTS_FIRST_EFFECT_KIND = "fights_first"
CHARGE_FIGHTS_FIRST_EFFECT_KIND = "charge_grants_fights_first"


class FightsFirstSourcePayload(TypedDict):
    unit_instance_id: str
    effect_id: str
    source_rule_id: str
    effect_kind: str


class FightsFirstRegistryPayload(TypedDict):
    sources: list[FightsFirstSourcePayload]


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


class FightStepStatePayload(TypedDict):
    step: str
    status: str


class FightPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    step_states: list[FightStepStatePayload]
    ordering_bands: list[str]
    current_band_index: int
    next_player_id: str
    eligible_at_start_unit_ids: list[str]
    activated_unit_ids: list[str]
    passed_player_ids: list[str]
    activation_selections: list[FightActivationSelectionPayload]
    eligible_passes: list[EligibleToFightPassPayload]
    resolved_interrupt_ids: list[str]
    fights_first_registry: FightsFirstRegistryPayload
    phase_complete: bool


@dataclass(frozen=True, slots=True)
class FightsFirstSource:
    unit_instance_id: str
    effect_id: str
    source_rule_id: str
    effect_kind: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FightsFirstSource unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "effect_id",
            _validate_identifier("FightsFirstSource effect_id", self.effect_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("FightsFirstSource source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "effect_kind",
            _validate_identifier("FightsFirstSource effect_kind", self.effect_kind),
        )

    def to_payload(self) -> FightsFirstSourcePayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "effect_id": self.effect_id,
            "source_rule_id": self.source_rule_id,
            "effect_kind": self.effect_kind,
        }

    @classmethod
    def from_payload(cls, payload: FightsFirstSourcePayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            effect_id=payload["effect_id"],
            source_rule_id=payload["source_rule_id"],
            effect_kind=payload["effect_kind"],
        )


@dataclass(frozen=True, slots=True)
class FightsFirstRegistry:
    sources: tuple[FightsFirstSource, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", _validate_fights_first_sources(self.sources))

    @classmethod
    def from_state(cls, state: GameState) -> Self:
        sources: list[FightsFirstSource] = []
        for effect in state.persisting_effects:
            effect_payload = effect.effect_payload
            if not isinstance(effect_payload, dict):
                continue
            effect_kind = effect_payload.get("effect_kind")
            if effect_kind not in {FIGHTS_FIRST_EFFECT_KIND, CHARGE_FIGHTS_FIRST_EFFECT_KIND}:
                continue
            for unit_instance_id in effect.target_unit_instance_ids:
                sources.append(
                    FightsFirstSource(
                        unit_instance_id=unit_instance_id,
                        effect_id=effect.effect_id,
                        source_rule_id=effect.source_rule_id,
                        effect_kind=effect_kind,
                    )
                )
        return cls(tuple(sources))

    def has_unit(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return any(source.unit_instance_id == requested_unit_id for source in self.sources)

    def charged_unit_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    source.unit_instance_id
                    for source in self.sources
                    if source.effect_kind == CHARGE_FIGHTS_FIRST_EFFECT_KIND
                }
            )
        )

    def to_payload(self) -> FightsFirstRegistryPayload:
        return {"sources": [source.to_payload() for source in self.sources]}

    @classmethod
    def from_payload(cls, payload: FightsFirstRegistryPayload) -> Self:
        return cls(tuple(FightsFirstSource.from_payload(source) for source in payload["sources"]))


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
            _validate_positive_int("FightEligibilityContext battle_round", self.battle_round),
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
            _validate_positive_float(
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
            _validate_positive_int("FightActivationSelection battle_round", self.battle_round),
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
            _validate_positive_int("EligibleToFightPass battle_round", self.battle_round),
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
            _validate_positive_float(
                "EligibleToFightPass pass_distance_inches",
                self.pass_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "eligible_unit_ids",
            _validate_identifier_tuple(
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
            _validate_positive_int("FightInterruptRequest battle_round", self.battle_round),
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
            _validate_identifier_tuple(
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
class FightPhaseState:
    battle_round: int
    active_player_id: str
    step_states: tuple[FightStepState, ...]
    ordering_bands: tuple[FightOrderingBandKind, ...]
    current_band_index: int
    next_player_id: str
    eligible_at_start_unit_ids: tuple[str, ...]
    activated_unit_ids: tuple[str, ...] = ()
    passed_player_ids: tuple[str, ...] = ()
    activation_selections: tuple[FightActivationSelection, ...] = ()
    eligible_passes: tuple[EligibleToFightPass, ...] = ()
    resolved_interrupt_ids: tuple[str, ...] = ()
    fights_first_registry: FightsFirstRegistry = field(default_factory=FightsFirstRegistry)
    phase_complete: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FightPhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("FightPhaseState active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "step_states", _validate_step_states(self.step_states))
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
            _validate_identifier("FightPhaseState next_player_id", self.next_player_id),
        )
        object.__setattr__(
            self,
            "eligible_at_start_unit_ids",
            _validate_identifier_tuple(
                "FightPhaseState eligible_at_start_unit_ids",
                self.eligible_at_start_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "activated_unit_ids",
            _validate_identifier_tuple(
                "FightPhaseState activated_unit_ids",
                self.activated_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "passed_player_ids",
            _validate_identifier_tuple(
                "FightPhaseState passed_player_ids",
                self.passed_player_ids,
            ),
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
            "resolved_interrupt_ids",
            _validate_identifier_tuple(
                "FightPhaseState resolved_interrupt_ids",
                self.resolved_interrupt_ids,
            ),
        )
        if type(self.fights_first_registry) is not FightsFirstRegistry:
            raise GameLifecycleError(
                "FightPhaseState fights_first_registry must be FightsFirstRegistry."
            )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("FightPhaseState phase_complete must be a bool.")
        _validate_unique_unit_ids(self.activated_unit_ids)
        _validate_unique_unit_ids(self.eligible_at_start_unit_ids)
        _validate_unique_interrupt_ids(self.resolved_interrupt_ids)

    @classmethod
    def start(
        cls,
        *,
        battle_round: int,
        active_player_id: str,
        policy: FightPolicyDescriptor,
        eligible_at_start_unit_ids: tuple[str, ...],
        fights_first_registry: FightsFirstRegistry,
    ) -> Self:
        if type(policy) is not FightPolicyDescriptor:
            raise GameLifecycleError("FightPhaseState start requires a FightPolicyDescriptor.")
        return cls(
            battle_round=battle_round,
            active_player_id=active_player_id,
            step_states=tuple(_initial_step_state(step) for step in policy.steps),
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id=active_player_id,
            eligible_at_start_unit_ids=eligible_at_start_unit_ids,
            fights_first_registry=fights_first_registry,
        )

    @property
    def current_ordering_band(self) -> FightOrderingBandKind:
        return self.ordering_bands[self.current_band_index]

    def with_next_player(self, player_id: str) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step_states=self.step_states,
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=_validate_identifier("player_id", player_id),
            eligible_at_start_unit_ids=self.eligible_at_start_unit_ids,
            activated_unit_ids=self.activated_unit_ids,
            passed_player_ids=self.passed_player_ids,
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupt_ids=self.resolved_interrupt_ids,
            fights_first_registry=self.fights_first_registry,
            phase_complete=self.phase_complete,
        )

    def with_next_band(self) -> Self:
        if self.current_band_index + 1 >= len(self.ordering_bands):
            return self.with_phase_complete()
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step_states=self.step_states,
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index + 1,
            next_player_id=self.active_player_id,
            eligible_at_start_unit_ids=self.eligible_at_start_unit_ids,
            activated_unit_ids=self.activated_unit_ids,
            passed_player_ids=(),
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupt_ids=self.resolved_interrupt_ids,
            fights_first_registry=self.fights_first_registry,
            phase_complete=False,
        )

    def with_activation(self, selection: FightActivationSelection) -> Self:
        if type(selection) is not FightActivationSelection:
            raise GameLifecycleError("Fight activation requires FightActivationSelection.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Fight activation battle round drift.")
        if selection.unit_instance_id in self.activated_unit_ids:
            raise GameLifecycleError("Fight activation unit already activated.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step_states=self.step_states,
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            eligible_at_start_unit_ids=self.eligible_at_start_unit_ids,
            activated_unit_ids=(*self.activated_unit_ids, selection.unit_instance_id),
            passed_player_ids=tuple(
                player_id
                for player_id in self.passed_player_ids
                if player_id != selection.player_id
            ),
            activation_selections=(*self.activation_selections, selection),
            eligible_passes=self.eligible_passes,
            resolved_interrupt_ids=self.resolved_interrupt_ids,
            fights_first_registry=self.fights_first_registry,
            phase_complete=False,
        )

    def with_eligible_pass(self, eligible_pass: EligibleToFightPass) -> Self:
        if type(eligible_pass) is not EligibleToFightPass:
            raise GameLifecycleError("Fight pass requires EligibleToFightPass.")
        if eligible_pass.battle_round != self.battle_round:
            raise GameLifecycleError("Fight pass battle round drift.")
        if eligible_pass.ordering_band is not self.current_ordering_band:
            raise GameLifecycleError("Fight pass ordering band drift.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step_states=self.step_states,
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            eligible_at_start_unit_ids=self.eligible_at_start_unit_ids,
            activated_unit_ids=self.activated_unit_ids,
            passed_player_ids=tuple(sorted({*self.passed_player_ids, eligible_pass.player_id})),
            activation_selections=self.activation_selections,
            eligible_passes=(*self.eligible_passes, eligible_pass),
            resolved_interrupt_ids=self.resolved_interrupt_ids,
            fights_first_registry=self.fights_first_registry,
            phase_complete=False,
        )

    def with_resolved_interrupt(self, interrupt_id: str) -> Self:
        resolved_interrupt_id = _validate_identifier("interrupt_id", interrupt_id)
        if resolved_interrupt_id in self.resolved_interrupt_ids:
            raise GameLifecycleError("Fight interrupt has already resolved.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step_states=self.step_states,
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            eligible_at_start_unit_ids=self.eligible_at_start_unit_ids,
            activated_unit_ids=self.activated_unit_ids,
            passed_player_ids=self.passed_player_ids,
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupt_ids=(*self.resolved_interrupt_ids, resolved_interrupt_id),
            fights_first_registry=self.fights_first_registry,
            phase_complete=False,
        )

    def with_phase_complete(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step_states=tuple(
                FightStepState(step=state.step, status="complete") for state in self.step_states
            ),
            ordering_bands=self.ordering_bands,
            current_band_index=self.current_band_index,
            next_player_id=self.next_player_id,
            eligible_at_start_unit_ids=self.eligible_at_start_unit_ids,
            activated_unit_ids=self.activated_unit_ids,
            passed_player_ids=self.passed_player_ids,
            activation_selections=self.activation_selections,
            eligible_passes=self.eligible_passes,
            resolved_interrupt_ids=self.resolved_interrupt_ids,
            fights_first_registry=self.fights_first_registry,
            phase_complete=True,
        )

    def to_payload(self) -> FightPhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "step_states": [step.to_payload() for step in self.step_states],
            "ordering_bands": [band.value for band in self.ordering_bands],
            "current_band_index": self.current_band_index,
            "next_player_id": self.next_player_id,
            "eligible_at_start_unit_ids": list(self.eligible_at_start_unit_ids),
            "activated_unit_ids": list(self.activated_unit_ids),
            "passed_player_ids": list(self.passed_player_ids),
            "activation_selections": [
                selection.to_payload() for selection in self.activation_selections
            ],
            "eligible_passes": [
                eligible_pass.to_payload() for eligible_pass in self.eligible_passes
            ],
            "resolved_interrupt_ids": list(self.resolved_interrupt_ids),
            "fights_first_registry": self.fights_first_registry.to_payload(),
            "phase_complete": self.phase_complete,
        }

    @classmethod
    def from_payload(cls, payload: FightPhaseStatePayload) -> Self:
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            step_states=tuple(FightStepState.from_payload(step) for step in payload["step_states"]),
            ordering_bands=tuple(
                fight_ordering_band_kind_from_token(band) for band in payload["ordering_bands"]
            ),
            current_band_index=payload["current_band_index"],
            next_player_id=payload["next_player_id"],
            eligible_at_start_unit_ids=tuple(payload["eligible_at_start_unit_ids"]),
            activated_unit_ids=tuple(payload["activated_unit_ids"]),
            passed_player_ids=tuple(payload["passed_player_ids"]),
            activation_selections=tuple(
                FightActivationSelection.from_payload(selection)
                for selection in payload["activation_selections"]
            ),
            eligible_passes=tuple(
                EligibleToFightPass.from_payload(eligible_pass)
                for eligible_pass in payload["eligible_passes"]
            ),
            resolved_interrupt_ids=tuple(payload["resolved_interrupt_ids"]),
            fights_first_registry=FightsFirstRegistry.from_payload(
                payload["fights_first_registry"]
            ),
            phase_complete=payload["phase_complete"],
        )


def eligible_fight_contexts_for_player(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    player_id: str,
    policy: FightPolicyDescriptor,
) -> tuple[FightEligibilityContext, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    contexts: list[FightEligibilityContext] = []
    for unit_id in _unit_ids_for_player(state=state, player_id=requested_player_id):
        if unit_id in fight_state.activated_unit_ids:
            continue
        reasons = _eligibility_reasons_for_unit(
            state=state,
            fight_state=fight_state,
            unit_instance_id=unit_id,
            policy=policy,
        )
        if not reasons:
            continue
        band = fight_state.current_ordering_band
        has_fights_first = fight_state.fights_first_registry.has_unit(unit_id)
        if band is FightOrderingBandKind.FIGHTS_FIRST and not has_fights_first:
            continue
        if band is FightOrderingBandKind.REMAINING_COMBATS and has_fights_first:
            continue
        contexts.append(
            FightEligibilityContext(
                player_id=requested_player_id,
                battle_round=fight_state.battle_round,
                unit_instance_id=unit_id,
                ordering_band=band,
                eligibility_reasons=reasons,
                closest_enemy_distance_inches=_closest_enemy_distance_inches(
                    state=state,
                    player_id=requested_player_id,
                    unit_instance_id=unit_id,
                ),
                pass_distance_inches=policy.eligible_pass_distance_inches,
            )
        )
    return tuple(sorted(contexts, key=lambda context: context.unit_instance_id))


def eligible_pass_is_available(contexts: tuple[FightEligibilityContext, ...]) -> bool:
    if not contexts:
        return False
    return all(context.more_than_pass_distance_from_all_enemies for context in contexts)


def engaged_unit_ids_at_fight_start(
    *,
    state: GameState,
    policy: FightPolicyDescriptor,
) -> tuple[str, ...]:
    del policy
    engaged: set[str] = set()
    for first_player_id in state.player_ids:
        for unit_id in _unit_ids_for_player(state=state, player_id=first_player_id):
            if _unit_is_engaged(state=state, player_id=first_player_id, unit_instance_id=unit_id):
                engaged.add(unit_id)
    return tuple(sorted(engaged))


def fight_activation_option_id(*, unit_instance_id: str, fight_type: FightTypeKind) -> str:
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    fight_type_value = fight_type_kind_from_token(fight_type)
    return f"fight:{fight_type_value.value}:{unit_id}"


def fight_activation_option_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    context: FightEligibilityContext,
    fight_type: FightTypeKind,
) -> JsonValue:
    fight_type_value = fight_type_kind_from_token(fight_type)
    return validate_json_value(
        {
            "submission_kind": "select_fight_activation",
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhaseKind.FIGHT.value,
            "player_id": context.player_id,
            "active_player_id": fight_state.active_player_id,
            "unit_instance_id": context.unit_instance_id,
            "ordering_band": context.ordering_band.value,
            "fight_type": fight_type_value.value,
            "eligibility_context": context.to_payload(),
        }
    )


def eligible_pass_option_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    player_id: str,
    contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> JsonValue:
    return validate_json_value(
        {
            "submission_kind": "eligible_to_fight_pass",
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhaseKind.FIGHT.value,
            "player_id": _validate_identifier("player_id", player_id),
            "active_player_id": fight_state.active_player_id,
            "ordering_band": fight_state.current_ordering_band.value,
            "pass_distance_inches": policy.eligible_pass_distance_inches,
            "eligible_unit_ids": [context.unit_instance_id for context in contexts],
        }
    )


def fight_interrupt_option_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    interrupt: FightInterruptRequest,
    context: FightEligibilityContext,
    fight_type: FightTypeKind,
) -> JsonValue:
    payload = fight_activation_option_payload(
        state=state,
        fight_state=fight_state,
        context=context,
        fight_type=fight_type,
    )
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fight interrupt option payload must be an object.")
    payload["submission_kind"] = "select_fight_interrupt"
    payload["interrupt"] = validate_json_value(interrupt.to_payload())
    return validate_json_value(payload)


def decline_fight_interrupt_payload(*, interrupt: FightInterruptRequest) -> JsonValue:
    return validate_json_value(
        {
            "submission_kind": "decline_fight_interrupt",
            "interrupt": validate_json_value(interrupt.to_payload()),
        }
    )


def fight_interrupt_sources_for_player(
    *,
    state: GameState,
    player_id: str,
) -> tuple[tuple[str, str, str], ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    sources: list[tuple[str, str, str]] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") != FIGHT_INTERRUPT_EFFECT_KIND:
            continue
        source_rule_id = effect_payload.get("source_rule_id")
        if type(source_rule_id) is not str:
            source_rule_id = effect.source_rule_id
        sources.append((effect.effect_id, source_rule_id, effect.source_rule_id))
    return tuple(sorted(sources, key=lambda source: source[0]))


def current_fight_activation_selection_from_payload(
    *,
    result_payload: JsonValue,
    request_id: str,
    result_id: str,
    interrupt_id: str | None = None,
) -> FightActivationSelection:
    payload = _json_object("Fight activation result payload", result_payload)
    context_payload = _json_object(
        "Fight activation eligibility_context",
        payload.get("eligibility_context"),
    )
    return FightActivationSelection(
        player_id=_payload_string(payload, key="player_id"),
        battle_round=_payload_positive_int(payload, key="battle_round"),
        unit_instance_id=_payload_string(payload, key="unit_instance_id"),
        ordering_band=fight_ordering_band_kind_from_token(payload["ordering_band"]),
        fight_type=fight_type_kind_from_token(payload["fight_type"]),
        eligibility_reasons=tuple(
            fight_eligibility_kind_from_token(reason)
            for reason in _payload_string_list(context_payload, key="eligibility_reasons")
        ),
        request_id=request_id,
        result_id=result_id,
        interrupt_id=interrupt_id,
    )


def current_eligible_pass_from_payload(
    *,
    result_payload: JsonValue,
    request_id: str,
    result_id: str,
) -> EligibleToFightPass:
    payload = _json_object("Eligible-to-fight pass payload", result_payload)
    return EligibleToFightPass(
        player_id=_payload_string(payload, key="player_id"),
        battle_round=_payload_positive_int(payload, key="battle_round"),
        ordering_band=fight_ordering_band_kind_from_token(payload["ordering_band"]),
        request_id=request_id,
        result_id=result_id,
        pass_distance_inches=_payload_positive_float(payload, key="pass_distance_inches"),
        eligible_unit_ids=tuple(_payload_string_list(payload, key="eligible_unit_ids")),
    )


def fight_interrupt_request_from_payload(result_payload: JsonValue) -> FightInterruptRequest:
    payload = _json_object("Fight interrupt result payload", result_payload)
    interrupt_payload = _json_object("Fight interrupt payload", payload.get("interrupt"))
    return FightInterruptRequest.from_payload(cast(FightInterruptRequestPayload, interrupt_payload))


def _eligibility_reasons_for_unit(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    unit_instance_id: str,
    policy: FightPolicyDescriptor,
) -> tuple[FightEligibilityKind, ...]:
    reasons: list[FightEligibilityKind] = []
    if (
        FightEligibilityKind.CHARGED_THIS_TURN in policy.eligibility_kinds
        and unit_instance_id in fight_state.fights_first_registry.charged_unit_ids()
    ):
        reasons.append(FightEligibilityKind.CHARGED_THIS_TURN)
    if (
        FightEligibilityKind.ENGAGED_AT_FIGHT_PHASE_START in policy.eligibility_kinds
        and unit_instance_id in fight_state.eligible_at_start_unit_ids
    ):
        reasons.append(FightEligibilityKind.ENGAGED_AT_FIGHT_PHASE_START)
    if FightEligibilityKind.ENGAGED_AT_ACTIVATION in policy.eligibility_kinds:
        owner = _owner_for_unit(state=state, unit_instance_id=unit_instance_id)
        if _unit_is_engaged(state=state, player_id=owner, unit_instance_id=unit_instance_id):
            reasons.append(FightEligibilityKind.ENGAGED_AT_ACTIVATION)
    return tuple(reasons)


def _unit_is_engaged(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    unit_models = _geometry_models_for_unit(state=state, unit_instance_id=unit_instance_id)
    if not unit_models:
        return False
    for enemy_unit_id in _enemy_unit_ids_for_player(state=state, player_id=player_id):
        enemy_models = _geometry_models_for_unit(state=state, unit_instance_id=enemy_unit_id)
        if _any_models_within_engagement_range(
            first_models=unit_models,
            second_models=enemy_models,
            state=state,
        ):
            return True
    return False


def _closest_enemy_distance_inches(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> float | None:
    unit_models = _geometry_models_for_unit(state=state, unit_instance_id=unit_instance_id)
    if not unit_models:
        return None
    distances: list[float] = []
    for enemy_unit_id in _enemy_unit_ids_for_player(state=state, player_id=player_id):
        for first_model in unit_models:
            for second_model in _geometry_models_for_unit(
                state=state,
                unit_instance_id=enemy_unit_id,
            ):
                distances.append(first_model.range_to(second_model))
    if not distances:
        return None
    return min(distances)


def _any_models_within_engagement_range(
    *,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    state: GameState,
) -> bool:
    policy = state.runtime_ruleset_descriptor().engagement_policy
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
) -> tuple[GeometryModel, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight eligibility requires battlefield_state.")
    unit = _unit_by_id(state=state, unit_instance_id=unit_instance_id)
    try:
        unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    except ValueError as exc:
        raise GameLifecycleError("Fight eligibility requires placed units.") from exc
    model_by_id = {model.model_instance_id: model for model in unit.own_models}
    models: list[GeometryModel] = []
    for placement in unit_placement.model_placements:
        model = model_by_id.get(placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("UnitPlacement references an unknown model.")
        if not model.is_alive:
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def _unit_ids_for_player(*, state: GameState, player_id: str) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Fight phase requires mustered army definitions.")
    placed_unit_ids = _placed_unit_ids(state)
    return tuple(
        unit.unit_instance_id for unit in army.units if unit.unit_instance_id in placed_unit_ids
    )


def _enemy_unit_ids_for_player(*, state: GameState, player_id: str) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    return tuple(
        unit_id
        for opponent_id in state.player_ids
        if opponent_id != requested_player_id
        for unit_id in _unit_ids_for_player(state=state, player_id=opponent_id)
    )


def _owner_for_unit(*, state: GameState, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id
    raise GameLifecycleError("Fight unit owner was not found.")


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Fight unit was not found.")


def _placed_unit_ids(state: GameState) -> set[str]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight phase requires battlefield_state.")
    payload = battlefield_state.to_payload()
    return {
        unit_placement["unit_instance_id"]
        for army in payload["placed_armies"]
        for unit_placement in army["unit_placements"]
    }


def _initial_step_state(step: FightPhaseStepKind) -> FightStepState:
    step_value = fight_phase_step_kind_from_token(step)
    status = "active" if step_value is FightPhaseStepKind.FIGHT else "pending"
    return FightStepState(step=step_value, status=status)


def _validate_fights_first_sources(values: object) -> tuple[FightsFirstSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightsFirstRegistry sources must be a tuple.")
    sources = tuple(
        _validate_fights_first_source(value) for value in cast(tuple[object, ...], values)
    )
    seen: set[tuple[str, str]] = set()
    for source in sources:
        key = (source.unit_instance_id, source.effect_id)
        if key in seen:
            raise GameLifecycleError("FightsFirstRegistry sources must be unique.")
        seen.add(key)
    return tuple(sorted(sources, key=lambda source: (source.unit_instance_id, source.effect_id)))


def _validate_fights_first_source(value: object) -> FightsFirstSource:
    if type(value) is not FightsFirstSource:
        raise GameLifecycleError("FightsFirstRegistry sources must contain FightsFirstSource.")
    return value


def _validate_step_states(values: object) -> tuple[FightStepState, ...]:
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
        raise GameLifecycleError("FightPhaseState ordering_bands must be a tuple.")
    bands = tuple(
        fight_ordering_band_kind_from_token(value) for value in cast(tuple[object, ...], values)
    )
    if not bands:
        raise GameLifecycleError("FightPhaseState ordering_bands must not be empty.")
    return bands


def _validate_band_index(index: object, bands: tuple[FightOrderingBandKind, ...]) -> int:
    if type(index) is not int:
        raise GameLifecycleError("FightPhaseState current_band_index must be an int.")
    if index < 0 or index >= len(bands):
        raise GameLifecycleError("FightPhaseState current_band_index is out of range.")
    return index


def _validate_activation_selections(values: object) -> tuple[FightActivationSelection, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightPhaseState activation_selections must be a tuple.")
    return tuple(
        _validate_activation_selection(value) for value in cast(tuple[object, ...], values)
    )


def _validate_activation_selection(value: object) -> FightActivationSelection:
    if type(value) is not FightActivationSelection:
        raise GameLifecycleError(
            "FightPhaseState activation_selections must contain FightActivationSelection."
        )
    return value


def _validate_eligible_passes(values: object) -> tuple[EligibleToFightPass, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightPhaseState eligible_passes must be a tuple.")
    return tuple(_validate_eligible_pass(value) for value in cast(tuple[object, ...], values))


def _validate_eligible_pass(value: object) -> EligibleToFightPass:
    if type(value) is not EligibleToFightPass:
        raise GameLifecycleError(
            "FightPhaseState eligible_passes must contain EligibleToFightPass."
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


def _validate_identifier_tuple(
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
        raise GameLifecycleError("FightPhaseState unit IDs must be unique.")


def _validate_unique_interrupt_ids(interrupt_ids: tuple[str, ...]) -> None:
    if len(set(interrupt_ids)) != len(interrupt_ids):
        raise GameLifecycleError("FightPhaseState interrupt IDs must be unique.")


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
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_positive_float(field_name: str, value: object) -> float:
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


def _json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"{key} must be a list.")
    return tuple(_validate_identifier(f"{key} item", item) for item in value)


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    return _validate_positive_int(key, payload.get(key))


def _payload_positive_float(payload: dict[str, JsonValue], *, key: str) -> float:
    return _validate_positive_float(key, payload.get(key))
