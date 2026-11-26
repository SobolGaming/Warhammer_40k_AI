"""Reproduce the two Stage 4 development fixtures with the ordinary player facade."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from math import hypot, isclose, sqrt
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from scripts.stage2_preservation_timing import SEED, views
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction, payload_digest
from warhammer40k_core.ai.screen_movement_candidates import generate_normal_move_proposals
from warhammer40k_core.ai.training_admission import VerifiedEpisodeOrigin
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

RECEIPT = Path(__file__).resolve().parents[1] / "docs" / "stage4-benchmark-receipt.json"
BASELINE = "immediate-material-hold-v1"
A, B = "player-a", "player-b"
SCREEN = "army-alpha:scout-redeploy-unit"
ALLY = "army-alpha:deep-strike-unit"
RESERVE = "army-alpha:strategic-reserve-unit"
OPPONENT = "army-beta:scout-redeploy-unit"
HOLD, NORMAL = "remain_stationary", "normal_move"
CASES = ("hold-follow", "screen-follow", "screen-omit")
HORIZON = (4, A, "movement", "select_movement_unit")
BOUNDARIES = (
    (3, A, "fight", "turn_end"),
    (3, B, "fight", "turn_end"),
    (4, A, "command", "phase_end"),
)
RADIUS = 16 / 25.4
DIAGONAL = 5.25 / sqrt(2)
MOVE_ACTION = "select_movement_action"
TRANSIT_REJECT = "enemy_engagement_range_transit_forbidden"
ISSUED_CHOICES = {
    "select_secondary_missions": "fixed:assassination:bring_it_down",
    "select_reserve_declaration": "complete_reserve_declarations",
    "select_redeploy_unit": "complete_redeploys",
    "select_prebattle_action": "complete_prebattle_actions",
    "select_shooting_unit": "complete_shooting_phase",
    "select_charging_unit": "complete_charge_phase",
    "use_stratagem": "decline_stratagem_window",
}

type Row = dict[str, Any]
type Raw = dict[str, tuple[PolicyAction, Row]]
type Areas = dict[str, list[Polygon]]


class BenchmarkGap(RuntimeError):
    """A frozen occurrence, native submission, or replay was unobserved."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkGap(message)


def actor(session: LocalGameSession) -> PlayerDecisionContext:
    request = session.lifecycle.pending_decision_request()
    require(request is not None, "Expected an ordinary pending request.")
    assert request is not None
    view = session.view_for_context(viewer=ViewerContext.for_player(request.actor_id))
    return PlayerDecisionContext.from_view(view, choice_seed=7)


def finite(context: PlayerDecisionContext, option: str) -> PolicyAction:
    return FiniteCandidateSet.from_context(context).select(context, option)


def immediate_material(context: PlayerDecisionContext) -> PolicyAction:
    """Select Hold when both issued actions have zero immediate damage swing."""
    require(
        context.route.decision_type == MOVE_ACTION and context.route.battle_phase == "movement",
        "The baseline requires an ordinary Movement action offer.",
    )
    menu = FiniteCandidateSet.from_context(context)
    require({HOLD, NORMAL}.issubset(menu.candidate_ids), "Baseline comparison options missing.")
    return menu.select(context, HOLD)


def submit(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    action: PolicyAction,
    *,
    probe_id: str | None = None,
) -> LifecycleStatus:
    require(
        (action.actor_id, action.request_id, action.observation_hash)
        == (context.route.actor_id, context.request["request_id"], context.observation_hash),
        "Stale actor action.",
    )
    # Preserve the archived result IDs, including the west-lane rejection.
    before = session.decision_record_count()
    result = probe_id or f"stage4-edge-scoring-v1:{before}"
    viewer = ViewerContext.for_player(action.actor_id)
    if action.option_id is not None:
        return session.submit_viewer_option(
            viewer=viewer,
            request_id=action.request_id,
            result_id=result,
            option_id=action.option_id,
        )
    assert action.proposal_json is not None
    return session.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=action.request_id,
        result_id=result,
        payload=json.loads(action.proposal_json),
    )


