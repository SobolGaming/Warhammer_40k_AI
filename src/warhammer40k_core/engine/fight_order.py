from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

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
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequencePayload
from warhammer40k_core.engine.battlefield_presence import fight_present_rules_unit_views
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order_records import (
    EligibleToFightPass as EligibleToFightPass,
)
from warhammer40k_core.engine.fight_order_records import (
    EligibleToFightPassPayload as EligibleToFightPassPayload,
)
from warhammer40k_core.engine.fight_order_records import (
    FightActivationSelection as FightActivationSelection,
)
from warhammer40k_core.engine.fight_order_records import (
    FightActivationSelectionPayload as FightActivationSelectionPayload,
)
from warhammer40k_core.engine.fight_order_records import (
    FightEligibilityContext as FightEligibilityContext,
)
from warhammer40k_core.engine.fight_order_records import (
    FightEligibilityContextPayload as FightEligibilityContextPayload,
)
from warhammer40k_core.engine.fight_order_records import (
    FightInterruptRequest as FightInterruptRequest,
)
from warhammer40k_core.engine.fight_order_records import (
    FightInterruptRequestPayload as FightInterruptRequestPayload,
)
from warhammer40k_core.engine.fight_order_records import (
    FightMovementStepState as FightMovementStepState,
)
from warhammer40k_core.engine.fight_order_records import (
    FightMovementStepStatePayload as FightMovementStepStatePayload,
)
from warhammer40k_core.engine.fight_order_records import (
    FightOrderState as FightOrderState,
)
from warhammer40k_core.engine.fight_order_records import (
    FightOrderStatePayload as FightOrderStatePayload,
)
from warhammer40k_core.engine.fight_order_records import (
    FightStepState as FightStepState,
)
from warhammer40k_core.engine.fight_order_records import (
    FightStepStatePayload as FightStepStatePayload,
)
from warhammer40k_core.engine.fight_order_records import (
    ResolvedFightInterrupt as ResolvedFightInterrupt,
)
from warhammer40k_core.engine.fight_order_records import (
    ResolvedFightInterruptPayload as ResolvedFightInterruptPayload,
)
from warhammer40k_core.engine.fight_order_records import (
    step_states_for_current_step as step_states_for_current_step,
)
from warhammer40k_core.engine.fight_order_records import (
    validate_identifier_tuple as validate_identifier_tuple,
)
from warhammer40k_core.engine.fight_order_records import (
    validate_positive_float as validate_positive_float,
)
from warhammer40k_core.engine.fight_order_records import (
    validate_positive_int as validate_positive_int,
)
from warhammer40k_core.engine.fight_order_records import (
    validate_step_states as validate_step_states,
)
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
    FightsFirstSource as FightsFirstSource,
)
from warhammer40k_core.engine.forced_fight_context import (
    ForcedFightActivationContext as ForcedFightActivationContext,
)
from warhammer40k_core.engine.forced_fight_context import (
    ForcedFightActivationContextPayload as ForcedFightActivationContextPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    current_closest_physical_enemy_distance_inches,
    current_rules_unit_is_physically_engaged,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_identity_history_contains,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


FIGHT_ACTIVATION_DECISION_TYPE = "select_fight_activation"
FIGHT_INTERRUPT_DECISION_TYPE = "resolve_fight_interrupt"
ELIGIBLE_TO_FIGHT_PASS_OPTION_ID = "eligible_to_fight_pass"
DECLINE_FIGHT_INTERRUPT_OPTION_ID = "decline_fight_interrupt"
FIGHT_INTERRUPT_EFFECT_KIND = "fight_interrupt"
_UNSET = object()


class FightPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    current_step: str
    step_states: list[FightStepStatePayload]
    pile_in_state: FightMovementStepStatePayload | None
    consolidate_state: FightMovementStepStatePayload | None
    fight_order_state: FightOrderStatePayload
    active_activation: FightActivationSelectionPayload | None
    pending_completed_attack_sequence: NotRequired[AttackSequencePayload]
    attack_sequence: AttackSequencePayload | None
    allocated_model_ids_this_phase: list[str]
    overrun_pile_in_completed_activation_result_ids: list[str]
    phase_complete: bool
    forced_activation_context: NotRequired[ForcedFightActivationContextPayload]
    suspended_state: NotRequired[FightPhaseStatePayload]


@dataclass(frozen=True, slots=True)
class FightPhaseState:
    battle_round: int
    active_player_id: str
    current_step: FightPhaseStepKind
    step_states: tuple[FightStepState, ...]
    fight_order_state: FightOrderState
    pile_in_state: FightMovementStepState | None = None
    consolidate_state: FightMovementStepState | None = None
    active_activation: FightActivationSelection | None = None
    pending_completed_attack_sequence: AttackSequence | None = None
    attack_sequence: AttackSequence | None = None
    allocated_model_ids_this_phase: tuple[str, ...] = ()
    overrun_pile_in_completed_activation_result_ids: tuple[str, ...] = ()
    phase_complete: bool = False
    forced_activation_context: ForcedFightActivationContext | None = None
    suspended_state: FightPhaseState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            validate_positive_int("FightPhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("FightPhaseState active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "current_step",
            fight_phase_step_kind_from_token(self.current_step),
        )
        object.__setattr__(self, "step_states", validate_step_states(self.step_states))
        if type(self.fight_order_state) is not FightOrderState:
            raise GameLifecycleError("FightPhaseState fight_order_state must be FightOrderState.")
        if self.pile_in_state is not None and type(self.pile_in_state) is not (
            FightMovementStepState
        ):
            raise GameLifecycleError(
                "FightPhaseState pile_in_state must be FightMovementStepState."
            )
        if self.consolidate_state is not None and type(self.consolidate_state) is not (
            FightMovementStepState
        ):
            raise GameLifecycleError(
                "FightPhaseState consolidate_state must be FightMovementStepState."
            )
        if self.active_activation is not None and type(self.active_activation) is not (
            FightActivationSelection
        ):
            raise GameLifecycleError(
                "FightPhaseState active_activation must be FightActivationSelection."
            )
        if (
            self.pending_completed_attack_sequence is not None
            and type(self.pending_completed_attack_sequence) is not AttackSequence
        ):
            raise GameLifecycleError(
                "FightPhaseState pending_completed_attack_sequence must be AttackSequence."
            )
        if self.attack_sequence is not None and type(self.attack_sequence) is not AttackSequence:
            raise GameLifecycleError("FightPhaseState attack_sequence must be AttackSequence.")
        if self.attack_sequence is not None and self.pending_completed_attack_sequence is not None:
            raise GameLifecycleError(
                "FightPhaseState cannot retain active and completed attack sequences together."
            )
        object.__setattr__(
            self,
            "allocated_model_ids_this_phase",
            validate_identifier_tuple(
                "FightPhaseState allocated_model_ids_this_phase",
                self.allocated_model_ids_this_phase,
            ),
        )
        object.__setattr__(
            self,
            "overrun_pile_in_completed_activation_result_ids",
            validate_identifier_tuple(
                "FightPhaseState overrun_pile_in_completed_activation_result_ids",
                self.overrun_pile_in_completed_activation_result_ids,
            ),
        )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("FightPhaseState phase_complete must be a bool.")
        if (
            self.forced_activation_context is not None
            and type(self.forced_activation_context) is not ForcedFightActivationContext
        ):
            raise GameLifecycleError("FightPhaseState forced_activation_context must be typed.")

        if self.suspended_state is not None:
            if type(self.suspended_state) is not FightPhaseState:
                raise GameLifecycleError("Suspended Fight state must be typed.")
            if (
                self.forced_activation_context is None
                or self.forced_activation_context.source_phase is not BattlePhaseKind.FIGHT
                or self.suspended_state.forced_activation_context is not None
                or self.suspended_state.suspended_state is not None
                or self.suspended_state.battle_round != self.battle_round
                or self.suspended_state.active_player_id != self.active_player_id
            ):
                raise GameLifecycleError("Suspended Fight state context drift.")

    @classmethod
    def start(
        cls,
        *,
        battle_round: int,
        active_player_id: str,
        policy: FightPolicyDescriptor,
        engaged_at_fight_step_start_unit_ids: tuple[str, ...],
        fights_first_registry: FightsFirstRegistry,
    ) -> Self:
        if type(policy) is not FightPolicyDescriptor:
            raise GameLifecycleError("FightPhaseState start requires a FightPolicyDescriptor.")
        return cls(
            battle_round=battle_round,
            active_player_id=active_player_id,
            current_step=FightPhaseStepKind.PILE_IN,
            step_states=step_states_for_current_step(
                steps=policy.steps,
                current_step=FightPhaseStepKind.PILE_IN,
                phase_complete=False,
            ),
            pile_in_state=FightMovementStepState.start(
                step=FightPhaseStepKind.PILE_IN,
                next_player_id=active_player_id,
            ),
            consolidate_state=FightMovementStepState.start(
                step=FightPhaseStepKind.CONSOLIDATE,
                next_player_id=active_player_id,
            ),
            fight_order_state=FightOrderState.start(
                policy=policy,
                next_player_id=active_player_id,
                engaged_at_fight_step_start_unit_ids=engaged_at_fight_step_start_unit_ids,
                fights_first_registry=fights_first_registry,
            ),
        )

    @classmethod
    def for_forced_activations(
        cls,
        *,
        battle_round: int,
        active_player_id: str,
        policy: FightPolicyDescriptor,
        context: ForcedFightActivationContext,
        fights_first_registry: FightsFirstRegistry,
        suspended_state: FightPhaseState | None = None,
    ) -> Self:
        if type(policy) is not FightPolicyDescriptor:
            raise GameLifecycleError("Forced Fight activations require a FightPolicyDescriptor.")
        if type(context) is not ForcedFightActivationContext:
            raise GameLifecycleError("Forced Fight activations require a typed source context.")
        return cls(
            battle_round=battle_round,
            active_player_id=active_player_id,
            current_step=FightPhaseStepKind.FIGHT,
            step_states=step_states_for_current_step(
                steps=policy.steps,
                current_step=FightPhaseStepKind.FIGHT,
                phase_complete=False,
            ),
            fight_order_state=FightOrderState(
                ordering_bands=(FightOrderingBandKind.REMAINING_COMBATS,),
                current_band_index=0,
                next_player_id=context.selecting_player_id,
                engaged_at_fight_step_start_unit_ids=(
                    context.eligible_unit_instance_ids
                    if suspended_state is None
                    else suspended_state.fight_order_state.engaged_at_fight_step_start_unit_ids
                ),
                fights_first_registry=fights_first_registry,
            ),
            forced_activation_context=context,
            suspended_state=suspended_state,
            allocated_model_ids_this_phase=(
                () if suspended_state is None else suspended_state.allocated_model_ids_this_phase
            ),
        )

    @property
    def current_ordering_band(self) -> FightOrderingBandKind:
        return self.fight_order_state.current_ordering_band

    def with_next_player(self, player_id: str) -> Self:
        return self._with_order_state(self.fight_order_state.with_next_player(player_id))

    def with_next_band(self) -> Self:
        if self.fight_order_state.current_band_index + 1 >= len(
            self.fight_order_state.ordering_bands
        ):
            return self.with_phase_complete()
        return self._with_order_state(
            self.fight_order_state.with_next_band(next_player_id=self.active_player_id)
        )

    def with_ordering_band(
        self,
        *,
        ordering_band: FightOrderingBandKind,
        next_player_id: str,
    ) -> Self:
        band = fight_ordering_band_kind_from_token(ordering_band)
        return self._with_order_state(
            self.fight_order_state.with_ordering_band(
                current_band_index=self.fight_order_state.ordering_bands.index(band),
                next_player_id=next_player_id,
            )
        )

    def with_activation(self, selection: FightActivationSelection) -> Self:
        if type(selection) is not FightActivationSelection:
            raise GameLifecycleError("Fight activation requires FightActivationSelection.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Fight activation battle round drift.")
        return self._with_order_state(self.fight_order_state.with_activation(selection))

    def with_eligible_pass(self, eligible_pass: EligibleToFightPass) -> Self:
        if type(eligible_pass) is not EligibleToFightPass:
            raise GameLifecycleError("Fight pass requires EligibleToFightPass.")
        if eligible_pass.battle_round != self.battle_round:
            raise GameLifecycleError("Fight pass battle round drift.")
        return self._with_order_state(self.fight_order_state.with_eligible_pass(eligible_pass))

    def with_resolved_interrupt(self, *, interrupt_id: str, source_effect_id: str) -> Self:
        return self._with_order_state(
            self.fight_order_state.with_resolved_interrupt(
                interrupt_id=interrupt_id,
                source_effect_id=source_effect_id,
            )
        )

    def with_current_step(
        self,
        *,
        current_step: FightPhaseStepKind,
        policy: FightPolicyDescriptor,
    ) -> Self:
        if type(policy) is not FightPolicyDescriptor:
            raise GameLifecycleError("FightPhaseState current-step update requires policy.")
        step = fight_phase_step_kind_from_token(current_step)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=step,
            step_states=step_states_for_current_step(
                steps=policy.steps,
                current_step=step,
                phase_complete=False,
            ),
            pile_in_state=self.pile_in_state,
            consolidate_state=self.consolidate_state,
            fight_order_state=self.fight_order_state,
            active_activation=self.active_activation,
            pending_completed_attack_sequence=self.pending_completed_attack_sequence,
            attack_sequence=self.attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
            overrun_pile_in_completed_activation_result_ids=(
                self.overrun_pile_in_completed_activation_result_ids
            ),
            phase_complete=False,
            forced_activation_context=self.forced_activation_context,
            suspended_state=self.suspended_state,
        )

    def with_pile_in_state(self, pile_in_state: FightMovementStepState) -> Self:
        if type(pile_in_state) is not FightMovementStepState:
            raise GameLifecycleError("FightPhaseState pile_in_state update requires state.")
        if pile_in_state.step is not FightPhaseStepKind.PILE_IN:
            raise GameLifecycleError("FightPhaseState pile_in_state step drift.")
        return self._replace(pile_in_state=pile_in_state)

    def with_consolidate_state(self, consolidate_state: FightMovementStepState) -> Self:
        if type(consolidate_state) is not FightMovementStepState:
            raise GameLifecycleError("FightPhaseState consolidate_state update requires state.")
        if consolidate_state.step is not FightPhaseStepKind.CONSOLIDATE:
            raise GameLifecycleError("FightPhaseState consolidate_state step drift.")
        return self._replace(consolidate_state=consolidate_state)

    def with_active_activation(self, selection: FightActivationSelection | None) -> Self:
        if selection is not None:
            if type(selection) is not FightActivationSelection:
                raise GameLifecycleError(
                    "FightPhaseState active activation update requires selection."
                )
            if selection.battle_round != self.battle_round:
                raise GameLifecycleError("Fight activation battle round drift.")
        return self._replace(active_activation=selection)

    def with_attack_sequence_update(
        self,
        *,
        attack_sequence: AttackSequence | None,
        allocated_model_ids_this_phase: tuple[str, ...],
    ) -> Self:
        if attack_sequence is not None and type(attack_sequence) is not AttackSequence:
            raise GameLifecycleError("FightPhaseState attack_sequence update requires sequence.")
        from warhammer40k_core.engine.attack_completion_authority import (
            attack_completion_continuation,
        )

        return self._replace(
            pending_completed_attack_sequence=attack_completion_continuation(
                previous=self.attack_sequence,
                updated=attack_sequence,
                pending=self.pending_completed_attack_sequence,
            ),
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids_this_phase,
        )

    def with_pending_completed_attack_sequence(
        self,
        attack_sequence: AttackSequence | None,
    ) -> Self:
        if attack_sequence is not None and type(attack_sequence) is not AttackSequence:
            raise GameLifecycleError(
                "FightPhaseState completed attack sequence update requires sequence."
            )
        return self._replace(pending_completed_attack_sequence=attack_sequence)

    def with_overrun_pile_in_completed(self, *, activation_result_id: str) -> Self:
        result_id = _validate_identifier("activation_result_id", activation_result_id)
        if result_id in self.overrun_pile_in_completed_activation_result_ids:
            raise GameLifecycleError("Overrun pile-in has already completed for this activation.")
        return self._replace(
            overrun_pile_in_completed_activation_result_ids=(
                *self.overrun_pile_in_completed_activation_result_ids,
                result_id,
            ),
        )

    def overrun_pile_in_is_completed(self, *, activation_result_id: str) -> bool:
        result_id = _validate_identifier("activation_result_id", activation_result_id)
        return result_id in self.overrun_pile_in_completed_activation_result_ids

    def with_phase_complete(self) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=FightPhaseStepKind.END,
            step_states=tuple(
                FightStepState(step=state.step, status="complete") for state in self.step_states
            ),
            pile_in_state=self.pile_in_state,
            consolidate_state=self.consolidate_state,
            fight_order_state=self.fight_order_state,
            active_activation=None,
            pending_completed_attack_sequence=None,
            attack_sequence=None,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
            overrun_pile_in_completed_activation_result_ids=(
                self.overrun_pile_in_completed_activation_result_ids
            ),
            phase_complete=True,
            forced_activation_context=self.forced_activation_context,
            suspended_state=self.suspended_state,
        )

    def _with_order_state(self, fight_order_state: FightOrderState) -> Self:
        return self._replace(fight_order_state=fight_order_state)

    def _replace(
        self,
        *,
        current_step: FightPhaseStepKind | None = None,
        step_states: tuple[FightStepState, ...] | None = None,
        fight_order_state: FightOrderState | None = None,
        pile_in_state: FightMovementStepState | None | object = _UNSET,
        consolidate_state: FightMovementStepState | None | object = _UNSET,
        active_activation: FightActivationSelection | None | object = _UNSET,
        pending_completed_attack_sequence: AttackSequence | None | object = _UNSET,
        attack_sequence: AttackSequence | None | object = _UNSET,
        allocated_model_ids_this_phase: tuple[str, ...] | None = None,
        overrun_pile_in_completed_activation_result_ids: tuple[str, ...] | None = None,
    ) -> Self:
        next_pile_in_state = self.pile_in_state if pile_in_state is _UNSET else pile_in_state
        next_consolidate_state = (
            self.consolidate_state if consolidate_state is _UNSET else consolidate_state
        )
        next_active_activation = (
            self.active_activation if active_activation is _UNSET else active_activation
        )
        next_pending_completed_attack_sequence = (
            self.pending_completed_attack_sequence
            if pending_completed_attack_sequence is _UNSET
            else pending_completed_attack_sequence
        )
        next_attack_sequence = (
            self.attack_sequence if attack_sequence is _UNSET else attack_sequence
        )
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            current_step=self.current_step if current_step is None else current_step,
            step_states=self.step_states if step_states is None else step_states,
            pile_in_state=cast(FightMovementStepState | None, next_pile_in_state),
            consolidate_state=cast(FightMovementStepState | None, next_consolidate_state),
            fight_order_state=(
                self.fight_order_state if fight_order_state is None else fight_order_state
            ),
            active_activation=cast(FightActivationSelection | None, next_active_activation),
            pending_completed_attack_sequence=cast(
                AttackSequence | None,
                next_pending_completed_attack_sequence,
            ),
            attack_sequence=cast(AttackSequence | None, next_attack_sequence),
            allocated_model_ids_this_phase=(
                self.allocated_model_ids_this_phase
                if allocated_model_ids_this_phase is None
                else allocated_model_ids_this_phase
            ),
            overrun_pile_in_completed_activation_result_ids=(
                self.overrun_pile_in_completed_activation_result_ids
                if overrun_pile_in_completed_activation_result_ids is None
                else overrun_pile_in_completed_activation_result_ids
            ),
            phase_complete=False,
            forced_activation_context=self.forced_activation_context,
            suspended_state=self.suspended_state,
        )

    def to_payload(self) -> FightPhaseStatePayload:
        payload: FightPhaseStatePayload = {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "current_step": self.current_step.value,
            "step_states": [step.to_payload() for step in self.step_states],
            "pile_in_state": None
            if self.pile_in_state is None
            else self.pile_in_state.to_payload(),
            "consolidate_state": (
                None if self.consolidate_state is None else self.consolidate_state.to_payload()
            ),
            "fight_order_state": self.fight_order_state.to_payload(),
            "active_activation": (
                None if self.active_activation is None else self.active_activation.to_payload()
            ),
            "attack_sequence": (
                None if self.attack_sequence is None else self.attack_sequence.to_payload()
            ),
            "allocated_model_ids_this_phase": list(self.allocated_model_ids_this_phase),
            "overrun_pile_in_completed_activation_result_ids": list(
                self.overrun_pile_in_completed_activation_result_ids
            ),
            "phase_complete": self.phase_complete,
        }
        if self.pending_completed_attack_sequence is not None:
            payload["pending_completed_attack_sequence"] = (
                self.pending_completed_attack_sequence.to_payload()
            )
        if self.forced_activation_context is not None:
            payload["forced_activation_context"] = self.forced_activation_context.to_payload()
        if self.suspended_state is not None:
            payload["suspended_state"] = self.suspended_state.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: FightPhaseStatePayload) -> Self:
        suspended = payload.get("suspended_state")
        if suspended is not None and "suspended_state" in suspended:
            raise GameLifecycleError("Nested suspended Fight state is forbidden.")
        return cls(
            suspended_state=None if suspended is None else FightPhaseState.from_payload(suspended),
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            current_step=fight_phase_step_kind_from_token(payload["current_step"]),
            step_states=tuple(FightStepState.from_payload(step) for step in payload["step_states"]),
            pile_in_state=(
                None
                if payload["pile_in_state"] is None
                else FightMovementStepState.from_payload(payload["pile_in_state"])
            ),
            consolidate_state=(
                None
                if payload["consolidate_state"] is None
                else FightMovementStepState.from_payload(payload["consolidate_state"])
            ),
            fight_order_state=FightOrderState.from_payload(payload["fight_order_state"]),
            active_activation=(
                None
                if payload["active_activation"] is None
                else FightActivationSelection.from_payload(payload["active_activation"])
            ),
            pending_completed_attack_sequence=(
                None
                if (completed_payload := payload.get("pending_completed_attack_sequence")) is None
                else AttackSequence.from_payload(completed_payload)
            ),
            attack_sequence=(
                None
                if payload["attack_sequence"] is None
                else AttackSequence.from_payload(payload["attack_sequence"])
            ),
            allocated_model_ids_this_phase=tuple(payload["allocated_model_ids_this_phase"]),
            overrun_pile_in_completed_activation_result_ids=tuple(
                payload["overrun_pile_in_completed_activation_result_ids"]
            ),
            phase_complete=payload["phase_complete"],
            forced_activation_context=(
                None
                if (forced_payload := payload.get("forced_activation_context")) is None
                else ForcedFightActivationContext.from_payload(forced_payload)
            ),
        )


