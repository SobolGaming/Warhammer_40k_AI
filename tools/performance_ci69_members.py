"""Authored finite CI69 provenance declarations, authenticated as current source.

These immutable literals extend the accepted controls without changing budgets,
assertions, live observation boundaries, or historical authorities.
"""

import ast
import hashlib
import json
from typing import Any

CONTROL_MEMBERS: frozenset[str] = frozenset(
    {
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        "AGENTS.md",
        "README.md",
        "docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md",
        "pyproject.toml",
        "scripts/build_test_shards.py",
        "tests/code_quality/test_ci_performance_gates.py",
        "tests/conftest.py",
        "tests/code_quality/test_thousand_sons_perils_preservation.py",
        "ci/quality_shards/all.txt",
        "ci/quality_shards/shard-1-modules.txt",
        "ci/quality_shards/shard-1.txt",
        "ci/quality_shards/shard-2-modules.txt",
        "ci/quality_shards/shard-2.txt",
        "ci/quality_shards/shard-3-modules.txt",
        "ci/quality_shards/shard-3.txt",
        "ci/quality_shards/shard-4-modules.txt",
        "ci/quality_shards/shard-4.txt",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "docs/performance/change-assessment.json",
        "docs/performance/policy-v3/operation-map.json",
        "tests/code_quality/test_cumulative_preservation.py",
        "tests/code_quality/test_d07_geometry_containment.py",
        "tests/code_quality/test_performance_category_migration.py",
        "tests/code_quality/test_performance_policy.py",
        "tests/code_quality/test_performance_preflight.py",
        "tests/code_quality/test_performance_provenance.py",
        "tests/code_quality/test_performance_static_successor.py",
        "tests/code_quality/test_qualification40_successor.py",
        "tests/code_quality/test_quality_runtime.py",
        "tests/d07_geometry_containment.py",
        "tools/cumulative_preservation.py",
        "tools/performance_ci60_qualification.py",
        "tools/performance_history_snapshot.py",
        "tools/performance_policy.py",
        "tools/performance_preflight.py",
        "tools/performance_preflight_successor.py",
    }
)

INPUT_ADDITIONS: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "scripts/build_test_shards.py",
        "src/warhammer40k_core/_engine_build_manifest.json",
        "src/warhammer40k_core/engine/model_attack_completion.py",
        "src/warhammer40k_core/engine/phases/shooting_decisions.py",
        "src/warhammer40k_core/engine/phases/shooting_handler.py",
        "src/warhammer40k_core/engine/phases/shooting_model.py",
        "src/warhammer40k_core/engine/retained_destruction_dispatch.py",
        "src/warhammer40k_core/engine/retained_shooting.py",
        "src/warhammer40k_core/engine/shooting_target_replacement.py",
        "src/warhammer40k_core/engine/target_replacement_dispatch.py",
        "tests/code_quality/test_ci_performance_gates.py",
        "tests/conftest.py",
        "tests/emergency_geometry_helpers.py",
        "tests/order101_failed_setup_helpers.py",
        "tests/phase13b_shooting_declaration_helpers.py",
        "tests/rules/rules24/unit/test_shadow_form_lookup.py",
        "tests/rules/section04/test_completion_boundaries.py",
        "tests/rules/section05/test_rule_effect_retention.py",
        "tests/rules/section11/test_required_target_protocol.py",
        "tests/support/section05_rule_effect_retention.py",
        "tests/unit/test_phase13b_shooting_declarations.py",
        "tests/unit/test_phase15c_fight_order.py",
        "tests/code_quality/test_thousand_sons_perils_preservation.py",
        "tests/code_quality/test_cumulative_preservation.py",
        "tests/code_quality/test_d07_geometry_containment.py",
        "tests/code_quality/test_performance_static_successor.py",
        "tests/code_quality/test_quality_runtime.py",
        "tests/d07_geometry_containment.py",
        "tests/data/d07_geometry_containment_v3.json",
        "tools/performance_ci69_members.py",
    }
)

