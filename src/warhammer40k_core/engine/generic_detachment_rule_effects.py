from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationHookBinding,
    BattleFormationRequestContext,
    BattleFormationRequestHandler,
)
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.fight_order import FIGHTS_FIRST_EFFECT_KIND
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_more_dakka_ir_support_2026_27 as more_dakka_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_spectacle_of_slaughter_ir_support_2026_27 as spectacle_ir,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord

MORE_DAKKA_DETACHMENT_ID = "more-dakka"
MORE_DAKKA_FACTION_KEYWORD = "ORKS"
MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID = more_dakka_ir.MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID
SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID = (
    spectacle_ir.SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID
)
SPECTACLE_OF_SLAUGHTER_UNIT_KEYWORD = spectacle_ir.FLAWLESS_BLADES_KEYWORD
COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID = (
    court_ir.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID
)
COURT_OF_THE_PHOENICIAN_FACTION_KEYWORD = court_ir.EMPERORS_CHILDREN_KEYWORD
SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID = (
    shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
)
SHADOW_LEGION_KEYWORD = shadow_legion_ir.SHADOW_LEGION_KEYWORD
_BATTLE_FORMATION_DETACHMENT_RULE_DESCRIPTOR_IDS = frozenset(
    {
        MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID,
        SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID,
        COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID,
        SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
    }
)


@dataclass(frozen=True, slots=True)
class _GenericDetachmentRuleBindingSource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic detachment binding requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic detachment binding requires RuleIR.")
        if self.record.rule_ir_hash is None:
            raise GameLifecycleError("Generic detachment record requires rule_ir_hash.")
        if self.rule_ir.ir_hash() != self.record.rule_ir_hash:
            raise GameLifecycleError("Generic detachment execution record has stale RuleIR hash.")


