from __future__ import annotations

from tests.factions.chaos_daemons.consumer_helpers import (
    CRUSHERS,
    BattlePhase,
    DecisionResult,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    Path,
    Pose,
    ReplayRunner,
    Section02Definitions,
    anchor,
    cast,
    events,
    json,
    locate,
    pytest,
    replace,
    request,
    scene,
    selection,
)


@pytest.mark.parametrize("inside", [True, False])
@pytest.mark.parametrize("seed", [0, 2])
def test_batch04_native_shadow_terror_commits_damage_only_on_failed_test(
    faction_definitions: Section02Definitions, inside: bool, seed: int
) -> None:
    from tests.support.battle_shock_batch04 import (
        command_scene,
        decline_bravery,
        health,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )

    s = command_scene(
        faction_definitions,
        inside=inside,
        seed=seed,
        rng_seed_label="b04-2:terror:private-0" if seed == 2 else None,
    )
    assert (
        army_rule.unit_within_shadow_of_chaos(
            state=s.state, player_id="owner", unit_instance_id="foe:target"
        )
        is inside
    )
    before = health(s.session, "foe:target")
    status = decline_bravery(s)
    results = events(s.session, "battle_shock_test_resolved")
    assert len(results) == 1
    outcome = results[0]["battle_shock_result"]
    assert isinstance(outcome, dict)
    modified = outcome["modified_roll"]
    assert isinstance(modified, dict)
    modifiers = modified["modifiers"]
    assert isinstance(modifiers, list)
    assert all(isinstance(m, dict) for m in modifiers)
    typed_modifiers = [cast(dict[str, JsonValue], m) for m in modifiers]
    assert [m["operand"] for m in typed_modifiers] == ([-1] if inside else [])
    assert all(m["source_id"] == army_rule.JULY_SOURCE_RULE_ID for m in typed_modifiers)
    assert outcome["passed"] is (seed == 2 or not inside)
    if inside and seed == 0:
        r = request(status, "select_mortal_wound_model")
        count = len(s.session.lifecycle.decision_controller.records)
        status = s.session.submit_option(
            request_id=r.request_id,
            option_id=r.options[0].option_id,
            result_id="b04:terror",
        )
        assert len(s.session.lifecycle.decision_controller.records) == count + 1
        applied = events(s.session, "chaos_daemons_daemonic_terror_mortal_wounds_applied")
        assert len(applied) == 1
        assert applied[0]["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID
        assert applied[0]["player_id"] == "owner"
        assert applied[0]["target_unit_instance_id"] == "foe:target"
        d3 = applied[0]["d3_result"]
        assert isinstance(d3, dict)
        amount = d3["value"]
        assert type(amount) is int
        assert health(s.session, "foe:target") == max(0, before - amount)
    else:
        assert events(s.session, "chaos_daemons_daemonic_terror_mortal_wounds_applied") == []
        assert health(s.session, "foe:target") == before
    request(status, "select_movement_unit")
    assert s.state.stratagem_use_records == []
    assert len(events(s.session, "battle_shock_test_resolved")) == 1


def test_batch04_terror_pending_authority_atomic_retry_restore_fork_and_exact_replay(
    faction_definitions: Section02Definitions, tmp_path: Path
) -> None:
    from copy import deepcopy

    from tests.support.battle_shock_batch04 import (
        command_scene,
        decline_bravery,
        health,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError

    s = command_scene(faction_definitions)
    # Explicit replay origin after the recorded prior-casualty premise. That
    # fixture history predates this test's facade choices and is not replay credit.
    s.session._initial_replay_lifecycle_payload = deepcopy(  # pyright: ignore[reportPrivateUsage]
        s.session.lifecycle.to_payload()
    )
    r = request(decline_bravery(s), "select_mortal_wound_model")
    valid = DecisionResult.for_request(
        result_id="b04:terror-accepted",
        request=r,
        selected_option_id=r.options[0].option_id,
    )
    for invalid in (replace(valid, actor_id="owner"), replace(valid, payload={})):
        before = s.session.lifecycle.to_payload()
        assert (
            s.session.lifecycle.submit_decision(invalid).status_kind is LifecycleStatusKind.INVALID
        )
        assert s.session.lifecycle.to_payload() == before
    phase = s.state.battle_phase_index
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.FIGHT)
    before = s.session.lifecycle.to_payload()
    assert s.session.lifecycle.submit_decision(valid).status_kind is LifecycleStatusKind.INVALID
    assert s.session.lifecycle.to_payload() == before
    s.state.battle_phase_index = phase
    saved = json.loads(json.dumps(s.session.to_persistence_payload()))
    (tmp_path / "terror-pending.json").write_text(json.dumps(saved), encoding="utf8")

    # Corrupt one causal source field at a time; do not replace a controller or
    # fabricate provider registration. Each load starts from the valid checkpoint.
    def corrupt(value: JsonValue, key: str, expected: JsonValue, replacement: JsonValue) -> bool:
        if isinstance(value, dict):
            if value.get(key) == expected:
                value[key] = replacement
                return True
            return any(corrupt(v, key, expected, replacement) for v in value.values())
        if isinstance(value, list):
            return any(corrupt(v, key, expected, replacement) for v in value)
        return False

    for key, expected, replacement in (
        ("source_kind", "chaos_daemons_daemonic_terror", "wrong-provider"),
        ("source_step", "daemonic_terror_mortal_wounds", "wrong-step"),
    ):
        drifted = deepcopy(saved)
        assert corrupt(drifted, key, expected, replacement)
        with pytest.raises(GameLifecycleError):
            LocalGameSession.from_persistence_payload(drifted)
    restored = LocalGameSession.from_persistence_payload(saved)
    fork = s.session.fork()
    assert restored.to_persistence_payload() == saved
    for current in (s.session, restored, fork):
        before_health = health(current, "foe:target")
        request(
            current.submit_option(
                request_id=r.request_id,
                option_id=r.options[0].option_id,
                result_id="b04:terror-accepted",
            ),
            "select_movement_unit",
        )
        assert health(current, "foe:target") < before_health
        assert len(events(current, "chaos_daemons_daemonic_terror_mortal_wounds_applied")) == 1
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="b04-terror"))
            .run()
            .reproduced_exactly
        )
    assert (
        s.session.lifecycle.to_payload()
        == restored.lifecycle.to_payload()
        == fork.lifecycle.to_payload()
    )


