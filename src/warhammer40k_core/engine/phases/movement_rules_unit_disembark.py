from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacementRecord,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.hazard import CORE_HAZARD_ROLLS_RULE_ID
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
    DestroyedTransportModelRoll,
    DisembarkedUnitState,
    DisembarkModeKind,
    DisembarkSelection,
    TransportCargoState,
    TransportMovementStatus,
    TransportOperationViolation,
    TransportOperationViolationCode,
    TransportRestrictionOverride,
    resolve_combat_disembark,
    resolve_disembark,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    rules_unit_coherency_result,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import MortalWoundApplication
    from warhammer40k_core.engine.game_state import GameState


RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND = "rules_unit_combat_disembark"


@dataclass(frozen=True, slots=True)
class RulesUnitDisembarkSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    attempted_placement: RulesUnitPlacement
    disembark_mode: DisembarkModeKind
    transport_movement_status: TransportMovementStatus
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = ()

    def __post_init__(self) -> None:
        if type(self.attempted_placement) is not RulesUnitPlacement:
            raise GameLifecycleError("Rules-unit Disembark requires RulesUnitPlacement.")
        if self.attempted_placement.rules_unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("Rules-unit Disembark placement identity drift.")
        if self.attempted_placement.player_id != self.player_id:
            raise GameLifecycleError("Rules-unit Disembark placement player drift.")


@dataclass(frozen=True, slots=True)
class RulesUnitDisembarkResolution:
    selection: RulesUnitDisembarkSelection
    violations: tuple[TransportOperationViolation, ...]
    coherency_result: UnitCoherencyResult
    updated_cargo_state: TransportCargoState | None
    disembarked_unit_state: DisembarkedUnitState | None
    transition_batch: BattlefieldTransitionBatch | None

    def __post_init__(self) -> None:
        if self.violations and (
            self.updated_cargo_state is not None
            or self.disembarked_unit_state is not None
            or self.transition_batch is not None
        ):
            raise GameLifecycleError(
                "Invalid rules-unit Disembark cannot contain mutation records."
            )
        if not self.violations and (
            self.updated_cargo_state is None
            or self.disembarked_unit_state is None
            or self.transition_batch is None
        ):
            raise GameLifecycleError(
                "Valid rules-unit Disembark requires complete mutation records."
            )

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "selection": {
                "player_id": self.selection.player_id,
                "battle_round": self.selection.battle_round,
                "unit_instance_id": self.selection.unit_instance_id,
                "transport_unit_instance_id": self.selection.transport_unit_instance_id,
                "attempted_rules_unit_placement": validate_json_value(
                    self.selection.attempted_placement.to_payload()
                ),
                "disembark_mode": self.selection.disembark_mode.value,
                "transport_movement_status": self.selection.transport_movement_status.value,
                "restriction_overrides": [
                    validate_json_value(override.to_payload())
                    for override in self.selection.restriction_overrides
                ],
            },
            "is_valid": self.is_valid,
            "violations": [
                validate_json_value(violation.to_payload()) for violation in self.violations
            ],
            "coherency_result": validate_json_value(self.coherency_result.to_payload()),
            "updated_cargo_state": None
            if self.updated_cargo_state is None
            else validate_json_value(self.updated_cargo_state.to_payload()),
            "disembarked_unit_state": None
            if self.disembarked_unit_state is None
            else validate_json_value(self.disembarked_unit_state.to_payload()),
            "transition_batch": None
            if self.transition_batch is None
            else validate_json_value(self.transition_batch.to_payload()),
        }


