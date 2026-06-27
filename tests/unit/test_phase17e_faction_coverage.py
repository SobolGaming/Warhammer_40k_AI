from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlparse

import pytest
from tools.fetch_official_sources import load_official_source_manifest

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_subrules_2026_27 as faction_subrule_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
    Phase17ECoverageRow,
    Phase17ECoverageStatus,
    Phase17EFactionCoverageError,
    Phase17EUnsupportedReason,
)

ROOT = Path(__file__).resolve().parents[2]
FACTION_PACK_MANIFEST = ROOT / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
RAW_FACTION_PDF_DIR = ROOT / "data" / "raw" / "faction_packs"
BRIDGE_JSON_DIR = (
    ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS = frozenset(
    (
        "enhancement:aeldari:corsair-coterie:infamy",
        "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:assassins-eye-upgrade",
        "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:camouflaged-snipers-upgrade",
        "enhancement:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:apocalyptic-steeds-upgrade",
        "enhancement:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:soul-shattering-charge-upgrade",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:casting-back-the-veil",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:eldritch-suppression",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:nomads-of-the-hidden-way",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:from-beyond-the-veil",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:inescapable-manifestations",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:warp-riders",
    )
)
FADE_TO_DARKNESS_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980004"
FADE_TO_DARKNESS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:fade_to_darkness:turn-end-reserves",
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:fade_to_darkness:unit-destroyed",
)
LEAPING_SHADOWS_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980002"
LEAPING_SHADOWS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:leaping_shadows:scouts_9",
)
MANTLE_OF_GLOOM_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980003"
MANTLE_OF_GLOOM_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:mantle_of_gloom:objective-control",
)
MALICE_MADE_MANIFEST_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980005"
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
CHAOS_DAEMONS_DETACHMENT_RULE_RUNTIME_CONSUMERS_BY_KEY = {
    ("chaos-daemons", "blood-legion"): BLOOD_LEGION_RUNTIME_CONSUMERS,
    ("chaos-daemons", "cavalcade-of-chaos"): CAVALCADE_OF_CHAOS_RUNTIME_CONSUMERS,
    ("chaos-daemons", "daemonic-incursion"): DAEMONIC_INCURSION_RUNTIME_CONSUMERS,
    ("chaos-daemons", "shadow-legion"): SHADOW_LEGION_RUNTIME_CONSUMERS,
}
AELDARI_BATTLE_FOCUS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:aeldari:army_rule:fade_back",
    "warhammer_40000_11th:aeldari:army_rule:flitting_shadows",
    "warhammer_40000_11th:aeldari:army_rule:opportunity_seized",
    "warhammer_40000_11th:aeldari:army_rule:star_engines",
    "warhammer_40000_11th:aeldari:army_rule:sudden_strike",
    "warhammer_40000_11th:aeldari:army_rule:swift_as_the_wind",
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
CHAOS_DAEMONS_SHADOW_OF_CHAOS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos",
)
CHAOS_KNIGHTS_HARBINGERS_OF_DREAD_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:battle-shock",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:darkness:hit-roll",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:doom:wound-roll",
    "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread:leadership",
)
CHAOS_SPACE_MARINES_DARK_PACTS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:attack_sequence_completed",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:fight:lethal_hits",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:fight:sustained_hits_1",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:mortal_wound_feel_no_pain",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:shooting:lethal_hits",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:shooting:sustained_hits_1",
    "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:weapon_profile_modifier",
)
DEATH_GUARD_NURGLES_GIFT_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:armour-save-option",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:leadership",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:melee-hit-roll",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:movement-budget",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:objective-control",
    "warhammer_40000_11th:death_guard:army_rule:nurgles_gift:toughness",
)
DRUKHARI_POWER_FROM_PAIN_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:battle-shock-failed",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:command-phase-start",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:enemy-unit-destroyed",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:hatred-eternal-fight",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:hatred-eternal-shooting",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:lithe-agility-advance",
    "warhammer_40000_11th:drukhari:army_rule:power_from_pain:lithe-agility-charge",
)
EMPERORS_CHILDREN_THRILL_SEEKERS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:advance-eligibility",
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:charge-target-restriction",
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:fall-back-eligibility",
    "warhammer_40000_11th:emperors_children:army_rule:thrill_seekers:shooting-target-restriction",
)
GREY_KNIGHTS_GATE_OF_INFINITY_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:grey_knights:army_rule:gate_of_infinity",
)
LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:command-phase-start",
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:hit-roll",
    "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:wound-roll",
)
NECRONS_REANIMATION_PROTOCOLS_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:necrons:army_rule:reanimation_protocols",
)
ORKS_WAAAGH_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:orks:army_rule:waaagh",
    "warhammer_40000_11th:orks:army_rule:waaagh:advance-eligibility",
    "warhammer_40000_11th:orks:army_rule:waaagh:invulnerable-save",
    "warhammer_40000_11th:orks:army_rule:waaagh:weapon-profile",
)
TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good",
    "warhammer_40000_11th:tau_empire:army_rule:for_the_greater_good:weapon-profile",
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
SPACE_MARINES_OATH_OF_MOMENT_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:space_marines:army_rule:oath_of_moment",
    "warhammer_40000_11th:space_marines:army_rule:oath_of_moment:wound-roll",
)
WORLD_EATERS_BLESSINGS_OF_KHORNE_RUNTIME_CONSUMERS = (
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:rage_fuelled_invigoration",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:total_carnage",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:"
    "unbridled_bloodlust:charge_roll",
    "warhammer_40000_11th:world_eaters:army_rule:blessings_of_khorne:weapon-profile-keywords",
)
FACTION_ARMY_RULE_NAMES_BY_FACTION_ID = {
    "aeldari": "Battle Focus",
    "astra-militarum": "Voice of Command",
    "black-templars": "Templar Vows",
    "chaos-daemons": "The Shadow of Chaos",
    "chaos-knights": "Harbingers of Dread",
    "chaos-space-marines": "Dark Pacts",
    "death-guard": "Nurgle's Gift",
    "drukhari": "Power from Pain",
    "emperors-children": "Thrill Seekers",
    "grey-knights": "Gate of Infinity",
    "leagues-of-votann": "Prioritised Efficiency",
    "necrons": "Reanimation Protocols",
    "orks": "Waaagh!",
    "space-marines": "Oath of Moment",
    "tau-empire": "For the Greater Good",
    "world-eaters": "Blessings of Khorne",
}
FACTION_ARMY_RULE_RUNTIME_CONSUMERS_BY_FACTION_ID = {
    "aeldari": AELDARI_BATTLE_FOCUS_RUNTIME_CONSUMERS,
    "astra-militarum": ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS,
    "black-templars": BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMERS,
    "chaos-daemons": CHAOS_DAEMONS_SHADOW_OF_CHAOS_RUNTIME_CONSUMERS,
    "chaos-knights": CHAOS_KNIGHTS_HARBINGERS_OF_DREAD_RUNTIME_CONSUMERS,
    "chaos-space-marines": CHAOS_SPACE_MARINES_DARK_PACTS_RUNTIME_CONSUMERS,
    "death-guard": DEATH_GUARD_NURGLES_GIFT_RUNTIME_CONSUMERS,
    "drukhari": DRUKHARI_POWER_FROM_PAIN_RUNTIME_CONSUMERS,
    "emperors-children": EMPERORS_CHILDREN_THRILL_SEEKERS_RUNTIME_CONSUMERS,
    "grey-knights": GREY_KNIGHTS_GATE_OF_INFINITY_RUNTIME_CONSUMERS,
    "leagues-of-votann": LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS,
    "necrons": NECRONS_REANIMATION_PROTOCOLS_RUNTIME_CONSUMERS,
    "orks": ORKS_WAAAGH_RUNTIME_CONSUMERS,
    "space-marines": SPACE_MARINES_OATH_OF_MOMENT_RUNTIME_CONSUMERS,
    "tau-empire": TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS,
    "world-eaters": WORLD_EATERS_BLESSINGS_OF_KHORNE_RUNTIME_CONSUMERS,
}


