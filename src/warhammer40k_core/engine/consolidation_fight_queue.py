"""Engine-owned response boundary for both enemy-engaging consolidation modes."""

from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, ConsolidationModeKind
from warhammer40k_core.engine.battlefield_presence import (
    battlefield_scenario_for_state,
    scenario_rules_unit_has_placed_alive_model,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.fight_resolution import FightMovementProposal
from warhammer40k_core.engine.forced_fight_context import ForcedFightActivationContext
from warhammer40k_core.engine.forced_fight_queue import install_forced_fight_queue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_identity_history_contains,
    rules_unit_view_by_id,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_fight_2026_09 import (
    CONSOLIDATION_SOURCE_ID,
    ONGOING_SOURCE_ID,
)


def start_consolidation_fight_queue(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal: FightMovementProposal,
    movement_event: EventRecord,
) -> None:
    if (
        proposal.proposal_kind is not ProposalKind.CONSOLIDATE
        or proposal.consolidation_mode
        not in {
            ConsolidationModeKind.ONGOING,
            ConsolidationModeKind.ENGAGING,
        }
    ):
        return
    suspended = state.fight_phase_state
    if suspended is None or suspended.forced_activation_context is not None:
        raise GameLifecycleError("Consolidation requires its ordinary Fight state.")
    if movement_event.event_type != "fight_movement_completed":
        raise GameLifecycleError("Consolidation response requires a completed movement event.")
    source = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    scenario = battlefield_scenario_for_state(state=state)
    physically_engaged = scenario_physically_engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=source.unit_instance_id,
    )
    engaged = tuple(
        unit_id
        for unit_id in physically_engaged
        if scenario_rules_unit_has_placed_alive_model(
            scenario=scenario,
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
        )
    )
    selected = suspended.fight_order_state.selected_to_fight_unit_ids
    pending = tuple(
        unit_id
        for unit_id in engaged
        if not rules_unit_identity_history_contains(
            state=state,
            identity_ids=selected,
            unit_instance_id=unit_id,
        )
    )
    source_rule_id = (
        ONGOING_SOURCE_ID
        if proposal.consolidation_mode is ConsolidationModeKind.ONGOING
        else CONSOLIDATION_SOURCE_ID
    )
    if not pending:
        decisions.event_log.append(
            "forced_fight_activation_queue_skipped",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhaseKind.FIGHT.value,
                    "active_player_id": state.active_player_id,
                    "phase_body_status": "forced_fight_activation_queue_skipped",
                    "source_rule_id": source_rule_id,
                    "trigger_event_id": movement_event.event_id,
                    "source_unit_instance_id": source.unit_instance_id,
                    "engaged_enemy_unit_instance_ids": list(engaged),
                    "already_selected_unit_instance_ids": sorted(selected),
                }
            ),
        )
        return
    owners = {
        rules_unit_view_by_id(state=state, unit_instance_id=unit_id).owner_player_id
        for unit_id in pending
    }
    if len(owners) != 1 or source.owner_player_id in owners:
        raise GameLifecycleError("Consolidation response units must belong to one opponent.")
    context = ForcedFightActivationContext(
        context_id=f"forced-fight:{movement_event.event_id}",
        source_rule_id=source_rule_id,
        trigger_event_id=movement_event.event_id,
        source_phase=BattlePhaseKind.FIGHT,
        source_unit_instance_id=source.unit_instance_id,
        transport_unit_instance_id=None,
        selecting_player_id=next(iter(owners)),
        eligible_unit_instance_ids=pending,
    )
    install_forced_fight_queue(
        state=state,
        decisions=decisions,
        context=context,
        policy=state.runtime_ruleset_descriptor().fight_policy,
        suspended_state=suspended,
    )
