from __future__ import annotations

from typing import cast

from tests.shared.category_migration.unit_splitting import (
    CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
    GENERIC_RULE_EFFECT_KIND,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE,
    UNIT_SPLIT_CONSUMER_ID,
    ArmyDefinition,
    AttachmentDeclaration,
    BattlePhase,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    Characteristic,
    DamageKind,
    DatasheetAbilityDescriptor,
    DecisionResult,
    EffectExpiration,
    EffectExpirationKind,
    EnhancementAssignment,
    EnhancementDefinition,
    EventStreamCursor,
    FightsFirstRegistry,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    HitRollModifierContext,
    LifecycleStatusKind,
    LocalGameSession,
    MovementMode,
    MovementProposalPayload,
    MovementProposalRequest,
    ObjectiveRuleScope,
    PathWitness,
    PersistingEffect,
    Pose,
    RuleIR,
    RuleIRPayload,
    RuleParameter,
    RuleSourceText,
    RuntimeContentBundle,
    UnitCharacteristicModifierContext,
    WeaponKeyword,
    WeaponProfileModifierContext,
    _attached_split_config_with_enhancement,
    _complete_split,
    _deploy_split_units,
    _move_one_successor,
    _session_at_split,
    _split_config,
    _submit_first,
    apply_damage_to_model,
    blood_legion_ir,
    build_split_army,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    compile_rule_source_text,
    conditional_leading_source_unit_applies,
    conditional_not_leading_source_applies,
    current_enhancement_bearer,
    deadly_demise_modifier_for_model,
    default_unit_selection,
    deployment_placement_payload_for_request,
    enhancement_bearer_model,
    enhancement_bearer_unit,
    generic_rule_hit_roll_modifier,
    generic_rule_modified_unit_characteristic,
    initialize_unit_resource,
    json,
    keyword_source,
    mustered_armies,
    phase11c_config,
    pytest,
    replace,
    rules_unit_views_from_armies,
    runtime_assignment_for_current_bearer,
    straight_line_witness_for_unit,
    unit_resource_ledger_for_unit,
    unit_selection,
    unit_split_permissions,
    validate_attached_rules_unit_identity_after_destruction,
    validate_json_value,
)


@pytest.mark.parametrize("attached", [False, True])
def test_split_choices_use_session_and_checkpoint_round_trip(attached: bool) -> None:
    session = LocalGameSession()
    config = (
        phase11c_config()
        if not attached
        else phase11c_config(
            player_a_units=(
                default_unit_selection("bodyguard"),
                unit_selection(
                    unit_selection_id="leader",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
            ),
            player_a_attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader",
                    bodyguard_unit_selection_id="bodyguard",
                ),
            ),
        )
    )
    session.start(_split_config(config))
    status = session.advance_until_decision_or_terminal()
    while (
        status.decision_request is not None
        and status.decision_request.decision_type != SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
    ):
        _submit_first(session)
        status = session.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
    status = session.submit_option(
        request_id=request.request_id,
        option_id="split",
        result_id="choose-split",
    )
    for _ in range(6 if attached else 5):
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        _submit_first(session)
        status = session.advance_until_decision_or_terminal()
    assert session.lifecycle.state is not None
    assert len(session.lifecycle.state.army_definitions[0].unit_splits) == 1
    assert ":split:" not in json.dumps(session.view(viewer_player_id="player-b"))
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert ":split:" not in json.dumps(
        session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    )
    assert "unit_split_applied" in json.dumps(
        session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    )
    _deploy_split_units(session)
    _move_one_successor(session)
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    persisted = session.to_persistence_payload()
    replayed = LocalGameSession.from_persistence_payload(persisted)
    assert replayed.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert ":split:" in json.dumps(session.view(viewer_player_id="player-b"))
    state = session.lifecycle.state
    split_army = state.army_definitions[0]
    views = rules_unit_views_from_armies(armies=(split_army,))
    assert len(views) == 2
    target = views[1]
    leaders = tuple(c.unit for c in target.components if c.role == "leader")
    for model in target.alive_models():
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=target.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.current_wounds,
            damage_kind=DamageKind.NORMAL,
        )
        if leaders:
            current = rules_unit_views_from_armies(armies=(state.army_definitions[0],))[1]
            leader_alive = any(
                c.unit.alive_own_models() for c in current.components if c.role == "leader"
            )
            bodyguard_alive = any(
                c.unit.alive_own_models() for c in current.components if c.role == "bodyguard"
            )
            assert conditional_not_leading_source_applies(
                state=state,
                source_unit_instance_id=leaders[0].source_unit_instance_id,
            ) is (leader_alive and not bodyguard_alive)
    after = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert not after[1].alive_models()
    assert after[0].alive_models() == views[0].alive_models()
    validate_attached_rules_unit_identity_after_destruction(
        state=state,
        rules_unit_instance_id=target.unit_instance_id,
    )


