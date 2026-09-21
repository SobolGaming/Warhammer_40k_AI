"""Shared roster attachment construction and certification."""

from __future__ import annotations

from warhammer40k_core.core.attachment_eligibility import (
    AttachmentRole,
    AttachmentTargetEligibility,
)
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.engine import attachment_mustering_validation as _attachment_mustering
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    ArmyMusterRequest,
    RosterLegalityViolation,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.model_keyword_grants import unit_with_attached_role_evidence
from warhammer40k_core.engine.roster_bearer_validation import RosterModelResolver
from warhammer40k_core.engine.unit_factory import UnitFactoryError, UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_roster_construction_2026_09 as construction_source,
)


def append_attachment_violations(
    *,
    request: ArmyMusterRequest,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    model_resolver: RosterModelResolver,
    violations: list[RosterLegalityViolation],
) -> None:
    if not request.attachment_declarations and not any(
        _datasheet_has_attachment_role(datasheet=row, role=AttachmentRole.SUPPORT)
        for row in datasheets_by_selection_id.values()
    ):
        return
    if len(datasheets_by_selection_id) != len(request.unit_selections):
        # Existing unit-selection diagnostics are authoritative; no partial formation is certified.
        return
    try:
        units = tuple(
            model_resolver.unit(
                datasheet=datasheets_by_selection_id[row.unit_selection_id],
                unit_selection_id=row.unit_selection_id,
            )
            for row in request.unit_selections
        )
        resolve_attached_unit_formations(
            request=request, units=units, datasheets_by_selection_id=datasheets_by_selection_id
        )
    except (ArmyMusteringError, UnitFactoryError) as exc:
        violations.append(
            RosterLegalityViolation(
                violation_code="attachment_declaration_invalid",
                message=str(exc),
                source_id=construction_source.SUPPORT_SOURCE_ID,
            )
        )


