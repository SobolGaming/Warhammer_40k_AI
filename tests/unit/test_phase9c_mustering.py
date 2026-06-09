from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition, DatasheetDefinition
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
    ArmyMusterRequest,
    ArmyMusterRequestPayload,
    AttachedUnitFormation,
    muster_army,
)
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    BattleSize,
    BattleSizeMusteringPolicy,
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
    battle_size_from_token,
    resolve_model_profile_selections,
    resolve_wargear_selections,
    selected_force_disposition_ids,
    validate_detachment_selection,
    validate_unit_selection_for_faction,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitComponent,
    RulesUnitComponentRole,
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)


def _unit_selection(
    *,
    unit_selection_id: str = "intercessor-unit-1",
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
        wargear_selections=wargear_selections,
    )


def _muster_request(
    catalog: ArmyCatalog,
    *,
    army_id: str = "army-alpha",
    player_id: str = "player-a",
    detachment_selection: DetachmentSelection | None = None,
    unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    catalog_id: str | None = None,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id if catalog_id is None else catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=detachment_selection
        if detachment_selection is not None
        else DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=unit_selections if unit_selections is not None else (_unit_selection(),),
        attachment_declarations=attachment_declarations,
    )


def _phase16_source_detachment(
    *,
    row: faction_detachment_source.SourceDetachmentRow,
    unit_datasheet_ids: tuple[str, ...],
) -> DetachmentDefinition:
    return DetachmentDefinition(
        detachment_id=row.detachment_id,
        name=row.name,
        faction_id=row.faction_id,
        detachment_point_cost=row.detachment_point_cost,
        unit_datasheet_ids=unit_datasheet_ids,
        force_disposition_ids=(row.force_disposition_id,),
        source_ids=row.source_ids,
    )


def _phase16_source_detachment_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    unit_datasheet_ids = tuple(datasheet.datasheet_id for datasheet in base_catalog.datasheets)
    source_factions = tuple(
        FactionDefinition(
            faction_id=row.faction_id,
            name=row.name,
            faction_keywords=row.faction_keywords,
            source_ids=row.source_ids,
        )
        for row in faction_detachment_source.faction_rows()
    )
    factions = (base_catalog.faction_by_id("core-marine-force"), *source_factions)
    detachments = tuple(
        _phase16_source_detachment(
            row=row,
            unit_datasheet_ids=unit_datasheet_ids,
        )
        for row in faction_detachment_source.detachment_rows()
    )

    return ArmyCatalog(
        catalog_id="phase16-faction-detachments-2026-27",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id=faction_detachment_source.SOURCE_PACKAGE_ID,
        datasheets=base_catalog.datasheets,
        wargear=base_catalog.wargear,
        factions=factions,
        army_rules=base_catalog.army_rules,
        detachments=detachments,
        source_ids=(faction_detachment_source.SOURCE_PACKAGE_ID,),
    )


def _detachment_by_id(catalog: ArmyCatalog, detachment_id: str) -> DetachmentDefinition:
    matches = tuple(
        detachment
        for detachment in catalog.detachments
        if detachment.detachment_id == detachment_id
    )
    assert len(matches) == 1
    return matches[0]


def test_army_mustering_consumes_catalog_and_produces_runtime_instances() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)

    army = muster_army(catalog=catalog, request=request)
    payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)
    unit = army.unit_by_id("army-alpha:intercessor-unit-1")
    model = unit.own_models[0]

    assert army.stable_identity() == "army:army-alpha"
    assert army.catalog_id == catalog.catalog_id
    assert army.ruleset_id == catalog.ruleset_id
    assert unit.datasheet_id == "core-intercessor-like-infantry"
    assert unit.datasheet_source_ids == ("datasheet:core-intercessor-like-infantry",)
    assert len(unit.own_models) == 5
    assert unit.wargear_selections[0].wargear_ids == ("core-bolt-rifle",)
    assert model.datasheet_id == unit.datasheet_id
    assert model.model_profile_id == "core-intercessor-like"
    assert model.base_size.diameter_mm == 32.0
    assert model.starting_wounds == 2
    assert model.source_ids == (
        "datasheet:core-intercessor-like-infantry",
        "datasheet:core-intercessor-like-infantry:profile",
    )
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert ArmyDefinition.from_payload(payload).to_payload() == army.to_payload()


