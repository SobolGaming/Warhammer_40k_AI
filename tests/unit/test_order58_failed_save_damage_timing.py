from __future__ import annotations

import json

import pytest
from tests.order58_failed_save_damage_timing_helpers import (
    FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE,
    ORDER58_SOURCE_ID,
    defender_wounds,
    isolate_defender_model,
    order58_registry,
    order58_shooting_lifecycle,
    replacement_events,
    resolve_order58_attack,
    typed_replacement_payload,
)
from tests.phase13b_shooting_declaration_helpers import _state

from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
    AllocatedAttackDamageModifierBinding,
    AllocatedAttackDamageModifierContext,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.failed_save_damage_timing import (
    FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID,
    TIMING_POLICY,
    unused_failed_save_damage_replacement,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveOption,
    resolve_saving_throw,
    saving_throw_roll_spec,
)


def test_failed_save_changes_incoming_damage_to_zero_after_the_save() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    starting = defender.own_models[0].wounds_remaining
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=attacker,
        defender=defender,
        sequence_id="order58-failed-save",
        registry=order58_registry(source_unit_instance_id=defender.unit_instance_id),
    )

    events = replacement_events(lifecycle)
    payload = typed_replacement_payload(events[0])
    assert len(events) == 1
    assert payload["replacement_damage"] == 0
    assert payload["timing_source_rule_id"] == FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID
    assert payload["source_id"] == ORDER58_SOURCE_ID
    assert payload["source_unit_instance_id"] == defender.unit_instance_id
    assert defender_wounds(lifecycle, defender) == starting
    assert TIMING_POLICY.applies_after_saving_throw is True
    assert TIMING_POLICY.applies_before_saving_throw is False


def test_successful_save_does_not_replace_incoming_damage() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    starting = defender.own_models[0].wounds_remaining
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=attacker,
        defender=defender,
        sequence_id="order58-successful-save",
        save_value=6,
        registry=order58_registry(source_unit_instance_id=defender.unit_instance_id),
    )

    assert replacement_events(lifecycle) == ()
    assert defender_wounds(lifecycle, defender) == starting


def test_failed_save_without_replacement_inflicts_weapon_damage() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    starting = defender.own_models[0].wounds_remaining
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=attacker,
        defender=defender,
        sequence_id="order58-ordinary-damage",
        damage=1,
    )

    assert replacement_events(lifecycle) == ()
    assert defender_wounds(lifecycle, defender) == starting - 1


def test_failed_save_replacement_is_once_per_turn() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    starting = defender.own_models[0].wounds_remaining
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=attacker,
        defender=defender,
        sequence_id="order58-once-per-turn",
        attacks=2,
        damage=1,
        registry=order58_registry(source_unit_instance_id=defender.unit_instance_id),
    )

    assert len(replacement_events(lifecycle)) == 1
    assert defender_wounds(lifecycle, defender) == starting - 1


def test_allocated_attack_damage_modifier_does_not_run_when_damage_is_replaced() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    observed: list[AllocatedAttackDamageModifierContext] = []

    def allocated_damage_modifier(context: AllocatedAttackDamageModifierContext) -> int:
        observed.append(context)
        return 4

    registry = RuntimeModifierRegistry.from_bindings(
        failed_save_damage_replacement_bindings=order58_registry(
            source_unit_instance_id=defender.unit_instance_id
        ).failed_save_damage_replacement_bindings,
        allocated_attack_damage_modifier_bindings=(
            AllocatedAttackDamageModifierBinding(
                modifier_id="order58-allocated-damage-modifier",
                source_id="order58-allocated-damage-source",
                handler=allocated_damage_modifier,
            ),
        ),
    )
    starting = defender.own_models[0].wounds_remaining
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=attacker,
        defender=defender,
        sequence_id="order58-skip-allocated-modifier",
        registry=registry,
    )

    assert observed == []
    assert defender_wounds(lifecycle, defender) == starting
    assert len(replacement_events(lifecycle)) == 1


def test_nonzero_failed_save_replacement_fails_closed() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]

    with pytest.raises(GameLifecycleError, match="incoming attack Damage to zero"):
        resolve_order58_attack(
            lifecycle=lifecycle,
            attacker=attacker,
            defender=defender,
            sequence_id="order58-nonzero-replacement",
            registry=order58_registry(
                source_unit_instance_id=defender.unit_instance_id,
                replacement_damage=1,
            ),
        )


def test_unused_replacement_rejects_a_successful_saving_throw() -> None:
    lifecycle, units = order58_shooting_lifecycle()
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    isolate_defender_model(lifecycle, defender)
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender.own_models[0].model_instance_id,
        attack_context_id="order58-owner:pool-001:attack-001",
    )
    saving_throw = resolve_saving_throw(
        options=(SaveOption(SaveKind.ARMOUR, 3, 3, 0),),
        roll_state=DiceRollManager("order58-owner").roll_fixed(spec, [6]),
    )
    assert saving_throw.successful is True
    with pytest.raises(GameLifecycleError, match="after a failed save"):
        unused_failed_save_damage_replacement(
            state=_state(lifecycle),
            event_records=lifecycle.decision_controller.event_log.records,
            runtime_modifiers=order58_registry(source_unit_instance_id=defender.unit_instance_id),
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            allocated_model_instance_id=defender.own_models[0].model_instance_id,
            source_phase=BattlePhase.SHOOTING,
            saving_throw=saving_throw,
        )


def test_failed_save_replacement_survives_adapter_restore_and_viewer_events() -> None:
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession

    lifecycle, units = order58_shooting_lifecycle(game_id="order58-restore")
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    starting = defender.own_models[0].wounds_remaining
    resolve_order58_attack(
        lifecycle=lifecycle,
        attacker=attacker,
        defender=defender,
        sequence_id="order58-restore",
        registry=order58_registry(source_unit_instance_id=defender.unit_instance_id),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    restored_state = GameState.from_payload(json.loads(json.dumps(_state(lifecycle).to_payload())))
    restored_events = tuple(
        EventRecord.from_payload(json.loads(json.dumps(event.to_payload())))
        for event in replacement_events(lifecycle)
    )

    def viewer_count(viewer_player_id: str) -> int:
        page = session.events_since(
            cursor=EventStreamCursor(),
            viewer_player_id=viewer_player_id,
        )
        return sum(
            1
            for event in page["events"]
            if event["event_type"] == FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE
        )

    assert defender_wounds(lifecycle, defender) == starting
    assert (
        model_by_id(
            state=restored_state,
            model_instance_id=defender.own_models[0].model_instance_id,
        ).wounds_remaining
        == starting
    )
    assert len(replacement_events(lifecycle)) == 1
    assert len(restored_events) == 1
    assert typed_replacement_payload(restored_events[0])["timing_source_rule_id"] == (
        FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID
    )
    assert viewer_count("player-a") == 1
    assert viewer_count("player-b") == 1
    assert session.view(viewer_player_id="player-a")["game_id"] == "order58-restore"
    assert session.view(viewer_player_id="player-b")["game_id"] == "order58-restore"
