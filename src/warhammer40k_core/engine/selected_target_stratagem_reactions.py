from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.target_replacement import (
    SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
    TargetReplacementContext,
    replacement_selection,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.stratagems import (
        StratagemCatalogIndex,
        StratagemEligibilityContext,
    )

_validate_identifier = IdentifierValidator(GameLifecycleError)


def request_after_unit_selected_as_target_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    attack_sequence: AttackSequence,
    phase: BattlePhase,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.stratagems import (
        SELECTED_TARGET_UNIT_CONTEXT_KEY,
        StratagemCatalogIndex,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(state) is not GameState:
        raise GameLifecycleError("Selected-as-target trigger requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Selected-as-target trigger requires DecisionController.")
    if type(stratagem_index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Selected-as-target trigger requires StratagemCatalogIndex.")
    if type(stratagem_cost_modifier_registry) is not StratagemCostModifierRegistry:
        raise GameLifecycleError(
            "Selected-as-target trigger requires StratagemCostModifierRegistry."
        )
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Selected-as-target trigger requires an AttackSequence.")
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("Selected-as-target trigger requires BattlePhase.")
    selection_id, target_unit_ids = _latest_target_selection(
        decisions=decisions, attack_sequence=attack_sequence
    )
    if not target_unit_ids:
        return None
    attacking_player_id = attack_sequence.attacker_player_id
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != attacking_player_id
    ):
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=reacting_player_id,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            timing_window_id=selected_as_target_timing_window_id(
                sequence_id=selection_id,
                player_id=reacting_player_id,
            ),
            trigger_payload={
                SELECTED_TARGET_UNIT_CONTEXT_KEY: list(target_unit_ids),
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "attacking_player_id": attacking_player_id,
                "attack_sequence_id": attack_sequence.sequence_id,
            },
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        if stratagem_used_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if not options:
            continue
        request = create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "unit_selected_as_target_stratagem_window_opened",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": phase.value,
                    "player_id": reacting_player_id,
                    "attacking_player_id": attacking_player_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "selected_target_unit_instance_ids": list(target_unit_ids),
                    "attack_sequence_id": attack_sequence.sequence_id,
                    "stratagem_context": context.to_payload(),
                    "request_id": request.request_id,
                    "phase_body_status": "unit_selected_as_target_stratagem_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": phase.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": reacting_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "phase_body_status": "unit_selected_as_target_stratagem_pending",
                "pending_request_id": request.request_id,
            },
        )
    return None


def _latest_target_selection(
    *, decisions: DecisionController, attack_sequence: AttackSequence
) -> tuple[str, tuple[str, ...]]:
    """A replacement is a new selection; a decline selects no targets.

    Use the authoritative decision history so restoration and repeated advances
    identify the same window without another mutable per-sequence counter.
    """
    for record in reversed(decisions.records):
        if record.request.decision_type != SELECT_TARGET_REPLACEMENT_DECISION_TYPE:
            continue
        context = TargetReplacementContext.from_payload(record.request.payload)
        if context.action_id != attack_sequence.sequence_id:
            continue
        targets = replacement_selection(
            request=record.request, result=record.result, current=context
        )
        return (
            f"target-replacement:{record.result.result_id}",
            () if targets is None else targets,
        )
    return attack_sequence.sequence_id, target_unit_ids_for_attack_sequence(attack_sequence)


def selected_as_target_timing_window_id(*, sequence_id: str, player_id: str) -> str:
    return (
        "selected-as-target:"
        f"{_validate_identifier('sequence_id', sequence_id)}:"
        f"player-{_validate_identifier('player_id', player_id)}"
    )


def target_unit_ids_for_attack_sequence(attack_sequence: AttackSequence) -> tuple[str, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Attack sequence target ids require an AttackSequence.")
    return tuple(sorted({pool.target_unit_instance_id for pool in attack_sequence.attack_pools}))


def stratagem_used_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    context_payload = context.to_payload()
    for record in decisions.event_log.records:
        if record.event_type != "stratagem_used":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Stratagem use event payload must be an object.")
        payload_object = cast(dict[str, object], payload)
        if (
            payload_object.get("game_id") == context_payload.get("game_id")
            and payload_object.get("player_id") == context_payload.get("player_id")
            and payload_object.get("battle_round") == context_payload.get("battle_round")
            and payload_object.get("phase") == context_payload.get("phase")
            and payload_object.get("active_player_id") == context_payload.get("active_player_id")
            and payload_object.get("timing_window_id") == context_payload.get("timing_window_id")
        ):
            return True
    return False
