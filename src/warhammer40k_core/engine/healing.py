from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import healing_source_context as hctx
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
)
from warhammer40k_core.engine.damage_allocation import model_by_id, unit_owner_player_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

SELECT_HEALING_MODEL_DECISION_TYPE = "select_healing_model"
CORE_HEALING_RULE_ID = "core_rules_healing"


class HealingStepKind(StrEnum):
    HEAL_WOUND = "heal_wound"
    REVIVE_MODEL = "revive_model"
    NO_EFFECT = "no_effect"


class HealingStepPayload(TypedDict):
    step_index: int
    step_kind: str
    model_instance_id: str | None
    starting_wounds_remaining: int | None
    final_wounds_remaining: int | None
    request_id: str | None
    result_id: str | None
    transition_batch: BattlefieldTransitionBatchPayload | None


class HealingEffectPayload(TypedDict):
    effect_id: str
    target_unit_instance_id: str
    amount: int
    opposing_player_id: str
    selection_actor_player_id: str | None
    source_rule_id: str
    source_context: JsonValue
    phase_start_model_ids: list[str]
    phase_start_enemy_engagement_model_ids: list[str]
    resolved_steps: list[HealingStepPayload]


class HealingSelectionPayload(TypedDict):
    submission_kind: str
    selection_kind: str
    effect_id: str
    target_unit_instance_id: str
    step_index: int
    model_instance_id: str
    legal_model_ids: list[str]
    source_rule_id: str
    source_context: JsonValue


