"""Normal one-bearer activation: irrelevant Movement and meaningful attack Strength."""

from dataclasses import replace
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_generic_source_relevance_helpers import declared_attack_relevance_characteristic
from tests.s25_native_profile_helpers import native_profile_request

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.effects import EffectExpirationKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_characteristic_operations,
    generic_rule_matching_unit_effects,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("kind", ["unused-movement", "meaningful-strength"])
def test_native_generic_sources_follow_actual_attack_consumers(player: str, kind: str) -> None:
    session, request = native_profile_request(player=player, mode=f"activated-own-{kind}-one")
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [w for w in weapons if w["weapon_profile_id"] == first["weapon_profile_id"]]
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-generic-relevance:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert len(sequence.attack_pools) == 2
    pools = sequence.attack_pools
    movement = kind == "unused-movement"
    if movement:
        group = sequence.current_gathered_group
        assert group is not None
        assert group.pool_indices == (0, 1)
        assert group.total_attacks == 4
        assert pools[0].weapon_profile.to_payload() == pools[1].weapon_profile.to_payload()
        assert len({s.rules_json for s in group.native_snapshots}) == 1
        assert len({s.raw_signature_json for s in group.native_snapshots}) == 2
        assert len({s.pool_sha256 for s in group.native_snapshots}) == 2
        assert len({s.source_proof_json for s in group.native_snapshots}) == 2
        for index in range(4):
            current = replace(sequence, attack_index=index).current_pool()
            physical = pools[index // 2]
            assert current.attacker_model_instance_id == physical.attacker_model_instance_id
            assert current.weapon_selection_context == physical.weapon_selection_context
            assert current.selected_weapon_ability_ids == physical.selected_weapon_ability_ids
    else:
        assert sequence.current_gathered_group is None
        assert isinstance(pools[0].weapon_profile.strength, CharacteristicValue)
        assert isinstance(pools[1].weapon_profile.strength, CharacteristicValue)
        assert pools[0].weapon_profile.strength.final == pools[1].weapon_profile.strength.final + 1
        assert pools[0].weapon_profile.to_payload() != pools[1].weapon_profile.to_payload()
    descriptor = declared_attack_relevance_characteristic(kind)
    effects = [
        effect
        for effect in generic_rule_matching_unit_effects(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
        )
        if effect.source_id == descriptor.source_id
    ]
    assert len(effects) == 1
    effect = effects[0]
    assert effect.target_kind is RuleTargetKind.THIS_MODEL
    assert effect.source_model_instance_id == pools[0].attacker_model_instance_id
    assert effect.parameters == (
        {"characteristic": "movement", "delta": 1}
        if movement
        else {"characteristic": "strength", "delta": 1, "weapon_scope": "ranged"}
    )
    persisted = effect.persisting_effect
    assert persisted.owner_player_id == player
    assert persisted.target_unit_instance_ids == (sequence.attacking_unit_instance_id,)
    assert persisted.expiration.expiration_kind is EffectExpirationKind.END_PHASE
    assert persisted.expiration.phase is not None
    assert persisted.expiration.phase.value == "shooting"
    assert persisted.expiration.player_id == player
    assert len(effect.conditions) == 1
    assert effect.conditions[0]["kind"] == "frequency_limit"
    if movement:
        # The actual independent unit-characteristic consumer still sees the effect.
        operations = generic_rule_characteristic_operations(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            characteristic=Characteristic.MOVEMENT,
            model_instance_id=pools[0].attacker_model_instance_id,
        )
        assert len(operations) == 1
        assert operations[0].operand == 1
        assert operations[0].modifier_id == persisted.effect_id
        assert not generic_rule_characteristic_operations(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            characteristic=Characteristic.MOVEMENT,
            model_instance_id=pools[1].attacker_model_instance_id,
        )
    persisted_payload = persisted.to_payload()
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-generic-invalid",
            result_id="s25-generic-invalid",
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(120):
        live_state = session.lifecycle.state
        assert live_state is not None
        if live_state.current_battle_phase is sequence.source_phase:
            assert (
                next(
                    item.to_payload()
                    for item in live_state.persisting_effects
                    if item.effect_id == persisted.effect_id
                )
                == persisted_payload
            )
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        live_state = session.lifecycle.state
        assert live_state is not None
        if live_state.current_battle_phase is sequence.source_phase:
            assert (
                next(
                    item.to_payload()
                    for item in live_state.persisting_effects
                    if item.effect_id == persisted.effect_id
                )
                == persisted_payload
            )
        # Native advancement may also complete Shooting before returning the
        # next request. Authenticate the real boundary below, without submitting
        # another decision after the actual attack completion.
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("S25 generic source relevance did not complete natively.")
    assert_checkpoint(session)
    completed_state = session.lifecycle.state
    assert completed_state is not None
    events = session.lifecycle.decision_controller.event_log.records
    phase_boundaries = [
        (index, event.payload)
        for index, event in enumerate(events)
        if event.event_type == "battle_phase_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("completed_phase") == "shooting"
    ]
    if phase_boundaries:
        assert len(phase_boundaries) == 1
        index, boundary = phase_boundaries[0]
        assert boundary["active_player_id"] == player
        assert boundary["battle_round"] == persisted.started_battle_round
        assert boundary["next_phase"] == "charge"
        assert completed_state.current_battle_phase is BattlePhase.CHARGE
        assert (
            next(
                i
                for i, event in enumerate(events)
                if event.event_type == "attack_sequence_completed"
            )
            < index
        )
        assert not any(
            item.effect_id == persisted.effect_id for item in completed_state.persisting_effects
        )
    else:
        assert completed_state.current_battle_phase is sequence.source_phase
        assert (
            next(
                item.to_payload()
                for item in completed_state.persisting_effects
                if item.effect_id == persisted.effect_id
            )
            == persisted_payload
        )
    activations = [
        event.payload
        for event in events
        if event.event_type == "catalog_any_phase_once_per_battle_ability_activated"
        and isinstance(event.payload, dict)
    ]
    assert len(activations) == 1
    assert activations[0]["source_model_instance_id"] == pools[0].attacker_model_instance_id
    stages: dict[str, list[int]] = {"hit": [], "wound": []}
    for index, event in enumerate(events):
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            for name in stages:
                if spec.get("roll_type") == "attack_sequence." + name:
                    stages[name].append(index)
    assert len(stages["hit"]) == 4
    assert stages["wound"]
    if movement:
        assert max(stages["hit"]) < min(stages["wound"])
