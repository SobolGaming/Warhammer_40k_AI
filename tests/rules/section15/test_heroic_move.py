"""15.11 effect completes the shared witnessed Charge after its roll/target steps."""

from dataclasses import replace

from tests.generic_modifier_helpers import generic_effect
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section11_fixtures import propose, witness
from tests.support.section15_fixtures import checkpoint, context, offer, request, submit
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def test_heroic_roll_target_invalid_path_retry_and_accepted_native_move(
    section15_definitions: Section02Definitions,
) -> None:
    session, state, unit, enemy = checkpoint(
        section15_definitions, phase=BattlePhase.CHARGE, active="opponent", distance=5
    )
    state.charge_phase_state = ChargePhaseState(
        state.battle_round,
        "opponent",
        phase_complete=True,
        declared_target_unit_instance_ids_by_unit={enemy: (unit,)},
    )
    # Explicit source permission makes the geometric positive independent of RNG.
    # Printed native models and physical path constraints are unchanged.
    effect = generic_effect(
        effect_id="constructed:s15:charge-modifier",
        owner_player_id="owner",
        target_unit_instance_ids=(unit,),
        target_kind="this_unit",
        effect_kind="modify_dice_roll",
        parameters={"roll_type": "charge", "delta": 12},
    )
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="opponent"),
        )
    )
    req = offer(session, state, "heroic-intervention", context(state, TimingTriggerKind.END_PHASE))
    declaration = request(submit(session, req, unit, effect={"mode": "into_the_fray"}))
    targets = request(
        session.submit_option(
            request_id=declaration.request_id, result_id="s15:heroic-declare", option_id=unit
        )
    )
    target_option = next(o for o in targets.options if o.option_id != "decline_charge_targets")
    moving = request(
        session.submit_option(
            request_id=targets.request_id,
            result_id="s15:heroic-target",
            option_id=target_option.option_id,
        )
    )
    assert moving.decision_type == "submit_movement_proposal"
    before = state.battlefield_state
    invalid = propose(
        session, unit, (enemy,), witness(state, unit, 0), result_id="s15:heroic-invalid"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    accepted = propose(
        session, unit, (enemy,), witness(state, unit, 3), result_id="s15:heroic-legal"
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state != before
    assert state.active_player_id == "opponent"
    assert state.effective_active_player_id() == "opponent"
