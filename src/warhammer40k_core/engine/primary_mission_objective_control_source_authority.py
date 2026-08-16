from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.abilities import AbilityCatalogRecord, AbilitySourceKind
from warhammer40k_core.engine.effects import (
    EffectExpiration,
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
    RuntimeEnhancementAssignment,
    RuntimeEnhancementAssignmentPayload,
)
from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
from warhammer40k_core.engine.generic_rule_effect_identity import (
    generic_rule_persisting_effect_id,
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

_EXECUTION_EFFECT_KEYS = frozenset(
    {
        "effect_kind",
        "rule_id",
        "source_id",
        "rule_ir_hash",
        "clause_id",
        "effect_index",
        "source_span",
        "target",
        "target_unit_instance_ids",
        "duration",
        "effect",
        "context",
    }
)
_DETACHMENT_EFFECT_KEYS = frozenset(
    {
        "coverage_descriptor_id",
        "execution_id",
        "detachment_id",
        "generic_detachment_effect_id",
    }
)
_ENHANCEMENT_EFFECT_KEYS = frozenset(
    {
        "coverage_descriptor_id",
        "execution_id",
        "enhancement_assignment",
    }
)
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
        execution_payload, creation_family, rule_ir, clause = _validated_execution_effect_payload(
            effect=effect,
            authority_index=rule_ir_authority_index,
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
            _validate_detachment_effect_authority(
                state=state,
                effect=effect,
                event_records=event_records,
                checkpoint_index=checkpoint_index,
                faction_rule_execution_registry=faction_rule_execution_registry,
                runtime_content_activation=runtime_content_activation,
            )
        elif creation_family == _ENHANCEMENT_CREATION_FAMILY:
            _validate_enhancement_effect_authority(
                effect=effect,
                event_records=event_records,
                checkpoint_index=checkpoint_index,
                faction_rule_execution_registry=faction_rule_execution_registry,
                runtime_content_activation=runtime_content_activation,
            )


def _validated_execution_effect_payload(
    *,
    effect: PersistingEffect,
    authority_index: RuntimeRuleIRAuthorityIndex | None,
) -> tuple[dict[str, JsonValue], str, RuleIR, RuleClause]:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Primary mission Objective Control effect payload is invalid.")
    if authority_index is None:
        raise GameLifecycleError(
            "Primary mission Objective Control effect lacks loaded RuleIR authority."
        )
    rule_ir = authority_index.rule_ir_for(
        source_id=_payload_string(payload, key="source_id"),
        rule_ir_hash=_payload_string(payload, key="rule_ir_hash"),
    )
    clause = _rule_clause_for_payload(rule_ir=rule_ir, payload=payload)
    effect_index = payload.get("effect_index")
    if type(effect_index) is not int or not 0 <= effect_index < len(clause.effects):
        raise GameLifecycleError("Primary mission Objective Control effect slot is invalid.")
    expected_fields = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "effect_kind": "generic_rule_execution",
                "rule_id": rule_ir.rule_id,
                "source_id": rule_ir.source_id,
                "rule_ir_hash": rule_ir.ir_hash(),
                "clause_id": clause.clause_id,
                "effect_index": effect_index,
                "source_span": clause.source_span.to_payload(),
                "target": None if clause.target is None else clause.target.to_payload(),
                "duration": (None if clause.duration is None else clause.duration.to_payload()),
                "effect": clause.effects[effect_index].to_payload(),
            }
        ),
    )
    for key, expected in expected_fields.items():
        if payload.get(key) != expected:
            raise GameLifecycleError(
                "Primary mission Objective Control effect contradicts loaded RuleIR."
            )
    expected_conditions = validate_json_value([row.to_payload() for row in clause.conditions])
    if clause.conditions:
        if payload.get("conditions") != expected_conditions:
            raise GameLifecycleError(
                "Primary mission Objective Control effect conditions contradict loaded RuleIR."
            )
    elif "conditions" in payload:
        raise GameLifecycleError(
            "Primary mission Objective Control effect has invented RuleIR conditions."
        )
    creation_family = _creation_family(payload)
    if creation_family == _DIRECT_CREATION_FAMILY:
        authority_index.rule_ir_for_player(
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            player_id=effect.owner_player_id,
        )
    provider_keys: frozenset[str] = (
        _DETACHMENT_EFFECT_KEYS
        if creation_family == _DETACHMENT_CREATION_FAMILY
        else (
            _ENHANCEMENT_EFFECT_KEYS
            if creation_family == _ENHANCEMENT_CREATION_FAMILY
            else frozenset[str]()
        )
    )
    allowed_keys = _EXECUTION_EFFECT_KEYS | provider_keys
    if clause.conditions:
        allowed_keys = allowed_keys | {"conditions"}
    if set(payload) - allowed_keys:
        raise GameLifecycleError(
            "Primary mission Objective Control effect has unsupported source metadata."
        )
    if effect.source_rule_id != rule_ir.source_id:
        raise GameLifecycleError("Primary mission Objective Control source rule drifted.")
    return (
        {key: value for key, value in payload.items() if key not in provider_keys},
        creation_family,
        rule_ir,
        clause,
    )


