from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import (
    FightOrderingBandKind,
    FightPolicyDescriptor,
    RulesetDescriptor,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    DECLINE_FIGHT_INTERRUPT_OPTION_ID,
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
    FightActivationSelection,
    FightEligibilityContext,
    FightInterruptRequest,
    FightPhaseState,
    FightsFirstRegistry,
    current_eligible_pass_from_payload,
    current_fight_activation_selection_from_payload,
    decline_fight_interrupt_payload,
    eligible_fight_contexts_for_player,
    eligible_pass_is_available,
    eligible_pass_option_payload,
    engaged_unit_ids_at_fight_start,
    fight_activation_option_id,
    fight_activation_option_payload,
    fight_interrupt_option_payload,
    fight_interrupt_request_from_payload,
    fight_interrupt_sources_for_player,
    legal_fight_types_for_context,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_FIGHT_PHASE_COMPLETE_STATUS = "fight_phase_complete"
_FIGHT_ACTIVATION_REQUIRED_STATUS = "fight_activation_required"
_FIGHT_PASS_RECORDED_STATUS = "eligible_to_fight_pass_recorded"
_FIGHT_ACTIVATION_RECORDED_STATUS = "fight_activation_recorded"
_FIGHT_INTERRUPT_REQUIRED_STATUS = "fight_interrupt_required"
_FIGHT_INTERRUPT_DECLINED_STATUS = "fight_interrupt_declined"
_FIGHT_INTERRUPT_RECORDED_STATUS = "fight_interrupt_recorded"


@dataclass(frozen=True, slots=True)
class FightPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "FightPhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.FIGHT

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        del reaction_queue
        _validate_fight_phase_state(state)
        policy = _fight_policy_for_handler(self)
        fight_state = _ensure_fight_phase_state(
            state=state,
            decisions=decisions,
            policy=policy,
        )
        if fight_state.phase_complete:
            decisions.event_log.append(
                "fight_phase_completed",
                _fight_phase_status_payload(
                    state=state,
                    fight_state=fight_state,
                    phase_body_status=_FIGHT_PHASE_COMPLETE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_fight_phase_status_payload(
                    state=state,
                    fight_state=fight_state,
                    phase_body_status=_FIGHT_PHASE_COMPLETE_STATUS,
                ),
            )

        selected_context = _advance_to_next_fight_request(
            state=state,
            fight_state=fight_state,
            policy=policy,
        )
        state.fight_phase_state = selected_context.fight_state
        if selected_context.fight_state.phase_complete:
            decisions.event_log.append(
                "fight_phase_completed",
                _fight_phase_status_payload(
                    state=state,
                    fight_state=selected_context.fight_state,
                    phase_body_status=_FIGHT_PHASE_COMPLETE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_fight_phase_status_payload(
                    state=state,
                    fight_state=selected_context.fight_state,
                    phase_body_status=_FIGHT_PHASE_COMPLETE_STATUS,
                ),
            )
        return _request_fight_activation(
            state=state,
            decisions=decisions,
            fight_state=selected_context.fight_state,
            contexts=selected_context.contexts,
            pass_available=selected_context.pass_available,
            policy=policy,
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus | None:
        if result.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
            return _apply_fight_activation_decision(
                state=state,
                result=result,
                decisions=decisions,
                reaction_queue=reaction_queue,
                policy=_fight_policy_for_handler(self),
            )
        if result.decision_type == FIGHT_INTERRUPT_DECISION_TYPE:
            return _apply_fight_interrupt_decision(
                state=state,
                result=result,
                decisions=decisions,
                policy=_fight_policy_for_handler(self),
            )
        raise GameLifecycleError("Fight phase received unsupported decision type.")


@dataclass(frozen=True, slots=True)
class _FightRequestContext:
    fight_state: FightPhaseState
    contexts: tuple[FightEligibilityContext, ...]
    pass_available: bool


def invalid_fight_activation_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_activation_result",
    )
    if invalid_status is not None:
        return invalid_status
    fight_state = state.fight_phase_state
    if fight_state is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selection has no active fight phase state.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "fight_phase_state",
            },
        )
    policy = ruleset_descriptor.fight_policy
    current_contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=_require_actor(result),
        policy=policy,
    )
    if result.selected_option_id == ELIGIBLE_TO_FIGHT_PASS_OPTION_ID:
        return _invalid_fight_pass_status(
            state=state,
            result=result,
            fight_state=fight_state,
            current_contexts=current_contexts,
            policy=policy,
        )
    return _invalid_fight_activation_selection_status(
        state=state,
        result=result,
        fight_state=fight_state,
        current_contexts=current_contexts,
        policy=policy,
    )


