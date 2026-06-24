from __future__ import annotations

import importlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from warhammer40k_core.engine.faction_content.bundle import (
    DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentSupportStatus
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.generated_manifest import (
    generated_runtime_content_rows,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogRecord
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_JSON_DIR = (
    ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
OUTPUT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_subrules_2026_27.py"
)
BRIDGE_SOURCE_PACKAGE_ID = "gw-11e-phase17e-exact-faction-subrules-2026-27:bridge-source-row"
CURRENT_SOURCE_OWNER_IDS = frozenset(
    (row.faction_id, row.detachment_id) for row in faction_detachments_2026_27.detachment_rows()
)
CURRENT_FACTION_NAMES_BY_ID = {
    row.faction_id: row.name for row in faction_detachments_2026_27.faction_rows()
}
CURRENT_DETACHMENT_NAMES_BY_OWNER_ID = {
    (row.faction_id, row.detachment_id): row.name
    for row in faction_detachments_2026_27.detachment_rows()
}
FACTION_SLUG_OVERRIDES = {
    "emperor-s-children": "emperors-children",
    "t-au-empire": "tau-empire",
}
SOURCE_ONLY_STATUS = "source_only"
ENGINE_CONSUMED_STATUS = "engine_consumed"
SKIP_REASON_MISSING_OWNER_FIELDS = "missing_owner_fields"
SKIP_REASON_OWNER_NOT_IN_CURRENT_SOURCE_PACKAGE = "owner_not_in_current_source_package"
APPROVED_SKIPPED_BRIDGE_REASONS = frozenset(
    (
        SKIP_REASON_MISSING_OWNER_FIELDS,
        SKIP_REASON_OWNER_NOT_IN_CURRENT_SOURCE_PACKAGE,
    )
)
RUNTIME_ONLY_PROVENANCE_REASON = "runtime_handler_without_bridge_source_row"
APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS = frozenset(
    (
        "enhancement:aeldari:corsair-coterie:infamy",
        "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:assassins-eye-upgrade",
        "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:camouflaged-snipers-upgrade",
        "enhancement:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:apocalyptic-steeds-upgrade",
        "enhancement:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:soul-shattering-charge-upgrade",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:casting-back-the-veil",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:eldritch-suppression",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:nomads-of-the-hidden-way",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:from-beyond-the-veil",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:inescapable-manifestations",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:warp-riders",
    )
)


@dataclass(frozen=True, slots=True)
class GeneratedEnhancementRow:
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    enhancement_id: str
    name: str
    points: int | None
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]

    @property
    def source_row_id(self) -> str:
        return f"enhancement:{self.faction_id}:{self.detachment_id}:{self.enhancement_id}"

    @property
    def support_status(self) -> str:
        if self.runtime_consumer_ids:
            return ENGINE_CONSUMED_STATUS
        return SOURCE_ONLY_STATUS


@dataclass(frozen=True, slots=True)
class GeneratedStratagemRow:
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    stratagem_id: str
    name: str
    command_point_cost: int
    timing: str
    category: str
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]

    @property
    def source_row_id(self) -> str:
        return f"stratagem:{self.faction_id}:{self.detachment_id}:{self.stratagem_id}"

    @property
    def support_status(self) -> str:
        if self.runtime_consumer_ids:
            return ENGINE_CONSUMED_STATUS
        return SOURCE_ONLY_STATUS


@dataclass(frozen=True, slots=True)
class RuntimeEnhancementSeed:
    faction_id: str
    detachment_id: str
    enhancement_id: str
    name: str
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeStratagemSeed:
    faction_id: str
    detachment_id: str
    stratagem_id: str
    name: str
    command_point_cost: int
    timing: str
    category: str
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedSkippedBridgeRow:
    table: str
    bridge_source_row_id: str
    source_faction_id: str
    source_faction_slug: str
    source_detachment_label: str
    derived_faction_id: str
    derived_detachment_id: str
    skip_reason: str

    @property
    def source_row_id(self) -> str:
        return f"skipped-bridge:{self.table}:{self.bridge_source_row_id}"


@dataclass(frozen=True, slots=True)
class GeneratedRuntimeOnlyRow:
    table: str
    source_row_id: str
    faction_id: str
    detachment_id: str
    rule_id: str
    name: str
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]
    provenance_reason: str


def main() -> None:
    faction_rows_by_bridge_id = _faction_rows_by_bridge_id()
    bridge_enhancements, skipped_bridge_enhancements = _bridge_enhancement_rows(
        faction_rows_by_bridge_id
    )
    bridge_stratagems, skipped_bridge_stratagems = _bridge_stratagem_rows(faction_rows_by_bridge_id)
    runtime_enhancements, runtime_stratagems = _runtime_subrule_seeds()
    enhancements, runtime_only_enhancements = _overlay_runtime_enhancements(
        bridge_rows=bridge_enhancements,
        runtime_rows=runtime_enhancements,
    )
    stratagems, runtime_only_stratagems = _overlay_runtime_stratagems(
        bridge_rows=bridge_stratagems,
        runtime_rows=runtime_stratagems,
    )
    OUTPUT_PATH.write_text(
        _module_content(
            enhancements=enhancements,
            stratagems=stratagems,
            skipped_bridge_rows=_validate_approved_skipped_bridge_rows(
                (*skipped_bridge_enhancements, *skipped_bridge_stratagems)
            ),
            runtime_only_rows=_validate_approved_runtime_only_rows(
                (*runtime_only_enhancements, *runtime_only_stratagems)
            ),
        ),
        encoding="utf-8",
    )


