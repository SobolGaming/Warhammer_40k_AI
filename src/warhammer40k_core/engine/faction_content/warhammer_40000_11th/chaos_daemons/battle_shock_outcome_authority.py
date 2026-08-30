from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import (
    D3RollResult,
    DiceExpression,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSpec,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
)
from warhammer40k_core.engine.battle_shock_historical_authority import (
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockPendingOutcomeAuthority,
    BattleShockPendingOutcomeAuthorityContext,
)
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    parse_battle_shock_resolution_authority,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    DecisionRequestPayload,
    parameterized_decision_option,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.healing import (
    SELECT_HEALING_MODEL_DECISION_TYPE,
    HealingEffect,
    HealingStep,
    HealingStepKind,
    HealingStepPayload,
    healing_effect_from_request,
)
from warhammer40k_core.engine.healing_revival import (
    SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    healing_effect_from_revival_request,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    current_rules_unit_views_for_identity,
)

_EFFECT_KIND = "daemonic_manifestation_battleline_revival"
_PENDING_EVENT_TYPE = "chaos_daemons_daemonic_manifestation_revival_pending"
_SOURCE_CONTEXT_KEYS = frozenset(
    {
        "hook_id",
        "effect_kind",
        "battle_shock_result_id",
        "player_id",
        "unit_instance_id",
        "eligible_revival_model_ids",
        "revive_destroyed_models_only",
        "revive_model_full_health",
        "allow_revival_finish",
        "d3_result",
    }
)
_PENDING_EVENT_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "phase",
        "source_rule_id",
        "battle_shock_result_id",
        "player_id",
        "unit_instance_id",
        "rules_unit_instance_id",
        "eligible_destroyed_model_ids",
        "d3_result",
        "healing_effect",
        "decision_request_id",
    }
)


