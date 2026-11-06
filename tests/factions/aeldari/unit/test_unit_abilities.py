from __future__ import annotations

from pathlib import Path

from tests.factions.aeldari.consumer_helpers import (
    AVENGERS,
    ELDRAD,
    LORD,
    RANGERS,
    Any,
    ArmyMusteringError,
    AttachmentDeclaration,
    BattlePhase,
    BattlePhaseKind,
    DecisionResult,
    EffectExpirationBoundary,
    LifecycleStatusKind,
    LocalGameSession,
    MovementPhaseState,
    Pose,
    ReplayRunner,
    ReserveKind,
    ReserveState,
    SaveKind,
    SaveOptionModifierContext,
    Scene,
    Section02Definitions,
    WoundRollModifierContext,
    anchor,
    attack_modifier_snapshots,
    cast,
    casualty_checkpoint,
    events,
    finish_attacks,
    json,
    locate,
    muster_army,
    pytest,
    replace,
    request,
    rules_unit_has_infiltrators,
    rules_unit_view_by_id,
    scene,
    selection,
    shooting_payload,
    shooting_request,
    submit_translation,
    translate,
    weapon_rows,
)
from tests.factions.aeldari.current_source_helpers import definitions
from tests.psychic_modifier_helpers import submit_fixture_request
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.saves import SaveOption, save_options_for_model


