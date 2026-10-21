"""15.10: constructed SMOKE keyword on native envelopes; native generic effect path."""

from dataclasses import replace

import pytest

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section09_fixtures import add_unit
from tests.support.section15_fixtures import checkpoint, context, obj, offer
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_sources
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(("offset", "collateral"), [(0.5, True), (6, False)])
def test_smoke_grants_cover_to_itself_and_only_targets_obscured_by_its_models(
    section15_definitions: Section02Definitions, offset: float, collateral: bool
) -> None:
    d = section15_definitions
    session, state, unit, enemy = checkpoint(
        d, phase=BattlePhase.SHOOTING, active="opponent", distance=20, materialize=False
    )
    own = state.army_definition_for_player("owner")
    other = state.army_definition_for_player("opponent")
    assert own is not None
    assert other is not None
    native = own.unit_by_id(unit)
    smoke = with_unit_keywords(native, keywords=(*native.keywords, "SMOKE"))
    state.army_definitions[:] = [
        replace(a, units=(smoke,)) if a.player_id == "owner" else a for a in state.army_definitions
    ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(placement(smoke, (Pose.at(20, 10 + offset),)))
    )
    target = d.unit(LORD_EXULTANT, identity="sheltered")
    add_unit(state, target, (Pose.at(10, 10),))
    # The observer is the native enemy at x=30; smoke is between x=30 and x=10.
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    req = offer(session, state, "smokescreen", context(state, TimingTriggerKind.START_PHASE))
    selected = next(
        o
        for o in req.options
        if isinstance(o.payload, dict)
        and obj(o.payload)["target_binding"]["target_unit_instance_id"] == unit
    )
    status = session.submit_option(
        request_id=req.request_id, result_id="s15:smoke", option_id=selected.option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    attacker = other.unit_by_id(enemy)
    profile = d.weapon(f"{LORD_EXULTANT}:bolt-pistol")
    self_pool = attack_pool(attacker, smoke, profile, f"{LORD_EXULTANT}:bolt-pistol")
    behind_pool = attack_pool(attacker, target, profile, f"{LORD_EXULTANT}:bolt-pistol")
    assert obscuring_model_cover_sources(state=state, pool=self_pool) is not None
    assert (obscuring_model_cover_sources(state=state, pool=behind_pool) is not None) is collateral
    assert state.command_point_total("owner") == 3
    assert state.stratagem_use_records[-1].targeted_unit_instance_ids == (unit,)
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=state.battle_round, phase=BattlePhase.SHOOTING, player_id="opponent"
        )
    )
    assert obscuring_model_cover_sources(state=state, pool=self_pool) is None
    assert obscuring_model_cover_sources(state=state, pool=behind_pool) is None
