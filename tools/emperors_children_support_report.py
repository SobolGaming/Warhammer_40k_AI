from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

EMPERORS_CHILDREN_FACTION_ID = "emperors-children"

_EMPERORS_CHILDREN_GROUP = "Emperor's Children"
_VEHICLES_GROUP = "Vehicles and Daemon Engines"
_SLAANESH_DAEMONS_GROUP = "Slaanesh Daemons"


@dataclass(frozen=True, slots=True)
class EmperorsChildrenDatasheetReviewRow:
    group: str
    datasheet: str
    datasheet_id: str
    ir_coverage: str
    supported_semantics: str
    semantics_needed: str
    catalog_blockers: str


_DATASHEET_GROUP_INTROS = {
    _EMPERORS_CHILDREN_GROUP: (
        "This table covers Emperor's Children characters and infantry from the pinned "
        "predecessor source, with the Faction Pack Rules Updates applied where cited."
    ),
    _VEHICLES_GROUP: (
        "This table covers the Emperor's Children transports, vehicles, daemon engines, and "
        "other non-infantry support units from the pinned predecessor source, plus the complete "
        "Defiler datasheet reprinted in the Faction Pack."
    ),
    _SLAANESH_DAEMONS_GROUP: (
        "This table covers the Slaanesh Daemon datasheets retained by the Emperor's Children "
        "source scope. The Faction Pack does not reprint or update these rows, so the pinned "
        "predecessor rows remain authoritative for this review."
    ),
}

_NO_GENERATED_SUPPORT_ROW = (
    "No generated DatasheetSupportRow; active catalog, model, wargear, geometry, and "
    "playability evidence is not yet proven."
)

