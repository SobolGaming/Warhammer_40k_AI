from __future__ import annotations

import ast
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
ATTACK_SEQUENCE_SPLIT_PATHS = tuple(sorted(ATTACK_SEQUENCE_PATH.parent.glob("attack_sequence*.py")))
DAMAGE_ALLOCATION_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "damage_allocation.py"
HAZARD_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "hazard.py"
GAME_STATE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "game_state.py"
UNIT_STATE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "unit_state.py"
HEALING_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "healing.py"
DATASHEET_PATH = ROOT / "src" / "warhammer40k_core" / "core" / "datasheet.py"
ATTACHMENT_ELIGIBILITY_PATH = (
    ROOT / "src" / "warhammer40k_core" / "core" / "attachment_eligibility.py"
)
LIST_VALIDATION_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "list_validation.py"
ARMY_MUSTERING_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "army_mustering.py"
ATTACHED_UNIT_FORMATION_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "attached_unit_formation.py"
)
STRATAGEMS_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems.py"
STRATAGEMS_SPLIT_PATHS = tuple(sorted(STRATAGEMS_PATH.parent.glob("stratagems*.py")))
SHOOTING_PHASE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "shooting.py"
SHOOTING_PHASE_SPLIT_PATHS = tuple(sorted(SHOOTING_PHASE_PATH.parent.glob("shooting*.py")))
ADAPTER_CONTRACT_PATH = ROOT / "docs" / "ADAPTER_DECISION_CONTRACT.md"


def _function_source_from_paths(paths: tuple[Path, ...], function_name: str) -> str:
    for path in paths:
        module_source = path.read_text(encoding="utf-8")
        module = ast.parse(module_source)
        for node in module.body:
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                source = ast.get_source_segment(module_source, node)
                assert source is not None
                return source
    raise AssertionError(f"Function {function_name} not found.")


def _attack_sequence_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in ATTACK_SEQUENCE_SPLIT_PATHS)


def _stratagems_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in STRATAGEMS_SPLIT_PATHS)


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


def test_phase14i_core_ability_source_rows_have_no_unsupported_handlers() -> None:
    unsupported_rows = tuple(
        row for row in ability_rows() if row.handler_id.startswith("unsupported:")
    )

    assert tuple((row.ability_id, row.handler_id) for row in unsupported_rows) == ()


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
    assert "future ability-runtime families" in phase14i_section
    assert "runtime effects complete" in phase14i_section
    assert "STEALTH grants Benefit of Cover against ranged attacks" not in phase14i_section
    assert "[PSYCHIC] modifier-ignore submissions" not in phase14i_section
    assert "[ONE SHOT] first weapon selection is legal" not in phase14i_section
    assert "Super-heavy Walker movement is offered" not in phase14i_section


def test_phase14h_transport_blocker_and_attached_toughness_cutover_are_explicit() -> None:
    transport_source = TRANSPORTS_PATH.read_text(encoding="utf-8")
    attack_sequence_source = _attack_sequence_source()
    damage_allocation_source = DAMAGE_ALLOCATION_PATH.read_text(encoding="utf-8")
    hazard_source = HAZARD_PATH.read_text(encoding="utf-8")
    game_state_source = GAME_STATE_PATH.read_text(encoding="utf-8")
    unit_state_source = UNIT_STATE_PATH.read_text(encoding="utf-8")
    healing_source = HEALING_PATH.read_text(encoding="utf-8")
    datasheet_source = DATASHEET_PATH.read_text(encoding="utf-8")
    attachment_eligibility_source = ATTACHMENT_ELIGIBILITY_PATH.read_text(encoding="utf-8")
    list_validation_source = LIST_VALIDATION_PATH.read_text(encoding="utf-8")
    army_mustering_source = ARMY_MUSTERING_PATH.read_text(encoding="utf-8")
    attached_unit_formation_source = ATTACHED_UNIT_FORMATION_PATH.read_text(encoding="utf-8")
    stratagems_source = _stratagems_source()

    assert "def resolve_combat_disembark(" in transport_source
    assert "Combat Disembark requires resolve_combat_disembark." in transport_source
    assert "combat_disembark.hazard_roll" in transport_source
    assert "apply_transport_hazard_mortal_wounds" in transport_source
    assert "transport_hazard_mortal_wounds" in transport_source
    assert "HAZARD_ROLL_FAILURE_THRESHOLD = 2" in hazard_source
    assert "hazard_mortal_wounds_per_failed_roll" in attack_sequence_source
    assert "pending_destroyed_transport_disembark" in attack_sequence_source
    assert "destroyed_transport_disembark_placement_requested" in attack_sequence_source
    assert "apply_destroyed_transport_disembark_proposal_decision" in attack_sequence_source
    assert "remove_transport_cargo_state" in game_state_source
    assert "def add_unit_to_army(" in game_state_source
    assert "def apply_strategic_reserve_declarations(" in game_state_source
    assert "def declare_battle_formation_embarkation(" in game_state_source
    assert "def reposition_unit_to_strategic_reserves(" in game_state_source
    assert "is_at_half_strength" in unit_state_source
    assert "attached_unit_bodyguard_model_ids" in attack_sequence_source
    assert "_highest_toughness_for_models" in attack_sequence_source
    assert '"attached-role:leader" in model.source_ids' in damage_allocation_source
    assert '"attached-role:support" in model.source_ids' in damage_allocation_source
    assert "SELECT_HEALING_MODEL_DECISION_TYPE" in healing_source
    assert "resolve_healing_until_blocked" in healing_source
    assert "apply_healing_model_decision" in healing_source
    assert "with_returned_model_placement" in healing_source
    assert "phase_start_enemy_engagement_model_ids" in healing_source
    assert "attachment_eligibilities" in datasheet_source
    assert "class AttachmentEligibility" in attachment_eligibility_source
    assert "class AttachmentDeclaration" in list_validation_source
    assert "class AttachedUnitFormation" in attached_unit_formation_source
    assert "def _resolve_attached_unit_formations(" in army_mustering_source
    assert "def _validate_required_support_attachments(" in army_mustering_source
    assert (
        "Support units must be declared as part of an attached unit during mustering."
        in army_mustering_source
    )
    assert "AttachmentRole.LEADER" in army_mustering_source
    assert "AttachmentRole.SUPPORT" in army_mustering_source
    assert '"runtime-attached-unit:{role}"' in army_mustering_source
    assert "def _starting_strength_records_for_army(" in game_state_source
    assert "def _starting_strength_record_for_attached_unit(" in game_state_source
    assert "def _remove_attached_unit_formation(" in game_state_source
    assert "attached_unit.component_unit_instance_ids" in stratagems_source


