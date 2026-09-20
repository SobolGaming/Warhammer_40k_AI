from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.reserve_arrival_requirements import reposition_destruction_policy
from warhammer40k_core.engine.reserves import (
    AircraftReserveDeclaration,
    ReserveOrigin,
    ReserveState,
)
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_aircraft_2026_09 import (
    DEPLOYMENT_SOURCE_ID,
)


def apply_mandatory_aircraft_reserve_declarations(
    *,
    state: GameState,
    config: GameConfig,
    decisions: DecisionController,
) -> tuple[ReserveState, ...]:
    from warhammer40k_core.engine.reserve_declarations import (
        _cargo_unit_ids_for_transport,  # pyright: ignore[reportPrivateUsage]
        _embarked_points_for_unit_ids,  # pyright: ignore[reportPrivateUsage]
        _points_for_rules_unit,  # pyright: ignore[reportPrivateUsage]
        reserve_legality_context_for_player,
    )

    if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        raise GameLifecycleError("Aircraft reserve declarations require DECLARE_BATTLE_FORMATIONS.")
    policy = reposition_destruction_policy(
        mission_setup=state.mission_setup,
        destruction_deadline_policy=None,
    )
    recorded: list[ReserveState] = []
    for army in state.army_definitions:
        context = reserve_legality_context_for_player(
            state=state,
            config=config,
            player_id=army.player_id,
        )
        current_points = context.current_strategic_reserves_points
        for unit in rules_unit_views_from_armies(armies=(army,)):
            if "AIRCRAFT" not in unit.keywords:
                continue
            if state.reserve_state_for_unit(unit.unit_instance_id) is not None:
                continue
            points = _points_for_rules_unit(context=context, view=unit)
            cargo = tuple(
                sorted(
                    {
                        cargo_id
                        for component_id in unit.component_unit_instance_ids
                        for cargo_id in _cargo_unit_ids_for_transport(
                            state=state, transport_unit_id=component_id
                        )
                    }
                )
            )
            cargo_points = _embarked_points_for_unit_ids(context=context, unit_instance_ids=cargo)
            if points is None or cargo_points is None:
                raise GameLifecycleError(
                    "Aircraft reserve declaration requires source-backed unit points."
                )
            total_points = sum(point.points for point in points) + cargo_points
            if current_points + total_points > context.strategic_reserves_points_limit:
                raise GameLifecycleError(
                    "Aircraft reserve declarations exceed the player's points limit."
                )
            declaration = AircraftReserveDeclaration(
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                reserve_origin=ReserveOrigin.AIRCRAFT_MANDATORY_RESERVE,
                declared_during_step=SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                source_rule_id=DEPLOYMENT_SOURCE_ID,
                unit_points=total_points,
                points_limit=context.strategic_reserves_points_limit,
                has_aircraft_keyword=True,
            )
            reserve_state = replace(
                declaration.to_reserve_state(destruction_deadline_policy=policy),
                embarked_unit_instance_ids=cargo,
            )
            state.record_reserve_state(reserve_state)
            current_points += total_points
            recorded.append(reserve_state)
            decisions.event_log.append(
                "aircraft_reserve_declared",
                {
                    "game_id": state.game_id,
                    "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    "player_id": army.player_id,
                    "secret": True,
                    "visibility_source": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    "unit_instance_id": unit.unit_instance_id,
                    "declaration": declaration.to_payload(),
                    "reserve_state": reserve_state.to_payload(),
                    "source_id": DEPLOYMENT_SOURCE_ID,
                },
            )
    return tuple(sorted(recorded, key=lambda item: item.unit_instance_id))
