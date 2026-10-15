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


def test_split_preserves_selected_membership_and_model_identity() -> None:
    army = mustered_armies(phase11c_config())[0]
    original = army.units[0]
    selected = original.own_model_ids()[::2]
    split = build_split_army(
        army=army,
        unit_instance_id=original.unit_instance_id,
        first_model_ids=selected,
        request_id="test:split:1",
        source_id="test:authorized-split",
        specified_strengths=None,
    )
    assert len(split.units) == 2
    assert split.units[0].own_model_ids() == selected
    assert sorted(model for unit in split.units for model in unit.own_model_ids()) == sorted(
        original.own_model_ids()
    )
    assert {model for unit in split.units for model in unit.own_models} == set(original.own_models)
    assert split.unit_splits[0].source_unit_instance_id == original.unit_instance_id
    assert ArmyDefinition.from_payload(json.loads(json.dumps(split.to_payload()))) == split


def test_split_models_cannot_be_subdivided_again_or_reassigned_without_lineage() -> None:
    army = mustered_armies(phase11c_config())[0]
    original = army.units[0]
    split = build_split_army(
        army=army,
        unit_instance_id=original.unit_instance_id,
        first_model_ids=original.own_model_ids()[:2],
        request_id="test:split:1",
        source_id="test:authorized-split",
        specified_strengths=None,
    )
    with pytest.raises(GameLifecycleError, match="already"):
        build_split_army(
            army=split,
            unit_instance_id=split.units[0].unit_instance_id,
            first_model_ids=split.units[0].own_model_ids()[:1],
            request_id="test:split:2",
            source_id="test:authorized-split",
            specified_strengths=None,
        )
    with pytest.raises(GameLifecycleError, match=r"lineage|split"):
        replace(split, unit_splits=())


@pytest.mark.parametrize("extra_models", [0, 1, 2])
def test_ten_model_source_and_attached_leader_support_balancing(extra_models: int) -> None:
    selections = [
        unit_selection(
            unit_selection_id="bodyguard",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=10,
        )
    ]
    attachments: list[AttachmentDeclaration] = []
    for role in ("leader", "support")[:extra_models]:
        selections.append(
            unit_selection(
                unit_selection_id=role,
                datasheet_id=f"core-character-{role}",
                model_profile_id=f"core-character-{role}",
                model_count=1,
            )
        )
        attachments.append(
            AttachmentDeclaration(
                source_unit_selection_id=role,
                bodyguard_unit_selection_id="bodyguard",
            )
        )
    session = _session_at_split(
        phase11c_config(
            player_a_units=tuple(selections),
            player_a_attachment_declarations=tuple(attachments),
        )
    )
    _complete_split(session)
    state = session.lifecycle.state
    assert state is not None
    record = state.army_definitions[0].unit_splits[0]
    assert record.used_balanced_fallback is (extra_models > 0)
    assert tuple(len(record.model_ids(i)) for i in (0, 1)) == (
        (10 + extra_models + 1) // 2,
        (10 + extra_models) // 2,
    )
    views = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert sum(len(v.own_models) for v in views) == 10 + extra_models
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


def test_split_preserves_existing_effects_and_one_resource_account() -> None:
    session = _session_at_split()
    state = session.lifecycle.state
    assert state is not None
    original_id = state.army_definitions[0].units[0].unit_instance_id
    effect = PersistingEffect(
        effect_id="test:static-fights-first",
        source_rule_id="test:static-source",
        owner_player_id="player-a",
        target_unit_instance_ids=(original_id,),
        started_battle_round=1,
        expiration=EffectExpiration(EffectExpirationKind.END_OF_BATTLE),
        effect_payload={"effect_kind": "fights_first"},
    )
    state.record_persisting_effect(effect)
    initialize_unit_resource(
        state=state,
        player_id="player-a",
        unit_instance_id=original_id,
        resource_kind="test:token",
        amount=1,
        source_rule_id="test:resource",
    )
    _complete_split(session)
    successors = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    registry = FightsFirstRegistry.from_state(state)
    for view in successors:
        assert state.persisting_effects_for_unit(view.unit_instance_id) == (effect,)
        assert registry.has_unit(view.unit_instance_id)
        ledger = unit_resource_ledger_for_unit(state=state, unit_instance_id=view.unit_instance_id)
        assert ledger is not None
        assert ledger.unit_instance_id == original_id
        assert ledger.total("test:token") == 1
    assert len(state.unit_resource_ledgers) == 1
    with pytest.raises(GameLifecycleError, match="ambiguous membership"):
        conditional_not_leading_source_applies(state=state, source_unit_instance_id=original_id)


