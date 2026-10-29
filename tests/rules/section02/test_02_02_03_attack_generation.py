"""Random Attacks and actual equipment at the narrow declaration/gather boundary."""

import pytest

from tests.support.section02_consumers import (
    combat_state,
    payload_object,
    payload_text,
    scenario,
    set_origin,
)
from tests.support.section02_fixtures import CHAOS_SPAWN, INFRACTORS, Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposal
from warhammer40k_core.engine.fight_weapon_selection import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    available_melee_weapons_payloads,
    melee_attack_sequence_from_proposal,
)
from warhammer40k_core.engine.phase import BattlePhase


@pytest.mark.parametrize("datasheet", [CHAOS_SPAWN, INFRACTORS])
def test_02_02_03_generate_each_equipped_weapon_before_pooling(
    section02_definitions: Section02Definitions, datasheet: str
) -> None:
    attacker = section02_definitions.unit(datasheet, identity="attacker")
    target = section02_definitions.unit(identity="target", army_id="opponent-army")
    state = combat_state(section02_definitions, attacker, target)
    set_origin(state, attacker, 10, 10)
    set_origin(state, target, 12.2, 10)
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    board = scenario(state)
    manager = DiceRollManager("section02-generation")
    before = manager.event_log.to_payload()
    rows = available_melee_weapons_payloads(
        scenario=board,
        ruleset_descriptor=descriptor,
        unit=attacker,
        army_catalog=section02_definitions.package.army_catalog,
    )
    assert manager.event_log.to_payload() == before
    assert len(rows) == len(attacker.own_models)
    declarations: list[MeleeWeaponDeclaration] = []
    for raw in rows:
        assert isinstance(raw, dict)
        row = raw
        assert row["engaged_target_unit_instance_ids"] == [target.unit_instance_id]
        declarations.append(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=str(row["model_instance_id"]),
                wargear_id=str(row["wargear_id"]),
                weapon_profile_id=str(row["weapon_profile_id"]),
                weapon_instance_id=str(row["weapon_instance_id"]),
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            )
        )
    proposal = MeleeDeclarationProposal(
        proposal_request_id="declaration",
        proposal_kind="melee_declaration",
        player_id="owner",
        battle_round=1,
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id="weapon-choice",
        source_decision_result_id="chosen-weapons",
        declarations=tuple(declarations),
    )
    sequence = melee_attack_sequence_from_proposal(
        scenario=board,
        ruleset_descriptor=descriptor,
        proposal=proposal,
        army_catalog=section02_definitions.package.army_catalog,
        dice_manager=manager,
        sequence_id="generated",
    )
    assert sequence.source_phase is BattlePhase.FIGHT
    assert len(sequence.attack_pools) == len(attacker.own_models)
    assert len({p.weapon_instance_id for p in sequence.attack_pools}) == len(attacker.own_models)
    assert {p.target_unit_instance_id for p in sequence.attack_pools} == {target.unit_instance_id}
    if datasheet == CHAOS_SPAWN:
        assert all(3 <= p.attacks <= 8 for p in sequence.attack_pools)
        payload = manager.event_log.to_payload()
        rolls = [
            payload_object(row["payload"])
            for row in payload
            if row["event_type"] == "random_characteristic_rolled"
        ]
        assert len(rolls) == len(attacker.own_models)
        assert len({payload_text(row["scope_id"]) for row in rolls}) == len(attacker.own_models)
        assert all(
            row["timing"] == "per_weapon" and row["characteristic"] == "attacks" for row in rolls
        )
        assert [row["value"] for row in rolls] == [p.attacks for p in sequence.attack_pools]
        from warhammer40k_core.engine.native_attack_gathering import (
            native_gathered_attack_groups_for_target,
        )
        from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

        before_gather = manager.event_log.to_payload()
        groups = native_gathered_attack_groups_for_target(
            state=state,
            registry=RuntimeModifierRegistry.empty(),
            attack_sequence=sequence,
            target_unit_instance_id=target.unit_instance_id,
            target_has_character=False,
            has_custom_callbacks=False,
        )
        assert sum(g.total_attacks for g in groups) == sum(p.attacks for p in sequence.attack_pools)
        assert sorted(i for g in groups for i in g.pool_indices) == list(
            range(len(sequence.attack_pools))
        )
        assert manager.event_log.to_payload() == before_gather
    else:
        assert all(p.attacks == 4 for p in sequence.attack_pools)
        assert manager.event_log.to_payload() == before
    # These are actual melee inventories: ranged pistols never enter this consumer.
    assert all("pistol" not in p.wargear_id for p in sequence.attack_pools)
    assert {p.attacker_model_instance_id for p in sequence.attack_pools} == set(
        attacker.own_model_ids()
    )
