from __future__ import annotations

from dataclasses import dataclass, replace

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogError
from warhammer40k_core.core.attachment_eligibility import (
    AttachmentEligibility,
    AttachmentRole,
    AttachmentTargetEligibility,
)
from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    ModelProfileDefinition,
)
from warhammer40k_core.core.detachment import DetachmentDefinition, EnhancementDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.validation import FixedMessageIdentifierValidator
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
)
from warhammer40k_core.engine.list_validation import (
    UnitMusterSelection,
    resolve_model_profile_selections,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.list_validation_errors import (
    ListValidationError,
)
from warhammer40k_core.engine.roster_points import (
    RosterEnhancementPointValue,
    RosterUnitPointValue,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.rules.mfm_source import (
    MfmDetachmentRecord,
    MfmEnhancementRecord,
    MfmFactionRecord,
    MfmLeaderAllowance,
    MfmSourcePackage,
    MfmUnitCostBracket,
    MfmUnitCostRow,
    MfmUnitRecord,
    source_label_slug,
)


class ArmyPointsError(ValueError):
    """Raised when MFM army points cannot be calculated from structured source data."""


@dataclass(frozen=True, slots=True)
class MfmUnitPointLine:
    unit_selection_id: str
    datasheet_id: str
    mfm_unit_record_id: str
    mfm_unit_id: str
    unit_number: int
    model_count: int
    base_points: int
    wargear_points: int
    total_points: int
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit_selection_id", _validate_identifier(self.unit_selection_id))
        object.__setattr__(self, "datasheet_id", _validate_identifier(self.datasheet_id))
        object.__setattr__(
            self,
            "mfm_unit_record_id",
            _validate_identifier(self.mfm_unit_record_id),
        )
        object.__setattr__(self, "mfm_unit_id", _validate_identifier(self.mfm_unit_id))
        object.__setattr__(self, "unit_number", _validate_positive_int(self.unit_number))
        object.__setattr__(self, "model_count", _validate_positive_int(self.model_count))
        object.__setattr__(self, "base_points", _validate_non_negative_int(self.base_points))
        object.__setattr__(self, "wargear_points", _validate_non_negative_int(self.wargear_points))
        object.__setattr__(self, "total_points", _validate_non_negative_int(self.total_points))
        if self.total_points != self.base_points + self.wargear_points:
            raise ArmyPointsError("MfmUnitPointLine total_points must equal base plus wargear.")
        object.__setattr__(self, "source_ids", _validate_identifier_tuple(self.source_ids))

    def roster_unit_point_value(self) -> RosterUnitPointValue:
        return RosterUnitPointValue(
            unit_selection_id=self.unit_selection_id,
            points=self.total_points,
            source_id=";".join(self.source_ids),
        )


@dataclass(frozen=True, slots=True)
class MfmEnhancementPointLine:
    enhancement_id: str
    target_unit_selection_id: str
    points: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "enhancement_id", _validate_identifier(self.enhancement_id))
        object.__setattr__(
            self,
            "target_unit_selection_id",
            _validate_identifier(self.target_unit_selection_id),
        )
        object.__setattr__(self, "points", _validate_non_negative_int(self.points))
        object.__setattr__(self, "source_id", _validate_identifier(self.source_id))

    def roster_enhancement_point_value(self) -> RosterEnhancementPointValue:
        return RosterEnhancementPointValue(
            enhancement_id=self.enhancement_id,
            target_unit_selection_id=self.target_unit_selection_id,
            points=self.points,
            source_id=self.source_id,
        )


@dataclass(frozen=True, slots=True)
class MfmArmyPointCalculation:
    unit_lines: tuple[MfmUnitPointLine, ...]
    enhancement_lines: tuple[MfmEnhancementPointLine, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit_lines", _validate_unit_line_tuple(self.unit_lines))
        object.__setattr__(
            self,
            "enhancement_lines",
            _validate_enhancement_line_tuple(self.enhancement_lines),
        )

    @property
    def total_points(self) -> int:
        return sum(line.total_points for line in self.unit_lines) + sum(
            line.points for line in self.enhancement_lines
        )

    def roster_unit_point_values(self) -> tuple[RosterUnitPointValue, ...]:
        return tuple(line.roster_unit_point_value() for line in self.unit_lines)

    def roster_enhancement_point_values(self) -> tuple[RosterEnhancementPointValue, ...]:
        return tuple(line.roster_enhancement_point_value() for line in self.enhancement_lines)


def calculate_mfm_army_points(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    source_package: MfmSourcePackage | None = None,
) -> MfmArmyPointCalculation:
    if type(catalog) is not ArmyCatalog:
        raise ArmyPointsError("MFM army points require an ArmyCatalog.")
    if type(request) is not ArmyMusterRequest:
        raise ArmyPointsError("MFM army points require an ArmyMusterRequest.")
    _validate_request_catalog_identity(catalog=catalog, request=request)
    faction = _mfm_faction_for_request(
        catalog=catalog,
        request=request,
        source_package=source_package,
    )
    priced_units = _priced_unit_records(catalog=catalog, request=request, faction=faction)
    unit_lines = tuple(
        _unit_point_line(
            catalog=catalog,
            selection=selection,
            datasheet=datasheet,
            mfm_unit=mfm_unit,
            unit_number=unit_number,
        )
        for selection, datasheet, mfm_unit, unit_number in priced_units
    )
    enhancement_lines = tuple(
        _enhancement_point_line(
            catalog=catalog,
            request=request,
            faction=faction,
            assignment=assignment,
        )
        for assignment in request.enhancement_assignments
    )
    return MfmArmyPointCalculation(unit_lines=unit_lines, enhancement_lines=enhancement_lines)


def mfm_roster_unit_point_values(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    source_package: MfmSourcePackage | None = None,
) -> tuple[RosterUnitPointValue, ...]:
    return calculate_mfm_army_points(
        catalog=catalog,
        request=request,
        source_package=source_package,
    ).roster_unit_point_values()


def catalog_with_mfm_leader_allowances(
    *,
    catalog: ArmyCatalog,
    faction_id: str,
    source_package: MfmSourcePackage | None = None,
) -> ArmyCatalog:
    if type(catalog) is not ArmyCatalog:
        raise ArmyPointsError("MFM leader overlay requires an ArmyCatalog.")
    requested_faction_id = _validate_identifier(faction_id)
    faction = _mfm_faction_by_catalog_faction_id(
        catalog=catalog,
        faction_id=requested_faction_id,
        source_package=source_package,
    )
    catalog_faction = _catalog_faction(catalog=catalog, faction_id=requested_faction_id)
    return replace(
        catalog,
        datasheets=_datasheets_with_mfm_leader_allowances(
            catalog=catalog,
            catalog_faction=catalog_faction,
            faction=faction,
        ),
    )


def catalog_with_mfm_points(
    *,
    catalog: ArmyCatalog,
    faction_id: str,
    source_package: MfmSourcePackage | None = None,
) -> ArmyCatalog:
    if type(catalog) is not ArmyCatalog:
        raise ArmyPointsError("MFM point overlay requires an ArmyCatalog.")
    requested_faction_id = _validate_identifier(faction_id)
    faction = _mfm_faction_by_catalog_faction_id(
        catalog=catalog,
        faction_id=requested_faction_id,
        source_package=source_package,
    )
    catalog_faction = _catalog_faction(catalog=catalog, faction_id=requested_faction_id)
    return replace(
        catalog,
        datasheets=_datasheets_with_mfm_leader_allowances(
            catalog=catalog,
            catalog_faction=catalog_faction,
            faction=faction,
        ),
        enhancements=_enhancements_with_mfm_points(
            catalog=catalog,
            faction=faction,
            faction_id=requested_faction_id,
        ),
    )


def _datasheets_with_mfm_leader_allowances(
    *,
    catalog: ArmyCatalog,
    catalog_faction: FactionDefinition,
    faction: MfmFactionRecord,
) -> tuple[DatasheetDefinition, ...]:
    datasheets_by_unit_id = _catalog_datasheets_by_mfm_unit_id(catalog.datasheets)
    updated_datasheets: list[DatasheetDefinition] = []
    for datasheet in catalog.datasheets:
        if not set(datasheet.keywords.faction_keywords).intersection(
            catalog_faction.faction_keywords
        ):
            updated_datasheets.append(datasheet)
            continue
        mfm_unit = _mfm_unit_for_datasheet(faction=faction, datasheet=datasheet)
        leader_allowance = mfm_unit.leader_allowance
        non_leader_eligibilities = tuple(
            eligibility
            for eligibility in datasheet.attachment_eligibilities
            if eligibility.role is not AttachmentRole.LEADER
        )
        if leader_allowance is None:
            updated_datasheets.append(
                replace(datasheet, attachment_eligibilities=non_leader_eligibilities)
            )
            continue
        updated_datasheets.append(
            replace(
                datasheet,
                attachment_eligibilities=(
                    *non_leader_eligibilities,
                    _attachment_eligibility_from_mfm(
                        leader_allowance=leader_allowance,
                        datasheets_by_unit_id=datasheets_by_unit_id,
                    ),
                ),
            )
        )
    return tuple(updated_datasheets)


def _enhancements_with_mfm_points(
    *,
    catalog: ArmyCatalog,
    faction: MfmFactionRecord,
    faction_id: str,
) -> tuple[EnhancementDefinition, ...]:
    points_by_catalog_enhancement_id = _mfm_enhancement_points_by_catalog_enhancement_id(
        catalog=catalog,
        faction=faction,
        faction_id=faction_id,
    )
    return tuple(
        replace(
            enhancement,
            points=points_by_catalog_enhancement_id[enhancement.enhancement_id],
        )
        if enhancement.enhancement_id in points_by_catalog_enhancement_id
        else enhancement
        for enhancement in catalog.enhancements
    )


def _mfm_enhancement_points_by_catalog_enhancement_id(
    *,
    catalog: ArmyCatalog,
    faction: MfmFactionRecord,
    faction_id: str,
) -> dict[str, int]:
    catalog_enhancements_by_id = {
        enhancement.enhancement_id: enhancement for enhancement in catalog.enhancements
    }
    points_by_id: dict[str, int] = {}
    for detachment in catalog.detachments:
        if detachment.faction_id != faction_id:
            continue
        mfm_detachment = _mfm_detachment_for_catalog_detachment(
            faction=faction,
            detachment=detachment,
        )
        for enhancement_id in detachment.enhancement_ids:
            catalog_enhancement = catalog_enhancements_by_id.get(enhancement_id)
            if catalog_enhancement is None:
                raise ArmyPointsError(
                    "MFM enhancement point overlay found a missing catalog enhancement."
                )
            mfm_enhancement = _mfm_enhancement_for_catalog_enhancement(
                detachment=mfm_detachment,
                enhancement=catalog_enhancement,
            )
            previous_points = points_by_id.get(catalog_enhancement.enhancement_id)
            if previous_points is not None and previous_points != mfm_enhancement.points:
                raise ArmyPointsError(
                    "MFM enhancement point overlay found conflicting enhancement prices."
                )
            points_by_id[catalog_enhancement.enhancement_id] = mfm_enhancement.points
    return points_by_id


def _priced_unit_records(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    faction: MfmFactionRecord,
) -> tuple[tuple[UnitMusterSelection, DatasheetDefinition, MfmUnitRecord, int], ...]:
    ordered: list[tuple[UnitMusterSelection, DatasheetDefinition, MfmUnitRecord]] = []
    for selection in request.unit_selections:
        datasheet = _catalog_datasheet(catalog=catalog, datasheet_id=selection.datasheet_id)
        ordered.append(
            (
                selection,
                datasheet,
                _mfm_unit_for_datasheet(faction=faction, datasheet=datasheet),
            )
        )
    unit_counts: dict[str, int] = {}
    priced: list[tuple[UnitMusterSelection, DatasheetDefinition, MfmUnitRecord, int]] = []
    for selection, datasheet, mfm_unit in ordered:
        unit_number = unit_counts.get(mfm_unit.record_id, 0) + 1
        unit_counts[mfm_unit.record_id] = unit_number
        priced.append((selection, datasheet, mfm_unit, unit_number))
    return tuple(priced)


def _unit_point_line(
    *,
    catalog: ArmyCatalog,
    selection: UnitMusterSelection,
    datasheet: DatasheetDefinition,
    mfm_unit: MfmUnitRecord,
    unit_number: int,
) -> MfmUnitPointLine:
    model_selections = _resolved_model_profile_selections(
        datasheet=datasheet,
        selection=selection,
    )
    wargear_selections = _resolved_wargear_selections(
        catalog=catalog,
        datasheet=datasheet,
        selection=selection,
    )
    bracket = mfm_unit.cost_bracket_for_unit_number(unit_number)
    base_row, add_on_rows = _base_and_add_on_rows(
        bracket=bracket,
        datasheet=datasheet,
        model_selections=model_selections,
    )
    wargear_points, wargear_source_ids = _wargear_points(
        catalog=catalog,
        mfm_unit=mfm_unit,
        wargear_selections=wargear_selections,
    )
    base_points = base_row.points + sum(row.points for row in add_on_rows)
    source_ids = tuple(
        sorted(
            {
                mfm_unit.source_id,
                bracket.source_id,
                base_row.source_id,
                *(row.source_id for row in add_on_rows),
                *wargear_source_ids,
            }
        )
    )
    return MfmUnitPointLine(
        unit_selection_id=selection.unit_selection_id,
        datasheet_id=datasheet.datasheet_id,
        mfm_unit_record_id=mfm_unit.record_id,
        mfm_unit_id=mfm_unit.unit_id,
        unit_number=unit_number,
        model_count=sum(model.model_count for model in model_selections),
        base_points=base_points,
        wargear_points=wargear_points,
        total_points=base_points + wargear_points,
        source_ids=source_ids,
    )


def _base_and_add_on_rows(
    *,
    bracket: MfmUnitCostBracket,
    datasheet: DatasheetDefinition,
    model_selections: tuple[ModelProfileSelection, ...],
) -> tuple[MfmUnitCostRow, tuple[MfmUnitCostRow, ...]]:
    selected_counts = _selected_source_model_counts(
        datasheet=datasheet,
        model_selections=model_selections,
    )
    add_on_rows = _selected_add_on_rows(bracket=bracket, selected_counts=selected_counts)
    add_on_model_ids = {
        row.additional_model_id for row in add_on_rows if row.additional_model_id is not None
    }
    base_counts = {
        model_id: count
        for model_id, count in selected_counts.items()
        if model_id not in add_on_model_ids
    }
    base_row = _selected_base_row(bracket=bracket, selected_counts=base_counts)
    return base_row, add_on_rows


def _selected_add_on_rows(
    *,
    bracket: MfmUnitCostBracket,
    selected_counts: dict[str, int],
) -> tuple[MfmUnitCostRow, ...]:
    rows: list[MfmUnitCostRow] = []
    for row in bracket.rows:
        if row.additional_model_id is None or row.additional_model_count is None:
            continue
        selected_count = selected_counts.get(row.additional_model_id)
        if selected_count is None:
            continue
        if selected_count != row.additional_model_count:
            raise ArmyPointsError("MFM add-on model row count does not match selection.")
        rows.append(row)
    return tuple(rows)


def _selected_base_row(
    *,
    bracket: MfmUnitCostBracket,
    selected_counts: dict[str, int],
) -> MfmUnitCostRow:
    total_models = sum(selected_counts.values())
    if total_models < 1:
        raise ArmyPointsError("MFM base points require at least one selected model.")
    matches = tuple(
        row
        for row in bracket.rows
        if row.additional_model_count is None
        and _base_row_matches(row=row, selected_counts=selected_counts, total_models=total_models)
    )
    if len(matches) != 1:
        raise ArmyPointsError("MFM unit cost bracket did not resolve to exactly one base row.")
    return matches[0]


def _base_row_matches(
    *,
    row: MfmUnitCostRow,
    selected_counts: dict[str, int],
    total_models: int,
) -> bool:
    if row.model_count != total_models:
        return False
    if row.model_component_ids:
        expected_counts = dict(
            zip(row.model_component_ids, row.model_component_counts, strict=True)
        )
        return selected_counts == expected_counts
    if row.model_id is not None:
        return len(selected_counts) == 1 and selected_counts.get(row.model_id) == row.model_count
    return True


def _wargear_points(
    *,
    catalog: ArmyCatalog,
    mfm_unit: MfmUnitRecord,
    wargear_selections: tuple[WargearSelection, ...],
) -> tuple[int, tuple[str, ...]]:
    selected_counts: dict[str, int] = {}
    for selection in wargear_selections:
        for wargear_id in selection.wargear_ids:
            wargear = _catalog_wargear(catalog=catalog, wargear_id=wargear_id)
            source_wargear_id = source_label_slug(wargear.name)
            selected_counts[source_wargear_id] = selected_counts.get(source_wargear_id, 0) + 1
    total = 0
    source_ids: list[str] = []
    for mfm_cost in mfm_unit.wargear_costs:
        selected_count = selected_counts.get(mfm_cost.wargear_id, 0)
        if selected_count == 0:
            continue
        total += selected_count * mfm_cost.points_per_item
        source_ids.append(mfm_cost.source_id)
    return total, tuple(source_ids)


def _enhancement_point_line(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    faction: MfmFactionRecord,
    assignment: EnhancementAssignment,
) -> MfmEnhancementPointLine:
    _unit_selection_by_id(request=request, unit_selection_id=assignment.target_unit_selection_id)
    enhancement = _mfm_enhancement_for_assignment(
        catalog=catalog,
        request=request,
        faction=faction,
        assignment=assignment,
    )
    return MfmEnhancementPointLine(
        enhancement_id=assignment.enhancement_id,
        target_unit_selection_id=assignment.target_unit_selection_id,
        points=enhancement.points,
        source_id=enhancement.source_id,
    )


def _mfm_enhancement_for_assignment(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    faction: MfmFactionRecord,
    assignment: EnhancementAssignment,
) -> MfmEnhancementRecord:
    enhancement = _catalog_enhancement(catalog=catalog, enhancement_id=assignment.enhancement_id)
    selected_detachments = _mfm_detachments_for_request(
        catalog=catalog,
        request=request,
        faction=faction,
    )
    selected_enhancements = tuple(
        mfm_enhancement
        for detachment in selected_detachments
        for mfm_enhancement in detachment.enhancements
    )
    requested_ids = (assignment.enhancement_id, source_label_slug(enhancement.name))
    matches = tuple(
        mfm_enhancement
        for mfm_enhancement in selected_enhancements
        if mfm_enhancement.enhancement_id in requested_ids
    )
    if len(matches) != 1:
        raise ArmyPointsError("MFM enhancement assignment did not resolve to one enhancement.")
    return matches[0]


def _mfm_detachments_for_request(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    faction: MfmFactionRecord,
) -> tuple[MfmDetachmentRecord, ...]:
    records: list[MfmDetachmentRecord] = []
    for detachment_id in request.detachment_selection.detachment_ids:
        detachment = _catalog_detachment(catalog=catalog, detachment_id=detachment_id)
        records.append(
            _mfm_detachment_for_catalog_detachment(
                faction=faction,
                detachment=detachment,
            )
        )
    return tuple(records)


def _mfm_detachment_for_catalog_detachment(
    *,
    faction: MfmFactionRecord,
    detachment: DetachmentDefinition,
) -> MfmDetachmentRecord:
    requested_ids = (detachment.detachment_id, source_label_slug(detachment.name))
    matches = tuple(
        mfm_detachment
        for mfm_detachment in faction.detachments
        if mfm_detachment.detachment_id in requested_ids
    )
    if len(matches) != 1:
        raise ArmyPointsError("MFM detachment selection did not resolve to one detachment.")
    return matches[0]


def _mfm_enhancement_for_catalog_enhancement(
    *,
    detachment: MfmDetachmentRecord,
    enhancement: EnhancementDefinition,
) -> MfmEnhancementRecord:
    requested_ids = (enhancement.enhancement_id, source_label_slug(enhancement.name))
    matches = tuple(
        mfm_enhancement
        for mfm_enhancement in detachment.enhancements
        if mfm_enhancement.enhancement_id in requested_ids
    )
    if len(matches) != 1:
        raise ArmyPointsError("MFM enhancement did not resolve to one enhancement.")
    return matches[0]


def _mfm_faction_for_request(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
    source_package: MfmSourcePackage | None,
) -> MfmFactionRecord:
    return _mfm_faction_by_catalog_faction_id(
        catalog=catalog,
        faction_id=request.detachment_selection.faction_id,
        source_package=source_package,
    )


def _mfm_faction_by_catalog_faction_id(
    *,
    catalog: ArmyCatalog,
    faction_id: str,
    source_package: MfmSourcePackage | None,
) -> MfmFactionRecord:
    catalog_faction = _catalog_faction(catalog=catalog, faction_id=faction_id)
    requested_ids = (catalog_faction.faction_id, source_label_slug(catalog_faction.name))
    if source_package is None:
        return _current_mfm_faction_by_ids(requested_ids)
    if type(source_package) is not MfmSourcePackage:
        raise ArmyPointsError("MFM lookup requires an MfmSourcePackage.")
    matches = tuple(
        faction for faction in source_package.factions if faction.faction_id in requested_ids
    )
    if len(matches) != 1:
        raise ArmyPointsError("MFM faction selection did not resolve to one faction.")
    return matches[0]


def _current_mfm_faction_by_ids(requested_ids: tuple[str, str]) -> MfmFactionRecord:
    supported_ids = frozenset(_current_mfm_supported_faction_ids())
    matches = tuple(requested_id for requested_id in requested_ids if requested_id in supported_ids)
    if len(matches) != 1:
        raise ArmyPointsError("MFM faction selection did not resolve to one generated faction.")
    return _current_mfm_faction_record(matches[0])


def _current_mfm_supported_faction_ids() -> tuple[str, ...]:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_06 import (
        supported_faction_ids,
    )

    return supported_faction_ids()


def _current_mfm_faction_record(faction_id: str) -> MfmFactionRecord:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_06 import (
        faction_record,
    )

    return faction_record(faction_id)


def _mfm_unit_for_datasheet(
    *,
    faction: MfmFactionRecord,
    datasheet: DatasheetDefinition,
) -> MfmUnitRecord:
    requested_ids = (datasheet.datasheet_id, source_label_slug(datasheet.name))
    record_matches = tuple(unit for unit in faction.units if unit.record_id in requested_ids)
    if len(record_matches) == 1:
        return record_matches[0]
    unit_matches = tuple(unit for unit in faction.units if unit.unit_id in requested_ids)
    if len(unit_matches) != 1:
        raise ArmyPointsError("MFM datasheet mapping did not resolve to one unit record.")
    return unit_matches[0]


def _attachment_eligibility_from_mfm(
    *,
    leader_allowance: MfmLeaderAllowance,
    datasheets_by_unit_id: dict[str, tuple[DatasheetDefinition, ...]],
) -> AttachmentEligibility:
    bodyguard_datasheet_ids: list[str] = []
    for unit_id in leader_allowance.allowed_bodyguard_unit_ids:
        datasheets = datasheets_by_unit_id.get(unit_id, ())
        if len(datasheets) != 1:
            raise ArmyPointsError(
                "MFM leader allowance did not resolve to one bodyguard datasheet."
            )
        bodyguard_datasheet_ids.append(datasheets[0].datasheet_id)
    return AttachmentEligibility(
        role=AttachmentRole.LEADER,
        targets=tuple(
            AttachmentTargetEligibility(
                bodyguard_datasheet_id=bodyguard_datasheet_id,
                source_ids=(leader_allowance.source_id,),
            )
            for bodyguard_datasheet_id in bodyguard_datasheet_ids
        ),
    )


def _catalog_datasheets_by_mfm_unit_id(
    datasheets: tuple[DatasheetDefinition, ...],
) -> dict[str, tuple[DatasheetDefinition, ...]]:
    grouped: dict[str, dict[str, DatasheetDefinition]] = {}
    for datasheet in datasheets:
        grouped.setdefault(source_label_slug(datasheet.name), {})[datasheet.datasheet_id] = (
            datasheet
        )
        grouped.setdefault(datasheet.datasheet_id, {})[datasheet.datasheet_id] = datasheet
    return {
        unit_id: tuple(sorted(records.values(), key=lambda datasheet: datasheet.datasheet_id))
        for unit_id, records in grouped.items()
    }


def _selected_source_model_counts(
    *,
    datasheet: DatasheetDefinition,
    model_selections: tuple[ModelProfileSelection, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for selection in model_selections:
        profile = datasheet.model_profile_by_id(selection.model_profile_id)
        source_id = _source_model_id(profile)
        counts[source_id] = counts.get(source_id, 0) + selection.model_count
    return counts


def _source_model_id(profile: ModelProfileDefinition) -> str:
    return source_label_slug(profile.name)


def _resolved_model_profile_selections(
    *,
    datasheet: DatasheetDefinition,
    selection: UnitMusterSelection,
) -> tuple[ModelProfileSelection, ...]:
    try:
        return resolve_model_profile_selections(
            datasheet=datasheet,
            selections=selection.model_profile_selections,
        )
    except ListValidationError as exc:
        raise ArmyPointsError("MFM points received invalid model profile selections.") from exc


def _resolved_wargear_selections(
    *,
    catalog: ArmyCatalog,
    datasheet: DatasheetDefinition,
    selection: UnitMusterSelection,
) -> tuple[WargearSelection, ...]:
    try:
        return resolve_wargear_selections(
            catalog=catalog,
            datasheet=datasheet,
            requested_selections=selection.wargear_selections,
            model_profile_selections=_resolved_model_profile_selections(
                datasheet=datasheet,
                selection=selection,
            ),
        )
    except ListValidationError as exc:
        raise ArmyPointsError("MFM points received invalid wargear selections.") from exc


def _validate_request_catalog_identity(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
) -> None:
    if request.catalog_id != catalog.catalog_id:
        raise ArmyPointsError("ArmyMusterRequest catalog_id does not match catalog.")
    if request.source_package_id != catalog.source_package_id:
        raise ArmyPointsError("ArmyMusterRequest source_package_id does not match catalog.")
    if request.ruleset_id != catalog.ruleset_id:
        raise ArmyPointsError("ArmyMusterRequest ruleset_id does not match catalog.")


def _catalog_datasheet(*, catalog: ArmyCatalog, datasheet_id: str) -> DatasheetDefinition:
    try:
        return catalog.datasheet_by_id(datasheet_id)
    except ArmyCatalogError as exc:
        raise ArmyPointsError("MFM points datasheet_id was not found in catalog.") from exc


def _catalog_faction(catalog: ArmyCatalog, faction_id: str) -> FactionDefinition:
    try:
        return catalog.faction_by_id(faction_id)
    except ArmyCatalogError as exc:
        raise ArmyPointsError("MFM points faction_id was not found in catalog.") from exc


def _catalog_wargear(*, catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_id = _validate_identifier(wargear_id)
    for wargear in catalog.wargear:
        if wargear.wargear_id == requested_id:
            return wargear
    raise ArmyPointsError("MFM points wargear_id was not found in catalog.")


def _catalog_detachment(*, catalog: ArmyCatalog, detachment_id: str) -> DetachmentDefinition:
    requested_id = _validate_identifier(detachment_id)
    for detachment in catalog.detachments:
        if detachment.detachment_id == requested_id:
            return detachment
    raise ArmyPointsError("MFM points detachment_id was not found in catalog.")


def _catalog_enhancement(*, catalog: ArmyCatalog, enhancement_id: str) -> EnhancementDefinition:
    requested_id = _validate_identifier(enhancement_id)
    for enhancement in catalog.enhancements:
        if enhancement.enhancement_id == requested_id:
            return enhancement
    raise ArmyPointsError("MFM points enhancement_id was not found in catalog.")


def _unit_selection_by_id(
    *,
    request: ArmyMusterRequest,
    unit_selection_id: str,
) -> UnitMusterSelection:
    requested_id = _validate_identifier(unit_selection_id)
    for selection in request.unit_selections:
        if selection.unit_selection_id == requested_id:
            return selection
    raise ArmyPointsError("MFM enhancement target unit selection was not found.")


def _validate_unit_line_tuple(values: tuple[MfmUnitPointLine, ...]) -> tuple[MfmUnitPointLine, ...]:
    if type(values) is not tuple:
        raise ArmyPointsError("MfmArmyPointCalculation unit_lines must be a tuple.")
    if not values:
        raise ArmyPointsError("MfmArmyPointCalculation unit_lines must not be empty.")
    seen: set[str] = set()
    for value in values:
        if type(value) is not MfmUnitPointLine:
            raise ArmyPointsError("MfmArmyPointCalculation unit_lines must contain unit lines.")
        if value.unit_selection_id in seen:
            raise ArmyPointsError("MfmArmyPointCalculation unit_lines must not contain duplicates.")
        seen.add(value.unit_selection_id)
    return values


def _validate_enhancement_line_tuple(
    values: tuple[MfmEnhancementPointLine, ...],
) -> tuple[MfmEnhancementPointLine, ...]:
    if type(values) is not tuple:
        raise ArmyPointsError("MfmArmyPointCalculation enhancement_lines must be a tuple.")
    seen: set[tuple[str, str]] = set()
    for value in values:
        if type(value) is not MfmEnhancementPointLine:
            raise ArmyPointsError(
                "MfmArmyPointCalculation enhancement_lines must contain enhancement lines."
            )
        key = (value.enhancement_id, value.target_unit_selection_id)
        if key in seen:
            raise ArmyPointsError(
                "MfmArmyPointCalculation enhancement_lines must not contain duplicates."
            )
        seen.add(key)
    return tuple(
        sorted(values, key=lambda value: (value.enhancement_id, value.target_unit_selection_id))
    )


def _validate_identifier_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ArmyPointsError("identifier tuple must be a tuple.")
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        identifier = _validate_identifier(value)
        if identifier in seen:
            raise ArmyPointsError("identifier tuple must not contain duplicates.")
        seen.add(identifier)
        normalized.append(identifier)
    return tuple(normalized)


_validate_identifier = FixedMessageIdentifierValidator(
    ArmyPointsError,
    string_message="identifier must be a string.",
    empty_message="identifier must not be empty.",
)


def _validate_positive_int(value: object) -> int:
    if type(value) is not int:
        raise ArmyPointsError("positive value must be an integer.")
    if value < 1:
        raise ArmyPointsError("positive value must be at least 1.")
    return value


def _validate_non_negative_int(value: object) -> int:
    if type(value) is not int:
        raise ArmyPointsError("non-negative value must be an integer.")
    if value < 0:
        raise ArmyPointsError("non-negative value must not be negative.")
    return value
