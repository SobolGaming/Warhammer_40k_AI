from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
)
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    catalog_descriptor_consumption_for,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_clause_wide_consumer_ids,
    catalog_rule_ir_consumer_ids_for_effect,
    catalog_rule_ir_consumers_for_clause,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_rule_selected_target_classification import (
    contextual_consumers_for_clause,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_abilities import (
    descriptor_is_deadly_demise,
    descriptor_is_deep_strike,
    descriptor_is_feel_no_pain,
    descriptor_is_stealth,
)
from warhammer40k_core.rules.parsed_tokens import TextSpan, TextSpanPayload
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
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


class AbilityOverallSupport(StrEnum):
    FULL = "Full"
    PARTIAL = "Partial"
    PARSED = "Parsed"
    UNSUPPORTED = "Unsupported"


class AbilityCoverageRowPayload(TypedDict):
    coverage_row_id: str
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


class AbilityClauseCoverageRowPayload(TypedDict):
    source_ability_id: str
    ability_name: str
    clause_id: str
    source_span: TextSpanPayload
    trigger_kind: str | None
    effect_kinds: list[str]
    effect_runtime_consumer_ids: list[list[str]]
    runtime_consumer_ids: list[str]
    support_stage: str
    diagnostics: list[str]


class AbilitySupportRollupPayload(TypedDict):
    source_ability_id: str
    ability_name: str
    total_clause_count: int
    consumed_clause_count: int
    unsupported_clause_count: int
    overall_ability_support: str


class AbilityCoverageAbilityDatasheetPairPayload(TypedDict):
    coverage_row_id: str
    ability_id: str
    ability_name: str
    datasheet_id: str
    datasheet_name: str
    source_kind: str


class AbilityCoverageCategoryRowPayload(TypedDict):
    category_id: str
    category_name: str
    coverage_row_count: int
    coverage_row_ids: list[str]
    ability_datasheet_pairs: list[AbilityCoverageAbilityDatasheetPairPayload]
    source_kind_counts: dict[str, int]
    support_stages: list[str]
    runtime_consumer_ids: list[str]
    ability_names: list[str]
    datasheet_names: list[str]


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

    @property
    def coverage_row_id(self) -> str:
        source_wargear_id = self.source_wargear_id or "none"
        return (
            f"{self.catalog_id}/{self.datasheet_id}/{self.source_kind.value}/"
            f"{self.ability_id}/{source_wargear_id}"
        )

    def to_payload(self) -> AbilityCoverageRowPayload:
        return {
            "coverage_row_id": self.coverage_row_id,
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


@dataclass(frozen=True, slots=True)
class AbilityClauseCoverageRow:
    source_ability_id: str
    ability_name: str
    clause_id: str
    source_span: TextSpan
    trigger_kind: str | None
    effect_kinds: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]
    support_stage: AbilityCoverageSupportStage
    effect_runtime_consumer_ids: tuple[tuple[str, ...], ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_ability_id",
            _validate_string("source_ability_id", self.source_ability_id),
        )
        object.__setattr__(
            self,
            "ability_name",
            _validate_string("ability_name", self.ability_name),
        )
        object.__setattr__(self, "clause_id", _validate_string("clause_id", self.clause_id))
        if type(self.source_span) is not TextSpan:
            raise GameLifecycleError("AbilityClauseCoverageRow source_span must be TextSpan.")
        if self.trigger_kind is not None:
            object.__setattr__(
                self,
                "trigger_kind",
                _validate_string("trigger_kind", self.trigger_kind),
            )
        object.__setattr__(
            self,
            "effect_kinds",
            _validate_string_tuple("effect_kinds", self.effect_kinds),
        )
        runtime_consumers = _validate_string_tuple(
            "runtime_consumer_ids", self.runtime_consumer_ids
        )
        object.__setattr__(self, "runtime_consumer_ids", runtime_consumers)
        if type(self.effect_runtime_consumer_ids) is not tuple:
            raise GameLifecycleError(
                "AbilityClauseCoverageRow effect_runtime_consumer_ids must be a tuple."
            )
        effect_consumers = tuple(
            _validate_string_tuple("effect_runtime_consumer_ids", consumer_ids)
            for consumer_ids in self.effect_runtime_consumer_ids
        )
        if len(effect_consumers) != len(self.effect_kinds):
            raise GameLifecycleError(
                "AbilityClauseCoverageRow effect consumer evidence must match effect_kinds."
            )
        if not {
            consumer_id for consumer_ids in effect_consumers for consumer_id in consumer_ids
        }.issubset(runtime_consumers):
            raise GameLifecycleError(
                "AbilityClauseCoverageRow effect consumers must be clause consumers."
            )
        object.__setattr__(self, "effect_runtime_consumer_ids", effect_consumers)
        if type(self.support_stage) is not AbilityCoverageSupportStage:
            raise GameLifecycleError(
                "AbilityClauseCoverageRow support_stage must be AbilityCoverageSupportStage."
            )
        if self.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED and (
            not effect_consumers or any(not consumer_ids for consumer_ids in effect_consumers)
        ):
            raise GameLifecycleError(
                "Engine-consumed ability clauses require consumers for every effect."
            )
        object.__setattr__(
            self,
            "diagnostics",
            _validate_string_tuple("diagnostics", self.diagnostics),
        )

    def to_payload(self) -> AbilityClauseCoverageRowPayload:
        return {
            "source_ability_id": self.source_ability_id,
            "ability_name": self.ability_name,
            "clause_id": self.clause_id,
            "source_span": self.source_span.to_payload(),
            "trigger_kind": self.trigger_kind,
            "effect_kinds": list(self.effect_kinds),
            "effect_runtime_consumer_ids": [
                list(consumer_ids) for consumer_ids in self.effect_runtime_consumer_ids
            ],
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "support_stage": self.support_stage.value,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True, slots=True)
class AbilitySupportRollup:
    source_ability_id: str
    ability_name: str
    total_clause_count: int
    consumed_clause_count: int
    unsupported_clause_count: int
    overall_ability_support: AbilityOverallSupport

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_ability_id",
            _validate_string("source_ability_id", self.source_ability_id),
        )
        object.__setattr__(
            self,
            "ability_name",
            _validate_string("ability_name", self.ability_name),
        )
        if type(self.total_clause_count) is not int or self.total_clause_count < 0:
            raise GameLifecycleError(
                "AbilitySupportRollup total_clause_count must be non-negative."
            )
        if type(self.consumed_clause_count) is not int or self.consumed_clause_count < 0:
            raise GameLifecycleError(
                "AbilitySupportRollup consumed_clause_count must be non-negative."
            )
        if type(self.unsupported_clause_count) is not int or self.unsupported_clause_count < 0:
            raise GameLifecycleError(
                "AbilitySupportRollup unsupported_clause_count must be non-negative."
            )
        if self.consumed_clause_count > self.total_clause_count:
            raise GameLifecycleError("AbilitySupportRollup consumed count exceeds total.")
        if self.unsupported_clause_count > self.total_clause_count:
            raise GameLifecycleError("AbilitySupportRollup unsupported count exceeds total.")
        if type(self.overall_ability_support) is not AbilityOverallSupport:
            raise GameLifecycleError(
                "AbilitySupportRollup overall support must be AbilityOverallSupport."
            )

    def to_payload(self) -> AbilitySupportRollupPayload:
        return {
            "source_ability_id": self.source_ability_id,
            "ability_name": self.ability_name,
            "total_clause_count": self.total_clause_count,
            "consumed_clause_count": self.consumed_clause_count,
            "unsupported_clause_count": self.unsupported_clause_count,
            "overall_ability_support": self.overall_ability_support.value,
        }


