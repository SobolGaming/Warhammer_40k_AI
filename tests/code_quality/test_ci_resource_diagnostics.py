from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import cast

import pytest
from scripts.ci_resource_diagnostics import snapshot

ROOT = Path(__file__).resolve().parents[2]


def test_resource_snapshots_are_read_only_and_label_counter_scope(tmp_path: Path) -> None:
    files = {
        "proc/vmstat": "pgfault 20\noom_kill 8\n",
        "proc/self/cgroup": "0::/job\n",
        "sys/fs/cgroup/job/memory.events": "low 0\noom 2\noom_kill 1\n",
        "sys/fs/cgroup/job/memory.peak": "2048\n",
        "sys/fs/cgroup/job/memory.current": "1024\n",
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    before = snapshot(phase="before", root=tmp_path)
    after = snapshot(phase="after", root=tmp_path)
    assert {name: (tmp_path / name).read_text() for name in files} == files
    assert cast(dict[str, object], before["host_oom_kill"])["value"] == 8
    cgroup = cast(dict[str, object], after["cgroup"])
    readings = cast(dict[str, dict[str, object]], cgroup["readings"])
    assert readings["memory.peak"]["text"] == "2048\n"
    assert readings["memory.events"]["text"] == "low 0\noom 2\noom_kill 1\n"
    assert readings["memory.max"]["available"] is False
    assert "lifetime" in str(after["interpretation"])
    assert "not proof" in str(after["interpretation"])
    assert after["worker_exit_code"] is None
    assert "Unknown" in str(after["worker_exit_code_availability"])


@pytest.mark.parametrize("membership", [None, "4:memory:/job\n", "0::/../../outside\n"])
def test_unavailable_or_unsupported_resource_scope_is_explicit(
    tmp_path: Path,
    membership: str | None,
) -> None:
    if membership is not None:
        path = tmp_path / "proc/self/cgroup"
        path.parent.mkdir(parents=True)
        path.write_text(membership, encoding="utf-8")
    receipt = snapshot(phase="after", root=tmp_path)
    assert cast(dict[str, object], receipt["host_oom_kill"])["available"] is False
    assert cast(dict[str, object], receipt["cgroup"])["available"] is False
    assert receipt["worker_exit_code"] is None


@pytest.mark.skipif(os.name != "posix", reason="Hosted inner workload is a POSIX shell.")
@pytest.mark.parametrize(
    ("history", "pytest_status", "expected"), [(0, 0, 0), (0, 7, 1), (23, 0, 23)]
)
def test_diagnostic_failure_never_masks_inner_workload_status(
    tmp_path: Path,
    history: int,
    pytest_status: int,
    expected: int,
) -> None:
    executable = tmp_path / "uv"
    executable.write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        ' *scripts.ci_resource_diagnostics*) echo "diagnostic $*" >> calls; exit 9;;\n'
        ' *scripts.validate_source_history*) exit "$HISTORY_STATUS";;\n'
        ' *pytest*) exit "$PYTEST_STATUS";;\n'
        " *) exit 77;;\n"
        "esac\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    manifest = tmp_path / "shard.txt"
    manifest.write_text("tests/selected.py\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run_behavioral_coverage.sh")],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "HISTORY_STATUS": str(history),
            "PYTEST_STATUS": str(pytest_status),
            "SHARD_MANIFEST": str(manifest),
            "SHARD_ID": "1",
            "SELECTED_INDEX_CACHE_HIT": "true",
            "SELECTED_ARMY_SOURCE_INDEX": "unused.json",
            "BEHAVIOR_EXECUTION_DEADLINE": "1800",
            "TEST_TIMING_DIR": "reports/timing",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected
    calls = (tmp_path / "calls").read_text().splitlines()
    assert len(calls) == 2
    assert "--phase before" in calls[0]
    assert "--phase after" in calls[1]
    assert result.stderr.count("workload status is unchanged") == 2


def test_invalid_snapshot_phase_is_rejected() -> None:
    with pytest.raises(ValueError, match="before or after"):
        snapshot(phase="during")
