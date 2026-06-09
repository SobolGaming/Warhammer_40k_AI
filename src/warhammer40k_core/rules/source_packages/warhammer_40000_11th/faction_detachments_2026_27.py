from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from warhammer40k_core.rules.text_normalization import (
    TextNormalizationError,
    normalize_rule_text,
)

SOURCE_PACKAGE_ID = "gw-11e-faction-detachments-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Faction Detachments 2026-27"
SOURCE_VERSION = "2026-27"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-faction-detachment-source-v1"


class FactionDetachmentSourceError(ValueError):
    """Raised when faction detachment source data violates CORE V2 invariants."""


_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_IDENTIFIER_TEXT_RE = re.compile(r"[^a-z0-9]+")
_VALID_FORCE_DISPOSITION_IDS = frozenset(
    {
        "disruption",
        "priority-assets",
        "purge-the-foe",
        "reconnaissance",
        "take-and-hold",
    }
)


@dataclass(frozen=True, slots=True)
class SourceFactionRow:
    faction_id: str
    raw_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "faction_id",
            _validate_identifier("SourceFactionRow faction_id", self.faction_id),
        )
        _normalize_source_label("SourceFactionRow raw_name", self.raw_name)

    @property
    def name(self) -> str:
        return _normalize_source_label("SourceFactionRow raw_name", self.raw_name)

    @property
    def faction_keywords(self) -> tuple[str, ...]:
        return (self.name.upper(),)

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:faction:{self.faction_id}"

    @property
    def source_ids(self) -> tuple[str, ...]:
        return (self.source_id,)

    def to_payload(self) -> dict[str, object]:
        return {
            "faction_id": self.faction_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "faction_keywords": list(self.faction_keywords),
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class SourceDetachmentRow:
    faction_id: str
    detachment_id: str
    raw_name: str
    force_disposition_id: str
    detachment_point_cost: int
    is_new_for_eleventh: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "faction_id",
            _validate_identifier("SourceDetachmentRow faction_id", self.faction_id),
        )
        object.__setattr__(
            self,
            "detachment_id",
            _validate_identifier("SourceDetachmentRow detachment_id", self.detachment_id),
        )
        normalized_name = _normalize_source_label(
            "SourceDetachmentRow raw_name",
            self.raw_name,
        )
        expected_detachment_id = _slug_for_label(normalized_name)
        if self.detachment_id != expected_detachment_id:
            raise FactionDetachmentSourceError(
                "SourceDetachmentRow detachment_id must match normalized raw_name."
            )
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_force_disposition_id(self.force_disposition_id),
        )
        object.__setattr__(
            self,
            "detachment_point_cost",
            _validate_detachment_point_cost(self.detachment_point_cost),
        )
        if type(self.is_new_for_eleventh) is not bool:
            raise FactionDetachmentSourceError(
                "SourceDetachmentRow is_new_for_eleventh must be a boolean."
            )

    @property
    def name(self) -> str:
        return _normalize_source_label("SourceDetachmentRow raw_name", self.raw_name)

    @property
    def source_id(self) -> str:
        return f"{SOURCE_PACKAGE_ID}:detachment:{self.faction_id}:{self.detachment_id}"

    @property
    def source_ids(self) -> tuple[str, ...]:
        return (self.source_id,)

    def to_payload(self) -> dict[str, object]:
        return {
            "faction_id": self.faction_id,
            "detachment_id": self.detachment_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "force_disposition_id": self.force_disposition_id,
            "detachment_point_cost": self.detachment_point_cost,
            "is_new_for_eleventh": self.is_new_for_eleventh,
            "source_id": self.source_id,
        }


def faction_rows() -> tuple[SourceFactionRow, ...]:
    return _FACTION_ROWS


def detachment_rows() -> tuple[SourceDetachmentRow, ...]:
    return _DETACHMENT_ROWS


def source_payload() -> dict[str, object]:
    return {
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
        "factions": [row.to_payload() for row in _FACTION_ROWS],
        "detachments": [row.to_payload() for row in _DETACHMENT_ROWS],
    }


def _faction(raw_name: str) -> SourceFactionRow:
    normalized_name = _normalize_source_label("SourceFactionRow raw_name", raw_name)
    return SourceFactionRow(
        faction_id=_slug_for_label(normalized_name),
        raw_name=raw_name,
    )


