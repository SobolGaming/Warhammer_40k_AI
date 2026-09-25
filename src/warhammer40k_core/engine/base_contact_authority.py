"""Source-authorized deemed contact for accepted, witnessed engine movement."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.game_state import GameState

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.base_contact import (
    BaseContactUnresolved,
    DeemedBaseContact,
    establish_deemed_base_contact,
)
from warhammer40k_core.geometry.movement_reachability import MovementGoal, MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import (
    PathConstraintViolation,
    PathValidationContext,
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityContext,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_base_contact_2026_09 import (
    DEEMED_BASE_CONTACT_SOURCE_ID,
)


def contacts_for_validated_move(
    *,
    path_context: PathValidationContext,
    terrain_context: TerrainPathLegalityContext,
    path_result: PathValidationResult,
    terrain_result: TerrainPathLegalityResult,
    query: MovementReachabilityQuery | None = None,
) -> PathValidationResult:
    if not path_result.is_valid or not terrain_result.is_valid:
        return path_result
    enemies = tuple(m for m in path_context.enemy_models if m.body_parts)
    if not enemies:
        return path_result
    if query is None:
        query = MovementReachabilityQuery(
            path_context=path_context,
            terrain_context=terrain_context,
            goal=MovementGoal(models=enemies, range_inches=0.0),
        )
    contacts: list[DeemedBaseContact] = []
    for enemy in enemies:
        try:
            contact = establish_deemed_base_contact(
                query=query,
                enemy_model_id=enemy.model_id,
                source_rule_id=DEEMED_BASE_CONTACT_SOURCE_ID,
            )
        except BaseContactUnresolved as exc:
            return replace(
                path_result,
                violations=(
                    PathConstraintViolation(
                        violation_code="deemed_base_contact_unresolved",
                        message=str(exc),
                        model_id=path_context.moving_model.model_id,
                        blocker_id=enemy.model_id,
                    ),
                ),
            )
        if contact is not None:
            contacts.append(contact)
    return replace(path_result, deemed_base_contacts=tuple(contacts), base_contact_query=query)


def current_deemed_base_contacts(state: GameState | None) -> tuple[DeemedBaseContact, ...]:
    if state is None:
        return ()
    if any(
        row.battle_round == state.battle_round and row.active_player_id == state.active_player_id
        for row in state.end_turn_cleanup_states
    ):
        return ()
    from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield

    return tuple(
        contact
        for row in state.model_movement_history
        if row.battle_round == state.battle_round and row.turn_player_id == state.active_player_id
        for raw in row.base_contacts
        for contact in (DeemedBaseContact.from_payload(raw),)
        if all(
            model_is_present_on_battlefield(state=state, model_instance_id=model_id)
            for model_id in contact.pair
        )
    )


def engine_models_in_base_contact(
    first: Model,
    second: Model,
    *,
    state: GameState | None,
    epsilon: float = 1e-9,
) -> bool:
    if first.range_to(second) <= epsilon:
        return True
    if state is None:
        return False
    for contact in current_deemed_base_contacts(state):
        if contact.pair != frozenset((first.model_id, second.model_id)):
            continue
        if contact.source_rule_id != DEEMED_BASE_CONTACT_SOURCE_ID:
            raise GameLifecycleError("Deemed contact has an unauthorized source.")
        query = current_contact_query(state=state, contact=contact)
        if contact.continues(first, second, current_query=query):
            return True
    return False


def current_contact_query(
    *, state: GameState, contact: DeemedBaseContact
) -> MovementReachabilityQuery:
    """Refresh every physical dependency before checking a continuing condition."""
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement

    scenario = battlefield_scenario_for_state(state=state)
    geometry = {
        placement.model_instance_id: geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement), placement=placement
        )
        for army in scenario.battlefield_state.placed_armies
        for unit in army.unit_placements
        for placement in unit.model_placements
        if scenario.model_is_present_on_battlefield(placement.model_instance_id)
    }
    owners = {
        model.model_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    original = contact.movement_query
    source = geometry[contact.moving_model_id]
    owner = owners[source.model_id]
    witness = PathWitness.for_paths(((source.model_id, (source.pose, source.pose)),))

    def refreshed(models: tuple[Model, ...]) -> tuple[Model, ...]:
        return tuple(geometry[m.model_id] for m in models if m.model_id in geometry)

    return replace(
        original,
        path_context=replace(
            original.path_context,
            moving_model=source,
            witness=witness,
            friendly_models=tuple(
                m
                for mid, m in sorted(geometry.items())
                if mid != source.model_id and owners[mid] == owner
            ),
            enemy_models=tuple(m for mid, m in sorted(geometry.items()) if owners[mid] != owner),
        ),
        terrain_context=replace(
            original.terrain_context,
            moving_model=source,
            witness=witness,
            terrain_features=scenario.battlefield_state.terrain_features,
            terrain=tuple(
                v for f in scenario.battlefield_state.terrain_features for v in f.terrain_volumes()
            ),
        ),
        goal=MovementGoal(models=(geometry[contact.enemy_model_id],), range_inches=0.0),
        required_goals=tuple(
            replace(g, models=refreshed(g.models))
            for g in original.required_goals
            if not g.models or refreshed(g.models)
        ),
        required_if_reachable_goals=tuple(
            replace(g, models=refreshed(g.models))
            for g in original.required_if_reachable_goals
            if not g.models or refreshed(g.models)
        ),
        forbidden_goals=tuple(
            replace(g, models=refreshed(g.models))
            for g in original.forbidden_goals
            if not g.models or refreshed(g.models)
        ),
        coherent_models=refreshed(original.coherent_models),
        closer_target_groups=tuple(
            refreshed(g) for g in original.closer_target_groups if refreshed(g)
        ),
    )


def contact_query_for_move(
    *,
    path_context: PathValidationContext,
    terrain_context: TerrainPathLegalityContext,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    ruleset: RulesetDescriptor,
    fight_proposal: FightMovementProposal | None = None,
    surge_target_id: str | None = None,
) -> MovementReachabilityQuery | None:
    """Use the whole attached rules unit and its proposed endpoints for coherency."""
    from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies

    if not any(m.body_parts for m in path_context.enemy_models):
        return None
    unit = rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_instance_id)
    peer_ids = {m.model_instance_id for m in unit.own_models if m.is_alive}
    peers = tuple(m for m in path_context.friendly_models if m.model_id in peer_ids)
    query = contact_query_with_peers(
        path_context=path_context, terrain_context=terrain_context, peers=peers, ruleset=ruleset
    )
    if fight_proposal is None and surge_target_id is None:
        return query
    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.base_contact_move_constraints import contact_move_constraints

    groups: dict[str, list[Model]] = {}
    enemy_by_id = {m.model_id: m for m in path_context.enemy_models}
    for army in scenario.armies:
        for component in army.units:
            group = rules_unit_view_from_armies(
                armies=scenario.armies, unit_instance_id=component.unit_instance_id
            )
            for model in component.own_models:
                if model.model_instance_id in enemy_by_id:
                    groups.setdefault(group.unit_instance_id, []).append(
                        enemy_by_id[model.model_instance_id]
                    )
    selected_ids = (
        (surge_target_id,)
        if fight_proposal is None
        else tuple(
            sorted(
                {
                    rules_unit_view_from_armies(
                        armies=scenario.armies, unit_instance_id=uid
                    ).unit_instance_id
                    for uid in fight_proposal.target_unit_instance_ids
                }
            )
        )
    )
    return contact_move_constraints(
        query,
        ruleset=ruleset,
        enemy_groups=tuple(tuple(ms) for _, ms in sorted(groups.items())),
        selected_groups=tuple(tuple(groups[uid]) for uid in selected_ids if uid is not None),
        mode=MovementMode.NORMAL if fight_proposal is None else fight_proposal.movement_mode,
        consolidation_mode=None if fight_proposal is None else fight_proposal.consolidation_mode,
        surge=surge_target_id is not None,
    )


def contact_query_with_peers(
    *,
    path_context: PathValidationContext,
    terrain_context: TerrainPathLegalityContext,
    peers: tuple[Model, ...],
    ruleset: RulesetDescriptor,
) -> MovementReachabilityQuery:
    policy = ruleset.coherency_policy
    neighbors = policy.required_neighbors_small_unit
    if (
        policy.large_unit_model_count_threshold is not None
        and len(peers) + 1 >= policy.large_unit_model_count_threshold
    ):
        neighbors = policy.required_neighbors_large_unit
    return MovementReachabilityQuery(
        path_context=path_context,
        terrain_context=terrain_context,
        goal=MovementGoal(models=path_context.enemy_models, range_inches=0.0),
        coherent_models=peers,
        coherency_neighbor_count=1 if neighbors is None else neighbors,
        coherency_horizontal_inches=0.0
        if policy.max_horizontal_inches is None
        else policy.max_horizontal_inches,
        coherency_vertical_inches=0.0
        if policy.max_vertical_inches is None
        else policy.max_vertical_inches,
        coherency_max_span_inches=policy.max_unit_span_inches,
        coherency_all_models_distance_inches=policy.max_all_models_distance_inches,
    )
