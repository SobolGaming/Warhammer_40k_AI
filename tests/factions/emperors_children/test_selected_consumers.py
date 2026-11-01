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


@pytest.fixture(scope="module")
def current_ec_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    from tools.generate_ability_support_matrix import (
        _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
    )

    return Section02Definitions(
        _ability_support_catalog_package(
            datasheet_ids=("000004081", "000004083", "000000611", "000004080", "000004078"),
            source_index_dir=selected_army_source_index,
        ),
        0.0,
    )


@pytest.mark.parametrize("role", ["chaos-terminators", "terminator-champion"])
@pytest.mark.parametrize("weapon_name", ["combi-bolter", "combi-weapon"])
def test_current_terminator_native_weapons_change_wound_and_armour_save(
    current_ec_definitions: Section02Definitions,
    role: str,
    weapon_name: str,
) -> None:
    from tests.support.section02_consumers import attack_pool
    from tests.support.section04_fixtures import combat_state
    from tests.support.section05_sequence import fixed_sequence_dice, payloads, resolve
    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.unit_factory import UnitInstance
    from warhammer40k_core.engine.wargear_selections import WargearSelection
    from warhammer40k_core.engine.weapon_instances import (
        equipped_weapon_profile_instances_for_model,
    )

    d = current_ec_definitions
    sheet = d.package.army_catalog.datasheet_by_id("000004081")
    wargear_id = f"000004081:{weapon_name}"
    choices: tuple[WargearSelection, ...] = ()
    if weapon_name == "combi-weapon":
        option = next(
            o
            for o in sheet.wargear_options
            if wargear_id in o.allowed_wargear_ids and o.model_profile_id == f"000004081:{role}"
        )
        choices = (WargearSelection(option.option_id, f"000004081:{role}", (wargear_id,)),)
    unit = d.unit("000004081", wargear=choices)
    assert UnitInstance.from_payload(unit.to_payload()).to_payload() == unit.to_payload()
    model = next(
        m
        for m in unit.own_models
        if m.model_profile_id == f"000004081:{role}"
        and any(
            w.wargear_id == wargear_id
            for w in equipped_weapon_profile_instances_for_model(
                model=m, army_catalog=d.package.army_catalog
            )
        )
    )
    physical = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=model, army_catalog=d.package.army_catalog
        )
        if w.wargear_id == wargear_id
    )
    weapon = physical.weapon_profile
    assert weapon.strength_for_interaction() == 5
    assert weapon.armor_penetration.final == -1
    target = d.unit("000000611", army_id="enemy", identity="target")
    from warhammer40k_core.core.attributes import Characteristic

    assert len(target.own_models) == 1
    assert {
        v.characteristic: v.final
        for v in target.own_models[0].characteristics
        if v.characteristic in (Characteristic.TOUGHNESS, Characteristic.SAVE)
    } == {Characteristic.TOUGHNESS: 9, Characteristic.SAVE: 3}
    assert "VEHICLE" in target.own_models[0].keywords
    assert "INFANTRY" not in target.own_models[0].keywords
    # Native single-model T9, Sv3+ VEHICLE: S5 wounds on5 and AP-1 makes save3 fail.
    # Anti-Infantry cannot replace this S/T check; the target has no invulnerable save.
    pool = replace(
        attack_pool(unit, target, weapon, wargear_id),
        attacker_model_instance_id=model.model_instance_id,
        weapon_instance_id=physical.weapon_instance_id,
    )
    sequence = AttackSequence(
        "s05", "owner", unit.unit_instance_id, (pool,), source_phase=BattlePhase.SHOOTING
    )
    state = combat_state(d, unit, target=target, distance=18)
    n = pool.attacks
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (5,) * n, (5,) * n, (3,) * n)
    )
    assert remaining is None, status
    assert status is None
    steps = payloads(decisions, "attack_sequence_step")
    assert len([p for p in steps if p["step"] == "wound"]) == n
    assert len([p for p in steps if p["step"] == "save"]) == n
    assert model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds == (
        target.own_models[0].current_wounds - n
    )