def test_muster_request_and_runtime_payloads_round_trip_without_object_reprs() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)
    request_payload = cast(
        ArmyMusterRequestPayload,
        json.loads(json.dumps(request.to_payload(), sort_keys=True)),
    )
    request_blob = json.dumps(request_payload, sort_keys=True)
    army = muster_army(catalog=catalog, request=ArmyMusterRequest.from_payload(request_payload))
    unit_payload = json.dumps(army.units[0].to_payload(), sort_keys=True)

    assert "<" not in request_blob
    assert "object at 0x" not in request_blob
    assert "<" not in unit_payload
    assert "object at 0x" not in unit_payload
    assert ArmyMusterRequest.from_payload(request_payload).to_payload() == request.to_payload()


def test_runtime_units_use_explicit_own_model_semantics() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    unit = army.units[0]

    assert isinstance(unit, UnitInstance)
    assert len(unit.own_models) == 5
    assert unit.own_model_ids() == tuple(model.model_instance_id for model in unit.own_models)
    assert not hasattr(unit, "models")


def test_attachment_declarations_form_runtime_attached_unit_from_structured_catalog() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )

    army = muster_army(catalog=catalog, request=request)
    payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    formation = army.attached_units[0]
    bodyguard = army.unit_by_id("army-alpha:bodyguard-unit")
    leader = army.unit_by_id("army-alpha:leader-unit")
    support = army.unit_by_id("army-alpha:support-unit")

    assert formation.attached_unit_instance_id == "attached-unit:army-alpha:bodyguard-unit"
    assert formation.bodyguard_unit_instance_id == bodyguard.unit_instance_id
    assert formation.leader_unit_instance_ids == (leader.unit_instance_id,)
    assert formation.support_unit_instance_ids == (support.unit_instance_id,)
    assert formation.component_unit_instance_ids == (
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
        support.unit_instance_id,
    )
    assert "ATTACHED_UNIT" in bodyguard.keywords
    assert "runtime-attached-unit:bodyguard" in bodyguard.own_models[0].source_ids
    assert "attached-role:leader" in leader.own_models[0].source_ids
    assert "runtime-attached-unit:leader" in leader.own_models[0].source_ids
    assert "attached-role:support" in support.own_models[0].source_ids
    assert "runtime-attached-unit:support" in support.own_models[0].source_ids
    assert "<" not in json.dumps(payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)
    assert ArmyDefinition.from_payload(payload).to_payload() == army.to_payload()


def test_rules_unit_view_resolves_physical_and_mustered_attached_units() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
            _unit_selection(unit_selection_id="loose-unit"),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    army = muster_army(catalog=catalog, request=request)
    formation = army.attached_units[0]
    bodyguard = army.unit_by_id("army-alpha:bodyguard-unit")
    leader = army.unit_by_id("army-alpha:leader-unit")
    support = army.unit_by_id("army-alpha:support-unit")
    loose_unit = army.unit_by_id("army-alpha:loose-unit")

    attached_view = rules_unit_view_from_armies(
        armies=(army,),
        unit_instance_id=bodyguard.unit_instance_id,
    )
    physical_view = rules_unit_view_from_armies(
        armies=(army,),
        unit_instance_id=loose_unit.unit_instance_id,
    )

    assert attached_view.unit_instance_id == formation.attached_unit_instance_id
    assert (
        rules_unit_id_for_unit_id(
            armies=(army,),
            unit_instance_id=support.unit_instance_id,
        )
        == formation.attached_unit_instance_id
    )
    assert attached_view.owner_player_id == "player-a"
    assert attached_view.component_unit_instance_ids == (
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
        support.unit_instance_id,
    )
    assert (
        attached_view.component_unit_id_for_model(leader.own_models[0].model_instance_id)
        == leader.unit_instance_id
    )
    assert (
        attached_view.component_role_for_model(support.own_models[0].model_instance_id) == "support"
    )
    assert attached_view.bodyguard_model_ids(attached_view.alive_models()) == tuple(
        model.model_instance_id for model in bodyguard.own_models
    )
    assert attached_view.character_model_ids(attached_view.alive_models()) == (
        leader.own_models[0].model_instance_id,
        support.own_models[0].model_instance_id,
    )
    assert "ATTACHED_UNIT" in attached_view.keywords
    assert "CORE Marines" in attached_view.faction_keywords
    assert physical_view.unit_instance_id == loose_unit.unit_instance_id
    assert physical_view.attached_unit is None
    assert physical_view.bodyguard_model_ids(physical_view.alive_models()) == ()
    assert physical_view.character_model_ids(physical_view.alive_models()) == ()


