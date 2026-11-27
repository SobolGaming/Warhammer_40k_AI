"""Run one frozen, actor-bound Stage 4 split-objective group from latched setup."""

from __future__ import annotations

import json
from collections import Counter
from math import hypot, isclose
from pathlib import Path
from typing import cast

from shapely.geometry import Point, Polygon

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_policy_target as policy_target
from scripts import stage4_split_objective as fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.screen_movement_candidates import ScreenMovementGap
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.replay import ReplayArtifactError

BASE = "54fd9dcceaa593314a519ceaa695adbafc5ac14a"
NATIVE_CAP = 2
DECISION_CAP = 50
WALL_SECONDS = 1100
ORIGIN = (2, bench.A, "movement", bench.MOVE_ACTION)
HORIZON = (3, bench.A, "movement", "select_movement_unit")
type Boundary = tuple[int, str, str, str]

BOUNDARIES: tuple[Boundary, ...] = (
    (2, bench.A, "fight", "turn_end"),
    (2, bench.B, "command", "phase_end"),
    (2, bench.B, "fight", "turn_end"),
    (3, bench.A, "command", "phase_end"),
)
ARMS = (
    ("hold-omit", False, False),
    ("hold-follow", False, True),
    ("screen-omit", True, False),
    ("screen-follow", True, True),
)
ROLE_BY_UNIT = {
    fixture.SCREEN: "screen",
    fixture.ALLY: "follow",
    fixture.OPPONENT: "respond",
}
POLICY = {
    "stage": "R1 A moves east and B west, exactly 4.5 inches",
    "screen": "shallow south-east at 8:3, touch west footprint, longest eligible first",
    "follow": "east, touch east footprint, longest eligible first",
    "respond": (
        "West aimed at west footprint (longest first); "
        "northwest diagonal aimed at east footprint (longest first); "
        "reserve one slot for each present route before testing additional eligible moves; "
        "take first native-accepted candidate, else issued Hold"
    ),
    "controls": "A uses its issued Hold for each omitted action",
    "admission": (
        "identical restored prefix, ordered A2 Screen/Hold and Follow/Omit and B2 response, "
        "at least one native-accepted active response, exact common horizon and independent "
        "replay of each arm, no dependence on scoring values"
    ),
}
ERRORS = (
    bench.BenchmarkGap,
    GameLifecycleError,
    PolicyError,
    ReplayArtifactError,
    ScreenMovementGap,
)


def unit_radius(offer: PlayerDecisionContext, model_id: str) -> float:
    display = offer.observation["model_display_by_id"][model_id]
    size = display["base_size"]
    bench.require(
        size is not None and size["kind"] == "circular" and size["diameter_mm"] == 40.0,
        f"Actor-visible base drift for {model_id}: {size}.",
    )
    assert size is not None
    assert size["diameter_mm"] is not None
    return size["diameter_mm"] / 50.8


def candidate_route(role: str, dx: float, dy: float, west: bool, east: bool) -> int | None:
    horizontal = isclose(dy, 0, abs_tol=1e-8)
    if role in {"stage-a", "stage-b"}:
        signed = 4.5 if role == "stage-a" else -4.5
        return 0 if horizontal and isclose(dx, signed, abs_tol=1e-8) else None
    if role == "screen":
        return 0 if west and dx > 0 and isclose(dy, -3 * dx / 8, abs_tol=1e-8) else None
    if role == "follow":
        return 0 if east and dx > 0 and horizontal else None
    if west and dx < 0 and horizontal:
        return 0
    if east and dx < 0 and isclose(dy, -dx, abs_tol=1e-8):
        return 1
    return None


