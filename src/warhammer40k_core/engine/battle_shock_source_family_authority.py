from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockModifierApplication
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    BattleShockResolutionAuthority,
    PendingBattleShockRerollAuthority,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_rule_states import (
    FactionRuleState,
    FactionRuleStatePayload,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.battle_shock_historical_authority import (
        HistoricalBattleShockAuthorityContext,
    )
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


_COMMAND_SOURCE = "command_battle_shock"
_COMMAND_START_SOURCE = "command_phase_start_battle_shock"
_STRATAGEM_SOURCE = "stratagem_battle_shock"
_CATALOG_SELECTED_SOURCE = "catalog_selected_target_effect"
_MOVE_COMPLETED_SOURCE = "unit_move_completed_battle_shock"
_FORCED_DESPERATE_ESCAPE_SOURCE = "forced_desperate_escape_battle_shock"

_COMMAND_BASE_KEYS = frozenset(
    {"game_id", "battle_round", "active_player_id", "phase", "source_kind"}
)
_COMMAND_START_BASE_KEYS = frozenset({*_COMMAND_BASE_KEYS, "source_faction_rule_state"})
_SELECTED_TARGET_BASE_KEYS = frozenset(
    {
        *_COMMAND_BASE_KEYS,
        "hook_id",
        "catalog_record_id",
        "source_rule_id",
        "source_unit_instance_id",
        "selection_clause_id",
        "effect_clause_id",
        "effect_index",
        "selected_target_unit_instance_id",
        "target_unit_instance_id",
        "target_identity_resolution",
        "target_player_id",
        "effect_payload",
        "selected_target_decision_result",
        "selected_target_payload",
        "selected_target_recorded_effects_before_battle_shock",
        "selected_target_remaining_effect_records_after_battle_shock",
        "selected_target_remaining_effect_start_index",
    }
)
_MOVE_COMPLETED_BASE_KEYS = frozenset(
    {
        *_COMMAND_BASE_KEYS,
        "trigger_event_id",
        "movement_action",
        "hook_id",
        "effect_key",
        "source_rule_id",
        "target_unit_instance_id",
        "target_player_id",
        "replay_payload",
    }
)
_FORCED_DESPERATE_ESCAPE_BASE_KEYS = frozenset(
    {
        *_COMMAND_BASE_KEYS,
        "unit_instance_id",
        "source_rule_ids",
        "source_rule_id",
        "fall_back_result",
        "action_result",
        "movement_proposal_request_id",
    }
)


def validate_battle_shock_source_family_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    resolved_index: int,
    request_payload: dict[str, JsonValue],
    request_context: dict[str, JsonValue],
    request_base: dict[str, JsonValue],
    result: BattleShockResult,
) -> None:
    """Bind one structurally complete resolution to its exact producer family."""
    source_kind = request_base.get("source_kind")
    if type(source_kind) is not str:
        raise GameLifecycleError("Battle-shock result lacks recognized source authority.")
    prior_events = event_records[:resolved_index]
    if source_kind == _COMMAND_SOURCE:
        if (
            frozenset(request_base) != _COMMAND_BASE_KEYS
            or request_base.get("phase") != "command"
            or result.request.reason
            not in {
                BattleShockTestReason.COMMAND_PHASE_REQUIRED,
                BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
            }
            or _matching_command_snapshots(
                prior_events=prior_events,
                request_payload=request_payload,
                request_base=request_base,
            )
            != 1
        ):
            raise GameLifecycleError("Battle-shock Command source authority drifted.")
        return
    if source_kind == _STRATAGEM_SOURCE:
        source_use = request_base.get("source_stratagem_use")
        if (
            result.request.reason is not BattleShockTestReason.FORCED_BY_STRATAGEM
            or not isinstance(source_use, dict)
            or sum(
                event.event_type == "stratagem_used" and event.payload == source_use
                for event in prior_events
            )
            != 1
        ):
            raise GameLifecycleError("Battle-shock Stratagem source authority drifted.")
        _validate_source_decision_ids(
            event_records=event_records,
            decision_records=decision_records,
            resolved_index=resolved_index,
            source_payload=source_use,
        )
        return
    if source_kind == _COMMAND_START_SOURCE:
        source_state = request_base.get("source_faction_rule_state")
        if (
            frozenset(request_base) != _COMMAND_START_BASE_KEYS
            or result.request.reason is not BattleShockTestReason.FORCED_BY_ARMY_RULE
            or request_base.get("phase") != "command"
            or not isinstance(source_state, dict)
        ):
            raise GameLifecycleError("Battle-shock Command-start source authority drifted.")
        _validate_source_decision_ids(
            event_records=event_records,
            decision_records=decision_records,
            resolved_index=resolved_index,
            source_payload=source_state,
        )
        return
    if source_kind == _CATALOG_SELECTED_SOURCE:
        _validate_selected_target_source(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=resolved_index,
            request=result.request,
            base=request_base,
        )
        return
    if source_kind == _MOVE_COMPLETED_SOURCE:
        trigger_id = request_base.get("trigger_event_id")
        if (
            frozenset(request_base) != _MOVE_COMPLETED_BASE_KEYS
            or type(trigger_id) is not str
            or sum(event.event_id == trigger_id for event in prior_events) != 1
        ):
            raise GameLifecycleError("Battle-shock move-completed source authority drifted.")
        return
    if source_kind == _FORCED_DESPERATE_ESCAPE_SOURCE:
        _validate_forced_desperate_escape_source(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=resolved_index,
            request=result.request,
            request_context=request_context,
            base=request_base,
        )
        return
    raise GameLifecycleError("Battle-shock result source kind is unsupported.")


