"""Build the reviewed Order 30 source artifacts offline."""

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
    / "core_fight_on_death_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/fight_on_death_2026_09_07.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-fight-on-death"
VERSION = "maintained-app-mirrors-observed-2026-09-07"
OBSERVED_AT = "2026-09-07T21:35:45Z"
AUDIT_ID = "core-fight-on-death-maintained-app-mirrors-2026-09-07"
GDM_URL = "https://game-datamissions.com/11th/rules/changelog"
PRESENCE_URL = "https://www.40k.app/rules/05-attack-sequence"
PRESENCE_TEXT = (
    "Fight On Death (05.04.05) requires models awaiting such an ability to stay on the "
    "battlefield until their unit has attacked (or until the end of the phase). How do these "
    "models function while this is the case?\n"
    "Models awaiting a Fight On Death ability are still present on the battlefield for all "
    "rules purposes. This includes (but is not limited to) the following regarding such "
    "models:\n"
    "They can be measured to by friendly/enemy abilities.\n"
    "They can be considered visible to friendly/enemy models where relevant.\n"
    "They can use their datasheet abilities.\n"
    "They can be targeted by stratagems.\n"
    "Enemy units can still be engaged with them (which may restrict the opposing player's "
    "consolidation/pile-In moves made as part of an overrun fight)."
)
FIGHT_ON_DEATH_TEXT = (
    "Some rules enable models to attack after they have been destroyed. When a model under "
    "such an effect is destroyed, do not remove it from play.\n"
    "Those models will stay on the battlefield until their unit is selected to attack and "
    "has attacked, or until the end of the phase (whichever comes first). Any rules triggered "
    "by those models being destroyed are resolved, and then those destroyed models are removed.\n"
    "If a rule instructs a destroyed model to fight immediately after the attacking unit, "
    "instead that model is not removed from the battlefield until that model's unit has "
    "fought, or until the end of the phase (whichever comes first). This allows the models in "
    "the unit to fight all at once, and stratagems that target that unit will also affect that "
    "destroyed model."
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
            "retained-presence",
            "FAQ",
            PRESENCE_TEXT,
            ["warhammer40k_core.engine.ability_presence:active_ability_model_ids_for_unit"],
        ),
        (
            "fight-on-death",
            "05.04.05",
            FIGHT_ON_DEATH_TEXT,
            ["warhammer40k_core.engine.retained_destruction_selection:apply_retention_selection"],
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
            "evidence_id": f"core-fight-on-death-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_title": f"P05B {section} {slug}",
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
            if slug == "retained-presence"
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
                "evidence_id": f"core-fight-on-death-mirror:{row_id}",
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
        "artifact_schema": "core-v2-core-fight-on-death-source-v1",
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
            "The complete 05.04.05 statement and v931 FAQ were observed through indexed "
            "maintained-mirror pages. Direct 40k.app retrieval returned HTTP 403. No App "
            "version is inferred for 40k.app; no co-version comparison is asserted."
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
                raise SystemExit(f"P05B source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
