from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.code_quality.source_index import combined_source_for, python_files, source_for
from warhammer40k_core.core.ruleset_descriptor import (
    CoherencyPolicyKind,
    CoverEffect,
    ReserveDestructionTimingKind,
    RulesetDescriptor,
)
from warhammer40k_core.engine import lifecycle as lifecycle_module
from warhammer40k_core.engine.attack_sequence_decision_family import (
    ATTACK_SEQUENCE_ACTIVE_CONTINUATION_DECISION_TYPES,
    ATTACK_SEQUENCE_AUTHORITY_BOUND_DECISION_TYPES,
    ATTACK_SEQUENCE_CONTEXT_BOUND_DECISION_TYPES,
    ATTACK_SEQUENCE_DECISION_TYPES,
)
from warhammer40k_core.engine.reserves import StrategicReserveRule
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_stratagems import (
    core_stratagem_rows,
)

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
ATTACK_SEQUENCE_PATH = SRC_ROOT / "engine" / "attack_sequence.py"
DAMAGE_ALLOCATION_PATH = SRC_ROOT / "engine" / "damage_allocation.py"
DECISION_PATH = SRC_ROOT / "engine" / "decision.py"
DIRECT_MORTAL_WOUND_PATH = SRC_ROOT / "engine" / "direct_mortal_wound_application.py"
MORTAL_WOUND_MODEL_ALLOCATION_PATH = SRC_ROOT / "engine" / "mortal_wound_model_allocation.py"
MORTAL_WOUND_TARGET_LINEAGE_PATH = SRC_ROOT / "engine" / "mortal_wound_target_lineage.py"
MORTAL_WOUND_DESTRUCTION_EVIDENCE_PATH = (
    SRC_ROOT / "engine" / "mortal_wound_destruction_evidence.py"
)
MODEL_DESTRUCTION_COMPLETION_RESTORE_PATH = (
    SRC_ROOT / "engine" / "model_destruction_cause_completion_restore.py"
)
SHOOTING_PHASE_PATH = SRC_ROOT / "engine" / "phases" / "shooting.py"
SHOOTING_PHASE_SPLIT_PATHS = tuple(sorted(SHOOTING_PHASE_PATH.parent.glob("shooting*.py")))
LIFECYCLE_PATH = SRC_ROOT / "engine" / "lifecycle.py"
RESERVES_PATH = SRC_ROOT / "engine" / "reserves.py"
CORE_STRATAGEMS_PATH = (
    SRC_ROOT / "rules" / "source_packages" / "warhammer_40000_11th" / "core_stratagems.py"
)
CORE_STRATAGEM_APP_SOURCE_PATH = (
    SRC_ROOT
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "core_stratagems_2026_08"
    / "artifacts"
    / "package.json"
)
ADAPTER_CONTRACT_PATH = ROOT / "docs" / "ADAPTER_DECISION_CONTRACT.md"
ARCHITECTURE_PATH = ROOT / "ARCHITECTURE_V2.md"
README_PATH = ROOT / "README.md"


def test_phase14k_retired_attack_save_choice_surfaces_absent_from_runtime() -> None:
    retired_tokens = (
        "select_" + "saving_throw_kind",
        "SELECT_" + "SAVING_THROW_KIND_DECISION_TYPE",
        "SavingThrowKindDecision",
        "build_" + "saving_throw_kind_request",
        "select_" + "attack_allocation",
        "SELECT_" + "ATTACK_ALLOCATION_DECISION_TYPE",
        "AttackAllocationDecision",
        "build_" + "attack_allocation_request",
    )
    violations: list[str] = []

    for path in _runtime_python_files():
        text = source_for(path)
        relative_path = path.relative_to(ROOT).as_posix()
        for token in retired_tokens:
            if token in text:
                violations.append(f"{relative_path}: contains {token!r}")

    assert not violations, (
        "Phase 14K rejects retired attack save/allocation decision surfaces:\n"
        + "\n".join(violations)
    )


