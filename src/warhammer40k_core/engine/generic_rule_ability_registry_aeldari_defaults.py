from __future__ import annotations

from typing import Protocol, cast

from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.enhancement_effects import EnhancementEffectContext
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleBattleFormationAbility,
    GenericRuleEnhancementEffectAbility,
    GenericRuleObjectiveControlModifierAbility,
    GenericRuleSaveOptionModifierAbility,
    GenericRuleStratagemCostChoiceAbility,
    GenericRuleStratagemCostModifierAbility,
    GenericRuleTurnEndAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    SaveOptionModifierContext,
)
from warhammer40k_core.engine.saves import SaveOption
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierContext
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext, TurnEndResultContext
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_corsair_coterie_ir_support_2026_27 as corsair_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_path_of_the_outcast_ir_support_2026_27 as path_outcast_ir,
)


class _PathOfTheOutcastEnhancementsModule(Protocol):
    CAMOUFLAGED_SNIPERS_EFFECT_ID: str
    ASSASSINS_EYE_EFFECT_ID: str

    def camouflaged_snipers_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def assassins_eye_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...


class _CorsairCoterieEnhancementsModule(Protocol):
    ARCHRAIDER_EFFECT_ID: str
    ARCHRAIDER_SETUP_HOOK_ID: str
    ARCHRAIDER_COST_CHOICE_HOOK_ID: str
    ARCHRAIDER_COST_MODIFIER_ID: str
    INFAMY_EFFECT_ID: str
    VOIDSTONE_EFFECT_ID: str
    VOIDSTONE_SAVE_MODIFIER_ID: str
    WEBWAY_PATHSTONE_EFFECT_ID: str
    WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID: str
    INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID: str
    WEBWAY_PATHSTONE_TURN_END_HOOK_ID: str

    def archraider_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def archraider_model_selection_request(
        self,
        context: BattleFormationRequestContext,
    ) -> DecisionRequest | None: ...

    def apply_archraider_model_selection_result(
        self,
        context: BattleFormationResultContext,
    ) -> bool: ...

    def archraider_command_point_cost_choice_request(
        self,
        context: StratagemCostChoiceRequestContext,
    ) -> DecisionRequest | None: ...

    def apply_archraider_command_point_cost_choice_result(
        self,
        context: StratagemCostChoiceResultContext,
    ) -> bool: ...

    def archraider_command_point_cost_modifier(
        self,
        context: StratagemCostModifierContext,
    ) -> int: ...

    def infamy_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def voidstone_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def webway_pathstone_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def webway_pathstone_deep_strike_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def infamy_objective_control_modifier(
        self,
        context: ObjectiveControlModifierContext,
    ) -> int: ...

    def voidstone_save_option_modifier(
        self,
        context: SaveOptionModifierContext,
    ) -> tuple[SaveOption, ...]: ...

    def webway_pathstone_turn_end_request(
        self,
        context: TurnEndRequestContext,
    ) -> DecisionRequest | None: ...

    def apply_webway_pathstone_turn_end_result(
        self,
        context: TurnEndResultContext,
    ) -> bool: ...


def aeldari_path_of_the_outcast_enhancement_effect_abilities() -> tuple[
    GenericRuleEnhancementEffectAbility, ...
]:
    return (
        GenericRuleEnhancementEffectAbility(
            ability_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_KEEP_HIDDEN_ABILITY,
            coverage_descriptor_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_SOURCE_RULE_ID,
            enhancement_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            effect_id_builder=_camouflaged_snipers_effect_id,
            context_predicate=_enhancement_context_predicate,
            effect_builder=_camouflaged_snipers_effect,
        ),
        GenericRuleEnhancementEffectAbility(
            ability_id=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
            coverage_descriptor_id=path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=path_outcast_ir.ASSASSINS_EYE_SOURCE_RULE_ID,
            enhancement_id=path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_ID,
            effect_id_builder=_assassins_eye_effect_id,
            context_predicate=_enhancement_context_predicate,
            effect_builder=_assassins_eye_effect,
        ),
    )


