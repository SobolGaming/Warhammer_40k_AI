from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batch_from_event,
    validate_timing_batch_transition,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch


class RuleTriggerKind(StrEnum):
    BATTLE_SHOCK_OUTCOME = "battle_shock_outcome"
    ATTACK_COMPLETION = "attack_completion"
    MOVE_COMPLETION = "move_completion"
    MODEL_DESTRUCTION = "model_destruction"


class RuleTriggerPayload(TypedDict):
    trigger_id: str
    kind: str
    context: JsonValue
    parent_batch_id: str | None
    parent_participant_id: str | None


@dataclass(frozen=True, slots=True)
class RuleTrigger:
    kind: RuleTriggerKind
    context: JsonValue
    parent_batch_id: str | None
    parent_participant_id: str | None

    def __post_init__(self) -> None:
        if type(self.kind) is not RuleTriggerKind:
            raise GameLifecycleError("Rule trigger kind must be typed.")
        if not isinstance(self.context, dict):
            raise GameLifecycleError("Rule trigger context must be an object.")
        object.__setattr__(self, "context", validate_json_value(self.context))
        if (self.parent_batch_id is None) != (self.parent_participant_id is None):
            raise GameLifecycleError("Rule trigger parent requires both batch and rule identity.")
        if self.parent_batch_id is not None:
            validate = IdentifierValidator(GameLifecycleError)
            validate("parent_batch_id", self.parent_batch_id)
            validate("parent_participant_id", self.parent_participant_id)

    @property
    def trigger_id(self) -> str:
        digest = canonical_payload_sha256(cast(dict[str, JsonValue], self.context))
        return f"rule-trigger:{self.kind.value}:{digest}"

    @property
    def conflict_id(self) -> str:
        context = self.context
        if not isinstance(context, dict):
            raise GameLifecycleError("Rule trigger context must be an object.")
        if self.kind is RuleTriggerKind.BATTLE_SHOCK_OUTCOME:
            result = context.get("battle_shock_result")
            if not isinstance(result, dict) or type(result.get("result_id")) is not str:
                raise GameLifecycleError("Battle-shock trigger requires its result identity.")
            return f"battle-shock-outcome:{result['result_id']}"
        if self.kind is RuleTriggerKind.ATTACK_COMPLETION:
            sequence = context.get("attack_sequence")
            if (
                not isinstance(sequence, dict)
                or type(sequence.get("sequence_id")) is not str
                or type(context.get("trigger_event_id")) is not str
            ):
                raise GameLifecycleError(
                    "Attack trigger requires sequence and completion identity."
                )
            return f"attack-completion:{context['trigger_event_id']}:{sequence['sequence_id']}"
        if self.kind is RuleTriggerKind.MODEL_DESTRUCTION:
            if type(context.get("trigger_event_id")) is not str:
                raise GameLifecycleError("Destruction trigger requires its model event identity.")
            return f"model-destruction:{context['trigger_event_id']}"
        if self.kind is RuleTriggerKind.MOVE_COMPLETION:
            if type(context.get("trigger_event_id")) is not str:
                raise GameLifecycleError("Move trigger requires its completion event identity.")
            return f"move-completion:{context['trigger_event_id']}"
        raise GameLifecycleError("Rule trigger has no sequencing context identity.")

    def to_payload(self) -> RuleTriggerPayload:
        return {
            "trigger_id": self.trigger_id,
            "kind": self.kind.value,
            "context": self.context,
            "parent_batch_id": self.parent_batch_id,
            "parent_participant_id": self.parent_participant_id,
        }

    @classmethod
    def from_payload(cls, payload: RuleTriggerPayload) -> Self:
        if set(payload) != {
            "trigger_id",
            "kind",
            "context",
            "parent_batch_id",
            "parent_participant_id",
        }:
            raise GameLifecycleError("Rule trigger payload schema drift.")
        if type(payload["kind"]) is not str:
            raise GameLifecycleError("Rule trigger kind must be a string.")
        try:
            kind = RuleTriggerKind(payload["kind"])
        except ValueError as error:
            raise GameLifecycleError("Rule trigger kind is unsupported.") from error
        trigger = cls(
            kind=kind,
            context=payload["context"],
            parent_batch_id=payload["parent_batch_id"],
            parent_participant_id=payload["parent_participant_id"],
        )
        if trigger.to_payload() != payload:
            raise GameLifecycleError("Rule trigger payload identity drift.")
        return trigger


@dataclass(frozen=True, slots=True)
class RuleTriggerHistory:
    observed: tuple[RuleTrigger, ...]
    released: tuple[str, ...]
    completed: tuple[str, ...]
    batches: tuple[TimingBatch, ...]

    def ready(self) -> tuple[RuleTrigger, ...]:
        completed_batches = {
            batch.batch_id for batch in self.batches if batch.current_batch_complete
        }
        return tuple(
            trigger
            for trigger in self.observed
            if trigger.trigger_id not in self.completed
            and (trigger.parent_batch_id is None or trigger.parent_batch_id in completed_batches)
        )


