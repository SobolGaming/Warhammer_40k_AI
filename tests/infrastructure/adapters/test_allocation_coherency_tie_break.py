"""Native defender allocation and bounded one-removal tie-break."""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from typing import cast
from unittest.mock import patch

import pytest

from tests.phase15c_fight_order_helpers import fight_config, unit_placement_at
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from tests.support.private_randomness import fixture_private_rng_seed
from tests.support.screen_rod_allocation import (
    CAVALCADE_RULESET,
    SCREEN_ROD_MODEL_IDS,
    screen_rod_allocation_view,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import DecisionRequestViewPayload, GameViewPayload
from warhammer40k_core.ai import allocation_coherency
from warhammer40k_core.ai.allocation_coherency import (
    AllocationCoherencyPolicy,
    AllocationCoherencyTieBreakPolicy,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_coherency import UnitCoherencyContext, UnitCoherencyResult
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.milli_inch_oval_oval_distance import oval_oval_distance_ticks
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)

_ATTACKER = "player-a"
_DEFENDER = "player-b"
_SHOOTER = "army-alpha:attacker"
_TARGET = "army-beta:defender"
_LORD = "000001120"
_CRUSHERS = "000001115"
_ROD = f"{_LORD}:rod-of-sorcery:standard"
_DAMAGE = "select_damage_allocation_model"
_CLEANUP = "select_coherency_casualty"

type NativeFrontier = tuple[LocalGameSession, tuple[str, ...], GameViewPayload]


def _native_shooting_start(*, mixed_oval: bool = False) -> tuple[LocalGameSession, tuple[str, ...]]:
    """Construct the open-map Shooting start from admitted units and equipment."""
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    model_geometries = package.model_geometries
    if mixed_oval:
        # For this control only, fit the Bloodhunter with the sourced Seeker oval.
        seeker = next(
            row for row in model_geometries if row.model_profile_id == "000001145:seekers"
        )
        model_geometries = tuple(
            replace(
                seeker,
                model_profile_id=row.model_profile_id,
                model_geometry_id=row.model_geometry_id,
            )
            if row.model_profile_id == f"{_CRUSHERS}:bloodhunter"
            else row
            for row in model_geometries
        )
    config = fight_config(
        game_id="native-bloodcrusher-defender",
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("defender",),
        datasheet_id=_LORD,
        model_profile_id=f"{_LORD}:lord-of-change",
        model_count=1,
        alpha_faction_id="chaos-daemons",
        enemy_faction_id="chaos-daemons",
        alpha_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        enemy_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        catalog=package.army_catalog,
    )
    attack, defend = config.army_muster_requests
    (shooter,) = attack.unit_selections
    (target,) = defend.unit_selections
    shooter = replace(
        shooter,
        wargear_selections=(
            WargearSelection(
                option_id=f"{_LORD}:equipment-choice:option-1",
                model_profile_id=f"{_LORD}:lord-of-change",
                wargear_ids=(f"{_LORD}:rod-of-sorcery",),
                selection_count=1,
            ),
        ),
    )
    target = replace(
        target,
        datasheet_id=_CRUSHERS,
        model_profile_selections=(
            ModelProfileSelection(f"{_CRUSHERS}:bloodcrushers", 5),
            ModelProfileSelection(f"{_CRUSHERS}:bloodhunter", 1),
        ),
    )
    config = replace(
        config,
        private_rng_seed=fixture_private_rng_seed(6),
        army_muster_requests=(
            replace(attack, unit_selections=(shooter,)),
            replace(defend, unit_selections=(target,)),
        ),
        model_geometries=model_geometries,
        ruleset_descriptor=CAVALCADE_RULESET,
    )
    armies = tuple(
        muster_army(
            catalog=config.army_catalog, request=request, model_geometries=config.model_geometries
        )
        for request in config.army_muster_requests
    )
    mission = config.mission_setup
    assert mission is not None
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id=f"{config.game_id}-battlefield",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    ).battlefield_state
    bloodhunter_x = 39.30 if mixed_oval else 39.75
    poses = (
        (Pose.at(29, 11),),
        tuple(Pose.at(x, 20, 0, 90) for x in (29, 31.15, 33.30, 35.45, 37.60, bloodhunter_x)),
    )
    state = GameState.from_config(config)
    for army, unit_poses in zip(armies, poses, strict=True):
        (unit,) = army.units
        state.record_army_definition(army)
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(
                unit, army_id=army.army_id, player_id=army.player_id, poses=unit_poses
            )
        )
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = _ATTACKER
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring_it_down")
            )
        )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    return LocalGameSession(lifecycle), armies[1].units[0].own_model_ids()


