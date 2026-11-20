"""Measure and verify the fixed native Cavalcade mirror from setup to game completion."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from tests.support.cavalcade_v995 import strict_mirror_session
from tools.performance_policy import (
    MAP,
    POLICY,
    canonical_digest,
    digest,
    git,
    object_value,
    read_object,
    runtime_inputs,
    validate_full_game,
)

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleStage, LifecycleStatusKind

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import EventRecord

ROOT = Path(__file__).resolve().parents[1]
DRIVER = "scripts/measure_cavalcade_full_game.py"
WORKLOAD_ID = "cavalcade-v995-setup-to-complete-v1"
MODULE = DRIVER.removesuffix(".py").replace("/", ".")
PLAYERS = ("player-a", "player-b")


class WorkloadError(ValueError):
    """The live game or evidence diverged from the versioned workload."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkloadError(message)


def _write(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _load_workload() -> tuple[str, dict[str, object]]:
    profiles = object_value(read_object(ROOT / MAP)["full_game_profiles"])
    registration = object_value(profiles[DRIVER])
    fixture = registration["fixture"]
    if not isinstance(fixture, str):
        raise WorkloadError("Cavalcade registration requires a fixture path.")
    workload = read_object(ROOT / fixture)
    _require(
        registration["workload_id"] == WORKLOAD_ID == workload["workload_id"],
        "Cavalcade workload ID drifted.",
    )
    setup = object_value(workload["setup"])
    roster_path = setup["roster_path"]
    if not isinstance(roster_path, str):
        raise WorkloadError("Cavalcade requires the canonical roster path.")
    _require(
        digest((ROOT / roster_path).read_bytes()) == setup["roster_sha256"],
        "The canonical roster file drifted.",
    )
    return fixture, workload


def _play(workload: dict[str, object]) -> LocalGameSession:
    setup = object_value(workload["setup"])
    seed_byte = setup["private_seed_byte"]
    if type(seed_byte) is not int or not 0 <= seed_byte <= 255:
        raise WorkloadError("The frozen private seed byte is invalid.")
    actions = validate_json_value(workload["actions"])
    if not isinstance(actions, list):
        raise WorkloadError("The frozen actions must be an ordered list.")
    session = strict_mirror_session(private_rng_seed=bytes([seed_byte] * 32).hex())
    _require(
        session.lifecycle.state is not None
        and session.lifecycle.state.stage is GameLifecycleStage.SETUP
        and session.decision_record_count() == 0,
        "The workload must start at ordinary setup before any player decisions.",
    )
    for value in actions:
        action = object_value(value)
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        index = session.decision_record_count()
        if request is None or status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
            raise WorkloadError(
                f"Action {index} requires a pending decision: {status.status_kind}."
            )
        _require(
            (index, request.request_id, request.decision_type, request.actor_id)
            == (
                action["record_index"],
                action["request_id"],
                action["decision_type"],
                action["actor_id"],
            ),
            f"Live decision {index} drifted: {request.request_id}/{request.decision_type}.",
        )
        result_id = action["result_id"]
        if not isinstance(result_id, str):
            raise WorkloadError(f"Action {index} requires a result ID.")
        _require(
            ("proposal" in action) == request.is_parameterized_submission_request()
            and ("proposal" in action) != ("option_id" in action),
            f"Action {index} must match the issued request's submission form.",
        )
        if "proposal" in action:
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=validate_json_value(action["proposal"]),
                result_id=result_id,
            )
        else:
            option_id = action["option_id"]
            if not isinstance(option_id, str):
                raise WorkloadError(f"Action {index} requires an option ID.")
            status = session.submit_option(
                request_id=request.request_id, option_id=option_id, result_id=result_id
            )
        if "expected_rejection" in action:
            payload = object_value(status.payload)
            _require(
                status.status_kind is LifecycleStatusKind.INVALID
                and payload.get("violation_code") == action["expected_rejection"],
                f"Action {index} did not reproduce its recorded rule rejection: {status.message}.",
            )
        else:
            _require(
                status.status_kind
                not in (LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED),
                f"Action {index} failed: {status.status_kind} {status.message}.",
            )
        _require(session.decision_record_count() > index, f"Action {index} was not recorded.")

    status = session.advance_until_decision_or_terminal()
    _require(
        status.status_kind is LifecycleStatusKind.TERMINAL
        and status.stage is GameLifecycleStage.COMPLETE
        and session.lifecycle.pending_decision_request() is None,
        f"The action trace did not reach ordinary completion: {status.status_kind}.",
    )
    return session


