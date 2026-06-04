from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
ATTACK_SEQUENCE_PATH = SRC_ROOT / "engine" / "attack_sequence.py"
DAMAGE_ALLOCATION_PATH = SRC_ROOT / "engine" / "damage_allocation.py"
SHOOTING_PHASE_PATH = SRC_ROOT / "engine" / "phases" / "shooting.py"
LIFECYCLE_PATH = SRC_ROOT / "engine" / "lifecycle.py"
ADAPTER_CONTRACT_PATH = ROOT / "docs" / "ADAPTER_DECISION_CONTRACT.md"


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
        (SHOOTING_PHASE_PATH, "apply_damage_allocation_model_decision"),
        (LIFECYCLE_PATH, "SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE"),
        (LIFECYCLE_PATH, "_invalid_damage_allocation_model_status"),
    )
    missing: list[str] = []

    for path, token in runtime_expectations:
        if token not in path.read_text(encoding="utf-8"):
            missing.append(f"{path.relative_to(ROOT).as_posix()}: missing {token!r}")

    contract_text = ADAPTER_CONTRACT_PATH.read_text(encoding="utf-8")
    if "select_damage_allocation_model" not in contract_text:
        missing.append("docs/ADAPTER_DECISION_CONTRACT.md: missing damage model decision")

    assert not missing, (
        "Phase 14K damage model allocation choice must be registered in runtime "
        "and the adapter contract:\n" + "\n".join(missing)
    )


def _runtime_python_files() -> tuple[Path, ...]:
    return tuple(sorted(SRC_ROOT.rglob("*.py"), key=lambda path: path.as_posix()))
