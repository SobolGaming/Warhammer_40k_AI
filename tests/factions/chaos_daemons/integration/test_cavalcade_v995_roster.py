"""Strict admission of the exact app export; no roster or geometry exemptions."""

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import TypedDict, cast

import pytest

from tests.phase13b_shooting_declaration_helpers import (
    _compact_shooting_lifecycle,
    _proposal_from_request,
    _select_shooting_unit_and_type,
)
from tests.setup_completion_helpers import enter_battle_for_fixture
from tests.support.faction_batch01 import unit_placement
from tests.support.viewer_identity_fixtures import ordinal_identity_config_payload
from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    DEV_PLAYER_A_TOKEN,
    DEV_PLAYER_B_TOKEN,
    ViewerContext,
    bearer_authorization,
)
from warhammer40k_core.adapters.battlefield_projection import authoritative_geometry_hash
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.external_contract import (
    CREATE_SESSION_SCHEMA_VERSION,
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.session_protocol import AuthoritativeSession, SessionProtocolError
from warhammer40k_core.adapters.session_recovery import (
    recover_server_persistence_payload,
    server_persistence_payload,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.adapters.viewer_identity import ViewerIdentityError, ViewerIdentityMap
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
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    ModelGeometryCatalogError,
    ModelGeometrySourceEvidence,
)
from warhammer40k_core.core.rng import RandomSource
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    ModelPlacementPayload,
    PlacedArmy,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.deployment import (
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
)
from warhammer40k_core.engine.effects import EffectExpirationBoundary, EffectExpirationKind
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import datasheets
from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedContext
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import deterministic_tactical_secondary_draw
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
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


def _strict_mirror_session(*, private_rng_seed: str = "a1" * 32) -> LocalGameSession:
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


def test_private_seed_is_distinct_from_public_identity_and_absent_from_player_data() -> None:
    session = _strict_mirror_session()
    seed = session.lifecycle.config.private_rng_seed
    assert session.lifecycle.state is not None
    state = session.lifecycle.state
    assert seed == state.private_rng_seed
    assert seed != state.game_id
    checkpoint = session.to_persistence_payload()
    assert isinstance(checkpoint, dict)
    assert isinstance(checkpoint["rng_state"], dict)
    assert checkpoint["rng_state"]["seed"] == seed
    for player_id in ("player-a", "player-b"):
        surfaces = (
            session.view(viewer_player_id=player_id),
            state.to_public_payload(viewer_player_id=player_id),
            session.events_since(EventStreamCursor(), viewer_player_id=player_id),
            session.support_profile(),
            session.rules_catalog_view(),
        )
        for surface in surfaces:
            assert seed not in json.dumps(surface)
            assert "private_rng_seed" not in json.dumps(surface)


def test_private_seed_changes_future_randomness_without_changing_player_observation() -> None:
    left = _strict_mirror_session(private_rng_seed="a1" * 32)
    right = _strict_mirror_session(private_rng_seed="b2" * 32)
    assert left.view(viewer_player_id="player-a") == right.view(viewer_player_id="player-a")
    streams: list[list[int]] = []
    for session in (left, right):
        checkpoint = session.to_persistence_payload()
        assert isinstance(checkpoint, dict)
        source = RandomSource.from_payload(checkpoint["rng_state"])
        streams.append(
            [source.randint_inclusive(1, 6, stream_label="private-seed-test") for _ in range(32)]
        )
        restored = LocalGameSession.from_persistence_payload(checkpoint)
        assert restored.to_persistence_payload() == checkpoint
    assert streams[0] != streams[1]


def test_tactical_card_order_uses_private_seed_and_preserves_exclusions() -> None:
    session = _strict_mirror_session()
    setup = session.lifecycle.config.mission_setup
    assert setup is not None
    pack = warhammer_event_companion_2026_07_mission_pack()
    count = sum(m.availability.value in {"tactical", "both"} for m in pack.secondary_missions)
    first = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        private_rng_seed="a1" * 32,
        draw_id="draw-1",
        player_id="player-a",
        battle_round=1,
        draw_count=count,
    )
    same = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        private_rng_seed="a1" * 32,
        draw_id="draw-1",
        player_id="player-a",
        battle_round=1,
        draw_count=count,
    )
    other = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        private_rng_seed="b2" * 32,
        draw_id="draw-1",
        player_id="player-a",
        battle_round=1,
        draw_count=count,
    )
    later = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        private_rng_seed="a1" * 32,
        draw_id="draw-2",
        player_id="player-a",
        battle_round=1,
        draw_count=count,
    )
    assert first != later
    assert set(first) == set(later)
    with pytest.raises(GameLifecycleError, match="draw_id"):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            private_rng_seed="a1" * 32,
            draw_id="",
            player_id="player-a",
            battle_round=1,
            draw_count=1,
        )
    assert first == same
    assert first != other
    assert set(first) == set(other)
    remaining = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        private_rng_seed="a1" * 32,
        draw_id="draw-1",
        player_id="player-a",
        battle_round=1,
        draw_count=count - 1,
        excluded_secondary_mission_ids=(first[0],),
    )
    assert first[0] not in remaining
    assert len(remaining) == count - 1
    state = GameState.from_config(session.lifecycle.config)
    enter_battle_for_fixture(state)
    first_cards = state.draw_tactical_secondary_cards(
        player_id="player-a", source_result_id="reused-provenance", draw_count=count
    )
    assert state.tactical_secondary_draw_sequence == 1
    for card in first_cards:
        state.forget_secondary_mission_card_state(card)
    restored = GameState.from_payload(state.to_payload())
    later_cards = state.draw_tactical_secondary_cards(
        player_id="player-a", source_result_id="reused-provenance", draw_count=count
    )
    restored_cards = restored.draw_tactical_secondary_cards(
        player_id="player-a", source_result_id="reused-provenance", draw_count=count
    )
    assert later_cards == restored_cards
    assert tuple(c.secondary_mission_id for c in first_cards) != tuple(
        c.secondary_mission_id for c in later_cards
    )
    assert state.to_payload() == restored.to_payload()
    assert state.tactical_secondary_draw_sequence == 2
    assert "tactical_secondary_draw_sequence" not in state.to_public_payload(
        viewer_player_id="player-a"
    )
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="enough cards"):
        state.draw_tactical_secondary_cards(
            player_id="player-a", source_result_id="rejected", draw_count=1
        )
    assert state.to_payload() == before


