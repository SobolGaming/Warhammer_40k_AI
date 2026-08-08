from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import (
    default_deployment_pose,
    deployment_placement_payload_for_request,
)
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase13b_shooting_declaration_helpers import (
    _proposal_from_request as shooting_declaration_proposal,
)
from tests.phase13b_shooting_declaration_helpers import (
    _shooting_lifecycle as shooting_lifecycle,
)
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition, StratagemDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


@pytest.mark.integration
def test_local_session_drives_setup_movement_shooting_and_charge_via_facade() -> None:
    session = LocalGameSession()
    session.start(_config())
    status = session.advance_until_decision_or_terminal()
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = _submit_fixed_secondaries(session, status=status)
    status = _submit_all_deployments(session, status=status)
    _assert_pending_view(session, viewer_player_id="player-a", decision_type="select_movement_unit")

    status = _submit_pending_option(
        session,
        status=status,
        option_id="army-alpha:intercessor-unit-1",
        result_id="ws13-select-first-mover",
    )
    _assert_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = _submit_pending_option(
        session,
        status=status,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="ws13-first-normal-move",
    )
    status = _submit_movement_proposal(
        session,
        status=status,
        result_id="ws13-first-normal-move-proposal",
        dx=3.0,
    )
    status = _decline_optional_stratagem(session, status=status, result_id="ws13-decline-window")

    status = _submit_pending_option(
        session,
        status=status,
        option_id="army-alpha:intercessor-unit-2",
        result_id="ws13-select-second-mover",
    )
    _assert_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = _submit_pending_option(
        session,
        status=status,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="ws13-second-remains-stationary",
    )
    status = _decline_optional_stratagem(
        session,
        status=status,
        result_id="ws13-decline-end-movement-window",
    )

    _assert_request(status, SELECT_SHOOTING_UNIT_DECISION_TYPE)
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "movement_activation_completed",
        "battle_phase_completed",
    )
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = _submit_pending_option(
        session,
        status=status,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="ws13-complete-shooting",
    )
    _assert_request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "shooting_phase_completed",
        "battle_phase_completed",
    )
    _assert_pending_view(session, viewer_player_id="player-b", decision_type="select_movement_unit")


@pytest.mark.integration
def test_local_session_drives_charge_completion_via_projection_and_events() -> None:
    lifecycle, _units = charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="ws13-charge-completion",
    )
    session = LocalGameSession(lifecycle=lifecycle)
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = session.advance_until_decision_or_terminal()
    request = _assert_request(status, SELECT_CHARGING_UNIT_DECISION_TYPE)
    _assert_pending_view(session, viewer_player_id="player-a", decision_type="select_charging_unit")
    assert COMPLETE_CHARGE_PHASE_OPTION_ID in {option.option_id for option in request.options}

    status = _submit_pending_option(
        session,
        status=status,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="ws13-complete-charge",
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "charge_phase_completed",
        "battle_phase_completed",
    )
    _assert_pending_view(session, viewer_player_id="player-b", decision_type="select_movement_unit")


@pytest.mark.integration
def test_local_session_drives_fight_pass_via_projection_and_events() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="ws13-fight-pass",
        charge_fights_first_unit_keys=("intercessor-1",),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = session.advance_until_decision_or_terminal()
    request = _assert_request(status, FIGHT_ACTIVATION_DECISION_TYPE)
    _assert_pending_view(
        session,
        viewer_player_id="player-a",
        decision_type="select_fight_activation",
    )
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {option.option_id for option in request.options}

    status = _submit_pending_option(
        session,
        status=status,
        option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
        result_id="ws13-fight-pass",
    )
    event_delta = session.events_since(cursor, viewer_player_id="player-a")

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert units["intercessor-1"].unit_instance_id in str(event_delta["events"])
    _assert_event_types(event_delta, "eligible_to_fight_pass_recorded")