_DATASHEET_REVIEW_ROWS = (
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Fulgrim",
        datasheet_id="000004077",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D6, Deep Strike, and the Thrill Seekers army-rule handler are "
            "implemented generic or faction paths. The source overlay applies the updated "
            "Serpentine terrain-transit text."
        ),
        semantics_needed=(
            "Daemonic Poisons persistent target state and Command-phase mortal wounds; Daemon "
            "Primarch mode selection; Beguiling Form hit modifier; Daemonic Speed Fights First; "
            "Enthralling Hypnosis Fall Back test and denial."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Lord Exultant",
        datasheet_id="000004078",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Leader and the Thrill Seekers army-rule handler are implemented paths."
        ),
        semantics_needed=(
            "Perfectionists led-unit Lethal Hits grant; once-per-battle Euphoric Strikes Attacks "
            "and Armour Penetration modifiers; conditional Lord of the Host Infiltrators and "
            "Scouts 6-inch grants."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Tormentors",
        datasheet_id="000004079",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Infiltrators and the Thrill Seekers army-rule handler are implemented paths; the "
            "source overlay applies the updated power sword Strength."
        ),
        semantics_needed=(
            "Objective Defiled sticky-objective control and Icon of Excess end-of-phase "
            "Leadership test and Command point reward."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Infractors",
        datasheet_id="000004080",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Scouts 6 inches and the Thrill Seekers army-rule handler are implemented paths; "
            "the source overlay applies the updated power sword Strength."
        ),
        semantics_needed=(
            "Excessive Assault conditional Wound re-rolls and Icon of Excess end-of-phase "
            "Leadership test and Command point reward."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Chaos Terminators",
        datasheet_id="000004081",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deep Strike and the Thrill Seekers army-rule handler are implemented paths; the "
            "source overlay applies the updated Lethal Obsession text."
        ),
        semantics_needed=(
            "Lethal Obsession must persist the sole shooting target and condition the later "
            "Charge-roll re-roll on declaring against that target."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Lucius the Eternal",
        datasheet_id="000004083",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Feel No Pain 5+, Leader, Lone Operative, and the Thrill Seekers army-rule handler "
            "are implemented paths."
        ),
        semantics_needed=(
            "A Challenge Worthy of Skill keyword-targeted Hit and Wound re-rolls and Duelist's "
            "Hubris conditional Fights First while not leading a unit."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Lord Kakophonist",
        datasheet_id="000004084",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Leader and the Thrill Seekers army-rule handler are implemented paths."
        ),
        semantics_needed=(
            "Obsessive Annunciation ranged Sustained Hits 1 grant and Doom Siren post-shoot "
            "mortal wounds followed by a conditional Battle-shock test."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Sorcerer",
        datasheet_id="000004085",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Leader and the Thrill Seekers army-rule handler are implemented paths."
        ),
        semantics_needed=(
            "Warped Interference ranged-cover grant and Wracking Agonies persisted Move and "
            "Charge-roll penalties on a unit hit by Agonising Energies."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Noise Marines",
        datasheet_id="000004088",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics="The Thrill Seekers army-rule handler is implemented.",
        semantics_needed=(
            "Terrifying Crescendo must persist and stack its Battle-shock and Leadership test "
            "penalty, including the Faction Pack FAQ clarification."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_EMPERORS_CHILDREN_GROUP,
        datasheet="Flawless Blades",
        datasheet_id="000004089",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "The Thrill Seekers army-rule handler is implemented; the source overlay applies "
            "the updated Blissblade Attacks characteristic."
        ),
        semantics_needed=(
            "Daemonic Patrons Critical Wound threshold, phase-scoped state, destroyed-enemy "
            "attribution, and end-of-Fight self-destruction."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_VEHICLES_GROUP,
        datasheet="Chaos Land Raider",
        datasheet_id="000004082",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D6 and the Thrill Seekers army-rule handler are implemented paths; "
            "the source overlay adds the Frame keyword."
        ),
        semantics_needed="Assault Ramp post-Normal-move disembark and Charge eligibility.",
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_VEHICLES_GROUP,
        datasheet="Chaos Rhino",
        datasheet_id="000004093",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D3, Firing Deck 2, and the Thrill Seekers army-rule handler are "
            "implemented paths; the source overlay adds the Frame keyword."
        ),
        semantics_needed=(
            "Assault Vehicle post-Advance disembark, Normal-move treatment, Charge denial, and "
            "remaining action eligibility."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_VEHICLES_GROUP,
        datasheet="Chaos Spawn",
        datasheet_id="000004090",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Feel No Pain 5+ and the Thrill Seekers army-rule handler are implemented paths; "
            "the source overlay applies the updated Scuttling Horrors trigger text."
        ),
        semantics_needed=(
            "Scuttling Horrors once-per-turn enemy-move trigger and PathWitness-backed Normal "
            "move of up to 6 inches."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_VEHICLES_GROUP,
        datasheet="Maulerfiend",
        datasheet_id="000004091",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D3 and the Thrill Seekers army-rule handler are implemented paths."
        ),
        semantics_needed=(
            "Glutton for Punishment Hit modifier below Starting Strength and additional Wound "
            "modifier while Below Half-strength."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_VEHICLES_GROUP,
        datasheet="Heldrake",
        datasheet_id="000004092",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D3, Hover, and the Thrill Seekers army-rule handler are implemented "
            "paths; the overlay applies Movement, Save, Objective Control, and Aircraft-removal "
            "updates."
        ),
        semantics_needed=(
            "Airborne Predator moved-over target detection with PathWitness evidence and its "
            "Fly-sensitive mortal-wound rolls."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_VEHICLES_GROUP,
        datasheet="Defiler",
        datasheet_id="000004208",
        ir_coverage="IR parsed; host needed",
        supported_semantics=(
            "Deadly Demise D6, Revel in Desecration hit modifier, Scuttling Walker movement "
            "transit, and the Thrill Seekers army-rule behavior are implemented."
        ),
        semantics_needed=(
            "Bind the exact Thrill Seekers source ability row to the existing named army-rule "
            "handler so generated evidence no longer reports it as descriptor-only."
        ),
        catalog_blockers=(
            "No known catalog blocker; catalog, model geometry, wargear, and weapon-keyword "
            "evidence are Full in the generated DatasheetSupportRow."
        ),
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Daemon Prince of Slaanesh",
        datasheet_id="000004086",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D3 and the Thrill Seekers army-rule handler are implemented paths."
        ),
        semantics_needed=(
            "Lord of Excess conditional Lone Operative, Excessive Vigour charged-unit melee "
            "Armour Penetration aura, and Ecstatic Death fight-on-death sequencing."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Daemon Prince of Slaanesh with Wings",
        datasheet_id="000004087",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D3, Deep Strike, and the Thrill Seekers army-rule handler are "
            "implemented paths."
        ),
        semantics_needed=(
            "Daemonic Destruction charge-end mortal wounds capped at six and Stimulated by Pain "
            "incoming Damage reduction."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Daemonettes",
        datasheet_id="000004095",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deep Strike, Fights First, Daemonic Icon Leadership, Instrument of Chaos Charge "
            "modifier, and Pact of Excess mustering restrictions are implemented paths."
        ),
        semantics_needed=(
            "Horrifying Beauty Fight-start Battle-shock tests with the Below Half-strength "
            "modifier."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Fiends",
        datasheet_id="000004096",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics="Deep Strike and Pact of Excess mustering restrictions are paths.",
        semantics_needed=(
            "Soporific Musk Fall Back Desperate Escape tests, Monster/Vehicle exclusions, and "
            "the Battle-shocked test modifier."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Keeper of Secrets",
        datasheet_id="000004097",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D6, Deep Strike, hit-roll modifiers, Shining Aegis Save override, and "
            "Pact of Excess mustering restrictions are implemented generic paths."
        ),
        semantics_needed=(
            "Daemon Lord of Slaanesh melee Armour Penetration aura for Legions of Excess units "
            "and exact Mesmerising Form source binding."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Seekers",
        datasheet_id="000004098",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deep Strike, Scouts 9 inches, Daemonic Icon Leadership, Instrument of Chaos Charge "
            "modifier, and Pact of Excess mustering restrictions are implemented paths."
        ),
        semantics_needed="Unholy Speed Advance- and Charge-roll re-roll permissions.",
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
    EmperorsChildrenDatasheetReviewRow(
        group=_SLAANESH_DAEMONS_GROUP,
        datasheet="Shalaxi Helbane",
        datasheet_id="000004094",
        ir_coverage="Bridge/catalog blocked",
        supported_semantics=(
            "Deadly Demise D6, Deep Strike, and Pact of Excess mustering restrictions are "
            "implemented paths."
        ),
        semantics_needed=(
            "No Prey Can Evade Advance and Charge re-rolls and Monarch of the Hunt deterministic "
            "quarry selection, re-rolls, destruction tracking, and reselection."
        ),
        catalog_blockers=_NO_GENERATED_SUPPORT_ROW,
    ),
)

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


