from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

EDITION_ID = "warhammer_40000_10th"
SOURCE_PACKAGE_ID = "gw-10e-core-abilities"
SOURCE_TITLE = "Warhammer 40,000 10th Edition Core Abilities"
SOURCE_VERSION = "10e-core-rules"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-ability-source-v1"


@dataclass(frozen=True, slots=True)
class SourceAbilityRow:
    ability_id: str
    name: str
    source_kind: str
    source_id: str
    when_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    trigger_kind: str
    phase: str | None
    handler_id: str
    required_keywords: tuple[str, ...] = ()
    forbidden_keywords: tuple[str, ...] = ()
    required_input_keys: tuple[str, ...] = ()
    faction_id: str | None = None
    detachment_id: str | None = None
    datasheet_id: str | None = None
    wargear_id: str | None = None
    weapon_profile_id: str | None = None
    effect_payload: dict[str, object] | None = None
    disabled: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "ability_id": self.ability_id,
            "name": self.name,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "when_descriptor": self.when_descriptor,
            "effect_descriptor": self.effect_descriptor,
            "restrictions_descriptor": self.restrictions_descriptor,
            "trigger_kind": self.trigger_kind,
            "phase": self.phase,
            "handler_id": self.handler_id,
            "required_keywords": list(self.required_keywords),
            "forbidden_keywords": list(self.forbidden_keywords),
            "required_input_keys": list(self.required_input_keys),
            "faction_id": self.faction_id,
            "detachment_id": self.detachment_id,
            "datasheet_id": self.datasheet_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "effect_payload": self.effect_payload,
            "disabled": self.disabled,
        }


def source_package_identity_payload() -> dict[str, str]:
    return {
        "edition_id": EDITION_ID,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_commit_or_import_hash": _import_hash(),
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
    }


