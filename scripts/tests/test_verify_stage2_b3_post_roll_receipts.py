"""CLI controls for unverified Stage 2 archive summaries."""

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from scripts import verify_stage2_b3_post_roll_receipts as verifier


@pytest.mark.parametrize(
    ("corrupt", "diagnostic"),
    [(False, "decline-targets-checkpoint.json"), (True, "Raw receipt SHA-256 mismatch")],
)
@pytest.mark.parametrize("preservation", [False, True])
def test_rejects_unverified_archive_without_summary(
    tmp_path: Path,
    corrupt: bool,
    diagnostic: str,
    preservation: bool,
) -> None:
    first_name = (
        "producer.txt"
        if preservation
        else ("stage2-b3-closeout-evidence/decline-targets-checkpoint.json")
    )
    if corrupt:
        first_receipt = tmp_path / first_name
        first_receipt.parent.mkdir(exist_ok=True)
        first_receipt.write_bytes(b"{}\n")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "scripts.verify_stage2_b3_post_roll_receipts",
            "--receipts",
            str(tmp_path),
            *(["--preservation"] if preservation else []),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert (first_name if not corrupt else diagnostic) in result.stderr


def test_rejects_fabricated_generated_authored_pair_without_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_name = f"{verifier.GENERATED}/result.json"
    raw_path = tmp_path / raw_name
    raw_path.parent.mkdir()
    raw = b'{"qualifying_pair": null}'
    raw_path.write_bytes(raw)

    fixture = json.loads(verifier.FIXTURE.read_bytes())
    fixture["raw_sha256"] = {raw_name: sha256(raw).hexdigest()}
    campaign = fixture["generated_campaign"]
    campaign["qualifying_landed_pair"] = {
        "generated_candidate_id": campaign["candidate_id"],
        "authored_checkpoint": fixture["authored_landed_reference"]["checkpoint"],
    }
    forged = tmp_path / "forged-fixture.json"
    forged.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr(verifier, "FIXTURE", forged)
    monkeypatch.setattr(sys, "argv", ["verify", "--receipts", str(tmp_path)])

    assert verifier.main() == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Qualifying generated landed pair differs from the authenticated source" in output.err
