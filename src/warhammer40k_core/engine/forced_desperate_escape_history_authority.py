from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.battle_shock_stratagem_authority import (
    historical_stratagem_generic_rule_execution_result,
)
from warhammer40k_core.engine.catalog_desperate_escape import (
    CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND,
    battle_shocked_modifier_for_record,
    falling_back_unit_allowed,
    force_desperate_escape_clause,
    matching_desperate_escape_records,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    geometry_models_are_physically_engaged,
)
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.stratagem_use_history_authority import (
    FiniteStratagemUseHistoryAuthority,
    StratagemUseHistoryAuthority,
    validate_loaded_stratagem_use_provider,
    validate_stratagem_use_history,
)
from warhammer40k_core.engine.stratagems_model import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemEligibilityContext,
    StratagemTargetBinding,
)
from warhammer40k_core.rules.rule_ir import RuleEffectKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState

_CATALOG_KEYS = frozenset(
    {
        "effect_id",
        "source_kind",
        "source_rule_id",
        "catalog_record_id",
        "ability_id",
        "ability_name",
        "rule_ir_hash",
        "forcing_unit_instance_id",
        "fall_back_unit_instance_id",
        "required_fall_back_mode",
        "desperate_escape_roll_modifier",
        "battle_round",
        "phase",
    }
)
_STRATAGEM_KEYS = frozenset(
    {
        "effect_id",
        "source_rule_id",
        "stratagem_use_id",
        "source_stratagem_id",
        "forcing_unit_instance_id",
        "fall_back_unit_instance_id",
        "required_fall_back_mode",
    }
)
_REGISTERED_EVENT_KEYS = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "active_player_id",
        "stratagem_use",
        "forcing_unit_instance_id",
        "fall_back_unit_instance_id",
        "persisting_effect",
    }
)


