from __future__ import annotations

from collections.abc import Iterable

EMPERORS_CHILDREN_FACTION_ID = "emperors-children"

_DETACHMENT_PDF_REFERENCE_BY_ID = {
    "elegant-brutes": "Physical PDF page 2",
    "frenzied-host": "Physical PDF page 3",
    "spectacle-of-slaughter": "Physical PDF page 4",
    "court-of-the-phoenician": "Physical PDF pages 5-6",
}

_DETACHMENT_CONTENT_BY_ID = {
    "elegant-brutes": (
        ("Eager to Kill",),
        ("Cacophonic Accompaniment", "Frenzied Ferocity Upgrade"),
        ("Delight in Agony", "Psychedelic Soulflame", "Warp Plunge"),
    ),
    "frenzied-host": (
        ("Frantic Focus",),
        ("Euphoric Crown", "Howling Plate"),
        ("Possessive Mania", "Agonised Cacophony", "Absolute Sensory Overload"),
    ),
    "spectacle-of-slaughter": (
        ("Entitled to Victory",),
        ("Eager Patrons Upgrade", "Beguiling Grotesquerie Upgrade"),
        ("Honour Is for Fools", "Single-minded Strike", "Intoxicated by Triumph"),
    ),
    "court-of-the-phoenician": (
        ("Sensational Performance", "Master of the Pageant"),
        ("Tears of the Phoenix", "Exalted Patron", "Soulstain Made Manifest", "Spiritsliver"),
        (
            "Contemptuous Disregard",
            "Prideful Superiority",
            "Sinuous Breach",
            "Close-quarters Excruciation",
            "Euphoric Inspiration",
            "Catalytic Stimulus",
        ),
    ),
}

_DETACHMENT_SEMANTICS_NEEDED_BY_ID = {
    "carnival-of-excess": (
        "IR still needed: Legions of Excess mustering limits, reciprocal six-inch Empowered "
        "states, Sustained Hits 1 grants, and the upgraded Critical Hit threshold for weapons "
        "that already have Sustained Hits."
    ),
    "coterie-of-the-conceited": (
        "IR still needed: battle-round pledge selection, a replay-safe Pact point ledger, failed-"
        "pledge mortal wounds, and the cumulative Hit, Wound, weapon-keyword, and Critical Hit "
        "threshold bonuses."
    ),
    "elegant-brutes": (
        "IR still needed: a setup-completion hook that gives the arriving Emperor's Children "
        "Terminator unit +1 to Charge rolls until the end of the turn."
    ),
    "frenzied-host": (
        "IR still needed: Battleline Advance/Fall Back selection must grant +1 Strength to the "
        "unit's attacks until turn end, and mustering must enforce the exclusive HOST tag."
    ),
    "mercurial-host": (
        "IR still needed: Emperor's Children units require army-wide Advance-roll rerolls."
    ),
    "peerless-bladesmen": (
        "IR still needed: after charging, a unit selected to fight must choose between Lethal Hits "
        "and Sustained Hits 1 for its melee weapons while resolving those attacks."
    ),
    "rapid-evisceration": (
        "IR still needed: Transport models and models that disembarked this turn must reroll Hit "
        "rolls of 1 and Wound rolls of 1, using the Faction Pack's updated Mechanised Murder text."
    ),
    "slaaneshs-chosen": (
        "IR still needed: Character movement-modifier immunity, deterministic Favoured Champions "
        "ownership transfers after destruction, and Favoured Champions Wound-roll rerolls."
    ),
}

_RULES_UPDATE_ROWS = (
    (
        "Detachment",
        "Carnival of Excess - Empyric Suffusion",
        "Heroic Intervention targeting the bearer's unit costs 1CP less.",
    ),
    (
        "Detachment",
        "Coterie of the Conceited - Armour of Abhorrence",
        "Worsen incoming Armour Penetration by 1 until the attacking unit finishes its attacks.",
    ),
    (
        "Detachment",
        "Mercurial Host - Dark Vigour",
        "The Stratagem's target range changes from 9 inches to 8 inches.",
    ),
    (
        "Detachment",
        "Peerless Bladesmen - Faultless Opportunist",
        "Heroic Intervention can be reused on the bearer's unit, costs 1CP less, and does not "
        "block other uses that phase.",
    ),
    (
        "Detachment",
        "Rapid Evisceration - On to the Next",
        "At the end of the Fight phase, a unit that destroyed an enemy can embark in an eligible "
        "friendly Transport.",
    ),
    (
        "Detachment",
        "Rapid Evisceration - Mechanised Murder",
        "Transport models and models that disembarked this turn reroll Hit rolls of 1 and Wound "
        "rolls of 1.",
    ),
    (
        "Detachment",
        "Slaanesh's Chosen - Vengeful Surge",
        "The unit makes a D6-inch surge move; non-Favoured Champions can reroll the distance.",
    ),
    (
        "Detachment",
        "Slaanesh's Chosen - Refusal to be Outdone",
        "A nearby Character that declares a charge rerolls the Charge roll and must finish engaged "
        "with one of the specified enemy units.",
    ),
    (
        "Datasheet",
        "Chaos Spawn - Scuttling Horrors",
        "After an enemy ends a move within 8 inches, an unengaged unit can make a Normal move of "
        "up to 6 inches.",
    ),
    (
        "Datasheet",
        "Chaos Terminators - Lethal Obsession",
        "After shooting, track a hit enemy for a charge reroll that must finish engaged with that "
        "enemy.",
    ),
    (
        "Datasheet",
        "Flawless Blades - Blissblade",
        "The weapon's Attacks characteristic changes to 4.",
    ),
    (
        "Datasheet",
        "Fulgrim - Serpentine",
        "Normal, Advance, and Fall Back moves can cross terrain sections up to 4 inches high.",
    ),
    (
        "Datasheet",
        "Heldrake",
        "Movement becomes 12 inches, Save becomes 3+, Objective Control becomes '-', and the "
        "Aircraft keyword is removed.",
    ),
    (
        "Datasheet",
        "Infractors and Tormentors - power sword",
        "The weapon's Strength characteristic changes to 5.",
    ),
    (
        "Datasheet",
        "Chaos Land Raider and Chaos Rhino",
        "Both datasheets gain the Frame keyword.",
    ),
)

