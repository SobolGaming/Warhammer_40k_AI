from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.command_points import (
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandPointSpendResultPayload,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    parameterized_decision_option,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems_model import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    StratagemUseRecord,
)
from warhammer40k_core.engine.stratagems_selection import (
    stratagem_selection_from_decision_result,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    ReactionWindowPayload,
    TimingWindowError,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState

_PROPOSAL_PAYLOAD_KEYS = frozenset(
    {
        "proposal_kind",
        "context",
        "catalog_record",
        "target_binding",
        "effect_selection",
    }
)
_PROPOSAL_REQUEST_CONTEXT_KEYS = frozenset(
    {"request_id", "decision_type", "actor_id", *_PROPOSAL_PAYLOAD_KEYS}
)


@dataclass(frozen=True, slots=True)
class StratagemUseHistoryAuthority:
    use_record: StratagemUseRecord
    catalog_record: StratagemCatalogRecord
    decision_record: DecisionRecord
    proposal_request: StratagemTargetProposal
    submitted_proposal: StratagemTargetProposal
    requested_event_index: int
    recorded_event_index: int
    accepted_event_index: int
    spend_event_index: int | None
    used_event_index: int


@dataclass(frozen=True, slots=True)
class FiniteStratagemUseHistoryAuthority:
    use_record: StratagemUseRecord
    catalog_record: StratagemCatalogRecord
    decision_record: DecisionRecord
    context: StratagemEligibilityContext
    target_binding: StratagemTargetBinding
    effect_selection: JsonValue
    requested_event_index: int
    recorded_event_index: int
    spend_event_index: int | None
    used_event_index: int


def validate_stratagem_use_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    use_record: StratagemUseRecord,
    mutation_index: int,
) -> StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority:
    matches = tuple(
        record
        for record in decision_records
        if record.request.request_id == use_record.request_id
        and record.result.result_id == use_record.result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Stratagem-use source decision authority drifted.")
    decision_type = matches[0].request.decision_type
    if decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return validate_parameterized_stratagem_use_history(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            use_record=use_record,
            mutation_index=mutation_index,
        )
    if decision_type == STRATAGEM_DECISION_TYPE:
        return validate_finite_stratagem_use_history(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            use_record=use_record,
            mutation_index=mutation_index,
        )
    raise GameLifecycleError("Stratagem-use source decision type is unsupported.")


def validate_finite_stratagem_use_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    use_record: StratagemUseRecord,
    mutation_index: int,
) -> FiniteStratagemUseHistoryAuthority:
    """Bind a retained use to its exact finite option, CP spend, state row, and events."""
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Stratagem-use history requires a StratagemUseRecord.")
    if type(mutation_index) is not int or not 0 <= mutation_index <= len(event_records):
        raise GameLifecycleError("Stratagem-use mutation index is invalid.")
    _validate_exact_state_use(state=state, use_record=use_record)
    used_index = _exact_use_event_index(
        event_records=event_records,
        use_record=use_record,
        mutation_index=mutation_index,
    )
    decision_record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=used_index,
        request_id=use_record.request_id,
        result_id=use_record.result_id,
    )
    requested_index, recorded_index = _exact_decision_event_indices(
        event_records=event_records,
        decision_record=decision_record,
        used_index=used_index,
    )
    context, catalog_record, target_binding, effect_selection = _finite_selection(decision_record)
    _validate_finite_use_binding(
        use_record=use_record,
        decision_record=decision_record,
        context=context,
        catalog_record=catalog_record,
        target_binding=target_binding,
        effect_selection=effect_selection,
    )
    spend_index = _validate_command_point_spend(
        state=state,
        event_records=event_records,
        use_record=use_record,
        accepted_index=recorded_index,
        used_index=used_index,
    )
    _validate_deterministic_use_id(
        event_records=event_records,
        use_record=use_record,
        used_index=used_index,
    )
    if catalog_record.definition.restriction_policy.once_per_battle:
        same_uses = tuple(
            stored
            for stored in state.stratagem_use_records
            if stored.player_id == use_record.player_id
            and stored.stratagem_id == use_record.stratagem_id
        )
        if same_uses != (use_record,):
            raise GameLifecycleError("Once-per-battle Stratagem-use authority drifted.")
    return FiniteStratagemUseHistoryAuthority(
        use_record=use_record,
        catalog_record=catalog_record,
        decision_record=decision_record,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        requested_event_index=requested_index,
        recorded_event_index=recorded_index,
        spend_event_index=spend_index,
        used_event_index=used_index,
    )