@pytest.mark.parametrize("sheet", ["000004081", "000004083"])
@pytest.mark.parametrize("face", [4, 5])
def test_current_native_toughness_changes_real_wound_resolution(
    current_ec_definitions: Section02Definitions,
    sheet: str,
    face: int,
) -> None:
    from tests.support.section05_sequence import (
        fixed_sequence_dice,
        native_sequence,
        payloads,
        resolve,
    )
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.unit_factory import UnitInstance

    d = current_ec_definitions
    target = d.unit(sheet, army_id="enemy", identity="target")
    assert UnitInstance.from_payload(target.to_payload()).to_payload() == target.to_payload()
    assert {
        v.final
        for m in target.own_models
        for v in m.characteristics
        if v.characteristic is Characteristic.TOUGHNESS
    } == {6}
    if sheet == "000004081":
        assert {m.model_profile_id for m in target.own_models} == {
            "000004081:chaos-terminators",
            "000004081:terminator-champion",
        }
    state, target, sequence = native_sequence(d, target=target)
    assert sequence.attack_pools[0].weapon_profile.strength_for_interaction() == 5
    # S5 wounds native T6 on5; the former T5 profile incorrectly accepted4.
    dice = fixed_sequence_dice(sequence, target, (3,), (face,), (1,))
    if face == 4:
        dice = dice[:-1]
    decisions, remaining, status = resolve(state, sequence, dice)
    if sheet == "000004081" and face == 5:
        from warhammer40k_core.engine.attack_sequence import resolve_attack_sequence_until_blocked
        from warhammer40k_core.engine.attack_sequence_group_selection import (
            apply_damage_allocation_model_decision,
        )

        assert remaining is not None
        assert status is not None
        assert status.decision_request is not None
        request = status.decision_request
        assert request.decision_type == "select_damage_allocation_model"
        assert request.actor_id == "opponent"
        assert len(request.options) == len(target.own_models)
        chosen = DecisionResult.for_request(
            result_id="current-toughness-allocation",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        decisions.submit_result(chosen)
        remaining, allocated, status = apply_damage_allocation_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            attack_sequence=remaining,
            result=chosen,
            already_allocated_model_ids=(),
        )
        if remaining is not None and status is None:
            remaining, _, status = resolve_attack_sequence_until_blocked(
                state=state,
                decisions=decisions,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                attack_sequence=remaining,
                already_allocated_model_ids=allocated,
            )
    assert remaining is None, status
    assert status is None
    steps = payloads(decisions, "attack_sequence_step")
    assert len([p for p in steps if p["step"] == "save"]) == int(face == 5)
    assert model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds == (
        target.own_models[0].current_wounds - int(face == 5)
    )


def test_current_ec_source_overlay_is_closed_and_preimage_bound() -> None:
    from tools.ability_support_sources import load_source_artifacts
    from tools.generate_ability_support_matrix import DEFAULT_SOURCE_JSON_DIR
    from tools.generate_emperors_children_current_source import generated_overlay_pack

    from warhammer40k_core.rules.source_overlay import (
        SourceOverlayError,
        apply_source_release_overlays,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        emperors_children_current_2026_11 as current,
    )

    pack = current.overlay_pack()
    assert pack == generated_overlay_pack()
    numeric = pack.operations[:4]
    assert len(pack.operations) == 6
    assert sum(len(o.fields) for o in numeric) == 6
    assert {o.source_row_id for o in numeric} == {
        "000004081:1",
        "000004081:1:1:8658",
        "000004081:2:1:8659",
        "000004083:1",
    }
    assert pack.operations[4].source_row_id == "000004077:6"
    assert pack.operations[4].operation_kind.value == "supersede_row"
    assert dict(pack.operations[5].fields)["keyword"] == "Mobile"
    sources = load_source_artifacts(DEFAULT_SOURCE_JSON_DIR)
    updated = apply_source_release_overlays(
        source_artifacts=sources,
        release_manifest=current.source_release_manifest(),
        overlay_packs=(pack,),
    )
    originals = {(a.source_table, r.source_row_id): r for a in sources for r in a.rows}
    after = {(a.source_table, r.source_row_id): r for a in updated for r in a.rows}
    touched = {(o.source_table, o.source_row_id) for o in pack.operations}
    assert set(after) - set(originals) == {
        ("Datasheets_keywords", pack.operations[5].source_row_id)
    }
    for identity, row in originals.items():
        if identity not in touched:
            assert row.to_payload() == after[identity].to_payload()
    for index in range(5):
        stale = replace(pack.operations[index], expected_preimage_hash="0" * 64)
        with pytest.raises(SourceOverlayError, match="target_drift"):
            apply_source_release_overlays(
                source_artifacts=sources,
                release_manifest=current.source_release_manifest(),
                overlay_packs=(
                    replace(
                        pack,
                        operations=(*pack.operations[:index], stale, *pack.operations[index + 1 :]),
                    ),
                ),
            )
    with pytest.raises(SourceOverlayError, match="invalid"):
        current.overlay_pack_from_json_bytes(b"not JSON")


