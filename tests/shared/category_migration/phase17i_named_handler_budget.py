from __future__ import annotations

import json
from dataclasses import replace

import pytest

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27 as execution_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_named_handler_budget_2026_27 as budget_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import july_faction_packs_2026_07
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionBlockReason,
    Phase17FExecutionStatus,
)

__all__: list[str] = []
__all__ += ["Phase17FExecutionBlockReason", "Phase17FExecutionStatus", "budget_source"]
__all__ += ["execution_source", "json", "july_faction_packs_2026_07", "pytest", "replace"]