def test_private_seed_must_survive_restore_and_match_config() -> None:
    session = _strict_mirror_session()
    payload = session.lifecycle.to_payload()
    assert payload["config"] is not None
    assert session.lifecycle.state is not None
    payload["state"]["private_rng_seed"] = "b2" * 32
    with pytest.raises(GameLifecycleError, match=r"seed.*config"):
        GameLifecycle.from_payload(payload)
    legacy_config = cast(dict[str, object], session.lifecycle.config.to_payload())
    legacy_config.pop("private_rng_seed")
    with pytest.raises(GameLifecycleError, match=r"private.*seed|legacy"):
        GameConfig.from_payload(cast(GameConfigPayload, legacy_config))
    legacy_state = cast(dict[str, object], session.lifecycle.state.to_payload())
    legacy_state.pop("private_rng_seed")
    with pytest.raises(GameLifecycleError, match=r"private.*seed|legacy"):
        GameState.from_payload(cast(GameStatePayload, legacy_state))
    for invalid_sequence in (None, True, -1, "0"):
        invalid_state = cast(dict[str, object], session.lifecycle.state.to_payload())
        if invalid_sequence is None:
            invalid_state.pop("tactical_secondary_draw_sequence")
        else:
            invalid_state["tactical_secondary_draw_sequence"] = invalid_sequence
        with pytest.raises(GameLifecycleError, match="tactical draw sequence"):
            GameState.from_payload(cast(GameStatePayload, invalid_state))
    with pytest.raises(GameLifecycleError, match=r"seed.*config"):
        GameLifecycle(
            state=replace(session.lifecycle.state, private_rng_seed="b2" * 32),
            _config=session.lifecycle.config,
        )


