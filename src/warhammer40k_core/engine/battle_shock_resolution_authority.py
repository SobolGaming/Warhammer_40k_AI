from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.dice import (
    DiceRollState,
    DiceRollStatePayload,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockModifierApplication,
    BattleShockModifierApplicationPayload,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    BATTLE_SHOCK_MODIFIER_APPLICATION_EVENT,
    BattleShockPassedStatePolicy,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


@dataclass(frozen=True, slots=True)
class BattleShockRerollAuthority:
    decision_record: DecisionRecord
    permission: RerollPermission
    decision_requested_event_index: int
    decision_recorded_event_index: int
    disposition_event_index: int
    accepted: bool
    passed_state_policy: BattleShockPassedStatePolicy
    resolved_event_types: tuple[str, ...]
    additional_modifier_applications: tuple[BattleShockModifierApplication, ...]


@dataclass(frozen=True, slots=True)
class BattleShockResolutionAuthority:
    request_event_index: int
    original_roll_event_index: int
    modifier_event_index: int
    resolved_event_index: int
    request_context: dict[str, JsonValue]
    base_payload: dict[str, JsonValue]
    result: BattleShockResult
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]
    modifier_applications: tuple[BattleShockModifierApplication, ...]
    reroll: BattleShockRerollAuthority | None


@dataclass(frozen=True, slots=True)
class PendingBattleShockRerollAuthority:
    decision_request: DecisionRequest
    test_request: BattleShockTestRequest
    initial_roll_state: DiceRollState
    permission: RerollPermission
    source_kind: str
    base_payload: dict[str, JsonValue]
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]
    passed_state_policy: BattleShockPassedStatePolicy
    resolved_event_types: tuple[str, ...]
    additional_modifier_applications: tuple[BattleShockModifierApplication, ...]


@dataclass(frozen=True, slots=True)
class _ModifierAuthority:
    event_index: int
    phase_start_battle_shocked_unit_ids: tuple[str, ...]
    applications: tuple[BattleShockModifierApplication, ...]


_REROLL_CONTEXT_KEYS = frozenset(
    {
        "source_kind",
        "game_id",
        "battle_round",
        "phase",
        "active_player_id",
        "battle_shock_test_request",
        "battle_shock_roll_state",
        "phase_start_battle_shocked_unit_ids",
        "passed_state_policy",
        "base_payload",
        "resolved_event_types",
        "additional_modifier_applications",
    }
)