def validate_july_daemonic_manifestation_pending_outcome(
    context: BattleShockPendingOutcomeAuthorityContext,
    *,
    hook_id: str,
    source_rule_id: str,
) -> BattleShockPendingOutcomeAuthority | None:
    """Reconstruct one pending July revival from its loaded source and causal history."""

    if type(context) is not BattleShockPendingOutcomeAuthorityContext:
        raise GameLifecycleError("Daemonic Manifestation outcome authority requires context.")
    events = context.decisions.event_log.records
    marker_identifies_provider = any(
        event.event_type == _PENDING_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("decision_request_id") == context.request.request_id
        for event in events
    )
    placement_producer_identifies_provider = _placement_producer_identifies_provider(
        context=context,
        hook_id=hook_id,
        source_rule_id=source_rule_id,
    )
    effect = _effect_from_supported_request(context.request)
    if effect is None:
        if marker_identifies_provider or placement_producer_identifies_provider:
            raise GameLifecycleError("Daemonic Manifestation outcome provider identity drifted.")
        return None
    source_context = effect.source_context if isinstance(effect.source_context, dict) else None
    source_identifies_provider = effect.source_rule_id == source_rule_id
    kind_identifies_provider = (
        source_context is not None and source_context.get("effect_kind") == _EFFECT_KIND
    )
    hook_identifies_provider = (
        source_context is not None and source_context.get("hook_id") == hook_id
    )
    provider_effect_id_prefix = f"{hook_id}:daemonic-manifestation-battleline:"
    effect_id_identifies_provider = effect.effect_id.startswith(provider_effect_id_prefix)
    request_id_identifies_provider = context.request.request_id.startswith(
        provider_effect_id_prefix
    )
    lineage_identifies_provider = _placement_lineage_identifies_provider(
        context=context,
        hook_id=hook_id,
        source_rule_id=source_rule_id,
    )
    if not any(
        (
            source_identifies_provider,
            kind_identifies_provider,
            hook_identifies_provider,
            effect_id_identifies_provider,
            request_id_identifies_provider,
            marker_identifies_provider,
            lineage_identifies_provider,
            placement_producer_identifies_provider,
        )
    ):
        return None
    if (
        not source_identifies_provider
        or not kind_identifies_provider
        or not hook_identifies_provider
        or not effect_id_identifies_provider
        or source_context is None
    ):
        raise GameLifecycleError("Daemonic Manifestation outcome provider identity drifted.")
    if frozenset(source_context) != _SOURCE_CONTEXT_KEYS:
        raise GameLifecycleError("Daemonic Manifestation outcome source context drifted.")

    request_event_index = _exact_request_event_index(events=events, request=context.request)
    result_id = _identifier(source_context.get("battle_shock_result_id"), "result ID")
    resolved_matches = tuple(
        (index, event)
        for index, event in enumerate(events[:request_event_index])
        if event.event_type == "battle_shock_test_resolved"
        and isinstance(event.payload, dict)
        and _result_id_from_resolved_payload(event.payload) == result_id
    )
    if len(resolved_matches) != 1:
        raise GameLifecycleError("Daemonic Manifestation Battle-shock result authority drifted.")
    resolved_index, resolved_event = resolved_matches[0]
    resolved_payload = _object(resolved_event.payload, "resolved event")
    result = BattleShockResult.from_payload(
        cast(
            BattleShockResultPayload,
            _object(resolved_payload.get("battle_shock_result"), "Battle-shock result"),
        )
    )
    resolution = parse_battle_shock_resolution_authority(
        event_records=events,
        decision_records=context.decisions.records,
        resolved_index=resolved_index,
        resolved_payload=resolved_payload,
        result=result,
    )
    historical = historical_battle_shock_authority_context(
        state=context.state,
        event_records=events,
        decision_records=context.decisions.records,
        boundary_event_index=resolved_index,
        request=result.request,
        active_player_id=resolution.active_player_id,
        phase=resolution.phase,
        phase_start_battle_shocked_unit_ids=(resolution.phase_start_battle_shocked_unit_ids),
    )
    target = historical.rules_unit(result.request.unit_instance_id)
    daemon_army = historical.army_for_player(result.request.player_id)
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )

    if (
        not result.passed
        or target.owner_player_id != result.request.player_id
        or daemon_army.detachment_selection.faction_id != army_rule.CHAOS_DAEMONS_FACTION_ID
        or not army_rule.rules_unit_has_keyword(target, "BATTLELINE")
        or not army_rule.historical_daemonic_manifestation_applies(
            context=historical,
            daemon_army=daemon_army,
            target=target,
        )
    ):
        raise GameLifecycleError("Daemonic Manifestation outcome predicate drifted.")

    target_model_ids = {model.model_instance_id for model in target.own_models}
    character_model_ids = set(target.character_model_ids(target.own_models))
    for component in target.components:
        if army_rule.unit_has_keyword(component.unit, "CHARACTER"):
            character_model_ids.update(
                model.model_instance_id for model in component.unit.own_models
            )
    destroyed_ids = tuple(
        sorted(
            row.model_instance_id
            for row in historical.physical_models
            if row.model_instance_id in target_model_ids
            and row.presence == "destroyed"
            and row.model_instance_id not in character_model_ids
        )
    )
    if not destroyed_ids:
        raise GameLifecycleError("Daemonic Manifestation revival lacks destroyed models.")
    d3_result = _exact_manifestation_d3(
        events=events,
        resolved_index=resolved_index,
        request_event_index=request_event_index,
        unit_instance_id=target.unit_instance_id,
    )
    opponent_ids = tuple(
        sorted(
            player_id for player_id in historical.player_ids if player_id != daemon_army.player_id
        )
    )
    if len(opponent_ids) != 1:
        raise GameLifecycleError("Daemonic Manifestation opponent authority drifted.")
    expected_effect = HealingEffect(
        effect_id=f"{hook_id}:daemonic-manifestation-battleline:{result.result_id}",
        target_unit_instance_id=target.unit_instance_id,
        amount=d3_result.value,
        opposing_player_id=opponent_ids[0],
        selection_actor_player_id=daemon_army.player_id,
        source_rule_id=source_rule_id,
        source_context=validate_json_value(
            {
                "hook_id": hook_id,
                "effect_kind": _EFFECT_KIND,
                "battle_shock_result_id": result.result_id,
                "player_id": daemon_army.player_id,
                "unit_instance_id": target.unit_instance_id,
                "eligible_revival_model_ids": list(destroyed_ids),
                "revive_destroyed_models_only": True,
                "revive_model_full_health": True,
                "allow_revival_finish": True,
                "d3_result": d3_result.to_payload(),
            }
        ),
        phase_start_model_ids=historical.placed_alive_model_ids(target.unit_instance_id),
    )
    initial_pending_index = _validate_initial_pending_event(
        context=context,
        result=result,
        expected_effect=expected_effect,
        destroyed_ids=destroyed_ids,
        d3_result=d3_result,
        request_event_index=request_event_index,
    )
    _validate_effect_prefix(
        context=context,
        effect=effect,
        expected_effect=expected_effect,
        initial_pending_index=initial_pending_index,
        request_event_index=request_event_index,
    )
    _validate_exact_pending_request(
        context=context,
        effect=effect,
        expected_effect=expected_effect,
        destroyed_ids=destroyed_ids,
        target=target,
        request_event_index=request_event_index,
    )
    return BattleShockPendingOutcomeAuthority(
        result=result,
        resolved_event_index=resolved_index,
    )


