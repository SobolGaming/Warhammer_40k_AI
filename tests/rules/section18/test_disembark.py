"""18.03/18.04/18.06/18.07: actual placement consumers and mode restrictions."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section18_fixtures import AVENGERS, transport_scene
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.ingress_placement_restrictions import restrictions_for_arrival
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import StrategicReserveRule
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    DisembarkResolution,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
    apply_disembark_to_battlefield,
    resolve_disembark,
)
from warhammer40k_core.geometry.pose import Pose

MODES = [
    (DisembarkModeKind.TACTICAL_DISEMBARK, TransportMovementStatus.NOT_MOVED, None),
    (DisembarkModeKind.TACTICAL_DISEMBARK, TransportMovementStatus.REMAIN_STATIONARY, None),
    (DisembarkModeKind.RAPID_DISEMBARK, TransportMovementStatus.NORMAL_MOVE, None),
    (
        DisembarkModeKind.ASSAULT_DISEMBARK,
        TransportMovementStatus.NORMAL_MOVE,
        TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK,
    ),
    (
        DisembarkModeKind.SHOCK_DISEMBARK,
        TransportMovementStatus.ADVANCE,
        TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK,
    ),
    (
        DisembarkModeKind.SHOCK_DISEMBARK,
        TransportMovementStatus.FALL_BACK,
        TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK,
    ),
]


@pytest.mark.parametrize(("mode", "status", "permission"), MODES)
@pytest.mark.parametrize(("delta", "valid"), [(-0.001, True), (0.001, False)])
def test_each_standard_mode_uses_whole_three_inch_setup_and_its_actual_aftermath(
    section18_definitions: Section02Definitions,
    mode: DisembarkModeKind,
    status: TransportMovementStatus,
    permission: TransportRestrictionOverrideKind | None,
    delta: float,
    valid: bool,
) -> None:
    s = transport_scene(section18_definitions)
    # Whole distance: center + passenger radius - transport radius = 3.
    rp = s.passenger.own_models[0].geometry.parts[0].radius_x_inches
    rt = s.transport.own_models[0].geometry.parts[0].radius_x_inches
    overrides = (
        ()
        if permission is None
        else (TransportRestrictionOverride(permission, "constructed:s18:mode-permission"),)
    )
    result = resolve_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=s.selection(
            mode, status, poses=(Pose.at(20 + rt + 3 - rp + delta, 20),), overrides=overrides
        ),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
    )
    assert result.is_valid is valid, result.violations
    assert {v.violation_code.value for v in result.violations} == (
        set() if valid else {"disembark_distance"}
    )
    if valid:
        assert result.updated_cargo_state is not None
        assert result.updated_cargo_state.embarked_unit_instance_ids == ()
        outcome = result.disembarked_unit_state
        assert outcome is not None
        assert outcome.can_move_further is (mode is DisembarkModeKind.TACTICAL_DISEMBARK)
        assert outcome.can_declare_charge is (
            mode in {DisembarkModeKind.TACTICAL_DISEMBARK, DisembarkModeKind.ASSAULT_DISEMBARK}
        )
        assert not outcome.can_choose_remain_stationary
        assert outcome.battle_shocked_until is None
        after = apply_disembark_to_battlefield(
            battlefield_state=s.scenario.battlefield_state, disembark=result
        )
        assert (
            after.unit_placement_by_id(s.passenger.unit_instance_id)
            == result.selection.attempted_placement
        )
        assert result.transition_batch is not None
        assert {r.placement_kind for r in result.transition_batch.placements} == {
            BattlefieldPlacementKind.DISEMBARK
        }
        assert DisembarkResolution.from_payload(result.to_payload()) == result
    else:
        assert result.disembarked_unit_state is None
        assert result.updated_cargo_state is None
        assert result.transition_batch is None


@pytest.mark.parametrize(("mode", "status", "permission"), MODES)
def test_no_standard_mode_can_disembark_cargo_embarked_this_phase(
    section18_definitions: Section02Definitions,
    mode: DisembarkModeKind,
    status: TransportMovementStatus,
    permission: TransportRestrictionOverrideKind | None,
) -> None:
    s = transport_scene(section18_definitions)
    # Distinguish new cargo this phase from the default next-phase snapshot.
    cargo = replace(s.cargo, phase_battle_round=1, started_phase_embarked_unit_instance_ids=())
    overrides = (
        ()
        if permission is None
        else (TransportRestrictionOverride(permission, "constructed:s18:permission"),)
    )
    result = resolve_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=cargo,
        selection=s.selection(mode, status, overrides=overrides),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
    )
    assert not result.is_valid
    assert {v.violation_code.value for v in result.violations} == {
        "unit_did_not_start_phase_embarked"
    }
    assert result.updated_cargo_state is None
    assert result.transition_batch is None


@pytest.mark.parametrize(
    ("mode", "status"),
    [
        (DisembarkModeKind.TACTICAL_DISEMBARK, TransportMovementStatus.NORMAL_MOVE),
        (DisembarkModeKind.TACTICAL_DISEMBARK, TransportMovementStatus.ADVANCE),
        (DisembarkModeKind.TACTICAL_DISEMBARK, TransportMovementStatus.FALL_BACK),
        (DisembarkModeKind.RAPID_DISEMBARK, TransportMovementStatus.NOT_MOVED),
        (DisembarkModeKind.RAPID_DISEMBARK, TransportMovementStatus.ADVANCE),
        (DisembarkModeKind.RAPID_DISEMBARK, TransportMovementStatus.FALL_BACK),
        (DisembarkModeKind.ASSAULT_DISEMBARK, TransportMovementStatus.ADVANCE),
        (DisembarkModeKind.ASSAULT_DISEMBARK, TransportMovementStatus.FALL_BACK),
    ],
)
def test_source_mode_order_and_advance_fall_back_exclusions_reject_wrong_pairs(
    section18_definitions: Section02Definitions,
    mode: DisembarkModeKind,
    status: TransportMovementStatus,
) -> None:
    s = transport_scene(section18_definitions)
    with pytest.raises(GameLifecycleError, match="Disembark"):
        s.selection(mode, status)


@pytest.mark.parametrize(
    ("mode", "permission_code"),
    [
        (DisembarkModeKind.ASSAULT_DISEMBARK, "assault_disembark_permission_required"),
        (DisembarkModeKind.SHOCK_DISEMBARK, "shock_disembark_permission_required"),
    ],
)
def test_special_modes_require_a_separate_permitting_rule(
    section18_definitions: Section02Definitions,
    mode: DisembarkModeKind,
    permission_code: str,
) -> None:
    s = transport_scene(section18_definitions)
    result = resolve_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=s.selection(mode),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
    )
    assert not result.is_valid
    assert {v.violation_code.value for v in result.violations} == {permission_code}
    assert result.updated_cargo_state is None
    assert result.transition_batch is None


@pytest.mark.parametrize(
    "fault",
    ["carrier-off-board", "not-cargo", "overlap", "outside", "partial", "coherency", "engaged"],
)
def test_setup_keeps_transport_presence_cargo_entire_unit_coherency_and_unengaged_requirements(
    section18_definitions: Section02Definitions,
    fault: str,
) -> None:
    multi = fault in {"partial", "coherency"}
    s = transport_scene(
        section18_definitions,
        passenger_sheet=AVENGERS if multi else "000004193",
        enemy_poses=(Pose.at(25, 20),) if fault == "engaged" else (Pose.at(50, 35),),
    )
    selection = s.selection(
        poses=(
            Pose.at(22, 18),
            Pose.at(23.3, 18.5),
            Pose.at(23.5, 20),
            Pose.at(23.3, 21.5),
            Pose.at(22, 22),
        )
        if multi
        else None
    )
    scene, cargo = s.scenario, s.cargo
    expected = {
        "carrier-off-board": "transport_placement_drift",
        "not-cargo": "unit_not_embarked",
        "overlap": "model_overlap",
        "outside": "battlefield_edge_crossed",
        "partial": "unit_placement_drift",
        "coherency": "unit_coherency_broken",
        "engaged": "enemy_engagement_range",
    }[fault]
    if fault == "carrier-off-board":
        scene = replace(
            scene,
            battlefield_state=scene.battlefield_state.without_unit_placement(
                s.transport.unit_instance_id
            ),
        )
    elif fault == "not-cargo":
        cargo = replace(cargo, embarked_unit_instance_ids=())
    elif fault == "overlap":
        selection = replace(
            selection, attempted_placement=placement(s.passenger, (Pose.at(20, 20),))
        )
    elif fault == "outside":
        selection = replace(
            selection, attempted_placement=placement(s.passenger, (Pose.at(-1, 20),))
        )
    elif fault == "partial":
        selection = replace(
            selection,
            attempted_placement=replace(
                selection.attempted_placement,
                model_placements=selection.attempted_placement.model_placements[:-1],
            ),
        )
    elif fault == "coherency":
        points = selection.attempted_placement.model_placements
        selection = replace(
            selection,
            attempted_placement=replace(
                selection.attempted_placement,
                model_placements=(*points[:-1], replace(points[-1], pose=Pose.at(17, 20))),
            ),
        )
    result = resolve_disembark(
        scenario=scene,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=cargo,
        selection=selection,
        unit=s.passenger,
        transport_placement=s.carrier_placement,
    )
    assert not result.is_valid
    assert expected in {v.violation_code.value for v in result.violations}, result.violations
    assert result.updated_cargo_state is None
    assert result.disembarked_unit_state is None
    assert result.transition_batch is None


@pytest.mark.parametrize("fault", ["none", "enemy-distance", "enemy-zone", "edge-distance"])
def test_rapid_nested_clarification_inherits_ingress_enemy_distance_zone_and_edge_rules(
    section18_definitions: Section02Definitions,
    fault: str,
) -> None:
    s = transport_scene(
        section18_definitions,
        enemy_poses=(Pose.at(29, 20),) if fault == "enemy-distance" else (Pose.at(50, 35),),
    )
    rules = restrictions_for_arrival(
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        battle_round=2,
        strategic_rule=StrategicReserveRule(
            edge_distance_inches=3 if fault == "edge-distance" else 30,
            enemy_horizontal_distance_inches=8,
        ),
        deep_strike_enemy_distance=None,
        source_restrictions=(),
        distance_grants=(),
    )
    zones = (
        (
            DeploymentZone.rectangle(
                "constructed:s18:enemy-zone", "opponent", min_x=22, min_y=19, max_x=28, max_y=25
            ),
        )
        if fault == "enemy-zone"
        else ()
    )
    result = resolve_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=s.selection(
            DisembarkModeKind.RAPID_DISEMBARK, TransportMovementStatus.INGRESS_MOVE
        ),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
        ingress_restrictions=rules,
        enemy_deployment_zones=zones,
        deployment_zones=zones,
    )
    assert result.is_valid is (fault == "none"), result.violations
    if fault != "none":
        assert "rapid_disembark_ingress_restriction" in {
            v.violation_code.value for v in result.violations
        }
        assert result.updated_cargo_state is None
        assert result.transition_batch is None
