"""Authenticated Core example, not a claimed native Infractor ability.

Minimal cross-section integration: real marker geometry/control is necessary to
exercise the two nested predicates. No mission lifecycle is run.
"""

from dataclasses import replace

import pytest

from tests.support.section02_consumers import combat_state, scenario, set_origin
from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
)
from warhammer40k_core.engine.catalog_nested_attack_reroll_runtime import (
    nested_attack_reroll_handler,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import AttackRerollPermissionContext
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


@pytest.fixture(scope="session")
def section02_objective_setup() -> MissionSetup:
    from time import perf_counter

    started = perf_counter()
    pack = chapter_approved_2026_27_mission_pack()
    entry = pack.mission_pool_entries[0]
    setup = MissionSetup.from_mission_pack(
        mission_pack=pack,
        mission_pool_entry_id=entry.mission_pool_entry_id,
        attacker_player_id="owner",
        attacker_force_disposition_id=entry.player_force_disposition_id,
        defender_player_id="opponent",
        defender_force_disposition_id=entry.opponent_force_disposition_id,
    )
    print(f"Section02 objective preparation: {perf_counter() - started:.6f}s; one immutable setup")
    return setup


@pytest.mark.parametrize("closest", [False, True])
@pytest.mark.parametrize("on_objective", [False, True])
def test_02_03_01_improvement_requires_both_real_predicates(
    section02_definitions: Section02Definitions,
    section02_objective_setup: MissionSetup,
    closest: bool,
    on_objective: bool,
) -> None:
    text = (
        "This unit's ranged attacks that target the closest eligible target can "
        "re-roll hit rolls of 1. If that target is within range of an objective "
        "your opponent controls, re-roll hit rolls."
    )
    source_id = "rule:02:02.03.01:1:example"
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=source_id, raw_text=text, objective_scope=ObjectiveRuleScope.CORE_RULES
        ),
        source_keyword_sequence_parts=section02_definitions.unit().keywords,
    ).rule_ir
    assert not rule.diagnostics
    attacker = section02_definitions.unit(identity="attacker")
    target = section02_definitions.unit(identity="target", army_id="opponent-army")
    nearer = section02_definitions.unit(identity="nearer", army_id="opponent-army")
    state = combat_state(section02_definitions, attacker, target)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.army_definitions[1] = replace(state.army_definitions[1], units=(target, nearer))
    board = create_deterministic_battlefield_scenario(
        battlefield_id="section02", armies=tuple(state.army_definitions)
    ).battlefield_state
    state.replace_battlefield_state(board)
    setup = section02_objective_setup
    state.army_definitions[0] = replace(
        state.army_definitions[0],
        force_disposition_id=setup.force_disposition_id_for_player("owner"),
    )
    state.army_definitions[1] = replace(
        state.army_definitions[1],
        force_disposition_id=setup.force_disposition_id_for_player("opponent"),
    )
    state.record_mission_setup(setup)
    marker = setup.objective_markers[0]
    # Scene uses actual 32mm bases; no overlap and no engagement-range shortcut.
    y = marker.y_inches if on_objective else marker.y_inches + 6
    set_origin(state, attacker, marker.x_inches - 9, y)
    from warhammer40k_core.geometry.pose import Pose

    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    origin = placement.model_placements[0].pose.position
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(m, pose=Pose.at(origin.x, origin.y + m.pose.position.x - origin.x))
                    for m in placement.model_placements
                ),
            )
        )
    )
    set_origin(state, target, marker.x_inches, y)
    set_origin(state, nearer, marker.x_inches + 10 if closest else marker.x_inches - 4, y + 2)
    context = ObjectiveControlContext(
        game_id=state.game_id,
        scenario=scenario(state),
        objective_markers=tuple(m.to_objective_marker() for m in setup.objective_markers),
        battle_shocked_unit_ids=(),
        timing=ObjectiveControlTiming.PHASE_END,
        phase="shooting",
        battle_round=1,
        active_player_id="owner",
    )
    control = resolve_objective_control(context)
    state.record_objective_control_record(control)
    # A Core example is an explicit handler input; no datasheet is mutated or granted it.
    definition = AbilityDefinition(
        ability_id=source_id,
        name="Core nested example",
        source_id=source_id,
        when_descriptor="ranged attacks",
        effect_descriptor=text,
        restrictions_descriptor="closest and opponent objective",
        timing=AbilityTimingDescriptor(TimingTriggerKind.PASSIVE_QUERY),
    )
    source = CatalogDatasheetClauseSource(
        "owner", AbilityCatalogRecord(source_id, definition), attacker, rule.clauses[0], rule
    )
    weapon = section02_definitions.weapon(f"{INFRACTORS}:bolt-pistol")
    result = nested_attack_reroll_handler(source, None, section02_definitions.package.army_catalog)(
        AttackRerollPermissionContext(
            state=state,
            player_id="owner",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            source_phase=BattlePhase.SHOOTING,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            weapon_profile=weapon,
            shooting_type=ShootingType.NORMAL,
        )
    )
    if not closest:
        assert result is None
    else:
        assert result is not None
        assert isinstance(result.source_payload, dict)
        nested = result.source_payload["nested_conditions"]
        assert isinstance(nested, dict)
        assert nested["improved_reroll_applies"] is on_objective
        assert ("conditional_hit_reroll" in result.source_payload) is not on_objective
