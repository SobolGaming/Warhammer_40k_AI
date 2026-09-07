from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import AbilityCatalogRecord
from warhammer40k_core.engine.effects import (
    PersistingEffect,
    PersistingEffectPayload,
)
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.faction_content.activation import (
    RuntimeContentActivation,
)
from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
from warhammer40k_core.engine.generic_rule_effect_identity import (
    generic_rule_persisting_effect_id,
)
from warhammer40k_core.engine.generic_rule_source_authority import (
    generic_ability_provider_matches,
    generic_execution_context_from_payload,
    generic_stratagem_provider_matches,
    validate_generic_detachment_effect_authority,
    validate_generic_enhancement_effect_authority,
    validated_generic_execution_effect_payload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.rule_duration_execution import expiration_for_duration
from warhammer40k_core.engine.rule_execution import RuleExecutionContext
from warhammer40k_core.engine.rule_target_resolution import (
    target_unit_instance_ids_for_clause,
)
from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex
from warhammer40k_core.engine.stratagems_model import StratagemCatalogRecord
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance

_DIRECT_CREATION_FAMILY = "direct"
_DETACHMENT_CREATION_FAMILY = "detachment"
_ENHANCEMENT_CREATION_FAMILY = "enhancement"
_RULE_EXECUTION_CONTEXT_KEYS = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "active_player_id",
        "timing_window_id",
        "source_unit_instance_id",
        "source_model_instance_id",
        "target_unit_instance_ids",
        "target_player_id",
        "source_keywords",
        "trigger_payload",
        "record_persisting_effects",
    }
)


def validate_primary_mission_oc_effect_event_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    for source in checkpoint.objective_control_modifier_sources:
        if source.source_effect_id is None:
            continue
        raw_effect = source.source_effect_json
        if raw_effect is None:
            raise GameLifecycleError(
                "Primary mission Objective Control effect source is incomplete."
            )
        effect = PersistingEffect.from_payload(
            cast(PersistingEffectPayload, _json_object(raw_effect, context="effect source"))
        )
        execution_payload, creation_family, rule_ir, clause = (
            validated_generic_execution_effect_payload(
                effect=effect,
                authority_index=rule_ir_authority_index,
            )
        )
        if creation_family != _ENHANCEMENT_CREATION_FAMILY:
            matches = tuple(
                event
                for event in event_records[:checkpoint_index]
                if event.event_type == "rule_execution_effect_applied"
                and event.payload == execution_payload
            )
            if len(matches) != 1:
                raise GameLifecycleError(
                    "Primary mission Objective Control effect lacks exact creation-event authority."
                )
        execution_context = _validate_effect_creation_context(
            state=state,
            effect=effect,
            checkpoint=checkpoint,
        )
        if creation_family == _DIRECT_CREATION_FAMILY:
            _validate_direct_effect_identity(
                state=state,
                effect=effect,
                rule_ir=rule_ir,
                clause=clause,
                context=execution_context,
                checkpoint=checkpoint,
                authority_index=rule_ir_authority_index,
            )
        if creation_family == _DETACHMENT_CREATION_FAMILY:
            validate_generic_detachment_effect_authority(
                armies=tuple(state.army_definitions),
                effect=effect,
                event_records=event_records,
                checkpoint_index=checkpoint_index,
                faction_rule_execution_registry=faction_rule_execution_registry,
                runtime_content_activation=runtime_content_activation,
            )
        elif creation_family == _ENHANCEMENT_CREATION_FAMILY:
            validate_generic_enhancement_effect_authority(
                effect=effect,
                event_records=event_records,
                checkpoint_index=checkpoint_index,
                faction_rule_execution_registry=faction_rule_execution_registry,
                runtime_content_activation=runtime_content_activation,
            )


