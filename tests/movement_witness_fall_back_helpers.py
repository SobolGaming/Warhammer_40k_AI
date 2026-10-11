"""Native Charge/Fight/Fall Back path using predeclared analytical W50 Core models.

The attached scene has one bodyguard and one leader under the existing explicit
legacy roster fixture flag. Combat, dice, setup and proposals stay native. These
finite synthetic ownership controls do not certify faction/gameplay support.
"""

from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.movement_witness_membership_helpers import (
    public_models,
    public_movement_proposal,
    quiet_choice,
)
from tests.phase11c_command_phase_helpers import mustered_armies, phase11c_config, unit_selection
from tests.phase13b_shooting_declaration_helpers import _compact_intercessor_catalog
from tests.psychic_modifier_helpers import submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import FightMovementProposal
from warhammer40k_core.engine.list_validation import AttachmentDeclaration, UnitMusterSelection
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import ModelPath, PathWitness
from warhammer40k_core.geometry.pose import Pose


def native_fall_back_request(
    *, player: str, attached: bool
) -> tuple[LocalGameSession, DecisionRequest]:
    enemy = "player-b" if player == "player-a" else "player-a"
    units: tuple[UnitMusterSelection, ...] = (
        unit_selection(
            unit_selection_id="mover",
            datasheet_id="core-intercessor-like-infantry" if attached else "core-character-leader",
            model_profile_id="core-intercessor-like" if attached else "core-character-leader",
            model_count=1,
        ),
    )
    attachments = (AttachmentDeclaration("leader", "mover"),) if attached else ()
    if attached:
        units += (
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        )
    config = phase11c_config(
        game_id=f"witness-native-fall-back:{player}:{attached}",
        player_a_units=units,
        player_b_units=units,
        player_a_attachment_declarations=attachments,
        player_b_attachment_declarations=attachments,
    )
    # Analytical W50 profiles are declared before start; native combat and RNG remain intact.
    config = replace(
        config,
        army_catalog=replace(
            _compact_intercessor_catalog(config.army_catalog),
            datasheets=tuple(
                replace(
                    sheet,
                    model_profiles=tuple(
                        replace(
                            profile,
                            characteristics=tuple(
                                CharacteristicValue.from_raw(Characteristic.WOUNDS, 50)
                                if value.characteristic is Characteristic.WOUNDS
                                else value
                                for value in profile.characteristics
                            ),
                        )
                        for profile in sheet.model_profiles
                    ),
                )
                for sheet in _compact_intercessor_catalog(config.army_catalog).datasheets
            ),
        ),
    )
    armies = mustered_armies(config)
    radius_by_id: dict[str, float] = {}
    y_by_id: dict[str, float] = {}
    for army in armies:
        for unit in army.units:
            for model in unit.own_models:
                shape = model.geometry.base_shape()
                assert isinstance(shape, CircularBase)
                radius_by_id[model.model_instance_id] = shape.radius
                y_by_id[model.model_instance_id] = (
                    30 if model.model_profile_id == "core-character-leader" and attached else 28
                )
    radii = tuple(
        max(
            radius_by_id[model.model_instance_id]
            for unit in army.units
            for model in unit.own_models
        )
        for army in armies
    )
    center_a = 10.0
    separation = config.ruleset_descriptor.engagement_policy.horizontal_inches + 0.5
    center_b = center_a + sum(radii) + separation
    boundary = center_a + radii[0] + separation / 2
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        terrain_features=(),
        battlefield_layout_id=None,
        deployment_map_id="witness:adjacent-zones",
        terrain_layout_id="witness:empty-terrain",
        deployment_zones=(
            DeploymentZone.rectangle("A", "player-a", min_x=0, min_y=0, max_x=boundary, max_y=44),
            DeploymentZone.rectangle("B", "player-b", min_x=boundary, min_y=0, max_x=60, max_y=44),
        ),
    )
    config = replace(
        config,
        mission_setup=mission,
        turn_order=(enemy, player),
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    session = LocalGameSession()
    session.start(config)
    charged = False
    for index in range(150):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        kind = request.decision_type
        if kind == "submit_deployment_placement":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"fall-back:deploy:{index}",
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, owner, _model: Pose.at(
                        center_a if owner == "player-a" else center_b,
                        y_by_id[_model],
                    ),
                ),
            )
        elif kind == "select_charging_unit" and request.actor_id == enemy and not charged:
            choice = next(
                x.option_id
                for x in request.options
                if not x.option_id.startswith(("complete_", "end_", "decline"))
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=choice,
                result_id=f"fall-back:charge:{index}",
            )
        elif kind == "select_charge_targets":
            choice = next(
                x.option_id
                for x in request.options
                if isinstance(x.payload, dict) and x.payload.get("target_ids")
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=choice,
                result_id=f"fall-back:targets:{index}",
            )
        elif kind == "submit_movement_proposal" and request.actor_id == enemy and not charged:
            context = MovementProposalRequest.from_decision_request_payload(request.payload)
            assert context.context is not None
            target_selection = cast(dict[str, JsonValue], context.context["target_selection"])
            targets = cast(list[str], target_selection["target_ids"])
            models = public_models(session, enemy)
            positions = {
                key: pose["position"]
                for key, row in models.items()
                if (pose := row["pose"]) is not None
            }
            state = session.lifecycle.state
            assert state is not None
            movers = rules_unit_view_by_id(
                state=state, unit_instance_id=context.unit_instance_id
            ).alive_models()
            defenders = rules_unit_view_by_id(
                state=state, unit_instance_id=targets[0]
            ).alive_models()
            paths: list[ModelPath] = []
            for mover in movers:
                own = models[mover.model_instance_id]
                assert own["pose"] is not None
                p = own["pose"]["position"]
                defender = min(
                    defenders,
                    key=lambda model: abs(
                        positions[model.model_instance_id]["y_inches"] - p["y_inches"]
                    ),
                )
                target = models[defender.model_instance_id]
                assert target["pose"] is not None
                t = target["pose"]["position"]
                radius_a = mover.geometry.base_shape()
                radius_b = defender.geometry.base_shape()
                assert isinstance(radius_a, CircularBase)
                assert isinstance(radius_b, CircularBase)
                sign = 1 if t["x_inches"] > p["x_inches"] else -1
                paths.append(
                    (
                        mover.model_instance_id,
                        (
                            Pose.at(p["x_inches"], p["y_inches"]),
                            Pose.at(
                                t["x_inches"] - sign * (radius_a.radius + radius_b.radius + 1e-7),
                                t["y_inches"],
                            ),
                        ),
                    )
                )
            witness = PathWitness.for_paths(tuple(paths))
            proposal = ChargeMoveProposal(
                proposal_request_id=context.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=context.unit_instance_id,
                movement_phase_action="charge_move",
                movement_mode=MovementMode.CHARGE,
                charge_target_unit_instance_ids=tuple(targets),
                witness=witness,
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"fall-back:charge-move:{index}",
                payload=validate_json_value(proposal.to_payload()),
            )
            charged = status.status_kind is not LifecycleStatusKind.INVALID
        elif kind == "select_movement_unit" and request.actor_id == player and charged:
            choice = next(
                x.option_id
                for x in request.options
                if not x.option_id.startswith(("complete_", "end_", "decline"))
            )
            status = session.submit_option(
                request_id=request.request_id, option_id=choice, result_id=f"fall-back:unit:{index}"
            )
        elif kind == "select_movement_action" and request.actor_id == player and charged:
            choice = next(
                x.option_id
                for x in request.options
                if isinstance(x.payload, dict)
                and x.payload.get("movement_phase_action") == "fall_back"
                and x.payload.get("fall_back_mode") == "ordered_retreat"
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=choice,
                result_id=f"fall-back:action:{index}",
            )
        elif (
            kind == "submit_movement_proposal"
            and request.actor_id == player
            and charged
            and MovementProposalRequest.from_decision_request_payload(
                request.payload
            ).proposal_kind.value
            == "fall_back"
        ):
            return session, request
        elif kind == "submit_movement_proposal" and charged:
            context = MovementProposalRequest.from_decision_request_payload(request.payload)
            assert context.context is not None
            assert context.movement_phase_action is not None
            if context.proposal_kind.value == "consolidate":
                submit_fixture_request(session, request)
                continue
            assert context.proposal_kind.value == "pile_in"
            fight_targets = tuple(
                cast(list[str], context.context["legal_target_unit_instance_ids"])
            )
            fight_proposal = FightMovementProposal(
                proposal_request_id=context.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=context.unit_instance_id,
                movement_phase_action=context.movement_phase_action,
                movement_mode=MovementMode.PILE_IN,
                pile_in_target_unit_instance_ids=fight_targets,
                witness=public_movement_proposal(session, request, dx=0).witness,
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"fall-back:pile-in:{index}",
                payload=validate_json_value(fight_proposal.to_payload()),
            )
        elif kind == "submit_melee_declaration":
            submit_fixture_request(session, request)
            continue
        else:
            quiet_choice(session, request)
            continue
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    else:
        raise AssertionError("Native Fall Back was not reached")
