"""Reach retained death through actual attack resolution and accepted DecisionResult."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    resolve,
)

from warhammer40k_core.engine.damage_allocation import DestructionReactionSource
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_reaction_kind import DestructionReactionKind
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.retained_destruction_selection import (
    apply_retention_selection,
    is_retention_request,
)
from warhammer40k_core.engine.retained_destruction_state import RetainedModelDestruction
from warhammer40k_core.engine.unit_factory import UnitInstance

SOURCE = DestructionReactionSource(
    source_id="constructed:s05:fod",
    source_rule_id="constructed:s05:fod",
    reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
)


def terminal_retention(
    d: Section02Definitions,
    *,
    demise: bool = False,
    distance: float = 8,
    melee: bool = False,
) -> tuple[GameState, UnitInstance, DecisionController, DecisionRequest]:
    state, target, sequence = native_sequence(d, distance=distance, melee=melee)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(state, target)
    sources: tuple[DestructionReactionSource, ...] = (SOURCE,)
    if demise:
        sources = (
            *sources,
            DestructionReactionSource(
                source_id="constructed:s05:demise",
                source_rule_id="constructed:s05:demise",
                reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                optional=False,
                payload={
                    "trigger_roll_threshold": 6,
                    "range_inches": 6.0,
                    "mortal_wounds": {"kind": "fixed", "value": 1},
                },
            ),
        )
    state.record_model_destruction_reaction_sources(
        model_instance_id=target.own_model_ids()[0], sources=sources
    )
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6,), (6,), (1,))
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    assert is_retention_request(status.decision_request)
    return state, target, decisions, status.decision_request


def retain(
    state: GameState, decisions: DecisionController, request: DecisionRequest
) -> RetainedModelDestruction:
    result = DecisionResult.for_request(
        result_id="s05:retain", request=request, selected_option_id=SOURCE.source_id
    )
    decisions.submit_result(result)
    return apply_retention_selection(state=state, decisions=decisions, result=result)
