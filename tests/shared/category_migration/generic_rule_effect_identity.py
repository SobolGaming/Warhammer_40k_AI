"""R42-003: persisted identity belongs to one activation, binding and effect slot."""

from dataclasses import replace
from typing import Any, cast

import pytest

from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.generic_rule_effect_identity import generic_rule_persisting_effect_id
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as keyword_source,
)


def _scene() -> tuple[RuleIR, RuleExecutionContext]:
    lifecycle, units = fight_lifecycle(
        game_id="order42-effect-identity",
        alpha_unit_ids=("first", "second"),
        enemy_unit_ids=("enemy",),
        origins={
            "first": Pose.at(10, 10),
            "second": Pose.at(20, 10),
            "enemy": Pose.at(40, 10),
        },
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
    )
    state = lifecycle.state
    assert state is not None
    source = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id="order42:identity-stealth-grant",
        raw_text="That unit gains Stealth until the end of the phase.",
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=keyword_source.canonical_datasheet_keyword_sequence_parts(),
    ).rule_ir
    assert rule_ir.is_supported
    return rule_ir, RuleExecutionContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
        timing_window_id="order42:first-activation",
        source_unit_instance_id=units["first"].unit_instance_id,
        source_model_instance_id=units["first"].own_models[0].model_instance_id,
        target_unit_instance_ids=(units["first"].unit_instance_id,),
        target_player_id="player-a",
        trigger_payload={"decision_result_id": "order42:first-result"},
        state=state,
        event_log=EventLog(),
    )


__all__: list[str] = []
__all__ += ["Any", "BattlePhase", "EventLog", "GameLifecycleError", "ObjectiveRuleScope", "Pose"]
__all__ += ["RuleClause", "RuleExecutionContext", "RuleExecutionStatus", "RuleIR"]
__all__ += ["RuleSourceText", "_scene", "cast", "compile_rule_source_text", "execute_rule_ir"]
__all__ += ["fight_lifecycle", "generic_rule_persisting_effect_id", "keyword_source", "pytest"]
__all__ += ["replace"]
