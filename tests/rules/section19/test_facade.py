"""Native attached shooting follows one public activation and shared grants."""

import json

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section04_fixtures import (
    choose,
    pending,
    shooting_payload,
    shooting_request,
    weapon_rows,
)
from tests.support.section07_fixtures import boundary_session
from tests.support.section09_fixtures import add_unit, attach_mission
from tests.support.section19_fixtures import LORD, attached_scene, has_lethal
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("body_alive", [0, 5])
def test_native_attached_public_shooting_has_one_activation_and_physical_weapon_owners(
    section19_definitions: Section02Definitions,
    body_alive: int,
) -> None:
    d = section19_definitions
    s = attached_scene(d)
    s.set_living("bodyguard", body_alive)
    # Declared clear-board mission checkpoint; no native complete-restore claim.
    attach_mission(s.state)
    add_unit(s.state, d.unit(LORD, identity="spare"), (Pose.at(7, 30),))
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(
        s.state.battlefield_state.with_unit_placement(
            placement(s.enemy, (Pose.at(19, 10),), enemy=True)
        )
    )
    session = boundary_session(d, s.state)
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    handler = ShootingPhaseHandler(
        ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
        army_catalog=d.package.army_catalog,
    )
    handler.begin_phase(state=s.state, decisions=session.lifecycle.decision_controller)
    req = pending(session)
    if req.decision_type == "start_mission_action":
        choose(session, req, "continue_to_shooting")
        req = pending(session)
    assert req.decision_type == "select_shooting_unit"
    options = {o.option_id for o in req.options}
    assert s.view.unit_instance_id in options
    assert not options.intersection(s.view.component_unit_instance_ids)
    req = shooting_request(session, s.view.unit_instance_id)
    assert req.decision_type == "submit_shooting_declaration"
    rows = weapon_rows(req)
    living = {m.model_instance_id for m in s.view.alive_models()}
    assert rows
    available_model_ids: set[str] = set()
    for row in rows:
        model_id = row["model_instance_id"]
        assert isinstance(model_id, str)
        available_model_ids.add(model_id)
    assert available_model_ids == living
    assert all(has_lethal(s, mid) for mid in living)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=req.request_id,
        result_id="s19:malformed",
        payload={"proposal_request_id": req.request_id},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    # Select one real equipped ranged weapon per living model from public inventory.
    selected: list[dict[str, JsonValue]] = []
    seen: set[str] = set()
    for row in rows:
        model_id = row["model_instance_id"]
        assert isinstance(model_id, str)
        if model_id not in seen:
            selected.append(row)
            seen.add(model_id)
    status = session.submit_parameterized_payload(
        request_id=req.request_id,
        result_id="s19:declare",
        payload=shooting_payload(req, selected, [s.enemy.unit_instance_id] * len(selected)),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert s.state.shooting_phase_state is not None
    assert s.state.shooting_phase_state.selected_unit_ids == (s.view.unit_instance_id,)
    controller = session.lifecycle.decision_controller
    assert any(
        e.event_type == "shooting_declaration_accepted" for e in controller.event_log.records
    )
    for viewer in ("owner", "opponent"):
        view = session.view(viewer_player_id=viewer)
        delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert json.loads(json.dumps(view)) == view
        assert json.loads(json.dumps(delta)) == delta
    assert "0x" not in json.dumps(controller.to_payload())
