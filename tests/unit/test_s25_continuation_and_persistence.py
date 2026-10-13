"""Normal generated checkpoints continue identically; malformed physical payloads fail closed."""

import json
from typing import cast

import pytest
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_gathering_helpers import native_two_bearer_inputs

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError


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
