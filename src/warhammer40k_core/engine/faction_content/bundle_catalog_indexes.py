from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilityCatalogRecord
from warhammer40k_core.engine.ability_catalog import build_player_ability_index
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.stratagem_catalog import build_player_stratagem_index
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemCatalogRecord


def ability_indexes_by_player_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    catalog: ArmyCatalog,
    records: tuple[AbilityCatalogRecord, ...],
) -> Mapping[str, AbilityCatalogIndex]:
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return MappingProxyType(indexes)


def stratagem_indexes_by_player_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    catalog: ArmyCatalog,
    records: tuple[StratagemCatalogRecord, ...],
) -> Mapping[str, StratagemCatalogIndex]:
    indexes = {
        army.player_id: build_player_stratagem_index(
            records,
            detachment_ids=army.detachment_selection.detachment_ids,
            stratagem_ids=_selected_stratagem_ids_for_army(army=army, catalog=catalog),
        )
        for army in armies
    }
    return MappingProxyType(indexes)


def _selected_stratagem_ids_for_army(
    *,
    army: ArmyDefinition,
    catalog: ArmyCatalog,
) -> tuple[str, ...]:
    selected: set[str] = set(army.detachment_selection.stratagem_ids)
    selected_detachment_ids = set(army.detachment_selection.detachment_ids)
    for detachment in catalog.detachments:
        if detachment.detachment_id in selected_detachment_ids:
            selected.update(detachment.stratagem_ids)
    return tuple(sorted(selected))


__all__ = ("ability_indexes_by_player_id", "stratagem_indexes_by_player_id")
