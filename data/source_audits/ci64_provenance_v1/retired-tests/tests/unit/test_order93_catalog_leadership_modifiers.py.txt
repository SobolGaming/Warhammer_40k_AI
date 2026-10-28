from __future__ import annotations

from typing import cast

import pytest
from tests.order93_catalog_leadership_helpers import icon_leadership_session
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner


@pytest.mark.parametrize(
    ("datasheet_id", "attached_leader"),
    [("000001115", False), ("000001132", False), ("000001132", True)],
)
@pytest.mark.parametrize(
    ("ignore_set", "bearer_alive", "expected"),
    [(False, True, 7), (True, True, 8), (False, False, 8)],
)
def test_loaded_icon_leadership_source_is_selectable_for_every_model(
    datasheet_id: str, attached_leader: bool, ignore_set: bool, bearer_alive: bool, expected: int
) -> None:
    session, source_id, alive_ids = icon_leadership_session(
        datasheet_id=datasheet_id, bearer_alive=bearer_alive, attached_leader=attached_leader
    )
    initial = session.lifecycle.to_payload()
    state = session.lifecycle.state
    assert state is not None
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    group = rules_unit_view_by_id(state=state, unit_instance_id="army-a:icon-unit")
    if attached_leader:
        assert set(group.component_unit_instance_ids) == {"army-a:icon-unit", "army-a:leader"}
        leader = next(
            model
            for model in group.alive_models()
            if model.model_instance_id.startswith("army-a:leader:")
        )
        assert f"{datasheet_id}:daemonic-icon" not in leader.wargear_ids
    selected_models: set[str] = set()
    source_models: set[str] = set()
    for _ in range(40):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            assert subject["kind"] == "leadership_characteristic"
            model_id = cast(str, subject["model_instance_id"])
            assert subject["unit_instance_id"] == group.unit_instance_id
            selected_models.add(model_id)
            inventory = cast(list[dict[str, JsonValue]], payload["modifiers"])
            operations = [cast(dict[str, JsonValue], item["operation"]) for item in inventory]
            icon_operations = [
                operation for operation in operations if operation["source_id"] == source_id
            ]
            if bearer_alive:
                assert len(icon_operations) == 1
                assert icon_operations[0]["operation"] == "set"
                assert icon_operations[0]["operand"] == 6
                source_models.add(model_id)
            else:
                assert not icon_operations
            assert any(
                operation["operation"] == "add" and operation["operand"] == 1
                for operation in operations
            )
            snapshot = session.lifecycle.to_payload()
            session = LocalGameSession(GameLifecycle.from_payload(snapshot))
            assert session.lifecycle.to_payload() == snapshot
            cursor = cast(list[str], payload["decided_modifier_ids"])
            operation = operations[len(cursor)]
            ignore = ignore_set and operation["operation"] == "set"
            prefix = "ignore:" if ignore else "keep:"
            option_id = next(
                (
                    option.option_id
                    for option in request.options
                    if option.option_id.startswith(prefix)
                ),
                "ignore-remaining" if ignore else "keep-remaining",
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:icon-choice",
                option_id=option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        elif request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:decline",
                payload=stratagem_decline_payload(),
            )
        else:
            submit_fixture_request(session, request)
        resolved = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "battle_shock_test_resolved"
        ]
        if resolved:
            break
    else:
        raise AssertionError("Icon Command test did not complete.")
    assert selected_models == alive_ids
    assert source_models == (alive_ids if bearer_alive else set())
    payload = cast(dict[str, JsonValue], resolved[-1])
    result = cast(dict[str, JsonValue], payload["battle_shock_result"])
    assert result["leadership_target"] == expected
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id=f"icon:{datasheet_id}:{ignore_set}:{bearer_alive}",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
