from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


type UnitMoveCompletedMortalWoundHandler = Callable[
    ["UnitMoveCompletedContext"],
    tuple["UnitMoveCompletedMortalWoundEffect", ...],
]
type UnitMoveCompletedMortalWoundRequestHandler = Callable[
    ["UnitMoveCompletedContext"],
    LifecycleStatus | None,
]

UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_SOURCE_KIND = "unit_move_completed_mortal_wounds"
UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_PENDING_EVENT = "unit_move_completed_mortal_wounds_pending"
UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT = "unit_move_completed_mortal_wounds_resolved"
UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT = "unit_move_completed_mortal_wounds_rolled"
UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_IGNORED_EVENT = "unit_move_completed_mortal_wounds_ignored"


@dataclass(frozen=True, slots=True)
class UnitMoveCompletedContext:
    state: GameState
    ruleset_descriptor: RulesetDescriptor
    runtime_modifier_registry: RuntimeModifierRegistry
    completed_phase: BattlePhase
    trigger_event_id: str
    trigger_event_payload: dict[str, JsonValue]
    triggering_unit_instance_id: str
    triggering_player_id: str
    movement_action: str
    decisions: DecisionController | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState
        from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

        if type(self.state) is not GameState:
            raise GameLifecycleError("Unit move completed context requires GameState.")
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("Unit move completed context requires a RulesetDescriptor.")
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "Unit move completed context requires a RuntimeModifierRegistry."
            )
        object.__setattr__(self, "completed_phase", _battle_phase_from_token(self.completed_phase))
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "trigger_event_payload",
            _validate_json_object("trigger_event_payload", self.trigger_event_payload),
        )
        object.__setattr__(
            self,
            "triggering_unit_instance_id",
            _validate_identifier(
                "triggering_unit_instance_id",
                self.triggering_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "triggering_player_id",
            _validate_identifier("triggering_player_id", self.triggering_player_id),
        )
        object.__setattr__(
            self,
            "movement_action",
            _validate_identifier("movement_action", self.movement_action),
        )
        if self.decisions is not None and type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "Unit move completed context decisions must be a DecisionController."
            )


@dataclass(frozen=True, slots=True)
class UnitMoveCompletedMortalWoundEffect:
    hook_id: str
    source_id: str
    source_rule_id: str
    target_unit_instance_id: str
    target_player_id: str
    rolling_player_id: str
    trigger_event_id: str
    roll_threshold: int
    mortal_wounds_expression: DiceExpression
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_player_id",
            _validate_identifier("target_player_id", self.target_player_id),
        )
        object.__setattr__(
            self,
            "rolling_player_id",
            _validate_identifier("rolling_player_id", self.rolling_player_id),
        )
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "roll_threshold",
            _validate_d6_threshold("roll_threshold", self.roll_threshold),
        )
        if type(self.mortal_wounds_expression) is not DiceExpression:
            raise GameLifecycleError(
                "Unit move completed mortal wound effect requires DiceExpression."
            )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))


@dataclass(frozen=True, slots=True)
class UnitMoveCompletedMortalWoundHookBinding:
    hook_id: str
    source_id: str
    handler: UnitMoveCompletedMortalWoundHandler | None = None
    request_handler: UnitMoveCompletedMortalWoundRequestHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.handler is not None and not callable(self.handler):
            raise GameLifecycleError(
                "UnitMoveCompletedMortalWoundHookBinding handler must be callable."
            )
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError(
                "UnitMoveCompletedMortalWoundHookBinding request_handler must be callable."
            )
        if self.handler is None and self.request_handler is None:
            raise GameLifecycleError(
                "UnitMoveCompletedMortalWoundHookBinding requires a handler or request_handler."
            )


