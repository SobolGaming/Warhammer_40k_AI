"""Real gathered dice retain callback authority; this is a constructed hook fixture."""

from dataclasses import replace

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
    _shooting_lifecycle,
    _state,
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceEvent,
    AttackSequenceHooks,
    AttackSequenceStep,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.gathered_attack_dice import resolve_gathered_attack_dice
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@pytest.mark.parametrize("custom_callback", [False, True])
def test_gathered_wound_results_respect_effect_changes_from_custom_callbacks(
    custom_callback: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, defender = units["intercessor-1"], units["enemy"]
    profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 100),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="order135-wound-callback",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker, defender=defender, weapon_profile=profile, attacks=2
            ),
        ),
    )
    contexts = tuple(replace(sequence, attack_index=i).attack_context_id() for i in range(2))
    manager = DiceRollManager(
        state.game_id,
        event_log=lifecycle.decision_controller.event_log,
        injected_results=tuple(
            _fixed_roll_result(
                roll_id=f"order135-wound-callback:{index}",
                spec=attack_sequence_wound_roll_spec(
                    weapon_profile_id=profile.profile_id,
                    attack_context_id=context,
                    attacker_player_id="player-a",
                ),
                value=3,
            )
            for index, context in enumerate(contexts)
        ),
    )
    observed: list[AttackSequenceEvent] = []

    def apply_effect_after_first_wound(event: AttackSequenceEvent) -> AttackSequenceEvent:
        observed.append(event)
        if event.step is AttackSequenceStep.WOUND and event.attack_context_id == contexts[0]:
            state.record_persisting_effect(
                generic_effect(
                    effect_id="order135:callback-critical-wound",
                    owner_player_id="player-a",
                    target_unit_instance_ids=(attacker.unit_instance_id,),
                    target_kind="this_unit",
                    effect_kind="set_contextual_status",
                    parameters={
                        "attack_role": "attacker",
                        "critical_threshold": 3,
                        "roll_type": "wound",
                        "status": "critical_wound_threshold",
                    },
                )
            )
        return event

    wounded, status = resolve_gathered_attack_dice(
        state=state,
        decisions=lifecycle.decision_controller,
        manager=manager,
        attack_sequence=sequence,
        hooks=AttackSequenceHooks(
            handlers=(apply_effect_after_first_wound,) if custom_callback else ()
        ),
        stratagem_index=None,
        stratagem_cost_modifier_registry=None,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status is None
    assert [row["attack_context_id"] for _, row in wounded] == list(contexts)
    assert [row["wound_roll"]["unmodified_roll"] for _, row in wounded] == [3, 3]
    assert [row["wound_roll"]["critical_threshold"] for _, row in wounded] == (
        [6, 3] if custom_callback else [6, 6]
    )
    assert [row["wound_roll"]["critical"] for _, row in wounded] == [False, custom_callback]
    physical = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "dice_rolled"
    ]
    assert len(physical) == 2
    assert len({event.event_id for event in physical}) == 2
    assert len([event for event in observed if event.step is AttackSequenceStep.WOUND]) == (
        2 if custom_callback else 0
    )
