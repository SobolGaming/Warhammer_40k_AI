"""Cross-category assertions at the shared facade attack completion boundary."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.d10_profile_helpers import (
    advertised_weapons,
    declaration_request,
    finish_profile_attack,
    profile_checkpoint,
    profile_proposal,
    profile_session,
    submit_profile,
)
from tests.lethal_hits_helpers import attack_completed, lethal_session
from tests.order97_gap_probes_04_06 import mixed_hazard_unit, weaponless_fight_session
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
)
from tests.psychic_modifier_helpers import pending_request, psychic_session, submit_fixture_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    RangeProfileKind,
    WeaponKeyword,
)
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    gathered_attack_groups_for_target,
)
from warhammer40k_core.engine.attack_sequence_selection import target_has_character_for_attack_group
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.hazard import (
    failed_hazard_roll_indices,
    hazard_mortal_wounds_per_failed_roll,
    hazard_roll_spec,
)
from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.stratagems import stratagem_decline_payload


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_facade_attack_selection_precedes_resolution_and_records_completed_participation(
    phase: BattlePhase,
) -> None:
    session = lethal_session(phase, sustained=0)
    selected = False
    declared = False
    for _ in range(150):
        if attack_completed(session):
            break
        request = pending_request(session)
        events = session.lifecycle.decision_controller.event_log.records
        assert not any(e.event_type == "attack_sequence_models_attacked" for e in events)
        if request.decision_type in {"select_shooting_unit", "select_fight_activation"}:
            selected = True
        if request.decision_type in {"submit_shooting_declaration", "submit_melee_declaration"}:
            assert selected
            assert not any(e.event_type == "attack_sequence_step" for e in events)
            declared = True
        if request.decision_type == "select_lethal_hit_wound":
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:order97",
                option_id="auto-wound",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "submit_stratagem_target_proposal":
            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:order97",
                payload=stratagem_decline_payload(),
            )
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("The real facade attack failed to finish.")
    assert declared
    events = session.lifecycle.decision_controller.event_log.records
    completion_index = next(
        i for i, e in enumerate(events) if e.event_type == "attack_sequence_completed"
    )
    step_indices = [i for i, e in enumerate(events) if e.event_type == "attack_sequence_step"]
    assert step_indices
    assert max(step_indices) < completion_index
    completion = cast(dict[str, JsonValue], events[completion_index].payload)
    sequence = completed_attack_sequence(
        event_records=events, sequence_id=cast(str, completion["sequence_id"])
    )
    assert sequence.is_complete
    assert sequence.source_phase is phase
    assert sequence.deferred_mortal_wounds == ()
    participants = next(e for e in events if e.event_type == "attack_sequence_models_attacked")
    body = cast(dict[str, JsonValue], participants.payload)
    assert body["model_instance_ids"] == sorted(
        {pool.attacker_model_instance_id for pool in sequence.attack_pools}
    )
    assert body["attack_phase"] == phase.value
    for pool in sequence.attack_pools:
        wargear = next(
            item
            for item in session.lifecycle.config.army_catalog.wargear
            if item.wargear_id == pool.wargear_id
        )
        assert pool.weapon_profile == wargear.weapon_profile_by_id(pool.weapon_profile_id)
        assert (pool.weapon_profile.range_profile.kind is RangeProfileKind.MELEE) == (
            phase is BattlePhase.FIGHT
        )
        assert pool.target_unit_instance_id == "army-beta:enemy"
        assert pool.attacks == pool.weapon_profile.attack_profile.resolve_value(18) == 18
        assert model_has_attacked_this_phase(
            event_records=events,
            model_instance_id=pool.attacker_model_instance_id,
            battle_round=cast(int, body["battle_round"]),
            active_player_id=cast(str, body["active_player_id"]),
            phase=cast(str, body["phase"]),
        )
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order97-attack")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("roll_type", ["unit_hazard", "hazardous_test"])
def test_hazard_requests_use_one_d6_or_one_explicit_simultaneous_batch(roll_type: str) -> None:
    spec = hazard_roll_spec(reason="Order97 hazard evidence", roll_type=roll_type, actor_id="a")
    assert spec.expression.quantity == 1
    assert spec.expression.sides == 6
    manager = DiceRollManager("order97-hazard")
    single = manager.roll_fixed(spec, [2])
    assert single.current_values == (2,)
    assert failed_hazard_roll_indices(single) == (0,)
    batch_spec = hazard_roll_spec(
        reason="Order97 simultaneous hazards", roll_type=roll_type, actor_id="a", quantity=4
    )
    batch = manager.roll_fixed(batch_spec, [1, 2, 3, 6])
    assert batch.current_values == (1, 2, 3, 6)
    assert failed_hazard_roll_indices(batch) == (0, 1)
    rolls = [e for e in manager.event_log.records if e.event_type == "dice_rolled"]
    assert len(rolls) == 2


def test_mixed_infantry_vehicle_hazard_matches_the_specific_faq() -> None:
    unit = mixed_hazard_unit("INFANTRY")
    assert ["VEHICLE" in model.keywords for model in unit.own_models] == [False, False, True]
    assert hazard_mortal_wounds_per_failed_roll(unit) == 1


def test_weaponless_model_completes_a_fight_selection_without_melee_attacks() -> None:
    session = weaponless_fight_session()
    state = session.lifecycle.state
    assert state is not None
    unarmed = state.army_definitions[0].units[0]
    assert all(not model.wargear_ids for model in unarmed.own_models)
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "fight_activation_selected" for e in events)
    assert any(e.event_type == "fight_activation_completed" for e in events)
    assert not any(e.event_type == "attack_sequence_step" for e in events)


@pytest.mark.parametrize("characteristic", ["skill", "strength", "armor_penetration", "damage"])
@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_identical_attack_grouping_separates_each_characteristic(
    characteristic: str, phase: BattlePhase
) -> None:
    lifecycle = lethal_session(phase, sustained=0).lifecycle
    state = lifecycle.state
    assert state is not None
    attacker, target = state.army_definitions[0].units[0], state.army_definitions[1].units[0]
    profile = replace(_first_weapon_profile(lifecycle, attacker), keywords=(), abilities=())
    changed = {
        "skill": replace(
            profile,
            skill=CharacteristicValue.from_raw(
                Characteristic.BALLISTIC_SKILL
                if phase is BattlePhase.SHOOTING
                else Characteristic.WEAPON_SKILL,
                5,
            ),
        ),
        "strength": replace(
            profile, strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 9)
        ),
        "armor_penetration": replace(
            profile,
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -4),
        ),
        "damage": replace(profile, damage_profile=DamageProfile.fixed(9)),
    }[characteristic]
    pool = _attack_pool_for_test(
        attacker=attacker, defender=target, weapon_profile=profile, attacks=1
    )
    copy = replace(pool, weapon_instance_id="order97:second-physical-weapon")
    sequence = AttackSequence.start(
        sequence_id="order97:grouping",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool, copy),
    )
    identical = gathered_attack_groups_for_target(
        target_has_character=target_has_character_for_attack_group(
            state=state, target_unit_instance_id=target.unit_instance_id
        ),
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
    )
    assert len(identical) == 1
    different = gathered_attack_groups_for_target(
        target_has_character=target_has_character_for_attack_group(
            state=state, target_unit_instance_id=target.unit_instance_id
        ),
        attack_sequence=replace(
            sequence, attack_pools=(pool, replace(copy, weapon_profile=changed))
        ),
        target_unit_instance_id=target.unit_instance_id,
    )
    assert len(different) == 2


def test_mixed_damage_finishes_normal_attacks_before_deferred_mortal_wounds() -> None:
    session = psychic_session(
        BattlePhase.SHOOTING,
        psychic=False,
        weapon_profile_transform=lambda profile: replace(
            profile,
            keywords=(WeaponKeyword.TORRENT, WeaponKeyword.DEVASTATING_WOUNDS),
            abilities=(AbilityDescriptor.devastating_wounds(),),
            attack_profile=AttackProfile.fixed(4),
            damage_profile=DamageProfile.fixed(1),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        ),
    )
    # Keep measured helper defaults; renew this real first decision's source identity.
    request = pending_request(session)
    assert request.decision_type == "select_shooting_unit"
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order123-mixed-damage-source-choice-4",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    for _ in range(150):
        if attack_completed(session):
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("Mixed damage attack did not complete.")
    events = session.lifecycle.decision_controller.event_log.records
    normal_indices = [
        i
        for i, e in enumerate(events)
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload["step"] == "damage"
        and isinstance(e.payload["payload"], dict)
        and e.payload["payload"].get("damage_application") is not None
    ]
    mortal_indices = [
        i
        for i, e in enumerate(events)
        if e.event_type == "devastating_wounds_mortal_wounds_applied"
    ]
    assert normal_indices
    assert mortal_indices
    assert max(normal_indices) < min(mortal_indices)
    mortal_applications = [
        cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], events[i].payload)["mortal_wound_application"],
        )
        for i in mortal_indices
    ]
    assert any(application["applications"] for application in mortal_applications)
    for index in normal_indices:
        body = cast(dict[str, JsonValue], events[index].payload)
        details = cast(dict[str, JsonValue], body["payload"])
        application = cast(dict[str, JsonValue], details["damage_application"])
        assert application["damage_kind"] == "normal"
        assert application["requested_damage"] == 1


@pytest.mark.parametrize("split_targets", [False, True])
def test_selected_rules_unit_target_inventory_includes_every_weapon_pool(
    split_targets: bool,
) -> None:
    from tests.phase13b_shooting_declaration_helpers import _phase14l_multi_group_lifecycle

    from warhammer40k_core.engine.attack_sequence_selection import unresolved_target_unit_ids

    lifecycle, units, _ = _phase14l_multi_group_lifecycle(game_id="order97-single-target")
    attacker = units["intercessor-1"]
    first, second = units["enemy-a"], units["enemy-b"]
    profile = _first_weapon_profile(lifecycle, attacker)
    pools = tuple(
        replace(
            _attack_pool_for_test(
                attacker=attacker,
                defender=second if split_targets and index == 2 else first,
                weapon_profile=profile,
                attacks=1,
            ),
            attacker_model_instance_id=model.model_instance_id,
            weapon_instance_id=f"{model.model_instance_id}:rifle",
        )
        for index, model in enumerate(attacker.own_models[:3])
    )
    sequence = AttackSequence.start(
        sequence_id="order97-selected-targets",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=pools,
    )
    targets = unresolved_target_unit_ids(sequence)
    expected = (
        tuple(sorted((first.unit_instance_id, second.unit_instance_id)))
        if split_targets
        else (first.unit_instance_id,)
    )
    assert targets == expected
    assert (len(targets) == 1) is (not split_targets)


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("targetless", [False, True])
@pytest.mark.parametrize("alternate", [False, True])
def test_one_copy_cannot_select_two_profiles_and_exact_request_retries(
    player: str, targetless: bool, alternate: bool
) -> None:
    session = profile_session()
    request = declaration_request(session, player=player)
    weapons = advertised_weapons(request)
    copy_id = weapons[0]["weapon_instance_id"]
    profiles = [weapon for weapon in weapons if weapon["weapon_instance_id"] == copy_id]
    assert len(profiles) == 2
    assert len({weapon["weapon_profile_id"] for weapon in profiles}) == 2
    proposal = profile_proposal(request, profiles, targetless=targetless)
    if targetless:
        # The physical selection rule applies even when just one alternative
        # selects a target; targetless selection still commits that weapon.
        proposal = replace(
            proposal,
            declarations=(
                proposal.declarations[0],
                replace(
                    proposal.declarations[1],
                    target_unit_instance_id="army-beta:enemy"
                    if player == "player-a"
                    else "army-alpha:shooter",
                ),
            ),
        )
    before = session.to_persistence_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d10-invalid-both-profiles",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    body = cast(dict[str, JsonValue], status.payload)
    validation = cast(dict[str, JsonValue], body["proposal_validation"])
    violations = cast(list[dict[str, JsonValue]], validation["violations"])
    assert violations[0]["violation_code"] == "duplicate_weapon_declaration"
    assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
    assert session.to_persistence_payload() == before
    restored, fork = profile_checkpoint(session)
    legal = profile_proposal(request, [profiles[int(alternate)]])
    submit_profile(session, request, legal)
    assert restored.to_persistence_payload() == fork.to_persistence_payload() == before
    pools = finish_profile_attack(session)
    for clone in (restored, fork):
        submit_profile(clone, request, legal)
        assert finish_profile_attack(clone) == pools
        assert clone.to_persistence_payload() == session.to_persistence_payload()
    assert len(pools) == 1
    assert pools[0]["weapon_instance_id"] == copy_id
    assert pools[0]["weapon_profile_id"] == profiles[int(alternate)]["weapon_profile_id"]
    assert pools[0]["attacks"] == 1 + int(alternate)
    profile_checkpoint(session)


@pytest.mark.parametrize("kind", ["copies", "models", "attached", "firing_deck"])
def test_independent_physical_weapons_can_choose_different_profiles(kind: str) -> None:
    session = profile_session(
        copies=2 if kind == "copies" else 1,
        models=2 if kind in {"models", "firing_deck"} else 1,
        attached=kind == "attached",
        firing_deck=kind == "firing_deck",
    )
    request = declaration_request(session, firing_deck=kind == "firing_deck")
    weapons = advertised_weapons(request)
    if kind == "firing_deck":
        weapons = [weapon for weapon in weapons if "firing_deck_source_model_instance_id" in weapon]
    by_copy = {weapon["weapon_instance_id"]: weapon for weapon in weapons}
    copy_ids = list(by_copy)
    assert len(copy_ids) >= 2
    if kind == "attached":
        leader_id = next(
            copy_id
            for copy_id, weapon in by_copy.items()
            if ":leader:" in weapon["model_instance_id"]
        )
        bodyguard_id = next(
            copy_id
            for copy_id, weapon in by_copy.items()
            if ":shooter:" in weapon["model_instance_id"]
        )
        copy_ids = [bodyguard_id, leader_id]
    selected = [
        next(
            weapon
            for weapon in weapons
            if weapon["weapon_instance_id"] == copy_id
            and weapon["weapon_profile_id"].endswith(":d10-alternate") is bool(index)
        )
        for index, copy_id in enumerate(copy_ids[:2])
    ]
    assert selected[0]["weapon_instance_id"] != selected[1]["weapon_instance_id"]
    if kind == "copies":
        assert selected[0]["model_instance_id"] == selected[1]["model_instance_id"]
    elif kind == "firing_deck":
        assert selected[0]["model_instance_id"] == selected[1]["model_instance_id"]
        first_source_model = selected[0].get("firing_deck_source_model_instance_id")
        second_source_model = selected[1].get("firing_deck_source_model_instance_id")
        assert first_source_model is not None
        assert second_source_model is not None
        assert first_source_model != second_source_model
    else:
        assert selected[0]["model_instance_id"] != selected[1]["model_instance_id"]
    proposal = profile_proposal(request, selected)
    restored, fork = profile_checkpoint(session)
    submit_profile(session, request, proposal)
    pools = finish_profile_attack(session)
    assert [pool["weapon_instance_id"] for pool in pools] == [
        weapon["weapon_instance_id"] for weapon in selected
    ]
    assert [pool["weapon_profile_id"] for pool in pools] == [
        weapon["weapon_profile_id"] for weapon in selected
    ]
    assert [pool["attacks"] for pool in pools] == [1, 2]
    for clone in (restored, fork):
        submit_profile(clone, request, proposal)
        assert finish_profile_attack(clone) == pools
        assert clone.to_persistence_payload() == session.to_persistence_payload()
    profile_checkpoint(session)


def test_profile_selection_rejects_stale_wrong_player_and_unadvertised_copy_atomically() -> None:
    session = profile_session()
    request = declaration_request(session)
    proposal = profile_proposal(request, [advertised_weapons(request)[0]])
    invalid_proposals = (
        replace(proposal, proposal_request_id="d10-stale-request"),
        replace(proposal, player_id="player-b"),
        replace(
            proposal,
            declarations=(
                replace(proposal.declarations[0], weapon_instance_id="d10-unadvertised-copy"),
            ),
        ),
    )
    before = session.to_persistence_payload()
    for invalid in invalid_proposals:
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="d10-invalid-context",
            payload=validate_json_value(invalid.to_payload()),
        )
        assert status.status_kind is LifecycleStatusKind.INVALID, status
        assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
        assert session.to_persistence_payload() == before
    submit_profile(session, request, proposal)
    assert len(finish_profile_attack(session)) == 1
    profile_checkpoint(session)
