"""Real source-permission fixture and ordinary disembark submissions."""

from __future__ import annotations

from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session
from tests.order60_emergency_disembark_helpers import emergency_disembark_unit_placement
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, UnitPlacement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.transport_embark_context import NoMovementEmbarkContext
from warhammer40k_core.engine.transport_source_embark import no_movement_embark_permission_effect
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus

SOURCE_ID = "faq:c2df3e97-f21e-4fc9-943e-37072c08c10e"


def source_embark_session(*, allow_after_disembark: bool = True) -> LocalGameSession:
    session = disembark_session()
    state = session.lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        no_movement_embark_permission_effect(
            context=NoMovementEmbarkContext(
                source_rule_id=SOURCE_ID,
                permission_effect_id="order114:permission",
                occasion_id="order114:source-occasion",
                battle_round=state.battle_round,
                turn_player_id="player-a",
                phase=BattlePhase.MOVEMENT,
                unit_instance_id=PASSENGER_ID,
            ),
            owner_player_id="player-a",
            allow_after_disembark=allow_after_disembark,
        )
    )
    return session


def disembark_at_transport(
    session: LocalGameSession,
    *,
    unit_instance_id: str = PASSENGER_ID,
) -> None:
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order114:unit",
        option_id=unit_instance_id,
    )
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="order114:disembark",
        option_id="disembark",
    )
    assert status.decision_request is not None
    request = status.decision_request
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    placement: UnitPlacement | RulesUnitPlacement
    if unit_instance_id == PASSENGER_ID:
        placement = emergency_disembark_unit_placement(
            unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
            army_id="army-alpha",
            player_id="player-a",
            center_x=10,
            center_y=10,
        )
    else:
        from tests.order60_emergency_disembark_helpers import emergency_disembark_contact_poses
        from warhammer40k_core.engine.battlefield_state import ModelPlacement
        from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

        view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
        models = view.alive_models()
        poses = dict(
            zip(
                (model.model_instance_id for model in models),
                emergency_disembark_contact_poses(
                    models, center_x=10, center_y=10, step_degrees=60
                ),
                strict=True,
            )
        )
        placement = RulesUnitPlacement(
            rules_unit_instance_id=view.unit_instance_id,
            component_unit_placements=tuple(
                UnitPlacement(
                    army_id="army-alpha",
                    player_id="player-a",
                    unit_instance_id=component.unit.unit_instance_id,
                    model_placements=tuple(
                        ModelPlacement(
                            army_id="army-alpha",
                            player_id="player-a",
                            unit_instance_id=component.unit.unit_instance_id,
                            model_instance_id=model.model_instance_id,
                            pose=poses[model.model_instance_id],
                        )
                        for model in component.unit.alive_own_models()
                    ),
                )
                for component in view.living_components
            ),
        )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order114:place",
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=unit_instance_id,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=placement if isinstance(placement, UnitPlacement) else None,
                attempted_rules_unit_placement=(
                    placement if isinstance(placement, RulesUnitPlacement) else None
                ),
                transport_unit_instance_id=TRANSPORT_ID,
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def attached_source_embark_session() -> tuple[LocalGameSession, str]:
    from tests.core_stratagem_helpers import (
        _clear_terrain,
        _complete_current_command_for_fixture,  # pyright: ignore[reportPrivateUsage]
        _replace_unit_poses,
    )
    from tests.support.ability_presence_fixtures import ability_presence_fixture
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    config, state, decisions = ability_presence_fixture(embarked=True, attached=True)
    _clear_terrain(state)
    _replace_unit_poses(state, unit_instance_id=TRANSPORT_ID, poses=(Pose.at(10, 10),))
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    lifecycle = _complete_current_command_for_fixture(lifecycle)
    runtime_state = lifecycle.state
    assert runtime_state is not None
    state = runtime_state
    unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id="army-alpha:leader"
    ).unit_instance_id
    state.record_persisting_effect(
        no_movement_embark_permission_effect(
            context=NoMovementEmbarkContext(
                source_rule_id=SOURCE_ID,
                permission_effect_id="order114:attached-permission",
                occasion_id="order114:attached-occasion",
                battle_round=state.battle_round,
                turn_player_id="player-a",
                phase=BattlePhase.MOVEMENT,
                unit_instance_id=unit_id,
            ),
            owner_player_id="player-a",
            allow_after_disembark=True,
        )
    )
    return LocalGameSession(lifecycle), unit_id