def _bridge_enhancement_rows(
    faction_rows_by_bridge_id: dict[str, dict[str, str]],
) -> tuple[tuple[GeneratedEnhancementRow, ...], tuple[GeneratedSkippedBridgeRow, ...]]:
    rows: list[GeneratedEnhancementRow] = []
    skipped_rows: list[GeneratedSkippedBridgeRow] = []
    for row in _source_rows("Enhancements"):
        fields = row["fields"]
        bridge_faction_id = fields["faction_id"]
        detachment_name = fields["detachment"]
        if not bridge_faction_id or not detachment_name:
            skipped_rows.append(
                _skipped_bridge_row(
                    table="Enhancements",
                    source_row_id=row["source_row_id"],
                    faction_rows_by_bridge_id=faction_rows_by_bridge_id,
                    bridge_faction_id=bridge_faction_id,
                    detachment_name=detachment_name,
                    skip_reason=SKIP_REASON_MISSING_OWNER_FIELDS,
                )
            )
            continue
        faction_id = _current_faction_id_for_bridge_row(
            faction_rows_by_bridge_id=faction_rows_by_bridge_id,
            bridge_faction_id=bridge_faction_id,
        )
        detachment_id = _slug_for_label(detachment_name)
        owner_id = (faction_id, detachment_id)
        if owner_id not in CURRENT_SOURCE_OWNER_IDS:
            skipped_rows.append(
                _skipped_bridge_row(
                    table="Enhancements",
                    source_row_id=row["source_row_id"],
                    faction_rows_by_bridge_id=faction_rows_by_bridge_id,
                    bridge_faction_id=bridge_faction_id,
                    detachment_name=detachment_name,
                    skip_reason=SKIP_REASON_OWNER_NOT_IN_CURRENT_SOURCE_PACKAGE,
                )
            )
            continue
        rows.append(
            GeneratedEnhancementRow(
                faction_id=faction_id,
                faction_name=CURRENT_FACTION_NAMES_BY_ID[faction_id],
                detachment_id=detachment_id,
                detachment_name=CURRENT_DETACHMENT_NAMES_BY_OWNER_ID[owner_id],
                enhancement_id=fields["id"],
                name=fields["name"],
                points=_optional_int(fields["cost"]),
                source_ids=(
                    _bridge_source_id(table="Enhancements", source_row_id=row["source_row_id"]),
                ),
                runtime_consumer_ids=(),
            )
        )
    return (
        tuple(sorted(rows, key=lambda row: row.source_row_id)),
        tuple(sorted(skipped_rows, key=lambda row: row.source_row_id)),
    )


def _bridge_stratagem_rows(
    faction_rows_by_bridge_id: dict[str, dict[str, str]],
) -> tuple[tuple[GeneratedStratagemRow, ...], tuple[GeneratedSkippedBridgeRow, ...]]:
    rows: list[GeneratedStratagemRow] = []
    skipped_rows: list[GeneratedSkippedBridgeRow] = []
    for row in _source_rows("Stratagems"):
        fields = row["fields"]
        bridge_faction_id = fields["faction_id"]
        detachment_name = fields["detachment"]
        if not bridge_faction_id or not detachment_name:
            skipped_rows.append(
                _skipped_bridge_row(
                    table="Stratagems",
                    source_row_id=row["source_row_id"],
                    faction_rows_by_bridge_id=faction_rows_by_bridge_id,
                    bridge_faction_id=bridge_faction_id,
                    detachment_name=detachment_name,
                    skip_reason=SKIP_REASON_MISSING_OWNER_FIELDS,
                )
            )
            continue
        faction_id = _current_faction_id_for_bridge_row(
            faction_rows_by_bridge_id=faction_rows_by_bridge_id,
            bridge_faction_id=bridge_faction_id,
        )
        detachment_id = _slug_for_label(detachment_name)
        owner_id = (faction_id, detachment_id)
        if owner_id not in CURRENT_SOURCE_OWNER_IDS:
            skipped_rows.append(
                _skipped_bridge_row(
                    table="Stratagems",
                    source_row_id=row["source_row_id"],
                    faction_rows_by_bridge_id=faction_rows_by_bridge_id,
                    bridge_faction_id=bridge_faction_id,
                    detachment_name=detachment_name,
                    skip_reason=SKIP_REASON_OWNER_NOT_IN_CURRENT_SOURCE_PACKAGE,
                )
            )
            continue
        rows.append(
            GeneratedStratagemRow(
                faction_id=faction_id,
                faction_name=CURRENT_FACTION_NAMES_BY_ID[faction_id],
                detachment_id=detachment_id,
                detachment_name=CURRENT_DETACHMENT_NAMES_BY_OWNER_ID[owner_id],
                stratagem_id=fields["id"],
                name=fields["name"],
                command_point_cost=_required_int(fields["cp_cost"]),
                timing=_bridge_timing_descriptor(fields),
                category=fields["type"],
                source_ids=(
                    _bridge_source_id(table="Stratagems", source_row_id=row["source_row_id"]),
                ),
                runtime_consumer_ids=(),
            )
        )
    return (
        tuple(sorted(rows, key=lambda row: row.source_row_id)),
        tuple(sorted(skipped_rows, key=lambda row: row.source_row_id)),
    )


def _overlay_runtime_enhancements(
    *,
    bridge_rows: tuple[GeneratedEnhancementRow, ...],
    runtime_rows: tuple[RuntimeEnhancementSeed, ...],
) -> tuple[tuple[GeneratedEnhancementRow, ...], tuple[GeneratedRuntimeOnlyRow, ...]]:
    bridge_by_source_row_id = {row.source_row_id: row for row in bridge_rows}
    bridge_by_name = {_rule_name_key(row): row for row in bridge_rows}
    runtime_by_id = _merged_runtime_enhancement_rows(runtime_rows)
    output: list[GeneratedEnhancementRow] = []
    runtime_only_rows: list[GeneratedRuntimeOnlyRow] = []
    for runtime_row in runtime_by_id:
        owner_id = (runtime_row.faction_id, runtime_row.detachment_id)
        bridge_row = bridge_by_source_row_id.get(_enhancement_source_row_id(runtime_row))
        if bridge_row is not None:
            bridge_by_name.pop(_rule_name_key(bridge_row), None)
        else:
            bridge_row = bridge_by_name.pop(_rule_name_key(runtime_row), None)
        source_ids = runtime_row.source_ids
        points: int | None = None
        name = runtime_row.name
        if bridge_row is not None:
            source_ids = _sorted_unique((*bridge_row.source_ids, *runtime_row.source_ids))
            points = bridge_row.points
            name = bridge_row.name
        generated_row = GeneratedEnhancementRow(
            faction_id=runtime_row.faction_id,
            faction_name=CURRENT_FACTION_NAMES_BY_ID[runtime_row.faction_id],
            detachment_id=runtime_row.detachment_id,
            detachment_name=CURRENT_DETACHMENT_NAMES_BY_OWNER_ID[owner_id],
            enhancement_id=runtime_row.enhancement_id,
            name=name,
            points=points,
            source_ids=source_ids,
            runtime_consumer_ids=runtime_row.runtime_consumer_ids,
        )
        output.append(generated_row)
        if bridge_row is None:
            runtime_only_rows.append(
                _runtime_only_row(
                    table="Enhancements",
                    source_row_id=generated_row.source_row_id,
                    faction_id=generated_row.faction_id,
                    detachment_id=generated_row.detachment_id,
                    rule_id=generated_row.enhancement_id,
                    name=generated_row.name,
                    source_ids=generated_row.source_ids,
                    runtime_consumer_ids=generated_row.runtime_consumer_ids,
                )
            )
    output.extend(bridge_by_name.values())
    return (
        tuple(sorted(output, key=lambda row: row.source_row_id)),
        tuple(sorted(runtime_only_rows, key=lambda row: row.source_row_id)),
    )


