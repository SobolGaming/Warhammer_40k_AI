from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint


@dataclass(frozen=True, slots=True)
class SourceBattlefieldTerrainFeatureRow:
    feature_id: str
    feature_kind: str
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    rules_footprint_polygon: tuple[TerrainDisplayPoint, ...]
    source_note: str
    display_geometry: TerrainDisplayGeometry

    def to_payload(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "feature_kind": self.feature_kind,
            "footprint_center_x_inches": self.footprint_center_x_inches,
            "footprint_center_y_inches": self.footprint_center_y_inches,
            "footprint_width_inches": self.footprint_width_inches,
            "footprint_depth_inches": self.footprint_depth_inches,
            "rules_footprint_polygon": [
                point.to_payload() for point in self.rules_footprint_polygon
            ],
            "source_note": self.source_note,
            "display_geometry": self.display_geometry.to_payload(),
        }