def test_rules_unit_projection_value_objects_fail_fast() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    unit = army.units[0]
    component = RulesUnitComponent(unit=unit, role="unit")

    with pytest.raises(GameLifecycleError, match="UnitInstance"):
        RulesUnitComponent(unit=cast(UnitInstance, "bad-unit"), role="unit")
    with pytest.raises(GameLifecycleError, match="unsupported role"):
        RulesUnitComponent(unit=unit, role=cast(RulesUnitComponentRole, "bad-role"))
    with pytest.raises(GameLifecycleError, match="components must be a tuple"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=cast(tuple[RulesUnitComponent, ...], [component]),
        )
    with pytest.raises(GameLifecycleError, match="requires at least one component"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(),
        )
    with pytest.raises(GameLifecycleError, match="RulesUnitComponent values"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=cast(tuple[RulesUnitComponent, ...], ("bad-component",)),
        )
    with pytest.raises(GameLifecycleError, match="AttachedUnitFormation"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component,),
            attached_unit=cast(AttachedUnitFormation, "bad-attached-unit"),
        )
    with pytest.raises(GameLifecycleError, match="exactly one component"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component, component),
        )
    with pytest.raises(GameLifecycleError, match="unknown"):
        rules_unit_view_from_armies(armies=(army,), unit_instance_id="missing-unit")
    with pytest.raises(GameLifecycleError, match="not in the rules unit"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component,),
        ).component_unit_id_for_model("missing-model")
    with pytest.raises(GameLifecycleError, match="not in the rules unit"):
        RulesUnitView(
            unit_instance_id=unit.unit_instance_id,
            owner_player_id=army.player_id,
            components=(component,),
        ).component_role_for_model("missing-model")


def test_attachment_declarations_reject_missing_eligibility_and_illegal_bodyguards() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    missing_eligibility_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="source-infantry"),
            _unit_selection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-boyz-like-infantry",
                model_profile_id="core-boyz-like",
                model_count=10,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="source-infantry",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )
    illegal_bodyguard_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-boyz-like-infantry",
                model_profile_id="core-boyz-like",
                model_count=10,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="no attachment eligibility"):
        muster_army(catalog=catalog, request=missing_eligibility_request)
    with pytest.raises(ArmyMusteringError, match="bodyguard datasheet"):
        muster_army(catalog=catalog, request=illegal_bodyguard_request)


def test_attachment_declarations_reject_duplicate_sources_and_duplicate_roles() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    with pytest.raises(ArmyMusteringError, match="unique source unit IDs"):
        _muster_request(
            catalog,
            unit_selections=(
                _unit_selection(unit_selection_id="bodyguard-unit"),
                _unit_selection(unit_selection_id="second-bodyguard-unit"),
                _unit_selection(
                    unit_selection_id="leader-unit",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
            ),
            attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader-unit",
                    bodyguard_unit_selection_id="bodyguard-unit",
                ),
                AttachmentDeclaration(
                    source_unit_selection_id="leader-unit",
                    bodyguard_unit_selection_id="second-bodyguard-unit",
                ),
            ),
        )

    duplicate_role_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="second-leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="second-leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="one Leader or one Support"):
        muster_army(catalog=catalog, request=duplicate_role_request)


