from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequencePayload,
    AttackSequenceStep,
)
from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    selected_target_option_id,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    catalog_selected_target_clauses_from_record,
    clause_is_post_shoot_hit_target_selection,
    clause_requires_prior_mortal_wounds,
    effect_is_immediate_selected_target_battle_shock,
    effect_with_selected_target,
    post_shoot_selected_target_effect_clauses_after,
    post_shoot_target_once_per_turn,
    post_shoot_target_selection_is_optional,
    required_keywords_for_clause,
    runtime_clause_id_from_record,
    selection_source_model_ids_for_record,
    selection_subject,
    selection_weapon_names,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    effect_is_immediate_selected_target_mortal_wounds,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, EffectExpiration
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_duration_execution import expiration_for_duration
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_weapon_selector_applies,
)
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleTargetKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogRecord
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance


_COMPLETION_KEYS = frozenset({"sequence_id", "attacker_player_id", "attacking_unit_instance_id"})


def validate_catalog_selected_target_loaded_source_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    request: BattleShockTestRequest,
    source_decision_record: DecisionRecord,
    request_base: dict[str, JsonValue],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Rebuild the exact post-shoot selected-target request from causal authority."""

    selection_boundary = _selection_request_event_index(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=request_event_index,
        record=source_decision_record,
    )
    active_player_id = _identifier(request_base.get("active_player_id"), "active player ID")
    historical = historical_battle_shock_authority_context(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        boundary_event_index=selection_boundary,
        request=request,
        active_player_id=active_player_id,
        phase=BattlePhase.SHOOTING,
        phase_start_battle_shocked_unit_ids=(),
    )
    player_id = source_decision_record.request.actor_id
    if player_id is None:
        raise GameLifecycleError("Selected-target source player is missing.")
    loaded_record = _loaded_record(
        player_id=player_id,
        record_id=request_base.get("catalog_record_id"),
        source_rule_id=request_base.get("source_rule_id"),
        runtime_content_bundle=runtime_content_bundle,
    )
    selection_clause, effect_clauses = _loaded_clauses(
        record=loaded_record,
        selection_clause_id=request_base.get("selection_clause_id"),
    )
    source_unit_id = _identifier(request_base.get("source_unit_instance_id"), "source unit ID")
    source_unit, source_army = historical.unit_and_army(source_unit_id)
    source_model_ids = historical.component_placed_alive_model_ids(source_unit_id)
    if source_army.player_id != player_id or not catalog_rule_record_source_matches_unit(
        record=loaded_record,
        unit=source_unit,
        current_model_instance_ids=source_model_ids,
    ):
        raise GameLifecycleError("Selected-target loaded source ownership drifted.")
    source_rules_unit_ids = tuple(
        rules_unit.unit_instance_id
        for rules_unit in historical.all_rules_units()
        if any(
            component.unit.unit_instance_id == source_unit.unit_instance_id
            for component in rules_unit.components
        )
    )
    if len(source_rules_unit_ids) != 1:
        raise GameLifecycleError("Selected-target source rules-unit authority drifted.")
    payload = _object(
        source_decision_record.request.payload,
        "selected-target decision request payload",
    )
    sequence = _authenticated_attack_sequence(
        event_records=event_records,
        decision_records=decision_records,
        selection_boundary=selection_boundary,
        payload=payload,
        player_id=player_id,
        source_rules_unit_id=source_rules_unit_ids[0],
    )
    source_model_id = _optional_identifier(
        payload.get("source_model_instance_id"), "source model ID"
    )
    if source_model_id not in selection_source_model_ids_for_record(
        loaded_record,
        source_unit,
        selection_clause,
        effect_clauses,
        source_model_ids,
    ):
        raise GameLifecycleError("Selected-target source-model authority drifted.")
    target_ids = _eligible_hit_target_ids(
        historical=historical,
        event_records=event_records,
        selection_boundary=selection_boundary,
        sequence=sequence,
        selection_clause=selection_clause,
        source_player_id=player_id,
        source_model_instance_id=source_model_id,
        loaded_record=loaded_record,
    )
    expected_options = tuple(
        _expected_option(
            historical=historical,
            record=loaded_record,
            source_unit=source_unit,
            source_model_instance_id=source_model_id,
            selection_clause=selection_clause,
            effect_clauses=effect_clauses,
            target_unit_instance_id=target_id,
            sequence=sequence,
            completion_event_id=_identifier(
                payload.get("attack_sequence_completed_event_id"),
                "attack-sequence completion event ID",
            ),
            optional=post_shoot_target_selection_is_optional(selection_clause),
        )
        for target_id in target_ids
    )
    _validate_exact_request(
        historical=historical,
        source_record=source_decision_record,
        loaded_record=loaded_record,
        source_unit=source_unit,
        source_model_instance_id=source_model_id,
        selection_clause=selection_clause,
        effect_clauses=effect_clauses,
        sequence=sequence,
        expected_options=expected_options,
    )


def _selection_request_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    record: DecisionRecord,
) -> int:
    matches = tuple(
        index
        for index, event in enumerate(event_records[:mutation_index])
        if event.event_type == "decision_requested" and event.payload == record.request.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Selected-target request boundary drifted.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=record.request.request_id,
        result_id=record.result.result_id,
    )
    return matches[0]


def _loaded_record(
    *,
    player_id: str,
    record_id: JsonValue,
    source_rule_id: JsonValue,
    runtime_content_bundle: RuntimeContentBundle,
) -> AbilityCatalogRecord:
    index = runtime_content_bundle.ability_indexes_by_player_id.get(player_id)
    matches = (
        ()
        if index is None
        else tuple(
            record
            for record in index.all_records()
            if record.record_id == record_id and record.definition.source_id == source_rule_id
        )
    )
    if len(matches) != 1:
        raise GameLifecycleError("Selected-target loaded catalog authority drifted.")
    return matches[0]


def _loaded_clauses(
    *,
    record: AbilityCatalogRecord,
    selection_clause_id: JsonValue,
) -> tuple[RuleClause, tuple[RuleClause, ...]]:
    clauses = catalog_selected_target_clauses_from_record(record)
    runtime_clause_id = runtime_clause_id_from_record(record)
    matches = tuple(
        (index, clause)
        for index, clause in enumerate(clauses)
        if clause.clause_id == selection_clause_id
        and (runtime_clause_id is None or runtime_clause_id == clause.clause_id)
        and clause_is_post_shoot_hit_target_selection(clause)
    )
    if len(matches) != 1:
        raise GameLifecycleError("Selected-target loaded selection clause drifted.")
    index, selection_clause = matches[0]
    effect_clauses = post_shoot_selected_target_effect_clauses_after(clauses, index)
    if not effect_clauses:
        raise GameLifecycleError("Selected-target loaded effect inventory is empty.")
    return selection_clause, effect_clauses


def _authenticated_attack_sequence(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    selection_boundary: int,
    payload: dict[str, JsonValue],
    player_id: str,
    source_rules_unit_id: str,
) -> AttackSequence:
    raw_sequence = _object(payload.get("attack_sequence"), "attack sequence")
    sequence = AttackSequence.from_payload(cast(AttackSequencePayload, raw_sequence))
    completion_id = _identifier(
        payload.get("attack_sequence_completed_event_id"),
        "attack-sequence completion event ID",
    )
    completion = tuple(
        (index, event)
        for index, event in enumerate(event_records[:selection_boundary])
        if event.event_id == completion_id and event.event_type == "attack_sequence_completed"
    )
    expected_completion = {
        "sequence_id": sequence.sequence_id,
        "attacker_player_id": sequence.attacker_player_id,
        "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
    }
    declarations = tuple(
        (index, event)
        for index, event in enumerate(event_records[:selection_boundary])
        if event.event_type == "shooting_declaration_accepted"
        and isinstance(event.payload, dict)
        and event.payload.get("attack_pools")
        == [pool.to_payload() for pool in sequence.attack_pools]
        and event.payload.get("unit_instance_id") == source_rules_unit_id
        and event.payload.get("active_player_id") == player_id
    )
    if (
        payload.get("attack_sequence_id") != sequence.sequence_id
        or sequence.source_phase is not BattlePhase.SHOOTING
        or not sequence.is_complete
        or sequence.attacker_player_id != player_id
        or sequence.attacking_unit_instance_id != source_rules_unit_id
        or len(completion) != 1
        or not isinstance(completion[0][1].payload, dict)
        or frozenset(completion[0][1].payload) != _COMPLETION_KEYS
        or completion[0][1].payload != expected_completion
        or len(declarations) != 1
        or not declarations[0][0] < completion[0][0] < selection_boundary
    ):
        raise GameLifecycleError("Selected-target attack-sequence authority drifted.")
    declaration_payload = cast(dict[str, JsonValue], declarations[0][1].payload)
    request_id = _identifier(declaration_payload.get("request_id"), "declaration request ID")
    result_id = _identifier(declaration_payload.get("result_id"), "declaration result ID")
    if sequence.sequence_id != f"attack-sequence:{result_id}":
        raise GameLifecycleError("Selected-target attack-sequence identity drifted.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=declarations[0][0],
        request_id=request_id,
        result_id=result_id,
    )
    return sequence


def _eligible_hit_target_ids(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    event_records: tuple[EventRecord, ...],
    selection_boundary: int,
    sequence: AttackSequence,
    selection_clause: RuleClause,
    source_player_id: str,
    source_model_instance_id: str | None,
    loaded_record: AbilityCatalogRecord,
) -> tuple[str, ...]:
    unsupported = tuple(
        condition.kind
        for condition in selection_clause.conditions
        if condition.kind not in {RuleConditionKind.KEYWORD_GATE, RuleConditionKind.FREQUENCY_LIMIT}
    )
    if unsupported:
        raise GameLifecycleError("Selected-target historical selection predicate is unsupported.")
    subject = selection_subject(selection_clause)
    requested_model_id = None if subject == "this_models_unit" else source_model_instance_id
    weapon_names = selection_weapon_names(selection_clause)
    hit_target_ids: set[str] = set()
    for event in event_records[:selection_boundary]:
        if event.event_type != "attack_sequence_step" or not isinstance(event.payload, dict):
            continue
        payload = event.payload
        if payload.get("sequence_id") != sequence.sequence_id:
            continue
        if payload.get("step") != AttackSequenceStep.HIT.value:
            continue
        hit_payload = payload.get("payload")
        pool_index = payload.get("pool_index")
        if (
            not isinstance(hit_payload, dict)
            or hit_payload.get("successful") is not True
            or type(pool_index) is not int
            or not 0 <= pool_index < len(sequence.attack_pools)
        ):
            continue
        pool = sequence.attack_pools[pool_index]
        if requested_model_id is not None and pool.attacker_model_instance_id != requested_model_id:
            continue
        if weapon_names and not rule_ir_weapon_selector_applies(
            parameters={"weapon_names": weapon_names},
            profile=pool.weapon_profile,
        ):
            continue
        hit_target_ids.add(pool.target_unit_instance_id)
    target_parameters = (
        {}
        if selection_clause.target is None
        else parameter_payload(selection_clause.target.parameters)
    )
    if target_parameters.get("allegiance") != "enemy":
        raise GameLifecycleError("Selected-target loaded target allegiance is unsupported.")
    required_keywords = required_keywords_for_clause(selection_clause)
    excluded: frozenset[str] = (
        _prior_once_per_turn_targets(
            historical=historical,
            event_records=event_records[:selection_boundary],
            source_rule_id=loaded_record.definition.source_id,
        )
        if post_shoot_target_once_per_turn(selection_clause)
        else frozenset[str]()
    )
    targets: list[str] = []
    for target_id in sorted(hit_target_ids):
        target = historical.rules_unit(target_id)
        if (
            target.owner_player_id == source_player_id
            or not historical.placed_alive_model_ids(target_id)
            or target_id in excluded
        ):
            continue
        if required_keywords and not unit_has_required_keywords(
            unit_keywords=target.keywords,
            faction_keywords=target.faction_keywords,
            required_keywords=required_keywords,
        ):
            continue
        targets.append(target_id)
    return tuple(targets)


def _prior_once_per_turn_targets(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    event_records: tuple[EventRecord, ...],
    source_rule_id: str,
) -> frozenset[str]:
    selected: set[str] = set()
    for event in event_records:
        if event.event_type != "catalog_post_shoot_hit_target_effect_selected":
            continue
        payload = _object(event.payload, "prior selected-target event")
        if (
            payload.get("battle_round") == historical.request.battle_round
            and payload.get("active_player_id") == historical.active_player_id
            and payload.get("source_rule_id") == source_rule_id
            and payload.get("use_ability") is True
        ):
            selected.add(_identifier(payload.get("target_unit_instance_id"), "prior target ID"))
    return frozenset(selected)


@dataclass(frozen=True, slots=True)
class _ExpectedOption:
    option_id: str
    target_unit_instance_id: str
    payload: dict[str, JsonValue]


def _expected_option(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
    target_unit_instance_id: str,
    sequence: AttackSequence,
    completion_event_id: str,
    optional: bool,
) -> _ExpectedOption:
    common = _common_payload(
        historical=historical,
        record=record,
        source_unit=source_unit,
        source_model_instance_id=source_model_instance_id,
        selection_clause=selection_clause,
        effect_clauses=effect_clauses,
        sequence=sequence,
        completion_event_id=completion_event_id,
        optional=optional,
    )
    option_id = selected_target_option_id(
        record=record,
        unit=source_unit,
        source_model_instance_id=source_model_instance_id,
        selection_clause=selection_clause,
        target_unit_instance_id=target_unit_instance_id,
        attack_sequence_completed_event_id=completion_event_id,
    )
    payload = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                **common,
                **({"use_ability": True} if optional else {}),
                "selected_catalog_target_effect": {
                    "option_id": option_id,
                    "target_unit_instance_id": target_unit_instance_id,
                },
                "generic_rule_effect_records": list(
                    _effect_records(
                        historical=historical,
                        record=record,
                        source_unit=source_unit,
                        source_model_instance_id=source_model_instance_id,
                        selection_clause=selection_clause,
                        effect_clauses=effect_clauses,
                        target_unit_instance_id=target_unit_instance_id,
                        sequence=sequence,
                        completion_event_id=completion_event_id,
                    )
                ),
            }
        ),
    )
    return _ExpectedOption(
        option_id=option_id,
        target_unit_instance_id=target_unit_instance_id,
        payload=payload,
    )


def _common_payload(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
    sequence: AttackSequence,
    completion_event_id: str,
    optional: bool,
) -> dict[str, JsonValue]:
    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "submission_kind": (SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND),
                "hook_id": CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                "game_id": historical.game_id,
                "battle_round": historical.request.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": historical.active_player_id,
                "player_id": historical.rules_unit_containing_unit(
                    source_unit.unit_instance_id
                ).owner_player_id,
                "catalog_record_id": record.record_id,
                "ability_id": record.definition.ability_id,
                "ability_name": record.definition.name,
                "source_rule_id": record.definition.source_id,
                "rule_ir_hash": rule_ir.ir_hash(),
                "source_unit_instance_id": source_unit.unit_instance_id,
                "source_model_instance_id": source_model_instance_id,
                "selection_clause_id": selection_clause.clause_id,
                "selection_clause": selection_clause.to_payload(),
                "effect_clause_ids": [clause.clause_id for clause in effect_clauses],
                "attack_sequence_id": sequence.sequence_id,
                "attack_sequence": sequence.to_payload(),
                "attack_sequence_completed_event_id": completion_event_id,
                **({"optional": True} if optional else {}),
            }
        ),
    )


def _effect_records(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
    target_unit_instance_id: str,
    sequence: AttackSequence,
    completion_event_id: str,
) -> tuple[dict[str, JsonValue], ...]:
    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
    rows: list[dict[str, JsonValue]] = []
    for clause in effect_clauses:
        if not _status_gate_allows(
            historical=historical,
            clause=clause,
            target_unit_instance_id=target_unit_instance_id,
        ):
            continue
        target_ids = _historical_effect_target_ids(
            historical=historical,
            source_player_id=historical.rules_unit_containing_unit(
                source_unit.unit_instance_id
            ).owner_player_id,
            source_unit=source_unit,
            target_unit_instance_id=target_unit_instance_id,
            clause=clause,
        )
        if not target_ids:
            continue
        for effect_index, effect in enumerate(clause.effects):
            transformed = effect_with_selected_target(
                effect,
                selected_target_unit_instance_id=target_unit_instance_id,
                clause=clause,
            )
            context = RuleExecutionContext(
                game_id=historical.game_id,
                player_id=historical.rules_unit_containing_unit(
                    source_unit.unit_instance_id
                ).owner_player_id,
                battle_round=historical.request.battle_round,
                phase=BattlePhaseKind.SHOOTING,
                active_player_id=historical.active_player_id,
                timing_window_id="attack_sequence_completed",
                source_unit_instance_id=source_unit.unit_instance_id,
                source_model_instance_id=source_model_instance_id,
                target_unit_instance_ids=target_ids,
                source_keywords=tuple(
                    sorted((*source_unit.keywords, *source_unit.faction_keywords))
                ),
                trigger_payload={
                    "selected_target_unit_instance_ids": [target_unit_instance_id],
                    "selected_target_unit_instance_id": target_unit_instance_id,
                    "target_unit_statuses": (
                        ["battle_shocked"]
                        if target_unit_instance_id in historical.battle_shocked_unit_ids
                        else []
                    ),
                    "catalog_record_id": record.record_id,
                    "selection_clause_id": selection_clause.clause_id,
                    "submission_kind": (
                        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND
                    ),
                },
                state=None,
                event_log=None,
                record_persisting_effects=False,
            )
            immediate_kind: str | None = None
            if clause.duration is None and effect_is_immediate_selected_target_battle_shock(effect):
                immediate_kind = "force_battle_shock_test"
            elif clause.duration is None and effect_is_immediate_selected_target_mortal_wounds(
                effect
            ):
                immediate_kind = "inflict_mortal_wounds"
            row: dict[str, object] = {
                "source_rule_id": record.definition.source_id,
                "owner_player_id": context.player_id,
                "target_unit_instance_ids": list(target_ids),
                "started_battle_round": historical.request.battle_round,
                "started_phase": BattlePhaseKind.SHOOTING.value,
                "expiration": _expiration(
                    clause=clause,
                    context=context,
                ).to_payload(),
                "effect_payload": {
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "rule_id": rule_ir.rule_id,
                    "source_id": record.definition.source_id,
                    "rule_ir_hash": rule_ir.ir_hash(),
                    "clause_id": clause.clause_id,
                    "effect_index": effect_index,
                    "source_span": clause.source_span.to_payload(),
                    "target": None if clause.target is None else clause.target.to_payload(),
                    "target_unit_instance_ids": list(target_ids),
                    "duration": None if clause.duration is None else clause.duration.to_payload(),
                    "effect": transformed.to_payload(),
                    "conditions": [condition.to_payload() for condition in clause.conditions],
                    "context": context.to_payload(),
                    "catalog_selected_target": {
                        "hook_id": CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                        "submission_kind": (
                            SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND
                        ),
                        "catalog_record_id": record.record_id,
                        "ability_id": record.definition.ability_id,
                        "ability_name": record.definition.name,
                        "source_unit_instance_id": source_unit.unit_instance_id,
                        "source_model_instance_id": source_model_instance_id,
                        "selection_clause_id": selection_clause.clause_id,
                        "selected_target_unit_instance_id": target_unit_instance_id,
                        "attack_sequence_id": sequence.sequence_id,
                        "attack_sequence_completed_event_id": completion_event_id,
                    },
                },
                "catalog_record_id": record.record_id,
                "ability_id": record.definition.ability_id,
                "ability_name": record.definition.name,
                "source_unit_instance_id": source_unit.unit_instance_id,
                "source_model_instance_id": source_model_instance_id,
                "selection_clause_id": selection_clause.clause_id,
                "effect_clause_id": clause.clause_id,
                "effect_index": effect_index,
                "selected_target_unit_instance_id": target_unit_instance_id,
            }
            if immediate_kind is not None:
                row["immediate_effect_kind"] = immediate_kind
            if clause_requires_prior_mortal_wounds(clause):
                row["immediate_effect_condition"] = "prior_effect_inflicted_mortal_wounds"
            rows.append(cast(dict[str, JsonValue], validate_json_value(row)))
    return tuple(rows)


def _status_gate_allows(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    clause: RuleClause,
    target_unit_instance_id: str,
) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
            continue
        parameters = parameter_payload(condition.parameters)
        if parameters.get("relationship") != "target_unit_has_status":
            continue
        if parameters.get("status") != "battle_shocked":
            raise GameLifecycleError("Selected-target status condition is unsupported.")
        return target_unit_instance_id in historical.battle_shocked_unit_ids
    return True


def _historical_effect_target_ids(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    source_player_id: str,
    source_unit: UnitInstance,
    target_unit_instance_id: str,
    clause: RuleClause,
) -> tuple[str, ...]:
    if clause.target is None:
        return ()
    source_id = historical.rules_unit_containing_unit(source_unit.unit_instance_id).unit_instance_id
    if clause.target.kind in {RuleTargetKind.THIS_MODEL, RuleTargetKind.THIS_UNIT}:
        return (source_id,)
    if clause.target.kind in {
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.SELECTED_TARGET,
        RuleTargetKind.SELECTED_UNIT,
    }:
        return (historical.rules_unit(target_unit_instance_id).unit_instance_id,)
    if clause.target.kind is not RuleTargetKind.FRIENDLY_UNIT:
        return ()
    required = required_keywords_for_clause(clause)
    return tuple(
        unit.unit_instance_id
        for unit in historical.all_rules_units()
        if unit.owner_player_id == source_player_id
        and (
            not required
            or unit_has_required_keywords(
                unit_keywords=unit.keywords,
                faction_keywords=unit.faction_keywords,
                required_keywords=required,
            )
        )
    )


def _expiration(
    *,
    clause: RuleClause,
    context: RuleExecutionContext,
) -> EffectExpiration:
    if clause.duration is None:
        return EffectExpiration.end_phase(
            battle_round=context.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=_identifier(context.active_player_id, "active player ID"),
        )
    if clause.duration.kind is RuleDurationKind.PERMANENT:
        return EffectExpiration.end_of_battle()
    expiration = expiration_for_duration(duration=clause.duration, context=context)
    if expiration is None:
        raise GameLifecycleError("Selected-target duration lacks an expiration.")
    return expiration


def _validate_exact_request(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    source_record: DecisionRecord,
    loaded_record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
    sequence: AttackSequence,
    expected_options: tuple[_ExpectedOption, ...],
) -> None:
    optional = post_shoot_target_selection_is_optional(selection_clause)
    completion_id = _identifier(
        _object(source_record.request.payload, "selected-target request").get(
            "attack_sequence_completed_event_id"
        ),
        "completion event ID",
    )
    common = _common_payload(
        historical=historical,
        record=loaded_record,
        source_unit=source_unit,
        source_model_instance_id=source_model_instance_id,
        selection_clause=selection_clause,
        effect_clauses=effect_clauses,
        sequence=sequence,
        completion_event_id=completion_id,
        optional=optional,
    )
    request_payload = _object(source_record.request.payload, "selected-target request")
    expected_request_payload = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                **common,
                "available_target_unit_instance_ids": [
                    option.target_unit_instance_id for option in expected_options
                ],
                "available_catalog_selected_target_options": [
                    {
                        "option_id": option.option_id,
                        "target_unit_instance_id": option.target_unit_instance_id,
                    }
                    for option in expected_options
                ],
                **({"optional": True} if optional else {}),
            }
        ),
    )
    _ignore_display_names(expected_request_payload, request_payload)
    expected_decision_options = [
        {
            "option_id": option.option_id,
            "label": f"Select {option.target_unit_instance_id}",
            "payload": option.payload,
        }
        for option in expected_options
    ]
    if optional:
        expected_decision_options.append(
            {
                "option_id": (
                    f"{CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID}:"
                    f"{loaded_record.record_id}:decline"
                ),
                "label": "Do not use this ability",
                "payload": {
                    **common,
                    "use_ability": False,
                    "selected_catalog_target_effect": None,
                    "generic_rule_effect_records": [],
                },
            }
        )
    expected_decision_options.sort(key=lambda option: cast(str, option["option_id"]))
    observed_options = [option.to_payload() for option in source_record.request.options]
    for expected, observed in zip(expected_decision_options, observed_options, strict=False):
        expected_payload = _object(expected["payload"], "expected option payload")
        observed_payload = _object(observed["payload"], "observed option payload")
        _ignore_display_names(expected_payload, observed_payload)
    selected_options = tuple(
        option
        for option in source_record.request.options
        if option.option_id == source_record.result.selected_option_id
    )
    if (
        source_record.request.decision_type
        != SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
        or source_record.request.actor_id
        != historical.rules_unit_containing_unit(source_unit.unit_instance_id).owner_player_id
        or request_payload != expected_request_payload
        or observed_options != expected_decision_options
        or len(selected_options) != 1
        or source_record.result.payload != selected_options[0].payload
    ):
        raise GameLifecycleError("Selected-target loaded decision inventory drifted.")


def _ignore_display_names(
    expected: dict[str, JsonValue],
    observed: dict[str, JsonValue],
) -> None:
    observed_name = observed.get("ability_name")
    if type(observed_name) is not str or not observed_name:
        raise GameLifecycleError("Selected-target audit display name is invalid.")
    expected["ability_name"] = observed_name
    expected_effects = expected.get("generic_rule_effect_records")
    observed_effects = observed.get("generic_rule_effect_records")
    if not isinstance(expected_effects, list) or not isinstance(observed_effects, list):
        return
    if len(expected_effects) != len(observed_effects):
        return
    for raw_expected, raw_observed in zip(expected_effects, observed_effects, strict=True):
        if not isinstance(raw_expected, dict) or not isinstance(raw_observed, dict):
            continue
        name = raw_observed.get("ability_name")
        if type(name) is not str or not name:
            raise GameLifecycleError("Selected-target effect audit display name is invalid.")
        raw_expected["ability_name"] = name
        expected_payload = raw_expected.get("effect_payload")
        observed_payload = raw_observed.get("effect_payload")
        if not isinstance(expected_payload, dict) or not isinstance(observed_payload, dict):
            continue
        expected_catalog = expected_payload.get("catalog_selected_target")
        observed_catalog = observed_payload.get("catalog_selected_target")
        if isinstance(expected_catalog, dict) and isinstance(observed_catalog, dict):
            nested_name = observed_catalog.get("ability_name")
            if type(nested_name) is not str or not nested_name:
                raise GameLifecycleError("Selected-target nested audit display name is invalid.")
            expected_catalog["ability_name"] = nested_name


def _object(value: object, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{context} must be an object.")
    return cast(dict[str, JsonValue], value)


def _identifier(value: object, context: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Selected-target {context} must be an identifier.")
    return value


def _optional_identifier(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, context)


__all__ = ("validate_catalog_selected_target_loaded_source_authority",)
