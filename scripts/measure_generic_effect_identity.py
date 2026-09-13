"""Compare R42-003 identity derivation on one recorded Unending Fidelity activation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

from warhammer40k_core.engine.generic_rule_effect_identity import generic_rule_persisting_effect_id
from warhammer40k_core.engine.generic_rule_source_authority import (
    generic_execution_context_from_payload,
)
from warhammer40k_core.rules.rule_ir import RuleIR

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = "docs/performance/order42/effect_identity_workload.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-api", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workload = json.loads((ROOT / WORKLOAD).read_text())
    rule_ir = RuleIR.from_payload(workload["rule_ir"])
    clause = next(c for c in rule_ir.clauses if c.clause_id == workload["clause_id"])
    context = generic_execution_context_from_payload(workload["context"])
    kwargs: dict[str, object] = {
        "rule_ir": rule_ir,
        "clause": clause,
        "target_unit_instance_ids": tuple(workload["target_unit_instance_ids"]),
    }
    if args.base_api:
        kwargs.update(
            effect=clause.effects[workload["effect_index"]],
            source_unit_instance_id=context.source_unit_instance_id,
            source_model_instance_id=context.source_model_instance_id,
        )
    else:
        kwargs.update(effect_index=workload["effect_index"], context=context)
    # The historical API is selected explicitly; production has no compatibility path.
    derive = cast(Callable[..., str], generic_rule_persisting_effect_id)
    rows = []
    for sample in range(7):
        started = time.perf_counter()
        identity = derive(**kwargs)
        elapsed = time.perf_counter() - started
        rows.append({"sample": sample, "seconds": elapsed, "identity": identity})
    values = [row["seconds"] for row in rows]
    report = {
        "workload_id": "order42-recorded-effect-identity-v1",
        "base_api": args.base_api,
        "rows": rows,
        "summary": {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": max(values),
            "maximum": max(values),
            "samples": len(values),
            "completion_rate": 1.0,
            "queries_per_second": 1 / statistics.mean(values),
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "model_count": 4,
        "terrain_count": 0,
        "seed": workload["context"]["game_id"],
        "timing_boundary": "one identity derivation; recorded context and RuleIR loaded first",
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_generic_effect_identity.py",
                WORKLOAD,
                "uv.lock",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
