"""Public native setup for bounded movement-witness membership evidence."""

from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from warhammer40k_core.adapters.battlefield_projection import BattlefieldModelEntityPayload
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.list_validation import AttachmentDeclaration, UnitMusterSelection
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import ModelPath, PathWitness
from warhammer40k_core.geometry.pose import Pose


def public_models(
    session: LocalGameSession, player: str
) -> dict[str, BattlefieldModelEntityPayload]:
    battlefield = session.view(viewer_player_id=player)["battlefield_view"]
    assert battlefield is not None
    return battlefield["authoritative"]["models_by_id"]


def quiet_choice(session: LocalGameSession, request: DecisionRequest) -> None:
    if request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"witness:quiet:{request.request_id}",
            payload=stratagem_decline_payload(),
        )
    else:
        choices = tuple(option.option_id for option in request.options)
        assert choices, request.decision_type
        option = (
            "fixed:assassination:bring_it_down"
            if request.decision_type == "select_secondary_missions"
            else next(
                (
                    x
                    for x in choices
                    if x.startswith(("complete_", "end_", "decline", "skip", "keep"))
                ),
                choices[0],
            )
        )
        if request.decision_type == "select_movement_action":
            option = "remain_stationary"
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option,
            result_id=f"witness:quiet:{request.request_id}",
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()


def native_movement_request(
    *, player: str = "player-a", attached: bool = False, action: str = "normal_move"
) -> tuple[LocalGameSession, DecisionRequest]:
    if action == "fall_back":
        from tests.movement_witness_fall_back_helpers import native_fall_back_request

        return native_fall_back_request(player=player, attached=attached)
    selections: tuple[UnitMusterSelection, ...] = (
        unit_selection(
            unit_selection_id="mover",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
    )
    attachments: tuple[AttachmentDeclaration, ...] = ()
    if attached:
        selections += (
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        )
        attachments = (AttachmentDeclaration("leader", "mover"),)
    config = phase11c_config(
        game_id=f"witness-native:{player}:{attached}:{action}",
        player_a_units=selections,
        player_b_units=selections,
        player_a_attachment_declarations=attachments,
        player_b_attachment_declarations=attachments,
    )
    assert config.mission_setup is not None
    mission = replace(config.mission_setup, terrain_features=())
    config = replace(
        config,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    session = LocalGameSession()
    session.start(config)
    for _ in range(150):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_movement_proposal" and request.actor_id == player:
            return session, request
        if request.decision_type == "submit_deployment_placement":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"witness:deploy:{request.request_id}",
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda i, owner, _model: Pose.at(
                        (8 if owner == "player-a" else 52) + (i // 3) * 1.5,
                        26 + (i % 3) * 1.5,
                        facing_degrees=0,
                    ),
                ),
            )
        elif request.actor_id == player and request.decision_type == "select_movement_unit":
            models = public_models(session, player)
            actor = next(
                row["rules_unit_instance_id"]
                for row in models.values()
                if row["owner_player_id"] == player and row["state"] == "placed"
            )
            assert actor is not None
            status = session.submit_option(
                request_id=request.request_id,
                option_id=actor,
                result_id=f"witness:unit:{request.request_id}",
            )
        elif request.actor_id == player and request.decision_type == "select_movement_action":
            option = next(
                x.option_id
                for x in request.options
                if isinstance(x.payload, dict) and x.payload.get("movement_phase_action") == action
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option,
                result_id=f"witness:action:{request.request_id}",
            )
        else:
            quiet_choice(session, request)
            continue
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Native movement proposal was not reached")


def public_movement_proposal(
    session: LocalGameSession, request: DecisionRequest, *, dx: float = 0.5
) -> MovementProposalPayload:
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert context.context is not None
    assert context.movement_phase_action is not None
    mode = context.context["movement_mode"]
    assert isinstance(mode, str)
    paths: list[ModelPath] = []
    assert request.actor_id is not None
    for row in public_models(session, request.actor_id).values():
        if row["rules_unit_instance_id"] != context.unit_instance_id or row["state"] != "placed":
            continue
        assert row["pose"] is not None
        position = row["pose"]["position"]
        start = Pose.at(
            position["x_inches"],
            position["y_inches"],
            position["z_inches"],
            facing_degrees=row["pose"]["facing_degrees"],
        )
        end = Pose.at(
            start.position.x + dx,
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        paths.append((row["model_instance_id"], (start, end)))
    assert paths
    # Move the front column first so each individual path preserves model separation.
    paths.sort(key=lambda item: item[1][0].position.x, reverse=dx >= 0)
    return MovementProposalPayload(
        proposal_request_id=context.request_id,
        proposal_kind=context.proposal_kind,
        unit_instance_id=context.unit_instance_id,
        movement_phase_action=context.movement_phase_action,
        movement_mode=mode,
        fall_back_mode=cast(str | None, context.context.get("fall_back_mode")),
        witness=PathWitness.for_paths(tuple(paths)),
    )


def proposal_json(proposal: MovementProposalPayload) -> JsonValue:
    return validate_json_value(proposal.to_payload())
