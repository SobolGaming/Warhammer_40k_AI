# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.aeldari_39k_pro_audit import (
    AUDIT_PATH as AELDARI_AUDIT_PATH,
)
from tools.aeldari_39k_pro_audit import (
    aeldari_thirty_nine_k_pro_audit,
    load_aeldari_thirty_nine_k_pro_audit,
)
from tools.core_rules_40k_app_audit import (
    AUDIT_PATH as CORE_RULES_40K_APP_AUDIT_PATH,
)
from tools.core_rules_40k_app_audit import (
    REPORT_PATH as CORE_RULES_40K_APP_REPORT_PATH,
)
from tools.core_rules_40k_app_audit import (
    _evidence_hash,
    _source_observation_hash,
    core_rules_forty_k_app_audit,
    core_rules_forty_k_app_audit_markdown,
    load_core_rules_forty_k_app_audit,
)
from tools.core_rules_maintained_mirror_audit import (
    AUDIT_PATH as CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH,
)
from tools.core_rules_maintained_mirror_audit import (
    REPORT_PATH as CORE_RULES_MAINTAINED_MIRROR_REPORT_PATH,
)
from tools.core_rules_maintained_mirror_audit import (
    core_rules_maintained_mirror_audit,
    core_rules_maintained_mirror_markdown,
    load_core_rules_maintained_mirror_audit,
)
from tools.emperors_children_39k_pro_audit import (
    AUDIT_PATH,
    emperors_children_thirty_nine_k_pro_audit,
    load_emperors_children_thirty_nine_k_pro_audit,
)
from tools.faction_pack_datasheet_review import faction_pack_datasheet_review
from tools.generate_ability_support_matrix import (
    _ability_datasheet_pairs_text,
    _inline_code_list,
    _markdown_text,
    ability_support_matrix_rows,
    faction_support_markdown_files,
    runtime_content_semantic_coverage_payload,
    support_matrix_markdown,
)

from warhammer40k_core.engine.ability_coverage import (
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)


def test_global_support_renderer_preserves_section_order_and_runtime_inventory() -> None:
    ability_rows = ability_support_matrix_rows()
    category_rows = ability_coverage_category_rows(ability_rows)
    markdown = support_matrix_markdown(
        ability_coverage_category_rows_payload(category_rows),
        ability_rows=ability_coverage_rows_payload(ability_rows),
        runtime_semantic_coverage=runtime_content_semantic_coverage_payload(),
    )

    headings = (
        "## Runtime Content Semantic Coverage",
        "## Mustering / List Construction Support",
        "## Factions",
        "## Maulerfiend Cross-faction Support",
        "## Runtime Hook Inventory",
    )
    assert all(heading in markdown for heading in headings)
    assert tuple(markdown.index(heading) for heading in headings) == tuple(
        sorted(markdown.index(heading) for heading in headings)
    )

    represented_consumer_ids = {
        consumer_id for row in ability_rows for consumer_id in row.runtime_consumer_ids
    }
    assert represented_consumer_ids
    assert all(f"`{consumer_id}`" in markdown for consumer_id in represented_consumer_ids)