def _effect_from_supported_request(request: DecisionRequest) -> HealingEffect | None:
    if request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
        return healing_effect_from_request(request=request)
    if request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
        return healing_effect_from_revival_request(request=request)
    return None


def _placement_lineage_identifies_provider(
    *,
    context: BattleShockPendingOutcomeAuthorityContext,
    hook_id: str,
    source_rule_id: str,
) -> bool:
    request = context.request
    if request.decision_type != SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
        return False
    if not isinstance(request.payload, dict):
        return False
    selection_request_id = request.payload.get("source_selection_request_id")
    selection_result_id = request.payload.get("source_selection_result_id")
    if type(selection_request_id) is not str or type(selection_result_id) is not str:
        return False
    marker_identifies_provider = any(
        event.event_type == _PENDING_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("decision_request_id") == selection_request_id
        for event in context.decisions.event_log.records
    )
    matches = tuple(
        record
        for record in context.decisions.records
        if record.request.request_id == selection_request_id
        and record.result.request_id == selection_request_id
        and record.result.result_id == selection_result_id
    )
    if len(matches) != 1:
        return marker_identifies_provider
    root_request = matches[0].request
    if root_request.decision_type != SELECT_HEALING_MODEL_DECISION_TYPE:
        return marker_identifies_provider
    root_effect = healing_effect_from_request(request=root_request)
    root_context = (
        root_effect.source_context if isinstance(root_effect.source_context, dict) else None
    )
    return marker_identifies_provider or any(
        (
            root_effect.source_rule_id == source_rule_id,
            root_context is not None and root_context.get("effect_kind") == _EFFECT_KIND,
            root_context is not None and root_context.get("hook_id") == hook_id,
            root_effect.effect_id.startswith(f"{hook_id}:daemonic-manifestation-battleline:"),
        )
    )


