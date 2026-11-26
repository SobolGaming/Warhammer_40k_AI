"""Whispering Web must activate after physical model shots and affect later attacks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from tests.factions.aeldari.current_source_helpers import definitions
from tests.factions.aeldari.mandiblasters_helpers import hit_payloads
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.support.faction_batch01 import anchor, locate, request, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import shooting_payload, shooting_request, weapon_rows
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollResultPayload,
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pose import Pose

if TYPE_CHECKING:
    from tests.support.faction_batch01 import Scene
    from warhammer40k_core.engine.decision_request import DecisionRequest

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
    from tests.support.faction_batch01 import events

    (count_payload,) = (
        row
        for row in events(s.session, "random_characteristic_rolled")
        if row["characteristic"] == "attacks"
    )
    count = RandomCharacteristicRoll.from_payload(
        cast(RandomCharacteristicRollPayload, count_payload)
    )
    attack_die = count.roll_state.original_result
    rolls = [
        DiceRollResult.from_payload(cast(DiceRollResultPayload, row))
        for row in events(s.session, "dice_rolled")
    ]
    assert attack_die in rolls
    assert attack_die.spec.expression == DiceExpression(quantity=1, sides=6, modifier=3)
    (face,) = attack_die.values
    assert count.roll_state.current_values == attack_die.values
    hits = hit_payloads(s)
    assert len(hits) == count.value == face + attack_die.spec.expression.modifier
    assert all(
        h["successful"]
        and h["skipped"]
        and not h["critical"]
        and h["roll_state"] is None
        and h["unmodified_roll"] is None
        and h["generated_hits"] == 1
        for h in hits
    )
    assert all(roll.spec.roll_type != "attack_sequence.hit" for roll in rolls)
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
    from tests.factions.aeldari.lhykhis_scripted_attacks import scripted_six_brood_twain_wounds
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.order130_helpers import session_from_casualty_checkpoint
    from tests.support.faction_batch01 import events
    from tests.support.section02_consumers import payload_object
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target = "foe:walkers"
    scripted = web_scene(
        native_definitions,
        attached=True,
        seed="native-web-attached",
        rng_seed_label="native-web-attached-private-screen-1526",
    )
    ordinary = restored_scene(scripted)

    def resolve(current: Scene) -> DecisionRequest:
        declare_web(current, attached=True)
        pending = drive_to(current, {CHOICE, "select_shooting_unit"}, source_first=False)
        groups = [
            payload_object(payload_object(record.result.payload)["gathered_group"])["pool_indices"]
            for record in current.session.lifecycle.decision_controller.records
            if record.request.decision_type == "select_attack_weapon_group"
            and payload_object(record.result.payload)["sequence_id"]
            == "attack-sequence:web-declaration"
        ]
        assert groups == [[1], [2, 3, 4, 5], [0]]
        return pending

    def assert_no_surviving_target(current: Scene, pending: DecisionRequest) -> None:
        assert pending.decision_type == "select_shooting_unit"
        assert not rules_unit_view_by_id(
            state=current.state, unit_instance_id=target
        ).alive_models()
        [casualty] = [
            row
            for row in events(current.session, "model_destroyed")
            if row["target_unit_instance_id"] == target
        ]
        assert casualty["source_model_instance_id"] in current.units["own:lhykhis"].own_model_ids()
        assert not events(current.session, "catalog_post_shoot_hit_target_effect_requested")

    # Scripted native proof. Earlier bodyguard groups still consume ordinary RNG.
    with scripted_six_brood_twain_wounds(scripted, attached_target=False):
        pending = resolve(scripted)
    assert_no_surviving_target(scripted, pending)
    scripted.session = session_from_casualty_checkpoint(scripted.session.lifecycle)
    _assert_web_shooting_end_replay(scripted, pending, artifact_id="web-scripted-source-last")

    # Ordinary full replay preserves its reached outcome and the actual offer/absence.
    pending = resolve(ordinary)
    alive = rules_unit_view_by_id(state=ordinary.state, unit_instance_id=target).alive_models()
    if alive:
        assert pending.decision_type == CHOICE
        assert not any(
            row["target_unit_instance_id"] == target
            for row in events(ordinary.session, "model_destroyed")
        )
        _assert_web_choice_replay(ordinary, pending, target, artifact_id="web-ordinary-source-last")
    else:
        assert_no_surviving_target(ordinary, pending)
        _assert_web_shooting_end_replay(ordinary, pending, artifact_id="web-ordinary-source-last")


def _assert_web_shooting_end_replay(
    current: Scene, pending: DecisionRequest, *, artifact_id: str
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import choose
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene

    restored = restored_scene(current)
    assert restored.session.to_persistence_payload() == current.session.to_persistence_payload()
    for branch in (current, restored):
        request_before = branch.session.lifecycle.pending_decision_request()
        assert request_before is not None
        assert request_before == pending
        choose(branch, request_before, "complete_shooting_phase")
    assert restored.session.to_persistence_payload() == current.session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(current.session.replay_artifact(artifact_id=artifact_id))
        .run()
        .reproduced_exactly
    )


def _assert_web_choice_replay(
    current: Scene,
    pending: DecisionRequest,
    target: str,
    *,
    artifact_id: str,
    restore_accepted_mark: bool = False,
) -> None:
    from tests.factions.aeldari.lhykhis_helpers import choose, hit_with_face
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.support.faction_batch01 import events
    from tests.support.section02_consumers import payload_object

    assert pending.decision_type == CHOICE
    assert payload_object(pending.payload)["available_target_unit_instance_ids"] == [target]
    assert len(pending.options) == 1
    restored = restored_scene(current)
    assert restored.session.to_persistence_payload() == current.session.to_persistence_payload()
    for branch in (current, restored):
        request_before = branch.session.lifecycle.pending_decision_request()
        assert request_before is not None
        assert request_before == pending
        choose(branch, request_before, request_before.options[0].option_id)
        assert len(events(branch.session, "catalog_post_shoot_hit_target_effect_selected")) == 1
        assert hit_with_face(branch, target_id=target, face=5).critical
    accepted = current.session.to_persistence_payload()
    assert restored.session.to_persistence_payload() == accepted
    if restore_accepted_mark:
        restored_accepted = restored_scene(current)
        assert restored_accepted.session.to_persistence_payload() == accepted
        hit = hit_with_face(restored_accepted, target_id=target, face=5)
        assert hit.unmodified_roll == hit.critical_threshold == 5
        assert hit.critical
    assert (
        ReplayRunner.from_payload(current.session.replay_artifact(artifact_id=artifact_id))
        .run()
        .reproduced_exactly
    )


def _assert_charged_fangs_use_natural_four_and_five(s: Scene, completed_before: int) -> None:
    from tests.factions.aeldari.lhykhis_helpers import choose
    from tests.factions.aeldari.lhykhis_scripted_attacks import scripted_charged_fangs
    from tests.support.faction_batch01 import events
    from tests.support.section02_consumers import payload_object, payload_text
    from warhammer40k_core.engine.lethal_hits import (
        AUTO_WOUND_OPTION_ID,
        SELECT_LETHAL_HIT_WOUND_DECISION_TYPE,
    )

    choice: DecisionRequest | None = None
    with scripted_charged_fangs(s):
        for _ in range(180):
            if len(events(s.session, "attack_sequence_completed")) > completed_before:
                break
            pending = request(s.session.advance_until_decision_or_terminal())
            if pending.decision_type == "select_attack_weapon_group" and choice is None:
                options = [
                    option
                    for option in pending.options
                    if payload_object(payload_object(option.payload)["gathered_group"])[
                        "pool_indices"
                    ]
                    == [0]
                ]
                assert len(options) == 1
                choose(s, pending, options[0].option_id)
            elif pending.decision_type == SELECT_LETHAL_HIT_WOUND_DECISION_TYPE:
                context = payload_text(payload_object(pending.payload)["attack_context_id"])
                if context.endswith(":pool-001:attack-002"):
                    assert choice is None
                    assert pending.actor_id == "owner"
                    assert AUTO_WOUND_OPTION_ID in {option.option_id for option in pending.options}
                    choice = pending
                    choose(s, pending, AUTO_WOUND_OPTION_ID)
                else:
                    submit_fixture_request(s.session, pending)
            else:
                submit_fixture_request(s.session, pending)
        else:
            raise AssertionError("Scripted native charged Fight did not complete")

    assert choice is not None
    [completion] = events(s.session, "attack_sequence_completed")[completed_before:]
    sequence_id = payload_text(completion["sequence_id"])
    choice_payload = payload_object(choice.payload)
    assert choice_payload["sequence_id"] == sequence_id
    critical_id = f"{sequence_id}:pool-001:attack-002"
    normal_id = f"{sequence_id}:pool-001:attack-001"
    assert choice_payload["attack_context_id"] == critical_id
    steps = [
        row
        for row in events(s.session, "attack_sequence_step")
        if row["sequence_id"] == sequence_id
        and payload_text(row["attack_context_id"]).startswith(f"{sequence_id}:pool-001:")
    ]
    hits = [payload_object(row["payload"]) for row in steps if row["step"] == "hit"]
    assert [hit["unmodified_roll"] for hit in hits] == [4, 5, 1, 1, 1]
    assert [hit["successful"] for hit in hits] == [True, True, False, False, False]
    assert [hit["critical"] for hit in hits] == [False, True, False, False, False]
    assert all(hit["critical_threshold"] == 5 for hit in hits)

    wounds = {
        payload_text(row["attack_context_id"]): payload_object(row["payload"])
        for row in steps
        if row["step"] == "wound"
    }
    assert wounds.keys() == {normal_id, critical_id}
    assert not wounds[normal_id]["skipped"]
    assert not wounds[normal_id]["successful"]
    assert wounds[normal_id]["unmodified_roll"] == 1
    assert wounds[critical_id]["skipped"]
    assert wounds[critical_id]["successful"]
    assert wounds[critical_id]["unmodified_roll"] is None
    assert not wounds[critical_id]["critical"]

    # The selected group uses precisely the fixture's physical dice on the live journal.
    physical_wounds = [
        row
        for row in events(s.session, "dice_rolled")
        if (spec := payload_object(row["spec"]))["roll_type"] == "attack_sequence.wound"
        and payload_text(spec["reason"]).endswith((normal_id, critical_id))
    ]
    [normal_wound] = physical_wounds
    assert payload_text(payload_object(normal_wound["spec"])["reason"]).endswith(normal_id)
    assert normal_wound["values"] == [1]
    assert normal_wound["source"] == "fixed"
    records = s.session.lifecycle.decision_controller.records
    [applied] = [
        record
        for record in records
        if record.request.decision_type == SELECT_LETHAL_HIT_WOUND_DECISION_TYPE
        and payload_object(record.request.payload)["attack_context_id"] in {normal_id, critical_id}
    ]
    assert applied.request == choice
    assert applied.result.selected_option_id == AUTO_WOUND_OPTION_ID


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
    from tests.support.section02_consumers import payload_object, payload_text
    from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
    from warhammer40k_core.engine.lethal_hits import (
        AUTO_WOUND_OPTION_ID,
        SELECT_LETHAL_HIT_WOUND_DECISION_TYPE,
    )

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
    scripted = restored_scene(s)
    _assert_charged_fangs_use_natural_four_and_five(scripted, completed_before)
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
    [completion] = events(s.session, "attack_sequence_completed")[completed_before:]
    sequence_id = cast(str, completion["sequence_id"])
    decisions = s.session.lifecycle.decision_controller
    sequence = completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence_id
    )
    assert sequence.attacking_unit_instance_id == "own:lhykhis"

    steps = [
        row
        for row in events(s.session, "attack_sequence_step")
        if row["sequence_id"] == sequence_id
    ]
    hits = {
        payload_text(row["attack_context_id"]): payload_object(row["payload"])
        for row in steps
        if row["step"] == "hit"
    }
    assert hits
    for hit in hits.values():
        face = hit["unmodified_roll"]
        assert type(face) is int
        assert hit["critical_threshold"] == 5
        assert hit["critical"] is (face >= 5)
    critical_ids = {attack_id for attack_id, hit in hits.items() if hit["critical"]}
    auto_wounds = {
        payload_text(row["attack_context_id"]): payload_object(row["payload"])
        for row in steps
        if row["step"] == "wound" and payload_object(row["payload"])["skipped"]
    }
    applied_choices = {
        payload_text(payload_object(record.request.payload)["attack_context_id"])
        for record in decisions.records
        if record.request.decision_type == SELECT_LETHAL_HIT_WOUND_DECISION_TYPE
        and record.result.selected_option_id == AUTO_WOUND_OPTION_ID
        and payload_object(record.request.payload)["sequence_id"] == sequence_id
    }
    assert critical_ids == applied_choices == auto_wounds.keys()
    assert auto_wounds
    assert all(wound["successful"] and not wound["critical"] for wound in auto_wounds.values())
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
    from tests.factions.aeldari.lhykhis_helpers import declare_web, drive_to, web_scene
    from tests.factions.aeldari.lhykhis_scripted_attacks import scripted_six_brood_twain_wounds
    from tests.factions.aeldari.mandiblasters_helpers import restored_scene
    from tests.order130_helpers import session_from_casualty_checkpoint
    from tests.support.faction_batch01 import events
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target = "attached-unit:foe:target-body"
    scripted = web_scene(native_definitions, attached_target=True, seed="native-web-attached")
    ordinary = restored_scene(scripted)
    bodyguard_ids = set(scripted.units["foe:target-body"].own_model_ids())
    leader_ids = set(scripted.units["foe:target-leader"].own_model_ids())
    source_ids = set(scripted.units["own:lhykhis"].own_model_ids())

    def resolve(current: Scene) -> tuple[DecisionRequest, set[str]]:
        declare_web(current, target_id=target)
        pending = drive_to(current, {CHOICE, "select_shooting_unit"})
        view = rules_unit_view_by_id(state=current.state, unit_instance_id=target)
        casualties = [
            row
            for row in events(current.session, "model_destroyed")
            if row["model_instance_id"] in bodyguard_ids
        ]
        assert all(row["source_model_instance_id"] in source_ids for row in casualties)
        from tests.support.section02_consumers import payload_text

        dead = {payload_text(row["model_instance_id"]) for row in casualties}
        assert view.is_attached_rules_unit
        assert {model.model_instance_id for model in view.alive_models()} == (
            (bodyguard_ids - dead) | leader_ids
        )
        return pending, dead

    # Scripted native removal of the final bodyguard and a genuine mark continuation.
    with scripted_six_brood_twain_wounds(scripted, attached_target=True):
        pending, dead = resolve(scripted)
    assert dead == bodyguard_ids
    scripted.session = session_from_casualty_checkpoint(scripted.session.lifecycle)
    _assert_web_choice_replay(
        scripted, pending, target, artifact_id="web-scripted-attached", restore_accepted_mark=True
    )

    # Unmodified ordinary RNG checks the exact derived survivor set and the same
    # original target identity, whether or not every bodyguard dies on this run.
    pending, _ = resolve(ordinary)
    _assert_web_choice_replay(
        ordinary, pending, target, artifact_id="web-ordinary-attached", restore_accepted_mark=True
    )
