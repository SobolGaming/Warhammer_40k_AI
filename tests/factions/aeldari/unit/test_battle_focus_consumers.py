from __future__ import annotations

from pathlib import Path

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
    [("fade:0", True, True), ("fade:1", True, False), ("fade:miss:private-3", False, False)],
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
        seed="fade:later-round:private-0" if history == "later_round" else "fade:0",
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


@pytest.fixture(scope="module")
def current_aeldari_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    from tests.factions.aeldari.current_source_helpers import definitions

    return definitions(selected_army_source_index)


@pytest.mark.parametrize("accept", [False, True])
def test_native_sudden_strike_charge_completion_choice_restore_and_replay(
    current_aeldari_definitions: Section02Definitions,
    accept: bool,
) -> None:
    import json

    from tests.factions.aeldari.current_source_helpers import AUTARCH, charge
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.effects import EffectExpirationKind
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.replay import ReplayRunner

    d = current_aeldari_definitions
    s = scene(
        d,
        (selection(d, AUTARCH, "charger"),),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.CHARGE,
        seed="aeldari-current-charge-False",
    )
    locate(s, "own:charger", (Pose.at(10, 10),))
    locate(s, "foe:enemy", (Pose.at(14, 10),))
    anchor(s)
    r = request(
        charge(s, "own:charger", "foe:enemy", 4 - 36 / 25.4), "select_move_completion_effect"
    )
    assert _battle_focus_spends(s) == []
    assert {o.option_id for o in r.options} == {"use", "decline"}
    assert events(s.session, "charge_move_completed")
    own_view = s.session.view(viewer_player_id="owner")["pending_decision"]
    assert own_view is not None
    assert own_view["decision_type"] == "select_move_completion_effect"
    other_view = s.session.view(viewer_player_id="opponent")["pending_decision"]
    assert other_view is not None
    assert other_view["actor_id"] == "owner"
    assert other_view["options"] == own_view["options"]
    before_invalid = s.session.to_persistence_payload()
    with pytest.raises((DecisionError, GameLifecycleError)):
        s.session.submit_option(request_id=r.request_id, option_id="invented", result_id="invalid")
    assert s.session.to_persistence_payload() == before_invalid
    saved = json.loads(json.dumps(s.session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    option = "use" if accept else "decline"
    for session in (s.session, restored):
        status = session.submit_option(
            request_id=r.request_id, option_id=option, result_id="sudden-current-choice"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert restored.lifecycle.to_payload() == s.session.lifecycle.to_payload()
    after_choice = s.session.to_persistence_payload()
    with pytest.raises(GameLifecycleError):
        s.session.submit_option(
            request_id=r.request_id, option_id=option, result_id="repeat-choice"
        )
    assert s.session.to_persistence_payload() == after_choice
    assert len(_battle_focus_spends(s)) == int(accept)
    effects = [
        e
        for e in s.state.persisting_effects
        if isinstance(e.effect_payload, dict)
        and e.effect_payload.get("effect_kind") == "fight_activation_movement_distance"
    ]
    assert len(effects) == int(accept)
    if accept:
        assert effects[0].expiration.expiration_kind is EffectExpirationKind.END_TURN
        assert effects[0].started_phase is BattlePhase.CHARGE
        assert isinstance(effects[0].effect_payload, dict)
        assert effects[0].effect_payload["pile_in_distance_inches"] == 6
        assert effects[0].effect_payload["consolidate_distance_inches"] == 6
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="sudden-current"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("count", [8, 10, 11])
def test_current_native_voidscarred_specialist_close_combat_loadouts(
    current_aeldari_definitions: Section02Definitions,
    count: int,
) -> None:
    from tests.factions.aeldari.current_source_helpers import VOIDSCARRED
    from warhammer40k_core.engine.unit_factory import UnitFactoryError, UnitInstance
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

    composition = tuple(
        ModelProfileSelection(f"{VOIDSCARRED}:{role}", number)
        for role, number in (
            ("corsair-voidscarred", count - 4),
            ("voidscarred-felarch", 1),
            ("shade-runner", 1),
            ("soul-weaver", 1),
            ("way-seeker", 1),
        )
    )
    if count == 11:
        with pytest.raises(UnitFactoryError, match="invalid"):
            current_aeldari_definitions.unit(VOIDSCARRED, composition=composition)
        return
    unit = current_aeldari_definitions.unit(VOIDSCARRED, composition=composition)
    assert len(unit.own_models) == count
    assert UnitInstance.from_payload(unit.to_payload()) == unit
    for model in unit.own_models:
        assert model.wargear_ids.count(f"{VOIDSCARRED}:close-combat-weapon") == 1
    expected = {
        "shade-runner": "paired-hekatarii-blades",
        "soul-weaver": "channeller-stones",
        "way-seeker": "witch-staff",
    }
    for role, equipment in expected.items():
        model = next(m for m in unit.own_models if m.model_profile_id == f"{VOIDSCARRED}:{role}")
        assert f"{VOIDSCARRED}:{equipment}" in model.wargear_ids


def test_native_sudden_strike_decline_then_other_charge_spends_once_per_phase(
    current_aeldari_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.current_source_helpers import AUTARCH, charge

    d = current_aeldari_definitions
    s = scene(
        d,
        tuple(selection(d, AUTARCH, name) for name in ("one", "two", "three")),
        tuple(selection(d, LORD, name) for name in ("one", "two", "three")),
        phase=BattlePhase.CHARGE,
        seed="aeldari-current-charge-False",
    )
    for i, name in enumerate(("one", "two", "three")):
        locate(s, f"own:{name}", (Pose.at(10, 10 + 12 * i),))
        locate(s, f"foe:{name}", (Pose.at(14, 10 + 12 * i),))
    anchor(s)
    r = request(charge(s, "own:one", "foe:one", 4 - 36 / 25.4), "select_move_completion_effect")
    s.session.submit_option(request_id=r.request_id, option_id="decline", result_id="decline-first")
    assert _battle_focus_spends(s) == []
    r = request(charge(s, "own:two", "foe:two", 4 - 36 / 25.4), "select_move_completion_effect")
    s.session.submit_option(request_id=r.request_id, option_id="use", result_id="use-second")
    status = charge(s, "own:three", "foe:three", 4 - 36 / 25.4)
    assert request(status).decision_type != "select_move_completion_effect"
    assert len(_battle_focus_spends(s)) == 1
    assert _battle_focus_spends(s)[0]["unit_instance_id"] == "own:two"
    assert len(events(s.session, "charge_move_completed")) == 3


def test_native_sudden_strike_six_inch_consolidation_and_turn_expiry(
    current_aeldari_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.factions.aeldari.current_source_helpers import AUTARCH, charge
    from tests.psychic_modifier_helpers import submit_fixture_request
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
    from warhammer40k_core.engine.replay import ReplayRunner
    from warhammer40k_core.geometry.pathing import PathWitness

    d = current_aeldari_definitions
    s = scene(
        d,
        (selection(d, AUTARCH, "charger"),),
        (selection(d, LORD, "enemy"), selection(d, LORD, "spare")),
        phase=BattlePhase.CHARGE,
        seed="aeldari-current-sudden-consolidation-private-0",
    )
    locate(s, "own:charger", (Pose.at(10, 10),))
    locate(s, "foe:enemy", (Pose.at(14, 10),))
    locate(s, "foe:spare", (Pose.at(16.5, 10),))
    # Explicit prior-wound checkpoint: native weapons and model profiles unchanged.
    for i, army in enumerate(s.state.army_definitions):
        s.state.army_definitions[i] = replace(
            army,
            units=tuple(
                replace(
                    unit, own_models=tuple(replace(m, wounds_remaining=1) for m in unit.own_models)
                )
                if unit.unit_instance_id == "foe:enemy"
                else unit
                for unit in army.units
            ),
        )
    anchor(s)
    r = request(
        charge(s, "own:charger", "foe:enemy", 4 - 36 / 25.4), "select_move_completion_effect"
    )
    s.session.submit_option(
        request_id=r.request_id, option_id="use", result_id="sudden-distance-use"
    )
    for _ in range(80):
        pending_move = s.session.lifecycle.pending_decision_request()
        assert pending_move is not None
        r = pending_move
        if r.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(r.payload)
            if move.proposal_kind.value == "consolidate" and move.unit_instance_id == "own:charger":
                break
        submit_fixture_request(s.session, r)
    else:
        raise AssertionError("Native consolidation not reached")
    assert move.context is not None
    assert move.context["maximum_distance_inches"] == 6
    assert events(s.session, "model_destroyed")
    assert s.state.battlefield_state is not None
    placed = s.state.battlefield_state.unit_placement_by_id("own:charger")
    model = placed.model_placements[0]
    endpoint = Pose.at(16.5 - 36 / 25.4, 10)
    via = Pose.at(model.pose.position.x, 8)
    distance = 2 + ((endpoint.position.x - model.pose.position.x) ** 2 + 4) ** 0.5
    assert 3 < distance < 6
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        result_id="sudden-six-inch-consolidation",
        payload={
            "proposal_request_id": move.request_id,
            "proposal_kind": "consolidate",
            "unit_instance_id": "own:charger",
            "movement_phase_action": "consolidate",
            "movement_mode": "consolidate",
            "consolidation_mode": "engaging",
            "consolidate_target_unit_instance_ids": ["foe:spare"],
            "witness": validate_json_value(
                PathWitness.for_paths(
                    ((model.model_instance_id, (model.pose, via, endpoint)),)
                ).to_payload()
            ),
        },
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert s.state.battlefield_state.model_placement_by_id(model.model_instance_id).pose == endpoint
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="sudden-distance"))
        .run()
        .reproduced_exactly
    )
    effects = [
        e
        for e in s.state.persisting_effects
        if isinstance(e.effect_payload, dict)
        and e.effect_payload.get("effect_kind") == "fight_activation_movement_distance"
    ]
    assert len(effects) == 1
    for _ in range(100):
        if s.state.active_player_id != "owner":
            break
        pending = s.session.lifecycle.pending_decision_request()
        if pending is None:
            s.session.advance_until_decision_or_terminal()
        else:
            submit_fixture_request(s.session, pending)
    else:
        raise AssertionError("Actual turn end not reached")
    assert effects[0] not in s.state.persisting_effects
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="sudden-expired"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize(
    ("accept", "refund_leader", "use_flitting", "seed"),
    [
        (False, False, False, "aeldari-current-charge-False"),
        (True, False, False, "aeldari-current-charge-False"),
        (False, True, False, "aeldari-current-charge-False"),
        (True, True, False, "aeldari-current-charge-False"),
        (True, True, False, "aeldari-refund-success"),
        (False, False, True, "aeldari-current-charge-False"),
    ],
)
def test_native_attached_sudden_strike_uses_group_and_source_refund(
    current_aeldari_definitions: Section02Definitions,
    accept: bool,
    refund_leader: bool,
    use_flitting: bool,
    seed: str,
) -> None:
    import math

    from tests.factions.aeldari.current_source_helpers import AUTARCH, charge
    from tests.order130_helpers import session_from_casualty_checkpoint
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration
    from warhammer40k_core.engine.replay import ReplayRunner

    d = current_aeldari_definitions
    leader_id = "000002759" if refund_leader else AUTARCH
    body_id = "000000600" if refund_leader else AVENGERS
    s = scene(
        d,
        (selection(d, body_id, "body"), selection(d, leader_id, "leader")),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.CHARGE,
        seed=seed,
        attachments=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="body"
            ),
        ),
    )
    body = s.units["own:body"]
    locate(s, "own:body", tuple(Pose.at(10, 10 + 1.3 * i) for i in range(len(body.own_models))))
    locate(s, "own:leader", (Pose.at(10, 8.7),))
    locate(s, "foe:enemy", (Pose.at(14, 10),))
    # A legal native five-model Bodyguard was mustered; four prior casualties leave
    # a normal still-attached unit. This test starts after those casualties.
    anchor(s)
    destroy_models_with_recorded_mortal_wounds(
        state=s.state,
        decisions=s.session.lifecycle.decision_controller,
        unit_instance_id="attached-unit:own:body",
        model_instance_ids=tuple(m.model_instance_id for m in body.own_models[1:]),
        application_id="attached-prior-casualties",
        destroying_player_id="opponent",
    )
    s.session = session_from_casualty_checkpoint(s.session.lifecycle)
    group = "attached-unit:own:body"
    body_radius = body.own_models[0].geometry.parts[0].radius_x_inches
    leader_radius = s.units["own:leader"].own_models[0].geometry.parts[0].radius_x_inches
    enemy_radius = s.units["foe:enemy"].own_models[0].geometry.parts[0].radius_x_inches
    body_model = body.own_models[0].model_instance_id
    leader_model = s.units["own:leader"].own_models[0].model_instance_id
    r = request(
        charge(
            s,
            group,
            "foe:enemy",
            0,
            use_flitting=use_flitting,
            endpoints={
                body_model: Pose.at(14 - body_radius - enemy_radius, 10),
                leader_model: Pose.at(
                    14 - (leader_radius + enemy_radius) / 2,
                    10 - (leader_radius + enemy_radius) * math.sqrt(3) / 2,
                ),
            },
        ),
    )
    if use_flitting:
        assert r.decision_type != "select_move_completion_effect"
        spends = _battle_focus_spends(s)
        assert len(spends) == 1
        assert spends[0]["maneuver"] == "flitting_shadows"
        assert spends[0]["unit_instance_id"] == group
        saved = s.session.to_persistence_payload()
        assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
        assert (
            ReplayRunner.from_payload(
                s.session.replay_artifact(artifact_id="attached-flitting-quota")
            )
            .run()
            .reproduced_exactly
        )
        return
    if r.decision_type == "resolve_sequencing_order":
        choice = next(o for o in r.options if "sudden_strike" in o.option_id)
        r = request(
            s.session.submit_option(
                request_id=r.request_id,
                option_id=choice.option_id,
                result_id="attached-select-sudden",
            )
        )
    assert r.decision_type == "select_move_completion_effect"
    assert isinstance(r.payload, dict)
    assert r.payload["unit_instance_id"] == group
    assert _battle_focus_spends(s) == []
    assert events(s.session, "faction_resource_refund_roll_resolved") == []
    status = s.session.submit_option(
        request_id=r.request_id,
        option_id="use" if accept else "decline",
        result_id="attached-sudden-choice",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    spends = _battle_focus_spends(s)
    assert len(spends) == int(accept)
    refunds = events(s.session, "faction_resource_refund_roll_resolved")
    assert len(refunds) == int(accept and refund_leader)
    if refunds:
        resolution = refunds[0]["resolution"]
        assert isinstance(resolution, dict)
        assert resolution["resource_kind"] == "battle_focus_token"
        assert resolution["success_threshold"] == 3
        if seed == "aeldari-refund-success":
            assert resolution["succeeded"] is True
        credits = s.state.faction_resource_ledger_for_player("owner").transactions
        assert len(credits) == int(resolution["succeeded"] is True)
        assert sum(t.amount for t in credits) == int(resolution["succeeded"] is True)
    if accept:
        assert spends[0]["unit_instance_id"] == group
        effects = [
            e
            for e in s.state.persisting_effects
            if isinstance(e.effect_payload, dict)
            and e.effect_payload.get("effect_kind") == "fight_activation_movement_distance"
        ]
        assert effects[0].target_unit_instance_ids == (group,)
    saved = s.session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="attached-sudden"))
        .run()
        .reproduced_exactly
    )