def test_fresh_private_seeds_and_explicit_config_copying() -> None:
    session = _strict_mirror_session()
    for invalid_seed in (None, True, "", "x" * 64, "a" * 63, "A" * 64):
        with pytest.raises(GameLifecycleError, match="Private RNG seed"):
            replace(session.lifecycle.config, private_rng_seed=cast(str, invalid_seed))
    with pytest.raises(GameLifecycleError, match="public game identity"):
        replace(session.lifecycle.config, game_id="c3" * 32, private_rng_seed="c3" * 32)
    first = replace(session.lifecycle.config, private_rng_seed="c3" * 32)
    second = replace(session.lifecycle.config, private_rng_seed="d4" * 32)
    assert GameState.from_config(first).private_rng_seed == first.private_rng_seed
    assert GameState.from_config(second).private_rng_seed == second.private_rng_seed
    left = GameState.from_payload(GameState.from_config(first).to_payload())
    right = GameState.from_payload(GameState.from_config(first).to_payload())
    assert left.private_rng_seed == right.private_rng_seed

    # Omission during fresh construction generates entropy; omission on restore
    # above is an error. Public game identity is identical in these new configs.
    def fresh_config() -> GameConfig:
        return GameConfig(
            game_id=first.game_id,
            ruleset_descriptor=first.ruleset_descriptor,
            army_catalog=first.army_catalog,
            army_muster_requests=first.army_muster_requests,
            player_ids=first.player_ids,
            turn_order=first.turn_order,
            fixed_secondary_mission_ids=first.fixed_secondary_mission_ids,
            model_geometries=first.model_geometries,
            mission_setup=first.mission_setup,
        )

    generated_a = fresh_config()
    generated_b = fresh_config()
    assert generated_a.private_rng_seed != generated_b.private_rng_seed
    assert generated_a.game_id == generated_b.game_id == first.game_id


