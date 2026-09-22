"""Shared source-backed Embark validation for every movement consumer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phase_movement_history import PhaseMovementRecord

# Shared transport geometry remains owned by transports during this focused extraction.
# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.transport_embark_groups import (
    cargo_model_count,
    embark_transition_batch_for_rules_unit,
    embarking_rules_unit_placement,
)
from warhammer40k_core.engine.unit_rule_effects import embark_transport_forbidden_effect_source_ids
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_embark_setup_turn_2026_09 as source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.transports import (
        EmbarkResolution,
        EmbarkSelection,
        TransportCargoState,
    )


def resolve_embark(
    *,
    scenario: BattlefieldScenario,
    movement_history: tuple[PhaseMovementRecord, ...],
    turn_player_id: str,
    cargo_state: TransportCargoState,
    selection: EmbarkSelection,
    unit_placement: UnitPlacement,
    transport_placement: UnitPlacement,
    persisting_effects: tuple[PersistingEffect, ...] = (),
) -> EmbarkResolution:
    from warhammer40k_core.core.validation import IdentifierValidator
    from warhammer40k_core.engine.transport_disembark_geometry import (
        geometry_models_for_unit_placement,
    )
    from warhammer40k_core.engine.transports import (
        _CORE_TRANSPORT_RULE_ID,
        _EMBARK_DISTANCE_INCHES,
        EmbarkResolution,
        EmbarkSelection,
        TransportCargoState,
        TransportOperationViolation,
        TransportOperationViolationCode,
        _append_transport_common_violations,
    )

    IdentifierValidator(GameLifecycleError)("Embark turn_player_id", turn_player_id)
    if type(movement_history) is not tuple or any(
        type(row) is not PhaseMovementRecord for row in movement_history
    ):
        raise GameLifecycleError("Embark requires typed movement history.")
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("resolve_embark requires a BattlefieldScenario.")
    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("resolve_embark requires a TransportCargoState.")
    if type(selection) is not EmbarkSelection:
        raise GameLifecycleError("resolve_embark requires an EmbarkSelection.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("resolve_embark unit_placement must be UnitPlacement.")
    if type(transport_placement) is not UnitPlacement:
        raise GameLifecycleError("resolve_embark transport_placement must be UnitPlacement.")
    if type(persisting_effects) is not tuple:
        raise GameLifecycleError("resolve_embark persisting_effects must be a tuple.")
    for effect in persisting_effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("resolve_embark persisting_effects must contain effects.")
    active_cargo = cargo_state.for_movement_phase(battle_round=selection.battle_round)
    scenario.unit_instance_for_placement(unit_placement)
    transport = scenario.unit_instance_for_placement(transport_placement)
    rules_unit, rules_unit_placement = embarking_rules_unit_placement(
        scenario=scenario,
        selected_unit_placement=unit_placement,
    )
    violations: list[TransportOperationViolation] = []
    _append_transport_common_violations(
        violations=violations,
        cargo_state=active_cargo,
        selection_player_id=selection.player_id,
        transport=transport,
        transport_placement=transport_placement,
    )
    if selection.unit_instance_id not in {
        rules_unit.unit_instance_id,
        unit_placement.unit_instance_id,
    }:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Embark placement does not match the selected rules unit.",
                unit_instance_id=selection.unit_instance_id,
            )
        )
    if rules_unit_placement.player_id != selection.player_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
                message="Embarking unit must belong to the selected player.",
                unit_instance_id=unit_placement.unit_instance_id,
            )
        )
    if any(
        active_cargo.contains_unit(component_id)
        for component_id in rules_unit.component_unit_instance_ids
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_ALREADY_EMBARKED,
                message="Unit is already embarked in this Transport.",
                unit_instance_id=rules_unit.unit_instance_id,
            )
        )
    forbidden_source_ids = embark_transport_forbidden_effect_source_ids(
        persisting_effects,
        owner_player_id=selection.player_id,
    )
    for source_rule_id in forbidden_source_ids:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.EMBARK_FORBIDDEN_BY_EFFECT,
                message="A persisting rule effect forbids this unit from Embarking.",
                unit_instance_id=rules_unit.unit_instance_id,
                source_rule_id=source_rule_id,
            )
        )
    if embark_after_setup_forbidden(
        rules_unit=rules_unit,
        movement_history=movement_history,
        turn_player_id=turn_player_id,
        selection=selection,
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.EMBARK_AFTER_SETUP_FORBIDDEN,
                message="Unit cannot Embark after it was set up on the battlefield this turn.",
                unit_instance_id=rules_unit.unit_instance_id,
                source_rule_id=source.EMBARK_POLICY.source_rule_id,
            )
        )
    if any(
        not active_cargo.capacity_profile.allows_unit(component.unit)
        for component in rules_unit.living_components
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.CAPACITY_EXCEEDED,
                message="Transport capacity profile does not allow this unit.",
                unit_instance_id=rules_unit.unit_instance_id,
                source_rule_id=active_cargo.capacity_profile.source_id,
            )
        )
    if (
        cargo_model_count(
            scenario=scenario,
            embarked_unit_instance_ids=active_cargo.embarked_unit_instance_ids,
        )
        + len(rules_unit.alive_models())
        > active_cargo.capacity_profile.max_model_count
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.CAPACITY_EXCEEDED,
                message="Transport capacity would be exceeded.",
                unit_instance_id=rules_unit.unit_instance_id,
                source_rule_id=active_cargo.capacity_profile.source_id,
            )
        )
    transport_models = geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=transport_placement,
    )
    for model in rules_unit_placement.geometry_models(scenario):
        if not _model_within_any_transport_model(
            model,
            transport_models=transport_models,
            distance_inches=_EMBARK_DISTANCE_INCHES,
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.EMBARK_DISTANCE,
                    message="Embark requires every model to end within 3 inches of the Transport.",
                    unit_instance_id=rules_unit.unit_instance_id,
                    model_instance_id=model.model_id,
                    blocker_id=transport_placement.unit_instance_id,
                    source_rule_id=_CORE_TRANSPORT_RULE_ID,
                )
            )
    if violations:
        return EmbarkResolution(
            selection=selection,
            violations=tuple(violations),
            updated_cargo_state=None,
            transition_batch=None,
        )
    updated_cargo = active_cargo
    for component_id in rules_unit_placement.component_unit_instance_ids:
        updated_cargo = updated_cargo.with_embarked_unit(component_id)
    return EmbarkResolution(
        selection=selection,
        violations=(),
        updated_cargo_state=updated_cargo,
        transition_batch=embark_transition_batch_for_rules_unit(
            rules_unit_placement=rules_unit_placement,
            transport_unit_instance_id=transport_placement.unit_instance_id,
            source_rule_id=_CORE_TRANSPORT_RULE_ID,
        ),
    )


def embark_after_setup_forbidden(
    *,
    rules_unit: RulesUnitView,
    movement_history: tuple[PhaseMovementRecord, ...],
    turn_player_id: str,
    selection: EmbarkSelection,
) -> bool:
    """A rules-unit setup survives later movement and component identity changes."""
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.transports import TransportRestrictionOverrideKind

    model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    setups = tuple(
        row
        for row in movement_history
        if row.setup_kind is not None
        and row.battle_round == selection.battle_round
        and row.turn_player_id == turn_player_id
        and (
            row.unit_instance_id == rules_unit.unit_instance_id
            or model_ids.intersection(row.model_instance_ids)
        )
    )
    return source.EMBARK_POLICY.forbids_setup_this_turn and any(
        row.setup_kind is not BattlefieldPlacementKind.DISEMBARK
        or not selection.has_override(TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK)
        for row in setups
    )


def _model_within_any_transport_model(
    model: Model,
    *,
    transport_models: tuple[Model, ...],
    distance_inches: float,
) -> bool:
    return any(
        model.base_distance_to(transport_model) <= distance_inches
        for transport_model in transport_models
    )