@dataclass(frozen=True, slots=True)
class RulesUnitCombatDisembarkModelRoll:
    component_unit_instance_id: str
    roll: DestroyedTransportModelRoll
    mortal_wounds_per_failed_roll: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_unit_instance_id",
            _validate_identifier(
                "RulesUnitCombatDisembarkModelRoll component_unit_instance_id",
                self.component_unit_instance_id,
            ),
        )
        if type(self.roll) is not DestroyedTransportModelRoll:
            raise GameLifecycleError(
                "Rules-unit Combat Disembark roll must be a transport hazard roll."
            )
        if type(
            self.mortal_wounds_per_failed_roll
        ) is not int or self.mortal_wounds_per_failed_roll not in {1, 3}:
            raise GameLifecycleError(
                "Rules-unit Combat Disembark mortal wounds per failed roll drift."
            )

    @property
    def mortal_wounds(self) -> int:
        return self.mortal_wounds_per_failed_roll if self.roll.mortal_wound_inflicted else 0

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "component_unit_instance_id": self.component_unit_instance_id,
            "roll": validate_json_value(self.roll.to_payload()),
            "mortal_wounds_per_failed_roll": self.mortal_wounds_per_failed_roll,
            "mortal_wounds": self.mortal_wounds,
        }


@dataclass(frozen=True, slots=True)
class RulesUnitCombatDisembarkResolution:
    placement: RulesUnitDisembarkResolution
    tactical_resolution: RulesUnitDisembarkResolution
    model_rolls: tuple[RulesUnitCombatDisembarkModelRoll, ...]

    def __post_init__(self) -> None:
        if self.placement.selection.disembark_mode is not DisembarkModeKind.COMBAT_DISEMBARK:
            raise GameLifecycleError("Rules-unit Combat Disembark placement mode drift.")
        if (
            self.tactical_resolution.selection.disembark_mode
            is not DisembarkModeKind.TACTICAL_DISEMBARK
        ):
            raise GameLifecycleError("Rules-unit Combat Disembark tactical fallback mode drift.")
        if self.placement.is_valid and not self.tactical_resolution.is_valid:
            expected_component_by_model_id = {
                placement.model_instance_id: component.unit_instance_id
                for component in (
                    self.placement.selection.attempted_placement.component_unit_placements
                )
                for placement in component.model_placements
            }
            rolled_model_ids = tuple(roll.roll.model_instance_id for roll in self.model_rolls)
            if (
                len(rolled_model_ids) != len(expected_component_by_model_id)
                or len(set(rolled_model_ids)) != len(rolled_model_ids)
                or set(rolled_model_ids) != set(expected_component_by_model_id)
            ):
                raise GameLifecycleError("Rules-unit Combat Disembark hazard roll model drift.")
            for model_roll in self.model_rolls:
                if expected_component_by_model_id[model_roll.roll.model_instance_id] != (
                    model_roll.component_unit_instance_id
                ):
                    raise GameLifecycleError(
                        "Rules-unit Combat Disembark hazard roll component drift."
                    )
        elif self.model_rolls:
            raise GameLifecycleError(
                "Ineligible rules-unit Combat Disembark cannot contain hazard rolls."
            )

    @property
    def is_valid(self) -> bool:
        return self.placement.is_valid and not self.tactical_resolution.is_valid

    @property
    def mortal_wounds(self) -> int:
        return sum(roll.mortal_wounds for roll in self.model_rolls)

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "placement": validate_json_value(self.placement.to_payload()),
            "tactical_resolution": validate_json_value(self.tactical_resolution.to_payload()),
            "model_rolls": [
                validate_json_value(model_roll.to_payload()) for model_roll in self.model_rolls
            ],
            "mortal_wounds": self.mortal_wounds,
        }