def validate_pending_battle_shock_source_family_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    authority: PendingBattleShockRerollAuthority,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Bind one live reroll to the exact producer that requested its test."""
    source_kind = authority.source_kind
    request = authority.test_request
    base = authority.base_payload
    expected_event_types = {
        _COMMAND_SOURCE: ("battle_shock_test_resolved",),
        _COMMAND_START_SOURCE: ("battle_shock_test_resolved",),
        _STRATAGEM_SOURCE: ("battle_shock_test_resolved",),
        _CATALOG_SELECTED_SOURCE: (
            "battle_shock_test_resolved",
            "catalog_selected_target_battle_shock_resolved",
        ),
        _MOVE_COMPLETED_SOURCE: (
            "battle_shock_test_resolved",
            "unit_move_completed_battle_shock_resolved",
        ),
        _FORCED_DESPERATE_ESCAPE_SOURCE: (
            "battle_shock_test_resolved",
            "forced_desperate_escape_battle_shock_resolved",
        ),
    }.get(source_kind)
    if expected_event_types is None:
        raise GameLifecycleError("Pending Battle-shock source kind is unsupported.")
    if authority.resolved_event_types != expected_event_types:
        raise GameLifecycleError("Pending Battle-shock resolved-event inventory drifted.")
    if source_kind == _COMMAND_SOURCE:
        if (
            frozenset(base) != _COMMAND_BASE_KEYS
            or request.reason
            not in {
                BattleShockTestReason.COMMAND_PHASE_REQUIRED,
                BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
            }
            or _matching_command_snapshots(
                prior_events=event_records[:request_event_index],
                request_payload=cast(dict[str, JsonValue], request.to_payload()),
                request_base=base,
            )
            != 1
        ):
            raise GameLifecycleError("Pending Command Battle-shock source authority drifted.")
        return
    if source_kind == _COMMAND_START_SOURCE:
        _validate_pending_command_start_source(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=request_event_index,
            authority=authority,
        )
        return
    if source_kind == _STRATAGEM_SOURCE:
        from warhammer40k_core.engine.battle_shock_stratagem_authority import (
            validate_stratagem_battle_shock_source_authority,
        )

        source = validate_stratagem_battle_shock_source_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=request_event_index,
            request=request,
            request_base=base,
            runtime_content_bundle=runtime_content_bundle,
        )
        if authority.additional_modifier_applications != source.additional_modifier_applications:
            raise GameLifecycleError("Pending Stratagem Battle-shock applications drifted.")
        return
    if authority.additional_modifier_applications:
        raise GameLifecycleError("Pending Battle-shock has unsupported source applications.")
    if source_kind == _CATALOG_SELECTED_SOURCE:
        _validate_pending_selected_target_source(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=request_event_index,
            authority=authority,
            runtime_content_bundle=runtime_content_bundle,
        )
        return
    if source_kind == _MOVE_COMPLETED_SOURCE:
        from warhammer40k_core.engine.battle_shock_event_authority import (
            validate_unit_move_completed_battle_shock_request_authority,
        )

        validate_unit_move_completed_battle_shock_request_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=request_event_index,
            request_base=base,
            request=request,
            active_player_id=authority.active_player_id,
            phase=authority.phase,
            phase_start_battle_shocked_unit_ids=(authority.phase_start_battle_shocked_unit_ids),
            runtime_content_bundle=runtime_content_bundle,
        )
        return
    _validate_pending_forced_desperate_escape_source(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_event_index=request_event_index,
        authority=authority,
        runtime_content_bundle=runtime_content_bundle,
    )


def validate_battle_shock_runtime_source_family_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    authority: BattleShockResolutionAuthority,
    historical: HistoricalBattleShockAuthorityContext,
    modifier_applications: tuple[BattleShockModifierApplication, ...],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Rebind a completed source occurrence to exact loaded, event-bound authority."""
    source_kind = authority.base_payload.get("source_kind")
    result = authority.result
    if source_kind == _STRATAGEM_SOURCE:
        from warhammer40k_core.engine.battle_shock_stratagem_authority import (
            validate_stratagem_battle_shock_source_authority,
        )

        source = validate_stratagem_battle_shock_source_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=authority.request_event_index,
            request=result.request,
            request_base=authority.base_payload,
            runtime_content_bundle=runtime_content_bundle,
        )
        source_applications = tuple(
            application
            for application in modifier_applications
            if application.hook_id == source.history.use_record.handler_id
        )
        if source_applications != source.additional_modifier_applications:
            raise GameLifecycleError(
                "Completed Stratagem Battle-shock source applications drifted."
            )
        return
    if source_kind == _COMMAND_START_SOURCE:
        _validate_completed_command_start_source(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            authority=authority,
            historical=historical,
            runtime_content_bundle=runtime_content_bundle,
        )
        return
    if source_kind == _CATALOG_SELECTED_SOURCE:
        matched = _validate_selected_target_source(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=authority.request_event_index,
            request=result.request,
            base=authority.base_payload,
        )
        _validate_loaded_selected_target_source_history(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=authority.request_event_index,
            request=result.request,
            matched=matched,
            base=authority.base_payload,
            runtime_content_bundle=runtime_content_bundle,
        )
        return
    if source_kind == _MOVE_COMPLETED_SOURCE:
        from warhammer40k_core.engine.battle_shock_event_authority import (
            validate_unit_move_completed_battle_shock_request_authority,
        )

        validate_unit_move_completed_battle_shock_request_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=authority.request_event_index,
            request_base=authority.base_payload,
            request=result.request,
            active_player_id=authority.active_player_id,
            phase=authority.phase,
            phase_start_battle_shocked_unit_ids=(authority.phase_start_battle_shocked_unit_ids),
            runtime_content_bundle=runtime_content_bundle,
        )
        return
    if source_kind == _FORCED_DESPERATE_ESCAPE_SOURCE:
        movement_record = _validate_forced_desperate_escape_source(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=authority.request_event_index,
            request=result.request,
            request_context=authority.request_context,
            base=authority.base_payload,
        )
        _validate_loaded_forced_desperate_escape_source_history(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            request_event_index=authority.request_event_index,
            request=result.request,
            movement_record=movement_record,
            base=authority.base_payload,
            runtime_content_bundle=runtime_content_bundle,
        )