def test_current_packaged_court_native_profiles_mobile_and_roundtrip() -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
    from warhammer40k_core.engine.unit_factory import UnitInstance
    from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        court_of_slaughter_anvanth_2026_08 as packaged,
    )

    package = packaged.catalog_package()
    assert (
        CanonicalCatalogPackage.from_payload(package.to_payload()).to_payload()
        == package.to_payload()
    )
    d = Section02Definitions(package, 0.0)
    for sheet in ("000004081", "000004083"):
        unit = d.unit(sheet)
        assert UnitInstance.from_payload(unit.to_payload()).to_payload() == unit.to_payload()
        assert {
            v.final
            for m in unit.own_models
            for v in m.characteristics
            if v.characteristic is Characteristic.TOUGHNESS
        } == {6}
    for name in ("combi-bolter", "combi-weapon"):
        weapon = d.weapon(f"000004081:{name}")
        assert (weapon.strength_for_interaction(), weapon.armor_penetration.final) == (5, -1)
    fulgrim = d.unit("000004077")
    assert "MOBILE" in fulgrim.own_models[0].keywords
    assert not any(
        a.ability_id == "000004077:serpentine"
        for a in package.army_catalog.datasheet_by_id("000004077").abilities
    )
    capability = MovementCapabilitySet.from_keywords(
        fulgrim.own_models[0].keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode="normal",
    )
    assert capability.can_traverse_ruins_walls
    assert capability.terrain_as_if_absent_height_inches is None
    assert MovementCapabilitySet.from_payload(capability.to_payload()) == capability
    # The packaged consumer now receives the already-merged October corrections too.
    lord = d.unit("000004078")
    assert {
        v.final
        for v in lord.own_models[0].characteristics
        if v.characteristic is Characteristic.TOUGHNESS
    } == {5}


@pytest.mark.parametrize("kind", ["user_supplied_estimate", "crowd_sourced_measurement"])
def test_explicit_provisional_geometry_preserves_uncertainty_and_rejects_unknowns(
    kind: str,
) -> None:
    from warhammer40k_core.core.model_geometry_catalog import (
        GeometryEvidenceKind,
        GeometryMeasurementKind,
        GeometryReviewStatus,
        GeometrySourceUnits,
        ModelGeometrySourceEvidence,
        ModelHeightDefinition,
    )

    evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="sorcerer:provisional-height",
        evidence_kind=GeometryEvidenceKind(kind),
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id="user-relayed-estimate:2026-11-01:sorcerer-foot-plastic",
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(("height", 65.0),),
        document_reference="data/source_audits/sorcerer_2026_11/geometry.json",
        reviewer_status=GeometryReviewStatus.PROVISIONAL_ESTIMATE,
    )
    height = ModelHeightDefinition.from_evidence(evidence)
    assert height.height_inches == 65 / 25.4
    payload = evidence.to_payload()
    assert payload["reviewer_status"] == "provisional_estimate"
    assert payload["evidence_kind"] == kind
    assert ModelGeometrySourceEvidence.from_payload(payload) == evidence
    assert ModelHeightDefinition.from_payload(height.to_payload()) == height
    with pytest.raises(ValueError, match="not accepted"):
        ModelHeightDefinition.from_evidence(
            replace(evidence, reviewer_status=GeometryReviewStatus.NEEDS_REVIEW)
        )
    with pytest.raises(ValueError, match="GeometryReviewStatus"):
        ModelGeometrySourceEvidence.from_payload({**payload, "reviewer_status": "unknown"})
    with pytest.raises(ValueError, match="greater than 0"):
        ModelGeometrySourceEvidence.from_payload({**payload, "source_dimensions": {"height": 0.0}})
    if kind == "user_supplied_estimate":
        with pytest.raises(ValueError, match="estimate"):
            replace(evidence, reviewer_status=GeometryReviewStatus.ACCEPTED)
    with pytest.raises(ValueError, match="official"):
        replace(evidence, evidence_kind=GeometryEvidenceKind.OFFICIAL_MODEL_PROFILE)


