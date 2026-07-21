from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.generate_ability_support_matrix import DatasheetSupportRow

if TYPE_CHECKING or __package__:
    from tools.aeldari_ability_semantic_descriptions import (
        DOCUMENTATION_BUCKET_STILL_NEEDED,
        DOCUMENTATION_BUCKET_SUPPORTED,
        AeldariAbilitySemanticDescription,
        aeldari_ability_semantic_descriptions,
    )
    from tools.aeldari_datasheet_semantic_coverage import (
        SEMANTIC_BUCKET_ALL_CONSUMED,
        SEMANTIC_BUCKET_BRIDGE_BLOCKED,
        SEMANTIC_BUCKET_HOST_NEEDED,
        SEMANTIC_BUCKET_UNSUPPORTED_IR,
        AeldariDatasheetSemanticCoverage,
        aeldari_datasheet_semantic_coverage,
    )
    from tools.aeldari_datasheet_semantic_snapshot import (
        aeldari_datasheet_semantic_snapshot_markdown,
    )
else:
    from aeldari_ability_semantic_descriptions import (
        DOCUMENTATION_BUCKET_STILL_NEEDED,
        DOCUMENTATION_BUCKET_SUPPORTED,
        AeldariAbilitySemanticDescription,
        aeldari_ability_semantic_descriptions,
    )
    from aeldari_datasheet_semantic_coverage import (
        SEMANTIC_BUCKET_ALL_CONSUMED,
        SEMANTIC_BUCKET_BRIDGE_BLOCKED,
        SEMANTIC_BUCKET_HOST_NEEDED,
        SEMANTIC_BUCKET_UNSUPPORTED_IR,
        AeldariDatasheetSemanticCoverage,
        aeldari_datasheet_semantic_coverage,
    )
    from aeldari_datasheet_semantic_snapshot import (
        aeldari_datasheet_semantic_snapshot_markdown,
    )

_IR_COVERAGE_LABELS = {
    SEMANTIC_BUCKET_ALL_CONSUMED: "All consumed",
    SEMANTIC_BUCKET_HOST_NEEDED: "IR parsed; host needed",
    SEMANTIC_BUCKET_UNSUPPORTED_IR: "Unsupported IR",
    SEMANTIC_BUCKET_BRIDGE_BLOCKED: "Bridge/catalog blocked",
}

_ACCEPTED_OVERALL_STATUSES = frozenset({"Full", "Playable"})
_ACCEPTED_WEAPON_KEYWORD_STATUSES = frozenset({"Full", "None"})
_HOST_LIMITATION_PREFIX = "host limitation: "

