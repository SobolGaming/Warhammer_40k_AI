"""Fast opt-in checks for the sealed Stage 4 policy-target link."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest

from scripts import stage4_benchmark_entry as bench
from scripts import stage4_policy_target as link
from scripts.stage4_split_objective import sealed_receipt
from scripts.stage4_tactical_features import tactical_inputs
from warhammer40k_core.adapters.projection import PROJECTION_SCHEMA_VERSION, GameViewPayload
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.semantic_features import SemanticObservation
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE


@pytest.fixture
def reproduction() -> tuple[bench.Row, bench.Row]:
    reference = sealed_receipt()
    observed = deepcopy({key: value for key, value in reference.items() if key != "setup_evidence"})
    return reference, observed


def test_sealed_reproduction_is_admitted(reproduction: tuple[bench.Row, bench.Row]) -> None:
    link.verify_report(*reproduction)


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("partition",), "reserve", "all four observed development arms"),
        (("arms", "screen-omit"), None, "all four observed development arms"),
        (("protocol", "horizon", 0), 4, "Mixed or stale Stage 4 horizon"),
        (("protocol", "layout_source", "artifact_hash"), "a" * 64, "source, menu or replay"),
        (("origin", "request_id"), "stale-request", "source, menu or replay"),
        (("arms", "hold-omit", "event_log"), "b" * 64, "source, menu or replay"),
        (("arms", "screen-follow", "strict_replay"), False, "source, menu or replay"),
        (
            ("arms", "screen-follow", "menus", 0, "actor_view_hash"),
            "c" * 64,
            "source, menu or replay",
        ),
    ],
)
def test_reproduction_drift_is_refused(
    reproduction: tuple[bench.Row, bench.Row],
    path: tuple[str | int, ...],
    value: object,
    reason: str,
) -> None:
    reference, observed = reproduction
    target: Any = observed
    for field in path[:-1]:
        target = target[field]
    if value is None:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    with pytest.raises(bench.BenchmarkGap, match=reason):
        link.verify_report(reference, observed)


def test_receipt_cannot_be_replaced_along_with_replay(
    reproduction: tuple[bench.Row, bench.Row],
) -> None:
    reference, observed = reproduction
    reference["origin"]["checkpoint"] = observed["origin"]["checkpoint"] = "f" * 64
    with pytest.raises(bench.BenchmarkGap, match="differs from the seal"):
        link.verify_report(reference, observed)


def test_evaluation_groups_transitively_keep_families_together() -> None:
    inventory = {
        "a": frozenset({("source", "source-one")}),
        "b": frozenset({("geometry", "shape-one"), ("trajectory", "start-one")}),
        "c": frozenset({("trajectory", "start-one")}),
        "d": frozenset({("source", "source-one"), ("geometry", "shape-one")}),
        "e": frozenset({("source", "shape-one")}),
    }
    assert link.evaluation_groups(inventory) == [["a", "b", "c", "d"], ["e"]]
    assert link.evaluation_groups(dict(reversed(tuple(inventory.items())))) == [
        ["a", "b", "c", "d"],
        ["e"],
    ]


def test_prospective_coverage_excludes_unprobed_candidates(
    reproduction: tuple[bench.Row, bench.Row],
) -> None:
    _, observed = reproduction
    coverage = link._candidate_coverage(observed["arms"]["screen-follow"]["menus"][-1])
    assert coverage["raw_count"] == 32
    assert coverage["geometry_excluded_count"] == 28
    assert coverage["committed_proposal_id"] in coverage["prospective_native_accepts"]
    assert len(coverage["prospective_native_accepts"]) == 1
    assert len(coverage["prospective_native_rejects"]) == 1
    assert len(coverage["cap_unprobed_ids"]) == 2
    assert set(coverage["cap_unprobed_ids"]).isdisjoint(coverage["prospective_native_accepts"])


def test_native_acceptance_cannot_move_between_choice_bindings(
    reproduction: tuple[bench.Row, bench.Row],
) -> None:
    reference, observed = reproduction
    hold_arm = observed["arms"]["hold-follow"]
    hold, screen = (observed["arms"][arm]["menus"][-1] for arm in ("hold-follow", "screen-follow"))
    assert hold["raw_ids_hash"] == screen["raw_ids_hash"]
    assert all(
        hold[key] != screen[key]
        for key in ("action_request_id", "proposal_request_id", "actor_view_hash")
    )

    west = "normal-move:18b0cddad71a6aa5dd98958dd9ea06a14b608012b8c2e65eeca5f91bcdc6c15d"
    northwest = "normal-move:f1f55d8266e0e9e20bb2bfe535b365f427decc9e014915cf11039a0f4c5c01c0"
    hold_coverage, screen_coverage = map(link._candidate_coverage, (hold, screen))
    assert (
        hold_coverage["finite_selected_id"] == screen_coverage["finite_selected_id"] == bench.NORMAL
    )
    assert hold_coverage["committed_proposal_id"] == west
    assert west in hold_coverage["prospective_native_accepts"]
    assert screen_coverage["committed_proposal_id"] == northwest
    assert west in screen_coverage["prospective_native_rejects"]
    assert northwest in hold_coverage["prospective_native_accepts"]
    assert northwest != hold_coverage["committed_proposal_id"]
    assert "gain_vp" not in hold_coverage

    assert all(
        row["finite_request_id"] != row["proposal_request_id"]
        for row in (hold_coverage, screen_coverage)
    )

    finite_hold = link._candidate_coverage(hold_arm["menus"][0])
    assert finite_hold["finite_selected_id"] == bench.HOLD
    assert finite_hold["committed_proposal_id"] is None
    assert "proposal_request_id" not in finite_hold

    frozen_choice_bytes = payload_digest(hold_coverage)
    hold_arm["gain_vp"][bench.A] += 1
    assert payload_digest(link._candidate_coverage(hold)) == frozen_choice_bytes
    hold_arm["gain_vp"][bench.A] -= 1
    screen["native_probes"] = deepcopy(hold["native_probes"])
    with pytest.raises(bench.BenchmarkGap, match="source, menu or replay"):
        link.verify_report(reference, observed)


def test_sealed_development_pair_margins_and_interactions() -> None:
    west = json.loads(bench.WEST_RECEIPT.read_text(encoding="utf-8"))
    for receipt, expected in ((west, (3, 8)), (sealed_receipt(), (0, 5))):
        margins = {
            name: arm["gain_vp"][bench.A] - arm["gain_vp"][bench.B]
            for name, arm in receipt["arms"].items()
        }
        omit, follow = (margins[screen] - margins[hold] for hold, screen in link.PAIRS)
        assert (omit, follow) == expected
        assert follow - omit == receipt["interaction"] == 5


@pytest.fixture
def tactical_view() -> bench.Row:
    def model(unit: str, owner: str, x: float) -> bench.Row:
        return {
            "model_instance_id": unit,
            "rules_unit_instance_id": unit,
            "owner_player_id": owner,
            "state": "placed",
            "pose": {
                "position": {"x_inches": x, "y_inches": 0.0, "z_inches": 0.0},
                "facing_degrees": 0.0,
            },
            "geometry": {
                "measurement_shapes": [
                    {
                        "kind": "circle",
                        "center": {"x_inches": 0, "y_inches": 0},
                        "radius_inches": 0.5,
                    },
                ],
                "height_inches": 2.0,
            },
        }

    def area(x: float) -> bench.Row:
        return {
            "footprint": {
                "vertices": [
                    {"x_inches": x + dx, "y_inches": dy}
                    for dx, dy in ((0, -1), (2, -1), (2, 1), (0, 1))
                ]
            }
        }

    models = {
        "acting": model("acting", bench.A, 4.0),
        "ally": model("ally", bench.A, 1.0),
        "opponent": model("opponent", bench.B, 7.5),
    }
    return {
        "projection_schema": PROJECTION_SCHEMA_VERSION,
        "projection_state_hash": "a" * 64,
        "viewer_role": "player",
        "viewer_player_id": bench.A,
        "player_ids": [bench.A, bench.B],
        "stage": "battle",
        "current_setup_step": None,
        "current_battle_phase": "movement",
        "public_victory_point_ledgers": [],
        "pending_decision": {
            "request_id": "finite-request",
            "decision_type": bench.MOVE_ACTION,
            "actor_id": bench.A,
            "is_parameterized": False,
            "interaction": {"proposal_kind": None},
            "payload": {"unit_instance_id": "acting"},
            "options": [
                DecisionOption(option, option, {}).to_payload()
                for option in (bench.HOLD, bench.NORMAL)
            ],
        },
        "mission_setup": {
            "objective_terrain_areas": [
                {"objective_marker_id": "objective", "terrain_area_ids": ["first", "second"]},
            ]
        },
        "battlefield_view": {
            "authoritative": {
                "models_by_id": models,
                "terrain_areas_by_id": {"first": area(0), "second": area(6)},
            }
        },
        "model_display_by_id": {
            unit: {
                "visible_status": "visible",
                "keywords": [],
                "current_characteristics": {
                    "OC": {"final": oc, "redaction": {"hidden": False}},
                },
            }
            for unit, oc in (("acting", 1), ("ally", 2), ("opponent", 3))
        },
    }


def _context(view: bench.Row, seed: int = 0) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(cast(GameViewPayload, view), choice_seed=seed)


def _finite_input(context: PlayerDecisionContext) -> bench.Row:
    return link.FrozenChoice(
        SemanticObservation.from_context(context),
        FiniteCandidateSet.from_context(context),
        tactical_inputs(context),
        "authoritative-request",
    ).policy_input()


@pytest.mark.stubbed
def test_tactics_measure_both_linked_areas_and_separate_request_kinds(
    tactical_view: bench.Row,
) -> None:
    finite = _context(tactical_view)
    assert _finite_input(finite) == {
        "model_inputs": [2, -1, 1.5, 0.0, 0.0],
        "legal_action_ids": [bench.HOLD, bench.NORMAL],
    }
    child = tactical_view["pending_decision"]
    child.update(
        request_id="child-request",
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        is_parameterized=True,
        interaction={"proposal_kind": "normal_move"},
        payload={"proposal_request": {"unit_instance_id": "acting"}},
        options=[],
    )
    assert tactical_inputs(_context(tactical_view)) == (-1, 1.5, 0.0, 0.0)
    tactical_view["mission_setup"]["objective_terrain_areas"][0]["terrain_area_ids"] = ["first"]
    assert tactical_inputs(_context(tactical_view)) == (2, 1.5, 0.0, 5.0)


@pytest.mark.stubbed
def test_policy_input_bytes_ignore_targets_and_metadata(
    tactical_view: bench.Row, reproduction: tuple[bench.Row, bench.Row]
) -> None:
    context = _context(tactical_view)
    before = canonical_json(_finite_input(context)).encode()
    reference, observed = reproduction
    link.verify_report(reference, observed)
    observed["arms"]["screen-follow"]["gain_vp"][bench.A] += 1
    observed["protocol"]["seed"] = "changed-seed"
    with pytest.raises(bench.BenchmarkGap, match="source, menu or replay"):
        link.verify_report(reference, observed)

    tactical_view["projection_state_hash"] = "b" * 64
    tactical_view["game_id"] = "unrelated-game"
    tactical_view["public_victory_point_ledgers"] = [{"victory_points": 100}]
    tactical_view["pending_decision"]["request_id"] = "renamed-request"
    tactical_view["pending_decision"]["options"][0]["label"] = "unrelated-label"
    link_def = tactical_view["mission_setup"]["objective_terrain_areas"][0]
    link_def.update(objective_marker_id="renamed-objective", terrain_area_ids=["second", "renamed"])
    areas = tactical_view["battlefield_view"]["authoritative"]["terrain_areas_by_id"]
    areas["renamed"] = areas.pop("first")
    areas["renamed"]["source_id"] = "unrelated-source"
    mutated = _context(tactical_view, seed=123)
    assert mutated.observation_hash != context.observation_hash
    assert canonical_json(_finite_input(mutated)).encode() == before


@pytest.mark.stubbed
def test_missing_visible_measurements_are_explicit(tactical_view: bench.Row) -> None:
    tactical_view["model_display_by_id"]["opponent"]["current_characteristics"]["OC"]["final"] = (
        None
    )
    assert tactical_inputs(_context(tactical_view)) == (None, 1.5, 0.0, 0.0)
    tactical_view["battlefield_view"]["authoritative"]["models_by_id"]["ally"]["state"] = "reserves"
    assert tactical_inputs(_context(tactical_view)) == (None, 1.5, None, 0.0)
    tactical_view["mission_setup"]["objective_terrain_areas"] = []
    assert tactical_inputs(_context(tactical_view)) == (None, None, None, None)
