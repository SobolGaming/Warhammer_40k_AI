"""The existing Stratagem provider supplies restrictions to the ordinary Charge owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.charge_budget_value import ChargeRollLimit
from warhammer40k_core.engine.charge_phase_state import ChargeInterruption, ChargePhaseState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import (
        StratagemDefinition,
        StratagemEligibilityContext,
        StratagemTargetBinding,
        StratagemUseRecord,
    )


def heroic_charge_source(
    *, state: GameState, use: StratagemUseRecord, parent: ChargePhaseState
) -> ChargeInterruption:
    from warhammer40k_core.engine.stratagems_model import (
        HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
        HEROIC_INTERVENTION_MODE_INTO_THE_FRAY,
        HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND,
    )
    from warhammer40k_core.engine.stratagems_selection import _effect_selection_string_or_none

    mode = _effect_selection_string_or_none(
        effect_selection=use.effect_selection, key=HEROIC_INTERVENTION_MODE_CONTEXT_KEY
    )
    if mode not in {
        HEROIC_INTERVENTION_MODE_INTO_THE_FRAY,
        HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND,
    }:
        raise GameLifecycleError("Heroic Intervention requires an explicit mode before rolling.")
    unit_id = use.target_binding.target_unit_instance_id
    if unit_id is None:
        raise GameLifecycleError("Heroic Intervention requires its targeted unit.")
    unit_id = rules_unit_view_by_id(state=state, unit_instance_id=unit_id).unit_instance_id
    fray = mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
    charged = tuple(
        sorted(
            unit_id
            for unit_id, targets in parent.declared_target_unit_instance_ids_by_unit.items()
            if targets
        )
    )
    return ChargeInterruption(
        source_id=use.source_id,
        source_request_id=use.request_id,
        source_result_id=use.result_id,
        unit_instance_id=unit_id,
        allowed_target_ids=None if fray else charged,
        target_range_inches=6.0 if fray else 12.0,
        roll_limit=ChargeRollLimit(use.source_id, 6) if fray else None,
        suspended_phase=parent,
    )


def _apply_heroic_intervention_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ability_index: AbilityCatalogIndex,
) -> None:
    parent = state.charge_phase_state
    if parent is None:
        raise GameLifecycleError(
            "Heroic Intervention requires completed ordinary Charge authority."
        )
    source = heroic_charge_source(state=state, use=use_record, parent=parent)
    state.replace_charge_phase_state(
        ChargePhaseState(
            battle_round=state.battle_round,
            active_player_id=use_record.player_id,
            interruption=source,
        )
    )
    from warhammer40k_core.engine.active_player_scopes import charge_scope, push_scope

    scope = charge_scope(state)
    if scope is None:
        raise GameLifecycleError("Charge interruption failed to create its active-player scope.")
    push_scope(state, scope)
    decisions.event_log.append(
        "interrupted_charge_started",
        {
            "player_id": use_record.player_id,
            "source": source.to_payload(),
        },
    )


__all__ = ("_apply_heroic_intervention_handler",)


def heroic_charge_target_distances(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    mode: str,
    maximum_distance_inches: float,
) -> dict[str, float]:
    from warhammer40k_core.engine.charge_targets import charge_target_candidates
    from warhammer40k_core.engine.stratagems_model import (
        HEROIC_INTERVENTION_MODE_INTO_THE_FRAY,
        HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND,
    )

    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if view.owner_player_id != player_id:
        raise GameLifecycleError("Heroic Charge source owner drift.")
    if mode not in {
        HEROIC_INTERVENTION_MODE_INTO_THE_FRAY,
        HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND,
    }:
        raise GameLifecycleError("Heroic Charge source mode is invalid.")
    phase = state.charge_phase_state
    parent = (
        phase if phase is None or phase.interruption is None else phase.interruption.suspended_phase
    )
    charged = (
        ()
        if parent is None
        else tuple(
            unit_id
            for unit_id, targets in parent.declared_target_unit_instance_ids_by_unit.items()
            if targets
        )
    )
    return {
        candidate.target_unit_instance_id: candidate.closest_distance_inches
        for candidate in charge_target_candidates(
            state=state,
            unit_instance_id=view.unit_instance_id,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
        if candidate.is_legal
        and candidate.closest_distance_inches <= maximum_distance_inches
        and (
            candidate.closest_distance_inches <= 6
            if mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
            else candidate.target_unit_instance_id in charged
        )
    }
