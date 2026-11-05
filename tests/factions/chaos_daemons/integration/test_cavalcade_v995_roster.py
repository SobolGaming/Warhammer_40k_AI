"""Strict admission of the exact app export; no roster or geometry exemptions."""

import json
from dataclasses import replace
from pathlib import Path
from typing import TypedDict, cast

import pytest

from tests.support.faction_batch01 import unit_placement
from warhammer40k_core.adapters.access_control import DEV_ADMIN_TOKEN, bearer_authorization
from warhammer40k_core.adapters.external_contract import (
    CREATE_SESSION_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    ModelGeometryCatalogError,
    ModelGeometrySourceEvidence,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    ModelPlacementPayload,
    PlacedArmy,
)
from warhammer40k_core.engine.deployment import (
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
)
from warhammer40k_core.engine.effects import EffectExpirationBoundary, EffectExpirationKind
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import datasheets
from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedContext
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.player_army_list import (
    army_muster_request_from_player_army_list,
    load_player_army_list,
)
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
    mfm_2026_10,
)

ROOT = Path(__file__).resolve().parents[4]


def test_v995_army_strictly_musters_independently_for_both_players() -> None:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    army_list = load_player_army_list(ROOT / "data/army_lists/cavalcade-shadow-bloodthirster.json")
    armies: list[ArmyDefinition] = []
    for suffix in ("a", "b"):
        request = army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=army_list,
            points_source_package=mfm_2026_10.source_package(),
            army_id=f"cavalcade-{suffix}",
            player_id=f"player-{suffix}",
        )
        assert request.roster_legality_required
        assert sum(p.points for p in request.unit_points) == 1945
        assert sum(p.points for p in request.enhancement_point_values) == 55
        army = muster_army(
            catalog=package.army_catalog,
            request=request,
            model_geometries=package.model_geometries,
        )
        assert army.roster_legality_report.is_legal
        assert len(army.units) == 9
        assert sum(len(u.own_models) for u in army.units) == 39
        assert all(m.geometry is not None for u in army.units for m in u.own_models)
        armies.append(army)
    left = {m.model_instance_id for u in armies[0].units for m in u.own_models}
    right = {m.model_instance_id for u in armies[1].units for m in u.own_models}
    assert left.isdisjoint(right)
    assert armies[0].units[0] is not armies[1].units[0]


def _strict_mirror_session() -> LocalGameSession:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    army_list = load_player_army_list(ROOT / "data/army_lists/cavalcade-shadow-bloodthirster.json")
    requests = tuple(
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=army_list,
            points_source_package=mfm_2026_10.source_package(),
            army_id=f"cavalcade-{suffix}",
            player_id=f"player-{suffix}",
        )
        for suffix in ("a", "b")
    )
    config = GameConfig(
        game_id="cavalcade-v995-mirror",
        ruleset_descriptor=(
            RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
                descriptor_version="cavalcade-v995-mirror"
            )
        ),
        army_catalog=package.army_catalog,
        army_muster_requests=requests,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        model_geometries=package.model_geometries,
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
            terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
            attacker_player_id="player-a",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )
    session = LocalGameSession()
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    return session


def test_strict_mirror_session_finishes_mustering_and_round_trips_setup() -> None:
    session = _strict_mirror_session()
    assert session.lifecycle.state is not None
    assert len(session.lifecycle.state.army_definitions) == 2
    assert all(a.roster_legality_report.is_legal for a in session.lifecycle.state.army_definitions)
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.lifecycle.state is not None
    assert restored.to_persistence_payload() == checkpoint
    assert (
        restored.lifecycle.state.army_definitions[0]
        is not restored.lifecycle.state.army_definitions[1]
    )


@pytest.mark.parametrize(
    ("endpoint", "schema_version"),
    [("/games", CREATE_SESSION_SCHEMA_VERSION), ("/sessions", SESSION_CREATE_SCHEMA_VERSION)],
)
def test_exact_mirror_config_passes_network_admission(endpoint: str, schema_version: str) -> None:
    session = _strict_mirror_session()
    config = session.lifecycle.to_payload()["config"]
    response = AdapterGameServer().handle(
        method="POST",
        path=endpoint,
        authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        body=validate_json_value({"schema_version": schema_version, "config": config}),
    )
    assert response.status_code == 201, response.payload


