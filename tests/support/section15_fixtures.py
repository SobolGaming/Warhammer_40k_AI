"""Stratagem-owner checkpoints: native sheets, no roster or earlier-phase claim.

Catalog resources are prepared once and hash-checked after use. Every scenario
creates new mutable units, ledgers, decisions and battlefield. Trigger payloads
are explicit constructed checkpoints unless a test exercises native discovery.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section07_fixtures import boundary_session
from tests.support.section09_fixtures import attach_mission
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems import (
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    request_stratagem_target_proposal,
    request_stratagem_use,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose

IDS = ("000004080", "000004078", "000000593", "000000968", "000000599", "000004090")


@pytest.fixture(scope="session")
def section15_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    elapsed = perf_counter() - start

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    from tests.support.section09_fixtures import movement_mission

    mission = movement_mission()
    mission_before = mission.to_payload()
    print(f"Section15 preparation: {elapsed:.6f}s; one indexed build, {len(IDS)} native sheets")
    yield Section02Definitions(package, elapsed)
    assert digest() == before
    assert mission.to_payload() == mission_before


def record(identifier: str) -> StratagemCatalogRecord:
    return next(
        r
        for r in eleventh_edition_core_stratagem_index().all_records()
        if r.definition.stratagem_id == identifier
    )


def checkpoint(
    d: Section02Definitions,
    *,
    sheet: str = "000004078",
    phase: BattlePhase = BattlePhase.FIGHT,
    active: str = "owner",
    distance: float = 8,
    cp: int = 4,
    materialize: bool = True,
) -> tuple[LocalGameSession, GameState, str, str]:
    unit = d.unit(sheet)
    enemy = d.unit("000004078", identity="target", army_id="enemy")
    state = native_state(
        d,
        unit,
        tuple(Pose.at(10, 10 + i * 1.2) for i in range(len(unit.own_models))),
        enemy=enemy,
        enemy_poses=(Pose.at(10 + distance, 10),),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.active_player_id = active
    # Facade continuation needs mission identity. This cached immutable Companion
    # checkpoint carries no scoring/admission or preceding setup claim.
    attach_mission(state)
    # Mission policy is part of the checkpoint's ruleset identity, just as it is
    # in the GameConfig built below. No phase or game setup is executed here.
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    state.starting_strength_records.sort(key=lambda row: row.unit_instance_id)
    for player in state.player_ids:
        if cp:
            state.gain_command_points(
                player_id=player,
                amount=cp,
                source_id="constructed:s15:resource-checkpoint",
                source_kind=CommandPointSourceKind.OTHER,
                cap_exempt=True,
            )
    session = boundary_session(d, state)
    # Materialize the normal content bundle before an atomicity snapshot. Lazy
    # resource preparation is not part of the submitted player's mutation.
    if materialize:
        session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return session, state, unit.unit_instance_id, enemy.unit_instance_id


def obj(value: object) -> dict[str, Any]:
    """Validate a JSON object before inspecting its schema-specific fields."""
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def context(
    state: GameState, trigger: TimingTriggerKind, payload: object = None, *, player: str = "owner"
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext.from_state(
        state=state,
        player_id=player,
        trigger_kind=trigger,
        timing_window_id="constructed:s15:window",
        trigger_payload=validate_json_value(payload),
    )


def binding(unit: str, player: str = "owner") -> StratagemTargetBinding:
    return StratagemTargetBinding(StratagemTargetKind.FRIENDLY_UNIT, player, unit)


def request(status: LifecycleStatus) -> DecisionRequest:
    assert status.decision_request is not None, status
    return status.decision_request


def offer(
    session: LocalGameSession, state: GameState, identifier: str, ctx: StratagemEligibilityContext
) -> DecisionRequest:
    rec = record(identifier)
    decisions = session.lifecycle.decision_controller
    if rec.definition.target_spec.enumerable:
        return request(
            request_stratagem_use(
                state=state,
                decisions=decisions,
                catalog_records=(rec,),
                context=ctx,
            )
        )
    return request(
        request_stratagem_target_proposal(
            state=state,
            decisions=decisions,
            proposal_request=StratagemTargetProposal.for_request(context=ctx, catalog_record=rec),
        )
    )


def submit(
    session: LocalGameSession,
    req: DecisionRequest,
    unit: str,
    *,
    effect: JsonValue = None,
    player: str = "owner",
    result: str = "s15:use",
) -> LifecycleStatus:
    assert isinstance(req.payload, dict)
    proposal = StratagemTargetProposal.from_payload(obj(req.payload)["proposal_request"])
    bound = proposal.with_binding(binding(unit, player), effect_selection=effect)
    return session.submit_parameterized_payload(
        request_id=req.request_id,
        result_id=result,
        payload=validate_json_value({"proposal": bound.to_payload()}),
    )


def events(session: LocalGameSession, kind: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for event in session.lifecycle.decision_controller.event_log.records:
        if event.event_type == kind:
            assert isinstance(event.payload, dict)
            found.append(obj(event.payload))
    return found