def parse_pending_battle_shock_reroll_authority(
    request: DecisionRequest,
) -> PendingBattleShockRerollAuthority:
    """Parse and canonically rebuild one unresolved Battle-shock reroll request."""
    if type(request) is not DecisionRequest or request.decision_type != DICE_REROLL_DECISION_TYPE:
        raise GameLifecycleError("Pending Battle-shock reroll requires a dice-reroll request.")
    payload = _object(request.payload, "pending reroll request")
    context = _object(payload.get("battle_shock_context"), "pending reroll context")
    if frozenset(context) != _REROLL_CONTEXT_KEYS:
        raise GameLifecycleError("Pending Battle-shock reroll context shape drifted.")
    base_payload = _object(context.get("base_payload"), "pending reroll base payload")
    test_request = BattleShockTestRequest.from_payload(
        cast(
            BattleShockTestRequestPayload,
            _object(context.get("battle_shock_test_request"), "pending test request"),
        )
    )
    initial_roll_state = DiceRollState.from_payload(
        cast(
            DiceRollStatePayload,
            _object(context.get("battle_shock_roll_state"), "pending initial roll"),
        )
    )
    if initial_roll_state.original_result.spec != test_request.spec or initial_roll_state.rerolls:
        raise GameLifecycleError("Pending Battle-shock initial roll state drifted.")
    permission = RerollPermission.from_payload(
        cast(RerollPermissionPayload, _object(payload.get("permission"), "reroll permission"))
    )
    source_kind = _identifier(context.get("source_kind"), "pending source kind")
    active_player_id = _identifier(context.get("active_player_id"), "pending active player")
    phase = _phase(context.get("phase"))
    phase_start_ids = _identifier_list(
        context.get("phase_start_battle_shocked_unit_ids"),
        "pending phase-start units",
    )
    resolved_event_types = _identifier_list(
        context.get("resolved_event_types"),
        "pending resolved event types",
        require_sorted=False,
    )
    if "battle_shock_test_resolved" not in resolved_event_types:
        raise GameLifecycleError("Pending Battle-shock resolved-event inventory drifted.")
    policy_token = _identifier(context.get("passed_state_policy"), "pending state policy")
    try:
        passed_state_policy = BattleShockPassedStatePolicy(policy_token)
    except ValueError as exc:
        raise GameLifecycleError("Pending Battle-shock state policy is unsupported.") from exc
    _validate_source_state_policy(
        source_kind=source_kind,
        passed_state_policy=passed_state_policy,
    )
    additional_applications = _modifier_application_list(
        context.get("additional_modifier_applications"),
        "pending additional modifier applications",
    )
    if (
        context.get("game_id") != test_request.game_id
        or context.get("battle_round") != test_request.battle_round
        or base_payload.get("game_id") != test_request.game_id
        or base_payload.get("battle_round") != test_request.battle_round
        or base_payload.get("active_player_id") != active_player_id
        or base_payload.get("phase") != phase.value
        or base_payload.get("source_kind") != source_kind
        or context.get("battle_shock_test_request") != test_request.to_payload()
        or permission.owning_player_id != test_request.player_id
    ):
        raise GameLifecycleError("Pending Battle-shock occurrence context drifted.")
    expected = DiceRollManager(test_request.game_id).build_reroll_request(
        initial_roll_state,
        request_id=request.request_id,
        actor_id=test_request.player_id,
        permission=permission,
        extra_payload={"battle_shock_context": context},
    )
    if request != expected:
        raise GameLifecycleError("Pending Battle-shock reroll request drifted.")
    return PendingBattleShockRerollAuthority(
        decision_request=request,
        test_request=test_request,
        initial_roll_state=initial_roll_state,
        permission=permission,
        source_kind=source_kind,
        base_payload=base_payload,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_ids,
        passed_state_policy=passed_state_policy,
        resolved_event_types=resolved_event_types,
        additional_modifier_applications=additional_applications,
    )


