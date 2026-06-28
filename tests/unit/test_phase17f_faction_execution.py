from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionContext,
    FactionRuleExecutionRegistry,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
    FactionRuleGenericIrExecutor,
    FactionRuleNamedHandler,
    default_faction_rule_execution_registry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27 as faction_execution_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
    Phase17ECoverageStatus,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionBlockReason,
    Phase17FExecutionPackage,
    Phase17FExecutionPackagePayload,
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
    Phase17FFactionExecutionError,
)

FADE_TO_DARKNESS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:fade_to_darkness:turn-end-reserves",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:fade_to_darkness:unit-destroyed",
)
LEAPING_SHADOWS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:leaping_shadows:scouts_9",
)
MANTLE_OF_GLOOM_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:mantle_of_gloom:objective-control",
)
MALICE_MADE_MANIFEST_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancement:malice_made_manifest",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:malice_made_manifest:mortal-wound-fnp",
)
BLOOD_LEGION_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:murdercall",
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:blood_tainted",
)
CAVALCADE_OF_CHAOS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:cavalcade_of_chaos:unholy_avalanche",
)
DAEMONIC_INCURSION_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts",
)
SHADOW_LEGION_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "murderers-cowl:advance-eligibility",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "shadows-caress:snap-target-restriction",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:shooting:lethal_hits",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:shooting:sustained_hits_1",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:fight:lethal_hits",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:fight:sustained_hits_1",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:attack-sequence-completed",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:mortal-wound-fnp",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:penumbral-puppetry:hit-roll",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:gloam-rot:wound-roll",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule:"
    "disciples-of-belakor:weapon-profile",
)
ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:battle-shock",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:movement",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:objective-control",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:save-option",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:unit-characteristic",
    "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command:weapon-profile",
)
LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:command-phase-start",
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:hit-roll",
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:wound-roll",
)
BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:black_templars:army_rule:templar_vows",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:abhor_the_witch:charge-declaration",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:abhor_the_witch:charge-targets",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:abhor_the_witch:melee-precision",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:accept_any_challenge:wound-roll",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:suffer_not_the_unclean:fall-back",
    "warhammer_40000_11th:black_templars:army_rule:templar_vows:"
    "uphold_the_honour:objective-control",
)
TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good",
    "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good:weapon-profile",
)
THOUSAND_SONS_CABAL_OF_SORCERERS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers",
    "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers:mortal-wound-feel-no-pain",
    "warhammer_40000_11th:thousand_sons:army_rule:cabal_of_sorcerers:weapon-profile",
)
TYRANIDS_SHADOW_IN_THE_WARP_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp",
    "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp:battle-shock",
    "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp:synapse:weapon-profile",
)
IMPERIAL_KNIGHTS_CODE_CHIVALRIC_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:eager:charge-roll",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:eager:movement-budget",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:enemy-unit-destroyed",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:end-battle-round",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:end-turn",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:legacy:leadership",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:legacy:objective-control",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:martial-valour:fight",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:martial-valour:shooting",
    "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric:oath-selection",
)
SOURCE_BACKED_ARMY_RULE_NAMES_BY_FACTION_ID = {
    "aeldari": "Battle Focus",
    "astra-militarum": "Voice of Command",
    "black-templars": "Templar Vows",
    "chaos-daemons": "The Shadow of Chaos",
    "chaos-knights": "Harbingers of Dread",
    "chaos-space-marines": "Dark Pacts",
    "death-guard": "Nurgle's Gift",
    "drukhari": "Power from Pain",
    "emperors-children": "Thrill Seekers",
    "genestealer-cults": "Cult Ambush",
    "grey-knights": "Gate of Infinity",
    "imperial-knights": "Code Chivalric",
    "leagues-of-votann": "Prioritised Efficiency",
    "necrons": "Reanimation Protocols",
    "orks": "Waaagh!",
    "space-marines": "Oath of Moment",
    "tau-empire": "For the Greater Good",
    "thousand-sons": "Cabal of Sorcerers",
    "tyranids": "Shadow in the Warp / Synapse",
    "world-eaters": "Blessings of Khorne",
}