@pytest.mark.parametrize("selection", [(), (0,), (0, 0), (0, 1, 2, 3, 4)])
def test_split_rejects_incomplete_or_unbalanced_membership(selection: tuple[int, ...]) -> None:
    army = mustered_armies(phase11c_config())[0]
    unit = army.units[0]
    with pytest.raises(GameLifecycleError):
        build_split_army(
            army=army,
            unit_instance_id=unit.unit_instance_id,
            first_model_ids=tuple(unit.own_model_ids()[index] for index in selection),
            request_id="test:split:1",
            source_id="test:authorized-split",
            specified_strengths=None,
        )


@pytest.mark.parametrize("field", ["request_id", "actor_id", "selected_option_id", "payload"])
def test_invalid_split_submission_does_not_pop_or_mutate(field: str) -> None:
    session = _session_at_split()
    request = session.lifecycle.decision_controller.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="invalid-split", request=request, selected_option_id="split"
    )
    invalid = {
        "request_id": replace(result, request_id="stale-request"),
        "actor_id": replace(result, actor_id="player-b"),
        "selected_option_id": replace(result, selected_option_id="invented"),
        "payload": replace(result, payload={"action": "decline"}),
    }[field]
    before = session.lifecycle.to_payload()
    status = session.lifecycle.submit_decision(invalid)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_split_membership_request_authenticates_live_source_models_before_pop() -> None:
    session = _session_at_split()
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definitions[0]
    unit = army.units[0]
    model = unit.own_models[0]
    state.army_definitions[0] = replace(
        army,
        units=(
            replace(unit, own_models=(replace(model, wounds_remaining=1), *unit.own_models[1:])),
        ),
    )
    before = session.lifecycle.to_payload()
    request = session.lifecycle.decision_controller.queue.peek_next()
    status = session.submit_option(
        request_id=request.request_id, option_id="split", result_id="drift"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("field", ["source_rule_id", "army_fingerprint", "first_model_ids", "step"])
def test_split_pending_checkpoint_rejects_source_and_membership_drift(field: str) -> None:
    session = _session_at_split()
    payload = session.lifecycle.to_payload()
    pending = payload["decisions"]["queue"]["pending_requests"][0]["payload"]
    assert isinstance(pending, dict)
    pending[field] = validate_json_value(
        {"first_model_ids": ["foreign-model"], "step": 2}.get(field, "drift")
    )
    with pytest.raises(GameLifecycleError, match=r"split|decision|event"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("target", ["event", "record", "lineage"])
def test_split_checkpoint_authenticates_partition_and_application(target: str) -> None:
    session = _session_at_split()
    _complete_split(session)
    payload = session.lifecycle.to_payload()
    if target == "event":
        event = next(
            e for e in payload["decisions"]["event_log"] if e["event_type"] == "unit_split_applied"
        )
        assert isinstance(event["payload"], dict)
        event["payload"]["player_id"] = "player-b"
    elif target == "record":
        record = next(
            r
            for r in payload["decisions"]["records"]
            if r["request"]["decision_type"] == SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
        )
        record["result"]["selected_option_id"] = "decline"
        record["result"]["payload"] = {"action": "decline"}
    else:
        assert payload["state"] is not None
        army_payload = payload["state"]["army_definitions"][0]
        assert "unit_splits" in army_payload
        army_payload["unit_splits"][0]["first_model_ids"] = ["foreign"]
    with pytest.raises(GameLifecycleError, match=r"split|decision|event|source"):
        GameLifecycle.from_payload(payload)


def test_unit_split_source_artifact_is_registered_complete_and_hash_pinned() -> None:
    from tools.build_core_unit_splitting_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_unit_splitting_2026_09 as source,
    )

    package_payload, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_bytes()) == package_payload
    assert json.loads(AUDIT_PATH.read_bytes()) == audit
    package = source.source_package()
    rules = source.source_rules()
    assert set(package.evidence_required_source_ids) == {rule.source_id for rule in rules}
    assert len(rules) == 2
    for rule in rules:
        assert package.source_catalog.source_text_by_id(rule.source_id).raw_text == rule.source_text
        assert rule.section_id == "01.02.06"
        assert rule.semantic_execution_status == "executable_engine_runtime"
    assert "once" in rules[0].source_text
    assert "Leader/Support" in rules[1].source_text
    assert source.source_evidence_records()
    with pytest.raises(source.UnitSplittingSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_leader_effect_follows_its_source_models_without_granting_to_sibling() -> None:
    session = _session_at_split(
        phase11c_config(
            player_a_units=(
                default_unit_selection("bodyguard"),
                unit_selection(
                    unit_selection_id="leader",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
            ),
            player_a_attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader",
                    bodyguard_unit_selection_id="bodyguard",
                ),
            ),
        )
    )
    state = session.lifecycle.state
    assert state is not None
    (original,) = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    leader = next(c.unit for c in original.components if c.role == "leader")
    bodyguard = next(c.unit for c in original.components if c.role == "bodyguard")
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="test:leader-fights-first",
            source_rule_id="test:leader-source",
            owner_player_id="player-a",
            target_unit_instance_ids=(original.unit_instance_id,),
            started_battle_round=1,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "descriptor_id": CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
                "required_bodyguard_keyword": bodyguard.keywords[0],
                "context": {"source_unit_instance_id": leader.unit_instance_id},
                "effect": {
                    "kind": "grant_ability",
                    "parameters": [{"key": "ability", "value": "fights_first"}],
                },
            },
        )
    )
    _complete_split(session)
    registry = FightsFirstRegistry.from_state(state)
    successors = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert len(registry.sources) == 1
    for view in successors:
        has_leader = any(m in view.own_models for m in leader.own_models)
        assert (
            conditional_leading_source_unit_applies(
                state=state,
                rules_unit_instance_id=view.unit_instance_id,
                source_unit_instance_id=leader.unit_instance_id,
            )
            is has_leader
        )
        assert registry.has_unit(view.unit_instance_id) is has_leader