def _placement_producer_identifies_provider(
    *,
    context: BattleShockPendingOutcomeAuthorityContext,
    hook_id: str,
    source_rule_id: str,
) -> bool:
    """Authenticate a placement from its recorded selection producer, not child routing."""

    events = context.decisions.event_log.records
    claims = 0
    for producer_index, producer_event in enumerate(events):
        if producer_event.event_type != "decision_recorded":
            continue
        producer_records = tuple(
            record
            for record in context.decisions.records
            if record.to_payload() == producer_event.payload
        )
        if len(producer_records) != 1:
            continue
        producer = producer_records[0]
        if producer.request.decision_type != SELECT_HEALING_MODEL_DECISION_TYPE:
            continue
        root_effect = healing_effect_from_request(request=producer.request)
        initial_effect_payload = root_effect.to_payload() | {"resolved_steps": []}
        marker_matches = tuple(
            (index, event)
            for index, event in enumerate(events[:producer_index])
            if event.event_type == _PENDING_EVENT_TYPE
            and isinstance(event.payload, dict)
            and event.payload.get("healing_effect") == initial_effect_payload
        )
        if not marker_matches:
            continue
        if len(marker_matches) != 1:
            raise GameLifecycleError("Daemonic Manifestation pending occurrence drifted.")
        marker_index, marker = marker_matches[0]
        marker_payload = _object(marker.payload, "pending event")
        initial_request_id = _identifier(
            marker_payload.get("decision_request_id"),
            "initial request ID",
        )
        initial_request_events = tuple(
            event
            for event in events[:marker_index]
            if event.event_type == "decision_requested"
            and isinstance(event.payload, dict)
            and event.payload.get("request_id") == initial_request_id
        )
        if len(initial_request_events) != 1:
            raise GameLifecycleError("Daemonic Manifestation initial decision authority drifted.")
        initial_request = DecisionRequest.from_payload(
            cast(DecisionRequestPayload, initial_request_events[0].payload)
        )
        initial_effect = healing_effect_from_request(request=initial_request)
        root_context = (
            initial_effect.source_context
            if isinstance(initial_effect.source_context, dict)
            else None
        )
        if (
            initial_request.request_id != initial_request_id
            or initial_effect.to_payload() != initial_effect_payload
            or initial_effect.source_rule_id != source_rule_id
            or root_context is None
            or root_context.get("effect_kind") != _EFFECT_KIND
            or root_context.get("hook_id") != hook_id
            or not initial_effect.effect_id.startswith(
                f"{hook_id}:daemonic-manifestation-battleline:"
            )
        ):
            raise GameLifecycleError("Daemonic Manifestation outcome provider identity drifted.")
        if marker_payload.get("source_rule_id") != source_rule_id or marker_payload.get(
            "battle_shock_result_id"
        ) != root_context.get("battle_shock_result_id"):
            raise GameLifecycleError("Daemonic Manifestation pending evidence drifted.")
        validate_mutation_decision_closure(
            event_records=events,
            decision_records=context.decisions.records,
            mutation_index=producer_index + 1,
            request_id=producer.request.request_id,
            result_id=producer.result.result_id,
        )
        selected = producer.request.option_by_id(producer.result.selected_option_id)
        selected_payload = _object(selected.payload, "revival selection")
        if selected_payload.get("selection_kind") != HealingStepKind.REVIVE_MODEL.value:
            continue
        model_id = _identifier(selected_payload.get("model_instance_id"), "revival model ID")
        if producer.result.payload != selected.payload:
            raise GameLifecycleError("Daemonic Manifestation revival selection drifted.")
        if producer_index + 1 == len(events):
            raise GameLifecycleError("Daemonic Manifestation placement chronology drifted.")
        child_event = events[producer_index + 1]
        if child_event.event_type == "healing_step_resolved":
            _validate_completed_selection_step(
                events=events,
                decision_records=context.decisions.records,
                event_index=producer_index + 1,
                event=child_event,
                effect=root_effect,
                model_id=model_id,
                request_id=producer.request.request_id,
                result_id=producer.result.result_id,
            )
            continue
        if child_event.event_type != "decision_requested" or not isinstance(
            child_event.payload, dict
        ):
            raise GameLifecycleError("Daemonic Manifestation placement chronology drifted.")
        child_request = DecisionRequest.from_payload(
            cast(DecisionRequestPayload, child_event.payload)
        )
        pending_matches = tuple(
            pending
            for pending in context.decisions.queue.pending_requests
            if pending == child_request
        )
        completed_matches = tuple(
            record for record in context.decisions.records if record.request == child_request
        )
        if completed_matches:
            if len(completed_matches) != 1 or pending_matches:
                raise GameLifecycleError("Daemonic Manifestation pending descendant drifted.")
            component_id = _historical_component_unit_id_for_model(
                context=context,
                target_unit_instance_id=root_effect.target_unit_instance_id,
                model_id=model_id,
            )
            expected_request = _expected_placement_request(
                effect=root_effect,
                producer=producer,
                model_id=model_id,
                component_id=component_id,
            )
            if child_request != expected_request:
                raise GameLifecycleError(
                    "Daemonic Manifestation outcome provider identity drifted."
                )
            _validate_completed_placement_step(
                events=events,
                decision_records=context.decisions.records,
                effect=root_effect,
                model_id=model_id,
                child_request=child_request,
                result_id=completed_matches[0].result.result_id,
            )
            continue
        if len(pending_matches) != 1:
            raise GameLifecycleError("Daemonic Manifestation pending descendant drifted.")
        relevant_descendants = tuple(
            view
            for view in current_rules_unit_views_for_identity(
                state=context.state,
                unit_instance_id=root_effect.target_unit_instance_id,
            )
            if any(model.model_instance_id == model_id for model in view.own_models)
        )
        if len(relevant_descendants) != 1:
            raise GameLifecycleError("Daemonic Manifestation placement descendant is ambiguous.")
        component_id = relevant_descendants[0].component_unit_id_for_model(model_id)
        expected_request = _expected_placement_request(
            effect=root_effect,
            producer=producer,
            model_id=model_id,
            component_id=component_id,
        )
        if child_request != expected_request:
            raise GameLifecycleError("Daemonic Manifestation outcome provider identity drifted.")
        if context.request == child_request:
            claims += 1
    if claims > 1:
        raise GameLifecycleError("Daemonic Manifestation pending descendant is ambiguous.")
    return claims == 1