@pytest.mark.parametrize(("inside", "wounded"), [(True, True), (True, False), (False, True)])
def test_batch04_manifestation_native_healing_consumes_shadow_and_health_boundary(
    faction_definitions: Section02Definitions, inside: bool, wounded: bool
) -> None:
    from tests.support.battle_shock_batch04 import (
        command_scene,
        decline_bravery,
        health,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )

    s = command_scene(
        faction_definitions,
        manifestation=True,
        inside=inside,
        wounded=wounded,
        seed=2,
        rng_seed_label="b04-2:manifestation:private-11",
    )
    before = health(s.session, "own:daemon")
    status = decline_bravery(s)
    request(status, "select_movement_unit")
    resolved = events(s.session, "battle_shock_test_resolved")
    assert len(resolved) == 1
    result = resolved[0]["battle_shock_result"]
    assert isinstance(result, dict)
    # This fixed native roll reaches Leadership only with Manifestation's +1.
    assert result["passed"] is inside
    modified = result["modified_roll"]
    assert isinstance(modified, dict)
    modifiers = modified["modifiers"]
    assert isinstance(modifiers, list)
    assert all(isinstance(m, dict) for m in modifiers)
    assert [cast(dict[str, JsonValue], m)["operand"] for m in modifiers] == ([1] if inside else [])
    healed = events(s.session, "chaos_daemons_daemonic_manifestation_healing_resolved")
    if inside and wounded:
        assert len(healed) == 1
        assert healed[0]["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID
        assert healed[0]["unit_instance_id"] == "own:daemon"
        d3 = healed[0]["d3_result"]
        assert isinstance(d3, dict)
        amount = d3["value"]
        assert type(amount) is int
        assert health(s.session, "own:daemon") == min(4, before + amount)
    else:
        assert healed == []
        assert health(s.session, "own:daemon") == before
        assert len(events(s.session, "chaos_daemons_daemonic_manifestation_no_effect")) == int(
            inside
        )
    assert events(s.session, "chaos_daemons_daemonic_terror_mortal_wounds_applied") == []


def test_manifestation_history_survives_the_tested_units_later_destruction(
    faction_definitions: Section02Definitions,
) -> None:
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from tests.support.battle_shock_batch04 import command_scene, decline_bravery, health
    from warhammer40k_core.engine.battle_shock_event_authority import (
        validate_battle_shock_runtime_content_authority,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    s = command_scene(
        faction_definitions,
        manifestation=True,
        seed=2,
        rng_seed_label="b04-2:manifestation:private-11",
    )
    unit_id = "own:daemon"
    assert health(s.session, unit_id) == 1
    request(decline_bravery(s), "select_movement_unit")
    tested = rules_unit_view_by_id(state=s.state, unit_instance_id=unit_id)
    assert army_rule.LEGIONES_DAEMONICA in tested.faction_keywords
    (survivor,) = tested.alive_models()
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    decisions = s.session.lifecycle.decision_controller
    destroy_models_with_recorded_mortal_wounds(
        state=s.state,
        decisions=decisions,
        unit_instance_id=unit_id,
        model_instance_ids=(survivor.model_instance_id,),
        application_id="fixture:later-casualty",
        destroying_player_id="opponent",
    )
    assert health(s.session, unit_id) == 0
    assert not rules_unit_view_by_id(state=s.state, unit_instance_id=unit_id).faction_keywords

    events = decisions.event_log.records
    validate_battle_shock_runtime_content_authority(
        state=s.state,
        event_records=events,
        decision_records=decisions.records,
        runtime_content_bundle=bundle,
    )

    (recorded,) = (
        event
        for event in events
        if event.event_type == "battle_shock_modifier_applications_recorded"
    )
    assert isinstance(recorded.payload, dict)
    assert recorded.payload["battle_shock_modifier_applications"]
    tampered = replace(
        recorded, payload={**recorded.payload, "battle_shock_modifier_applications": []}
    )
    with pytest.raises(GameLifecycleError, match="modifier application authority drifted"):
        validate_battle_shock_runtime_content_authority(
            state=s.state,
            event_records=tuple(tampered if event is recorded else event for event in events),
            decision_records=decisions.records,
            runtime_content_bundle=bundle,
        )


def test_batch04_command_start_bravery_validates_owner_phase_target_before_spend(
    faction_definitions: Section02Definitions,
) -> None:
    from tests.support.battle_shock_batch04 import command_scene, health
    from tests.support.section15_fixtures import submit

    s = command_scene(faction_definitions)
    r = request(
        s.session.advance_until_decision_or_terminal(),
        "submit_stratagem_target_proposal",
    )
    hp = health(s.session, "foe:target")
    assert s.state.command_point_total("opponent") == 1
    before = s.session.lifecycle.to_payload()
    assert (
        submit(s.session, r, "own:daemon", player="owner").status_kind
        is LifecycleStatusKind.INVALID
    )
    assert s.session.lifecycle.to_payload() == before
    phase = s.state.battle_phase_index
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.FIGHT)
    before = s.session.lifecycle.to_payload()
    assert (
        submit(s.session, r, "foe:target", player="opponent").status_kind
        is LifecycleStatusKind.INVALID
    )
    assert s.session.lifecycle.to_payload() == before
    s.state.battle_phase_index = phase
    request(submit(s.session, r, "foe:target", player="opponent"), "select_movement_unit")
    assert s.state.command_point_total("opponent") == 0
    assert s.state.command_point_total("owner") == 1
    assert len(s.state.stratagem_use_records) == 1
    use = s.state.stratagem_use_records[0]
    assert use.stratagem_id == "insane-bravery"
    assert use.targeted_unit_instance_ids == ("foe:target",)
    outcomes = events(s.session, "battle_shock_test_resolved")
    assert len(outcomes) == 1
    assert outcomes[0]["auto_passed"] is True
    assert health(s.session, "foe:target") == hp
    assert events(s.session, "chaos_daemons_daemonic_terror_mortal_wounds_applied") == []


@pytest.mark.parametrize(
    ("opposing_control", "omit_terror"),
    [(False, False), (True, False), (True, True)],
)
def test_later_daemon_casualty_still_requires_historical_territorial_terror(
    faction_definitions: Section02Definitions,
    monkeypatch: pytest.MonkeyPatch,
    opposing_control: bool,
    omit_terror: bool,
) -> None:
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from tests.support.battle_shock_batch04 import decline_bravery
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.direct_mortal_wound_application import (
        apply_direct_mortal_wounds_to_unit,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError

    d = faction_definitions
    s = scene(
        d,
        (selection(d, CRUSHERS, "subject"),),
        (selection(d, CRUSHERS, "controller"),),
        phase=BattlePhase.COMMAND,
        seed="b04-2",
        rng_seed_label="b04-2:territory:private-2",
    )
    mission = s.state.mission_setup
    assert mission is not None
    (zone,) = (zone for zone in mission.deployment_zones if zone.player_id == "owner")
    (marker,) = (
        marker
        for marker in mission.objective_markers
        if zone.contains_point(marker.x_inches, marker.y_inches)
    )
    subject = s.units["own:subject"]
    locate(
        s,
        subject.unit_instance_id,
        tuple(Pose.at(marker.x_inches, marker.y_inches + 7 + 2.5 * index) for index in range(3)),
    )
    if opposing_control:
        locate(
            s,
            "foe:controller",
            tuple(
                Pose.at(marker.x_inches, marker.y_inches + 2.5 * index - 2.5) for index in range(3)
            ),
        )
    assert (
        army_rule.unit_within_shadow_of_chaos(
            state=s.state, player_id="opponent", unit_instance_id=subject.unit_instance_id
        )
        is opposing_control
    )
    anchor(s)
    decisions = s.session.lifecycle.decision_controller
    destroy_models_with_recorded_mortal_wounds(
        state=s.state,
        decisions=decisions,
        unit_instance_id=subject.unit_instance_id,
        model_instance_ids=subject.own_model_ids()[1:],
        application_id="fixture:territorial-terror-prior-casualties",
        destroying_player_id="opponent",
    )
    with monkeypatch.context() as patch:
        if omit_terror:
            # Generate every linked result and trigger identity through the native
            # path so restore reaches the independent historical comparison.
            def without_terror(**_kwargs: object) -> bool:
                return False

            patch.setattr(army_rule, "_daemonic_terror_applies", without_terror)
        status = decline_bravery(s)
    request(status, "select_movement_unit")
    (event,) = events(s.session, "battle_shock_test_resolved")
    result = cast(dict[str, JsonValue], event["battle_shock_result"])
    assert result["passed"] is True
    roll = cast(dict[str, JsonValue], result["modified_roll"])
    modifiers = cast(list[dict[str, JsonValue]], roll["modifiers"])
    assert [row["operand"] for row in modifiers] == (
        [1, -1] if opposing_control and not omit_terror else [1]
    )
    casualties = apply_direct_mortal_wounds_to_unit(
        state=s.state,
        decisions=decisions,
        application_id="fixture:territorial-terror-later-casualty",
        source_rule_id="fixture:territorial-terror-later-casualty:source",
        source_context={"source_kind": "fixture_preexisting_casualties"},
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=s.state,
            destroying_player_id="opponent",
            source_rules_unit_instance_id="foe:controller",
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.MOVEMENT,
            source_step="fixture_preexisting_casualties",
        ),
        target_unit_instance_id=subject.unit_instance_id,
        mortal_wounds=subject.own_models[0].current_wounds,
    )
    assert casualties.applications[-1].destroyed
    payload = s.session.lifecycle.to_payload()
    if omit_terror:
        with pytest.raises(GameLifecycleError, match="incomplete or context-invalid"):
            GameLifecycle.from_payload(payload)
    else:
        assert GameLifecycle.from_payload(payload).to_payload() == payload


@pytest.mark.parametrize(
    ("territory", "premise", "expected_shadow"),
    [
        ("no_mans_land", "one_of_three", False),
        ("no_mans_land", "two_of_three", True),
        ("no_mans_land", "exact_half", True),
        ("no_mans_land", "contested", False),
        ("no_mans_land", "enemy_controlled", False),
        ("opponent_deployment_zone", "controlled", True),
        ("opponent_deployment_zone", "enemy_controlled", False),
    ],
)
def test_controlled_territory_drives_loaded_manifestation_roll(
    faction_definitions: Section02Definitions,
    territory: str,
    premise: str,
    expected_shadow: bool,
) -> None:
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from tests.support.battle_shock_batch04 import decline_bravery
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlContext,
        ObjectiveControlStatus,
        ObjectiveControlTiming,
        resolve_objective_control,
    )

    d = faction_definitions
    s = scene(
        d,
        tuple(selection(d, CRUSHERS, name) for name in ("subject", "first", "second")),
        (selection(d, CRUSHERS, "defender"),),
        phase=BattlePhase.COMMAND,
        seed="b04-2",
        rng_seed_label="b04-2:territory:private-1",
    )
    assert s.state.mission_setup is not None
    mission = s.state.mission_setup
    neutral = [
        marker
        for marker in mission.objective_markers
        if not any(
            zone.contains_point(marker.x_inches, marker.y_inches)
            for zone in mission.deployment_zones
        )
    ]
    assert len(neutral) == 3
    if premise == "exact_half":
        # Explicit two-objective component layout, not a canonical mission claim.
        s.state.mission_setup = replace(
            mission,
            deployment_map_id="daemons-control:two-neutral-objectives",
            terrain_layout_id="daemons-control:two-neutral-objectives",
            objective_markers=tuple(m for m in mission.objective_markers if m != neutral[2]),
        )
        neutral = neutral[:2]
    if territory == "no_mans_land":
        region_markers = neutral
        subject_x, subject_y = 36.0, 22.0
    else:
        region_markers = [
            marker
            for marker in mission.objective_markers
            if any(
                zone.player_id == "opponent"
                and zone.contains_point(marker.x_inches, marker.y_inches)
                for zone in mission.deployment_zones
            )
        ]
        assert len(region_markers) == 1
        subject_x, subject_y = 46.0, 22.0

    def place(unit_id: str, x: float, y: float) -> None:
        locate(s, unit_id, tuple(Pose.at(x, y + i * 2.5) for i in range(3)))

    place("own:subject", subject_x, subject_y)
    place("own:first", 10, 10)
    place("own:second", 10, 25)
    place("foe:defender", 55, 5)
    contested = premise == "contested"
    enemy = premise == "enemy_controlled"
    first = region_markers[0]
    if territory == "no_mans_land" or not enemy:
        place("own:first", first.x_inches, first.y_inches - 2.5)
    if premise == "two_of_three" or contested:
        second = region_markers[1]
        place("own:second", second.x_inches, second.y_inches - 2.5)
    if contested or enemy:
        defended = region_markers[1] if territory == "no_mans_land" else first
        # Matching real Bloodcrusher OC; opposite sides avoid physical overlap.
        place(
            "foe:defender", defended.x_inches + (3.0 if contested else 0.0), defended.y_inches - 2.5
        )
        if contested:
            place("own:second", defended.x_inches - 3.0, defended.y_inches - 2.5)
    anchor(s)
    subject = s.units["own:subject"]
    destroy_models_with_recorded_mortal_wounds(
        state=s.state,
        decisions=s.session.lifecycle.decision_controller,
        unit_instance_id=subject.unit_instance_id,
        model_instance_ids=subject.own_model_ids()[1:],
        application_id="fixture:controlled-territory-casualties",
        destroying_player_id="opponent",
    )
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            s.state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        )
    )
    results = tuple(record.result_by_objective_id(m.objective_marker_id) for m in region_markers)
    controlled = sum(r.controlled_by_player_id == "owner" for r in results)
    assert controlled == (
        2 if premise == "two_of_three" else 0 if enemy and territory != "no_mans_land" else 1
    )
    if contested or enemy:
        defended_result = results[1] if territory == "no_mans_land" else results[0]
        assert defended_result.status is (
            ObjectiveControlStatus.CONTESTED if contested else ObjectiveControlStatus.CONTROLLED
        )
        assert defended_result.controlled_by_player_id == (None if contested else "opponent")
        assert {score.player_id: score.score for score in defended_result.scores} == (
            {"owner": 6, "opponent": 6} if contested else {"opponent": 6}
        )
    for result in results:
        if result.controlled_by_player_id == "owner":
            assert {score.player_id: score.score for score in result.scores} == {"owner": 6}
    assert (controlled * 2 >= len(results)) is expected_shadow
    region = army_rule.ShadowRegion(territory)
    assert (
        region in army_rule.shadow_regions_for_player(state=s.state, player_id="owner")
    ) is expected_shadow
    assert (
        army_rule.unit_within_shadow_of_chaos(
            state=s.state, player_id="owner", unit_instance_id=subject.unit_instance_id
        )
        is expected_shadow
    )
    request(decline_bravery(s), "select_movement_unit")
    resolved = events(s.session, "battle_shock_test_resolved")
    assert len(resolved) == 1
    outcome = resolved[0]["battle_shock_result"]
    assert isinstance(outcome, dict)
    modified = outcome["modified_roll"]
    assert isinstance(modified, dict)
    modifiers = modified["modifiers"]
    assert isinstance(modifiers, list)
    expected_modifiers = ([1] if expected_shadow else []) + (
        [-1] if territory == "opponent_deployment_zone" else []
    )
    assert [cast(dict[str, JsonValue], m)["operand"] for m in modifiers] == expected_modifiers
    assert all(
        cast(dict[str, JsonValue], m)["source_id"] == army_rule.JULY_SOURCE_RULE_ID
        for m in modifiers
    )
    unmodified = modified["unmodified"]
    assert isinstance(unmodified, dict)
    raw_value = unmodified["value"]
    assert type(raw_value) is int
    assert modified["final_value"] == raw_value + sum(expected_modifiers)
    final_value, leadership = modified["final_value"], outcome["leadership_target"]
    assert type(final_value) is int
    assert type(leadership) is int
    assert outcome["passed"] is (final_value >= leadership)
    if territory == "no_mans_land" and premise != "enemy_controlled":
        assert outcome["passed"] is expected_shadow