def _request(view: GameViewPayload) -> DecisionRequestViewPayload:
    request = view["pending_decision"]
    assert request is not None
    return request


def _pending_view(session: LocalGameSession) -> GameViewPayload:
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id is not None
    return session.view(viewer_player_id=status.decision_request.actor_id)


def _select(session: LocalGameSession, view: GameViewPayload, option_id: str) -> None:
    request = _request(view)
    assert request["actor_id"] is not None
    status = session.submit_viewer_option(
        viewer=ViewerContext.for_player(request["actor_id"]),
        request_id=request["request_id"],
        result_id=f"native-bloodcrusher:{session.decision_record_count()}",
        option_id=option_id,
    )
    assert status.status_kind not in {LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED}


def _declare_rod(session: LocalGameSession, view: GameViewPayload) -> None:
    request = _request(view)
    assert request["decision_type"] == "submit_shooting_declaration"
    payload = cast(dict[str, JsonValue], request["payload"])
    offer = cast(dict[str, JsonValue], payload["proposal_request"])
    weapons = cast(list[dict[str, str]], offer["available_weapons"])
    (rod,) = (weapon for weapon in weapons if weapon["weapon_profile_id"] == _ROD)
    targets = cast(list[dict[str, JsonValue]], offer["target_candidates"])
    (target,) = (
        row
        for row in targets
        if row["weapon_profile_id"] == _ROD and row["target_unit_instance_id"] == _TARGET
    )
    assert target["is_legal"]
    assert len(cast(list[str], target["target_visible_model_ids"])) == 6
    proposal = ShootingDeclarationProposal(
        proposal_request_id=cast(str, offer["request_id"]),
        proposal_kind=cast(str, offer["proposal_kind"]),
        player_id=_ATTACKER,
        battle_round=cast(int, offer["battle_round"]),
        unit_instance_id=cast(str, offer["unit_instance_id"]),
        source_decision_request_id=cast(str, offer["source_decision_request_id"]),
        source_decision_result_id=cast(str, offer["source_decision_result_id"]),
        declarations=(
            WeaponDeclaration(
                rod["weapon_instance_id"],
                rod["model_instance_id"],
                rod["wargear_id"],
                _ROD,
                _TARGET,
                ShootingType.NORMAL,
            ),
        ),
        visibility_cache_key=cast(str, offer["visibility_cache_key"]),
    )
    status = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(_ATTACKER),
        request_id=request["request_id"],
        result_id=f"native-bloodcrusher:{session.decision_record_count()}",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind not in {LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED}


def _reach_native_frontier(*, mixed_oval: bool = False) -> NativeFrontier:
    session, ids = _native_shooting_start(mixed_oval=mixed_oval)
    view = _pending_view(session)
    request = _request(view)
    assert request["decision_type"] == "select_faction_rule_shooting_phase_start_option"
    grant_ids = tuple(
        option["option_id"]
        for option in request["options"]
        if option["option_id"].endswith("option_001_ignores_cover")
    )
    (ignores_cover,) = grant_ids
    _select(session, view, ignores_cover)
    _select(session, _pending_view(session), _SHOOTER)
    _select(session, _pending_view(session), "normal")
    _declare_rod(session, _pending_view(session))
    first = _pending_view(session)
    assert _request(first)["decision_type"] == _DAMAGE
    assert first["viewer_player_id"] == _DEFENDER
    _select(session, first, ids[3])
    view = _pending_view(session)
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.request_id == "decision-request-000008"
    assert pending.decision_type == _DAMAGE
    assert pending.actor_id == _DEFENDER
    return session, ids, view


@pytest.fixture(scope="module")
def native_frontier() -> Iterator[NativeFrontier]:
    session, ids, view = _reach_native_frontier()
    snapshot = session.lifecycle.to_payload()
    yield session, ids, view
    assert session.lifecycle.to_payload() == snapshot


def _context(view: GameViewPayload) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(view, choice_seed=0)


