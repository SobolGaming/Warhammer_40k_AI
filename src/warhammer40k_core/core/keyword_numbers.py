"""Declared number spellings of catalog keywords (Core 02.05.01).

This is lexical identity, not an English stemmer or model-owner label matcher.
The canonical spelling is retained from the catalog/source vocabulary. Unknown
words, invariant plurals and compound datasheet names are never guessed.
"""

KEYWORD_NUMBER_SOURCE_ID = "rule:02:02.05.01:1"

_NUMBER_ALIASES = {
    "CHARACTERS": "CHARACTER",
    "MONSTERS": "MONSTER",
    "VEHICLES": "VEHICLE",
    "PSYKERS": "PSYKER",
    "TRANSPORTS": "TRANSPORT",
    "BEASTS": "BEAST",
    "SWARMS": "SWARM",
    "WALKERS": "WALKER",
    "DAEMONS": "DAEMON",
    "BATTLESUITS": "BATTLESUIT",
    "DEDICATED TRANSPORTS": "DEDICATED TRANSPORT",
    "EPIC HEROES": "EPIC HERO",
    "FORTIFICATIONS": "FORTIFICATION",
    "GRENADE": "GRENADES",
    "IMMORTAL": "IMMORTALS",
    "DEATHMARK": "DEATHMARKS",
    "GUARDIAN": "GUARDIANS",
    "ASPECT WARRIORS": "ASPECT WARRIOR",
    "HELLFLAYERS": "HELLFLAYER",
    "TERMINATORS": "TERMINATOR",
    "JUMP PACKS": "JUMP PACK",
    "BURROWERS": "BURROWER",
    "WARLOCKS": "WARLOCK",
}


def keyword_number_identity(token: str) -> str:
    """Resolve an already formatted token to its declared catalog identity."""
    spaced = token.replace("_", " ")
    identity = _NUMBER_ALIASES.get(spaced)
    if identity is None:
        return token
    return identity.replace(" ", "_") if "_" in token else identity


def keyword_number_spellings(token: str) -> tuple[str, ...]:
    """Source vocabulary segmentation must consume the whole literal alias."""
    identity = keyword_number_identity(token).replace("_", " ")
    spellings = {identity, *(a for a, c in _NUMBER_ALIASES.items() if c == identity)}
    return tuple(sorted(s.replace(" ", "_") if "_" in token else s for s in spellings))
