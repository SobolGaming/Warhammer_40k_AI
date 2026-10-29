"""15.05/15.06: native physical sources, exact dice counts and selection guards."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import (
    binding,
    checkpoint,
    context,
    events,
    obj,
    offer,
    record,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.crushing_impact_selection import (
    crushing_impact_effect_selections,
    crushing_impact_mortal_wounds,
)
from warhammer40k_core.engine.explosives_selection import explosives_effect_selections
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_use_options
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def _health(state: GameState) -> dict[str, tuple[str, int, bool]]:
    return {
        model.model_instance_id: (unit.unit_instance_id, model.current_wounds, model.is_alive)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }


def test_native_explosives_source_rolls_six_and_applies_four_plus_mortals(
    section15_definitions: Section02Definitions,
) -> None:
    session, state, unit, enemy = checkpoint(
        section15_definitions, phase=BattlePhase.SHOOTING, distance=6
    )
    from dataclasses import replace

    from tests.support.section09_fixtures import add_unit
    from warhammer40k_core.geometry.pose import Pose

    bystander = section15_definitions.unit("000004078", identity="bystander")
    add_unit(state, bystander, (Pose.at(40, 40),))
    own = state.army_definition_for_player("owner")
    other = state.army_definition_for_player("opponent")
    assert own is not None
    assert other is not None
    source_model_id = own.unit_by_id(unit).own_models[0].model_instance_id
    target_model = other.unit_by_id(enemy).own_models[0]
    enemy_model_id = target_model.model_instance_id
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model

    # A normal already-wounded native enemy: no fabricated datasheet profile and
    # no preceding attack replay. The Stratagem must cause the eventual casualty.
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=enemy,
        model_instance_id=enemy_model_id,
        damage=target_model.current_wounds - 1,
        damage_kind=DamageKind.NORMAL,
    )
    before_health = _health(state)
    assert before_health[enemy_model_id] == (enemy, 1, True)
    state.starting_strength_records.sort(key=lambda row: row.unit_instance_id)

    # A serializable custom-layout checkpoint must declare custom component IDs;
    # it must not masquerade as the Companion's unplayed source terrain layout.
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        deployment_map_id="constructed:s15:deployment",
        terrain_layout_id="constructed:s15:terrain",
    )
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    ctx = context(state, TimingTriggerKind.DURING_PHASE)
    req = offer(session, state, "explosives", ctx)
    status = session.submit_option(
        request_id=req.request_id, result_id="s15:explosives", option_id=req.options[0].option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    payload = events(session, "explosives_resolved")[-1]
    values = payload["roll_state"]["original_result"]["values"]
    assert len(values) == 6
    assert payload["mortal_wounds"] == sum(v >= 4 for v in values)
    assert payload["mortal_wounds"] > 0
    assert payload["source_model_instance_id"] == source_model_id
    assert payload["explosives_unit_instance_id"] == unit
    assert payload["target_unit_instance_id"] == enemy
    after_health = _health(state)
    expected_wounds = max(0, before_health[enemy_model_id][1] - payload["mortal_wounds"])
    assert after_health[enemy_model_id] == (enemy, expected_wounds, expected_wounds > 0)
    assert expected_wounds == 0  # The native casualty is the actual SF15-001 refresh trigger.
    assert {m: h for m, h in after_health.items() if m != enemy_model_id} == {
        m: h for m, h in before_health.items() if m != enemy_model_id
    }
    assert (
        after_health[bystander.own_models[0].model_instance_id]
        == before_health[bystander.own_models[0].model_instance_id]
    )
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none(enemy) is None
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    assert _health(state) == after_health
    use = state.stratagem_use_records[-1]
    assert use.targeted_unit_instance_ids == (unit,)
    assert set(use.affected_unit_instance_ids) == {unit, enemy}
    assert state.command_point_total("owner") == 3
    from warhammer40k_core.engine.game_state import GameState

    # This is the authoritative state fragment. The clause checkpoint deliberately
    # has no admitted roster and therefore cannot certify full lifecycle replay.
    checkpoint_payload = state.to_payload()
    restored = GameState.from_payload(checkpoint_payload)
    assert restored.to_payload() == checkpoint_payload
    assert _health(restored) == after_health


@pytest.mark.parametrize(("distance", "legal"), [(6, True), (20, False), (1, False)])
def test_explosives_requires_selected_model_range_and_unengaged_units(
    section15_definitions: Section02Definitions, distance: float, legal: bool
) -> None:
    _session, state, unit, enemy = checkpoint(
        section15_definitions, phase=BattlePhase.SHOOTING, distance=distance
    )
    before = state.to_payload()
    choices = explosives_effect_selections(
        state=state,
        context=context(state, TimingTriggerKind.DURING_PHASE),
        target_binding=binding(unit),
    )
    assert bool(choices) is legal
    if choices:
        assert obj(choices[0])["enemy_target_unit_instance_id"] == enemy
        own = state.army_definition_for_player("owner")
        assert own is not None
        assert obj(choices[0])["source_model_instance_id"] in own.unit_by_id(unit).own_model_ids()
    assert state.to_payload() == before


@pytest.mark.parametrize("sheet", ["000004078", "000000599"])
def test_explosives_native_keyword_gate_excludes_non_grenades_vehicle(
    section15_definitions: Section02Definitions, sheet: str
) -> None:
    _session, state, unit, _ = checkpoint(
        section15_definitions, sheet=sheet, phase=BattlePhase.SHOOTING, distance=6
    )
    choices = explosives_effect_selections(
        state=state,
        context=context(state, TimingTriggerKind.DURING_PHASE),
        target_binding=binding(unit),
    )
    assert bool(choices) is (sheet == "000004078")


@pytest.mark.parametrize("can_shoot", [False, True])
def test_explosives_advance_restriction_applies_even_with_a_shooting_permission(
    section15_definitions: Section02Definitions, can_shoot: bool
) -> None:
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.phases.movement import (
        AdvancedUnitState,
        AdvanceRollRequest,
        AdvanceRollResult,
        MovementDiceRecord,
        MovementPhaseActionKind,
    )

    _session, state, unit, _ = checkpoint(
        section15_definitions, phase=BattlePhase.SHOOTING, distance=6
    )
    roll_request = AdvanceRollRequest.for_unit(
        request_id="constructed:s15:prior-advance",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="owner",
        unit_instance_id=unit,
    )
    rolled = DiceRollManager(state.game_id).roll_fixed(roll_request.spec, (3,))
    state.record_advanced_unit_state(
        AdvancedUnitState(
            "owner",
            state.battle_round,
            unit,
            MovementDiceRecord(
                "owner",
                state.battle_round,
                unit,
                MovementPhaseActionKind.ADVANCE,
                AdvanceRollResult.from_roll_state(request=roll_request, roll_state=rolled),
            ),
            can_shoot=can_shoot,
        )
    )
    before = state.to_payload()
    assert (
        explosives_effect_selections(
            state=state,
            context=context(state, TimingTriggerKind.DURING_PHASE),
            target_binding=binding(unit),
        )
        == ()
    )
    assert state.to_payload() == before


def test_native_maulerfiend_crushing_impact_rolls_selected_models_toughness(
    section15_definitions: Section02Definitions,
) -> None:
    session, state, unit, enemy = checkpoint(
        section15_definitions, sheet="000000968", phase=BattlePhase.CHARGE, distance=3
    )
    from tests.support.section09_fixtures import add_unit
    from warhammer40k_core.geometry.pose import Pose

    bystander = section15_definitions.unit("000004078", identity="bystander")
    add_unit(state, bystander, (Pose.at(40, 40),))
    before_health = _health(state)
    own = state.army_definition_for_player("owner")
    assert own is not None
    model = own.unit_by_id(unit).own_models[0]
    ctx = context(
        state, TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE, {"triggering_unit_instance_id": unit}
    )
    selections = crushing_impact_effect_selections(
        state=state, context=ctx, target_binding=binding(unit)
    )
    assert selections == (
        {"enemy_target_unit_instance_id": enemy, "model_instance_id": model.model_instance_id},
    )
    req = offer(session, state, "crushing-impact", ctx)
    status = session.submit_option(
        request_id=req.request_id, result_id="s15:impact", option_id=req.options[0].option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    payload = events(session, "crushing_impact_resolved")[-1]
    values = payload["roll_state"]["original_result"]["values"]
    assert len(values) == model.characteristic(Characteristic.TOUGHNESS).final
    assert payload["source_mortal_wounds"] == min(6, values.count(1))
    assert payload["enemy_mortal_wounds"] == min(6, sum(v >= 5 for v in values))
    assert payload["source_mortal_wounds"] > 0
    assert payload["enemy_mortal_wounds"] > 0
    assert payload["source_unit_instance_id"] == unit
    assert payload["source_model_instance_id"] == model.model_instance_id
    assert payload["target_unit_instance_id"] == enemy
    other = state.army_definition_for_player("opponent")
    assert other is not None
    enemy_model_id = other.unit_by_id(enemy).own_models[0].model_instance_id
    after_health = _health(state)
    for model_id, target_unit, amount in (
        (model.model_instance_id, unit, payload["source_mortal_wounds"]),
        (enemy_model_id, enemy, payload["enemy_mortal_wounds"]),
    ):
        expected = max(0, before_health[model_id][1] - amount)
        assert after_health[model_id] == (target_unit, expected, expected > 0)
    affected = {model.model_instance_id, enemy_model_id}
    assert {m: h for m, h in after_health.items() if m not in affected} == {
        m: h for m, h in before_health.items() if m not in affected
    }
    assert (
        after_health[bystander.own_models[0].model_instance_id]
        == before_health[bystander.own_models[0].model_instance_id]
    )
    assert state.stratagem_use_records[-1].targeted_unit_instance_ids == (unit,)


@pytest.mark.parametrize(
    ("faces", "expected"),
    [((1,) * 9 + (6,) * 9, (6, 6)), ((2, 3, 4), (0, 0)), ((1, 4, 5, 6), (1, 2))],
)
def test_crushing_independent_caps_and_exact_one_five_six_faces(
    faces: tuple[int, ...], expected: tuple[int, int]
) -> None:
    assert crushing_impact_mortal_wounds(faces) == expected


@pytest.mark.parametrize(
    ("active", "trigger", "legal"),
    [
        ("owner", TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE, True),
        ("opponent", TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE, False),
        ("owner", TimingTriggerKind.END_PHASE, False),
    ],
)
def test_crushing_impact_belongs_to_charging_unit_in_own_charge_window(
    section15_definitions: Section02Definitions,
    active: str,
    trigger: TimingTriggerKind,
    legal: bool,
) -> None:
    _session, state, unit, _ = checkpoint(
        section15_definitions,
        sheet="000000968",
        phase=BattlePhase.CHARGE,
        distance=3,
        active=active,
    )
    options = stratagem_use_options(
        state=state,
        catalog_records=(record("crushing-impact"),),
        context=context(state, trigger, {"triggering_unit_instance_id": unit}),
    )
    assert bool(options) is legal