def test_rangers_infiltrators_and_ranged_invulnerable_queries_are_model_scoped(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, RANGERS, "rangers"), selection(d, ELDRAD, "eldrad")),
        (selection(d, LORD, "enemy"),),
    )
    rangers = s.units["own:rangers"]
    assert rules_unit_has_infiltrators(
        state=s.state,
        view=rules_unit_view_by_id(state=s.state, unit_instance_id=rangers.unit_instance_id),
    )
    assert not rules_unit_has_infiltrators(
        state=s.state, view=rules_unit_view_by_id(state=s.state, unit_instance_id="own:eldrad")
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    ranged = d.weapon(f"{LORD}:bolt-pistol")
    melee = d.weapon(f"{LORD}:phoenix-power-spear")
    context = SaveOptionModifierContext(
        s.state,
        rangers.unit_instance_id,
        (),
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id="foe:enemy",
        attacker_model_instance_id=s.units["foe:enemy"].own_model_ids()[0],
        weapon_profile=ranged,
        allocated_model_instance_id=rangers.own_model_ids()[0],
    )
    for mid in rangers.own_model_ids():
        options = bundle.runtime_modifier_registry.modified_save_options(
            replace(context, allocated_model_instance_id=mid)
        )
        assert [(o.save_kind, o.target_number) for o in options] == [(SaveKind.INVULNERABLE, 5)]
    assert (
        bundle.runtime_modifier_registry.modified_save_options(
            replace(context, weapon_profile=melee, source_phase=BattlePhase.FIGHT)
        )
        == ()
    )
    assert (
        bundle.runtime_modifier_registry.modified_save_options(
            replace(context, allocated_model_instance_id=s.units["own:eldrad"].own_model_ids()[0])
        )
        == ()
    )


def test_ranger_stealth_changes_actual_native_shooting_skill(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, RANGERS, "rangers"),),
        (selection(d, LORD, "shooter"), selection(d, LORD, "spare")),
        phase=BattlePhase.SHOOTING,
        active="opponent",
    )
    locate(s, "foe:shooter", (Pose.at(22, 10),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    r = shooting_request(s.session, "foe:shooter")
    rows = weapon_rows(r)
    rows = [row for row in rows if row["wargear_id"] == f"{LORD}:bolt-pistol"]
    assert len(rows) == 1
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=shooting_payload(r, rows, ("own:rangers",)),
        result_id="rangers:incoming-shot",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    shooting = s.state.shooting_phase_state
    assert shooting is not None
    assert len(shooting.attack_pools) == 1
    pool = shooting.attack_pools[0]
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    modifiers = attack_modifier_snapshots(
        state=s.state,
        pool=pool,
        source_phase=BattlePhase.SHOOTING,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    assert "stealth" in pool.targeting_rule_ids
    assert sum(m.modifier.operand for m in modifiers if m.kind == "skill") == 1
    finish_attacks(s.session)
    steps = events(s.session, "attack_sequence_step")
    hits = [cast(dict[str, Any], e["payload"]) for e in steps if e["step"] == "hit"]
    assert len(hits) == 1
    assert hits[0]["target_number"] == pool.weapon_profile.skill.final + 1
    assert events(s.session, "attack_sequence_completed")


def test_rangers_native_enemy_move_reaction_restores_moves_once_and_replays(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, RANGERS, "rangers"),),
        (selection(d, LORD, "mover"), selection(d, LORD, "other")),
        active="opponent",
    )
    locate(s, "foe:mover", (Pose.at(22, 10),))
    locate(s, "foe:other", (Pose.at(22, 14),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_movement_unit")
    r = request(translate(s, "foe:mover", 0.25), "select_triggered_movement")
    assert r.actor_id == "owner"
    assert {o.option_id for o in r.options} == {
        "decline_triggered_movement",
        "triggered:own:rangers",
    }
    saved = json.loads(json.dumps(s.session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    for current in (s.session, restored):
        pending = current.lifecycle.pending_decision_request()
        assert pending is not None
        r = pending
        r = request(
            current.submit_option(
                request_id=r.request_id,
                option_id="triggered:own:rangers",
                result_id="rangers:react",
            ),
            "submit_movement_proposal",
        )
        before = current.lifecycle.to_payload()
        invalid = current.submit_parameterized_payload(
            request_id=r.request_id, payload={}, result_id="rangers:malformed"
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert current.lifecycle.to_payload() == before
        assert current.lifecycle.state is not None
        branch = Scene(current, current.lifecycle.state, s.units)
        board = branch.state.battlefield_state
        assert board is not None
        starts = board.unit_placement_by_id("own:rangers")
        status = submit_translation(branch, r, "own:rangers", -0.25)
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        assert branch.state.battlefield_state is not None
        ends = branch.state.battlefield_state.unit_placement_by_id("own:rangers")
        assert [p.pose.position.x for p in ends.model_placements] == [
            p.pose.position.x - 0.25 for p in starts.model_placements
        ]
        request(status, "select_movement_unit")
        second = request(translate(branch, "foe:other", 0.25), "select_triggered_movement")
        assert {o.option_id for o in second.options} == {"decline_triggered_movement"}
        current.submit_option(
            request_id=second.request_id,
            option_id="decline_triggered_movement",
            result_id="rangers:already-moved",
        )
        assert len(events(current, "triggered_movement_resolved")) == 1
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="rangers-reactive"))
            .run()
            .reproduced_exactly
        )
    assert s.session.lifecycle.to_payload() == restored.lifecycle.to_payload()


@pytest.mark.parametrize(
    ("presence", "active"),
    [
        ("battlefield", "owner"),
        ("capped", "owner"),
        ("reserves", "owner"),
        ("destroyed", "owner"),
        ("battlefield", "opponent"),
    ],
)
def test_diviner_cp_gain_requires_own_command_phase_and_physical_presence(
    faction_definitions: Section02Definitions,
    presence: str,
    active: str,
) -> None:
    from warhammer40k_core.engine.command_points import CommandPointSourceKind

    d = faction_definitions
    s = scene(
        d,
        (selection(d, ELDRAD, "eldrad"), selection(d, AVENGERS, "body")),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.COMMAND,
        active=active,
    )
    unit = s.units["own:eldrad"]
    if presence == "capped":
        s.state.gain_command_points(
            player_id="owner",
            amount=1,
            source_id="constructed:batch01:prior-other-gain",
            source_kind=CommandPointSourceKind.OTHER,
        )
    if presence == "reserves":
        s.state.record_reserve_state(
            ReserveState.declared_before_battle(
                player_id="owner",
                unit_instance_id=unit.unit_instance_id,
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            )
        )
        assert s.state.battlefield_state is not None
        s.state.replace_battlefield_state(
            s.state.battlefield_state.without_unit_placement(unit.unit_instance_id)
        )
    elif presence == "destroyed":
        casualty_checkpoint(s, unit.own_model_ids())
    status = s.session.advance_until_decision_or_terminal()
    for i in range(12):
        if (
            status.decision_request is None
            or status.decision_request.decision_type != "resolve_sequencing_order"
        ):
            break
        r = status.decision_request
        status = s.session.submit_option(
            request_id=r.request_id,
            option_id=r.options[0].option_id,
            result_id=f"diviner:sequence:{i}",
        )
    eligible = presence in {"battlefield", "capped"} and active == "owner"
    gains = events(s.session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(eligible)
    assert s.state.command_point_total("owner") == 1 + int(eligible)
    assert s.state.command_point_total("opponent") == 1
    transactions = s.state.command_point_ledger_for_player("owner").transactions
    assert (
        sum(
            t.amount
            for t in transactions
            if t.source_kind is CommandPointSourceKind.COMMAND_PHASE_START
        )
        == 1
    )
    assert sum(
        t.amount for t in transactions if t.source_kind is CommandPointSourceKind.OTHER
    ) == int(eligible)
    if eligible:
        cp_result = cast(dict[str, Any], gains[0]["command_point_result"])
        assert cp_result["status"] == ("capped" if presence == "capped" else "applied")
        assert cp_result["applied_amount"] == int(presence != "capped")


def test_doom_selects_only_eligible_target_modifies_wounds_then_expires(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, ELDRAD, "eldrad"), selection(d, AVENGERS, "body")),
        (selection(d, LORD, "near"), selection(d, LORD, "far")),
    )
    locate(s, "foe:near", (Pose.at(20, 10),))
    locate(s, "foe:far", (Pose.at(45, 10),))
    anchor(s)
    own_ids = tuple(
        u.unit_instance_id
        for a in s.state.army_definitions
        if a.player_id == "owner"
        for u in a.units
    )
    s.state.movement_phase_state = MovementPhaseState(
        1, "owner", move_units_completed=True, selected_unit_ids=own_ids, moved_unit_ids=own_ids
    )
    r = request(
        s.session.advance_until_decision_or_terminal(), "select_catalog_movement_end_target_effect"
    )
    payload = cast(dict[str, Any], r.payload)
    assert payload["available_target_unit_instance_ids"] == ["foe:near"]
    valid = DecisionResult.for_request(
        request=r, result_id="doom:valid", selected_option_id=r.options[0].option_id
    )
    bad_payload = json.loads(json.dumps(valid.payload))
    bad_payload["selected_catalog_target_effect"]["target_unit_instance_id"] = "foe:far"
    before = s.session.lifecycle.to_payload()
    assert (
        s.session.lifecycle.submit_decision(replace(valid, payload=bad_payload)).status_kind
        is LifecycleStatusKind.INVALID
    )
    assert s.session.lifecycle.to_payload() == before
    status = s.session.submit_option(
        request_id=r.request_id, option_id=r.options[0].option_id, result_id="doom:near"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    effects = [
        e for e in s.state.persisting_effects if e.source_rule_id == payload["source_rule_id"]
    ]
    assert len(effects) == 1
    assert effects[0].target_unit_instance_ids == ("own:body", "own:eldrad")
    registry = s.session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry  # pyright: ignore[reportPrivateUsage]
    body = s.units["own:body"]
    ctx = WoundRollModifierContext(
        s.state,
        BattlePhase.SHOOTING,
        body.unit_instance_id,
        body.own_model_ids()[0],
        "foe:near",
        d.weapon(f"{AVENGERS}:avenger-shuriken-catapult"),
        4,
        4,
    )
    assert registry.wound_roll_modifier(ctx) == 1
    assert registry.wound_roll_modifier(replace(ctx, target_unit_instance_id="foe:far")) == 0
    saved = s.session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="doom"))
        .run()
        .reproduced_exactly
    )
    s.state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_start(
            battle_round=2, phase=BattlePhaseKind.COMMAND, player_id="owner"
        )
    )
    assert registry.wound_roll_modifier(ctx) == 0