def test_order70_native_fights_first_footprint_follows_split_models_and_restore() -> None:
    from warhammer40k_core.engine.fights_first import fights_first_model_inventory
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    config = phase11c_config()
    ability = DatasheetAbilityDescriptor(
        ability_id="core-fights-first",
        name="Fights First",
        source_id="order70:split-native",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.CORE,
        effect_description="Intrinsic component Fights First.",
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(row, abilities=(*row.abilities, ability))
            if row.datasheet_id == "core-intercessor-like-infantry"
            else row
            for row in config.army_catalog.datasheets
        ),
    )
    session = _session_at_split(replace(config, army_catalog=catalog))
    _complete_split(session)
    state = session.lifecycle.state
    assert state is not None
    registry = FightsFirstRegistry.from_state(state)
    views = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert len(views) == 2
    footprints: list[set[str]] = []
    for identity in views:
        view = rules_unit_view_by_id(state=state, unit_instance_id=identity.unit_instance_id)
        present, grants = fights_first_model_inventory(state=state, view=view)
        assert registry.has_unit(view.unit_instance_id)
        assert {m for _, ids in grants for m in ids} == set(present)
        footprints.append(set(present))
    assert footprints[0].isdisjoint(footprints[1])
    restored = session.fork().lifecycle.state
    assert restored is not None
    assert FightsFirstRegistry.from_state(restored) == registry


def test_core_splitting_rule_grants_no_permission_and_catalog_consumer_is_registered() -> None:
    assert unit_split_permissions(mustered_armies(phase11c_config())[0]) == ()
    army = mustered_armies(_split_config())[0]
    (permission,) = unit_split_permissions(army)
    ability = next(
        a for a in army.units[0].datasheet_abilities if a.source_id == permission.source_id
    )
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    assert UNIT_SPLIT_CONSUMER_ID in catalog_rule_ir_consumers_for_rule(rule)
    assert UNIT_SPLIT_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(rule)


@pytest.mark.parametrize("include_component_aliases", [False, True])
def test_retained_attack_grant_follows_split_predecessor_once_per_model(
    include_component_aliases: bool,
) -> None:
    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.destruction_reaction_kind import DestructionReactionKind
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.retained_attack_grants import persisted_retained_attack_sources
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        retained_attack_sources_2026_09 as retained_sources,
    )

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
    rule = retained_sources.rule_ir_for_source(retained_sources.UNENDING_FIDELITY_SOURCE_ID)
    clause = rule.clauses[0]
    targets = (
        (original.unit_instance_id, *original.component_unit_instance_ids)
        if include_component_aliases
        else (original.unit_instance_id,)
    )
    effect = generic_effect(
        effect_id="test:retained-predecessor-grant",
        owner_player_id="player-a",
        target_unit_instance_ids=targets,
        target_kind="selected_unit",
        effect_kind="grant_ability",
        parameters={},
    )
    payload = effect.effect_payload
    assert isinstance(payload, dict)
    payload = {
        **payload,
        "effect": cast(JsonValue, clause.effects[0].to_payload()),
        "rule_ir_hash": rule.ir_hash(),
        "clause_id": clause.clause_id,
    }
    effect = replace(
        effect,
        source_rule_id=rule.source_id,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=payload,
    )
    state.record_persisting_effect(effect)
    _complete_split(session)
    checkpoint = session.lifecycle.to_payload()
    restored = GameLifecycle.from_payload(checkpoint)
    assert restored.to_payload() == checkpoint
    state = restored.state
    assert state is not None
    successors = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    assert len(successors) == 2
    for view in successors:
        assert view.unit_instance_id != original.unit_instance_id
        for model in view.own_models:
            sources = persisted_retained_attack_sources(
                state=state, model_instance_id=model.model_instance_id
            )
            assert len(sources) == 1, (view.unit_instance_id, model.model_instance_id)
            assert sources[0].reaction_kind is DestructionReactionKind.SHOOT_OR_FIGHT_ON_DEATH
            assert sources[0].source_rule_id == rule.source_id
    opponent = state.army_definitions[1].units[0].own_models[0]
    assert not persisted_retained_attack_sources(
        state=state, model_instance_id=opponent.model_instance_id
    )


def test_enhancement_bearer_rejects_foreign_roster_assignment_and_source() -> None:
    army = mustered_armies(_attached_split_config_with_enhancement())[0]
    assignment = army.enhancement_assignments[0]
    with pytest.raises(GameLifecycleError, match="not in the owning army"):
        enhancement_bearer_unit(army, assignment=replace(assignment, source_id="foreign"))
    with pytest.raises(GameLifecycleError, match="unknown bearer unit"):
        current_enhancement_bearer(army, source_unit_instance_id="foreign:leader")


