"""Actual loaded Chaos Daemons Icon sources at a canonical Command boundary."""

from __future__ import annotations

from dataclasses import replace

from tests.order93_nonattack_helpers import add_nonattack_effects
from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    destroy_models_with_recorded_mortal_wounds,
    phase11c_config,
    secondary_choice,
)
from tests.phase17n_primary_mission_helpers import phase17n_event_setup
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import (
    AttachmentEligibility,
    AttachmentRole,
    AttachmentTargetEligibility,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.profile_modifiers import profile_with_delta
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07,
)


def icon_leadership_session(
    *, datasheet_id: str, bearer_alive: bool, attached_leader: bool = False
) -> tuple[LocalGameSession, str, frozenset[str]]:
    package = chaos_daemons_roster_2026_07.catalog_package()
    base_catalog = (
        _with_test_leader(package.army_catalog, datasheet_id=datasheet_id)
        if attached_leader
        else package.army_catalog
    )
    catalog = replace(
        base_catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            profile_with_delta(
                                value,
                                1,
                                source_id="source:icon-test:leadership-penalty",
                                modifier_id="icon-test:leadership-penalty",
                                bound_numeric=True,
                            )
                            if value.characteristic is Characteristic.LEADERSHIP
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in base_catalog.datasheets
        ),
    )
    sheet = catalog.datasheet_by_id(datasheet_id)
    icon = next(
        ability for ability in sheet.abilities if ability.source_id.endswith(f"{datasheet_id}:3")
    )
    wargear_id = icon.source_wargear_id
    assert wargear_id is not None
    assert wargear_id == f"{datasheet_id}:daemonic-icon"
    option = next(
        option for option in sheet.wargear_options if wargear_id in option.allowed_wargear_ids
    )
    selection = UnitMusterSelection(
        unit_selection_id="icon-unit",
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(
                model_profile_id=composition.model_profile_id, model_count=composition.max_models
            )
            for composition in sheet.composition
        ),
        wargear_selections=(
            WargearSelection(
                option_id=option.option_id,
                model_profile_id=option.model_profile_id,
                wargear_ids=(wargear_id,),
            ),
        ),
    )
    config = replace(
        phase11c_config(game_id=f"order93-icon-{datasheet_id}"),
        army_catalog=catalog,
        army_muster_requests=tuple(
            ArmyMusterRequest(
                army_id=f"army-{suffix}",
                player_id=f"player-{suffix}",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="chaos-daemons", detachment_ids=("shadow-legion",)
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    selection,
                    *(
                        (
                            UnitMusterSelection(
                                unit_selection_id="leader",
                                datasheet_id="core-character-leader",
                                model_profile_selections=(
                                    ModelProfileSelection(
                                        model_profile_id="core-character-leader", model_count=1
                                    ),
                                ),
                            ),
                        )
                        if attached_leader and suffix == "a"
                        else ()
                    ),
                ),
                attachment_declarations=(
                    (
                        AttachmentDeclaration(
                            source_unit_selection_id="leader",
                            bodyguard_unit_selection_id="icon-unit",
                        ),
                    )
                    if attached_leader and suffix == "a"
                    else ()
                ),
            )
            for suffix in ("a", "b")
        ),
        mission_setup=phase17n_event_setup(
            layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
            attacker_force_disposition_id="purge-the-foe",
            defender_force_disposition_id="purge-the-foe",
        ),
    )
    state = GameState.from_config(config)
    decisions = DecisionController()
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=catalog, request=request))
    assert config.mission_setup is not None
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="order93-icon-battlefield",
            armies=tuple(state.army_definitions),
            battlefield_width_inches=config.mission_setup.battlefield_width_inches,
            battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
            terrain_features=config.mission_setup.terrain_features,
        ).battlefield_state
    )
    for owner in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=owner, mode=SecondaryMissionMode.FIXED)
        )
    if attached_leader:
        from warhammer40k_core.geometry.pose import Pose

        assert state.battlefield_state is not None
        leader_placement = state.battlefield_state.unit_placement_by_id("army-a:leader")
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                leader_placement,
                model_placements=tuple(
                    replace(model, pose=Pose.at(7, 8))
                    for model in leader_placement.model_placements
                ),
            )
        )
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    unit = state.army_definitions[0].units[0]
    bearer = next(model for model in unit.own_models if wargear_id in model.wargear_ids)
    non_bearers = tuple(model for model in unit.own_models if model is not bearer)
    alive_ids = frozenset(
        (bearer.model_instance_id, non_bearers[0].model_instance_id)
        if bearer_alive
        else (non_bearers[0].model_instance_id, non_bearers[1].model_instance_id)
    )
    rules_unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id=unit.unit_instance_id
    ).unit_instance_id
    destroy_models_with_recorded_mortal_wounds(
        state=state,
        decisions=decisions,
        unit_instance_id=rules_unit_id,
        model_instance_ids=tuple(
            model.model_instance_id
            for model in unit.own_models
            if model.model_instance_id not in alive_ids
        ),
        application_id="icon-test:casualties",
        destroying_player_id="player-b",
    )
    if attached_leader:
        leader = next(
            unit
            for unit in state.army_definitions[0].units
            if unit.unit_instance_id == "army-a:leader"
        )
        alive_ids = alive_ids.union(model.model_instance_id for model in leader.own_models)
    add_nonattack_effects(
        state,
        unit_id=rules_unit_id,
        owner="player-a",
        characteristic="leadership",
        operations=False,
    )
    return (
        LocalGameSession(
            GameLifecycle.from_payload(
                {
                    "config": config.to_payload(),
                    "parameterized_movement_proposals": True,
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                }
            )
        ),
        icon.source_id,
        alive_ids,
    )


def _with_test_leader(catalog: ArmyCatalog, *, datasheet_id: str) -> ArmyCatalog:
    """Canonical fixture attachment; it does not assert a published Daemon relationship.

    The bodyguard and its Icon RuleIR remain the actual loaded source. The
    canonical Leader supplies a distinct physical component through real muster
    validation and attached-unit formation, without a runtime handler injection.
    """
    canonical = ArmyCatalog.phase9a_canonical_content_pack()
    leader = canonical.datasheet_by_id("core-character-leader")
    leader = replace(
        leader,
        keywords=DatasheetKeywordSet(
            keywords=leader.keywords.keywords, faction_keywords=("LEGIONES DAEMONICA",)
        ),
        model_profiles=tuple(
            replace(
                profile,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.LEADERSHIP, 7)
                    if value.characteristic is Characteristic.LEADERSHIP
                    else value
                    for value in profile.characteristics
                ),
            )
            for profile in leader.model_profiles
        ),
        attachment_eligibilities=(
            AttachmentEligibility(
                role=AttachmentRole.LEADER,
                targets=(
                    AttachmentTargetEligibility(
                        bodyguard_datasheet_id=datasheet_id,
                        source_ids=("test:icon-cross-component-attachment",),
                    ),
                ),
            ),
        ),
    )
    return replace(
        catalog,
        datasheets=(*catalog.datasheets, leader),
        wargear=(
            *catalog.wargear,
            next(
                wargear
                for wargear in canonical.wargear
                if wargear.wargear_id == "core-leader-blade"
            ),
        ),
        detachments=tuple(
            replace(
                detachment, unit_datasheet_ids=(*detachment.unit_datasheet_ids, leader.datasheet_id)
            )
            for detachment in catalog.detachments
        ),
    )
