"""Authenticate retained shooting permissions, nested hosts and physical completion."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.retained_destruction_state import RetainedModelDestruction
from warhammer40k_core.engine.retained_shooting import (
    RetainedShootingExecution,
    current_retained_shooter,
    retained_shooting_executions,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_retained_shooting_history(
    *, state: GameState, event_records: tuple[EventRecord, ...]
) -> None:
    opened: dict[str, tuple[RetainedModelDestruction, dict[str, JsonValue]]] = {}
    selected: dict[str, dict[str, JsonValue]] = {}
    starts: dict[str, int] = {}
    stack: list[RetainedShootingExecution] = []
    for index, event in enumerate(event_records):
        if event.event_type == "fight_on_death_retention_opened":
            payload = _object(event.payload)
            record = RetainedModelDestruction.from_payload(payload["destruction"])
            opened[record.cause_id] = record, payload
        elif event.event_type == "fight_on_death_retention_selected":
            payload = _object(event.payload)
            selected[_string(payload, "cause_id")] = payload
        elif event.event_type == "retained_shooting_started":
            execution = RetainedShootingExecution.from_payload(event.payload)
            if execution.parent_cause_id != (stack[-1].cause_id if stack else None):
                raise GameLifecycleError(
                    "Retained shooting parent differs from chronological history."
                )
            if execution.cause_id not in opened or execution.cause_id not in selected:
                raise GameLifecycleError(
                    "Retained shooting lacks its original destruction selection."
                )
            record, _opening = opened[execution.cause_id]
            choice = selected[execution.cause_id]
            sources = [
                source
                for source in record.eligible_sources
                if source.source_id == execution.source_id
            ]
            if (
                execution.cause_id in starts
                or execution.attacks_completed
                or len(sources) != 1
                or sources[0].source_rule_id != execution.source_rule_id
                or execution.model_instance_id != record.model_instance_id
                or choice["selected_action"] != "shoot"
                or choice["selected_source_id"] != execution.source_id
                or choice["request_id"] != execution.source_request_id
                or choice["result_id"] != execution.source_result_id
            ):
                raise GameLifecycleError("Retained shooting source or action entitlement drift.")
            if execution.suspended_shooting is not None and stack:
                parent = stack[-1]
                host = execution.suspended_shooting
                if (
                    parent.attacks_completed
                    or host.source_decision_request_id != parent.source_request_id
                    or host.source_decision_result_id != parent.source_result_id
                    or host.source_rule_id != parent.source_rule_id
                ):
                    raise GameLifecycleError("Retained shooting suspended parent source drift.")
            starts[execution.cause_id] = index
            stack.append(execution)
        elif event.event_type == "retained_shooting_hazardous_automatically_passed":
            _validate_automatic_hazardous(
                event=event,
                index=index,
                stack=stack,
                starts=starts,
                opened=opened,
                event_records=event_records,
            )
        elif event.event_type == "retained_shooting_attacks_completed":
            payload = _object(event.payload)
            execution = _top_execution(stack, payload)
            if execution.attacks_completed or set(payload) != {
                "cause_id",
                "model_instance_id",
                "attack_pools",
            }:
                raise GameLifecycleError(
                    "Retained shooting completed more than once or with drifted fields."
                )
            prior = event_records[starts[execution.cause_id] + 1 : index]
            declarations = _declarations(prior, execution)
            pools = payload["attack_pools"]
            if not isinstance(pools, list):
                raise GameLifecycleError("Retained shooting completion pools are invalid.")
            if pools:
                if (
                    len(declarations) != 1
                    or _object(declarations[0].payload)["attack_pools"] != pools
                ):
                    raise GameLifecycleError(
                        "Retained shooting completion lacks its exact declaration."
                    )
                declaration = _object(declarations[0].payload)
                sequence_id = f"out-of-phase-attack-sequence:{_string(declaration, 'result_id')}"
                if (
                    sum(
                        event.event_type == "attack_sequence_completed"
                        and isinstance(event.payload, dict)
                        and event.payload.get("sequence_id") == sequence_id
                        for event in prior
                    )
                    != 1
                ):
                    raise GameLifecycleError(
                        "Retained shooting completed before its attack sequence."
                    )
                _validate_actor_pools(pools, execution)
            elif declarations:
                raise GameLifecycleError("Retained shooting discarded its declared attacks.")
            record, _opening = opened[execution.cause_id]
            if not prior or prior[-1].event_type != "out_of_phase_shooting_completed":
                raise GameLifecycleError(
                    "Retained shooting lacks its ordinary executor completion."
                )
            completion = _object(prior[-1].payload)
            if (
                completion["source_rule_id"] != execution.source_rule_id
                or completion["player_id"] != record.placement.player_id
            ):
                raise GameLifecycleError("Retained shooting executor completion authority drift.")
            stack[-1] = replace(execution, attacks_completed=True)
        elif event.event_type == "retained_shooting_resumed_parent":
            payload = _object(event.payload)
            execution = _top_execution(stack, payload)
            if not execution.attacks_completed or set(payload) != {"cause_id", "model_instance_id"}:
                raise GameLifecycleError("Retained shooting resumed before completing its attacks.")
            if (
                sum(
                    event.event_type == "fight_on_death_destruction_completed"
                    and isinstance(event.payload, dict)
                    and event.payload.get("cause_id") == execution.cause_id
                    for event in event_records[:index]
                )
                != 1
            ):
                raise GameLifecycleError(
                    "Retained shooting resumed before physical destruction completed."
                )
            stack.pop()
    if tuple(stack) != retained_shooting_executions(state=state):
        raise GameLifecycleError("Retained shooting state differs from its authenticated history.")
    for execution in stack:
        record, opening = opened[execution.cause_id]
        effect = next(
            effect for effect in state.persisting_effects if effect.effect_id == execution.effect_id
        )
        phase = BattlePhase(_string(opening, "phase"))
        if (
            effect.owner_player_id != record.placement.player_id
            or effect.target_unit_instance_ids != (record.placement.unit_instance_id,)
            or effect.started_battle_round != opening["battle_round"]
            or effect.started_phase is not phase
            or effect.expiration
            != EffectExpiration.end_phase(
                battle_round=cast(int, opening["battle_round"]),
                phase=phase,
                player_id=_string(opening, "active_player_id"),
            )
        ):
            raise GameLifecycleError("Retained shooting execution owner or lifetime drift.")
    current = current_retained_shooter(state=state)
    if current is not None and (not stack or stack[-1].cause_id != current.cause_id):
        raise GameLifecycleError("Retained shooting active host is not its innermost execution.")
    if stack and not stack[-1].attacks_completed and current is None:
        raise GameLifecycleError("Retained shooting execution lost its active attack host.")


def _validate_automatic_hazardous(
    *,
    event: EventRecord,
    index: int,
    stack: list[RetainedShootingExecution],
    starts: dict[str, int],
    opened: dict[str, tuple[RetainedModelDestruction, dict[str, JsonValue]]],
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.weapon_declaration import (
        RangedAttackPool,
        RangedAttackPoolPayload,
    )

    payload = _object(event.payload)
    execution = _top_execution(stack, payload)
    record, _opening = opened[execution.cause_id]
    source = next(
        source for source in record.eligible_sources if source.source_id == execution.source_id
    )
    prior = event_records[starts[execution.cause_id] + 1 : index]
    declarations = _declarations(prior, execution)
    if (
        execution.attacks_completed
        or len(declarations) != 1
        or not isinstance(source.payload, dict)
        or source.payload.get("shooting_hazardous_tests_automatically_pass") is not True
    ):
        raise GameLifecycleError("Retained shooting Hazardous exception lacks source authority.")
    declaration = _object(declarations[0].payload)
    raw_pools = declaration["attack_pools"]
    _validate_actor_pools(raw_pools, execution)
    pools = tuple(
        RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, pool))
        for pool in cast(list[JsonValue], raw_pools)
    )
    pairs = tuple(
        sorted(
            {
                (pool.weapon_instance_id, pool.weapon_profile.profile_id)
                for pool in pools
                if WeaponKeyword.HAZARDOUS in pool.weapon_profile.keywords
            }
        )
    )
    expected = {
        "cause_id": execution.cause_id,
        "model_instance_id": execution.model_instance_id,
        "source_id": execution.source_id,
        "source_rule_id": execution.source_rule_id,
        "sequence_id": f"out-of-phase-attack-sequence:{_string(declaration, 'result_id')}",
        "weapon_instance_ids": [pair[0] for pair in pairs],
        "weapon_profile_ids": [pair[1] for pair in pairs],
    }
    if (
        not pairs
        or payload != expected
        or any(
            event.event_type == "retained_shooting_hazardous_automatically_passed"
            and isinstance(event.payload, dict)
            and event.payload.get("cause_id") == execution.cause_id
            for event in prior
        )
    ):
        raise GameLifecycleError("Retained shooting Hazardous outcome or weapon identity drift.")


def _declarations(
    events: tuple[EventRecord, ...], execution: RetainedShootingExecution
) -> tuple[EventRecord, ...]:
    return tuple(
        event
        for event in events
        if event.event_type == "out_of_phase_shooting_declaration_accepted"
        and isinstance(event.payload, dict)
        and event.payload.get("source_rule_id") == execution.source_rule_id
        and any(
            isinstance(pool, dict)
            and pool.get("attacker_model_instance_id") == execution.model_instance_id
            for pool in cast(list[JsonValue], event.payload["attack_pools"])
        )
    )


def _validate_actor_pools(pools: JsonValue, execution: RetainedShootingExecution) -> None:
    if (
        not isinstance(pools, list)
        or not pools
        or any(
            not isinstance(pool, dict)
            or pool.get("attacker_model_instance_id") != execution.model_instance_id
            for pool in pools
        )
    ):
        raise GameLifecycleError("Retained shooting declaration includes an unauthorized model.")


def _top_execution(
    stack: list[RetainedShootingExecution], payload: dict[str, JsonValue]
) -> RetainedShootingExecution:
    if (
        not stack
        or payload.get("cause_id") != stack[-1].cause_id
        or payload.get("model_instance_id") != stack[-1].model_instance_id
    ):
        raise GameLifecycleError(
            "Retained shooting event does not belong to the innermost execution."
        )
    return stack[-1]


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Retained shooting history requires an object.")
    return value


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload[key]
    if type(value) is not str or not value:
        raise GameLifecycleError("Retained shooting history requires an identifier.")
    return value
