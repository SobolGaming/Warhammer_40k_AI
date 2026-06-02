from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
SOURCE_DIRS = (ROOT / "src", ROOT / "tests")


def test_phase14c_retired_pivot_cost_policy_is_not_used() -> None:
    violations: list[str] = []

    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(ROOT).as_posix()
        for token in _retired_pivot_cost_tokens():
            if token in text:
                violations.append(f"{relative_path}: contains {token!r}")

    assert not violations, (
        "Phase 14C retires pivot-cost movement policy. Rotations remain legal movement "
        "witnesses, but they must not add distance cost:\n" + "\n".join(violations)
    )


def _python_files() -> tuple[Path, ...]:
    paths: list[Path] = []
    for source_dir in SOURCE_DIRS:
        paths.extend(path for path in source_dir.rglob("*.py") if path != THIS_FILE)
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def _retired_pivot_cost_tokens() -> tuple[str, ...]:
    return (
        "PivotCostPolicy",
        "PivotCostPolicyPayload",
        "pivot_cost_policy",
        "pivot_cost_inches",
        "pivot_cost_pending",
        "pivot_value_inches",
        "applied_cost_inches",
        "first_pivot_for_model",
    )
