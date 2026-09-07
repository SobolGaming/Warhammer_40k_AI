"""Build the reviewed Order 25 source artifacts offline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "core_embarked_abilities_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/embarked_abilities_2026_09_07.audit.json"
)
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-embarked-abilities"
VERSION = "maintained-app-mirrors-observed-2026-09-07"
OBSERVED_AT = "2026-09-07T00:02:56Z"
AUDIT_ID = "core-embarked-abilities-maintained-app-mirrors-2026-09-07"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"
PRESENCE_URL = "https://www.40k.app/rules/01-core-concepts"
EMBARKED_TEXT = (
    "Do a unit's abilities continue to function while they are embarked within a TRANSPORT?\n"
    "Yes, within the restrictions specified by the ability itself. Embarked units are Not On "
    "The Battlefield (01.02.04), so any ability requiring visibility or measurement to another "
    "unit will fail.\n"
    "Example: Azrael is attached to an Intercessor Squad unit and embarked within a TRANSPORT, "
    "and that TRANSPORT is making a shooting attack using the Firing Deck ability. While "
    "Azrael's Supreme Grand Master ability is still technically active, it will have no effect, "
    "as the requirements of the ability are not met (the ability affects 'weapons equipped by "
    "models' in Azrael's unit, and for the purposes of Firing Deck, the TRANSPORT itself is "
    "equipped with those weapons instead)."
)
PRESENCE_TEXT = (
    "A unit that is embarked within a TRANSPORT or that is in strategic reserves is not on "
    "the battlefield. The following applies to such units:\n"
    "That unit is not visible to any other units (units are visible to themselves).\n"
    "Any other unit is not visible to that unit.\n"
    "Players cannot measure distances to or from that unit (units are within range of their "
    "own abilities).\n"
    "This means units not on the battlefield cannot be selected or targeted by any attack or "
    "rule that requires a unit to be visible or within a certain distance (other than their "
    "own abilities).\n"
    "Such units can still use their other rules, and are still units in the controlling "
    "player's army and so can be affected by rules that require a player to select a unit "
    "from an army, as well as rules that affect all units in an army."
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _observation(value: dict[str, object]) -> str:
    evidence = copy.deepcopy(value)
    evidence.update(
        observation_sha256="",
        load_support_status="not_loaded",
        semantic_execution_status="not_certified",
        runtime_consumer_ids=[],
    )
    return _hash(evidence)


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for slug, section, source_text, consumers in (
        (
            "embarked-abilities",
            "FAQ",
            EMBARKED_TEXT,
            ["warhammer40k_core.engine.ability_presence:active_ability_model_ids_for_unit"],
        ),
        (
            "off-battlefield-ability-conditions",
            "01.02.04",
            PRESENCE_TEXT,
            ["warhammer40k_core.engine.ability_presence:ability_spatial_relationship"],
        ),
    ):
        source_id = f"{PACKAGE_ID}:{slug}"
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()
        rules.append(
            {
                "source_id": source_id,
                "section_id": section,
                "source_text": source_text,
                "transcription_sha256": text_hash,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": consumers,
            }
        )
        shared: dict[str, object] = {
            "rule_source_id": source_id,
            "app_build": None,
            "capture_artifact_path": None,
            "capture_sha256": None,
            "transcription_sha256": text_hash,
            "official_corroborating_source_ids": [],
            "observation_sha256": "",
            "load_support_status": "loaded",
            "semantic_execution_status": "executable_engine_runtime",
            "runtime_consumer_ids": consumers,
        }
        review = {
            **shared,
            "evidence_id": f"core-embarked-abilities-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P01C {section} {slug}",
            "source_platform": "Repository",
            "source_url": None,
            "observed_at": None,
            "app_version": None,
            "verification_status": "unverified",
            "provider_non_affiliation_recorded": False,
        }
        review["observation_sha256"] = _observation(review)
        evidence.append(review)
        providers: list[tuple[str, str, str | None]] = [
            ("Game Datamissions", GDM_URL, "931")
            if slug == "embarked-abilities"
            else ("40k.app", PRESENCE_URL, None)
        ]
        for provider, url, version in providers:
            row_id = f"{slug}:{'gdm-v931' if version else '40k-app'}"
            audit: dict[str, object] = {
                "row_id": row_id,
                "provider_name": provider,
                "source_url": url,
                "observed_at": OBSERVED_AT,
                "app_version": version,
                "policy_id": POLICY,
                "rule_source_id": source_id,
                "transcription_sha256": text_hash,
                "provider_non_affiliation_recorded": True,
            }
            audit_hash = _hash(audit)
            audits.append({**audit, "source_observation_sha256": audit_hash})
            mirror = {
                **shared,
                "evidence_id": f"core-embarked-abilities-mirror:{row_id}",
                "evidence_kind": "third_party_mirror",
                "authority": "project_authoritative_app_mirror",
                "project_authority_policy_id": POLICY,
                "review_audit_id": AUDIT_ID,
                "review_audit_row_id": row_id,
                "review_audit_source_observation_sha256": audit_hash,
                "provider_name": provider,
                "source_title": f"{provider} {section} {slug}",
                "source_platform": "Web",
                "source_url": url,
                "observed_at": None if version else OBSERVED_AT,
                "app_version": version,
                "verification_status": "authoritative_app_mirror",
                "provider_non_affiliation_recorded": True,
            }
            mirror["observation_sha256"] = _observation(mirror)
            evidence.append(mirror)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-core-embarked-abilities-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    payload["package_hash"] = _hash(payload)
    return payload, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "rows": audits,
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
        "co_version_comparison": (
            "Complete v931 FAQ observed in the rendered changelog after selecting version 931. "
            "The 01.02.04 ability and geometry clauses were observed in the 40k.app "
            "search-index page (direct fetch 403); no App version is inferred. "
            "The final Battle-shock paragraph remains certified separately by P01. "
            "No co-version comparison is asserted."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"P01C source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
