"""Tiny synthetic controls; never imports or executes Warhammer runtime targets."""

from __future__ import annotations

import contextlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
import restore_internal_campaign as campaign
import restore_internal_plugin as plugin


class HarnessControls(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ["RESTORE_SYNTHETIC_ROOT"]).resolve()
        self.directory = Path(tempfile.mkdtemp(prefix="synthetic-", dir=parent))
        assert self.directory.resolve().is_relative_to(parent)
        assert not plugin._originals
        plugin._stack.clear()
        plugin._rows.clear()
        plugin._edges.clear()
        plugin._reports.clear()
        plugin._phase_spans.clear()
        plugin._targets.clear()
        plugin._telemetry_failures.clear()
        plugin._phase = "call"
        plugin._output = self.directory
        plugin._mode = "internal"
        plugin._thread = threading.get_ident()
        plugin._last_write = time.monotonic()
        plugin._max_depth = 0

    def tearDown(self):
        plugin.restore_originals()
        assert not plugin._stack
        assert not any(name.startswith("warhammer40k_core") for name in sys.modules)

    def install(self, owner, name, label="toy", purpose=None):
        original = inspect.getattr_static(owner, name)
        plugin.install(owner, name, original, label, purpose)
        return original

    def test_periodic_write_failure_preserves_original_outcomes(self):
        for io_method in ("write_text", "replace"):
            for raises in (False, True):
                with self.subTest(io_method=io_method, raises=raises):
                    value = object()
                    original_error = ValueError("original domain failure")

                    def act(raises=raises, original_error=original_error, value=value):
                        if raises:
                            raise original_error
                        return value

                    owner = types.SimpleNamespace(act=act)
                    self.install(owner, "act")
                    plugin._last_write = time.monotonic() - 31
                    with patch.object(
                        Path, io_method, side_effect=OSError("synthetic disk failure")
                    ):
                        if raises:
                            with pytest.raises(
                                ValueError, match="original domain failure"
                            ) as caught:
                                owner.act()
                            assert caught.value is original_error
                        else:
                            assert owner.act() is value
                    assert plugin._telemetry_failures[-1]["message"] == "synthetic disk failure"
                    plugin._reports[:] = [
                        {"nodeid": plugin.NODE, "when": phase, "outcome": "passed"}
                        for phase in ("setup", "call", "teardown")
                    ]
                    session = types.SimpleNamespace(exitstatus=0)
                    plugin.pytest_sessionfinish(session, 0)
                    receipt = json.loads((self.directory / "attribution.json").read_bytes())
                    assert not receipt["complete"]
                    assert receipt["telemetry_failures"]
                    assert session.exitstatus == pytest.ExitCode.INTERNAL_ERROR
                    plugin._telemetry_failures.clear()

    def test_source_verification_consumes_admission_margin(self):
        budget = [670.0]

        def verification(*args):
            budget[0] -= 12

        with (
            patch.object(campaign, "check_sources", side_effect=verification),
            pytest.raises(RuntimeError, match="post-verification admission"),
        ):
            campaign.verify_for_launch(None, None, None, lambda: budget[0])
        assert budget[0] == 658

    def test_final_source_verification_cannot_cross_success_deadline(self):
        budget = [10.0]

        def verification(*args):
            budget[0] -= 12

        receipts = [{"passed": True}, {"passed": True}]
        assert campaign.completion_status(receipts, lambda: 100)
        assert not campaign.completion_status(receipts, lambda: -1)
        assert not campaign.completion_status(receipts, lambda: 4)
        with (
            patch.object(campaign, "check_sources", side_effect=verification),
            pytest.raises(RuntimeError, match="source post-check"),
        ):
            campaign.verify_after_invocation(None, None, None, lambda: budget[0])
        assert not campaign.completion_status(receipts, lambda: budget[0])

    def test_terminal_io_crossing_deadline_cannot_retain_success(self):
        budget = [6.0]
        observed = []

        def slow_write(_path, value):
            observed.append(dict(value))
            budget[0] -= 7

        with patch.object(campaign, "write", side_effect=slow_write):
            complete = campaign.publish_terminal(
                self.directory / "terminal.json", {"complete": True}, lambda: budget[0]
            )
        assert not complete
        assert observed[0]["complete"]
        assert not observed[-1]["complete"]
        assert observed[-1]["deadline_exhausted"]

    def test_ample_budget_admission_still_passes(self):
        with patch.object(campaign, "check_sources") as verification:
            campaign.verify_for_launch(None, None, None, lambda: 1000)
        verification.assert_called_once()
        campaign.require_budget(lambda: 1000, 665, "child launch")

    def test_classmethod_argument_result_and_descriptor_identity(self):
        class Toy:
            @classmethod
            def act(cls, value, *, other):
                assert cls is Toy
                assert value is other
                return value

        original = self.install(Toy, "act")
        value = object()
        assert Toy.act(value, other=value) is value
        plugin.restore_originals()
        assert inspect.getattr_static(Toy, "act") is original

    def test_staticmethod_identity(self):
        class Toy:
            @staticmethod
            def act(value):
                return value

        original = self.install(Toy, "act")
        value = object()
        assert Toy.act(value) is value
        plugin.restore_originals()
        assert inspect.getattr_static(Toy, "act") is original

    def test_module_function_exception_is_unchanged(self):
        error = ValueError("synthetic original error")

        def act():
            raise error

        owner = types.SimpleNamespace(act=act)
        self.install(owner, "act")
        with pytest.raises(ValueError, match="synthetic original error") as caught:
            owner.act()
        assert caught.value is error
        assert next(iter(plugin._rows.values()))["raised_calls"] == 1

    def test_nested_restore_exclusive_and_purpose(self):
        child = types.SimpleNamespace(act=lambda value: value)
        parent = types.SimpleNamespace(act=lambda value: child.act(value))
        self.install(child, "act", "restore", "historical_root")
        self.install(parent, "act", "restore", "checkpoint")
        value = object()
        assert parent.act(value) is value
        rows = {row["restore_depth"]: row for row in plugin._rows.values()}
        assert set(rows) == {1, 2}
        assert rows[1]["purpose"] == "checkpoint"
        assert rows[2]["purpose"] == "historical_root"
        assert rows[1]["inclusive_wall"] - rows[2]["inclusive_wall"] == pytest.approx(
            rows[1]["exclusive_wall"], abs=1e-12
        )
        assert rows[1]["exclusive_wall"] >= 0
        assert plugin._max_depth == 2

    def test_phase_restores_after_exception(self):
        def fail_in_phase():
            with contextlib.contextmanager(plugin.phase_span)("setup"):
                assert plugin._phase == "setup"
                raise ValueError("phase")

        with pytest.raises(ValueError, match="phase"):
            fail_in_phase()
        assert plugin._phase == "call"
        assert "setup" in plugin._phase_spans

    def test_wrong_node_fails_before_running(self):
        session = types.SimpleNamespace(items=[types.SimpleNamespace(nodeid="wrong")])
        with pytest.raises(pytest.UsageError):
            plugin.pytest_collection_finish(session)

    def test_wrong_output_rejects_before_runtime_import(self):
        options = {"--restore-mode": "internal", "--restore-output": str(self.directory / "wrong")}
        session = types.SimpleNamespace(config=types.SimpleNamespace(getoption=options.__getitem__))
        with (
            patch.dict(os.environ, {"RESTORE_OUTPUT_ROOT": str(self.directory)}),
            pytest.raises(pytest.UsageError),
        ):
            plugin.pytest_sessionstart(session)

    def test_command_rejects_wrong_mode_and_inside_checkout(self):
        root = self.directory / "checkout"
        with pytest.raises(ValueError, match="Only declared diagnostic modes"):
            campaign.command(root, self.directory / "other", "other")
        with pytest.raises(ValueError, match="Absolute external output"):
            campaign.command(root, root / "internal", "internal")
        with pytest.raises(ValueError, match="Absolute external output"):
            campaign.command(Path("relative"), self.directory / "internal", "internal")

    def test_external_descriptor_drift_restores_then_fails(self):
        owner = types.SimpleNamespace(act=lambda: 1)
        original = self.install(owner, "act")
        owner.act = lambda: 2
        with pytest.raises(RuntimeError, match="descriptors changed"):
            plugin.restore_originals()
        assert owner.act is original

    def test_partial_receipt_cannot_claim_complete(self):
        plugin.write_receipt()
        import json

        receipt = json.loads((self.directory / "attribution.json").read_bytes())
        assert not receipt["complete"]
        assert receipt["exitstatus"] is None

    def test_manifest_digest_and_frozen_revision_rejection(self):
        path = self.directory / "manifest.json"
        path.write_text(json.dumps({"head": campaign.HEAD, "tree": campaign.TREE}))
        with pytest.raises(ValueError, match="reviewed binding"):
            campaign.read_manifest(path, "0" * 64)
        assert campaign.read_manifest(path, campaign.digest(path))["head"] == campaign.HEAD
        path.write_text(json.dumps({"head": "wrong", "tree": campaign.TREE}))
        with pytest.raises(ValueError, match="implementation differs"):
            campaign.read_manifest(path, campaign.digest(path))

    def test_source_blob_check_rejects_git_hidden_worktree_drift(self):
        root = self.directory / "toy-repo"
        root.mkdir()
        value = root / "input.txt"
        value.write_bytes(b"original\n")

        def git(*args):
            return subprocess.check_output(["git", "-C", str(root), *args])

        git("init", "-q")
        git("add", "input.txt")
        git(
            "-c",
            "user.name=Synthetic control",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "synthetic only",
        )
        head = git("rev-parse", "HEAD").decode().strip()
        tree = git("rev-parse", "HEAD^{tree}").decode().strip()
        blob = git("rev-parse", "HEAD:input.txt").decode().strip()
        manifest = {"source": {"input.txt": blob}, "harness": {}}
        with patch.object(campaign, "HEAD", head), patch.object(campaign, "TREE", tree):
            campaign.check_sources(root, self.directory, manifest)
            git("update-index", "--assume-unchanged", "input.txt")
            value.write_bytes(b"changed but status concealed\n")
            assert git("status", "--porcelain") == b""
            with pytest.raises(ValueError, match="Source bytes drifted"):
                campaign.check_sources(root, self.directory, manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
