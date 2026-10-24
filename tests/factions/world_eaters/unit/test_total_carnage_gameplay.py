"""Total Carnage timing branches and real retained Fight completion."""

from typing import cast

import pytest
from tests.factions.world_eaters.attack_helpers import resolve_native_attack
from tests.factions.world_eaters.gameplay_helpers import (
    SOURCE,
    complete_activation,
    events,
    gameplay_session,
    reach,
    select_blessings,
)
from tests.factions.world_eaters.world_eaters_helpers import _unit_by_id
from tests.fight_completion_positive_helpers import assert_completed_melee

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import army_rule
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.retained_destruction_state import retained_destructions


@pytest.mark.parametrize("branch", ["miss", "ranged", "already-fought"])
def test_total_carnage_ineligible_or_failed_trigger_completes_killing_attack(branch: str) -> None:
    session = gameplay_session(
        game_id="we-carnage-guards",
        phase=BattlePhase.SHOOTING if branch == "ranged" else BattlePhase.FIGHT,
    )
    select_blessings(session, army_rule.BlessingOfKhorne.TOTAL_CARNAGE)
    if branch == "already-fought":
        complete_activation(session, SOURCE)
        assert_completed_melee(session.lifecycle, unit_instance_id=SOURCE)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model_id = _unit_by_id(state, SOURCE).own_models[0].model_instance_id
    # Native guard proof retains the actual completed Fight state. Its incoming
    # executor has its own controller; the lifecycle's next phase request remains
    # owned by that lifecycle and is never replaced or consumed by this fixture.
    native = (
        DecisionController()
        if branch == "already-fought"
        else session.lifecycle.decision_controller
    )
    remaining, status = resolve_native_attack(
        session,
        incoming=True,
        ranged=branch == "ranged",
        trigger=1 if branch == "miss" else None,
        damage=10,
        controller=native,
    )
    assert status is None
    assert remaining is None or remaining.is_complete
    assert not _unit_by_id(state, SOURCE).own_models[0].is_alive
    assert model_id in state.battlefield_state.removed_model_ids
    triggers = [
        cast(dict[str, JsonValue], row.payload)
        for row in native.event_log.records
        if row.event_type == "fight_on_death_retention_trigger_resolved"
    ]
    if branch == "miss":
        assert len(triggers) == 1
        assert triggers[0]["applicable"] is True
        assert triggers[0]["triggered"] is False
    else:
        assert len(triggers) == 1
        assert triggers[0]["applicable"] is False
        assert triggers[0]["triggered"] is False
        assert triggers[0]["trigger_roll"] is None
        assert not any(
            row.event_type == "dice_rolled"
            and isinstance(row.payload, dict)
            and isinstance(row.payload["spec"], dict)
            and row.payload["spec"]["roll_type"] == "world_eaters_total_carnage"
            for row in native.event_log.records
        )
    assert not native.queue.pending_requests


@pytest.mark.parametrize("accept", [False, True])
def test_total_carnage_real_kill_decline_or_retained_fight_and_single_cleanup(accept: bool) -> None:
    session = gameplay_session(game_id="we-carnage-outcome-3", lethal=True, enemy_first=True)
    select_blessings(session, army_rule.BlessingOfKhorne.TOTAL_CARNAGE)
    request = reach(session, "select_destruction_reaction")
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model_id = _unit_by_id(state, SOURCE).own_models[0].model_instance_id
    placement = state.battlefield_state.model_placement_by_id(model_id)
    assert not _unit_by_id(state, SOURCE).own_models[0].is_alive
    assert model_id not in state.battlefield_state.removed_model_ids
    assert events(session, "fight_on_death_retention_trigger_resolved")[0]["triggered"] is True
    option = next(
        item.option_id
        for item in request.options
        if item.option_id.startswith(army_rule.TOTAL_CARNAGE_HOOK_ID)
    )
    status = session.submit_option(
        request_id=request.request_id,
        result_id="we-carnage-choice",
        option_id=option if accept else "decline_destruction_reaction",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    if accept:
        assert state.battlefield_state.model_placement_by_id(model_id) == placement
        assert len(retained_destructions(state=state)) == 1
        checkpoint = session.lifecycle.to_payload()
        restored = GameLifecycle.from_payload(checkpoint)
        assert restored.to_payload() == checkpoint
        session = LocalGameSession(restored)
        complete_activation(session, SOURCE)
        assert_completed_melee(session.lifecycle, unit_instance_id=SOURCE)
        assert len(events(session, "fight_on_death_destruction_completed")) == 1
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert state.battlefield_state.model_placement_or_none(model_id) is None
    deaths = [
        row for row in events(session, "model_destroyed") if row["model_instance_id"] == model_id
    ]
    assert len(deaths) == 1
    if not accept:
        assert events(session, "fight_on_death_destruction_completed") == []
        assert not any(
            cast(dict[str, JsonValue], row["activation_selection"])["unit_instance_id"] == SOURCE
            for row in events(session, "unit_has_fought")
        )
