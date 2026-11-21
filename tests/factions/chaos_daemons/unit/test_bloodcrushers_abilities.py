from __future__ import annotations

from tests.factions.chaos_daemons.consumer_helpers import (
    CRUSHERS,
    LORD,
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
    begin,
    cast,
    casualty_checkpoint,
    choose,
    events,
    json,
    locate,
    propose,
    pytest,
    replace,
    request,
    roll,
    scene,
    selection,
    targets,
    witness,
)


def test_brass_stampede_native_charge_completion(
    faction_definitions: Section02Definitions, tmp_path: Path
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (
            selection(d, CRUSHERS, "crushers", equipment=("instrument-of-chaos",)),
            selection(d, CRUSHERS, "spare"),
        ),
        (selection(d, CRUSHERS, "target"),),
        phase=BattlePhase.CHARGE,
    )
    unit = s.units["own:crushers"]
    target = s.units["foe:target"]
    locate(s, unit.unit_instance_id, tuple(Pose.at(10, 10 + i * 2.5) for i in range(3)))
    locate(s, target.unit_instance_id, tuple(Pose.at(16, 10 + i * 2.5) for i in range(3)))
    anchor(s)
    r = begin(s.session)
    choose(s.session, unit.unit_instance_id)
    targets(s.session, (target.unit_instance_id,))
    result = roll(s.session)
    assert result.value == result.request.resolve_roll(result.roll_state).unmodified.value + 1
    status = propose(
        s.session,
        unit.unit_instance_id,
        (target.unit_instance_id,),
        witness(s.state, unit.unit_instance_id, 2.0),
    )
    r = request(status)
    assert r.decision_type == "select_catalog_unit_move_completed_mortal_wounds_target"
    assert isinstance(r.payload, dict)
    assert r.payload["roll_model_instance_ids"] == list(unit.own_model_ids())
    assert r.payload["available_target_unit_instance_ids"] == [target.unit_instance_id]
    assert str(r.payload["source_rule_id"]).endswith("Datasheets_abilities:000001115:5")
    valid = DecisionResult.for_request(
        result_id="stampede:target",
        request=r,
        selected_option_id=r.options[0].option_id,
    )
    for bad in (replace(valid, actor_id="opponent"), replace(valid, payload={})):
        before = s.session.lifecycle.to_payload()
        invalid = s.session.lifecycle.submit_decision(bad)
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert s.session.lifecycle.to_payload() == before
    phase = s.state.battle_phase_index
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.FIGHT)
    before = s.session.lifecycle.to_payload()
    assert s.session.lifecycle.submit_decision(valid).status_kind is LifecycleStatusKind.INVALID
    assert s.session.lifecycle.to_payload() == before
    s.state.battle_phase_index = phase
    board = s.state.battlefield_state
    locate(s, target.unit_instance_id, tuple(Pose.at(30, 10 + i * 2.5) for i in range(3)))
    before = s.session.lifecycle.to_payload()
    assert s.session.lifecycle.submit_decision(valid).status_kind is LifecycleStatusKind.INVALID
    assert s.session.lifecycle.to_payload() == before
    assert board is not None
    s.state.replace_battlefield_state(board)
    saved = json.loads(json.dumps(s.session.to_persistence_payload()))
    (tmp_path / "stampede-pending.json").write_text(json.dumps(saved, indent=2), encoding="utf8")
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    branch = s.session.fork()
    before_hp = sum(m.current_wounds for m in target.own_models)
    for current in (s.session, restored, branch):
        status = current.submit_option(
            request_id=r.request_id,
            option_id=r.options[0].option_id,
            result_id="stampede:accepted",
        )
        for i in range(30):
            if (
                status.decision_request is None
                or status.decision_request.decision_type != "select_mortal_wound_model"
            ):
                break
            child = status.decision_request
            status = current.submit_option(
                request_id=child.request_id,
                option_id=child.options[0].option_id,
                result_id=f"stampede:allocate:{i}",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            pytest.fail("Brass Stampede allocation did not terminate")
        request(status, "select_charging_unit")
        rolled = events(current, "unit_move_completed_mortal_wounds_rolled")
        assert len(rolled) == 3
        assert {
            cast(
                str,
                cast(dict[str, JsonValue], row["replay_payload"])["roll_model_instance_id"],
            )
            for row in rolled
        } == set(unit.own_model_ids())
        resolved = events(current, "unit_move_completed_mortal_wounds_resolved")
        damage = sum(cast(int, row["mortal_wounds"]) for row in resolved)
        assert damage > 0
        assert current.lifecycle.state is not None
        live_target = next(
            u
            for a in current.lifecycle.state.army_definitions
            for u in a.units
            if u.unit_instance_id == target.unit_instance_id
        )
        assert sum(m.current_wounds for m in live_target.own_models) == before_hp - damage
        assert len(events(current, "charge_move_completed")) == 1
        assert (
            len(events(current, "catalog_unit_move_completed_mortal_wounds_target_selected")) == 1
        )
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="stampede"))
            .run()
            .reproduced_exactly
        )
    assert (
        restored.lifecycle.to_payload()
        == branch.lifecycle.to_payload()
        == s.session.lifecycle.to_payload()
    )
    for viewer in ("owner", "opponent"):
        view = s.session.view(viewer_player_id=viewer)
        assert json.loads(json.dumps(view)) == view