def test_phase17f_execution_package_covers_every_phase17e_coverage_row() -> None:
    coverage_package = faction_coverage_source.phase17e_coverage_package()
    execution_package = faction_execution_source.phase17f_execution_package()
    records_by_coverage_id = {
        record.coverage_descriptor_id: record for record in execution_package.execution_records
    }

    assert set(records_by_coverage_id) == {
        row.descriptor_id for row in coverage_package.coverage_rows
    }
    for coverage_row in coverage_package.coverage_rows:
        execution_record = records_by_coverage_id[coverage_row.descriptor_id]
        assert execution_record.coverage_kind is coverage_row.coverage_kind
        assert execution_record.coverage_status is coverage_row.status
        assert execution_record.faction_id == coverage_row.faction_id
        assert execution_record.detachment_id == coverage_row.detachment_id
        assert execution_record.source_ids == coverage_row.source_ids
        assert execution_record.rule_id == coverage_row.rule_id
        assert execution_record.timing_descriptor == coverage_row.timing_descriptor
        assert execution_record.rule_category == coverage_row.rule_category
        assert execution_record.runtime_support_status == (
            None
            if coverage_row.runtime_support_status is None
            else coverage_row.runtime_support_status.value
        )
        assert execution_record.runtime_consumer_ids == coverage_row.runtime_consumer_ids


def test_phase17f_exact_enhancement_and_stratagem_execution_records_are_one_to_one() -> None:
    execution_package = faction_execution_source.phase17f_execution_package()
    exact_records = tuple(
        record
        for record in execution_package.execution_records
        if record.coverage_kind
        in {
            Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
            Phase17ECoverageKind.DETACHMENT_STRATAGEM,
        }
    )
    exact_coverage_rows = tuple(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind
        in {
            Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
            Phase17ECoverageKind.DETACHMENT_STRATAGEM,
        }
    )

    assert len(exact_records) == len(exact_coverage_rows)
    assert {record.coverage_descriptor_id for record in exact_records} == {
        row.descriptor_id for row in exact_coverage_rows
    }
    assert all(record.rule_id is not None for record in exact_records)
    assert all(record.timing_descriptor is not None for record in exact_records)
    assert all(record.rule_category is not None for record in exact_records)


def test_phase17f_fade_to_darkness_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.faction_id == "chaos-daemons"
        and record.detachment_id == "shadow-legion"
        and record.rule_id == "000009980004"
    )

    assert record.rule_name == "Fade to Darkness"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == FADE_TO_DARKNESS_RUNTIME_CONSUMERS
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == FADE_TO_DARKNESS_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_leaping_shadows_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.faction_id == "chaos-daemons"
        and record.detachment_id == "shadow-legion"
        and record.rule_id == "000009980002"
    )

    assert record.rule_name == "Leaping Shadows"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == LEAPING_SHADOWS_RUNTIME_CONSUMERS
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == LEAPING_SHADOWS_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_mantle_of_gloom_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.faction_id == "chaos-daemons"
        and record.detachment_id == "shadow-legion"
        and record.rule_id == "000009980003"
    )

    assert record.rule_name == "Mantle of Gloom (Aura)"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == MANTLE_OF_GLOOM_RUNTIME_CONSUMERS
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == MANTLE_OF_GLOOM_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_malice_made_manifest_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.faction_id == "chaos-daemons"
        and record.detachment_id == "shadow-legion"
        and record.rule_id == "000009980005"
    )

    assert record.rule_name == "Malice Made Manifest"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == MALICE_MADE_MANIFEST_RUNTIME_CONSUMERS
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == MALICE_MADE_MANIFEST_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


@pytest.mark.parametrize(
    ("detachment_id", "rule_name", "runtime_consumers"),
    [
        (
            "blood-legion",
            "Blood Legion detachment rule",
            BLOOD_LEGION_RUNTIME_CONSUMERS,
        ),
        (
            "cavalcade-of-chaos",
            "Cavalcade of Chaos detachment rule",
            CAVALCADE_OF_CHAOS_RUNTIME_CONSUMERS,
        ),
        (
            "daemonic-incursion",
            "Daemonic Incursion detachment rule",
            DAEMONIC_INCURSION_RUNTIME_CONSUMERS,
        ),
        (
            "shadow-legion",
            "Shadow Legion detachment rule",
            SHADOW_LEGION_RUNTIME_CONSUMERS,
        ),
    ],
)
def test_phase17f_chaos_daemons_detachment_rule_execution_record_is_named_handler(
    detachment_id: str,
    rule_name: str,
    runtime_consumers: tuple[str, ...],
) -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
        and record.faction_id == "chaos-daemons"
        and record.detachment_id == detachment_id
    )

    assert record.rule_name == rule_name
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(sorted(runtime_consumers))
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == runtime_consumers[0]
    assert record.block_reason is None