def test_runtime_payloads_reject_hierarchy_and_source_drift() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    army_payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army.to_payload(), sort_keys=True)),
    )
    unit_payload = army_payload["units"][0]

    foreign_army_payload = cast(
        ArmyDefinitionPayload,
        json.loads(json.dumps(army_payload, sort_keys=True)),
    )
    old_unit_id = foreign_army_payload["units"][0]["unit_instance_id"]
    new_unit_id = "other-army:intercessor-unit-1"
    foreign_army_payload["units"][0]["unit_instance_id"] = new_unit_id
    for model_payload in foreign_army_payload["units"][0]["own_models"]:
        model_payload["model_instance_id"] = model_payload["model_instance_id"].replace(
            old_unit_id,
            new_unit_id,
        )
    with pytest.raises(ArmyMusteringError, match="scoped to army_id"):
        ArmyDefinition.from_payload(foreign_army_payload)

    datasheet_mismatch = json.loads(json.dumps(unit_payload, sort_keys=True))
    datasheet_mismatch["own_models"][0]["datasheet_id"] = "other-datasheet"
    with pytest.raises(UnitFactoryError, match="datasheet_id"):
        UnitInstance.from_payload(datasheet_mismatch)

    model_scope_mismatch = json.loads(json.dumps(unit_payload, sort_keys=True))
    model_scope_mismatch["own_models"][0]["model_instance_id"] = "other-unit:model-001"
    with pytest.raises(UnitFactoryError, match="scoped to unit_instance_id"):
        UnitInstance.from_payload(model_scope_mismatch)

    empty_unit_sources = json.loads(json.dumps(unit_payload, sort_keys=True))
    empty_unit_sources["datasheet_source_ids"] = []
    with pytest.raises(UnitFactoryError, match="datasheet_source_ids"):
        UnitInstance.from_payload(empty_unit_sources)

    empty_model_sources = json.loads(json.dumps(unit_payload, sort_keys=True))
    empty_model_sources["own_models"][0]["source_ids"] = []
    with pytest.raises(UnitFactoryError, match="source_ids"):
        UnitInstance.from_payload(empty_model_sources)


def test_selected_wargear_must_be_legal_for_datasheet_option() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    illegal_wargear = WargearSelection(
        option_id="core-intercessor-like-infantry:default-wargear",
        model_profile_id="core-intercessor-like",
        wargear_ids=("core-heavy-cannon",),
    )
    request = _muster_request(
        catalog,
        unit_selections=(_unit_selection(wargear_selections=(illegal_wargear,)),),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=catalog, request=request)


def test_model_profile_counts_must_match_datasheet_composition() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(
        catalog,
        unit_selections=(_unit_selection(model_count=4),),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=catalog, request=request)


def test_detachment_enhancement_and_stratagem_selections_are_validated_as_data() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    enhancement = EnhancementDefinition(
        enhancement_id="core-enhancement",
        name="Core Enhancement",
        source_id="enhancement:core-enhancement",
    )
    stratagem = StratagemDefinition(
        stratagem_id="core-stratagem",
        name="Core Stratagem",
        source_id="stratagem:core-stratagem",
        command_point_cost=1,
    )
    detachment = replace(
        catalog.detachments[0],
        enhancement_ids=(enhancement.enhancement_id,),
        stratagem_ids=(stratagem.stratagem_id,),
    )
    catalog_with_content = ArmyCatalog(
        catalog_id="phase9c-with-detachment-content",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(detachment,),
        enhancements=(enhancement,),
        stratagems=(stratagem,),
        source_ids=catalog.source_ids,
    )
    valid_request = _muster_request(
        catalog_with_content,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=(enhancement.enhancement_id,),
            stratagem_ids=(stratagem.stratagem_id,),
        ),
    )
    invalid_request = _muster_request(
        catalog_with_content,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
            enhancement_ids=("not-allowed",),
        ),
    )

    army = muster_army(catalog=catalog_with_content, request=valid_request)
    assert army.detachment_selection == valid_request.detachment_selection
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=catalog_with_content, request=invalid_request)


def test_strike_force_is_the_only_supported_battle_size_policy() -> None:
    policy = BattleSizeMusteringPolicy.strike_force()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)

    assert policy.points_limit == 2000
    assert policy.battlefield_width_inches == 60.0
    assert policy.battlefield_depth_inches == 44.0
    assert policy.detachment_point_limit == 3
    assert policy.enhancement_limit == 4
    assert policy.unit_limit == 3
    assert policy.battleline_unit_limit == 6
    assert muster_army(catalog=catalog, request=request).battle_size.value == "strike_force"

    with pytest.raises(ListValidationError, match="Unsupported BattleSize"):
        battle_size_from_token("incursion")
    with pytest.raises(ArmyMusteringError, match="battle_size"):
        replace(request, battle_size=cast(BattleSize, "incursion"))