def rule_trigger_history(decisions: DecisionController) -> RuleTriggerHistory:
    observed: dict[str, RuleTrigger] = {}
    released: list[str] = []
    completed: list[str] = []
    batches: dict[str, TimingBatch] = {}
    contexts: dict[str, dict[int, TimingBatch]] = {}
    for event_index, event in enumerate(decisions.event_log.records):
        if event.event_type == TIMING_BATCH_EVENT_TYPE:
            batch = timing_batch_from_event(event)
            context_batches = contexts.setdefault(batch.context.conflict_id, {})
            if context_batches and next(iter(context_batches.values())).context != batch.context:
                raise GameLifecycleError("Rule trigger timing context authority drifted.")
            validate_timing_batch_transition(
                batch=batch,
                event=event,
                event_index=event_index,
                batches=context_batches,
                events=decisions.event_log.records,
                records=decisions.records,
            )
            context_batches[batch.generation] = batch
            if any(
                observed[identifier].conflict_id == batch.context.conflict_id
                for identifier in completed
            ):
                raise GameLifecycleError("Completed rule trigger reopened its timing batch.")
            if batch.batch_id in batches:
                del batches[batch.batch_id]
            batches[batch.batch_id] = batch
        elif event.event_type == "rule_trigger_observed":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Rule trigger observation requires an object.")
            trigger = RuleTrigger.from_payload(cast(RuleTriggerPayload, event.payload))
            if trigger.trigger_id in observed:
                raise GameLifecycleError("Rule trigger observation is duplicated.")
            selected = tuple(
                batch for batch in batches.values() if batch.selected_participant_id is not None
            )
            if trigger.parent_batch_id is not None:
                parent = batches.get(trigger.parent_batch_id)
                if (
                    parent is None
                    or parent.selected_participant_id != trigger.parent_participant_id
                ):
                    raise GameLifecycleError("Rule trigger lacks its selected parent rule.")
                if not selected or selected[-1] != parent:
                    raise GameLifecycleError("Rule trigger bypasses the current selected rule.")
            elif selected:
                raise GameLifecycleError("New rule trigger bypasses an unfinished timing batch.")
            observed[trigger.trigger_id] = trigger
        elif event.event_type in ("rule_trigger_released", "rule_trigger_completed"):
            if not isinstance(event.payload, dict) or set(event.payload) != {"trigger_id"}:
                raise GameLifecycleError("Rule trigger disposition requires its exact identity.")
            identifier = event.payload["trigger_id"]
            if type(identifier) is not str or identifier not in observed:
                raise GameLifecycleError("Rule trigger disposition has no observed occurrence.")
            trigger = observed[identifier]
            if event.event_type == "rule_trigger_released":
                if identifier in released or (
                    trigger.parent_batch_id is not None
                    and not batches[trigger.parent_batch_id].current_batch_complete
                ):
                    raise GameLifecycleError(
                        "Rule trigger released before its parent batch completed."
                    )
                if any(active not in completed for active in released):
                    raise GameLifecycleError(
                        "Rule trigger release interrupts another released occurrence."
                    )
                ready = RuleTriggerHistory(
                    tuple(observed.values()),
                    tuple(released),
                    tuple(completed),
                    tuple(batches.values()),
                ).ready()
                if not ready or ready[0] != trigger:
                    raise GameLifecycleError("Rule trigger release bypasses an earlier occurrence.")
                released.append(identifier)
            else:
                if identifier not in released or identifier in completed:
                    raise GameLifecycleError("Rule trigger completion lacks a unique release.")
                if any(
                    batch.context.conflict_id == trigger.conflict_id
                    and not batch.current_batch_complete
                    for batch in batches.values()
                ):
                    raise GameLifecycleError("Rule trigger completed with unfinished timing rules.")
                completed.append(identifier)
    return RuleTriggerHistory(
        tuple(observed.values()), tuple(released), tuple(completed), tuple(batches.values())
    )


def observe_rule_trigger(
    *, decisions: DecisionController, kind: RuleTriggerKind, context: JsonValue
) -> RuleTrigger:
    history = rule_trigger_history(decisions)
    identity = RuleTrigger(kind, context, None, None).trigger_id
    for trigger in history.observed:
        if trigger.trigger_id == identity:
            return trigger
    selected = tuple(
        batch for batch in history.batches if batch.selected_participant_id is not None
    )
    parent = selected[-1] if selected else None
    trigger = RuleTrigger(
        kind,
        context,
        parent.batch_id if parent is not None else None,
        parent.selected_participant_id if parent is not None else None,
    )
    decisions.event_log.append("rule_trigger_observed", trigger.to_payload())
    return trigger


def release_rule_trigger(*, decisions: DecisionController, trigger: RuleTrigger) -> bool:
    history = rule_trigger_history(decisions)
    ready = history.ready()
    if not ready or ready[0] != trigger:
        return False
    if trigger.trigger_id not in history.released:
        decisions.event_log.append("rule_trigger_released", {"trigger_id": trigger.trigger_id})
    return True


def unreleased_rule_trigger_status(
    *, decisions: DecisionController, trigger: RuleTrigger, stage: GameLifecycleStage
) -> LifecycleStatus | None:
    """Keep a blocked root's action host; let a deferred child finish its parent."""
    history = rule_trigger_history(decisions)
    if trigger not in history.observed:
        raise GameLifecycleError("Unreleased rule trigger has no observed occurrence.")
    if trigger.trigger_id in history.completed or trigger.parent_batch_id is not None:
        return None
    return LifecycleStatus.advanced(
        stage=stage,
        payload={"phase_body_status": "rule_trigger_waiting_for_prior_trigger"},
    )


def complete_rule_trigger(*, decisions: DecisionController, trigger: RuleTrigger) -> None:
    history = rule_trigger_history(decisions)
    if trigger.trigger_id not in history.released or trigger.trigger_id in history.completed:
        raise GameLifecycleError("Rule trigger completion requires a pending released occurrence.")
    if any(
        batch.context.conflict_id == trigger.conflict_id and not batch.current_batch_complete
        for batch in history.batches
    ):
        raise GameLifecycleError("Rule trigger completed with unfinished timing rules.")
    decisions.event_log.append("rule_trigger_completed", {"trigger_id": trigger.trigger_id})
