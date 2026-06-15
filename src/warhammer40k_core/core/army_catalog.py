from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.content_scope import (
    SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES,
    CatalogContentScope,
)
from warhammer40k_core.core.datasheet import (
    AttachmentEligibility,
    AttachmentRole,
    BaseSizeDefinition,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetCatalogError,
    DatasheetDefinition,
    DatasheetDefinitionPayload,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    ModelProfileDefinition,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import (
    DetachmentCatalogError,
    DetachmentDefinition,
    DetachmentDefinitionPayload,
    EnhancementDefinition,
    EnhancementDefinitionPayload,
    StratagemDefinition,
    StratagemDefinitionPayload,
)
from warhammer40k_core.core.faction import (
    ArmyRuleDefinition,
    ArmyRuleDefinitionPayload,
    FactionCatalogError,
    FactionDefinition,
    FactionDefinitionPayload,
)
from warhammer40k_core.core.ruleset import RulesetError, RulesetId, RulesetIdPayload
from warhammer40k_core.core.wargear import Wargear, WargearError, WargearPayload
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)


class ArmyCatalogError(ValueError):
    """Raised when army catalog data violates CORE V2 invariants."""


class ArmyCatalogPayload(TypedDict):
    catalog_id: str
    ruleset_id: RulesetIdPayload
    source_package_id: str
    datasheets: list[DatasheetDefinitionPayload]
    wargear: list[WargearPayload]
    factions: list[FactionDefinitionPayload]
    army_rules: list[ArmyRuleDefinitionPayload]
    detachments: list[DetachmentDefinitionPayload]
    enhancements: list[EnhancementDefinitionPayload]
    stratagems: list[StratagemDefinitionPayload]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class ArmyCatalog:
    catalog_id: str
    ruleset_id: RulesetId
    source_package_id: str
    datasheets: tuple[DatasheetDefinition, ...]
    wargear: tuple[Wargear, ...]
    factions: tuple[FactionDefinition, ...]
    army_rules: tuple[ArmyRuleDefinition, ...] = ()
    detachments: tuple[DetachmentDefinition, ...] = ()
    enhancements: tuple[EnhancementDefinition, ...] = ()
    stratagems: tuple[StratagemDefinition, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_id",
            _validate_unprefixed_identifier("ArmyCatalog catalog_id", self.catalog_id, "catalog:"),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise ArmyCatalogError("ArmyCatalog ruleset_id must be a RulesetId.")
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("ArmyCatalog source_package_id", self.source_package_id),
        )
        datasheets = _validate_datasheet_tuple("ArmyCatalog datasheets", self.datasheets)
        wargear = _validate_wargear_tuple("ArmyCatalog wargear", self.wargear)
        factions = _validate_faction_tuple("ArmyCatalog factions", self.factions)
        army_rules = _validate_army_rule_tuple("ArmyCatalog army_rules", self.army_rules)
        detachments = _validate_detachment_tuple("ArmyCatalog detachments", self.detachments)
        enhancements = _validate_enhancement_tuple("ArmyCatalog enhancements", self.enhancements)
        stratagems = _validate_stratagem_tuple("ArmyCatalog stratagems", self.stratagems)

        _validate_datasheet_faction_keywords(datasheets, factions)
        _validate_datasheet_wargear_links(datasheets, wargear)
        _validate_faction_rule_links(factions, army_rules)
        _validate_supported_content_scopes(
            datasheets=datasheets,
            factions=factions,
            army_rules=army_rules,
            detachments=detachments,
            enhancements=enhancements,
            stratagems=stratagems,
        )
        _validate_detachment_links(detachments, datasheets, factions, enhancements, stratagems)

        object.__setattr__(
            self,
            "datasheets",
            tuple(sorted(datasheets, key=lambda datasheet: datasheet.datasheet_id)),
        )
        object.__setattr__(
            self,
            "wargear",
            tuple(sorted(wargear, key=lambda item: item.wargear_id)),
        )
        object.__setattr__(
            self,
            "factions",
            tuple(sorted(factions, key=lambda faction: faction.faction_id)),
        )
        object.__setattr__(
            self,
            "army_rules",
            tuple(sorted(army_rules, key=lambda rule: rule.rule_id)),
        )
        object.__setattr__(
            self,
            "detachments",
            tuple(sorted(detachments, key=lambda detachment: detachment.detachment_id)),
        )
        object.__setattr__(
            self,
            "enhancements",
            tuple(sorted(enhancements, key=lambda enhancement: enhancement.enhancement_id)),
        )
        object.__setattr__(
            self,
            "stratagems",
            tuple(sorted(stratagems, key=lambda stratagem: stratagem.stratagem_id)),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("ArmyCatalog source_ids", self.source_ids),
        )

    @classmethod
    def phase9a_canonical_content_pack(cls) -> Self:
        source_package_id = "data-package:core-v2:phase9a-canonical:0.1.0"
        infantry_wargear = _ranged_wargear(
            wargear_id="core-bolt-rifle",
            name="Core bolt rifle",
            range_inches=24,
            attacks=2,
            ballistic_skill=3,
            strength=4,
            armor_penetration=-1,
            damage=1,
            keywords=(WeaponKeyword.ASSAULT, WeaponKeyword.RAPID_FIRE),
            abilities=(AbilityDescriptor.rapid_fire(1),),
        )
        mob_wargear = _ranged_wargear(
            wargear_id="core-mob-shoota",
            name="Core mob shoota",
            range_inches=18,
            attacks=2,
            ballistic_skill=5,
            strength=4,
            armor_penetration=0,
            damage=1,
            keywords=(),
        )
        leader_wargear = _melee_wargear(
            wargear_id="core-leader-blade",
            name="Core leader blade",
            attacks=5,
            weapon_skill=2,
            strength=5,
            armor_penetration=-2,
            damage=2,
        )
        transport_wargear = _ranged_wargear(
            wargear_id="core-transport-array",
            name="Core transport array",
            range_inches=24,
            attacks=6,
            ballistic_skill=4,
            strength=5,
            armor_penetration=0,
            damage=1,
            keywords=(),
        )
        transport_firing_deck_ability = DatasheetAbilityDescriptor(
            ability_id="core-firing-deck",
            name="CORE Firing Deck",
            source_id="datasheet:core-transport:ability:firing-deck",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            timing_tags=("shooting",),
            parameter_tokens=("2",),
        )
        vehicle_wargear = _ranged_wargear(
            wargear_id="core-heavy-cannon",
            name="Core heavy cannon",
            range_inches=48,
            attacks=2,
            ballistic_skill=4,
            strength=10,
            armor_penetration=-2,
            damage=3,
            keywords=(WeaponKeyword.HEAVY,),
            abilities=(AbilityDescriptor.heavy(),),
        )
        deep_strike_wargear = _ranged_wargear(
            wargear_id="core-drop-carbine",
            name="Core drop carbine",
            range_inches=18,
            attacks=3,
            ballistic_skill=3,
            strength=4,
            armor_penetration=0,
            damage=1,
            keywords=(),
        )
        army_rule = ArmyRuleDefinition(
            rule_id="core-discipline",
            name="Core Discipline",
            source_id="army-rule:core-discipline",
        )
        faction = FactionDefinition(
            faction_id="core-marine-force",
            name="CORE Marine Force",
            content_scope=CatalogContentScope.MATCHED_PLAY,
            faction_keywords=("CORE Marines",),
            army_rule_ids=(army_rule.rule_id,),
            source_ids=("faction:core-marine-force",),
        )
        detachment = DetachmentDefinition(
            detachment_id="core-combined-arms",
            name="CORE Combined Arms",
            faction_id=faction.faction_id,
            content_scope=CatalogContentScope.MATCHED_PLAY,
            detachment_point_cost=1,
            unit_datasheet_ids=(
                "core-boyz-like-infantry",
                "core-character-leader",
                "core-character-support",
                "core-deep-strike-unit",
                "core-intercessor-like-infantry",
                "core-transport",
                "core-vehicle-monster",
            ),
            force_disposition_ids=("purge-the-foe",),
            source_ids=("detachment:core-combined-arms",),
        )
        return cls(
            catalog_id="phase9a-canonical",
            ruleset_id=RulesetId.warhammer_40000_eleventh(version="core-v2-phase9a"),
            source_package_id=source_package_id,
            datasheets=(
                _datasheet(
                    datasheet_id="core-intercessor-like-infantry",
                    name="CORE Intercessor-like Infantry",
                    model_profile_id="core-intercessor-like",
                    min_models=5,
                    max_models=10,
                    base_diameter_mm=32.0,
                    movement=6,
                    toughness=4,
                    save=3,
                    wounds=2,
                    leadership=6,
                    objective_control=2,
                    weapon_skill=3,
                    ballistic_skill=3,
                    keywords=("Infantry", "Battleline"),
                    faction_keywords=("CORE Marines",),
                    wargear_id=infantry_wargear.wargear_id,
                ),
                _datasheet(
                    datasheet_id="core-boyz-like-infantry",
                    name="CORE Boyz-like Infantry",
                    model_profile_id="core-boyz-like",
                    min_models=10,
                    max_models=20,
                    base_diameter_mm=32.0,
                    movement=6,
                    toughness=5,
                    save=6,
                    wounds=1,
                    leadership=7,
                    objective_control=2,
                    weapon_skill=3,
                    ballistic_skill=5,
                    keywords=("Infantry",),
                    faction_keywords=("CORE Marines",),
                    wargear_id=mob_wargear.wargear_id,
                ),
                _datasheet(
                    datasheet_id="core-character-leader",
                    name="CORE Character Leader",
                    model_profile_id="core-character-leader",
                    min_models=1,
                    max_models=1,
                    base_diameter_mm=40.0,
                    movement=6,
                    toughness=4,
                    save=3,
                    wounds=5,
                    leadership=5,
                    objective_control=1,
                    weapon_skill=2,
                    ballistic_skill=2,
                    keywords=("Character", "Leader", "Infantry"),
                    faction_keywords=("CORE Marines",),
                    wargear_id=leader_wargear.wargear_id,
                    attachment_eligibilities=(
                        AttachmentEligibility(
                            role=AttachmentRole.LEADER,
                            allowed_bodyguard_datasheet_ids=("core-intercessor-like-infantry",),
                            source_id="datasheet:core-character-leader:attachment:leader",
                        ),
                    ),
                ),
                _datasheet(
                    datasheet_id="core-character-support",
                    name="CORE Character Support",
                    model_profile_id="core-character-support",
                    min_models=1,
                    max_models=1,
                    base_diameter_mm=40.0,
                    movement=6,
                    toughness=4,
                    save=3,
                    wounds=4,
                    leadership=5,
                    objective_control=1,
                    weapon_skill=2,
                    ballistic_skill=2,
                    keywords=("Character", "Support", "Infantry"),
                    faction_keywords=("CORE Marines",),
                    wargear_id=leader_wargear.wargear_id,
                    attachment_eligibilities=(
                        AttachmentEligibility(
                            role=AttachmentRole.SUPPORT,
                            allowed_bodyguard_datasheet_ids=("core-intercessor-like-infantry",),
                            source_id="datasheet:core-character-support:attachment:support",
                        ),
                    ),
                ),
                _datasheet(
                    datasheet_id="core-transport",
                    name="CORE Transport",
                    model_profile_id="core-transport",
                    min_models=1,
                    max_models=1,
                    base_diameter_mm=100.0,
                    movement=12,
                    toughness=9,
                    save=3,
                    wounds=10,
                    leadership=6,
                    objective_control=2,
                    weapon_skill=6,
                    ballistic_skill=4,
                    keywords=("Transport", "Vehicle"),
                    faction_keywords=("CORE Marines",),
                    wargear_id=transport_wargear.wargear_id,
                    abilities=(transport_firing_deck_ability,),
                ),
                _datasheet(
                    datasheet_id="core-vehicle-monster",
                    name="CORE Vehicle Monster",
                    model_profile_id="core-vehicle-monster",
                    min_models=1,
                    max_models=1,
                    base_diameter_mm=120.0,
                    movement=10,
                    toughness=10,
                    save=3,
                    wounds=12,
                    leadership=6,
                    objective_control=4,
                    weapon_skill=4,
                    ballistic_skill=4,
                    keywords=("Monster", "Vehicle"),
                    faction_keywords=("CORE Marines",),
                    wargear_id=vehicle_wargear.wargear_id,
                ),
                _deep_strike_datasheet(wargear_id=deep_strike_wargear.wargear_id),
            ),
            wargear=(
                infantry_wargear,
                mob_wargear,
                leader_wargear,
                transport_wargear,
                vehicle_wargear,
                deep_strike_wargear,
            ),
            factions=(faction,),
            army_rules=(army_rule,),
            detachments=(detachment,),
            source_ids=("catalog:phase9a-canonical",),
        )

    def stable_identity(self) -> str:
        return f"catalog:{self.catalog_id}"

    def datasheet_by_id(self, datasheet_id: str) -> DatasheetDefinition:
        requested_id = _validate_identifier("datasheet_id", datasheet_id)
        for datasheet in self.datasheets:
            if datasheet.datasheet_id == requested_id:
                return datasheet
        raise ArmyCatalogError("ArmyCatalog datasheet_id was not found.")

    def faction_by_id(self, faction_id: str) -> FactionDefinition:
        requested_id = _validate_identifier("faction_id", faction_id)
        for faction in self.factions:
            if faction.faction_id == requested_id:
                return faction
        raise ArmyCatalogError("ArmyCatalog faction_id was not found.")

    def to_payload(self) -> ArmyCatalogPayload:
        return {
            "catalog_id": self.catalog_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "source_package_id": self.source_package_id,
            "datasheets": [datasheet.to_payload() for datasheet in self.datasheets],
            "wargear": [item.to_payload() for item in self.wargear],
            "factions": [faction.to_payload() for faction in self.factions],
            "army_rules": [rule.to_payload() for rule in self.army_rules],
            "detachments": [detachment.to_payload() for detachment in self.detachments],
            "enhancements": [enhancement.to_payload() for enhancement in self.enhancements],
            "stratagems": [stratagem.to_payload() for stratagem in self.stratagems],
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: ArmyCatalogPayload) -> Self:
        return cls(
            catalog_id=payload["catalog_id"],
            ruleset_id=_ruleset_id_from_payload(payload["ruleset_id"]),
            source_package_id=payload["source_package_id"],
            datasheets=tuple(
                _datasheet_from_payload(datasheet) for datasheet in payload["datasheets"]
            ),
            wargear=tuple(_wargear_from_payload(item) for item in payload["wargear"]),
            factions=tuple(_faction_from_payload(faction) for faction in payload["factions"]),
            army_rules=tuple(_army_rule_from_payload(rule) for rule in payload["army_rules"]),
            detachments=tuple(
                _detachment_from_payload(detachment) for detachment in payload["detachments"]
            ),
            enhancements=tuple(
                _enhancement_from_payload(enhancement) for enhancement in payload["enhancements"]
            ),
            stratagems=tuple(
                _stratagem_from_payload(stratagem) for stratagem in payload["stratagems"]
            ),
            source_ids=tuple(payload["source_ids"]),
        )


