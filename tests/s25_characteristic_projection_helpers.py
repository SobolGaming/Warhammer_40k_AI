"""Explicit analytical characteristic sources through full native setup/activation."""

from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)


def declared_projection_ability(characteristic: Characteristic) -> DatasheetAbilityDescriptor:
    """Pre-start typed IR; never official source evidence or a persisted-state edit."""
    text = (
        "S25 analytical characteristic projection: once per battle at phase start, "
        f"modify this model's {characteristic.value} until the end of the phase."
    )
    source = "analytical:s25-characteristic-projection:" + characteristic.value
    span = TextSpan(text, 0, len(text))
    delta = -1 if characteristic is Characteristic.ARMOR_PENETRATION else 1
    clause = RuleClause(
        source + ":clause",
        span,
        trigger=RuleTrigger(
            RuleTriggerKind.TIMING_WINDOW,
            span,
            parameters_from_pairs((("edge", "start"), ("phase", "any"))),
        ),
        conditions=(
            RuleCondition(
                RuleConditionKind.FREQUENCY_LIMIT,
                span,
                parameters_from_pairs(
                    (
                        ("activation_kind", "optional_ability_use"),
                        ("max_uses", 1),
                        ("scope", "battle"),
                        ("usage_subject", "this_model"),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(RuleTargetKind.THIS_MODEL, span),
        effects=(
            RuleEffectSpec(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                span,
                parameters_from_pairs((("characteristic", characteristic.value), ("delta", delta))),
            ),
        ),
        duration=RuleDuration(
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            span,
            parameters_from_pairs((("endpoint", "phase"),)),
        ),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-characteristic-projection:" + characteristic.value,
        name="S25 analytical characteristic projection " + characteristic.value,
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )


def projection_shooting_request(
    *, player: str, characteristic: Characteristic, base_attacks: int = 2
) -> tuple[LocalGameSession, DecisionRequest]:
    units = (
        unit_selection(
            unit_selection_id="scalar",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
    )
    other = "player-b" if player == "player-a" else "player-a"
    config = phase11c_config(
        game_id=f"s25-characteristic-projection:{player}:{characteristic.value}",
        player_a_units=units,
        player_b_units=units,
    )
    ability = declared_projection_ability(characteristic)
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                item,
                abilities=(*item.abilities, ability),
                source_ids=(*item.source_ids, ability.source_id),
            )
            if item.datasheet_id == "core-intercessor-like-infantry"
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
                        attack_profile=AttackProfile.fixed(base_attacks),
                        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
                        source_ids=(*profile.source_ids, "analytical:s25-projection-profile"),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            if item.wargear_id == "core-bolt-rifle"
            else item
            for item in config.army_catalog.wargear
        ),
    )
    assert config.mission_setup is not None
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
    for index in range(240):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "select_shooting_type":
            status = session.submit_option(
                request_id=request.request_id,
                option_id="normal",
                result_id=f"s25-projection:normal:{index}",
            )
            assert status.decision_request is not None
            assert status.decision_request.decision_type == "submit_shooting_declaration"
            return session, status.decision_request
        if request.decision_type == "submit_deployment_placement":
            payload = deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda n, owner, _model_id: Pose.at(
                    8 if owner == "player-a" else 52, 26 + 1.5 * n
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=payload,
                result_id=f"s25-projection:deploy:{index}",
            )
        elif request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=stratagem_decline_payload(),
                result_id=f"s25-projection:decline:{index}",
            )
        elif request.decision_type == "select_catalog_any_phase_once_per_battle_ability":
            state = session.lifecycle.state
            assert state is not None
            source_model = next(
                unit.own_models[0].model_instance_id
                for army in state.army_definitions
                if army.player_id == player
                for unit in army.units
                if unit.unit_instance_id.endswith(":scalar")
            )
            activation = cast(dict[str, JsonValue], request.payload)
            use = (
                request.actor_id == player
                and activation["phase"] == "shooting"
                and activation["source_model_instance_id"] == source_model
            )
            option = next(
                o.option_id
                for o in request.options
                if cast(dict[str, JsonValue], o.payload)["activate"] is use
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option,
                result_id=f"s25-projection:activate:{index}",
            )
        elif request.decision_type == "select_secondary_missions":
            status = session.submit_option(
                request_id=request.request_id,
                option_id="fixed:assassination:bring_it_down",
                result_id=f"s25-projection:secondary:{index}",
            )
        else:
            option = (
                "remain_stationary"
                if request.decision_type == "select_movement_action"
                else ("army-alpha:scalar" if player == "player-a" else "army-beta:scalar")
                if request.decision_type == "select_shooting_unit"
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
                result_id=f"s25-projection:setup:{index}",
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Full native projection setup did not reach Shooting.")
