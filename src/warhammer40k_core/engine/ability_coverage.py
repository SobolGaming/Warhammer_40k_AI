from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    parameter_payload,
)


class AbilityCoverageSupportStage(StrEnum):
    DESCRIPTOR_ONLY = "descriptor_only"
    IR_COMPILED_UNSUPPORTED = "ir_compiled_unsupported"
    GENERIC_IR_EXECUTABLE = "generic_ir_executable"
    ENGINE_CONSUMED = "engine_consumed"


class AbilityCoverageRowPayload(TypedDict):
    catalog_id: str
    datasheet_id: str
    datasheet_name: str
    ability_id: str
    ability_name: str
    source_kind: str
    source_wargear_id: str | None
    catalog_support: str
    support_stage: str
    semantic_categories: list[str]
    runtime_consumer_ids: list[str]
    diagnostic_reasons: list[str]


@dataclass(frozen=True, slots=True)
class AbilityCoverageRow:
    catalog_id: str
    datasheet_id: str
    datasheet_name: str
    ability_id: str
    ability_name: str
    source_kind: CatalogAbilitySourceKind
    source_wargear_id: str | None
    catalog_support: CatalogAbilitySupport
    support_stage: AbilityCoverageSupportStage
    semantic_categories: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.catalog_id) is not str or not self.catalog_id.strip():
            raise GameLifecycleError("AbilityCoverageRow catalog_id must be a string.")
        if type(self.datasheet_id) is not str or not self.datasheet_id.strip():
            raise GameLifecycleError("AbilityCoverageRow datasheet_id must be a string.")
        if type(self.datasheet_name) is not str or not self.datasheet_name.strip():
            raise GameLifecycleError("AbilityCoverageRow datasheet_name must be a string.")
        if type(self.ability_id) is not str or not self.ability_id.strip():
            raise GameLifecycleError("AbilityCoverageRow ability_id must be a string.")
        if type(self.ability_name) is not str or not self.ability_name.strip():
            raise GameLifecycleError("AbilityCoverageRow ability_name must be a string.")
        if type(self.source_kind) is not CatalogAbilitySourceKind:
            raise GameLifecycleError(
                "AbilityCoverageRow source_kind must be CatalogAbilitySourceKind."
            )
        if self.source_wargear_id is not None and (
            type(self.source_wargear_id) is not str or not self.source_wargear_id.strip()
        ):
            raise GameLifecycleError("AbilityCoverageRow source_wargear_id must be a string.")
        if type(self.catalog_support) is not CatalogAbilitySupport:
            raise GameLifecycleError(
                "AbilityCoverageRow catalog_support must be CatalogAbilitySupport."
            )
        if type(self.support_stage) is not AbilityCoverageSupportStage:
            raise GameLifecycleError(
                "AbilityCoverageRow support_stage must be AbilityCoverageSupportStage."
            )
        object.__setattr__(
            self,
            "semantic_categories",
            _validate_string_tuple("semantic_categories", self.semantic_categories),
        )
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validate_string_tuple("runtime_consumer_ids", self.runtime_consumer_ids),
        )
        object.__setattr__(
            self,
            "diagnostic_reasons",
            _validate_string_tuple("diagnostic_reasons", self.diagnostic_reasons),
        )

    def to_payload(self) -> AbilityCoverageRowPayload:
        return {
            "catalog_id": self.catalog_id,
            "datasheet_id": self.datasheet_id,
            "datasheet_name": self.datasheet_name,
            "ability_id": self.ability_id,
            "ability_name": self.ability_name,
            "source_kind": self.source_kind.value,
            "source_wargear_id": self.source_wargear_id,
            "catalog_support": self.catalog_support.value,
            "support_stage": self.support_stage.value,
            "semantic_categories": list(self.semantic_categories),
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "diagnostic_reasons": list(self.diagnostic_reasons),
        }


def ability_coverage_rows_from_catalog(
    catalog: ArmyCatalog,
    *,
    datasheet_ids: tuple[str, ...] = (),
) -> tuple[AbilityCoverageRow, ...]:
    if type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Ability coverage requires an ArmyCatalog.")
    if type(datasheet_ids) is not tuple:
        raise GameLifecycleError("Ability coverage datasheet_ids must be a tuple.")
    selected_ids = frozenset(_validate_string_tuple("datasheet_ids", datasheet_ids))
    rows: list[AbilityCoverageRow] = []
    for datasheet in catalog.datasheets:
        if selected_ids and datasheet.datasheet_id not in selected_ids:
            continue
        rows.extend(_ability_coverage_rows_for_datasheet(catalog=catalog, datasheet=datasheet))
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.datasheet_id,
                row.source_kind.value,
                row.source_wargear_id or "",
                row.ability_name,
                row.ability_id,
            ),
        )
    )