def _historical_component_unit_id_for_model(
    *,
    context: BattleShockPendingOutcomeAuthorityContext,
    target_unit_instance_id: str,
    model_id: str,
) -> str:
    attached_matches = tuple(
        record
        for record in context.state.starting_attached_unit_records
        if record.attached_unit_instance_id == target_unit_instance_id
    )
    if attached_matches:
        if len(attached_matches) != 1:
            raise GameLifecycleError(
                "Daemonic Manifestation historical target identity is ambiguous."
            )
        component_matches = tuple(
            component_id
            for component_id, model_ids in attached_matches[
                0
            ].starting_model_instance_ids_by_component
            if model_id in model_ids
        )
        if len(component_matches) != 1:
            raise GameLifecycleError(
                "Daemonic Manifestation historical model identity is ambiguous."
            )
        return component_matches[0]
    component_id = context.state.unit_instance_id_for_model(model_id)
    if component_id != target_unit_instance_id:
        raise GameLifecycleError("Daemonic Manifestation historical target identity drifted.")
    return component_id


def _expected_placement_request(
    *,
    effect: HealingEffect,
    producer: DecisionRecord,
    model_id: str,
    component_id: str,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=(f"{effect.effect_id}:healing-step-{effect.next_step_index():03d}:placement"),
        decision_type=SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
        actor_id=effect.selection_actor_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
                "proposal_kind": "healing_revival_placement",
                "effect": effect.to_payload(),
                "step_index": effect.next_step_index(),
                "model_instance_id": model_id,
                "component_unit_instance_id": component_id,
                "source_selection_request_id": producer.request.request_id,
                "source_selection_result_id": producer.result.result_id,
            }
        ),
        options=(parameterized_decision_option(),),
    )


def _validate_completed_selection_step(
    *,
    events: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    event: EventRecord,
    effect: HealingEffect,
    model_id: str,
    request_id: str,
    result_id: str,
) -> None:
    step = _healing_step_from_event(event=event, effect=effect)
    if (
        step.step_index != effect.next_step_index()
        or step.step_kind
        not in {
            HealingStepKind.REVIVE_MODEL_EMBARKED,
            HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY,
        }
        or step.model_instance_id != model_id
        or step.request_id != request_id
        or step.result_id != result_id
    ):
        raise GameLifecycleError("Daemonic Manifestation healing step drifted.")
    validate_mutation_decision_closure(
        event_records=events,
        decision_records=decision_records,
        mutation_index=event_index,
        request_id=request_id,
        result_id=result_id,
    )