@pytest.mark.parametrize("bodyguard", ["000004079", "000004080", "000004088"])
def test_sorcerer_current_native_muster_geometry_equipment_and_leader_targets(
    bodyguard: str,
) -> None:
    from tests.support.sorcerer_native import SORCERER, native_request
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.datasheet import ModelProfileDefinitionPayload
    from warhammer40k_core.core.model_geometry_catalog import GeometryReviewStatus
    from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        court_of_slaughter_anvanth_2026_08 as source,
    )

    package = source.catalog_package()
    selected = native_request(player="owner", bodyguard=bodyguard)
    army = muster_army(
        catalog=package.army_catalog, request=selected, model_geometries=package.model_geometries
    )
    assert army.roster_legality_report.is_legal
    profile = package.army_catalog.datasheet_by_id(SORCERER).model_profiles[0]
    assert profile.requires_geometry_record
    assert type(profile).from_payload(profile.to_payload()) == profile
    with pytest.raises(ValueError, match="must be bool"):
        type(profile).from_payload(
            cast(
                ModelProfileDefinitionPayload,
                {
                    **profile.to_payload(),
                    "requires_geometry_record": "yes",
                },
            )
        )
    legacy_profile = package.army_catalog.datasheet_by_id(bodyguard).model_profiles[0]
    assert not legacy_profile.requires_geometry_record
    assert "requires_geometry_record" not in legacy_profile.to_payload()
    assert next(p.points for p in selected.unit_points if p.unit_selection_id == "sorcerer") == 55
    unit = next(u for u in army.units if u.datasheet_id == SORCERER)
    assert len(unit.own_models) == 1
    model = unit.own_models[0]
    assert (
        next(c.final for c in model.characteristics if c.characteristic is Characteristic.TOUGHNESS)
        == 5
    )
    assert set(model.wargear_ids) == {
        f"{SORCERER}:agonising-energies",
        f"{SORCERER}:bolt-pistol",
        f"{SORCERER}:force-weapon",
    }
    pistol = next(
        w for w in package.army_catalog.wargear if w.wargear_id == f"{SORCERER}:bolt-pistol"
    ).weapon_profiles[0]
    assert pistol.strength.final == 5
    assert pistol.armor_penetration.final == -1
    geometry = next(
        g for g in package.model_geometries if g.model_profile_id == model.model_profile_id
    )
    assert geometry.height.height_inches == 65 / 25.4
    assert (
        next(
            e for e in geometry.evidence if e.evidence_id == geometry.height.evidence_id
        ).reviewer_status
        is GeometryReviewStatus.PROVISIONAL_ESTIMATE
    )
    assert ArmyDefinition.from_payload(army.to_payload()).to_payload() == army.to_payload()


@pytest.fixture(scope="module")
def sorcerer_native_shooting_checkpoint() -> Any:
    from tests.support.sorcerer_native import (
        deploy_native,
        native_declaration,
        native_session,
        translate_native,
    )

    session = native_session()
    deploy_native(session)
    translate_native(session, "attached-unit:owner:bodyguard", 7.0)
    native_declaration(session, "attached-unit:owner:bodyguard")
    state = session.lifecycle.state
    assert state is not None
    assert all(a.roster_legality_report.is_legal for a in state.army_definitions)
    return session.to_persistence_payload()