def test_current_native_voidscarred_specialists_offer_close_combat_weapons(
    current_aeldari_definitions: Section02Definitions,
) -> None:
    import math

    from tests.factions.aeldari.current_source_helpers import VOIDSCARRED
    from tests.psychic_modifier_helpers import submit_fixture_request
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
    from warhammer40k_core.engine.list_validation import UnitMusterSelection
    from warhammer40k_core.engine.replay import ReplayRunner
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

    d = current_aeldari_definitions
    unit_selection = UnitMusterSelection(
        unit_selection_id="corsairs",
        datasheet_id=VOIDSCARRED,
        model_profile_selections=tuple(
            ModelProfileSelection(f"{VOIDSCARRED}:{role}", count)
            for role, count in (
                ("corsair-voidscarred", 4),
                ("voidscarred-felarch", 1),
                ("shade-runner", 1),
                ("soul-weaver", 1),
                ("way-seeker", 1),
            )
        ),
    )
    s = scene(
        d,
        (unit_selection,),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.FIGHT,
        active="opponent",
        seed="current-specialist-melee",
    )
    locate(
        s,
        "own:corsairs",
        tuple(
            Pose.at(14 + 2.6 * math.cos(i * math.pi / 4), 14 + 2.6 * math.sin(i * math.pi / 4))
            for i in range(8)
        ),
    )
    locate(s, "foe:enemy", (Pose.at(14, 14),))
    anchor(s)
    status = s.session.advance_until_decision_or_terminal()
    for _ in range(50):
        r = request(status)
        if r.decision_type == "submit_melee_declaration":
            melee = MeleeDeclarationProposalRequest.from_decision_request(r)
            if melee.unit_instance_id == "own:corsairs":
                break
        submit_fixture_request(s.session, r)
        status = s.session.advance_until_decision_or_terminal()
    else:
        raise AssertionError("Native specialist melee declaration not reached")
    for role in ("shade-runner", "soul-weaver", "way-seeker"):
        model = next(
            m
            for m in s.units["own:corsairs"].own_models
            if m.model_profile_id == f"{VOIDSCARRED}:{role}"
        )
        assert any(
            isinstance(row, dict)
            and row.get("model_instance_id") == model.model_instance_id
            and row.get("wargear_id") == f"{VOIDSCARRED}:close-combat-weapon"
            for row in melee.available_weapons
        )
    saved = s.session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="specialist-melee"))
        .run()
        .reproduced_exactly
    )


