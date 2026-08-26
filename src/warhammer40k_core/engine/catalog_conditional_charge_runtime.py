from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    ability_record_is_active_generic_rule_ir,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_presence import (
    battlefield_scenario_for_state,
    rules_unit_has_placed_alive_model,
)
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.catalog_conditional_charge_support import (
    CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,
    FriendlyEngagedAnchorChargeSemantic,
    clause_is_friendly_engaged_anchor_charge_reroll,
    clause_is_stratagem_phase_use_exception,
    friendly_engaged_anchor_charge_semantic,
    stratagem_phase_use_exception_semantic,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationHookBinding,
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    scenario_rules_units_are_physically_engaged,
)
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.rule_target_resolution import canonical_keyword
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_display_name,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagem_phase_use_exceptions import (
    PHASE_USE_EXCEPTION_PAYLOAD_KEY,
    StratagemPhaseUseException,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogRecord
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import RuleClause

_CHARGE_EFFECT_KIND = "catalog_ir_friendly_engaged_anchor_charge_reroll"


@dataclass(frozen=True, slots=True)
class _PhaseUseExceptionSource:
    record: AbilityCatalogRecord
    clause: RuleClause
    stratagem_id: str


@dataclass(frozen=True, slots=True)
class _ConditionalChargeSource:
    owner_player_id: str
    record: AbilityCatalogRecord
    clause: RuleClause
    semantic: FriendlyEngagedAnchorChargeSemantic
    source_component_unit_instance_id: str
    anchor_component_unit_instance_id: str
    enemy_component_unit_instance_id: str
    hook_id: str

    def binding(self) -> ChargeDeclarationHookBinding:
        return ChargeDeclarationHookBinding(
            hook_id=self.hook_id,
            source_id=self.record.definition.source_id,
            handler=self.grant,
        )

    def grant(self, context: ChargeDeclarationContext) -> ChargeDeclarationGrant | None:
        if type(context) is not ChargeDeclarationContext:
            raise GameLifecycleError("Catalog conditional Charge requires hook context.")
        if context.player_id != self.owner_player_id:
            return None
        source_view = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=context.unit_instance_id,
        )
        if source_view.owner_player_id != self.owner_player_id:
            return None
        source_component = _component_unit_or_none(
            source_view,
            unit_instance_id=self.source_component_unit_instance_id,
        )
        if source_component is None:
            return None
        current_source_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
            state=context.state,
            unit=source_component,
        )
        if not current_source_model_ids or not catalog_rule_record_source_matches_unit(
            record=self.record,
            unit=source_component,
            current_model_instance_ids=current_source_model_ids,
        ):
            return None
        anchor_view = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=self.anchor_component_unit_instance_id,
        )
        enemy_view = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=self.enemy_component_unit_instance_id,
        )
        if not _candidate_relationships_are_current(
            source_view=source_view,
            anchor_view=anchor_view,
            enemy_view=enemy_view,
            owner_player_id=self.owner_player_id,
        ):
            return None
        if not _component_is_canonical_anchor(
            anchor_view,
            component_unit_instance_id=self.anchor_component_unit_instance_id,
            keyword=self.semantic.anchor_keyword,
        ) or not _component_is_canonical_enemy(
            enemy_view,
            component_unit_instance_id=self.enemy_component_unit_instance_id,
        ):
            return None
        source_models = _placed_alive_geometry_models(context, source_view)
        anchor_models = _placed_alive_geometry_models(context, anchor_view)
        enemy_models = _placed_alive_geometry_models(context, enemy_view)
        if not source_models or not anchor_models or not enemy_models:
            return None
        if _minimum_distance(source_models, anchor_models) > (
            self.semantic.maximum_anchor_distance_inches
        ):
            return None
        if not _models_are_engaged(context, anchor_view, enemy_view):
            return None
        return self._grant_for_current_pair(
            context=context,
            source_view=source_view,
            anchor_view=anchor_view,
            enemy_view=enemy_view,
        )

    def _grant_for_current_pair(
        self,
        *,
        context: ChargeDeclarationContext,
        source_view: RulesUnitView,
        anchor_view: RulesUnitView,
        enemy_view: RulesUnitView,
    ) -> ChargeDeclarationGrant:
        rule_ir = rule_ir_from_execution_payload(self.record.definition.replay_payload)
        source_payload = validate_json_value(
            {
                "effect_kind": _CHARGE_EFFECT_KIND,
                "consumer_id": CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,
                "catalog_record_id": self.record.record_id,
                "ability_id": self.record.definition.ability_id,
                "source_rule_id": self.record.definition.source_id,
                "rule_id": rule_ir.rule_id,
                "rule_ir_hash": rule_ir.ir_hash(),
                "clause_id": self.clause.clause_id,
                "hook_id": self.hook_id,
                "battle_round": context.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "player_id": context.player_id,
                "unit_instance_id": source_view.unit_instance_id,
                "source_component_unit_instance_id": (self.source_component_unit_instance_id),
                "anchor_unit_instance_id": anchor_view.unit_instance_id,
                "anchor_component_unit_instance_id": (self.anchor_component_unit_instance_id),
                "required_enemy_unit_instance_id": enemy_view.unit_instance_id,
                "required_enemy_component_unit_instance_id": (
                    self.enemy_component_unit_instance_id
                ),
                "anchor_keyword": self.semantic.anchor_keyword,
                "maximum_anchor_distance_inches": (self.semantic.maximum_anchor_distance_inches),
                CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: [enemy_view.unit_instance_id],
                "selection_request_id": context.selection_request_id,
                "selection_result_id": context.selection_result_id,
            }
        )
        permission = RerollPermission(
            source_id=(
                f"{self.hook_id}:{source_view.unit_instance_id}:"
                f"round-{context.battle_round:02d}:{context.selection_result_id}"
            ),
            timing_window="after_charge_roll",
            owning_player_id=context.player_id,
            eligible_roll_type=self.semantic.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy(
                self.semantic.component_selection_policy
            ),
        )
        return ChargeDeclarationGrant(
            hook_id=self.hook_id,
            source_id=self.record.definition.source_id,
            label=(
                f"{self.record.definition.name}: {rules_unit_display_name(anchor_view)} / "
                f"{rules_unit_display_name(enemy_view)}"
            ),
            replay_payload=source_payload,
            unit_effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(source_view.unit_instance_id,),
                permission=permission,
                source_payload=source_payload,
            ),
            unit_effect_expiration="end_phase",
        )


