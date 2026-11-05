"""Exact bounded Starfang/Deep Strike source-only smoke admission controls."""

from __future__ import annotations

import copy
import fnmatch
import subprocess
from pathlib import Path
from typing import cast

import pytest
from tools import performance_policy as policy
from tools.performance_policy import object_value, read_object

ROOT = Path(__file__).resolve().parents[2]
BASE = "79a27e4a26e180a28457712818d47e274df7c99a"
SCOPE = ROOT / "docs/performance/policy-v3/starfang-deep-strike-smoke-scope.json"


def test_starfang_source_smoke_binding_and_predecessor_are_exact() -> None:
    scope = read_object(SCOPE)
    bindings = object_value(scope["changes"])
    operations = object_value(scope["smoke_operations"])
    for path, change in bindings.items():
        expected = cast(list[str], operations[path])
        assert policy.starfang_deep_strike_smoke_operations(
            base=BASE, path=path, category="rule_semantics", change=change
        ) == frozenset(expected)
        for base, selected_path, category in (
            ("a" * 40, path, "rule_semantics"),
            (BASE, "tools/unreviewed.py", "rule_semantics"),
            (BASE, path, "algorithm_or_search"),
            (BASE, path, "cache_policy"),
            (BASE, path, "serialization_or_replay_work"),
        ):
            assert not policy.starfang_deep_strike_smoke_operations(
                base=base, path=selected_path, category=category, change=change
            )
        for part in ("file", "owner"):
            changed = copy.deepcopy(object_value(change))
            if part == "file":
                changed["after_sha256"] = "0" * 64
            else:
                object_value(next(iter(object_value(changed["owners"]).values())))["after"] = (
                    "0" * 64
                )
            assert not policy.starfang_deep_strike_smoke_operations(
                base=BASE, path=path, category="rule_semantics", change=changed
            )
    raw = (ROOT / "tools/performance_policy.py").read_bytes()
    prior = subprocess.check_output(
        ["git", "show", BASE + ":tools/performance_policy.py"], cwd=ROOT
    )
    assert policy.starfang_deep_strike_policy_predecessor(raw) == prior
    assert policy.starfang_deep_strike_policy_predecessor(prior) == prior
    for altered in (b"", raw + b"\n", raw.replace(b"category !=", b"category ==", 1)):
        with pytest.raises(ValueError, match="Starfang/Deep Strike"):
            policy.starfang_deep_strike_policy_predecessor(altered)
    mapping = read_object(ROOT / "docs/performance/policy-v3/operation-map.json")
    old_mapping = read_object_from_git("docs/performance/policy-v3/operation-map.json")
    old_operations = object_value(old_mapping["operations"])
    # Retiring tracked prose must not leave dead selectors in the live map.
    # All operations, runtime/test selectors and policy settings remain exact.
    retired_docs = {
        path
        for path in subprocess.check_output(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=D",
                BASE,
                "HEAD",
                "--",
                "docs/",
                "contracts/",
            ],
            cwd=ROOT,
            text=True,
        ).splitlines()
        if path.endswith(".md") and not (ROOT / path).exists()
    }
    for name, operation in old_operations.items():
        expected_operation = object_value(operation).copy()
        expected_operation["paths"] = [
            path
            for path in cast(list[str], expected_operation["paths"])
            if path not in retired_docs
        ]
        assert object_value(mapping["operations"])[name] == expected_operation