def test_faction_support_renderer_preserves_section_order() -> None:
    aeldari = faction_support_markdown_files()["aeldari.md"]
    emperors_children = faction_support_markdown_files()["emperors-children.md"]

    assert aeldari.startswith("# Aeldari Support Matrix\n")
    assert aeldari.index("## Detachment Rule Support") < aeldari.index(
        "## Datasheet component coverage"
    )
    assert (
        aeldari.index("## Semantic Support Snapshot")
        < aeldari.index("## Detachment Rule Support")
        < aeldari.index("## Datasheet Source Review")
        < aeldari.index("## Secondary-reference Audit")
        < aeldari.index("## Datasheet component coverage")
    )
    assert "Corsair Coterie — Relentless Raiders" in aeldari
    assert "Armoured Warhost — Skilled Crews" in aeldari
    assert "15 detachments, 52 Enhancements, and 78 Stratagems" in aeldari
    assert "| Detachment rules | 15 | 2 | 0 | 13 |" in aeldari
    assert "| Enhancements | 52 | 6 | 0 | 46 |" in aeldari
    assert "| Stratagems | 78 | 9 | 0 | 69 |" in aeldari
    assert "https://39k.pro/faction/-utUCEwvtbI" in aeldari
    assert aeldari.count("https://39k.pro/detachment/") == 15
    assert "Guileful Strategist" not in aeldari
    assert "Harmonisation Matrix" not in aeldari
    assert "## Faction Pack Review" in emperors_children
    assert "Elegant Brutes | Yes | Physical PDF page 2" in emperors_children
    assert "Frenzied Host | Yes | Physical PDF page 3" in emperors_children
    assert "Spectacle of Slaughter | Yes | Physical PDF page 4" in emperors_children
    assert "Court of the Phoenician | No - reprinted/updated" in emperors_children
    assert "Cacophonic Accompaniment<br>Frenzied Ferocity Upgrade" in emperors_children
    assert "Possessive Mania<br>Agonised Cacophony<br>Absolute Sensory Overload" in (
        emperors_children
    )
    assert "are not yet present in the structured Phase17E artifacts" in emperors_children
    assert "## Semantic Support Snapshot" in emperors_children
    assert (
        emperors_children.index("## Faction Pack Review")
        < emperors_children.index("## Semantic Support Snapshot")
        < emperors_children.index("## Detachment Rule Support")
        < emperors_children.index("## Datasheet Source Review")
        < emperors_children.index("## Secondary-reference Audit")
        < emperors_children.index("## Datasheet component coverage")
        < emperors_children.index("### Maulerfiend Cross-faction Support")
        < emperors_children.index("## Cross-source Semantic Equivalence")
    )
    assert "Court of the Phoenician | **Implemented**" in emperors_children
    assert "| Core | 31 | 31 assignments matched |" in emperors_children
    assert "| Faction | 23 | 23 assignments matched |" in emperors_children
    assert "| Datasheet | 35 | 34 assignments matched;" in emperors_children
    assert "`ec-flawless-blades-blissblade-attacks`" in emperors_children
    assert "`ec-tormentors-power-sword-strength`" in emperors_children
    assert "`ec-infractors-power-sword-strength`" in emperors_children
    assert emperors_children.count("| `ec-heldrake-profile` | Heldrake |") == 3
    assert "`ec-heldrake-remove-aircraft`" in emperors_children
    assert "`ec-chaos-land-raider-frame`" in emperors_children
    assert "`ec-chaos-rhino-frame`" in emperors_children
    assert "https://39k.pro/faction/uyQevAixq5I" in emperors_children
    assert emperors_children.count("https://39k.pro/datasheet/") == 23
    assert "emperors_children_2026_07_31.audit.json" in emperors_children
    assert "e114f25710a8fbc2089ca2bf02fe578cb5d7ed541f1671ee8c1a6405e124ac8a" in (emperors_children)
    assert "100 have observed provider relationships" in emperors_children
    assert "http://39k.pro" not in emperors_children
    assert "### Maulerfiend Cross-faction Support" in emperors_children
    assert "#### Reusable generic mechanics" in emperors_children
    assert "#### Exact faction variants" in emperors_children
    assert "### Unit Datasheet Source Treatments" not in emperors_children
    assert "### Datasheet Ability Details" not in emperors_children
    support_markdown = emperors_children.split("## Datasheet component coverage", 1)[1]
    assert "### Emperor's Children" in support_markdown
    assert "### Vehicles and Daemon Engines" in support_markdown
    assert "### Slaanesh Daemons" in support_markdown
    expected_header = (
        "| Datasheet | Source basis | IR coverage | Supported semantics | "
        "IR semantics still needed | Bridge / catalog blockers |"
    )
    assert support_markdown.count(expected_header) == 3
    review = faction_pack_datasheet_review("emperors-children")
    assert len(review.rows) == 23
    for row in review.rows:
        assert row.datasheet_id is not None
        assert support_markdown.count(f"| {row.datasheet_name} (`{row.datasheet_id}`) |") == 1
    assert (
        "No Prey Can Evade Advance and Charge re-rolls and Monarch of the Hunt deterministic"
        not in emperors_children
    )
    assert "Both datasheet abilities are engine-consumed" in emperors_children
    assert "Chaos Daemons — Shalaxi Helbane — Monarch of the Hunt" in emperors_children
    assert "Emperor's Children — Shalaxi Helbane — Monarch of the Hunt" in emperors_children
    assert "## Detachment Rule Coverage Rows" not in emperors_children


