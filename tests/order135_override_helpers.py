"""Pregame analytical Core catalog exercising the generic token consumer.

The retained token wording is compiled through RuleIR. The three-attack rifle,
token allowance and Sustained Hits are declared fixture data, not a faction
provider certification. Setup, dice and every subsequent choice are native.
"""

from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
    DatasheetWargearOption,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.wargear_selection_limits import DatasheetWargearSelectionLimit
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice_result_override_descriptors import (
    ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.engine.wargear_selections import WargearSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def override_config() -> GameConfig:
    source = "source:aeldari:aspect-shrine-token"
    token = "fixture:order135:token"
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(
            objective_scope=ObjectiveRuleScope.CORE_RULES,
            source_id=source,
            raw_text=(
                "Once per battle for each Aspect Shrine token this unit has, you can change "
                "the result of one Hit roll or one Wound roll made for a model in this unit "
                "(excluding CHARACTER models) to an unmodified 6."
            ),
        ),
        source_keyword_sequence_parts=("CHARACTER",),
    )
    ability = DatasheetAbilityDescriptor(
        ability_id=token,
        name="Fixture Token",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        source_wargear_id=token,
        effect_description="Generic retained token consumer in an analytical Core fixture.",
        rule_ir_payload=cast(CatalogJsonObject, compiled.rule_ir.to_payload()),
    )
    option = DatasheetWargearOption(
        option_id=token,
        model_profile_id="core-intercessor-like",
        default_wargear_ids=(),
        allowed_wargear_ids=(token,),
        min_selections=0,
        max_selections=1,
        source_ids=(source,),
        selection_limit=DatasheetWargearSelectionLimit(
            selection_group_id=token,
            models_per_increment=1,
            max_group_selections_per_increment=1,
            max_option_selections_per_increment=1,
            unit_resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
            unit_resource_amount_per_selection=1,
        ),
    )
    unit = unit_selection(
        unit_selection_id="scalar",
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )
    attacker = replace(
        unit,
        wargear_selections=(
            WargearSelection(
                option_id=token,
                model_profile_id="core-intercessor-like",
                wargear_ids=(token,),
                selection_count=3,
            ),
        ),
    )
    config = phase11c_config(
        game_id="order135-native-override",
        player_a_units=(attacker,),
        player_b_units=(unit,),
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                row,
                abilities=(*row.abilities, ability),
                wargear_options=(*row.wargear_options, option),
            )
            if row.datasheet_id == unit.datasheet_id
            else row
            for row in config.army_catalog.datasheets
        ),
        wargear=(
            *(
                replace(
                    weapon,
                    weapon_profiles=tuple(
                        replace(
                            profile,
                            range_profile=RangeProfile.distance(60),
                            attack_profile=AttackProfile.fixed(3),
                            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
                            keywords=(WeaponKeyword.SUSTAINED_HITS,),
                            abilities=(AbilityDescriptor.sustained_hits(1),),
                        )
                        for profile in weapon.weapon_profiles
                    ),
                )
                if weapon.wargear_id == "core-bolt-rifle"
                else weapon
                for weapon in config.army_catalog.wargear
            ),
            Wargear(wargear_id=token, name="Fixture Token", source_ids=(source,)),
        ),
    )
    assert config.mission_setup is not None
    mission = replace(config.mission_setup, terrain_features=())
    return replace(
        config,
        army_catalog=catalog,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )


def native_override_session() -> LocalGameSession:
    session = LocalGameSession()
    session.start(override_config())
    for index in range(100):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        kind = request.decision_type
        if kind == "select_dice_result_override":
            return session
        if kind == "submit_shooting_declaration":
            proposal = proposal_from_request(request=request, target_unit_id="army-beta:scalar")
            payload = proposal.to_payload()
            payload["declarations"] = payload["declarations"][:1]
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="override:declaration",
                payload=validate_json_value(payload),
            )
        elif kind == "submit_deployment_placement":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"override:deploy:{index}",
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda i, owner, _model: Pose.at(
                        8 if owner == "player-a" else 52, 26 + 1.5 * i
                    ),
                ),
            )
        elif kind == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"override:decline:{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            special = {
                "select_secondary_missions": "fixed:assassination:bring_it_down",
                "select_shooting_unit": "army-alpha:scalar",
                "select_shooting_type": "normal",
                "select_movement_action": "remain_stationary",
            }
            option = special.get(
                kind,
                next(
                    (
                        item.option_id
                        for item in request.options
                        if item.option_id.startswith(("complete_", "end_", "decline", "skip"))
                    ),
                    request.options[0].option_id,
                ),
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"override:setup:{index}",
                option_id=option,
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Native override did not reach its first Hit decision.")


def next_override(session: LocalGameSession) -> DecisionRequest:
    for _ in range(80):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "select_dice_result_override":
            return request
        decline_choice(session, request)
    raise AssertionError("Next override was not reached.")


def decline_choice(session: LocalGameSession, request: DecisionRequest) -> None:
    if request.decision_type == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{request.request_id}:decline",
            payload=stratagem_decline_payload(),
        )
    else:
        option = next(
            (o.option_id for o in request.options if "decline" in o.option_id),
            request.options[0].option_id,
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:resolve",
            option_id=option,
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
