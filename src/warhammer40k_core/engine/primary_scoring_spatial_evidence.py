from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from warhammer40k_core.core.battlefield_regions import BattlefieldRegion, BattlefieldRegionKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    objective_control_timing_from_token,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_views_from_armies
from warhammer40k_core.geometry import shapely_backend

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class _Footprint(Protocol):
    def covers(self, other: object) -> bool: ...


TABLE_QUARTER_NORTH_WEST = "table-quarter:north-west"
TABLE_QUARTER_NORTH_EAST = "table-quarter:north-east"
TABLE_QUARTER_SOUTH_WEST = "table-quarter:south-west"
TABLE_QUARTER_SOUTH_EAST = "table-quarter:south-east"
TABLE_QUARTER_IDS = (
    TABLE_QUARTER_NORTH_WEST,
    TABLE_QUARTER_NORTH_EAST,
    TABLE_QUARTER_SOUTH_WEST,
    TABLE_QUARTER_SOUTH_EAST,
)
_CENTER_EXCLUSION_INCHES = 6.0

PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION = (
    "each_controlled_objective_in_opponent_territory"
)
PRIMARY_SCORING_THREE_TABLE_QUARTERS_CONDITION = (
    "three_or_more_friendly_units_wholly_within_three_different_table_quarters_"
    "not_within_six_of_center"
)
PRIMARY_SCORING_FOUR_TABLE_QUARTERS_CONDITION = (
    "four_or_more_friendly_units_wholly_within_four_different_table_quarters_"
    "not_within_six_of_center"
)
PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION = (
    "no_enemy_units_wholly_within_own_territory_end_of_battle"
)
PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS = frozenset(
    {
        PRIMARY_SCORING_THREE_TABLE_QUARTERS_CONDITION,
        PRIMARY_SCORING_FOUR_TABLE_QUARTERS_CONDITION,
    }
)
PRIMARY_SCORING_SPATIAL_CONDITIONS = frozenset(
    {
        PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
        *PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS,
        PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    }
)


class PrimaryTableQuarterUnitWitnessPayload(TypedDict):
    rules_unit_instance_id: str
    quarter_id: str
    model_instance_ids: list[str]


class PrimaryTerritoryUnitWitnessPayload(TypedDict):
    rules_unit_instance_id: str
    model_instance_ids: list[str]


class PrimaryScoringSpatialEvidencePayload(TypedDict):
    game_id: str
    battlefield_id: str
    battle_round: int
    active_player_id: str
    phase: str
    timing: str
    objective_control_record_id: str
    objective_control_record_hash: str
    player_id: str
    requested_condition_ids: list[str]
    table_quarter_unit_witnesses: list[PrimaryTableQuarterUnitWitnessPayload]
    enemy_units_wholly_within_own_territory: list[PrimaryTerritoryUnitWitnessPayload]
    opponent_territory_objective_ids: list[str]


