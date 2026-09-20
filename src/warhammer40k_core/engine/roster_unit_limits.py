"""Core battle-size duplication limits over canonical catalog keywords."""

from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.engine.list_validation import BattleSize, BattleSizeMusteringPolicy


def datasheet_unit_limit(
    datasheet: DatasheetDefinition, *, policy: BattleSizeMusteringPolicy
) -> int:
    """Apply the Dedicated Transport exception only at source-backed battle sizes."""
    if "BATTLELINE" in datasheet.keywords.keywords or (
        policy.battle_size in (BattleSize.INCURSION, BattleSize.STRIKE_FORCE)
        and "DEDICATED TRANSPORT" in datasheet.keywords.keywords
    ):
        return policy.battleline_unit_limit
    return policy.unit_limit
