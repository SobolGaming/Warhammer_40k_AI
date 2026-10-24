"""Authenticate reviewed S25 fixture evolution before unchanged historical pins."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIRECTORY = "data/source_audits/s25"
PRESERVATION_SHA256 = "758f5a4232bc063608c2081a5d94b7e38a203ec7d6c6dcb300adfdef906d7d54"
FILE_PINS: dict[str, dict[str, object]] = {
    "tests/integration/test_retained_shooting.py": {
        "path": "tests/integration/test_retained_shooting.py",
        "baseline_archive": "data/source_audits/s25/baseline-tests/test_retained_shooting.py.txt",
        "base_mode": "100644",
        "base_git_blob": "c2a02eed6a0492a3c28d8d587fbfd758016b82ee",
        "base_raw_bytes": 79179,
        "base_raw_sha256": "766a18d87c0e93eefd247133cf7ff47aadfec78752bc5b676fa82c281d363037",
        "current_mode": "100644",
        "current_git_blob": "da1e922f32e17a107eb5c87893adb30c5d05d009",
        "current_raw_bytes": 79460,
        "current_raw_sha256": "72f1b2390db1f5013e96bcb43bd985a39115b5055470a128698e5c3b474c107a",
        "current_lf_bytes": 79460,
        "current_lf_sha256": "72f1b2390db1f5013e96bcb43bd985a39115b5055470a128698e5c3b474c107a",
    },
    "tests/unit/test_order92_random_melee.py": {
        "path": "tests/unit/test_order92_random_melee.py",
        "baseline_archive": (
            "data/source_audits/s25/baseline-tests/test_order92_random_melee.py.txt"
        ),
        "base_mode": "100644",
        "base_git_blob": "f95115c86521902eccd4dcb230f26c506a1f92b7",
        "base_raw_bytes": 49099,
        "base_raw_sha256": "791195d1226c39ce7856526c6653d0710648307e1fa80ec15ebd17f9c65c607d",
        "current_mode": "100644",
        "current_git_blob": "0ea4ce2f484f2d899b97c1d7f2dfe400dd0aada8",
        "current_raw_bytes": 49124,
        "current_raw_sha256": "aaec568588bd6c93867457cb1bbb9c9b397096802464de57b440f9e300befe59",
        "current_lf_bytes": 49124,
        "current_lf_sha256": "aaec568588bd6c93867457cb1bbb9c9b397096802464de57b440f9e300befe59",
    },
}
HELPER_PINS: dict[str, dict[str, object]] = {
    "tests/s25_original_fixture_controls.py": {
        "path": "tests/s25_original_fixture_controls.py",
        "raw_bytes": 2715,
        "raw_sha256": "65c77909ab6711f2687de7dedc39a840db5adb710e37b4f52126711698a8ebbd",
    },
    "tests/random_melee_helpers.py": {
        "path": "tests/random_melee_helpers.py",
        "raw_bytes": 9924,
        "raw_sha256": "407c76f7be4eded9ffcbe27c4593653be630d3a4114b5f441f2994d7a8a83bb8",
    },
}
# Authenticate current integration fixtures before the unchanged historical pins.
# The preimage is byte-identical to FILE_PINS' reviewed S25 current source.
INTEGRATION_RANDOM_PREIMAGE = (
    "data/source_audits/integration_2026_10_19/test_order92_random_melee.before.py.txt"
)
INTEGRATION_RANDOM_RAW_BYTES = 49370
INTEGRATION_RANDOM_RAW_SHA256 = "d66808312139f8931f3476fe076293ad78e94ec3a27965f8442d9c788df52164"
MANIFEST_HEADER: dict[str, object] = {
    "schema": "s25-explicit-fixture-archival-preservation-v1",
    "base": "b652c9f8148963a5a9f9a79d5ddf5e9bd230d971",
    "base_tree": "9afc837e21d2340b6f26773d3b97e546809976c6",
    "fixture_reviewed_head": "7a67043cc86d8772659769a94cffef289a6e3b2c",
    "fixture_reviewed_tree": "55eb0071db356683f87f4fead17eaef5fb2ac444",
    "qualifications": {
        "actual_current_source_byte_equal_to_BASE": False,
        "identical_rng_or_replay_history_claim": False,
        "complete_original_assertions_With_branches_decorators_ceilings_preserved": True,
        "archival_source_quality_only": True,
        "runtime_compatibility_shim": False,
        "passing_gate_or_CLEAN_credit": False,
    },
    "review_evidence": {
        "exact_design_SHA256": "de18d09f5696b3714e4f92162ab04dc90831171786c99024dd90ffba1e334201",
        "same_coding_design_PROOF_SHA256": (
            "0b357c3f468f7e84c077a30706f81688604bd43554d55004a08cfd3791d2d8c4"
        ),
        "same_rules_design_PROOF_SHA256": (
            "8f89e9f6eb04f3cd4b50bef3d6df5eacb0a29322125f5b56576f981011595acc"
        ),
        "coding_bounded_fixture_closure_PROOF_SHA256": (
            "7257238b1f9e0422c9fe817c6266eff923a0d2afb6f08fbcebce7928e2981821"
        ),
        "rules_bounded_fixture_closure_PROOF_SHA256": (
            "77ff1b358e590bc41ecae2dca0a15f31e3290d9f823ce4cfdc521c6310f644a0"
        ),
        "complete_failed_quality_preserved_no_credit_SHA256": (
            "86f14d432ac638f7ae9a4e376f8a719cd4f8b4bc908b2c836eb3f816eae7ec81"
        ),
    },
}


def _same_manifest_value(actual: object, expected: object) -> None:
    # JSON distinguishes integer/bool and integer/float identities that ordinary
    # Python equality would conflate. No source or path normalization occurs.
    assert json.dumps(actual, sort_keys=True, separators=(",", ":")) == json.dumps(
        expected, sort_keys=True, separators=(",", ":")
    )


def assert_s25_manifest_layout(payload: object) -> None:
    """Reject path/identity drift independently of the manifest byte pin."""
    assert isinstance(payload, dict)
    manifest = cast(dict[str, object], payload)
    assert set(manifest) == set(MANIFEST_HEADER) | {"files", "helpers"}
    for field, expected in MANIFEST_HEADER.items():
        _same_manifest_value(manifest[field], expected)
    for field, expected_rows in (("files", FILE_PINS), ("helpers", HELPER_PINS)):
        supplied = manifest[field]
        assert isinstance(supplied, list)
        rows = cast(list[object], supplied)
        assert len(rows) == 2
        seen: set[str] = set()
        for raw_row in rows:
            assert isinstance(raw_row, dict)
            row = cast(dict[str, object], raw_row)
            path = row.get("path")
            assert isinstance(path, str)
            assert path in expected_rows
            assert path not in seen
            seen.add(path)
            _same_manifest_value(row, expected_rows[path])
        assert seen == set(expected_rows)


def _pinned_bytes(path: Path, size: object, digest: object) -> bytes:
    assert path.is_file()
    assert not path.is_symlink()
    assert path.resolve().is_relative_to(ROOT.resolve())
    raw = path.read_bytes()
    assert len(raw) == size
    assert hashlib.sha256(raw).hexdigest() == digest
    return raw


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _one_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    targets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
    assert len(targets) == 1
    target = targets[0]
    assert isinstance(target, ast.FunctionDef)
    assert target in tree.body
    return target


def _one_call(function: ast.FunctionDef, name: str) -> ast.Call:
    targets = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]
    assert len(targets) == 1
    return targets[0]


def _one_keyword(call: ast.Call, name: str) -> ast.keyword:
    targets = [keyword for keyword in call.keywords if keyword.arg == name]
    assert len(targets) == 1
    return targets[0]


def _expression(text: str) -> ast.expr:
    return ast.parse(text, mode="eval").body


def _same_ast(actual: ast.AST, expected: ast.AST) -> None:
    assert ast.dump(actual, include_attributes=False) == ast.dump(
        expected, include_attributes=False
    )


def _integration_reviewed_random_bytes(current: bytes) -> bytes:
    """Permit only two literal fixture changes; retain the entire assertion AST."""
    pin = FILE_PINS["tests/unit/test_order92_random_melee.py"]
    before = _pinned_bytes(
        ROOT / INTEGRATION_RANDOM_PREIMAGE,
        pin["current_raw_bytes"],
        pin["current_raw_sha256"],
    )
    expected, actual = ast.parse(before), ast.parse(current)
    # This change is already present in the accepted incoming Section25 handoff.
    cleave = _one_function(
        expected, "test_random_cleave_is_a_single_target_bonus_never_a_splittable_budget"
    )
    call = _one_call(cleave, "random_melee_session")
    _same_ast(
        call, _expression('random_melee_session(cleave=True, game_id="order92-cleave-name-2")')
    )
    _one_keyword(call, "game_id").value = ast.Constant(value="order92-cleave-name-3")
    call.keywords.append(ast.keyword(arg="pause_at_first_hit", value=ast.Constant(value=True)))
    # Fixed-A otherwise rolls two wound ones and never reaches its existing
    # primary-kill/extra-pool assertions. The random variant identity is unchanged.
    fixture = _one_function(expected, "_lethal_extra_session")
    identity = _one_keyword(_one_call(fixture, "fight_lifecycle"), "game_id")
    _same_ast(identity.value, _expression('"order56-retained-fight-0"'))
    identity.value = _expression(
        '"order56-retained-fight-0" if random else "order112-lethal-extra-fixed"'
    )
    _same_ast(actual, expected)
    return before


def assert_s25_fixture_only_ast(path: str, original: bytes, current: bytes) -> None:
    """Check the actual complete module after only literal reviewed substitutions.

    Current byte authentication is separate so negative controls exercise this
    very validator even if a proposed new digest accompanied a weakened test.
    """
    assert path in FILE_PINS
    pin = FILE_PINS[path]
    assert len(original) == pin["base_raw_bytes"]
    assert hashlib.sha256(original).hexdigest() == pin["base_raw_sha256"]
    if path == "tests/unit/test_order92_random_melee.py":
        current = _integration_reviewed_random_bytes(current)
    expected, actual = ast.parse(original), ast.parse(current)
    if path == "tests/unit/test_order92_random_melee.py":
        name = "test_all_weapons_commit_before_dice_and_each_budget_is_conserved"
        before = _one_function(expected, name)
        after = _one_function(actual, name)
        call = _one_call(before, "random_melee_session")
        _one_call(after, "random_melee_session")
        _same_ast(call, _expression("random_melee_session(extra=extra, attacker_models=models)"))
        call.keywords.append(ast.keyword(arg="pause_at_first_hit", value=ast.Constant(value=True)))
    else:
        assert path == "tests/integration/test_retained_shooting.py"
        name = "test_order_30_unending_fidelity_executes_one_selected_attack"
        before = _one_function(expected, name)
        after = _one_function(actual, name)
        call = _one_call(before, "fight_lifecycle")
        _one_call(after, "fight_lifecycle")
        catalog = _one_keyword(call, "catalog")
        _same_ast(catalog.value, _expression("unending_fidelity_catalog()"))
        catalog.value = ast.Call(
            func=ast.Name(id="retained_distinct_weapon_catalog", ctx=ast.Load()),
            args=[catalog.value],
            keywords=[],
        )
        specs = _one_keyword(call, "enemy_unit_specs")
        _same_ast(
            specs.value,
            _expression(
                '{"enemy": ("core-intercessor-like-infantry", "core-intercessor-like", 1)} '
                "if attached else None"
            ),
        )
        specs.value = _expression(
            '{"enemy": ("core-intercessor-like-infantry", "core-intercessor-like", 1), '
            '"leader": (RETAINED_DISTINCT_LEADER_DATASHEET_ID, "core-character-leader", 1)} '
            "if attached else None"
        )
        imports = [
            (index, node)
            for index, node in enumerate(expected.body)
            if isinstance(node, ast.ImportFrom) and node.module == "tests.retained_attack_helpers"
        ]
        assert len(imports) == 1
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module == "tests.s25_original_fixture_controls"
            for node in ast.walk(expected)
        )
        current_imports = [
            node
            for node in ast.walk(actual)
            if isinstance(node, ast.ImportFrom)
            and node.module == "tests.s25_original_fixture_controls"
        ]
        assert len(current_imports) == 1
        added_import = ast.parse(
            "from tests.s25_original_fixture_controls import "
            "RETAINED_DISTINCT_LEADER_DATASHEET_ID, retained_distinct_weapon_catalog"
        ).body[0]
        _same_ast(current_imports[0], added_import)
        expected.body.insert(imports[0][0] + 1, added_import)
    _same_ast(actual, expected)


def preserved_s25_predecessor_test_bytes(path: str, current: bytes) -> bytes:
    """Authenticate current source and its precise evolution before archival projection."""
    if path not in FILE_PINS:
        return current
    assert isinstance(current, bytes)
    manifest_path = ROOT / ARCHIVE_DIRECTORY / "test-preservation.json"
    manifest_raw = manifest_path.read_bytes()
    assert hashlib.sha256(manifest_raw).hexdigest() == PRESERVATION_SHA256
    assert_s25_manifest_layout(json.loads(manifest_raw))
    for helper_path, helper in HELPER_PINS.items():
        _pinned_bytes(ROOT / helper_path, helper["raw_bytes"], helper["raw_sha256"])
    pin = FILE_PINS[path]
    supplied_current = current
    if path == "tests/unit/test_order92_random_melee.py":
        integration_raw = _pinned_bytes(
            ROOT / path, INTEGRATION_RANDOM_RAW_BYTES, INTEGRATION_RANDOM_RAW_SHA256
        )
        assert current in (integration_raw, integration_raw.replace(b"\r\n", b"\n"))
        actual_raw = _integration_reviewed_random_bytes(current)
        current = actual_raw
    else:
        actual_raw = _pinned_bytes(ROOT / path, pin["current_raw_bytes"], pin["current_raw_sha256"])
    normalized = actual_raw.replace(b"\r\n", b"\n")
    assert len(normalized) == pin["current_lf_bytes"]
    assert hashlib.sha256(normalized).hexdigest() == pin["current_lf_sha256"]
    assert current in (actual_raw, normalized)
    assert _git_blob(actual_raw) == pin["current_git_blob"]
    archive = ROOT / cast(str, pin["baseline_archive"])
    assert archive.resolve().is_relative_to((ROOT / ARCHIVE_DIRECTORY).resolve())
    assert pin["base_mode"] == pin["current_mode"] == "100644"
    original = _pinned_bytes(archive, pin["base_raw_bytes"], pin["base_raw_sha256"])
    assert _git_blob(original) == pin["base_git_blob"]
    assert_s25_fixture_only_ast(path, original, supplied_current)
    return original
