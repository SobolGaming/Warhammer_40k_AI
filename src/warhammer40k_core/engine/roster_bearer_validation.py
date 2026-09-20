"""Roster model eligibility and Warlord keyword authority."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
)
from warhammer40k_core.core.detachment import EnhancementDefinition, EnhancementSubtype
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.engine.army_mustering import (
    AELDARI_FACTION_ID,
    ANHRATHE_KEYWORD,
    CHARACTER_KEYWORD,
    CORSAIR_COTERIE_DETACHMENT_ID,
    CORSAIR_COTERIE_ENHANCEMENT_IDS,
    DAEMONIC_PACT_SOURCE_ID,
    DREADBLADES_SOURCE_ID,
    DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID,
    FREEBLADES_SOURCE_ID,
    INFANTRY_KEYWORD,
    ArmyMusteringError,
    ArmyMusterRequest,
    EnhancementAssignment,
    RosterLegalityReport,
    RosterLegalityViolation,
    WarlordSelection,
    datasheet_has_keyword,
    is_daemonic_pact_datasheet,
    roster_attached_groups,
)
from warhammer40k_core.engine.list_validation import (
    dreadblades_datasheet_allowed_for_faction,
    drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction,
    freeblades_datasheet_allowed_for_faction,
)
from warhammer40k_core.engine.roster_model_identity import selected_roster_model
from warhammer40k_core.engine.unit_factory import (
    ModelInstance,
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_roster_models_2026_09 as roster_source,
)


@dataclass(slots=True)
class RosterModelResolver:
    """Reconstruct each selected source unit once within one validation call."""

    catalog: ArmyCatalog
    request: ArmyMusterRequest
    _units: dict[str, UnitInstance] = field(default_factory=dict[str, UnitInstance], init=False)

    def selected_model(
        self,
        *,
        datasheet: DatasheetDefinition,
        unit_selection_id: str,
        model_profile_id: str,
        model_index: int,
    ) -> ModelInstance:
        if unit_selection_id not in self._units:
            selection = next(
                row
                for row in self.request.unit_selections
                if row.unit_selection_id == unit_selection_id
            )
            self._units[unit_selection_id] = UnitFactory(catalog=self.catalog).instantiate_unit(
                army_id=self.request.army_id, selection=selection, datasheet=datasheet
            )
        return selected_roster_model(
            self._units[unit_selection_id],
            model_profile_id=model_profile_id,
            model_index=model_index,
        )


def append_warlord_violations(
    *,
    model_resolver: RosterModelResolver,
    request: ArmyMusterRequest,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    if request.warlord_selection is None:
        violations.append(
            RosterLegalityViolation(
                violation_code="missing_warlord_selection",
                message="Roster requires one selected Warlord.",
                source_id=roster_source.WARLORD_SOURCE_ID,
            )
        )
        return
    datasheet = datasheets_by_selection_id.get(request.warlord_selection.unit_selection_id)
    if datasheet is None:
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_unknown_unit",
                message="WarlordSelection references an unknown unit selection.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=request.warlord_selection.source_id,
            )
        )
        return
    selected = request.warlord_selection
    model = _selected_model(
        model_resolver=model_resolver,
        datasheet=datasheet,
        unit_selection_id=selected.unit_selection_id,
        model_profile_id=selected.model_profile_id,
        model_index=selected.model_index,
        kind="warlord",
        source_id=selected.source_id,
    )
    if isinstance(model, RosterLegalityViolation):
        violations.append(model)
    if isinstance(model, ModelInstance) and "CHARACTER" not in model.keywords:
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_character_required",
                message="WarlordSelection requires a CHARACTER model.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=request.warlord_selection.source_id,
            )
        )
    forbidden_source_id = _datasheet_warlord_forbidden_source_id(datasheet)
    if forbidden_source_id is not None:
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_forbidden",
                message="WarlordSelection target has a rule that says it cannot be Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=forbidden_source_id,
            )
        )
    if is_daemonic_pact_datasheet(datasheet, faction.faction_keywords):
        violations.append(
            RosterLegalityViolation(
                violation_code="daemonic_pact_warlord_forbidden",
                message="Daemonic Pact Legiones Daemonica units cannot be selected as Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=DAEMONIC_PACT_SOURCE_ID,
            )
        )
    elif drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    ):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_drukhari_corsairs_and_travelling_players_forbidden",
                message=(
                    "Corsairs and Travelling Players HARLEQUINS or ANHRATHE units cannot "
                    "be selected as Warlord."
                ),
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=DRUKHARI_CORSAIRS_AND_TRAVELLING_PLAYERS_SOURCE_ID,
            )
        )
    elif freeblades_datasheet_allowed_for_faction(datasheet=datasheet, faction=faction):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_freeblades_forbidden",
                message="Freeblades Imperial Knights models cannot be selected as Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=FREEBLADES_SOURCE_ID,
            )
        )
    elif dreadblades_datasheet_allowed_for_faction(datasheet=datasheet, faction=faction):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_dreadblades_forbidden",
                message="Dreadblades Chaos Knights models cannot be selected as Warlord.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=DREADBLADES_SOURCE_ID,
            )
        )
    elif not set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords):
        violations.append(
            RosterLegalityViolation(
                violation_code="warlord_faction_keyword_required",
                message="WarlordSelection must share the army faction keyword.",
                unit_selection_id=request.warlord_selection.unit_selection_id,
                source_id=request.warlord_selection.source_id,
            )
        )
    _append_supreme_commander_warlord_violations(
        warlord_selection=request.warlord_selection,
        faction=faction,
        datasheets_by_selection_id=datasheets_by_selection_id,
        violations=violations,
    )


def _append_supreme_commander_warlord_violations(
    *,
    warlord_selection: WarlordSelection,
    faction: FactionDefinition,
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    violations: list[RosterLegalityViolation],
) -> None:
    required_source_by_selection_id = {
        selection_id: source_id
        for selection_id, datasheet in datasheets_by_selection_id.items()
        if (source_id := _datasheet_requires_warlord_source_id(datasheet)) is not None
        and not _datasheet_warlord_is_forbidden(datasheet=datasheet, faction=faction)
    }
    if not required_source_by_selection_id:
        return
    eligible_required_selection_ids = tuple(
        sorted(
            selection_id
            for selection_id in required_source_by_selection_id
            if _datasheet_can_be_selected_warlord(
                datasheet=datasheets_by_selection_id[selection_id],
                faction=faction,
            )
        )
    )
    if not eligible_required_selection_ids:
        first_required_selection_id = sorted(required_source_by_selection_id)[0]
        violations.append(
            RosterLegalityViolation(
                violation_code="supreme_commander_warlord_conflict",
                message=(
                    "Supreme Commander requires a Warlord from that set, but every such "
                    "unit is blocked from being Warlord."
                ),
                unit_selection_id=first_required_selection_id,
                source_id=required_source_by_selection_id[first_required_selection_id],
            )
        )
        return
    if warlord_selection.unit_selection_id in set(eligible_required_selection_ids):
        return
    first_eligible_selection_id = eligible_required_selection_ids[0]
    violations.append(
        RosterLegalityViolation(
            violation_code="supreme_commander_warlord_required",
            message=(
                "When one or more eligible Supreme Commander units are in the army, "
                "one of them must be selected as Warlord."
            ),
            unit_selection_id=warlord_selection.unit_selection_id,
            source_id=required_source_by_selection_id[first_eligible_selection_id],
        )
    )


def _datasheet_can_be_selected_warlord(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if not datasheet_has_keyword(datasheet, "CHARACTER"):
        return False
    if _datasheet_warlord_is_forbidden(datasheet=datasheet, faction=faction):
        return False
    return bool(set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords))


def _datasheet_warlord_is_forbidden(
    *, datasheet: DatasheetDefinition, faction: FactionDefinition
) -> bool:
    return (
        _datasheet_warlord_forbidden_source_id(datasheet) is not None
        or is_daemonic_pact_datasheet(datasheet, faction.faction_keywords)
        or drukhari_corsairs_and_travelling_players_datasheet_allowed_for_faction(
            datasheet=datasheet, faction=faction
        )
        or freeblades_datasheet_allowed_for_faction(datasheet=datasheet, faction=faction)
        or dreadblades_datasheet_allowed_for_faction(datasheet=datasheet, faction=faction)
    )


def _datasheet_requires_warlord_source_id(datasheet: DatasheetDefinition) -> str | None:
    for ability in datasheet.abilities:
        value = _ability_mustering_warlord_value(ability)
        if value == MUSTERING_WARLORD_REQUIRED:
            return ability.source_id
    return None


def _datasheet_warlord_forbidden_source_id(datasheet: DatasheetDefinition) -> str | None:
    for ability in datasheet.abilities:
        if _ability_mustering_warlord_value(ability) == MUSTERING_WARLORD_FORBIDDEN:
            return ability.source_id
    return None


def _ability_mustering_warlord_value(ability: DatasheetAbilityDescriptor) -> str | None:
    payload = ability.rule_ir_payload
    if payload is None or MUSTERING_WARLORD_RULE_KEY not in payload:
        return None
    value = payload[MUSTERING_WARLORD_RULE_KEY]
    if type(value) is not str:
        raise ArmyMusteringError("mustering_warlord descriptor value must be a string.")
    if value not in {MUSTERING_WARLORD_REQUIRED, MUSTERING_WARLORD_FORBIDDEN}:
        raise ArmyMusteringError("mustering_warlord descriptor value is unsupported.")
    return value


def append_enhancement_violations(
    *,
    catalog: ArmyCatalog,
    model_resolver: RosterModelResolver,
    request: ArmyMusterRequest,
    selected_detachment_enhancement_ids: tuple[str, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    enhancement_limit: int,
    violations: list[RosterLegalityViolation],
) -> None:
    effective_enhancement_limit = _effective_enhancement_limit(
        request=request,
        enhancement_limit=enhancement_limit,
    )
    if len(request.detachment_selection.enhancement_ids) > effective_enhancement_limit:
        violations.append(
            RosterLegalityViolation(
                violation_code="enhancement_limit_exceeded",
                message="Roster exceeds the battle-size Enhancement limit.",
                source_id="phase16d:enhancement-limit",
            )
        )
    selected_ids = set(request.detachment_selection.enhancement_ids)
    detachment_allowed_ids = set(selected_detachment_enhancement_ids)
    catalog_enhancement_by_id = {
        enhancement.enhancement_id: enhancement for enhancement in catalog.enhancements
    }
    attached_group_by_selection_id = roster_attached_groups(request)
    enhancement_count_by_attached_group: dict[tuple[str, ...], int] = {}
    assignment_count_by_enhancement_id: dict[str, int] = {}
    for assignment in request.enhancement_assignments:
        assignment_count_by_enhancement_id[assignment.enhancement_id] = (
            assignment_count_by_enhancement_id.get(assignment.enhancement_id, 0) + 1
        )
        if assignment.enhancement_id not in selected_ids:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_not_selected",
                    message="EnhancementAssignment must use a selected Enhancement.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        if assignment.enhancement_id not in detachment_allowed_ids:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_not_allowed_by_detachment",
                    message="EnhancementAssignment is not granted by the selected detachment.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        enhancement = catalog_enhancement_by_id.get(assignment.enhancement_id)
        if enhancement is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_unknown",
                    message="EnhancementAssignment references an unknown Enhancement.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        elif enhancement.points is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="source_awaiting_enhancement_points",
                    message="EnhancementAssignment requires source-backed Enhancement points.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=enhancement.source_id,
                )
            )
        datasheet = datasheets_by_selection_id.get(assignment.target_unit_selection_id)
        if datasheet is None:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_unknown_target",
                    message="EnhancementAssignment target unit selection is unknown.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
            continue
        is_corsair_coterie_enhancement = (
            enhancement is not None
            and _request_uses_corsair_coterie(request)
            and _is_corsair_coterie_enhancement_id(enhancement.enhancement_id)
        )
        is_upgrade = enhancement is not None and _enhancement_is_upgrade(enhancement)
        model = _selected_model(
            model_resolver=model_resolver,
            datasheet=datasheet,
            unit_selection_id=assignment.target_unit_selection_id,
            model_profile_id=assignment.model_profile_id,
            model_index=assignment.model_index,
            kind="enhancement",
            source_id=assignment.source_id,
        )
        if isinstance(model, RosterLegalityViolation):
            violations.append(model)
        if is_corsair_coterie_enhancement:
            if enhancement is None:
                raise ArmyMusteringError("Corsair Coterie Enhancement is missing.")
            if isinstance(model, ModelInstance):
                _append_corsair_coterie_enhancement_target_violations(
                    enhancement=enhancement,
                    model=model,
                    assignment=assignment,
                    violations=violations,
                )
        elif (
            not is_upgrade
            and isinstance(model, ModelInstance)
            and "CHARACTER" not in model.keywords
        ):
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_character_required",
                    message="Enhancements require a CHARACTER bearer model.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=assignment.source_id,
                )
            )
        if isinstance(model, ModelInstance) and "EPIC HERO" in model.keywords:
            violations.append(
                RosterLegalityViolation(
                    violation_code="epic_hero_enhancement_forbidden",
                    message="EPIC HERO models cannot be given Enhancements.",
                    unit_selection_id=assignment.target_unit_selection_id,
                    source_id=(
                        "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:"
                        "25.04-epic-hero-enhancements"
                    ),
                )
            )
        if enhancement is not None and isinstance(model, ModelInstance):
            _append_enhancement_target_requirement_violations(
                enhancement=enhancement,
                model=model,
                assignment=assignment,
                violations=violations,
            )
        attached_group = attached_group_by_selection_id.get(assignment.target_unit_selection_id)
        if attached_group is not None:
            enhancement_count_by_attached_group[attached_group] = (
                enhancement_count_by_attached_group.get(attached_group, 0) + 1
            )
    for enhancement_id, assignment_count in assignment_count_by_enhancement_id.items():
        enhancement = catalog_enhancement_by_id.get(enhancement_id)
        if enhancement is None:
            continue
        if _request_uses_corsair_coterie(request) and _is_corsair_coterie_enhancement_id(
            enhancement_id
        ):
            if assignment_count > 1:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="enhancement_repeated_assignment_forbidden",
                        message="A Corsair Enhancement can be assigned to only one unit.",
                        source_id=enhancement.source_id,
                    )
                )
            continue
        if _enhancement_is_upgrade(enhancement):
            if assignment_count > 3:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="upgrade_assignment_limit_exceeded",
                        message="A selected Upgrade can be assigned to at most three units.",
                        source_id=enhancement.source_id,
                    )
                )
            continue
        if assignment_count > 1:
            violations.append(
                RosterLegalityViolation(
                    violation_code="enhancement_repeated_assignment_forbidden",
                    message="A standard Enhancement can be assigned to only one unit.",
                    source_id=enhancement.source_id,
                )
            )
    for attached_group, count in enhancement_count_by_attached_group.items():
        if count > 1:
            violations.append(
                RosterLegalityViolation(
                    violation_code="attached_squad_enhancement_limit_exceeded",
                    message="An attached squad can have at most one Enhancement or Upgrade.",
                    unit_selection_id=attached_group[0],
                    source_id="phase16d:attached-squad-enhancement-limit",
                )
            )


def _effective_enhancement_limit(
    *,
    request: ArmyMusterRequest,
    enhancement_limit: int,
) -> int:
    if not _request_uses_corsair_coterie(request):
        return enhancement_limit
    return max(enhancement_limit, len(CORSAIR_COTERIE_ENHANCEMENT_IDS))


def _append_corsair_coterie_enhancement_target_violations(
    *,
    enhancement: EnhancementDefinition,
    model: ModelInstance,
    assignment: EnhancementAssignment,
    violations: list[RosterLegalityViolation],
) -> None:
    if ANHRATHE_KEYWORD not in model.keywords:
        violations.append(
            RosterLegalityViolation(
                violation_code="corsair_coterie_anhrathe_required",
                message="Corsair Enhancements require an ANHRATHE bearer model.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )
    if enhancement.enhancement_id == "archraider" and CHARACTER_KEYWORD not in model.keywords:
        violations.append(
            RosterLegalityViolation(
                violation_code="corsair_coterie_archraider_character_required",
                message="Archraider requires an ANHRATHE CHARACTER bearer model.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )
    if enhancement.enhancement_id == "voidstone" and INFANTRY_KEYWORD not in model.keywords:
        violations.append(
            RosterLegalityViolation(
                violation_code="corsair_coterie_voidstone_infantry_required",
                message="Voidstone requires an ANHRATHE INFANTRY bearer model.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )


def _append_enhancement_target_requirement_violations(
    *,
    enhancement: EnhancementDefinition,
    model: ModelInstance,
    assignment: EnhancementAssignment,
    violations: list[RosterLegalityViolation],
) -> None:
    for keyword in enhancement.target_required_keywords:
        if keyword in model.keywords:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="enhancement_target_keyword_required",
                message="EnhancementAssignment target unit is missing a required keyword.",
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )
    for keyword in enhancement.target_required_faction_keywords:
        if keyword in model.faction_keywords:
            continue
        violations.append(
            RosterLegalityViolation(
                violation_code="enhancement_target_faction_keyword_required",
                message=(
                    "EnhancementAssignment target unit is missing a required faction keyword."
                ),
                unit_selection_id=assignment.target_unit_selection_id,
                source_id=enhancement.source_id,
            )
        )


def apply_warlord_keyword_if_selected(
    *,
    request: ArmyMusterRequest,
    units: tuple[UnitInstance, ...],
    roster_legality_report: RosterLegalityReport,
) -> tuple[UnitInstance, ...]:
    if request.warlord_selection is None:
        return units
    if any(
        _warlord_violation_blocks_keyword(violation)
        for violation in roster_legality_report.violations
    ):
        return units
    target_unit_id = f"{request.army_id}:{request.warlord_selection.unit_selection_id}"
    target_unit = next(unit for unit in units if unit.unit_instance_id == target_unit_id)
    target_model = selected_roster_model(
        target_unit,
        model_profile_id=request.warlord_selection.model_profile_id,
        model_index=request.warlord_selection.model_index,
    )
    return tuple(
        replace(
            unit,
            own_models=tuple(
                replace(
                    model,
                    keyword_assignment=replace(
                        model.keyword_assignment,
                        keywords=tuple(sorted({*model.keywords, "WARLORD"})),
                        source_ids=tuple(
                            sorted(
                                {
                                    *model.keyword_assignment.source_ids,
                                    request.warlord_selection.source_id,
                                }
                            )
                        ),
                    ),
                )
                if model.model_instance_id == target_model.model_instance_id
                else model
                for model in unit.own_models
            ),
        )
        if unit.unit_instance_id == target_unit_id
        else unit
        for unit in units
    )


def _warlord_violation_blocks_keyword(violation: RosterLegalityViolation) -> bool:
    if type(violation) is not RosterLegalityViolation:
        raise ArmyMusteringError("Warlord violation lookup requires a RosterLegalityViolation.")
    return (
        violation.violation_code == "missing_warlord_selection"
        or violation.violation_code.startswith("warlord_")
        or violation.violation_code.endswith("_warlord_forbidden")
        or violation.violation_code.startswith("supreme_commander_warlord")
    )


def _selected_model(
    *,
    model_resolver: RosterModelResolver,
    datasheet: DatasheetDefinition,
    unit_selection_id: str,
    model_profile_id: str,
    model_index: int,
    kind: str,
    source_id: str,
) -> ModelInstance | RosterLegalityViolation:
    try:
        return model_resolver.selected_model(
            datasheet=datasheet,
            unit_selection_id=unit_selection_id,
            model_profile_id=model_profile_id,
            model_index=model_index,
        )
    except UnitFactoryError as exc:
        return RosterLegalityViolation(
            violation_code=f"{kind}_invalid_model_selection",
            message=str(exc),
            unit_selection_id=unit_selection_id,
            source_id=source_id,
        )


def _enhancement_is_upgrade(enhancement: EnhancementDefinition) -> bool:
    return EnhancementSubtype.UPGRADE in enhancement.subtypes


def _request_uses_corsair_coterie(request: ArmyMusterRequest) -> bool:
    return (
        request.detachment_selection.faction_id == AELDARI_FACTION_ID
        and CORSAIR_COTERIE_DETACHMENT_ID in request.detachment_selection.detachment_ids
    )


def _is_corsair_coterie_enhancement_id(enhancement_id: str) -> bool:
    return enhancement_id in CORSAIR_COTERIE_ENHANCEMENT_IDS
