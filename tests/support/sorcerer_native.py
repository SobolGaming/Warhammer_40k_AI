"""Production catalog, strict MFM roster and public legal setup for Sorcerer tests."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, WarlordSelection
from warhammer40k_core.engine.army_points import calculate_mfm_army_points
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    BattleSize,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    court_of_slaughter_anvanth_2026_08 as source_catalog,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    mfm_2026_07,
)

SORCERER = "000004085"
TORMENTORS = "000004079"


def native_selection(sheet: str, identity: str) -> UnitMusterSelection:
    catalog = source_catalog.catalog_package().army_catalog
    datasheet = catalog.datasheet_by_id(sheet)
    return UnitMusterSelection(
        unit_selection_id=identity,
        datasheet_id=sheet,
        model_profile_selections=tuple(
            ModelProfileSelection(p.model_profile_id, p.min_models) for p in datasheet.composition
        ),
    )


def native_request(
    *,
    player: str,
    bodyguard: str | None = TORMENTORS,
    leader_sheet: str = SORCERER,
    attached: bool = True,
    extra_units: tuple[UnitMusterSelection, ...] = (),
) -> ArmyMusterRequest:
    catalog = source_catalog.catalog_package().army_catalog
    leader = native_selection(leader_sheet, "sorcerer")
    request = ArmyMusterRequest(
        army_id=player,
        player_id=player,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection("emperors-children", ("court-of-the-phoenician",)),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            leader,
            *((native_selection(bodyguard, "bodyguard"),) if bodyguard else ()),
            *extra_units,
        ),
        attachment_declarations=(AttachmentDeclaration("sorcerer", "bodyguard"),)
        if attached and bodyguard is not None
        else (),
        warlord_selection=WarlordSelection(
            unit_selection_id="sorcerer",
            source_id="core:muster-warlord-selection",
            model_profile_id=leader.model_profile_selections[0].model_profile_id,
            model_index=1,
        ),
        roster_legality_required=True,
        battle_size=BattleSize.INCURSION,
    )
    points = calculate_mfm_army_points(
        catalog=catalog, request=request, source_package=mfm_2026_07.source_package()
    )
    return replace(
        request,
        points_source_package_id=mfm_2026_07.SOURCE_PACKAGE_ID,
        unit_points=points.roster_unit_point_values(),
    )


def native_session(
    *,
    seed: str = "sorcerer-native",
    attached: bool = True,
    enemy_attached: bool = True,
    own_bodyguard: str = TORMENTORS,
    second_sorcerer: bool = False,
    enemy_character_only: bool = False,
) -> LocalGameSession:
    package = source_catalog.catalog_package()
    mission = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-3",
        terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-3",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="purge-the-foe",
    )
    config = GameConfig(
        game_id=seed,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
        army_catalog=package.army_catalog,
        army_muster_requests=(
            native_request(
                player="owner",
                attached=attached,
                bodyguard=own_bodyguard,
                extra_units=(native_selection(SORCERER, "second-sorcerer"),)
                if second_sorcerer
                else (),
            ),
            native_request(
                player="opponent",
                attached=enemy_attached,
                bodyguard=None if enemy_character_only else TORMENTORS,
                leader_sheet="000004086" if enemy_character_only else SORCERER,
            ),
        ),
        player_ids=("owner", "opponent"),
        turn_order=("owner", "opponent"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=mission,
        model_geometries=package.model_geometries,
    )
    session = LocalGameSession()
    session.start(config)
    return session


def deploy_native(session: LocalGameSession, *, original_visibility_scene: bool = False) -> None:
    from tests.deployment_submission_helpers import deployment_placement_payload_for_request

    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.geometry.pose import Pose

    status = session.advance_until_decision_or_terminal()
    for index in range(30):
        request = status.decision_request
        assert request is not None, status
        if request.decision_type == "select_movement_unit":
            return
        if request.decision_type == "submit_deployment_placement":
            proposal = request.payload
            assert isinstance(proposal, dict)
            context = proposal["proposal_request"]
            assert isinstance(context, dict)

            def pose(
                i: int,
                player: str,
                model: str,
                unit_id: str = str(context["unit_instance_id"]),
            ) -> Pose:
                if ":second-sorcerer:" in model:
                    return Pose.at(5.5, 4.5)
                if unit_id == "opponent:sorcerer":
                    if original_visibility_scene:
                        return Pose.at(31.0, 4.5)
                    return Pose.at(31.5, 1.5) if ":000004086:" in model else Pose.at(31.0, 1.4)
                state = session.lifecycle.state
                assert state is not None
                own_noise = any(
                    unit.datasheet_id == "000004088"
                    for army in state.army_definitions
                    if army.player_id == "owner"
                    for unit in army.units
                )
                if player == "owner" and own_noise:
                    if ":sorcerer:" in model:
                        return Pose.at(1.4, 1.2)
                    return Pose.at(3.1 + (i % 3) * 1.7, 1.2 + (i // 3) * 1.7)
                if unit_id == "opponent:bodyguard":
                    return Pose.at(
                        (31.0 if original_visibility_scene else 34.0) + (i % 3) * 1.5,
                        1.4 + (i // 3) * 1.5,
                    )
                if player == "owner" and ":sorcerer:" in model:
                    return Pose.at(6.5, 2.9)
                return Pose.at(
                    (3.5 if player == "owner" else 31.0) + (i % 3) * 1.5, 1.4 + (i // 3) * 1.5
                )

            payload = deployment_placement_payload_for_request(
                session.lifecycle, request=request, pose_factory=pose
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id=f"native-deploy:{index}"
            )
        else:
            option = next(
                (o for o in request.options if o.option_id == "decline"), request.options[0]
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"native-setup:{index}",
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("Native setup did not reach Movement")


def translate_native(session: LocalGameSession, unit_id: str, dx: float) -> None:
    from tests.sequential_translation_helpers import leading_first_translation_paths

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.geometry.pose import Pose

    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == "select_movement_unit"
    status = session.submit_option(
        request_id=request.request_id,
        option_id=unit_id,
        result_id=f"{request.request_id}:move-unit",
    )
    for index in range(10):
        request = status.decision_request
        assert request is not None
        if request.decision_type == "submit_movement_proposal":
            break
        choice = "normal_move" if request.decision_type == "select_movement_action" else "decline"
        status = session.submit_option(
            request_id=request.request_id,
            option_id=choice,
            result_id=f"{request.request_id}:move-action:{index}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    else:
        raise AssertionError("Native movement proposal not reached")
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    placements = tuple(
        state.battlefield_state.model_placement_by_id(m.model_instance_id)
        for m in view.own_models
        if m.is_alive
    )
    witness = PathWitness.for_paths(
        leading_first_translation_paths(
            tuple(
                (
                    p.model_instance_id,
                    (p.pose, Pose.at(p.pose.position.x + dx, p.pose.position.y, p.pose.position.z)),
                )
                for p in placements
            ),
            dx=dx,
        )
    )
    assert context.movement_phase_action is not None
    proposal = MovementProposalPayload(
        request.request_id,
        context.proposal_kind,
        unit_id,
        context.movement_phase_action,
        witness,
        movement_mode=str(context.context["movement_mode"])
        if context.context and context.context.get("movement_mode") is not None
        else None,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id=f"{request.request_id}:move-path",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def native_choice(session: LocalGameSession, *, option_id: str | None = None) -> None:
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    request = session.lifecycle.pending_decision_request()
    assert request is not None
    if request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:native-decline",
            payload=stratagem_decline_payload(),
        )
    else:
        default = {
            "select_movement_action": "remain_stationary",
            "select_shooting_unit": "complete_shooting_phase",
            "select_charging_unit": "complete_charge_phase",
            "select_psychic_attack_modifier_ignores": "keep-all-modifiers",
            "use_stratagem": "decline_stratagem_window",
        }.get(request.decision_type, "decline")
        selected = option_id or next(
            (o.option_id for o in request.options if o.option_id == default),
            request.options[0].option_id,
        )
        status = session.submit_option(
            request_id=request.request_id,
            option_id=selected,
            result_id=f"{request.request_id}:native-choice",
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def native_declaration(session: LocalGameSession, unit_id: str) -> None:
    for _ in range(40):
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        if request.decision_type == "submit_shooting_declaration":
            return
        choice = (
            unit_id
            if request.decision_type == "select_shooting_unit"
            else ("normal" if request.decision_type == "select_shooting_type" else None)
        )
        native_choice(session, option_id=choice)
    raise AssertionError("Native shooting declaration not reached")


def native_fire(
    session: LocalGameSession,
    *,
    profile_id: str,
    target_id: str = "attached-unit:opponent:bodyguard",
    ignore_psychic: bool = False,
    result_id: str = "native:energies",
    model_id: str | None = None,
    snap: bool = False,
) -> tuple[str, ...]:
    from typing import cast

    from tests.support.section04_fixtures import shooting_payload

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == "submit_shooting_declaration"
    payload = cast(dict[str, JsonValue], request.payload)
    proposal = cast(dict[str, JsonValue], payload["proposal_request"])
    rows = cast(list[dict[str, JsonValue]], proposal["available_weapons"])
    selected = [
        r
        for r in rows
        if r["weapon_profile_id"] == profile_id
        and (model_id is None or r["model_instance_id"] == model_id)
    ]
    assert selected
    submitted = shooting_payload(request, selected, [target_id] * len(selected))
    if snap:
        assert isinstance(submitted, dict)
        declarations = submitted["declarations"]
        assert isinstance(declarations, list)
        for declaration in declarations:
            assert isinstance(declaration, dict)
            declaration["shooting_type"] = "snap"
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=submitted,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    seen: list[str] = []
    for _ in range(100):
        request = session.lifecycle.pending_decision_request()
        if request is None:
            status = session.advance_until_decision_or_terminal()
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            request = status.decision_request
        assert request is not None
        if request.decision_type in {"select_movement_unit", "select_shooting_unit"}:
            return tuple(seen)
        seen.append(request.decision_type)
        choice = (
            "ignore-detrimental-modifiers"
            if ignore_psychic and request.decision_type == "select_psychic_attack_modifier_ignores"
            else None
        )
        native_choice(session, option_id=choice)
    raise AssertionError("Native shooting did not complete")


def native_sorcerer_overwatch(session: LocalGameSession) -> tuple[str, ...]:
    from typing import cast

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.stratagems import (
        StratagemTargetBinding,
        StratagemTargetKind,
        StratagemTargetProposal,
        StratagemTargetProposalPayload,
    )

    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == "submit_stratagem_target_proposal"
    assert isinstance(request.payload, dict)
    proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, request.payload["proposal_request"])
    )
    assert proposal.stratagem_id == "fire-overwatch"
    proposal = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="owner",
            target_unit_instance_id="attached-unit:owner:bodyguard",
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="native:overwatch-shooter",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    return native_fire(
        session,
        profile_id="000004085:agonising-energies:witchfire",
        result_id="native:reactive",
        snap=True,
    )


def assert_native_movement_budget(
    session: LocalGameSession, unit_id: str, expected_inches: float
) -> None:
    from tests.support.faction_batch01 import events

    completed = [
        event
        for event in events(session, "movement_activation_completed")
        if event["unit_instance_id"] == unit_id
    ]
    assert completed
    models = completed[-1]["model_movements"]
    assert isinstance(models, list)
    assert models
    for model in models:
        assert isinstance(model, dict)
        result = model["path_validation_result"]
        assert isinstance(result, dict)
        assert result["is_valid"] is True
        witness = result["movement_distance_witness"]
        assert isinstance(witness, dict)
        budget = witness["budget"]
        assert isinstance(budget, dict)
        assert budget["max_distance_inches"] == expected_inches
