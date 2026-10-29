"""Sensitivity controls for the bounded D07 geometry verifier only."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path
from typing import NamedTuple, Protocol, cast

import pytest

from tests import d07_geometry_containment as geometry

ROOT = Path(__file__).resolve().parents[2]
RETRY_OWNER = "src/warhammer40k_core/engine/phases/movement_escape_mortals.py"
CASUALTY_OWNER = "src/warhammer40k_core/engine/desperate_escape_mortal_wounds.py"


class _SuccessorFreeze(Protocol):
    def _freeze(self, root: Path) -> str: ...

    def freeze(self, root: Path) -> str:
        return self._freeze(root)


@pytest.fixture(scope="module")
def preserved_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("d07-geometry")
    shutil.copytree(ROOT / "src", root / "src")
    recipe = cast(geometry.GeometryRecipe, json.loads((ROOT / geometry.RECIPE).read_bytes()))
    for name in (
        geometry.RECIPE,
        geometry.HISTORICAL_RECIPE,
        geometry.FNP_RECIPE,
        geometry.ARCHIVE,
        *recipe["source_evidence"],
    ):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / name).read_bytes())
    return root


class _FnpRecipeConstants(NamedTuple):
    HISTORICAL_RECIPE: str
    HISTORICAL_RECIPE_SHA256: str
    RECIPE: str
    RECIPE_SHA256: str


@pytest.fixture
def reviewed_fnp_stage(tmp_path: Path) -> tuple[Path, _FnpRecipeConstants]:
    """Original FNP assertion inputs, explicitly historical after live admission."""
    from tools import performance_ci60_qualification as ci60
    from tools.performance_preflight_successor import read_frozen_blobs

    ci60.admitted(ROOT)
    transition_name = "tests/data/reviewed_fnp_record_transition.json"
    transition_raw = geometry.read_owned_geometry_member(ROOT, transition_name)
    if hashlib.sha256(transition_raw).hexdigest() != (
        "a0a30709ad38cc2bf051877c1439b774325db745ae5871c4744c19db714071e9"
    ):
        raise ValueError("D07 historical FNP transition changed.")
    transition = json.loads(transition_raw)
    substitutions = transition["runtime_digest_substitutions"]
    names = [row["path"] for row in substitutions]
    historical = read_frozen_blobs(ROOT, "234deb628f3d6d7c49f3d344dfe6f066151017da", names)
    constants = _FnpRecipeConstants(
        geometry.HISTORICAL_RECIPE,
        geometry.HISTORICAL_RECIPE_SHA256,
        geometry.FNP_RECIPE,
        geometry.FNP_RECIPE_SHA256,
    )
    for row in substitutions:
        if hashlib.sha256(historical[row["path"]]).hexdigest() != row["candidate_sha"]:
            raise ValueError("D07 historical FNP native input changed.")
    for name, pin in (
        (constants.HISTORICAL_RECIPE, constants.HISTORICAL_RECIPE_SHA256),
        (constants.RECIPE, constants.RECIPE_SHA256),
    ):
        raw = geometry.read_owned_geometry_member(ROOT, name)
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError("D07 historical FNP authority changed.")
        historical[name] = raw
    historical[transition_name] = transition_raw
    for name, raw in historical.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return tmp_path, constants


def _changed_geometry(kind: str) -> bytes:
    tree = ast.parse((ROOT / geometry.LIVE).read_bytes())
    proposal = tree.body[19]
    assert isinstance(proposal, ast.FunctionDef)
    branch = proposal.body[21]
    assert isinstance(branch, ast.If)
    if kind == "fourth_retry_statement":
        branch.body.insert(16, ast.Pass())
    elif kind == "duplicate_retry_occurrence":
        branch.body.insert(
            16,
            ast.parse(
                "from warhammer40k_core.engine.phases.movement_escape_mortals "
                "import completed_escape_retry"
            ).body[0],
        )
    elif kind == "retry_condition":
        retry = branch.body[15]
        assert isinstance(retry, ast.If)
        retry.test = ast.Constant(value=True)
    elif kind == "other_geometry_branch":
        # A preexisting geometry rejection condition outside the three additions.
        other = branch.body[12]
        assert isinstance(other, ast.If)
        other.test = ast.Constant(value=False)
    elif kind == "other_function":
        other_function = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n is not proposal
        )
        other_function.body.append(ast.Pass())
    elif kind == "module_statement":
        tree.body.append(ast.parse("d07_unrelated_initializer = 1").body[0])
    elif kind == "delegation_attribution":
        continuation = tree.body[28]
        assert isinstance(continuation, ast.FunctionDef)
        failed = continuation.body[0]
        assert isinstance(failed, ast.If)
        returned = failed.body[1]
        assert isinstance(returned, ast.Return)
        assert isinstance(returned.value, ast.Call)
        keyword = next(k for k in returned.value.keywords if k.arg == "action_result")
        keyword.value = ast.Constant(value=None)
    elif kind == "decorator":
        proposal.decorator_list.append(ast.Name(id="unreviewed_decorator", ctx=ast.Load()))
    else:
        raise ValueError("Unknown D07 mutation: " + kind)
    return ast.unparse(ast.fix_missing_locations(tree)).encode()


def test_d07_geometry_exact_containment_positive(preserved_root: Path) -> None:
    geometry.verify_d07_geometry_containment(preserved_root)


@pytest.mark.parametrize(
    "kind",
    [
        "fourth_retry_statement",
        "duplicate_retry_occurrence",
        "retry_condition",
        "other_geometry_branch",
        "other_function",
        "module_statement",
        "delegation_attribution",
        "decorator",
    ],
)
def test_d07_bounded_ast_rejects_unlisted_changes_even_without_byte_pins(kind: str) -> None:
    old = (ROOT / geometry.ARCHIVE).read_bytes()
    with pytest.raises(ValueError, match="D07"):
        geometry.assert_bounded_geometry(old, _changed_geometry(kind))


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (geometry.LIVE, b"def _apply_movement_proposal_decision(", b"def changed_owner("),
        (
            RETRY_OWNER,
            b"proposal.actor_id != action.actor_id",
            b"proposal.actor_id == action.actor_id",
        ),
        (RETRY_OWNER, b"application.target_unit_instance_id", b"application.application_id"),
        (CASUALTY_OWNER, b"DestructionSourceKind.ABILITY", b"DestructionSourceKind.ATTACK"),
        (CASUALTY_OWNER, b"spill_over=True", b"spill_over=False"),
    ],
)
def test_d07_warm_live_drift_rejects_before_archive_access(
    preserved_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    before: bytes,
    after: bytes,
) -> None:
    geometry.verify_d07_geometry_containment(preserved_root)
    target = preserved_root / path
    raw = target.read_bytes()
    assert raw.count(before) >= 1
    target.write_bytes(raw.replace(before, after, 1))
    reads: list[str] = []
    original_read = geometry.read_owned_geometry_member

    def tracked_read(root: Path, name: str) -> bytes:
        reads.append(name)
        return original_read(root, name)

    monkeypatch.setattr(geometry, "read_owned_geometry_member", tracked_read)
    try:
        with pytest.raises(ValueError, match="D07 live runtime input changed"):
            geometry.verify_d07_geometry_containment(preserved_root)
        assert geometry.ARCHIVE not in reads
    finally:
        target.write_bytes(raw)


def test_d07_recomputed_current_pin_cannot_admit_fourth_statement(
    preserved_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_path = preserved_root / geometry.LIVE
    recipe_path = preserved_root / geometry.RECIPE
    live = live_path.read_bytes()
    frozen = recipe_path.read_bytes()
    changed = _changed_geometry("fourth_retry_statement")
    recipe = json.loads(frozen)
    recipe["source_files"][geometry.LIVE] = hashlib.sha256(changed).hexdigest()
    repinned = (json.dumps(recipe, indent=2) + "\n").encode()
    live_path.write_bytes(changed)
    recipe_path.write_bytes(repinned)
    monkeypatch.setattr(geometry, "RECIPE_SHA256", hashlib.sha256(repinned).hexdigest())
    try:
        with pytest.raises(ValueError, match="outside the exact"):
            geometry.verify_d07_geometry_containment(preserved_root)
    finally:
        live_path.write_bytes(live)
        recipe_path.write_bytes(frozen)


@pytest.mark.parametrize("change", ["extra", "missing", "recipe", "archive"])
def test_d07_membership_recipe_and_archive_are_bound(preserved_root: Path, change: str) -> None:
    target = (
        preserved_root
        / {
            "extra": "src/warhammer40k_core/d07_unreviewed.py",
            "missing": RETRY_OWNER,
            "recipe": geometry.RECIPE,
            "archive": geometry.ARCHIVE,
        }[change]
    )
    raw = target.read_bytes() if target.exists() else None
    if change == "missing":
        target.unlink()
    else:
        target.write_bytes((raw or b"") + b"\n# unreviewed\n")
    try:
        with pytest.raises(ValueError, match="D07"):
            geometry.verify_d07_geometry_containment(preserved_root)
    finally:
        if raw is None:
            target.unlink()
        else:
            target.write_bytes(raw)


def test_d07_reviewed_fnp_successor_is_exactly_five_digest_substitutions(
    reviewed_fnp_stage: tuple[Path, _FnpRecipeConstants],
) -> None:
    ROOT, geometry = reviewed_fnp_stage
    transition_raw = (ROOT / "tests/data/reviewed_fnp_record_transition.json").read_bytes()
    assert (
        hashlib.sha256(transition_raw).hexdigest()
        == "a0a30709ad38cc2bf051877c1439b774325db745ae5871c4744c19db714071e9"
    )
    transition = json.loads(transition_raw)
    historical = (ROOT / geometry.HISTORICAL_RECIPE).read_bytes()
    successor = (ROOT / geometry.RECIPE).read_bytes()
    assert hashlib.sha256(historical).hexdigest() == geometry.HISTORICAL_RECIPE_SHA256
    assert hashlib.sha256(successor).hexdigest() == geometry.RECIPE_SHA256
    expected = json.loads(historical)
    current = json.loads(successor)
    assert len(expected["source_files"]) == len(current["source_files"]) == 3104
    assert expected["source_files"].keys() == current["source_files"].keys()
    substitutions = transition["runtime_digest_substitutions"]
    assert len(substitutions) == 5
    assert {r["path"] for r in substitutions} == {
        "src/warhammer40k_core/_engine_build_manifest.json",
        "src/warhammer40k_core/engine/attack_sequence_destruction_authority.py",
        "src/warhammer40k_core/engine/model_destruction_cause_attack_restore.py",
        "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
        "src/warhammer40k_core/engine/retained_demise_removal.py",
    }
    for row in substitutions:
        assert expected["source_files"][row["path"]] == row["historical_sha"]
        expected["source_files"][row["path"]] = row["candidate_sha"]
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["candidate_sha"]
    expected["version"] = "d07-geometry-containment-v2-reviewed-fnp"
    assert current == expected


@pytest.mark.parametrize(
    "path",
    [
        "src/warhammer40k_core/_engine_build_manifest.json",
        "src/warhammer40k_core/engine/attack_sequence_destruction_authority.py",
        "src/warhammer40k_core/engine/model_destruction_cause_attack_restore.py",
        "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
        "src/warhammer40k_core/engine/retained_demise_removal.py",
        "src/warhammer40k_core/engine/psychic_ability_usage.py",
        "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/generated_manifest.py",
        "src/warhammer40k_core/engine/model_destruction_cause_authority.py",
        "src/warhammer40k_core/engine/model_destruction_cause_producers.py",
        "src/warhammer40k_core/engine/retained_destruction_history.py",
    ],
)
def test_d07_reviewed_successor_runtime_drift_refuses_before_archive(
    preserved_root: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    geometry.verify_d07_geometry_containment(preserved_root)
    target = preserved_root / path
    original = target.read_bytes()
    target.write_bytes(original + b"\n ")
    reads: list[str] = []
    read = geometry.read_owned_geometry_member

    def tracked(root: Path, name: str) -> bytes:
        reads.append(name)
        return read(root, name)

    monkeypatch.setattr(geometry, "read_owned_geometry_member", tracked)
    try:
        with pytest.raises(ValueError, match="D07 live runtime input changed"):
            geometry.verify_d07_geometry_containment(preserved_root)
        assert geometry.ARCHIVE not in reads
    finally:
        target.write_bytes(original)


def test_d07_arbitrary_live_repin_cannot_replace_reviewed_successor(
    preserved_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = preserved_root / RETRY_OWNER
    recipe_path = preserved_root / geometry.RECIPE
    original, frozen = path.read_bytes(), recipe_path.read_bytes()
    changed = original + b"\n# arbitrary repin\n"
    recipe = json.loads(frozen)
    recipe["source_files"][RETRY_OWNER] = hashlib.sha256(changed).hexdigest()
    path.write_bytes(changed)
    recipe_path.write_bytes((json.dumps(recipe, indent=2) + "\n").encode())
    reads: list[str] = []
    read = geometry.read_owned_geometry_member

    def tracked(root: Path, name: str) -> bytes:
        reads.append(name)
        return read(root, name)

    monkeypatch.setattr(geometry, "read_owned_geometry_member", tracked)
    try:
        with pytest.raises(ValueError, match="D07 containment recipe changed"):
            geometry.verify_d07_geometry_containment(preserved_root)
        assert geometry.ARCHIVE not in reads
    finally:
        path.write_bytes(original)
        recipe_path.write_bytes(frozen)


def test_d07_historical_recipe_remains_authenticated(preserved_root: Path) -> None:
    path = preserved_root / geometry.HISTORICAL_RECIPE
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    try:
        with pytest.raises(ValueError, match="D07 historical recipe changed"):
            geometry.verify_d07_geometry_containment(preserved_root)
    finally:
        path.write_bytes(original)


def test_order135_reviewed_fnp_metadata_transition_preserves_all_obligations() -> None:
    transition_raw = (ROOT / "tests/data/reviewed_fnp_record_transition.json").read_bytes()
    assert (
        hashlib.sha256(transition_raw).hexdigest()
        == "a0a30709ad38cc2bf051877c1439b774325db745ae5871c4744c19db714071e9"
    )
    transition = json.loads(transition_raw)
    historical = (ROOT / transition["order135_history"]).read_bytes()
    assert hashlib.sha256(historical).hexdigest() == transition["order135_history_sha256"]
    expected = json.loads(historical)
    changes = transition["order135_leaf_deltas"]
    assert len(changes) == 4
    # Exact metadata paths are pinned; no requirement/owner/assertion substitution.
    assert {row["path"] for row in changes} == {
        "/current_files_observed/tests/integration/test_fight_on_death_presence.py/sha256",
        "/current_files_observed/tests/integration/test_fight_on_death_presence.py/bytes",
        "/tests/tests/integration/test_fight_on_death_presence.py::test_order_30_retained_model_fights_from_original_base_then_is_removed/file_sha256",
        "/tests/tests/integration/test_fight_on_death_presence.py::test_order_30_other_destruction_triggers_wait_for_retained_model_completion/file_sha256",
    }
    # Keys contain slashes, so use their complete authenticated map keys.
    filename = "tests/integration/test_fight_on_death_presence.py"
    for row in changes:
        if row["path"].startswith("/current_files_observed/"):
            parent = expected["current_files_observed"][filename]
        else:
            node = row["path"][len("/tests/") : -len("/file_sha256")]
            parent = expected["tests"][node]
        key = row["path"].rsplit("/", 1)[1]
        assert parent[key] == row["old"]
        parent[key] = row["new"]
    actual = (ROOT / transition["order135_output"]).read_bytes()
    # Authenticate the complete current tooling successor before comparing this
    # historical FNP transition with its exact accepted predecessor bytes.
    from tools import performance_preflight_successor as successor

    successor_probe = cast(_SuccessorFreeze, successor)
    _SuccessorFreeze.freeze(successor_probe, ROOT)
    actual = successor.preceding_control(ROOT, transition["order135_output"], actual)
    assert hashlib.sha256(actual).hexdigest() == transition["order135_output_sha256"]
    assert json.loads(actual) == expected


def test_d07_current_catalog_matches_exact_accepted_runtime_successors() -> None:
    from tools.performance_preflight_successor import read_frozen_blobs

    geometry.verify_d07_geometry_containment(ROOT)
    names = list(geometry.CURRENT_SOURCE_SUBSTITUTIONS)
    assert len(names) == 7
    before = read_frozen_blobs(ROOT, geometry.CURRENT_RUNTIME_BASE, names)
    after = read_frozen_blobs(ROOT, geometry.CURRENT_RUNTIME_COMMIT, names)
    expected = json.loads((ROOT / geometry.FNP_RECIPE).read_bytes())
    for name, (old_pin, new_pin) in geometry.CURRENT_SOURCE_SUBSTITUTIONS.items():
        assert hashlib.sha256(before[name]).hexdigest() == old_pin
        assert hashlib.sha256(after[name]).hexdigest() == new_pin
        assert (ROOT / name).read_bytes() == after[name]
        assert expected["source_files"][name] == old_pin
        expected["source_files"][name] = new_pin
    expected["version"] = "d07-geometry-containment-v3-reviewed-ci57-c5"
    current = json.loads((ROOT / geometry.RECIPE).read_bytes())
    assert current == expected
    assert len(current["source_files"]) == 3104


def test_d07_reviewed_fnp_authority_still_rejects_mutation_before_archive(
    preserved_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    geometry.verify_d07_geometry_containment(preserved_root)
    path = preserved_root / geometry.FNP_RECIPE
    original = path.read_bytes()
    reads: list[str] = []
    read = geometry.read_owned_geometry_member

    def tracked(root: Path, name: str) -> bytes:
        reads.append(name)
        return read(root, name)

    monkeypatch.setattr(geometry, "read_owned_geometry_member", tracked)
    path.write_bytes(original + b" ")
    try:
        with pytest.raises(ValueError, match="D07 reviewed FNP recipe changed"):
            geometry.verify_d07_geometry_containment(preserved_root)
        assert geometry.ARCHIVE not in reads
    finally:
        path.write_bytes(original)