def validate_parameterized_stratagem_use_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    use_record: StratagemUseRecord,
    mutation_index: int,
) -> StratagemUseHistoryAuthority:
    """Bind a retained use to its exact proposal, CP spend, state row, and events."""
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Stratagem-use history requires a StratagemUseRecord.")
    if type(mutation_index) is not int or not 0 <= mutation_index <= len(event_records):
        raise GameLifecycleError("Stratagem-use mutation index is invalid.")
    _validate_exact_state_use(state=state, use_record=use_record)
    used_index = _exact_use_event_index(
        event_records=event_records,
        use_record=use_record,
        mutation_index=mutation_index,
    )
    decision_record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=used_index,
        request_id=use_record.request_id,
        result_id=use_record.result_id,
    )
    requested_index, recorded_index = _exact_decision_event_indices(
        event_records=event_records,
        decision_record=decision_record,
        used_index=used_index,
    )
    proposal_request = _proposal_from_exact_request(decision_record)
    submitted_proposal = _proposal_from_exact_result(decision_record)
    _validate_proposal_use_binding(
        use_record=use_record,
        proposal_request=proposal_request,
        submitted_proposal=submitted_proposal,
        decision_record=decision_record,
    )
    accepted_index = _exact_accepted_event_index(
        event_records=event_records,
        decision_record=decision_record,
        submitted_proposal=submitted_proposal,
        recorded_index=recorded_index,
        used_index=used_index,
    )
    spend_index = _validate_command_point_spend(
        state=state,
        event_records=event_records,
        use_record=use_record,
        accepted_index=accepted_index,
        used_index=used_index,
    )
    _validate_deterministic_use_id(
        event_records=event_records,
        use_record=use_record,
        used_index=used_index,
    )
    if proposal_request.catalog_record.definition.restriction_policy.once_per_battle:
        same_uses = tuple(
            stored
            for stored in state.stratagem_use_records
            if stored.player_id == use_record.player_id
            and stored.stratagem_id == use_record.stratagem_id
        )
        if same_uses != (use_record,):
            raise GameLifecycleError("Once-per-battle Stratagem-use authority drifted.")
    return StratagemUseHistoryAuthority(
        use_record=use_record,
        catalog_record=proposal_request.catalog_record,
        decision_record=decision_record,
        proposal_request=proposal_request,
        submitted_proposal=submitted_proposal,
        requested_event_index=requested_index,
        recorded_event_index=recorded_index,
        accepted_event_index=accepted_index,
        spend_event_index=spend_index,
        used_event_index=used_index,
    )


def validate_loaded_stratagem_use_provider(
    *,
    authority: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
    runtime_content_bundle: RuntimeContentBundle,
    built_in_handler_ids: frozenset[str] = frozenset(),
) -> None:
    """Bind the authenticated proposal row to the enabled player runtime index."""
    if type(authority) not in {
        StratagemUseHistoryAuthority,
        FiniteStratagemUseHistoryAuthority,
    }:
        raise GameLifecycleError("Loaded Stratagem authority requires validated use history.")
    if type(built_in_handler_ids) is not frozenset or any(
        type(handler_id) is not str or not handler_id.strip() for handler_id in built_in_handler_ids
    ):
        raise GameLifecycleError("Built-in Stratagem handler IDs must be a frozenset.")
    use = authority.use_record
    index = runtime_content_bundle.stratagem_indexes_by_player_id.get(use.player_id)
    if index is None:
        raise GameLifecycleError("Stratagem use lacks its loaded player catalog index.")
    matches = tuple(
        record
        for record in index.all_records()
        if record.definition.stratagem_id == use.stratagem_id
    )
    if len(matches) != 1 or matches[0] != authority.catalog_record or matches[0].disabled:
        raise GameLifecycleError("Stratagem-use loaded catalog authority drifted.")
    handler_id = use.handler_id
    if handler_id not in built_in_handler_ids and not (
        runtime_content_bundle.stratagem_handler_registry.has_handler(handler_id)
    ):
        raise GameLifecycleError("Stratagem-use handler lacks loaded provider authority.")


