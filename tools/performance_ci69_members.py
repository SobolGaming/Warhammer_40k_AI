"""Authored finite CI69 provenance declarations, authenticated as current source.

These immutable literals extend the accepted controls without changing budgets,
assertions, live observation boundaries, or historical authorities.
"""

import ast
import hashlib
import json
from pathlib import Path
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


RETIREMENT_NAMESPACE = "data/source_audits/ci64_provenance_v1/retired-tests/"
RETIRED_TESTS: frozenset[str] = frozenset(
    {
        "tests/integration/test_order127_infiltrators_redeploy.py",
        "tests/integration/test_order128_setup_overhang.py",
        "tests/integration/test_order135_gathered_override.py",
        "tests/integration/test_order135_gathered_psychic_preparation.py",
        "tests/unit/test_order100_frame_measurement.py",
        "tests/unit/test_order101_setup_failure.py",
        "tests/unit/test_order104_range_visibility.py",
        "tests/unit/test_order105_hazard.py",
        "tests/unit/test_order106_pile_in.py",
        "tests/unit/test_order107_fight_distance_window.py",
        "tests/unit/test_order108_terrain_semantics.py",
        "tests/unit/test_order109_unit_control.py",
        "tests/unit/test_order111_friendly_transit.py",
        "tests/unit/test_order115_absent_movement.py",
        "tests/unit/test_order116_additional_mortals.py",
        "tests/unit/test_order117_mortal_allocation.py",
        "tests/unit/test_order121_command_abilities.py",
        "tests/unit/test_order122_effect_defaults.py",
        "tests/unit/test_order123_datasheet_identity.py",
        "tests/unit/test_order124_nested_conditions.py",
        "tests/unit/test_order125_implicit_subjects.py",
        "tests/unit/test_order126_sequential_movement.py",
        "tests/unit/test_order128_setup_model_fit.py",
        "tests/unit/test_order129_flight_history.py",
        "tests/unit/test_order130_model_mission_destruction.py",
        "tests/unit/test_order131_objective_endpoint_geometry.py",
        "tests/unit/test_order131_objective_movement.py",
        "tests/unit/test_order132_disembark_distance.py",
        "tests/unit/test_order133_keyword_materialization.py",
        "tests/unit/test_order133_keyword_numbers.py",
        "tests/unit/test_order134_deployment_restrictions.py",
        "tests/unit/test_order135_combat_tactical_feasibility.py",
        "tests/unit/test_order135_counteroffensive_band.py",
        "tests/unit/test_order135_counteroffensive_timing.py",
        "tests/unit/test_order135_fight_pass.py",
        "tests/unit/test_order135_fight_transition.py",
        "tests/unit/test_order135_gathered_attack_steps.py",
        "tests/unit/test_order135_gathered_wound_callback.py",
        "tests/unit/test_order135_objective_overlap.py",
        "tests/unit/test_order135_physical_visibility.py",
        "tests/unit/test_order135_shooting_boundary.py",
        "tests/unit/test_order135_tactical_setup_proof.py",
        "tests/unit/test_order135_transport_boundaries.py",
        "tests/unit/test_order135_visibility_facade.py",
        "tests/unit/test_order135_visibility_rng_projection.py",
        "tests/unit/test_order36_sequencing.py",
        "tests/unit/test_order36_timing_authority.py",
        "tests/unit/test_order51_flight.py",
        "tests/unit/test_order52_surge.py",
        "tests/unit/test_order53_movement_abilities.py",
        "tests/unit/test_order54_setup.py",
        "tests/unit/test_order55_disembark.py",
        "tests/unit/test_order57_destroyed_referent_measurement.py",
        "tests/unit/test_order58_failed_save_damage_timing.py",
        "tests/unit/test_order59_empty_dedicated_transport.py",
        "tests/unit/test_order60_emergency_disembark.py",
        "tests/unit/test_order61_embark.py",
        "tests/unit/test_order63_reserve_transports.py",
        "tests/unit/test_order64_reserve_lifetimes.py",
        "tests/unit/test_order65_firing_deck.py",
        "tests/unit/test_order78_gone_to_ground.py",
        "tests/unit/test_order79_control_first.py",
        "tests/unit/test_order80_normal_move.py",
        "tests/unit/test_order81_parameterized_projection.py",
        "tests/unit/test_order82_revival_engagement.py",
        "tests/unit/test_order85_deemed_base_contact.py",
        "tests/unit/test_order86_table_quarters.py",
        "tests/unit/test_order87_gathered_profile_restore.py",
        "tests/unit/test_order87_random_profiles.py",
        "tests/unit/test_order88_absent_strength.py",
        "tests/unit/test_order89_healing.py",
        "tests/unit/test_order90_off_battlefield_revival.py",
        "tests/unit/test_order91_empty_shooting.py",
        "tests/unit/test_order92_random_melee.py",
        "tests/unit/test_order93_attack_modifiers.py",
        "tests/unit/test_order93_catalog_leadership_modifiers.py",
        "tests/unit/test_order93_healing_modifiers.py",
        "tests/unit/test_order93_mission_action_modifiers.py",
        "tests/unit/test_order93_modifier_ignore.py",
        "tests/unit/test_order93_nonattack_modifiers.py",
        "tests/unit/test_order93_permission_context.py",
        "tests/unit/test_order93_weapon_modifiers.py",
        "tests/unit/test_order95_optional_shooting.py",
        "tests/unit/test_order96_twin_linked.py",
        "tests/unit/test_order97_attack_evidence.py",
        "tests/unit/test_order97_damage_evidence.py",
        "tests/unit/test_order97_facade_evidence.py",
        "tests/unit/test_order97_foundation_evidence.py",
        "tests/unit/test_order97_movement_evidence.py",
        "tests/unit/test_order97_secondary_clause_evidence.py",
        "tests/unit/test_order97_semantic_evidence_18_25.py",
        "tests/unit/test_order97_timing_evidence.py",
    }
)