def eligible_fight_contexts_for_player(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    player_id: str,
    policy: FightPolicyDescriptor,
) -> tuple[FightEligibilityContext, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    forced_context = fight_state.forced_activation_context
    if forced_context is not None and requested_player_id != forced_context.selecting_player_id:
        return ()
    if state.army_definition_for_player(requested_player_id) is None:
        raise GameLifecycleError("Fight phase requires mustered army definitions.")
    placed_rules_units = fight_present_rules_unit_views(state=state)
    player_rules_units = tuple(
        rules_unit
        for rules_unit in placed_rules_units
        if rules_unit.owner_player_id == requested_player_id
    )
    contexts: list[FightEligibilityContext] = []
    for rules_unit in player_rules_units:
        unit_id = rules_unit.unit_instance_id
        if forced_context is not None and not rules_unit_identity_history_contains(
            state=state,
            identity_ids=forced_context.eligible_unit_instance_ids,
            unit_instance_id=unit_id,
        ):
            continue
        if rules_unit_identity_history_contains(
            state=state,
            identity_ids=fight_state.fight_order_state.selected_to_fight_unit_ids,
            unit_instance_id=rules_unit.unit_instance_id,
        ):
            continue
        reasons = _fight_eligibility_reasons_for_rules_unit(
            state=state,
            fight_state=fight_state,
            rules_unit=rules_unit,
            policy=policy,
        )
        if not reasons:
            continue
        band = fight_state.current_ordering_band
        has_fights_first = fight_state.fight_order_state.fights_first_registry.has_unit_lineage(
            state=state,
            unit_instance_id=unit_id,
        )
        if forced_context is None:
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
                    rules_unit=rules_unit,
                ),
                pass_distance_inches=policy.eligible_pass_distance_inches,
            )
        )
    return tuple(sorted(contexts, key=lambda context: context.unit_instance_id))


