# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from tests.shared.category_migration.order86_table_quarters import (
    BaseShape,
    CircularBase,
    Fraction,
    Model,
    ModelVolume,
    OvalBase,
    Pose,
    RectangularBase,
    _analytic_quarter_oracle,
    _assert_forged_quarter_witnesses_rejected,
    _exact_rectangle_contact_facing,
    hypot,
    inf,
    nextafter,
    pytest,
    replace,
    scoring_table_quarter_id_or_none,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("side", [-1, 1])
@pytest.mark.parametrize(
    ("gap", "qualifies"),
    [
        (0.0, False),
        (0.01, False),
        pytest.param(0.5 / 25.4, False, id="rounded-nominal-tangency-overlaps"),
        (0.02, True),
    ],
)
def test_quarter_divider_borders(axis: str, side: int, gap: float, qualifies: bool) -> None:
    coordinate = 30.0 + side * (0.5 + gap)
    model = Model(
        "model",
        Pose.at(coordinate, 10.0) if axis == "x" else Pose.at(10.0, coordinate),
        CircularBase(0.5),
        ModelVolume(1.0),
    )
    expected = (
        "table-quarter:south-west"
        if side < 0
        else "table-quarter:south-east"
        if axis == "x"
        else "table-quarter:north-west"
    )
    assert scoring_table_quarter_id_or_none(geometry_models=(model,), center_x=30, center_y=30) == (
        expected if qualifies else None
    )


@pytest.mark.parametrize("leader_gap", [0.01, 0.02])
def test_attached_leader_controls_whole_unit_quarter_in_both_consumers(leader_gap: float) -> None:
    from tests.phase11c_command_phase_helpers import default_unit_selection, unit_selection
    from tests.phase17n_primary_mission_helpers import (
        phase17n_event_setup,
        phase17n_state_with_setup,
    )

    from warhammer40k_core.engine.list_validation import AttachmentDeclaration
    from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
        PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS,
        build_primary_scoring_spatial_evidence,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.secondary_scoring_occupancy import (
        build_secondary_battlefield_occupancy,
    )

    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="reconnaissance",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_b_units=(
            default_unit_selection("body"),
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_b_attachment_declarations=(AttachmentDeclaration("leader", "body"),),
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    view = next(
        v
        for v in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if v.owner_player_id == "player-b"
    )
    assert len(view.component_unit_instance_ids) == 2
    army = state.army_definition_for_player("player-b")
    assert army is not None
    for unit in army.units:
        placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
        radius = unit.own_models[0].geometry.base_shape().max_radius()
        anchor = (
            battlefield.battlefield_width_inches / 2
            - radius
            - (leader_gap if unit.unit_instance_id.endswith(":leader") else 2.0)
        )
        battlefield = battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    replace(p, pose=Pose.at(anchor - i * 1.5, 45))
                    for i, p in enumerate(placement.model_placements)
                )
            )
        )
    state.battlefield_state = battlefield
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    primary = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-b",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )
    secondary = build_secondary_battlefield_occupancy(
        state=state,
        player_id="player-b",
        record=record,
        selection=None,
        model_placements=tuple(
            p
            for army in battlefield.placed_armies
            for unit in army.unit_placements
            for p in unit.model_placements
        ),
    )
    assert len(primary.table_quarter_unit_witnesses) == (0 if leader_gap == 0.01 else 1)
    assert secondary.presence_quarter_ids == (
        () if leader_gap == 0.01 else ("table-quarter:north-west",)
    )
    if leader_gap == 0.02:
        witness = primary.table_quarter_unit_witnesses[0]
        assert witness.rules_unit_instance_id == view.unit_instance_id
        assert witness.model_instance_ids == tuple(
            sorted(m.model_instance_id for m in view.alive_models())
        )


__all__: list[str] = []
__all__ += ["BaseShape", "Fraction", "GameState", "OvalBase", "RectangularBase"]
__all__ += ["_analytic_quarter_oracle", "_assert_forged_quarter_witnesses_rejected"]
__all__ += ["_exact_rectangle_contact_facing", "hypot", "inf", "nextafter"]