def test_runner_rejects_operator_seed_that_aliases_public_catalog_identity() -> None:
    original = _strict_mirror_session()
    public_hash = original.rules_catalog_view()["source_hash"]
    session = _strict_mirror_session(private_rng_seed=public_hash)
    policy = _ProbePolicy()
    with pytest.raises(RunnerError, match="Private RNG authority appears"):
        BoundedPolicyRunner(
            session=session,
            router=_probe_router(session, policy),
            limits=RunLimits(policy_seed=3, max_decisions=1, max_seconds=120),
        ).run()
    assert policy.contexts == []
    assert session.decision_record_count() == 0


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
            # Structurally valid placements from the wrong physical component
            # are illegal without requiring a speculative geometry search.
            for placement in payload["model_placements"]:
                placement["unit_instance_id"] = "cavalcade-b:bloodcrushers-2"
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
    session.submit_viewer_option(
        viewer=ViewerContext.for_player("player-b"),
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
    if failure in {"stale", "invalid"}:
        assert "invalid" in str(caught.value).lower()


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
    session.submit_viewer_option(
        viewer=ViewerContext.for_player(context.route.actor_id),
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


def test_player_runner_expired_policy_choice_is_never_submitted() -> None:
    session = _strict_mirror_session()

    class SlowPolicy(_ProbePolicy):
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            action = super().choose(context)
            time.sleep(10.01)
            return action

    policy = SlowPolicy()
    with pytest.raises(RunnerError, match="elapsed-time progress limit") as caught:
        BoundedPolicyRunner(
            session=session,
            router=_probe_router(session, policy),
            limits=RunLimits(policy_seed=2, max_decisions=1, max_seconds=10),
        ).run()
    assert len(policy.contexts) == 1
    assert len(caught.value.report.decisions) == 1
    assert not caught.value.report.decisions[0].accepted
    assert session.decision_record_count() == 0


def test_player_runner_identity_binds_policy_seed_and_configuration() -> None:
    session = _strict_mirror_session()
    route = PolicyRoute.from_view(session.view(viewer_player_id="player-a"))
    ids: list[str] = []
    for seed, configuration in ((3, "{}"), (4, "{}"), (3, '{"mode":"other"}')):
        policy = _ProbePolicy()
        report = BoundedPolicyRunner(
            session=session,
            router=PolicyRouter((PolicyRegistration(route, "identity-v1", configuration, policy),)),
            limits=RunLimits(policy_seed=seed, max_decisions=1, max_seconds=120),
        ).run(stop_at=RunBoundary("setup", "select_secondary_missions"))
        assert policy.contexts == []
        assert report.stop_reason == "requested_boundary"
        ids.append(report.run_id)
    assert len(set(ids)) == 3


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
    assert request.actor_id == "player-a"
    target_id = units["enemy"].unit_instance_id

    class ShootingPolicy:
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            public = context.request
            request = DecisionRequest.from_payload(
                cast(
                    DecisionRequestPayload,
                    {
                        "request_id": public["request_id"],
                        "decision_type": public["decision_type"],
                        "actor_id": public["actor_id"],
                        "payload": public["payload"],
                        "options": public["options"],
                    },
                )
            )
            proposal = _proposal_from_request(request=request, target_unit_id=target_id)
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
    command_request = session.lifecycle.pending_decision_request()
    assert command_request is not None
    assert command_request.actor_id is not None
    view = session.view(viewer_player_id=command_request.actor_id)
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


def test_policy_choice_identity_ignores_another_actors_runner_history() -> None:
    class SelectingPolicy:
        def __init__(self) -> None:
            self.contexts: list[PlayerDecisionContext] = []

        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            self.contexts.append(context)
            return context.select_option("fixed:assassination:bring_it_down")

    first = _strict_mirror_session()
    route_a = PolicyRoute.from_view(first.view(viewer_player_id="player-a"))
    route_b = replace(route_a, actor_id="player-b")
    first_b = SelectingPolicy()
    with pytest.raises(RunnerError, match="decision progress limit"):
        BoundedPolicyRunner(
            session=first,
            router=PolicyRouter(
                (
                    PolicyRegistration(route_a, "fixed-secondary-v1", "{}", SelectingPolicy()),
                    PolicyRegistration(route_b, "fixed-secondary-v1", "{}", first_b),
                )
            ),
            limits=RunLimits(policy_seed=19, max_decisions=2, max_seconds=120),
        ).run()
    records = first.lifecycle.decision_controller.records
    assert len(records) == 2
    previous = records[0]
    second = _strict_mirror_session()
    assert previous.result.selected_option_id is not None
    second.submit_option(
        request_id=previous.request.request_id,
        option_id=previous.result.selected_option_id,
        result_id=previous.result.result_id,
    )
    second_b = SelectingPolicy()
    with pytest.raises(RunnerError, match="decision progress limit"):
        BoundedPolicyRunner(
            session=second,
            router=PolicyRouter(
                (PolicyRegistration(route_b, "fixed-secondary-v1", "{}", second_b),)
            ),
            limits=RunLimits(policy_seed=19, max_decisions=1, max_seconds=120),
        ).run()
    assert first_b.contexts[0].observation == second_b.contexts[0].observation
    assert first_b.contexts[0].choice_seed == second_b.contexts[0].choice_seed
    assert records[1].result == second.lifecycle.decision_controller.records[1].result


def test_hidden_reserve_choice_count_does_not_change_opponents_observation_or_event_ids() -> None:
    sessions: list[LocalGameSession] = []
    for extra_reserve in (False, True):
        session = _strict_mirror_session()
        for actor in ("player-a", "player-b"):
            pending = session.view(viewer_player_id=actor)["pending_decision"]
            assert pending is not None
            session.submit_viewer_option(
                viewer=ViewerContext.for_player(actor),
                request_id=pending["request_id"],
                option_id="fixed:assassination:bring_it_down",
                result_id=f"fixed:{actor}",
            )
            session.advance_until_decision_or_terminal()
        if extra_reserve:
            pending = session.view(viewer_player_id="player-a")["pending_decision"]
            assert pending is not None
            option = next(
                o
                for o in pending["options"]
                if o["option_id"].startswith("declare_deep_strike:")
                and "nurglings" in o["option_id"]
            )
            session.submit_viewer_option(
                viewer=ViewerContext.for_player("player-a"),
                request_id=pending["request_id"],
                option_id=option["option_id"],
                result_id="hidden-nurglings-reserve",
            )
            session.advance_until_decision_or_terminal()
        pending = session.view(viewer_player_id="player-a")["pending_decision"]
        assert pending is not None
        session.submit_viewer_option(
            viewer=ViewerContext.for_player("player-a"),
            request_id=pending["request_id"],
            option_id="complete_reserve_declarations",
            result_id="a-reserves-complete",
        )
        session.advance_until_decision_or_terminal()
        sessions.append(session)
    left, right = sessions
    assert left.lifecycle.pending_decision_request() != right.lifecycle.pending_decision_request()
    assert left.view(viewer_player_id="player-b") == right.view(viewer_player_id="player-b")
    assert left.events_since(
        EventStreamCursor(), viewer_player_id="player-b"
    ) == right.events_since(EventStreamCursor(), viewer_player_id="player-b")
    view = right.view(viewer_player_id="player-b")
    pending = view["pending_decision"]
    assert pending is not None
    before = right.lifecycle.to_payload()
    for viewer, request_id in (
        (ViewerContext.for_player("player-a"), pending["request_id"]),
        (ViewerContext.for_player("player-b"), "unissued-request"),
    ):
        with pytest.raises(GameLifecycleError):
            right.submit_viewer_option(
                viewer=viewer,
                request_id=request_id,
                option_id="complete_reserve_declarations",
                result_id="wrong",
            )
        assert right.lifecycle.to_payload() == before
    assert right.lifecycle.state is not None
    assert "decision_request_count" not in right.lifecycle.state.to_public_payload(
        viewer_player_id="player-b"
    )


def test_hidden_reserve_progress_preserves_server_metadata_and_cursor() -> None:
    source = _strict_mirror_session()
    server = AdapterGameServer(event_retention_limit=2)

    def request(
        method: str,
        path: str,
        token: str,
        body: JsonValue = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, JsonValue]:
        response = server.handle(
            method=method,
            path=path,
            authorization=bearer_authorization(token),
            body=body,
            query=query,
        )
        assert response.status_code in {200, 201}, response.payload
        assert isinstance(response.payload, dict)
        return response.payload

    created = request(
        "POST",
        "/sessions",
        DEV_ADMIN_TOKEN,
        {
            "schema_version": SESSION_CREATE_SCHEMA_VERSION,
            "config": validate_json_value(source.lifecycle.config.to_payload()),
        },
    )
    session_id = created["session_id"]
    assert isinstance(session_id, str)
    server._sessions[session_id].revision_retention_limit = 2  # pyright: ignore[reportPrivateUsage]
    base = f"/sessions/{session_id}"
    request(
        "POST",
        f"{base}/commands",
        DEV_ADMIN_TOKEN,
        {
            "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
            "command_id": "start",
            "session_id": session_id,
            "expected_session_revision": 0,
            "request_id": None,
            "result_id": None,
            "submission": {"submission_kind": "start_session"},
        },
    )

    def select(actor: str, option_id: str, command_id: str) -> None:
        token = DEV_PLAYER_A_TOKEN if actor == "player-a" else DEV_PLAYER_B_TOKEN
        metadata = request("GET", base, token)
        envelope = request("GET", f"{base}/projection", token)
        projection = envelope["projection"]
        assert isinstance(projection, dict)
        pending = projection["pending_decision"]
        assert isinstance(pending, dict)
        request(
            "POST",
            f"{base}/commands",
            token,
            {
                "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
                "command_id": command_id,
                "session_id": session_id,
                "expected_session_revision": metadata["session_revision"],
                "request_id": pending["request_id"],
                "result_id": f"{command_id}:result",
                "submission": {"submission_kind": "finite_option", "option_id": option_id},
            },
        )

    select("player-a", "fixed:assassination:bring_it_down", "secondary-a")
    select("player-b", "fixed:assassination:bring_it_down", "secondary-b")
    before = request("GET", base, DEV_PLAYER_B_TOKEN)
    cursor = before["event_cursor"]
    assert isinstance(cursor, str)
    assert before["last_activity_at"] is None
    select("player-a", "declare_deep_strike:cavalcade-a:nurglings", "hidden-reserve")
    assert request("GET", base, DEV_PLAYER_B_TOKEN) == before
    delta = request("GET", f"{base}/events", DEV_PLAYER_B_TOKEN, query={"cursor": cursor})
    assert delta["events"] == []
    assert delta["resync_required"] is False
    assert delta["next_cursor"] == cursor
    assert delta["from_revision"] == delta["to_revision"] == before["session_revision"]
    # Durable journal validation resolves the wire aliases back to exact engine
    # records and independently validates viewer revisions and cursor bindings.
    saved = server.persistence_payload()
    assert saved["sessions"]
    recovered = recover_server_persistence_payload(
        saved,
        principal_registry=server.principal_registry,
        session_recovery_factory=LocalGameSession.from_persistence_payload,
    )
    assert (
        server_persistence_payload(
            sessions=recovered.sessions,
            session_id_by_game_id=recovered.session_id_by_game_id,
            cursor_codec=recovered.cursor_codec,
            principal_registry=server.principal_registry,
            event_retention_limit=recovered.event_retention_limit,
        )
        == saved
    )


def test_viewer_identity_map_preserves_entities_and_rejects_unissued_references() -> None:
    payload: JsonValue = {
        "request_id": "decision-request-000007",
        "unit_instance_id": "unit-a:event-000007",
        "source_event_ids": ["event-000012"],
        "timing_window_id": "window:roll-000007",
        "descriptor_id": "window:roll-000007:descriptor",
        "catalog_record_id": "stable:catalog-descriptor",
        "game_id": "public-game:event-000007",
        "player_id": "public-player:event-000007",
        "player_ids": ["public-player:event-000007", "player-b"],
        "option_id": "roll-000007:component-0",
        "effect_key": "effect:event-000012",
        "unit_display_by_id": {"unit-a:event-000007": {"unit_instance_id": "unit-a:event-000007"}},
        "context_hash": "a" * 64,
        "metadata": {"label": "unchanged event-000012 text"},
        "reason": "Surge from event-000012 after roll-000007",
        "decision_id": "client-result",
        "resolving_decision_id": "client-result",
        "source_result_id": "client-result",
    }
    identities = ViewerIdentityMap("game-a:player-a")
    public = identities.project(payload)
    assert isinstance(public, dict)
    assert public["game_id"] == "public-game:event-000007"
    assert public["player_id"] == "public-player:event-000007"
    assert public["player_ids"] == ["public-player:event-000007", "player-b"]
    assert public["unit_instance_id"] != "unit-a:event-000007"
    assert public["metadata"] != {"label": "unchanged event-000012 text"}
    assert "event-000012" not in json.dumps(public)
    assert public["request_id"] != "decision-request-000007"
    assert public["decision_id"] == public["resolving_decision_id"] == public["source_result_id"]
    assert identities.resolve(public) == payload
    reordered = json.loads(json.dumps(payload, sort_keys=True))
    assert ViewerIdentityMap("game-a:player-a").project(reordered) == public
    other_ordinals = ViewerIdentityMap("game-a:player-a")
    assert (
        other_ordinals.project(
            {
                **cast(dict[str, JsonValue], payload),
                "request_id": "decision-request-000099",
                "metadata": {"label": "unchanged event-000999 text"},
                "reason": "Surge from event-000999 after roll-000099",
                "unit_instance_id": "unit-a:event-000099",
                "option_id": "roll-000099:component-0",
                "effect_key": "effect:event-000999",
                "unit_display_by_id": {
                    "unit-a:event-000099": {"unit_instance_id": "unit-a:event-000099"}
                },
                "source_event_ids": ["event-000999"],
                "timing_window_id": "window:roll-000099",
                "descriptor_id": "window:roll-000099:descriptor",
                "context_hash": "b" * 64,
            }
        )
        == public
    )
    with pytest.raises(ViewerIdentityError, match="unissued"):
        ViewerIdentityMap("game-b:player-a").resolve(public)
    with pytest.raises(ViewerIdentityError, match="unissued"):
        identities.resolve({"proposal_request_id": "decision-request-000007"})
    with pytest.raises(ViewerIdentityError, match="undeclared"):
        identities.project({"unregistered_authority_reference": "event-000012"})
    unchanged = ViewerIdentityMap("same-visible-history")
    hidden_change = ViewerIdentityMap("same-visible-history")
    first: JsonValue = {"request_id": "decision-request-000001", "context_hash": "a" * 64}
    assert unchanged.project(first) == hidden_change.project(first)
    assert unchanged.project(
        {"request_id": "decision-request-000002", "context_hash": "a" * 64}
    ) == hidden_change.project({"request_id": "decision-request-000009", "context_hash": "b" * 64})

    same_event_state = ViewerIdentityMap("same-visible-events")
    changed_event_state = ViewerIdentityMap("same-visible-events")
    for index in (1, 2):
        before: JsonValue = {"event_id": f"event-{index:06d}", "state_hash": "a" * 64}
        after: JsonValue = {"event_id": f"event-{index + 10:06d}", "state_hash": str(index) * 64}
        assert same_event_state.project(before) == changed_event_state.project(after)


def test_policy_context_rejects_undeclared_authority_fields() -> None:
    view = _strict_mirror_session().view(viewer_player_id="player-a")
    forged = cast(GameViewPayload, {**view, "lifecycle": {"private_rng_seed": "a1" * 32}})
    with pytest.raises(PolicyError, match="unknown projection"):
        PlayerDecisionContext.from_view(forged, choice_seed=3)
    pending = view["pending_decision"]
    assert pending is not None
    cast(dict[str, JsonValue], pending)["rng_state"] = {"seed": "a1" * 32}
    with pytest.raises(PolicyError, match="unknown request"):
        PlayerDecisionContext.from_view(view, choice_seed=3)


def test_hidden_dice_count_does_not_advance_public_roll_or_event_identities() -> None:
    visible: list[dict[str, JsonValue]] = []
    canonical_rolls: list[JsonValue] = []
    for hidden_roll in (False, True):
        manager = DiceRollManager("f0" * 32)
        if hidden_roll:
            manager.roll(
                DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="Private ability roll",
                    roll_type="private.ability",
                    actor_id="player-a",
                )
            )
            manager.event_log.mark_secret_suffix(
                start_index=0, player_id="player-a", visibility_source="core_ability_instance"
            )
            manager = DiceRollManager("f0" * 32, event_log=manager.event_log)
        manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Public ability roll",
                roll_type="public.ability",
                actor_id="player-b",
            )
        )
        records = manager.event_log.records
        assert isinstance(records[-1].payload, dict)
        canonical_rolls.append(records[-1].payload["roll_id"])
        delta = EventStreamCursor().events_since(manager.event_log, viewer_player_id="player-b")
        assert delta["next_cursor"] == len(delta["events"]) == 1
        event = delta["events"][0]
        assert isinstance(event["payload"], dict)
        visible.append({"event_id": event["event_id"], "roll_id": event["payload"]["roll_id"]})
        restored = EventLog.from_payload(manager.event_log.to_payload())
        assert EventStreamCursor().events_since(restored, viewer_player_id="player-b") == delta
        assert "f0" * 32 not in json.dumps(delta)
    assert canonical_rolls == ["roll-000001", "roll-000002"]
    assert visible[0] == visible[1]


