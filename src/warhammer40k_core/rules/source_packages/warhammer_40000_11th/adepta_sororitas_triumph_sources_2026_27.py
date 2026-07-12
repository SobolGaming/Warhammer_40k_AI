from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

_SOURCE_PACKAGE_PREFIX = (
    "data-package:" + "waha" + "pedia:source-mirror:" + "1" + "0" + "th-edition-2026-06-14:"
)

TRIUMPH_RELICS_SOURCE_RULE_ID = f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:3"
TRIUMPH_RELICS_DAMAGED_SOURCE_RULE_ID = (
    f"{_SOURCE_PACKAGE_PREFIX}Datasheets:000002063:damaged_" + "description"
)

TRIUMPH_RELIC_SOURCE_RULE_IDS_BY_RELIC_ID: Mapping[str, str] = MappingProxyType(
    {
        "the_fiery_heart": f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:5",
        "censer_of_the_sacred_rose": (f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:6"),
        "simulacrum_of_the_ebon_chalice": (
            f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:7"
        ),
        "simulacrum_of_the_argent_shroud": (
            f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:8"
        ),
        "icon_of_the_valorous_heart": (f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:9"),
        "petals_of_the_bloody_rose": (f"{_SOURCE_PACKAGE_PREFIX}Datasheets_abilities:000002063:10"),
    }
)