@dataclass(frozen=True, slots=True)
class HealingStep:
    step_index: int
    step_kind: HealingStepKind
    model_instance_id: str | None
    starting_wounds_remaining: int | None
    final_wounds_remaining: int | None
    request_id: str | None = None
    result_id: str | None = None
    transition_batch: BattlefieldTransitionBatch | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_index",
            _validate_positive_int("HealingStep step_index", self.step_index),
        )
        object.__setattr__(self, "step_kind", healing_step_kind_from_token(self.step_kind))
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "HealingStep model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "starting_wounds_remaining",
            _validate_optional_non_negative_int(
                "HealingStep starting_wounds_remaining",
                self.starting_wounds_remaining,
            ),
        )
        object.__setattr__(
            self,
            "final_wounds_remaining",
            _validate_optional_non_negative_int(
                "HealingStep final_wounds_remaining",
                self.final_wounds_remaining,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_optional_identifier("HealingStep request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_optional_identifier("HealingStep result_id", self.result_id),
        )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "HealingStep transition_batch must be a BattlefieldTransitionBatch."
            )
        if self.step_kind is HealingStepKind.NO_EFFECT:
            if self.model_instance_id is not None:
                raise GameLifecycleError("No-effect HealingStep must not select a model.")
            if (
                self.starting_wounds_remaining is not None
                or self.final_wounds_remaining is not None
            ):
                raise GameLifecycleError("No-effect HealingStep must not include wounds.")
            if self.transition_batch is not None:
                raise GameLifecycleError("No-effect HealingStep must not include placement.")
            return
        if self.model_instance_id is None:
            raise GameLifecycleError("HealingStep must select a model.")
        if self.starting_wounds_remaining is None or self.final_wounds_remaining is None:
            raise GameLifecycleError("HealingStep must include wound transition state.")
        if self.step_kind is HealingStepKind.HEAL_WOUND and self.transition_batch is not None:
            raise GameLifecycleError("Heal-wound HealingStep must not include placement.")
        if self.step_kind is HealingStepKind.REVIVE_MODEL and self.transition_batch is None:
            raise GameLifecycleError("Revive-model HealingStep requires placement.")

    def to_payload(self) -> HealingStepPayload:
        return {
            "step_index": self.step_index,
            "step_kind": self.step_kind.value,
            "model_instance_id": self.model_instance_id,
            "starting_wounds_remaining": self.starting_wounds_remaining,
            "final_wounds_remaining": self.final_wounds_remaining,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "transition_batch": (
                None if self.transition_batch is None else self.transition_batch.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: HealingStepPayload) -> Self:
        transition_payload = payload["transition_batch"]
        return cls(
            step_index=payload["step_index"],
            step_kind=healing_step_kind_from_token(payload["step_kind"]),
            model_instance_id=payload["model_instance_id"],
            starting_wounds_remaining=payload["starting_wounds_remaining"],
            final_wounds_remaining=payload["final_wounds_remaining"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            transition_batch=(
                None
                if transition_payload is None
                else BattlefieldTransitionBatch.from_payload(transition_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class HealingEffect:
    effect_id: str
    target_unit_instance_id: str
    amount: int
    opposing_player_id: str
    selection_actor_player_id: str | None = None
    source_rule_id: str = CORE_HEALING_RULE_ID
    source_context: JsonValue = None
    phase_start_model_ids: tuple[str, ...] = ()
    phase_start_enemy_engagement_model_ids: tuple[str, ...] = ()
    resolved_steps: tuple[HealingStep, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _validate_identifier("effect_id", self.effect_id))
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(self, "amount", _validate_positive_int("amount", self.amount))
        object.__setattr__(
            self,
            "opposing_player_id",
            _validate_identifier("opposing_player_id", self.opposing_player_id),
        )
        object.__setattr__(
            self,
            "selection_actor_player_id",
            _validate_optional_identifier(
                "selection_actor_player_id",
                self.selection_actor_player_id,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(self, "source_context", validate_json_value(self.source_context))
        object.__setattr__(
            self,
            "phase_start_model_ids",
            _validate_identifier_tuple(
                "phase_start_model_ids",
                self.phase_start_model_ids,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "phase_start_enemy_engagement_model_ids",
            _validate_identifier_tuple(
                "phase_start_enemy_engagement_model_ids",
                self.phase_start_enemy_engagement_model_ids,
                min_length=0,
            ),
        )
        if type(self.resolved_steps) is not tuple:
            raise GameLifecycleError("HealingEffect resolved_steps must be a tuple.")
        steps = tuple(_validate_healing_step(value) for value in self.resolved_steps)
        expected_indexes = tuple(range(1, len(steps) + 1))
        if tuple(step.step_index for step in steps) != expected_indexes:
            raise GameLifecycleError("HealingEffect resolved_steps must be sequential.")
        if len(steps) > self.amount:
            raise GameLifecycleError("HealingEffect resolved_steps exceed amount.")
        object.__setattr__(self, "resolved_steps", steps)

    def is_complete(self) -> bool:
        return len(self.resolved_steps) == self.amount

    def next_step_index(self) -> int:
        if self.is_complete():
            raise GameLifecycleError("HealingEffect is already complete.")
        return len(self.resolved_steps) + 1

    def with_step(self, step: HealingStep) -> Self:
        if type(step) is not HealingStep:
            raise GameLifecycleError("HealingEffect step must be a HealingStep.")
        if step.step_index != self.next_step_index():
            raise GameLifecycleError("HealingEffect step_index drift.")
        return type(self)(
            effect_id=self.effect_id,
            target_unit_instance_id=self.target_unit_instance_id,
            amount=self.amount,
            opposing_player_id=self.opposing_player_id,
            selection_actor_player_id=self.selection_actor_player_id,
            source_rule_id=self.source_rule_id,
            source_context=self.source_context,
            phase_start_model_ids=self.phase_start_model_ids,
            phase_start_enemy_engagement_model_ids=self.phase_start_enemy_engagement_model_ids,
            resolved_steps=(*self.resolved_steps, step),
        )

    def to_payload(self) -> HealingEffectPayload:
        return {
            "effect_id": self.effect_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "amount": self.amount,
            "opposing_player_id": self.opposing_player_id,
            "selection_actor_player_id": self.selection_actor_player_id,
            "source_rule_id": self.source_rule_id,
            "source_context": self.source_context,
            "phase_start_model_ids": list(self.phase_start_model_ids),
            "phase_start_enemy_engagement_model_ids": list(
                self.phase_start_enemy_engagement_model_ids
            ),
            "resolved_steps": [step.to_payload() for step in self.resolved_steps],
        }

    @classmethod
    def from_payload(cls, payload: HealingEffectPayload) -> Self:
        return cls(
            effect_id=payload["effect_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            amount=payload["amount"],
            opposing_player_id=payload["opposing_player_id"],
            selection_actor_player_id=payload["selection_actor_player_id"],
            source_rule_id=payload["source_rule_id"],
            source_context=payload["source_context"],
            phase_start_model_ids=tuple(payload["phase_start_model_ids"]),
            phase_start_enemy_engagement_model_ids=tuple(
                payload["phase_start_enemy_engagement_model_ids"]
            ),
            resolved_steps=tuple(
                HealingStep.from_payload(step) for step in payload["resolved_steps"]
            ),
        )


@dataclass(frozen=True, slots=True)
class HealingModelSelection:
    request_id: str
    result_id: str
    player_id: str
    selection_kind: HealingStepKind
    effect_id: str
    target_unit_instance_id: str
    step_index: int
    selected_model_id: str
    legal_model_ids: tuple[str, ...]
    source_rule_id: str
    source_context: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("HealingModelSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("HealingModelSelection result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("HealingModelSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "selection_kind",
            healing_step_kind_from_token(self.selection_kind),
        )
        if self.selection_kind is HealingStepKind.NO_EFFECT:
            raise GameLifecycleError("HealingModelSelection cannot select no_effect.")
        object.__setattr__(
            self,
            "effect_id",
            _validate_identifier("HealingModelSelection effect_id", self.effect_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "HealingModelSelection target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "step_index",
            _validate_positive_int("HealingModelSelection step_index", self.step_index),
        )
        object.__setattr__(
            self,
            "selected_model_id",
            _validate_identifier(
                "HealingModelSelection selected_model_id",
                self.selected_model_id,
            ),
        )
        object.__setattr__(
            self,
            "legal_model_ids",
            _validate_identifier_tuple(
                "HealingModelSelection legal_model_ids",
                self.legal_model_ids,
                min_length=1,
            ),
        )
        if self.selected_model_id not in self.legal_model_ids:
            raise GameLifecycleError("HealingModelSelection selected model is not legal.")
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("HealingModelSelection source_rule_id", self.source_rule_id),
        )
        object.__setattr__(self, "source_context", validate_json_value(self.source_context))

    @classmethod
    def from_result(cls, *, request: DecisionRequest, result: DecisionResult) -> Self:
        if request.decision_type != SELECT_HEALING_MODEL_DECISION_TYPE:
            raise GameLifecycleError("Healing model selection requires a healing request.")
        result.validate_for_request(request)
        payload = _healing_selection_payload(result.payload)
        return cls(
            request_id=result.request_id,
            result_id=result.result_id,
            player_id=_require_actor_id(result.actor_id),
            selection_kind=healing_step_kind_from_token(payload["selection_kind"]),
            effect_id=payload["effect_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            step_index=payload["step_index"],
            selected_model_id=payload["model_instance_id"],
            legal_model_ids=tuple(payload["legal_model_ids"]),
            source_rule_id=payload["source_rule_id"],
            source_context=payload["source_context"],
        )


@dataclass(frozen=True, slots=True)
class _HealingStepCandidates:
    step_kind: HealingStepKind
    model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_kind", healing_step_kind_from_token(self.step_kind))
        object.__setattr__(
            self,
            "model_ids",
            _validate_identifier_tuple(
                "_HealingStepCandidates model_ids",
                self.model_ids,
                min_length=0,
            ),
        )
        if self.step_kind is HealingStepKind.NO_EFFECT and self.model_ids:
            raise GameLifecycleError("No-effect healing candidates must not include models.")
        if self.step_kind is not HealingStepKind.NO_EFFECT and not self.model_ids:
            raise GameLifecycleError("Healing candidates require models.")


def resolve_healing_until_blocked(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
) -> tuple[HealingEffect, DecisionRequest | None]:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Healing resolution requires a DecisionController.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Healing resolution requires a RulesetDescriptor.")
    _validate_effect_for_state(state=state, effect=effect)
    current = effect
    while not current.is_complete():
        candidates = _healing_candidates_for_next_step(state=state, effect=current)
        if candidates.step_kind is HealingStepKind.REVIVE_MODEL and len(candidates.model_ids) == 1:
            from warhammer40k_core.engine.healing_revival import (
                request_healing_revival_placement,
            )

            return current, request_healing_revival_placement(
                state=state,
                decisions=decisions,
                effect=current,
                model_instance_id=candidates.model_ids[0],
                source_selection_request_id=None,
                source_selection_result_id=None,
            )
        if len(candidates.model_ids) > 1:
            return current, _build_healing_model_request(
                state=state,
                decisions=decisions,
                effect=current,
                candidates=candidates,
            )
        step = _apply_forced_healing_step(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            effect=current,
            candidates=candidates,
        )
        current = current.with_step(step)
        _emit_healing_step(decisions=decisions, effect=current, step=step)
    decisions.event_log.append(
        "healing_resolved",
        {
            "effect": validate_json_value(current.to_payload()),
            "completed": True,
        },
    )
    return current, None


def apply_healing_model_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    result: DecisionResult,
) -> tuple[HealingEffect, DecisionRequest | None]:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Healing decision application requires a DecisionController.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Healing decision application requires a RulesetDescriptor.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Healing decision application requires a DecisionResult.")
    _validate_effect_for_state(state=state, effect=effect)
    pending_request = decisions.queue.peek_next()
    request_effect = healing_effect_from_request(request=pending_request)
    if request_effect.to_payload() != effect.to_payload():
        raise GameLifecycleError("Healing request effect drift.")
    _validated_healing_selection(
        state=state,
        request=pending_request,
        result=result,
        effect=effect,
    )
    decisions.submit_result(result)
    return apply_recorded_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        request=pending_request,
        result=result,
        effect=effect,
    )


def apply_recorded_healing_model_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    request: DecisionRequest,
    result: DecisionResult,
    effect: HealingEffect | None = None,
) -> tuple[HealingEffect, DecisionRequest | None]:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Healing decision application requires a DecisionController.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Healing decision application requires a RulesetDescriptor.")
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Healing decision application requires a DecisionRequest.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Healing decision application requires a DecisionResult.")
    decisions.record_for_result(result)
    request_effect = healing_effect_from_request(request=request)
    active_effect = request_effect if effect is None else effect
    if request_effect.to_payload() != active_effect.to_payload():
        raise GameLifecycleError("Healing request effect drift.")
    _validate_effect_for_state(state=state, effect=active_effect)
    selection, candidates = _validated_healing_selection(
        state=state,
        request=request,
        result=result,
        effect=active_effect,
    )
    if selection.selection_kind is HealingStepKind.REVIVE_MODEL:
        from warhammer40k_core.engine.healing_revival import (
            request_healing_revival_placement,
        )

        return active_effect, request_healing_revival_placement(
            state=state,
            decisions=decisions,
            effect=active_effect,
            model_instance_id=selection.selected_model_id,
            source_selection_request_id=request.request_id,
            source_selection_result_id=result.result_id,
        )
    step = _apply_selected_healing_step(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        effect=active_effect,
        candidates=candidates,
        selection=selection,
    )
    updated = active_effect.with_step(step)
    _emit_healing_step(decisions=decisions, effect=updated, step=step)
    return resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        effect=updated,
    )


def healing_effect_from_request(*, request: DecisionRequest) -> HealingEffect:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Healing effect routing requires a DecisionRequest.")
    if request.decision_type != SELECT_HEALING_MODEL_DECISION_TYPE:
        raise GameLifecycleError("Healing effect routing requires a healing request.")
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Healing request payload must be an object.")
    effect_payload = payload.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Healing request payload missing effect.")
    return HealingEffect.from_payload(cast(HealingEffectPayload, effect_payload))


def healing_revival_candidate_model_ids(
    *,
    state: GameState,
    effect: HealingEffect,
) -> tuple[str, ...]:
    candidates = _healing_candidates_for_next_step(state=state, effect=effect)
    if candidates.step_kind is not HealingStepKind.REVIVE_MODEL:
        raise GameLifecycleError("Healing effect does not currently permit revival.")
    return candidates.model_ids


def invalid_healing_model_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Healing decision validation requires a DecisionRequest.")
    if request.decision_type != SELECT_HEALING_MODEL_DECISION_TYPE:
        raise GameLifecycleError("Healing decision validation requires a healing request.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Healing decision validation requires a DecisionResult.")
    invalid_reason = "invalid_healing_model_selection_result"
    finite_status = _invalid_finite_healing_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason=invalid_reason,
    )
    if finite_status is not None:
        return finite_status
    effect = healing_effect_from_request(request=request)
    _validate_effect_for_state(state=state, effect=effect)
    selection = HealingModelSelection.from_result(request=request, result=result)
    stale_field = _healing_selection_stale_field(
        state=state,
        selection=selection,
        effect=effect,
    )
    if stale_field is not None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Healing model selection no longer matches state.",
            payload={"invalid_reason": invalid_reason, "field": stale_field},
        )
    return None


def healing_step_kind_from_token(token: object) -> HealingStepKind:
    if type(token) is HealingStepKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("HealingStepKind token must be a string.")
    try:
        return HealingStepKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported HealingStepKind token: {token}.") from exc


def _healing_candidates_for_next_step(
    *,
    state: GameState,
    effect: HealingEffect,
) -> _HealingStepCandidates:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=effect.target_unit_instance_id,
    )
    wounded_model_ids = hctx.selected_wounded_healing_model_ids(
        effect.source_context,
        effect.resolved_steps,
        HealingStepKind.HEAL_WOUND,
        rules_unit.own_models,
        _rules_unit_allows_multiple_wounded_healing(rules_unit),
    )
    if wounded_model_ids:
        return _HealingStepCandidates(
            step_kind=HealingStepKind.HEAL_WOUND, model_ids=wounded_model_ids
        )
    if hctx.healing_source_context_bool(effect.source_context, "heal_wounded_models_only"):
        return _HealingStepCandidates(step_kind=HealingStepKind.NO_EFFECT)
    starting_strength = state.starting_strength_record_for_unit(rules_unit.unit_instance_id)
    alive_count = len(tuple(model for model in rules_unit.own_models if model.is_alive))
    if alive_count >= starting_strength.starting_model_count:
        return _HealingStepCandidates(step_kind=HealingStepKind.NO_EFFECT)
    battlefield = _battlefield_state(state)
    removed_ids = set(battlefield.removed_model_ids)
    missing_model_ids = tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.own_models
            if not model.is_alive and model.model_instance_id in removed_ids
        )
    )
    if not missing_model_ids:
        raise GameLifecycleError(
            "Healing cannot revive a below-starting-strength unit without removed models."
        )
    return _HealingStepCandidates(
        step_kind=HealingStepKind.REVIVE_MODEL,
        model_ids=missing_model_ids,
    )


def _build_healing_model_request(
    *,
    state: GameState,
    decisions: DecisionController,
    effect: HealingEffect,
    candidates: _HealingStepCandidates,
) -> DecisionRequest:
    if candidates.step_kind is HealingStepKind.NO_EFFECT:
        raise GameLifecycleError("No-effect healing must not request a model selection.")
    step_index = effect.next_step_index()
    options = tuple(
        DecisionOption(
            option_id=_healing_option_id(
                effect_id=effect.effect_id,
                step_index=step_index,
                model_instance_id=model_id,
            ),
            label=_healing_option_label(
                state=state,
                step_kind=candidates.step_kind,
                model_instance_id=model_id,
            ),
            payload=validate_json_value(
                _healing_selection_payload_for_model(
                    effect=effect,
                    step_kind=candidates.step_kind,
                    step_index=step_index,
                    model_id=model_id,
                    legal_model_ids=candidates.model_ids,
                )
            ),
        )
        for model_id in candidates.model_ids
    )
    request = DecisionRequest(
        request_id=f"{effect.effect_id}:healing-step-{step_index:03d}",
        decision_type=SELECT_HEALING_MODEL_DECISION_TYPE,
        actor_id=healing_selection_actor_player_id(effect),
        payload=validate_json_value(
            {
                "selection_kind": candidates.step_kind.value,
                "effect": effect.to_payload(),
                "step_index": step_index,
                "legal_model_ids": list(candidates.model_ids),
            }
        ),
        options=options,
    )
    return decisions.request_decision(request)


def _apply_forced_healing_step(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    candidates: _HealingStepCandidates,
) -> HealingStep:
    if candidates.step_kind is HealingStepKind.NO_EFFECT:
        return HealingStep(
            step_index=effect.next_step_index(),
            step_kind=HealingStepKind.NO_EFFECT,
            model_instance_id=None,
            starting_wounds_remaining=None,
            final_wounds_remaining=None,
        )
    if len(candidates.model_ids) != 1:
        raise GameLifecycleError("Forced healing step requires exactly one model.")
    if candidates.step_kind is HealingStepKind.REVIVE_MODEL:
        raise GameLifecycleError("Healing revival requires a placement decision.")
    return _apply_healing_step_to_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        effect=effect,
        step_kind=candidates.step_kind,
        model_instance_id=candidates.model_ids[0],
        request_id=None,
        result_id=None,
    )


def _apply_selected_healing_step(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    candidates: _HealingStepCandidates,
    selection: HealingModelSelection,
) -> HealingStep:
    if selection.selected_model_id not in candidates.model_ids:
        raise GameLifecycleError("Healing selected model is not legal.")
    if selection.selection_kind is HealingStepKind.REVIVE_MODEL:
        raise GameLifecycleError("Healing revival requires a placement decision.")
    return _apply_healing_step_to_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        effect=effect,
        step_kind=selection.selection_kind,
        model_instance_id=selection.selected_model_id,
        request_id=selection.request_id,
        result_id=selection.result_id,
    )


def _apply_healing_step_to_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    effect: HealingEffect,
    step_kind: HealingStepKind,
    model_instance_id: str,
    request_id: str | None,
    result_id: str | None,
) -> HealingStep:
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if step_kind is HealingStepKind.HEAL_WOUND:
        if not model.is_alive or model.wounds_remaining >= model.starting_wounds:
            raise GameLifecycleError("Healing selected model is not wounded.")
        final_wounds = model.wounds_remaining + 1
        _replace_model_wounds(
            state=state,
            model_instance_id=model_instance_id,
            wounds_remaining=final_wounds,
        )
        return HealingStep(
            step_index=effect.next_step_index(),
            step_kind=HealingStepKind.HEAL_WOUND,
            model_instance_id=model_instance_id,
            starting_wounds_remaining=model.wounds_remaining,
            final_wounds_remaining=final_wounds,
            request_id=request_id,
            result_id=result_id,
        )
    raise GameLifecycleError("Unsupported selected healing step kind.")