def test_emperors_children_39k_pro_audit_retains_assignment_level_evidence() -> None:
    audit = emperors_children_thirty_nine_k_pro_audit()

    assert len(audit.datasheets) == 23
    assert len(audit.assignments) == 101
    assert len({row.observed_provider_url for row in audit.datasheets}) == 23
    provider_datasheet_ids_by_source = {
        row.source_datasheet_id: row.observed_provider_url.rsplit("/", 1)[-1]
        for row in audit.datasheets
    }
    assert all(
        row.observed_provider_datasheet_id
        == provider_datasheet_ids_by_source[row.source_datasheet_id]
        for row in audit.assignments
    )
    assert all(
        row.source_datasheet_name.replace("\u2019", "'").casefold()
        == row.observed_provider_name.replace("\u2019", "'").casefold()
        for row in audit.datasheets
    )
    assert audit.ability_category_rows() == (
        ("Core", 31, "31 assignments matched"),
        ("Faction", 23, "23 assignments matched"),
        ("Datasheet", 35, "34 assignments matched; 1 retained provider relationship discrepancy"),
        ("Wargear", 7, "7 assignments matched"),
        ("Daemon Primarch choice", 3, "3 assignments matched"),
        ("Datasheet sidebar rule", 2, "2 assignments matched"),
    )
    assert tuple(
        (row.source_assignment_id, row.source_assignment_name, row.match_status)
        for row in audit.assignment_discrepancies
    ) == (("000004077:6", "Serpentine", "provider_definition_unassigned"),)
    qualified_assignments = {
        row.source_assignment_id: (
            row.source_assignment_name,
            row.source_qualifiers,
            row.observed_provider_qualifiers,
        )
        for row in audit.assignments
        if row.source_qualifiers
    }
    assert qualified_assignments == {
        "000004077:9": ("Enthralling Hypnosis (Aura)", ("Aura",), ("Aura",)),
        "000004085:3": ("Warped Interference (Psychic)", ("Psychic",), ("Psychic",)),
        "000004085:4": ("Wracking Agonies (Psychic)", ("Psychic",), ("Psychic",)),
        "000004086:4": ("Excessive Vigour (Aura)", ("Aura",), ("Aura",)),
        "000004097:4": ("Daemon Lord of Slaanesh (Aura)", ("Aura",), ("Aura",)),
    }
    assert len(audit.datasheet_deltas) == 12
    assert all(row.evidence_sha256 for row in audit.datasheet_deltas)
    assert all(
        row.observed_provider_datasheet_id in provider_datasheet_ids_by_source.values()
        for row in audit.datasheet_deltas
    )


def test_aeldari_39k_pro_audit_retains_current_exact_inventory() -> None:
    audit = aeldari_thirty_nine_k_pro_audit()

    assert len(audit.detachments) == 15
    assert audit.enhancement_count == 52
    assert audit.stratagem_count == 78
    assert audit.in_scope_datasheet_count == 70
    assert audit.exact_ability_count == audit.matched_exact_ability_count == 145
    assert len({row.provider_url for row in audit.detachments}) == 15
    assert {row.detachment_id for row in audit.detachments} >= {
        "fateful-performance",
        "serpents-brood",
        "twilight-flickers",
    }