def resolve_attached_unit_formations(
    *,
    request: ArmyMusterRequest,
    units: tuple[UnitInstance, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
) -> tuple[tuple[UnitInstance, ...], tuple[AttachedUnitFormation, ...]]:
    if not request.attachment_declarations:
        _validate_required_support_attachments(
            request=request,
            datasheets_by_selection_id=datasheets_by_selection_id,
            attached_source_selection_ids=set(),
        )
        return units, ()
    units_by_selection_id = {
        unit.unit_instance_id.removeprefix(f"{request.army_id}:"): unit for unit in units
    }
    grouped: dict[
        str,
        dict[AttachmentRole, tuple[UnitInstance, AttachmentTargetEligibility]],
    ] = {}
    for declaration in request.attachment_declarations:
        source_unit = units_by_selection_id.get(declaration.source_unit_selection_id)
        bodyguard_unit = units_by_selection_id.get(declaration.bodyguard_unit_selection_id)
        if source_unit is None:
            raise ArmyMusteringError("AttachmentDeclaration source unit was not mustered.")
        if bodyguard_unit is None:
            raise ArmyMusteringError("AttachmentDeclaration bodyguard unit was not mustered.")
        source_datasheet = datasheets_by_selection_id[declaration.source_unit_selection_id]
        bodyguard_datasheet = datasheets_by_selection_id[declaration.bodyguard_unit_selection_id]
        eligibility = _attachment_mustering.required_attachment_eligibility(
            source_datasheet,
            error_type=ArmyMusteringError,
        )
        target = eligibility.target_for_bodyguard_datasheet_id(bodyguard_datasheet.datasheet_id)
        if target is None:
            raise ArmyMusteringError(
                "AttachmentDeclaration bodyguard datasheet is not allowed by source datasheet."
            )
        selected_source_wargear_ids = {
            wargear_id for model in source_unit.own_models for wargear_id in model.wargear_ids
        }
        if not set(target.required_wargear_ids).issubset(selected_source_wargear_ids):
            raise ArmyMusteringError(
                "AttachmentDeclaration source unit does not satisfy the target wargear "
                "requirements."
            )
        role_group = grouped.setdefault(declaration.bodyguard_unit_selection_id, {})
        if eligibility.role in role_group:
            raise ArmyMusteringError(
                "AttachmentDeclaration exceeds one Leader or one Support per bodyguard."
            )
        role_group[eligibility.role] = (source_unit, target)

    _validate_required_support_attachments(
        request=request,
        datasheets_by_selection_id=datasheets_by_selection_id,
        attached_source_selection_ids={
            declaration.source_unit_selection_id for declaration in request.attachment_declarations
        },
    )

    formations: list[AttachedUnitFormation] = []
    roles_by_unit_id: dict[str, str] = {}
    claimed_component_ids: set[str] = set()
    for bodyguard_selection_id in sorted(grouped):
        bodyguard_unit = units_by_selection_id[bodyguard_selection_id]
        role_group = grouped[bodyguard_selection_id]
        leader_ids = tuple(
            sorted(
                unit.unit_instance_id
                for role, (unit, _target) in role_group.items()
                if role is AttachmentRole.LEADER
            )
        )
        support_ids = tuple(
            sorted(
                unit.unit_instance_id
                for role, (unit, _target) in role_group.items()
                if role is AttachmentRole.SUPPORT
            )
        )
        component_ids = tuple(sorted((bodyguard_unit.unit_instance_id, *leader_ids, *support_ids)))
        overlap = claimed_component_ids.intersection(component_ids)
        if overlap:
            raise ArmyMusteringError(
                "AttachmentDeclaration cannot place a unit in multiple attached units."
            )
        claimed_component_ids.update(component_ids)
        attached_unit_id = f"attached-unit:{request.army_id}:{bodyguard_selection_id}"
        source_id = f"attached-unit-join:{request.army_id}:{bodyguard_selection_id}"
        attachment_source_ids = tuple(
            sorted(
                {
                    attachment_source_id
                    for _unit, target in role_group.values()
                    for attachment_source_id in target.source_ids
                }
            )
        )
        formations.append(
            AttachedUnitFormation(
                attached_unit_instance_id=attached_unit_id,
                bodyguard_unit_instance_id=bodyguard_unit.unit_instance_id,
                leader_unit_instance_ids=leader_ids,
                support_unit_instance_ids=support_ids,
                component_unit_instance_ids=component_ids,
                source_id=source_id,
                attachment_source_ids=attachment_source_ids,
            )
        )
        roles_by_unit_id[bodyguard_unit.unit_instance_id] = "bodyguard"
        for unit_id in leader_ids:
            roles_by_unit_id[unit_id] = "leader"
        for unit_id in support_ids:
            roles_by_unit_id[unit_id] = "support"

    return (
        tuple(
            unit_with_attached_role_evidence(
                unit,
                role=roles_by_unit_id.get(unit.unit_instance_id),
            )
            for unit in units
        ),
        tuple(sorted(formations, key=lambda formation: formation.attached_unit_instance_id)),
    )


def _validate_required_support_attachments(
    *,
    request: ArmyMusterRequest,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    attached_source_selection_ids: set[str],
) -> None:
    for selection in request.unit_selections:
        datasheet = datasheets_by_selection_id[selection.unit_selection_id]
        if (
            _datasheet_has_attachment_role(datasheet=datasheet, role=AttachmentRole.SUPPORT)
            and selection.unit_selection_id not in attached_source_selection_ids
        ):
            raise ArmyMusteringError(
                "Support units must be declared as part of an attached unit during mustering."
            )


def _datasheet_has_attachment_role(
    *,
    datasheet: DatasheetDefinition,
    role: AttachmentRole,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ArmyMusteringError("Attachment role lookup requires a DatasheetDefinition.")
    if type(role) is not AttachmentRole:
        raise ArmyMusteringError("Attachment role lookup requires an AttachmentRole.")
    return any(eligibility.role is role for eligibility in datasheet.attachment_eligibilities)
