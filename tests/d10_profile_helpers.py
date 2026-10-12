"""Predeclared, admitted physical equipment for the scoped profile repair."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.d09_heavy_helpers import decline_native_windows, reach_second_player_movement
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _proposal_from_declarations,
    _shooting_lifecycle,
)
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetWargearOption
from warhammer40k_core.core.weapon_profiles import AttackProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.transports import FiringDeckSelection, FiringDeckWeaponSelection
from warhammer40k_core.engine.weapon_declaration import (
    AvailableWeaponPayload,
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pose import Pose


def profile_catalog(*, copies: int = 1) -> ArmyCatalog:
    catalog = _canonical_catalog()
    wargear = tuple(
        replace(
            item,
            weapon_profiles=(
                replace(item.weapon_profiles[0], attack_profile=AttackProfile.fixed(1)),
                replace(
                    item.weapon_profiles[0],
                    profile_id=item.weapon_profiles[0].profile_id + ":d10-alternate",
                    attack_profile=AttackProfile.fixed(2),
                ),
            ),
        )
        if item.wargear_id in {"core-bolt-rifle", "core-leader-bolt-pistol"}
        else item
        for item in catalog.wargear
    )
    catalog = replace(catalog, wargear=wargear)
    if copies == 2:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    wargear_options=(
                        *sheet.wargear_options,
                        DatasheetWargearOption(
                            option_id=sheet.datasheet_id + ":d10-second-rifle",
                            model_profile_id=sheet.model_profiles[0].model_profile_id,
                            default_wargear_ids=("core-bolt-rifle",),
                            allowed_wargear_ids=("core-bolt-rifle",),
                            min_selections=1,
                            max_selections=1,
                        ),
                    ),
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    else:
        assert copies == 1
    return replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                wargear_options=(
                    *sheet.wargear_options,
                    DatasheetWargearOption(
                        option_id=sheet.datasheet_id + ":d10-leader-rifle",
                        model_profile_id=sheet.model_profiles[0].model_profile_id,
                        default_wargear_ids=("core-bolt-rifle",),
                        allowed_wargear_ids=("core-bolt-rifle",),
                        min_selections=1,
                        max_selections=1,
                    ),
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in catalog.datasheets
        ),
    )


def profile_session(
    *, copies: int = 1, models: int = 1, attached: bool = False, firing_deck: bool = False
) -> LocalGameSession:
    catalog = profile_catalog(copies=copies)
    if attached:
        lifecycle, _ = charge_lifecycle(
            alpha_unit_ids=("shooter", "leader"),
            alpha_attached_unit_ids=("shooter", "leader"),
            alpha_origins={"shooter": Pose.at(10, 20), "leader": Pose.at(10, 21.8)},
            enemy_model_poses=compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
            game_id="d10-attached-profiles",
            catalog=catalog,
        )
        assert lifecycle.state is not None
        lifecycle.state.battle_phase_index = lifecycle.state.battle_phase_sequence.index(
            BattlePhase.SHOOTING
        )
    else:
        lifecycle, _ = _shooting_lifecycle(
            alpha_unit_ids=("transport-1", "shooter") if firing_deck else ("shooter",),
            alpha_datasheets={
                "shooter": ("core-intercessor-like-infantry", "core-intercessor-like", models),
                "transport-1": ("core-transport", "core-transport", 1),
            },
            embarked_unit_ids=("shooter",) if firing_deck else (),
            enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", 2),
            catalog=_compact_intercessor_catalog(catalog),
            game_id=f"d10-profiles-{copies}-{models}-{firing_deck}",
        )
    # Construction and the analytical battle root are fixed before the first
    # facade request. All later state, history, equipment and dice are engine-owned.
    # The legacy builder records roster fixtures after start(). Resolve the
    # standard runtime content bundle at the analytical root, before facade use.
    return LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))


def declaration_request(
    session: LocalGameSession, *, player: str = "player-a", firing_deck: bool = False
) -> DecisionRequest:
    if player == "player-b":
        reach_second_player_movement(session)
        for _ in range(40):
            request = decline_native_windows(session)
            state = session.lifecycle.state
            assert state is not None
            if state.current_battle_phase is BattlePhase.SHOOTING:
                break
            options = [
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or option.option_id == "remain_stationary"
                or "decline" in option.option_id
            ]
            if not options:
                assert request.decision_type == "select_movement_unit", request
                options = list(request.options)
            option = options[0]
            status = session.submit_option(
                request_id=request.request_id,
                result_id=request.request_id + ":d10-skip",
                option_id=option.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            raise AssertionError("D10 native continuation did not reach second Shooting.")
    request = decline_native_windows(session)
    assert request.decision_type == "select_shooting_unit", request
    component = (
        ("army-alpha:transport-1" if firing_deck else "army-alpha:shooter")
        if player == "player-a"
        else "army-beta:enemy"
    )
    state = session.lifecycle.state
    assert state is not None
    unit_id = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions), unit_instance_id=component
    ).unit_instance_id
    status = session.submit_option(
        request_id=request.request_id, result_id=request.request_id + ":d10-unit", option_id=unit_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    request = decline_native_windows(session)
    assert request.decision_type == "select_shooting_type", request
    status = session.submit_option(
        request_id=request.request_id,
        result_id=request.request_id + ":d10-type",
        option_id="normal",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    request = decline_native_windows(session)
    assert request.decision_type == "submit_shooting_declaration", request
    return request


def advertised_weapons(request: DecisionRequest) -> list[AvailableWeaponPayload]:
    payload = cast(dict[str, JsonValue], request.payload)
    proposal = cast(dict[str, JsonValue], payload["proposal_request"])
    return cast(list[AvailableWeaponPayload], proposal["available_weapons"])


def profile_proposal(
    request: DecisionRequest, weapons: list[AvailableWeaponPayload], *, targetless: bool = False
) -> ShootingDeclarationProposal:
    payload = cast(dict[str, JsonValue], request.payload)
    context = cast(dict[str, JsonValue], payload["proposal_request"])
    target = (
        "army-beta:enemy" if context["active_player_id"] == "player-a" else "army-alpha:shooter"
    )
    declarations = tuple(
        WeaponDeclaration(
            weapon_instance_id=weapon["weapon_instance_id"],
            attacker_model_instance_id=weapon["model_instance_id"],
            wargear_id=weapon["wargear_id"],
            weapon_profile_id=weapon["weapon_profile_id"],
            target_unit_instance_id=None if targetless else target,
            shooting_type=ShootingType.NORMAL,
            firing_deck_source_unit_instance_id=weapon.get("firing_deck_source_unit_instance_id"),
            firing_deck_source_model_instance_id=weapon.get("firing_deck_source_model_instance_id"),
        )
        for weapon in weapons
    )
    proposal = _proposal_from_declarations(request=request, declarations=declarations)
    borrowed = [weapon for weapon in weapons if "firing_deck_source_unit_instance_id" in weapon]
    if borrowed:
        from warhammer40k_core.core.weapon_profiles import WeaponProfile

        selections: list[FiringDeckWeaponSelection] = []
        for weapon in borrowed:
            source_model_id = weapon.get("firing_deck_source_model_instance_id")
            assert source_model_id is not None
            selections.append(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=weapon["firing_deck_source_unit_instance_id"],
                    model_instance_id=source_model_id,
                    weapon_instance_id=weapon["weapon_instance_id"],
                    wargear_id=weapon["wargear_id"],
                    weapon_profile=WeaponProfile.from_payload(weapon["weapon_profile"]),
                )
            )
        proposal = replace(
            proposal,
            firing_deck_selection=FiringDeckSelection(
                player_id=proposal.player_id,
                battle_round=proposal.battle_round,
                transport_unit_instance_id=proposal.unit_instance_id,
                firing_deck_value=cast(int, context["firing_deck_value"]),
                weapon_selections=tuple(selections),
                already_shot_unit_instance_ids=tuple(
                    cast(list[str], context["firing_deck_already_shot_unit_instance_ids"])
                ),
            ),
        )
    return proposal


def submit_profile(
    session: LocalGameSession, request: DecisionRequest, proposal: ShootingDeclarationProposal
) -> None:
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=request.request_id + ":d10-valid",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def finish_profile_attack(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    for _ in range(60):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "attack_sequence_completed" for event in events):
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("D10 native attacks did not complete.")
    accepted = next(
        event for event in events if event.event_type == "shooting_declaration_accepted"
    )
    assert isinstance(accepted.payload, dict)
    return cast(list[dict[str, JsonValue]], accepted.payload["attack_pools"])


def profile_checkpoint(session: LocalGameSession) -> tuple[LocalGameSession, LocalGameSession]:
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
                    principal_id=f"d10-{role.value}-{player}", role=role, player_id=player
                ).bind_to_session(player_ids=("player-a", "player-b"))
                assert clone.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert clone.events_since_for_context(
                    EventStreamCursor(), viewer=viewer
                ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="d10-profile")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    return restored, fork
