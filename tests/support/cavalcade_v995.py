"""Ordinary setup for the separately versioned native screening workload.

The finite recipe is intentionally equivalent to the retained roster regression.
That historical test stays byte-identical for authenticated scheduling evidence;
this helper shares public config/session owners, not duplicated engine behavior.
"""

import json
from pathlib import Path
from typing import TypedDict, cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyRegistration,
    PolicyRoute,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.deployment import (
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatusKind, SetupStep
from warhammer40k_core.engine.player_army_list import (
    army_muster_request_from_player_army_list,
    load_player_army_list,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
    mfm_2026_10,
)

ROOT = Path(__file__).resolve().parents[2]


def strict_mirror_session(*, private_rng_seed: str = "a1" * 32) -> LocalGameSession:
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
        private_rng_seed=private_rng_seed,
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


class _DeploymentFixture(TypedDict):
    mission_pool_entry_id: str
    deployment_order: list[str]
    placements: dict[str, list[ModelPlacementPayload]]


class _MirrorSetupPolicy:
    """Explicit fixture recipe, not a general policy or automatic pass fallback."""

    def __init__(self, player_id: str, fixture: _DeploymentFixture) -> None:
        self.fixture = fixture
        self.units = tuple(
            unit
            for unit in fixture["deployment_order"]
            if unit.startswith(f"cavalcade-{player_id[-1]}:")
        )
        self.index = 0

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        assert "private_rng_seed" not in context.observation_json
        assert "a1" * 32 not in context.observation_json
        family = context.route.decision_type
        options = {
            "select_secondary_missions": "fixed:assassination:bring_it_down",
            "select_reserve_declaration": "complete_reserve_declarations",
            "select_prebattle_action": "complete_prebattle_actions",
        }
        if family in options:
            return context.select_option(options[family])
        if family == "select_deployment_unit":
            unit_id = self.units[self.index]
            self.index += 1
            return context.select_option(f"deploy:{unit_id}")
        assert family == "submit_deployment_placement"
        request = DeploymentPlacementRequest.from_decision_request_payload(
            context.request["payload"]
        )
        proposal = DeploymentPlacementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            game_id=request.game_id,
            ruleset_descriptor_hash=request.ruleset_descriptor_hash,
            setup_step=SetupStep.DEPLOY_ARMIES,
            player_id=context.route.actor_id,
            unit_instance_id=request.unit_instance_id,
            placement_kind=request.placement_kind,
            model_placements=tuple(
                ModelPlacement.from_payload(p)
                for p in self.fixture["placements"][request.unit_instance_id]
            ),
            context=request.context,
        )
        return context.propose(validate_json_value(proposal.to_payload()))


def deployment_fixture() -> _DeploymentFixture:
    return cast(
        _DeploymentFixture,
        json.loads(
            ROOT.joinpath(
                "tests/factions/chaos_daemons/integration/fixtures/cavalcade_v995_deployment.json"
            ).read_text()
        ),
    )


def mirror_router(fixture: _DeploymentFixture) -> PolicyRouter:
    registrations: list[PolicyRegistration] = []
    for player in ("player-a", "player-b"):
        policy = _MirrorSetupPolicy(player, fixture)
        for family, step, kind in (
            ("select_secondary_missions", "select_secondary_missions", None),
            ("select_reserve_declaration", "declare_battle_formations", None),
            ("select_deployment_unit", "deploy_armies", None),
            ("submit_deployment_placement", "deploy_armies", "deployment_placement"),
            ("select_prebattle_action", "resolve_prebattle_actions", None),
        ):
            registrations.append(
                PolicyRegistration(
                    PolicyRoute(player, family, "setup", step, None, kind),
                    "mirror-explicit-setup-v1",
                    json.dumps({"fixture_hash": payload_digest(fixture), "player_id": player}),
                    policy,
                )
            )
    return PolicyRouter(tuple(registrations))
