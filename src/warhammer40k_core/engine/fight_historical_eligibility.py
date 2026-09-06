from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import (
    FightEligibilityKind,
    FightOrderingBandKind,
    FightPolicyDescriptor,
)
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.fight_model_authority_history import (
    historical_rules_unit_model_ids,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightEligibilityContext,
    FightPhaseState,
    FightPhaseStatePayload,
)
from warhammer40k_core.engine.fights_first import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FightsFirstRegistry,
    FightsFirstRegistryPayload,
)
from warhammer40k_core.engine.forced_fight_authority import forced_fight_selecting_player_id
from warhammer40k_core.engine.forced_fight_context import ForcedFightActivationContext
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    geometry_models_are_physically_engaged,
)
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    PhysicalModelAuthority,
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_identity_history_contains,
    rules_unit_views_from_armies,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel


@dataclass(frozen=True, slots=True)
class _HistoricalGeometry:
    owner_player_id: str
    geometry_model: GeometryModel


def forced_fight_eligibility_contexts_before_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    battle_round: int,
    context: ForcedFightActivationContext,
    prior_selections: tuple[FightActivationSelection, ...],
    policy: FightPolicyDescriptor,
) -> tuple[FightEligibilityContext, ...]:
    """Rebuild one forced-Fight request from event-bound physical authority."""

    selecting_player_id = forced_fight_selecting_player_id(
        state=state,
        source_unit_instance_id=context.source_unit_instance_id,
        eligible_unit_instance_ids=context.eligible_unit_instance_ids,
    )
    if context.selecting_player_id != selecting_player_id:
        raise GameLifecycleError(
            "Forced Fight historical selecting player differs from canonical owner."
        )
    physical_rows = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=event_index,
    )
    historical_geometry_by_model_id = _historical_geometry_by_model_id(
        state=state,
        physical_rows=physical_rows,
    )
    enemy_models = tuple(
        row.geometry_model
        for row in historical_geometry_by_model_id.values()
        if row.owner_player_id != selecting_player_id
    )
    prior_unit_ids = tuple(selection.unit_instance_id for selection in prior_selections)
    suspended = forced_fight_suspended_state_before_event(
        event_records=event_records, event_index=event_index, context=context
    )
    engaged_at_start = (
        context.eligible_unit_instance_ids
        if suspended is None
        else suspended.fight_order_state.engaged_at_fight_step_start_unit_ids
    )
    fights_first_registry = forced_fight_registry_before_event(
        event_records=event_records,
        event_index=event_index,
        context=context,
        battle_round=battle_round,
    )
    contexts: list[FightEligibilityContext] = []
    for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        unit_id = rules_unit.unit_instance_id
        if rules_unit.owner_player_id != selecting_player_id:
            continue
        if not rules_unit_identity_history_contains(
            state=state,
            identity_ids=context.eligible_unit_instance_ids,
            unit_instance_id=unit_id,
        ):
            continue
        if rules_unit_identity_history_contains(
            state=state,
            identity_ids=prior_unit_ids,
            unit_instance_id=unit_id,
        ):
            continue
        lineage_model_ids = historical_rules_unit_model_ids(
            state=state,
            event_records=event_records,
            unit_instance_id=unit_id,
        )
        unit_models = tuple(
            historical_geometry_by_model_id[model_id].geometry_model
            for model_id in sorted(lineage_model_ids)
            if model_id in historical_geometry_by_model_id
        )
        if not unit_models:
            continue
        currently_engaged = geometry_models_are_physically_engaged(
            first_models=unit_models,
            second_models=enemy_models,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
        reasons = tuple(
            reason
            for reason, applies in (
                (
                    FightEligibilityKind.CHARGED_THIS_TURN,
                    fights_first_registry.has_unit_lineage(
                        state=state,
                        unit_instance_id=unit_id,
                        effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
                    ),
                ),
                (
                    FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,
                    rules_unit_identity_history_contains(
                        state=state, identity_ids=engaged_at_start, unit_instance_id=unit_id
                    ),
                ),
                (FightEligibilityKind.CURRENTLY_ENGAGED, currently_engaged),
            )
            if applies and reason in policy.eligibility_kinds
        )
        reasons = (*reasons, FightEligibilityKind.FORCED_ACTIVATION)
        contexts.append(
            FightEligibilityContext(
                player_id=selecting_player_id,
                battle_round=battle_round,
                unit_instance_id=unit_id,
                ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
                eligibility_reasons=reasons,
                closest_enemy_distance_inches=_closest_enemy_distance_inches(
                    unit_models=unit_models,
                    enemy_models=enemy_models,
                ),
                pass_distance_inches=policy.eligible_pass_distance_inches,
            )
        )
    return tuple(sorted(contexts, key=lambda value: value.unit_instance_id))


def forced_fight_suspended_state_before_event(
    *,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    context: ForcedFightActivationContext,
) -> FightPhaseState | None:
    if context.source_phase.value != "fight":
        return None
    starts = tuple(
        event
        for event in event_records[:event_index]
        if event.event_type == "forced_fight_activation_queue_started"
        and isinstance(event.payload, dict)
        and event.payload.get("forced_activation_context") == context.to_payload()
    )
    if len(starts) != 1 or not isinstance(starts[0].payload, dict):
        raise GameLifecycleError("Consolidation eligibility requires its preceding queue boundary.")
    payload = starts[0].payload.get("suspended_state")
    if not isinstance(payload, dict):
        raise GameLifecycleError("Consolidation eligibility requires the ordinary Fight snapshot.")
    suspended = FightPhaseState.from_payload(cast(FightPhaseStatePayload, payload))
    if (
        starts[0].payload.get("battle_round") != suspended.battle_round
        or starts[0].payload.get("active_player_id") != suspended.active_player_id
        or starts[0].payload.get("phase") != context.source_phase.value
    ):
        raise GameLifecycleError("Consolidation historical Fight time context drift.")
    return suspended


def forced_fight_registry_before_event(
    *,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    context: ForcedFightActivationContext,
    battle_round: int,
) -> FightsFirstRegistry:
    """Use the registry frozen by the original Fight owner, never today's effects."""
    suspended = forced_fight_suspended_state_before_event(
        event_records=event_records, event_index=event_index, context=context
    )
    if suspended is not None:
        if suspended.battle_round != battle_round:
            raise GameLifecycleError("Forced Fight historical registry round drift.")
        return suspended.fight_order_state.fights_first_registry
    starts = tuple(
        event
        for event in event_records[:event_index]
        if event.event_type == "forced_fight_activation_queue_started"
        and isinstance(event.payload, dict)
        and event.payload.get("forced_activation_context") == context.to_payload()
    )
    if len(starts) != 1 or not isinstance(starts[0].payload, dict):
        raise GameLifecycleError("Forced Fight registry requires one exact queue-start event.")
    payload = starts[0].payload
    if payload.get("battle_round") != battle_round:
        raise GameLifecycleError("Forced Fight historical registry round drift.")
    registry_payload = payload.get("fights_first_registry")
    if not isinstance(registry_payload, dict):
        raise GameLifecycleError("Forced Fight registry snapshot is missing or malformed.")
    try:
        return FightsFirstRegistry.from_payload(cast(FightsFirstRegistryPayload, registry_payload))
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Forced Fight registry snapshot is malformed.") from exc


def _historical_geometry_by_model_id(
    *,
    state: GameState,
    physical_rows: tuple[PhysicalModelAuthority, ...],
) -> dict[str, _HistoricalGeometry]:
    model_authority = {
        model.model_instance_id: (army.army_id, army.player_id, unit.unit_instance_id, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    geometry_by_id: dict[str, _HistoricalGeometry] = {}
    for row in physical_rows:
        if row.presence not in {"battlefield", "retained_destroyed"}:
            continue
        identity = model_authority.get(row.model_instance_id)
        if identity is None or row.pose is None:
            raise GameLifecycleError("Historical Fight physical authority is incomplete.")
        army_id, player_id, unit_instance_id, model = identity
        try:
            geometry_model = geometry_model_for_placement(
                model=model,
                placement=ModelPlacement(
                    army_id=army_id,
                    player_id=player_id,
                    unit_instance_id=unit_instance_id,
                    model_instance_id=row.model_instance_id,
                    pose=row.pose,
                ),
            )
        except PlacementError as exc:
            raise GameLifecycleError("Historical Fight physical geometry is invalid.") from exc
        geometry_by_id[row.model_instance_id] = _HistoricalGeometry(
            owner_player_id=player_id,
            geometry_model=geometry_model,
        )
    return geometry_by_id


def _closest_enemy_distance_inches(
    *,
    unit_models: tuple[GeometryModel, ...],
    enemy_models: tuple[GeometryModel, ...],
) -> float | None:
    distances = tuple(
        unit_model.range_to(enemy_model)
        for unit_model in unit_models
        for enemy_model in enemy_models
    )
    return None if not distances else min(distances)


__all__ = ("forced_fight_eligibility_contexts_before_event",)