_DETACHMENT_SEMANTICS_NEEDED_BY_ID = {
    "armoured-warhost": (
        "IR still needed: grant Assault to ranged weapons of friendly Aeldari Vehicle models and "
        "grant Advance rerolls to friendly Aeldari Vehicle Fly units."
    ),
    "aspect-host": (
        "IR still needed: when an Aspect Warriors or Avatar of Khaine unit is selected to shoot or "
        "fight, offer a phase-scoped choice between Hit-rolls-of-1 and Wound-rolls-of-1 rerolls."
    ),
    "devoted-of-ynnead": (
        "IR still needed: Ynnari mustering/keyword/Warlord rules; an end-of-opponent-"
        "Shooting-phase D6+1 reactive move after a nearby Ynnari unit is destroyed; a Fade Back "
        "replacement move that can enter Engagement Range; and a Fight-start Fights First grant "
        "below Starting Strength."
    ),
    "eldritch-raiders": (
        "IR still needed: army-wide charge-after-Advance, Advance rerolls for Anhrathe/Rangers/"
        "Shroud Runners, and Veterans of the Void mustering for unique paid Corsair Enhancements."
    ),
    "fateful-performance": (
        "IR still needed: Harlequins Charge moves through enemy models and mustering-time "
        "exclusive ACROBATIC detachment-tag validation."
    ),
    "ghosts-of-the-webway": (
        "IR still needed: Harlequins Charge transit through enemy models, Troupe Battleline and "
        "Objective Control 2 grants, and the three-copy Death Jester/Shadowseer/Troupe Master cap."
    ),
    "guardian-battlehost": (
        "IR still needed: +1 Hit for Dire Avenger, Guardian, Support Weapon, and War Walker "
        "attacks when either the attacking unit or target is within range of an objective marker."
    ),
    "seer-council": (
        "IR still needed: battle-size-scaled Fate dice generation, a replay-safe Fate dice pool, "
        "and value-matched dice discard to reduce the corresponding Stratagem's CP cost."
    ),
    "serpents-brood": (
        "IR still needed: Sustained Hits 1 for Harlequins Mounted/Vehicle weapons and newly "
        "disembarked Harlequins, plus Troupe Battleline/OC 2 and Travelling Players roster caps."
    ),
    "spirit-conclave": (
        "IR still needed: Vengeful Dead tokens on Psyker destruction, marked-target +1 Hit/Wound "
        "for Wraith Constructs, a 12-inch Spirit Guides Battle Focus aura, and Wraith Battleline "
        "grants."
    ),
    "twilight-flickers": (
        "IR still needed: a friendly Harlequins Stealth grant and mustering-time exclusive "
        "ACROBATIC detachment-tag validation."
    ),
    "warhost": (
        "IR still needed: one extra Battle Focus token each battle round, +1 inch for Swift as the "
        "Wind, and +1 to D6 results used by Agile Manoeuvres."
    ),
    "windrider-host": (
        "IR still needed: Mounted/Vyper reserve declaration, battle-round advancement for arrival, "
        "battle-size-capped end-of-opponent-turn return to Strategic Reserves, and Windrider "
        "Battleline."
    ),
}


def aeldari_semantic_snapshot_markdown(
    *,
    detachment_rows: tuple[tuple[str, bool], ...],
    enhancement_rows: tuple[tuple[str, str, bool], ...],
    stratagem_rows: tuple[tuple[str, str, bool], ...],
) -> list[str]:
    lines = [
        "",
        "## Semantic Support Snapshot",
        "",
        (
            "This generated snapshot separates source review from semantic execution. "
            "Detachment-rule support uses the semantic support table below. Exact "
            "Enhancement and Stratagem support uses the shared Phase17F execution evidence. "
            "The Exact Ability Semantic Coverage table groups the reviewed Aeldari source scope "
            "by tradition. It bridges every effective datasheet and derives each semantic bucket "
            "from exact datasheet and wargear ability text, parser diagnostics, and runtime "
            "consumers. It does not report catalog or playability support; the separate Datasheet "
            "/ Unit Support table remains authoritative for those fields."
        ),
        "",
        "### Detachments",
        "",
        "| Fully supported | Still needs semantic support |",
        "| --- | --- |",
        (
            f"| {_markdown_line_list(name for name, supported in detachment_rows if supported)} | "
            f"{_markdown_line_list(name for name, supported in detachment_rows if not supported)} |"
        ),
    ]
    lines.extend(_exact_source_rows_snapshot_markdown("Enhancements", enhancement_rows))
    lines.extend(_exact_source_rows_snapshot_markdown("Stratagems", stratagem_rows))
    lines.extend(aeldari_datasheet_semantic_snapshot_markdown())
    return lines


def _exact_source_rows_snapshot_markdown(
    title: str,
    rows: tuple[tuple[str, str, bool], ...],
) -> list[str]:
    lines = [
        "",
        f"### {title}",
        "",
        "| Detachment | Runtime supported / executable | Still source-only / blocked |",
        "| --- | --- | --- |",
    ]
    for detachment_name in sorted({row[0] for row in rows}):
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(detachment_name),
                    _markdown_line_list(
                        sorted(
                            rule_name
                            for row_detachment, rule_name, supported in rows
                            if row_detachment == detachment_name and supported
                        )
                    ),
                    _markdown_line_list(
                        sorted(
                            rule_name
                            for row_detachment, rule_name, supported in rows
                            if row_detachment == detachment_name and not supported
                        )
                    ),
                )
            )
            + " |"
        )
    return lines