def test_native_heroic_charge_offers_sudden_strike_in_opponents_turn(
    current_aeldari_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.current_source_helpers import AUTARCH, charge
    from tests.support.section15_fixtures import submit
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.replay import ReplayRunner

    d = current_aeldari_definitions
    s = scene(
        d,
        (selection(d, AUTARCH, "charger"), selection(d, AUTARCH, "bait")),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.CHARGE,
        active="opponent",
        seed="aeldari-current-charge-False",
    )
    locate(s, "own:charger", (Pose.at(10, 8),))
    locate(s, "own:bait", (Pose.at(14, 10),))
    locate(s, "foe:enemy", (Pose.at(18, 10),))
    s.state.gain_command_points(
        player_id="owner",
        amount=3,
        source_id="native-heroic-resource-checkpoint",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    anchor(s)
    heroic = request(charge(s, "foe:enemy", "own:bait", -(4 - 36 / 25.4)))
    assert heroic.decision_type == "submit_stratagem_target_proposal", heroic.to_payload()
    declaration = request(
        submit(s.session, heroic, "own:charger", effect={"mode": "into_the_fray"})
    )
    if declaration.decision_type == "select_stratagem_cost_modifier_option":
        decline = next(o for o in declaration.options if "decline" in o.option_id)
        declaration = request(
            s.session.submit_option(
                request_id=declaration.request_id,
                option_id=decline.option_id,
                result_id="heroic-cost-decline",
            )
        )
    assert declaration.decision_type == "select_charging_unit", declaration.to_payload()
    r = request(
        charge(
            s,
            "own:charger",
            "foe:enemy",
            0,
            endpoints={
                s.units["own:charger"].own_models[0].model_instance_id: Pose.at(
                    14 + 18 / 25.4, 10 - 36 / 25.4 * 3**0.5 / 2
                )
            },
        ),
        "select_move_completion_effect",
    )
    assert r.actor_id == "owner"
    assert s.state.active_player_id == "opponent"
    pending = s.session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(pending)
    assert restored.to_persistence_payload() == pending
    for branch in (s.session, restored):
        branch.submit_option(
            request_id=r.request_id, option_id="use", result_id="heroic-sudden-use"
        )
    assert restored.lifecycle.to_payload() == s.session.lifecycle.to_payload()
    spend = _battle_focus_spends(s)
    assert len(spend) == 1
    assert spend[0]["turn_player_id"] == "opponent"
    effect = next(
        e
        for e in s.state.persisting_effects
        if isinstance(e.effect_payload, dict)
        and e.effect_payload.get("effect_kind") == "fight_activation_movement_distance"
    )
    assert effect.expiration.player_id == "opponent"
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="heroic-sudden"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("boundary", ["exhausted", "last_token", "missing_ability"])
def test_sudden_strike_charge_end_resource_and_ability_boundaries(
    current_aeldari_definitions: Section02Definitions,
    boundary: str,
) -> None:
    from dataclasses import replace

    from tests.factions.aeldari.current_source_helpers import AUTARCH, charge
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.replay import ReplayRunner

    d = current_aeldari_definitions
    s = scene(
        d,
        (selection(d, AUTARCH, "charger"),),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.CHARGE,
        seed="aeldari-current-charge-False",
    )
    locate(s, "own:charger", (Pose.at(10, 10),))
    locate(s, "foe:enemy", (Pose.at(14, 10),))
    count = 4 if boundary == "exhausted" else 3 if boundary == "last_token" else 0
    # Explicit prior-phase resource checkpoint; this case qualifies current
    # charge-end availability/spending, not execution of the earlier spends.
    for i in range(count):
        s.state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"sudden-prior-token:{i}",
                source_rule_id="phase17f:phase17e:aeldari:army-rule",
                owner_player_id="owner",
                target_unit_instance_ids=("own:charger",),
                started_battle_round=1,
                started_phase=BattlePhase.MOVEMENT,
                expiration=EffectExpiration.end_battle_round(battle_round=1),
                effect_payload={
                    "effect_kind": "aeldari_battle_focus_token_spent",
                    "maneuver": "swift_as_the_wind",
                    "turn_player_id": "owner",
                    "unit_instance_id": "own:charger",
                    "battle_focus_token_cost": 1,
                },
            )
        )
    if boundary == "missing_ability":
        # Provider input-boundary negative only: intentionally incomplete ability
        # metadata is not represented as a legal native source construction.
        for i, army in enumerate(s.state.army_definitions):
            if army.player_id == "owner":
                s.state.army_definitions[i] = replace(
                    army,
                    units=tuple(
                        replace(
                            unit,
                            datasheet_abilities=tuple(
                                a for a in unit.datasheet_abilities if a.ability_id != "000009894"
                            ),
                        )
                        for unit in army.units
                    ),
                )
    anchor(s)
    r = request(charge(s, "own:charger", "foe:enemy", 4 - 36 / 25.4))
    assert len(_battle_focus_spends(s)) == count
    if boundary == "last_token":
        assert r.decision_type == "select_move_completion_effect"
        s.session.submit_option(
            request_id=r.request_id, option_id="use", result_id="last-sudden-token"
        )
        assert len(_battle_focus_spends(s)) == 4
    else:
        assert r.decision_type != "select_move_completion_effect"
        assert not any(
            isinstance(e.effect_payload, dict)
            and e.effect_payload.get("effect_kind") == "fight_activation_movement_distance"
            for e in s.state.persisting_effects
        )
    if boundary != "missing_ability":
        assert (
            ReplayRunner.from_payload(
                s.session.replay_artifact(artifact_id="sudden-resource-boundary")
            )
            .run()
            .reproduced_exactly
        )
