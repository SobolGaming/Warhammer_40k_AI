"""Assertion-level evidence for foundational Core source definitions."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay, clause_session
from tests.model_keyword_helpers import mixed_keyword_unit
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollSpec,
    DiceRollSpecError,
)
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierOperation,
    ModifierScope,
    ModifierStack,
    ModifierTiming,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.damage_allocation import model_owner_player_id, unit_owner_player_id
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters.army_rule import (
    BlessingOfKhorne,
    _matching_allocations,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.rules.rule_characteristic_parser import _directional_characteristic_delta


def test_model_and_unit_ownership_resolve_to_the_controlling_player() -> None:
    session = clause_session(phase=BattlePhase.COMMAND)
    state = session.lifecycle.state
    assert state is not None
    for army in state.army_definitions:
        for unit in army.units:
            assert (
                unit_owner_player_id(state=state, unit_instance_id=unit.unit_instance_id)
                == army.player_id
            )
            for model in unit.own_models:
                assert (
                    model_owner_player_id(state=state, model_instance_id=model.model_instance_id)
                    == army.player_id
                )


@pytest.mark.parametrize("remaining", [0, 1, 2, 3])
def test_multi_model_strength_predicates_use_the_frozen_starting_count(remaining: int) -> None:
    original = mixed_keyword_unit()
    record = StartingStrengthRecord.from_unit(player_id="player-a", unit=original)
    models = tuple(
        replace(model, wounds_remaining=0) if index >= remaining else model
        for index, model in enumerate(original.own_models)
    )
    current = replace(original, own_models=models)
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=current,
        starting_strength=record,
        current_model_ids=tuple(
            model.model_instance_id for model in current.own_models if model.current_wounds > 0
        ),
    )
    assert record.starting_model_count == 3
    assert context.is_below_starting_strength is (remaining < 3)
    assert context.is_at_half_strength is False
    assert context.is_below_half_strength is (remaining < 1.5)


@pytest.mark.parametrize("remaining", [0, 1, 2])
def test_single_model_strength_predicates_use_remaining_wounds(remaining: int) -> None:
    original = mixed_keyword_unit()
    original = replace(original, own_models=(original.own_models[0],))
    record = StartingStrengthRecord.from_unit(player_id="player-a", unit=original)
    current = replace(
        original, own_models=(replace(original.own_models[0], wounds_remaining=remaining),)
    )
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=current,
        starting_strength=record,
        current_model_ids=tuple(
            model.model_instance_id for model in current.own_models if model.current_wounds > 0
        ),
    )
    assert record.single_model_starting_wounds == 2
    assert context.is_below_starting_strength is (remaining < 2)
    assert context.is_at_half_strength is (remaining == 1)
    assert context.is_below_half_strength is (remaining < 1)


@pytest.mark.parametrize("face", [1, 2, 3, 4, 5, 6])
def test_d6_accepts_each_physical_face(face: int) -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Core D6 evidence",
        roll_type="test_roll",
    )
    result = DiceRollResult.from_values(roll_id="d6", spec=spec, values=(face,), source="fixed")
    assert result.total == face


@pytest.mark.parametrize("face", [0, 7])
def test_d6_rejects_faces_outside_one_through_six(face: int) -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Core D6 evidence",
        roll_type="test_roll",
    )
    with pytest.raises(DiceRollSpecError):
        DiceRollResult.from_values(roll_id="d6", spec=spec, values=(face,), source="fixed")


def test_multiple_dice_sum_all_faces_and_the_intrinsic_constant() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=3, sides=6, modifier=2),
        reason="Core expression evidence",
        roll_type="test_roll",
    )
    result = DiceRollResult.from_values(
        roll_id="3d6-plus2", spec=spec, values=(1, 4, 6), source="fixed"
    )
    assert result.total == 13
    assert result.spec.expression.modifier == 2


@pytest.mark.parametrize(("values", "passed"), [((2, 3), False), ((3, 3), True), ((3, 4), True)])
def test_leadership_battle_shock_uses_two_d6_and_inclusive_threshold(
    values: tuple[int, int], passed: bool
) -> None:
    unit = mixed_keyword_unit()
    context = BelowHalfStrengthContext.from_unit(
        player_id="player-a",
        unit=unit,
        starting_strength=StartingStrengthRecord.from_unit(player_id="player-a", unit=unit),
        current_model_ids=(unit.own_models[0].model_instance_id,),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="leadership",
        game_id="core-evidence",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=6,
        below_half_strength_context=context,
    )
    assert request.spec.expression == DiceExpression(quantity=2, sides=6)
    roll = DiceRollManager("core-evidence").roll_fixed(request.spec, values)
    result = BattleShockResult.from_roll_state(
        result_id="leadership-result", request=request, roll_state=roll
    )
    assert result.passed is passed
    assert result.total == sum(values)


@pytest.mark.parametrize(
    ("values", "expected"),
    [((1, 2, 3), ()), ((1, 1, 2), ((0, 1),)), ((1, 1, 1), ((0, 1), (0, 2), (1, 2)))],
)
def test_double_consumer_requires_two_equal_dice(
    values: tuple[int, ...], expected: tuple[tuple[int, ...], ...]
) -> None:
    assert _matching_allocations(values, BlessingOfKhorne.UNBRIDLED_BLOODLUST) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((1, 1, 2), ()),
        ((1, 1, 1), ((0, 1, 2),)),
        ((1, 1, 1, 1), ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))),
    ],
)
def test_triple_consumer_requires_three_equal_dice(
    values: tuple[int, ...], expected: tuple[tuple[int, ...], ...]
) -> None:
    assert _matching_allocations(values, BlessingOfKhorne.MARTIAL_EXCELLENCE) == expected


@pytest.mark.parametrize(
    "characteristic",
    [
        Characteristic.WEAPON_SKILL,
        Characteristic.BALLISTIC_SKILL,
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
        Characteristic.LEADERSHIP,
        Characteristic.ARMOR_PENETRATION,
    ],
)
def test_threshold_and_ap_improvement_decreases_the_numeric_characteristic(
    characteristic: Characteristic,
) -> None:
    assert (
        _directional_characteristic_delta(characteristic=characteristic, verb="improve", value=2)
        == -2
    )
    assert (
        _directional_characteristic_delta(characteristic=characteristic, verb="worsen", value=2)
        == 2
    )


@pytest.mark.parametrize(
    "characteristic",
    [
        Characteristic.MOVEMENT,
        Characteristic.TOUGHNESS,
        Characteristic.STRENGTH,
        Characteristic.WOUNDS,
        Characteristic.ATTACKS,
        Characteristic.DAMAGE,
        Characteristic.OBJECTIVE_CONTROL,
    ],
)
def test_ordinary_characteristic_improvement_increases_the_numeric_characteristic(
    characteristic: Characteristic,
) -> None:
    assert (
        _directional_characteristic_delta(characteristic=characteristic, verb="improve", value=2)
        == 2
    )
    assert (
        _directional_characteristic_delta(characteristic=characteristic, verb="worsen", value=2)
        == -2
    )


def test_invulnerable_save_modifier_cannot_improve_past_two_plus() -> None:
    characteristic = Characteristic.INVULNERABLE_SAVE
    modifier = Modifier(
        modifier_id="improve-invulnerable",
        scope=ModifierScope.for_characteristics((characteristic,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=-5,
    )
    assert (
        ModifierStack(characteristic=characteristic, raw_value=4, modifiers=(modifier,))
        .resolve()
        .final
        == 2
    )


def test_exact_keyword_matching_does_not_promote_embedded_words() -> None:
    unit = with_unit_keywords(mixed_keyword_unit(), keywords=("COMMISSAR GRAVES",))
    assert unit_has_keyword(unit, "COMMISSAR_GRAVES")
    assert not unit_has_keyword(unit, "COMMISSAR")


def test_mixed_unit_keyword_does_not_promote_member_keywords() -> None:
    unit = mixed_keyword_unit()
    assert unit_has_keyword(unit, "PSYKER")
    assert tuple("PSYKER" in model.keywords for model in unit.own_models) == (False, False, True)


def test_reminder_resource_tokens_never_enter_the_physical_model_inventory() -> None:
    from warhammer40k_core.engine.unit_resources import UnitResourceLedger

    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit = state.army_definitions[0].units[0]
    models = tuple(
        model for army in state.army_definitions for row in army.units for model in row.own_models
    )
    battlefield = state.battlefield_state.to_payload()
    tokens = UnitResourceLedger.empty_for_unit(
        player_id="player-a", unit_instance_id=unit.unit_instance_id
    ).initialize(
        resource_kind="aeldari:aspect-shrine-token",
        amount=2,
        source_rule_id="order97:reminder-token",
    )
    state.replace_unit_resource_ledgers([tokens])
    assert (
        tuple(
            model
            for army in state.army_definitions
            for row in army.units
            for model in row.own_models
        )
        == models
    )
    assert state.battlefield_state.to_payload() == battlefield
    assert state.unit_resource_ledgers[0].total("aeldari:aspect-shrine-token") == 2


def test_default_wargear_is_equipped_separately_by_every_selected_model() -> None:
    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    unit = state.army_definitions[0].units[0]
    assert len(unit.own_models) == 5
    assert tuple(model.wargear_ids for model in unit.own_models) == (("core-bolt-rifle",),) * 5


def test_model_health_definition_matches_full_wounds_and_zero_health_casualties() -> None:
    model = mixed_keyword_unit().own_models[0]
    assert model.current_wounds == model.characteristic(Characteristic.WOUNDS).final
    assert model.is_alive
    assert not replace(model, wounds_remaining=0).is_alive


def test_other_unit_excludes_source_and_keeps_a_second_same_datasheet_instance() -> None:
    from tests.phase11c_command_phase_helpers import battle_state, default_unit_selection
    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir

    state = battle_state(
        player_a_units=(default_unit_selection("one"), default_unit_selection("two"))
    )
    source, other = state.army_definitions[0].units
    assert source.datasheet_id == other.datasheet_id
    ir = compiled_ability_rule(
        'Aura: while another friendly unit is within 100" of this unit, '
        "subtract 1 from wound rolls."
    )
    result = execute_rule_ir(
        rule_ir=ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id="player-a",
            timing_window_id="order97:aura",
            source_unit_instance_id=source.unit_instance_id,
            state=state,
        ),
    )
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [other.unit_instance_id]


def test_split_successors_record_their_own_starting_strength() -> None:
    from tests.phase11c_command_phase_helpers import mustered_armies, phase11c_config

    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_splitting import build_split_army

    config = phase11c_config()
    army = mustered_armies(config)[0]
    original = army.units[0]
    split = build_split_army(
        army=army,
        unit_instance_id=original.unit_instance_id,
        first_model_ids=original.own_model_ids()[::2],
        request_id="order97:split",
        source_id="order97:split-source",
        specified_strengths=None,
    )
    state = GameState.from_config(config)
    state.record_army_definition(split)
    assert sorted(
        state.starting_strength_record_for_unit(unit.unit_instance_id).starting_model_count
        for unit in split.units
    ) == [2, 3]


def test_unit_within_range_needs_only_one_near_model() -> None:
    from warhammer40k_core.engine.stratagems_geometry import _units_are_within_range_inches
    from warhammer40k_core.geometry.pose import Pose

    session = clause_session(phase=BattlePhase.COMMAND)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    target = state.battlefield_state.unit_placement_by_id("army-beta:enemy")
    first = source.model_placements[0].pose.position
    near = replace(target.model_placements[0], pose=Pose.at(first.x + 1.5, first.y, first.z))
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        replace(target, model_placements=(near, *target.model_placements[1:]))
    )
    assert _units_are_within_range_inches(
        state=state,
        first_unit_instance_id=source.unit_instance_id,
        second_unit_instance_id=target.unit_instance_id,
        distance_inches=1,
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(target)
    assert not _units_are_within_range_inches(
        state=state,
        first_unit_instance_id=source.unit_instance_id,
        second_unit_instance_id=target.unit_instance_id,
        distance_inches=1,
    )


@pytest.mark.parametrize("keyword", ["INFANTRY", "MONSTER", "VEHICLE"])
def test_unrestricted_unit_effect_includes_every_model_keyword_class(keyword: str) -> None:
    from tests.phase11c_command_phase_helpers import battle_state, default_unit_selection
    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir

    state = battle_state(
        player_a_units=(default_unit_selection("one"), default_unit_selection("two"))
    )
    army = state.army_definitions[0]
    source, target = army.units
    target = with_unit_keywords(target, keywords=(keyword,))
    state.replace_army_definitions(
        [replace(army, units=(source, target)), *state.army_definitions[1:]]
    )
    result = execute_rule_ir(
        rule_ir=compiled_ability_rule(
            'Aura: while another friendly unit is within 100" of this unit, '
            "subtract 1 from wound rolls."
        ),
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id="player-a",
            timing_window_id="order97:all-keywords",
            source_unit_instance_id=source.unit_instance_id,
            state=state,
        ),
    )
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [target.unit_instance_id]


def test_unit_wholly_within_region_checks_every_physical_member() -> None:
    from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
        _Footprint,
        _placements_wholly_within_region,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry import shapely_backend
    from warhammer40k_core.geometry.base import RectangularBase
    from warhammer40k_core.geometry.pose import Pose

    session = clause_session(phase=BattlePhase.COMMAND)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:mover")
    placement = state.battlefield_state.unit_placement_by_id(view.unit_instance_id)
    region = shapely_backend.footprint_for_base(RectangularBase(20, 20), Pose.at(10, 10))
    inside = tuple(replace(row, pose=Pose.at(10, 10)) for row in placement.model_placements)
    assert _placements_wholly_within_region(
        view=view, placements=inside, region_footprint=cast(_Footprint, region)
    )
    one_outside = (replace(inside[0], pose=Pose.at(25, 10)), *inside[1:])
    assert not _placements_wholly_within_region(
        view=view, placements=one_outside, region_footprint=cast(_Footprint, region)
    )


@pytest.mark.parametrize("attacks", [1, 3])
def test_unit_ranged_attacks_bonus_changes_weapon_count_once(attacks: int) -> None:
    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.core.weapon_profiles import AttackProfile
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir
    from warhammer40k_core.engine.runtime_modifiers import (
        RuntimeModifierRegistry,
        WeaponProfileModifierContext,
    )

    session = clause_session(phase=BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    attacker = state.army_definitions[0].units[0]
    defender = state.army_definitions[1].units[0]
    profile = next(
        row
        for row in session.lifecycle.config.army_catalog.wargear
        if row.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    profile = replace(profile, attack_profile=AttackProfile.fixed(attacks))
    execute_rule_ir(
        rule_ir=compiled_ability_rule(
            "Until the end of the phase, add 1 to the Attacks characteristic of ranged "
            "weapons equipped by models in this unit."
        ),
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.SHOOTING,
            active_player_id="player-a",
            timing_window_id="order97:attacks",
            source_unit_instance_id=attacker.unit_instance_id,
            state=state,
        ),
    )
    modified = RuntimeModifierRegistry.empty().modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            weapon_profile=profile,
        )
    )
    assert modified.attack_profile.fixed_attacks == attacks + 1


@pytest.mark.parametrize("face", [1, 2, 3, 4, 5, 6])
def test_source_dice_ranges_include_both_endpoints(face: int) -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.imperial_knights import (
        army_rule as knights,
    )

    expected = (
        knights.CodeChivalricDeed.LAY_LOW_THE_TYRANT,
        knights.CodeChivalricDeed.RECLAIM_THE_REALM,
        knights.CodeChivalricDeed.REAP_A_GREAT_TALLY,
    )
    assert knights._deed_from_d6(face) is expected[(face - 1) // 2]


def test_absent_movement_characteristic_still_allows_physical_setup() -> None:
    from warhammer40k_core.core.attributes import CharacteristicValue
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario

    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definitions[0]
    unit = army.units[0]
    immobile = replace(
        unit,
        own_models=tuple(
            replace(
                model,
                characteristics=tuple(
                    CharacteristicValue.source_dash(Characteristic.MOVEMENT)
                    if value.characteristic is Characteristic.MOVEMENT
                    else value
                    for value in model.characteristics
                ),
            )
            for model in unit.own_models
        ),
    )
    setup = create_deterministic_battlefield_scenario(
        battlefield_id="order97:dash-setup", armies=(replace(army, units=(immobile,)),)
    )
    placement = setup.battlefield_state.unit_placement_by_id(immobile.unit_instance_id)
    assert (
        tuple(row.model_instance_id for row in placement.model_placements)
        == immobile.own_model_ids()
    )


def test_first_battle_round_attached_starting_strength_survives_casualties() -> None:
    from tests.support.ability_presence_fixtures import ability_presence_fixture

    from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    _, state, _ = ability_presence_fixture(embarked=False, attached=True)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    assert state.battle_round == 1
    original = state.starting_strength_record_for_unit(view.unit_instance_id)
    assert original.starting_model_count == len(view.alive_models()) == 6
    for model in view.alive_models()[:4]:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    current = rules_unit_view_by_id(state=state, unit_instance_id=view.unit_instance_id)
    assert len(current.alive_models()) == 2
    assert state.starting_strength_record_for_unit(view.unit_instance_id) == original
    assert state.starting_strength_record_for_unit(view.unit_instance_id).starting_model_count == 6


@pytest.mark.parametrize(
    ("raw_range", "distance", "allowed"),
    [
        (1, 8.9, True),
        (1, 9.1, False),
        (99, 29.9, True),
        (99, 30.1, False),
    ],
)
def test_lone_operative_actual_target_consumer_clamps_range(
    raw_range: int,
    distance: float,
    allowed: bool,
) -> None:
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.lone_operative import lone_operative_target_allowed
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.unit_abilities import LoneOperativeAbilityProfile
    from warhammer40k_core.geometry.pose import Pose

    session = clause_session(
        phase=BattlePhase.SHOOTING, enemy_origin=Pose.at(10 + 32 / 25.4 + distance, 20)
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.army_definitions[0].units[0]
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:enemy")
    assert (
        lone_operative_target_allowed(
            scenario=BattlefieldScenario(
                armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
            ),
            attacker_unit=source,
            attacker_model_instance_id=source.own_models[0].model_instance_id,
            target_rules_unit=target,
            profile=LoneOperativeAbilityProfile(
                source_id="order97:lone-range", range_inches=raw_range
            ),
        )
        is allowed
    )


def test_explicit_return_count_cannot_exceed_attached_starting_strength() -> None:
    from tests.order90_revival_helpers import offboard_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle, effect, _ = offboard_scene(reserves=True)
    state = lifecycle.state
    assert state is not None
    effect = replace(effect, amount=99)
    view = rules_unit_view_by_id(state=state, unit_instance_id=effect.target_unit_instance_id)
    original_ids = tuple(model.model_instance_id for model in view.own_models)
    assert len(view.alive_models()) == 5
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    result = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order97:overlarge-return-count",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    current = rules_unit_view_by_id(state=state, unit_instance_id=effect.target_unit_instance_id)
    assert (
        len(current.alive_models())
        == state.starting_strength_record_for_unit(current.unit_instance_id).starting_model_count
        == 6
    )
    assert tuple(model.model_instance_id for model in current.own_models) == original_ids
    assert (
        result.decision_request is None
        or result.decision_request.decision_type != "select_healing_model"
    )
    assert_persistence_viewers_replay(session)


@pytest.mark.parametrize("presence", ["battlefield", "embarked", "reserves"])
@pytest.mark.parametrize("condition", ["range", "visibility", "none"])
def test_incoming_selection_cannot_measure_or_see_off_battlefield_targets(
    presence: str, condition: str
) -> None:
    from tests.support.ability_presence_fixtures import (
        ability_presence_fixture,
        compiled_ability_rule,
    )

    from warhammer40k_core.engine.ability_presence import ability_presence
    from warhammer40k_core.engine.catalog_selected_target_effects_support import (
        eligible_selection_target_unit_ids,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.rules.rule_ir import RuleConditionKind

    _, state, _ = ability_presence_fixture(
        embarked=presence == "embarked", reserves=presence == "reserves", attached=False
    )
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:transport")
    target = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    assert ability_presence(state=state, rules_unit=source).battlefield_model_ids
    assert bool(ability_presence(state=state, rules_unit=target).battlefield_model_ids) is (
        presence == "battlefield"
    )
    clause = compiled_ability_rule(
        'At the start of the Fight phase, select one friendly unit within 100" of and visible '
        "to this model. Until the end of the phase, add 1 to the Strength characteristic "
        "of melee weapons equipped by models in that unit."
    ).clauses[0]
    keep = {
        "range": {RuleConditionKind.DISTANCE_PREDICATE},
        "visibility": {RuleConditionKind.VISIBILITY_PREDICATE},
        "none": set[RuleConditionKind](),
    }[condition]
    clause = replace(clause, conditions=tuple(c for c in clause.conditions if c.kind in keep))
    targets = eligible_selection_target_unit_ids(
        state=state,
        source_player_id="player-a",
        source_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        selection_clause=clause,
        explicit_target_unit_ids=(target.unit_instance_id,),
    )
    assert targets == (
        (target.unit_instance_id,) if presence == "battlefield" or condition == "none" else ()
    )


@pytest.mark.parametrize("reserves", [False, True])
def test_incoming_army_selection_applies_effect_to_off_battlefield_target(reserves: bool) -> None:
    from tests.order90_revival_helpers import offboard_scene
    from tests.support.ability_presence_fixtures import compiled_ability_rule

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.ability_presence import ability_presence
    from warhammer40k_core.engine.catalog_selected_target_effects_support import (
        eligible_selection_target_unit_ids,
    )
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle, effect, model_id = offboard_scene(reserves=reserves)
    state = lifecycle.state
    assert state is not None
    target_id = effect.target_unit_instance_id
    source = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:transport")
    assert ability_presence(state=state, rules_unit=source).battlefield_model_ids
    assert not ability_presence(
        state=state, rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=target_id)
    ).battlefield_model_ids
    clause = compiled_ability_rule(
        "At the start of the Fight phase, select one friendly unit."
    ).clauses[0]
    targets = eligible_selection_target_unit_ids(
        state=state,
        source_player_id="player-a",
        source_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_models[0].model_instance_id,
        selection_clause=clause,
        explicit_target_unit_ids=None,
    )
    assert target_id in targets
    assert model_by_id(state=state, model_instance_id=model_id).current_wounds == 0
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    assert request.decision_type == "select_healing_model"
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order97-incoming-effect",
    )
    assert status.status_kind not in {
        LifecycleStatusKind.INVALID,
        LifecycleStatusKind.UNSUPPORTED,
    }, status
    current = session.lifecycle.state
    assert current is not None
    restored = model_by_id(state=current, model_instance_id=model_id)
    assert restored.current_wounds == restored.initial_wounds
    assert not ability_presence(
        state=current, rules_unit=rules_unit_view_by_id(state=current, unit_instance_id=target_id)
    ).battlefield_model_ids
    assert model_id in (
        current.unarrived_reserve_model_ids() if reserves else current.embarked_model_ids()
    )
    assert_persistence_viewers_replay(session)
