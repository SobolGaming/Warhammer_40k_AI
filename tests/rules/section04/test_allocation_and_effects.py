"""Small real resolver consumers for allocation and attack-specific weapon effects."""

from dataclasses import replace
from typing import cast

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
    AllocatedAttackDamageModifierBinding,
    AllocatedAttackDamageModifierContext,
)
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
)
from warhammer40k_core.engine.attack_sequence_hazardous import (
    _hazardous_roll_spec,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model


def test_allocated_attack_modifier_receives_actual_model_only_at_damage(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    state = combat_state(d, unit, target=target)
    physical = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=unit.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.weapon_profile.profile_id == d.weapon(f"{LORD_EXULTANT}:plasma-pistol", 1).profile_id
    )
    pool = replace(
        attack_pool(unit, target, physical.weapon_profile, physical.wargear_id),
        weapon_instance_id=physical.weapon_instance_id,
    )
    sequence = AttackSequence("allocated", "owner", unit.unit_instance_id, (pool,))
    decisions = DecisionController()
    observed: list[AllocatedAttackDamageModifierContext] = []
    seen_steps: list[list[str]] = []

    def allocated(context: AllocatedAttackDamageModifierContext) -> int:
        observed.append(context)
        seen_steps.append(
            [
                cast(str, cast(dict[str, JsonValue], e.payload)["step"])
                for e in decisions.event_log.records
                if e.event_type == "attack_sequence_step"
            ]
        )
        return -1

    registry = RuntimeModifierRegistry.from_bindings(
        allocated_attack_damage_modifier_bindings=(
            AllocatedAttackDamageModifierBinding(
                "constructed:allocation", "constructed:section04", allocated
            ),
        )
    )
    context_id = "allocated:pool-001:attack-001"
    specs = (
        attack_sequence_hit_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=context_id,
            attacker_player_id="owner",
        ),
        attack_sequence_wound_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=context_id,
            attacker_player_id="owner",
        ),
        saving_throw_roll_spec(
            save_kind=SaveKind.INVULNERABLE,
            player_id="opponent",
            allocated_model_id=target.own_model_ids()[0],
            attack_context_id=context_id,
        ),
    )
    physical_dice = DiceRollManager("physical")
    results = tuple(
        physical_dice.roll_fixed(spec, (value,)).original_result
        for spec, value in zip(specs, (6, 6, 1), strict=True)
    )
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "allocated", event_log=decisions.event_log, injected_results=results
        ),
        runtime_modifier_registry=registry,
    )
    assert status is None
    assert remaining is None
    assert len(observed) == 1
    assert observed[0].allocated_model_instance_id == target.own_model_ids()[0]
    assert observed[0].target_unit_instance_id == target.unit_instance_id
    assert observed[0].current_value == 2
    assert seen_steps[0].index("hit") < seen_steps[0].index("wound")
    assert "damage" not in seen_steps[0]
    updated = model_by_id(state=state, model_instance_id=target.own_model_ids()[0])
    assert updated.wounds_remaining == cast(int, target.own_models[0].wounds_remaining) - 1


def test_constructed_attack_keyword_persists_to_post_attack_hazard_consumer(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    state = combat_state(d, unit, target=target)
    native = d.weapon(f"{LORD_EXULTANT}:bolt-pistol")
    # Explicit Core attack-specific change: bolt pistol is not natively Hazardous.
    modified = replace(native, keywords=(*native.keywords, WeaponKeyword.HAZARDOUS))
    instance = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=unit.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.weapon_profile == native
    )
    pool = replace(
        attack_pool(unit, target, modified, instance.wargear_id),
        weapon_instance_id=instance.weapon_instance_id,
    )
    sequence = AttackSequence("effect-lifetime", "owner", unit.unit_instance_id, (pool,))
    assert not sequence.is_complete
    assert sequence.selected_weapons[0].weapon_profile == modified
    decisions = DecisionController()
    specs = (
        attack_sequence_hit_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id="effect-lifetime:pool-001:attack-001",
            attacker_player_id="owner",
        ),
        _hazardous_roll_spec(attack_sequence=sequence, quantity=1),
    )
    dice = DiceRollManager("physical")
    results = tuple(
        dice.roll_fixed(spec, (value,)).original_result
        for spec, value in zip(specs, (1, 6), strict=True)
    )
    manager = DiceRollManager("effects", event_log=decisions.event_log, injected_results=results)
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=manager,
    )
    assert status is None
    assert remaining is None
    completed = completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence.sequence_id
    )
    completion_event = next(
        e for e in decisions.event_log.records if e.event_type == "attack_sequence_completed"
    )
    status = AttackSequenceCompletedHookRegistry.empty().resolve_completed_sequence(
        AttackSequenceCompletedContext(
            state,
            decisions,
            manager,
            RuntimeModifierRegistry(),
            BattlePhase.SHOOTING,
            completed,
            completion_event.event_id,
        )
    )
    assert status is None
    event = next(
        e for e in decisions.event_log.records if e.event_type == "hazardous_test_resolved"
    )
    payload = cast(dict[str, JsonValue], event.payload)
    assert payload["hazardous_weapon_instance_ids"] == [instance.weapon_instance_id]
    assert payload["hazardous_weapon_profile_ids"] == [native.profile_id]
    assert payload["successful"] is True
    completed = completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence.sequence_id
    )
    assert completed.is_complete
    assert completed.selected_weapons[0].weapon_profile == modified
    events = decisions.event_log.records
    assert max(
        i for i, e in enumerate(events) if e.event_type == "attack_sequence_step"
    ) < events.index(event)
    assert events.index(completion_event) < events.index(event)
    assert WeaponKeyword.HAZARDOUS not in d.weapon(instance.wargear_id).keywords
