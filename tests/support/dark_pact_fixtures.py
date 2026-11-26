"""Shared catalog fixture for native Dark Pact timing tests."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import _compact_intercessor_catalog

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import AttachmentTargetEligibility
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.faction_aliases import (
    CHAOS_DAEMONS_FACTION_ID,
    CHAOS_SPACE_MARINES_FACTION_ID,
)
from warhammer40k_core.core.weapon_profiles import RangeProfile
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari import power_from_pain

DATASHEET = "pact-test-marine"
LEADER_SHEET = "core-character-leader"
RESOLVED = "chaos_space_marines_dark_pact_resolved"


def dark_pact_catalog(case: str, *, faction: str, detachment: str, attached: bool) -> ArmyCatalog:
    catalog = _compact_intercessor_catalog(ArmyCatalog.phase9a_canonical_content_pack())
    base = catalog.datasheet_by_id("core-intercessor-like-infantry")
    (model,) = base.model_profiles
    leadership = 2 if case in {"pass", "decline"} else 12
    profiles = tuple(
        replace(
            model,
            model_profile_id=model_id,
            characteristics=tuple(
                CharacteristicValue.from_raw(value.characteristic, leadership)
                if value.characteristic is Characteristic.LEADERSHIP
                else CharacteristicValue.from_raw(value.characteristic, wounds)
                if value.characteristic is Characteristic.WOUNDS
                else value
                for value in model.characteristics
            ),
        )
        for model_id, wounds in (
            ("special-marine", 1 if case in {"casualty", "wipe", "only-gun"} else 6),
            ("standard-marine", 6),
        )
    )
    rifle = next(item for item in catalog.wargear if item.wargear_id == "core-bolt-rifle")
    (ranged,) = rifle.weapon_profiles
    armed = tuple(
        replace(
            rifle,
            wargear_id=f"{prefix}-arms",
            weapon_profiles=(
                *(
                    ()
                    if prefix == "standard" and case == "only-gun"
                    else (replace(ranged, profile_id=f"{prefix}-ranged"),)
                ),
                replace(
                    ranged,
                    profile_id=f"{prefix}-melee",
                    range_profile=RangeProfile.melee(),
                    skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
                ),
            ),
        )
        for prefix in ("unique", "standard")
    )
    daemons = faction == CHAOS_DAEMONS_FACTION_ID
    faction_keyword = {
        CHAOS_DAEMONS_FACTION_ID: "Legiones Daemonica",
        CHAOS_SPACE_MARINES_FACTION_ID: "Heretic Astartes",
        power_from_pain.DRUKHARI_FACTION_ID: "Drukhari",
    }[faction]
    faction_name = {
        CHAOS_DAEMONS_FACTION_ID: "Chaos Daemons",
        CHAOS_SPACE_MARINES_FACTION_ID: "Chaos Space Marines",
        power_from_pain.DRUKHARI_FACTION_ID: "Drukhari",
    }[faction]
    marine = replace(
        base,
        datasheet_id=DATASHEET,
        name="Be'lakor" if daemons else "Dark Pact test marine",
        keywords=DatasheetKeywordSet(
            keywords=(*base.keywords.keywords, "Undivided") if daemons else base.keywords.keywords,
            faction_keywords=(faction_keyword,),
        ),
        model_profiles=profiles,
        composition=(
            UnitCompositionDefinition(
                model_profile_id="special-marine", min_models=1, max_models=1
            ),
            UnitCompositionDefinition(
                model_profile_id="standard-marine",
                min_models=0,
                max_models=1,
                allows_zero_models=True,
            ),
        ),
        wargear_options=tuple(
            DatasheetWargearOption(
                option_id=f"{profile.model_profile_id}-arms",
                model_profile_id=profile.model_profile_id,
                default_wargear_ids=(weapon.wargear_id,),
                allowed_wargear_ids=(weapon.wargear_id,),
                min_selections=1,
                max_selections=1,
            )
            for profile, weapon in zip(profiles, armed, strict=True)
        ),
    )
    if faction == power_from_pain.DRUKHARI_FACTION_ID:
        marine = replace(
            marine,
            abilities=(
                DatasheetAbilityDescriptor(
                    ability_id="fixture-hatred-eternal",
                    name="Hatred Eternal (Pain)",
                    source_id="fixture:hatred-eternal",
                    support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                    source_kind=CatalogAbilitySourceKind.DATASHEET,
                    parameter_tokens=(power_from_pain.HATRED_ETERNAL_ABILITY_KEY,),
                    effect_description="When empowered, this unit can re-roll hit rolls.",
                ),
            ),
        )
    datasheets = catalog.datasheets
    if attached:
        leader = catalog.datasheet_by_id(LEADER_SHEET)
        leader = replace(
            leader,
            keywords=replace(leader.keywords, faction_keywords=(faction_keyword,)),
            attachment_eligibilities=tuple(
                replace(
                    eligibility,
                    targets=(AttachmentTargetEligibility(DATASHEET, ("fixture:leader",)),),
                )
                for eligibility in leader.attachment_eligibilities
            ),
            model_profiles=tuple(
                replace(
                    profile,
                    characteristics=tuple(
                        CharacteristicValue.from_raw(value.characteristic, leadership)
                        if value.characteristic is Characteristic.LEADERSHIP
                        else value
                        for value in profile.characteristics
                    ),
                )
                for profile in leader.model_profiles
            ),
        )
        datasheets = tuple(
            leader if sheet.datasheet_id == LEADER_SHEET else sheet for sheet in datasheets
        )
    return replace(
        catalog,
        datasheets=(*datasheets, marine),
        factions=(
            *catalog.factions,
            FactionDefinition(
                faction_id=faction,
                name=faction_name,
                faction_keywords=(faction_keyword,),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id=detachment,
                detachment_id=detachment,
                name=detachment,
                faction_id=faction,
                detachment_point_cost=1,
                unit_datasheet_ids=(DATASHEET, LEADER_SHEET) if attached else (DATASHEET,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        wargear=(*catalog.wargear, *armed),
    )