def stratagem_records_with_source_backed_phase_use_exceptions(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    stratagem_records: tuple[StratagemCatalogRecord, ...],
) -> tuple[StratagemCatalogRecord, ...]:
    indexes = _validate_ability_indexes(ability_indexes_by_player_id)
    records = _validate_stratagem_records(stratagem_records)
    sources_by_stratagem_id: dict[str, list[_PhaseUseExceptionSource]] = {}
    seen_record_clause_ids: set[tuple[str, str]] = set()
    for index in indexes.values():
        for record in index.all_records():
            if not ability_record_is_active_generic_rule_ir(record):
                continue
            for clause in catalog_rule_clauses_from_record(record):
                if not clause_is_stratagem_phase_use_exception(clause):
                    continue
                key = (record.record_id, clause.clause_id)
                if key in seen_record_clause_ids:
                    continue
                seen_record_clause_ids.add(key)
                semantic = stratagem_phase_use_exception_semantic(clause)
                sources_by_stratagem_id.setdefault(semantic.stratagem_id, []).append(
                    _PhaseUseExceptionSource(
                        record=record,
                        clause=clause,
                        stratagem_id=semantic.stratagem_id,
                    )
                )
    if not sources_by_stratagem_id:
        return records
    available_stratagem_ids = {record.definition.stratagem_id for record in records}
    missing = sorted(set(sources_by_stratagem_id).difference(available_stratagem_ids))
    if missing:
        core_records_by_stratagem_id = {
            record.definition.stratagem_id: record
            for record in eleventh_edition_core_stratagem_catalog_records()
        }
        unavailable = sorted(set(missing).difference(core_records_by_stratagem_id))
        if unavailable:
            raise GameLifecycleError(
                "Source-backed phase-use exception references unavailable Stratagem IDs: "
                + ", ".join(unavailable)
            )
        records = (
            *records,
            *(core_records_by_stratagem_id[stratagem_id] for stratagem_id in missing),
        )
    return tuple(
        _record_with_phase_use_exception(
            record,
            sources=tuple(sources_by_stratagem_id.get(record.definition.stratagem_id, ())),
        )
        for record in records
    )


