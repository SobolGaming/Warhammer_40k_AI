"""Exercise one native Normal Shooting target choice over the frozen development seeds."""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import replace
from hashlib import sha256
from time import perf_counter

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_split_objective as fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import _unit_selection
from warhammer40k_core.ai.normal_shooting_policy import generate_normal_shooting_candidates
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction, payload_digest
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

PROTOCOL = bench.RECEIPT.with_name("stage4-native-shooting-protocol.json")
RECEIPT = PROTOCOL.with_name("stage4-native-shooting-receipt.json")
REQUIRED_CHOICES = {
    "select_resolve_target_unit",
    "select_attack_weapon_group",
    "select_post_roll_attack_pool",
    "select_damage_allocation_model",
}
KEEP_OPTIONS = {"decline", "keep", "keep_all_modifiers", "decline_stratagem_window"}


def config(protocol: bench.Row, seed: str) -> GameConfig:
    base = fixture.config()
    mission = base.mission_setup
    assert mission is not None
    bench.require(
        mission.battlefield_layout_id == protocol["source_layout"], "Source layout drifted."
    )
    rosters = tuple(
        replace(
            army,
            unit_selections=tuple(
                _unit_selection(
                    unit_selection_id=unit.split(":")[1],
                    datasheet_id=row["sheet"],
                    model_profile_id=row["sheet"],
                    model_count=1,
                )
                for unit, row in protocol["roster"].items()
                if unit.startswith(army.army_id + ":")
            ),
        )
        for army in base.army_muster_requests
    )
    return replace(
        base,
        game_id=protocol["family"],
        private_rng_seed=seed,
        army_muster_requests=rosters,
        mission_setup=replace(
            mission,
            battlefield_layout_id=None,
            deployment_map_id=protocol["family"],
            terrain_layout_id=protocol["family"],
            terrain_areas=(),
            terrain_features=(),
            objective_terrain_areas=(),
        ),
    )


def setup_action(context: PlayerDecisionContext, protocol: bench.Row) -> PolicyAction:
    kind = context.route.decision_type
    if kind == "submit_deployment_placement":
        return bench.placement(
            context, {"deployment": {unit: row["xy"] for unit, row in protocol["roster"].items()}}
        )
    if kind in {"select_deployment_unit", "select_movement_unit"}:
        prefix = "deploy:" if kind == "select_deployment_unit" else ""
        options = {row["option_id"] for row in context.request["options"]}
        choice = next(
            (prefix + unit for unit in protocol["roster"] if prefix + unit in options), None
        )
        bench.require(choice is not None, f"{kind}: no frozen roster unit was offered.")
        assert choice is not None
        return bench.finite(context, choice)
    if kind == "select_shooting_unit":
        return bench.finite(context, protocol["shooter"])
    if kind == "select_shooting_type":
        return bench.finite(context, "normal")
    return fixture.ordinary(context)


def open_origin(protocol: bench.Row, seed: str) -> bench.Row:
    session = LocalGameSession()
    status = session.start(config(protocol, seed))
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = session.advance_until_decision_or_terminal()
    bench.require(
        status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION,
        f"Native startup stopped at {status.status_kind}: {status.message}",
    )
    for step in range(protocol["setup_decision_cap"] + 1):
        context = bench.actor(session)
        if list(fixture.coordinates(context)) == protocol["origin"]:
            origin = bench.strict_checkpoint(session)
            rng = origin["rng_state"]
            bench.require(
                rng["seed"] == seed and rng["draw_count"] == 0,
                "Expected the explicit startup seed and no pre-fork draws.",
            )
            return origin
        if step < protocol["setup_decision_cap"]:
            bench.commit(session, context, setup_action(context, protocol))
    raise bench.BenchmarkGap("The native Shooting origin was not reached within the setup cap.")


def response(context: PlayerDecisionContext) -> PolicyAction:
    kind = context.route.decision_type
    if kind == "submit_stratagem_target_proposal":
        bench.require(context.request["payload"]["declinable"] is True, "Mandatory Stratagem.")
        return context.propose(stratagem_decline_payload())
    options = sorted(row["option_id"] for row in context.request["options"])
    if kind == "use_stratagem":
        options = [opt for opt in options if opt in KEEP_OPTIONS or opt.endswith(":decline")]
        bench.require(len(options) == 1, "Expected one issued Stratagem decline or keep option.")
    else:
        bench.require(kind in REQUIRED_CHOICES and bool(options), f"Unexpected response {kind}.")
    return bench.finite(context, options[0])


def material(checkpoint: bench.Row, target: str) -> tuple[int, int]:
    (unit,) = [
        unit
        for army in checkpoint["lifecycle"]["state"]["army_definitions"]
        for unit in army["units"]
        if unit["unit_instance_id"] == target
    ]
    wounds = [model["wounds_remaining"] for model in unit["own_models"]]
    return sum(wounds), sum(wound > 0 for wound in wounds)


