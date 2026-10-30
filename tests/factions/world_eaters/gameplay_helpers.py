"""Fresh canonical World Eaters consumer fixtures; no official roster certification."""

from dataclasses import replace
from typing import cast

from tests.factions.world_eaters.world_eaters_helpers import (
    ICON_OF_KHORNE_WARGEAR_ID,
    _world_eaters_catalog,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import army_rule
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

SOURCE = "army-alpha:source"
ENEMY = "army-beta:enemy"


def gameplay_session(
    *,
    game_id: str,
    enemy_x: float = 12.0,
    lethal: bool = False,
    phase: BattlePhase = BattlePhase.FIGHT,
    enemy_first: bool = False,
    infantry_target: bool = True,
    extra_enemy_x: float | None = None,
) -> LocalGameSession:
    catalog = _world_eaters_catalog()
    leader = catalog.datasheet_by_id("core-character-leader")
    leader = replace(
        leader,
        keywords=replace(
            leader.keywords, keywords=tuple(token.upper() for token in leader.keywords.keywords)
        ),
    )
    we_leader = replace(
        leader,
        datasheet_id="we-gameplay-leader",
        keywords=replace(leader.keywords, faction_keywords=("WORLD EATERS",)),
        wargear_options=tuple(
            replace(
                option,
                default_wargear_ids=(*option.default_wargear_ids, ICON_OF_KHORNE_WARGEAR_ID),
                allowed_wargear_ids=(*option.allowed_wargear_ids, ICON_OF_KHORNE_WARGEAR_ID),
                min_selections=2,
                max_selections=2,
            )
            for option in leader.wargear_options
        ),
    )
    catalog = replace(
        catalog,
        datasheets=(
            *(
                replace(leader, keywords=replace(leader.keywords, keywords=("VEHICLE",)))
                if item.datasheet_id == leader.datasheet_id and not infantry_target
                else leader
                if item.datasheet_id == leader.datasheet_id
                else item
                for item in catalog.datasheets
            ),
            we_leader,
        ),
        detachments=tuple(
            replace(
                item,
                unit_datasheet_ids=(*item.unit_datasheet_ids, we_leader.datasheet_id),
                force_disposition_ids=(*item.force_disposition_ids, "purge-the-foe"),
            )
            if item.detachment_id == "berzerker-warband"
            else item
            for item in catalog.detachments
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(1),
                        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -6
                        ),
                        damage_profile=DamageProfile.fixed(10 if lethal else 1),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            if item.wargear_id == "core-leader-blade"
            else item
            for item in catalog.wargear
        ),
    )
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",) if extra_enemy_x is None else ("enemy", "next-enemy"),
        origins={
            "source": Pose.at(10, 10),
            "enemy": Pose.at(enemy_x, 10),
            **({} if extra_enemy_x is None else {"next-enemy": Pose.at(extra_enemy_x, 10)}),
        },
        game_id=game_id,
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs={"source": (we_leader.datasheet_id, "core-character-leader", 1)},
        alpha_faction_id=army_rule.WORLD_EATERS_FACTION_ID,
        alpha_detachment_ids=("berzerker-warband",),
        fights_first_unit_keys=(("enemy",) if enemy_first else ("source",))
        if phase is BattlePhase.FIGHT
        else (),
        charge_fights_first_unit_keys=("source",)
        if not enemy_first and phase is BattlePhase.FIGHT
        else (),
        battle_phase=phase,
    )
    return LocalGameSession(lifecycle)


def select_blessings(session: LocalGameSession, *blessings: army_rule.BlessingOfKhorne) -> None:
    state = session.lifecycle.state
    assert state is not None
    phase_index = state.battle_phase_index
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    decisions = session.lifecycle.decision_controller
    options = army_rule.blessings_selection_options(
        player_id="player-a",
        battle_round=state.battle_round,
        dice_values=(6, 6, 5, 5, 4, 4, 3, 3),
        bloodshed_points=0,
    )
    request = decisions.request_decision(
        DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id="player-a",
            payload={"hook_id": army_rule.HOOK_ID},
            options=options,
        )
    )
    selected = "+".join(sorted(item.value for item in blessings))
    result = DecisionResult.for_request(
        result_id="we-gameplay-blessings",
        request=request,
        selected_option_id=f"world_eaters:blessings:{selected}",
    )
    decisions.submit_result(result)
    assert army_rule.apply_blessings_selection_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    state.battle_phase_index = phase_index


def events(session: LocalGameSession, kind: str) -> list[dict[str, JsonValue]]:
    return [
        cast(dict[str, JsonValue], event.payload)
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == kind
    ]


def reach(session: LocalGameSession, kind: str, *, limit: int = 40) -> DecisionRequest:
    for _ in range(limit):
        request = pending_request(session)
        if request.decision_type == kind:
            return request
        if request.decision_type == "select_movement_unit" and any(
            option.option_id == SOURCE for option in request.options
        ):
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:source",
                option_id=SOURCE,
            )
            continue
        submit_gameplay_request(session, request)
    raise AssertionError(f"Did not reach {kind}")