@pytest.mark.parametrize(
    ("profile", "ignore", "target_number"),
    [
        ("witchfire", False, 4),
        ("focused-witchfire", True, 3),
    ],
)
def test_sorcerer_native_shooting_cover_wracking_and_exact_replay(
    sorcerer_native_shooting_checkpoint: Any,
    profile: str,
    ignore: bool,
    target_number: int,
) -> None:
    from tests.support.sorcerer_native import (
        assert_native_movement_budget,
        native_choice,
        native_fire,
        translate_native,
    )
    from warhammer40k_core.engine.replay import ReplayRunStatus

    session = LocalGameSession.from_persistence_payload(sorcerer_native_shooting_checkpoint)
    seen = native_fire(
        session, profile_id=f"000004085:agonising-energies:{profile}", ignore_psychic=ignore
    )
    assert "select_psychic_attack_modifier_ignores" in seen
    assert "select_catalog_post_shoot_hit_target_effect" in seen
    state = session.lifecycle.state
    assert state is not None
    hits = [p["payload"] for p in events(session, "attack_sequence_step") if p["step"] == "hit"]
    assert hits
    assert all(isinstance(hit, dict) and hit["target_number"] == target_number for hit in hits)
    assert any(isinstance(hit, dict) and hit["successful"] is True for hit in hits)
    effects = [
        e
        for e in state.persisting_effects
        if isinstance(e.effect_payload, dict)
        and e.effect_payload.get("rule_id") == "sorcerer:datasheet:000004085:4"
    ]
    assert len(effects) == 2
    assert all(e.target_unit_instance_ids == ("attached-unit:opponent:bodyguard",) for e in effects)
    assert all(
        e.expiration.battle_round == 2 and e.expiration.player_id == "owner" for e in effects
    )
    assert state.active_player_id == "opponent"
    persisted = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(persisted)
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for viewer in ("owner", "opponent"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    if profile == "witchfire":
        translate_native(session, "attached-unit:opponent:bodyguard", -5.0)
        assert_native_movement_budget(session, "attached-unit:opponent:bodyguard", 5.0)
        for _ in range(50):
            current = session.lifecycle.state
            assert current is not None
            if current.battle_round == 2 and current.active_player_id == "owner":
                break
            pending = session.lifecycle.pending_decision_request()
            assert pending is not None
            native_choice(
                session,
                option_id="attached-unit:opponent:bodyguard"
                if pending.decision_type == "select_charging_unit"
                else None,
            )
        else:
            raise AssertionError("Native next owner turn did not start")
        assert not any(
            isinstance(e.effect_payload, dict)
            and e.effect_payload.get("rule_id") == "sorcerer:datasheet:000004085:4"
            for e in state.persisting_effects
        )
        charge = events(session, "charge_roll_resolved")[-1]
        modifiers = charge["charge_roll_modifiers"]
        assert isinstance(modifiers, list)
        assert len(modifiers) == 1
        assert isinstance(modifiers[0], dict)
        assert modifiers[0]["operand"] == -2
    result = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id=f"sorcerer-native:{profile}")
    ).run()
    assert result.status is ReplayRunStatus.REPRODUCED


def test_sorcerer_bodyguard_hits_do_not_activate_its_wracking_agony(
    sorcerer_native_shooting_checkpoint: Any,
) -> None:
    from tests.support.sorcerer_native import native_fire

    session = LocalGameSession.from_persistence_payload(sorcerer_native_shooting_checkpoint)
    seen = native_fire(session, profile_id="000004079:boltgun:standard")
    assert "select_catalog_post_shoot_hit_target_effect" not in seen
    state = session.lifecycle.state
    assert state is not None
    assert not any(
        isinstance(e.effect_payload, dict)
        and e.effect_payload.get("rule_id") == "sorcerer:datasheet:000004085:4"
        for e in state.persisting_effects
    )
    assert any(
        isinstance(p["payload"], dict) and p["payload"].get("successful") is True
        for p in events(session, "attack_sequence_step")
        if p["step"] == "hit"
    )