def test_strike_force_detachment_points_force_dispositions_and_unit_grants() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_detachment = catalog.detachments[0]
    vanguard_detachment = replace(
        base_detachment,
        detachment_id="core-vanguard",
        name="CORE Vanguard",
        detachment_point_cost=2,
        unit_datasheet_ids=("core-intercessor-like-infantry",),
        force_disposition_ids=("reconnaissance",),
        source_ids=("detachment:core-vanguard",),
    )
    support_detachment = replace(
        base_detachment,
        detachment_id="core-support",
        name="CORE Support",
        detachment_point_cost=1,
        unit_datasheet_ids=("core-character-leader", "core-intercessor-like-infantry"),
        force_disposition_ids=("take-and-hold",),
        source_ids=("detachment:core-support",),
    )
    multi_detachment_catalog = ArmyCatalog(
        catalog_id="phase16d-multi-detachment",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(base_detachment, support_detachment, vanguard_detachment),
        source_ids=catalog.source_ids,
    )
    legal_selection = DetachmentSelection(
        faction_id="core-marine-force",
        detachment_ids=("core-support", "core-vanguard"),
    )
    over_limit_selection = DetachmentSelection(
        faction_id="core-marine-force",
        detachment_ids=("core-combined-arms", "core-support", "core-vanguard"),
    )
    unsupported_unit_request = _muster_request(
        multi_detachment_catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-vanguard",),
        ),
        unit_selections=(
            _unit_selection(
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )

    faction, detachments = validate_detachment_selection(
        catalog=multi_detachment_catalog,
        selection=legal_selection,
    )
    army = muster_army(
        catalog=multi_detachment_catalog,
        request=_muster_request(multi_detachment_catalog, detachment_selection=legal_selection),
    )

    assert faction.faction_id == "core-marine-force"
    assert tuple(detachment.detachment_id for detachment in detachments) == (
        "core-support",
        "core-vanguard",
    )
    assert army.detachment_selection.detachment_ids == ("core-support", "core-vanguard")
    assert selected_force_disposition_ids(
        catalog=multi_detachment_catalog,
        selection=legal_selection,
    ) == ("reconnaissance", "take-and-hold")
    with pytest.raises(ListValidationError, match="Detachment Points"):
        validate_detachment_selection(
            catalog=multi_detachment_catalog,
            selection=over_limit_selection,
        )
    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=multi_detachment_catalog, request=unsupported_unit_request)


def test_phase16_faction_detachment_source_rows_are_normalized() -> None:
    faction_rows = faction_detachment_source.faction_rows()
    detachment_rows = faction_detachment_source.detachment_rows()
    payload = faction_detachment_source.source_payload()
    detachment_names = {row.detachment_id: row.name for row in detachment_rows}
    new_detachment_ids = {row.detachment_id for row in detachment_rows if row.is_new_for_eleventh}

    assert len(faction_rows) == 15
    assert len(detachment_rows) == 145
    assert payload["source_package_id"] == faction_detachment_source.SOURCE_PACKAGE_ID
    assert {row.faction_id for row in faction_rows} >= {
        "leagues-of-votann",
        "space-marines",
        "tau-empire",
    }
    assert next(row for row in faction_rows if row.faction_id == "tau-empire").name == (
        "T'au Empire"
    )
    assert detachment_names["delve-assault-shift"] == "Delve Assault Shift"
    assert detachment_names["needgaard-oathband"] == "Needgaard Oathband"
    assert "advanced-acquisition-cadre" in new_detachment_ids
    assert all("New - " not in row.name for row in detachment_rows)
    assert all(ord(character) < 128 for row in faction_rows for character in row.name)
    assert all(ord(character) < 128 for row in detachment_rows for character in row.name)


