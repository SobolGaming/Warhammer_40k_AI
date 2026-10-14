"""Per-weapon random A, Hazardous and One Shot survive native cross-bearer grouping."""

from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_native_profile_helpers import native_profile_request

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("mode", ["random-attacks", "physical-completion"])
def test_native_physical_weapons_keep_random_counts_and_completion_authority(
    player: str, mode: str
) -> None:
    session, request = native_profile_request(player=player, mode=mode)
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [w for w in weapons if w["weapon_profile_id"] == first["weapon_profile_id"]]
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, w["model_instance_id"]),
            "weapon_instance_id": cast(str, w["weapon_instance_id"]),
        }
        for w in matching[:2]
    ]
    physical_ids = {row["weapon_instance_id"] for row in proposal["declarations"]}
    assert len(physical_ids) == 2
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-physical:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    shooting = state.shooting_phase_state
    assert shooting is not None
    sequence = shooting.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert group.pool_indices == (0, 1)
    assert group.total_attacks == sum(pool.attacks for pool in sequence.attack_pools)
    assert_checkpoint(session)
    for _ in range(100):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "attack_sequence_completed" for event in events):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("S25 physical weapon native continuation did not complete.")
    assert_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    hits = [
        event
        for event in events
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == "attack_sequence.hit"
    ]
    assert len(hits) == group.total_attacks
    if mode == "random-attacks":
        rows = [
            event.payload
            for event in events
            if event.event_type == "random_characteristic_rolled"
            and isinstance(event.payload, dict)
            and event.payload.get("characteristic") == "attacks"
        ]
        assert len(rows) == 2
    else:
        uses = state.one_shot_weapon_use_records
        assert {record.weapon_instance_id for record in uses} == physical_ids
        hazards = [
            event.payload
            for event in events
            if event.event_type == "hazardous_test_resolved" and isinstance(event.payload, dict)
        ]
        assert len(hazards) == 1
        assert set(cast(list[str], hazards[0]["hazardous_weapon_instance_ids"])) == physical_ids