def resolve_rules_unit_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: RulesUnitDisembarkSelection,
    rules_unit: RulesUnitView,
    transport_placement: object,
    objective_markers: tuple[ObjectiveMarker, ...] = (),
) -> RulesUnitDisembarkResolution:
    from warhammer40k_core.engine.battlefield_state import UnitPlacement

    if type(transport_placement) is not UnitPlacement:
        raise GameLifecycleError("Rules-unit Disembark requires Transport UnitPlacement.")
    selection.attempted_placement.validate_for_view(rules_unit)
    if rules_unit.unit_instance_id != selection.unit_instance_id:
        raise GameLifecycleError("Rules-unit Disembark canonical identity drift.")
    component_ids = selection.attempted_placement.component_unit_instance_ids
    active_cargo = cargo_state.for_movement_phase(battle_round=selection.battle_round)
    violations: list[TransportOperationViolation] = []
    validation_scenario = scenario
    for component in selection.attempted_placement.component_unit_placements:
        physical_selection = DisembarkSelection(
            player_id=selection.player_id,
            battle_round=selection.battle_round,
            unit_instance_id=component.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            attempted_placement=component,
            disembark_mode=selection.disembark_mode,
            transport_movement_status=selection.transport_movement_status,
            restriction_overrides=selection.restriction_overrides,
        )
        component_resolution = resolve_disembark(
            scenario=validation_scenario,
            ruleset_descriptor=ruleset_descriptor,
            cargo_state=active_cargo,
            selection=physical_selection,
            unit=next(
                rules_component.unit
                for rules_component in rules_unit.components
                if rules_component.unit.unit_instance_id == component.unit_instance_id
            ),
            transport_placement=transport_placement,
            objective_markers=objective_markers,
        )
        violations.extend(
            violation
            for violation in component_resolution.violations
            if violation.violation_code is not TransportOperationViolationCode.UNIT_COHERENCY_BROKEN
        )
        validation_scenario = BattlefieldScenario(
            armies=validation_scenario.armies,
            battlefield_state=validation_scenario.battlefield_state.with_added_unit_placement(
                component
            ),
            present_destroyed_model_ids=validation_scenario.present_destroyed_model_ids,
        )
    coherency_result = rules_unit_coherency_result(
        scenario=validation_scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
    )
    if not coherency_result.is_coherent:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_COHERENCY_BROKEN,
                message="Disembark placement violates attached rules-unit coherency.",
                unit_instance_id=rules_unit.unit_instance_id,
            )
        )
    if violations:
        return RulesUnitDisembarkResolution(
            selection=selection,
            violations=tuple(violations),
            coherency_result=coherency_result,
            updated_cargo_state=None,
            disembarked_unit_state=None,
            transition_batch=None,
        )
    updated_cargo = active_cargo
    for component_id in component_ids:
        updated_cargo = updated_cargo.with_disembarked_unit(component_id)
    disembarked_state = DisembarkedUnitState.for_mode(
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        transport_unit_instance_id=selection.transport_unit_instance_id,
        disembark_mode=selection.disembark_mode,
        transport_movement_status=selection.transport_movement_status,
    )
    return RulesUnitDisembarkResolution(
        selection=selection,
        violations=(),
        coherency_result=coherency_result,
        updated_cargo_state=updated_cargo,
        disembarked_unit_state=disembarked_state,
        transition_batch=BattlefieldTransitionBatch(
            placements=tuple(
                ModelPlacementRecord(
                    model_instance_id=model_placement.model_instance_id,
                    placement_kind=BattlefieldPlacementKind.DISEMBARK,
                    pose=model_placement.pose,
                    source_phase=BattlePhase.MOVEMENT.value,
                    source_step="move_units",
                    source_rule_id=disembarked_state.source_rule_id,
                    source_event_id=None,
                )
                for model_placement in selection.attempted_placement.model_placements
            )
        ),
    )


