from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
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

from warhammer40k_core.engine.ability_coverage import AbilityCoverageSupportStage

_IR_COVERAGE_LABELS = {
    SEMANTIC_BUCKET_ALL_CONSUMED: "All consumed",
    SEMANTIC_BUCKET_HOST_NEEDED: "IR parsed; host needed",
    SEMANTIC_BUCKET_UNSUPPORTED_IR: "Unsupported IR",
    SEMANTIC_BUCKET_BRIDGE_BLOCKED: "Bridge/catalog blocked",
}

_COMPLETE_PDF_PAGE_RANGES = {
    "000004193": "12-13",
    "000004194": "14-15",
    "000000605": "16-17",
    "000004195": "18-19",
    "000004196": "20-21",
}

_SUPPORTED_SEMANTICS_BY_DATASHEET_ID = {
    "000000568": (
        "Diviner of Futures Command-phase CP gain is consumed. Doom's visible-enemy "
        "selection and friendly Aeldari wound-roll modifier compile to structured IR."
    ),
    "000000572": (
        "Storm of Silence Character-target wound rerolls and Whirling Death's fixed Advance "
        "distance and vertical-distance exception are consumed."
    ),
    "000000574": (
        "Burning Lance's led-unit Melta range modifier and Unquenchable Resolve's first-death "
        "return at full wounds are consumed."
    ),
    "000000577": (
        "Aspect Training's leader-conditioned ability grants, Path of Command's Stratagem-cost "
        "reduction, and Superlative Strategist's Advance and Agile Manoeuvre rerolls are consumed."
    ),
    "000000585": (
        "Runes of Fortune's charge-declaration reaction and Charge-roll modifier compile to "
        "structured IR."
    ),
    "000000587": "Runes of Battle's unit-wide Ignores Cover weapon grant is consumed.",
    "000000588": (
        "Spirit Mark's selected Wraith target and Sustained Hits grant, Spiritseer's conditional "
        "Lone Operative, and Tears of Isha healing or model return are consumed."
    ),
    "000000592": (
        "Path of the Outcast's optional D6-inch reactive Normal move is consumed through the "
        "shared movement proposal and PathWitness path."
    ),
    "000000593": "Aspect Shrine Token's once-per-battle Hit or Wound result override is consumed.",
    "000000594": (
        "Acrobatic's charge-after-Advance-or-Fall-Back eligibility and Aspect Shrine Token's "
        "Hit or Wound result override are consumed."
    ),
    "000000595": (
        "Mandiblasters' charge-conditioned Critical Hit threshold and Aspect Shrine Token's "
        "Hit or Wound result override are consumed."
    ),
    "000000596": (
        "Assured Destruction's Monster/Vehicle Hit, Wound, and Damage rerolls and Aspect Shrine "
        "Token's Hit or Wound result override are consumed."
    ),
    "000000597": (
        "Psychic Guidance's nearby-Psyker Leadership and Hit modifiers and War Construct's "
        "shoot-after-Fall-Back eligibility are consumed."
    ),
    "000000598": (
        "Malevolent Souls fight-on-death, Psychic Guidance's Leadership and Hit modifiers, and "
        "Forceshield's invulnerable save are consumed."
    ),
    "000000599": (
        "Wave Serpent Shield's Strength-versus-Toughness predicate and defensive Wound-roll "
        "modifier compile to structured IR."
    ),
    "000000600": (
        "Grenade Pack Flyover's setup/move-completed mortal wounds and Grenade restriction, plus "
        "Aspect Shrine Token's Hit or Wound result override, are consumed."
    ),
    "000000601": (
        "Flickerjump's movement-action choice, fixed Move, charge restriction, and mortal wounds, "
        "plus Aspect Shrine Token's result override, are consumed."
    ),
    "000000603": (
        "Skyhunter's Fly target predicate and ranged Hit- and Wound-roll modifiers compile to "
        "structured IR."
    ),
    "000000605": (
        "Harassment Fire's post-shoot hit-target tracking and suppressed-unit Hit-roll modifier "
        "are consumed."
    ),
    "000000607": (
        "Inescapable Accuracy's Ballistic Skill and Hit-modifier ignore semantics compile to "
        "structured IR; Aspect Shrine Token's result override is consumed."
    ),
    "000000609": (
        "Fire Support's post-shoot target tracking, same-transport disembark predicate, and "
        "Wound-roll reroll compile to structured IR."
    ),
    "000000611": (
        "Monofilament Web's post-hit pinned state and Move and Charge modifiers are consumed."
    ),
    "000000612": (
        "Crystalline Targeting's post-shoot target tracking and friendly Aeldari Armour "
        "Penetration modifier are consumed."
    ),
    "000000613": (
        "Fated Hero's battle-start keyword choice and target-conditioned Hit/Wound rerolls, plus "
        "Psychic Guidance's nearby-Psyker skill and Leadership modifiers, are consumed."
    ),
    "000002531": (
        "Reavers of the Void's objective-conditioned Hit rerolls and Mistshield's invulnerable "
        "save are consumed."
    ),
    "000002532": (
        "Piratical Raiders' tracked quarry and Lethal Hits/Precision grants, Channeller Stones' "
        "first-failed-save damage replacement, Faolchu's Ignores Cover grant, and Mistshield are "
        "consumed."
    ),
    "000002533": (
        "Target Acquisition's post-shoot long-rifle hit tracking and Benefit of Cover denial "
        "are consumed."
    ),
    "000002534": (
        "Cegorach's Favour's melee Hit-roll reroll and Wound-roll modifier compile to "
        "structured IR."
    ),
    "000002538": (
        "Blur of Movement's charge-after-Advance eligibility compiles to structured IR, and Path "
        "of Damnation's Warlord restriction is consumed."
    ),
    "000002539": "Acrobatic Grace's incoming-attack Hit-roll modifier compiles to structured IR.",
    "000002542": (
        "Herald of Ynnead's Fight-phase enemy selection and friendly Aeldari Wound-roll reroll "
        "compile to structured IR."
    ),
    "000002759": (
        "Indomitable Strength of Will's Battle Focus token refund and Path of Command's "
        "Stratagem-cost reduction are consumed."
    ),
    "000003909": (
        "Empyric Ambush's Flickerjump charge eligibility and Whispering Web's post-shoot tracked "
        "target and Critical Hit threshold are consumed."
    ),
    "000003914": "Reborn Mastermind's once-per-round Stratagem-cost reduction is consumed.",
    "000003915": "Storm of Blades' led-unit melee Sustained Hits 1 grant is consumed.",
    "000004193": (
        "Piratical Hero's led-unit Sustained Hits and Hit modifier and Prince of Corsairs' "
        "post-deployment redeploy/Strategic Reserves permission are consumed."
    ),
    "000004194": (
        "Aethersense's reserve-arrival exclusion and Fury of the Void's post-shoot riven target "
        "and friendly Aeldari Strength modifier are consumed."
    ),
    "000004195": (
        "Hallucinogen Grenades' opponent-Shooting-phase friendly Infantry selection and temporary "
        "Stealth grant are consumed."
    ),
    "000004196": (
        "Raid and Run's Fight-end eligibility split and D3+3-inch Normal/Fall Back movement are "
        "consumed through the shared triggered-movement path."
    ),
}