def read_object_from_git(path: str) -> dict[str, object]:
    import json

    return cast(
        dict[str, object],
        json.loads(subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT)),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-owner",
        "extra-owner",
        "file-hash",
        "owner-hash",
        "existing-owner-null",
        "operation",
        "extra-binding",
        "extra-field",
        "proof-after",
        "proof-before",
        "proof-block",
        "proof-call",
        "proof-predecessor",
        "proof-field",
    ],
)
def test_starfang_source_smoke_rejects_unbounded_declarations(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    scope = read_object(SCOPE)
    path = "tools/generate_ability_support_matrix.py"
    change = object_value(scope["changes"])[path]
    altered = copy.deepcopy(scope)
    bindings = object_value(altered["changes"])
    binding = object_value(bindings[path])
    owners = object_value(binding["owners"])
    proof = object_value(altered["policy_successor"])
    if mutation == "missing-owner":
        owners.pop("_ability_support_catalog_package")
    elif mutation == "extra-owner":
        owners["unreviewed"] = {"before": "1" * 64, "after": "2" * 64}
    elif mutation == "file-hash":
        binding["after_sha256"] = "not-a-hash"
    elif mutation == "owner-hash":
        object_value(owners["_ability_support_catalog_package"])["after"] = "not-a-hash"
    elif mutation == "existing-owner-null":
        object_value(owners["_ability_support_catalog_package"])["before"] = None
    elif mutation == "operation":
        object_value(altered["smoke_operations"])[path] = ["cache-policy"]
    elif mutation == "extra-binding":
        bindings["unreviewed.py"] = copy.deepcopy(binding)
    elif mutation.startswith("proof-"):
        proof[
            {
                "proof-after": "after_sha256",
                "proof-before": "before_sha256",
                "proof-block": "function_block_sha256",
                "proof-call": "union_call_sha256",
                "proof-predecessor": "predecessor_call_sha256",
                "proof-field": "unreviewed",
            }[mutation]
        ] = "0" * 64
    else:
        altered["unreviewed"] = True

    def altered_scope(_selected: Path) -> dict[str, object]:
        return altered

    monkeypatch.setattr(policy, "read_object", altered_scope)
    with pytest.raises(ValueError, match=r"Starfang/Deep Strike|Unexpected"):
        policy.starfang_deep_strike_smoke_operations(
            base=BASE, path=path, category="rule_semantics", change=change
        )


def test_starfang_assessment_requires_mandatory_operations_and_detailed_categories() -> None:
    scope = read_object(SCOPE)
    changes = object_value(scope["changes"])
    mapping = read_object(ROOT / policy.MAP)
    operations: dict[str, list[str]] = {
        path: [
            name
            for name, raw in object_value(mapping["operations"]).items()
            if any(
                fnmatch.fnmatchcase(path, pattern)
                for pattern in cast(list[str], object_value(raw)["paths"])
            )
            and any(
                fnmatch.fnmatchcase(owner, pattern)
                for owner in object_value(object_value(change)["owners"])
                for pattern in cast(list[str], object_value(raw)["owners"])
            )
        ]
        for path, change in changes.items()
    }
    build = "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "1" * 64
    rows: dict[str, object] = {
        path: {
            "category": "rule_semantics",
            "operations": selected,
            "selected_families": [],
            "rationale": scope["source_obligation"],
            "source_obligation": scope["source_obligation"],
            "unchanged_work": scope["unchanged_work"],
        }
        for path, selected in operations.items()
    }
    assessment: dict[str, object] = {
        "policy": policy.POLICY,
        "base": BASE,
        "runtime_build_id": build,
        "operation_map_sha256": policy.canonical_digest(mapping),
        "changes": changes,
        "rows": rows,
        "milestone": "ordinary",
        "comparisons": {},
        "full_game": None,
    }
    assert (
        policy.validate_assessment(
            assessment, base=BASE, changes=changes, runtime_id=build, operation_map=mapping
        )
        == set()
    )
    for path, selected in operations.items():
        for omitted in selected:
            altered = copy.deepcopy(assessment)
            object_value(object_value(altered["rows"])[path])["operations"] = [
                name for name in selected if name != omitted
            ]
            with pytest.raises(ValueError, match="operation"):
                policy.validate_assessment(
                    altered,
                    base=BASE,
                    changes=changes,
                    runtime_id=build,
                    operation_map=mapping,
                )
        for category in ("algorithm_or_search", "cache_policy", "serialization_or_replay_work"):
            altered = copy.deepcopy(assessment)
            object_value(object_value(altered["rows"])[path])["category"] = category
            with pytest.raises(ValueError, match="detailed"):
                policy.validate_assessment(
                    altered,
                    base=BASE,
                    changes=changes,
                    runtime_id=build,
                    operation_map=mapping,
                )


def test_starfang_overlay_projects_only_exact_historical_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import json

    from tools import source_scope_provenance as provenance

    from tests.support.acts_preservation import defiler_provenance_predecessor
    from tests.support.source_provenance import (
        historical_snapshot_inputs,
        retired_identity_tokens,
    )

    path = ROOT / provenance.STARFANG_OVERLAY
    raw = path.read_bytes()
    projected = provenance.registered_provenance_text(ROOT, path, raw, historical_snapshot_inputs)
    assert projected is not None
    expected = json.loads(raw)
    del expected["base_source_package_id"]["version"]
    assert json.loads(projected) == expected
    assert not any(token in projected for token in retired_identity_tokens())
    assert path.read_bytes() == raw
    assert (
        provenance.registered_provenance_text(
            ROOT, ROOT / "unregistered-starfang-overlay.json", raw, historical_snapshot_inputs
        )
        is None
    )
    with pytest.raises(ValueError, match="exact reviewed bytes"):
        provenance.registered_provenance_text(ROOT, path, raw + b"\n", historical_snapshot_inputs)
    for mutation in ("base_source_package_id", "target_edition", "schema_version"):
        changed = json.loads(raw)
        changed[mutation] = retired_identity_tokens()[0]
        changed_raw = json.dumps(changed).encode()
        with pytest.raises(ValueError, match="exact reviewed bytes"):
            provenance.registered_provenance_text(
                ROOT, path, changed_raw, historical_snapshot_inputs
            )
        # Review of new bytes cannot bypass the unchanged semantic identity checks.
        with monkeypatch.context() as scoped:
            scoped.setattr(
                provenance, "STARFANG_OVERLAY_SHA256", hashlib.sha256(changed_raw).hexdigest()
            )
            with pytest.raises(ValueError, match="historical base identity changed"):
                provenance.registered_provenance_text(
                    ROOT, path, changed_raw, historical_snapshot_inputs
                )
    linked = tmp_path / provenance.STARFANG_OVERLAY
    linked.parent.mkdir(parents=True)
    linked.symlink_to(path)
    with pytest.raises(ValueError, match="exact reviewed bytes"):
        provenance.registered_provenance_text(tmp_path, linked, raw, historical_snapshot_inputs)
    operative = json.loads(raw)
    operative["operations"][0]["reason"] = retired_identity_tokens()[0]
    operative_raw = json.dumps(operative).encode()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            provenance, "STARFANG_OVERLAY_SHA256", hashlib.sha256(operative_raw).hexdigest()
        )
        text = provenance.registered_provenance_text(
            ROOT, path, operative_raw, historical_snapshot_inputs
        )
        assert text is not None
        assert retired_identity_tokens()[0] in text
    helper = (ROOT / "tools/source_scope_provenance.py").read_bytes()
    assert hashlib.sha256(defiler_provenance_predecessor(helper)).hexdigest() == (
        "40ef539dc75aa669df54a099d7788b74ca68453c7ae18a1e009194c48a42f64a"
    )
    binding = b"        root / STARFANG_OVERLAY: STARFANG_OVERLAY_SHA256,\n"
    for changed_helper in (
        helper.replace(b"STARFANG_OVERLAY_SHA256", b"ALTERED_STARFANG_OVERLAY_SHA256"),
        helper.replace(binding, b""),
        helper.replace(binding, binding + binding),
    ):
        with pytest.raises(ValueError, match="registered edition provenance inputs changed"):
            defiler_provenance_predecessor(changed_helper)