def _creation_family(payload: dict[str, JsonValue]) -> str:
    if "enhancement_assignment" in payload:
        if not _ENHANCEMENT_EFFECT_KEYS.issubset(payload) or (
            _DETACHMENT_EFFECT_KEYS - {"coverage_descriptor_id", "execution_id"}
        ).intersection(payload):
            raise GameLifecycleError("Generic enhancement effect authority is incomplete.")
        return _ENHANCEMENT_CREATION_FAMILY
    if _DETACHMENT_EFFECT_KEYS.intersection(payload):
        if not _DETACHMENT_EFFECT_KEYS.issubset(payload):
            raise GameLifecycleError("Generic detachment effect authority is incomplete.")
        return _DETACHMENT_CREATION_FAMILY
    if (_ENHANCEMENT_EFFECT_KEYS - {"enhancement_assignment"}).intersection(payload):
        raise GameLifecycleError("Generic RuleIR provider authority is incomplete.")
    return _DIRECT_CREATION_FAMILY


def _rule_clause_for_payload(
    *,
    rule_ir: RuleIR,
    payload: dict[str, JsonValue],
) -> RuleClause:
    clause_id = _payload_string(payload, key="clause_id")
    matches = tuple(clause for clause in rule_ir.clauses if clause.clause_id == clause_id)
    if len(matches) != 1:
        raise GameLifecycleError("Primary mission Objective Control effect clause is not loaded.")
    return matches[0]