def _validate_completed_command_start_source(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    authority: BattleShockResolutionAuthority,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    from warhammer40k_core.engine.command_phase_start_hooks import (
        CommandPhaseStartCompletedBattleShockAuthorityContext,
    )

    raw_state = authority.base_payload.get("source_faction_rule_state")
    if not isinstance(raw_state, dict):
        raise GameLifecycleError("Completed Command-start Battle-shock source is invalid.")
    source_state = FactionRuleState.from_payload(cast(FactionRuleStatePayload, raw_state))
    if sum(candidate == source_state for candidate in state.faction_rule_states) != 1:
        raise GameLifecycleError("Completed Command-start Battle-shock state drifted.")
    source_payload = _object(source_state.payload, "Command-start source-state payload")
    hook_id = source_payload.get("hook_id")
    if type(hook_id) is not str or not hook_id:
        raise GameLifecycleError("Completed Command-start hook identity is invalid.")
    record = _source_decision_record(
        decision_records=decision_records,
        source_state=source_state,
    )
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=authority.request_event_index,
        request_id=source_state.request_id,
        result_id=source_state.result_id,
    )
    runtime_content_bundle.command_phase_start_hook_registry.validate_completed_battle_shock_authority(
        hook_id=hook_id,
        source_id=source_state.source_rule_id,
        context=CommandPhaseStartCompletedBattleShockAuthorityContext(
            state=state,
            historical=historical,
            source_state=source_state,
            source_decision_record=record,
            request=authority.result.request,
        ),
    )