def invalid_fight_interrupt_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_interrupt_result",
    )
    if invalid_status is not None:
        return invalid_status
    fight_state = state.fight_phase_state
    if fight_state is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt has no active fight phase state.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "fight_phase_state",
            },
        )
    interrupt = fight_interrupt_request_from_payload(result.payload)
    fight_order_state = fight_state.fight_order_state
    if interrupt.interrupt_id in fight_order_state.resolved_interrupt_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt has already resolved.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "interrupt_id",
            },
        )
    if interrupt.source_effect_id in fight_order_state.resolved_interrupt_source_effect_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt source has already resolved.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "source_effect_id",
            },
        )
    if result.selected_option_id == DECLINE_FIGHT_INTERRUPT_OPTION_ID:
        return None
    policy = ruleset_descriptor.fight_policy
    current_contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=interrupt.player_id,
        policy=policy,
    )
    selected = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
        interrupt_id=interrupt.interrupt_id,
    )
    matching_context = _matching_context(current_contexts, selected.unit_instance_id)
    if matching_context is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected unit is no longer eligible.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "unit_instance_id",
            },
        )
    if selected.unit_instance_id not in interrupt.eligible_unit_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected a unit outside the interrupt snapshot.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "eligible_unit_ids",
            },
        )
    expected_option_id = fight_activation_option_id(
        unit_instance_id=selected.unit_instance_id,
        fight_type=selected.fight_type,
    )
    if result.selected_option_id != expected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected option does not match its payload.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "selected_option_id",
            },
        )
    if selected.fight_type not in legal_fight_types_for_context(
        context=matching_context,
        policy=policy,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected fight type is not legal for that unit.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "fight_type",
            },
        )
    if matching_context.to_payload() != _context_payload_from_result(result):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt eligibility context is stale.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "eligibility_context",
            },
        )
    return None


def _ensure_fight_phase_state(
    *,
    state: GameState,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
) -> FightPhaseState:
    fight_state = state.fight_phase_state
    if fight_state is not None:
        return fight_state
    active_player_id = _active_player_id(state)
    registry = FightsFirstRegistry.from_state(state)
    started = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=engaged_unit_ids_at_fight_start(
            state=state,
            policy=policy,
        ),
        fights_first_registry=registry,
    )
    state.fight_phase_state = started
    decisions.event_log.append(
        "fight_phase_started",
        _fight_phase_status_payload(
            state=state,
            fight_state=started,
            phase_body_status="fight_phase_started",
        ),
    )
    return started


def _advance_to_next_fight_request(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    policy: FightPolicyDescriptor,
) -> _FightRequestContext:
    current = fight_state
    checked_player_ids: set[str] = set()
    for _iteration in range(
        len(state.player_ids) * (len(current.fight_order_state.ordering_bands) + 1) * 2
    ):
        if current.phase_complete:
            return _FightRequestContext(
                fight_state=current,
                contexts=(),
                pass_available=False,
            )
        if (
            current.current_ordering_band is FightOrderingBandKind.REMAINING_COMBATS
            and _fights_first_contexts_available(
                state=state,
                fight_state=current,
                policy=policy,
            )
        ):
            current = current.with_ordering_band(
                ordering_band=FightOrderingBandKind.FIGHTS_FIRST,
                next_player_id=current.active_player_id,
            )
            checked_player_ids = set()
            continue
        contexts = (
            ()
            if current.fight_order_state.next_player_id
            in current.fight_order_state.passed_player_ids
            else eligible_fight_contexts_for_player(
                state=state,
                fight_state=current,
                player_id=current.fight_order_state.next_player_id,
                policy=policy,
            )
        )
        if contexts:
            return _FightRequestContext(
                fight_state=current,
                contexts=contexts,
                pass_available=eligible_pass_is_available(contexts),
            )
        checked_player_ids.add(current.fight_order_state.next_player_id)
        if len(checked_player_ids) < len(state.player_ids):
            current = current.with_next_player(
                _next_player_id(
                    player_ids=state.player_ids,
                    current_player_id=current.fight_order_state.next_player_id,
                )
            )
            continue
        current = current.with_next_band()
        checked_player_ids = set()
    raise GameLifecycleError("Fight phase exceeded deterministic ordering guard.")


