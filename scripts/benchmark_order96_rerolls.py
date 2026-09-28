"""Matched physical attack work, with all optional rerolls submitted by the facade."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path
from time import perf_counter
from typing import cast

from tests.absent_strength_helpers import strength_session
from tests.lethal_hits_helpers import attack_steps
from tests.psychic_modifier_helpers import pending_request
from tests.twin_linked_helpers import complete_optional_attack, sustained_twin_session

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase


def measure(*, sustained: bool = False) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        for accept in (False, True):
            samples: list[float] = []
            preparation: list[float] = []
            restore: list[float] = []
            work: list[dict[str, int]] = []
            for _ in range(5):
                start = perf_counter()
                session = sustained_twin_session(phase) if sustained else strength_session(phase)
                pending_request(session)
                ready = perf_counter()
                complete_optional_attack(session, reroll=accept)
                completed = perf_counter()
                assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
                restore.append(perf_counter() - completed)
                samples.append(completed - ready)
                preparation.append(ready - start)
                decisions = session.lifecycle.decision_controller
                work.append(
                    {
                        "wounds": len(attack_steps(session, "wound")),
                        "reroll_choices": sum(
                            r.request.decision_type == "select_dice_reroll"
                            for r in decisions.records
                        ),
                        "rerolls": sum(
                            e.event_type == "dice_reroll_resolved"
                            for e in decisions.event_log.records
                        ),
                        "automatic_weapon_rerolls": sum(
                            e.event_type == "weapon_ability_reroll_resolved"
                            for e in decisions.event_log.records
                        ),
                    }
                )
                if sustained:
                    hits = attack_steps(session, "hit")
                    work[-1].update(
                        {
                            "hits": len(hits),
                            "distinct_hit_contexts": len(
                                {cast(str, row["attack_context_id"]) for row in hits}
                            ),
                            "critical_hits": sum(
                                cast(dict[str, JsonValue], row["payload"])["critical"] is True
                                for row in hits
                            ),
                            "sustained_d3": sum(
                                event.event_type == "d3_roll_resolved"
                                for event in decisions.event_log.records
                            ),
                        }
                    )
            rows.append(
                {
                    "phase": phase.value,
                    "accept": accept,
                    "setup_seconds": preparation,
                    "samples_seconds": samples,
                    "restore_seconds": restore,
                    "work_counts": work,
                    "mean": statistics.mean(samples),
                    "median": statistics.median(samples),
                    "p95_and_maximum": max(samples),
                    "restore_mean": statistics.mean(restore),
                    "slices_per_second": 1 / statistics.mean(samples),
                }
            )
    return {
        "workload": (
            "order96-sustained-d3-optional-wound-rerolls-v1"
            if sustained
            else "order96-optional-wound-rerolls-v1"
        ),
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "hardware_status": "provisional",
        "concurrency": 1,
        "coverage": False,
        "fixture": (
            "Two units, one model each, no terrain; 12 Twin-linked/Sustained Hits D3 attacks"
            if sustained
            else (
                "Two units, one model each, no terrain; "
                "12 Torrent/Twin-linked attacks, dash S vs T1"
            )
        ),
        "seeds": (
            ["psychic-sources", "psychic-sources-fight"]
            if sustained
            else ["order88-shooting", "order88-fight"]
        ),
        "policy": (
            "Submit decline or reroll:0 through LocalGameSession; decline Stratagem opportunities"
        ),
        "timing_boundary": (
            "Pending phase choice through first attack completion; setup and restore separate"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order96_rerolls.py",
                "tests/absent_strength_helpers.py",
                "tests/twin_linked_helpers.py",
                "tests/lethal_hits_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "completion_rate": 1.0,
        "full_game_samples": 0,
        "full_game_certified": False,
        "timing_budget": (
            "Diagnostic; owner-deferred provisional component timing gates remain deferred"
        ),
        "work_gate": (
            "One submitted choice per wound; one physical D3 per critical hit; "
            "no duplicate hit contexts; at most one reroll per die; no synthetic weapon decisions"
            if sustained
            else "12 wounds and 12 submitted choices; at most one "
            "reroll per physical die; no synthetic weapon decisions"
        ),
        "baseline_limit": (
            "Base implements the reported bug and is a cost comparison, not a correctness oracle"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sustained", action="store_true")
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(measure(sustained=arguments.sustained), indent=2) + "\n")
