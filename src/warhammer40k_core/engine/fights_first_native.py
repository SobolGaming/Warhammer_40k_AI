"""Intrinsic Fights First occurrences retain their physical model ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.engine.core_ability_state import core_instance_groups
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.effects import PersistingEffect
    from warhammer40k_core.engine.unit_factory import UnitInstance


@dataclass(frozen=True, slots=True)
class NativeFightsFirstSource:
    effect_id: str
    source_rule_id: str
    unit_instance_id: str
    model_ids: tuple[str, ...]

    def effect_payload(self) -> dict[str, JsonValue]:
        return {
            "effect_kind": "fights_first",
            "source_rule_id": self.source_rule_id,
            "native_model_ids": list(self.model_ids),
        }


def native_fights_first_sources(unit: UnitInstance) -> tuple[NativeFightsFirstSource, ...]:
    occurrences = dict(core_instance_groups(unit)).get(CoreAbilityFamily.FIGHTS_FIRST, ())
    if occurrences:
        return tuple(
            NativeFightsFirstSource(
                f"{source.instance_id}:fights-first",
                source.source_id,
                unit.unit_instance_id,
                tuple(sorted(unit.own_model_ids())),
            )
            for source in occurrences
        )
    # Keywords are model-owned canonical tokens. A unit's keyword union cannot
    # establish that its other models have this ability.
    model_ids = tuple(
        sorted(
            model.model_instance_id for model in unit.own_models if "FIGHTS_FIRST" in model.keywords
        )
    )
    if not model_ids:
        return ()
    from warhammer40k_core.engine.catalog_rule_consumption import CORE_FIGHTS_FIRST_SOURCE_ID

    source_id = CORE_FIGHTS_FIRST_SOURCE_ID
    return (
        NativeFightsFirstSource(
            f"{source_id}:{unit.unit_instance_id}:fights-first",
            source_id,
            unit.unit_instance_id,
            model_ids,
        ),
    )


def validate_native_fights_first_effects(
    *,
    armies: tuple[ArmyDefinition, ...],
    effects: tuple[PersistingEffect, ...],
) -> None:
    """Bind native effect scope to catalog/model authority, including split origins."""
    expected = {
        source.effect_id: source
        for army in armies
        for unit in (
            *(unit for unit in army.units if unit.split_origin is None),
            *(unit for record in army.unit_splits for unit in record.source_units),
        )
        for source in native_fights_first_sources(unit)
    }
    for effect in effects:
        source = expected.get(effect.effect_id)
        payload = effect.effect_payload
        if source is None:
            if isinstance(payload, dict) and "native_model_ids" in payload:
                raise GameLifecycleError("Native Fights First effect has no intrinsic source.")
            continue
        if (
            effect.source_rule_id != source.source_rule_id
            or effect.target_unit_instance_ids != (source.unit_instance_id,)
            or payload != source.effect_payload()
        ):
            raise GameLifecycleError("Native Fights First source scope drift.")
