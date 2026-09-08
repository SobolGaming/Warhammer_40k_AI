from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.fight_activation_units import (
    validate_attached_rules_unit_after_fight_activation,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_destruction_cleanup import begin_retained_destruction_cleanup
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import FightPolicyDescriptor
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.fight_order import FightActivationSelection
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.fight import FightPhaseHandler
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


UNIT_FOUGHT_STATUS = "unit_fought"


def completed_activation_event(
    *, decisions: DecisionController, activation: FightActivationSelection
) -> EventRecord | None:
    matches = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "unit_has_fought"
        and isinstance(event.payload, dict)
        and event.payload.get("activation_selection") == activation.to_payload()
    )
    if len(matches) > 1:
        raise GameLifecycleError("Fight activation completion was recorded twice.")
    return None if not matches else matches[0]


def complete_active_fight_activation(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
    activation: FightActivationSelection,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.phases.fight import (
        request_counteroffensive_if_available,
        request_fight_interrupt_if_available,
        require_fight_state,
    )

    fight_state = require_fight_state(state)
    if fight_state.active_activation != activation:
        raise GameLifecycleError("Fight completion active selection drift.")
    unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id=activation.unit_instance_id
    ).unit_instance_id
    event = completed_activation_event(decisions=decisions, activation=activation)
    if event is None:
        event = decisions.event_log.append(
            "unit_has_fought",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": UNIT_FOUGHT_STATUS,
                    "activation_selection": activation.to_payload(),
                    **(
                        {}
                        if fight_state.forced_activation_context is None
                        else {
                            "forced_activation_context": (
                                fight_state.forced_activation_context.to_payload()
                            ),
                        }
                    ),
                }
            ),
        )
    status = begin_retained_destruction_cleanup(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_id,
        reason="unit_fight_completed",
    )
    if status is not None:
        return status
    # Cleanup decisions retain this activation until its destruction owners finish.
    # Later resumption finds the event above and cannot repeat attacks or completion.
    state.replace_fight_phase_state(require_fight_state(state).with_active_activation(None))
    validate_attached_rules_unit_after_fight_activation(state=state, rules_unit_instance_id=unit_id)
    if fight_state.forced_activation_context is not None:
        return None
    counteroffensive_status = request_counteroffensive_if_available(
        handler=handler,
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=activation,
        trigger_event_id=event.event_id,
        policy=policy,
    )
    if counteroffensive_status is not None:
        return counteroffensive_status
    return request_fight_interrupt_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=activation,
        trigger_event_id=event.event_id,
        policy=policy,
    )
