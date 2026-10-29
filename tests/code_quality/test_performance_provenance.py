"""Complete-byte provenance reuse keeps every live source observation fresh."""

from __future__ import annotations

import contextvars
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from tools import performance_preflight as preflight
from tools.performance_preflight import AdmissionOperands, AdmissionValidator


class _Storage(Protocol):
    limit: int
    retained: int
    active: bool
    admissions: dict[tuple[Any, ...], AdmissionOperands]

    def digest(self, path: str, raw: bytes) -> str: ...

    def admission(
        self,
        validator: AdmissionValidator,
        operands: AdmissionOperands,
        identity: tuple[str, ...],
        dependencies: tuple[Callable[..., Any], ...],
    ) -> None: ...


class _Mechanisms(Protocol):
    def _Digests(self, limit: int) -> _Storage: ...

    def _same_read(
        self,
        before: os.stat_result,
        opened: os.stat_result,
        closed: os.stat_result,
        after: os.stat_result,
        *,
        windows: bool,
    ) -> bool: ...

    def storage(self, limit: int) -> _Storage:
        return self._Digests(limit)

    def read_validator(self) -> Callable[..., bool]:
        return self._same_read


_mechanisms = cast(_Mechanisms, preflight)
IDENTITY: tuple[str, ...] = ("repository", "phase", "native-catalog", "plain60")


def test_admission_reuses_only_successful_complete_operands() -> None:
    calls: list[AdmissionOperands] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(operands)
        if operands != (("first", 0o100644, b"original"),):
            raise ValueError("different source")

    @preflight.invocation
    def run() -> None:
        original = (("first", 0o100644, b"original"),)
        preflight.admission_proof(check, original, IDENTITY, ())
        preflight.admission_proof(check, original, IDENTITY, ())
        for _ in range(2):
            with pytest.raises(ValueError, match="different source"):
                preflight.admission_proof(check, (("first", 0o100644, b"modified"),), IDENTITY, ())
        preflight.admission_proof(check, original, IDENTITY, ())

    run()
    run()
    assert len(calls) == 8


@pytest.mark.parametrize(
    "changed",
    [
        (("second", 0o100644, b"same"), ("first", 0o100644, b"same")),
        (("first", 0o100755, b"same"), ("second", 0o100644, b"same")),
        (("first", 0o100644, b"same"), ("second", 0o100644, b"else")),
        (("first", 0o100644, b"same"), ("first", 0o100644, b"same")),
    ],
    ids=["order", "mode", "bytes", "multiplicity"],
)
def test_admission_key_preserves_order_mode_bytes_and_multiplicity(
    changed: AdmissionOperands,
) -> None:
    calls: list[AdmissionOperands] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(operands)

    @preflight.invocation
    def run() -> None:
        initial = (("first", 0o100644, b"same"), ("second", 0o100644, b"same"))
        preflight.admission_proof(check, initial, IDENTITY, ())
        preflight.admission_proof(check, changed, IDENTITY, ())

    run()
    assert len(calls) == 2


@pytest.mark.parametrize("field", range(4), ids=["repository", "phase", "catalog", "domain"])
def test_admission_identity_changes_require_independent_proof(field: int) -> None:
    calls: list[tuple[str, ...]] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(identity)

    @preflight.invocation
    def run() -> None:
        changed = list(IDENTITY)
        changed[field] += "-changed"
        preflight.admission_proof(check, (), IDENTITY, ())
        preflight.admission_proof(check, (), tuple(changed), ())

    run()
    assert len(calls) == 2


