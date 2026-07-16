from __future__ import annotations

import re

UNIT_COMPOSITION_PART_RE = re.compile(
    r"(?P<count>\d+(?:-\d+)?)\s+(?P<name>.+?)"
    r"(?=(?:,\s+|\s+and\s+)\d+(?:-\d+)?\s+|$)",
    re.IGNORECASE,
)
UNIT_COMPOSITION_SEPARATOR_RE = re.compile(r"(?:,\s+|\s+and\s+)", re.IGNORECASE)
UNIT_COMPOSITION_MAX_MODELS_RE = re.compile(
    r"^This unit can contain a maximum of (?P<maximum>\d+) models\.$",
    re.IGNORECASE,
)
OPTION_RE = re.compile(
    r"^1 (?P<model>.+?) that is not equipped with (?:a|an|1) "
    r"(?P<forbidden>.+?) can be equipped with 1 (?P<granted>.+?)\.$",
    re.IGNORECASE,
)
EQUIPMENT_WITH_CHOICES_RE = re.compile(
    r"^This model can be equipped with one of the following:\n"
    r"(?P<choices>(?:- (?:\d+ )?.+?(?:\n|$))+)$",
    re.IGNORECASE,
)
REPLACEMENT_WITH_REQUIRED_CHOICES_RE = re.compile(
    r"^This model's (?P<replaced>.+?) can be replaced with 1 (?P<required>.+?) "
    r"and one of the following:\n(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
REPLACEMENT_WITH_CHOICES_RE = re.compile(
    r"^This model's (?P<replaced>.+?) can be replaced with one of the following:\n"
    r"(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
NAMED_MODEL_REPLACEMENT_WITH_CHOICES_RE = re.compile(
    r"^The (?P<model>.+?) can replace (?:its|their) (?P<replaced>.+?) "
    r"with one of the following:\n(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
SCALED_MODEL_REPLACEMENT_WITH_PAIRED_CHOICES_RE = re.compile(
    r"^For every (?P<models_per_increment>\d+) models in the unit, up to "
    r"(?P<max_per_increment>\d+) (?P<model>.+?) models can each have their "
    r"(?P<replaced_first>.+?) and (?P<replaced_second>.+?) replaced with one of "
    r"the following\*:\n(?P<choices>(?:- 1 .+? and 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
PAIRED_OPTION_CHOICE_RE = re.compile(
    r"^- 1 (?P<first>.+?) and 1 (?P<second>.+?)$",
    re.IGNORECASE,
)
SCALED_OPTION_DUPLICATE_RESTRICTION_RE = re.compile(
    r"^\* You cannot select the same option more than once per unit unless it contains "
    r"(?P<threshold>\d+) models, in which case you cannot select the same weapon more than "
    r"(?P<max_duplicates>\w+) per unit\.$",
    re.IGNORECASE,
)
SINGLE_REPLACEMENT_RE = re.compile(
    r"^This model's (?P<replaced>.+?) can be replaced with "
    r"(?P<replacement_count>\d+) (?P<replacement>.+?)\.?$",
    re.IGNORECASE,
)
EQUIPMENT_CHOICE_RE = re.compile(
    r"^- (?:(?P<count>\d+) )?(?P<name>.+?)\.?$",
    re.IGNORECASE,
)
OPTION_CHOICE_RE = re.compile(r"^- 1 (?P<name>.+?)\.?$", re.IGNORECASE)
OPTION_CHOICE_RESTRICTION_RE = re.compile(
    r"^(?P<name>.+?)\s+\((?P<restriction>.+)\)$",
    re.IGNORECASE,
)
DUPLICATE_EQUIPMENT_RESTRICTION_RE = re.compile(
    r"^a model cannot be equipped with more than one (?P<name>.+)$",
    re.IGNORECASE,
)
DAEMONIC_ALLEGIANCE_ADDITIONAL_WARGEAR_RE = re.compile(
    r"\b(?P<keyword>KHORNE|TZEENTCH|NURGLE|SLAANESH)\s*-\s*"
    r"This model is additionally equipped with:\s*(?P<wargear>.+?)"
    r"(?=(?:\s+\b(?:KHORNE|TZEENTCH|NURGLE|SLAANESH)\s*-\s*"
    r"This model is additionally equipped with:)|\s*$)",
    re.IGNORECASE | re.DOTALL,
)
LOADOUT_RE = re.compile(r"[^.]+? (?:is|are) equipped with: (?P<items>[^.]+)\.?", re.IGNORECASE)
LOADOUT_ITEM_COUNT_RE = re.compile(r"^(?P<count>\d+)\s+(?P<name>.+)$")
DAMAGED_HEADER_RE = re.compile(
    r"^\s*DAMAGED:\s*\d+\s*-\s*\d+\s+WOUNDS\s+REMAINING\s*",
    re.IGNORECASE,
)
DAMAGED_RANGE_RE = re.compile(
    r"While\s+(?:this\s+model|this\s+unit's\s+(?P<model_name>.+?)\s+model)\s+has\s+"
    r"(?P<wounds_min>\d+)\s*-\s*(?P<wounds_max>\d+)\s+wounds\s+remaining",
    re.IGNORECASE,
)
DAMAGED_HIT_RE = re.compile(
    r"each\s+time\s+(?:this\s+model|it|this\s+unit)\s+makes\s+an\s+attack,\s+"
    r"subtract\s+(?P<value>\d+)\s+from\s+the\s+Hit\s+roll",
    re.IGNORECASE,
)
DAMAGED_MODEL_POSSESSIVE_RE = r"this\s+model'?s"
DAMAGED_APOSTROPHE_RE = r"'"
DAMAGED_OC_RE = re.compile(
    rf"subtract\s+(?P<value>\d+)\s+from\s+"
    rf"(?:{DAMAGED_MODEL_POSSESSIVE_RE}|its)\s+"
    r"Objective\s+Control\s+characteristic",
    re.IGNORECASE,
)
DAMAGED_ATTACKS_ADD_RE = re.compile(
    r"add\s+(?P<value>\d+)\s+to\s+the\s+Attacks\s+characteristic\s+of\s+"
    rf"{DAMAGED_MODEL_POSSESSIVE_RE}\s+"
    r"(?P<weapon_scope>melee\s+weapons|[^.]+)",
    re.IGNORECASE,
)
DAMAGED_ATTACKS_HALVE_RE = re.compile(
    r"(?:the\s+Attacks\s+characteristics\s+of\s+all\s+of\s+its\s+weapons\s+are\s+halved|"
    r"halve\s+the\s+Attacks\s+characteristic\s+of\s+that\s+model's\s+weapons)",
    re.IGNORECASE,
)
DAMAGED_SHOOTING_WEAPON_SELECTION_LIMIT_RE = re.compile(
    rf"you\s+can\s+only\s+select\s+(?P<max>\w+)\s+of\s+the\s+"
    rf"(?P<selection_group>C{DAMAGED_APOSTROPHE_RE}tan\s+Powers\s+weapons)\s+"
    r"in\s+your\s+Shooting\s+phase,\s+instead\s+of\s+(?P<baseline>\w+)",
    re.IGNORECASE,
)
DAMAGED_ABILITY_SELECTION_LIMIT_RE = re.compile(
    r"you\s+can\s+only\s+select\s+(?P<max>\w+)\s+ability\s+when\s+using\s+its\s+"
    r"(?P<selection_group>Relics\s+of\s+the\s+Matriarchs\s+ability),\s+"
    r"instead\s+of\s+up\s+to\s+(?P<baseline>\w+)",
    re.IGNORECASE,
)
DAMAGED_IGNORABLE_REMAINDER_RE = re.compile(r"[\s,.;:]+|(?:\band\b)|(?:\bwhile\b)", re.IGNORECASE)
COUNT_WORDS = {
    "once": 1,
    "one": 1,
    "twice": 2,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
DAEMONIC_ALLEGIANCE_KEYWORDS = ("KHORNE", "TZEENTCH", "NURGLE", "SLAANESH")
FACTION_ARMY_RULE_ABILITY_IDS_BY_FACTION_ID = {
    "AE": "000009894",
    "DG": "000008396",
    "EC": "000009994",
    "TS": "000008424",
    "WE": "000008428",
}
