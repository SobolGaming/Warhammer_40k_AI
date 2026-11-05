"""Strict admission of the exact app export; no roster or geometry exemptions."""

import json
from dataclasses import replace
from pathlib import Path
from typing import TypedDict, cast

import pytest

from tests.phase13b_shooting_declaration_helpers import (
    _compact_shooting_lifecycle,
    _proposal_from_request,
    _select_shooting_unit_and_type,
)
from tests.support.faction_batch01 import unit_placement
from warhammer40k_core.adapters.access_control import DEV_ADMIN_TOKEN, bearer_authorization
from warhammer40k_core.adapters.external_contract import (
    CREATE_SESSION_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRegistration,
    PolicyRoute,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.ai.runner import (
    BoundedPolicyRunner,
    RunBoundary,
    RunLimits,
    RunnerError,
    RunReport,
)
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


class _InvalidPlacementPolicy(_MirrorSetupPolicy):
    def __init__(self, fixture: _DeploymentFixture, failure: str) -> None:
        super().__init__("player-b", fixture)
        self.failure = failure

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        valid = super().choose(context)
        assert valid.proposal_json is not None
        payload = json.loads(valid.proposal_json)
        if self.failure == "stale":
            payload["proposal_request_id"] = "stale-proposal"
        elif self.failure == "malformed":
            payload.pop("game_id")
        else:
            assert self.failure == "invalid"
            payload["model_placements"][0]["pose"]["position"]["x"] = -1000.0
        return context.propose(validate_json_value(payload))


def _deployment_fixture() -> _DeploymentFixture:
    return cast(
        _DeploymentFixture,
        json.loads(
            Path(__file__)
            .with_name("fixtures")
            .joinpath("cavalcade_v995_deployment.json")
            .read_text()
        ),
    )


@pytest.mark.parametrize("failure", ["stale", "malformed", "invalid"])
def test_player_runner_rejects_committed_placement_without_retry(failure: str) -> None:
    session = _strict_mirror_session()
    fixture = _deployment_fixture()
    # Reach the first real proposal through the bounded recipe, then commit one
    # deliberately invalid proposal. No direct controller replacement or stubs.
    BoundedPolicyRunner(
        session=session,
        router=_mirror_router(fixture),
        limits=RunLimits(policy_seed=19, max_decisions=4, max_seconds=120),
    ).run(stop_at=RunBoundary("setup", "deploy_armies"))
    view = session.view(viewer_player_id="player-b")
    request = view["pending_decision"]
    assert request is not None
    assert request["actor_id"] == "player-b"
    unit_id = fixture["deployment_order"][0]
    session.submit_option(
        request_id=request["request_id"],
        option_id=f"deploy:{unit_id}",
        result_id="select-fixture-unit",
    )
    route = PolicyRoute.from_view(session.view(viewer_player_id="player-b"))
    router = PolicyRouter(
        (
            PolicyRegistration(
                route,
                "invalid-proposal-v1",
                json.dumps({"failure": failure}),
                _InvalidPlacementPolicy(fixture, failure),
            ),
        )
    )
    count = session.decision_record_count()
    with pytest.raises(RunnerError) as caught:
        BoundedPolicyRunner(
            session=session,
            router=router,
            limits=RunLimits(policy_seed=19, max_decisions=1, max_seconds=120),
        ).run()
    assert session.decision_record_count() == count
    assert len(caught.value.report.decisions) == 1
    assert not caught.value.report.decisions[0].accepted


def _mirror_router(fixture: _DeploymentFixture) -> PolicyRouter:
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


class _ProbePolicy:
    def __init__(self, failure: str = "none") -> None:
        self.failure = failure
        self.contexts: list[PlayerDecisionContext] = []

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        self.contexts.append(context)
        if self.failure == "exhausted":
            raise CandidateExhaustedError("Declared search exhausted all candidates.")
        if self.failure == "malformed":
            return cast(PolicyAction, None)
        if self.failure == "submission_kind":
            return context.propose({})
        action = context.select_option("fixed:assassination:bring_it_down")
        if self.failure == "actor":
            return replace(action, actor_id="player-b")
        if self.failure == "request":
            return replace(action, request_id="stale-request")
        if self.failure == "observation":
            return replace(action, observation_hash="stale-observation")
        if self.failure == "invalid":
            return replace(action, option_id="not-an-engine-option")
        assert self.failure == "none"
        return action


def _probe_router(session: LocalGameSession, policy: _ProbePolicy) -> PolicyRouter:
    view = session.view(viewer_player_id="player-a")
    return PolicyRouter(
        (
            PolicyRegistration(
                PolicyRoute.from_view(view),
                "probe-v1",
                '{"choice":"fixed"}',
                policy,
            ),
        )
    )


@pytest.mark.parametrize(
    "failure",
    [
        "actor",
        "request",
        "observation",
        "invalid",
        "malformed",
        "submission_kind",
        "exhausted",
    ],
)
def test_player_runner_stops_after_one_bad_choice_without_substituting(failure: str) -> None:
    session = _strict_mirror_session()
    policy = _ProbePolicy(failure)
    initial_records = session.decision_record_count()
    runner = BoundedPolicyRunner(
        session=session,
        router=_probe_router(session, policy),
        limits=RunLimits(policy_seed=3, max_decisions=3, max_seconds=120),
    )
    with pytest.raises(RunnerError) as caught:
        runner.run()
    assert len(policy.contexts) == 1
    assert session.decision_record_count() == initial_records
    assert len(caught.value.report.decisions) == 1
    assert not caught.value.report.decisions[0].accepted
    assert caught.value.report.decisions[0].choice_seconds >= 0
    with pytest.raises(PolicyError, match="single-use"):
        runner.run()


def test_player_runner_is_reproducible_and_stops_at_decision_budget() -> None:
    session = _strict_mirror_session()
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    reports: list[RunReport] = []
    seeds: list[int] = []
    for current in (session, restored):
        policy = _ProbePolicy()
        with pytest.raises(RunnerError, match="decision progress limit") as caught:
            BoundedPolicyRunner(
                session=current,
                router=_probe_router(current, policy),
                limits=RunLimits(policy_seed=71, max_decisions=1, max_seconds=120),
            ).run()
        reports.append(caught.value.report)
        seeds.append(policy.contexts[0].choice_seed)
        assert len(policy.contexts) == 1
        assert len(caught.value.report.decisions) == 1
        assert caught.value.report.decisions[0].accepted
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="bounded-first-decision"))
            .run()
            .reproduced_exactly
        )
    assert reports[0].run_id == reports[1].run_id
    assert seeds[0] == seeds[1]
    assert session.to_persistence_payload() == restored.to_persistence_payload()