def test_phase17f_leagues_of_votann_army_rule_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "leagues-of-votann"
    )

    assert record.coverage_descriptor_id == "phase17e:leagues-of-votann:army-rule"
    assert record.rule_name == "Prioritised Efficiency"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS)
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_black_templars_army_rule_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "black-templars"
    )

    assert record.coverage_descriptor_id == "phase17e:black-templars:army-rule"
    assert record.execution_id == "phase17f:phase17e:black-templars:army-rule"
    assert record.rule_name == "Templar Vows"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMERS)
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_astra_militarum_army_rule_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "astra-militarum"
    )

    assert record.coverage_descriptor_id == "phase17e:astra-militarum:army-rule"
    assert record.execution_id == "phase17f:phase17e:astra-militarum:army-rule"
    assert record.rule_name == "Voice of Command"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS)
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_tau_empire_army_rule_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "tau-empire"
    )

    assert record.coverage_descriptor_id == "phase17e:tau-empire:army-rule"
    assert record.execution_id == "phase17f:phase17e:tau-empire:army-rule"
    assert record.rule_name == "For the Greater Good"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS)
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_thousand_sons_army_rule_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "thousand-sons"
    )

    assert record.coverage_descriptor_id == "phase17e:thousand-sons:army-rule"
    assert record.execution_id == "phase17f:phase17e:thousand-sons:army-rule"
    assert record.rule_name == "Cabal of Sorcerers"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(THOUSAND_SONS_CABAL_OF_SORCERERS_RUNTIME_CONSUMERS)
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == THOUSAND_SONS_CABAL_OF_SORCERERS_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_imperial_knights_army_rule_execution_record_is_named_handler() -> None:
    record = next(
        record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and record.faction_id == "imperial-knights"
    )

    assert record.coverage_descriptor_id == "phase17e:imperial-knights:army-rule"
    assert record.execution_id == "phase17f:phase17e:imperial-knights:army-rule"
    assert record.rule_name == "Code Chivalric"
    assert record.runtime_support_status == "engine_consumed"
    assert record.runtime_consumer_ids == tuple(
        sorted(IMPERIAL_KNIGHTS_CODE_CHIVALRIC_RUNTIME_CONSUMERS)
    )
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    assert record.handler_id == IMPERIAL_KNIGHTS_CODE_CHIVALRIC_RUNTIME_CONSUMERS[0]
    assert record.block_reason is None


def test_phase17f_source_backed_army_rule_execution_records_are_named_handlers() -> None:
    assert set(faction_coverage_source.FACTION_ARMY_RULE_RUNTIME_CONSUMER_IDS_BY_FACTION_ID) == set(
        SOURCE_BACKED_ARMY_RULE_NAMES_BY_FACTION_ID
    )
    execution_records_by_faction_id = {
        record.faction_id: record
        for record in faction_execution_source.phase17f_execution_package().execution_records
        if record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
    }

    for faction_id, rule_name in SOURCE_BACKED_ARMY_RULE_NAMES_BY_FACTION_ID.items():
        record = execution_records_by_faction_id[faction_id]
        runtime_consumers = tuple(
            sorted(
                faction_coverage_source.FACTION_ARMY_RULE_RUNTIME_CONSUMER_IDS_BY_FACTION_ID[
                    faction_id
                ]
            )
        )
        assert record.coverage_descriptor_id == f"phase17e:{faction_id}:army-rule"
        assert record.execution_id == f"phase17f:phase17e:{faction_id}:army-rule"
        assert record.rule_name == rule_name
        assert record.runtime_support_status == "engine_consumed"
        assert record.runtime_consumer_ids == runtime_consumers
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
        assert record.handler_id == runtime_consumers[0]
        assert record.block_reason is None


