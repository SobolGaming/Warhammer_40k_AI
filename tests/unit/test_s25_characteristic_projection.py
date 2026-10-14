"""Normal admitted characteristic sources follow actual attack consumers and roles."""

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_characteristic_projection_helpers import (
    declared_projection_ability,
    projection_shooting_request,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.effects import EffectExpirationKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_characteristic_operations,
    generic_rule_matching_unit_effects,
)
from warhammer40k_core.engine.native_attack_gathering import (
    _current_applicable_rules,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.native_gathering_permission_relevance import (
    unused_attack_characteristic_sources,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind

_UNUSED_RANGED = (
    Characteristic.MOVEMENT,
    Characteristic.LEADERSHIP,
    Characteristic.OBJECTIVE_CONTROL,
    Characteristic.TOUGHNESS,
    Characteristic.SAVE,
    Characteristic.INVULNERABLE_SAVE,
    Characteristic.WOUNDS,
    Characteristic.WEAPON_SKILL,
)
_USED_RANGED = (
    Characteristic.BALLISTIC_SKILL,
    Characteristic.STRENGTH,
    Characteristic.ATTACKS,
    Characteristic.ARMOR_PENETRATION,
    Characteristic.DAMAGE,
    Characteristic.RANGE,
)


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("characteristic", [*_UNUSED_RANGED, *_USED_RANGED])
def test_native_characteristic_sources_project_to_real_attack_subjects(
    player: str, characteristic: Characteristic
) -> None:
    session, request = projection_shooting_request(player=player, characteristic=characteristic)
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [w for w in weapons if w["weapon_profile_id"] == first["weapon_profile_id"]]
    assert len(matching) >= 2
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    state = session.lifecycle.state
    assert state is not None
    cp_before = state.command_point_total(player)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-characteristic-projection:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert len(sequence.attack_pools) == 2
    pools = sequence.attack_pools
    assert pools[0].target_visible_model_ids == pools[1].target_visible_model_ids
    assert pools[0].target_in_range_model_ids == pools[1].target_in_range_model_ids
    unused = characteristic in _UNUSED_RANGED
    quantity_consumed = characteristic is Characteristic.ATTACKS
    comparison_unused = unused or quantity_consumed
    group = sequence.current_gathered_group
    if comparison_unused:
        assert group is not None
        assert group.pool_indices == (0, 1)
        assert group.total_attacks == (5 if quantity_consumed else 4)
        if quantity_consumed:
            assert [pool.attacks for pool in pools] == [3, 2]
            assert pools[0].weapon_profile.to_payload() != pools[1].weapon_profile.to_payload()
        else:
            assert pools[0].weapon_profile.to_payload() == pools[1].weapon_profile.to_payload()
        assert len({s.rules_json for s in group.native_snapshots}) == 1
        assert len({s.raw_signature_json for s in group.native_snapshots}) == 2
        assert len({s.pool_sha256 for s in group.native_snapshots}) == 2
        assert len({s.source_proof_json for s in group.native_snapshots}) == 2
        for index in range(group.total_attacks):
            current = replace(sequence, attack_index=index).current_pool()
            physical = pools[0 if index < pools[0].attacks else 1]
            assert current.attacker_model_instance_id == physical.attacker_model_instance_id
            assert current.weapon_selection_context == physical.weapon_selection_context
            assert current.selected_weapon_ability_ids == physical.selected_weapon_ability_ids
    else:
        assert group is None
        assert pools[0].weapon_profile.to_payload() != pools[1].weapon_profile.to_payload()
    descriptor = declared_projection_ability(characteristic)
    effects = tuple(
        effect
        for effect in generic_rule_matching_unit_effects(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
        )
        if effect.source_id == descriptor.source_id
    )
    assert len(effects) == 1
    effect = effects[0]
    assert effect.target_kind is RuleTargetKind.THIS_MODEL
    assert effect.source_model_instance_id == pools[0].attacker_model_instance_id
    delta = -1 if characteristic is Characteristic.ARMOR_PENETRATION else 1
    assert effect.parameters == {"characteristic": characteristic.value, "delta": delta}
    persisted = effect.persisting_effect
    assert persisted.owner_player_id == player
    assert persisted.target_unit_instance_ids == (sequence.attacking_unit_instance_id,)
    assert persisted.expiration.expiration_kind is EffectExpirationKind.END_PHASE
    assert persisted.expiration.phase is BattlePhase.SHOOTING
    assert persisted.expiration.player_id == player
    assert len(effect.conditions) == 1
    assert effect.conditions[0]["kind"] == "frequency_limit"
    parameters = cast(dict[str, JsonValue], effect.conditions[0]["parameters"])
    assert parameters == {
        "activation_kind": "optional_ability_use",
        "max_uses": 1,
        "scope": "battle",
        "usage_subject": "this_model",
    }
    if characteristic in _UNUSED_RANGED[:-1]:
        # Actual unit-operation authority survives comparison projection.
        operations = generic_rule_characteristic_operations(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            characteristic=characteristic,
            model_instance_id=pools[0].attacker_model_instance_id,
        )
        assert len(operations) == 1
        assert operations[0].operand == 1
        assert operations[0].modifier_id == persisted.effect_id
        assert not generic_rule_characteristic_operations(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            characteristic=characteristic,
            model_instance_id=pools[1].attacker_model_instance_id,
        )
    registry = session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry  # pyright: ignore[reportPrivateUsage]
    target_view = rules_unit_view_by_id(state=state, unit_instance_id=target)
    for index, pool in enumerate(pools):
        comparison, raw = _current_applicable_rules(
            state=state,
            registry=registry,
            sequence=sequence,
            pool=pool,
            target_has_character="CHARACTER" in target_view.keywords,
        )
        matched = [
            row
            for row in cast(list[dict[str, JsonValue]], raw["generic_applicable_sources"])
            if row["source_id"] == descriptor.source_id
        ]
        assert len(matched) == (1 if index == 0 else 0)
        excluded = raw.get("unused_characteristic_sources_excluded_from_comparison", [])
        assert excluded == (matched if comparison_unused else [])
        retained = [
            row
            for row in cast(list[dict[str, JsonValue]], comparison["generic_applicable_sources"])
            if row["source_id"] == descriptor.source_id
        ]
        assert bool(retained) is (index == 0 and not comparison_unused)
    if comparison_unused:
        assert len(unused_attack_characteristic_sources(effects, pool=pools[0])) == 1
    for defense in (
        Characteristic.TOUGHNESS,
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
        Characteristic.WOUNDS,
    ):
        # Pure comparison copies only: target defense remains meaningful; no state injection.
        target_effect = replace(
            effect, role="target", parameters={"characteristic": defense.value, "delta": 1}
        )
        assert not unused_attack_characteristic_sources((target_effect,), pool=pools[0])
    unknown_parameters: tuple[dict[str, JsonValue], ...] = (
        {"characteristic": "leadership", "delta": True},
        {"characteristic": "leadership", "delta": "unknown"},
        {"characteristic": "unknown", "delta": 1},
        {"characteristic": "detection_range", "delta": 1},
        {"characteristic": 1, "delta": 1},
        {"delta": 1},
    )
    for probe_parameters in unknown_parameters:
        assert not unused_attack_characteristic_sources(
            (replace(effect, parameters=probe_parameters),), pool=pools[0]
        )
    assert not unused_attack_characteristic_sources(
        (replace(effect, effect_kind=RuleEffectKind.SET_CHARACTERISTIC),), pool=pools[0]
    )
    persisted_payload = persisted.to_payload()
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-projection:invalid",
            result_id="s25-projection:invalid",
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(120):
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        assert pending is not None
        live = session.lifecycle.state
        assert live is not None
        if live.current_battle_phase is sequence.source_phase:
            assert (
                next(
                    e.to_payload()
                    for e in live.persisting_effects
                    if e.effect_id == persisted.effect_id
                )
                == persisted_payload
            )
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("Projection attack did not complete through native continuation.")
    assert_checkpoint(session)
    completed = session.lifecycle.state
    assert completed is not None
    assert completed.command_point_total(player) == cp_before
    events = session.lifecycle.decision_controller.event_log.records
    activations = [
        e.payload
        for e in events
        if e.event_type == "catalog_any_phase_once_per_battle_ability_activated"
        and isinstance(e.payload, dict)
    ]
    assert len(activations) == 1
    assert activations[0]["source_model_instance_id"] == pools[0].attacker_model_instance_id
    if completed.current_battle_phase is sequence.source_phase:
        assert (
            next(
                e.to_payload()
                for e in completed.persisting_effects
                if e.effect_id == persisted.effect_id
            )
            == persisted_payload
        )
    else:
        assert completed.current_battle_phase is BattlePhase.CHARGE
        assert not any(e.effect_id == persisted.effect_id for e in completed.persisting_effects)
    stages = {
        name: [
            i
            for i, e in enumerate(events)
            if e.event_type == "dice_rolled"
            and isinstance(e.payload, dict)
            and cast(dict[str, JsonValue], e.payload["spec"]).get("roll_type")
            == "attack_sequence." + name
        ]
        for name in ("hit", "wound")
    }
    assert len(stages["hit"]) == (5 if characteristic is Characteristic.ATTACKS else 4)
    assert stages["wound"]
    if comparison_unused:
        assert max(stages["hit"]) < min(stages["wound"])
    assert group is None or all(
        set(json.loads(s.rules_json)) == {"applicable_rules_sha256"} for s in group.native_snapshots
    )
