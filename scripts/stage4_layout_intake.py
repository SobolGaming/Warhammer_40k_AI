"""Prove the first prospective Movement intake family through the A2 action only."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from math import hypot
from pathlib import Path

from shapely import to_wkb
from shapely.geometry import Polygon

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_evaluation as evaluation
from scripts import stage4_split_objective as setup_driver
from scripts.stage4_tactical_features import _linked_objectives, _model_geometry
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import (
    _unit_selection,
    canonical_setup_prebattle_smoke_config,
)
from warhammer40k_core.ai import screen_movement_candidates
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.ai.screen_movement_candidates import ScreenMovementGap
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_geometry import measure_model_to_objective
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    LOCATE_AND_DENY_CHOICE_KIND,
    PUNISHMENT_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
)
from warhammer40k_core.engine.replay import ReplayArtifactError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layouts_2026_06.event_companion_full_artifact_types import (  # noqa: E501
    BattlefieldLayoutArtifact,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_primary_scoring_2026_06 import (  # noqa: E501
    event_companion_primary_scoring_artifact,
)

RECIPE = bench.RECEIPT.with_name("stage4-layout-intake-recipe.json")
ORIGIN = (2, bench.A, "movement", bench.MOVE_ACTION)
LAYOUT_C = setup_driver.LAYOUT
NATIVE_PREFLIGHT_ERRORS = (bench.BenchmarkGap, GameLifecycleError, PolicyError, ReplayArtifactError)
DEVELOPMENT_LAYOUTS = {
    "west": "take-and-hold-vs-purge-the-foe-layout-3",
    "guard": "take-and-hold-vs-purge-the-foe-layout-2",
    "layout-c": LAYOUT_C,
    "shooting": LAYOUT_C,
}

# Origin and event commitments from the West/Guard benchmark, West cooperation,
# the Layout C setup latch and origin, and the six Shooting origins in the public
# development receipts at the protocol base. Timing/mechanism reuse Layout C.
# The intake worker needs no outcome-bearing receipt.
DEVELOPMENT_ORIGINS = {
    "west": [
        "fb0441ed6e037bbd70762cb7fb27e3b39c3a18a8ab88e7a3b70680f99767d2b8",
        "f7d263deefb3facb0dfaabe58df7371929dcda0d13488f88b8c7e2ee7c04a393",
        "fb22f83cbb3890e655fc764abc1cbccd22991f2cb7ad398ec7b6f487ab846398",
    ],
    "guard": [
        "4171ab82b3c1ea656c6fb5f7a4f85804f247eb189dda0c1c7e30deb8516096d5",
        "8ec1c330548796ce442e9912d5ee9d480639df2f5a72a9501cd4daecea3e7310",
    ],
    "layout-c": [
        "e54c9b1b2565470ee438200bbf2a688b8bfc4499e627950f1f79695b259357c5",
        "e00f5a8245e52af1f324944d1b31adbd691a9b27e4407ef7b7fb23f115d8af3b",
        "c3e3e6c2ed18825530bf0e57923b278a18c1405e57ef9123759131f230ff347a",
        "60ce229b27f8fede057883a471142c9a32104d71b65fe02b75f1a5fe9febf167",
    ],
    "shooting": [
        "52378b871afbbc54c3bf604d88d2a32c8026675a3f0c13992daedfc25405d06d",
        "282ddb81939e10e0b0792ca27b5ad1060632cf825ec932b97f572e0e1783e0a4",
        "6c841f1a288f6843609876034e518d826cd26338a818af9824234231533f6d00",
        "85f8c3ba6f8eb28d56687e81a821b1700e050f44cbdfab5f292ba57b49e15b74",
        "9b49742542698b40d31c3b7734d9d531f525f4aee8bfb19eaa03b7def685dced",
        "2859e1797e547565b194a3fce22b9257b261e5342768082e13767f7e4afaa224",
        "672646149847b304af683c6fb938839d4380c24601df648b7a61bbdff330c2e2",
        "a4fbdf41f1f0bcecc540508559300237687072216a2dc0a63719fea1ec5d7b1a",
        "5484c2fb3a050a8954a7e5de4441f5fb96755e67167a8c7bb2107489ece97a04",
        "c9c0cb979ba72d6a69694d09d7e65e4f08975e9241061c45a6f07f368908cf30",
        "18138d602ea26fd84ab140121bfdc88032628d4cca6dabbce5f89d6ba68050a9",
        "bef2f7d63892681e95a2ae7c730f17ae4c02ca07ffb9500ea73ed3936f4317ec",
    ],
}
DEVELOPMENT_SCENARIOS = {
    "west": ["layout3-west-lane-dev"],
    "guard": ["layout2-central-guard-dev"],
    "layout-c": ["disruption-mirror-c-split-central-dev"],
    "shooting": ["disruption-mirror-c-split-central-dev", "layout-c-flatboard-shooting-dev"],
}


class IntakeGap(bench.BenchmarkGap):
    """Stable preflight disposition with no outcome data."""

    def __init__(self, code: str, **details: object) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def need(condition: bool, code: str) -> None:
    if not condition:
        raise IntakeGap(code)


def load_recipe() -> bench.Row:
    return json.loads(
        RECIPE.read_text(encoding="utf-8"), object_pairs_hook=evaluation._unique_object
    )


def mission(layout: str, pairing: list[str]) -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=bench.warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-" + layout,
        terrain_layout_id=layout,
        attacker_player_id=bench.A,
        defender_player_id=bench.B,
        attacker_force_disposition_id=pairing[0],
        defender_force_disposition_id=pairing[1],
    )


def polygon_key(vertices: list[tuple[float, float]]) -> str:
    return to_wkb(Polygon(vertices).normalize(), hex=True, byte_order=1)


def geometry_key(setup: MissionSetup, *, flat: bool = False) -> str:
    data = setup.to_payload()
    footprints = [
        polygon_key([(p["x_inches"], p["y_inches"]) for p in area["footprint_polygon"]])
        for area in data["terrain_areas"]
    ]
    zones = [
        sorted(
            polygon_key([(p["x"], p["y"]) for p in boundary["vertices"]])
            for boundary in zone["shape"]["polygons"]
        )
        for zone in data["deployment_zones"]
    ]
    return payload_digest(
        [
            data["battlefield_width_inches"],
            data["battlefield_depth_inches"],
            sorted(zones),
            [] if flat else sorted(footprints),
        ]
    )


def linked_footprint_key(setup: MissionSetup, target: str) -> str:
    """Match the linked-footprint geometry binding published by stage4_policy_target."""
    data = setup.to_payload()
    (links,) = [
        row["terrain_area_ids"]
        for row in data["objective_terrain_areas"]
        if row["objective_marker_id"] == target
    ]
    return payload_digest(
        sorted(
            [[point["x_inches"], point["y_inches"]] for point in area["footprint_polygon"]]
            for area in data["terrain_areas"]
            if area["terrain_area_id"] in links
        )
    )


def source_inventory(recipe: bench.Row) -> tuple[MissionSetup, bench.Row, bench.Row, list[int]]:
    layouts, manifest, used = development_inventory()
    page = recipe["source_page"]
    need(page == next(p for p in range(9, 54) if p not in used), "candidate_page_order")
    setup, reserve = source_candidate(recipe, layouts[recipe["layout"]], manifest)
    need(
        all(
            set(reserve["geometry_sha256"]).isdisjoint(dev["geometry_sha256"])
            for dev in manifest["families"]
        ),
        "development_geometry_overlap",
    )
    return setup, manifest, reserve, used


def development_inventory() -> tuple[dict[str, BattlefieldLayoutArtifact], bench.Row, list[int]]:
    artifact = evaluation.event_layouts.battlefield_artifact()
    scoring = event_companion_primary_scoring_artifact()
    layouts = {row.layout_id: row for row in artifact.layouts}
    pages = sorted(row.source_page for row in layouts.values())
    need(pages == list(range(9, 54)), "layout_inventory_drift")
    used = sorted({layouts[key].source_page for key in DEVELOPMENT_LAYOUTS.values()})
    manifest: bench.Row = {
        "schema": evaluation.SPLIT_SCHEMA,
        "layout_release": {
            "package": artifact.source_package_id,
            "artifact_sha256": artifact.package_hash,
            "pdf_sha256": artifact.source_pdf_sha256,
        },
        "families": [],
    }
    for name, layout in DEVELOPMENT_LAYOUTS.items():
        dev = layouts[layout]
        dev_setup = mission(layout, list(dev.force_disposition_pair))
        geometry = [geometry_key(dev_setup, flat=name == "shooting")]
        if name == "layout-c":
            geometry.append(linked_footprint_key(dev_setup, setup_driver.TARGET))
        manifest["families"].append(
            {
                "id": name,
                "partition": "development",
                "scoring_artifact_sha256": scoring.package_hash,
                "source_diagram_pages": [dev.source_page],
                "scenario_lineage": [layout, *DEVELOPMENT_SCENARIOS[name]],
                "geometry_families": [layout],
                "geometry_sha256": geometry,
                "trajectory_sha256": DEVELOPMENT_ORIGINS[name],
            }
        )
    return layouts, manifest, used


def source_candidate(
    recipe: bench.Row, row: BattlefieldLayoutArtifact, manifest: bench.Row
) -> tuple[MissionSetup, bench.Row]:
    setup = mission(row.layout_id, recipe["pairing"])
    need(
        row.source_page == recipe["source_page"]
        and row.layout_id == recipe["layout"]
        and list(row.force_disposition_pair) == recipe["pairing"]
        and list(row.primary_missions)
        == recipe["primary_missions"]
        == [a.primary_mission_id for a in setup.primary_mission_assignments]
        and [a.force_disposition_id for a in setup.primary_mission_assignments] == recipe["pairing"]
        and any(
            o.objective_id == recipe["target"]
            and o.terrain_area_ids
            and o.role in {"central", "expansion"}
            for o in row.objectives
        )
        and recipe["target"] in bench.objective_areas(setup),
        "source_binding_drift",
    )
    return setup, {
        "id": f"reserve-page-{row.source_page}",
        "partition": "reserve",
        "scoring_artifact_sha256": manifest["families"][0]["scoring_artifact_sha256"],
        "source_diagram_pages": [row.source_page],
        "scenario_lineage": [row.layout_id],
        "geometry_families": [row.layout_id],
        "geometry_sha256": [geometry_key(setup), linked_footprint_key(setup, recipe["target"])],
        "trajectory_sha256": [],
    }


def config(recipe: bench.Row, setup: MissionSetup, seed: str) -> GameConfig:
    base = canonical_setup_prebattle_smoke_config(
        game_id="stage4-intake:" + recipe["layout"], private_rng_seed=seed
    )
    sheet = recipe["datasheet"]
    rosters = tuple(
        replace(
            army,
            force_disposition_id=disposition,
            unit_selections=tuple(
                _unit_selection(
                    unit_selection_id=unit.split(":")[1],
                    datasheet_id=sheet,
                    model_profile_id=sheet,
                    model_count=1,
                )
                for unit in recipe["roles"].values()
                if unit.startswith(army.army_id + ":")
            ),
        )
        for army, disposition in zip(base.army_muster_requests, recipe["pairing"], strict=True)
    )
    return replace(base, army_muster_requests=rosters, mission_setup=setup, reserve_unit_points=())


class _PrimaryMissionChoices:
    """Bind each required prefix choice to exact targets in the current actor menu.

    A recipe window uses phase "start_battle" for Locate and Deny, or phase
    "command" and a positive battle_round for Punishment.
    """

    def __init__(self, declarations: object) -> None:
        if not isinstance(declarations, list):
            raise IntakeGap("invalid_primary_mission_choice_declarations")
        self.pending: dict[tuple[str, str, int | None, str | None], tuple[str, ...]] = {}
        self.used: set[tuple[str, str, int | None, str | None]] = set()
        for declaration in declarations:
            need(
                isinstance(declaration, dict)
                and set(declaration)
                == {"actor_id", "choice_kind", "window", "selected_target_ids"},
                "invalid_primary_mission_choice_declaration",
            )
            actor = declaration["actor_id"]
            kind = declaration["choice_kind"]
            window = declaration["window"]
            targets = declaration["selected_target_ids"]
            need(actor in (bench.A, bench.B), "invalid_primary_mission_choice_actor")
            if kind == LOCATE_AND_DENY_CHOICE_KIND:
                need(window == {"phase": "start_battle"}, "invalid_primary_mission_choice_window")
                key = (actor, kind, None, None)
            elif kind == PUNISHMENT_CHOICE_KIND:
                need(
                    isinstance(window, dict)
                    and set(window) == {"battle_round", "phase"}
                    and window["phase"] == BattlePhase.COMMAND.value
                    and type(window["battle_round"]) is int
                    and window["battle_round"] > 0,
                    "invalid_primary_mission_choice_window",
                )
                key = (actor, kind, window["battle_round"], window["phase"])
            else:
                raise IntakeGap("unexpected_primary_mission_choice")
            need(
                isinstance(targets, list)
                and all(
                    isinstance(target, str) and target and target == target.strip()
                    for target in targets
                )
                and len(set(targets)) == len(targets),
                "invalid_primary_mission_choice_targets",
            )
            need(key not in self.pending, "repeated_primary_mission_choice")
            self.pending[key] = tuple(sorted(targets))

    def select(self, context: PlayerDecisionContext) -> PolicyAction:
        request = context.request
        choice = PrimaryMissionChoiceData.from_payload(request["payload"])
        actor = context.route.actor_id
        need(choice.player_id == actor, "foreign_primary_mission_choice")
        if choice.choice_kind == LOCATE_AND_DENY_CHOICE_KIND:
            valid_window = context.route.stage == "setup" and choice.battle_round is None
        elif choice.choice_kind == PUNISHMENT_CHOICE_KIND:
            valid_window = (
                choice.phase == context.route.battle_phase == BattlePhase.COMMAND.value
                and choice.battle_round == context.observation["battle_round"]
            )
        else:
            raise IntakeGap("unexpected_primary_mission_choice")
        need(valid_window, "invalid_primary_mission_choice_window")
        key = (actor, choice.choice_kind, choice.battle_round, choice.phase)
        need(key not in self.used, "repeated_primary_mission_choice")
        need(key in self.pending, "unconfigured_primary_mission_choice")
        targets = self.pending[key]
        need(set(targets) <= set(choice.legal_target_ids), "unavailable_primary_mission_choice")
        expected = choice.with_selected_targets(targets)
        matches = [
            option["option_id"]
            for option in request["options"]
            if PrimaryMissionChoiceData.from_payload(option["payload"]) == expected
        ]
        need(bool(matches), "unavailable_primary_mission_choice")
        need(len(matches) == 1, "ambiguous_primary_mission_choice")
        action = bench.finite(context, matches[0])
        del self.pending[key]
        self.used.add(key)
        return action

    def require_complete(self) -> None:
        need(not self.pending, "unused_primary_mission_choice")


def open_origin(
    game: GameConfig, recipe: bench.Row, prefix_moves: list[bench.Row]
) -> LocalGameSession:
    primary_choices = _PrimaryMissionChoices(recipe.get("primary_mission_choices", []))
    session = LocalGameSession()
    status = session.start(game)
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = session.advance_until_decision_or_terminal()
    need(status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, "startup_failed")
    expected_moves = recipe.get("round_one_moves", {})
    completed_moves = set()
    for step in range(recipe["prefix_decision_cap"] + 1):
        context = bench.actor(session)
        occurrence = setup_driver.coordinates(context)
        kind = context.route.decision_type
        if occurrence == ORIGIN:
            need(
                context.route.actor_id == bench.A
                and context.request["payload"]["unit_instance_id"] == recipe["roles"]["screen"],
                "wrong_origin_unit",
            )
            need(completed_moves == set(expected_moves), "missing_round_one_move")
            primary_choices.require_complete()
            return session
        need(occurrence[0] <= 2, "missed_a2_origin")
        if step == recipe["prefix_decision_cap"]:
            break
        if kind == "submit_deployment_placement":
            action = bench.placement(context, recipe)
        elif kind == "select_secondary_missions":
            action = bench.finite(context, recipe["fixed_secondary_option"])
        elif kind == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
            action = primary_choices.select(context)
        elif occurrence[0] == 1 and kind == bench.MOVE_ACTION:
            unit = context.request["payload"]["unit_instance_id"]
            if unit in expected_moves:
                need(unit not in completed_moves, "duplicate_round_one_move")
                bench.commit(session, context, bench.finite(context, bench.NORMAL))
                continue
            action = setup_driver.ordinary(context)
        elif kind == "submit_movement_proposal":
            unit = context.request["payload"]["proposal_request"]["unit_instance_id"]
            need(
                occurrence[0] == 1
                and context.route.proposal_kind == bench.NORMAL
                and unit in expected_moves
                and unit not in completed_moves,
                "unexpected_prefix_move",
            )
            raw = bench.raw_moves(context)
            selected, selection = select_path(session, context, raw, recipe, expected_moves[unit])
            prefix_moves.append({"unit": unit, **selection})
            need(selected is not None, "round_one_path_unavailable")
            completed_moves.add(unit)
            action = raw[selected][0]
        else:
            # All other Movement offers Hold. Shooting, Charge and optional reactions are skipped.
            action = setup_driver.ordinary(context)
        bench.commit(session, context, action)
    raise IntakeGap("prefix_decision_cap")


def origin_type(
    session: LocalGameSession, context: PlayerDecisionContext, target: str
) -> bench.Row:
    view = context.observation
    objectives = [o for o in _linked_objectives(view) if o.objective_id == target]
    board = view["battlefield_view"]
    need(len(objectives) == 1 and board is not None, "target_not_visible")
    assert board is not None
    oc = dict.fromkeys((bench.A, bench.B), 0)
    for model_id, entity in board["authoritative"]["models_by_id"].items():
        if entity["state"] != "placed":
            continue
        display = view["model_display_by_id"][model_id]
        model = _model_geometry(entity, display)
        need(model is not None, "model_geometry_not_visible")
        assert model is not None
        if measure_model_to_objective(model=model, objective=objectives[0]).within_control_range:
            shown = display["current_characteristics"]["OC"]
            value = shown["final"]
            need(not shown["redaction"]["hidden"] and type(value) is int, "oc_not_visible")
            oc[entity["owner_player_id"]] += value
    events = session.events_since(EventStreamCursor(), viewer_player_id=bench.A)["events"]
    published = [
        event["payload"]["primary_objective_turn_start_state"]
        for event in events
        if event["event_type"] == PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT
        and event["payload"]["battle_round"] == 2
        and event["payload"]["active_player_id"] == bench.A
    ]
    need(len(published) == 1, "origin_control_not_visible")
    results = published[0]["source_objective_control_record"]["results"]
    controls = [row for row in results if row["objective_id"] == target]
    need(
        len(controls) == 1 and controls[0]["status"] != "unsupported", "origin_control_unavailable"
    )
    controller = controls[0]["controlled_by_player_id"]
    return {
        "type": classify_origin(oc, controller),
        "controller": controller,
        "visible_contact_oc": oc,
    }


def classify_origin(oc: dict[str, int], controller: str | None) -> str:
    participants = [player for player, amount in oc.items() if amount > 0]
    if len(participants) == 2:
        return "contested"
    if participants == [controller]:
        return "held"
    if not participants and controller is None:
        return "empty"
    raise IntakeGap("origin_type_ineligible")


def screen_order(raw: bench.Raw, direction: list[int], threshold: float) -> list[str]:
    ux, uy = direction
    return sorted(
        key
        for key, (_, proposal) in raw.items()
        for dx, dy in (bench.delta(proposal),)
        if (dx * ux + dy * uy) / (hypot(dx, dy) * hypot(ux, uy)) >= threshold
    )


def select_path(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    raw: bench.Raw,
    recipe: bench.Row,
    direction: list[int],
) -> tuple[str | None, bench.Row]:
    order = screen_order(raw, direction, recipe["route_cosine_min"])
    probes = []
    selected = None
    for key in order[: recipe["native_probe_cap"]]:
        violation = bench.trial(session, context, raw, key)
        probes.append({"id": key, "violation": violation})
        if violation is None:
            selected = key
            break
    return selected, {
        "eligible_candidates": order,
        "cap_losses": max(0, len(order) - recipe["native_probe_cap"]),
        "probes": probes,
    }


def immediate_menu(
    session: LocalGameSession, context: PlayerDecisionContext, recipe: bench.Row
) -> bench.Row:
    menu = FiniteCandidateSet.from_context(context)
    actions = (bench.HOLD, bench.NORMAL)
    need(set(actions) <= set(menu.candidate_ids), "hold_or_normal_missing")
    screen_unit = recipe["roles"]["screen"]
    need(
        all(
            row.option["payload"]["unit_instance_id"] == screen_unit
            for row in menu.candidates
            if row.option["option_id"] in actions
        ),
        "finite_unit_binding",
    )
    before = payload_digest(session.lifecycle.to_payload())
    hold, screen = session.fork(), session.fork()
    for branch, option in ((hold, bench.HOLD), (screen, bench.NORMAL)):
        need(
            payload_digest(branch.lifecycle.to_payload()) == before
            and bench.actor(branch) == context,
            "fork_origin_mismatch",
        )
        records = branch.decision_record_count()
        status = bench.submit(branch, context, menu.select(context, option))
        need(
            status.status_kind
            in {LifecycleStatusKind.ADVANCED, LifecycleStatusKind.WAITING_FOR_DECISION}
            and branch.decision_record_count() == records + 1,
            "hold_rejected" if option == bench.HOLD else "normal_rejected",
        )
    child = bench.actor(screen)
    need(
        setup_driver.coordinates(child) == (2, bench.A, "movement", "submit_movement_proposal")
        and child.route.actor_id == bench.A
        and child.route.proposal_kind == bench.NORMAL
        and child.request["payload"]["proposal_request"]["unit_instance_id"] == screen_unit,
        "screen_child_binding",
    )
    raw = bench.raw_moves(child)
    accepted, selection = select_path(screen, child, raw, recipe, recipe["routes"]["screen"])
    if accepted is None:
        raise IntakeGap("screen_unavailable_under_cap", **selection)
    # Submit the selected native path on the branch through the same adapter, without
    # advancing to another decision. Neither branch is continued past S.
    records = screen.decision_record_count()
    status = bench.submit(screen, child, raw[accepted][0])
    need(
        status.status_kind
        in {LifecycleStatusKind.ADVANCED, LifecycleStatusKind.WAITING_FOR_DECISION}
        and screen.decision_record_count() == records + 1
        and payload_digest(session.lifecycle.to_payload()) == before,
        "screen_commit_or_parent_isolation",
    )
    return {
        "request_id": menu.request_id,
        "actor_id": menu.actor_id,
        "observation_sha256": context.observation_hash,
        "issued_options": list(menu.candidate_ids),
        "excluded_options": [choice for choice in menu.candidate_ids if choice not in actions],
        "hold": "accepted",
        "normal_move_child_request_id": child.request["request_id"],
        "raw_candidates": len(raw),
        "raw_candidate_ids_sha256": payload_digest(sorted(raw)),
        **selection,
        "selected_screen": accepted,
    }


def preflight(
    recipe: bench.Row,
    setup: MissionSetup,
    seed: str,
    evidence: bench.Row | None = None,
    *,
    on_origin: Callable[[bench.Row], None] | None = None,
) -> bench.Row:
    proof = {} if evidence is None else evidence
    prefix_moves: list[bench.Row] = []
    if evidence is not None:
        proof["round_one_probes"] = prefix_moves
    session = open_origin(config(recipe, setup, seed), recipe, prefix_moves)
    proof["a2_origin_reached"] = True
    context = bench.actor(session)
    checkpoint = bench.strict_checkpoint(session)
    rng = checkpoint["rng_state"]
    need(rng["seed"] == seed, "startup_seed_drift")
    proof.update(
        origin_sha256=checkpoint["content_hash"],
        event_prefix_sha256=checkpoint["event_log_hash"],
        decision_prefix_sha256=checkpoint["decision_records_hash"],
        decision_count=session.decision_record_count(),
        draw_count=rng["draw_count"],
        strict_restore_and_replay=True,
    )
    proof["origin"] = origin_type(session, context, recipe["target"])
    if on_origin is not None:
        on_origin({**proof, "status": "origin_verified"})
    proof["menu"] = immediate_menu(session, context, recipe)
    return proof


def run() -> bool:
    recipe = load_recipe()
    page = recipe["source_page"]
    try:
        setup, manifest, reserve, excluded = source_inventory(recipe)
    except IntakeGap as gap:
        print(json.dumps({"page": page, "status": "ineligible", "reason": gap.code}), flush=True)
        return False
    rows = []
    proofs = []
    for number in (1, 2):
        seed = sha256(f"{recipe['seed_namespace']}/{number}".encode()).hexdigest()
        try:
            proof = preflight(recipe, setup, seed)
        except IntakeGap as gap:
            rows.append(
                {
                    "seed_index": number,
                    "status": "ineligible",
                    "reason": gap.code,
                    **gap.details,
                }
            )
        except ScreenMovementGap as gap:
            rows.append({"seed_index": number, "status": "ineligible", "reason": gap.reason.value})
        except NATIVE_PREFLIGHT_ERRORS:
            rows.append(
                {
                    "seed_index": number,
                    "status": "ineligible",
                    "reason": "native_preflight_failed",
                }
            )
        else:
            proofs.append(proof)
            rows.append(
                {"seed_index": number, "startup_seed_hex": seed, "status": "eligible", **proof}
            )
    eligible = len(proofs) == 2 and proofs[0]["origin"]["type"] == proofs[1]["origin"]["type"]
    receipt = {
        "page": page,
        "layout": recipe["layout"],
        "pairing": recipe["pairing"],
        "primary_missions": recipe["primary_missions"],
        "target": recipe["target"],
        "recipe_sha256": payload_digest(recipe),
        "engine_build_id": verified_engine_build_identity().build_id,
        "candidate_generator_sha256": sha256(
            Path(screen_movement_candidates.__file__).read_bytes()
        ).hexdigest(),
        "development_pages": excluded,
        "diagram_count": 45,
        "status": "provisionally_eligible" if eligible else "ineligible",
        "reason": None
        if eligible
        else ("origin_type_mismatch" if len(proofs) == 2 else "seed_preflight_failed"),
        "continuation_disjointness": "sealed_check_pending",
        "attempts": rows,
    }
    if eligible:
        reserve["trajectory_sha256"] = sorted(
            {
                row[key]
                for row in proofs
                for key in ("origin_sha256", "event_prefix_sha256", "decision_prefix_sha256")
            }
        )
        manifest["families"].append(reserve)
        try:
            groups = evaluation.validate_split(manifest)
            need([reserve["id"]] in groups, "reserve_component_not_disjoint")
        except bench.BenchmarkGap:
            eligible = False
            receipt.update(status="ineligible", reason="family_disjointness_failed")
        else:
            receipt.update({"components": groups, "split_manifest": manifest})
    print(json.dumps(receipt), flush=True)
    return eligible
