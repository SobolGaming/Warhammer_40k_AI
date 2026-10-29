"""11.00/01/03 and 11.04 bonus: actual boundary effects and consumers."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_timing import timing_session
from tests.support.section11_fixtures import (
    events,
    modifier,
    propose,
    select,
    session_for,
    state_case,
    targets,
    witness,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.fights_first import FightsFirstRegistry, fights_first_model_inventory
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_event_phase_hooks import end_bindings
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("position", ["start", "end"])
def test_nonempty_compiled_charge_rules_surround_body_exactly_once(
    section11_definitions: Section02Definitions,
    active: str,
    position: str,
) -> None:
    state, _, _ = state_case(section11_definitions)
    from dataclasses import replace

    from tests.support.section09_fixtures import unplace

    spare = next(
        u
        for a in state.army_definitions
        for u in a.units
        if u.unit_instance_id == "section02:spare"
    )
    state.replace_battlefield_state(unplace(state, spare))
    state.army_definitions[:] = [
        replace(a, units=tuple(u for u in a.units if u.unit_instance_id != spare.unit_instance_id))
        for a in state.army_definitions
    ]
    state.starting_strength_records[:] = [
        r for r in state.starting_strength_records if r.unit_instance_id != spare.unit_instance_id
    ]
    state.active_player_id = active
    session = timing_session(
        section11_definitions, state, f"At the {position} of your Charge phase"
    )
    index = session.lifecycle._require_battle_round_flow()._runtime_event_index  # pyright: ignore[reportPrivateUsage]
    handler = ChargePhaseHandler(ruleset_descriptor=state.runtime_ruleset_descriptor())
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.CHARGE: handler},
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=session.lifecycle.config.army_catalog,
        runtime_event_index=index,
        turn_end_hooks=TurnEndHookRegistry.from_bindings(end_bindings(index)),
    )
    decisions = session.lifecycle.decision_controller
    for i in range(8):
        status = flow.advance(state=state, decisions=decisions)
        if state.current_battle_phase is BattlePhase.FIGHT:
            break
        request = status.decision_request
        assert request is not None
        assert request.actor_id == active
        assert request.decision_type == "select_charging_unit"
        result = DecisionResult.for_request(
            result_id=f"phase-complete:{i}",
            request=request,
            selected_option_id="complete_charge_phase",
        )
        decisions.submit_result(result)
        handler.apply_decision(state=state, result=result, decisions=decisions)
    else:
        pytest.fail("Charge phase boundary did not complete")
    gains = events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(active == "owner")
    types = [e.event_type for e in decisions.event_log.records]
    assert types.count("charge_phase_completed") == 1
    assert types.count("battle_phase_completed") == 1
    if gains:
        assert gains[0]["passed"] is True
        assert state.command_point_total("owner") == 1
        effect = types.index("catalog_ir_command_point_phase_gain_resolved")
        assert (
            (effect < types.index("charging_unit_selection_requested"))
            if position == "start"
            else (
                types.index("charge_phase_completed")
                < effect
                < types.index("battle_phase_completed")
            )
        )


def test_completed_charge_grants_every_physical_model_bonus_until_turn_end(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    modifier(state, unit.unit_instance_id, 12)
    session = session_for(section11_definitions, state)
    select(session, unit)
    targets(session, (enemy.unit_instance_id,))
    result = propose(
        session,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 4.25),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    registry = FightsFirstRegistry.from_state(state)
    assert registry.charged_unit_ids() == (unit.unit_instance_id,)
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    present, grants = fights_first_model_inventory(state=state, view=view)
    assert present == unit.own_model_ids()
    charge_grants = [
        ids for source, ids in grants if source.effect_kind == "charge_grants_fights_first"
    ]
    assert charge_grants == [unit.own_model_ids()]
    effect = next(
        e
        for e in state.persisting_effects
        if isinstance(e.effect_payload, dict)
        and e.effect_payload.get("effect_kind") == "charge_grants_fights_first"
    )
    assert effect.target_unit_instance_ids == (unit.unit_instance_id,)
    assert effect.owner_player_id == "owner"
    assert state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, phase=BattlePhase.CHARGE, player_id="owner"
        )
    ) != (effect,)
    assert FightsFirstRegistry.from_state(state).charged_unit_ids() == (unit.unit_instance_id,)
    assert effect not in state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=1, player_id="opponent")
    )
    assert effect in state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=1, player_id="owner")
    )
    assert FightsFirstRegistry.from_state(state).charged_unit_ids() == ()
