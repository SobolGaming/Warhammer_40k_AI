"""09.05.01/06/07: movement history reaches charge, shooting and Action consumers."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import choose, movement_case, propose, select
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.normal_move_history import NormalMoveSourceKind, NormalMoveState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.shooting_eligibility_state import shooting_state_restriction_reason
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("action", ["advance", "fall_back:ordered_retreat"])
def test_completed_move_blocks_charge_and_actions_through_the_rest_of_turn(
    section09_definitions: Section02Definitions,
    action: str,
) -> None:
    session, state, unit = movement_case(
        section09_definitions, engaged=action.startswith("fall_back")
    )
    request = choose(session, select(session, unit), action)
    ends = (
        (Pose.at(10, 6), Pose.at(12.5, 6))
        if action.startswith("fall_back")
        else (Pose.at(10, 11), Pose.at(12.5, 11))
    )
    propose(session, request, unit, ends)
    suffix = "fell_back" if action.startswith("fall_back") else "advanced"
    for phase in (BattlePhase.SHOOTING, BattlePhase.CHARGE, BattlePhase.FIGHT):
        # The move was native; enter only the downstream eligibility query boundary.
        state.battle_phase_index = state.battle_phase_sequence.index(phase)
        assert (
            charge_unit_ineligibility_reason(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                charge_state=ChargePhaseState(1, "owner"),
                ignore_already_selected=False,
            )
            == f"charge_unit_{suffix}"
        )
        assert (
            mission_action_unit_ineligibility_reason(
                state=state,
                player_id="owner",
                unit_instance_id=unit.unit_instance_id,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
            == f"mission_action_unit_{suffix}"
        )
        assert shooting_state_restriction_reason(
            state=state,
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
            player_id="owner",
        ) == ("fell_back" if suffix == "fell_back" else None)
    # The engine cleanup owner is the minimal exact end-of-turn boundary.
    state.clear_turn_action_states(player_id="owner", battle_round=1)
    assert not state.advanced_unit_states
    assert not state.fell_back_unit_states
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="owner",
            unit_instance_id=unit.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )


@pytest.mark.parametrize("phase", [BattlePhase.MOVEMENT, BattlePhase.SHOOTING])
@pytest.mark.parametrize("source", list(NormalMoveSourceKind))
def test_prior_normal_move_in_same_phase_blocks_another_normal_only(
    section09_definitions: Section02Definitions,
    phase: BattlePhase,
    source: NormalMoveSourceKind,
) -> None:
    session, state, unit = movement_case(section09_definitions)
    # Constructed prior completed Normal Move receipt; the selection consumer,
    # not this fixture, decides whether that receipt belongs to this occurrence.
    state.record_normal_move_state(
        NormalMoveState(
            "owner",
            "owner",
            1,
            phase,
            unit.unit_instance_id,
            "constructed:prior-normal",
            source,
            "prior-request",
            "prior-result",
        )
    )
    request = select(session, unit)
    assert ("normal_move" in {o.option_id for o in request.options}) is (
        phase is not BattlePhase.MOVEMENT
    )
    assert {"advance", "remain_stationary"}.issubset(o.option_id for o in request.options)


def test_normal_move_completion_records_actual_once_per_phase_history(
    section09_definitions: Section02Definitions,
) -> None:
    session, state, unit = movement_case(section09_definitions)
    request = choose(session, select(session, unit), "normal_move")
    propose(session, request, unit, (Pose.at(10, 11), Pose.at(12.5, 11)))
    assert len(state.normal_move_states) == 1
    record = state.normal_move_states[0]
    assert record.unit_instance_id == unit.unit_instance_id
    assert record.phase is BattlePhase.MOVEMENT
    assert record.source_kind is NormalMoveSourceKind.MOVEMENT_PHASE_ACTION
    before = tuple(state.normal_move_states)
    # Re-entering the real handler cannot make a second copy of its completion.
    from tests.support.section09_fixtures import begin

    begin(session)
    assert tuple(state.normal_move_states) == before


@pytest.mark.parametrize("action", ["advance", "fall_back:ordered_retreat"])
def test_explicit_charge_permission_is_consumed_by_shared_charge_owner(
    section09_definitions: Section02Definitions,
    action: str,
) -> None:
    session, state, unit = movement_case(
        section09_definitions, engaged=action.startswith("fall_back")
    )
    request = choose(session, select(session, unit), action)
    propose(
        session,
        request,
        unit,
        (Pose.at(10, 6), Pose.at(12.5, 6))
        if action.startswith("fall_back")
        else (Pose.at(10, 11), Pose.at(12.5, 11)),
    )
    # Constructed already-permitted grant boundary. This covers the downstream
    # exception, not admission of any named faction/ability provider.
    if action == "advance":
        state.advanced_unit_states[:] = [
            replace(r, can_declare_charge=True) for r in state.advanced_unit_states
        ]
    else:
        state.fell_back_unit_states[:] = [
            replace(r, can_declare_charge=True, can_shoot=True) for r in state.fell_back_unit_states
        ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert charge_unit_ineligibility_reason(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        charge_state=ChargePhaseState(1, "owner"),
        ignore_already_selected=False,
    ) not in {"charge_unit_advanced", "charge_unit_fell_back"}
    assert (
        shooting_state_restriction_reason(
            state=state,
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
            player_id="owner",
        )
        is None
    )