def catalog_conditional_charge_declaration_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[ChargeDeclarationHookBinding, ...]:
    indexes = _validate_ability_indexes(ability_indexes_by_player_id)
    validated_armies = _validate_armies(armies)
    sources: list[_ConditionalChargeSource] = []
    for army in validated_armies:
        index = indexes.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Catalog conditional Charge is missing ability index.")
        friendly_units = tuple(sorted(army.units, key=lambda unit: unit.unit_instance_id))
        enemy_units = tuple(
            sorted(
                (
                    unit
                    for enemy_army in validated_armies
                    if enemy_army.player_id != army.player_id
                    for unit in enemy_army.units
                ),
                key=lambda unit: unit.unit_instance_id,
            )
        )
        for record in index.all_records():
            if not ability_record_is_active_generic_rule_ir(record):
                continue
            for clause in catalog_rule_clauses_from_record(record):
                if not clause_is_friendly_engaged_anchor_charge_reroll(clause):
                    continue
                semantic = friendly_engaged_anchor_charge_semantic(clause)
                for source_unit in friendly_units:
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=source_unit,
                        current_model_instance_ids=source_unit.own_model_ids(),
                    ):
                        continue
                    for anchor_unit in friendly_units:
                        if anchor_unit.unit_instance_id == source_unit.unit_instance_id:
                            continue
                        for enemy_unit in enemy_units:
                            sources.append(
                                _conditional_charge_source(
                                    owner_player_id=army.player_id,
                                    record=record,
                                    clause=clause,
                                    semantic=semantic,
                                    source_unit=source_unit,
                                    anchor_unit=anchor_unit,
                                    enemy_unit=enemy_unit,
                                )
                            )
    return tuple(source.binding() for source in sorted(sources, key=lambda item: item.hook_id))


def _record_with_phase_use_exception(
    record: StratagemCatalogRecord,
    *,
    sources: tuple[_PhaseUseExceptionSource, ...],
) -> StratagemCatalogRecord:
    if not sources:
        return record
    identities = {
        (source.record.definition.ability_id, source.record.definition.source_id)
        for source in sources
    }
    if len(identities) != 1:
        raise GameLifecycleError(
            "A Stratagem phase-use exception must have one source ability identity."
        )
    source_ability_id, source_id = next(iter(identities))
    eligible_datasheet_ids = tuple(
        sorted(
            {
                source.record.datasheet_id
                for source in sources
                if source.record.datasheet_id is not None
            }
        )
    )
    if not eligible_datasheet_ids:
        raise GameLifecycleError(
            "A Stratagem phase-use exception requires a datasheet-owned source."
        )
    payload = record.definition.effect_payload
    if payload is None:
        merged_payload: dict[str, JsonValue] = {}
    elif isinstance(payload, dict):
        merged_payload = dict(payload)
    else:
        raise GameLifecycleError("Stratagem phase-use exception effect payload must be an object.")
    incoming = StratagemPhaseUseException(
        source_ability_id=source_ability_id,
        source_id=source_id,
        eligible_datasheet_ids=eligible_datasheet_ids,
    )
    existing_payload = merged_payload.get(PHASE_USE_EXCEPTION_PAYLOAD_KEY)
    if existing_payload is not None:
        existing = StratagemPhaseUseException.from_payload(existing_payload)
        if (
            existing.source_ability_id != incoming.source_ability_id
            or existing.source_id != incoming.source_id
        ):
            raise GameLifecycleError("Stratagem phase-use exception source identity drift.")
        incoming = replace(
            incoming,
            eligible_datasheet_ids=tuple(
                sorted({*existing.eligible_datasheet_ids, *incoming.eligible_datasheet_ids})
            ),
        )
    merged_payload[PHASE_USE_EXCEPTION_PAYLOAD_KEY] = incoming.to_payload()
    return replace(
        record,
        definition=replace(
            record.definition,
            effect_payload=validate_json_value(merged_payload),
        ),
    )


def _conditional_charge_source(
    *,
    owner_player_id: str,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    semantic: FriendlyEngagedAnchorChargeSemantic,
    source_unit: UnitInstance,
    anchor_unit: UnitInstance,
    enemy_unit: UnitInstance,
) -> _ConditionalChargeSource:
    digest = hashlib.sha256(
        "\x00".join(
            (
                owner_player_id,
                record.record_id,
                clause.clause_id,
                source_unit.unit_instance_id,
                anchor_unit.unit_instance_id,
                enemy_unit.unit_instance_id,
            )
        ).encode("utf-8")
    ).hexdigest()[:24]
    return _ConditionalChargeSource(
        owner_player_id=owner_player_id,
        record=record,
        clause=clause,
        semantic=semantic,
        source_component_unit_instance_id=source_unit.unit_instance_id,
        anchor_component_unit_instance_id=anchor_unit.unit_instance_id,
        enemy_component_unit_instance_id=enemy_unit.unit_instance_id,
        hook_id=f"{CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID}:{digest}",
    )


