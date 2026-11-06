"""Native current-source Whispering Web scenes and finite submission helpers."""

from __future__ import annotations

from dataclasses import replace

from tests.psychic_modifier_helpers import submit_fixture_request
from tests.support.faction_batch01 import Scene, anchor, locate, request, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import shooting_payload, shooting_request, weapon_rows
from warhammer40k_core.engine.attack_sequence_model import HitRoll
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import AttachmentDeclaration, UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose

LHYKHIS = "000003909"
SPIDERS = "000000601"
AVENGERS = "000000593"
WALKERS = "000000612"
CHOICE = "select_catalog_post_shoot_hit_target_effect"


def web_scene(
    d: Section02Definitions,
    *,
    attached: bool = False,
    seed: str = "native-web",
    rng_seed_label: str | None = None,
    full_target: bool = False,
    charge_ready: bool = False,
    wounded_source: bool = False,
    attached_target: bool = False,
    other_engaged: bool = False,
) -> Scene:
    # This source-backed detachment has an implemented runtime and permits the
    # native attached scene; the separate Outcast attached-selection defect is
    # not hidden behind a replaced hook or injected decision controller.
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_detachments_2026_27 as identities,
    )

    source = next(
        row for row in identities.detachment_rows() if row.detachment_id == "corsair-coterie"
    )
    catalog = d.package.army_catalog
    base = next(row for row in catalog.detachments if row.faction_id == "aeldari")
    detachment = replace(
        base,
        canonical_detachment_id=source.detachment_id,
        detachment_id=source.detachment_id,
        name=source.name,
        detachment_point_cost=source.detachment_point_cost,
        source_ids=source.source_ids,
        force_disposition_ids=tuple(
            sorted({source.force_disposition_id, "take-and-hold", "purge-the-foe"})
        ),
    )
    d = replace(
        d,
        package=replace(
            d.package, army_catalog=replace(catalog, detachments=(*catalog.detachments, detachment))
        ),
    )
    own: tuple[UnitMusterSelection, ...] = (
        selection(d, LHYKHIS, "lhykhis"),
        selection(d, AVENGERS, "avengers"),
    )
    if attached:
        own += (selection(d, SPIDERS, "spiders"),)
    if other_engaged:
        own += (selection(d, WALKERS, "reserve-shot"),)
    s = scene(
        d,
        own,
        (
            (
                selection(d, SPIDERS, "target-body"),
                selection(d, LHYKHIS, "target-leader"),
                selection(d, WALKERS, "other"),
            )
            if attached_target
            else (
                selection(d, WALKERS, "walkers", full=full_target),
                selection(d, WALKERS, "other"),
            )
        ),
        detachment_id_by_faction={"aeldari": "corsair-coterie"},
        phase=BattlePhase.SHOOTING,
        seed=seed,
        rng_seed_label=rng_seed_label,
        attachments=(AttachmentDeclaration("lhykhis", "spiders"),) if attached else (),
        enemy_attachments=(AttachmentDeclaration("target-leader", "target-body"),)
        if attached_target
        else (),
    )
    locate(s, "own:lhykhis", (Pose.at(14 if charge_ready else 10, 10),))
    locate(
        s,
        "own:avengers",
        tuple(
            Pose.at(16.5, 19.4 + i * 1.3) if other_engaged else Pose.at(25, 7 + i * 2)
            for i in range(len(s.units["own:avengers"].own_models))
        ),
    )
    if attached_target:
        locate(
            s,
            "foe:target-body",
            tuple(
                Pose.at(19, 10 + i * 1.5) for i in range(len(s.units["foe:target-body"].own_models))
            ),
        )
        locate(s, "foe:target-leader", (Pose.at(19, 18),))
    else:
        locate(
            s,
            "foe:walkers",
            tuple(
                Pose.at(19, 10 + i * 2.4) if wounded_source else Pose.at(19, 10 + i * 3)
                for i in range(len(s.units["foe:walkers"].own_models))
            ),
        )
    locate(
        s,
        "foe:other",
        (Pose.at(30, 25) if attached_target else Pose.at(19, 22 if other_engaged else 18),),
    )
    if attached:
        locate(
            s,
            "own:spiders",
            tuple(Pose.at(10, 12 + i * 2) for i in range(len(s.units["own:spiders"].own_models))),
        )
    if other_engaged:
        locate(s, "own:reserve-shot", (Pose.at(5, 10),))
    _verify_scene_geometry(s, other_engaged=other_engaged)
    if wounded_source:
        from tests.order130_helpers import session_from_casualty_checkpoint

        _record_wounded_source(s)
        anchor(s)
        s.session = session_from_casualty_checkpoint(s.session.lifecycle)
    else:
        anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    return s


