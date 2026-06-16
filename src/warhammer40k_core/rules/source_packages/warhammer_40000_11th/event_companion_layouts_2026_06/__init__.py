from __future__ import annotations

from .common import (
    FOOTPRINT_6X2,
    FOOTPRINT_6X4,
    FOOTPRINT_7X11_5,
    FOOTPRINT_8X11_5_POLYGON,
    FOOTPRINT_10X2_5,
    EventBattlefieldLayoutSource,
    EventObjectiveRoleCountSpec,
    EventObjectiveSpec,
    EventObjectiveTerrainAreaSpec,
    EventTerrainAreaLocalTransformSpec,
    EventTerrainAreaMirrorPair,
    EventTerrainAreaSpec,
)
from .disruption_vs_reconnaissance import (
    LAYOUTS as DISRUPTION_VS_RECONNAISSANCE_LAYOUTS,
)
from .take_and_hold_vs_take_and_hold import (
    LAYOUTS as TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUTS,
)

__all__ = (
    "EXTRACTED_LAYOUTS",
    "EXTRACTED_LAYOUTS_BY_ID",
    "EXTRACTED_LAYOUT_IDS",
    "FOOTPRINT_6X2",
    "FOOTPRINT_6X4",
    "FOOTPRINT_7X11_5",
    "FOOTPRINT_8X11_5_POLYGON",
    "FOOTPRINT_10X2_5",
    "EventBattlefieldLayoutSource",
    "EventObjectiveRoleCountSpec",
    "EventObjectiveSpec",
    "EventObjectiveTerrainAreaSpec",
    "EventTerrainAreaLocalTransformSpec",
    "EventTerrainAreaMirrorPair",
    "EventTerrainAreaSpec",
)

EXTRACTED_LAYOUTS: tuple[EventBattlefieldLayoutSource, ...] = (
    *TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUTS,
    *DISRUPTION_VS_RECONNAISSANCE_LAYOUTS,
)


def _index_layouts(
    layouts: tuple[EventBattlefieldLayoutSource, ...],
) -> dict[str, EventBattlefieldLayoutSource]:
    indexed: dict[str, EventBattlefieldLayoutSource] = {}
    for layout in layouts:
        if layout.layout_id in indexed:
            raise ValueError(f"Duplicate Event Companion layout ID: {layout.layout_id}")
        indexed[layout.layout_id] = layout
    return indexed


EXTRACTED_LAYOUTS_BY_ID = _index_layouts(EXTRACTED_LAYOUTS)
EXTRACTED_LAYOUT_IDS = frozenset(EXTRACTED_LAYOUTS_BY_ID)
