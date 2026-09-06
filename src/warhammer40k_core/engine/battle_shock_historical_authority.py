from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
from warhammer40k_core.engine.battle_shock_model_authority import (
    command_test_allows_off_battlefield,
)
from warhammer40k_core.engine.battle_shock_state_history import (
    battle_shock_state_authority_before_event,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    PhysicalModelAuthority,
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_from_armies,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class HistoricalBattleShockAuthorityContext:
    """Typed, event-bound facts used to authenticate one Battle-shock test.

    This context is internal and is never serialized. Physical facts come from
    the shared authenticated transition/damage history. Unit definitions and
    starting-strength rows are immutable mustered authority. Mutable faction
    state and effects are deliberately absent: source providers must establish
    those from their exact causal event families.
    """

    game_id: str
    player_ids: tuple[str, ...]
    turn_order: tuple[str, ...]
    battle_phase_sequence: tuple[BattlePhase, ...]
    armies: tuple[ArmyDefinition, ...]
    mission_setup: MissionSetup
    battlefield_width_inches: float
    battlefield_depth_inches: float
    starting_strength_records: tuple[StartingStrengthRecord, ...]
    starting_attached_unit_records: tuple[StartingAttachedUnitRecord, ...]
    physical_models: tuple[PhysicalModelAuthority, ...]
    active_attached_unit_ids: tuple[str, ...]
    battle_shocked_unit_ids: tuple[str, ...]
    event_records: tuple[EventRecord, ...]
    decision_records: tuple[DecisionRecord, ...]
    boundary_event_index: int
    request: BattleShockTestRequest
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def rules_unit(self, unit_instance_id: str) -> RulesUnitView:
        if type(unit_instance_id) is not str or not unit_instance_id:
            raise GameLifecycleError("Historical Battle-shock rules-unit ID is invalid.")
        try:
            view = rules_unit_view_from_armies(
                armies=self.armies, unit_instance_id=unit_instance_id
            )
        except GameLifecycleError as exc:
            raise GameLifecycleError(
                "Historical Battle-shock rules-unit authority is invalid."
            ) from exc
        if view.unit_instance_id != unit_instance_id:
            raise GameLifecycleError(
                "Historical Battle-shock requires canonical rules-unit identity."
            )
        if view.is_attached_rules_unit and unit_instance_id not in self.active_attached_unit_ids:
            raise GameLifecycleError("Historical Battle-shock attached identity is not active.")
        return view

    def all_rules_units(self) -> tuple[RulesUnitView, ...]:
        return tuple(
            self.rules_unit(view.unit_instance_id)
            for view in rules_unit_views_from_armies(armies=self.armies)
        )

    def rules_unit_containing_unit(self, unit_instance_id: str) -> RulesUnitView:
        matches = tuple(
            rules_unit
            for rules_unit in self.all_rules_units()
            if any(
                component.unit.unit_instance_id == unit_instance_id
                for component in rules_unit.components
            )
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Historical Battle-shock component rules-unit authority is ambiguous."
            )
        return matches[0]

    def army_for_player(self, player_id: str) -> ArmyDefinition:
        matches = tuple(army for army in self.armies if army.player_id == player_id)
        if len(matches) != 1:
            raise GameLifecycleError("Historical Battle-shock army authority is ambiguous.")
        return matches[0]

    def unit_and_army(self, unit_instance_id: str) -> tuple[UnitInstance, ArmyDefinition]:
        matches = tuple(
            (unit, army)
            for army in self.armies
            for unit in army.units
            if unit.unit_instance_id == unit_instance_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Historical Battle-shock unit authority is ambiguous.")
        return matches[0]

    def model(self, model_instance_id: str) -> ModelInstance:
        matches = tuple(
            model
            for army in self.armies
            for unit in army.units
            for model in unit.own_models
            if model.model_instance_id == model_instance_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Historical Battle-shock model authority is ambiguous.")
        return matches[0]

    def placed_alive_model_ids(self, unit_instance_id: str) -> tuple[str, ...]:
        rules_unit = self.rules_unit(unit_instance_id)
        allowed = {model.model_instance_id for model in rules_unit.own_models}
        return tuple(
            sorted(
                row.model_instance_id
                for row in self.physical_models
                if row.model_instance_id in allowed and row.presence == "battlefield"
            )
        )

    def battle_shock_model_ids(self, unit_instance_id: str) -> tuple[str, ...]:
        """Use event-bound living strength without manufacturing battlefield geometry."""
        rules_unit = self.rules_unit(unit_instance_id)
        allowed = {model.model_instance_id for model in rules_unit.own_models}
        rows = tuple(
            row
            for row in self.physical_models
            if row.model_instance_id in allowed and row.wounds_remaining > 0
        )
        if (
            command_test_allows_off_battlefield(
                reason=self.request.reason,
                phase=self.phase,
                player_id=rules_unit.owner_player_id,
                active_player_id=self.active_player_id,
            )
            and rows
        ):
            presences = {row.presence for row in rows}
            if presences in ({"embarked"}, {"reserves"}):
                return tuple(sorted(row.model_instance_id for row in rows))
            if presences & {"embarked", "reserves"}:
                raise GameLifecycleError("Historical Battle-shock rules-unit presence is split.")
        return self.placed_alive_model_ids(unit_instance_id)

    def below_half_strength_context(self, unit_instance_id: str) -> BelowHalfStrengthContext:
        rules_unit = self.rules_unit(unit_instance_id)
        starting_strength = self.starting_strength(rules_unit.unit_instance_id)
        current_model_ids = self.battle_shock_model_ids(rules_unit.unit_instance_id)
        single_model_wounds_remaining = None
        if starting_strength.starting_model_count == 1:
            model_ids = {model.model_instance_id for model in rules_unit.own_models}
            matching_rows = tuple(
                row for row in self.physical_models if row.model_instance_id in model_ids
            )
            if len(model_ids) != 1 or len(matching_rows) != 1:
                raise GameLifecycleError(
                    "Historical Battle-shock single-model wound authority is ambiguous."
                )
            single_model_wounds_remaining = matching_rows[0].wounds_remaining
        return BelowHalfStrengthContext(
            player_id=rules_unit.owner_player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            starting_model_count=starting_strength.starting_model_count,
            current_model_count=len(current_model_ids),
            single_model_starting_wounds=starting_strength.single_model_starting_wounds,
            single_model_wounds_remaining=single_model_wounds_remaining,
        )

    def geometry_models(self, unit_instance_id: str) -> tuple[GeometryModel, ...]:
        rows = {
            row.model_instance_id: row
            for row in self.physical_models
            if row.presence == "battlefield"
        }
        geometries: list[GeometryModel] = []
        for model_id in self.placed_alive_model_ids(unit_instance_id):
            row = rows.get(model_id)
            if row is None or row.pose is None:
                raise GameLifecycleError(
                    "Historical Battle-shock battlefield model lacks exact pose authority."
                )
            unit, army = self.unit_and_army_for_model(model_id)
            geometries.append(
                geometry_model_for_placement(
                    model=self.model(model_id),
                    placement=ModelPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_instance_id=model_id,
                        pose=row.pose,
                        split_origin=unit.split_origin,
                    ),
                )
            )
        return tuple(geometries)

    def component_placed_alive_model_ids(self, unit_instance_id: str) -> tuple[str, ...]:
        unit, _army = self.unit_and_army(unit_instance_id)
        allowed = {model.model_instance_id for model in unit.own_models}
        return tuple(
            sorted(
                row.model_instance_id
                for row in self.physical_models
                if row.model_instance_id in allowed and row.presence == "battlefield"
            )
        )

    def component_geometry_models(self, unit_instance_id: str) -> tuple[GeometryModel, ...]:
        unit, army = self.unit_and_army(unit_instance_id)
        rows = {
            row.model_instance_id: row
            for row in self.physical_models
            if row.presence == "battlefield"
        }
        geometries: list[GeometryModel] = []
        for model_id in self.component_placed_alive_model_ids(unit_instance_id):
            row = rows.get(model_id)
            if row is None or row.pose is None:
                raise GameLifecycleError(
                    "Historical Battle-shock component model lacks exact pose authority."
                )
            geometries.append(
                geometry_model_for_placement(
                    model=self.model(model_id),
                    placement=ModelPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_instance_id=model_id,
                        pose=row.pose,
                        split_origin=unit.split_origin,
                    ),
                )
            )
        return tuple(geometries)

    def unit_and_army_for_model(
        self, model_instance_id: str
    ) -> tuple[UnitInstance, ArmyDefinition]:
        matches = tuple(
            (unit, army)
            for army in self.armies
            for unit in army.units
            if any(model.model_instance_id == model_instance_id for model in unit.own_models)
        )
        if len(matches) != 1:
            raise GameLifecycleError("Historical Battle-shock model owner is ambiguous.")
        return matches[0]

    def starting_strength(self, unit_instance_id: str) -> StartingStrengthRecord:
        matches = tuple(
            record
            for record in self.starting_strength_records
            if record.unit_instance_id == unit_instance_id
        )
        if len(matches) == 1:
            return matches[0]
        if not matches:
            attached_matches = tuple(
                record
                for record in self.starting_attached_unit_records
                if record.attached_unit_instance_id == unit_instance_id
            )
            if len(attached_matches) == 1:
                attached = attached_matches[0]
                return StartingStrengthRecord(
                    player_id=attached.player_id,
                    unit_instance_id=attached.attached_unit_instance_id,
                    starting_model_count=attached.starting_model_count,
                    single_model_starting_wounds=None,
                    source_id=attached.source_id,
                )
        raise GameLifecycleError(
            "Historical Battle-shock starting-strength authority is ambiguous."
        )

    def _starting_attached_record(self, unit_instance_id: str) -> StartingAttachedUnitRecord:
        matches = tuple(
            record
            for record in self.starting_attached_unit_records
            if record.attached_unit_instance_id == unit_instance_id
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Historical Battle-shock attached-unit authority is ambiguous."
            )
        return matches[0]


def historical_battle_shock_authority_context(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    boundary_event_index: int,
    request: BattleShockTestRequest,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
) -> HistoricalBattleShockAuthorityContext:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Historical Battle-shock authority requires GameState.")
    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Historical Battle-shock authority requires a request.")
    if request.game_id != state.game_id or request.player_id not in state.player_ids:
        raise GameLifecycleError("Historical Battle-shock request game or player drifted.")
    if type(active_player_id) is not str or active_player_id not in state.player_ids:
        raise GameLifecycleError("Historical Battle-shock active player drifted.")
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("Historical Battle-shock phase must be typed.")
    if type(
        phase_start_battle_shocked_unit_ids
    ) is not tuple or phase_start_battle_shocked_unit_ids != tuple(
        sorted(set(phase_start_battle_shocked_unit_ids))
    ):
        raise GameLifecycleError("Historical Battle-shock phase-start state drifted.")
    physical = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=boundary_event_index,
    )
    shock_state = battle_shock_state_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=boundary_event_index,
    )
    if state.mission_setup is None or state.battlefield_state is None:
        raise GameLifecycleError("Historical Battle-shock authority requires battle setup.")
    return HistoricalBattleShockAuthorityContext(
        game_id=state.game_id,
        player_ids=tuple(state.player_ids),
        turn_order=tuple(state.turn_order),
        battle_phase_sequence=tuple(state.battle_phase_sequence),
        armies=tuple(state.army_definitions),
        mission_setup=state.mission_setup,
        battlefield_width_inches=state.battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=state.battlefield_state.battlefield_depth_inches,
        starting_strength_records=tuple(state.starting_strength_records),
        starting_attached_unit_records=tuple(state.starting_attached_unit_records),
        physical_models=physical,
        active_attached_unit_ids=shock_state.active_attached_unit_ids,
        battle_shocked_unit_ids=shock_state.battle_shocked_unit_ids,
        event_records=event_records,
        decision_records=decision_records,
        boundary_event_index=boundary_event_index,
        request=request,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
    )


__all__ = (
    "HistoricalBattleShockAuthorityContext",
    "historical_battle_shock_authority_context",
)
