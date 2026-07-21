from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
from dataclasses import replace
from datetime import date
from typing import Any, cast

import pytest

from warhammer40k_core.core import army_catalog as army_catalog_module
from warhammer40k_core.core import datasheet as datasheet_module
from warhammer40k_core.core.army_catalog import (
    ArmyCatalog,
    ArmyCatalogError,
    ArmyCatalogPayload,
)
from warhammer40k_core.core.attachment_eligibility import (
    AttachmentEligibility,
    AttachmentRole,
    AttachmentTargetEligibility,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.content_scope import CatalogContentScope
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    BaseSizeKind,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DamagedEffectDefinition,
    DamagedEffectKind,
    DamagedWeaponScope,
    DatasheetCatalogError,
    DatasheetKeywordSet,
    DatasheetMusteringOption,
    DatasheetMusteringOptionEffect,
    DatasheetMusteringOptionEffectKind,
    DatasheetWargearOption,
    DatasheetWargearOptionCondition,
    DatasheetWargearOptionEffect,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.detachment import (
    DetachmentCatalogError,
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    RulesetDescriptorError,
    SetupSequenceDescriptor,
    SetupStepKind,
)
from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    DataPackageError,
    DataPackageId,
    RulesetBundle,
    SourceDocumentId,
)
from warhammer40k_core.rules.source_catalog import (
    SourceCatalog,
    SourceCatalogError,
    SourceCatalogPayload,
    SourceDocument,
)
from warhammer40k_core.rules.source_data import RuleSourceText


