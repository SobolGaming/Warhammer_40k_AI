from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityExecutionContext,
    AbilitySourceKind,
    ability_record_is_active_generic_rule_ir,
    ability_records_for_context,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import RulesUnitView


CATALOG_IR_MODIFIER_IGNORE_PERMISSION_CONSUMER_ID = "catalog-ir:modifier-ignore-permission"


class ModifierIgnoreKind(StrEnum):
    MOVEMENT_CHARACTERISTIC = "movement_characteristic"
    ADVANCE_ROLL = "advance_roll"
    CHARGE_ROLL = "charge_roll"
    DESPERATE_ESCAPE_ROLL = "desperate_escape_roll"
    HEALING_ROLL = "healing_roll"
    TOUGHNESS_CHARACTERISTIC = "toughness_characteristic"
    SAVE_CHARACTERISTIC = "save_characteristic"
    INVULNERABLE_SAVE_CHARACTERISTIC = "invulnerable_save_characteristic"
    WOUNDS_CHARACTERISTIC = "wounds_characteristic"
    LEADERSHIP_CHARACTERISTIC = "leadership_characteristic"
    OBJECTIVE_CONTROL_CHARACTERISTIC = "objective_control_characteristic"
    BALLISTIC_SKILL_CHARACTERISTIC = "ballistic_skill_characteristic"
    WEAPON_SKILL_CHARACTERISTIC = "weapon_skill_characteristic"
    STRENGTH_CHARACTERISTIC = "strength_characteristic"
    ARMOR_PENETRATION_CHARACTERISTIC = "armor_penetration_characteristic"
    ATTACKS_CHARACTERISTIC = "attacks_characteristic"
    DAMAGE_CHARACTERISTIC = "damage_characteristic"
    RANGE_CHARACTERISTIC = "range_characteristic"
    HIT_ROLL = "hit_roll"
    WOUND_ROLL = "wound_roll"
    SAVE_ROLL = "save_roll"
    DAMAGE_ROLL = "damage_roll"
    LEADERSHIP_ROLL = "leadership_roll"
    BATTLE_SHOCK_ROLL = "battle_shock_roll"


@dataclass(frozen=True, slots=True)
class CatalogModifierIgnorePermission:
    permission_id: str
    record_id: str
    source_id: str
    rule_ir_hash: str
    clause_id: str
    modifier_kinds: tuple[ModifierIgnoreKind, ...]
    source_context: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "permission_id",
            _validate_identifier("modifier-ignore permission_id", self.permission_id),
        )
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("modifier-ignore record_id", self.record_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("modifier-ignore source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "rule_ir_hash",
            _validate_identifier("modifier-ignore rule_ir_hash", self.rule_ir_hash),
        )
        object.__setattr__(
            self,
            "clause_id",
            _validate_identifier("modifier-ignore clause_id", self.clause_id),
        )
        if type(self.modifier_kinds) is not tuple or not self.modifier_kinds:
            raise GameLifecycleError("Modifier-ignore permission requires modifier kinds.")
        kinds = tuple(ModifierIgnoreKind(kind) for kind in self.modifier_kinds)
        if len(set(kinds)) != len(kinds):
            raise GameLifecycleError("Modifier-ignore permission kinds must be unique.")
        object.__setattr__(self, "modifier_kinds", tuple(sorted(kinds, key=str)))
        context = validate_json_value(self.source_context)
        if context is not None and not isinstance(context, dict):
            raise GameLifecycleError("Modifier-ignore source context requires an object.")
        object.__setattr__(self, "source_context", context)

    def supports(self, kind: ModifierIgnoreKind) -> bool:
        if type(kind) is not ModifierIgnoreKind:
            raise GameLifecycleError("Modifier-ignore query requires a typed kind.")
        return kind in self.modifier_kinds

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "permission_id": self.permission_id,
            "record_id": self.record_id,
            "source_id": self.source_id,
            "rule_ir_hash": self.rule_ir_hash,
            "clause_id": self.clause_id,
            "modifier_kinds": [kind.value for kind in self.modifier_kinds],
        }
        if self.source_context is not None:
            payload["source_context"] = self.source_context
        return payload