def _validate_effect_for_state(*, state: GameState, effect: HealingEffect) -> None:
    if type(effect) is not HealingEffect:
        raise GameLifecycleError("Healing resolution requires a HealingEffect.")
    if effect.opposing_player_id not in state.player_ids:
        raise GameLifecycleError("Healing opposing player is not in this game.")
    if (
        effect.selection_actor_player_id is not None
        and effect.selection_actor_player_id not in state.player_ids
    ):
        raise GameLifecycleError("Healing selection actor is not in this game.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=effect.target_unit_instance_id,
    )
    if (
        rules_unit.is_attached_rules_unit
        and effect.target_unit_instance_id != rules_unit.unit_instance_id
    ):
        raise GameLifecycleError(
            "Healing an active attached unit must target the attached-unit identity."
        )
    owner = unit_owner_player_id(state=state, unit_instance_id=effect.target_unit_instance_id)
    if effect.opposing_player_id == owner:
        raise GameLifecycleError("Healing opposing player cannot control the target unit.")


def healing_selection_actor_player_id(effect: HealingEffect) -> str:
    if type(effect) is not HealingEffect:
        raise GameLifecycleError("Healing selection actor lookup requires a HealingEffect.")
    if effect.selection_actor_player_id is not None:
        return effect.selection_actor_player_id
    return effect.opposing_player_id


