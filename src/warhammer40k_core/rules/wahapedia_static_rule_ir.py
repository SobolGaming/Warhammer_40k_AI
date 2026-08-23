from __future__ import annotations

import json

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_pack_rule_ir,
)


def compact_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return faction_pack_rule_ir.datasheet_rule_ir_payload_by_source_row_id(source_row_id)


def payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return datasheet_rule_ir_payload_by_source_row_id(source_row_id)
