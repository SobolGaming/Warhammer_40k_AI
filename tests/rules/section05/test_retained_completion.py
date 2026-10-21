"""A real retained melee attack precedes destruction cleanup, including Deadly Demise."""

from dataclasses import replace

import pytest

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section05_sequence import payloads
from warhammer40k_core.engine.attack_completion_authority import (
    completed_attack_sequence,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.retained_destruction_cleanup import (
    begin_retained_destruction_cleanup,
)
from warhammer40k_core.engine.retained_model_presence import (
    model_is_present_on_battlefield,
)
from warhammer40k_core.engine.weapon_instances import (
    equipped_weapon_profile_instances_for_model,
)


@pytest.mark.parametrize("demise", [False, True])
def test_real_retained_melee_finishes_before_removal(
    section05_definitions: Section02Definitions, demise: bool
) -> None:
    d = section05_definitions
    state, target, decisions, request = terminal_retention(
        d, demise=demise, distance=2.0, melee=True
    )
    retain(state, decisions, request)
    mid = target.own_model_ids()[0]
    retained = unit_by_id(state=state, unit_instance_id=target.unit_instance_id)
    enemy = unit_by_id(state=state, unit_instance_id="section02:subject")
    physical = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=retained.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.wargear_id == f"{LORD_EXULTANT}:close-combat-weapon"
    )
    pool = replace(
        attack_pool(retained, enemy, physical.weapon_profile, physical.wargear_id),
        weapon_instance_id=physical.weapon_instance_id,
    )
    sequence = AttackSequence(
        "s05:retained-fight",
        "opponent",
        target.unit_instance_id,
        (pool,),
        source_phase=BattlePhase.FIGHT,
    )
    dice = DiceRollManager("physical-misses")
    results = tuple(
        dice.roll_fixed(
            attack_sequence_hit_roll_spec(
                weapon_profile_id=pool.weapon_profile_id,
                attack_context_id=f"s05:retained-fight:pool-001:attack-{i:03d}",
                attacker_player_id="opponent",
            ),
            (1,),
        ).original_result
        for i in range(1, pool.attacks + 1)
    )
    assert model_is_present_on_battlefield(state=state, model_instance_id=mid)
    assert not payloads(decisions, "model_destroyed")
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "s05:retained-fight",
            event_log=decisions.event_log,
            injected_results=results,
        ),
    )
    assert remaining is None
    assert status is None
    assert completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence.sequence_id
    ).is_complete
    assert model_is_present_on_battlefield(state=state, model_instance_id=mid)
    assert not payloads(decisions, "model_destroyed")
    assert (
        begin_retained_destruction_cleanup(
            state=state,
            decisions=decisions,
            reason="unit_fight_completed",
            unit_instance_id=target.unit_instance_id,
        )
        is None
    )
    assert not model_is_present_on_battlefield(state=state, model_instance_id=mid)
    events = decisions.event_log.records
    completed = next(i for i, e in enumerate(events) if e.event_type == "attack_sequence_completed")
    removed = next(i for i, e in enumerate(events) if e.event_type == "model_destroyed")
    assert completed < removed
    if demise:
        reaction = next(
            i for i, e in enumerate(events) if e.event_type == "destruction_reaction_resolved"
        )
        # Adopted FAQ20: complete Fight, remove this casualty, then Deadly Demise.
        assert completed < removed < reaction