_SEMANTICS_NEEDED_BY_DATASHEET_ID = {
    "000000568": (
        "A Movement-phase-end visible enemy selection host, persistence through the next Command "
        "phase, and the friendly Aeldari +1 Wound query for Doom."
    ),
    "000000571": (
        "A once-per-battle named-weapon Damage/Anti-Infantry/Devastating Wounds grant; and a "
        "post-shoot 6-inch Normal move for a led unit with a turn-long charge restriction."
    ),
    "000000575": (
        "End-of-opponent-turn return to Strategic Reserves; 6-inch Deep Strike with a charge "
        "restriction; and a setup-this-turn all-successful-Hits-are-Critical modifier."
    ),
    "000000576": (
        "Post-shoot forced Battle-shock with a -1 test modifier; and single-target attack "
        "declaration followed by 3-inch splash D3 mortal wounds on 5+ after the attacks resolve."
    ),
    "000000581": (
        "Allocated-attack Damage halving; and a 6-inch friendly Aeldari aura that adds 1 to "
        "Advance and Charge rolls."
    ),
    "000000582": (
        "A once-per-phase led-unit Hit/Wound/Damage result override to an unmodified 6 with a "
        "Support Weapon exclusion; and a visible tracked enemy granting friendly Aeldari +1 Hit."
    ),
    "000000583": (
        "A once-per-phase led-unit Hit/Wound/Damage result override to an unmodified 6; and a "
        "visible tracked enemy whose attacks suffer -1 to Wound."
    ),
    "000000584": (
        "A Farseer-leading defensive Wound-roll modifier; and per-model nearby-Psyker counting "
        "that scales Destructor Attacks and Strength to a +2 cap."
    ),
    "000000585": (
        "A selected-to-shoot nearby-Psyker count that scales this model's Destructor Attacks and "
        "Strength to a +2 cap."
    ),
    "000000587": (
        "Per-model selected-to-shoot nearby-Psyker counting that scales each Destructor's Attacks "
        "and Strength to a +2 cap."
    ),
    "000000589": (
        "Dependent-platform destruction when the last Guardian dies; and a no-token, extra-use "
        "Fade Back permission that bypasses the normal once-per-phase Battle Focus limit."
    ),
    "000000590": (
        "Dependent Serpent's Scale Platform destruction, sticky objective control, and a "
        "bearer-unit 5+ invulnerable save grant."
    ),
    "000000591": (
        "Ranged Hit-roll rerolls of 1, upgraded to full Hit rerolls when the target is the closest "
        "eligible target."
    ),
    "000000593": (
        "A half-range predicate granting ranged Sustained Hits 1, plus a bearer-only 4+ "
        "invulnerable save."
    ),
    "000000599": (
        "A ranged-target query host for Strength greater than Toughness and the resulting -1 "
        "Wound-roll modifier."
    ),
    "000000602": (
        "Vertical-distance-free Normal, Advance, Fall Back, and Charge movement with PathWitness "
        "validation, plus a bearer-only 4+ invulnerable save."
    ),
    "000000603": (
        "A ranged attack modifier host that checks the target's Fly capability and applies +1 Hit "
        "and +1 Wound."
    ),
    "000000606": (
        "A 9-inch enemy aura that subtracts 1 from both Battle-shock and Leadership tests."
    ),
    "000000607": (
        "An attack-sequence query host that ignores selected Ballistic Skill and Hit-roll "
        "modifiers."
    ),
    "000000609": (
        "Post-shoot hit-target tracking tied to models that disembarked from this Transport this "
        "turn, with Wound rerolls that persist through the end of the turn."
    ),
    "000000610": (
        "One Hit and one Wound reroll per shooting activation; and Linked Fire range/visibility "
        "origin substitution through another visible Fire Prism with Attacks fixed to 1."
    ),
    "000000614": (
        "Half-range attack-count rerolls for named weapons; model/terrain transit with "
        "PathWitness, Engagement Range constraints, and a Battle-shock risk after tall terrain; "
        "plus a 4+ invulnerable save and allocated-attack Damage reduction."
    ),
    "000002534": (
        "Six-inch Pile-in/Consolidation movement with closest-unit rather than closest-model "
        "constraints; a one-model army cap; and vertical-distance-free movement for the bearer."
    ),
    "000002535": (
        "An 18-inch ranged target restriction for the led unit, a one-model army cap, Hazardous "
        "grants to enemy melee weapons, and vertical-distance-free bearer movement."
    ),
    "000002536": (
        "A Fight-phase-start finite choice among Hit rerolls, +1 Wound, or defensive -1 Hit, plus "
        "vertical-distance-free bearer movement."
    ),
    "000002537": (
        "A selected-to-shoot choice among Ignores Cover, Precision, or Sustained Hits 3; "
        "post-shoot Battle-shock with a destroyed-model modifier; a one-model army cap; and Flip "
        "Belt movement."
    ),
    "000002538": (
        "A once-per-battle pre-move 2D6-inch Move and +3 Attacks modifier through the end of the "
        "turn, plus vertical-distance-free bearer movement."
    ),
    "000002539": "An incoming-attack query host for Acrobatic Grace's -1 Hit modifier.",
    "000002540": "An 18-inch ranged target restriction for Polychromatic Camouflage.",
    "000002541": (
        "Fight-end conditional Transport embarkation, including same-turn re-embarkation after "
        "disembarking, with capacity, unit-shape, distance, and Engagement Range validation."
    ),
    "000002542": (
        "Yvraine/Epic Hero mutual-exclusion mustering; and Command-phase D3+1 Bodyguard model "
        "returns on 2+, excluding Support Weapon models."
    ),
    "000002543": (
        "Visarch/Epic Hero mutual-exclusion mustering, a led-unit Fights First grant, and Feel No "
        "Pain 4+ for other attached Character models."
    ),
    "000002544": (
        "Yncarne/Epic Hero mutual-exclusion mustering, D3 lost-wound restoration after destroying "
        "a unit, and once-per-opponent-turn teleport setup at a destroyed friendly unit's location."
    ),
    "000003910": (
        "Damage rerolls of 1 upgraded to full rerolls against Titanic targets; Support Artillery "
        "prebattle joining/Starting Strength/Transport restrictions; and conditional Toughness 3."
    ),
    "000003911": (
        "A persistent snared target with per-model mortal wounds on later Normal/Advance/Fall Back "
        "moves; Support Artillery joining restrictions; and conditional Toughness 3."
    ),
    "000003912": (
        "Same-phase allied Vibro Cannon target counting that scales Strength, AP, and Damage; "
        "Support Artillery joining restrictions; and conditional Toughness 3."
    ),
    "000003913": (
        "Model/terrain transit with PathWitness and Engagement Range endpoint constraints, plus a "
        "4+ invulnerable save and allocated-attack Damage reduction."
    ),
    "000003914": (
        "Led-unit Wound rerolls of 1 upgraded to full rerolls below Starting Strength; and a "
        "Shadow Field state that forbids save rerolls and permanently removes the save after its "
        "first fail."
    ),
    "000003915": (
        "A Fight-phase-start below-Starting-Strength predicate that grants the unit Fights First."
    ),
    "000003916": (
        "Sticky objective control while the unit or its Transport is in range, plus a "
        "wargear-based Grenades keyword grant."
    ),
    "000003917": (
        "Forced Desperate Escape tests when eligible nearby enemies Fall Back, with a "
        "Battle-shocked test modifier and Monster/Vehicle exclusions."
    ),
    "000003918": (
        "Fight-phase-start forced Battle-shock tests for every enemy unit in Engagement Range."
    ),
    "000003919": (
        "PathWitness-backed moved-over enemy selection and per-model mortal wounds, "
        "bearer-specific rerolls for those dice, and a bearer melee Lance grant."
    ),
    "000003920": "A fixed 6-inch Advance modifier that replaces the Advance roll.",
    "000003921": (
        "Fight-end conditional Transport embarkation, including same-turn re-embarkation after "
        "disembarking, with Ynnari unit-shape, capacity, distance, and Engagement Range validation."
    ),
}

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
    generated_datasheet_ids: frozenset[str],
    leader_attachment_evidence_datasheet_ids: frozenset[str],
) -> list[str]:
    coverage = aeldari_datasheet_semantic_coverage()
    _validate_description_coverage(coverage.rows)
    reviewed_ids = {row.datasheet_id for row in coverage.rows}
    unknown_generated_ids = generated_datasheet_ids - reviewed_ids
    if unknown_generated_ids:
        raise ValueError(
            "Aeldari generated datasheet support rows are absent from the exact semantic review."
        )
    lines: list[str] = []
    group_names = tuple(dict.fromkeys(row.group for row in coverage.rows))
    for group_name in group_names:
        lines.extend(
            _group_markdown(
                group_name=group_name,
                rows=tuple(row for row in coverage.rows if row.group == group_name),
                generated_datasheet_ids=generated_datasheet_ids,
                leader_attachment_evidence_datasheet_ids=(leader_attachment_evidence_datasheet_ids),
            )
        )
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _group_markdown(
    *,
    group_name: str,
    rows: tuple[AeldariDatasheetSemanticCoverage, ...],
    generated_datasheet_ids: frozenset[str],
    leader_attachment_evidence_datasheet_ids: frozenset[str],
) -> list[str]:
    lines = [
        f"### {group_name}",
        "",
        (
            f"This source-review table covers the pinned {group_name} Aeldari datasheets. "
            "Complete Faction Pack datasheets supersede predecessor rows, PDF Rules Updates "
            "modify the pinned predecessor snapshot, and unchanged predecessor rows remain "
            "explicitly reviewed. `All consumed` means every exact non-core datasheet or wargear "
            "ability is consumed by an engine runtime host. `IR parsed; host needed` means the "
            "text compiles to supported structured IR but at least one semantic lacks a phase or "
            "query consumer. `Unsupported IR` means at least one exact ability has blocking parser "
            "diagnostics. `Bridge/catalog blocked` means source normalization or generated catalog "
            "evidence prevents a safe playability claim."
        ),
        "",
        (
            "| Datasheet | Source basis | IR coverage | Supported semantics | "
            "IR semantics still needed | Bridge / catalog blockers |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda item: (item.datasheet_name.lower(), item.datasheet_id)):
        supported_semantics = _SUPPORTED_SEMANTICS_BY_DATASHEET_ID.get(
            row.datasheet_id,
            "No non-core datasheet or wargear semantics are currently consumed.",
        )
        if row.datasheet_id in leader_attachment_evidence_datasheet_ids:
            supported_semantics = (
                supported_semantics.rstrip(".")
                + ". Source-backed Leader attachment targets are consumed by generic army "
                "mustering."
            )
        semantics_needed = _SEMANTICS_NEEDED_BY_DATASHEET_ID.get(row.datasheet_id, "None.")
        catalog_blockers = (
            "No known catalog blocker."
            if row.datasheet_id in generated_datasheet_ids
            else (
                "No generated DatasheetSupportRow; catalog/model/wargear/geometry playability "
                "remains unproven."
            )
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    f"{_markdown_text(row.datasheet_name)} (`{row.datasheet_id}`)",
                    _markdown_text(_source_basis(row)),
                    _IR_COVERAGE_LABELS[row.semantic_bucket],
                    _markdown_text(supported_semantics),
                    _markdown_text(semantics_needed),
                    _markdown_text(catalog_blockers),
                )
            )
            + " |"
        )
    lines.append("")
    return lines


