"""Canonical phase-end Overwatch sessions for behavior and timing evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _clear_terrain, _replace_unit_poses
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfile, WeaponKeyword
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.move_completion_triggers import record_move_completion_event
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import MovementPhaseState
from warhammer40k_core.engine.stratagems import (
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
)
from warhammer40k_core.geometry.pose import Pose

SHOOTER = "army-alpha:shooter"
ENEMIES = ("army-beta:enemy", "army-beta:enemy-2")


def overwatch_session(
    *,
    moved: bool = False,
    cp: int = 1,
    shooter_models: int = 1,
    weapon_range: int = 24,
    attacks: int = 2,
    attached: bool = False,
    indirect: bool = False,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        range_profile=RangeProfile.distance(weapon_range),
                        attack_profile=AttackProfile.fixed(attacks),
                        keywords=tuple(
                            dict.fromkeys(
                                (
                                    *profile.keywords,
                                    *((WeaponKeyword.INDIRECT_FIRE,) if indirect else ()),
                                )
                            )
                        ),
                    )
                    if profile.range_profile.distance_inches is not None
                    else profile
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    lifecycle, _ = _shooting_lifecycle(
        alpha_unit_ids=("shooter", "leader") if attached else ("shooter",),
        game_id="order45-overwatch",
        alpha_unit_specs=(
            ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", shooter_models),
        )
        + (("leader", "core-character-leader", "core-character-leader", 1),) * attached,
        alpha_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="shooter"
            ),
        )
        if attached
        else (),
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="enemy-leader", bodyguard_unit_selection_id="enemy"
            ),
        )
        if attached
        else (),
        enemy_unit_specs=tuple(
            (key, "core-intercessor-like-infantry", "core-intercessor-like", 1)
            for key in ("enemy", "enemy-2")
        )
        + (("enemy-leader", "core-character-leader", "core-character-leader", 1),) * attached,
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    state.shooting_phase_state = None
    _clear_terrain(state)
    for unit_id, pose in (
        (SHOOTER, Pose.at(10, 10)),
        (ENEMIES[0], Pose.at(20, 10)),
        (ENEMIES[1], Pose.at(20, 16)),
    ):
        _replace_unit_poses(
            state,
            unit_instance_id=unit_id,
            poses=(
                tuple(Pose.at(10 + index * 2, 10) for index in range(shooter_models))
                if unit_id == SHOOTER
                else (pose,)
            ),
        )
    if attached:
        for unit_id, pose in (
            ("army-alpha:leader", Pose.at(10, 12)),
            ("army-beta:enemy-leader", Pose.at(20, 12)),
        ):
            _replace_unit_poses(state, unit_instance_id=unit_id, poses=(pose,))
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    if cp:
        state.gain_command_points(
            player_id="player-a",
            amount=cp,
            source_id="order45:cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-b",
        move_units_completed=True,
        selected_unit_ids=(ENEMIES[0],) if moved else (),
        moved_unit_ids=(ENEMIES[0],) if moved else (),
    )
    if moved:
        record_move_completion_event(
            state=state,
            decisions=lifecycle.decision_controller,
            event_type="movement_activation_completed",
            payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": "player-b",
                "phase": "movement",
                "unit_instance_id": ENEMIES[0],
                "movement_phase_action": "normal_move",
                "phase_body_status": "activation_complete",
            },
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))


def pending_overwatch(session: LocalGameSession) -> DecisionRequest:
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "submit_stratagem_target_proposal", request
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, object], request.payload["proposal_request"])
    assert (
        StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, proposal)
        ).stratagem_id
        == "fire-overwatch"
    )
    return request


def choose_shooter(session: LocalGameSession, request: DecisionRequest) -> LifecycleStatus:
    proposal = shooter_proposal(request)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order45:choose-shooter",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )


def shooter_proposal(request: DecisionRequest) -> StratagemTargetProposal:
    assert isinstance(request.payload, dict)
    return StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, request.payload["proposal_request"])
    ).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=SHOOTER,
        )
    )


def choose_enemy(
    session: LocalGameSession, request: DecisionRequest, enemy: str
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order45:choose-enemy",
        payload=validate_json_value(
            _proposal_from_request(request=request, target_unit_id=enemy).to_payload()
        ),
    )


def finish_overwatch(session: LocalGameSession, status: LifecycleStatus) -> LifecycleStatus:
    for index in range(100):
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        state = session.lifecycle.state
        assert state is not None
        if state.out_of_phase_shooting_state is None:
            return status
        request = status.decision_request
        if request is None:
            status = session.advance_until_decision_or_terminal()
            continue
        option = next((o for o in request.options if "decline" in o.option_id), request.options[0])
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id=f"order45:finish-{index}",
        )
    raise AssertionError("Overwatch did not complete.")


def decline_overwatch(session: LocalGameSession, request: DecisionRequest) -> LifecycleStatus:
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    assert request.decision_type == "submit_stratagem_target_proposal"
    assert isinstance(request.payload, dict)
    proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, request.payload["proposal_request"])
    )
    assert proposal.stratagem_id == "fire-overwatch"
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"order45:decline:{request.request_id}",
        payload=stratagem_decline_payload(),
    )
