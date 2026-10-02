"""Facade fixtures for selection completion independently of actual melee attacks."""

from __future__ import annotations

import json
from dataclasses import replace

from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.retained_attack_helpers import lethal_retained_attack_catalog
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    MovementMode,
)
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_resolution import CONSOLIDATE_ACTION, FightMovementProposal
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def completion_session(
    *,
    armed: bool,
    retained: bool = False,
    interrupt: bool = False,
    counteroffensive: bool = False,
    no_target: bool = False,
    automatic_hit: bool = False,
    miss: bool = False,
    record_deployment: bool = False,
) -> LocalGameSession:
    catalog = (
        lethal_retained_attack_catalog()
        if retained
        else ArmyCatalog.phase9a_canonical_content_pack()
    )
    original = catalog.datasheet_by_id("core-character-leader")
    subject = replace(
        original,
        datasheet_id="order102-subject",
        wargear_options=tuple(
            option if armed else replace(option, default_wargear_ids=(), min_selections=0)
            for option in original.wargear_options
        ),
    )
    catalog = replace(catalog, datasheets=(*catalog.datasheets, subject))
    if not retained:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=tuple(
                        replace(
                            profile,
                            attack_profile=AttackProfile.fixed(1),
                            keywords=(*profile.keywords, WeaponKeyword.TORRENT)
                            if automatic_hit
                            else profile.keywords,
                            skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 6)
                            if miss and item.wargear_id == "core-leader-blade"
                            else profile.skill,
                        )
                        for profile in item.weapon_profiles
                    ),
                )
                for item in catalog.wargear
            ),
        )
    subject_key = "enemy" if retained else "subject"
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker", "observer") if retained else ("subject",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10, 10),
            "subject": Pose.at(10, 10),
            "enemy": Pose.at(14.2 if no_target else 12, 10),
            "observer": Pose.at(12, 14),
        },
        game_id="order102-retained" if retained else "order102-completion",
        model_count=1,
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        alpha_unit_specs=None
        if retained
        else {"subject": (subject.datasheet_id, "core-character-leader", 1)},
        enemy_unit_specs={"enemy": (subject.datasheet_id, "core-character-leader", 1)}
        if retained
        else None,
        fights_first_unit_keys=("attacker",)
        if retained
        else ()
        if no_target
        else ("subject", "enemy"),
        charge_fights_first_unit_keys=("subject",) if no_target else (),
        fight_interrupt_unit_keys=("enemy",) if interrupt else (),
        record_deployment=record_deployment,
    )
    state = lifecycle.state
    assert state is not None
    if counteroffensive:
        state.gain_command_points(
            player_id="player-b",
            amount=2,
            source_id="order102-cp",
            source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
            cap_exempt=True,
        )
    if retained:
        model_id = units[subject_key].own_models[0].model_instance_id
        state.record_model_destruction_reaction_sources(
            model_instance_id=model_id,
            sources=(
                DestructionReactionSource(
                    source_id="order102-retain",
                    source_rule_id="order102-retain",
                    reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                ),
                DestructionReactionSource(
                    source_id="order102-demise",
                    source_rule_id="order102-demise",
                    reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                    optional=False,
                    payload={
                        "trigger_roll_threshold": 1,
                        "range_inches": 6.0,
                        "mortal_wounds": {"kind": "fixed", "value": 1},
                    },
                ),
            ),
        )
        state.record_model_feel_no_pain_sources(
            model_instance_id=units["observer"].own_models[0].model_instance_id,
            decline_allowed=True,
            sources=(FeelNoPainSource(source_id="order102-cleanup-fnp", threshold=6),),
        )
    return LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))


def engaging_completion_session(*, fight_type: str) -> LocalGameSession:
    """Finish a real Engaging response after an ordinary empty selection."""
    session = completion_session(
        armed=True, no_target=True, automatic_hit=True, record_deployment=True
    )
    for _ in range(40):
        request = pending_request(session)
        if request.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            if move.proposal_kind is ProposalKind.CONSOLIDATE:
                break
        submit_completion_request(session)
    else:
        raise AssertionError("Ordinary empty selection did not reach Consolidation.")
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model = state.battlefield_state.unit_placement_by_id(move.unit_instance_id).model_placements[0]
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order102-engaging",
        payload=validate_json_value(
            FightMovementProposal(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.CONSOLIDATE,
                unit_instance_id=move.unit_instance_id,
                movement_phase_action=CONSOLIDATE_ACTION,
                movement_mode=MovementMode.CONSOLIDATE,
                consolidation_mode=ConsolidationModeKind.ENGAGING,
                consolidate_target_unit_instance_ids=("army-beta:enemy",),
                witness=PathWitness.for_paths(
                    (
                        (
                            model.model_instance_id,
                            (model.pose, Pose.at(model.pose.position.x + 2, model.pose.position.y)),
                        ),
                    )
                ),
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    request = pending_request(session)
    assert request.decision_type == "select_fight_activation", request
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload["fight_type"] == fight_type
    )
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order102-forced-response",
        option_id=option.option_id,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    for _ in range(40):
        if any(
            event.event_type == "forced_fight_activation_queue_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            return session
        submit_completion_request(session)
    raise AssertionError("Engaging response did not resume ordinary play.")


def drive_to_completion(session: LocalGameSession, *, unit_id: str) -> None:
    for _ in range(100):
        if any(
            event.event_type == "fight_activation_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("unit_instance_id") == unit_id
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            return
        submit_completion_request(session)
    raise AssertionError("Fight selection did not complete through the facade.")


def submit_completion_request(session: LocalGameSession) -> None:
    request = pending_request(session)
    if request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:decline",
            payload=stratagem_decline_payload(),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    elif request.decision_type == "select_destruction_reaction":
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:retain",
            option_id="order102-retain",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    else:
        submit_fixture_request(session, request)


def assert_completion_round_trip(session: LocalGameSession) -> LocalGameSession:
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order102")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    return restored