@pytest.mark.parametrize("bearer_alive", [True, False])
def test_instrument_changes_native_charge_roll_only_while_physical_bearer_lives(
    faction_definitions: Section02Definitions, bearer_alive: bool
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (
            selection(d, CRUSHERS, "crushers", equipment=("instrument-of-chaos",)),
            selection(d, CRUSHERS, "spare"),
        ),
        (selection(d, LORD, "target"),),
        phase=BattlePhase.CHARGE,
    )
    unit = s.units["own:crushers"]
    bearer = next(m for m in unit.own_models if f"{CRUSHERS}:instrument-of-chaos" in m.wargear_ids)
    assert sum(f"{CRUSHERS}:instrument-of-chaos" in m.wargear_ids for m in unit.own_models) == 1
    locate(s, unit.unit_instance_id, tuple(Pose.at(10, 10 + i * 2.5) for i in range(3)))
    locate(s, "foe:target", (Pose.at(15, 10),))
    if not bearer_alive:
        casualty_checkpoint(s, (bearer.model_instance_id,))
    begin(s.session)
    choose(s.session, unit.unit_instance_id)
    result = roll(s.session)
    unmodified = result.request.resolve_roll(result.roll_state).unmodified.value
    assert result.value == unmodified + int(bearer_alive)
    assert len(result.request.roll_modifiers) == int(bearer_alive)
    assert result.request.spec.expression.modifier == 0
    assert (
        events(s.session, "charge_roll_resolved")[-1]["unit_instance_id"] == unit.unit_instance_id
    )


@pytest.mark.parametrize("bearer_alive", [True, False])
def test_icon_leadership_query_uses_current_physical_bearer(
    faction_definitions: Section02Definitions, bearer_alive: bool
) -> None:
    from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests

    d = faction_definitions
    s = scene(
        d,
        (selection(d, CRUSHERS, "crushers", equipment=("daemonic-icon",)),),
        (selection(d, LORD, "target"),),
        phase=BattlePhase.COMMAND,
    )
    unit = s.units["own:crushers"]
    bearer = next(m for m in unit.own_models if f"{CRUSHERS}:daemonic-icon" in m.wargear_ids)
    nonbearers = [m for m in unit.own_models if m != bearer]
    assert len(nonbearers) == 2
    surviving = bearer if bearer_alive else nonbearers[0]
    casualty_checkpoint(s, tuple(m.model_instance_id for m in unit.own_models if m != surviving))
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    assert s.state.battlefield_state is not None
    army = next(a for a in s.state.army_definitions if a.player_id == "owner")
    baseline = collect_battle_shock_test_requests(
        game_id=s.state.game_id,
        battle_round=1,
        player_id="owner",
        army=army,
        battlefield_state=s.state.battlefield_state,
        starting_strength_records=tuple(s.state.starting_strength_records),
        battle_shocked_unit_ids=(),
    )
    loaded = collect_battle_shock_test_requests(
        game_id=s.state.game_id,
        battle_round=1,
        player_id="owner",
        army=army,
        battlefield_state=s.state.battlefield_state,
        starting_strength_records=tuple(s.state.starting_strength_records),
        battle_shocked_unit_ids=(),
        ability_index=bundle.ability_indexes_by_player_id["owner"],
    )
    assert len(baseline) == len(loaded) == 1
    assert baseline[0].leadership_target == 7
    assert loaded[0].leadership_target == (6 if bearer_alive else 7)
    assert s.state.battlefield_state is not None
    assert tuple(
        p.model_instance_id
        for p in s.state.battlefield_state.unit_placement_by_id(
            unit.unit_instance_id
        ).model_placements
    ) == (surviving.model_instance_id,)


