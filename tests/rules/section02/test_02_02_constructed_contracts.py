"""Explicit constructed Core contracts; NOT certification of a native datasheet.

Fresh model/weapon containers reuse valid structural definitions and geometry.
The named values below are constructed rule inputs, carry Core-contract identity,
and never modify the immutable retained catalog. Geometry is used only for the
setup/selection contracts that actually need battlefield presence.
"""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_consumers import attack_pool, payload_object, payload_text
from tests.support.section02_fixtures import INFRACTORS, Section02Definitions, health_state
from tests.support.section03_fixtures import native_state, placement, scenario
from warhammer40k_core.core.attributes import Characteristic as C
from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    RandomProfileValue,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.advance_roll import AdvanceRollRequest, AdvanceRollResult
from warhammer40k_core.engine.aircraft import AircraftMovementPolicy
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.movement import (
    AdvanceMoveResolution,
    NormalMoveResolution,
    resolve_advance_move,
    resolve_normal_move,
)
from warhammer40k_core.engine.phases.movement_action_decisions import _request_movement_action
from warhammer40k_core.engine.phases.movement_model import (
    MovementPhaseActionKind,
    MovementUnitSelection,
)
from warhammer40k_core.engine.phases.movement_state import MovementPhaseState
from warhammer40k_core.engine.phases.movement_validation import _model_movement_budget_inches
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.random_profile_evaluation import evaluate_unit_profile_characteristics
from warhammer40k_core.engine.random_weapon_profiles import evaluate_attack_weapon_profile
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.reserves import resolve_reserve_arrival
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
    TriggeredMovementResolution,
)
from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

CONTRACT_SOURCE = "rule:02:constructed-contract"


def contract_unit(
    definitions: Section02Definitions, value: ProfileCharacteristicValue
) -> UnitInstance:
    shape = definitions.unit(identity="constructed-contract")
    models = tuple(
        replace(
            m,
            keyword_assignment=replace(m.keyword_assignment, datasheet_id="core-contract"),
            datasheet_id="core-contract",
            name="Constructed Core model",
            source_ids=(CONTRACT_SOURCE,),
            characteristics=tuple(
                value if c.characteristic is value.characteristic else c for c in m.characteristics
            ),
        )
        for m in shape.own_models
    )
    return replace(
        shape,
        datasheet_id="core-contract",
        name="Constructed Core unit",
        datasheet_abilities=(),
        datasheet_source_ids=(CONTRACT_SOURCE,),
        own_models=models,
    )


def contract_state(definitions: Section02Definitions, unit: UnitInstance) -> GameState:
    state = health_state(definitions, definitions.unit())
    state.army_definitions[0] = replace(state.army_definitions[0], units=(unit,))
    return state


