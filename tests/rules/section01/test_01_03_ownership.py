"""Explicit source-category contracts pass the bundle's real player gates and executor."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import core_rule, minimal_state
from tests.support.section02_fixtures import AVENGERS, Section02Definitions
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    default_ability_handler_registry,
    execute_abilities_from_index,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle_catalog_indexes import (
    ability_indexes_by_player_id,
)
from warhammer40k_core.engine.list_validation import DetachmentSelection
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize(
    "kind",
    [
        AbilitySourceKind.FACTION,
        AbilitySourceKind.DETACHMENT,
        AbilitySourceKind.ENHANCEMENT,
        AbilitySourceKind.DATASHEET,
    ],
)
def test_01_03_01_source_owner_gates_actual_effect_execution(
    section01_definitions: Section02Definitions, kind: AbilitySourceKind
) -> None:
    unit = section01_definitions.unit()
    peer = section01_definitions.unit(AVENGERS, identity="enemy", army_id="enemy")
    state = minimal_state(section01_definitions, unit)
    rule = core_rule("This unit gains Stealth until the end of the phase.")
    # Source metadata is a constructed Core ownership contract, not faction support.
    definition = AbilityDefinition(
        "constructed:ownership",
        "Ownership contract",
        rule.source_id,
        "command",
        "Stealth",
        "owner only",
        AbilityTimingDescriptor(TimingTriggerKind.START_PHASE, BattlePhase.COMMAND),
        handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        replay_payload=validate_json_value({"rule_ir": rule.to_payload()}),
    )
    owner = replace(
        state.army_definitions[0],
        detachment_selection=replace(
            state.army_definitions[0].detachment_selection,
            enhancement_ids=(definition.ability_id,),
        ),
    )
    enemy = replace(
        owner,
        army_id="enemy",
        player_id="opponent",
        units=(peer,),
        detachment_selection=DetachmentSelection("AE", ("constructed:other-detachment",)),
    )
    state.army_definitions[:] = [owner, enemy]
    record = AbilityCatalogRecord(
        "constructed:ownership",
        definition,
        kind,
        faction_id=owner.detachment_selection.faction_id
        if kind is AbilitySourceKind.FACTION
        else None,
        detachment_id=owner.detachment_selection.detachment_ids[0]
        if kind in {AbilitySourceKind.DETACHMENT, AbilitySourceKind.ENHANCEMENT}
        else None,
        datasheet_id=unit.datasheet_id if kind is AbilitySourceKind.DATASHEET else None,
    )
    indexes = ability_indexes_by_player_id(
        armies=(owner, enemy),
        catalog=section01_definitions.package.army_catalog,
        records=(record,),
    )
    assert indexes["owner"].all_records() == (record,)
    assert indexes["opponent"].all_records() == ()
    for player, source, count in (("opponent", peer, 0), ("owner", unit, 1)):
        results = execute_abilities_from_index(
            registry=default_ability_handler_registry(),
            index=indexes[player],
            context=AbilityExecutionContext(
                state.game_id,
                player,
                1,
                BattlePhase.COMMAND,
                "opponent",
                TimingTriggerKind.START_PHASE,
                source_unit_instance_id=source.unit_instance_id,
                state=state,
            ),
        )
        assert len(results) == count
        assert all(result.status is AbilityResolutionStatus.APPLIED for result in results)
    (effect,) = state.persisting_effects
    assert effect.owner_player_id == "owner"
    assert effect.applies_to_unit(unit.unit_instance_id)
    assert not effect.applies_to_unit(peer.unit_instance_id)
