from __future__ import annotations

from pathlib import Path

from warhammer40k_core.core.ruleset_descriptor import (
    CoherencyPolicyKind,
    CoverEffect,
    ReserveDestructionTimingKind,
    RulesetDescriptor,
)
from warhammer40k_core.engine.reserves import StrategicReserveRule
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_stratagems import (
    core_stratagem_rows,
)

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
ATTACK_SEQUENCE_PATH = SRC_ROOT / "engine" / "attack_sequence.py"
DAMAGE_ALLOCATION_PATH = SRC_ROOT / "engine" / "damage_allocation.py"
SHOOTING_PHASE_PATH = SRC_ROOT / "engine" / "phases" / "shooting.py"
SHOOTING_PHASE_SPLIT_PATHS = tuple(sorted(SHOOTING_PHASE_PATH.parent.glob("shooting*.py")))
LIFECYCLE_PATH = SRC_ROOT / "engine" / "lifecycle.py"
RESERVES_PATH = SRC_ROOT / "engine" / "reserves.py"
CORE_STRATAGEMS_PATH = (
    SRC_ROOT / "rules" / "source_packages" / "warhammer_40000_11th" / "core_stratagems.py"
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
        text = path.read_text(encoding="utf-8")
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

    contract_text = ADAPTER_CONTRACT_PATH.read_text(encoding="utf-8")
    if "select_damage_allocation_model" not in contract_text:
        missing.append("docs/ADAPTER_DECISION_CONTRACT.md: missing damage model decision")

    assert not missing, (
        "Phase 14K damage model allocation choice must be registered in runtime "
        "and the adapter contract:\n" + "\n".join(missing)
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
        text = path.read_text(encoding="utf-8")
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

    source = RESERVES_PATH.read_text(encoding="utf-8")
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

    source = CORE_STRATAGEMS_PATH.read_text(encoding="utf-8")
    assert "Counter-offensive" not in source
    assert "stratagem_id=" + '"grenade"' not in source
    assert "stratagem_id=" + '"tank-shock"' not in source
    assert "stratagem_id=" + '"go-to-ground"' not in source


def test_phase14k_docs_mark_phase_complete() -> None:
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
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
    return tuple(sorted(SRC_ROOT.rglob("*.py"), key=lambda path: path.as_posix()))


def _source_for_path(path: Path) -> str:
    if path == SHOOTING_PHASE_PATH:
        return "\n".join(
            split_path.read_text(encoding="utf-8") for split_path in SHOOTING_PHASE_SPLIT_PATHS
        )
    return path.read_text(encoding="utf-8")
