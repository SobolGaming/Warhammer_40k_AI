"""Unresolved target replacement after real preceding attacks destroy the target."""

import json
from dataclasses import replace
from typing import cast

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.phase13b_shooting_declaration_helpers import (
    _catalog_with_same_profile_id_target_cache_collision_weapons,
    _compact_intercessor_catalog,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.precision_grouping_helpers import PrecisionGroupingScene
from tests.psychic_modifier_helpers import submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.geometry.pose import Pose


def precision_replacement_scene(*, replacement_character: bool) -> PrecisionGroupingScene:
    catalog = _compact_intercessor_catalog(
        _catalog_with_same_profile_id_target_cache_collision_weapons()
    )
    weapons = catalog.wargear[-2:]
    common = replace(
        weapons[0].weapon_profiles[0],
        range_profile=RangeProfile.distance(36),
        attack_profile=AttackProfile.fixed(2),
        keywords=(),
        abilities=(),
    )
    kill = replace(
        weapons[0],
        wargear_id="order103-preceding-weapon",
        weapon_profiles=(
            replace(
                common,
                attack_profile=AttackProfile.fixed(8),
                keywords=(WeaponKeyword.TORRENT,),
                strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                armor_penetration=CharacteristicValue.from_raw(
                    Characteristic.ARMOR_PENETRATION, -6
                ),
                damage_profile=DamageProfile.fixed(12),
            ),
        ),
    )
    catalog = replace(
        catalog,
        wargear=(
            *catalog.wargear[:-2],
            replace(
                weapons[0], weapon_profiles=(replace(common, keywords=(WeaponKeyword.PRECISION,)),)
            ),
            replace(weapons[1], weapon_profiles=(common,)),
            kill,
        ),
        datasheets=tuple(
            replace(
                sheet,
                wargear_options=tuple(
                    replace(
                        option,
                        default_wargear_ids=(*option.default_wargear_ids, kill.wargear_id),
                        allowed_wargear_ids=(*option.allowed_wargear_ids, kill.wargear_id),
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
    infantry: tuple[str, str, int] = (
        "core-intercessor-like-infantry",
        "core-intercessor-like",
        2,
    )
    character: tuple[str, str, int] = ("core-character-leader", "core-character-leader", 1)
    old_target = infantry if replacement_character else character
    new_target = character if replacement_character else infantry
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        alpha_unit_specs=(
            ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_unit_specs=(
            ("old", old_target[0], old_target[1], old_target[2]),
            ("new", new_target[0], new_target[1], new_target[2]),
        ),
        game_id=f"order103-replacement-{replacement_character}",
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    # Canonical initial phase placement. No pose or history changes after this root.
    for key, x, y in (("shooter", 10, 20), ("old", 20, 20), ("new", 20, 25)):
        _replace_unit_poses(
            state,
            unit_instance_id=units[key].unit_instance_id,
            poses=tuple(Pose.at(x + 1.4 * i, y) for i in range(len(units[key].own_models))),
        )
    initial = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    session = LocalGameSession(GameLifecycle.from_payload(initial))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id=units["shooter"].unit_instance_id,
        result_id="order103-replacement-shooter",
    ).decision_request
    assert request is not None
    if request.decision_type == "select_shooting_type":
        request = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order103-replacement-type",
        ).decision_request
        assert request is not None
    proposal = _proposal_from_request(request=request, target_unit_id=units["old"].unit_instance_id)
    body = cast(dict[str, JsonValue], request.payload)
    available = cast(
        list[dict[str, JsonValue]],
        cast(dict[str, JsonValue], body["proposal_request"])["available_weapons"],
    )
    assert len(available) == 3
    proposal = replace(
        proposal,
        declarations=tuple(
            replace(
                proposal.declarations[0],
                weapon_instance_id=cast(str, item["weapon_instance_id"]),
                wargear_id=cast(str, item["wargear_id"]),
                weapon_profile_id=cast(str, item["weapon_profile_id"]),
            )
            for item in available
        ),
    )
    request = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="order103-replacement-declare",
    ).decision_request
    assert request is not None
    assert request.decision_type == "select_attack_weapon_group"
    preceding = next(
        option
        for option in request.options
        if cast(
            list[dict[str, JsonValue]],
            cast(
                dict[str, JsonValue], cast(dict[str, JsonValue], option.payload)["gathered_group"]
            )["contributions"],
        )[0]["wargear_id"]
        == kill.wargear_id
    )
    session.submit_option(
        request_id=request.request_id,
        option_id=preceding.option_id,
        result_id="order103-preceding-attacks",
    )
    replacements = 0
    for _ in range(60):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "select_target_replacement":
            session.submit_option(
                request_id=request.request_id,
                option_id=f"target:{units['new'].unit_instance_id}",
                result_id=f"order103-replace-{replacements}",
            )
            replacements += 1
            if replacements == 2:
                break
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("Preceding real attacks did not offer both unresolved replacements.")
    assert any(
        event.event_type == "model_destroyed"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    return PrecisionGroupingScene(
        session=session,
        initial_lifecycle=initial,
        target_id=units["new"].unit_instance_id,
        physical_weapon_ids=tuple(
            cast(str, item["weapon_instance_id"])
            for item in available
            if item["wargear_id"] != kill.wargear_id
        ),
        precision_weapon_id=next(
            cast(str, item["weapon_instance_id"])
            for item in available
            if item["wargear_id"] == weapons[0].wargear_id
        ),
    )
