from __future__ import annotations

from dataclasses import dataclass

AELDARI_FACTION_ID = "aeldari"


@dataclass(frozen=True)
class AeldariDatasheetReviewRow:
    datasheet_id: str
    datasheet: str
    source_basis: str
    semantics_needed: str


@dataclass(frozen=True)
class AeldariDatasheetReviewGroup:
    name: str
    rows: tuple[AeldariDatasheetReviewRow, ...]


_GROUP_DATASHEETS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Craftworlds / Asuryani",
        (
            ("000000568", "Eldrad Ulthran"),
            ("000000571", "Asurmen"),
            ("000000572", "Jain Zar"),
            ("000000574", "Fuegan"),
            ("000000575", "Baharroth"),
            ("000000576", "Maugan Ra"),
            ("000000577", "Autarch"),
            ("000000581", "Avatar of Khaine"),
            ("000000582", "Farseer"),
            ("000000583", "Farseer Skyrunner"),
            ("000000584", "Warlock Conclave"),
            ("000000585", "Warlock"),
            ("000000587", "Warlock Skyrunners"),
            ("000000588", "Spiritseer"),
            ("000000589", "Guardian Defenders"),
            ("000000590", "Storm Guardians"),
            ("000000591", "Windriders"),
            ("000000592", "Rangers"),
            ("000000593", "Dire Avengers"),
            ("000000594", "Howling Banshees"),
            ("000000595", "Striking Scorpions"),
            ("000000596", "Fire Dragons"),
            ("000000597", "Wraithguard"),
            ("000000598", "Wraithblades"),
            ("000000599", "Wave Serpent"),
            ("000000600", "Swooping Hawks"),
            ("000000601", "Warp Spiders"),
            ("000000602", "Shining Spears"),
            ("000000603", "Crimson Hunter"),
            ("000000605", "Vypers"),
            ("000000606", "Hemlock Wraithfighter"),
            ("000000607", "Dark Reapers"),
            ("000000609", "Falcon"),
            ("000000610", "Fire Prism"),
            ("000000611", "Night Spinner"),
            ("000000612", "War Walkers"),
            ("000000613", "Wraithlord"),
            ("000000614", "Wraithknight"),
            ("000002533", "Shroud Runners"),
            ("000002759", "Autarch Wayleaper"),
            ("000003909", "Lhykhis"),
            ("000003910", "D-cannon Platform"),
            ("000003911", "Shadow Weaver Platform"),
            ("000003912", "Vibro Cannon Platform"),
            ("000003913", "Wraithknight with Ghostglaive"),
        ),
    ),
    (
        "Anhrathe / Corsairs",
        (
            ("000002531", "Corsair Voidreavers"),
            ("000002532", "Corsair Voidscarred"),
            ("000004193", "Prince Yriel"),
            ("000004194", "Kharseth"),
            ("000004195", "Starfangs"),
            ("000004196", "Corsair Skyreavers"),
        ),
    ),
    (
        "Harlequins",
        (
            ("000002534", "Troupe Master"),
            ("000002535", "Shadowseer"),
            ("000002536", "Troupe"),
            ("000002537", "Death Jester"),
            ("000002538", "Solitaire"),
            ("000002539", "Skyweavers"),
            ("000002540", "Voidweaver"),
            ("000002541", "Starweaver"),
        ),
    ),
    (
        "Ynnari",
        (
            ("000002542", "Yvraine"),
            ("000002543", "The Visarch"),
            ("000002544", "The Yncarne"),
            ("000003914", "Ynnari Archon"),
            ("000003915", "Ynnari Succubus"),
            ("000003916", "Ynnari Kabalite Warriors"),
            ("000003917", "Ynnari Wyches"),
            ("000003918", "Ynnari Incubi"),
            ("000003919", "Ynnari Reavers"),
            ("000003920", "Ynnari Raider"),
            ("000003921", "Ynnari Venom"),
        ),
    ),
)


