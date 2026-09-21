"""Core-owned evaluation of source-linked detachment construction constraints."""

from __future__ import annotations

from warhammer40k_core.core.attributes import CharacteristicValueKind
from warhammer40k_core.core.construction_constraints import (
    AllUnitSelector,
    AnyUnitSelector,
    CharacteristicComparison,
    CharacteristicUnitSelector,
    ConstructionConstraint,
    ConstructionConstraintError,
    ConstructionConstraintKind,
    DatasheetUnitSelector,
    ExcludeUnitSelector,
    KeywordUnitSelector,
    ModelQuantifier,
    UnitSelector,
)
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    ArmyMusterRequest,
    RosterLegalityReport,
    RosterLegalityViolation,
)
from warhammer40k_core.engine.roster_bearer_validation import RosterModelResolver
from warhammer40k_core.engine.unit_factory import UnitFactoryError, UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_roster_construction_2026_09 as construction_source,
)


def unit_matches(
    selector: UnitSelector,
    *,
    unit: UnitInstance,
    effective_keywords: frozenset[str],
) -> bool:
    if isinstance(selector, DatasheetUnitSelector):
        return unit.datasheet_id in selector.datasheet_ids
    if isinstance(selector, KeywordUnitSelector):
        return (
            set(selector.all_of).issubset(effective_keywords)
            and (not selector.any_of or bool(set(selector.any_of).intersection(effective_keywords)))
            and not set(selector.none_of).intersection(effective_keywords)
        )
    if isinstance(selector, CharacteristicUnitSelector):
        values = tuple(model.characteristic(selector.characteristic) for model in unit.own_models)
        if not values or any(
            value.value_kind is not CharacteristicValueKind.NUMERIC for value in values
        ):
            raise ConstructionConstraintError(
                "Construction threshold requires numeric roster characteristics."
            )
        matches = tuple(
            value.final >= selector.value
            if selector.comparison is CharacteristicComparison.AT_LEAST
            else value.final <= selector.value
            if selector.comparison is CharacteristicComparison.AT_MOST
            else value.final == selector.value
            for value in values
        )
        return all(matches) if selector.models is ModelQuantifier.ALL else any(matches)
    if isinstance(selector, (AllUnitSelector, AnyUnitSelector)):
        # Evaluate every child: an unsupported atom cannot hide behind short-circuiting.
        matches = tuple(
            unit_matches(row, unit=unit, effective_keywords=effective_keywords)
            for row in selector.selectors
        )
        return all(matches) if isinstance(selector, AllUnitSelector) else any(matches)
    if type(selector) is ExcludeUnitSelector:
        included = unit_matches(selector.selector, unit=unit, effective_keywords=effective_keywords)
        excluded = unit_matches(selector.excluded, unit=unit, effective_keywords=effective_keywords)
        return included and not excluded
    raise ConstructionConstraintError("Unsupported construction unit selector.")


def _constraint_matches(
    *,
    constraint: ConstructionConstraint,
    owner_id: str,
    request: ArmyMusterRequest,
    detachments: tuple[DetachmentDefinition, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    model_resolver: RosterModelResolver,
) -> list[str]:
    matches: list[str] = []
    if constraint.unit_selector is not None:
        for selection in request.unit_selections:
            if selection.unit_selection_id not in datasheets_by_selection_id:
                raise ConstructionConstraintError(
                    "Construction input contains an invalid unit selection."
                )
            unit = model_resolver.unit(
                datasheet=datasheets_by_selection_id[selection.unit_selection_id],
                unit_selection_id=selection.unit_selection_id,
            )
            if unit_matches(
                constraint.unit_selector,
                unit=unit,
                effective_keywords=frozenset((*unit.keywords, *unit.faction_keywords)),
            ):
                matches.append(selection.unit_selection_id)
    elif constraint.detachment_selector is not None:
        selector = constraint.detachment_selector
        matches = [
            row.detachment_id
            for row in detachments
            if row.detachment_id != owner_id
            and row.canonical_detachment_id in selector.detachment_ids
            and row.canonical_detachment_id not in selector.excluded_detachment_ids
        ]
    else:
        raise ConstructionConstraintError("Construction constraint has no selector.")
    return sorted(matches)


def append_construction_violations(
    *,
    request: ArmyMusterRequest,
    detachments: tuple[DetachmentDefinition, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
    model_resolver: RosterModelResolver,
    violations: list[RosterLegalityViolation],
) -> None:
    for owner in detachments:
        for constraint in owner.construction_constraints:
            try:
                matches = _constraint_matches(
                    constraint=constraint,
                    owner_id=owner.detachment_id,
                    request=request,
                    detachments=detachments,
                    datasheets_by_selection_id=datasheets_by_selection_id,
                    model_resolver=model_resolver,
                )
            except (ConstructionConstraintError, UnitFactoryError) as exc:
                violations.append(
                    RosterLegalityViolation(
                        violation_code="construction_constraint_invalid",
                        source_id=constraint.source_id,
                        message=f"{owner.detachment_id}/{constraint.constraint_id}: {exc}",
                    )
                )
                continue
            required = constraint.kind in {
                ConstructionConstraintKind.REQUIRED_UNIT,
                ConstructionConstraintKind.REQUIRED_OTHER_DETACHMENT,
            }
            if bool(matches) == required:
                continue
            violations.append(
                RosterLegalityViolation(
                    violation_code=constraint.kind.value,
                    source_id=constraint.source_id,
                    message=f"{owner.detachment_id}/{constraint.constraint_id}: "
                    f"construction constraint failed; matches={','.join(sorted(matches))}.",
                    unit_selection_id=(
                        matches[0] if matches and constraint.unit_selector is not None else None
                    ),
                )
            )


def assert_construction_legal(report: RosterLegalityReport) -> None:
    codes = {kind.value for kind in ConstructionConstraintKind} | {
        "construction_constraint_invalid"
    }
    if any(row.violation_code in codes for row in report.violations):
        raise ArmyMusteringError(
            "ArmyMusterRequest construction constraints are invalid "
            f"({construction_source.CONSTRAINTS_SOURCE_ID})."
        )
