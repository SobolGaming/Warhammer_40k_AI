"""Compare the native scoring windows on two sealed Layout C trajectories."""

from __future__ import annotations

import json

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_split_objective as fixture
from scripts import stage4_split_objective_replay as replay
from scripts.stage2_preservation_timing import SEED
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.player_policy import payload_digest

SCHEMA = "stage4-layout-c-scoring-timing-v1"
ARMS = ("screen-omit", "screen-follow")
DECISION_CAP = 60
WALL_SECONDS = replay.WALL_SECONDS + 600
HORIZON = (4, bench.B, "movement", "select_movement_unit")
B2_END = replay.BOUNDARIES[2]
A3_COMMAND = replay.BOUNDARIES[3]
B3_COMMAND = (3, bench.B, "command", "phase_end")
A4_COMMAND = (4, bench.A, "command", "phase_end")
A4_END = (4, bench.A, "fight", "turn_end")
CONTINUATION_BOUNDARIES = (
    (3, bench.A, "fight", "turn_end"),
    B3_COMMAND,
    (3, bench.B, "fight", "turn_end"),
    A4_COMMAND,
    A4_END,
    (4, bench.B, "command", "phase_end"),
)
LATE_RULE = "outmaneuver-round-four-onwards-objectives"
WINDOW_AWARDS = {
    A3_COMMAND: (fixture.RULE, 5),
    B3_COMMAND: (fixture.RULE, 5),
    A4_END: (LATE_RULE, 6),
}


def protocol(source: bench.Row) -> bench.Row:
    """Verify the later clause in the same retained artifact as the sealed run."""
    artifact = fixture.SOURCE / "event_companion_2026_06_artifacts/primary-scoring.json"
    data = json.loads(artifact.read_text(encoding="utf-8"))
    mission = next(
        row
        for row in data["primary_missions"]
        if row["primary_mission_id"] == "primary-outmaneuver"
    )
    rule = next(row for row in mission["scoring_rules"] if row["rule_id"] == LATE_RULE)
    bench.require(
        data["package_hash"] == source["mission_source"]["scoring_artifact_hash"]
        and (rule["timing"], rule["turn_scope"], rule["condition"], rule["victory_points"])
        == (
            "battle_round_four_onwards_turn_end",
            "own_player_turn",
            "each_non_home_objective_controlled_battle_round_four_onwards",
            6,
        ),
        "The retained Outmanoeuvre turn-end clause drifted.",
    )
    return {
        "schema": SCHEMA,
        "partition": "development",
        "training_rows": 0,
        "arms": ARMS,
        "seed": SEED,
        "target": fixture.TARGET,
        "layout_source": source["layout_source"],
        "linked_footprints_inches": source["linked_footprints_inches"],
        "mission_source": source["mission_source"],
        "round_four_onwards_rule": rule,
        "october_scoring_clause_verified": False,
        "start_offer": replay.HORIZON,
        "stop_offer": HORIZON,
        "boundaries": (B2_END, A3_COMMAND, *CONTINUATION_BOUNDARIES),
        "continuation": "issued Hold, ordinary phase completion and decline",
        "continuation_decision_cap": DECISION_CAP,
        "wall_seconds": WALL_SECONDS,
    }


def matched_paths(reference: bench.Row) -> bench.Row:
    menus = {arm: reference["arms"][arm]["menus"] for arm in ARMS}
    shared = {}
    for index, role in ((0, "screen"), (2, "respond")):
        omit, follow = (menus[arm][index] for arm in ARMS)
        bench.require(
            omit["role"] == follow["role"] == role
            and omit["selected"] == follow["selected"] != bench.HOLD
            and [p for p in omit["native_probes"] if p["id"] == omit["selected"]]
            == [p for p in follow["native_probes"] if p["id"] == follow["selected"]]
            and any(
                probe["id"] == omit["selected"] and probe["violation"] is None
                for probe in omit["native_probes"]
            ),
            f"Layout C timing arms differ on the native {role} path.",
        )
        shared[role] = omit["selected"]
    return {"shared_path_ids": shared, "sealed_path_menus": menus}


def advance(session: LocalGameSession) -> int:
    bench.require(
        fixture.coordinates(bench.actor(session)) == replay.HORIZON,
        "Expected the sealed A3 Movement offer.",
    )
    context = bench.actor(session)
    for index in range(DECISION_CAP):
        if fixture.coordinates(context) == HORIZON:
            return index
        bench.commit(session, context, fixture.ordinary(context))
        context = bench.actor(session)
    bench.require(
        fixture.coordinates(context) == HORIZON,
        "Layout C timing continuation exhausted its decision cap.",
    )
    return DECISION_CAP