def ordered_candidates(
    offer: PlayerDecisionContext, raw: bench.Raw, polygons: dict[str, Polygon], role: str
) -> tuple[list[str], dict[str, bench.Row]]:
    routes: dict[int, list[tuple[float, str]]] = {0: [], 1: []}
    evidence = {}
    for key, (_, proposal) in raw.items():
        (path,) = proposal["witness"]["model_paths"]
        (endpoint,) = bench.path_points(proposal, end=True)
        radius = unit_radius(offer, path["model_id"])
        west = polygons[fixture.WEST_LOBE].distance(Point(endpoint)) <= radius
        east = polygons[fixture.EAST_LOBE].distance(Point(endpoint)) <= radius
        dx, dy = bench.delta(proposal)
        route = candidate_route(role, dx, dy, west, east)
        if route is not None:
            routes[route].append((-hypot(dx, dy), key))
            evidence[key] = {
                "route": route,
                "translation_inches": [dx, dy],
                "endpoint_inches": endpoint,
                "footprint_radius_inches": radius,
                "west_contact": west,
                "east_contact": east,
            }
    first, second = ([key for _, key in sorted(route)] for route in routes.values())
    order = first[:1] + second[:1] + first[1:] + second[1:]
    return order, evidence


def select_move(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    polygons: dict[str, Polygon],
    role: str,
    arm: str,
    *,
    screen_offers: list[policy_target.FrozenMovementOffer] | None = None,
) -> bench.Row:
    unit = context.request["payload"]["unit_instance_id"]
    menu = FiniteCandidateSet.from_context(context)
    bench.require(
        {bench.HOLD, bench.NORMAL} <= set(menu.candidate_ids),
        f"{arm} {role} lacked the native Hold/Normal offer for {unit}: {menu.candidate_ids}.",
    )
    response = role == "respond"
    scratch = session.fork() if response else session
    stamp = {
        "arm": arm,
        "role": role,
        "unit": unit,
        "actor": context.route.actor_id,
        "action_request_id": context.request["request_id"],
    }
    fixture.emit("movement_offer", **stamp)
    bench.commit(scratch, context, menu.select(context, bench.NORMAL))
    offer = bench.actor(scratch)
    if screen_offers is not None and role == "screen":
        screen_offers.append(policy_target.FrozenMovementOffer.capture(scratch, offer))
    raw = bench.raw_moves(offer)
    order, geometry = ordered_candidates(offer, raw, polygons, role)
    ledger: bench.Row = {
        **stamp,
        "proposal_request_id": offer.request["request_id"],
        "actor_view_hash": offer.observation_hash,
        "raw_count": len(raw),
        "raw_ids_hash": payload_digest(list(raw)),
        "geometry_excluded": len(raw) - len(order),
        "ordered_eligible_ids": order,
        "cap_lost_ids": order[NATIVE_CAP:],
        "native_probes": [],
    }
    fixture.emit("movement_menu", **ledger)
    before = payload_digest(scratch.lifecycle.to_payload())
    for key in order[:NATIVE_CAP]:
        fixture.emit("native_probe", **stamp, candidate_id=key, **geometry[key])
        violation = bench.trial(scratch, offer, raw, key)
        ledger["native_probes"].append({"id": key, "violation": violation, **geometry[key]})
        fixture.emit("native_probe_result", **stamp, candidate_id=key, violation=violation)
    bench.require(
        payload_digest(scratch.lifecycle.to_payload()) == before,
        f"Native probe mutated the {arm} {role} parent.",
    )
    accepted = [probe["id"] for probe in ledger["native_probes"] if probe["violation"] is None]
    if accepted:
        key = accepted[0]
        if response:
            bench.commit(session, context, menu.select(context, bench.NORMAL))
        bench.commit(session, bench.actor(session), raw[key][0])
        ledger["selected"] = key
    else:
        bench.require(
            response, f"{arm} {role}, {unit}: no accepted proposal inside native cap {NATIVE_CAP}."
        )
        bench.commit(session, context, menu.select(context, bench.HOLD))
        ledger["selected"] = bench.HOLD
    return ledger