def _finite_selection(
    record: DecisionRecord,
) -> tuple[
    StratagemEligibilityContext,
    StratagemCatalogRecord,
    StratagemTargetBinding,
    JsonValue,
]:
    request = record.request
    result = record.result
    if (
        request.decision_type != STRATAGEM_DECISION_TYPE
        or request.actor_id is None
        or result.decision_type != STRATAGEM_DECISION_TYPE
        or result.actor_id != request.actor_id
    ):
        raise GameLifecycleError("Finite Stratagem-use decision identity drifted.")
    request_payload = _object(request.payload, context="finite request")
    direct_payload = {
        "stratagem_context": request_payload.get("stratagem_context"),
        "finite": request_payload.get("finite"),
    }
    if frozenset(request_payload) == frozenset(direct_payload):
        pass
    elif frozenset(request_payload) == frozenset(
        {
            *direct_payload,
            "reaction_window",
            "interrupts_parent",
            "parent",
            "handler_payload",
        }
    ):
        handler_payload = _object(
            request_payload.get("handler_payload"), context="reaction handler payload"
        )
        reaction_window = _object(request_payload.get("reaction_window"), context="reaction window")
        parent = _object(request_payload.get("parent"), context="reaction parent")
        if frozenset(reaction_window) != frozenset(
            {"timing_window", "eligible_player_ids", "blocks_parent"}
        ):
            raise GameLifecycleError("Finite Stratagem-use reaction window shape drifted.")
        try:
            parsed_reaction_window = ReactionWindow.from_payload(
                cast(ReactionWindowPayload, reaction_window)
            )
        except (KeyError, TimingWindowError) as exc:
            raise GameLifecycleError("Finite Stratagem-use reaction window is invalid.") from exc
        if (
            handler_payload != direct_payload
            or request_payload.get("interrupts_parent") is not True
            or frozenset(parent) != frozenset({"phase", "step", "resume_token"})
            or parsed_reaction_window.timing_window.phase is None
            or parsed_reaction_window.timing_window.phase.value != parent.get("phase")
            or request.actor_id not in parsed_reaction_window.eligible_player_ids
            or not parsed_reaction_window.blocks_parent
        ):
            raise GameLifecycleError("Finite Stratagem-use reaction context drifted.")
    else:
        raise GameLifecycleError("Finite Stratagem-use request shape drifted.")
    if request_payload.get("finite") is not True:
        raise GameLifecycleError("Finite Stratagem-use marker drifted.")
    matching_options = tuple(
        option for option in request.options if option.option_id == result.selected_option_id
    )
    if len(matching_options) != 1 or matching_options[0].payload != result.payload:
        raise GameLifecycleError("Finite Stratagem-use selected option authority drifted.")
    selection = stratagem_selection_from_decision_result(result)
    if selection is None:
        raise GameLifecycleError("Finite Stratagem-use result payload drifted.")
    context, catalog_record, target_binding, effect_selection = selection
    if request_payload.get("stratagem_context") != validate_json_value(context.to_payload()) or (
        "reaction_window" in request_payload
        and _object(
            _object(request_payload.get("reaction_window"), context="reaction window").get(
                "timing_window"
            ),
            context="timing window",
        ).get("phase")
        != context.phase.value
    ):
        raise GameLifecycleError("Finite Stratagem-use request context drifted.")
    return context, catalog_record, target_binding, effect_selection


def _validate_finite_use_binding(
    *,
    use_record: StratagemUseRecord,
    decision_record: DecisionRecord,
    context: StratagemEligibilityContext,
    catalog_record: StratagemCatalogRecord,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
) -> None:
    definition = catalog_record.definition
    if (
        use_record.player_id != context.player_id
        or use_record.stratagem_id != definition.stratagem_id
        or use_record.source_id != definition.source_id
        or use_record.battle_round != context.battle_round
        or use_record.phase is not context.phase
        or use_record.active_player_id != context.active_player_id
        or use_record.timing_window_id != context.timing_window_id
        or use_record.request_id != decision_record.request.request_id
        or use_record.result_id != decision_record.result.result_id
        or use_record.selected_option_id != decision_record.result.selected_option_id
        or use_record.target_binding != target_binding
        or use_record.handler_id != definition.handler_id
        or use_record.effect_selection != effect_selection
        or use_record.effect_payload != definition.effect_payload
        or not use_record.effects_resolved
        or use_record.unresolved_reason is not None
    ):
        raise GameLifecycleError("Finite Stratagem-use binding drifted.")


def _validate_exact_state_use(*, state: GameState, use_record: StratagemUseRecord) -> None:
    matches = tuple(
        stored for stored in state.stratagem_use_records if stored.use_id == use_record.use_id
    )
    if matches != (use_record,):
        raise GameLifecycleError("Stratagem-use state authority drifted.")


def _exact_use_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    use_record: StratagemUseRecord,
    mutation_index: int,
) -> int:
    matching_ids = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "stratagem_used"
        and isinstance(event.payload, dict)
        and event.payload.get("use_id") == use_record.use_id
    )
    expected_payload = validate_json_value(use_record.to_payload())
    if (
        len(matching_ids) != 1
        or matching_ids[0][1].payload != expected_payload
        or matching_ids[0][0] >= mutation_index
    ):
        raise GameLifecycleError("Stratagem-use event authority drifted.")
    return matching_ids[0][0]


