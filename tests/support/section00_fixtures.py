"""Four retained real definitions, shared read-only; every case owns fresh state."""

import hashlib
import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from functools import cache
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import movement_mission
from tests.support.section18_fixtures import (
    INFRACTORS,
    LORD,
    WAVE,
    YRIEL,
    TransportScene,
    transport_scene,
)
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.assault_disembark import assault_disembark_permission_effect
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.lifecycle_history_origins import restore as restore_history_origins
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.shock_disembark import shock_disembark_permission_effect
from warhammer40k_core.engine.transports import DisembarkModeKind


@pytest.fixture(scope="session")
def section00_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=(INFRACTORS, LORD, WAVE, YRIEL), source_index_dir=selected_army_source_index
    )
    mission = conversion_mission()
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    mission_before = mission.to_payload()
    elapsed = perf_counter() - start
    print(f"Section00 four real definitions: {elapsed:.6f}s")
    yield Section02Definitions(package, elapsed)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )
    assert mission.to_payload() == mission_before


def grant(scene: TransportScene, mode: DisembarkModeKind, *, eligible: str | None = None) -> None:
    factory = (
        assault_disembark_permission_effect
        if mode is DisembarkModeKind.ASSAULT_DISEMBARK
        else shock_disembark_permission_effect
    )
    scene.state.record_persisting_effect(
        factory(
            effect_id=f"constructed:s00:{mode.value}",
            source_rule_id=f"constructed:s00:permission:{mode.value}",
            owner_player_id="owner",
            transport_unit_instance_id=scene.transport.unit_instance_id,
            eligible_rules_unit_instance_ids=(eligible or scene.passenger.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhase.MOVEMENT,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="owner"),
        )
    )


@cache
def conversion_mission() -> MissionSetup:
    """Explicit custom empty field; no official layout admission is implied."""
    return replace(
        movement_mission(),
        deployment_map_id="constructed:s00:deployment",
        terrain_layout_id="constructed:s00:empty-field",
        battlefield_regions=(),
    )


def conversion_scene(definitions: Section02Definitions) -> TransportScene:
    scene = transport_scene(definitions)
    scene.state.mission_setup = conversion_mission()
    scene.state.ruleset_descriptor_hash = scene.state.runtime_ruleset_descriptor().descriptor_hash
    scene.state.starting_strength_records.sort(key=lambda r: (r.player_id, r.unit_instance_id))
    return scene


def restore_kernel(session: LocalGameSession, payload: GameLifecyclePayload) -> LocalGameSession:
    """Typed Core checkpoint reconstruction, without native roster re-admission.

    The real facade kernel is deliberately not a legally mustered mixed-faction
    army. State, decisions, events, history origins and RNG are independently
    deserialized; the immutable catalog/config resource is reused. Full session
    persistence remains covered by the unchanged normal-roster smoke.
    """
    value = deepcopy(payload)
    state = GameState.from_payload(value["state"])
    config = session.lifecycle.config
    result = GameLifecycle(
        state=state,
        _config=config,
        decision_controller=DecisionController.from_payload(value["decisions"]),
        _movement_phase_handler=MovementPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        ),
        _runtime_content_audit=value.get("runtime_content_audit"),
    )
    restore_history_origins(result, value)
    assert result.to_payload() == value
    return LocalGameSession(result)