def _validate_detachment_effect_authority(
    *,
    state: GameState,
    effect: PersistingEffect,
    event_records: tuple[EventRecord, ...],
    checkpoint_index: int,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None,
    runtime_content_activation: RuntimeContentActivation | None,
) -> None:
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    present_keys = _DETACHMENT_EFFECT_KEYS.intersection(payload)
    if not present_keys:
        return
    if present_keys != _DETACHMENT_EFFECT_KEYS:
        raise GameLifecycleError("Generic detachment effect authority is incomplete.")
    coverage_id = _payload_string(payload, key="coverage_descriptor_id")
    execution_id = _payload_string(payload, key="execution_id")
    detachment_id = _payload_string(payload, key="detachment_id")
    source_effect_id = _payload_string(payload, key="generic_detachment_effect_id")
    clause_id = _payload_string(payload, key="clause_id")
    rule_ir_hash = _payload_string(payload, key="rule_ir_hash")
    expected_effect_id = (
        f"rule-effect:{rule_ir_hash[:16]}:{coverage_id}:{effect.owner_player_id}:"
        f"{clause_id.rsplit(':', 1)[-1]}"
    )
    context = payload.get("context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Generic detachment effect context is invalid.")
    trigger_payload = context.get("trigger_payload")
    if faction_rule_execution_registry is None or runtime_content_activation is None:
        raise GameLifecycleError(
            "Generic detachment Objective Control effect lacks provider authority."
        )
    record = faction_rule_execution_registry.record_by_execution_id(execution_id)
    provider_rule_ir = faction_rule_execution_registry.resolved_generic_rule_ir(execution_id)
    owner_armies = tuple(
        army for army in state.army_definitions if army.player_id == effect.owner_player_id
    )
    if (
        record.execution_id != execution_id
        or record.coverage_descriptor_id != coverage_id
        or record.detachment_id != detachment_id
        or record.rule_ir_hash != rule_ir_hash
        or provider_rule_ir.source_id != effect.source_rule_id
        or provider_rule_ir.ir_hash() != rule_ir_hash
        or source_effect_id != effect.effect_id
        or source_effect_id != expected_effect_id
        or effect.expiration != EffectExpiration.end_of_battle()
        or len(owner_armies) != 1
        or detachment_id not in owner_armies[0].detachment_selection.detachment_ids
        or detachment_id not in runtime_content_activation.selected_detachment_ids
        or execution_id not in runtime_content_activation.selected_execution_record_ids
        or not isinstance(trigger_payload, dict)
        or trigger_payload.get("event") != "detachment_rule_setup"
        or trigger_payload.get("detachment_id") != detachment_id
        or trigger_payload.get("coverage_descriptor_id") != coverage_id
    ):
        raise GameLifecycleError("Generic detachment effect identity drifted.")
    matches: list[EventRecord] = []
    for event in event_records[:checkpoint_index]:
        if event.event_type != "generic_detachment_rule_effects_applied" or not isinstance(
            event.payload, dict
        ):
            continue
        installed_effects = event.payload.get("persisting_effects")
        if (
            event.payload.get("game_id") == context.get("game_id")
            and event.payload.get("coverage_descriptor_id") == coverage_id
            and event.payload.get("execution_id") == execution_id
            and isinstance(installed_effects, list)
            and validate_json_value(effect.to_payload()) in installed_effects
        ):
            matches.append(event)
    if len(matches) != 1:
        raise GameLifecycleError(
            "Generic detachment Objective Control effect lacks installation-event authority."
        )