@pytest.mark.integration
def test_local_session_drives_armour_of_contempt_fight_save_completion_and_replay() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("defender",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "defender": Pose.at(12.0, 20.0),
        },
        game_id="ws14-armour-of-contempt-fight-facade",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        catalog=_armour_of_contempt_catalog(),
        enemy_unit_specs={
            "defender": (
                "ws14-adeptus-astartes-character",
                "core-character-leader",
                1,
            ),
        },
        enemy_faction_id="space-marines",
        enemy_detachment_ids=("gladius-task-force",),
    )
    state = lifecycle.state
    assert state is not None
    _grant_facade_cp(state=state, player_id="player-b")
    session = LocalGameSession(lifecycle=lifecycle)

    status = _drain_facade_movement_requests(
        session,
        session.advance_until_decision_or_terminal(),
        result_prefix="ws14-aoc-fight-opening",
    )
    activation_request = _assert_request(status, FIGHT_ACTIVATION_DECISION_TYPE)
    activation_option = next(
        option
        for option in activation_request.options
        if units["attacker"].unit_instance_id in str(option.payload)
    )
    status = session.submit_option(
        request_id=activation_request.request_id,
        option_id=activation_option.option_id,
        result_id="ws14-aoc-fight-activation",
    )
    status = _drain_facade_movement_requests(
        session,
        status,
        result_prefix="ws14-aoc-fight-pile-in",
    )
    declaration_request = _assert_request(status, SUBMIT_MELEE_DECLARATION_DECISION_TYPE)
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        payload=_minimal_melee_declaration_payload(declaration_request),
        result_id="ws14-aoc-melee-declaration",
    )

    stratagem_request = _assert_request(status, STRATAGEM_DECISION_TYPE)
    _assert_pending_request_for_both_players(session, stratagem_request)
    stratagem_option = next(
        option
        for option in stratagem_request.options
        if _option_stratagem_id(option.payload) == "000008352002"
        and _option_target_unit_id(option.payload) == units["defender"].unit_instance_id
    )
    status = session.submit_option(
        request_id=stratagem_request.request_id,
        option_id=stratagem_option.option_id,
        result_id="ws14-aoc-fight-use-stratagem",
    )
    assert state.command_point_total("player-b") == 0

    status = _drive_attack_sequence_through_facade(
        session,
        status,
        result_prefix="ws14-aoc-fight-resolution",
    )

    assert _assert_request(status).decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert not any(
        "000008352002" in effect.source_rule_id
        for effect in state.persisting_effects_for_unit(units["defender"].unit_instance_id)
    )
    _assert_attack_save_used_modified_ap(lifecycle, expected_armor_penetration=-1)
    assert _event_type_count(lifecycle, "attack_sequence_completed") == 1
    assert _event_type_count(lifecycle, "rule_execution_effect_applied") == 1
    assert _event_type_count(lifecycle, "generic_rule_attack_sequence_effects_expired") == 1
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws14:aoc:fight-facade")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_drives_armour_of_contempt_shared_shooting_path() -> None:
    lifecycle, units = shooting_lifecycle(
        alpha_unit_ids=("attacker",),
        game_id="ws14-armour-of-contempt-shooting-facade",
        enemy_unit_specs=(
            (
                "defender",
                "ws14-adeptus-astartes-infantry",
                "core-intercessor-like",
                5,
            ),
        ),
        catalog=_armour_of_contempt_catalog(),
        enemy_faction_id="space-marines",
        enemy_detachment_ids=("gladius-task-force",),
    )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    state = lifecycle.state
    assert state is not None
    _grant_facade_cp(state=state, player_id="player-b")
    session = LocalGameSession(lifecycle=lifecycle)

    status = session.advance_until_decision_or_terminal()
    selection_request = _assert_request(status, SELECT_SHOOTING_UNIT_DECISION_TYPE)
    status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=units["attacker"].unit_instance_id,
        result_id="ws14-aoc-select-shooter",
    )
    shooting_type_request = _assert_request(status, SELECT_SHOOTING_TYPE_DECISION_TYPE)
    status = session.submit_option(
        request_id=shooting_type_request.request_id,
        option_id=ShootingType.NORMAL.value,
        result_id="ws14-aoc-select-shooting-type",
    )
    declaration_request = _assert_request(status, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE)
    proposal = shooting_declaration_proposal(
        request=declaration_request,
        target_unit_id=units["defender"].unit_instance_id,
    )
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="ws14-aoc-shooting-declaration",
    )

    stratagem_request = _assert_request(status, STRATAGEM_DECISION_TYPE)
    _assert_pending_request_for_both_players(session, stratagem_request)
    stratagem_option = next(
        option
        for option in stratagem_request.options
        if _option_stratagem_id(option.payload) == "000008352002"
        and _option_target_unit_id(option.payload) == units["defender"].unit_instance_id
    )
    status = session.submit_option(
        request_id=stratagem_request.request_id,
        option_id=stratagem_option.option_id,
        result_id="ws14-aoc-shooting-use-stratagem",
    )
    status = _drive_attack_sequence_through_facade(
        session,
        status,
        result_prefix="ws14-aoc-shooting-resolution",
    )

    resumed_request = _assert_request(status)
    assert resumed_request.decision_type != STRATAGEM_DECISION_TYPE
    assert not any(
        "000008352002" in effect.source_rule_id
        for effect in state.persisting_effects_for_unit(units["defender"].unit_instance_id)
    )
    _assert_attack_save_used_modified_ap(lifecycle, expected_armor_penetration=0)
    assert _event_type_count(lifecycle, "attack_sequence_completed") == 1
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws14:aoc:shooting-facade")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def _submit_fixed_secondaries(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    for result_id in ("ws13-secondary-a", "ws13-secondary-b"):
        request = _assert_request(current, SECONDARY_MISSION_DECISION_TYPE)
        current = session.submit_option(
            request_id=request.request_id,
            option_id="fixed:assassination:bring_it_down",
            result_id=result_id,
        )
    return current


