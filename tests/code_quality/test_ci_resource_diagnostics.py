from __future__ import annotations

import json
import os
import subprocess
import sys
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


@pytest.mark.skipif(os.name != "posix", reason="Hosted inner workload is a POSIX shell.")
@pytest.mark.parametrize("selection", ["parallel", "mirror", "native", "both", "native-only"])
@pytest.mark.parametrize(("serial_status", "parallel_status"), [(0, 0), (7, 0), (0, 9)])
def test_bounded_setup_lane_preserves_selection_coverage_and_failure(
    tmp_path: Path,
    selection: str,
    serial_status: int,
    parallel_status: int,
) -> None:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE
    from scripts.current_shard_compatibility import NATIVE_PREFIX_OWNER, NEW_NODES

    mirror_owner = SERIAL_BEHAVIORAL_CASE.split("::", 1)[0]
    ordinary = "tests/ordinary.py"
    selectors = [] if selection == "native-only" else [ordinary]
    serial_selectors: list[str] = []
    if selection in {"mirror", "both"}:
        selectors.extend([mirror_owner, SERIAL_BEHAVIORAL_CASE])
        serial_selectors.append(SERIAL_BEHAVIORAL_CASE)
    if selection in {"native", "both", "native-only"}:
        selectors.append(NATIVE_PREFIX_OWNER)
        serial_selectors.append(NATIVE_PREFIX_OWNER)
    selectors.sort()  # Real manifests put the native filename before the mirror node.
    parallel_selectors = [item for item in selectors if item not in serial_selectors]
    executable = tmp_path / "uv"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "if 'pytest' in args:\n"
        "    with Path('pytest-calls.jsonl').open('a') as stream:\n"
        "        stream.write(json.dumps({'args': args, "
        "'timing': os.environ['TEST_TIMING_DIR']}) + '\\n')\n"
        "    lane = 'SERIAL_STATUS' if args[args.index('-n') + 1] == '1' "
        "else 'PARALLEL_STATUS'\n"
        "    sys.exit(int(os.environ[lane]))\n"
        "if any(name in args for name in "
        "('scripts.ci_resource_diagnostics', 'scripts.validate_source_history')):\n"
        "    sys.exit(0)\n"
        "sys.exit(77)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    manifest = tmp_path / "shard.txt"
    manifest.write_text("\n".join(selectors) + "\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run_behavioral_coverage.sh")],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "SERIAL_STATUS": str(serial_status),
            "PARALLEL_STATUS": str(parallel_status),
            "SHARD_MANIFEST": str(manifest),
            "SHARD_ID": "2",
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
    expected_failure = bool(
        (serial_selectors and serial_status) or (parallel_selectors and parallel_status)
    )
    assert result.returncode == int(expected_failure), result.stdout + result.stderr
    calls = [
        cast(dict[str, object], json.loads(line))
        for line in (tmp_path / "pytest-calls.jsonl").read_text().splitlines()
    ]
    assert len(calls) == bool(serial_selectors) + bool(parallel_selectors)
    observed_selection: list[str] = []
    for index, call in enumerate(calls):
        args = cast(list[str], call["args"])
        start = args.index("pytest") + 1
        stop = next(
            position for position in range(start, len(args)) if args[position].startswith("-")
        )
        selected = args[start:stop]
        serial_lane = bool(serial_selectors) and index == 0
        assert selected == (serial_selectors if serial_lane else parallel_selectors)
        observed_selection.extend(selected)
        assert args[args.index("-n") + 1] == ("1" if serial_lane else "auto")
        assert args.count("--cov=warhammer40k_core") == 1
        assert args.count("--cov-append") == int(bool(serial_selectors) and not serial_lane)
        assert "--cov-fail-under=0" in args
        assert "--dist=worksteal" in args
        if serial_lane:
            assert call["timing"] == "reports/timing/isolated-mirror"
        else:
            assert args[args.index("--deselect") + 1] == SERIAL_BEHAVIORAL_CASE
            assert call["timing"] == (
                "reports/timing/remainder" if serial_selectors else "reports/timing"
            )
    assert sorted(observed_selection) == sorted(selectors)
    # Expand the one file that must keep all six real cases together. The mirror
    # node is selected only in the serial lane and deselected from its owner file.
    native_nodes = {node for node in NEW_NODES if node.split("::", 1)[0] == NATIVE_PREFIX_OWNER}
    assert len(native_nodes) == 6
    assert observed_selection.count(NATIVE_PREFIX_OWNER) == int(NATIVE_PREFIX_OWNER in selectors)
    assert observed_selection.count(SERIAL_BEHAVIORAL_CASE) == int(
        SERIAL_BEHAVIORAL_CASE in selectors
    )
