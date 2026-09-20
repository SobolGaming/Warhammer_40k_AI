"""Measure Order 67 pre-game roster validation on one provisional host."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from pathlib import Path

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.build_identity import current_engine_build_id
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, validate_roster_legality
    from warhammer40k_core.engine.list_validation import (
        BattleSize,
        DetachmentSelection,
        UnitMusterSelection,
    )
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    rows = []
    for count in (2, 4, 20):
        request = ArmyMusterRequest(
            army_id="benchmark",
            player_id="player-a",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="core-marine-force", detachment_ids=("core-combined-arms",)
            ),
            force_disposition_id="purge-the-foe",
            battle_size=BattleSize.INCURSION,
            unit_selections=tuple(
                UnitMusterSelection(
                    unit_selection_id=f"unit-{i}",
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_selections=(
                        ModelProfileSelection(
                            model_profile_id="core-intercessor-like", model_count=5
                        ),
                    ),
                )
                for i in range(count)
            ),
        )
        validate_roster_legality(catalog=catalog, request=request)
        samples = []
        for _ in range(7):
            start = time.perf_counter()
            for _ in range(100):
                report = validate_roster_legality(catalog=catalog, request=request)
            samples.append(time.perf_counter() - start)
        rows.append(
            {
                "unit_count": count,
                "model_count": count * 5,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "complete": True,
                "violation_codes": sorted({v.violation_code for v in report.violations}),
            }
        )
    cpu, memory = _host_inventory()
    output = {
        "workload": "order67-roster-validation-v1",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "host_role": "provisional",
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "revision": args.revision,
        "runtime_build_id": current_engine_build_id(),
        "timing_boundary": (
            "100 validate_roster_legality calls; catalog/request construction excluded; "
            "no gameplay, terrain, RNG or decisions"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in ("scripts/measure_order67.py", "uv.lock")
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
