"""Exact app-derived army lists and a bounded mixed-matchup deployment prefix."""

from pathlib import Path

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.deployment import (
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind, SetupStep
from warhammer40k_core.engine.player_army_list import (
    army_muster_request_from_player_army_list,
    load_player_army_list,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_monster_mash_2026_11,
    mfm_2026_10,
)

ROOT = Path(__file__).resolve().parents[2]
MONSTER_MASH_PLAYER = "player-a"
CAVALCADE_PLAYER = "player-b"
MISSION_LAYOUT = "take-and-hold-vs-purge-the-foe-layout-1"


def monster_mash_vs_cavalcade_config() -> GameConfig:
    package = chaos_daemons_monster_mash_2026_11.catalog_package()
    players = (MONSTER_MASH_PLAYER, CAVALCADE_PLAYER)
    roster_ids = ("monster-mash", "cavalcade-shadow-bloodthirster")
    rosters = tuple(
        load_player_army_list(ROOT / "data" / "army_lists" / f"{roster_id}.json")
        for roster_id in roster_ids
    )
    requests = tuple(
        army_muster_request_from_player_army_list(
            catalog=package.army_catalog,
            army_list=roster,
            points_source_package=mfm_2026_10.source_package(),
            army_id=army_id,
            player_id=player,
        )
        for roster, army_id, player in zip(
            rosters, ("monster-mash-a", "cavalcade-b"), players, strict=True
        )
    )
    return GameConfig(
        game_id="monster-mash-v995-vs-cavalcade",
        private_rng_seed="a1" * 32,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="monster-mash-v995-vs-cavalcade"
        ),
        army_catalog=package.army_catalog,
        army_muster_requests=requests,
        player_ids=players,
        turn_order=players,
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        model_geometries=package.model_geometries,
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id=f"mission-{MISSION_LAYOUT}",
            terrain_layout_id=MISSION_LAYOUT,
            attacker_player_id=players[0],
            attacker_force_disposition_id=rosters[0].force_disposition_id,
            defender_player_id=players[1],
            defender_force_disposition_id=rosters[1].force_disposition_id,
        ),
    )


def begin_staged_deployment(session: LocalGameSession) -> LifecycleStatus:
    """Choose fixed secondaries, declare both armies on the field, and place two anchors."""
    status = session.advance_until_decision_or_terminal()
    choices = (
        ("select_secondary_missions", "fixed:assassination:bring_it_down"),
        ("select_secondary_missions", "fixed:assassination:bring_it_down"),
        ("select_reserve_declaration", "complete_reserve_declarations"),
        ("select_reserve_declaration", "complete_reserve_declarations"),
    )
    for decision_type, option_id in choices:
        status = _submit_option(session, status, decision_type, option_id)
    for player_id, army_id, unit_suffix, x, y in (
        (CAVALCADE_PLAYER, "cavalcade-b", "belakor", 41.0, 57.0),
        (MONSTER_MASH_PLAYER, "monster-mash-a", "kairos-fateweaver", 3.0, 3.0),
    ):
        unit_id = f"{army_id}:{unit_suffix}"
        assert status.decision_request is not None
        assert status.decision_request.actor_id == player_id
        status = _submit_option(session, status, "select_deployment_unit", f"deploy:{unit_id}")
        viewer = ViewerContext.for_player(player_id)
        pending = session.view_for_context(viewer=viewer)["pending_decision"]
        assert pending is not None
        assert pending["decision_type"] == "submit_deployment_placement"
        request = DeploymentPlacementRequest.from_decision_request_payload(pending["payload"])
        assert request.unit_instance_id == unit_id
        (model_id,) = request.model_instance_ids
        proposal = DeploymentPlacementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            game_id=request.game_id,
            ruleset_descriptor_hash=request.ruleset_descriptor_hash,
            setup_step=SetupStep.DEPLOY_ARMIES,
            player_id=player_id,
            unit_instance_id=unit_id,
            placement_kind=request.placement_kind,
            model_placements=(
                ModelPlacement(army_id, player_id, unit_id, model_id, Pose.at(x, y)),
            ),
            context=request.context,
        )
        status = session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=pending["request_id"],
            payload=validate_json_value(proposal.to_payload()),
            result_id=f"monster-mash-v995-deploy:{unit_id}",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    return status


def _submit_option(
    session: LocalGameSession, status: LifecycleStatus, decision_type: str, option_id: str
) -> LifecycleStatus:
    request = status.decision_request
    assert request is not None, status
    assert request.actor_id is not None, status
    viewer = ViewerContext.for_player(request.actor_id)
    pending = session.view_for_context(viewer=viewer)["pending_decision"]
    assert pending is not None, status
    assert pending["decision_type"] == decision_type, status
    assert option_id in {option["option_id"] for option in pending["options"]}
    result = session.submit_viewer_option(
        viewer=viewer,
        request_id=pending["request_id"],
        option_id=option_id,
        result_id=f"monster-mash-v995-setup:{session.decision_record_count() + 1}",
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, result
    return result