def drive(
    session: LocalGameSession,
    polygons: dict[str, Polygon],
    leg: str,
    arm: str,
    screen: bool = False,
    follow: bool = False,
    *,
    screen_offers: list[policy_target.FrozenMovementOffer] | None = None,
) -> list[bench.Row]:
    rows = []
    for _ in range(DECISION_CAP):
        context = bench.actor(session)
        route = fixture.coordinates(context)
        rnd, turn, _, kind = route
        unit = context.request["payload"].get("unit_instance_id")
        if leg == "stem" and route == ORIGIN:
            bench.require(unit == fixture.SCREEN, "Round-two origin did not offer Screen first.")
            bench.require(
                [row["unit"] for row in rows] == [fixture.SCREEN, fixture.ALLY, fixture.OPPONENT],
                "Shared stem did not commit all three planned stage moves.",
            )
            return rows
        if route == HORIZON:
            bench.require(leg == "horizon", f"{arm} missed its preflight offer.")
            return rows
        if kind != bench.MOVE_ACTION:
            bench.commit(session, context, fixture.ordinary(context))
            continue
        bench.require(unit in ROLE_BY_UNIT, f"{arm} encountered an unexpected unit {unit}.")
        if leg == "stem":
            bench.require(rnd == 1, f"Unexpected stem movement in round {rnd}.")
            role = "stage-a" if turn == bench.A else "stage-b"
            rows.append(select_move(session, context, polygons, role, arm))
            continue
        bench.require(leg == "preflight" and rnd == 2, f"{arm} missed its horizon.")
        role = ROLE_BY_UNIT[unit]
        if role == "respond" or (role == "screen" and screen) or (role == "follow" and follow):
            rows.append(
                select_move(session, context, polygons, role, arm, screen_offers=screen_offers)
            )
        else:
            bench.commit(session, context, fixture.ordinary(context))
            rows.append(
                {
                    "arm": arm,
                    "role": role,
                    "unit": unit,
                    "actor": context.route.actor_id,
                    "action_request_id": context.request["request_id"],
                    "selected": bench.HOLD,
                }
            )
        if role == "respond":
            bench.require(
                [row["role"] for row in rows] == ["screen", "follow", "respond"]
                and fixture.coordinates(bench.actor(session))[:2] == (2, bench.B),
                f"{arm} missed an ordered A2/B2 action before scoring.",
            )
            return rows
    raise bench.BenchmarkGap(f"{arm} {leg} exceeded {DECISION_CAP} decisions.")