def test_admission_validator_and_semantic_dependency_are_part_of_identity() -> None:
    calls: list[str] = []

    def first(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("first")

    def second(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("second")

    @preflight.invocation
    def run() -> None:
        preflight.admission_proof(first, (), IDENTITY, (str,))
        preflight.admission_proof(first, (), IDENTITY, (bytes,))
        preflight.admission_proof(second, (), IDENTITY, (bytes,))

    run()
    assert calls == ["first", "first", "second"]


@pytest.mark.parametrize("cancel", [False, True])
def test_admission_revokes_copied_context_after_success_or_cancellation(cancel: bool) -> None:
    contexts: list[contextvars.Context] = []
    calls: list[AdmissionOperands] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(operands)

    @preflight.invocation
    def run() -> None:
        preflight.admission_proof(check, (), IDENTITY, ())
        contexts.append(contextvars.copy_context())
        if cancel:
            raise KeyboardInterrupt("cancelled")

    if cancel:
        with pytest.raises(KeyboardInterrupt, match="cancelled"):
            run()
    else:
        run()
    contexts[0].run(preflight.admission_proof, check, (), IDENTITY, ())
    assert calls == [(), ()]


def test_admission_and_digest_share_the_existing_payload_limit() -> None:
    storage = _Mechanisms.storage(_mechanisms, 8)
    calls: list[AdmissionOperands] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(operands)

    storage.digest("source", b"1234")
    operands = (("proof", 0o100644, b"56789"),)
    storage.admission(check, operands, IDENTITY, ())
    storage.admission(check, operands, IDENTITY, ())
    assert len(calls) == 2
    assert storage.retained == 4
    small = (("proof", 0o100644, b"5678"),)
    storage.admission(check, small, IDENTITY, ())
    storage.admission(check, small, IDENTITY, ())
    assert len(calls) == 3
    assert storage.retained == storage.limit == 8


def test_fresh_members_read_changed_bytes_with_restored_mtime(tmp_path: Path) -> None:
    path = tmp_path / "source.py"
    path.write_bytes(b"before")
    metadata = path.stat()
    first = preflight.source_members(tmp_path, ["source.py"])
    path.write_bytes(b"edited")
    os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    second = preflight.source_members(tmp_path, ["source.py"])
    assert first[0][2] == b"before"
    assert second[0][2] == b"edited"
    assert first != second


def test_fresh_members_preserve_requested_observation_order(tmp_path: Path) -> None:
    for name in ("second.py", "first.py"):
        (tmp_path / name).write_bytes(name.encode())
    members = preflight.source_members(tmp_path, ["second.py", "first.py", "second.py"])
    assert [name for name, _, _ in members] == ["second.py", "first.py", "second.py"]


@pytest.mark.parametrize("kind", ["file", "ancestor", "hardlink", "root"])
def test_fresh_members_reject_unowned_paths(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "root"
    directory = root / "nested"
    directory.mkdir(parents=True)
    path = directory / "source.py"
    path.write_bytes(b"source")
    if kind == "file":
        target = tmp_path / "target.py"
        path.rename(target)
        path.symlink_to(target)
    elif kind == "ancestor":
        target = tmp_path / "target"
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
    elif kind == "hardlink":
        os.link(path, tmp_path / "alias.py")
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    with pytest.raises(ValueError, match=r"Aliased|owned regular"):
        preflight.source_members(root, ["nested/source.py"])


@pytest.mark.parametrize("above_root", [False, True], ids=["descendant", "absolute-ancestor"])
def test_fresh_members_recheck_ancestor_before_each_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, above_root: bool
) -> None:
    parent = tmp_path / "parent"
    root = parent / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    for name in ("first.py", "second.py"):
        (nested / name).write_bytes(b"same")
    original_read = _Mechanisms.read_validator(_mechanisms)
    original_open = cast(Callable[..., Any], Path.open)
    switched = False
    second_file_opened = False

    def observe_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        nonlocal second_file_opened
        if path == nested / "second.py":
            second_file_opened = True
        return original_open(path, *args, **kwargs)

    def observe_read(*args: Any, **kwargs: Any) -> bool:
        nonlocal switched
        result = original_read(*args, **kwargs)
        if not switched:
            selected = parent if above_root else nested
            target = tmp_path / "saved"
            selected.rename(target)
            selected.symlink_to(target, target_is_directory=True)
            switched = True
        return result

    monkeypatch.setattr(Path, "open", observe_open)
    monkeypatch.setattr(preflight, "_same_read", observe_read)
    with pytest.raises(ValueError, match=r"Aliased|owned regular"):
        preflight.source_members(root, ["nested/first.py", "nested/second.py"])
    assert switched
    assert not second_file_opened


class _Ci60Mechanisms(Protocol):
    def _current_applicability(
        self, actual: dict[str, bytes], current: dict[str, str], family: str
    ) -> dict[str, Any]: ...

    def applicability(
        self, actual: dict[str, bytes], current: dict[str, str], family: str
    ) -> dict[str, Any]:
        return self._current_applicability(actual, current, family)

    def validators(self) -> tuple[AdmissionValidator, AdmissionValidator]:
        return self._admitted_derivation, self._derivation_transition

    def _derivation_transition(
        self, operands: AdmissionOperands, identity: tuple[str, ...]
    ) -> None: ...

    def transition(self, operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        return self._derivation_transition(operands, identity)

    def _admitted_derivation(
        self, operands: AdmissionOperands, identity: tuple[str, ...]
    ) -> None: ...

    def derive(self, operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        return self._admitted_derivation(operands, identity)


@pytest.fixture(scope="module")
def original_ci60_operands() -> AdmissionOperands:
    """Actual native E/F objects exercise the preserved original proof unchanged."""
    import json
    import subprocess

    from tools import performance_ci60_qualification as ci60
    from tools.performance_preflight_successor import read_frozen_blobs

    root = Path(__file__).resolve().parents[2]
    names = (
        subprocess.check_output(
            ["git", "diff", "--name-only", ci60.BASE, str(ci60.FREEZE)], cwd=root
        )
        .decode()
        .splitlines()
    )
    frozen = read_frozen_blobs(root, str(ci60.FREEZE), names)
    previous = read_frozen_blobs(root, ci60.BASE, sorted(ci60.CONTROLS))
    current = read_frozen_blobs(root, ci60.DERIVATION_BASE, names)
    return (
        ("freeze", 0, str(ci60.FREEZE).encode()),
        ("selection", 0, json.dumps(names).encode()),
        *(("frozen/" + name, 0, raw) for name, raw in frozen.items()),
        *(("old/" + name, 0, raw) for name, raw in previous.items()),
        ("assessment-first", 0, current[ci60.ASSESSMENT]),
        ("assessment-second", 0, current[ci60.ASSESSMENT]),
        *(("current/" + name, 0, raw) for name, raw in current.items()),
    )


def test_original_native_ci60_derivation_matches_reused_verdict(
    original_ci60_operands: AdmissionOperands,
) -> None:
    from tools import performance_ci60_qualification as ci60

    stage = cast(_Ci60Mechanisms, ci60)
    calls = 0

    def validate(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        nonlocal calls
        calls += 1
        _Ci60Mechanisms.derive(stage, operands, identity)

    # One independent direct derivation and then exactly one bounded reused proof.
    _Ci60Mechanisms.derive(stage, original_ci60_operands, ())

    @preflight.invocation
    def run() -> None:
        preflight.admission_proof(validate, original_ci60_operands, IDENTITY, ())
        preflight.admission_proof(validate, original_ci60_operands, IDENTITY, ())

    run()
    assert calls == 1


@pytest.mark.parametrize(
    "selected",
    ["assessment-first", "assessment-second", "current/tools/performance_policy.py"],
)
def test_original_native_derivation_rejects_each_changed_observation(
    original_ci60_operands: AdmissionOperands, selected: str
) -> None:
    from tools import performance_ci60_qualification as ci60

    stage = cast(_Ci60Mechanisms, ci60)
    changed = tuple(
        (name, mode, b"{}" if name == selected else raw)
        for name, mode, raw in original_ci60_operands
    )
    assert changed != original_ci60_operands
    with pytest.raises(ValueError, match=r"assessment|Preflight source"):
        _Ci60Mechanisms.derive(stage, changed, ())


def test_independent_preflight_and_postflight_do_not_share_derivations() -> None:
    calls: list[str] = []

    def validate(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("proof")

    @preflight.invocation
    def phase() -> None:
        preflight.admission_proof(validate, (), IDENTITY, ())
        preflight.admission_proof(validate, (), IDENTITY, ())

    phase()
    phase()
    assert calls == ["proof", "proof"]


def test_unscoped_observations_do_not_reuse_derivations() -> None:
    calls: list[str] = []

    def validate(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("proof")

    @preflight.invocation
    def run() -> None:
        preflight.admission_proof(validate, (), None, ())
        preflight.admission_proof(validate, (), None, ())

    run()
    assert calls == ["proof", "proof"]


@pytest.mark.parametrize("cancel", [False, True])
def test_activated_native_history_revokes_copied_phase_after_completion(
    cancel: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from tools import performance_ci60_qualification as ci60
    from tools import performance_ci69_members as ci69
    from tools import performance_history_snapshot as history
    from tools import performance_policy as policy

    original_bindings = preflight.ci60_admission_bindings()
    for module, attribute in (
        (ci60, "ci69"),
        (ci60, "ast"),
        (ci60, "json"),
        (ci60, "hashlib"),
        (ci69, "ast"),
        (ci69, "json"),
        (ci69, "hashlib"),
        (policy, "ast"),
        (policy, "hashlib"),
    ):
        with monkeypatch.context() as aliases:
            aliases.setattr(module, attribute, object())
            with pytest.raises(ValueError, match="module alias"):
                preflight.ci60_admission_bindings()
        assert preflight.ci60_admission_bindings() == original_bindings
    for attribute in (
        "CONTROL_MEMBERS",
        "INPUT_ADDITIONS",
        "OBSERVED_ADDITIONS",
        "CUTOVER_PATH",
        "RUNTIME_SUCCESSORS",
        "CUTOVER_NEW",
        "CUTOVER_ADDED_INPUTS",
        "RETIRED_TESTS",
        "RETIREMENT_NAMESPACE",
    ):
        original_selector = cast(frozenset[str] | str, vars(ci69)[attribute])
        changed_selector = (
            original_selector | {"unexpected"}
            if isinstance(original_selector, frozenset)
            else original_selector + "-unexpected"
        )
        with monkeypatch.context() as aliases:
            aliases.setattr(ci69, attribute, changed_selector)
            assert preflight.ci60_admission_bindings() != original_bindings
        assert preflight.ci60_admission_bindings() == original_bindings

    root = Path(__file__).resolve().parents[2]
    copied: list[contextvars.Context] = []
    observations: list[tuple[str, ...]] = []
    source_members = preflight.source_members
    computations: list[str] = []
    original, transition = _Ci60Mechanisms.validators(cast(_Ci60Mechanisms, ci60))

    def original_proof(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        computations.append("original")
        original(operands, identity)

    def transition_proof(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        computations.append("transition")
        transition(operands, identity)

    monkeypatch.setattr(ci60, "_admitted_derivation", original_proof)
    monkeypatch.setattr(ci60, "_derivation_transition", transition_proof)

    def observe(selected: Path, names: list[str]) -> AdmissionOperands:
        result = source_members(selected, names)
        observations.append(tuple(names))
        return result

    monkeypatch.setattr(preflight, "source_members", observe)
    live_head_checks: list[tuple[str, ...]] = []
    original_git = ci60.git

    def observe_git(selected: Path, *args: str) -> bytes:
        if args[:2] == ("merge-base", "--is-ancestor") and args[-1] == "HEAD":
            live_head_checks.append(args)
        return original_git(selected, *args)

    monkeypatch.setattr(ci60, "git", observe_git)

    @preflight.invocation
    def run() -> None:
        computations.clear()  # Include the original bootstrap computation.
        with history.phase(root, ci60.PR_BASE, None):
            assert computations == ["transition", "original"]
            identity = history.proof_identity(root)
            assert identity is not None
            assert identity[0] == root.as_posix()
            assert len(identity[1]) == 32
            with pytest.raises(ValueError, match="another repository"):
                history.proof_identity(root / "different")
            with ThreadPoolExecutor(max_workers=1) as pool:
                wrong_thread = contextvars.copy_context()
                with pytest.raises(ValueError, match="inactive"):
                    pool.submit(wrong_thread.run, history.proof_identity, root).result(timeout=5)
            start = len(observations)
            head_start = len(live_head_checks)
            first = ci60.admitted(root)
            first_observations = observations[start:]
            first_head_checks = live_head_checks[head_start:]
            assert first_head_checks == [
                ("merge-base", "--is-ancestor", str(freeze), "HEAD")
                for freeze in (ci60.FREEZE, ci60.DERIVATION_FREEZE, ci60.PRELUDE_FREEZE)
            ]
            first[ci60.SELF] = b"caller-owned dictionary"
            start = len(observations)
            head_start = len(live_head_checks)
            second = ci60.admitted(root)
            assert live_head_checks[head_start:] == first_head_checks
            assert observations[start:] == first_observations
            assert computations == ["transition", "original"]
            cutover_rows = {
                "tests/rules/section04/test_completion_boundaries.py",
                "tests/rules/rules24/unit/test_shadow_form_lookup.py",
                "tests/rules/section05/test_rule_effect_retention.py",
                "tests/rules/section11/test_required_target_protocol.py",
                "tests/unit/test_phase13b_shooting_declarations.py",
                "tests/unit/test_phase15c_fight_order.py",
            }
            cutover_rows.add("tests/performance/test_fight_phase_reconstruction.py")
            cutover_rows |= {
                ci69.RETIREMENT_NAMESPACE + name + ".txt" for name in ci69.RETIRED_TESTS
            }
            cutover_operands = (
                *(("next-frozen/" + name, 0, raw) for name, raw in second.items()),
                *(
                    ("next-current/" + name, (root / name).stat().st_mode, second[name])
                    for name in sorted(cutover_rows)
                ),
            )
            cutover_calls: list[str] = []

            def validate_cutover(operands: AdmissionOperands, _identity: tuple[str, ...]) -> None:
                cutover_calls.append("native")
                ci69.validate_cutover(operands)

            preflight.admission_proof(validate_cutover, cutover_operands, identity, ())
            preflight.admission_proof(validate_cutover, cutover_operands, identity, ())
            assert cutover_calls == ["native"]
            changed_record = json.loads(second[ci69.CUTOVER_PATH])
            changed_record["coverage"]["current_floor"] = 49
            changed_operands = tuple(
                (
                    name,
                    mode,
                    json.dumps(changed_record).encode()
                    if name == "next-frozen/" + ci69.CUTOVER_PATH
                    else raw,
                )
                for name, mode, raw in cutover_operands
            )
            assert changed_operands != cutover_operands
            with pytest.raises(ValueError, match="coverage policy"):
                preflight.admission_proof(validate_cutover, changed_operands, identity, ())
            assert cutover_calls == ["native", "native"]
            preflight.admission_proof(validate_cutover, cutover_operands, identity, ())
            assert cutover_calls == ["native", "native"]
            latest_status = ci60.history(
                root,
                "diff",
                "--name-status",
                "--no-renames",
                "-z",
                ci60.PRELUDE_BASE,
                str(ci60.PRELUDE_FREEZE),
            )
            latest_names = ci69.prelude_members(latest_status, ci60.PRELUDE_MEMBERS)
            retired_name = min(ci69.RETIRED_TESTS)
            deletion = b"D\0" + retired_name.encode() + b"\0"
            assert latest_status.count(deletion) == 1
            for wrong in (
                latest_status.replace(deletion, b"M\0" + retired_name.encode() + b"\0", 1),
                latest_status.replace(deletion, b"R100\0" + retired_name.encode() + b"\0", 1),
                latest_status.replace(deletion, b"", 1),
                latest_status + deletion,
                latest_status + b"A\0tests/unit/unlisted.py\0",
            ):
                with pytest.raises(ValueError, match="CI64"):
                    ci69.prelude_members(wrong, ci60.PRELUDE_MEMBERS)
            cutover_observed = {
                ".github/pull_request_template.md",
                ".github/workflows/ci.yml",
                "AGENTS.md",
                "README.md",
                "data/source_audits/ci64_provenance_v1/test-cutover.json",
                "docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md",
                "pyproject.toml",
                "scripts/build_test_shards.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
                "src/warhammer40k_core/engine/model_attack_completion.py",
                "src/warhammer40k_core/engine/phases/shooting_decisions.py",
                "src/warhammer40k_core/engine/phases/shooting_handler.py",
                "src/warhammer40k_core/engine/phases/shooting_model.py",
                "src/warhammer40k_core/engine/retained_destruction_dispatch.py",
                "src/warhammer40k_core/engine/retained_shooting.py",
                "src/warhammer40k_core/engine/shooting_target_replacement.py",
                "src/warhammer40k_core/engine/target_replacement_dispatch.py",
                "tests/code_quality/test_ci_performance_gates.py",
                "tests/conftest.py",
                "tests/emergency_geometry_helpers.py",
                "tests/order101_failed_setup_helpers.py",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/rules/rules24/unit/test_shadow_form_lookup.py",
                "tests/rules/section04/test_completion_boundaries.py",
                "tests/rules/section05/test_rule_effect_retention.py",
                "tests/rules/section11/test_required_target_protocol.py",
                "tests/support/section05_rule_effect_retention.py",
                "tests/unit/test_phase13b_shooting_declarations.py",
                "tests/unit/test_phase15c_fight_order.py",
            }
            cutover_observed |= {
                "tests/measurement_native_api.py",
                "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/order101_failed_setup_helpers.py.txt",
                "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/emergency_geometry_helpers.py.txt",
                "data/source_audits/ci64_provenance_v1/benchmark-api-preimages/tests/phase13b_shooting_declaration_helpers.py.txt",
            }
            cutover_observed |= {
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/integration/test_order127_infiltrators_redeploy.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/integration/test_order128_setup_overhang.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/integration/test_order135_gathered_override.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/integration/test_order135_gathered_psychic_preparation.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order100_frame_measurement.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order101_setup_failure.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order104_range_visibility.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order105_hazard.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order106_pile_in.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order107_fight_distance_window.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order108_terrain_semantics.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order109_unit_control.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order111_friendly_transit.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order115_absent_movement.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order116_additional_mortals.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order117_mortal_allocation.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order121_command_abilities.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order122_effect_defaults.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order123_datasheet_identity.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order124_nested_conditions.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order125_implicit_subjects.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order126_sequential_movement.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order128_setup_model_fit.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order129_flight_history.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order130_model_mission_destruction.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order131_objective_endpoint_geometry.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order131_objective_movement.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order132_disembark_distance.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order133_keyword_materialization.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order133_keyword_numbers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order134_deployment_restrictions.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_combat_tactical_feasibility.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_counteroffensive_band.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_counteroffensive_timing.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_fight_pass.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_fight_transition.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_gathered_attack_steps.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_gathered_wound_callback.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_objective_overlap.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_physical_visibility.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_shooting_boundary.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_tactical_setup_proof.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_transport_boundaries.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_visibility_facade.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order135_visibility_rng_projection.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order36_sequencing.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order36_timing_authority.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order51_flight.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order52_surge.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order53_movement_abilities.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order54_setup.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order55_disembark.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order57_destroyed_referent_measurement.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order58_failed_save_damage_timing.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order59_empty_dedicated_transport.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order60_emergency_disembark.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order61_embark.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order63_reserve_transports.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order64_reserve_lifetimes.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order65_firing_deck.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order78_gone_to_ground.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order79_control_first.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order80_normal_move.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order81_parameterized_projection.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order82_revival_engagement.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order85_deemed_base_contact.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order86_table_quarters.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order87_gathered_profile_restore.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order87_random_profiles.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order88_absent_strength.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order89_healing.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order90_off_battlefield_revival.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order91_empty_shooting.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order92_random_melee.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_attack_modifiers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_catalog_leadership_modifiers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_healing_modifiers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_mission_action_modifiers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_modifier_ignore.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_nonattack_modifiers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_permission_context.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order93_weapon_modifiers.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order95_optional_shooting.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order96_twin_linked.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_attack_evidence.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_damage_evidence.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_facade_evidence.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_foundation_evidence.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_movement_evidence.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_secondary_clause_evidence.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_semantic_evidence_18_25.py.txt",
                "data/source_audits/ci64_provenance_v1/retired-tests/tests/unit/test_order97_timing_evidence.py.txt",
                "tests/category_migration_preservation.py",
                "tests/code_quality/test_order135_current_core_audit.py",
                "tests/code_quality/test_s25_fixture_preservation.py",
                "tools/core_rules_order97_history.py",
                "tools/core_rules_order97_inventory.py",
            }
            cutover_observed.add("tools/core_rules_order95_audit.py")
            cutover_observed |= {
                "contracts/examples/support-profile-player-b-redacted.json",
                "contracts/manifest.json",
                "contracts/examples/persistence/session-persistence.json",
                "contracts/examples/sessions/session-command-outcome.json",
                "contracts/examples/support-profile.json",
                "contracts/examples/support-profile-player-a-redacted.json",
                "contracts/examples/sessions/session-metadata-created.json",
                "contracts/examples/sessions/session-command-started.json",
            }
            cutover_observed |= {
                "scripts/measure_order72.py",
                "tests/performance/test_fight_phase_reconstruction.py",
                "ci/test_shards/case-partitions.json",
                "tests/support/fight_phase_reconstruction.py",
            }
            cutover_observed |= {
                "ci/test_shards/shard-11.txt",
                "ci/test_shards/shard-2.txt",
                "ci/test_shards/shard-3.txt",
                "ci/test_shards/shard-5.txt",
                "ci/test_shards/shard-7.txt",
                "ci/test_shards/shard-4.txt",
                "ci/test_shards/shard-1.txt",
                "ci/test_shards/shard-9.txt",
                "ci/test_shards/shard-10.txt",
                "ci/test_shards/shard-12.txt",
                "ci/test_shards/shard-8.txt",
                "ci/test_shards/durations.json",
                "ci/test_shards/shard-6.txt",
            }
            cutover_observed |= {
                "data/source_audits/ci64_provenance_v1/measurements/dice-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/dice-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/dice_sustained-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/dice_sustained-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/fight-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/fight-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/movement-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/movement-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/objective_control-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/objective_control-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/reconstruction-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/reconstruction-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/roster-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/roster-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/setup-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/setup-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/shock_reconstruction-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/shock_reconstruction-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/strength-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/strength-head.json",
                "data/source_audits/ci64_provenance_v1/measurements/visibility-base.json",
                "data/source_audits/ci64_provenance_v1/measurements/visibility-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/dice-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/dice-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/dice_sustained-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/dice_sustained-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/fight-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/fight-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/movement-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/movement-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/objective_control-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/objective_control-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/reconstruction-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/reconstruction-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/roster-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/roster-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/setup-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/setup-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/shock_reconstruction-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/shock_reconstruction-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/strength-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/strength-head.json",
                "data/source_audits/ci64_provenance_v1/receipts/visibility-base.json",
                "data/source_audits/ci64_provenance_v1/receipts/visibility-head.json",
                "docs/ORDER_124_SCOPE_PLAN.md",
                "docs/SECTION24_CORE_ABILITIES_SCOPE.md",
                "docs/performance/current/ci78-current-dice.json",
                "docs/performance/current/ci78-current-dice_sustained.json",
                "docs/performance/current/ci78-current-external_contract_source_reuse.json",
                "docs/performance/current/ci78-current-fight.json",
                "docs/performance/current/ci78-current-movement.json",
                "docs/performance/current/ci78-current-objective_control.json",
                "docs/performance/current/ci78-current-reconstruction.json",
                "docs/performance/current/ci78-current-roster.json",
                "docs/performance/current/ci78-current-setup.json",
                "docs/performance/current/ci78-current-shock_reconstruction.json",
                "docs/performance/current/ci78-current-strength.json",
                "docs/performance/current/ci78-current-visibility.json",
                "src/warhammer40k_core/engine/catalog_setup_reactive_shoot_charge.py",
                "src/warhammer40k_core/engine/catalog_shadow_form_runtime.py",
                "src/warhammer40k_core/engine/decision.py",
                "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py",
                "src/warhammer40k_core/engine/phases/charge.py",
                "tests/integration/test_catalog_rule_ir_runtime.py",
                "tests/integration/test_embarked_ability_authority.py",
                "tests/integration/test_fight_on_death_presence.py",
                "tests/integration/test_retained_shooting.py",
                "tests/phase15a_charge_declaration_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "tests/replay/test_phase18b_replay_runner.py",
                "tests/rules/section07/coverage.json",
                "tests/rules/section18/coverage.json",
                "tests/rules/section20/coverage.json",
                "tests/rules/section22/coverage.json",
                "tests/rules/section24/README.md",
                "tests/rules/section24/coverage.json",
                "tests/rules/section24/test_inventory.py",
                "tests/shared/category_migration/phase17d_rule_execution.py",
                "tests/unit/test_dice.py",
                "tests/unit/test_phase11e_mission_scoring_cleanup.py",
                "tests/unit/test_phase15a_charge_declarations.py",
                "tests/unit/test_phase17_emperors_children_datasheet_overlay.py",
                "tests/unit/test_phase17g_chaos_daemons_blood_legion.py",
                "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py",
                "tests/unit/test_phase17n_runtime_rule_ir_oc_authority.py",
            }
            assert len(cutover_observed) == 241
            assert len(first_observations[4]) == 274
            assert sum(map(len, first_observations)) == 410
            assert all(first_observations[4].count(name) == 1 for name in cutover_observed)
            assert first_observations[4] == tuple(
                name for name in latest_names if name in ci60.PRELUDE_OBSERVED
            )
            first_observations = [
                *first_observations[:4],
                tuple(name for name in first_observations[4] if name not in cutover_observed),
            ]
            latest_names = [name for name in latest_names if name not in cutover_observed]
            perils_guard = "tests/code_quality/test_thousand_sons_perils_preservation.py"
            assert len(first_observations[4]) == 33
            assert sum(map(len, first_observations)) == 169
            assert first_observations[4].count(perils_guard) == 1
            assert first[perils_guard] == (root / perils_guard).read_bytes()
            assert first_observations[4] == tuple(
                name for name in latest_names if name in ci60.PRELUDE_OBSERVED
            )
            first_observations = [
                *first_observations[:4],
                tuple(name for name in first_observations[4] if name != perils_guard),
            ]
            latest_names = [name for name in latest_names if name != perils_guard]
            static_test = "tests/code_quality/test_performance_static_successor.py"
            assert len(first_observations) == 5
            assert len(first_observations[4]) == 32
            assert sum(map(len, first_observations)) == 168
            assert first_observations[4] == tuple(
                name for name in latest_names if name in ci60.PRELUDE_OBSERVED
            )
            assert first_observations[4].count(static_test) == 1
            first_observations = [
                *first_observations[:4],
                tuple(name for name in first_observations[4] if name != static_test),
            ]
            latest_names = [name for name in latest_names if name != static_test]
            # Validate the complete new observation before the exact historical views.
            ci69_observed = {
                "tests/d07_geometry_containment.py",
                "tests/code_quality/test_d07_geometry_containment.py",
                "tests/code_quality/test_quality_runtime.py",
                "ci/quality_shards/shard-4.txt",
                "ci/quality_shards/shard-2-modules.txt",
                "ci/quality_shards/shard-3-modules.txt",
                "ci/quality_shards/shard-4-modules.txt",
                "tests/data/d07_geometry_containment_v3.json",
                "tools/performance_ci69_members.py",
            }
            assert len(ci69_observed) == 9
            assert len(first_observations) == 5
            assert len(first_observations[4]) == 31
            assert sum(map(len, first_observations)) == 167
            assert first_observations[4] == tuple(
                name for name in latest_names if name in ci60.PRELUDE_OBSERVED
            )
            assert all(first_observations[4].count(name) == 1 for name in ci69_observed)
            first_observations = [
                *first_observations[:4],
                tuple(name for name in first_observations[4] if name not in ci69_observed),
            ]
            latest_names = [name for name in latest_names if name not in ci69_observed]
            extra_observed = {
                "tests/code_quality/test_performance_category_migration.py",
                "tools/performance_preflight_successor.py",
            }
            assert len(extra_observed) == 2
            assert len(first_observations) == 5
            assert len(first_observations[4]) == 22
            assert sum(map(len, first_observations)) == 158
            assert first_observations[4] == tuple(
                name for name in latest_names if name in ci60.PRELUDE_OBSERVED
            )
            assert all(first_observations[4].count(name) == 1 for name in extra_observed)
            assert not extra_observed.intersection(
                name for scan in first_observations[:4] for name in scan
            )
            first_observations = [
                *first_observations[:4],
                tuple(name for name in first_observations[4] if name not in extra_observed),
            ]
            latest_names = [name for name in latest_names if name not in extra_observed]
            added = {ci60.TRANSACTION_TEST} | ci60.TRANSACTION_SHARDS
            assert len(added) == 3
            assert len(first_observations) == 5
            assert len(first_observations[4]) == 20
            assert sum(map(len, first_observations)) == 156
            assert first_observations[4] == tuple(
                name for name in latest_names if name in ci60.PRELUDE_OBSERVED
            )
            assert all(first_observations[4].count(name) == 1 for name in added)
            assert not added.intersection(name for scan in first_observations[:4] for name in scan)
            first_observations = [
                *first_observations[:4],
                tuple(name for name in first_observations[4] if name not in added),
            ]
            expected_new = tuple(
                name for name in latest_names if name in ci60.PRELUDE_NEW - {ci60.TRANSACTION_TEST}
            )
            assert len(first_observations) == 5
            assert len(expected_new) == 17
            assert first_observations[4] == expected_new
            assert sum(map(len, first_observations)) == 153
            first_observations = first_observations[:4]
            original_names = (
                ci60.history(root, "diff", "--name-only", ci60.BASE, str(ci60.FREEZE))
                .decode()
                .splitlines()
            )
            assert first_observations[:3] == [
                (ci60.ASSESSMENT,),
                (ci60.ASSESSMENT,),
                tuple(original_names),
            ]
            assert sum(map(len, first_observations[:3])) == 109
            assert set(first_observations[3]) == ci60.DERIVATION_MEMBERS
            assert len(first_observations) == 4
            assert second[ci60.SELF] == (root / ci60.SELF).read_bytes()
            copied.append(contextvars.copy_context())
            if cancel:
                raise KeyboardInterrupt("phase cancelled")

    if cancel:
        with pytest.raises(KeyboardInterrupt, match="phase cancelled"):
            run()
    else:
        run()
    with pytest.raises(ValueError, match="inactive"):
        copied[0].run(history.proof_identity, root)


@pytest.fixture(scope="module")
def finite_derivation_operands() -> AdmissionOperands:
    """Native predecessor bytes and an explicit synthetic activation exercise the recipe."""
    import json

    from tools import performance_ci60_qualification as ci60
    from tools.performance_policy import owner_hashes
    from tools.performance_preflight_successor import read_frozen_blobs

    root = Path(__file__).resolve().parents[2]
    previous = read_frozen_blobs(root, ci60.DERIVATION_BASE, sorted(ci60.DERIVATION_CONTROLS))
    frozen = dict.fromkeys(sorted(ci60.DERIVATION_MEMBERS), b"{}\n")
    frozen.update(previous)
    frozen[ci60.SELF] = (root / ci60.SELF).read_bytes()
    marker = b"\nDERIVATION_FREEZE: str | None = None"
    active = f'\nDERIVATION_FREEZE: str | None = "{ci60.DERIVATION_FREEZE}"'.encode()
    if marker not in frozen[ci60.SELF]:
        frozen[ci60.SELF] = frozen[ci60.SELF].replace(active, marker, 1)
    names = sorted(frozen)
    frozen[ci60.DERIVATION_NAMESPACE + "/changed-members.json"] = json.dumps(names).encode()
    transitions = {
        "schema": "ci61-exact-provenance-v1",
        "base": ci60.DERIVATION_BASE,
        "changes": {
            name: {
                "before_sha256": ci60.digest(previous[name]),
                "after_sha256": ci60.digest(frozen[name]),
                "edits": [{"before": previous[name].decode(), "after": frozen[name].decode()}],
            }
            for name in sorted(previous.keys() - {ci60.ASSESSMENT})
        },
    }
    frozen[ci60.DERIVATION_NAMESPACE + "/control-transitions.json"] = json.dumps(
        transitions
    ).encode()
    freeze = "1" * 40
    current = frozen | {
        ci60.SELF: frozen[ci60.SELF].replace(
            marker, f'\nDERIVATION_FREEZE: str | None = "{freeze}"'.encode(), 1
        )
    }
    assessment = json.loads(frozen[ci60.ASSESSMENT])
    assessment["changes"][ci60.SELF]["after_sha256"] = ci60.digest(current[ci60.SELF])
    assessment["changes"][ci60.SELF]["owners"]["@module"]["after"] = owner_hashes(
        ci60.SELF, current[ci60.SELF]
    )["@module"]
    current[ci60.ASSESSMENT] = json.dumps(assessment).encode()
    return (
        ("freeze", 0, freeze.encode()),
        ("selection", 0, json.dumps(names).encode()),
        *((f"frozen/{name}", 0, raw) for name, raw in frozen.items()),
        *((f"previous/{name}", 0, raw) for name, raw in previous.items()),
        *((f"current/{name}", 0o100644, raw) for name, raw in current.items()),
        ("assessment-first", 0o100644, current[ci60.ASSESSMENT]),
        ("assessment-second", 0o100644, current[ci60.ASSESSMENT]),
        *((f"observed/{name}", 0o100644, current[name]) for name in sorted(previous)),
    )


def test_finite_transition_reuses_only_complete_successful_bytes(
    finite_derivation_operands: AdmissionOperands,
) -> None:
    from tools import performance_ci60_qualification as ci60

    stage = cast(_Ci60Mechanisms, ci60)
    calls: list[str] = []

    def validate(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("derive")
        _Ci60Mechanisms.transition(stage, operands, identity)

    @preflight.invocation
    def run() -> None:
        preflight.admission_proof(validate, finite_derivation_operands, IDENTITY, ())
        preflight.admission_proof(validate, finite_derivation_operands, IDENTITY, ())

    run()
    assert calls == ["derive"]


@pytest.mark.parametrize(
    "selected",
    [
        "selection",
        "assessment-first",
        "assessment-second",
        "current/tools/performance_preflight.py",
        "observed/tools/performance_history_snapshot.py",
        "previous/tools/performance_preflight.py",
    ],
)
def test_finite_transition_rejects_changed_boundary_observations(
    finite_derivation_operands: AdmissionOperands, selected: str
) -> None:
    from tools import performance_ci60_qualification as ci60

    stage = cast(_Ci60Mechanisms, ci60)
    changed = tuple(
        (name, mode, b"[]" if name == "selection" else b"{}")
        if name == selected
        else (name, mode, raw)
        for name, mode, raw in finite_derivation_operands
    )
    with pytest.raises(ValueError, match=r"membership|assessment|Preflight|source changed"):
        _Ci60Mechanisms.transition(stage, changed, ())


def test_measurement_projection_includes_newly_changed_preflight_control(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tools import performance_ci60_qualification as ci60

    name = "tools/performance_preflight.py"
    current = {name: b"actual-current-collector", ci60.SELF: b"actual-self"}
    before = {name: b"native-E-collector"}

    def admitted(root: Path) -> dict[str, bytes]:
        assert root == tmp_path
        return current.copy()

    def projection(root: Path) -> dict[str, bytes]:
        assert root == tmp_path
        return before.copy()

    monkeypatch.setattr(ci60, "admitted", admitted)
    monkeypatch.setattr(ci60, "control_projection", projection)
    supplied = {path: ci60.digest(raw) for path, raw in current.items()}
    supplied["src/unchanged.py"] = "unchanged-runtime"
    assert ci60.measurement_controls(tmp_path, supplied) == {
        name: ci60.digest(before[name]),
        "src/unchanged.py": "unchanged-runtime",
    }
    with pytest.raises(ValueError, match="omitted current control bytes"):
        ci60.measurement_controls(tmp_path, supplied | {name: ci60.digest(before[name])})


def test_finite_transition_preserves_existing_operation_budgets(
    finite_derivation_operands: AdmissionOperands,
) -> None:
    import json

    from tools import performance_ci60_qualification as ci60

    values = {name: raw for name, _, raw in finite_derivation_operands}
    mapping = json.loads(values["frozen/" + ci60.MAP])
    mapping["families"]["external_contract_source_reuse"]["samples_per_case"] += 1
    replacement = json.dumps(mapping).encode()
    transition_name = ci60.DERIVATION_NAMESPACE + "/control-transitions.json"
    transitions = json.loads(values["frozen/" + transition_name])
    row = transitions["changes"][ci60.MAP]
    row["after_sha256"] = ci60.digest(replacement)
    row["edits"][0]["after"] = replacement.decode()
    updates = {
        "frozen/" + ci60.MAP: replacement,
        "current/" + ci60.MAP: replacement,
        "observed/" + ci60.MAP: replacement,
        "frozen/" + transition_name: json.dumps(transitions).encode(),
        "current/" + transition_name: json.dumps(transitions).encode(),
    }
    changed = tuple(
        (name, mode, updates.get(name, raw)) for name, mode, raw in finite_derivation_operands
    )
    with pytest.raises(ValueError, match="existing operation, family or budget"):
        _Ci60Mechanisms.transition(cast(_Ci60Mechanisms, ci60), changed, ())


def test_superseded_source_report_requires_exact_native_bytes() -> None:
    import hashlib
    import subprocess

    from tools import performance_ci60_qualification as ci60

    root = Path(__file__).resolve().parents[2]
    path = "docs/performance/current/ci60-external_contract_source_reuse.json"
    raw = subprocess.check_output(["git", "show", ci60.DERIVATION_BASE + ":" + path], cwd=root)
    change: dict[str, object] = {
        "before_sha256": None,
        "after_sha256": hashlib.sha256(raw).hexdigest(),
    }
    assert ci60.retained_historical_report(base=ci60.PR_BASE, path=path, change=change)
    assert not ci60.retained_historical_report(
        base=ci60.PR_BASE,
        path=path,
        change=change | {"after_sha256": hashlib.sha256(raw + b" ").hexdigest()},
    )
    assert not ci60.retained_historical_report(
        base=ci60.PR_BASE, path="docs/performance/current/unrelated.json", change=change
    )
    assert not ci60.retained_historical_report(
        base=ci60.PR_BASE, path=path, change=change | {"before_sha256": "existing"}
    )


@pytest.mark.parametrize("changed", ["inventories", "roles", "base"])
def test_source_token_binding_rejects_changed_finite_provenance(changed: str) -> None:
    import json

    from tools import performance_ci60_qualification as ci60

    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / ci60.NAMESPACE / "tool-input-roles.json").read_bytes())
    inventories = (root / spec["inventories_path"]).read_bytes()
    spec_path = ci60.DERIVATION_NAMESPACE + "/source-token-roles.json"
    spec["inventories_path"] = ci60.DERIVATION_NAMESPACE + "/source-token-inventories.json"
    actual = {spec_path: json.dumps(spec).encode(), spec["inventories_path"]: inventories}
    original = ci60.source_binding(
        actual, "test-producing-digest", namespace=ci60.DERIVATION_NAMESPACE
    )
    assert original["family"] == "external_contract_source_reuse"
    if changed == "inventories":
        altered = json.loads(inventories)
        altered["head"]["tools/performance_preflight.py"] = "changed"
        actual[spec["inventories_path"]] = json.dumps(altered).encode()
    elif changed == "roles":
        spec["roles"].pop(next(iter(spec["roles"])))
        actual[spec_path] = json.dumps(spec).encode()
    else:
        spec["base_revision"] = "0" * 40
        actual[spec_path] = json.dumps(spec).encode()
    with pytest.raises(ValueError, match="complete source-token input roles changed"):
        ci60.source_binding(actual, "test-producing-digest", namespace=ci60.DERIVATION_NAMESPACE)


@pytest.mark.parametrize("changed", ["runtime", "dependency", "startup-drop", "startup-pin"])
def test_activated_native_applicability_rejects_false_equivalence(changed: str) -> None:
    import json

    from tools import performance_ci60_qualification as ci60

    root = Path(__file__).resolve().parents[2]
    actual = ci60.admitted(root)
    from tools.performance_preflight_successor import read_frozen_blobs

    # Preserve the original CI61 negative fixture explicitly as native E61 data.
    actual = read_frozen_blobs(root, ci60.PRELUDE_BASE, sorted(actual.keys() - ci60.PRELUDE_NEW))
    producing_name = ci60.DERIVATION_NAMESPACE + "/producing-inputs.json"
    proof_name = ci60.DERIVATION_NAMESPACE + "/applicability.json"
    produced = json.loads(actual[producing_name])
    current = produced | {ci60.SELF: ci60.digest(actual[ci60.SELF])}
    stage = cast(_Ci60Mechanisms, ci60)
    original = _Ci60Mechanisms.applicability(stage, actual, current, "dice")
    assert len(original["families"]) == 11
    proof = json.loads(actual[proof_name])
    if changed in {"runtime", "dependency"}:
        path = "src/warhammer40k_core/__init__.py" if changed == "runtime" else "uv.lock"
        before = produced[path]
        produced[path] = ci60.digest(b"coordinated changed input")
        current[path] = produced[path]
        proof["current_producing_input_digest"] = ci60.canonical(produced)
        proof["changes"][path] = {"before": before, "after": produced[path]}
        proof["unchanged_inputs"].pop(path)
        actual[producing_name] = json.dumps(produced).encode()
    elif changed == "startup-drop":
        proof["families"]["dice"]["unchanged_startup"].pop("tests/conftest.py")
    else:
        proof["families"]["dice"]["unchanged_startup"]["tests/conftest.py"] = "altered"
    actual[proof_name] = json.dumps(proof).encode()
    with pytest.raises(ValueError, match=r"applicability changed|consumer/startup proof changed"):
        _Ci60Mechanisms.applicability(stage, actual, current, "dice")


class _Ci64Mechanisms(Protocol):
    def _prelude_transition(self, operands: AdmissionOperands) -> dict[str, bytes]: ...
    def _prelude_applicability(
        self, actual: dict[str, bytes], current: dict[str, str], family: str
    ) -> dict[str, Any]: ...
    def _producing_inputs(
        self, actual: dict[str, bytes], current: dict[str, str]
    ) -> dict[str, str]: ...

    def transition(self, operands: AdmissionOperands) -> dict[str, bytes]:
        return self._prelude_transition(operands)

    def applicability(
        self, actual: dict[str, bytes], current: dict[str, str], family: str
    ) -> dict[str, Any]:
        return self._prelude_applicability(actual, current, family)

    def producing(self, actual: dict[str, bytes], current: dict[str, str]) -> dict[str, str]:
        return self._producing_inputs(actual, current)


@pytest.fixture(scope="module")
def ci64_pure_transition_operands() -> AdmissionOperands:
    """Native E61 preimages and explicitly synthetic records test the pure proof only."""
    import json

    from tools import performance_ci60_qualification as ci60
    from tools.performance_policy import owner_hashes
    from tools.performance_preflight_successor import read_frozen_blobs

    root = Path(__file__).resolve().parents[2]
    previous = read_frozen_blobs(root, ci60.PRELUDE_BASE, sorted(ci60.PRELUDE_CONTROLS))
    frozen = dict.fromkeys(sorted(ci60.PRELUDE_MEMBERS), b"{}\n") | previous
    frozen[ci60.SELF] = (root / ci60.SELF).read_bytes()
    marker = b"\nPRELUDE_FREEZE: str | None = None"
    active = f'\nPRELUDE_FREEZE: str | None = "{ci60.PRELUDE_FREEZE}"'.encode()
    if marker not in frozen[ci60.SELF]:
        frozen[ci60.SELF] = frozen[ci60.SELF].replace(active, marker, 1)
    names = sorted(frozen)
    frozen[ci60.PRELUDE_NAMESPACE + "/changed-members.json"] = json.dumps(names).encode()
    transitions = {
        "schema": "ci64-exact-provenance-v1",
        "base": ci60.PRELUDE_BASE,
        "changes": {
            name: {
                "before_sha256": ci60.digest(previous[name]),
                "after_sha256": ci60.digest(frozen[name]),
                "edits": [{"before": previous[name].decode(), "after": frozen[name].decode()}],
            }
            for name in sorted(previous.keys() - {ci60.ASSESSMENT})
        },
    }
    frozen[ci60.PRELUDE_NAMESPACE + "/control-transitions.json"] = json.dumps(transitions).encode()
    freeze = "2" * 40
    current = frozen | {
        ci60.SELF: frozen[ci60.SELF].replace(
            marker, f'\nPRELUDE_FREEZE: str | None = "{freeze}"'.encode(), 1
        )
    }
    assessment = json.loads(frozen[ci60.ASSESSMENT])
    assessment["changes"][ci60.SELF]["after_sha256"] = ci60.digest(current[ci60.SELF])
    assessment["changes"][ci60.SELF]["owners"]["@module"]["after"] = owner_hashes(
        ci60.SELF, current[ci60.SELF]
    )["@module"]
    current[ci60.ASSESSMENT] = json.dumps(assessment).encode()
    return (
        ("next-freeze", 0, freeze.encode()),
        ("next-selection", 0, json.dumps(names).encode()),
        *((f"next-frozen/{name}", 0, raw) for name, raw in frozen.items()),
        *((f"next-previous/{name}", 0, raw) for name, raw in previous.items()),
        *((f"current/{name}", 0o100644, current[name]) for name in sorted(previous)),
        *(
            (f"next-current/{name}", 0o100644, current[name])
            for name in sorted(ci60.PRELUDE_OBSERVED)
        ),
        ("assessment-first", 0o100644, current[ci60.ASSESSMENT]),
        ("assessment-second", 0o100644, current[ci60.ASSESSMENT]),
        *((f"observed/{name}", 0o100644, current[name]) for name in sorted(previous)),
    )


def test_ci64_pure_transition_preserves_exact_native_preimages(
    ci64_pure_transition_operands: AdmissionOperands,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_ci60_qualification as ci60
    from tools import performance_ci69_members as members

    result = _Ci64Mechanisms.transition(cast(_Ci64Mechanisms, ci60), ci64_pure_transition_operands)
    assert result == {
        name.removeprefix("next-previous/"): raw
        for name, _, raw in ci64_pure_transition_operands
        if name.startswith("next-previous/")
    }

    bindings = preflight.ci60_admission_bindings()
    empty_additions: frozenset[str] = frozenset()
    with monkeypatch.context() as unused_declaration:
        unused_declaration.setattr(members, "OBSERVED_ADDITIONS", empty_additions)
        assert preflight.ci60_admission_bindings() == bindings
        assert (
            _Ci64Mechanisms.transition(cast(_Ci64Mechanisms, ci60), ci64_pure_transition_operands)
            == result
        )
        with monkeypatch.context() as actual_selector:
            actual_selector.setattr(
                ci60, "PRELUDE_OBSERVED", ci60.PRELUDE_OBSERVED | {"unreviewed-owned-input"}
            )
            assert preflight.ci60_admission_bindings() != bindings
            with pytest.raises(ValueError, match="CI64 finite source membership changed"):
                _Ci64Mechanisms.transition(
                    cast(_Ci64Mechanisms, ci60), ci64_pure_transition_operands
                )


@pytest.mark.parametrize(
    "selected",
    [
        "next-selection",
        "assessment-first",
        "assessment-second",
        "current/tools/performance_policy.py",
        "observed/tools/performance_policy.py",
        "next-previous/tools/performance_policy.py",
        "next-current/docs/CI64_PROVENANCE_SCOPE.md",
    ],
)
def test_ci64_pure_transition_rejects_changed_observations(
    ci64_pure_transition_operands: AdmissionOperands, selected: str
) -> None:
    from tools import performance_ci60_qualification as ci60

    changed = tuple(
        (name, mode, raw + b"\nchanged" if name == selected else raw)
        for name, mode, raw in ci64_pure_transition_operands
    )
    assert changed != ci64_pure_transition_operands
    with pytest.raises(ValueError, match=r"CI64|Extra data"):
        _Ci64Mechanisms.transition(cast(_Ci64Mechanisms, ci60), changed)


@pytest.mark.parametrize("mandatory", [False, 1, "yes"])
def test_ci64_pure_transition_rejects_nonboolean_mandatory_operation(
    ci64_pure_transition_operands: AdmissionOperands, mandatory: object
) -> None:
    import json

    from tools import performance_ci60_qualification as ci60

    values = {name: raw for name, _, raw in ci64_pure_transition_operands}
    mapping = json.loads(values["next-frozen/" + ci60.MAP])
    mapping["operations"]["ci64-test-addition"] = {
        "paths": ["tools/performance_policy.py"],
        "owners": ["owner_hashes"],
        "families": [],
        "mandatory": mandatory,
        "sensitive": False,
    }
    raw = json.dumps(mapping).encode()
    key = "next-frozen/" + ci60.PRELUDE_NAMESPACE + "/control-transitions.json"
    record = json.loads(values[key])
    record["changes"][ci60.MAP]["after_sha256"] = ci60.digest(raw)
    record["changes"][ci60.MAP]["edits"][0]["after"] = raw.decode()
    replacements = {
        "next-frozen/" + ci60.MAP: raw,
        "current/" + ci60.MAP: raw,
        "observed/" + ci60.MAP: raw,
        key: json.dumps(record).encode(),
        "next-current/" + ci60.PRELUDE_NAMESPACE + "/control-transitions.json": json.dumps(
            record
        ).encode(),
    }
    changed = tuple(
        (name, mode, replacements.get(name, raw))
        for name, mode, raw in ci64_pure_transition_operands
    )
    with pytest.raises(ValueError, match="finite, literal and mandatory"):
        _Ci64Mechanisms.transition(cast(_Ci64Mechanisms, ci60), changed)


@pytest.mark.parametrize(
    "changed", ["runtime", "dependency", "startup-drop", "startup-pin", "old-map"]
)
def test_activated_native_ci64_applicability_rejects_false_equivalence(changed: str) -> None:
    import json

    from tools import performance_ci60_qualification as ci60

    root = Path(__file__).resolve().parents[2]
    actual = ci60.admitted(root)
    name = ci60.PRELUDE_NAMESPACE + "/producing-inputs.json"
    proof_name = ci60.PRELUDE_NAMESPACE + "/applicability.json"
    produced = json.loads(actual[name])
    current = produced | {ci60.SELF: ci60.digest(actual[ci60.SELF])}
    stage = cast(_Ci64Mechanisms, ci60)
    original = _Ci64Mechanisms.applicability(stage, actual, current, "dice")
    assert len(original["families"]) == 11
    proof = json.loads(actual[proof_name])
    if changed == "old-map":
        previous = json.loads(actual[ci60.DERIVATION_NAMESPACE + "/producing-inputs.json"])
        with pytest.raises(ValueError, match="complete producing inputs differ"):
            _Ci64Mechanisms.producing(stage, actual, previous)
        return
    if changed in {"runtime", "dependency"}:
        path = "src/warhammer40k_core/__init__.py" if changed == "runtime" else "uv.lock"
        before = produced[path]
        produced[path] = ci60.digest(b"coordinated changed input")
        current[path] = produced[path]
        proof["current_producing_input_digest"] = ci60.canonical(produced)
        proof["changes"][path] = {"before": before, "after": produced[path]}
        proof["unchanged_inputs"].pop(path)
        actual[name] = json.dumps(produced).encode()
    elif changed == "startup-drop":
        proof["families"]["dice"]["unchanged_startup"].pop("tests/conftest.py")
    else:
        proof["families"]["dice"]["unchanged_startup"]["tests/conftest.py"] = "altered"
    actual[proof_name] = json.dumps(proof).encode()
    with pytest.raises(ValueError, match=r"applicability changed|consumer/startup proof changed"):
        _Ci64Mechanisms.applicability(stage, actual, current, "dice")


def test_activated_native_ci64_two_entry_budget_and_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_ci60_qualification as ci60
    from tools import performance_history_snapshot as history

    root = Path(__file__).resolve().parents[2]
    original = cast(
        Callable[[AdmissionOperands], dict[str, bytes]], vars(ci60)["_prelude_transition"]
    )
    calls: list[int] = []
    held: list[_Storage] = []

    def observed(operands: AdmissionOperands) -> dict[str, bytes]:
        calls.append(sum(len(raw) for _, _, raw in operands))
        return original(operands)

    monkeypatch.setattr(ci60, "_prelude_transition", observed)

    @preflight.invocation
    def run() -> None:
        calls.clear()  # Bootstrap and first active requests share one complete proof.
        with history.phase(root, ci60.PR_BASE, None):
            scope = vars(preflight)["_DIGESTS"]
            storage = cast(_Storage, scope.get())
            held.append(storage)
            bootstrap_entries = dict(storage.admissions)
            ci60.admitted(root)
            assert storage.admissions == bootstrap_entries
            assert all(
                storage.admissions[key] is not value for key, value in bootstrap_entries.items()
            )
            snapshot = vars(history)["_ACTIVE"].get()
            assert snapshot is not None
            current_operands = next(
                operands
                for key, operands in storage.admissions.items()
                if key[0].__name__ == "_current_derivation_transition"
            )
            historical = [
                (name.removeprefix("next-frozen/"), raw)
                for name, _, raw in current_operands
                if name.startswith("next-frozen/")
            ]
            assert historical
            assert all(
                raw is snapshot.contents["plain60", ci60.PRELUDE_FREEZE, name]
                for name, raw in historical
            )
            retained = storage.retained
            entries = dict(storage.admissions)
            ci60.admitted(root)
            assert len(calls) == 1
            assert calls[0] <= 128 * 1024 * 1024
            assert len(storage.admissions) == 2
            assert storage.admissions == entries
            assert storage.retained == retained <= storage.limit == 512 * 1024 * 1024
            sizes = {
                key[0].__name__: sum(len(raw) for _, _, raw in operands)
                for key, operands in entries.items()
            }
            assert sizes["_current_derivation_transition"] <= 128 * 1024 * 1024
            assert sizes["_admitted_derivation"] == 74_279_914

    run()
    assert not held[0].active
    assert held[0].retained == 0
    assert not held[0].admissions


def _ci65_storage() -> _Storage:
    scope = cast(contextvars.ContextVar[_Storage | None], vars(preflight)["_DIGESTS"])
    storage = scope.get()
    assert storage is not None
    return storage


def _ci65_validators(
    calls: list[str],
) -> tuple[AdmissionValidator, AdmissionValidator]:
    def first(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("first")
        if any(raw == b"reject" for _, _, raw in operands):
            raise ValueError("rejected complete operand")

    def second(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append("second")

    return first, second


def test_ci65_handoff_preserves_default_none_and_standalone_behavior(tmp_path: Path) -> None:
    calls: list[str] = []
    validators = _ci65_validators(calls)
    operands: AdmissionOperands = (("source", 0o100644, b"same"),)

    def acquire() -> str:
        for validator in validators:
            preflight.admission_proof(validator, operands, None, (), repository=tmp_path)
        return "cohort"

    with preflight.ci60_bootstrap_admission(tmp_path, validators, acquire) as result:
        assert result == "cohort"
        with preflight.ci60_phase_admission(tmp_path, None):
            acquire()
    assert calls == ["first", "second", "first", "second"]

    @preflight.invocation
    def no_opt_in() -> None:
        acquire()
        acquire()
        assert _ci65_storage().admissions == {}

    calls.clear()
    no_opt_in()
    assert calls == ["first", "second", "first", "second"]


def test_ci65_handoff_promotes_once_and_revokes_at_phase_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_history_snapshot as history

    phase: list[tuple[str, ...] | None] = [None]

    def current_identity(root: Path) -> tuple[str, ...] | None:
        return phase[0]

    monkeypatch.setattr(history, "proof_identity", current_identity)
    calls: list[str] = []
    validators = _ci65_validators(calls)
    operands: AdmissionOperands = (("source", 0o100644, b"same"),)
    held: list[_Storage] = []

    def acquire() -> str:
        for validator in validators:
            preflight.admission_proof(validator, operands, None, (), repository=tmp_path)
        return "cohort"

    @preflight.invocation
    def run() -> None:
        storage = _ci65_storage()
        held.append(storage)
        with preflight.ci60_bootstrap_admission(tmp_path, validators, acquire):
            assert len(storage.admissions) == 2
            retained = storage.retained
            assert calls == ["first", "second"]
            phase[0] = ("repository", "phase-one")
            with preflight.ci60_phase_admission(tmp_path, phase[0]):
                for validator in validators:
                    preflight.admission_proof(
                        validator, operands, phase[0], (), repository=tmp_path
                    )
                assert calls == ["first", "second"]
                assert storage.retained == retained
                assert len(storage.admissions) == 2
            assert storage.admissions == {}
            assert storage.retained == 0
            phase[0] = None
            acquire()
            assert calls == ["first", "second", "first", "second"]
            assert storage.admissions == {}
            phase[0] = ("repository", "phase-two")
            with preflight.ci60_phase_admission(tmp_path, phase[0]):
                for validator in validators:
                    preflight.admission_proof(
                        validator, operands, phase[0], (), repository=tmp_path
                    )
            assert calls == ["first", "second"] * 3

    run()
    assert held[0].active is False
    assert held[0].admissions == {}
    assert held[0].retained == 0


@pytest.mark.parametrize("change", ["bytes", "mode", "order", "multiplicity", "dependency"])
def test_ci65_handoff_first_active_use_compares_every_operand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from tools import performance_history_snapshot as history

    def current_identity(root: Path) -> tuple[str, ...] | None:
        return IDENTITY

    monkeypatch.setattr(history, "proof_identity", current_identity)
    calls: list[str] = []
    validators = _ci65_validators(calls)
    original: AdmissionOperands = (("a", 0o100644, b"a"), ("b", 0o100644, b"b"))
    changed = original
    dependencies: tuple[Callable[..., Any], ...] = ()
    if change == "bytes":
        changed = (("a", 0o100644, b"changed"), original[1])
    elif change == "mode":
        changed = (("a", 0o100755, b"a"), original[1])
    elif change == "order":
        changed = tuple(reversed(original))
    elif change == "multiplicity":
        changed = (*original, original[0])
    else:
        dependencies = (bytes,)

    def acquire() -> None:
        for validator in validators:
            preflight.admission_proof(validator, original, None, (), repository=tmp_path)

    @preflight.invocation
    def run() -> None:
        with (
            preflight.ci60_bootstrap_admission(tmp_path, validators, acquire),
            preflight.ci60_phase_admission(tmp_path, IDENTITY),
        ):
            preflight.admission_proof(
                validators[0], changed, IDENTITY, dependencies, repository=tmp_path
            )
            preflight.admission_proof(validators[1], original, IDENTITY, (), repository=tmp_path)
        assert calls == ["first", "second", "first"]

    run()


@pytest.mark.parametrize("stage", ["bootstrap", "catalog", "seal", "activation", "body", "cancel"])
def test_ci65_handoff_revokes_pending_and_promoted_on_every_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    from tools import performance_history_snapshot as history

    def current_identity(root: Path) -> tuple[str, ...] | None:
        return IDENTITY

    monkeypatch.setattr(history, "proof_identity", current_identity)
    calls: list[str] = []
    validators = _ci65_validators(calls)
    operands: AdmissionOperands = (("source", 0o100644, b"same"),)
    copied: list[contextvars.Context] = []

    def acquire() -> None:
        for validator in validators:
            preflight.admission_proof(validator, operands, None, (), repository=tmp_path)
        copied.append(contextvars.copy_context())
        if stage == "bootstrap":
            raise RuntimeError("bootstrap failure")

    @preflight.invocation
    def run() -> None:
        storage = _ci65_storage()

        def fail_in_scope() -> None:
            with preflight.ci60_bootstrap_admission(tmp_path, validators, acquire):
                if stage in {"catalog", "seal", "activation"}:
                    raise RuntimeError(stage + " failure")
                with preflight.ci60_phase_admission(tmp_path, IDENTITY):
                    if stage == "cancel":
                        raise KeyboardInterrupt
                    raise RuntimeError("body failure")

        with pytest.raises((RuntimeError, KeyboardInterrupt)):
            fail_in_scope()
        assert storage.admissions == {}
        assert storage.retained == 0

    run()
    count = len(calls)
    copied[0].run(preflight.admission_proof, validators[0], operands, None, (), repository=tmp_path)
    assert len(calls) == count + 1


@pytest.mark.parametrize("identity", [None, ("forged",), IDENTITY])
def test_ci65_handoff_requires_actual_live_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, identity: tuple[str, ...] | None
) -> None:
    from tools import performance_history_snapshot as history

    def current_identity(root: Path) -> tuple[str, ...] | None:
        return None

    monkeypatch.setattr(history, "proof_identity", current_identity)
    calls: list[str] = []
    validators = _ci65_validators(calls)

    @preflight.invocation
    def run() -> None:
        with (
            preflight.ci60_bootstrap_admission(tmp_path, validators, lambda: None),
            pytest.raises(ValueError, match="authenticated history phase"),
            preflight.ci60_phase_admission(tmp_path, identity),
        ):
            raise AssertionError("Unauthenticated phase must never enter.")

    run()
    assert calls == []


@pytest.mark.parametrize("owner_change", ["thread", "pid", "repository"])
def test_ci65_handoff_rejects_other_owner_or_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner_change: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    calls: list[str] = []
    validators = _ci65_validators(calls)
    operands: AdmissionOperands = (("source", 0o100644, b"same"),)
    other = tmp_path / "other"
    other.mkdir()

    def request() -> None:
        preflight.admission_proof(
            validators[0],
            operands,
            None,
            (),
            repository=other if owner_change == "repository" else tmp_path,
        )

    def acquire() -> None:
        if owner_change == "thread":
            copied = contextvars.copy_context()
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(copied.run, request).result()
        elif owner_change == "pid":
            pid = os.getpid()
            with monkeypatch.context() as scope:
                scope.setattr(os, "getpid", lambda: pid + 1)
                request()
        else:
            request()

    @preflight.invocation
    def run() -> None:
        with (
            pytest.raises(ValueError, match=r"another owner|another repository"),
            preflight.ci60_bootstrap_admission(tmp_path, validators, acquire),
        ):
            raise AssertionError("Wrong owner must never publish bootstrap.")
        assert _ci65_storage().admissions == {}

    run()
    assert calls == []


@pytest.mark.parametrize("limit", [0, 3, 100])
def test_ci65_handoff_obeys_shared_budget_and_uncached_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    from tools import performance_history_snapshot as history

    def current_identity(root: Path) -> tuple[str, ...] | None:
        return IDENTITY

    monkeypatch.setattr(history, "proof_identity", current_identity)
    calls: list[str] = []
    validators = _ci65_validators(calls)
    operands: AdmissionOperands = (("source", 0o100644, b"same"),)

    def acquire() -> None:
        for validator in validators:
            preflight.admission_proof(validator, operands, None, (), repository=tmp_path)

    @preflight.invocation
    def run() -> None:
        storage = _ci65_storage()
        storage.limit = limit
        with preflight.ci60_bootstrap_admission(tmp_path, validators, acquire):
            assert storage.retained <= limit
            with preflight.ci60_phase_admission(tmp_path, IDENTITY):
                for validator in validators:
                    preflight.admission_proof(
                        validator, operands, IDENTITY, (), repository=tmp_path
                    )
                assert storage.retained <= limit
                assert len(storage.admissions) <= 2
        assert storage.retained == 0

    run()
    assert calls == ["first", "second"] * (1 if limit >= 8 else 2)


@pytest.mark.parametrize("stage", ["catalog", "seal", "activation"])
def test_activated_native_ci65_acquisition_failure_revokes_pending(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    """The current admitted cohort must revoke bootstrap entries before publication."""
    from tools import performance_ci60_qualification as ci60
    from tools import performance_history_snapshot as history

    root = Path(__file__).resolve().parents[2]
    held: list[_Storage] = []
    copied: list[contextvars.Context] = []
    other_retained: list[int] = []

    def fail(*args: object, **kwargs: object) -> Any:
        storage = _ci65_storage()
        assert len(storage.admissions) == 2
        other_retained.append(
            storage.retained
            - sum(len(raw) for operands in storage.admissions.values() for _, _, raw in operands)
        )
        held.append(storage)
        copied.append(contextvars.copy_context())
        raise RuntimeError("ci65 acquisition failure: " + stage)

    target = {"catalog": "_catalog", "seal": "_seal", "activation": "_activate"}[stage]
    monkeypatch.setattr(history, target, fail)

    @preflight.invocation
    def run() -> None:
        with (
            pytest.raises(RuntimeError, match="ci65 acquisition failure"),
            history.phase(root, ci60.PR_BASE, None),
        ):
            raise AssertionError("Failed acquisition must never publish.")
        assert history.proof_identity(root) is None
        assert held[0].admissions == {}
        assert held[0].retained == other_retained[0]

    run()
    assert not held[0].active
    assert copied[0].run(history.proof_identity, root) is None


def test_ci66_equal_admission_refreshes_references_without_new_proof_or_charge() -> None:
    storage = _Mechanisms.storage(_mechanisms, 1024)
    calls: list[AdmissionOperands] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(operands)
        if operands[0][2] == b"changed":
            raise ValueError("changed bytes")

    first: AdmissionOperands = (("member", 0o100644, bytes(bytearray(b"equal"))),)
    latest: AdmissionOperands = (("member", 0o100644, bytes(bytearray(b"equal"))),)
    assert first == latest
    assert first is not latest
    assert first[0][2] is not latest[0][2]
    key = check, IDENTITY, ()
    storage.admission(check, first, IDENTITY, ())
    charge = storage.retained
    storage.admission(check, latest, IDENTITY, ())
    assert storage.admissions[key] is latest
    assert storage.retained == charge == 5
    assert calls == [first]
    third: AdmissionOperands = (("member", 0o100644, latest[0][2]),)
    storage.admission(check, third, IDENTITY, ())
    assert storage.admissions[key] is third
    assert storage.admissions[key][0][2] is latest[0][2]
    assert storage.retained == charge
    assert calls == [first]
    with pytest.raises(ValueError, match="changed bytes"):
        storage.admission(check, (("member", 0o100644, b"changed"),), IDENTITY, ())
    assert key not in storage.admissions
    assert storage.retained == 0
    assert len(calls) == 2


@pytest.mark.parametrize("changed", ["mode", "order", "multiplicity", "dependency", "phase"])
def test_ci66_refreshed_admission_still_checks_every_operand_and_key(changed: str) -> None:
    storage = _Mechanisms.storage(_mechanisms, 1024)
    calls: list[AdmissionOperands] = []

    def check(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
        calls.append(operands)

    first: AdmissionOperands = (("a", 1, b"a"), ("b", 2, b"b"))
    latest: AdmissionOperands = tuple((n, m, bytes(bytearray(raw))) for n, m, raw in first)
    storage.admission(check, first, IDENTITY, ())
    storage.admission(check, latest, IDENTITY, ())
    assert storage.admissions[check, IDENTITY, ()] is latest
    altered = latest
    identity = IDENTITY
    dependencies: tuple[Callable[..., Any], ...] = ()
    if changed == "mode":
        altered = (("a", 2, b"a"), latest[1])
    elif changed == "order":
        altered = tuple(reversed(latest))
    elif changed == "multiplicity":
        altered = (latest[0], latest[0])
    elif changed == "dependency":
        dependencies = (str,)
    else:
        identity = (*IDENTITY[:-1], "second-phase")
    storage.admission(check, altered, identity, dependencies)
    assert len(calls) == 2


def test_benchmark_shooting_api_preserves_native_current_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import measurement_native_api as api
    from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState

    phase = ShootingPhaseState(battle_round=1, active_player_id="player-a")
    expected = phase.with_attack_sequence_update(
        attack_sequence=None, allocated_model_ids_this_phase=(), pending_decision_requests=()
    )
    api.benchmark_shooting_method.cache_clear()
    try:
        with monkeypatch.context() as scoped:
            scoped.delenv(api.BENCHMARK_SHOOTING_API_ENV, raising=False)
            ordinary = api.benchmark_shooting_update(
                phase,
                attack_sequence=None,
                allocated_model_ids_this_phase=(),
                pending_decision_requests=(),
            )
            scoped.setenv(api.BENCHMARK_SHOOTING_API_ENV, "head-current")
            scoped.setenv(
                api.BENCHMARK_NATIVE_SRC_ENV, str(Path(__file__).resolve().parents[2] / "src")
            )
            head = api.benchmark_shooting_update(
                phase,
                attack_sequence=None,
                allocated_model_ids_this_phase=(),
                pending_decision_requests=(),
            )
        assert ordinary == expected
        assert head == expected
    finally:
        api.benchmark_shooting_method.cache_clear()


def test_benchmark_shooting_api_rejects_unknown_mode_or_native_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import measurement_native_api as api
    from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState

    phase = ShootingPhaseState(battle_round=1, active_player_id="player-a")
    api.benchmark_shooting_method.cache_clear()
    try:
        with monkeypatch.context() as scoped:
            scoped.setenv(
                api.BENCHMARK_NATIVE_SRC_ENV, str(Path(__file__).resolve().parents[2] / "src")
            )
            for role in ("unknown", "base-5f509724"):
                scoped.setenv(api.BENCHMARK_SHOOTING_API_ENV, role)
                with pytest.raises(ValueError, match="Unknown benchmark"):
                    api.benchmark_shooting_update(
                        phase,
                        attack_sequence=None,
                        allocated_model_ids_this_phase=(),
                        pending_decision_requests=(),
                    )
    finally:
        api.benchmark_shooting_method.cache_clear()


@pytest.mark.stubbed
def test_benchmark_shooting_api_rejects_unknown_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inspect import Signature

    from tests import measurement_native_api as api

    api.benchmark_shooting_method.cache_clear()
    try:
        with monkeypatch.context() as scoped:

            def changed_signature(_method: object) -> Signature:
                return Signature()

            scoped.setattr(api, "signature", changed_signature)
            with pytest.raises(ValueError, match="Unknown benchmark native Shooting"):
                api.benchmark_shooting_method(
                    "head-current", str(Path(__file__).resolve().parents[2] / "src")
                )
    finally:
        api.benchmark_shooting_method.cache_clear()