def test_eldrad_leader_does_not_invent_selected_bodyguard_admission(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, ELDRAD, "eldrad"), selection(d, RANGERS, "rangers")),
        (selection(d, LORD, "enemy"),),
    )
    sheet = d.package.army_catalog.datasheet_by_id(ELDRAD)
    assert any(
        a.core_family is not None and a.core_family.value == "leader"
        for a in s.units["own:eldrad"].datasheet_abilities
    )
    assert sheet.attachment_eligibilities == ()
    own_request = next(
        r for r in s.session.lifecycle.config.army_muster_requests if r.player_id == "owner"
    )
    with pytest.raises(ArmyMusteringError, match=r"attachment|Leader|leader"):
        muster_army(
            catalog=d.package.army_catalog,
            request=replace(
                own_request, attachment_declarations=(AttachmentDeclaration("eldrad", "rangers"),)
            ),
            model_geometries=d.package.model_geometries,
        )


BANSHEES = "000000594"
JAIN_ZAR = "000000572"


@pytest.fixture(scope="module")
def save_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    return definitions(selected_army_source_index, datasheet_ids=(BANSHEES, JAIN_ZAR, LORD, ELDRAD))


def test_native_banshee_roles_keep_base_five_and_melee_four(
    save_definitions: Section02Definitions,
) -> None:
    d = save_definitions
    s = scene(
        d,
        (selection(d, BANSHEES, "banshees"), selection(d, ELDRAD, "other")),
        (selection(d, LORD, "enemy"),),
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    unit = s.units["own:banshees"]
    assert len({m.model_profile_id for m in unit.own_models}) == 2
    for model in unit.own_models:
        base = save_options_for_model(model=model, armor_penetration=-3)
        assert next(o.target_number for o in base if o.save_kind is SaveKind.INVULNERABLE) == 5
        context = SaveOptionModifierContext(
            s.state,
            unit.unit_instance_id,
            (SaveOption(SaveKind.INVULNERABLE, 5, 5, 0),),
            source_phase=BattlePhase.FIGHT,
            weapon_profile=d.weapon(f"{LORD}:phoenix-power-spear"),
            allocated_model_instance_id=model.model_instance_id,
        )
        options = bundle.runtime_modifier_registry.modified_save_options(context)
        assert [(o.save_kind, o.target_number) for o in options] == [(SaveKind.INVULNERABLE, 4)]
        for changed in (
            replace(context, weapon_profile=d.weapon(f"{LORD}:bolt-pistol")),
            replace(context, weapon_profile=None),
            replace(context, allocated_model_instance_id=None),
            replace(context, allocated_model_instance_id=s.units["own:other"].own_model_ids()[0]),
            replace(context, target_unit_instance_id="own:other"),
        ):
            assert (
                bundle.runtime_modifier_registry.modified_save_options(changed)
                == context.save_options
            )
        # Weapon kind, not phase name, controls an incoming-attack restriction.
        assert (
            bundle.runtime_modifier_registry.modified_save_options(
                replace(context, source_phase=BattlePhase.SHOOTING)
            )
            == options
        )
        assert (
            bundle.runtime_modifier_registry.modified_save_options(
                replace(context, save_options=(SaveOption(SaveKind.INVULNERABLE, 3, 3, 0),))
            )[0].target_number
            == 3
        )


@pytest.mark.parametrize(("role", "seed"), (("howling-banshees", 4), ("howling-banshee-exarch", 1)))
def test_native_fight_melee_save_restore_and_exact_replay(
    save_definitions: Section02Definitions, role: str, seed: int
) -> None:
    d = save_definitions
    s = scene(
        d,
        (selection(d, BANSHEES, "banshees"),),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.FIGHT,
        seed=f"banshee-melee-save-{seed}",
    )
    unit = s.units["own:banshees"]
    survivor = next(m for m in unit.own_models if m.model_profile_id == f"{BANSHEES}:{role}")
    remaining = tuple(m for m in unit.own_models if m != survivor)
    positions = {survivor.model_instance_id: Pose.at(10, 10)}
    positions.update(
        {m.model_instance_id: Pose.at(10 - 1.3 * (i + 1), 10) for i, m in enumerate(remaining)}
    )
    locate(s, "own:banshees", tuple(positions[m.model_instance_id] for m in unit.own_models))
    locate(s, "foe:enemy", (Pose.at(12, 10),))
    anchor(s)
    status = s.session.advance_until_decision_or_terminal()
    restored = None
    for _ in range(100):
        r = request(status)
        if r.decision_type == "submit_melee_declaration" and r.actor_id == "opponent":
            saved = s.session.to_persistence_payload()
            restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(saved)))
            assert restored.to_persistence_payload() == saved
            for player in ("owner", "opponent"):
                assert restored.view(viewer_player_id=player) == s.session.view(
                    viewer_player_id=player
                )
        _submit_attack_choice(s.session, r, survivor.model_instance_id)
        if restored is not None:
            rr = restored.lifecycle.pending_decision_request()
            assert rr is not None
            assert rr.to_payload() == r.to_payload()
            _submit_attack_choice(restored, rr, survivor.model_instance_id)
            assert restored.to_persistence_payload() == s.session.to_persistence_payload()
        if len(events(s.session, "attack_sequence_completed")) >= 2:
            break
        status = s.session.advance_until_decision_or_terminal()
    else:
        raise AssertionError("Native Fight attack did not finish")
    saves = [
        cast(dict[str, Any], e.payload)["payload"]
        for e in s.session.lifecycle.decision_controller.event_log.records
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "save"
        and "foe:enemy" in str(e.payload.get("sequence_id"))
    ]
    assert any(
        v["unmodified_roll"] == 4
        and v["successful"]
        and v["save_kind"] == "invulnerable"
        and v["target_number"] == 4
        and v["option"]["characteristic_trace"]["source_value"] == 5
        and f":{role}:" in v["allocated_model_id"]
        for v in saves
    )
    assert restored is not None
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="banshee-save"))
        .run()
        .reproduced_exactly
    )


