"""Native EC component attachments, physical grants and once-per-battle choices."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.support.faction_batch01 import (
    INFRACTORS,
    LORD,
    RANGERS,
    TORMENTORS,
    anchor,
    events,
    locate,
    request,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.catalog_once_per_battle_runtime import CatalogOncePerBattleRuntime
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment_ability_queries import rules_unit_has_infiltrators
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartRequestContext
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.prebattle import PreBattleProposalRequest, ScoutMoveProposal
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.scout_abilities import scout_ability_instances_for_rules_unit
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("seed", "expected_passed", "capped"),
    [
        ("faction-batch01-ec-fight-2", True, False),
        ("faction-batch01-ec-fight-3", False, False),
        ("faction-batch01-ec-fight-3", True, True),
    ],
)
def test_infractors_native_melee_rerolls_destroy_enemy_then_icon_uses_own_bearer(
    faction_definitions: Section02Definitions,
    seed: str,
    expected_passed: bool,
    capped: bool,
    tmp_path: Path,
) -> None:
    from tests.support.faction_batch01_fight import fight_to_end
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.destruction_provenance import (
        DestructionSourceKind,
        ModelDestructionAttribution,
    )
    from warhammer40k_core.engine.runtime_modifiers import AttackRerollPermissionContext

    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "infractors", equipment=("icon-of-excess",), full=True),),
        (selection(d, RANGERS, "target"),),
        phase=BattlePhase.FIGHT,
        seed=seed,
    )
    unit = s.units["own:infractors"]
    target = s.units["foe:target"]
    assert len(unit.own_models) == 10
    assert s.state.mission_setup is not None
    marker = s.state.mission_setup.objective_markers[0]
    locate(
        s,
        unit.unit_instance_id,
        tuple(
            Pose.at(
                marker.x_inches - (3.2 if i % 2 == 0 else 1.8),
                marker.y_inches - 2.8 + (i // 2) * 1.4,
            )
            for i in range(10)
        ),
    )
    locate(
        s,
        target.unit_instance_id,
        tuple(Pose.at(marker.x_inches, marker.y_inches - 2.8 + i * 1.4) for i in range(5)),
    )
    anchor(s)
    if capped:
        from warhammer40k_core.engine.command_points import CommandPointSourceKind

        s.state.gain_command_points(
            player_id="owner",
            amount=1,
            source_id="constructed:batch01:prior-other-gain",
            source_kind=CommandPointSourceKind.OTHER,
        )
    registry = s.session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry  # pyright: ignore[reportPrivateUsage]
    ctx = AttackRerollPermissionContext(
        s.state,
        "owner",
        unit.unit_instance_id,
        unit.own_model_ids()[0],
        target.unit_instance_id,
        BattlePhase.FIGHT,
        "attack_sequence.wound",
        "attack_sequence.wound",
    )
    permission = registry.attack_reroll_permission_context(ctx)
    assert permission is not None
    assert (
        registry.attack_reroll_permission_context(replace(ctx, source_phase=BattlePhase.SHOOTING))
        is None
    )
    rerolls = fight_to_end(s)
    assert rerolls
    for payload in rerolls:
        assert payload["current_values"]
        assert payload["attack_context"]["unit_instance_id"] == unit.unit_instance_id
        assert (
            payload["attack_context"]["source_payload"]["conditional_wound_reroll"][
                "full_reroll_if_target_within_objective_range"
            ]
            is True
        )
    deaths = [
        e
        for e in events(s.session, "model_destroyed")
        if e["target_unit_instance_id"] == target.unit_instance_id
    ]
    assert len(deaths) == 5
    if seed == "faction-batch01-ec-fight-2":
        # Regression: subsequent declared physical pools cancel after the last casualty.
        cancelled = events(s.session, "attack_pool_not_allocated")
        assert cancelled
        assert all(e["target_unit_instance_id"] == target.unit_instance_id for e in cancelled)
        assert all(e["reason"] == "target_destroyed_and_removed" for e in cancelled)
        saved = s.session.to_persistence_payload()
        (tmp_path / "completed-fight.json").write_text(json.dumps(saved), encoding="utf-8")
        assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
        assert (
            ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="exhausted-target"))
            .run()
            .reproduced_exactly
        )
    for death in deaths:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(death)
        assert (
            attribution.destruction_provenance.destruction_source_kind
            is DestructionSourceKind.ATTACK
        )
        assert attribution.attacking_unit_instance_id == unit.unit_instance_id
        assert attribution.attacking_model_instance_id in unit.own_model_ids()
    leadership = events(s.session, "catalog_ir_command_point_leadership_test_resolved")
    assert len(leadership) == 1
    assert leadership[0]["source_unit_instance_id"] == unit.unit_instance_id
    bearer = next(m for m in unit.own_models if f"{INFRACTORS}:icon-of-excess" in m.wargear_ids)
    assert leadership[0]["source_model_instance_id"] == bearer.model_instance_id
    assert leadership[0]["leadership_target"] == 6
    # RNG mixes the real decision/event history, including current weapon profiles.
    # Retain explicit successful, failed and capped cases after the source correction.
    rolled = cast(dict[str, Any], leadership[0]["leadership_roll"])
    modified = cast(dict[str, Any], leadership[0]["leadership_modified_roll"])
    assert rolled["original_result"]["source"] == "rng"
    assert rolled["current_total"] == sum(rolled["current_values"])
    assert modified["modifiers"] == []
    assert modified["final_value"] == rolled["current_total"]
    assert leadership[0]["passed"] is (modified["final_value"] >= 6)
    (tmp_path / "leadership-result.json").write_text(json.dumps(leadership[0]), encoding="utf-8")
    assert leadership[0]["passed"] is expected_passed
    transactions = s.state.command_point_ledger_for_player("owner").transactions
    assert (
        sum(
            t.amount
            for t in transactions
            if t.source_kind is CommandPointSourceKind.COMMAND_PHASE_START
        )
        == 1
    )
    other = tuple(t for t in transactions if t.source_kind is CommandPointSourceKind.OTHER)
    assert sum(t.amount for t in other) == int(expected_passed or capped)
    assert sum(t.amount for t in other if t.source_id == leadership[0]["source_rule_id"]) == int(
        expected_passed and not capped
    )
    if expected_passed:
        result = cast(dict[str, Any], leadership[0]["command_point_result"])
        assert result["applied_amount"] == int(not capped)
        assert result["status"] == ("capped" if capped else "applied")
        assert s.state.command_point_total("owner") == 2  # Icon/prior gain plus next Core Command.
    else:
        assert leadership[0]["command_point_result"] is None
        assert s.state.command_point_total("owner") == 1  # Next Command's Core gain only.


def test_icon_does_not_gain_cp_without_enemy_destruction(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "infractors", equipment=("icon-of-excess",)),),
        (selection(d, RANGERS, "target"),),
        phase=BattlePhase.FIGHT,
    )
    anchor(s)
    s.session.advance_until_decision_or_terminal()
    assert not events(s.session, "model_destroyed")
    assert not events(s.session, "catalog_ir_command_point_leadership_test_resolved")
    assert s.state.command_point_total("owner") == 1  # Native next Command's Core CP only.


@pytest.mark.parametrize("body_sheet", [INFRACTORS, TORMENTORS])
@pytest.mark.parametrize("attached", [False, True])
def test_native_leader_attachment_controls_conditional_setup_and_weapon_grants(
    faction_definitions: Section02Definitions,
    body_sheet: str,
    attached: bool,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, body_sheet, "body"), selection(d, LORD, "leader")),
        (selection(d, LORD, "enemy"),),
        attachments=(AttachmentDeclaration("leader", "body"),) if attached else (),
    )
    locate(s, "own:leader", (Pose.at(12.5, 15),))
    army = next(a for a in s.state.army_definitions if a.player_id == "owner")
    assert bool(army.attached_units) is attached
    group_id = army.attached_units[0].attached_unit_instance_id if attached else "own:leader"
    view = rules_unit_view_by_id(state=s.state, unit_instance_id=group_id)
    assert view.owner_player_id == "owner"
    assert {m.model_instance_id for m in view.alive_models()} == set(
        s.units["own:leader"].own_model_ids()
    ) | (set(s.units["own:body"].own_model_ids()) if attached else set())
    assert rules_unit_has_infiltrators(state=s.state, view=view) is (
        attached and body_sheet == TORMENTORS
    )
    scouts = scout_ability_instances_for_rules_unit(
        state=s.state, view=view, army_catalog=d.package.army_catalog
    )
    assert {i.model_instance_id for i in scouts} == (
        {m.model_instance_id for m in view.alive_models()}
        if attached and body_sheet == INFRACTORS
        else set()
    )
    assert all(i.distance_inches == 6 for i in scouts)
    registry = s.session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry  # pyright: ignore[reportPrivateUsage]
    leader = s.units["own:leader"]
    spear = d.weapon(f"{LORD}:phoenix-power-spear")
    ctx = WeaponProfileModifierContext(
        s.state, BattlePhase.FIGHT, group_id, leader.own_model_ids()[0], "foe:enemy", spear
    )
    modified = registry.modified_weapon_profile(ctx)
    assert (WeaponKeyword.LETHAL_HITS in modified.keywords) is attached
    if attached:
        body = s.units["own:body"]
        weapon = d.weapon(
            f"{body_sheet}:duelling-sabre" if body_sheet == INFRACTORS else f"{body_sheet}:boltgun"
        )
        assert (
            WeaponKeyword.LETHAL_HITS
            in registry.modified_weapon_profile(
                replace(
                    ctx, attacker_model_instance_id=body.own_model_ids()[0], weapon_profile=weapon
                )
            ).keywords
        )
        # A separate enemy Lord does not inherit another player's leading grant.
        enemy_ctx = replace(
            ctx,
            attacking_unit_instance_id="foe:enemy",
            attacker_model_instance_id=s.units["foe:enemy"].own_model_ids()[0],
        )
        assert WeaponKeyword.LETHAL_HITS not in registry.modified_weapon_profile(enemy_ctx).keywords


@pytest.mark.parametrize("activate", [False, True])
def test_euphoric_strikes_native_choice_owns_only_lord_melee_and_once_ledger(
    faction_definitions: Section02Definitions,
    activate: bool,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "body"), selection(d, LORD, "leader")),
        (selection(d, RANGERS, "enemy"),),
        phase=BattlePhase.FIGHT,
        attachments=(AttachmentDeclaration("leader", "body"),),
    )
    locate(s, "own:leader", (Pose.at(12.5, 15),))
    locate(s, "foe:enemy", tuple(Pose.at(18, 10 + i * 1.4) for i in range(5)))
    anchor(s)
    r = request(
        s.session.advance_until_decision_or_terminal(),
        "select_faction_rule_fight_phase_start_option",
    )
    payload = cast(dict[str, Any], r.payload)
    descriptor = next(
        a
        for a in d.package.army_catalog.datasheet_by_id(LORD).abilities
        if a.ability_id == f"{LORD}:euphoric-strikes"
    )
    assert descriptor.rule_ir_payload is not None
    ir_source = descriptor.rule_ir_payload["source_id"]
    assert payload["source_rule_id"] == descriptor.source_id
    assert payload["source_unit_instance_id"] == "own:leader"
    assert payload["source_model_instance_id"] == s.units["own:leader"].own_model_ids()[0]
    option = next(o for o in r.options if cast(dict[str, Any], o.payload)["activate"] is activate)
    valid = DecisionResult.for_request(
        request=r, selected_option_id=option.option_id, result_id="euphoric:valid"
    )
    for bad in (replace(valid, actor_id="opponent"), replace(valid, payload={})):
        before = s.session.lifecycle.to_payload()
        assert s.session.lifecycle.submit_decision(bad).status_kind is LifecycleStatusKind.INVALID
        assert s.session.lifecycle.to_payload() == before
    saved = json.loads(json.dumps(s.session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    for current in (s.session, restored):
        status = current.submit_option(
            request_id=r.request_id, option_id=option.option_id, result_id="euphoric:chosen"
        )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
        state = current.lifecycle.state
        assert state is not None
        effects = [e for e in state.persisting_effects if e.source_rule_id == ir_source]
        assert len(effects) == (2 if activate else 0)
        bundle = current.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
        army = next(a for a in state.army_definitions if a.player_id == "owner")
        group = army.attached_units[0].attached_unit_instance_id
        assert all(e.target_unit_instance_ids == (group,) for e in effects)
        assert all(
            cast(dict[str, Any], e.effect_payload)["context"]["source_model_instance_id"]
            == s.units["own:leader"].own_model_ids()[0]
            for e in effects
        )
        spear = d.weapon(f"{LORD}:phoenix-power-spear")
        ctx = WeaponProfileModifierContext(
            state,
            BattlePhase.FIGHT,
            group,
            s.units["own:leader"].own_model_ids()[0],
            "foe:enemy",
            spear,
        )
        modified = bundle.runtime_modifier_registry.modified_weapon_profile(ctx)
        assert spear.attack_profile.fixed_attacks is not None
        assert modified.attack_profile.fixed_attacks == spear.attack_profile.fixed_attacks + (
            3 if activate else 0
        )
        assert modified.armor_penetration.final == spear.armor_penetration.final - int(activate)
        pistol = d.weapon(f"{LORD}:bolt-pistol")
        assert (
            bundle.runtime_modifier_registry.modified_weapon_profile(
                replace(ctx, weapon_profile=pistol)
            ).attack_profile
            == pistol.attack_profile
        )
        sabre = d.weapon(f"{INFRACTORS}:duelling-sabre")
        body_ctx = replace(
            ctx,
            attacker_model_instance_id=s.units["own:body"].own_model_ids()[0],
            weapon_profile=sabre,
        )
        assert (
            bundle.runtime_modifier_registry.modified_weapon_profile(body_ctx).attack_profile
            == sabre.attack_profile
        )
        runtime = CatalogOncePerBattleRuntime(
            bundle.ability_indexes_by_player_id, tuple(state.army_definitions)
        )
        assert (
            runtime.fight_phase_start_request(
                FightPhaseStartRequestContext(state, current.lifecycle.decision_controller)
            )
            is None
        )
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="euphoric"))
            .run()
            .reproduced_exactly
        )
        state.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=1, phase=BattlePhaseKind.FIGHT, player_id="owner"
            )
        )
        assert (
            bundle.runtime_modifier_registry.modified_weapon_profile(ctx).attack_profile
            == spear.attack_profile
        )
        # Explicit later-window query; no traversal or admission of an intervening turn.
        state.battle_round = 2
        offered = runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(state, current.lifecycle.decision_controller)
        )
        assert (offered is not None) is (not activate)


def test_infractors_leading_lord_scouts_moves_all_physical_models_natively(
    faction_definitions: Section02Definitions,
) -> None:
    from tests.sequential_translation_helpers import leading_first_translation_paths
    from tests.setup_completion_helpers import record_current_battlefield_placements_for_fixture
    from warhammer40k_core.engine.event_log import validate_json_value

    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "body"), selection(d, LORD, "leader")),
        (selection(d, LORD, "enemy"),),
        attachments=(AttachmentDeclaration("leader", "body"),),
    )
    locate(s, "own:leader", (Pose.at(12.5, 15),))
    # Constructed pre-battle boundary: this does not certify prior deployment admission.
    s.state.stage = GameLifecycleStage.SETUP
    s.state.battle_round = 0
    s.state.setup_step_index = s.state.setup_sequence.index(SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    s.state.battle_phase_index = None
    s.state.active_player_id = None
    record_current_battlefield_placements_for_fixture(
        s.state, decisions=s.session.lifecycle.decision_controller
    )
    r = request(s.session.advance_until_decision_or_terminal(), "select_prebattle_action")
    option = next(o for o in r.options if o.option_id.startswith("scout_move:"))
    r = request(
        s.session.submit_option(
            request_id=r.request_id, option_id=option.option_id, result_id="infractors:scout"
        ),
        "submit_scout_move",
    )
    context = PreBattleProposalRequest.from_decision_request_payload(r.payload)
    assert context.scout_distance_inches == 6
    expected = set(s.units["own:body"].own_model_ids()) | set(s.units["own:leader"].own_model_ids())
    assert set(context.model_instance_ids) == expected
    assert s.state.battlefield_state is not None
    board = s.state.battlefield_state
    starts = tuple(
        p
        for a in board.placed_armies
        for u in a.unit_placements
        for p in u.model_placements
        if p.model_instance_id in expected
    )
    proposal = ScoutMoveProposal(
        context.request_id,
        context.proposal_kind,
        context.game_id,
        context.ruleset_descriptor_hash,
        context.setup_step,
        context.player_id,
        context.unit_instance_id,
        context.action_kind,
        context.source_rule_id,
        6,
        PathWitness.for_paths(
            leading_first_translation_paths(
                tuple(
                    (
                        p.model_instance_id,
                        (p.pose, Pose.at(p.pose.position.x + 0.25, p.pose.position.y)),
                    )
                    for p in starts
                ),
                dx=0.25,
            )
        ),
        context.context,
    )
    before = s.session.lifecycle.to_payload()
    invalid = s.session.submit_parameterized_payload(
        request_id=r.request_id, payload={}, result_id="infractors:scout-malformed"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.session.lifecycle.to_payload() == before
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="infractors:scout-moved",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert s.state.battlefield_state is not None
    ends = {
        p.model_instance_id: p.pose
        for a in s.state.battlefield_state.placed_armies
        for u in a.unit_placements
        for p in u.model_placements
        if p.model_instance_id in expected
    }
    assert set(ends) == expected
    for p in starts:
        assert ends[p.model_instance_id].position.x == p.pose.position.x + 0.25
    assert len(events(s.session, "prebattle_scout_move_completed")) == 1


def test_current_lord_exultant_profile_reaches_native_muster_and_restore(
    faction_definitions: Section02Definitions,
) -> None:
    """Preferred v981 profile values survive the shared catalog and native state."""
    d = faction_definitions
    catalog = d.package.army_catalog
    lord = catalog.datasheet_by_id(LORD)
    characteristics = {
        value.characteristic.value: value.final for value in lord.model_profiles[0].characteristics
    }
    assert characteristics["toughness"] == 5
    weapons = {
        profile.name: profile
        for wargear in catalog.wargear
        if wargear.wargear_id.startswith(f"{LORD}:")
        for profile in wargear.weapon_profiles
    }
    assert weapons["Bolt pistol"].strength_for_interaction() == 5
    from warhammer40k_core.core.random_profile_values import resolved_profile_characteristic

    assert resolved_profile_characteristic(weapons["Bolt pistol"].armor_penetration).final == -1
    assert weapons["Close combat weapon"].strength_for_interaction() == 5
    # Unchanged profiles and identity are positive controls, not a whole-sheet certification.
    assert lord.model_profiles[0].model_profile_id == "000004078:lord-exultant"
    assert weapons["Phoenix power spear"].strength_for_interaction() == 7
    assert weapons["Rapture lash"].strength_for_interaction() == 4
    s = scene(
        d,
        (selection(d, LORD, "lord"),),
        (selection(d, RANGERS, "target"),),
        phase=BattlePhase.SHOOTING,
        seed="ec-current-profile",
    )
    physical = s.units["own:lord"].own_models[0]
    values = {
        resolved_profile_characteristic(
            value
        ).characteristic.value: resolved_profile_characteristic(value).final
        for value in physical.characteristics
    }
    assert values["toughness"] == 5
    assert (physical.starting_wounds, physical.wounds_remaining) == (5, 5)
    saved = s.session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="ec-current-profile"))
        .run()
        .reproduced_exactly
    )


def test_current_six_ec_numeric_profiles_and_keywords() -> None:
    from tools.generate_ability_support_matrix import (
        _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
    )

    from warhammer40k_core.core.random_profile_values import resolved_profile_characteristic

    expected_models = {
        "000004078": (5, 5),
        "000004079": (5, 2),
        "000004080": (5, 2),
        "000004084": (6, 6),
        "000004088": (5, 3),
        "000004089": (5, 3),
    }
    catalog = _ability_support_catalog_package(datasheet_ids=tuple(expected_models)).army_catalog
    for sheet, (toughness, wounds) in expected_models.items():
        profile = catalog.datasheet_by_id(sheet).model_profiles[0]
        values = {value.characteristic.value: value.final for value in profile.characteristics}
        assert (values["toughness"], values["wounds"]) == (toughness, wounds)
    profiles = {
        (wargear.wargear_id.split(":")[0], profile.name): profile
        for wargear in catalog.wargear
        for profile in wargear.weapon_profiles
    }
    for sheet in ("000004078", "000004079", "000004080", "000004089"):
        pistol = profiles[sheet, "Bolt pistol"]
        assert pistol.strength_for_interaction() == 5
        assert resolved_profile_characteristic(pistol.armor_penetration).final == -1
        assert WeaponKeyword.PISTOL in pistol.keywords
    for sheet in ("000004078", "000004079", "000004084", "000004088"):
        assert profiles[sheet, "Close combat weapon"].strength_for_interaction() == 5
    boltgun = profiles["000004079", "Boltgun"]
    assert boltgun.strength_for_interaction() == 5
    assert resolved_profile_characteristic(boltgun.armor_penetration).final == -1
    assert WeaponKeyword.PRECISION in boltgun.keywords
    assert profiles["000004080", "Duelling sabre"].strength_for_interaction() == 5
    assert WeaponKeyword.PRECISION in profiles["000004080", "Duelling sabre"].keywords
    # Earlier June corrections and unrelated profiles are positive controls.
    assert profiles["000004089", "Blissblade"].attack_profile.fixed_attacks == 4
    assert profiles["000004079", "Power sword"].strength_for_interaction() == 5
    assert profiles["000004078", "Rapture lash"].strength_for_interaction() == 4


def test_current_ec_overlay_has_exact_numeric_boundary_and_stale_preimage_rejects() -> None:
    from tools.ability_support_sources import load_source_artifacts
    from tools.generate_ability_support_matrix import DEFAULT_SOURCE_JSON_DIR
    from tools.generate_emperors_children_current_profiles import generated_overlay_pack

    from warhammer40k_core.rules.source_overlay import (
        SourceOverlayError,
        apply_source_release_overlays,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        emperors_children_profiles_2026_10 as current,
    )

    pack = current.overlay_pack()
    assert pack == generated_overlay_pack()
    assert len(pack.operations) == 15
    assert sum(len(operation.fields) for operation in pack.operations) == 20
    assert all(
        set(dict(operation.fields)) <= {"T", "W", "S", "AP"} for operation in pack.operations
    )
    sources = load_source_artifacts(DEFAULT_SOURCE_JSON_DIR)
    updated = apply_source_release_overlays(
        source_artifacts=sources,
        release_manifest=current.source_release_manifest(),
        overlay_packs=(pack,),
    )
    original_rows = {
        (artifact.source_table, row.source_row_id): row
        for artifact in sources
        for row in artifact.rows
    }
    current_rows = {
        (artifact.source_table, row.source_row_id): row
        for artifact in updated
        for row in artifact.rows
    }
    assert original_rows.keys() == current_rows.keys()
    expected = {
        (operation.source_table, operation.source_row_id): dict(operation.fields)
        for operation in pack.operations
    }
    observed = {}
    for identity, before in original_rows.items():
        after = current_rows[identity]
        previous_fields, current_fields = (
            before.runtime_fields_payload(),
            after.runtime_fields_payload(),
        )
        changes = {
            key: value for key, value in current_fields.items() if previous_fields[key] != value
        }
        if changes:
            observed[identity] = changes
        if identity not in expected:
            assert before.to_payload() == after.to_payload()
    assert observed == expected
    stale = replace(pack.operations[0], expected_preimage_hash="0" * 64)
    with pytest.raises(SourceOverlayError, match="target_drift"):
        apply_source_release_overlays(
            source_artifacts=sources,
            release_manifest=current.source_release_manifest(),
            overlay_packs=(replace(pack, operations=(stale, *pack.operations[1:])),),
        )
    with pytest.raises(SourceOverlayError, match="invalid"):
        current.overlay_pack_from_json_bytes(b"not JSON")
