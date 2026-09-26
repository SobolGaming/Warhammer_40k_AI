"""Facade-driven random defensive profiles on real gathered weapon contributions."""

from dataclasses import replace
from typing import cast

from tests.phase13b_shooting_declaration_helpers import (
    _catalog_with_same_profile_id_target_cache_collision_weapons,
    _compact_shooting_lifecycle,
    _proposal_from_request,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfile, WeaponKeyword
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle


def gathered_profile_session(
    characteristic: Characteristic = Characteristic.TOUGHNESS,
    *,
    extra_group: bool = False,
    contribution_count: int = 2,
) -> LocalGameSession:
    assert contribution_count in (1, 2)
    assert not extra_group or contribution_count == 2
    catalog = _catalog_with_same_profile_id_target_cache_collision_weapons()
    common = catalog.wargear[-2].weapon_profiles[0]
    common = replace(
        common,
        attack_profile=AttackProfile.fixed(2),
        range_profile=RangeProfile.distance(36),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    catalog = replace(
        catalog,
        wargear=(
            *catalog.wargear[:-2],
            *(replace(w, weapon_profiles=(common,)) for w in catalog.wargear[-2:]),
        ),
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        model,
                        characteristics=tuple(
                            RandomProfileValue(
                                characteristic, DiceExpression(1, 3, 2), model.source_ids[0]
                            )
                            if value.characteristic is characteristic
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
    if extra_group:
        extra = replace(
            catalog.wargear[-1],
            wargear_id="zz-order87-separate-group",
            weapon_profiles=(
                replace(common, strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 7)),
            ),
        )
        catalog = replace(
            catalog,
            wargear=(*catalog.wargear, extra),
            datasheets=tuple(
                replace(
                    sheet,
                    wargear_options=tuple(
                        replace(
                            option,
                            default_wargear_ids=(*option.default_wargear_ids, extra.wargear_id),
                            allowed_wargear_ids=(*option.allowed_wargear_ids, extra.wargear_id),
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
    lifecycle, units = _compact_shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        enemy_model_count=2,
        game_id="order87-gathered-profiles",
        catalog=catalog,
    )
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id=units["shooter"].unit_instance_id,
        result_id="select-shooter",
    ).decision_request
    assert request is not None
    if request.decision_type == "select_shooting_type":
        request = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="select-shooting-type",
        ).decision_request
        assert request is not None
    proposal = _proposal_from_request(
        request=request, target_unit_id=units["enemy"].unit_instance_id
    )
    payload = cast(dict[str, JsonValue], request.payload)
    proposal_request = cast(dict[str, JsonValue], payload["proposal_request"])
    weapons = cast(list[dict[str, JsonValue]], proposal_request["available_weapons"])
    assert len(weapons) == (3 if extra_group else 2)
    proposal = replace(
        proposal,
        declarations=tuple(
            replace(
                proposal.declarations[0],
                weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
                wargear_id=cast(str, weapon["wargear_id"]),
                weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
            )
            for weapon in (weapons if extra_group else weapons[:contribution_count])
        ),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="declare-gathered-shots",
    )
    if extra_group:
        request = status.decision_request
        assert request is not None
        assert request.decision_type == "select_attack_weapon_group"
        option = next(
            option
            for option in request.options
            if isinstance(option.payload, dict)
            and isinstance(option.payload["gathered_group"], dict)
            and option.payload["gathered_group"]["total_attacks"] == 4
        )
        session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id="select-gathered-group",
        )
    return session
