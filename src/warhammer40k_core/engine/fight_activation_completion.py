from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.fight_activation_units import (
    validate_attached_rules_unit_after_fight_activation,
)
from warhammer40k_core.engine.fight_selection_completion import (
    FIGHT_SELECTION_COMPLETED,
    actual_fought_payload,
    fight_selection_attack_evidence,
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
        if event.event_type == FIGHT_SELECTION_COMPLETED
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
        sequence_id, has_fought = fight_selection_attack_evidence(
            events=decisions.event_log.records, records=decisions.records, activation=activation
        )
        event = decisions.event_log.append(
            FIGHT_SELECTION_COMPLETED,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": FIGHT_SELECTION_COMPLETED,
                    "activation_selection": activation.to_payload(),
                    "attack_sequence_id": sequence_id,
                    "has_fought": has_fought,
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
        if has_fought:
            decisions.event_log.append("unit_has_fought", actual_fought_payload(event))
    # 05.04.05 retains an unarmed/empty selection until the phase ends. Consuming
    # its selection alone cannot trigger destruction rules or physical removal.
    if isinstance(event.payload, dict) and event.payload["has_fought"] is True:
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
    decisions.event_log.append("fight_activation_completed", activation.to_payload())
    validate_attached_rules_unit_after_fight_activation(state=state, rules_unit_instance_id=unit_id)
    if fight_state.forced_activation_context is not None:
        return None
    fought_events = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type == "unit_has_fought"
        and isinstance(record.payload, dict)
        and record.payload.get("activation_selection") == activation.to_payload()
    )
    if not fought_events:
        return None
    if len(fought_events) != 1:
        raise GameLifecycleError("Fight activation actual fought status was recorded twice.")
    fought_event = fought_events[0]
    counteroffensive_status = request_counteroffensive_if_available(
        handler=handler,
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=activation,
        trigger_event_id=fought_event.event_id,
        policy=policy,
    )
    if counteroffensive_status is not None:
        return counteroffensive_status
    return request_fight_interrupt_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=activation,
        trigger_event_id=fought_event.event_id,
        policy=policy,
    )