def test_player_route_preserves_configured_ordinal_like_public_identity() -> None:
    player = "player-event-000001"
    payload = ordinal_identity_config_payload(
        validate_json_value(canonical_setup_prebattle_smoke_config().to_payload()),
        player_a_id=player,
        game_id="game-event-000001",
    )
    session = LocalGameSession()
    session.start(GameConfig.from_payload(cast(GameConfigPayload, payload)))
    session.advance_until_decision_or_terminal()
    view = session.view(viewer_player_id=player)
    assert view["game_id"] == "game-event-000001"
    assert view["player_ids"] == [player, "player-b"]
    assert PolicyRoute.from_view(view).actor_id == player
    assert PlayerDecisionContext.from_view(view, choice_seed=1).route.actor_id == player

    stored = json.loads(json.dumps(session.to_persistence_payload(), sort_keys=True))
    restored = LocalGameSession.from_persistence_payload(stored)
    assert restored.view(viewer_player_id=player) == view

    battlefield = view["battlefield_view"]
    assert battlefield is not None
    assert battlefield["authoritative_geometry_hash"] == authoritative_geometry_hash(
        bounds=battlefield["bounds"], authoritative=battlefield["authoritative"]
    )
    assert all(
        key == model["model_instance_id"]
        for key, model in battlefield["authoritative"]["models_by_id"].items()
    )