def _validate_effect_creation_context(
    *,
    state: GameState,
    effect: PersistingEffect,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> RuleExecutionContext:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Primary mission Objective Control effect payload is invalid.")
    raw_context = payload.get("context")
    target_ids = payload.get("target_unit_instance_ids")
    if not isinstance(raw_context, dict) or not isinstance(target_ids, list):
        raise GameLifecycleError("Primary mission Objective Control effect context is invalid.")
    context = raw_context
    if frozenset(context) != _RULE_EXECUTION_CONTEXT_KEYS:
        raise GameLifecycleError("Primary mission Objective Control effect context drifted.")
    execution_context = generic_execution_context_from_payload(context, state=state)
    started_phase = None if effect.started_phase is None else effect.started_phase.value
    if (
        payload.get("source_id") != effect.source_rule_id
        or target_ids != list(effect.target_unit_instance_ids)
        or execution_context.to_payload() != context
        or execution_context.game_id != checkpoint.game_id
        or execution_context.player_id != effect.owner_player_id
        or execution_context.battle_round != effect.started_battle_round
        or (None if execution_context.phase is None else execution_context.phase.value)
        != started_phase
        or execution_context.target_unit_instance_ids != effect.target_unit_instance_ids
        or execution_context.record_persisting_effects is not True
        or effect.started_battle_round > checkpoint.battle_round
    ):
        raise GameLifecycleError(
            "Primary mission Objective Control effect creation context drifted."
        )
    return execution_context


def _validate_direct_effect_identity(
    *,
    state: GameState,
    effect: PersistingEffect,
    rule_ir: RuleIR,
    clause: RuleClause,
    context: RuleExecutionContext,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    authority_index: RuntimeRuleIRAuthorityIndex | None,
) -> None:
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    effect_index = _payload_non_negative_int(payload, key="effect_index")
    if effect_index >= len(clause.effects) or clause.duration is None:
        raise GameLifecycleError("Generic RuleIR persisted effect identity is invalid.")
    effect_spec = clause.effects[effect_index]
    expected_effect_id = generic_rule_persisting_effect_id(
        rule_ir=rule_ir,
        clause=clause,
        effect=effect_spec,
        source_unit_instance_id=context.source_unit_instance_id,
        source_model_instance_id=context.source_model_instance_id,
        target_unit_instance_ids=effect.target_unit_instance_ids,
    )
    expected_expiration = expiration_for_duration(
        duration=clause.duration,
        context=context,
    )
    expected_target_ids = target_unit_instance_ids_for_clause(
        clause=clause,
        context=context,
        target_unit_instance_ids=None,
    )
    _validate_direct_execution_source(
        checkpoint=checkpoint,
        context=context,
    )
    _validate_direct_provider_authority(
        state=state,
        checkpoint=checkpoint,
        context=context,
        rule_ir=rule_ir,
        authority_index=authority_index,
    )
    if (
        effect.effect_id != expected_effect_id
        or expected_expiration is None
        or effect.expiration != expected_expiration
        or effect.target_unit_instance_ids != expected_target_ids
    ):
        raise GameLifecycleError("Generic RuleIR persisted effect identity drifted.")


def _validate_direct_execution_source(
    *,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    context: RuleExecutionContext,
) -> None:
    source_unit_id = context.source_unit_instance_id
    source_model_id = context.source_model_instance_id
    if source_unit_id is None:
        if source_model_id is not None:
            raise GameLifecycleError("Generic RuleIR source model lacks its source unit.")
        return
    source_rows = tuple(
        row
        for row in checkpoint.model_states
        if source_unit_id in {row.rules_unit_instance_id, row.component_unit_instance_id}
    )
    if not source_rows or {row.owner_player_id for row in source_rows} != {context.player_id}:
        raise GameLifecycleError("Generic RuleIR source unit ownership drifted.")
    if source_model_id is None:
        return
    model_rows = tuple(row for row in source_rows if row.model_instance_id == source_model_id)
    if len(model_rows) != 1:
        raise GameLifecycleError("Generic RuleIR source model identity drifted.")


def _validate_direct_provider_authority(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    context: RuleExecutionContext,
    rule_ir: RuleIR,
    authority_index: RuntimeRuleIRAuthorityIndex | None,
) -> None:
    if authority_index is None:
        raise GameLifecycleError("Generic RuleIR effect lacks direct provider authority.")
    ability_records = authority_index.ability_records_for_player(
        source_id=rule_ir.source_id,
        rule_ir_hash=rule_ir.ir_hash(),
        player_id=context.player_id,
    )
    stratagem_records = authority_index.stratagem_records_for_player(
        source_id=rule_ir.source_id,
        rule_ir_hash=rule_ir.ir_hash(),
        player_id=context.player_id,
    )
    if any(
        _ability_provider_matches(
            state=state,
            checkpoint=checkpoint,
            context=context,
            record=record,
        )
        for record in ability_records
    ) or any(
        _stratagem_provider_matches(
            state=state,
            context=context,
            record=record,
        )
        for record in stratagem_records
    ):
        return
    raise GameLifecycleError("Generic RuleIR effect lacks exact provider timing authority.")


def _ability_provider_matches(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    context: RuleExecutionContext,
    record: AbilityCatalogRecord,
) -> bool:
    army = _army_for_player(state=state, player_id=context.player_id)
    source_units = _source_component_units(
        state=state,
        checkpoint=checkpoint,
        source_unit_instance_id=context.source_unit_instance_id,
    )
    return generic_ability_provider_matches(
        context=context, record=record, army=army, source_units=source_units
    )


def _stratagem_provider_matches(
    *,
    state: GameState,
    context: RuleExecutionContext,
    record: StratagemCatalogRecord,
) -> bool:
    return generic_stratagem_provider_matches(
        context=context, record=record, uses=tuple(state.stratagem_use_records)
    )


def _army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    matches = tuple(army for army in state.army_definitions if army.player_id == player_id)
    if len(matches) != 1:
        raise GameLifecycleError("Generic RuleIR provider army authority drifted.")
    return matches[0]


def _source_component_units(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    source_unit_instance_id: str | None,
) -> tuple[UnitInstance, ...]:
    if source_unit_instance_id is None:
        return ()
    component_ids = {
        row.component_unit_instance_id
        for row in checkpoint.model_states
        if source_unit_instance_id in {row.rules_unit_instance_id, row.component_unit_instance_id}
    }
    return tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in component_ids
    )


def _json_object(value: str, *, context: str) -> dict[str, JsonValue]:
    import json

    try:
        decoded: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GameLifecycleError(f"Primary mission {context} JSON is invalid.") from exc
    validated = validate_json_value(decoded)
    if not isinstance(validated, dict) or canonical_json(validated) != value:
        raise GameLifecycleError(f"Primary mission {context} JSON is not canonical.")
    return validated


def _payload_non_negative_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"Primary mission Objective Control effect requires {key}.")
    return value


__all__ = ("validate_primary_mission_oc_effect_event_authority",)
