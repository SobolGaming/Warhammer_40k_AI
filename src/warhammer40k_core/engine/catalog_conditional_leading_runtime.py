from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from warhammer40k_core.core.weapon_profiles import (
    RangeProfile,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_leading_weapon_range_effects,
)
from warhammer40k_core.engine.catalog_datasheet_rule_extensions import (
    CatalogConditionalLeadingFixedAdvanceDescriptor,
    conditional_leading_fixed_advance_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
    CATALOG_IR_WEAPON_RANGE_MODIFIER_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause


@dataclass(frozen=True, slots=True)
class _FixedAdvanceSource:
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    descriptor: CatalogConditionalLeadingFixedAdvanceDescriptor


@dataclass(frozen=True, slots=True)
class CatalogConditionalLeadingRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.ability_indexes_by_player_id), Mapping):
            raise GameLifecycleError("Conditional leading indexes must be a mapping.")
        if type(self.armies) is not tuple or not all(
            type(army) is ArmyDefinition for army in self.armies
        ):
            raise GameLifecycleError("Conditional leading runtime requires armies.")
        player_ids = {army.player_id for army in self.armies}
        if set(self.ability_indexes_by_player_id) != player_ids:
            raise GameLifecycleError("Conditional leading indexes must match armies.")

    def advance_move_bindings(self) -> tuple[AdvanceMoveHookBinding, ...]:
        if not self._has_fixed_advance_records():
            return ()
        return (
            AdvanceMoveHookBinding(
                hook_id=CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
                source_id=CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
                handler=self.fixed_advance_grant,
            ),
        )

    def fixed_advance_grant(self, context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
        if type(context) is not AdvanceMoveContext:
            raise GameLifecycleError("Conditional fixed Advance requires context.")
        if context.movement_phase_action != "advance":
            return None
        sources = self._fixed_advance_sources_for_rules_unit(
            state=context.state,
            rules_unit_instance_id=context.unit_instance_id,
        )
        if not sources:
            return None
        if len(sources) != 1:
            raise GameLifecycleError("Multiple conditional fixed Advance sources are active.")
        source = sources[0]
        descriptor = source.descriptor
        source_rule_id = source.record.definition.source_id
        return AdvanceMoveGrant(
            hook_id=CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
            source_id=CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
            label="Fixed Advance",
            granted_ranged_weapon_keywords=(),
            movement_bonus_inches=descriptor.movement_bonus_inches,
            fixed_advance_inches=descriptor.fixed_advance_inches,
            ignores_vertical_distance=descriptor.ignores_vertical_distance,
            automatic=True,
            replay_payload=validate_json_value(
                {
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source_rule_id,
                    "clause_id": source.clause.clause_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "rules_unit_instance_id": context.unit_instance_id,
                    "fixed_advance_inches": descriptor.fixed_advance_inches,
                    "ignores_vertical_distance": descriptor.ignores_vertical_distance,
                }
            ),
        )

    def weapon_profile_bindings(self) -> tuple[WeaponProfileModifierBinding, ...]:
        return (
            WeaponProfileModifierBinding(
                modifier_id=CATALOG_IR_WEAPON_RANGE_MODIFIER_CONSUMER_ID,
                source_id=CATALOG_IR_WEAPON_RANGE_MODIFIER_CONSUMER_ID,
                handler=self.weapon_range_modifier,
            ),
        )

    def weapon_range_modifier(self, context: WeaponProfileModifierContext) -> WeaponProfile:
        if type(context) is not WeaponProfileModifierContext:
            raise GameLifecycleError("Conditional weapon range modifier requires context.")
        profile = context.weapon_profile
        effects = conditional_leading_weapon_range_effects(
            state=context.state,
            rules_unit_instance_id=context.attacking_unit_instance_id,
        )
        if not effects:
            return profile
        if len(effects) != 1:
            raise GameLifecycleError("Multiple conditional weapon range modifiers are active.")
        payload = effects[0].effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Conditional weapon range payload must be an object.")
        parameters = _effect_parameters(payload)
        if (
            parameters.get("characteristic") != "range"
            or parameters.get("required_weapon_keyword") != "MELTA"
            or parameters.get("target_scope") != "weapons_equipped_by_models_in_leading_unit"
            or parameters.get("delta") != 6
        ):
            raise GameLifecycleError("Conditional weapon range descriptor drift.")
        if (
            WeaponKeyword.MELTA not in profile.keywords
            or profile.range_profile.kind is not RangeProfileKind.DISTANCE
        ):
            return profile
        distance = profile.range_profile.distance_inches
        if distance is None:
            raise GameLifecycleError("Ranged weapon profile distance is missing.")
        source_ids = (
            profile.source_ids
            if effects[0].source_rule_id in profile.source_ids
            else tuple(sorted((*profile.source_ids, effects[0].source_rule_id)))
        )
        return replace(
            profile,
            range_profile=RangeProfile.distance(distance + 6),
            source_ids=source_ids,
        )

    def _has_fixed_advance_records(self) -> bool:
        return any(
            conditional_leading_fixed_advance_descriptor_for_clause(clause) is not None
            for index in self.ability_indexes_by_player_id.values()
            for record in index.all_records()
            if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
            for clause in catalog_rule_clauses_from_record(record)
        )

    def _fixed_advance_sources_for_rules_unit(
        self,
        *,
        state: object,
        rules_unit_instance_id: str,
    ) -> tuple[_FixedAdvanceSource, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Conditional fixed Advance requires GameState.")
        view = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_instance_id)
        if not view.is_attached_rules_unit:
            return ()
        index = self.ability_indexes_by_player_id[view.owner_player_id]
        sources: list[_FixedAdvanceSource] = []
        for component in view.components:
            if component.role not in {"leader", "support"}:
                continue
            unit = component.unit
            current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=state,
                unit=unit,
            )
            if not current_model_ids:
                continue
            for record in index.all_records():
                if (
                    record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID
                    or not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                    )
                ):
                    continue
                for clause in catalog_rule_clauses_from_record(record):
                    descriptor = conditional_leading_fixed_advance_descriptor_for_clause(clause)
                    if descriptor is not None:
                        sources.append(
                            _FixedAdvanceSource(
                                record=record,
                                unit=unit,
                                clause=clause,
                                descriptor=descriptor,
                            )
                        )
        return tuple(
            sorted(
                sources,
                key=lambda source: (
                    source.unit.unit_instance_id,
                    source.record.record_id,
                    source.clause.clause_id,
                ),
            )
        )


def catalog_conditional_leading_advance_move_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AdvanceMoveHookBinding, ...]:
    return CatalogConditionalLeadingRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).advance_move_bindings()


def catalog_conditional_leading_weapon_profile_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[WeaponProfileModifierBinding, ...]:
    return CatalogConditionalLeadingRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).weapon_profile_bindings()


def _effect_parameters(payload: Mapping[str, object]) -> dict[str, object]:
    effect = payload.get("effect")
    if not isinstance(effect, Mapping):
        raise GameLifecycleError("Conditional RuleIR effect is missing.")
    effect_payload = cast(Mapping[str, object], effect)
    raw_parameters = effect_payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Conditional RuleIR effect parameters are malformed.")
    values: dict[str, object] = {}
    for parameter in cast(list[object], raw_parameters):
        if not isinstance(parameter, Mapping):
            raise GameLifecycleError("Conditional RuleIR parameter must be an object.")
        parameter_payload = cast(Mapping[str, object], parameter)
        key = parameter_payload.get("key")
        if type(key) is not str or key in values:
            raise GameLifecycleError("Conditional RuleIR parameter key is invalid.")
        values[key] = parameter_payload.get("value")
    return values
