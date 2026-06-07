from __future__ import annotations

from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_abilities import (
    ability_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_stratagems import (
    core_stratagem_rows,
)

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE_PATH = ROOT / "ARCHITECTURE_V2.md"
README_PATH = ROOT / "README.md"
TRANSPORTS_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "transports.py"
ATTACK_SEQUENCE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "attack_sequence.py"
DAMAGE_ALLOCATION_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "damage_allocation.py"
HAZARD_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "hazard.py"


def test_phase14i_core_stratagem_source_cutover_is_complete() -> None:
    rows = core_stratagem_rows()
    expected_stratagem_ids = {
        "command-reroll",
        "counteroffensive",
        "crushing-impact",
        "epic-challenge",
        "explosives",
        "fire-overwatch",
        "heroic-intervention",
        "insane-bravery",
        "new-orders",
        "rapid-ingress",
        "smokescreen",
    }

    assert {row.stratagem_id for row in rows} == expected_stratagem_ids
    assert [row.stratagem_id for row in rows if row.handler_id.startswith("unsupported:")] == []


def test_phase14i_unsupported_core_ability_contract_is_explicit() -> None:
    unsupported_rows = tuple(
        row for row in ability_rows() if row.handler_id.startswith("unsupported:")
    )

    assert tuple((row.ability_id, row.handler_id) for row in unsupported_rows) == (
        ("core-deadly-demise", "unsupported:phase-13c:deadly-demise"),
        ("core-deep-strike", "unsupported:phase-15b:deep-strike"),
        ("core-feel-no-pain", "unsupported:phase-13c:feel-no-pain"),
        ("core-firing-deck", "unsupported:phase-13d:firing-deck"),
        ("core-infiltrators", "unsupported:phase-15b:infiltrators"),
        ("core-leader", "unsupported:phase-15c:leader"),
        ("core-lone-operative", "unsupported:phase-13b:lone-operative"),
        ("core-scouts", "unsupported:phase-15b:scouts"),
        ("core-stealth", "unsupported:phase-13d:stealth"),
    )


def test_phase14i_docs_mark_complete_without_overclaiming_ability_runtime() -> None:
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    phase14i_section = architecture.split("## Phase 14I:", maxsplit=1)[1].split(
        "\n## ",
        maxsplit=1,
    )[0]

    assert "Status: Complete." in phase14i_section
    assert "Phase 14I is complete" in architecture
    assert "Phase 14I is complete" in readme
    assert "explicit unsupported" in phase14i_section
    assert "descriptors with owning phase IDs" in phase14i_section


def test_phase14h_transport_blocker_and_attached_toughness_cutover_are_explicit() -> None:
    transport_source = TRANSPORTS_PATH.read_text(encoding="utf-8")
    attack_sequence_source = ATTACK_SEQUENCE_PATH.read_text(encoding="utf-8")
    damage_allocation_source = DAMAGE_ALLOCATION_PATH.read_text(encoding="utf-8")
    hazard_source = HAZARD_PATH.read_text(encoding="utf-8")

    assert "def resolve_combat_disembark(" in transport_source
    assert "Combat Disembark requires resolve_combat_disembark." in transport_source
    assert "combat_disembark.hazard_roll" in transport_source
    assert "HAZARD_ROLL_FAILURE_THRESHOLD = 2" in hazard_source
    assert "hazard_mortal_wounds_per_failed_roll" in attack_sequence_source
    assert "attached_unit_bodyguard_model_ids" in attack_sequence_source
    assert "_highest_toughness_for_models" in attack_sequence_source
    assert '"attached-role:leader" in model.source_ids' in damage_allocation_source
    assert '"attached-role:support" in model.source_ids' in damage_allocation_source


def test_phase14h_docs_do_not_mark_complete_while_blockers_remain() -> None:
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    phase14h_section = architecture.split("## Phase 14H:", maxsplit=1)[1].split(
        "\n## Phase 14I:",
        maxsplit=1,
    )[0]

    assert "Status: Deferred." in phase14h_section
    assert "Phase 14H remains deferred" in architecture
    assert "Phase 14H remains deferred" in readme
    assert "Phase 14H is complete" not in architecture
    assert "Phase 14H is complete" not in readme
    assert "mixed-Toughness attached-unit attack handling" not in architecture
    assert "mixed-Toughness attached-unit attack handling" not in readme
