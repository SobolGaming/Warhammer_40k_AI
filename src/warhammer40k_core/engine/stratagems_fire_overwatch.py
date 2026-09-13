"""Core Fire Overwatch delegates its phase-end attack to shared Snap Shooting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.shooting_requests import (
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import ShootingUnitSelectedGrantRegistry
from warhammer40k_core.engine.stratagems_model import (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemUseRecord,
)
from warhammer40k_core.engine.stratagems_validation import _require_target_unit_id
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionHookRegistry
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

__all__ = ("_apply_fire_overwatch_handler",)


def _apply_fire_overwatch_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> None:
    if context.trigger_kind is not TimingTriggerKind.END_PHASE:
        raise GameLifecycleError("Fire Overwatch requires the end of opponent Movement phase.")
    if context.phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("Fire Overwatch requires the Movement phase.")
    shooting_unit_id = _require_target_unit_id(target_binding)
    request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=use_record.player_id,
        unit_instance_id=shooting_unit_id,
        parent_phase=context.phase,
        source_rule_id=CORE_FIRE_OVERWATCH_HANDLER_ID,
        source_decision_request_id=use_record.request_id,
        source_decision_result_id=use_record.result_id,
        source_context=validate_json_value(
            {
                "source_kind": "fire_overwatch",
                "stratagem_use": use_record.to_payload(),
                "trigger_kind": context.trigger_kind.value,
                "trigger_payload": context.trigger_payload,
            }
        ),
        shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    decisions.event_log.append(
        "fire_overwatch_shooting_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "shooting_unit_instance_id": shooting_unit_id,
        },
    )