def test_attached_bodyguard_save_does_not_transfer_to_leader(
    save_definitions: Section02Definitions,
) -> None:
    d = save_definitions
    s = scene(
        d,
        (selection(d, BANSHEES, "banshees"), selection(d, JAIN_ZAR, "leader")),
        (selection(d, LORD, "enemy"),),
        attachments=(AttachmentDeclaration("leader", "banshees"),),
    )
    attached = next(a for a in s.state.army_definitions if a.player_id == "owner").attached_units[0]
    registry = s.session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry  # pyright: ignore[reportPrivateUsage]
    context = SaveOptionModifierContext(
        s.state,
        attached.attached_unit_instance_id,
        (),
        source_phase=BattlePhase.FIGHT,
        weapon_profile=d.weapon(f"{LORD}:phoenix-power-spear"),
        allocated_model_instance_id=s.units["own:banshees"].own_model_ids()[0],
    )
    for model_id in s.units["own:banshees"].own_model_ids():
        options = registry.modified_save_options(
            replace(context, allocated_model_instance_id=model_id)
        )
        assert [(o.save_kind, o.target_number) for o in options] == [(SaveKind.INVULNERABLE, 4)]
    # Empty input isolates the Banshee grant from Jain Zar's own printed 4+ base.
    assert (
        registry.modified_save_options(
            replace(context, allocated_model_instance_id=s.units["own:leader"].own_model_ids()[0])
        )
        == ()
    )
    assert (
        registry.modified_save_options(
            replace(context, weapon_profile=d.weapon(f"{LORD}:bolt-pistol"))
        )
        == ()
    )


