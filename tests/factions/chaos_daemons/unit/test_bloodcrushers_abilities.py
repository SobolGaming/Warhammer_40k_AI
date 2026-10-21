from __future__ import annotations

from tests.factions.chaos_daemons.consumer_helpers import (
    CRUSHERS,
    LORD,
    BattlePhase,
    DecisionResult,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    Path,
    Pose,
    ReplayRunner,
    Section02Definitions,
    anchor,
    begin,
    cast,
    casualty_checkpoint,
    choose,
    events,
    json,
    locate,
    propose,
    pytest,
    replace,
    request,
    roll,
    scene,
    selection,
    targets,
    witness,
)


def test_brass_stampede_native_charge_completion(
    faction_definitions: Section02Definitions, tmp_path: Path
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (
            selection(d, CRUSHERS, "crushers", equipment=("instrument-of-chaos",)),
            selection(d, CRUSHERS, "spare"),
        ),
        (selection(d, CRUSHERS, "target"),),
        phase=BattlePhase.CHARGE,
    )
    unit = s.units["own:crushers"]
    target = s.units["foe:target"]
    locate(s, unit.unit_instance_id, tuple(Pose.at(10, 10 + i * 2.5) for i in range(3)))
    locate(s, target.unit_instance_id, tuple(Pose.at(16, 10 + i * 2.5) for i in range(3)))
    anchor(s)
    r = begin(s.session)
    choose(s.session, unit.unit_instance_id)
    targets(s.session, (target.unit_instance_id,))
    result = roll(s.session)
    assert result.value == result.request.resolve_roll(result.roll_state).unmodified.value + 1
    status = propose(
        s.session,
        unit.unit_instance_id,
        (target.unit_instance_id,),
        witness(s.state, unit.unit_instance_id, 2.0),
    )
    r = request(status)
    assert r.decision_type == "select_catalog_unit_move_completed_mortal_wounds_target"
    assert isinstance(r.payload, dict)
    assert r.payload["roll_model_instance_ids"] == list(unit.own_model_ids())
    assert r.payload["available_target_unit_instance_ids"] == [target.unit_instance_id]
    assert str(r.payload["source_rule_id"]).endswith("Datasheets_abilities:000001115:5")
    valid = DecisionResult.for_request(
        result_id="stampede:target",
        request=r,
        selected_option_id=r.options[0].option_id,
    )
    for bad in (replace(valid, actor_id="opponent"), replace(valid, payload={})):
        before = s.session.lifecycle.to_payload()
        invalid = s.session.lifecycle.submit_decision(bad)
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert s.session.lifecycle.to_payload() == before
    phase = s.state.battle_phase_index
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.FIGHT)
    before = s.session.lifecycle.to_payload()
    assert s.session.lifecycle.submit_decision(valid).status_kind is LifecycleStatusKind.INVALID
    assert s.session.lifecycle.to_payload() == before
    s.state.battle_phase_index = phase
    board = s.state.battlefield_state
    locate(s, target.unit_instance_id, tuple(Pose.at(30, 10 + i * 2.5) for i in range(3)))
    before = s.session.lifecycle.to_payload()
    assert s.session.lifecycle.submit_decision(valid).status_kind is LifecycleStatusKind.INVALID
    assert s.session.lifecycle.to_payload() == before
    assert board is not None
    s.state.replace_battlefield_state(board)
    saved = json.loads(json.dumps(s.session.to_persistence_payload()))
    (tmp_path / "stampede-pending.json").write_text(json.dumps(saved, indent=2), encoding="utf8")
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    branch = s.session.fork()
    before_hp = sum(m.current_wounds for m in target.own_models)
    for current in (s.session, restored, branch):
        status = current.submit_option(
            request_id=r.request_id,
            option_id=r.options[0].option_id,
            result_id="stampede:accepted",
        )
        for i in range(30):
            if (
                status.decision_request is None
                or status.decision_request.decision_type != "select_mortal_wound_model"
            ):
                break
            child = status.decision_request
            status = current.submit_option(
                request_id=child.request_id,
                option_id=child.options[0].option_id,
                result_id=f"stampede:allocate:{i}",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            pytest.fail("Brass Stampede allocation did not terminate")
        request(status, "select_charging_unit")
        rolled = events(current, "unit_move_completed_mortal_wounds_rolled")
        assert len(rolled) == 3
        assert {
            cast(
                str,
                cast(dict[str, JsonValue], row["replay_payload"])["roll_model_instance_id"],
            )
            for row in rolled
        } == set(unit.own_model_ids())
        resolved = events(current, "unit_move_completed_mortal_wounds_resolved")
        damage = sum(cast(int, row["mortal_wounds"]) for row in resolved)
        assert damage > 0
        assert current.lifecycle.state is not None
        live_target = next(
            u
            for a in current.lifecycle.state.army_definitions
            for u in a.units
            if u.unit_instance_id == target.unit_instance_id
        )
        assert sum(m.current_wounds for m in live_target.own_models) == before_hp - damage
        assert len(events(current, "charge_move_completed")) == 1
        assert (
            len(events(current, "catalog_unit_move_completed_mortal_wounds_target_selected")) == 1
        )
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="stampede"))
            .run()
            .reproduced_exactly
        )
    assert (
        restored.lifecycle.to_payload()
        == branch.lifecycle.to_payload()
        == s.session.lifecycle.to_payload()
    )
    for viewer in ("owner", "opponent"):
        view = s.session.view(viewer_player_id=viewer)
        assert json.loads(json.dumps(view)) == view