def _source_basis(row: AeldariDatasheetSemanticCoverage) -> str:
    if row.treatment == "complete_pdf":
        page_range = _COMPLETE_PDF_PAGE_RANGES.get(row.datasheet_id)
        if page_range is None:
            raise ValueError("Aeldari complete-PDF datasheet is missing an exact page range.")
        return f"PDF pages {page_range}; supersedes Wahapedia."
    if row.treatment == "rules_update":
        return (
            "Pinned Wahapedia predecessor row plus PDF Rules Update, physical page 23 "
            "(contents page 27)."
        )
    if row.treatment == "unchanged_predecessor":
        return "Pinned Wahapedia predecessor row; not reprinted or updated in PDF."
    raise ValueError(f"Unsupported Aeldari datasheet source treatment {row.treatment!r}.")


def _validate_description_coverage(
    rows: tuple[AeldariDatasheetSemanticCoverage, ...],
) -> None:
    supported_stages = frozenset(
        {
            AbilityCoverageSupportStage.ENGINE_CONSUMED,
            AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE,
        }
    )
    expected_supported_ids = {
        row.datasheet_id
        for row in rows
        if any(ability.support_stage in supported_stages for ability in row.abilities)
    }
    if set(_SUPPORTED_SEMANTICS_BY_DATASHEET_ID) != expected_supported_ids:
        raise ValueError("Aeldari supported-semantic descriptions drifted from exact evidence.")
    expected_needed_ids = {
        row.datasheet_id for row in rows if row.semantic_bucket != SEMANTIC_BUCKET_ALL_CONSUMED
    }
    if set(_SEMANTICS_NEEDED_BY_DATASHEET_ID) != expected_needed_ids:
        raise ValueError("Aeldari missing-semantic descriptions drifted from exact evidence.")
    complete_pdf_ids = {row.datasheet_id for row in rows if row.treatment == "complete_pdf"}
    if set(_COMPLETE_PDF_PAGE_RANGES) != complete_pdf_ids:
        raise ValueError("Aeldari complete-PDF page ranges drifted from source treatments.")


def _markdown_text(value: str) -> str:
    return value.replace("|", "\\|")


def _markdown_line_list(values: Iterable[str]) -> str:
    text_values = tuple(values)
    if not text_values:
        return "None"
    return "<br>".join(_markdown_text(value) for value in text_values)