def test_v995_contextual_shadow_aura_applies_only_to_friendly_khorne_units_in_range() -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
        datasheets,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.rule_aura_resolution import aura_affected_unit_ids
    from warhammer40k_core.rules.rule_ir import RuleConditionKind, RuleParameter

    definitions = _v995_shadow_definitions()
    s = scene(
        definitions,
        (
            selection(definitions, "000002582", "bloodthirster"),
            selection(definitions, CRUSHERS, "khorne"),
            selection(definitions, CRUSHERS, "distant"),
            selection(definitions, "000001120", "tzeentch"),
        ),
        (selection(definitions, CRUSHERS, "khorne"),),
    )
    locate(s, "own:bloodthirster", (Pose.at(22, 30),))
    locate(s, "own:khorne", tuple(Pose.at(25, 27 + 3 * i) for i in range(3)))
    locate(s, "own:distant", tuple(Pose.at(40, 27 + 3 * i) for i in range(3)))
    locate(s, "own:tzeentch", (Pose.at(18, 30),))
    locate(s, "foe:khorne", tuple(Pose.at(24, 35 + 3 * i) for i in range(3)))
    before = s.state.to_payload()

    expected = {
        "foe:khorne": False,
        "own:tzeentch": False,
        "own:distant": False,
        "own:khorne": True,
    }
    assert {
        target: army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
            state=s.state, player_id="owner", unit_instance_id=target
        )
        for target in expected
    } == expected
    bloodthirster = s.units["own:bloodthirster"]
    ability = next(
        ability
        for ability in bloodthirster.datasheet_abilities
        if ability.ability_id == datasheets.BLOODTHIRSTER_GREATER_DAEMON_ABILITY_ID
    )
    rule_ir = army_rule._semantic_rule_ir_for_ability(ability)  # pyright: ignore[reportPrivateUsage]
    [clause] = rule_ir.clauses
    assert clause.target is not None
    malformed_target = replace(
        clause.target,
        parameters=tuple(p for p in clause.target.parameters if p.key == "allegiance"),
    )
    with pytest.raises(GameLifecycleError, match="matching target and condition keywords"):
        aura_affected_unit_ids(
            clause=replace(clause, target=malformed_target),
            state=s.state,
            source_unit_instance_id=bloodthirster.unit_instance_id,
            source_model_instance_id=bloodthirster.own_models[0].model_instance_id,
            target_unit_instance_id="foe:khorne",
        )
    [distance] = (
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    for parameter in (
        RuleParameter("object_allegiance", "enemy"),
        RuleParameter("subject", "this_model"),
    ):
        malformed_distance = replace(distance, parameters=(*distance.parameters, parameter))
        with pytest.raises(GameLifecycleError, match="positive, unqualified within range"):
            aura_affected_unit_ids(
                clause=replace(
                    clause,
                    conditions=tuple(
                        malformed_distance if condition is distance else condition
                        for condition in clause.conditions
                    ),
                ),
                state=s.state,
                source_unit_instance_id=bloodthirster.unit_instance_id,
                source_model_instance_id=bloodthirster.own_models[0].model_instance_id,
                target_unit_instance_id="foe:khorne",
            )
    first_gate = next(c for c in clause.conditions if c.kind is RuleConditionKind.KEYWORD_GATE)
    malformed_gate = replace(first_gate, parameters=(RuleParameter("required_keyword", None),))
    with pytest.raises(GameLifecycleError, match="matching target and condition keywords"):
        aura_affected_unit_ids(
            clause=replace(clause, conditions=(*clause.conditions, malformed_gate)),
            state=s.state,
            source_unit_instance_id=bloodthirster.unit_instance_id,
            source_model_instance_id=bloodthirster.own_models[0].model_instance_id,
            target_unit_instance_id="foe:khorne",
        )
    [effect] = clause.effects
    malformed_effect = replace(
        effect,
        parameters=(*effect.parameters, RuleParameter("operation", "deny")),
    )
    with pytest.raises(GameLifecycleError, match="unsupported effect"):
        army_rule._semantic_shadow_aura_targets(  # pyright: ignore[reportPrivateUsage]
            rule_ir=replace(rule_ir, clauses=(replace(clause, effects=(malformed_effect,)),)),
            state=s.state,
            source_unit_instance_id=bloodthirster.unit_instance_id,
            source_model_instance_id=bloodthirster.own_models[0].model_instance_id,
            target_unit_instance_id="foe:khorne",
        )
    assert s.state.to_payload() == before


@pytest.mark.parametrize("near_greater_daemon", [False, True])
def test_v995_opposing_command_battle_shock_resolves_with_qualified_terror(
    near_greater_daemon: bool,
) -> None:
    from tests.support.battle_shock_batch04 import health
    from warhammer40k_core.adapters.access_control import ViewerContext
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.direct_mortal_wound_application import (
        apply_direct_mortal_wounds_to_unit,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    definitions = _v995_shadow_definitions()
    s = scene(
        definitions,
        (selection(definitions, "000002582", "bloodthirster"),),
        (selection(definitions, "000001120", "lord-of-change"),),
        phase=BattlePhase.COMMAND,
        active="opponent",
        seed="v995-contextual-shadow",
    )
    target_id = "foe:lord-of-change"
    locate(s, "own:bloodthirster", (Pose.at(23 if near_greater_daemon else 8, 33),))
    locate(s, target_id, (Pose.at(28, 33),))
    anchor(s)
    apply_direct_mortal_wounds_to_unit(
        state=s.state,
        decisions=s.session.lifecycle.decision_controller,
        application_id="fixture:v995-contextual-shadow-prior-wounds",
        source_rule_id="fixture:v995-contextual-shadow-prior-wounds:source",
        source_context={"source_kind": "fixture_preexisting_casualties"},
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=s.state,
            destroying_player_id="owner",
            source_rules_unit_instance_id=None,
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.COMMAND,
            source_step="fixture_preexisting_casualties",
        ),
        target_unit_instance_id=target_id,
        mortal_wounds=10,
    )
    assert health(s.session, target_id) == 8
    request(s.session.advance_until_decision_or_terminal(), "submit_stratagem_target_proposal")
    view = s.session.view(viewer_player_id="opponent")
    pending = view["pending_decision"]
    assert pending is not None
    assert pending["decision_type"] == "submit_stratagem_target_proposal"
    status = s.session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player("opponent"),
        request_id=pending["request_id"],
        payload=stratagem_decline_payload(),
        result_id="v995-contextual-shadow:decline",
    )
    request(status, "select_movement_unit")
    assert not army_rule.unit_within_shadow_of_chaos(
        state=s.state, player_id="owner", unit_instance_id=target_id
    )
    [resolved] = events(s.session, "battle_shock_test_resolved")
    result = resolved["battle_shock_result"]
    assert isinstance(result, dict)
    modified = result["modified_roll"]
    assert isinstance(modified, dict)
    modifiers = modified["modifiers"]
    assert isinstance(modifiers, list)
    assert [cast(dict[str, JsonValue], m)["operand"] for m in modifiers] == (
        [-1] if near_greater_daemon else []
    )
    assert all(
        cast(dict[str, JsonValue], m)["source_id"] == army_rule.JULY_SOURCE_RULE_ID
        for m in modifiers
    )
    assert result["passed"] is (not near_greater_daemon)
    reactions = events(s.session, "chaos_daemons_daemonic_terror_mortal_wounds_applied")
    if near_greater_daemon:
        [reaction] = reactions
        assert reaction["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID
        assert reaction["player_id"] == "owner"
        assert reaction["target_unit_instance_id"] == target_id
        d3 = reaction["d3_result"]
        assert isinstance(d3, dict)
        amount = d3["value"]
        assert type(amount) is int
        assert health(s.session, target_id) == 8 - amount
    else:
        assert reactions == []
        assert health(s.session, target_id) == 8


def _v995_shadow_definitions() -> Section02Definitions:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        chaos_daemons_cavalcade_2026_11,
    )

    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    catalog = package.army_catalog
    # The bounded fixture uses asymmetric force dispositions in a shared mission.
    detachments = tuple(
        replace(
            d, force_disposition_ids=(*d.force_disposition_ids, "take-and-hold", "purge-the-foe")
        )
        if d.detachment_id == "cavalcade-of-chaos"
        else d
        for d in catalog.detachments
    )
    return Section02Definitions(
        replace(package, army_catalog=replace(catalog, detachments=detachments)), 0.0
    )