class _DeploymentFixture(TypedDict):
    mission_pool_entry_id: str
    deployment_order: list[str]
    placements: dict[str, list[ModelPlacementPayload]]


def test_exact_mirror_deploys_all_78_models_and_replays_to_battle() -> None:
    """Explicit legal setup recipe, submitted through the shared adapter authority."""
    session = _strict_mirror_session()
    fixture = cast(
        _DeploymentFixture,
        json.loads(
            Path(__file__)
            .with_name("fixtures")
            .joinpath("cavalcade_v995_deployment.json")
            .read_text()
        ),
    )
    assert fixture["mission_pool_entry_id"] == "mission-purge-the-foe-vs-purge-the-foe-layout-1"
    for decision_type, option in (
        ("select_secondary_missions", "fixed:assassination:bring_it_down"),
        ("select_secondary_missions", "fixed:assassination:bring_it_down"),
        ("select_reserve_declaration", "complete_reserve_declarations"),
        ("select_reserve_declaration", "complete_reserve_declarations"),
    ):
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.decision_type == decision_type
        session.submit_option(
            request_id=request.request_id, option_id=option, result_id=f"{request.request_id}:setup"
        )
    for unit_id in fixture["deployment_order"]:
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.decision_type == "select_deployment_unit"
        session.submit_option(
            request_id=request.request_id,
            option_id=f"deploy:{unit_id}",
            result_id=f"{request.request_id}:unit",
        )
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.decision_type == "submit_deployment_placement"
        context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
        assert context.unit_instance_id == unit_id
        state = session.lifecycle.state
        assert state is not None
        assert request.actor_id is not None
        proposal = DeploymentPlacementProposal(
            proposal_request_id=context.request_id,
            proposal_kind=context.proposal_kind,
            game_id=state.game_id,
            ruleset_descriptor_hash=state.ruleset_descriptor_hash,
            setup_step=SetupStep.DEPLOY_ARMIES,
            player_id=request.actor_id,
            unit_instance_id=unit_id,
            placement_kind=context.placement_kind,
            model_placements=tuple(
                ModelPlacement.from_payload(p) for p in fixture["placements"][unit_id]
            ),
            context=context.context,
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=validate_json_value(proposal.to_payload()),
            result_id=f"{request.request_id}:placement",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    for player in ("player-a", "player-b"):
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.decision_type == "select_prebattle_action"
        assert request.actor_id == player
        assert f"scout_move:cavalcade-{player[-1]}:seekers" in {
            option.option_id for option in request.options
        }
        # Deliberately deploy everyone and decline Scout moves in this setup recipe.
        status = session.submit_option(
            request_id=request.request_id,
            option_id="complete_prebattle_actions",
            result_id=f"{request.request_id}:hold-position",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = session.lifecycle.state
    assert state is not None
    assert state.stage is GameLifecycleStage.BATTLE
    assert state.battle_round == 1
    assert state.current_battle_phase is BattlePhase.COMMAND
    assert session.lifecycle.pending_decision_request() is not None
    assert state.battlefield_state is not None
    assert (
        sum(
            len(unit.model_placements)
            for army in state.battlefield_state.placed_armies
            for unit in army.unit_placements
        )
        == 78
    )
    assert (
        LocalGameSession.from_persistence_payload(
            session.to_persistence_payload()
        ).to_persistence_payload()
        == session.to_persistence_payload()
    )
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="cavalcade-native-setup")
    )
    assert replay.run().reproduced_exactly


