"""D12 admitted analytical Fight roots and shared public decision consumers.

Mustered Core Leader/Support membership and physical keywords remain canonical.
Optional analytical equipment is declared in the catalog before muster/hydration.
All choices after the validated root use LocalGameSession, real dice and history.
This bounded Core scene makes no faction, provider or complete-game claim.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.fight_completion_helpers import submit_completion_request
from tests.order135_counteroffensive_helpers import proposal_from_native_request
from tests.phase15c_fight_order_helpers import fight_config, mustered_armies, unit_placement_at
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetWargearOption
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import StratagemTargetBinding, StratagemTargetProposal
from warhammer40k_core.geometry.pose import Pose


def epic_scene(
    *,
    player: str = "player-a",
    attached: bool = True,
    support: bool = False,
    armed_bodyguard: bool = False,
    dead: str | None = None,
    cp: int = 2,
    noncharacter: bool = False,
    pause_attacks: bool = False,
) -> LocalGameSession:
    assert player in {"player-a", "player-b"}
    assert dead in {None, "leader", "bodyguard"}
    assert not support or attached
    if dead is not None:
        from tests.epic_challenge_split_helpers import native_split_epic_request

        session, _ = native_split_epic_request(player=player, split=False, casualty=dead)
        return session
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if pause_attacks:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=tuple(
                        replace(
                            profile,
                            keywords=(
                                *profile.keywords,
                                WeaponKeyword.TWIN_LINKED,
                            ),
                            source_ids=(*profile.source_ids, "d12:analytical-attack-pause"),
                        )
                        for profile in item.weapon_profiles
                    ),
                )
                if item.wargear_id == "core-leader-blade"
                else item
                for item in catalog.wargear
            ),
        )
    if armed_bodyguard or noncharacter:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    wargear_options=(
                        *sheet.wargear_options,
                        DatasheetWargearOption(
                            option_id="d12:analytical-bodyguard-blade",
                            model_profile_id="core-intercessor-like",
                            default_wargear_ids=("core-leader-blade",),
                            allowed_wargear_ids=("core-leader-blade",),
                            min_selections=1,
                            max_selections=1,
                            source_ids=("d12:analytical-equipment",),
                        ),
                    ),
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    subjects = {"leader": ("core-character-leader", "core-character-leader", 1)}
    if attached or noncharacter:
        subjects["bodyguard"] = (
            "core-intercessor-like-infantry",
            "core-intercessor-like",
            5,
        )
    if noncharacter:
        del subjects["leader"]
    if support:
        subjects["support"] = ("core-character-support", "core-character-support", 1)
    subjects["foreign"] = ("core-character-leader", "core-character-leader", 1)
    targets = {"enemy": ("core-character-leader", "core-character-leader", 1)}
    attachments = (
        tuple(
            AttachmentDeclaration(name, "bodyguard")
            for name in subjects
            if name in {"leader", "support"}
        )
        if attached and not noncharacter
        else ()
    )
    config = fight_config(
        game_id=f"d12-epic:{player}:{attached}:{support}:{armed_bodyguard}:{dead}:{cp}:{noncharacter}:{pause_attacks}",
        alpha_unit_ids=tuple(subjects) if player == "player-a" else tuple(targets),
        enemy_unit_ids=tuple(targets) if player == "player-a" else tuple(subjects),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs=subjects if player == "player-a" else targets,
        enemy_unit_specs=targets if player == "player-a" else subjects,
        catalog=catalog,
        alpha_attachment_declarations=attachments if player == "player-a" else (),
        enemy_attachment_declarations=attachments if player == "player-b" else (),
    )
    other = "player-b" if player == "player-a" else "player-a"
    config = replace(config, turn_order=(player, other))
    armies = mustered_armies(config)
    mission = config.mission_setup
    assert mission is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=config.game_id + ":battlefield",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    )
    battlefield = scenario.battlefield_state
    for army in armies:
        for unit in army.units:
            key = unit.unit_instance_id.split(":")[-1]
            poses = (
                tuple(Pose.at(10 + (i % 3) * 1.6, 20 + (i // 3) * 1.6) for i in range(5))
                if key == "bodyguard"
                else (Pose.at(13.2, 21.6),)
                if key == "leader" and attached
                else (Pose.at(13.2, 23.2),)
                if key == "support"
                else (Pose.at(40, 20),)
                if key == "foreign"
                else (Pose.at(14.8 if attached or noncharacter else 11.8, 21.6),)
                if key == "enemy"
                else (Pose.at(10, 21.3),)
            )
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=poses)
            )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.active_player_id = player
    for owner in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=owner,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    if cp:
        state.gain_command_points(
            player_id=player,
            amount=cp,
            source_id="d12:initial-cp",
            source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
            cap_exempt=True,
        )
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return LocalGameSession(GameLifecycle.from_payload(payload))


def epic_unit_from_state(state: GameState, *, player: str) -> RulesUnitView:
    army = next(army for army in state.army_definitions if army.player_id == player)
    unit = next(unit for unit in army.units if unit.unit_instance_id.endswith(":leader"))
    return rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)


def epic_request(session: LocalGameSession, *, player: str) -> DecisionRequest:
    for _ in range(60):
        request = pending_request(session)
        if request.decision_type == "submit_stratagem_target_proposal":
            proposal = proposal_from_native_request(request)
            if proposal.stratagem_id == "epic-challenge" and request.actor_id == player:
                return request
        submit_completion_request(session)
    raise AssertionError("Native selected friendly CHARACTER did not offer Epic Challenge.")


def epic_proposal(request: DecisionRequest, *, model_id: JsonValue) -> StratagemTargetProposal:
    proposal = proposal_from_native_request(request)
    trigger = proposal.context.trigger_payload
    assert isinstance(trigger, dict)
    unit_id = trigger["selected_unit_instance_id"]
    assert isinstance(unit_id, str)
    return proposal.with_binding(
        StratagemTargetBinding(
            target_kind=proposal.target_spec.target_kind,
            target_player_id=request.actor_id,
            target_unit_instance_id=unit_id,
        ),
        effect_selection={"character_model_instance_id": model_id},
    )


def submit_epic(
    session: LocalGameSession, request: DecisionRequest, proposal: StratagemTargetProposal
) -> None:
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=request.request_id + ":d12-legal",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def submit_all_melee(session: LocalGameSession, request: DecisionRequest) -> None:
    melee = MeleeDeclarationProposalRequest.from_decision_request(request)
    declarations: list[JsonValue] = []
    for row in melee.available_weapons:
        assert isinstance(row, dict)
        targets = row["engaged_target_unit_instance_ids"]
        assert isinstance(targets, list)
        if targets:
            declarations.append(
                {
                    "attacker_model_instance_id": row["model_instance_id"],
                    "weapon_instance_id": row["weapon_instance_id"],
                    "wargear_id": row["wargear_id"],
                    "weapon_profile_id": row["weapon_profile_id"],
                    "target_allocations": [{"target_unit_instance_id": targets[0]}],
                }
            )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=request.request_id + ":d12-melee",
        payload={
            "proposal_request_id": melee.request_id,
            "proposal_kind": melee.proposal_kind,
            "player_id": melee.actor_id,
            "battle_round": melee.battle_round,
            "unit_instance_id": melee.unit_instance_id,
            "source_decision_request_id": melee.source_decision_request_id,
            "source_decision_result_id": melee.source_decision_result_id,
            "declarations": declarations,
        },
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def finish_epic_fight(session: LocalGameSession, *, unit_id: str) -> None:
    for _ in range(90):
        events = session.lifecycle.decision_controller.event_log.records
        if any(
            event.event_type == "fight_activation_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("unit_instance_id") == unit_id
            for event in events
        ):
            return
        request = pending_request(session)
        if request.decision_type == "submit_melee_declaration":
            submit_all_melee(session, request)
        elif request.decision_type == "submit_stratagem_target_proposal":
            submit_completion_request(session)
        else:
            submit_fixture_request(session, request)
    raise AssertionError("D12 selected unit did not complete actual native melee attacks.")


def epic_checkpoint(session: LocalGameSession) -> tuple[LocalGameSession, LocalGameSession]:
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    assert restored.to_persistence_payload() == fork.to_persistence_payload() == checkpoint
    assert restored.lifecycle is not session.lifecycle
    assert fork.lifecycle is not session.lifecycle
    assert fork.lifecycle.state is not session.lifecycle.state
    for clone in (restored, fork):
        for role in PrincipalRole:
            players = (
                ("player-a", "player-b")
                if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
                else (None,)
            )
            for player in players:
                viewer = AuthenticatedPrincipal(
                    principal_id=f"d12:{role.value}:{player}", role=role, player_id=player
                ).bind_to_session(player_ids=("player-a", "player-b"))
                assert clone.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert clone.events_since_for_context(
                    EventStreamCursor(), viewer=viewer
                ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="d12:epic")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    return restored, fork
