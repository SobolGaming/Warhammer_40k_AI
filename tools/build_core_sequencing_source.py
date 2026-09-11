# ruff: noqa: E501, RUF001
"""Reproduce the reviewed P01D source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/core_sequencing_2026_09/artifacts/package.json"
)
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/sequencing_2026_09_10.audit.json"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
PACKAGE_ID = "gw-11e-core-sequencing"
VERSION = "maintained-app-mirrors-observed-2026-09-10"
OBSERVED_AT = "2026-09-10T16:07:00+00:00"
BOUNDARY_OBSERVED_AT = "2026-09-10T18:07:00+00:00"
AUDIT_ID = "core-sequencing-maintained-app-mirrors-2026-09-10"
RULES = (
    (
        "active-player",
        "01.03",
        "01-core-concepts",
        "ACTIVE PLAYER AND OPPOSING PLAYER\nAt any given time, one player is the ‘active player’ and their opponent is the ‘opposing player’. Which player is which changes throughout the battle, but both players are always one or the other; whenever a player becomes the active player, their opponent becomes the opposing player, and vice versa.\nWhile it is neither player’s turn (e.g. at the start or end of the battle round), the player who takes the first turn in each battle round is the active player.\nWhile it is a player’s turn, that player is the active player, with the following exceptions:\n- Each time a unit is selected to move, that unit’s controlling player is the active player until that move ends.\n- Each time a unit is selected to shoot or selected to fight, that unit’s controlling player is the active player until those attacks are resolved.",
    ),
    (
        "players-rules",
        "01.03.01",
        "01-core-concepts",
        "Player's Rules\nDuring the game, players will sometimes need to know which rules are theirs, as opposed to their opponent’s. The following are considered a player’s rules:\n- Any army rules they have.\n- Any detachments in their army.\n- Any stratagems they use.\n- Any enhancements that units or models in their army have.\n- Any abilities or rules found on their units’ datasheets.\nRules that have restrictions (e.g. 'Once per battle/turn/phase') only apply to the player whose rule it is. Some missions may introduce additional rules that take effect in the battle. Where this is the case:\n- If the rule is used by a player, it is treated as one of that player’s rules.\n- If it is not used by a player, and always takes effect, such a rule is resolved before any of the active player’s rules, in an order of their choosing.",
    ),
    (
        "rules-sequencing",
        "01.03.02",
        "01-core-concepts",
        "Rules Sequencing\nAt any point in the game, the players will have rules that they can or must use, which may occur at the same time another player can or must use a rule. Unless otherwise stated, these are activated in the following order:\n1. All of the active player’s rules that must be used, in an order of their choosing.\n2. All of the active player’s rules that they can optionally use and wish to use, in an order of their choosing.\n3. All of the opposing player’s rules that must be used, in an order of their choosing.\n4. All of the opposing player’s rules that they can optionally use and wish to use, in an order of their choosing.\nIf another rule could be used after a rule has resolved during this sequence but before other rules in that same timing have resolved, those new rules do not trigger until all the remaining rules to be resolved in that same timing have been resolved.\nExample: The active player's unit has an ability enabling it to make a normal move after it has shot. An enemy unit targeted by that unit has an ability enabling it to shoot back at a unit that shot at it. The active player's rule is resolved first, followed by the opposing player's rule.",
    ),
    (
        "end-turn-mission-order",
        "07.02",
        "07-the-battle-round",
        "7. End of Turn Step: Rules that are triggered at the end of a turn are resolved now, in the following order:\n1. First resolve rules triggered at this point other than mission rules.\n2. Both players then consult their mission; if one or both players have achieved any aspects of their mission that are triggered at this point, resolve them now.",
    ),
    (
        "end-round-mission-order",
        "07.03",
        "07-the-battle-round",
        "END OF BATTLE ROUND\nRules that are triggered at the end of the battle round are resolved now, in the following order:\n1. First resolve rules triggered at this point other than mission rules.\n2. Both players then consult their mission; if one or both players have achieved any aspects of their mission that are triggered at this point, resolve them now.\nThe battle round then ends and, unless the battle ends, the next battle round starts. The mission you are playing will tell you how many battle rounds to resolve before the battle ends.",
    ),
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for slug, section, page, source_text in RULES:
        source_id = f"{PACKAGE_ID}:{slug}"
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()
        url = f"https://www.40k.app/rules/{page}"
        consumers = {
            "active-player": [
                "warhammer40k_core.engine.active_player:effective_active_player_id",
                "warhammer40k_core.engine.active_player_scopes:ActivePlayerScope",
            ],
            "players-rules": [
                "warhammer40k_core.engine.sequencing:sequencing_tier",
                "warhammer40k_core.engine.mission_timing_candidates:mission_timing_candidates",
            ],
            "rules-sequencing": [
                "warhammer40k_core.engine.sequencing:sequencing_tier",
                "warhammer40k_core.engine.timing_rule_candidates:resolve_timing_rule_candidates",
                "warhammer40k_core.engine.rule_trigger_state:observe_rule_trigger",
            ],
            "end-turn-mission-order": [
                "warhammer40k_core.engine.battle_round_flow:BattleRoundFlow",
                "warhammer40k_core.engine.mission_turn_end_sequencing:request_mission_turn_end_rules",
            ],
            "end-round-mission-order": [
                "warhammer40k_core.engine.battle_round_flow:BattleRoundFlow",
                "warhammer40k_core.engine.sequencing:sequencing_tier",
            ],
        }[slug]
        observed_at = BOUNDARY_OBSERVED_AT if section.startswith("07.") else OBSERVED_AT
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
        audit: dict[str, object] = {
            "row_id": slug,
            "provider_name": "40k.app",
            "source_url": url,
            "observed_at": observed_at,
            "app_version": None,
            "policy_id": POLICY,
            "rule_source_id": source_id,
            "transcription_sha256": text_hash,
            "provider_non_affiliation_recorded": True,
        }
        audit_hash = _hash(audit)
        audits.append({**audit, "source_observation_sha256": audit_hash})
        row: dict[str, object] = {
            "evidence_id": f"core-sequencing-mirror:{slug}",
            "rule_source_id": source_id,
            "evidence_kind": "third_party_mirror",
            "authority": "project_authoritative_app_mirror",
            "project_authority_policy_id": POLICY,
            "review_audit_id": AUDIT_ID,
            "review_audit_row_id": slug,
            "review_audit_source_observation_sha256": audit_hash,
            "provider_name": "40k.app",
            "source_title": f"40k.app {section} {slug}",
            "source_platform": "Web",
            "source_url": url,
            "observed_at": observed_at,
            "app_version": None,
            "app_build": None,
            "capture_artifact_path": None,
            "capture_sha256": None,
            "transcription_sha256": text_hash,
            "official_corroborating_source_ids": [],
            "verification_status": "authoritative_app_mirror",
            "provider_non_affiliation_recorded": True,
            "observation_sha256": "",
            "load_support_status": "loaded",
            "semantic_execution_status": "executable_engine_runtime",
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
            "evidence_id": f"core-sequencing-review:{slug}",
            "evidence_kind": "project_reviewed_app_transcription",
            "authority": "unverified_transcription_only",
            "project_authority_policy_id": None,
            "review_audit_id": None,
            "review_audit_row_id": None,
            "review_audit_source_observation_sha256": None,
            "provider_name": "CORE V2 Source Review",
            "source_platform": "Repository",
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
        evidence.append(review)
        evidence.append(row)
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-sequencing-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "rows": audits,
        "observation_time_precision": "minute",
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
        "co_version_comparison": "Expanded 01.03–01.03.02 and 07.02–07.03 read directly in the browser. No App version exposed; no co-version comparison asserted.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"P01D source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