def commit(session: LocalGameSession, context: PlayerDecisionContext, action: PolicyAction) -> None:
    before = session.decision_record_count()
    status = submit(session, context, action)
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = session.advance_until_decision_or_terminal()
    require(
        status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and session.decision_record_count() > before,
        f"{context.route.decision_type} stopped at {status.status_kind}: {status.message}",
    )


def make_config(fixture: Row):
    fixture_config = canonical_setup_prebattle_smoke_config(
        game_id=fixture["game_id"],
        private_rng_seed=SEED,
    )
    if fixture["layout"] == 3:
        alpha, beta = fixture_config.army_muster_requests
        template = next(
            x for x in alpha.unit_selections if x.unit_selection_id == "deep-strike-unit"
        )
        units = tuple(
            replace(template, unit_selection_id=x.unit_selection_id)
            if x.unit_selection_id == "scout-redeploy-unit"
            else x
            for x in alpha.unit_selections
        )
        return replace(
            fixture_config, army_muster_requests=(replace(alpha, unit_selections=units), beta)
        )

    layout = "take-and-hold-vs-purge-the-foe-layout-2"
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-" + layout,
        terrain_layout_id=layout,
        attacker_player_id=A,
        attacker_force_disposition_id="take-and-hold",
        defender_player_id=B,
        defender_force_disposition_id="purge-the-foe",
    )
    return replace(fixture_config, mission_setup=setup)


def placement(context: PlayerDecisionContext, fixture: Row) -> PolicyAction:
    pending = context.observation["pending_proposal"]
    assert pending is not None
    unit = pending["unit_instance_id"]
    payload = {
        k: pending[k]
        for k in (
            "proposal_kind",
            "game_id",
            "ruleset_descriptor_hash",
            "setup_step",
            "player_id",
            "unit_instance_id",
            "placement_kind",
            "context",
        )
    }
    payload["proposal_request_id"] = pending["request_id"]
    payload["model_placements"] = [
        {
            "army_id": unit.split(":")[0],
            "player_id": context.route.actor_id,
            "unit_instance_id": unit,
            "model_instance_id": model_id,
            "pose": {
                "position": {"x": x, "y": y, "z": 0.0},
                "facing": {"degrees": 180.0 if unit == OPPONENT else 0.0},
            },
        }
        for model_id, (x, y) in zip(
            pending["model_instance_ids"], fixture["deployment"][unit], strict=True
        )
    ]
    return context.propose(payload)


def objective_areas(setup: MissionSetup) -> Areas:
    source = setup.to_payload()
    areas = {
        area["terrain_area_id"]: Polygon(
            [(p["x_inches"], p["y_inches"]) for p in area["footprint_polygon"]]
        )
        for area in source["terrain_areas"]
    }
    return {
        o["objective_marker_id"]: [areas[k] for k in o["terrain_area_ids"]]
        for o in source["objective_terrain_areas"]
    }


def raw_moves(context: PlayerDecisionContext) -> Raw:
    raw = {}
    for action in generate_normal_move_proposals(context):
        assert action.proposal_json is not None
        proposal = json.loads(action.proposal_json)
        shape = {k: v for k, v in proposal.items() if k != "proposal_request_id"}
        key = "normal-move:" + payload_digest(shape)
        require(key not in raw, "Duplicate generated movement ID.")
        raw[key] = (action, proposal)
    return raw


def path_points(proposal: Row, end: bool) -> list[tuple[float, float]]:
    return [
        (point["x"], point["y"])
        for path in proposal["witness"]["model_paths"]
        for point in (path["poses"][-1 if end else 0]["position"],)
    ]


def delta(proposal: Row) -> tuple[float, float]:
    (x, y), *_ = path_points(proposal, False)
    (ex, ey), *_ = path_points(proposal, True)
    return ex - x, ey - y


def touches(points: list[tuple[float, float]], polygons: list[Polygon]) -> int:
    return sum(any(poly.distance(Point(x, y)) <= RADIUS for poly in polygons) for x, y in points)