def _overlay_runtime_stratagems(
    *,
    bridge_rows: tuple[GeneratedStratagemRow, ...],
    runtime_rows: tuple[RuntimeStratagemSeed, ...],
) -> tuple[tuple[GeneratedStratagemRow, ...], tuple[GeneratedRuntimeOnlyRow, ...]]:
    bridge_by_name = {_rule_name_key(row): row for row in bridge_rows}
    output: list[GeneratedStratagemRow] = []
    runtime_only_rows: list[GeneratedRuntimeOnlyRow] = []
    for runtime_row in runtime_rows:
        owner_id = (runtime_row.faction_id, runtime_row.detachment_id)
        bridge_row = bridge_by_name.pop(_rule_name_key(runtime_row), None)
        source_ids = runtime_row.source_ids
        if bridge_row is not None:
            source_ids = _sorted_unique((*bridge_row.source_ids, *runtime_row.source_ids))
        generated_row = GeneratedStratagemRow(
            faction_id=runtime_row.faction_id,
            faction_name=CURRENT_FACTION_NAMES_BY_ID[runtime_row.faction_id],
            detachment_id=runtime_row.detachment_id,
            detachment_name=CURRENT_DETACHMENT_NAMES_BY_OWNER_ID[owner_id],
            stratagem_id=runtime_row.stratagem_id,
            name=runtime_row.name,
            command_point_cost=runtime_row.command_point_cost,
            timing=runtime_row.timing,
            category=runtime_row.category,
            source_ids=source_ids,
            runtime_consumer_ids=runtime_row.runtime_consumer_ids,
        )
        output.append(generated_row)
        if bridge_row is None:
            runtime_only_rows.append(
                _runtime_only_row(
                    table="Stratagems",
                    source_row_id=generated_row.source_row_id,
                    faction_id=generated_row.faction_id,
                    detachment_id=generated_row.detachment_id,
                    rule_id=generated_row.stratagem_id,
                    name=generated_row.name,
                    source_ids=generated_row.source_ids,
                    runtime_consumer_ids=generated_row.runtime_consumer_ids,
                )
            )
    output.extend(bridge_by_name.values())
    return (
        tuple(sorted(output, key=lambda row: row.source_row_id)),
        tuple(sorted(runtime_only_rows, key=lambda row: row.source_row_id)),
    )


def _runtime_subrule_seeds() -> tuple[
    tuple[RuntimeEnhancementSeed, ...], tuple[RuntimeStratagemSeed, ...]
]:
    enhancements: list[RuntimeEnhancementSeed] = []
    stratagems: list[RuntimeStratagemSeed] = []
    for contribution in _runtime_content_contributions():
        enhancements.extend(_runtime_enhancement_seeds(contribution))
        stratagems.extend(_runtime_stratagem_seeds(contribution))
    return (tuple(enhancements), tuple(stratagems))


def _runtime_enhancement_seeds(
    contribution: RuntimeContentContribution,
) -> tuple[RuntimeEnhancementSeed, ...]:
    rows: list[RuntimeEnhancementSeed] = []
    for effect_binding in contribution.enhancement_effect_bindings:
        faction_id, detachment_id = _owner_id_from_runtime_source_id(effect_binding.source_id)
        rows.append(
            RuntimeEnhancementSeed(
                faction_id=faction_id,
                detachment_id=detachment_id,
                enhancement_id=effect_binding.enhancement_id,
                name=_label_for_identifier(effect_binding.enhancement_id),
                source_ids=(effect_binding.source_id,),
                runtime_consumer_ids=(effect_binding.effect_id,),
            )
        )
    for fight_binding in contribution.fight_activation_ability_hook_bindings:
        owner_id = _owner_id_or_none_from_runtime_source_id(fight_binding.source_id)
        if owner_id is None:
            continue
        faction_id, detachment_id = owner_id
        enhancement_name = _label_for_identifier(fight_binding.hook_id)
        rows.append(
            RuntimeEnhancementSeed(
                faction_id=faction_id,
                detachment_id=detachment_id,
                enhancement_id=f"{faction_id}:{detachment_id}:{_slug_for_label(enhancement_name)}",
                name=enhancement_name,
                source_ids=(fight_binding.source_id,),
                runtime_consumer_ids=(fight_binding.hook_id,),
            )
        )
    for turn_end_binding in contribution.turn_end_hook_bindings:
        seed = _runtime_enhancement_seed_from_exact_source_id(
            source_id=turn_end_binding.source_id,
            runtime_consumer_id=turn_end_binding.hook_id,
        )
        if seed is not None:
            rows.append(seed)
    for unit_destroyed_binding in contribution.unit_destroyed_hook_bindings:
        seed = _runtime_enhancement_seed_from_exact_source_id(
            source_id=unit_destroyed_binding.source_id,
            runtime_consumer_id=unit_destroyed_binding.hook_id,
        )
        if seed is not None:
            rows.append(seed)
    for objective_control_binding in contribution.objective_control_modifier_bindings:
        seed = _runtime_enhancement_seed_from_exact_source_id(
            source_id=objective_control_binding.source_id,
            runtime_consumer_id=objective_control_binding.modifier_id,
        )
        if seed is not None:
            rows.append(seed)
    return tuple(rows)


def _runtime_enhancement_seed_from_exact_source_id(
    *,
    source_id: str,
    runtime_consumer_id: str,
) -> RuntimeEnhancementSeed | None:
    parsed = _exact_enhancement_owner_and_rule_id_from_source_id(source_id)
    if parsed is None:
        return None
    faction_id, detachment_id, enhancement_id = parsed
    return RuntimeEnhancementSeed(
        faction_id=faction_id,
        detachment_id=detachment_id,
        enhancement_id=enhancement_id,
        name=_label_for_identifier(enhancement_id),
        source_ids=(source_id,),
        runtime_consumer_ids=(runtime_consumer_id,),
    )


def _runtime_stratagem_seeds(
    contribution: RuntimeContentContribution,
) -> tuple[RuntimeStratagemSeed, ...]:
    handler_ids = {binding.handler_id for binding in contribution.stratagem_handler_bindings}
    rows: list[RuntimeStratagemSeed] = []
    for record in contribution.stratagem_records:
        rows.append(_runtime_stratagem_seed(record, handler_ids=handler_ids))
    return tuple(rows)


def _runtime_stratagem_seed(
    record: StratagemCatalogRecord,
    *,
    handler_ids: set[str],
) -> RuntimeStratagemSeed:
    definition = record.definition
    faction_id, detachment_id = _owner_id_from_runtime_stratagem(record)
    runtime_consumer_ids = (definition.handler_id,)
    if definition.handler_id in handler_ids:
        runtime_consumer_ids = (definition.handler_id,)
    return RuntimeStratagemSeed(
        faction_id=faction_id,
        detachment_id=detachment_id,
        stratagem_id=definition.stratagem_id,
        name=definition.name,
        command_point_cost=definition.command_point_cost,
        timing=_runtime_timing_descriptor(record),
        category=definition.category.value,
        source_ids=(definition.source_id,),
        runtime_consumer_ids=runtime_consumer_ids,
    )