def _proposal_from_exact_request(record: DecisionRecord) -> StratagemTargetProposal:
    request = record.request
    if (
        request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        or request.actor_id is None
        or request.options != (parameterized_decision_option(),)
    ):
        raise GameLifecycleError("Stratagem-use proposal request authority drifted.")
    payload = _object(request.payload, context="proposal request")
    if frozenset(payload) not in {
        frozenset({"proposal_request"}),
        frozenset({"proposal_request", "declinable"}),
    }:
        raise GameLifecycleError("Stratagem-use proposal request shape drifted.")
    if "declinable" in payload and payload["declinable"] is not True:
        raise GameLifecycleError("Stratagem-use proposal decline authority drifted.")
    context = _object(payload.get("proposal_request"), context="proposal request context")
    if frozenset(context) != _PROPOSAL_REQUEST_CONTEXT_KEYS:
        raise GameLifecycleError("Stratagem-use proposal request context shape drifted.")
    if (
        context.get("request_id") != request.request_id
        or context.get("decision_type") != request.decision_type
        or context.get("actor_id") != request.actor_id
    ):
        raise GameLifecycleError("Stratagem-use proposal request identity drifted.")
    proposal_payload = {key: context[key] for key in _PROPOSAL_PAYLOAD_KEYS}
    proposal = _proposal_from_payload(proposal_payload)
    expected: dict[str, JsonValue] = {
        "proposal_request": {
            "request_id": request.request_id,
            "decision_type": request.decision_type,
            "actor_id": request.actor_id,
            **cast(dict[str, JsonValue], validate_json_value(proposal.to_payload())),
        }
    }
    if "declinable" in payload:
        expected["declinable"] = True
    if payload != validate_json_value(expected) or proposal.target_binding is not None:
        raise GameLifecycleError("Stratagem-use proposal request payload drifted.")
    return proposal


def _exact_decision_event_indices(
    *,
    event_records: tuple[EventRecord, ...],
    decision_record: DecisionRecord,
    used_index: int,
) -> tuple[int, int]:
    requested = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_requested"
        and event.payload == decision_record.request.to_payload()
    )
    recorded = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_recorded" and event.payload == decision_record.to_payload()
    )
    if len(requested) != 1 or len(recorded) != 1 or not requested[0] < recorded[0] < used_index:
        raise GameLifecycleError("Stratagem-use decision event order drifted.")
    return requested[0], recorded[0]


def _proposal_from_exact_result(record: DecisionRecord) -> StratagemTargetProposal:
    result = record.result
    if (
        result.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        or result.actor_id != record.request.actor_id
        or result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID
    ):
        raise GameLifecycleError("Stratagem-use proposal result authority drifted.")
    payload = _object(result.payload, context="proposal result")
    if frozenset(payload) != frozenset({"proposal"}):
        raise GameLifecycleError("Stratagem-use proposal result shape drifted.")
    raw_proposal = _object(payload.get("proposal"), context="submitted proposal")
    if frozenset(raw_proposal) != _PROPOSAL_PAYLOAD_KEYS:
        raise GameLifecycleError("Stratagem-use submitted proposal shape drifted.")
    proposal = _proposal_from_payload(raw_proposal)
    if payload != validate_json_value({"proposal": proposal.to_payload()}):
        raise GameLifecycleError("Stratagem-use submitted proposal payload drifted.")
    return proposal


def _proposal_from_payload(payload: dict[str, JsonValue]) -> StratagemTargetProposal:
    try:
        return StratagemTargetProposal.from_payload(cast(StratagemTargetProposalPayload, payload))
    except KeyError as exc:
        raise GameLifecycleError("Stratagem-use proposal payload is incomplete.") from exc


def _validate_proposal_use_binding(
    *,
    use_record: StratagemUseRecord,
    proposal_request: StratagemTargetProposal,
    submitted_proposal: StratagemTargetProposal,
    decision_record: DecisionRecord,
) -> None:
    context = proposal_request.context
    definition = proposal_request.catalog_record.definition
    if (
        submitted_proposal.proposal_kind != proposal_request.proposal_kind
        or submitted_proposal.context != context
        or submitted_proposal.catalog_record != proposal_request.catalog_record
        or submitted_proposal.target_binding is None
        or use_record.player_id != context.player_id
        or use_record.stratagem_id != definition.stratagem_id
        or use_record.source_id != definition.source_id
        or use_record.battle_round != context.battle_round
        or use_record.phase is not context.phase
        or use_record.active_player_id != context.active_player_id
        or use_record.timing_window_id != context.timing_window_id
        or use_record.request_id != decision_record.request.request_id
        or use_record.result_id != decision_record.result.result_id
        or use_record.selected_option_id != decision_record.result.selected_option_id
        or use_record.target_binding != submitted_proposal.target_binding
        or use_record.handler_id != definition.handler_id
        or use_record.effect_selection != submitted_proposal.effect_selection
        or use_record.effect_payload != definition.effect_payload
        or not use_record.effects_resolved
        or use_record.unresolved_reason is not None
    ):
        raise GameLifecycleError("Stratagem-use proposal binding drifted.")