def core_ability_rows() -> tuple[SourceAbilityRow, ...]:
    source_prefix = f"{SOURCE_PACKAGE_ID}:core"
    return tuple(
        sorted(
            (
                _passive_keyword_row(
                    ability_id="keyword-aircraft",
                    name="AIRCRAFT keyword",
                    required_keywords=("AIRCRAFT",),
                    movement_flags=("is_aircraft",),
                ),
                _passive_keyword_row(
                    ability_id="keyword-beast",
                    name="BEAST keyword",
                    required_keywords=("BEAST",),
                    movement_flags=("is_beast", "can_traverse_ruins_walls"),
                ),
                _passive_keyword_row(
                    ability_id="keyword-belisarius-cawl",
                    name="BELISARIUS CAWL keyword",
                    required_keywords=("BELISARIUS_CAWL",),
                    movement_flags=("can_traverse_ruins_walls",),
                ),
                _passive_keyword_row(
                    ability_id="keyword-fly",
                    name="FLY keyword",
                    required_keywords=("FLY",),
                    movement_flags=("has_fly",),
                ),
                _passive_keyword_row(
                    ability_id="keyword-hover",
                    name="HOVER keyword",
                    required_keywords=("HOVER",),
                    movement_flags=("is_hover",),
                ),
                _passive_keyword_row(
                    ability_id="keyword-imperium-primarch",
                    name="IMPERIUM PRIMARCH keyword",
                    required_keywords=("IMPERIUM_PRIMARCH",),
                    movement_flags=("can_traverse_ruins_walls",),
                ),
                _passive_keyword_row(
                    ability_id="keyword-infantry",
                    name="INFANTRY keyword",
                    required_keywords=("INFANTRY",),
                    movement_flags=("is_infantry", "can_traverse_ruins_walls"),
                ),
                _passive_keyword_row(
                    ability_id="keyword-monster",
                    name="MONSTER keyword",
                    required_keywords=("MONSTER",),
                    movement_flags=("is_monster", "blocks_friendly_vehicle_monster_pass_through"),
                ),
                _passive_keyword_row(
                    ability_id="keyword-titanic",
                    name="TITANIC keyword",
                    required_keywords=("TITANIC",),
                    movement_flags=("is_titanic",),
                ),
                _passive_keyword_row(
                    ability_id="keyword-vehicle",
                    name="VEHICLE keyword",
                    required_keywords=("VEHICLE",),
                    movement_flags=("is_vehicle", "blocks_friendly_vehicle_monster_pass_through"),
                ),
                _passive_keyword_row(
                    ability_id="keyword-walker",
                    name="WALKER keyword",
                    required_keywords=("WALKER",),
                    movement_flags=("is_walker",),
                ),
                SourceAbilityRow(
                    ability_id="core-deadly-demise",
                    name="Deadly Demise",
                    source_kind="core",
                    source_id=f"{source_prefix}:deadly-demise",
                    when_descriptor="when this unit is destroyed",
                    effect_descriptor="roll for a mortal-wound explosion before removal",
                    restrictions_descriptor="core ability parameters define the trigger value",
                    trigger_kind="after_unit_destroyed",
                    phase=None,
                    handler_id="unsupported:phase-13c:deadly-demise",
                    required_keywords=("DEADLY_DEMISE",),
                ),
                SourceAbilityRow(
                    ability_id="core-deep-strike",
                    name="Deep Strike",
                    source_kind="datasheet",
                    source_id=f"{source_prefix}:deep-strike",
                    when_descriptor="deployment and reserves setup",
                    effect_descriptor="unit can be set up in reserves and arrive by its rules",
                    restrictions_descriptor="deployment and reserves phase gates apply",
                    trigger_kind="before_battle",
                    phase=None,
                    handler_id="unsupported:phase-15b:deep-strike",
                    required_keywords=("DEEP_STRIKE",),
                    datasheet_id="core-deep-strike-unit",
                ),
                SourceAbilityRow(
                    ability_id="core-feel-no-pain",
                    name="Feel No Pain",
                    source_kind="core",
                    source_id=f"{source_prefix}:feel-no-pain",
                    when_descriptor="each time this model would lose a wound",
                    effect_descriptor="roll to ignore that lost wound",
                    restrictions_descriptor="only one feel-no-pain ability per lost wound",
                    trigger_kind="any_phase",
                    phase=None,
                    handler_id="unsupported:phase-13c:feel-no-pain",
                    required_keywords=("FEEL_NO_PAIN",),
                ),
                SourceAbilityRow(
                    ability_id="core-firing-deck",
                    name="Firing Deck",
                    source_kind="core",
                    source_id=f"{source_prefix}:firing-deck",
                    when_descriptor="shooting phase when this transport shoots",
                    effect_descriptor="models embarked within can contribute ranged attacks",
                    restrictions_descriptor="transport and embarked model restrictions apply",
                    trigger_kind="start_phase",
                    phase="shooting",
                    handler_id="unsupported:phase-13d:firing-deck",
                    required_keywords=("FIRING_DECK",),
                ),
                SourceAbilityRow(
                    ability_id="core-hazardous",
                    name="Hazardous",
                    source_kind="weapon",
                    source_id=f"{source_prefix}:hazardous",
                    when_descriptor="after attacks are resolved with this weapon",
                    effect_descriptor="make a hazardous test for each affected model or unit",
                    restrictions_descriptor="hazardous weapon test rules apply",
                    trigger_kind="after_dice_roll",
                    phase=None,
                    handler_id="unsupported:phase-13d:hazardous",
                    required_keywords=("HAZARDOUS",),
                ),
                SourceAbilityRow(
                    ability_id="core-infiltrators",
                    name="Infiltrators",
                    source_kind="core",
                    source_id=f"{source_prefix}:infiltrators",
                    when_descriptor="deployment setup",
                    effect_descriptor="unit can be set up using infiltrator deployment rules",
                    restrictions_descriptor="deployment and distance restrictions apply",
                    trigger_kind="before_battle",
                    phase=None,
                    handler_id="unsupported:phase-15b:infiltrators",
                    required_keywords=("INFILTRATORS",),
                ),
                SourceAbilityRow(
                    ability_id="core-leader",
                    name="Leader",
                    source_kind="datasheet",
                    source_id=f"{source_prefix}:leader",
                    when_descriptor="declare battle formations",
                    effect_descriptor="leader can attach to eligible bodyguard units",
                    restrictions_descriptor="datasheet leader attachment list applies",
                    trigger_kind="before_battle",
                    phase=None,
                    handler_id="unsupported:phase-15c:leader",
                    required_keywords=("LEADER",),
                    datasheet_id="core-character-leader",
                ),
                SourceAbilityRow(
                    ability_id="core-lone-operative",
                    name="Lone Operative",
                    source_kind="core",
                    source_id=f"{source_prefix}:lone-operative",
                    when_descriptor="opponent shooting phase when selecting targets",
                    effect_descriptor="unit cannot be selected outside the allowed range gate",
                    restrictions_descriptor=(
                        "visibility, range, and closest eligible target rules apply"
                    ),
                    trigger_kind="after_unit_selected_as_target",
                    phase="shooting",
                    handler_id="unsupported:phase-13b:lone-operative",
                    required_keywords=("LONE_OPERATIVE",),
                ),
                SourceAbilityRow(
                    ability_id="core-scouts",
                    name="Scouts",
                    source_kind="core",
                    source_id=f"{source_prefix}:scouts",
                    when_descriptor="before the first turn begins",
                    effect_descriptor="unit can make a pre-battle scouts move",
                    restrictions_descriptor="scouts distance and transport restrictions apply",
                    trigger_kind="before_battle",
                    phase=None,
                    handler_id="unsupported:phase-15b:scouts",
                    required_keywords=("SCOUTS",),
                ),
                SourceAbilityRow(
                    ability_id="core-stealth",
                    name="Stealth",
                    source_kind="core",
                    source_id=f"{source_prefix}:stealth",
                    when_descriptor="opponent shooting phase when resolving ranged attacks",
                    effect_descriptor="subtract from hit rolls against this unit",
                    restrictions_descriptor="ranged attack timing restrictions apply",
                    trigger_kind="after_unit_selected_as_target",
                    phase="shooting",
                    handler_id="unsupported:phase-13d:stealth",
                    required_keywords=("STEALTH",),
                ),
            ),
            key=lambda row: row.ability_id,
        )
    )


def ability_rows() -> tuple[SourceAbilityRow, ...]:
    return core_ability_rows()


def _passive_keyword_row(
    *,
    ability_id: str,
    name: str,
    required_keywords: tuple[str, ...],
    movement_flags: tuple[str, ...],
) -> SourceAbilityRow:
    source_prefix = f"{SOURCE_PACKAGE_ID}:keyword"
    return SourceAbilityRow(
        ability_id=ability_id,
        name=name,
        source_kind="keyword",
        source_id=f"{source_prefix}:{ability_id}",
        when_descriptor="passive keyword gate",
        effect_descriptor="keyword contributes deterministic movement capability flags",
        restrictions_descriptor="canonical keyword must be present on the source unit",
        trigger_kind="any_phase",
        phase=None,
        handler_id="core:movement-keyword-gate",
        required_keywords=required_keywords,
        effect_payload={"movement_capability_flags": list(movement_flags)},
    )


def _import_hash() -> str:
    encoded = json.dumps(
        {
            "edition_id": EDITION_ID,
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_title": SOURCE_TITLE,
            "source_version": SOURCE_VERSION,
            "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
            "abilities": [row.to_payload() for row in ability_rows()],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
