"""Core selector contracts on a real, legally attached Lord and Infractors.

Selectors are Core inputs, not invented native datasheet abilities.
"""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
    health_state,
)
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, TargetKeywordMatchMode
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.catalog_model_scope import scoped_roll_model_ids_for_effect
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_ability_effects import (
    _required_keywords_apply,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    _target_keyword_gate_matches_descriptor,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.rules.rule_token_normalization import keyword_any_tokens


def attachment_state(
    definitions: Section02Definitions,
) -> tuple[GameState, RulesUnitView, UnitInstance, UnitInstance]:
    bodyguard = definitions.unit(identity="bodyguard")
    leader = definitions.unit(LORD_EXULTANT, identity="leader")
    target = next(
        t
        for e in definitions.package.army_catalog.datasheet_by_id(
            LORD_EXULTANT
        ).attachment_eligibilities
        for t in e.targets
        if t.bodyguard_datasheet_id == INFRACTORS
    )
    formation = AttachedUnitFormation(
        attached_unit_instance_id="attached-unit:section02:bodyguard",
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id=target.source_ids[0],
        attachment_source_ids=target.source_ids,
    )
    state = health_state(definitions, bodyguard)
    state.army_definitions[0] = replace(
        state.army_definitions[0], units=(bodyguard, leader), attached_units=(formation,)
    )
    return (
        state,
        rules_unit_view_by_id(state=state, unit_instance_id=formation.attached_unit_instance_id),
        bodyguard,
        leader,
    )


def attachment(
    definitions: Section02Definitions,
) -> tuple[RulesUnitView, UnitInstance, UnitInstance]:
    _, view, bodyguard, leader = attachment_state(definitions)
    return view, bodyguard, leader


@pytest.mark.parametrize(
    ("keyword", "expected"),
    [("CHARACTER", True), ("CHARACTERS", True), ("INFANTRY", True), ("VEHICLE", False)],
)
def test_02_05_01_unit_effect_uses_any_member_keyword(
    section02_definitions: Section02Definitions, keyword: str, expected: bool
) -> None:
    view, _, _ = attachment(section02_definitions)
    assert (
        _required_keywords_apply(parameters={"required_keyword": keyword}, rules_unit=view)
        is expected
    )


@pytest.mark.parametrize(
    ("keyword", "scope"),
    [("CHARACTER", "leader"), ("CHARACTERS", "leader"), ("INFANTRY", "all"), ("VEHICLE", "none")],
)
def test_02_05_01_model_effect_does_not_inherit_unit_union(
    section02_definitions: Section02Definitions, keyword: str, scope: str
) -> None:
    view, bodyguard, leader = attachment(section02_definitions)
    current = bodyguard.own_model_ids() + leader.own_model_ids()
    result = scoped_roll_model_ids_for_effect(
        source_rules_unit=view,
        current_roll_model_instance_ids=current,
        effect_parameters={"required_model_keyword": keyword},
    )
    assert result == tuple(
        sorted({"leader": leader.own_model_ids(), "all": current, "none": ()}[scope])
    )


@pytest.mark.parametrize(
    ("keyword", "unit_matches", "model_matches"),
    [("CHARACTER", False, True), ("VEHICLE", True, True), ("INFANTRY", False, False)],
)
def test_02_05_01_non_keyword_inverts_the_selected_scope_only(
    section02_definitions: Section02Definitions,
    keyword: str,
    unit_matches: bool,
    model_matches: bool,
) -> None:
    view, bodyguard, _ = attachment(section02_definitions)
    selector = AbilityDescriptor.hunter(
        target_keywords=(keyword,), target_keyword_match_mode=TargetKeywordMatchMode.MISSING_KEYWORD
    )
    assert (
        _target_keyword_gate_matches_descriptor(selector, target_keywords=view.keywords)
        is unit_matches
    )
    assert (
        _target_keyword_gate_matches_descriptor(
            selector, target_keywords=bodyguard.own_models[0].keywords
        )
        is model_matches
    )


@pytest.mark.parametrize("separator", [", ", " or ", "/"])
@pytest.mark.parametrize(
    ("alternatives", "expected"),
    [(("VEHICLE", "CHARACTER"), True), (("VEHICLE", "MONSTER"), False)],
)
def test_02_05_01_alternative_keywords_reach_target_gate(
    section02_definitions: Section02Definitions,
    separator: str,
    alternatives: tuple[str, str],
    expected: bool,
) -> None:
    view, _, _ = attachment(section02_definitions)
    expression = separator.join(alternatives)
    # Slash belongs to the descriptor boundary; prose comma/or to the rule parser.
    tokens = (expression,) if separator == "/" else keyword_any_tokens(expression)
    descriptor = AbilityDescriptor.hunter(target_keywords=tokens)
    assert (
        _target_keyword_gate_matches_descriptor(descriptor, target_keywords=view.keywords)
        is expected
    )


@pytest.mark.parametrize("noun", ["", " unit"])
def test_02_05_01_implicit_subject_reaches_unit_keyword_consumer(
    section02_definitions: Section02Definitions, noun: str
) -> None:
    from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
    from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
    from warhammer40k_core.rules.rule_ir import RuleTargetKind, parameter_payload
    from warhammer40k_core.rules.source_data import RuleSourceText

    unit = section02_definitions.unit(LORD_EXULTANT)
    text = (
        "At the start of your opponent's Shooting phase, "
        f'select one friendly CHARACTER{noun} within 6" of this model. '
        "Until the end of the phase, add 1 to the Charge rolls for that unit."
    )
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="core:02.05.01:subject-contract",
            raw_text=text,
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        ),
        source_keyword_sequence_parts=unit.keywords,
    ).rule_ir
    assert not rule.diagnostics
    target = rule.clauses[0].target
    assert target is not None
    assert target.kind is RuleTargetKind.FRIENDLY_UNIT
    view, _, _ = attachment(section02_definitions)
    parameters = parameter_payload(target.parameters)
    assert parameters["required_keyword"] == "CHARACTER"
    assert _required_keywords_apply(
        parameters={"required_keyword": str(parameters["required_keyword"])}, rules_unit=view
    )


def test_02_05_01_keyword_target_is_whole_attached_unit(
    section02_definitions: Section02Definitions,
) -> None:
    from tests.support.section02_consumers import scenario, set_origin
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
    from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model

    state, view, bodyguard, leader = attachment_state(section02_definitions)
    attacker = section02_definitions.unit(identity="attacker", army_id="opponent-army")
    enemy = replace(
        state.army_definitions[0],
        army_id="opponent-army",
        player_id="opponent",
        units=(attacker,),
        attached_units=(),
    )
    state.army_definitions.append(enemy)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="section02", armies=tuple(state.army_definitions)
        ).battlefield_state
    )
    set_origin(state, attacker, 2, 10)
    set_origin(state, bodyguard, 13, 10)
    set_origin(state, leader, 13, 12)
    selector = AbilityDescriptor.hunter(target_keywords=("CHARACTER",))
    assert _target_keyword_gate_matches_descriptor(selector, target_keywords=view.keywords)
    candidate = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=section02_definitions.weapon(f"{INFRACTORS}:bolt-pistol"),
        target_unit_id=view.unit_instance_id,
    )
    assert candidate.target_unit_instance_id == view.unit_instance_id
    assert set(candidate.target_visible_model_ids) == set(
        bodyguard.own_model_ids() + leader.own_model_ids()
    )
    assert not set(candidate.target_visible_model_ids).issubset(leader.own_model_ids())