def score(
    origin: bench.Row, endpoint: bench.Row, *, boundaries: tuple[Boundary, ...] = BOUNDARIES
) -> bench.Row:
    start, end = (cp["lifecycle"]["state"] for cp in (origin, endpoint))
    records: dict[str, bench.Row] = {}
    for boundary in boundaries:
        matches = [
            r
            for r in end["objective_control_records"]
            if (r["battle_round"], r["active_player_id"], r["phase"], r["timing"]) == boundary
        ]
        bench.require(len(matches) == 1, f"Expected one objective record at {boundary}.")
        row = matches[0]
        records[row["record_id"]] = {
            "boundary": list(boundary),
            "objectives": {},
        }
        for objective in row["results"]:
            bench.require(objective["unsupported_reason"] is None, "Unsupported objective record.")
            contributions: Counter[str] = Counter()
            for model in objective["contributors"]:
                contributions[model["unit_instance_id"]] += model["effective_objective_control"]
            records[row["record_id"]]["objectives"][objective["objective_id"]] = {
                "oc": {x["player_id"]: x["score"] for x in objective["scores"]},
                "controller": objective["controlled_by_player_id"],
                "unit_oc": contributions,
                "vp": {bench.A: 0, bench.B: 0},
            }
    gain, awards = {}, []
    from_ledger = {row["player_id"]: row for row in start["victory_point_ledgers"]}
    for to in end["victory_point_ledgers"]:
        player = to["player_id"]
        prior = from_ledger[player]
        earlier, complete = prior["transactions"], to["transactions"]
        bench.require(complete[: len(earlier)] == earlier, "The origin VP ledger changed.")
        delta = complete[len(earlier) :]
        gain[player] = to["victory_points"] - prior["victory_points"]
        bench.require(gain[player] == sum(x["amount"] for x in delta), "VP failed reconciliation.")
        for tx in delta:
            metadata = tx["metadata"]
            boundary = metadata["objective_control_record_id"]
            ids = metadata["controlled_objective_ids"]
            per = metadata["victory_points_per_count"]
            rule = metadata["scoring_rule_id"]
            bench.require(
                tx["source_id"] == "primary-outmaneuver"
                and tx["source_kind"] == "primary"
                and tx["hidden"] is False
                and tx["player_id"] == player
                and boundary in records
                and records[boundary]["boundary"]
                == [tx["battle_round"], player, tx["phase"], tx["scoring_timing"]]
                and bool(ids)
                and len(ids) == len(set(ids))
                and tx["amount"] == per * len(ids),
                f"Cannot allocate the award unambiguously to objectives: {tx}.",
            )
            if rule == fixture.RULE:
                bench.require(
                    per == 5
                    and tuple(records[boundary]["boundary"])
                    in {
                        (2, bench.B, "command", "phase_end"),
                        (3, bench.A, "command", "phase_end"),
                        (3, bench.B, "command", "phase_end"),
                    },
                    f"Wrong Outmanoeuvre Command clause or boundary: {tx}.",
                )
            for objective_id in ids:
                objective = records[boundary]["objectives"][objective_id]
                bench.require(objective["controller"] == player, "Award and OC controller differ.")
                objective["vp"][player] += per
            awards.append(
                {
                    "player": player,
                    "boundary_id": boundary,
                    "rule": rule,
                    "vp": tx["amount"],
                    "vp_by_objective": dict.fromkeys(ids, per),
                }
            )

    def living_material(state: bench.Row) -> bench.Row:
        models = bench.material(state)
        return {
            "living_models": sum(value > 0 for value in models.values()),
            "total_wounds": sum(models.values()),
            "wounds_by_model": models,
        }

    return {
        **bench.checkpoint_summary(endpoint),
        "gain_vp": gain,
        "awards": awards,
        "objective_boundaries": records,
        "material": {"origin": living_material(start), "endpoint": living_material(end)},
        "rng_draw_delta": endpoint["rng_state"]["draw_count"] - origin["rng_state"]["draw_count"],
    }


