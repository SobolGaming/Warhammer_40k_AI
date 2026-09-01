from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserves import (
    ReserveOrigin,
    ReserveState,
    ReserveStatePayload,
    ReserveStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies

_INITIAL_RESERVE_ORIGINS = frozenset(
    (
        ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        ReserveOrigin.DEPLOY_ARMIES_OVERFLOW,
        ReserveOrigin.AIRCRAFT_MANDATORY_RESERVE,
    )
)
_INITIAL_RESERVE_SOURCE_EVENT_TYPES = frozenset(
    (
        "aircraft_reserve_declared",
        "prebattle_redeploy_to_strategic_reserves",
        "reserve_unit_declared",
    )
)


def validate_reserve_state_consistency(*, state: GameState) -> None:
    """Validate canonical ownership and physical-state closure for every ReserveState."""
    if not state.reserve_states:
        return
    for reserve_state in state.reserve_states:
        reserve_view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions),
            unit_instance_id=reserve_state.unit_instance_id,
        )
        if reserve_view.unit_instance_id != reserve_state.unit_instance_id:
            raise GameLifecycleError("reserve_states must use canonical rules-unit identity.")
        if reserve_view.owner_player_id != reserve_state.player_id:
            raise GameLifecycleError("reserve_states player_id does not match unit owner.")
        for embarked_unit_id in reserve_state.embarked_unit_instance_ids:
            embarked_view = rules_unit_view_from_armies(
                armies=tuple(state.army_definitions),
                unit_instance_id=embarked_unit_id,
            )
            if embarked_view.owner_player_id != reserve_state.player_id:
                raise GameLifecycleError("reserve_states embarked unit owner drift.")

    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    placed_model_ids = set(battlefield_state.placed_model_ids())
    removed_model_ids = set(battlefield_state.removed_model_ids)
    currently_embarked_model_ids = set(state.embarked_model_ids())
    for reserve_state in state.reserve_states:
        reserve_view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions),
            unit_instance_id=reserve_state.unit_instance_id,
        )
        reserve_model_ids = {model.model_instance_id for model in reserve_view.own_models}
        embarked_views = tuple(
            rules_unit_view_from_armies(
                armies=tuple(state.army_definitions),
                unit_instance_id=embarked_unit_id,
            )
            for embarked_unit_id in reserve_state.embarked_unit_instance_ids
        )
        embarked_model_ids = {
            model.model_instance_id
            for embarked_view in embarked_views
            for model in embarked_view.own_models
        }
        if reserve_state.status is ReserveStatus.IN_RESERVES:
            route_views = (reserve_view, *embarked_views)
            route_model_ids = reserve_model_ids | embarked_model_ids
            unarrived_alive_model_ids = {
                model.model_instance_id
                for route_view in route_views
                for model in route_view.own_models
                if model.is_alive
            }
            unarrived_dead_model_ids = route_model_ids - unarrived_alive_model_ids
            if route_model_ids & placed_model_ids:
                raise GameLifecycleError("unarrived reserve models must not be placed.")
            if unarrived_alive_model_ids & removed_model_ids:
                raise GameLifecycleError("living unarrived reserve models must not be removed.")
            if not unarrived_dead_model_ids <= removed_model_ids:
                raise GameLifecycleError(
                    "destroyed unarrived reserve models must have exact removal state."
                )
        if reserve_state.status is ReserveStatus.ARRIVED:
            alive_model_ids = {
                model.model_instance_id for model in reserve_view.own_models if model.is_alive
            }
            dead_model_ids = reserve_model_ids - alive_model_ids
            if not alive_model_ids <= placed_model_ids | currently_embarked_model_ids:
                raise GameLifecycleError(
                    "living arrived reserve unit models must be placed or embarked."
                )
            if alive_model_ids & removed_model_ids:
                raise GameLifecycleError("living arrived reserve models must not be removed.")
            if not dead_model_ids <= removed_model_ids or dead_model_ids & placed_model_ids:
                raise GameLifecycleError(
                    "destroyed arrived reserve models must have exact removal state."
                )
        if (
            reserve_state.status is ReserveStatus.DESTROYED
            and not (reserve_model_ids | embarked_model_ids) <= removed_model_ids
        ):
            raise GameLifecycleError("destroyed reserve models must be removed.")


