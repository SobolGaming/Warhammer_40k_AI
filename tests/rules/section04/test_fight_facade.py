from dataclasses import replace
from typing import cast

import pytest

from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.random_melee_helpers import melee_boundary, single_target_commitment_payload
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
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.count_profiles import AttackProfile, DamageProfile
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import DECLINE_STRATAGEM_WINDOW_OPTION_ID
from warhammer40k_core.geometry.pose import Pose


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


@pytest.mark.parametrize("reroll", [False, True])
def test_fight_damage_reroll_stays_fresh_after_previous_attack_destroys_model(reroll: bool) -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    blade = next(gear for gear in catalog.wargear if gear.wargear_id == "core-leader-blade")
    infantry = next(
        sheet
        for sheet in catalog.datasheets
        if sheet.datasheet_id == "core-intercessor-like-infantry"
    )
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                gear,
                weapon_profiles=(
                    replace(
                        blade.weapon_profiles[0],
                        attack_profile=AttackProfile.fixed(8),
                        damage_profile=DamageProfile.dice(DiceExpression(1, 6, 2)),
                    ),
                ),
            )
            if gear == blade
            else gear
            for gear in catalog.wargear
        ),
        datasheets=tuple(
            replace(
                sheet, composition=tuple(replace(row, min_models=2) for row in sheet.composition)
            )
            if sheet == infantry
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("target", "spare"),
        origins={"attacker": Pose.at(20, 20), "target": Pose.at(22, 20), "spare": Pose.at(40, 40)},
        game_id="fight-reroll-after-casualty",
        catalog=catalog,
        alpha_unit_specs={"attacker": ("core-character-leader", "core-character-leader", 1)},
        enemy_unit_specs={"target": (infantry.datasheet_id, "core-intercessor-like", 2)},
        fights_first_unit_keys=("attacker",),
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="fight-reroll-after-casualty:fixture",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    session = LocalGameSession(lifecycle)
    request = melee_boundary(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="fight-reroll-after-casualty:melee",
        payload=single_target_commitment_payload(request),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    events = lifecycle.decision_controller.event_log
    for _ in range(35):
        request = pending(session)
        if any(event.event_type == "model_destroyed" for event in events.records):
            break
        option = next(
            (
                option
                for option in request.options
                if option.option_id == DECLINE_STRATAGEM_WINDOW_OPTION_ID
            ),
            request.options[0],
        )
        choose(session, request, option.option_id)
    else:
        raise AssertionError("Fight did not destroy the first target model.")
    assert request.actor_id == "player-a"
    assert request.decision_type == "use_stratagem"
    window = cast(dict[str, JsonValue], body(request)["opportunity_window"])
    metadata = cast(dict[str, JsonValue], window["metadata"])
    roll_type = cast(str, metadata["roll_type"])
    prefix = "random_characteristic.damage.per_attack."
    assert roll_type.startswith(prefix)
    attack_context_id = roll_type.removeprefix(prefix).removesuffix(":damage")
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    view = session.view(viewer_player_id=request.actor_id)["pending_decision"]
    assert view is not None
    assert restored.view(viewer_player_id=request.actor_id)["pending_decision"] == view
    option_id = next(
        option["option_id"]
        for option in view["options"]
        if ("command-reroll" in option["option_id"]) == reroll
    )
    status = restored.submit_viewer_option(
        viewer=ViewerContext.for_player(request.actor_id),
        request_id=view["request_id"],
        option_id=option_id,
        result_id="fight-reroll-after-casualty:answer",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    assert window["sequence_number"] == len(events.records) - 1
    assert (
        sum(event.event_type == "model_destruction_occurrence_recorded" for event in events.records)
        == 1
    )
    casualty = next(event for event in events.records if event.event_type == "model_destroyed")
    casualty_id = cast(dict[str, JsonValue], casualty.payload)["model_instance_id"]
    assert casualty_id in {model.model_instance_id for model in units["target"].own_models}
    resumed_events = restored.lifecycle.decision_controller.event_log.records
    assert (
        sum(
            event.event_type == "model_destroyed"
            and cast(dict[str, JsonValue], event.payload)["model_instance_id"] == casualty_id
            for event in resumed_events
        )
        == 1
    )
    assert (
        sum(
            event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "damage"
            and event.payload.get("attack_context_id") == attack_context_id
            for event in resumed_events
        )
        == 1
    )
    assert sum(event.event_type == "command_reroll_resolved" for event in resumed_events) == reroll
    restored_state = restored.lifecycle.state
    assert restored_state is not None
    assert (
        sum(
            record.command_point_cost
            for record in restored_state.stratagem_use_records
            if record.stratagem_id == "command-reroll" and record.player_id == "player-a"
        )
        == reroll
    )
    replay = ReplayRunner.from_payload(
        restored.replay_artifact(artifact_id="fight-reroll-after-casualty")
    ).run()
    assert replay.reproduced_exactly, replay
