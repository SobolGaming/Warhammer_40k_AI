"""Reproduce the reviewed October layout extraction from both immutable PDFs.

Run with Python 3.12 and tools/event_companion_layout_source/requirements.txt.
This development-only workflow never imports or mutates the rules engine.
Only the exact reviewed July/October documents are admitted. Project continuity
IDs and physical shape models remain explicit reviewed inputs, not GW labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data/source_audits/event_companion_2026_10"
PDF_NAME = "eng_14-10_wh40k_event_companion-rdwnqprl4c-nj8oqogadv.pdf"
SOURCE_INPUTS = {
    "docs/source_rules/eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf": (
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
    ),
    "docs/source_rules/"
    + PDF_NAME: "187253a9b6ea377f5e44d1148454bd042b165b03bb5c45c51a5880762bf56dc2",
    (
        "data/source_audits/event_companion_2026_06/phase17n_event_companion_ba"
        "ttlefields_pages_9_53_extraction.json"
    ): ("a3e9392adeb52696902a016e3c3529933d1e99f3bfd67069d607410d8e1c137f"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, expected in SOURCE_INPUTS.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Reviewed source input drifted: {name}")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "EVENT_LAYOUT_AUDIT_WORK_DIR": str(work)}
    for script in ("observe.py", "correspond.py", "contacts.py", "extract.py"):
        subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/event_companion_layout_source" / script)],
            env=env,
            check=True,
        )
    candidate = json.loads((work / "october-extraction-candidate.json").read_text())
    candidate["source"].update(
        pdf_filename=PDF_NAME,
        repo_relative_pdf_path="docs/source_rules/" + PDF_NAME,
    )
    candidate["source"]["official_index_observation"] = json.loads(
        (SOURCE_DIR / "official-source-observation.json").read_text()
    )
    candidate["global_audits"]["validation_status"] = "passed"
    candidate["global_audits"]["validation_scope"] = (
        "Independently checked current raw vectors/images/markers/roles/contacts and "
        "board/regions on all45pages; runtime qualification is separate."
    )
    raw = (json.dumps(candidate, indent=2) + "\n").encode()
    output = work / "event_companion_layouts_pages_8_53.json"
    output.write_bytes(raw)
    if args.check and raw != (SOURCE_DIR / output.name).read_bytes():
        raise ValueError("Current reviewed layout extraction differs from raw-source reproduction.")
    print(f"Source extraction {'verified' if args.check else 'written'}: {output}")


if __name__ == "__main__":
    main()
