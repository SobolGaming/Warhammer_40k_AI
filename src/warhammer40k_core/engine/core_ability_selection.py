"""Finite active-instance decisions for persistent native core abilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ability_sources import AbilitySourceInstance
from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.engine.ability_instance_selection import DUPLICATED_ABILITIES_SOURCE_ID
from warhammer40k_core.engine.core_ability_runtime_inventory import core_ability_inventory
from warhammer40k_core.engine.core_ability_state import CoreAbilitySelection, core_instance_groups
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.unit_factory import UnitInstance

SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE = "select_core_ability_instance"
_USE_TIME_FAMILIES = frozenset(
    {CoreAbilityFamily.SCOUTS, CoreAbilityFamily.FEEL_NO_PAIN, CoreAbilityFamily.DEADLY_DEMISE}
)


def core_ability_selection_request(
    *,
    unit: UnitInstance,
    family: CoreAbilityFamily,
    sources: tuple[AbilitySourceInstance, ...],
    player_id: str,
    request_id: str,
    opportunity_id: str,
    secret: bool = False,
) -> DecisionRequest:
    if (
        len(sources) < 2
        or len({source.instance_id for source in sources}) != len(sources)
        or any(source.owner_id != unit.unit_instance_id for source in sources)
    ):
        raise GameLifecycleError("Core instance request requires the complete duplicate inventory.")
    definitions = {
        (ability.source_id, ability.ability_id): ability for ability in unit.datasheet_abilities
    }
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE,
        actor_id=player_id,
        payload=validate_json_value(
            {
                "unit_instance_id": unit.unit_instance_id,
                "player_id": player_id,
                "secret": secret,
                "visibility_source": "core_ability_instance",
                "ability_family": family.value,
                "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                "opportunity_id": opportunity_id,
                "ability_sources": [source.to_payload() for source in sources],
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=source.instance_id,
                label=definitions[(source.source_id, source.ability_id)].name
                if (source.source_id, source.ability_id) in definitions
                else source.ability_id,
                payload=validate_json_value(
                    {
                        "unit_instance_id": unit.unit_instance_id,
                        "ability_family": family.value,
                        "selected_ability_instance_id": source.instance_id,
                        "ability_source": source.to_payload(),
                        "runtime_source": (source.source_id, source.ability_id) not in definitions
                        or len(dict(core_instance_groups(unit)).get(family, ())) < 2,
                        "ability_descriptor": definitions[
                            (source.source_id, source.ability_id)
                        ].to_payload()
                        if (source.source_id, source.ability_id) in definitions
                        else None,
                    }
                ),
            )
            for source in sources
        ),
    )


def request_core_ability_selection_if_needed(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    if state.stage is GameLifecycleStage.COMPLETE or decisions.queue.pending_requests:
        return None
    opportunity_id = _opportunity_id(state, decisions)
    for army in sorted(state.army_definitions, key=lambda army: army.player_id):
        for unit in sorted(army.units, key=lambda unit: unit.unit_instance_id):
            if not unit.alive_own_models():
                continue
            inventory = core_ability_inventory(state=state, unit=unit, registry=registry)
            current_ids = {source.instance_id for _, sources in inventory for source in sources}
            expired = tuple(
                choice
                for choice in unit.core_ability_selections
                if choice.instance_id not in current_ids
            )
            if expired:
                unit = replace(
                    unit,
                    core_ability_selections=tuple(
                        choice for choice in unit.core_ability_selections if choice not in expired
                    ),
                )
                state.replace_army_definitions(
                    [
                        replace(
                            stored,
                            units=tuple(
                                unit if member.unit_instance_id == unit.unit_instance_id else member
                                for member in stored.units
                            ),
                        )
                        if stored.player_id == army.player_id
                        else stored
                        for stored in state.army_definitions
                    ]
                )
                for choice in expired:
                    decisions.event_log.append(
                        "core_ability_instance_expired",
                        validate_json_value(
                            {
                                "unit_instance_id": unit.unit_instance_id,
                                "player_id": army.player_id,
                                "secret": True,
                                "visibility_source": "core_ability_instance",
                                "choice": choice.to_payload(),
                            }
                        ),
                    )
            for family, sources in inventory:
                if family in _USE_TIME_FAMILIES or len(sources) < 2:
                    continue
                if any(
                    choice.family is family and choice.opportunity_id == opportunity_id
                    for choice in unit.core_ability_selections
                ):
                    continue
                request = core_ability_selection_request(
                    unit=unit,
                    family=family,
                    sources=sources,
                    player_id=army.player_id,
                    request_id=state.next_decision_request_id(),
                    opportunity_id=opportunity_id,
                    secret=state.stage is GameLifecycleStage.SETUP,
                )
                decisions.request_decision(request)
                return LifecycleStatus.waiting_for_decision(
                    stage=state.stage, decision_request=request
                )
    return None


def core_ability_selection_dispatch_handler(
    *,
    state_provider: Callable[[], GameState],
    decisions: DecisionController,
    advance: Callable[[], LifecycleStatus],
    registry_provider: Callable[[], RuntimeModifierRegistry],
) -> DecisionDispatchHandler:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        state = state_provider()
        try:
            result.validate_for_request(request)
            unit_id, family = _identity(request)
            unit, player_id = _owned_unit(state, unit_id)
            expected = core_ability_selection_request(
                unit=unit,
                family=family,
                sources=dict(
                    core_ability_inventory(state=state, unit=unit, registry=registry_provider())
                ).get(family, ()),
                player_id=player_id,
                request_id=request.request_id,
                opportunity_id=_opportunity_id(state, decisions),
                secret=state.stage is GameLifecycleStage.SETUP,
            )
        except (DecisionError, GameLifecycleError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={"invalid_reason": "core_ability_instance_drift"},
            )
        if expected != request:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Core ability instance inventory or opportunity drift.",
                payload={"invalid_reason": "core_ability_instance_drift"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        state = state_provider()
        invalid = validate(record.request, result)
        if invalid is not None:
            raise GameLifecycleError("Accepted core ability instance failed revalidation.")
        unit_id, family = _identity(record.request)
        unit, player_id = _owned_unit(state, unit_id)
        choice = CoreAbilitySelection(
            family=family,
            instance_id=result.selected_option_id,
            decision_result_id=result.result_id,
            opportunity_id=_opportunity_id(state, decisions),
            runtime_source=_runtime_selection_source(
                record.request, unit, result.selected_option_id
            ),
        )
        replacement = replace(
            unit,
            core_ability_selections=(
                *(stored for stored in unit.core_ability_selections if stored.family is not family),
                choice,
            ),
        )
        state.replace_army_definitions(
            [
                replace(
                    army,
                    units=tuple(
                        replacement if member.unit_instance_id == unit_id else member
                        for member in army.units
                    ),
                )
                if army.player_id == player_id
                else army
                for army in state.army_definitions
            ]
        )
        decisions.event_log.append(
            "core_ability_instance_selected",
            validate_json_value(
                {
                    "request_id": record.request.request_id,
                    "result_id": result.result_id,
                    "player_id": player_id,
                    "unit_instance_id": unit_id,
                    "choice": choice.to_payload(),
                    "secret": cast(dict[str, JsonValue], record.request.payload)["secret"],
                    "visibility_source": "core_ability_instance",
                    "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                }
            ),
        )
        return advance()

    return DecisionDispatchHandler(
        decision_type=SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE,
        pre_validator=validate,
        applier=apply,
    )


def validate_core_ability_selection_history(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: RuntimeModifierRegistry,
) -> None:
    from warhammer40k_core.engine.ability_instance_history import validate_ability_instance_history

    validate_ability_instance_history(state=state, decisions=decisions)
    records = {
        record.result.result_id: record
        for record in decisions.records
        if record.request.decision_type == SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE
    }
    from warhammer40k_core.engine.core_ability_damage_selection import (
        is_deadly_demise_instance_request,
        validate_deadly_demise_instance_request,
    )

    selected_events = {
        event.payload["result_id"]: event.payload
        for event in decisions.event_log.records
        if event.event_type == "core_ability_instance_selected"
        and isinstance(event.payload, dict)
        and "choice" in event.payload
    }
    if len(selected_events) != len(records):
        raise GameLifecycleError("Core ability instance event inventory drift.")
    recorded_choices: dict[str, CoreAbilitySelection] = {}
    latest: dict[tuple[str, CoreAbilityFamily], str] = {}
    for record in records.values():
        unit_id, family = _identity(record.request)
        latest[(unit_id, family)] = record.result.result_id
        payload = cast(dict[str, JsonValue], record.request.payload)
        choice = CoreAbilitySelection(
            family=family,
            instance_id=record.result.selected_option_id,
            decision_result_id=record.result.result_id,
            opportunity_id=cast(str, payload["opportunity_id"]),
            runtime_source=_recorded_runtime_source(
                record.request, record.result.selected_option_id
            ),
        )
        recorded_choices[record.result.result_id] = choice
        expected_event = {
            "request_id": record.request.request_id,
            "result_id": record.result.result_id,
            "player_id": record.result.actor_id,
            "unit_instance_id": unit_id,
            "choice": choice.to_payload(),
            "secret": payload["secret"],
            "visibility_source": "core_ability_instance",
            "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
        }
        if selected_events.get(record.result.result_id) != expected_event:
            raise GameLifecycleError("Core ability instance decision event drift.")
    for request in decisions.queue.pending_requests:
        if is_deadly_demise_instance_request(request):
            validate_deadly_demise_instance_request(state=state, request=request)
    expired_result_ids: set[str] = set()
    for event in decisions.event_log.records:
        if event.event_type != "core_ability_instance_expired":
            continue
        if not isinstance(event.payload, dict) or not isinstance(event.payload.get("choice"), dict):
            raise GameLifecycleError("Expired core instance requires its recorded choice.")
        raw_choice = cast(dict[str, JsonValue], event.payload["choice"])
        result_id = raw_choice.get("decision_result_id")
        if (
            type(result_id) is not str
            or result_id not in records
            or result_id in expired_result_ids
        ):
            raise GameLifecycleError("Expired core instance decision inventory drift.")
        unit_id, _ = _identity(records[result_id].request)
        if event.payload != {
            "unit_instance_id": unit_id,
            "player_id": records[result_id].result.actor_id,
            "secret": True,
            "visibility_source": "core_ability_instance",
            "choice": recorded_choices[result_id].to_payload(),
        }:
            raise GameLifecycleError("Expired core instance source drift.")
        expired_result_ids.add(result_id)
    for army in state.army_definitions:
        for unit in army.units:
            expected_choices = {
                family: result_id
                for (unit_id, family), result_id in latest.items()
                if unit_id == unit.unit_instance_id and result_id not in expired_result_ids
            }
            if {
                choice.family: choice.decision_result_id for choice in unit.core_ability_selections
            } != expected_choices:
                raise GameLifecycleError("Active core instances do not match the latest decisions.")
            for choice in unit.core_ability_selections:
                choice_record = records.get(choice.decision_result_id)
                if (
                    choice_record is None
                    or choice_record.result.selected_option_id != choice.instance_id
                    or choice_record.result.actor_id != army.player_id
                    or choice != recorded_choices[choice.decision_result_id]
                ):
                    raise GameLifecycleError(
                        "Active core instance lacks its controlling-player decision."
                    )
                unit_id, family = _identity(choice_record.request)
                payload = cast(dict[str, JsonValue], choice_record.request.payload)
                if (
                    unit_id != unit.unit_instance_id
                    or family is not choice.family
                    or payload.get("opportunity_id") != choice.opportunity_id
                ):
                    raise GameLifecycleError("Active core instance decision context drift.")
    for request in decisions.queue.pending_requests:
        if request.decision_type != SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE:
            continue
        unit_id, family = _identity(request)
        unit, player_id = _owned_unit(state, unit_id)
        sources = dict(core_ability_inventory(state=state, unit=unit, registry=registry)).get(
            family, ()
        )
        expected = core_ability_selection_request(
            unit=unit,
            family=family,
            sources=sources,
            player_id=player_id,
            request_id=request.request_id,
            opportunity_id=_opportunity_id(state, decisions),
            secret=state.stage is GameLifecycleStage.SETUP,
        )
        if request != expected:
            raise GameLifecycleError("Pending core instance inventory drift.")


def _identity(request: DecisionRequest) -> tuple[str, CoreAbilityFamily]:
    if request.decision_type != SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE or not isinstance(
        request.payload, dict
    ):
        raise GameLifecycleError("Core instance request requires its typed context.")
    unit_id = request.payload.get("unit_instance_id")
    family = request.payload.get("ability_family")
    if type(unit_id) is not str or type(family) is not str:
        raise GameLifecycleError("Core instance context requires unit and family identifiers.")
    try:
        resolved_family = CoreAbilityFamily(family)
    except ValueError as exc:
        raise GameLifecycleError("Core instance family is unsupported.") from exc
    if resolved_family in _USE_TIME_FAMILIES:
        raise GameLifecycleError("Core instance family requires its use-time decision.")
    return unit_id, resolved_family


def _owned_unit(state: GameState, unit_id: str) -> tuple[UnitInstance, str]:
    matches = tuple(
        (unit, army.player_id)
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Core instance unit ownership drift.")
    return matches[0]


def _opportunity_id(state: GameState, decisions: DecisionController) -> str:
    previous = next(
        (
            record.result.result_id
            for record in reversed(decisions.records)
            if record.request.decision_type != SELECT_CORE_ABILITY_INSTANCE_DECISION_TYPE
        ),
        None,
    )
    payload = {
        "stage": state.stage.value,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "setup_step": None if state.current_setup_step is None else state.current_setup_step.value,
        "phase": None if state.current_battle_phase is None else state.current_battle_phase.value,
        "previous_result_id": previous,
    }
    return f"core-ability-opportunity:{sha256(canonical_json(payload).encode()).hexdigest()}"


def _recorded_runtime_source(
    request: DecisionRequest, selected_id: str
) -> AbilitySourceInstance | None:
    from warhammer40k_core.core.ability_sources import AbilitySourceInstancePayload

    payload = request.option_by_id(selected_id).payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Core ability option requires source context.")
    if payload.get("runtime_source") is True:
        return AbilitySourceInstance.from_payload(
            cast(AbilitySourceInstancePayload, payload["ability_source"])
        )
    return None


def _runtime_selection_source(
    request: DecisionRequest, unit: UnitInstance, selected_id: str
) -> AbilitySourceInstance | None:
    source = _recorded_runtime_source(request, selected_id)
    if source is not None and source.owner_id != unit.unit_instance_id:
        raise GameLifecycleError("Core ability runtime source owner drift.")
    return source