def _validate_selection_matches_effect(
    *,
    selection: HealingModelSelection,
    effect: HealingEffect,
) -> None:
    if selection.effect_id != effect.effect_id:
        raise GameLifecycleError("Healing selection effect_id drift.")
    if selection.target_unit_instance_id != effect.target_unit_instance_id:
        raise GameLifecycleError("Healing selection target_unit_instance_id drift.")
    if selection.step_index != effect.next_step_index():
        raise GameLifecycleError("Healing selection step_index drift.")
    if selection.source_rule_id != effect.source_rule_id:
        raise GameLifecycleError("Healing selection source_rule_id drift.")
    if selection.source_context != effect.source_context:
        raise GameLifecycleError("Healing selection source_context drift.")


def _validated_healing_selection(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    effect: HealingEffect,
) -> tuple[HealingModelSelection, _HealingStepCandidates]:
    result.validate_for_request(request)
    selection = HealingModelSelection.from_result(request=request, result=result)
    _validate_selection_matches_effect(selection=selection, effect=effect)
    candidates = _healing_candidates_for_next_step(state=state, effect=effect)
    if selection.selection_kind is not candidates.step_kind:
        raise GameLifecycleError("Healing model selection kind is stale.")
    if selection.legal_model_ids != candidates.model_ids:
        raise GameLifecycleError("Healing model legal candidates are stale.")
    if selection.selected_model_id not in candidates.model_ids:
        raise GameLifecycleError("Healing model selection is no longer legal.")
    return selection, candidates


