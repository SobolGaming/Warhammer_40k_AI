"""R87-001: legal gathered defensive-profile occurrences must survive persistence."""

import json

import pytest
from tests.order87_gathered_profile_helpers import gathered_profile_session
from tests.psychic_modifier_helpers import submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_profile_attack_groups import validate_profile_attack_group


def test_gathered_random_toughness_round_trip_and_continuation() -> None:
    session = gathered_profile_session()
    events = session.lifecycle.decision_controller.event_log.records
    groups = [
        record.result.payload
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_attack_weapon_group"
    ]
    assert len(groups) == 1
    group_payload = groups[0]
    assert isinstance(group_payload, dict)
    group = group_payload["gathered_group"]
    assert isinstance(group, dict)
    assert group["pool_indices"] == [0, 1]
    assert group["total_attacks"] == 4
    contributions = group["contributions"]
    assert isinstance(contributions, list)
    assert len(contributions) == 2
    scopes = [
        event.payload["scope_id"]
        for event in events
        if event.event_type == "random_profile_values_evaluated" and isinstance(event.payload, dict)
    ]
    assert any(str(scope).endswith("pool-001:attack-003") for scope in scopes)
    assert any(str(scope).endswith("pool-001:attack-004") for scope in scopes)
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    initial_rolls = [e for e in events if e.event_type == "random_characteristic_rolled"]
    assert len(initial_rolls) == 8
    for current in (session, restored):
        for _ in range(20):
            if any(
                e.event_type == "attack_sequence_completed"
                for e in current.lifecycle.decision_controller.event_log.records
            ):
                break
            request = current.advance_until_decision_or_terminal().decision_request
            assert request is not None
            submit_fixture_request(current, request)
        else:
            raise AssertionError("Gathered attack did not complete through the session facade.")
        assert [
            e
            for e in current.lifecycle.decision_controller.event_log.records
            if e.event_type == "random_characteristic_rolled"
        ] == initial_rolls
    assert restored.to_persistence_payload() == session.to_persistence_payload()


@pytest.mark.parametrize("characteristic", [Characteristic.SAVE, Characteristic.TOUGHNESS])
def test_defensive_profiles_bind_to_selected_group_not_all_declared_attacks(
    characteristic: Characteristic,
) -> None:
    session = gathered_profile_session(characteristic, extra_group=True)
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    records = session.lifecycle.decision_controller.records
    events = session.lifecycle.decision_controller.event_log.records
    evaluation = next(e for e in events if e.event_type == "random_profile_values_evaluated")
    before = events[: events.index(evaluation)]
    assert isinstance(evaluation.payload, dict)
    target = evaluation.payload["unit_instance_id"]
    assert isinstance(target, str)
    sequence_id = "attack-sequence:declare-gathered-shots"
    validate_profile_attack_group(
        sequence_id=sequence_id,
        pool_index=0,
        attack_index=3,
        target_unit_instance_id=target,
        events=before,
        decisions=records,
    )
    # A third, incompatible pool targets the same unit, but its two attacks are
    # not part of the selected four-attack group. Its option is offered, not selected.
    selection = next(r for r in records if r.request.decision_type == "select_attack_weapon_group")
    assert len(selection.request.options) == 2
    for pool_index, attack_index, target_id in (
        (0, 4, target),
        (1, 0, target),
        (2, 0, target),
        (0, 0, "army-alpha:shooter"),
    ):
        with pytest.raises(GameLifecycleError, match="selected gathered attack"):
            validate_profile_attack_group(
                sequence_id=sequence_id,
                pool_index=pool_index,
                attack_index=attack_index,
                target_unit_instance_id=target_id,
                events=before,
                decisions=records,
            )
    without_selection = tuple(
        e
        for e in before
        if not (
            e.event_type == "decision_recorded"
            and isinstance(e.payload, dict)
            and e.payload.get("record_id") == selection.record_id
        )
    )
    with pytest.raises(GameLifecycleError, match="selected gathered attack"):
        validate_profile_attack_group(
            sequence_id=sequence_id,
            pool_index=0,
            attack_index=0,
            target_unit_instance_id=target,
            events=without_selection,
            decisions=records,
        )
    with pytest.raises(GameLifecycleError, match="recorded decision"):
        validate_profile_attack_group(
            sequence_id=sequence_id,
            pool_index=0,
            attack_index=0,
            target_unit_instance_id=target,
            events=before,
            decisions=tuple(r for r in records if r != selection),
        )


@pytest.mark.parametrize("replacement", ["pool-001:attack-005", "pool-002:attack-004"])
def test_persistence_rejects_substituted_gathered_attack_identity(replacement: str) -> None:
    session = gathered_profile_session()
    payload = json.loads(
        json.dumps(session.lifecycle.to_payload()).replace("pool-001:attack-004", replacement)
    )
    with pytest.raises(GameLifecycleError, match="selected gathered attack"):
        GameLifecycle.from_payload(payload)
