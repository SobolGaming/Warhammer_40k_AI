"""Engine-owned cargo and battlefield mutation shared by all embark occasions."""

from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transports import EmbarkResolution, apply_embark_to_battlefield


def apply_embark_mutation(
    *,
    state: GameState,
    decisions: DecisionController,
    embark: EmbarkResolution,
    result: DecisionResult,
) -> None:
    if state.current_battle_phase is None:
        raise GameLifecycleError("Embark requires a current battle phase.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Embark requires battlefield_state.")
    if embark.updated_cargo_state is None:
        raise GameLifecycleError("Valid EmbarkResolution requires updated cargo state.")
    if embark.transition_batch is None:
        raise GameLifecycleError("Valid EmbarkResolution requires a transition batch.")
    state.replace_battlefield_state(
        apply_embark_to_battlefield(
            battlefield_state=battlefield_state,
            embark=embark,
        )
    )
    state.replace_transport_cargo_state(embark.updated_cargo_state)
    embarked_rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=embark.selection.unit_instance_id,
    )
    departed_component_ids = tuple(
        sorted(
            {
                embarked_rules_unit.component_unit_id_for_model(removal.model_instance_id)
                for removal in embark.transition_batch.removals
            }
        )
    )
    departure_ids_before = tuple(
        value.departure_id for value in state.primary_battlefield_departure_states
    )
    record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=embarked_rules_unit.unit_instance_id,
        affected_component_unit_instance_ids=departed_component_ids,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=tuple(
            removal.model_instance_id for removal in embark.transition_batch.removals
        ),
        removal_kind=BattlefieldRemovalKind.EMBARK,
        occurrence_id=result.result_id,
        source_id=result.result_id,
    )
    decisions.event_log.append(
        "unit_embarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": state.current_battle_phase.value,
            "unit_instance_id": embark.selection.unit_instance_id,
            "transport_unit_instance_id": embark.selection.transport_unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_embarked",
            "updated_cargo_state": validate_json_value(embark.updated_cargo_state.to_payload()),
            "transition_batch": validate_json_value(embark.transition_batch.to_payload()),
            "embark_selection": validate_json_value(embark.selection.to_payload()),
        },
    )
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=departure_ids_before,
    )