def _healing_selection_stale_field(
    *,
    state: GameState,
    selection: HealingModelSelection,
    effect: HealingEffect,
) -> str | None:
    if selection.effect_id != effect.effect_id:
        return "effect_id"
    if selection.target_unit_instance_id != effect.target_unit_instance_id:
        return "target_unit_instance_id"
    if selection.step_index != effect.next_step_index():
        return "step_index"
    if selection.source_rule_id != effect.source_rule_id:
        return "source_rule_id"
    if selection.source_context != effect.source_context:
        return "source_context"
    candidates = _healing_candidates_for_next_step(state=state, effect=effect)
    if selection.selection_kind is not candidates.step_kind:
        return "selection_kind"
    if selection.legal_model_ids != candidates.model_ids:
        return "legal_model_ids"
    if selection.selected_model_id not in candidates.model_ids:
        return "model_instance_id"
    return None


def _invalid_finite_healing_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending healing request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending healing request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending healing request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending for healing.",
            payload={"invalid_reason": invalid_reason, "field": "selected_option_id"},
        )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the selected healing option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _healing_selection_payload_for_model(
    *,
    effect: HealingEffect,
    step_kind: HealingStepKind,
    step_index: int,
    model_id: str,
    legal_model_ids: tuple[str, ...],
) -> HealingSelectionPayload:
    return {
        "submission_kind": SELECT_HEALING_MODEL_DECISION_TYPE,
        "selection_kind": step_kind.value,
        "effect_id": effect.effect_id,
        "target_unit_instance_id": effect.target_unit_instance_id,
        "step_index": step_index,
        "model_instance_id": model_id,
        "legal_model_ids": list(legal_model_ids),
        "source_rule_id": effect.source_rule_id,
        "source_context": effect.source_context,
    }


