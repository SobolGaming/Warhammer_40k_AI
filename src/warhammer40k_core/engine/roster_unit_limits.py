"""Core battle-size duplication limits over canonical catalog keywords."""

from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.engine.list_validation import BattleSizeMusteringPolicy


def datasheet_unit_limit(
    datasheet: DatasheetDefinition, *, policy: BattleSizeMusteringPolicy
) -> int:
    """Either keyword doubles the ordinary allowance; having both does not stack."""
    if "BATTLELINE" in datasheet.keywords.keywords or (
        "DEDICATED TRANSPORT" in datasheet.keywords.keywords
    ):
        return policy.battleline_unit_limit
    return policy.unit_limit