def unit_is_currently_engaged(*, state: GameState, unit_instance_id: str) -> bool:
    """Return current Engagement Range state for the whole attached rules unit."""
    return current_rules_unit_is_physically_engaged(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )


def eligible_pass_is_available(contexts: tuple[FightEligibilityContext, ...]) -> bool:
    if not contexts:
        return False
    return all(context.more_than_pass_distance_from_all_enemies for context in contexts)


def legal_fight_types_for_context(
    *,
    context: FightEligibilityContext,
    policy: FightPolicyDescriptor,
) -> tuple[FightTypeKind, ...]:
    types: list[FightTypeKind] = []
    currently_engaged = FightEligibilityKind.CURRENTLY_ENGAGED in context.eligibility_reasons
    engaged_at_step_start = (
        FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START in context.eligibility_reasons
    )
    if FightTypeKind.NORMAL in policy.fight_types and currently_engaged:
        types.append(FightTypeKind.NORMAL)
    if FightTypeKind.OVERRUN in policy.fight_types and (
        not currently_engaged or not engaged_at_step_start
    ):
        types.append(FightTypeKind.OVERRUN)
    return tuple(types)


def engaged_unit_ids_at_fight_start(
    *,
    state: GameState,
    policy: FightPolicyDescriptor,
) -> tuple[str, ...]:
    del policy
    placed_rules_units = fight_present_rules_unit_views(state=state)
    engaged: set[str] = set()
    for rules_unit in placed_rules_units:
        if _unit_is_engaged(
            state=state,
            rules_unit=rules_unit,
        ):
            engaged.add(rules_unit.unit_instance_id)
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
    payload: dict[str, JsonValue] = {
        "submission_kind": "select_fight_activation",
        "game_id": state.game_id,
        "battle_round": fight_state.battle_round,
        "phase": BattlePhaseKind.FIGHT.value,
        "player_id": context.player_id,
        "active_player_id": fight_state.active_player_id,
        "unit_instance_id": context.unit_instance_id,
        "ordering_band": context.ordering_band.value,
        "fight_type": fight_type_value.value,
        "eligibility_context": validate_json_value(context.to_payload()),
    }
    if fight_state.forced_activation_context is not None:
        payload["forced_activation_context"] = validate_json_value(
            fight_state.forced_activation_context.to_payload()
        )
    return validate_json_value(payload)


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
            "battle_round": fight_state.battle_round,
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


