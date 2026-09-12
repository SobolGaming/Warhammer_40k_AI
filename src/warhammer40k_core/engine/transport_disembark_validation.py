from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.transports import (
    ASSAULT_DISEMBARK_MOVE_SOURCE_ID,
    SHOCK_DISEMBARK_MOVE_SOURCE_ID,
    DisembarkModeKind,
    DisembarkSelection,
    TransportCargoState,
    TransportMovementStatus,
    TransportOperationViolation,
    TransportOperationViolationCode,
    TransportRestrictionOverrideKind,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

_CORE_TRANSPORT_RULE_ID = "core_rules_transports"


def append_disembark_eligibility_violations(
    *,
    violations: list[TransportOperationViolation],
    active_cargo: TransportCargoState,
    scenario: BattlefieldScenario,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    require_started_phase_embarked: bool,
) -> None:
    if require_started_phase_embarked and (
        scenario.battlefield_state.unit_placement_or_none(transport_placement.unit_instance_id)
        != transport_placement
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.TRANSPORT_PLACEMENT_DRIFT,
                message="Disembark requires the current battlefield Transport placement.",
                unit_instance_id=unit.unit_instance_id,
                blocker_id=transport_placement.unit_instance_id,
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
            )
        )
    if require_started_phase_embarked and (
        not active_cargo.unit_started_phase_embarked(unit.unit_instance_id)
        or active_cargo.unit_disembarked_this_phase(unit.unit_instance_id)
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_DID_NOT_START_PHASE_EMBARKED,
                message="Disembark requires no embark into this Transport this phase.",
                unit_instance_id=unit.unit_instance_id,
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
            )
        )
    shock_is_permitted = (
        selection.disembark_mode is DisembarkModeKind.SHOCK_DISEMBARK
        and selection.has_override(TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK)
    )
    if (
        selection.transport_movement_status
        in {
            TransportMovementStatus.ADVANCE,
            TransportMovementStatus.FALL_BACK,
        }
        and not selection.has_override(
            TransportRestrictionOverrideKind.ALLOW_DISEMBARK_AFTER_ADVANCE_OR_FALL_BACK
        )
        and not shock_is_permitted
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.TRANSPORT_ADVANCED_OR_FELL_BACK,
                message="Units cannot Disembark after their Transport Advanced or Fell Back.",
                unit_instance_id=unit.unit_instance_id,
                blocker_id=transport_placement.unit_instance_id,
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
            )
        )
    if selection.disembark_mode is DisembarkModeKind.ASSAULT_DISEMBARK and not (
        selection.has_override(TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK)
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=(
                    TransportOperationViolationCode.ASSAULT_DISEMBARK_PERMISSION_REQUIRED
                ),
                message="Assault Disembark requires a source-backed permitting rule.",
                unit_instance_id=unit.unit_instance_id,
                blocker_id=transport_placement.unit_instance_id,
                source_rule_id=ASSAULT_DISEMBARK_MOVE_SOURCE_ID,
            )
        )
    if selection.disembark_mode is DisembarkModeKind.SHOCK_DISEMBARK and not (
        selection.has_override(TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK)
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=(
                    TransportOperationViolationCode.SHOCK_DISEMBARK_PERMISSION_REQUIRED
                ),
                message="Shock Disembark requires a source-backed permitting rule.",
                unit_instance_id=unit.unit_instance_id,
                blocker_id=transport_placement.unit_instance_id,
                source_rule_id=SHOCK_DISEMBARK_MOVE_SOURCE_ID,
            )
        )
