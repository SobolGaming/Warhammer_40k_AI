"""Current fixture evolution must not hide altered original test obligations."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import cast

import pytest

from tests import s25_test_preservation_helpers as preservation
from tests.d09_test_preservation_helpers import preserved_d09_predecessor_test_bytes
from tests.d10_test_preservation_helpers import preserved_d10_predecessor_test_bytes

ROOT = Path(__file__).resolve().parents[2]
RANDOM = "tests/unit/test_order92_random_melee.py"
RETAINED = "tests/integration/test_retained_shooting.py"
PATHS = (RANDOM, RETAINED)
TARGETS = {
    RANDOM: "test_all_weapons_commit_before_dice_and_each_budget_is_conserved",
    RETAINED: "test_order_30_unending_fidelity_executes_one_selected_attack",
}


def _sources(path: str) -> tuple[bytes, bytes]:
    original = ROOT / cast(str, preservation.FILE_PINS[path]["baseline_archive"])
    return original.read_bytes(), (ROOT / path).read_bytes()


@pytest.mark.parametrize("path", PATHS)
def test_current_complete_bytes_and_literal_ast_join_unchanged_historical_chain(path: str) -> None:
    original, current = _sources(path)
    preservation.assert_s25_fixture_only_ast(path, original, current)
    assert preservation.preserved_s25_predecessor_test_bytes(path, current) == original
    assert preserved_d10_predecessor_test_bytes(path, current) == original
    assert preserved_d09_predecessor_test_bytes(path, current) == original
    assert current != original


@pytest.mark.parametrize(
    "path",
    [
        "tests/unit/unreviewed.py",
        "tests/unit/./test_order92_random_melee.py",
        "TESTS/unit/test_order92_random_melee.py",
        "tests\\unit\\test_order92_random_melee.py",
        "tests/unit/test_order92_random_melee.py.unreviewed",
    ],
)
def test_other_paths_are_identical_input_before_lookup_or_normalization(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preservation, "ROOT", tmp_path / "missing")
    current = b"arbitrary\r\nnon-UTF8:\xff"
    assert preservation.preserved_s25_predecessor_test_bytes(path, current) is current


def _remove_node(tree: ast.Module, target: ast.AST) -> None:
    for parent in ast.walk(tree):
        for _field, value in ast.iter_fields(parent):
            if isinstance(value, list) and target in value:
                cast(list[object], value).remove(target)
                return
    raise AssertionError("Mutation target must belong to the actual current module")


def _mutated_current(path: str, kind: str) -> bytes:
    tree = ast.parse(_sources(path)[1])
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == TARGETS[path]
    )
    call_name = "random_melee_session" if path == RANDOM else "fight_lifecycle"
    call = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == call_name
    )
    if kind == "remove_assertion":
        _remove_node(
            tree, next(node for node in ast.walk(function) if isinstance(node, ast.Assert))
        )
    elif kind == "weaken_assertion":
        assertion = next(node for node in ast.walk(function) if isinstance(node, ast.Assert))
        assertion.test = ast.Constant(value=True)
    elif kind == "With":
        with_statement = next(node for node in ast.walk(tree) if isinstance(node, ast.With))
        with_statement.items[0].context_expr = ast.Name(id="unapproved_context", ctx=ast.Load())
    elif kind == "branch":
        branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If))
        branch.test = ast.UnaryOp(op=ast.Not(), operand=branch.test)
    elif kind == "iterator":
        loop = next(node for node in ast.walk(tree) if isinstance(node, ast.For))
        loop.iter = ast.List(elts=[], ctx=ast.Load())
    elif kind == "decorator":
        function.decorator_list.append(ast.Name(id="unapproved_marker", ctx=ast.Load()))
    elif kind == "ceiling":
        range_call = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
            and any(isinstance(arg, ast.Constant) and type(arg.value) is int for arg in node.args)
        )
        constant = next(
            arg
            for arg in range_call.args
            if isinstance(arg, ast.Constant) and type(arg.value) is int
        )
        constant.value = cast(int, constant.value) + 1
    elif kind == "unrelated_function":
        other = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name != TARGETS[path]
        )
        other.body.insert(0, ast.Pass())
    elif kind == "unrelated_statement":
        tree.body.append(ast.Pass())
    elif kind == "extra_import":
        tree.body.insert(0, ast.Import(names=[ast.alias(name="unapproved_module", asname=None)]))
    elif kind == "duplicate_target":
        tree.body.append(copy.deepcopy(function))
    elif kind == "duplicate_call":
        function.body.append(ast.Expr(value=copy.deepcopy(call)))
    elif kind == "extra_function":
        tree.body.extend(ast.parse("def unapproved_function():\n    return None\n").body)
    elif kind == "extra_setup":
        call.keywords.append(ast.keyword(arg="unapproved_setup", value=ast.Constant(value=True)))
    elif kind in {"pause_false", "pause_one"}:
        keyword = next(item for item in call.keywords if item.arg == "pause_at_first_hit")
        keyword.value = ast.Constant(value=False if kind == "pause_false" else 1)
    elif kind in {"fixed_identity", "random_identity", "fixed_predicate", "cleave_identity"}:
        fixture_name = (
            "test_random_cleave_is_a_single_target_bonus_never_a_splittable_budget"
            if kind == "cleave_identity"
            else "_lethal_extra_session"
        )
        fixture = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == fixture_name
        )
        call_name = "random_melee_session" if kind == "cleave_identity" else "fight_lifecycle"
        fixture_call = next(
            node
            for node in ast.walk(fixture)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == call_name
        )
        identity = next(keyword for keyword in fixture_call.keywords if keyword.arg == "game_id")
        if kind == "cleave_identity":
            identity.value = ast.Constant(value="unapproved-cleave-identity")
        else:
            assert isinstance(identity.value, ast.IfExp)
            if kind == "fixed_identity":
                identity.value.orelse = ast.Constant(value="unapproved-fixed-identity")
            elif kind == "random_identity":
                identity.value.body = ast.Constant(value="unapproved-random-identity")
            else:
                identity.value.test = ast.Constant(value=False)
    elif kind == "leader_literal":
        keyword = next(item for item in call.keywords if item.arg == "enemy_unit_specs")
        assert isinstance(keyword.value, ast.IfExp)
        assert isinstance(keyword.value.body, ast.Dict)
        leader = keyword.value.body.values[1]
        assert isinstance(leader, ast.Tuple)
        leader.elts[0] = ast.Constant(value="core-character-leader")
    elif kind == "enemy_entry":
        keyword = next(item for item in call.keywords if item.arg == "enemy_unit_specs")
        assert isinstance(keyword.value, ast.IfExp)
        assert isinstance(keyword.value.body, ast.Dict)
        enemy = keyword.value.body.values[0]
        assert isinstance(enemy, ast.Tuple)
        enemy.elts[2] = ast.Constant(value=2)
    elif kind == "attached_predicate":
        keyword = next(item for item in call.keywords if item.arg == "enemy_unit_specs")
        assert isinstance(keyword.value, ast.IfExp)
        keyword.value.test = ast.Constant(value=True)
    elif kind == "catalog_wrapper":
        keyword = next(item for item in call.keywords if item.arg == "catalog")
        assert isinstance(keyword.value, ast.Call)
        assert isinstance(keyword.value.func, ast.Name)
        keyword.value.func.id = "unapproved_catalog_wrapper"
    elif kind in {"helper_import_alias", "duplicate_helper_import"}:
        import_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "tests.s25_original_fixture_controls"
        )
        if kind == "helper_import_alias":
            import_node.names[0].asname = "unapproved_alias"
        else:
            tree.body.append(copy.deepcopy(import_node))
    else:
        raise AssertionError("Every mutation has one explicit definition")
    return ast.unparse(ast.fix_missing_locations(tree)).encode("utf-8")


COMMON_MUTATIONS = (
    "remove_assertion",
    "weaken_assertion",
    "With",
    "branch",
    "iterator",
    "decorator",
    "ceiling",
    "unrelated_function",
    "unrelated_statement",
    "extra_import",
    "duplicate_target",
    "duplicate_call",
    "extra_function",
    "extra_setup",
)
AST_CONTROLS = (
    *[(path, kind) for path in PATHS for kind in COMMON_MUTATIONS],
    (RANDOM, "pause_false"),
    (RANDOM, "pause_one"),
    *[
        (RANDOM, kind)
        for kind in ("fixed_identity", "random_identity", "fixed_predicate", "cleave_identity")
    ],
    *[
        (RETAINED, kind)
        for kind in (
            "leader_literal",
            "enemy_entry",
            "attached_predicate",
            "catalog_wrapper",
            "helper_import_alias",
            "duplicate_helper_import",
        )
    ],
)


@pytest.mark.parametrize(("path", "kind"), AST_CONTROLS)
def test_actual_whole_module_ast_guard_rejects_obligation_drift_without_current_hash_gate(
    path: str, kind: str
) -> None:
    original, _current = _sources(path)
    with pytest.raises(AssertionError):
        preservation.assert_s25_fixture_only_ast(path, original, _mutated_current(path, kind))


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate_file",
        "extra_file",
        "path_alias",
        "base",
        "base_blob",
        "mode",
        "archive_alias",
        "extra_field",
        "duplicate_helper",
        "helper_pin",
        "raw_size_float",
        "qualifier_bool_int",
    ],
)
def test_actual_manifest_layout_guard_rejects_drift_independently_of_byte_pin(kind: str) -> None:
    payload = json.loads(
        (ROOT / preservation.ARCHIVE_DIRECTORY / "test-preservation.json").read_bytes()
    )
    if kind == "duplicate_file":
        payload["files"][1] = copy.deepcopy(payload["files"][0])
    elif kind == "extra_file":
        payload["files"].append(copy.deepcopy(payload["files"][0]))
    elif kind == "path_alias":
        payload["files"][0]["path"] = "tests/integration/./test_retained_shooting.py"
    elif kind == "base":
        payload["base"] = "0" * 40
    elif kind == "base_blob":
        payload["files"][0]["base_git_blob"] = "0" * 40
    elif kind == "mode":
        payload["files"][0]["base_mode"] = "120000"
    elif kind == "archive_alias":
        payload["files"][0]["baseline_archive"] = "data/source_audits/s25/../replacement.txt"
    elif kind == "extra_field":
        payload["files"][0]["unapproved"] = True
    elif kind == "duplicate_helper":
        payload["helpers"][1] = copy.deepcopy(payload["helpers"][0])
    elif kind == "raw_size_float":
        payload["files"][0]["base_raw_bytes"] = float(payload["files"][0]["base_raw_bytes"])
    elif kind == "qualifier_bool_int":
        payload["qualifications"]["archival_source_quality_only"] = 1
    else:
        assert kind == "helper_pin"
        payload["helpers"][0]["raw_sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        preservation.assert_s25_manifest_layout(payload)


@pytest.mark.parametrize(
    "tamper",
    ["current", "retained_helper", "random_helper", "archive", "manifest", "integration_archive"],
)
def test_actual_projection_rejects_complete_byte_tamper_before_returning_history(
    tamper: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        *PATHS,
        *preservation.HELPER_PINS,
        preservation.INTEGRATION_RANDOM_PREIMAGE,
        *(cast(str, row["baseline_archive"]) for row in preservation.FILE_PINS.values()),
        preservation.ARCHIVE_DIRECTORY + "/test-preservation.json",
    }
    for relative in files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    target_path = {
        "current": RANDOM,
        "integration_archive": preservation.INTEGRATION_RANDOM_PREIMAGE,
        "retained_helper": "tests/s25_original_fixture_controls.py",
        "random_helper": "tests/random_melee_helpers.py",
        "archive": cast(str, preservation.FILE_PINS[RANDOM]["baseline_archive"]),
        "manifest": preservation.ARCHIVE_DIRECTORY + "/test-preservation.json",
    }[tamper]
    target = tmp_path / target_path
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(preservation, "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        preservation.preserved_s25_predecessor_test_bytes(RANDOM, _sources(RANDOM)[1])


def test_existing_d10_complete_bytes_remain_after_only_declared_prefix_removal() -> None:
    current = (ROOT / "tests/d10_test_preservation_helpers.py").read_bytes()
    import_line = (
        b"from tests.s25_test_preservation_helpers import preserved_s25_predecessor_test_bytes\n\n"
    )
    prefix = b"    current = preserved_s25_predecessor_test_bytes(path, current)\n"
    assert current.count(import_line) == current.count(prefix) == 1
    original = current.replace(import_line, b"", 1).replace(prefix, b"", 1)
    assert hashlib.sha256(original).hexdigest() == (
        "696f39bb47156830d0d018639fe02cf6e3a0c683b6f85b45476e54703887a152"
    )