def test_source_catalog_round_trips_source_package_identity_without_object_reprs() -> None:
    package_id = DataPackageId(
        namespace="core-v2",
        package_name="phase9a-canonical",
        version="0.1.0",
    )
    catalog_version = CatalogVersion.dated(
        version_id="phase9a-canonical",
        source_date=date(2026, 5, 26),
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id="canonical-datasheets",
    )
    source_text = RuleSourceText.from_raw(
        source_id="datasheet:core-deep-strike-unit:ability:deep-strike",
        raw_text="deep strike: this unsupported deployment rule is source-linked.",
    )
    document = SourceDocument(
        document_id=document_id,
        title="Canonical datasheets",
        source_texts=(source_text,),
    )
    bundle = RulesetBundle(
        bundle_id="phase9a-core-v2",
        ruleset_id=RulesetId.warhammer_40000_eleventh(version="core-v2-phase9a"),
        package_id=package_id,
        catalog_version=catalog_version,
        source_document_ids=(document_id,),
    )
    catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(document,),
        ruleset_bundles=(bundle,),
    )
    payload = cast(
        SourceCatalogPayload,
        json.loads(json.dumps(catalog.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert package_id.stable_identity() == "data-package:core-v2:phase9a-canonical:0.1.0"
    assert catalog.source_text_by_id(source_text.source_id).normalized_text == (
        "deep strike: this unsupported deployment rule is source-linked."
    )
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert SourceCatalog.from_payload(payload).to_payload() == catalog.to_payload()


def test_source_catalog_rejects_inconsistent_package_links() -> None:
    package_id = DataPackageId(namespace="core-v2", package_name="primary", version="1")
    other_package_id = DataPackageId(namespace="core-v2", package_name="other", version="1")
    catalog_version = CatalogVersion.dated(version_id="v1", source_date=date(2026, 5, 26))
    document = SourceDocument(
        document_id=SourceDocumentId(package_id=other_package_id, document_id="doc"),
        title="Wrong package",
        source_texts=(RuleSourceText.from_raw(source_id="rule:one", raw_text="Blast."),),
    )

    with pytest.raises(SourceCatalogError, match="packages"):
        SourceCatalog(
            package_id=package_id,
            catalog_version=catalog_version,
            documents=(document,),
        )

    with pytest.raises(DataPackageError):
        CatalogVersion(version_id="v1", source_date="not-a-date")


def test_source_catalog_rejects_ambiguous_source_documents() -> None:
    package_id = DataPackageId(namespace="core-v2", package_name="primary", version="1")
    document_id = SourceDocumentId(package_id=package_id, document_id="doc")
    source_text = RuleSourceText.from_raw(source_id="rule:one", raw_text="Blast.")
    document = SourceDocument(
        document_id=document_id,
        title="Primary",
        source_texts=(source_text,),
    )

    with pytest.raises(SourceCatalogError, match="not found"):
        document.source_text_by_id("missing")
    with pytest.raises(SourceCatalogError, match="duplicate"):
        SourceDocument(
            document_id=document_id,
            title="Duplicate sources",
            source_texts=(source_text, source_text),
        )
    with pytest.raises(SourceCatalogError, match="duplicate"):
        SourceCatalog(
            package_id=package_id,
            catalog_version=CatalogVersion.dated(version_id="v1", source_date=date(2026, 5, 26)),
            documents=(document, document),
        )


def test_army_catalog_round_trips_canonical_phase9a_content_pack() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    payload = cast(
        ArmyCatalogPayload,
        json.loads(json.dumps(catalog.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)
    deep_strike = catalog.datasheet_by_id("core-deep-strike-unit")
    infantry = catalog.datasheet_by_id("core-intercessor-like-infantry")
    leader = catalog.datasheet_by_id("core-character-leader")
    support = catalog.datasheet_by_id("core-character-support")
    infantry_profile = infantry.model_profile_by_id("core-intercessor-like")

    assert len(catalog.datasheets) == 7
    assert catalog.faction_by_id("core-marine-force").faction_keywords == ("CORE MARINES",)
    assert catalog.detachments[0].detachment_point_cost == 1
    assert catalog.detachments[0].force_disposition_ids == ("purge-the-foe",)
    assert "core-intercessor-like-infantry" in catalog.detachments[0].unit_datasheet_ids
    assert infantry_profile.characteristic(Characteristic.MOVEMENT).final == 6
    assert deep_strike.abilities[0].support is CatalogAbilitySupport.UNSUPPORTED
    assert deep_strike.abilities[0].source_id == (
        "datasheet:core-deep-strike-unit:ability:deep-strike"
    )
    assert leader.attachment_eligibilities[0].role is AttachmentRole.LEADER
    assert tuple(
        target.bodyguard_datasheet_id for target in leader.attachment_eligibilities[0].targets
    ) == (infantry.datasheet_id,)
    assert support.attachment_eligibilities[0].role is AttachmentRole.SUPPORT
    assert tuple(
        target.bodyguard_datasheet_id for target in support.attachment_eligibilities[0].targets
    ) == (infantry.datasheet_id,)
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert ArmyCatalog.from_payload(payload).to_payload() == catalog.to_payload()


def test_army_catalog_rejects_attachment_targets_outside_the_catalog() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    leader = catalog.datasheet_by_id("core-character-leader")
    invalid_leader = replace(
        leader,
        attachment_eligibilities=(
            AttachmentEligibility(
                role=AttachmentRole.LEADER,
                targets=(
                    AttachmentTargetEligibility(
                        bodyguard_datasheet_id="missing-bodyguard",
                        source_ids=("test:missing-bodyguard-attachment",),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(ArmyCatalogError, match="unknown bodyguard datasheet"):
        replace(
            catalog,
            datasheets=tuple(
                invalid_leader if datasheet.datasheet_id == leader.datasheet_id else datasheet
                for datasheet in catalog.datasheets
            ),
        )


def test_catalog_keyword_tokens_are_canonicalized_at_data_boundary() -> None:
    keywords = DatasheetKeywordSet(
        keywords=("Infantry", "Battleline"),
        faction_keywords=("Astra Militarum",),
    )
    faction = FactionDefinition(
        faction_id="astra-militarum",
        name="Astra Militarum",
        faction_keywords=("Astra Militarum",),
    )
    enhancement = EnhancementDefinition(
        enhancement_id="test-enhancement",
        name="Test Enhancement",
        source_id="phase9a:test-enhancement",
        target_required_keywords=("Character",),
        target_required_faction_keywords=("Adeptus Astartes",),
    )
    mustering_keyword_effect = DatasheetMusteringOptionEffect(
        kind=DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
        keyword="Jump Pack",
    )

    assert keywords.keywords == ("BATTLELINE", "INFANTRY")
    assert keywords.faction_keywords == ("ASTRA MILITARUM",)
    assert faction.faction_keywords == ("ASTRA MILITARUM",)
    assert enhancement.target_required_keywords == ("CHARACTER",)
    assert enhancement.target_required_faction_keywords == ("ADEPTUS ASTARTES",)
    assert mustering_keyword_effect.keyword == "JUMP PACK"

    with pytest.raises(DatasheetCatalogError, match="must not contain duplicates"):
        DatasheetKeywordSet(keywords=("Infantry", "INFANTRY"))


def test_datasheet_catalog_keeps_base_facts_as_core_catalog_data() -> None:
    oval = BaseSizeDefinition.oval(length_mm=75.0, width_mm=42.0)
    rectangle = BaseSizeDefinition.rectangular(length_mm=100.0, width_mm=60.0)

    assert oval.to_payload()["kind"] == "oval"
    assert rectangle.to_payload()["width_mm"] == 60.0

    with pytest.raises(DatasheetCatalogError):
        BaseSizeDefinition(
            kind=cast(BaseSizeKind, "circular"),
            diameter_mm=32.0,
            length_mm=1.0,
        )
    with pytest.raises(DatasheetCatalogError):
        BaseSizeDefinition.oval(length_mm=25.0, width_mm=32.0)
    with pytest.raises(DatasheetCatalogError):
        BaseSizeDefinition(kind=cast(BaseSizeKind, "unsupported"), diameter_mm=32.0)


def test_model_profiles_fail_fast_when_required_characteristics_are_missing() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    profile = catalog.datasheet_by_id("core-intercessor-like-infantry").model_profile_by_id(
        "core-intercessor-like"
    )

    for missing_characteristic in (
        Characteristic.BALLISTIC_SKILL,
        Characteristic.OBJECTIVE_CONTROL,
    ):
        with pytest.raises(DatasheetCatalogError, match="missing required characteristics"):
            replace(
                profile,
                characteristics=tuple(
                    value
                    for value in profile.characteristics
                    if value.characteristic is not missing_characteristic
                ),
            )


def test_detachment_catalog_objects_are_data_not_behavior() -> None:
    enhancement = EnhancementDefinition(
        enhancement_id="core-enhancement",
        name="Core Enhancement",
        source_id="enhancement:core-enhancement",
        subtypes=(EnhancementSubtype.UPGRADE,),
        points=10,
        ability_descriptor_ids=("ability:core-enhancement",),
    )
    stratagem = StratagemDefinition(
        stratagem_id="core-stratagem",
        name="Core Stratagem",
        source_id="stratagem:core-stratagem",
        command_point_cost=1,
        timing_tags=("command_phase",),
        ability_descriptor_ids=("ability:core-stratagem",),
    )
    detachment = DetachmentDefinition(
        detachment_id="core-detachment",
        name="Core Detachment",
        faction_id="core-marine-force",
        detachment_point_cost=2,
        unit_datasheet_ids=("core-intercessor-like-infantry",),
        force_disposition_ids=("take-and-hold",),
        enhancement_ids=(enhancement.enhancement_id,),
        stratagem_ids=(stratagem.stratagem_id,),
    )

    assert EnhancementDefinition.from_payload(enhancement.to_payload()) == enhancement
    assert enhancement.to_payload()["subtypes"] == ["upgrade"]
    assert StratagemDefinition.from_payload(stratagem.to_payload()) == stratagem
    assert DetachmentDefinition.from_payload(detachment.to_payload()) == detachment
    assert enhancement.stable_identity() == "enhancement:core-enhancement"
    assert stratagem.stable_identity() == "stratagem:core-stratagem"
    assert detachment.stable_identity() == "detachment:core-detachment"
    assert detachment.detachment_point_cost == 2
    assert detachment.unit_datasheet_ids == ("core-intercessor-like-infantry",)
    assert detachment.force_disposition_ids == ("take-and-hold",)

    with pytest.raises(DetachmentCatalogError):
        EnhancementDefinition(
            enhancement_id="enhancement:prefixed",
            name="Bad",
            source_id="enhancement:bad",
            subtypes=cast(tuple[EnhancementSubtype, ...], ("upgrade", "upgrade")),
            points=-1,
        )
    with pytest.raises(DetachmentCatalogError, match="Subtype"):
        EnhancementDefinition(
            enhancement_id="bad-subtype",
            name="Bad Subtype",
            source_id="enhancement:bad-subtype",
            subtypes=cast(tuple[EnhancementSubtype, ...], ("not-a-subtype",)),
            points=0,
        )
    with pytest.raises(DetachmentCatalogError):
        StratagemDefinition(
            stratagem_id="bad",
            name="Bad",
            source_id="stratagem:bad",
            command_point_cost=-1,
        )
    with pytest.raises(DetachmentCatalogError, match="between 1 and 3"):
        replace(detachment, detachment_point_cost=4)


def test_army_catalog_rejects_ambiguous_or_missing_catalog_links() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    broken_datasheet = replace(
        datasheet,
        wargear_options=(
            DatasheetWargearOption(
                option_id="broken-default",
                model_profile_id="core-intercessor-like",
                default_wargear_ids=("missing-wargear",),
                allowed_wargear_ids=("missing-wargear",),
                min_selections=1,
                max_selections=1,
            ),
        ),
    )

    with pytest.raises(ArmyCatalogError, match="unknown wargear"):
        ArmyCatalog(
            catalog_id="broken",
            ruleset_id=catalog.ruleset_id,
            source_package_id=catalog.source_package_id,
            datasheets=(broken_datasheet,),
            wargear=catalog.wargear,
            factions=catalog.factions,
        )

    with pytest.raises(ArmyCatalogError, match="duplicate datasheet"):
        ArmyCatalog(
            catalog_id="duplicate",
            ruleset_id=catalog.ruleset_id,
            source_package_id=catalog.source_package_id,
            datasheets=(datasheet, datasheet),
            wargear=catalog.wargear,
            factions=catalog.factions,
        )


def test_army_catalog_rejects_unsupported_active_content_scopes() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()

    with pytest.raises(ArmyCatalogError, match="unsupported datasheet content scope"):
        ArmyCatalog(
            catalog_id="legends-datasheet",
            ruleset_id=catalog.ruleset_id,
            source_package_id=catalog.source_package_id,
            datasheets=(
                replace(catalog.datasheets[0], content_scope=CatalogContentScope.LEGENDS),
                *catalog.datasheets[1:],
            ),
            wargear=catalog.wargear,
            factions=catalog.factions,
            army_rules=catalog.army_rules,
            detachments=catalog.detachments,
        )

    with pytest.raises(ArmyCatalogError, match="unsupported detachment content scope"):
        ArmyCatalog(
            catalog_id="combat-patrol-detachment",
            ruleset_id=catalog.ruleset_id,
            source_package_id=catalog.source_package_id,
            datasheets=catalog.datasheets,
            wargear=catalog.wargear,
            factions=catalog.factions,
            army_rules=catalog.army_rules,
            detachments=(
                replace(
                    catalog.detachments[0],
                    content_scope=CatalogContentScope.COMBAT_PATROL,
                ),
            ),
        )


def test_datasheet_wargear_options_reject_defaults_that_exceed_max_selections() -> None:
    with pytest.raises(DatasheetCatalogError, match="default_wargear_ids"):
        DatasheetWargearOption(
            option_id="bad-default-cardinality",
            model_profile_id="core-intercessor-like",
            default_wargear_ids=("a", "b", "c"),
            allowed_wargear_ids=("a", "b", "c"),
            min_selections=0,
            max_selections=1,
        )


def test_army_catalog_validates_detachment_content_links() -> None:
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
    valid_catalog = ArmyCatalog(
        catalog_id="with-detachment-content",
        ruleset_id=catalog.ruleset_id,
        source_package_id=catalog.source_package_id,
        datasheets=catalog.datasheets,
        wargear=catalog.wargear,
        factions=catalog.factions,
        army_rules=catalog.army_rules,
        detachments=(detachment,),
        enhancements=(enhancement,),
        stratagems=(stratagem,),
    )

    assert valid_catalog.detachments[0].enhancement_ids == (enhancement.enhancement_id,)

    with pytest.raises(ArmyCatalogError, match="unknown enhancement"):
        ArmyCatalog(
            catalog_id="missing-enhancement",
            ruleset_id=catalog.ruleset_id,
            source_package_id=catalog.source_package_id,
            datasheets=catalog.datasheets,
            wargear=catalog.wargear,
            factions=catalog.factions,
            army_rules=catalog.army_rules,
            detachments=(detachment,),
            stratagems=(stratagem,),
        )


def test_army_catalog_collection_validators_fail_fast_for_shape_type_and_identity() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    enhancement = EnhancementDefinition(
        enhancement_id="test-enhancement",
        name="Test Enhancement",
        source_id="source:test-enhancement",
    )
    stratagem = StratagemDefinition(
        stratagem_id="test-stratagem",
        name="Test Stratagem",
        source_id="source:test-stratagem",
        command_point_cost=1,
    )
    validator_cases: tuple[tuple[Any, object, bool], ...] = (
        (army_catalog_module._validate_datasheet_tuple, catalog.datasheets[0], True),
        (army_catalog_module._validate_wargear_tuple, catalog.wargear[0], True),
        (army_catalog_module._validate_faction_tuple, catalog.factions[0], True),
        (army_catalog_module._validate_army_rule_tuple, catalog.army_rules[0], False),
        (army_catalog_module._validate_detachment_tuple, catalog.detachments[0], False),
        (army_catalog_module._validate_enhancement_tuple, enhancement, False),
        (army_catalog_module._validate_stratagem_tuple, stratagem, False),
    )

    for validator, valid_item, rejects_empty in validator_cases:
        with pytest.raises(ArmyCatalogError, match="must be a tuple"):
            cast(Any, validator)("test values", [valid_item])
        if rejects_empty:
            with pytest.raises(ArmyCatalogError, match="must not be empty"):
                cast(Any, validator)("test values", ())
        with pytest.raises(ArmyCatalogError, match="must contain"):
            cast(Any, validator)("test values", (object(),))
        with pytest.raises(ArmyCatalogError, match="duplicate"):
            cast(Any, validator)("test values", (valid_item, valid_item))

    assert army_catalog_module._validate_identifier_tuple("ids", ("z", "a")) == ("a", "z")
    with pytest.raises(ArmyCatalogError, match="must be a tuple"):
        army_catalog_module._validate_identifier_tuple("ids", cast(Any, ["id"]))
    with pytest.raises(ArmyCatalogError, match="duplicates"):
        army_catalog_module._validate_identifier_tuple("ids", ("id", "id"))
    with pytest.raises(ArmyCatalogError, match="stable identity prefix"):
        army_catalog_module._validate_unprefixed_identifier("catalog_id", "catalog:bad", "catalog:")


def test_army_catalog_link_validators_reject_each_unknown_reference_family() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheets[0]
    model_profile_id = datasheet.model_profiles[0].model_profile_id
    wargear_id = catalog.wargear[0].wargear_id
    faction = catalog.factions[0]
    detachment = catalog.detachments[0]
    enhancement = EnhancementDefinition(
        enhancement_id="test-enhancement",
        name="Test Enhancement",
        source_id="source:test-enhancement",
    )
    stratagem = StratagemDefinition(
        stratagem_id="test-stratagem",
        name="Test Stratagem",
        source_id="source:test-stratagem",
        command_point_cost=1,
    )

    for keywords, message in (((), "declare faction"), (("UNKNOWN",), "match a faction")):
        invalid_datasheet = replace(
            datasheet,
            keywords=replace(datasheet.keywords, faction_keywords=keywords),
        )
        with pytest.raises(ArmyCatalogError, match=message):
            army_catalog_module._validate_datasheet_faction_keywords(
                (invalid_datasheet,),
                catalog.factions,
            )

    replacement_effect = DatasheetWargearOptionEffect(
        kind=WargearOptionEffectKind.REPLACE_WARGEAR,
        wargear_id=wargear_id,
        replaced_wargear_id="missing-wargear",
        model_count=1,
        wargear_count=1,
    )
    replacement_option = DatasheetWargearOption(
        option_id="broken-replacement",
        model_profile_id=model_profile_id,
        default_wargear_ids=(wargear_id,),
        allowed_wargear_ids=(wargear_id,),
        effects=(replacement_effect,),
    )
    replacement_reference_option = DatasheetWargearOption(
        option_id="replacement-reference",
        model_profile_id=model_profile_id,
        default_wargear_ids=(),
        allowed_wargear_ids=("missing-wargear",),
    )
    with pytest.raises(ArmyCatalogError, match="replacement effect"):
        army_catalog_module._validate_datasheet_wargear_links(
            (
                replace(
                    datasheet,
                    wargear_options=(replacement_option, replacement_reference_option),
                ),
            ),
            catalog.wargear,
        )

    mustering_option = DatasheetMusteringOption(
        option_id="broken-mustering-wargear",
        selection_group_id="test-group",
        label="Broken mustering wargear",
        model_profile_id=model_profile_id,
        effects=(
            DatasheetMusteringOptionEffect(
                kind=DatasheetMusteringOptionEffectKind.ADD_WARGEAR,
                wargear_id="missing-wargear",
                model_count=1,
                wargear_count=1,
            ),
        ),
    )
    with pytest.raises(ArmyCatalogError, match="mustering option"):
        army_catalog_module._validate_datasheet_wargear_links(
            (replace(datasheet, mustering_options=(mustering_option,)),),
            catalog.wargear,
        )

    with pytest.raises(ArmyCatalogError, match="unknown army rule"):
        army_catalog_module._validate_faction_rule_links(
            (replace(faction, army_rule_ids=("missing-rule",)),),
            catalog.army_rules,
        )

    detachment_link_cases = (
        (replace(detachment, faction_id="missing-faction"), "unknown faction"),
        (replace(detachment, unit_datasheet_ids=("missing-datasheet",)), "unknown datasheet"),
        (replace(detachment, enhancement_ids=("missing-enhancement",)), "unknown enhancement"),
        (replace(detachment, stratagem_ids=("missing-stratagem",)), "unknown stratagem"),
    )
    for invalid_detachment, message in detachment_link_cases:
        with pytest.raises(ArmyCatalogError, match=message):
            army_catalog_module._validate_detachment_links(
                (invalid_detachment,),
                catalog.datasheets,
                catalog.factions,
                (enhancement,),
                (stratagem,),
            )


def test_army_catalog_rejects_unsupported_scope_for_every_catalog_owner() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    enhancement = EnhancementDefinition(
        enhancement_id="test-enhancement",
        name="Test Enhancement",
        source_id="source:test-enhancement",
    )
    stratagem = StratagemDefinition(
        stratagem_id="test-stratagem",
        name="Test Stratagem",
        source_id="source:test-stratagem",
        command_point_cost=1,
    )
    collections: dict[str, Any] = {
        "datasheets": catalog.datasheets,
        "factions": catalog.factions,
        "army_rules": catalog.army_rules,
        "detachments": catalog.detachments,
        "enhancements": (enhancement,),
        "stratagems": (stratagem,),
    }

    for field_name, values in collections.items():
        invalid_values = (replace(values[0], content_scope=CatalogContentScope.LEGENDS),)
        arguments = dict(collections)
        arguments[field_name] = invalid_values
        with pytest.raises(
            ArmyCatalogError, match=f"unsupported {field_name[:-1].replace('_', ' ')}"
        ):
            cast(Any, army_catalog_module._validate_supported_content_scopes)(**arguments)


def test_army_catalog_payload_boundaries_translate_owned_domain_errors() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    payload = catalog.to_payload()
    invalid_payload_cases: tuple[tuple[Any, dict[str, object], str], ...] = (
        (
            army_catalog_module._ruleset_id_from_payload,
            {**payload["ruleset_id"], "edition": ""},
            "ruleset_id payload",
        ),
        (
            army_catalog_module._datasheet_from_payload,
            {**payload["datasheets"][0], "datasheet_id": "datasheet:bad"},
            "datasheet payload",
        ),
        (
            army_catalog_module._wargear_from_payload,
            {**payload["wargear"][0], "wargear_id": "wargear:bad"},
            "wargear payload",
        ),
        (
            army_catalog_module._faction_from_payload,
            {**payload["factions"][0], "faction_id": "faction:bad"},
            "faction payload",
        ),
        (
            army_catalog_module._army_rule_from_payload,
            {**payload["army_rules"][0], "rule_id": "army-rule:bad"},
            "army rule payload",
        ),
        (
            army_catalog_module._detachment_from_payload,
            {**payload["detachments"][0], "detachment_id": "detachment:bad"},
            "detachment payload",
        ),
        (
            army_catalog_module._enhancement_from_payload,
            {
                "enhancement_id": "enhancement:bad",
                "name": "Bad",
                "source_id": "source:bad",
                "content_scope": "matched_play",
                "subtypes": [],
                "points": 0,
                "target_required_keywords": [],
                "target_required_faction_keywords": [],
                "ability_descriptor_ids": [],
            },
            "enhancement payload",
        ),
        (
            army_catalog_module._stratagem_from_payload,
            {
                "stratagem_id": "stratagem:bad",
                "name": "Bad",
                "source_id": "source:bad",
                "content_scope": "matched_play",
                "command_point_cost": 1,
                "timing_tags": [],
                "ability_descriptor_ids": [],
            },
            "stratagem payload",
        ),
    )

    for loader, invalid_payload, message in invalid_payload_cases:
        with pytest.raises(ArmyCatalogError, match=message):
            cast(Any, loader)(invalid_payload)


@pytest.mark.parametrize(
    ("converter", "enum_value"),
    [
        (datasheet_module.base_size_kind_from_token, BaseSizeKind.CIRCULAR),
        (datasheet_module.catalog_ability_support_from_token, CatalogAbilitySupport.UNSUPPORTED),
        (
            datasheet_module.catalog_ability_source_kind_from_token,
            CatalogAbilitySourceKind.DATASHEET,
        ),
        (datasheet_module.damaged_effect_kind_from_token, DamagedEffectKind.HIT_ROLL_MODIFIER),
        (datasheet_module.damaged_weapon_scope_from_token, DamagedWeaponScope.ALL),
        (
            datasheet_module.wargear_option_condition_kind_from_token,
            WargearOptionConditionKind.MODEL_EQUIPPED_WITH,
        ),
        (
            datasheet_module.wargear_option_effect_kind_from_token,
            WargearOptionEffectKind.ADD_WARGEAR,
        ),
        (
            datasheet_module.datasheet_mustering_option_effect_kind_from_token,
            DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
        ),
    ],
)
def test_datasheet_enum_boundaries_accept_members_and_reject_bad_tokens(
    converter: Any,
    enum_value: object,
) -> None:
    assert converter(enum_value) is enum_value
    with pytest.raises(DatasheetCatalogError, match="must be a string"):
        converter(1)
    with pytest.raises(DatasheetCatalogError, match="Unsupported"):
        converter("not-supported")


def test_datasheet_scalar_and_json_validators_cover_fail_fast_boundaries() -> None:
    assert datasheet_module.damaged_weapon_scope_from_token(None) is None
    assert datasheet_module._validate_optional_identifier("id", None) is None
    assert datasheet_module._validate_optional_int("count", None) is None
    assert datasheet_module._validate_optional_positive_int("count", None) is None
    assert datasheet_module._validate_json_value("value", None) is None
    assert datasheet_module._validate_json_value("value", True) is True
    assert datasheet_module._validate_json_value("value", 2) == 2
    assert datasheet_module._validate_json_value("value", "text") == "text"
    assert datasheet_module._validate_json_value("value", 2.5) == 2.5
    assert datasheet_module._validate_json_value("value", [1, {"key": False}]) == [
        1,
        {"key": False},
    ]
    assert datasheet_module._validate_positive_number("size", 2) == 2.0
    assert datasheet_module._validate_positive_int("count", 2) == 2
    assert datasheet_module._validate_non_negative_int("count", 0) == 0
    assert datasheet_module._validate_optional_int("count", 0) == 0
    assert datasheet_module._validate_optional_positive_int("count", 1) == 1

    invalid_calls: tuple[tuple[Any, tuple[object, ...], str], ...] = (
        (datasheet_module._validate_json_object, ("value", []), "JSON object"),
        (datasheet_module._validate_json_value, ("value", float("inf")), "finite"),
        (datasheet_module._validate_json_value, ("value", (1,)), "JSON-safe"),
        (datasheet_module._validate_json_object_tuple, ("value", []), "tuple"),
        (datasheet_module._validate_positive_number, ("size", True), "number"),
        (datasheet_module._validate_positive_number, ("size", float("nan")), "finite"),
        (datasheet_module._validate_positive_number, ("size", 0), "greater than 0"),
        (datasheet_module._validate_positive_int, ("count", True), "integer"),
        (datasheet_module._validate_positive_int, ("count", 0), "at least 1"),
        (datasheet_module._validate_non_negative_int, ("count", True), "integer"),
        (datasheet_module._validate_non_negative_int, ("count", -1), "negative"),
        (datasheet_module._validate_optional_int, ("count", "1"), "integer"),
        (datasheet_module._validate_optional_positive_int, ("count", 0), "at least 1"),
    )
    for validator, arguments, message in invalid_calls:
        with pytest.raises(DatasheetCatalogError, match=message):
            cast(Any, validator)(*arguments)

    with pytest.raises(DatasheetCatalogError, match="stable identity prefix"):
        datasheet_module._validate_unprefixed_identifier("id", "ability:bad", "ability:")
    with pytest.raises(DatasheetCatalogError, match="must be a tuple"):
        datasheet_module._validate_identifier_tuple("ids", cast(Any, ["id"]))
    with pytest.raises(DatasheetCatalogError, match="at least 1"):
        datasheet_module._validate_identifier_tuple("ids", (), min_length=1)
    with pytest.raises(DatasheetCatalogError, match="duplicates"):
        datasheet_module._validate_identifier_tuple(
            "ids",
            ("Jump Pack", "JUMP PACK"),
            canonicalize_keywords=True,
        )
    with pytest.raises(DatasheetCatalogError, match="content_scope is invalid"):
        datasheet_module._catalog_content_scope_from_token("content_scope", "unsupported")
    with pytest.raises(DatasheetCatalogError, match="Characteristic token"):
        datasheet_module._characteristic_from_token("unsupported")
    with pytest.raises(DatasheetCatalogError, match="CharacteristicValue payload"):
        datasheet_module._characteristic_value_from_payload(cast(Any, {"characteristic": "bad"}))


def test_datasheet_collection_validators_reject_invalid_shapes_and_duplicates() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheets[0]
    ability = catalog.datasheet_by_id("core-deep-strike-unit").abilities[0]
    attachment = catalog.datasheet_by_id("core-character-leader").attachment_eligibilities[0]
    damaged_effect = DamagedEffectDefinition(
        damaged_effect_id="test-damaged",
        model_profile_id=datasheet.model_profiles[0].model_profile_id,
        wounds_min=1,
        wounds_max=2,
        effect_kind=DamagedEffectKind.HIT_ROLL_MODIFIER,
        modifier=-1,
        source_id="source:test-damaged",
    )
    condition = DatasheetWargearOptionCondition(
        kind=WargearOptionConditionKind.MODEL_EQUIPPED_WITH,
        wargear_ids=(catalog.wargear[0].wargear_id,),
    )
    effect = DatasheetWargearOptionEffect(
        kind=WargearOptionEffectKind.ADD_WARGEAR,
        wargear_id=catalog.wargear[0].wargear_id,
        model_count=1,
        wargear_count=1,
    )
    mustering_effect = DatasheetMusteringOptionEffect(
        kind=DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
        keyword="Character",
    )
    mustering_option = DatasheetMusteringOption(
        option_id="test-mustering",
        selection_group_id="test-group",
        label="Test mustering",
        effects=(mustering_effect,),
    )
    cases: tuple[tuple[Any, object, bool, bool], ...] = (
        (datasheet_module._validate_model_profile_tuple, datasheet.model_profiles[0], True, True),
        (datasheet_module._validate_composition_tuple, datasheet.composition[0], True, True),
        (
            datasheet_module._validate_wargear_option_tuple,
            datasheet.wargear_options[0],
            False,
            True,
        ),
        (datasheet_module._validate_wargear_option_condition_tuple, condition, False, False),
        (datasheet_module._validate_wargear_option_effect_tuple, effect, False, False),
        (datasheet_module._validate_mustering_option_tuple, mustering_option, False, True),
        (datasheet_module._validate_mustering_option_effect_tuple, mustering_effect, True, False),
        (datasheet_module._validate_ability_descriptor_tuple, ability, False, True),
        (datasheet_module._validate_damaged_effect_tuple, damaged_effect, False, True),
        (datasheet_module._validate_attachment_eligibility_tuple, attachment, False, True),
    )

    for validator, valid_item, rejects_empty, rejects_duplicate in cases:
        with pytest.raises(DatasheetCatalogError, match="must be a tuple"):
            cast(Any, validator)("test values", [valid_item])
        if rejects_empty:
            with pytest.raises(DatasheetCatalogError, match="must not be empty"):
                cast(Any, validator)("test values", ())
        with pytest.raises(DatasheetCatalogError, match="must contain"):
            cast(Any, validator)("test values", (object(),))
        if rejects_duplicate:
            with pytest.raises(DatasheetCatalogError, match="duplicate"):
                cast(Any, validator)("test values", (valid_item, valid_item))


def test_datasheet_damaged_and_effect_sort_contracts_reject_invalid_combinations() -> None:
    with pytest.raises(DatasheetCatalogError, match="require weapon scope"):
        datasheet_module._validate_damaged_weapon_scope(weapon_scope=None, weapon_names=())
    with pytest.raises(DatasheetCatalogError, match="require weapon_names"):
        datasheet_module._validate_damaged_weapon_scope(
            weapon_scope=DamagedWeaponScope.NAMED,
            weapon_names=(),
        )
    datasheet_module._validate_damaged_weapon_scope(
        weapon_scope=DamagedWeaponScope.NAMED,
        weapon_names=("test weapon",),
    )
    with pytest.raises(DatasheetCatalogError, match="must not include weapon_names"):
        datasheet_module._validate_damaged_weapon_scope(
            weapon_scope=DamagedWeaponScope.ALL,
            weapon_names=("test weapon",),
        )
    with pytest.raises(DatasheetCatalogError, match="must not include selection limits"):
        datasheet_module._validate_no_damaged_selection_limit(
            max_selections=1,
            baseline_max_selections=None,
            selection_group=None,
        )

    effect_order = (
        DatasheetWargearOptionEffect(
            kind=WargearOptionEffectKind.REPLACE_WARGEAR,
            wargear_id="replacement",
            replaced_wargear_id="original",
            model_count=1,
            wargear_count=1,
        ),
        DatasheetWargearOptionEffect(
            kind=WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED,
            wargear_id="replacement",
            replaced_wargear_id="original",
            model_count=1,
            wargear_count=0,
        ),
        DatasheetWargearOptionEffect(
            kind=WargearOptionEffectKind.ADD_WARGEAR,
            wargear_id="replacement",
            model_count=1,
            wargear_count=1,
        ),
        DatasheetWargearOptionEffect(
            kind=WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
            wargear_id="replacement",
            model_count=1,
            wargear_count=1,
        ),
    )
    assert tuple(
        datasheet_module._wargear_option_effect_sort_order(effect.kind) for effect in effect_order
    ) == (0, 1, 2, 2)
    with pytest.raises(DatasheetCatalogError, match="Unsupported WargearOptionEffectKind"):
        datasheet_module._wargear_option_effect_sort_order(cast(Any, "unsupported"))

    keyword_effect = DatasheetMusteringOptionEffect(
        kind=DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
        keyword="Character",
    )
    wargear_effect = DatasheetMusteringOptionEffect(
        kind=DatasheetMusteringOptionEffectKind.ADD_WARGEAR,
        wargear_id="test-wargear",
        model_count=1,
        wargear_count=1,
    )
    assert datasheet_module._mustering_option_effect_sort_key(keyword_effect)[0] == 0
    assert datasheet_module._mustering_option_effect_sort_key(wargear_effect)[0] == 1
    invalid_effect = object.__new__(DatasheetMusteringOptionEffect)
    object.__setattr__(invalid_effect, "kind", "unsupported")
    with pytest.raises(DatasheetCatalogError, match="Unsupported DatasheetMustering"):
        datasheet_module._mustering_option_effect_sort_key(invalid_effect)


def test_phase_sequence_descriptors_are_explicit_policy_data() -> None:
    setup_sequence = SetupSequenceDescriptor.warhammer_40000_eleventh_default()
    battle_sequence = BattlePhaseSequenceDescriptor.warhammer_40000_eleventh_default()

    assert setup_sequence.steps == (
        SetupStepKind.MUSTER_ARMIES,
        SetupStepKind.SELECT_MISSION,
        SetupStepKind.CREATE_BATTLEFIELD,
        SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
        SetupStepKind.SELECT_SECONDARY_MISSIONS,
        SetupStepKind.DECLARE_BATTLE_FORMATIONS,
        SetupStepKind.DEPLOY_ARMIES,
        SetupStepKind.REDEPLOY_UNITS,
        SetupStepKind.DETERMINE_FIRST_TURN,
        SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
    )
    assert battle_sequence.phases == (
        BattlePhaseKind.COMMAND,
        BattlePhaseKind.MOVEMENT,
        BattlePhaseKind.SHOOTING,
        BattlePhaseKind.CHARGE,
        BattlePhaseKind.FIGHT,
    )
    assert SetupSequenceDescriptor.from_payload(setup_sequence.to_payload()) == setup_sequence
    assert BattlePhaseSequenceDescriptor.from_payload(battle_sequence.to_payload()) == (
        battle_sequence
    )


def test_phase_sequence_descriptors_reject_driver_local_ambiguity() -> None:
    with pytest.raises(RulesetDescriptorError, match="unique"):
        SetupSequenceDescriptor(steps=(SetupStepKind.MUSTER_ARMIES, SetupStepKind.MUSTER_ARMIES))
    with pytest.raises(RulesetDescriptorError, match="unique"):
        BattlePhaseSequenceDescriptor(phases=(BattlePhaseKind.COMMAND, BattlePhaseKind.COMMAND))
    with pytest.raises(RulesetDescriptorError):
        SetupSequenceDescriptor.from_payload({"steps": ["unsupported"]})