def test_phase16_faction_detachment_source_rows_fail_fast_on_bad_data() -> None:
    with pytest.raises(faction_detachment_source.FactionDetachmentSourceError, match="slug"):
        faction_detachment_source.SourceFactionRow(
            faction_id="Bad Faction",
            raw_name="Bad Faction",
        )
    with pytest.raises(faction_detachment_source.FactionDetachmentSourceError, match="raw_name"):
        faction_detachment_source.SourceFactionRow(
            faction_id="bad-faction",
            raw_name=cast(str, 1),
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="detachment_id",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="wrong-id",
            raw_name="Gladius Task Force",
            force_disposition_id="priority-assets",
            detachment_point_cost=3,
            is_new_for_eleventh=False,
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="force_disposition_id",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            raw_name="Gladius Task Force",
            force_disposition_id="unknown-disposition",
            detachment_point_cost=3,
            is_new_for_eleventh=False,
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="detachment_point_cost",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            raw_name="Gladius Task Force",
            force_disposition_id="priority-assets",
            detachment_point_cost=4,
            is_new_for_eleventh=False,
        )
    with pytest.raises(
        faction_detachment_source.FactionDetachmentSourceError,
        match="is_new_for_eleventh",
    ):
        faction_detachment_source.SourceDetachmentRow(
            faction_id="space-marines",
            detachment_id="gladius-task-force",
            raw_name="Gladius Task Force",
            force_disposition_id="priority-assets",
            detachment_point_cost=3,
            is_new_for_eleventh=cast(bool, "yes"),
        )


def test_phase16_faction_detachment_matrix_supports_strike_force_combinations() -> None:
    catalog = _phase16_source_detachment_catalog()
    gladius_task_force = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("gladius-task-force",),
    )
    firestorm_plus_fulguris = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("firestorm-assault-force", "fulguris-task-force"),
    )
    black_templar_force = DetachmentSelection(
        faction_id="black-templars",
        detachment_ids=(
            "companions-of-vehemence",
            "marshals-household",
        ),
    )

    _space_marines, space_marine_detachments = validate_detachment_selection(
        catalog=catalog,
        selection=gladius_task_force,
    )
    assert tuple(detachment.detachment_id for detachment in space_marine_detachments) == (
        "gladius-task-force",
    )
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=gladius_task_force,
    ) == ("priority-assets",)
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=firestorm_plus_fulguris,
    ) == ("disruption", "purge-the-foe")
    assert selected_force_disposition_ids(
        catalog=catalog,
        selection=black_templar_force,
    ) == ("priority-assets", "purge-the-foe")


def test_phase16_faction_detachment_matrix_applies_source_corrections() -> None:
    catalog = _phase16_source_detachment_catalog()

    assert _detachment_by_id(catalog, "librarius-conclave").force_disposition_ids == (
        "reconnaissance",
    )
    assert _detachment_by_id(catalog, "subversion-assets").force_disposition_ids == (
        "reconnaissance",
    )
    assert _detachment_by_id(catalog, "anvil-siege-force").force_disposition_ids == (
        "take-and-hold",
    )
    assert _detachment_by_id(catalog, "armoured-speartip").force_disposition_ids == (
        "take-and-hold",
    )
    assert _detachment_by_id(catalog, "vanguard-spearhead").force_disposition_ids == (
        "reconnaissance",
    )
    assert _detachment_by_id(catalog, "black-spear-task-force").force_disposition_ids == (
        "priority-assets",
    )
    assert _detachment_by_id(catalog, "warpbane-task-force").force_disposition_ids == (
        "purge-the-foe",
    )
    assert _detachment_by_id(catalog, "saga-of-the-bold").force_disposition_ids == (
        "priority-assets",
    )


def test_phase16_faction_detachment_matrix_fails_closed_on_invalid_rows() -> None:
    catalog = _phase16_source_detachment_catalog()
    over_strike_force_limit = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("gladius-task-force", "bastion-task-force"),
    )
    cross_faction_selection = DetachmentSelection(
        faction_id="space-marines",
        detachment_ids=("marshals-household",),
    )

    with pytest.raises(ListValidationError, match="Detachment Points"):
        validate_detachment_selection(catalog=catalog, selection=over_strike_force_limit)
    with pytest.raises(ListValidationError, match="does not belong to faction"):
        validate_detachment_selection(catalog=catalog, selection=cross_faction_selection)


def test_detachment_selection_fails_closed_on_awaiting_source_grants() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    missing_cost_catalog = ArmyCatalog(
        catalog_id="missing-detachment-cost",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(replace(catalog.detachments[0], detachment_point_cost=None),),
    )
    missing_force_disposition_catalog = ArmyCatalog(
        catalog_id="missing-force-disposition",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(replace(catalog.detachments[0], force_disposition_ids=()),),
    )

    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=missing_cost_catalog, request=_muster_request(missing_cost_catalog))
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(
            catalog=missing_force_disposition_catalog,
            request=_muster_request(missing_force_disposition_catalog),
        )