def expected_observed() -> frozenset[str]:
    """Independent literal boundary; never alias the mutable declaration name."""
    return frozenset(
        {
            "docs/ORDER_124_SCOPE_PLAN.md",
            "docs/SECTION24_CORE_ABILITIES_SCOPE.md",
            "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py",
            "src/warhammer40k_core/engine/catalog_shadow_form_runtime.py",
            "src/warhammer40k_core/engine/decision.py",
            "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
            "src/warhammer40k_core/engine/phases/charge.py",
            "tests/integration/test_catalog_rule_ir_runtime.py",
            "tests/integration/test_embarked_ability_authority.py",
            "tests/integration/test_fight_on_death_presence.py",
            "tests/integration/test_retained_shooting.py",
            "tests/phase15a_charge_declaration_helpers.py",
            "tests/psychic_modifier_helpers.py",
            "tests/replay/test_phase18b_replay_runner.py",
            "tests/rules/section07/coverage.json",
            "tests/rules/section18/coverage.json",
            "tests/rules/section20/coverage.json",
            "tests/rules/section22/coverage.json",
            "tests/rules/section24/README.md",
            "tests/rules/section24/coverage.json",
            "tests/rules/section24/test_inventory.py",
            "tests/shared/category_migration/phase17d_rule_execution.py",
            "tests/unit/test_dice.py",
            "tests/unit/test_phase11e_mission_scoring_cleanup.py",
            "tests/unit/test_phase15a_charge_declarations.py",
            "tests/unit/test_phase17_emperors_children_datasheet_overlay.py",
            "tests/unit/test_phase17g_chaos_daemons_blood_legion.py",
            "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py",
            "tests/unit/test_phase17n_runtime_rule_ir_oc_authority.py",
            "ci/test_shards/durations.json",
            "ci/test_shards/shard-1.txt",
            "ci/test_shards/shard-10.txt",
            "ci/test_shards/shard-11.txt",
            "ci/test_shards/shard-12.txt",
            "ci/test_shards/shard-2.txt",
            "ci/test_shards/shard-3.txt",
            "ci/test_shards/shard-4.txt",
            "ci/test_shards/shard-5.txt",
            "ci/test_shards/shard-6.txt",
            "ci/test_shards/shard-7.txt",
            "ci/test_shards/shard-8.txt",
            "ci/test_shards/shard-9.txt",
            "scripts/measure_order72.py",
            "contracts/examples/persistence/session-persistence.json",
            "contracts/examples/sessions/session-command-outcome.json",
            "contracts/examples/sessions/session-command-started.json",
            "contracts/examples/sessions/session-metadata-created.json",
            "contracts/examples/support-profile-player-a-redacted.json",
            "contracts/examples/support-profile-player-b-redacted.json",
            "contracts/examples/support-profile.json",
            "contracts/manifest.json",
            "tools/core_rules_order95_audit.py",
            "tests/category_migration_preservation.py",
            "tests/code_quality/test_order135_current_core_audit.py",
            "tests/code_quality/test_s25_fixture_preservation.py",
            "tools/core_rules_order97_history.py",
            "tools/core_rules_order97_inventory.py",
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
    retired = retirement_rows(record)
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
        "tests/performance/test_fight_phase_reconstruction.py",
        "tests/rules/rules24/unit/test_shadow_form_lookup.py",
        "tests/rules/section05/test_rule_effect_retention.py",
        "tests/rules/section11/test_required_target_protocol.py",
    }
    if type(active) is not dict or active.keys() != native.keys() | ports:
        raise ValueError("Finite active test membership omitted or invented a test.")
    changed_active = ports | {
        "tests/rules/section04/test_completion_boundaries.py",
        "tests/rules/section24/test_inventory.py",
    }
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
    for row in retired.values():
        current_row(row["archive"], row["native"])
    updates = record["inactive_updates"]
    typed_name = "tests/integration/test_embarked_ability_authority.py"
    if type(updates) is not dict or updates.keys() != recipes.keys() | {typed_name}:
        raise ValueError("Finite inactive API update membership changed.")
    wanted = ast.dump(
        ast.parse("lifecycle.decision_controller.queue.pending_requests", mode="eval").body,
        include_attributes=False,
    )
    typed = updates[typed_name]
    if (
        type(typed) is not dict
        or typed.keys() != {"before", "after", "recipe"}
        or typed["before"] != record["inactive_legacy_files"][typed_name]
        or typed["recipe"] != "type-only-battle-phase-cast-v1"
    ):
        raise ValueError("Finite inactive typing update changed its native preimage or recipe.")
    current_row(typed_name, typed["after"])
    raw = frozen[typed_name]
    after_assert = b"assert cast(BattlePhase, state.current_battle_phase) is BattlePhase.SHOOTING"
    before_assert = b"assert state.current_battle_phase is BattlePhase.SHOOTING"
    if (
        raw.count(after_assert) != 1
        or hashlib.sha256(raw.replace(after_assert, before_assert, 1)).hexdigest()
        != typed["before"]["sha256"]
    ):
        raise ValueError("Finite inactive typing update changed bytes beyond the exact cast.")
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


def retirement_rows(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Authenticate this exact policy retirement; never imply current execution."""
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
        raise ValueError("Retirement native5734 classification changed.")
    supplied = record["retirements"]
    if type(supplied) is not list or len(supplied) != 92:
        raise ValueError("Exact92 retirement membership changed.")
    rows: dict[str, dict[str, Any]] = {}
    for row in supplied:
        if type(row) is not dict or row.keys() != {"path", "archive", "native"}:
            raise ValueError("Malformed retirement row.")
        name = row["path"]
        if type(name) is not str or name not in RETIRED_TESTS or name in rows:
            raise ValueError("Unlisted or duplicate retired test.")
        if (
            row["archive"] != RETIREMENT_NAMESPACE + name + ".txt"
            or row["native"] != record["inactive_legacy_files"][name]
        ):
            raise ValueError("Retirement archive or native identity changed.")
        rows[name] = row
    native = {name: row["native"] for name, row in rows.items()}
    encoded = json.dumps(native, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if (
        rows.keys() != RETIRED_TESTS
        or hashlib.sha256(encoded).hexdigest()
        != "30ce81d57e4fe404dfac0de28662f1ae428d716a29ef095d711f520a4315ad46"
    ):
        raise ValueError("Exact92 native retirement authority changed.")
    return rows


def retirement_absence(root: Path, names: tuple[str, ...] | None = None) -> None:
    """Fresh absence includes broken symlinks; this never supplies source bytes."""
    if root.absolute() != root.resolve(strict=True):
        raise ValueError("Retirement root is aliased.")
    selected = tuple(sorted(RETIRED_TESTS)) if names is None else names
    if any(name not in RETIRED_TESTS for name in selected):
        raise ValueError("Unlisted retirement absence request.")
    for name in selected:
        target = root / name
        if target.parent.resolve(strict=True) != target.parent:
            raise ValueError("Retirement parent is aliased.")
        try:
            target.lstat()
        except FileNotFoundError:
            continue
        raise ValueError("Retired test reappeared: " + name)


def retired_test_source(root: Path, name: str) -> tuple[Path, bytes] | None:
    """Historical only; unregistered roots retain their strict physical readers."""
    if name not in RETIRED_TESTS or not (root / CUTOVER_PATH).is_file():
        return None
    from tools.performance_preflight import source_members

    retirement_absence(root, (name,))
    archive = RETIREMENT_NAMESPACE + name + ".txt"
    observed = source_members(root, [CUTOVER_PATH, archive])
    values = {path: raw for path, _, raw in observed}
    rows = retirement_rows(json.loads(values[CUTOVER_PATH]))
    row = rows[name]["native"]
    mode = {path: mode for path, mode, _ in observed}[archive]
    raw = values[archive]
    oid = hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
    ).hexdigest()
    if (
        ("100755" if mode & 0o100 else "100644") != row["mode"]
        or len(raw) != row["bytes"]
        or hashlib.sha256(raw).hexdigest() != row["sha256"]
        or oid != row["blob_sha1"]
    ):
        raise ValueError("Retired native source archive changed.")
    retirement_absence(root, (name,))
    return root / archive, raw


def current_source_projection(previous: dict[str, str], actual: dict[str, bytes]) -> dict[str, str]:
    """Actual current membership omits retired tests; historical bytes stay separate."""
    return {name: pin for name, pin in previous.items() if name not in RETIRED_TESTS} | {
        name: hashlib.sha256(raw).hexdigest() for name, raw in actual.items()
    }


CONTROL_MEMBERS |= frozenset(
    [
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_order135_current_core_audit.py",
        "tests/code_quality/test_s25_fixture_preservation.py",
        "tools/core_rules_order97_history.py",
        "tools/core_rules_order97_inventory.py",
    ]
)
INPUT_ADDITIONS |= RETIRED_TESTS | frozenset(
    [
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_order135_current_core_audit.py",
        "tests/code_quality/test_s25_fixture_preservation.py",
        "tools/core_rules_order97_history.py",
        "tools/core_rules_order97_inventory.py",
    ]
)
OBSERVED_ADDITIONS |= frozenset(
    [
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_order135_current_core_audit.py",
        "tests/code_quality/test_s25_fixture_preservation.py",
        "tools/core_rules_order97_history.py",
        "tools/core_rules_order97_inventory.py",
    ]
)
CUTOVER_NEW |= frozenset(RETIREMENT_NAMESPACE + name + ".txt" for name in RETIRED_TESTS)

CONTROL_MEMBERS |= frozenset({"tools/core_rules_order95_audit.py"})
INPUT_ADDITIONS |= frozenset({"tools/core_rules_order95_audit.py"})
OBSERVED_ADDITIONS |= frozenset({"tools/core_rules_order95_audit.py"})

RUNTIME_SUCCESSORS |= frozenset(
    [
        "contracts/examples/persistence/session-persistence.json",
        "contracts/examples/sessions/session-command-outcome.json",
        "contracts/examples/sessions/session-command-started.json",
        "contracts/examples/sessions/session-metadata-created.json",
        "contracts/examples/support-profile-player-a-redacted.json",
        "contracts/examples/support-profile-player-b-redacted.json",
        "contracts/examples/support-profile.json",
        "contracts/manifest.json",
    ]
)
OBSERVED_ADDITIONS |= frozenset(
    [
        "contracts/examples/persistence/session-persistence.json",
        "contracts/examples/sessions/session-command-outcome.json",
        "contracts/examples/sessions/session-command-started.json",
        "contracts/examples/sessions/session-metadata-created.json",
        "contracts/examples/support-profile-player-a-redacted.json",
        "contracts/examples/support-profile-player-b-redacted.json",
        "contracts/examples/support-profile.json",
        "contracts/manifest.json",
    ]
)

RUNTIME_SUCCESSORS |= frozenset({"scripts/measure_order72.py"})
INPUT_ADDITIONS |= frozenset(
    [
        "tests/performance/test_fight_phase_reconstruction.py",
        "tests/support/fight_phase_reconstruction.py",
        "scripts/measure_order72.py",
    ]
)
CUTOVER_NEW |= frozenset(
    [
        "tests/performance/test_fight_phase_reconstruction.py",
        "tests/support/fight_phase_reconstruction.py",
        "ci/test_shards/case-partitions.json",
    ]
)
CUTOVER_ADDED_INPUTS |= frozenset(
    [
        "tests/performance/test_fight_phase_reconstruction.py",
        "tests/support/fight_phase_reconstruction.py",
    ]
)
OBSERVED_ADDITIONS |= frozenset({"scripts/measure_order72.py"})


def prelude_members(raw: bytes, members: frozenset[str]) -> list[str]:
    """One native no-renames status fact proves all92 are deleted in immutable F."""
    expected = members | RETIRED_TESTS
    if len(raw) != sum(len(name.encode()) + 3 for name in expected):
        raise ValueError("CI64 native source-status byte count changed.")
    fields = raw.split(b"\0")
    if fields[-1:] != [b""] or len(fields) % 2 != 1:
        raise ValueError("CI64 native source-status framing changed.")
    rows: dict[str, bytes] = {}
    for status, encoded in zip(fields[:-1:2], fields[1:-1:2], strict=True):
        name = encoded.decode()
        if name not in expected or name in rows:
            raise ValueError("CI64 native source-status membership changed.")
        if name in RETIRED_TESTS:
            if status != b"D":
                raise ValueError("CI64 source freeze retains a retired test.")
        elif status not in {b"A", b"M"}:
            raise ValueError("CI64 live source-status changed.")
        rows[name] = status
    if rows.keys() != expected:
        raise ValueError("CI64 native source-status membership changed.")
    return sorted(rows)


CONTROL_MEMBERS |= frozenset(
    [
        "ci/test_shards/durations.json",
        "ci/test_shards/shard-1.txt",
        "ci/test_shards/shard-10.txt",
        "ci/test_shards/shard-11.txt",
        "ci/test_shards/shard-12.txt",
        "ci/test_shards/shard-2.txt",
        "ci/test_shards/shard-3.txt",
        "ci/test_shards/shard-4.txt",
        "ci/test_shards/shard-5.txt",
        "ci/test_shards/shard-6.txt",
        "ci/test_shards/shard-7.txt",
        "ci/test_shards/shard-8.txt",
        "ci/test_shards/shard-9.txt",
    ]
)
OBSERVED_ADDITIONS |= frozenset(
    [
        "ci/test_shards/durations.json",
        "ci/test_shards/shard-1.txt",
        "ci/test_shards/shard-10.txt",
        "ci/test_shards/shard-11.txt",
        "ci/test_shards/shard-12.txt",
        "ci/test_shards/shard-2.txt",
        "ci/test_shards/shard-3.txt",
        "ci/test_shards/shard-4.txt",
        "ci/test_shards/shard-5.txt",
        "ci/test_shards/shard-6.txt",
        "ci/test_shards/shard-7.txt",
        "ci/test_shards/shard-8.txt",
        "ci/test_shards/shard-9.txt",
    ]
)

# Exact current source and native evidence epoch; no historical input is repinned.

CONTROL_MEMBERS |= frozenset(
    {
        "docs/ORDER_124_SCOPE_PLAN.md",
        "docs/SECTION24_CORE_ABILITIES_SCOPE.md",
        "tests/rules/section24/README.md",
    }
)

RUNTIME_SUCCESSORS |= frozenset(
    {
        "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py",
        "src/warhammer40k_core/engine/catalog_shadow_form_runtime.py",
        "src/warhammer40k_core/engine/decision.py",
        "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
        "src/warhammer40k_core/engine/phases/charge.py",
        "tests/integration/test_catalog_rule_ir_runtime.py",
        "tests/integration/test_embarked_ability_authority.py",
        "tests/integration/test_fight_on_death_presence.py",
        "tests/integration/test_retained_shooting.py",
        "tests/phase15a_charge_declaration_helpers.py",
        "tests/psychic_modifier_helpers.py",
        "tests/replay/test_phase18b_replay_runner.py",
        "tests/rules/section07/coverage.json",
        "tests/rules/section18/coverage.json",
        "tests/rules/section20/coverage.json",
        "tests/rules/section22/coverage.json",
        "tests/rules/section24/coverage.json",
        "tests/rules/section24/test_inventory.py",
        "tests/shared/category_migration/phase17d_rule_execution.py",
        "tests/unit/test_dice.py",
        "tests/unit/test_phase11e_mission_scoring_cleanup.py",
        "tests/unit/test_phase15a_charge_declarations.py",
        "tests/unit/test_phase17_emperors_children_datasheet_overlay.py",
        "tests/unit/test_phase17g_chaos_daemons_blood_legion.py",
        "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py",
        "tests/unit/test_phase17n_runtime_rule_ir_oc_authority.py",
    }
)

INPUT_ADDITIONS |= frozenset(
    {
        "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py",
        "src/warhammer40k_core/engine/catalog_shadow_form_runtime.py",
        "src/warhammer40k_core/engine/decision.py",
        "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
        "src/warhammer40k_core/engine/phases/charge.py",
        "tests/integration/test_catalog_rule_ir_runtime.py",
        "tests/integration/test_embarked_ability_authority.py",
        "tests/integration/test_fight_on_death_presence.py",
        "tests/integration/test_retained_shooting.py",
        "tests/phase15a_charge_declaration_helpers.py",
        "tests/psychic_modifier_helpers.py",
        "tests/replay/test_phase18b_replay_runner.py",
        "tests/rules/section07/coverage.json",
        "tests/rules/section18/coverage.json",
        "tests/rules/section20/coverage.json",
        "tests/rules/section22/coverage.json",
        "tests/rules/section24/coverage.json",
        "tests/rules/section24/test_inventory.py",
        "tests/shared/category_migration/phase17d_rule_execution.py",
        "tests/unit/test_dice.py",
        "tests/unit/test_phase11e_mission_scoring_cleanup.py",
        "tests/unit/test_phase15a_charge_declarations.py",
        "tests/unit/test_phase17_emperors_children_datasheet_overlay.py",
        "tests/unit/test_phase17g_chaos_daemons_blood_legion.py",
        "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py",
        "tests/unit/test_phase17n_runtime_rule_ir_oc_authority.py",
    }
)

OBSERVED_ADDITIONS |= frozenset(
    {
        "docs/ORDER_124_SCOPE_PLAN.md",
        "docs/SECTION24_CORE_ABILITIES_SCOPE.md",
        "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py",
        "src/warhammer40k_core/engine/catalog_shadow_form_runtime.py",
        "src/warhammer40k_core/engine/decision.py",
        "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
        "src/warhammer40k_core/engine/phases/charge.py",
        "tests/integration/test_catalog_rule_ir_runtime.py",
        "tests/integration/test_embarked_ability_authority.py",
        "tests/integration/test_fight_on_death_presence.py",
        "tests/integration/test_retained_shooting.py",
        "tests/phase15a_charge_declaration_helpers.py",
        "tests/psychic_modifier_helpers.py",
        "tests/replay/test_phase18b_replay_runner.py",
        "tests/rules/section07/coverage.json",
        "tests/rules/section18/coverage.json",
        "tests/rules/section20/coverage.json",
        "tests/rules/section22/coverage.json",
        "tests/rules/section24/README.md",
        "tests/rules/section24/coverage.json",
        "tests/rules/section24/test_inventory.py",
        "tests/shared/category_migration/phase17d_rule_execution.py",
        "tests/unit/test_dice.py",
        "tests/unit/test_phase11e_mission_scoring_cleanup.py",
        "tests/unit/test_phase15a_charge_declarations.py",
        "tests/unit/test_phase17_emperors_children_datasheet_overlay.py",
        "tests/unit/test_phase17g_chaos_daemons_blood_legion.py",
        "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py",
        "tests/unit/test_phase17n_runtime_rule_ir_oc_authority.py",
    }
)

CUTOVER_NEW |= frozenset(
    {
        "data/source_audits/ci64_provenance_v1/measurements/dice-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/dice-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/dice_sustained-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/dice_sustained-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/fight-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/fight-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/movement-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/movement-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/objective_control-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/objective_control-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/reconstruction-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/reconstruction-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/roster-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/roster-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/setup-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/setup-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/shock_reconstruction-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/shock_reconstruction-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/strength-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/strength-head.json",
        "data/source_audits/ci64_provenance_v1/measurements/visibility-base.json",
        "data/source_audits/ci64_provenance_v1/measurements/visibility-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/dice-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/dice-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/dice_sustained-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/dice_sustained-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/fight-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/fight-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/movement-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/movement-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/objective_control-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/objective_control-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/reconstruction-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/reconstruction-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/roster-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/roster-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/setup-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/setup-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/shock_reconstruction-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/shock_reconstruction-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/strength-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/strength-head.json",
        "data/source_audits/ci64_provenance_v1/receipts/visibility-base.json",
        "data/source_audits/ci64_provenance_v1/receipts/visibility-head.json",
        "docs/performance/current/ci64-external_contract_source_reuse.json",
        "docs/performance/current/ci78-current-dice.json",
        "docs/performance/current/ci78-current-dice_sustained.json",
        "docs/performance/current/ci78-current-fight.json",
        "docs/performance/current/ci78-current-movement.json",
        "docs/performance/current/ci78-current-objective_control.json",
        "docs/performance/current/ci78-current-reconstruction.json",
        "docs/performance/current/ci78-current-roster.json",
        "docs/performance/current/ci78-current-setup.json",
        "docs/performance/current/ci78-current-shock_reconstruction.json",
        "docs/performance/current/ci78-current-strength.json",
        "docs/performance/current/ci78-current-visibility.json",
    }
)

HISTORICAL_CURRENT_REPORTS: dict[str, str] = {
    "docs/performance/current/ci60-dice.json": (
        "6d8fd010383901ec4a853daac45aab84a79e4ee244b7057ffffc57696ec15e8e"
    ),
    "docs/performance/current/ci60-dice_sustained.json": (
        "a8bbdac5f0c49da74c6189d4440d896c326f4b30ae0fc82c8c3d7394a198ec95"
    ),
    "docs/performance/current/ci64-external_contract_source_reuse.json": (
        "95809d41d4f2b6e1704e3bedf4e2c36a390d3de2cd624a56a28735149093cf9f"
    ),
    "docs/performance/current/ci60-fight.json": (
        "70a746c1edffe86747ba18a69d750e6998d2367628d0abdfe56e96c44bfbcb37"
    ),
    "docs/performance/current/ci60-movement.json": (
        "3289f042642874383d108910e126989b17f54aac6e77466e9bf83ec175df5ef1"
    ),
    "docs/performance/current/qualification40-objective_control.json": (
        "9a3dbd260593b859c21e984b684945612a9ac7651dd25fe9b75c7611ef2db9ab"
    ),
    "docs/performance/current/ci60-reconstruction.json": (
        "4aaa1f15793a1240b40a627b0e7f56f4b58498be8c4b6a08f369602327ce4344"
    ),
    "docs/performance/current/qualification40-roster.json": (
        "400c84b7ac8833ca5251b45a79e440d61e5a15626cb6a4bb84dd6307741e46a9"
    ),
    "docs/performance/current/ci60-setup.json": (
        "20e5fe0386d04a57b9929dfb9e1d6ae08972bf7016ec28e715194638100aad65"
    ),
    "docs/performance/current/ci60-shock_reconstruction.json": (
        "e511bf0c7c52de4e37d3d1ce35fa15bb93dc9e425e76200ea5c5a5c0af5e3ba8"
    ),
    "docs/performance/current/ci60-strength.json": (
        "2ff96033f8859142838b8d131b89a01362cf5347f764085d54bb94b89d9e8b2f"
    ),
    "docs/performance/current/ci60-visibility.json": (
        "5253a0edab3afde964ae9257a3decfbee7a4199e05c2d6140acd09046e32309c"
    ),
}

CURRENT_SOURCE_REPORT = "docs/performance/current/ci78-current-external_contract_source_reuse.json"


def historical_current_report(
    base: str, path: str, change: dict[str, object], expected_base: str, previous: dict[str, str]
) -> bool:
    """Only exact old report bytes receive historical status, never current credit."""
    pins = previous | HISTORICAL_CURRENT_REPORTS
    return (
        base == expected_base
        and path in pins
        and change["before_sha256"] is None
        and change["after_sha256"] == pins[path]
    )


# Exact approved benchmark fixture input and three native historical preimages.
CUTOVER_NEW |= frozenset(
    {
        "tests/measurement_native_api.py",
        "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/order101_failed_setup_helpers.py.txt",
        "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/emergency_geometry_helpers.py.txt",
        "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/phase13b_shooting_declaration_helpers.py.txt",
    }
)
INPUT_ADDITIONS |= frozenset({"tests/measurement_native_api.py", "tests/rules/section24/README.md"})
CUTOVER_ADDED_INPUTS |= frozenset({"tests/measurement_native_api.py"})
OBSERVED_ADDITIONS |= frozenset(
    {
        "tests/measurement_native_api.py",
        "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/order101_failed_setup_helpers.py.txt",
        "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/emergency_geometry_helpers.py.txt",
        "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/phase13b_shooting_declaration_helpers.py.txt",
    }
)
