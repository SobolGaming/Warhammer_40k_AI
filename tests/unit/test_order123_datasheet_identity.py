"""Selected Core datasheet identity survives the shared keyword ownership path."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.model_keyword_helpers import mixed_keyword_catalog, mixed_keyword_unit

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_keywords import model_keyword_assignment
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
        replace(row, keywords=tuple(k for k in row.keywords if k != sheet.name_keyword))
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

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    token = sheet.name_keyword
    assert token not in sheet.keywords.keywords
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
