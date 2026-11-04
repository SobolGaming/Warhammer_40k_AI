"""Actual opponent model choice and mandatory saves despite impossible first armour."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from tests.support.section05_fixtures import contract_characteristic
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.attack_sequence_group_selection import (
    apply_damage_allocation_model_decision,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_result import DecisionResult


@pytest.mark.parametrize("impossible_first", [False, True])
def test_opponent_choice_and_faq09_later_better_save(
    section05_definitions: Section02Definitions, impossible_first: bool
) -> None:
    d = section05_definitions
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    if impossible_first:
        target = replace(
            target,
            own_models=(
                replace(
                    contract_characteristic(target.own_models[0], Characteristic.SAVE, 6),
                    wounds_remaining=1,
                ),
                *(
                    contract_characteristic(m, Characteristic.SAVE, 2)
                    for m in target.own_models[1:]
                ),
            ),
        )
    state, target, sequence = native_sequence(d, target=target, attacks=2)
    if impossible_first:
        pool = sequence.attack_pools[0]
        # Explicit AP boundary: first model needs 8+, later models need 4+.
        sequence = replace(
            sequence,
            attack_pools=(
                replace(
                    pool,
                    weapon_profile=replace(
                        pool.weapon_profile,
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -2
                        ),
                    ),
                ),
            ),
        )
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6, 6), (6, 6), (1, 6))
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    request = status.decision_request
    assert request.actor_id == "opponent"
    assert request.decision_type == "select_damage_allocation_model"
    assert len(request.options) == len(target.own_models) - (1 if impossible_first else 0)
    result = DecisionResult.for_request(
        result_id="s05:allocate",
        request=request,
        selected_option_id=request.options[-1].option_id,
    )
    decisions.submit_result(result)
    remaining, _, status = apply_damage_allocation_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=remaining,
        result=result,
        already_allocated_model_ids=(),
    )
    assert status is None
    steps = payloads(decisions, "attack_sequence_step")
    assert len([s for s in steps if s["step"] == "save"]) == 2
    assert model_by_id(
        state=state, model_instance_id=target.own_model_ids()[-1]
    ).current_wounds == (2 if impossible_first else 1)
    if impossible_first:
        assert not model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).is_alive
        rolls = payloads(decisions, "dice_rolled")
        assert len(rolls) == 6
        assert len(payloads(decisions, "model_destroyed")) == 1


@pytest.mark.parametrize("field", ["save", "invulnerable_save"])
@pytest.mark.parametrize("value", [None, 2, 6, 7, 8, 19])
def test_effective_save_characteristic_constructor_and_decoder(
    field: str, value: int | None
) -> None:
    from tests.save7_allocation_helpers import allocation_group
    from warhammer40k_core.engine.damage_allocation import AllocationGroup

    original = allocation_group(2, 2)
    group = (
        replace(original, save=value)
        if field == "save"
        else replace(original, invulnerable_save=value)
    )
    payload = original.to_payload()
    if field == "save":
        payload["save"] = value
    else:
        payload["invulnerable_save"] = value
    restored = AllocationGroup.from_payload(payload)
    assert restored == group
    observed = restored.save if field == "save" else restored.invulnerable_save
    assert observed == value
    assert value is None or type(observed) is int


@pytest.mark.parametrize("field", ["save", "invulnerable_save"])
@pytest.mark.parametrize("value", [True, False, 2.0, 7.0, "7", -1, 0, 1])
def test_effective_save_characteristic_rejects_malformed_values(field: str, value: object) -> None:
    from tests.save7_allocation_helpers import allocation_group
    from warhammer40k_core.engine.damage_allocation import AllocationGroup
    from warhammer40k_core.engine.phase import GameLifecycleError

    original = allocation_group(2, 2)
    if field == "save":
        with pytest.raises(GameLifecycleError):
            replace(original, save=cast(int, value))
    else:
        with pytest.raises(GameLifecycleError):
            replace(original, invulnerable_save=cast(int, value))
    payload = original.to_payload()
    if field == "save":
        payload["save"] = cast(int | None, value)
    else:
        payload["invulnerable_save"] = cast(int | None, value)
    with pytest.raises(GameLifecycleError):
        AllocationGroup.from_payload(payload)


def test_native_bloodletters_unit_and_allocation_roundtrip(
    selected_army_source_index: Path | None,
) -> None:
    import json

    from tests.daemons_native_source_helpers import BELAKOR, native_definitions
    from tests.save7_allocation_helpers import native_target
    from tests.support.section04_fixtures import combat_state
    from warhammer40k_core.engine.damage_allocation import (
        AllocationGroup,
        allocation_context_for_unit,
        allocation_groups_for_context,
    )
    from warhammer40k_core.engine.unit_factory import UnitInstance

    definitions = native_definitions(selected_army_source_index)
    target = native_target(selected_army_source_index)
    assert len(target.own_models) == 10
    restored = UnitInstance.from_payload(json.loads(json.dumps(target.to_payload())))
    assert restored == target
    state = combat_state(definitions, definitions.unit(BELAKOR), target=restored)
    groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context_for_unit(
            state=state, target_unit_instance_id=restored.unit_instance_id
        ),
    )
    assert len(groups) == 1
    group = groups[0]
    assert (group.wounds, group.save, group.invulnerable_save) == (1, 7, 5)
    assert group.model_ids == tuple(sorted(restored.own_model_ids()))
    assert ":sv7:" in group.group_id
    assert AllocationGroup.from_payload(json.loads(json.dumps(group.to_payload()))) == group


@pytest.mark.parametrize("phase", ["fight", "shooting"])
@pytest.mark.parametrize("target_sheet", ["000001114", "000004080"])
def test_native_save7_facade_completes_attack(
    selected_army_source_index: Path | None, phase: str, target_sheet: str
) -> None:
    from tests.save7_allocation_helpers import native_attack_session
    from tests.support.section04_fixtures import finish_attacks
    from tests.support.section05_sequence import payloads
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.phase import BattlePhase

    session, original = native_attack_session(
        selected_army_source_index, BattlePhase(phase), target_sheet=target_sheet
    )
    finish_attacks(session)
    decisions = session.lifecycle.decision_controller
    assert payloads(decisions, "attack_sequence_completed")
    steps = payloads(decisions, "attack_sequence_step")
    assert all(
        any(step["step"] == expected for step in steps)
        for expected in ("hit", "wound", "save", "damage")
    )
    state = session.lifecycle.state
    assert state is not None
    final = unit_by_id(state=state, unit_instance_id=original.unit_instance_id)
    assert sum(model.current_wounds for model in final.own_models) < sum(
        model.current_wounds for model in original.own_models
    )
    if target_sheet == "000001114":
        assert len(original.own_models) == 10
        assert all(
            model.characteristic(Characteristic.SAVE).final == 7 for model in final.own_models
        )


@pytest.mark.parametrize("character", [False, True])
def test_effective_save7_character_and_mixed_group_choices(
    selected_army_source_index: Path | None,
    character: bool,
) -> None:
    import json

    from tests.daemons_native_source_helpers import BELAKOR, native_definitions
    from tests.save7_allocation_helpers import modified_model, native_target
    from tests.support.section04_fixtures import combat_state
    from warhammer40k_core.engine.damage_allocation import (
        AllocationGroup,
        AllocationGroupRole,
        AllocationOrderDecision,
        allocation_context_for_unit,
        allocation_groups_for_context,
        build_allocation_order_request,
    )

    d = native_definitions(selected_army_source_index)
    target = native_target(selected_army_source_index, "000004078" if character else "000001114")
    first = target.own_models[0]
    first = modified_model(
        first,
        Characteristic.SAVE,
        (7 if character else 8) - first.characteristic(Characteristic.SAVE).final,
    )
    first = modified_model(
        first,
        Characteristic.INVULNERABLE_SAVE,
        8 - first.characteristic(Characteristic.INVULNERABLE_SAVE).final,
    )
    target = replace(target, own_models=(first, *target.own_models[1:]))
    state = combat_state(d, d.unit(BELAKOR), target=target)
    context = allocation_context_for_unit(
        state=state, target_unit_instance_id=target.unit_instance_id
    )
    if character:
        # Typed Core surviving-attached-character context on the native body;
        # this does not claim a native attachment provider or roster admission.
        context = replace(context, attached_unit_character_model_ids=target.own_model_ids())
    groups = allocation_groups_for_context(state=state, allocation_context=context)
    assert {g.save for g in groups} == ({7} if character else {7, 8})
    assert any(g.invulnerable_save == 8 for g in groups)
    if character:
        assert len(groups) == 1
        assert groups[0].role in {AllocationGroupRole.CHARACTER, AllocationGroupRole.LEADER}
        assert groups[0].character_model_ids == target.own_model_ids()
    else:
        assert all(g.role is AllocationGroupRole.NON_CHARACTER for g in groups)
    assert (
        tuple(AllocationGroup.from_payload(json.loads(json.dumps(g.to_payload()))) for g in groups)
        == groups
    )
    if character:
        # One group is forced; it must not invent an allocation-order choice.
        from warhammer40k_core.engine.phase import GameLifecycleError

        with pytest.raises(GameLifecycleError, match="at least two legal orders"):
            build_allocation_order_request(
                request_id="save7:forced",
                defender_player_id="opponent",
                attack_context={"attack_context_id": "save7:forced"},
                allocation_context=context,
                allocation_groups=groups,
            )
        return
    request = build_allocation_order_request(
        request_id="save7:mixed",
        defender_player_id="opponent",
        attack_context={"attack_context_id": "save7:mixed"},
        allocation_context=context,
        allocation_groups=groups,
    )
    assert request.actor_id == "opponent"
    assert len(request.options) == 2
    assert isinstance(request.payload, dict)
    assert all(
        g.to_payload() in cast(list[object], request.payload["allocation_groups"]) for g in groups
    )
    result = DecisionResult.for_request(
        request=request,
        result_id="save7:mixed:result",
        selected_option_id=request.options[-1].option_id,
    )
    selection = AllocationOrderDecision.from_result(request=request, result=result)
    assert {group.save for group in selection.allocation_groups} == {7, 8}
    assert selection.ordered_group_ids == tuple(reversed([g.group_id for g in groups]))


@pytest.mark.parametrize("threshold", [True, 2.0, "2", -1, 0, 1, 7, 8])
def test_effective_save_widening_keeps_d6_and_fnp_bounds(threshold: object) -> None:
    from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
    from warhammer40k_core.engine.damage_allocation_validation import validate_d6_target
    from warhammer40k_core.engine.phase import GameLifecycleError

    with pytest.raises(GameLifecycleError):
        validate_d6_target("save7:bounded-control", threshold)
    with pytest.raises(GameLifecycleError):
        FeelNoPainSource("save7:fnp", cast(int, threshold))
    for valid in (2, 6):
        assert validate_d6_target("save7:bounded-control", valid) == valid
        assert FeelNoPainSource("save7:fnp", valid).threshold == valid