def _request_fight_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus:
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=FIGHT_ACTIVATION_DECISION_TYPE,
        actor_id=fight_state.fight_order_state.next_player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": fight_state.active_player_id,
                "player_id": fight_state.fight_order_state.next_player_id,
                "step_states": [step.to_payload() for step in fight_state.step_states],
                "ordering_band": fight_state.current_ordering_band.value,
                "eligible_contexts": [context.to_payload() for context in contexts],
                "eligible_pass_available": pass_available,
            }
        ),
        options=_fight_activation_options(
            state=state,
            fight_state=fight_state,
            contexts=contexts,
            pass_available=pass_available,
            policy=policy,
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_activation_selection_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": fight_state.active_player_id,
                "player_id": fight_state.fight_order_state.next_player_id,
                "ordering_band": fight_state.current_ordering_band.value,
                "request_id": request.request_id,
                "eligible_unit_ids": [context.unit_instance_id for context in contexts],
                "eligible_pass_available": pass_available,
                "phase_body_status": _FIGHT_ACTIVATION_REQUIRED_STATUS,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_ACTIVATION_REQUIRED_STATUS,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "player_id": fight_state.fight_order_state.next_player_id,
            "ordering_band": fight_state.current_ordering_band.value,
            "eligible_unit_ids": [context.unit_instance_id for context in contexts],
            "eligible_pass_available": pass_available,
        },
    )


def _fight_activation_options(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for context in contexts:
        for fight_type in legal_fight_types_for_context(context=context, policy=policy):
            options.append(
                DecisionOption(
                    option_id=fight_activation_option_id(
                        unit_instance_id=context.unit_instance_id,
                        fight_type=fight_type,
                    ),
                    label=f"{context.unit_instance_id} {fight_type.value}",
                    payload=fight_activation_option_payload(
                        state=state,
                        fight_state=fight_state,
                        context=context,
                        fight_type=fight_type,
                    ),
                )
            )
    if pass_available:
        options.append(
            DecisionOption(
                option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
                label="Eligible To Fight Pass",
                payload=eligible_pass_option_payload(
                    state=state,
                    fight_state=fight_state,
                    player_id=fight_state.fight_order_state.next_player_id,
                    contexts=contexts,
                    policy=policy,
                ),
            )
        )
    return tuple(options)


def _fights_first_contexts_available(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    policy: FightPolicyDescriptor,
) -> bool:
    fights_first_state = fight_state.with_ordering_band(
        ordering_band=FightOrderingBandKind.FIGHTS_FIRST,
        next_player_id=fight_state.active_player_id,
    )
    return any(
        eligible_fight_contexts_for_player(
            state=state,
            fight_state=fights_first_state,
            player_id=player_id,
            policy=policy,
        )
        for player_id in state.player_ids
    )


def _apply_fight_activation_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    if result.selected_option_id == ELIGIBLE_TO_FIGHT_PASS_OPTION_ID:
        eligible_pass = current_eligible_pass_from_payload(
            result_payload=result.payload,
            request_id=result.request_id,
            result_id=result.result_id,
        )
        state.fight_phase_state = fight_state.with_eligible_pass(eligible_pass).with_next_player(
            _next_player_id(player_ids=state.player_ids, current_player_id=eligible_pass.player_id)
        )
        decisions.event_log.append(
            "eligible_to_fight_pass_recorded",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_PASS_RECORDED_STATUS,
                    "eligible_pass": eligible_pass.to_payload(),
                }
            ),
        )
        return None

    selection = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    activated_state = fight_state.with_activation(selection).with_next_player(
        _next_player_id(player_ids=state.player_ids, current_player_id=selection.player_id)
    )
    state.fight_phase_state = activated_state
    event = decisions.event_log.append(
        "fight_activation_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_ACTIVATION_RECORDED_STATUS,
                "activation_selection": selection.to_payload(),
                "phase15d_resolution": "deferred",
            }
        ),
    )
    return _request_fight_interrupt_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=selection,
        trigger_event_id=event.event_id,
        policy=policy,
    )