def parse_battle_shock_resolution_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    resolved_index: int,
    resolved_payload: dict[str, JsonValue],
    result: BattleShockResult,
) -> BattleShockResolutionAuthority:
    """Parse one exact request-to-result Battle-shock authority chain."""
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Battle-shock event authority requires event records.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Battle-shock event authority requires decision records.")
    if type(resolved_index) is not int or not 0 <= resolved_index < len(event_records):
        raise GameLifecycleError("Battle-shock resolved event index is invalid.")
    if type(result) is not BattleShockResult:
        raise GameLifecycleError("Battle-shock event authority requires a result.")
    prior_events = event_records[:resolved_index]
    request_payload = cast(
        dict[str, JsonValue],
        validate_json_value(result.request.to_payload()),
    )
    requested = tuple(
        (index, event)
        for index, event in enumerate(prior_events)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == request_payload
    )
    if len(requested) != 1:
        raise GameLifecycleError("Battle-shock result lacks exact request authority.")
    request_index, request_event = requested[0]
    request_context = cast(dict[str, JsonValue], request_event.payload)
    request_base = {
        key: value for key, value in request_context.items() if key != "battle_shock_test_request"
    }
    resolved_base = {
        key: value
        for key, value in resolved_payload.items()
        if key
        not in {
            "battle_shock_result",
            "auto_passed",
            "state_update",
            "cleared_battle_shocked_unit_ids",
        }
    }
    if (
        request_base != resolved_base
        or not {
            "battle_shock_result",
            "auto_passed",
            "state_update",
            "cleared_battle_shocked_unit_ids",
        }.issubset(resolved_payload)
        or request_context.get("game_id") != result.request.game_id
        or request_context.get("battle_round") != result.request.battle_round
        or resolved_payload.get("game_id") != result.request.game_id
        or resolved_payload.get("battle_round") != result.request.battle_round
    ):
        raise GameLifecycleError("Battle-shock request context drifted.")
    _validate_reason_context(result)
    original_roll = result.roll_state.original_result
    original_rolls = tuple(
        (index, event)
        for index, event in enumerate(prior_events)
        if event.event_type == "dice_rolled" and event.payload == original_roll.to_payload()
    )
    if len(original_rolls) != 1 or original_rolls[0][0] <= request_index:
        raise GameLifecycleError("Battle-shock result lacks exact dice authority.")
    original_roll_index = original_rolls[0][0]
    latest_roll_authority_index = original_roll_index
    reroll_decisions = tuple(
        record
        for record in decision_records
        if record.request.decision_type == DICE_REROLL_DECISION_TYPE
        and _reroll_request_payload(record) == request_payload
    )
    reroll_by_result_id = {record.result.result_id: record for record in reroll_decisions}
    if len(reroll_by_result_id) != len(reroll_decisions) or len(reroll_decisions) > 1:
        raise GameLifecycleError("Battle-shock reroll authority is duplicated.")
    accepted_ids = {row.decision_id for row in result.roll_state.rerolls}
    if len(result.roll_state.rerolls) > 1 or not accepted_ids <= set(reroll_by_result_id):
        raise GameLifecycleError("Battle-shock reroll state lacks authority.")
    initial_state = DiceRollState.from_result(original_roll)
    rolling_state = initial_state
    reroll_authority: BattleShockRerollAuthority | None = None
    for reroll in result.roll_state.rerolls:
        record = reroll_by_result_id[reroll.decision_id]
        authority = _validate_reroll_decision(
            event_records=event_records,
            decision_records=decision_records,
            resolved_index=resolved_index,
            request_index=request_index,
            original_roll_event_index=original_roll_index,
            request_payload=request_payload,
            request_base=request_base,
            original_state=initial_state,
            record=record,
            accepted=True,
        )
        if (
            record.result.decision_type != DICE_REROLL_DECISION_TYPE
            or record.request.request_id != reroll.request_id
            or _selected_reroll_indices(record) != reroll.selected_indices
        ):
            raise GameLifecycleError("Battle-shock reroll decision drifted.")
        replacement_rolls = tuple(
            (index, event)
            for index, event in enumerate(prior_events)
            if event.event_type == "dice_rolled"
            and event.payload == reroll.replacement_result.to_payload()
        )
        if (
            len(replacement_rolls) != 1
            or replacement_rolls[0][0] <= authority.decision_recorded_event_index
        ):
            raise GameLifecycleError("Battle-shock reroll lacks exact dice authority.")
        latest_roll_authority_index = replacement_rolls[0][0]
        rolling_state = rolling_state.with_reroll(
            decision_id=reroll.decision_id,
            request_id=reroll.request_id,
            selected_indices=reroll.selected_indices,
            replacement_result=reroll.replacement_result,
        )
        resolved_rerolls = tuple(
            (index, event)
            for index, event in enumerate(prior_events)
            if event.event_type == "dice_reroll_resolved"
            and event.payload == rolling_state.to_payload()
        )
        if len(resolved_rerolls) != 1 or resolved_rerolls[0][0] <= replacement_rolls[0][0]:
            raise GameLifecycleError("Battle-shock reroll lacks exact resolution authority.")
        latest_roll_authority_index = resolved_rerolls[0][0]
        reroll_authority = _with_disposition(authority, resolved_rerolls[0][0])
    for record in reroll_decisions:
        if record.result.result_id in accepted_ids:
            continue
        authority = _validate_reroll_decision(
            event_records=event_records,
            decision_records=decision_records,
            resolved_index=resolved_index,
            request_index=request_index,
            original_roll_event_index=original_roll_index,
            request_payload=request_payload,
            request_base=request_base,
            original_state=initial_state,
            record=record,
            accepted=False,
        )
        declined = tuple(
            (index, event)
            for index, event in enumerate(prior_events)
            if event.event_type == "dice_reroll_declined"
            and event.payload
            == {
                "roll_id": original_roll.roll_id,
                "decision_id": record.result.result_id,
                "request_id": record.request.request_id,
            }
        )
        if len(declined) != 1 or declined[0][0] <= authority.decision_recorded_event_index:
            raise GameLifecycleError("Battle-shock reroll decline lacks exact authority.")
        latest_roll_authority_index = declined[0][0]
        reroll_authority = _with_disposition(authority, declined[0][0])
    if rolling_state != result.roll_state:
        raise GameLifecycleError("Battle-shock roll history drifted.")
    modifier = _modifier_authority(
        prior_events=prior_events,
        request_payload=request_payload,
        request_base=request_base,
        result=result,
        latest_roll_authority_index=latest_roll_authority_index,
    )
    if reroll_authority is not None:
        if any(
            application not in modifier.applications
            for application in reroll_authority.additional_modifier_applications
        ):
            raise GameLifecycleError("Battle-shock reroll source applications drifted.")
        _validate_resolved_event_inventory(
            event_records=event_records,
            resolved_payload=resolved_payload,
            modifier_event_index=modifier.event_index,
            reroll=reroll_authority,
        )
        _validate_source_state_policy(
            source_kind=_identifier(request_base.get("source_kind"), "source kind"),
            passed_state_policy=reroll_authority.passed_state_policy,
        )
    return BattleShockResolutionAuthority(
        request_event_index=request_index,
        original_roll_event_index=original_roll_index,
        modifier_event_index=modifier.event_index,
        resolved_event_index=resolved_index,
        request_context=request_context,
        base_payload=request_base,
        result=result,
        active_player_id=_identifier(request_base.get("active_player_id"), "active player"),
        phase=_phase(request_base.get("phase")),
        phase_start_battle_shocked_unit_ids=modifier.phase_start_battle_shocked_unit_ids,
        modifier_applications=modifier.applications,
        reroll=reroll_authority,
    )


