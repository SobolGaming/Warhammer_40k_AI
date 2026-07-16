from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    WeaponKeyword,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.fight_resolution import (
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeWeaponDeclaration,
    available_melee_weapons_payloads,
    melee_target_unit_ids,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.geometry.pose import Pose


def melee_fixture(
    *,
    include_extra_attacks: bool = False,
    leader_keywords: tuple[WeaponKeyword, ...] = (),
    leader_abilities: tuple[AbilityDescriptor, ...] = (),
    target_a_pose: Pose | None = None,
    target_b_pose: Pose | None = None,
    target_a_datasheet_id: str = "core-character-leader",
    target_a_model_profile_id: str = "core-character-leader",
    target_a_model_count: int = 1,
) -> tuple[
    ArmyCatalog,
    RulesetDescriptor,
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
]:
    resolved_target_a_pose = Pose.at(12.0, 10.0) if target_a_pose is None else target_a_pose
    resolved_target_b_pose = Pose.at(10.0, 12.0) if target_b_pose is None else target_b_pose
    catalog = melee_catalog(
        include_extra_attacks=include_extra_attacks,
        leader_keywords=leader_keywords,
        leader_abilities=leader_abilities,
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase15d-test")
    armies = melee_armies(
        catalog,
        target_a_datasheet_id=target_a_datasheet_id,
        target_a_model_profile_id=target_a_model_profile_id,
        target_a_model_count=target_a_model_count,
    )
    attacker = armies[0].unit_by_id("army-alpha:attacker")
    if include_extra_attacks:
        attacker = replace(
            attacker,
            wargear_selections=(
                WargearSelection(
                    option_id="phase15d-extra-attacks",
                    model_profile_id="core-character-leader",
                    wargear_ids=("core-leader-blade", "core-extra-blade"),
                ),
            ),
        )
        armies = (
            replace(armies[0], units=(attacker,)),
            armies[1],
        )
    target_a = armies[1].unit_by_id("army-beta:target-a")
    target_b = armies[1].unit_by_id("army-beta:target-b")
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15d-battlefield",
        armies=armies,
    )
    battlefield = scenario.battlefield_state
    battlefield = battlefield.with_unit_placement(
        unit_placement(
            attacker, army_id="army-alpha", player_id="player-a", pose=Pose.at(10.0, 10.0)
        )
    )
    battlefield = battlefield.with_unit_placement(
        unit_placement(
            target_a, army_id="army-beta", player_id="player-b", pose=resolved_target_a_pose
        )
    )
    battlefield = battlefield.with_unit_placement(
        unit_placement(
            target_b,
            army_id="army-beta",
            player_id="player-b",
            pose=resolved_target_b_pose,
        )
    )
    return (
        catalog,
        ruleset,
        BattlefieldScenario(armies=armies, battlefield_state=battlefield),
        attacker,
        target_a,
        target_b,
    )


def melee_catalog(
    *,
    include_extra_attacks: bool,
    leader_keywords: tuple[WeaponKeyword, ...] = (),
    leader_abilities: tuple[AbilityDescriptor, ...] = (),
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if leader_keywords or leader_abilities:
        leader_blade = next(
            wargear for wargear in catalog.wargear if wargear.wargear_id == "core-leader-blade"
        )
        leader_profile = leader_blade.weapon_profiles[0]
        updated_leader_blade = replace(
            leader_blade,
            weapon_profiles=(
                replace(
                    leader_profile,
                    keywords=tuple(sorted(leader_keywords)),
                    abilities=leader_abilities,
                ),
            ),
        )
        catalog = replace(
            catalog,
            wargear=tuple(
                updated_leader_blade
                if wargear.wargear_id == updated_leader_blade.wargear_id
                else wargear
                for wargear in catalog.wargear
            ),
        )
    if not include_extra_attacks:
        return catalog
    leader_blade = next(
        wargear for wargear in catalog.wargear if wargear.wargear_id == "core-leader-blade"
    )
    leader_profile = leader_blade.weapon_profiles[0]
    extra_profile = replace(
        leader_profile,
        profile_id="core-extra-blade:standard",
        name="Core extra blade",
        keywords=(WeaponKeyword.EXTRA_ATTACKS,),
    )
    return replace(
        catalog,
        wargear=(
            *catalog.wargear,
            Wargear(
                wargear_id="core-extra-blade",
                name="Core extra blade",
                weapon_profiles=(extra_profile,),
            ),
        ),
    )


def melee_armies(
    catalog: ArmyCatalog,
    *,
    target_a_datasheet_id: str = "core-character-leader",
    target_a_model_profile_id: str = "core-character-leader",
    target_a_model_count: int = 1,
) -> tuple[ArmyDefinition, ArmyDefinition]:
    return (
        muster_army(
            catalog=catalog,
            request=army_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_ids=("attacker",),
            ),
        ),
        muster_army(
            catalog=catalog,
            request=ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    unit_muster_selection(
                        unit_selection_id="target-a",
                        datasheet_id=target_a_datasheet_id,
                        model_profile_id=target_a_model_profile_id,
                        model_count=target_a_model_count,
                    ),
                    unit_muster_selection(
                        unit_selection_id="target-b",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )


def army_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            unit_muster_selection(
                unit_selection_id=unit_id,
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            )
            for unit_id in unit_ids
        ),
    )


def unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def unit_placement(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    pose: Pose,
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(
                    pose.position.x,
                    pose.position.y + (index * 2.0),
                    pose.position.z,
                    facing_degrees=pose.facing.degrees,
                ),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def melee_request(
    *,
    catalog: ArmyCatalog,
    ruleset: RulesetDescriptor,
    scenario: BattlefieldScenario,
    attacker: UnitInstance,
) -> MeleeDeclarationProposalRequest:
    return MeleeDeclarationProposalRequest(
        request_id="phase15d-melee-request",
        actor_id="player-a",
        game_id="phase15d-game",
        battle_round=1,
        active_player_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id="phase15d-source-request",
        source_decision_result_id="phase15d-source-result",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        available_weapons=available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit=attacker,
            army_catalog=catalog,
        ),
        target_unit_instance_ids=melee_target_unit_ids(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_instance_id=attacker.unit_instance_id,
        ),
    )


def melee_proposal(
    *,
    request: MeleeDeclarationProposalRequest,
    attacker: UnitInstance,
    declarations: tuple[MeleeWeaponDeclaration, ...],
) -> MeleeDeclarationProposal:
    return MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=declarations,
    )