def test_phase17e_payload_is_deterministic_json_safe_and_round_trips() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    payload = package.to_payload()

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert (
        payload["source_payload_checksum_sha256"]
        == (
            faction_coverage_source.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        )
    )
    assert faction_coverage_source.Phase17ECoveragePackage.from_payload(payload) == package

    stale_payload = payload.copy()
    stale_payload["source_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(Phase17EFactionCoverageError, match="checksum is stale"):
        faction_coverage_source.Phase17ECoveragePackage.from_payload(stale_payload)


def test_phase17e_exact_subrule_source_payloads_are_deterministic_and_validated() -> None:
    enhancement = next(
        row for row in faction_subrule_source.enhancement_rows() if row.runtime_consumer_ids
    )
    stratagem = next(
        row for row in faction_subrule_source.stratagem_rows() if row.runtime_consumer_ids
    )
    enhancement_payload = enhancement.to_payload()
    stratagem_payload = stratagem.to_payload()
    payload = {
        "identity": faction_subrule_source.source_package_identity_payload(),
        "enhancement": enhancement_payload,
        "stratagem": stratagem_payload,
    }

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert enhancement.source_id in enhancement_payload["source_ids"]
    assert stratagem.source_id in stratagem_payload["source_ids"]
    assert faction_subrule_source.SourceEnhancementRow.from_payload(enhancement_payload) == (
        enhancement
    )
    assert faction_subrule_source.SourceStratagemRow.from_payload(stratagem_payload) == stratagem

    with pytest.raises(ValueError, match="points"):
        replace(enhancement, points=-1)

    with pytest.raises(ValueError, match="must not be empty"):
        replace(enhancement, source_ids=())

    with pytest.raises(ValueError, match="command_point_cost"):
        replace(stratagem, command_point_cost=-1)

    with pytest.raises(ValueError, match="must be unique"):
        replace(stratagem, runtime_consumer_ids=("duplicate", "duplicate"))


def test_phase17e_exact_subrule_source_audit_accounts_for_every_bridge_input_row() -> None:
    skipped_rows = faction_subrule_source.skipped_bridge_rows()
    runtime_only_rows = faction_subrule_source.runtime_only_rows()
    identity = faction_subrule_source.source_package_identity_payload()
    emitted_bridge_source_ids = {
        source_id
        for row in faction_subrule_source.enhancement_rows()
        for source_id in row.source_ids
        if ":bridge-source-row:" in source_id
    }
    emitted_bridge_source_ids.update(
        source_id
        for row in faction_subrule_source.stratagem_rows()
        for source_id in row.source_ids
        if ":bridge-source-row:" in source_id
    )
    skipped_bridge_source_ids = {
        _bridge_source_id(row.table, row.bridge_source_row_id) for row in skipped_rows
    }
    bridge_input_source_ids = {
        _bridge_source_id(table, source_row_id)
        for table in ("Enhancements", "Stratagems")
        for source_row_id in _bridge_source_row_ids(table)
    }

    assert identity["skipped_bridge_row_count"] == str(len(skipped_rows))
    assert identity["runtime_only_row_count"] == str(len(runtime_only_rows))
    assert len(skipped_rows) == 601
    assert Counter(row.skip_reason for row in skipped_rows) == Counter(
        {
            "owner_not_in_current_source_package": 573,
            "missing_owner_fields": 28,
        }
    )
    assert emitted_bridge_source_ids.isdisjoint(skipped_bridge_source_ids)
    assert emitted_bridge_source_ids.union(skipped_bridge_source_ids) == bridge_input_source_ids
    assert all(
        row.skip_reason in faction_subrule_source.APPROVED_SKIPPED_BRIDGE_REASONS
        for row in skipped_rows
    )
    assert all(
        (row.derived_faction_id, row.derived_detachment_id)
        not in {
            (detachment.faction_id, detachment.detachment_id)
            for detachment in faction_detachment_source.detachment_rows()
        }
        for row in skipped_rows
        if row.skip_reason == "owner_not_in_current_source_package"
    )
    assert all(
        faction_subrule_source.SourceSkippedBridgeRow.from_payload(row.to_payload()) == row
        for row in skipped_rows[:3]
    )
    assert {row.source_row_id for row in runtime_only_rows} == APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS
    assert all(
        row.provenance_reason in faction_subrule_source.APPROVED_RUNTIME_ONLY_PROVENANCE_REASONS
        for row in runtime_only_rows
    )
    assert all(
        faction_subrule_source.SourceRuntimeOnlyRow.from_payload(row.to_payload()) == row
        for row in runtime_only_rows
    )


def test_phase17e_manifest_records_match_official_source_manifest() -> None:
    manifest_entries = load_official_source_manifest(FACTION_PACK_MANIFEST)
    entries_by_package_id = {entry.package_id: entry for entry in manifest_entries}
    records_by_package_id = {
        record.package_id: record for record in faction_coverage_source.faction_pdf_records()
    }

    assert len(manifest_entries) == len(faction_detachment_source.faction_rows())
    assert set(records_by_package_id) == set(entries_by_package_id)
    for package_id, record in records_by_package_id.items():
        entry = entries_by_package_id[package_id]
        assert record.title == entry.title
        assert record.source_date == entry.source_date
        assert record.sha256 == entry.sha256
        assert record.bytes == entry.expected_bytes
        assert record.pdf_filename == PurePosixPath(urlparse(entry.source_url).path).name
        assert entry.local_cache_path is not None
        assert record.pdf_filename == PurePosixPath(entry.local_cache_path).name


def test_phase17e_loads_every_seeded_faction_and_detachment() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    faction_rows = faction_detachment_source.faction_rows()
    detachment_rows = faction_detachment_source.detachment_rows()
    rows_by_kind = _rows_by_kind(package.coverage_rows)
    pdf_by_faction_id = {record.faction_id: record for record in package.pdf_records}

    assert set(pdf_by_faction_id) == {row.faction_id for row in faction_rows}
    assert len(rows_by_kind[Phase17ECoverageKind.FACTION_ARMY_RULE]) == len(faction_rows)
    assert len(rows_by_kind[Phase17ECoverageKind.DATASHEET_INTAKE]) == len(faction_rows)
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_RULE]) == len(detachment_rows)
    assert rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT_DESCRIPTORS] == []
    assert rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM_DESCRIPTORS] == []
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT]) == len(
        faction_subrule_source.enhancement_rows()
    )
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM]) == len(
        faction_subrule_source.stratagem_rows()
    )

    army_rule_rows = {
        row.faction_id: row for row in rows_by_kind[Phase17ECoverageKind.FACTION_ARMY_RULE]
    }
    datasheet_rows = {
        row.faction_id: row for row in rows_by_kind[Phase17ECoverageKind.DATASHEET_INTAKE]
    }
    detachment_rule_rows = _detachment_row_map(rows_by_kind[Phase17ECoverageKind.DETACHMENT_RULE])

    for faction_row in faction_rows:
        pdf_record = pdf_by_faction_id[faction_row.faction_id]
        army_row = army_rule_rows[faction_row.faction_id]
        datasheet_row = datasheet_rows[faction_row.faction_id]

        assert faction_row.source_id in army_row.source_ids
        assert pdf_record.source_id in army_row.source_ids
        if faction_row.faction_id in FACTION_ARMY_RULE_RUNTIME_CONSUMERS_BY_FACTION_ID:
            army_rule_runtime_consumers: tuple[str, ...] = (
                FACTION_ARMY_RULE_RUNTIME_CONSUMERS_BY_FACTION_ID[faction_row.faction_id]
            )
            assert army_row.status is Phase17ECoverageStatus.IMPLEMENTED
            assert army_row.runtime_support_status is not None
            assert army_row.runtime_support_status.value == "engine_consumed"
            assert army_row.runtime_consumer_ids == tuple(sorted(army_rule_runtime_consumers))
            assert army_row.handler_id == army_rule_runtime_consumers[0]
        else:
            assert army_row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
            assert army_row.runtime_support_status is None
            assert army_row.runtime_consumer_ids == ()
            assert army_row.handler_id == f"phase17e:faction:{faction_row.faction_id}:army-rule"
        assert faction_row.source_id in datasheet_row.source_ids
        assert pdf_record.source_id in datasheet_row.source_ids
        assert datasheet_row.unsupported_reason is (
            Phase17EUnsupportedReason.DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS
        )

    for detachment_row in detachment_rows:
        key = (detachment_row.faction_id, detachment_row.detachment_id)
        pdf_record = pdf_by_faction_id[detachment_row.faction_id]
        coverage_row = detachment_rule_rows[key]
        assert detachment_row.source_id in coverage_row.source_ids
        assert pdf_record.source_id in coverage_row.source_ids
        assert coverage_row.detachment_name == detachment_row.name
        assert coverage_row.force_disposition_id == detachment_row.force_disposition_id
        assert coverage_row.detachment_point_cost == detachment_row.detachment_point_cost
        assert coverage_row.is_new_for_eleventh is detachment_row.is_new_for_eleventh
        if key in CHAOS_DAEMONS_DETACHMENT_RULE_RUNTIME_CONSUMERS_BY_KEY:
            detachment_runtime_consumers: tuple[str, ...] = (
                CHAOS_DAEMONS_DETACHMENT_RULE_RUNTIME_CONSUMERS_BY_KEY[key]
            )
            assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
            assert coverage_row.runtime_support_status is not None
            assert coverage_row.runtime_support_status.value == "engine_consumed"
            assert coverage_row.runtime_consumer_ids == tuple(sorted(detachment_runtime_consumers))
            assert coverage_row.handler_id == detachment_runtime_consumers[0]
        else:
            assert coverage_row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
            assert coverage_row.runtime_support_status is None
            assert coverage_row.runtime_consumer_ids == ()
            assert coverage_row.handler_id == (
                f"phase17e:detachment:{detachment_row.detachment_id}:rule"
            )


