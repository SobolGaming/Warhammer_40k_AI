"""Real facade workloads for Order 33 outcomes and reproducible slice measurement."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase13b_shooting_declaration_helpers import (
    _blocking_ruin,
    _canonical_catalog,
    _compact_intercessor_catalog,
    _config,
    _configure_shooting_battle_state,
    _grant_command_reroll_cp,
    _mustered_armies,
    _proposal_from_request,
    _scenario_with_unit_pose,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.geometry.pose import Pose

INDIRECT_PROFILE = "order33:indirect"
ORDINARY_PROFILE = "core-bolt-rifle:standard"
SHOOTER = "army-alpha:intercessor-1"
TARGET = "army-beta:enemy"


def indirect_session(
    *,
    visible: bool = True,
    stationary: bool = True,
    observer: bool = False,
    attacks: int = 1,
    hit_modifier: int = 0,
    rerolls: bool = False,
    game_id: str = "order33-shooting",
    model_count: int = 2,
    ballistic_skill: int = 2,
    shooter_keyword: str | None = None,
    engager_distance: float | None = None,
    engager_attached: bool = False,
    assault: bool = False,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    if shooter_keyword is not None:
        assert shooter_keyword in {"VEHICLE", "MONSTER"}
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    row,
                    keywords=replace(
                        row.keywords, keywords=(*row.keywords.keywords, shooter_keyword)
                    ),
                )
                if row.datasheet_id == "core-intercessor-like-infantry"
                else row
                for row in catalog.datasheets
            ),
        )
    wargear_rows: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id != "core-bolt-rifle":
            wargear_rows.append(wargear)
            continue
        ordinary = replace(
            wargear.weapon_profiles[0],
            keywords=(WeaponKeyword.ASSAULT,) if assault else (),
            abilities=(),
            attack_profile=AttackProfile.fixed(attacks),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, ballistic_skill),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
        )
        indirect = replace(
            ordinary,
            profile_id=INDIRECT_PROFILE,
            name="Indirect fixture rifle",
            keywords=(*ordinary.keywords, WeaponKeyword.INDIRECT_FIRE),
        )
        wargear_rows.append(replace(wargear, weapon_profiles=(ordinary, indirect)))
    catalog = replace(catalog, wargear=tuple(wargear_rows))
    alpha_ids = ("intercessor-1", "observer") if observer else ("intercessor-1",)
    config = _config(
        alpha_unit_ids=alpha_ids,
        alpha_datasheets=None,
        alpha_unit_specs=tuple(
            (key, "core-intercessor-like-infantry", "core-intercessor-like", model_count)
            for key in alpha_ids
        ),
        enemy_datasheet=None,
        enemy_unit_specs=(
            ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            *(
                (("engager", "core-intercessor-like-infantry", "core-intercessor-like", 1),)
                if engager_distance is not None
                else ()
            ),
            *(
                (("engager-leader", "core-character-leader", "core-character-leader", 1),)
                if engager_attached
                else ()
            ),
        ),
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="engager-leader", bodyguard_unit_selection_id="engager"
            ),
        )
        if engager_attached
        else (),
        game_id=game_id,
        catalog=catalog,
    )
    assert config.mission_setup is not None
    config = replace(
        config,
        mission_setup=replace(
            config.mission_setup, terrain_features=() if visible else (_blocking_ruin(),)
        ),
    )
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    assert config.mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order33-battlefield",
        armies=armies,
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
    )
    for army in armies:
        for unit in army.units:
            key = unit.unit_instance_id.split(":", 1)[1]
            x, y = (
                (10.0, 45.0)
                if key == "engager" and engager_attached
                else (10.0, 35.0 + engager_distance)
                if key in {"engager", "engager-leader"} and engager_distance is not None
                else (30.0, 35.0)
                if key == "enemy"
                else (10.0, 45.0)
                if key == "observer"
                else (10.0, 35.0)
            )
            scenario = _scenario_with_unit_pose(
                scenario=scenario,
                unit=unit,
                army_id=army.army_id,
                player_id=army.player_id,
                poses=tuple(Pose.at(x + index * 1.4, y) for index in range(len(unit.own_models))),
            )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = lifecycle.state
    assert state is not None
    _configure_shooting_battle_state(
        state=state,
        decisions=lifecycle.decision_controller,
        armies=armies,
        battlefield=replace(
            scenario.battlefield_state, terrain_features=config.mission_setup.terrain_features
        ),
        units=units,
        embarked_unit_ids=(),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    session = LocalGameSession(lifecycle=lifecycle)
    if hit_modifier:
        state.record_persisting_effect(
            generic_effect(
                effect_id="order33-hit-modifier",
                owner_player_id="player-a",
                target_unit_instance_ids=(SHOOTER,),
                target_kind="this_unit",
                effect_kind="modify_dice_roll",
                parameters={"roll_type": "hit", "delta": hit_modifier, "attack_role": "attacker"},
            )
        )
    if rerolls:
        _grant_command_reroll_cp(state, player_id="player-a")
        state.record_persisting_effect(
            generic_effect(
                effect_id="order33-hit-reroll",
                owner_player_id="player-a",
                target_unit_instance_ids=(SHOOTER,),
                target_kind="this_unit",
                effect_kind="reroll_permission",
                parameters={"roll_type": "hit", "attack_role": "attacker"},
            )
        )
    complete_movement_before_shooting(session, stationary=stationary, assault=assault)
    return LocalGameSession.from_persistence_payload(session.to_persistence_payload())


def complete_movement_before_shooting(
    session: LocalGameSession, *, stationary: bool, assault: bool = False
) -> None:
    selected_unit_id = ""
    for index in range(30):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if state.current_battle_phase is BattlePhase.SHOOTING:
            assert state.movement_phase_state is None
            return
        result_id = f"order33:movement:{index}"
        if request.decision_type == "select_movement_unit":
            selected_unit_id = request.options[0].option_id
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=selected_unit_id
            )
        elif request.decision_type == "select_movement_action":
            action = (
                "advance"
                if selected_unit_id == SHOOTER and assault
                else "normal_move"
                if selected_unit_id == SHOOTER and not stationary
                else "remain_stationary"
            )
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=action
            )
        elif request.decision_type == "submit_movement_proposal":
            offered = MovementProposalRequest.from_decision_request_payload(request.payload)
            proposal = MovementProposalPayload(
                proposal_request_id=offered.request_id,
                proposal_kind=offered.proposal_kind,
                unit_instance_id=selected_unit_id,
                movement_phase_action="advance" if assault else "normal_move",
                movement_mode="advance" if assault else "normal",
                witness=straight_line_witness_for_unit(
                    session.lifecycle, unit_instance_id=selected_unit_id, dx=0.5
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=validate_json_value(proposal.to_payload()),
            )
        else:
            submit_fixture_request(session, request)
            continue
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("Movement did not finish within the fixture decision budget")


def select_indirect_declaration(
    session: LocalGameSession, mode: ShootingType = ShootingType.INDIRECT
) -> DecisionRequest:
    request = pending_request(session)
    assert request.decision_type == "select_shooting_unit"
    status = session.submit_option(
        request_id=request.request_id, result_id="order33:select-unit", option_id=SHOOTER
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    assert request.decision_type == "select_shooting_type"
    status = session.submit_option(
        request_id=request.request_id, result_id="order33:select-mode", option_id=mode.value
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    assert request.decision_type == "submit_shooting_declaration"
    return request


def submit_indirect_declaration(
    session: LocalGameSession, request: DecisionRequest, *, mixed: bool = False
) -> None:
    proposal = _proposal_from_request(
        request=request, target_unit_id=TARGET, weapon_profile_id=INDIRECT_PROFILE
    )
    if mixed:
        body = cast(dict[str, JsonValue], request.payload)
        offered = cast(dict[str, JsonValue], body["proposal_request"])
        weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
        ordinary = next(
            weapon
            for weapon in weapons
            if weapon["weapon_profile_id"] == ORDINARY_PROFILE
            and weapon["model_instance_id"] != proposal.declarations[0].attacker_model_instance_id
        )
        declaration = replace(
            proposal.declarations[0],
            attacker_model_instance_id=cast(str, ordinary["model_instance_id"]),
            weapon_instance_id=cast(str, ordinary["weapon_instance_id"]),
            weapon_profile_id=ORDINARY_PROFILE,
        )
        proposal = replace(proposal, declarations=(*proposal.declarations, declaration))
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order33:declare",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def complete_indirect_attack(session: LocalGameSession) -> tuple[str, ...]:
    choices: list[str] = []
    for _ in range(300):
        state = session.lifecycle.state
        assert state is not None
        shooting = state.shooting_phase_state
        if state.current_battle_phase is not BattlePhase.SHOOTING:
            return tuple(choices)
        if (
            shooting is not None
            and SHOOTER in shooting.shot_unit_ids
            and shooting.attack_sequence is None
            and shooting.pending_completed_attack_sequence is None
        ):
            return tuple(choices)
        request = pending_request(session)
        choices.append(request.decision_type)
        if request.decision_type == "select_shooting_unit":
            raise AssertionError("Shooting returned to selection without completing the shooter")
        if request.options:
            keep = next(
                (
                    option
                    for option in request.options
                    if "decline" in option.option_id or "keep" in option.option_id
                ),
                request.options[0],
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:order33-choice",
                option_id=keep.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
    raise AssertionError("Order 33 attack did not complete within its finite decision budget")


def shooting_event_payloads(
    session: LocalGameSession, event_type: str
) -> list[dict[str, JsonValue]]:
    return [
        cast(dict[str, JsonValue], event.payload)
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    ]


def assert_indirect_outcomes(
    *,
    visible: bool,
    stationary: bool,
    observer: bool,
    mode: ShootingType,
    modifier: int,
    ballistic_skill: int = 2,
) -> None:
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.weapon_abilities import (
        INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
        INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
        INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    )

    session = indirect_session(
        visible=visible,
        stationary=stationary,
        observer=observer,
        attacks=36,
        hit_modifier=modifier,
        ballistic_skill=ballistic_skill,
    )
    pending_request(session)
    initial = session.lifecycle.to_payload()
    request = select_indirect_declaration(session, mode)
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    assert {cast(str, row["weapon_profile_id"]) for row in weapons} == {
        INDIRECT_PROFILE,
        ORDINARY_PROFILE,
    }
    pending_checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(pending_checkpoint)
    assert restored.to_persistence_payload() == pending_checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    submit_indirect_declaration(session, request, mixed=visible)
    complete_indirect_attack(session)
    pools = cast(
        list[dict[str, JsonValue]],
        shooting_event_payloads(session, "shooting_declaration_accepted")[0]["attack_pools"],
    )
    hits = [
        cast(dict[str, JsonValue], row["payload"])
        for row in shooting_event_payloads(session, "attack_sequence_step")
        if row["step"] == "hit"
    ]
    for pool in pools:
        restricted = mode is ShootingType.INDIRECT and pool["weapon_profile_id"] == INDIRECT_PROFILE
        rules = cast(list[str], pool["targeting_rule_ids"])
        assert (INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in rules) is restricted
        assert (INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in rules) is restricted
        improved = restricted and stationary and (visible or observer)
        assert (INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in rules) is improved
        assert pool["hit_roll_modifier"] == 0
        pool_hits = [hit for hit in hits if hit["weapon_profile_id"] == pool["weapon_profile_id"]]
        assert len(pool_hits) == 36
        assert {1, 3, 4, 5, 6} <= {cast(int, hit["unmodified_roll"]) for hit in pool_hits}
        minimum = (4 if improved else 6) if restricted else 2
        for hit in pool_hits:
            raw = cast(int, hit["unmodified_roll"])
            skill = ballistic_skill + (1 if restricted else 0)
            assert hit["minimum_unmodified_success"] == minimum
            assert hit["target_number"] == skill
            assert hit["modifier"] == modifier
            assert hit["successful"] is (raw == 6 or (raw >= minimum and raw + modifier >= skill))
            roll = cast(dict[str, JsonValue], hit["roll_state"])
            original = cast(dict[str, JsonValue], roll["original_result"])
            spec = cast(dict[str, JsonValue], original["spec"])
            assert (
                INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID
                in cast(list[str], spec["reroll_forbidden_rule_ids"])
            ) is restricted
    artifact = ReplayArtifact.capture(
        artifact_id="order33-matrix",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
