from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierBinding,
    StratagemCostModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)

CONTRIBUTION_ID = (
    "warhammer_40000_11th:emperors_children:detachment:court_of_the_phoenician:rule:rule_ir"
)
MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID = (
    "warhammer_40000_11th:emperors_children:detachment:"
    "court_of_the_phoenician:master_of_the_pageant:cp_cost_reduction"
)
COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID = (
    "gw-11e-phase17e-faction-coverage-2026-27:phase17e:"
    "emperors-children:court-of-the-phoenician:rule:source-text"
)
MASTER_OF_THE_PAGEANT_ABILITY = "stratagem_cp_cost_reduction"
MASTER_OF_THE_PAGEANT_STRATAGEM_IDS = frozenset({"000010655003", "000010655004"})


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_cost_modifier_bindings=(
            StratagemCostModifierBinding(
                modifier_id=MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID,
                source_id=COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID,
                handler=master_of_the_pageant_command_point_cost_modifier,
            ),
        ),
    )


def master_of_the_pageant_command_point_cost_modifier(
    context: StratagemCostModifierContext,
) -> int:
    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Master of the Pageant requires cost modifier context.")
    if context.definition.stratagem_id not in MASTER_OF_THE_PAGEANT_STRATAGEM_IDS:
        return context.current_command_point_cost
    if context.target_binding is None or context.target_binding.target_unit_instance_id is None:
        return context.current_command_point_cost
    target_unit = _unit_by_id(
        state=context.state,
        unit_instance_id=context.target_binding.target_unit_instance_id,
    )
    if not _unit_has_keyword(target_unit, court_ir.FULGRIM_KEYWORD):
        return context.current_command_point_cost
    if not _player_has_master_of_the_pageant_effect(
        context=context,
        player_id=context.eligibility_context.player_id,
    ):
        return context.current_command_point_cost
    if _master_of_the_pageant_used_this_battle_round(
        context=context,
        player_id=context.eligibility_context.player_id,
    ):
        return context.current_command_point_cost
    return max(0, context.current_command_point_cost - 1)


def _player_has_master_of_the_pageant_effect(
    *,
    context: StratagemCostModifierContext,
    player_id: str,
) -> bool:
    for effect in context.state.persisting_effects:
        if effect.owner_player_id != player_id:
            continue
        if effect.source_rule_id != COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Master of the Pageant effect payload must be an object.")
        if generic_rule_effect_payload_grants_ability(
            payload,
            ability=MASTER_OF_THE_PAGEANT_ABILITY,
        ):
            return True
    return False


def _master_of_the_pageant_used_this_battle_round(
    *,
    context: StratagemCostModifierContext,
    player_id: str,
) -> bool:
    for record in context.state.stratagem_use_records_for_player(player_id):
        if record.battle_round != context.state.battle_round:
            continue
        if MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID in record.command_point_modifier_ids:
            return True
    return False


def _unit_by_id(*, state: object, unit_instance_id: str) -> UnitInstance:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Master of the Pageant unit lookup requires GameState.")
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise GameLifecycleError("Master of the Pageant target unit is unknown.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Master of the Pageant keyword lookup requires UnitInstance.")
    return keyword in (*unit.keywords, *unit.faction_keywords)