_COMPLETE_FACTION_PACK_DATASHEETS: dict[str, tuple[str, str]] = {
    "000000605": (
        "Faction Pack pages 16-17; supersedes the predecessor-edition Vypers row.",
        (
            "Ingest the replacement profiles and Harassment Fire suppressed-target Hit-roll "
            "modifier, then prove its expiry at the start of the Aeldari player's next turn."
        ),
    ),
    "000004193": (
        (
            "Faction Pack pages 12-13; supersedes the excluded predecessor-edition Legends "
            "Prince Yriel row."
        ),
        (
            "Ingest Piratical Hero's led-unit Sustained Hits and Hit-roll modifier plus Prince "
            "of Corsairs post-deployment redeployment and Strategic Reserves choices."
        ),
    ),
    "000004194": (
        "Faction Pack pages 14-15; new current-edition Kharseth datasheet.",
        (
            "Ingest Aethersense reserve-arrival denial and Fury of the Void's post-shoot "
            "riven-target Strength modifier and expiry."
        ),
    ),
    "000004195": (
        "Faction Pack pages 18-19; new current-edition Starfangs datasheet.",
        (
            "Ingest Hallucinogen Grenades as a start-of-opponent-Shooting-phase selection "
            "that grants Stealth to a visible Aeldari Infantry unit."
        ),
    ),
    "000004196": (
        "Faction Pack pages 20-21; new current-edition Corsair Skyreavers datasheet.",
        (
            "Ingest Raid and Run's end-of-Fight D3+3-inch Normal or Fall Back move through "
            "the shared decision path with PathWitness validation."
        ),
    ),
}


_FACTION_PACK_RULE_UPDATES: dict[str, str] = {
    "000000571": "Hand of Asuryan once-per-battle weapon profile and keyword change",
    "000000575": "Cloudstrider turn-end reserves and restricted 6-inch Deep Strike setup",
    "000000582": "Leader attachment list",
    "000000584": "Warlock Conclave keyword and Declare Battle Formations join rule",
    "000000585": "Leader removal and Support addition",
    "000000587": "Warlock Skyrunners keyword, join rule, and Ignores Cover grant",
    "000000592": "Path of the Outcast reactive movement trigger and distance",
    "000000593": "Aspect Shrine Token replacement",
    "000000594": "Aspect Shrine Token replacement",
    "000000595": "Aspect Shrine Token replacement",
    "000000596": "Aspect Shrine Token replacement",
    "000000599": "transport capacity and passenger restrictions",
    "000000600": "Aspect Shrine Token replacement",
    "000000601": "Aspect Shrine Token replacement",
    "000000603": "Frame keyword plus Movement and Objective Control profile change",
    "000000606": "Frame keyword plus Movement and Objective Control profile change",
    "000000607": "Aspect Shrine Token replacement",
    "000000609": "transport capacity and passenger restrictions",
    "000002531": "Battle Focus addition and shuriken-rifle wargear option",
    "000002535": "neuro disruptor wargear option",
    "000002541": "Rapid Embarkation after disembarking from the same transport",
    "000002542": "Herald of Ynnead Fight-phase target and Wound-roll reroll",
    "000003918": "demiklaives single-blade Armour Penetration change",
    "000003921": "Lithe Embarkation and pre-battle unit-splitting transport rule",
}


def aeldari_datasheet_review_groups() -> tuple[AeldariDatasheetReviewGroup, ...]:
    return tuple(
        AeldariDatasheetReviewGroup(
            name=group_name,
            rows=tuple(_review_row(datasheet_id, datasheet) for datasheet_id, datasheet in rows),
        )
        for group_name, rows in _GROUP_DATASHEETS
    )


def aeldari_datasheet_counts() -> tuple[int, int, int]:
    groups = aeldari_datasheet_review_groups()
    total = sum(len(group.rows) for group in groups)
    complete_pdf_rows = len(_COMPLETE_FACTION_PACK_DATASHEETS)
    updated_rows = len(_FACTION_PACK_RULE_UPDATES)
    return total, complete_pdf_rows, updated_rows


def aeldari_datasheet_snapshot_markdown() -> list[str]:
    total, complete_pdf_rows, updated_rows = aeldari_datasheet_counts()
    unchanged_rows = total - complete_pdf_rows - updated_rows
    return [
        "",
        "### Unit Datasheets",
        "",
        "| Review bucket | Count | Source treatment |",
        "| --- | ---: | --- |",
        (
            f"| Complete Faction Pack datasheets | {complete_pdf_rows} | "
            "Faction Pack pages 12-21 are authoritative. |"
        ),
        (
            f"| Faction Pack datasheet updates | {updated_rows} | The predecessor-edition "
            "source row is retained with the Rules Updates datasheet page applied. |"
        ),
        (
            f"| Unchanged current datasheets | {unchanged_rows} | The predecessor-edition "
            "source row is retained because Faction Pack v1.0 does not replace or update it. |"
        ),
        (
            f"| **Current datasheets reviewed** | **{total}** | "
            "Legends and Imperial Armour excluded. |"
        ),
    ]


