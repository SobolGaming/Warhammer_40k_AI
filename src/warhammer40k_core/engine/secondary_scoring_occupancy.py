from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from warhammer40k_core.core.battlefield_regions import BattlefieldRegion, BattlefieldRegionKind
from warhammer40k_core.core.objectives import DEFAULT_OBJECTIVE_CONTROL_HORIZONTAL_INCHES
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_persisted_lineage import (
    frozen_component_lineage_from_departures,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    TABLE_QUARTER_IDS,
    TABLE_QUARTER_NORTH_EAST,
    TABLE_QUARTER_NORTH_WEST,
    TABLE_QUARTER_SOUTH_EAST,
    TABLE_QUARTER_SOUTH_WEST,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_is_battle_shocked,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection

_validate_identifier = IdentifierValidator(GameLifecycleError)
_CENTER_THREE_INCHES = 3.0
_CENTER_SIX_INCHES = 6.0
_EDGE_SIX_INCHES = 6.0
_AIRCRAFT_KEYWORD = "AIRCRAFT"
_EDGE_WEST = "west"
_EDGE_EAST = "east"
_EDGE_SOUTH = "south"
_EDGE_NORTH = "north"
_OPPOSITE_EDGE_PAIRS = frozenset(
    {
        frozenset({_EDGE_WEST, _EDGE_EAST}),
        frozenset({_EDGE_SOUTH, _EDGE_NORTH}),
    }
)


class _Footprint(Protocol):
    def covers(self, other: object) -> bool: ...

    def intersects(self, other: object) -> bool: ...


@dataclass(frozen=True, slots=True)
class SecondaryCharacterModel:
    model_instance_id: str
    unit_instance_id: str
    owner_player_id: str
    starting_wounds: int
    wounds_remaining: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("character model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("character unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("character owner_player_id", self.owner_player_id),
        )
        if type(self.starting_wounds) is not int or self.starting_wounds <= 0:
            raise GameLifecycleError("character starting_wounds must be a positive int.")
        if type(self.wounds_remaining) is not int or self.wounds_remaining < 0:
            raise GameLifecycleError("character wounds_remaining must be a non-negative int.")


@dataclass(frozen=True, slots=True)
class SecondaryBattlefieldOccupancy:
    player_id: str
    presence_quarter_ids: tuple[str, ...]
    friendly_within_three_of_center_unit_ids: tuple[str, ...]
    enemy_within_three_of_center_unit_ids: tuple[str, ...]
    enemy_within_six_of_center_unit_ids: tuple[str, ...]
    friendly_wholly_within_no_mans_land_unit_ids: tuple[str, ...]
    enemy_wholly_within_no_mans_land_unit_ids: tuple[str, ...]
    friendly_wholly_within_opponent_deployment_zone_unit_ids: tuple[str, ...]
    friendly_near_edge_unit_ids: tuple[str, ...]
    friendly_near_edge_outside_own_territory_unit_ids: tuple[str, ...]
    opposite_edge_unit_ids: tuple[str, ...]
    beacon_on_battlefield: bool
    beacon_within_own_deployment_zone: bool
    beacon_within_own_territory: bool
    guarded_objective_ids: tuple[str, ...]
    tempting_objective_id: str | None
    enemy_character_models: tuple[SecondaryCharacterModel, ...]
    own_territory_resolved: bool
    own_deployment_resolved: bool
    opponent_deployment_resolved: bool
    no_mans_land_resolved: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "presence_quarter_ids",
            _validate_identifier_tuple("presence_quarter_ids", self.presence_quarter_ids),
        )
        if any(quarter_id not in TABLE_QUARTER_IDS for quarter_id in self.presence_quarter_ids):
            raise GameLifecycleError("presence_quarter_ids contains an unsupported quarter.")
        for field_name, value in (
            ("own_territory_resolved", self.own_territory_resolved),
            ("own_deployment_resolved", self.own_deployment_resolved),
            ("opponent_deployment_resolved", self.opponent_deployment_resolved),
            ("no_mans_land_resolved", self.no_mans_land_resolved),
        ):
            if type(value) is not bool:
                raise GameLifecycleError(f"{field_name} must be a bool.")