def _submit_all_deployments(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    result_number = 1
    while current.decision_request is not None and current.decision_request.decision_type in {
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    }:
        request = current.decision_request
        result_id = f"ws13-deploy-{result_number:06d}"
        if request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
            current = session.submit_option(
                request_id=request.request_id,
                option_id=request.options[0].option_id,
                result_id=result_id,
            )
        else:
            current = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=_shooting_reachable_deployment_pose,
                ),
                result_id=result_id,
            )
        result_number += 1
    return current


def _submit_pending_option(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    request = _assert_request(status)
    return session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=result_id,
    )


def _submit_movement_proposal(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    result_id: str,
    dx: float,
) -> LifecycleStatus:
    request = _assert_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=ProposalKind.NORMAL_MOVE,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        movement_mode=MovementMode.NORMAL.value,
        witness=straight_line_witness_for_unit(
            session.lifecycle,
            unit_instance_id=proposal.unit_instance_id,
            dx=dx,
        ),
    ).to_payload()
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _decline_optional_stratagem(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = _assert_request(status)
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=stratagem_decline_payload(),
        result_id=result_id,
    )


def _assert_request(
    status: LifecycleStatus,
    decision_type: str | None = None,
) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    if decision_type is not None:
        assert status.decision_request.decision_type == decision_type
    return status.decision_request


def _assert_pending_view(
    session: LocalGameSession,
    *,
    viewer_player_id: str,
    decision_type: str,
) -> None:
    view = session.view(viewer_player_id=viewer_player_id)
    pending = view["pending_decision"]
    assert pending is not None
    assert pending["decision_type"] == decision_type
    assert "object at 0x" not in str(view)


