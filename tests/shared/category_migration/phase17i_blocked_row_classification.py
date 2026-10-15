from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from warhammer40k_core.rules.rule_templates import RuleTemplateFamily, rule_template_by_id
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blocked_row_classification_2026_27 as classification_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27 as execution_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)


def _payload_checksum(
    payload: classification_source.Phase17IBlockedRowClassificationReportPayload,
) -> str:
    payload_without_checksum: dict[str, object] = dict(payload)
    payload_without_checksum["source_payload_checksum_sha256"] = ""
    encoded = json.dumps(payload_without_checksum, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


__all__: list[str] = []
__all__ += ["Phase17FExecutionStatus", "RuleTemplateFamily", "_payload_checksum"]
__all__ += ["classification_source", "execution_source", "hashlib", "json", "pytest", "replace"]
__all__ += ["rule_template_by_id"]