def _submit_attack_choice(session: LocalGameSession, r: DecisionRequest, model_id: str) -> None:
    if r.decision_type == "submit_melee_declaration" and r.actor_id == "opponent":
        melee = MeleeDeclarationProposalRequest.from_decision_request(r)
        weapon = next(
            cast(dict[str, Any], w)
            for w in melee.available_weapons
            if isinstance(w, dict) and w["wargear_id"] == f"{LORD}:phoenix-power-spear"
        )
        status = session.submit_parameterized_payload(
            request_id=r.request_id,
            result_id=f"{r.request_id}:native-spear",
            payload={
                "proposal_request_id": melee.request_id,
                "proposal_kind": melee.proposal_kind,
                "player_id": melee.actor_id,
                "battle_round": melee.battle_round,
                "unit_instance_id": melee.unit_instance_id,
                "source_decision_request_id": melee.source_decision_request_id,
                "source_decision_result_id": melee.source_decision_result_id,
                "declarations": [
                    {
                        "attacker_model_instance_id": weapon["model_instance_id"],
                        "weapon_instance_id": weapon["weapon_instance_id"],
                        "wargear_id": weapon["wargear_id"],
                        "weapon_profile_id": weapon["weapon_profile_id"],
                        "target_allocations": [{"target_unit_instance_id": "own:banshees"}],
                    }
                ],
            },
        )
        assert status.status_kind.value != "invalid", status.to_payload()
    elif r.decision_type == "select_allocation_order":
        option = next(
            o
            for o in r.options
            if model_id in cast(dict[str, Any], o.payload)["ordered_groups"][0]["model_ids"]
        )
        session.submit_option(
            request_id=r.request_id,
            option_id=option.option_id,
            result_id=f"{r.request_id}:native-order",
        )
    elif r.decision_type == "select_damage_allocation_model" and any(
        o.option_id == model_id for o in r.options
    ):
        session.submit_option(
            request_id=r.request_id, option_id=model_id, result_id=f"{r.request_id}:native-model"
        )
    else:
        submit_fixture_request(session, r)