def _datasheet(
    *,
    datasheet_id: str,
    name: str,
    model_profile_id: str,
    min_models: int,
    max_models: int,
    base_diameter_mm: float,
    movement: int,
    toughness: int,
    save: int,
    wounds: int,
    leadership: int,
    objective_control: int,
    weapon_skill: int,
    ballistic_skill: int,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    wargear_id: str,
    abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
    attachment_eligibilities: tuple[AttachmentEligibility, ...] = (),
) -> DatasheetDefinition:
    return DatasheetDefinition(
        datasheet_id=datasheet_id,
        name=name,
        content_scope=CatalogContentScope.MATCHED_PLAY,
        keywords=DatasheetKeywordSet(keywords=keywords, faction_keywords=faction_keywords),
        model_profiles=(
            ModelProfileDefinition(
                model_profile_id=model_profile_id,
                name=name,
                characteristics=_core_characteristics(
                    movement=movement,
                    toughness=toughness,
                    save=save,
                    wounds=wounds,
                    leadership=leadership,
                    objective_control=objective_control,
                    weapon_skill=weapon_skill,
                    ballistic_skill=ballistic_skill,
                ),
                base_size=BaseSizeDefinition.circular(base_diameter_mm),
                source_ids=(f"datasheet:{datasheet_id}:profile",),
            ),
        ),
        composition=(
            UnitCompositionDefinition(
                model_profile_id=model_profile_id,
                min_models=min_models,
                max_models=max_models,
            ),
        ),
        wargear_options=(
            DatasheetWargearOption(
                option_id=f"{datasheet_id}:default-wargear",
                model_profile_id=model_profile_id,
                default_wargear_ids=(wargear_id,),
                allowed_wargear_ids=(wargear_id,),
                min_selections=1,
                max_selections=1,
            ),
        ),
        abilities=abilities,
        attachment_eligibilities=attachment_eligibilities,
        source_ids=(f"datasheet:{datasheet_id}",),
    )