def ranked(
    raw: Raw,
    areas: Areas,
    role: str,
    preference: str,
    ux: float,
    uy: float,
) -> list[str]:
    target = {
        suffix: [p for k, polys in areas.items() if k.endswith(suffix) for p in polys]
        for suffix in ("central-01", "central-02")
    }
    results = []
    for key, (_, proposal) in raw.items():
        dx, dy = delta(proposal)
        length = hypot(dx, dy)
        if (dx * ux + dy * uy) / (length * hypot(ux, uy)) < 0.999:
            continue
        end = path_points(proposal, True)
        ally = touches(end, target["central-01"])
        guard = touches(end, target["central-02"])
        starts = touches(path_points(proposal, False), target["central-02"])
        eligible = {
            "stage": True,
            "screen": guard < starts and ally == 0,
            "follow": ally > 0,
            "guard": guard >= 4,
            "north": guard <= 2,
        }[role]
        if eligible:
            rank = (-ally if role == "follow" else 0, length if preference == "short" else -length)
            results.append((rank, key))
    return [k for _, k in sorted(results, key=lambda row: row[0])]


def vector(raw: Raw, dx: float, dy: float) -> str:
    matches = [
        k
        for k, (_, p) in raw.items()
        if all(isclose(a, b, abs_tol=1e-8) for a, b in zip(delta(p), (dx, dy), strict=True))
    ]
    require(len(matches) == 1, f"Expected one generated translation for ({dx}, {dy}).")
    return matches[0]


def battlefield(session: LocalGameSession) -> Row:
    state = session.lifecycle.state
    assert state is not None
    return state.to_payload()["battlefield_state"]


def trial(
    session: LocalGameSession, context: PlayerDecisionContext, raw: Raw, key: str
) -> str | None:
    fork = session.fork()
    before = battlefield(fork)
    status = submit(fork, context, raw[key][0], probe_id="stage4-local-policy-probe:" + key)
    after = battlefield(fork)
    if status.status_kind is LifecycleStatusKind.INVALID:
        require(after == before, "Rejected native probe changed the battlefield.")
        assert isinstance(status.payload, dict)
        code = status.payload.get("violation_code")
        require(isinstance(code, str), f"Missing native violation: {status.message}")
        return code
    require(
        status.status_kind
        in {LifecycleStatusKind.ADVANCED, LifecycleStatusKind.WAITING_FOR_DECISION},
        f"Unresolved native probe: {status.status_kind}",
    )
    moved = {
        m["model_instance_id"]: m["pose"]
        for a in after["placed_armies"]
        for u in a["unit_placements"]
        for m in u["model_placements"]
    }
    require(
        all(moved[p["model_id"]] == p["poses"][-1] for p in raw[key][1]["witness"]["model_paths"]),
        "Native probe failed to apply all endpoints.",
    )
    return None


def capped(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    raw: Raw,
    order: list[str],
    cap: int,
) -> list[list[str | None]]:
    before = payload_digest(session.lifecycle.to_payload())
    result = [[key, trial(session, context, raw, key)] for key in order[:cap]]
    require(
        payload_digest(session.lifecycle.to_payload()) == before, "Probe mutated its live parent."
    )
    return result


def menu_row(
    raw: Raw,
    selected: str | None,
    *,
    offered: list[str] | None = None,
    rejections: list[list[str | None]] | None = None,
    lost: int | None = None,
    excluded: int | None = None,
) -> list[Any]:
    return [
        len(raw),
        payload_digest(list(raw)),
        selected,
        offered,
        rejections or [],
        lost,
        excluded,
    ]


def move(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    role: str,
    plan: list[Any],
    areas: Areas,
    history: Row,
    *,
    audit: bool,
) -> None:
    raw = raw_moves(context)
    preference, dx, dy = plan
    if preference == "vector":
        if role == "screen":
            require(
                all(
                    touches(path_points(p, True), polys) == 0
                    for _, p in raw.values()
                    for polys in areas.values()
                ),
                "A west-lane S candidate can touch an objective.",
            )
        key = vector(raw, dx, dy)
        west_audit(session, context, raw, key, history, audit)
        commit(session, context, raw[key][0])
        history["menus"].append(menu_row(raw, key))
        return
    order = ranked(raw, areas, role, preference, dx, dy)
    probes = capped(session, context, raw, order, 1 if role == "stage" else 2)
    accepted = [key for key, code in probes if code is None]
    require(bool(accepted), f"No accepted generated {role} move inside the cap.")
    key = accepted[0]
    commit(session, context, raw[key][0])
    history["menus"].append(
        menu_row(
            raw,
            key,
            offered=accepted,
            rejections=[r for r in probes if r[1] is not None],
            lost=len(order) - len(probes),
            excluded=len(raw) - len(order),
        )
    )


