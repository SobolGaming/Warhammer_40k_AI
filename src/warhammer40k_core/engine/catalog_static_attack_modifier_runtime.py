from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
    ability_record_is_active_generic_rule_ir,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_attack_condition_classification import (
    clause_effect_is_supported_this_model_attack_roll_modifier,
)
from warhammer40k_core.engine.catalog_conditional_leader_abilities import (
    CatalogConditionalLeaderAbilityRuntime,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_current_wargear_bearer_model_ids,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectSpec, RuleIR

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def record_catalog_static_rule_effects(
    *,
    state: GameState,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[PersistingEffect, ...]:
    _require_game_state(state)
    conditional_effects = CatalogConditionalLeaderAbilityRuntime(
        ability_indexes_by_player_id,
        armies,
    ).record_static_effects(state=state)
    attack_effects = CatalogStaticAttackModifierRuntime(
        ability_indexes_by_player_id,
        armies,
    ).record_static_effects(state=state)
    return tuple(
        sorted((*conditional_effects, *attack_effects), key=lambda effect: effect.effect_id)
    )


@dataclass(frozen=True, slots=True)
class _StaticAttackModifierSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    effect: RuleEffectSpec
    effect_index: int
    rule_ir: RuleIR
    source_model_instance_id: str

    @property
    def effect_id(self) -> str:
        return (
            f"{self.rule_ir.source_id}:{self.unit.unit_instance_id}:"
            f"{self.source_model_instance_id}:{self.clause.clause_id}:"
            f"effect:{self.effect_index}:static-attack-modifier"
        )


@dataclass(frozen=True, slots=True)
class CatalogStaticAttackModifierRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if set(indexes) != {army.player_id for army in armies}:
            raise GameLifecycleError("Catalog static attack modifier indexes must match armies.")
        object.__setattr__(self, "ability_indexes_by_player_id", indexes)
        object.__setattr__(self, "armies", armies)

    def record_static_effects(self, *, state: GameState) -> tuple[PersistingEffect, ...]:
        _require_game_state(state)
        effects: list[PersistingEffect] = []
        for source in self._sources():
            effect = _persisting_effect_for_source(state=state, source=source)
            _record_effect_once(state=state, effect=effect)
            effects.append(effect)
        return tuple(sorted(effects, key=lambda effect: effect.effect_id))

    def _sources(self) -> tuple[_StaticAttackModifierSource, ...]:
        sources: list[_StaticAttackModifierSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.all_records():
                if not ability_record_is_active_generic_rule_ir(record):
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                for unit in army.units:
                    current_model_ids = unit.own_model_ids()
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                    ):
                        continue
                    source_model_ids = _source_model_ids(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                    )
                    for clause in catalog_rule_clauses_from_record(record):
                        for effect_index, effect in enumerate(clause.effects):
                            if not clause_effect_is_supported_this_model_attack_roll_modifier(
                                clause,
                                effect,
                            ):
                                continue
                            sources.extend(
                                _StaticAttackModifierSource(
                                    player_id=army.player_id,
                                    record=record,
                                    unit=unit,
                                    clause=clause,
                                    effect=effect,
                                    effect_index=effect_index,
                                    rule_ir=rule_ir,
                                    source_model_instance_id=model_id,
                                )
                                for model_id in source_model_ids
                            )
        return tuple(sorted(sources, key=lambda source: source.effect_id))


def _source_model_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if record.source_kind is not AbilitySourceKind.WARGEAR:
        return current_model_instance_ids
    return catalog_rule_record_current_wargear_bearer_model_ids(
        record=record,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
    )


def _persisting_effect_for_source(
    *,
    state: GameState,
    source: _StaticAttackModifierSource,
) -> PersistingEffect:
    context = RuleExecutionContext(
        game_id=state.game_id,
        player_id=source.player_id,
        battle_round=1,
        phase=None,
        active_player_id=None,
        source_unit_instance_id=source.unit.unit_instance_id,
        source_model_instance_id=source.source_model_instance_id,
        source_keywords=tuple(sorted({*source.unit.keywords, *source.unit.faction_keywords})),
        state=state,
        record_persisting_effects=False,
    )
    payload = generic_rule_effect_payload(
        rule_ir=source.rule_ir,
        clause=source.clause,
        effect=source.effect,
        context=context,
        target_unit_instance_ids=(source.unit.unit_instance_id,),
        effect_index=source.effect_index,
    )
    return generic_rule_persisting_effect(
        effect_id=source.effect_id,
        source_rule_id=source.rule_ir.source_id,
        owner_player_id=source.player_id,
        target_unit_instance_ids=(source.unit.unit_instance_id,),
        started_battle_round=1,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=validate_json_value(payload),
    )


def _record_effect_once(*, state: GameState, effect: PersistingEffect) -> None:
    for existing in state.persisting_effects:
        if existing.effect_id != effect.effect_id:
            continue
        if existing != effect:
            raise GameLifecycleError("Catalog static attack modifier conflicts with state.")
        return
    state.record_persisting_effect(effect)


def _validate_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog static attack modifier indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog static attack modifier index entry is invalid.")
        indexes[player_id] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog static attack modifiers require ArmyDefinition tuple.")
    armies = cast(tuple[object, ...], value)
    if not all(type(army) is ArmyDefinition for army in armies):
        raise GameLifecycleError("Catalog static attack modifiers require ArmyDefinition tuple.")
    resolved = cast(tuple[ArmyDefinition, ...], armies)
    player_ids = tuple(army.player_id for army in resolved)
    if len(set(player_ids)) != len(player_ids):
        raise GameLifecycleError("Catalog static attack modifier armies duplicate player ids.")
    return tuple(sorted(resolved, key=lambda army: army.player_id))


def _require_game_state(value: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(value) is not GameState:
        raise GameLifecycleError("Catalog static attack modifiers require GameState.")