def _assert_event_types(
    event_delta: EventStreamDeltaPayload,
    *event_types: str,
) -> None:
    visible_event_types = {event["event_type"] for event in event_delta["events"]}
    for event_type in event_types:
        assert event_type in visible_event_types


def _cursor_after(session: LocalGameSession, *, viewer_player_id: str) -> EventStreamCursor:
    event_delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer_player_id)
    return EventStreamCursor(event_delta["next_cursor"])


def _armour_of_contempt_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    character = base_catalog.datasheet_by_id("core-character-leader")
    infantry = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    astartes_character = replace(
        character,
        datasheet_id="ws14-adeptus-astartes-character",
        name="WS14 Adeptus Astartes Character",
        keywords=DatasheetKeywordSet(
            keywords=character.keywords.keywords,
            faction_keywords=("ADEPTUS ASTARTES",),
        ),
        source_ids=("datasheet:ws14-adeptus-astartes-character",),
    )
    astartes_infantry = replace(
        infantry,
        datasheet_id="ws14-adeptus-astartes-infantry",
        name="WS14 Adeptus Astartes Infantry",
        keywords=DatasheetKeywordSet(
            keywords=infantry.keywords.keywords,
            faction_keywords=("ADEPTUS ASTARTES",),
        ),
        source_ids=("datasheet:ws14-adeptus-astartes-infantry",),
    )
    return replace(
        base_catalog,
        catalog_id="ws14-armour-of-contempt-facade",
        source_package_id="data-package:core-v2:ws14-armour-of-contempt-facade:0.1.0",
        datasheets=(*base_catalog.datasheets, astartes_character, astartes_infantry),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id="space-marines",
                name="Space Marines",
                faction_keywords=("ADEPTUS ASTARTES",),
                source_ids=("faction:space-marines",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="gladius-task-force",
                name="Gladius Task Force",
                faction_id="space-marines",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    astartes_character.datasheet_id,
                    astartes_infantry.datasheet_id,
                ),
                force_disposition_ids=("purge-the-foe",),
                stratagem_ids=("000008352002",),
                source_ids=("detachment:gladius-task-force",),
            ),
        ),
        stratagems=(
            *base_catalog.stratagems,
            StratagemDefinition(
                stratagem_id="000008352002",
                name="Armour of Contempt",
                source_id=("phase17e:stratagem:space-marines:gladius-task-force:000008352002"),
                command_point_cost=1,
                timing_tags=("shooting", "fight"),
            ),
        ),
    )


def _grant_facade_cp(*, state: GameState, player_id: str) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=1,
        source_id=f"ws14-aoc-facade-grant:{player_id}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _minimal_melee_declaration_payload(request: DecisionRequest) -> JsonValue:
    proposal = MeleeDeclarationProposalRequest.from_decision_request(request)
    declarations: list[dict[str, JsonValue]] = []
    selected_model_ids: set[str] = set()
    for raw_weapon in proposal.available_weapons:
        weapon = cast(dict[str, JsonValue], raw_weapon)
        model_instance_id = cast(str, weapon["model_instance_id"])
        target_unit_ids = cast(list[str], weapon["engaged_target_unit_instance_ids"])
        if (
            model_instance_id in selected_model_ids
            or weapon["is_extra_attacks"] is True
            or not target_unit_ids
        ):
            continue
        selected_model_ids.add(model_instance_id)
        declarations.append(
            {
                "attacker_model_instance_id": model_instance_id,
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile_id"],
                "target_allocations": [
                    {"target_unit_instance_id": target_unit_ids[0]},
                ],
            }
        )
    assert declarations
    return validate_json_value(
        {
            "proposal_request_id": proposal.request_id,
            "proposal_kind": proposal.proposal_kind,
            "player_id": proposal.actor_id,
            "battle_round": proposal.battle_round,
            "unit_instance_id": proposal.unit_instance_id,
            "source_decision_request_id": proposal.source_decision_request_id,
            "source_decision_result_id": proposal.source_decision_result_id,
            "declarations": declarations,
        }
    )