@pytest.mark.parametrize("target_scope", ["unit", "leader_model", "multiple_aliases"])
def test_split_generic_numerical_effects_apply_after_restore(target_scope: str) -> None:
    config = _attached_split_config_with_enhancement()
    config = replace(
        config,
        army_muster_requests=(
            replace(config.army_muster_requests[0], enhancement_assignments=()),
            config.army_muster_requests[1],
        ),
    )
    session = _session_at_split(config)
    state = session.lifecycle.state
    assert state is not None
    (original,) = rules_unit_views_from_armies(armies=(state.army_definitions[0],))
    leader = next(c.unit for c in original.components if c.role == "leader")
    model_id = leader.own_models[0].model_instance_id
    whole_unit = target_scope != "leader_model"
    targets = (
        (original.unit_instance_id, *original.component_unit_instance_ids)
        if target_scope == "multiple_aliases"
        else (original.unit_instance_id if whole_unit else leader.unit_instance_id,)
    )
    for kind, parameters in (
        ("modify_dice_roll", [{"key": "roll_type", "value": "hit"}, {"key": "delta", "value": 1}]),
        (
            "modify_characteristic",
            [
                {"key": "characteristic", "value": "movement"},
                {"key": "delta", "value": 2},
            ],
        ),
    ):
        state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"test:split:{kind}",
                source_rule_id="test:split-numerical",
                owner_player_id="player-a",
                target_unit_instance_ids=targets,
                started_battle_round=1,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload={
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "source_id": "test:split-numerical",
                    "rule_id": "test:split-numerical",
                    "rule_ir_hash": "test:split-hash",
                    "clause_id": f"test:{kind}",
                    "effect_index": 0,
                    "target": {"kind": "this_unit" if whole_unit else "this_model"},
                    "effect": {"kind": kind, "parameters": validate_json_value(parameters)},
                    "conditions": [],
                    "context": {"source_model_instance_id": model_id},
                },
            )
        )
    before_effects = tuple(e.to_payload() for e in state.persisting_effects)
    _complete_split(session)
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for current in (session, restored):
        state = current.lifecycle.state
        assert state is not None
        assert tuple(e.to_payload() for e in state.persisting_effects) == before_effects
        profile = current.lifecycle.config.army_catalog.wargear[0].weapon_profiles[0]
        for view in rules_unit_views_from_armies(armies=(state.army_definitions[0],)):
            for model in view.alive_models():
                assert generic_rule_modified_unit_characteristic(
                    UnitCharacteristicModifierContext(
                        state=state,
                        unit_instance_id=view.unit_instance_id,
                        model_instance_id=model.model_instance_id,
                        characteristic=Characteristic.MOVEMENT,
                        base_value=6,
                        current_value=6,
                    )
                ) == (8 if whole_unit or model.model_instance_id == model_id else 6)
                assert generic_rule_hit_roll_modifier(
                    HitRollModifierContext(
                        state=state,
                        attacking_unit_instance_id=view.unit_instance_id,
                        attacker_model_instance_id=model.model_instance_id,
                        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
                        weapon_profile=profile,
                        source_phase=BattlePhase.SHOOTING,
                    )
                ) == (1 if whole_unit or model.model_instance_id == model_id else 0)


def test_order68_explicit_nonfirst_bearer_retains_identity_after_split_and_restore() -> None:
    config = _attached_split_config_with_enhancement()
    request = config.army_muster_requests[0]
    assignment = replace(
        request.enhancement_assignments[0],
        target_unit_selection_id="bodyguard",
        model_profile_id="core-intercessor-like",
        model_index=2,
    )
    config = replace(
        config,
        army_muster_requests=(
            replace(request, enhancement_assignments=(assignment,)),
            config.army_muster_requests[1],
        ),
    )
    session = _session_at_split(config)
    assert session.lifecycle.state is not None
    before = enhancement_bearer_model(
        session.lifecycle.state.army_definitions[0], assignment=assignment
    )
    assert before.model_instance_id == "army-alpha:bodyguard:core-intercessor-like:002"
    _complete_split(session)
    restored = session.fork()
    assert restored.lifecycle.state is not None
    army = restored.lifecycle.state.army_definitions[0]
    after = enhancement_bearer_model(army, assignment=assignment)
    assert after.model_instance_id == before.model_instance_id
    owner = enhancement_bearer_unit(army, assignment=assignment)
    assert owner.unit_instance_id != "army-alpha:bodyguard"
    assert after.model_instance_id in owner.own_model_ids()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()


__all__: list[str] = []
__all__ += ["CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID", "CatalogJsonObject", "DamageKind"]
__all__ += ["DecisionResult", "EnhancementAssignment", "EnhancementDefinition"]
__all__ += ["EventStreamCursor", "GameConfig", "GameLifecycleStage", "LifecycleStatusKind"]
__all__ += ["LocalGameSession", "MovementMode", "MovementProposalPayload"]
__all__ += ["MovementProposalRequest", "ObjectiveRuleScope", "PathWitness", "Pose"]
__all__ += ["RuleParameter", "RuleSourceText", "RuntimeContentBundle"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE"]
__all__ += ["WeaponKeyword", "WeaponProfileModifierContext", "_deploy_split_units"]
__all__ += ["_move_one_successor", "_submit_first", "apply_damage_to_model", "blood_legion_ir"]
__all__ += ["compile_rule_source_text", "conditional_leading_source_unit_applies"]
__all__ += ["deadly_demise_modifier_for_model", "deployment_placement_payload_for_request"]
__all__ += ["keyword_source", "runtime_assignment_for_current_bearer"]
__all__ += ["straight_line_witness_for_unit"]
__all__ += ["validate_attached_rules_unit_identity_after_destruction"]
