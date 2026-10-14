"""Compare exact owned characteristic references without changing physical traces."""

from __future__ import annotations

import json
from typing import cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json


def compare_characteristic_descriptors(
    rules: dict[str, JsonValue], *, modifier_ids: dict[str, str]
) -> None:
    """All descriptor data survives; only source-proved modifier references change."""
    signature = cast(dict[str, JsonValue], rules["semantic_signature"])
    tokens: list[JsonValue] = []
    prefix = "skill-modifier:"
    for token in cast(list[str], signature["weapon_rule_tokens"]):
        if token.startswith(prefix):
            modifier = cast(dict[str, JsonValue], json.loads(token[len(prefix) :]))
            identifier = modifier.get("modifier_id")
            if isinstance(identifier, str) and identifier in modifier_ids:
                modifier["modifier_id"] = modifier_ids[identifier]
            token = prefix + canonical_json(modifier)
        tokens.append(token)
    signature["weapon_rule_tokens"] = sorted(tokens, key=canonical_json)
    for field in ("strength", "armor_penetration", "damage"):
        descriptor = cast(dict[str, JsonValue], json.loads(cast(str, signature[field])))
        _compare_descriptor(descriptor, modifier_ids)
        signature[field] = canonical_json(descriptor)
    basis = cast(str, signature["hit_basis"])
    prefix = "random_hit_target:"
    if basis.startswith(prefix):
        descriptor = cast(dict[str, JsonValue], json.loads(basis[len(prefix) :]))
        _compare_descriptor(descriptor, modifier_ids)
        signature["hit_basis"] = prefix + canonical_json(descriptor)
    numeric = cast(dict[str, JsonValue], rules["numeric_descriptors"])
    _compare_descriptor(cast(dict[str, JsonValue], numeric["strength"]), modifier_ids)


def _compare_descriptor(descriptor: dict[str, JsonValue], ids: dict[str, str]) -> None:
    trace = descriptor.get("modifier_trace")
    if isinstance(trace, dict):
        reorder = _compare_operations(trace, ids)
        _compare_references(trace, ids, reorder=reorder)
    else:
        reorder = _compare_operations(descriptor, ids)
    _compare_references(descriptor, ids, reorder=reorder)


def _compare_references(
    descriptor: dict[str, JsonValue], ids: dict[str, str], *, reorder: bool
) -> None:
    for field in ("applied_modifier_ids", "ignored_modifier_ids"):
        references = descriptor.get(field)
        if isinstance(references, list):
            replaced = [
                ids.get(item, item) if isinstance(item, str) else item for item in references
            ]
            descriptor[field] = sorted(replaced, key=canonical_json) if reorder else replaced


def _compare_operations(descriptor: dict[str, JsonValue], ids: dict[str, str]) -> bool:
    operations = descriptor.get("modifiers")
    if not isinstance(operations, list):
        return False
    # The actual stack orders these additions by ID. Their order is irrelevant
    # only with this complete source-proven commutative shape. Unknown IDs,
    # floors, sets, multiplication and exclusive/priority choices retain order.
    commutative = bool(operations) and all(
        isinstance(item, dict)
        and set(item)
        == {
            "modifier_id",
            "source_id",
            "operation",
            "operand",
            "timing",
            "priority",
            "exclusive_group",
            "scope",
        }
        and isinstance(item["modifier_id"], str)
        and item["modifier_id"] in ids
        and item["operation"] == "add"
        and item["timing"] == "additive"
        and item["priority"] == 0
        and item["exclusive_group"] is None
        for item in operations
    )
    for item in operations:
        if isinstance(item, dict):
            identifier = item.get("modifier_id")
            if isinstance(identifier, str) and identifier in ids:
                item["modifier_id"] = ids[identifier]
    if commutative:
        descriptor["modifiers"] = sorted(operations, key=canonical_json)
    return commutative
