from __future__ import annotations

from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookBinding,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectContext,
    EnhancementPersistingEffectGrant,
    EnhancementUnitKeywordGrant,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    army_for_player as _shared_army_for_player,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_bool,
    payload_identifier,
    payload_object,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    SaveOptionModifierBinding,
    SaveOptionModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
    StratagemCostChoiceHookBinding,
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
    source_result_payload_for_cost_choice,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierBinding,
    StratagemCostModifierContext,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_corsair_coterie_ir_support_2026_27 as corsair_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:enhancements:scaffold"
ARCHRAIDER_SOURCE_RULE_ID = corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
INFAMY_SOURCE_RULE_ID = corsair_ir.INFAMY_SOURCE_RULE_ID
VOIDSTONE_SOURCE_RULE_ID = corsair_ir.VOIDSTONE_SOURCE_RULE_ID
WEBWAY_PATHSTONE_SOURCE_RULE_ID = corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
CORSAIR_COTERIE_DETACHMENT_ID = "corsair-coterie"
AELDARI_FACTION_ID = "aeldari"
ANHRATHE = "ANHRATHE"
DEEP_STRIKE = "DEEP STRIKE"

ARCHRAIDER_ENHANCEMENT_ID = "archraider"
INFAMY_ENHANCEMENT_ID = "infamy"
VOIDSTONE_ENHANCEMENT_ID = "voidstone"
WEBWAY_PATHSTONE_ENHANCEMENT_ID = "webway-pathstone"

ARCHRAIDER_EFFECT_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:archraider"
INFAMY_EFFECT_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:infamy"
VOIDSTONE_EFFECT_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:voidstone"
WEBWAY_PATHSTONE_EFFECT_ID = (
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:webway_pathstone"
)
WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID = f"{WEBWAY_PATHSTONE_EFFECT_ID}:deep_strike"
ARCHRAIDER_SETUP_HOOK_ID = f"{ARCHRAIDER_EFFECT_ID}:select_model"
ARCHRAIDER_COST_CHOICE_HOOK_ID = f"{ARCHRAIDER_EFFECT_ID}:lord_of_deceit_choice"
ARCHRAIDER_COST_MODIFIER_ID = f"{ARCHRAIDER_EFFECT_ID}:lord_of_deceit"
INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID = f"{INFAMY_EFFECT_ID}:objective_control"
VOIDSTONE_SAVE_MODIFIER_ID = f"{VOIDSTONE_EFFECT_ID}:save_option"
WEBWAY_PATHSTONE_TURN_END_HOOK_ID = f"{WEBWAY_PATHSTONE_EFFECT_ID}:turn_end_reserves"

ARCHRAIDER_STATE_KIND = "aeldari_corsair_coterie_archraider_model"
ARCHRAIDER_EFFECT_KIND = "aeldari_corsair_coterie_archraider"
INFAMY_EFFECT_KIND = "aeldari_corsair_coterie_infamy"
VOIDSTONE_EFFECT_KIND = "aeldari_corsair_coterie_voidstone"
WEBWAY_PATHSTONE_EFFECT_KIND = "aeldari_corsair_coterie_webway_pathstone"

INFAMY_AURA_RANGE_INCHES = 3.0
ARCHRAIDER_AURA_RANGE_INCHES = 12.0

WEBWAY_PATHSTONE_USED_EVENT = "aeldari_corsair_coterie_webway_pathstone_used"
WEBWAY_PATHSTONE_DECLINED_EVENT = "aeldari_corsair_coterie_webway_pathstone_declined"
ARCHRAIDER_MODEL_SELECTED_EVENT = "aeldari_corsair_coterie_archraider_model_selected"
ARCHRAIDER_COST_MODIFIER_USED_EVENT = "aeldari_corsair_coterie_lord_of_deceit_used"
ARCHRAIDER_COST_MODIFIER_DECLINED_EVENT = "aeldari_corsair_coterie_lord_of_deceit_declined"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_formation_hook_bindings=(
            BattleFormationHookBinding(
                hook_id=ARCHRAIDER_SETUP_HOOK_ID,
                source_id=ARCHRAIDER_SOURCE_RULE_ID,
                request_handler=archraider_model_selection_request,
                result_handler=apply_archraider_model_selection_result,
            ),
        ),
        stratagem_cost_choice_hook_bindings=(
            StratagemCostChoiceHookBinding(
                hook_id=ARCHRAIDER_COST_CHOICE_HOOK_ID,
                source_id=ARCHRAIDER_SOURCE_RULE_ID,
                request_handler=archraider_command_point_cost_choice_request,
                result_handler=apply_archraider_command_point_cost_choice_result,
            ),
        ),
        stratagem_cost_modifier_bindings=(
            StratagemCostModifierBinding(
                modifier_id=ARCHRAIDER_COST_MODIFIER_ID,
                source_id=ARCHRAIDER_SOURCE_RULE_ID,
                handler=archraider_command_point_cost_modifier,
            ),
        ),
        save_option_modifier_bindings=(
            SaveOptionModifierBinding(
                modifier_id=VOIDSTONE_SAVE_MODIFIER_ID,
                source_id=VOIDSTONE_SOURCE_RULE_ID,
                handler=voidstone_save_option_modifier,
            ),
        ),
    )