def test_sorcerer_native_misses_do_not_offer_wracking(
    sorcerer_native_shooting_checkpoint: Any,
) -> None:
    from tests.support.sorcerer_native import native_fire

    session = LocalGameSession.from_persistence_payload(sorcerer_native_shooting_checkpoint)
    seen = native_fire(
        session,
        profile_id="000004085:agonising-energies:witchfire",
        result_id="decision-request-000019:native-fire",
    )
    assert "select_catalog_post_shoot_hit_target_effect" not in seen
    hits = [p["payload"] for p in events(session, "attack_sequence_step") if p["step"] == "hit"]
    assert hits
    assert all(isinstance(hit, dict) and hit["successful"] is False for hit in hits)


def test_sorcerer_muster_rejects_illegal_bodyguard_counts_equipment_and_missing_geometry() -> None:
    from tests.support.sorcerer_native import native_request
    from warhammer40k_core.engine.army_mustering import ArmyMusteringError, muster_army
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        court_of_slaughter_anvanth_2026_08 as source,
    )

    package = source.catalog_package()
    selected = native_request(player="owner")
    illegal = native_request(player="owner", bodyguard="000004089")
    leader = selected.unit_selections[0]
    bad_count = replace(
        leader,
        model_profile_selections=(
            ModelProfileSelection(leader.model_profile_selections[0].model_profile_id, 2),
        ),
    )
    bad_weapon = replace(
        leader,
        wargear_selections=(
            WargearSelection(
                "unadvertised",
                leader.model_profile_selections[0].model_profile_id,
                ("unadvertised",),
            ),
        ),
    )
    for invalid_request in (
        illegal,
        replace(selected, unit_selections=(bad_count, *selected.unit_selections[1:])),
        replace(selected, unit_selections=(bad_weapon, *selected.unit_selections[1:])),
    ):
        with pytest.raises(ArmyMusteringError):
            muster_army(
                catalog=package.army_catalog,
                request=invalid_request,
                model_geometries=package.model_geometries,
            )
    with pytest.raises(ArmyMusteringError):
        muster_army(
            catalog=package.army_catalog,
            request=selected,
            model_geometries=tuple(
                g
                for g in package.model_geometries
                if g.model_profile_id != leader.model_profile_selections[0].model_profile_id
            ),
        )


@pytest.mark.parametrize("case", ["never-attached", "ignores-cover"])
def test_sorcerer_native_cover_is_conditional_and_respects_ignores_cover(case: str) -> None:
    from tests.support.sorcerer_native import (
        deploy_native,
        native_declaration,
        native_fire,
        native_session,
        translate_native,
    )

    session = native_session(
        enemy_attached=case != "never-attached",
        own_bodyguard="000004088" if case == "ignores-cover" else "000004079",
    )
    deploy_native(session)
    translate_native(
        session, "attached-unit:owner:bodyguard", 6.0 if case == "ignores-cover" else 7.0
    )
    native_declaration(session, "attached-unit:owner:bodyguard")
    native_fire(
        session,
        profile_id="000004088:sonic-blaster:standard"
        if case == "ignores-cover"
        else "000004085:agonising-energies:witchfire",
        target_id="attached-unit:opponent:bodyguard"
        if case == "ignores-cover"
        else "opponent:sorcerer",
        model_id="owner:bodyguard:000004088:noise-marines:005" if case == "ignores-cover" else None,
    )
    hits = [p["payload"] for p in events(session, "attack_sequence_step") if p["step"] == "hit"]
    assert hits
    assert all(isinstance(hit, dict) and hit["target_number"] == 3 for hit in hits)
    assert all(
        isinstance(hit, dict) and hit.get("psychic_modifier_selection") is None for hit in hits
    )


