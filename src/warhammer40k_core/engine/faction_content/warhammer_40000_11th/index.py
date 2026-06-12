from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.faction_content.loader import RuntimeContentModuleIndex
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentManifest
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.generated_manifest import (
    generated_runtime_content_rows,
)


def runtime_content_manifest(*, catalog: ArmyCatalog) -> RuntimeContentManifest:
    return RuntimeContentManifest.from_catalog(
        catalog=catalog,
        generated_rows=generated_runtime_content_rows(),
    )


def runtime_content_module_index() -> RuntimeContentModuleIndex:
    generated_index = RuntimeContentManifest(
        rows=generated_runtime_content_rows()
    ).to_module_index()
    return RuntimeContentModuleIndex(
        faction_modules=generated_index.faction_modules,
        detachment_modules=generated_index.detachment_modules,
        enhancement_modules=generated_index.enhancement_modules,
        stratagem_modules=generated_index.stratagem_modules,
        datasheet_modules=generated_index.datasheet_modules,
        wargear_modules=generated_index.wargear_modules,
        weapon_profile_modules=generated_index.weapon_profile_modules,
    )
