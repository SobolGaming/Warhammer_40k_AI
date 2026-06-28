from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.headless import submit_headless_decision
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.network import (
    network_events_since_payload,
    network_rules_catalog_view_payload,
    network_status_payload,
    network_view_payload,
    submit_network_option,
)
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.adapters.ui import (
    submit_ui_option,
    ui_events_since,
    ui_rules_catalog_view,
    ui_view,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.interfaces.cli import render_decision_request_for_cli, submit_cli_choice
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


@dataclass(frozen=True, slots=True)
class FixedHeadlessOptionRanker:
    option_id: str

    def choose_option(
        self,
        *,
        request: DecisionRequest,
        view: GameViewPayload,
    ) -> str:
        assert self.option_id in {option.option_id for option in request.options}
        assert view["viewer_player_id"] == request.actor_id
        return self.option_id


@dataclass(frozen=True, slots=True)
class DeploymentPayloadGenerator:
    session: LocalGameSession

    def generate_payload(
        self,
        *,
        request: DecisionRequest,
        view: GameViewPayload,
    ) -> JsonValue:
        assert request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
        assert view["viewer_player_id"] == request.actor_id
        return deployment_placement_payload_for_request(self.session.lifecycle, request=request)


def test_local_game_session_satisfies_shared_adapter_session_protocol() -> None:
    session, status = _fresh_started_session(game_id="phase18c-protocol-game")
    request = _decision_request(status)
    catalog_view = session.rules_catalog_view()
    game_view = session.view(viewer_player_id="player-a")
    event_delta = session.events_since(EventStreamCursor(), viewer_player_id="player-a")

    assert isinstance(session, AdapterGameSession)
    assert request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert catalog_view["catalog_id"] == session.lifecycle.config.army_catalog.catalog_id
    assert game_view["viewer_player_id"] == "player-a"
    assert event_delta["viewer_player_id"] == "player-a"
    assert validate_json_value(json.loads(json.dumps(catalog_view, sort_keys=True))) == catalog_view
    assert validate_json_value(json.loads(json.dumps(game_view, sort_keys=True))) == game_view
    assert validate_json_value(json.loads(json.dumps(event_delta, sort_keys=True))) == event_delta


def test_cli_ui_network_and_headless_finite_producers_submit_through_session() -> None:
    cli_session, cli_status = _fresh_started_session(game_id="phase18c-cli-producer-game")
    cli_request = _decision_request(cli_status)
    cli_prompt = render_decision_request_for_cli(cli_request)
    cli_follow_up = submit_cli_choice(
        session=cli_session,
        prompt=cli_prompt,
        choice="tactical",
        result_id="phase18c-cli-choice",
    )

    ui_session, ui_status = _fresh_started_session(game_id="phase18c-ui-producer-game")
    ui_request = _decision_request(ui_status)
    ui_follow_up = submit_ui_option(
        ui_session,
        {
            "request_id": ui_request.request_id,
            "option_id": "tactical",
            "result_id": "phase18c-ui-choice",
        },
    )

    network_session, network_status = _fresh_started_session(
        game_id="phase18c-network-producer-game"
    )
    network_request = _decision_request(network_status)
    network_follow_up = submit_network_option(
        network_session,
        {
            "request_id": network_request.request_id,
            "option_id": "tactical",
            "result_id": "phase18c-network-choice",
        },
    )

    headless_session, headless_status = _fresh_started_session(
        game_id="phase18c-headless-producer-game"
    )
    headless_follow_up = submit_headless_decision(
        session=headless_session,
        status=headless_status,
        viewer_player_id="player-a",
        result_id="phase18c-headless-choice",
        finite_option_ranker=FixedHeadlessOptionRanker("tactical"),
        parameterized_payload_generator=DeploymentPayloadGenerator(headless_session),
    )

    for session, follow_up in (
        (cli_session, cli_follow_up),
        (ui_session, ui_follow_up),
        (network_session, network_follow_up),
        (headless_session, headless_follow_up),
    ):
        assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        assert session.lifecycle.decision_controller.records[-1].result.selected_option_id == (
            "tactical"
        )


def test_ui_and_network_projection_wrappers_return_session_payloads() -> None:
    session, status = _fresh_started_session(game_id="phase18c-projection-wrapper-game")

    assert network_status_payload(status) == status.to_payload()
    assert ui_rules_catalog_view(session) == session.rules_catalog_view()
    assert network_rules_catalog_view_payload(session) == session.rules_catalog_view()
    assert ui_view(session, viewer_player_id="player-a") == session.view(
        viewer_player_id="player-a"
    )
    assert network_view_payload(session, viewer_player_id="player-a") == session.view(
        viewer_player_id="player-a"
    )
    assert ui_events_since(session, EventStreamCursor(), viewer_player_id="player-a") == (
        session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    )
    assert network_events_since_payload(
        session,
        EventStreamCursor(),
        viewer_player_id="player-b",
    ) == session.events_since(EventStreamCursor(), viewer_player_id="player-b")


def test_replay_adapter_submits_recorded_finite_decision_through_session() -> None:
    source, source_status = _fresh_started_session(game_id="phase18c-replay-finite-game")
    source_request = _decision_request(source_status)
    source.submit_option(
        request_id=source_request.request_id,
        option_id="tactical",
        result_id="phase18c-replay-finite-choice",
    )
    record = source.lifecycle.decision_controller.records[-1]

    target, _target_status = _fresh_started_session(game_id="phase18c-replay-finite-game")
    follow_up = submit_replay_record(session=target, record=record)

    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert target.lifecycle.decision_controller.records[-1].to_payload() == record.to_payload()


def test_headless_and_replay_parameterized_producers_submit_deployment_payloads() -> None:
    source, source_status = _session_at_first_deployment_placement(
        game_id="phase18c-parameterized-game"
    )
    source_request = _decision_request(source_status)
    source_follow_up = submit_headless_decision(
        session=source,
        status=source_status,
        viewer_player_id=cast(str, source_request.actor_id),
        result_id="phase18c-headless-deployment-placement",
        finite_option_ranker=FixedHeadlessOptionRanker("unused"),
        parameterized_payload_generator=DeploymentPayloadGenerator(source),
    )
    record = source.lifecycle.decision_controller.records[-1]

    target, _target_status = _session_at_first_deployment_placement(
        game_id="phase18c-parameterized-game"
    )
    replay_follow_up = submit_replay_record(session=target, record=record)

    assert source_follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert replay_follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert record.result.selected_option_id == PARAMETERIZED_DECISION_OPTION_ID
    assert target.lifecycle.decision_controller.records[-1].to_payload() == record.to_payload()


def _fresh_started_session(*, game_id: str) -> tuple[LocalGameSession, LifecycleStatus]:
    session = LocalGameSession()
    session.start(_config(game_id=game_id))
    return session, session.advance_until_decision_or_terminal()


def _session_at_first_deployment_placement(
    *,
    game_id: str,
) -> tuple[LocalGameSession, LifecycleStatus]:
    session, status = _fresh_started_session(game_id=game_id)
    first_request = _decision_request(status)
    assert first_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    status = session.submit_option(
        request_id=first_request.request_id,
        option_id="fixed:assassination:bring_it_down",
        result_id=f"{game_id}-secondary-a",
    )
    second_request = _decision_request(status)
    assert second_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    status = session.submit_option(
        request_id=second_request.request_id,
        option_id="fixed:assassination:bring_it_down",
        result_id=f"{game_id}-secondary-b",
    )
    selection_request = _decision_request(status)
    assert selection_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=selection_request.options[0].option_id,
        result_id=f"{game_id}-deployment-unit",
    )
    placement_request = _decision_request(status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    return session, status


def _config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase18c-session-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request