def _row(
    faction_id: str,
    raw_name: str,
    raw_force_disposition: str,
    detachment_point_cost: int,
    *,
    new_for_eleventh: bool = False,
) -> SourceDetachmentRow:
    normalized_name = _normalize_source_label("SourceDetachmentRow raw_name", raw_name)
    normalized_force_disposition = _normalize_source_label(
        "SourceDetachmentRow raw_force_disposition",
        raw_force_disposition,
    )
    return SourceDetachmentRow(
        faction_id=faction_id,
        detachment_id=_slug_for_label(normalized_name),
        raw_name=raw_name,
        force_disposition_id=_slug_for_label(normalized_force_disposition),
        detachment_point_cost=detachment_point_cost,
        is_new_for_eleventh=new_for_eleventh,
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise FactionDetachmentSourceError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not _IDENTIFIER_RE.fullmatch(stripped):
        raise FactionDetachmentSourceError(f"{field_name} must be a slug identifier.")
    return stripped


def _validate_force_disposition_id(value: object) -> str:
    force_disposition_id = _validate_identifier(
        "SourceDetachmentRow force_disposition_id",
        value,
    )
    if force_disposition_id not in _VALID_FORCE_DISPOSITION_IDS:
        raise FactionDetachmentSourceError(
            "SourceDetachmentRow force_disposition_id is not recognized."
        )
    return force_disposition_id


def _validate_detachment_point_cost(value: object) -> int:
    if type(value) is not int:
        raise FactionDetachmentSourceError(
            "SourceDetachmentRow detachment_point_cost must be an integer."
        )
    if value < 1 or value > 3:
        raise FactionDetachmentSourceError(
            "SourceDetachmentRow detachment_point_cost must be between 1 and 3."
        )
    return value


def _normalize_source_label(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise FactionDetachmentSourceError(f"{field_name} must be a string.")
    try:
        normalized = normalize_rule_text(value)
    except TextNormalizationError as exc:
        raise FactionDetachmentSourceError(f"{field_name} is invalid.") from exc
    ascii_normalized = (
        unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    )
    stripped = ascii_normalized.strip()
    if not stripped:
        raise FactionDetachmentSourceError(f"{field_name} must not normalize to empty.")
    return stripped


def _slug_for_label(label: str) -> str:
    normalized = _normalize_source_label("slug label", label)
    apostrophe_free = normalized.lower().replace("'", "")
    slug = _NON_IDENTIFIER_TEXT_RE.sub("-", apostrophe_free).strip("-")
    if not slug:
        raise FactionDetachmentSourceError("slug label must not normalize to empty.")
    return slug


def _validate_unique_faction_rows(
    rows: tuple[SourceFactionRow, ...],
) -> tuple[SourceFactionRow, ...]:
    seen: set[str] = set()
    for row in rows:
        if row.faction_id in seen:
            raise FactionDetachmentSourceError("SourceFactionRow faction_id must be unique.")
        seen.add(row.faction_id)
    return rows


def _validate_detachment_rows(
    rows: tuple[SourceDetachmentRow, ...],
    faction_rows: tuple[SourceFactionRow, ...],
) -> tuple[SourceDetachmentRow, ...]:
    faction_ids = {row.faction_id for row in faction_rows}
    seen: set[str] = set()
    for row in rows:
        if row.faction_id not in faction_ids:
            raise FactionDetachmentSourceError(
                "SourceDetachmentRow faction_id must reference a faction row."
            )
        if row.detachment_id in seen:
            raise FactionDetachmentSourceError("SourceDetachmentRow detachment_id must be unique.")
        seen.add(row.detachment_id)
    return rows


_FACTION_ROWS = _validate_unique_faction_rows(
    (
        _faction("Orks"),
        _faction("Aeldari"),
        _faction("Drukhari"),
        _faction("Tyranids"),
        _faction("Genestealer Cults"),
        _faction("Necrons"),
        _faction("Leagues of Votann"),
        _faction("T\u2019au Empire"),
        _faction("Space Marines"),
        _faction("Dark Angels"),
        _faction("Blood Angels"),
        _faction("Space Wolves"),
        _faction("Black Templars"),
        _faction("Deathwatch"),
        _faction("Grey Knights"),
    )
)

_DETACHMENT_ROWS = _validate_detachment_rows(
    (
        _row("orks", "More Dakka!", "Purge the Foe", 1, new_for_eleventh=True),
        _row("orks", "Rollin' Deff", "Priority Assets", 1, new_for_eleventh=True),
        _row("orks", "Taktikal Brigade", "Disruption", 1, new_for_eleventh=True),
        _row("orks", "Blitz Brigade", "Reconnaissance", 2),
        _row("orks", "Bully Boyz", "Purge the Foe", 2),
        _row("orks", "Da Big Hunt", "Purge the Foe", 2),
        _row("orks", "Dread Mob", "Purge the Foe", 2),
        _row("orks", "Freebooter Krew", "Take and Hold", 2),
        _row("orks", "Green Tide", "Take and Hold", 2),
        _row("orks", "Kult of Speed", "Disruption", 2),
        _row("orks", "Speedwaaagh!", "Reconnaissance", 2),
        _row("orks", "War Horde", "Take and Hold", 3),
        _row("aeldari", "Armoured Warhost", "Reconnaissance", 1, new_for_eleventh=True),
        _row("aeldari", "Fateful Performance", "Disruption", 1, new_for_eleventh=True),
        _row("aeldari", "Path of the Outcast", "Reconnaissance", 1, new_for_eleventh=True),
        _row("aeldari", "Twilight Flickers", "Take and Hold", 1, new_for_eleventh=True),
        _row("aeldari", "Aspect Host", "Disruption", 3),
        _row("aeldari", "Corsair Coterie", "Priority Assets", 2),
        _row("aeldari", "Devoted of Ynnead", "Priority Assets", 2),
        _row("aeldari", "Eldritch Raiders", "Disruption", 2),
        _row("aeldari", "Ghosts of the Webway", "Disruption", 2),
        _row("aeldari", "Guardian Battlehost", "Take and Hold", 2),
        _row("aeldari", "Seer Council", "Priority Assets", 2),
        _row("aeldari", "Serpent's Brood", "Purge the Foe", 2),
        _row("aeldari", "Spirit Conclave", "Take and Hold", 2),
        _row("aeldari", "Warhost", "Purge the Foe", 3),
        _row("aeldari", "Windrider Host", "Disruption", 2),
        _row("drukhari", "Exhibition of Slaughter", "Disruption", 1, new_for_eleventh=True),
        _row("drukhari", "Kabalite Agonysts", "Purge the Foe", 1, new_for_eleventh=True),
        _row("drukhari", "Tools of Torment", "Take and Hold", 1, new_for_eleventh=True),
        _row("drukhari", "Covenite Coterie", "Purge the Foe", 2),
        _row("drukhari", "Kabalite Cartel", "Disruption", 2),
        _row("drukhari", "Realspace Raiders", "Priority Assets", 2),
        _row("drukhari", "Reaper's Wager", "Purge the Foe", 3),
        _row("drukhari", "Skysplinter Assault", "Reconnaissance", 2),
        _row("drukhari", "Spectacle of Spite", "Purge the Foe", 2),
        _row("tyranids", "Ambush Predators", "Disruption", 1, new_for_eleventh=True),
        _row("tyranids", "Talons of the Norn Queen", "Take and Hold", 1, new_for_eleventh=True),
        _row("tyranids", "Warrior Bioform Onslaught", "Take and Hold", 1, new_for_eleventh=True),
        _row("tyranids", "Assimilation Swarm", "Priority Assets", 2),
        _row("tyranids", "Crusher Stampede", "Purge the Foe", 2),
        _row("tyranids", "Invasion Fleet", "Take and Hold", 3),
        _row("tyranids", "Subterranean Assault", "Disruption", 3),
        _row("tyranids", "Synaptic Nexus", "Disruption", 2),
        _row("tyranids", "Unending Swarm", "Take and Hold", 2),
        _row("tyranids", "Vanguard Onslaught", "Reconnaissance", 2),
        _row(
            "genestealer-cults",
            "Heroes of the Uprising",
            "Purge the Foe",
            1,
            new_for_eleventh=True,
        ),
        _row(
            "genestealer-cults",
            "Purestrain Broodswarm",
            "Priority Assets",
            1,
            new_for_eleventh=True,
        ),
        _row(
            "genestealer-cults",
            "Xenocult Masses",
            "Disruption",
            1,
            new_for_eleventh=True,
        ),
        _row("genestealer-cults", "Biosanctic Broodsurge", "Take and Hold", 2),
        _row("genestealer-cults", "Brood Brothers Auxillia", "Take and Hold", 2),
        _row("genestealer-cults", "Final Day", "Purge the Foe", 2),
        _row("genestealer-cults", "Host of Ascension", "Take and Hold", 3),
        _row("genestealer-cults", "Outlander Claw", "Reconnaissance", 2),
        _row("genestealer-cults", "Xenocreed Congregation", "Priority Assets", 2),
        _row("necrons", "Hand of the Dynasty", "Take and Hold", 1, new_for_eleventh=True),
        _row("necrons", "Skyshroud Spearhead", "Reconnaissance", 1, new_for_eleventh=True),
        _row("necrons", "The Phaeron's Armoury", "Priority Assets", 1, new_for_eleventh=True),
        _row("necrons", "Annihilation Legion", "Purge the Foe", 2),
        _row("necrons", "Awakened Dynasty", "Take and Hold", 3),
        _row("necrons", "Canoptek Court", "Take and Hold", 3),
        _row("necrons", "Cryptek Conclave", "Priority Assets", 2),
        _row("necrons", "Cursed Legion", "Purge the Foe", 2),
        _row("necrons", "Hypercrypt Legion", "Reconnaissance", 2),
        _row("necrons", "Obeisance Phalanx", "Disruption", 2),
        _row("necrons", "Pantheon of Woe", "Purge the Foe", 2),
        _row("necrons", "Starshatter Arsenal", "Priority Assets", 3),
        _row(
            "leagues-of-votann",
            "Armoured Trailblazers",
            "Disruption",
            1,
            new_for_eleventh=True,
        ),
        _row("leagues-of-votann", "Farseekers", "Reconnaissance", 1, new_for_eleventh=True),
        _row(
            "leagues-of-votann",
            "Hearthguard Covenant",
            "Priority Assets",
            1,
            new_for_eleventh=True,
        ),
        _row("leagues-of-votann", "Brandfast Oathband", "Take and Hold", 2),
        _row("leagues-of-votann", "D\u00ealve Assault Shift", "Purge the Foe", 2),
        _row("leagues-of-votann", "Hearthband", "Priority Assets", 3),
        _row("leagues-of-votann", "Hearthfyre Arsenal", "Priority Assets", 2),
        _row("leagues-of-votann", "Mercenary Oathband", "Take and Hold", 2),
        _row("leagues-of-votann", "Needga\u00e2rd Oathband", "Purge the Foe", 2),
        _row("leagues-of-votann", "Persecution Prospect", "Disruption", 2),
        _row(
            "tau-empire", "Advanced Acquisition Cadre", "Reconnaissance", 1, new_for_eleventh=True
        ),
        _row("tau-empire", "Auxillary Cadre", "Disruption", 1, new_for_eleventh=True),
        _row(
            "tau-empire",
            "Experimental Prototype Cadre",
            "Priority Assets",
            1,
            new_for_eleventh=True,
        ),
        _row("tau-empire", "Kauyon", "Priority Assets", 2),
        _row("tau-empire", "Kroot Hunting Pack", "Take and Hold", 2),
        _row("tau-empire", "Mont'ka", "Purge the Foe", 3),
        _row("tau-empire", "Retaliation Cadre", "Purge the Foe", 2),
        _row("space-marines", "Fulguris Task Force", "Disruption", 1, new_for_eleventh=True),
        _row("space-marines", "Librarius Conclave", "Reconnaissance", 1, new_for_eleventh=True),
        _row("space-marines", "Subversion Assets", "Reconnaissance", 1, new_for_eleventh=True),
        _row("space-marines", "1st Company Task Force", "Priority Assets", 2),
        _row("space-marines", "Anvil Siege Force", "Take and Hold", 2),
        _row("space-marines", "Armoured Speartip", "Take and Hold", 3),
        _row("space-marines", "Bastion Task Force", "Take and Hold", 2),
        _row("space-marines", "Blade of Ultramar", "Priority Assets", 3),
        _row("space-marines", "Ceramite Sentinels", "Take and Hold", 3),
        _row("space-marines", "Emperor's Shield", "Priority Assets", 2),
        _row("space-marines", "Firestorm Assault Force", "Purge the Foe", 2),
        _row("space-marines", "Forgefather's Seekers", "Purge the Foe", 2),
        _row("space-marines", "Gladius Task Force", "Priority Assets", 3),
        _row("space-marines", "Hammer of Avernii", "Priority Assets", 2),
        _row("space-marines", "Headhunter Task Force", "Priority Assets", 2),
        _row("space-marines", "Ironstorm Spearhead", "Purge the Foe", 2),
        _row("space-marines", "Orbital Assault Force", "Take and Hold", 2),
        _row("space-marines", "Reclamation Force", "Take and Hold", 2),
        _row("space-marines", "Shadowmark Talon", "Disruption", 2),
        _row("space-marines", "Spearpoint Task Force", "Disruption", 2),
        _row("space-marines", "Stormlance Task Force", "Disruption", 3),
        _row("space-marines", "Vanguard Spearhead", "Reconnaissance", 2),
        _row("dark-angels", "Dark Age Arsenal", "Priority Assets", 1, new_for_eleventh=True),
        _row("dark-angels", "Darkflight Pursuit", "Reconnaissance", 1, new_for_eleventh=True),
        _row("dark-angels", "Interrogation Conclave", "Purge the Foe", 1, new_for_eleventh=True),
        _row("dark-angels", "Company of Hunters", "Disruption", 2),
        _row("dark-angels", "Inner Circle Task Force", "Priority Assets", 2),
        _row("dark-angels", "Lion's Blade Task Force", "Purge the Foe", 2),
        _row("dark-angels", "Unforgiven Task Force", "Take and Hold", 2),
        _row("dark-angels", "Wrath of the Rock", "Priority Assets", 3),
        _row("blood-angels", "Encarmine Speartip", "Disruption", 1, new_for_eleventh=True),
        _row("blood-angels", "Legacy of Grace", "Priority Assets", 1, new_for_eleventh=True),
        _row("blood-angels", "Wrath of the Doomed", "Purge the Foe", 1, new_for_eleventh=True),
        _row("blood-angels", "Angelic Inheritors", "Priority Assets", 3),
        _row("blood-angels", "Liberator Assault Group", "Take and Hold", 3),
        _row("blood-angels", "Rage-cursed Onslaught", "Purge the Foe", 3),
        _row("blood-angels", "The Angelic Host", "Disruption", 2),
        _row("blood-angels", "The Lost Brethren", "Purge the Foe", 2),
        _row("space-wolves", "Champions of Fenris", "Purge the Foe", 1, new_for_eleventh=True),
        _row(
            "space-wolves",
            "Legends of Saga and Song",
            "Take and Hold",
            1,
            new_for_eleventh=True,
        ),
        _row("space-wolves", "Veterans of the Fang", "Disruption", 1, new_for_eleventh=True),
        _row("space-wolves", "Saga of the Beastslayer", "Purge the Foe", 2),
        _row("space-wolves", "Saga of the Bold", "Priority Assets", 2),
        _row("space-wolves", "Saga of the Great Wolf", "Take and Hold", 2),
        _row("space-wolves", "Saga of the Hunter", "Disruption", 2),
        _row("black-templars", "Marshal's Household", "Priority Assets", 1, new_for_eleventh=True),
        _row("black-templars", "The Living Miracle", "Purge the Foe", 1, new_for_eleventh=True),
        _row("black-templars", "Wrathful Procession", "Take and Hold", 1, new_for_eleventh=True),
        _row("black-templars", "Companions of Vehemence", "Purge the Foe", 2),
        _row("black-templars", "Godhammer Assault Force", "Disruption", 2),
        _row("black-templars", "Vindication Task Force", "Priority Assets", 2),
        _row("deathwatch", "Black Spear Task Force", "Priority Assets", 3),
        _row("grey-knights", "Argent Assault", "Purge the Foe", 1, new_for_eleventh=True),
        _row("grey-knights", "Fires of Purgation", "Disruption", 1, new_for_eleventh=True),
        _row(
            "grey-knights",
            "Immaterial Interdiction",
            "Priority Assets",
            1,
            new_for_eleventh=True,
        ),
        _row("grey-knights", "Augurium Task Force", "Reconnaissance", 2),
        _row("grey-knights", "Banishers", "Disruption", 2),
        _row("grey-knights", "Brotherhood Strike", "Purge the Foe", 2),
        _row("grey-knights", "Hallowed Conclave", "Take and Hold", 2),
        _row("grey-knights", "Sanctic Spearhead", "Priority Assets", 2),
        _row("grey-knights", "Warpbane Task Force", "Purge the Foe", 3),
    ),
    _FACTION_ROWS,
)