def test_phase17e_exact_enhancement_and_stratagem_rows_cover_source_catalog() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    rows_by_kind = _rows_by_kind(package.coverage_rows)
    pdf_by_faction_id = {record.faction_id: record for record in package.pdf_records}
    detachment_rows_by_owner_id = {
        (row.faction_id, row.detachment_id): row
        for row in faction_detachment_source.detachment_rows()
    }

    enhancement_rows = {
        (row.faction_id, row.detachment_id, row.rule_id): row
        for row in rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT]
    }
    stratagem_rows = {
        (row.faction_id, row.detachment_id, row.rule_id): row
        for row in rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM]
    }

    assert set(enhancement_rows) == {
        (row.faction_id, row.detachment_id, row.enhancement_id)
        for row in faction_subrule_source.enhancement_rows()
    }
    assert set(stratagem_rows) == {
        (row.faction_id, row.detachment_id, row.stratagem_id)
        for row in faction_subrule_source.stratagem_rows()
    }

    for enhancement_source_row in faction_subrule_source.enhancement_rows():
        coverage_row = enhancement_rows[
            (
                enhancement_source_row.faction_id,
                enhancement_source_row.detachment_id,
                enhancement_source_row.enhancement_id,
            )
        ]
        detachment_row = detachment_rows_by_owner_id[
            (enhancement_source_row.faction_id, enhancement_source_row.detachment_id)
        ]
        _assert_exact_subrule_coverage_matches_source(
            coverage_row=coverage_row,
            source_ids=enhancement_source_row.all_source_ids,
            rule_id=enhancement_source_row.enhancement_id,
            rule_name=enhancement_source_row.name,
            timing_descriptor=enhancement_source_row.timing_descriptor,
            rule_category=enhancement_source_row.category,
            runtime_support_status=enhancement_source_row.runtime_support_status.value,
            runtime_consumer_ids=enhancement_source_row.runtime_consumer_ids,
            detachment_source_id=detachment_row.source_id,
            pdf_source_id=pdf_by_faction_id[enhancement_source_row.faction_id].source_id,
        )

    for stratagem_source_row in faction_subrule_source.stratagem_rows():
        coverage_row = stratagem_rows[
            (
                stratagem_source_row.faction_id,
                stratagem_source_row.detachment_id,
                stratagem_source_row.stratagem_id,
            )
        ]
        detachment_row = detachment_rows_by_owner_id[
            (stratagem_source_row.faction_id, stratagem_source_row.detachment_id)
        ]
        _assert_exact_subrule_coverage_matches_source(
            coverage_row=coverage_row,
            source_ids=stratagem_source_row.all_source_ids,
            rule_id=stratagem_source_row.stratagem_id,
            rule_name=stratagem_source_row.name,
            timing_descriptor=stratagem_source_row.timing_descriptor,
            rule_category=stratagem_source_row.category,
            runtime_support_status=stratagem_source_row.runtime_support_status.value,
            runtime_consumer_ids=stratagem_source_row.runtime_consumer_ids,
            detachment_source_id=detachment_row.source_id,
            pdf_source_id=pdf_by_faction_id[stratagem_source_row.faction_id].source_id,
        )


