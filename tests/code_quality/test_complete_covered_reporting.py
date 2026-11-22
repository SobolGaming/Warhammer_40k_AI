from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import run_complete_covered_profile as profile


@pytest.mark.parametrize("case", ["below_floor", "at_floor", "branch_denominator"])
def test_complete_json_reporting_preserves_floor_evidence_and_failure_propagation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    package = tmp_path / "fixture_package"
    package.mkdir()
    (package / "__init__.py").write_text("")
    source = package / "sample.py"
    if case == "branch_denominator":
        source.write_text("flag = True\nif flag:\n    value = 1\nelse:\n    value = 2\n")
        executed_lines = 5
    else:
        source.write_text("".join(f"value_{line} = {line}\n" for line in range(10000)))
        executed_lines = 6800 if case == "at_floor" else 6799
    (tmp_path / "pyproject.toml").write_text(
        "[tool.coverage.run]\nbranch = true\nsource = "
        + json.dumps([str(package)])
        + "\n[tool.coverage.report]\nfail_under = 68\nprecision = 2\n"
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        "from pathlib import Path\n"
        "source = Path('fixture_package/sample.py').resolve()\n"
        f"prefix = ''.join(source.read_text().splitlines(keepends=True)[:{executed_lines}])\n"
        "exec(compile(prefix, str(source), 'exec'))\n"
    )
    output = tmp_path / "reports"
    output.mkdir()
    environment = {**os.environ, "COVERAGE_FILE": str(output / ".coverage")}
    measured = subprocess.run(
        [sys.executable, "-B", "-m", "coverage", "run", str(driver)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert measured.returncode == 0, measured.stdout + measured.stderr
    monkeypatch.setattr(profile, "ROOT", tmp_path)
    command = profile.coverage_report_command(output)
    assert command == [
        sys.executable,
        "-B",
        "-m",
        "coverage",
        "json",
        "--fail-under=68",
        "-o",
        str(output / "coverage.json"),
    ]
    # The controller's stage must return the real gate's failure and stop before
    # any later command. Full JSON evidence still exists for below-floor results.
    marker = output / "subsequent-command.txt"
    stages: list[dict[str, object]] = []
    status = profile._stage(  # pyright: ignore[reportPrivateUsage]
        "coverage",
        [
            command,
            [
                sys.executable,
                "-c",
                "from pathlib import Path; "
                "Path('reports/subsequent-command.txt').write_text('ran')",
            ],
        ],
        output=output,
        environment=environment,
        stages=stages,
    )
    expected_status = 0 if case == "at_floor" else 2
    assert status == expected_status
    assert stages[0]["exit_code"] == expected_status
    assert marker.exists() == (expected_status == 0)
    evidence = json.loads((output / "coverage.json").read_bytes())
    assert evidence["meta"]["branch_coverage"] is True
    assert set(evidence["files"]) == {"fixture_package/__init__.py", "fixture_package/sample.py"}
    totals = evidence["totals"]
    if case == "branch_denominator":
        assert totals["num_statements"] == 4
        assert totals["covered_lines"] == 3
        assert totals["num_branches"] == 2
        assert totals["covered_branches"] == 1
        assert totals["percent_covered_display"] == "66.67"
    else:
        assert totals["num_statements"] == 10000
        assert totals["covered_lines"] == executed_lines
        assert totals["percent_covered"] == executed_lines / 100
