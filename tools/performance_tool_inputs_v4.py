"""Fresh source-overlay comparisons bound to finite reviewed exact-base scopes.

Historical v1/v2/v3 specifications and receipts remain separate. The role lists
are closed: every other selected byte must be identical between the two arms.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tools import performance_tool_inputs as original
from tools import performance_tool_inputs_v2 as previous

SCHEMA = "tool-input-roles-v4"
BASE = "bc9acd8419e7b97a2c1260c7e932d2cb9c3fc370"
SPEC_PATH = "docs/performance/policy-v3/vyper-source-input-roles-v4.json"
DRIVER = "scripts/measure_vyper_source_binding.py"
PACKAGE = "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
NEW_TREATMENT = frozenset(
    {
        PACKAGE + "aeldari_vyper_title_2026_10.py",
        PACKAGE + "aeldari_vyper_title_2026_10.overlay-pack.json",
        "tools/generate_vyper_source_overlay.py",
    }
)
TREATMENT = NEW_TREATMENT | {"tools/ability_support_sources.py", "tools/aeldari_support_report.py"}
DERIVED = previous.DERIVED | {
    "data/generated/ability_coverage/ability_coverage_rows.json",
    "data/generated/ability_coverage/ability_support_category_rows.json",
    "data/generated/ability_coverage/datasheet_support_rows.json",
}
CONTROL = frozenset(
    {
        SPEC_PATH,
        original.MAP_PATH,
        DRIVER,
        "tools/performance_tool_inputs.py",
        "tools/performance_tool_inputs_v4.py",
        "tools/performance_policy.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_performance_tool_inputs_v2.py",
        "tests/code_quality/test_current_comparison_routing.py",
        "tests/code_quality/test_phase14a_source_identity.py",
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_category_migration_preservation.py",
        "docs/performance/policy-v3/vyper-provenance-20261030/phase14a-predecessor.py.txt",
        "tests/code_quality/test_ws12_generated_data_artifacts.py",
        "tests/code_quality/test_generated_ability_support_artifacts.py",
        "tests/rules/section25/test_mfm.py",
        "data/source_audits/ci64_provenance_v1/test-cutover.json",
        "data/source_audits/supported_rules_2026_10/vyper-binding.json",
    }
)
HARNESS = frozenset(
    {
        DRIVER,
        "scripts/source_reuse_experiment.py",
        "scripts/ci_attribution_supervisor.py",
        "scripts/check_ci_attribution_supervisor.py",
        original.WORKLOAD,
        "tests/conftest.py",
        "tests/timing_plugin.py",
    }
)
REQUIRED = original.REQUIRED | (HARNESS - {DRIVER})


@dataclass(frozen=True, slots=True)
class ReviewedScope:
    base: str
    spec_path: str
    spec_raw_sha256: str
    spec_canonical_sha256: str
    report_path: str
    new_treatment: frozenset[str]
    treatment: frozenset[str]
    derived: frozenset[str]
    control: frozenset[str]
    required: frozenset[str]
    harness: frozenset[str]


EC_BASE = "105b467b1140e6d9ff6710a74ed839ad225d17ec"
EC_SPEC_PATH = "docs/performance/policy-v3/ec-profile-input-roles-v4.json"
EC_REPORT_PATH = "docs/performance/current/ec-profile-105b-v4.json"
ACTS_BASE = "2490faab2c41915c54eb26aed04902165fbfc042"
ACTS_SPEC_PATH = "docs/performance/policy-v3/acts-of-faith-input-roles-v4.json"
ACTS_REPORT_PATH = "docs/performance/current/acts-of-faith-2490-v4.json"
DEFILER_BASE = "c15bd1564bd62a7c1ba9069a5ee6bbc7a6b94ce8"
DEFILER_SPEC_PATH = "docs/performance/policy-v3/defiler-input-roles-v4.json"
DEFILER_REPORT_PATH = "docs/performance/current/defiler-c15-v4.json"
PR2_BASE = "2b640ffca912f72d74e3b08cec0c0c4b12ce776a"
PR2_SPEC_PATH = "docs/performance/policy-v3/pr2-player-boundary-input-roles-v4.json"
PR2_REPORT_PATH = "docs/performance/current/pr2-source-reuse-2b640-v4.json"
_SCOPES = (
    ReviewedScope(
        BASE,
        SPEC_PATH,
        "76d0e3bc6cd71c5205cabf30c990f16bf190632953d5fec2978ac660abb7c37f",
        "0df4b51388949aa86d8fd0cc4f0952e49341d80a6bd1c57754971209576fd258",
        "docs/performance/current/vyper-source-bc9-v4.json",
        NEW_TREATMENT,
        TREATMENT,
        DERIVED,
        CONTROL,
        REQUIRED,
        HARNESS,
    ),
    ReviewedScope(
        EC_BASE,
        EC_SPEC_PATH,
        "27a4bbd23a55f34672dcfb36767bb424b285d0ae65ad6ea08fb5c8e9f6484020",
        "9d656dd9200d0d692c9fe3bfd7b1f0ecacaa805e8dd5d610f93ad92a27c40e05",
        EC_REPORT_PATH,
        frozenset(
            [
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/emperors_children_profiles_2026_10.overlay-pack.json",
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/emperors_children_profiles_2026_10.py",
                "tools/generate_emperors_children_current_profiles.py",
            ]
        ),
        frozenset(
            [
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/emperors_children_profiles_2026_10.overlay-pack.json",
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/emperors_children_profiles_2026_10.py",
                "tools/ability_support_sources.py",
                "tools/generate_emperors_children_current_profiles.py",
            ]
        ),
        frozenset(
            [
                "contracts/examples/persistence/session-persistence.json",
                "contracts/examples/sessions/session-command-outcome.json",
                "contracts/examples/sessions/session-command-started.json",
                "contracts/examples/sessions/session-metadata-created.json",
                "contracts/examples/support-profile-player-a-redacted.json",
                "contracts/examples/support-profile-player-b-redacted.json",
                "contracts/examples/support-profile.json",
                "contracts/manifest.json",
                "src/warhammer40k_core/_engine_build_manifest.json",
            ]
        ),
        frozenset(
            [
                "data/source_audits/ci64_provenance_v1/test-cutover.json",
                "data/source_audits/supported_rules_2026_10/ec-profiles.json",
                "docs/performance/policy-v3/ec-profile-input-roles-v4.json",
                "docs/performance/policy-v3/ec-provenance-20261031/phase14a-predecessor.py.txt",
                "docs/performance/policy-v3/operation-map.json",
                "scripts/check_performance_policy.py",
                "scripts/measure_vyper_source_binding.py",
                "tests/category_migration_preservation.py",
                "tests/code_quality/test_category_migration_preservation.py",
                "tests/code_quality/test_current_comparison_routing.py",
                "tests/code_quality/test_performance_tool_inputs.py",
                "tests/code_quality/test_phase14a_source_identity.py",
                "tests/code_quality/test_registered_source_scopes.py",
                "tests/factions/aeldari/unit/test_battle_focus_consumers.py",
                "tests/factions/emperors_children/test_selected_consumers.py",
                "tests/factions/emperors_children/test_shared_attack_consumers.py",
                "tests/rules/section02/test_02_04_01_constructed_contract.py",
                "tests/rules/section02/test_02_04_weapons.py",
                "tests/rules/section05/coverage.json",
                "tests/rules/section05/test_rolls.py",
                "tests/rules/section05/test_toughness.py",
                "tests/rules/section18/coverage.json",
                "tests/rules/section18/test_emergency_status.py",
                "tests/support/section05_fixtures.py",
                "tools/performance_tool_inputs.py",
                "tools/performance_tool_inputs_v4.py",
                "tools/source_scope_provenance.py",
            ]
        ),
        REQUIRED,
        HARNESS,
    ),
    ReviewedScope(
        ACTS_BASE,
        ACTS_SPEC_PATH,
        "1321bb30199f34a0baff2ede6b58b543113e99fc1d59fb3f42e5547a1e2724ae",
        "0609643f0ac6d04f9ff8e9ea38d51baec2ef75d24f18c38f68f5b0dac4fa4d42",
        ACTS_REPORT_PATH,
        frozenset(
            [
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/turn_sequencing.py"
            ]
        ),
        frozenset(
            [
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/army_rule.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/destruction_sequencing.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/round_sequencing.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/turn_sequencing.py",
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_coverage_2026_27.py",
                "tools/generate_ability_support_matrix.py",
            ]
        ),
        frozenset(
            [
                "contracts/examples/persistence/session-persistence.json",
                "contracts/examples/sessions/session-command-outcome.json",
                "contracts/examples/sessions/session-command-started.json",
                "contracts/examples/sessions/session-metadata-created.json",
                "contracts/examples/support-profile-player-a-redacted.json",
                "contracts/examples/support-profile-player-b-redacted.json",
                "contracts/examples/support-profile.json",
                "contracts/manifest.json",
                "data/generated/ability_coverage/cross_source_semantic_equivalence.json",
                "data/generated/ability_coverage/runtime_content_semantic_coverage.json",
                "data/generated/ability_coverage/ability_coverage_rows.json",
                "data/generated/ability_coverage/ability_support_category_rows.json",
                "src/warhammer40k_core/_engine_build_manifest.json",
            ]
        ),
        frozenset(
            [
                ".gitattributes",
                "FACTION_INTEGRATION.md",
                "ci/quality_shards/all.txt",
                "ci/quality_shards/shard-1.txt",
                "ci/quality_shards/shard-4.txt",
                "data/source_audits/ci64_provenance_v1/test-cutover.json",
                "data/source_audits/supported_rules_2026_10/acts-of-faith-timing.json",
                "docs/performance/policy-v3/acts-of-faith-input-roles-v4.json",
                "docs/performance/policy-v3/acts-provenance-20261031/runtime-hook-predecessor.py.txt",
                "docs/performance/policy-v3/acts-provenance-20261031/source-scope-predecessor.py.txt",
                "docs/performance/policy-v3/operation-map.json",
                "tests/category_migration_preservation.py",
                "tests/code_quality/test_category_migration_preservation.py",
                "tests/code_quality/test_registered_source_scopes.py",
                "tests/infrastructure/runtime_hooks/unit/test_runtime_hook_bindings.py",
                "docs/performance/policy-v3/acts-provenance-20261031/runtime-consumer-predecessor.py.txt",
                "tests/shared/category_migration/reporting__test_runtime_consumer_evidence.py",
                "docs/performance/policy-v3/acts-provenance-20261031/inactive-acts-api-recipe.json",
                "docs/performance/policy-v3/acts-provenance-20261031/inactive-acts-predecessor.py.txt",
                "scripts/build_test_shards.py",
                "tests/unit/test_phase17g_adepta_sororitas_army_rule.py",
                "tests/support/acts_of_faith.py",
                "tests/support/acts_preservation.py",
                "tools/performance_tool_inputs_v4.py",
                "tools/source_scope_provenance.py",
            ]
        ),
        REQUIRED,
        HARNESS,
    ),
    ReviewedScope(
        DEFILER_BASE,
        DEFILER_SPEC_PATH,
        "e8ffff573fad9ae0e065061bf2de00cd1999fd1a77a3d80419709920cc596553",
        "faee397a17a5ae4ea1d536640334d49c75824ac73b487a2eb05b02a0609aa9de",
        DEFILER_REPORT_PATH,
        frozenset(),
        frozenset(
            [
                "src/warhammer40k_core/rules/wahapedia_bridge.py",
                "src/warhammer40k_core/rules/wahapedia_replacement_option_bridge.py",
                "tools/maulerfiend_cross_faction_support.py",
            ]
        ),
        frozenset(
            [
                "contracts/examples/persistence/session-persistence.json",
                "contracts/examples/sessions/session-command-outcome.json",
                "contracts/examples/sessions/session-command-started.json",
                "contracts/examples/sessions/session-metadata-created.json",
                "contracts/examples/support-profile-player-a-redacted.json",
                "contracts/examples/support-profile-player-b-redacted.json",
                "contracts/examples/support-profile.json",
                "contracts/manifest.json",
                "data/generated/ability_coverage/maulerfiend_cross_faction_support.json",
                "src/warhammer40k_core/_engine_build_manifest.json",
            ]
        ),
        frozenset(
            [
                "ci/quality_shards/all.txt",
                "ci/quality_shards/shard-1.txt",
                "ci/quality_shards/shard-4.txt",
                "data/source_audits/ci64_provenance_v1/test-cutover.json",
                "data/source_audits/supported_rules_2026_10/defiler-replacement.json",
                "docs/performance/policy-v3/defiler-input-roles-v4.json",
                "docs/performance/policy-v3/operation-map.json",
                "tests/category_migration_preservation.py",
                "tests/code_quality/test_category_migration_preservation.py",
                "tests/code_quality/test_registered_source_scopes.py",
                "tests/rules/section22/test_wargear.py",
                "tests/support/acts_preservation.py",
                "tools/performance_tool_inputs_v4.py",
                "tools/source_scope_provenance.py",
            ]
        ),
        REQUIRED,
        HARNESS,
    ),
    ReviewedScope(
        PR2_BASE,
        PR2_SPEC_PATH,
        "ac7c34a6e2c037a3be8dc67514c597ca962cfed0dc915b7841afa4b2fd26325f",
        "9f74633f8d7acfb529aac5c7e362d752be2c2cbdd22af0a4f8d446e69eb93496",
        PR2_REPORT_PATH,
        frozenset(
            [
                "contracts/compatibility/46.0.0-shape.json",
                "contracts/migrations/45-to-46.md",
                "src/warhammer40k_core/adapters/viewer_identity.py",
                "src/warhammer40k_core/ai/player_policy.py",
                "src/warhammer40k_core/ai/runner.py",
                "src/warhammer40k_core/engine/private_randomness.py",
                "tests/support/private_randomness.py",
            ]
        ),
        frozenset(
            [
                "contracts/README.md",
                "contracts/compatibility-policy.md",
                "contracts/compatibility/46.0.0-shape.json",
                "contracts/migrations/45-to-46.md",
                "contracts/openapi.yaml",
                "contracts/schemas/create-session.schema.json",
                "contracts/schemas/decision-request-view.schema.json",
                "contracts/schemas/event-delta.schema.json",
                "contracts/schemas/game-view.schema.json",
                "contracts/schemas/lifecycle-status.schema.json",
                "contracts/schemas/replay-metadata.schema.json",
                "contracts/schemas/session-command-envelope.schema.json",
                "contracts/schemas/session-command-outcome.schema.json",
                "contracts/schemas/session-command-result.schema.json",
                "contracts/schemas/session-create.schema.json",
                "contracts/schemas/session-metadata.schema.json",
                "contracts/schemas/session-persistence.schema.json",
                "contracts/schemas/session-projection.schema.json",
                "scripts/export_ui_contract_fixtures.py",
                "src/warhammer40k_core/adapters/checkpoint_reconstruction.py",
                "src/warhammer40k_core/adapters/command_protocol.py",
                "src/warhammer40k_core/adapters/contracts.py",
                "src/warhammer40k_core/adapters/decisions.py",
                "src/warhammer40k_core/adapters/event_stream.py",
                "src/warhammer40k_core/adapters/external_contract.py",
                "src/warhammer40k_core/adapters/headless.py",
                "src/warhammer40k_core/adapters/local_session.py",
                "src/warhammer40k_core/adapters/network.py",
                "src/warhammer40k_core/adapters/projection.py",
                "src/warhammer40k_core/adapters/redaction.py",
                "src/warhammer40k_core/adapters/server.py",
                "src/warhammer40k_core/adapters/server_commands.py",
                "src/warhammer40k_core/adapters/server_mutations.py",
                "src/warhammer40k_core/adapters/server_responses.py",
                "src/warhammer40k_core/adapters/server_sync.py",
                "src/warhammer40k_core/adapters/session_events.py",
                "src/warhammer40k_core/adapters/session_protocol.py",
                "src/warhammer40k_core/adapters/session_recovery.py",
                "src/warhammer40k_core/adapters/session_revision.py",
                "src/warhammer40k_core/adapters/setup_smoke.py",
                "src/warhammer40k_core/adapters/ui.py",
                "src/warhammer40k_core/adapters/viewer_identity.py",
                "src/warhammer40k_core/ai/player_policy.py",
                "src/warhammer40k_core/ai/runner.py",
                "src/warhammer40k_core/engine/attack_completion_triggers.py",
                "src/warhammer40k_core/engine/attack_sequence_damage_rerolls.py",
                "src/warhammer40k_core/engine/attack_sequence_destroyed_transport.py",
                "src/warhammer40k_core/engine/attack_sequence_dice_rerolls.py",
                "src/warhammer40k_core/engine/attack_sequence_dispatch.py",
                "src/warhammer40k_core/engine/attack_sequence_group_selection.py",
                "src/warhammer40k_core/engine/battle_shock_modifier_continuation.py",
                "src/warhammer40k_core/engine/battle_shock_outcome_triggers.py",
                "src/warhammer40k_core/engine/battle_shock_resolution.py",
                "src/warhammer40k_core/engine/battle_shock_resolution_authority.py",
                "src/warhammer40k_core/engine/catalog_command_point_test_evaluation.py",
                "src/warhammer40k_core/engine/catalog_command_restoration_runtime.py",
                "src/warhammer40k_core/engine/catalog_fall_back_denial_sequencing.py",
                "src/warhammer40k_core/engine/catalog_fight_end_triggered_movement_runtime.py",
                "src/warhammer40k_core/engine/catalog_poisoned_status_runtime.py",
                "src/warhammer40k_core/engine/catalog_selected_target_mortal_wounds.py",
                "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py",
                "src/warhammer40k_core/engine/charge_roll_flow.py",
                "src/warhammer40k_core/engine/charge_roll_reroll_requests.py",
                "src/warhammer40k_core/engine/command_battle_shock_history.py",
                "src/warhammer40k_core/engine/desperate_escape_mortal_wounds.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/adepta_sororitas/army_rule.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/aeldari/detachments/corsair_coterie/stratagems.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/aeldari/detachments/path_of_the_outcast/stratagems.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/chaos_daemons/datasheets.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/chaos_daemons/detachments/shadow_legion/enhancements.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/chaos_knights/army_rule.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/imperial_knights/army_rule.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/necrons/army_rule.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/thousand_sons/army_rule.py",
                "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/world_eaters/round_sequencing.py",
                "src/warhammer40k_core/engine/faction_resources.py",
                "src/warhammer40k_core/engine/fight_attack_completion.py",
                "src/warhammer40k_core/engine/fight_unit_selected_grant_resolution.py",
                "src/warhammer40k_core/engine/game_state.py",
                "src/warhammer40k_core/engine/game_state_payloads.py",
                "src/warhammer40k_core/engine/hazardous_completion.py",
                "src/warhammer40k_core/engine/lifecycle.py",
                "src/warhammer40k_core/engine/lifecycle_payload_consistency.py",
                "src/warhammer40k_core/engine/melee_weapon_commitment.py",
                "src/warhammer40k_core/engine/missions.py",
                "src/warhammer40k_core/engine/model_shooting_completion.py",
                "src/warhammer40k_core/engine/move_keyword_completion.py",
                "src/warhammer40k_core/engine/movement_phase_end_mortal_wounds.py",
                "src/warhammer40k_core/engine/phases/command.py",
                "src/warhammer40k_core/engine/phases/command_battle_shock_rerolls.py",
                "src/warhammer40k_core/engine/phases/fight_melee.py",
                "src/warhammer40k_core/engine/phases/movement_action_decisions.py",
                "src/warhammer40k_core/engine/phases/movement_completion_candidates.py",
                "src/warhammer40k_core/engine/phases/movement_options_dice.py",
                "src/warhammer40k_core/engine/phases/movement_rules_unit_disembark.py",
                "src/warhammer40k_core/engine/phases/shooting_declaration_validation.py",
                "src/warhammer40k_core/engine/phases/shooting_handler.py",
                "src/warhammer40k_core/engine/phases/shooting_reactions.py",
                "src/warhammer40k_core/engine/phases/shooting_surge_candidates.py",
                "src/warhammer40k_core/engine/private_randomness.py",
                "src/warhammer40k_core/engine/random_profile_evaluation.py",
                "src/warhammer40k_core/engine/random_weapon_range.py",
                "src/warhammer40k_core/engine/replay.py",
                "src/warhammer40k_core/engine/retained_destruction_attack.py",
                "src/warhammer40k_core/engine/retained_destruction_cleanup.py",
                "src/warhammer40k_core/engine/retained_destruction_rule.py",
                "src/warhammer40k_core/engine/return_on_death.py",
                "src/warhammer40k_core/engine/rule_model_destruction.py",
                "src/warhammer40k_core/engine/shooting_selection_completion.py",
                "src/warhammer40k_core/engine/stratagems_core_handlers.py",
                "src/warhammer40k_core/engine/stratagems_effect_handlers.py",
                "src/warhammer40k_core/engine/stratagems_generic_rule_ir.py",
                "src/warhammer40k_core/engine/stratagems_generic_rule_ir_runtime.py",
                "src/warhammer40k_core/engine/surge_authority.py",
                "src/warhammer40k_core/engine/surge_history.py",
                "src/warhammer40k_core/engine/transports.py",
                "src/warhammer40k_core/engine/triggered_movement_selection.py",
                "src/warhammer40k_core/engine/unit_move_completed_hooks.py",
                "src/warhammer40k_core/interfaces/cli.py",
                "tests/phase15a_charge_config_helpers.py",
                "tests/phase15a_charge_declaration_helpers.py",
                "tests/support/private_randomness.py",
            ]
        ),
        frozenset(
            [
                "contracts/examples/decisions/families/select_movement_action.json",
                "contracts/examples/decisions/families/select_movement_unit.json",
                "contracts/examples/decisions/families/select_secondary_missions.json",
                "contracts/examples/decisions/families/submit_movement_proposal.json",
                "contracts/examples/decisions/pending_movement_request.json",
                "contracts/examples/events/initial-player-a.json",
                "contracts/examples/events/initial-player-b.json",
                "contracts/examples/persistence/session-persistence.json",
                "contracts/examples/projections/attached_charge_view.json",
                "contracts/examples/projections/hidden_secondary_redaction_view.json",
                "contracts/examples/projections/initial_setup_view_player1.json",
                "contracts/examples/projections/initial_setup_view_player2.json",
                "contracts/examples/projections/post_deployment_view.json",
                "contracts/examples/projections/terrain_snapshot_hidden_reserve_view_player_a.json",
                "contracts/examples/projections/terrain_snapshot_hidden_reserve_view_player_b.json",
                "contracts/examples/projections/visible_modifier_datacard_view.json",
                "contracts/examples/replay-metadata.json",
                "contracts/examples/sessions/create-session.json",
                "contracts/examples/sessions/session-command-envelope.json",
                "contracts/examples/sessions/session-command-outcome.json",
                "contracts/examples/sessions/session-command-started.json",
                "contracts/examples/sessions/session-create.json",
                "contracts/examples/sessions/session-metadata-created.json",
                "contracts/examples/statuses/advanced.json",
                "contracts/examples/statuses/invalid.json",
                "contracts/examples/statuses/terminal.json",
                "contracts/examples/statuses/unsupported.json",
                "contracts/examples/statuses/waiting-for-decision.json",
                "contracts/examples/support-profile-player-a-redacted.json",
                "contracts/examples/support-profile-player-b-redacted.json",
                "contracts/examples/support-profile.json",
                "contracts/manifest.json",
                "src/warhammer40k_core/_engine_build_manifest.json",
            ]
        ),
        frozenset(
            [
                "ci/quality_shards/all.txt",
                "ci/quality_shards/shard-1.txt",
                "ci/quality_shards/shard-3.txt",
                "ci/quality_shards/shard-4.txt",
                "data/source_audits/ci64_provenance_v1/test-cutover.json",
                "data/source_audits/private_rng_fixture_preimages_v1.json",
                "docs/performance/policy-v3/operation-map.json",
                "docs/performance/policy-v3/pr2-player-boundary-input-roles-v4.json",
                "scripts/build_test_shards.py",
                "scripts/measure_player_boundary.py",
                "scripts/measure_private_rng_reconstruction.py",
                "scripts/measure_private_tactical_draw.py",
                "scripts/mock_event_layout_ui.py",
                "tests/action_battle_shock_helpers.py",
                "tests/category_migration_preservation.py",
                "tests/code_quality/test_adapter_decision_contract.py",
                "tests/code_quality/test_category_migration_preservation.py",
                "tests/code_quality/test_ci_performance_gates.py",
                "tests/code_quality/test_order84_dice_authority.py",
                "tests/code_quality/test_performance_policy.py",
                "tests/code_quality/test_performance_reconstruction_campaign.py",
                "tests/code_quality/test_phase18e_server_network_audit.py",
                "tests/code_quality/test_registered_source_scopes.py",
                "tests/code_quality/test_starfang_source_policy.py",
                "tests/conftest.py",
                "tests/core_stratagem_helpers.py",
                "tests/daemons_native_source_helpers.py",
                "tests/daemons_native_source_preservation.py",
                "tests/dice_result_semantics_helpers.py",
                "tests/disembark_eligibility_helpers.py",
                "tests/factions/aeldari/army_rule_helpers.py",
                "tests/factions/aeldari/lhykhis_helpers.py",
                "tests/factions/aeldari/mandiblasters_helpers.py",
                "tests/factions/aeldari/unit/test_battle_focus_consumers.py",
                "tests/factions/aeldari/unit/test_lhykhis.py",
                "tests/factions/aeldari/unit/test_mandiblasters.py",
                "tests/factions/aeldari/unit/test_unit_abilities.py",
                "tests/factions/chaos_daemons/integration/test_cavalcade_v995_roster.py",
                "tests/factions/chaos_daemons/integration/test_horror_split_materialization.py",
                "tests/factions/chaos_daemons/unit/test_chaos_daemons_army_rule.py",
                "tests/factions/death_guard/army_rule_helpers.py",
                "tests/factions/emperors_children/test_selected_consumers.py",
                "tests/factions/grey_knights/unit/test_grey_knights_army_rule.py",
                "tests/factions/leagues_of_votann/unit/test_leagues_of_votann_army_rule.py",
                "tests/factions/necrons/unit/test_necrons_army_rule.py",
                "tests/factions/orks/unit/test_orks_army_rule.py",
                "tests/factions/tau_empire/unit/test_tau_empire_army_rule.py",
                "tests/factions/tyranids/unit/test_tyranids_army_rule.py",
                "tests/factions/world_eaters/attack_helpers.py",
                "tests/factions/world_eaters/unit/test_blessings_gameplay.py",
                "tests/factions/world_eaters/unit/test_icon_gameplay.py",
                "tests/factions/world_eaters/unit/test_total_carnage_gameplay.py",
                "tests/factions/world_eaters/unit/test_world_eaters_army_rule.py",
                "tests/factions/world_eaters/world_eaters_helpers.py",
                "tests/infrastructure/adapters/unit/test_session_commands.py",
                "tests/infrastructure/decisions/unit/test_physical_proposal_prevalidation.py",
                "tests/infrastructure/lifecycle/unit/test_lifecycle.py",
                "tests/infrastructure/missions/unit/test_event_companion_part2.py",
                "tests/infrastructure/rule_execution/unit/test_rule_execution.py",
                "tests/order127_helpers.py",
                "tests/order57_destroyed_referent_helpers.py",
                "tests/order59_empty_dedicated_transport_helpers.py",
                "tests/order63_reserve_transport_helpers.py",
                "tests/order79_choice_helpers.py",
                "tests/phase10p_reserves_helpers.py",
                "tests/phase11c_command_phase_helpers.py",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
                "tests/phase17n_step5g_pairing_certification_helpers.py",
                "tests/rules/rules24/unit/test_return_on_death.py",
                "tests/rules/section01/test_01_05_choice.py",
                "tests/rules/section04/test_completion_boundaries.py",
                "tests/rules/section09/coverage.json",
                "tests/rules/section09/test_distances.py",
                "tests/rules/section09/test_fall_back.py",
                "tests/rules/section09/test_focused_checkpoint.py",
                "tests/rules/section11/coverage.json",
                "tests/rules/section11/test_selection.py",
                "tests/rules/section15/coverage.json",
                "tests/rules/section15/test_mortals.py",
                "tests/rules/section15/test_reactions.py",
                "tests/rules/section15/test_reroll.py",
                "tests/rules/section15/test_snap_faqs.py",
                "tests/rules/section18/coverage.json",
                "tests/rules/section18/test_emergency_status.py",
                "tests/rules/section18/test_facade.py",
                "tests/rules/section21/coverage.json",
                "tests/rules/section21/test_boundaries.py",
                "tests/rules/section22/coverage.json",
                "tests/rules/section22/test_damage.py",
                "tests/rules/section24/test_damaged.py",
                "tests/rules/section25/coverage.json",
                "tests/rules/section25/test_facade.py",
                "tests/shared/category_migration/generic_rule_ability_registry.py",
                "tests/shared/category_migration/horror_split_materialization.py",
                "tests/shared/category_migration/phase10d_battlefield_transitions.py",
                "tests/shared/category_migration/phase11a_mission_pack.py",
                "tests/shared/category_migration/phase11e_mission_scoring_cleanup_configuration.py",
                "tests/shared/category_migration/phase11f_game_end_scoring.py",
                "tests/shared/category_migration/phase16a_deployment.py",
                "tests/shared/category_migration/phase16b_prebattle.py",
                "tests/shared/category_migration/phase16e_setup_completion.py",
                "tests/shared/category_migration/phase17d_rule_execution.py",
                "tests/shared/category_migration/phase17g_black_templars_army_rule.py",
                "tests/shared/category_migration/phase17g_runtime_content.py",
                "tests/shared/category_migration/phase17n_primary_scoring_grammar.py",
                "tests/shared/category_migration/phase17n_primary_scoring_spatial_evidence.py",
                "tests/shared/category_migration/phase18f_session_commands.py",
                "tests/shared/category_migration/phase18l_session_persistence.py",
                "tests/shared/category_migration/phase9b_lifecycle.py",
                "tests/shared/category_migration/primary_boundary_scoring_builders.py",
                "tests/shared/category_migration/primary_boundary_state_and_geometry.py",
                "tests/shared/category_migration/return_on_death.py",
                "tests/shared/category_migration/tracked_targets.py",
                "tests/shared/category_migration/ws14_generic_ir_lifecycle_court.py",
                "tests/shared/category_migration/ws14_generic_ir_lifecycle_more_dakka.py",
                "tests/shared/category_migration/ws14_generic_ir_lifecycle_spectacle.py",
                "tests/support/a32_transport.py",
                "tests/support/battle_shock_batch04.py",
                "tests/support/catalog_runtime_fixtures.py",
                "tests/support/faction_batch01.py",
                "tests/support/faction_layout_preservation.py",
                "tests/support/fight_phase_reconstruction.py",
                "tests/support/fixtures/player_boundary_config.json",
                "tests/support/fixtures/private_rng_reconstruction_config.json",
                "tests/rules/section07/coverage.json",
                "tests/support/private_rng_fixture_preservation.py",
                "tests/support/section02_fixtures.py",
                "tests/support/section03_session.py",
                "tests/support/section05_rule_effect_retention.py",
                "tests/support/section08_fixtures.py",
                "tests/support/section11_fixtures.py",
                "tests/support/section12_fixtures.py",
                "tests/support/section15_fixtures.py",
                "tests/support/sorcerer_native.py",
                "tests/support/viewer_identity_fixtures.py",
                "tests/unit/test_phase11e_mission_scoring_cleanup.py",
                "tools/performance_policy.py",
                "tools/performance_private_randomness.py",
                "tools/performance_tool_inputs_v4.py",
                "tools/source_scope_provenance.py",
            ]
        ),
        REQUIRED,
        HARNESS,
    ),
)


def registered_scope(base: str = BASE) -> ReviewedScope:
    matches = [scope for scope in _SCOPES if scope.base == base]
    if len(matches) != 1:
        raise ValueError("V4 requires an exact PR600 or registered reviewed base.")
    return matches[0]


def scope_for_specification(path: str) -> ReviewedScope:
    matches = [scope for scope in _SCOPES if scope.spec_path == path]
    if len(matches) != 1:
        raise ValueError("Unknown v4 reviewed role specification.")
    return matches[0]


def registered_declarations() -> tuple[dict[str, str], ...]:
    return tuple({"schema": SCHEMA, "role_specification": scope.spec_path} for scope in _SCOPES)


def validate_scope_binding(base: str, binding: dict[str, object]) -> ReviewedScope:
    scope = registered_scope(base)
    if (
        binding.get("schema") != SCHEMA
        or binding.get("role_spec_sha256") != scope.spec_canonical_sha256
    ):
        raise ValueError("V4 report does not bind the exact registered scope.")
    return scope


def selected(path: str, *, scope_base: str = BASE) -> bool:
    """Complete code, source-data, schema and copied-output input boundaries.

    Current reports live only under docs/performance/current; neither reports nor
    the assessment recursively hash themselves. The fixed role spec is included.
    """
    scope = registered_scope(scope_base)
    return (
        path.startswith(("src/", "tests/", "scripts/", "tools/", "contracts/", "schemas/", "data/"))
        or path in scope.required | scope.control
    )


def validate_spec(spec: dict[str, object], *, scope_base: str = BASE) -> None:
    scope = registered_scope(scope_base)
    if spec.keys() != {
        "schema",
        "family",
        "workload",
        "base",
        "treatment",
        "derived_outputs",
        "control_plane",
        "required_dependencies",
        "harness",
    } or (spec["schema"], spec["family"], spec["workload"], spec["base"]) != (
        SCHEMA,
        original.FAMILY,
        original.WORKLOAD,
        scope.base,
    ):
        raise ValueError("Unsupported v4 exact-base role specification.")
    control = original.input_object(spec["control_plane"])
    original.input_paths(list(control))
    if (
        frozenset(original.input_paths(spec["treatment"])) != scope.treatment
        or frozenset(original.input_paths(spec["derived_outputs"])) != scope.derived
        or control.keys() != scope.control
        or frozenset(original.input_paths(spec["required_dependencies"])) != scope.required
        or frozenset(original.input_paths(spec["harness"])) != scope.harness
    ):
        raise ValueError("V4 roles differ from the exact reviewed workload scope.")
    if scope.treatment & (scope.derived | scope.control) or scope.derived & scope.control:
        raise ValueError("Overlapping v4 roles.")
    if any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in control.values()):
        raise ValueError("Every v4 control requires an explicit workload-role reason.")

    if original.digest(spec) != scope.spec_canonical_sha256:
        raise ValueError("V4 specification differs from its registered canonical digest.")


def read_role_spec(root: Path, *, scope_base: str = BASE) -> dict[str, object]:
    scope = registered_scope(scope_base)
    path = root / scope.spec_path
    if path.is_symlink() or not path.is_file():
        raise ValueError("V4 specification must be a regular reviewed file.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != scope.spec_raw_sha256:
        raise ValueError("V4 specification raw bytes differ from its reviewed registration.")
    spec = original.input_object(json.loads(raw, object_pairs_hook=original.unique_input_object))
    validate_spec(spec, scope_base=scope.base)
    return spec


def classify_inputs(
    *,
    spec: dict[str, object],
    base: dict[str, str],
    head: dict[str, str],
    base_revision: str,
    head_revision: str,
    head_input_digest: str,
    harness_base: dict[str, str],
    harness_head: dict[str, str],
) -> dict[str, object]:
    scope = registered_scope(base_revision)
    validate_spec(spec, scope_base=scope.base)
    for identity, length in ((base_revision, 40), (head_revision, 40), (head_input_digest, 64)):
        if len(identity) != length or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Missing actual v4 revision/input digest.")
    if base_revision != scope.base or head_revision == scope.base:
        raise ValueError("V4 requires the exact PR600 base and a fresh head.")
    for inventory in (base, head, harness_base, harness_head):
        original.input_paths(list(inventory))
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in inventory.values()
        ):
            raise ValueError("V4 inputs require complete raw-byte SHA256 identities.")
    if (
        not base.keys() >= scope.required | scope.derived | (scope.treatment - scope.new_treatment)
        or base.keys() & scope.new_treatment
    ):
        raise ValueError("V4 base source/dependency presence differs from the reviewed base.")
    if not head.keys() >= scope.required | scope.treatment | scope.derived | scope.control:
        raise ValueError("V4 head lacks required source/dependency inputs.")
    common_base = {
        p: v for p, v in base.items() if p not in scope.treatment | scope.derived | scope.control
    }
    common_head = {
        p: v for p, v in head.items() if p not in scope.treatment | scope.derived | scope.control
    }
    if common_base != common_head:
        raise ValueError("True common source/fixture/workload/dependency inputs changed.")
    if (
        harness_base.keys() != scope.harness
        or harness_base != harness_head
        or harness_head != {p: head[p] for p in scope.harness}
    ):
        raise ValueError("V4 requires the same independently bound harness on both arms.")
    sides: dict[str, object] = {}
    for name, inventory, revision in (("base", base, base_revision), ("head", head, head_revision)):
        sides[name] = {
            "revision": revision,
            "inventory": inventory,
            "inventory_sha256": original.digest(inventory),
            "implementation": {p: inventory.get(p) for p in sorted(scope.treatment)},
            "derived_outputs": {p: inventory[p] for p in sorted(scope.derived)},
            "control_plane": {p: inventory.get(p) for p in sorted(scope.control)},
        }
    return {
        "schema": SCHEMA,
        "family": original.FAMILY,
        "role_spec_sha256": original.digest(spec),
        "head_input_digest": head_input_digest,
        "common": common_head,
        "common_sha256": original.digest(common_head),
        "sides": sides,
        "harness": {
            "base": harness_base,
            "head": harness_head,
            "sha256": original.digest(harness_head),
        },
    }


def git_inventory(
    root: Path, revision: str, *, scope_base: str = BASE
) -> tuple[dict[str, str], dict[str, str]]:
    """Hash independently fetched Git blobs in bounded batches, without checkout."""
    git = ["git", "-c", f"safe.directory={root.as_posix()}"]
    entries = subprocess.check_output([*git, "ls-tree", "-r", "-z", revision], cwd=root)
    objects: dict[str, str] = {}
    for row in entries.decode().split("\0"):
        if row:
            metadata, path = row.split("\t", 1)
            mode, kind, oid = metadata.split()
            if selected(path, scope_base=scope_base):
                if kind != "blob" or mode not in {"100644", "100755"}:
                    raise ValueError("V4 inputs must be regular Git blobs.")
                objects[path] = oid
    inventory: dict[str, str] = {}
    paths = sorted(objects)
    for offset in range(0, len(paths), 32):
        batch = paths[offset : offset + 32]
        payload = subprocess.check_output(
            [*git, "cat-file", "--batch"],
            input="".join(objects[p] + "\n" for p in batch).encode(),
            cwd=root,
        )
        cursor = 0
        for path in batch:
            boundary = payload.index(b"\n", cursor)
            oid, kind, length = payload[cursor:boundary].decode().split()
            start, end = boundary + 1, boundary + 1 + int(length)
            if oid != objects[path] or kind != "blob" or payload[end : end + 1] != b"\n":
                raise ValueError("V4 Git input identity or framing drifted.")
            inventory[path] = hashlib.sha256(payload[start:end]).hexdigest()
            cursor = end + 1
        if cursor != len(payload):
            raise ValueError("Unexpected trailing v4 Git input bytes.")
    return inventory, objects


def current_inventory(
    root: Path, *, scope_base: str = BASE
) -> tuple[dict[str, str], dict[str, str]]:
    names = set(
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    ) - {""}
    # Both the runtime source scanner and the copied output tree see ignored files.
    names.update(
        p.relative_to(root).as_posix()
        for p in (root / "src").rglob("*")
        if p.is_file()
        and (p.suffix in {".py", ".json"} or p.name == "py.typed")
        and not {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}.intersection(
            p.relative_to(root / "src").parts
        )
    )
    for directory in ("contracts", "data", "schemas"):
        names.update(
            p.relative_to(root).as_posix() for p in (root / directory).rglob("*") if p.is_file()
        )
    inventory: dict[str, str] = {}
    blobs: dict[str, str] = {}
    for name in sorted(names):
        if selected(name, scope_base=scope_base):
            path = root / name
            if path.is_symlink():
                raise ValueError("V4 current inputs must be regular files.")
            if path.is_file():
                content = path.read_bytes()
                inventory[name] = hashlib.sha256(content).hexdigest()
                blobs[name] = hashlib.sha1(
                    f"blob {len(content)}\0".encode() + content, usedforsecurity=False
                ).hexdigest()
    return inventory, blobs


def comparison_inputs(
    root: Path, *, base: str, head_input_digest: str, measured_head: str | None
) -> dict[str, object]:
    scope = registered_scope(base)
    # Preserve original entry signatures for the historical scope and its controls.
    options = {} if base == BASE else {"scope_base": base}
    spec = read_role_spec(root, **options)
    before, _ = git_inventory(root, base, **options)
    after, blobs = current_inventory(root, **options)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    if measured_head is not None:
        if len(measured_head) != 40 or any(c not in "0123456789abcdef" for c in measured_head):
            raise ValueError("Invalid v4 measured revision selector.")
        # Squash-merged main may not descend from the measured branch commit.
        # The retained Git object is a locator; independently equal bytes admit it.
        _, measured_blobs = git_inventory(root, measured_head, **options)
        if measured_blobs != blobs:
            raise ValueError("V4 measured head bytes differ from the current source inventory.")
        revision = measured_head
    harness = {p: after[p] for p in scope.harness}
    return classify_inputs(
        spec=spec,
        base=before,
        head=after,
        base_revision=base,
        head_revision=revision,
        head_input_digest=head_input_digest,
        harness_base=harness,
        harness_head=harness,
    )


def validate_generated_evidence(observed: object, binding: dict[str, object]) -> None:
    records = original.input_object(observed)
    if records.keys() != {"base", "head"} or binding.get("schema") != SCHEMA:
        raise ValueError("Missing v4 generated-output parity evidence.")
    sides = original.input_object(binding["sides"])
    for side in ("base", "head"):
        inventory = original.input_object(original.input_object(sides[side])["inventory"])
        expected = {
            p.removeprefix("contracts/"): value
            for p, value in inventory.items()
            if p.startswith("contracts/")
        }
        if not expected or records[side] != [expected, expected, expected]:
            raise ValueError("V4 requires all three complete exact generated trees per arm.")