def test_phase14h_shooting_selector_and_range_helpers_are_rules_unit_aware() -> None:
    active_selector_source = _function_source_from_paths(
        SHOOTING_PHASE_SPLIT_PATHS,
        "_active_player_placed_unit_ids",
    )
    legal_selector_source = _function_source_from_paths(
        SHOOTING_PHASE_SPLIT_PATHS, "_legal_shooting_unit_ids"
    )
    options_source = _function_source_from_paths(
        SHOOTING_PHASE_SPLIT_PATHS, "_shooting_unit_options"
    )
    available_weapons_source = _function_source_from_paths(
        SHOOTING_PHASE_SPLIT_PATHS,
        "_available_weapons_for_rules_unit",
    )
    range_source = _function_source_from_paths(
        SHOOTING_PHASE_SPLIT_PATHS, "_unit_target_within_max_range"
    )

    assert "rules_unit_id_for_unit_id" in active_selector_source
    assert "unit_ids.append(placement.unit_instance_id)" not in active_selector_source
    assert "seen: set[str]" in active_selector_source

    assert "rules_unit_view_by_id" in legal_selector_source
    assert "_unit_by_id" not in legal_selector_source
    assert "_rules_unit_has_legal_shooting_declaration" in legal_selector_source
    assert "legal.append(rules_unit.unit_instance_id)" in legal_selector_source

    assert "option_id=rules_unit.unit_instance_id" in options_source
    assert '"unit_instance_id": rules_unit.unit_instance_id' in options_source
    assert "_available_weapons_for_unit" in available_weapons_source
    assert "for component in rules_unit.components" in available_weapons_source

    assert "target_within_shooting_selection_range" in range_source
    assert "rules_unit_view_from_armies" not in range_source
    assert "_unit_placements_for_rules_unit_or_none" not in range_source
    assert "unit_placement_by_id(component" not in range_source


def test_phase14h_docs_mark_complete_after_attached_formation_cutover() -> None:
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")
    phase14h_section = architecture.split("## Phase 14H:", maxsplit=1)[1].split(
        "\n## Phase 14I:",
        maxsplit=1,
    )[0]

    assert "Status: Complete." in phase14h_section
    assert "Phase 14H is complete" in architecture
    assert "Phase 14H is complete" in readme
    assert "Phase 14H remains deferred" not in architecture
    assert "Phase 14H remains deferred" not in readme
    assert "runtime Attached Unit formation" in architecture
    assert "runtime Attached Unit formation" in readme
    assert "structured army-list Leader/Support declarations" in architecture
    assert "structured army-list Leader/Support declarations" in readme
    assert "first-class attached rules-unit formation records" in architecture
    assert "first-class attached rules-unit formation records" in readme
    assert "Broader real-faction Leader/Support eligibility data" in architecture
    assert "runtime attached-unit formation;" not in readme
    assert "open blocker" not in phase14h_section
    assert "Healing Wounds primitive now iterates each healing amount" in architecture
    assert "healing, revival, persisting effects" in readme
    assert "Movement-phase Combat Disembark fallback now accepts Combat mode" in architecture
    assert "Movement-phase Combat Disembark fallback with engine-owned" in readme
    assert "Attached Unit formation" in architecture
    assert "full repositioned-unit effect persistence" not in architecture
    assert "setup-time reserve/transport declarations" not in architecture
    assert "setup-time Strategic Reserve declarations" in architecture
    assert "setup-time Strategic Reserve declarations" in readme
    assert "repositioned-unit Advance/Fall Back/Disembark history" in architecture
    assert "repositioned-unit Advance/Fall Back/Disembark history" in readme
    assert "destroyed-Transport orchestration from real destruction timing" not in architecture
    assert "destroyed-Transport orchestration from real destruction timing" not in readme
    adapter_contract = ADAPTER_CONTRACT_PATH.read_text(encoding="utf-8")
    assert "player-facing destruction-time host remains Phase 14H work" not in adapter_contract
    assert "actual destruction event before Transport removal and Deadly Demise" in adapter_contract
    assert "mixed-Toughness attached-unit attack handling" not in architecture
    assert "mixed-Toughness attached-unit attack handling" not in readme
