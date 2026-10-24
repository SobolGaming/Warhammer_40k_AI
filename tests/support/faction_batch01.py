"""Bounded source-backed faction consumers, with fresh mutable case graphs.

The catalog keeps selected real datasheets unchanged. Source faction/detachment
identities let the normal loader admit providers; the small component requests
are deliberately non-strict rosters. Battle checkpoints skip previous phases and
do not certify a legal full army, native setup traversal, or complete factions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.triggered_movement import TriggeredMovementHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

CRUSHERS = "000001115"
RANGERS = "000000592"
ELDRAD = "000000568"
INFRACTORS = "000004080"
TORMENTORS = "000004079"
LORD = "000004078"
AVENGERS = "000000593"
IDS = (CRUSHERS, RANGERS, ELDRAD, INFRACTORS, LORD, AVENGERS, TORMENTORS)
# Scope is selected component admission, not a complete detachment catalog.
FACTIONS = {
    "CD": ("chaos-daemons", "cavalcade-of-chaos"),
    "AE": ("aeldari", "path-of-the-outcast"),
    "EC": ("emperors-children", "court-of-the-phoenician"),
}


@pytest.fixture(scope="session")
def faction_definitions(selected_army_source_index: Path | None) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    catalog = package.army_catalog
    factions: list[FactionDefinition] = []
    detachments: list[DetachmentDefinition] = []
    for source_faction in catalog.factions:
        faction_id, detachment_id = FACTIONS[source_faction.faction_id]
        row = next(r for r in identities.faction_rows() if r.faction_id == faction_id)
        factions.append(
            FactionDefinition(
                faction_id=row.faction_id,
                name=row.name,
                faction_keywords=source_faction.faction_keywords,
                source_ids=(*row.source_ids, *source_faction.source_ids),
            )
        )
        detachment = next(
            r for r in identities.detachment_rows() if r.detachment_id == detachment_id
        )
        detachments.append(
            DetachmentDefinition(
                canonical_detachment_id=detachment.detachment_id,
                detachment_id=detachment.detachment_id,
                name=detachment.name,
                faction_id=faction_id,
                detachment_point_cost=detachment.detachment_point_cost,
                unit_datasheet_ids=tuple(
                    s.datasheet_id
                    for s in catalog.datasheets
                    if set(s.keywords.faction_keywords) & set(source_faction.faction_keywords)
                ),
                force_disposition_ids=tuple(
                    sorted({detachment.force_disposition_id, "take-and-hold", "purge-the-foe"})
                ),
                source_ids=detachment.source_ids,
            )
        )
    package = replace(
        package,
        army_catalog=replace(catalog, factions=tuple(factions), detachments=tuple(detachments)),
    )
    before = digest(package.to_payload())
    seconds = perf_counter() - start
    print(f"Faction batch01 preparation: {seconds:.6f}s; one package, {len(IDS)} real sheets")
    yield Section02Definitions(package, seconds)
    assert digest(package.to_payload()) == before, "Shared definitions were mutated"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def selection(
    d: Section02Definitions,
    sheet: str,
    identity: str,
    *,
    equipment: tuple[str, ...] = (),
    full: bool = False,
) -> UnitMusterSelection:
    datasheet = d.package.army_catalog.datasheet_by_id(sheet)
    wargear: list[WargearSelection] = []
    for suffix in equipment:
        wargear_id = f"{sheet}:{suffix}"
        option = next(o for o in datasheet.wargear_options if wargear_id in o.allowed_wargear_ids)
        wargear.append(WargearSelection(option.option_id, option.model_profile_id, (wargear_id,)))
    return UnitMusterSelection(
        unit_selection_id=identity,
        datasheet_id=sheet,
        model_profile_selections=tuple(
            ModelProfileSelection(c.model_profile_id, c.max_models if full else c.min_models)
            for c in datasheet.composition
        ),
        wargear_selections=tuple(wargear),
    )


@dataclass
class Scene:
    session: LocalGameSession
    state: GameState
    units: dict[str, UnitInstance]


def scene(
    d: Section02Definitions,
    own: tuple[UnitMusterSelection, ...],
    enemy: tuple[UnitMusterSelection, ...],
    *,
    phase: BattlePhase = BattlePhase.MOVEMENT,
    active: str = "owner",
    seed: str = "faction-batch01",
    attachments: tuple[AttachmentDeclaration, ...] = (),
    setup: bool = False,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> Scene:
    from tests.support.section10_fixtures import shooting_mission

    catalog = d.package.army_catalog
    requests: list[ArmyMusterRequest] = []
    for army_id, player, selections in (("own", "owner", own), ("foe", "opponent", enemy)):
        sheet = catalog.datasheet_by_id(selections[0].datasheet_id)
        faction_definition = next(
            f
            for f in catalog.factions
            if set(f.faction_keywords) & set(sheet.keywords.faction_keywords)
        )
        faction = faction_definition.faction_id
        detachment = next(did for fid, did in FACTIONS.values() if fid == faction)
        requests.append(
            ArmyMusterRequest(
                army_id=army_id,
                player_id=player,
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(faction, (detachment,)),
                force_disposition_id="take-and-hold" if player == "owner" else "purge-the-foe",
                unit_selections=selections,
                attachment_declarations=attachments if player == "owner" else (),
            )
        )
    mission = replace(shooting_mission(), terrain_features=terrain_features)
    if terrain_features:
        # Explicit custom component layout: never relabel synthetic geometry as
        # the source mission's canonical terrain/deployment layout.
        mission = replace(
            mission,
            terrain_layout_id="batch03:custom-terrain",
            deployment_map_id="batch03:custom-deployment",
        )
    config = GameConfig(
        game_id=seed,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
        army_catalog=catalog,
        army_muster_requests=tuple(requests),
        player_ids=("owner", "opponent"),
        turn_order=("owner", "opponent"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        allow_legacy_non_strict_rosters=True,
        model_geometries=d.package.model_geometries,
        mission_setup=mission,
    )
    # Copy only instantiated units, never the full catalog or source table graph.
    armies = tuple(
        deepcopy(
            muster_army(catalog=catalog, request=r, model_geometries=d.package.model_geometries)
        )
        for r in requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed: list[PlacedArmy] = []
    for ai, army in enumerate(armies):
        placements: list[UnitPlacement] = []
        for ui, unit in enumerate(army.units):
            poses = tuple(
                Pose.at(10 + ai * 25 + (i % 3) * 2.5, 10 + ui * 12 + (i // 3) * 2.5)
                for i in range(len(unit.own_models))
            )
            placements.append(unit_placement(army.army_id, army.player_id, unit, poses))
        placed.append(PlacedArmy(army.army_id, army.player_id, tuple(placements)))
    if setup:
        state.record_battlefield_state(BattlefieldRuntimeState(seed, 60, 44, placed_armies=()))
        state.stage = GameLifecycleStage.SETUP
        state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    else:
        state.record_battlefield_state(
            BattlefieldRuntimeState(
                seed, 60, 44, placed_armies=tuple(placed), terrain_features=terrain_features
            )
        )
        state.stage = GameLifecycleStage.BATTLE
        state.setup_step_index = None
        state.battle_phase_index = state.battle_phase_sequence.index(phase)
        state.battle_round = 1
        state.active_player_id = active
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    descriptor = config.ruleset_descriptor
    command = CommandPhaseHandler(ruleset_descriptor=descriptor, army_catalog=catalog)
    movement = MovementPhaseHandler(ruleset_descriptor=descriptor, army_catalog=catalog)
    shooting = ShootingPhaseHandler(ruleset_descriptor=descriptor, army_catalog=catalog)
    charge = ChargePhaseHandler(ruleset_descriptor=descriptor)
    fight = FightPhaseHandler(ruleset_descriptor=descriptor, army_catalog=catalog)
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.COMMAND: command,
            BattlePhase.MOVEMENT: movement,
            BattlePhase.SHOOTING: shooting,
            BattlePhase.CHARGE: charge,
            BattlePhase.FIGHT: fight,
        },
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
    )
    session = LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _command_phase_handler=command,
            _movement_phase_handler=movement,
            _shooting_phase_handler=shooting,
            _charge_phase_handler=charge,
            _fight_phase_handler=fight,
            _battle_round_flow=flow,
            _triggered_movement_handler=TriggeredMovementHandler(ruleset_descriptor=descriptor),
        )
    )
    # Ordinary lifecycle loading owns registration and static materialization.
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()
    return Scene(session, state, {u.unit_instance_id: u for a in armies for u in a.units})


def unit_placement(
    army: str, player: str, unit: UnitInstance, poses: tuple[Pose, ...]
) -> UnitPlacement:
    assert len(poses) == len(unit.own_models)
    return UnitPlacement(
        army,
        player,
        unit.unit_instance_id,
        tuple(
            ModelPlacement(army, player, unit.unit_instance_id, m.model_instance_id, p)
            for m, p in zip(unit.own_models, poses, strict=True)
        ),
    )


def locate(s: Scene, unit_id: str, poses: tuple[Pose, ...]) -> None:
    unit = s.units[unit_id]
    army = next(a for a in s.state.army_definitions if unit in a.units)
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(
        s.state.battlefield_state.with_unit_placement(
            unit_placement(army.army_id, army.player_id, unit, poses)
        )
    )


def request(status: LifecycleStatus, kind: str | None = None) -> DecisionRequest:
    r = status.decision_request
    assert r is not None, status
    if kind is not None:
        assert r.decision_type == kind, (r.decision_type, r.to_payload())
    return r


def events(s: LocalGameSession, kind: str) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for e in s.lifecycle.decision_controller.event_log.records:
        if e.event_type == kind:
            assert isinstance(e.payload, dict)
            result.append(e.payload)
    return result


def casualty_checkpoint(s: Scene, model_ids: tuple[str, ...]) -> None:
    """Explicit prior-casualty premise; tests do not certify the removal path here."""
    for ai, army in enumerate(s.state.army_definitions):
        units = tuple(
            replace(
                u,
                own_models=tuple(
                    replace(m, wounds_remaining=0) if m.model_instance_id in model_ids else m
                    for m in u.own_models
                ),
            )
            for u in army.units
        )
        s.state.army_definitions[ai] = replace(army, units=units)
        s.units.update({u.unit_instance_id: u for u in units})
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(s.state.battlefield_state.with_removed_models(model_ids))


def anchor(s: Scene, *, physical: bool = True) -> None:
    """Freeze the constructed physical turn boundary after final fixture placement."""
    from tests.setup_completion_helpers import (
        record_current_battlefield_placements_for_fixture,
        record_primary_turn_start_evidence_for_fixture,
    )

    if physical:
        record_current_battlefield_placements_for_fixture(
            s.state, decisions=s.session.lifecycle.decision_controller
        )
    record_primary_turn_start_evidence_for_fixture(
        s.state, decisions=s.session.lifecycle.decision_controller
    )


def translate(s: Scene, unit_id: str, dx: float) -> LifecycleStatus:
    """Submit one native Normal move from the current Movement unit request."""
    r = s.session.lifecycle.pending_decision_request()
    assert r is not None
    assert r.decision_type == "select_movement_unit"
    r = request(
        s.session.submit_option(
            request_id=r.request_id, option_id=unit_id, result_id=f"{r.request_id}:unit"
        ),
        "select_movement_action",
    )
    r = request(
        s.session.submit_option(
            request_id=r.request_id, option_id="normal_move", result_id=f"{r.request_id}:normal"
        ),
        "submit_movement_proposal",
    )
    return submit_translation(s, r, unit_id, dx)


def submit_translation(s: Scene, r: DecisionRequest, unit_id: str, dx: float) -> LifecycleStatus:
    from tests.sequential_translation_helpers import leading_first_translation_paths

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    assert s.state.battlefield_state is not None
    placement = s.state.battlefield_state.unit_placement_by_id(unit_id)
    context = MovementProposalRequest.from_decision_request_payload(r.payload)
    witness = PathWitness.for_paths(
        leading_first_translation_paths(
            tuple(
                (
                    p.model_instance_id,
                    (p.pose, Pose.at(p.pose.position.x + dx, p.pose.position.y, p.pose.position.z)),
                )
                for p in placement.model_placements
            ),
            dx=dx,
        )
    )
    assert context.movement_phase_action is not None
    assert context.context is not None
    mode = context.context.get("movement_mode")
    assert mode is None or isinstance(mode, str)
    proposal = MovementProposalPayload(
        r.request_id,
        context.proposal_kind,
        unit_id,
        context.movement_phase_action,
        witness,
        movement_mode=mode,
    )
    return s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id=f"{r.request_id}:path",
    )