_FAQ_ROWS = (
    (
        "Coterie of the Conceited",
        "Unbound Arrogance can be used while the Warlord is off the battlefield; the pledge rises "
        "from 0 to 1.",
    ),
    (
        "Noise Marines",
        "Terrifying Crescendo can affect the same enemy unit more than once, so its test modifiers "
        "stack.",
    ),
    (
        "Carnival of Excess",
        "Daemonic Empowerment makes an unmodified Hit roll of 5+ a Critical Hit even when the "
        "weapon already has a higher Sustained Hits value.",
    ),
)


def emperors_children_faction_pack_review_markdown(
    *,
    detachment_rows: tuple[tuple[str, str, str, int, bool, bool], ...],
) -> list[str]:
    lines = [
        "",
        "## 11th Edition Faction Pack Review",
        "",
        (
            "Faction Pack version 1.0 is legal for matched play from 20 June 2026. It is the "
            "authoritative source for the additions and changes summarized here; unchanged "
            "datasheets continue to use the pinned predecessor snapshot identified in the source "
            "review below."
        ),
        "",
        "### Detachments in the Faction Pack",
        "",
        (
            "The 11th-edition source catalog marks Elegant Brutes, Frenzied Host, and Spectacle "
            "of Slaughter as new. The pack also reprints Court of the Phoenician with its complete "
            "detachment rule, Enhancements, and Stratagems."
        ),
        "",
        (
            "| Detachment | New for 11th | PDF reference | Force Disposition | Detachment points | "
            "Rules | Enhancements | Stratagems | Semantic execution |"
        ),
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    rows_by_id = {row[0]: row for row in detachment_rows}
    for detachment_id in _DETACHMENT_PDF_REFERENCE_BY_ID:
        source_row = rows_by_id.get(detachment_id)
        if source_row is None:
            raise ValueError(
                "Emperor's Children Faction Pack detachment review is missing a source row."
            )
        _, name, force_disposition, points, is_new, supported = source_row
        rules, enhancements, stratagems = _DETACHMENT_CONTENT_BY_ID[detachment_id]
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(name),
                    "Yes" if is_new else "No - reprinted/updated",
                    _DETACHMENT_PDF_REFERENCE_BY_ID[detachment_id],
                    f"`{_markdown_text(force_disposition)}`",
                    str(points),
                    _markdown_line_list(rules),
                    _markdown_line_list(enhancements),
                    _markdown_line_list(stratagems),
                    "Full" if supported else "Still needs semantic support",
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            (
                "The generated exact-row counts and semantic tables below include Court of the "
                "Phoenician and Spectacle of Slaughter. Elegant Brutes and Frenzied Host are "
                "source-reviewed from the PDF above, but their Enhancement and Stratagem rows "
                "are not yet present in the structured Phase17E artifacts; listing them here "
                "makes no catalog-load or semantic-execution claim."
            ),
        )
    )
    lines.extend(
        (
            "",
            "### Rules Updates",
            "",
            (
                "Physical PDF page 9 carries forward the following predecessor-to-11th-edition "
                "changes. The summaries identify the effective rule shape without making a "
                "separate engine-support claim."
            ),
            "",
            "| Scope | Rule or profile | Effective update |",
            "| --- | --- | --- |",
        )
    )
    for scope, subject, summary in _RULES_UPDATE_ROWS:
        lines.append(
            f"| {_markdown_text(scope)} | {_markdown_text(subject)} | {_markdown_text(summary)} |"
        )
    lines.extend(
        (
            "",
            "### FAQ Clarifications",
            "",
            "Physical PDF page 10 records three interaction clarifications.",
            "",
            "| Subject | Clarification |",
            "| --- | --- |",
        )
    )
    for subject, clarification in _FAQ_ROWS:
        lines.append(f"| {_markdown_text(subject)} | {_markdown_text(clarification)} |")
    return lines


def emperors_children_semantic_snapshot_markdown(
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
            "Detachment-rule support uses the gameplay support table below. Exact Enhancement "
            "and Stratagem support uses shared Phase17F execution evidence, including executable "
            "generic RuleIR. Datasheet source treatment and playability remain separate sections."
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
    return lines


def emperors_children_detachment_semantics_needed(detachment_id: str) -> str:
    description = _DETACHMENT_SEMANTICS_NEEDED_BY_ID.get(detachment_id)
    if description is None:
        raise ValueError(
            "Unsupported Emperor's Children detachment is missing an IR-semantics-needed "
            "description."
        )
    return description


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


def _markdown_line_list(values: Iterable[str]) -> str:
    rendered = tuple(_markdown_text(value) for value in values)
    return "<br>".join(rendered) if rendered else "None"


def _markdown_text(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
