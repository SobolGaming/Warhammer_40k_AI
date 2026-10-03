"""Config-backed objective scenes, rooted before decisions and boundary evidence."""

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _configure_shooting_battle_state,
    shooting_lifecycle,
)
from tests.phase17n_primary_mission_helpers import phase17n_event_setup
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose

SOURCE = "army-alpha:source"
SUPPORT = "army-alpha:support"
LEADER = "army-alpha:leader"


def control_session(
    *,
    source_oc: int = 0,
    attached: bool = False,
    random_oc: bool = False,
    primary_mission: bool = False,
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue(
                                Characteristic.OBJECTIVE_CONTROL, source_oc, source_oc, source_oc
                            )
                            if value.characteristic is Characteristic.OBJECTIVE_CONTROL
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    if random_oc:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    model_profiles=tuple(
                        replace(
                            profile,
                            characteristics=tuple(
                                RandomProfileValue(
                                    Characteristic.OBJECTIVE_CONTROL,
                                    DiceExpression(1, 3),
                                    profile.source_ids[0],
                                )
                                if value.characteristic is Characteristic.OBJECTIVE_CONTROL
                                else value
                                for value in profile.characteristics
                            ),
                        )
                        for profile in sheet.model_profiles
                    ),
                )
                if sheet.datasheet_id == "core-character-leader"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    lifecycle, units = shooting_lifecycle(
        alpha_unit_ids=("source", "support", *(("leader",) if attached else ())),
        alpha_datasheets=dict.fromkeys(
            ("support", *(("leader",) if attached else ())),
            ("core-character-leader", "core-character-leader", 1),
        ),
        alpha_attachment_declarations=(
            (
                AttachmentDeclaration(
                    source_unit_selection_id="leader", bodyguard_unit_selection_id="source"
                ),
            )
            if attached
            else ()
        ),
        game_id=f"order109-control-{source_oc}-{attached}",
        catalog=catalog,
    )
    if primary_mission:
        setup = phase17n_event_setup(
            layout_id="purge-the-foe-vs-priority-assets-layout-1",
            attacker_force_disposition_id="priority-assets",
            defender_force_disposition_id="purge-the-foe",
        )
        config = lifecycle.config
        assert config is not None
        catalog = replace(
            catalog,
            detachments=tuple(
                replace(
                    detachment,
                    force_disposition_ids=tuple(
                        sorted({*detachment.force_disposition_ids, "priority-assets"})
                    ),
                )
                for detachment in catalog.detachments
            ),
        )
        config = replace(
            config,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(),
            army_catalog=catalog,
            mission_setup=setup,
            army_muster_requests=tuple(
                replace(request, force_disposition_id="priority-assets")
                if request.player_id == "player-a"
                else request
                for request in config.army_muster_requests
            ),
        )
        armies = tuple(
            muster_army(catalog=catalog, request=request) for request in config.army_muster_requests
        )
        units = {
            unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
            for army in armies
            for unit in army.units
        }
        scenario = create_deterministic_battlefield_scenario(
            battlefield_id="order109-mission",
            armies=armies,
            battlefield_width_inches=setup.battlefield_width_inches,
            battlefield_depth_inches=setup.battlefield_depth_inches,
            terrain_features=setup.terrain_features,
        )
        lifecycle = GameLifecycle()
        lifecycle.start(config)
        lifecycle.decision_controller.event_log = EventLog()
        assert lifecycle.state is not None
        _configure_shooting_battle_state(
            state=lifecycle.state,
            decisions=lifecycle.decision_controller,
            armies=armies,
            battlefield=scenario.battlefield_state,
            units=units,
            embarked_unit_ids=(),
        )
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    battlefield = state.battlefield_state
    positions = {
        "source": ((2.4, -0.65), (3.7, -0.65), (2.4, 0.65), (3.7, 0.65), (2.4, 1.95)),
        "support": ((-2.0, 0.0),),
        "leader": ((5.2, 0.0),),
    }
    # This mission's central objective is the linked terrain footprint, whose
    # western corner is (17.586, 34.138), rather than the marker disk. Straddle
    # that edge with a coherent mixed unit: OC0 bodies touch the terrain while
    # the positive-OC attached Leader remains outside the entire footprint.
    origin_x, origin_y = (20.4, 34.15) if primary_mission else (marker.x_inches, marker.y_inches)
    for key in positions:
        if key not in units:
            continue
        placement = battlefield.unit_placement_by_id(units[key].unit_instance_id)
        battlefield = battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model.with_pose(Pose.at(origin_x - x, origin_y + y))
                    for model, (x, y) in zip(
                        placement.model_placements, positions[key], strict=True
                    )
                )
            )
        )
    state.battlefield_state = battlefield
    state.battle_phase_index = state.battle_phase_sequence.index(
        BattlePhase.SHOOTING if primary_mission else BattlePhase.FIGHT
    )
    rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