def aeldari_corsair_coterie_enhancement_effect_abilities() -> tuple[
    GenericRuleEnhancementEffectAbility, ...
]:
    return (
        GenericRuleEnhancementEffectAbility(
            ability_id=corsair_ir.ARCHRAIDER_MARKER_ABILITY,
            coverage_descriptor_id=corsair_ir.ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.ARCHRAIDER_SOURCE_RULE_ID,
            enhancement_id=corsair_ir.ARCHRAIDER_ENHANCEMENT_ID,
            effect_id_builder=_corsair_archraider_effect_id,
            context_predicate=_corsair_enhancement_context_predicate,
            effect_builder=_corsair_archraider_effect,
        ),
        GenericRuleEnhancementEffectAbility(
            ability_id=corsair_ir.INFAMY_MARKER_ABILITY,
            coverage_descriptor_id=corsair_ir.INFAMY_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.INFAMY_SOURCE_RULE_ID,
            enhancement_id=corsair_ir.INFAMY_ENHANCEMENT_ID,
            effect_id_builder=_corsair_infamy_effect_id,
            context_predicate=_corsair_enhancement_context_predicate,
            effect_builder=_corsair_infamy_effect,
        ),
        GenericRuleEnhancementEffectAbility(
            ability_id=corsair_ir.VOIDSTONE_MARKER_ABILITY,
            coverage_descriptor_id=corsair_ir.VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.VOIDSTONE_SOURCE_RULE_ID,
            enhancement_id=corsair_ir.VOIDSTONE_ENHANCEMENT_ID,
            effect_id_builder=_corsair_voidstone_effect_id,
            context_predicate=_corsair_enhancement_context_predicate,
            effect_builder=_corsair_voidstone_effect,
        ),
        GenericRuleEnhancementEffectAbility(
            ability_id=corsair_ir.WEBWAY_PATHSTONE_MARKER_ABILITY,
            coverage_descriptor_id=corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID,
            enhancement_id=corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_ID,
            effect_id_builder=_corsair_webway_pathstone_effect_id,
            context_predicate=_corsair_enhancement_context_predicate,
            effect_builder=_corsair_webway_pathstone_effect,
        ),
        GenericRuleEnhancementEffectAbility(
            ability_id=corsair_ir.WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY,
            coverage_descriptor_id=corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID,
            enhancement_id=corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_ID,
            effect_id_builder=_corsair_webway_pathstone_deep_strike_effect_id,
            context_predicate=_corsair_enhancement_context_predicate,
            effect_builder=_corsair_webway_pathstone_deep_strike_effect,
        ),
    )


def aeldari_corsair_coterie_battle_formation_abilities() -> tuple[
    GenericRuleBattleFormationAbility, ...
]:
    return (
        GenericRuleBattleFormationAbility(
            ability_id=corsair_ir.ARCHRAIDER_MODEL_SELECTION_ABILITY,
            coverage_descriptor_id=corsair_ir.ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.ARCHRAIDER_SOURCE_RULE_ID,
            hook_id_builder=_corsair_archraider_setup_hook_id,
            request_builder=_corsair_archraider_model_selection_request,
            result_builder=_corsair_apply_archraider_model_selection_result,
        ),
    )


def aeldari_corsair_coterie_objective_control_modifier_abilities() -> tuple[
    GenericRuleObjectiveControlModifierAbility, ...
]:
    return (
        GenericRuleObjectiveControlModifierAbility(
            ability_id=corsair_ir.INFAMY_OBJECTIVE_CONTROL_ABILITY,
            coverage_descriptor_id=corsair_ir.INFAMY_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.INFAMY_SOURCE_RULE_ID,
            modifier_id_builder=_corsair_infamy_objective_control_modifier_id,
            context_predicate=_corsair_objective_control_context_predicate,
            modifier_builder=_corsair_infamy_objective_control_modifier,
        ),
    )


def aeldari_corsair_coterie_stratagem_cost_choice_abilities() -> tuple[
    GenericRuleStratagemCostChoiceAbility, ...
]:
    return (
        GenericRuleStratagemCostChoiceAbility(
            ability_id=corsair_ir.ARCHRAIDER_STRATAGEM_COST_CHOICE_ABILITY,
            coverage_descriptor_id=corsair_ir.ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.ARCHRAIDER_SOURCE_RULE_ID,
            hook_id_builder=_corsair_archraider_cost_choice_hook_id,
            request_builder=_corsair_archraider_cost_choice_request,
            result_builder=_corsair_apply_archraider_cost_choice_result,
        ),
    )


