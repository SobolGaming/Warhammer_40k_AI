from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import cast

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.interaction_metadata import (
    InteractionKind,
    adapter_visible_interaction_decision_types,
    registered_interaction_decision_types,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.weapon_abilities import WEAPON_ABILITY_SELECTION_DECISION_TYPE

ROOT = Path(__file__).resolve().parents[2]
INTERACTION_MODULE = ROOT / "src" / "warhammer40k_core" / "engine" / "interaction_metadata.py"
THIN_VISUAL_CONSUMERS = (
    ROOT / "src" / "warhammer40k_core" / "adapters" / "ui.py",
    ROOT / "src" / "warhammer40k_core" / "adapters" / "network.py",
    ROOT / "src" / "warhammer40k_core" / "interfaces" / "cli.py",
)
TYPESCRIPT_RENDERER = ROOT / "conformance" / "typescript" / "src" / "interaction.ts"
FRAMEWORK_TOKENS = frozenset(
    {"angular", "canvas", "component_id", "flutter", "react", "swiftui", "vue"}
)


def test_registered_decision_families_have_exact_interaction_metadata_coverage() -> None:
    contracts = GameLifecycle().decision_dispatch_contracts
    registered_types = {contract.decision_type for contract in contracts}

    assert registered_types == set(registered_interaction_decision_types())
    assert all(contract.interaction_kinds for contract in contracts)
    assert all(
        interaction_kind in {kind.value for kind in InteractionKind}
        for contract in contracts
        for interaction_kind in contract.interaction_kinds
    )
    assert set(adapter_visible_interaction_decision_types()) == {
        *registered_types,
        WEAPON_ABILITY_SELECTION_DECISION_TYPE,
    }
    cult_ambush = next(
        contract
        for contract in contracts
        if contract.decision_type == "submit_cult_ambush_marker_placement"
    )
    assert cult_ambush.interaction_kinds == (
        InteractionKind.BATTLEFIELD_POINT_PLACEMENT.value,
        InteractionKind.CONFIRMATION.value,
    )


def test_conformance_variant_renderer_unions_match_every_published_inventory() -> None:
    contracts_by_type = {
        contract.decision_type: contract for contract in GameLifecycle().decision_dispatch_contracts
    }
    coverage = _json_object(
        json.loads(
            (ROOT / "contracts" / "examples" / "decisions" / "family-coverage.json").read_text(
                encoding="utf-8"
            )
        )
    )
    support_profile = _json_object(
        json.loads(
            (ROOT / "contracts" / "examples" / "support-profile.json").read_text(encoding="utf-8")
        )
    )
    conformance = _json_object(
        json.loads(
            (
                ROOT / "contracts" / "examples" / "decisions" / "interaction-conformance.json"
            ).read_text(encoding="utf-8")
        )
    )
    family_rows = {
        _json_string(row["decision_type"]): row
        for value in _json_list(coverage["families"])
        if (row := _json_object(value))["registry_scope"] != "redaction"
    }
    support_rows = {
        _json_string(row["decision_type"]): row
        for value in _json_list(support_profile["decision_interaction_support_rows"])
        if (row := _json_object(value))
    }

    for value in _json_list(conformance["cases"]):
        case = _json_object(value)
        request = _json_object(case["request"])
        decision_type = _json_string(request["decision_type"])
        interaction = _json_object(request["interaction"])
        variant_kinds = {
            _json_string(_json_object(variant)["interaction_kind"])
            for variant in _json_list(interaction["submission_variants"])
        }
        family_kinds = _unique_string_set(family_rows[decision_type]["interaction_kinds"])
        support_kinds = _unique_string_set(support_rows[decision_type]["interaction_kinds"])
        contract = contracts_by_type.get(decision_type)
        contract_kinds = (
            _unique_string_set(list(contract.interaction_kinds))
            if contract is not None
            else variant_kinds
        )

        assert variant_kinds == contract_kinds == family_kinds == support_kinds


def test_published_interaction_kind_inventory_matches_engine_enum() -> None:
    schema = _json_object(
        json.loads(
            (ROOT / "contracts" / "schemas" / "interaction-descriptor.schema.json").read_text(
                encoding="utf-8"
            )
        )
    )
    coverage = _json_object(
        json.loads(
            (ROOT / "contracts" / "examples" / "decisions" / "family-coverage.json").read_text(
                encoding="utf-8"
            )
        )
    )
    definitions = _json_object(schema["$defs"])
    interaction_kind = _json_object(definitions["interaction_kind"])
    schema_values = {_json_string(value) for value in _json_list(interaction_kind["enum"])}
    engine_values = {kind.value for kind in InteractionKind}

    assert schema_values == engine_values
    assert coverage["standard_interaction_kinds"] == sorted(engine_values)
    assert coverage["interaction_kind_count"] == len(engine_values)


def test_visual_consumers_do_not_branch_on_decision_type() -> None:
    violations: list[str] = []
    for path in THIN_VISUAL_CONSUMERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.IfExp, ast.Match)) and _contains_decision_type(node):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not violations, (
        "Visual consumers must select interactions from engine-authored metadata, not "
        "decision_type branches:\n" + "\n".join(violations)
    )
    assert "decision_type" not in TYPESCRIPT_RENDERER.read_text(encoding="utf-8")


def test_interaction_metadata_is_presentation_neutral() -> None:
    source = INTERACTION_MODULE.read_text(encoding="utf-8").lower()
    present = sorted(
        token for token in FRAMEWORK_TOKENS if re.search(rf"\b{re.escape(token)}\b", source)
    )

    assert not present, "Interaction metadata contains framework tokens: " + ", ".join(present)


def _contains_decision_type(node: ast.AST) -> bool:
    return any(
        (isinstance(child, ast.Attribute) and child.attr == "decision_type")
        or (
            isinstance(child, ast.Constant)
            and type(child.value) is str
            and child.value == "decision_type"
        )
        for child in ast.walk(node)
    )


def _json_object(value: object) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return cast(dict[str, JsonValue], value)


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _json_string(value: JsonValue) -> str:
    assert type(value) is str
    return value


def _unique_string_set(value: JsonValue) -> set[str]:
    values = [_json_string(item) for item in _json_list(value)]
    assert values
    assert len(values) == len(set(values))
    return set(values)