def test_native_ranged_attack_keeps_five_plus_save(save_definitions: Section02Definitions) -> None:
    d = save_definitions
    s = scene(
        d,
        (selection(d, BANSHEES, "banshees"),),
        (selection(d, LORD, "enemy"),),
        phase=BattlePhase.SHOOTING,
        active="opponent",
        seed="banshee-ranged-save-2",
    )
    unit = s.units["own:banshees"]
    locate(s, "own:banshees", tuple(Pose.at(10 - i * 1.3, 10) for i in range(len(unit.own_models))))
    locate(s, "foe:enemy", (Pose.at(16, 10),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    r = shooting_request(s.session, "foe:enemy")
    rows = [
        row
        for row in weapon_rows(r)
        if row["wargear_id"] == f"{LORD}:plasma-pistol"
        and str(row["weapon_profile_id"]).endswith(":standard")
    ]
    assert len(rows) == 1
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        result_id=f"{r.request_id}:plasma",
        payload=shooting_payload(r, rows, ("own:banshees",)),
    )
    for _ in range(30):
        if events(s.session, "attack_sequence_completed"):
            break
        rr = request(status)
        _submit_attack_choice(s.session, rr, unit.own_model_ids()[0])
        status = s.session.advance_until_decision_or_terminal()
    else:
        raise AssertionError("Native ranged attack did not finish")
    saves = [
        cast(dict[str, Any], e.payload)["payload"]
        for e in s.session.lifecycle.decision_controller.event_log.records
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "save"
    ]
    assert saves, [
        (v.get("step"), v.get("payload")) for v in events(s.session, "attack_sequence_step")
    ]
    assert any(
        v["save_kind"] == "invulnerable" and v["target_number"] == 5 and v["successful"]
        for v in saves
    ), saves
    for value in saves:
        invulnerable = next(o for o in value["save_options"] if o["save_kind"] == "invulnerable")
        assert invulnerable["target_number"] == 5
        assert not any("conditional-melee" in source for source in invulnerable["source_rule_ids"])
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="banshee-ranged-save"))
        .run()
        .reproduced_exactly
    )
