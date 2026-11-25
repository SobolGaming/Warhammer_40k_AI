"""CLI controls for a missing or modified external Stage 2 archive."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("corrupt", "diagnostic"),
    [(False, "decline-targets-checkpoint.json"), (True, "Raw receipt SHA-256 mismatch")],
)
def test_rejects_unverified_archive_without_summary(
    tmp_path: Path, corrupt: bool, diagnostic: str
) -> None:
    if corrupt:
        first_receipt = tmp_path / "stage2-b3-closeout-evidence" / "decline-targets-checkpoint.json"
        first_receipt.parent.mkdir()
        first_receipt.write_bytes(b"{}\n")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "scripts.verify_stage2_b3_post_roll_receipts",
            "--receipts",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert diagnostic in result.stderr