@dataclass(frozen=True, slots=True)
class AbilityCoverageAbilityDatasheetPair:
    coverage_row_id: str
    ability_id: str
    ability_name: str
    datasheet_id: str
    datasheet_name: str
    source_kind: CatalogAbilitySourceKind

    def __post_init__(self) -> None:
        if type(self.coverage_row_id) is not str or not self.coverage_row_id.strip():
            raise GameLifecycleError(
                "AbilityCoverageAbilityDatasheetPair coverage_row_id must be a string."
            )
        if type(self.ability_id) is not str or not self.ability_id.strip():
            raise GameLifecycleError(
                "AbilityCoverageAbilityDatasheetPair ability_id must be a string."
            )
        if type(self.ability_name) is not str or not self.ability_name.strip():
            raise GameLifecycleError(
                "AbilityCoverageAbilityDatasheetPair ability_name must be a string."
            )
        if type(self.datasheet_id) is not str or not self.datasheet_id.strip():
            raise GameLifecycleError(
                "AbilityCoverageAbilityDatasheetPair datasheet_id must be a string."
            )
        if type(self.datasheet_name) is not str or not self.datasheet_name.strip():
            raise GameLifecycleError(
                "AbilityCoverageAbilityDatasheetPair datasheet_name must be a string."
            )
        if type(self.source_kind) is not CatalogAbilitySourceKind:
            raise GameLifecycleError(
                "AbilityCoverageAbilityDatasheetPair source_kind must be CatalogAbilitySourceKind."
            )

    def to_payload(self) -> AbilityCoverageAbilityDatasheetPairPayload:
        return {
            "coverage_row_id": self.coverage_row_id,
            "ability_id": self.ability_id,
            "ability_name": self.ability_name,
            "datasheet_id": self.datasheet_id,
            "datasheet_name": self.datasheet_name,
            "source_kind": self.source_kind.value,
        }


@dataclass(frozen=True, slots=True)
class AbilityCoverageCategoryRow:
    category_id: str
    category_name: str
    coverage_row_count: int
    coverage_row_ids: tuple[str, ...]
    ability_datasheet_pairs: tuple[AbilityCoverageAbilityDatasheetPair, ...]
    source_kind_counts: tuple[tuple[str, int], ...]
    support_stages: tuple[AbilityCoverageSupportStage, ...]
    runtime_consumer_ids: tuple[str, ...]
    ability_names: tuple[str, ...]
    datasheet_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.category_id) is not str or not self.category_id.strip():
            raise GameLifecycleError("AbilityCoverageCategoryRow category_id must be a string.")
        if type(self.category_name) is not str or not self.category_name.strip():
            raise GameLifecycleError("AbilityCoverageCategoryRow category_name must be a string.")
        if type(self.coverage_row_count) is not int or self.coverage_row_count < 1:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow coverage_row_count must be a positive integer."
            )
        object.__setattr__(
            self,
            "coverage_row_ids",
            _validate_string_tuple("coverage_row_ids", self.coverage_row_ids),
        )
        if len(self.coverage_row_ids) != self.coverage_row_count:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow coverage_row_ids must match coverage_row_count."
            )
        if type(self.ability_datasheet_pairs) is not tuple:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow ability_datasheet_pairs must be a tuple."
            )
        if len(self.ability_datasheet_pairs) != self.coverage_row_count:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow ability_datasheet_pairs must match coverage_row_count."
            )
        for pair in self.ability_datasheet_pairs:
            if type(pair) is not AbilityCoverageAbilityDatasheetPair:
                raise GameLifecycleError(
                    "AbilityCoverageCategoryRow ability_datasheet_pairs must contain pairs."
                )
        object.__setattr__(
            self,
            "source_kind_counts",
            _validate_source_kind_counts(
                self.source_kind_counts,
                expected_row_count=self.coverage_row_count,
            ),
        )
        if type(self.support_stages) is not tuple:
            raise GameLifecycleError("AbilityCoverageCategoryRow support_stages must be a tuple.")
        for stage in self.support_stages:
            if type(stage) is not AbilityCoverageSupportStage:
                raise GameLifecycleError(
                    "AbilityCoverageCategoryRow support_stages must contain support stages."
                )
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validate_string_tuple("runtime_consumer_ids", self.runtime_consumer_ids),
        )
        object.__setattr__(
            self,
            "ability_names",
            _validate_string_tuple("ability_names", self.ability_names),
        )
        object.__setattr__(
            self,
            "datasheet_names",
            _validate_string_tuple("datasheet_names", self.datasheet_names),
        )

    def to_payload(self) -> AbilityCoverageCategoryRowPayload:
        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
            "coverage_row_count": self.coverage_row_count,
            "coverage_row_ids": list(self.coverage_row_ids),
            "ability_datasheet_pairs": [pair.to_payload() for pair in self.ability_datasheet_pairs],
            "source_kind_counts": dict(self.source_kind_counts),
            "support_stages": [stage.value for stage in self.support_stages],
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "ability_names": list(self.ability_names),
            "datasheet_names": list(self.datasheet_names),
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


def ability_coverage_row_for_descriptor(
    *,
    catalog_id: str,
    datasheet_id: str,
    datasheet_name: str,
    ability: DatasheetAbilityDescriptor,
) -> AbilityCoverageRow:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability coverage requires a DatasheetAbilityDescriptor.")
    rule_ir = _rule_ir_for_ability(ability)
    consumer_ids = _runtime_consumer_ids(ability=ability, rule_ir=rule_ir)
    return AbilityCoverageRow(
        catalog_id=_validate_string("catalog_id", catalog_id),
        datasheet_id=_validate_string("datasheet_id", datasheet_id),
        datasheet_name=_validate_string("datasheet_name", datasheet_name),
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


def ability_coverage_rows_payload(
    rows: tuple[AbilityCoverageRow, ...],
) -> list[AbilityCoverageRowPayload]:
    if type(rows) is not tuple:
        raise GameLifecycleError("Ability coverage rows must be a tuple.")
    return [row.to_payload() for row in rows]


def ability_clause_coverage_rows_for_ability(
    ability: DatasheetAbilityDescriptor,
) -> tuple[AbilityClauseCoverageRow, ...]:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability clause coverage requires a descriptor.")
    rule_ir = _rule_ir_for_ability(ability)
    if rule_ir is None:
        return ()
    return ability_clause_coverage_rows_for_rule_ir(
        source_ability_id=ability.source_id,
        ability_name=ability.name,
        rule_ir=rule_ir,
    )


def ability_clause_coverage_rows_for_rule_ir(
    *,
    source_ability_id: str,
    ability_name: str,
    rule_ir: RuleIR,
    runtime_consumers_by_clause_id: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[AbilityClauseCoverageRow, ...]:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Ability clause coverage requires RuleIR.")
    source_id = _validate_string("source_ability_id", source_ability_id)
    name = _validate_string("ability_name", ability_name)
    consumer_override = _validated_clause_consumer_override(runtime_consumers_by_clause_id)
    rows = tuple(
        _clause_coverage_row(
            source_ability_id=source_id,
            ability_name=name,
            clause=clause,
            runtime_consumer_ids=(
                tuple(
                    sorted(
                        {
                            *catalog_rule_ir_consumers_for_clause(clause),
                            *contextual_consumers_for_clause(
                                rule_ir=rule_ir,
                                clause=clause,
                            ),
                        }
                    )
                )
                if consumer_override is None
                else consumer_override.get(clause.clause_id, ())
            ),
        )
        for clause in rule_ir.clauses
    )
    return tuple(sorted(rows, key=lambda row: row.clause_id))


def ability_support_rollup_for_ability(
    ability: DatasheetAbilityDescriptor,
) -> AbilitySupportRollup | None:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability support rollup requires a descriptor.")
    rule_ir = _rule_ir_for_ability(ability)
    if rule_ir is None:
        return None
    return ability_support_rollup_for_rule_ir(
        source_ability_id=ability.source_id,
        ability_name=ability.name,
        rule_ir=rule_ir,
    )


def ability_support_rollup_for_rule_ir(
    *,
    source_ability_id: str,
    ability_name: str,
    rule_ir: RuleIR,
    runtime_consumers_by_clause_id: Mapping[str, tuple[str, ...]] | None = None,
) -> AbilitySupportRollup:
    rows = ability_clause_coverage_rows_for_rule_ir(
        source_ability_id=source_ability_id,
        ability_name=ability_name,
        rule_ir=rule_ir,
        runtime_consumers_by_clause_id=runtime_consumers_by_clause_id,
    )
    consumed_count = sum(1 for row in rows if _clause_row_is_consumed(row))
    unsupported_count = sum(
        1
        for row in rows
        if row.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    )
    return AbilitySupportRollup(
        source_ability_id=source_ability_id,
        ability_name=ability_name,
        total_clause_count=len(rows),
        consumed_clause_count=consumed_count,
        unsupported_clause_count=unsupported_count,
        overall_ability_support=_overall_support(
            total_clause_count=len(rows),
            consumed_clause_count=consumed_count,
            unsupported_clause_count=unsupported_count,
        ),
    )


def ability_coverage_category_rows(
    rows: tuple[AbilityCoverageRow, ...],
) -> tuple[AbilityCoverageCategoryRow, ...]:
    if type(rows) is not tuple:
        raise GameLifecycleError("Ability coverage rows must be a tuple.")
    grouped: dict[str, list[AbilityCoverageRow]] = {}
    for row in rows:
        if type(row) is not AbilityCoverageRow:
            raise GameLifecycleError("Ability coverage category rows require coverage rows.")
        for semantic_category in row.semantic_categories:
            grouped.setdefault(semantic_category, []).append(row)
    return tuple(
        _category_row_for_group(category_id=category_id, category_rows=tuple(category_rows))
        for category_id, category_rows in sorted(
            grouped.items(),
            key=lambda item: (_category_name(item[0]), item[0]),
        )
    )


def ability_coverage_category_rows_payload(
    rows: tuple[AbilityCoverageCategoryRow, ...],
) -> list[AbilityCoverageCategoryRowPayload]:
    if type(rows) is not tuple:
        raise GameLifecycleError("Ability coverage category rows must be a tuple.")
    for row in rows:
        if type(row) is not AbilityCoverageCategoryRow:
            raise GameLifecycleError(
                "Ability coverage category row payloads require category rows."
            )
    return [row.to_payload() for row in rows]


def _category_row_for_group(
    *,
    category_id: str,
    category_rows: tuple[AbilityCoverageRow, ...],
) -> AbilityCoverageCategoryRow:
    if type(category_id) is not str or not category_id.strip():
        raise GameLifecycleError("Ability coverage category_id must be a string.")
    if type(category_rows) is not tuple or not category_rows:
        raise GameLifecycleError("Ability coverage category rows require rows.")
    sorted_rows = tuple(sorted(category_rows, key=_coverage_row_sort_key))
    return AbilityCoverageCategoryRow(
        category_id=category_id,
        category_name=_category_name(category_id),
        coverage_row_count=len(sorted_rows),
        coverage_row_ids=tuple(row.coverage_row_id for row in sorted_rows),
        ability_datasheet_pairs=tuple(
            AbilityCoverageAbilityDatasheetPair(
                coverage_row_id=row.coverage_row_id,
                ability_id=row.ability_id,
                ability_name=row.ability_name,
                datasheet_id=row.datasheet_id,
                datasheet_name=row.datasheet_name,
                source_kind=row.source_kind,
            )
            for row in sorted_rows
        ),
        source_kind_counts=_source_kind_counts(sorted_rows),
        support_stages=tuple(
            sorted(
                {row.support_stage for row in sorted_rows},
                key=lambda stage: _SUPPORT_STAGE_ORDER[stage],
            )
        ),
        runtime_consumer_ids=tuple(
            sorted(
                {
                    runtime_consumer_id
                    for row in sorted_rows
                    for runtime_consumer_id in row.runtime_consumer_ids
                }
            )
        ),
        ability_names=tuple(sorted({row.ability_name for row in sorted_rows})),
        datasheet_names=tuple(sorted({row.datasheet_name for row in sorted_rows})),
    )


def _ability_coverage_rows_for_datasheet(
    *,
    catalog: ArmyCatalog,
    datasheet: DatasheetDefinition,
) -> tuple[AbilityCoverageRow, ...]:
    if type(datasheet) is not DatasheetDefinition:
        raise GameLifecycleError("Ability coverage requires DatasheetDefinition values.")
    rows: list[AbilityCoverageRow] = []
    for ability in datasheet.abilities:
        rows.append(
            ability_coverage_row_for_descriptor(
                catalog_id=catalog.catalog_id,
                datasheet_id=datasheet.datasheet_id,
                datasheet_name=datasheet.name,
                ability=ability,
            )
        )
    return tuple(rows)


def _rule_ir_for_ability(ability: DatasheetAbilityDescriptor) -> RuleIR | None:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability coverage requires DatasheetAbilityDescriptor values.")
    if ability.support is CatalogAbilitySupport.DESCRIPTOR_ONLY:
        return None
    if ability.rule_ir_payload is None:
        return None
    return RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))


def _runtime_consumer_ids(
    *,
    ability: DatasheetAbilityDescriptor,
    rule_ir: RuleIR | None,
) -> tuple[str, ...]:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability runtime consumers require a descriptor.")
    if rule_ir is not None:
        return catalog_rule_ir_consumers_for_rule(rule_ir)
    return _descriptor_runtime_consumer_ids(ability)


def _descriptor_runtime_consumer_ids(
    ability: DatasheetAbilityDescriptor,
) -> tuple[str, ...]:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability descriptor consumers require a descriptor.")
    if descriptor_is_deep_strike(ability):
        return (
            "descriptor:movement:deep-strike-placement",
            "descriptor:reserve-declaration:deep-strike",
        )
    if descriptor_is_deadly_demise(ability):
        return (
            "descriptor:destruction-reaction:deadly-demise-source",
            "descriptor:destruction-reaction:deadly-demise-resolution",
        )
    if descriptor_is_feel_no_pain(ability):
        return (
            "descriptor:lost-wound:feel-no-pain-source",
            "descriptor:lost-wound:feel-no-pain-resolution",
        )
    if descriptor_is_stealth(ability):
        return (CORE_STEALTH_RUNTIME_CONSUMER_ID,)
    descriptor_consumption = catalog_descriptor_consumption_for(ability)
    if descriptor_consumption is not None:
        return descriptor_consumption.runtime_consumer_ids
    if _descriptor_is_supreme_commander(ability):
        return (SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,)
    if _descriptor_is_warlord_restriction(ability):
        return (WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,)
    return ()


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
    if ability.support is CatalogAbilitySupport.GENERIC_RULE_IR and rule_ir is not None:
        rollup = ability_support_rollup_for_rule_ir(
            source_ability_id=ability.source_id,
            ability_name=ability.name,
            rule_ir=rule_ir,
        )
        if rollup.overall_ability_support is AbilityOverallSupport.FULL and consumer_ids:
            return AbilityCoverageSupportStage.ENGINE_CONSUMED
        if rollup.overall_ability_support is AbilityOverallSupport.UNSUPPORTED:
            return AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
        return AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    if (
        ability.support is CatalogAbilitySupport.DESCRIPTOR_ONLY
        and rule_ir is None
        and consumer_ids
    ):
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
        return _descriptor_semantic_categories(ability)
    categories: set[str] = set()
    for clause in rule_ir.clauses:
        target = _semantic_target_token(clause.target.kind if clause.target is not None else None)
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
            elif (
                effect.kind is RuleEffectKind.GRANT_ABILITY
                and parameters.get("ability") == "Feel No Pain"
            ):
                categories.add(f"{ability.source_kind.value}.feel_no_pain.source.{target}")
            else:
                categories.add(f"{ability.source_kind.value}.rule_ir.{effect.kind.value}.{target}")
        if clause.unsupported_reason is not None:
            categories.add(
                f"{ability.source_kind.value}.unsupported.{clause.unsupported_reason.value}"
            )
    if not categories:
        categories.add(f"{ability.source_kind.value}.rule_ir.no_effects")
    return tuple(sorted(categories))


def _clause_coverage_row(
    *,
    source_ability_id: str,
    ability_name: str,
    clause: RuleClause,
    runtime_consumer_ids: tuple[str, ...],
) -> AbilityClauseCoverageRow:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Ability clause coverage requires RuleClause values.")
    if type(runtime_consumer_ids) is not tuple:
        raise GameLifecycleError("Ability clause coverage consumers must be a tuple.")
    effect_runtime_consumer_ids = _effect_runtime_consumer_ids(
        clause=clause, runtime_consumer_ids=runtime_consumer_ids
    )
    return AbilityClauseCoverageRow(
        source_ability_id=source_ability_id,
        ability_name=ability_name,
        clause_id=clause.clause_id,
        source_span=clause.source_span,
        trigger_kind=None if clause.trigger is None else clause.trigger.kind.value,
        effect_kinds=tuple(effect.kind.value for effect in clause.effects),
        effect_runtime_consumer_ids=effect_runtime_consumer_ids,
        runtime_consumer_ids=tuple(sorted(runtime_consumer_ids)),
        support_stage=_clause_support_stage(
            clause=clause,
            effect_runtime_consumer_ids=effect_runtime_consumer_ids,
        ),
        diagnostics=tuple(
            f"{diagnostic.reason.value}:{diagnostic.source_span.start}-"
            f"{diagnostic.source_span.end}:{diagnostic.message}"
            for diagnostic in clause.diagnostics
        ),
    )


