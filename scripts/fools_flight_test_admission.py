"""Authorize one exact Fool's Flight source/test successor without rewriting old receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)

TRANSITION = "data/source_audits/ci64_provenance_v1/fools-flight-test-v1.json"
TRANSITION_SHA256 = "2e929a5228f40f85fbad88d4fd0c8831ff4dd23011804c2bf001250b3b0d5f45"
BASE = "6701b3108eeea0124932cac5d70758e18dea89f2"
OWNER = "tests/factions/chaos_daemons/integration/test_fools_flight.py"
CLASSIFIER = "tests/infrastructure/source_governance/unit/test_blocked_row_classification.py"
REPLACED_SOURCES = frozenset(
    {
        "src/warhammer40k_core/engine/charge_phase_flow.py",
        "src/warhammer40k_core/engine/charge_roll_flow.py",
        "src/warhammer40k_core/engine/stratagems_eligibility.py",
        "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
        "chaos_daemons/detachments/blood_legion/stratagems.py",
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "faction_blood_legion_ir_support_2026_27.py",
    }
)
NEW_SOURCE = "src/warhammer40k_core/engine/movement_charge_stratagem.py"


class _TestReplacement(TypedDict):
    before: dict[str, object]
    after: dict[str, object]


class _Receipt(TypedDict):
    schema: str
    base: str
    retained_transition_sha256: str
    retained_runtime_fingerprint: str
    runtime_fingerprint: str
    replaced_sources: dict[str, dict[str, str]]
    new_sources: dict[str, str]
    added_files: dict[str, dict[str, object]]
    updated_files: dict[str, _TestReplacement]


@dataclass(frozen=True, slots=True)
class FoolsFlightAdmission:
    receipt: _Receipt
    raw: bytes

    def replace_pins(
        self, *, sources: dict[str, str], classification: dict[str, object]
    ) -> tuple[dict[str, str], dict[str, object]]:
        replacements = self.receipt["replaced_sources"]
        for name, binding in replacements.items():
            if sources.get(name) != binding["before"]:
                raise SystemExit("Fool's Flight source predecessor differs: " + name)
        test = self.receipt["updated_files"][CLASSIFIER]
        if test["before"] != classification:
            raise SystemExit("Fool's Flight classifier predecessor differs.")
        return {**sources, **{name: row["after"] for name, row in replacements.items()}}, test[
            "after"
        ]

    def admits_after(
        self, *, root: Path, runtime: str, predecessor: bytes
    ) -> tuple[str, dict[str, dict[str, object]], bytes]:
        if self.receipt["retained_runtime_fingerprint"] != runtime or self.receipt[
            "retained_transition_sha256"
        ] != _sha(predecessor):
            raise SystemExit("Fool's Flight transition predecessor differs.")
        return (
            self.receipt["runtime_fingerprint"],
            _selection_members(self.receipt["added_files"], root),
            self.raw,
        )


def load_fools_flight_admission(root: Path) -> FoolsFlightAdmission | None:
    target = root / TRANSITION
    _selection_no_links(root, target)
    if not target.exists():
        return None
    raw = target.read_bytes()
    if _sha(raw) != TRANSITION_SHA256:
        raise SystemExit("Fool's Flight admission receipt bytes differ.")
    record = cast(_Receipt, json.loads(raw, object_pairs_hook=_selection_object))
    if (
        set(record) != set(_Receipt.__required_keys__)
        or record["schema"] != "finite-fools-flight-test-v1"
        or record["base"] != BASE
        or record["replaced_sources"].keys() != REPLACED_SOURCES
        or record["new_sources"].keys() != {NEW_SOURCE}
        or record["added_files"].keys() != {OWNER}
        or record["updated_files"].keys() != {CLASSIFIER}
        or record["updated_files"][CLASSIFIER].keys() != {"before", "after"}
        or any(
            row.keys() != {"before", "after"} or row["before"] == row["after"]
            for row in record["replaced_sources"].values()
        )
    ):
        raise SystemExit("Fool's Flight transition inventory differs.")
    for name, digest in record["new_sources"].items():
        source = root / name
        _selection_no_links(root, source)
        if not source.is_file() or _sha(source.read_bytes()) != digest:
            raise SystemExit("Fool's Flight new source bytes differ: " + name)
    return FoolsFlightAdmission(record, raw)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