def test_two_native_sorcerers_wrack_the_same_target_without_stacking_movement() -> None:
    from tests.support.sorcerer_native import (
        assert_native_movement_budget,
        deploy_native,
        native_declaration,
        native_fire,
        native_session,
        translate_native,
    )

    session = native_session(second_sorcerer=True)
    deploy_native(session)
    translate_native(session, "attached-unit:owner:bodyguard", 7.0)
    translate_native(session, "owner:second-sorcerer", 6.2)
    for identity, result in (
        ("attached-unit:owner:bodyguard", "native:energies"),
        ("owner:second-sorcerer", "native:energies-2"),
    ):
        native_declaration(session, identity)
        seen = native_fire(
            session, profile_id="000004085:agonising-energies:witchfire", result_id=result
        )
        assert "select_catalog_post_shoot_hit_target_effect" in seen
    state = session.lifecycle.state
    assert state is not None
    assert state.active_player_id == "opponent"
    effects = [
        e
        for e in state.persisting_effects
        if isinstance(e.effect_payload, dict)
        and e.effect_payload.get("rule_id") == "sorcerer:datasheet:000004085:4"
    ]
    assert len(effects) == 4
    # Two distinct real receipts retain their durations; the generic source slot
    # applies the named condition once. A cumulative -4 would reject this move.
    translate_native(session, "attached-unit:opponent:bodyguard", -5.0)
    assert_native_movement_budget(session, "attached-unit:opponent:bodyguard", 5.0)


@pytest.mark.parametrize("omit_all", [True, False])
def test_sorcerer_strict_public_setup_requires_provisional_geometry(omit_all: bool) -> None:
    from tests.support.sorcerer_native import native_session
    from warhammer40k_core.engine.phase import GameLifecycleError

    original = native_session()
    config = original.lifecycle.config
    assert config is not None
    assert config.model_geometries is not None
    geometry = (
        None
        if omit_all
        else tuple(
            record
            for record in config.model_geometries
            if record.model_profile_id != "000004085:sorcerer"
        )
    )
    altered = replace(config, model_geometries=geometry)
    assert not altered.allow_legacy_non_strict_rosters
    session = LocalGameSession()
    session.start(altered)
    with pytest.raises(GameLifecycleError, match="MUSTER_ARMIES failed"):
        session.advance_until_decision_or_terminal()
    assert session.lifecycle.state is not None
    assert not session.lifecycle.state.army_definitions


def test_sorcerer_native_agonising_hits_on_non_infantry_do_not_offer_wracking() -> None:
    from tests.support.sorcerer_native import (
        deploy_native,
        native_declaration,
        native_fire,
        native_session,
        translate_native,
    )

    session = native_session(enemy_character_only=True)
    deploy_native(session)
    translate_native(session, "attached-unit:owner:bodyguard", 7.0)
    native_declaration(session, "attached-unit:owner:bodyguard")
    seen = native_fire(
        session,
        profile_id="000004085:agonising-energies:witchfire",
        target_id="opponent:sorcerer",
    )
    assert "select_catalog_post_shoot_hit_target_effect" not in seen
    hits = [p["payload"] for p in events(session, "attack_sequence_step") if p["step"] == "hit"]
    assert any(isinstance(hit, dict) and hit["successful"] is True for hit in hits)


def test_sorcerer_native_bolt_pistol_hits_do_not_offer_wracking(
    sorcerer_native_shooting_checkpoint: Any,
) -> None:
    from tests.support.sorcerer_native import (
        native_choice,
        native_declaration,
        native_fire,
        translate_native,
    )

    session = LocalGameSession.from_persistence_payload(sorcerer_native_shooting_checkpoint)
    native_fire(session, profile_id="000004079:boltgun:standard")
    translate_native(session, "attached-unit:opponent:bodyguard", -7.0)
    for _ in range(50):
        current = session.lifecycle.state
        assert current is not None
        if current.battle_round == 2 and current.active_player_id == "owner":
            break
        native_choice(session)
    else:
        raise AssertionError("Native second owner turn not reached")
    native_declaration(session, "attached-unit:owner:bodyguard")
    before = len(events(session, "attack_sequence_step"))
    seen = native_fire(
        session, profile_id="000004085:bolt-pistol:standard", result_id="native:pistol"
    )
    assert "select_catalog_post_shoot_hit_target_effect" not in seen
    attacks = events(session, "attack_sequence_step")[before:]
    assert any(
        p["step"] == "hit" and isinstance(p["payload"], dict) and p["payload"]["successful"] is True
        for p in attacks
    )


