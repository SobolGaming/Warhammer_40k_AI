"""12.01/12.09 timing and FAQ2 selection completion with explicit constructed equipment."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import choose, pending
from tests.support.section09_timing import timing_session
from tests.support.section12_fixtures import (
    begin,
    checkpoint,
    engaged_case,
    events,
    session_for,
)
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.boundary_rule_flow import request_end_rules
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartHookRegistry
from warhammer40k_core.engine.fight_resolution import FightMovementProposal
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.runtime_event_phase_hooks import end_bindings, fight_start_bindings
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry


def _unequip(s: GameState) -> None:
    # Native bodies, characteristics, geometry and abilities; zero equipment is
    # constructed because this selected supported catalog has no unarmed unit.
    s.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                replace(
                    u,
                    own_models=tuple(replace(m, wargear_ids=()) for m in u.own_models),
                    wargear_selections=(),
                )
                for u in a.units
            ),
        )
        for a in s.army_definitions
    ]


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("position", ["start", "end"])
def test_nonempty_compiled_fight_boundary_rule_resolves_once_at_its_own_boundary(
    section12_definitions: Section02Definitions, active: str, position: str
) -> None:
    s, _u, _e = engaged_case(section12_definitions)
    _unequip(s)
    s.active_player_id = active
    session = timing_session(section12_definitions, s, f"At the {position} of your Fight phase")
    index = session.lifecycle._require_battle_round_flow()._runtime_event_index  # pyright: ignore[reportPrivateUsage]
    config = session.lifecycle.config
    handler = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        fight_phase_start_hooks=FightPhaseStartHookRegistry.from_bindings(
            fight_start_bindings(index)
        ),
    )
    registry = TurnEndHookRegistry.from_bindings(end_bindings(index))
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: handler},
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        runtime_event_index=index,
        turn_end_hooks=registry,
    )
    decisions = session.lifecycle.decision_controller
    for i in range(32):
        status = (
            flow.advance(state=s, decisions=decisions)
            if i == 0
            else handler.begin_phase(state=s, decisions=decisions)
        )
        r = status.decision_request
        if r is None:
            from warhammer40k_core.engine.phase import LifecycleStatusKind

            assert status.status_kind is LifecycleStatusKind.ADVANCED, status
            assert s.fight_phase_state is not None
            if s.fight_phase_state.current_step is FightPhaseStepKind.END:
                break
            continue
        if r.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(r.payload)
            from warhammer40k_core.core.ruleset_descriptor import MovementMode

            assert move.movement_phase_action is not None
            p = FightMovementProposal(
                move.request_id,
                move.proposal_kind,
                move.unit_instance_id,
                move.movement_phase_action,
                MovementMode.PILE_IN
                if move.proposal_kind.value == "pile_in"
                else MovementMode.CONSOLIDATE,
            )
            result = replace(
                DecisionResult.for_request(
                    result_id=f"timing:{i}", request=r, selected_option_id=r.options[0].option_id
                ),
                payload=validate_json_value(p.to_payload()),
            )
        else:
            option = next((o for o in r.options if o.option_id.endswith(":decline")), r.options[0])
            result = DecisionResult.for_request(
                result_id=f"timing:{i}", request=r, selected_option_id=option.option_id
            )
        decisions.submit_result(result)
        handler.apply_decision(state=s, result=result, decisions=decisions)
        if (
            s.fight_phase_state is not None
            and s.fight_phase_state.current_step is FightPhaseStepKind.END
        ):
            handler.begin_phase(state=s, decisions=decisions)
            break
    else:
        pytest.fail("bounded real Fight body did not complete")
    gains = events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(position == "start" and active == "owner")
    for _ in range(2):
        end_status = request_end_rules(
            state=s,
            decisions=decisions,
            registry=registry,
            trigger_kind=TimingTriggerKind.END_PHASE,
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        assert end_status is None, end_status
    gains = events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(active == "owner")
    types = [x.event_type for x in decisions.event_log.records]
    if gains:
        gain = types.index("catalog_ir_command_point_phase_gain_resolved")
        moves = [i for i, x in enumerate(types) if x == "fight_movement_completed"]
        assert len(moves) == 4
        assert gain < min(moves) if position == "start" else gain > max(moves)
        assert s.command_point_total("owner") == 1


def test_faq2_unequipped_native_body_is_selected_and_resolves_without_attacks(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, _e = engaged_case(section12_definitions)
    _unequip(s)
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    r = begin(session)
    choose(session, r, r.options[0].option_id)
    assert len(events(session, "fight_activation_selected")) == 1
    assert len(events(session, "fight_activation_completed")) == 1
    assert not events(session, "attack_sequence_step")
    assert not events(session, "unit_has_fought")
    assert pending(session).actor_id == "opponent"
    assert all(u.unit_instance_id not in o.option_id for o in pending(session).options)