def test_phase17f_execution_payload_is_deterministic_json_safe_and_round_trips() -> None:
    package = faction_execution_source.phase17f_execution_package()
    payload = package.to_payload()

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert (
        payload["source_payload_checksum_sha256"]
        == (
            faction_execution_source.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        )
    )
    assert (
        payload["upstream_payload_checksum_sha256"]
        == (
            faction_coverage_source.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        )
    )
    assert Phase17FExecutionPackage.from_payload(payload) == package

    stale_payload = payload.copy()
    stale_payload["source_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(Phase17FFactionExecutionError, match="checksum is stale"):
        Phase17FExecutionPackage.from_payload(stale_payload)

    stale_upstream_payload = payload.copy()
    stale_upstream_payload["upstream_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(Phase17FFactionExecutionError, match="upstream payload checksum"):
        Phase17FExecutionPackage.from_payload(stale_upstream_payload)

    drifted_payload = package.to_payload()
    drifted_payload["execution_records"][0]["faction_name"] = "Drifted Faction Name"
    drifted_payload["source_payload_checksum_sha256"] = _payload_checksum(drifted_payload)
    with pytest.raises(Phase17FFactionExecutionError, match="does not match Phase17E"):
        Phase17FExecutionPackage.from_payload(drifted_payload)


def test_phase17f_execution_statuses_are_explicit_for_all_phase17e_rows() -> None:
    coverage_package = faction_coverage_source.phase17e_coverage_package()
    execution_package = faction_execution_source.phase17f_execution_package()
    coverage_status_counts = coverage_package.status_counts()
    execution_status_counts = execution_package.status_counts()

    assert execution_status_counts[Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR.value] == 0
    assert (
        execution_status_counts[Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER.value]
        == coverage_status_counts[Phase17ECoverageStatus.IMPLEMENTED.value]
    )
    assert (
        execution_status_counts[Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED.value]
        == coverage_status_counts[Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED.value]
    )
    assert (
        execution_status_counts[
            Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP.value
        ]
        == coverage_status_counts[Phase17ECoverageStatus.UNSUPPORTED.value]
    )
    assert len(execution_package.blocked_records()) == (
        len(execution_package.execution_records)
        - execution_status_counts[Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER.value]
    )
    assert execution_package.unapproved_blocked_records() == ()
    assert all(record.is_approved_blocked for record in execution_package.blocked_records())


def test_phase17f_registry_dispatches_every_record_without_missing_handlers() -> None:
    registry = default_faction_rule_execution_registry()
    context = _context()

    for record in registry.all_records():
        result = registry.execute(execution_id=record.execution_id, context=context)
        assert result.status is FactionRuleExecutionStatus.UNSUPPORTED
        assert result.source_ids == record.source_ids
        assert result.coverage_descriptor_id == record.coverage_descriptor_id
        if record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER:
            assert result.reason == "named_handler_not_registered"
        elif (
            record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
        ):
            assert result.reason == "structured_rule_semantics_required"
        else:
            assert result.reason == (
                f"approved_phase17e_source_gap:{record.phase17e_unsupported_reason}"
            )
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result


def test_phase17f_registry_rejects_unknown_execution_id() -> None:
    registry = default_faction_rule_execution_registry()

    with pytest.raises(GameLifecycleError, match="missing execution record"):
        registry.execute(execution_id="phase17f:missing", context=_context())


def test_phase17f_registry_rejects_invalid_registry_inputs_and_contexts() -> None:
    record = faction_execution_source.phase17f_execution_package().execution_records[0]

    with pytest.raises(GameLifecycleError, match="records must be a tuple"):
        FactionRuleExecutionRegistry.from_records(
            cast(tuple[Phase17FExecutionRecord, ...], [record])
        )

    with pytest.raises(GameLifecycleError, match="records must contain"):
        FactionRuleExecutionRegistry.from_records((cast(Phase17FExecutionRecord, object()),))

    with pytest.raises(GameLifecycleError, match="record IDs must be unique"):
        FactionRuleExecutionRegistry.from_records((record, record))

    with pytest.raises(GameLifecycleError, match="named_handlers must be a mapping"):
        FactionRuleExecutionRegistry.from_records(
            (record,),
            named_handlers=cast(Mapping[str, FactionRuleNamedHandler], object()),
        )

    with pytest.raises(GameLifecycleError, match="named handlers must be callable"):
        FactionRuleExecutionRegistry.from_records(
            (record,),
            named_handlers=cast(
                Mapping[str, FactionRuleNamedHandler],
                {"handler": object()},
            ),
        )

    with pytest.raises(GameLifecycleError, match="generic_ir_executor must be callable"):
        FactionRuleExecutionRegistry.from_records(
            (record,),
            generic_ir_executor=cast(FactionRuleGenericIrExecutor, object()),
        )

    registry = FactionRuleExecutionRegistry.from_records((record,))
    with pytest.raises(GameLifecycleError, match="requires a context"):
        registry.execute(
            execution_id=record.execution_id,
            context=cast(FactionRuleExecutionContext, object()),
        )


def test_phase17f_registry_rejects_executable_records_without_registered_executor() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    named_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
        block_reason=None,
    )
    generic_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
        block_reason=None,
        rule_ir_hash="0" * 64,
        execution_id=f"{blocked_record.execution_id}:generic",
    )
    registry = FactionRuleExecutionRegistry.from_records((named_record, generic_record))

    named_result = registry.execute(execution_id=named_record.execution_id, context=_context())
    generic_result = registry.execute(execution_id=generic_record.execution_id, context=_context())

    assert named_result.status is FactionRuleExecutionStatus.UNSUPPORTED
    assert named_result.reason == "named_handler_not_registered"
    assert generic_result.status is FactionRuleExecutionStatus.UNSUPPORTED
    assert generic_result.reason == "generic_ir_executor_not_registered"


