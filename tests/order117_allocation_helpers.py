"""Canonical Core permission fixtures; named Stratagem activation stays load-only."""

from __future__ import annotations

from tests.lethal_hits_helpers import attack_completed
from tests.order116_mortal_helpers import additional_mortal_session
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mortal_wound_allocation_permissions import (
    mortal_wound_allocation_permission_effect,
)
from warhammer40k_core.engine.phase import BattlePhase

SOURCE_ID = (
    "gw-11e-phase17e-exact-faction-subrules-2026-27:"
    "stratagem:adeptus-custodes:shield-host:000008394002"
)
PERMISSION_ID = "order117:allocation-permission"


def allocation_permission_session(
    phase: BattlePhase,
    *,
    decline_allowed: bool = False,
    existing_optional_fnp: bool = False,
    enemy_models: int = 2,
    permission_target_is_attacker: bool = False,
    command_reroll_player_id: str | None = None,
    threshold: int = 4,
) -> LocalGameSession:
    session = additional_mortal_session(
        phase,
        mortal_wounds=12,
        attacks=3,
        armor_penetration=0,
        enemy_models=enemy_models,
        optional_fnp=existing_optional_fnp,
        command_reroll_player_id=command_reroll_player_id,
    )
    state = session.lifecycle.state
    assert state is not None
    target = state.army_definitions[0 if permission_target_is_attacker else 1].units[0]
    state.record_persisting_effect(
        mortal_wound_allocation_permission_effect(
            state=state,
            effect_id=PERMISSION_ID,
            source_rule_id=SOURCE_ID,
            target_unit_instance_id=target.unit_instance_id,
            occasion_id="order117:provider-authorized-occasion",
            threshold=threshold,
            decline_allowed=decline_allowed,
        )
    )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))


def complete_allocation_attack(session: LocalGameSession, *, decline: bool = False) -> None:
    for _ in range(150):
        if attack_completed(session):
            return
        request = pending_request(session)
        if request.decision_type == "select_feel_no_pain" and not decline:
            options = [
                option
                for option in request.options
                if isinstance(option.payload, dict) and option.payload.get("source_id") is not None
            ]
            assert options
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:fixture-choice",
                option_id=options[-1].option_id,
            )
        else:
            submit_fixture_request(session, request)
    raise AssertionError("Allocation-trigger attack did not complete.")