def _source_decision_record(
    *,
    decision_records: tuple[DecisionRecord, ...],
    source_state: FactionRuleState,
) -> DecisionRecord:
    matches = tuple(
        record
        for record in decision_records
        if record.request.request_id == source_state.request_id
        and record.result.result_id == source_state.result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Command-start source decision authority drifted.")
    return matches[0]


def _validate_pending_command_start_source(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    authority: PendingBattleShockRerollAuthority,
) -> None:
    if frozenset(authority.base_payload) != _COMMAND_START_BASE_KEYS:
        raise GameLifecycleError("Pending Command-start Battle-shock source shape drifted.")
    raw_state = authority.base_payload.get("source_faction_rule_state")
    if not isinstance(raw_state, dict):
        raise GameLifecycleError("Pending Command-start Battle-shock source state is invalid.")
    source_state = FactionRuleState.from_payload(cast(FactionRuleStatePayload, raw_state))
    matching_states = tuple(row for row in state.faction_rule_states if row == source_state)
    if len(matching_states) != 1:
        raise GameLifecycleError("Pending Command-start Battle-shock state authority drifted.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=request_event_index,
        request_id=source_state.request_id,
        result_id=source_state.result_id,
    )
    if (
        authority.test_request.reason is not BattleShockTestReason.FORCED_BY_ARMY_RULE
        or authority.phase.value != "command"
    ):
        raise GameLifecycleError("Pending Command-start Battle-shock occurrence drifted.")


def _validate_pending_selected_target_source(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    authority: PendingBattleShockRerollAuthority,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    base = authority.base_payload
    matched = _validate_selected_target_source(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=request_event_index,
        request=authority.test_request,
        base=base,
    )
    _validate_loaded_selected_target_source_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_event_index=request_event_index,
        request=authority.test_request,
        matched=matched,
        base=base,
        runtime_content_bundle=runtime_content_bundle,
    )


def _validate_loaded_selected_target_source_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    request: object,
    matched: DecisionRecord,
    base: dict[str, JsonValue],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
    from warhammer40k_core.engine.catalog_selected_target_history_authority import (
        validate_catalog_selected_target_loaded_source_authority,
    )

    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Selected-target Battle-shock request is invalid.")
    validate_catalog_selected_target_loaded_source_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_event_index=request_event_index,
        request=request,
        source_decision_record=matched,
        request_base=base,
        runtime_content_bundle=runtime_content_bundle,
    )


