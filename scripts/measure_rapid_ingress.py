"""Order 35: bounded reserve queries and real target submission (no geometry redesign)."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from pathlib import Path
from types import CodeType

from tests.rapid_ingress_helpers import (
    ingress_context,
    ingress_placement,
    ingress_session,
    reach_ingress_window,
    submit_ingress_target,
)

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems_eligibility import _enumerated_target_bindings
from warhammer40k_core.engine.stratagems_selection import _stratagem_unavailable_reason

ROOT = Path(__file__).resolve().parents[1]
CASES = ("legal", "first_round", "aircraft", "mixed", "placement")
WORK_METRICS = frozenset(
    {
        "unarrived_reserve_states_for_player",
        "rules_unit_view_by_id",
        "resolve_reserve_arrival",
        "resolve_visibility_pair",
        "_rapid_ingress_unit_ids",
        "rapid_ingress_target_error",
    }
)


def sample(*, case: str, profile: bool = False) -> dict[str, object]:
    if case not in CASES:
        raise ValueError("Unknown Rapid Ingress workload")
    started = time.perf_counter()
    inventory = (
        ("AIRCRAFT", "INFANTRY") * 8
        if case == "mixed"
        else ("AIRCRAFT",)
        if case == "aircraft"
        else ("INFANTRY",)
    )
    session = ingress_session(battle_round=1 if case == "first_round" else 2, inventory=inventory)
    state = session.lifecycle.state
    assert state is not None
    context = ingress_context(session)
    record = next(
        r
        for r in eleventh_edition_core_stratagem_index().records_for(context.trigger_kind)
        if r.definition.handler_id == "core:rapid-ingress"
    )
    profiler = cProfile.Profile()
    prepared = time.perf_counter()
    if profile:
        profiler.enable()
    reason = _stratagem_unavailable_reason(
        state=state, record=record, context=context, target_binding=None
    )
    bindings = _enumerated_target_bindings(
        state=state, player_id=context.player_id, definition=record.definition, context=context
    )
    submitted = False
    status = None
    if case in {"legal", "mixed", "placement"}:
        request = reach_ingress_window(session)
        status = submit_ingress_target(
            session,
            request,
            target="army-beta:reserve-1" if case == "mixed" else "army-beta:reserve-0",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
        assert status.decision_request is not None
        assert status.decision_request.decision_type == "submit_placement_proposal"
        submitted = True
        if case == "placement":
            placement_request = status.decision_request
            status = session.submit_parameterized_payload(
                request_id=placement_request.request_id,
                result_id="order35:benchmark-placement",
                payload=validate_json_value(
                    ingress_placement(session, placement_request).to_payload()
                ),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            assert session.lifecycle.reaction_queue.frames == ()
    if profile:
        profiler.disable()
    ended = time.perf_counter()
    counts: dict[str, int] = {}
    if profile:
        for entry in profiler.getstats():
            if isinstance(entry.code, CodeType) and entry.code.co_name in WORK_METRICS:
                counts[entry.code.co_name] = counts.get(entry.code.co_name, 0) + entry.callcount
    return {
        "case": case,
        "setup_seconds": prepared - started,
        "slice_seconds": ended - prepared,
        "inventory_size": len(inventory),
        "eligible_targets": len(bindings),
        "unavailable_reason": reason,
        "submitted": submitted,
        "work_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--work-counts", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = [
        sample(case=case, profile=args.work_counts) for case in CASES for _ in range(args.samples)
    ]
    summaries = {}
    for case in CASES:
        values = sorted(float(str(r["slice_seconds"])) for r in rows if r["case"] == case)
        summaries[case] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": values[math.ceil(0.95 * len(values)) - 1],
            "max": max(values),
            "samples": len(values),
            "completion_rate": 1.0,
            "slices_per_second": 1 / statistics.mean(values),
        }
    inputs = (
        "uv.lock",
        "scripts/measure_rapid_ingress.py",
        "tests/rapid_ingress_helpers.py",
        "tests/core_stratagem_helpers.py",
        "tests/setup_completion_helpers.py",
        "tests/unit_keyword_helpers.py",
        "tests/psychic_modifier_helpers.py",
    )
    report = {
        "workload_id": "order35-rapid-ingress-v2",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"])
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "mode": "profile" if args.work_counts else "uninstrumented_timing",
        "hardware_status": "provisional; one process, no concurrent test workers",
        "timing_boundary": (
            "setup separate; availability, target enumeration; legal Movement-end "
            "facade target submission; placement case also completes placement and parent resume"
        ),
        "terrain_shapes": 0,
        "models_per_unit": 5,
        "decision_policy": "remain stationary; select legal reserve target",
        "hashes": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
        "summaries": summaries,
        "samples": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "summaries": summaries}))


if __name__ == "__main__":
    main()
