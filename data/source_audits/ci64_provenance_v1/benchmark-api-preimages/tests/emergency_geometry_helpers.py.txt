"""Real destroyed-Transport decisions for Emergency Set Up geometry regressions."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.order60_emergency_disembark_helpers import emergency_disembark_contact_poses
from tests.phase13b_shooting_declaration_helpers import (
    _apply_shooting_declaration_without_advancing,
    _attached_enemy_declarations,
    _attached_enemy_unit_specs,
    _catalog_with_extra_bolt_profile,
    _decision_request,
    _destroyed_transport_hazard_roll_results_for_test,
    _fixed_roll_result,
    _proposal_from_request,
    _ruleset,
    _select_shooting_unit_and_type,
    _shooting_lifecycle,
    _state,
    _unit_placement_at,
    _weapon_profile_by_wargear,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.attack_sequence import resolve_attack_sequence_until_blocked
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition


def emergency_geometry_session(
    *, attached: bool, rectangular: bool
) -> tuple[LocalGameSession, PlacementProposalPayload]:
    profile = replace(
        _weapon_profile_by_wargear(
            wargear_id="core-bolt-rifle", weapon_profile_id="core-bolt-rifle:standard"
        ),
        profile_id="emergency-geometry-rifle",
        name="Emergency geometry rifle",
        attack_profile=AttackProfile.fixed(1),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        damage_profile=DamageProfile.fixed(20),
        keywords=(),
        abilities=(),
    )
    catalog = _catalog_with_extra_bolt_profile(profile)
    if rectangular:
        sheet = catalog.datasheet_by_id("core-transport")
        sheet = replace(
            sheet,
            model_profiles=tuple(
                replace(
                    model, base_size=BaseSizeDefinition.rectangular(length_mm=100, width_mm=260)
                )
                for model in sheet.model_profiles
            ),
        )
        catalog = replace(
            catalog,
            datasheets=tuple(
                sheet if row.datasheet_id == sheet.datasheet_id else row
                for row in catalog.datasheets
            ),
        )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="emergency-geometry",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            *(
                _attached_enemy_unit_specs()[:2]
                if attached
                else (
                    (
                        "enemy-passenger",
                        "core-intercessor-like-infantry",
                        "core-intercessor-like",
                        5,
                    ),
                )
            ),
        ),
        enemy_attachment_declarations=_attached_enemy_declarations()[:1] if attached else (),
        catalog=catalog,
    )
    state = _state(lifecycle)
    transport = units["enemy-transport"]
    passengers = (
        (units["bodyguard-unit"], units["leader-unit"]) if attached else (units["enemy-passenger"],)
    )
    passenger_ids = tuple(sorted(unit.unit_instance_id for unit in passengers))
    battlefield = state.battlefield_state
    assert battlefield is not None
    for unit in passengers:
        battlefield = battlefield.without_unit_placement(unit.unit_instance_id)
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        display_template_id="emergency-floor",
        center_x_inches=35,
        center_y_inches=35,
        width_inches=20,
        depth_inches=16,
    )
    feature = TerrainFeatureDefinition(
        feature_id="emergency-floor",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=35,
        footprint_center_y_inches=35,
        footprint_width_inches=20,
        footprint_depth_inches=16,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="supported-floor",
                center_x_inches=35,
                center_y_inches=35,
                bottom_z_inches=6,
                width_inches=20,
                depth_inches=16,
                thickness_inches=0.5,
            ),
        ),
    )
    state.battlefield_state = replace(battlefield, terrain_features=(feature,))
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=passenger_ids,
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=passenger_ids,
        )
    )
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions), unit_instance_id=passenger_ids[0]
    )
    models = view.alive_models()
    poses = (
        tuple(
            Pose.at(
                35 + 50 / 25.4 + model.geometry.base_shape().max_radius() + 0.02,
                35 + 1.6 * (i - (len(models) - 1) / 2),
            )
            for i, model in enumerate(models)
        )
        if rectangular
        else emergency_disembark_contact_poses(models, center_x=35, center_y=35)
    )
    by_id = {model.model_instance_id: pose for model, pose in zip(models, poses, strict=True)}
    components = tuple(
        _unit_placement_at(
            unit,
            army_id="army-beta",
            player_id="player-b",
            poses=tuple(by_id[model.model_instance_id] for model in unit.own_models),
        )
        for unit in passengers
    )
    placement = RulesUnitPlacement(
        rules_unit_instance_id=view.unit_instance_id, component_unit_placements=components
    )
    selection = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="select-shooter",
    )
    sequence = _apply_shooting_declaration_without_advancing(
        lifecycle,
        request=declaration,
        proposal=_proposal_from_request(
            request=declaration,
            target_unit_id=transport.unit_instance_id,
            weapon_profile_id=profile.profile_id,
        ),
        result_id="declare-shooting",
    )
    context_id = f"{sequence.sequence_id}:pool-001:attack-001"
    hit = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {profile.profile_id} attack {context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {profile.profile_id} attack {context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=transport.own_models[0].model_instance_id,
        attack_context_id=context_id,
    )
    remaining_sequence, allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "emergency-geometry",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="hit", spec=hit, value=6),
                _fixed_roll_result(roll_id="wound", spec=wound, value=6),
                _fixed_roll_result(roll_id="save", spec=save, value=1),
                *(
                    roll
                    for component in components
                    for roll in _destroyed_transport_hazard_roll_results_for_test(
                        component,
                        values=tuple(6 for _ in component.model_placements),
                        roll_id_prefix=component.unit_instance_id,
                    )
                ),
            ),
        ),
    )
    phase = state.shooting_phase_state
    assert phase is not None
    state.replace_shooting_phase_state(
        phase.with_attack_sequence_update(
            attack_sequence=remaining_sequence, allocated_model_ids_this_phase=allocated
        )
    )
    request = MovementProposalRequest.from_decision_request_payload(
        _decision_request(cast(LifecycleStatus, status)).payload
    )
    proposal = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        unit_instance_id=view.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=None if attached else components[0],
        attempted_rules_unit_placement=placement if attached else None,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    return LocalGameSession(lifecycle=lifecycle), proposal