def _validate_completed_placement_step(
    *,
    events: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    effect: HealingEffect,
    model_id: str,
    child_request: DecisionRequest,
    result_id: str,
) -> None:
    matches: list[tuple[int, HealingStep]] = []
    for event_index, event in enumerate(events):
        if event.event_type != "healing_step_resolved" or not isinstance(event.payload, dict):
            continue
        if event.payload.get("effect_id") != effect.effect_id:
            continue
        step = _healing_step_from_event(event=event, effect=effect)
        if step.request_id == child_request.request_id and step.result_id == result_id:
            matches.append((event_index, step))
    if len(matches) != 1:
        raise GameLifecycleError("Daemonic Manifestation placement chronology drifted.")
    event_index, step = matches[0]
    if (
        step.step_index != effect.next_step_index()
        or step.step_kind is not HealingStepKind.REVIVE_MODEL
        or step.model_instance_id != model_id
        or step.transition_batch is None
    ):
        raise GameLifecycleError("Daemonic Manifestation healing step drifted.")
    validate_mutation_decision_closure(
        event_records=events,
        decision_records=decision_records,
        mutation_index=event_index,
        request_id=child_request.request_id,
        result_id=result_id,
    )


def _healing_step_from_event(*, event: EventRecord, effect: HealingEffect) -> HealingStep:
    payload = _object(event.payload, "healing step event")
    raw_step = _object(payload.get("step"), "healing step")
    step = HealingStep.from_payload(cast(HealingStepPayload, raw_step))
    expected_payload = validate_json_value(
        {
            "effect_id": effect.effect_id,
            "target_unit_instance_id": effect.target_unit_instance_id,
            "amount": effect.amount,
            "source_rule_id": effect.source_rule_id,
            "source_context": effect.source_context,
            "step": step.to_payload(),
        }
    )
    if event.payload != expected_payload:
        raise GameLifecycleError("Daemonic Manifestation healing step drifted.")
    return step


def _exact_manifestation_d3(
    *,
    events: tuple[EventRecord, ...],
    resolved_index: int,
    request_event_index: int,
    unit_instance_id: str,
) -> D3RollResult:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Daemonic Manifestation",
        roll_type="chaos_daemons.daemonic_manifestation_d3",
        actor_id=unit_instance_id,
    )
    matches: list[DiceRollResult] = []
    for event in events[resolved_index + 1 : request_event_index]:
        if event.event_type != "dice_rolled" or not isinstance(event.payload, dict):
            continue
        roll = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if roll.spec == spec:
            matches.append(roll)
    if len(matches) != 1:
        raise GameLifecycleError("Daemonic Manifestation D3 authority drifted.")
    return D3RollResult.from_source_d6_result(matches[0])


def _validate_initial_pending_event(
    *,
    context: BattleShockPendingOutcomeAuthorityContext,
    result: BattleShockResult,
    expected_effect: HealingEffect,
    destroyed_ids: tuple[str, ...],
    d3_result: D3RollResult,
    request_event_index: int,
) -> int:
    matches = tuple(
        (index, event)
        for index, event in enumerate(context.decisions.event_log.records)
        if event.event_type == _PENDING_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_result_id") == result.result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Daemonic Manifestation pending occurrence drifted.")
    index, event = matches[0]
    payload = _object(event.payload, "pending event")
    expected = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": result.request.game_id,
                "battle_round": result.request.battle_round,
                "phase": "command",
                "source_rule_id": expected_effect.source_rule_id,
                "battle_shock_result_id": result.result_id,
                "player_id": result.request.player_id,
                "unit_instance_id": result.request.unit_instance_id,
                "rules_unit_instance_id": result.request.unit_instance_id,
                "eligible_destroyed_model_ids": list(destroyed_ids),
                "d3_result": d3_result.to_payload(),
                "healing_effect": expected_effect.to_payload(),
                "decision_request_id": "pending-request-id",
            }
        ),
    )
    # The initial event always names the first request, which may differ from the current one.
    expected["decision_request_id"] = payload.get("decision_request_id")
    if frozenset(payload) != _PENDING_EVENT_KEYS or payload != expected:
        raise GameLifecycleError("Daemonic Manifestation pending evidence drifted.")
    initial_request_id = _identifier(payload.get("decision_request_id"), "initial request ID")
    initial_request_events = tuple(
        event
        for event in context.decisions.event_log.records[:index]
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == initial_request_id
    )
    if len(initial_request_events) != 1:
        raise GameLifecycleError("Daemonic Manifestation initial decision authority drifted.")
    initial_request = DecisionRequest.from_payload(
        cast(DecisionRequestPayload, initial_request_events[0].payload)
    )
    if (
        _effect_from_supported_request(initial_request) != expected_effect
        or initial_request.request_id != initial_request_id
    ):
        raise GameLifecycleError("Daemonic Manifestation initial request drifted.")
    if request_event_index > index and context.request.request_id == initial_request_id:
        raise GameLifecycleError("Daemonic Manifestation pending request ordering drifted.")
    return index