def test_starfang_provenance_predecessor_preserves_exact_bytes_and_rejects_drift() -> None:
    from tests.support.acts_preservation import starfang_provenance_predecessor

    current = (ROOT / "tools/source_scope_provenance.py").read_bytes()
    prior = subprocess.check_output(
        ["git", "show", BASE + ":tools/source_scope_provenance.py"], cwd=ROOT
    )
    assert starfang_provenance_predecessor(current) == prior
    assert starfang_provenance_predecessor(prior) == prior
    binding = b"        root / STARFANG_OVERLAY: STARFANG_OVERLAY_SHA256,\n"
    for altered in (
        b"",
        current + b"\n",
        current.replace(b"starfang_keyword_2026_11", b"unreviewed_source"),
        current.replace(b"477ce675ddebbf0f", b"0000000000000000"),
        current.replace(binding, b""),
        current.replace(binding, binding + binding),
        current.replace(b"return contexts.get(relative)", b"return None"),
    ):
        with pytest.raises(ValueError, match="Exact registered edition provenance inputs changed"):
            starfang_provenance_predecessor(altered)
        assert starfang_provenance_predecessor(current) == prior


def test_starfang_helper_move_is_exact_and_only_three_owners_are_deleted() -> None:
    import hashlib

    scope = read_object(SCOPE)
    path = "tests/code_quality/test_registered_source_scopes.py"
    binding = object_value(object_value(scope["changes"])[path])
    owners = object_value(binding["owners"])
    deleted = {"_historical_report", "historical_snapshot_inputs", "retired_identity_tokens"}
    assert set(owners) == deleted | {
        "@module",
        "test_old_scope_binding_is_retained_but_cannot_qualify_new_scope",
        "test_banshee_eldrad_provenance_successor_preserves_exact_base_and_original_chain",
    }
    assert {name for name, row in owners.items() if object_value(row)["after"] is None} == deleted
    proof = object_value(scope["helper_move_proof"])
    assert proof["source_path"] == path
    assert proof["source_change"] == binding
    assert proof["helper_path"] == "tests/support/source_provenance.py"
    assert (
        proof["helper_sha256"]
        == hashlib.sha256((ROOT / "tests/support/source_provenance.py").read_bytes()).hexdigest()
    )
    assert proof["renames"] == {"_historical_report": "historical_source_report"}
    assert set(object_value(proof["normalized_owner_sha256"])) == deleted