def _validate_reroll_decision(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    resolved_index: int,
    request_index: int,
    original_roll_event_index: int,
    request_payload: dict[str, JsonValue],
    request_base: dict[str, JsonValue],
    original_state: DiceRollState,
    record: DecisionRecord,
    accepted: bool,
) -> BattleShockRerollAuthority:
    validated = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=resolved_index,
        request_id=record.request.request_id,
        result_id=record.result.result_id,
    )
    if validated != record:
        raise GameLifecycleError("Battle-shock reroll decision ledger drifted.")
    requested = tuple(
        index
        for index, event in enumerate(event_records[:resolved_index])
        if event.event_type == "decision_requested" and event.payload == record.request.to_payload()
    )
    recorded = tuple(
        index
        for index, event in enumerate(event_records[:resolved_index])
        if event.event_type == "decision_recorded" and event.payload == record.to_payload()
    )
    if (
        len(requested) != 1
        or len(recorded) != 1
        or not (
            request_index < original_roll_event_index < requested[0] < recorded[0] < resolved_index
        )
    ):
        raise GameLifecycleError("Battle-shock reroll decision event closure drifted.")
    payload = _object(record.request.payload, "reroll request")
    context = _object(payload.get("battle_shock_context"), "reroll context")
    phase_start_ids = _identifier_list(
        context.get("phase_start_battle_shocked_unit_ids"),
        "reroll phase-start units",
    )
    event_types = _identifier_list(
        context.get("resolved_event_types"),
        "reroll resolved event types",
        require_sorted=False,
    )
    additional_applications = _modifier_application_list(
        context.get("additional_modifier_applications"),
        "reroll additional modifier applications",
    )
    if (
        frozenset(context) != _REROLL_CONTEXT_KEYS
        or "battle_shock_test_resolved" not in event_types
    ):
        raise GameLifecycleError("Battle-shock reroll context shape drifted.")
    retained_initial = DiceRollState.from_payload(
        cast(
            DiceRollStatePayload,
            _object(context.get("battle_shock_roll_state"), "reroll initial roll"),
        )
    )
    if (
        retained_initial != original_state
        or context.get("battle_shock_test_request") != request_payload
        or context.get("base_payload") != request_base
        or context.get("game_id") != request_base.get("game_id")
        or context.get("battle_round") != request_base.get("battle_round")
        or context.get("phase") != request_base.get("phase")
        or context.get("active_player_id") != request_base.get("active_player_id")
        or context.get("source_kind") != request_base.get("source_kind")
    ):
        raise GameLifecycleError("Battle-shock reroll occurrence context drifted.")
    permission = RerollPermission.from_payload(
        cast(RerollPermissionPayload, _object(payload.get("permission"), "reroll permission"))
    )
    expected_request = DiceRollManager(
        _identifier(request_base.get("game_id"), "reroll game")
    ).build_reroll_request(
        original_state,
        request_id=record.request.request_id,
        actor_id=record.request.actor_id,
        permission=permission,
        extra_payload={"battle_shock_context": context},
    )
    selected = record.request.option_by_id(record.result.selected_option_id)
    if (
        record.request != expected_request
        or record.result.payload != selected.payload
        or accepted != bool(_selected_reroll_indices(record))
        or permission.owning_player_id != _result_actor(record)
        or not phase_start_ids == tuple(sorted(phase_start_ids))
    ):
        raise GameLifecycleError("Battle-shock reroll request or disposition drifted.")
    return BattleShockRerollAuthority(
        decision_record=record,
        permission=permission,
        decision_requested_event_index=requested[0],
        decision_recorded_event_index=recorded[0],
        disposition_event_index=recorded[0],
        accepted=accepted,
        passed_state_policy=_passed_state_policy(context),
        resolved_event_types=event_types,
        additional_modifier_applications=additional_applications,
    )