def _validate_pending_forced_desperate_escape_source(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    authority: PendingBattleShockRerollAuthority,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    movement_record = _validate_forced_desperate_escape_source(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=request_event_index,
        request=authority.test_request,
        request_context={
            **authority.base_payload,
            "battle_shock_test_request": cast(
                dict[str, JsonValue], authority.test_request.to_payload()
            ),
        },
        base=authority.base_payload,
    )
    _validate_loaded_forced_desperate_escape_source_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_event_index=request_event_index,
        request=authority.test_request,
        movement_record=movement_record,
        base=authority.base_payload,
        runtime_content_bundle=runtime_content_bundle,
    )


def _validate_loaded_forced_desperate_escape_source_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request_event_index: int,
    request: object,
    movement_record: DecisionRecord,
    base: dict[str, JsonValue],
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
    from warhammer40k_core.engine.forced_desperate_escape_history_authority import (
        validate_forced_desperate_escape_loaded_source_authority,
    )
    from warhammer40k_core.engine.phases.movement_state import (
        FallBackActionResult,
        FallBackActionResultPayload,
    )

    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Desperate Escape Battle-shock request is invalid.")
    fall_back = FallBackActionResult.from_payload(
        cast(
            FallBackActionResultPayload,
            _object(base.get("fall_back_result"), "Fall Back result"),
        )
    )
    raw_sources = fall_back.movement_payload.get("forced_desperate_escape_sources")
    if not isinstance(raw_sources, list) or any(
        not isinstance(source, dict) for source in raw_sources
    ):
        raise GameLifecycleError("Desperate Escape loaded source inventory is invalid.")
    validate_forced_desperate_escape_loaded_source_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_event_index=request_event_index,
        request=request,
        movement_record=movement_record,
        sources=tuple(cast(dict[str, JsonValue], source) for source in raw_sources),
        runtime_content_bundle=runtime_content_bundle,
    )


def _validate_selected_target_source(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    request: object,
    base: dict[str, JsonValue],
) -> DecisionRecord:
    from warhammer40k_core.engine.battle_shock import BattleShockTestRequest

    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Selected-target Battle-shock request is invalid.")
    if frozenset(base) != _SELECTED_TARGET_BASE_KEYS:
        raise GameLifecycleError("Selected-target Battle-shock source shape drifted.")
    raw_result = base.get("selected_target_decision_result")
    matching = tuple(
        record for record in decision_records if record.result.to_payload() == raw_result
    )
    if len(matching) != 1:
        raise GameLifecycleError("Battle-shock selected-target source authority drifted.")
    record = matching[0]
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=record.request.request_id,
        result_id=record.result.result_id,
    )
    selected_payload = _object(base.get("selected_target_payload"), "selected-target payload")
    selected_effect = _object(
        selected_payload.get("selected_catalog_target_effect"),
        "selected-target option",
    )
    effect_payload = _object(base.get("effect_payload"), "selected-target effect")
    raw_effect_records = selected_payload.get("generic_rule_effect_records")
    if not isinstance(raw_effect_records, list) or any(
        not isinstance(candidate, dict) for candidate in raw_effect_records
    ):
        raise GameLifecycleError("Selected-target Battle-shock effect inventory is invalid.")
    effect_records = tuple(
        cast(dict[str, JsonValue], candidate) for candidate in raw_effect_records
    )
    matching_effect_indices = tuple(
        index
        for index, candidate in enumerate(effect_records)
        if (
            candidate.get("catalog_record_id") == base.get("catalog_record_id")
            and candidate.get("source_rule_id") == base.get("source_rule_id")
            and candidate.get("source_unit_instance_id") == base.get("source_unit_instance_id")
            and candidate.get("selection_clause_id") == base.get("selection_clause_id")
            and candidate.get("effect_clause_id") == base.get("effect_clause_id")
            and candidate.get("effect_index") == base.get("effect_index")
            and candidate.get("selected_target_unit_instance_id")
            == base.get("selected_target_unit_instance_id")
            and candidate.get("effect_payload") == effect_payload
        )
    )
    raw_recorded_before = base.get("selected_target_recorded_effects_before_battle_shock")
    raw_remaining = base.get("selected_target_remaining_effect_records_after_battle_shock")
    remaining_start_index = base.get("selected_target_remaining_effect_start_index")
    if (
        record.result.payload != selected_payload
        or selected_payload.get("catalog_record_id") != base.get("catalog_record_id")
        or selected_payload.get("source_rule_id") != base.get("source_rule_id")
        or selected_payload.get("source_unit_instance_id") != base.get("source_unit_instance_id")
        or selected_payload.get("selection_clause_id") != base.get("selection_clause_id")
        or selected_effect.get("target_unit_instance_id")
        != base.get("selected_target_unit_instance_id")
        or len(matching_effect_indices) != 1
        or not isinstance(raw_recorded_before, list)
        or any(not isinstance(candidate, dict) for candidate in raw_recorded_before)
        or not isinstance(raw_remaining, list)
        or any(not isinstance(candidate, dict) for candidate in raw_remaining)
        or remaining_start_index != matching_effect_indices[0] + 1
        or raw_remaining != list(effect_records[matching_effect_indices[0] + 1 :])
        or request.reason is not BattleShockTestReason.FORCED_BY_ARMY_RULE
        or base.get("target_unit_instance_id") != request.unit_instance_id
        or base.get("target_player_id") != request.player_id
    ):
        raise GameLifecycleError("Selected-target Battle-shock occurrence authority drifted.")
    _validate_selected_target_recorded_prefix(
        event_records=event_records,
        mutation_index=mutation_index,
        decision_record=record,
        effect_records=effect_records,
        current_effect_index=matching_effect_indices[0],
        recorded_before=tuple(
            cast(dict[str, JsonValue], candidate) for candidate in raw_recorded_before
        ),
    )
    return record