def west_audit(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    raw: Raw,
    key: str,
    history: Row,
    enabled: bool,
) -> None:
    if enabled:
        order = [key, *(k for k in raw if k != key)]
        probes = capped(session, context, raw, order, 2)
        history["retro"].append(
            {
                "attempts": probes,
                "accepted": [k for k, code in probes if code is None],
                "cap_lost": len(raw) - len(probes),
            }
        )


def west_b3(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    case: str,
    history: Row,
    *,
    audit: bool,
) -> None:
    visible = context.observation["battlefield_view"]
    assert visible is not None
    board = visible["authoritative"]["models_by_id"]
    placed = {
        unit: [
            (m["pose"]["position"]["x_inches"], m["pose"]["position"]["y_inches"])
            for m in board.values()
            if m["rules_unit_instance_id"] == unit and m["state"] == "placed"
        ]
        for unit in (SCREEN, OPPONENT)
    }
    require((len(placed[SCREEN]), len(placed[OPPONENT])) == (3, 5), "West formation drift.")
    clear = all(
        LineString([(x, y), (x + DIAGONAL, y + DIAGONAL)]).distance(Point(sx, sy)) > 2 + 2 * RADIUS
        for x, y in placed[OPPONENT]
        for sx, sy in placed[SCREEN]
    )
    if clear:
        commit(session, context, finite(context, NORMAL))
        move(
            session,
            actor(session),
            "reply",
            ["vector", DIAGONAL, DIAGONAL],
            {},
            history,
            audit=audit,
        )
        return
    if case == "screen-follow":
        fork = session.fork()
        commit(fork, context, finite(context, NORMAL))
        offer = actor(fork)
        raw = raw_moves(offer)
        key = vector(raw, DIAGONAL, DIAGONAL)
        west_audit(fork, offer, raw, key, history, audit)
        before = battlefield(fork)
        status = submit(fork, offer, raw[key][0])
        assert isinstance(status.payload, dict)
        require(
            status.status_kind is LifecycleStatusKind.INVALID
            and status.payload.get("violation_code") == TRANSIT_REJECT
            and battlefield(fork) == before,
            "West B3 transit rejection drifted.",
        )
        cp = fork.to_persistence_payload()
        replay = ReplayRunner.from_payload(cp["replay_artifact"]).run()
        require(
            replay.reproduced_exactly and replay.final_event_log_hash == cp["event_log_hash"],
            "West B3 rejection failed exact replay.",
        )
        history["rejected_fork"] = [cp["content_hash"], cp["event_log_hash"]]
        history["menus"].append(menu_row(raw, key, rejections=[[key, TRANSIT_REJECT]]))
    commit(session, context, finite(context, HOLD))


def guard_b3(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    areas: Areas,
    history: Row,
) -> None:
    scratch = session.fork()
    commit(scratch, context, finite(context, NORMAL))
    offer = actor(scratch)
    raw = raw_moves(offer)
    guard = ranked(raw, areas, "guard", "short", -8, -3)
    north = ranked(raw, areas, "north", "short", -1, 1)
    order = guard[:1] + north[:1] + guard[1:] + north[1:]
    probes = capped(scratch, offer, raw, order, 2)
    accepted = [key for key, code in probes if code is None]
    key = next((key for key in guard + north if key in accepted), None)
    if key is None:
        commit(session, context, finite(context, HOLD))
    else:
        commit(session, context, finite(context, NORMAL))
        commit(session, actor(session), raw[key][0])
    history["menus"].append(
        menu_row(
            raw,
            key,
            offered=accepted,
            rejections=[r for r in probes if r[1] is not None],
            lost=len(order) - len(probes),
            excluded=len(raw) - len(order),
        )
    )