def _result_actor(record: DecisionRecord) -> str:
    if record.result.actor_id is None:
        raise GameLifecycleError("Battle-shock reroll result actor is missing.")
    return record.result.actor_id


def _modifier_authority(
    *,
    prior_events: tuple[EventRecord, ...],
    request_payload: dict[str, JsonValue],
    request_base: dict[str, JsonValue],
    result: BattleShockResult,
    latest_roll_authority_index: int,
) -> _ModifierAuthority:
    matches = tuple(
        (index, event)
        for index, event in enumerate(prior_events)
        if event.event_type == BATTLE_SHOCK_MODIFIER_APPLICATION_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == request_payload
    )
    if len(matches) != 1 or matches[0][0] <= latest_roll_authority_index:
        raise GameLifecycleError("Battle-shock modifier application authority is missing.")
    payload = cast(dict[str, JsonValue], matches[0][1].payload)
    raw_applications = payload.get("battle_shock_modifier_applications")
    if not isinstance(raw_applications, list) or any(
        not isinstance(value, dict) for value in raw_applications
    ):
        raise GameLifecycleError("Battle-shock modifier applications are invalid.")
    applications = tuple(
        BattleShockModifierApplication.from_payload(
            cast(BattleShockModifierApplicationPayload, value)
        )
        for value in raw_applications
        if isinstance(value, dict)
    )
    phase_start_ids = _identifier_list(
        payload.get("phase_start_battle_shocked_unit_ids"),
        "phase-start modifier units",
    )
    expected = validate_json_value(
        {
            **request_base,
            "battle_shock_test_request": request_payload,
            "phase_start_battle_shocked_unit_ids": list(phase_start_ids),
            "battle_shock_modifier_applications": [
                application.to_payload() for application in applications
            ],
        }
    )
    flattened = tuple(
        modifier for application in applications for modifier in application.modifiers
    )
    keys = tuple((application.hook_id, application.source_id) for application in applications)
    if (
        payload != expected
        or keys != tuple(sorted(keys))
        or len(set(keys)) != len(keys)
        or tuple(sorted(flattened, key=lambda value: value.modifier_id))
        != result.modified_roll.modifiers
    ):
        raise GameLifecycleError("Battle-shock modifier application authority drifted.")
    return _ModifierAuthority(matches[0][0], phase_start_ids, applications)


def _validate_resolved_event_inventory(
    *,
    event_records: tuple[EventRecord, ...],
    resolved_payload: dict[str, JsonValue],
    modifier_event_index: int,
    reroll: BattleShockRerollAuthority,
) -> None:
    context = _object(
        _object(reroll.decision_record.request.payload, "reroll request").get(
            "battle_shock_context"
        ),
        "reroll context",
    )
    event_types = _identifier_list(
        context.get("resolved_event_types"),
        "reroll resolved event types",
        require_sorted=False,
    )
    for event_type in event_types:
        matches = tuple(
            index
            for index, event in enumerate(event_records)
            if event.event_type == event_type and event.payload == resolved_payload
        )
        if len(matches) != 1 or matches[0] <= modifier_event_index:
            raise GameLifecycleError("Battle-shock resolved event inventory drifted.")


def _validate_reason_context(result: BattleShockResult) -> None:
    reason = result.request.reason
    context = result.request.below_half_strength_context
    if (
        reason is BattleShockTestReason.BELOW_HALF_STRENGTH
        and not context.is_at_or_below_half_strength
    ):
        raise GameLifecycleError("Battle-shock below-half reason lacks predicate authority.")
    if (
        reason is BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED
        and not context.is_below_starting_strength
    ):
        raise GameLifecycleError(
            "Battle-shock below-starting-strength reason lacks predicate authority."
        )