def _validate_selected_target_recorded_prefix(
    *,
    event_records: tuple[EventRecord, ...],
    mutation_index: int,
    decision_record: DecisionRecord,
    effect_records: tuple[dict[str, JsonValue], ...],
    current_effect_index: int,
    recorded_before: tuple[dict[str, JsonValue], ...],
) -> None:
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )
    from warhammer40k_core.engine.catalog_selected_target_effects_support import (
        recorded_effects_include_inflicted_mortal_wounds,
    )

    expected: list[dict[str, JsonValue]] = []
    for effect_index, effect_record in enumerate(effect_records[:current_effect_index]):
        condition = effect_record.get("immediate_effect_condition")
        if condition is not None:
            if condition != "prior_effect_inflicted_mortal_wounds":
                raise GameLifecycleError("Selected-target prefix condition is unsupported.")
            if not recorded_effects_include_inflicted_mortal_wounds(expected):
                continue
        immediate_kind = effect_record.get("immediate_effect_kind")
        if immediate_kind is not None:
            resolved = _selected_target_immediate_resolution_events(
                event_records=event_records,
                mutation_index=mutation_index,
                decision_record=decision_record,
                effect_record=effect_record,
                immediate_kind=immediate_kind,
            )
            if len(resolved) != 1:
                raise GameLifecycleError(
                    "Selected-target prior immediate-effect authority drifted."
                )
            expected.append(resolved[0])
            continue
        try:
            expected.append(
                cast(
                    dict[str, JsonValue],
                    validate_json_value(
                        {
                            "effect_id": (
                                f"{decision_record.result.result_id}:"
                                f"{CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT}:"
                                f"{effect_index:03d}"
                            ),
                            "source_rule_id": effect_record["source_rule_id"],
                            "owner_player_id": effect_record["owner_player_id"],
                            "target_unit_instance_ids": effect_record["target_unit_instance_ids"],
                            "started_battle_round": effect_record["started_battle_round"],
                            "started_phase": effect_record["started_phase"],
                            "expiration": effect_record["expiration"],
                            "effect_payload": effect_record["effect_payload"],
                        }
                    ),
                )
            )
        except KeyError as exc:
            raise GameLifecycleError(
                "Selected-target prior persisting effect is incomplete."
            ) from exc
    if tuple(expected) != recorded_before:
        raise GameLifecycleError("Selected-target recorded effect prefix drifted.")