def archraider_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    return _persisting_enhancement_effect(
        context=context,
        enhancement_id=ARCHRAIDER_ENHANCEMENT_ID,
        effect_id=ARCHRAIDER_EFFECT_ID,
        effect_kind=ARCHRAIDER_EFFECT_KIND,
        source_rule_id=ARCHRAIDER_SOURCE_RULE_ID,
    )


def infamy_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    return _persisting_enhancement_effect(
        context=context,
        enhancement_id=INFAMY_ENHANCEMENT_ID,
        effect_id=INFAMY_EFFECT_ID,
        effect_kind=INFAMY_EFFECT_KIND,
        source_rule_id=INFAMY_SOURCE_RULE_ID,
    )


def voidstone_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    return _persisting_enhancement_effect(
        context=context,
        enhancement_id=VOIDSTONE_ENHANCEMENT_ID,
        effect_id=VOIDSTONE_EFFECT_ID,
        effect_kind=VOIDSTONE_EFFECT_KIND,
        source_rule_id=VOIDSTONE_SOURCE_RULE_ID,
    )


def webway_pathstone_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    return _persisting_enhancement_effect(
        context=context,
        enhancement_id=WEBWAY_PATHSTONE_ENHANCEMENT_ID,
        effect_id=WEBWAY_PATHSTONE_EFFECT_ID,
        effect_kind=WEBWAY_PATHSTONE_EFFECT_KIND,
        source_rule_id=WEBWAY_PATHSTONE_SOURCE_RULE_ID,
    )


def webway_pathstone_deep_strike_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementUnitKeywordGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Webway Pathstone requires EnhancementEffectContext.")
    if context.assignment.enhancement_id != WEBWAY_PATHSTONE_ENHANCEMENT_ID:
        return ()
    _validate_corsair_coterie_army(context.army, label="Webway Pathstone")
    return (
        EnhancementUnitKeywordGrant(
            effect_id=WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID,
            source_id=WEBWAY_PATHSTONE_SOURCE_RULE_ID,
            enhancement_id=WEBWAY_PATHSTONE_ENHANCEMENT_ID,
            target_unit_instance_id=context.target_unit.unit_instance_id,
            keyword=DEEP_STRIKE,
            replay_payload={
                "effect_kind": f"{WEBWAY_PATHSTONE_EFFECT_KIND}_deep_strike",
                "target_unit_instance_id": context.target_unit.unit_instance_id,
                "granted_keyword": DEEP_STRIKE,
            },
        ),
    )


def _persisting_enhancement_effect(
    *,
    context: EnhancementEffectContext,
    enhancement_id: str,
    effect_id: str,
    effect_kind: str,
    source_rule_id: str,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Corsair Coterie requires EnhancementEffectContext.")
    if context.assignment.enhancement_id != enhancement_id:
        return ()
    _validate_corsair_coterie_army(context.army, label=enhancement_id)
    effect = PersistingEffect(
        effect_id=f"{effect_id}:{context.target_unit.unit_instance_id}",
        source_rule_id=source_rule_id,
        owner_player_id=context.army.player_id,
        target_unit_instance_ids=(context.target_unit.unit_instance_id,),
        started_battle_round=context.state.battle_round,
        started_phase=None,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={
            "effect_kind": effect_kind,
            "enhancement_id": enhancement_id,
            "assignment_source_id": context.assignment.source_id,
            "target_unit_instance_id": context.target_unit.unit_instance_id,
        },
    )
    return (
        EnhancementPersistingEffectGrant(
            effect_id=effect_id,
            source_id=source_rule_id,
            enhancement_id=enhancement_id,
            target_unit_instance_id=context.target_unit.unit_instance_id,
            persisting_effect=effect,
            replay_payload={
                "effect_kind": effect_kind,
                "enhancement_id": enhancement_id,
                "target_unit_instance_id": context.target_unit.unit_instance_id,
            },
        ),
    )


def archraider_model_selection_request(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleFormationRequestContext:
        raise GameLifecycleError("Archraider requires a battle-formation request context.")
    for army in _corsair_coterie_armies(context.state):
        for assignment, unit in _assigned_units(army, enhancement_id=ARCHRAIDER_ENHANCEMENT_ID):
            if (
                _archraider_state_for_unit(
                    context.state,
                    player_id=army.player_id,
                    unit_instance_id=unit.unit_instance_id,
                )
                is not None
            ):
                continue
            options = _archraider_model_options(
                player_id=army.player_id,
                assignment=assignment,
                unit=unit,
            )
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    "faction_id": AELDARI_FACTION_ID,
                    "detachment_id": CORSAIR_COTERIE_DETACHMENT_ID,
                    "source_rule_id": ARCHRAIDER_SOURCE_RULE_ID,
                    "hook_id": ARCHRAIDER_SETUP_HOOK_ID,
                    "state_kind": ARCHRAIDER_STATE_KIND,
                    "target_unit_instance_id": unit.unit_instance_id,
                    "enhancement_id": ARCHRAIDER_ENHANCEMENT_ID,
                },
                options=options,
            )
    return None