def validate_initial_reserve_destruction_policy_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    """Bind initial ReserveState deadline policy to mission and declaration authority."""
    expected_policy = reposition_destruction_policy(
        mission_setup=state.mission_setup,
        destruction_deadline_policy=None,
    )
    initial_states = tuple(
        reserve_state
        for reserve_state in state.reserve_states
        if reserve_state.reserve_origin in _INITIAL_RESERVE_ORIGINS
    )
    if any(
        reserve_state.destruction_deadline_policy != expected_policy
        for reserve_state in initial_states
    ):
        raise GameLifecycleError(
            "Initial ReserveState destruction deadline policy authority drift."
        )

    source_states_by_identity: dict[tuple[str, str], ReserveState] = {}
    for event in event_records:
        if event.event_type not in _INITIAL_RESERVE_SOURCE_EVENT_TYPES:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Initial reserve declaration evidence is malformed.")
        raw_reserve_state = event.payload.get("reserve_state")
        if not isinstance(raw_reserve_state, dict):
            raise GameLifecycleError("Initial reserve declaration evidence is malformed.")
        try:
            source_state = ReserveState.from_payload(cast(ReserveStatePayload, raw_reserve_state))
        except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
            raise GameLifecycleError("Initial reserve declaration evidence is malformed.") from exc
        identity = (source_state.player_id, source_state.unit_instance_id)
        if (
            event.payload.get("game_id") != state.game_id
            or event.payload.get("player_id") != source_state.player_id
            or event.payload.get("unit_instance_id") != source_state.unit_instance_id
            or source_state.reserve_origin not in _INITIAL_RESERVE_ORIGINS
            or source_state.status is not ReserveStatus.IN_RESERVES
            or source_state.destruction_deadline_policy != expected_policy
            or identity in source_states_by_identity
        ):
            raise GameLifecycleError("Initial reserve declaration evidence drift.")
        source_states_by_identity[identity] = source_state

    consumed_source_identities = _initial_source_identities_with_arrival(
        source_states_by_identity=source_states_by_identity,
        event_records=event_records,
    )
    for reserve_state in initial_states:
        identity = (reserve_state.player_id, reserve_state.unit_instance_id)
        recorded_state = source_states_by_identity.get(identity)
        if recorded_state is None or not _initial_reserve_fields_match(
            first=recorded_state,
            second=reserve_state,
        ):
            raise GameLifecycleError("Initial reserve declaration evidence drift.")
        consumed_source_identities.add(identity)
    if consumed_source_identities != set(source_states_by_identity):
        raise GameLifecycleError("Initial reserve declaration source event is orphaned.")


def _initial_source_identities_with_arrival(
    *,
    source_states_by_identity: dict[tuple[str, str], ReserveState],
    event_records: tuple[EventRecord, ...],
) -> set[tuple[str, str]]:
    arrival_request_ids = {
        request_id
        for event in event_records
        if event.event_type == "reinforcement_unit_arrived"
        and isinstance(event.payload, dict)
        and type(request_id := event.payload.get("request_id")) is str
    }
    consumed: set[tuple[str, str]] = set()
    for event in event_records:
        if event.event_type != "decision_requested" or not isinstance(event.payload, dict):
            continue
        if event.payload.get("request_id") not in arrival_request_ids:
            continue
        request_payload = event.payload.get("payload")
        if not isinstance(request_payload, dict):
            continue
        proposal_request = request_payload.get("proposal_request")
        if not isinstance(proposal_request, dict):
            continue
        context = proposal_request.get("context")
        if not isinstance(context, dict):
            continue
        raw_reserve_state = context.get("reserve_state")
        if not isinstance(raw_reserve_state, dict):
            continue
        try:
            reserve_state = ReserveState.from_payload(cast(ReserveStatePayload, raw_reserve_state))
        except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
            raise GameLifecycleError(
                "Initial reserve arrival declaration evidence is malformed."
            ) from exc
        identity = (reserve_state.player_id, reserve_state.unit_instance_id)
        source_state = source_states_by_identity.get(identity)
        if source_state is not None and source_state.to_payload() == reserve_state.to_payload():
            consumed.add(identity)
    return consumed


def _initial_reserve_fields_match(*, first: ReserveState, second: ReserveState) -> bool:
    return (
        first.player_id == second.player_id
        and first.unit_instance_id == second.unit_instance_id
        and first.reserve_origin is second.reserve_origin
        and first.reserve_kind is second.reserve_kind
        and first.source_rule_ids == second.source_rule_ids
        and first.points_contribution == second.points_contribution
        and first.declared_during_step == second.declared_during_step
        and first.entered_reserves_battle_round == second.entered_reserves_battle_round
        and first.entered_reserves_phase == second.entered_reserves_phase
        and first.required_arrival_battle_round == second.required_arrival_battle_round
        and first.required_arrival_phase == second.required_arrival_phase
        and first.required_arrival_source_rule_id == second.required_arrival_source_rule_id
        and first.required_arrival_placement_kind == second.required_arrival_placement_kind
        and first.destruction_deadline_policy == second.destruction_deadline_policy
        and first.embarked_unit_instance_ids == second.embarked_unit_instance_ids
    )
