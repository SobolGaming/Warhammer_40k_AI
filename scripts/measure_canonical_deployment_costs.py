"""Serial Linux operator diagnostics for the frozen deployment coverage report.

Run with the locked project interpreter, without coverage/profiling/test workers.
No clock or measurement field is added to runtime objects or authoritative JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import signal
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

SCHEMA = "canonical-deployment-costs-v1"
MAX_CPU_SECONDS = 8 * 60 * 60
ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_roundtrip(value: object) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


class Journal:
    """Append before entering an operation, retaining incomplete attempts on kill."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sequence = 0

    def append(self, value: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")

    def timed(self, name: str, operation: Callable[[], T], **context: Any) -> T:
        self.sequence += 1
        identity = {"sequence": self.sequence, "name": name, **context}
        self.append({**identity, "event": "start", "utc": datetime.now(UTC).isoformat()})
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            return operation()
        finally:
            elapsed_wall, elapsed_cpu = time.perf_counter() - wall, time.process_time() - cpu
            error = sys.exc_info()[0]
            self.append(
                {
                    **identity,
                    "event": "finish",
                    "wall_seconds": elapsed_wall,
                    "cpu_seconds": elapsed_cpu,
                    "outcome": "passed" if error is None else "failed",
                    "exception_type": None if error is None else error.__name__,
                }
            )


def generation_parameters(translations: tuple[tuple[float, float], ...] | None) -> dict[str, Any]:
    # Default generated search keeps the owner's raw ceiling of 64 even though
    # the default offset count is bounded. Reference generation explicitly uses ten.
    return {} if translations is None else {"translations": translations, "raw_budget": 10}


def worker(output: Path, repeats: int, components: bool, reference_suite: bool = False) -> None:
    if reference_suite:
        reference_suite_worker(output, repeats, components)
        return
    journal = Journal(output / "attempts.jsonl")

    def imports() -> None:
        # Import timing is distinct from interpreter/process startup. Keeping it
        # here permits a real first import in each newly launched worker.
        import warhammer40k_core.ai.canonical_deployment_coverage  # noqa: F401

    journal.timed("runtime_import", imports, phase="bootstrap")
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.ai.canonical_deployment import (
        CanonicalDeploymentAdmission,
        canonical_deployment_config,
        canonical_deployment_prefixes,
        reproduce_canonical_deployment,
    )
    from warhammer40k_core.ai.canonical_deployment_coverage import (
        REFERENCE_TRANSLATIONS,
        CanonicalDeploymentCoverage,
    )
    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.replay import ReplayRunner

    expected_hash: str | None = None
    for repeat in range(repeats):
        context = {
            "repeat": repeat,
            "phase": "full_report",
            "process_state": "first_iteration" if repeat == 0 else "within_process_repeat",
        }
        session, recipe = journal.timed(
            "endpoint_reproduction", reproduce_canonical_deployment, **context
        )
        report = journal.timed(
            "coverage_measure",
            partial(CanonicalDeploymentCoverage.measure, session=session),
            **context,
        )
        # JSON conversion deliberately outside both headline report timers.
        payload = journal.timed(
            "report_json_roundtrip",
            partial(json_roundtrip, report.to_payload()),
            **context,
        )
        loaded = journal.timed(
            "coverage_from_payload",
            partial(CanonicalDeploymentCoverage.from_payload, payload, session=session),
            **context,
        )
        if report.content_hash != loaded.content_hash:
            raise ValueError("Closed reproduction changed the report content hash.")
        if expected_hash is not None and expected_hash != report.content_hash:
            raise ValueError("Within-process report identity drifted.")
        expected_hash = report.content_hash
        journal.append({"event": "verified_report", **context, "hash": expected_hash})
        if repeat == 0:
            write_json(output / "canonical-report.json", payload)

    if components:
        context = {"phase": "prepared_component_pass", "repeat": 0}
        config = journal.timed("configuration", canonical_deployment_config, **context)
        startup = LocalGameSession()
        journal.timed("session_start", partial(startup.start, config), **context)
        journal.timed("initial_advance", startup.advance_until_decision_or_terminal, **context)
        journal.timed(
            "admission", lambda: CanonicalDeploymentAdmission.from_session(session), **context
        )
        prefixes = journal.timed(
            "prefix_reconstruction",
            lambda: canonical_deployment_prefixes(session, recipe),
            **context,
        )
        checkpoint = journal.timed("persistence_encode", session.to_persistence_payload, **context)
        checkpoint = journal.timed(
            "checkpoint_json_roundtrip", partial(json_roundtrip, checkpoint), **context
        )
        restored = journal.timed(
            "persistence_restore",
            partial(LocalGameSession.from_persistence_payload, checkpoint),
            **context,
        )
        if canonical_json(restored.to_persistence_payload()) != canonical_json(checkpoint):
            raise ValueError("Persistence diagnostic failed exact checkpoint reproduction.")
        artifact = journal.timed(
            "replay_artifact",
            lambda: session.replay_artifact(artifact_id="component-costs"),
            **context,
        )
        replay = journal.timed(
            "replay_load_and_run",
            lambda artifact=artifact: ReplayRunner.from_payload(artifact).run(),  # type: ignore[misc]
            **context,
        )
        if not replay.reproduced_exactly:
            raise ValueError("Replay diagnostic failed exact reproduction.")
        candidate_components(journal, prefixes, payload["rows"], context, REFERENCE_TRANSLATIONS)
    journal.append({"event": "worker_complete", "report_hash": expected_hash})


def candidate_components(
    journal: Journal,
    prefixes: Any,
    rows: Any,
    context: dict[str, Any],
    reference_translations: tuple[tuple[float, float], ...],
) -> None:
    from warhammer40k_core.ai.canonical_deployment_coverage import _finite_results
    from warhammer40k_core.ai.deployment_candidate_search import (
        DEFAULT_TRANSLATIONS,
        DeploymentCandidateSet,
    )
    from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
    from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
    from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet

    for index, (prefix, actor, action) in enumerate(prefixes):
        occurrence = {**context, "index": index}
        authoritative_row = rows[index]
        journal.timed("fresh_fork", prefix.fork, **occurrence)
        if action.option_id is not None:
            finite_candidates = journal.timed(
                "finite_generation",
                partial(FiniteCandidateSet.from_context, actor),
                **occurrence,
            )
            if finite_candidates.to_payload() != authoritative_row["candidate_set"]:
                raise ValueError("Component finite generation drifted from complete report.")
            reference_ids = tuple(option["option_id"] for option in actor.request["options"])
            # Invoke the coverage owner's exact fresh-fork finite procedure;
            # do not copy its submission/acceptance algorithm into the harness.
            results = journal.timed(
                "finite_fresh_fork_validation",
                partial(_finite_results, prefix, actor, reference_ids),
                candidate_count=len(reference_ids),
                **occurrence,
            )
            if results != authoritative_row["reference_results"]:
                raise ValueError("Component finite results drifted from complete report.")
        else:
            seed = DeploymentPlacementCandidate.from_action(action, context=actor)
            for role, translations, budget in (
                ("generated", None, len(DEFAULT_TRANSLATIONS)),
                ("reference", reference_translations, 10),
            ):
                parameters = generation_parameters(translations)
                candidates = journal.timed(
                    "placement_generation",
                    partial(
                        DeploymentCandidateSet.generate,
                        seed,
                        context=actor,
                        **parameters,
                    ),
                    role=role,
                    candidate_count=budget,
                    **occurrence,
                )
                validated = journal.timed(
                    "placement_fresh_fork_validation",
                    partial(
                        ValidatedDeploymentCandidates.validate,
                        candidates,
                        context=actor,
                        session=prefix,
                        validation_budget=budget,
                        accepted_limit=16,
                    ),
                    role=role,
                    candidate_count=budget,
                    **occurrence,
                )
                if validated.to_payload()["stop_reason"] != "complete":
                    raise ValueError("Component validation did not complete.")
                set_key = "candidate_set" if role == "generated" else "reference_set"
                result_key = "validation" if role == "generated" else "reference_validation"
                if (
                    candidates.to_payload() != authoritative_row[set_key]
                    or validated.to_payload() != authoritative_row[result_key]
                ):
                    raise ValueError("Component placement results drifted from complete report.")


def reference_suite_worker(output: Path, repeats: int, components: bool) -> None:
    journal = Journal(output / "attempts.jsonl")

    def imports() -> None:
        import warhammer40k_core.ai.deployment_reference_suite  # noqa: F401

    journal.timed("runtime_import", imports, phase="bootstrap")
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.ai.canonical_deployment import _recipe_prefixes
    from warhammer40k_core.ai.deployment_reference_suite import (
        REFERENCE_CASES,
        SUITE_REFERENCE_TRANSLATIONS,
        DeploymentReferenceSuite,
        reference_case_steps,
        reproduce_reference_case,
        require_reference_suite_definition,
    )
    from warhammer40k_core.ai.training_admission import VerifiedEpisodeOrigin
    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.replay import ReplayRunner

    write_json(output / "suite-definition.json", require_reference_suite_definition())
    expected_hash: str | None = None
    for repeat in range(repeats):
        context = {
            "repeat": repeat,
            "phase": "full_report",
            "process_state": "first_iteration" if repeat == 0 else "within_process_repeat",
        }
        report = journal.timed("suite_measure", DeploymentReferenceSuite.measure, **context)
        payload = journal.timed(
            "report_json_roundtrip", partial(json_roundtrip, report.to_payload()), **context
        )
        if repeat == 0:
            write_json(output / "suite-report.json", payload)
        loaded = journal.timed(
            "suite_from_payload", partial(DeploymentReferenceSuite.from_payload, payload), **context
        )
        if report.content_hash != loaded.content_hash:
            raise ValueError("Closed suite reproduction changed its report content hash.")
        if expected_hash is not None and expected_hash != report.content_hash:
            raise ValueError("Within-process suite identity drifted.")
        expected_hash = report.content_hash
        journal.append({"event": "verified_report", **context, "hash": expected_hash})
    if components:
        for case_index, (case_id, _) in enumerate(REFERENCE_CASES):
            context = {"phase": "prepared_component_pass", "repeat": 0, "case_id": case_id}
            session, recipe = journal.timed(
                "endpoint_reproduction", partial(reproduce_reference_case, case_id), **context
            )
            authoritative = payload["cases"][case_index]
            origin = journal.timed(
                "origin_admission",
                partial(
                    VerifiedEpisodeOrigin.from_session, session, config=session.lifecycle.config
                ),
                **context,
            )
            if origin.to_payload() != authoritative["origin"]:
                raise ValueError("Component origin drifted from the complete suite.")
            prefixes = journal.timed(
                "prefix_reconstruction",
                partial(_recipe_prefixes, session, recipe, steps=reference_case_steps(case_id)),
                **context,
            )
            checkpoint = journal.timed(
                "persistence_encode", session.to_persistence_payload, **context
            )
            checkpoint = journal.timed(
                "checkpoint_json_roundtrip", partial(json_roundtrip, checkpoint), **context
            )
            restored = journal.timed(
                "persistence_restore",
                partial(LocalGameSession.from_persistence_payload, checkpoint),
                **context,
            )
            if canonical_json(restored.to_persistence_payload()) != canonical_json(checkpoint):
                raise ValueError("Suite component persistence changed its checkpoint.")
            artifact = journal.timed(
                "replay_artifact",
                partial(session.replay_artifact, artifact_id="suite-component-costs"),
                **context,
            )
            replay = journal.timed(
                "replay_load_and_run",
                lambda artifact=artifact: ReplayRunner.from_payload(artifact).run(),  # type: ignore[misc]
                **context,
            )
            if not replay.reproduced_exactly:
                raise ValueError("Suite component replay failed exact reproduction.")
            candidate_components(
                journal, prefixes, authoritative["rows"], context, SUITE_REFERENCE_TRANSLATIONS
            )
    journal.append({"event": "worker_complete", "report_hash": expected_hash})


def read_journal(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.exists():
        return [], None
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
            return rows, line  # Preserve a killed worker's partial last write.
    return rows, None


def summarize(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[float]] = {}
    for attempt in attempts:
        for row in attempt["events"]:
            if row["event"] != "finish" or row["outcome"] != "passed":
                continue
            key = tuple(
                row.get(field)
                for field in ("phase", "process_state", "name", "index", "role", "case_id")
            )
            groups.setdefault(key, []).append(row["wall_seconds"])
    return [
        {
            **{
                field: value
                for field, value in zip(
                    ("phase", "process_state", "name", "index", "role", "case_id"), key, strict=True
                )
                if field != "case_id" or value is not None
            },
            "n": len(values),
            "mean_seconds": statistics.mean(values),
            "median_seconds": statistics.median(values),
            "min_seconds": min(values),
            "max_seconds": max(values),
            "empirical_p90_seconds": sorted(values)[math.ceil(0.90 * len(values)) - 1],
            "empirical_p95_seconds": sorted(values)[math.ceil(0.95 * len(values)) - 1],
            "sample_stdev_seconds": statistics.stdev(values) if len(values) > 1 else None,
        }
        for key, values in groups.items()
    ]


def environment(host_note: str) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()

    return {
        "utc": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "uname": list(platform.uname()),
        "python": sys.version,
        "executable": sys.executable,
        "cpu_count": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "cpuinfo": Path("/proc/cpuinfo").read_text(),
        "meminfo": Path("/proc/meminfo").read_text(),
        "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text()
        if Path("/sys/fs/cgroup/cpu.max").exists()
        else None,
        "cgroup_memory_max": Path("/sys/fs/cgroup/memory.max").read_text()
        if Path("/sys/fs/cgroup/memory.max").exists()
        else None,
        "host_note": host_note,
        "reference_hardware_qualification": "provisional-host-only",
        "dependencies": sorted(
            (dist.metadata["Name"], dist.version) for dist in importlib.metadata.distributions()
        ),
        "thread_environment": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "source_commit": git("rev-parse", "HEAD"),
        "source_tree": git("rev-parse", "HEAD^{tree}"),
        "git_status": git("status", "--porcelain"),
        "tracked_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=ROOT)
        ).hexdigest(),
        "harness_sha256": digest(Path(__file__)),
        "lock_sha256": digest(ROOT / "uv.lock"),
        "engine_manifest": json.loads(
            (ROOT / "src/warhammer40k_core/_engine_build_manifest.json").read_text()
        ),
    }


def process_cpu(pid: int) -> float:
    # /proc stat's comm can contain spaces/parentheses; fields after the final
    # ')' begin with field 3. utime/stime are fields 14/15, in clock ticks.
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def budget_reason(elapsed: float, cpu: float, wall_limit: float, cpu_limit: float) -> str | None:
    if elapsed >= wall_limit:
        return "campaign_wall_budget"
    if cpu >= cpu_limit:
        return "campaign_cpu_budget"
    return None


def supervise(
    command: list[str],
    directory: Path,
    campaign_start: float,
    used_cpu: float,
    wall_limit: float,
    cpu_limit: float,
) -> tuple[int, str | None]:
    """Bound a serial process group, preserving its logs even on interruption."""
    reason = None
    with (
        (directory / "stdout.log").open("w") as stdout,
        (directory / "stderr.log").open("w") as stderr,
    ):
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=stdout, stderr=stderr, start_new_session=True
        )
        try:
            while process.poll() is None:
                current_cpu = process_cpu(process.pid)
                reason = budget_reason(
                    time.monotonic() - campaign_start, used_cpu + current_cpu, wall_limit, cpu_limit
                )
                if reason:
                    os.killpg(process.pid, signal.SIGKILL)
                    break
                time.sleep(0.1)
            return process.wait(), reason
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait(), "operator_interrupt"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def campaign(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite a prior attempt.
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA,
        "command": [sys.executable, *sys.argv],
        "environment": environment(args.host_note),
        "settings": {
            "processes": args.processes,
            "repeats": args.repeats,
            "components": args.components,
            "workload": "reference-suite" if args.reference_suite else "canonical",
            "wall_budget_seconds": args.wall_seconds,
            "cpu_budget_seconds": args.cpu_seconds,
            "workers": 1,
            "coverage": False,
            "profiler": False,
            "cache_semantics": (
                "fresh-process-first-iteration-then-within-process-repeats; OS-cache-uncontrolled"
            ),
            "component_semantics": (
                "separate-prepared-pass-after-full-repeats; non-additive-inclusive-owner-costs"
            ),
        },
        "attempts": [],
        "status": "running",
        "uncertainty": (
            "descriptive finite samples; repeats clustered within process; "
            "no confidence or throughput claim"
        ),
    }
    write_json(output / "measurement.json", evidence)
    started = time.monotonic()
    initial_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    used_cpu = 0.0
    expected_hash: str | None = None
    for index in range(args.processes):
        reason = budget_reason(
            time.monotonic() - started, used_cpu, args.wall_seconds, args.cpu_seconds
        )
        if reason:
            evidence["status"] = reason
            break
        directory = output / f"process-{index:02d}"
        directory.mkdir()
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            str(directory),
            "--repeats",
            str(args.repeats),
        ]
        if args.components:
            command.append("--components")
        if args.reference_suite:
            command.append("--reference-suite")
        attempt_start = time.monotonic()
        # The worker starts a fresh interpreter. Output and failures are retained
        # verbatim, even if a runtime error precedes its first journal record.
        returncode, reason = supervise(
            command, directory, started, used_cpu, args.wall_seconds, args.cpu_seconds
        )
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        total_cpu = usage.ru_utime + usage.ru_stime - initial_cpu.ru_utime - initial_cpu.ru_stime
        events, partial = read_journal(directory / "attempts.jsonl")
        attempt = {
            "index": index,
            "command": command,
            "returncode": returncode,
            "wall_seconds": time.monotonic() - attempt_start,
            "cpu_seconds": total_cpu - used_cpu,
            "stop_reason": reason,
            "events": events,
            "partial_journal_line": partial,
            "stdout": (directory / "stdout.log").read_text(),
            "stderr": (directory / "stderr.log").read_text(),
        }
        evidence["attempts"].append(attempt)
        used_cpu = total_cpu
        hashes = [row["hash"] for row in events if row["event"] == "verified_report"]
        if expected_hash is None and hashes:
            expected_hash = hashes[0]
        identity_ok = all(value == expected_hash for value in hashes)
        complete = bool(events) and events[-1]["event"] == "worker_complete"
        evidence["status"] = reason or (
            "worker_failure"
            if returncode or not complete
            else "report_identity_failure"
            if not identity_ok
            else "running"
        )
        evidence["report_hash"] = expected_hash
        evidence["summary"] = summarize(evidence["attempts"])
        evidence["elapsed_wall_seconds"] = time.monotonic() - started
        evidence["child_cpu_seconds"] = used_cpu
        write_json(output / "measurement.json", evidence)
        if evidence["status"] != "running":
            break
    if evidence["status"] == "running":
        evidence["status"] = "complete"
    evidence["elapsed_wall_seconds"] = time.monotonic() - started
    evidence["child_cpu_seconds"] = used_cpu
    write_json(output / "measurement.json", evidence)
    print(json.dumps({"status": evidence["status"], "output": str(output)}))
    return 0 if evidence["status"] == "complete" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path)
    result.add_argument(
        "--host-note", default="Host hardware outside Linux guest not independently verified."
    )
    result.add_argument("--processes", type=int, default=3)
    result.add_argument("--repeats", type=int, default=2)
    result.add_argument("--components", action="store_true")
    result.add_argument("--reference-suite", action="store_true")
    result.add_argument("--wall-seconds", type=float, default=3600)
    result.add_argument("--cpu-seconds", type=float, default=7200)
    result.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    return result


def main() -> int:
    arguments = parser()
    args = arguments.parse_args()
    if args.processes < 1 or args.repeats < 1:
        arguments.error("processes and repeats must be positive")
    if not (
        math.isfinite(args.wall_seconds)
        and args.wall_seconds > 0
        and math.isfinite(args.cpu_seconds)
        and 0 < args.cpu_seconds <= MAX_CPU_SECONDS
    ):
        arguments.error("positive finite budgets required; CPU ceiling is eight hours")
    if args.worker:
        worker(args.worker, args.repeats, args.components, args.reference_suite)
        return 0
    if args.output is None:
        arguments.error("--output is required")
    if sys.gettrace() is not None or sys.getprofile() is not None:
        arguments.error("run without coverage, tracing or profiling")
    return campaign(args)


if __name__ == "__main__":
    raise SystemExit(main())
