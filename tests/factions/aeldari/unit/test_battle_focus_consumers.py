from __future__ import annotations

from tests.factions.aeldari.consumer_helpers import (
    AVENGERS,
    ELDRAD,
    LORD,
    Any,
    BattlePhase,
    LifecycleStatusKind,
    Pose,
    Section02Definitions,
    _accept_normal_reaction,
    _assert_normal_reaction,
    _battle_focus_spends,
    _choice,
    _fall_back,
    _pending,
    anchor,
    cast,
    events,
    finish_attacks,
    locate,
    pytest,
    request,
    scene,
    selection,
    shooting_payload,
    shooting_request,
    weapon_rows,
)


def test_opportunity_seized_native_fall_back_decline_then_normal_move(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (
            selection(d, ELDRAD, "reactor"),
            selection(d, AVENGERS, "other"),
            selection(d, AVENGERS, "declined"),
        ),
        tuple(selection(d, LORD, name) for name in ("first", "second", "third", "spare")),
        active="opponent",
    )
    locate(s, "own:other", tuple(Pose.at(10, 22 + i * 1.5) for i in range(5)))
    locate(s, "own:declined", tuple(Pose.at(10, 34 + i * 1.5) for i in range(5)))
    locate(s, "foe:first", (Pose.at(11.5, 34),))
    locate(s, "foe:second", (Pose.at(11.5, 10),))
    locate(s, "foe:third", (Pose.at(11.5, 22),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_movement_unit")
    r = request(_fall_back(s, "foe:first"), "select_triggered_movement")
    assert {o.option_id for o in r.options} == {
        "decline_triggered_movement",
        "triggered:own:declined",
    }
    assert s.state.battlefield_state is not None
    before = s.state.battlefield_state
    request(_choice(s, "decline_triggered_movement"), "select_movement_unit")
    assert s.state.battlefield_state == before
    assert _battle_focus_spends(s) == []
    r = request(_fall_back(s, "foe:second"), "select_triggered_movement")
    _assert_normal_reaction(s, r, "opportunity_seized")
    _accept_normal_reaction(s, recover=True)
    # A fresh, otherwise eligible unit cannot repeat this manoeuvre this phase.
    r = request(_fall_back(s, "foe:third"), "select_movement_unit")
    assert r.actor_id == "opponent"
    assert len(_battle_focus_spends(s)) == 1


@pytest.mark.parametrize(
    ("seed", "hit", "accept"),
    [("fade:0", True, True), ("fade:1", True, False), ("fade:6", False, False)],
)
def test_fade_back_native_hit_or_miss_controls_normal_move(
    faction_definitions: Section02Definitions,
    seed: str,
    hit: bool,
    accept: bool,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, ELDRAD, "reactor"), selection(d, AVENGERS, "other")),
        (selection(d, LORD, "shooter"), selection(d, LORD, "spare")),
        active="opponent",
        phase=BattlePhase.SHOOTING,
        seed=seed,
    )
    locate(s, "foe:shooter", (Pose.at(18, 10),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    r = shooting_request(s.session, "foe:shooter")
    rows = [row for row in weapon_rows(r) if row["wargear_id"] == f"{LORD}:bolt-pistol"]
    assert len(rows) == 1
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=shooting_payload(r, rows, ("own:reactor",)),
        result_id=f"{r.request_id}:incoming",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    finish_attacks(s.session)
    hits = [
        cast(dict[str, Any], e["payload"])
        for e in events(s.session, "attack_sequence_step")
        if e["step"] == "hit"
    ]
    assert len(hits) == 1
    assert hits[0]["successful"] is hit
    assert s.state.battlefield_state is not None
    before = s.state.battlefield_state.unit_placement_by_id("own:reactor")
    r = _pending(s)
    if hit:
        _assert_normal_reaction(s, r, "fade_back")
        if accept:
            _accept_normal_reaction(s)
        else:
            request(_choice(s, "decline_triggered_movement"), "select_shooting_unit")
            assert s.state.battlefield_state.unit_placement_by_id("own:reactor") == before
            assert _battle_focus_spends(s) == []
    else:
        assert r.decision_type == "select_shooting_unit"
        assert events(s.session, "shooting_end_surge_triggered") == []
        assert s.state.battlefield_state.unit_placement_by_id("own:reactor") == before
        assert _battle_focus_spends(s) == []
    # The remaining enemy activation can continue lawfully even without a target.
    assert s.session.lifecycle.pending_decision_request() is not None
    r = shooting_request(s.session, "foe:spare")
    assert r.decision_type == "select_charging_unit"


@pytest.mark.parametrize(
    ("maneuver", "history"),
    [
        (m, h)
        for m in ("opportunity_seized", "fade_back")
        for h in ("unit_used", "maneuver_used", "exhausted", "last_token", "later_round")
    ]
    + [("opportunity_seized", "earlier_turn")],
)
def test_native_battle_focus_availability_respects_carried_history(
    faction_definitions: Section02Definitions,
    maneuver: str,
    history: str,
) -> None:
    """Explicit prior-spend checkpoint; only the new trigger and consequence run here."""
    from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect

    d = faction_definitions
    phase = BattlePhase.MOVEMENT if maneuver == "opportunity_seized" else BattlePhase.SHOOTING
    s = scene(
        d,
        (selection(d, ELDRAD, "reactor"), selection(d, AVENGERS, "other")),
        (selection(d, LORD, "shooter"), selection(d, LORD, "spare")),
        active="opponent",
        phase=phase,
        seed="fade:0",
    )
    if history == "later_round":
        s.state.battle_round = 2
    # Preserve exact source semantics: old phase spends consume round tokens,
    # while one-per-unit and one-per-manoeuvre restrictions expire by phase.
    count = 4 if history in {"exhausted", "later_round"} else 3 if history == "last_token" else 1
    prior_rows = [
        ("own:other", "swift_as_the_wind", BattlePhaseKind.MOVEMENT),
        ("own:other", "flitting_shadows", BattlePhaseKind.CHARGE),
        ("own:other", "sudden_strike", BattlePhaseKind.FIGHT),
        ("own:reactor", "swift_as_the_wind", BattlePhaseKind.MOVEMENT),
    ]
    for i in range(count):
        unit_id, prior_maneuver, started_phase = prior_rows[i]
        if history == "unit_used":
            unit_id, prior_maneuver, started_phase = (
                "own:reactor",
                "flitting_shadows",
                BattlePhaseKind(phase.value),
            )
        elif history == "maneuver_used":
            prior_maneuver, started_phase = maneuver, BattlePhaseKind(phase.value)
        elif history == "earlier_turn":
            unit_id = "own:reactor"
        s.state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"prior-battle-focus:{i}",
                source_rule_id="phase17f:phase17e:aeldari:army-rule",
                owner_player_id="owner",
                target_unit_instance_ids=(unit_id,),
                started_battle_round=1,
                started_phase=started_phase,
                expiration=EffectExpiration.end_battle_round(battle_round=1),
                effect_payload={
                    "effect_kind": "aeldari_battle_focus_token_spent",
                    "maneuver": prior_maneuver,
                    "turn_player_id": "opponent"
                    if history in {"unit_used", "maneuver_used"}
                    else "owner",
                    "unit_instance_id": unit_id,
                    "battle_focus_token_cost": 1,
                },
            )
        )
    locate(s, "foe:shooter", (Pose.at(11.5 if phase is BattlePhase.MOVEMENT else 18, 10),))
    anchor(s)
    s.session.advance_until_decision_or_terminal()
    if phase is BattlePhase.MOVEMENT:
        status = _fall_back(s, "foe:shooter")
    else:
        r = shooting_request(s.session, "foe:shooter")
        rows = [row for row in weapon_rows(r) if row["wargear_id"] == f"{LORD}:bolt-pistol"]
        s.session.submit_parameterized_payload(
            request_id=r.request_id,
            payload=shooting_payload(r, rows, ("own:reactor",)),
            result_id=f"{r.request_id}:incoming",
        )
        finish_attacks(s.session)
        hits = [
            cast(dict[str, Any], e["payload"])
            for e in events(s.session, "attack_sequence_step")
            if e["step"] == "hit"
        ]
        assert hits[0]["successful"]
        status = s.session.advance_until_decision_or_terminal()
    r = request(status)
    if history in {"unit_used", "maneuver_used", "exhausted"}:
        assert r.decision_type == (
            "select_movement_unit" if phase is BattlePhase.MOVEMENT else "select_shooting_unit"
        )
        assert len(_battle_focus_spends(s)) == count
    else:
        _assert_normal_reaction(s, r, maneuver)
        _accept_normal_reaction(s)
        # Accepted fourth token is consumed once; earlier phase history cannot block it.
        assert len(_battle_focus_spends(s)) == count + 1
