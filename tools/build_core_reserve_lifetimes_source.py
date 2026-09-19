"""Reproduce the reviewed Order 64 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-reserve-lifetimes"
VERSION = "maintained-app-mirrors-observed-2026-09-19"
OBSERVED_AT = "2026-09-19T21:33:00+00:00"
AUDIT_ID = "core-reserve-lifetimes-maintained-app-mirrors-2026-09-19"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:arrival"
DESCRIPTOR = {
    "arrival_source_id": SOURCE_ID,
    "reposition_source_id": f"{PACKAGE_ID}:reposition",
    "cleanup_source_id": f"{PACKAGE_ID}:final-turn-cleanup",
    "ingress_source_id": f"{PACKAGE_ID}:ingress",
    "earliest_arrival_battle_round": 2,
    "destruction_battle_round": 3,
    "movement_lock_expires_at": "next_charge_phase_start",
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_reserve_lifetimes_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / (
    "data/source_audits/maintained_app_mirrors/reserve_lifetimes_2026_09_19.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _build_single(
    *, slug: str, text: str, provider: str, url: str, version: str | None, section: str
) -> tuple[dict[str, object], dict[str, object]]:
    source_id = f"{PACKAGE_ID}:{slug}"
    execution = "executable_engine_runtime"
    consumers = {
        "arrival": [
            "warhammer40k_core.engine.reserve_destruction:resolve_unarrived_reserve_destruction"
        ],
        "reposition": [
            "warhammer40k_core.engine.game_state:GameState.reposition_unit_to_strategic_reserves"
        ],
        "final-turn-cleanup": [
            "warhammer40k_core.engine.reserve_destruction:final_turn_cleanup_policy"
        ],
        "ingress": ["warhammer40k_core.engine.ingress_lifetimes:ingress_movement_locked"],
    }[slug]
    obligations = {
        "arrival": ["Core round-two arrival and round-three destruction with both exemptions."],
        "reposition": [
            "Preserve move history, timed effects and circumstances across repositioning."
        ],
        "final-turn-cleanup": ["Destroy all remaining reserves without destroyed-model triggers."],
        "ingress": ["Every other movement type is locked until the next Charge phase starts."],
    }[slug]
    transcription = hashlib.sha256(text.encode()).hexdigest()
    audit: dict[str, object] = {
        "row_id": slug,
        "provider_name": provider,
        "source_url": url,
        "observed_at": OBSERVED_AT,
        "app_version": version,
        "policy_id": POLICY,
        "rule_source_id": source_id,
        "transcription_sha256": transcription,
        "provider_non_affiliation_recorded": True,
        "transcription_scope": f"Complete {section} operative text.",
        "reviewed_obligations": obligations,
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": f"core-reserve-lifetimes-mirror:{slug}",
        "rule_source_id": source_id,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": slug,
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": provider,
        "source_title": f"{provider} {section}",
        "source_platform": "Web",
        "source_url": url,
        "observed_at": None if version else OBSERVED_AT,
        "app_version": version,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription,
        "official_corroborating_source_ids": [],
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": execution,
        "runtime_consumer_ids": consumers,
    }
    row["observation_sha256"] = _hash(
        {
            **row,
            "load_support_status": "not_loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
        }
    )
    review = {
        **row,
        "evidence_id": f"core-reserve-lifetimes-review:{slug}",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_platform": "Repository",
        "app_version": None,
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
    }
    review["observation_sha256"] = _hash(
        {
            **review,
            "load_support_status": "not_loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
        }
    )
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-reserve-lifetimes-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": source_id,
                "section_id": section,
                "source_text": text,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": execution,
                "runtime_consumer_ids": consumers,
            }
        ],
        "evidence": [review, row],
        "reserve_lifetimes_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "minute",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": (
            "Complete 40k.app 20.01.02, 20.02, 20.03 and 20.04 browser-visible text."
        ),
        "co_version_comparison": "No second-provider observation asserted.",
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
    }


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    observations = [
        _build_single(
            slug="final-turn-cleanup",
            section="20.01.02",
            text=(
                "At the end of the final turn, units in strategic reserves are destroyed, "
                "but they do not trigger rules that apply when a model is destroyed."
            ),
            provider="40k.app",
            version=None,
            url="https://www.40k.app/rules/20-strategic-reserves",
        ),
        _build_single(
            slug="reposition",
            section="20.02",
            text=(
                "Some rules allow units to be removed from the battlefield and placed in "
                "strategic reserves during the battle. Units that use such rules are known"
                " as repositioned units. In addition to any other rules that apply to such"
                " units (such as where they can or cannot arrive), all of the following "
                "rules apply to them: If used in the Movement phase, such rules can be "
                "used on units that have already moved that phase. A repositioned unit "
                "that is set up in the same turn in which it made an advance, fall-back or"
                " disembark move has still made an advance, fall-back or disembark move "
                "that turn. When they are removed from the battlefield, any rules that are"
                " affecting such units for a specified duration or under specified "
                "circumstances continue to affect them while that duration and/or those "
                "circumstances apply. Example: A unit that was within range of an aura "
                "ability when removed from the battlefield would no longer be affected by "
                "that aura ability if it is no longer within range of it when it makes an "
                "ingress move, but a unit that was battle-shocked when removed from the "
                "battlefield would still be battle-shocked if it makes an ingress move in "
                "the same turn."
            ),
            provider="40k.app",
            version=None,
            url="https://www.40k.app/rules/20-strategic-reserves",
        ),
        _build_single(
            slug="arrival",
            section="20.03",
            text=(
                "To arrive on the battlefield, each strategic reserves unit must make an "
                "ingress move (20.04). Unless otherwise stated, they can only do so from "
                "the second battle round onwards. At the end of the third battle round, "
                "unless otherwise stated, all strategic reserves units that have not made "
                "one or more ingress moves are destroyed, with the following exceptions: "
                "Units embarked within TRANSPORTS that have made an ingress move during "
                "the battle. Repositioned units (20.02)."
            ),
            provider="40k.app",
            version=None,
            url="https://www.40k.app/rules/20-strategic-reserves",
        ),
        _build_single(
            slug="ingress",
            section="20.04",
            text=(
                "When eligible: Your unit is in strategic reserves (excluding units that "
                "are embarked within TRANSPORTS that are themselves in strategic reserves)"
                ' Set-up distance: 6" Effect: Your unit is set up as described in Set Up '
                "(03.02) While moving: Set up your unit wholly within the set-up distance "
                'of one or more battlefield edges and more than 8" horizontally from all '
                "enemy units. Before the Third Battle Round: While doing so, no models can"
                " be set up within your opponent’s deployment zone. After moving: Unless "  # noqa: RUF001 -- exact source transcription
                "otherwise stated, until the start of the next Charge phase, your unit is "
                "not eligible to make any other type of move."
            ),
            provider="40k.app",
            version=None,
            url="https://www.40k.app/rules/20-strategic-reserves",
        ),
    ]
    artifact, audit = observations[0]
    artifact["rules"] = [row for part, _ in observations for row in part["rules"]]
    artifact["evidence"] = [row for part, _ in observations for row in part["evidence"]]
    audit["rows"] = [row for _, part in observations for row in part["rows"]]
    audit["observation_method"] = (
        "Browser-visible 40k.app complete 20.01.02, 20.02, 20.03 and 20.04."
    )
    artifact["package_hash"] = ""
    artifact["package_hash"] = _hash(artifact)
    return artifact, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"Order 64 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
