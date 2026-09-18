from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.command_points import initial_command_point_ledgers
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.damage_allocation_targets import DamageKind
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.model_destruction_cause_authority import ModelDestructionCauseKind
from warhammer40k_core.engine.model_logical_death import (
    append_damage_application_model_logical_death_event,
)
from warhammer40k_core.engine.phase import GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.model_geometry import ModelGeometry


def destroy_and_remove_order57_model(
    *,
    state: GameState,
    event_log: EventLog,
    model: ModelInstance,
    cause_id: str,
) -> None:
    record_order57_logical_death(
        state=state,
        event_log=event_log,
        model=model,
        cause_id=cause_id,
        placement_retained=False,
        wounds_remaining=0,
        remove=True,
    )


def record_order57_logical_death(
    *,
    state: GameState,
    event_log: EventLog,
    model: ModelInstance,
    cause_id: str,
    placement_retained: bool,
    wounds_remaining: int,
    remove: bool,
) -> None:
    assert state.battlefield_state is not None
    placement = state.battlefield_state.model_placement_by_id(model.model_instance_id)
    current = model_by_id(state=state, model_instance_id=model.model_instance_id)
    starting = current.wounds_remaining
    set_order57_model_wounds(
        state,
        model_instance_id=model.model_instance_id,
        wounds_remaining=wounds_remaining,
    )
    if remove:
        state.battlefield_state = state.battlefield_state.with_removed_models(
            (model.model_instance_id,)
        )
    view = rules_unit_view_by_id(state=state, unit_instance_id=placement.unit_instance_id)
    append_damage_application_model_logical_death_event(
        state=state,
        event_log=event_log,
        cause_id=cause_id,
        cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
        producer_id="producer-order57",
        model_instance_id=model.model_instance_id,
        physical_unit_instance_id=placement.unit_instance_id,
        rules_unit_instance_id=view.unit_instance_id,
        destroyed_model_placement=placement,
        placement_retained=placement_retained,
        damage_application={
            "target_unit_instance_id": view.unit_instance_id,
            "model_instance_id": model.model_instance_id,
            "damage_kind": DamageKind.MORTAL.value,
            "requested_damage": starting,
            "wounds_lost": starting,
            "excess_damage_lost": 0,
            "starting_wounds_remaining": starting,
            "final_wounds_remaining": 0,
            "destroyed": True,
        },
    )


def ordinary_order57_distance(
    *,
    state: GameState,
    source: ModelInstance,
    target: ModelInstance,
) -> float:
    assert state.battlefield_state is not None
    return DistanceMeasurementContext.from_models(
        geometry_model_for_placement(
            model=model_by_id(state=state, model_instance_id=source.model_instance_id),
            placement=state.battlefield_state.model_placement_by_id(source.model_instance_id),
        ),
        geometry_model_for_placement(
            model=model_by_id(state=state, model_instance_id=target.model_instance_id),
            placement=state.battlefield_state.model_placement_by_id(target.model_instance_id),
        ),
    ).closest_distance_inches()


def order57_battle_state() -> tuple[GameState, EventLog]:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order57-battlefield",
        armies=_mustered_armies(),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="order57-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )
    for army in scenario.armies:
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    return state, EventLog()


def set_order57_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        if model.model_instance_id == model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def replace_order57_model_geometry(
    state: GameState,
    *,
    model_instance_id: str,
    geometry: ModelGeometry,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, geometry=geometry)
                        if model.model_instance_id == model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def order57_alpha_unit(state: GameState) -> UnitInstance:
    return _player_unit(state, player_id="player-a")


def order57_beta_unit(state: GameState) -> UnitInstance:
    return _player_unit(state, player_id="player-b")


def order57_alpha_models(state: GameState) -> tuple[ModelInstance, ...]:
    return order57_alpha_unit(state).own_models


def order57_beta_models(state: GameState) -> tuple[ModelInstance, ...]:
    return order57_beta_unit(state).own_models


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=f"{army_id}-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _player_unit(state: GameState, *, player_id: str) -> UnitInstance:
    for army in state.army_definitions:
        if army.player_id == player_id:
            return army.units[0]
    raise AssertionError(f"missing {player_id} unit")
