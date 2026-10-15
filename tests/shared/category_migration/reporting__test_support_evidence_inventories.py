from __future__ import annotations

from tools.generate_ability_support_matrix import (
    DATASHEET_SUPPORT_OVERALL_VALUES,
    MUSTERING_SUPPORT_STAGE_VALUES,
    ability_support_matrix_rows,
    datasheet_support_rows,
    datasheet_support_rows_payload,
    mustering_support_rows,
    mustering_support_rows_payload,
    runtime_content_semantic_coverage_payload,
)

from warhammer40k_core.engine import army_mustering
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_detachments_2026_27

__all__: list[str] = []
__all__ += ["DATASHEET_SUPPORT_OVERALL_VALUES", "AbilityCoverageSupportStage"]
__all__ += ["MUSTERING_SUPPORT_STAGE_VALUES", "ability_coverage_category_rows"]
__all__ += ["ability_coverage_category_rows_payload", "ability_coverage_rows_payload"]
__all__ += ["ability_support_matrix_rows", "army_mustering", "datasheet_support_rows"]
__all__ += ["datasheet_support_rows_payload", "faction_detachments_2026_27"]
__all__ += ["mustering_support_rows", "mustering_support_rows_payload"]
__all__ += ["runtime_content_semantic_coverage_payload"]