@dataclass(frozen=True, slots=True)
class UnitMoveCompletedMortalWoundHookRegistry:
    bindings: tuple[UnitMoveCompletedMortalWoundHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(
        cls,
        bindings: tuple[UnitMoveCompletedMortalWoundHookBinding, ...],
    ) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
        return self.bindings

    def effects_for(
        self,
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Unit move completed hooks require a context.")
        effects: list[UnitMoveCompletedMortalWoundEffect] = []
        for binding in self.bindings:
            if binding.handler is None:
                continue
            handler_effects = binding.handler(context)
            if type(handler_effects) is not tuple:
                raise GameLifecycleError(
                    "Unit move completed handlers must return an effect tuple."
                )
            for effect in handler_effects:
                if type(effect) is not UnitMoveCompletedMortalWoundEffect:
                    raise GameLifecycleError(
                        "Unit move completed handlers must return mortal wound effects."
                    )
                if effect.hook_id != binding.hook_id:
                    raise GameLifecycleError("Unit move completed handler returned hook_id drift.")
                if effect.source_id != binding.source_id:
                    raise GameLifecycleError(
                        "Unit move completed handler returned source_id drift."
                    )
                if effect.trigger_event_id != context.trigger_event_id:
                    raise GameLifecycleError(
                        "Unit move completed handler returned trigger event drift."
                    )
                effects.append(effect)
        return tuple(
            sorted(
                effects,
                key=lambda effect: (
                    effect.trigger_event_id,
                    effect.target_unit_instance_id,
                    effect.hook_id,
                    repr(effect.replay_payload),
                ),
            )
        )

    def request_status_for(self, context: UnitMoveCompletedContext) -> LifecycleStatus | None:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Unit move completed hooks require a context.")
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            status = binding.request_handler(context)
            if status is None:
                continue
            if type(status) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Unit move completed request handlers must return LifecycleStatus or None."
                )
            return status
        return None


def resolve_unit_move_completed_mortal_wound_hooks(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: UnitMoveCompletedMortalWoundHookRegistry,
    ruleset_descriptor: RulesetDescriptor,
    runtime_modifier_registry: RuntimeModifierRegistry,
    completed_phase: BattlePhase,
    event_type: str,
    movement_actions: tuple[str, ...],
) -> LifecycleStatus | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Unit move completed hooks require a DecisionController.")
    if type(registry) is not UnitMoveCompletedMortalWoundHookRegistry:
        raise GameLifecycleError("Unit move completed hooks require a registry.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Unit move completed hooks require a RulesetDescriptor.")
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Unit move completed hooks require a RuntimeModifierRegistry.")
    phase = _battle_phase_from_token(completed_phase)
    requested_event_type = _validate_identifier("event_type", event_type)
    requested_actions = _validate_identifier_tuple("movement_actions", movement_actions)
    if not registry.all_bindings():
        return None
    processed_effect_keys = _processed_effect_keys(decisions)
    for event_id, payload in _unprocessed_move_completion_events(
        state=state,
        decisions=decisions,
        completed_phase=phase,
        event_type=requested_event_type,
        movement_actions=requested_actions,
    ):
        triggering_unit_id = _payload_string(payload, "unit_instance_id")
        triggering_player_id = _payload_string(payload, "active_player_id")
        movement_action = _movement_action_from_payload(payload)
        context = UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            runtime_modifier_registry=runtime_modifier_registry,
            completed_phase=phase,
            trigger_event_id=event_id,
            trigger_event_payload=payload,
            triggering_unit_instance_id=triggering_unit_id,
            triggering_player_id=triggering_player_id,
            movement_action=movement_action,
            decisions=decisions,
        )
        request_status = registry.request_status_for(context)
        if request_status is not None:
            return request_status
        for effect in registry.effects_for(context):
            if _effect_key(effect) in processed_effect_keys:
                continue
            status = _resolve_mortal_wound_effect(
                state=state,
                decisions=decisions,
                effect=effect,
                completed_phase=phase,
                movement_action=movement_action,
            )
            if status is not None:
                return status
    return None