def _with_disposition(
    authority: BattleShockRerollAuthority,
    disposition_event_index: int,
) -> BattleShockRerollAuthority:
    return BattleShockRerollAuthority(
        decision_record=authority.decision_record,
        permission=authority.permission,
        decision_requested_event_index=authority.decision_requested_event_index,
        decision_recorded_event_index=authority.decision_recorded_event_index,
        disposition_event_index=disposition_event_index,
        accepted=authority.accepted,
        passed_state_policy=authority.passed_state_policy,
        resolved_event_types=authority.resolved_event_types,
        additional_modifier_applications=authority.additional_modifier_applications,
    )


def _passed_state_policy(
    context: dict[str, JsonValue],
) -> BattleShockPassedStatePolicy:
    token = _identifier(context.get("passed_state_policy"), "reroll state policy")
    try:
        return BattleShockPassedStatePolicy(token)
    except ValueError as exc:
        raise GameLifecycleError("Battle-shock reroll state policy is unsupported.") from exc


def _validate_source_state_policy(
    *,
    source_kind: str,
    passed_state_policy: BattleShockPassedStatePolicy,
) -> None:
    supported_preserve_sources = frozenset(
        {
            "catalog_selected_target_effect",
            "command_phase_start_battle_shock",
            "desperate_escape_battle_shock",
            "forced_desperate_escape_battle_shock",
            "stratagem_battle_shock",
            "unit_move_completed_battle_shock",
        }
    )
    if source_kind == "command_battle_shock":
        expected = BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED
    elif source_kind in supported_preserve_sources:
        expected = BattleShockPassedStatePolicy.PRESERVE
    else:
        raise GameLifecycleError("Battle-shock reroll source kind is unsupported.")
    if passed_state_policy is not expected:
        raise GameLifecycleError("Battle-shock reroll passed-state policy drifted.")


def _selected_reroll_indices(record: DecisionRecord) -> tuple[int, ...]:
    raw = _object(record.result.payload, "reroll result").get("selected_indices")
    if not isinstance(raw, list) or any(type(value) is not int for value in raw):
        raise GameLifecycleError("Battle-shock reroll selected indices are invalid.")
    indices = tuple(cast(list[int], raw))
    if indices != tuple(sorted(set(indices))) or any(index < 0 for index in indices):
        raise GameLifecycleError("Battle-shock reroll selected indices drifted.")
    return indices


def _reroll_request_payload(record: DecisionRecord) -> JsonValue:
    if not isinstance(record.request.payload, dict):
        return None
    context = record.request.payload.get("battle_shock_context")
    if not isinstance(context, dict):
        return None
    return context.get("battle_shock_test_request")


def _identifier_list(
    value: JsonValue,
    context: str,
    *,
    require_sorted: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        type(item) is not str or not item.strip() for item in value
    ):
        raise GameLifecycleError(f"Battle-shock {context} is invalid.")
    values = tuple(cast(list[str], value))
    if len(set(values)) != len(values) or (require_sorted and values != tuple(sorted(values))):
        raise GameLifecycleError(f"Battle-shock {context} drifted.")
    return values


def _modifier_application_list(
    value: JsonValue,
    context: str,
) -> tuple[BattleShockModifierApplication, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise GameLifecycleError(f"Battle-shock {context} is invalid.")
    applications = tuple(
        BattleShockModifierApplication.from_payload(
            cast(BattleShockModifierApplicationPayload, item)
        )
        for item in value
        if isinstance(item, dict)
    )
    identities = tuple((row.hook_id, row.source_id) for row in applications)
    if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
        raise GameLifecycleError(f"Battle-shock {context} drifted.")
    return applications


def _object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Battle-shock {context} must be an object.")
    return value


def _identifier(value: JsonValue, context: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Battle-shock {context} must be an identifier.")
    return value


def _phase(value: JsonValue) -> BattlePhase:
    token = _identifier(value, "phase")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError("Battle-shock phase is unsupported.") from exc


__all__ = (
    "BattleShockRerollAuthority",
    "BattleShockResolutionAuthority",
    "PendingBattleShockRerollAuthority",
    "parse_battle_shock_resolution_authority",
    "parse_pending_battle_shock_reroll_authority",
)