def objective_at(report: bench.Row, boundary: replay.Boundary) -> bench.Row:
    matches = [
        (key, record)
        for key, record in report["objective_boundaries"].items()
        if record["boundary"] == list(boundary)
    ]
    bench.require(len(matches) == 1, f"Expected one target record at {boundary}.")
    key, record = matches[0]
    return {"boundary_id": key, **record["objectives"][fixture.TARGET]}


def timing_outcome(early: bench.Row, continuation: bench.Row) -> bench.Row:
    bench.require(
        continuation["material"]["origin"] == continuation["material"]["endpoint"]
        and continuation["rng_draw_delta"] == 0
        and continuation["active_rng_draws"] == early["active_rng_draws"] == 0,
        "The passive continuation changed material or consumed chance.",
    )
    observed = [
        {"boundary": boundary, **objective_at(report, boundary)}
        for report, boundaries in (
            (early, (B2_END, A3_COMMAND)),
            (continuation, CONTINUATION_BOUNDARIES),
        )
        for boundary in boundaries
    ]
    awards = early["awards"] + continuation["awards"]
    for row in observed:
        boundary = row["boundary"]
        active = boundary[1]
        rule, rate = WINDOW_AWARDS.get(boundary, (None, 0))
        points = rate if row["controller"] == active else 0
        expected_vp = {player: points if player == active else 0 for player in (bench.A, bench.B)}
        target_awards = [
            (award["player"], award["rule"], award["vp_by_objective"][fixture.TARGET])
            for award in awards
            if award["boundary_id"] == row["boundary_id"]
            and fixture.TARGET in award["vp_by_objective"]
        ]
        bench.require(
            row["vp"] == expected_vp
            and target_awards == ([(active, rule, points)] if points else []),
            f"Target VP disagrees with its native window {boundary}.",
        )
    return {"target_boundaries": observed, "a3_awards": early["awards"], **continuation}


def run(
    frozen: bench.Row,
    sealed: bench.Row,
    branches: dict[str, LocalGameSession],
    checkpoints: dict[str, bench.Row],
) -> None:
    evidence = matched_paths(sealed)
    outcomes = {}
    for arm in ARMS:
        early = sealed["arms"][arm]
        start = checkpoints[arm]
        session = branches[arm]
        count = advance(session)
        end = bench.strict_checkpoint(session)
        start_state, end_state = (cp["lifecycle"]["state"] for cp in (start, end))
        bench.require(
            end["rng_state"]["seed"] == start["rng_state"]["seed"]
            and end_state["battlefield_state"] == start_state["battlefield_state"],
            f"{arm} passive continuation changed the battlefield or RNG seed.",
        )
        continuation = replay.score(start, end, boundaries=CONTINUATION_BOUNDARIES)
        prior = {row["player_id"]: row for row in start_state["victory_point_ledgers"]}
        transactions = [
            tx
            for row in end_state["victory_point_ledgers"]
            for tx in row["transactions"][len(prior[row["player_id"]]["transactions"]) :]
        ]
        result = timing_outcome(early, continuation)
        outcomes[arm] = {
            "a3_checkpoint": early["checkpoint"],
            "a3_event_log": early["event_log"],
            "continuation_decisions": count,
            "transactions_after_a3_command": transactions,
            **result,
        }

    def award_difference(boundary: replay.Boundary) -> int:
        omit, follow = (
            next(row for row in outcomes[arm]["target_boundaries"] if row["boundary"] == boundary)
            for arm in ARMS
        )
        follow_margin: int = follow["vp"][bench.A] - follow["vp"][bench.B]
        omit_margin: int = omit["vp"][bench.A] - omit["vp"][bench.B]
        return follow_margin - omit_margin

    result = {
        "protocol": frozen,
        "protocol_hash": payload_digest(frozen),
        "sealed_origin": sealed["origin"],
        "path_evidence": evidence,
        "arms": outcomes,
        "ally_follow_boundary_vp_margin_delta": {
            "a3_command_end": award_difference(A3_COMMAND),
            "a4_command_end": award_difference(A4_COMMAND),
            "a4_turn_end": award_difference(A4_END),
        },
    }
    fixture.emit("development_scoring_timing", **result, evidence_hash=payload_digest(result))