def run(
    checkpoint: Path, *, link_policy_target: bool = False, scoring_timing: bool = False
) -> None:
    if scoring_timing:
        from scripts import stage4_scoring_timing as timing

    reference = fixture.sealed_receipt()
    if link_policy_target or scoring_timing:
        policy_target.verify_seal(reference)
    setup_hash = reference["setup_evidence"]["latch"]["checkpoint"]
    stage = "setup_checkpoint"
    arm = "shared"
    result: bench.Row = {
        "schema": "stage4-disruption-c-split-central-2x2-v1",
        "base": BASE,
        "partition": "development",
        "status": "unobserved",
        "interaction": None,
        "training_rows": 0,
        "arms": {},
    }
    timing_protocol: bench.Row | None = None
    try:
        saved_setup = json.loads(checkpoint.read_text(encoding="utf-8"))
        bench.require(
            saved_setup["content_hash"] == setup_hash, "Expected the sealed Layout C setup."
        )
        common = LocalGameSession.from_persistence_payload(saved_setup)
        bench.require(common.to_persistence_payload() == saved_setup, "Latched setup drifted.")
        source = fixture.source_evidence(common.lifecycle.config)
        polygons = {
            key: Polygon(points) for key, points in source["linked_footprints_inches"].items()
        }
        result["protocol"] = {
            "seed": bench.SEED,
            "setup": setup_hash,
            "policy": POLICY,
            "native_cap": NATIVE_CAP,
            "horizon": HORIZON,
            "wall_seconds": WALL_SECONDS,
            "setup_deployment_inches": fixture.DEPLOYMENT,
            **source,
            "october_scoring_clause_verified": False,
        }
        fixture.emit("protocol_frozen", **result["protocol"])
        if scoring_timing:
            timing_protocol = timing.protocol(source)
            fixture.emit("timing_protocol_frozen", **timing_protocol)
        stage = "stem"
        result["stem"] = drive(common, polygons, "stem", arm)
        origin = cast(bench.Row, common.to_persistence_payload())
        result["origin"] = {
            "checkpoint": origin["content_hash"],
            "event_log": origin["event_log_hash"],
            "active_rng_draws": origin["rng_state"]["draw_count"],
            "record_count": common.decision_record_count(),
            "request_id": bench.actor(common).request["request_id"],
        }
        fixture.emit("origin", **result["origin"])
        frozen_choice = (
            policy_target.FrozenChoice.capture(common, bench.actor(common))
            if link_policy_target
            else None
        )
        endpoints = {}
        stage = "live_admission"
        branches = {}
        screen_offers: list[policy_target.FrozenMovementOffer] | None = (
            [] if link_policy_target else None
        )
        for arm, screen, follow in ARMS:
            branch = common.fork()
            menus = drive(
                branch, polygons, "preflight", arm, screen, follow, screen_offers=screen_offers
            )
            branches[arm] = branch
            result["arms"][arm] = {"menus": menus}
            fixture.emit("live_arm_admitted", arm=arm, menus=menus)
        bench.require(
            any(row["menus"][-1]["selected"] != bench.HOLD for row in result["arms"].values()),
            "All four opponent occurrences took the finite Hold fallback.",
        )
        fixture.emit("group_live_admitted", arms=list(branches))
        stage = "horizon_replay"
        for arm, branch in branches.items():
            drive(branch, polygons, "horizon", arm)
            fixture.emit("horizon_reached", arm=arm, records=branch.decision_record_count())
            endpoint = bench.strict_checkpoint(branch)
            if frozen_choice is not None or scoring_timing:
                bench.require(
                    fixture.coordinates(bench.actor(branch)) == HORIZON,
                    f"{arm} reached a mixed or stale A3 Movement horizon.",
                )
                endpoints[arm] = endpoint
            result["arms"][arm].update(
                score(origin, endpoint), records=branch.decision_record_count()
            )
            fixture.emit("endpoint_replayed", arm=arm, **result["arms"][arm])
        stage = "isolation"
        bench.require(
            common.to_persistence_payload() == origin, "Branches mutated the shared origin."
        )
    except ERRORS as exc:
        result["gap"] = {"stage": stage, "arm": arm, "type": type(exc).__name__, "detail": str(exc)}
        fixture.emit("group_result", **result)
        raise SystemExit(1) from exc
    margins = {
        name: row["gain_vp"][bench.A] - row["gain_vp"][bench.B]
        for name, row in result["arms"].items()
    }
    after_hold = margins["hold-follow"] - margins["hold-omit"]
    after_screen = margins["screen-follow"] - margins["screen-omit"]
    result.update(
        status="observed",
        margins=margins,
        follow_after_hold=after_hold,
        follow_after_screen=after_screen,
        interaction=after_screen - after_hold,
    )
    expected = {key: value for key, value in reference.items() if key != "setup_evidence"}
    observed = json.loads(json.dumps({"group": fixture.GROUP, **result}))
    drift = [
        key for key in expected.keys() | observed.keys() if expected.get(key) != observed.get(key)
    ]
    if drift:
        fixture.emit("reproduction_drift", fields=sorted(drift))
        raise bench.BenchmarkGap("The Layout C run differs from its sealed four-arm receipt.")
    if frozen_choice is not None:
        bench.require(
            screen_offers is not None
            and len(screen_offers) == len(policy_target.PAIRS)
            and all(offer == screen_offers[0] for offer in screen_offers),
            "Matched Screen arms did not capture the same child offer.",
        )
        assert screen_offers is not None
        link = policy_target.build_link(
            reference, observed, frozen_choice, screen_offers[0], origin, endpoints
        )
        fixture.emit("development_policy_target", **link, link_hash=payload_digest(link))
    fixture.emit("group_result", **result)
    if scoring_timing and timing_protocol is not None:
        try:
            timing.run(timing_protocol, observed, branches, endpoints)
        except ERRORS as exc:
            fixture.emit("timing_gap", type=type(exc).__name__, detail=str(exc))
            raise SystemExit(1) from exc