def test_player_context_is_detached_and_hides_opponent_secret_decisions() -> None:
    session = _strict_mirror_session()
    view = session.view(viewer_player_id="player-a")
    context = PlayerDecisionContext.from_view(view, choice_seed=3)
    original = context.observation_json
    view["public_secondary_mission_choices"].append({"tamper": True})
    context.observation["public_secondary_mission_choices"].append({"tamper": True})
    assert context.observation_json == original
    assert context.observation == session.view(viewer_player_id="player-a")
    assert set(context.__slots__) == {"route", "observation_json", "choice_seed"}
    opponent = session.view(viewer_player_id="player-b")
    assert opponent["pending_decision"] is not None
    assert opponent["pending_decision"]["request_id"] == "hidden-request"
    with pytest.raises(PolicyError, match="own pending actor"):
        PlayerDecisionContext.from_view(opponent, choice_seed=3)
    request = context.request
    session.submit_option(
        request_id=request["request_id"],
        option_id="fixed:assassination:bring_it_down",
        result_id="isolation-explicit-choice",
    )
    next_view = session.view(viewer_player_id="player-b")
    next_context = PlayerDecisionContext.from_view(next_view, choice_seed=4)
    assert next_context.route.actor_id == "player-b"
    assert next_view["public_secondary_mission_choices"] == [
        {"hidden": True, "player_id": "player-a", "selected": True}
    ]
    assert "rng_seed" not in next_context.observation
    assert "rng_state" not in next_context.observation


