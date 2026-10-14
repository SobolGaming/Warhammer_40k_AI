"""Normal generated checkpoints continue identically; malformed physical payloads fail closed."""

import json
from typing import cast

import pytest
from tests.d02_save_step_helpers import native_save_step_shooting_request
from tests.lethal_hits_helpers import attack_completed, complete_attack
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_gathering_helpers import native_two_bearer_inputs

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import DECLINE_STRATAGEM_WINDOW_OPTION_ID


@pytest.fixture(scope="module")
def generated_session() -> LocalGameSession:
    session, _, _ = native_two_bearer_inputs()
    return session


def test_restored_and_forked_native_pool_continue_with_exact_physical_dice_and_events(
    generated_session: LocalGameSession,
) -> None:
    before = generated_session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(before)))
    fork = generated_session.fork()
    assert restored.lifecycle is not fork.lifecycle
    assert restored.lifecycle.state is not fork.lifecycle.state
    for _ in range(100):
        requests = tuple(
            session.advance_until_decision_or_terminal().decision_request
            for session in (restored, fork)
        )
        assert requests[0] is not None
        assert requests[1] is not None
        assert requests[0].to_payload() == requests[1].to_payload()
        for session, request in zip((restored, fork), requests, strict=True):
            assert request is not None
            submit_fixture_request(session, request)
        assert restored.to_persistence_payload() == fork.to_persistence_payload()
        assert generated_session.to_persistence_payload() == before
        if any(
            event.event_type == "attack_sequence_completed"
            for event in restored.lifecycle.decision_controller.event_log.records
        ):
            break
    else:
        raise AssertionError("Recovered S25 physical pool did not complete.")
    # Continue beyond completion through the next native request on both copies.
    for session in (restored, fork):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        submit_fixture_request(session, request)
    assert restored.to_persistence_payload() == fork.to_persistence_payload()


@pytest.mark.parametrize("drift", ["bearer", "pool-index", "snapshot-field", "physical-weapon"])
def test_malformed_native_group_payload_rejects_without_changing_generated_state(
    generated_session: LocalGameSession,
    drift: str,
) -> None:
    state = generated_session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    before = generated_session.to_persistence_payload()
    payload = json.loads(json.dumps(sequence.to_payload()))
    group = cast(dict[str, JsonValue], payload["current_gathered_group"])
    snapshots = cast(list[dict[str, JsonValue]], group["native_snapshots"])
    if drift == "bearer":
        snapshots[1]["attacker_model_instance_id"] = "s25:foreign-physical-bearer"
    elif drift == "pool-index":
        snapshots[1]["pool_index"] = True
    elif drift == "snapshot-field":
        snapshots[1]["unrecognized_authority"] = "s25:unissued"
    else:
        payload["attack_pools"][1]["weapon_instance_id"] = "s25:foreign-physical-weapon"
    with pytest.raises(GameLifecycleError):
        AttackSequence.from_payload(payload)
    assert generated_session.to_persistence_payload() == before
    assert AttackSequence.from_payload(sequence.to_payload()) == sequence


@pytest.mark.parametrize("attacking_player", ["player-a", "player-b"])
@pytest.mark.parametrize("use_reroll", [True, False])
def test_native_save_step_precedes_command_reroll_and_survives_continuation(
    attacking_player: str, use_reroll: bool
) -> None:
    """05.00: all original saves in one physical pool precede any reroll choice."""
    session, request = native_save_step_shooting_request(
        attacks=12, attacking_player=attacking_player
    )
    defender = "player-b" if attacking_player == "player-a" else "player-a"
    target = "army-beta:scalar" if attacking_player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    proposal["declarations"] = proposal["declarations"][:1]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="independent-multiattack-declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    for _ in range(80):
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        request = pending
        if request.decision_type == "use_stratagem" and _original_save_indices(session):
            break
        submit_fixture_request(session, request)
        assert not attack_completed(session), "Native actual dice did not reach a save choice."
    else:
        raise AssertionError("Native save choice was not reached within the decision bound.")
    assert request.actor_id == defender
    successful_wounds = sum(
        event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload["step"] == "wound"
        and cast(dict[str, JsonValue], event.payload["payload"])["successful"] is True
        for event in session.lifecycle.decision_controller.event_log.records
    )
    assert successful_wounds >= 2, "The actual-dice scene must exercise multiple saves."
    assert len(_original_save_indices(session)) == successful_wounds
    assert_checkpoint(session)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    forked = session.fork()
    for branch in (session, restored, forked):
        pending = branch.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        assert pending.to_payload() == request.to_payload()
        state = branch.lifecycle.state
        assert state is not None
        before = state.command_point_total(defender)
        option = next(
            option.option_id
            for option in pending.options
            if (option.option_id != DECLINE_STRATAGEM_WINDOW_OPTION_ID) == use_reroll
        )
        status = branch.submit_option(
            request_id=pending.request_id,
            option_id=option,
            result_id="d02-save-reroll-choice",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        assert state.command_point_total(defender) == before - int(use_reroll)
        complete_attack(branch)
        events = branch.lifecycle.decision_controller.event_log.records
        saves = _original_save_indices(branch)
        assert len(saves) == successful_wounds, "Resume must not duplicate original dice."
        rerolls = [
            index
            for index, event in enumerate(events)
            if event.event_type == "dice_reroll_resolved"
        ]
        assert len(rerolls) == int(use_reroll)
        if use_reroll:
            assert max(saves) < min(rerolls)
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    assert session.lifecycle.to_payload() == forked.lifecycle.to_payload()
    assert_checkpoint(session)


def _original_save_indices(session: LocalGameSession) -> list[int]:
    return [
        index
        for index, event in enumerate(session.lifecycle.decision_controller.event_log.records)
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"])["roll_type"]
        in {"attack_sequence.save.armour", "attack_sequence.save.invulnerable"}
    ]