@pytest.mark.parametrize("bearer_alive", [True, False])
def test_instrument_changes_native_charge_roll_only_while_physical_bearer_lives(
    faction_definitions: Section02Definitions, bearer_alive: bool
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (
            selection(d, CRUSHERS, "crushers", equipment=("instrument-of-chaos",)),
            selection(d, CRUSHERS, "spare"),
        ),
        (selection(d, LORD, "target"),),
        phase=BattlePhase.CHARGE,
    )
    unit = s.units["own:crushers"]
    bearer = next(m for m in unit.own_models if f"{CRUSHERS}:instrument-of-chaos" in m.wargear_ids)
    assert sum(f"{CRUSHERS}:instrument-of-chaos" in m.wargear_ids for m in unit.own_models) == 1
    locate(s, unit.unit_instance_id, tuple(Pose.at(10, 10 + i * 2.5) for i in range(3)))
    locate(s, "foe:target", (Pose.at(15, 10),))
    if not bearer_alive:
        casualty_checkpoint(s, (bearer.model_instance_id,))
    begin(s.session)
    choose(s.session, unit.unit_instance_id)
    result = roll(s.session)
    unmodified = result.request.resolve_roll(result.roll_state).unmodified.value
    assert result.value == unmodified + int(bearer_alive)
    assert len(result.request.roll_modifiers) == int(bearer_alive)
    assert result.request.spec.expression.modifier == 0
    assert (
        events(s.session, "charge_roll_resolved")[-1]["unit_instance_id"] == unit.unit_instance_id
    )


@pytest.mark.parametrize("bearer_alive", [True, False])
def test_icon_leadership_query_uses_current_physical_bearer(
    faction_definitions: Section02Definitions, bearer_alive: bool
) -> None:
    from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests

    d = faction_definitions
    s = scene(
        d,
        (selection(d, CRUSHERS, "crushers", equipment=("daemonic-icon",)),),
        (selection(d, LORD, "target"),),
        phase=BattlePhase.COMMAND,
    )
    unit = s.units["own:crushers"]
    bearer = next(m for m in unit.own_models if f"{CRUSHERS}:daemonic-icon" in m.wargear_ids)
    nonbearers = [m for m in unit.own_models if m != bearer]
    assert len(nonbearers) == 2
    surviving = bearer if bearer_alive else nonbearers[0]
    casualty_checkpoint(s, tuple(m.model_instance_id for m in unit.own_models if m != surviving))
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    assert s.state.battlefield_state is not None
    army = next(a for a in s.state.army_definitions if a.player_id == "owner")
    baseline = collect_battle_shock_test_requests(
        game_id=s.state.game_id,
        battle_round=1,
        player_id="owner",
        army=army,
        battlefield_state=s.state.battlefield_state,
        starting_strength_records=tuple(s.state.starting_strength_records),
        battle_shocked_unit_ids=(),
    )
    loaded = collect_battle_shock_test_requests(
        game_id=s.state.game_id,
        battle_round=1,
        player_id="owner",
        army=army,
        battlefield_state=s.state.battlefield_state,
        starting_strength_records=tuple(s.state.starting_strength_records),
        battle_shocked_unit_ids=(),
        ability_index=bundle.ability_indexes_by_player_id["owner"],
    )
    assert len(baseline) == len(loaded) == 1
    assert baseline[0].leadership_target == 7
    assert loaded[0].leadership_target == (6 if bearer_alive else 7)
    assert s.state.battlefield_state is not None
    assert tuple(
        p.model_instance_id
        for p in s.state.battlefield_state.unit_placement_by_id(
            unit.unit_instance_id
        ).model_placements
    ) == (surviving.model_instance_id,)