@pytest.mark.parametrize("engaged_when_selected", [True, False])
def test_mischief_makers_uses_selection_boundary_and_survives_source_movement(
    engaged_when_selected: bool,
) -> None:
    """Bounded engagement premise; this does not certify source-layout deployment."""
    session = _strict_mirror_session()
    assert session.lifecycle.state is not None
    state = GameState.from_payload(session.lifecycle.state.to_payload())
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        battlefield_layout_id=None,
        terrain_layout_id="cavalcade-mischief-component-layout",
        deployment_map_id="cavalcade-mischief-component-deployment",
        battlefield_regions=(),
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        objective_markers=(),
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    own, enemy = state.army_definitions
    source = next(u for u in own.units if u.unit_instance_id == "cavalcade-a:nurglings")
    selected = next(u for u in enemy.units if u.unit_instance_id == "cavalcade-b:bloodcrushers-1")
    source_x = 10 if engaged_when_selected else 40
    source_placement = unit_placement(
        own.army_id,
        own.player_id,
        source,
        tuple(Pose.at(source_x, 10 + i * 2) for i in range(3)),
    )
    selected_placement = unit_placement(
        enemy.army_id,
        enemy.player_id,
        selected,
        tuple(Pose.at(13, 10 + i * 2.5) for i in range(6)),
    )
    state.replace_battlefield_state(
        BattlefieldRuntimeState(
            state.game_id,
            44,
            60,
            placed_armies=(
                PlacedArmy(own.army_id, own.player_id, (source_placement,)),
                PlacedArmy(enemy.army_id, enemy.player_id, (selected_placement,)),
            ),
        )
    )
    profile = next(
        w
        for w in chaos_daemons_cavalcade_2026_11.catalog_package().army_catalog.wargear
        if w.wargear_id == "000001115:hellblade"
    ).weapon_profiles[0]
    hit = HitRollModifierContext(
        state,
        selected.unit_instance_id,
        selected.own_models[0].model_instance_id,
        source.unit_instance_id,
        profile,
        BattlePhase.FIGHT,
    )
    assert datasheets.mischief_makers_hit_roll_modifier(hit) == 0
    selection = FightUnitSelectedContext(
        state=state,
        player_id=enemy.player_id,
        battle_round=1,
        unit_instance_id=selected.unit_instance_id,
        fight_type="ordinary",
        ordering_band="remaining_combats",
        request_id="mischief:selection",
        result_id="mischief:selection-result",
    )
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    grants = bundle.fight_unit_selected_hook_registry.grants_for(selection)
    assert len(grants) == int(engaged_when_selected)
    for grant in grants:
        state.record_persisting_effect(grant.persisting_effect)
    assert state.battlefield_state is not None
    destination_x = 40 if engaged_when_selected else 10
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            unit_placement(
                own.army_id,
                own.player_id,
                source,
                tuple(Pose.at(destination_x, 10 + i * 2) for i in range(3)),
            )
        )
    )
    expected = -1 if engaged_when_selected else 0
    assert datasheets.mischief_makers_hit_roll_modifier(hit) == expected
    restored = GameState.from_payload(state.to_payload())
    assert datasheets.mischief_makers_hit_roll_modifier(replace(hit, state=restored)) == expected
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary(EffectExpirationKind.END_PHASE, 1, BattlePhase.FIGHT, "player-a")
    )
    assert datasheets.mischief_makers_hit_roll_modifier(hit) == 0


def test_provisional_geometry_round_trips_without_promoting_estimates() -> None:
    records = chaos_daemons_cavalcade_2026_11.catalog_package().model_geometries
    provisional = [
        evidence
        for record in records
        for evidence in record.evidence
        if evidence.reviewer_status is GeometryReviewStatus.PROVISIONAL_ESTIMATE
    ]
    assert len(provisional) == 7
    assert (
        sum(e.evidence_kind is GeometryEvidenceKind.UNVERIFIED_ESTIMATE for e in provisional) == 3
    )
    for evidence in provisional:
        assert ModelGeometrySourceEvidence.from_payload(evidence.to_payload()) == evidence
        if evidence.evidence_kind is GeometryEvidenceKind.UNVERIFIED_ESTIMATE:
            with pytest.raises(ModelGeometryCatalogError, match="cannot be verified"):
                replace(evidence, reviewer_status=GeometryReviewStatus.ACCEPTED)
