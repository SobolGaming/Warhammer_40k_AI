"""Source-backed Stratagem permission to Charge after an enemy completes Fall Back."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargeInterruption, ChargePhaseState
from warhammer40k_core.engine.charge_targets import closest_unit_distance_inches
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import placed_alive_rules_unit_views
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import (
        StratagemEligibilityContext,
        StratagemUseRecord,
    )

ABILITY = "charge_after_enemy_fall_back"
TRIGGER_RANGE = "charge_after_enemy_fall_back_trigger_range_inches"
TRIGGER_EVENT = "fall_back_completion_event_id"
TRIGGER_UNIT = "triggering_unit_instance_id"
CHARGE_POOL = "enemy_units_that_fell_back_this_phase"

_identifier = IdentifierValidator(GameLifecycleError)


def fall_back_charge_trigger_payload(
    *,
    battle_round: int,
    turn_player_id: str,
    source_event_id: str,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
) -> dict[str, JsonValue]:
    """Trust only actual, accepted Fall Back completions at or before this occurrence."""
    pool: set[str] = set()
    for index, event in enumerate(events):
        payload = event.payload
        if (
            event.event_type == "movement_activation_completed"
            and isinstance(payload, dict)
            and payload.get("movement_phase_action") == "fall_back"
            and payload.get("phase") == BattlePhase.MOVEMENT.value
            and payload.get("battle_round") == battle_round
            and payload.get("active_player_id") == turn_player_id
        ):
            unit_id = _identifier("fall back unit", payload.get("unit_instance_id"))
            record = validate_mutation_decision_closure(
                event_records=events,
                decision_records=records,
                mutation_index=index,
                request_id=_identifier("fall back request", payload.get("request_id")),
                result_id=_identifier("fall back result", payload.get("result_id")),
            )
            if record.result.actor_id != turn_player_id:
                raise GameLifecycleError("Fall Back completion actor drift.")
            pool.add(unit_id)
            if event.event_id == source_event_id:
                return {
                    TRIGGER_EVENT: source_event_id,
                    TRIGGER_UNIT: unit_id,
                    CHARGE_POOL: validate_json_value(sorted(pool)),
                }
        if event.event_id == source_event_id:
            break
    raise GameLifecycleError("Charge permission requires an accepted enemy Fall Back completion.")


def fall_back_charge_target_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_unit_id: str | None,
    trigger_range: JsonValue,
) -> str | None:
    if type(trigger_range) not in {int, float} or not isinstance(trigger_range, (int, float)):
        raise GameLifecycleError("Movement Charge permission requires a numeric trigger range.")
    if not 0 < trigger_range <= 12:
        raise GameLifecycleError("Movement Charge permission trigger range is invalid.")
    payload = context.trigger_payload
    if (
        context.trigger_kind is not TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_FALL_BACK
        or context.phase is not BattlePhase.MOVEMENT
        or context.player_id == context.active_player_id
        or not isinstance(payload, dict)
        or TRIGGER_EVENT not in payload
    ):
        return "charge_requires_enemy_fall_back_completion"
    if target_unit_id is None:
        return None
    present = {view.unit_instance_id: view for view in placed_alive_rules_unit_views(state=state)}
    source_unit = _identifier(TRIGGER_UNIT, payload.get(TRIGGER_UNIT))
    if (
        source_unit not in present
        or present[source_unit].owner_player_id != context.active_player_id
    ):
        return "triggering_enemy_not_present"
    if (
        target_unit_id not in present
        or present[target_unit_id].owner_player_id != context.player_id
    ):
        return "charge_unit_off_battlefield"
    if (
        closest_unit_distance_inches(
            scenario=battlefield_scenario_for_state(state=state),
            source_unit_instance_id=target_unit_id,
            target_unit_instance_id=source_unit,
        )
        > trigger_range
    ):
        return "charge_unit_outside_trigger_range"
    return charge_unit_ineligibility_reason(
        state=state,
        unit_instance_id=target_unit_id,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        charge_state=ChargePhaseState(state.battle_round, context.player_id),
        ignore_already_selected=False,
        allowed_target_ids=_allowed_targets(payload),
    )


def movement_charge_source(
    *,
    state: GameState,
    use: StratagemUseRecord,
    context: StratagemEligibilityContext,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
) -> ChargeInterruption:
    if not isinstance(context.trigger_payload, dict):
        raise GameLifecycleError("Movement Charge source requires a trigger payload.")
    event_id = _identifier(TRIGGER_EVENT, context.trigger_payload.get(TRIGGER_EVENT))
    turn_owner = _identifier("turn player", use.active_player_id)
    expected = fall_back_charge_trigger_payload(
        battle_round=use.battle_round,
        turn_player_id=turn_owner,
        source_event_id=event_id,
        events=events,
        records=records,
    )
    if (
        context.trigger_payload != expected
        or context.trigger_kind is not TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_FALL_BACK
        or context.timing_window_id != f"enemy-fell-back:{event_id}"
        or context.phase is not BattlePhase.MOVEMENT
        or context.player_id == turn_owner
    ):
        raise GameLifecycleError("Movement Charge source window or target pool drift.")
    return ChargeInterruption(
        source_id=use.source_id,
        source_request_id=use.request_id,
        source_result_id=use.result_id,
        unit_instance_id=_identifier("charging unit", use.target_binding.target_unit_instance_id),
        allowed_target_ids=_allowed_targets(expected),
        target_range_inches=state.runtime_ruleset_descriptor().charge_policy.max_declaration_range_inches,
        roll_limit=None,
        suspended_phase=None,
        movement_source_player_id=turn_owner,
        movement_source_event_id=event_id,
    )


def _allowed_targets(payload: dict[str, JsonValue]) -> tuple[str, ...]:
    pool = payload.get(CHARGE_POOL)
    if not isinstance(pool, list) or not pool:
        raise GameLifecycleError("Movement Charge source requires its enemy target pool.")
    ids = tuple(_identifier(CHARGE_POOL, unit_id) for unit_id in pool)
    if ids != tuple(sorted(set(ids))):
        raise GameLifecycleError("Movement Charge enemy target pool is not canonical.")
    return ids