def test_phase17e_fade_to_darkness_exact_row_is_engine_consumed() -> None:
    source_row = next(
        row
        for row in faction_subrule_source.enhancement_rows()
        if row.source_row_id == FADE_TO_DARKNESS_SOURCE_ROW_ID
    )
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and row.faction_id == "chaos-daemons"
        and row.detachment_id == "shadow-legion"
        and row.rule_id == "000009980004"
    )

    assert source_row.name == "Fade to Darkness"
    assert source_row.runtime_support_status.value == "engine_consumed"
    assert source_row.runtime_consumer_ids == FADE_TO_DARKNESS_RUNTIME_CONSUMERS
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == FADE_TO_DARKNESS_RUNTIME_CONSUMERS
    assert coverage_row.handler_id == FADE_TO_DARKNESS_RUNTIME_CONSUMERS[0]


def test_phase17e_leaping_shadows_exact_row_is_engine_consumed() -> None:
    source_row = next(
        row
        for row in faction_subrule_source.enhancement_rows()
        if row.source_row_id == LEAPING_SHADOWS_SOURCE_ROW_ID
    )
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and row.faction_id == "chaos-daemons"
        and row.detachment_id == "shadow-legion"
        and row.rule_id == "000009980002"
    )

    assert source_row.name == "Leaping Shadows"
    assert source_row.runtime_support_status.value == "engine_consumed"
    assert source_row.runtime_consumer_ids == LEAPING_SHADOWS_RUNTIME_CONSUMERS
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == LEAPING_SHADOWS_RUNTIME_CONSUMERS
    assert coverage_row.handler_id == LEAPING_SHADOWS_RUNTIME_CONSUMERS[0]


