from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import (
    ArmyCatalog,
    ArmyCatalogError,
    ArmyCatalogPayload,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.content_scope import CatalogContentScope
from warhammer40k_core.core.datasheet import (
    AttachmentRole,
    BaseSizeDefinition,
    BaseSizeKind,
    CatalogAbilitySupport,
    DatasheetCatalogError,
    DatasheetWargearOption,
)
from warhammer40k_core.core.detachment import (
    DetachmentCatalogError,
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
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
    assert catalog.faction_by_id("core-marine-force").faction_keywords == ("CORE Marines",)
    assert catalog.detachments[0].detachment_point_cost == 1
    assert catalog.detachments[0].force_disposition_ids == ("purge-the-foe",)
    assert "core-intercessor-like-infantry" in catalog.detachments[0].unit_datasheet_ids
    assert infantry_profile.characteristic(Characteristic.MOVEMENT).final == 6
    assert deep_strike.abilities[0].support is CatalogAbilitySupport.UNSUPPORTED
    assert deep_strike.abilities[0].source_id == (
        "datasheet:core-deep-strike-unit:ability:deep-strike"
    )
    assert leader.attachment_eligibilities[0].role is AttachmentRole.LEADER
    assert leader.attachment_eligibilities[0].allowed_bodyguard_datasheet_ids == (
        infantry.datasheet_id,
    )
    assert support.attachment_eligibilities[0].role is AttachmentRole.SUPPORT
    assert support.attachment_eligibilities[0].allowed_bodyguard_datasheet_ids == (
        infantry.datasheet_id,
    )
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert ArmyCatalog.from_payload(payload).to_payload() == catalog.to_payload()


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
            points=-1,
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