def _selected_target_immediate_resolution_events(
    *,
    event_records: tuple[EventRecord, ...],
    mutation_index: int,
    decision_record: DecisionRecord,
    effect_record: dict[str, JsonValue],
    immediate_kind: JsonValue,
) -> tuple[dict[str, JsonValue], ...]:
    if immediate_kind == "inflict_mortal_wounds":
        event_type = "catalog_selected_target_mortal_wounds_resolved"
    elif immediate_kind == "force_battle_shock_test":
        event_type = "catalog_selected_target_battle_shock_resolved"
    else:
        raise GameLifecycleError("Selected-target immediate effect kind is unsupported.")
    matches: list[dict[str, JsonValue]] = []
    for event in event_records[:mutation_index]:
        if event.event_type != event_type or not isinstance(event.payload, dict):
            continue
        payload = event.payload
        if payload.get("selected_target_decision_result") != decision_record.result.to_payload():
            continue
        if immediate_kind == "inflict_mortal_wounds":
            if payload.get("selected_target_effect_record") != effect_record:
                continue
        elif not (
            payload.get("catalog_record_id") == effect_record.get("catalog_record_id")
            and payload.get("source_rule_id") == effect_record.get("source_rule_id")
            and payload.get("source_unit_instance_id")
            == effect_record.get("source_unit_instance_id")
            and payload.get("selection_clause_id") == effect_record.get("selection_clause_id")
            and payload.get("effect_clause_id") == effect_record.get("effect_clause_id")
            and payload.get("effect_index") == effect_record.get("effect_index")
            and payload.get("selected_target_unit_instance_id")
            == effect_record.get("selected_target_unit_instance_id")
            and payload.get("effect_payload") == effect_record.get("effect_payload")
        ):
            continue
        matches.append(payload)
    return tuple(matches)