@pytest.mark.parametrize("drift", ["unknown-role", "melee", "extra-condition"])
def test_leading_cover_rejects_unrecognized_source_descriptor_scope(drift: str) -> None:
    from warhammer40k_core.engine.catalog_cover_support import clause_is_leading_cover
    from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload, RuleParameter
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        court_of_slaughter_anvanth_2026_08 as source,
    )

    sheet = source.catalog_package().army_catalog.datasheet_by_id("000004085")
    ability = next(a for a in sheet.abilities if a.name.startswith("Warped Interference"))
    assert ability.rule_ir_payload is not None
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    clause = rule.clauses[0]
    assert clause_is_leading_cover(clause)
    if drift == "unknown-role":
        condition = replace(
            clause.conditions[0], parameters=(RuleParameter("relationship", "unknown_role"),)
        )
        invalid = replace(clause, conditions=(condition,))
    elif drift == "melee":
        effect = replace(
            clause.effects[0],
            parameters=tuple(
                RuleParameter(p.key, "melee") if p.key == "attack_kind" else p
                for p in clause.effects[0].parameters
            ),
        )
        invalid = replace(clause, effects=(effect,))
    else:
        invalid = replace(clause, conditions=(*clause.conditions, clause.conditions[0]))
    assert not clause_is_leading_cover(invalid)


def test_sorcerer_native_overwatch_hits_cannot_trigger_own_shooting_wracking(
    sorcerer_native_shooting_checkpoint: Any,
) -> None:
    from tests.support.sorcerer_native import (
        native_fire,
        native_sorcerer_overwatch,
        translate_native,
    )

    session = LocalGameSession.from_persistence_payload(sorcerer_native_shooting_checkpoint)
    native_fire(session, profile_id="000004079:boltgun:standard")
    translate_native(session, "attached-unit:opponent:bodyguard", -7.0)
    before = len(events(session, "attack_sequence_step"))
    seen = native_sorcerer_overwatch(session)
    assert "select_catalog_post_shoot_hit_target_effect" not in seen
    steps = events(session, "attack_sequence_step")[before:]
    assert any(
        p["step"] == "hit" and isinstance(p["payload"], dict) and p["payload"]["successful"] is True
        for p in steps
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.active_player_id == "opponent"
    assert state.out_of_phase_shooting_state is None
    assert not any(
        isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("rule_id") == "sorcerer:datasheet:000004085:4"
        for effect in state.persisting_effects
    )


def test_sorcerer_original_rear_blocker_scene_completes_shooting_and_exact_replay() -> None:
    from tests.support.sorcerer_native import (
        deploy_native,
        native_declaration,
        native_fire,
        native_session,
        translate_native,
    )
    from warhammer40k_core.engine.replay import ReplayRunStatus

    session = native_session(enemy_attached=False)
    deploy_native(session, original_visibility_scene=True)
    translate_native(session, "attached-unit:owner:bodyguard", 7.0)
    # Retain the original accepted 494.54-second diagnostic scene, including the
    # lone Sorcerer at (31, 4.5) and its separate bodyguards starting at (31, 1.4).
    # Declaration enumerates every real target before selecting the attack.
    native_declaration(session, "attached-unit:owner:bodyguard")
    native_fire(
        session,
        profile_id="000004085:agonising-energies:witchfire",
        target_id="opponent:sorcerer",
    )
    hits = [p["payload"] for p in events(session, "attack_sequence_step") if p["step"] == "hit"]
    assert hits
    assert all(isinstance(hit, dict) and hit["target_number"] == 3 for hit in hits)
    assert any(isinstance(hit, dict) and hit["successful"] is True for hit in hits)
    persisted = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(persisted)
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for viewer in ("owner", "opponent"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    result = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="sorcerer-original-rear-blocker-scene")
    ).run()
    assert result.status is ReplayRunStatus.REPRODUCED
