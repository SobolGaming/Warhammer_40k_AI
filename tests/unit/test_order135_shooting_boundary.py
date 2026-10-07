"""Native last-shooter declarations retain actual-shot boundary authority."""

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session
from tests.order128_helpers import assert_checkpoint
from tests.order135_rng_helpers import native_scalar_shooting_request
from tests.order135_visibility_helpers import edge_shooting_boundary
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    capture_primary_mission_boundary_checkpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_unit_history_authority import (
    validate_primary_mission_boundary_unit_history_authority,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def _shooting_boundaries(
    session: LocalGameSession, start: int
) -> tuple[PrimaryMissionBoundaryCheckpoint, ...]:
    state = session.lifecycle.state
    assert state is not None
    return tuple(
        authority.boundary_checkpoint
        for authority in state.objective_control_record_authorities[start:]
        if authority.boundary_checkpoint.phase == BattlePhase.SHOOTING.value
    )


@pytest.mark.parametrize("physical", [False, True])
@pytest.mark.parametrize("selected_targetless", [False, True])
def test_last_shooter_without_attacks_preserves_boundary_save_fork_views_and_replay(
    physical: bool, selected_targetless: bool
) -> None:
    if physical:
        session, request = edge_shooting_boundary()
        status = session.submit_option(
            request_id=request.request_id, option_id="normal", result_id="order135-b01:normal"
        )
        assert status.decision_request is not None
        request = status.decision_request
        target = "army-alpha:large"
    else:
        session, request = native_scalar_shooting_request()
        target = "army-beta:scalar"
    assert request.decision_type == "submit_shooting_declaration"
    assert_checkpoint(session)

    payload = json.loads(
        json.dumps(proposal_from_request(request=request, target_unit_id=target).to_payload())
    )
    if selected_targetless:
        assert payload["declarations"]
        for declaration in payload["declarations"]:
            declaration["target_unit_instance_id"] = None
    else:
        payload["declarations"] = []
    unit_id = payload["unit_instance_id"]
    start = len(session.lifecycle.decision_controller.event_log.records)
    assert session.lifecycle.state is not None
    boundary_start = len(session.lifecycle.state.objective_control_record_authorities)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-b01:decline-all-targets",
        payload=validate_json_value(payload),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    session.advance_until_decision_or_terminal()
    assert _shooting_boundaries(session, boundary_start)
    declarations = tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records[start:]
        if event.event_type == "shooting_declaration_accepted"
    )
    assert len(declarations) == 1
    declaration = cast(dict[str, object], declarations[0].payload)
    assert declaration["attack_pools"] == []
    assert declaration["ranged_attack_history_record"] is None
    assert bool(declaration["weapons_without_attacks"]) is selected_targetless
    for checkpoint in _shooting_boundaries(session, boundary_start):
        assert unit_id not in checkpoint.shot_unit_instance_ids
    assert_checkpoint(session)


@pytest.mark.parametrize(("weapon_index", "no_damage"), [(0, False), (1, True)])
def test_nonempty_native_attack_remains_shot_at_boundary(
    weapon_index: int, no_damage: bool
) -> None:
    session, request = native_scalar_shooting_request()
    payload = json.loads(
        json.dumps(
            proposal_from_request(request=request, target_unit_id="army-beta:scalar").to_payload()
        )
    )
    # A player may choose one offered weapon. No dice or runtime state is edited.
    declaration = payload["declarations"][0]
    offered = cast(dict[str, object], cast(dict[str, object], request.payload)["proposal_request"])
    weapons = [
        row
        for row in cast(list[dict[str, object]], offered["available_weapons"])
        if row["wargear_id"] == declaration["wargear_id"]
        and row["weapon_profile_id"] == declaration["weapon_profile_id"]
    ]
    selected = weapons[weapon_index]
    declaration["attacker_model_instance_id"] = selected["model_instance_id"]
    declaration["weapon_instance_id"] = selected["weapon_instance_id"]
    payload["declarations"] = [declaration]
    assert payload["declarations"]
    unit_id = payload["unit_instance_id"]
    assert session.lifecycle.state is not None
    boundary_start = len(session.lifecycle.state.objective_control_record_authorities)
    event_start = len(session.lifecycle.decision_controller.event_log.records)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-b01:actual-one-attack",
        payload=validate_json_value(payload),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    for _ in range(40):
        session.advance_until_decision_or_terminal()
        if _shooting_boundaries(session, boundary_start):
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("Actual native attack did not reach its Shooting boundary.")
    events = session.lifecycle.decision_controller.event_log.records[event_start:]
    declarations = tuple(
        event for event in events if event.event_type == "shooting_declaration_accepted"
    )
    assert len(declarations) == 1
    declaration = cast(dict[str, object], declarations[0].payload)
    assert declaration["attack_pools"]
    assert declaration["ranged_attack_history_record"] is not None
    assert any(event.event_type == "attack_sequence_completed" for event in events)
    assert any(event.event_type == "dice_rolled" for event in events)
    wounds_lost = 0
    for event in events:
        if (
            event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "damage"
        ):
            damage = cast(dict[str, object], event.payload["payload"])["damage_application"]
            if damage is not None:
                wounds_lost += cast(int, cast(dict[str, object], damage)["wounds_lost"])
    assert (wounds_lost == 0) is no_damage
    for checkpoint in _shooting_boundaries(session, boundary_start):
        assert unit_id in checkpoint.shot_unit_instance_ids
    assert_checkpoint(session)


@pytest.mark.parametrize("change", ["missing", "none", "object", "item", "zero_attacks"])
def test_boundary_shot_projection_requires_explicit_valid_attack_pools(change: str) -> None:
    session = empty_shooting_session(reachable=True, spare=True)
    request = pending_request(session)
    status = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="order135-pool:unit"
    )
    assert status.decision_request is not None
    request = status.decision_request
    status = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order135-pool:type"
    )
    assert status.decision_request is not None
    request = status.decision_request
    proposal = proposal_from_request(request=request, target_unit_id="army-beta:enemy")
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-pool:declaration",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="objective_control",
        player_id="player-a",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    decisions = session.lifecycle.decision_controller
    unit_id = SHOOTER
    events = decisions.event_log.records
    validate_primary_mission_boundary_unit_history_authority(
        state=state,
        event_records=events,
        decision_records=tuple(decisions.records),
        checkpoint_index=len(events),
        checkpoint=checkpoint,
    )
    assert unit_id in checkpoint.shot_unit_instance_ids
    declaration_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "shooting_declaration_accepted"
    )
    event = events[declaration_index]
    payload = json.loads(json.dumps(event.payload))
    if change == "missing":
        del payload["attack_pools"]
    elif change == "none":
        payload["attack_pools"] = None
    elif change == "object":
        payload["attack_pools"] = {}
    elif change == "item":
        payload["attack_pools"] = [None]
    else:
        assert payload["attack_pools"]
        payload["attack_pools"][0]["attacks"] = 0
    changed = (
        *events[:declaration_index],
        replace(event, payload=validate_json_value(payload)),
        *events[declaration_index + 1 :],
    )
    with pytest.raises(GameLifecycleError, match=r"attack.pool|greater than zero"):
        validate_primary_mission_boundary_unit_history_authority(
            state=state,
            event_records=changed,
            decision_records=tuple(decisions.records),
            checkpoint_index=len(changed),
            checkpoint=checkpoint,
        )
    assert state.shooting_phase_state is not None
    assert unit_id in state.shooting_phase_state.shot_unit_ids
