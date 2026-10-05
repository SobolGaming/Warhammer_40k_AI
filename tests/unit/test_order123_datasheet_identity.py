"""Selected Core datasheet identity survives the shared keyword ownership path."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.model_keyword_helpers import mixed_keyword_catalog, mixed_keyword_unit

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_keywords import model_keyword_assignment
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.catalog_model_scope import scoped_roll_model_ids_for_effect
from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword


def test_name_is_normalized_once_without_rewriting_retained_catalog_keywords() -> None:
    from warhammer40k_core.engine.list_validation import UnitMusterSelection
    from warhammer40k_core.engine.unit_factory import UnitFactory
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    assert sheet.name_keyword == "CORE INTERCESSOR-LIKE INFANTRY"
    assert sheet.name_keyword not in sheet.keywords.keywords
    assert ArmyCatalog.from_payload(catalog.to_payload()) == catalog
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="order123-identity-army",
        datasheet=sheet,
        selection=UnitMusterSelection(
            unit_selection_id="name-keyword",
            datasheet_id=sheet.datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(
                    model_profile_id=row.model_profile_id, model_count=row.min_models
                )
                for row in sheet.composition
            ),
        ),
    )
    assert unit_has_keyword(unit, sheet.name_keyword)
    assert all(sheet.name_keyword in model.keywords for model in unit.own_models)
    assert unit.keywords.count(sheet.name_keyword) == 1
    renamed = replace(unit, name="Player display alias")
    assert unit_has_keyword(renamed, sheet.name_keyword)
    assert not unit_has_keyword(renamed, renamed.name)
    assert all("SPECIALIST" not in model.keywords for model in unit.own_models)
    assert UnitInstance.from_payload(unit.to_payload()) == unit


@pytest.mark.parametrize("explicit", [False, True])
def test_scoped_and_materialization_assignments_add_only_datasheet_identity(explicit: bool) -> None:
    catalog = mixed_keyword_catalog()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    sheet = replace(
        sheet,
        keywords=replace(
            sheet.keywords,
            keywords=tuple(k for k in sheet.keywords.keywords if k != sheet.name_keyword),
        ),
    )
    assignments = tuple(
        replace(
            row,
            keywords=tuple(k for k in row.keywords if k != sheet.name_keyword),
            name_keyword=None,
        )
        for row in catalog.model_keyword_assignments
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
        model_keyword_assignments=assignments,
    )
    row = catalog.model_keyword_assignments[0]
    variant = replace(row, materialization_descriptor_id="order123-variant")
    assignment = model_keyword_assignment(
        datasheet=sheet,
        model_profile_id=row.model_profile_id,
        assignments=(*catalog.model_keyword_assignments, variant) if explicit else (),
        materialization_descriptor_id="order123-variant" if explicit else None,
    )
    assert sheet.name_keyword in assignment.keywords
    assert assignment.keywords.count(sheet.name_keyword) == 1
    if explicit:
        assert sheet.name_keyword not in variant.keywords
        assert assignment.source_ids == variant.source_ids
        assert assignment.materialization_descriptor_id == "order123-variant"
        assert set(assignment.keywords) == {*variant.keywords, sheet.name_keyword}


def test_live_model_scope_keeps_identity_after_specialist_casualty() -> None:
    unit = mixed_keyword_unit()
    token = "CORE INTERCESSOR-LIKE INFANTRY"
    specialist = next(model for model in unit.own_models if "PSYKER" in model.keywords)
    unit = replace(
        unit,
        own_models=tuple(
            replace(model, wounds_remaining=0) if model == specialist else model
            for model in unit.own_models
        ),
    )
    view = RulesUnitView(
        unit_instance_id=unit.unit_instance_id,
        owner_player_id="player-a",
        components=(RulesUnitComponent(unit=unit, role="unit"),),
    )
    assert token in view.keywords
    assert "PSYKER" not in view.keywords
    living = tuple(model.model_instance_id for model in unit.own_models if model.is_alive)
    assert scoped_roll_model_ids_for_effect(
        source_rules_unit=view,
        current_roll_model_instance_ids=tuple(m.model_instance_id for m in unit.own_models),
        effect_parameters={"required_model_keyword": token},
    ) == tuple(sorted(living))
    assert (
        scoped_roll_model_ids_for_effect(
            source_rules_unit=view,
            current_roll_model_instance_ids=living,
            effect_parameters={"required_model_keyword": "SPECIALIST"},
        )
        == ()
    )


@pytest.mark.parametrize("name", ["INFANTRY", "Be'lakor", "Lord of Change", "Name-with-hyphens"])
def test_identity_keeps_native_keyword_punctuation_and_deduplicates(name: str) -> None:
    from warhammer40k_core.engine.army_mustering import datasheet_has_keyword

    sheet = ArmyCatalog.phase9a_canonical_content_pack().datasheets[0]
    sheet = replace(sheet, name=name)
    assert sheet.name_keyword == name.upper()
    assert sheet.effective_keywords.count(name.upper()) == 1
    assert datasheet_has_keyword(sheet, name)
    assert not datasheet_has_keyword(sheet, "UNRELATED NAME")
    assert "name_keyword" not in sheet.to_payload()
    assert "effective_keywords" not in sheet.to_payload()


def test_official_admitted_catalog_already_has_names_and_preserves_reconciliation() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        chaos_daemons_roster_2026_07 as source,
    )

    package = source.catalog_package()
    source.validate_catalog_against_reconciliation(
        catalog=package.army_catalog, reconciliation=source.reconciliation_manifest()
    )
    assert len(package.army_catalog.datasheets) == 5
    for sheet in package.army_catalog.datasheets:
        assert sheet.name_keyword in sheet.keywords.keywords
        assert sheet.effective_keywords == sheet.keywords.keywords
        for profile in sheet.model_profiles:
            assignment = model_keyword_assignment(
                datasheet=sheet,
                model_profile_id=profile.model_profile_id,
                assignments=package.army_catalog.model_keyword_assignments,
            )
            assert sheet.name_keyword in assignment.keywords
            assert assignment.keywords.count(sheet.name_keyword) == 1


def test_catalog_name_transport_and_enhancement_gates_share_identity() -> None:
    from warhammer40k_core.adapters.projection import project_rules_catalog_view
    from warhammer40k_core.engine import army_mustering, list_validation
    from warhammer40k_core.engine.army_mustering import DedicatedTransportCapacityProfile
    from warhammer40k_core.engine.list_validation import BattleSizeMusteringPolicy
    from warhammer40k_core.engine.roster_unit_limits import datasheet_unit_limit

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    token = sheet.name_keyword
    assert token not in sheet.keywords.keywords
    ordinary = replace(
        sheet,
        keywords=replace(
            sheet.keywords,
            keywords=tuple(
                keyword
                for keyword in sheet.keywords.keywords
                if keyword not in {"BATTLELINE", "DEDICATED TRANSPORT"}
            ),
        ),
    )
    strike = BattleSizeMusteringPolicy.strike_force()
    onslaught = BattleSizeMusteringPolicy.onslaught()
    assert datasheet_unit_limit(ordinary, policy=strike) == strike.unit_limit
    for name in ("BATTLELINE", "DEDICATED TRANSPORT"):
        named = replace(ordinary, name=name)
        assert name not in named.keywords.keywords
        assert named.effective_keywords.count(name) == 1
        assert datasheet_unit_limit(named, policy=strike) == strike.battleline_unit_limit
        assert datasheet_unit_limit(named, policy=onslaught) == (
            onslaught.battleline_unit_limit if name == "BATTLELINE" else onslaught.unit_limit
        )
    for query in (
        army_mustering._datasheet_has_any_keyword,
        list_validation._datasheet_has_any_keyword,
    ):
        assert query(sheet, frozenset({token}))
        assert not query(sheet, frozenset({"OTHER DATASHEET"}))
    profile = DedicatedTransportCapacityProfile(
        transport_datasheet_id="core-dedicated-transport",
        max_model_count=12,
        allowed_keywords=(token,),
        excluded_keywords=(),
        source_id="core-permission:order123:name-capacity",
    )
    assert army_mustering._transport_capacity_allows_datasheet(profile, sheet)
    assert not army_mustering._transport_capacity_allows_datasheet(
        replace(profile, excluded_keywords=(token,)), sheet
    )
    assert not army_mustering._transport_capacity_allows_datasheet(
        replace(profile, allowed_keywords=("OTHER DATASHEET",)), sheet
    )
    view = project_rules_catalog_view(catalog=catalog)
    assert token in view["datasheet_display_by_id"][sheet.datasheet_id]["keywords"]


def test_materialized_model_keeps_datasheet_identity_despite_distinct_model_label() -> None:
    from warhammer40k_core.engine.unit_factory import UnitFactory

    catalog = mixed_keyword_catalog()
    row = catalog.model_keyword_assignments[0]
    variant = replace(row, materialization_descriptor_id="order123-source-variant")
    catalog = replace(
        catalog, model_keyword_assignments=(*catalog.model_keyword_assignments, variant)
    )
    model = UnitFactory(catalog=catalog).instantiate_materialized_model(
        datasheet_id=row.datasheet_id,
        model_profile_id=row.model_profile_id,
        model_instance_id="order123-returned-model",
        model_name="Returned model display label",
        wargear_ids=(),
        source_id="core-permission:order123:materialized",
        materialization_descriptor_id="order123-source-variant",
    )
    assert "CORE INTERCESSOR-LIKE INFANTRY" in model.keywords
    assert "RETURNED MODEL DISPLAY LABEL" not in model.keywords
    assert model.keyword_assignment == variant


@pytest.mark.integration
@pytest.mark.parametrize("activate", [True, False])
def test_loaded_lifecycle_identity_pending_continuation_fork_viewers_and_exact_replay(
    activate: bool,
) -> None:
    from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
    from tests.order122_helpers import (
        advance_to_default_grant,
        default_effect_session,
        submit_quiet_choice,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext
    from warhammer40k_core.engine.rule_target_resolution import (
        effect_clause_target_unavailable_reason,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleEffectKind,
        RuleEffectSpec,
        RuleParameter,
        RuleTargetKind,
        RuleTargetSpec,
    )

    session = default_effect_session()
    request = advance_to_default_grant(session)
    checkpoint = session.to_persistence_payload()
    forked = session.fork()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    before = restored.lifecycle.to_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        restored.submit_option(
            request_id=request.request_id, result_id="order123-invalid", option_id="unoffered-name"
        )
    assert restored.lifecycle.to_payload() == before
    state = restored.lifecycle.state
    assert state is not None
    attached = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    token = "CORE CHARACTER LEADER"
    bodyguard_token = "CORE INTERCESSOR-LIKE INFANTRY"
    assert {token, bodyguard_token} <= set(attached.keywords)
    leader_ids = tuple(
        model.model_instance_id
        for model in attached.own_models
        if model.datasheet_id == "core-character-leader"
    )
    assert (
        scoped_roll_model_ids_for_effect(
            source_rules_unit=attached,
            current_roll_model_instance_ids=tuple(
                model.model_instance_id for model in attached.own_models
            ),
            effect_parameters={"required_model_keyword": token},
        )
        == leader_ids
    )
    context = RuleExecutionContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=state.battle_round,
        phase=state.current_battle_phase,
        active_player_id=state.active_player_id,
        target_unit_instance_ids=(attached.unit_instance_id,),
        state=state,
    )
    for keyword, reason in (
        (token, None),
        (bodyguard_token, None),
        (bodyguard_token.replace("-", " "), "unit_missing_required_keyword"),
        (bodyguard_token.replace("-", "_").replace(" ", "_"), "unit_missing_required_keyword"),
        ("UNRELATED DATASHEET", "unit_missing_required_keyword"),
    ):
        span = TextSpan(start=0, end=len(keyword), text=keyword)
        clause = RuleClause(
            clause_id="core-permission:order123:name-target",
            source_span=span,
            target=RuleTargetSpec(
                kind=RuleTargetKind.FRIENDLY_UNIT,
                source_span=span,
                parameters=(RuleParameter(key="required_keyword", value=keyword),),
            ),
            effects=(RuleEffectSpec(kind=RuleEffectKind.GRANT_ABILITY, source_span=span),),
        )
        assert effect_clause_target_unavailable_reason(clause=clause, context=context) == reason
    assert restored.lifecycle.to_payload() == before
    for viewer in ("player-a", "player-b"):
        view = restored.view(viewer_player_id=viewer)
        assert token in view["unit_display_by_id"]["army-alpha:leader"]["keywords"]
        assert bodyguard_token in view["unit_display_by_id"]["army-alpha:passengers"]["keywords"]
        for model_id in leader_ids:
            assert token in view["model_display_by_id"][model_id]["keywords"]
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("activate") is activate
    )
    restored.submit_option(
        request_id=request.request_id, result_id="order123-activation", option_id=option.option_id
    )
    assert forked.to_persistence_payload() == checkpoint
    assert_persistence_viewers_replay(restored)

    for index in range(120):
        status = restored.advance_until_decision_or_terminal()
        if state.battle_round == 2:
            break
        assert status.decision_request is not None
        submit_quiet_choice(restored, status.decision_request, result_id=f"order123-cycle-{index}")
    else:
        raise AssertionError("Complete native lifecycle cycle did not finish.")
    assert (
        token in rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader").keywords
    )
    assert_persistence_viewers_replay(restored)


def _native_name_unit(name: str, *, ordinary_name: bool = False) -> UnitInstance:
    from warhammer40k_core.engine.list_validation import UnitMusterSelection
    from warhammer40k_core.engine.unit_factory import UnitFactory
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = replace(catalog.datasheet_by_id("core-intercessor-like-infantry"), name=name)
    if ordinary_name:
        sheet = replace(
            sheet,
            keywords=replace(
                sheet.keywords,
                keywords=tuple(sorted({*sheet.keywords.keywords, sheet.name_keyword})),
            ),
        )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
    )
    return UnitFactory(catalog=catalog).instantiate_unit(
        army_id="order123-native",
        datasheet=sheet,
        selection=UnitMusterSelection(
            unit_selection_id=f"identity:{name}",
            datasheet_id=sheet.datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(
                    model_profile_id=row.model_profile_id, model_count=row.min_models
                )
                for row in sheet.composition
            ),
        ),
    )


@pytest.mark.parametrize(
    ("name", "near"),
    [
        ("Name-with-hyphens", "Name with hyphens"),
        ("Name with hyphens", "Name-with-hyphens"),
        ("Be'lakor", "Belakor"),
        ("Lords of Change", "Lord of Change"),
    ],
)
def test_contextful_generic_gates_preserve_both_native_sides(name: str, near: str) -> None:
    from warhammer40k_core.engine import catalog_battle_shock_runtime, generic_rule_ability_effects
    from warhammer40k_core.engine.abilities import AbilityExecutionContext, KeywordGate
    from warhammer40k_core.engine.generic_detachment_rule_effects import (
        _unit_matches_keyword_requirement,
        _UnitKeywordRequirement,
    )
    from warhammer40k_core.engine.rule_aura_resolution import _rules_unit_has_excluded_keyword
    from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
    from warhammer40k_core.engine.transports import TransportCapacityProfile

    unit = _native_name_unit(name)
    view = RulesUnitView(
        unit_instance_id=unit.unit_instance_id,
        owner_player_id="player-a",
        components=(RulesUnitComponent(unit=unit, role="unit"),),
    )
    assert unit.datasheet_name_keywords == (name.upper(),)
    context = AbilityExecutionContext.passive_keyword_gate(
        source_keywords=view.keywords, source_name_keywords=view.datasheet_name_keywords
    )
    restored = AbilityExecutionContext.from_payload(context.to_payload())
    assert restored == context
    for query, expected in ((name, True), (near, False), (near.replace(" ", "_"), False)):
        assert unit_has_keyword(unit, query) is expected
        assert (
            unit_has_required_keywords(
                unit_keywords=view.keywords,
                faction_keywords=view.faction_keywords,
                required_keywords=("INFANTRY", query),
                name_keywords=view.datasheet_name_keywords,
            )
            is expected
        )
        assert generic_rule_ability_effects._rules_unit_has_keyword(view, query) is expected
        assert (
            catalog_battle_shock_runtime._unit_has_required_keyword(unit, required_keyword=query)
            is expected
        )
        assert (
            catalog_battle_shock_runtime._rules_unit_has_required_keyword(
                view, required_keyword=query
            )
            is expected
        )
        assert (
            _rules_unit_has_excluded_keyword(rules_unit=view, excluded_keywords=(query,))
            is expected
        )
        gate = KeywordGate(required_keywords=(query,))
        assert (
            KeywordGate.from_payload(gate.to_payload()).matches(
                restored.source_keywords, name_keywords=restored.source_name_keywords
            )
            is expected
        )
        assert (
            KeywordGate(forbidden_keywords=(query,)).matches(
                restored.source_keywords, name_keywords=restored.source_name_keywords
            )
            is not expected
        )
        requirement = _UnitKeywordRequirement(
            required_keywords=(query,),
            required_faction_keywords=(),
            required_keyword_any=None,
            excluded_keywords=(),
        )
        assert _unit_matches_keyword_requirement(unit, requirement) is expected
        assert (
            _unit_matches_keyword_requirement(
                unit, replace(requirement, required_keywords=(), required_keyword_any=(query,))
            )
            is expected
        )
        assert (
            _unit_matches_keyword_requirement(
                unit, replace(requirement, required_keywords=(), excluded_keywords=(query,))
            )
            is not expected
        )
        assert (
            TransportCapacityProfile(
                transport_datasheet_id="test", max_model_count=20, allowed_keywords=(query,)
            ).allows_unit(unit)
            is expected
        )
        assert (
            TransportCapacityProfile(
                transport_datasheet_id="test", max_model_count=20, excluded_keywords=(query,)
            ).allows_unit(unit)
            is not expected
        )


@pytest.mark.parametrize("ordinary", [False, True])
def test_name_role_and_independent_grant_keep_conventional_keyword_compatibility(
    ordinary: bool,
) -> None:
    from warhammer40k_core.engine.model_keyword_grants import grant_unit_keywords
    from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords

    unit = _native_name_unit("DEDICATED TRANSPORT", ordinary_name=ordinary)
    assert unit_has_keyword(unit, "DEDICATED TRANSPORT")
    assert unit_has_keyword(unit, "DEDICATED-TRANSPORT") is ordinary
    assert unit_has_required_keywords(
        unit_keywords=("DEDICATED TRANSPORT",),
        faction_keywords=(),
        required_keywords=("DEDICATED-TRANSPORT",),
    )
    granted = grant_unit_keywords(
        unit, keywords=("DEDICATED TRANSPORT",), source_id="core-test:grant"
    )
    assert unit_has_keyword(granted, "DEDICATED-TRANSPORT")
    assert all(model.keyword_assignment.name_is_ordinary_keyword for model in granted.own_models)
    assert UnitInstance.from_payload(granted.to_payload()).datasheet_name_keywords == ()
    assert unit_has_required_keywords(
        unit_keywords=unit.keywords,
        faction_keywords=("DEDICATED TRANSPORT",),
        required_keywords=("DEDICATED-TRANSPORT",),
        name_keywords=unit.datasheet_name_keywords,
    )


def test_near_names_coexist_in_one_attached_inventory_without_aliasing_each_other() -> None:
    from warhammer40k_core.engine.abilities import AbilityExecutionContext, KeywordGate
    from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
    from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords

    first = _native_name_unit("Name-with-hyphens")
    second = _native_name_unit("Name with hyphens")
    formation = AttachedUnitFormation(
        attached_unit_instance_id="attached-unit:order123-near-names",
        bodyguard_unit_instance_id=first.unit_instance_id,
        leader_unit_instance_ids=(second.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((first.unit_instance_id, second.unit_instance_id))
        ),
        source_id="core-test:formation",
        attachment_source_ids=("core-test:attachment",),
    )
    view = RulesUnitView(
        unit_instance_id=formation.attached_unit_instance_id,
        owner_player_id="player-a",
        components=(
            RulesUnitComponent(unit=first, role="bodyguard"),
            RulesUnitComponent(unit=second, role="leader"),
        ),
        attached_unit=formation,
    )
    assert unit_has_required_keywords(
        unit_keywords=view.keywords,
        faction_keywords=view.faction_keywords,
        required_keywords=("NAME-WITH-HYPHENS", "NAME WITH HYPHENS"),
        name_keywords=view.datasheet_name_keywords,
    )
    context = AbilityExecutionContext.passive_keyword_gate(
        source_keywords=view.keywords, source_name_keywords=view.datasheet_name_keywords
    )
    assert AbilityExecutionContext.from_payload(context.to_payload()) == context
    for name in view.datasheet_name_keywords:
        assert KeywordGate(required_keywords=(name,)).matches(
            context.source_keywords, name_keywords=context.source_name_keywords
        )
    assert not unit_has_keyword(first, "NAME WITH HYPHENS")
    assert not unit_has_keyword(second, "NAME-WITH-HYPHENS")


def _native_weapon_profile() -> WeaponProfile:
    return ArmyCatalog.phase9a_canonical_content_pack().wargear[0].weapon_profiles[0]


def test_explicit_native_selector_declarations_disambiguate_eager_validation_only() -> None:
    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor
    from warhammer40k_core.engine.abilities import KeywordGate
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.weapon_abilities import anti_keyword_critical_threshold

    unit = _native_name_unit("Name-with-hyphens")
    names = ("NAME-WITH-HYPHENS", "NAME WITH HYPHENS")
    gate = KeywordGate(
        required_keywords=(names[0],),
        forbidden_keywords=(names[1],),
        native_keyword_selectors=names,
    )
    assert KeywordGate.from_payload(gate.to_payload()) == gate
    assert gate.matches(unit.keywords, name_keywords=unit.datasheet_name_keywords)
    assert not replace(gate, required_keywords=(names[1],), forbidden_keywords=(names[0],)).matches(
        unit.keywords, name_keywords=unit.datasheet_name_keywords
    )
    both = KeywordGate(required_keywords=names, native_keyword_selectors=names)
    assert not both.matches(unit.keywords, name_keywords=unit.datasheet_name_keywords)
    anti = AbilityDescriptor.anti_keyword("/".join(names), 2, native_keyword_selectors=names)
    assert AbilityDescriptor.from_payload(anti.to_payload()) == anti
    profile = replace(_native_weapon_profile(), keywords=(), abilities=(anti,))
    assert (
        anti_keyword_critical_threshold(
            profile=profile,
            target_keywords=unit.keywords,
            name_keywords=unit.datasheet_name_keywords,
        )
        == 2
    )
    with pytest.raises(GameLifecycleError, match="duplicate"):
        KeywordGate(required_keywords=("Deep Strike", "DEEP-STRIKE"))
    with pytest.raises(GameLifecycleError, match="cannot be both"):
        KeywordGate(required_keywords=("Deep Strike",), forbidden_keywords=("DEEP-STRIKE",))
    with pytest.raises(GameLifecycleError, match="selector inventory"):
        KeywordGate(required_keywords=(names[0],), native_keyword_selectors=("UNRELATED",))


@pytest.mark.parametrize("change", ["one-field", "null", "wrong-role-type"])
def test_model_name_payload_metadata_is_strictly_paired(change: str) -> None:
    from typing import cast

    from warhammer40k_core.core.model_keywords import (
        ModelKeywordAssignment,
        ModelKeywordAssignmentPayload,
        ModelKeywordError,
    )

    assignment = _native_name_unit("Native-name").own_models[0].keyword_assignment
    payload = dict(assignment.to_payload())
    if change == "one-field":
        del payload["name_is_ordinary_keyword"]
    elif change == "null":
        payload["name_keyword"] = None
    else:
        payload["name_is_ordinary_keyword"] = "false"
    with pytest.raises(ModelKeywordError, match=r"metadata fields|identity must|role must"):
        ModelKeywordAssignment.from_payload(cast(ModelKeywordAssignmentPayload, payload))


@pytest.mark.parametrize(
    ("name", "near"),
    [
        ("Name-with-hyphens", "Name with hyphens"),
        ("Name with hyphens", "Name-with-hyphens"),
    ],
)
def test_weapon_positive_negative_and_anti_selectors_keep_native_spelling(
    name: str, near: str
) -> None:
    from warhammer40k_core.core.weapon_profiles import (
        AbilityDescriptor,
        AntiKeywordMatchMode,
        TargetKeywordMatchMode,
        WeaponKeyword,
    )
    from warhammer40k_core.engine.weapon_abilities import (
        anti_keyword_critical_threshold,
        lethal_hits_applies,
    )

    unit = _native_name_unit(name)
    for selector, expected in ((name, True), (near, False)):
        descriptor = AbilityDescriptor.lethal_hits(target_keywords=(selector,))
        assert descriptor.target_keywords == (selector.upper(),)
        assert AbilityDescriptor.from_payload(descriptor.to_payload()) == descriptor
        profile = replace(
            _native_weapon_profile(), keywords=(WeaponKeyword.LETHAL_HITS,), abilities=(descriptor,)
        )
        assert (
            lethal_hits_applies(
                profile, target_keywords=unit.keywords, name_keywords=unit.datasheet_name_keywords
            )
            is expected
        )
        negative = AbilityDescriptor.lethal_hits(
            target_keywords=(selector,),
            target_keyword_match_mode=TargetKeywordMatchMode.MISSING_KEYWORD,
        )
        assert (
            lethal_hits_applies(
                replace(profile, abilities=(negative,)),
                target_keywords=unit.keywords,
                name_keywords=unit.datasheet_name_keywords,
            )
            is not expected
        )
        anti = AbilityDescriptor.anti_keyword(selector, 2)
        anti_profile = replace(_native_weapon_profile(), keywords=(), abilities=(anti,))
        assert anti_keyword_critical_threshold(
            profile=anti_profile,
            target_keywords=unit.keywords,
            name_keywords=unit.datasheet_name_keywords,
        ) == (2 if expected else None)
        anti_negative = AbilityDescriptor.anti_keyword(
            selector, 2, match_mode=AntiKeywordMatchMode.MISSING_KEYWORD
        )
        assert anti_keyword_critical_threshold(
            profile=replace(anti_profile, abilities=(anti_negative,)),
            target_keywords=unit.keywords,
            name_keywords=unit.datasheet_name_keywords,
        ) == (None if expected else 2)


@pytest.mark.parametrize("change", ["lost", "role"])
def test_current_runtime_restore_authenticates_name_classification(change: str) -> None:
    from tests.order122_helpers import advance_to_default_grant, default_effect_session

    from warhammer40k_core.adapters.local_session import LocalGameSession, _payload_sha256

    session = default_effect_session()
    advance_to_default_grant(session)
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    found = False

    def change_assignment(value: object) -> None:
        nonlocal found
        if isinstance(value, dict):
            if "keyword_assignment" in value and not found:
                assignment = value["keyword_assignment"]
                assert isinstance(assignment, dict)
                if change == "lost":
                    del assignment["name_keyword"]
                    del assignment["name_is_ordinary_keyword"]
                else:
                    assignment["name_is_ordinary_keyword"] = not assignment[
                        "name_is_ordinary_keyword"
                    ]
                found = True
            for child in value.values():
                change_assignment(child)
        elif isinstance(value, list):
            for child in value:
                change_assignment(child)

    change_assignment(payload)
    assert found
    payload["content_hash"] = _payload_sha256(
        {key: value for key, value in payload.items() if key != "content_hash"}
    )
    with pytest.raises(ValueError, match="could not be reconstructed") as error:
        LocalGameSession.from_persistence_payload(payload)
    assert str(error.value.__cause__) == "Lifecycle state army definitions do not match config."


@pytest.mark.parametrize("field", ["required_keywords", "forbidden_keywords", "target_keywords"])
def test_native_selector_metadata_preserves_eager_domain_container_errors(field: str) -> None:
    from typing import Any, cast

    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponProfileError
    from warhammer40k_core.engine.abilities import KeywordGate
    from warhammer40k_core.engine.phase import GameLifecycleError

    invalid = cast(Any, None)
    if field == "target_keywords":
        with pytest.raises(WeaponProfileError, match="target_keywords must be a tuple"):
            AbilityDescriptor.lethal_hits(target_keywords=invalid)
    elif field == "required_keywords":
        with pytest.raises(GameLifecycleError, match="required_keywords must be a tuple"):
            KeywordGate(required_keywords=invalid)
    else:
        with pytest.raises(GameLifecycleError, match="forbidden_keywords must be a tuple"):
            KeywordGate(forbidden_keywords=invalid)


@pytest.mark.parametrize("name", ["Non-standard Squad", "Alpha/Beta Squad", "Captain's Guard"])
def test_declared_native_weapon_selectors_preserve_names_at_grammar_boundaries(name: str) -> None:
    from warhammer40k_core.core.weapon_profiles import (
        AbilityDescriptor,
        TargetKeywordMatchMode,
        WeaponKeyword,
    )
    from warhammer40k_core.engine.weapon_abilities import (
        anti_keyword_critical_threshold,
        hunter_target_allowed,
    )

    unit = _native_name_unit(name)
    native = (name.upper(),)
    descriptor = AbilityDescriptor.hunter(
        target_keywords=native,
        target_keyword_match_mode=TargetKeywordMatchMode.HAS_KEYWORD,
        native_keyword_selectors=native,
    )
    assert descriptor.target_keywords == native
    assert AbilityDescriptor.from_payload(descriptor.to_payload()) == descriptor
    profile = replace(
        _native_weapon_profile(), keywords=(WeaponKeyword.HUNTER,), abilities=(descriptor,)
    )
    assert hunter_target_allowed(
        profile, target_keywords=unit.keywords, name_keywords=unit.datasheet_name_keywords
    )
    assert not hunter_target_allowed(profile, target_keywords=("INFANTRY",))
    anti = AbilityDescriptor.anti_keyword(name, 2, native_keyword_selectors=native)
    anti_profile = replace(
        profile, keywords=(), abilities=(AbilityDescriptor.from_payload(anti.to_payload()),)
    )
    assert (
        anti_keyword_critical_threshold(
            profile=anti_profile,
            target_keywords=unit.keywords,
            name_keywords=unit.datasheet_name_keywords,
        )
        == 2
    )
    assert (
        anti_keyword_critical_threshold(profile=anti_profile, target_keywords=("INFANTRY",)) is None
    )
