"""Preflight the Stage 4 split-objective development fixture."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from shapely.geometry import Point, Polygon

from scripts import stage4_benchmark_entry as bench
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import (
    _unit_selection,
    canonical_setup_prebattle_smoke_config,
)
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

GROUP = "disruption-mirror-c-split-central-dev"
LAYOUT = "disruption-vs-disruption-layout-3"
TARGET = LAYOUT + "-central-01"
WEST_LOBE = LAYOUT + "-terrain-area-09"
EAST_LOBE = LAYOUT + "-terrain-area-08"
RULE = "outmaneuver-rounds-two-three-objectives"
PREPARE_SECONDS = 120
SCREEN = "army-alpha:screen"
ALLY = "army-alpha:ally"
OPPONENT = "army-beta:opponent"
DEPLOYMENT = {SCREEN: [(11.4, 31.1)], ALLY: [(12.8, 36.65)], OPPONENT: [(32.55, 29.0)]}
DATASHEETS = {
    SCREEN: "core-character-leader",
    ALLY: "core-character-leader",
    OPPONENT: "core-character-leader",
}
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
ARTIFACTS = SOURCE / "event_companion_layouts_2026_06/artifacts"
RECEIPT = ROOT / "docs/stage4-split-objective-receipt.json"


def sealed_receipt() -> bench.Row:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def emit(event: str, **row: object) -> None:
    print(json.dumps({"group": GROUP, "event": event, **row}), flush=True)


def config() -> GameConfig:
    base = canonical_setup_prebattle_smoke_config(game_id=GROUP, private_rng_seed=bench.SEED)
    alpha, beta = base.army_muster_requests

    def selection(unit: str) -> UnitMusterSelection:
        sheet = DATASHEETS[unit]
        return _unit_selection(
            unit_selection_id=unit.split(":")[1],
            datasheet_id=sheet,
            model_profile_id=sheet,
            model_count=1,
        )

    mission = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-" + LAYOUT,
        terrain_layout_id=LAYOUT,
        attacker_player_id=bench.A,
        attacker_force_disposition_id="disruption",
        defender_player_id=bench.B,
        defender_force_disposition_id="disruption",
    )
    return replace(
        base,
        army_muster_requests=(
            replace(
                alpha,
                force_disposition_id="disruption",
                unit_selections=(
                    selection(SCREEN),
                    selection(ALLY),
                ),
            ),
            replace(
                beta, force_disposition_id="disruption", unit_selections=(selection(OPPONENT),)
            ),
        ),
        mission_setup=mission,
        reserve_unit_points=(),
    )


def source_evidence(game: GameConfig) -> bench.Row:
    setup = game.mission_setup.to_payload()
    layout = json.loads(
        (ARTIFACTS / "event-companion-battlefields.json").read_text(encoding="utf-8")
    )
    association = json.loads(
        (ARTIFACTS / "event-companion-objective-associations.json").read_text(encoding="utf-8")
    )
    mission = json.loads(
        (SOURCE / "event_companion_2026_06_artifacts/primary-scoring.json").read_text(
            encoding="utf-8"
        )
    )
    (layout_row,) = [row for row in layout["layouts"] if row["layout_id"] == LAYOUT]
    (linked,) = [
        o["terrain_area_ids"]
        for o in setup["objective_terrain_areas"]
        if o["objective_marker_id"] == TARGET
    ]
    bench.require(
        set(linked)
        == set(association["objectives"][TARGET]["terrain_area_ids"])
        == {WEST_LOBE, EAST_LOBE}
        and layout["source_pdf_sha256"] == association["source_pdf_sha256"],
        "The runtime and reviewed evidence disagree about the two central linked areas.",
    )
    polygons = {
        area["terrain_area_id"]: [[p["x_inches"], p["y_inches"]] for p in area["footprint_polygon"]]
        for area in setup["terrain_areas"]
        if area["terrain_area_id"] in linked
    }
    (primary,) = [
        row
        for row in mission["primary_missions"]
        if row["primary_mission_id"] == "primary-outmaneuver"
    ]
    (rule,) = [row for row in primary["scoring_rules"] if row["rule_id"] == RULE]
    bench.require(
        (rule["timing"], rule["turn_scope"], rule["condition"], rule["victory_points"])
        == (
            "battle_rounds_two_and_three_command_phase",
            "own_player_turn",
            "each_non_home_objective_controlled_battle_rounds_two_and_three",
            5,
        )
        and layout_row["primary_missions"] == ["primary-outmaneuver"] * 2
        and all(
            assignment["primary_mission_id"] == "primary-outmaneuver"
            for assignment in setup["primary_mission_assignments"]
        ),
        "The imported primary does not award five per non-home objective at A3 Command.",
    )
    diameters = {}
    for unit, sheet in DATASHEETS.items():
        (profile,) = next(
            d for d in game.army_catalog.datasheets if d.datasheet_id == sheet
        ).model_profiles
        size = profile.base_size
        bench.require(
            size.kind.value == "circular" and size.diameter_mm == 40.0,
            f"Unexpected actual base for {unit}: {size}.",
        )
        diameters[unit] = size.diameter_mm
        player = bench.B if unit == OPPONENT else bench.A
        (zone,) = [z["shape"] for z in setup["deployment_zones"] if z["player_id"] == player]
        (boundary,) = zone["polygons"]
        polygon = Polygon([(v["x"], v["y"]) for v in boundary["vertices"]])
        (point,) = DEPLOYMENT[unit]
        bench.require(
            polygon.covers(Point(point).buffer(size.diameter_mm / 50.8, quad_segs=64)),
            f"Actual {size.diameter_mm} mm base leaves the deployment zone for {unit}.",
        )
    return {
        "target": TARGET,
        "layout_source": {
            "package": layout["source_package_id"],
            "artifact_hash": layout["package_hash"],
            "pdf_sha256": layout["source_pdf_sha256"],
            "page": layout_row["source_page"],
            "association_review_sha256": association["source_review_sha256"],
        },
        "mission_source": {
            "package": setup["source_id"],
            "version": setup["source_version"],
            "scoring_artifact_hash": mission["package_hash"],
            "rule": rule,
        },
        "linked_footprints_inches": polygons,
        "base_diameters_mm": diameters,
    }


def coordinates(context: PlayerDecisionContext) -> tuple[int, str | None, str | None, str]:
    return (
        context.observation["battle_round"],
        context.observation["active_player_id"],
        context.route.battle_phase,
        context.route.decision_type,
    )


def ordinary(context: PlayerDecisionContext) -> PolicyAction:
    kind = context.route.decision_type
    if kind in bench.ISSUED_CHOICES:
        return bench.finite(context, bench.ISSUED_CHOICES[kind])
    if kind in {"select_deployment_unit", "select_movement_unit"}:
        order = (SCREEN, ALLY) if context.route.actor_id == bench.A else (OPPONENT,)
        prefix = "deploy:" if kind == "select_deployment_unit" else ""
        menu = FiniteCandidateSet.from_context(context)
        choice = next(
            (prefix + unit for unit in order if prefix + unit in menu.candidate_ids), None
        )
        bench.require(
            choice is not None, f"Missing frozen {kind} option from {menu.candidate_ids}."
        )
        assert choice is not None
        return menu.select(context, choice)
    if kind == "submit_stratagem_target_proposal":
        bench.require(
            context.request["payload"]["declinable"] is True,
            "Unexpected mandatory Stratagem reaction.",
        )
        return context.propose(stratagem_decline_payload())
    if kind == bench.MOVE_ACTION:
        return bench.finite(context, bench.HOLD)
    raise bench.BenchmarkGap(f"Unexpected native setup route {kind}.")


def prepare(checkpoint: Path) -> None:
    """Rebuild exactly one documented setup through native placement."""
    try:
        prepare_setup(checkpoint)
    except (bench.BenchmarkGap, GameLifecycleError, PolicyError) as exc:
        causes = []
        cause = exc.__cause__
        while cause is not None:
            causes.append({"type": type(cause).__name__, "detail": str(cause)})
            cause = cause.__cause__
        emit("gap", stage="setup", detail=str(exc), causes=causes)
        raise


def prepare_setup(checkpoint: Path) -> None:
    expected = sealed_receipt()["setup_evidence"]
    roster = {"deployment": DEPLOYMENT, "datasheets": DATASHEETS}
    bench.require(json.loads(json.dumps(roster)) == expected["roster"], "The setup roster drifted.")
    emit("setup_start", **roster)
    game = config()
    emit("source_verified", **source_evidence(game))
    session = LocalGameSession()
    status = session.start(game)
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = session.advance_until_decision_or_terminal()
    bench.require(
        status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION,
        f"Native startup stopped at {status.status_kind}: {status.message}",
    )
    placed = []
    placements = []
    for _ in range(40):
        context = bench.actor(session)
        route = coordinates(context)
        request_id = context.request["request_id"]
        emit("setup_offer", route=route, actor=context.route.actor_id, request_id=request_id)
        if route == (1, bench.A, "movement", "select_movement_unit"):
            bench.require(set(placed) == set(DEPLOYMENT), "Missing a native deployment receipt.")
            saved = session.to_persistence_payload()
            staged = checkpoint.with_suffix(checkpoint.suffix + ".tmp")
            staged.write_text(json.dumps(saved), encoding="utf-8")
            reopened = LocalGameSession.from_persistence_payload(
                json.loads(staged.read_text(encoding="utf-8"))
            )
            bench.require(
                reopened.to_persistence_payload() == saved
                and bench.views(session) == bench.views(reopened),
                "Setup checkpoint failed strict restore of state or actor views.",
            )
            latch = {
                "checkpoint": saved["content_hash"],
                "event_log": saved["event_log_hash"],
                "request_id": request_id,
                "placed": placed,
                "rng_draws": saved["rng_state"]["draw_count"],
                "records": session.decision_record_count(),
            }
            bench.require(
                placements == expected["placement_receipts"] and latch == expected["latch"],
                "The native placement receipts or restored setup checkpoint drifted.",
            )
            staged.replace(checkpoint)
            emit("setup_latched", **latch)
            return
        if context.route.decision_type == "submit_deployment_placement":
            action = bench.placement(context, {"deployment": DEPLOYMENT})
            pending = context.observation["pending_proposal"]
            assert pending is not None
            assert action.proposal_json is not None
            unit = pending["unit_instance_id"]
            emit(
                "placement_attempt",
                unit=unit,
                request_id=request_id,
                proposal_hash=payload_digest(json.loads(action.proposal_json)),
            )
            status = bench.submit(session, context, action)
            receipt = {
                "unit": unit,
                "request_id": request_id,
                "status": status.status_kind.value,
                "detail": status.message,
                "native": status.payload
                if status.status_kind is LifecycleStatusKind.INVALID
                else None,
            }
            emit("placement_result", **receipt)
            placements.append(receipt)
            bench.require(
                status.status_kind
                in {LifecycleStatusKind.ADVANCED, LifecycleStatusKind.WAITING_FOR_DECISION},
                f"{unit} placement {request_id}: {status.status_kind}: {status.message}",
            )
            placed.append(unit)
            if status.status_kind is LifecycleStatusKind.ADVANCED:
                status = session.advance_until_decision_or_terminal()
                bench.require(
                    status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION,
                    f"After {unit} deployment: {status.status_kind}: {status.message}",
                )
            continue
        bench.commit(session, context, ordinary(context))
    raise bench.BenchmarkGap("The 40-decision setup cap was exhausted.")