def schedule(fixture: Row, case: str) -> dict[tuple[int, str], tuple[str, list[Any]]]:
    if case == "stem":
        return {(r, unit): ("stage", spec) for r, unit, *spec in fixture["stem"]}
    if case == "finish":
        return {}
    west = fixture["layout"] == 3
    moves = {}
    if case != "hold-follow":
        moves[3, SCREEN] = ("screen", ["vector", 0, -8.75] if west else ["long", 1, 1])
    if case != "screen-omit":
        diagonal_e = 7.5 / sqrt(2)
        moves[3, ALLY] = (
            "follow",
            ["vector", diagonal_e, -diagonal_e] if west else ["short", 0, -1],
        )
    return moves


def advance(
    session: LocalGameSession,
    fixture: Row,
    areas: Areas,
    case: str,
    *,
    audit: bool = False,
) -> Row:
    moves = schedule(fixture, case)
    seen = set()
    history: Row = {"menus": [], "retro": []}
    west = fixture["layout"] == 3
    for _ in range(100):
        c = actor(session)
        rnd, turn = c.observation["battle_round"], c.observation["active_player_id"]
        kind, request = c.route.decision_type, c.request["payload"]
        unit = request.get("unit_instance_id")
        if case == "stem" and (rnd, turn, kind, unit) == (3, A, MOVE_ACTION, SCREEN):
            break
        if case == "finish" and (rnd, turn, c.route.battle_phase, kind) == HORIZON:
            break
        if case in CASES and (rnd, turn, kind) == (3, B, MOVE_ACTION):
            require(unit == OPPONENT, "Unexpected active B3 unit.")
            if west:
                west_b3(session, c, case, history, audit=audit)
            else:
                guard_b3(session, c, areas, history)
            after = actor(session).observation
            require(
                (after["battle_round"], after["active_player_id"]) == (3, B),
                "Scoring proceeded past B3 preflight.",
            )
            break
        if kind in ISSUED_CHOICES:
            action = finite(c, ISSUED_CHOICES[kind])
        elif kind in {"select_deployment_unit", "select_movement_unit"}:
            deploying = kind == "select_deployment_unit"
            order = (
                (OPPONENT,)
                if c.route.actor_id == B
                else (ALLY, SCREEN, RESERVE)
                if deploying or (rnd == 1 and not west)
                else (SCREEN, ALLY, RESERVE)
            )
            prefix = "deploy:" if deploying else ""
            offered = FiniteCandidateSet.from_context(c)
            choice = next(
                (prefix + unit for unit in order if prefix + unit in offered.candidate_ids), None
            )
            require(choice is not None, "Frozen ordinary unit selection missing.")
            assert choice is not None
            action = offered.select(c, choice)
        elif kind == "submit_deployment_placement":
            action = placement(c, fixture)
        elif kind == MOVE_ACTION:
            if case == "hold-follow" and (rnd, unit) == (3, SCREEN):
                action = immediate_material(c)
                history["baseline_option"] = action.option_id
            else:
                action = finite(c, NORMAL if (rnd, unit) in moves else HOLD)
        elif kind == "submit_movement_proposal":
            proposal = request["proposal_request"]
            key = (rnd, proposal["unit_instance_id"])
            require(
                key in moves and key not in seen and proposal["proposal_kind"] == NORMAL,
                "Unscheduled ordinary Normal Move.",
            )
            role, plan = moves[key]
            move(session, c, role, plan, areas, history, audit=audit)
            seen.add(key)
            continue
        elif kind == "submit_stratagem_target_proposal":
            require(request["declinable"] is True, "Unscheduled mandatory reaction.")
            action = c.propose(stratagem_decline_payload())
        else:
            raise BenchmarkGap(f"Unexpected native route {kind} at {rnd}, {turn}.")
        commit(session, c, action)
    else:
        raise BenchmarkGap("The 100-decision continuation cap was exhausted.")
    require(seen == set(moves), "Incomplete frozen move schedule.")
    return history


def material(state: Row) -> dict[str, int]:
    return {
        m["model_instance_id"]: m["wounds_remaining"]
        for army in state["army_definitions"]
        for unit in army["units"]
        for m in unit["own_models"]
    }