def test_phase17f_registry_applies_executable_records_only_after_registered_executor_runs() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    named_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
        block_reason=None,
    )
    generic_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
        block_reason=None,
        rule_ir_hash="0" * 64,
        execution_id=f"{blocked_record.execution_id}:generic",
    )
    calls: list[str] = []
    handler_id = _require_handler_id(named_record)

    def named_handler(
        record: Phase17FExecutionRecord,
        context: FactionRuleExecutionContext,
    ) -> FactionRuleExecutionResult:
        calls.append(f"named:{record.execution_id}")
        return FactionRuleExecutionResult.applied(record=record, context=context)

    def generic_executor(
        record: Phase17FExecutionRecord,
        context: FactionRuleExecutionContext,
    ) -> FactionRuleExecutionResult:
        calls.append(f"generic:{record.execution_id}")
        return FactionRuleExecutionResult.applied(record=record, context=context)

    registry = FactionRuleExecutionRegistry.from_records(
        (named_record, generic_record),
        named_handlers={handler_id: named_handler},
        generic_ir_executor=generic_executor,
    )

    named_result = registry.execute(execution_id=named_record.execution_id, context=_context())
    generic_result = registry.execute(execution_id=generic_record.execution_id, context=_context())

    assert calls == [
        f"named:{named_record.execution_id}",
        f"generic:{generic_record.execution_id}",
    ]
    assert named_result.status is FactionRuleExecutionStatus.APPLIED
    assert generic_result.status is FactionRuleExecutionStatus.APPLIED
    assert FactionRuleExecutionResult.from_payload(named_result.to_payload()) == named_result
    assert FactionRuleExecutionResult.from_payload(generic_result.to_payload()) == generic_result


@pytest.mark.parametrize(
    "field_name",
    [
        "execution_id",
        "coverage_descriptor_id",
        "coverage_kind",
        "faction_id",
        "faction_name",
        "detachment_id",
        "detachment_name",
        "handler_id",
        "source_ids",
    ],
)
def test_phase17f_registry_rejects_mismatched_executor_result(field_name: str) -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    executable_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
        block_reason=None,
    )
    baseline_result = FactionRuleExecutionResult.applied(
        record=executable_record,
        context=_context(),
    )
    mismatched_result = _mismatched_result_for_field(baseline_result, field_name)
    handler_id = _require_handler_id(executable_record)

    def mismatched_handler(
        record: Phase17FExecutionRecord,
        context: FactionRuleExecutionContext,
    ) -> FactionRuleExecutionResult:
        return mismatched_result

    registry = FactionRuleExecutionRegistry.from_records(
        (executable_record,),
        named_handlers={handler_id: mismatched_handler},
    )

    with pytest.raises(GameLifecycleError, match=f"mismatched {field_name}"):
        registry.execute(execution_id=executable_record.execution_id, context=_context())


def test_phase17f_context_payload_round_trips() -> None:
    context = _context()

    assert FactionRuleExecutionContext.from_payload(context.to_payload()) == context


def test_phase17f_execution_result_rejects_inconsistent_status_reason_shapes() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    executable_record = replace(
        blocked_record,
        execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
        block_reason=None,
    )
    result = FactionRuleExecutionResult.applied(record=executable_record, context=_context())

    with pytest.raises(GameLifecycleError, match="cannot include reason"):
        replace(result, reason="unexpected")

    with pytest.raises(GameLifecycleError, match="requires reason"):
        replace(result, status=FactionRuleExecutionStatus.UNSUPPORTED)


