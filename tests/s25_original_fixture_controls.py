"""Pre-start fixture distinctions that preserve original physical branch checks."""

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue

RETAINED_DISTINCT_LEADER_DATASHEET_ID = "analytical:s25-retained-distinct-enemy-leader"


def retained_distinct_weapon_catalog(catalog: ArmyCatalog) -> ArmyCatalog:
    """Keep the original first-group casualty/remaining-group skip reachable.

    Identical attacks from an attached bodyguard and leader must gather under
    S25. The original regression specifically tests a *remaining* group. Give
    the leader a genuinely distinct predeclared Strength while retaining its
    lethal damage, quantity and every original retained-source/ownership check.
    This is analytical fixture data loaded before the native lifecycle starts.
    """
    source = next(item for item in catalog.wargear if item.wargear_id == "core-leader-blade")
    identifier = "analytical:s25-retained-distinct-leader-blade"
    distinct = replace(
        source,
        wargear_id=identifier,
        name="Analytical retained-branch distinct leader blade",
        weapon_profiles=tuple(
            replace(
                profile,
                profile_id=identifier + ":" + str(index),
                strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 99),
                source_ids=(*profile.source_ids, identifier),
            )
            for index, profile in enumerate(source.weapon_profiles)
        ),
    )
    return replace(
        catalog,
        wargear=(*catalog.wargear, distinct),
        datasheets=(
            *catalog.datasheets,
            next(
                replace(
                    sheet,
                    datasheet_id=RETAINED_DISTINCT_LEADER_DATASHEET_ID,
                    wargear_options=tuple(
                        replace(
                            option,
                            default_wargear_ids=tuple(
                                identifier if key == source.wargear_id else key
                                for key in option.default_wargear_ids
                            ),
                            allowed_wargear_ids=tuple(
                                identifier if key == source.wargear_id else key
                                for key in option.allowed_wargear_ids
                            ),
                        )
                        for option in sheet.wargear_options
                    ),
                )
                for sheet in catalog.datasheets
                if sheet.datasheet_id == "core-character-leader"
            ),
        ),
    )