def _continued_branch(
    session: LocalGameSession,
    ids: tuple[str, ...],
    choice: str,
) -> tuple[list[str], list[int], list[str]]:
    # The second wound on the chosen model is applied without another request.
    _select(session, _pending_view(session), choice)
    final_save = _pending_view(session)
    assert _request(final_save)["decision_type"] == _DAMAGE
    assert choice not in [option["option_id"] for option in _request(final_save)["options"]]
    _select(session, final_save, ids[-1])
    charge = _pending_view(session)
    assert _request(charge)["decision_type"] == "select_charging_unit"
    _select(session, charge, "complete_charge_phase")

    cleanups: list[str] = []
    view = _pending_view(session)
    while _request(view)["decision_type"] == _CLEANUP:
        assert view["current_battle_phase"] == "fight"
        assert view["viewer_player_id"] == _DEFENDER
        assert len(cleanups) < 2
        offered = {option["option_id"] for option in _request(view)["options"]}
        # Both forks use the same fixed, ordinary owner choice.
        pick = next(model_id for model_id in reversed(ids) if model_id in offered)
        _select(session, view, pick)
        cleanups.append(pick)
        view = _pending_view(session)

    assert view["current_battle_phase"] == "command"
    assert view["viewer_player_id"] == _DEFENDER
    events = session.lifecycle.decision_controller.event_log.records
    steps = [
        cast(dict[str, JsonValue], event.payload)
        for event in events
        if event.event_type == "attack_sequence_step"
    ]
    save_faces: list[int] = []
    damage: list[tuple[JsonValue, JsonValue, JsonValue]] = []
    for step in steps:
        row = cast(dict[str, JsonValue], step["payload"])
        if step["step"] == "save":
            save_faces.append(cast(int, row["unmodified_roll"]))
        if step["step"] == "damage" and row["damage_application"] is not None:
            receipt = cast(dict[str, JsonValue], row["damage_application"])
            damage.append(
                (
                    receipt["model_instance_id"],
                    receipt["starting_wounds_remaining"],
                    receipt["final_wounds_remaining"],
                )
            )
    assert damage == [(ids[3], 4, 2), (ids[3], 2, 0), (choice, 4, 2), (choice, 2, 0)]
    battlefield = view["battlefield_view"]
    assert battlefield is not None
    placed_ids = battlefield["authoritative"]["models_by_id"]
    return (
        cleanups,
        save_faces,
        [model_id for model_id in ids if placed_ids[model_id]["state"] == "placed"],
    )


def test_native_defender_tie_break_saves_one_model_with_exact_fork_and_replay(
    native_frontier: NativeFrontier,
) -> None:
    session, ids, view = native_frontier
    context = _context(view)
    assert [option["option_id"] for option in context.request["options"]] == [
        ids[0],
        ids[1],
        ids[2],
        ids[4],
        ids[5],
    ]
    assert all(
        view["model_display_by_id"][option["option_id"]]["wounds_remaining"] == 4
        for option in context.request["options"]
    )
    first = AllocationCoherencyPolicy(CAVALCADE_RULESET)
    bounded = AllocationCoherencyTieBreakPolicy(CAVALCADE_RULESET)
    assert not any(first.score_options(context).values())
    assert first.choose(context) == context.select_option(ids[0])
    assert bounded.choose(context) == context.select_option(ids[4])

    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for player in (_ATTACKER, _DEFENDER):
        assert restored.view(viewer_player_id=player) == session.view(viewer_player_id=player)

    old, better = session.fork(), restored.fork()
    assert old.to_persistence_payload() == better.to_persistence_payload() == checkpoint
    assert _continued_branch(old, ids, ids[0]) == (
        [ids[5], ids[4]],
        [1, 1, 2, 2, 4],
        [ids[1], ids[2]],
    )
    assert _continued_branch(better, ids, ids[4]) == (
        [ids[5]],
        [1, 1, 2, 2, 4],
        [ids[0], ids[1], ids[2]],
    )
    for fork in (old, better):
        save = json.loads(json.dumps(fork.to_persistence_payload()))
        assert LocalGameSession.from_persistence_payload(save).to_persistence_payload() == save
        assert (
            ReplayRunner.from_payload(fork.replay_artifact(artifact_id="defender-native"))
            .run()
            .reproduced_exactly
        )


@pytest.fixture
def validation_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    original = UnitCoherencyContext.validate_models
    calls: list[tuple[str, ...]] = []

    def track(coherency: UnitCoherencyContext, models: tuple[Model, ...]) -> UnitCoherencyResult:
        calls.append(tuple(model.model_id for model in models))
        return original(coherency, models)

    monkeypatch.setattr(UnitCoherencyContext, "validate_models", track)
    return calls


def _issued(view: GameViewPayload, option_ids: tuple[str, ...]) -> GameViewPayload:
    result = deepcopy(view)
    request = _request(result)
    options = {option["option_id"]: option for option in request["options"]}
    request["options"] = [options[option_id] for option_id in option_ids]
    return result