@pytest.mark.parametrize("drift", ["source", "timing", "parameters", "duplicate"])
def test_split_permissions_fail_closed_on_unsupported_or_drifted_source(drift: str) -> None:
    army = mustered_armies(_split_config())[0]
    unit = army.units[0]
    (permission,) = unit_split_permissions(army)
    ability = next(a for a in unit.datasheet_abilities if a.source_id == permission.source_id)
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    clause = rule.clauses[0]
    assert clause.trigger is not None
    if drift == "source":
        rule = replace(rule, source_id="drifted-source")
    elif drift == "timing":
        rule = replace(
            rule,
            clauses=(
                replace(
                    clause,
                    trigger=replace(
                        clause.trigger,
                        parameters=(RuleParameter("timing_window", "fight"),),
                    ),
                ),
            ),
        )
    elif drift == "parameters":
        rule = replace(
            rule,
            clauses=(
                replace(
                    clause,
                    effects=(
                        replace(
                            clause.effects[0],
                            parameters=(RuleParameter("optional", "yes"),),
                        ),
                    ),
                ),
            ),
        )
    else:
        rule = replace(
            rule, clauses=(clause, replace(clause, clause_id=f"{clause.clause_id}:copy"))
        )
    altered = replace(ability, rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()))
    altered_unit = replace(
        unit,
        datasheet_abilities=tuple(
            altered if a.ability_id == ability.ability_id else a for a in unit.datasheet_abilities
        ),
    )
    with pytest.raises(GameLifecycleError, match=r"split|Split"):
        unit_split_permissions(replace(army, units=(altered_unit,)))


