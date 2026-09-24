from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import cast

from scripts.tacoma_2026_source_audit import audit_tacoma_2026_sources

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.interaction_metadata import (
    InteractionKind,
    ParameterizedRequestLayout,
    adapter_visible_interaction_decision_types,
    decision_interaction_support_rows,
    parameterized_request_layout,
    registered_interaction_decision_types,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.weapon_abilities import WEAPON_ABILITY_SELECTION_DECISION_TYPE
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026

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


def test_p09a_split_movement_selection_surfaces_are_fully_retired() -> None:
    retired_tokens = (
        "complete_disembarks",
        "complete_reinforcements",
        "select_disembark_unit",
        "select_reinforcement_unit",
    )
    registered_types = {
        contract.decision_type for contract in GameLifecycle().decision_dispatch_contracts
    }
    assert registered_types.isdisjoint(retired_tokens)
    assert set(registered_interaction_decision_types()).isdisjoint(retired_tokens)

    engine_root = ROOT / "src" / "warhammer40k_core" / "engine"
    engine_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(engine_root.rglob("*.py"))
    )
    for retired_token in retired_tokens:
        assert retired_token not in engine_source


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


def test_tacoma_overlay_provenance_and_attachment_assumption_fail_closed() -> None:
    audit = audit_tacoma_2026_sources(ROOT)

    assert audit.source_pdf_sha256 == tacoma_open_2026.SOURCE_PDF_SHA256
    assert len(audit.cult_ambush_datasheet_ids) == 7
    assert audit.eligible_attaching_datasheet_ids


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


def test_parameterized_request_layouts_cover_dispatch_and_published_examples() -> None:
    registered = {
        contract.decision_type
        for contract in GameLifecycle().decision_dispatch_contracts
        if contract.submission_kind.value == "parameterized"
    }
    assert registered == {
        row["decision_type"]
        for row in decision_interaction_support_rows()
        if row["submission_kind"] == "parameterized"
    }
    flat = {
        "submit_healing_revival_placement",
        "submit_return_on_death_placement",
        "submit_catalog_model_materialization_placement",
        "submit_cult_ambush_marker_placement",
    }
    for decision_type in registered:
        expected = (
            ParameterizedRequestLayout.FLAT
            if decision_type in flat
            else ParameterizedRequestLayout.NESTED
        )
        assert parameterized_request_layout(decision_type) is expected
    examples = json.loads(
        (ROOT / "contracts/examples/decisions/interaction-conformance.json").read_text()
    )
    covered: set[str] = set()
    for case in examples["cases"]:
        request = case["request"]
        if not request["is_parameterized"]:
            continue
        decision_type = request["decision_type"]
        covered.add(decision_type)
        assert ("proposal_request" in request["payload"]) == (decision_type not in flat)
    assert covered == registered
    projection = (ROOT / "src/warhammer40k_core/adapters/projection.py").read_text()
    assert "parameterized_proposal_request_payload(request)" in projection
    context_reader = (
        INTERACTION_MODULE.read_text()
        .split("def _request_context(", 1)[1]
        .split("def _proposal_kind(", 1)[0]
    )
    assert "parameterized_proposal_request_payload(request)" in context_reader
    assert "def _metadata_bearing_proposal_request" not in projection
    # Every derived request projection must consume the existing shared redaction
    # result, including nested interaction payloads, before extracting context.
    for function, reader in (
        ("public_decision_request_view", "interaction_descriptor_for_request"),
        ("_proposal_view", "parameterized_proposal_request_payload"),
        ("_nested_interaction_request_views", "nested_interaction_request_payloads"),
    ):
        body = projection.split(f"def {function}(", 1)[1].split("\ndef ", 1)[0]
        assert body.index("public_decision_request_payload(") < body.index(f"{reader}(")
        assert "DecisionRequest.from_payload(" in body


def test_order81_matched_projection_component_budget() -> None:
    # Order 82 removes the obsolete HealingEffect field from the shared fixture.
    # Compare fresh measurements of both runtimes with that same fixture, while
    # preserving the original Order 81 evidence and its unchanged budget.
    folder = ROOT / "docs/performance/order82"
    base = json.loads((folder / "projection-base.json").read_text())
    head = json.loads((folder / "projection-head.json").read_text())
    budgets = json.loads((ROOT / "docs/performance/order81/projection-budgets.json").read_text())
    assert base["workload"] == head["workload"] == budgets["workload"]
    for key in (
        "python",
        "platform",
        "cpu",
        "logical_cpus",
        "memory_bytes",
        "workers",
        "lock_sha256",
        "script_sha256",
        "fixture_sha256",
    ):
        assert base[key] == head[key]
    assert (
        head["script_sha256"]
        == hashlib.sha256(
            (ROOT / "scripts/benchmark_order81_projection.py").read_bytes()
        ).hexdigest()
    )
    assert (
        head["fixture_sha256"]
        == hashlib.sha256((ROOT / "tests/order81_projection_helpers.py").read_bytes()).hexdigest()
    )
    assert len(base["rows"]) == len(head["rows"]) == 2
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["case"] == after["case"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 9
        assert before["iterations_per_sample"] == after["iterations_per_sample"] == 2000
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * budgets["mean_ratio"] + budgets["mean_additive_seconds"]
        )
        assert after["maximum_seconds"] <= budgets["maximum_seconds"]
    assert (
        base["proposal_projections"]["nested_request"]
        == head["proposal_projections"]["nested_request"]
    )
    assert base["proposal_projections"]["flat_request"]["status"] == "projection_error"
    assert head["proposal_projections"]["flat_request"]["status"] == "projected"