def _validate_enhancement_effect_authority(
    *,
    effect: PersistingEffect,
    event_records: tuple[EventRecord, ...],
    checkpoint_index: int,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None,
    runtime_content_activation: RuntimeContentActivation | None,
) -> None:
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    coverage_id = _payload_string(payload, key="coverage_descriptor_id")
    execution_id = _payload_string(payload, key="execution_id")
    assignment_payload = payload.get("enhancement_assignment")
    if not isinstance(assignment_payload, dict):
        raise GameLifecycleError("Generic enhancement assignment authority is invalid.")
    assignment = RuntimeEnhancementAssignment.from_payload(
        cast(RuntimeEnhancementAssignmentPayload, assignment_payload)
    )
    if faction_rule_execution_registry is None or runtime_content_activation is None:
        raise GameLifecycleError(
            "Generic enhancement Objective Control effect lacks provider authority."
        )
    record = faction_rule_execution_registry.record_by_execution_id(execution_id)
    provider_rule_ir = faction_rule_execution_registry.resolved_generic_rule_ir(execution_id)
    rule_ir_hash = _payload_string(payload, key="rule_ir_hash")
    clause_id = _payload_string(payload, key="clause_id")
    expected_effect_id = f"{execution_id}:{assignment.assignment_id}:{clause_id}:persisting"
    if (
        record.coverage_kind.value != "detachment_enhancement"
        or record.execution_id != execution_id
        or record.coverage_descriptor_id != coverage_id
        or record.rule_ir_hash != rule_ir_hash
        or record.rule_id != assignment.enhancement_id
        or provider_rule_ir.source_id != effect.source_rule_id
        or provider_rule_ir.ir_hash() != rule_ir_hash
        or assignment not in runtime_content_activation.selected_enhancement_assignments
        or assignment.player_id != effect.owner_player_id
        or assignment.bearer_unit_instance_id not in effect.target_unit_instance_ids
        or effect.effect_id != expected_effect_id
        or effect.expiration != EffectExpiration.end_of_battle()
    ):
        raise GameLifecycleError("Generic enhancement effect identity drifted.")
    context = payload.get("context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Generic enhancement execution context is invalid.")
    trigger_payload = context.get("trigger_payload")
    if (
        not isinstance(trigger_payload, dict)
        or trigger_payload.get("event") != "enhancement_assignment"
        or trigger_payload.get("enhancement_assignment") != assignment_payload
    ):
        raise GameLifecycleError("Generic enhancement execution context drifted.")
    expected_grant_fields = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "effect_id": execution_id,
                "source_id": effect.source_rule_id,
                "enhancement_id": assignment.enhancement_id,
                "target_unit_instance_id": assignment.bearer_unit_instance_id,
                "persisting_effect": effect.to_payload(),
            }
        ),
    )
    matching_grants: list[dict[str, JsonValue]] = []
    for event in event_records[:checkpoint_index]:
        if event.event_type != "enhancement_effects_applied" or not isinstance(event.payload, dict):
            continue
        raw_grants = event.payload.get("effects")
        if event.payload.get("game_id") != context.get("game_id") or not isinstance(
            raw_grants, list
        ):
            continue
        for raw_grant in raw_grants:
            if not isinstance(raw_grant, dict) or any(
                raw_grant.get(key) != value for key, value in expected_grant_fields.items()
            ):
                continue
            replay_payload = raw_grant.get("replay_payload")
            if (
                not isinstance(replay_payload, dict)
                or replay_payload.get("execution_id") != execution_id
                or replay_payload.get("coverage_descriptor_id") != coverage_id
                or replay_payload.get("enhancement_assignment") != assignment_payload
            ):
                continue
            matching_grants.append(raw_grant)
    if len(matching_grants) != 1:
        raise GameLifecycleError(
            "Generic enhancement Objective Control effect lacks installation-event authority."
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
    phase_token = context["phase"]
    if phase_token is not None and type(phase_token) is not str:
        raise GameLifecycleError("Primary mission Objective Control effect phase is invalid.")
    execution_context = RuleExecutionContext(
        game_id=_payload_string(context, key="game_id"),
        player_id=_payload_string(context, key="player_id"),
        battle_round=_payload_positive_int(context, key="battle_round"),
        phase=(None if phase_token is None else battle_phase_kind_from_token(phase_token)),
        active_player_id=_payload_optional_string(context, key="active_player_id"),
        timing_window_id=_payload_optional_string(context, key="timing_window_id"),
        source_unit_instance_id=_payload_optional_string(
            context,
            key="source_unit_instance_id",
        ),
        source_model_instance_id=_payload_optional_string(
            context,
            key="source_model_instance_id",
        ),
        target_unit_instance_ids=_payload_string_tuple(
            context,
            key="target_unit_instance_ids",
        ),
        target_player_id=_payload_optional_string(context, key="target_player_id"),
        source_keywords=_payload_string_tuple(context, key="source_keywords"),
        trigger_payload=context["trigger_payload"],
        state=state,
        record_persisting_effects=_payload_bool(
            context,
            key="record_persisting_effects",
        ),
    )
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
    timing = record.definition.timing
    if (timing.phase is not None and timing.phase is not context.phase) or (
        timing.timing_window_id is not None and timing.timing_window_id != context.timing_window_id
    ):
        return False
    army = _army_for_player(state=state, player_id=context.player_id)
    source_units = _source_component_units(
        state=state,
        checkpoint=checkpoint,
        source_unit_instance_id=context.source_unit_instance_id,
    )
    if context.source_unit_instance_id is not None and not source_units:
        return False
    actual_keywords = tuple(
        sorted(
            {
                *(
                    keyword
                    for unit in source_units
                    for keyword in (*unit.keywords, *unit.faction_keywords)
                )
            }
        )
    )
    if not record.definition.keyword_gate.matches(actual_keywords):
        return False
    source_kind = record.source_kind
    if source_kind in {AbilitySourceKind.CORE, AbilitySourceKind.KEYWORD}:
        return True
    if source_kind is AbilitySourceKind.FACTION:
        return record.faction_id == army.detachment_selection.faction_id
    if source_kind is AbilitySourceKind.DETACHMENT:
        return record.detachment_id in army.detachment_selection.detachment_ids
    if source_kind is AbilitySourceKind.ENHANCEMENT:
        return (
            record.detachment_id in army.detachment_selection.detachment_ids
            and record.definition.ability_id in army.detachment_selection.enhancement_ids
        )
    if source_kind is AbilitySourceKind.DATASHEET:
        return any(unit.datasheet_id == record.datasheet_id for unit in source_units)
    if source_kind is AbilitySourceKind.WARGEAR:
        models = tuple(model for unit in source_units for model in unit.own_models)
        if context.source_model_instance_id is not None:
            models = tuple(
                model
                for model in models
                if model.model_instance_id == context.source_model_instance_id
            )
        return any(record.wargear_id in model.wargear_ids for model in models)
    if source_kind is AbilitySourceKind.WEAPON:
        return bool(source_units)
    return False


def _stratagem_provider_matches(
    *,
    state: GameState,
    context: RuleExecutionContext,
    record: StratagemCatalogRecord,
) -> bool:
    timing = record.definition.timing
    if (timing.phase is not None and timing.phase is not context.phase) or (
        timing.timing_window_id is not None and timing.timing_window_id != context.timing_window_id
    ):
        return False
    trigger = context.trigger_payload
    if not isinstance(trigger, dict):
        return False
    use_id = trigger.get("stratagem_use_id")
    nested_context = trigger.get("stratagem_context")
    if (
        trigger.get("stratagem_id") != record.definition.stratagem_id
        or type(use_id) is not str
        or not isinstance(nested_context, dict)
        or nested_context.get("trigger_kind") != timing.trigger_kind.value
        or nested_context.get("phase") != (None if context.phase is None else context.phase.value)
        or nested_context.get("timing_window_id") != context.timing_window_id
    ):
        return False
    uses = tuple(use for use in state.stratagem_use_records if use.use_id == use_id)
    if len(uses) != 1:
        return False
    use = uses[0]
    return (
        use.player_id == context.player_id
        and use.stratagem_id == record.definition.stratagem_id
        and use.source_id == record.definition.source_id
        and use.battle_round == context.battle_round
        and use.phase == (None if context.phase is None else context.phase.value)
        and use.active_player_id == context.active_player_id
        and use.timing_window_id == context.timing_window_id
        and trigger.get("effect_selection") == use.effect_selection
        and use.effects_resolved
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


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Primary mission Objective Control effect requires {key}.")
    return value


def _payload_optional_string(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _payload_string(payload, key=key)


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Primary mission Objective Control effect requires {key}.")
    return value


def _payload_non_negative_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"Primary mission Objective Control effect requires {key}.")
    return value


def _payload_string_tuple(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or any(
        type(item) is not str or not item.strip() for item in value
    ):
        raise GameLifecycleError(f"Primary mission Objective Control effect requires {key}.")
    return tuple(cast(list[str], value))


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Primary mission Objective Control effect requires {key}.")
    return value


__all__ = ("validate_primary_mission_oc_effect_event_authority",)
