"""Section10 kernels: immutable indexed native definitions, fresh case graphs.

Mission identity is required by the public shooting proposal context. No setup,
mustering, prior phase traversal, replay or faction admission is exercised.
"""

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import replace
from functools import cache
from pathlib import Path
from time import perf_counter
from typing import cast

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import (
    choose,
    combat_session,
    combat_state,
    pending,
    shooting_payload,
)
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.advance_roll import AdvanceRollRequest, AdvanceRollResult
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

LORD = "000004078"
SPAWN = "000004090"
AVENGERS = "000000593"
SPINNER = "000000611"
DEFILER = "000000969"
INFRACTORS = "000004080"
WRAITHLORD = "000000613"
IDS = (LORD, SPAWN, AVENGERS, SPINNER, DEFILER, INFRACTORS, WRAITHLORD)


@cache
def shooting_mission() -> MissionSetup:
    from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

    return replace(
        MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="owner",
            defender_player_id="opponent",
            attacker_force_disposition_id="take-and-hold",
            defender_force_disposition_id="purge-the-foe",
        ),
        battlefield_layout_id=None,
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
    )


@pytest.fixture(scope="session")
def section10_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    mission = shooting_mission()
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    mission_before = mission.to_payload()
    seconds = perf_counter() - start
    print(
        f"Section10 preparation: {seconds:.6f}s; "
        f"{len(IDS)} native definitions, one mission identity"
    )
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )
    assert mission.to_payload() == mission_before


def advanced(state: GameState, unit: UnitInstance) -> None:
    """Constructed valid prior Advance receipt; shooting admission is under test."""
    request = AdvanceRollRequest.for_unit(
        request_id="constructed:advance",
        game_id=state.game_id,
        battle_round=1,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
    )
    roll = AdvanceRollResult.from_roll_state(
        request=request, roll_state=DiceRollManager("section10").roll_fixed(request.spec, (3,))
    )
    state.record_advanced_unit_state(
        AdvancedUnitState(
            "owner",
            1,
            unit.unit_instance_id,
            MovementDiceRecord(
                "owner", 1, unit.unit_instance_id, MovementPhaseActionKind.ADVANCE, roll
            ),
        )
    )


def case(
    definitions: Section02Definitions,
    datasheet: str = LORD,
    *,
    engaged: bool = False,
    advance: bool = False,
    distance: float | None = None,
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    unit = definitions.unit(datasheet)
    state = combat_state(
        definitions,
        unit,
        distance=distance
        if distance is not None
        else (
            (5 if datasheet == DEFILER else 3.5 if datasheet == SPINNER else 2.5) if engaged else 12
        ),
    )
    if advance:
        advanced(state, unit)
    session = shooting_session(definitions, state, shooting_mission())
    return session, state, unit


def shooting_session(
    definitions: Section02Definitions, state: GameState, mission: MissionSetup
) -> LocalGameSession:
    session = combat_session(definitions, state, mission)
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    # The public attack continuation tracks destroyed units against a turn-start
    # membership snapshot. Record this minimal identity boundary, without playing
    # setup, mustering or Command. It grants no rule or altered health.
    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    return session


def declaration_request(
    session: LocalGameSession, unit: UnitInstance, shooting_type: str
) -> DecisionRequest:
    choose(session, pending(session), unit.unit_instance_id)
    request = pending(session)
    assert request.decision_type == "select_shooting_type"
    choose(session, request, shooting_type)
    return pending(session)


def payload(
    request: DecisionRequest,
    rows: list[dict[str, JsonValue]],
    targets: Sequence[str | None],
    kind: str,
) -> JsonValue:
    result = shooting_payload(request, rows, targets)
    assert isinstance(result, dict)
    declarations = cast(list[dict[str, JsonValue]], result["declarations"])
    for declaration in declarations:
        declaration["shooting_type"] = kind
    return validate_json_value(result)


def submit(
    session: LocalGameSession,
    rows: list[dict[str, JsonValue]],
    targets: Sequence[str | None],
    kind: str,
    *,
    result_id: str = "section10:declare",
) -> LifecycleStatus:
    request = pending(session)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=payload(request, rows, targets, kind),
    )


def accepted_pools(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    records = session.lifecycle.decision_controller.event_log.records
    accepted = next(e for e in reversed(records) if e.event_type == "shooting_declaration_accepted")
    assert isinstance(accepted.payload, dict)
    return cast(list[dict[str, JsonValue]], accepted.payload["attack_pools"])


def assert_valid(result: LifecycleStatus) -> None:
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