def declare_web(
    s: Scene,
    *,
    attached: bool = False,
    bodyguards_only: bool = False,
    no_attacks: bool = False,
    target_id: str = "foe:walkers",
) -> None:
    r = shooting_request(s.session, "attached-unit:own:spiders" if attached else "own:lhykhis")
    rows = weapon_rows(r)
    source_ids = set(s.units["own:lhykhis"].own_model_ids())
    if bodyguards_only:
        rows = [row for row in rows if row["model_instance_id"] not in source_ids]
    targets = [
        None if no_attacks else target_id if row["model_instance_id"] in source_ids else "foe:other"
        for row in rows
    ]
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=shooting_payload(r, rows, targets),
        result_id="web-declaration",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()


def choose(s: Scene, r: DecisionRequest, option_id: str) -> None:
    status = s.session.submit_option(
        request_id=r.request_id, option_id=option_id, result_id=f"{r.request_id}:web-choice"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()


def drive_to(s: Scene, kinds: set[str], *, source_first: bool = True) -> DecisionRequest:
    for _ in range(250):
        r = request(s.session.advance_until_decision_or_terminal())
        if r.decision_type in kinds:
            return r
        if r.decision_type == "select_resolve_target_unit":
            preferred = "foe:walkers" if source_first else "foe:other"
            option = next(
                (
                    o
                    for o in r.options
                    if isinstance(o.payload, dict)
                    and o.payload.get("target_unit_instance_id") == preferred
                ),
                r.options[0],
            )
            choose(s, r, option.option_id)
        elif r.decision_type == "select_attack_weapon_group":
            model_id = s.units["own:lhykhis"].own_model_ids()[0]
            matching: list[DecisionOption] = []
            for option in r.options:
                assert isinstance(option.payload, dict)
                group = option.payload["gathered_group"]
                assert isinstance(group, dict)
                snapshots = group.get("native_snapshots", [])
                assert isinstance(snapshots, list)
                source = any(
                    isinstance(row, dict) and row.get("attacker_model_instance_id") == model_id
                    for row in snapshots
                )
                if source is source_first:
                    matching.append(option)
            choose(s, r, (matching or list(r.options))[0].option_id)
        else:
            submit_fixture_request(s.session, r)
    raise AssertionError("Native web scene did not reach requested decision boundary")


def activate_web(s: Scene) -> None:
    declare_web(s)
    r = drive_to(s, {CHOICE, "select_shooting_unit"})
    assert r.decision_type == CHOICE
    choose(s, r, r.options[0].option_id)
    drive_to(s, {"select_shooting_unit"})


def hit_with_face(
    s: Scene,
    *,
    attacker_id: str = "own:avengers",
    target_id: str = "foe:walkers",
    face: int = 5,
    melee: bool = False,
    modifier: int = 0,
    model_id: str | None = None,
) -> HitRoll:
    from tests.support.section02_consumers import attack_pool
    from warhammer40k_core.core.modifiers import RollModifier
    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.engine.attack_sequence import (
        AttackSequence,
        attack_sequence_hit_roll_spec,
    )
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.native_attack_gathering import (
        _current_applicable_rules,  # pyright: ignore[reportPrivateUsage]
    )

    unit = next(
        u for a in s.state.army_definitions for u in a.units if u.unit_instance_id == attacker_id
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target_view = rules_unit_view_by_id(state=s.state, unit_instance_id=target_id)
    target = next(
        c.unit for c in target_view.components if any(m.is_alive for m in c.unit.own_models)
    )
    catalog = s.session.lifecycle.config.army_catalog
    assert catalog is not None
    kind = RangeProfileKind.MELEE if melee else RangeProfileKind.DISTANCE
    model = next(
        m
        for m in unit.own_models
        if m.is_alive and (model_id is None or m.model_instance_id == model_id)
    )
    gear, profile = next(
        (w, p)
        for w in catalog.wargear
        if w.wargear_id in model.wargear_ids
        for p in w.weapon_profiles
        if p.range_profile.kind is kind
    )
    pool = replace(
        attack_pool(unit, target, profile, gear.wargear_id),
        target_unit_instance_id=target_id,
        attacker_model_instance_id=model.model_instance_id,
        hit_roll_modifier=modifier,
        hit_roll_modifiers=(
            RollModifier(
                "constructed:web-hit-modifier", modifier, source_id="constructed:hit-owner"
            ),
        )
        if modifier
        else (),
    )
    phase = BattlePhase.FIGHT if melee else BattlePhase.SHOOTING
    owner = next(a.player_id for a in s.state.army_definitions if unit in a.units)
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id, attack_context_id="web-face", attacker_player_id=owner
    )
    physical = DiceRollManager("physical").roll_fixed(spec, (face,)).original_result
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    hit = _roll_hit(
        state=s.state,
        manager=DiceRollManager("native-web-face", injected_results=(physical,)),
        pool=pool,
        attacker_player_id=owner,
        attack_context_id="web-face",
        source_phase=phase,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    comparison, _ = _current_applicable_rules(
        state=s.state,
        registry=bundle.runtime_modifier_registry,
        sequence=AttackSequence("web-face", owner, attacker_id, (pool,), source_phase=phase),
        pool=pool,
        target_has_character=False,
    )
    gathered = comparison["hit_thresholds"]
    assert isinstance(gathered, dict)
    if not hit.skipped:
        assert gathered["critical_threshold"] == hit.critical_threshold
        assert gathered["source_ids"] == list(hit.threshold_source_ids)
    return hit


def legal_shooting_payload(r: DecisionRequest, target_id: str) -> dict[str, JsonValue]:
    """Choose one actually offered source for every native weapon-ability family."""
    from typing import cast

    rows = weapon_rows(r)
    payload = shooting_payload(r, rows, tuple(target_id for _ in rows))
    assert isinstance(payload, dict)
    assert isinstance(r.payload, dict)
    proposal = cast(dict[str, JsonValue], r.payload["proposal_request"])
    candidates = cast(list[dict[str, JsonValue]], proposal["target_candidates"])
    for declaration in cast(list[dict[str, JsonValue]], payload["declarations"]):
        candidate = next(
            c
            for c in candidates
            if c["target_unit_instance_id"] == target_id
            and c["weapon_instance_id"] == declaration["weapon_instance_id"]
            and c["weapon_profile_id"] == declaration["weapon_profile_id"]
        )
        declaration["selected_weapon_ability_ids"] = [
            cast(list[dict[str, JsonValue]], choice["options"])[0]["option_id"]
            for choice in cast(
                list[dict[str, JsonValue]], candidate["required_weapon_ability_selections"]
            )
        ]
    return payload


def _record_wounded_source(s: Scene) -> None:
    """Engine-generated nonlethal prior damage; subsequent death is a native Fight attack."""
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        continue_mortal_wound_application,
    )
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )

    model = s.units["own:lhykhis"].own_models[0]
    routed = continue_mortal_wound_application(
        state=s.state,
        decisions=s.session.lifecycle.decision_controller,
        request_id="web-prior-wound",
        progress=MortalWoundApplicationProgress.start(
            application_id="web-prior-wound",
            source_rule_id="constructed:prior-wounded-checkpoint",
            source_context={"source_kind": "fixture", "model_instance_id": model.model_instance_id},
            target_unit_instance_id="own:lhykhis",
            defender_player_id="owner",
            mortal_wounds=model.current_wounds - 1,
            spill_over=False,
            priority_model_ids=(model.model_instance_id,),
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=s.state,
                destroying_player_id="opponent",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=BattlePhase.SHOOTING,
                source_step="fixture",
            ),
        ),
    )
    assert routed.request is None
    assert routed.application is not None
    assert not any(a.destroyed for a in routed.application.applications)


