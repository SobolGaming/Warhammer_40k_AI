"""16.01 start exclusions, same-native positive controls and read-only queries."""

from dataclasses import replace

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section10_fixtures import advanced
from tests.support.section16_fixtures import SPAWN, action, checkpoint

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.phases.movement import FellBackUnitState
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def reason(state: GameState, unit_id: str, player: str = "owner") -> str | None:
    return mission_action_unit_ineligibility_reason(
        state=state,
        player_id=player,
        unit_instance_id=unit_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )


@pytest.mark.parametrize(
    ("restriction", "expected"),
    [
        ("ordinary", None),
        ("off_battlefield", "mission_action_unit_off_battlefield"),
        ("AIRCRAFT", "mission_action_unit_aircraft"),
        ("FORTIFICATION", "mission_action_unit_fortification"),
        ("battle_shocked", "mission_action_unit_battle_shocked"),
        ("engaged", "mission_action_unit_engaged"),
        ("advanced", "mission_action_unit_advanced"),
        ("fell_back", "mission_action_unit_fell_back"),
        ("already_started", "mission_action_unit_already_started_action"),
    ],
)
def test_each_start_exclusion_has_native_positive_and_atomic_query(
    section16_definitions: Section02Definitions, restriction: str, expected: str | None
) -> None:
    control, native = checkpoint(section16_definitions)
    assert reason(control, native.unit_instance_id) is None
    state, unit = checkpoint(
        section16_definitions,
        supplement=restriction if restriction in {"AIRCRAFT", "FORTIFICATION"} else None,
        engaged=restriction == "engaged",
    )
    assert unit.own_model_ids() == native.own_model_ids()
    if restriction == "off_battlefield":
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(unit.unit_instance_id)
        )
    elif restriction == "battle_shocked":
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    elif restriction == "advanced":
        # A typed prior-Advance receipt; the preceding Movement phase is not replayed.
        advanced(state, unit)
    elif restriction == "fell_back":
        state.record_fell_back_unit_state(FellBackUnitState("owner", 1, unit.unit_instance_id))
    elif restriction == "already_started":
        state.record_mission_action_state(action(unit))
    before = state.to_payload()
    assert reason(state, unit.unit_instance_id) == expected
    assert state.to_payload() == before


@pytest.mark.parametrize("oc", [0, "-", 1])
def test_zero_and_dash_oc_excluded_positive_oc_eligible(
    section16_definitions: Section02Definitions, oc: int | str
) -> None:
    state, unit = checkpoint(section16_definitions)
    # Explicit Core characteristic boundary; printed native OC is retained in the
    # immutable definition. This does not claim a native '-' OC granting source.
    altered = replace(
        unit,
        own_models=tuple(
            replace(
                m,
                characteristics=tuple(
                    (
                        CharacteristicValue.source_dash(Characteristic.OBJECTIVE_CONTROL)
                        if oc == "-"
                        else CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, int(oc))
                    )
                    if c.characteristic is Characteristic.OBJECTIVE_CONTROL
                    else c
                    for c in m.characteristics
                ),
            )
            for m in unit.own_models
        ),
    )
    state.army_definitions[:] = [
        replace(a, units=(altered,)) if a.player_id == "owner" else a
        for a in state.army_definitions
    ]
    assert reason(state, unit.unit_instance_id) == (
        None if oc == 1 else "mission_action_unit_zero_objective_control"
    )


def test_native_spawn_positive_oc_is_eligible(section16_definitions: Section02Definitions) -> None:
    state, unit = checkpoint(section16_definitions, sheet=SPAWN)
    assert all(
        m.characteristic(Characteristic.OBJECTIVE_CONTROL).final > 0 for m in unit.own_models
    )
    assert reason(state, unit.unit_instance_id) is None


@pytest.mark.parametrize("titanic", [False, True])
def test_engagement_exception_is_only_titanic(
    section16_definitions: Section02Definitions, titanic: bool
) -> None:
    from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

    state, unit = checkpoint(
        section16_definitions, engaged=True, supplement="TITANIC" if titanic else None
    )
    assert unit_within_enemy_engagement_range(state=state, unit_instance_id=unit.unit_instance_id)
    assert reason(state, unit.unit_instance_id) == (
        None if titanic else "mission_action_unit_engaged"
    )


@pytest.mark.parametrize("other", ["AIRCRAFT", "FORTIFICATION"])
def test_titanic_does_not_override_other_keyword_exclusions(
    section16_definitions: Section02Definitions, other: str
) -> None:
    from tests.unit_keyword_helpers import with_unit_keywords

    state, unit = checkpoint(section16_definitions, supplement="TITANIC")
    replaced = with_unit_keywords(unit, keywords=tuple(sorted({*unit.keywords, other})))
    state.army_definitions[:] = [
        replace(a, units=(replaced,)) if a.player_id == "owner" else a
        for a in state.army_definitions
    ]
    assert reason(state, unit.unit_instance_id) == f"mission_action_unit_{other.lower()}"


def test_unit_must_belong_to_player(section16_definitions: Section02Definitions) -> None:
    state, unit = checkpoint(section16_definitions)
    assert reason(state, unit.unit_instance_id) is None
    assert reason(state, unit.unit_instance_id, "opponent") == "mission_action_unit_wrong_owner"


def test_both_players_have_same_native_action_eligibility(
    section16_definitions: Section02Definitions,
) -> None:
    state, unit = checkpoint(section16_definitions)
    enemy = next(a for a in state.army_definitions if a.player_id == "opponent").units[0]
    assert unit.datasheet_id == enemy.datasheet_id
    assert reason(state, unit.unit_instance_id, "owner") is None
    assert reason(state, enemy.unit_instance_id, "opponent") is None