def _healing_selection_payload(payload: JsonValue) -> HealingSelectionPayload:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Healing selection payload must be an object.")
    raw = payload
    if raw.get("submission_kind") != SELECT_HEALING_MODEL_DECISION_TYPE:
        raise GameLifecycleError("Healing selection payload submission_kind drift.")
    legal_model_ids = raw.get("legal_model_ids")
    if not isinstance(legal_model_ids, list):
        raise GameLifecycleError("Healing selection legal_model_ids must be a list.")
    return HealingSelectionPayload(
        submission_kind=_payload_string(raw, key="submission_kind"),
        selection_kind=_payload_string(raw, key="selection_kind"),
        effect_id=_payload_string(raw, key="effect_id"),
        target_unit_instance_id=_payload_string(raw, key="target_unit_instance_id"),
        step_index=_payload_int(raw, key="step_index"),
        model_instance_id=_payload_string(raw, key="model_instance_id"),
        legal_model_ids=[
            _validate_identifier("legal_model_id", value) for value in legal_model_ids
        ],
        source_rule_id=_payload_string(raw, key="source_rule_id"),
        source_context=validate_json_value(raw.get("source_context")),
    )


def _healing_option_id(
    *,
    effect_id: str,
    step_index: int,
    model_instance_id: str,
) -> str:
    return f"{effect_id}:healing-step-{step_index:03d}:model:{model_instance_id}"