def _deep_strike_datasheet(wargear_id: str) -> DatasheetDefinition:
    datasheet_id = "core-deep-strike-unit"
    ability = DatasheetAbilityDescriptor(
        ability_id="core-deep-strike",
        name="CORE Deep Strike",
        source_id=f"datasheet:{datasheet_id}:ability:deep-strike",
        support=CatalogAbilitySupport.UNSUPPORTED,
        timing_tags=("deployment", "reserves"),
    )
    return DatasheetDefinition(
        datasheet_id=datasheet_id,
        name="CORE Deep Strike Unit",
        content_scope=CatalogContentScope.MATCHED_PLAY,
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Deep Strike"),
            faction_keywords=("CORE Marines",),
        ),
        model_profiles=(
            ModelProfileDefinition(
                model_profile_id="core-deep-strike-model",
                name="CORE Deep Strike Model",
                characteristics=_core_characteristics(
                    movement=10,
                    toughness=4,
                    save=3,
                    wounds=2,
                    leadership=6,
                    objective_control=1,
                    weapon_skill=3,
                    ballistic_skill=3,
                ),
                base_size=BaseSizeDefinition.circular(32.0),
                source_ids=("datasheet:core-deep-strike-unit:profile",),
            ),
        ),
        composition=(
            UnitCompositionDefinition(
                model_profile_id="core-deep-strike-model",
                min_models=3,
                max_models=6,
            ),
        ),
        wargear_options=(
            DatasheetWargearOption(
                option_id="core-deep-strike-unit:default-wargear",
                model_profile_id="core-deep-strike-model",
                default_wargear_ids=(wargear_id,),
                allowed_wargear_ids=(wargear_id,),
                min_selections=1,
                max_selections=1,
            ),
        ),
        abilities=(ability,),
        source_ids=("datasheet:core-deep-strike-unit",),
    )


