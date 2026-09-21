"""Matched uncached engaged shooting candidates, outside scene preparation."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import time
from pathlib import Path

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.order71_helpers")
    presence = importlib.import_module("warhammer40k_core.engine.battlefield_presence")
    targets = importlib.import_module("warhammer40k_core.engine.shooting_targets")
    keywords = importlib.import_module("warhammer40k_core.core.weapon_profiles")
    rows = []
    for name, settings in (
        ("third-party-close", {"keywords": (keywords.WeaponKeyword.CLOSE_QUARTERS,)}),
        ("both-causes", {"attacker_vehicle": True, "attacker_engaged": True}),
        (
            "mutual-close",
            {
                "attacker_vehicle": True,
                "mutual": True,
                "keywords": (keywords.WeaponKeyword.CLOSE_QUARTERS,),
            },
        ),
        ("attached-third-party", {"attached_target": True}),
    ):
        session = helpers.engaged_shooting_session(**settings)
        state = session.lifecycle.state
        assert state is not None
        scenario = presence.battlefield_scenario_for_state(state=state)
        attacker = next(
            unit
            for army in state.army_definitions
            for unit in army.units
            if unit.unit_instance_id == helpers.SHOOTER
        )
        args_query = {
            "scenario": scenario,
            "ruleset_descriptor": state.runtime_ruleset_descriptor(),
            "attacker_unit": attacker,
            "attacker_model_instance_id": attacker.own_models[0].model_instance_id,
            "weapon_profile": helpers.shooting_profile(session),
            "target_unit_id": helpers.TARGET,
        }
        samples = []
        for _ in range(7):
            start = time.perf_counter()
            for _ in range(10):
                candidate = targets.shooting_target_candidate_for_model(**args_query)
            samples.append(time.perf_counter() - start)
        rows.append(
            {
                "case": name,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "complete": True,
                "legal": candidate.is_legal,
                "hit_modifier": candidate.hit_roll_modifier,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order71-engaged-shooting-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "10 uncached complete model-target candidates, including geometry and engagement; "
            "canonical scene preparation excluded; seven serial samples without coverage"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in ("scripts/measure_order71.py", "tests/order71_helpers.py", "uv.lock")
        },
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
