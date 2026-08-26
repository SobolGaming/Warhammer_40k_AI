from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_presence import rules_unit_has_placed_alive_model
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    resolve_unit_movement_endpoint_coherency,
)
from warhammer40k_core.geometry.pathing import PathWitness

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def triggered_movement_unit_has_placed_living_source(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    _require_game_state(state)
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return rules_unit_has_placed_alive_model(state=state, rules_unit=rules_unit)


def triggered_movement_source_model_placements(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[ModelPlacement, ...]:
    """Return the placed living models authorized to make a triggered move."""

    _require_scenario(scenario)
    _require_unit_placement(unit_placement)
    return tuple(
        sorted(
            (
                placement
                for placement in unit_placement.model_placements
                if scenario.model_instance_for_placement(placement).is_alive
                and scenario.model_is_present_at_placement(placement)
            ),
            key=lambda placement: placement.model_instance_id,
        )
    )


def require_triggered_movement_source_model_placements(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[ModelPlacement, ...]:
    placements = triggered_movement_source_model_placements(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    if not placements:
        raise GameLifecycleError(
            "Triggered movement requires at least one placed living source model."
        )
    return placements


def validate_triggered_movement_source_witness(
    *,
    witness: PathWitness,
    source_model_placements: tuple[ModelPlacement, ...],
) -> None:
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Triggered movement requires a PathWitness.")
    placements = _require_non_empty_model_placements(source_model_placements)
    expected_model_ids = tuple(sorted(placement.model_instance_id for placement in placements))
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError(
            "Triggered movement witness must match selected unit living models."
        )


def merge_triggered_movement_source_endpoints(
    *,
    unit_placement: UnitPlacement,
    source_model_placements: tuple[ModelPlacement, ...],
    witness: PathWitness,
) -> UnitPlacement:
    _require_unit_placement(unit_placement)
    validate_triggered_movement_source_witness(
        witness=witness,
        source_model_placements=source_model_placements,
    )
    source_ids = {placement.model_instance_id for placement in source_model_placements}
    return unit_placement.with_model_placements(
        tuple(
            placement.with_pose(witness.final_pose_for_model(placement.model_instance_id))
            if placement.model_instance_id in source_ids
            else placement
            for placement in unit_placement.model_placements
        )
    )


def resolve_triggered_movement_source_coherency(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    before: UnitPlacement,
    attempted: UnitPlacement,
    source_model_placements: tuple[ModelPlacement, ...],
    displacement_kind: ModelDisplacementKind,
) -> tuple[UnitCoherencyResult, MovementRollbackRecord | None]:
    _require_scenario(scenario)
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Triggered movement source coherency requires RulesetDescriptor.")
    _require_unit_placement(before)
    _require_unit_placement(attempted)
    source_placements = _require_non_empty_model_placements(source_model_placements)
    source_ids = {placement.model_instance_id for placement in source_placements}
    before_source = before.with_model_placements(source_placements)
    attempted_source = attempted.with_model_placements(
        tuple(
            placement
            for placement in attempted.model_placements
            if placement.model_instance_id in source_ids
        )
    )
    _, coherency_result, source_rollback = resolve_unit_movement_endpoint_coherency(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=before_source,
        attempted=attempted_source,
        displacement_kind=displacement_kind,
    )
    if source_rollback is None:
        return (coherency_result, None)
    return (
        coherency_result,
        MovementRollbackRecord(
            unit_instance_id=before.unit_instance_id,
            displacement_kind=displacement_kind,
            before_placement=before,
            attempted_placement=attempted,
            coherency_result=coherency_result,
        ),
    )


def retained_triggered_movement_blocker_ids(
    *,
    scenario: BattlefieldScenario,
    moving_player_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return retained destroyed friendly and enemy transit blockers."""

    _require_scenario(scenario)
    player_id = _validate_identifier("moving_player_id", moving_player_id)
    retained_ids = frozenset(scenario.present_destroyed_model_ids)
    friendly: list[str] = []
    enemy: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        destination = friendly if placed_army.player_id == player_id else enemy
        destination.extend(
            placement.model_instance_id
            for unit_placement in placed_army.unit_placements
            for placement in unit_placement.model_placements
            if placement.model_instance_id in retained_ids
            and scenario.model_is_present_at_placement(placement)
        )
    witnessed_ids = {*friendly, *enemy}
    if witnessed_ids != set(retained_ids):
        raise GameLifecycleError(
            "Triggered movement retained blocker inventory does not match the scenario."
        )
    return (tuple(sorted(friendly)), tuple(sorted(enemy)))


def _require_non_empty_model_placements(
    values: tuple[ModelPlacement, ...],
) -> tuple[ModelPlacement, ...]:
    if type(values) is not tuple or not values:
        raise GameLifecycleError("Triggered movement source placements must be a non-empty tuple.")
    if any(type(value) is not ModelPlacement for value in values):
        raise GameLifecycleError(
            "Triggered movement source placements must contain ModelPlacement values."
        )
    model_ids = tuple(value.model_instance_id for value in values)
    if len(model_ids) != len(set(model_ids)):
        raise GameLifecycleError("Triggered movement source placements must be unique.")
    return tuple(sorted(values, key=lambda value: value.model_instance_id))


def _require_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Triggered movement source authority requires GameState.")


def _require_scenario(scenario: object) -> None:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError(
            "Triggered movement source authority requires BattlefieldScenario."
        )


def _require_unit_placement(unit_placement: object) -> None:
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Triggered movement source authority requires UnitPlacement.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "merge_triggered_movement_source_endpoints",
    "require_triggered_movement_source_model_placements",
    "resolve_triggered_movement_source_coherency",
    "retained_triggered_movement_blocker_ids",
    "triggered_movement_source_model_placements",
    "triggered_movement_unit_has_placed_living_source",
    "validate_triggered_movement_source_witness",
)