def _merged_runtime_enhancement_rows(
    rows: tuple[RuntimeEnhancementSeed, ...],
) -> tuple[RuntimeEnhancementSeed, ...]:
    rows_by_identity: dict[tuple[str, str, str], RuntimeEnhancementSeed] = {}
    for row in rows:
        identity = (row.faction_id, row.detachment_id, row.enhancement_id)
        existing = rows_by_identity.get(identity)
        if existing is None:
            rows_by_identity[identity] = row
            continue
        rows_by_identity[identity] = RuntimeEnhancementSeed(
            faction_id=row.faction_id,
            detachment_id=row.detachment_id,
            enhancement_id=row.enhancement_id,
            name=row.name,
            source_ids=_sorted_unique((*existing.source_ids, *row.source_ids)),
            runtime_consumer_ids=_sorted_unique(
                (*existing.runtime_consumer_ids, *row.runtime_consumer_ids)
            ),
        )
    return tuple(sorted(rows_by_identity.values(), key=_runtime_enhancement_sort_key))


def _runtime_content_contributions() -> tuple[RuntimeContentContribution, ...]:
    contributions: list[RuntimeContentContribution] = []
    for row in generated_runtime_content_rows():
        if row.support_status is not RuntimeContentSupportStatus.SUPPORTED:
            continue
        if row.module_path is None:
            raise TypeError("Supported runtime manifest row lacks module_path.")
        module = importlib.import_module(row.module_path)
        factory_candidate = module.__dict__.get("runtime_contribution")
        if not callable(factory_candidate):
            raise TypeError("Runtime content module lacks runtime_contribution().")
        factory = cast(Callable[[], RuntimeContentContribution], factory_candidate)
        contribution = factory()
        if type(contribution) is not RuntimeContentContribution:
            raise TypeError("Runtime content module returned invalid RuntimeContentContribution.")
        if contribution.contribution_id == DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID:
            contribution = contribution.with_contribution_id(row.module_path)
        contributions.append(contribution)
    return tuple(contributions)