def _apply_fight_interrupt_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    del policy
    fight_state = _require_fight_state(state)
    interrupt = fight_interrupt_request_from_payload(result.payload)
    if result.selected_option_id == DECLINE_FIGHT_INTERRUPT_OPTION_ID:
        state.fight_phase_state = fight_state.with_resolved_interrupt(
            interrupt_id=interrupt.interrupt_id,
            source_effect_id=interrupt.source_effect_id,
        )
        decisions.event_log.append(
            "fight_interrupt_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_INTERRUPT_DECLINED_STATUS,
                    "interrupt": interrupt.to_payload(),
                }
            ),
        )
        return None

    selection = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
        interrupt_id=interrupt.interrupt_id,
    )
    state.fight_phase_state = fight_state.with_activation(selection).with_resolved_interrupt(
        interrupt_id=interrupt.interrupt_id,
        source_effect_id=interrupt.source_effect_id,
    )
    decisions.event_log.append(
        "fight_interrupt_activation_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_INTERRUPT_RECORDED_STATUS,
                "interrupt": interrupt.to_payload(),
                "activation_selection": selection.to_payload(),
                "phase15d_resolution": "deferred",
            }
        ),
    )
    return None


def _request_fight_interrupt_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    fought_selection: FightActivationSelection,
    trigger_event_id: str,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    if reaction_queue is None:
        return None
    fight_state = _require_fight_state(state)
    for player_id in state.player_ids:
        if player_id == fought_selection.player_id:
            continue
        for source_effect_id, source_rule_id, _effect_rule_id in fight_interrupt_sources_for_player(
            state=state,
            player_id=player_id,
        ):
            interrupt_id = f"fight-interrupt:{source_effect_id}:{trigger_event_id}"
            if (
                interrupt_id in fight_state.fight_order_state.resolved_interrupt_ids
                or source_effect_id
                in fight_state.fight_order_state.resolved_interrupt_source_effect_ids
            ):
                continue
            contexts = eligible_fight_contexts_for_player(
                state=state,
                fight_state=fight_state,
                player_id=player_id,
                policy=policy,
            )
            if not contexts:
                continue
            interrupt = FightInterruptRequest(
                interrupt_id=interrupt_id,
                source_effect_id=source_effect_id,
                source_rule_id=source_rule_id,
                player_id=player_id,
                battle_round=state.battle_round,
                ordering_band=fight_state.current_ordering_band,
                trigger_event_id=trigger_event_id,
                eligible_unit_ids=tuple(context.unit_instance_id for context in contexts),
            )
            triggered = reaction_queue.emit_decision_request(
                state=state,
                decisions=decisions,
                reaction_window=ReactionWindow(
                    timing_window=TimingWindow(
                        window_id=(
                            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
                            f"fight-interrupt:{source_effect_id}:{trigger_event_id}"
                        ),
                        descriptor=TimingWindowDescriptor(
                            descriptor_id=f"{interrupt_id}:descriptor",
                            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
                            source_rule_id=source_rule_id,
                            phase=BattlePhase.FIGHT,
                            source_step="fight",
                        ),
                        game_id=state.game_id,
                        battle_round=state.battle_round,
                        active_player_id=_active_player_id(state),
                        phase=BattlePhase.FIGHT,
                        trigger_event_id=trigger_event_id,
                    ),
                    eligible_player_ids=(player_id,),
                ),
                parent_phase=BattlePhase.FIGHT,
                parent_step="fight",
                resume_token=interrupt_id,
                actor_id=player_id,
                decision_type=FIGHT_INTERRUPT_DECISION_TYPE,
                options=_fight_interrupt_options(
                    state=state,
                    fight_state=fight_state,
                    interrupt=interrupt,
                    contexts=contexts,
                    policy=policy,
                ),
                payload={
                    "phase_body_status": _FIGHT_INTERRUPT_REQUIRED_STATUS,
                    "interrupt": validate_json_value(interrupt.to_payload()),
                },
            )
            decisions.event_log.append(
                "fight_interrupt_requested",
                validate_json_value(
                    {
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.FIGHT.value,
                        "phase_body_status": _FIGHT_INTERRUPT_REQUIRED_STATUS,
                        "request_id": triggered.decision_request.request_id,
                        "interrupt": interrupt.to_payload(),
                    }
                ),
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=triggered.decision_request,
                payload={
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_INTERRUPT_REQUIRED_STATUS,
                    "request_id": triggered.decision_request.request_id,
                    "interrupt_id": interrupt.interrupt_id,
                },
            )
    return None


