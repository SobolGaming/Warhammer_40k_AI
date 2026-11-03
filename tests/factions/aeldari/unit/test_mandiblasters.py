"""Mandiblasters: charge-gated melee critical hits from the current native source."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.factions.aeldari.current_source_helpers import definitions
from tests.factions.aeldari.mandiblasters_helpers import (
    SCORPIONS,
    WALKERS,
    finish_first_attack,
    hit_context,
    hit_payloads,
    indexes,
    restored_scene,
    scorpion_scene,
)
from tests.support.faction_batch01 import events
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.replay import ReplayRunner


@pytest.fixture(scope="module")
def native_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    return definitions(
        selected_army_source_index,
        datasheet_ids=(SCORPIONS, WALKERS, "000000577", "000003909", "000000594"),
    )


@pytest.mark.parametrize("charged", [True, False])
def test_native_charge_fight_natural_faces_and_exact_replay(
    native_definitions: Section02Definitions,
    charged: bool,
) -> None:
    s = scorpion_scene(native_definitions, charged=charged)
    finish_first_attack(s)
    hits = hit_payloads(s)
    assert hits
    # Execution, including Sustained Hits and ordinary wound/save/damage continuation.
    fives = [e for e in hits if e["unmodified_roll"] == 5]
    assert fives
    for hit in fives:
        assert hit["critical"] is charged
        assert hit["critical_threshold"] == (5 if charged else 6)
        assert hit["generated_hits"] == (2 if charged else 1)
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="mandiblasters-native"))
        .run()
        .reproduced_exactly
    )


def test_all_fifteen_native_profiles_share_attached_charge_gate(
    native_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds

    s = scorpion_scene(native_definitions, attached=True)
    counts = {True: 0, False: 0}
    for sheet, unit_id in ((SCORPIONS, "own:scorpions"), ("000000577", "own:autarch")):
        for wargear in native_definitions.package.army_catalog.wargear:
            if not wargear.wargear_id.startswith(sheet + ":"):
                continue
            for profile in wargear.weapon_profiles:
                melee = profile.range_profile.kind is RangeProfileKind.MELEE
                counts[melee] += 1
                for model_id in (
                    m.model_instance_id
                    for a in s.state.army_definitions
                    for u in a.units
                    if u.unit_instance_id == unit_id
                    for m in u.own_models
                    if m.is_alive
                ):
                    thresholds = resolve_hit_thresholds(
                        hit_context(s, profile, model_id),
                        ability_indexes=indexes(s),
                    )
                    assert thresholds.critical_threshold == (5 if melee else 6)
                    assert len(
                        [source for source in thresholds.source_ids if ":000000595:5:" in source]
                    ) == int(melee)
    assert counts == {True: 7, False: 8}


@pytest.mark.parametrize("checkpoint", ["after-charge", "during-critical-hit"])
def test_valid_native_persistence_resumes_exactly(
    native_definitions: Section02Definitions,
    checkpoint: str,
) -> None:
    from tests.psychic_modifier_helpers import submit_fixture_request

    s = scorpion_scene(native_definitions)
    if checkpoint == "during-critical-hit":
        for _ in range(100):
            if any(hit["unmodified_roll"] == 5 and hit["critical"] for hit in hit_payloads(s)):
                break
            status = s.session.advance_until_decision_or_terminal()
            assert status.decision_request is not None
            submit_fixture_request(s.session, status.decision_request)
        else:
            raise AssertionError("No critical-five checkpoint reached")
    restored = restored_scene(s)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    finish_first_attack(s)
    finish_first_attack(restored)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(restored.session.replay_artifact(artifact_id="restored"))
        .run()
        .reproduced_exactly
    )


def test_passive_threshold_requires_loaded_active_record(
    native_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds

    s = scorpion_scene(native_definitions)
    profile = native_definitions.weapon(SCORPIONS + ":scorpion-chainsword")
    context = hit_context(s, profile, s.units["own:scorpions"].own_model_ids()[0])
    assert resolve_hit_thresholds(context).critical_threshold == 6
    disabled = tuple(
        (
            owner,
            AbilityCatalogIndex.from_records(
                tuple(
                    replace(record, disabled=True)
                    if record.definition.ability_id == SCORPIONS + ":mandiblasters"
                    else record
                    for record in index.all_records()
                )
            ),
        )
        for owner, index in indexes(s)
    )
    assert resolve_hit_thresholds(context, ability_indexes=disabled).critical_threshold == 6
    assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 5


def test_native_compiler_preserves_every_gate_and_rejects_partial_passive_shapes(
    native_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace
    from typing import cast

    from warhammer40k_core.engine.catalog_contextual_status_consumption import (
        consumer_ids_for_clause,
    )
    from warhammer40k_core.engine.catalog_self_hit_thresholds import charged_melee_self_threshold
    from warhammer40k_core.rules.rule_ir import (
        RuleIR,
        RuleIRPayload,
        parameter_payload,
        parameters_from_pairs,
    )

    ability = next(
        a
        for a in native_definitions.package.army_catalog.datasheet_by_id(SCORPIONS).abilities
        if a.ability_id == SCORPIONS + ":mandiblasters"
    )
    assert ability.rule_ir_payload is not None
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    clause = rule.clauses[0]
    assert charged_melee_self_threshold(clause) == 5
    parameters = parameter_payload(clause.effects[0].parameters)
    assert parameters["requires_charge_move_this_turn"] is True
    assert parameters["weapon_scope"] == "melee"
    for key in parameters:
        bad = replace(
            clause,
            effects=(
                replace(
                    clause.effects[0],
                    parameters=parameters_from_pairs(
                        tuple((k, v) for k, v in parameters.items() if k != key)
                    ),
                ),
            ),
        )
        assert charged_melee_self_threshold(bad) is None
        assert "catalog-ir:critical-hit-threshold" not in consumer_ids_for_clause(bad)
        from warhammer40k_core.engine.ability_coverage import (
            AbilityOverallSupport,
            ability_support_rollup_for_rule_ir,
        )

        assert (
            ability_support_rollup_for_rule_ir(
                source_ability_id=ability.source_id,
                ability_name=ability.name,
                rule_ir=replace(rule, clauses=(bad,)),
            ).overall_ability_support
            is not AbilityOverallSupport.FULL
        )
    lhykhis = native_definitions.package.army_catalog.datasheet_by_id("000003909")
    whispering = next(a for a in lhykhis.abilities if a.ability_id == "000003909:whispering-web")
    assert whispering.rule_ir_payload is not None
    assert all(
        charged_melee_self_threshold(c) is None
        for c in RuleIR.from_payload(cast(RuleIRPayload, whispering.rule_ir_payload)).clauses
    )


def test_native_pistol_shooting_is_not_critical_five_and_replays(
    native_definitions: Section02Definitions,
) -> None:
    from tests.support.faction_batch01 import anchor, locate, request, scene, selection
    from tests.support.section04_fixtures import (
        finish_attacks,
        shooting_payload,
        shooting_request,
        weapon_rows,
    )
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.geometry.pose import Pose

    s = scene(
        native_definitions,
        (selection(native_definitions, SCORPIONS, "scorpions"),),
        (selection(native_definitions, WALKERS, "walkers"),),
        phase=BattlePhase.SHOOTING,
        seed="independent-mandiblasters-probe",
    )
    locate(s, "foe:walkers", (Pose.at(19, 10),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    r = shooting_request(s.session, "own:scorpions")
    rows = [row for row in weapon_rows(r) if row["wargear_id"] == SCORPIONS + ":shuriken-pistol"]
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=shooting_payload(r, rows, ("foe:walkers",) * len(rows)),
        result_id="native-pistol",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    finish_attacks(s.session)
    hits = hit_payloads(s)
    assert any(h["unmodified_roll"] == 5 for h in hits)
    assert all(
        h["critical_threshold"] == 6 and h["critical"] is (h["unmodified_roll"] == 6) for h in hits
    )
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="native-pistol"))
        .run()
        .reproduced_exactly
    )


def test_rejected_move_and_unaccepted_charge_never_grant_threshold(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.current_source_helpers import charge
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds

    s = scorpion_scene(native_definitions, perform_charge=False)
    context = hit_context(
        s,
        native_definitions.weapon(SCORPIONS + ":scorpion-chainsword"),
        s.units["own:scorpions"].own_model_ids()[0],
    )
    assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 6
    with pytest.raises(AssertionError, match="charge_preferred_distance_not_reached"):
        charge(s, "own:scorpions", "foe:walkers", 2.0)
    assert not events(s.session, "charge_move_completed")
    assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 6


def test_charge_expires_at_next_player_turn(
    native_definitions: Section02Definitions,
) -> None:
    from tests.psychic_modifier_helpers import submit_fixture_request
    from warhammer40k_core.engine.fights_first import FightsFirstRegistry
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds

    s = scorpion_scene(native_definitions)
    for _ in range(200):
        status = s.session.advance_until_decision_or_terminal()
        if s.state.active_player_id != "owner":
            break
        assert status.decision_request is not None
        submit_fixture_request(s.session, status.decision_request)
    else:
        raise AssertionError("Next turn not reached")
    assert not FightsFirstRegistry.from_state(s.state).charged_unit_ids()
    assert s.state.battle_round == 1
    live = next(
        m
        for a in s.state.army_definitions
        for u in a.units
        if u.unit_instance_id == "own:scorpions"
        for m in u.own_models
        if m.is_alive
    )
    context = hit_context(
        s, native_definitions.weapon(SCORPIONS + ":scorpion-chainsword"), live.model_instance_id
    )
    assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 6


@pytest.mark.parametrize("lost", ["leader", "bodyguard"])
def test_attached_source_lifetime_tracks_engine_casualties(
    native_definitions: Section02Definitions,
    lost: str,
) -> None:
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    s = scorpion_scene(native_definitions, attached=True)
    body = s.units["own:scorpions"]
    leader = s.units["own:autarch"]
    profile = native_definitions.weapon(
        "000000577:star-glaive" if lost == "bodyguard" else SCORPIONS + ":scorpion-chainsword"
    )
    recipient = leader.own_model_ids()[0] if lost == "bodyguard" else body.own_model_ids()[0]
    context = hit_context(s, profile, recipient)

    def destroy(ids: tuple[str, ...]) -> None:
        from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model

        # Isolated lifetime kernel: engine-owned non-attack damage, no queued
        # allocation, artificial buff, source flag, or historical edit.
        for model_id in ids:
            current = next(
                m
                for a in s.state.army_definitions
                for u in a.units
                for m in u.own_models
                if m.model_instance_id == model_id
            )
            if current.is_alive:
                apply_damage_to_model(
                    state=s.state,
                    target_unit_instance_id=s.state.unit_instance_id_for_model(model_id),
                    model_instance_id=model_id,
                    damage=current.current_wounds,
                    damage_kind=DamageKind.NORMAL,
                )

    if lost == "leader":
        destroy(leader.own_model_ids())
        assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 5
    else:
        destroy(body.own_model_ids()[1:])
        assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 5
        destroy(body.own_model_ids()[:1])
        assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 6
    assert rules_unit_view_by_id(
        state=s.state, unit_instance_id=leader.unit_instance_id
    ).is_attached_rules_unit


@pytest.mark.parametrize(
    ("sheet", "gear", "sustained"),
    [
        (SCORPIONS, "scorpion-chainsword", True),
        (SCORPIONS, "biting-blade", True),
        (SCORPIONS, "chainsabres", True),
        (SCORPIONS, "scorpions-claw", False),
        ("000000577", "star-glaive", False),
        ("000000577", "banshee-blade", False),
        ("000000577", "scorpion-chainsword", True),
    ],
)
def test_legally_equipped_native_melee_profiles_use_shared_hit_owner(
    native_definitions: Section02Definitions,
    sheet: str,
    gear: str,
    sustained: bool,
) -> None:
    from dataclasses import replace

    from tests.support.section02_consumers import attack_pool
    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.phase import BattlePhase

    s = scorpion_scene(
        native_definitions,
        attached=True,
        scorpion_equipment=(gear,) if sheet == SCORPIONS and gear != "scorpion-chainsword" else (),
        leader_equipment=(gear,) if sheet != SCORPIONS and gear != "star-glaive" else (),
    )
    wargear_id = sheet + ":" + gear
    profile = next(
        p
        for w in native_definitions.package.army_catalog.wargear
        if w.wargear_id == wargear_id
        for p in w.weapon_profiles
        if p.range_profile.kind is RangeProfileKind.MELEE
    )
    unit = s.units["own:scorpions" if sheet == SCORPIONS else "own:autarch"]
    model = next(m for m in unit.own_models if wargear_id in m.wargear_ids)
    pool = replace(
        attack_pool(unit, s.units["foe:walkers"], profile, wargear_id),
        attacker_model_instance_id=model.model_instance_id,
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id,
        attack_context_id="native-profile",
        attacker_player_id="owner",
    )
    physical = DiceRollManager("physical").roll_fixed(spec, (5,)).original_result
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    hit = _roll_hit(
        state=s.state,
        manager=DiceRollManager("native-profile", injected_results=(physical,)),
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="native-profile",
        source_phase=BattlePhase.FIGHT,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    assert hit.unmodified_roll == 5
    assert hit.critical
    assert hit.successful
    assert hit.critical_threshold == 5
    assert hit.generated_hits == (2 if sustained else 1)

    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.native_attack_gathering import (
        _current_applicable_rules,  # pyright: ignore[reportPrivateUsage]
    )

    sequence = AttackSequence(
        "native-parity",
        "owner",
        "attached-unit:own:scorpions",
        (pool,),
        source_phase=BattlePhase.FIGHT,
    )
    comparison, _ = _current_applicable_rules(
        state=s.state,
        registry=bundle.runtime_modifier_registry,
        sequence=sequence,
        pool=pool,
        target_has_character=False,
    )
    gathered = comparison["hit_thresholds"]
    assert isinstance(gathered, dict)
    assert gathered["critical_threshold"] == hit.critical_threshold
    assert gathered["critical_is_threshold"] is hit.critical_is_threshold
    assert gathered["source_ids"] == list(hit.threshold_source_ids)


def test_critical_five_uses_unmodified_faces_and_snap_prohibition(
    native_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.support.section02_consumers import attack_pool
    from warhammer40k_core.core.modifiers import RollModifier
    from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.weapon_abilities import SNAP_SHOOTING_RULE_ID

    s = scorpion_scene(native_definitions)
    profile = native_definitions.weapon(SCORPIONS + ":scorpion-chainsword")
    native = attack_pool(
        s.units["own:scorpions"],
        s.units["foe:walkers"],
        profile,
        SCORPIONS + ":scorpion-chainsword",
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    for raw, modifier, snap in (
        (5, -1, False),
        (4, 1, False),
        (1, 1, False),
        (6, -1, False),
        (5, 0, True),
        (6, 0, True),
    ):
        pool = replace(
            native,
            hit_roll_modifier=modifier,
            hit_roll_modifiers=(
                RollModifier(
                    "constructed:core-hit-modifier", modifier, source_id="constructed:hit-owner"
                ),
            )
            if modifier
            else (),
            targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,) if snap else (),
        )
        spec = attack_sequence_hit_roll_spec(
            weapon_profile_id=profile.profile_id,
            attack_context_id="face-boundary",
            attacker_player_id="owner",
            reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,) if snap else (),
        )
        physical = DiceRollManager("physical").roll_fixed(spec, (raw,)).original_result
        hit = _roll_hit(
            state=s.state,
            manager=DiceRollManager("face", injected_results=(physical,)),
            pool=pool,
            attacker_player_id="owner",
            attack_context_id="face-boundary",
            source_phase=BattlePhase.FIGHT,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
        )
        assert hit.critical is (not snap and raw >= 5)
        assert hit.unmodified_roll == raw
        assert hit.final_roll == max(1, raw + modifier)
        if raw == 1 or (snap and raw == 5):
            assert not hit.successful

    from warhammer40k_core.core.dice import (
        DiceExpression,
        DiceRollSpec,
        RerollComponentSelectionPolicy,
        RerollPermission,
    )
    from warhammer40k_core.engine.decision_result import DecisionResult

    # Isolated live-hit kernel: the real dice owner resolves a permitted whole
    # roll reroll; neither the hit classification nor dice history is fabricated.
    for before, after in ((4, 5), (5, 4)):
        spec = attack_sequence_hit_roll_spec(
            weapon_profile_id=profile.profile_id,
            attack_context_id="reroll-face",
            attacker_player_id="owner",
        )
        replacement_spec = DiceRollSpec(
            DiceExpression(1, 6),
            f"Reroll selected dice for {spec.reason}",
            f"{spec.roll_type}.reroll",
            actor_id="owner",
        )
        physical_rerolls = DiceRollManager("physical-reroll")
        physical_rerolls.roll_fixed(spec, (before,))
        replacement = physical_rerolls.roll_fixed(replacement_spec, (after,)).original_result
        manager = DiceRollManager("reroll-face", injected_results=(replacement,))
        original = manager.roll_fixed(spec, (before,))
        permission = RerollPermission(
            source_id="core:01.05.02",
            timing_window="after_roll_before_modifiers",
            owning_player_id="owner",
            eligible_roll_type=spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
        request = manager.request_reroll(original, permission=permission)
        manager.resolve_reroll(
            original,
            request=request,
            result=DecisionResult.for_request(
                result_id="reroll-choice", request=request, selected_option_id="reroll:0"
            ),
        )
        hit = _roll_hit(
            state=s.state,
            manager=manager,
            pool=native,
            attacker_player_id="owner",
            attack_context_id="reroll-face",
            source_phase=BattlePhase.FIGHT,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
        )
        assert hit.unmodified_roll == after
        assert hit.critical is (after == 5)


def test_last_bodyguard_destroyed_by_real_attack_retains_only_source_semantics(
    native_definitions: Section02Definitions,
) -> None:
    from tests.psychic_modifier_helpers import submit_fixture_request
    from warhammer40k_core.engine.ability_presence import ability_presence
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    s = scorpion_scene(native_definitions, attached=True, one_bodyguard=True)
    source_model_id = s.units["own:scorpions"].own_model_ids()[2]
    leader_model_id = s.units["own:autarch"].own_model_ids()[0]
    context = hit_context(s, native_definitions.weapon("000000577:star-glaive"), leader_model_id)
    assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 5
    for _ in range(250):
        if events(s.session, "attack_ability_sources_expired"):
            break
        status = s.session.advance_until_decision_or_terminal()
        assert status.decision_request is not None
        submit_fixture_request(s.session, status.decision_request)
    else:
        raise AssertionError("Native destroying attack was not completed")
    records = s.session.lifecycle.decision_controller.event_log.records
    retained_index = next(
        i for i, event in enumerate(records) if event.event_type == "attack_ability_source_retained"
    )
    expired_index = next(
        i for i, event in enumerate(records) if event.event_type == "attack_ability_sources_expired"
    )
    assert retained_index < expired_index
    assert any(
        event.event_type == "attack_sequence_step"
        for event in records[retained_index + 1 : expired_index]
    )
    from warhammer40k_core.engine.fights_first import (
        CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        FightsFirstRegistry,
    )

    assert FightsFirstRegistry.from_state(s.state).has_unit_lineage(
        state=s.state, unit_instance_id="own:autarch", effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND
    )
    assert source_model_id in str(records[retained_index].payload)
    # Homogeneous attacks resolve this window atomically. Check its native
    # retained/expiry events; do not manufacture a paused source or activation.
    view = rules_unit_view_by_id(state=s.state, unit_instance_id="own:autarch")
    assert any(m.model_instance_id == leader_model_id for m in view.alive_models())
    assert view.is_attached_rules_unit
    assert source_model_id not in ability_presence(state=s.state, rules_unit=view).active_model_ids
    assert source_model_id not in view.retained_model_ids
    assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 6
    restored = restored_scene(s)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(
            s.session.replay_artifact(artifact_id="native-bodyguard-retention")
        )
        .run()
        .reproduced_exactly
    )


def test_lhykhis_selected_target_source_is_excluded_from_passive_query(
    native_definitions: Section02Definitions,
) -> None:
    from typing import cast

    from tests.support.faction_batch01 import scene, selection
    from warhammer40k_core.engine.catalog_rule_selected_target_classification import (
        clause_is_post_shoot_hit_target_selection,
    )
    from warhammer40k_core.engine.catalog_self_hit_thresholds import catalog_self_hit_thresholds
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload

    s = scene(
        native_definitions,
        (
            selection(native_definitions, "000003909", "lhykhis"),
            selection(native_definitions, SCORPIONS, "scorpions"),
        ),
        (selection(native_definitions, WALKERS, "walkers"),),
        phase=BattlePhase.FIGHT,
        seed="mandiblasters-lhykhis-passive-exclusion",
    )
    context = hit_context(
        s,
        native_definitions.weapon(SCORPIONS + ":scorpion-chainsword"),
        s.units["own:scorpions"].own_model_ids()[0],
    )
    assert catalog_self_hit_thresholds(context, ability_indexes=indexes(s)) == ()
    source = next(
        a
        for a in native_definitions.package.army_catalog.datasheet_by_id("000003909").abilities
        if a.ability_id == "000003909:whispering-web"
    )
    assert source.rule_ir_payload is not None
    current_rule = RuleIR.from_payload(cast(RuleIRPayload, source.rule_ir_payload))
    assert (
        current_rule.ir_hash() == "24669fc8e965061719402530ca0fb87090f75a817629350401d332f042e74073"
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

    historical = faction_pack_rule_ir.datasheet_rule_ir_payload_by_source_row_id("000003909:5")
    assert historical is not None
    rule = RuleIR.from_payload(historical)
    assert current_rule.normalized_text == rule.normalized_text
    assert current_rule.source_id == rule.source_id
    assert current_rule.clauses[0] == rule.clauses[0]
    assert rule.ir_hash() == "02b5c11d47776e8a050dd004db3f1d725c8ec1828e1624017c439bc0fa1c2219"
    assert clause_is_post_shoot_hit_target_selection(rule.clauses[0])
    # The predecessor selected-target execution gap remains preserved historical
    # evidence; current native selected-target behavior is covered in test_lhykhis.


def test_native_ordinary_fights_first_and_unattached_units_do_not_grant_mandiblasters(
    native_definitions: Section02Definitions,
) -> None:
    from tests.support.faction_batch01 import scene, selection
    from warhammer40k_core.engine.fights_first import FightsFirstRegistry
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds
    from warhammer40k_core.engine.phase import BattlePhase

    s = scene(
        native_definitions,
        (
            selection(native_definitions, SCORPIONS, "scorpions"),
            selection(native_definitions, "000000577", "autarch"),
            selection(native_definitions, "000000594", "banshees"),
        ),
        (selection(native_definitions, WALKERS, "walkers"),),
        phase=BattlePhase.FIGHT,
        seed="mandiblasters-ordinary-fights-first",
    )
    registry = FightsFirstRegistry.from_state(s.state)
    assert registry.has_unit("own:banshees")
    assert not registry.charged_unit_ids()
    for unit_id, weapon in (
        ("own:scorpions", SCORPIONS + ":scorpion-chainsword"),
        ("own:autarch", "000000577:star-glaive"),
        ("own:banshees", "000000594:banshee-blade"),
    ):
        context = hit_context(
            s, native_definitions.weapon(weapon), s.units[unit_id].own_model_ids()[0]
        )
        assert resolve_hit_thresholds(context, ability_indexes=indexes(s)).critical_threshold == 6


def test_loaded_catalog_cannot_silently_omit_the_attacking_owner(
    native_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds
    from warhammer40k_core.engine.phase import GameLifecycleError

    s = scorpion_scene(native_definitions)
    context = hit_context(
        s,
        native_definitions.weapon(SCORPIONS + ":scorpion-chainsword"),
        s.units["own:scorpions"].own_model_ids()[0],
    )
    other_only = tuple((owner, idx) for owner, idx in indexes(s) if owner != "owner")
    assert other_only
    with pytest.raises(GameLifecycleError, match="missing"):
        resolve_hit_thresholds(context, ability_indexes=other_only)