def test_mustering_rejects_request_catalog_identity_drift() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog, catalog_id="other-catalog")

    with pytest.raises(ArmyMusteringError, match="catalog_id"):
        muster_army(catalog=catalog, request=request)


def test_mustering_rejects_unknown_datasheets_and_missing_detachments() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    unknown_datasheet_request = _muster_request(
        catalog,
        unit_selections=(
            _unit_selection(
                datasheet_id="missing-datasheet",
                model_profile_id="core-intercessor-like",
            ),
        ),
    )
    missing_detachment_request = _muster_request(
        catalog,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("missing-detachment",),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection"):
        muster_army(catalog=catalog, request=unknown_datasheet_request)
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=catalog, request=missing_detachment_request)


def test_mustering_value_objects_fail_fast_on_invalid_shapes() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    request = _muster_request(catalog)
    army = muster_army(catalog=catalog, request=request)

    with pytest.raises(ArmyMusteringError, match="ruleset_id"):
        replace(request, ruleset_id=cast(RulesetId, "bad-ruleset"))
    with pytest.raises(ArmyMusteringError, match="detachment_selection"):
        replace(request, detachment_selection=cast(DetachmentSelection, "bad-detachment"))
    with pytest.raises(ArmyMusteringError, match="unit_selections"):
        replace(request, unit_selections=())
    with pytest.raises(ArmyMusteringError, match="unique"):
        replace(request, unit_selections=(request.unit_selections[0], request.unit_selections[0]))
    with pytest.raises(ArmyMusteringError, match="unit_instance_id"):
        army.unit_by_id("missing-unit")
    with pytest.raises(ArmyMusteringError, match="ruleset_id"):
        replace(army, ruleset_id=cast(RulesetId, "bad-ruleset"))
    with pytest.raises(ArmyMusteringError, match="detachment_selection"):
        replace(army, detachment_selection=cast(DetachmentSelection, "bad-detachment"))
    with pytest.raises(ArmyMusteringError, match="units"):
        replace(army, units=())
    with pytest.raises(ArmyMusteringError, match="catalog"):
        muster_army(catalog=cast(ArmyCatalog, "bad-catalog"), request=request)
    with pytest.raises(ArmyMusteringError, match="request"):
        muster_army(catalog=catalog, request=cast(ArmyMusterRequest, "bad-request"))
    with pytest.raises(ArmyMusteringError, match="source_package_id"):
        muster_army(catalog=catalog, request=replace(request, source_package_id="other-package"))
    with pytest.raises(ArmyMusteringError, match="ruleset_id"):
        muster_army(
            catalog=catalog,
            request=replace(
                request,
                ruleset_id=RulesetId.warhammer_40000_eleventh(version="other-ruleset"),
            ),
        )