def aeldari_corsair_coterie_stratagem_cost_modifier_abilities() -> tuple[
    GenericRuleStratagemCostModifierAbility, ...
]:
    return (
        GenericRuleStratagemCostModifierAbility(
            ability_id=corsair_ir.ARCHRAIDER_STRATAGEM_COST_MODIFIER_ABILITY,
            coverage_descriptor_id=corsair_ir.ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.ARCHRAIDER_SOURCE_RULE_ID,
            modifier_id_builder=_corsair_archraider_cost_modifier_id,
            context_predicate=_corsair_stratagem_cost_modifier_context_predicate,
            modifier_builder=_corsair_archraider_cost_modifier,
        ),
    )


def aeldari_corsair_coterie_save_option_modifier_abilities() -> tuple[
    GenericRuleSaveOptionModifierAbility, ...
]:
    return (
        GenericRuleSaveOptionModifierAbility(
            ability_id=corsair_ir.VOIDSTONE_SAVE_OPTION_ABILITY,
            coverage_descriptor_id=corsair_ir.VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.VOIDSTONE_SOURCE_RULE_ID,
            modifier_id_builder=_corsair_voidstone_save_option_modifier_id,
            context_predicate=_corsair_save_option_context_predicate,
            modifier_builder=_corsair_voidstone_save_option_modifier,
        ),
    )


def aeldari_corsair_coterie_turn_end_abilities() -> tuple[GenericRuleTurnEndAbility, ...]:
    return (
        GenericRuleTurnEndAbility(
            ability_id=corsair_ir.WEBWAY_PATHSTONE_RESERVES_ABILITY,
            coverage_descriptor_id=corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID,
            hook_id_builder=_corsair_webway_pathstone_turn_end_hook_id,
            request_builder=_corsair_webway_pathstone_turn_end_request,
            result_builder=_corsair_apply_webway_pathstone_turn_end_result,
        ),
    )


def _path_of_the_outcast_enhancements() -> _PathOfTheOutcastEnhancementsModule:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.path_of_the_outcast import (  # noqa: E501
        enhancements,
    )

    return cast(_PathOfTheOutcastEnhancementsModule, enhancements)


def _corsair_coterie_enhancements() -> _CorsairCoterieEnhancementsModule:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.corsair_coterie import (  # noqa: E501
        enhancements,
    )

    return cast(_CorsairCoterieEnhancementsModule, enhancements)