def _completed_phases(
    events: tuple[EventRecord, ...],
) -> list[tuple[object, object, object]]:
    completed: list[tuple[object, object, object]] = []
    for event in events:
        if event.event_type == "fight_phase_completed":
            # The generic Fight boundary carries the incoming turn's player and round.
            payload = object_value(event.payload)
            completed.append(
                (payload["battle_round"], payload["active_player_id"], payload["phase"])
            )
        elif event.event_type == "battle_phase_completed":
            payload = object_value(event.payload)
            if payload["completed_phase"] != "fight":
                completed.append(
                    (
                        payload["battle_round"],
                        payload["active_player_id"],
                        payload["completed_phase"],
                    )
                )
    return completed


def _terminal_evidence(
    session: LocalGameSession, workload: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    from warhammer40k_core.engine.phase import BattlePhase

    expected = object_value(workload["expected"])
    setup = object_value(workload["setup"])
    state = session.lifecycle.state
    if state is None or state.stage is not GameLifecycleStage.COMPLETE:
        raise WorkloadError("Expected a completed game.")
    checkpoint = object_value(session.to_persistence_payload())
    events = session.lifecycle.decision_controller.event_log.records
    if not events:
        raise WorkloadError("A completed game requires a terminal event.")
    terminal_event = events[-1]
    rounds = expected["battle_rounds"]
    if type(rounds) is not int:
        raise WorkloadError("The expected battle round count must be an integer.")
    _require(
        _completed_phases(events)
        == [
            (round_id, player, phase.value)
            for round_id in range(1, rounds + 1)
            for player in PLAYERS
            for phase in BattlePhase
        ],
        "The completed phase sequence drifted.",
    )
    result = object_value(state.game_result_payload())
    _require(
        len(events) == expected["event_count"]
        and terminal_event.event_type == "game_completed"
        and terminal_event.payload == result
        and session.decision_record_count() == expected["decision_count"]
        and result["final_scores"] == expected["final_scores"]
        and canonical_digest(result) == expected["game_result_sha256"],
        "The terminal decision count, event ledger, or game result drifted.",
    )
    for key in ("lifecycle", "decision_records", "event_log", "rng_state"):
        _require(checkpoint[f"{key}_hash"] == expected[f"{key}_sha256"], f"{key} drifted.")
    _require(
        canonical_digest(checkpoint["source_identity"]) == setup["source_identity_sha256"],
        "The canonical game configuration drifted.",
    )
    return checkpoint, {
        "decision_count": session.decision_record_count(),
        "event_count": len(events),
        "final_event_id": terminal_event.event_id,
        "lifecycle_sha256": checkpoint["lifecycle_hash"],
        "checkpoint_content_sha256": checkpoint["content_hash"],
        "event_log_sha256": checkpoint["event_log_hash"],
        "result": result,
    }


def _sample(output: Path, launch_time: float) -> None:
    _, workload = _load_workload()
    started = time.monotonic()
    session = _play(workload)
    elapsed = time.monotonic() - started
    _write(
        output / "timing.json",
        {
            "startup_seconds": started - launch_time,
            "initialization_through_completion_seconds": elapsed,
        },
    )
    checkpoint, terminal = _terminal_evidence(session, workload)
    _write(output / "checkpoint.json", checkpoint)
    _write(output / "terminal.json", terminal)


def _measure(output: Path, sample_count: int, timeout: int, base: str) -> int:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    fixture, workload = _load_workload()
    _require(not git(ROOT, "status", "--porcelain"), "Measure from a clean checkout.")
    inputs = runtime_inputs(ROOT)
    setup = object_value(workload["setup"])
    base_sha = git(ROOT, "rev-parse", "--verify", f"{base}^{{commit}}").decode().strip()
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    git(ROOT, "merge-base", "--is-ancestor", base_sha, head)
    cpu = next(
        row.split(":", 1)[1].strip()
        for row in Path("/proc/cpuinfo").read_text().splitlines()
        if row.startswith("model name")
    )
    samples: list[dict[str, object]] = []
    seconds: list[float] = []
    startup_seconds: list[float] = []
    report: dict[str, object] = {
        "schema": "cavalcade-full-game-measurement-v1",
        "policy": POLICY,
        "driver": DRIVER,
        "supported_driver": True,
        "decision_policy": WORKLOAD_ID,
        "base_revision": base_sha,
        "head_revision": head,
        "runtime_build_id": verified_engine_build_identity().build_id,
        "head_input_digest": canonical_digest(inputs),
        "workload_sha256": inputs[DRIVER],
        "fixture_sha256": inputs[fixture],
        "fixture_origin": workload["source"],
        "lock_sha256": inputs["uv.lock"],
        "host": {
            "cpu": cpu,
            "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
            "logical_cpus": len(os.sched_getaffinity(0)),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "role": "provisional",
        },
        "dependencies": {name: version(name) for name in ("numpy", "shapely", "z3-solver")},
        "concurrency": 1,
        "time_limit_seconds": timeout,
        "seeds": [setup["private_seed_byte"]] * sample_count,
        "rosters": [
            {
                key: setup[key]
                for key in (
                    "army_points_per_player",
                    "models_per_player",
                    "units_per_player",
                    "roster_path",
                    "roster_sha256",
                )
            }
        ]
        * sample_count,
        "terrain": [{key: setup[key] for key in ("terrain_layout_id", "terrain_feature_count")}]
        * sample_count,
        "requested_samples": sample_count,
        "samples": samples,
        "normal_completion": False,
        "initialization_through_completion_seconds": seconds,
        "startup_seconds": startup_seconds,
        "qualification": "incomplete",
    }
    output.mkdir()
    _write(output / "measurement.json", report)
    for index in range(sample_count):
        dest = output / f"sample-{index + 1:03d}"
        dest.mkdir()
        started = time.monotonic()
        row: dict[str, object] = {"sample": index + 1}
        with (dest / "process.log").open("wb") as log:
            try:
                process = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        MODULE,
                        "_sample",
                        str(dest),
                        str(started),
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
                row.update(
                    exit_code=process.returncode,
                    status="completed" if process.returncode == 0 else "failed",
                )
            except subprocess.TimeoutExpired:
                row["status"] = "timeout"
        row["process_seconds"] = time.monotonic() - started
        if (dest / "timing.json").is_file():
            timing = read_object(dest / "timing.json")
            row.update(timing)
            if row["status"] == "completed":
                seconds.append(float(str(timing["initialization_through_completion_seconds"])))
                startup_seconds.append(float(str(timing["startup_seconds"])))
                row["terminal"] = read_object(dest / "terminal.json")
        samples.append(row)
        _write(output / "measurement.json", report)

    report["normal_completion"] = len(seconds) == sample_count
    report["completion_rate"] = len(seconds) / sample_count
    process_seconds = sum(float(str(sample["process_seconds"])) for sample in samples)
    report["completed_games_per_process_hour"] = len(seconds) * 3600 / process_seconds
    if seconds:
        ordered = sorted(seconds)
        report["completed_game_seconds"] = {
            "mean": statistics.mean(ordered),
            "median": statistics.median(ordered),
            "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
            "max": ordered[-1],
        }
        report["mean_below_60_seconds"] = statistics.mean(ordered) < 60
        report["observed_max_at_most_300_seconds"] = ordered[-1] <= 300
    _require(
        inputs == runtime_inputs(ROOT)
        and head == git(ROOT, "rev-parse", "HEAD").decode().strip()
        and not git(ROOT, "status", "--porcelain"),
        "Measurement inputs changed during sampling.",
    )
    try:
        validate_full_game(
            report,
            base=base_sha,
            runtime_id=str(report["runtime_build_id"]),
            input_digest=str(report["head_input_digest"]),
            workload_sha256=inputs[DRIVER],
        )
    except ValueError as exc:
        report["qualification"] = str(exc)
    else:
        report["qualification"] = "observed thresholds passed on provisional hardware"
    _write(output / "measurement.json", report)
    return 0 if report["normal_completion"] else 1


def _verify(checkpoint_path: Path, output: Path) -> None:
    from tests.support.cavalcade_native_fight import view_evidence

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import (
        ReplayProjectionCheckpoint,
        ReplayProjectionSnapshot,
        ReplayRunner,
    )

    _, workload = _load_workload()
    expected = object_value(workload["expected"])
    checkpoint = validate_json_value(read_object(checkpoint_path))
    session = LocalGameSession.from_persistence_payload(checkpoint)
    _require(session.to_persistence_payload() == checkpoint, "The public restore drifted.")
    _, terminal = _terminal_evidence(session, workload)
    artifact = session.replay_artifact(artifact_id=WORKLOAD_ID)
    origin = object_value(artifact["initial_lifecycle"])
    origin_state = object_value(origin["state"])
    _require(
        origin_state["stage"] == "setup"
        and origin_state["battle_round"] == 0
        and object_value(origin["decisions"])["records"] == [],
        "Replay must originate from ordinary setup before any decisions.",
    )
    count = session.decision_record_count()
    checkpoints: list[ReplayProjectionCheckpoint] = []
    for player in PLAYERS:
        view = session.view(viewer_player_id=player)
        checkpoints.append(
            ReplayProjectionCheckpoint.from_lifecycle(
                lifecycle=session.lifecycle,
                checkpoint_id=f"terminal:{player}",
                decision_record_index=count,
                viewer_player_id=player,
                projection_schema=view["projection_schema"],
                projection_state_hash=view["projection_state_hash"],
            )
        )
    artifact["projection_checkpoints"] = [checkpoint.to_payload() for checkpoint in checkpoints]

    def projection(
        lifecycle: GameLifecycle, boundary: ReplayProjectionCheckpoint
    ) -> ReplayProjectionSnapshot:
        player = boundary.viewer_player_id
        projected = view_evidence(LocalGameSession(lifecycle=lifecycle), player)
        _require(
            canonical_digest(projected) == object_value(expected["viewer_sha256"])[player]
            and canonical_digest(lifecycle.to_payload()) == expected["lifecycle_sha256"],
            f"Replay terminal lifecycle or viewer stream drifted for {player}.",
        )
        view = object_value(object_value(projected)["view"])
        return ReplayProjectionSnapshot(
            player, str(view["projection_schema"]), str(view["projection_state_hash"])
        )

    for checkpoint_view in checkpoints:
        projection(session.lifecycle, checkpoint_view)
    _write(output / "restore.json", {**terminal, "both_viewers_and_event_streams_matched": True})
    replay = ReplayRunner.from_payload(artifact, projection_provider=projection).run()
    _write(output / "replay.json", replay.to_payload())
    _require(replay.reproduced_exactly, f"Setup-to-terminal replay drifted: {replay.diagnostics}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", metavar="{measure,verify}", required=True)
    measure = subparsers.add_parser(
        "measure", help="Measure serial fresh-process in-process games."
    )
    measure.add_argument("output", type=Path)
    measure.add_argument("--base", required=True)
    measure.add_argument("--samples", type=int, default=1)
    measure.add_argument("--timeout", type=int, default=3600)
    verify = subparsers.add_parser(
        "verify", help="Strictly restore and replay one terminal checkpoint."
    )
    verify.add_argument("checkpoint", type=Path)
    verify.add_argument("output", type=Path)
    sample = subparsers.add_parser("_sample")
    sample.add_argument("output", type=Path)
    sample.add_argument("launch_time", type=float)
    args = parser.parse_args()
    if args.command == "measure":
        if args.samples < 1 or args.timeout < 1:
            parser.error("Sample count and timeout must be positive.")
        return _measure(args.output.resolve(), args.samples, args.timeout, args.base)
    if args.command == "verify":
        args.output.mkdir()
        _verify(args.checkpoint, args.output)
    else:
        _sample(args.output, args.launch_time)
    return 0


if __name__ == "__main__":
    sys.exit(main())