OBSERVED_ADDITIONS: frozenset[str] = frozenset(
    {
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        "AGENTS.md",
        "README.md",
        "docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md",
        "pyproject.toml",
        "scripts/build_test_shards.py",
        "src/warhammer40k_core/_engine_build_manifest.json",
        "src/warhammer40k_core/engine/model_attack_completion.py",
        "src/warhammer40k_core/engine/phases/shooting_decisions.py",
        "src/warhammer40k_core/engine/phases/shooting_handler.py",
        "src/warhammer40k_core/engine/phases/shooting_model.py",
        "src/warhammer40k_core/engine/retained_destruction_dispatch.py",
        "src/warhammer40k_core/engine/retained_shooting.py",
        "src/warhammer40k_core/engine/shooting_target_replacement.py",
        "src/warhammer40k_core/engine/target_replacement_dispatch.py",
        "tests/code_quality/test_ci_performance_gates.py",
        "tests/conftest.py",
        "tests/emergency_geometry_helpers.py",
        "tests/order101_failed_setup_helpers.py",
        "tests/phase13b_shooting_declaration_helpers.py",
        "tests/rules/section04/test_completion_boundaries.py",
        "tests/unit/test_phase13b_shooting_declarations.py",
        "tests/unit/test_phase15c_fight_order.py",
        "tests/code_quality/test_thousand_sons_perils_preservation.py",
        "ci/quality_shards/shard-2-modules.txt",
        "ci/quality_shards/shard-3-modules.txt",
        "ci/quality_shards/shard-4-modules.txt",
        "ci/quality_shards/shard-4.txt",
        "tests/code_quality/test_d07_geometry_containment.py",
        "tests/code_quality/test_performance_static_successor.py",
        "tests/code_quality/test_quality_runtime.py",
        "tests/d07_geometry_containment.py",
    }
)


CUTOVER_PATH = "data/source_audits/ci64_provenance_v1/test-cutover.json"

RUNTIME_SUCCESSORS: frozenset[str] = frozenset(
    {
        "src/warhammer40k_core/_engine_build_manifest.json",
        "src/warhammer40k_core/engine/model_attack_completion.py",
        "src/warhammer40k_core/engine/phases/shooting_decisions.py",
        "src/warhammer40k_core/engine/phases/shooting_handler.py",
        "src/warhammer40k_core/engine/phases/shooting_model.py",
        "src/warhammer40k_core/engine/retained_destruction_dispatch.py",
        "src/warhammer40k_core/engine/retained_shooting.py",
        "src/warhammer40k_core/engine/shooting_target_replacement.py",
        "src/warhammer40k_core/engine/target_replacement_dispatch.py",
        "tests/emergency_geometry_helpers.py",
        "tests/order101_failed_setup_helpers.py",
        "tests/phase13b_shooting_declaration_helpers.py",
        "tests/rules/section04/test_completion_boundaries.py",
        "tests/unit/test_phase13b_shooting_declarations.py",
        "tests/unit/test_phase15c_fight_order.py",
    }
)

CUTOVER_NEW: frozenset[str] = frozenset(
    {
        "data/source_audits/ci64_provenance_v1/test-cutover.json",
        "tests/rules/rules24/unit/test_shadow_form_lookup.py",
        "tests/rules/section05/test_rule_effect_retention.py",
        "tests/rules/section11/test_required_target_protocol.py",
        "tests/support/section05_rule_effect_retention.py",
    }
)

CUTOVER_ADDED_INPUTS: frozenset[str] = frozenset(
    {
        "tests/rules/rules24/unit/test_shadow_form_lookup.py",
        "tests/rules/section05/test_rule_effect_retention.py",
        "tests/rules/section11/test_required_target_protocol.py",
        "tests/support/section05_rule_effect_retention.py",
    }
)


