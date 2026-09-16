"""Authenticate completed Surge target and optimality proofs against event-time geometry."""

from __future__ import annotations

from dataclasses import replace
from math import isclose
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_model_authority_history import historical_rules_unit_model_ids
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.surge_choices import selected_surge_target
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementDescriptorPayload,
    is_triggered_movement_proposal_request,
)
from warhammer40k_core.geometry.movement_reachability import MovementGoal
from warhammer40k_core.geometry.pose import Pose, PosePayload
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_surge_2026_09 import (
    SURGE_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def validate_surge_history(*, state: GameState, decisions: DecisionController) -> None:
    from warhammer40k_core.engine.surge_authority import (
        validate_surge_selection_chain,
        validate_surge_trigger_occurrence,
    )

    events = decisions.event_log.records
    identities = {
        model.model_instance_id: (army, unit, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    ruleset = state.runtime_ruleset_descriptor()
    for index, event in enumerate(events):
        payload = event.payload
        if (
            event.event_type != "triggered_movement_resolved"
            or not isinstance(payload, dict)
            or payload.get("triggered_movement_kind") != "surge"
        ):
            continue
        matches = tuple(
            record
            for record in decisions.records
            if record.request.request_id == payload.get("request_id")
            and record.result.result_id == payload.get("result_id")
        )
        if len(matches) != 1:
            raise GameLifecycleError("Surge completion lost its movement decision.")
        record = matches[0]
        context = (
            MovementProposalRequest.from_decision_request_payload(record.request.payload).context
            if is_triggered_movement_proposal_request(record.request)
            else record.request.payload
        )
        if not isinstance(context, dict) or not isinstance(context.get("descriptor"), dict):
            raise GameLifecycleError("Surge completion lost its descriptor.")
        descriptor = TriggeredMovementDescriptor.from_payload(
            cast(TriggeredMovementDescriptorPayload, context["descriptor"])
        )
        if is_triggered_movement_proposal_request(record.request):
            validate_surge_selection_chain(decisions, context, descriptor, request=record.request)
        if (
            payload.get("source_rule_id") != descriptor.source_rule_id
            or payload.get("trigger_timing") != descriptor.trigger_timing.to_payload()
        ):
            raise GameLifecycleError("Surge completion granting source drifted.")
        validate_surge_trigger_occurrence(
            events=events[:index],
            descriptor=descriptor,
            battle_round=cast(int, payload["battle_round"]),
            turn_player_id=cast(str, payload["active_player_id"]),
        )
        selected = (
            context
            if is_triggered_movement_proposal_request(record.request)
            else record.result.payload
        )
        target = selected_surge_target(selected, descriptor)
        source = payload.get("unit_instance_id")
        if (
            not isinstance(source, str)
            or target is None
            or payload.get("surge_target_unit_instance_id") != target
        ):
            raise GameLifecycleError("Surge completion target commitment drifted.")
        physical = physical_model_authority_before_event(
            state=state,
            event_records=events,
            decision_records=decisions.records,
            event_index=index,
        )
        geometry: dict[str, Model] = {}
        living: set[str] = set()
        for physical_row in physical:
            if physical_row.presence not in {"battlefield", "retained_destroyed"}:
                continue
            if physical_row.pose is None or physical_row.model_instance_id not in identities:
                raise GameLifecycleError("Surge historical geometry is incomplete.")
            army, unit, model = identities[physical_row.model_instance_id]
            geometry[model.model_instance_id] = geometry_model_for_placement(
                model=model,
                placement=ModelPlacement(
                    army_id=army.army_id,
                    player_id=army.player_id,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=physical_row.pose,
                    split_origin=unit.split_origin,
                ),
            )
            if physical_row.presence == "battlefield":
                living.add(model.model_instance_id)
        source_ids = (
            historical_rules_unit_model_ids(
                state=state, event_records=events, unit_instance_id=source
            )
            & living
        )
        target_ids = (
            historical_rules_unit_model_ids(
                state=state, event_records=events, unit_instance_id=target
            )
            & geometry.keys()
        )
        targets = tuple(geometry[key] for key in sorted(target_ids))
        all_source_ids = (
            historical_rules_unit_model_ids(
                state=state, event_records=events, unit_instance_id=source
            )
            & geometry.keys()
        )
        source_owners = {identities[key][0].player_id for key in all_source_ids}
        if len(source_owners) != 1:
            raise GameLifecycleError("Surge historical source ownership drifted.")
        source_owner = next(iter(source_owners))
        can_fly = any("FLY" in identities[key][2].keywords for key in source_ids)
        enemies = tuple(
            model for key, model in geometry.items() if identities[key][0].player_id != source_owner
        )
        eligible_enemies = tuple(
            enemy
            for enemy in enemies
            if can_fly or "AIRCRAFT" not in identities[enemy.model_id][2].keywords
        )
        if (
            not eligible_enemies
            or not targets
            or any(identities[key][0].player_id == source_owner for key in target_ids)
        ):
            raise GameLifecycleError("Surge historical target ownership drifted.")
        closest = min(
            geometry[key].range_to(enemy) for key in all_source_ids for enemy in eligible_enemies
        )
        selected_distance = min(
            geometry[key].range_to(enemy) for key in all_source_ids for enemy in targets
        )
        if not isclose(selected_distance, closest, rel_tol=0.0, abs_tol=1e-9):
            raise GameLifecycleError("Surge historical target was not closest.")
        rows = payload.get("surge_model_endpoints")
        movements = payload.get("model_movements")
        if not targets or not isinstance(rows, list) or not isinstance(movements, list):
            raise GameLifecycleError("Surge completion requires physical endpoint evidence.")
        by_model: dict[str, dict[str, JsonValue]] = {}
        for movement in movements:
            if not isinstance(movement, dict) or not isinstance(
                movement.get("model_instance_id"), str
            ):
                raise GameLifecycleError("Surge movement inventory is malformed.")
            by_model[cast(str, movement["model_instance_id"])] = movement
        if frozenset(by_model) != source_ids or len(rows) != len(source_ids):
            raise GameLifecycleError("Surge living model endpoint inventory drifted.")
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("model_instance_id"), str):
                raise GameLifecycleError("Surge endpoint proof is malformed.")
            model_id = cast(str, row["model_instance_id"])
            if model_id not in source_ids or model_id in seen:
                raise GameLifecycleError("Surge endpoint proof inventory drifted.")
            seen.add(model_id)
            start = geometry[model_id]
            raw_end = by_model[model_id].get("end_pose")
            if (
                not isinstance(raw_end, dict)
                or by_model[model_id].get("start_pose") != start.pose.to_payload()
            ):
                raise GameLifecycleError("Surge historical path geometry drifted.")
            end = replace(start, pose=Pose.from_payload(cast(PosePayload, raw_end)))
            if any(
                end.is_within_engagement_range(
                    enemy,
                    horizontal_inches=ruleset.engagement_policy.horizontal_inches,
                    vertical_inches=ruleset.engagement_policy.vertical_inches,
                )
                for enemy in enemies
                if enemy.model_id not in target_ids
            ):
                raise GameLifecycleError("Surge historical endpoint engages another enemy.")
            goal = MovementGoal(
                models=targets,
                horizontal_inches=ruleset.engagement_policy.horizontal_inches,
                vertical_inches=ruleset.engagement_policy.vertical_inches,
            )
            distance = min(end.range_to(enemy) for enemy in targets)
            if (
                row.get("source_rule_id") != SURGE_SOURCE_ID
                or row.get("component_unit_instance_id") != identities[model_id][1].unit_instance_id
                or row.get("target_unit_instance_id") != target
                or row.get("distance_before_inches")
                != min(start.range_to(enemy) for enemy in targets)
                or row.get("distance_after_inches") != distance
                or row.get("alternative_witness") is not None
            ):
                raise GameLifecycleError("Surge historical endpoint evidence drifted.")
            if goal.contains(end):
                if (
                    row.get("engagement_status") != "satisfied"
                    or row.get("approach_status") != "not_required"
                ):
                    raise GameLifecycleError("Surge engagement proof drifted.")
            else:
                budget = descriptor.max_distance_inches
                lower = max(
                    0.0,
                    MovementGoal(models=targets, range_inches=0.0).distance_lower_bound(start)
                    - budget,
                )
                if (
                    row.get("engagement_status") != "unreachable"
                    or goal.distance_lower_bound(start) <= budget + 1e-8
                    or row.get("approach_status") != "optimal_bound"
                    or row.get("distance_lower_bound_inches") != lower
                    or distance > lower + 1e-8
                ):
                    raise GameLifecycleError("Surge maximum-approach proof drifted.")