def _drain_facade_movement_requests(
    session: LocalGameSession,
    status: LifecycleStatus,
    *,
    result_prefix: str,
) -> LifecycleStatus:
    current = status
    result_index = 1
    while (
        current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        context = cast(dict[str, JsonValue], proposal.context)
        current = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=validate_json_value(
                {
                    "proposal_request_id": proposal.request_id,
                    "proposal_kind": proposal.proposal_kind.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "movement_phase_action": proposal.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                }
            ),
            result_id=f"{result_prefix}-{result_index:03d}",
        )
        result_index += 1
    return current


def _drive_attack_sequence_through_facade(
    session: LocalGameSession,
    status: LifecycleStatus,
    *,
    result_prefix: str,
) -> LifecycleStatus:
    current = status
    for result_index in range(1, 129):
        if _event_type_count(session.lifecycle, "attack_sequence_completed") == 1:
            return current
        request = _assert_request(current)
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            current = _drain_facade_movement_requests(
                session,
                current,
                result_prefix=f"{result_prefix}-movement-{result_index:03d}",
            )
            continue
        decline_option = next(
            (
                option
                for option in request.options
                if option.option_id == "decline_stratagem_window"
            ),
            None,
        )
        selected_option = request.options[0] if decline_option is None else decline_option
        current = session.submit_option(
            request_id=request.request_id,
            option_id=selected_option.option_id,
            result_id=f"{result_prefix}-{result_index:03d}",
        )
    raise AssertionError("Attack sequence did not resume to its phase selection request.")


def _assert_pending_request_for_both_players(
    session: LocalGameSession,
    request: DecisionRequest,
) -> None:
    for viewer_player_id in ("player-a", "player-b"):
        pending = session.view(viewer_player_id=viewer_player_id)["pending_decision"]
        assert pending is not None
        assert pending["request_id"] == request.request_id
        assert pending["decision_type"] == STRATAGEM_DECISION_TYPE
        assert "object at 0x" not in json.dumps(pending, sort_keys=True)


def _option_stratagem_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    catalog_record = payload.get("catalog_record")
    if not isinstance(catalog_record, dict):
        return None
    definition = catalog_record.get("definition")
    if not isinstance(definition, dict):
        return None
    value = definition.get("stratagem_id")
    return value if isinstance(value, str) else None


def _option_target_unit_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    target_binding = payload.get("target_binding")
    if not isinstance(target_binding, dict):
        return None
    value = target_binding.get("target_unit_instance_id")
    return value if isinstance(value, str) else None


def _assert_attack_save_used_modified_ap(
    lifecycle: GameLifecycle,
    *,
    expected_armor_penetration: int,
) -> None:
    save_options = tuple(
        option
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        for event_payload in (_json_object(event.payload),)
        if event_payload.get("step") == "save"
        for save_payload in (_json_object(event_payload["payload"]),)
        for option in cast(list[dict[str, JsonValue]], save_payload["save_options"])
    )
    assert save_options
    assert any(option["armor_penetration"] == expected_armor_penetration for option in save_options)


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _event_type_count(lifecycle: GameLifecycle, event_type: str) -> int:
    return sum(
        event.event_type == event_type for event in lifecycle.decision_controller.event_log.records
    )


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="ws13-adapter-phase-families",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-ws13-adapter-phase-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
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
    unit_selection_ids: tuple[str, ...],
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
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _shooting_reachable_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id in {
        "army-alpha:intercessor-unit-1",
        "army-beta:intercessor-unit-3",
    }:
        x = 15.5 if player_id == "player-a" else 43.5
        facing = 0.0 if player_id == "player-a" else 180.0
        return Pose.at(x, 17.0 + (index * 1.8), 0.0, facing_degrees=facing)
    return default_deployment_pose(index, player_id, model_instance_id)
