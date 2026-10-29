"""Core post-roll damage change partitions at the real attack resolver."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
)
from warhammer40k_core.core.weapon_profiles import DamageProfile, WeaponProfile
from warhammer40k_core.engine.attack_sequence import (
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_post_roll import (
    apply_post_roll_attack_pool_decision,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.post_roll_weapon_profile_modifiers import (
    PostRollWeaponProfileModifierBinding,
    PostRollWeaponProfileModifierContext,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@pytest.mark.parametrize("reverse", [False, True])
def test_modified_wounds_form_pools_and_active_player_chooses_order(
    section05_definitions: Section02Definitions, reverse: bool
) -> None:
    state, target, sequence = native_sequence(section05_definitions, attacks=2)

    def on_critical(context: PostRollWeaponProfileModifierContext) -> WeaponProfile:
        return (
            replace(context.weapon_profile, damage_profile=DamageProfile.fixed(2))
            if context.wound_roll.critical
            else context.weapon_profile
        )

    registry = RuntimeModifierRegistry.from_bindings(
        post_roll_weapon_profile_modifier_bindings=(
            PostRollWeaponProfileModifierBinding(
                "constructed:s05:critical-damage",
                "constructed:s05:critical-damage",
                on_critical,
            ),
        )
    )
    decisions = DecisionController()
    fixed = fixed_sequence_dice(sequence, target, (6, 6), (4, 6), (1, 1))
    if reverse:
        fixed = (*fixed[:-2], fixed[-1], fixed[-2])
    dice = DiceRollManager("s05", event_log=decisions.event_log, injected_results=fixed)
    remaining, allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice,
        runtime_modifier_registry=registry,
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "select_post_roll_attack_pool"
    assert request.actor_id == "owner"
    assert len(request.options) == 2
    assert remaining.post_roll_attack_pools is not None
    assert len(remaining.post_roll_attack_pools.unresolved_pools) == 2
    assert not [
        r
        for r in payloads(decisions, "dice_rolled")
        if str(cast(dict[str, JsonValue], r["spec"])["roll_type"]).startswith(
            "attack_sequence.save"
        )
    ]
    result = DecisionResult.for_request(
        result_id="s05:pool-choice",
        request=request,
        selected_option_id=request.options[int(reverse)].option_id,
    )
    decisions.submit_result(result)
    selected = apply_post_roll_attack_pool_decision(
        decisions=decisions, attack_sequence=remaining, result=result
    )
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=selected,
        already_allocated_model_ids=allocated,
        dice_manager=dice,
        runtime_modifier_registry=registry,
    )
    assert status is None
    assert remaining is None
    steps = payloads(decisions, "attack_sequence_step")
    tail = [p for p in steps if p["step"] in ("save", "damage")]
    assert [p["step"] for p in tail] == ["save", "damage", "save", "damage"]
    assert tail[0]["attack_context_id"] == tail[1]["attack_context_id"]
    assert tail[2]["attack_context_id"] == tail[3]["attack_context_id"]
    damage = [
        cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], p["payload"])["damage_application"],
        )["requested_damage"]
        for p in tail
        if p["step"] == "damage"
    ]
    assert sorted(cast(list[int], damage)) == [1, 2]
    assert damage == ([2, 1] if reverse else [1, 2])
    assert model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds == 2
