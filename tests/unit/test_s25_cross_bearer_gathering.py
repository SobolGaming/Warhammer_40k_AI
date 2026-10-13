"""S25: identical physical bearers share stages without sharing ownership."""

from dataclasses import replace
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_gathered_step_helpers import native_gathered_shooting_request
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_sequence_model import GatheredAttackGroupPayload
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


def _declare_two_bearers() -> LocalGameSession:
    session, request = native_gathered_shooting_request()
    proposal = proposal_from_request(
        request=request, target_unit_id="army-beta:scalar"
    ).to_payload()
    payload = cast(dict[str, JsonValue], request.payload)
    offered = cast(dict[str, JsonValue], payload["proposal_request"])
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    first = proposal["declarations"][0]
    matching = [
        weapon
        for weapon in weapons
        if weapon["weapon_profile_id"] == first["weapon_profile_id"]
        and weapon["wargear_id"] == first["wargear_id"]
    ]
    proposal["declarations"] = [
        {
            **first,
            "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
            "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
        }
        for weapon in matching[:2]
    ]
    assert len({row["attacker_model_instance_id"] for row in proposal["declarations"]}) == 2
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-two-bearers",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    return session


def test_native_equal_bearers_keep_each_physical_attack_in_one_gathered_pool() -> None:
    session = _declare_two_bearers()
    selections = [
        record
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_attack_weapon_group"
    ]
    assert len(selections) == 1
    selected = cast(dict[str, JsonValue], selections[0].result.payload)
    group = cast(GatheredAttackGroupPayload, selected["gathered_group"])
    assert group["pool_indices"] == [0, 1]
    assert group["total_attacks"] == 6
    assert [row["attacks"] for row in group["contributions"]] == [3, 3]
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert sequence.current_gathered_group is not None
    for index in range(6):
        physical = sequence.attack_pools[0 if index < 3 else 1]
        current = replace(sequence, attack_index=index).current_pool()
        assert current.attacker_model_instance_id == physical.attacker_model_instance_id
        assert current.weapon_instance_id == physical.weapon_instance_id
        assert current.weapon_profile_id == physical.weapon_profile_id
        assert current.weapon_selection_context == physical.weapon_selection_context
        assert current.selected_weapon_ability_ids == physical.selected_weapon_ability_ids
    assert_checkpoint(session)


def test_native_gathered_hit_wound_save_boundaries_survive_retry_restore_and_completion() -> None:
    session = _declare_two_bearers()
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id, option_id="s25-unknown-option", result_id="s25-invalid"
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(100):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "attack_sequence_completed" for event in events):
            break
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Native S25 gathered attacks did not complete.")
    assert_checkpoint(session)
    events = session.lifecycle.decision_controller.event_log.records
    indices: dict[str, list[int]] = {"hit": [], "wound": [], "save": []}
    for index, event in enumerate(events):
        if event.event_type != "dice_rolled" or not isinstance(event.payload, dict):
            continue
        spec = cast(dict[str, JsonValue], event.payload["spec"])
        roll_type = cast(str, spec["roll_type"])
        if roll_type in {"attack_sequence.hit", "attack_sequence.wound"}:
            indices[roll_type.removeprefix("attack_sequence.")].append(index)
        elif roll_type.startswith("attack_sequence.save."):
            indices["save"].append(index)
    assert len(indices["hit"]) == 6
    assert indices["wound"]
    assert indices["save"]
    assert max(indices["hit"]) < min(indices["wound"])
    assert max(indices["wound"]) < min(indices["save"])
