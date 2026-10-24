"""03.02.02: explicit oversized geometry and in-turn restriction contracts."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import MAULERFIEND, Section02Definitions
from tests.support.section03_fixtures import native_state
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.large_model_deployment_restrictions import (
    record_conditional_deployment_restriction,
)
from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
from warhammer40k_core.engine.large_model_setup import oversized_deployment_violation
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    ("zone_width", "x", "code"),
    [
        (3, 4, None),
        (3, 4.01, "large_model_edge_contact_missing"),
        (9, 4, "deployment_zone_violation"),
    ],
)
def test_constructed_oversize_must_be_impossible_and_touch_owned_edge(
    section03_setup_mission: MissionSetup, zone_width: float, x: float, code: str | None
) -> None:
    model = Model("constructed-8-inch-base", Pose.at(x, 15), CircularBase(radius=4), ModelVolume(6))
    zone = DeploymentZone.rectangle("narrow", "owner", min_x=0, min_y=0, max_x=zone_width, max_y=44)
    assert (
        oversized_deployment_violation(
            model=model, zones=(zone,), mission=section03_setup_mission, player_id="owner"
        )
        == code
    )
    if code is None:
        assert (
            oversized_deployment_violation(
                model=model,
                zones=(replace(zone, player_id="opponent"),),
                mission=section03_setup_mission,
                player_id="opponent",
            )
            == "large_model_edge_contact_missing"
        )


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
@pytest.mark.parametrize(
    "activity",
    [
        "normal",
        "advance",
        "fall_back",
        "charge",
        "ranged_attacks",
        "remain_stationary",
        "pile_in",
        "consolidate",
        "melee_attacks",
    ],
)
def test_constructed_qualifying_deployment_locks_only_source_activities_for_actual_turn(
    section03_definitions: Section02Definitions, turn_player: str, activity: str
) -> None:
    # Explicit production seam contract: qualifying oversized condition is supplied,
    # not claimed as an authentic in-turn oversized Maulerfiend deployment.
    unit = section03_definitions.unit(MAULERFIEND)
    state = native_state(section03_definitions, unit)
    state.active_player_id = turn_player
    effect = record_conditional_deployment_restriction(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        qualifying_model_instance_ids=unit.own_model_ids(),
        setup_occasion_id="constructed-qualified-condition",
    )
    assert effect is not None
    restricted = activity in {"normal", "advance", "fall_back", "charge", "ranged_attacks"}
    assert (
        large_model_activity_reason(state, unit.unit_instance_id, activity) is not None
    ) is restricted
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(
            battle_round=1, player_id="opponent" if turn_player == "owner" else "owner"
        )
    )
    assert (
        large_model_activity_reason(state, unit.unit_instance_id, activity) is not None
    ) is restricted
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=1, player_id=turn_player)
    )
    assert large_model_activity_reason(state, unit.unit_instance_id, activity) is None
