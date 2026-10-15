from __future__ import annotations

from copy import deepcopy as deepcopy
from dataclasses import replace as replace
from typing import cast as cast

import pytest as pytest

from tests.phase17n_primary_mission_helpers import (
    phase17n_action_opportunity_fixture as phase17n_action_opportunity_fixture,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_consecrate_pending_fixture as phase17n_consecrate_pending_fixture,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_direct_action_pending_fixture as phase17n_direct_action_pending_fixture,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_locate_pending_fixture as phase17n_locate_pending_fixture,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_punishment_pending_fixture as phase17n_punishment_pending_fixture,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_sensor_pending_fixture as phase17n_sensor_pending_fixture,
)
from warhammer40k_core.engine.decision_controller import DecisionController as DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord as DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest as DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult as DecisionResult
from warhammer40k_core.engine.event_log import JsonValue as JsonValue
from warhammer40k_core.engine.event_log import validate_json_value as validate_json_value
from warhammer40k_core.engine.game_state import GameState as GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle as GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError as GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT as PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    PrimaryMissionChoiceData as PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_pending_request_integrity import (
    validate_primary_mission_pending_request_integrity,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry as RuntimeModifierRegistry,
)

type PendingFixture = tuple[GameState, DecisionController, DecisionRequest]


@pytest.fixture(scope="module")
def action_opportunity() -> PendingFixture:
    return phase17n_action_opportunity_fixture()


@pytest.fixture(scope="module")
def direct_action() -> PendingFixture:
    return phase17n_direct_action_pending_fixture()


@pytest.fixture(scope="module")
def locate_choice() -> PendingFixture:
    return phase17n_locate_pending_fixture()


@pytest.fixture(scope="module")
def punishment_choice() -> PendingFixture:
    return phase17n_punishment_pending_fixture()


@pytest.fixture(scope="module")
def consecrate_choice() -> PendingFixture:
    return phase17n_consecrate_pending_fixture()


@pytest.fixture(scope="module")
def sensor_choice() -> PendingFixture:
    return phase17n_sensor_pending_fixture()


def _validate(*, state: GameState, decisions: DecisionController) -> None:
    validate_primary_mission_pending_request_integrity(
        state=state,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )


def _controller_with_pending_request(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
    synchronize_requested_event: bool,
) -> DecisionController:
    payload = deepcopy(decisions.to_payload())
    payload["queue"]["pending_requests"] = [request.to_payload()]
    if synchronize_requested_event:
        original_request_id = decisions.queue.pending_requests[0].request_id
        for event in payload["event_log"]:
            if event["event_type"] != "decision_requested":
                continue
            event_payload = event["payload"]
            if not isinstance(event_payload, dict):
                continue
            if event_payload.get("request_id") == original_request_id:
                event["payload"] = cast(JsonValue, request.to_payload())
    return DecisionController.from_payload(payload)


__all__: list[str] = [
    "PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT",
    "DecisionController",
    "DecisionRecord",
    "DecisionRequest",
    "DecisionResult",
    "GameLifecycle",
    "GameLifecycleError",
    "GameState",
    "JsonValue",
    "PendingFixture",
    "PrimaryMissionChoiceData",
    "RuntimeModifierRegistry",
    "_controller_with_pending_request",
    "_validate",
    "action_opportunity",
    "cast",
    "consecrate_choice",
    "deepcopy",
    "direct_action",
    "locate_choice",
    "phase17n_action_opportunity_fixture",
    "phase17n_consecrate_pending_fixture",
    "phase17n_direct_action_pending_fixture",
    "phase17n_locate_pending_fixture",
    "phase17n_punishment_pending_fixture",
    "phase17n_sensor_pending_fixture",
    "punishment_choice",
    "pytest",
    "replace",
    "sensor_choice",
    "validate_json_value",
    "validate_primary_mission_pending_request_integrity",
]
