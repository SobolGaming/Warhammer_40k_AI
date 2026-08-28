from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.dice import (
    D3RollResult,
    D3RollResultPayload,
    DiceExpression,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollSpec,
)
from warhammer40k_core.engine.battle_shock import BattleShockResult, BattleShockResultPayload
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockCompletedOutcomeAuthorityContext,
    BattleShockPendingOutcomeAuthority,
    BattleShockPendingOutcomeAuthorityContext,
)
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    parse_battle_shock_resolution_authority,
)
from warhammer40k_core.engine.command_battle_shock_forced_provider_authority import (
    historical_harbingers_abilities,
)
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
    MortalWoundApplicationProgress,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.common import payload_identifier
from warhammer40k_core.engine.faction_content.common import payload_object as _payload_object
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_application_authority import (
    MortalWoundApplicationAuthority,
    mortal_wound_application_authority_inventory,
    validate_pending_mortal_wound_application_authority,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

HARBINGERS_DELIRIUM_D3_ROLL_TYPE = "chaos_knights_delirium_mortal_wounds_d3"
DELIRIUM_MORTAL_WOUNDS_SOURCE_KIND = "chaos_knights_delirium_mortal_wounds"


@dataclass(frozen=True, slots=True)
class _DeliriumOccurrenceAuthority:
    result: BattleShockResult
    phase: BattlePhase
    resolved_event_index: int
    resolution_payload: dict[str, JsonValue]
    d3_result: D3RollResult
    chaos_knights_player_id: str


def validate_delirium_pending_outcome_authority(
    context: BattleShockPendingOutcomeAuthorityContext,
) -> BattleShockPendingOutcomeAuthority | None:
    """Reconstruct one pending Delirium outcome from exact source and event authority."""

    if type(context) is not BattleShockPendingOutcomeAuthorityContext:
        raise GameLifecycleError("Delirium pending outcome authority requires context.")
    if not is_mortal_wound_feel_no_pain_request(context.request):
        return None
    source_context = mortal_wound_feel_no_pain_source_context(context.request)
    request_payload = _payload_object(context.request.payload)
    progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
        request_payload.get("lost_wound_context")
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule,
    )

    source_identifies_provider = progress.source_rule_id == army_rule.SOURCE_RULE_ID
    kind_identifies_provider = isinstance(source_context, dict) and source_context.get(
        "source_kind"
    ) == (DELIRIUM_MORTAL_WOUNDS_SOURCE_KIND)
    if not source_identifies_provider and not kind_identifies_provider:
        return None
    if not source_identifies_provider or not kind_identifies_provider:
        raise GameLifecycleError("Delirium pending outcome provider identity drifted.")
    source_context = cast(dict[str, JsonValue], source_context)
    if context.state.current_battle_phase is not delirium_phase(
        delirium_source_context(source_context)["phase"]
    ) or context.state.battle_round != _payload_object(
        delirium_source_context(source_context)["resolution_payload"]
    ).get("battle_round"):
        raise GameLifecycleError("Delirium pending outcome live phase drifted.")
    events = context.decisions.event_log.records
    if context.decisions.queue.pending_requests.count(context.request) != 1:
        raise GameLifecycleError("Delirium pending outcome request is not queued.")
    request_event_indices = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "decision_requested"
        and event.payload == context.request.to_payload()
    )
    if len(request_event_indices) != 1:
        raise GameLifecycleError("Delirium pending request event authority drifted.")
    request_event_index = request_event_indices[0]
    occurrence = _validate_delirium_occurrence(
        state=context.state,
        events=events,
        decision_records=context.decisions.records,
        source_context=source_context,
        boundary_event_index=request_event_index,
    )
    if (
        progress.application_id
        != f"{occurrence.result.result_id}:delirium:{occurrence.result.request.unit_instance_id}"
        or progress.source_rule_id != army_rule.SOURCE_RULE_ID
        or progress.source_context != source_context
        or progress.target_unit_instance_id != occurrence.result.request.unit_instance_id
        or progress.defender_player_id != occurrence.result.request.player_id
        or progress.destruction_evidence is None
        or progress.destruction_evidence.destroying_player_id != occurrence.chaos_knights_player_id
        or progress.destruction_evidence.action_phase is not occurrence.phase
        or progress.destruction_evidence.parent_battle_phase is not occurrence.phase
        or progress.destruction_evidence.source_step != "delirium_mortal_wounds"
    ):
        raise GameLifecycleError("Delirium pending mortal wound progress drifted.")
    if progress.mortal_wounds != occurrence.d3_result.value:
        raise GameLifecycleError("Delirium pending D3 authority drifted.")
    application_inventory = mortal_wound_application_authority_inventory(
        event_records=events,
        game_id=context.state.game_id,
    )
    validate_pending_mortal_wound_application_authority(
        state=context.state,
        event_records=events,
        progress=progress,
        request_event=events[request_event_index],
        inventory=application_inventory,
    )
    expected_pending_payload = validate_json_value(
        {
            **occurrence.resolution_payload,
            "feel_no_pain_request_id": context.request.request_id,
            "remaining_mortal_wounds": progress.remaining_mortal_wounds,
        }
    )
    pending_markers = tuple(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "chaos_knights_delirium_mortal_wounds_pending"
        and isinstance(event.payload, dict)
        and event.payload.get("feel_no_pain_request_id") == context.request.request_id
    )
    if (
        len(pending_markers) != 1
        or pending_markers[0][1].payload != expected_pending_payload
        or pending_markers[0][0] <= request_event_index
    ):
        raise GameLifecycleError("Delirium pending marker authority drifted.")
    return BattleShockPendingOutcomeAuthority(
        result=occurrence.result,
        resolved_event_index=occurrence.resolved_event_index,
    )


