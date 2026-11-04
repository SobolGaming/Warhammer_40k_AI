"""Reproduce the separately pinned complete observations for three keyword corrections."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
D = ROOT / "data/source_audits/daemons_next_three_2026_11"


def raw(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build() -> bytes:
    observed = (D / "reviewed-observation.json").read_bytes()
    if sha(observed) != "e550211684cf4104f39dacecffd11ec5b3a9a691894eee49ecaab2972f213a2c":
        raise ValueError("Three-keyword reviewed observation drifted.")
    observation = json.loads(observed)
    captures = observation["captures"]
    template = (P / "daemons_native_2026_11.audit.json").read_bytes()
    assert sha(template) == "c5520d359da6f3732765803fea9258fb50d3726cce49392b9f85411aa0e18940"
    audit = json.loads(template)
    rows = []
    for slug, title, roles in (
        (
            "flesh-hounds",
            "Flesh Hounds",
            [
                ("Gore Hound", "Gore Hound 60 x 35.5mm Oval Base"),
                ("Flesh Hound", "Flesh Hound 60 x 35.5mm Oval Base"),
            ],
        ),
        ("lord-of-change", "Lord of Change", [("Lord of Change", "Lord of Change 100mm")]),
        (
            "plaguebearers",
            "Plaguebearers",
            [("Plagueridden", "Plagueridden 32mm"), ("Plaguebearer", "Plaguebearer 32mm")],
        ),
    ):
        c = captures[slug + "-current"]
        row = copy.deepcopy(audit["observations"][0])
        text = c["text"]
        start = title + "\nDATASHEET"
        operative = text[text.index(start) :]
        assert all(statement in text for _, statement in roles)
        row.update(
            observation_id="daemons-next-three-2026-11-04:datasheet:" + slug,
            source_id="faction-app:chaos-daemons:datasheet:" + slug,
            source_title=title,
            source_url=c["url"],
            observed_at=c["observed_utc"],
            captured_text=text,
            capture_sha256=sha(text.encode()),
            operative_start=start,
            operative_text=operative,
            transcription_sha256=sha(operative.encode()),
            scope_review=observation["authority_limit"],
            geometry=[
                {
                    "model_role": role,
                    "base_statement": statement,
                    "base_status": "observed",
                    "height_status": "not_observed",
                    "fieldability_certified": False,
                    "volume_authority": "accepted_model_geometry_catalog_evidence_required",
                }
                for role, statement in roles
            ],
        )
        row["source_observation_sha256"] = sha(
            json.dumps(
                {k: v for k, v in row.items() if k != "source_observation_sha256"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        rows.append(row)
    audit.update(
        audit_id="daemons-next-three-app-mirror-2026-11-04",
        observations=rows,
        selected_source_ids=[r["source_id"] for r in rows],
    )
    audit["version_evidence"]["observed_at"] = captures["app-updates-index-context"]["observed_utc"]
    return raw(audit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = P / "daemons_next_three_2026_11.audit.json"
    content = build()
    if args.check:
        if path.read_bytes() != content:
            raise ValueError("Three-keyword source artifact drifted.")
    else:
        path.write_bytes(content)
    print(sha(content))


if __name__ == "__main__":
    main()