def expected_observed() -> frozenset[str]:
    """Independent literal boundary; never alias the mutable declaration name."""
    return frozenset(
        {
            ".github/pull_request_template.md",
            ".github/workflows/ci.yml",
            "AGENTS.md",
            "README.md",
            "ci/quality_shards/shard-2-modules.txt",
            "ci/quality_shards/shard-3-modules.txt",
            "ci/quality_shards/shard-4-modules.txt",
            "ci/quality_shards/shard-4.txt",
            "docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md",
            "pyproject.toml",
            "scripts/build_test_shards.py",
            "src/warhammer40k_core/_engine_build_manifest.json",
            "src/warhammer40k_core/engine/model_attack_completion.py",
            "src/warhammer40k_core/engine/phases/shooting_decisions.py",
            "src/warhammer40k_core/engine/phases/shooting_handler.py",
            "src/warhammer40k_core/engine/phases/shooting_model.py",
            "src/warhammer40k_core/engine/retained_destruction_dispatch.py",
            "src/warhammer40k_core/engine/retained_shooting.py",
            "src/warhammer40k_core/engine/shooting_target_replacement.py",
            "src/warhammer40k_core/engine/target_replacement_dispatch.py",
            "tests/code_quality/test_ci_performance_gates.py",
            "tests/code_quality/test_d07_geometry_containment.py",
            "tests/code_quality/test_performance_category_migration.py",
            "tests/code_quality/test_performance_static_successor.py",
            "tests/code_quality/test_quality_runtime.py",
            "tests/code_quality/test_thousand_sons_perils_preservation.py",
            "tests/conftest.py",
            "tests/d07_geometry_containment.py",
            "tests/emergency_geometry_helpers.py",
            "tests/order101_failed_setup_helpers.py",
            "tests/phase13b_shooting_declaration_helpers.py",
            "tests/rules/section04/test_completion_boundaries.py",
            "tests/unit/test_phase13b_shooting_declarations.py",
            "tests/unit/test_phase15c_fight_order.py",
            "tools/performance_preflight_successor.py",
        }
    )