def apply_archraider_model_selection_result(context: BattleFormationResultContext) -> bool:
    if type(context) is not BattleFormationResultContext:
        raise GameLifecycleError("Archraider requires a battle-formation result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != ARCHRAIDER_SETUP_HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    player_id = _payload_string(result_payload, "player_id")
    unit_instance_id = _payload_string(result_payload, "target_unit_instance_id")
    selected_model_id = _payload_string(result_payload, "selected_model_instance_id")
    army = _army_for_player(tuple(context.state.army_definitions), player_id=player_id)
    unit = _unit_in_army_by_id(army, unit_instance_id=unit_instance_id)
    if not any(model.model_instance_id == selected_model_id for model in unit.own_models):
        raise GameLifecycleError("Archraider selected model is not in the enhanced unit.")
    if (
        _archraider_state_for_unit(
            context.state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
        )
        is not None
    ):
        raise GameLifecycleError("Archraider model is already selected.")
    state_record = FactionRuleState(
        state_id=f"{ARCHRAIDER_SETUP_HOOK_ID}:{unit_instance_id}:selected-model",
        player_id=player_id,
        faction_id=AELDARI_FACTION_ID,
        source_rule_id=ARCHRAIDER_SOURCE_RULE_ID,
        state_kind=ARCHRAIDER_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "effect_kind": ARCHRAIDER_EFFECT_KIND,
                "detachment_id": CORSAIR_COTERIE_DETACHMENT_ID,
                "enhancement_id": ARCHRAIDER_ENHANCEMENT_ID,
                "hook_id": ARCHRAIDER_SETUP_HOOK_ID,
                "target_unit_instance_id": unit_instance_id,
                "selected_model_instance_id": selected_model_id,
                "selected_option_id": context.result.selected_option_id,
            }
        ),
    )
    context.state.record_faction_rule_state(state_record)
    context.decisions.event_log.append(
        ARCHRAIDER_MODEL_SELECTED_EVENT,
        {
            "game_id": context.state.game_id,
            "player_id": player_id,
            "source_rule_id": ARCHRAIDER_SOURCE_RULE_ID,
            "hook_id": ARCHRAIDER_SETUP_HOOK_ID,
            "target_unit_instance_id": unit_instance_id,
            "selected_model_instance_id": selected_model_id,
            "faction_rule_state": validate_json_value(state_record.to_payload()),
        },
    )
    return True


def archraider_command_point_cost_modifier(context: StratagemCostModifierContext) -> int:
    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Archraider CP modifier requires context.")
    if not _archraider_cost_choice_used_for_source_result(context):
        return context.current_command_point_cost
    target = context.target_binding
    if target is None or target.target_unit_instance_id is None or target.target_player_id is None:
        return context.current_command_point_cost
    if target.target_player_id != context.eligibility_context.player_id:
        return context.current_command_point_cost
    for army in _corsair_coterie_armies(context.state):
        if army.player_id == context.eligibility_context.player_id:
            continue
        if _archraider_used_this_turn(
            context.state,
            decisions=context.decisions,
            player_id=army.player_id,
            active_player_id=context.eligibility_context.active_player_id,
            source_decision_result_id=context.source_decision_result_id,
        ):
            continue
        selected_model_ids = _selected_archraider_model_ids(
            context.state,
            player_id=army.player_id,
        )
        if any(
            _model_within_unit_range(
                state=context.state,
                model_instance_id=model_id,
                target_unit_instance_id=target.target_unit_instance_id,
                range_inches=ARCHRAIDER_AURA_RANGE_INCHES,
            )
            for model_id in selected_model_ids
        ):
            return context.current_command_point_cost + 1
    return context.current_command_point_cost


