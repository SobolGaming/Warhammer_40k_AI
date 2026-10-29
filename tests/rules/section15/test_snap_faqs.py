"""15.08/15.09 and FAQs55/56: native profiles at the shared hit and facade owners."""

from dataclasses import replace

import pytest

from tests.generic_modifier_helpers import generic_effect
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import native_sequence
from tests.support.section15_fixtures import checkpoint, context, obj, offer, request, submit
from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.weapon_abilities import SNAP_SHOOTING_RULE_ID


@pytest.mark.parametrize("split_targets", [False, True])
def test_snap_two_weapons_allow_one_target_and_atomically_reject_two(
    section15_definitions: Section02Definitions, split_targets: bool
) -> None:
    from tests.support.section03_fixtures import placement
    from tests.support.section04_fixtures import shooting_payload, weapon_rows
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind
    from warhammer40k_core.engine.unit_state import StartingStrengthRecord
    from warhammer40k_core.geometry.pose import Pose

    d = section15_definitions
    session, state, unit, enemy = checkpoint(
        d,
        sheet="000004080",
        phase=BattlePhase.MOVEMENT,
        active="opponent",
        distance=8,
        materialize=False,
    )
    other = d.unit("000004078", identity="second-target", army_id="enemy")
    state.army_definitions[:] = [
        replace(a, units=(*a.units, other)) if a.player_id == "opponent" else a
        for a in state.army_definitions
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="opponent", unit=other)
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=(
                        *a.unit_placements,
                        placement(other, (Pose.at(18, 14),), enemy=True),
                    ),
                )
                if a.player_id == "opponent"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    use = offer(session, state, "fire-overwatch", context(state, TimingTriggerKind.END_PHASE))
    declaration = request(submit(session, use, unit))
    candidates = obj(declaration.payload)["proposal_request"]["target_candidates"]
    # Both physical targets independently qualify; cardinality is the only changed predicate.
    assert {enemy, other.unit_instance_id}.issubset(
        {
            c["target_unit_instance_id"]
            for c in candidates
            if c["is_legal"] and "snap" in c["shooting_types"]
        }
    )
    rows = weapon_rows(declaration)[:2]
    assert len(rows) == 2
    assert rows[0]["weapon_instance_id"] != rows[1]["weapon_instance_id"]
    payload = obj(
        shooting_payload(
            declaration, rows, [enemy, other.unit_instance_id if split_targets else enemy]
        )
    )
    for row in payload["declarations"]:
        row["shooting_type"] = "snap"
    before = session.lifecycle.to_payload()
    pending = session.lifecycle.decision_controller.queue.pending_requests
    status = session.submit_parameterized_payload(
        request_id=declaration.request_id, result_id="s15:snap-cardinality", payload=payload
    )
    assert (status.status_kind is LifecycleStatusKind.INVALID) is split_targets
    if split_targets:
        assert session.lifecycle.to_payload() == before
        assert (
            session.lifecycle.decision_controller.queue.pending_requests
            == pending
            == (declaration,)
        )
    else:
        assert session.lifecycle.to_payload() != before
        assert session.lifecycle.decision_controller.queue.pending_requests != pending
        assert state.command_point_total("owner") == 3


@pytest.mark.parametrize("snap", [False, True])
@pytest.mark.parametrize("face", [1, 2, 3, 4, 5, 6])
def test_faq55_56_critical_four_plus_grant_cannot_create_snap_hits_or_criticals(
    section15_definitions: Section02Definitions, snap: bool, face: int
) -> None:
    state, _target, sequence = native_sequence(section15_definitions)
    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue

    native = sequence.attack_pools[0]
    # Explicit FAQ contract: BS5 plus a critical4 grant on an unchanged native
    # weapon identity; this is not claimed as the Lord's printed BS.
    pool = replace(
        native,
        weapon_profile=replace(
            native.weapon_profile,
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 5),
        ),
        targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,) if snap else (),
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id="constructed:s15:critical",
            owner_player_id="owner",
            target_unit_instance_ids=(sequence.attacking_unit_instance_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "attack_role": "attacker",
                "roll_type": "hit",
                "status": "critical_hit_threshold",
                "critical_threshold": 4,
            },
        )
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="s15:hit",
        attacker_player_id="owner",
        reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,) if snap else (),
    )
    original = DiceRollManager(state.game_id).roll_fixed(spec, (face,)).original_result
    hit = _roll_hit(
        state=state,
        manager=DiceRollManager(state.game_id, injected_results=(original,)),
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="s15:hit",
        source_phase=BattlePhase.SHOOTING,
    )
    assert hit.successful is (face == 6 if snap else face >= 4)
    assert hit.critical is (False if snap else face >= 4)
    assert hit.roll_state is not None
    assert hit.roll_state.original_result.spec.reroll_forbidden_rule_ids == (
        (SNAP_SHOOTING_RULE_ID,) if snap else ()
    )
    assert hit.unmodified_roll == face


@pytest.mark.parametrize(
    ("face", "delta", "successful"), [(5, 20, False), (6, -20, True), (1, 20, False)]
)
def test_snap_unmodified_six_is_independent_of_roll_modifiers(
    section15_definitions: Section02Definitions, face: int, delta: int, successful: bool
) -> None:
    state, _target, sequence = native_sequence(section15_definitions)
    from warhammer40k_core.core.modifiers import RollModifier

    pool = replace(
        sequence.attack_pools[0],
        targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,),
        hit_roll_modifier=delta,
        hit_roll_modifiers=(
            RollModifier("constructed:s15:hit-modifier", delta, "constructed:s15:permission"),
        ),
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="s15:modified-hit",
        attacker_player_id="owner",
        reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
    )
    original = DiceRollManager(state.game_id).roll_fixed(spec, (face,)).original_result
    hit = _roll_hit(
        state=state,
        manager=DiceRollManager(state.game_id, injected_results=(original,)),
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="s15:modified-hit",
        source_phase=BattlePhase.SHOOTING,
    )
    assert hit.successful is successful
    assert hit.critical is False
    assert hit.unmodified_roll == face


def test_overwatch_native_target_gets_shared_snap_declaration_and_completes_attack(
    section15_definitions: Section02Definitions,
) -> None:
    from tests.support.section04_fixtures import finish_attacks, shooting_payload, weapon_rows
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    session, state, unit, enemy = checkpoint(
        section15_definitions, phase=BattlePhase.MOVEMENT, active="opponent", distance=8
    )
    req = offer(session, state, "fire-overwatch", context(state, TimingTriggerKind.END_PHASE))
    declaration = request(submit(session, req, unit))
    assert declaration.decision_type == "submit_shooting_declaration"
    assert isinstance(declaration.payload, dict)
    proposal = obj(declaration.payload)["proposal_request"]
    assert all(
        c["shooting_types"] == ["snap"] for c in proposal["target_candidates"] if c["is_legal"]
    )
    rows = weapon_rows(declaration)[:1]
    assert rows
    payload = obj(shooting_payload(declaration, rows, [enemy] * len(rows)))
    for row in payload["declarations"]:
        row["shooting_type"] = "snap"
    status = session.submit_parameterized_payload(
        request_id=declaration.request_id,
        result_id="s15:snap-declare",
        payload=payload,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    finish_attacks(session)
    from warhammer40k_core.engine.activity_restrictions import has_activity_restriction
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    assert has_activity_restriction(
        state=state,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit),
        activity="completed_shooting",
    )
    assert state.command_point_total("owner") == 3
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert any(
        e.event_type == "attack_sequence_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )
