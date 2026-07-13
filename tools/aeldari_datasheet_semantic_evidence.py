from __future__ import annotations

import hashlib
from dataclasses import dataclass

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_clause_coverage_rows_for_ability,
    ability_coverage_row_for_descriptor,
)
from warhammer40k_core.rules.source_overlay import OverlaySourceArtifact
from warhammer40k_core.rules.wahapedia_datasheet_ability_bridge import (
    BridgedDatasheetAbility,
    bridge_datasheet_abilities,
)

CATALOG_ID = "aeldari-effective-datasheet-abilities-2026-06"


@dataclass(frozen=True, slots=True)
class SourceDerivedSemanticConsumerEvidence:
    semantic_id: str
    semantic_kind: str
    runtime_consumer_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "semantic_id": self.semantic_id,
            "semantic_kind": self.semantic_kind,
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
        }


@dataclass(frozen=True, slots=True)
class SourceDerivedAeldariAbilityEvidence:
    datasheet_id: str
    datasheet_name: str
    ability_id: str
    ability_name: str
    source_kind: CatalogAbilitySourceKind
    source_row_id: str
    source_ids: tuple[str, ...]
    raw_text: str
    raw_text_sha256: str
    normalized_text_sha256: str
    catalog_support: CatalogAbilitySupport
    support_stage: AbilityCoverageSupportStage
    semantic_consumers: tuple[SourceDerivedSemanticConsumerEvidence, ...]
    runtime_consumer_ids: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]

    @property
    def source_identity(self) -> tuple[str, str, str]:
        return self.datasheet_id, self.source_row_id, self.ability_id

    @property
    def semantic_inventory(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (semantic.semantic_id, semantic.semantic_kind) for semantic in self.semantic_consumers
        )

    def to_ability_payload(self) -> dict[str, object]:
        return {
            "ability_id": self.ability_id,
            "ability_name": self.ability_name,
            "source_kind": self.source_kind.value,
            "source_row_id": self.source_row_id,
            "source_ids": list(self.source_ids),
            "raw_text": self.raw_text,
            "raw_text_sha256": self.raw_text_sha256,
            "normalized_text_sha256": self.normalized_text_sha256,
            "catalog_support": self.catalog_support.value,
            "support_stage": self.support_stage.value,
            "semantic_consumers": [semantic.to_payload() for semantic in self.semantic_consumers],
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "diagnostic_reasons": list(self.diagnostic_reasons),
        }


def source_derived_aeldari_exact_ability_evidence(
    *,
    effective_artifacts: tuple[OverlaySourceArtifact, ...],
    datasheet_id_names: tuple[tuple[str, str], ...],
) -> tuple[SourceDerivedAeldariAbilityEvidence, ...]:
    if type(effective_artifacts) is not tuple or not effective_artifacts:
        raise TypeError("Aeldari semantic evidence requires effective source artifacts.")
    if type(datasheet_id_names) is not tuple or not datasheet_id_names:
        raise TypeError("Aeldari semantic evidence requires datasheet identities.")
    names_by_id: dict[str, str] = {}
    for identity in datasheet_id_names:
        if type(identity) is not tuple or len(identity) != 2:
            raise TypeError("Aeldari semantic evidence identities must be ID/name pairs.")
        datasheet_id, datasheet_name = identity
        if not datasheet_id.strip() or not datasheet_name.strip():
            raise ValueError("Aeldari semantic evidence identities require text values.")
        if datasheet_id in names_by_id:
            raise ValueError("Aeldari semantic evidence contains duplicate datasheet IDs.")
        names_by_id[datasheet_id] = datasheet_name

    bridged_rows = bridge_datasheet_abilities(
        source_artifacts=effective_artifacts,
        datasheet_ids=tuple(names_by_id),
    )
    evidence = tuple(
        _source_derived_ability_evidence(
            ability_row=ability_row,
            datasheet_name=names_by_id[ability_row.datasheet_id],
        )
        for ability_row in bridged_rows
    )
    represented_ids = {row.datasheet_id for row in evidence}
    if represented_ids != names_by_id.keys():
        raise ValueError("Aeldari semantic evidence does not exhaust the datasheet IDs.")
    identities = tuple(row.source_identity for row in evidence)
    if len(identities) != len(set(identities)):
        raise ValueError("Aeldari semantic evidence contains duplicate ability identities.")
    return evidence


def _source_derived_ability_evidence(
    *,
    ability_row: BridgedDatasheetAbility,
    datasheet_name: str,
) -> SourceDerivedAeldariAbilityEvidence:
    coverage = ability_coverage_row_for_descriptor(
        catalog_id=CATALOG_ID,
        datasheet_id=ability_row.datasheet_id,
        datasheet_name=datasheet_name,
        ability=ability_row.descriptor,
    )
    return SourceDerivedAeldariAbilityEvidence(
        datasheet_id=ability_row.datasheet_id,
        datasheet_name=datasheet_name,
        ability_id=ability_row.descriptor.ability_id,
        ability_name=ability_row.descriptor.name,
        source_kind=ability_row.descriptor.source_kind,
        source_row_id=ability_row.source_row_id,
        source_ids=ability_row.source_ids,
        raw_text=ability_row.raw_description,
        raw_text_sha256=_sha256_text(ability_row.raw_description),
        normalized_text_sha256=_sha256_text(ability_row.normalized_description),
        catalog_support=ability_row.descriptor.support,
        support_stage=coverage.support_stage,
        semantic_consumers=_semantic_consumer_evidence(
            ability_row=ability_row,
            runtime_consumer_ids=coverage.runtime_consumer_ids,
        ),
        runtime_consumer_ids=coverage.runtime_consumer_ids,
        diagnostic_reasons=coverage.diagnostic_reasons,
    )


def _semantic_consumer_evidence(
    *,
    ability_row: BridgedDatasheetAbility,
    runtime_consumer_ids: tuple[str, ...],
) -> tuple[SourceDerivedSemanticConsumerEvidence, ...]:
    clause_rows = ability_clause_coverage_rows_for_ability(ability_row.descriptor)
    if not clause_rows:
        return (
            SourceDerivedSemanticConsumerEvidence(
                semantic_id=f"descriptor:{ability_row.descriptor.ability_id}",
                semantic_kind="descriptor",
                runtime_consumer_ids=runtime_consumer_ids,
            ),
        )
    evidence: list[SourceDerivedSemanticConsumerEvidence] = []
    for clause_row in clause_rows:
        if len(clause_row.effect_kinds) != len(clause_row.effect_runtime_consumer_ids):
            raise ValueError("Exact ability clause effect evidence is incomplete.")
        evidence.extend(
            SourceDerivedSemanticConsumerEvidence(
                semantic_id=f"{clause_row.clause_id}:effect:{index}",
                semantic_kind=effect_kind,
                runtime_consumer_ids=effect_consumer_ids,
            )
            for index, (effect_kind, effect_consumer_ids) in enumerate(
                zip(
                    clause_row.effect_kinds,
                    clause_row.effect_runtime_consumer_ids,
                    strict=True,
                )
            )
        )
    return tuple(evidence)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
