"""Current PR587 source-token evidence, separate from both immutable older role scopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "tool-input-roles-v3"
SPEC_PATH = "data/source_audits/qualification40_v1/tool-input-roles-v3.json"
FAMILY = "external_contract_source_reuse"
BASE = "5f509724da25a2f6ded0c2739a8e7c84bdf59c91"


def expected_binding(root: Path, *, input_digest: str) -> dict[str, Any]:
    from tools import performance_qualification_successor as stage

    freeze = stage._freeze(root)
    spec = json.loads(stage._member(root, SPEC_PATH, freeze))
    if spec["schema"] != SCHEMA or spec["base_revision"] != BASE:
        raise ValueError("Current source-token role scope has another exact base/schema.")
    inventories = json.loads(stage._member(root, spec["inventories_path"], freeze))
    if stage._digest(inventories) != spec["inventories_sha256"]:
        raise ValueError("Current source-token complete inventory changed.")
    before, after = inventories["base"], inventories["head"]
    common = {p: v for p, v in before.items() if after.get(p) == v}
    changed = (set(before) | set(after)) - set(common)
    if set(spec["roles"]) != changed or any(
        role not in {"runtime-or-generator-treatment", "side-derived-output", "untimed-governance"}
        for role in spec["roles"].values()
    ):
        raise ValueError("Current source-token per-path roles omit or invent an input.")
    if stage._digest(common) != spec["common_sha256"]:
        raise ValueError("Current source-token identical common harness changed.")
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "base_revision": BASE,
        "head_input_digest": input_digest,
        "role_spec_sha256": stage._digest(spec),
        "complete_inventories_sha256": stage._digest(inventories),
        "common_sha256": stage._digest(common),
        "contract_trees": spec["contract_trees"],
        "runtime_identities": spec["runtime_identities"],
        "shared_dependencies_sha256": spec["shared_dependencies_sha256"],
        "shared_workload_sha256": spec["shared_workload_sha256"],
    }


def validate_generated_evidence(observed: object, binding: dict[str, object]) -> None:
    if binding.get("schema") != SCHEMA or not isinstance(observed, dict):
        raise ValueError("Current source-token generated parity evidence is missing.")
    if observed.keys() != {"base", "head"}:
        raise ValueError("Current source-token must retain both generated arms.")
    trees = binding["contract_trees"]
    if not isinstance(trees, dict) or trees.keys() != {"base", "head"}:
        raise ValueError("Current source-token must bind both complete contract inventories.")
    for side in ("base", "head"):
        if not trees[side] or observed[side] != [trees[side], trees[side], trees[side]]:
            raise ValueError(
                "Current source-token requires all three complete exact generated trees."
            )