def clause_is_modifier_ignore_permission(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Modifier-ignore classification requires RuleClause.")
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.conditions
        or clause.target is None
        or clause.target.kind not in {RuleTargetKind.THIS_MODEL, RuleTargetKind.THIS_UNIT}
        or clause.target.parameters
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.WHILE_CONDITION_TRUE
        or clause.duration.parameters
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    raw_kinds = parameters.get("modifier_kinds", tuple(kind.value for kind in ModifierIgnoreKind))
    if type(raw_kinds) is not tuple or not raw_kinds:
        return False
    if any(type(value) is not str for value in raw_kinds):
        return False
    try:
        kinds = tuple(ModifierIgnoreKind(value) for value in raw_kinds)
    except (TypeError, ValueError):  # fmt: skip
        return False
    expected: dict[str, object] = {
        "ability": "modifier_ignore_permission",
        "selection": "any_or_all",
    }
    if "modifier_kinds" in parameters:
        expected["modifier_kinds"] = raw_kinds
    return len(set(kinds)) == len(kinds) and parameters == expected


def catalog_modifier_ignore_permissions_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[CatalogModifierIgnorePermission, ...]:
    if type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Modifier-ignore query requires AbilityCatalogIndex.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Modifier-ignore query requires UnitInstance.")
    current_ids = _validate_identifier_tuple(
        "modifier-ignore current_model_instance_ids",
        current_model_instance_ids,
    )
    from warhammer40k_core.engine.catalog_rule_consumption import (
        catalog_rule_clauses_from_record,
        catalog_rule_record_source_matches_unit,
    )
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    permissions: list[CatalogModifierIgnorePermission] = []
    for record in ability_index.all_records():
        if not ability_record_is_active_generic_rule_ir(record):
            continue
        if not catalog_rule_record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_ids,
        ):
            continue
        rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
        for clause in catalog_rule_clauses_from_record(record):
            if not clause_is_modifier_ignore_permission(clause):
                continue
            raw_kinds = parameter_payload(clause.effects[0].parameters).get(
                "modifier_kinds", tuple(kind.value for kind in ModifierIgnoreKind)
            )
            if type(raw_kinds) is not tuple or any(type(value) is not str for value in raw_kinds):
                raise GameLifecycleError("Modifier-ignore permission kind payload drifted.")
            kinds = tuple(ModifierIgnoreKind(value) for value in raw_kinds)
            permissions.append(
                CatalogModifierIgnorePermission(
                    permission_id=f"{rule_ir.source_id}:{clause.clause_id}:modifier-ignore",
                    record_id=record.record_id,
                    source_id=rule_ir.source_id,
                    rule_ir_hash=rule_ir.ir_hash(),
                    clause_id=clause.clause_id,
                    modifier_kinds=kinds,
                )
            )
    return tuple(sorted(permissions, key=lambda permission: permission.permission_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)


def modifier_ignore_permission_candidates_present(
    *, state: GameState, ability_indexes: tuple[AbilityCatalogIndex, ...]
) -> bool:
    """Conservative source probe before a whole-army subject search.

    This grants no permission and caches no mutable source state. Any persisted
    generic effect remains a candidate so malformed or restricted grants still
    reach the existing strict applicability owner. Catalog candidates use the
    same supported-clause classifier as the full permission query.
    """
    from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
    from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND
    from warhammer40k_core.engine.game_state import GameState

    if (
        type(state) is not GameState
        or type(ability_indexes) is not tuple
        or any(type(index) is not AbilityCatalogIndex for index in ability_indexes)
    ):
        raise GameLifecycleError("Modifier-ignore candidates require state and ability indexes.")
    if any(
        isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == GENERIC_RULE_EFFECT_KIND
        for effect in state.persisting_effects
    ):
        return True
    return any(
        clause_is_modifier_ignore_permission(clause)
        for index in ability_indexes
        for record in index.all_records()
        if ability_record_is_active_generic_rule_ir(record)
        for clause in catalog_rule_clauses_from_record(record)
    )


def modifier_ignore_permissions_for_subject(
    *,
    state: GameState,
    ability_index: AbilityCatalogIndex,
    unit_instance_id: str,
    kind: ModifierIgnoreKind,
    model_instance_id: str | None = None,
    weapon_profile_id: str | None = None,
) -> tuple[CatalogModifierIgnorePermission, ...]:
    """Resolve current permission sources without granting physical weapon authority.

    The calling operation owns the selected profile's equipped-weapon/AttackPool
    validation. This query additionally enforces every source record's model,
    wargear and profile constraint against that authenticated subject.
    """
    from warhammer40k_core.engine.ability_presence import ability_presence
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if type(state) is not GameState or type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Modifier-ignore subject query requires state and ability index.")
    if type(kind) is not ModifierIgnoreKind:
        raise GameLifecycleError("Modifier-ignore query requires a typed kind.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    model_id = (
        None
        if model_instance_id is None
        else _validate_identifier("model_instance_id", model_instance_id)
    )
    profile_id = (
        None
        if weapon_profile_id is None
        else _validate_identifier("weapon_profile_id", weapon_profile_id)
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if model_id is not None:
        component_id = view.component_unit_id_for_model(model_id)
        if requested_unit_id not in {view.unit_instance_id, component_id}:
            raise GameLifecycleError("Modifier-ignore subject model has wrong component owner.")
    if profile_id is not None and model_id is None:
        raise GameLifecycleError("Modifier-ignore weapon subject requires its model owner.")
    current_ids = ability_presence(state=state, rules_unit=view).active_model_ids
    if not current_ids or (model_id is not None and model_id not in current_ids):
        return ()
    subject_context: dict[str, JsonValue] = {
        "subject_unit_instance_id": view.unit_instance_id,
        "subject_component_unit_instance_id": requested_unit_id,
        "subject_model_instance_id": model_id,
        "subject_weapon_profile_id": profile_id,
        "subject_kind": kind.value,
    }
    permissions = _catalog_subject_permissions(
        state=state,
        ability_index=ability_index,
        view=view,
        current_ids=current_ids,
        model_id=model_id,
        profile_id=profile_id,
        kind=kind,
        subject_context=subject_context,
    )
    permissions.extend(
        _persisted_subject_permissions(
            state=state,
            view=view,
            current_ids=current_ids,
            model_id=model_id,
            profile_id=profile_id,
            kind=kind,
            subject_context=subject_context,
        )
    )
    return tuple(sorted(permissions, key=lambda permission: permission.permission_id))


def _catalog_subject_permissions(
    *,
    state: GameState,
    ability_index: AbilityCatalogIndex,
    view: RulesUnitView,
    current_ids: tuple[str, ...],
    model_id: str | None,
    profile_id: str | None,
    kind: ModifierIgnoreKind,
    subject_context: dict[str, JsonValue],
) -> list[CatalogModifierIgnorePermission]:
    from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    permissions: list[CatalogModifierIgnorePermission] = []
    for component in view.components:
        source_unit = component.unit
        source_ids = tuple(
            model.model_instance_id
            for model in source_unit.own_models
            if model.model_instance_id in current_ids
        )
        if not source_ids:
            continue
        for record in ability_index.all_records():
            if not ability_record_is_active_generic_rule_ir(record):
                continue
            bearer_ids = _source_bearer_ids(
                record=record,
                unit=source_unit,
                current_ids=source_ids,
                profile_id=profile_id,
            )
            if not bearer_ids or (
                record.source_kind is AbilitySourceKind.WEAPON and model_id not in bearer_ids
            ):
                continue
            rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
            for clause in catalog_rule_clauses_from_record(record):
                if not clause_is_modifier_ignore_permission(clause):
                    continue
                kinds = _permission_kinds(parameter_payload(clause.effects[0].parameters))
                if kind not in kinds:
                    continue
                assert clause.target is not None
                model_scope = clause.target.kind is RuleTargetKind.THIS_MODEL
                applicable_bearers = tuple(
                    source_id
                    for source_id in bearer_ids
                    if (
                        not model_scope
                        or source_id == model_id
                        or (model_id is None and current_ids == (source_id,))
                    )
                )
                eligible_bearers = tuple(
                    source_id
                    for source_id in applicable_bearers
                    if ability_records_for_context(
                        records=(record,),
                        context=AbilityExecutionContext(
                            game_id=state.game_id,
                            player_id=view.owner_player_id,
                            battle_round=state.battle_round,
                            phase=state.current_battle_phase,
                            active_player_id=state.active_player_id,
                            trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
                            source_unit_instance_id=source_unit.unit_instance_id,
                            source_model_instance_id=source_id,
                            source_keywords=(
                                source_unit.own_model_by_id(source_id).keywords
                                if model_scope
                                else view.keywords
                            ),
                            state=state,
                        ),
                    )
                )
                if not eligible_bearers:
                    continue
                source_model_id = eligible_bearers[0] if model_scope else None
                permission_id = (
                    f"{record.record_id}:{clause.clause_id}:{source_unit.unit_instance_id}:"
                    f"{source_model_id if source_model_id is not None else 'unit'}:modifier-ignore"
                )
                permissions.append(
                    CatalogModifierIgnorePermission(
                        permission_id=permission_id,
                        record_id=record.record_id,
                        source_id=rule_ir.source_id,
                        rule_ir_hash=rule_ir.ir_hash(),
                        clause_id=clause.clause_id,
                        modifier_kinds=kinds,
                        source_context={
                            **subject_context,
                            "source_kind": "catalog",
                            "source_unit_instance_id": source_unit.unit_instance_id,
                            "source_model_instance_id": source_model_id,
                            "source_wargear_id": record.wargear_id,
                            "source_weapon_profile_id": record.weapon_profile_id,
                            "source_target_kind": clause.target.kind.value,
                            "eligible_source_model_ids": list(eligible_bearers),
                        },
                    )
                )
    return permissions


def _source_bearer_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_ids: tuple[str, ...],
    profile_id: str | None,
) -> tuple[str, ...]:
    if record.source_kind not in {
        AbilitySourceKind.DATASHEET,
        AbilitySourceKind.WARGEAR,
        AbilitySourceKind.WEAPON,
    }:
        return ()
    if record.datasheet_id is not None and record.datasheet_id != unit.datasheet_id:
        return ()
    if record.weapon_profile_id is not None and record.weapon_profile_id != profile_id:
        return ()
    if record.source_kind is AbilitySourceKind.WEAPON and (
        record.weapon_profile_id is None or record.wargear_id is None
    ):
        return ()
    if record.wargear_id is None:
        return current_ids
    return tuple(
        model.model_instance_id
        for model in unit.own_models
        if model.model_instance_id in current_ids and record.wargear_id in model.wargear_ids
    )


def _permission_kinds(parameters: Mapping[str, object]) -> tuple[ModifierIgnoreKind, ...]:
    raw_kinds = parameters.get("modifier_kinds")
    if "modifier_kinds" not in parameters:
        return tuple(ModifierIgnoreKind)
    if type(raw_kinds) not in {tuple, list} or not raw_kinds:
        raise GameLifecycleError("Modifier-ignore permission kinds must be a non-empty sequence.")
    values = cast(tuple[object, ...] | list[object], raw_kinds)
    if any(type(value) is not str for value in values):
        raise GameLifecycleError("Modifier-ignore permission kinds must contain string tokens.")
    try:
        kinds = tuple(ModifierIgnoreKind(cast(str, value)) for value in values)
    except ValueError as exc:
        raise GameLifecycleError("Modifier-ignore permission has an unsupported kind.") from exc
    if len(kinds) != len(set(kinds)):
        raise GameLifecycleError("Modifier-ignore permission kinds must be unique.")
    return kinds


def _persisted_subject_permissions(
    *,
    state: GameState,
    view: RulesUnitView,
    current_ids: tuple[str, ...],
    model_id: str | None,
    profile_id: str | None,
    kind: ModifierIgnoreKind,
    subject_context: dict[str, JsonValue],
) -> list[CatalogModifierIgnorePermission]:
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_effect_context_applies,
        generic_rule_matching_unit_effects,
    )

    permissions: list[CatalogModifierIgnorePermission] = []
    for effect in generic_rule_matching_unit_effects(
        state=state,
        unit_instance_id=view.unit_instance_id,
        effect_kind=RuleEffectKind.GRANT_ABILITY,
    ):
        if effect.parameters.get("ability") != "modifier_ignore_permission":
            continue
        if effect.target_kind not in {
            RuleTargetKind.THIS_MODEL,
            RuleTargetKind.THIS_UNIT,
            RuleTargetKind.SELECTED_UNIT,
            RuleTargetKind.FRIENDLY_UNIT,
            RuleTargetKind.AURA_UNITS,
        }:
            raise GameLifecycleError("Persisted modifier-ignore subject scope is unsupported.")
        if effect.parameters.get("selection") != "any_or_all":
            raise GameLifecycleError("Persisted modifier-ignore selection is unsupported.")
        kinds = _permission_kinds(dict(effect.parameters))
        if kind not in kinds:
            continue
        if effect.persisting_effect.source_rule_id != effect.source_id:
            raise GameLifecycleError("Persisted modifier-ignore source identity drift.")
        if effect.target_kind is RuleTargetKind.THIS_MODEL:
            if effect.source_model_instance_id is None:
                raise GameLifecycleError("Persisted THIS_MODEL permission requires source model.")
            if effect.source_model_instance_id not in current_ids:
                continue
            if effect.source_model_instance_id != model_id and (
                model_id is not None or current_ids != (effect.source_model_instance_id,)
            ):
                continue
        if any(
            condition.get("kind") != RuleConditionKind.TARGET_CONSTRAINT.value
            for condition in effect.conditions
        ):
            raise GameLifecycleError("Persisted modifier-ignore condition kind is unsupported.")
        supported_keys = {
            "ability",
            "selection",
            "modifier_kinds",
            "source_phase",
            "required_keyword",
            "required_keyword_sequence",
            "target_constraint",
            "attack_role",
            "ability_required",
            "requires_charge_move_this_turn",
            "target_required_keyword",
            "selected_target_unit_instance_id",
            "target_allegiance",
            "attacker_scope",
        }
        if set(effect.parameters) - supported_keys:
            raise GameLifecycleError("Persisted modifier-ignore restriction is unsupported.")
        if not generic_effect_context_applies(
            state=state,
            effect=effect,
            attacking_unit_instance_id=view.unit_instance_id,
            attacker_model_instance_id=(
                current_ids[0] if model_id is None and len(current_ids) == 1 else model_id
            ),
            target_unit_instance_id=None,
            source_phase=state.current_battle_phase,
            weapon_profile=None,
            attack_strength=None,
            target_toughness=None,
        ):
            continue
        permissions.append(
            CatalogModifierIgnorePermission(
                permission_id=f"{effect.persisting_effect.effect_id}:modifier-ignore",
                record_id=effect.persisting_effect.effect_id,
                source_id=effect.source_id,
                rule_ir_hash=effect.rule_ir_hash,
                clause_id=effect.clause_id,
                modifier_kinds=kinds,
                source_context={
                    **subject_context,
                    "source_kind": "persisting_effect",
                    "source_model_instance_id": effect.source_model_instance_id,
                    "source_target_kind": None
                    if effect.target_kind is None
                    else effect.target_kind.value,
                    "persisting_effect": validate_json_value(effect.persisting_effect.to_payload()),
                },
            )
        )
    return permissions