def _core_characteristics(
    *,
    movement: int,
    toughness: int,
    save: int,
    wounds: int,
    leadership: int,
    objective_control: int,
    weapon_skill: int,
    ballistic_skill: int,
    invulnerable_save: int | None = None,
) -> tuple[CharacteristicValue, ...]:
    return (
        CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, ballistic_skill),
        (
            CharacteristicValue.source_dash(Characteristic.INVULNERABLE_SAVE)
            if invulnerable_save is None
            else CharacteristicValue.from_raw(Characteristic.INVULNERABLE_SAVE, invulnerable_save)
        ),
        CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership),
        CharacteristicValue.from_raw(Characteristic.MOVEMENT, movement),
        CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, objective_control),
        CharacteristicValue.from_raw(Characteristic.SAVE, save),
        CharacteristicValue.from_raw(Characteristic.TOUGHNESS, toughness),
        CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, weapon_skill),
        CharacteristicValue.from_raw(Characteristic.WOUNDS, wounds),
    )


def _ranged_wargear(
    *,
    wargear_id: str,
    name: str,
    range_inches: int,
    attacks: int,
    ballistic_skill: int,
    strength: int,
    armor_penetration: int,
    damage: int,
    keywords: tuple[WeaponKeyword, ...],
    abilities: tuple[AbilityDescriptor, ...] = (),
) -> Wargear:
    return Wargear(
        wargear_id=wargear_id,
        name=name,
        weapon_profiles=(
            WeaponProfile(
                profile_id=f"{wargear_id}:standard",
                name=name,
                range_profile=RangeProfile.distance(range_inches),
                attack_profile=AttackProfile.fixed(attacks),
                skill=CharacteristicValue.from_raw(
                    Characteristic.BALLISTIC_SKILL,
                    ballistic_skill,
                ),
                strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, strength),
                armor_penetration=CharacteristicValue.from_raw(
                    Characteristic.ARMOR_PENETRATION,
                    armor_penetration,
                ),
                damage_profile=DamageProfile.fixed(damage),
                keywords=keywords,
                abilities=abilities,
            ),
        ),
    )