def resolve_rules_unit_combat_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: RulesUnitDisembarkSelection,
    rules_unit: RulesUnitView,
    transport_placement: object,
    dice_manager: DiceRollManager,
    objective_markers: tuple[ObjectiveMarker, ...] = (),
) -> RulesUnitCombatDisembarkResolution:
    if selection.disembark_mode is not DisembarkModeKind.COMBAT_DISEMBARK:
        raise GameLifecycleError("Rules-unit Combat Disembark requires Combat mode.")
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Rules-unit Combat Disembark requires DiceRollManager.")
    tactical_resolution = resolve_rules_unit_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=replace(
            selection,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        ),
        rules_unit=rules_unit,
        transport_placement=transport_placement,
        objective_markers=objective_markers,
    )
    validation_placement, _validation_rolls = _resolve_rules_unit_combat_components(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        rules_unit=rules_unit,
        transport_placement=transport_placement,
        dice_manager=DiceRollManager(f"{selection.unit_instance_id}:combat-disembark-validation"),
        objective_markers=objective_markers,
    )
    if not validation_placement.is_valid or tactical_resolution.is_valid:
        return RulesUnitCombatDisembarkResolution(
            placement=validation_placement,
            tactical_resolution=tactical_resolution,
            model_rolls=(),
        )
    placement, model_rolls = _resolve_rules_unit_combat_components(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        rules_unit=rules_unit,
        transport_placement=transport_placement,
        dice_manager=dice_manager,
        objective_markers=objective_markers,
    )
    if not placement.is_valid:
        raise GameLifecycleError("Rules-unit Combat Disembark validation drifted.")
    return RulesUnitCombatDisembarkResolution(
        placement=placement,
        tactical_resolution=tactical_resolution,
        model_rolls=model_rolls,
    )


def _resolve_rules_unit_combat_components(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: RulesUnitDisembarkSelection,
    rules_unit: RulesUnitView,
    transport_placement: object,
    dice_manager: DiceRollManager,
    objective_markers: tuple[ObjectiveMarker, ...],
) -> tuple[
    RulesUnitDisembarkResolution,
    tuple[RulesUnitCombatDisembarkModelRoll, ...],
]:
    from warhammer40k_core.engine.battlefield_state import UnitPlacement

    if type(transport_placement) is not UnitPlacement:
        raise GameLifecycleError("Rules-unit Combat Disembark requires Transport placement.")
    selection.attempted_placement.validate_for_view(rules_unit)
    active_cargo = cargo_state.for_movement_phase(battle_round=selection.battle_round)
    validation_scenario = scenario
    violations: list[TransportOperationViolation] = []
    model_rolls: list[RulesUnitCombatDisembarkModelRoll] = []
    component_by_id = {
        component.unit.unit_instance_id: component.unit for component in rules_unit.components
    }
    for component_placement in selection.attempted_placement.component_unit_placements:
        physical_selection = DisembarkSelection(
            player_id=selection.player_id,
            battle_round=selection.battle_round,
            unit_instance_id=component_placement.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            attempted_placement=component_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=selection.transport_movement_status,
            restriction_overrides=selection.restriction_overrides,
        )
        component_result = resolve_combat_disembark(
            scenario=validation_scenario,
            ruleset_descriptor=ruleset_descriptor,
            cargo_state=active_cargo,
            selection=physical_selection,
            unit=component_by_id[component_placement.unit_instance_id],
            transport_placement=transport_placement,
            dice_manager=dice_manager,
            objective_markers=objective_markers,
        )
        violations.extend(
            violation
            for violation in component_result.placement.violations
            if violation.violation_code is not TransportOperationViolationCode.UNIT_COHERENCY_BROKEN
        )
        model_rolls.extend(
            RulesUnitCombatDisembarkModelRoll(
                component_unit_instance_id=component_placement.unit_instance_id,
                roll=roll,
                mortal_wounds_per_failed_roll=(component_result.mortal_wounds_per_failed_roll),
            )
            for roll in component_result.model_rolls
        )
        validation_scenario = BattlefieldScenario(
            armies=validation_scenario.armies,
            battlefield_state=validation_scenario.battlefield_state.with_added_unit_placement(
                component_placement
            ),
            present_destroyed_model_ids=validation_scenario.present_destroyed_model_ids,
        )
    coherency_result = rules_unit_coherency_result(
        scenario=validation_scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
    )
    if not coherency_result.is_coherent:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_COHERENCY_BROKEN,
                message="Combat Disembark placement violates attached rules-unit coherency.",
                unit_instance_id=rules_unit.unit_instance_id,
            )
        )
    if violations:
        return (
            RulesUnitDisembarkResolution(
                selection=selection,
                violations=tuple(violations),
                coherency_result=coherency_result,
                updated_cargo_state=None,
                disembarked_unit_state=None,
                transition_batch=None,
            ),
            (),
        )
    updated_cargo = active_cargo
    for component_id in selection.attempted_placement.component_unit_instance_ids:
        updated_cargo = updated_cargo.with_disembarked_unit(component_id)
    disembarked_state = DisembarkedUnitState.for_mode(
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        transport_unit_instance_id=selection.transport_unit_instance_id,
        disembark_mode=selection.disembark_mode,
        transport_movement_status=selection.transport_movement_status,
    )
    return (
        RulesUnitDisembarkResolution(
            selection=selection,
            violations=(),
            coherency_result=coherency_result,
            updated_cargo_state=updated_cargo,
            disembarked_unit_state=disembarked_state,
            transition_batch=BattlefieldTransitionBatch(
                placements=tuple(
                    ModelPlacementRecord(
                        model_instance_id=model_placement.model_instance_id,
                        placement_kind=BattlefieldPlacementKind.DISEMBARK,
                        pose=model_placement.pose,
                        source_phase=BattlePhase.MOVEMENT.value,
                        source_step="move_units",
                        source_rule_id=disembarked_state.source_rule_id,
                        source_event_id=None,
                    )
                    for model_placement in selection.attempted_placement.model_placements
                )
            ),
        ),
        tuple(model_rolls),
    )