def test_phase14k_damage_allocation_model_choice_is_runtime_and_contract_registered() -> None:
    runtime_expectations = (
        (DAMAGE_ALLOCATION_PATH, "SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE"),
        (DAMAGE_ALLOCATION_PATH, "DamageAllocationModelDecision"),
        (DAMAGE_ALLOCATION_PATH, "build_damage_allocation_model_request"),
        (ATTACK_SEQUENCE_PATH, "apply_damage_allocation_model_decision"),
        (ATTACK_SEQUENCE_PATH, "_legal_model_ids_for_allocation_group_damage"),
        (ATTACK_SEQUENCE_PATH, "current_legal_damage_allocation_model_ids"),
        (SHOOTING_PHASE_PATH, "apply_damage_allocation_model_decision"),
        (LIFECYCLE_PATH, "SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE"),
        (LIFECYCLE_PATH, "_invalid_damage_allocation_model_status"),
        (LIFECYCLE_PATH, "current_legal_damage_allocation_model_ids"),
    )
    missing: list[str] = []

    for path, token in runtime_expectations:
        if token not in _source_for_path(path):
            missing.append(f"{path.relative_to(ROOT).as_posix()}: missing {token!r}")

    contract_text = source_for(ADAPTER_CONTRACT_PATH)
    if "select_damage_allocation_model" not in contract_text:
        missing.append("docs/ADAPTER_DECISION_CONTRACT.md: missing damage model decision")

    assert not missing, (
        "Phase 14K damage model allocation choice must be registered in runtime "
        "and the adapter contract:\n" + "\n".join(missing)
    )


def test_p06b_mortal_wound_model_ties_cannot_use_sorted_first_fallback() -> None:
    damage_source = source_for(DAMAGE_ALLOCATION_PATH)
    mortal_wound_model_source = source_for(MORTAL_WOUND_MODEL_ALLOCATION_PATH)
    direct_source = source_for(DIRECT_MORTAL_WOUND_PATH)
    lifecycle_source = source_for(LIFECYCLE_PATH)
    contract_source = source_for(ADAPTER_CONTRACT_PATH)

    assert "SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE" in mortal_wound_model_source
    assert "MortalWoundAllocationPriority" in mortal_wound_model_source
    assert "build_mortal_wound_model_request" in mortal_wound_model_source
    assert "if len(legal_model_ids) > 1:" in mortal_wound_model_source
    assert "continue_mortal_wound_application as _continue_mortal_wound_application" in (
        damage_source
    )
    assert "Mortal wound model choices require lifecycle routing." in direct_source
    assert direct_source.index("if len(legal_model_ids) > 1:") < direct_source.index(
        "model_id = next(iter(legal_model_ids))"
    )
    assert "invalid_mortal_wound_model_status" in mortal_wound_model_source
    assert "_mw_model.invalid_mortal_wound_model_status" in lifecycle_source
    assert "select_mortal_wound_model" in contract_source
    assert "tuple(sorted(alive_model_ids))[0]" not in mortal_wound_model_source
    assert "tuple(sorted(alive_model_ids))[0]" not in direct_source


def test_p06b_in_flight_mortal_wounds_preserve_split_target_lineage() -> None:
    allocation_source = source_for(MORTAL_WOUND_MODEL_ALLOCATION_PATH)
    lineage_source = source_for(MORTAL_WOUND_TARGET_LINEAGE_PATH)
    damage_source = source_for(DAMAGE_ALLOCATION_PATH)
    destruction_source = source_for(MORTAL_WOUND_DESTRUCTION_EVIDENCE_PATH)
    restore_source = source_for(MODEL_DESTRUCTION_COMPLETION_RESTORE_PATH)
    decision_source = source_for(DECISION_PATH)

    assert "current_placed_alive_rules_unit_view_for_identity" not in allocation_source
    assert "_progress_with_target_lineage" in allocation_source
    assert "target_lineage=lineage" in allocation_source
    assert "FROZEN_RULES_UNIT_COMPONENTS_POLICY" in lineage_source
    assert "current_rules_unit_views_for_canonical_identity" in lineage_source
    assert "target_lineage.assert_contains_model" in damage_source
    assert "logical_death.rules_unit_instance_id" in destruction_source
    assert "record.physical_unit_instance_id" in restore_source
    assert "target_lineage.component_unit_instance_ids" in restore_source
    assert '"target_lineage",' in decision_source


def test_p06b_shared_attack_sequence_phase_ownership_cannot_drift() -> None:
    def decision_types(name: str) -> frozenset[str]:
        value = cast(object, getattr(lifecycle_module, name))
        assert type(value) is frozenset
        items = cast(frozenset[object], value)
        assert all(type(item) is str for item in items)
        return cast(frozenset[str], items)

    shooting_types = decision_types("_SHOOTING_DECISION_TYPES")
    fight_types = decision_types("_FIGHT_DECISION_TYPES")
    assert shooting_types >= ATTACK_SEQUENCE_DECISION_TYPES
    assert fight_types >= ATTACK_SEQUENCE_DECISION_TYPES
    assert ATTACK_SEQUENCE_DECISION_TYPES == (
        ATTACK_SEQUENCE_CONTEXT_BOUND_DECISION_TYPES
        | ATTACK_SEQUENCE_ACTIVE_CONTINUATION_DECISION_TYPES
        | ATTACK_SEQUENCE_AUTHORITY_BOUND_DECISION_TYPES
    )


