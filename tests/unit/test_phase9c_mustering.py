from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition, DatasheetDefinition
from warhammer40k_core.core.detachment import EnhancementDefinition, StratagemDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
    ArmyMusterRequest,
    ArmyMusterRequestPayload,
    muster_army,
)
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
    resolve_model_profile_selections,
    resolve_wargear_selections,
    validate_detachment_selection,
    validate_unit_selection_for_faction,
)
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
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
            detachment_id="core-combined-arms",
        ),
        unit_selections=unit_selections if unit_selections is not None else (_unit_selection(),),
        attachment_declarations=attachment_declarations,
    )


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
            detachment_id="core-combined-arms",
            enhancement_ids=(enhancement.enhancement_id,),
            stratagem_ids=(stratagem.stratagem_id,),
        ),
    )
    invalid_request = _muster_request(
        catalog_with_content,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
            enhancement_ids=("not-allowed",),
        ),
    )

    army = muster_army(catalog=catalog_with_content, request=valid_request)
    assert army.detachment_selection == valid_request.detachment_selection
    with pytest.raises(ArmyMusteringError, match="detachment selection"):
        muster_army(catalog=catalog_with_content, request=invalid_request)


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
            detachment_id="missing-detachment",
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
        detachment_id="core-combined-arms",
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
                detachment_id="core-combined-arms",
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
        DetachmentSelection(faction_id="faction:bad", detachment_id="core-combined-arms")
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