@pytest.mark.parametrize("aura", [False, True])
def test_split_enhancement_follows_live_bearer_and_restores(aura: bool) -> None:
    session = _session_at_split(_attached_split_config_with_enhancement(aura=aura))
    state = session.lifecycle.state
    assert state is not None
    original_assignment = state.army_definitions[0].enhancement_assignments
    original_effects = tuple(e.to_payload() for e in state.persisting_effects)
    _complete_split(session)
    assert tuple(e.to_payload() for e in state.persisting_effects) == original_effects
    _deploy_split_units(session)
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    replayed = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert replayed.lifecycle.to_payload() == session.lifecycle.to_payload()
    for current in (session, restored, replayed):
        state = current.lifecycle.state
        assert state is not None
        assert state.army_definitions[0].enhancement_assignments == original_assignment
        bundle = object.__getattribute__(current.lifecycle, "_runtime_content_bundle")
        assert type(bundle) is RuntimeContentBundle
        assignments = tuple(
            a
            for a in bundle.activation.selected_enhancement_assignments
            if a.player_id == "player-a"
        )
        assert len(assignments) == 1
        assert assignments[0].target_unit_selection_id == "leader"
        profile = next(
            w
            for w in current.lifecycle.config.army_catalog.wargear
            if w.wargear_id == ("core-leader-blade" if aura else "core-bolt-rifle")
        ).weapon_profiles[0]
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            contains_leader = any(
                c.unit.source_unit_instance_id == "army-alpha:leader" for c in view.components
            )
            selected = runtime_assignment_for_current_bearer(
                state=state,
                player_id="player-a",
                assignments=assignments,
                unit_instance_id=view.unit_instance_id,
            )
            assert selected == (assignments[0] if contains_leader else None)
            for model in view.alive_models():
                if aura:
                    modified = bundle.runtime_modifier_registry.modified_weapon_profile(
                        WeaponProfileModifierContext(
                            state=state,
                            attacking_unit_instance_id=view.unit_instance_id,
                            attacker_model_instance_id=model.model_instance_id,
                            target_unit_instance_id=state.army_definitions[1]
                            .units[0]
                            .unit_instance_id,
                            weapon_profile=profile,
                            source_phase=BattlePhase.FIGHT,
                        )
                    )
                    assert (WeaponKeyword.LANCE in modified.keywords) is contains_leader
                    continue
                value = bundle.runtime_modifier_registry.hit_roll_modifier(
                    HitRollModifierContext(
                        state=state,
                        attacking_unit_instance_id=view.unit_instance_id,
                        attacker_model_instance_id=model.model_instance_id,
                        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
                        weapon_profile=profile,
                        source_phase=BattlePhase.SHOOTING,
                    )
                )
                assert value == (1 if contains_leader else 0)
    if aura:
        state = replayed.lifecycle.state
        assert state is not None
        army = state.army_definitions[0]
        bearer = enhancement_bearer_unit(army, assignment=original_assignment[0])
        assert bearer.unit_instance_id != "army-alpha:leader"
        model = bearer.own_models[0]
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=bearer.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.current_wounds,
            damage_kind=DamageKind.NORMAL,
        )
        current_bearer = enhancement_bearer_unit(
            state.army_definitions[0], assignment=original_assignment[0]
        )
        assert not current_bearer.own_models[0].is_alive
        assert army.source_unit_by_id("army-alpha:leader").own_models[0].is_alive
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            modified = bundle.runtime_modifier_registry.modified_weapon_profile(
                WeaponProfileModifierContext(
                    state=state,
                    attacking_unit_instance_id=view.unit_instance_id,
                    attacker_model_instance_id=view.alive_models()[0].model_instance_id,
                    target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
                    weapon_profile=profile,
                    source_phase=BattlePhase.FIGHT,
                )
            )
            assert WeaponKeyword.LANCE not in modified.keywords