def apply_rules_unit_disembark_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    disembark: RulesUnitDisembarkResolution,
) -> BattlefieldRuntimeState:
    if not disembark.is_valid:
        raise GameLifecycleError("Invalid rules-unit Disembark cannot mutate battlefield state.")
    return disembark.selection.attempted_placement.add_to_battlefield(battlefield_state)


def apply_rules_unit_combat_disembark_to_state(
    *,
    state: GameState,
    decisions: DecisionController,
    combat_disembark: RulesUnitCombatDisembarkResolution,
    result: DecisionResult,
    dice_manager: DiceRollManager,
) -> DecisionRequest | None:
    from warhammer40k_core.engine.damage_allocation import continue_mortal_wound_application
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_application_progress import (
        start_hazardous_mortal_wound_application,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Rules-unit Combat Disembark requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Rules-unit Combat Disembark requires DecisionController.")
    if type(combat_disembark) is not RulesUnitCombatDisembarkResolution:
        raise GameLifecycleError("Rules-unit Combat Disembark requires grouped resolution.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Rules-unit Combat Disembark requires DecisionResult.")
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Rules-unit Combat Disembark requires DiceRollManager.")
    if not combat_disembark.is_valid:
        raise GameLifecycleError("Invalid rules-unit Combat Disembark cannot mutate state.")
    disembark = combat_disembark.placement
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Rules-unit Combat Disembark requires battlefield_state.")
    if disembark.updated_cargo_state is None or disembark.disembarked_unit_state is None:
        raise GameLifecycleError(
            "Valid rules-unit Combat Disembark requires complete state records."
        )
    state.replace_battlefield_state(
        apply_rules_unit_disembark_to_battlefield(
            battlefield_state=battlefield_state,
            disembark=disembark,
        )
    )
    state.replace_transport_cargo_state(disembark.updated_cargo_state)
    state.record_disembarked_unit_state(disembark.disembarked_unit_state)
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Rules-unit Combat Disembark requires active movement selection.")
    if movement_state.active_selection.unit_instance_id != disembark.selection.unit_instance_id:
        raise GameLifecycleError("Rules-unit Combat Disembark active movement selection drift.")
    state.replace_movement_phase_state(
        movement_state.with_activation_complete(
            disembark.selection.unit_instance_id,
            maximum_model_distance_inches=0.0,
            maximum_model_horizontal_distance_inches=0.0,
        )
    )
    decisions.event_log.append(
        "unit_disembarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": disembark.selection.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": disembark.selection.unit_instance_id,
            "transport_unit_instance_id": (disembark.selection.transport_unit_instance_id),
            "disembark_mode": disembark.selection.disembark_mode.value,
            "transport_movement_status": (disembark.selection.transport_movement_status.value),
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_disembarked",
            "updated_cargo_state": validate_json_value(disembark.updated_cargo_state.to_payload()),
            "disembarked_unit_state": validate_json_value(
                disembark.disembarked_unit_state.to_payload()
            ),
            "transition_batch": validate_json_value(disembark.transition_batch.to_payload())
            if disembark.transition_batch is not None
            else None,
            "tactical_fallback_violations": [
                validate_json_value(violation.to_payload())
                for violation in combat_disembark.tactical_resolution.violations
            ],
        },
    )
    mortal_wounds = combat_disembark.mortal_wounds
    combat_payload = validate_json_value(combat_disembark.to_payload())
    if mortal_wounds == 0:
        _emit_rules_unit_combat_hazard_resolved(
            decisions=decisions,
            combat_payload=combat_payload,
            mortal_wounds=0,
            application=None,
        )
        return None
    source_context = validate_json_value(
        {
            "source_kind": TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            "source_rule_id": CORE_HAZARD_ROLLS_RULE_ID,
            "disembark_payload_kind": RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND,
            "player_id": disembark.selection.player_id,
            "battle_round": disembark.selection.battle_round,
            "unit_instance_id": disembark.selection.unit_instance_id,
            "transport_unit_instance_id": disembark.selection.transport_unit_instance_id,
            "disembark_mode": DisembarkModeKind.COMBAT_DISEMBARK.value,
            "mortal_wounds": mortal_wounds,
            "disembark": combat_payload,
        }
    )
    progress = start_hazardous_mortal_wound_application(
        state=state,
        application_id=(
            f"{disembark.selection.unit_instance_id}:combat_disembark:"
            f"transport-hazard-mortal-wounds:r{state.battle_round}"
        ),
        source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
        source_context=source_context,
        target_unit_instance_id=disembark.selection.unit_instance_id,
        destroying_player_id=disembark.selection.player_id,
        mortal_wounds=mortal_wounds,
        source_step="transport_hazard_mortal_wounds",
    )
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice_manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return routed.request
    if routed.application is None:
        raise GameLifecycleError(
            "Rules-unit Combat Disembark hazard did not produce an application."
        )
    _emit_rules_unit_combat_hazard_resolved(
        decisions=decisions,
        combat_payload=combat_payload,
        mortal_wounds=mortal_wounds,
        application=routed.application,
    )
    return None