def test_phase17f_execution_records_reject_inconsistent_block_shapes() -> None:
    blocked_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    source_gap_record = _first_execution_record(
        Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP
    )

    with pytest.raises(Phase17FFactionExecutionError, match="require block_reason"):
        replace(blocked_record, block_reason=None)

    with pytest.raises(Phase17FFactionExecutionError, match="Only blocked"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
            block_reason=Phase17FExecutionBlockReason.STRUCTURED_RULE_SEMANTICS_REQUIRED,
        )

    with pytest.raises(Phase17FFactionExecutionError, match="require handler_id"):
        replace(blocked_record, handler_id=None)

    with pytest.raises(Phase17FFactionExecutionError, match="require rule_ir_hash"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
            block_reason=None,
            rule_ir_hash=None,
        )

    with pytest.raises(Phase17FFactionExecutionError, match="require handler_id"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER,
            block_reason=None,
            handler_id=None,
        )

    with pytest.raises(Phase17FFactionExecutionError, match="require phase17e"):
        replace(source_gap_record, phase17e_unsupported_reason=None)

    with pytest.raises(Phase17FFactionExecutionError, match="SHA-256 digest"):
        replace(
            blocked_record,
            execution_status=Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR,
            block_reason=None,
            rule_ir_hash="bad",
        )


def test_phase17f_execution_package_rejects_invalid_record_sets() -> None:
    record = faction_execution_source.phase17f_execution_package().execution_records[0]

    with pytest.raises(Phase17FFactionExecutionError, match="must be a tuple"):
        Phase17FExecutionPackage(
            execution_records=cast(tuple[Phase17FExecutionRecord, ...], [record])
        )

    with pytest.raises(Phase17FFactionExecutionError, match="must contain"):
        Phase17FExecutionPackage(execution_records=(cast(Phase17FExecutionRecord, object()),))

    with pytest.raises(Phase17FFactionExecutionError, match="must be unique"):
        Phase17FExecutionPackage(execution_records=(record, record))

    with pytest.raises(Phase17FFactionExecutionError, match="unknown Phase17E"):
        Phase17FExecutionPackage(
            execution_records=(replace(record, coverage_descriptor_id="phase17e:missing"),)
        )

    with pytest.raises(Phase17FFactionExecutionError, match="cover every Phase17E"):
        Phase17FExecutionPackage(execution_records=())


def _context() -> FactionRuleExecutionContext:
    return FactionRuleExecutionContext(
        game_id="game-phase17f",
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.COMMAND,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:unit-1",
        target_unit_instance_ids=("army-beta:unit-1",),
        trigger_payload={"event": "phase17f-smoke"},
    )


def _first_execution_record(status: Phase17FExecutionStatus) -> Phase17FExecutionRecord:
    for record in faction_execution_source.phase17f_execution_package().execution_records:
        if record.execution_status is status:
            return record
    raise AssertionError(f"Missing Phase17F execution status: {status.value}.")


def _require_handler_id(record: Phase17FExecutionRecord) -> str:
    if record.handler_id is None:
        raise AssertionError("Expected Phase17F execution record to include handler_id.")
    return record.handler_id


def _mismatched_result_for_field(
    result: FactionRuleExecutionResult,
    field_name: str,
) -> FactionRuleExecutionResult:
    if field_name == "execution_id":
        return replace(result, execution_id="phase17f:wrong-execution")
    if field_name == "coverage_descriptor_id":
        return replace(result, coverage_descriptor_id="phase17e:wrong-descriptor")
    if field_name == "coverage_kind":
        return replace(result, coverage_kind="wrong-coverage-kind")
    if field_name == "faction_id":
        return replace(result, faction_id="wrong-faction")
    if field_name == "faction_name":
        return replace(result, faction_name="Wrong Faction")
    if field_name == "detachment_id":
        return replace(result, detachment_id="wrong-detachment")
    if field_name == "detachment_name":
        return replace(result, detachment_name="Wrong Detachment")
    if field_name == "handler_id":
        return replace(result, handler_id="wrong-handler")
    if field_name == "source_ids":
        return replace(result, source_ids=("wrong-source",))
    raise AssertionError(f"Unsupported mismatch field: {field_name}.")


def _payload_checksum(payload: Phase17FExecutionPackagePayload) -> str:
    payload_without_checksum: dict[str, object] = dict(payload)
    payload_without_checksum["source_payload_checksum_sha256"] = ""
    encoded = json.dumps(payload_without_checksum, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