def apply_unit_move_completed_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Move-completed Feel No Pain requires DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Move-completed Feel No Pain requires DecisionController.")
    record = decisions.record_for_result(result)
    request = record.request
    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError("Move-completed Feel No Pain requires mortal wound context.")
    source_context = mortal_wound_feel_no_pain_source_context(request)
    if not isinstance(source_context, dict) or source_context.get("source_kind") != (
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_SOURCE_KIND
    ):
        raise GameLifecycleError("Move-completed Feel No Pain source context is invalid.")
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
                "source_rule_id": source_context["source_rule_id"],
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Move-completed Feel No Pain did not finish routing.")
    decisions.event_log.append(
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT,
        {
            **_source_context_event_payload(source_context),
            "mortal_application": routed.application.to_payload(),
            "feel_no_pain_result_id": result.result_id,
        },
    )
    return None


def is_unit_move_completed_mortal_wound_feel_no_pain_request(
    request: object,
) -> bool:
    if type(request) is not DecisionRequest:
        return False
    if not is_mortal_wound_feel_no_pain_request(request):
        return False
    source_context = mortal_wound_feel_no_pain_source_context(request)
    return isinstance(source_context, dict) and source_context.get("source_kind") == (
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_SOURCE_KIND
    )


def _resolve_mortal_wound_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    effect: UnitMoveCompletedMortalWoundEffect,
    completed_phase: BattlePhase,
    movement_action: str,
) -> LifecycleStatus | None:
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=(
                "Unit move completed mortal wound trigger "
                f"{effect.source_rule_id} for {effect.target_unit_instance_id}"
            ),
            roll_type="unit_move_completed_mortal_wounds.trigger",
            actor_id=effect.rolling_player_id,
        )
    )
    roll_payload = validate_json_value(roll_state.to_payload())
    base_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": completed_phase.value,
        "active_player_id": state.active_player_id,
        "trigger_event_id": effect.trigger_event_id,
        "movement_action": movement_action,
        "hook_id": effect.hook_id,
        "effect_key": _effect_key(effect),
        "source_rule_id": effect.source_rule_id,
        "target_unit_instance_id": effect.target_unit_instance_id,
        "target_player_id": effect.target_player_id,
        "rolling_player_id": effect.rolling_player_id,
        "roll_threshold": effect.roll_threshold,
        "trigger_roll": roll_payload,
        "replay_payload": effect.replay_payload,
    }
    decisions.event_log.append(
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT,
        base_payload,
    )
    if roll_state.current_total < effect.roll_threshold:
        decisions.event_log.append(
            UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_IGNORED_EVENT,
            {
                **base_payload,
                "ignored_reason": "trigger_roll_failed",
            },
        )
        return None
    damage_roll = manager.roll(
        DiceRollSpec(
            expression=effect.mortal_wounds_expression,
            reason=(
                "Unit move completed mortal wounds "
                f"{effect.source_rule_id} for {effect.target_unit_instance_id}"
            ),
            roll_type="unit_move_completed_mortal_wounds.damage",
            actor_id=effect.rolling_player_id,
        )
    )
    source_context: dict[str, JsonValue] = {
        **base_payload,
        "source_kind": UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_SOURCE_KIND,
        "damage_roll": validate_json_value(damage_roll.to_payload()),
        "mortal_wounds": damage_roll.current_total,
    }
    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"unit-move-completed-mortal-wounds:{effect.trigger_event_id}:"
            f"{effect.hook_id}:{effect.target_unit_instance_id}:"
            f"{_effect_digest(effect)}"
        ),
        source_rule_id=effect.source_rule_id,
        source_context=source_context,
        target_unit_instance_id=effect.target_unit_instance_id,
        defender_player_id=effect.target_player_id,
        mortal_wounds=damage_roll.current_total,
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
        decisions.event_log.append(
            UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_PENDING_EVENT,
            {
                **source_context,
                "request_id": routed.request.request_id,
            },
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=routed.request,
            payload={
                "phase": completed_phase.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": effect.source_rule_id,
                "trigger_event_id": effect.trigger_event_id,
                "target_unit_instance_id": effect.target_unit_instance_id,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Unit move completed mortal wounds did not resolve.")
    decisions.event_log.append(
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT,
        {
            **source_context,
            "mortal_application": routed.application.to_payload(),
        },
    )
    return None


def _unprocessed_move_completion_events(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    event_type: str,
    movement_actions: tuple[str, ...],
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    events: list[tuple[str, dict[str, JsonValue]]] = []
    for record in decisions.event_log.records:
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("phase") != completed_phase.value:
            continue
        if _movement_action_from_payload(payload) not in movement_actions:
            continue
        events.append((record.event_id, payload))
    return tuple(events)


def _processed_effect_keys(decisions: DecisionController) -> set[str]:
    processed: set[str] = set()
    for record in decisions.event_log.records:
        if record.event_type not in {
            UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_PENDING_EVENT,
            UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT,
            UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_IGNORED_EVENT,
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        effect_key = payload.get("effect_key")
        if type(effect_key) is str:
            processed.add(effect_key)
    return processed


def _effect_key(effect: UnitMoveCompletedMortalWoundEffect) -> str:
    payload = {
        "trigger_event_id": effect.trigger_event_id,
        "hook_id": effect.hook_id,
        "source_id": effect.source_id,
        "source_rule_id": effect.source_rule_id,
        "target_unit_instance_id": effect.target_unit_instance_id,
        "target_player_id": effect.target_player_id,
        "rolling_player_id": effect.rolling_player_id,
        "replay_payload": effect.replay_payload,
    }
    return canonical_json(payload)


def _effect_digest(effect: UnitMoveCompletedMortalWoundEffect) -> str:
    return hashlib.sha256(_effect_key(effect).encode("utf-8")).hexdigest()[:16]


def _movement_action_from_payload(payload: dict[str, JsonValue]) -> str:
    movement_action = payload.get("movement_phase_action")
    if type(movement_action) is str:
        return _validate_identifier("movement_phase_action", movement_action)
    phase = payload.get("phase")
    if phase == BattlePhase.CHARGE.value:
        return "charge_move"
    raise GameLifecycleError("Move completion event missing movement action.")


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Move completion event missing string {key}.")
    return _validate_identifier(key, value)


def _source_context_event_payload(source_context: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "game_id": source_context["game_id"],
        "battle_round": source_context["battle_round"],
        "phase": source_context["phase"],
        "active_player_id": source_context["active_player_id"],
        "trigger_event_id": source_context["trigger_event_id"],
        "movement_action": source_context["movement_action"],
        "hook_id": source_context["hook_id"],
        "effect_key": source_context["effect_key"],
        "source_rule_id": source_context["source_rule_id"],
        "target_unit_instance_id": source_context["target_unit_instance_id"],
        "target_player_id": source_context["target_player_id"],
        "rolling_player_id": source_context["rolling_player_id"],
        "roll_threshold": source_context["roll_threshold"],
        "trigger_roll": source_context["trigger_roll"],
        "damage_roll": source_context["damage_roll"],
        "mortal_wounds": source_context["mortal_wounds"],
        "replay_payload": source_context["replay_payload"],
    }


def _validate_hook_bindings(
    value: object,
) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Unit move completed hook bindings must be a tuple.")
    bindings: list[UnitMoveCompletedMortalWoundHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not UnitMoveCompletedMortalWoundHookBinding:
            raise GameLifecycleError("Unit move completed hook registry requires hook bindings.")
        if binding.hook_id in seen:
            raise GameLifecycleError("Unit move completed hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Battle phase token must be a string.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported battle phase token: {token}.") from exc


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    raw_object = cast(dict[str, object], value)
    return cast(dict[str, JsonValue], validate_json_value(raw_object))


def _validate_d6_threshold(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        sorted(
            _validate_identifier(f"{field_name} entry", value)
            for value in cast(tuple[object, ...], values)
        )
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