def test_phase17e_mantle_of_gloom_exact_row_is_engine_consumed() -> None:
    source_row = next(
        row
        for row in faction_subrule_source.enhancement_rows()
        if row.source_row_id == MANTLE_OF_GLOOM_SOURCE_ROW_ID
    )
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and row.faction_id == "chaos-daemons"
        and row.detachment_id == "shadow-legion"
        and row.rule_id == "000009980003"
    )

    assert source_row.name == "Mantle of Gloom (Aura)"
    assert source_row.runtime_support_status.value == "engine_consumed"
    assert source_row.runtime_consumer_ids == MANTLE_OF_GLOOM_RUNTIME_CONSUMERS
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == MANTLE_OF_GLOOM_RUNTIME_CONSUMERS
    assert coverage_row.handler_id == MANTLE_OF_GLOOM_RUNTIME_CONSUMERS[0]


def test_phase17e_malice_made_manifest_exact_row_is_engine_consumed() -> None:
    source_row = next(
        row
        for row in faction_subrule_source.enhancement_rows()
        if row.source_row_id == MALICE_MADE_MANIFEST_SOURCE_ROW_ID
    )
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and row.faction_id == "chaos-daemons"
        and row.detachment_id == "shadow-legion"
        and row.rule_id == "000009980005"
    )

    assert source_row.name == "Malice Made Manifest"
    assert source_row.runtime_support_status.value == "engine_consumed"
    assert source_row.runtime_consumer_ids == MALICE_MADE_MANIFEST_RUNTIME_CONSUMERS
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == MALICE_MADE_MANIFEST_RUNTIME_CONSUMERS
    assert coverage_row.handler_id == MALICE_MADE_MANIFEST_RUNTIME_CONSUMERS[0]


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
def test_phase17e_chaos_daemons_detachment_rule_is_engine_consumed(
    detachment_id: str,
    rule_name: str,
    runtime_consumers: tuple[str, ...],
) -> None:
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
        and row.faction_id == "chaos-daemons"
        and row.detachment_id == detachment_id
    )

    assert coverage_row.rule_name == rule_name
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(sorted(runtime_consumers))
    assert coverage_row.handler_id == runtime_consumers[0]