@pytest.mark.parametrize("mutation", ["before", "non-null-after", "unlisted-deletion"])
def test_starfang_helper_move_rejects_changed_actual_owner_binding(mutation: str) -> None:
    scope = read_object(SCOPE)
    path = "tests/code_quality/test_registered_source_scopes.py"
    changed = copy.deepcopy(object_value(object_value(scope["changes"])[path]))
    owners = object_value(changed["owners"])
    if mutation == "before":
        object_value(owners["_historical_report"])["before"] = "0" * 64
    elif mutation == "non-null-after":
        object_value(owners["_historical_report"])["after"] = "0" * 64
    else:
        object_value(owners["@module"])["after"] = None
    assert not policy.starfang_deep_strike_smoke_operations(
        base=BASE, path=path, category="rule_semantics", change=changed
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "deleted-before",
        "deleted-after",
        "unlisted-deletion",
        "original-path-deletion",
        "helper-path",
        "helper-sha",
        "source-path",
        "source-change",
        "rename",
        "owner-proof",
    ],
)
def test_starfang_helper_move_rejects_unbounded_declaration_or_proof(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    scope = read_object(SCOPE)
    path = "tests/code_quality/test_registered_source_scopes.py"
    change = object_value(scope["changes"])[path]
    altered = copy.deepcopy(scope)
    owners = object_value(object_value(object_value(altered["changes"])[path])["owners"])
    proof = object_value(altered["helper_move_proof"])
    if mutation == "deleted-before":
        object_value(owners["_historical_report"])["before"] = "0" * 64
    elif mutation == "deleted-after":
        object_value(owners["_historical_report"])["after"] = "0" * 64
    elif mutation == "unlisted-deletion":
        object_value(owners["@module"])["after"] = None
    elif mutation == "original-path-deletion":
        source = object_value(object_value(altered["changes"])["tools/ability_support_sources.py"])
        object_value(object_value(source["owners"])["@module"])["after"] = None
    elif mutation == "helper-path":
        proof["helper_path"] = "tests/support/unreviewed.py"
    elif mutation == "helper-sha":
        proof["helper_sha256"] = "0" * 64
    elif mutation == "source-path":
        proof["source_path"] = "tests/code_quality/test_unreviewed.py"
    elif mutation == "source-change":
        object_value(proof["source_change"])["after_sha256"] = "0" * 64
    elif mutation == "rename":
        object_value(proof["renames"])["retired_identity_tokens"] = "unreviewed"
    else:
        object_value(proof["normalized_owner_sha256"])["historical_snapshot_inputs"] = "0" * 64

    def altered_scope(_selected: Path) -> dict[str, object]:
        return altered

    monkeypatch.setattr(policy, "read_object", altered_scope)
    with pytest.raises(ValueError, match=r"Starfang/Deep Strike|Unexpected"):
        policy.starfang_deep_strike_smoke_operations(
            base=BASE, path=path, category="rule_semantics", change=change
        )


def test_starfang_helper_move_rejects_changed_helper_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    scope = read_object(SCOPE)
    path = "tests/code_quality/test_registered_source_scopes.py"
    helper = ROOT / "tests/support/source_provenance.py"
    original_read_bytes = Path.read_bytes

    def changed_helper_bytes(selected: Path) -> bytes:
        raw = original_read_bytes(selected)
        return raw + b"\n" if selected == helper else raw

    monkeypatch.setattr(Path, "read_bytes", changed_helper_bytes)
    with pytest.raises(ValueError, match="Starfang/Deep Strike"):
        policy.starfang_deep_strike_smoke_operations(
            base=BASE,
            path=path,
            category="rule_semantics",
            change=object_value(scope["changes"])[path],
        )


def test_wave_frame_performance_scope_is_exact_and_preserves_policy_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.performance_daemons_native import daemons_native_policy_predecessor
    from tools.performance_wave_frame import BASE as FRAME_BASE
    from tools.performance_wave_frame import (
        OPERATIONS,
        wave_frame_policy_predecessor,
        wave_frame_smoke_operations,
    )
    from tools.performance_wave_frame import SCOPE as FRAME_SCOPE

    # Authenticate this historical policy view before testing its unchanged pins.
    policy_path = ROOT / "tools/performance_policy.py"
    original_read_bytes = Path.read_bytes
    from tools.performance_daemons_final import daemons_final_policy_predecessor
    from tools.performance_daemons_next import daemons_next_policy_predecessor

    predecessor = daemons_native_policy_predecessor(
        daemons_next_policy_predecessor(
            daemons_final_policy_predecessor(original_read_bytes(policy_path))
        )
    )

    def historical_policy_bytes(path: Path) -> bytes:
        return predecessor if path == policy_path else original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", historical_policy_bytes)
    scope = read_object(ROOT / FRAME_SCOPE)
    for path, change in object_value(scope["changes"]).items():
        assert wave_frame_smoke_operations(
            base=FRAME_BASE, path=path, category="rule_semantics", change=change
        ) == frozenset({OPERATIONS[path]})
        for base, selected, category in (
            ("0" * 40, path, "rule_semantics"),
            (FRAME_BASE, "tools/unreviewed.py", "rule_semantics"),
            (FRAME_BASE, path, "algorithm_or_search"),
            (FRAME_BASE, path, "cache_policy"),
            (FRAME_BASE, path, "serialization_or_replay_work"),
        ):
            assert not wave_frame_smoke_operations(
                base=base, path=selected, category=category, change=change
            )
        drift = copy.deepcopy(object_value(change))
        drift["after_sha256"] = "0" * 64
        assert not wave_frame_smoke_operations(
            base=FRAME_BASE, path=path, category="rule_semantics", change=drift
        )
        drift = copy.deepcopy(object_value(change))
        object_value(next(iter(object_value(drift["owners"]).values())))["after"] = "0" * 64
        assert not wave_frame_smoke_operations(
            base=FRAME_BASE, path=path, category="rule_semantics", change=drift
        )
    current = (ROOT / "tools/performance_policy.py").read_bytes()
    before = subprocess.check_output(
        ["git", "show", FRAME_BASE + ":tools/performance_policy.py"], cwd=ROOT
    )
    assert wave_frame_policy_predecessor(current) == before
    assert wave_frame_policy_predecessor(before) == before
    for policy_drift in (
        current + b"\n",
        current.replace(b"wave_frame_smoke_operations", b"other_operation"),
    ):
        with pytest.raises(ValueError, match="Wave FRAME"):
            wave_frame_policy_predecessor(policy_drift)
    assert policy.starfang_deep_strike_policy_predecessor(current) == subprocess.check_output(
        ["git", "show", BASE + ":tools/performance_policy.py"], cwd=ROOT
    )


def test_wave_frame_source_provenance_admission_is_exact() -> None:
    from tools import source_scope_provenance as provenance

    from tests.support.source_provenance import historical_snapshot_inputs
    from tests.wave_serpent_frame_helpers import before_wave_provenance

    path = ROOT / provenance.WAVE_FRAME_OVERLAY
    raw = path.read_bytes()
    projected = provenance.registered_provenance_text(ROOT, path, raw, historical_snapshot_inputs)
    assert projected is not None
    import json

    expected = json.loads(raw)
    del expected["base_source_package_id"]["version"]
    assert json.loads(projected) == expected
    with pytest.raises(ValueError, match="exact reviewed bytes"):
        provenance.registered_provenance_text(ROOT, path, raw + b" ", historical_snapshot_inputs)
    helper = (ROOT / "tools/source_scope_provenance.py").read_bytes()
    prior = subprocess.check_output(
        [
            "git",
            "show",
            "6ca0ee47d44b227d805b15b5c1de8ca321003da8:tools/source_scope_provenance.py",
        ],
        cwd=ROOT,
    )
    assert before_wave_provenance(helper) == prior
    for drift in (
        helper + b"\n",
        helper.replace(b"WAVE_FRAME_OVERLAY_SHA256", b"UNREVIEWED_OVERLAY_SHA256"),
    ):
        with pytest.raises(ValueError, match="registered edition provenance inputs changed"):
            before_wave_provenance(drift)


def test_daemons_native_performance_scope_is_exact_and_preserves_policy_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.performance_daemons_final import daemons_final_policy_predecessor
    from tools.performance_daemons_native import BASE as DAEMONS_BASE
    from tools.performance_daemons_native import (
        OPERATIONS,
        daemons_native_policy_predecessor,
        daemons_native_smoke_operations,
    )
    from tools.performance_daemons_native import SCOPE as DAEMONS_SCOPE
    from tools.performance_daemons_next import daemons_next_policy_predecessor

    policy_path = ROOT / "tools/performance_policy.py"
    original_read_bytes = Path.read_bytes
    predecessor = daemons_next_policy_predecessor(
        daemons_final_policy_predecessor(original_read_bytes(policy_path))
    )

    def historical_policy_bytes(path: Path) -> bytes:
        return predecessor if path == policy_path else original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", historical_policy_bytes)

    scope = read_object(ROOT / DAEMONS_SCOPE)
    for path, change in object_value(scope["changes"]).items():
        assert daemons_native_smoke_operations(
            base=DAEMONS_BASE, path=path, category="rule_semantics", change=change
        ) == frozenset({OPERATIONS[path]})
        for base, selected, category in (
            ("0" * 40, path, "rule_semantics"),
            (DAEMONS_BASE, "tools/unreviewed.py", "rule_semantics"),
            (DAEMONS_BASE, path, "algorithm_or_search"),
            (DAEMONS_BASE, path, "cache_policy"),
            (DAEMONS_BASE, path, "serialization_or_replay_work"),
        ):
            assert not daemons_native_smoke_operations(
                base=base, path=selected, category=category, change=change
            )
        drift = copy.deepcopy(object_value(change))
        drift["after_sha256"] = "0" * 64
        assert not daemons_native_smoke_operations(
            base=DAEMONS_BASE, path=path, category="rule_semantics", change=drift
        )
        drift = copy.deepcopy(object_value(change))
        object_value(next(iter(object_value(drift["owners"]).values())))["after"] = "0" * 64
        assert not daemons_native_smoke_operations(
            base=DAEMONS_BASE, path=path, category="rule_semantics", change=drift
        )
    current = (ROOT / "tools/performance_policy.py").read_bytes()
    before = subprocess.check_output(
        ["git", "show", DAEMONS_BASE + ":tools/performance_policy.py"], cwd=ROOT
    )
    assert daemons_native_policy_predecessor(current) == before
    assert daemons_native_policy_predecessor(before) == before
    for policy_drift in (
        current + b"\n",
        current.replace(b"daemons_native_smoke_operations", b"other_operation"),
    ):
        with pytest.raises(ValueError, match="Daemons native"):
            daemons_native_policy_predecessor(policy_drift)
    assert policy.starfang_deep_strike_policy_predecessor(current) == subprocess.check_output(
        ["git", "show", BASE + ":tools/performance_policy.py"], cwd=ROOT
    )


def test_daemons_next_three_performance_scope_is_exact_and_preserves_policy_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.performance_daemons_final import daemons_final_policy_predecessor
    from tools.performance_daemons_next import BASE as NEXT_BASE
    from tools.performance_daemons_next import (
        OPERATIONS,
        daemons_next_policy_predecessor,
        daemons_next_smoke_operations,
    )
    from tools.performance_daemons_next import SCOPE as NEXT_SCOPE

    policy_path = ROOT / "tools/performance_policy.py"
    original_read_bytes = Path.read_bytes
    predecessor = daemons_final_policy_predecessor(original_read_bytes(policy_path))

    def historical_policy_bytes(path: Path) -> bytes:
        return predecessor if path == policy_path else original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", historical_policy_bytes)

    scope = read_object(ROOT / NEXT_SCOPE)
    for path, change in object_value(scope["changes"]).items():
        assert daemons_next_smoke_operations(
            base=NEXT_BASE, path=path, category="rule_semantics", change=change
        ) == frozenset({OPERATIONS[path]})
        for base, selected, category in (
            ("0" * 40, path, "rule_semantics"),
            (NEXT_BASE, "tools/unreviewed.py", "rule_semantics"),
            (NEXT_BASE, path, "algorithm_or_search"),
            (NEXT_BASE, path, "cache_policy"),
            (NEXT_BASE, path, "serialization_or_replay_work"),
        ):
            assert not daemons_next_smoke_operations(
                base=base, path=selected, category=category, change=change
            )
        drift = copy.deepcopy(object_value(change))
        drift["after_sha256"] = "0" * 64
        assert not daemons_next_smoke_operations(
            base=NEXT_BASE, path=path, category="rule_semantics", change=drift
        )
        drift = copy.deepcopy(object_value(change))
        object_value(next(iter(object_value(drift["owners"]).values())))["after"] = "0" * 64
        assert not daemons_next_smoke_operations(
            base=NEXT_BASE, path=path, category="rule_semantics", change=drift
        )
    current = (ROOT / "tools/performance_policy.py").read_bytes()
    before = subprocess.check_output(
        ["git", "show", NEXT_BASE + ":tools/performance_policy.py"], cwd=ROOT
    )
    assert daemons_next_policy_predecessor(current) == before
    assert daemons_next_policy_predecessor(before) == before
    for policy_drift in (
        current + b"\n",
        current.replace(b"daemons_next_smoke_operations", b"other_operation"),
    ):
        with pytest.raises(ValueError, match="Daemons next-three"):
            daemons_next_policy_predecessor(policy_drift)
    assert policy.starfang_deep_strike_policy_predecessor(current) == subprocess.check_output(
        ["git", "show", BASE + ":tools/performance_policy.py"], cwd=ROOT
    )


def test_daemons_next_three_retained_capture_bytes_match_receipts() -> None:
    import hashlib
    import json

    directory = ROOT / "data/source_audits/daemons_next_three_2026_11"
    raw = (directory / "source-capture-receipts.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "cc67ebf416a0bf463c812c51a6c83d3784fa68e2bcfdbb874e9cd34b66d7478c"
    )
    receipts = json.loads(raw)
    assert len(receipts) == 21
    assert len({row["file"] for row in receipts}) == 21
    for row in receipts:
        text_path = directory / row["file"]
        assert text_path.name == row["file"]
        text_bytes = text_path.read_bytes()
        capture = text_path.with_suffix(".json").read_bytes()
        assert hashlib.sha256(text_bytes).hexdigest() == row["sha256_utf8"]
        assert hashlib.sha256(capture).hexdigest() == row["json_sha256"]
        assert json.loads(capture)["text"].encode("utf-8") == text_bytes


def test_daemons_final_four_performance_scope_is_exact_and_preserves_policy_chain() -> None:
    from tools.performance_daemons_final import BASE as FINAL_BASE
    from tools.performance_daemons_final import (
        OPERATIONS,
        daemons_final_policy_predecessor,
        daemons_final_smoke_operations,
    )
    from tools.performance_daemons_final import SCOPE as FINAL_SCOPE

    scope = read_object(ROOT / FINAL_SCOPE)
    for path, change in object_value(scope["changes"]).items():
        assert daemons_final_smoke_operations(
            base=FINAL_BASE, path=path, category="rule_semantics", change=change
        ) == frozenset({OPERATIONS[path]})
        for base, selected, category in (
            ("0" * 40, path, "rule_semantics"),
            (FINAL_BASE, "tools/unreviewed.py", "rule_semantics"),
            (FINAL_BASE, path, "algorithm_or_search"),
            (FINAL_BASE, path, "cache_policy"),
            (FINAL_BASE, path, "serialization_or_replay_work"),
        ):
            assert not daemons_final_smoke_operations(
                base=base, path=selected, category=category, change=change
            )
        drift = copy.deepcopy(object_value(change))
        drift["after_sha256"] = "0" * 64
        assert not daemons_final_smoke_operations(
            base=FINAL_BASE, path=path, category="rule_semantics", change=drift
        )
        drift = copy.deepcopy(object_value(change))
        object_value(next(iter(object_value(drift["owners"]).values())))["after"] = "0" * 64
        assert not daemons_final_smoke_operations(
            base=FINAL_BASE, path=path, category="rule_semantics", change=drift
        )
    current = (ROOT / "tools/performance_policy.py").read_bytes()
    before = subprocess.check_output(
        ["git", "show", FINAL_BASE + ":tools/performance_policy.py"], cwd=ROOT
    )
    assert daemons_final_policy_predecessor(current) == before
    assert daemons_final_policy_predecessor(before) == before
    for policy_drift in (
        current + b"\n",
        current.replace(b"daemons_final_smoke_operations", b"other_operation"),
    ):
        with pytest.raises(ValueError, match="Daemons final-four"):
            daemons_final_policy_predecessor(policy_drift)
    assert policy.starfang_deep_strike_policy_predecessor(current) == subprocess.check_output(
        ["git", "show", BASE + ":tools/performance_policy.py"], cwd=ROOT
    )


def test_daemons_final_four_retained_capture_bytes_match_receipts() -> None:
    import hashlib
    import json

    directory = ROOT / "data/source_audits/daemons_final_four_2026_11"
    raw = (directory / "source-capture-receipts.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "3da81bad73e6e8ef6655cff3f8961480a3980ae64d28b1d11fc983bb26e02536"
    )
    receipts = json.loads(raw)
    assert len(receipts) == 25
    assert len({row["file"] for row in receipts}) == 25
    for row in receipts:
        text_path = directory / row["file"]
        assert text_path.name == row["file"]
        text_bytes = text_path.read_bytes()
        capture = text_path.with_suffix(".json").read_bytes()
        assert hashlib.sha256(text_bytes).hexdigest() == row["sha256_utf8"]
        assert hashlib.sha256(capture).hexdigest() == row["json_sha256"]
        assert json.loads(capture)["text"].encode("utf-8") == text_bytes