def _candidate_relationships_are_current(
    *,
    source_view: RulesUnitView,
    anchor_view: RulesUnitView,
    enemy_view: RulesUnitView,
    owner_player_id: str,
) -> bool:
    return (
        source_view.unit_instance_id != anchor_view.unit_instance_id
        and source_view.owner_player_id == owner_player_id
        and anchor_view.owner_player_id == owner_player_id
        and enemy_view.owner_player_id != owner_player_id
    )


def _component_unit_or_none(
    view: RulesUnitView,
    *,
    unit_instance_id: str,
) -> UnitInstance | None:
    for component in view.components:
        if component.unit.unit_instance_id == unit_instance_id:
            return component.unit
    return None


def _component_is_canonical_anchor(
    view: RulesUnitView,
    *,
    component_unit_instance_id: str,
    keyword: str,
) -> bool:
    required_keyword = canonical_keyword(keyword)
    matching_component_ids = tuple(
        sorted(
            component.unit.unit_instance_id
            for component in view.keyword_contributing_components
            if required_keyword
            in {
                canonical_keyword(value)
                for value in (*component.unit.keywords, *component.unit.faction_keywords)
            }
        )
    )
    return bool(matching_component_ids) and component_unit_instance_id == matching_component_ids[0]


def _component_is_canonical_enemy(
    view: RulesUnitView,
    *,
    component_unit_instance_id: str,
) -> bool:
    current_component_ids = tuple(
        sorted(
            component.unit.unit_instance_id
            for component in view.components
            if any(model.is_alive for model in component.unit.own_models)
        )
    )
    return bool(current_component_ids) and component_unit_instance_id == current_component_ids[0]


def _placed_alive_geometry_models(
    context: ChargeDeclarationContext,
    view: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Catalog conditional Charge requires battlefield_state.")
    models: list[GeometryModel] = []
    for model in view.alive_models():
        placement = battlefield.model_placement_or_none(model.model_instance_id)
        if placement is None:
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def _minimum_distance(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> float:
    if not first_models or not second_models:
        raise GameLifecycleError("Catalog conditional Charge distance requires model groups.")
    return min(first.range_to(second) for first in first_models for second in second_models)


def _models_are_engaged(
    context: ChargeDeclarationContext,
    first_view: RulesUnitView,
    second_view: RulesUnitView,
) -> bool:
    if not rules_unit_has_placed_alive_model(
        state=context.state,
        rules_unit=first_view,
    ) or not rules_unit_has_placed_alive_model(
        state=context.state,
        rules_unit=second_view,
    ):
        return False
    return scenario_rules_units_are_physically_engaged(
        scenario=battlefield_scenario_for_state(state=context.state),
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        first_unit_instance_id=first_view.unit_instance_id,
        second_unit_instance_id=second_view.unit_instance_id,
    )


def _validate_ability_indexes(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog conditional Charge requires ability indexes.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or not player_id.strip():
            raise GameLifecycleError("Catalog conditional Charge player ID is invalid.")
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog conditional Charge ability index is invalid.")
        indexes[player_id.strip()] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog conditional Charge requires army tuple.")
    armies: list[ArmyDefinition] = []
    seen_player_ids: set[str] = set()
    for army in cast(tuple[object, ...], value):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog conditional Charge requires ArmyDefinition values.")
        if army.player_id in seen_player_ids:
            raise GameLifecycleError("Catalog conditional Charge player armies must be unique.")
        seen_player_ids.add(army.player_id)
        armies.append(army)
    return tuple(sorted(armies, key=lambda army: army.player_id))


def _validate_stratagem_records(value: object) -> tuple[StratagemCatalogRecord, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Phase-use exception requires Stratagem record tuple.")
    records: list[StratagemCatalogRecord] = []
    for record in cast(tuple[object, ...], value):
        if type(record) is not StratagemCatalogRecord:
            raise GameLifecycleError("Phase-use exception requires StratagemCatalogRecord values.")
        records.append(record)
    return tuple(records)
