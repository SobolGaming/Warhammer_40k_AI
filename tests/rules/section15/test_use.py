"""15.01 and nested definitions at the shared history/identity restriction owner."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import binding, context, record
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagems_eligibility import (
    _restriction_violation,
    derive_stratagem_use_unit_ids,
)
from warhammer40k_core.engine.stratagems_model import StratagemUseRecord
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("none", "same_stratagem_per_phase"),
        ("other-stratagem", "targeted_unit_already_stratagem_target"),
        ("other-target", "same_stratagem_per_phase"),
        ("other-player", None),
        ("other-phase", None),
        ("other-round", None),
        ("other-turn", None),
        ("explicit-target-permission", None),
    ],
)
def test_each_players_use_and_target_limits_have_exact_phase_and_turn_scope(
    section15_definitions: Section02Definitions, change: str, expected: str | None
) -> None:
    d = section15_definitions
    first, other = d.unit(identity="first"), d.unit(identity="other")
    state = minimal_state(d, first, other)
    rec = record("epic-challenge")
    ctx = context(state, TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT)
    use = StratagemUseRecord(
        "constructed:s15:prior-use",
        "owner",
        rec.definition.stratagem_id,
        rec.definition.source_id,
        state.battle_round,
        BattlePhase.COMMAND,
        "owner",
        "constructed:s15:prior-window",
        "request",
        "result",
        "option",
        binding(first.unit_instance_id),
        (first.unit_instance_id,),
        (first.unit_instance_id,),
        1,
        None,
        rec.definition.handler_id,
    )
    state.stratagem_use_records.append(use)
    target = binding(first.unit_instance_id)
    definition = rec.definition
    if change in {"other-stratagem", "explicit-target-permission"}:
        definition = record("smokescreen").definition
    if change == "explicit-target-permission":
        definition = replace(
            definition,
            restriction_policy=replace(
                definition.restriction_policy, same_unit_target_per_phase=False
            ),
        )
    if change == "other-target":
        target = binding(other.unit_instance_id)
    if change == "other-player":
        ctx = replace(ctx, player_id="opponent")
    elif change == "other-phase":
        ctx = replace(ctx, phase=BattlePhase.MOVEMENT)
    elif change == "other-round":
        ctx = replace(ctx, battle_round=2)
    elif change == "other-turn":
        ctx = replace(ctx, active_player_id="opponent")
    before = state.to_payload()
    reason = _restriction_violation(
        state=state,
        player_id=ctx.player_id,
        definition=definition,
        context=ctx,
        target_binding=target,
    )
    assert reason == expected
    assert state.to_payload() == before


def test_target_and_collateral_affected_sets_do_not_expand_your_unit_target_scope(
    section15_definitions: Section02Definitions,
) -> None:
    d = section15_definitions
    unit, other = d.unit(identity="selected"), d.unit(identity="collateral")
    state = minimal_state(d, unit, other)
    ctx = context(state, TimingTriggerKind.DURING_PHASE)
    targets, affected = derive_stratagem_use_unit_ids(
        state=state,
        definition=record("explosives").definition,
        context=ctx,
        target_binding=binding(unit.unit_instance_id),
        effect_selection={
            "effect_selection_kind": "source_model_and_enemy_unit",
            "source_model_instance_id": unit.own_model_ids()[0],
            "enemy_target_unit_instance_id": other.unit_instance_id,
        },
    )
    assert targets == (unit.unit_instance_id,)
    assert set(affected) == {unit.unit_instance_id, other.unit_instance_id}
    assert other.unit_instance_id not in targets


def test_once_per_battle_brave_use_survives_phase_round_and_turn_changes(
    section15_definitions: Section02Definitions,
) -> None:
    d = section15_definitions
    unit = d.unit()
    state = minimal_state(d, unit)
    rec = record("insane-bravery")
    state.stratagem_use_records.append(
        StratagemUseRecord(
            "constructed:s15:bravery-history",
            "owner",
            rec.definition.stratagem_id,
            rec.definition.source_id,
            1,
            BattlePhase.COMMAND,
            "owner",
            None,
            "request",
            "result",
            "option",
            binding(unit.unit_instance_id),
            (unit.unit_instance_id,),
            (unit.unit_instance_id,),
            1,
            None,
            rec.definition.handler_id,
        )
    )
    ctx = replace(
        context(state, TimingTriggerKind.START_PHASE), battle_round=4, active_player_id="opponent"
    )
    assert (
        _restriction_violation(
            state=state,
            player_id="owner",
            definition=rec.definition,
            context=ctx,
            target_binding=binding(unit.unit_instance_id),
        )
        == "once_per_battle"
    )