def submit_melee_toward(s: Scene, r: DecisionRequest, target_id: str) -> None:
    """Submit each native weapon against the requested target only when actually offered."""
    from typing import cast

    from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest

    melee = MeleeDeclarationProposalRequest.from_decision_request(r)
    declarations: list[JsonValue] = []
    primary: set[str] = set()
    selected: set[str] = set()
    for raw in melee.available_weapons:
        row = cast(dict[str, JsonValue], raw)
        model_id = cast(str, row["model_instance_id"])
        weapon_id = cast(str, row["weapon_instance_id"])
        targets = cast(list[str], row["engaged_target_unit_instance_ids"])
        if target_id not in targets or weapon_id in selected:
            continue
        if row["is_extra_attacks"] is not True:
            if model_id in primary:
                continue
            primary.add(model_id)
        selected.add(weapon_id)
        declarations.append(
            {
                "attacker_model_instance_id": model_id,
                "weapon_instance_id": weapon_id,
                "wargear_id": row["wargear_id"],
                "weapon_profile_id": row["weapon_profile_id"],
                "target_allocations": [{"target_unit_instance_id": target_id}],
            }
        )
    assert declarations, (target_id, melee.available_weapons)
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        result_id=f"{r.request_id}:fixture-choice",
        payload={
            "proposal_request_id": melee.request_id,
            "proposal_kind": melee.proposal_kind,
            "player_id": melee.actor_id,
            "battle_round": melee.battle_round,
            "unit_instance_id": melee.unit_instance_id,
            "source_decision_request_id": melee.source_decision_request_id,
            "source_decision_result_id": melee.source_decision_result_id,
            "declarations": declarations,
        },
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()