def complete_activation(
    session: LocalGameSession, unit_id: str, *, lethal_choice: str = "auto-wound"
) -> None:
    for _ in range(80):
        if any(
            row.get("unit_instance_id") == unit_id
            for row in events(session, "fight_activation_completed")
        ):
            return
        request = pending_request(session)
        if request.decision_type == "select_lethal_hit_wound":
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:chosen",
                option_id=lethal_choice,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        else:
            submit_gameplay_request(session, request)
    raise AssertionError(f"Fight activation did not complete for {unit_id}")


def submit_gameplay_request(session: LocalGameSession, request: DecisionRequest) -> None:
    if request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:decline",
            payload=stratagem_decline_payload(),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    elif request.decision_type == "select_movement_action":
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:stationary",
            option_id="remain_stationary",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    else:
        submit_fixture_request(session, request)


def move_fight(session: LocalGameSession, request: DecisionRequest, *, dx: float) -> None:
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert move.context is not None
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(move.unit_instance_id)
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (model.pose, Pose.at(model.pose.position.x + dx, model.pose.position.y)),
            )
            for model in placement.model_placements
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"{request.request_id}:witnessed",
        payload={
            "proposal_request_id": move.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": move.movement_phase_action,
            "movement_mode": move.context["movement_mode"],
            "pile_in_target_unit_instance_ids": move.context["legal_target_unit_instance_ids"],
            "witness": validate_json_value(witness.to_payload()),
        },
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()


def attached_gameplay_session(
    *,
    game_id: str,
    phase: BattlePhase = BattlePhase.FIGHT,
    icon: bool = True,
    enemy_x: float = 13.5,
    bodyguard_count: int = 5,
) -> LocalGameSession:
    """Real canonical mustering and attachment; analytical profiles, not roster certification."""
    from warhammer40k_core.core.datasheet import DatasheetWargearOption
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration

    catalog = _world_eaters_catalog()
    ids = ("core-character-leader", "core-intercessor-like-infantry")
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                composition=tuple(replace(part, min_models=1) for part in sheet.composition)
                if bodyguard_count == 1 and sheet.datasheet_id == ids[1]
                else sheet.composition,
                keywords=replace(
                    sheet.keywords,
                    keywords=tuple(token.upper() for token in sheet.keywords.keywords),
                    faction_keywords=(*sheet.keywords.faction_keywords, "WORLD EATERS"),
                ),
                wargear_options=(
                    *sheet.wargear_options,
                    DatasheetWargearOption(
                        option_id="we-attached:icon",
                        model_profile_id="core-intercessor-like",
                        default_wargear_ids=(ICON_OF_KHORNE_WARGEAR_ID,),
                        allowed_wargear_ids=(ICON_OF_KHORNE_WARGEAR_ID,),
                        min_selections=1,
                        max_selections=1,
                        source_ids=(army_rule.ICON_OF_KHORNE_RULE_UPDATE_SOURCE,),
                    ),
                )
                if icon and sheet.datasheet_id == ids[1]
                else sheet.wargear_options,
            )
            if sheet.datasheet_id in ids
            else sheet
            for sheet in catalog.datasheets
        ),
        detachments=tuple(
            replace(
                item,
                unit_datasheet_ids=(*item.unit_datasheet_ids, *ids),
                force_disposition_ids=(*item.force_disposition_ids, "purge-the-foe"),
            )
            if item.detachment_id == "berzerker-warband"
            else item
            for item in catalog.detachments
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(1),
                        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -6
                        ),
                        damage_profile=DamageProfile.fixed(10),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            if item.wargear_id == "core-leader-blade"
            else item
            for item in catalog.wargear
        ),
    )
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=("bodyguard", "leader"),
        enemy_unit_ids=("enemy",),
        origins={},
        poses_by_unit_key={
            "bodyguard": (
                (Pose.at(11.5, 11.5),)
                if bodyguard_count == 1
                else tuple(Pose.at(10, 10 + 1.5 * i) for i in range(bodyguard_count))
            ),
            "leader": (Pose.at(11.5, 10),),
            "enemy": (Pose.at(enemy_x, 10),),
        },
        alpha_unit_specs={
            "leader": ("core-character-leader", "core-character-leader", 1),
            "bodyguard": (
                "core-intercessor-like-infantry",
                "core-intercessor-like",
                bodyguard_count,
            ),
        },
        enemy_unit_specs={"enemy": ("core-character-leader", "core-character-leader", 1)},
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "bodyguard"),),
        alpha_faction_id="world-eaters",
        alpha_detachment_ids=("berzerker-warband",),
        catalog=catalog,
        game_id=game_id,
        battle_phase=phase,
        fights_first_unit_keys=("bodyguard",),
        record_deployment=True,
    )
    return LocalGameSession(lifecycle)