def test_phase17e_leagues_of_votann_army_rule_is_engine_consumed() -> None:
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.faction_id == "leagues-of-votann"
    )

    assert coverage_row.descriptor_id == "phase17e:leagues-of-votann:army-rule"
    assert coverage_row.rule_name == "Prioritised Efficiency"
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(
        sorted(LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS)
    )
    assert coverage_row.handler_id == LEAGUES_OF_VOTANN_PRIORITISED_EFFICIENCY_RUNTIME_CONSUMERS[0]


def test_phase17e_black_templars_army_rule_is_engine_consumed() -> None:
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.faction_id == "black-templars"
    )

    assert coverage_row.descriptor_id == "phase17e:black-templars:army-rule"
    assert coverage_row.rule_name == "Templar Vows"
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(
        sorted(BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMERS)
    )
    assert coverage_row.handler_id == BLACK_TEMPLARS_TEMPLAR_VOWS_RUNTIME_CONSUMERS[0]


def test_phase17e_astra_militarum_army_rule_is_engine_consumed() -> None:
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.faction_id == "astra-militarum"
    )

    assert coverage_row.descriptor_id == "phase17e:astra-militarum:army-rule"
    assert coverage_row.rule_name == "Voice of Command"
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(
        sorted(ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS)
    )
    assert coverage_row.handler_id == ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS[0]
    assert (
        faction_coverage_source.FACTION_ARMY_RULE_NAMES_BY_FACTION_ID["astra-militarum"]
        == "Voice of Command"
    )
    assert (
        faction_coverage_source.FACTION_ARMY_RULE_RUNTIME_CONSUMER_IDS_BY_FACTION_ID[
            "astra-militarum"
        ]
        == ASTRA_MILITARUM_VOICE_OF_COMMAND_RUNTIME_CONSUMERS
    )


def test_phase17e_tau_empire_army_rule_is_engine_consumed() -> None:
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.faction_id == "tau-empire"
    )

    assert coverage_row.descriptor_id == "phase17e:tau-empire:army-rule"
    assert coverage_row.rule_name == "For the Greater Good"
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(
        sorted(TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS)
    )
    assert coverage_row.handler_id == TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS[0]
    assert (
        faction_coverage_source.FACTION_ARMY_RULE_NAMES_BY_FACTION_ID["tau-empire"]
        == "For the Greater Good"
    )
    assert (
        faction_coverage_source.FACTION_ARMY_RULE_RUNTIME_CONSUMER_IDS_BY_FACTION_ID["tau-empire"]
        == TAU_EMPIRE_FOR_THE_GREATER_GOOD_RUNTIME_CONSUMERS
    )


@pytest.mark.parametrize(
    ("faction_id", "rule_name", "runtime_consumers"),
    tuple(
        (
            faction_id,
            FACTION_ARMY_RULE_NAMES_BY_FACTION_ID[faction_id],
            runtime_consumers,
        )
        for faction_id, runtime_consumers in (
            FACTION_ARMY_RULE_RUNTIME_CONSUMERS_BY_FACTION_ID.items()
        )
    ),
    ids=tuple(FACTION_ARMY_RULE_RUNTIME_CONSUMERS_BY_FACTION_ID),
)
def test_phase17e_source_backed_army_rule_is_engine_consumed(
    faction_id: str,
    rule_name: str,
    runtime_consumers: tuple[str, ...],
) -> None:
    coverage_row = next(
        row
        for row in faction_coverage_source.coverage_rows()
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.faction_id == faction_id
    )

    assert coverage_row.descriptor_id == f"phase17e:{faction_id}:army-rule"
    assert coverage_row.rule_name == rule_name
    assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == "engine_consumed"
    assert coverage_row.runtime_consumer_ids == tuple(sorted(runtime_consumers))
    assert coverage_row.handler_id == next(iter(sorted(runtime_consumers)))


def test_phase17e_coverage_report_groups_supported_and_approved_unsupported_rows() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    faction_count = len(faction_detachment_source.faction_rows())
    detachment_count = len(faction_detachment_source.detachment_rows())
    enhancement_rows = faction_subrule_source.enhancement_rows()
    stratagem_rows = faction_subrule_source.stratagem_rows()
    implemented_exact_count = sum(1 for row in enhancement_rows if row.runtime_consumer_ids) + sum(
        1 for row in stratagem_rows if row.runtime_consumer_ids
    )
    implemented_army_rule_count = len(FACTION_ARMY_RULE_RUNTIME_CONSUMERS_BY_FACTION_ID)
    implemented_detachment_rule_count = len(CHAOS_DAEMONS_DETACHMENT_RULE_RUNTIME_CONSUMERS_BY_KEY)
    source_only_exact_count = len(enhancement_rows) + len(stratagem_rows) - implemented_exact_count
    status_counts = package.status_counts()

    assert status_counts[Phase17ECoverageStatus.IMPLEMENTED.value] == (
        implemented_army_rule_count + implemented_exact_count + implemented_detachment_rule_count
    )
    assert status_counts[Phase17ECoverageStatus.GENERIC_SUPPORTED.value] == 0
    assert status_counts[Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED.value] == (
        (faction_count - implemented_army_rule_count)
        + (detachment_count - implemented_detachment_rule_count)
        + source_only_exact_count
    )
    assert status_counts[Phase17ECoverageStatus.UNSUPPORTED.value] == faction_count
    unsupported_count = status_counts[Phase17ECoverageStatus.UNSUPPORTED.value]
    assert len(package.unsupported_rows()) == unsupported_count
    assert package.unapproved_unsupported_rows() == ()
    assert all(row.is_approved_unsupported for row in package.unsupported_rows())


