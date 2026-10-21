"""15.02: actual native-unit roll ownership and complete versus component rerolls."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import checkpoint, context, events, offer, request
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_use_options
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize(
    "roll_type",
    [
        "advance_roll",
        "charge_roll",
        "damage_roll",
        "hazardous_test",
        "hit_roll",
        "save_roll",
        "wound_roll",
        "number_of_attacks_roll",
    ],
)
def test_every_adopted_command_reroll_class_resolves_the_recorded_roll(
    section15_definitions: Section02Definitions, roll_type: str
) -> None:
    session, state, unit, _ = checkpoint(section15_definitions, phase=BattlePhase.SHOOTING)
    decisions = session.lifecycle.decision_controller
    quantity = 2 if roll_type == "charge_roll" else 1
    roll = DiceRollManager(state.game_id, event_log=decisions.event_log).roll_fixed(
        DiceRollSpec(
            DiceExpression(quantity, 6),
            "constructed:s15:roll-boundary",
            roll_type=roll_type,
            actor_id="owner",
        ),
        (1,) * quantity,
    )
    req = offer(
        session,
        state,
        "command-reroll",
        context(
            state,
            TimingTriggerKind.AFTER_DICE_ROLL,
            {"dice_roll_state": roll.to_payload(), "affected_unit_instance_id": unit},
        ),
    )
    status = session.submit_option(
        request_id=req.request_id,
        result_id="s15:reroll",
        option_id=req.options[0].option_id,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    payload = events(session, "command_reroll_resolved")[-1]
    updated = payload["updated_roll_state"]
    assert updated["original_result"] == roll.to_payload()["original_result"]
    assert updated["rerolls"][0]["selected_indices"] == list(range(quantity))
    assert len(updated["rerolls"]) == 1
    assert state.command_point_total("owner") == 3
    assert state.stratagem_use_records[-1].targeted_unit_instance_ids == (unit,)


@pytest.mark.parametrize("selected", [0, 1])
def test_non_charge_multiple_dice_rerolls_only_selected_component(
    section15_definitions: Section02Definitions, selected: int
) -> None:
    session, state, unit, _ = checkpoint(section15_definitions, phase=BattlePhase.SHOOTING)
    roll = DiceRollManager(
        state.game_id, event_log=session.lifecycle.decision_controller.event_log
    ).roll_fixed(
        DiceRollSpec(
            DiceExpression(2, 6),
            "constructed:s15:pooled-attacks",
            roll_type="number_of_attacks_roll",
            actor_id="owner",
        ),
        (1, 5),
    )
    req = offer(
        session,
        state,
        "command-reroll",
        context(
            state,
            TimingTriggerKind.AFTER_DICE_ROLL,
            {"dice_roll_state": roll.to_payload(), "affected_unit_instance_id": unit},
        ),
    )
    reroll = request(
        session.submit_option(
            request_id=req.request_id,
            result_id="s15:choose-stratagem",
            option_id=req.options[0].option_id,
        )
    )
    assert tuple(o.option_id for o in reroll.options) == ("decline", "reroll:0", "reroll:1")
    session.submit_option(
        request_id=reroll.request_id, result_id="s15:choose-die", option_id=f"reroll:{selected}"
    )
    updated = events(session, "command_reroll_resolved")[-1]["updated_roll_state"]
    assert updated["rerolls"][0]["selected_indices"] == [selected]
    assert updated["current_values"][1 - selected] == (1, 5)[1 - selected]
    assert state.command_point_total("owner") == 3


@pytest.mark.parametrize(
    ("roll_type", "actor", "forbidden"),
    [
        ("battle_shock_roll", "owner", ()),
        ("desperate_escape_roll", "owner", ()),
        ("advance_roll", "opponent", ()),
        ("hit_roll", "owner", ("core:snap-shooting",)),
    ],
)
def test_unlisted_enemy_and_snap_forbidden_rolls_have_no_offer_or_spend(
    section15_definitions: Section02Definitions,
    roll_type: str,
    actor: str,
    forbidden: tuple[str, ...],
) -> None:
    from tests.support.section15_fixtures import record

    session, state, unit, _ = checkpoint(section15_definitions)
    roll = DiceRollManager(
        state.game_id, event_log=session.lifecycle.decision_controller.event_log
    ).roll_fixed(
        DiceRollSpec(
            DiceExpression(1, 6),
            "constructed:s15:ineligible-roll",
            roll_type=roll_type,
            actor_id=actor,
            reroll_forbidden_rule_ids=forbidden,
        ),
        (1,),
    )
    before = state.to_payload()
    options = stratagem_use_options(
        state=state,
        catalog_records=(record("command-reroll"),),
        context=context(
            state,
            TimingTriggerKind.AFTER_DICE_ROLL,
            {"dice_roll_state": roll.to_payload(), "affected_unit_instance_id": unit},
        ),
    )
    assert options == ()
    assert state.to_payload() == before