def apply_rules_unit_combat_disembark_feel_no_pain_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> DecisionRequest | None:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
        mortal_wound_resolution_source_context,
        resolve_mortal_wound_decision,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Rules-unit Combat Disembark FNP requires GameState.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Rules-unit Combat Disembark FNP requires DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Rules-unit Combat Disembark FNP requires DecisionController.")
    record = decisions.record_for_result(result)
    request = record.request
    if not is_mortal_wound_resolution_request(request):
        raise GameLifecycleError("Rules-unit Combat Disembark FNP requires mortal wound context.")
    source_context = mortal_wound_resolution_source_context(request)
    combat_payload, mortal_wounds = _rules_unit_combat_hazard_context(source_context)
    routed = resolve_mortal_wound_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return routed.request
    if routed.application is None:
        raise GameLifecycleError("Rules-unit Combat Disembark FNP did not finish hazard routing.")
    _emit_rules_unit_combat_hazard_resolved(
        decisions=decisions,
        combat_payload=combat_payload,
        mortal_wounds=mortal_wounds,
        application=routed.application,
    )
    return None


def _rules_unit_combat_hazard_context(
    source_context: JsonValue,
) -> tuple[JsonValue, int]:
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Rules-unit Combat Disembark hazard context is invalid.")
    if source_context.get("source_kind") != TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Rules-unit Combat Disembark hazard source kind drift.")
    if source_context.get("source_rule_id") != CORE_HAZARD_ROLLS_RULE_ID:
        raise GameLifecycleError("Rules-unit Combat Disembark hazard source rule drift.")
    if source_context.get("disembark_payload_kind") != RULES_UNIT_COMBAT_DISEMBARK_PAYLOAD_KIND:
        raise GameLifecycleError("Rules-unit Combat Disembark payload kind drift.")
    if source_context.get("disembark_mode") != DisembarkModeKind.COMBAT_DISEMBARK.value:
        raise GameLifecycleError("Rules-unit Combat Disembark mode drift.")
    mortal_wounds = source_context.get("mortal_wounds")
    if type(mortal_wounds) is not int or mortal_wounds <= 0:
        raise GameLifecycleError("Rules-unit Combat Disembark mortal wounds drift.")
    combat_payload = source_context.get("disembark")
    if not isinstance(combat_payload, dict):
        raise GameLifecycleError("Rules-unit Combat Disembark payload is invalid.")
    if combat_payload.get("mortal_wounds") != mortal_wounds:
        raise GameLifecycleError("Rules-unit Combat Disembark hazard total drift.")
    placement = combat_payload.get("placement")
    tactical = combat_payload.get("tactical_resolution")
    model_rolls = combat_payload.get("model_rolls")
    if not isinstance(placement, dict) or placement.get("is_valid") is not True:
        raise GameLifecycleError("Rules-unit Combat Disembark placement payload drift.")
    if not isinstance(tactical, dict) or tactical.get("is_valid") is not False:
        raise GameLifecycleError("Rules-unit Combat Disembark tactical payload drift.")
    if not isinstance(model_rolls, list):
        raise GameLifecycleError("Rules-unit Combat Disembark model rolls are invalid.")
    rolled_mortal_wounds = 0
    for model_roll in model_rolls:
        if not isinstance(model_roll, dict):
            raise GameLifecycleError("Rules-unit Combat Disembark model roll is invalid.")
        roll_mortal_wounds = model_roll.get("mortal_wounds")
        if type(roll_mortal_wounds) is not int or roll_mortal_wounds < 0:
            raise GameLifecycleError("Rules-unit Combat Disembark model mortal wounds drift.")
        rolled_mortal_wounds += roll_mortal_wounds
    if rolled_mortal_wounds != mortal_wounds:
        raise GameLifecycleError("Rules-unit Combat Disembark model roll total drift.")
    selection = placement.get("selection")
    if not isinstance(selection, dict):
        raise GameLifecycleError("Rules-unit Combat Disembark selection is invalid.")
    for field in (
        "player_id",
        "unit_instance_id",
        "transport_unit_instance_id",
        "battle_round",
        "disembark_mode",
    ):
        if selection.get(field) != source_context.get(field):
            raise GameLifecycleError(f"Rules-unit Combat Disembark source {field} drift.")
    return validate_json_value(combat_payload), mortal_wounds


def _emit_rules_unit_combat_hazard_resolved(
    *,
    decisions: DecisionController,
    combat_payload: JsonValue,
    mortal_wounds: int,
    application: MortalWoundApplication | None,
) -> None:
    decisions.event_log.append(
        TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
        {
            "source_rule_id": CORE_HAZARD_ROLLS_RULE_ID,
            "source_kind": TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            "disembark_mode": DisembarkModeKind.COMBAT_DISEMBARK.value,
            "disembark": validate_json_value(combat_payload),
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": None
            if application is None
            else validate_json_value(application.to_payload()),
            "pending_mortal_wound_request": None,
            "pending_mortal_wound_request_id": None,
        },
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
