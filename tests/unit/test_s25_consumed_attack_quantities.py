"""Consumed physical quantities do not split later identical attack stages."""

from dataclasses import replace
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_characteristic_projection_helpers import projection_shooting_request

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("base_attacks", [2, 3])
def test_actual_consumed_counts_share_hit_stage_without_sharing_physical_authority(
    player: str, base_attacks: int
) -> None:
    session, request = projection_shooting_request(
        player=player, characteristic=Characteristic.ATTACKS, base_attacks=base_attacks
    )
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [row for row in weapons if row["weapon_profile_id"] == first["weapon_profile_id"]]
    assert len(matching) >= 2
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-consumed-quantity:declare",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert group.pool_indices == (0, 1)
    counts = [base_attacks + 1, base_attacks]
    assert [pool.attacks for pool in sequence.attack_pools] == counts
    assert [row.attacks for row in group.contributions] == counts
    assert group.total_attacks == sum(counts)
    assert len({row.weapon_instance_id for row in group.contributions}) == 2
    for index in range(group.total_attacks):
        physical = sequence.attack_pools[0 if index < counts[0] else 1]
        current = replace(sequence, attack_index=index).current_pool()
        assert current.attacker_model_instance_id == physical.attacker_model_instance_id
        assert current.weapon_instance_id == physical.weapon_instance_id
        assert current.weapon_selection_context == physical.weapon_selection_context
    cp = {owner: state.command_point_total(owner) for owner in ("player-a", "player-b")}
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError):
        session.submit_option(
            request_id=pending.request_id,
            result_id="s25-consumed-quantity:invalid",
            option_id="s25-consumed-quantity:missing-option",
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(160):
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("Consumed-quantity attack did not complete natively.")
    assert_checkpoint(session)
    completed = session.lifecycle.state
    assert completed is not None
    assert {owner: completed.command_point_total(owner) for owner in cp} == cp
    events = session.lifecycle.decision_controller.event_log.records
    indices = {
        stage: [
            index
            for index, event in enumerate(events)
            if event.event_type == "dice_rolled"
            and isinstance(event.payload, dict)
            and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
            == "attack_sequence." + stage
        ]
        for stage in ("hit", "wound")
    }
    assert len(indices["hit"]) == sum(counts)
    assert indices["wound"]
    assert max(indices["hit"]) < min(indices["wound"])
