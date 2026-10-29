"""20.01 and FAQs40/41: pre-battle cap, cargo, friendship and physical absence."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section18_fixtures import transport_scene
from tests.support.section20_fixtures import reserve_scene
from warhammer40k_core.engine.list_validation import BattleSize
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.reserve_declarations import (
    reserve_declaration_options_for_player,
    reserve_legality_context_for_player,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveUnitPointValue,
    StrategicReserveDeclaration,
)


@pytest.mark.parametrize(
    ("size", "cap"),
    [(BattleSize.INCURSION, 500), (BattleSize.STRIKE_FORCE, 1000), (BattleSize.ONSLAUGHT, 1500)],
)
@pytest.mark.parametrize("excess", [0, 1])
def test_prebattle_half_battle_size_cap_includes_embarked_points(
    section20_definitions: Section02Definitions, size: BattleSize, cap: int, excess: int
) -> None:
    s = transport_scene(section20_definitions)
    state = s.state
    state.army_definitions[:] = [
        replace(
            a,
            battle_size=size,
            roster_legality_report=replace(a.roster_legality_report, battle_size=size),
        )
        for a in state.army_definitions
    ]
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    state.battle_phase_index = None
    state.battlefield_state = None
    config = replace(
        s.session.lifecycle.config,
        reserve_unit_points=(
            ReserveUnitPointValue(
                s.transport.unit_instance_id, cap - 100, "constructed:s20:price:carrier"
            ),
            ReserveUnitPointValue(
                s.passenger.unit_instance_id, 100 + excess, "constructed:s20:price:cargo"
            ),
            ReserveUnitPointValue(
                next(a for a in state.army_definitions if a.player_id == "opponent")
                .units[0]
                .unit_instance_id,
                1,
                "constructed:s20:price:enemy",
            ),
        ),
    )
    context = reserve_legality_context_for_player(state=state, config=config, player_id="owner")
    assert context.strategic_reserves_points_limit == cap
    options = reserve_declaration_options_for_player(
        state=state, config=config, player_id="owner", include_completion=False
    )
    matching = [
        o
        for o in options
        if o.option_id == f"declare_strategic_reserves:{s.transport.unit_instance_id}"
    ]
    assert bool(matching) is (excess == 0)
    assert not any(s.passenger.unit_instance_id == o.option_id.split(":", 1)[-1] for o in options)
    assert not any("enemy" in o.option_id for o in options)
    if matching:
        assert isinstance(matching[0].payload, dict)
        assert matching[0].payload["points_contribution"] == cap
        assert matching[0].payload["embarked_unit_points"] == 100
        assert matching[0].payload["embarked_unit_instance_ids"] == [s.passenger.unit_instance_id]


@pytest.mark.parametrize("case", ["cap", "over-total", "enemy", "fortification"])
def test_declaration_engine_boundary_is_atomic_and_uses_explicit_native_units(
    section20_definitions: Section02Definitions, case: str
) -> None:
    s = reserve_scene(section20_definitions)
    s.state.reserve_states.clear()
    unit = s.unit
    if case == "fortification":
        # Explicit Core keyword contract; native Fortification admission is unproven.
        unit = replace(
            unit,
            own_models=tuple(
                replace(
                    m,
                    keyword_assignment=replace(
                        m.keyword_assignment,
                        keywords=(*m.keyword_assignment.keywords, "FORTIFICATION"),
                    ),
                )
                for m in unit.own_models
            ),
        )
    before = s.state.to_payload()
    if case == "fortification":
        with pytest.raises(GameLifecycleError, match="FORTIFICATIONS"):
            StrategicReserveDeclaration.for_unit(
                unit=unit,
                player_id="owner",
                unit_points=100,
                embarked_unit_points=0,
                points_limit=1000,
            )
    else:
        declarations = [
            StrategicReserveDeclaration.for_unit(
                unit=unit,
                player_id="opponent" if case == "enemy" else "owner",
                unit_points=500,
                embarked_unit_points=0,
                points_limit=1000,
            )
        ]
        if case in {"cap", "over-total"}:
            declarations.append(
                StrategicReserveDeclaration.for_unit(
                    unit=s.enemy,
                    player_id="opponent",
                    unit_points=500,
                    embarked_unit_points=0,
                    points_limit=1000,
                )
            )
        if case == "over-total":
            # Duplicate is an independent invalid input; other cases retain cap checks.
            declarations.append(declarations[0])
        if case in {"enemy", "over-total"}:
            with pytest.raises(GameLifecycleError, match=r"player_id drift|duplicate"):
                s.state.apply_strategic_reserve_declarations(
                    declarations=tuple(declarations),
                    destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
                )
        else:
            rows = s.state.apply_strategic_reserve_declarations(
                declarations=tuple(declarations),
                destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
            )
            assert len(rows) == 2
            assert all(r.points_contribution == 500 for r in rows)
    if case != "cap":
        assert s.state.to_payload() == before


def test_combined_friendly_declarations_include_existing_reserves_and_reject_over_cap(
    section20_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section20_definitions)
    s.state.reserve_states.clear()
    declarations = tuple(
        StrategicReserveDeclaration.for_unit(
            unit=u, player_id="owner", unit_points=p, embarked_unit_points=0, points_limit=1000
        )
        for u, p in ((s.transport, 600), (s.passenger, 401))
    )
    before = s.state.to_payload()
    with pytest.raises(GameLifecycleError, match="exceed the player's points limit"):
        s.state.apply_strategic_reserve_declarations(
            declarations=declarations,
            destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
        )
    assert s.state.to_payload() == before
    s.state.apply_strategic_reserve_declarations(
        declarations=(declarations[0],),
        destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
    )
    with pytest.raises(GameLifecycleError, match="exceed the player's points limit"):
        s.state.apply_strategic_reserve_declarations(
            declarations=(declarations[1],),
            destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
        )
    assert len(s.state.reserve_states) == 1