def build_secondary_battlefield_occupancy(
    *,
    state: GameState,
    player_id: str,
    record: ObjectiveControlRecord,
    selection: SecondaryMissionSelection | None,
    model_placements: tuple[ModelPlacement, ...],
) -> SecondaryBattlefieldOccupancy:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Secondary occupancy requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Secondary occupancy requires an ObjectiveControlRecord.")
    requested_player = _validate_identifier("player_id", player_id)
    if requested_player not in state.player_ids:
        raise GameLifecycleError("Secondary occupancy player_id is not in this game.")
    mission_setup = state.mission_setup
    battlefield_state = state.battlefield_state
    if mission_setup is None or battlefield_state is None:
        raise GameLifecycleError("Secondary occupancy requires mission and battlefield state.")
    own_role = _owner_role(mission_setup=mission_setup, player_id=requested_player)
    opponent_role = "defender" if own_role == "attacker" else "attacker"
    own_territory = _optional_single_region(
        mission_setup.battlefield_regions,
        kind=BattlefieldRegionKind.TERRITORY,
        owner_role=own_role,
    )
    opponent_deployment = _optional_single_region(
        mission_setup.battlefield_regions,
        kind=BattlefieldRegionKind.DEPLOYMENT_ZONE,
        owner_role=opponent_role,
    )
    own_deployment = _optional_single_region(
        mission_setup.battlefield_regions,
        kind=BattlefieldRegionKind.DEPLOYMENT_ZONE,
        owner_role=own_role,
    )
    no_mans_land = _optional_single_region(
        mission_setup.battlefield_regions,
        kind=BattlefieldRegionKind.NO_MANS_LAND,
        owner_role=None,
    )
    own_territory_footprint = None if own_territory is None else _region_footprint(own_territory)
    opponent_deployment_footprint = (
        None if opponent_deployment is None else _region_footprint(opponent_deployment)
    )
    own_deployment_footprint = None if own_deployment is None else _region_footprint(own_deployment)
    no_mans_land_footprint = None if no_mans_land is None else _region_footprint(no_mans_land)
    placement_by_model_id = {
        placement.model_instance_id: placement for placement in model_placements
    }
    embarked_unit_ids = _embarked_unit_ids(state)
    views = rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    placed_units = tuple(
        resolved
        for view in views
        if (
            resolved := _placed_rules_unit_or_none(
                view=view,
                battlefield_state=battlefield_state,
                placement_by_model_id=placement_by_model_id,
                embarked_unit_ids=embarked_unit_ids,
            )
        )
        is not None
    )
    width = battlefield_state.battlefield_width_inches
    depth = battlefield_state.battlefield_depth_inches
    center_x = width / 2.0
    center_y = depth / 2.0
    presence_quarter_ids: list[str] = []
    friendly_center_three: list[str] = []
    enemy_center_three: list[str] = []
    enemy_center_six: list[str] = []
    friendly_nml: list[str] = []
    enemy_nml: list[str] = []
    friendly_opponent_dz: list[str] = []
    near_edge: list[str] = []
    near_edge_outside_territory: list[str] = []
    edge_by_unit: dict[str, frozenset[str]] = {}
    for view, placements in placed_units:
        geometry_models = _geometry_models(view=view, placements=placements)
        unit_id = view.unit_instance_id
        owner_id = view.owner_player_id
        eligible = _eligible_scoring_unit(state=state, view=view)
        wholly_nml = no_mans_land_footprint is not None and _wholly_within(
            geometry_models,
            no_mans_land_footprint,
        )
        if owner_id == requested_player and eligible:
            quarter_id = _table_quarter_id_or_none(
                geometry_models=geometry_models,
                center_x=center_x,
                center_y=center_y,
            )
            if quarter_id is not None:
                presence_quarter_ids.append(quarter_id)
            if _within_distance_of_point(
                geometry_models,
                x=center_x,
                y=center_y,
                inches=_CENTER_THREE_INCHES,
            ):
                friendly_center_three.append(unit_id)
            if wholly_nml:
                friendly_nml.append(unit_id)
            if opponent_deployment_footprint is not None and _wholly_within(
                geometry_models,
                opponent_deployment_footprint,
            ):
                friendly_opponent_dz.append(unit_id)
            edges = _near_edges(
                geometry_models,
                width=width,
                depth=depth,
            )
            if edges:
                near_edge.append(unit_id)
                edge_by_unit[unit_id] = edges
                if own_territory_footprint is not None and not _intersects_region(
                    geometry_models,
                    own_territory_footprint,
                ):
                    near_edge_outside_territory.append(unit_id)
        elif owner_id != requested_player:
            if _within_distance_of_point(
                geometry_models,
                x=center_x,
                y=center_y,
                inches=_CENTER_THREE_INCHES,
            ):
                enemy_center_three.append(unit_id)
            if _within_distance_of_point(
                geometry_models,
                x=center_x,
                y=center_y,
                inches=_CENTER_SIX_INCHES,
            ):
                enemy_center_six.append(unit_id)
            if eligible and wholly_nml:
                enemy_nml.append(unit_id)
    opposite_ids = _opposite_edge_unit_ids(
        edge_by_unit=edge_by_unit,
        outside_territory_unit_ids=frozenset(near_edge_outside_territory),
    )
    beacon_on_battlefield = False
    beacon_within_own_dz = False
    beacon_within_own_territory = False
    if selection is not None and selection.beacon_unit_instance_id is not None:
        beacon_ids = _beacon_current_unit_ids(
            state=state,
            historical_unit_instance_id=selection.beacon_unit_instance_id,
        )
        beacon_matches = tuple(
            (view, placements)
            for view, placements in placed_units
            if view.unit_instance_id in beacon_ids or _shares_component(view, beacon_ids)
        )
        beacon_on_battlefield = bool(beacon_matches)
        if beacon_on_battlefield:
            geometry_models = tuple(
                model
                for view, placements in beacon_matches
                for model in _geometry_models(view=view, placements=placements)
            )
            beacon_within_own_dz = own_deployment_footprint is not None and _intersects_region(
                geometry_models, own_deployment_footprint
            )
            beacon_within_own_territory = (
                own_territory_footprint is not None
                and _intersects_region(geometry_models, own_territory_footprint)
            )
    guarded_ids = _guarded_objective_ids(
        state=state,
        record=record,
        player_id=requested_player,
        selection=selection,
        placed_units=placed_units,
        mission_objective_ids=tuple(
            marker.objective_marker_id for marker in mission_setup.objective_markers
        ),
    )
    return SecondaryBattlefieldOccupancy(
        player_id=requested_player,
        presence_quarter_ids=tuple(sorted(set(presence_quarter_ids))),
        friendly_within_three_of_center_unit_ids=tuple(sorted(set(friendly_center_three))),
        enemy_within_three_of_center_unit_ids=tuple(sorted(set(enemy_center_three))),
        enemy_within_six_of_center_unit_ids=tuple(sorted(set(enemy_center_six))),
        friendly_wholly_within_no_mans_land_unit_ids=tuple(sorted(set(friendly_nml))),
        enemy_wholly_within_no_mans_land_unit_ids=tuple(sorted(set(enemy_nml))),
        friendly_wholly_within_opponent_deployment_zone_unit_ids=tuple(
            sorted(set(friendly_opponent_dz))
        ),
        friendly_near_edge_unit_ids=tuple(sorted(set(near_edge))),
        friendly_near_edge_outside_own_territory_unit_ids=tuple(
            sorted(set(near_edge_outside_territory))
        ),
        opposite_edge_unit_ids=opposite_ids,
        beacon_on_battlefield=beacon_on_battlefield,
        beacon_within_own_deployment_zone=beacon_within_own_dz,
        beacon_within_own_territory=beacon_within_own_territory,
        guarded_objective_ids=guarded_ids,
        tempting_objective_id=(None if selection is None else selection.tempting_objective_id),
        enemy_character_models=_enemy_character_models(state=state, player_id=requested_player),
        own_territory_resolved=own_territory is not None,
        own_deployment_resolved=own_deployment is not None,
        opponent_deployment_resolved=opponent_deployment is not None,
        no_mans_land_resolved=no_mans_land is not None,
    )


