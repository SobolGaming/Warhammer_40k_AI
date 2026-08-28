from __future__ import annotations

from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext


def historical_battle_shock_context_for_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    active_player_id: str,
    phase: BattlePhase = BattlePhase.COMMAND,
    reason: BattleShockTestReason = BattleShockTestReason.COMMAND_PHASE_REQUIRED,
    phase_start_battle_shocked_unit_ids: tuple[str, ...] = (),
) -> HistoricalBattleShockAuthorityContext:
    """Build one real event-bound context for faction-provider history regressions."""

    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    alive_model_ids = tuple(sorted(model.model_instance_id for model in rules_unit.alive_models()))
    request = BattleShockTestRequest.for_unit(
        request_id=(
            f"battle-shock-history:{state.battle_round:02d}:"
            f"{active_player_id}:{rules_unit.unit_instance_id}:{reason.value}"
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=rules_unit.owner_player_id,
        unit_instance_id=rules_unit.unit_instance_id,
        reason=reason,
        leadership_target=7,
        below_half_strength_context=BelowHalfStrengthContext.from_rules_unit(
            rules_unit=rules_unit,
            starting_strength=state.starting_strength_record_for_unit(rules_unit.unit_instance_id),
            current_model_ids=alive_model_ids,
        ),
    )
    decisions.event_log.append(
        "battle_shock_test_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": phase.value,
                "source_kind": "command_battle_shock",
                "battle_shock_test_request": request.to_payload(),
            }
        ),
    )
    event_records = decisions.event_log.records
    return historical_battle_shock_authority_context(
        state=state,
        event_records=event_records,
        decision_records=decisions.records,
        boundary_event_index=len(event_records) - 1,
        request=request,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
    )


__all__ = ("historical_battle_shock_context_for_unit",)
