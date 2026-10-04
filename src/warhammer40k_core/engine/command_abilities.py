"""The selected Core Command-abilities boundary, distinct from start/end rules."""

from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.faction_content.events import RuntimeContentEventIndex
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.runtime_timing_sequencing import resolve_runtime_timing_window
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

COMMAND_ABILITIES_SOURCE_RULE_ID = "rule:08:08.04:1"
COMMAND_ABILITIES_SOURCE_STEP = "command_abilities"


def command_abilities_window(state: GameState) -> TimingWindow:
    command = state.command_step_state
    active = state.active_player_id
    if (
        state.current_battle_phase is not BattlePhase.COMMAND
        or active is None
        or command is None
        or command.battle_round != state.battle_round
        or command.active_player_id != active
        or not command.command_points_granted
        or not command.battle_shock_step_resolved
    ):
        raise GameLifecycleError("Command abilities require completed Core CP and Battle-shock.")
    identifier = (
        f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
        f"turn:{active}:phase:command:abilities"
    )
    return TimingWindow(
        window_id=identifier,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=active,
        phase=BattlePhase.COMMAND,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{identifier}:descriptor",
            trigger_kind=TimingTriggerKind.DURING_PHASE,
            source_rule_id=COMMAND_ABILITIES_SOURCE_RULE_ID,
            phase=BattlePhase.COMMAND,
            source_step=COMMAND_ABILITIES_SOURCE_STEP,
        ),
    )


def resolve_command_abilities(
    *,
    state: GameState,
    decisions: DecisionController,
    index: RuntimeContentEventIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> LifecycleStatus | None:
    return resolve_runtime_timing_window(
        state=state,
        decisions=decisions,
        window=command_abilities_window(state),
        index=index,
        runtime_modifier_registry=runtime_modifier_registry,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
