"""Cheap exact-argv/output-guard regression checks; no engine import or child launch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ci_attribution as campaign
import ci_attribution_profile as profile


class CapturedLaunch(RuntimeError):
    """Stop before subprocess creation after checking the real invoke path."""


def check(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Command regression checks require enabled assertions")
    repository = Path(__file__).resolve().parents[1]
    output = output.resolve()
    if output.is_relative_to(repository):
        raise ValueError("Check evidence must be outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    files = [repository / name for name in campaign.ADDITIONS]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    rows = []
    declared = [
        ("critical", "control", 900, campaign.CRITICAL),
        ("critical", "boundaries", 1200, campaign.CRITICAL),
        ("quality", "control", 420, campaign.QUALITY),
        ("quality", "profile", 900, campaign.QUALITY),
    ]
    assert list(campaign.RUNS) == [row[:3] for row in declared]
    resource_stub = SimpleNamespace(
        RUSAGE_CHILDREN=0,
        getrusage=lambda _kind: SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=0),
    )
    for sample, mode, cap, node in declared:
        directory = output / f"{sample}-{mode}"
        pytest_args = [
            "-p",
            "scripts.ci_attribution_plugin",
            node,
            "-q",
            "-n",
            "0",
            "--basetemp",
            str(directory / "tmp"),
            "-o",
            f"cache_dir={directory / 'cache'}",
            f"--junitxml={directory / 'junit.xml'}",
        ]
        pytest_args += (
            ["--cov=warhammer40k_core", "--cov-branch", "--cov-report=", "--cov-fail-under=0"]
            if sample == "critical"
            else ["--no-cov"]
        )
        prefix = (
            [
                sys.executable,
                "scripts/ci_attribution_profile.py",
                str(directory / "pytest.prof"),
                "pytest",
            ]
            if mode == "profile"
            else [sys.executable, "-m", "pytest"]
        )
        expected = [*prefix, *pytest_args]
        assert campaign.build_command(sample, mode, directory) == expected

        def capture(
            command, expected=expected, cap=cap, node=node, directory=directory, mode=mode, **kwargs
        ):
            assert command == expected
            assert kwargs["timeout"] == cap
            env = kwargs["env"]
            assert env["ATTRIBUTION_NODEID"] == node
            assert env["ATTRIBUTION_RUN_OUTPUT"] == str(directory)
            assert env["ATTRIBUTION_BOUNDARIES"] == str(int(mode == "boundaries"))
            assert env["ATTRIBUTION_CHILD_PROFILES"] == str(int(mode == "profile"))
            assert env["COVERAGE_FILE"] == str(directory / ".coverage")
            raise CapturedLaunch("No process was launched")

        with (
            patch.dict(sys.modules, {"resource": resource_stub}),
            patch.object(campaign, "run_owned", capture),
        ):
            try:
                campaign.invoke(sample, mode, cap, output)
            except CapturedLaunch:
                rows.append(
                    {
                        "sample": sample,
                        "mode": mode,
                        "argv": expected,
                        "actual_invoke_captured": True,
                        "no_child_launched": True,
                    }
                )
            else:
                raise AssertionError("Invocation bypassed the capturing launcher")

    with patch.dict(os.environ, {"ATTRIBUTION_RUN_OUTPUT": str(output)}):
        valid = [str(output / "allowed.prof"), "pytest", "--version"]
        assert profile.validate_request(valid) == (output / "allowed.prof", "pytest", ["--version"])
        generator = str(repository / "scripts/build_external_contract.py")
        assert profile.validate_request([str(output / "generator.prof"), generator, "--check"])[
            1:
        ] == (generator, ["--check"])
        protected = repository / "scripts/ci_attribution_supervisor.py"
        rejected = [
            [
                str(protected),
                str(repository / "scripts/check_ci_attribution_supervisor.py"),
                str(output / "pytest.prof"),
                "pytest",
            ],  # Exact R2 positional failure.
            [str(repository / "tracked.prof"), "pytest"],
            [str(output.parent / "wrong-run.prof"), "pytest"],
            [str(output / "wrong.py"), "pytest"],
            [str(output / "wrong-target.prof"), str(protected)],
            [],
        ]
        (output / "existing.prof").write_bytes(b"preserve existing profile")
        rejected.append([str(output / "existing.prof"), "pytest"])
        (output / "existing-status.status.json").write_text("preserve status", encoding="utf-8")
        rejected.append([str(output / "existing-status.prof"), "pytest"])
        for argv in rejected:
            with (
                patch.object(sys, "argv", ["ci_attribution_profile.py", *argv]),
                patch.object(
                    profile.cProfile,
                    "Profile",
                    side_effect=AssertionError("Profiler must not start"),
                ),
            ):
                try:
                    profile.main()
                except ValueError:
                    continue
                raise AssertionError(f"Unsafe request was accepted: {argv}")
        assert (output / "existing.prof").read_bytes() == b"preserve existing profile"
        assert (output / "existing-status.status.json").read_text() == "preserve status"
    try:
        campaign.build_command("quality", "profile", repository / "scripts")
    except ValueError:
        builder_rejected_checkout = True
    else:
        raise AssertionError("Builder accepted checkout output")
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert before == after, "A command check changed proposed repository source"
    (output / "results.json").write_text(
        json.dumps(
            {
                "passed": True,
                "invocations": rows,
                "rejected_profile_requests": len(rejected),
                "builder_rejected_checkout": builder_rejected_checkout,
                "source_hashes_before": before,
                "source_hashes_after": after,
                "environment": {
                    "platform": platform.platform(),
                    "python": sys.version,
                    "logical_cpus": os.cpu_count(),
                    "workers": 0,
                    "processes": "one checker; zero diagnostic child processes",
                    "coverage": False,
                    "cache": "not a runtime workload; no engine/application cache",
                    "measurement": "functional argv/path checks with intercepted launcher",
                    "hardware": "local metadata only; no Linux performance inference",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    check(parser.parse_args().output)
