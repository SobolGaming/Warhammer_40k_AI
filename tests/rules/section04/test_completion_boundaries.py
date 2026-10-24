"""Completion status contrasts with accepted declarations and empty selections."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_completion import completion_boundaries
from tests.support.section04_fixtures import (
    choose,
    combat_session,
    combat_state,
    declare_shooting,
    pending,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.shooting_eligibility import _unit_has_already_shot
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


def test_native_unit_is_not_shot_before_any_declared_attack_resolves(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup
) -> None:
    """Source-correct SF04-002 regression: declaration alone is not having shot."""
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit)
    session = combat_session(d, state, section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    assert not _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)
    declare_shooting(session, request, weapon_rows(request)[:2], ["enemy:target"] * 2)
    assert pending(session).decision_type == "select_attack_weapon_group"
    events = session.lifecycle.decision_controller.event_log.records
    assert not any(
        e.event_type in {"attack_sequence_step", "attack_sequence_completed", "unit_has_shot"}
        for e in events
    )
    assert not model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=unit.own_model_ids()[0],
        battle_round=1,
        active_player_id="owner",
        phase="shooting",
    )
    assert not _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)


def test_constructed_unequipped_native_body_resolves_fight_without_having_fought(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup
) -> None:
    """No supported native unarmed melee profile: explicit zero-equipment contract."""
    d = section04_definitions
    native = d.unit(LORD_EXULTANT)
    unit = replace(
        native,
        own_models=tuple(replace(m, wargear_ids=()) for m in native.own_models),
        wargear_selections=(),
    )
    state = combat_state(d, unit, phase=BattlePhase.FIGHT, distance=2.5)
    session = combat_session(d, state, section04_mission)
    request = pending(session)
    assert request.decision_type == "select_fight_activation"
    option = next(o.option_id for o in request.options if unit.unit_instance_id in o.option_id)
    choose(session, request, option)
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "fight_activation_selected" for e in events)
    assert any(e.event_type == "fight_activation_completed" for e in events)
    assert not any(e.event_type in {"attack_sequence_step", "unit_has_fought"} for e in events)
    assert not model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=unit.own_model_ids()[0],
        battle_round=1,
        active_player_id="owner",
        phase="fight",
    )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_completed_weapon_is_distinct_from_unfinished_model_and_unit(
    section04_definitions: Section02Definitions,
    phase: BattlePhase,
) -> None:
    """Native physical weapons; melee extra-attack admission is an explicit contract."""
    original, snapshots, final_events = completion_boundaries(
        section04_definitions, phase=phase, multiple_models=False
    )
    sequence, events = next((s, e) for s, e in snapshots if s.used_pool_indices == (0,))
    assert (
        original.attack_pools[0].weapon_instance_id != original.attack_pools[1].weapon_instance_id
    )
    assert sequence.used_pool_indices == (0,)
    hits = [
        cast(dict[str, JsonValue], e.payload)["pool_index"]
        for e in events
        if e.event_type == "attack_sequence_step"
        and cast(dict[str, JsonValue], e.payload)["step"] == "hit"
    ]
    assert hits == [0] * original.attack_pools[0].attacks
    assert not sequence.is_complete
    assert not model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=original.attack_pools[0].attacker_model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase=phase.value,
    )
    with pytest.raises(GameLifecycleError, match="unique executor state"):
        completed_attack_sequence(event_records=events, sequence_id=original.sequence_id)
    finished = completed_attack_sequence(
        event_records=final_events, sequence_id=original.sequence_id
    )
    assert finished.is_complete
    assert set(finished.used_pool_indices) == set(range(len(original.attack_pools)))
    assert model_has_attacked_this_phase(
        event_records=final_events,
        model_instance_id=original.attack_pools[0].attacker_model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase=phase.value,
    )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_finished_native_model_counts_before_other_models_complete(
    section04_definitions: Section02Definitions,
    phase: BattlePhase,
) -> None:
    """Three native bearers/targets; an explicit selected-pool executor contract."""
    original, snapshots, final_events = completion_boundaries(
        section04_definitions, phase=phase, multiple_models=True
    )
    sequence, events = next((s, e) for s, e in snapshots if s.used_pool_indices == (0,))
    finished = completed_attack_sequence(
        event_records=final_events, sequence_id=original.sequence_id
    )
    assert finished.is_complete
    assert all(
        model_has_attacked_this_phase(
            event_records=final_events,
            model_instance_id=pool.attacker_model_instance_id,
            battle_round=1,
            active_player_id="owner",
            phase=phase.value,
        )
        for pool in original.attack_pools
    )
    assert len({p.attacker_model_instance_id for p in original.attack_pools}) == 3
    assert sequence.used_pool_indices == (0,)
    hits = [
        cast(dict[str, JsonValue], e.payload)["pool_index"]
        for e in events
        if e.event_type == "attack_sequence_step"
        and cast(dict[str, JsonValue], e.payload)["step"] == "hit"
    ]
    assert hits == [0] * original.attack_pools[0].attacks
    assert not sequence.is_complete
    assert not any(e.event_type == "attack_sequence_completed" for e in events)
    assert not model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=original.attack_pools[1].attacker_model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase=phase.value,
    )
    assert model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=original.attack_pools[0].attacker_model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase=phase.value,
    ), "This model finished all its selected attacks while other models remain"


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_facade_incremental_completion_restore_continue_fork_and_replay(
    phase: BattlePhase,
) -> None:
    """Three real canonical bearers, engine declarations and ordinary seeded RNG."""
    import json

    from tests.phase13b_shooting_declaration_helpers import (
        _canonical_catalog,
        _compact_intercessor_catalog,
    )
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from tests.psychic_modifier_helpers import submit_fixture_request
    from tests.support.section04_fixtures import body, finish_attacks
    from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
    from warhammer40k_core.engine.model_attack_history import validate_model_attack_history
    from warhammer40k_core.geometry.pose import Pose

    distance = 8 if phase is BattlePhase.SHOOTING else 2
    subject_spec = ("core-intercessor-like-infantry", "core-intercessor-like", 3)
    target_spec = ("core-intercessor-like-infantry", "core-intercessor-like", 1)
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    # Explicit equipment contract: existing canonical blade on real domain bodies.
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                wargear_options=tuple(
                    replace(
                        profile,
                        default_wargear_ids=(*profile.default_wargear_ids, "core-leader-blade"),
                        allowed_wargear_ids=(*profile.allowed_wargear_ids, "core-leader-blade"),
                        min_selections=2,
                        max_selections=2,
                    )
                    for profile in sheet.wargear_options
                ),
            )
            if sheet.datasheet_id == subject_spec[0]
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("subject", "spare"),
        enemy_unit_ids=("enemy", "other", "third"),
        origins={
            "subject": Pose.at(10, 10),
            "enemy": Pose.at(10 + distance, 10),
            "other": Pose.at(10 - distance, 12),
            "third": Pose.at(12, 12 + distance),
            "spare": Pose.at(40, 35),
        },
        game_id="sf04-completion-" + phase.value,
        model_count=3,
        poses_by_unit_key={
            "subject": (Pose.at(10, 10), Pose.at(10, 12), Pose.at(12, 12)),
            "enemy": (Pose.at(10 + distance, 10),),
            "other": (Pose.at(10 - distance, 12),),
            "third": (Pose.at(12, 12 + distance),),
            "spare": (Pose.at(40, 35),),
        },
        alpha_unit_specs={"subject": subject_spec, "spare": target_spec},
        enemy_unit_specs=dict.fromkeys(("enemy", "other", "third"), target_spec),
        catalog=catalog,
        battle_phase=phase,
    )
    unit = units["subject"]
    targets = [units[key].unit_instance_id for key in ("enemy", "other", "third")]
    session = LocalGameSession(lifecycle)
    state = lifecycle.state
    assert state is not None
    if phase is BattlePhase.FIGHT:
        policy = state.runtime_ruleset_descriptor().fight_policy
        state.fight_phase_state = FightPhaseState.start(
            battle_round=1,
            active_player_id="player-a",
            policy=policy,
            engaged_at_fight_step_start_unit_ids=(unit.unit_instance_id, *targets),
            fights_first_registry=FightsFirstRegistry(),
        ).with_current_step(current_step=FightPhaseStepKind.FIGHT, policy=policy)
    session.advance_until_decision_or_terminal()
    if pending(session).decision_type == "start_mission_action":
        choose(session, pending(session), "continue_to_shooting")
    if phase is BattlePhase.SHOOTING:
        request = shooting_request(session, unit.unit_instance_id)
    else:
        for _ in range(12):
            request = pending(session)
            if request.decision_type == "submit_melee_declaration":
                break
            if request.decision_type == "select_fight_activation":
                choose(
                    session,
                    request,
                    next(
                        o.option_id for o in request.options if unit.unit_instance_id in o.option_id
                    ),
                )
            else:
                submit_fixture_request(session, request)
        else:
            raise AssertionError("Native melee declaration was not reached")
    assert request.decision_type == (
        "submit_shooting_declaration"
        if phase is BattlePhase.SHOOTING
        else "submit_melee_declaration"
    )
    rows = [
        next(
            row
            for row in weapon_rows(request)
            if row["model_instance_id"] == model.model_instance_id
        )
        for model in unit.own_models
    ]
    if phase is BattlePhase.SHOOTING:
        declare_shooting(session, request, rows, targets)
        assert not _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)
    else:
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
                    "weapon_instance_id": row["weapon_instance_id"],
                    "wargear_id": row["wargear_id"],
                    "weapon_profile_id": row["weapon_profile_id"],
                    "selected_weapon_ability_ids": [],
                    "target_allocations": [{"target_unit_instance_id": target}],
                }
                for row, target in zip(rows, targets, strict=True)
            ],
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=request.request_id + ":native-completion",
            payload=validate_json_value(payload),
        )
        assert status.status_kind.value != "invalid", status
    declared = json.loads(json.dumps(session.to_persistence_payload()))
    restored_declaration = LocalGameSession.from_persistence_payload(declared)
    assert restored_declaration.to_persistence_payload() == declared
    if phase is BattlePhase.SHOOTING:
        premature = json.loads(json.dumps(session.lifecycle.to_payload()))
        premature["state"]["shooting_phase_state"]["shot_unit_ids"] = [unit.unit_instance_id]
        with pytest.raises(GameLifecycleError, match="has-shot inventory"):
            GameLifecycle.from_payload(premature)
    for _ in range(80):
        events = session.lifecycle.decision_controller.event_log.records
        if any(e.event_type == "attack_sequence_models_attacked" for e in events):
            break
        request = pending(session)
        option = next(
            (
                o.option_id
                for o in request.options
                if o.option_id == "resolve-target:army-beta:enemy"
            ),
            request.options[0].option_id,
        )
        choose(session, request, option)
    else:
        raise AssertionError("Native first bearer failed to finish")
    assert not any(e.event_type == "attack_sequence_completed" for e in events)
    assert model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=unit.own_models[0].model_instance_id,
        battle_round=1,
        active_player_id="player-a",
        phase=phase.value,
    )
    assert not model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=unit.own_models[1].model_instance_id,
        battle_round=1,
        active_player_id="player-a",
        phase=phase.value,
    )
    if phase is BattlePhase.SHOOTING:
        assert not _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)
    validate_model_attack_history(event_records=events)
    participation = next(e for e in events if e.event_type == "attack_sequence_models_attacked")
    assert isinstance(participation.payload, dict)
    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    for viewer in state.player_ids:
        public = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert not any(
            event["event_type"] == "attack_sequence_model_completion_state_recorded"
            for event in public["events"]
        )
    forged = replace(
        participation,
        payload={
            **participation.payload,
            "model_instance_ids": [unit.own_models[1].model_instance_id],
        },
    )
    with pytest.raises(GameLifecycleError, match="differs from its declaration"):
        validate_model_attack_history(
            event_records=tuple(forged if e == participation else e for e in events)
        )
    index = events.index(participation)
    with pytest.raises(GameLifecycleError):
        validate_model_attack_history(event_records=(*events, events[index - 1], participation))
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    finish_attacks(fork)
    assert session.to_persistence_payload() == checkpoint
    finish_attacks(session)
    finish_attacks(restored)
    assert (
        restored.to_persistence_payload()
        == session.to_persistence_payload()
        == fork.to_persistence_payload()
    )
    final = json.loads(json.dumps(session.to_persistence_payload()))
    assert LocalGameSession.from_persistence_payload(final).to_persistence_payload() == final
    if phase is BattlePhase.SHOOTING:
        assert _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)
        forged_lifecycle = json.loads(json.dumps(session.lifecycle.to_payload()))
        forged_lifecycle["state"]["shooting_phase_state"]["shot_unit_ids"] = []
        with pytest.raises(GameLifecycleError, match="has-shot inventory"):
            GameLifecycle.from_payload(forged_lifecycle)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="sf04-completion")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_bearer_owned_deferred_damage_prevents_model_completion(
    section04_definitions: Section02Definitions,
    phase: BattlePhase,
) -> None:
    from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
    from warhammer40k_core.engine.deferred_mortal_wounds import DeferredMortalWounds
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.event_log import EventLog, validate_json_value
    from warhammer40k_core.engine.model_attack_completion import (
        MODEL_COMPLETION_STATE_EVENT,
        completed_model_ids,
    )

    original, snapshots, _ = completion_boundaries(
        section04_definitions, phase=phase, multiple_models=True
    )
    sequence, _ = next((s, e) for s, e in snapshots if s.used_pool_indices == (0,))
    pool = original.attack_pools[0]
    assert completed_model_ids(sequence) == {pool.attacker_model_instance_id}
    pending_damage = replace(
        sequence,
        deferred_mortal_wounds=(
            DeferredMortalWounds(
                source_rule_id="rule:04:04.03.04:1",
                source_model_instance_id=pool.attacker_model_instance_id,
                source_weapon_profile=pool.weapon_profile,
                target_unit_instance_id=pool.target_unit_instance_id,
                attack_context_id="s04-boundary:pool-001:attack-001",
                mortal_wounds=1,
            ),
        ),
    )
    assert completed_model_ids(pending_damage) == frozenset()
    assert completed_model_ids(replace(pending_damage, deferred_mortal_wounds=())) == {
        pool.attacker_model_instance_id
    }
    # The new redundant state receipt follows the existing history-neutral policy.
    plain_log, evidence_log = EventLog(), EventLog()
    evidence_log.append(MODEL_COMPLETION_STATE_EVENT, validate_json_value(sequence.to_payload()))
    plain = DiceRollManager("sf04-evidence-neutral", event_log=plain_log)
    with_evidence = DiceRollManager("sf04-evidence-neutral", event_log=evidence_log)
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="sf04-neutral-hit",
        attacker_player_id="owner",
    )
    assert plain.roll(spec).current_values == with_evidence.roll(spec).current_values
    assert plain.rng.to_payload() == with_evidence.rng.to_payload()


@pytest.mark.parametrize("retain", [False, True])
def test_all_attacks_unit_boundary_survives_pending_target_reaction(retain: bool) -> None:
    """Canonical facade kernel; explicit FOD permission, native retention choice."""
    import json

    from tests.retained_attack_helpers import pending_retained_attack
    from warhammer40k_core.engine.damage_allocation import DECLINE_DESTRUCTION_REACTION_OPTION_ID

    session, _ = pending_retained_attack(game_id="sf04-target-reaction")
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert sequence.is_complete
    assert not sequence.deferred_mortal_wounds
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "attack_sequence_attacks_resolved" for e in events)
    assert not any(e.event_type == "attack_sequence_completed" for e in events)
    unit_id = sequence.attacking_unit_instance_id
    assert _unit_has_already_shot(state=state, unit_instance_id=unit_id)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    assert restored.to_persistence_payload() == fork.to_persistence_payload() == checkpoint
    omitted = json.loads(json.dumps(session.lifecycle.to_payload()))
    omitted["state"]["shooting_phase_state"]["shot_unit_ids"] = []
    with pytest.raises(GameLifecycleError, match="has-shot inventory"):
        GameLifecycle.from_payload(omitted)
    for branch in (session, restored, fork):
        request = pending(branch)
        assert request.decision_type == "select_destruction_reaction"
        option = next(
            row.option_id
            for row in request.options
            if (row.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID) is retain
        )
        choose(branch, request, option)
        current = branch.lifecycle.state
        assert current is not None
        assert _unit_has_already_shot(state=current, unit_instance_id=unit_id)
    assert (
        session.to_persistence_payload()
        == restored.to_persistence_payload()
        == fork.to_persistence_payload()
    )
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="sf04-reaction")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("first_hit", [False, True])
def test_native_group_discharge_uses_finished_physical_contributions(
    section04_definitions: Section02Definitions, phase: BattlePhase, first_hit: bool
) -> None:
    """Two native bearers; selected A1 contract, miss or failed wound vs pending damage."""
    from tests.support.section02_consumers import attack_pool
    from tests.support.section02_fixtures import INFRACTORS
    from warhammer40k_core.core.dice import DiceRollResult
    from warhammer40k_core.engine.attack_sequence import (
        AttackSequence,
        attack_sequence_hit_roll_spec,
        attack_sequence_wound_roll_spec,
        resolve_attack_sequence_until_blocked,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.model_attack_completion import (
        completed_model_ids,
        resolved_model_ids,
    )
    from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
    from warhammer40k_core.engine.weapon_instances import (
        equipped_weapon_profile_instances_for_model,
    )

    d = section04_definitions
    attacker = d.unit(INFRACTORS)
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    state = combat_state(
        d,
        attacker,
        target=target,
        distance=8 if phase is BattlePhase.SHOOTING else 2.5,
        phase=phase,
    )
    weapons = [
        next(
            w
            for w in equipped_weapon_profile_instances_for_model(
                model=m, army_catalog=d.package.army_catalog
            )
            if (w.weapon_profile.range_profile.distance_inches is None)
            is (phase is BattlePhase.FIGHT)
        )
        for m in attacker.own_models[:2]
    ]
    pools = tuple(
        replace(
            attack_pool(attacker, target, w.weapon_profile, w.wargear_id),
            attacker_model_instance_id=w.model_instance_id,
            weapon_instance_id=w.weapon_instance_id,
            attacks=1,
        )
        for w in weapons
    )
    sequence = AttackSequence(
        "sf04-shared", "owner", attacker.unit_instance_id, pools, source_phase=phase
    )
    specs = [
        (
            attack_sequence_hit_roll_spec(
                weapon_profile_id=p.weapon_profile_id,
                attack_context_id=f"sf04-shared:pool-001:attack-{i + 1:03d}",
                attacker_player_id="owner",
            ),
            6 if i or first_hit else 1,
        )
        for i, p in enumerate(pools)
    ]
    if first_hit:
        specs.append(
            (
                attack_sequence_wound_roll_spec(
                    weapon_profile_id=pools[0].weapon_profile_id,
                    attack_context_id="sf04-shared:pool-001:attack-001",
                    attacker_player_id="owner",
                ),
                1,
            )
        )
    specs.extend(
        [
            (
                attack_sequence_wound_roll_spec(
                    weapon_profile_id=pools[1].weapon_profile_id,
                    attack_context_id="sf04-shared:pool-001:attack-002",
                    attacker_player_id="owner",
                ),
                6,
            ),
            (
                saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id="opponent",
                    allocated_model_id=target.own_model_ids()[0],
                    attack_context_id="sf04-shared:pool-001:attack-002",
                ),
                1,
            ),
        ]
    )
    decisions = DecisionController()
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "sf04-shared",
            event_log=decisions.event_log,
            injected_results=tuple(
                DiceRollResult.from_values(
                    roll_id=f"sf04:{i}", spec=spec, values=(value,), source="rng"
                )
                for i, (spec, value) in enumerate(specs)
            ),
        ),
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    assert remaining.current_gathered_group is not None
    assert remaining.current_gathered_group.pool_indices == (0, 1)
    assert remaining.pending_grouped_damage is not None
    assert status.decision_request.decision_type == "select_damage_allocation_model"
    events = decisions.event_log.records
    assert completed_model_ids(remaining) == {weapons[0].model_instance_id}
    assert resolved_model_ids(remaining, event_records=events) == {weapons[0].model_instance_id}
    assert model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=weapons[0].model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase=phase.value,
    )
    assert not model_has_attacked_this_phase(
        event_records=events,
        model_instance_id=weapons[1].model_instance_id,
        battle_round=1,
        active_player_id="owner",
        phase=phase.value,
    )
    # A claimed pending inventory cannot replace missing finalized physical steps.
    without_first_steps = tuple(
        e
        for e in events
        if not (
            e.event_type == "attack_sequence_step"
            and isinstance(e.payload, dict)
            and e.payload.get("attack_index") == 0
        )
    )
    assert not resolved_model_ids(remaining, event_records=without_first_steps)
    restored = AttackSequence.from_payload(remaining.to_payload())
    assert restored == remaining
    assert resolved_model_ids(restored, event_records=events) == {weapons[0].model_instance_id}
    # Finalized flags remain bound to the actual interpreted physical dice.
    first_step = next(
        e
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "hit"
        and e.payload.get("attack_index") == 0
    )
    assert isinstance(first_step.payload, dict)
    hit_payload = first_step.payload["payload"]
    assert isinstance(hit_payload, dict)
    forged_step = replace(
        first_step,
        payload={
            **first_step.payload,
            "payload": {**hit_payload, "successful": not hit_payload["successful"]},
        },
    )
    with pytest.raises(GameLifecycleError):
        resolved_model_ids(
            remaining, event_records=tuple(forged_step if e == first_step else e for e in events)
        )


def test_shared_group_pending_damage_valid_save_fork_continue_and_replay() -> None:
    """Small canonical A2 bodies; fixed game identity uses ordinary journal RNG."""
    import json

    from tests.phase13b_shooting_declaration_helpers import (
        _canonical_catalog,
        _compact_intercessor_catalog,
    )
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from tests.support.section04_fixtures import finish_attacks
    from warhammer40k_core.engine.model_attack_history import validate_model_attack_history
    from warhammer40k_core.geometry.pose import Pose

    sheet = "core-intercessor-like-infantry"
    profile = "core-intercessor-like"
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("subject", "spare"),
        enemy_unit_ids=("enemy",),
        origins={"subject": Pose.at(10, 10), "enemy": Pose.at(18, 10), "spare": Pose.at(40, 35)},
        game_id="sf04-group-persistence-2",
        model_count=2,
        alpha_unit_specs={"subject": (sheet, profile, 2), "spare": (sheet, profile, 1)},
        enemy_unit_specs={"enemy": (sheet, profile, 2)},
        poses_by_unit_key={
            "subject": (Pose.at(10, 10), Pose.at(10, 12)),
            "enemy": (Pose.at(18, 10), Pose.at(18, 12)),
            "spare": (Pose.at(40, 35),),
        },
        catalog=_compact_intercessor_catalog(_canonical_catalog()),
        battle_phase=BattlePhase.SHOOTING,
    )
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    if pending(session).decision_type == "start_mission_action":
        choose(session, pending(session), "continue_to_shooting")
    unit = units["subject"]
    request = shooting_request(session, unit.unit_instance_id)
    declare_shooting(session, request, weapon_rows(request), [units["enemy"].unit_instance_id] * 2)
    assert pending(session).decision_type == "select_damage_allocation_model"
    state = lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    assert sequence.current_gathered_group is not None
    assert sequence.current_gathered_group.pool_indices == (0, 1)
    assert sequence.pending_grouped_damage is not None
    events = lifecycle.decision_controller.event_log.records
    assert [
        model_has_attacked_this_phase(
            event_records=events,
            model_instance_id=m.model_instance_id,
            battle_round=1,
            active_player_id="player-a",
            phase="shooting",
        )
        for m in unit.own_models
    ] == [True, False]
    assert not _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)
    validate_model_attack_history(event_records=events)
    missing_steps = tuple(
        e
        for e in events
        if not (
            e.event_type == "attack_sequence_step"
            and isinstance(e.payload, dict)
            and e.payload.get("attack_index") in (0, 1)
        )
    )
    with pytest.raises(GameLifecycleError):
        validate_model_attack_history(event_records=missing_steps)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    finish_attacks(fork)
    assert session.to_persistence_payload() == checkpoint
    finish_attacks(session)
    finish_attacks(restored)
    assert (
        session.to_persistence_payload()
        == restored.to_persistence_payload()
        == fork.to_persistence_payload()
    )
    assert _unit_has_already_shot(state=state, unit_instance_id=unit.unit_instance_id)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="sf04-shared")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
