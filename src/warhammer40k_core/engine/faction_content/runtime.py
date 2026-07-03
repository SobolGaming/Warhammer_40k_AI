from __future__ import annotations

from warhammer40k_core.core.ruleset import RulesetEdition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.loader import (
    RuntimeContentModuleIndex,
    load_runtime_content_contributions,
)
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentManifest
from warhammer40k_core.engine.faction_content.stratagem_activation import (
    source_backed_detachment_stratagem_activation_records,
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
    activation = runtime_content_activation_for_armies(config=config, armies=armies)
    manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor,
        config=config,
    )
    contributions = load_runtime_content_contributions(
        activation=activation,
        manifest=manifest,
    )
    return RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=armies,
        catalog=config.army_catalog,
        contributions=contributions,
        base_ability_records=catalog_ability_records_from_catalog(config.army_catalog),
        base_stratagem_records=source_backed_detachment_stratagem_activation_records(),
    )


def runtime_content_activation_for_armies(
    *,
    config: GameConfig,
    armies: tuple[ArmyDefinition, ...],
) -> RuntimeContentActivation:
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime content activation build requires GameConfig.")
    if type(armies) is not tuple:
        raise GameLifecycleError("Runtime content activation build requires army tuple.")
    roster_activation = RuntimeContentActivation.from_armies(
        armies=armies,
        catalog=config.army_catalog,
    )
    manifest = runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor,
        config=config,
    )
    return manifest.resolve_activation(roster_activation)


def runtime_content_manifest_for_ruleset(
    *,
    ruleset_descriptor: RulesetDescriptor,
    config: GameConfig,
) -> RuntimeContentManifest:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Runtime content manifest lookup requires RulesetDescriptor.")
    if type(config) is not GameConfig:
        raise GameLifecycleError("Runtime content manifest generation requires GameConfig.")
    ruleset_id = ruleset_descriptor.ruleset_id
    if ruleset_id.game == "warhammer_40000" and ruleset_id.edition is RulesetEdition.ELEVENTH:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.index import (
            runtime_content_manifest,
        )

        return runtime_content_manifest(catalog=config.army_catalog)
    raise GameLifecycleError("Runtime content manifest is unavailable for ruleset.")


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
