from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameter,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
)

if TYPE_CHECKING or __package__:
    from tools.canonical_json_hash import canonical_json_sha256
    from tools.faction_rule_ir_bundle import canonical_package_hash
else:
    from canonical_json_hash import canonical_json_sha256
    from faction_rule_ir_bundle import canonical_package_hash

_ROOT = Path(__file__).resolve().parents[1]
_PDFS = _ROOT / "data" / "raw" / "faction_packs"
_SNAPSHOT = (
    _ROOT / "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_abilities.json"
)
_REVIEW = _ROOT / "data/source_manifests/faction_pack_datasheet_review_v1.json"
_DAEMONS_PDF = (
    _PDFS / "eng_22-07_warhammer_40,000_faction_pack_chaos_daemons-lycqqrymwe-qogh4b5yly.pdf"
)
_DEATH_GUARD_PDF = (
    _PDFS / "eng_22-07_warhammer_40,000_faction_pack_death_guard-333phejcfc-tvefnstlub.pdf"
)
_DAEMONS_ID = "000001134"
_DEATH_GUARD_ID = "000004115"
_DAEMONS_PACKAGE = "gw-11e-chaos-daemons-beasts-of-nurgle-datasheet-2026-07"
_DEATH_GUARD_PACKAGE = "gw-11e-death-guard-beasts-of-nurgle-datasheet-2026-07"
_ABILITY_NAME = "Grotesque Regeneration"
_DATASHEET_NAME = "Beasts of Nurgle"

# Retained transcription from the Chaos Daemons Faction Pack, physical page 82.
_DAEMONS_TEXT = (
    "At the end of each phase, if a Beasts of Nurgle model in this unit has lost any wounds "
    "but is not destroyed, that model regains all of its lost wounds."
)


def generated_chaos_daemons_artifact_payload() -> dict[str, object]:
    pdf_sha256 = hashlib.sha256(_DAEMONS_PDF.read_bytes()).hexdigest()
    if pdf_sha256 != "818f7ef144691b9eef6b3c5b5d0a39793690af5a958037b7055215e6675e6a2c":
        raise ValueError("Chaos Daemons Beasts of Nurgle Faction Pack drifted.")
    return _package(
        "chaos-daemons",
        _DAEMONS_ID,
        _DAEMONS_PACKAGE,
        _DAEMONS_TEXT,
        {
            "source_pdf_filename": _DAEMONS_PDF.name,
            "source_pdf_sha256": pdf_sha256,
            "source_page_numbers": [82, 83],
        },
    )


def generated_death_guard_artifact_payload() -> dict[str, object]:
    raw_snapshot = _SNAPSHOT.read_bytes()
    snapshot = json.loads(raw_snapshot)
    row_id = f"{_DEATH_GUARD_ID}:5"
    (row,) = (row for row in snapshot["rows"] if row["source_row_id"] == row_id)
    fields = row["fields"]
    (description,) = (
        field for field in row["text_fields"] if field["column_name"] == "description"
    )
    text = description["normalized_text"]
    if (
        fields["datasheet_id"] != _DEATH_GUARD_ID
        or fields["type"] != "Datasheet"
        or fields["name"] != _ABILITY_NAME
        or hashlib.sha256(text.encode()).hexdigest()
        != "e6d6a002f21bb02bb82e8ab348e69fa1dd965789f3fbdffd2c3ef70ac2e54f7c"
    ):
        raise ValueError("Death Guard Beasts of Nurgle predecessor ability drifted.")

    review = json.loads(_REVIEW.read_bytes())
    (faction,) = (
        faction for faction in review["factions"] if faction["faction_id"] == "death-guard"
    )
    (review_row,) = (row for row in faction["rows"] if row["datasheet_id"] == _DEATH_GUARD_ID)
    pdf_sha256 = hashlib.sha256(_DEATH_GUARD_PDF.read_bytes()).hexdigest()
    if (
        faction["pdf_filename"] != _DEATH_GUARD_PDF.name
        or faction["pdf_sha256"] != pdf_sha256
        or review_row["review_row_id"] != f"source:{_DEATH_GUARD_ID}"
        or review_row["datasheet_name"] != _DATASHEET_NAME
        or review_row["treatment"] != "unchanged_predecessor"
        or review_row["pdf_page_reference"] is not None
    ):
        raise ValueError("Death Guard Beasts of Nurgle predecessor source review drifted.")
    return _package(
        "death-guard",
        _DEATH_GUARD_ID,
        _DEATH_GUARD_PACKAGE,
        text,
        {
            "source_snapshot_filename": _SNAPSHOT.name,
            "source_snapshot_sha256": hashlib.sha256(raw_snapshot).hexdigest(),
            "source_artifact_hash": snapshot["artifact_hash"],
            "official_document_filename": _DEATH_GUARD_PDF.name,
            "official_document_sha256": pdf_sha256,
            "official_document_pages": [],
            "review_manifest_filename": _REVIEW.name,
            "review_manifest_sha256": canonical_json_sha256(_REVIEW),
            "review_row_id": review_row["review_row_id"],
            "review_treatment": review_row["treatment"],
        },
    )


def _package(
    faction_id: str,
    datasheet_id: str,
    package_id: str,
    text: str,
    provenance: dict[str, object],
) -> dict[str, object]:
    row_id = f"{datasheet_id}:5"
    rule_id = f"phase17n:{faction_id}:datasheet:{row_id}"
    rule = RuleIR(
        rule_id=rule_id,
        source_id=f"{package_id}:datasheet:{row_id}",
        normalized_text=text,
        parser_version="manual-source-backed-rule-ir:v1",
        clauses=(
            RuleClause(
                clause_id=f"{rule_id}:clause:001",
                template_id="phase17n:phase-end-self-healing",
                source_span=_span(text, text),
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(text, "At the end of each phase"),
                    parameters=_parameters(("edge", "end"), ("phase", "any")),
                ),
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=_span(text, "has lost any wounds but is not destroyed"),
                        parameters=_parameters(("model_state", "living_and_wounded")),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_UNIT,
                    source_span=_span(text, "a Beasts of Nurgle model in this unit"),
                    parameters=_parameters(("scope", "own_models")),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.RESTORE_LOST_WOUNDS,
                        source_span=_span(text, "regains all of its lost wounds"),
                        parameters=_parameters(("amount", "all"), ("target_scope", "that_model")),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.IMMEDIATE,
                    source_span=_span(text, "regains all of its lost wounds"),
                ),
            ),
        ),
    )
    payload: dict[str, object] = {
        "artifact_schema": f"core-v2-{faction_id}-beasts-of-nurgle-rule-ir-v1",
        "source_package_id": package_id,
        **provenance,
        "datasheet_id": datasheet_id,
        "datasheet_name": _DATASHEET_NAME,
        "records": {
            row_id: {
                "ability_name": _ABILITY_NAME,
                "normalized_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "rule_ir": rule.to_payload(),
            },
        },
        "package_hash": "",
    }
    payload["package_hash"] = canonical_package_hash(payload)
    return payload


def _parameters(*pairs: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def _span(text: str, fragment: str) -> TextSpan:
    start = text.index(fragment)
    return TextSpan(text=fragment, start=start, end=start + len(fragment))
