"""Whispering Web must activate after physical model shots and affect later attacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.factions.aeldari.current_source_helpers import definitions
from tests.factions.aeldari.mandiblasters_helpers import hit_payloads
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.support.faction_batch01 import anchor, locate, request, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import shooting_payload, shooting_request, weapon_rows
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pose import Pose

LHYKHIS = "000003909"
CHOICE = "select_catalog_post_shoot_hit_target_effect"


@pytest.fixture(scope="module")
def native_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    return definitions(
        selected_army_source_index,
        datasheet_ids=(LHYKHIS, "000000594", "000000612", "000000601", "000000593", "000004079"),
    )


def test_native_torrent_hits_without_damage_require_target_choice(
    native_definitions: Section02Definitions,
) -> None:
    s = scene(
        native_definitions,
        (
            selection(native_definitions, LHYKHIS, "lhykhis"),
            selection(native_definitions, "000000594", "scorpions"),
        ),
        (
            selection(native_definitions, "000000612", "walkers"),
            selection(native_definitions, "000000612", "other"),
        ),
        phase=BattlePhase.SHOOTING,
        seed="mandiblasters-lhykhis-control-private-6",
    )
    locate(s, "foe:walkers", (Pose.at(19, 10),))
    anchor(s)
    request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    r = shooting_request(s.session, "own:lhykhis")
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=shooting_payload(r, weapon_rows(r)[:1], ("foe:walkers",)),
        result_id="lhykhis-shoot",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    for _ in range(100):
        r = request(s.session.advance_until_decision_or_terminal())
        if r.decision_type in {CHOICE, "select_shooting_unit"}:
            break
        submit_fixture_request(s.session, r)
    assert r.decision_type == CHOICE
    hits = hit_payloads(s)
    assert len(hits) == 6
    assert all(h["successful"] and h["skipped"] and not h["critical"] for h in hits)
    assert s.units["foe:walkers"].own_models[0].current_wounds == 6
    assert len(r.options) == 1
    s.session.submit_option(
        request_id=r.request_id, option_id=r.options[0].option_id, result_id="choose-web"
    )
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="whispering-web"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("source_first", [True, False])
def test_attached_model_completion_selects_only_its_hits_and_restores(
    native_definitions: Section02Definitions,
    source_first: bool,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import choose, declare_web, drive_to, web_scene
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.support.faction_batch01 import events

    s = web_scene(native_definitions, attached=True, seed="native-web-attached", full_target=True)
    declare_web(s, attached=True)
    r = drive_to(s, {CHOICE, "select_shooting_unit"}, source_first=source_first)
    assert r.decision_type == CHOICE
    assert isinstance(r.payload, dict)
    assert r.payload["source_model_instance_id"] == s.units["own:lhykhis"].own_model_ids()[0]
    assert r.payload["available_target_unit_instance_ids"] == ["foe:walkers"]
    unit_completed = events(s.session, "attack_sequence_completed")
    assert bool(unit_completed) is (not source_first)
    assert isinstance(r.payload["attack_sequence"], dict)
    source_event_id = r.payload["attack_sequence_completed_event_id"]
    evidence = next(
        e
        for e in s.session.lifecycle.decision_controller.event_log.records
        if e.event_id == source_event_id
    )
    assert evidence.event_type == "attack_sequence_models_attacked"
    if source_first:
        from tests.factions.aeldari.lhykhis_completion_helpers import (
            assert_partial_completion_authority,
        )

        assert_partial_completion_authority(s)
    assert len(r.options) == 1
    restored = restored_scene(s)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    for current in (s, restored):
        pending = current.session.lifecycle.pending_decision_request()
        assert pending is not None
        choose(current, pending, pending.options[0].option_id)
        drive_to(current, {"select_shooting_unit"}, source_first=source_first)
        assert len(events(current.session, "catalog_post_shoot_hit_target_effect_selected")) == 1
        if not source_first:
            records = current.session.lifecycle.decision_controller.event_log.records
            web_index = next(
                i
                for i, e in enumerate(records)
                if e.event_type == "catalog_post_shoot_hit_target_effect_selected"
            )
            focus_index, focus = next(
                (i, e)
                for i, e in enumerate(records)
                if e.event_type == "decision_requested"
                and isinstance(e.payload, dict)
                and e.payload.get("decision_type") == "select_triggered_movement"
            )
            assert focus_index > web_index
            assert isinstance(focus.payload, dict)
            assert focus.payload["actor_id"] == "opponent"
            from warhammer40k_core.engine.timing_batch_runtime import timing_batch_from_event

            batches = [
                timing_batch_from_event(e)
                for e in records
                if e.event_type == "timing_batch_transition"
            ]
            assert any(
                any(":000003909:5" in p.source_rule_id for p in b.participants)
                and any(
                    p.source_rule_id == "phase17f:phase17e:aeldari:army-rule"
                    for p in b.participants
                )
                for b in batches
            )
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-attached"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("no_attacks", [True, False])
def test_bodyguard_hits_or_empty_selection_cannot_activate_source(
    native_definitions: Section02Definitions,
    no_attacks: bool,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import declare_web, drive_to, web_scene
    from tests.support.faction_batch01 import events

    s = web_scene(native_definitions, attached=True)
    declare_web(s, attached=True, bodyguards_only=not no_attacks, no_attacks=no_attacks)
    r = drive_to(s, {CHOICE, "select_shooting_unit"})
    assert r.decision_type == "select_shooting_unit"
    assert not events(s.session, "catalog_post_shoot_hit_target_effect_requested")
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-no-source-hit"))
        .run()
        .reproduced_exactly
    )


def test_compiled_grant_requires_every_typed_gate(native_definitions: Section02Definitions) -> None:
    from dataclasses import replace
    from typing import cast

    from warhammer40k_core.engine.catalog_selected_target_pair_support import (
        selected_target_persisting_effect_clause_is_supported,
    )
    from warhammer40k_core.rules.rule_ir import (
        RuleIR,
        RuleIRPayload,
        parameter_payload,
        parameters_from_pairs,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

    ability = next(
        a
        for a in native_definitions.package.army_catalog.datasheet_by_id(LHYKHIS).abilities
        if a.ability_id == LHYKHIS + ":whispering-web"
    )
    assert ability.rule_ir_payload is not None
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    clause = rule.clauses[1]
    assert selected_target_persisting_effect_clause_is_supported(clause)
    values = parameter_payload(clause.effects[0].parameters)
    assert values["required_model_keyword"] == "AELDARI"
    for key in values:
        effect = replace(
            clause.effects[0],
            parameters=parameters_from_pairs(tuple((k, v) for k, v in values.items() if k != key)),
        )
        assert not selected_target_persisting_effect_clause_is_supported(
            replace(clause, effects=(effect,))
        )
    for key, value in (
        ("critical_threshold", True),
        ("critical_threshold", 7),
        ("critical_threshold", 1),
        ("roll_type", "wound"),
        ("attack_role", "target"),
        ("unknown", True),
    ):
        effect = replace(
            clause.effects[0],
            parameters=parameters_from_pairs(tuple({**values, key: value}.items())),
        )
        assert not selected_target_persisting_effect_clause_is_supported(
            replace(clause, effects=(effect,))
        )
    for condition in clause.conditions:
        assert not selected_target_persisting_effect_clause_is_supported(
            replace(clause, conditions=(condition,))
        )
    assert clause.trigger is not None
    assert not selected_target_persisting_effect_clause_is_supported(
        replace(
            clause,
            trigger=replace(
                clause.trigger, parameters=parameters_from_pairs((("roll_type", "wound"),))
            ),
        )
    )
    old = faction_pack_rule_ir.datasheet_rule_ir_payload_by_source_row_id("000003909:5")
    assert old is not None
    assert (
        RuleIR.from_payload(old).ir_hash()
        == "02b5c11d47776e8a050dd004db3f1d725c8ec1828e1624017c439bc0fa1c2219"
    )
    assert rule.normalized_text == old["normalized_text"]
    assert rule.rule_id == old["rule_id"]


def test_marked_native_ranged_and_melee_faces_use_shared_provenance(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import activate_web, hit_with_face, web_scene

    s = web_scene(native_definitions)
    activate_web(s)
    for attacker, melee in (("own:avengers", False), ("own:lhykhis", True)):
        for face in (4, 5, 6):
            for modifier in (-1, 0, 1):
                hit = hit_with_face(
                    s, attacker_id=attacker, face=face, melee=melee, modifier=modifier
                )
                assert hit.critical is (face >= 5)
                assert hit.critical_threshold == 5
                assert any(":000003909:5:" in source for source in hit.threshold_source_ids)
    # An unrelated enemy and the opposing Aeldari owner cannot borrow the mark.
    assert not hit_with_face(s, target_id="foe:other", face=5).critical
    assert not hit_with_face(s, attacker_id="foe:other", face=5).critical
    # Brood Twain remains automatic, with no unmodified face or critical result.
    automatic = hit_with_face(s, attacker_id="own:lhykhis")
    assert automatic.skipped
    assert not automatic.critical


def test_later_native_ranged_attacks_use_mark_and_resume_pending_work(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import (
        activate_web,
        drive_to,
        legal_shooting_payload,
        web_scene,
    )
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.support.faction_batch01 import events

    s = web_scene(native_definitions, full_target=True, seed="native-web-ranged")
    activate_web(s)
    checkpoint = restored_scene(s)
    assert checkpoint.session.to_persistence_payload() == s.session.to_persistence_payload()
    for current in (s, checkpoint):
        r = shooting_request(current.session, "own:avengers")
        status = current.session.submit_parameterized_payload(
            request_id=r.request_id,
            payload=legal_shooting_payload(r, "foe:walkers"),
            result_id="ranged-web-beneficiary",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    pending = restored_scene(s)
    assert pending.session.to_persistence_payload() == s.session.to_persistence_payload()
    for current in (s, checkpoint, pending):
        drive_to(current, {"select_shooting_unit"})
    assert checkpoint.session.to_persistence_payload() == s.session.to_persistence_payload()
    assert pending.session.to_persistence_payload() == s.session.to_persistence_payload()
    hit_rows = [
        e["payload"]
        for e in events(s.session, "attack_sequence_step")
        if e["step"] == "hit" and isinstance(e["payload"], dict) and not e["payload"]["skipped"]
    ]
    assert any(h["unmodified_roll"] == 5 for h in hit_rows)
    for hit in hit_rows:
        assert isinstance(hit["unmodified_roll"], int)
        assert hit["critical"] is (hit["unmodified_roll"] >= 5)
        assert hit["critical_threshold"] == 5
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-ranged-native"))
        .run()
        .reproduced_exactly
    )


def test_finite_selection_rejects_wrong_actor_stale_option_and_payload(
    native_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.factions.aeldari.lhykhis_helpers import declare_web, drive_to, web_scene
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        invalid_catalog_post_shoot_hit_target_effect_status,
    )
    from warhammer40k_core.engine.decision_result import DecisionResult

    s = web_scene(native_definitions)
    declare_web(s)
    r = drive_to(s, {CHOICE})
    result = DecisionResult.for_request(
        request=r, selected_option_id=r.options[0].option_id, result_id="valid-web"
    )
    before = s.session.to_persistence_payload()
    for invalid in (
        replace(result, actor_id="opponent"),
        replace(result, request_id="stale-web"),
        replace(result, selected_option_id="unoffered-web"),
        replace(result, payload={"forged": True}),
    ):
        assert (
            invalid_catalog_post_shoot_hit_target_effect_status(
                state=s.state, request=r, result=invalid
            )
            is not None
        )
        status = s.session.lifecycle.submit_decision(invalid)
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert s.session.lifecycle.pending_decision_request() == r
        assert s.session.to_persistence_payload() == before


def test_native_source_last_killed_target_has_no_selection(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import declare_web, drive_to, web_scene
    from tests.support.faction_batch01 import events

    s = web_scene(
        native_definitions,
        attached=True,
        seed="native-web-attached",
        rng_seed_label="native-web-attached-private-screen-1526",
    )
    declare_web(s, attached=True)
    r = drive_to(s, {CHOICE, "select_shooting_unit"}, source_first=False)
    assert r.decision_type == "select_shooting_unit"
    assert not any(
        m.is_alive
        for a in s.state.army_definitions
        for u in a.units
        if u.unit_instance_id == "foe:walkers"
        for m in u.own_models
    )
    assert any(
        e["source_model_instance_id"] in s.units["own:lhykhis"].own_model_ids()
        and e["target_unit_instance_id"] == "foe:walkers"
        for e in events(s.session, "model_destroyed")
    )
    assert not events(s.session, "catalog_post_shoot_hit_target_effect_requested")


def test_native_charge_fight_critical_five_is_lethal_and_turn_expiry_replays(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.current_source_helpers import charge
    from tests.factions.aeldari.lhykhis_helpers import (
        activate_web,
        choose,
        drive_to,
        hit_with_face,
        web_scene,
    )
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.support.faction_batch01 import events

    s = web_scene(native_definitions, full_target=True, charge_ready=True, seed="native-web-charge")
    activate_web(s)
    r = request(s.session.advance_until_decision_or_terminal(), "select_shooting_unit")
    choose(s, r, "complete_shooting_phase")
    drive_to(s, {"select_charging_unit"})
    charge(s, "own:lhykhis", "foe:walkers", 19 - (60 + 40) / 50.8 - 14)
    r = drive_to(s, {"select_charging_unit", "select_fight_activation"})
    if r.decision_type == "select_charging_unit":
        choose(s, r, "complete_charge_phase")
    assert events(s.session, "charge_move_completed")
    completed_before = len(events(s.session, "attack_sequence_completed"))
    restored = restored_scene(s)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    for current in (s, restored):
        for _ in range(180):
            if len(events(current.session, "attack_sequence_completed")) > completed_before:
                break
            r = request(current.session.advance_until_decision_or_terminal())
            submit_fixture_request(current.session, r)
        else:
            raise AssertionError("Native charged fight did not complete")
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    steps = events(s.session, "attack_sequence_step")
    hits = [
        e
        for e in steps
        if e["step"] == "hit"
        and isinstance(e["payload"], dict)
        and e["payload"]["unmodified_roll"] == 5
    ]
    assert hits
    for hit in hits:
        assert isinstance(hit["payload"], dict)
        assert hit["payload"]["critical"]
        assert hit["payload"]["critical_threshold"] == 5
    wounds = [
        e["payload"] for e in steps if e["step"] == "wound" and isinstance(e["payload"], dict)
    ]
    assert any(w["skipped"] and w["successful"] and not w["critical"] for w in wounds)
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-charge-fight"))
        .run()
        .reproduced_exactly
    )
    for _ in range(250):
        status = s.session.advance_until_decision_or_terminal()
        if s.state.active_player_id != "owner":
            break
        submit_fixture_request(s.session, request(status))
    else:
        raise AssertionError("Next player turn not reached")
    assert hit_with_face(s, face=5).critical_threshold == 6
    assert restored_scene(s).session.to_persistence_payload() == s.session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-expired"))
        .run()
        .reproduced_exactly
    )


def test_physical_attacker_keyword_cannot_be_borrowed_from_unit_union(
    native_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.factions.aeldari.lhykhis_helpers import activate_web, hit_with_face, web_scene
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    s = web_scene(native_definitions)
    activate_web(s)
    unit = next(
        u for a in s.state.army_definitions for u in a.units if u.unit_instance_id == "own:avengers"
    )
    first, second = unit.own_models[:2]
    assert hit_with_face(s, model_id=first.model_instance_id).critical
    # Explicit mixed-model contract, not an invented legal mixed-faction roster:
    # remove only the physical first model's faction token, leaving its unit's
    # other canonical models and aggregate AELDARI membership intact.
    changed = replace(
        first,
        keyword_assignment=replace(
            first.keyword_assignment,
            faction_keywords=tuple(
                k for k in first.keyword_assignment.faction_keywords if k != "AELDARI"
            ),
            keywords=tuple(k for k in first.keyword_assignment.keywords if k != "AELDARI"),
        ),
    )
    s.state.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                replace(u, own_models=(changed, *u.own_models[1:])) if u is unit else u
                for u in a.units
            ),
        )
        for a in s.state.army_definitions
    ]
    assert (
        "AELDARI"
        in rules_unit_view_by_id(state=s.state, unit_instance_id=unit.unit_instance_id).keywords
    )
    assert not hit_with_face(s, model_id=first.model_instance_id).critical
    assert hit_with_face(s, model_id=second.model_instance_id).critical


def test_native_source_death_does_not_revoke_existing_turn_grant(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import assert_native_source_loss

    assert_native_source_loss(native_definitions, seed="native-web-charge-4-private-4")


@pytest.mark.parametrize(
    ("unit_requirement", "unit_player"),
    [("mandatory", "owner"), ("optional", "owner"), ("mandatory", "opponent")],
)
def test_final_model_and_unit_candidates_share_core_sequencing(
    native_definitions: Section02Definitions, unit_requirement: str, unit_player: str
) -> None:
    from dataclasses import replace

    from tests.factions.aeldari.lhykhis_helpers import declare_web, drive_to, web_scene
    from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
    from warhammer40k_core.engine.attack_completion_sequencing import (
        resolve_attack_completion_candidates_now,
    )
    from warhammer40k_core.engine.attack_sequence_completion_hooks import (
        AttackSequenceCompletedContext,
        AttackSequenceCompletedHookBinding,
        AttackSequenceCompletedHookRegistry,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.event_log import EventLog
    from warhammer40k_core.engine.model_shooting_completion import model_completion_boundary
    from warhammer40k_core.engine.sequencing import (
        SequencingParticipant,
        SequencingRequirement,
        sequencing_decision_event_from_request,
    )
    from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

    s = web_scene(native_definitions, full_target=True)
    declare_web(s)
    r = drive_to(s, {CHOICE})
    original = s.session.lifecycle.decision_controller
    end = next(
        i
        for i, e in enumerate(original.event_log.records)
        if e.event_type == "attack_sequence_completion_state_recorded"
    )
    # A shared sequencing contract rooted in the exact native completion prefix.
    # The extra unit provider is explicitly constructed, not a new faction rule.
    decisions = DecisionController(
        event_log=EventLog(list(original.event_log.records[: end + 1])),
        _records=list(original.records),
    )
    completed = original.event_log.records[end - 1]
    assert completed.event_type == "attack_sequence_completed"
    assert isinstance(completed.payload, dict)
    sequence_id = completed.payload["sequence_id"]
    assert isinstance(sequence_id, str)
    sequence = completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence_id
    )
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    context = AttackSequenceCompletedContext(
        s.state,
        decisions,
        DiceRollManager(s.state.private_rng_seed, event_log=decisions.event_log),
        bundle.runtime_modifier_registry,
        BattlePhase.SHOOTING,
        sequence,
        completed.event_id,
    )
    activated: list[str] = []

    def activate_unit() -> None:
        activated.append("unit")

    unit_candidate = TimingRuleCandidate(
        SequencingParticipant(
            "constructed:unit-after-shot",
            unit_player,
            "constructed:shared-unit-completion",
            SequencingRequirement(unit_requirement),
        ),
        activate_unit,
    )

    def unit_candidates(
        _context: AttackSequenceCompletedContext,
    ) -> tuple[TimingRuleCandidate, ...]:
        return () if activated else (unit_candidate,)

    binding = AttackSequenceCompletedHookBinding(
        "constructed:unit-after-shot",
        "constructed:unit-source",
        lambda _context: None,
        candidate_handler=unit_candidates,
    )
    registry = AttackSequenceCompletedHookRegistry.from_bindings(
        (*bundle.attack_sequence_completed_hook_registry.bindings, binding)
    )
    all_candidates = registry.candidates_for(context)
    assert len(all_candidates) == 2
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        post_shoot_hit_target_effect_groups,
    )

    def groups(c: AttackSequenceCompletedContext) -> object:
        return post_shoot_hit_target_effect_groups(
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            armies=tuple(s.state.army_definitions),
            context=c,
        )

    assert not groups(replace(context, source_phase=BattlePhase.FIGHT))
    phase_index = s.state.battle_phase_index
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert not groups(context)
    s.state.battle_phase_index = phase_index
    s.state.active_player_id = "opponent"
    assert not groups(context)
    s.state.active_player_id = "owner"
    assert isinstance(r.payload, dict)
    model_event_id = r.payload["attack_sequence_completed_event_id"]
    assert isinstance(model_event_id, str)
    model_sequence, ids, _ = model_completion_boundary(decisions.event_log.records, model_event_id)
    partial = replace(
        context,
        attack_sequence=model_sequence,
        attack_sequence_completed_event_id=model_event_id,
        completed_model_instance_ids=ids,
    )
    assert len(registry.candidates_for(partial)) == 1
    status = resolve_attack_completion_candidates_now(
        context, lambda: registry.candidates_for(context)
    )
    assert status is not None
    if unit_requirement == "mandatory" and unit_player == "owner":
        order = decisions.queue.peek_next()
        assert order.decision_type == "resolve_sequencing_order"
        assert order.actor_id == "owner"
        result = DecisionResult.for_request(
            request=order,
            result_id="unit-first",
            selected_option_id="next:constructed:unit-after-shot",
        )
        decisions.submit_result(result)
        event_type, payload = sequencing_decision_event_from_request(request=order, result=result)
        decisions.event_log.append(event_type, payload)
        resolve_attack_completion_candidates_now(context, lambda: registry.candidates_for(context))
        assert activated == ["unit"]
    else:
        assert not activated
    assert decisions.queue.peek_next().decision_type == CHOICE


def test_native_attached_target_survives_bodyguard_loss_with_same_mark_identity(
    native_definitions: Section02Definitions,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import (
        choose,
        declare_web,
        drive_to,
        hit_with_face,
        web_scene,
    )
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target_id = "attached-unit:foe:target-body"
    s = web_scene(native_definitions, attached_target=True, seed="native-web-attached")
    declare_web(s, target_id=target_id)
    r = drive_to(s, {CHOICE, "select_shooting_unit"})
    assert r.decision_type == CHOICE
    assert isinstance(r.payload, dict)
    assert r.payload["available_target_unit_instance_ids"] == [target_id]
    view = rules_unit_view_by_id(state=s.state, unit_instance_id=target_id)
    assert all(
        m.model_instance_id in s.units["foe:target-leader"].own_model_ids()
        for m in view.alive_models()
    )
    assert view.is_attached_rules_unit
    choose(s, r, r.options[0].option_id)
    assert hit_with_face(s, target_id=target_id).critical
    restored = restored_scene(s)
    assert restored.session.to_persistence_payload() == s.session.to_persistence_payload()
    assert hit_with_face(restored, target_id=target_id).critical
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="web-target-survivor"))
        .run()
        .reproduced_exactly
    )
