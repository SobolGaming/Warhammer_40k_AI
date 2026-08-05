from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import DiceRollState, RerollPermission
from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    SelectedTargetChargeConstraint,
)
from warhammer40k_core.engine.charge_declaration import (
    CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID,
    ChargeRollRequest,
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    required_charge_target_unit_instance_ids,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def build_charge_roll_reroll_request(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_request: ChargeRollRequest,
    roll_state: DiceRollState,
    permission: RerollPermission,
    selected_target_constraint: SelectedTargetChargeConstraint | None,
    legal_target_unit_instance_ids: tuple[str, ...],
) -> DecisionRequest:
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    required_target_ids = required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=roll_request.unit_instance_id,
        reachable_target_unit_instance_ids=legal_target_unit_instance_ids,
    )
    return manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=roll_request.player_id,
        permission=permission,
        ignored_reroll_forbidden_rule_ids=(CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID,),
        extra_payload={
            "charge_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": roll_request.unit_instance_id,
                "charge_roll_request": validate_json_value(roll_request.to_payload()),
                "charge_roll_state": validate_json_value(roll_state.to_payload()),
                "legal_target_unit_instance_ids": list(legal_target_unit_instance_ids),
                CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
                "selected_target_charge_constraint": (
                    None
                    if selected_target_constraint is None
                    else selected_target_constraint.to_payload()
                ),
            }
        },
    )