def _validate_effect_prefix(
    *,
    context: BattleShockPendingOutcomeAuthorityContext,
    effect: HealingEffect,
    expected_effect: HealingEffect,
    initial_pending_index: int,
    request_event_index: int,
) -> None:
    if effect.to_payload() | {"resolved_steps": []} != expected_effect.to_payload():
        # Dict union intentionally replaces only the authenticated progress field.
        raise GameLifecycleError("Daemonic Manifestation healing effect authority drifted.")
    step_events = tuple(
        (index, event)
        for index, event in enumerate(context.decisions.event_log.records)
        if initial_pending_index < index < request_event_index
        and event.event_type == "healing_step_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("effect_id") == effect.effect_id
    )
    if len(step_events) != len(effect.resolved_steps):
        raise GameLifecycleError("Daemonic Manifestation healing progress drifted.")
    for (event_index, event), step in zip(step_events, effect.resolved_steps, strict=True):
        expected_payload = validate_json_value(
            {
                "effect_id": effect.effect_id,
                "target_unit_instance_id": effect.target_unit_instance_id,
                "amount": effect.amount,
                "source_rule_id": effect.source_rule_id,
                "source_context": effect.source_context,
                "step": step.to_payload(),
            }
        )
        if event.payload != expected_payload:
            raise GameLifecycleError("Daemonic Manifestation healing step drifted.")
        if step.request_id is not None and step.result_id is not None:
            validate_mutation_decision_closure(
                event_records=context.decisions.event_log.records,
                decision_records=context.decisions.records,
                mutation_index=event_index,
                request_id=step.request_id,
                result_id=step.result_id,
            )


