"""Reproduce the reviewed Order 63 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-reserve-transport"
VERSION = "maintained-app-mirrors-observed-2026-09-19"
OBSERVED_AT = "2026-09-19T19:06:00+00:00"
AUDIT_ID = "core-reserve-transport-maintained-app-mirrors-2026-09-19"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:reserve-transport"
TEXT = (
    "When a unit uses the rapid disembark mode after its TRANSPORT makes an ingress "
    "move, the models must follow the same rules and restrictions as that TRANSPORT "
    'did. For example, if that TRANSPORT had to be set up more than 8" from all enemy '
    "units and not within your opponent\u2019s deployment zone, the same applies to the "
    "disembarking unit."
)

URL = "https://game-datamissions.com/11th/rules/changelog"
CONSUMERS = [
    "warhammer40k_core.engine.ingress_placement_restrictions:validate_inherited_placement",
    "warhammer40k_core.engine.reserve_arrival_resolution:resolve_reserve_arrival",
]
DESCRIPTOR = {
    "source_rule_id": SOURCE_ID,
    "inherits_ingress_placement": True,
    "cargo_remains_embarked": True,
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_reserve_transport_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / (
    "data/source_audits/maintained_app_mirrors/reserve_transport_2026_09_19.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _build_single(
    *, slug: str, text: str, provider: str, url: str, version: str | None, section: str
) -> tuple[dict[str, object], dict[str, object]]:
    source_id = f"{PACKAGE_ID}:{slug}"
    execution = (
        "executable_engine_runtime" if slug == "reserve-transport" else "partial_engine_runtime"
    )
    consumers = {
        "reserve-transport": [CONSUMERS[0]],
        "placing-reserves": ["warhammer40k_core.engine.reserves:StrategicReserveDeclaration"],
        "ingress": [CONSUMERS[1]],
    }[slug]
    obligations = {
        "reserve-transport": [
            "Rapid Disembark inherits every ingress placement restriction.",
            "Apply inherited restrictions to every passenger model.",
        ],
        "placing-reserves": [
            "Embarked cargo contributes to the reserve points limit; this package does not "
            "recertify all army construction rules."
        ],
        "ingress": [
            "Cargo remains embarked during Transport ingress and is not independently eligible.",
            "General ingress activity lifetimes remain Order 64 work.",
        ],
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
        "evidence_id": f"core-reserve-transport-mirror:{slug}",
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
        "evidence_id": f"core-reserve-transport-review:{slug}",
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
        "artifact_schema": "core-v2-core-reserve-transport-source-v1",
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
        "reserve_transport_policy": DESCRIPTOR,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "minute",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": (
            "Complete v946 18.04.01 Rapid Disembark text retrieved from the "
            "Game Datamissions changelog."
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
            slug="reserve-transport",
            text=TEXT,
            provider="Game Datamissions",
            url=URL,
            version="946",
            section="18.04.01",
        ),
        _build_single(
            slug="placing-reserves",
            provider="40k.app",
            version=None,
            url="https://www.40k.app/rules/20-strategic-reserves",
            section="20.01",
            text=(
                "Before the battle, in the Declare Battle Formations step, you can "
                "select one or more friendly units (excluding FORTIFICATIONS) to "
                "place in strategic reserves. Instead of setting up these units on "
                "the battlefield during deployment, place them to one side; they are "
                "strategic reserves units, and will arrive later in the battle. "
                "Unless otherwise stated, the combined points value of all of your "
                "strategic reserves units (including those embarked within TRANSPORTS "
                "that are themselves placed in strategic reserves) cannot exceed 50% "
                "of your points limit for your battle size."
            ),
        ),
        _build_single(
            slug="ingress",
            provider="40k.app",
            version=None,
            url="https://www.40k.app/rules/20-strategic-reserves",
            section="20.04",
            text=(
                "When eligible: Your unit is in strategic reserves (excluding units "
                "that are embarked within TRANSPORTS that are themselves in strategic "
                'reserves) Set-up distance: 6" Effect: Your unit is set up as described '
                "in Set Up (03.02) While moving: Set up your unit wholly within the "
                'set-up distance of one or more battlefield edges and more than 8" '
                "horizontally from all enemy units. Before the Third Battle Round: "
                "While doing so, no models can be set up within your opponent\u2019s "
                "deployment zone. After moving: Unless otherwise stated, until the "
                "start of the next Charge phase, your unit is not eligible to make "
                "any other type of move."
            ),
        ),
    ]
    artifact, audit = observations[0]
    artifact["rules"] = [row for part, _ in observations for row in part["rules"]]
    artifact["evidence"] = [row for part, _ in observations for row in part["evidence"]]
    audit["rows"] = [row for _, part in observations for row in part["rows"]]
    audit["observation_method"] = (
        "Browser-visible 40k.app 20.01/20.04 and Game Datamissions v946 18.04.01."
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
                raise SystemExit(f"Order 63 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
