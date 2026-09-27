"""Canonical finite weapon commitment and pre-pop split authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fight_activation_units import active_fight_activation_rules_unit
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposal
from warhammer40k_core.engine.fight_rules_unit_melee import (
    rules_unit_available_melee_weapons_payloads,
)
from warhammer40k_core.engine.melee_weapon_commitment import (
    COMMITMENT_KEY,
    SELECT_MELEE_WEAPON_DECISION_TYPE,
    MeleeAttackBudget,
    budgets_from_commitment,
    chosen_rows,
    commitment_for_activation,
    object_payload,
    selection_records,
    selection_request,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def current_selection_request(host: GameLifecycle, request_id: str) -> DecisionRequest:
    state, config = host.state, host.config
    if state is None or state.fight_phase_state is None:
        raise GameLifecycleError("Melee weapon commitment requires an active Fight.")
    activation = state.fight_phase_state.active_activation
    if (
        activation is None
        or commitment_for_activation(host.decision_controller, activation.result_id) is not None
    ):
        raise GameLifecycleError("Melee weapon commitment activation is not pending.")
    unit = active_fight_activation_rules_unit(state=state, activation=activation)
    if unit is None:
        raise GameLifecycleError("Melee weapon commitment lost its rules unit.")
    rows = rules_unit_available_melee_weapons_payloads(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=config.ruleset_descriptor,
        rules_unit=unit,
        army_catalog=config.army_catalog,
        state=state,
        source_decision_result_id=activation.result_id,
        runtime_modifier_registry=host._fight_phase_handler.runtime_modifier_registry,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.melee_pool_authority import commitment_inventory

    rows = commitment_inventory(rows, state)
    records = selection_records(host.decision_controller, activation.result_id)
    for index, record in enumerate(records):
        if record.request != selection_request(
            request_id=record.request.request_id,
            activation=activation,
            rows=rows,
            index=index,
            previous=records[:index],
        ):
            raise GameLifecycleError("Melee committed weapon inventory drifted.")
    return selection_request(
        request_id=request_id,
        activation=activation,
        rows=rows,
        index=len(records),
        previous=records,
    )


def validate_declaration_commitment(
    *,
    decisions: DecisionController | None,
    request: DecisionRequest,
    proposal: MeleeDeclarationProposal,
) -> dict[str, MeleeAttackBudget] | None:
    expected = (
        None
        if decisions is None
        else commitment_for_activation(decisions, proposal.source_decision_result_id)
    )
    published = object_payload(request.payload).get(COMMITMENT_KEY)
    if published != expected:
        raise GameLifecycleError("Melee declaration commitment differs from recorded authority.")
    if expected is None:
        return None
    budgets = budgets_from_commitment(expected)
    declared = {declaration.weapon_instance_id for declaration in proposal.declarations}
    if declared != set(budgets) or len(declared) != len(proposal.declarations):
        raise GameLifecycleError(
            "Melee declaration must use exactly the committed physical weapons."
        )
    for declaration in proposal.declarations:
        if declaration.weapon_instance_id is None:
            raise GameLifecycleError("Committed melee declaration requires physical identity.")
        budget = budgets[declaration.weapon_instance_id]
        if declaration.weapon_key != (
            budget.model_instance_id,
            budget.wargear_id,
            budget.weapon_profile_id,
        ):
            raise GameLifecycleError(
                "Melee declaration changed a committed model, weapon or profile."
            )
    return budgets


def validate_selection(
    host: GameLifecycle, request: DecisionRequest, result: DecisionResult
) -> None:
    expected = current_selection_request(host, request.request_id)
    if expected != request:
        raise GameLifecycleError("Melee weapon selection context drifted.")
    result.validate_for_request(expected)
    payload = object_payload(request.payload)
    rows = payload["available_weapons"]
    if not isinstance(rows, list):
        raise GameLifecycleError("Melee weapon inventory is malformed.")
    activation_id = payload["activation_result_id"]
    if type(activation_id) is not str:
        raise GameLifecycleError("Melee activation identity is malformed.")
    records = selection_records(host.decision_controller, activation_id)
    if result.payload is not None:
        selected_id = object_payload(result.payload)["weapon_instance_id"]
        if any(
            row["weapon_instance_id"] == selected_id for row in chosen_rows(tuple(rows), records)
        ):
            raise GameLifecycleError("A physical melee weapon cannot use multiple profiles.")


def decision_dispatch_handlers(host: GameLifecycle) -> tuple[DecisionDispatchHandler, ...]:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        if host.state is None:
            raise GameLifecycleError("Melee commitment requires game state.")
        try:
            validate_selection(host, request, result)
        except (GameLifecycleError, DecisionError) as exc:
            return LifecycleStatus.invalid(
                stage=host.state.stage,
                message=str(exc),
                payload={"invalid_reason": "melee_weapon_commitment_drift"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        # DecisionController has already committed the exact finite payload.
        del record, result
        return host.advance_until_decision_or_terminal()

    return (
        DecisionDispatchHandler(
            decision_type=SELECT_MELEE_WEAPON_DECISION_TYPE, pre_validator=validate, applier=apply
        ),
    )
