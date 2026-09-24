"""Matched reactive move, turn advance and checkpoint costs, not complete games."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import statistics
import time
from pathlib import Path

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--ordinary-restore", action="store_true")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helper = importlib.import_module("tests.normal_move_occurrence_helpers")
    session_type = importlib.import_module(
        "warhammer40k_core.adapters.local_session"
    ).LocalGameSession
    rows = []
    for parameterized in (False, True):
        samples = []
        available = []
        for _ in range(3):
            session, unit_id = helper.reaction_session(
                parameterized=True if args.ordinary_restore else parameterized,
                attached=parameterized if args.ordinary_restore else False,
            )
            if args.ordinary_restore:
                status = helper.accept_reaction(session, parameterized=True)
                request = helper.next_player_action(session, status, unit_id)
                started = time.perf_counter()
                proposal_status = session.submit_option(
                    request_id=request.request_id,
                    option_id="normal_move",
                    result_id="measured-normal",
                )
                helper.submit_path(
                    session, helper.request_from(proposal_status), result_id="measured-normal-path"
                )
            else:
                started = time.perf_counter()
                status = helper.accept_reaction(session, parameterized=parameterized)
                request = helper.next_player_action(session, status, unit_id)
            checkpoint = session.to_persistence_payload()
            restored = session_type.from_persistence_payload(checkpoint)
            assert restored.to_persistence_payload() == checkpoint
            samples.append(time.perf_counter() - started)
            available.append("normal_move" in {o.option_id for o in request.options})
        rows.append(
            {
                "case": (
                    ("attached" if parameterized else "standalone")
                    if args.ordinary_restore
                    else ("parameterized" if parameterized else "finite")
                ),
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "complete": True,
                "normal_move_available": available,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": (
            "order80-ordinary-move-authority-v1"
            if args.ordinary_restore
            else "order80-normal-move-occurrence-v1"
        ),
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "host_role": "provisional",
        "concurrency": 1,
        "timing_boundary": (
            "Accepted ordinary Normal Move selection/proposal, checkpoint export and restore; "
            "initial scene/reaction/turn preparation excluded; "
            "three serial samples without coverage"
            if args.ordinary_restore
            else "Accepted reactive move through next player Movement action enumeration, session "
            "checkpoint export and restore; initial scene/permission preparation excluded; "
            "three serial samples without coverage"
        ),
        "hashes": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path("scripts/measure_order80.py"),
                Path("tests/normal_move_occurrence_helpers.py"),
                Path("tests/phase15c_fight_order_helpers.py"),
                Path("uv.lock"),
            )
        },
        "rows": rows,
        "full_game_certified": False,
        "semantic_note": (
            "Base is published PR #500. Same accepted ordinary move and checkpoint work; "
            "review regressions separately verify rejected forged histories."
            if args.ordinary_restore
            else "Base wrongly omits Normal Move; timing compares the same submitted decisions "
            "and checkpoint work, not semantic equivalence"
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
