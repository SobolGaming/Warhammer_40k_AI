from __future__ import annotations

from warhammer40k_core.core.attachment_eligibility import AttachmentEligibility
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.unit_factory import UnitInstance


def validate_physical_unit_ids(
    *, army_id: str, units: tuple[UnitInstance, ...], error_type: type[ValueError]
) -> None:
    seen: set[str] = set()
    for unit in units:
        if unit.unit_instance_id in seen:
            raise error_type("ArmyDefinition units must have unique IDs.")
        seen.add(unit.unit_instance_id)
    for unit in units:
        if not unit.unit_instance_id.startswith(f"{army_id}:"):
            raise error_type("ArmyDefinition unit IDs must be scoped to army_id.")


def validate_attached_unit_references(
    *,
    army_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...],
    error_type: type[ValueError],
) -> None:
    requested_army_id = IdentifierValidator(error_type)("army_id", army_id)
    if requested_army_id.startswith("army:"):
        raise error_type("army_id must not include the stable identity prefix.")
    unit_ids = {unit.unit_instance_id for unit in units}
    claimed_component_ids: set[str] = set()
    for attached_unit in attached_units:
        if not attached_unit.attached_unit_instance_id.startswith(
            f"attached-unit:{requested_army_id}:"
        ):
            raise error_type("AttachedUnitFormation attached ID must be scoped to army_id.")
        if attached_unit.attached_unit_instance_id in unit_ids:
            raise error_type("AttachedUnitFormation identity must not be a physical unit.")
        for component_id in attached_unit.component_unit_instance_ids:
            if component_id not in unit_ids:
                raise error_type("AttachedUnitFormation references an unknown unit.")
            if component_id in claimed_component_ids:
                raise error_type("AttachedUnitFormation component units must not overlap.")
            claimed_component_ids.add(component_id)


def required_attachment_eligibility(
    datasheet: DatasheetDefinition,
    *,
    error_type: type[ValueError],
) -> AttachmentEligibility:
    if type(datasheet) is not DatasheetDefinition:
        raise error_type("Attachment eligibility lookup requires a DatasheetDefinition.")
    eligibilities = datasheet.attachment_eligibilities
    if not eligibilities:
        raise error_type("AttachmentDeclaration source datasheet has no attachment eligibility.")
    if len(eligibilities) != 1:
        raise error_type(
            "AttachmentDeclaration source datasheet must declare exactly one attachment role."
        )
    return eligibilities[0]