def archraider_command_point_cost_choice_request(
    context: StratagemCostChoiceRequestContext,
) -> DecisionRequest | None:
    if type(context) is not StratagemCostChoiceRequestContext:
        raise GameLifecycleError("Archraider requires a stratagem cost choice context.")
    target = context.target_binding
    if target.target_unit_instance_id is None or target.target_player_id is None:
        return None
    if target.target_player_id != context.eligibility_context.player_id:
        return None
    for army in _corsair_coterie_armies(context.state):
        if army.player_id == context.eligibility_context.player_id:
            continue
        if _archraider_used_this_turn(
            context.state,
            decisions=context.decisions,
            player_id=army.player_id,
            active_player_id=context.eligibility_context.active_player_id,
            source_decision_result_id=None,
        ):
            continue
        eligible_model_ids = _eligible_archraider_model_ids_for_target(
            state=context.state,
            player_id=army.player_id,
            target_unit_instance_id=target.target_unit_instance_id,
        )
        if not eligible_model_ids:
            continue
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload={
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.eligibility_context.active_player_id,
                "phase": context.eligibility_context.phase.value,
                "source_rule_id": ARCHRAIDER_SOURCE_RULE_ID,
                "hook_id": ARCHRAIDER_COST_CHOICE_HOOK_ID,
                "modifier_id": ARCHRAIDER_COST_MODIFIER_ID,
                "enhancement_id": ARCHRAIDER_ENHANCEMENT_ID,
                "stratagem_id": context.definition.stratagem_id,
                "stratagem_player_id": context.eligibility_context.player_id,
                "target_unit_instance_id": target.target_unit_instance_id,
                "eligible_model_instance_ids": list(eligible_model_ids),
                "source_decision_request_id": context.source_request.request_id,
                "source_decision_result_id": context.source_result.result_id,
                "source_decision_result": source_result_payload_for_cost_choice(
                    context.source_result
                ),
            },
            options=(
                _archraider_cost_choice_option(
                    player_id=army.player_id,
                    target_unit_instance_id=target.target_unit_instance_id,
                    source_decision_request_id=context.source_request.request_id,
                    source_decision_result_id=context.source_result.result_id,
                    use_ability=True,
                ),
                _archraider_cost_choice_option(
                    player_id=army.player_id,
                    target_unit_instance_id=target.target_unit_instance_id,
                    source_decision_request_id=context.source_request.request_id,
                    source_decision_result_id=context.source_result.result_id,
                    use_ability=False,
                ),
            ),
        )
    return None


