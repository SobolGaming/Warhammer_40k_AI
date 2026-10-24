"""06.02/06.02.01: real native attacks with an explicit source-permission input."""

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import fixed_sequence_dice, native_sequence, payloads, resolve
from warhammer40k_core.engine.additional_attack_mortal_permissions import (
    additional_attack_mortal_permission_effect,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.event_log import JsonValue


@pytest.mark.parametrize("saves", [(1, 1), (6, 1), (6, 6)])
def test_normal_damage_precedes_additional_mortals_and_keeps_attack_identity(
    section06_definitions: Section02Definitions,
    saves: tuple[int, int],
) -> None:
    state, target, sequence = native_sequence(section06_definitions, attacks=2)
    pool = sequence.attack_pools[0]
    # Authenticated existing provider descriptor; tests Core permission consumption,
    # not named faction activation or native bolt-pistol additional mortal text.
    source = (
        "gw-11e-phase17e-exact-faction-subrules-2026-27:bridge-source-row:Enhancements:000009777003"
    )
    state.record_persisting_effect(
        additional_attack_mortal_permission_effect(
            state=state,
            effect_id="s06:additional",
            source_rule_id=source,
            source_model_instance_id=pool.attacker_model_instance_id,
            occasion_id="s06:provider-authorized",
            weapon_scope="all",
            mortal_wounds=1,
        )
    )
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6, 6), (6, 6), saves)
    )
    assert remaining is None
    assert status is None
    applied = payloads(decisions, "additional_attack_mortal_wounds_applied")
    assert len(applied) == 2
    damage = [p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "damage"]
    applications = [cast(dict[str, JsonValue], p["payload"])["damage_application"] for p in damage]
    normal = [cast(dict[str, JsonValue], a) for a in applications if a is not None]
    assert len(normal) == saves.count(1)
    assert all(
        a["requested_damage"] == a["wounds_lost"] == 1 and a["damage_kind"] == "normal"
        for a in normal
    )
    assert pool.weapon_profile.damage_profile.fixed_damage == 1
    assert (
        model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds
        == 5 - saves.count(1) - 2
    )
    events = decisions.event_log.records
    normal_indices = [
        i
        for i, e in enumerate(events)
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload["step"] == "damage"
    ]
    mortal_indices = [
        i for i, e in enumerate(events) if e.event_type == "mortal_wound_model_allocated"
    ]
    assert len(mortal_indices) == 2
    assert all(n < m for n in normal_indices for m in mortal_indices)
    assert [a["attack_context_ids"] for a in applied] == [
        ["s05:pool-001:attack-001"],
        ["s05:pool-001:attack-002"],
    ]
    for a in applied:
        assert a["source_rule_id"] == source
        assert a["mortal_wounds"] == 1
