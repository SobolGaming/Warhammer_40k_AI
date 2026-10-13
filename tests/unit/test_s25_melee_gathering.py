"""S25 shared Fight authority from admitted preconfigured analytical Core roots.

Equipment/Twin-linked are declared before muster by the existing D12 fixture.
Subsequent choices, dice, allocations and history use LocalGameSession.
"""

from typing import cast

import pytest
from tests.epic_challenge_helpers import epic_checkpoint, epic_scene, submit_all_melee
from tests.fight_completion_helpers import submit_completion_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind


@pytest.mark.parametrize("player", ["player-a", "player-b"])
def test_melee_cross_bearer_pool_preserves_rerolls_allocation_and_native_continuation(
    player: str,
) -> None:
    session = epic_scene(player=player, noncharacter=True, armed_bodyguard=True, pause_attacks=True)
    for _ in range(80):
        request = pending_request(session)
        if request.decision_type == "submit_melee_declaration" and request.actor_id == player:
            payload = cast(dict[str, JsonValue], request.payload)
            proposal = cast(dict[str, JsonValue], payload["proposal_request"])
            if str(proposal["unit_instance_id"]).endswith(":bodyguard"):
                break
        submit_completion_request(session)
    else:
        raise AssertionError("S25 Core bodyguard did not reach native melee declaration.")
    unit_id = cast(str, proposal["unit_instance_id"])
    state = session.lifecycle.state
    assert state is not None
    cp_before = state.command_point_total(player)
    submit_all_melee(session, request)
    group_records = [
        record
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_attack_weapon_group"
    ]
    assert group_records
    groups = [
        cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], record.result.payload)["gathered_group"],
        )
        for record in group_records
    ]
    contributions = cast(list[dict[str, JsonValue]], groups[0]["contributions"])
    assert len({cast(str, row["attacker_model_instance_id"]) for row in contributions}) > 1
    assert groups[0]["total_attacks"] == sum(cast(int, row["attacks"]) for row in contributions)
    epic_checkpoint(session)
    for _ in range(160):
        events = session.lifecycle.decision_controller.event_log.records
        if any(
            event.event_type == "fight_activation_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("unit_instance_id") == unit_id
            for event in events
        ):
            break
        request = pending_request(session)
        if "reroll" in request.decision_type:
            option = next(
                (option for option in request.options if option.option_id.startswith("reroll:")),
                request.options[0],
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=request.request_id + ":s25-reroll",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "submit_stratagem_target_proposal":
            submit_completion_request(session)
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("S25 native melee activation did not complete.")
    epic_checkpoint(session)
    assert state.command_point_total(player) <= cp_before
    events = session.lifecycle.decision_controller.event_log.records
    assert any(event.event_type == "dice_reroll_resolved" for event in events)
    assert any(event.event_type == "attack_sequence_completed" for event in events)
    sequence_ids = {
        cast(str, cast(dict[str, JsonValue], record.request.payload)["sequence_id"])
        for record in group_records
    }
    wounds = [
        event.payload
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") in sequence_ids
        and event.payload.get("step") == "wound"
    ]
    assert wounds
