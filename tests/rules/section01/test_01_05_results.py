"""Physical dice groups and automatic outcomes use production semantic owners."""

from dataclasses import replace
from itertools import combinations

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_consumers import attack_pool, payload_object
from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.dice_errors import DiceRollSpecError
from warhammer40k_core.core.dice_extremum import (
    DiceExtremum,
    DiceExtremumSelection,
    extremum_indices,
)
from warhammer40k_core.engine.attack_sequence_model import HitRoll, WoundRoll
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters.army_rule import (
    BlessingOfKhorne,
    _matching_allocations,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize("count", [2, 3])
@pytest.mark.parametrize("face", range(1, 7))
def test_01_05_06_double_triple_at_least_required_equal_dice(count: int, face: int) -> None:
    blessing = (
        BlessingOfKhorne.UNBRIDLED_BLOODLUST if count == 2 else BlessingOfKhorne.MARTIAL_EXCELLENCE
    )
    for copies in range(1, 5):
        values = (face,) * copies + ((face % 6) + 1,)
        actual = {
            indices for indices in _matching_allocations(values, blessing) if len(indices) == count
        }
        expected = {
            indices
            for indices in combinations(range(len(values)), count)
            if len({values[i] for i in indices}) == 1
        }
        assert actual == expected


@pytest.mark.parametrize("extremum", list(DiceExtremum))
@pytest.mark.parametrize("values", [(1, 6, 3), (2, 2, 5), (5, 5, 2), (4, 4, 4)])
def test_01_05_07_only_extreme_physical_dice_can_be_selected(
    extremum: DiceExtremum, values: tuple[int, ...]
) -> None:
    roll = DiceRollManager("extreme").roll_fixed(
        DiceRollSpec(
            DiceExpression(len(values), 6),
            reason="Core contract",
            roll_type="contract",
            actor_id="opponent",
        ),
        values,
    )
    expected = (max if extremum is DiceExtremum.HIGHEST else min)(values)
    assert extremum_indices(roll, extremum) == tuple(
        i for i, v in enumerate(values) if v == expected
    )
    for index, value in enumerate(values):
        if value == expected:
            selected = DiceExtremumSelection(roll, extremum, index)
            assert selected.component_id.endswith(f":component-{index}")
            assert selected.value == expected
        else:
            with pytest.raises(DiceRollSpecError, match="not a matching"):
                DiceExtremumSelection(roll, extremum, index)


@pytest.mark.parametrize("kind", ["hit", "wound"])
def test_01_05_01_automatic_outcome_has_no_die_and_no_critical(kind: str) -> None:
    outcome = (
        HitRoll.auto_hit(target_number=None)
        if kind == "hit"
        else WoundRoll.auto_wound(strength=None, toughness=None, target_number=None)
    )
    assert outcome.successful
    assert outcome.skipped
    assert not outcome.critical
    assert outcome.roll_state is None
    assert outcome.unmodified_roll is None
    assert outcome.final_roll is None


def test_01_05_01_automatic_hit_advances_to_wound_without_hit_die(
    section01_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound
    from warhammer40k_core.engine.attack_sequence_model import AttackSequenceHooks
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    attacker = section01_definitions.unit(identity="attacker")
    target = section01_definitions.unit(identity="target", army_id="opponent-army")
    state = minimal_state(section01_definitions, attacker)
    state.army_definitions.append(
        replace(
            state.army_definitions[0],
            army_id="opponent-army",
            player_id="opponent",
            units=(target,),
        )
    )
    place_units(state)
    native = section01_definitions.weapon(f"{INFRACTORS}:bolt-pistol")
    # Explicit Core automatic-hit contract, not a Torrent grant to native Infractors.
    contract = replace(
        native,
        profile_id="constructed:automatic-hit",
        name="Core automatic-hit contract",
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
        ability_sources=(),
        source_ids=("constructed:section01:automatic-hit",),
    )
    pool = attack_pool(attacker, target, contract, "constructed:automatic-hit")
    sequence = AttackSequence("automatic", "owner", attacker.unit_instance_id, (pool,))
    decisions = DecisionController()
    manager = DiceRollManager("automatic", event_log=decisions.event_log)
    _, status = _roll_hit_and_wound(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=sequence,
        hooks=AttackSequenceHooks.empty(),
        stratagem_index=None,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status is None
    events = decisions.event_log.to_payload()
    steps = [
        payload_object(e["payload"]) for e in events if e["event_type"] == "attack_sequence_step"
    ]
    assert [e["step"] for e in steps] == ["hit", "wound"]
    hit = payload_object(steps[0]["payload"])
    wound = payload_object(steps[1]["payload"])
    assert hit["skipped"] is True
    assert hit["roll_state"] is None
    assert hit["critical"] is False
    assert hit["generated_hits"] == 1
    assert wound["skipped"] is False
    assert wound["roll_state"] is not None
    rolls = [payload_object(e["payload"]) for e in events if e["event_type"] == "dice_rolled"]
    assert len(rolls) == 1


@pytest.mark.parametrize(
    ("pair", "expected"),
    [
        ((1, 2), "lay_low_the_tyrant"),
        ((3, 4), "reclaim_the_realm"),
        ((5, 6), "reap_a_great_tally"),
    ],
)
def test_01_05_inclusive_ranges_in_real_dice_table(pair: tuple[int, int], expected: str) -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.imperial_knights import (
        army_rule as knights,
    )

    assert {knights._deed_from_d6(value).value for value in pair} == {expected}  # pyright: ignore[reportPrivateUsage]