def _verify_scene_geometry(s: Scene, *, other_engaged: bool) -> None:
    from itertools import combinations

    from warhammer40k_core.engine.battlefield_state import geometry_model_at_pose
    from warhammer40k_core.geometry.physical_model import models_overlap_physically

    battlefield = s.state.battlefield_state
    assert battlefield is not None
    models = {
        model.model_instance_id: geometry_model_at_pose(
            model=model, pose=battlefield.model_placement_by_id(model.model_instance_id).pose
        )
        for army in s.state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if battlefield.model_placement_or_none(model.model_instance_id) is not None
    }
    for first, second in combinations(models.values(), 2):
        assert not models_overlap_physically(first, second), (first, second)
    from warhammer40k_core.engine.physical_engagement import (
        current_physically_engaged_enemy_rules_unit_ids,
    )

    assert not current_physically_engaged_enemy_rules_unit_ids(
        state=s.state, unit_instance_id="own:lhykhis"
    )
    if other_engaged:
        assert "foe:other" in current_physically_engaged_enemy_rules_unit_ids(
            state=s.state, unit_instance_id="own:avengers"
        )


def assert_native_source_loss(native_definitions: Section02Definitions, *, seed: str) -> None:
    from tests.factions.aeldari.current_source_helpers import charge
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.support.faction_batch01 import events
    from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
    from warhammer40k_core.engine.replay import ReplayRunner

    s = web_scene(
        native_definitions,
        full_target=True,
        charge_ready=True,
        wounded_source=True,
        other_engaged=True,
        seed=seed,
    )
    activate_web(s)
    r = request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    choose(s, r, "complete_shooting_phase")
    drive_to(s, {"select_charging_unit"})
    charge(s, "own:lhykhis", "foe:walkers", 19 - (60 + 40) / 50.8 - 14)
    r = drive_to(s, {"select_charging_unit", "select_fight_activation"})
    if r.decision_type == "select_charging_unit":
        choose(s, r, "complete_charge_phase")
    source_id = s.units["own:lhykhis"].own_model_ids()[0]
    for _ in range(180):
        dead = [
            e for e in events(s.session, "model_destroyed") if e["model_instance_id"] == source_id
        ]
        if dead:
            break
        assert s.state.active_player_id == "owner", (
            events(s.session, "attack_sequence_completed"),
            events(s.session, "attack_damage_applied"),
            [
                (
                    u.unit_instance_id,
                    [(m.model_instance_id, m.current_wounds) for m in u.own_models],
                )
                for a in s.state.army_definitions
                for u in a.units
            ],
        )
        r = request(s.session.advance_until_decision_or_terminal())
        if r.decision_type == "select_fight_activation" and r.actor_id == "opponent":
            option = next((o for o in r.options if "foe:walkers" in o.option_id), r.options[0])
            choose(s, r, option.option_id)
        elif (
            r.decision_type == "submit_melee_declaration"
            and r.actor_id == "opponent"
            and MeleeDeclarationProposalRequest.from_decision_request(r).unit_instance_id
            == "foe:walkers"
        ):
            submit_melee_toward(s, r, "own:lhykhis")
        else:
            submit_fixture_request(s.session, r)
    else:
        raise AssertionError("Native source destruction not reached")
    assert dead[0]["attacking_unit_instance_id"] == "foe:walkers"
    assert (
        next(
            m
            for a in s.state.army_definitions
            for u in a.units
            for m in u.own_models
            if m.model_instance_id == source_id
        ).current_wounds
        == 0
    )
    assert s.state.current_battle_phase is BattlePhase.FIGHT
    assert hit_with_face(s, face=5).critical
    restored = restored_scene(s)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    assert hit_with_face(restored, face=5).critical
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-source-destroyed"))
        .run()
        .reproduced_exactly
    )