def _validate_exact_pending_request(
    *,
    context: BattleShockPendingOutcomeAuthorityContext,
    effect: HealingEffect,
    expected_effect: HealingEffect,
    destroyed_ids: tuple[str, ...],
    target: RulesUnitView,
    request_event_index: int,
) -> None:
    revived_ids = {
        step.model_instance_id
        for step in effect.resolved_steps
        if step.step_kind
        in {
            HealingStepKind.REVIVE_MODEL,
            HealingStepKind.REVIVE_MODEL_EMBARKED,
        }
        and step.model_instance_id is not None
    }
    remaining_ids = tuple(model_id for model_id in destroyed_ids if model_id not in revived_ids)
    if context.request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
        step_index = effect.next_step_index()
        options = (
            *(
                DecisionOption(
                    option_id=(
                        f"{effect.effect_id}:healing-step-{step_index:03d}:model:{model_id}"
                    ),
                    label=f"Revive {_model_name(target=target, model_instance_id=model_id)}",
                    payload=validate_json_value(
                        {
                            "submission_kind": SELECT_HEALING_MODEL_DECISION_TYPE,
                            "selection_kind": HealingStepKind.REVIVE_MODEL.value,
                            "effect_id": effect.effect_id,
                            "target_unit_instance_id": effect.target_unit_instance_id,
                            "step_index": step_index,
                            "model_instance_id": model_id,
                            "legal_model_ids": list(remaining_ids),
                            "source_rule_id": effect.source_rule_id,
                            "source_context": effect.source_context,
                        }
                    ),
                )
                for model_id in remaining_ids
            ),
            DecisionOption(
                option_id=f"{effect.effect_id}:healing-step-{step_index:03d}:finish",
                label="Finish returning models",
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_HEALING_MODEL_DECISION_TYPE,
                        "selection_kind": HealingStepKind.FINISH.value,
                        "effect_id": effect.effect_id,
                        "target_unit_instance_id": effect.target_unit_instance_id,
                        "step_index": step_index,
                        "model_instance_id": None,
                        "legal_model_ids": list(remaining_ids),
                        "source_rule_id": effect.source_rule_id,
                        "source_context": effect.source_context,
                    }
                ),
            ),
        )
        expected_request = DecisionRequest(
            request_id=f"{effect.effect_id}:healing-step-{step_index:03d}",
            decision_type=SELECT_HEALING_MODEL_DECISION_TYPE,
            actor_id=expected_effect.selection_actor_player_id,
            payload=validate_json_value(
                {
                    "selection_kind": HealingStepKind.REVIVE_MODEL.value,
                    "effect": effect.to_payload(),
                    "step_index": step_index,
                    "legal_model_ids": list(remaining_ids),
                }
            ),
            options=options,
        )
        if context.request != expected_request:
            raise GameLifecycleError("Daemonic Manifestation healing request drifted.")
        return
    payload = _object(context.request.payload, "revival placement request")
    if frozenset(payload) != frozenset(
        {
            "submission_kind",
            "proposal_kind",
            "effect",
            "step_index",
            "model_instance_id",
            "component_unit_instance_id",
            "source_selection_request_id",
            "source_selection_result_id",
        }
    ):
        raise GameLifecycleError("Daemonic Manifestation placement request shape drifted.")
    model_id = _identifier(payload.get("model_instance_id"), "revival model ID")
    component_id = target.component_unit_id_for_model(model_id)
    selection_request_id = payload.get("source_selection_request_id")
    selection_result_id = payload.get("source_selection_result_id")
    if type(selection_request_id) is not str or type(selection_result_id) is not str:
        raise GameLifecycleError("Daemonic Manifestation placement selection is missing.")
    record = validate_mutation_decision_closure(
        event_records=context.decisions.event_log.records,
        decision_records=context.decisions.records,
        mutation_index=request_event_index,
        request_id=selection_request_id,
        result_id=selection_result_id,
    )
    selected = record.request.option_by_id(record.result.selected_option_id)
    selected_payload = _object(selected.payload, "revival selection")
    if (
        selected_payload.get("model_instance_id") != model_id
        or record.result.payload != selected.payload
        or model_id not in remaining_ids
    ):
        raise GameLifecycleError("Daemonic Manifestation revival selection drifted.")
    expected_request = DecisionRequest(
        request_id=f"{effect.effect_id}:healing-step-{effect.next_step_index():03d}:placement",
        decision_type=SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
        actor_id=expected_effect.selection_actor_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
                "proposal_kind": "healing_revival_placement",
                "effect": effect.to_payload(),
                "step_index": effect.next_step_index(),
                "model_instance_id": model_id,
                "component_unit_instance_id": component_id,
                "source_selection_request_id": selection_request_id,
                "source_selection_result_id": selection_result_id,
            }
        ),
        options=(parameterized_decision_option(),),
    )
    if context.request != expected_request:
        raise GameLifecycleError("Daemonic Manifestation placement request drifted.")


def _model_name(*, target: RulesUnitView, model_instance_id: str) -> str:
    matches = tuple(
        model.name for model in target.own_models if model.model_instance_id == model_instance_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Daemonic Manifestation revival model is ambiguous.")
    return matches[0]


def _exact_request_event_index(
    *,
    events: tuple[EventRecord, ...],
    request: DecisionRequest,
) -> int:
    matches = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Daemonic Manifestation pending request authority drifted.")
    return matches[0]


def _result_id_from_resolved_payload(payload: dict[str, JsonValue]) -> str | None:
    result = payload.get("battle_shock_result")
    if not isinstance(result, dict):
        return None
    value = result.get("result_id")
    return value if type(value) is str else None


def _object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Daemonic Manifestation {context} must be an object.")
    return value


def _identifier(value: JsonValue, context: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Daemonic Manifestation {context} must be an identifier.")
    return value


__all__ = ("validate_july_daemonic_manifestation_pending_outcome",)