def aeldari_detachment_semantics_needed(detachment_id: str) -> str:
    description = _DETACHMENT_SEMANTICS_NEEDED_BY_ID.get(detachment_id)
    if description is None:
        raise ValueError(
            "Unsupported Aeldari detachment is missing an IR-semantics-needed description."
        )
    return description


def aeldari_datasheet_support_markdown(
    *,
    support_rows_by_datasheet_id: Mapping[str, DatasheetSupportRow],
) -> list[str]:
    coverage = aeldari_datasheet_semantic_coverage()
    descriptions = aeldari_ability_semantic_descriptions()
    reviewed_ids = {row.datasheet_id for row in coverage.rows}
    unknown_support_ids = support_rows_by_datasheet_id.keys() - reviewed_ids
    if unknown_support_ids:
        raise ValueError(
            "Aeldari generated datasheet support rows are absent from the exact semantic review."
        )
    descriptions_by_ability_id = {row.ability_id: row for row in descriptions.rows}
    lines: list[str] = []
    group_names = tuple(dict.fromkeys(row.group for row in coverage.rows))
    for group_name in group_names:
        lines.extend(
            _group_markdown(
                group_name=group_name,
                rows=tuple(row for row in coverage.rows if row.group == group_name),
                descriptions_by_ability_id=descriptions_by_ability_id,
                support_rows_by_datasheet_id=support_rows_by_datasheet_id,
            )
        )
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _group_markdown(
    *,
    group_name: str,
    rows: tuple[AeldariDatasheetSemanticCoverage, ...],
    descriptions_by_ability_id: Mapping[str, AeldariAbilitySemanticDescription],
    support_rows_by_datasheet_id: Mapping[str, DatasheetSupportRow],
) -> list[str]:
    lines = [
        f"### {group_name}",
        "",
        (
            f"This source-review table covers the pinned {group_name} Aeldari datasheets. "
            "Complete Faction Pack datasheets supersede predecessor rows, PDF Rules Updates "
            "modify the pinned predecessor snapshot, and unchanged predecessor rows remain "
            "explicitly reviewed. Every supported or still-needed description is bound to one "
            "exact ability ID, source-text hash, support stage, semantic inventory, runtime "
            "consumer set, and diagnostic set in the generated semantic-description artifact. "
            "`All consumed` means every exact non-core datasheet or wargear ability is consumed "
            "by an engine runtime host. `IR parsed; host needed` means the text compiles to "
            "supported structured IR but at least one semantic lacks a phase or query consumer. "
            "`Unsupported IR` means at least one exact ability has blocking parser diagnostics. "
            "`Bridge/catalog blocked` means source normalization or generated catalog evidence "
            "prevents a safe playability claim."
        ),
        "",
        (
            "| Datasheet | Source basis | IR coverage | Supported semantics | "
            "IR semantics still needed | Bridge / catalog blockers |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda item: (item.datasheet_name.lower(), item.datasheet_id)):
        lines.append(
            "| "
            + " | ".join(
                (
                    f"{_markdown_text(row.datasheet_name)} (`{row.datasheet_id}`)",
                    _markdown_text(_source_basis(row)),
                    _IR_COVERAGE_LABELS[row.semantic_bucket],
                    _ability_descriptions_markdown(
                        row=row,
                        descriptions_by_ability_id=descriptions_by_ability_id,
                        documentation_bucket=DOCUMENTATION_BUCKET_SUPPORTED,
                    ),
                    _ability_descriptions_markdown(
                        row=row,
                        descriptions_by_ability_id=descriptions_by_ability_id,
                        documentation_bucket=DOCUMENTATION_BUCKET_STILL_NEEDED,
                    ),
                    _markdown_text(
                        _catalog_blocker_description(
                            semantic_row=row,
                            support_row=support_rows_by_datasheet_id.get(row.datasheet_id),
                        )
                    ),
                )
            )
            + " |"
        )
    lines.append("")
    return lines


def _ability_descriptions_markdown(
    *,
    row: AeldariDatasheetSemanticCoverage,
    descriptions_by_ability_id: Mapping[str, AeldariAbilitySemanticDescription],
    documentation_bucket: str,
) -> str:
    values: list[str] = []
    for ability in row.abilities:
        description = descriptions_by_ability_id.get(ability.ability_id)
        if description is None:
            raise ValueError("Aeldari exact ability is missing its semantic description.")
        if description.documentation_bucket == documentation_bucket:
            values.append(
                f"{_markdown_text(ability.ability_name)} (`{ability.ability_id}`): "
                f"{_markdown_text(description.description)}"
            )
    if not values:
        return "None."
    return "<br>".join(values)


def _source_basis(row: AeldariDatasheetSemanticCoverage) -> str:
    reference = row.pdf_page_reference
    if row.treatment == "complete_pdf":
        prefix = "Complete Datasheets, physical PDF pages "
        if reference is None or not reference.startswith(prefix):
            raise ValueError(
                "Aeldari complete-PDF source review requires an exact authoritative page range."
            )
        return f"PDF pages {reference.removeprefix(prefix)}; supersedes Wahapedia."
    if row.treatment == "rules_update":
        if reference is None:
            raise ValueError("Aeldari Rules Update source review requires a PDF reference.")
        return f"Pinned Wahapedia predecessor row plus PDF {reference}."
    if row.treatment == "unchanged_predecessor":
        if reference is not None:
            raise ValueError("Unchanged Aeldari predecessor rows must not cite a PDF page.")
        return "Pinned Wahapedia predecessor row; not reprinted or updated in PDF."
    raise ValueError(f"Unsupported Aeldari datasheet source treatment {row.treatment!r}.")


def _catalog_blocker_description(
    *,
    semantic_row: AeldariDatasheetSemanticCoverage,
    support_row: DatasheetSupportRow | None,
) -> str:
    if support_row is None:
        return (
            "No generated DatasheetSupportRow; catalog/model/wargear/geometry playability "
            "remains unproven."
        )
    if (
        support_row.faction_id != "aeldari"
        or support_row.datasheet_id != semantic_row.datasheet_id
        or support_row.datasheet_name != semantic_row.datasheet_name
    ):
        raise ValueError("Aeldari DatasheetSupportRow identity drifted from semantic evidence.")
    failures: list[str] = []
    if support_row.overall not in _ACCEPTED_OVERALL_STATUSES:
        failures.append(f"overall `{support_row.overall}`")
    for label, status in (
        ("catalog", support_row.catalog_status),
        ("models/geometry", support_row.model_geometry_status),
        ("wargear", support_row.wargear_status),
        ("datasheet abilities", support_row.datasheet_ability_status),
    ):
        if status != "Full":
            failures.append(f"{label} `{status}`")
    if support_row.weapon_keyword_status not in _ACCEPTED_WEAPON_KEYWORD_STATUSES:
        failures.append(f"weapon keywords `{support_row.weapon_keyword_status}`")
    host_limitation = _host_limitation(support_row.tests_evidence)
    if failures:
        return (
            "Generated support row blocks an unqualified playability claim: "
            + "; ".join(failures)
            + f". Notes: {support_row.notes} Tests/evidence: {support_row.tests_evidence}"
        )
    if host_limitation is not None:
        return f"Generated playability evidence records a host limitation: {host_limitation}"
    return (
        "No known catalog blocker. Generated row: "
        f"overall `{support_row.overall}`; catalog `{support_row.catalog_status}`; "
        f"models/geometry `{support_row.model_geometry_status}`; "
        f"wargear `{support_row.wargear_status}`; "
        f"weapon keywords `{support_row.weapon_keyword_status}`; "
        f"datasheet abilities `{support_row.datasheet_ability_status}`."
    )


def _host_limitation(tests_evidence: str) -> str | None:
    marker_index = tests_evidence.find(_HOST_LIMITATION_PREFIX)
    if marker_index == -1:
        return None
    return tests_evidence[marker_index + len(_HOST_LIMITATION_PREFIX) :]


def _markdown_text(value: str) -> str:
    return value.replace("|", "\\|")


def _markdown_line_list(values: Iterable[str]) -> str:
    text_values = tuple(values)
    if not text_values:
        return "None"
    return "<br>".join(_markdown_text(value) for value in text_values)
