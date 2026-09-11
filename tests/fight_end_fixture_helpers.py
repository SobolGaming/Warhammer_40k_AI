"""Real phase-boundary routing for focused Fight-end executor fixtures."""

from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.boundary_rule_flow import prepare_phase_end_boundary
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_phase_end_hooks import (
    FightPhaseEndHookRegistry,
    FightPhaseEndRequestContext,
)
from warhammer40k_core.engine.fight_phase_end_sequencing import fight_end_boundary_binding
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry


def single_fight_end_request(
    registry: FightPhaseEndHookRegistry,
    context: FightPhaseEndRequestContext,
) -> DecisionRequest | None:
    prepare_phase_end_boundary(
        state=context.state,
        decisions=context.decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = registry.next_request_for(context)
    assert request is None or isinstance(request, DecisionRequest)
    return request


def advance_fight_end_fixture(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus:
    return BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: handler},
        turn_end_hooks=TurnEndHookRegistry.from_bindings(
            (fight_end_boundary_binding(handler.fight_phase_end_hooks),)
        ),
        runtime_modifier_registry=handler.runtime_modifier_registry,
        ruleset_descriptor=handler.ruleset_descriptor,
        army_catalog=handler.army_catalog,
    ).advance(state=state, decisions=decisions)


def advance_completed_phase_fixture(
    *, flow: BattleRoundFlow, config: GameConfig, state: GameState, decisions: DecisionController
) -> LifecycleStatus:
    """Finish loaded deferred rules around a deliberately completed phase body."""
    from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
    from warhammer40k_core.engine.faction_content.runtime import (
        build_runtime_content_bundle_for_armies,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
    from warhammer40k_core.engine.rule_trigger_runtime import advance_rule_triggers

    if state.current_battle_phase is BattlePhase.FIGHT:
        fight = state.fight_phase_state
        if fight is None or (fight.battle_round, fight.active_player_id) != (
            state.battle_round,
            state.active_player_id,
        ):
            seed_completed_fight_phase(state)
    bundle = build_runtime_content_bundle_for_armies(
        config=config, armies=tuple(state.army_definitions)
    )
    shooting = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    for _ in range(32):
        status = advance_rule_triggers(
            state=state,
            decisions=decisions,
            runtime_bundle_provider=lambda: bundle,
            shooting_handler_provider=lambda: shooting,
        )
        if status is None:
            status = flow.advance(state=state, decisions=decisions)
        if status.status_kind is not LifecycleStatusKind.ADVANCED:
            return status
    raise AssertionError("Completed phase did not finish its deferred rules")
