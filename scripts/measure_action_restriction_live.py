"""Representative live selection, effect-inventory and retained-reaction work."""

from __future__ import annotations

import cProfile
import time
from types import CodeType

from tests.indirect_shooting_helpers import (
    SHOOTER,
    complete_indirect_attack,
    indirect_session,
    select_indirect_declaration,
    submit_indirect_declaration,
)
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.retained_attack_helpers import pending_retained_attack

from warhammer40k_core.engine.damage_allocation import DestructionReactionKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.retained_destruction_state import retained_destructions
from warhammer40k_core.engine.shooting_types import ShootingType

LIVE_CASES = ("unrestricted", "attached_selection", "retained")
DIAGNOSTIC_CASE = "attached"
INVENTORY_SIZE = 32
WORK_METRICS = frozenset(
    {
        "rules_unit_view_by_id",
        "rules_unit_identity_ids",
        "persisting_effects_for_lineage",
        "applies_to_unit",
        "_legal_shooting_unit_ids",
        "_legal_charging_unit_ids",
        "invalid_shooting_unit_selection_status",
        "expire_persisting_effects_at_boundary",
        "resolve_line_of_sight",
        "resolve_visibility_pair",
        "resolve_visibility_pair_uncached",
        "decide_full",
    }
)


def live_sample(*, profile: bool, case: str) -> dict[str, object]:
    started = time.perf_counter()
    if case == "retained":
        session, _model = pending_retained_attack(
            reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH
        )
    elif case in ("unrestricted", "attached", "attached_selection"):
        session = indirect_session(
            observer=True,
            engager_attached=case in ("attached", "attached_selection"),
            engager_distance=10.0,
        )
    else:
        raise ValueError("Unknown Order 34 live workload.")
    state = session.lifecycle.state
    assert state is not None
    for index in range(INVENTORY_SIZE):
        state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"order34-workload-effect:{index:02d}",
                source_rule_id="order34-workload:inventory",
                owner_player_id="player-a",
                target_unit_instance_ids=(SHOOTER,),
                started_battle_round=state.battle_round,
                started_phase=BattlePhase.SHOOTING,
                expiration=EffectExpiration.end_turn(
                    battle_round=state.battle_round, player_id="player-a"
                ),
                effect_payload={"effect_kind": "order34_workload_inventory"},
            )
        )
    profiler = cProfile.Profile()
    prepared = time.perf_counter()
    initial_decisions = len(session.lifecycle.decision_controller.records)
    if profile:
        profiler.enable()
    if case == "retained":
        request = pending_request(session)
        option = next(
            option
            for option in request.options
            if isinstance(option.payload, dict) and option.payload.get("action") == "shoot"
        )
        session.submit_option(
            request_id=request.request_id,
            result_id="order34-live-retain",
            option_id=option.option_id,
        )
        for _ in range(60):
            request = pending_request(session)
            if request.decision_type == "submit_shooting_declaration":
                proposal = _proposal_from_request(request=request, target_unit_id=SHOOTER)
                session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id="order34-live-retained-declaration",
                    payload=validate_json_value(proposal.to_payload()),
                )
            else:
                submit_fixture_request(session, request)
            state = session.lifecycle.state
            assert state is not None
            if not retained_destructions(state=state):
                break
        else:
            raise AssertionError("Retained shooting continuation did not complete.")
    elif case == "attached_selection":
        request = pending_request(session)
        assert request.decision_type == "select_shooting_unit"
        session.submit_option(
            request_id=request.request_id, result_id="order34-attached-selection", option_id=SHOOTER
        )
        assert pending_request(session).decision_type == "select_shooting_type"
    else:
        request = select_indirect_declaration(session, ShootingType.NORMAL)
        submit_indirect_declaration(session, request)
        complete_indirect_attack(session)
    # Submit completion for the remaining shooting selection, then reach the
    # engine's actual charge option producer and complete the phase through it.
    reached_charge = False
    for index in range(40):
        if case == "attached_selection":
            break
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        reached_charge = any(
            event.event_type == "battle_phase_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("completed_phase") == "charge"
            for event in session.lifecycle.decision_controller.event_log.records
        )
        if reached_charge:
            break
        if request.decision_type == "select_charging_unit":
            reached_charge = True
        completion_option = next(
            (
                option
                for option in request.options
                if option.option_id.startswith("complete") or "decline" in option.option_id
            ),
            None,
        )
        if completion_option is None:
            raise AssertionError(
                f"Live transition requires a finite completion: {request.decision_type}"
            )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"order34-live-complete:{index}",
            option_id=completion_option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    else:
        raise AssertionError("Live phase transition exceeded its finite bound.")
    if profile:
        profiler.disable()
    completed = time.perf_counter()
    assert reached_charge or case == "attached_selection"
    counts: dict[str, int] = {}
    if profile:
        for entry in profiler.getstats():
            if isinstance(entry.code, CodeType) and entry.code.co_name in WORK_METRICS:
                name = entry.code.co_name
                counts[name] = counts.get(name, 0) + entry.callcount
    return {
        "case": case,
        "setup_seconds": prepared - started,
        "slice_seconds": completed - prepared,
        "inventory_size": INVENTORY_SIZE,
        "work_counts": counts,
        "decision_count": len(session.lifecycle.decision_controller.records) - initial_decisions,
        "reached_charge": reached_charge,
        "final_phase": state.current_battle_phase.value if state.current_battle_phase else None,
    }