def validate_delirium_completed_outcome_authority(
    context: BattleShockCompletedOutcomeAuthorityContext,
) -> None:
    """Authenticate every completed Delirium packet against its exact source history."""

    if type(context) is not BattleShockCompletedOutcomeAuthorityContext:
        raise GameLifecycleError("Delirium completed outcome authority requires context.")
    events = context.decisions.event_log.records
    event_indexes = {event.event_id: index for index, event in enumerate(events)}
    inventory = mortal_wound_application_authority_inventory(
        event_records=events,
        game_id=context.state.game_id,
    )
    pending_application_ids = _pending_mortal_wound_application_ids(context.decisions)
    claimed_applied_event_ids: set[str] = set()
    for started_event, authority in inventory.values():
        source_context = authority.source_context
        if not isinstance(source_context, dict) or source_context.get("source_kind") != (
            DELIRIUM_MORTAL_WOUNDS_SOURCE_KIND
        ):
            continue
        if authority.application_id in pending_application_ids:
            continue
        started_index = event_indexes[started_event.event_id]
        occurrence = _validate_delirium_occurrence(
            state=context.state,
            events=events,
            decision_records=context.decisions.records,
            source_context=source_context,
            boundary_event_index=started_index,
        )
        _validate_completed_application_root(
            authority=authority,
            occurrence=occurrence,
        )
        completion_index, application = _completed_application(
            events=events,
            authority=authority,
        )
        if completion_index <= started_index:
            raise GameLifecycleError("Delirium completion precedes its application authority.")
        applied_matches = tuple(
            (index, event)
            for index, event in enumerate(events)
            if event.event_type == "chaos_knights_delirium_mortal_wounds_applied"
            and isinstance(event.payload, dict)
            and event.payload.get("battle_shock_result_id") == occurrence.result.result_id
            and event.payload.get("target_unit_instance_id")
            == occurrence.result.request.unit_instance_id
        )
        if len(applied_matches) != 1:
            raise GameLifecycleError("Delirium completed outcome marker authority drifted.")
        applied_index, applied_event = applied_matches[0]
        if applied_event.event_id in claimed_applied_event_ids:
            raise GameLifecycleError("Delirium completed outcome marker was claimed twice.")
        claimed_applied_event_ids.add(applied_event.event_id)
        applied_payload = _payload_object(applied_event.payload)
        related_records = _feel_no_pain_records_for_application(
            decisions=context.decisions,
            application_id=authority.application_id,
        )
        expected_payload: dict[str, JsonValue] = {
            **occurrence.resolution_payload,
            "mortal_wound_application": validate_json_value(application.to_payload()),
        }
        if related_records:
            final_record = related_records[-1]
            validate_mutation_decision_closure(
                event_records=events,
                decision_records=context.decisions.records,
                mutation_index=applied_index,
                request_id=final_record.request.request_id,
                result_id=final_record.result.result_id,
            )
            expected_payload["feel_no_pain_result_id"] = final_record.result.result_id
        if applied_index <= completion_index or applied_payload != validate_json_value(
            expected_payload
        ):
            raise GameLifecycleError("Delirium completed outcome terminal payload drifted.")
    retained_applied_event_ids = {
        event.event_id
        for event in events
        if event.event_type == "chaos_knights_delirium_mortal_wounds_applied"
    }
    if retained_applied_event_ids != claimed_applied_event_ids:
        raise GameLifecycleError(
            "Delirium completed outcome marker lacks exactly one application authority."
        )


