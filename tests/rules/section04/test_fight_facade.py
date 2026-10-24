from typing import cast

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import (
    body,
    choose,
    combat_session,
    combat_state,
    finish_attacks,
    pending,
    weapon_rows,
)
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase
from warhammer40k_core.engine.phase import BattlePhase


def test_native_fight_selection_declaration_and_completion(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(
        d, combat_state(d, unit, phase=BattlePhase.FIGHT, distance=2.5), section04_mission
    )
    request = pending(session)
    assert request.decision_type == "select_fight_activation"
    choose(session, request, request.options[0].option_id)
    request = pending(session)
    assert request.decision_type == "submit_melee_declaration"
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "fight_activation_selected" for e in events)
    assert not any(e.event_type == "attack_sequence_step" for e in events)
    row = weapon_rows(request)[0]
    proposal = cast(dict[str, JsonValue], body(request)["proposal_request"])
    payload = {
        key: proposal[key]
        for key in (
            "battle_round",
            "unit_instance_id",
            "source_decision_request_id",
            "source_decision_result_id",
        )
    }
    payload.update(
        player_id=request.actor_id,
        proposal_kind="melee_declaration",
        proposal_request_id=request.request_id,
        declarations=[
            {
                "attacker_model_instance_id": row["model_instance_id"],
                "wargear_id": row["wargear_id"],
                "weapon_profile_id": row["weapon_profile_id"],
                "weapon_instance_id": row["weapon_instance_id"],
                "selected_weapon_ability_ids": [],
                "target_allocations": [{"target_unit_instance_id": "enemy:target"}],
            }
        ],
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="section04:melee",
        payload=validate_json_value(payload),
    )
    assert status.status_kind.value != "invalid", status
    finish_attacks(session)
    events = session.lifecycle.decision_controller.event_log.records
    completed = next(e for e in events if e.event_type == "attack_sequence_completed")
    sequence = completed_attack_sequence(
        event_records=events,
        sequence_id=cast(str, cast(dict[str, JsonValue], completed.payload)["sequence_id"]),
    )
    assert sequence.is_complete
    assert sequence.source_phase is BattlePhase.FIGHT
    assert len(sequence.attack_pools) == 1
    pool = sequence.attack_pools[0]
    assert pool.weapon_profile == d.weapon(pool.wargear_id)
    assert pool.weapon_instance_id == row["weapon_instance_id"]
    assert pool.attacks == pool.weapon_profile.attack_profile.fixed_attacks
    assert model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=pool.attacker_model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase="fight",
    )
    assert max(
        i for i, e in enumerate(events) if e.event_type == "attack_sequence_step"
    ) < events.index(completed)
    assert any(e.event_type == "unit_has_fought" for e in events)