def test_phase14k_retired_aircraft_minimum_move_policy_absent_from_runtime_and_docs() -> None:
    retired_tokens = (
        "Aircraft" + "MinimumMoveResult",
        "AircraftBase" + "MovementWitness",
        "validate_normal_move_witness_with_minimum_result",
        "minimum_" + "move_inches",
        "maximum_" + "pivot_degrees",
        "MINIMUM_" + "MOVE_UNAVAILABLE",
        "aircraft_" + "minimum_move_required",
        "aircraft_" + "forward_move_required",
        "aircraft_" + "pivot_limit_exceeded",
        "aircraft_" + "pivot_before_move",
        "aircraft_" + "multiple_pivots",
        "aircraft_" + "translation_after_pivot",
        "aircraft_" + "pivot_during_translation",
    )
    violations: list[str] = []

    for path in (*_runtime_python_files(), ARCHITECTURE_PATH, README_PATH):
        text = source_for(path)
        relative_path = path.relative_to(ROOT).as_posix()
        for token in retired_tokens:
            if token in text:
                violations.append(f"{relative_path}: contains {token!r}")

    assert not violations, (
        "Phase 14K removes the retired aircraft minimum-move and pivot-limit policy:\n"
        + "\n".join(violations)
    )


def test_phase14k_reserve_arrivals_use_move_units_and_eight_inch_enemy_distance() -> None:
    assert StrategicReserveRule().enemy_horizontal_distance_inches == 8.0

    source = source_for(RESERVES_PATH)
    forbidden_tokens = (
        'source_step="' + "reinforcements" + '"',
        "enemy_horizontal_distance_inches: float = 9.0",
        "else 9.0",
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert not violations, (
        "Phase 14K reserve arrivals must use Move Units and the 11th Edition "
        "more-than-8 enemy-distance policy:\n" + "\n".join(violations)
    )
    assert 'source_step="' + "move_units" + '"' in source


def test_phase14k_ruleset_descriptor_uses_11th_only_shared_primitives() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    assert descriptor.engagement_policy.horizontal_inches == 2.0
    assert descriptor.engagement_policy.vertical_inches == 5.0

    coherency_policy = descriptor.coherency_policy
    assert coherency_policy.policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT
    assert coherency_policy.required_neighbors_small_unit == 1
    assert coherency_policy.required_neighbors_large_unit is None
    assert coherency_policy.large_unit_model_count_threshold is None
    assert coherency_policy.max_horizontal_inches == 2.0
    assert coherency_policy.max_vertical_inches == 5.0
    assert coherency_policy.max_all_models_distance_inches is None
    assert coherency_policy.max_unit_span_inches == 9.0

    terrain_visibility_policy = descriptor.terrain_visibility_policy
    assert terrain_visibility_policy.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER
    assert terrain_visibility_policy.cover_policy.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER
    for feature_policy in terrain_visibility_policy.feature_policies:
        assert feature_policy.cover_policy.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER

    core_mission_policy = descriptor.mission_policy
    assert (
        core_mission_policy.reserve_destruction_timing is ReserveDestructionTimingKind.END_OF_BATTLE
    )
    assert core_mission_policy.reserve_destruction_battle_round is None

    chapter_approved = RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27()
    assert (
        chapter_approved.mission_policy.reserve_destruction_timing
        is ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N
    )
    assert chapter_approved.mission_policy.reserve_destruction_battle_round == 3


def test_phase14k_core_stratagem_source_package_uses_current_names() -> None:
    expected_core_names = {
        "Command Re-roll",
        "Counteroffensive",
        "Epic Challenge",
        "Fire Overwatch",
        "Explosives",
        "Heroic Intervention",
        "Insane Bravery",
        "Rapid Ingress",
        "New Orders",
        "Smokescreen",
        "Crushing Impact",
    }
    rows = core_stratagem_rows()
    names = {row.name for row in rows}

    assert names == expected_core_names
    assert {"Counter-offensive", "Grenade", "Tank Shock", "Go to Ground"}.isdisjoint(names)

    rapid_ingress = next(row for row in rows if row.stratagem_id == "rapid-ingress")
    assert "reinforcements step" not in rapid_ingress.effect_descriptor.lower()

    rows_by_id = {row.stratagem_id: row for row in rows}
    crushing_impact = rows_by_id["crushing-impact"]
    assert crushing_impact.source_id == "gw-11e-core-stratagems:core:crushing-impact"
    assert (
        crushing_impact.trigger_kind,
        crushing_impact.phase,
        crushing_impact.target_kind,
        crushing_impact.enumerable,
        crushing_impact.target_policy_id,
        crushing_impact.handler_id,
    ) == (
        "after_unit_ends_charge_move",
        "charge",
        "friendly_unit",
        False,
        "crushing_impact_unit",
        "core:crushing-impact",
    )
    assert "MONSTER/VEHICLE" in crushing_impact.target_descriptor
    assert "T characteristic" in crushing_impact.effect_descriptor
    assert "strength" not in crushing_impact.effect_descriptor.lower()

    explosives = rows_by_id["explosives"]
    assert (
        explosives.source_id,
        explosives.trigger_kind,
        explosives.phase,
        explosives.target_kind,
        explosives.enumerable,
        explosives.target_policy_id,
        explosives.handler_id,
    ) == (
        "gw-11e-core-stratagems:core:explosives",
        "start_phase",
        "shooting",
        "friendly_unit",
        False,
        "explosives_unit_and_enemy_target",
        "core:explosives",
    )

    rapid_ingress = rows_by_id["rapid-ingress"]
    assert (
        rapid_ingress.source_id,
        rapid_ingress.trigger_kind,
        rapid_ingress.phase,
        rapid_ingress.target_kind,
        rapid_ingress.enumerable,
        rapid_ingress.target_policy_id,
        rapid_ingress.handler_id,
    ) == (
        "gw-11e-core-stratagems:core:rapid-ingress",
        "end_phase",
        "movement",
        "friendly_unit",
        False,
        "reserves_unit",
        "core:rapid-ingress",
    )

    fire_overwatch = rows_by_id["fire-overwatch"]
    assert fire_overwatch.source_id == "gw-11e-core-stratagems:core:fire-overwatch"
    assert (
        fire_overwatch.trigger_kind,
        fire_overwatch.phase,
        fire_overwatch.target_kind,
        fire_overwatch.enumerable,
        fire_overwatch.target_policy_id,
        fire_overwatch.handler_id,
    ) == (
        "end_phase",
        "movement",
        "friendly_unit",
        False,
        "out_of_phase_shooting_unit",
        "core:fire-overwatch",
    )
    assert "unengaged" in fire_overwatch.target_descriptor
    assert "TITANIC" in fire_overwatch.target_descriptor
    assert "Snap Shooting" in fire_overwatch.effect_descriptor

    source = source_for(CORE_STRATAGEMS_PATH)
    current_source_artifact = source_for(CORE_STRATAGEM_APP_SOURCE_PATH)
    assert "Counter-offensive" not in source
    assert "stratagem_id=" + '"grenade"' not in source
    assert "stratagem_id=" + '"tank-shock"' not in source
    assert "stratagem_id=" + '"go-to-ground"' not in source
    assert "one vehicle unit from the player's army" not in source
    assert "roll dice based on strength" not in source
    assert "one eligible unit from the player's army that can shoot" not in source
    assert "shoots as if it were the shooting phase" not in source
    assert "roll dice based on strength" not in current_source_artifact


def test_phase14k_docs_mark_phase_complete() -> None:
    architecture = source_for(ARCHITECTURE_PATH)
    readme = source_for(README_PATH)
    phase14k_section = architecture.split("## Phase 14K:", maxsplit=1)[1].split(
        "\n## ",
        maxsplit=1,
    )[0]

    assert "Status: Complete." in phase14k_section
    assert "Phase 14K is complete" in architecture
    assert "Phase 14K is complete" in readme
    assert "Phase 14K is in progress" not in architecture
    assert "Phase 14K is in progress" not in readme


def _runtime_python_files() -> tuple[Path, ...]:
    return python_files(SRC_ROOT)


def _source_for_path(path: Path) -> str:
    if path == SHOOTING_PHASE_PATH:
        return combined_source_for(SHOOTING_PHASE_SPLIT_PATHS)
    return source_for(path)
