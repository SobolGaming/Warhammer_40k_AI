"""Source-owner controls over real native pools and explicitly analytical bindings.

These counterfactual pure queries do not claim normal facade/provider execution
for the analytical bindings. Native positive execution is proved separately.
"""

from dataclasses import replace
from typing import cast

import pytest
from tests.d10_profile_helpers import (
    advertised_weapons,
    declaration_request,
    profile_proposal,
    profile_session,
    submit_profile,
)
from tests.s25_gathering_helpers import native_two_bearer_inputs

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.attack_gathering_dependencies import AttackGatheringDependency
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.native_attack_gathering import (
    native_gathered_attack_groups_for_target,
)
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    RuntimeModifierRegistry,
    SaveOptionModifierBinding,
    WoundRollModifierBinding,
)


@pytest.fixture(scope="module")
def inputs() -> tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry]:
    return native_two_bearer_inputs()


def group_count(
    inputs: tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry],
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence | None = None,
) -> int:
    session, base, _ = inputs
    state = session.lifecycle.state
    assert state is not None
    before = session.to_persistence_payload()
    groups = native_gathered_attack_groups_for_target(
        state=state,
        registry=registry,
        attack_sequence=base if sequence is None else sequence,
        target_unit_instance_id=base.attack_pools[0].target_unit_instance_id,
        target_has_character=False,
        has_custom_callbacks=False,
    )
    assert session.to_persistence_payload() == before
    return len(groups)


@pytest.mark.parametrize("family", ["hit", "wound"])
@pytest.mark.parametrize("bearer_specific", [False, True])
def test_equal_applicability_gathers_and_real_bearer_modifier_difference_separates(
    inputs: tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry],
    family: str,
    bearer_specific: bool,
) -> None:
    _, sequence, registry = inputs
    first_model = sequence.attack_pools[0].attacker_model_instance_id
    if family == "hit":
        binding = HitRollModifierBinding(
            "analytical:s25-hit",
            "analytical:s25-source",
            lambda context: int(
                not bearer_specific or context.attacker_model_instance_id == first_model
            ),
        )
        registry = replace(
            registry, hit_roll_modifier_bindings=(*registry.hit_roll_modifier_bindings, binding)
        )
    else:
        wound_binding = WoundRollModifierBinding(
            "analytical:s25-wound",
            "analytical:s25-source",
            lambda context: int(
                not bearer_specific or context.attacker_model_instance_id == first_model
            ),
        )
        registry = replace(
            registry,
            wound_roll_modifier_bindings=(*registry.wound_roll_modifier_bindings, wound_binding),
        )
    assert group_count(inputs, registry) == (2 if bearer_specific else 1)


def test_shared_target_only_provider_has_no_physical_bearer_veto(
    inputs: tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry],
) -> None:
    _, _, registry = inputs
    binding = SaveOptionModifierBinding(
        modifier_id="analytical:s25-target-save",
        source_id="analytical:s25-target-source",
        handler=lambda context: context.save_options,
        gathering_dependency=AttackGatheringDependency.TARGET_ONLY,
    )
    known = replace(
        registry, save_option_modifier_bindings=(*registry.save_option_modifier_bindings, binding)
    )
    assert group_count(inputs, known) == 1
    # Missing dependency proof remains explicitly unresolved, never support credit.
    unknown = replace(binding, gathering_dependency=AttackGatheringDependency.UNKNOWN)
    unproven = replace(
        registry, save_option_modifier_bindings=(*registry.save_option_modifier_bindings, unknown)
    )
    assert group_count(inputs, unproven) == 2


@pytest.mark.parametrize(
    "characteristic", [Characteristic.STRENGTH, Characteristic.ARMOR_PENETRATION]
)
def test_different_operative_characteristics_remain_separate(
    inputs: tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry],
    characteristic: Characteristic,
) -> None:
    _, sequence, registry = inputs
    physical = sequence.attack_pools[1]
    profile = (
        replace(
            physical.weapon_profile,
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 7),
        )
        if characteristic is Characteristic.STRENGTH
        else replace(
            physical.weapon_profile,
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -2),
        )
    )
    changed = replace(
        sequence, attack_pools=(sequence.attack_pools[0], replace(physical, weapon_profile=profile))
    )
    assert group_count(inputs, registry, changed) == 2


def test_native_same_bearer_subgroup_keeps_each_actual_equipped_copy(
    inputs: tuple[LocalGameSession, AttackSequence, RuntimeModifierRegistry],
) -> None:
    # The preconfigured D10 root equips two real copies before facade use.
    session = profile_session(copies=2, models=2)
    request = declaration_request(session)
    weapons = advertised_weapons(request)
    matching = [
        weapon
        for weapon in weapons
        if weapon["weapon_profile_id"] == weapons[0]["weapon_profile_id"]
    ]
    first_model = matching[0]["model_instance_id"]
    first = [weapon for weapon in matching if weapon["model_instance_id"] == first_model]
    other = next(weapon for weapon in matching if weapon["model_instance_id"] != first_model)
    assert len(first) == 2
    submit_profile(session, request, profile_proposal(request, [*first, other]))
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    original = state.shooting_phase_state.attack_sequence
    assert original is not None
    sequence = AttackSequence.start(
        sequence_id="s25:actual-copy-query",
        attacker_player_id=original.attacker_player_id,
        attacking_unit_instance_id=original.attacking_unit_instance_id,
        attack_pools=original.attack_pools,
    )
    registry = replace(
        inputs[2],
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                "analytical:s25-copy-hit",
                "analytical:s25-copy-source",
                lambda context: int(context.attacker_model_instance_id == first_model),
            ),
        ),
    )
    target = original.attack_pools[0].target_unit_instance_id
    groups = native_gathered_attack_groups_for_target(
        state=state,
        registry=registry,
        attack_sequence=sequence,
        target_unit_instance_id=target,
        target_has_character=False,
        has_custom_callbacks=False,
    )
    assert len(groups) == 2
    group = next(group for group in groups if len(group.pool_indices) == 2)
    selected = sequence.with_selected_target_unit(target).with_current_gathered_group(group)
    assert group.native_snapshots
    indices = [
        index
        for contribution in group.contributions
        for index in [contribution.pool_index] * contribution.attacks
    ]
    for index, physical_index in enumerate(indices):
        physical = original.attack_pools[physical_index]
        current = replace(selected, attack_index=index).current_pool()
        assert current.weapon_instance_id == physical.weapon_instance_id
        assert current.attacker_model_instance_id == physical.attacker_model_instance_id
        assert current.weapon_profile_id == physical.weapon_profile_id
    assert cast(dict[str, JsonValue], selected.to_payload())["current_gathered_group"] is not None
