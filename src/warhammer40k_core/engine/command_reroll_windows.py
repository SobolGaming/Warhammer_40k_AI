from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollResult, DiceRollResultPayload, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.opportunity_windows import (
    OPPORTUNITY_REQUEST_FAMILY,
    OPPORTUNITY_SUBMISSION_PAYLOAD_KEY,
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
    TriggerBatchingMode,
    opportunity_boundary_game_state_payload,
    opportunity_boundary_state_hash,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex

_validate_identifier = IdentifierValidator(GameLifecycleError)


def request_command_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    affected_unit_instance_id: str,
    source_phase: BattlePhase,
    stratagem_index: StratagemCatalogIndex | None,
    phase_body_status: str,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None,
    trigger_context_extra: dict[str, JsonValue] | None = None,
) -> LifecycleStatus | None:
    if roll_state is not None and roll_state.rerolls:
        return None
    if roll_state is None or stratagem_index is None:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    from warhammer40k_core.engine.stratagems import (
        COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY,
        COMMAND_REROLL_DICE_CONTEXT_KEY,
        CORE_COMMAND_REROLL_HANDLER_ID,
        DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_for_handler_from_index,
        stratagem_window_declined_for_context,
    )

    phase = battle_phase_kind_from_token(source_phase)
    if trigger_context_extra is not None and set(trigger_context_extra).intersection(
        {
            COMMAND_REROLL_DICE_CONTEXT_KEY,
            COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY,
            "source_phase",
            "roll_id",
            "roll_type",
        }
    ):
        raise GameLifecycleError("Command Re-roll source context overrides dice authority.")
    window_id = (
        f"command-reroll-{phase.value}-round-{state.battle_round:02d}-"
        f"{roll_state.original_result.roll_id}"
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=actor_id,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        timing_window_id=window_id,
        trigger_payload=validate_json_value(
            {
                COMMAND_REROLL_DICE_CONTEXT_KEY: roll_state.to_payload(),
                COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY: affected_unit_instance_id,
                "source_phase": phase.value,
                "roll_id": roll_state.original_result.roll_id,
                "roll_type": roll_state.original_result.spec.roll_type,
                **({} if trigger_context_extra is None else trigger_context_extra),
            }
        ),
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_for_handler_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        handler_id=CORE_COMMAND_REROLL_HANDLER_ID,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    from warhammer40k_core.engine.stratagems_selection import (
        _require_stratagem_selection,
        _selected_command_point_cost,
    )

    option_costs: dict[str, int] = {}
    for option in options:
        selection_context, record, binding, effect_selection = _require_stratagem_selection(
            option.payload
        )
        option_costs[option.option_id] = _selected_command_point_cost(
            state=state,
            definition=record.definition,
            context=selection_context,
            target_binding=binding,
            effect_selection=effect_selection,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
    request_id = state.next_decision_request_id()
    opportunity_window = _command_reroll_opportunity_window(
        state=state,
        decisions=decisions,
        window_id=window_id,
        roll_state=roll_state,
        actor_id=actor_id,
        affected_unit_instance_id=affected_unit_instance_id,
        phase=phase,
        option_costs=option_costs,
        decline_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    )
    enriched_options = _command_reroll_opportunity_options(
        window=opportunity_window,
        player_id=actor_id,
        use_options=options,
        decline_option=stratagem_decline_option(),
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=enriched_options,
        request_id=request_id,
        payload_extra={
            "submission_family": OPPORTUNITY_REQUEST_FAMILY,
            "opportunity_window": cast(JsonValue, opportunity_window.to_payload()),
            "opportunity_window_id": opportunity_window.window_id,
            "legal_action_fingerprint": opportunity_window.legal_action_fingerprint(actor_id),
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": phase.value,
            "phase_body_status": phase_body_status,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": affected_unit_instance_id,
            "pending_request_id": request.request_id,
        },
    )


def _command_reroll_opportunity_window(
    *,
    state: GameState,
    decisions: DecisionController,
    window_id: str,
    roll_state: DiceRollState,
    actor_id: str,
    affected_unit_instance_id: str,
    phase: BattlePhase,
    option_costs: dict[str, int],
    decline_option_id: str,
) -> OpportunityWindow:
    sequence_number = len(decisions.event_log.records)
    anchor_event_id = _dice_rolled_event_id_for_roll(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
    )
    timing_window = TimingWindow(
        window_id=window_id,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{window_id}:descriptor",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_rule_id="core:command-reroll",
            phase=phase,
            source_step=roll_state.original_result.spec.roll_type,
            metadata={
                "roll_id": roll_state.original_result.roll_id,
                "roll_type": roll_state.original_result.spec.roll_type,
                "affected_unit_instance_id": affected_unit_instance_id,
            },
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        trigger_event_id=anchor_event_id,
    )
    legal_actions = (
        OpportunityLegalAction(
            action_id=decline_option_id,
            source_id="core:pass",
            action_kind=OpportunityActionKind.PASS,
            controller_id=None,
            label="Decline Command Re-roll",
            batching_mode=TriggerBatchingMode.NONE,
            payload={"pass": True},
        ),
        *(
            OpportunityLegalAction(
                action_id=option_id,
                source_id="core:command-reroll",
                action_kind=OpportunityActionKind.REROLL,
                controller_id=actor_id,
                label="Command Re-roll",
                cost=({"resource": "cp", "amount": cost},),
                target_ids=(affected_unit_instance_id,),
                target_spec={
                    "roll_id": roll_state.original_result.roll_id,
                    "roll_type": roll_state.original_result.spec.roll_type,
                    "affected_unit_instance_id": affected_unit_instance_id,
                },
                batching_mode=TriggerBatchingMode.ONE_OF,
                payload={
                    "stratagem_id": "command-reroll",
                    "option_id": option_id,
                    "roll_state": cast(JsonValue, roll_state.to_payload()),
                },
            )
            for option_id, cost in option_costs.items()
        ),
    )
    return OpportunityWindow(
        window_id=window_id,
        timing_window=timing_window,
        state_hash=_command_reroll_opportunity_state_hash(state=state, decisions=decisions),
        sequence_number=sequence_number,
        revision=1,
        anchor_event_ids=(anchor_event_id,),
        acting_player_id=state.active_player_id,
        eligible_player_ids=(actor_id,),
        priority_order=(actor_id,),
        legal_actions=legal_actions,
        default_action_id=decline_option_id,
        metadata={
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "phase": phase.value,
        },
    )


def _command_reroll_opportunity_options(
    *,
    window: OpportunityWindow,
    player_id: str,
    use_options: tuple[DecisionOption, ...],
    decline_option: DecisionOption,
) -> tuple[DecisionOption, ...]:
    return tuple(
        _command_reroll_opportunity_option(
            window=window,
            player_id=player_id,
            option=option,
        )
        for option in (*use_options, decline_option)
    )


def _command_reroll_opportunity_option(
    *,
    window: OpportunityWindow,
    player_id: str,
    option: DecisionOption,
) -> DecisionOption:
    action = window.action_by_id(option.option_id)
    if not isinstance(option.payload, dict):
        raise GameLifecycleError("Command Re-roll opportunity option payload must be an object.")
    fingerprint = window.legal_action_fingerprint(player_id)
    payload = dict(option.payload)
    payload[OPPORTUNITY_SUBMISSION_PAYLOAD_KEY] = window.submission_payload_for_action(
        action=action,
        player_id=player_id,
        legal_action_fingerprint=fingerprint,
    )
    return DecisionOption(
        option_id=option.option_id,
        label=option.label,
        payload=validate_json_value(payload),
    )


def _command_reroll_opportunity_state_hash(
    *,
    state: GameState,
    decisions: DecisionController,
) -> str:
    records = decisions.event_log.records
    return opportunity_boundary_state_hash(
        state_payload=_command_reroll_opportunity_boundary_state_payload(state),
        event_count=len(records),
        last_event_id=None if not records else records[-1].event_id,
    )


def _command_reroll_opportunity_boundary_state_payload(state: GameState) -> JsonValue:
    return opportunity_boundary_game_state_payload(
        game_id=state.game_id,
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        stage=state.stage.value,
        battle_phase_index=state.battle_phase_index,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        decision_request_count=state.decision_request_count,
        command_point_ledgers=cast(
            JsonValue,
            [ledger.to_payload() for ledger in state.command_point_ledgers],
        ),
        stratagem_use_records=cast(
            JsonValue,
            [record.to_payload() for record in state.stratagem_use_records],
        ),
        faction_rule_states=cast(
            JsonValue,
            [record.to_payload() for record in state.faction_rule_states],
        ),
    )


def _dice_rolled_event_id_for_roll(*, decisions: DecisionController, roll_id: str) -> str:
    requested_roll_id = _validate_identifier("roll_id", roll_id)
    for event in decisions.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("dice_rolled event payload must be an object.")
        result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if result.roll_id == requested_roll_id:
            return event.event_id
    raise GameLifecycleError("Command Re-roll opportunity requires a recorded dice roll.")


__all__ = (
    "_command_reroll_opportunity_boundary_state_payload",
    "_command_reroll_opportunity_option",
    "_command_reroll_opportunity_options",
    "_command_reroll_opportunity_state_hash",
    "_command_reroll_opportunity_window",
    "_dice_rolled_event_id_for_roll",
    "request_command_reroll_if_available",
)