def _healing_option_label(
    *,
    state: GameState,
    step_kind: HealingStepKind,
    model_instance_id: str,
) -> str:
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if step_kind is HealingStepKind.HEAL_WOUND:
        return f"Heal {model.name}"
    if step_kind is HealingStepKind.REVIVE_MODEL:
        return f"Revive {model.name}"
    raise GameLifecycleError("No-effect healing must not build an option label.")


def _emit_healing_step(
    *,
    decisions: DecisionController,
    effect: HealingEffect,
    step: HealingStep,
) -> None:
    decisions.event_log.append(
        "healing_step_resolved",
        {
            "effect_id": effect.effect_id,
            "target_unit_instance_id": effect.target_unit_instance_id,
            "amount": effect.amount,
            "source_rule_id": effect.source_rule_id,
            "source_context": effect.source_context,
            "step": validate_json_value(step.to_payload()),
        },
    )


def _replace_model_wounds(
    *,
    state: GameState,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    state.replace_army_definitions(
        list(
            healing_army_definitions_with_model_wounds(
                armies=tuple(state.army_definitions),
                model_instance_id=model_instance_id,
                wounds_remaining=wounds_remaining,
            )
        )
    )


def healing_army_definitions_with_model_wounds(
    *,
    armies: tuple[ArmyDefinition, ...],
    model_instance_id: str,
    wounds_remaining: int,
) -> tuple[ArmyDefinition, ...]:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in armies:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                did_update = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise GameLifecycleError("Healing cannot update an unknown model.")
    return tuple(updated_armies)


def _unit_is_attached_rules_unit(unit: UnitInstance) -> bool:
    if any(_canonical_keyword(keyword) == "ATTACHED UNIT" for keyword in unit.keywords):
        return True
    return any(
        source_id.startswith(("attached-role:", "runtime-attached-unit:"))
        for model in unit.own_models
        for source_id in model.source_ids
    )


def _rules_unit_allows_multiple_wounded_healing(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Healing rules-unit validation requires a RulesUnitView.")
    if rules_unit.is_attached_rules_unit:
        return True
    return _unit_is_attached_rules_unit(rules_unit.components[0].unit)


def _battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Healing requires battlefield_state.")
    if type(battlefield) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Healing battlefield_state must be a BattlefieldRuntimeState.")
    return battlefield


def _require_actor_id(actor_id: str | None) -> str:
    if actor_id is None:
        raise GameLifecycleError("Healing selection requires an actor.")
    return actor_id


def _validate_healing_step(value: object) -> HealingStep:
    if type(value) is not HealingStep:
        raise GameLifecycleError("HealingEffect resolved_steps must contain HealingStep values.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Healing payload missing required key: {key}.")
    return _validate_identifier(key, payload[key])


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Healing payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Healing payload key must be an integer: {key}.")
    return value


def _canonical_keyword(keyword: str) -> str:
    return keyword.replace("-", " ").replace("_", " ").upper()


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_optional_non_negative_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
