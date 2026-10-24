"""Fight activation validation and ordinary attacks through native public decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section12_fixtures import (
    begin,
    checkpoint,
    declare,
    engaged_case,
    events,
    finish_activation,
    melee_payload,
    select_fight,
    session_for,
)
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind


@pytest.mark.parametrize("field", ["actor", "request", "unit", "phase", "fight_type"])
def test_invalid_activation_context_preserves_queue_state_and_valid_continuation(
    section12_definitions: Section02Definitions, field: str
) -> None:
    s, u, _ = engaged_case(section12_definitions)
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    r = begin(session)
    result = DecisionResult.for_request(
        result_id="invalid", request=r, selected_option_id=r.options[0].option_id
    )
    assert isinstance(result.payload, dict)
    base_payload = result.payload
    if field == "actor":
        result = replace(result, actor_id="opponent")
    elif field == "request":
        result = replace(result, request_id="stale")
    else:
        result = replace(
            result,
            payload=base_payload | {"unit_instance_id": "enemy:target"}
            if field == "unit"
            else base_payload | {"phase": "shooting"}
            if field == "phase"
            else base_payload | {"fight_type": "absent"},
        )
    before = s.to_payload()
    records = session.lifecycle.decision_controller.records
    status = session.lifecycle.submit_decision(result)
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert s.to_payload() == before
    assert pending(session) == r
    assert session.lifecycle.decision_controller.records == records
    r = select_fight(session, u.unit_instance_id)
    assert r.decision_type == "submit_melee_declaration"
    status = declare(session)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    finish_activation(session)
    assert len(events(session, "unit_has_fought")) == 1


@pytest.mark.parametrize("field", ["target", "physical_weapon", "bearer", "stale", "empty"])
def test_melee_rejection_never_counts_as_fought_and_legal_attack_retry_completes(
    section12_definitions: Section02Definitions, field: str
) -> None:
    s, u, _ = engaged_case(section12_definitions)
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    begin(session)
    r = select_fight(session, u.unit_instance_id)
    payload = cast(dict[str, JsonValue], melee_payload(r))
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    if field == "target":
        declarations[0]["target_allocations"] = [{"target_unit_instance_id": u.unit_instance_id}]
    if field == "physical_weapon":
        declarations[0]["weapon_instance_id"] = "absent"
    if field == "bearer":
        declarations[0]["attacker_model_instance_id"] = "absent"
    if field == "stale":
        payload["proposal_request_id"] = "stale"
    if field == "empty":
        payload["declarations"] = []
    before = s.to_payload()
    records = session.lifecycle.decision_controller.records
    status = session.submit_parameterized_payload(
        request_id=r.request_id, result_id="invalid-melee", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert s.to_payload() == before
    assert pending(session) == r
    assert session.lifecycle.decision_controller.records == records
    assert not events(session, "unit_has_fought")
    assert not events(session, "attack_sequence_step")
    status = declare(session)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    finish_activation(session)
    assert len(events(session, "unit_has_fought")) == 1
    assert len(events(session, "attack_sequence_completed")) == 1
    assert pending(session).actor_id == "opponent"


def test_remaining_combat_returns_to_first_band_when_new_permission_is_consumed(
    section12_definitions: Section02Definitions,
) -> None:
    from tests.support.section12_fixtures import LORD, add_native, paths, submit_move
    from warhammer40k_core.geometry.pose import Pose

    s, u, e = engaged_case(section12_definitions)
    late = section12_definitions.unit(LORD, identity="late-first", army_id="enemy")
    add_native(s, late, (Pose.at(10, 14.3),), enemy=True)
    s.record_persisting_effect(
        PersistingEffect(
            effect_id="constructed:new-first",
            source_rule_id="constructed:new-first",
            owner_player_id="opponent",
            target_unit_instance_ids=(late.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhase.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=BattlePhase.FIGHT, player_id="owner"
            ),
            effect_payload={"effect_kind": "fights_first"},
        )
    )
    # Constructed Fight-step checkpoint: source became engaged after step start.
    # Actual Overrun Pile In below makes the previously unengaged FF enemy eligible.
    checkpoint(s, FightPhaseStepKind.FIGHT, engaged_ids=(e.unit_instance_id,))
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert r.actor_id == "owner"
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["ordering_band"]) for o in r.options
    } == {"remaining_combats"}
    select_fight(session, u.unit_instance_id, "overrun")
    result = submit_move(
        session, targets=(e.unit_instance_id,), witness=paths(s, (u.unit_instance_id,), 0.25, 0.8)
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    r = pending(session)
    payload = cast(dict[str, JsonValue], melee_payload(r))
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    declarations[0]["target_allocations"] = [{"target_unit_instance_id": e.unit_instance_id}]
    result = session.submit_parameterized_payload(
        request_id=r.request_id, result_id="ordinary-native-attacks", payload=payload
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    r = finish_activation(session)
    assert r.actor_id == "opponent"
    assert r.decision_type == "select_fight_activation"
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["ordering_band"]) for o in r.options
    } == {"fights_first"}
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["unit_instance_id"]) for o in r.options
    } == {late.unit_instance_id}
    assert len(events(session, "unit_has_fought")) == 1
