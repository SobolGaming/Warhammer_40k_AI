from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "warhammer40k_core"
FACTION_CONTENT_ROOT = PACKAGE / "engine" / "faction_content"

MAX_MODULE_LINES = 1500
GENERATED_FACTION_CONTENT_MAX_MODULE_LINES = 2000

LEGACY_OVERSIZED_MODULE_LIMITS = {
    "src/warhammer40k_core/core/datasheet.py": 1927,
    "src/warhammer40k_core/core/missions.py": 3553,
    "src/warhammer40k_core/core/ruleset_descriptor.py": 2879,
    "src/warhammer40k_core/engine/army_mustering.py": 3665,
    "src/warhammer40k_core/engine/battlefield_state.py": 1703,
    "src/warhammer40k_core/engine/catalog_rule_consumption.py": 6388,
    "src/warhammer40k_core/engine/cult_ambush.py": 1864,
    "src/warhammer40k_core/engine/damage_allocation.py": 3094,
    "src/warhammer40k_core/engine/deployment.py": 1750,
    "src/warhammer40k_core/engine/fight_order.py": 2000,
    "src/warhammer40k_core/engine/fight_resolution.py": 3324,
    "src/warhammer40k_core/engine/game_state.py": 7360,
    "src/warhammer40k_core/engine/healing.py": 1605,
    "src/warhammer40k_core/engine/lifecycle.py": 3921,
    "src/warhammer40k_core/engine/mission_decisions.py": 1560,
    "src/warhammer40k_core/engine/phases/charge.py": 3881,
    "src/warhammer40k_core/engine/phases/fight.py": 4065,
    "src/warhammer40k_core/engine/prebattle.py": 3546,
    "src/warhammer40k_core/engine/reserves.py": 2845,
    "src/warhammer40k_core/engine/rule_execution.py": 1793,
    "src/warhammer40k_core/engine/scoring.py": 4264,
    "src/warhammer40k_core/engine/shooting_targets.py": 1683,
    "src/warhammer40k_core/engine/transports.py": 3567,
    "src/warhammer40k_core/engine/triggered_movement.py": 2271,
    "src/warhammer40k_core/geometry/pathing.py": 2422,
    "src/warhammer40k_core/geometry/visibility.py": 1922,
    "src/warhammer40k_core/rules/mfm_source.py": 1814,
    "src/warhammer40k_core/rules/rule_parser.py": 2887,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "chapter_approved_2026_27.py": 1619,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "event_companion_2026_06.py": 3621,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "event_companion_base_size_rows.py": 8674,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "faction_coverage_2026_27.py": 1535,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "faction_subrules_2026_27.py": 2957,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "adepta_sororitas.py": 2041,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "adeptus_custodes.py": 2169,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "adeptus_mechanicus.py": 2320,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/aeldari.py": 4050,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "astra_militarum.py": 4278,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "black_templars.py": 5799,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "blood_angels.py": 6532,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "chaos_daemons.py": 2698,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "chaos_space_marines.py": 3630,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "dark_angels.py": 6508,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "death_guard.py": 2086,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "deathwatch.py": 5596,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "drukhari.py": 1671,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "genestealer_cults.py": 1662,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "grey_knights.py": 1987,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "imperial_agents.py": 2728,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "imperial_knights.py": 1590,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "leagues_of_votann.py": 1561,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/necrons.py": 3305,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/orks.py": 3483,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "space_marines.py": 6591,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "space_wolves.py": 6815,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "tau_empire.py": 2598,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "thousand_sons.py": 2075,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "tyranids.py": 3130,
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/mfm_2026_06/"
    "world_eaters.py": 1934,
    "src/warhammer40k_core/rules/wahapedia_bridge.py": 2425,
}


def test_new_modules_stay_within_size_budget() -> None:
    violations: list[str] = []

    for path in sorted(PACKAGE.rglob("*.py")):
        if _is_faction_content_module(path):
            continue
        relative_path = path.relative_to(ROOT).as_posix()
        line_count = _line_count(path)
        legacy_limit = LEGACY_OVERSIZED_MODULE_LIMITS.get(relative_path)
        if legacy_limit is not None:
            if line_count > legacy_limit:
                violations.append(f"{relative_path} grew from {legacy_limit} to {line_count} lines")
        elif line_count > MAX_MODULE_LINES:
            violations.append(f"{relative_path} has {line_count} lines")

    assert not violations, "Module size policy violations:\n" + "\n".join(violations)


def test_legacy_module_size_allowlist_only_shrinks() -> None:
    stale_entries: list[str] = []

    for relative_path in sorted(LEGACY_OVERSIZED_MODULE_LIMITS):
        path = ROOT / relative_path
        if not path.exists():
            stale_entries.append(f"{relative_path} no longer exists")
            continue
        line_count = _line_count(path)
        if line_count <= MAX_MODULE_LINES:
            stale_entries.append(f"{relative_path} is now {line_count} lines")

    assert not stale_entries, "Remove stale module-size allowlist entries:\n" + "\n".join(
        stale_entries
    )


def test_faction_content_modules_use_existing_size_budget() -> None:
    violations: list[str] = []

    for path in sorted(FACTION_CONTENT_ROOT.rglob("*.py")):
        line_count = _line_count(path)
        if line_count > GENERATED_FACTION_CONTENT_MAX_MODULE_LINES:
            violations.append(f"{path.relative_to(ROOT).as_posix()} has {line_count} lines")

    assert not violations, "Faction-content modules exceed their size budget:\n" + "\n".join(
        violations
    )


def _is_faction_content_module(path: Path) -> bool:
    return path.is_relative_to(FACTION_CONTENT_ROOT)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
