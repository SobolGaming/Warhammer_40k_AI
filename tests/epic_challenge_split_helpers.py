"""Public setup, split, deployment and Charge lead to a real D12 Fight window.

An analytical pre-battle split descriptor and adjacent legal deployment zones
are declared before start. W50 prevents this finite ownership scene from ending
before continuation checks; wounds, dice and all later mutations remain native.
The descriptor exercises existing Core splitting, not a faction granting claim.
"""

import math
from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.movement_witness_membership_helpers import quiet_choice
from tests.phase11c_command_phase_helpers import mustered_armies, phase11c_config, unit_selection
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.list_validation import AttachmentDeclaration, UnitMusterSelection
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as keyword_source,
)


def native_split_epic_request(
    *, player: str, split: bool = True, casualty: str | None = None
) -> tuple[LocalGameSession, DecisionRequest]:
    assert player in {"player-a", "player-b"}
    other = "player-b" if player == "player-a" else "player-a"
    assert casualty in {None, "leader", "bodyguard"}
    assert casualty is None or not split
    charger = player if casualty is None else other
    subjects: tuple[UnitMusterSelection, ...] = (
        unit_selection(
            unit_selection_id="bodyguard",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
        unit_selection(
            unit_selection_id="leader",
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
        ),
    )
    if casualty == "leader":
        subjects += (
            unit_selection(
                unit_selection_id="support",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        )
    enemies = (
        unit_selection(
            unit_selection_id="enemy",
            datasheet_id="d12:casualty-attacker" if casualty else "core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
        ),
    )
    config = phase11c_config(
        game_id=f"d12-native-split:{player}:{split}:{casualty}",
        player_a_units=subjects if player == "player-a" else enemies,
        player_b_units=subjects if player == "player-b" else enemies,
        player_a_attachment_declarations=tuple(
            AttachmentDeclaration(name, "bodyguard")
            for name in (("leader", "support") if casualty == "leader" else ("leader",))
        )
        if player == "player-a"
        else (),
        player_b_attachment_declarations=tuple(
            AttachmentDeclaration(name, "bodyguard")
            for name in (("leader", "support") if casualty == "leader" else ("leader",))
        )
        if player == "player-b"
        else (),
    )
    text = (
        "At the start of the Declare Battle Formations step, before any units have been set up, "
        "this unit can be split into two units, each containing five models."
    )
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="d12:analytical-split",
            raw_text=text,
            objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
        ),
        source_keyword_sequence_parts=keyword_source.canonical_datasheet_keyword_sequence_parts(),
    ).rule_ir
    ability = DatasheetAbilityDescriptor(
        ability_id="d12:analytical-split",
        name="D12 analytical split",
        source_id=rule.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    charge_text = "Add 10 to Charge rolls made for the bearer's unit."
    charge_rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="d12:analytical-charge",
            raw_text=charge_text,
            objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
        ),
        source_keyword_sequence_parts=keyword_source.canonical_datasheet_keyword_sequence_parts(),
    ).rule_ir
    assert all(clause.is_supported for clause in charge_rule.clauses)
    charge_ability = DatasheetAbilityDescriptor(
        ability_id=charge_rule.source_id,
        name="D12 analytical Charge modifier",
        source_id=charge_rule.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=charge_text,
        rule_ir_payload=cast(CatalogJsonObject, charge_rule.to_payload()),
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                abilities=(*sheet.abilities, ability)
                if split and sheet.datasheet_id == "core-intercessor-like-infantry"
                else (*sheet.abilities, charge_ability)
                if sheet.datasheet_id == "core-character-leader"
                else sheet.abilities,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue.from_raw(
                                Characteristic.WOUNDS,
                                1
                                if casualty == "bodyguard"
                                and sheet.datasheet_id == "core-intercessor-like-infantry"
                                else 50,
                            )
                            if value.characteristic is Characteristic.WOUNDS
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in config.army_catalog.datasheets
        ),
    )
    if casualty:
        original = catalog.datasheet_by_id("core-character-leader")
        original_weapon = next(
            item for item in catalog.wargear if item.wargear_id == "core-leader-blade"
        )
        weapon = replace(
            original_weapon,
            wargear_id="d12:casualty-weapon",
            name="D12 analytical casualty weapon",
            weapon_profiles=tuple(
                replace(
                    profile,
                    profile_id="d12:casualty-weapon:standard",
                    attack_profile=AttackProfile.fixed(1 if casualty == "leader" else 20),
                    damage_profile=DamageProfile.fixed(50 if casualty == "leader" else 1),
                    strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 100),
                    armor_penetration=CharacteristicValue.from_raw(
                        Characteristic.ARMOR_PENETRATION, -6
                    ),
                    keywords=(
                        *((WeaponKeyword.TORRENT,) if casualty == "bodyguard" else ()),
                        WeaponKeyword.TWIN_LINKED,
                        WeaponKeyword.ONE_SHOT,
                        *((WeaponKeyword.PRECISION,) if casualty == "leader" else ()),
                    ),
                    source_ids=("d12:analytical-casualty-profile",),
                )
                for profile in original_weapon.weapon_profiles
            ),
            source_ids=("d12:analytical-casualty-profile",),
        )
        attacker = replace(
            original,
            datasheet_id="d12:casualty-attacker",
            name="D12 analytical casualty attacker",
            wargear_options=tuple(
                replace(
                    option,
                    default_wargear_ids=(weapon.wargear_id,),
                    allowed_wargear_ids=(weapon.wargear_id,),
                )
                for option in original.wargear_options
            ),
            attachment_eligibilities=(),
            source_ids=("d12:analytical-casualty-profile",),
        )
        catalog = replace(
            catalog, wargear=(*catalog.wargear, weapon), datasheets=(*catalog.datasheets, attacker)
        )
    config = replace(config, army_catalog=catalog)
    declared = mustered_armies(config)
    radii: dict[str, float] = {}
    for army in declared:
        for unit in army.units:
            for model in unit.own_models:
                base = model.geometry.base_shape()
                assert isinstance(base, CircularBase)
                radii[model.model_instance_id] = base.radius
    character_radius = next(
        radii[m.model_instance_id]
        for a in declared
        for u in a.units
        for m in u.own_models
        if u.unit_instance_id.endswith(":leader")
    )
    enemy_radius = next(
        radii[m.model_instance_id]
        for a in declared
        for u in a.units
        for m in u.own_models
        if u.unit_instance_id.endswith(":enemy")
    )
    gap = config.ruleset_descriptor.engagement_policy.horizontal_inches + 0.5
    enemy_x = 14 + character_radius + enemy_radius + gap
    boundary = 14 + character_radius + gap / 2
    assert config.mission_setup is not None
    mission = replace(
        config.mission_setup,
        terrain_features=(),
        battlefield_layout_id=None,
        terrain_layout_id="d12:empty",
        deployment_map_id="d12:adjacent-zones",
        deployment_zones=(
            DeploymentZone.rectangle("A", player, min_x=0, min_y=0, max_x=boundary, max_y=44),
            DeploymentZone.rectangle("B", other, min_x=boundary, min_y=0, max_x=60, max_y=44),
        ),
    )
    config = replace(
        config,
        army_catalog=catalog,
        mission_setup=mission,
        turn_order=(charger, other if charger == player else player),
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )
    poses: dict[str, Pose] = {}
    leader_id: str | None = None
    enemy_id: str | None = None
    for army in mustered_armies(config):
        for unit in army.units:
            for index, model in enumerate(unit.own_models):
                if unit.unit_instance_id.endswith(":bodyguard"):
                    pose = (
                        Pose.at(10.8, 28 + index * 1.6)
                        if index < 3
                        else Pose.at(14, 28 + (index - 3) * 3.2)
                    )
                elif unit.unit_instance_id.endswith(":leader"):
                    leader_id = model.model_instance_id
                    pose = Pose.at(14, 29.6)
                elif unit.unit_instance_id.endswith(":support"):
                    pose = Pose.at(12.4, 31.2)
                else:
                    enemy_id = model.model_instance_id
                    pose = Pose.at(enemy_x, 29.6)
                poses[model.model_instance_id] = pose
    assert leader_id is not None
    assert enemy_id is not None
    session = LocalGameSession()
    session.start(config)
    charged = False
    for index in range(140):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        kind = request.decision_type
        result_id = f"d12:native-split:{index}"
        if kind == "submit_stratagem_target_proposal" and request.actor_id == player:
            from tests.order135_counteroffensive_helpers import proposal_from_native_request

            if proposal_from_native_request(request).stratagem_id == "epic-challenge":
                rules_view = rules_unit_view_by_id(
                    state=state, unit_instance_id=state.unit_instance_id_for_model(leader_id)
                )
                if casualty == "leader":
                    assert not rules_view.model_by_id(leader_id).is_alive, (
                        "Native Precision fixture did not destroy Leader."
                    )
                elif casualty == "bodyguard":
                    assert not any(
                        model.is_alive
                        for component in rules_view.components
                        if component.role == "bodyguard"
                        for model in component.unit.own_models
                    ), "Native fixture did not destroy complete Bodyguard."
                return session, request
        if kind == "select_unit_split_membership":
            option = (
                "split"
                if any(o.option_id == "split" for o in request.options)
                else request.options[0].option_id
            )
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=option
            )
        elif kind == "submit_deployment_placement":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, _owner, model: poses[model],
                ),
            )
        elif kind == "select_charging_unit" and request.actor_id == charger and not charged:
            rules_view = rules_unit_view_by_id(
                state=state,
                unit_instance_id=state.unit_instance_id_for_model(
                    leader_id if charger == player else enemy_id
                ),
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=result_id,
                option_id=rules_view.unit_instance_id,
            )
        elif kind == "select_charge_targets" and request.actor_id == charger:
            target = rules_unit_view_by_id(
                state=state,
                unit_instance_id=state.unit_instance_id_for_model(
                    enemy_id if charger == player else leader_id
                ),
            )
            option = next(
                o.option_id
                for o in request.options
                if isinstance(o.payload, dict)
                and o.payload.get("target_ids") == [target.unit_instance_id]
            )
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=option
            )
        elif kind == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            if move.proposal_kind is not ProposalKind.CHARGE_MOVE:
                submit_fixture_request(session, request)
                continue
            placement = charge_movement_placement(
                scenario=battlefield_scenario_for_state(state=state),
                unit_instance_id=move.unit_instance_id,
            )
            target = rules_unit_view_by_id(
                state=state,
                unit_instance_id=state.unit_instance_id_for_model(
                    enemy_id if charger == player else leader_id
                ),
            )
            assert move.context is not None
            maximum = move.context["maximum_distance_inches"]
            assert isinstance(maximum, (int, float))
            target_placement = charge_movement_placement(
                scenario=battlefield_scenario_for_state(state=state),
                unit_instance_id=target.unit_instance_id,
            )
            target_model = next(
                model
                for model in target_placement.model_placements
                if model.model_instance_id == (enemy_id if charger == player else leader_id)
            )
            charge_policy = session.lifecycle.config.ruleset_descriptor.charge_policy
            preferred = charge_policy.preferred_target_distance_inches
            assert preferred == 1.0
            ends: dict[str, Pose] = {}
            for mover in placement.model_placements:
                dy = mover.pose.position.y - target_model.pose.position.y
                radius = (
                    radii[mover.model_instance_id] + radii[target_model.model_instance_id] + 0.8
                )
                assert abs(dy) < radius
                sign = -1 if charger == player else 1
                end = Pose.at(
                    target_model.pose.position.x + sign * math.sqrt(radius**2 - dy**2),
                    mover.pose.position.y,
                )
                assert (
                    math.dist(
                        (mover.pose.position.x, mover.pose.position.y),
                        (end.position.x, end.position.y),
                    )
                    <= maximum
                )
                ends[mover.model_instance_id] = end
            paths = tuple(
                (
                    model.model_instance_id,
                    (
                        model.pose,
                        Pose.at(
                            (model.pose.position.x + ends[model.model_instance_id].position.x) / 2,
                            model.pose.position.y,
                        ),
                        ends[model.model_instance_id],
                    ),
                )
                for model in sorted(placement.model_placements, key=lambda m: -m.pose.position.x)
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=validate_json_value(
                    ChargeMoveProposal(
                        proposal_request_id=request.request_id,
                        unit_instance_id=move.unit_instance_id,
                        proposal_kind=move.proposal_kind,
                        movement_phase_action="charge_move",
                        movement_mode=MovementMode.CHARGE,
                        charge_target_unit_instance_ids=(target.unit_instance_id,),
                        witness=PathWitness.for_paths(paths),
                    ).to_payload()
                ),
            )
            charged = status.status_kind is not LifecycleStatusKind.INVALID
        elif kind == "submit_melee_declaration":
            from tests.epic_challenge_helpers import submit_all_melee

            submit_all_melee(session, request)
            continue
        elif (
            kind == "select_precision_allocation"
            and casualty == "leader"
            and request.actor_id == other
        ):
            option = next(
                option.option_id
                for option in request.options
                if isinstance(option.payload, dict)
                and isinstance(option.payload.get("selected_model_ids"), list)
                and leader_id in cast(list[str], option.payload["selected_model_ids"])
            )
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=option
            )
        elif kind == "select_dice_reroll":
            assert isinstance(request.payload, dict)
            assert request.payload["roll_type"] == "attack_sequence.wound"
            # Declared Twin-linked rerolls are only selected for a failed natural1.
            option = "reroll:0" if request.payload["current_values"] == [1] else "decline"
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=option
            )
        else:
            if state.stage is GameLifecycleStage.SETUP:
                assert request.options
                status = session.submit_option(
                    request_id=request.request_id,
                    result_id=result_id,
                    option_id=request.options[0].option_id,
                )
                assert status.status_kind is not LifecycleStatusKind.INVALID, status
                continue
            quiet_choice(session, request)
            continue
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    raise AssertionError("Native split/Charge did not reach the real Epic Challenge window.")