def _validate_forced_desperate_escape_source(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    request: object,
    request_context: dict[str, JsonValue],
    base: dict[str, JsonValue],
) -> DecisionRecord:
    from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
    from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
    from warhammer40k_core.engine.phases.movement_options_dice import (
        FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
    )
    from warhammer40k_core.engine.phases.movement_state import (
        FallBackActionResult,
        FallBackActionResultPayload,
    )

    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Desperate Escape Battle-shock request is invalid.")
    if frozenset(base) != _FORCED_DESPERATE_ESCAPE_BASE_KEYS:
        raise GameLifecycleError("Desperate Escape Battle-shock source shape drifted.")
    raw_fall_back = _object(base.get("fall_back_result"), "Fall Back result")
    raw_action_result = _object(base.get("action_result"), "movement action result")
    try:
        fall_back = FallBackActionResult.from_payload(
            cast(FallBackActionResultPayload, raw_fall_back)
        )
        action_result = DecisionResult.from_payload(cast(DecisionResultPayload, raw_action_result))
    except KeyError as exc:
        raise GameLifecycleError("Desperate Escape source payload is incomplete.") from exc
    proposal_request_id = base.get("movement_proposal_request_id")
    action_matches = tuple(
        record
        for record in decision_records
        if record.request.request_id == action_result.request_id
        and record.result.result_id == action_result.result_id
        and record.result.actor_id == action_result.actor_id
        and record.result.decision_type == action_result.decision_type
        and record.result.selected_option_id == action_result.selected_option_id
    )
    proposal_matches = tuple(
        record for record in decision_records if record.request.request_id == proposal_request_id
    )
    request_events = tuple(
        (event_index, event)
        for event_index, event in enumerate(event_records[: mutation_index + 1])
        if event.event_type == "battle_shock_test_requested" and event.payload == request_context
    )
    source_event_index = request_events[0][0] + 1 if len(request_events) == 1 else -1
    source_event = (
        event_records[source_event_index] if 0 <= source_event_index < len(event_records) else None
    )
    if (
        len(action_matches) != 1
        or len(proposal_matches) != 1
        or len(request_events) != 1
        or source_event is None
        or source_event.event_type != "forced_desperate_escape_battle_shock_requested"
        or source_event.payload != request_context
    ):
        raise GameLifecycleError("Battle-shock Desperate Escape source authority drifted.")
    action_record = action_matches[0]
    proposal_record = proposal_matches[0]
    proposal = MovementProposalRequest.from_decision_request_payload(
        proposal_record.request.payload
    )
    proposal_context = proposal.context or {}
    raw_sources = fall_back.movement_payload.get("forced_desperate_escape_sources")
    raw_source_ids = base.get("source_rule_ids")
    if not isinstance(raw_sources, list) or not raw_sources or not isinstance(raw_source_ids, list):
        raise GameLifecycleError("Desperate Escape source inventory is invalid.")
    source_ids_list: list[str] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_rule_id")
        if type(source_id) is str:
            source_ids_list.append(source_id)
    source_ids = tuple(sorted(source_ids_list))
    expected_action_payload = {
        "movement_phase_action": "fall_back",
        "unit_instance_id": fall_back.unit_instance_id,
        "witness": fall_back.witness.to_payload(),
        **fall_back.movement_payload,
    }
    if (
        len(source_ids) != len(raw_sources)
        or list(source_ids) != raw_source_ids
        or base.get("source_rule_id") != FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID
        or base.get("phase") != "movement"
        or base.get("unit_instance_id") != fall_back.unit_instance_id
        or request.unit_instance_id != fall_back.unit_instance_id
        or request.player_id != fall_back.attempted_placement.player_id
        or request.reason
        not in {
            BattleShockTestReason.FORCED_BY_ARMY_RULE,
            BattleShockTestReason.FORCED_BY_STRATAGEM,
        }
        or proposal.game_id != request.game_id
        or proposal.battle_round != request.battle_round
        or proposal.phase != "movement"
        or proposal.unit_instance_id != fall_back.unit_instance_id
        or proposal.movement_phase_action != "fall_back"
        or proposal.source_decision_request_id != action_result.request_id
        or proposal.source_decision_result_id != action_result.result_id
        or proposal_context.get("forced_desperate_escape_sources") != raw_sources
        or proposal_context.get("forced_desperate_escape_source_rule_ids") != raw_source_ids
        or action_result.payload != expected_action_payload
    ):
        raise GameLifecycleError("Desperate Escape source occurrence drifted.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=action_record.request.request_id,
        result_id=action_record.result.result_id,
    )
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=proposal_record.request.request_id,
        result_id=proposal_record.result.result_id,
    )
    return proposal_record


def _object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Battle-shock {context} must be an object.")
    return value


def _matching_command_snapshots(
    *,
    prior_events: tuple[EventRecord, ...],
    request_payload: dict[str, JsonValue],
    request_base: dict[str, JsonValue],
) -> int:
    matching = 0
    for event in prior_events:
        payload = event.payload
        if event.event_type != "battle_shock_step_snapshot_created" or not isinstance(
            payload, dict
        ):
            continue
        required = payload.get("battle_shock_required_test_requests")
        if (
            payload.get("game_id") == request_base.get("game_id")
            and payload.get("battle_round") == request_base.get("battle_round")
            and payload.get("active_player_id") == request_base.get("active_player_id")
            and payload.get("phase") == request_base.get("phase")
            and isinstance(required, list)
            and request_payload in required
        ):
            matching += 1
    return matching


def _validate_source_decision_ids(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    resolved_index: int,
    source_payload: dict[str, JsonValue],
) -> None:
    request_id = source_payload.get("request_id")
    result_id = source_payload.get("result_id")
    if type(request_id) is not str or type(result_id) is not str:
        raise GameLifecycleError("Battle-shock source decision identity is invalid.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=resolved_index,
        request_id=request_id,
        result_id=result_id,
    )


__all__ = (
    "validate_battle_shock_runtime_source_family_authority",
    "validate_battle_shock_source_family_authority",
    "validate_pending_battle_shock_source_family_authority",
)
