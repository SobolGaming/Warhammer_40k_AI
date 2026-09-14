"""Order 48 complete facade slices; new-capability evidence separate from matched Charge costs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

from tests.crushing_impact_helpers import complete_charge, crushing_session

from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    scenarios = []
    for name, attached, toughness, wounds, fnp in (
        ("ordinary", False, 4, 2, False),
        ("both_caps_and_feel_no_pain", False, 96, 20, True),
        ("both_attached_units_destroyed", True, 96, 1, False),
    ):
        rows = []
        for _ in range(args.samples):
            start = time.perf_counter()
            session = crushing_session(
                attached=attached, enemy_attached=attached, toughness=toughness, wounds=wounds
            )
            state = session.lifecycle.state
            assert state is not None
            if fnp:
                for army in state.army_definitions:
                    for unit in army.units:
                        for model in unit.own_models:
                            state.record_model_feel_no_pain_sources(
                                model_instance_id=model.model_instance_id,
                                sources=(FeelNoPainSource(source_id="order48:fnp", threshold=5),),
                                decline_allowed=True,
                            )
            ready = time.perf_counter()
            request = complete_charge(session).decision_request
            assert request is not None
            option = next(
                o
                for o in request.options
                if o.option_id.startswith("use-stratagem:crushing-impact:")
                and (not attached or "army-alpha:leader" in o.option_id)
            )
            status = session.submit_option(
                request_id=request.request_id, option_id=option.option_id, result_id="order48:use"
            )
            while (request := status.decision_request) is not None and request.decision_type in {
                "select_mortal_wound_model",
                "select_feel_no_pain",
            }:
                status = session.submit_option(
                    request_id=request.request_id,
                    option_id=request.options[0].option_id,
                    result_id=f"order48:{request.request_id}",
                )
            end = time.perf_counter()
            assert request is not None
            assert request.decision_type == "select_charging_unit"
            events = session.lifecycle.decision_controller.event_log.records
            results = [e.payload for e in events if e.event_type == "crushing_impact_resolved"]
            assert len(results) == 1
            result = results[0]
            assert isinstance(result, dict)
            rows.append(
                {
                    "setup_seconds": ready - start,
                    "slice_seconds": end - ready,
                    "decision_count": len(session.lifecycle.decision_controller.records),
                    "event_count": len(events),
                    "source_mortal_wounds": result["source_mortal_wounds"],
                    "enemy_mortal_wounds": result["enemy_mortal_wounds"],
                }
            )
        times = sorted(float(row["slice_seconds"]) for row in rows)
        scenarios.append(
            {
                "scenario_id": name,
                "model_count": 22 if attached else 20,
                "toughness": toughness,
                "wounds": wounds,
                "feel_no_pain": fnp,
                "samples": rows,
                "mean_seconds": statistics.mean(times),
                "median_seconds": statistics.median(times),
                "p95_seconds": times[math.ceil(len(times) * 0.95) - 1],
                "maximum_seconds": max(times),
                "completion_rate": 1,
            }
        )
    report = {
        "workload_id": "order48-crushing-impact-v1",
        "engine_build_id": current_engine_build_id(),
        "environment_report": "head.json",
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "terrain_count": 0,
        "game_id": "order48-crushing-impact",
        "policy": "Charge source to enemy; select leader if attached; first damage/FNP option",
        "timing_boundary": (
            "Charge selection through Crushing Impact and next charger; setup separate"
        ),
        "base_capability": "absent: base skips the Charge-end Crushing Impact opportunity",
        "scenarios": scenarios,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_crushing_impact.py",
                "tests/crushing_impact_helpers.py",
                "tests/phase15a_charge_declaration_helpers.py",
            )
        },
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