def validate_cutover(operands: tuple[tuple[str, int, bytes], ...]) -> None:
    """One code-pinned selection baseline; never historical measurement credit."""
    values = {name: raw for name, _, raw in operands}
    record: dict[str, Any] = json.loads(values["next-frozen/" + CUTOVER_PATH])
    required = {
        "schema",
        "source_base",
        "active_roots",
        "native_active_files",
        "active_files",
        "retained_active_files",
        "inactive_legacy_files",
        "inactive_updates",
        "benchmark_files",
        "retirements",
        "coverage",
    }
    if (
        type(record) is not dict
        or record.keys() != required
        or record["schema"] != "finite-test-cutover-v1"
    ):
        raise ValueError("Finite cutover schema changed.")
    baseline = {
        name: record[name]
        for name in (
            "source_base",
            "active_roots",
            "native_active_files",
            "retained_active_files",
            "inactive_legacy_files",
            "benchmark_files",
        )
    }
    encoded = json.dumps(baseline, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if (
        hashlib.sha256(encoded).hexdigest()
        != "207e59b1e4f56c209ca35f1839823a3dfa94e0ad71e231334549b3ce74945217"
    ):
        raise ValueError("Finite native5734 behavioral selection baseline changed.")
    if record["retirements"] != []:
        raise ValueError("Physical retirement is not admitted by this initial cutover.")
    coverage = record["coverage"]
    if (
        type(coverage) is not dict
        or coverage.keys()
        != {"metric", "source", "current_floor", "restoration_floor", "restoration_condition"}
        or coverage["metric"] != "coverage.py total with branch=true"
        or coverage["source"] != ["warhammer40k_core"]
        or type(coverage["current_floor"]) is not int
        or coverage["current_floor"] != 50
        or type(coverage["restoration_floor"]) is not int
        or coverage["restoration_floor"] != 85
        or type(coverage["restoration_condition"]) is not str
        or len(coverage["restoration_condition"].strip()) < 30
    ):
        raise ValueError("Finite temporary branch-coverage policy changed.")
    frozen = {name[12:]: raw for name, _, raw in operands if name.startswith("next-frozen/")}
    modes = {
        name.split("/", 1)[1]: mode
        for name, mode, _ in operands
        if name.startswith(("current/", "observed/", "next-current/"))
    }

    def current_row(name: str, row: Any) -> None:
        if type(row) is not dict or row.keys() != {"mode", "blob_sha1", "sha256", "bytes"}:
            raise ValueError("Finite current test row changed.")
        raw = frozen[name]
        oid = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()
        if (
            row["mode"] not in {"100644", "100755"}
            or ("100755" if modes[name] & 0o100 else "100644") != row["mode"]
            or type(row["bytes"]) is not int
            or row["bytes"] != len(raw)
            or row["blob_sha1"] != oid
            or row["sha256"] != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("Finite current test differs from its authenticated bytes or mode.")

    active = record["active_files"]
    native = record["native_active_files"]
    ports = {
        "tests/rules/rules24/unit/test_shadow_form_lookup.py",
        "tests/rules/section05/test_rule_effect_retention.py",
        "tests/rules/section11/test_required_target_protocol.py",
    }
    if type(active) is not dict or active.keys() != native.keys() | ports:
        raise ValueError("Finite active test membership omitted or invented a test.")
    changed_active = ports | {"tests/rules/section04/test_completion_boundaries.py"}
    for name, row in active.items():
        if name in changed_active:
            current_row(name, row)
        elif row != native[name]:
            raise ValueError("Unchanged native active test identity changed.")
    recipes: dict[str, Any] = {
        "tests/unit/test_phase15c_fight_order.py": {
            "before_ast_sha256": "159c3503ffc46bf5ab9093fcfd9560346187f715bf9f252c6f56b2b13c9c065d",
            "sites": [
                (
                    "test_pending_destroyed_transport_retains_physical_model_but_restores_living_history",
                    0,
                )
            ],
        },
        "tests/unit/test_phase13b_shooting_declarations.py": {
            "before_ast_sha256": "ee166830b3e78b490309691b1d4f06a690301948ec2d8e6f05217ce5382f7515",
            "sites": [
                (
                    "test_phase14k_grouped_damage_requests_defender_model_choice_inside_current_group",
                    0,
                ),
                (
                    "test_phase14k_damage_model_choice_stale_pending_damage_rejects_before_queue_pop",
                    0,
                ),
                ("test_phase14c_hazardous_mortal_wounds_route_optional_fnp_through_lifecycle", 0),
                ("test_phase14c_hazardous_mortal_wounds_route_optional_fnp_through_lifecycle", 1),
                ("test_p24d_hazardous_preserves_order_through_completion_and_restore", 0),
                ("test_phase14l_attack_sequence_selection_invalid_before_queue_pop", 0),
                ("test_phase13c_optional_feel_no_pain_choice_routes_through_lifecycle", 0),
                ("test_phase13e_destroyed_model_reaction_choice_records_removal_and_selection", 0),
                ("test_order_9_p05a_destruction_reaction_waits_for_attacking_unit_attacks", 0),
                ("_retain_attack_casualty_for_fight_on_death", 0),
                ("_retain_attack_casualty_for_fight_on_death", 1),
                (
                    "test_phase14h_destroyed_transport_disembarks_before_removal_and_deadly_demise",
                    0,
                ),
                ("test_phase13e_successful_deadly_demise_applies_mortal_wounds_before_removal", 0),
                ("test_phase13e_deadly_demise_fnp_pauses_before_destroyed_model_removal", 0),
                (
                    "test_phase13e_deadly_demise_secondary_casualty_gets_removal_record_and_reaction",
                    0,
                ),
                ("test_phase13e_destruction_reaction_invalid_submission_does_not_mutate_queue", 0),
            ],
        },
    }
    updates = record["inactive_updates"]
    if type(updates) is not dict or updates.keys() != recipes.keys():
        raise ValueError("Finite inactive API update membership changed.")
    wanted = ast.dump(
        ast.parse("lifecycle.decision_controller.queue.pending_requests", mode="eval").body,
        include_attributes=False,
    )
    for name, recipe in recipes.items():
        update = updates[name]
        if (
            type(update) is not dict
            or update.keys() != {"before", "after", "recipe"}
            or update["before"] != record["inactive_legacy_files"][name]
            or update["recipe"] != "add-pending-decision-requests-v1"
        ):
            raise ValueError("Finite inactive API update preimage or recipe changed.")
        current_row(name, update["after"])
        tree = ast.parse(frozen[name])
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for owner, index in recipe["sites"]:
            calls = [
                node
                for node in ast.walk(functions[owner])
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "with_attack_sequence_update"
            ]
            call = calls[index]
            keywords = [key for key in call.keywords if key.arg == "pending_decision_requests"]
            if (
                len(keywords) != 1
                or ast.dump(keywords[0].value, include_attributes=False) != wanted
            ):
                raise ValueError("Finite pending-decision owner argument changed.")
            call.keywords.remove(keywords[0])
        restored = hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
        if restored != recipe["before_ast_sha256"]:
            raise ValueError("Inactive API update changed an original AST or assertion.")
