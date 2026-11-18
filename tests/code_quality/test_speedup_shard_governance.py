"""Governance and regression controls for streamlined LPT sharding and CI/local speedups."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import scripts.build_test_shards as sharding

from tests.support.cross_worker_fixture_cache import (
    load_or_build_json_fixture,
    rehydrate_payload_receipt,
)
from warhammer40k_core.ai.canonical_deployment import CanonicalDeploymentAdmission
from warhammer40k_core.engine.event_log import JsonValue

ROOT = Path(__file__).resolve().parents[2]
SHARD_DIR = ROOT / "ci/test_shards"
MAX_SHARD_DIRECTORY_BYTES = 5 * 1024 * 1024


def test_shard_directory_is_free_of_historical_calibration_bloat() -> None:
    files = {
        p.relative_to(SHARD_DIR).as_posix(): p.stat().st_size
        for p in SHARD_DIR.rglob("*")
        if p.is_file()
    }
    expected = {
        "case-partitions.json",
        "durations.json",
        "preflight-case-partition.json",
        "step5g-case-partitions.json",
        "worker_benchmark.json",
        *(f"shard-{i}.txt" for i in range(1, 13)),
    }
    assert set(files) == expected
    assert sum(files.values()) < MAX_SHARD_DIRECTORY_BYTES
    completed = subprocess.run(
        [sys.executable, "-B", "scripts/build_test_shards.py", "--check", "--shard-count", "12"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_ci_workflow_has_preflight_caches_and_adaptive_runner_label() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ci-preflight:" in workflow
    assert "runs-on: ${{ vars.CI_LINUX_RUNNER || 'ubuntu-latest' }}" in workflow
    assert "path: .mypy_cache" in workflow
    assert "venv-test-v1-" in workflow
    assert 'WH40K_SOURCE_HISTORY_PREVALIDATED: "1"' in workflow
    assert "fetch_scheduling_sources.py" not in workflow


def test_multi_worker_worksteal_relevance_spreads_heavy_s25_cases() -> None:
    heavy = sharding._literal_partition_nodes(ROOT)[:10]  # pyright: ignore[reportPrivateUsage]
    ordinary = tuple(f"tests/fast/test_mod.py::test_case_{i}" for i in range(60))
    combined = (*heavy, *ordinary)
    for workers in (4, 8, 16, 32):
        if len(heavy) > workers:
            continue
        order = sharding.worksteal_relevance_order(combined, workers=workers)
        assert sorted(order) == list(range(len(combined)))
        offset = 0
        seen_heavy = 0
        for worker in range(workers):
            width = (len(combined) - offset) // (workers - worker)
            chunk = [combined[idx] for idx in order[offset : offset + width]]
            if worker < len(heavy):
                assert chunk[0] == heavy[worker]
                seen_heavy += 1
            offset += width
        assert seen_heavy == len(heavy)


def test_cross_worker_fixture_cache_builds_once_and_rejects_corruption(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    pytestconfig: pytest.Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", "speedup-unit-uid")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    source_probe = tmp_path / "fixture_owner.py"
    source_probe.write_text("VERSION = 1\n", encoding="utf-8")
    builds = 0

    def _build() -> JsonValue:
        nonlocal builds
        builds += 1
        return {"value": 42}

    first = load_or_build_json_fixture(
        key="unit-cache-probe",
        source_files=(source_probe,),
        tmp_path_factory=tmp_path_factory,
        pytestconfig=pytestconfig,
        build_payload=_build,
        restore_value=lambda raw: raw,
    )
    second = load_or_build_json_fixture(
        key="unit-cache-probe",
        source_files=(source_probe,),
        tmp_path_factory=tmp_path_factory,
        pytestconfig=pytestconfig,
        build_payload=_build,
        restore_value=lambda raw: raw,
    )
    assert first == second == {"value": 42}
    assert builds == 1

    # Source file modification invalidates the digest and forces a fresh build.
    source_probe.write_text("VERSION = 2\n", encoding="utf-8")
    third = load_or_build_json_fixture(
        key="unit-cache-probe",
        source_files=(source_probe,),
        tmp_path_factory=tmp_path_factory,
        pytestconfig=pytestconfig,
        build_payload=_build,
        restore_value=lambda raw: raw,
    )
    assert third == {"value": 42}
    assert builds == 2

    receipt = rehydrate_payload_receipt(CanonicalDeploymentAdmission, {"ok": True})
    assert receipt.to_payload() == {"ok": True}

    cache_dir = tmp_path_factory.getbasetemp().parent / "xdist-fixture-cache-speedup-unit-uid"
    entries = list(cache_dir.glob("*.json"))
    assert len(entries) == 2
    # Corrupt the active VERSION=2 digest entry in place so the next lookup hits
    # the bad envelope instead of an older sibling digest.
    source_probe.write_text("VERSION = 2\n", encoding="utf-8")
    for entry in entries:
        entry.write_text('{"schema": "wrong"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupted cross-worker fixture cache"):
        load_or_build_json_fixture(
            key="unit-cache-probe",
            source_files=(source_probe,),
            tmp_path_factory=tmp_path_factory,
            pytestconfig=pytestconfig,
            build_payload=_build,
            restore_value=lambda raw: raw,
        )