def test_recovery_validates_current_checkpoint_once_and_forks_isolated_authority() -> None:
    session = LocalGameSession()
    config = canonical_setup_prebattle_smoke_config(game_id="pr2-recovery-isolation")
    status = session.start(config)
    record = AuthoritativeSession.create(
        session_id="session:pr2-recovery-isolation",
        adapter_session=session,
        config=config,
        lifecycle_status=status,
        created_at="2026-08-21T16:00:00Z",
        started=True,
    )
    payload = record.to_persistence_payload()
    recovered_payloads: list[JsonValue] = []

    def recover_checkpoint(value: JsonValue) -> LocalGameSession:
        recovered_payloads.append(json.loads(json.dumps(value)))
        return LocalGameSession.from_persistence_payload(value)

    restored = AuthoritativeSession.from_persistence_payload(
        payload, session_recovery_factory=recover_checkpoint
    )
    snapshots = payload["revision_snapshots"]
    assert isinstance(snapshots, list)
    assert len(recovered_payloads) == len(snapshots)
    assert restored.to_persistence_payload() == payload
    snapshot_session = restored.current_snapshot().adapter_session
    before = snapshot_session.to_persistence_payload()
    assert restored.adapter_session is not snapshot_session
    advanced = restored.adapter_session.advance_until_decision_or_terminal()
    assert advanced.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert restored.adapter_session.to_persistence_payload() != before
    assert snapshot_session.to_persistence_payload() == before


