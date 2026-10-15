from __future__ import annotations

from tests.shared.category_migration.order54_setup import (
    BattlefieldEdge,
    BattlefieldPlacementKind,
    BattlefieldScenario,
    BattlePhase,
    ChargePhaseState,
    GameLifecycleError,
    LargeModelReservePlacementException,
    MovementMode,
    PathWitness,
    Pose,
    ReactionWindow,
    ReactionWindowKind,
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
    apply_reinforcement_placement_to_battlefield,
    battle_state_with_reserve,
    charge_unit_ineligibility_reason,
    large_model_activity_reason,
    pytest,
    replace,
    resolve_normal_move,
    resolve_reserve_arrival,
    rules_unit_view_by_id,
    shooting_state_restriction_reason,
    single_model_reserve_placement,
    with_unit_keywords,
)


def test_oversized_strip_proof_considers_rotation_and_full_battlefield_extent() -> None:
    from warhammer40k_core.engine.large_model_setup import base_fits_edge_band
    from warhammer40k_core.geometry.base import OvalBase, RectangularBase
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    for base in (OvalBase(8, 2), RectangularBase(8, 2)):
        model = Model(
            model_id="rotatable",
            pose=Pose.at(4, 4, facing_degrees=90),
            base=base,
            volume=ModelVolume(height=2),
        )
        assert base_fits_edge_band(
            model,
            edge=BattlefieldEdge.SOUTH,
            distance_inches=3,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
        )
        assert not base_fits_edge_band(
            model,
            edge=BattlefieldEdge.SOUTH,
            distance_inches=3,
            battlefield_width_inches=1,
            battlefield_depth_inches=44,
        )


@pytest.mark.parametrize(
    ("edge", "x", "y", "valid"),
    [
        ("north_west_corner", 200 / 25.4 / 2, 30.0, True),
        ("north_west_corner", 15.0, 44 - 200 / 25.4 / 2, True),
        ("north_west_corner", 60 - 200 / 25.4 / 2, 30.0, False),
    ],
)
def test_oversized_deployment_source_corner_has_two_own_edges(
    edge: str,
    x: float,
    y: float,
    valid: bool,
) -> None:
    from tests.large_model_setup_helpers import oversized_deployment_case
    from warhammer40k_core.engine.deployment import resolve_deployment_placement

    state, request, proposal = oversized_deployment_case(x=x)
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        attacker_battlefield_edge=edge,
        defender_battlefield_edge="south_east_corner",
    )
    proposal = replace(
        proposal,
        model_placements=tuple(replace(p, pose=Pose.at(x, y)) for p in proposal.model_placements),
    )
    result = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
    )
    assert result.is_valid is valid


__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldPlacementKind", "BattlefieldScenario", "ChargePhaseState"]
__all__ += ["GameLifecycleError", "LargeModelReservePlacementException", "MovementMode"]
__all__ += ["PathWitness", "ReactionWindow", "ReactionWindowKind", "TriggeredMovementDescriptor"]
__all__ += ["TriggeredMovementHandler", "TriggeredMovementKind"]
__all__ += ["apply_reinforcement_placement_to_battlefield", "battle_state_with_reserve"]
__all__ += ["charge_unit_ineligibility_reason", "large_model_activity_reason"]
__all__ += ["resolve_normal_move", "resolve_reserve_arrival", "rules_unit_view_by_id"]
__all__ += ["shooting_state_restriction_reason", "single_model_reserve_placement"]
__all__ += ["with_unit_keywords"]