def test_native_mixed_ovals_keep_v1_issued_order_without_repair_search(
    validation_calls: list[tuple[str, ...]],
) -> None:
    _, ids, view = _reach_native_frontier(mixed_oval=True)
    battlefield = view["battlefield_view"]
    assert battlefield is not None
    models = battlefield["authoritative"]["models_by_id"]
    crusher = models[ids[0]]["geometry"]["measurement_shapes"][0]
    hunter = models[ids[-1]]["geometry"]["measurement_shapes"][0]
    assert crusher["kind"] == hunter["kind"] == "ellipse"
    assert (crusher["length_inches"], crusher["width_inches"]) != (
        hunter["length_inches"],
        hunter["width_inches"],
    )

    context = _context(view)
    v1 = AllocationCoherencyPolicy(CAVALCADE_RULESET)
    assert tuple(v1.score_options(context).values()) == (False,) * 5
    first = v1.choose(context)
    assert first == context.select_option(ids[0])
    validation_calls.clear()

    with patch.object(
        allocation_coherency,
        "oval_oval_distance_ticks",
        wraps=oval_oval_distance_ticks,
    ) as compare_canonical_ovals:
        choice = AllocationCoherencyTieBreakPolicy(CAVALCADE_RULESET).choose(context)
    assert choice == first
    compare_canonical_ovals.assert_not_called()
    assert [len(call) for call in validation_calls] == [4] * 5


def test_bounded_validator_calls_and_first_coherent_short_circuit(
    native_frontier: NativeFrontier,
    validation_calls: list[tuple[str, ...]],
) -> None:
    _, ids, view = native_frontier
    policy = AllocationCoherencyTieBreakPolicy(CAVALCADE_RULESET)
    context = _context(view)
    assert policy.choose(context) == context.select_option(ids[4])
    assert [len(call) for call in validation_calls] == [4] * 5 + [3] * 10
    assert len(set(validation_calls[5:])) == 10

    validation_calls.clear()
    original = _context(screen_rod_allocation_view(SCREEN_ROD_MODEL_IDS))
    selection = original.request["options"][2]["option_id"]
    assert policy.choose(original) == original.select_option(selection)
    assert [len(call) for call in validation_calls] == [5] * 3


@pytest.mark.parametrize(
    ("indices", "loop_calls"),
    [((5, 4, 0), 7), ((2, 0, 1), 12), ((0,), 1)],
)
def test_tied_ranks_and_constrained_candidates_keep_issued_order(
    native_frontier: NativeFrontier,
    validation_calls: list[tuple[str, ...]],
    indices: tuple[int, ...],
    loop_calls: int,
) -> None:
    _, ids, view = native_frontier
    context = _context(_issued(view, tuple(ids[index] for index in indices)))
    assert AllocationCoherencyTieBreakPolicy(CAVALCADE_RULESET).choose(
        context
    ) == context.select_option(ids[indices[0]])
    assert len(validation_calls) == loop_calls


@pytest.mark.parametrize(
    "gap",
    ["missing-unit", "missing-wounds", "off-elevation", "milli-inch-disagreement", "six-models"],
)
def test_unsupported_scope_keeps_the_original_choice_and_skips_hypothetical_cleanup(
    native_frontier: NativeFrontier,
    validation_calls: list[tuple[str, ...]],
    gap: str,
) -> None:
    _, ids, original = native_frontier
    view = deepcopy(original)
    battlefield = view["battlefield_view"]
    assert battlefield is not None
    entities = battlefield["authoritative"]["models_by_id"]
    hunter_pose = entities[ids[-1]]["pose"]
    assert hunter_pose is not None
    if gap == "missing-unit":
        del view["unit_display_by_id"][_TARGET]
    elif gap == "missing-wounds":
        view["model_display_by_id"][ids[-1]]["wounds_remaining"] = None
    elif gap == "off-elevation":
        hunter_pose["position"]["z_inches"] = 0.10
    elif gap == "milli-inch-disagreement":
        # Native gap is just above 2in. Canonical oval gap is exactly 2000 ticks.
        hunter_pose["position"]["x_inches"] = 41.66712913385827
    else:
        dead = entities[ids[3]]
        dead["state"] = "placed"
        dead["pose"] = deepcopy(hunter_pose)
        assert dead["pose"] is not None
        dead["pose"]["position"]["x_inches"] = 35.45
        dead["pose"]["position"]["y_inches"] = 27.0
        view["model_display_by_id"][ids[3]]["wounds_remaining"] = 4
        request_payload = cast(dict[str, JsonValue], _request(view)["payload"])
        allocation = cast(dict[str, JsonValue], request_payload["allocation_context"])
        allocation["alive_model_ids"] = list(ids)
    context = _context(view)
    policy = AllocationCoherencyTieBreakPolicy(CAVALCADE_RULESET)
    assert policy.choose(context) == context.select_option(ids[0])
    assert len(validation_calls) == 5
    assert {len(call) for call in validation_calls} == {
        len(ids) - (1 if gap == "six-models" else 2)
    }
