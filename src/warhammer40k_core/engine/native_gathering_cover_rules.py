"""Compare actual Cover grants while retaining each observer's causal witness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.engine.catalog_cover_grants import catalog_cover_inventory
from warhammer40k_core.engine.core_stratagem_effects import unit_effects_grant_benefit_of_cover
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_inventories
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.shooting_targets import BENEFIT_OF_COVER_RULE_ID
from warhammer40k_core.engine.stealth import rules_unit_stealth_sources
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_gnarlmaw_2026_11 as gnarlmaw,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


@dataclass(frozen=True, slots=True)
class AllocationCoverSourceBinding:
    catalog_id: str
    datasheet_id: str
    convention_id: str
    matches_ability: Callable[[DatasheetAbilityDescriptor], bool]


@cache
def approved_allocation_cover_bindings() -> tuple[AllocationCoverSourceBinding, ...]:
    return (
        AllocationCoverSourceBinding(
            gnarlmaw.CATALOG_ID,
            gnarlmaw.DATASHEET_ID,
            gnarlmaw.DISEASED_COVER_CONVENTION_ID,
            gnarlmaw.is_reviewed_diseased_cover,
        ),
    )


def allocation_cover_bindings_by_model(
    armies: tuple[ArmyDefinition, ...],
    bindings: tuple[AllocationCoverSourceBinding, ...],
) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for binding in bindings:
        for army in armies:
            if army.catalog_id != binding.catalog_id:
                continue
            for unit in army.units:
                if unit.datasheet_id != binding.datasheet_id:
                    continue
                for ability in unit.datasheet_abilities:
                    if not binding.matches_ability(ability):
                        continue
                    payload = ability.rule_ir_payload
                    source_id = None if payload is None else payload.get("source_id")
                    if not isinstance(source_id, str):
                        raise GameLifecycleError(
                            "Approved allocation cover requires a RuleIR source ID."
                        )
                    for model in unit.own_models:
                        if not model.is_alive:
                            continue
                        if model.model_instance_id in result:
                            raise GameLifecycleError(
                                "Multiple approved cover bindings claim one model."
                            )
                        result[model.model_instance_id] = binding.convention_id, source_id
    return result


def allocation_cover_provenance(
    bindings_by_model: dict[str, tuple[str, str]],
    source_ids: frozenset[str],
    candidate_ids: set[str],
) -> dict[str, JsonValue]:
    by_binding: dict[tuple[str, str], list[str]] = {}
    for model_id in sorted(source_ids):
        by_binding.setdefault(bindings_by_model[model_id], []).append(model_id)
    records: list[dict[str, JsonValue]] = [
        {
            "convention_id": convention,
            "source_ability_id": source_id,
            "source_model_ids": list(models),
        }
        for (convention, source_id), models in sorted(by_binding.items())
    ]
    candidates = cast(list[JsonValue], sorted(candidate_ids))
    if len(records) == 1:
        return {**records[0], "allocation_candidate_model_ids": candidates}
    return {
        "approved_sources": list(records),
        "allocation_candidate_model_ids": candidates,
    }


def cover_gathering_inventories(
    *, state: GameState, pool: RangedAttackPool, registry: RuntimeModifierRegistry
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    from warhammer40k_core.engine.attack_sequence_hazardous import approved_pre_hit_cover_sources

    raw, applicable = obscuring_model_cover_inventories(state=state, pool=pool)
    gnarlmaw_cover = approved_pre_hit_cover_sources(
        state=state, pool=pool, runtime_modifier_registry=registry, gathering_preview=True
    )
    common = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                **catalog_cover_inventory(
                    state=state,
                    target_unit_instance_id=pool.target_unit_instance_id,
                    runtime_modifier_registry=registry,
                ),
                **(
                    {"gnarlmaw_diseased_cover": gnarlmaw_cover}
                    if gnarlmaw_cover is not None
                    else {}
                ),
                "effects": [
                    effect.to_payload()
                    for effect in state.persisting_effects_for_unit(pool.target_unit_instance_id)
                    if unit_effects_grant_benefit_of_cover((effect,))
                ],
                "stealth": rules_unit_stealth_sources(
                    state=state,
                    target_unit_instance_id=pool.target_unit_instance_id,
                    runtime_modifier_registry=registry,
                ),
            }
        ),
    )
    return {**common, "obscuring_models": raw}, {**common, "obscuring_models": applicable}


def compare_cover_modifier(
    rules: dict[str, JsonValue], *, raw: dict[str, JsonValue], applicable: dict[str, JsonValue]
) -> None:
    """Normalize only the exact Cover ID generated from this current owner inventory."""
    expected = BENEFIT_OF_COVER_RULE_ID + ":" + sha256(canonical_json(raw).encode()).hexdigest()
    replacement = (
        BENEFIT_OF_COVER_RULE_ID + ":" + sha256(canonical_json(applicable).encode()).hexdigest()
    )
    for item in cast(list[dict[str, JsonValue]], rules["hit_modifiers"]):
        modifier = cast(dict[str, JsonValue], item["modifier"])
        if (
            item["kind"] == "skill"
            and modifier["source_id"] == BENEFIT_OF_COVER_RULE_ID
            and modifier["modifier_id"] == expected
        ):
            modifier["modifier_id"] = replacement