def emperors_children_datasheet_support_markdown(
    *,
    review_rows: tuple[tuple[str, str, str, str | None], ...],
    generated_support_datasheet_ids: frozenset[str],
) -> list[str]:
    review_by_id = {row[0]: row for row in review_rows}
    expected_by_id = {row.datasheet_id: row for row in _DATASHEET_REVIEW_ROWS}
    if review_by_id.keys() != expected_by_id.keys():
        raise ValueError(
            "Emperor's Children datasheet semantic review must cover every manifest row exactly."
        )
    if generated_support_datasheet_ids != {"000004208"}:
        raise ValueError(
            "Emperor's Children generated support-row inventory changed; review the custom "
            "datasheet evidence before regenerating documentation."
        )
    for datasheet_id, (_, datasheet_name, _, _) in review_by_id.items():
        if datasheet_name != expected_by_id[datasheet_id].datasheet:
            raise ValueError(
                "Emperor's Children datasheet semantic review name drifted from the manifest."
            )

    lines: list[str] = []
    for group, intro in _DATASHEET_GROUP_INTROS.items():
        lines.extend(
            (
                f"### {group}",
                "",
                (
                    f"{intro} `All consumed` means every known non-core datasheet or wargear "
                    "ability is consumed by an engine runtime host. `IR parsed; host needed` "
                    "means the exact text compiles to structured IR but at least one semantic "
                    "lacks a phase or query consumer. `Unsupported IR` means at least one exact "
                    "ability has blocking parser diagnostics. `Bridge/catalog blocked` means "
                    "source normalization or generated catalog evidence prevents a safe "
                    "playability claim."
                ),
                "",
                (
                    "| Datasheet | Source basis | IR coverage | Supported semantics | "
                    "IR semantics still needed | Bridge / catalog blockers |"
                ),
                "| --- | --- | --- | --- | --- | --- |",
            )
        )
        for row in sorted(
            (review_row for review_row in _DATASHEET_REVIEW_ROWS if review_row.group == group),
            key=lambda review_row: (review_row.datasheet.lower(), review_row.datasheet_id),
        ):
            _, _, treatment, pdf_page_reference = review_by_id[row.datasheet_id]
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"{_markdown_text(row.datasheet)} (`{row.datasheet_id}`)",
                        _markdown_text(
                            _datasheet_source_basis(
                                treatment=treatment,
                                pdf_page_reference=pdf_page_reference,
                            )
                        ),
                        _markdown_text(row.ir_coverage),
                        _markdown_text(row.supported_semantics),
                        _markdown_text(row.semantics_needed),
                        _markdown_text(row.catalog_blockers),
                    )
                )
                + " |"
            )
        lines.append("")
    return lines[:-1]


def _datasheet_source_basis(*, treatment: str, pdf_page_reference: str | None) -> str:
    if treatment == "complete_pdf":
        expected = "Complete Datasheet, physical PDF pages 7-8"
        if pdf_page_reference != expected:
            raise ValueError("Emperor's Children complete datasheet page reference drifted.")
        return "PDF pages 7-8; supersedes the pinned predecessor row."
    if treatment == "rules_update":
        expected = "Rules Updates, physical PDF page 9"
        if pdf_page_reference != expected:
            raise ValueError("Emperor's Children Rules Update page reference drifted.")
        return "Pinned predecessor row plus PDF Rules Updates, physical page 9."
    if treatment == "unchanged_predecessor":
        if pdf_page_reference is not None:
            raise ValueError("Unchanged Emperor's Children rows must not cite a PDF page.")
        return "Pinned predecessor row; not reprinted or updated in the PDF."
    raise ValueError(f"Unsupported Emperor's Children datasheet source treatment {treatment!r}.")


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