def _exact_accepted_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    decision_record: DecisionRecord,
    submitted_proposal: StratagemTargetProposal,
    recorded_index: int,
    used_index: int,
) -> int:
    expected = validate_json_value(
        {
            "request_id": decision_record.request.request_id,
            "result_id": decision_record.result.result_id,
            "proposal": submitted_proposal.to_payload(),
        }
    )
    matches = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "stratagem_target_proposal_accepted" and event.payload == expected
    )
    if len(matches) != 1 or not recorded_index < matches[0] < used_index:
        raise GameLifecycleError("Stratagem-use accepted-proposal authority drifted.")
    return matches[0]


def _validate_command_point_spend(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    use_record: StratagemUseRecord,
    accepted_index: int,
    used_index: int,
) -> int | None:
    matching_events = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "command_points_spent"
        and isinstance(event.payload, dict)
        and event.payload.get("source_id") == use_record.use_id
    )
    if use_record.command_point_cost == 0:
        if use_record.command_point_transaction_id is not None or matching_events:
            raise GameLifecycleError("Zero-cost Stratagem-use spend authority drifted.")
        return None
    if len(matching_events) != 1:
        raise GameLifecycleError("Stratagem-use Command-point spend event drifted.")
    spend_index, spend_event = matching_events[0]
    if not accepted_index < spend_index < used_index:
        raise GameLifecycleError("Stratagem-use Command-point spend order drifted.")
    payload = _object(spend_event.payload, context="Command-point spend")
    if frozenset(payload) != frozenset(
        {
            "player_id",
            "battle_round",
            "requested_amount",
            "applied_amount",
            "status",
            "source_id",
            "source_kind",
            "transaction",
            "insufficient_reason",
        }
    ):
        raise GameLifecycleError("Stratagem-use Command-point spend shape drifted.")
    try:
        spend = CommandPointSpendResult.from_payload(cast(CommandPointSpendResultPayload, payload))
    except KeyError as exc:
        raise GameLifecycleError("Stratagem-use Command-point spend is incomplete.") from exc
    transaction_id = use_record.command_point_transaction_id
    ledger = state.command_point_ledger_for_player(use_record.player_id)
    transactions = tuple(
        transaction
        for transaction in ledger.transactions
        if transaction.transaction_id == transaction_id
    )
    if (
        payload != validate_json_value(spend.to_payload())
        or spend.status is not CommandPointSpendStatus.APPLIED
        or spend.player_id != use_record.player_id
        or spend.battle_round != use_record.battle_round
        or spend.requested_amount != use_record.command_point_cost
        or spend.applied_amount != use_record.command_point_cost
        or spend.source_id != use_record.use_id
        or spend.source_kind is not CommandPointSourceKind.STRATAGEM_SPEND
        or spend.transaction is None
        or spend.transaction.transaction_id != transaction_id
        or transactions != (spend.transaction,)
    ):
        raise GameLifecycleError("Stratagem-use Command-point spend authority drifted.")
    return spend_index


def _validate_deterministic_use_id(
    *,
    event_records: tuple[EventRecord, ...],
    use_record: StratagemUseRecord,
    used_index: int,
) -> None:
    ordinal = 1 + sum(event.event_type == "stratagem_used" for event in event_records[:used_index])
    expected = (
        f"stratagem-use:{use_record.player_id}:round-{use_record.battle_round:02d}:{ordinal:06d}"
    )
    if use_record.use_id != expected:
        raise GameLifecycleError("Stratagem-use deterministic identity drifted.")


def _object(value: JsonValue, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Stratagem-use {context} must be an object.")
    return value


__all__ = (
    "FiniteStratagemUseHistoryAuthority",
    "StratagemUseHistoryAuthority",
    "validate_finite_stratagem_use_history",
    "validate_loaded_stratagem_use_provider",
    "validate_parameterized_stratagem_use_history",
    "validate_stratagem_use_history",
)
