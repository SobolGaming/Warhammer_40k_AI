"""Opt-in regressions for the first prospective Movement intake."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import battle_state, phase11c_config

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_layout_batch as batch
from scripts import stage4_layout_intake as intake
from scripts import stage4_split_objective as control
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import (
    PROJECTION_SCHEMA_VERSION,
    GameViewPayload,
    public_decision_request_view,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_policies import primary_mission_choice_rule_for_id
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    CONSECRATE_CHOICE_KIND,
    LOCATE_AND_DENY_CHOICE_KIND,
    PUNISHMENT_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choices import (
    LOCATE_AND_DENY_CHOICE_RULE_ID,
    PUNISHMENT_CHOICE_RULE_ID,
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    apply_primary_mission_choice,
    locate_and_deny_setup_choice_request,
    primary_mission_choice_option_id,
    punishment_choice_request,
)


def _mission_choice_context(
    kind: str,
    *,
    actor_id: str = bench.A,
    player_id: str | None = None,
    request_id: str = "first-request",
    battle_round: int = 1,
) -> PlayerDecisionContext:
    setup = kind == LOCATE_AND_DENY_CHOICE_KIND
    targets = tuple(f"target-{index}" for index in range(6 if setup else 2))
    selections = (targets[:5], targets[1:]) if setup else ((targets[0],), (targets[1],))
    choice = PrimaryMissionChoiceData(
        game_id="synthetic-mission-choice",
        player_id=actor_id if player_id is None else player_id,
        choice_kind=kind,
        primary_mission_id="synthetic-primary",
        source_descriptor_id="synthetic-descriptor",
        source_rule_id="synthetic-rule",
        battle_round=None if setup else battle_round,
        phase=None if setup else "command",
        subject_id=None,
        source_action_id=None,
        legal_target_ids=targets,
        selected_target_ids=(),
        evidence_ids=(),
        used_fallback_candidates=False,
    )
    request = DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
        actor_id=actor_id,
        payload=validate_json_value(choice.to_payload()),
        options=tuple(
            DecisionOption(
                primary_mission_choice_option_id(choice=choice, selected_ids=selection),
                "Select " + ", ".join(selection),
                validate_json_value(choice.with_selected_targets(selection).to_payload()),
            )
            for selection in selections
        ),
    )
    view = {
        "projection_schema": PROJECTION_SCHEMA_VERSION,
        "viewer_role": "player",
        "viewer_player_id": actor_id,
        "player_ids": [bench.A, bench.B],
        "stage": "setup" if setup else "battle",
        "battle_round": 0 if setup else battle_round,
        "current_setup_step": "determine_first_turn" if setup else None,
        "current_battle_phase": choice.phase,
        "pending_decision": public_decision_request_view(
            request, viewer=ViewerContext.for_player(actor_id)
        ),
    }
    return PlayerDecisionContext.from_view(cast(GameViewPayload, view), choice_seed=0)


def _mission_declaration(
    kind: str,
    targets: list[str],
    *,
    actor_id: str = bench.A,
    battle_round: int = 1,
) -> bench.Row:
    return {
        "actor_id": actor_id,
        "choice_kind": kind,
        "window": {"phase": "start_battle"}
        if kind == LOCATE_AND_DENY_CHOICE_KIND
        else {"phase": "command", "battle_round": battle_round},
        "selected_target_ids": targets,
    }


@pytest.mark.parametrize(
    ("kind", "targets"),
    [
        (LOCATE_AND_DENY_CHOICE_KIND, ["target-5", "target-4", "target-3", "target-2", "target-1"]),
        (PUNISHMENT_CHOICE_KIND, ["target-1"]),
    ],
)
def test_primary_mission_choice_uses_the_current_issued_ids(kind: str, targets: list[str]) -> None:
    declarations = [_mission_declaration(kind, targets)]
    for request_id in ("first-request", "later-request"):
        context = _mission_choice_context(kind, request_id=request_id)
        choices = intake._PrimaryMissionChoices(declarations)
        action = choices.select(context)
        (issued,) = [
            option
            for option in context.request["options"]
            if PrimaryMissionChoiceData.from_payload(option["payload"]).selected_target_ids
            == tuple(sorted(targets))
        ]
        assert action == context.select_option(issued["option_id"])
        choices.require_complete()


def test_primary_mission_choice_consumes_each_required_window_once() -> None:
    kind = PUNISHMENT_CHOICE_KIND
    choices = intake._PrimaryMissionChoices(
        [
            _mission_declaration(kind, ["target-0"], battle_round=1),
            _mission_declaration(kind, ["target-1"], battle_round=2),
        ]
    )
    choices.select(_mission_choice_context(kind))
    with pytest.raises(intake.IntakeGap, match="unused_primary_mission_choice"):
        choices.require_complete()
    with pytest.raises(intake.IntakeGap, match="repeated_primary_mission_choice"):
        choices.select(_mission_choice_context(kind, request_id="repeated-window-request"))
    choices.select(_mission_choice_context(kind, battle_round=2))
    choices.require_complete()


@pytest.mark.parametrize(
    ("declarations", "reason"),
    [
        ([], "unconfigured_primary_mission_choice"),
        (
            [_mission_declaration(PUNISHMENT_CHOICE_KIND, ["target-0"], actor_id=bench.B)],
            "unconfigured_primary_mission_choice",
        ),
        (
            [_mission_declaration(PUNISHMENT_CHOICE_KIND, ["target-0"], battle_round=2)],
            "unconfigured_primary_mission_choice",
        ),
        (
            [_mission_declaration(PUNISHMENT_CHOICE_KIND, ["unknown-target"])],
            "unavailable_primary_mission_choice",
        ),
        (
            [_mission_declaration(PUNISHMENT_CHOICE_KIND, ["target-0", "target-1"])],
            "unavailable_primary_mission_choice",
        ),
    ],
)
def test_primary_mission_choice_rejects_missing_or_inexact_bindings(
    declarations: list[bench.Row], reason: str
) -> None:
    choices = intake._PrimaryMissionChoices(declarations)
    with pytest.raises(intake.IntakeGap, match=reason):
        choices.select(_mission_choice_context(PUNISHMENT_CHOICE_KIND))


def test_primary_mission_choice_rejects_duplicate_declarations() -> None:
    kind = PUNISHMENT_CHOICE_KIND
    with pytest.raises(intake.IntakeGap, match="repeated_primary_mission_choice"):
        intake._PrimaryMissionChoices(
            [_mission_declaration(kind, ["target-0"]), _mission_declaration(kind, ["target-1"])]
        )


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            {"window": {"phase": "movement", "battle_round": 1}},
            "invalid_primary_mission_choice_window",
        ),
        (
            {"window": {"phase": "command", "battle_round": True}},
            "invalid_primary_mission_choice_window",
        ),
        (
            {"selected_target_ids": ["target-0", "target-0"]},
            "invalid_primary_mission_choice_targets",
        ),
    ],
)
def test_primary_mission_choice_rejects_invalid_declarations(
    change: bench.Row, reason: str
) -> None:
    declaration = _mission_declaration(PUNISHMENT_CHOICE_KIND, ["target-0"])
    with pytest.raises(intake.IntakeGap, match=reason):
        intake._PrimaryMissionChoices([{**declaration, **change}])


@pytest.mark.parametrize(
    ("game_id", "reason"),
    [
        ("synthetic-mission-choice", "ambiguous_primary_mission_choice"),
        ("foreign-source-game", "unavailable_primary_mission_choice"),
    ],
)
def test_primary_mission_choice_rejects_ambiguous_or_foreign_options(
    game_id: str, reason: str
) -> None:
    kind = PUNISHMENT_CHOICE_KIND
    view = _mission_choice_context(kind).observation
    request = view["pending_decision"]
    assert request is not None
    (original,) = [
        option
        for option in request["options"]
        if PrimaryMissionChoiceData.from_payload(option["payload"]).selected_target_ids
        == ("target-0",)
    ]
    selected = PrimaryMissionChoiceData.from_payload(original["payload"])
    altered = {**selected.to_payload(), "game_id": game_id}
    other = DecisionOption("other-option", original["label"], validate_json_value(altered))
    if altered != selected.to_payload():
        request["options"].remove(original)
    request["options"].append(other.to_payload())
    choices = intake._PrimaryMissionChoices([_mission_declaration(kind, ["target-0"])])
    context = PlayerDecisionContext.from_view(view, choice_seed=0)
    with pytest.raises(intake.IntakeGap, match=reason):
        choices.select(context)


@pytest.mark.parametrize(
    ("kind", "player_id", "reason"),
    [
        (PUNISHMENT_CHOICE_KIND, bench.B, "foreign_primary_mission_choice"),
        (CONSECRATE_CHOICE_KIND, bench.A, "unexpected_primary_mission_choice"),
    ],
)
def test_primary_mission_choice_rejects_foreign_owner_or_unsupported_kind(
    kind: str, player_id: str, reason: str
) -> None:
    choices = intake._PrimaryMissionChoices([])
    with pytest.raises(intake.IntakeGap, match=reason):
        choices.select(_mission_choice_context(kind, player_id=player_id))


@pytest.mark.parametrize(
    ("kind", "rule_id", "targets"),
    [
        (
            LOCATE_AND_DENY_CHOICE_KIND,
            LOCATE_AND_DENY_CHOICE_RULE_ID,
            [
                f"{control.LAYOUT}-{target}"
                for target in (
                    "logical-terrain-contact-icon-02",
                    "terrain-area-06",
                    "terrain-area-07",
                    "terrain-area-10",
                    "terrain-area-13",
                )
            ],
        ),
        (PUNISHMENT_CHOICE_KIND, PUNISHMENT_CHOICE_RULE_ID, ["army-beta:intercessor-unit-3"]),
    ],
)
def test_primary_mission_choice_passes_native_validation_after_prior_allocation(
    kind: str, rule_id: str, targets: list[str]
) -> None:
    declarations = [_mission_declaration(kind, targets)]
    request_ids = []
    for allocate_prior in (False, True):
        decisions = DecisionController()
        setup_choice = kind == LOCATE_AND_DENY_CHOICE_KIND
        config = control.config() if setup_choice else phase11c_config()
        state = GameState.from_config(config) if setup_choice else battle_state(decisions=decisions)
        setup = state.mission_setup
        assert setup is not None
        # Exercise the native choice rules on fixed nonreserve geometry.
        mission = primary_mission_choice_rule_for_id(rule_id).primary_mission_id
        state.mission_setup = replace(
            setup,
            primary_mission_assignments=tuple(
                replace(assignment, primary_mission_id=mission)
                if assignment.player_id == bench.A
                else assignment
                for assignment in setup.primary_mission_assignments
            ),
        )
        if setup_choice:
            state.setup_step_index = len(state.setup_sequence) - 1
            issue = locate_and_deny_setup_choice_request
        else:
            state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
            issue = punishment_choice_request
        if allocate_prior:
            state.next_decision_request_id()

        request = issue(state=state, decisions=decisions)
        assert request is not None
        request_ids.append(request.request_id)
        decisions.request_decision(request)
        session = LocalGameSession(
            lifecycle=GameLifecycle(state=state, decision_controller=decisions, _config=config)
        )
        context = bench.actor(session)
        choices = intake._PrimaryMissionChoices(declarations)
        action = choices.select(context)
        assert action.request_id == context.request["request_id"]
        assert action.option_id is not None

        if setup_choice:
            # The synthetic assignment exercises the native handler independently of setup replay.
            result = DecisionResult.for_request(
                result_id="native-control", request=request, selected_option_id=action.option_id
            )
            decisions.submit_result(result)
            assert apply_primary_mission_choice(
                state=state, decisions=decisions, request=request, result=result
            )
        else:
            assert (
                bench.submit(session, context, action).status_kind is LifecycleStatusKind.ADVANCED
            )
        result = decisions.records[-1].result
        assert result.request_id == request.request_id
        assert PrimaryMissionChoiceData.from_payload(result.payload).selected_target_ids == tuple(
            sorted(targets)
        )
        choices.require_complete()
    assert request_ids[0] != request_ids[1]


def test_primary_mission_choices_are_optional_prospective_page_fields() -> None:
    base = {"roles": {"screen": "s", "follow": "f", "opponent": "o"}, "routes": {"screen": [1, 0]}}
    proposal = {
        "page": 100,
        "layout": "synthetic-layout",
        "pairing": ["synthetic-a", "synthetic-b"],
        "primary_missions": ["synthetic-primary-a", "synthetic-primary-b"],
        "target": "synthetic-target",
        "deployment": {"s": [], "f": [], "o": []},
        "routes": base["routes"],
        "round_one_moves": {},
        "proposed_origin": "empty",
    }
    key = "primary_mission_choices"
    declarations = [_mission_declaration(PUNISHMENT_CHOICE_KIND, ["target-0"])]
    assert key not in batch.recipe_for(proposal, base)
    assert batch.recipe_for({**proposal, key: declarations}, base)[key] == declarations
    with pytest.raises(intake.IntakeGap, match="candidate_recipe_fields"):
        batch.recipe_for({**proposal, "unknown": []}, base)
    with pytest.raises(intake.IntakeGap, match="page_9_recipe_drift"):
        batch.recipe_for({"page": 9, key: declarations}, base)


@pytest.mark.parametrize(
    ("contact", "controller", "category"),
    [
        ((0, 0), None, "empty"),
        ((2, 1), bench.A, "contested"),
        ((0, 1), bench.B, "held"),
    ],
)
def test_origin_categories_are_defined_by_visible_control(
    contact: tuple[int, int], controller: str | None, category: str
) -> None:
    assert (
        intake.classify_origin(dict(zip((bench.A, bench.B), contact, strict=True)), controller)
        == category
    )


def test_retained_control_without_contact_is_ineligible() -> None:
    with pytest.raises(intake.IntakeGap, match="origin_type_ineligible"):
        intake.classify_origin({bench.A: 0, bench.B: 0}, bench.A)


def test_first_recipe_uses_earliest_unused_diagram() -> None:
    recipe = intake.load_recipe()
    setup, manifest, reserve, used = intake.source_inventory(recipe)
    assert used == [13, 14, 38]
    assert reserve["source_diagram_pages"] == [9]
    assert reserve["trajectory_sha256"] == []
    assert setup.battlefield_layout_id == recipe["layout"]
    assert intake.evaluation.validate_split(manifest) == [
        ["guard"],
        ["layout-c", "shooting"],
        ["west"],
    ]
    with pytest.raises(intake.IntakeGap, match="candidate_page_order"):
        intake.source_inventory({**recipe, "source_page": 10})


@pytest.mark.parametrize(
    ("field", "binding", "component"),
    [
        (
            "trajectory_sha256",
            "fb22f83cbb3890e655fc764abc1cbccd22991f2cb7ad398ec7b6f487ab846398",
            "synthetic-reserve, west",
        ),
        (
            "geometry_sha256",
            "45793e48a681e6d0acd2361798d73f832037d136059a1352859d5ccd82475e32",
            "layout-c, shooting, synthetic-reserve",
        ),
    ],
)
def test_published_development_binding_rejects_reserve_collision(
    field: str, binding: str, component: str
) -> None:
    _, manifest, reserve, _ = intake.source_inventory(intake.load_recipe())
    synthetic = {
        **reserve,
        "id": "synthetic-reserve",
        "source_diagram_pages": [10],
        "scenario_lineage": ["synthetic-scenario"],
        "geometry_families": ["synthetic-geometry"],
        "geometry_sha256": [bench.payload_digest("synthetic board")],
        "trajectory_sha256": [bench.payload_digest("synthetic origin")],
    }
    manifest["families"].append(synthetic)
    assert ["synthetic-reserve"] in intake.evaluation.validate_split(manifest)

    synthetic[field].append(binding)
    with pytest.raises(bench.BenchmarkGap, match=f"crosses a connected component: {component}"):
        intake.evaluation.validate_split(manifest)


def test_frozen_batch_inventory_and_original_page_9() -> None:
    from scripts import stage4_layout_batch as batch

    plan = batch.load_plan()
    original = intake.load_recipe()
    layouts, development, used = intake.development_inventory()
    assert [row["page"] for row in plan["pages"]] == list(range(9, 54))
    assert [
        row["page"] for row in plan["pages"] if row.get("exclude") == "development_diagram"
    ] == used
    assert batch.recipe_for(plan["pages"][0], original) == original
    for row in plan["pages"]:
        if "exclude" in row:
            continue
        recipe = batch.recipe_for(row, original)
        _, candidate = intake.source_candidate(recipe, layouts[recipe["layout"]], development)
        assert candidate["source_diagram_pages"] == [row["page"]]
        assert recipe["native_probe_cap"] == 2
        assert recipe["worker_wall_seconds"] == 180
        assert recipe["seed_namespace"] == "stage4-movement-comparison-v1"


def test_batch_selection_skips_earliest_page_only_when_quotas_require_it() -> None:
    from scripts import stage4_layout_batch as batch

    rows = [
        {"page": page, "pairing": [pair], "component": component, "origin_type": kind}
        for page, pair, component, kind in (
            (9, "a", "A", "empty"),
            (10, "a", "B", "contested"),
            (12, "b", "C", "contested"),
            (15, "c", "D", "held"),
            (18, "d", "E", "held"),
            (21, "e", "F", "empty"),
            (24, "f", "G", "empty"),
            (27, "g", "G", "empty"),
            (30, "h", "H", "empty"),
            (33, "i", "I", "empty"),
        )
    ]
    selected = batch.choose(rows, 8, 2)
    assert selected is not None
    assert [row["page"] for row in selected] == [10, 12, 15, 18, 21, 24, 30, 33]
    assert batch.choose([row for row in rows if row["page"] != 10], 8, 2) is None


def test_batch_can_revisit_first_pairing_at_last_page() -> None:
    from scripts import stage4_layout_batch as batch

    rows = [
        {"page": page, "pairing": [pair], "component": page, "origin_type": kind}
        for page, (pair, kind) in enumerate(
            (
                ("P", "empty"),
                ("A", "empty"),
                ("B", "empty"),
                ("C", "contested"),
                ("D", "contested"),
                ("E", "held"),
                ("F", "empty"),
                ("G", "contested"),
                ("P", "held"),
            ),
            start=9,
        )
    ]
    assert batch.choose(rows, 8, 2) == rows[1:]


def test_batch_overlap_transitively_connects_failed_and_unattempted_candidates() -> None:
    from scripts import stage4_layout_batch as batch

    _, development, first, _ = intake.source_inventory(intake.load_recipe())
    first["trajectory_sha256"] = [bench.payload_digest("first")]
    bridge = {
        **first,
        "id": "reserve-page-10",
        "source_diagram_pages": [10],
        "scenario_lineage": ["bridge"],
        "geometry_families": ["bridge"],
        "geometry_sha256": [development["families"][0]["geometry_sha256"][0]],
    }
    last = {
        **bridge,
        "id": "reserve-page-11",
        "source_diagram_pages": [11],
        "geometry_sha256": [bench.payload_digest("other board")],
        "trajectory_sha256": [],
    }
    assert ["reserve-page-10", "reserve-page-11", "reserve-page-9", "west"] in batch.group_families(
        development, [first, bridge, last]
    )


def test_batch_preserves_origin_types_even_for_failed_native_menus() -> None:
    from scripts import stage4_layout_batch as batch

    receipt: bench.Row = {}
    attempts = [
        {"origin": {"type": "held"}, "status": "eligible"},
        {
            "origin": {"type": "held"},
            "status": "ineligible",
            "reason": "screen_unavailable_under_cap",
        },
    ]
    batch.candidate_disposition(receipt, attempts, None)
    assert receipt == {
        "origin_type": "held",
        "status": "ineligible",
        "reason": "seed_preflight_failed",
    }
    receipt = {}
    attempts[1] = {"origin": {"type": "contested"}, "status": "eligible"}
    batch.candidate_disposition(receipt, attempts, None)
    assert receipt == {"status": "ineligible", "reason": "origin_type_mismatch"}


def test_page_9_screen_probe_uses_native_child_fork() -> None:
    from hashlib import sha256

    recipe = intake.load_recipe()
    setup, _, _, _ = intake.source_inventory(recipe)
    seed = sha256(f"{recipe['seed_namespace']}/1".encode()).hexdigest()
    proof = intake.preflight(recipe, setup, seed)
    assert proof["origin"]["type"] == "empty"
    assert proof["strict_restore_and_replay"]
    assert proof["menu"]["hold"] == "accepted"
    assert proof["menu"]["probes"] == [{"id": proof["menu"]["selected_screen"], "violation": None}]


def test_receipt_verification_rejects_an_omitted_no_origin_bridge() -> None:
    from scripts import stage4_layout_batch as batch

    _, development, candidate, _ = intake.source_inventory(intake.load_recipe())
    candidate["trajectory_sha256"] = [bench.payload_digest("synthetic admitted origin")]
    bridge = {
        **candidate,
        "id": "reserve-page-10",
        "source_diagram_pages": [10],
        "geometry_sha256": [development["families"][0]["geometry_sha256"][0]],
        "trajectory_sha256": [],
    }
    pinned = {family["id"]: family for family in (candidate, bridge)}
    pages = [
        {
            "page": 9,
            "family_id": candidate["id"],
            "pairing": ["take-and-hold", "take-and-hold"],
            "origin_type": "empty",
            "status": "provisionally_eligible",
        },
        {"page": 10, "family_id": bridge["id"], "status": "ineligible"},
    ]
    reduced = {**development, "families": [*development["families"], candidate]}
    reduced_components = intake.evaluation.validate_split(reduced)
    assert [candidate["id"]] in reduced_components
    with pytest.raises(intake.IntakeGap, match="full_provenance_graph_mismatch"):
        batch.analyze(development, pinned, pages, expected_components=reduced_components)
    assert pages[0]["status"] == "provisionally_eligible"

    analysis = batch.analyze(development, pinned, pages)
    assert [bridge["id"], candidate["id"], "west"] in analysis["components"]
    assert pages[0]["reason"] == "development_component_overlap"
    assert analysis["qualified_counts"] == dict.fromkeys(batch.TYPES, 0)


@pytest.mark.parametrize("alias", ["original", "symlink", "hardlink"])
def test_verification_rejects_scored_receipts_before_reading(
    alias: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from os import link

    from scripts import stage4_layout_batch as batch

    scored = batch.HISTORICAL_SCORED_RECEIPTS[0]
    path = scored
    if alias == "symlink":
        path = tmp_path / "preflight.json"
        try:
            path.symlink_to(scored)
        except OSError:
            pytest.skip("Creating a symbolic link is unavailable on this platform.")
    if alias == "hardlink":
        path = tmp_path / "preflight.json"
        try:
            link(scored, path)
        except OSError:
            pytest.skip("Creating a hard link is unavailable on this volume.")

    def forbid_read(_path: Path) -> bytes:
        raise AssertionError("Verifier read a historical scored receipt")

    monkeypatch.setattr(Path, "read_bytes", forbid_read)
    with pytest.raises(intake.IntakeGap, match="historical_scored_receipt_forbidden"):
        batch.verify_file(path)


def test_outcome_blind_cli_rejects_historical_receipt_without_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from scripts import stage4_layout_batch as batch

    def forbid_read(_path: Path, **_kwargs: object) -> str:
        raise AssertionError("Verifier entered a scored receipt reader")

    monkeypatch.setattr(Path, "read_text", forbid_read)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4_benchmark_entry",
            "--layout-intake-verify",
            str(batch.HISTORICAL_SCORED_RECEIPTS[2]),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        bench.main()
    assert exc.value.code == 2
    assert "historical_scored_receipt_forbidden" in capsys.readouterr().err


def test_batch_round_trip_preserves_wall_cap_after_development_overlap(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    from hashlib import sha256

    from scripts import stage4_layout_batch as batch

    now = 0.0
    recipe = intake.load_recipe()

    def fake_preflight(page: int, cap: float) -> tuple[list[bench.Row], str | None]:
        nonlocal now
        assert page < 50
        now += min(cap, 84)
        attempts = [
            {
                "seed_index": index,
                "startup_seed_hex": sha256(
                    f"{recipe['seed_namespace']}/{index}".encode()
                ).hexdigest(),
                "status": "ineligible",
            }
            for index in (1, 2)
        ]
        if page not in (9, 15):
            return attempts, None
        for attempt in attempts:
            attempt.update(
                a2_origin_reached=True,
                strict_restore_and_replay=True,
                origin={
                    "type": "empty",
                    "controller": None,
                    "visible_contact_oc": {bench.A: 0, bench.B: 0},
                },
                event_prefix_sha256=bench.payload_digest(f"event {page}"),
                decision_prefix_sha256=bench.payload_digest(f"decision {page}"),
                origin_sha256=bench.payload_digest(f"origin {page}"),
                status="origin_verified",
            )
        if page == 15:
            attempts[0]["origin_sha256"] = intake.DEVELOPMENT_ORIGINS["west"][0]
            return attempts[:1], "preflight_wall_cap"
        for attempt in attempts:
            attempt.update(
                status="eligible",
                menu={
                    "actor_id": bench.A,
                    "issued_options": [bench.HOLD, bench.NORMAL],
                    "hold": "accepted",
                    "eligible_candidates": ["synthetic-screen"],
                    "selected_screen": "synthetic-screen",
                    "probes": [{"id": "synthetic-screen", "violation": None}],
                },
            )
        return attempts, None

    monkeypatch.setattr(batch, "monotonic", lambda: now)
    monkeypatch.setattr(batch, "preflight_page", fake_preflight)
    batch.run()
    receipt = json.loads(capsys.readouterr().out)
    by_page = {page["page"]: page for page in receipt["pages"]}
    assert by_page[15]["reason"] == by_page[50]["reason"] == "development_component_overlap"
    assert by_page[15]["preflight_disposition"] == "preflight_wall_cap"
    assert by_page[50]["preflight_disposition"] == "batch_wall_cap"
    assert "attempts" not in by_page[50]
    assert ["reserve-page-15", "reserve-page-50", "west"] in receipt["components"]

    verification = batch.verify_receipt(receipt)
    assert verification["provenance_vertices"] == 37
    assert verification["qualified_counts"] == {"empty": 1, "contested": 0, "held": 0}
    assert verification["proposed_pages"] == []

    # The earlier producer did not write the execution disposition.
    for page in receipt["pages"]:
        page.pop("preflight_disposition", None)
    assert batch.verify_receipt(receipt) == verification