def _fight_interrupt_options(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    interrupt: FightInterruptRequest,
    contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
            label="Decline Fight Interrupt",
            payload=decline_fight_interrupt_payload(interrupt=interrupt),
        )
    ]
    for context in contexts:
        for fight_type in legal_fight_types_for_context(context=context, policy=policy):
            options.append(
                DecisionOption(
                    option_id=fight_activation_option_id(
                        unit_instance_id=context.unit_instance_id,
                        fight_type=fight_type,
                    ),
                    label=f"{context.unit_instance_id} interrupt {fight_type.value}",
                    payload=fight_interrupt_option_payload(
                        state=state,
                        fight_state=fight_state,
                        interrupt=interrupt,
                        context=context,
                        fight_type=fight_type,
                    ),
                )
            )
    return tuple(options)


def _invalid_fight_pass_status(
    *,
    state: GameState,
    result: DecisionResult,
    fight_state: FightPhaseState,
    current_contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    if not eligible_pass_is_available(current_contexts):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass is not currently legal.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "eligible_to_fight_pass",
            },
        )
    eligible_pass = current_eligible_pass_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    expected_unit_ids = tuple(context.unit_instance_id for context in current_contexts)
    if eligible_pass.eligible_unit_ids != tuple(sorted(expected_unit_ids)):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass unit snapshot is stale.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "eligible_unit_ids",
            },
        )
    if eligible_pass.player_id != fight_state.fight_order_state.next_player_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass player drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "player_id",
            },
        )
    if eligible_pass.pass_distance_inches != policy.eligible_pass_distance_inches:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass distance drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "pass_distance_inches",
            },
        )
    return None


def _invalid_fight_activation_selection_status(
    *,
    state: GameState,
    result: DecisionResult,
    fight_state: FightPhaseState,
    current_contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    selected = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    expected_option_id = fight_activation_option_id(
        unit_instance_id=selected.unit_instance_id,
        fight_type=selected.fight_type,
    )
    if result.selected_option_id != expected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selected option does not match its payload.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "selected_option_id",
            },
        )
    if selected.player_id != fight_state.fight_order_state.next_player_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation player drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "player_id",
            },
        )
    if selected.ordering_band is not fight_state.current_ordering_band:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ordering band drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "ordering_band",
            },
        )
    if selected.fight_type not in policy.fight_types:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selected unsupported fight type.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "fight_type",
            },
        )
    matching_context = _matching_context(current_contexts, selected.unit_instance_id)
    if matching_context is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selected unit is no longer eligible.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "unit_instance_id",
            },
        )
    if matching_context.to_payload() != _context_payload_from_result(result):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation eligibility context is stale.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "eligibility_context",
            },
        )
    if selected.fight_type not in legal_fight_types_for_context(
        context=matching_context,
        policy=policy,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight type is not legal for the selected unit.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "fight_type",
            },
        )
    return None


def _matching_context(
    contexts: tuple[FightEligibilityContext, ...],
    unit_instance_id: str,
) -> FightEligibilityContext | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for context in contexts:
        if context.unit_instance_id == requested_unit_id:
            return context
    return None


def _context_payload_from_result(result: DecisionResult) -> dict[str, JsonValue]:
    payload = result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fight result payload must be an object.")
    context = payload.get("eligibility_context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Fight result payload requires eligibility_context.")
    return context


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending.",
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
            message="Decision result payload does not match the selected option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _fight_phase_status_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    phase_body_status: str,
) -> JsonValue:
    return validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": phase_body_status,
            "fight_phase_state": fight_state.to_payload(),
        }
    )


def _validate_fight_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("FightPhaseHandler can run only during battle.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("FightPhaseHandler phase does not match state.")
    if state.battlefield_state is None:
        raise GameLifecycleError("FightPhaseHandler requires battlefield_state.")


def _fight_policy_for_handler(handler: FightPhaseHandler) -> FightPolicyDescriptor:
    if handler.ruleset_descriptor is None:
        return RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    return handler.ruleset_descriptor.fight_policy


def _require_fight_state(state: GameState) -> FightPhaseState:
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Fight phase decision requires fight_phase_state.")
    return fight_state


def _require_actor(result: DecisionResult) -> str:
    if result.actor_id is None:
        raise GameLifecycleError("Fight decision requires an actor.")
    return result.actor_id


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Fight phase requires an active player.")
    return state.active_player_id


def _next_player_id(*, player_ids: tuple[str, ...], current_player_id: str) -> str:
    current = _validate_identifier("current_player_id", current_player_id)
    if current not in player_ids:
        raise GameLifecycleError("Fight ordering player is not in this game.")
    index = player_ids.index(current)
    return player_ids[(index + 1) % len(player_ids)]


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
