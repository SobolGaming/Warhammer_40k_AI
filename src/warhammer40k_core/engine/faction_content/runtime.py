from __future__ import annotations

from warhammer40k_core.core.ruleset import RulesetEdition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.loader import (
    RuntimeContentModuleIndex,
    load_runtime_content_contributions,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import GameLifecycleError


def build_runtime_content_bundle(config: GameConfig) -> RuntimeContentBundle:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime content bundle build requires GameConfig.")
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    return build_runtime_content_bundle_for_armies(config=config, armies=armies)


def build_runtime_content_bundle_for_armies(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
) -> RuntimeContentBundle:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime content bundle build requires GameConfig.")
    if type(armies) is not tuple:
        raise GameLifecycleError("Runtime content bundle build requires army tuple.")
    activation = RuntimeContentActivation.from_armies(armies=armies, catalog=config.army_catalog)
    module_index = _module_index_with_selected_weapon_profile_owners(
        module_index=runtime_content_module_index_for_ruleset(config.ruleset_descriptor),
        activation=activation,
        config=config,
    )
    contributions = load_runtime_content_contributions(
        activation=activation,
        module_index=module_index,
    )
    return RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=armies,
        catalog=config.army_catalog,
        contributions=contributions,
    )


def _module_index_with_selected_weapon_profile_owners(
    *,
    module_index: RuntimeContentModuleIndex,
    activation: RuntimeContentActivation,
    config: GameConfig,
) -> RuntimeContentModuleIndex:
    if type(module_index) is not RuntimeContentModuleIndex:
        raise GameLifecycleError("Runtime content module index is invalid.")
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Runtime content activation is invalid.")
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime content config is invalid.")
    weapon_profile_modules = dict(module_index.weapon_profile_modules)
    selected_wargear_ids = set(activation.selected_wargear_ids)
    selected_profile_ids = set(activation.selected_weapon_profile_ids)
    for wargear in config.army_catalog.wargear:
        if wargear.wargear_id not in selected_wargear_ids:
            continue
        module_path = module_index.wargear_modules.get(wargear.wargear_id)
        if module_path is None:
            continue
        for profile in wargear.weapon_profiles:
            if profile.profile_id in selected_profile_ids:
                weapon_profile_modules.setdefault(profile.profile_id, module_path)
    return RuntimeContentModuleIndex(
        faction_modules=module_index.faction_modules,
        detachment_modules=module_index.detachment_modules,
        enhancement_modules=module_index.enhancement_modules,
        stratagem_modules=module_index.stratagem_modules,
        datasheet_modules=module_index.datasheet_modules,
        wargear_modules=module_index.wargear_modules,
        weapon_profile_modules=weapon_profile_modules,
    )


def runtime_content_module_index_for_ruleset(
    ruleset_descriptor: RulesetDescriptor,
) -> RuntimeContentModuleIndex:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Runtime content module index lookup requires RulesetDescriptor.")
    ruleset_id = ruleset_descriptor.ruleset_id
    if ruleset_id.game == "warhammer_40000" and ruleset_id.edition is RulesetEdition.ELEVENTH:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.index import (
            runtime_content_module_index,
        )

        return runtime_content_module_index()
    raise GameLifecycleError("Runtime content module index is unavailable for ruleset.")
