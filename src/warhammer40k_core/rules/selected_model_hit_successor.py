"""Exact current lowering successor; retained faction artifacts stay historical."""

from __future__ import annotations

import hashlib
import json
from functools import cache
from typing import cast

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

PREDECESSOR_IR_HASH = "02b5c11d47776e8a050dd004db3f1d725c8ec1828e1624017c439bc0fa1c2219"
ARTIFACT_SHA256 = "4646ec50ebf5bd7224050e43415f5bcb25c90438188582e2a50cbbcbfd64d470"
SOURCE_ROW_ID = "000003909:5"


@cache
def _successor() -> RuleIR:
    raw = package_artifact_bytes(
        "warhammer40k_core.rules.source_packages.warhammer_40000_11th",
        "selected_model_hit_current_2026_11.json",
    )
    if hashlib.sha256(raw).hexdigest() != ARTIFACT_SHA256:
        raise RuleIRError("Selected model hit successor artifact digest drifted.")
    value = json.loads(raw)
    if (
        set(value) != {"schema_version", "source_row_id", "predecessor_ir_hash", "rule_ir"}
        or value["schema_version"] != "selected-model-hit-current-v1"
        or value["source_row_id"] != SOURCE_ROW_ID
        or value["predecessor_ir_hash"] != PREDECESSOR_IR_HASH
    ):
        raise RuleIRError("Selected model hit successor provenance drifted.")
    return RuleIR.from_payload(cast(RuleIRPayload, value["rule_ir"]))


def current_datasheet_rule_ir(
    source_row_id: str, previous: RuleIRPayload | None
) -> RuleIRPayload | None:
    if source_row_id != SOURCE_ROW_ID:
        return previous
    if previous is None:
        raise RuleIRError("Selected model hit predecessor is missing.")
    old = RuleIR.from_payload(previous)
    current = _successor()
    if (
        old.ir_hash() != PREDECESSOR_IR_HASH
        or current.rule_id != old.rule_id
        or current.source_id != old.source_id
        or current.normalized_text != old.normalized_text
        or current.clauses[0] != old.clauses[0]
    ):
        raise RuleIRError("Selected model hit predecessor identity drifted.")
    return current.to_payload()
