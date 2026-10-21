"""Off-board self abilities and army selection use the production spatial policy."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import core_rule, minimal_state, reserve_unit
from tests.support.section02_fixtures import AVENGERS, Section02Definitions
from warhammer40k_core.engine.ability_presence import (
    AbilitySpatialRelationship,
    ability_battlefield_conditions_apply,
    ability_presence,
    ability_spatial_relationship,
)
from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    eligible_selection_target_unit_ids,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transports import (
    TransportCapacityProfile,
    TransportCargoState,
)


@pytest.mark.parametrize("location", ["reserves", "embarked"])
def test_01_02_04_own_ability_and_other_spatial_selection(
    section01_definitions: Section02Definitions, location: str
) -> None:
    source = section01_definitions.unit(AVENGERS, identity="source")
    target = section01_definitions.unit(AVENGERS, identity="target")
    carrier = section01_definitions.unit("000000599", identity="transport")
    state = minimal_state(section01_definitions, source, target, carrier)
    state.record_battlefield_state(BattlefieldRuntimeState("offboard", 60, 44, ()))
    reserve_unit(state, source)
    if location == "reserves":
        reserve_unit(state, target)
    else:
        # Core cargo contract on native Wave Serpent and Dire Avenger definitions.
        state.transport_cargo_states[:] = [
            TransportCargoState(
                "owner",
                carrier.unit_instance_id,
                TransportCapacityProfile(
                    carrier.datasheet_id,
                    12,
                    source_id="constructed:core-cargo-capacity",
                ),
                (target.unit_instance_id,),
            )
        ]
    first = rules_unit_view_by_id(state=state, unit_instance_id=source.unit_instance_id)
    second = rules_unit_view_by_id(state=state, unit_instance_id=target.unit_instance_id)
    assert ability_presence(state=state, rules_unit=second).off_battlefield_model_ids == tuple(
        sorted(target.own_model_ids())
    )
    for a, b, expected in (
        (first, first, AbilitySpatialRelationship.OWN_ABILITY),
        (second, second, AbilitySpatialRelationship.OWN_ABILITY),
        (first, second, AbilitySpatialRelationship.OFF_BATTLEFIELD),
        (second, first, AbilitySpatialRelationship.OFF_BATTLEFIELD),
    ):
        assert ability_spatial_relationship(state=state, source=a, target=b) is expected
    for text, eligible in (
        ("At the start of the Fight phase, select one friendly unit.", True),
        (
            'At the start of the Fight phase, select one friendly unit within 6" of this unit.',
            False,
        ),
        (
            "At the start of the Fight phase, select one friendly unit "
            'within 6" of and visible to this unit.',
            False,
        ),
    ):
        rule = core_rule(text)
        ids = eligible_selection_target_unit_ids(
            state=state,
            source_player_id="owner",
            source_unit_instance_id=source.unit_instance_id,
            source_model_instance_id=None,
            selection_clause=rule.clauses[0],
            explicit_target_unit_ids=(target.unit_instance_id,),
        )
        assert ids == ((target.unit_instance_id,) if eligible else ())
    unrestricted = core_rule(
        "Add 1 to the Attacks characteristic of ranged weapons equipped by models in this unit."
    )
    assert ability_battlefield_conditions_apply(
        state=state,
        clause=unrestricted.clauses[0],
        source_unit_instance_id=target.unit_instance_id,
        source_model_instance_id=target.own_models[0].model_instance_id,
    )
    from warhammer40k_core.rules.rule_ir import (
        RuleCondition,
        RuleConditionKind,
        parameters_from_pairs,
    )

    # Explicit typed presence-condition contract; no claim of parser support for its prose.
    restricted = replace(
        unrestricted.clauses[0],
        conditions=(
            RuleCondition(
                RuleConditionKind.TARGET_CONSTRAINT,
                unrestricted.clauses[0].source_span,
                parameters_from_pairs((("relationship", "source_model_on_battlefield"),)),
            ),
        ),
    )
    assert not ability_battlefield_conditions_apply(
        state=state,
        clause=restricted,
        source_unit_instance_id=target.unit_instance_id,
        source_model_instance_id=target.own_models[0].model_instance_id,
    )


@pytest.mark.parametrize("alive", [0, 1, 2, 3, 5])
@pytest.mark.parametrize("shocked", [False, True])
@pytest.mark.parametrize("location", ["reserves", "embarked"])
def test_01_02_04_offboard_command_required_at_half_or_shocked(
    section01_definitions: Section02Definitions,
    alive: int,
    shocked: bool,
    location: str,
) -> None:
    original = section01_definitions.unit(AVENGERS)
    state = minimal_state(section01_definitions, original)
    unit = replace(
        original,
        own_models=tuple(
            replace(m, wounds_remaining=m.initial_wounds if i < alive else 0)
            for i, m in enumerate(original.own_models)
        ),
    )
    state.army_definitions[:] = [replace(state.army_definitions[0], units=(unit,))]
    state.record_battlefield_state(BattlefieldRuntimeState("offboard", 60, 44, ()))
    if location == "reserves":
        reserve_unit(state, unit)
    else:
        carrier = section01_definitions.unit("000000599", identity="carrier")
        state.add_unit_to_army(
            player_id="owner", unit=carrier, source_id="constructed:Core-carrier"
        )
        state.transport_cargo_states.append(
            TransportCargoState(
                "owner",
                carrier.unit_instance_id,
                TransportCapacityProfile(
                    carrier.datasheet_id, 12, source_id="constructed:Core-cargo"
                ),
                (unit.unit_instance_id,),
            )
        )
    assert state.battlefield_state is not None
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=1,
        player_id="owner",
        army=state.army_definitions[0],
        battlefield_state=state.battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        battle_shocked_unit_ids=(unit.unit_instance_id,) if shocked else (),
        state=state,
    )
    assert len(requests) == int(alive > 0 and (shocked or alive * 2 <= 5))
    if requests:
        assert requests[0].spec.expression.quantity == 2
        assert requests[0].leadership_target == 6