def _enemy_character_models(
    *,
    state: GameState,
    player_id: str,
) -> tuple[SecondaryCharacterModel, ...]:
    models: list[SecondaryCharacterModel] = []
    for army in state.army_definitions:
        if army.player_id == player_id:
            continue
        for unit in army.units:
            if not unit_has_keyword(unit, "CHARACTER"):
                continue
            for model in unit.own_models:
                models.append(
                    SecondaryCharacterModel(
                        model_instance_id=model.model_instance_id,
                        unit_instance_id=unit.unit_instance_id,
                        owner_player_id=army.player_id,
                        starting_wounds=model.starting_wounds,
                        wounds_remaining=model.wounds_remaining,
                    )
                )
    return tuple(
        sorted(
            models,
            key=lambda model: (model.unit_instance_id, model.model_instance_id),
        )
    )


def _guarded_objective_ids(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    player_id: str,
    selection: SecondaryMissionSelection | None,
    placed_units: tuple[tuple[RulesUnitView, tuple[ModelPlacement, ...]], ...],
    mission_objective_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if selection is None or not selection.guarded_objective_unit_ids:
        return ()
    controlled = {
        result.objective_id
        for result in record.results
        if result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == player_id
    }
    placed_by_id = {view.unit_instance_id: (view, placements) for view, placements in placed_units}
    if state.mission_setup is None:
        raise GameLifecycleError("Burden of Trust guard evaluation requires MissionSetup.")
    objective_by_id = {
        marker.objective_marker_id: marker for marker in state.mission_setup.objective_markers
    }
    guarded: list[str] = []
    for objective_id, unit_id in selection.guarded_objective_unit_ids:
        if objective_id not in mission_objective_ids or objective_id not in controlled:
            continue
        placed = placed_by_id.get(unit_id)
        if placed is None:
            continue
        view, placements = placed
        if view.owner_player_id != player_id:
            raise GameLifecycleError("Burden of Trust guard unit is not friendly.")
        marker = objective_by_id[objective_id]
        geometry_models = _geometry_models(view=view, placements=placements)
        if not _within_distance_of_point(
            geometry_models,
            x=marker.x_inches,
            y=marker.y_inches,
            inches=DEFAULT_OBJECTIVE_CONTROL_HORIZONTAL_INCHES,
        ):
            continue
        guarded.append(objective_id)
    return tuple(sorted(set(guarded)))


def _beacon_current_unit_ids(
    *,
    state: GameState,
    historical_unit_instance_id: str,
) -> frozenset[str]:
    requested = _validate_identifier("beacon_unit_instance_id", historical_unit_instance_id)
    departure_lineage = frozen_component_lineage_from_departures(
        historical_unit_instance_id=requested,
        departures=tuple(state.primary_battlefield_departure_states),
    )
    if departure_lineage is None:
        return frozenset({requested})
    _owner, frozen_components = departure_lineage
    current_ids = {
        view.unit_instance_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if frozenset(view.component_unit_instance_ids) <= frozen_components
    }
    if current_ids:
        return frozenset(current_ids)
    return frozenset({requested})


def _shares_component(view: RulesUnitView, unit_ids: frozenset[str]) -> bool:
    return bool(unit_ids.intersection(view.component_unit_instance_ids))


def _eligible_scoring_unit(*, state: GameState, view: RulesUnitView) -> bool:
    if any(unit_has_keyword(component.unit, _AIRCRAFT_KEYWORD) for component in view.components):
        return False
    return not rules_unit_is_battle_shocked(state=state, unit_instance_id=view.unit_instance_id)


def _placed_rules_unit_or_none(
    *,
    view: RulesUnitView,
    battlefield_state: BattlefieldRuntimeState,
    placement_by_model_id: dict[str, ModelPlacement],
    embarked_unit_ids: frozenset[str],
) -> tuple[RulesUnitView, tuple[ModelPlacement, ...]] | None:
    if view.unit_instance_id in embarked_unit_ids:
        return None
    if any(component_id in embarked_unit_ids for component_id in view.component_unit_instance_ids):
        return None
    model_by_id = {model.model_instance_id: model for model in view.own_models}
    placements = tuple(
        sorted(
            (
                placement_by_model_id[model_id]
                for model_id in model_by_id
                if model_id in placement_by_model_id
            ),
            key=lambda placement: placement.model_instance_id,
        )
    )
    if not placements:
        return None
    removed = set(battlefield_state.removed_model_ids)
    alive_ids = {
        model.model_instance_id
        for model in view.alive_models()
        if model.model_instance_id not in removed
    }
    if not alive_ids.intersection(placement.model_instance_id for placement in placements):
        return None
    return view, placements


def _embarked_unit_ids(state: GameState) -> frozenset[str]:
    embarked: set[str] = set()
    for cargo in state.transport_cargo_states:
        embarked.update(cargo.embarked_unit_instance_ids)
    return frozenset(embarked)


def _geometry_models(
    *,
    view: RulesUnitView,
    placements: tuple[ModelPlacement, ...],
) -> tuple[GeometryModel, ...]:
    model_by_id = {model.model_instance_id: model for model in view.own_models}
    return tuple(
        geometry_model_for_placement(
            model=model_by_id[placement.model_instance_id],
            placement=placement,
        )
        for placement in placements
        if placement.model_instance_id in model_by_id
    )


def _wholly_within(
    geometry_models: tuple[GeometryModel, ...],
    region_footprint: _Footprint,
) -> bool:
    if not geometry_models:
        return False
    return all(
        region_footprint.covers(shapely_backend.footprint_for_base(model.base, model.pose))
        for model in geometry_models
    )


def _intersects_region(
    geometry_models: tuple[GeometryModel, ...],
    region_footprint: _Footprint,
) -> bool:
    return any(
        region_footprint.intersects(shapely_backend.footprint_for_base(model.base, model.pose))
        for model in geometry_models
    )


def _within_distance_of_point(
    geometry_models: tuple[GeometryModel, ...],
    *,
    x: float,
    y: float,
    inches: float,
) -> bool:
    return any(
        shapely_backend.base_footprint_distance_to_point(
            model.base,
            model.pose,
            x=x,
            y=y,
        )
        <= inches
        for model in geometry_models
    )


def _table_quarter_id_or_none(
    *,
    geometry_models: tuple[GeometryModel, ...],
    center_x: float,
    center_y: float,
) -> str | None:
    if any(
        shapely_backend.base_footprint_distance_to_point(
            model.base,
            model.pose,
            x=center_x,
            y=center_y,
        )
        <= _CENTER_SIX_INCHES
        for model in geometry_models
    ):
        return None
    quarter_bounds = (
        (TABLE_QUARTER_NORTH_WEST, (0.0, center_y, center_x, 2.0 * center_y)),
        (TABLE_QUARTER_NORTH_EAST, (center_x, center_y, 2.0 * center_x, 2.0 * center_y)),
        (TABLE_QUARTER_SOUTH_WEST, (0.0, 0.0, center_x, center_y)),
        (TABLE_QUARTER_SOUTH_EAST, (center_x, 0.0, 2.0 * center_x, center_y)),
    )
    matching = tuple(
        quarter_id
        for quarter_id, bounds in quarter_bounds
        if all(
            shapely_backend.base_footprint_within_bounds(model.base, model.pose, bounds)
            for model in geometry_models
        )
    )
    if len(matching) != 1:
        return None
    return matching[0]


_EDGE_STRIP_INCHES = 0.01


def _near_edges(
    geometry_models: tuple[GeometryModel, ...],
    *,
    width: float,
    depth: float,
) -> frozenset[str]:
    edges: set[str] = set()
    strips = (
        (_EDGE_WEST, (0.0, 0.0, _EDGE_STRIP_INCHES, depth)),
        (_EDGE_EAST, (width - _EDGE_STRIP_INCHES, 0.0, width, depth)),
        (_EDGE_SOUTH, (0.0, 0.0, width, _EDGE_STRIP_INCHES)),
        (_EDGE_NORTH, (0.0, depth - _EDGE_STRIP_INCHES, width, depth)),
    )
    for model in geometry_models:
        for edge_id, bounds in strips:
            if (
                shapely_backend.base_footprint_distance_to_bounds(
                    model.base,
                    model.pose,
                    bounds,
                )
                <= _EDGE_SIX_INCHES
            ):
                edges.add(edge_id)
    return frozenset(edges)


def _opposite_edge_unit_ids(
    *,
    edge_by_unit: dict[str, frozenset[str]],
    outside_territory_unit_ids: frozenset[str],
) -> tuple[str, ...]:
    unit_ids = tuple(sorted(edge_by_unit))
    qualifying: set[str] = set()
    for index, left_id in enumerate(unit_ids):
        for right_id in unit_ids[index + 1 :]:
            pair_edges = edge_by_unit[left_id].union(edge_by_unit[right_id])
            if any(opposite <= pair_edges for opposite in _OPPOSITE_EDGE_PAIRS) and (
                left_id in outside_territory_unit_ids or right_id in outside_territory_unit_ids
            ):
                qualifying.add(left_id)
                qualifying.add(right_id)
    return tuple(sorted(qualifying))


def _owner_role(*, mission_setup: MissionSetup, player_id: str) -> str:
    if player_id == mission_setup.attacker_player_id:
        return "attacker"
    if player_id == mission_setup.defender_player_id:
        return "defender"
    raise GameLifecycleError("Secondary occupancy player is not in MissionSetup.")


def _optional_single_region(
    regions: tuple[BattlefieldRegion, ...],
    *,
    kind: BattlefieldRegionKind,
    owner_role: str | None,
) -> BattlefieldRegion | None:
    matches = tuple(
        region
        for region in regions
        if region.region_kind is kind and region.owner_role == owner_role
    )
    if len(matches) > 1:
        raise GameLifecycleError("Secondary occupancy requires exactly one matching region.")
    if not matches:
        return None
    return matches[0]


def _region_footprint(region: BattlefieldRegion) -> _Footprint:
    return cast(
        _Footprint,
        shapely_backend.footprint_for_deployment_zone_shape(region.shape),
    )


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)