def test_phase17e_coverage_rows_reject_unapproved_or_incomplete_status_shapes() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    named_handler_row = next(
        row
        for row in package.coverage_rows
        if row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
    )
    implemented_army_rule_row = next(
        row
        for row in package.coverage_rows
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.status is Phase17ECoverageStatus.IMPLEMENTED
    )
    unsupported_row = package.unsupported_rows()[0]

    with pytest.raises(Phase17EFactionCoverageError, match="require handler_id"):
        replace(named_handler_row, handler_id=None)

    with pytest.raises(Phase17EFactionCoverageError, match="require rule_ir_hash"):
        replace(named_handler_row, status=Phase17ECoverageStatus.GENERIC_SUPPORTED)

    with pytest.raises(Phase17EFactionCoverageError, match="require handler_id"):
        replace(implemented_army_rule_row, handler_id=None)

    with pytest.raises(Phase17EFactionCoverageError, match="cannot include exact"):
        replace(implemented_army_rule_row, rule_id="unexpected-exact-rule-id")

    with pytest.raises(Phase17EFactionCoverageError, match="requires runtime consumers"):
        replace(implemented_army_rule_row, runtime_consumer_ids=())

    with pytest.raises(Phase17EFactionCoverageError, match="require runtime support"):
        replace(implemented_army_rule_row, runtime_support_status=None)

    with pytest.raises(Phase17EFactionCoverageError, match="Only unsupported"):
        replace(
            named_handler_row,
            unsupported_reason=(
                Phase17EUnsupportedReason.DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS
            ),
        )

    with pytest.raises(Phase17EFactionCoverageError, match="require a reason"):
        replace(unsupported_row, unsupported_reason=None)


def test_phase17e_coverage_rows_reject_malformed_runtime_shape_tokens() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    named_handler_row = next(
        row
        for row in package.coverage_rows
        if row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
    )
    implemented_army_rule_row = next(
        row
        for row in package.coverage_rows
        if row.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
        and row.status is Phase17ECoverageStatus.IMPLEMENTED
    )
    implemented_detachment_row = next(
        row
        for row in package.coverage_rows
        if row.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
        and row.status is Phase17ECoverageStatus.IMPLEMENTED
    )
    implemented_exact_row = next(
        row
        for row in package.coverage_rows
        if row.coverage_kind in _EXACT_SUBRULE_TEST_KINDS
        and row.status is Phase17ECoverageStatus.IMPLEMENTED
    )
    datasheet_row = next(
        row
        for row in package.coverage_rows
        if row.coverage_kind is Phase17ECoverageKind.DATASHEET_INTAKE
    )
    unsupported_row = package.unsupported_rows()[0]

    with pytest.raises(Phase17EFactionCoverageError, match="Unsupported Phase17E coverage kind"):
        replace(named_handler_row, coverage_kind=cast(Phase17ECoverageKind, "unknown-kind"))

    with pytest.raises(Phase17EFactionCoverageError, match="Unsupported Phase17E coverage status"):
        replace(named_handler_row, status=cast(Phase17ECoverageStatus, "unknown-status"))

    with pytest.raises(
        Phase17EFactionCoverageError,
        match="Unsupported Phase17E unsupported reason",
    ):
        replace(
            unsupported_row,
            unsupported_reason=cast(Phase17EUnsupportedReason, "unknown-reason"),
        )

    with pytest.raises(
        Phase17EFactionCoverageError,
        match="Unsupported Phase17E runtime support status",
    ):
        replace(
            implemented_army_rule_row,
            runtime_support_status=cast(
                faction_subrule_source.SourceSubruleRuntimeStatus,
                "unknown-runtime-status",
            ),
        )

    with pytest.raises(Phase17EFactionCoverageError, match="source_ids must be a tuple"):
        replace(named_handler_row, source_ids=cast(tuple[str, ...], ["source"]))

    with pytest.raises(Phase17EFactionCoverageError, match="source_ids must be unique"):
        replace(named_handler_row, source_ids=("duplicate-source", "duplicate-source"))

    with pytest.raises(Phase17EFactionCoverageError, match="Exact subrule coverage"):
        replace(implemented_exact_row, runtime_support_status=None)

    with pytest.raises(Phase17EFactionCoverageError, match="Detachment rule coverage"):
        replace(implemented_detachment_row, rule_id="unexpected-exact-rule-id")

    with pytest.raises(Phase17EFactionCoverageError, match="requires runtime consumers"):
        replace(implemented_detachment_row, runtime_consumer_ids=())

    with pytest.raises(Phase17EFactionCoverageError, match="require runtime support"):
        replace(implemented_detachment_row, runtime_support_status=None)

    with pytest.raises(Phase17EFactionCoverageError, match="Only exact subrule coverage"):
        replace(datasheet_row, rule_id="unexpected-rule-id")

    with pytest.raises(Phase17EFactionCoverageError, match="detachment_point_cost must be"):
        replace(implemented_detachment_row, detachment_point_cost=0)


