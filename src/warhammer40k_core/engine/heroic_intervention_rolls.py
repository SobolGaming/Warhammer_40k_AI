from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.charge_roll_permissions import charge_reroll_permission_for_unit
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import (
        StratagemDefinition,
        StratagemEligibilityContext,
        StratagemTargetBinding,
        StratagemUseRecord,
    )


def is_heroic_charge_reroll(request: DecisionRequest) -> bool:
    return (
        request.decision_type == DICE_REROLL_DECISION_TYPE
        and isinstance(request.payload, dict)
        and "heroic_intervention_reroll_context" in request.payload
    )


def validate_heroic_charge_reroll(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    ability_index: AbilityCatalogIndex,
) -> tuple[StratagemUseRecord, str, DiceRollState]:
    from warhammer40k_core.engine.stratagem_use_history_authority import (
        validate_stratagem_use_history,
    )
    from warhammer40k_core.engine.stratagems_model import (
        StratagemUseRecord,
        StratagemUseRecordPayload,
    )
    from warhammer40k_core.engine.stratagems_selection import _heroic_intervention_mode

    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Heroic reroll payload must be an object.")
    context = request.payload.get("heroic_intervention_reroll_context")
    if not isinstance(context, dict) or set(context) != {"stratagem_use", "mode", "roll_state"}:
        raise GameLifecycleError("Heroic reroll context is malformed.")
    use_payload, roll_payload = context["stratagem_use"], context["roll_state"]
    if not isinstance(use_payload, dict) or not isinstance(roll_payload, dict):
        raise GameLifecycleError("Heroic reroll source is malformed.")
    use = StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, use_payload))
    history = validate_stratagem_use_history(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        use_record=use,
        mutation_index=len(decisions.event_log.records),
    )
    mode = _heroic_intervention_mode(
        definition=history.catalog_record.definition, effect_selection=use.effect_selection
    )
    if (
        use.handler_id != "core:heroic-intervention"
        or context["mode"] != mode
        or state.current_battle_phase is not BattlePhase.CHARGE
        or use.battle_round != state.battle_round
        or use.active_player_id != state.active_player_id
        or request.actor_id != use.player_id
    ):
        raise GameLifecycleError("Heroic reroll phase or source authority drift.")
    unit_id = use.target_binding.target_unit_instance_id
    if unit_id is None:
        raise GameLifecycleError("Heroic reroll has no target unit.")
    roll = DiceRollState.from_payload(cast(DiceRollStatePayload, roll_payload))
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason=f"Heroic Intervention charge roll for {use.use_id}",
        roll_type="charge_roll",
        actor_id=use.player_id,
    )
    if roll.original_result.spec != spec or roll.rerolls:
        raise GameLifecycleError("Heroic reroll original dice drift.")
    if (
        sum(
            e.event_type == "dice_rolled" and e.payload == roll.original_result.to_payload()
            for e in decisions.event_log.records
        )
        != 1
    ):
        raise GameLifecycleError("Heroic reroll requires unique recorded dice.")
    permission = charge_reroll_permission_for_unit(
        state=state,
        player_id=use.player_id,
        unit_instance_id=unit_id,
        ability_index=ability_index,
    )
    if permission is None:
        raise GameLifecycleError("Heroic reroll ability is no longer available.")
    expected = DiceRollManager(state.game_id).build_reroll_request(
        roll,
        request_id=request.request_id,
        actor_id=use.player_id,
        permission=permission,
        extra_payload={"heroic_intervention_reroll_context": context},
    )
    if expected != request:
        raise GameLifecycleError("Heroic reroll permission or options drift.")
    return use, mode, roll


def apply_heroic_charge_reroll(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    ability_index: AbilityCatalogIndex,
) -> None:
    use, mode, roll = validate_heroic_charge_reroll(
        state=state,
        decisions=decisions,
        request=request,
        ability_index=ability_index,
    )
    updated = DiceRollManager(state.game_id, event_log=decisions.event_log).resolve_reroll(
        roll,
        request=request,
        result=result,
        record_decision=False,
    )
    request_heroic_charge_move(
        state=state, decisions=decisions, use_record=use, mode=mode, roll_state=updated
    )


def _apply_heroic_intervention_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ability_index: AbilityCatalogIndex,
) -> None:
    from warhammer40k_core.engine.stratagems_selection import _heroic_intervention_mode
    from warhammer40k_core.engine.stratagems_validation import _require_target_unit_id

    target_unit_id = _require_target_unit_id(target_binding)
    mode = _heroic_intervention_mode(
        definition=definition,
        effect_selection=use_record.effect_selection,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Heroic Intervention charge roll for {use_record.use_id}",
            roll_type="charge_roll",
            actor_id=use_record.player_id,
        )
    )
    permission = charge_reroll_permission_for_unit(
        state=state,
        player_id=use_record.player_id,
        unit_instance_id=target_unit_id,
        ability_index=ability_index,
    )
    if permission is not None:
        request = manager.build_reroll_request(
            roll_state,
            request_id=state.next_decision_request_id(),
            actor_id=use_record.player_id,
            permission=permission,
            extra_payload={
                "heroic_intervention_reroll_context": {
                    "stratagem_use": validate_json_value(use_record.to_payload()),
                    "mode": mode,
                    "roll_state": validate_json_value(roll_state.to_payload()),
                }
            },
        )
        decisions.request_decision(request)
        return
    request_heroic_charge_move(
        state=state, decisions=decisions, use_record=use_record, mode=mode, roll_state=roll_state
    )


def request_heroic_charge_move(
    *,
    state: GameState,
    decisions: DecisionController,
    use_record: StratagemUseRecord,
    mode: str,
    roll_state: DiceRollState,
) -> None:
    from warhammer40k_core.engine.stratagems_effect_handlers import (
        _heroic_intervention_reachable_target_distances,
    )
    from warhammer40k_core.engine.stratagems_model import (
        CORE_HEROIC_INTERVENTION_HANDLER_ID,
        HEROIC_INTERVENTION_MODE_INTO_THE_FRAY,
    )
    from warhammer40k_core.engine.stratagems_validation import _require_target_unit_id

    target_unit_id = _require_target_unit_id(use_record.target_binding)
    maximum_distance = roll_state.current_total
    if mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY and maximum_distance > 6:
        maximum_distance = 6
    reachable = _heroic_intervention_reachable_target_distances(
        state=state,
        player_id=use_record.player_id,
        heroic_unit_id=target_unit_id,
        mode=mode,
        maximum_distance_inches=maximum_distance,
    )
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=use_record.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=target_unit_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=use_record.request_id,
        source_decision_result_id=use_record.result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action="charge_move",
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": CORE_HEROIC_INTERVENTION_HANDLER_ID,
                    "stratagem_use": use_record.to_payload(),
                    "mode": mode,
                    "movement_mode": MovementMode.CHARGE.value,
                    "charge_roll_state": roll_state.to_payload(),
                    "maximum_distance_inches": maximum_distance,
                    "reachable_target_unit_instance_ids": list(reachable),
                    "reachable_target_distances_inches": reachable,
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "heroic_intervention_charge_move_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "mode": mode,
            "charge_roll_state": roll_state.to_payload(),
            "maximum_distance_inches": maximum_distance,
            "reachable_target_unit_instance_ids": list(reachable),
            "reachable_target_distances_inches": reachable,
            "request_id": request.request_id,
        },
    )


__all__ = (
    "_apply_heroic_intervention_handler",
    "apply_heroic_charge_reroll",
    "is_heroic_charge_reroll",
    "request_heroic_charge_move",
    "validate_heroic_charge_reroll",
)