def _melee_wargear(
    *,
    wargear_id: str,
    name: str,
    attacks: int,
    weapon_skill: int,
    strength: int,
    armor_penetration: int,
    damage: int,
) -> Wargear:
    return Wargear(
        wargear_id=wargear_id,
        name=name,
        weapon_profiles=(
            WeaponProfile(
                profile_id=f"{wargear_id}:standard",
                name=name,
                range_profile=RangeProfile.melee(),
                attack_profile=AttackProfile.fixed(attacks),
                skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, weapon_skill),
                strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, strength),
                armor_penetration=CharacteristicValue.from_raw(
                    Characteristic.ARMOR_PENETRATION,
                    armor_penetration,
                ),
                damage_profile=DamageProfile.fixed(damage),
            ),
        ),
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise ArmyCatalogError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ArmyCatalogError(f"{field_name} must not be empty.")
    return stripped


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise ArmyCatalogError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_datasheet_tuple(
    field_name: str,
    values: tuple[DatasheetDefinition, ...],
) -> tuple[DatasheetDefinition, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[DatasheetDefinition] = []
    for value in values:
        if type(value) is not DatasheetDefinition:
            raise ArmyCatalogError(f"{field_name} must contain DatasheetDefinition values.")
        if value.datasheet_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate datasheet IDs.")
        seen.add(value.datasheet_id)
        validated.append(value)
    return tuple(validated)


def _validate_wargear_tuple(field_name: str, values: tuple[Wargear, ...]) -> tuple[Wargear, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[Wargear] = []
    for value in values:
        if type(value) is not Wargear:
            raise ArmyCatalogError(f"{field_name} must contain Wargear values.")
        if value.wargear_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate wargear IDs.")
        seen.add(value.wargear_id)
        validated.append(value)
    return tuple(validated)


def _validate_faction_tuple(
    field_name: str,
    values: tuple[FactionDefinition, ...],
) -> tuple[FactionDefinition, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[FactionDefinition] = []
    for value in values:
        if type(value) is not FactionDefinition:
            raise ArmyCatalogError(f"{field_name} must contain FactionDefinition values.")
        if value.faction_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate faction IDs.")
        seen.add(value.faction_id)
        validated.append(value)
    return tuple(validated)


def _validate_army_rule_tuple(
    field_name: str,
    values: tuple[ArmyRuleDefinition, ...],
) -> tuple[ArmyRuleDefinition, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[ArmyRuleDefinition] = []
    for value in values:
        if type(value) is not ArmyRuleDefinition:
            raise ArmyCatalogError(f"{field_name} must contain ArmyRuleDefinition values.")
        if value.rule_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate rule IDs.")
        seen.add(value.rule_id)
        validated.append(value)
    return tuple(validated)


def _validate_detachment_tuple(
    field_name: str,
    values: tuple[DetachmentDefinition, ...],
) -> tuple[DetachmentDefinition, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[DetachmentDefinition] = []
    for value in values:
        if type(value) is not DetachmentDefinition:
            raise ArmyCatalogError(f"{field_name} must contain DetachmentDefinition values.")
        if value.detachment_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate detachment IDs.")
        seen.add(value.detachment_id)
        validated.append(value)
    return tuple(validated)


def _validate_enhancement_tuple(
    field_name: str,
    values: tuple[EnhancementDefinition, ...],
) -> tuple[EnhancementDefinition, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[EnhancementDefinition] = []
    for value in values:
        if type(value) is not EnhancementDefinition:
            raise ArmyCatalogError(f"{field_name} must contain EnhancementDefinition values.")
        if value.enhancement_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate enhancement IDs.")
        seen.add(value.enhancement_id)
        validated.append(value)
    return tuple(validated)


def _validate_stratagem_tuple(
    field_name: str,
    values: tuple[StratagemDefinition, ...],
) -> tuple[StratagemDefinition, ...]:
    if type(values) is not tuple:
        raise ArmyCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[StratagemDefinition] = []
    for value in values:
        if type(value) is not StratagemDefinition:
            raise ArmyCatalogError(f"{field_name} must contain StratagemDefinition values.")
        if value.stratagem_id in seen:
            raise ArmyCatalogError(f"{field_name} must not contain duplicate stratagem IDs.")
        seen.add(value.stratagem_id)
        validated.append(value)
    return tuple(validated)


def _validate_datasheet_faction_keywords(
    datasheets: tuple[DatasheetDefinition, ...],
    factions: tuple[FactionDefinition, ...],
) -> None:
    faction_keywords: set[str] = set()
    for faction in factions:
        faction_keywords.update(faction.faction_keywords)
    for datasheet in datasheets:
        if not datasheet.keywords.faction_keywords:
            raise ArmyCatalogError("ArmyCatalog datasheets must declare faction keywords.")
        if not set(datasheet.keywords.faction_keywords).intersection(faction_keywords):
            raise ArmyCatalogError("ArmyCatalog datasheet faction keywords must match a faction.")


def _validate_datasheet_wargear_links(
    datasheets: tuple[DatasheetDefinition, ...],
    wargear: tuple[Wargear, ...],
) -> None:
    wargear_ids = {item.wargear_id for item in wargear}
    for datasheet in datasheets:
        for option in datasheet.wargear_options:
            for wargear_id in (*option.default_wargear_ids, *option.allowed_wargear_ids):
                if wargear_id not in wargear_ids:
                    raise ArmyCatalogError("ArmyCatalog datasheet references unknown wargear.")


def _validate_faction_rule_links(
    factions: tuple[FactionDefinition, ...],
    army_rules: tuple[ArmyRuleDefinition, ...],
) -> None:
    army_rule_ids = {rule.rule_id for rule in army_rules}
    for faction in factions:
        for rule_id in faction.army_rule_ids:
            if rule_id not in army_rule_ids:
                raise ArmyCatalogError("ArmyCatalog faction references an unknown army rule.")


def _validate_detachment_links(
    detachments: tuple[DetachmentDefinition, ...],
    datasheets: tuple[DatasheetDefinition, ...],
    factions: tuple[FactionDefinition, ...],
    enhancements: tuple[EnhancementDefinition, ...],
    stratagems: tuple[StratagemDefinition, ...],
) -> None:
    datasheet_ids = {datasheet.datasheet_id for datasheet in datasheets}
    faction_ids = {faction.faction_id for faction in factions}
    enhancement_ids = {enhancement.enhancement_id for enhancement in enhancements}
    stratagem_ids = {stratagem.stratagem_id for stratagem in stratagems}
    for detachment in detachments:
        if detachment.faction_id not in faction_ids:
            raise ArmyCatalogError("ArmyCatalog detachment references an unknown faction.")
        for datasheet_id in detachment.unit_datasheet_ids:
            if datasheet_id not in datasheet_ids:
                raise ArmyCatalogError("ArmyCatalog detachment references an unknown datasheet.")
        for enhancement_id in detachment.enhancement_ids:
            if enhancement_id not in enhancement_ids:
                raise ArmyCatalogError("ArmyCatalog detachment references an unknown enhancement.")
        for stratagem_id in detachment.stratagem_ids:
            if stratagem_id not in stratagem_ids:
                raise ArmyCatalogError("ArmyCatalog detachment references an unknown stratagem.")


def _validate_supported_content_scopes(
    *,
    datasheets: tuple[DatasheetDefinition, ...],
    factions: tuple[FactionDefinition, ...],
    army_rules: tuple[ArmyRuleDefinition, ...],
    detachments: tuple[DetachmentDefinition, ...],
    enhancements: tuple[EnhancementDefinition, ...],
    stratagems: tuple[StratagemDefinition, ...],
) -> None:
    for datasheet in datasheets:
        if datasheet.content_scope not in SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES:
            raise ArmyCatalogError("ArmyCatalog contains unsupported datasheet content scope.")
    for faction in factions:
        if faction.content_scope not in SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES:
            raise ArmyCatalogError("ArmyCatalog contains unsupported faction content scope.")
    for army_rule in army_rules:
        if army_rule.content_scope not in SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES:
            raise ArmyCatalogError("ArmyCatalog contains unsupported army rule content scope.")
    for detachment in detachments:
        if detachment.content_scope not in SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES:
            raise ArmyCatalogError("ArmyCatalog contains unsupported detachment content scope.")
    for enhancement in enhancements:
        if enhancement.content_scope not in SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES:
            raise ArmyCatalogError("ArmyCatalog contains unsupported enhancement content scope.")
    for stratagem in stratagems:
        if stratagem.content_scope not in SUPPORTED_ARMY_CATALOG_CONTENT_SCOPES:
            raise ArmyCatalogError("ArmyCatalog contains unsupported stratagem content scope.")


def _ruleset_id_from_payload(payload: RulesetIdPayload) -> RulesetId:
    try:
        return RulesetId.from_payload(payload)
    except RulesetError as exc:
        raise ArmyCatalogError("ArmyCatalog ruleset_id payload is invalid.") from exc


def _datasheet_from_payload(payload: DatasheetDefinitionPayload) -> DatasheetDefinition:
    try:
        return DatasheetDefinition.from_payload(payload)
    except DatasheetCatalogError as exc:
        raise ArmyCatalogError("ArmyCatalog datasheet payload is invalid.") from exc


def _wargear_from_payload(payload: WargearPayload) -> Wargear:
    try:
        return Wargear.from_payload(payload)
    except WargearError as exc:
        raise ArmyCatalogError("ArmyCatalog wargear payload is invalid.") from exc


def _faction_from_payload(payload: FactionDefinitionPayload) -> FactionDefinition:
    try:
        return FactionDefinition.from_payload(payload)
    except FactionCatalogError as exc:
        raise ArmyCatalogError("ArmyCatalog faction payload is invalid.") from exc


def _army_rule_from_payload(payload: ArmyRuleDefinitionPayload) -> ArmyRuleDefinition:
    try:
        return ArmyRuleDefinition.from_payload(payload)
    except FactionCatalogError as exc:
        raise ArmyCatalogError("ArmyCatalog army rule payload is invalid.") from exc


def _detachment_from_payload(payload: DetachmentDefinitionPayload) -> DetachmentDefinition:
    try:
        return DetachmentDefinition.from_payload(payload)
    except DetachmentCatalogError as exc:
        raise ArmyCatalogError("ArmyCatalog detachment payload is invalid.") from exc


def _enhancement_from_payload(payload: EnhancementDefinitionPayload) -> EnhancementDefinition:
    try:
        return EnhancementDefinition.from_payload(payload)
    except DetachmentCatalogError as exc:
        raise ArmyCatalogError("ArmyCatalog enhancement payload is invalid.") from exc


def _stratagem_from_payload(payload: StratagemDefinitionPayload) -> StratagemDefinition:
    try:
        return StratagemDefinition.from_payload(payload)
    except DetachmentCatalogError as exc:
        raise ArmyCatalogError("ArmyCatalog stratagem payload is invalid.") from exc
