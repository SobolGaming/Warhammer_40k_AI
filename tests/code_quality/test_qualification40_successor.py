"""New qualification may add exact obligations, never repin its prior stages."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from tools import cumulative_preservation as prior
from tools import performance_policy as policy
from tools import performance_preflight_successor as preflight
from tools import performance_qualification_successor as stage

ROOT = Path(__file__).resolve().parents[2]


class _QualificationMechanisms(Protocol):
    def _member(self, root: Path, name: str, freeze: str) -> bytes: ...

    def _read(self, root: Path, name: str) -> bytes: ...

    def member(self) -> Callable[[Path, str, str], bytes]:
        return self._member

    def read(self) -> Callable[[Path, str], bytes]:
        return self._read


# Capture real functions through a typed view before the test replaces them.
_stage = cast(_QualificationMechanisms, stage)


@pytest.fixture(scope="module")
def successor_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("qualification40")
    shutil.copytree(
        ROOT,
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "reports"
        ),
    )
    git_dir = (
        subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT)
        .decode()
        .strip()
    )
    (root / ".git").write_text("gitdir: " + git_dir + "\n")
    assert len(prior.verify_live(root)) == 64
    return root


def test_qualification_preserves_every_old_family_operation_and_assertion_stage() -> None:
    old = stage.accepted_operation_map(ROOT)
    current: dict[str, Any] = policy.read_object(ROOT / policy.MAP)
    family = current["families"]["external_contract_source_reuse"]
    assert family["input_binding"]["schema"] == "tool-input-roles-v3"
    family["input_binding"] = old["families"]["external_contract_source_reuse"]["input_binding"]
    assert {k: v for k, v in current.items() if k != "operations"} == {
        k: v for k, v in old.items() if k != "operations"
    }
    assert all(current["operations"][k] == value for k, value in old["operations"].items())
    assert all(
        current["operations"][k]["mandatory"] and current["operations"][k]["sensitive"]
        for k in old["operations"]
        if k.startswith("cumulative-exact-")
    )
    assert len(prior.verify_live(ROOT)) == 64
    assert prior.SOURCE_COMMIT == "036a1aa2b066fe37b0a9be37d4d9f45436a24e32"
    assert stage.ACCEPTED == "ee3ecc1de30a799811f6cbdf04a05d56e02f6ae5"


@pytest.mark.parametrize(
    "path",
    [
        "tests/support/section08_native_mission.py",
        "tests/support/section08_native_mission_source.py",
        "data/source_audits/section08_native_mission_2026_10_22/observation.json",
        "data/source_audits/qualification40_v1/accepted-source.json",
        "data/source_audits/qualification40_v1/control-transitions.json",
        "tools/performance_qualification_successor.py",
        "docs/performance/change-assessment.json",
    ],
)
def test_qualification_rejects_live_fixture_source_evidence_or_control_drift(
    successor_copy: Path, path: str
) -> None:
    file = successor_copy / path
    raw = file.read_bytes()
    try:
        file.write_bytes(raw + b"\nchanged\n")
        with pytest.raises((ValueError, json.JSONDecodeError)):
            prior.verify_live(successor_copy)
    finally:
        file.write_bytes(raw)


@pytest.mark.parametrize(
    "mutation",
    ["drop_old", "relax_sensitive", "relax_budget", "drop_new", "wildcard", "repin_additions"],
)
def test_qualification_map_mutation_cannot_inherit_historical_credit(
    successor_copy: Path, mutation: str
) -> None:
    file = successor_copy / policy.MAP
    raw = file.read_bytes()
    addition_path = successor_copy / stage.NAMESPACE / "added-operations.json"
    before = addition_path.read_bytes()
    value = json.loads(raw)
    old = stage.accepted_operation_map(ROOT)
    new_key = next(k for k in value["operations"] if k not in old["operations"])
    if mutation == "drop_old":
        value["operations"].pop(next(iter(old["operations"])))
    elif mutation == "relax_sensitive":
        value["operations"]["cumulative-exact-001"]["sensitive"] = False
    elif mutation == "relax_budget":
        value["families"]["reconstruction"]["samples_per_case"] = 1
    elif mutation == "drop_new":
        value["operations"].pop(new_key)
    else:
        value["operations"][new_key]["paths"] = ["src/*"]
    try:
        file.write_text(json.dumps(value))
        if mutation == "repin_additions":
            additions = json.loads(before)
            additions[new_key] = value["operations"][new_key]
            addition_path.write_text(json.dumps(additions))
        with pytest.raises(ValueError, match="Qualification"):
            stage.prior_operation_map_bytes(successor_copy)
    finally:
        file.write_bytes(raw)
        addition_path.write_bytes(before)


def test_qualification_producing_inputs_allows_only_anchor_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_ci60_qualification as ci60

    actual = policy.runtime_inputs(ROOT)
    historical = ci60.historical_inputs(ROOT)
    assert policy.canonical_digest(historical) == stage.PRODUCING_INPUT_DIGEST
    historical = ci60.historical_inputs(ROOT, original_controls=True)

    def historical_collector(root: Path) -> dict[str, str]:
        assert root == ROOT
        return dict(historical)

    def historical_projection(root: Path, inputs: dict[str, str]) -> dict[str, str]:
        assert root == ROOT
        return dict(inputs)

    with monkeypatch.context() as historical_context:
        historical_context.setattr(policy, "runtime_inputs", historical_collector)
        historical_context.setattr(preflight, "measurement_inputs", historical_projection)
        current = policy.runtime_inputs(ROOT)
        producing = stage.producing_inputs(ROOT, current)
        from tools.performance_preflight_successor import measurement_inputs

        current = measurement_inputs(ROOT, current)
        assert {k for k in current if current[k] != producing[k]} == {
            stage.SELF,
            policy.MAP,
            "tests/code_quality/test_qualification40_successor.py",
        }
        assert current.keys() == producing.keys()
        wrong = policy.runtime_inputs(ROOT)
        wrong.pop(stage.SELF)
        with pytest.raises(ValueError, match="collector omitted"):
            stage.producing_inputs(ROOT, wrong)

    with pytest.raises(ValueError, match="cannot change workload inputs"):
        stage.producing_inputs(ROOT, actual)
    producing = ci60.producing_inputs(ROOT, actual)
    assert producing.keys() == actual.keys()
    assert all(producing[name] == pin for name, pin in actual.items() if name != ci60.SELF)
    wrong = dict(actual)
    wrong["src/warhammer40k_core/engine/retained_demise_removal.py"] = "f" * 64
    with pytest.raises(ValueError, match="actual current collector"):
        ci60.producing_inputs(ROOT, wrong)

    proof = ci60.admitted(ROOT)
    producing_path = ci60.NAMESPACE + "/producing-inputs.json"
    forged = json.loads(proof[producing_path])
    forged[ci60.SELF] = "f" * 64
    proof[producing_path] = json.dumps(forged).encode()

    def forged_producing_control(root: Path) -> dict[str, bytes]:
        assert root == ROOT
        return proof

    with monkeypatch.context() as changed:
        changed.setattr(ci60, "admitted", forged_producing_control)
        with pytest.raises(ValueError, match="exact unactivated frozen source"):
            ci60.producing_inputs(ROOT, actual)

    ledger_name = "src/warhammer40k_core/engine/retained_demise_removal.py"
    proof = ci60.admitted(ROOT)
    owners = policy.owner_hashes(ledger_name, proof[ledger_name])
    ledger = ci60.historical_ledger_owners(ROOT, ledger_name, owners)
    assert ledger["@module"] == "482b60427ede07c2ef519a7633aa53e463c05dc353290f26e34cfe62594ced83"
    assert {k: v for k, v in ledger.items() if k != "@module"} == {
        k: v for k, v in owners.items() if k != "@module"
    }
    with pytest.raises(ValueError, match="current retained-demise owner source"):
        ci60.historical_ledger_owners(ROOT, ledger_name, owners | {"@module": "f" * 64})
    import_line = (
        b"    from warhammer40k_core.engine.retained_destruction_state "
        b"import RetainedModelDestruction\n"
    )
    for replacement, message in (
        (import_line * 2, "current retained-demise owner source"),
        (import_line.rstrip(b"\n") + b"  # altered\n", "sole reviewed type-only import"),
    ):
        changed_proof = proof | {
            ledger_name: proof[ledger_name]
            .replace(b"\r\n", b"\n")
            .replace(import_line, replacement, 1)
        }

        def changed_ledger_source(
            root: Path, value: dict[str, bytes] = changed_proof
        ) -> dict[str, bytes]:
            assert root == ROOT
            return value

        with monkeypatch.context() as changed:
            changed.setattr(ci60, "admitted", changed_ledger_source)
            with pytest.raises(ValueError, match=message):
                ci60.historical_ledger_owners(ROOT, ledger_name, owners)
    native_history = ci60.history

    def wrong_native_owner(root: Path, *args: str) -> bytes:
        if args == ("show", ci60.BASE + ":" + ledger_name):
            return proof[ledger_name]
        return native_history(root, *args)

    with monkeypatch.context() as changed:
        changed.setattr(ci60, "history", wrong_native_owner)
        with pytest.raises(ValueError, match="original retained-demise ledger owner"):
            ci60.historical_ledger_owners(ROOT, ledger_name, owners)
    assert ci60.historical_ledger_owners(ROOT, ledger_name, owners) == ledger

    test_proof = ci60.admitted(ROOT)
    for name, pin in ci60.HISTORICAL_TEST_PINS.items():
        current_test = test_proof[name]
        assert policy.digest(ci60.historical_test_preimage(ROOT, name, current_test)) == pin
        with pytest.raises(ValueError, match="unrelated current bytes"):
            ci60.historical_test_preimage(ROOT, name, current_test + b"\n")
    test_name = "tests/integration/test_fight_on_death_presence.py"
    original_test = ci60.historical_test_preimage(ROOT, test_name, test_proof[test_name])

    def wrong_test_native(root: Path, *args: str) -> bytes:
        if args == ("show", ci60.BASE + ":" + test_name):
            return original_test + b"\n"
        return native_history(root, *args)

    with monkeypatch.context() as changed:
        changed.setattr(ci60, "history", wrong_test_native)
        with pytest.raises(ValueError, match="native preimage changed"):
            ci60.historical_test_preimage(ROOT, test_name, test_proof[test_name])
    tree = ast.parse(original_test)
    assertion = next(node for node in ast.walk(tree) if isinstance(node, ast.Assert))
    assertion.test = ast.Constant(value=False)
    dropped = ast.unparse(tree).encode()
    changed_test_proof = test_proof | {test_name: dropped}

    def dropped_test_source(root: Path) -> dict[str, bytes]:
        assert root == ROOT
        return changed_test_proof

    with monkeypatch.context() as changed:
        changed.setattr(ci60, "admitted", dropped_test_source)
        with pytest.raises(ValueError, match="lost an original assertion"):
            ci60.historical_test_preimage(ROOT, test_name, dropped)
    assert ci60.historical_test_preimage(ROOT, test_name, test_proof[test_name]) == original_test


@pytest.mark.parametrize("mutation", ["owner", "path", "profile", "prior_operation"])
def test_qualification_map_identifier_requalification_rejects_semantic_drift(
    mutation: str,
) -> None:
    before = subprocess.check_output(
        ["git", "show", stage.PRODUCING_COMMIT + ":" + policy.MAP], cwd=ROOT
    )
    current = preflight.preceding_control(ROOT, policy.MAP, (ROOT / policy.MAP).read_bytes())
    stage.assert_symbolic_operation_map(before, current)
    value: dict[str, Any] = json.loads(current)
    key = next(k for k in value["operations"] if len(k) == len("qualification40-exact-") + 64)
    if mutation == "owner":
        value["operations"][key]["owners"].append("unreviewed_owner")
    elif mutation == "path":
        value["operations"][key]["paths"] = ["unreviewed/path.py"]
    elif mutation == "profile":
        value["families"]["reconstruction"]["samples_per_case"] = 1
    else:
        value["operations"].pop(next(iter(stage.accepted_operation_map(ROOT)["operations"])))
    raw = json.dumps(value).encode()
    with pytest.raises(ValueError, match="symbolic"):
        stage.assert_symbolic_operation_map(before, raw)


def test_qualification_map_current_collector_rejects_forged_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = (ROOT / policy.MAP).read_bytes() + b"\n"
    member, read = _QualificationMechanisms.member(_stage), _QualificationMechanisms.read(_stage)

    def repinned_member(root: Path, name: str, freeze: str) -> bytes:
        return raw if name == policy.MAP else member(root, name, freeze)

    def repinned_read(root: Path, name: str) -> bytes:
        return raw if name == policy.MAP else read(root, name)

    monkeypatch.setattr(stage, "_member", repinned_member)
    monkeypatch.setattr(stage, "_read", repinned_read)
    current = policy.runtime_inputs(ROOT) | {policy.MAP: policy.digest(raw)}
    with pytest.raises(ValueError, match="actual input collector omitted current control bytes"):
        stage.producing_inputs(ROOT, current)
