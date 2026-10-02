"""Real physical-weapon declarations for target-dependent identical attacks."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import cast

from tests.phase13b_shooting_declaration_helpers import (
    _attached_enemy_declarations,
    _attached_enemy_unit_specs,
    _attached_formation_for_player,
    _catalog_with_same_profile_id_target_cache_collision_weapons,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import submit_fixture_request
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_ability_sources import grant_weapon_ability
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


@dataclass(frozen=True)
class PrecisionGroupingScene:
    session: LocalGameSession
    initial_lifecycle: GameLifecyclePayload
    target_id: str
    physical_weapon_ids: tuple[str, ...]
    precision_weapon_id: str


def precision_shooting_scene(
    *,
    precision_first: bool,
    character_target: bool = False,
    random_defence: bool = False,
    duplicate_precision: bool = False,
    duplicate_lethal: bool = False,
    attached_target: bool = False,
) -> PrecisionGroupingScene:
    """Start at canonical phase setup; every attack choice uses the real facade."""
    catalog = _catalog_with_same_profile_id_target_cache_collision_weapons()
    common = replace(
        catalog.wargear[-2].weapon_profiles[0],
        attack_profile=AttackProfile.fixed(2),
        range_profile=RangeProfile.distance(36),
        keywords=(),
        abilities=(),
    )
    if attached_target:
        assert character_target
        common = replace(
            common,
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
            damage_profile=DamageProfile.fixed(12),
        )
    if duplicate_lethal:
        common = replace(
            common,
            keywords=(WeaponKeyword.LETHAL_HITS,),
            abilities=(AbilityDescriptor.lethal_hits(),),
        )
    weapons = catalog.wargear[-2:]
    precision_index = 0 if precision_first else 1
    catalog = replace(
        catalog,
        wargear=(
            *catalog.wargear[:-2],
            *(
                replace(
                    item,
                    weapon_profiles=(
                        replace(common, keywords=(*common.keywords, WeaponKeyword.PRECISION))
                        if index == precision_index
                        else common,
                    ),
                )
                for index, item in enumerate(weapons)
            ),
        ),
    )
    if duplicate_precision:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=(
                        grant_weapon_ability(
                            item.weapon_profiles[0],
                            keyword=WeaponKeyword.PRECISION,
                            ability=None,
                            source_id="order103-precision-grant",
                            source_instance_id="order103-precision-grant-1",
                        ),
                    ),
                )
                if item.wargear_id == weapons[precision_index].wargear_id
                else item
                for item in catalog.wargear
            ),
        )
    if duplicate_lethal:
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(
                    item,
                    weapon_profiles=(
                        grant_weapon_ability(
                            item.weapon_profiles[0],
                            keyword=WeaponKeyword.LETHAL_HITS,
                            ability=AbilityDescriptor.lethal_hits(),
                            source_id="order103-lethal-grant",
                            source_instance_id=item.wargear_id,
                        ),
                    ),
                )
                if item.wargear_id in {weapon.wargear_id for weapon in weapons}
                else item
                for item in catalog.wargear
            ),
        )
    if character_target and not attached_target:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    keywords=replace(
                        sheet.keywords, keywords=(*sheet.keywords.keywords, "CHARACTER")
                    ),
                )
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    if random_defence:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    model_profiles=tuple(
                        replace(
                            model,
                            characteristics=tuple(
                                RandomProfileValue(
                                    Characteristic.TOUGHNESS,
                                    DiceExpression(1, 3, 2),
                                    model.source_ids[0],
                                )
                                if value.characteristic is Characteristic.TOUGHNESS
                                else value
                                for value in model.characteristics
                            ),
                        )
                        for model in sheet.model_profiles
                    ),
                )
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, units = (
        _shooting_lifecycle(
            alpha_unit_ids=("shooter",),
            alpha_unit_specs=(
                ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
            ),
            enemy_unit_specs=_attached_enemy_unit_specs()[:2],
            enemy_attachment_declarations=_attached_enemy_declarations()[:1],
            game_id="order103-attached-precision",
            catalog=_compact_intercessor_catalog(catalog),
        )
        if attached_target
        else _compact_shooting_lifecycle(
            alpha_unit_ids=("shooter",),
            enemy_model_count=2,
            game_id=f"order103-precision-{precision_index}",
            catalog=catalog,
        )
    )
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    state = session.lifecycle.state
    assert state is not None
    target_id = (
        _attached_formation_for_player(state=state, player_id="player-b").attached_unit_instance_id
        if attached_target
        else units["enemy"].unit_instance_id
    )
    assert (
        "CHARACTER" in rules_unit_view_by_id(state=state, unit_instance_id=target_id).keywords
    ) is character_target
    initial = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id=units["shooter"].unit_instance_id,
        result_id="order103-select-shooter",
    ).decision_request
    assert request is not None
    if request.decision_type == "select_shooting_type":
        request = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order103-select-shooting-type",
        ).decision_request
        assert request is not None
    proposal = _proposal_from_request(request=request, target_unit_id=target_id)
    body = cast(dict[str, JsonValue], request.payload)
    proposal_body = cast(dict[str, JsonValue], body["proposal_request"])
    available = cast(list[dict[str, JsonValue]], proposal_body["available_weapons"])
    assert len(available) == 2
    selected_instances: dict[str, tuple[str, ...]] = {}
    if duplicate_precision or duplicate_lethal:
        for candidate in cast(list[dict[str, JsonValue]], proposal_body["target_candidates"]):
            if candidate["target_unit_instance_id"] != target_id:
                continue
            for nested in cast(
                list[dict[str, JsonValue]], candidate["required_weapon_ability_selections"]
            ):
                options = cast(list[dict[str, JsonValue]], nested["options"])
                assert len(options) == 2
                selected = (
                    next(
                        option
                        for option in options
                        if cast(
                            dict[str, JsonValue],
                            cast(dict[str, JsonValue], option["payload"])["ability_source"],
                        )["source_id"]
                        == "order103-lethal-grant"
                    )
                    if duplicate_lethal
                    else options[0]
                )
                selected_instances[cast(str, candidate["weapon_instance_id"])] = (
                    cast(str, selected["option_id"]),
                )
        assert len(selected_instances) == (2 if duplicate_lethal else 1)
    proposal = replace(
        proposal,
        declarations=tuple(
            replace(
                proposal.declarations[0],
                weapon_instance_id=cast(str, item["weapon_instance_id"]),
                wargear_id=cast(str, item["wargear_id"]),
                weapon_profile_id=cast(str, item["weapon_profile_id"]),
                selected_weapon_ability_ids=selected_instances.get(
                    cast(str, item["weapon_instance_id"]), ()
                ),
            )
            for item in available
        ),
    )
    session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="order103-declare-mixed-precision",
    )
    precision_wargear_id = weapons[precision_index].wargear_id
    return PrecisionGroupingScene(
        session=session,
        initial_lifecycle=initial,
        target_id=target_id,
        physical_weapon_ids=tuple(cast(str, item["weapon_instance_id"]) for item in available),
        precision_weapon_id=next(
            cast(str, item["weapon_instance_id"])
            for item in available
            if item["wargear_id"] == precision_wargear_id
        ),
    )


def offered_group_request(session: LocalGameSession) -> DecisionRequest:
    """Return the actual generated choice, including automatic singleton choices."""
    recorded = tuple(
        item.request
        for item in session.lifecycle.decision_controller.records
        if item.request.decision_type == "select_attack_weapon_group"
    )
    if recorded:
        return recorded[0]
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "select_attack_weapon_group"
    return request


def precision_melee_scene(*, precision_first: bool) -> PrecisionGroupingScene:
    """One primary plus two physical Extra Attacks weapons, through legal commitment."""
    catalog = _compact_intercessor_catalog(
        _catalog_with_same_profile_id_target_cache_collision_weapons()
    )
    primary = next(item for item in catalog.wargear if item.wargear_id == "core-leader-blade")
    common = replace(
        primary.weapon_profiles[0],
        attack_profile=AttackProfile.fixed(2),
        keywords=(WeaponKeyword.EXTRA_ATTACKS,),
        abilities=(),
    )
    extra = catalog.wargear[-2:]
    precision_index = 0 if precision_first else 1
    catalog = replace(
        catalog,
        wargear=(
            *catalog.wargear[:-2],
            *(
                replace(
                    item,
                    weapon_profiles=(
                        replace(common, keywords=(*common.keywords, WeaponKeyword.PRECISION))
                        if index == precision_index
                        else common,
                    ),
                )
                for index, item in enumerate(extra)
            ),
        ),
        datasheets=tuple(
            replace(
                sheet,
                wargear_options=tuple(
                    replace(
                        option,
                        default_wargear_ids=(primary.wargear_id, *option.default_wargear_ids),
                        allowed_wargear_ids=(primary.wargear_id, *option.allowed_wargear_ids),
                        min_selections=3,
                        max_selections=3,
                    )
                    for option in sheet.wargear_options
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("subject",),
        enemy_unit_ids=("enemy",),
        origins={"subject": Pose.at(10, 20), "enemy": Pose.at(10, 22)},
        game_id=f"order103-melee-{precision_index}",
        model_count=1,
        enemy_unit_specs={"enemy": ("core-intercessor-like-infantry", "core-intercessor-like", 2)},
        fights_first_unit_keys=("subject",),
        catalog=catalog,
    )
    initial = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    session = LocalGameSession(lifecycle)
    for _ in range(20):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_melee_declaration":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Mixed Extra Attacks commitment did not reach melee declaration.")
    melee = MeleeDeclarationProposalRequest.from_decision_request(request)
    weapons = tuple(cast(dict[str, JsonValue], item) for item in melee.available_weapons)
    assert len(weapons) == 3
    assert sum(item["is_extra_attacks"] is False for item in weapons) == 1
    assert sum(item["is_extra_attacks"] is True for item in weapons) == 2
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order103-mixed-melee",
        payload={
            "proposal_request_id": melee.request_id,
            "proposal_kind": melee.proposal_kind,
            "player_id": melee.actor_id,
            "battle_round": melee.battle_round,
            "unit_instance_id": melee.unit_instance_id,
            "source_decision_request_id": melee.source_decision_request_id,
            "source_decision_result_id": melee.source_decision_result_id,
            "declarations": [
                {
                    "attacker_model_instance_id": item["model_instance_id"],
                    "weapon_instance_id": item["weapon_instance_id"],
                    "wargear_id": item["wargear_id"],
                    "weapon_profile_id": item["weapon_profile_id"],
                    "target_allocations": [
                        {"target_unit_instance_id": units["enemy"].unit_instance_id}
                    ],
                }
                for item in weapons
            ],
        },
    )
    return PrecisionGroupingScene(
        session=session,
        initial_lifecycle=initial,
        target_id=units["enemy"].unit_instance_id,
        physical_weapon_ids=tuple(
            cast(str, item["weapon_instance_id"])
            for item in weapons
            if item["is_extra_attacks"] is True
        ),
        precision_weapon_id=next(
            cast(str, item["weapon_instance_id"])
            for item in weapons
            if item["wargear_id"] == extra[precision_index].wargear_id
        ),
    )


def assert_precision_scene_persistence_and_completion(
    scene: PrecisionGroupingScene, *, allow_precision: bool = False
) -> None:
    session = scene.session
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    for current in (session, restored):
        for _ in range(30):
            if any(
                event.event_type == "attack_sequence_completed"
                for event in current.lifecycle.decision_controller.event_log.records
            ):
                break
            request = current.advance_until_decision_or_terminal().decision_request
            assert request is not None
            assert allow_precision or request.decision_type != "select_precision_allocation"
            submit_fixture_request(current, request)
        else:
            raise AssertionError("Mixed PRECISION attacks did not complete through real decisions.")
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert allow_precision or not any(
        record.request.decision_type == "select_precision_allocation"
        for record in session.lifecycle.decision_controller.records
    )
    artifact = ReplayArtifact.capture(
        artifact_id="order103-mixed-precision",
        initial_lifecycle_payload=scene.initial_lifecycle,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