def scoring_oc(state: Row, targets: list[str]) -> list[list[list[int]]]:
    values = []
    for boundary in BOUNDARIES:
        (record,) = [
            r
            for r in state["objective_control_records"]
            if (r["battle_round"], r["active_player_id"], r["phase"], r["timing"]) == boundary
        ]
        row = [
            [
                sum(x["score"] for x in result["scores"] if x["player_id"] == player)
                for player in (A, B)
            ]
            for suffix in targets
            for result in record["results"]
            if result["objective_id"].endswith(suffix)
        ]
        require(len(row) == len(targets), "Missing target OC at the fixed scoring boundary.")
        values.append(row)
    return values


def endpoint(session: LocalGameSession, common: Row, fixture: Row) -> Row:
    cp = session.to_persistence_payload()
    actor_views = views(session)
    restored = LocalGameSession.from_persistence_payload(cp)
    require(
        restored.to_persistence_payload() == cp and views(restored) == actor_views,
        "Strict restore altered history or an actor view.",
    )
    replay = ReplayRunner.from_payload(cp["replay_artifact"]).run()
    require(
        replay.reproduced_exactly and replay.final_event_log_hash == cp["event_log_hash"],
        "Independent endpoint replay drifted.",
    )
    require(
        cp["rng_state"]["seed"] == common["rng_state"]["seed"]
        and cp["rng_state"]["draw_count"] == 0
        and common["rng_state"]["draw_count"] == 0,
        "Fixed-seed chance diverged.",
    )
    state = session.lifecycle.state
    assert state is not None
    raw = state.to_payload()
    require(material(raw) == material(common["lifecycle"]["state"]), "Material changed.")
    if fixture["layout"] == 3:
        require(
            all(
                c["unit_instance_id"] != SCREEN or c["effective_objective_control"] == 0
                for record in raw["objective_control_records"]
                for result in record["results"]
                for c in result["contributors"]
            ),
            "West-lane S supplied direct OC.",
        )
    return {
        "record_count": session.decision_record_count(),
        "checkpoint": cp["content_hash"],
        "event_log": cp["event_log_hash"],
        "vp": [state.victory_point_total(p) for p in (A, B)],
        "oc": scoring_oc(raw, fixture["targets"]),
    }


def baseline_scores(fixture: Row) -> Row:
    start_a, start_b = fixture["start_vp"]

    def gain(case: str) -> int:
        va, vb = fixture["arms"][case]["vp"]
        return (va - start_a) - (vb - start_b)

    hold, screen, omit = (gain(case) for case in CASES)
    return {
        "group": fixture["group"],
        "baseline": BASELINE,
        "baseline_margin_gain": hold,
        "screen_margin_gain": screen,
        "omit_margin_gain": omit,
        "screen_minus_baseline": screen - hold,
    }


def check_receipt(data: Row) -> None:
    require(
        data["schema"] == "stage4-development-v1"
        and data["baseline"] == BASELINE
        and tuple(data["horizon"]) == HORIZON
        and tuple(data["cases"]) == CASES
        and set(data["fixtures"]) == {"west", "guard"},
        "Unknown development receipt contract.",
    )
    require(
        len({f["group"] for f in data["fixtures"].values()}) == 2,
        "The two complete development groups must stay distinct.",
    )
    for name, fixture in data["fixtures"].items():
        require(
            set(fixture["arms"]) == set(CASES) and set(fixture["menus"]) == {"stem", *CASES},
            "Missing a fixture sibling or the shared stem.",
        )
        for leg, rows in fixture["menus"].items():
            for raw, fingerprint, selected, offered, rejects, lost, excluded in rows:
                require(0 < raw <= 32 and len(fingerprint) == 64, "Invalid raw inventory.")
                if name == "west":
                    require(
                        offered is None
                        and lost is None
                        and excluded is None
                        and selected
                        and len(rejects) <= 1
                        and all(k == selected for k, _ in rejects),
                        "Historical direct submissions cannot claim a live validation cap.",
                    )
                else:
                    require(
                        offered is not None
                        and lost >= 0
                        and excluded >= 0
                        and raw == len(offered) + len(rejects) + lost + excluded
                        and len(offered) + len(rejects) <= (1 if leg == "stem" else 2)
                        and (selected in offered if offered else selected is None),
                        "Live cap inventory or selected candidate drift.",
                    )
    west = data["fixtures"]["west"]
    for case in CASES:
        for direct, audit in zip(
            west["menus"][case], west["retrospective_menus"][case], strict=True
        ):
            probes = audit["attempts"]
            require(
                len(probes) == 2
                and probes[0][0] == direct[2]
                and (probes[0][1] is not None) == bool(direct[4])
                and audit["accepted"] == [key for key, code in probes if code is None]
                and direct[0] == len(probes) + audit["cap_lost"],
                "Retrospective native audit is inconsistent with the sealed live submission.",
            )