@pytest.mark.parametrize("dimension", ["actor_id", "decision_type", "setup_step", "proposal_kind"])
def test_player_routes_never_match_a_nearby_setup_route(dimension: str) -> None:
    session = _strict_mirror_session()
    route = PolicyRoute.from_view(session.view(viewer_player_id="player-a"))
    policy = _ProbePolicy()
    wrong = replace(route, **{dimension: "other"})
    router = PolicyRouter((PolicyRegistration(wrong, "wrong-v1", "{}", policy),))
    with pytest.raises(RunnerError, match="Unsupported exact policy route"):
        BoundedPolicyRunner(
            session=session,
            router=router,
            limits=RunLimits(policy_seed=2, max_decisions=1, max_seconds=120),
        ).run()
    assert policy.contexts == []
    assert session.decision_record_count() == 0


def test_player_routes_distinguish_battle_phase_and_reject_duplicates() -> None:
    command = PolicyRoute("player-a", "resolve_reaction_window", "battle", None, "command", None)
    fight = replace(command, battle_phase="fight")
    entry = PolicyRegistration(command, "command-v1", "{}", _ProbePolicy())
    router = PolicyRouter((entry,))
    assert router.resolve(command) is entry
    with pytest.raises(PolicyError, match="Unsupported exact"):
        router.resolve(fight)
    with pytest.raises(PolicyError, match="Duplicate"):
        PolicyRouter((entry, entry))


def test_player_runner_time_limit_is_an_error_before_policy_execution() -> None:
    session = _strict_mirror_session()
    policy = _ProbePolicy()
    with pytest.raises(RunnerError, match="elapsed-time progress limit"):
        BoundedPolicyRunner(
            session=session,
            router=_probe_router(session, policy),
            limits=RunLimits(policy_seed=2, max_decisions=1, max_seconds=1e-12),
        ).run()
    assert policy.contexts == []
    assert session.decision_record_count() == 0


def test_player_runner_preserves_engine_auto_selection_records_after_a_legal_action() -> None:
    lifecycle, units = _compact_shooting_lifecycle()
    session = LocalGameSession(lifecycle)
    status = session.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=status.decision_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="runner-regression-select",
    )
    proposal = _proposal_from_request(
        request=request, target_unit_id=units["enemy"].unit_instance_id
    )

    class ShootingPolicy:
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            return context.propose(validate_json_value(proposal.to_payload()))

    route = PolicyRoute.from_view(session.view(viewer_player_id="player-a"))
    before = session.decision_record_count()
    with pytest.raises(RunnerError, match="decision progress limit") as caught:
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter(
                (PolicyRegistration(route, "shooting-v1", "{}", ShootingPolicy()),)
            ),
            limits=RunLimits(policy_seed=3, max_decisions=1, max_seconds=120),
        ).run()
    assert len(caught.value.report.decisions) == 1
    assert caught.value.report.decisions[0].accepted
    assert [r.request.decision_type for r in lifecycle.decision_controller.records[before:]] == [
        "submit_shooting_declaration",
        "select_resolve_target_unit",
        "select_attack_weapon_group",
    ]
    assert (
        ReplayRunner.from_payload(
            session.replay_artifact(artifact_id="runner-auto-selection-regression")
        )
        .run()
        .reproduced_exactly
    )


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
    router = _mirror_router(fixture)
    report = BoundedPolicyRunner(
        session=session,
        router=router,
        limits=RunLimits(policy_seed=19, max_decisions=42, max_seconds=120),
    ).run(stop_at=RunBoundary("battle", "command"))
    assert report.stop_reason == "requested_boundary"
    assert len(report.decisions) == 42
    assert all(t.accepted for t in report.decisions)
    assert {t.route.actor_id for t in report.decisions} == {"player-a", "player-b"}
    assert {t.route.proposal_kind for t in report.decisions} == {None, "deployment_placement"}
    # Command is a real-session phase dispatch boundary, not an invented request.
    view = session.view(viewer_player_id="player-a")
    command_route = PolicyRoute.from_view(view)
    assert command_route.battle_phase == "command"
    wrong_phase = PolicyRegistration(
        replace(command_route, battle_phase="fight"), "wrong-phase-v1", "{}", _ProbePolicy()
    )
    count = session.decision_record_count()
    with pytest.raises(RunnerError, match="Unsupported exact policy route"):
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter((wrong_phase,)),
            limits=RunLimits(policy_seed=19, max_decisions=1, max_seconds=120),
        ).run()
    assert session.decision_record_count() == count
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