def ability_coverage_rows_payload(
    rows: tuple[AbilityCoverageRow, ...],
) -> list[AbilityCoverageRowPayload]:
    if type(rows) is not tuple:
        raise GameLifecycleError("Ability coverage rows must be a tuple.")
    return [row.to_payload() for row in rows]


def _ability_coverage_rows_for_datasheet(
    *,
    catalog: ArmyCatalog,
    datasheet: DatasheetDefinition,
) -> tuple[AbilityCoverageRow, ...]:
    if type(datasheet) is not DatasheetDefinition:
        raise GameLifecycleError("Ability coverage requires DatasheetDefinition values.")
    rows: list[AbilityCoverageRow] = []
    for ability in datasheet.abilities:
        rule_ir = _rule_ir_for_ability(ability)
        consumer_ids = () if rule_ir is None else catalog_rule_ir_consumers_for_rule(rule_ir)
        rows.append(
            AbilityCoverageRow(
                catalog_id=catalog.catalog_id,
                datasheet_id=datasheet.datasheet_id,
                datasheet_name=datasheet.name,
                ability_id=ability.ability_id,
                ability_name=ability.name,
                source_kind=ability.source_kind,
                source_wargear_id=ability.source_wargear_id,
                catalog_support=ability.support,
                support_stage=_support_stage(
                    ability=ability,
                    rule_ir=rule_ir,
                    consumer_ids=consumer_ids,
                ),
                semantic_categories=_semantic_categories(ability=ability, rule_ir=rule_ir),
                runtime_consumer_ids=consumer_ids,
                diagnostic_reasons=_diagnostic_reasons(ability),
            )
        )
    return tuple(rows)


def _rule_ir_for_ability(ability: DatasheetAbilityDescriptor) -> RuleIR | None:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability coverage requires DatasheetAbilityDescriptor values.")
    if ability.rule_ir_payload is None:
        return None
    return RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))


def _support_stage(
    *,
    ability: DatasheetAbilityDescriptor,
    rule_ir: RuleIR | None,
    consumer_ids: tuple[str, ...],
) -> AbilityCoverageSupportStage:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability support stage requires a descriptor.")
    if type(consumer_ids) is not tuple:
        raise GameLifecycleError("Ability support stage consumer_ids must be a tuple.")
    if consumer_ids:
        return AbilityCoverageSupportStage.ENGINE_CONSUMED
    if ability.support is CatalogAbilitySupport.GENERIC_RULE_IR:
        return AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    if rule_ir is not None or ability.rule_ir_diagnostics:
        return AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    return AbilityCoverageSupportStage.DESCRIPTOR_ONLY


def _semantic_categories(
    *,
    ability: DatasheetAbilityDescriptor,
    rule_ir: RuleIR | None,
) -> tuple[str, ...]:
    if rule_ir is None:
        return (f"{ability.source_kind.value}.descriptor",)
    categories: set[str] = set()
    for clause in rule_ir.clauses:
        target = "unscoped"
        if clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT:
            target = "this_unit"
        for effect in clause.effects:
            parameters = parameter_payload(effect.parameters)
            if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
                roll_type = _string_parameter(parameters, key="roll_type")
                categories.add(f"{ability.source_kind.value}.roll_modifier.{roll_type}.{target}")
            elif effect.kind is RuleEffectKind.SET_CHARACTERISTIC:
                characteristic = _string_parameter(parameters, key="characteristic")
                categories.add(
                    f"{ability.source_kind.value}.characteristic_set.{characteristic}.{target}"
                )
            else:
                categories.add(f"{ability.source_kind.value}.rule_ir.{effect.kind.value}.{target}")
        if clause.unsupported_reason is not None:
            categories.add(
                f"{ability.source_kind.value}.unsupported.{clause.unsupported_reason.value}"
            )
    if not categories:
        categories.add(f"{ability.source_kind.value}.rule_ir.no_effects")
    return tuple(sorted(categories))


def _string_parameter(parameters: Mapping[str, object], *, key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Ability coverage rule parameter {key} must be a string.")
    return value


def _diagnostic_reasons(ability: DatasheetAbilityDescriptor) -> tuple[str, ...]:
    reasons: set[str] = set()
    for diagnostic in ability.rule_ir_diagnostics:
        reason = diagnostic.get("reason")
        if reason is None:
            continue
        if type(reason) is not str:
            raise GameLifecycleError("Ability coverage diagnostic reason must be a string.")
        reasons.add(reason)
    return tuple(sorted(reasons))


def _validate_string_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("String tuple validation requires a field name.")
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    for value in values:
        if type(value) is not str or not value.strip():
            raise GameLifecycleError(f"{field_name} entries must be non-empty strings.")
    return values
