"""15.03: one selected native CHARACTER model, phase lifetime and atomic guards."""

from copy import deepcopy

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section15_fixtures import checkpoint, context, events, obj, offer, submit
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.fight_resolution import _epic_challenge_profile_if_applicable
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def test_only_selected_character_melee_weapons_gain_precision_until_phase_end(
    section15_definitions: Section02Definitions,
) -> None:
    d = section15_definitions
    session, state, unit, enemy = checkpoint(d)
    own = state.army_definition_for_player("owner")
    assert own is not None
    mid = own.unit_by_id(unit).own_model_ids()[0]
    ctx = context(
        state,
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        {"selected_unit_instance_id": unit},
    )
    req = offer(session, state, "epic-challenge", ctx)
    status = submit(session, req, unit, effect={"character_model_instance_id": mid})
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("owner") == 3
    use = state.stratagem_use_records[-1]
    assert use.targeted_unit_instance_ids == use.affected_unit_instance_ids == (unit,)
    melee = d.weapon(f"{LORD_EXULTANT}:close-combat-weapon")
    ranged = d.weapon(f"{LORD_EXULTANT}:bolt-pistol")
    assert WeaponKeyword.PRECISION not in melee.keywords
    assert (
        WeaponKeyword.PRECISION
        in _epic_challenge_profile_if_applicable(
            state=state, unit_instance_id=unit, attacker_model_instance_id=mid, profile=melee
        ).keywords
    )
    # The fight-only helper is called after the melee commitment owner; passing
    # ranged profiles to it would bypass that boundary. Native catalog resources
    # remain unchanged; the shooting consumer is independently exercised in Snap.
    assert d.weapon(f"{LORD_EXULTANT}:bolt-pistol") == ranged
    assert WeaponKeyword.PRECISION not in ranged.keywords
    other = state.army_definition_for_player("opponent")
    assert other is not None
    enemy_mid = other.unit_by_id(enemy).own_model_ids()[0]
    assert (
        _epic_challenge_profile_if_applicable(
            state=state, unit_instance_id=enemy, attacker_model_instance_id=enemy_mid, profile=melee
        )
        == melee
    )
    kinds = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
    assert kinds.index("command_points_spent") < kinds.index("stratagem_used")
    assert events(session, "stratagem_used")[-1]["player_id"] == "owner"
    from warhammer40k_core.engine.effects import EffectExpirationBoundary

    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=state.battle_round, phase=BattlePhase.FIGHT, player_id="owner"
        )
    )
    assert (
        _epic_challenge_profile_if_applicable(
            state=state, unit_instance_id=unit, attacker_model_instance_id=mid, profile=melee
        )
        == melee
    )


@pytest.mark.parametrize("drift", ["model", "unit", "owner", "round", "phase", "cp", "context"])
def test_epic_invalid_selection_preserves_queue_ledgers_effects_and_retry(
    section15_definitions: Section02Definitions, drift: str
) -> None:
    session, state, unit, enemy = checkpoint(section15_definitions)
    own = state.army_definition_for_player("owner")
    assert own is not None
    mid = own.unit_by_id(unit).own_model_ids()[0]
    req = offer(
        session,
        state,
        "epic-challenge",
        context(
            state,
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
            {"selected_unit_instance_id": unit},
        ),
    )
    assert isinstance(req.payload, dict)
    proposal = deepcopy(obj(req.payload)["proposal_request"])
    proposal["target_binding"] = {
        "target_kind": "friendly_unit",
        "target_player_id": "owner",
        "target_unit_instance_id": unit,
    }
    proposal["effect_selection"] = {"character_model_instance_id": mid}
    if drift == "model":
        proposal["effect_selection"]["character_model_instance_id"] = "unknown:model"
    elif drift == "unit":
        proposal["target_binding"]["target_unit_instance_id"] = enemy
    elif drift == "owner":
        proposal["target_binding"]["target_player_id"] = "opponent"
    elif drift == "round":
        proposal["context"]["battle_round"] += 1
    elif drift == "phase":
        proposal["context"]["phase"] = "shooting"
    elif drift == "context":
        proposal["context"]["trigger_payload"] = {"selected_unit_instance_id": enemy}
    else:
        state.spend_command_points(player_id="owner", amount=4, source_id="constructed:s15:drift")
    before = deepcopy(session.lifecycle.to_payload())
    status = session.submit_parameterized_payload(
        request_id=req.request_id,
        result_id="s15:invalid",
        payload={"proposal": proposal},
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.decision_controller.queue.pending_requests == (req,)
    assert state.stratagem_use_records == []
    assert [e.to_payload() for e in state.persisting_effects] == before["state"][
        "persisting_effects"
    ]
    if drift != "cp":
        accepted = submit(session, req, unit, effect={"character_model_instance_id": mid})
        assert accepted.status_kind is not LifecycleStatusKind.INVALID
        assert state.command_point_total("owner") == 3