def _enhancement_context_predicate(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Path of the Outcast enhancement effect requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Path of the Outcast enhancement effect requires source.")
    return True


def _corsair_enhancement_context_predicate(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Corsair Coterie enhancement effect requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Corsair Coterie enhancement effect requires source.")
    return True


def _corsair_objective_control_context_predicate(
    context: ObjectiveControlModifierContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Corsair Coterie Objective Control requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Corsair Coterie Objective Control requires source.")
    return True


def _corsair_stratagem_cost_modifier_context_predicate(
    context: StratagemCostModifierContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Corsair Coterie stratagem cost modifier requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Corsair Coterie stratagem cost modifier requires source.")
    return True


def _corsair_save_option_context_predicate(
    context: SaveOptionModifierContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Corsair Coterie save option modifier requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Corsair Coterie save option modifier requires source.")
    return True


def _camouflaged_snipers_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Camouflaged Snipers effect ID requires source.")
    return _path_of_the_outcast_enhancements().CAMOUFLAGED_SNIPERS_EFFECT_ID


def _camouflaged_snipers_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Camouflaged Snipers effect requires source.")
    return _path_of_the_outcast_enhancements().camouflaged_snipers_effect(context)


def _assassins_eye_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Assassins Eye effect ID requires source.")
    return _path_of_the_outcast_enhancements().ASSASSINS_EYE_EFFECT_ID


def _assassins_eye_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Assassins Eye effect requires source.")
    return _path_of_the_outcast_enhancements().assassins_eye_effect(context)


def _corsair_archraider_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider effect ID requires source.")
    return _corsair_coterie_enhancements().ARCHRAIDER_EFFECT_ID


def _corsair_archraider_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider effect requires source.")
    return _corsair_coterie_enhancements().archraider_effect(context)


def _corsair_archraider_setup_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider setup hook ID requires source.")
    return _corsair_coterie_enhancements().ARCHRAIDER_SETUP_HOOK_ID


def _corsair_archraider_model_selection_request(
    context: BattleFormationRequestContext,
    source: GenericRuleAbilitySource,
) -> DecisionRequest | None:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider model selection request requires source.")
    return _corsair_coterie_enhancements().archraider_model_selection_request(context)


def _corsair_apply_archraider_model_selection_result(
    context: BattleFormationResultContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider model selection result requires source.")
    return _corsair_coterie_enhancements().apply_archraider_model_selection_result(context)


def _corsair_archraider_cost_choice_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider cost choice hook ID requires source.")
    return _corsair_coterie_enhancements().ARCHRAIDER_COST_CHOICE_HOOK_ID


def _corsair_archraider_cost_choice_request(
    context: StratagemCostChoiceRequestContext,
    source: GenericRuleAbilitySource,
) -> DecisionRequest | None:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider cost choice request requires source.")
    return _corsair_coterie_enhancements().archraider_command_point_cost_choice_request(context)


def _corsair_apply_archraider_cost_choice_result(
    context: StratagemCostChoiceResultContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider cost choice result requires source.")
    return _corsair_coterie_enhancements().apply_archraider_command_point_cost_choice_result(
        context
    )


def _corsair_archraider_cost_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider cost modifier ID requires source.")
    return _corsair_coterie_enhancements().ARCHRAIDER_COST_MODIFIER_ID


def _corsair_archraider_cost_modifier(
    context: StratagemCostModifierContext,
    source: GenericRuleAbilitySource,
) -> int:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Archraider cost modifier requires source.")
    return _corsair_coterie_enhancements().archraider_command_point_cost_modifier(context)


def _corsair_infamy_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Infamy effect ID requires source.")
    return _corsair_coterie_enhancements().INFAMY_EFFECT_ID


def _corsair_infamy_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Infamy effect requires source.")
    return _corsair_coterie_enhancements().infamy_effect(context)


def _corsair_voidstone_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Voidstone effect ID requires source.")
    return _corsair_coterie_enhancements().VOIDSTONE_EFFECT_ID


def _corsair_voidstone_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Voidstone effect requires source.")
    return _corsair_coterie_enhancements().voidstone_effect(context)


def _corsair_voidstone_save_option_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Voidstone save option modifier ID requires source.")
    return _corsair_coterie_enhancements().VOIDSTONE_SAVE_MODIFIER_ID


def _corsair_voidstone_save_option_modifier(
    context: SaveOptionModifierContext,
    source: GenericRuleAbilitySource,
) -> tuple[SaveOption, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Voidstone save option modifier requires source.")
    return _corsair_coterie_enhancements().voidstone_save_option_modifier(context)


def _corsair_webway_pathstone_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone effect ID requires source.")
    return _corsair_coterie_enhancements().WEBWAY_PATHSTONE_EFFECT_ID


def _corsair_webway_pathstone_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone effect requires source.")
    return _corsair_coterie_enhancements().webway_pathstone_effect(context)


def _corsair_webway_pathstone_deep_strike_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone Deep Strike effect ID requires source.")
    return _corsair_coterie_enhancements().WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID


def _corsair_webway_pathstone_deep_strike_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone Deep Strike effect requires source.")
    return _corsair_coterie_enhancements().webway_pathstone_deep_strike_effect(context)


def _corsair_infamy_objective_control_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Infamy Objective Control modifier ID requires source.")
    return _corsair_coterie_enhancements().INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID


def _corsair_infamy_objective_control_modifier(
    context: ObjectiveControlModifierContext,
    source: GenericRuleAbilitySource,
) -> int:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Infamy Objective Control modifier requires source.")
    return _corsair_coterie_enhancements().infamy_objective_control_modifier(context)


def _corsair_webway_pathstone_turn_end_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone turn-end hook ID requires source.")
    return _corsair_coterie_enhancements().WEBWAY_PATHSTONE_TURN_END_HOOK_ID


def _corsair_webway_pathstone_turn_end_request(
    context: TurnEndRequestContext,
    source: GenericRuleAbilitySource,
) -> DecisionRequest | None:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone turn-end request requires source.")
    return _corsair_coterie_enhancements().webway_pathstone_turn_end_request(context)


def _corsair_apply_webway_pathstone_turn_end_result(
    context: TurnEndResultContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Webway Pathstone turn-end result requires source.")
    return _corsair_coterie_enhancements().apply_webway_pathstone_turn_end_result(context)
