"""Matched physical attack work, with all optional rerolls submitted by the facade."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
from pathlib import Path
from time import perf_counter
from typing import cast

from scripts.measure_order63 import _host_inventory, _select_runtime_src

ROOT = Path(__file__).resolve().parents[1]


def measure(*, sustained: bool = False, preflight_only: bool = False) -> dict[str, object]:
    from tests.absent_strength_helpers import strength_session
    from tests.lethal_hits_helpers import attack_steps
    from tests.psychic_modifier_helpers import pending_request
    from tests.twin_linked_helpers import complete_optional_attack, sustained_twin_session

    from warhammer40k_core.build_identity import verified_engine_build_identity
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phase import BattlePhase

    def clock() -> float:
        return 0.0 if preflight_only else perf_counter()

    rows: list[dict[str, object]] = []
    for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        for accept in (False, True):
            samples: list[float] = []
            preparation: list[float] = []
            restore: list[float] = []
            work: list[dict[str, int]] = []
            semantics: list[dict[str, object]] = []
            for _ in range(1 if preflight_only else 5):
                start = clock()
                session = sustained_twin_session(phase) if sustained else strength_session(phase)
                pending_request(session)
                ready = clock()
                complete_optional_attack(
                    session,
                    reroll=accept,
                    result_id_suffix=(
                        "order103-fixture-16-00"
                        if sustained and phase is BattlePhase.FIGHT and accept
                        else "fixture-choice"
                    ),
                )
                completed = clock()
                assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
                restore.append(clock() - completed)
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
                if preflight_only:
                    print(
                        json.dumps({"phase": phase.value, "accept": accept, "work": work[-1]}),
                        flush=True,
                    )
                choices = [
                    record
                    for record in decisions.records
                    if record.request.decision_type == "select_dice_reroll"
                ]
                roll_ids = [
                    cast(dict[str, JsonValue], record.request.payload)["roll_id"]
                    for record in choices
                ]
                assert work[-1]["automatic_weapon_rerolls"] == 0
                assert work[-1]["wounds"] == work[-1]["reroll_choices"] > 0
                assert len(set(cast(list[str], roll_ids))) == len(roll_ids)
                assert work[-1]["rerolls"] == (len(choices) if accept else 0)
                assert all(
                    record.result.selected_option_id == ("reroll:0" if accept else "decline")
                    for record in choices
                )
                completed_events = [
                    event.to_payload()
                    for event in decisions.event_log.records
                    if event.event_type == "attack_sequence_completed"
                ]
                assert len(completed_events) == 1
                if sustained:
                    assert work[-1]["hits"] == work[-1]["distinct_hit_contexts"] == 12
                    assert work[-1]["sustained_d3"] == work[-1]["critical_hits"] > 0
                else:
                    assert work[-1]["wounds"] == work[-1]["reroll_choices"] == 12
                semantics.append(
                    {
                        "complete": True,
                        "normal_restore_exact": True,
                        "wound_choice_roll_ids": roll_ids,
                        "choice_records": [record.to_payload() for record in choices],
                        "hit_steps": attack_steps(session, "hit"),
                        "wound_steps": attack_steps(session, "wound"),
                        "d3_events": [
                            event.to_payload()
                            for event in decisions.event_log.records
                            if event.event_type == "d3_roll_resolved"
                        ],
                        "completed_sequence_events": completed_events,
                        "event_count": len(decisions.event_log.records),
                        "decision_count": len(decisions.records),
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
                    "semantic_checks": semantics,
                    "mean": statistics.mean(samples),
                    "median": statistics.median(samples),
                    "p95_and_maximum": max(samples),
                    "restore_mean": statistics.mean(restore),
                    "slices_per_second": None if preflight_only else 1 / statistics.mean(samples),
                }
            )
    cpu, memory_bytes = _host_inventory()
    return {
        "preflight_only": preflight_only,
        "timings_recorded": not preflight_only,
        "cpu_allocation": os.cpu_count(),
        "workload": (
            "order96-sustained-d3-optional-wound-rerolls-v1"
            if sustained
            else "order96-optional-wound-rerolls-v1"
        ),
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory_bytes,
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
        "fixture_migration": (
            "Sustained Fight/accept uses fixed legal result-ID suffix order103-fixture-16-00 "
            "in both runtimes, already demonstrated by the retained positive control. "
            "The original current untimed preflight missed its critical/D3 branch and is "
            "retained as a preparation failure; no timing samples were discarded. "
            "Other cases preserve their original default decision IDs."
        ),
        "policy": (
            "Submit decline or reroll:0 through LocalGameSession; decline Stratagem opportunities"
        ),
        "timing_boundary": (
            "Pending phase choice through first attack completion; setup and restore separate"
        ),
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order96_rerolls.py",
                "scripts/measure_order63.py",
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
            "Current policy-v3 matched relative budgets apply; "
            "original historical records remain unchanged"
        ),
        "work_gate": (
            "One submitted choice per wound; one physical D3 per critical hit; "
            "no duplicate hit contexts; at most one reroll per die; no synthetic weapon decisions"
            if sustained
            else "12 wounds and 12 submitted choices; at most one "
            "reroll per physical die; no synthetic weapon decisions"
        ),
        "baseline_limit": (
            "Actual PR base 133956de already contains the Order96 optional-reroll repair. "
            "This current comparison measures the changed shared fixture owner and Order103 "
            "runtime on the same current workload; cross-version dice histories may differ."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sustained", action="store_true")
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--revision", default="current-checkout")
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    _select_runtime_src(arguments.runtime_src)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    report = measure(sustained=arguments.sustained, preflight_only=arguments.preflight_only)
    report["revision"] = arguments.revision
    report["runtime_src"] = str(arguments.runtime_src.resolve())
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