@dataclass(frozen=True, slots=True)
class PrimaryTableQuarterUnitWitness:
    rules_unit_instance_id: str
    quarter_id: str
    model_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rules_unit_instance_id",
            _validate_identifier(
                "PrimaryTableQuarterUnitWitness rules_unit_instance_id",
                self.rules_unit_instance_id,
            ),
        )
        if self.quarter_id not in TABLE_QUARTER_IDS:
            raise GameLifecycleError("PrimaryTableQuarterUnitWitness quarter_id is unsupported.")
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_sorted_identifier_tuple(
                "PrimaryTableQuarterUnitWitness model_instance_ids",
                self.model_instance_ids,
                require_non_empty=True,
            ),
        )

    def to_payload(self) -> PrimaryTableQuarterUnitWitnessPayload:
        return {
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "quarter_id": self.quarter_id,
            "model_instance_ids": list(self.model_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> PrimaryTableQuarterUnitWitness:
        raw = _required_payload_mapping(
            payload,
            field_name="PrimaryTableQuarterUnitWitness payload",
            required_keys=("rules_unit_instance_id", "quarter_id", "model_instance_ids"),
        )
        return cls(
            rules_unit_instance_id=cast(str, raw["rules_unit_instance_id"]),
            quarter_id=cast(str, raw["quarter_id"]),
            model_instance_ids=tuple(
                cast(
                    list[str],
                    _required_payload_list(
                        raw["model_instance_ids"],
                        field_name="PrimaryTableQuarterUnitWitness model_instance_ids",
                    ),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryTerritoryUnitWitness:
    rules_unit_instance_id: str
    model_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rules_unit_instance_id",
            _validate_identifier(
                "PrimaryTerritoryUnitWitness rules_unit_instance_id",
                self.rules_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_sorted_identifier_tuple(
                "PrimaryTerritoryUnitWitness model_instance_ids",
                self.model_instance_ids,
                require_non_empty=True,
            ),
        )

    def to_payload(self) -> PrimaryTerritoryUnitWitnessPayload:
        return {
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "model_instance_ids": list(self.model_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> PrimaryTerritoryUnitWitness:
        raw = _required_payload_mapping(
            payload,
            field_name="PrimaryTerritoryUnitWitness payload",
            required_keys=("rules_unit_instance_id", "model_instance_ids"),
        )
        return cls(
            rules_unit_instance_id=cast(str, raw["rules_unit_instance_id"]),
            model_instance_ids=tuple(
                cast(
                    list[str],
                    _required_payload_list(
                        raw["model_instance_ids"],
                        field_name="PrimaryTerritoryUnitWitness model_instance_ids",
                    ),
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryScoringSpatialEvidence:
    game_id: str
    battlefield_id: str
    battle_round: int
    active_player_id: str
    phase: str
    timing: ObjectiveControlTiming
    objective_control_record_id: str
    objective_control_record_hash: str
    player_id: str
    requested_condition_ids: tuple[str, ...]
    table_quarter_unit_witnesses: tuple[PrimaryTableQuarterUnitWitness, ...]
    enemy_units_wholly_within_own_territory: tuple[PrimaryTerritoryUnitWitness, ...]
    opponent_territory_objective_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "game_id",
            "battlefield_id",
            "active_player_id",
            "phase",
            "objective_control_record_id",
            "objective_control_record_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(
                    f"PrimaryScoringSpatialEvidence {field_name}",
                    getattr(self, field_name),
                ),
            )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "PrimaryScoringSpatialEvidence battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "timing",
            _objective_control_timing(self.timing),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PrimaryScoringSpatialEvidence player_id", self.player_id),
        )
        requested_conditions = _validate_requested_condition_ids(self.requested_condition_ids)
        quarter_witnesses = _validate_quarter_witnesses(self.table_quarter_unit_witnesses)
        territory_witnesses = _validate_territory_witnesses(
            self.enemy_units_wholly_within_own_territory
        )
        object.__setattr__(self, "table_quarter_unit_witnesses", quarter_witnesses)
        object.__setattr__(self, "requested_condition_ids", requested_conditions)
        object.__setattr__(
            self,
            "enemy_units_wholly_within_own_territory",
            territory_witnesses,
        )
        object.__setattr__(
            self,
            "opponent_territory_objective_ids",
            _validate_sorted_identifier_tuple(
                "PrimaryScoringSpatialEvidence opponent_territory_objective_ids",
                self.opponent_territory_objective_ids,
                require_non_empty=False,
            ),
        )
        if (
            not PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS.intersection(requested_conditions)
            and quarter_witnesses
        ):
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence has unrequested table-quarter witnesses."
            )
        if (
            PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION not in requested_conditions
            and territory_witnesses
        ):
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence has unrequested territory witnesses."
            )
        if (
            PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION not in requested_conditions
            and self.opponent_territory_objective_ids
        ):
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence has unrequested territory objectives."
            )

    def to_payload(self) -> PrimaryScoringSpatialEvidencePayload:
        return {
            "game_id": self.game_id,
            "battlefield_id": self.battlefield_id,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase": self.phase,
            "timing": self.timing.value,
            "objective_control_record_id": self.objective_control_record_id,
            "objective_control_record_hash": self.objective_control_record_hash,
            "player_id": self.player_id,
            "requested_condition_ids": list(self.requested_condition_ids),
            "table_quarter_unit_witnesses": [
                witness.to_payload() for witness in self.table_quarter_unit_witnesses
            ],
            "enemy_units_wholly_within_own_territory": [
                witness.to_payload() for witness in self.enemy_units_wholly_within_own_territory
            ],
            "opponent_territory_objective_ids": list(self.opponent_territory_objective_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> PrimaryScoringSpatialEvidence:
        raw = _required_payload_mapping(
            payload,
            field_name="PrimaryScoringSpatialEvidence payload",
            required_keys=tuple(PrimaryScoringSpatialEvidencePayload.__annotations__),
        )
        return cls(
            game_id=cast(str, raw["game_id"]),
            battlefield_id=cast(str, raw["battlefield_id"]),
            battle_round=cast(int, raw["battle_round"]),
            active_player_id=cast(str, raw["active_player_id"]),
            phase=cast(str, raw["phase"]),
            timing=objective_control_timing_from_token(raw["timing"]),
            objective_control_record_id=cast(str, raw["objective_control_record_id"]),
            objective_control_record_hash=cast(str, raw["objective_control_record_hash"]),
            player_id=cast(str, raw["player_id"]),
            requested_condition_ids=tuple(
                cast(
                    list[str],
                    _required_payload_list(
                        raw["requested_condition_ids"],
                        field_name="PrimaryScoringSpatialEvidence requested_condition_ids",
                    ),
                )
            ),
            table_quarter_unit_witnesses=tuple(
                PrimaryTableQuarterUnitWitness.from_payload(value)
                for value in _required_payload_list(
                    raw["table_quarter_unit_witnesses"],
                    field_name="PrimaryScoringSpatialEvidence table-quarter witnesses",
                )
            ),
            enemy_units_wholly_within_own_territory=tuple(
                PrimaryTerritoryUnitWitness.from_payload(value)
                for value in _required_payload_list(
                    raw["enemy_units_wholly_within_own_territory"],
                    field_name="PrimaryScoringSpatialEvidence territory witnesses",
                )
            ),
            opponent_territory_objective_ids=tuple(
                cast(
                    list[str],
                    _required_payload_list(
                        raw["opponent_territory_objective_ids"],
                        field_name=("PrimaryScoringSpatialEvidence opponent territory objectives"),
                    ),
                )
            ),
        )


def build_primary_scoring_spatial_evidence(
    *,
    state: GameState,
    player_id: str,
    record: ObjectiveControlRecord,
    requested_condition_ids: tuple[str, ...],
    model_placements: tuple[ModelPlacement, ...] | None = None,
) -> PrimaryScoringSpatialEvidence:
    """Derive exact, deterministic spatial witnesses for generic Primary conditions."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary spatial scoring evidence requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary spatial scoring evidence requires an ObjectiveControlRecord."
        )
    requested_player_id = _validate_identifier("player_id", player_id)
    if requested_player_id not in state.player_ids:
        raise GameLifecycleError("Primary spatial scoring player_id is not in this game.")
    requested_conditions = _validate_requested_condition_ids(requested_condition_ids)
    mission_setup = state.mission_setup
    battlefield_state = state.battlefield_state
    if mission_setup is None or battlefield_state is None:
        raise GameLifecycleError(
            "Primary spatial scoring evidence requires mission and battlefield state."
        )
    _validate_battlefield_identity(
        mission_setup=mission_setup,
        battlefield_state=battlefield_state,
    )
    _validate_record_identity(
        state=state,
        battlefield_state=battlefield_state,
        record=record,
        require_current_battle_context=model_placements is None,
    )
    needs_quarters = bool(
        PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS.intersection(requested_conditions)
    )
    needs_enemy_territory = (
        PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION in requested_conditions
    )
    needs_opponent_objectives = (
        PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION in requested_conditions
    )
    own_role, opponent_role = _directed_roles(
        mission_setup=mission_setup,
        player_id=requested_player_id,
    )
    own_territory = (
        _single_territory_region(mission_setup, owner_role=own_role)
        if needs_enemy_territory
        else None
    )
    own_territory_footprint = (
        cast(
            _Footprint,
            shapely_backend.footprint_for_deployment_zone_shape(own_territory.shape),
        )
        if own_territory is not None
        else None
    )
    opponent_territory = (
        _single_territory_region(mission_setup, owner_role=opponent_role)
        if needs_opponent_objectives
        else None
    )
    placement_by_model_id = None if model_placements is None else _placement_map(model_placements)
    unavailable_model_ids: set[str] = (
        set() if placement_by_model_id is not None else set(state.unavailable_model_ids())
    )
    views = (
        rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if needs_quarters or needs_enemy_territory
        else ()
    )
    placed_rules_units = tuple(
        resolved
        for view in views
        if (
            (needs_quarters and view.owner_player_id == requested_player_id)
            or (needs_enemy_territory and view.owner_player_id != requested_player_id)
        )
        if (
            resolved := _placed_alive_rules_unit_or_none(
                view=view,
                battlefield_state=battlefield_state,
                unavailable_model_ids=unavailable_model_ids,
                placement_by_model_id=placement_by_model_id,
            )
        )
        is not None
    )
    quarter_witnesses = tuple(
        sorted(
            (
                witness
                for view, placements in placed_rules_units
                if needs_quarters
                and view.owner_player_id == requested_player_id
                and (
                    witness := _table_quarter_witness_or_none(
                        view=view,
                        placements=placements,
                        battlefield_state=battlefield_state,
                    )
                )
                is not None
            ),
            key=lambda witness: (witness.quarter_id, witness.rules_unit_instance_id),
        )
    )
    enemy_territory_witnesses = tuple(
        sorted(
            (
                PrimaryTerritoryUnitWitness(
                    rules_unit_instance_id=view.unit_instance_id,
                    model_instance_ids=tuple(
                        sorted(placement.model_instance_id for placement in placements)
                    ),
                )
                for view, placements in placed_rules_units
                if needs_enemy_territory
                and view.owner_player_id != requested_player_id
                and own_territory is not None
                and own_territory_footprint is not None
                and _placements_wholly_within_region(
                    view=view,
                    placements=placements,
                    region_footprint=own_territory_footprint,
                )
            ),
            key=lambda witness: witness.rules_unit_instance_id,
        )
    )
    opponent_objective_ids = tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if opponent_territory is not None
            and opponent_territory.contains_point(marker.x_inches, marker.y_inches)
        )
    )
    return PrimaryScoringSpatialEvidence(
        game_id=record.game_id,
        battlefield_id=record.battlefield_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        player_id=requested_player_id,
        requested_condition_ids=requested_conditions,
        table_quarter_unit_witnesses=quarter_witnesses,
        enemy_units_wholly_within_own_territory=enemy_territory_witnesses,
        opponent_territory_objective_ids=opponent_objective_ids,
    )


def _placed_alive_rules_unit_or_none(
    *,
    view: RulesUnitView,
    battlefield_state: BattlefieldRuntimeState,
    unavailable_model_ids: set[str],
    placement_by_model_id: dict[str, ModelPlacement] | None = None,
) -> tuple[RulesUnitView, tuple[ModelPlacement, ...]] | None:
    model_by_id = {model.model_instance_id: model for model in view.own_models}
    if placement_by_model_id is not None:
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
        _validate_spatial_placements(
            view=view,
            placements=placements,
            model_by_id=model_by_id,
        )
        return view, placements
    removed_model_ids = set(battlefield_state.removed_model_ids)
    alive_models = tuple(
        sorted(
            (
                model
                for model in view.alive_models()
                if model.model_instance_id not in removed_model_ids
            ),
            key=lambda model: model.model_instance_id,
        )
    )
    if not alive_models:
        return None
    alive_model_ids = {model.model_instance_id for model in alive_models}
    placements = tuple(
        placement
        for model in alive_models
        if (placement := battlefield_state.model_placement_or_none(model.model_instance_id))
        is not None
    )
    placed_model_ids = {placement.model_instance_id for placement in placements}
    if placed_model_ids & unavailable_model_ids:
        raise GameLifecycleError("Primary spatial scoring found a placed model marked unavailable.")
    if not placements:
        if alive_model_ids <= unavailable_model_ids:
            return None
        raise GameLifecycleError(
            "Primary spatial scoring found an alive rules unit with no accounted placement."
        )
    if placed_model_ids != alive_model_ids:
        raise GameLifecycleError(
            "Primary spatial scoring requires every alive model in a rules unit to be placed."
        )
    _validate_spatial_placements(
        view=view,
        placements=placements,
        model_by_id=model_by_id,
    )
    return view, tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def _validate_spatial_placements(
    *,
    view: RulesUnitView,
    placements: tuple[ModelPlacement, ...],
    model_by_id: Mapping[str, object],
) -> None:
    for placement in placements:
        if placement.model_instance_id not in model_by_id:
            raise GameLifecycleError(
                "Primary spatial scoring model placement is missing from its rules unit."
            )
        if placement.player_id != view.owner_player_id:
            raise GameLifecycleError("Primary spatial scoring model placement owner drift.")
        if (
            placement.unit_instance_id
            != view.component_unit_for_model(placement.model_instance_id).unit_instance_id
        ):
            raise GameLifecycleError("Primary spatial scoring component placement drift.")


def _placement_map(model_placements: tuple[ModelPlacement, ...]) -> dict[str, ModelPlacement]:
    if type(model_placements) is not tuple or any(
        type(placement) is not ModelPlacement for placement in model_placements
    ):
        raise GameLifecycleError("Primary spatial scoring model placements must be typed.")
    placement_by_model_id: dict[str, ModelPlacement] = {}
    for placement in model_placements:
        if placement.model_instance_id in placement_by_model_id:
            raise GameLifecycleError("Primary spatial scoring model placements are duplicated.")
        placement_by_model_id[placement.model_instance_id] = placement
    return placement_by_model_id


def _table_quarter_witness_or_none(
    *,
    view: RulesUnitView,
    placements: tuple[ModelPlacement, ...],
    battlefield_state: BattlefieldRuntimeState,
) -> PrimaryTableQuarterUnitWitness | None:
    center_x = battlefield_state.battlefield_width_inches / 2.0
    center_y = battlefield_state.battlefield_depth_inches / 2.0
    model_by_id = {model.model_instance_id: model for model in view.own_models}
    geometry_models = tuple(
        geometry_model_for_placement(
            model=model_by_id[placement.model_instance_id],
            placement=placement,
        )
        for placement in placements
    )
    if any(
        shapely_backend.base_footprint_distance_to_point(
            model.base,
            model.pose,
            x=center_x,
            y=center_y,
        )
        <= _CENTER_EXCLUSION_INCHES
        for model in geometry_models
    ):
        return None
    quarter_bounds = (
        (TABLE_QUARTER_NORTH_WEST, (0.0, center_y, center_x, 2.0 * center_y)),
        (
            TABLE_QUARTER_NORTH_EAST,
            (center_x, center_y, 2.0 * center_x, 2.0 * center_y),
        ),
        (TABLE_QUARTER_SOUTH_WEST, (0.0, 0.0, center_x, center_y)),
        (TABLE_QUARTER_SOUTH_EAST, (center_x, 0.0, 2.0 * center_x, center_y)),
    )
    matching_quarters = tuple(
        quarter_id
        for quarter_id, bounds in quarter_bounds
        if all(
            shapely_backend.base_footprint_within_bounds(model.base, model.pose, bounds)
            for model in geometry_models
        )
    )
    if not matching_quarters:
        return None
    if len(matching_quarters) != 1:
        raise GameLifecycleError(
            "Primary spatial scoring rules unit belongs to multiple table quarters."
        )
    return PrimaryTableQuarterUnitWitness(
        rules_unit_instance_id=view.unit_instance_id,
        quarter_id=matching_quarters[0],
        model_instance_ids=tuple(sorted(placement.model_instance_id for placement in placements)),
    )


def _placements_wholly_within_region(
    *,
    view: RulesUnitView,
    placements: tuple[ModelPlacement, ...],
    region_footprint: _Footprint,
) -> bool:
    model_by_id = {model.model_instance_id: model for model in view.own_models}
    return all(
        region_footprint.covers(
            shapely_backend.footprint_for_base(
                geometry_model.base,
                geometry_model.pose,
            )
        )
        for placement in placements
        for geometry_model in (
            geometry_model_for_placement(
                model=model_by_id[placement.model_instance_id],
                placement=placement,
            ),
        )
    )


def _directed_roles(*, mission_setup: MissionSetup, player_id: str) -> tuple[str, str]:
    if player_id == mission_setup.attacker_player_id:
        return "attacker", "defender"
    if player_id == mission_setup.defender_player_id:
        return "defender", "attacker"
    raise GameLifecycleError("Primary spatial scoring player_id is not in MissionSetup.")


def _single_territory_region(
    mission_setup: MissionSetup,
    *,
    owner_role: str,
) -> BattlefieldRegion:
    matches = tuple(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == owner_role
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary spatial scoring requires exactly one territory for each player role."
        )
    return matches[0]


def _validate_battlefield_identity(
    *,
    mission_setup: MissionSetup,
    battlefield_state: BattlefieldRuntimeState,
) -> None:
    if (
        battlefield_state.battlefield_width_inches != mission_setup.battlefield_width_inches
        or battlefield_state.battlefield_depth_inches != mission_setup.battlefield_depth_inches
    ):
        raise GameLifecycleError(
            "Primary spatial scoring battlefield dimensions drifted from MissionSetup."
        )


def _validate_record_identity(
    *,
    state: GameState,
    battlefield_state: BattlefieldRuntimeState,
    record: ObjectiveControlRecord,
    require_current_battle_context: bool = True,
) -> None:
    if require_current_battle_context:
        current_phase = state.current_battle_phase
        if current_phase is None or state.active_player_id is None:
            raise GameLifecycleError(
                "Primary spatial scoring evidence requires an active battle boundary."
            )
        if (
            record.game_id != state.game_id
            or record.battlefield_id != battlefield_state.battlefield_id
            or record.battle_round != state.battle_round
            or record.active_player_id != state.active_player_id
            or record.phase != current_phase.value
        ):
            raise GameLifecycleError(
                "Primary spatial scoring ObjectiveControlRecord drifted from GameState."
            )
    elif (
        record.game_id != state.game_id or record.battlefield_id != battlefield_state.battlefield_id
    ):
        raise GameLifecycleError(
            "Primary spatial scoring ObjectiveControlRecord drifted from GameState."
        )
    stored = tuple(
        candidate
        for candidate in state.objective_control_records
        if candidate.record_id == record.record_id
    )
    if stored != (record,):
        raise GameLifecycleError(
            "Primary spatial scoring requires the authoritative ObjectiveControlRecord."
        )


def objective_control_record_hash(record: ObjectiveControlRecord) -> str:
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary spatial scoring record hash requires an ObjectiveControlRecord."
        )
    return hashlib.sha256(canonical_json(record.to_payload()).encode("utf-8")).hexdigest()


def _validate_requested_condition_ids(values: object) -> tuple[str, ...]:
    conditions = _validate_sorted_identifier_tuple(
        "PrimaryScoringSpatialEvidence requested_condition_ids",
        values,
        require_non_empty=True,
    )
    if not set(conditions) <= PRIMARY_SCORING_SPATIAL_CONDITIONS:
        raise GameLifecycleError(
            "PrimaryScoringSpatialEvidence requested_condition_ids are unsupported."
        )
    return conditions


def _validate_quarter_witnesses(
    values: object,
) -> tuple[PrimaryTableQuarterUnitWitness, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringSpatialEvidence table-quarter witnesses must be a tuple."
        )
    witnesses: list[PrimaryTableQuarterUnitWitness] = []
    unit_ids: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not PrimaryTableQuarterUnitWitness:
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence table-quarter witnesses are invalid."
            )
        if value.rules_unit_instance_id in unit_ids:
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence rules units must have one table-quarter witness."
            )
        unit_ids.add(value.rules_unit_instance_id)
        witnesses.append(value)
    expected = tuple(
        sorted(witnesses, key=lambda witness: (witness.quarter_id, witness.rules_unit_instance_id))
    )
    if raw_values != expected:
        raise GameLifecycleError(
            "PrimaryScoringSpatialEvidence table-quarter witnesses must be sorted."
        )
    return expected


def _validate_territory_witnesses(
    values: object,
) -> tuple[PrimaryTerritoryUnitWitness, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringSpatialEvidence territory witnesses must be a tuple."
        )
    witnesses: list[PrimaryTerritoryUnitWitness] = []
    unit_ids: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not PrimaryTerritoryUnitWitness:
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence territory witnesses are invalid."
            )
        if value.rules_unit_instance_id in unit_ids:
            raise GameLifecycleError(
                "PrimaryScoringSpatialEvidence territory witness units must be unique."
            )
        unit_ids.add(value.rules_unit_instance_id)
        witnesses.append(value)
    expected = tuple(sorted(witnesses, key=lambda witness: witness.rules_unit_instance_id))
    if raw_values != expected:
        raise GameLifecycleError(
            "PrimaryScoringSpatialEvidence territory witnesses must be sorted."
        )
    return expected


def _validate_sorted_identifier_tuple(
    field_name: str,
    values: object,
    *,
    require_non_empty: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} item", value)
        for value in cast(tuple[object, ...], values)
    )
    if require_non_empty and not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    if identifiers != tuple(sorted(identifiers)):
        raise GameLifecycleError(f"{field_name} must be sorted.")
    return identifiers


def _required_payload_mapping(
    payload: object,
    *,
    field_name: str,
    required_keys: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    untyped_raw = cast(dict[object, object], payload)
    if any(type(key) is not str for key in untyped_raw):
        raise GameLifecycleError(f"{field_name} must be an object.")
    raw = cast(dict[str, object], payload)
    if set(raw) != set(required_keys):
        raise GameLifecycleError(f"{field_name} fields are invalid.")
    return raw


def _required_payload_list(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{field_name} must be a list.")
    return cast(list[object], value)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _objective_control_timing(value: object) -> ObjectiveControlTiming:
    if type(value) is not ObjectiveControlTiming:
        raise GameLifecycleError(
            "PrimaryScoringSpatialEvidence timing must be ObjectiveControlTiming."
        )
    return value


def validate_primary_scoring_spatial_evidence_rows(
    values: object,
) -> tuple[PrimaryScoringSpatialEvidence, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("PrimaryScoringStateEvidence spatial evidence must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    rows: list[PrimaryScoringSpatialEvidence] = []
    seen_players: set[str] = set()
    for value in raw_values:
        if type(value) is not PrimaryScoringSpatialEvidence:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence spatial evidence must contain typed rows."
            )
        if value.player_id in seen_players:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence spatial evidence must not duplicate players."
            )
        seen_players.add(value.player_id)
        rows.append(value)
    expected = tuple(sorted(rows, key=lambda row: row.player_id))
    if raw_values != expected:
        raise GameLifecycleError("PrimaryScoringStateEvidence spatial evidence must be sorted.")
    return expected


__all__ = (
    "PRIMARY_SCORING_FOUR_TABLE_QUARTERS_CONDITION",
    "PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION",
    "PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION",
    "PRIMARY_SCORING_SPATIAL_CONDITIONS",
    "PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS",
    "PRIMARY_SCORING_THREE_TABLE_QUARTERS_CONDITION",
    "TABLE_QUARTER_IDS",
    "PrimaryScoringSpatialEvidence",
    "PrimaryScoringSpatialEvidencePayload",
    "PrimaryTableQuarterUnitWitness",
    "PrimaryTableQuarterUnitWitnessPayload",
    "PrimaryTerritoryUnitWitness",
    "PrimaryTerritoryUnitWitnessPayload",
    "build_primary_scoring_spatial_evidence",
    "objective_control_record_hash",
    "validate_primary_scoring_spatial_evidence_rows",
)