def generic_detachment_rule_battle_formation_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[BattleFormationHookBinding, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic detachment bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic detachment bindings require execution records.")
    selected_detachment_ids = set(activation.selected_detachment_ids)
    bindings: list[BattleFormationHookBinding] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic detachment bindings require execution records.")
        if not _record_is_generic_detachment_rule(record):
            continue
        if record.coverage_descriptor_id not in _BATTLE_FORMATION_DETACHMENT_RULE_DESCRIPTOR_IDS:
            continue
        if record.detachment_id not in selected_detachment_ids:
            continue
        rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
            record.coverage_descriptor_id
        )
        source = _GenericDetachmentRuleBindingSource(record=record, rule_ir=rule_ir)
        bindings.append(
            BattleFormationHookBinding(
                hook_id=f"{record.execution_id}:battle-formation",
                source_id=rule_ir.source_id,
                request_handler=_handler_for_source(source),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def battle_formation_hook_bindings(
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[BattleFormationHookBinding, ...]:
    return generic_detachment_rule_battle_formation_hook_bindings(
        activation=activation,
        execution_records=execution_records,
    )


def _handler_for_source(
    binding_source: _GenericDetachmentRuleBindingSource,
) -> BattleFormationRequestHandler:
    def handler(context: BattleFormationRequestContext) -> None:
        _apply_generic_detachment_rule_effects(
            context=context,
            binding_source=binding_source,
        )
        return

    return handler


def _apply_generic_detachment_rule_effects(
    *,
    context: BattleFormationRequestContext,
    binding_source: _GenericDetachmentRuleBindingSource,
) -> None:
    if type(context) is not BattleFormationRequestContext:
        raise GameLifecycleError("Generic detachment effects require request context.")
    if type(binding_source) is not _GenericDetachmentRuleBindingSource:
        raise GameLifecycleError("Generic detachment effects require binding source.")
    applied_payloads: list[JsonValue] = []
    for army in context.state.army_definitions:
        if not _army_uses_record(army=army, record=binding_source.record):
            continue
        target_unit_ids = _target_unit_ids_for_record(
            record=binding_source.record,
            army=army,
        )
        if not target_unit_ids:
            continue
        expected_ids = _expected_effect_ids(
            record=binding_source.record,
            rule_ir=binding_source.rule_ir,
            player_id=army.player_id,
        )
        existing_ids = {effect.effect_id for effect in context.state.persisting_effects}
        already_installed = tuple(
            effect_id for effect_id in expected_ids if effect_id in existing_ids
        )
        if len(already_installed) == len(expected_ids):
            continue
        if already_installed:
            raise GameLifecycleError("Generic detachment effects are partially installed.")
        result = execute_rule_ir(
            rule_ir=binding_source.rule_ir,
            context=RuleExecutionContext(
                game_id=context.state.game_id,
                player_id=army.player_id,
                battle_round=max(1, context.state.battle_round),
                phase=context.state.current_battle_phase,
                active_player_id=context.state.active_player_id,
                source_unit_instance_id=target_unit_ids[0],
                target_unit_instance_ids=target_unit_ids,
                target_player_id=army.player_id,
                trigger_payload={
                    "event": "detachment_rule_setup",
                    "detachment_id": binding_source.record.detachment_id,
                    "coverage_descriptor_id": binding_source.record.coverage_descriptor_id,
                },
                state=context.state,
                event_log=context.decisions.event_log,
                record_persisting_effects=False,
            ),
        )
        if result.status is not RuleExecutionStatus.APPLIED:
            if result.reason is None:
                raise GameLifecycleError("Generic detachment RuleIR failed without reason.")
            raise GameLifecycleError(f"Generic detachment RuleIR failed: {result.reason}.")
        if len(result.effect_payloads) != len(expected_ids):
            raise GameLifecycleError("Generic detachment RuleIR produced unexpected effects.")
        for effect_payload in result.effect_payloads:
            clause_id = _payload_string(effect_payload, "clause_id")
            effect_id = _detachment_effect_id(
                record=binding_source.record,
                rule_ir=binding_source.rule_ir,
                player_id=army.player_id,
                clause_id=clause_id,
            )
            effect = _persisting_effect_for_detachment_payload(
                effect_id=effect_id,
                source_rule_id=binding_source.rule_ir.source_id,
                owner_player_id=army.player_id,
                target_unit_instance_ids=target_unit_ids,
                started_battle_round=max(1, context.state.battle_round),
                started_phase=context.state.current_battle_phase,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=validate_json_value(
                    {
                        **effect_payload,
                        "coverage_descriptor_id": binding_source.record.coverage_descriptor_id,
                        "execution_id": binding_source.record.execution_id,
                        "detachment_id": binding_source.record.detachment_id,
                        "generic_detachment_effect_id": effect_id,
                    }
                ),
            )
            context.state.record_persisting_effect(effect)
            applied_payloads.append(validate_json_value(effect.to_payload()))
    if applied_payloads:
        context.decisions.event_log.append(
            "generic_detachment_rule_effects_applied",
            {
                "game_id": context.state.game_id,
                "coverage_descriptor_id": binding_source.record.coverage_descriptor_id,
                "execution_id": binding_source.record.execution_id,
                "persisting_effects": applied_payloads,
            },
        )


def _persisting_effect_for_detachment_payload(
    *,
    effect_id: str,
    source_rule_id: str,
    owner_player_id: str,
    target_unit_instance_ids: tuple[str, ...],
    started_battle_round: int,
    expiration: EffectExpiration,
    effect_payload: JsonValue,
    started_phase: BattlePhaseKind | None = None,
) -> PersistingEffect:
    payload = validate_json_value(effect_payload)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Generic detachment effect payload must be an object.")
    if generic_rule_effect_payload_grants_ability(payload, ability=FIGHTS_FIRST_EFFECT_KIND):
        return PersistingEffect(
            effect_id=effect_id,
            source_rule_id=source_rule_id,
            owner_player_id=owner_player_id,
            target_unit_instance_ids=target_unit_instance_ids,
            started_battle_round=started_battle_round,
            started_phase=started_phase,
            expiration=expiration,
            effect_payload=validate_json_value(
                {**payload, "effect_kind": FIGHTS_FIRST_EFFECT_KIND}
            ),
        )
    return generic_rule_persisting_effect(
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=started_battle_round,
        started_phase=started_phase,
        expiration=expiration,
        effect_payload=payload,
    )


def _record_is_generic_detachment_rule(record: _Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_RULE
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _army_uses_record(
    *,
    army: ArmyDefinition,
    record: _Phase17FExecutionRecord,
) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Generic detachment effects require ArmyDefinition.")
    if record.detachment_id is None:
        raise GameLifecycleError("Generic detachment record requires detachment_id.")
    return (
        army.detachment_selection.faction_id == record.faction_id
        and record.detachment_id in army.detachment_selection.detachment_ids
    )


def _target_unit_ids_for_record(
    *,
    record: _Phase17FExecutionRecord,
    army: ArmyDefinition,
) -> tuple[str, ...]:
    if record.coverage_descriptor_id == MORE_DAKKA_DETACHMENT_RULE_DESCRIPTOR_ID:
        target_ids = tuple(
            unit.unit_instance_id
            for unit in army.units
            if _unit_is_more_dakka_detachment_target(unit)
        )
        return tuple(sorted(target_ids))
    if record.coverage_descriptor_id == SPECTACLE_OF_SLAUGHTER_DETACHMENT_RULE_DESCRIPTOR_ID:
        target_ids = tuple(
            unit.unit_instance_id
            for unit in army.units
            if _unit_is_spectacle_of_slaughter_detachment_target(unit)
        )
        return tuple(sorted(target_ids))
    if record.coverage_descriptor_id == COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID:
        target_ids = tuple(
            unit.unit_instance_id
            for unit in army.units
            if _unit_is_court_of_the_phoenician_detachment_target(unit)
        )
        return tuple(sorted(target_ids))
    if record.coverage_descriptor_id == SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID:
        target_ids = tuple(
            unit.unit_instance_id
            for unit in army.units
            if _unit_is_shadow_legion_detachment_target(unit)
        )
        return tuple(sorted(target_ids))
    raise GameLifecycleError("Generic detachment record is not supported by runtime.")


def _unit_is_spectacle_of_slaughter_detachment_target(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic detachment target requires UnitInstance.")
    return SPECTACLE_OF_SLAUGHTER_UNIT_KEYWORD in (*unit.keywords, *unit.faction_keywords)


def _unit_is_more_dakka_detachment_target(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic detachment target requires UnitInstance.")
    if MORE_DAKKA_FACTION_KEYWORD not in unit.faction_keywords:
        return False
    return bool({"INFANTRY", "WALKER"}.intersection(unit.keywords))


def _unit_is_court_of_the_phoenician_detachment_target(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic detachment target requires UnitInstance.")
    return COURT_OF_THE_PHOENICIAN_FACTION_KEYWORD in (
        *unit.keywords,
        *unit.faction_keywords,
    )


def _unit_is_shadow_legion_detachment_target(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic detachment target requires UnitInstance.")
    return _canonical_keyword(SHADOW_LEGION_KEYWORD) in {
        _canonical_keyword(keyword) for keyword in (*unit.keywords, *unit.faction_keywords)
    }


def _expected_effect_ids(
    *,
    record: _Phase17FExecutionRecord,
    rule_ir: RuleIR,
    player_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            _detachment_effect_id(
                record=record,
                rule_ir=rule_ir,
                player_id=player_id,
                clause_id=clause.clause_id,
            )
            for clause in rule_ir.clauses
            if clause.effects
        )
    )


def _detachment_effect_id(
    *,
    record: _Phase17FExecutionRecord,
    rule_ir: RuleIR,
    player_id: str,
    clause_id: str,
) -> str:
    player = _validate_identifier("player_id", player_id)
    suffix = _validate_identifier("clause_suffix", clause_id.rsplit(":", 1)[-1])
    descriptor = _validate_identifier("coverage_descriptor_id", record.coverage_descriptor_id)
    return _validate_identifier(
        "generic_detachment_effect_id",
        f"rule-effect:{rule_ir.ir_hash()[:16]}:{descriptor}:{player}:{suffix}",
    )


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Generic detachment effect payload requires {key}.")
    return _validate_identifier(key, value)


def _canonical_keyword(value: str) -> str:
    return value.strip().upper().replace("_", " ").replace("-", " ")


_validate_identifier = IdentifierValidator(GameLifecycleError)
