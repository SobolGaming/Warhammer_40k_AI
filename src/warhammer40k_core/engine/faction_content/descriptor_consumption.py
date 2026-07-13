from __future__ import annotations

from warhammer40k_core.engine.catalog_descriptor_consumption import (
    CatalogDescriptorConsumptionRecord,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import (
    descriptor_consumption as aeldari_descriptor_consumption,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    descriptor_consumption as chaos_daemons_descriptor_consumption,
)


def faction_descriptor_consumption_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    return (
        *aeldari_descriptor_consumption.descriptor_consumption_records(),
        *chaos_daemons_descriptor_consumption.descriptor_consumption_records(),
    )