@pytest.mark.parametrize("missing_snapshot", [False, True])
def test_recovery_rejects_current_checkpoint_drift_before_reuse(missing_snapshot: bool) -> None:
    session = LocalGameSession()
    config = canonical_setup_prebattle_smoke_config(game_id="pr2-recovery-drift")
    status = session.start(config)
    record = AuthoritativeSession.create(
        session_id="session:pr2-recovery-drift",
        adapter_session=session,
        config=config,
        lifecycle_status=status,
        created_at="2026-08-21T16:00:00Z",
        started=True,
    )
    payload = record.to_persistence_payload()
    if missing_snapshot:
        payload["revision_snapshots"] = []
        diagnostic = "current session snapshot is missing"
    else:
        adapter_payload = payload["adapter_session"]
        assert isinstance(adapter_payload, dict)
        adapter_payload["content_hash"] = "0" * 64
        diagnostic = "current adapter checkpoint drifted"
    with pytest.raises(SessionProtocolError, match=diagnostic):
        AuthoritativeSession.from_persistence_payload(
            payload, session_recovery_factory=LocalGameSession.from_persistence_payload
        )


def test_authoritative_history_hashes_remain_exact_across_cache_and_progress() -> None:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config(game_id="pr2-history-hashes"))

    def assert_history() -> str:
        history = session.authoritative_history_payload()
        assert history["checkpoint_hash"] == payload_digest(session.to_persistence_payload())
        assert history["authoritative_state_hash"] == payload_digest(session.lifecycle.to_payload())
        assert history["decision_records"] == [
            record.to_payload() for record in session.lifecycle.decision_controller.records
        ]
        assert history["event_records"] == [
            record.to_payload()
            for record in session.lifecycle.decision_controller.event_log.records
        ]
        return history["authoritative_state_hash"]

    first = assert_history()
    assert assert_history() == first
    advanced = session.advance_until_decision_or_terminal()
    assert advanced.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    progressed = assert_history()
    assert progressed != first
    assert assert_history() == progressed


def test_public_checkpoint_export_detaches_both_cold_and_warm_cache() -> None:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config(game_id="pr2-checkpoint-detachment"))
    for _ in range(2):
        checkpoint = session.to_persistence_payload()
        expected = payload_digest(checkpoint)
        assert isinstance(checkpoint, dict)
        lifecycle = checkpoint["lifecycle"]
        assert isinstance(lifecycle, dict)
        state = lifecycle["state"]
        assert isinstance(state, dict)
        state["game_id"] = "caller-mutated-game"
        assert payload_digest(session.to_persistence_payload()) == expected
        assert session.lifecycle.config.game_id == "pr2-checkpoint-detachment"