def test_split_deadly_demise_enhancement_keeps_source_and_current_model_ownership() -> None:
    config = _attached_split_config_with_enhancement(aura=True)
    enhancement_id = blood_legion_ir.GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID
    config = replace(
        config,
        army_catalog=replace(
            config.army_catalog,
            enhancements=(
                EnhancementDefinition(
                    enhancement_id=enhancement_id,
                    name="Gateway unto Damnation",
                    points=10,
                    source_id=blood_legion_ir.GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID,
                ),
            ),
            detachments=tuple(
                replace(d, enhancement_ids=(enhancement_id,))
                for d in config.army_catalog.detachments
            ),
            datasheets=tuple(
                replace(d, keywords=replace(d.keywords, keywords=(*d.keywords.keywords, "Monster")))
                if d.datasheet_id == "core-character-leader"
                else d
                for d in config.army_catalog.datasheets
            ),
        ),
        army_muster_requests=(
            replace(
                config.army_muster_requests[0],
                enhancement_assignments=(
                    replace(
                        config.army_muster_requests[0].enhancement_assignments[0],
                        enhancement_id=enhancement_id,
                    ),
                ),
            ),
            config.army_muster_requests[1],
        ),
    )
    session = _session_at_split(config)
    state = session.lifecycle.state
    assert state is not None
    model_id = (
        state.army_definitions[0].unit_by_id("army-alpha:leader").own_models[0].model_instance_id
    )
    original = deadly_demise_modifier_for_model(state=state, model_instance_id=model_id)
    assert original is not None
    _complete_split(session)
    for current in (
        session,
        session.fork(),
        LocalGameSession.from_persistence_payload(session.to_persistence_payload()),
    ):
        assert current.lifecycle.to_payload() == session.lifecycle.to_payload()
        state = current.lifecycle.state
        assert state is not None
        assert deadly_demise_modifier_for_model(state=state, model_instance_id=model_id) == original
        assert original.source_unit_instance_id == "army-alpha:leader"
        assert state.unit_instance_id_for_model(model_id) != original.source_unit_instance_id
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            for model in view.own_models:
                if model.model_instance_id != model_id:
                    assert (
                        deadly_demise_modifier_for_model(
                            state=state, model_instance_id=model.model_instance_id
                        )
                        is None
                    )


__all__: list[str] = []
__all__ += ["ArmyDefinition", "CatalogAbilitySourceKind", "CatalogAbilitySupport"]
__all__ += ["Characteristic", "DatasheetAbilityDescriptor", "EffectExpirationKind"]
__all__ += ["EnhancementAssignment", "GameConfig", "GameLifecycleStage", "MovementMode"]
__all__ += ["MovementProposalPayload", "MovementProposalRequest", "ObjectiveRuleScope"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "PathWitness", "Pose", "RuleSourceText"]
__all__ += ["UNIT_SPLIT_CONSUMER_ID", "UnitCharacteristicModifierContext"]
__all__ += ["catalog_rule_ir_consumers_for_rule", "catalog_rule_ir_hook_ids_for_rule"]
__all__ += ["compile_rule_source_text", "current_enhancement_bearer"]
__all__ += ["deployment_placement_payload_for_request", "enhancement_bearer_model"]
__all__ += ["generic_rule_hit_roll_modifier", "generic_rule_modified_unit_characteristic"]
__all__ += ["initialize_unit_resource", "keyword_source", "straight_line_witness_for_unit"]
__all__ += ["unit_resource_ledger_for_unit"]