def checkpoint_row(checkpoint: bench.Row) -> bench.Row:
    decisions = checkpoint["lifecycle"]["decisions"]
    return {
        "checkpoint": checkpoint["content_hash"],
        "event_log": checkpoint["event_log_hash"],
        "request_id": decisions["queue"]["pending_requests"][0]["request_id"],
        "decisions": len(decisions["records"]),
        "events": len(decisions["event_log"]),
        "rng_draws": checkpoint["rng_state"]["draw_count"],
        "rng_history_sha256": payload_digest(checkpoint["rng_state"]["history"]),
    }


def run_arm(protocol: bench.Row, origin: bench.Row, target: str) -> bench.Row:
    session = LocalGameSession.from_persistence_payload(origin)
    context = bench.actor(session)
    candidates = generate_normal_shooting_candidates(context)
    bench.require(
        {
            candidate.target_unit_instance_id
            for candidate in candidates
            if candidate.declaration_count
        }
        == set(protocol["arms"]),
        "The native declaration menu does not match both frozen targets.",
    )
    (chosen,) = [
        candidate for candidate in candidates if candidate.target_unit_instance_id == target
    ]
    assert chosen.action.proposal_json is not None
    (weapon,) = json.loads(chosen.action.proposal_json)["declarations"]
    bench.require(
        weapon["weapon_profile_id"] == protocol["weapon_profile"]
        and context.request["payload"]["proposal_request"]["unit_instance_id"]
        == protocol["shooter"],
        "The ordinary declaration no longer offers the frozen shooter and weapon.",
    )
    bench.commit(session, context, chosen.action)
    responses = []
    for step in range(1, protocol["branch_decision_cap"] + 1):
        context = bench.actor(session)
        if list(fixture.coordinates(context)) == protocol["endpoint"]:
            break
        if step == protocol["branch_decision_cap"]:
            raise bench.BenchmarkGap("The shared Shooting endpoint exceeded the branch cap.")
        action = response(context)
        bench.commit(session, context, action)
        responses.append([context.route.decision_type, action.option_id])
    endpoint = bench.strict_checkpoint(session)
    outcome = {}
    for enemy in protocol["arms"]:
        start_wounds, start_models = material(origin, enemy)
        wounds, models = material(endpoint, enemy)
        outcome[enemy] = {
            "wounds_lost": start_wounds - wounds,
            "models_destroyed": start_models - models,
        }
    rng_delta = endpoint["rng_state"]["draw_count"] - origin["rng_state"]["draw_count"]
    bench.require(
        endpoint["rng_state"]["seed"] == origin["rng_state"]["seed"] and rng_delta > 0,
        "The volley failed to consume natural RNG on the startup seed.",
    )
    bench.require(
        all(
            outcome[enemy] == {"wounds_lost": 0, "models_destroyed": 0}
            for enemy in protocol["arms"]
            if enemy != target
        ),
        "An undeclared target changed material.",
    )
    end = checkpoint_row(endpoint)
    origin_count = len(origin["lifecycle"]["decisions"]["records"])
    return {
        "target": target,
        "candidate": chosen.candidate_id,
        "endpoint": end,
        "submitted_decisions": len(responses) + 1,
        "new_decision_records": end["decisions"] - origin_count,
        "responses": responses,
        "rng_draw_delta": rng_delta,
        "material": outcome,
    }


def run(*, verify: bool) -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    root = PROTOCOL.parent.parent
    evidence = {
        "protocol_sha256": payload_digest(protocol),
        "engine_build_id": verified_engine_build_identity().build_id,
        "lock_sha256": sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "seeds": [],
    }
    timings = []
    start = perf_counter()
    for index, seed in enumerate(protocol["seeds"], 1):
        t0 = perf_counter()
        origin = open_origin(protocol, seed)
        seed_row = {"seed": seed, "origin": checkpoint_row(origin), "arms": []}
        timing = {"setup_seconds": round(perf_counter() - t0, 3), "arms_seconds": {}}
        for target in protocol["arms"]:
            t0 = perf_counter()
            arm = run_arm(protocol, origin, target)
            seed_row["arms"].append(arm)
            timing["arms_seconds"][target] = round(perf_counter() - t0, 3)
            print(f"Seed {index}, {target}: strict replay passed", file=sys.stderr, flush=True)
        evidence["seeds"].append(seed_row)
        timings.append(timing)
    if verify:
        sealed = json.loads(RECEIPT.read_text(encoding="utf-8"))
        bench.require(
            sealed["evidence"] == evidence and sealed["evidence_hash"] == payload_digest(evidence),
            "The live Shooting outcomes or strict replay fingerprints drifted.",
        )
    print(
        json.dumps(
            {
                "evidence": evidence,
                "evidence_hash": payload_digest(evidence),
                "timing": {
                    "system": platform.platform(),
                    "python": platform.python_version(),
                    "worker_seconds": round(perf_counter() - start, 3),
                    "seeds": timings,
                },
            },
            indent=2,
        ),
        flush=True,
    )