def test_phase17e_local_raw_faction_pdfs_match_manifest_when_present() -> None:
    present_pdf_filenames: set[str]
    present_pdf_filenames = (
        {path.name for path in RAW_FACTION_PDF_DIR.glob("*.pdf")}
        if RAW_FACTION_PDF_DIR.exists()
        else set()
    )
    if not present_pdf_filenames:
        pytest.skip("No local raw faction PDFs are present.")
    records_by_filename = {
        record.pdf_filename: record for record in faction_coverage_source.faction_pdf_records()
    }
    unknown_pdf_filenames = present_pdf_filenames.difference(records_by_filename)
    assert not unknown_pdf_filenames

    for pdf_filename in sorted(present_pdf_filenames):
        record = records_by_filename[pdf_filename]
        pdf_path = RAW_FACTION_PDF_DIR / record.pdf_filename
        assert pdf_path.is_file()
        pdf_data = pdf_path.read_bytes()
        assert len(pdf_data) == record.bytes
        assert hashlib.sha256(pdf_data).hexdigest() == record.sha256


def _bridge_source_row_ids(table: str) -> set[str]:
    raw_payload = json.loads((BRIDGE_JSON_DIR / f"{table}.json").read_text(encoding="utf-8"))
    if type(raw_payload) is not dict:
        raise AssertionError("bridge source payload must be a JSON object")
    payload = cast(dict[str, object], raw_payload)
    raw_rows = payload["rows"]
    if type(raw_rows) is not list:
        raise AssertionError("bridge source payload rows must be a list")
    source_row_ids: set[str] = set()
    for raw_row in cast(list[object], raw_rows):
        if type(raw_row) is not dict:
            raise AssertionError("bridge source payload row must be a JSON object")
        row = cast(dict[str, object], raw_row)
        source_row_id = row["source_row_id"]
        if type(source_row_id) is not str:
            raise AssertionError("bridge source_row_id must be a string")
        source_row_ids.add(source_row_id)
    return source_row_ids


def _bridge_source_id(table: str, source_row_id: str) -> str:
    return (
        f"gw-11e-phase17e-exact-faction-subrules-2026-27:bridge-source-row:{table}:{source_row_id}"
    )


def _rows_by_kind(
    rows: tuple[Phase17ECoverageRow, ...],
) -> dict[Phase17ECoverageKind, list[Phase17ECoverageRow]]:
    rows_by_kind: dict[Phase17ECoverageKind, list[Phase17ECoverageRow]] = {
        kind: [] for kind in Phase17ECoverageKind
    }
    for row in rows:
        rows_by_kind[row.coverage_kind].append(row)
    return rows_by_kind


_EXACT_SUBRULE_TEST_KINDS = frozenset(
    (
        Phase17ECoverageKind.DETACHMENT_ENHANCEMENT,
        Phase17ECoverageKind.DETACHMENT_STRATAGEM,
    )
)


def _detachment_row_map(
    rows: list[Phase17ECoverageRow],
) -> dict[tuple[str, str], Phase17ECoverageRow]:
    mapped_rows: dict[tuple[str, str], Phase17ECoverageRow] = {}
    for row in rows:
        assert row.detachment_id is not None
        mapped_rows[(row.faction_id, row.detachment_id)] = row
    return mapped_rows


def _assert_exact_subrule_coverage_matches_source(
    *,
    coverage_row: Phase17ECoverageRow,
    source_ids: tuple[str, ...],
    rule_id: str,
    rule_name: str,
    timing_descriptor: str,
    rule_category: str,
    runtime_support_status: str,
    runtime_consumer_ids: tuple[str, ...],
    detachment_source_id: str,
    pdf_source_id: str,
) -> None:
    assert coverage_row.rule_id == rule_id
    assert coverage_row.rule_name == rule_name
    assert coverage_row.timing_descriptor == timing_descriptor
    assert coverage_row.rule_category == rule_category
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == runtime_support_status
    assert coverage_row.runtime_consumer_ids == runtime_consumer_ids
    assert all(source_id in coverage_row.source_ids for source_id in source_ids)
    assert detachment_source_id in coverage_row.source_ids
    assert pdf_source_id in coverage_row.source_ids
    if runtime_consumer_ids:
        assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
        assert coverage_row.handler_id == runtime_consumer_ids[0]
    else:
        assert coverage_row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
