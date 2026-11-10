"""Operator accounting/watchdog controls; no engine behavior replacement."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("resource")

from scripts import measure_canonical_deployment_costs as costs


def test_timing_journal_preserves_failure_and_propagates(tmp_path: Path) -> None:
    journal = costs.Journal(tmp_path / "attempts.jsonl")
    assert journal.timed("success", lambda: 17, phase="test") == 17

    def fail() -> None:
        raise ValueError("real diagnostic failure")

    with pytest.raises(ValueError, match="real diagnostic failure"):
        journal.timed("failure", fail, phase="test")
    rows, partial = costs.read_journal(journal.path)
    assert partial is None
    assert [row["event"] for row in rows] == ["start", "finish", "start", "finish"]
    assert [row["sequence"] for row in rows] == [1, 1, 2, 2]
    assert rows[-1]["outcome"] == "failed"
    assert rows[-1]["exception_type"] == "ValueError"
    assert rows[-1]["wall_seconds"] >= 0
    assert rows[-1]["cpu_seconds"] >= 0


def test_partial_journal_retains_killed_attempt_and_rejects_interior_damage(tmp_path: Path) -> None:
    path = tmp_path / "attempts.jsonl"
    path.write_text('{"event":"start"}\n{"event":')
    rows, partial = costs.read_journal(path)
    assert rows == [{"event": "start"}]
    assert partial == '{"event":'
    path.write_text('{"event":\n{"event":"finish"}\n')
    with pytest.raises(json.JSONDecodeError):
        costs.read_journal(path)


def test_summary_keeps_warm_cold_and_occurrences_separate() -> None:
    events: list[dict[str, Any]] = [
        {"event": "start", "name": "unfinished"},
        {"event": "finish", "outcome": "failed", "wall_seconds": 999},
    ]
    for seconds, state, index in (
        (1, "first_iteration", 4),
        (3, "first_iteration", 4),
        (7, "within_process_repeat", 4),
        (9, "first_iteration", 6),
    ):
        events.append(
            {
                "event": "finish",
                "outcome": "passed",
                "wall_seconds": seconds,
                "process_state": state,
                "index": index,
                "name": "cost",
                "phase": "test",
            }
        )
    result = costs.summarize([{"events": events}])
    assert [row["n"] for row in result] == [2, 1, 1]
    assert result[0]["mean_seconds"] == result[0]["median_seconds"] == 2
    assert result[0]["min_seconds"] == 1
    assert result[0]["max_seconds"] == 3
    assert result[0]["empirical_p90_seconds"] == result[0]["empirical_p95_seconds"] == 3
    assert result[1]["sample_stdev_seconds"] is None


def test_budget_boundary_stops_at_first_exhausted_limit() -> None:
    assert costs.budget_reason(9, 19, 10, 20) is None
    assert costs.budget_reason(10, 19, 10, 20) == "campaign_wall_budget"
    assert costs.budget_reason(9, 20, 10, 20) == "campaign_cpu_budget"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc supervisor")
def test_real_supervisor_retains_failure_and_enforces_wall_and_cpu(tmp_path: Path) -> None:
    for index, (program, wall, cpu, reason, code) in enumerate(
        (
            ("import sys; print('failure', file=sys.stderr); sys.exit(7)", 30, 30, None, 7),
            (
                "import time; print('started', flush=True); time.sleep(30)",
                0.3,
                30,
                "campaign_wall_budget",
                -9,
            ),
            ("while True: pass", 30, 0.2, "campaign_cpu_budget", -9),
        )
    ):
        directory = tmp_path / str(index)
        directory.mkdir()
        observed, stopped = costs.supervise(
            [sys.executable, "-c", program], directory, time.monotonic(), 0, wall, cpu
        )
        assert observed == code
        assert stopped == reason
    assert "failure" in (tmp_path / "0/stderr.log").read_text()
    assert "started" in (tmp_path / "1/stdout.log").read_text()


def test_cli_refuses_invalid_budgets_and_existing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for budget in ("nan", "0", "28801"):
        monkeypatch.setattr(
            sys, "argv", ["measure", "--output", str(tmp_path), "--cpu-seconds", budget]
        )
        with pytest.raises(SystemExit) as stopped:
            costs.main()
        assert stopped.value.code == 2
    arguments = costs.parser().parse_args(["--output", str(tmp_path)])
    with pytest.raises(FileExistsError):
        costs.campaign(arguments)


def test_retained_canonical_cost_evidence_reconciles_exact_report_and_attempts() -> None:
    root = Path(__file__).resolve().parents[2]
    directory = root / "docs/performance/canonical-deployment-costs-v1"
    evidence = json.loads((directory / "measurement.json").read_text())
    report = json.loads((directory / "canonical-report.json").read_text())
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    report_hash = hashlib.sha256(canonical.encode()).hexdigest()
    assert evidence["schema_version"] == costs.SCHEMA
    assert evidence["status"] == "complete"
    assert evidence["report_hash"] == report_hash
    assert report["schema_version"] == "canonical-deployment-coverage-v1"
    assert report["admission"]["configuration_hash"] == (
        "adfdb1ee885d9de34ddbe6ef7fe1be64c728f86d3529dc2e82b7523132926409"
    )
    assert report["totals"]["finite"]["accepted_count"] == 18
    placement = report["totals"]["placement"]
    assert placement["accepted_count"] == 19
    assert placement["validation_attempts"] == 20
    assert placement["legal_reference_count"] == 32
    assert placement["covered_legal_reference_count"] == 19
    assert placement["invalid_reference_probe_count"] == 8
    assert [row["index"] for row in report["rows"]] == list(range(11))
    assert report["stop_reason"] == "before-redeploy"
    for row in report["rows"]:
        if row["kind"] == "placement":
            assert row["candidate_set"]["raw_budget"] == 64
            assert row["candidate_set"]["raw_attempts"] == 5
            assert row["reference_set"]["raw_budget"] == 10
            assert row["reference_set"]["raw_attempts"] == 10
    settings = evidence["settings"]
    assert (settings["processes"], settings["repeats"], settings["components"]) == (3, 1, True)
    assert settings["cpu_budget_seconds"] <= costs.MAX_CPU_SECONDS
    assert evidence["elapsed_wall_seconds"] < settings["wall_budget_seconds"]
    assert evidence["child_cpu_seconds"] < settings["cpu_budget_seconds"]
    environment = evidence["environment"]
    assert environment["harness_sha256"] == costs.digest(
        root / "scripts/measure_canonical_deployment_costs.py"
    )
    assert environment["lock_sha256"] == costs.digest(root / "uv.lock")
    assert environment["cpu_affinity"]
    assert environment["cpuinfo"]
    assert environment["meminfo"]
    assert environment["dependencies"]
    assert environment["python"]
    assert environment["platform"]
    assert environment["engine_manifest"]["fingerprint"] == (
        "fead332323b81b04f201802bb82a254269cac3569b141b14705a6f971673ad3e"
    )
    assert [attempt["index"] for attempt in evidence["attempts"]] == [0, 1, 2]
    for attempt in evidence["attempts"]:
        assert attempt["returncode"] == 0
        assert attempt["stop_reason"] is None
        assert attempt["partial_journal_line"] is None
        events = attempt["events"]
        assert events[-1] == {"event": "worker_complete", "report_hash": report_hash}
        starts = [row for row in events if row["event"] == "start"]
        finishes = [row for row in events if row["event"] == "finish"]
        assert [row["sequence"] for row in starts] == list(range(1, len(starts) + 1))
        assert [row["sequence"] for row in finishes] == [row["sequence"] for row in starts]
        for start, finish in zip(starts, finishes, strict=True):
            assert start["name"] == finish["name"]
            assert finish["outcome"] == "passed"
            assert finish["exception_type"] is None
            assert finish["wall_seconds"] >= 0
            assert finish["cpu_seconds"] >= 0
        headlines = [
            row for row in finishes if row["name"] in ("coverage_measure", "coverage_from_payload")
        ]
        assert [row["name"] for row in headlines] == ["coverage_measure", "coverage_from_payload"]
        assert all(
            row["repeat"] == 0 and row["process_state"] == "first_iteration" for row in headlines
        )
        verified = [row for row in events if row["event"] == "verified_report"]
        assert len(verified) == 1
        assert verified[0]["hash"] == report_hash
        components = [row for row in finishes if row["phase"] == "prepared_component_pass"]
        assert {row["name"] for row in components} >= {
            "configuration",
            "session_start",
            "initial_advance",
            "admission",
            "prefix_reconstruction",
            "persistence_encode",
            "persistence_restore",
            "replay_load_and_run",
            "fresh_fork",
            "finite_generation",
            "finite_fresh_fork_validation",
            "placement_generation",
            "placement_fresh_fork_validation",
        }
        assert [row["index"] for row in components if row["name"] == "fresh_fork"] == list(
            range(11)
        )
        for role, count in (("generated", 5), ("reference", 10)):
            validation = [
                row
                for row in components
                if row["name"] == "placement_fresh_fork_validation" and row["role"] == role
            ]
            assert [row["index"] for row in validation] == [4, 6, 8, 10]
            assert all(row["candidate_count"] == count for row in validation)
    assert evidence["summary"] == costs.summarize(evidence["attempts"])

    # Retain the predecessor pilot verbatim, outside the three final samples.
    # Its original driver bytes were not saved; no current-driver reproduction
    # or source-authentication claim is inferred from its recorded digest.
    pilot_path = directory / "pilot-diagnostic.json"
    assert costs.digest(pilot_path) == (
        "2047acfd2951c269e61f7356fc3b5202caf8282543060847cb7473416bed7033"
    )
    pilot = json.loads(pilot_path.read_text())
    assert pilot["status"] == "complete"
    assert pilot["report_hash"] == report_hash
    assert pilot["environment"]["harness_sha256"] != environment["harness_sha256"]
    assert pilot["settings"]["processes"] == 1
    assert pilot["settings"]["repeats"] == 1
    assert pilot["settings"]["components"] is False
    assert pilot["settings"]["wall_budget_seconds"] == 600
    assert pilot["settings"]["cpu_budget_seconds"] == 1200
    assert pilot["elapsed_wall_seconds"] < 600
    assert pilot["child_cpu_seconds"] < 1200
    assert len(pilot["attempts"]) == 1
    pilot_attempt = pilot["attempts"][0]
    assert pilot_attempt["index"] == 0
    assert pilot_attempt["returncode"] == 0
    assert pilot_attempt["stop_reason"] is None
    assert pilot_attempt["partial_journal_line"] is None
    pilot_events = pilot_attempt["events"]
    assert pilot_events[-1] == {"event": "worker_complete", "report_hash": report_hash}
    pilot_starts = [row for row in pilot_events if row["event"] == "start"]
    pilot_finishes = [row for row in pilot_events if row["event"] == "finish"]
    assert [row["sequence"] for row in pilot_starts] == [1, 2, 3, 4, 5]
    assert [row["sequence"] for row in pilot_finishes] == [1, 2, 3, 4, 5]
    assert [row["name"] for row in pilot_finishes] == [
        "runtime_import",
        "endpoint_reproduction",
        "coverage_measure",
        "report_json_roundtrip",
        "coverage_from_payload",
    ]
    assert all(row["outcome"] == "passed" for row in pilot_finishes)


def test_component_generator_parameters_preserve_production_raw_budgets() -> None:
    root = Path(__file__).resolve().parents[2]
    source = ast.parse(
        (root / "src/warhammer40k_core/ai/canonical_deployment_coverage.py").read_text()
    )
    placement = next(
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "_placement_row"
    )
    calls = [
        node
        for node in ast.walk(placement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "generate"
    ]
    assert len(calls) == 2
    assert not any(keyword.arg == "raw_budget" for keyword in calls[0].keywords)
    assert costs.generation_parameters(None) == {}
    reference_budget = next(
        keyword.value for keyword in calls[1].keywords if keyword.arg == "raw_budget"
    )
    assert isinstance(reference_budget, ast.Constant)
    offsets = ((0.0, 0.0),)
    assert costs.generation_parameters(offsets) == {
        "translations": offsets,
        "raw_budget": reference_budget.value,
    }