@pytest.mark.parametrize("absent", [False, True])
@pytest.mark.parametrize("kind", ["translate", "rotate", "return", "hold"])
@pytest.mark.parametrize("mode", ["normal", "advance", "fixed"])
def test_02_02_absent_m_requires_fixed_pose_through_movement_consumers(
    section02_definitions: Section02Definitions, absent: bool, kind: str, mode: str
) -> None:
    """Constructed dash/zero M, native bodies; witnessed movement consumers, no setup claim here."""
    value = (
        CharacteristicValue.source_dash(C.MOVEMENT)
        if absent
        else CharacteristicValue.from_raw(C.MOVEMENT, 0)
    )
    unit = contract_unit(section02_definitions, value)
    state = native_state(section02_definitions, unit)
    board = scenario(state)
    current = board.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for row in current.model_placements:
        origin = row.pose
        shifted = Pose.at(origin.position.x + 0.5, origin.position.y)
        rotated = Pose.at(origin.position.x, origin.position.y, facing_degrees=90)
        points = {
            "translate": (origin, shifted),
            "rotate": (origin, rotated),
            "return": (origin, shifted, origin),
            "hold": (origin, origin),
        }[kind]
        paths.append((row.model_instance_id, points))
    witness = PathWitness.for_paths(tuple(paths))
    before = state.to_payload()
    descriptor = state.runtime_ruleset_descriptor()
    result: NormalMoveResolution | AdvanceMoveResolution | TriggeredMovementResolution
    if mode == "normal":
        result = resolve_normal_move(
            scenario=board,
            ruleset_descriptor=descriptor,
            unit_placement=current,
            path_witness=witness,
            movement_bonus_inches=3,
        )
    elif mode == "advance":
        request = AdvanceRollRequest.for_unit(
            request_id="contract:advance",
            game_id=state.game_id,
            battle_round=1,
            player_id="owner",
            unit_instance_id=unit.unit_instance_id,
        )
        roll = AdvanceRollResult.from_roll_state(
            request=request, roll_state=DiceRollManager("contract").roll_fixed(request.spec, (3,))
        )
        result = resolve_advance_move(
            scenario=board,
            ruleset_descriptor=descriptor,
            unit_placement=current,
            path_witness=witness,
            advance_roll=roll,
        )
    else:
        result = resolve_triggered_movement(
            scenario=board,
            ruleset_descriptor=descriptor,
            unit_placement=current,
            path_witness=witness,
            battle_round=1,
            turn_player_id="owner",
            descriptor=TriggeredMovementDescriptor(
                movement_kind=TriggeredMovementKind.TRIGGERED,
                source_rule_id="constructed:fixed-distance",
                max_distance_inches=3,
                trigger_timing=ReactionWindow(
                    phase=BattlePhase.MOVEMENT,
                    window_kind=ReactionWindowKind.RULE_TRIGGER,
                    source_step=None,
                    source_event_id=None,
                ),
            ),
        )
    assert result.is_valid is (not absent or kind == "hold"), result
    if absent and kind != "hold":
        assert all(
            any(v.violation_code == "model_pose_fixed" for v in row.violations)
            for row in result.path_validation_results
        )
        assert result.path_validation_results
    assert state.to_payload() == before