def test_aeldari_39k_pro_audit_rejects_duplicate_detachment_urls(tmp_path: Path) -> None:
    payload = json.loads(AELDARI_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["detachments"][1]["provider_url"] = payload["detachments"][0]["provider_url"]
    tampered_path = tmp_path / "duplicate-url-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="detachment URLs must be unique"):
        load_aeldari_thirty_nine_k_pro_audit(tampered_path)


def test_aeldari_39k_pro_audit_rejects_official_source_hash_drift(tmp_path: Path) -> None:
    payload = json.loads(AELDARI_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["official_source"]["pdf_sha256"] = "0" * 64
    tampered_path = tmp_path / "stale-official-hash-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="official PDF hash is stale"):
        load_aeldari_thirty_nine_k_pro_audit(tampered_path)


def test_core_rules_40k_app_audit_retains_exact_review_only_category_inventory() -> None:
    audit = core_rules_forty_k_app_audit()

    assert audit.audit_id == "40k-app-core-rules-2026-08-25"
    assert audit.scope == "core_rules_only"
    assert audit.excluded_scopes == (
        "factions",
        "faction_detachments",
        "faction_datasheets",
    )
    assert audit.provider_authority == "project_authoritative_verbatim_official_app_mirror"
    assert audit.project_authority_policy_id == (
        "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
    )
    assert audit.provider_affiliation == "not_affiliated_with_or_endorsed_by_games_workshop"
    assert not audit.runtime_input
    assert not audit.network_capture_retained
    assert tuple(row.category_id for row in audit.categories) == tuple(
        f"{number:02d}" for number in range(1, 26)
    )
    assert audit.categories[0].category_title == "Core Concepts"
    assert audit.categories[0].source_observation_sha256 == (
        "3668da89d60d6234672f11be41cb08ddca6816354db062b47c4b4adf8ebf2ec5"
    )
    assert audit.categories[0].evidence_sha256 == (
        "7f8432dff4b13cead0c550a2feed6724f14cad9e29440fc0f3f85e5ece23d9cc"
    )
    assert audit.categories[-1].category_title == "Muster Armies"
    assert len({row.provider_url for row in audit.categories}) == 25
    assert {row.implementation_status for row in audit.categories} == {
        "assessed_no_standalone_remediation",
        "assessed_remediation_planned",
    }
    assert {row.category_id: row.remediation_pr_ids for row in audit.categories} == {
        "01": ("P01",),
        "02": ("P02A", "P02B", "P02C"),
        "03": ("P03A", "P03B"),
        "04": ("P04",),
        "05": ("P05A", "P05B", "P05C"),
        "06": ("P06A", "P06B"),
        "07": (),
        "08": ("P08A", "P08B"),
        "09": ("P09A", "P09B"),
        "10": ("P10",),
        "11": ("P11A",),
        "12": ("P12",),
        "13": (),
        "14": ("P14",),
        "15": ("P15A", "P15B", "P15C", "P15D", "P15E"),
        "16": (),
        "17": (),
        "18": ("P18A", "P18B", "P18C"),
        "19": ("P19",),
        "20": ("P20",),
        "21": ("P21A", "P21B"),
        "22": ("P22",),
        "23": ("P23",),
        "24": ("P24A", "P24B", "P24C1", "P24C2", "P24D", "P24E"),
        "25": ("P25A", "P25B", "P25C"),
    }
    assert all(
        (row.implementation_status == "assessed_remediation_planned")
        == bool(row.remediation_pr_ids)
        for row in audit.categories
    )
    assert {row.provider_comparison_status for row in audit.categories} == {
        "authoritative_app_internal_numbering_drift",
        "authoritative_app_mirror",
        "authoritative_app_mirror_controls_repository_conflict",
        "authoritative_app_mirror_supersedes_pdf",
        "repository_transcription_not_observed_on_authoritative_app_mirror",
    }
    assert {row.category_id: row.source_observation_sha256 for row in audit.categories} == {
        "01": "3668da89d60d6234672f11be41cb08ddca6816354db062b47c4b4adf8ebf2ec5",
        "02": "0e11ace01b5e417429dd752bc4ce3cf51ab1f2dc57a93f0dc5f7e628275161dc",
        "03": "27da884f8f88931a3cd10608eeb7cbc3c6fbc172c9eb45d91ea360dbca625114",
        "04": "2034aaa716e966c3af702eaffbf3bf019e69519cc61cf40633a5b8799e17287b",
        "05": "c771b8acbb62f912cc21c649a6a1ec0cac5d5a1f02e5454747b9427a8571892e",
        "06": "646b405724eb9f1a7f441fed3b3af0cae62925c72fb4b069fc17118fbab13b73",
        "07": "ba289accfe6207de38af2832239f5ca0bdfa9d8d74ed859998422237949b0c84",
        "08": "0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e",
        "09": "a00bccdc9dd090acd4fa211034bd397739392c4f018276667e3309f8d66960ae",
        "10": "ce3a68840e30726e81884dd440fc46e8404d7cdd922753d845f84da6d626e162",
        "11": "df487690f77cd0d3b9d0c5e0d0d6594e6cf2dfeec261c0b67d9aa321aa311d40",
        "12": "e993a6133af95dc2f1361b32dc95b7d9b7502eb4aabc226f9e5e6dff34b92a63",
        "13": "02ea53d2341fe361461cb3938fc5d268e3a6a9b9645ce95f4e4ebd8a8eba7748",
        "14": "ff60f2ecfd3c0e16b9815c05183d66dcbe940fd0fca006046a08f93ba67a80fc",
        "15": "90d660a2388e7f6799e71fe8c2305d019409614b70ee9fcb962609851ab15f59",
        "16": "eb27b3d331dfd5b465afd3ec11e714fb688d2859259a658766450093177eac12",
        "17": "8aa7827d8d29631814f3f10d421af5ef4701b5d521f0b479bc6e4156bdd5c985",
        "18": "d9a06d3c5b350f66bad9e4b89f62242fd0f0b4c54579ea3ad6bbf2c2674b8d0e",
        "19": "9328cc0ae8f0c22dc52418c3238a105d7031cdfdb5daf78bd377c56f36c795bd",
        "20": "e286a7f886f625a18def11dc4fcbd41fd6fee12aad88a575471fed0e77186729",
        "21": "4e086bf2452707ef7936fb2c86296910d45ae05fd6e84ad9b3ea0c1e1eddc1de",
        "22": "57ca2143f8d413941a9e802ab944c8d35ac833e05a1816749ac8f9020d50f822",
        "23": "94abac99e6b702878f77c71c8e9e7eef02afea129913c8b95c059e6a15f9f72a",
        "24": "5f68585a913965b35453a1d3e6d8278583c85e20a6dcf0721fef6f899080877a",
        "25": "11ec20d47a3a15ae3a01377c5591ed22e14cf3e39a8f04d25424166d5d0e4ac7",
    }
    assert {row.category_id: row.evidence_sha256 for row in audit.categories} == {
        "01": "7f8432dff4b13cead0c550a2feed6724f14cad9e29440fc0f3f85e5ece23d9cc",
        "02": "d5aa00c9f0d05df48b51553968bb8c40dffd51e2642eaca11046a3e4a6785048",
        "03": "fc73057f314aaa3a26636086adfd21af487cebb84698f33edea5175b59561781",
        "04": "413cd047db61cf5e2bc5b92d2a20e5cc5a97e6e19dde2daad9a7a5f1ba5ce211",
        "05": "108c222661a9f0fc56bd0193f7dcc21f029984e3cf572e5d671590af62c60db9",
        "06": "03b3af0e02e68c0428594c4776d8f7014fc5fd6eac2defed37067846d29c5d75",
        "07": "49ec76e1dc76fc81f8ea3b1cd9b8bb2adf177f5fee41245fa029bb5af5329f29",
        "08": "cd6e35d6f3f22047e79b34ae45a2496f3616b42fc300ea85498b89b949aa664b",
        "09": "bf71111dd7f17a228da5e4f896ea9cb4d8c3d82ec6dc896985c6ade0f46abe6d",
        "10": "e384f55d7ee3b911f9e010412337a4ef9fd271223404e7aff74e919560adc898",
        "11": "69b305cdf256c0c5a92faf24bab49d88b95ce4516b1e6d246303366c9e388532",
        "12": "924cfca132f1b4cc7035de29fb89ea59f63fc21e029ae7bed5dc0187c0653846",
        "13": "748343cb725c898bf5f97e319e878e651afae38704ba10973998d3be28b59560",
        "14": "800458535b4b13829aacb64c69c3c40c60e4dd7ee5a9d34dd23b1020adb9fd6c",
        "15": "76cad1a1fc532e66f48a17c753d4adccb4b0ab2fa88a382808613d9eb3b82c5b",
        "16": "ad9da141624095f642196c64000a09fbb95812a7b5841e6387059e84228d3d2a",
        "17": "ea3f69f9dad4f1d59d3dfd8e13697c4b4048b3a3d052fccb45eac46a827f0c3c",
        "18": "fa080ce3e9ab02baae56420d38312398ffd97de6b7212f7fb2905aeddb1c1123",
        "19": "1cb1ddc1ab20641be54f24f82f5cc781287ac78ed2ed5dca03122bb4c9217c96",
        "20": "8b1647e5d71be606b96a601385d6deab4c6b0ada85c03fe78dad0ae76ee050a9",
        "21": "d027064739bd220eb7c1689713b5a24bf8a962eb3ee1b5b312ca190811da3f62",
        "22": "eaa21cbfb0bddd4b95d73f1f9a3015150b074d6a821450d130ba1c05f52b5fc8",
        "23": "6627dc38b2221c139b56384959b6c85306e911d925a9c5b072aaf007a497a6f2",
        "24": "081e467fd5fbc31f195c04c3804f1099138a8ead2eb2bfe25ace6c71fb21e72b",
        "25": "78a8f90f9dda44e289384c359d59ab1b0d1d616e6c2be85af38eb6a5d12e16a1",
    }
    assert all(row.evidence_sha256 for row in audit.findings)
    terrain = next(row for row in audit.categories if row.category_id == "13")
    assert terrain.provider_comparison_status == "authoritative_app_mirror_supersedes_pdf"
    assert terrain.finding_ids == ("hidden-unverified-source-13-09",)
    hidden_finding = next(
        row for row in audit.findings if row.finding_id == "hidden-unverified-source-13-09"
    )
    assert hidden_finding.verification_status == "authoritative_app_mirror_controls"
    assert hidden_finding.source_observation_sha256 == (
        "62d982be96a81f69059f11def8a0ee75e6ae64f2dfd6f7132e4913140e9aaaf4"
    )
    assert hidden_finding.evidence_sha256 == (
        "d61d3b849afbf3748e316fa14149eb9661836bbc29f2534aa0e7cdf61487dbf6"
    )
    assert "historical owner transcription is uncaptured and unverified" in (
        hidden_finding.how_currently_recorded
    )
    assert "project-authoritative App mirror" in hidden_finding.how_it_should_be_treated
    assert "runtime path is executable" in hidden_finding.how_it_should_be_treated
    assert "Terrain 13.09" in hidden_finding.specific_source_basis
    assert audit.project_authority_policy_id in hidden_finding.specific_source_basis
    objective_finding = next(
        row for row in audit.findings if row.finding_id == "july-transcription-conflict-12-08"
    )
    assert objective_finding.source_observation_sha256 == (
        "726ce364500c7f1d6b9776651f430ac05ad144a5899877fdbd857128e6cf041c"
    )
    assert objective_finding.evidence_sha256 == (
        "134e4f740df11313bb9b372cb1df61a2af7dc89a1efba735707025dacb7bb5ff"
    )

    report = core_rules_forty_k_app_audit_markdown(audit)
    assert CORE_RULES_40K_APP_REPORT_PATH.read_text(encoding="utf-8") == report
    assert "40k.app is treated as a verbatim authoritative mirror" in report
    assert "non-affiliated hosting provider" in report
    assert audit.project_authority_policy_id in report
    assert "Implementation evaluation" in report
    assert "Planned PRs" in report
    assert "P24A, P24B, P24C1, P24C2, P24D, P24E" in report
    assert "How it is currently recorded" in report
    assert "How it should be treated" in report
    assert "Specific rule/source basis" in report
    assert "Faction review is explicitly excluded" in report


def test_core_rules_maintained_mirror_audit_retains_both_non_affiliated_providers() -> None:
    audit = core_rules_maintained_mirror_audit()

    assert audit.audit_id == "core-rules-maintained-app-mirrors-2026-09-02"
    assert audit.project_authority_policy_id == (
        "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
    )
    assert tuple(provider.provider_name for provider in audit.providers) == (
        "40k.app",
        "Game Datamissions",
    )
    assert all(
        provider.affiliation == "not_affiliated_with_or_endorsed_by_games_workshop"
        and not provider.runtime_input
        and not provider.owned_by_games_workshop
        for provider in audit.providers
    )
    assert tuple(observation.app_version for observation in audit.observations) == (
        None,
        "931",
        "946",
    )
    assert all(
        observation.app_version is not None or observation.observed_at is not None
        for observation in audit.observations
    )
    assert all(observation.transcription_sha256 for observation in audit.observations)
    assert all(observation.source_observation_sha256 for observation in audit.observations)
    assert audit.comparison_identity_fields == ("rule_source_id", "app_version")
    assert audit.mismatch_disposition == "official_app_comparison_required"

    report = core_rules_maintained_mirror_markdown(audit)
    assert CORE_RULES_MAINTAINED_MIRROR_REPORT_PATH.read_text(encoding="utf-8") == report
    assert "40k.app" in report
    assert "Game Datamissions" in report
    assert "Neither provider is presented as owned" in report
    assert "A mismatch is rejected" in report


def test_core_rules_maintained_mirror_audit_rejects_incomplete_or_drifted_tuple(
    tmp_path: Path,
) -> None:
    payload = json.loads(CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH.read_text(encoding="utf-8"))
    observation = payload["observations"][1]
    observation["app_version"] = None
    observation["observed_at"] = None
    tampered_path = tmp_path / "missing-version-and-timestamp.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="requires an App-data version or timestamp"):
        load_core_rules_maintained_mirror_audit(tampered_path)

    payload = json.loads(CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["observations"][1]["reviewed_statement"] += " Drifted."
    tampered_path = tmp_path / "drifted-transcription.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="transcription hash drifted"):
        load_core_rules_maintained_mirror_audit(tampered_path)

    payload = json.loads(CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["providers"][1]["owned_by_games_workshop"] = True
    tampered_path = tmp_path / "false-official-provider.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="provider authority boundary drifted"):
        load_core_rules_maintained_mirror_audit(tampered_path)


def test_core_rules_40k_app_audit_rejects_url_and_scope_drift(tmp_path: Path) -> None:
    for index, invalid_url in enumerate(
        (
            "https://example.invalid/rules/01",
            "https://www.40k.app/rules/evil\nsuffix",
            "https://www.40k.app/rules/evil\rsuffix",
            "https://www.40k.app/rules/evil\tsuffix",
        )
    ):
        payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
        payload["categories"][0]["provider_url"] = invalid_url
        tampered_path = tmp_path / f"tampered-url-{index}.audit.json"
        tampered_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ValueError, match=r"40k\.app rules URL"):
            load_core_rules_forty_k_app_audit(tampered_path)

    payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["scope"]["review_scope"] = "factions"
    tampered_path = tmp_path / "tampered-scope.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="core-rules-only scope"):
        load_core_rules_forty_k_app_audit(tampered_path)


def test_core_rules_40k_app_audit_rejects_authority_policy_id_drift(tmp_path: Path) -> None:
    payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["provider"]["project_authority_policy_id"] = "core-rules-source-policy:wrong"
    tampered_path = tmp_path / "tampered-authority-policy.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="provider authority boundary drifted"):
        load_core_rules_forty_k_app_audit(tampered_path)


def test_core_rules_40k_app_audit_rejects_retained_finding_hash_drift(tmp_path: Path) -> None:
    payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
    hidden_finding = next(
        row for row in payload["findings"] if row["finding_id"] == "hidden-unverified-source-13-09"
    )
    hidden_finding["evidence_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered-retained-finding-hash.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="finding evidence hash drifted"):
        load_core_rules_forty_k_app_audit(tampered_path)


def test_core_rules_40k_app_audit_separates_source_observation_from_review_metadata(
    tmp_path: Path,
) -> None:
    payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
    category = payload["categories"][0]
    source_observation_sha256 = category["source_observation_sha256"]
    evidence_sha256 = category["evidence_sha256"]
    assert _source_observation_hash(category, row_kind="categories") == source_observation_sha256
    assert _evidence_hash(category) == evidence_sha256

    category["implementation_status"] = "assessed_no_standalone_remediation"
    category["remediation_pr_ids"] = []
    tampered_path = tmp_path / "review-metadata-only.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    assert _source_observation_hash(category, row_kind="categories") == source_observation_sha256
    assert _evidence_hash(category) != evidence_sha256
    with pytest.raises(ValueError, match="category evidence hash drifted"):
        load_core_rules_forty_k_app_audit(tampered_path)


def test_core_rules_40k_app_audit_rejects_unhashed_or_raw_provider_content(
    tmp_path: Path,
) -> None:
    payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["categories"][0]["category_title"] = "Changed title"
    tampered_path = tmp_path / "unhashed-observation.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="category source-observation hash drifted"):
        load_core_rules_forty_k_app_audit(tampered_path)

    payload = json.loads(CORE_RULES_40K_APP_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["categories"][0]["raw_rule_text"] = "Mirror body must not be retained."
    tampered_path = tmp_path / "raw-provider-content.audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="category fields drifted"):
        load_core_rules_forty_k_app_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_swapped_provider_urls(tmp_path: Path) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    first = payload["datasheets"][0]
    second = payload["datasheets"][1]
    first["observed_provider_url"], second["observed_provider_url"] = (
        second["observed_provider_url"],
        first["observed_provider_url"],
    )
    tampered_path = tmp_path / "tampered-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="datasheet evidence hash drifted"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_cross_datasheet_assignment_evidence(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    fulgrim_deep_strike = next(
        row for row in payload["assignments"] if row["source_assignment_id"] == "000004077:2"
    )
    terminator_deep_strike = next(
        row for row in payload["assignments"] if row["source_assignment_id"] == "000004081:1"
    )
    provider_evidence_fields = (
        "observed_provider_datasheet_id",
        "observed_provider_surface",
        "observed_provider_assignment_id",
        "observed_provider_definition_id",
        "observed_provider_name",
        "observed_provider_qualifiers",
        "evidence_sha256",
    )
    for field in provider_evidence_fields:
        fulgrim_deep_strike[field], terminator_deep_strike[field] = (
            terminator_deep_strike[field],
            fulgrim_deep_strike[field],
        )
    tampered_path = tmp_path / "cross-datasheet-assignment-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Provider parent datasheet mismatched"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_unhashed_delta_record_change(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    heldrake_movement = next(
        row
        for row in payload["datasheet_deltas"]
        if row["source_operation_id"] == "ec-heldrake-profile" and row["field"] == "M"
    )
    heldrake_movement["observed_provider_record_id"] = "mv-ZCUK3B6I"
    tampered_path = tmp_path / "changed-delta-record-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="delta evidence hash drifted"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_cross_datasheet_delta_evidence(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    tormentor_power_sword = next(
        row
        for row in payload["datasheet_deltas"]
        if row["source_operation_id"] == "ec-tormentors-power-sword-strength"
    )
    infractor_power_sword = next(
        row
        for row in payload["datasheet_deltas"]
        if row["source_operation_id"] == "ec-infractors-power-sword-strength"
    )
    provider_evidence_fields = (
        "observed_provider_record_kind",
        "observed_provider_record_id",
        "observed_provider_datasheet_id",
        "observed_provider_value",
        "evidence_sha256",
    )
    for field in provider_evidence_fields:
        tormentor_power_sword[field], infractor_power_sword[field] = (
            infractor_power_sword[field],
            tormentor_power_sword[field],
        )
    tampered_path = tmp_path / "cross-datasheet-delta-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Provider parent datasheet mismatched"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_support_renderer_escapes_tables_and_renders_empty_cells() -> None:
    assert _markdown_text("Alpha | Beta") == "Alpha \\| Beta"
    assert _inline_code_list(()) == "None"
    assert _ability_datasheet_pairs_text([]) == "None"
