from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from warhammer40k_core.engine.ability_coverage import (
    AbilityOverallSupport,
    ability_clause_coverage_rows_for_rule_ir,
    ability_support_rollup_for_rule_ir,
)
from warhammer40k_core.engine.semantic_equivalence import (
    CrossSourceSemanticAudit,
    SemanticContentKind,
    SemanticEquivalenceBasis,
    SemanticEquivalenceGroup,
    SemanticEquivalenceMember,
    SemanticExecutionStatus,
    SemanticSupportTransfer,
    semantic_member_from_rule_ir,
    semantic_member_without_source_text,
)
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
    faction_detachments_2026_27,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
    faction_subrules_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_JSON_DIR = (
    ROOT
    / "data"
    / "source_snapshots"
    / ("waha" + "pedia")
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
DEFAULT_OUTPUT_PATH = (
    ROOT / "data" / "generated" / "ability_coverage" / "cross_source_semantic_equivalence.json"
)
DEFAULT_DOCS_PATH = ROOT / "docs" / "CROSS_SOURCE_SEMANTIC_EQUIVALENCE.md"
GENERATED_BY_COMMAND = "uv run python tools/generate_ability_support_matrix.py"
_REQUIRED_SOURCE_TABLES = (
    "Source",
    "Factions",
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Detachment_abilities",
    "Enhancements",
    "Stratagems",
)
_FORBIDDEN_SOURCE_MARKERS = (
    "board action",
    "boarding action",
    "crusade",
    "forge world",
    "kill team",
    "legend",
)
_FACTION_SLUG_OVERRIDES = {
    "emperor-s-children": "emperors-children",
    "t-au-empire": "tau-empire",
}
_BRIDGE_SOURCE_ROW_RE = re.compile(
    r"bridge-source-row:(?P<table>Enhancements|Stratagems):(?P<row_id>[^:]+)$"
)


class CrossSourceSemanticGeneratorError(ValueError):
    """Raised when source inventory cannot produce fail-closed semantic evidence."""


@dataclass(frozen=True, slots=True)
class _SourceRuleText:
    source_row_ids: tuple[str, ...]
    source_text_ids: tuple[str, ...]
    raw_text: str


@dataclass(frozen=True, slots=True)
class _SourceInventory:
    artifacts: Mapping[str, WahapediaJsonArtifact]
    faction_slug_by_bridge_id: Mapping[str, str]
    faction_name_by_slug: Mapping[str, str]
    rows_by_table_and_id: Mapping[tuple[str, str], NormalizedSourceRow]
    detachment_rows_by_owner: Mapping[
        tuple[str, str],
        tuple[NormalizedSourceRow, ...],
    ]
    ability_rows_by_faction_and_name: Mapping[
        tuple[str, str],
        tuple[NormalizedSourceRow, ...],
    ]

    @classmethod
    def load(cls, source_json_dir: Path) -> _SourceInventory:
        artifacts = {
            table: _load_artifact(source_json_dir=source_json_dir, table=table)
            for table in _REQUIRED_SOURCE_TABLES
        }
        faction_name_by_slug = {
            row.faction_id: row.name for row in faction_detachments_2026_27.faction_rows()
        }
        faction_slug_by_bridge_id: dict[str, str] = {}
        for row in artifacts["Factions"].rows:
            fields = row.runtime_fields_payload()
            bridge_id = _required_field(fields, "id", table="Factions")
            link = _required_field(fields, "link", table="Factions")
            faction_slug_by_bridge_id[bridge_id] = _canonical_slug(
                link.rstrip("/").rsplit("/", maxsplit=1)[-1]
            )
        rows_by_table_and_id = {
            (table, row.source_row_id): row
            for table, artifact in artifacts.items()
            for row in artifact.rows
        }
        detachment_rows: dict[tuple[str, str], list[NormalizedSourceRow]] = {}
        for row in artifacts["Detachment_abilities"].rows:
            fields = row.runtime_fields_payload()
            faction_id = _bridge_faction_slug(
                faction_slug_by_bridge_id,
                _required_field(
                    fields,
                    "faction_id",
                    table="Detachment_abilities",
                ),
            )
            detachment_id = _slug(
                _required_field(
                    fields,
                    "detachment",
                    table="Detachment_abilities",
                )
            )
            detachment_rows.setdefault((faction_id, detachment_id), []).append(row)
        ability_rows: dict[tuple[str, str], list[NormalizedSourceRow]] = {}
        for row in artifacts["Abilities"].rows:
            fields = row.runtime_fields_payload()
            bridge_faction_id = fields.get("faction_id", "")
            if not bridge_faction_id.strip():
                continue
            faction_id = _bridge_faction_slug(
                faction_slug_by_bridge_id,
                bridge_faction_id,
            )
            ability_rows.setdefault(
                (
                    faction_id,
                    _slug(_required_field(fields, "name", table="Abilities")),
                ),
                [],
            ).append(row)
        return cls(
            artifacts=artifacts,
            faction_slug_by_bridge_id=dict(sorted(faction_slug_by_bridge_id.items())),
            faction_name_by_slug=faction_name_by_slug,
            rows_by_table_and_id=rows_by_table_and_id,
            detachment_rows_by_owner={
                key: tuple(sorted(rows, key=lambda item: item.source_row_id))
                for key, rows in sorted(detachment_rows.items())
            },
            ability_rows_by_faction_and_name={
                key: tuple(sorted(rows, key=lambda item: item.source_row_id))
                for key, rows in sorted(ability_rows.items())
            },
        )

    def source_text_for_execution(
        self,
        record: Phase17FExecutionRecord,
    ) -> _SourceRuleText | None:
        if record.coverage_kind in {
            Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
            Phase17ECoverageKind.DETACHMENT_STRATAGEM,
        }:
            return self._exact_subrule_text(record)
        if (
            record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
            and record.detachment_id is not None
        ):
            rows = self.detachment_rows_by_owner.get(
                (record.faction_id, record.detachment_id),
                (),
            )
            return _combined_source_text(rows) if rows else None
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE:
            ability_rows: list[NormalizedSourceRow] = []
            for name_part in record.rule_name.split(" / "):
                ability_rows.extend(
                    self.ability_rows_by_faction_and_name.get(
                        (record.faction_id, _slug(name_part)),
                        (),
                    )
                )
            return _combined_source_text(tuple(ability_rows)) if ability_rows else None
        return None

    def _exact_subrule_text(
        self,
        record: Phase17FExecutionRecord,
    ) -> _SourceRuleText | None:
        for source_id in record.source_ids:
            match = _BRIDGE_SOURCE_ROW_RE.search(source_id)
            if match is None:
                continue
            table = match.group("table")
            row = self.rows_by_table_and_id.get((table, match.group("row_id")))
            if row is not None:
                return _single_source_text(row)
        return None


def main() -> None:
    args = _parse_args()
    audit = cross_source_semantic_audit(source_json_dir=args.source_json_dir.resolve())
    args.output_path.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output_path.resolve().write_text(
        json.dumps(audit.to_payload(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    args.docs_path.resolve().write_text(
        semantic_equivalence_markdown(audit),
        encoding="utf-8",
    )


@cache
def cross_source_semantic_audit(
    *,
    source_json_dir: Path = DEFAULT_SOURCE_JSON_DIR,
) -> CrossSourceSemanticAudit:
    inventory = _SourceInventory.load(source_json_dir)
    members = (
        *_datasheet_ability_members(inventory),
        *_runtime_content_members(inventory),
    )
    return CrossSourceSemanticAudit(
        generated_by=GENERATED_BY_COMMAND,
        upstream_execution_checksum_sha256=(
            faction_execution_2026_27.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        ),
        source_artifact_hashes={
            table: inventory.artifacts[table].artifact_hash() for table in _REQUIRED_SOURCE_TABLES
        },
        members=members,
    )


def semantic_equivalence_markdown(audit: CrossSourceSemanticAudit) -> str:
    if type(audit) is not CrossSourceSemanticAudit:
        raise CrossSourceSemanticGeneratorError(
            "Semantic equivalence Markdown requires a typed audit."
        )
    groups = audit.equivalence_groups()
    kind_counts = Counter(member.content_kind for member in audit.members)
    structured_counts = Counter(
        member.content_kind
        for member in audit.members
        if member.equivalence_basis is SemanticEquivalenceBasis.STRUCTURED_RULE_IR
    )
    lines = [
        "# Cross-source Semantic Equivalence Audit",
        "",
        (
            f"Generated by `{audit.generated_by}`. Do not hand-edit this generated "
            "semantic evidence."
        ),
        "",
        (
            "This audit fingerprints provenance-free, fully structured RuleIR. Source IDs, "
            "display names, normalized prose, parser versions, clause IDs, source spans, and "
            "template IDs are excluded; typed triggers, conditions, targets, effects, "
            "durations, parameters, clause order, rules surface, and activation context remain."
        ),
        "",
        (
            "When RuleIR is incomplete, the audit records exact normalized-text identity only. "
            "That reveals duplicate source language but never transfers gameplay support. Named "
            "handler execution is also local evidence and is never promoted across sources. "
            "Only fully consumed datasheet RuleIR with content-neutral runtime consumers is "
            "marked transferable."
        ),
        "",
        "## Inventory",
        "",
        "| Content kind | Source members | Structured RuleIR |",
        "| --- | ---: | ---: |",
    ]
    for kind in SemanticContentKind:
        lines.append(f"| `{kind.value}` | {kind_counts[kind]} | {structured_counts[kind]} |")
    payload = audit.to_payload()
    lines.extend(
        (
            f"| **Total** | **{payload['member_count']}** | "
            f"**{payload['structured_member_count']}** |",
            "",
            (
                f"Equivalent groups: **{payload['equivalent_group_count']}**; "
                f"cross-faction groups: **{payload['cross_faction_group_count']}**; "
                f"exact-text-only members: **{payload['exact_text_only_member_count']}**; "
                "source-text-unavailable members: "
                f"**{payload['source_text_unavailable_member_count']}**."
            ),
            "",
            "## Equivalence Groups",
            "",
            (
                "| Group | Kind / surface | Basis | Members | Execution evidence | "
                "Support transfer |"
            ),
            "| --- | --- | --- | --- | --- | --- |",
        )
    )
    for group in groups:
        lines.append(_group_markdown_row(audit, group))
    lines.append("")
    return "\n".join(lines)


def faction_semantic_equivalence_markdown(
    audit: CrossSourceSemanticAudit,
    *,
    faction_id: str,
) -> list[str]:
    faction_members = tuple(member for member in audit.members if member.faction_id == faction_id)
    groups = audit.groups_for_faction(faction_id)
    structured_count = sum(
        member.equivalence_basis is SemanticEquivalenceBasis.STRUCTURED_RULE_IR
        for member in faction_members
    )
    lines = [
        "",
        "## Cross-source Semantic Equivalence",
        "",
        (
            "This section is generated from the repository-wide semantic audit. It is separate "
            "from catalog load/playability: it reports exact per-rule IR execution evidence and "
            "safe equivalence across source owners."
        ),
        "",
        "| Source members | Structured RuleIR | Equivalent groups |",
        "| ---: | ---: | ---: |",
        f"| {len(faction_members)} | {structured_count} | {len(groups)} |",
        "",
    ]
    if not groups:
        lines.append("No cross-source semantic-equivalence groups were found for this faction.")
        return lines
    lines.extend(
        (
            ("| Group | Kind / surface | Basis | Equivalent source rules | Execution conclusion |"),
            "| --- | --- | --- | --- | --- |",
        )
    )
    for group in groups:
        members = audit.members_for_group(group)
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{group.equivalence_hash[:12]}`",
                    f"`{group.content_kind.value}` / `{group.rules_surface}`",
                    f"`{group.equivalence_basis.value}`",
                    "<br>".join(_member_label(member) for member in members),
                    _group_conclusion(group),
                )
            )
            + " |"
        )
    return lines


def _datasheet_ability_members(
    inventory: _SourceInventory,
) -> tuple[SemanticEquivalenceMember, ...]:
    source_rows = {
        row.source_row_id: row
        for row in inventory.artifacts["Source"].rows
        if not _source_is_forbidden(row)
    }
    current_faction_ids = set(inventory.faction_name_by_slug)
    datasheets_by_id: dict[str, tuple[NormalizedSourceRow, str, str]] = {}
    for row in inventory.artifacts["Datasheets"].rows:
        fields = row.runtime_fields_payload()
        if _required_field(fields, "virtual", table="Datasheets") != "false":
            continue
        source_id = fields.get("source_id", "")
        if not source_id.strip():
            continue
        source_row = source_rows.get(source_id)
        if source_row is None:
            continue
        faction_id = _datasheet_faction_id(
            datasheet_fields=fields,
            source_fields=source_row.runtime_fields_payload(),
            bridge_faction_slugs=inventory.faction_slug_by_bridge_id,
            current_faction_ids=current_faction_ids,
        )
        if faction_id not in current_faction_ids:
            continue
        datasheet_id = _required_field(fields, "id", table="Datasheets")
        datasheets_by_id[datasheet_id] = (
            row,
            faction_id,
            inventory.faction_name_by_slug[faction_id],
        )

    members: list[SemanticEquivalenceMember] = []
    for row in inventory.artifacts["Datasheets_abilities"].rows:
        fields = row.runtime_fields_payload()
        datasheet_id = _required_field(
            fields,
            "datasheet_id",
            table="Datasheets_abilities",
        )
        datasheet_record = datasheets_by_id.get(datasheet_id)
        if datasheet_record is None:
            continue
        rules_surface = _required_field(
            fields,
            "type",
            table="Datasheets_abilities",
        )
        if rules_surface not in {"Datasheet", "Wargear"}:
            continue
        description = fields.get("description", "")
        if not description.strip():
            raise CrossSourceSemanticGeneratorError(
                "In-scope datasheet and wargear abilities require description text."
            )
        datasheet_row, faction_id, faction_name = datasheet_record
        datasheet_fields = datasheet_row.runtime_fields_payload()
        source_text = _single_source_text(row)
        rule_ir, normalized_text = _compile_source_text(
            member_id=f"datasheet-ability:{row.source_row_id}",
            source_text=source_text,
        )
        clause_rows = ability_clause_coverage_rows_for_rule_ir(
            source_ability_id=row.stable_source_id(),
            ability_name=_required_field(
                fields,
                "name",
                table="Datasheets_abilities",
            ),
            rule_ir=rule_ir,
        )
        runtime_consumer_ids = tuple(
            sorted(
                {
                    consumer_id
                    for clause_row in clause_rows
                    for consumer_id in clause_row.runtime_consumer_ids
                }
            )
        )
        rollup = ability_support_rollup_for_rule_ir(
            source_ability_id=row.stable_source_id(),
            ability_name=_required_field(
                fields,
                "name",
                table="Datasheets_abilities",
            ),
            rule_ir=rule_ir,
        )
        if rollup.overall_ability_support is AbilityOverallSupport.FULL and runtime_consumer_ids:
            status = SemanticExecutionStatus.ENGINE_CONSUMED
            transfer = SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR
        elif rule_ir.is_supported:
            status = SemanticExecutionStatus.GENERIC_IR_EXECUTABLE
            transfer = SemanticSupportTransfer.NONE
        else:
            status = SemanticExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS
            transfer = SemanticSupportTransfer.NONE
        members.append(
            semantic_member_from_rule_ir(
                member_id=f"datasheet-ability:{row.source_row_id}",
                content_kind=SemanticContentKind.DATASHEET_ABILITY,
                rules_surface=rules_surface.casefold(),
                faction_id=faction_id,
                faction_name=faction_name,
                owner_id=datasheet_id,
                owner_name=_required_field(
                    datasheet_fields,
                    "name",
                    table="Datasheets",
                ),
                rule_id=fields.get("ability_id", "").strip() or row.source_row_id,
                rule_name=_required_field(
                    fields,
                    "name",
                    table="Datasheets_abilities",
                ),
                source_row_ids=source_text.source_row_ids,
                source_text_ids=source_text.source_text_ids,
                semantic_context={"ability_source_kind": rules_surface.casefold()},
                normalized_text=normalized_text,
                rule_ir=rule_ir,
                execution_status=status,
                runtime_consumer_ids=runtime_consumer_ids,
                support_transfer=transfer,
            )
        )
    return tuple(members)


def _runtime_content_members(
    inventory: _SourceInventory,
) -> tuple[SemanticEquivalenceMember, ...]:
    members: list[SemanticEquivalenceMember] = []
    for record in faction_execution_2026_27.execution_records():
        content_kind = _content_kind_for_execution(record)
        if content_kind is None:
            continue
        semantic_context = _execution_semantic_context(record)
        if record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR:
            rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
                record.coverage_descriptor_id
            )
            source_text = _SourceRuleText(
                source_row_ids=record.source_ids,
                source_text_ids=(rule_ir.source_id,),
                raw_text=rule_ir.normalized_text,
            )
            members.append(
                _member_for_execution_rule_ir(
                    record=record,
                    content_kind=content_kind,
                    semantic_context=semantic_context,
                    source_text=source_text,
                    rule_ir=rule_ir,
                    normalized_text=rule_ir.normalized_text,
                )
            )
            continue
        execution_source_text = inventory.source_text_for_execution(record)
        if execution_source_text is None:
            members.append(
                semantic_member_without_source_text(
                    member_id=f"runtime-content:{record.execution_id}",
                    content_kind=content_kind,
                    rules_surface=content_kind.value,
                    faction_id=record.faction_id,
                    faction_name=record.faction_name,
                    owner_id=record.detachment_id or record.faction_id,
                    owner_name=record.detachment_name or record.faction_name,
                    rule_id=record.rule_id or record.coverage_descriptor_id,
                    rule_name=record.rule_name,
                    source_row_ids=record.source_ids,
                    semantic_context=semantic_context,
                    execution_status=_execution_status(record),
                    runtime_consumer_ids=record.runtime_consumer_ids,
                )
            )
            continue
        rule_ir, normalized_text = _compile_source_text(
            member_id=f"runtime-content:{record.execution_id}",
            source_text=execution_source_text,
        )
        members.append(
            _member_for_execution_rule_ir(
                record=record,
                content_kind=content_kind,
                semantic_context=semantic_context,
                source_text=execution_source_text,
                rule_ir=rule_ir,
                normalized_text=normalized_text,
            )
        )
    return tuple(members)


def _member_for_execution_rule_ir(
    *,
    record: Phase17FExecutionRecord,
    content_kind: SemanticContentKind,
    semantic_context: Mapping[str, object],
    source_text: _SourceRuleText,
    rule_ir: RuleIR,
    normalized_text: str,
) -> SemanticEquivalenceMember:
    return semantic_member_from_rule_ir(
        member_id=f"runtime-content:{record.execution_id}",
        content_kind=content_kind,
        rules_surface=content_kind.value,
        faction_id=record.faction_id,
        faction_name=record.faction_name,
        owner_id=record.detachment_id or record.faction_id,
        owner_name=record.detachment_name or record.faction_name,
        rule_id=record.rule_id or record.coverage_descriptor_id,
        rule_name=record.rule_name,
        source_row_ids=source_text.source_row_ids,
        source_text_ids=source_text.source_text_ids,
        semantic_context=semantic_context,
        normalized_text=normalized_text,
        rule_ir=rule_ir,
        execution_status=_execution_status(record),
        runtime_consumer_ids=record.runtime_consumer_ids,
    )


def _content_kind_for_execution(
    record: Phase17FExecutionRecord,
) -> SemanticContentKind | None:
    return {
        Phase17ECoverageKind.FACTION_ARMY_RULE: SemanticContentKind.FACTION_RULE,
        Phase17ECoverageKind.DETACHMENT_RULE: SemanticContentKind.DETACHMENT_RULE,
        Phase17ECoverageKind.DETACHMENT_ENHANCEMENT: SemanticContentKind.ENHANCEMENT,
        Phase17ECoverageKind.DETACHMENT_STRATAGEM: SemanticContentKind.STRATAGEM,
    }.get(record.coverage_kind)


def _execution_status(record: Phase17FExecutionRecord) -> SemanticExecutionStatus:
    return {
        Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR: (
            SemanticExecutionStatus.GENERIC_IR_EXECUTABLE
        ),
        Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER: (
            SemanticExecutionStatus.NAMED_HANDLER_EXECUTABLE
        ),
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED: (
            SemanticExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS
        ),
        Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP: (
            SemanticExecutionStatus.SOURCE_ONLY
        ),
    }[record.execution_status]


def _execution_semantic_context(
    record: Phase17FExecutionRecord,
) -> Mapping[str, object]:
    context: dict[str, object] = {}
    if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT:
        enhancement_matches = tuple(
            row
            for row in faction_subrules_2026_27.enhancement_rows()
            if row.faction_id == record.faction_id
            and row.detachment_id == record.detachment_id
            and row.name == record.rule_name
        )
        if len(enhancement_matches) != 1:
            raise CrossSourceSemanticGeneratorError(
                "Enhancement semantic context requires one exact source row."
            )
        context["points"] = enhancement_matches[0].points
    elif record.coverage_kind is Phase17ECoverageKind.DETACHMENT_STRATAGEM:
        stratagem_matches = tuple(
            row
            for row in faction_subrules_2026_27.stratagem_rows()
            if row.faction_id == record.faction_id
            and row.detachment_id == record.detachment_id
            and row.name == record.rule_name
        )
        if len(stratagem_matches) != 1:
            raise CrossSourceSemanticGeneratorError(
                "Stratagem semantic context requires one exact source row."
            )
        context["command_point_cost"] = stratagem_matches[0].command_point_cost
        context["timing"] = stratagem_matches[0].timing_descriptor
        context["category"] = stratagem_matches[0].category
    return context


def _compile_source_text(
    *,
    member_id: str,
    source_text: _SourceRuleText,
) -> tuple[RuleIR, str]:
    source = RuleSourceText.from_raw(
        source_id=f"cross-source-semantic-audit:{member_id}",
        raw_text=source_text.raw_text,
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    return rule_ir, source.normalized_text


def _single_source_text(row: NormalizedSourceRow) -> _SourceRuleText:
    description = tuple(field for field in row.text_fields if field.column_name == "description")
    if len(description) != 1:
        raise CrossSourceSemanticGeneratorError(
            f"{row.source_table} row {row.source_row_id} requires one description text field."
        )
    field = description[0]
    return _SourceRuleText(
        source_row_ids=(row.stable_source_id(),),
        source_text_ids=(field.source_text_id,),
        raw_text=field.sanitized_text,
    )


def _combined_source_text(
    rows: tuple[NormalizedSourceRow, ...],
) -> _SourceRuleText:
    if not rows:
        raise CrossSourceSemanticGeneratorError(
            "Combined semantic source text requires source rows."
        )
    source_texts = tuple(_single_source_text(row) for row in rows)
    raw_parts: list[str] = []
    for row, source_text in zip(rows, source_texts, strict=True):
        fields = row.runtime_fields_payload()
        raw_parts.append(
            f"{_required_field(fields, 'name', table=row.source_table)}: {source_text.raw_text}"
        )
    return _SourceRuleText(
        source_row_ids=tuple(
            source_row_id
            for source_text in source_texts
            for source_row_id in source_text.source_row_ids
        ),
        source_text_ids=tuple(
            source_text_id
            for source_text in source_texts
            for source_text_id in source_text.source_text_ids
        ),
        raw_text="\n".join(raw_parts),
    )


def _source_is_forbidden(row: NormalizedSourceRow) -> bool:
    fields = row.runtime_fields_payload()
    searchable = " ".join(
        (
            _required_field(fields, "name", table="Source"),
            _required_field(fields, "type", table="Source"),
        )
    ).casefold()
    return any(marker in searchable for marker in _FORBIDDEN_SOURCE_MARKERS)


def _datasheet_faction_id(
    *,
    datasheet_fields: Mapping[str, str],
    source_fields: Mapping[str, str],
    bridge_faction_slugs: Mapping[str, str],
    current_faction_ids: set[str],
) -> str:
    source_slug = _canonical_slug(_required_field(source_fields, "name", table="Source"))
    if source_slug in current_faction_ids:
        return source_slug
    bridge_faction_id = _required_field(
        datasheet_fields,
        "faction_id",
        table="Datasheets",
    )
    return _bridge_faction_slug(bridge_faction_slugs, bridge_faction_id)


def _bridge_faction_slug(
    faction_slug_by_bridge_id: Mapping[str, str],
    bridge_id: str,
) -> str:
    faction_slug = faction_slug_by_bridge_id.get(bridge_id)
    if faction_slug is None:
        raise CrossSourceSemanticGeneratorError(
            f"Source row references unknown faction ID {bridge_id!r}."
        )
    return faction_slug


def _load_artifact(*, source_json_dir: Path, table: str) -> WahapediaJsonArtifact:
    path = source_json_dir / f"{table}.json"
    if not path.is_file():
        raise CrossSourceSemanticGeneratorError(
            f"Semantic audit source artifact is missing: {path}."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CrossSourceSemanticGeneratorError(
            f"Semantic audit source artifact {table} is invalid JSON."
        ) from exc
    if not isinstance(value, dict):
        raise CrossSourceSemanticGeneratorError(
            f"Semantic audit source artifact {table} must be an object."
        )
    artifact = WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, value))
    if artifact.source_table != table:
        raise CrossSourceSemanticGeneratorError(
            f"Semantic audit source artifact {table} has mismatched table identity."
        )
    return artifact


def _group_markdown_row(
    audit: CrossSourceSemanticAudit,
    group: SemanticEquivalenceGroup,
) -> str:
    members = audit.members_for_group(group)
    return (
        "| "
        + " | ".join(
            (
                f"`{group.equivalence_hash[:12]}`",
                f"`{group.content_kind.value}` / `{group.rules_surface}`",
                f"`{group.equivalence_basis.value}`",
                "<br>".join(_member_label(member) for member in members),
                ", ".join(f"`{status.value}`" for status in group.execution_statuses),
                f"`{group.support_transfer.value}`",
            )
        )
        + " |"
    )


def _member_label(member: SemanticEquivalenceMember) -> str:
    return (
        f"{_markdown_text(member.faction_name)} — {_markdown_text(member.owner_name)} — "
        f"{_markdown_text(member.rule_name)} (`{member.execution_status.value}`)"
    )


def _group_conclusion(group: SemanticEquivalenceGroup) -> str:
    if group.support_transfer is SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR:
        consumers = ", ".join(f"`{value}`" for value in group.runtime_consumer_ids)
        return f"Engine-consumed through content-neutral generic RuleIR: {consumers}."
    if group.equivalence_basis is SemanticEquivalenceBasis.EXACT_NORMALIZED_TEXT:
        return "Exact normalized text only; gameplay support is not transferred."
    return "Equivalent structured IR; each source retains its local execution evidence."


def _required_field(
    fields: Mapping[str, str],
    field_name: str,
    *,
    table: str,
) -> str:
    value = fields.get(field_name)
    if value is None:
        raise CrossSourceSemanticGeneratorError(
            f"Semantic audit source row in {table} lacks {field_name}."
        )
    if not value.strip():
        raise CrossSourceSemanticGeneratorError(
            f"Semantic audit source row in {table} has empty {field_name}."
        )
    return value


def _canonical_slug(value: str) -> str:
    slug = _slug(value)
    return _FACTION_SLUG_OVERRIDES.get(slug, slug)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise CrossSourceSemanticGeneratorError(
            "Semantic audit source label cannot normalize to an empty slug."
        )
    return slug


def _markdown_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate cross-source semantic-equivalence evidence."
    )
    parser.add_argument(
        "--source-json-dir",
        type=Path,
        default=DEFAULT_SOURCE_JSON_DIR,
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )
    parser.add_argument(
        "--docs-path",
        type=Path,
        default=DEFAULT_DOCS_PATH,
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