def _effect_runtime_consumer_ids(
    *,
    clause: RuleClause,
    runtime_consumer_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Partition trigger- and condition-aware clause consumers by represented effect."""
    if not clause.effects:
        return ()
    if len(clause.effects) == 1:
        return (tuple(sorted(runtime_consumer_ids)),)
    consumers = frozenset(runtime_consumer_ids)
    clause_wide_consumers = consumers.intersection(catalog_rule_ir_clause_wide_consumer_ids(clause))
    return tuple(
        tuple(
            sorted(
                clause_wide_consumers
                | consumers.intersection(catalog_rule_ir_consumer_ids_for_effect(effect))
            )
        )
        for effect in clause.effects
    )


def _clause_support_stage(
    *,
    clause: RuleClause,
    effect_runtime_consumer_ids: tuple[tuple[str, ...], ...],
) -> AbilityCoverageSupportStage:
    if not clause.is_supported:
        return AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    if effect_runtime_consumer_ids and all(effect_runtime_consumer_ids):
        return AbilityCoverageSupportStage.ENGINE_CONSUMED
    return AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE


def _clause_row_is_consumed(row: AbilityClauseCoverageRow) -> bool:
    if row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED:
        return True
    return (
        row.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
        and not row.effect_kinds
        and not row.diagnostics
    )


def _overall_support(
    *,
    total_clause_count: int,
    consumed_clause_count: int,
    unsupported_clause_count: int,
) -> AbilityOverallSupport:
    if total_clause_count == 0:
        return AbilityOverallSupport.UNSUPPORTED
    if unsupported_clause_count == total_clause_count:
        return AbilityOverallSupport.UNSUPPORTED
    if consumed_clause_count == total_clause_count and unsupported_clause_count == 0:
        return AbilityOverallSupport.FULL
    if consumed_clause_count > 0:
        return AbilityOverallSupport.PARTIAL
    if unsupported_clause_count > 0:
        return AbilityOverallSupport.PARTIAL
    return AbilityOverallSupport.PARSED


def _semantic_target_token(target_kind: RuleTargetKind | None) -> str:
    if target_kind is None:
        return "unscoped"
    if type(target_kind) is not RuleTargetKind:
        raise GameLifecycleError("Ability coverage target kind must be RuleTargetKind.")
    if target_kind in {
        RuleTargetKind.AURA_UNITS,
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
        RuleTargetKind.WEAPON,
    }:
        return target_kind.value
    return "unscoped"


def _descriptor_semantic_categories(
    ability: DatasheetAbilityDescriptor,
) -> tuple[str, ...]:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Ability descriptor categories require a descriptor.")
    if descriptor_is_deep_strike(ability):
        return ("core.reserve.deep_strike",)
    if descriptor_is_deadly_demise(ability):
        return ("core.deadly_demise",)
    if descriptor_is_feel_no_pain(ability):
        return ("core.feel_no_pain",)
    if descriptor_is_stealth(ability):
        return ("core.stealth",)
    descriptor_consumption = catalog_descriptor_consumption_for(ability)
    if descriptor_consumption is not None:
        return descriptor_consumption.semantic_categories
    if _descriptor_is_supreme_commander(ability):
        return ("datasheet.mustering.supreme_commander",)
    return ("unknown.ability_text",)


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


def _descriptor_is_supreme_commander(ability: DatasheetAbilityDescriptor) -> bool:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Supreme Commander descriptor matching requires a descriptor.")
    payload = ability.rule_ir_payload
    return (
        ability.source_kind is CatalogAbilitySourceKind.DATASHEET
        and type(payload) is dict
        and payload.get(MUSTERING_WARLORD_RULE_KEY) == MUSTERING_WARLORD_REQUIRED
    )


def _descriptor_is_warlord_restriction(ability: DatasheetAbilityDescriptor) -> bool:
    payload = ability.rule_ir_payload
    return (
        ability.source_kind is CatalogAbilitySourceKind.DATASHEET
        and type(payload) is dict
        and payload.get(MUSTERING_WARLORD_RULE_KEY) == MUSTERING_WARLORD_FORBIDDEN
    )


def _coverage_row_sort_key(
    row: AbilityCoverageRow,
) -> tuple[str, str, str, str, str]:
    if type(row) is not AbilityCoverageRow:
        raise GameLifecycleError("Ability coverage row sort requires a coverage row.")
    return (
        row.datasheet_name,
        row.datasheet_id,
        row.source_kind.value,
        row.ability_name,
        row.ability_id,
    )


def _source_kind_counts(
    rows: tuple[AbilityCoverageRow, ...],
) -> tuple[tuple[str, int], ...]:
    if type(rows) is not tuple or not rows:
        raise GameLifecycleError("Ability coverage source kind counts require rows.")
    counts: dict[str, int] = {}
    for row in rows:
        if type(row) is not AbilityCoverageRow:
            raise GameLifecycleError("Ability coverage source kind counts require coverage rows.")
        source_kind = row.source_kind.value
        counts[source_kind] = counts.get(source_kind, 0) + 1
    return tuple(sorted(counts.items()))


def _validate_source_kind_counts(
    values: tuple[tuple[str, int], ...],
    *,
    expected_row_count: int,
) -> tuple[tuple[str, int], ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("AbilityCoverageCategoryRow source_kind_counts must be a tuple.")
    if type(expected_row_count) is not int or expected_row_count < 1:
        raise GameLifecycleError("Source kind count validation requires a positive row count.")
    seen: set[str] = set()
    total = 0
    for value in values:
        if type(value) is not tuple or len(value) != 2:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow source_kind_counts entries must be pairs."
            )
        source_kind, count = value
        if type(source_kind) is not str or not source_kind.strip():
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow source_kind_counts keys must be strings."
            )
        if source_kind in seen:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow source_kind_counts keys must be unique."
            )
        if type(count) is not int or count < 1:
            raise GameLifecycleError(
                "AbilityCoverageCategoryRow source_kind_counts values must be positive integers."
            )
        seen.add(source_kind)
        total += count
    if total != expected_row_count:
        raise GameLifecycleError(
            "AbilityCoverageCategoryRow source_kind_counts must match coverage_row_count."
        )
    return values


def _validated_clause_consumer_override(
    values: object,
) -> Mapping[str, tuple[str, ...]] | None:
    if values is None:
        return None
    if not isinstance(values, Mapping):
        raise GameLifecycleError("Ability clause consumer override must be a mapping.")
    mapping = cast(Mapping[object, object], values)
    validated: dict[str, tuple[str, ...]] = {}
    for clause_id, consumer_ids in mapping.items():
        validated[_validate_string("clause_id", clause_id)] = _validate_string_tuple(
            "runtime_consumer_ids",
            consumer_ids,
        )
    return validated


def _validate_string(field_name: str, value: object) -> str:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("String validation requires a field name.")
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _validate_string_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("String tuple validation requires a field name.")
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = cast(tuple[object, ...], values)
    for value in validated:
        if type(value) is not str or not value.strip():
            raise GameLifecycleError(f"{field_name} entries must be non-empty strings.")
    return cast(tuple[str, ...], validated)


_SUPPORT_STAGE_ORDER: Mapping[AbilityCoverageSupportStage, int] = {
    AbilityCoverageSupportStage.DESCRIPTOR_ONLY: 0,
    AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED: 1,
    AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE: 2,
    AbilityCoverageSupportStage.ENGINE_CONSUMED: 3,
}

_CATEGORY_NAMES: Mapping[str, str] = {
    "core.descriptor": "Core Ability Descriptor",
    "core.leader": "Leader",
    "core.scouts": "Scouts",
    "core.stealth": "Stealth",
    "core.reserve.deep_strike": "Deep Strike Reserve Arrival",
    "datasheet.mustering.supreme_commander": "Supreme Commander",
    "faction.army_rule.blessings_of_khorne": "World Eaters Army Rule",
    "faction.army_rule.battle_focus": "Aeldari Army Rule",
    "faction.army_rule.templar_vows": "Black Templars Army Rule",
    "faction.army_rule.dark_pacts": "Chaos Space Marines Army Rule",
    "faction.army_rule.corsairs_and_travelling_players": "Drukhari Army Rule",
    "faction.army_rule.power_from_pain": "Drukhari Army Rule",
    "faction.army_rule.thrill_seekers": "Emperor's Children Army Rule",
    "faction.army_rule.nurgles_gift": "Death Guard Army Rule",
    "faction.army_rule.shadow_of_chaos": "Chaos Daemons Army Rule",
    "unknown.ability_text": "Unknown Abilities",
    "faction.descriptor": "Faction Descriptor",
    "wargear.characteristic_set.leadership.this_unit": "Leadership Characteristic",
    "wargear.feel_no_pain.source.this_model": "Feel No Pain Source",
    "wargear.roll_modifier.charge.this_unit": "Charge Roll Modifier",
}

CORE_STEALTH_RUNTIME_CONSUMER_ID = "core:stealth"
SUPREME_COMMANDER_MUSTERING_CONSUMER_ID = "army-mustering:supreme-commander"
WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID = "army-mustering:warlord-restriction"


def _category_name(category_id: str) -> str:
    if type(category_id) is not str or not category_id.strip():
        raise GameLifecycleError("Ability coverage category_id must be a string.")
    known_name = _CATEGORY_NAMES.get(category_id)
    if known_name is not None:
        return known_name
    return " ".join(token.capitalize() for token in category_id.replace("_", ".").split("."))