def fight_eligibility_reasons_for_unit(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    unit_instance_id: str,
    policy: FightPolicyDescriptor,
) -> tuple[FightEligibilityKind, ...]:
    requested_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return _fight_eligibility_reasons_for_rules_unit(
        state=state,
        fight_state=fight_state,
        rules_unit=requested_rules_unit,
        policy=policy,
    )


def _fight_eligibility_reasons_for_rules_unit(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    rules_unit: RulesUnitView,
    policy: FightPolicyDescriptor,
) -> tuple[FightEligibilityKind, ...]:
    reasons: list[FightEligibilityKind] = []
    if (
        FightEligibilityKind.CHARGED_THIS_TURN in policy.eligibility_kinds
        and fight_state.fight_order_state.fights_first_registry.has_unit_lineage(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
            effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        )
    ):
        reasons.append(FightEligibilityKind.CHARGED_THIS_TURN)
    if (
        FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START in policy.eligibility_kinds
        and rules_unit_identity_history_contains(
            state=state,
            identity_ids=fight_state.fight_order_state.engaged_at_fight_step_start_unit_ids,
            unit_instance_id=rules_unit.unit_instance_id,
        )
    ):
        reasons.append(FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START)
    if FightEligibilityKind.CURRENTLY_ENGAGED in policy.eligibility_kinds and _unit_is_engaged(
        state=state,
        rules_unit=rules_unit,
    ):
        reasons.append(FightEligibilityKind.CURRENTLY_ENGAGED)
    forced = fight_state.forced_activation_context
    if forced is not None and rules_unit_identity_history_contains(
        state=state,
        identity_ids=forced.eligible_unit_instance_ids,
        unit_instance_id=rules_unit.unit_instance_id,
    ):
        reasons.append(FightEligibilityKind.FORCED_ACTIVATION)
    return tuple(reasons)


def _unit_is_engaged(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> bool:
    return current_rules_unit_is_physically_engaged(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    )


def _closest_enemy_distance_inches(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> float | None:
    return current_closest_physical_enemy_distance_inches(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


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
    return validate_positive_int(key, payload.get(key))


def _payload_positive_float(payload: dict[str, JsonValue], *, key: str) -> float:
    return validate_positive_float(key, payload.get(key))