def aeldari_datasheet_review_markdown() -> list[str]:
    lines = [
        "### Source scope and exclusions",
        "",
        (
            "This review treats the five complete datasheets on Faction Pack pages 12-21 "
            "as authoritative replacements or additions. It applies the datasheet errata on "
            "the Rules Updates datasheet page (physical PDF page 23; contents page 27) to "
            "the matching predecessor-edition source rows. All other current rows use the "
            "pinned Wahapedia predecessor-edition snapshot dated 2026-06-14 because Faction "
            "Pack v1.0 "
            "does not reprint or update them."
        ),
        "",
        (
            "The PDF's Warhammer Legends section begins at physical PDF page 25 (contents "
            "page 29) and is excluded in full. The 25 Aeldari rows marked as Legends in the "
            "pinned source snapshot are also excluded, including the superseded Prince Yriel "
            "(Legendary) and Corsair Skyreaver Band rows. Imperial Armour is outside CORE V2 "
            "scope, so its two titan rows and the contents reference to Imperial Armour pages "
            "22-25 are excluded as well."
        ),
        "",
        (
            "Every row below is source-reviewed but remains `Bridge/catalog blocked`: the "
            "generated catalog/support artifacts currently contain no Aeldari datasheets. "
            "Accordingly, this document makes no datasheet-level semantic-execution claim. "
            "Catalog ingestion, provenance-preserving overlays, representative geometry, "
            "ability IR, runtime consumers, and focused tests remain required before a row can "
            "be reported as playable or fully supported."
        ),
        "",
    ]
    for group in aeldari_datasheet_review_groups():
        lines.extend(_group_markdown(group))
    return lines[:-1]


def _review_row(datasheet_id: str, datasheet: str) -> AeldariDatasheetReviewRow:
    complete_pdf_row = _COMPLETE_FACTION_PACK_DATASHEETS.get(datasheet_id)
    if complete_pdf_row is not None:
        source_basis, semantics_needed = complete_pdf_row
        return AeldariDatasheetReviewRow(
            datasheet_id=datasheet_id,
            datasheet=datasheet,
            source_basis=source_basis,
            semantics_needed=semantics_needed,
        )
    update = _FACTION_PACK_RULE_UPDATES.get(datasheet_id)
    if update is not None:
        return AeldariDatasheetReviewRow(
            datasheet_id=datasheet_id,
            datasheet=datasheet,
            source_basis=(
                "Pinned predecessor-edition source row plus Faction Pack Rules Updates "
                "datasheet "
                f"page (physical PDF page 23; contents page 27): {update}."
            ),
            semantics_needed=(
                "Ingest and consume the updated source shape, then complete the remaining "
                "ability-by-ability semantic review."
            ),
        )
    return AeldariDatasheetReviewRow(
        datasheet_id=datasheet_id,
        datasheet=datasheet,
        source_basis=(
            "Pinned Wahapedia predecessor-edition snapshot (2026-06-14); no datasheet "
            "replacement or update in Faction Pack v1.0."
        ),
        semantics_needed=(
            "Ingest the source row and complete ability-by-ability semantic and geometry review."
        ),
    )


def _group_markdown(group: AeldariDatasheetReviewGroup) -> list[str]:
    lines = [
        f"### {group.name}",
        "",
        (
            "| Datasheet | Source basis | IR coverage | Supported semantics | "
            "IR semantics still needed | Bridge / catalog blockers |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(group.rows, key=lambda item: (item.datasheet.lower(), item.datasheet_id)):
        lines.append(
            "| "
            + " | ".join(
                (
                    f"{row.datasheet} (`{row.datasheet_id}`)",
                    row.source_basis,
                    "Bridge/catalog blocked",
                    "None proven; source review only.",
                    row.semantics_needed,
                    "No generated Aeldari catalog row; geometry and provenance review pending.",
                )
            )
            + " |"
        )
    lines.append("")
    return lines
