"""Fixed Damage has no roll consumer, despite real optional physical sources."""

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_fixed_damage_relevance_helpers import declared_fixed_damage_roll_ability
from tests.s25_native_profile_helpers import native_profile_request

from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.effects import EffectExpirationKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_matching_unit_effects,
)
from warhammer40k_core.engine.native_attack_gathering import (
    _current_applicable_rules,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.native_gathering_permission_relevance import (
    unused_fixed_damage_roll_sources,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("qualified_roll", [False, True])
@pytest.mark.parametrize("bearers", [1, 2])
def test_native_fixed_damage_excludes_only_unused_roll_sources(
    player: str, qualified_roll: bool, bearers: int
) -> None:
    qualifier = "qualified" if qualified_roll else "canonical"
    count = "one" if bearers == 1 else "two"
    session, request = native_profile_request(
        player=player, mode=f"activated-own-fixed-damage-roll-{qualifier}-{count}"
    )
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
        result_id="s25-fixed-damage-relevance:declaration",
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
    group = sequence.current_gathered_group
    assert group is not None
    assert group.pool_indices == (0, 1)
    assert group.total_attacks == 4
    assert pools[0].weapon_profile.to_payload() == pools[1].weapon_profile.to_payload()
    assert pools[0].weapon_profile.damage_profile.fixed_damage == 1
    assert pools[0].weapon_profile.damage_profile.dice_expression is None
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
    descriptor = declared_fixed_damage_roll_ability(qualified_roll=qualified_roll)
    effects = [
        effect
        for effect in generic_rule_matching_unit_effects(
            state=state,
            unit_instance_id=sequence.attacking_unit_instance_id,
            effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        )
        if effect.source_id == descriptor.source_id
    ]
    assert len(effects) == bearers
    assert {e.source_model_instance_id for e in effects} == {
        pool.attacker_model_instance_id for pool in pools[:bearers]
    }
    for effect in effects:
        assert effect.target_kind is RuleTargetKind.THIS_MODEL
        assert effect.parameters == {
            "roll_type": "attack_sequence.damage" if qualified_roll else "damage",
            "delta": 1,
        }
        persisted = effect.persisting_effect
        assert persisted.owner_player_id == player
        assert persisted.target_unit_instance_ids == (sequence.attacking_unit_instance_id,)
        assert persisted.expiration.expiration_kind is EffectExpirationKind.END_PHASE
        assert persisted.expiration.phase is not None
        assert persisted.expiration.phase.value == "shooting"
        assert persisted.expiration.player_id == player
        assert len(effect.conditions) == 1
        assert effect.conditions[0]["kind"] == "frequency_limit"
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    registry = bundle.runtime_modifier_registry
    target_view = rules_unit_view_by_id(state=state, unit_instance_id=target)
    for index, snapshot in enumerate(group.native_snapshots):
        assert set(json.loads(snapshot.source_proof_json)) == {"source_proof_sha256"}
        assert set(json.loads(snapshot.rules_json)) == {"applicable_rules_sha256"}
        comparison, raw = _current_applicable_rules(
            state=state,
            registry=registry,
            sequence=sequence,
            pool=pools[index],
            target_has_character="CHARACTER" in target_view.keywords,
        )
        matched = [
            row
            for row in cast(list[dict[str, JsonValue]], raw["generic_applicable_sources"])
            if row["source_id"] == descriptor.source_id
        ]
        assert len(matched) == (1 if index < bearers else 0)
        assert raw.get("unused_fixed_damage_roll_sources_excluded_from_comparison", []) == matched
        assert not any(
            row["source_id"] == descriptor.source_id
            for row in cast(list[dict[str, JsonValue]], comparison["generic_applicable_sources"])
        )
        assert comparison["damage_modifiers"] == raw["damage_modifiers"] == []
    assert len(unused_fixed_damage_roll_sources(tuple(effects), pool=pools[0])) == bearers
    unknown_parameters: tuple[dict[str, JsonValue], ...] = (
        {"roll_type": "damage", "delta": True},
        {"roll_type": "damage", "delta": "unknown"},
        {"roll_type": 1, "delta": 1},
        {"roll_type": "unknown", "delta": 1},
        {"roll_type": "hit", "delta": 1},
        {"roll_type": "", "delta": 1},
        {"roll_type": "  ", "delta": 1},
        {"delta": 1},
    )
    for effect in effects:
        for parameters in unknown_parameters:
            # Pure comparison input only; no authoritative state/effect mutation.
            assert not unused_fixed_damage_roll_sources(
                (replace(effect, parameters=parameters),), pool=pools[0]
            )
    persisted = effects[0].persisting_effect
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
    assert len(activations) == bearers
    assert {cast(str, a["source_model_instance_id"]) for a in activations} == {
        pool.attacker_model_instance_id for pool in pools[:bearers]
    }
    stages: dict[str, list[int]] = {"hit": [], "wound": []}
    for index, event in enumerate(events):
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            for name in stages:
                if spec.get("roll_type") == "attack_sequence." + name:
                    stages[name].append(index)
    assert len(stages["hit"]) == 4
    assert stages["wound"]
    assert max(stages["hit"]) < min(stages["wound"])
    assert not any(
        event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and "damage" in cast(str, cast(dict[str, JsonValue], event.payload["spec"])["roll_type"])
        for event in events
    )