def test_02_02_absent_move_still_accepts_actual_reserve_setup(
    section02_definitions: Section02Definitions,
) -> None:
    unit = contract_unit(section02_definitions, CharacteristicValue.source_dash(C.MOVEMENT))
    state = native_state(section02_definitions, unit)
    assert state.battlefield_state is not None
    state.battlefield_state = replace(state.battlefield_state, placed_armies=())
    reserve_unit(state, unit)
    poses = tuple(Pose.at(1, 10 + 2 * i) for i in range(len(unit.own_models)))
    proposed = placement(unit, poses)
    before = state.to_payload()
    result = resolve_reserve_arrival(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        reserve_state=state.reserve_states[0],
        attempted_placement=proposed,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid, result
    assert result.transition_batch is not None
    assert state.to_payload() == before
    assert all(m.characteristic(C.MOVEMENT).is_dash for m in unit.own_models)


def test_02_02_absent_oc_contributes_no_control_value(
    section02_definitions: Section02Definitions,
) -> None:
    unit = contract_unit(
        section02_definitions, CharacteristicValue.source_dash(C.OBJECTIVE_CONTROL)
    )
    for model in unit.own_models:
        value = model_objective_control_characteristic(model, battle_shocked=False)
        assert value.is_dash
        assert value.final == 0
    assert (
        model_objective_control_characteristic(
            section02_definitions.unit().own_models[0], battle_shocked=False
        ).final
        == 2
    )


def test_02_02_03_random_move_is_resolved_at_selection_and_used_for_budget(
    section02_definitions: Section02Definitions,
) -> None:
    unit = contract_unit(
        section02_definitions,
        RandomProfileValue(C.MOVEMENT, DiceExpression(1, 6, 2), CONTRACT_SOURCE),
    )
    state = contract_state(section02_definitions, unit)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="constructed-movement", armies=tuple(state.army_definitions)
        ).battlefield_state
    )
    decisions = DecisionController()
    assert decisions.event_log.to_payload() == []
    assert all(
        isinstance(m.characteristic(C.MOVEMENT), RandomProfileValue) for m in unit.own_models
    )
    selection = MovementUnitSelection(
        "owner", 1, unit.unit_instance_id, "select-unit", "selected-unit"
    )
    state.movement_phase_state = MovementPhaseState(1, "owner").with_unit_selection(selection)
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    _request_movement_action(
        state=state,
        decisions=decisions,
        active_selection=selection,
        ruleset_descriptor=descriptor,
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    rolls = [
        payload_object(e.payload)
        for e in decisions.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(rolls) == 1
    assert rolls[0]["timing"] == "unit_when_selected_to_move"
    current = state.army_definitions[0].units[0]
    policy = AircraftMovementPolicy.from_unit(unit=current, ruleset_descriptor=descriptor)
    for model in current.own_models:
        assert (
            _model_movement_budget_inches(
                model=model,
                aircraft_policy=policy,
                ruleset_descriptor=descriptor,
                movement_bonus_inches=0,
                movement_mode=MovementMode.NORMAL,
                movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            )
            == rolls[0]["value"]
        )
    before = decisions.event_log.to_payload()
    evaluate_unit_profile_characteristics(
        state=state,
        decisions=decisions,
        unit_instance_id=unit.unit_instance_id,
        scope_id=selection.result_id,
        characteristics=(C.MOVEMENT,),
    )
    assert decisions.event_log.to_payload() == before


def test_02_02_03_other_random_model_values_are_per_model_and_use(
    section02_definitions: Section02Definitions,
) -> None:
    unit = contract_unit(
        section02_definitions,
        RandomProfileValue(C.TOUGHNESS, DiceExpression(1, 6, 2), CONTRACT_SOURCE),
    )
    state = contract_state(section02_definitions, unit)
    decisions = DecisionController()
    for occurrence in ("first-use", "second-use"):
        evaluate_unit_profile_characteristics(
            state=state,
            decisions=decisions,
            unit_instance_id=unit.unit_instance_id,
            scope_id=occurrence,
            characteristics=(C.TOUGHNESS,),
        )
        before = decisions.event_log.to_payload()
        evaluate_unit_profile_characteristics(
            state=state,
            decisions=decisions,
            unit_instance_id=unit.unit_instance_id,
            scope_id=occurrence,
            characteristics=(C.TOUGHNESS,),
        )
        assert decisions.event_log.to_payload() == before
    rolls = [
        payload_object(e.payload)
        for e in decisions.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(rolls) == 2 * len(unit.own_models)
    assert len({payload_text(r["scope_id"]) for r in rolls}) == len(rolls)
    assert all(r["timing"] == "per_model" for r in rolls)


def test_02_02_03_other_random_weapon_values_are_per_weapon_and_use(
    section02_definitions: Section02Definitions,
) -> None:
    attacker = section02_definitions.unit(identity="constructed-weapon-owner")
    target = section02_definitions.unit(identity="target")
    source = section02_definitions.weapon(f"{INFRACTORS}:bolt-pistol")
    weapon = replace(
        source,
        profile_id="core-contract:random-strength",
        name="Constructed Core weapon",
        strength=RandomProfileValue(C.STRENGTH, DiceExpression(1, 6, 2), CONTRACT_SOURCE),
        source_ids=(CONTRACT_SOURCE,),
    )
    pool = attack_pool(attacker, target, weapon, f"{INFRACTORS}:bolt-pistol")
    decisions = DecisionController()
    manager = DiceRollManager("constructed-weapon", event_log=decisions.event_log)
    for model in attacker.own_models[:2]:
        physical = replace(
            pool,
            attacker_model_instance_id=model.model_instance_id,
            weapon_instance_id=f"core-contract:{model.model_instance_id}:weapon",
        )
        for occurrence in ("first-use", "second-use"):
            result = evaluate_attack_weapon_profile(
                pool=physical,
                decisions=decisions,
                manager=manager,
                attack_context_id=occurrence,
                player_id="owner",
                characteristics=(C.STRENGTH,),
            )
            assert 3 <= result.weapon_profile.strength.final <= 8
            before = decisions.event_log.to_payload()
            assert (
                evaluate_attack_weapon_profile(
                    pool=physical,
                    decisions=decisions,
                    manager=None,
                    attack_context_id=occurrence,
                    player_id="owner",
                    characteristics=(C.STRENGTH,),
                )
                == result
            )
            assert decisions.event_log.to_payload() == before
    rolls = [
        payload_object(e.payload)
        for e in decisions.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    assert len(rolls) == 4
    assert len({payload_text(r["scope_id"]) for r in rolls}) == 4
    assert all(r["timing"] == "per_weapon" for r in rolls)


def test_02_02_02_unqualified_contract_covers_rolls_models_and_weapons(
    section02_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.abilities import (
        GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        AbilityCatalogRecord,
        AbilityDefinition,
        AbilitySourceKind,
        AbilityTimingDescriptor,
    )
    from warhammer40k_core.engine.catalog_modifier_ignore import (
        catalog_modifier_ignore_permissions_for_unit,
    )
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleIR,
        RuleTargetKind,
        RuleTargetSpec,
        parameters_from_pairs,
    )

    text = "Constructed unqualified ignore-modifiers contract"
    span = TextSpan(text, 0, len(text))
    clause = RuleClause(
        "unqualified",
        span,
        target=RuleTargetSpec(RuleTargetKind.THIS_UNIT, span),
        effects=(
            RuleEffectSpec(
                RuleEffectKind.GRANT_ABILITY,
                span,
                parameters_from_pairs(
                    (("ability", "modifier_ignore_permission"), ("selection", "any_or_all"))
                ),
            ),
        ),
        duration=RuleDuration(RuleDurationKind.WHILE_CONDITION_TRUE, span),
    )
    rule = RuleIR(CONTRACT_SOURCE, CONTRACT_SOURCE, text, "constructed-contract", (clause,))
    definition = AbilityDefinition(
        CONTRACT_SOURCE,
        text,
        CONTRACT_SOURCE,
        "passive",
        text,
        "unqualified",
        AbilityTimingDescriptor(TimingTriggerKind.PASSIVE_QUERY),
        handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        replay_payload=validate_json_value({"rule_ir": rule.to_payload()}),
    )
    record = AbilityCatalogRecord(
        CONTRACT_SOURCE,
        definition,
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-contract",
    )
    unit = contract_unit(section02_definitions, CharacteristicValue.from_raw(C.MOVEMENT, 7))
    permissions = catalog_modifier_ignore_permissions_for_unit(
        ability_index=AbilityCatalogIndex.from_records((record,)),
        unit=unit,
        current_model_instance_ids=unit.own_model_ids(),
    )
    assert len(permissions) == 1
    assert {str(k) for k in permissions[0].modifier_kinds} == {
        "movement_characteristic",
        "advance_roll",
        "charge_roll",
        "desperate_escape_roll",
        "healing_roll",
        "toughness_characteristic",
        "save_characteristic",
        "invulnerable_save_characteristic",
        "wounds_characteristic",
        "leadership_characteristic",
        "objective_control_characteristic",
        "ballistic_skill_characteristic",
        "weapon_skill_characteristic",
        "strength_characteristic",
        "armor_penetration_characteristic",
        "attacks_characteristic",
        "damage_characteristic",
        "range_characteristic",
        "hit_roll",
        "wound_roll",
        "save_roll",
        "damage_roll",
        "leadership_roll",
        "battle_shock_roll",
    }
