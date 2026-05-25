from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_STUB_PATTERNS = [
    "SimpleNamespace(",
    "Mock(",
    "MagicMock(",
]


def test_no_stubs_in_integration_tests() -> None:
    integration_dirs = [
        ROOT / "tests" / "integration",
        ROOT / "tests" / "replay",
    ]

    violations: list[str] = []

    for directory in integration_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_STUB_PATTERNS:
                if pattern in text:
                    violations.append(f"{path.relative_to(ROOT)} uses {pattern}")

    assert not violations, "Integration/replay tests must use real fixtures:\n" + "\n".join(
        violations
    )