def test_list_validation_fails_fast_on_invalid_selection_shapes() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    detachment_selection = DetachmentSelection(
        faction_id="core-marine-force",
        detachment_ids=("core-combined-arms",),
    )
    unit_selection = _unit_selection()
    faction = catalog.faction_by_id("core-marine-force")
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")

    with pytest.raises(ListValidationError, match="catalog"):
        validate_detachment_selection(
            catalog=cast(ArmyCatalog, "bad-catalog"),
            selection=detachment_selection,
        )
    with pytest.raises(ListValidationError, match="selection"):
        validate_detachment_selection(
            catalog=catalog,
            selection=cast(DetachmentSelection, "bad-selection"),
        )
    with pytest.raises(ListValidationError, match="not found"):
        validate_detachment_selection(
            catalog=catalog,
            selection=DetachmentSelection(
                faction_id="missing-faction",
                detachment_ids=("core-combined-arms",),
            ),
        )
    with pytest.raises(ListValidationError, match="catalog"):
        validate_unit_selection_for_faction(
            catalog=cast(ArmyCatalog, "bad-catalog"),
            selection=unit_selection,
            faction=faction,
        )
    with pytest.raises(ListValidationError, match="selection"):
        validate_unit_selection_for_faction(
            catalog=catalog,
            selection=cast(UnitMusterSelection, "bad-selection"),
            faction=faction,
        )
    with pytest.raises(ListValidationError, match="faction"):
        validate_unit_selection_for_faction(
            catalog=catalog,
            selection=unit_selection,
            faction=cast(FactionDefinition, "bad-faction"),
        )
    with pytest.raises(ListValidationError, match="not legal for faction"):
        validate_unit_selection_for_faction(
            catalog=catalog,
            selection=unit_selection,
            faction=FactionDefinition(
                faction_id="other-faction",
                name="Other Faction",
                faction_keywords=("Other Keyword",),
            ),
        )
    with pytest.raises(ListValidationError, match="datasheet"):
        resolve_model_profile_selections(
            datasheet=cast(DatasheetDefinition, "bad-datasheet"),
            selections=unit_selection.model_profile_selections,
        )
    with pytest.raises(ListValidationError, match="composition"):
        resolve_model_profile_selections(
            datasheet=datasheet,
            selections=(ModelProfileSelection(model_profile_id="missing-profile", model_count=1),),
        )
    with pytest.raises(ListValidationError, match="exceeds"):
        resolve_model_profile_selections(
            datasheet=datasheet,
            selections=(
                ModelProfileSelection(model_profile_id="core-intercessor-like", model_count=11),
            ),
        )
    with pytest.raises(ListValidationError, match="unknown datasheet option"):
        resolve_wargear_selections(
            catalog=catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="unknown-option",
                    model_profile_id="core-intercessor-like",
                    wargear_ids=("core-bolt-rifle",),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="minimum"):
        resolve_wargear_selections(
            catalog=catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="core-intercessor-like-infantry:default-wargear",
                    model_profile_id="core-intercessor-like",
                    wargear_ids=(),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="must not include"):
        DetachmentSelection(faction_id="faction:bad", detachment_ids=("core-combined-arms",))
    with pytest.raises(ListValidationError, match="at least 1"):
        ModelProfileSelection(model_profile_id="core-intercessor-like", model_count=0)


def test_unit_factory_instances_and_validators_fail_fast() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = muster_army(catalog=catalog, request=_muster_request(catalog))
    unit = army.units[0]
    model = unit.own_models[0]
    factory = UnitFactory(catalog)
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")

    assert model.stable_identity().startswith("model:army-alpha:intercessor-unit-1")
    assert model.is_alive is True
    assert unit.stable_identity() == "unit:army-alpha:intercessor-unit-1"
    assert unit.alive_own_models() == unit.own_models

    with pytest.raises(UnitFactoryError, match="catalog"):
        UnitFactory(catalog=cast(ArmyCatalog, "bad-catalog"))
    with pytest.raises(UnitFactoryError, match="selection"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=cast(UnitMusterSelection, "bad-selection"),
            datasheet=datasheet,
        )
    with pytest.raises(UnitFactoryError, match="datasheet"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=_unit_selection(),
            datasheet=cast(DatasheetDefinition, "bad-datasheet"),
        )
    with pytest.raises(UnitFactoryError, match="does not match datasheet"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=replace(_unit_selection(), datasheet_id="core-transport"),
            datasheet=datasheet,
        )
    with pytest.raises(UnitFactoryError, match="factory catalog definition"):
        factory.instantiate_unit(
            army_id="army-alpha",
            selection=_unit_selection(),
            datasheet=replace(datasheet, source_ids=("datasheet:altered",)),
        )
    with pytest.raises(UnitFactoryError, match="base_size"):
        replace(model, base_size=cast(BaseSizeDefinition, "bad-base"))
    with pytest.raises(UnitFactoryError, match="wounds_remaining"):
        replace(model, starting_wounds=1, wounds_remaining=2)
    with pytest.raises(UnitFactoryError, match="characteristics"):
        replace(model, characteristics=())
    with pytest.raises(UnitFactoryError, match="own_models"):
        replace(unit, own_models=())
    with pytest.raises(UnitFactoryError, match="duplicate"):
        replace(unit, own_models=(model, model))
    with pytest.raises(UnitFactoryError, match="wargear_selections"):
        replace(unit, wargear_selections=cast(tuple[WargearSelection, ...], "bad-wargear"))
    with pytest.raises(UnitFactoryError, match="must not include"):
        replace(unit, unit_instance_id="unit:bad")
    with pytest.raises(UnitFactoryError, match="must be a string"):
        replace(model, model_instance_id=cast(str, 1))