def apply_archraider_command_point_cost_choice_result(
    context: StratagemCostChoiceResultContext,
) -> bool:
    if type(context) is not StratagemCostChoiceResultContext:
        raise GameLifecycleError("Archraider requires a stratagem cost choice result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != ARCHRAIDER_COST_CHOICE_HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    player_id = _payload_string(result_payload, "player_id")
    target_unit_instance_id = _payload_string(result_payload, "target_unit_instance_id")
    source_decision_request_id = _payload_string(result_payload, "source_decision_request_id")
    source_decision_result_id = _payload_string(result_payload, "source_decision_result_id")
    if source_decision_request_id != context.source_request.request_id:
        raise GameLifecycleError("Archraider source request drift.")
    if source_decision_result_id != context.source_result.result_id:
        raise GameLifecycleError("Archraider source result drift.")
    use_ability = _payload_bool(result_payload, "use_ability")
    if use_ability:
        eligible_model_ids = _eligible_archraider_model_ids_for_target(
            state=context.state,
            player_id=player_id,
            target_unit_instance_id=target_unit_instance_id,
        )
        if not eligible_model_ids:
            raise GameLifecycleError("Archraider target is no longer eligible.")
        if _archraider_used_this_turn(
            context.state,
            decisions=context.decisions,
            player_id=player_id,
            active_player_id=context.eligibility_context.active_player_id,
            source_decision_result_id=None,
        ):
            raise GameLifecycleError("Archraider has already been used this turn.")
    context.decisions.event_log.append(
        ARCHRAIDER_COST_MODIFIER_USED_EVENT
        if use_ability
        else ARCHRAIDER_COST_MODIFIER_DECLINED_EVENT,
        _archraider_cost_choice_event_payload(
            context=context,
            player_id=player_id,
            target_unit_instance_id=target_unit_instance_id,
            use_ability=use_ability,
        ),
    )
    return True


def infamy_objective_control_modifier(context: ObjectiveControlModifierContext) -> int:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Infamy Objective Control modifier requires context.")
    if not _unit_is_afflicted_by_infamy(
        state=context.state,
        target_unit_instance_id=context.unit_instance_id,
    ):
        return context.current_objective_control
    return max(1, context.current_objective_control - 1)


def voidstone_save_option_modifier(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Voidstone save option modifier requires context.")
    if not _unit_has_persisting_effect(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
        effect_kind=VOIDSTONE_EFFECT_KIND,
    ):
        return context.save_options
    if any(
        option.save_kind is SaveKind.INVULNERABLE and option.target_number <= 5
        for option in context.save_options
    ):
        return context.save_options
    armor_penetration = context.save_options[0].armor_penetration if context.save_options else 0
    return tuple(
        sorted(
            (
                *context.save_options,
                SaveOption(
                    save_kind=SaveKind.INVULNERABLE,
                    target_number=5,
                    characteristic_target_number=5,
                    armor_penetration=armor_penetration,
                    source_rule_ids=(VOIDSTONE_SOURCE_RULE_ID,),
                ),
            ),
            key=lambda option: (option.save_kind.value, option.target_number),
        )
    )


def webway_pathstone_turn_end_request(context: TurnEndRequestContext) -> DecisionRequest | None:
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Webway Pathstone requires a turn-end request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return None
    active_player_id = _active_player_id(context.state)
    for army in _corsair_coterie_armies(context.state):
        if army.player_id == active_player_id:
            continue
        for _assignment, unit in _assigned_units(
            army,
            enhancement_id=WEBWAY_PATHSTONE_ENHANCEMENT_ID,
        ):
            if _webway_pathstone_decision_recorded_this_turn(
                context,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            if _webway_pathstone_used_this_battle(
                context.decisions,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            if not _webway_pathstone_unit_can_enter_reserves(
                context.state,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": context.completed_phase.value,
                    "source_rule_id": WEBWAY_PATHSTONE_SOURCE_RULE_ID,
                    "hook_id": WEBWAY_PATHSTONE_TURN_END_HOOK_ID,
                    "enhancement_id": WEBWAY_PATHSTONE_ENHANCEMENT_ID,
                    "target_unit_instance_id": unit.unit_instance_id,
                },
                options=(
                    _webway_pathstone_option(
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        use_ability=True,
                    ),
                    _webway_pathstone_option(
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        use_ability=False,
                    ),
                ),
            )
    return None


def apply_webway_pathstone_turn_end_result(context: TurnEndResultContext) -> bool:
    if type(context) is not TurnEndResultContext:
        raise GameLifecycleError("Webway Pathstone requires a turn-end result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != WEBWAY_PATHSTONE_TURN_END_HOOK_ID:
        return False
    payload = _payload_object(context.result.payload)
    player_id = _payload_string(payload, "player_id")
    unit_instance_id = _payload_string(payload, "target_unit_instance_id")
    use_ability = _payload_bool(payload, "use_ability")
    if not use_ability:
        context.decisions.event_log.append(
            WEBWAY_PATHSTONE_DECLINED_EVENT,
            _webway_pathstone_event_payload(
                context=context,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                reserve_state_payload=None,
            ),
        )
        return True
    if not _webway_pathstone_unit_can_enter_reserves(
        context.state,
        unit_instance_id=unit_instance_id,
    ):
        raise GameLifecycleError("Webway Pathstone unit is no longer eligible.")
    reserve_state = context.state.reposition_unit_to_strategic_reserves(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        source_rule_ids=(WEBWAY_PATHSTONE_SOURCE_RULE_ID,),
    )
    context.decisions.event_log.append(
        WEBWAY_PATHSTONE_USED_EVENT,
        _webway_pathstone_event_payload(
            context=context,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_state_payload=cast(JsonValue, reserve_state.to_payload()),
        ),
    )
    return True


def _validate_corsair_coterie_army(army: ArmyDefinition, *, label: str) -> None:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError(f"{label} requires ArmyDefinition.")
    if not (
        army.detachment_selection.faction_id == AELDARI_FACTION_ID
        and CORSAIR_COTERIE_DETACHMENT_ID in army.detachment_selection.detachment_ids
    ):
        raise GameLifecycleError(f"{label} requires Corsair Coterie.")


def _corsair_coterie_armies(state: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Corsair Coterie requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == AELDARI_FACTION_ID
        and CORSAIR_COTERIE_DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _assigned_units(
    army: ArmyDefinition,
    *,
    enhancement_id: str,
) -> tuple[tuple[EnhancementAssignment, UnitInstance], ...]:
    matches: list[tuple[EnhancementAssignment, UnitInstance]] = []
    for assignment in army.enhancement_assignments:
        if assignment.enhancement_id != enhancement_id:
            continue
        unit_instance_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
        matches.append((assignment, _unit_in_army_by_id(army, unit_instance_id=unit_instance_id)))
    return tuple(sorted(matches, key=lambda item: item[1].unit_instance_id))


def _archraider_model_options(
    *,
    player_id: str,
    assignment: EnhancementAssignment,
    unit: UnitInstance,
) -> tuple[DecisionOption, ...]:
    if not unit.own_models:
        raise GameLifecycleError("Archraider unit has no selectable models.")
    return tuple(
        DecisionOption(
            option_id=(
                f"aeldari:corsair-coterie:archraider:{unit.unit_instance_id}:"
                f"{model.model_instance_id}"
            ),
            label=model.name,
            payload={
                "submission_kind": "aeldari_corsair_coterie_archraider_model_selection",
                "player_id": player_id,
                "source_rule_id": ARCHRAIDER_SOURCE_RULE_ID,
                "hook_id": ARCHRAIDER_SETUP_HOOK_ID,
                "enhancement_id": ARCHRAIDER_ENHANCEMENT_ID,
                "assignment_source_id": assignment.source_id,
                "target_unit_instance_id": unit.unit_instance_id,
                "selected_model_instance_id": model.model_instance_id,
            },
        )
        for model in unit.own_models
    )


def _webway_pathstone_option(
    *,
    player_id: str,
    unit_instance_id: str,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "decline"
    return DecisionOption(
        option_id=f"aeldari:corsair-coterie:webway-pathstone:{unit_instance_id}:{action}",
        label="Use Webway Pathstone" if use_ability else "Decline Webway Pathstone",
        payload={
            "submission_kind": "aeldari_corsair_coterie_webway_pathstone_turn_end",
            "player_id": player_id,
            "source_rule_id": WEBWAY_PATHSTONE_SOURCE_RULE_ID,
            "hook_id": WEBWAY_PATHSTONE_TURN_END_HOOK_ID,
            "enhancement_id": WEBWAY_PATHSTONE_ENHANCEMENT_ID,
            "target_unit_instance_id": unit_instance_id,
            "use_ability": use_ability,
        },
    )


def _archraider_cost_choice_option(
    *,
    player_id: str,
    target_unit_instance_id: str,
    source_decision_request_id: str,
    source_decision_result_id: str,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "decline"
    return DecisionOption(
        option_id=(
            "aeldari:corsair-coterie:archraider:"
            f"{source_decision_result_id}:{target_unit_instance_id}:{action}"
        ),
        label="Use Lord of Deceit" if use_ability else "Decline Lord of Deceit",
        payload={
            "submission_kind": "aeldari_corsair_coterie_lord_of_deceit_cost_choice",
            "player_id": player_id,
            "source_rule_id": ARCHRAIDER_SOURCE_RULE_ID,
            "hook_id": ARCHRAIDER_COST_CHOICE_HOOK_ID,
            "modifier_id": ARCHRAIDER_COST_MODIFIER_ID,
            "enhancement_id": ARCHRAIDER_ENHANCEMENT_ID,
            "target_unit_instance_id": target_unit_instance_id,
            "source_decision_request_id": source_decision_request_id,
            "source_decision_result_id": source_decision_result_id,
            "use_ability": use_ability,
        },
    )


def _webway_pathstone_unit_can_enter_reserves(
    state: object,
    *,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Webway Pathstone requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Webway Pathstone requires battlefield_state.")
    if state.reserve_state_for_unit(unit_instance_id) is not None:
        return False
    if not state.battlefield_state.is_unit_placed(unit_instance_id):
        return False
    return not unit_within_enemy_engagement_range(state=state, unit_instance_id=unit_instance_id)


def _unit_is_afflicted_by_infamy(
    *,
    state: object,
    target_unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Infamy requires GameState.")
    target_owner = _owner_for_unit(
        tuple(state.army_definitions),
        unit_instance_id=target_unit_instance_id,
    )
    for army in _corsair_coterie_armies(state):
        if army.player_id == target_owner:
            continue
        for _assignment, source_unit in _assigned_units(army, enhancement_id=INFAMY_ENHANCEMENT_ID):
            if _units_within_range(
                state=state,
                first_unit_instance_id=source_unit.unit_instance_id,
                second_unit_instance_id=target_unit_instance_id,
                range_inches=INFAMY_AURA_RANGE_INCHES,
            ):
                return True
    return False


def _unit_has_persisting_effect(
    state: object,
    *,
    unit_instance_id: str,
    effect_kind: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Corsair Coterie persisting effect lookup requires GameState.")
    requested_effect_kind = _validate_identifier("effect_kind", effect_kind)
    for effect in state.persisting_effects:
        if unit_instance_id not in effect.target_unit_instance_ids:
            continue
        payload = effect.effect_payload
        if isinstance(payload, dict) and payload.get("effect_kind") == requested_effect_kind:
            return True
    return False


def _selected_archraider_model_ids(
    state: object,
    *,
    player_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Archraider state lookup requires GameState.")
    model_ids: list[str] = []
    for record in state.faction_rule_states_for_player(
        player_id=player_id,
        state_kind=ARCHRAIDER_STATE_KIND,
    ):
        payload = _payload_object(record.payload)
        model_ids.append(_payload_string(payload, "selected_model_instance_id"))
    return tuple(sorted(model_ids))


def _eligible_archraider_model_ids_for_target(
    *,
    state: object,
    player_id: str,
    target_unit_instance_id: str,
) -> tuple[str, ...]:
    return tuple(
        model_id
        for model_id in _selected_archraider_model_ids(state, player_id=player_id)
        if _model_within_unit_range(
            state=state,
            model_instance_id=model_id,
            target_unit_instance_id=target_unit_instance_id,
            range_inches=ARCHRAIDER_AURA_RANGE_INCHES,
        )
    )


def _archraider_state_for_unit(
    state: object,
    *,
    player_id: str,
    unit_instance_id: str,
) -> FactionRuleState | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Archraider state lookup requires GameState.")
    for record in state.faction_rule_states_for_player(
        player_id=player_id,
        state_kind=ARCHRAIDER_STATE_KIND,
    ):
        payload = _payload_object(record.payload)
        if payload.get("target_unit_instance_id") == unit_instance_id:
            return record
    return None


def _archraider_used_this_turn(
    state: object,
    *,
    decisions: object | None,
    player_id: str,
    active_player_id: str | None,
    source_decision_result_id: str | None,
) -> bool:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Archraider usage lookup requires GameState.")
    if decisions is None:
        return any(
            record.battle_round == state.battle_round
            and record.active_player_id == active_player_id
            and ARCHRAIDER_COST_MODIFIER_ID in record.command_point_modifier_ids
            for record in state.stratagem_use_records
        )
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Archraider usage lookup requires DecisionController.")
    for record in decisions.event_log.records:
        if record.event_type != ARCHRAIDER_COST_MODIFIER_USED_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("player_id") != player_id:
            continue
        if (
            source_decision_result_id is not None
            and payload.get("source_decision_result_id") == source_decision_result_id
        ):
            continue
        if payload.get("use_ability") is True:
            return True
    return False


def _archraider_cost_choice_used_for_source_result(
    context: StratagemCostModifierContext,
) -> bool:
    from warhammer40k_core.engine.decision_controller import DecisionController

    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Archraider cost choice lookup requires context.")
    if context.decisions is None:
        return False
    if type(context.decisions) is not DecisionController:
        raise GameLifecycleError("Archraider cost choice lookup requires DecisionController.")
    if context.source_decision_result_id is None:
        return False
    for record in context.decisions.event_log.records:
        if record.event_type != ARCHRAIDER_COST_MODIFIER_USED_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("source_decision_result_id") != context.source_decision_result_id:
            continue
        if payload.get("modifier_id") != ARCHRAIDER_COST_MODIFIER_ID:
            continue
        return payload.get("use_ability") is True
    return False


def _webway_pathstone_decision_recorded_this_turn(
    context: TurnEndRequestContext,
    *,
    unit_instance_id: str,
) -> bool:
    active_player_id = _active_player_id(context.state)
    for record in context.decisions.event_log.records:
        if record.event_type not in {
            WEBWAY_PATHSTONE_USED_EVENT,
            WEBWAY_PATHSTONE_DECLINED_EVENT,
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        if payload.get("target_unit_instance_id") == unit_instance_id:
            return True
    return False


def _webway_pathstone_used_this_battle(
    decisions: object,
    *,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.decision_controller import DecisionController

    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Webway Pathstone usage lookup requires DecisionController.")
    for record in decisions.event_log.records:
        if record.event_type != WEBWAY_PATHSTONE_USED_EVENT:
            continue
        payload = record.payload
        if isinstance(payload, dict) and payload.get("target_unit_instance_id") == unit_instance_id:
            return True
    return False


def _webway_pathstone_event_payload(
    *,
    context: TurnEndResultContext,
    player_id: str,
    unit_instance_id: str,
    reserve_state_payload: JsonValue,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": _active_player_id(context.state),
        "phase": context.state.current_battle_phase.value
        if context.state.current_battle_phase is not None
        else None,
        "player_id": player_id,
        "source_rule_id": WEBWAY_PATHSTONE_SOURCE_RULE_ID,
        "hook_id": WEBWAY_PATHSTONE_TURN_END_HOOK_ID,
        "enhancement_id": WEBWAY_PATHSTONE_ENHANCEMENT_ID,
        "target_unit_instance_id": unit_instance_id,
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "reserve_state": reserve_state_payload,
    }


def _archraider_cost_choice_event_payload(
    *,
    context: StratagemCostChoiceResultContext,
    player_id: str,
    target_unit_instance_id: str,
    use_ability: bool,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": context.eligibility_context.active_player_id,
        "phase": context.eligibility_context.phase.value,
        "player_id": player_id,
        "source_rule_id": ARCHRAIDER_SOURCE_RULE_ID,
        "hook_id": ARCHRAIDER_COST_CHOICE_HOOK_ID,
        "modifier_id": ARCHRAIDER_COST_MODIFIER_ID,
        "enhancement_id": ARCHRAIDER_ENHANCEMENT_ID,
        "stratagem_id": context.definition.stratagem_id,
        "stratagem_player_id": context.eligibility_context.player_id,
        "target_unit_instance_id": target_unit_instance_id,
        "source_decision_request_id": context.source_request.request_id,
        "source_decision_result_id": context.source_result.result_id,
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "use_ability": use_ability,
    }


def _units_within_range(
    *,
    state: object,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
    range_inches: float,
) -> bool:
    first_models = _unit_geometry_models(state=state, unit_instance_id=first_unit_instance_id)
    second_models = _unit_geometry_models(state=state, unit_instance_id=second_unit_instance_id)
    return _any_models_within_range(first_models, second_models, range_inches=range_inches)


def _model_within_unit_range(
    *,
    state: object,
    model_instance_id: str,
    target_unit_instance_id: str,
    range_inches: float,
) -> bool:
    source_model = _geometry_model_for_model(state=state, model_instance_id=model_instance_id)
    if source_model is None:
        return False
    target_models = _unit_geometry_models(state=state, unit_instance_id=target_unit_instance_id)
    return any(
        shapely_backend.base_footprint_distance(
            source_model.base,
            source_model.pose,
            target_model.base,
            target_model.pose,
        )
        <= range_inches
        for target_model in target_models
    )


def _any_models_within_range(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    *,
    range_inches: float,
) -> bool:
    for first_model in first_models:
        for second_model in second_models:
            if (
                shapely_backend.base_footprint_distance(
                    first_model.base,
                    first_model.pose,
                    second_model.base,
                    second_model.pose,
                )
                <= range_inches
            ):
                return True
    return False


def _unit_geometry_models(
    *,
    state: object,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Unit geometry lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Unit geometry lookup requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = state.battlefield_state.unit_placement_or_none(unit_instance_id)
    if unit_placement is None:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _geometry_model_for_model(
    *,
    state: object,
    model_instance_id: str,
) -> GeometryModel | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Model geometry lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Model geometry lookup requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    placement = state.battlefield_state.model_placement_or_none(model_instance_id)
    if placement is None:
        return None
    model = scenario.model_instance_for_placement(placement)
    if not model.is_alive:
        return None
    return geometry_model_for_placement(model=model, placement=placement)


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    return _shared_army_for_player(
        armies,
        player_id=player_id,
        context="Corsair Coterie",
    )


def _unit_in_army_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Corsair Coterie unit is unknown.")


def _owner_for_unit(armies: tuple[ArmyDefinition, ...], *, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Corsair Coterie unit owner is unknown.")


def _active_player_id(state: object) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Active player lookup requires GameState.")
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Corsair Coterie requires an active player.")
    return active_player_id


def _payload_object(value: object) -> dict[str, JsonValue]:
    return payload_object(value)


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    if key not in payload or type(payload[key]) is not str:
        raise GameLifecycleError(f"Corsair Coterie payload missing string {key}.")
    return payload_identifier(payload, key)


def _payload_bool(payload: dict[str, JsonValue], key: str) -> bool:
    if key not in payload or type(payload[key]) is not bool:
        raise GameLifecycleError(f"Corsair Coterie payload missing bool {key}.")
    return payload_bool(payload, key)


_validate_identifier = IdentifierValidator(GameLifecycleError)