def reproduce(fixture: Row, *, audit: bool) -> None:
    config = make_config(fixture)
    common = LocalGameSession()
    status = common.start(config)
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = common.advance_until_decision_or_terminal()
    require(
        status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, "Ordinary startup failed."
    )
    areas = objective_areas(config.mission_setup)
    stem = advance(common, fixture, areas, "stem")
    origin = VerifiedEpisodeOrigin.from_session(common, config=config).to_payload()
    saved = common.to_persistence_payload()
    require(
        origin["engine_build_id"] == fixture["engine_build_id"], "Pinned runtime build drifted."
    )
    require(
        [origin["prefix_record_count"], origin["origin_checkpoint_hash"], saved["content_hash"]]
        == fixture["origin"]
        and stem["menus"] == fixture["menus"]["stem"],
        "Shared ordinary origin or staging menu drifted.",
    )
    require(
        [row["victory_points"] for row in saved["lifecycle"]["state"]["victory_point_ledgers"]]
        == fixture["start_vp"],
        "Shared origin VP drifted.",
    )
    print(json.dumps({"group": fixture["group"], "verified_origin": fixture["origin"]}), flush=True)

    # Check every B3 occurrence before advancing any scored arm to the horizon.
    sessions = {}
    for case in CASES:
        session = common.fork()
        seen = advance(session, fixture, areas, case, audit=audit)
        require(seen["menus"] == fixture["menus"][case], f"{case} movement menus drifted.")
        if "rejected_fork" in seen:
            require(seen["rejected_fork"] == fixture["rejected_fork"], "B3 rejection drifted.")
        if audit:
            require(seen["retro"] == fixture["retrospective_menus"][case], f"{case} audit drifted.")
        if case == "hold-follow":
            require(seen["baseline_option"] == HOLD, "Baseline action drifted.")
        sessions[case] = session
        print(json.dumps({"case": case, "native_menus_verified": True}), flush=True)

    for case, session in sessions.items():
        advance(session, fixture, areas, "finish")
        actual = endpoint(session, saved, fixture)
        require(actual == fixture["arms"][case], f"{case} scored endpoint drifted: {actual}")
        print(json.dumps({"case": case, "strict_replay": True, **actual}), flush=True)
    require(common.to_persistence_payload() == saved, "An arm mutated the common origin.")
    print(json.dumps({**baseline_scores(fixture), "training_rows": 0}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family", choices=("west", "guard"), help="Reproduce one development family."
    )
    parser.add_argument(
        "--audit-west", action="store_true", help="Also regenerate the retrospective west audit."
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.audit_west and args.family != "west":
        parser.error("--audit-west requires --family west")
    data = json.loads(RECEIPT.read_text(encoding="utf-8"))
    check_receipt(data)
    if args.family is None:
        for fixture in data["fixtures"].values():
            print(json.dumps(baseline_scores(fixture)))
        return
    if args.worker:
        reproduce(data["fixtures"][args.family], audit=args.audit_west)
        return
    cap = 1050 if args.family == "guard" or args.audit_west else 800
    command = [
        sys.executable,
        "-B",
        "-m",
        "scripts.stage4_benchmark_entry",
        "--worker",
        "--family",
        args.family,
    ]
    if args.audit_west:
        command.append("--audit-west")
    try:
        subprocess.run(command, check=True, timeout=cap)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"Unobserved: {args.family} exceeded the {cap}s local wall cap.") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Unobserved: {args.family} exited with {exc.returncode}.") from exc


if __name__ == "__main__":
    main()