def _validate_delirium_occurrence(
    *,
    state: GameState,
    events: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    source_context: dict[str, JsonValue],
    boundary_event_index: int,
) -> _DeliriumOccurrenceAuthority:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule,
    )

    if (
        type(state) is not GameState
        or type(decision_records) is not tuple
        or any(type(record) is not DecisionRecord for record in decision_records)
    ):
        raise GameLifecycleError("Delirium outcome occurrence authority is invalid.")
    parsed = delirium_source_context(source_context)
    phase = delirium_phase(parsed["phase"])
    result_payload = parsed["battle_shock_result"]
    if not isinstance(result_payload, dict):
        raise GameLifecycleError("Delirium outcome lacks Battle-shock result.")
    result = BattleShockResult.from_payload(cast(BattleShockResultPayload, result_payload))
    resolution_payload = _payload_object(parsed["resolution_payload"])
    chaos_knights_player_id = payload_identifier(resolution_payload, key="player_id")
    if (
        result.passed
        or resolution_payload.get("game_id") != state.game_id
        or resolution_payload.get("battle_round") != result.request.battle_round
        or resolution_payload.get("phase") != phase.value
        or resolution_payload.get("source_rule_id") != army_rule.SOURCE_RULE_ID
        or resolution_payload.get("battle_shock_result_id") != result.result_id
        or resolution_payload.get("target_unit_instance_id") != result.request.unit_instance_id
    ):
        raise GameLifecycleError("Delirium outcome source authority drifted.")
    matches = tuple(
        (index, event)
        for index, event in enumerate(events[:boundary_event_index])
        if event.event_type == "battle_shock_test_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_result") == result.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Delirium Battle-shock result authority drifted.")
    resolved_index, resolved_event = matches[0]
    resolved_payload = _payload_object(resolved_event.payload)
    resolution = parse_battle_shock_resolution_authority(
        event_records=events,
        decision_records=decision_records,
        resolved_index=resolved_index,
        resolved_payload=resolved_payload,
        result=result,
    )
    if resolution.phase is not phase:
        raise GameLifecycleError("Delirium Battle-shock phase authority drifted.")
    historical = historical_battle_shock_authority_context(
        state=state,
        event_records=events,
        decision_records=decision_records,
        boundary_event_index=resolved_index,
        request=result.request,
        active_player_id=resolution.active_player_id,
        phase=resolution.phase,
        phase_start_battle_shocked_unit_ids=resolution.phase_start_battle_shocked_unit_ids,
    )
    target = historical.rules_unit(result.request.unit_instance_id)
    chaos_knights_army = historical.army_for_player(chaos_knights_player_id)
    active_by_player = historical_harbingers_abilities(
        state=state,
        event_records=events,
        decision_records=decision_records,
        snapshot_index=resolved_index,
    )
    active = active_by_player.get(chaos_knights_player_id)
    if (
        target.owner_player_id != result.request.player_id
        or chaos_knights_player_id == result.request.player_id
        or chaos_knights_army.detachment_selection.faction_id != army_rule.CHAOS_KNIGHTS_FACTION_ID
        or active is None
        or army_rule.DreadAbility.DELIRIUM not in active
        or not _historical_unit_is_below_half_strength(historical, target)
        or not army_rule.historical_unit_within_dread_aura(
            historical,
            dread_army=chaos_knights_army,
            target=target,
            active=active,
        )
    ):
        raise GameLifecycleError("Delirium outcome predicate drifted.")
    d3_result = _exact_delirium_d3(
        events=events,
        resolved_index=resolved_index,
        request_event_index=boundary_event_index,
        target_unit_instance_id=target.unit_instance_id,
    )
    retained_d3_payload = _payload_object(resolution_payload.get("d3_result"))
    retained_d3 = D3RollResult.from_payload(cast(D3RollResultPayload, retained_d3_payload))
    if retained_d3 != d3_result:
        raise GameLifecycleError("Delirium D3 authority drifted.")
    return _DeliriumOccurrenceAuthority(
        result=result,
        phase=phase,
        resolved_event_index=resolved_index,
        resolution_payload=resolution_payload,
        d3_result=d3_result,
        chaos_knights_player_id=chaos_knights_player_id,
    )


def _validate_completed_application_root(
    *,
    authority: MortalWoundApplicationAuthority,
    occurrence: _DeliriumOccurrenceAuthority,
) -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule,
    )

    evidence = authority.destruction_evidence
    if (
        authority.application_id
        != f"{occurrence.result.result_id}:delirium:{occurrence.result.request.unit_instance_id}"
        or authority.source_rule_id != army_rule.SOURCE_RULE_ID
        or authority.target_unit_instance_id != occurrence.result.request.unit_instance_id
        or authority.defender_player_id != occurrence.result.request.player_id
        or authority.mortal_wounds != occurrence.d3_result.value
        or not authority.spill_over
        or evidence is None
        or evidence.destroying_player_id != occurrence.chaos_knights_player_id
        or evidence.action_phase is not occurrence.phase
        or evidence.parent_battle_phase is not occurrence.phase
        or evidence.source_step != "delirium_mortal_wounds"
    ):
        raise GameLifecycleError("Delirium completed application authority drifted.")


