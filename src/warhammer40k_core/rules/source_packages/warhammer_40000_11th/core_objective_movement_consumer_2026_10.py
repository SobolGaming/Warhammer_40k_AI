"""Eager source-bound overlay for one real objective movement instruction."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

_DATA = json.loads(
    package_artifact_bytes(
        "warhammer40k_core.rules.source_packages.warhammer_40000_11th",
        "core_objective_movement_consumer_2026_10.json",
    )
)
if _DATA["schema_version"] != "core-objective-movement-consumer-v1":
    raise ValueError("Objective movement consumer artifact schema drift.")
_PROFILE = _DATA["consumer_profile"]
if (
    hashlib.sha256(json.dumps(_PROFILE, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    != _DATA["consumer_profile_sha256"]
):
    raise ValueError("Objective movement consumer profile hash drift.")
SOURCE_ID: str = _PROFILE["source_id"]
REQUIRED_NAME_KEYWORD: str = _DATA["required_name_keyword"]
RULE_IR = RuleIR.from_payload(cast(RuleIRPayload, _DATA["rule_ir"]))
if RULE_IR.source_id != SOURCE_ID or not RULE_IR.is_supported:
    raise ValueError("Objective movement consumer RuleIR source or execution drift.")
if (
    _DATA["selected_core"]["row_id"] != "rule:01:01.04.03:1"
    or _DATA["selected_core"]["source_sha256"]
    != "0d9cbb45d59f4f90f0c0c34a2dedc6dbaf360ea7c9e602c21dc5807499706771"
):
    raise ValueError("Objective movement Core definition source drift.")
