"""Bounded target-dependent grouping and actual selected-history reconstruction.

The actual base incorrectly separates inapplicable Precision. It is a cost
reference, not a correctness oracle. Every runtime creates its own history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.measure_order63 import _host_inventory, _select_runtime_src

if TYPE_CHECKING:
    from tests.precision_grouping_helpers import PrecisionGroupingScene

    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.game_state import GameState

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "order103-target-aware-precision-v1"
GROUPING_CASES = {
    "plain_primary": (False, False, False),
    "precision_primary": (True, False, False),
    "character_target": (True, True, False),
    "selected_precision_source": (True, False, True),
}


def unresolved_inputs(scene: PrecisionGroupingScene) -> tuple[GameState, AttackSequence]:
    """Rebuild fresh owner inputs from accepted physical pools, before consumption."""
    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.weapon_declaration import (
        RangedAttackPool,
        RangedAttackPoolPayload,
    )

    state = GameLifecycle.from_payload(scene.initial_lifecycle).state
    assert state is not None
    accepted = next(
        event
        for event in scene.session.lifecycle.decision_controller.event_log.records
        if event.event_type == "shooting_declaration_accepted"
    )
    assert isinstance(accepted.payload, dict)
    raw = accepted.payload["attack_pools"]
    assert isinstance(raw, list)
    pools = tuple(RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, row)) for row in raw)
    sequence = AttackSequence.start(
        sequence_id="order103-measured-fresh-grouping",
        attacker_player_id=cast(str, accepted.payload["active_player_id"]),
        attacking_unit_instance_id=cast(str, accepted.payload["unit_instance_id"]),
        attack_pools=pools,
    )
    assert len(pools) == 2
    assert sum(pool.attacks for pool in pools) == 4
    assert not sequence.used_pool_indices
    assert sequence.current_gathered_group is None
    return state, sequence


def group_sample(
    scene: PrecisionGroupingScene,
    state: GameState,
    sequence: AttackSequence,
    *,
    expected_groups: int,
    timed: bool,
) -> dict[str, object]:
    from warhammer40k_core.engine.attack_sequence_selection import (
        build_select_attack_weapon_group_request,
    )

    before = sequence.to_payload()
    state_before = state.to_payload()
    started = time.perf_counter() if timed else 0
    request = build_select_attack_weapon_group_request(
        request_id="order103-measured-group-request",
        state=state,
        attack_sequence=sequence,
        target_unit_instance_id=scene.target_id,
    )
    elapsed = time.perf_counter() - started if timed else None
    assert len(request.options) == expected_groups
    physical: list[str] = []
    attacks = 0
    for option in request.options:
        assert isinstance(option.payload, dict)
        group = option.payload["gathered_group"]
        assert isinstance(group, dict)
        attacks += cast(int, group["total_attacks"])
        contributions = group["contributions"]
        assert isinstance(contributions, list)
        for contribution in contributions:
            assert isinstance(contribution, dict)
            physical.append(cast(str, contribution["weapon_instance_id"]))
    assert sorted(physical) == sorted(scene.physical_weapon_ids)
    assert attacks == 4
    assert sequence.to_payload() == before
    assert state.to_payload() == state_before
    return {
        "seconds": elapsed,
        "complete": True,
        "exact_result": True,
        "input_unchanged": True,
        "groups": len(request.options),
        "physical_weapons": physical,
        "physical_attacks": attacks,
        "request_sha256": hashlib.sha256(
            json.dumps(request.to_payload(), sort_keys=True).encode()
        ).hexdigest(),
    }


def checkpoint_inventory(scene: PrecisionGroupingScene) -> dict[str, object]:
    decisions = scene.session.lifecycle.decision_controller
    hit_steps = [
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload["step"] == "hit"
    ]
    return {
        "event_records": len(decisions.event_log.records),
        "decision_records": len(decisions.records),
        "event_type_counts": dict(
            sorted(Counter(event.event_type for event in decisions.event_log.records).items())
        ),
        "physical_weapons": list(scene.physical_weapon_ids),
        "physical_attacks": 4,
        "initial_decision_records": len(scene.initial_lifecycle["decisions"]["records"]),
        "hit_attempts": hit_steps,
    }


def reconstruct_sample(
    scene: PrecisionGroupingScene, operation: str, *, timed: bool
) -> dict[str, object]:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    saved = scene.session.to_persistence_payload()
    isolated = json.loads(json.dumps(saved))
    artifact = ReplayArtifact.capture(
        artifact_id="order103-measurement",
        initial_lifecycle_payload=scene.initial_lifecycle,
        final_lifecycle=scene.session.lifecycle,
    )
    artifact_payload = artifact.to_payload()
    artifact_before = json.loads(json.dumps(artifact_payload))
    runner = ReplayRunner.from_payload(artifact_payload)
    if operation == "restore":
        started = time.perf_counter() if timed else 0
        restored = LocalGameSession.from_persistence_payload(isolated)
        elapsed = time.perf_counter() - started if timed else None
        assert restored.to_persistence_payload() == saved
        assert restored.lifecycle.state is not scene.session.lifecycle.state
    elif operation == "replay":
        started = time.perf_counter() if timed else 0
        replay = runner.run()
        elapsed = time.perf_counter() - started if timed else None
        assert replay.reproduced_exactly, replay
    else:
        raise ValueError(f"Unknown operation: {operation}")
    assert scene.session.to_persistence_payload() == saved
    assert isolated == saved
    assert artifact_payload == artifact_before
    return {"seconds": elapsed, "complete": True, "exact_result": True, "input_unchanged": True}


def report_row(
    case: str,
    operation: str,
    samples: list[dict[str, object]],
    context: dict[str, object],
    *,
    preflight: bool,
) -> dict[str, object]:
    row = {
        "case": case,
        "operation": operation,
        **context,
        "samples": samples,
        "completion_rate": 1,
    }
    if not preflight:
        values = [float(str(sample["seconds"])) for sample in samples]
        row.update(
            mean_seconds=statistics.mean(values),
            median_seconds=statistics.median(values),
            p95_seconds=sorted(values)[math.ceil(0.95 * len(values)) - 1],
            maximum_seconds=max(values),
            operations_per_second=1 / statistics.mean(values),
        )
    print(json.dumps({"case": case, "operation": operation, "complete": True}), flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--semantics", choices=("base", "current"), required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from tests.precision_grouping_helpers import precision_shooting_scene
    from tests.psychic_modifier_helpers import submit_fixture_request

    from warhammer40k_core import build_identity
    from warhammer40k_core.engine import attack_sequence_selection, random_profile_attack_groups
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    rows = []
    count = 1 if args.preflight else 5
    for case, (precision_first, character_target, duplicate_precision) in GROUPING_CASES.items():
        scene = precision_shooting_scene(
            precision_first=precision_first,
            character_target=character_target,
            duplicate_precision=duplicate_precision,
        )
        state, sequence = unresolved_inputs(scene)
        assert (
            "CHARACTER"
            in rules_unit_view_by_id(state=state, unit_instance_id=scene.target_id).keywords
        ) is character_target
        current_state = scene.session.lifecycle.state
        assert current_state is not None
        assert (
            "CHARACTER"
            in rules_unit_view_by_id(state=current_state, unit_instance_id=scene.target_id).keywords
        ) is character_target
        expected = 2 if args.semantics == "base" or character_target else 1
        samples = [
            group_sample(scene, state, sequence, expected_groups=expected, timed=not args.preflight)
            for _ in range(count)
        ]
        assert len({sample["request_sha256"] for sample in samples}) == 1
        rows.append(
            report_row(
                case,
                "group_request",
                samples,
                {
                    "target_has_character": character_target,
                    "precision_primary": precision_first,
                    "selected_source_count": sum(
                        len(pool.selected_weapon_ability_ids) for pool in sequence.attack_pools
                    ),
                },
                preflight=args.preflight,
            )
        )

    scene = precision_shooting_scene(
        precision_first=True, random_defence=True, duplicate_precision=True
    )
    # Base requires a choice between two groups; current singleton may already be selected.
    for _ in range(10):
        decisions = scene.session.lifecycle.decision_controller
        if any(
            event.event_type == "random_profile_values_evaluated"
            for event in decisions.event_log.records
        ):
            break
        request = scene.session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        assert request.decision_type == "select_attack_weapon_group"
        precision_option = next(
            option
            for option in request.options
            if isinstance(option.payload, dict)
            and isinstance(option.payload["gathered_group"], dict)
            and any(
                isinstance(item, dict) and item["weapon_instance_id"] == scene.precision_weapon_id
                for item in cast(list[object], option.payload["gathered_group"]["contributions"])
            )
        )
        scene.session.submit_option(
            request_id=request.request_id,
            option_id=precision_option.option_id,
            # Fixed identity from the retained diagnostic that reaches this
            # actual pending source-group checkpoint on the unmodified base.
            result_id="order103-diagnostic-select-precision",
        )
    else:
        raise AssertionError("No selected random-profile checkpoint.")
    state = scene.session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert sequence.current_gathered_group is not None
    assert len(sequence.current_gathered_group.contributions) == (
        1 if args.semantics == "base" else 2
    )
    assert scene.precision_weapon_id in {
        item.weapon_instance_id for item in sequence.current_gathered_group.contributions
    }
    assert any(
        record.request.decision_type == "select_attack_weapon_group"
        for record in scene.session.lifecycle.decision_controller.records
    )
    context = checkpoint_inventory(scene)
    context["selected_group_physical_contributions"] = len(
        sequence.current_gathered_group.contributions
    )
    rows.append(
        report_row(
            "selected_random_source",
            "restore",
            [reconstruct_sample(scene, "restore", timed=not args.preflight) for _ in range(count)],
            context,
            preflight=args.preflight,
        )
    )
    for _ in range(30):
        events = scene.session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "attack_sequence_completed" for event in events):
            break
        request = scene.session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        assert request.decision_type != "select_precision_allocation"
        submit_fixture_request(scene.session, request)
    else:
        raise AssertionError("Physical attack inventory did not complete.")
    final_context = checkpoint_inventory(scene)
    hits = cast(list[dict[str, object]], final_context["hit_attempts"])
    assert len(hits) == 4, hits
    assert len({cast(str, hit["attack_context_id"]) for hit in hits}) == 4
    assert all(cast(dict[str, object], hit["payload"])["skipped"] is False for hit in hits)
    assert final_context["initial_decision_records"] == 0
    rows.append(
        report_row(
            "completed_random_source",
            "replay",
            [reconstruct_sample(scene, "replay", timed=not args.preflight) for _ in range(count)],
            final_context,
            preflight=args.preflight,
        )
    )
    cpu, memory = _host_inventory()
    shared = sorted(
        {
            str(Path(module.__file__).resolve().relative_to(ROOT)).replace("\\", "/")
            for name, module in sys.modules.items()
            if name.startswith(("tests.", "scripts."))
            and module.__file__
            and Path(module.__file__).resolve().is_relative_to(ROOT)
        }
        | {"uv.lock", "scripts/measure_precision_grouping.py"}
    )
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": build_identity.verified_engine_build_identity().build_id,
        "runtime_src": str(args.runtime_src.resolve()),
        "runtime_imports": {
            module.__name__: module.__file__
            for module in (build_identity, attack_sequence_selection, random_profile_attack_groups)
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": memory,
        "host_role": "provisional",
        "concurrency": 1,
        "coverage": False,
        "mode": "untimed_preflight" if args.preflight else "measurement",
        "semantics": args.semantics,
        "sample_protocol": (
            "Five independent operations on prepared warm inputs in one process; "
            "no discarded samples or cold-start claim"
        ),
        "timing_boundary": (
            "Group-request construction, LocalGameSession.from_persistence_payload "
            "or ReplayRunner.run only; preparation/JSON/artifact capture/assertions excluded"
        ),
        "qualification": (
            "Actual base incorrectly splits inapplicable PRECISION; restore compares "
            "each runtime's first selected random group (one versus two physical contributions); "
            "replay completes the same two weapons/four physical attacks. Fresh request inputs "
            "are components reconstructed from accepted pools and initial canonical state, "
            "not a pending facade checkpoint. No full-game or long-history certification."
        ),
        "hashes": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in shared},
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
