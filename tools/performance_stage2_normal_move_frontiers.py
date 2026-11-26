"""Measure the five frozen S/E movement probes without replaying the scoring protocol."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import dataclass
from hashlib import sha256
from math import isclose
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any, cast
from unittest.mock import patch

import orjson

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction
from warhammer40k_core.ai.screen_movement_candidates import (
    MAX_NORMAL_MOVE_PROPOSALS,
    generate_normal_move_proposals,
)
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases import movement_rules_units
from warhammer40k_core.engine.phases.movement_state import NormalMoveResolution
from warhammer40k_core.geometry.pathing import PathWitness

_REPEATS = 3
_VIEWER = ViewerContext.for_player("player-a")
_PREDICATE = (
    "test-only fixed witness predicates: pure -Y S and pure +Y E, each at three quarters "
    "of the shortest visible Move; exactly one generated match per offer; no retry or score input"
)


@dataclass(frozen=True)
class _Frontier:
    name: str
    role: str
    checkpoint: str
    ledger: str
    offer_tags: tuple[str, ...]
    selected_tag: str


_FRONTIERS = (
    _Frontier(
        "S early A4",
        "S",
        "common-A4-S-choice",
        "screen_e_score",
        ("screen:A4:screen:normal",),
        "screen:A4:screen:witness",
    ),
    _Frontier(
        "S late A5",
        "S",
        "hold-A5-entry",
        "late_screen_e_score",
        ("late:A5:S:unit", "late:A5:S:late-screen:normal"),
        "late:A5:S:late-screen:witness",
    ),
    _Frontier(
        "E A5 after S held",
        "E",
        "hold-E-choice",
        "hold_e_score",
        ("hold_e_score:A5:E:score:normal",),
        "hold_e_score:A5:E:score:witness",
    ),
    _Frontier(
        "E A5 after early S",
        "E",
        "screen-E-choice",
        "screen_e_score",
        ("screen_e_score:A5:E:score:normal",),
        "screen_e_score:A5:E:score:witness",
    ),
    _Frontier(
        "E A5 after late S",
        "E",
        "late-E-choice",
        "late_screen_e_score",
        ("late_screen_e_score:A5:E:score:normal",),
        "late_screen_e_score:A5:E:score:witness",
    ),
)


def _raw(folder: Path, name: str) -> bytes:
    return (folder / (name + ".json")).read_bytes()


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view_for_context(viewer=_VIEWER), choice_seed=0)


def _prepare(folder: Path, frontier: _Frontier) -> tuple[bytes, dict[str, Any], str]:
    original = _raw(folder, frontier.checkpoint + "-checkpoint")
    session = LocalGameSession.from_persistence_payload(orjson.loads(original))
    ledger: list[dict[str, Any]] = orjson.loads(_raw(folder, frontier.ledger + "-ledger"))
    rows = {row["result"]: row for row in ledger}
    assert len(rows) == len(ledger)
    for tag in frontier.offer_tags:
        recorded = rows[tag]
        context = _context(session)
        assert context.request["request_id"] == recorded["viewer_request"]
        assert context.request["decision_type"] == recorded["decision_kind"]
        action = FiniteCandidateSet.from_context(context).select(context, recorded["option"])
        assert action.option_id is not None
        status = session.submit_viewer_option(
            viewer=_VIEWER,
            request_id=action.request_id,
            option_id=action.option_id,
            result_id=tag,
        )
        assert status.status_kind.value == recorded["native_status"]
    return (
        orjson.dumps(session.to_persistence_payload()),
        rows[frontier.selected_tag],
        _digest(original),
    )


def _path_offsets(witness: PathWitness) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple(
            (pose.position.x - path[0].position.x, pose.position.y - path[0].position.y)
            for pose in path
        )
        for _, path in witness.model_paths
    )


def _xy_matches(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return all(isclose(x, y, abs_tol=1e-8) for x, y in zip(a, b, strict=True))


def _find_matches(
    raw: tuple[PolicyAction, ...],
    expected: tuple[float, float],
    original: tuple[tuple[float, float], ...],
    unit_id: str,
) -> tuple[JsonValue, int, int]:
    candidate_count = 0
    authored_count = 0
    selected: JsonValue = None
    for candidate in raw:
        assert candidate.proposal_json is not None
        parsed = orjson.loads(candidate.proposal_json)
        move = MovementProposalPayload.from_payload(parsed)
        assert move.unit_instance_id == unit_id
        offsets = _path_offsets(move.witness)
        if all(_xy_matches(paths[-1], expected) for paths in offsets):
            candidate_count += 1
            selected = cast(JsonValue, parsed)
        if all(
            len(path) == len(original)
            and all(_xy_matches(a, b) for a, b in zip(path, original, strict=True))
            for path in offsets
        ):
            authored_count += 1
    assert selected is not None
    assert candidate_count == 1
    return selected, candidate_count, authored_count


def _native(
    session: LocalGameSession,
    picked: JsonValue,
    row: dict[str, Any],
) -> tuple[float, float, str]:
    original = movement_rules_units.resolve_rules_unit_normal_move
    times: list[int] = []
    valid: list[bool] = []

    def measured(*args: Any, **kwargs: Any) -> NormalMoveResolution:
        start = perf_counter_ns()
        result = original(*args, **kwargs)
        times.append(perf_counter_ns() - start)
        valid.append(result.is_valid)
        return result

    events_before = session.event_record_count()
    with patch.object(movement_rules_units, "resolve_rules_unit_normal_move", measured):
        start = perf_counter_ns()
        status = session.submit_viewer_parameterized_payload(
            viewer=_VIEWER,
            request_id=row["viewer_request"],
            result_id=row["result"],
            payload=picked,
        )
        elapsed = perf_counter_ns() - start
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert valid == [True]
    (resolve_elapsed,) = times
    events = session.lifecycle.decision_controller.event_log.records[events_before:]
    assert [event.event_id for event in events] == row["new_event_ids"]
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert [pending.request_id, pending.actor_id, pending.decision_type] == row["next"]
    checkpoint = session.to_persistence_payload()
    assert isinstance(checkpoint, dict)
    event_digest = checkpoint["event_log_hash"]
    assert isinstance(event_digest, str)
    return resolve_elapsed / 1e9, elapsed / 1e9, event_digest


def _summary(values: list[float]) -> dict[str, object]:
    return {"samples": values, "median": median(values), "range": [min(values), max(values)]}


def _measure(frontier: _Frontier, folder: Path, authored: dict[str, Any]) -> dict[str, object]:
    origin, row, checkpoint_hash = _prepare(folder, frontier)
    witness = row["proposal"]["witness"]
    unit_id = row["proposal"]["unit_instance_id"]
    original = tuple(tuple(float(x) for x in point) for point in authored[unit_id])
    authored_offsets = tuple((x, y) for x, y in original)
    generation: list[float] = []
    validation: list[float] = []
    submission: list[float] = []
    event_hashes: set[str] = set()
    match_signatures: set[tuple[int, int, tuple[float, float]]] = set()
    for _ in range(_REPEATS):
        session = LocalGameSession.from_persistence_payload(orjson.loads(origin))
        context = _context(session)
        assert context.request["request_id"] == row["viewer_request"]
        assert context.route.proposal_kind == "normal_move"
        view = context.observation
        table = view["battlefield_view"]
        assert table is not None
        movers = [
            model_id
            for model_id, placement in table["authoritative"]["models_by_id"].items()
            if placement["rules_unit_instance_id"] == unit_id and placement["state"] == "placed"
        ]
        moves = [
            view["model_display_by_id"][model]["current_characteristics"]["M"]["final"]
            for model in movers
        ]
        shortest = min(value for value in moves if value is not None)
        expected = (0.0, (0.75 if frontier.role == "E" else -0.75) * shortest)
        t0 = perf_counter_ns()
        raw = generate_normal_move_proposals(context)
        generation.append((perf_counter_ns() - t0) / 1e9)
        assert len(raw) == row["generated_candidate_count"] == MAX_NORMAL_MOVE_PROPOSALS
        picked, equivalent, exact = _find_matches(raw, expected, authored_offsets, unit_id)
        assert picked == row["proposal"]
        assert exact == 0
        assert equivalent == 1
        match_signatures.add((exact, equivalent, expected))
        resolver_time, submit_time, event_hash = _native(session, picked, row)
        validation.append(resolver_time)
        submission.append(submit_time)
        event_hashes.add(event_hash)
    (native_event_hash,) = event_hashes
    ((exact, equivalent, expected),) = match_signatures
    return {
        "frontier": frontier.name,
        "role": frontier.role,
        "archived_native_request": row["native_request"],
        "viewer_request": row["viewer_request"],
        "archive_start_checkpoint": frontier.checkpoint,
        "archive_start_checkpoint_sha256": checkpoint_hash,
        "proposal_checkpoint_sha256": _digest(origin),
        "authored_relative_xy_waypoints_inches": authored_offsets,
        "exact_authored_waypoint_matches": exact,
        "selected_equivalent_relative_xy_endpoint_inches": expected,
        "predeclared_equivalent_matches": equivalent,
        "generated_candidates": MAX_NORMAL_MOVE_PROPOSALS,
        "selected_witness_sha256": _digest(_canonical(witness)),
        "accepted_native_probe_event_log_hash": native_event_hash,
        "accepted_samples": _REPEATS,
        "generation_wall_seconds": _summary(generation),
        "native_resolution_wall_seconds": _summary(validation),
        "native_submission_including_resolution_wall_seconds": _summary(submission),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "generated", type=Path, help="Retained generated-run checkpoint and ledger directory"
    )
    parser.add_argument("authored", type=Path, help="Retained authored reference directory")
    parser.add_argument(
        "receipt", type=Path, help="Repository's immutable generated timing/scoring receipt"
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    receipt_raw = args.receipt.read_bytes()
    receipt = json.loads(receipt_raw)
    protocol_raw = _raw(args.generated, "protocol")
    protocol = orjson.loads(protocol_raw)
    authored_raw = _raw(args.authored, "protocol")
    runtime = verified_engine_build_identity().build_id
    assert _digest(authored_raw) == receipt["locked_authored_reference"]["protocol_sha256"]
    assert (
        _digest(orjson.dumps(protocol, option=orjson.OPT_SORT_KEYS))
        == receipt["generated_protocol_digest"]
    )
    assert _digest(_raw(args.generated, "result")) == receipt["generated_result_sha256"]
    assert protocol["actions"]["S_E_rule"] == _PREDICATE
    assert protocol["expected_build"] == runtime
    authored = orjson.loads(authored_raw)["actions"]["paths_xy_from_each_own_model_start"]
    records: list[dict[str, object]] = []
    for frontier in _FRONTIERS:
        record = _measure(frontier, args.generated, authored)
        records.append(record)
        print(frontier.name, json.dumps(record, sort_keys=True), flush=True)
    output = {
        "schema": "stage2-normal-move-frontier-probes-v1",
        "runtime": runtime,
        "python": sys.version,
        "platform": platform.platform(),
        "scoring_receipt_sha256": _digest(receipt_raw),
        "authored_protocol_sha256": _digest(authored_raw),
        "generated_protocol_digest": receipt["generated_protocol_digest"],
        "driver_sha256": _digest(Path(__file__).read_bytes()),
        "samples_per_frontier": _REPEATS,
        "serial": True,
        "predeclared_equivalent_predicate": _PREDICATE,
        "native_proposals_validated_per_sample": 1,
        "timing_boundaries": {
            "generation_wall_seconds": (
                "generate_normal_move_proposals on a ready actor context; excludes restore, view "
                "construction, predicate matching and all native submission"
            ),
            "native_resolution_wall_seconds": (
                "resolve_rules_unit_normal_move inside ordinary submission: grouped geometry, "
                "path and rule resolution only; excludes the facade and commit/events"
            ),
            "native_submission_including_resolution_wall_seconds": (
                "submit_viewer_parameterized_payload: actor binding, native resolution, "
                "apply, events and next request; excludes preparation and post-timing checks"
            ),
        },
        "frontiers": records,
        "scope": (
            "One preserved matched witness per sample, fresh restore each time. No timing of other "
            "witnesses, no opponent actions, no resampling or scoring continuation."
        ),
    }
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