def validate_forced_desperate_escape_loaded_source_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    request: BattleShockTestRequest,
    movement_record: DecisionRecord,
    sources: tuple[dict[str, JsonValue], ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Recompute every forced-Desperate-Escape source at the proposal boundary."""

    proposal_indexes = tuple(
        index
        for index, event in enumerate(event_records[:request_event_index])
        if event.event_type == "decision_requested"
        and event.payload == movement_record.request.to_payload()
    )
    if len(proposal_indexes) != 1:
        raise GameLifecycleError("Desperate Escape proposal source boundary drifted.")
    proposal_index = proposal_indexes[0]
    historical = historical_battle_shock_authority_context(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        boundary_event_index=proposal_index,
        request=request,
        active_player_id=_active_player_id(movement_record),
        phase=BattlePhase.MOVEMENT,
        phase_start_battle_shocked_unit_ids=(),
    )
    catalog_sources = tuple(
        source
        for source in sources
        if source.get("source_kind") == CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND
    )
    expected_catalog_sources = _historical_catalog_sources(
        state=state,
        historical=historical,
        fall_back_unit_instance_id=request.unit_instance_id,
        runtime_content_bundle=runtime_content_bundle,
    )
    if tuple(_catalog_source_without_display_name(row) for row in catalog_sources) != tuple(
        _catalog_source_without_display_name(row) for row in expected_catalog_sources
    ):
        raise GameLifecycleError("Desperate Escape catalog source inventory drifted.")
    stratagem_sources = tuple(source for source in sources if "source_kind" not in source)
    if len(catalog_sources) + len(stratagem_sources) != len(sources):
        raise GameLifecycleError("Desperate Escape source kind is unsupported.")
    for source in stratagem_sources:
        _validate_stratagem_source(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            proposal_index=proposal_index,
            source=source,
            runtime_content_bundle=runtime_content_bundle,
        )


def _historical_catalog_sources(
    *,
    state: GameState,
    historical: HistoricalBattleShockAuthorityContext,
    fall_back_unit_instance_id: str,
    runtime_content_bundle: RuntimeContentBundle,
) -> tuple[dict[str, JsonValue], ...]:
    target_unit, target_army = historical.unit_and_army(fall_back_unit_instance_id)
    sources: list[dict[str, JsonValue]] = []
    for army in sorted(historical.armies, key=lambda value: value.player_id):
        if army.player_id == target_army.player_id:
            continue
        index = runtime_content_bundle.ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Desperate Escape catalog ability index is missing.")
        for source_unit in sorted(army.units, key=lambda value: value.unit_instance_id):
            model_ids = historical.component_placed_alive_model_ids(source_unit.unit_instance_id)
            if not model_ids:
                continue
            for record in matching_desperate_escape_records(
                index=index,
                unit=source_unit,
                current_model_instance_ids=model_ids,
            ):
                clause = force_desperate_escape_clause(record)
                if clause is None or not falling_back_unit_allowed(
                    clause=clause,
                    unit=target_unit,
                ):
                    continue
                if not geometry_models_are_physically_engaged(
                    first_models=historical.component_geometry_models(source_unit.unit_instance_id),
                    second_models=historical.geometry_models(fall_back_unit_instance_id),
                    ruleset_descriptor=state.runtime_ruleset_descriptor(),
                ):
                    continue
                if not catalog_rule_record_source_matches_unit(
                    record=record,
                    unit=source_unit,
                    current_model_instance_ids=model_ids,
                ):
                    raise GameLifecycleError("Desperate Escape catalog component source drifted.")
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                sources.append(
                    cast(
                        dict[str, JsonValue],
                        validate_json_value(
                            {
                                "effect_id": (
                                    f"{record.record_id}:force-desperate-escape:"
                                    f"{fall_back_unit_instance_id}"
                                ),
                                "source_kind": CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND,
                                "source_rule_id": record.definition.source_id,
                                "catalog_record_id": record.record_id,
                                "ability_id": record.definition.ability_id,
                                "ability_name": record.definition.name,
                                "rule_ir_hash": rule_ir.ir_hash(),
                                "forcing_unit_instance_id": source_unit.unit_instance_id,
                                "fall_back_unit_instance_id": fall_back_unit_instance_id,
                                "required_fall_back_mode": "desperate_escape",
                                "desperate_escape_roll_modifier": (
                                    battle_shocked_modifier_for_record(
                                        record=record,
                                        target_unit_instance_id=(fall_back_unit_instance_id),
                                        battle_shocked_unit_ids=(
                                            historical.battle_shocked_unit_ids
                                        ),
                                    )
                                ),
                                "battle_round": historical.request.battle_round,
                                "phase": BattlePhase.MOVEMENT.value,
                            }
                        ),
                    )
                )
    rows = tuple(sorted(sources, key=lambda value: str(value["effect_id"])))
    if any(frozenset(row) != _CATALOG_KEYS for row in rows):
        raise GameLifecycleError("Desperate Escape catalog source shape drifted.")
    return rows


def _validate_stratagem_source(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    proposal_index: int,
    source: dict[str, JsonValue],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    if frozenset(source) != _STRATAGEM_KEYS:
        raise GameLifecycleError("Desperate Escape Stratagem source shape drifted.")
    use_id = _identifier(source.get("stratagem_use_id"), "Stratagem use ID")
    uses = tuple(use for use in state.stratagem_use_records if use.use_id == use_id)
    if len(uses) != 1:
        raise GameLifecycleError("Desperate Escape Stratagem use authority drifted.")
    use = uses[0]
    history = validate_stratagem_use_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        use_record=use,
        mutation_index=proposal_index,
    )
    validate_loaded_stratagem_use_provider(
        authority=history,
        runtime_content_bundle=runtime_content_bundle,
        built_in_handler_ids=frozenset({GENERIC_RULE_IR_STRATAGEM_HANDLER_ID}),
    )
    if use.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        raise GameLifecycleError("Desperate Escape Stratagem handler authority drifted.")
    rule_result = historical_stratagem_generic_rule_execution_result(
        state=state,
        history=history,
    )
    recorded_rule_events: list[EventRecord] = []
    for expected_rule_event in rule_result.event_records:
        matches = tuple(
            event
            for event in event_records[history.recorded_event_index + 1 : proposal_index]
            if event.event_type == expected_rule_event.event_type
            and event.payload == expected_rule_event.payload
        )
        if len(matches) != 1:
            raise GameLifecycleError("Desperate Escape Stratagem RuleIR event authority drifted.")
        recorded_rule_events.append(matches[0])
    rule_result = replace(rule_result, event_records=tuple(recorded_rule_events))
    force_effects = tuple(
        effect
        for effect in rule_result.effect_payloads
        if _generic_effect_kind(effect) == RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS.value
    )
    if len(force_effects) != 1:
        raise GameLifecycleError("Desperate Escape Stratagem RuleIR effect drifted.")
    generic_effect = force_effects[0]
    source_rule_id = _identifier(generic_effect.get("source_id"), "source rule ID")
    context = _history_context(history)
    target_binding = _history_target_binding(history)
    forcing_unit_id = target_binding.target_unit_instance_id
    if forcing_unit_id is None:
        raise GameLifecycleError("Desperate Escape Stratagem forcing unit is missing.")
    fall_back_unit_id = _identifier(
        source.get("fall_back_unit_instance_id"),
        "Fall Back unit ID",
    )
    expected_effect = PersistingEffect(
        effect_id=f"{use.use_id}:force-desperate-escape:{fall_back_unit_id}",
        source_rule_id=source_rule_id,
        owner_player_id=use.player_id,
        target_unit_instance_ids=(fall_back_unit_id,),
        started_battle_round=use.battle_round,
        started_phase=BattlePhaseKind.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=use.battle_round,
            phase=BattlePhaseKind.MOVEMENT,
            player_id=context.active_player_id or use.player_id,
        ),
        effect_payload={
            "effect_kind": "forced_fall_back_desperate_escape",
            "stratagem_use_id": use.use_id,
            "source_rule_id": source_rule_id,
            "source_stratagem_id": use.stratagem_id,
            "forcing_unit_instance_id": forcing_unit_id,
            "fall_back_unit_instance_id": fall_back_unit_id,
            "required_fall_back_mode": "desperate_escape",
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(generic_effect),
        },
    )
    expected_source = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "effect_id": expected_effect.effect_id,
                "source_rule_id": source_rule_id,
                "stratagem_use_id": use.use_id,
                "source_stratagem_id": use.stratagem_id,
                "forcing_unit_instance_id": forcing_unit_id,
                "fall_back_unit_instance_id": fall_back_unit_id,
                "required_fall_back_mode": "desperate_escape",
            }
        ),
    )
    if source != expected_source:
        raise GameLifecycleError("Desperate Escape Stratagem source semantics drifted.")
    expected_event = validate_json_value(
        {
            "game_id": context.game_id,
            "player_id": use.player_id,
            "battle_round": use.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": context.active_player_id,
            "stratagem_use": use.to_payload(),
            "forcing_unit_instance_id": forcing_unit_id,
            "fall_back_unit_instance_id": fall_back_unit_id,
            "persisting_effect": expected_effect.to_payload(),
        }
    )
    registered_matches = tuple(
        index
        for index, event in enumerate(event_records[:proposal_index])
        if event.event_type == "forced_fall_back_desperate_escape_registered"
        and event.payload == expected_event
    )
    if (
        len(registered_matches) != 1
        or not isinstance(expected_event, dict)
        or (frozenset(expected_event) != _REGISTERED_EVENT_KEYS)
    ):
        raise GameLifecycleError("Desperate Escape Stratagem creation authority drifted.")


def _history_context(
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
) -> StratagemEligibilityContext:
    if isinstance(history, FiniteStratagemUseHistoryAuthority):
        return history.context
    return history.submitted_proposal.context


def _history_target_binding(
    history: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
) -> StratagemTargetBinding:
    if isinstance(history, FiniteStratagemUseHistoryAuthority):
        return history.target_binding
    binding = history.submitted_proposal.target_binding
    if binding is None:
        raise GameLifecycleError("Desperate Escape Stratagem target binding is missing.")
    return binding


def _generic_effect_kind(payload: dict[str, JsonValue]) -> str | None:
    raw_effect = payload.get("effect")
    if not isinstance(raw_effect, dict):
        return None
    value = raw_effect.get("kind")
    return value if type(value) is str else None


def _active_player_id(record: DecisionRecord) -> str:
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest

    proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    context = proposal.context or {}
    value = context.get("active_player_id")
    if type(value) is not str or not value:
        value = proposal.actor_id
    if type(value) is not str or not value:
        raise GameLifecycleError("Desperate Escape active-player authority is missing.")
    return value


def _identifier(value: JsonValue, context: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Desperate Escape {context} must be an identifier.")
    return value


def _catalog_source_without_display_name(
    source: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    name = source.get("ability_name")
    if type(name) is not str or not name:
        raise GameLifecycleError("Desperate Escape audit display name is invalid.")
    return {**source, "ability_name": "audit-display-name"}


__all__ = ("validate_forced_desperate_escape_loaded_source_authority",)