def _source_rows(table: str) -> tuple[dict[str, Any], ...]:
    payload = json.loads((SOURCE_JSON_DIR / f"{table}.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    if type(rows) is not list:
        raise TypeError("Wahapedia bridge payload rows must be a list.")
    validated_rows: list[dict[str, Any]] = []
    for row in cast(list[object], rows):
        if type(row) is not dict:
            raise TypeError("Wahapedia bridge payload rows must be objects.")
        validated_rows.append(cast(dict[str, Any], row))
    return tuple(validated_rows)


def _faction_rows_by_bridge_id() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for row in _source_rows("Factions"):
        fields = row["fields"]
        rows[fields["id"]] = fields
    return rows


def _skipped_bridge_row(
    *,
    table: str,
    source_row_id: str,
    faction_rows_by_bridge_id: dict[str, dict[str, str]],
    bridge_faction_id: str,
    detachment_name: str,
    skip_reason: str,
) -> GeneratedSkippedBridgeRow:
    source_faction_slug = _source_faction_slug_for_bridge_row(
        faction_rows_by_bridge_id=faction_rows_by_bridge_id,
        bridge_faction_id=bridge_faction_id,
    )
    derived_faction_id = _current_faction_id_for_bridge_slug(source_faction_slug)
    derived_detachment_id = _slug_for_label(detachment_name) if detachment_name else "<missing>"
    return GeneratedSkippedBridgeRow(
        table=table,
        bridge_source_row_id=source_row_id,
        source_faction_id=bridge_faction_id or "<missing>",
        source_faction_slug=source_faction_slug,
        source_detachment_label=detachment_name or "<missing>",
        derived_faction_id=derived_faction_id,
        derived_detachment_id=derived_detachment_id,
        skip_reason=skip_reason,
    )


def _runtime_only_row(
    *,
    table: str,
    source_row_id: str,
    faction_id: str,
    detachment_id: str,
    rule_id: str,
    name: str,
    source_ids: tuple[str, ...],
    runtime_consumer_ids: tuple[str, ...],
) -> GeneratedRuntimeOnlyRow:
    return GeneratedRuntimeOnlyRow(
        table=table,
        source_row_id=source_row_id,
        faction_id=faction_id,
        detachment_id=detachment_id,
        rule_id=rule_id,
        name=name,
        source_ids=source_ids,
        runtime_consumer_ids=runtime_consumer_ids,
        provenance_reason=RUNTIME_ONLY_PROVENANCE_REASON,
    )


def _current_faction_id_for_bridge_row(
    *,
    faction_rows_by_bridge_id: dict[str, dict[str, str]],
    bridge_faction_id: str,
) -> str:
    slug = _source_faction_slug_for_bridge_row(
        faction_rows_by_bridge_id=faction_rows_by_bridge_id,
        bridge_faction_id=bridge_faction_id,
    )
    return _current_faction_id_for_bridge_slug(slug)


def _source_faction_slug_for_bridge_row(
    *,
    faction_rows_by_bridge_id: dict[str, dict[str, str]],
    bridge_faction_id: str,
) -> str:
    if not bridge_faction_id:
        return "<missing>"
    fields = faction_rows_by_bridge_id.get(bridge_faction_id)
    if fields is None:
        return "<unknown>"
    return fields["link"].strip("/").split("/")[-1]


def _current_faction_id_for_bridge_slug(slug: str) -> str:
    if slug in {"<missing>", "<unknown>"}:
        return slug
    return FACTION_SLUG_OVERRIDES.get(slug, slug)


def _owner_id_from_runtime_stratagem(record: StratagemCatalogRecord) -> tuple[str, str]:
    pieces = record.definition.stratagem_id.split(":")
    if len(pieces) >= 3:
        owner_id = (pieces[0], pieces[1])
        if owner_id in CURRENT_SOURCE_OWNER_IDS:
            return owner_id
    if record.detachment_id is not None:
        for faction_id, detachment_id in CURRENT_SOURCE_OWNER_IDS:
            if detachment_id == record.detachment_id:
                return (faction_id, detachment_id)
    return _owner_id_from_runtime_source_id(record.definition.source_id)


def _owner_id_from_runtime_source_id(source_id: str) -> tuple[str, str]:
    owner_id = _owner_id_or_none_from_runtime_source_id(source_id)
    if owner_id is not None:
        return owner_id
    raise TypeError(f"Runtime source ID does not include a current owner: {source_id}")


def _owner_id_or_none_from_runtime_source_id(source_id: str) -> tuple[str, str] | None:
    pieces = source_id.split(":")
    for index in range(len(pieces) - 1):
        owner_id = (pieces[index], pieces[index + 1])
        if owner_id in CURRENT_SOURCE_OWNER_IDS:
            return owner_id
    return None


def _exact_enhancement_owner_and_rule_id_from_source_id(
    source_id: str,
) -> tuple[str, str, str] | None:
    pieces = source_id.split(":")
    for index, piece in enumerate(pieces):
        if piece != "enhancement":
            continue
        if index + 3 >= len(pieces):
            continue
        owner_id = (pieces[index + 1], pieces[index + 2])
        if owner_id not in CURRENT_SOURCE_OWNER_IDS:
            continue
        enhancement_id = ":".join(pieces[index + 3 :])
        if not enhancement_id:
            continue
        return (owner_id[0], owner_id[1], enhancement_id)
    return None


def _runtime_timing_descriptor(record: StratagemCatalogRecord) -> str:
    timing = record.definition.timing
    phase = None if timing.phase is None else timing.phase.value
    if phase is None and timing.timing_window_id is None:
        return timing.trigger_kind.value
    if timing.timing_window_id is None:
        return f"{timing.trigger_kind.value}:{phase}"
    return f"{timing.trigger_kind.value}:{phase}:{timing.timing_window_id}"


def _bridge_timing_descriptor(fields: dict[str, str]) -> str:
    turn = fields["turn"].strip()
    phase = fields["phase"].strip()
    if turn and phase:
        return f"{turn}; {phase}"
    if phase:
        return phase
    return turn


def _rule_name_key(
    row: GeneratedEnhancementRow
    | GeneratedStratagemRow
    | RuntimeEnhancementSeed
    | RuntimeStratagemSeed,
) -> tuple[str, str, str]:
    return (row.faction_id, row.detachment_id, _normalized_name(row.name))


def _runtime_enhancement_sort_key(row: RuntimeEnhancementSeed) -> str:
    return f"{row.faction_id}:{row.detachment_id}:{row.enhancement_id}"


def _enhancement_source_row_id(row: RuntimeEnhancementSeed) -> str:
    return f"enhancement:{row.faction_id}:{row.detachment_id}:{row.enhancement_id}"


def _label_for_identifier(identifier: str) -> str:
    tail = identifier.split(":")[-1]
    return " ".join(piece.capitalize() for piece in tail.replace("_", "-").split("-"))


def _normalized_name(name: str) -> str:
    return _slug_for_label(name).replace("-the-", "-")


def _slug_for_label(label: str) -> str:
    normalized = unicodedata.normalize("NFKD", label)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _bridge_source_id(*, table: str, source_row_id: str) -> str:
    return f"{BRIDGE_SOURCE_PACKAGE_ID}:{table}:{source_row_id}"


def _optional_int(raw_value: str) -> int | None:
    stripped = raw_value.strip()
    if not stripped:
        return None
    return int(stripped)


def _required_int(raw_value: str) -> int:
    return int(raw_value.strip())


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _validate_approved_skipped_bridge_rows(
    rows: tuple[GeneratedSkippedBridgeRow, ...],
) -> tuple[GeneratedSkippedBridgeRow, ...]:
    for row in rows:
        if row.skip_reason not in APPROVED_SKIPPED_BRIDGE_REASONS:
            raise TypeError(f"Unapproved bridge skip reason: {row.skip_reason}")
        owner_id = (row.derived_faction_id, row.derived_detachment_id)
        if (
            row.skip_reason == SKIP_REASON_OWNER_NOT_IN_CURRENT_SOURCE_PACKAGE
            and owner_id in CURRENT_SOURCE_OWNER_IDS
        ):
            raise TypeError(f"Bridge skip maps to a current source owner: {row.source_row_id}")
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _validate_approved_runtime_only_rows(
    rows: tuple[GeneratedRuntimeOnlyRow, ...],
) -> tuple[GeneratedRuntimeOnlyRow, ...]:
    actual_ids = {row.source_row_id for row in rows}
    unexpected = sorted(actual_ids.difference(APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS))
    if unexpected:
        raise TypeError(f"Runtime-only rows require explicit approval: {unexpected}")
    missing = sorted(APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS.difference(actual_ids))
    if missing:
        raise TypeError(f"Approved runtime-only rows were not emitted: {missing}")
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _module_content(
    *,
    enhancements: tuple[GeneratedEnhancementRow, ...],
    stratagems: tuple[GeneratedStratagemRow, ...],
    skipped_bridge_rows: tuple[GeneratedSkippedBridgeRow, ...],
    runtime_only_rows: tuple[GeneratedRuntimeOnlyRow, ...],
) -> str:
    return "\n".join(
        (
            "# Generated by tools/generate_faction_subrule_source_package.py.",
            "# Regenerate with `uv run python tools/generate_faction_subrule_source_package.py`.",
            "# ruff: noqa: E501",
            "# fmt: off",
            "from __future__ import annotations",
            "",
            "import hashlib",
            "import json",
            "from dataclasses import dataclass",
            "from enum import StrEnum",
            "from typing import Self, TypedDict, cast",
            "",
            'EDITION_ID = "warhammer_40000_11th"',
            'SOURCE_EDITION = "11th"',
            'SOURCE_PACKAGE_ID = "gw-11e-phase17e-exact-faction-subrules-2026-27"',
            'SOURCE_TITLE = "Warhammer 40,000 11th Edition Exact Faction Subrules"',
            'SOURCE_VERSION = "2026-27"',
            'SOURCE_DATE = "2026-06-21"',
            'UPSTREAM_IDENTITY = "source-bridge-plus-core-v2-runtime-named-handlers"',
            'IMPORTED_AT_SCHEMA_VERSION = "core-v2-phase17-exact-faction-subrules-v1"',
            (
                'APPROVED_SKIPPED_BRIDGE_REASONS = frozenset(("missing_owner_fields", '
                '"owner_not_in_current_source_package"))'
            ),
            (
                "APPROVED_RUNTIME_ONLY_PROVENANCE_REASONS = "
                'frozenset(("runtime_handler_without_bridge_source_row",))'
            ),
            "",
            "",
            _module_class_content(),
            "",
            _module_rows_content(
                enhancements=enhancements,
                stratagems=stratagems,
                skipped_bridge_rows=skipped_bridge_rows,
                runtime_only_rows=runtime_only_rows,
            ),
            "",
        )
    )


def _module_class_content() -> str:
    return r"""
class SourceSubruleRuntimeStatus(StrEnum):
    SOURCE_ONLY = "source_only"
    ENGINE_CONSUMED = "engine_consumed"


class SourceEnhancementRowPayload(TypedDict):
    source_row_id: str
    source_id: str
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    enhancement_id: str
    name: str
    points: int | None
    timing_descriptor: str
    category: str
    source_ids: list[str]
    runtime_support_status: str
    runtime_consumer_ids: list[str]


class SourceStratagemRowPayload(TypedDict):
    source_row_id: str
    source_id: str
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    stratagem_id: str
    name: str
    command_point_cost: int
    timing_descriptor: str
    category: str
    source_ids: list[str]
    runtime_support_status: str
    runtime_consumer_ids: list[str]


class SourceSkippedBridgeRowPayload(TypedDict):
    source_row_id: str
    source_id: str
    table: str
    bridge_source_row_id: str
    source_faction_id: str
    source_faction_slug: str
    source_detachment_label: str
    derived_faction_id: str
    derived_detachment_id: str
    skip_reason: str


class SourceRuntimeOnlyRowPayload(TypedDict):
    source_row_id: str
    source_id: str
    table: str
    faction_id: str
    detachment_id: str
    rule_id: str
    name: str
    source_ids: list[str]
    runtime_consumer_ids: list[str]
    provenance_reason: str


@dataclass(frozen=True, slots=True)
class SourceEnhancementRow:
    source_row_id: str
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    enhancement_id: str
    name: str
    points: int | None
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_row_id", _validate_identifier(self.source_row_id))
        object.__setattr__(self, "faction_id", _validate_identifier(self.faction_id))
        object.__setattr__(self, "faction_name", _validate_text(self.faction_name))
        object.__setattr__(self, "detachment_id", _validate_identifier(self.detachment_id))
        object.__setattr__(self, "detachment_name", _validate_text(self.detachment_name))
        object.__setattr__(self, "enhancement_id", _validate_identifier(self.enhancement_id))
        object.__setattr__(self, "name", _validate_text(self.name))
        if self.points is not None and (type(self.points) is not int or self.points < 0):
            raise ValueError("Source Enhancement points must be a non-negative int or None.")
        object.__setattr__(self, "source_ids", _validate_identifier_tuple(self.source_ids))
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validate_identifier_tuple(self.runtime_consumer_ids, allow_empty=True),
        )

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:{self.source_row_id}"

    @property
    def timing_descriptor(self) -> str:
        return "army_construction"

    @property
    def category(self) -> str:
        return "enhancement"

    @property
    def runtime_support_status(self) -> SourceSubruleRuntimeStatus:
        if self.runtime_consumer_ids:
            return SourceSubruleRuntimeStatus.ENGINE_CONSUMED
        return SourceSubruleRuntimeStatus.SOURCE_ONLY

    @property
    def all_source_ids(self) -> tuple[str, ...]:
        return _validate_identifier_tuple((self.source_id, *self.source_ids))

    def to_payload(self) -> SourceEnhancementRowPayload:
        return {
            "source_row_id": self.source_row_id,
            "source_id": self.source_id,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "detachment_id": self.detachment_id,
            "detachment_name": self.detachment_name,
            "enhancement_id": self.enhancement_id,
            "name": self.name,
            "points": self.points,
            "timing_descriptor": self.timing_descriptor,
            "category": self.category,
            "source_ids": list(self.all_source_ids),
            "runtime_support_status": self.runtime_support_status.value,
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
        }

    @classmethod
    def from_payload(cls, payload: SourceEnhancementRowPayload) -> Self:
        declared_source_id = payload["source_id"]
        source_ids = tuple(value for value in payload["source_ids"] if value != declared_source_id)
        return cls(
            source_row_id=payload["source_row_id"],
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            detachment_id=payload["detachment_id"],
            detachment_name=payload["detachment_name"],
            enhancement_id=payload["enhancement_id"],
            name=payload["name"],
            points=payload["points"],
            source_ids=source_ids,
            runtime_consumer_ids=tuple(payload["runtime_consumer_ids"]),
        )


@dataclass(frozen=True, slots=True)
class SourceStratagemRow:
    source_row_id: str
    faction_id: str
    faction_name: str
    detachment_id: str
    detachment_name: str
    stratagem_id: str
    name: str
    command_point_cost: int
    timing_descriptor: str
    category: str
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_row_id", _validate_identifier(self.source_row_id))
        object.__setattr__(self, "faction_id", _validate_identifier(self.faction_id))
        object.__setattr__(self, "faction_name", _validate_text(self.faction_name))
        object.__setattr__(self, "detachment_id", _validate_identifier(self.detachment_id))
        object.__setattr__(self, "detachment_name", _validate_text(self.detachment_name))
        object.__setattr__(self, "stratagem_id", _validate_identifier(self.stratagem_id))
        object.__setattr__(self, "name", _validate_text(self.name))
        if type(self.command_point_cost) is not int or self.command_point_cost < 0:
            raise ValueError("Source Stratagem command_point_cost must be a non-negative int.")
        object.__setattr__(self, "timing_descriptor", _validate_text(self.timing_descriptor))
        object.__setattr__(self, "category", _validate_text(self.category))
        object.__setattr__(self, "source_ids", _validate_identifier_tuple(self.source_ids))
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validate_identifier_tuple(self.runtime_consumer_ids, allow_empty=True),
        )

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:{self.source_row_id}"

    @property
    def runtime_support_status(self) -> SourceSubruleRuntimeStatus:
        if self.runtime_consumer_ids:
            return SourceSubruleRuntimeStatus.ENGINE_CONSUMED
        return SourceSubruleRuntimeStatus.SOURCE_ONLY

    @property
    def all_source_ids(self) -> tuple[str, ...]:
        return _validate_identifier_tuple((self.source_id, *self.source_ids))

    def to_payload(self) -> SourceStratagemRowPayload:
        return {
            "source_row_id": self.source_row_id,
            "source_id": self.source_id,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "detachment_id": self.detachment_id,
            "detachment_name": self.detachment_name,
            "stratagem_id": self.stratagem_id,
            "name": self.name,
            "command_point_cost": self.command_point_cost,
            "timing_descriptor": self.timing_descriptor,
            "category": self.category,
            "source_ids": list(self.all_source_ids),
            "runtime_support_status": self.runtime_support_status.value,
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
        }

    @classmethod
    def from_payload(cls, payload: SourceStratagemRowPayload) -> Self:
        declared_source_id = payload["source_id"]
        source_ids = tuple(value for value in payload["source_ids"] if value != declared_source_id)
        return cls(
            source_row_id=payload["source_row_id"],
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            detachment_id=payload["detachment_id"],
            detachment_name=payload["detachment_name"],
            stratagem_id=payload["stratagem_id"],
            name=payload["name"],
            command_point_cost=payload["command_point_cost"],
            timing_descriptor=payload["timing_descriptor"],
            category=payload["category"],
            source_ids=source_ids,
            runtime_consumer_ids=tuple(payload["runtime_consumer_ids"]),
        )


@dataclass(frozen=True, slots=True)
class SourceSkippedBridgeRow:
    table: str
    bridge_source_row_id: str
    source_faction_id: str
    source_faction_slug: str
    source_detachment_label: str
    derived_faction_id: str
    derived_detachment_id: str
    skip_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "table", _validate_identifier(self.table))
        object.__setattr__(
            self, "bridge_source_row_id", _validate_identifier(self.bridge_source_row_id)
        )
        object.__setattr__(self, "source_faction_id", _validate_text(self.source_faction_id))
        object.__setattr__(self, "source_faction_slug", _validate_text(self.source_faction_slug))
        object.__setattr__(
            self, "source_detachment_label", _validate_text(self.source_detachment_label)
        )
        object.__setattr__(
            self, "derived_faction_id", _validate_identifier(self.derived_faction_id)
        )
        object.__setattr__(
            self, "derived_detachment_id", _validate_identifier(self.derived_detachment_id)
        )
        object.__setattr__(self, "skip_reason", _validate_identifier(self.skip_reason))
        if self.skip_reason not in APPROVED_SKIPPED_BRIDGE_REASONS:
            raise ValueError("Skipped bridge row reason is not approved.")

    @property
    def source_row_id(self) -> str:
        return f"skipped-bridge:{self.table}:{self.bridge_source_row_id}"

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:{self.source_row_id}"

    def to_payload(self) -> SourceSkippedBridgeRowPayload:
        return {
            "source_row_id": self.source_row_id,
            "source_id": self.source_id,
            "table": self.table,
            "bridge_source_row_id": self.bridge_source_row_id,
            "source_faction_id": self.source_faction_id,
            "source_faction_slug": self.source_faction_slug,
            "source_detachment_label": self.source_detachment_label,
            "derived_faction_id": self.derived_faction_id,
            "derived_detachment_id": self.derived_detachment_id,
            "skip_reason": self.skip_reason,
        }

    @classmethod
    def from_payload(cls, payload: SourceSkippedBridgeRowPayload) -> Self:
        return cls(
            table=payload["table"],
            bridge_source_row_id=payload["bridge_source_row_id"],
            source_faction_id=payload["source_faction_id"],
            source_faction_slug=payload["source_faction_slug"],
            source_detachment_label=payload["source_detachment_label"],
            derived_faction_id=payload["derived_faction_id"],
            derived_detachment_id=payload["derived_detachment_id"],
            skip_reason=payload["skip_reason"],
        )


@dataclass(frozen=True, slots=True)
class SourceRuntimeOnlyRow:
    table: str
    source_row_id: str
    faction_id: str
    detachment_id: str
    rule_id: str
    name: str
    source_ids: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]
    provenance_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "table", _validate_identifier(self.table))
        object.__setattr__(self, "source_row_id", _validate_identifier(self.source_row_id))
        object.__setattr__(self, "faction_id", _validate_identifier(self.faction_id))
        object.__setattr__(self, "detachment_id", _validate_identifier(self.detachment_id))
        object.__setattr__(self, "rule_id", _validate_identifier(self.rule_id))
        object.__setattr__(self, "name", _validate_text(self.name))
        object.__setattr__(self, "source_ids", _validate_identifier_tuple(self.source_ids))
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validate_identifier_tuple(self.runtime_consumer_ids),
        )
        object.__setattr__(self, "provenance_reason", _validate_identifier(self.provenance_reason))
        if self.provenance_reason not in APPROVED_RUNTIME_ONLY_PROVENANCE_REASONS:
            raise ValueError("Runtime-only row provenance reason is not approved.")

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:runtime-only:{self.source_row_id}"

    def to_payload(self) -> SourceRuntimeOnlyRowPayload:
        return {
            "source_row_id": self.source_row_id,
            "source_id": self.source_id,
            "table": self.table,
            "faction_id": self.faction_id,
            "detachment_id": self.detachment_id,
            "rule_id": self.rule_id,
            "name": self.name,
            "source_ids": list(self.source_ids),
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "provenance_reason": self.provenance_reason,
        }

    @classmethod
    def from_payload(cls, payload: SourceRuntimeOnlyRowPayload) -> Self:
        return cls(
            table=payload["table"],
            source_row_id=payload["source_row_id"],
            faction_id=payload["faction_id"],
            detachment_id=payload["detachment_id"],
            rule_id=payload["rule_id"],
            name=payload["name"],
            source_ids=tuple(payload["source_ids"]),
            runtime_consumer_ids=tuple(payload["runtime_consumer_ids"]),
            provenance_reason=payload["provenance_reason"],
        )


def enhancement_rows() -> tuple[SourceEnhancementRow, ...]:
    return _ENHANCEMENT_ROWS


def stratagem_rows() -> tuple[SourceStratagemRow, ...]:
    return _STRATAGEM_ROWS


def skipped_bridge_rows() -> tuple[SourceSkippedBridgeRow, ...]:
    return _SKIPPED_BRIDGE_ROWS


def runtime_only_rows() -> tuple[SourceRuntimeOnlyRow, ...]:
    return _RUNTIME_ONLY_ROWS


def source_package_identity_payload() -> dict[str, str]:
    return {
        "edition_id": EDITION_ID,
        "source_edition": SOURCE_EDITION,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "upstream_identity": UPSTREAM_IDENTITY,
        "source_payload_checksum_sha256": source_payload_checksum_sha256(),
        "enhancement_row_count": str(len(_ENHANCEMENT_ROWS)),
        "stratagem_row_count": str(len(_STRATAGEM_ROWS)),
        "skipped_bridge_row_count": str(len(_SKIPPED_BRIDGE_ROWS)),
        "runtime_only_row_count": str(len(_RUNTIME_ONLY_ROWS)),
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def source_payload_checksum_sha256() -> str:
    encoded = json.dumps(
        {
            "enhancement_rows": [row.to_payload() for row in _ENHANCEMENT_ROWS],
            "runtime_only_rows": [row.to_payload() for row in _RUNTIME_ONLY_ROWS],
            "skipped_bridge_rows": [row.to_payload() for row in _SKIPPED_BRIDGE_ROWS],
            "stratagem_rows": [row.to_payload() for row in _STRATAGEM_ROWS],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_enhancement_rows(
    rows: tuple[SourceEnhancementRow, ...],
) -> tuple[SourceEnhancementRow, ...]:
    _validate_unique_source_rows(tuple(row.source_row_id for row in rows))
    _validate_unique_exact_rows(tuple(
        (row.faction_id, row.detachment_id, row.enhancement_id) for row in rows
    ))
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _validate_stratagem_rows(
    rows: tuple[SourceStratagemRow, ...],
) -> tuple[SourceStratagemRow, ...]:
    _validate_unique_source_rows(tuple(row.source_row_id for row in rows))
    _validate_unique_exact_rows(tuple(
        (row.faction_id, row.detachment_id, row.stratagem_id) for row in rows
    ))
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _validate_skipped_bridge_rows(
    rows: tuple[SourceSkippedBridgeRow, ...],
) -> tuple[SourceSkippedBridgeRow, ...]:
    _validate_unique_source_rows(tuple(row.source_row_id for row in rows))
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _validate_runtime_only_rows(
    rows: tuple[SourceRuntimeOnlyRow, ...],
) -> tuple[SourceRuntimeOnlyRow, ...]:
    _validate_unique_source_rows(tuple(row.source_row_id for row in rows))
    return tuple(sorted(rows, key=lambda row: row.source_row_id))


def _validate_unique_source_rows(source_row_ids: tuple[str, ...]) -> None:
    if len(set(source_row_ids)) != len(source_row_ids):
        raise ValueError("Exact faction subrule source_row_id values must be unique.")


def _validate_unique_exact_rows(exact_ids: tuple[tuple[str, str, str], ...]) -> None:
    if len(set(exact_ids)) != len(exact_ids):
        raise ValueError("Exact faction subrule owner/rule IDs must be unique.")


def _validate_identifier(value: object) -> str:
    if type(value) is not str:
        raise ValueError("Exact faction subrule identifiers must be strings.")
    stripped = value.strip()
    if not stripped:
        raise ValueError("Exact faction subrule identifiers must not be empty.")
    return stripped


def _validate_text(value: object) -> str:
    return _validate_identifier(value)


def _validate_identifier_tuple(
    values: object,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ValueError("Exact faction subrule identifier tuples must be tuples.")
    if not values and not allow_empty:
        raise ValueError("Exact faction subrule identifier tuples must not be empty.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(value)
        if identifier in seen:
            raise ValueError("Exact faction subrule identifier tuples must be unique.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))
""".strip()


def _module_rows_content(
    *,
    enhancements: tuple[GeneratedEnhancementRow, ...],
    stratagems: tuple[GeneratedStratagemRow, ...],
    skipped_bridge_rows: tuple[GeneratedSkippedBridgeRow, ...],
    runtime_only_rows: tuple[GeneratedRuntimeOnlyRow, ...],
) -> str:
    enhancement_lines = [
        "_ENHANCEMENT_ROWS: tuple[SourceEnhancementRow, ...] = _validate_enhancement_rows((",
        *(_enhancement_constructor_line(row) for row in enhancements),
        "))",
    ]
    stratagem_lines = [
        "_STRATAGEM_ROWS: tuple[SourceStratagemRow, ...] = _validate_stratagem_rows((",
        *(_stratagem_constructor_line(row) for row in stratagems),
        "))",
    ]
    skipped_bridge_lines = [
        (
            "_SKIPPED_BRIDGE_ROWS: tuple[SourceSkippedBridgeRow, ...] = "
            "_validate_skipped_bridge_rows(("
        ),
        *(_skipped_bridge_constructor_line(row) for row in skipped_bridge_rows),
        "))",
    ]
    runtime_only_lines = [
        "_RUNTIME_ONLY_ROWS: tuple[SourceRuntimeOnlyRow, ...] = _validate_runtime_only_rows((",
        *(_runtime_only_constructor_line(row) for row in runtime_only_rows),
        "))",
    ]
    return "\n".join(
        (
            *enhancement_lines,
            "",
            *stratagem_lines,
            "",
            *skipped_bridge_lines,
            "",
            *runtime_only_lines,
        )
    )


def _enhancement_constructor_line(row: GeneratedEnhancementRow) -> str:
    return (
        "    SourceEnhancementRow("
        f"source_row_id={_py_string(row.source_row_id)}, "
        f"faction_id={_py_string(row.faction_id)}, "
        f"faction_name={_py_string(row.faction_name)}, "
        f"detachment_id={_py_string(row.detachment_id)}, "
        f"detachment_name={_py_string(row.detachment_name)}, "
        f"enhancement_id={_py_string(row.enhancement_id)}, "
        f"name={_py_string(row.name)}, "
        f"points={_py_optional_int(row.points)}, "
        f"source_ids={_py_tuple(row.source_ids)}, "
        f"runtime_consumer_ids={_py_tuple(row.runtime_consumer_ids)}"
        "),"
    )


def _stratagem_constructor_line(row: GeneratedStratagemRow) -> str:
    return (
        "    SourceStratagemRow("
        f"source_row_id={_py_string(row.source_row_id)}, "
        f"faction_id={_py_string(row.faction_id)}, "
        f"faction_name={_py_string(row.faction_name)}, "
        f"detachment_id={_py_string(row.detachment_id)}, "
        f"detachment_name={_py_string(row.detachment_name)}, "
        f"stratagem_id={_py_string(row.stratagem_id)}, "
        f"name={_py_string(row.name)}, "
        f"command_point_cost={row.command_point_cost}, "
        f"timing_descriptor={_py_string(row.timing)}, "
        f"category={_py_string(row.category)}, "
        f"source_ids={_py_tuple(row.source_ids)}, "
        f"runtime_consumer_ids={_py_tuple(row.runtime_consumer_ids)}"
        "),"
    )


def _skipped_bridge_constructor_line(row: GeneratedSkippedBridgeRow) -> str:
    return (
        "    SourceSkippedBridgeRow("
        f"table={_py_string(row.table)}, "
        f"bridge_source_row_id={_py_string(row.bridge_source_row_id)}, "
        f"source_faction_id={_py_string(row.source_faction_id)}, "
        f"source_faction_slug={_py_string(row.source_faction_slug)}, "
        f"source_detachment_label={_py_string(row.source_detachment_label)}, "
        f"derived_faction_id={_py_string(row.derived_faction_id)}, "
        f"derived_detachment_id={_py_string(row.derived_detachment_id)}, "
        f"skip_reason={_py_string(row.skip_reason)}"
        "),"
    )


def _runtime_only_constructor_line(row: GeneratedRuntimeOnlyRow) -> str:
    return (
        "    SourceRuntimeOnlyRow("
        f"table={_py_string(row.table)}, "
        f"source_row_id={_py_string(row.source_row_id)}, "
        f"faction_id={_py_string(row.faction_id)}, "
        f"detachment_id={_py_string(row.detachment_id)}, "
        f"rule_id={_py_string(row.rule_id)}, "
        f"name={_py_string(row.name)}, "
        f"source_ids={_py_tuple(row.source_ids)}, "
        f"runtime_consumer_ids={_py_tuple(row.runtime_consumer_ids)}, "
        f"provenance_reason={_py_string(row.provenance_reason)}"
        "),"
    )


def _py_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _py_tuple(values: tuple[str, ...]) -> str:
    if not values:
        return "()"
    contents = ", ".join(_py_string(value) for value in values)
    if len(values) == 1:
        contents = f"{contents},"
    return f"({contents})"


def _py_optional_int(value: int | None) -> str:
    if value is None:
        return "None"
    return str(value)


if __name__ == "__main__":
    main()
