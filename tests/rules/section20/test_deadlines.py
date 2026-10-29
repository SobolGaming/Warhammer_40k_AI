"""20.01.02/20.03: reserve deadline, cargo and final cleanup without reactions."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section20_fixtures import reserve_scene
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reserve_destruction import (
    final_turn_cleanup_policy,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.reserve_lifetime_boundary import apply_destruction
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
    ReserveStatus,
)


@pytest.mark.parametrize(
    "kind", [ReserveKind.STRATEGIC_RESERVES, ReserveKind.RESERVES, ReserveKind.DEEP_STRIKE]
)
@pytest.mark.parametrize(
    ("round_number", "end", "exempt", "dies"),
    [
        (2, False, False, False),
        (3, False, False, True),
        (3, False, True, False),
        (5, True, True, True),
    ],
)
def test_synonymous_reserves_deadlines_and_final_cleanup_use_logical_death_without_model_triggers(
    section20_definitions: Section02Definitions,
    kind: ReserveKind,
    round_number: int,
    end: bool,
    exempt: bool,
    dies: bool,
) -> None:
    s = reserve_scene(section20_definitions)
    s.state.reserve_states[:] = [
        ReserveState.declared_before_battle(
            player_id="owner", unit_instance_id=s.unit.unit_instance_id, reserve_kind=kind
        )
    ]
    s.state.battle_round = round_number
    assert s.state.battlefield_state is not None
    result = resolve_unarrived_reserve_destruction(
        reserve_states=tuple(s.state.reserve_states),
        armies=tuple(s.state.army_definitions),
        battlefield_state=s.state.battlefield_state,
        policy=final_turn_cleanup_policy()
        if end
        else ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=round_number,
        end_of_battle=end,
        exempt_unit_instance_ids=frozenset({s.unit.unit_instance_id}) if exempt else frozenset(),
    )
    assert bool(result.destroyed_model_instance_ids) is dies
    assert (result.updated_reserve_states[0].status is ReserveStatus.DESTROYED) is dies
    if dies:
        apply_destruction(s.state, destruction=result)
        models = tuple(
            model_by_id(state=s.state, model_instance_id=mid) for mid in s.unit.own_model_ids()
        )
        assert not any(m.is_alive for m in models)
        assert set(s.unit.own_model_ids()).issubset(s.state.battlefield_state.removed_model_ids)
        assert not s.state.pending_return_on_death


def test_arrived_reserve_is_not_destroyed_at_either_deadline(
    section20_definitions: Section02Definitions,
) -> None:
    s = reserve_scene(section20_definitions)
    arrived = s.state.reserve_states[0].mark_arrived(
        battle_round=2,
        phase=BattlePhase.MOVEMENT,
        large_model_exception_used=False,
        post_arrival_restrictions=(),
    )
    assert s.state.battlefield_state is not None
    for end, number, policy in (
        (False, 3, ReserveDestructionTimingPolicy.core_rules_default()),
        (True, 5, final_turn_cleanup_policy()),
    ):
        result = resolve_unarrived_reserve_destruction(
            reserve_states=(arrived,),
            armies=tuple(s.state.army_definitions),
            battlefield_state=s.state.battlefield_state,
            policy=policy,
            battle_round=number,
            end_of_battle=end,
        )
        assert result.updated_reserve_states == (arrived,)
        assert not result.destroyed_model_instance_ids
