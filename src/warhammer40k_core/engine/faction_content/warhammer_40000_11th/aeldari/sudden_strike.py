"""Battle Focus resource orchestration at the current source charge-end window."""

from __future__ import annotations

# The named army-rule owner retains its bespoke resource accounting.
# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import army_rule
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
)
from warhammer40k_core.engine.move_completion_effects import (
    MoveCompletionEffectGrant,
    optional_move_completion_effect_binding,
)
from warhammer40k_core.engine.move_completion_rule_hooks import MoveCompletionRuleBinding
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext


def binding() -> MoveCompletionRuleBinding:
    return optional_move_completion_effect_binding(
        hook_id=army_rule.SUDDEN_STRIKE_HOOK_ID,
        source_rule_id=army_rule.SOURCE_RULE_ID,
        owns_trigger=_owns_trigger,
        grant_for=grant_for,
    )


def _owns_trigger(context: UnitMoveCompletedContext) -> bool:
    # Capture the army source occurrence independently of mutable tokens/quotas.
    # Actual unit eligibility is checked when its optional choice is reached.
    if context.movement_action != "charge_move":
        return False
    army = context.state.army_definition_for_player(context.triggering_player_id)
    return army is not None and army.detachment_selection.faction_id == army_rule.AELDARI_FACTION_ID


def grant_for(context: UnitMoveCompletedContext) -> MoveCompletionEffectGrant | None:
    if not _owns_trigger(context):
        return None
    state = context.state
    army = state.army_definition_for_player(context.triggering_player_id)
    if army is None:
        raise GameLifecycleError("Sudden Strike source army is missing.")
    view = rules_unit_view_by_id(state=state, unit_instance_id=context.triggering_unit_instance_id)
    if view.owner_player_id != context.triggering_player_id:
        raise GameLifecycleError("Sudden Strike moving unit owner drift.")
    if not view.alive_models() or not any(
        ability.ability_id == "000009894"
        for component in view.rules_present_components
        for ability in component.unit.datasheet_abilities
    ):
        return None
    if army_rule._battle_focus_tokens_remaining(state=state, army=army) <= 0:
        return None
    if army_rule.rules_unit_already_performed_agile_manoeuvre_this_phase(
        state=state,
        player_id=context.triggering_player_id,
        battle_round=state.battle_round,
        phase=context.completed_phase,
        unit_instance_id=view.unit_instance_id,
    ):
        return None
    if army_rule._maneuver_already_used_this_phase(
        state=state,
        player_id=context.triggering_player_id,
        battle_round=state.battle_round,
        phase=context.completed_phase,
        maneuver=army_rule.SUDDEN_STRIKE_MANEUVER,
    ):
        return None
    if state.active_player_id is None:
        raise GameLifecycleError("Sudden Strike requires its source turn owner.")
    spend: dict[str, JsonValue] = {
        "effect_kind": army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        "maneuver": army_rule.SUDDEN_STRIKE_MANEUVER,
        "unit_instance_id": view.unit_instance_id,
        "battle_focus_token_cost": 1,
        "trigger_event_id": context.trigger_event_id,
        "turn_player_id": state.active_player_id,
    }
    return MoveCompletionEffectGrant(
        label="Battle Focus: Sudden Strike",
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round, player_id=state.active_player_id
        ),
        effect_payload={
            "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
            "source_id": army_rule.SOURCE_RULE_ID,
            "unit_instance_id": view.unit_instance_id,
            "trigger_event_id": context.trigger_event_id,
            "pile_in_distance_inches": 6.0,
            "consolidate_distance_inches": 6.0,
        },
        decision_effect_payload=army_rule.battle_focus_spend_payload_for_rules_unit(
            state=state,
            player_id=context.triggering_player_id,
            unit_instance_id=view.unit_instance_id,
            payload=spend,
        ),
    )
