"""Synthetic profiles declared before ordinary Core setup, for physical rules controls."""

from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from tests.s25_declared_rule_helpers import (
    declared_activated_reroll_ability,
    declared_activated_variant_ability,
    declared_own_ignore_ability,
    declared_uniform_hit_ability,
)
from tests.s25_fixed_damage_relevance_helpers import declared_fixed_damage_roll_ability
from tests.s25_generic_damage_permission_helpers import declared_shared_damage_permission
from tests.s25_generic_source_relevance_helpers import declared_attack_relevance_characteristic
from tests.s25_permission_relevance_helpers import (
    declared_activated_relevance_ability,
    declared_passive_invulnerable_provider_ability,
)
from tests.s25_shared_unit_permission_helpers import declared_shared_unit_permission_ability
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose


def native_profile_request(*, player: str, mode: str) -> tuple[LocalGameSession, DecisionRequest]:
    units = (
        unit_selection(
            unit_selection_id="scalar",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
    )
    other = "player-b" if player == "player-a" else "player-a"
    cover = mode in {"obscuring-cover", "obscuring-cover-ignored"}
    shared_damage = mode in {"shared-unit-damage", "shared-unit-qualified-damage"}
    attached = mode in {"attached-own-ignore", "shared-unit-permission"} or shared_damage
    activation_mode = mode.startswith("activated-own-")
    activation_player = (
        other
        if mode
        in {
            "activated-own-unused-defender-characteristics",
            "activated-own-unused-defender-save-with-inv-provider",
            "activated-own-unused-defender-zero-ap-save-roll",
        }
        else player
    )
    own_units = (
        (
            *units,
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        )
        if attached
        else units
    )
    cover_targets = (
        tuple(
            unit_selection(
                unit_selection_id=key,
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            )
            for key in ("scalar", "smoke")
        )
        if cover
        else units
    )
    config = phase11c_config(
        game_id=f"s25-native:{player}:{mode}",
        player_a_units=own_units if player == "player-a" else cover_targets,
        player_b_units=own_units if player == "player-b" else cover_targets,
        player_a_attachment_declarations=(AttachmentDeclaration("leader", "scalar"),)
        if attached and player == "player-a"
        else (),
        player_b_attachment_declarations=(AttachmentDeclaration("leader", "scalar"),)
        if attached and player == "player-b"
        else (),
    )
    assert config.mission_setup is not None
    own_hit_ability = (
        declared_shared_damage_permission(
            chooser=True, qualified_roll=mode == "shared-unit-qualified-damage"
        )
        if shared_damage
        else declared_shared_unit_permission_ability(chooser=True)
        if mode == "shared-unit-permission"
        else declared_uniform_hit_ability()
        if mode == "uniform-own-hit"
        else declared_own_ignore_ability()
        if mode in {"own-ignore", "attached-own-ignore"}
        else declared_fixed_damage_roll_ability(qualified_roll="qualified" in mode)
        if mode.startswith("activated-own-fixed-damage-roll")
        else declared_activated_reroll_ability()
        if mode == "activated-own-reroll"
        else declared_attack_relevance_characteristic(
            mode.removeprefix("activated-own-").removesuffix("-one")
        )
        if mode
        in {
            "activated-own-unused-movement-one",
            "activated-own-meaningful-strength-one",
        }
        else declared_activated_relevance_ability(mode.removeprefix("activated-own-"))
        if mode.removeprefix("activated-own-").removesuffix("-one")
        in {
            "unused-wound",
            "unused-damage-roll",
            "unused-characteristics",
            "duplicate-rapid-fire",
            "unused-defender-characteristics",
            "unused-defender-save-with-inv-provider",
            "unused-defender-zero-ap-save-roll",
        }
        else declared_activated_variant_ability(mode.removeprefix("activated-own-"))
        if activation_mode
        else None
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                item,
                model_profiles=tuple(
                    replace(
                        model,
                        source_ids=(*model.source_ids, "analytical:s25-predeclared-toughness"),
                        characteristics=tuple(
                            RandomProfileValue(
                                Characteristic.TOUGHNESS,
                                DiceExpression(1, 3, 3),
                                "analytical:s25-predeclared-toughness",
                            )
                            if mode == "random-toughness"
                            and value.characteristic is Characteristic.TOUGHNESS
                            else value
                            for value in model.characteristics
                        ),
                    )
                    for model in item.model_profiles
                ),
            )
            if mode == "random-toughness"
            else item
            for item in config.army_catalog.datasheets
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        range_profile=RangeProfile.distance(60),
                        attack_profile=(
                            AttackProfile(dice_expression=DiceExpression(1, 3, 1))
                            if mode == "random-attacks"
                            else AttackProfile.fixed(2)
                        ),
                        skill=(
                            RandomProfileValue(
                                Characteristic.BALLISTIC_SKILL,
                                DiceExpression(1, 3, 1),
                                "analytical:s25-predeclared-profile",
                            )
                            if mode in {"random-skill", "activated-own-random-skill"}
                            else CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2)
                        ),
                        strength=(
                            RandomProfileValue(
                                Characteristic.STRENGTH,
                                DiceExpression(1, 3, 3),
                                "analytical:s25-predeclared-profile",
                            )
                            if mode == "random-strength"
                            else CharacteristicValue.from_raw(Characteristic.STRENGTH, 12)
                            if mode in {"random-damage", "random-ap"} or shared_damage
                            else profile.strength
                        ),
                        armor_penetration=(
                            RandomProfileValue(
                                Characteristic.ARMOR_PENETRATION,
                                DiceExpression(1, 3, -4),
                                "analytical:s25-predeclared-profile",
                            )
                            if mode == "random-ap"
                            else CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6)
                            if mode == "random-damage" or shared_damage
                            else CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0)
                            if mode == "activated-own-unused-defender-zero-ap-save-roll"
                            else profile.armor_penetration
                        ),
                        damage_profile=(
                            DamageProfile(dice_expression=DiceExpression(1, 3, 0))
                            if mode == "random-damage" or shared_damage
                            else profile.damage_profile
                        ),
                        keywords=(
                            (*profile.keywords, WeaponKeyword.ONE_SHOT, WeaponKeyword.HAZARDOUS)
                            if mode == "physical-completion"
                            else (*profile.keywords, WeaponKeyword.IGNORES_COVER)
                            if mode == "obscuring-cover-ignored"
                            else profile.keywords
                        ),
                        source_ids=(*profile.source_ids, "analytical:s25-predeclared-profile"),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            if item.wargear_id == "core-bolt-rifle"
            else item
            for item in config.army_catalog.wargear
        ),
    )
    if own_hit_ability is not None:
        abilities = (
            (own_hit_ability, declared_uniform_hit_ability())
            if mode in {"own-ignore", "attached-own-ignore"}
            else (own_hit_ability, declared_passive_invulnerable_provider_ability())
            if mode == "activated-own-unused-defender-save-with-inv-provider"
            else (own_hit_ability, declared_shared_unit_permission_ability(chooser=False))
            if mode == "shared-unit-permission"
            else (
                own_hit_ability,
                declared_shared_damage_permission(
                    chooser=False, qualified_roll=mode == "shared-unit-qualified-damage"
                ),
            )
            if shared_damage
            else (own_hit_ability,)
        )
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    item,
                    abilities=(*item.abilities, *abilities),
                    source_ids=(*item.source_ids, *(ability.source_id for ability in abilities)),
                )
                if item.datasheet_id
                == (
                    "core-character-leader"
                    if mode == "shared-unit-permission" or shared_damage
                    else "core-intercessor-like-infantry"
                )
                else item
                for item in catalog.datasheets
            ),
        )
    if cover:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    item,
                    keywords=replace(item.keywords, keywords=(*item.keywords.keywords, "SMOKE")),
                )
                if item.datasheet_id == "core-character-leader"
                else item
                for item in catalog.datasheets
            ),
        )
    mission = replace(config.mission_setup, terrain_features=())
    session = LocalGameSession()
    session.start(
        replace(
            config,
            army_catalog=catalog,
            mission_setup=mission,
            turn_order=(player, other),
            ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
                mission, rules_overlay_ids=()
            ),
        )
    )

    def deployment_pose(index: int, owner: str, model_id: str) -> Pose:
        if not cover:
            return Pose.at(8 if owner == "player-a" else 52, 26 + 1.5 * index)
        x, y = (
            (50, 27.3)
            if ":smoke:" in model_id
            else (55, 26.75)
            if owner == other
            else (8, (26, 15.8, 19, 22, 24)[index])
            if mode == "obscuring-cover-ignored"
            else (8, 26 + 1.5 * index)
        )
        return Pose.at(x if player == "player-a" else 60 - x, y)

    for index in range(240 if activation_mode else 100):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "select_shooting_type":
            status = session.submit_option(
                request_id=request.request_id,
                option_id="normal",
                result_id=f"s25-profile:normal:{index}",
            )
            assert status.decision_request is not None
            assert status.decision_request.decision_type == "submit_shooting_declaration"
            return session, status.decision_request
        if request.decision_type == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=deployment_pose,
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=payload,
                result_id=f"s25-profile:deploy:{index}",
            )
        elif request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=stratagem_decline_payload(),
                result_id=f"s25-profile:decline:{index}",
            )
        else:
            source_use = False
            activation = (
                activation_mode
                and request.decision_type == "select_catalog_any_phase_once_per_battle_ability"
            )
            if activation:
                state = session.lifecycle.state
                assert state is not None
                desired = {
                    m.model_instance_id
                    for army in state.army_definitions
                    if army.player_id == activation_player
                    for unit in army.units
                    if unit.unit_instance_id.endswith(":scalar")
                    for m in unit.own_models[: 1 if mode.endswith("-one") else 2]
                }
                activation_payload = cast(dict[str, JsonValue], request.payload)
                source_use = (
                    request.actor_id == activation_player
                    and activation_payload["phase"] == "shooting"
                    and cast(str, activation_payload["source_model_instance_id"]) in desired
                )
            defender_army = "army-beta" if player == "player-a" else "army-alpha"
            option = (
                next(
                    o.option_id
                    for o in request.options
                    if cast(dict[str, JsonValue], o.payload)["activate"] is source_use
                )
                if activation
                else f"use-stratagem:smokescreen:target:{defender_army}:smoke"
                if cover
                and request.decision_type == "use_stratagem"
                and request.actor_id == other
                and any(
                    o.option_id.endswith(":smoke") and "smokescreen" in o.option_id
                    for o in request.options
                )
                else "fixed:assassination:bring_it_down"
                if request.decision_type == "select_secondary_missions"
                else next(
                    o.option_id for o in request.options if o.option_id.startswith("attached-unit:")
                )
                if attached and request.decision_type == "select_shooting_unit"
                else ("army-alpha:scalar" if player == "player-a" else "army-beta:scalar")
                if request.decision_type == "select_shooting_unit"
                else "remain_stationary"
                if request.decision_type == "select_movement_action"
                else next(
                    (
                        o.option_id
                        for o in request.options
                        if o.option_id.startswith(("complete_", "end_", "decline", "skip"))
                    ),
                    request.options[0].option_id,
                )
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option,
                result_id=f"s25-profile:setup:{index}",
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("S25 predeclared profile did not reach ordinary native Shooting.")