def _completed_application(
    *,
    events: tuple[EventRecord, ...],
    authority: MortalWoundApplicationAuthority,
) -> tuple[int, MortalWoundApplication]:
    matches = tuple(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("application_id") == authority.application_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Delirium completed application terminal authority drifted.")
    index, event = matches[0]
    payload = _payload_object(event.payload)
    raw_application = payload.get("application")
    if not isinstance(raw_application, dict):
        raise GameLifecycleError("Delirium completed application result is invalid.")
    return index, MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, raw_application)
    )


def _feel_no_pain_records_for_application(
    *,
    decisions: DecisionController,
    application_id: str,
) -> tuple[DecisionRecord, ...]:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Delirium FNP history requires DecisionController.")
    records: list[DecisionRecord] = []
    for record in decisions.records:
        if not is_mortal_wound_feel_no_pain_request(record.request):
            continue
        request_payload = _payload_object(record.request.payload)
        progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
            request_payload.get("lost_wound_context")
        )
        if progress.application_id == application_id:
            records.append(record)
    return tuple(records)


def _pending_mortal_wound_application_ids(
    decisions: DecisionController,
) -> frozenset[str]:
    application_ids: set[str] = set()
    for request in decisions.queue.pending_requests:
        if not is_mortal_wound_feel_no_pain_request(request):
            continue
        request_payload = _payload_object(request.payload)
        progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
            request_payload.get("lost_wound_context")
        )
        application_ids.add(progress.application_id)
    return frozenset(application_ids)


def delirium_source_context(value: JsonValue) -> dict[str, JsonValue]:
    payload = _payload_object(value)
    if (
        frozenset(payload)
        != frozenset(
            {
                "source_kind",
                "phase",
                "battle_shock_result",
                "resolution_payload",
            }
        )
        or payload.get("source_kind") != DELIRIUM_MORTAL_WOUNDS_SOURCE_KIND
        or not isinstance(payload.get("battle_shock_result"), dict)
        or not isinstance(payload.get("resolution_payload"), dict)
    ):
        raise GameLifecycleError("Delirium mortal wound source context drifted.")
    resolution_payload = _payload_object(payload["resolution_payload"])
    if frozenset(resolution_payload) != frozenset(
        {
            "game_id",
            "battle_round",
            "phase",
            "source_rule_id",
            "battle_shock_result_id",
            "player_id",
            "target_unit_instance_id",
            "d3_result",
        }
    ):
        raise GameLifecycleError("Delirium mortal wound resolution payload drifted.")
    phase = delirium_phase(payload.get("phase"))
    if resolution_payload.get("phase") != phase.value:
        raise GameLifecycleError("Delirium mortal wound resolution phase drifted.")
    return payload


def delirium_phase(value: JsonValue) -> BattlePhase:
    if type(value) is not str:
        raise GameLifecycleError("Delirium mortal wound phase must be a string.")
    try:
        return BattlePhase(value)
    except ValueError as exc:
        raise GameLifecycleError("Delirium mortal wound phase is unsupported.") from exc


def _exact_delirium_d3(
    *,
    events: tuple[EventRecord, ...],
    resolved_index: int,
    request_event_index: int,
    target_unit_instance_id: str,
) -> D3RollResult:
    expected_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Delirium mortal wounds",
        roll_type=HARBINGERS_DELIRIUM_D3_ROLL_TYPE,
        actor_id=target_unit_instance_id,
    )
    matches: list[DiceRollResult] = []
    for event in events[resolved_index + 1 : request_event_index]:
        if event.event_type != "dice_rolled" or not isinstance(event.payload, dict):
            continue
        roll = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if roll.spec == expected_spec:
            matches.append(roll)
    if len(matches) != 1:
        raise GameLifecycleError("Delirium pending D3 occurrence authority drifted.")
    return D3RollResult.from_source_d6_result(matches[0])


def _historical_unit_is_below_half_strength(
    context: HistoricalBattleShockAuthorityContext,
    target: RulesUnitView,
) -> bool:
    current_model_ids = context.placed_alive_model_ids(target.unit_instance_id)
    if not current_model_ids:
        return False
    return BelowHalfStrengthContext.from_rules_unit(
        rules_unit=target,
        starting_strength=context.starting_strength(target.unit_instance_id),
        current_model_ids=current_model_ids,
    ).is_below_half_strength


__all__ = (
    "DELIRIUM_MORTAL_WOUNDS_SOURCE_KIND",
    "HARBINGERS_DELIRIUM_D3_ROLL_TYPE",
    "delirium_phase",
    "delirium_source_context",
    "validate_delirium_completed_outcome_authority",
    "validate_delirium_pending_outcome_authority",
)
