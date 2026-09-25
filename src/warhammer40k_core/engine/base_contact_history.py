"""Authenticate contact witnesses against accepted movement and physical history."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.base_contact_authority import contact_query_with_peers
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.battlefield_transition_history import (
    authoritative_battlefield_transition_batch_or_none,
)
from warhammer40k_core.engine.charge_model_endpoints import charge_endpoint_query
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_model_authority_history import historical_rules_unit_model_ids
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    physical_model_authority_before_event,
)
from warhammer40k_core.geometry.base_contact import (
    DeemedBaseContact,
    DeemedBaseContactPayload,
    establish_deemed_base_contact,
)
from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
)
from warhammer40k_core.geometry.movement_query_payloads import (
    MovementQueryPayload,
    query_from_payload,
)
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    PathWitnessPayload,
)
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_base_contact_2026_09 import (
    DEEMED_BASE_CONTACT_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


def validate_base_contact_history(
    *,
    state: GameState,
    events: tuple[EventRecord, ...],
    decisions: tuple[DecisionRecord, ...],
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    identities = {
        model.model_instance_id: (army, unit, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if not any(model.geometry.body_parts for _, _, model in identities.values()):
        if any(row.base_contacts for row in state.model_movement_history):
            raise GameLifecycleError("Deemed contact history lacks catalog body geometry.")
        return
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deemed contact history requires battlefield geometry.")
    for index, event in enumerate(events):
        if event.event_type not in {
            "movement_activation_completed",
            "charge_move_completed",
            "catalog_setup_reactive_charge_move_completed",
            "fight_movement_completed",
            "triggered_movement_resolved",
        }:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Deemed contact move payload is invalid.")
        resolution = (
            payload["resolution"] if event.event_type == "fight_movement_completed" else payload
        )
        if event.event_type == "movement_activation_completed" and payload.get(
            "movement_phase_action"
        ) in {"remain_stationary", "ingress", "disembark", "combat_disembark"}:
            continue
        if not isinstance(resolution, dict) or not isinstance(
            resolution.get("path_validation_results"), list
        ):
            raise GameLifecycleError("Deemed contact move path results are absent.")
        results = cast(list[JsonValue], resolution["path_validation_results"])
        if not results:
            continue
        physical = physical_model_authority_before_event(
            state=state,
            event_records=events,
            decision_records=decisions,
            event_index=index,
        )
        geometry: dict[str, Model] = {}
        for row in physical:
            if row.presence not in {"battlefield", "retained_destroyed"}:
                continue
            if row.pose is None:
                raise GameLifecycleError("Deemed contact historical placement is absent.")
            army, unit, model = identities[row.model_instance_id]
            geometry[row.model_instance_id] = geometry_model_for_placement(
                model=model,
                placement=ModelPlacement(
                    army_id=army.army_id,
                    player_id=army.player_id,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=row.pose,
                    split_origin=unit.split_origin,
                ),
            )
        transition = authoritative_battlefield_transition_batch_or_none(event=event)
        if transition is None:
            raise GameLifecycleError("Deemed contact requires accepted physical transitions.")
        final_poses = {row.model_instance_id: row.end_pose for row in transition.displacements}
        for raw in results:
            if not isinstance(raw, dict) or not isinstance(
                raw.get("movement_distance_witness"), dict
            ):
                raise GameLifecycleError(
                    "Deemed contact requires actual movement distance evidence."
                )
            distance = MovementDistanceWitness.from_payload(
                cast(MovementDistanceWitnessPayload, raw["movement_distance_witness"])
            )
            source = geometry[distance.model_id]
            owner, unit, _ = identities[source.model_id]
            enemy_models = tuple(
                m
                for mid, m in sorted(geometry.items())
                if identities[mid][0].player_id != owner.player_id
            )
            friendly_models = tuple(
                replace(m, pose=final_poses.get(mid, m.pose))
                for mid, m in sorted(geometry.items())
                if mid != source.model_id and identities[mid][0].player_id == owner.player_id
            )
            if not any(m.body_parts for m in enemy_models):
                if raw.get("deemed_base_contacts"):
                    raise GameLifecycleError("Deemed contact requires an overhanging enemy.")
                continue
            model_path = next(
                (
                    row.path_witness
                    for row in transition.displacements
                    if row.model_instance_id == source.model_id
                ),
                None,
            )
            if model_path is None:
                recorded_witness = resolution.get("witness")
                if event.event_type == "triggered_movement_resolved":
                    records = tuple(
                        d
                        for d in decisions
                        if d.request.request_id == payload["request_id"]
                        and d.result.result_id == payload["result_id"]
                    )
                    if len(records) != 1 or not isinstance(records[0].result.payload, dict):
                        raise GameLifecycleError(
                            "Deemed contact reactive movement decision is absent."
                        )
                    recorded_witness = records[0].result.payload.get("witness")
                if event.event_type == "fight_movement_completed":
                    from warhammer40k_core.engine.fight_resolution import (
                        fight_movement_proposal_from_payload,
                    )

                    records = tuple(
                        d
                        for d in decisions
                        if d.request.request_id == payload["request_id"]
                        and d.result.result_id == payload["result_id"]
                    )
                    if len(records) != 1:
                        raise GameLifecycleError(
                            "Deemed contact movement decision is absent or duplicated."
                        )
                    proposal = fight_movement_proposal_from_payload(records[0].result.payload)
                    recorded_witness = (
                        None
                        if proposal.witness is None
                        else cast(JsonValue, proposal.witness.to_payload())
                    )
                if not isinstance(recorded_witness, dict):
                    raise GameLifecycleError("Deemed contact actual path witness is absent.")
                model_path = PathWitness.for_paths(
                    (
                        (
                            source.model_id,
                            PathWitness.from_payload(
                                cast(PathWitnessPayload, recorded_witness)
                            ).poses_for_model(source.model_id),
                        ),
                    )
                )
            contacts_raw = raw.get("deemed_base_contacts", [])
            if not isinstance(contacts_raw, list):
                raise GameLifecycleError("Deemed contact witness inventory is invalid.")
            contacts = tuple(
                DeemedBaseContact.from_payload(cast(DeemedBaseContactPayload, c))
                for c in contacts_raw
            )
            if len({c.enemy_model_id for c in contacts}) != len(contacts):
                raise GameLifecycleError("Deemed contact witness inventory is duplicated.")
            if distance.budget is None:
                raise GameLifecycleError("Deemed contact requires the actual movement budget.")
            raw_query = raw.get("base_contact_query")
            if not isinstance(raw_query, dict):
                raise GameLifecycleError("Deemed contact movement query is absent.")
            query = query_from_payload(cast(MovementQueryPayload, raw_query))
            context = query.path_context
            if (
                any(
                    c.source_rule_id != DEEMED_BASE_CONTACT_SOURCE_ID
                    or c.moving_model_id != source.model_id
                    or c.movement_query != query
                    for c in contacts
                )
                or context.moving_model != source
                or context.witness != model_path
                or context.movement_distance_budget_inches != distance.budget.max_distance_inches
                or context.enemy_models != enemy_models
                or context.friendly_models != friendly_models
                or context.battlefield_width_inches != battlefield.battlefield_width_inches
                or context.battlefield_depth_inches != battlefield.battlefield_depth_inches
                or query.terrain_context.terrain_features != battlefield.terrain_features
                or query.terrain_context.terrain
                != tuple(v for f in battlefield.terrain_features for v in f.terrain_volumes())
                or context.terrain
                or query.terrain_context.witness != model_path
                or query.terrain_context.terrain_movement_policy
                != state.runtime_ruleset_descriptor().terrain_movement_policy
                or context.validate().movement_distance_witness != distance
            ):
                raise GameLifecycleError("Deemed contact physical movement authority drifted.")
            ruleset = state.runtime_ruleset_descriptor()
            mode = MovementMode(cast(str, resolution["movement_mode"]))
            if event.event_type == "fight_movement_completed":
                from warhammer40k_core.engine.base_contact_fight_history import (
                    validate_fight_contact_permissions,
                )

                validate_fight_contact_permissions(
                    state=state, unit=unit, physical=physical, query=query, mode=mode
                )
            from warhammer40k_core.engine.base_contact_fight_history import (
                validate_triggered_contact_permissions,
            )

            is_surge = False
            if event.event_type == "triggered_movement_resolved":
                is_surge = validate_triggered_contact_permissions(
                    state=state,
                    unit=unit,
                    physical=physical,
                    query=query,
                    payload=payload,
                    events=events,
                )
            policy = ruleset.movement_policy.policy_for_mode(mode)
            if (
                context.may_end_in_enemy_engagement
                != (policy.may_end_in_enemy_engagement or is_surge)
                or context.enemy_engagement_horizontal_inches
                != ruleset.engagement_policy.horizontal_inches
                or context.enemy_engagement_vertical_inches
                != ruleset.engagement_policy.vertical_inches
                or context.sample_interval_inches != 0.5
                or query.terrain_context.sample_interval_inches != 0.5
            ):
                raise GameLifecycleError("Deemed contact movement policy drifted.")
            source_ids = historical_rules_unit_model_ids(
                state=state,
                event_records=events,
                unit_instance_id=cast(str, payload["unit_instance_id"]),
            )
            alive_ids = {p.model_instance_id for p in physical if p.presence == "battlefield"}
            peers = tuple(m for m in friendly_models if m.model_id in source_ids & alive_ids)
            if event.event_type in {
                "charge_move_completed",
                "catalog_setup_reactive_charge_move_completed",
            }:
                from warhammer40k_core.engine.base_contact_charge_history import (
                    validate_charge_contact_permissions,
                )

                if runtime_content_bundle is None:
                    raise GameLifecycleError("Charge contact requires loaded runtime authority.")
                validate_charge_contact_permissions(
                    state=state,
                    unit=unit,
                    physical=physical,
                    query=query,
                    payload=payload,
                    events=events,
                    decisions=decisions,
                    event_index=index,
                    runtime_content_bundle=runtime_content_bundle,
                )
                endpoint = payload["endpoint_witness"]
                if not isinstance(endpoint, dict) or not isinstance(
                    endpoint["selected_target_unit_instance_ids"], list
                ):
                    raise GameLifecycleError("Deemed contact Charge target inventory is absent.")
                targets = {
                    target: tuple(
                        m
                        for m in enemy_models
                        if m.model_id
                        in historical_rules_unit_model_ids(
                            state=state, event_records=events, unit_instance_id=target
                        )
                    )
                    for target in cast(list[str], endpoint["selected_target_unit_instance_ids"])
                }
                target_model_ids = {m.model_id for group in targets.values() for m in group}
                non_targets = tuple(
                    (m,) for m in enemy_models if m.model_id not in target_model_ids
                )
                expected_query = charge_endpoint_query(
                    path_context=context,
                    terrain_context=query.terrain_context,
                    peers=peers,
                    targets=targets,
                    non_targets=non_targets,
                    ruleset=ruleset,
                )
                # Union grouping of forbidden enemy goals does not change its semantics.
                actual_forbidden = tuple(m for g in query.forbidden_goals for m in g.models)
                expected_forbidden = tuple(
                    m for g in expected_query.forbidden_goals for m in g.models
                )
                if actual_forbidden != expected_forbidden:
                    raise GameLifecycleError("Deemed contact forbidden Charge targets drifted.")
                expected_query = replace(expected_query, forbidden_goals=query.forbidden_goals)
            else:
                expected_query = contact_query_with_peers(
                    path_context=context,
                    terrain_context=query.terrain_context,
                    peers=peers,
                    ruleset=ruleset,
                )
            if event.event_type == "fight_movement_completed" or is_surge:
                from warhammer40k_core.engine.base_contact_move_constraints import (
                    contact_move_constraints,
                )
                from warhammer40k_core.engine.fight_resolution import (
                    fight_movement_proposal_from_payload,
                )

                def target_group(
                    uid: str, models: tuple[Model, ...] = enemy_models
                ) -> tuple[Model, ...]:
                    ids = historical_rules_unit_model_ids(
                        state=state, event_records=events, unit_instance_id=uid
                    )
                    return tuple(m for m in models if m.model_id in ids)

                groups = tuple(
                    dict.fromkeys(
                        group
                        for army in state.army_definitions
                        if army.player_id != owner.player_id
                        for u in army.units
                        for group in (target_group(u.unit_instance_id),)
                        if group
                    )
                )
                selected_ids: tuple[str, ...]
                consolidation = None
                if is_surge:
                    selected_ids = (cast(str, payload["surge_target_unit_instance_id"]),)
                else:
                    records = tuple(
                        d
                        for d in decisions
                        if d.request.request_id == payload["request_id"]
                        and d.result.result_id == payload["result_id"]
                    )
                    if len(records) != 1:
                        raise GameLifecycleError("Contact Fight target decision is absent.")
                    move = fight_movement_proposal_from_payload(records[0].result.payload)
                    selected_ids = move.target_unit_instance_ids
                    consolidation = move.consolidation_mode
                expected_query = contact_move_constraints(
                    expected_query,
                    ruleset=ruleset,
                    enemy_groups=groups,
                    selected_groups=tuple(target_group(uid) for uid in selected_ids),
                    mode=mode,
                    consolidation_mode=consolidation,
                    surge=is_surge,
                )
            if query != expected_query:
                raise GameLifecycleError("Deemed contact endpoint constraints drifted.")
            expected = tuple(
                contact.enemy_model_id
                for enemy in enemy_models
                if enemy.body_parts
                for contact in (
                    establish_deemed_base_contact(
                        query=query,
                        enemy_model_id=enemy.model_id,
                        source_rule_id=DEEMED_BASE_CONTACT_SOURCE_ID,
                    ),
                )
                if contact is not None
            )
            if tuple(c.enemy_model_id for c in contacts) != expected:
                raise GameLifecycleError(
                    "Deemed contact witness inventory differs from the accepted move."
                )
