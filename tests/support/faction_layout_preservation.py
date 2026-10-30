"""Authenticate relocated faction tests before historical or live reference reads."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import NotRequired, TypedDict, cast

MANIFEST = "data/source_audits/faction_test_layout/preservation.json"
MANIFEST_SHA256 = "7b092d9304f52885883d09c32893a35589419d6bf95dbf1331a60ce3cd51442a"
ORIGINALS = frozenset(
    [
        "tests/factions/aeldari/test_selected_consumers.py",
        "tests/factions/chaos_daemons/test_bloodcrushers_consumers.py",
        "tests/factions/chaos_daemons/test_bloodcrushers_reserves.py",
        "tests/unit/test_phase17g_adeptus_custodes_army_rule.py",
        "tests/unit/test_phase17g_aeldari_army_rule.py",
        "tests/unit/test_phase17g_death_guard_army_rule.py",
        "tests/unit/test_phase17g_death_guard_army_rule.py",
        "tests/unit/test_phase17g_grey_knights_army_rule.py",
        "tests/unit/test_phase17g_leagues_of_votann_army_rule.py",
        "tests/unit/test_phase17g_necrons_army_rule.py",
        "tests/unit/test_phase17g_orks_army_rule.py",
        "tests/unit/test_phase17g_tau_empire_army_rule.py",
        "tests/unit/test_phase17g_tyranids_army_rule.py",
        "tests/unit/test_phase17g_world_eaters_army_rule.py",
    ]
)


class LayoutRecord(TypedDict):
    archive: str
    original_sha256: str
    definitions: dict[str, str]
    successors: dict[str, str]
    appended_body_assertions: NotRequired[dict[str, int]]


class LayoutManifest(TypedDict):
    schema: str
    originals: dict[str, LayoutRecord]


def _read(root: Path, relative: str) -> bytes:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Faction layout evidence path escapes its root.")
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Faction layout evidence cannot use an alias.")
    return path.read_bytes()


def _definitions(
    raw: bytes,
    *,
    shadow_fixture_maintenance: bool = False,
    world_eaters_lookup_maintenance: bool = False,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in ast.parse(raw).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in result:
                raise ValueError("Duplicate faction layout definition.")
            if shadow_fixture_maintenance and node.name == (
                "test_restore_rejects_omitted_mandatory_shadow_modifier_application"
            ):
                # Only the reviewed deterministic result identity may differ.
                old = "phase17g-tyranids-omitted-modifier-authority:d07:8:unleash:d07-vector:16"
                refreshed = old.removesuffix("16") + "18"
                identities = [
                    value
                    for value in ast.walk(node)
                    if isinstance(value, ast.Constant) and value.value == refreshed
                ]
                if len(identities) != 1:
                    raise ValueError("Shadow omission fixture identity maintenance drifted.")
                identities[0].value = old
            if world_eaters_lookup_maintenance and node.name == (
                "test_world_eaters_army_rule_fail_fast_edges_are_explicit"
            ):
                # The canonical rules-unit lookup keeps the same domain error;
                # only its reviewed diagnostic match differs from the archive.
                matches = [
                    value.value
                    for value in ast.walk(node)
                    if isinstance(value, ast.keyword)
                    and value.arg == "match"
                    and isinstance(value.value, ast.Constant)
                    and value.value.value == "unit_instance_id is unknown"
                ]
                if len(matches) != 1:
                    raise ValueError("Faction layout World Eaters lookup maintenance drifted.")
                matches[0].value = "unit_instance_id was not found"
            result[node.name] = ast.dump(node)
    return result


def verify_layout_original(root: Path, relative: str) -> tuple[bytes, LayoutRecord]:
    if relative not in ORIGINALS:
        raise ValueError("Unknown faction layout original.")
    raw = _read(root, MANIFEST)
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Faction layout preservation manifest drifted.")
    manifest = cast(LayoutManifest, json.loads(raw))
    if manifest["schema"] != "faction-test-layout-preservation-v1" or set(
        manifest["originals"]
    ) != set(ORIGINALS):
        raise ValueError("Faction layout preservation membership drifted.")
    record = manifest["originals"][relative]
    original = _read(root, record["archive"])
    if hashlib.sha256(original).hexdigest() != record["original_sha256"]:
        raise ValueError("Faction layout original bytes drifted.")
    current: dict[str, dict[str, str]] = {}
    for name, expected in record["successors"].items():
        content = _read(root, name)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Faction layout live successor bytes drifted: " + name)
        current[name] = _definitions(
            content,
            shadow_fixture_maintenance=(
                relative == "tests/unit/test_phase17g_tyranids_army_rule.py"
                and name == "tests/factions/tyranids/unit/test_tyranids_army_rule.py"
            ),
            world_eaters_lookup_maintenance=(
                relative == "tests/unit/test_phase17g_world_eaters_army_rule.py"
                and name == "tests/factions/world_eaters/unit/test_world_eaters_army_rule.py"
            ),
        )
    # Explicit extensions preserve the complete original function as a prefix.
    # Every successor, including appended assertions, remains byte-hash pinned above.
    for symbol, statement_count in record.get("appended_body_assertions", {}).items():
        if type(statement_count) is not int or statement_count < 1:
            raise ValueError("Faction layout extension prefix count is invalid.")
        path, target = record["definitions"][symbol].split("::", 1)
        node = next(
            value
            for value in ast.parse(_read(root, path)).body
            if isinstance(value, ast.FunctionDef) and value.name == target
        )
        if len(node.body) <= statement_count or not any(
            isinstance(value, ast.Assert)
            for statement in node.body[statement_count:]
            for value in ast.walk(statement)
        ):
            raise ValueError("Faction layout extension requires appended assertions.")
        node.body = node.body[:statement_count]
        current[path][target] = ast.dump(node)
    before = _definitions(original)
    if before.keys() != record["definitions"].keys():
        raise ValueError("Faction layout definition inventory drifted.")
    for name, reference in record["definitions"].items():
        path, target = reference.split("::", 1)
        if before[name] != current[path][target]:
            raise ValueError("Faction layout assertion/helper/fixture AST drifted.")
    return original, record


def layout_live_reference(root: Path, reference: str) -> str:
    path, separator, name = reference.partition("::")
    if not separator or not name:
        raise ValueError("Live faction layout reference needs a complete definition.")
    _, record = verify_layout_original(root, path)
    outer, *nested = name.split("::")
    symbol, bracket, parameter = outer.partition("[")
    if symbol not in record["definitions"]:
        raise ValueError("Unknown live faction layout definition.")
    mapped = record["definitions"][symbol] + bracket + parameter
    return "::".join((mapped, *nested))
