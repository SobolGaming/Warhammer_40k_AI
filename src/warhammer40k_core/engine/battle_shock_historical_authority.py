from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
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
    RulesUnitComponent,
    RulesUnitView,
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
        if unit_instance_id in self.active_attached_unit_ids:
            record = self._starting_attached_record(unit_instance_id)
            army = self.army_for_player(record.player_id)
            unit_by_id = {unit.unit_instance_id: unit for unit in army.units}
            try:
                bodyguard = unit_by_id[record.bodyguard_unit_instance_id]
                leaders = tuple(unit_by_id[value] for value in record.leader_unit_instance_ids)
                support = tuple(unit_by_id[value] for value in record.support_unit_instance_ids)
            except KeyError as exc:
                raise GameLifecycleError(
                    "Historical Battle-shock attached-unit component is unknown."
                ) from exc
            formation = AttachedUnitFormation(
                attached_unit_instance_id=record.attached_unit_instance_id,
                bodyguard_unit_instance_id=record.bodyguard_unit_instance_id,
                leader_unit_instance_ids=record.leader_unit_instance_ids,
                support_unit_instance_ids=record.support_unit_instance_ids,
                component_unit_instance_ids=record.component_unit_instance_ids,
                source_id=record.source_id,
                attachment_source_ids=(record.source_id,),
            )
            return RulesUnitView(
                unit_instance_id=record.attached_unit_instance_id,
                owner_player_id=record.player_id,
                components=(
                    RulesUnitComponent(unit=bodyguard, role="bodyguard"),
                    *(RulesUnitComponent(unit=value, role="leader") for value in leaders),
                    *(RulesUnitComponent(unit=value, role="support") for value in support),
                ),
                attached_unit=formation,
            )
        unit, army = self.unit_and_army(unit_instance_id)
        if any(
            unit.unit_instance_id in record.component_unit_instance_ids
            and record.attached_unit_instance_id in self.active_attached_unit_ids
            for record in self.starting_attached_unit_records
        ):
            raise GameLifecycleError(
                "Historical Battle-shock component ID is not a canonical active rules unit."
            )
        return RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(RulesUnitComponent(unit=unit, role="unit"),),
        )

    def all_rules_units(self) -> tuple[RulesUnitView, ...]:
        attached_component_ids = {
            component_id
            for record in self.starting_attached_unit_records
            if record.attached_unit_instance_id in self.active_attached_unit_ids
            for component_id in record.component_unit_instance_ids
        }
        views = [self.rules_unit(value) for value in self.active_attached_unit_ids]
        views.extend(
            self.rules_unit(unit.unit_instance_id)
            for army in self.armies
            for unit in army.units
            if unit.unit_instance_id not in attached_component_ids
        )
        ids = tuple(value.unit_instance_id for value in views)
        if len(ids) != len(set(ids)):
            raise GameLifecycleError("Historical Battle-shock rules-unit inventory is duplicated.")
        return tuple(sorted(views, key=lambda value: value.unit_instance_id))

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

    def below_half_strength_context(self, unit_instance_id: str) -> BelowHalfStrengthContext:
        rules_unit = self.rules_unit(unit_instance_id)
        starting_strength = self.starting_strength(rules_unit.unit_instance_id)
        current_model_ids = self.placed_alive_model_ids(rules_unit.unit_instance_id)
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
