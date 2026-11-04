"""Immutable source observations are separate from the two executable owner fixes."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "data/source_audits/later_ir_icon_2026_11"


def test_later_ir_twelve_complete_source_observations_are_pinned() -> None:
    raw = (AUDIT / "source-only-audit.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "7c5e971b0eca74f8dc39b871aaa543ad29ee8128fa9a579b985f95e878ec4a92"
    )
    audit = json.loads(raw)
    for name, expected in audit["files"].items():
        content = (AUDIT / name).read_bytes()
        assert len(content) == expected["bytes"]
        assert hashlib.sha256(content).hexdigest() == expected["sha256"]
    joins = json.loads((AUDIT / "selected-source-observations.json").read_bytes())
    assert len(joins) == 12
    assert sum(j["observation_match"] == "exact" for j in joins) == 6
    assert sum(j["observation_match"] == "presentation_only" for j in joins) == 6
    for join in joins:
        capture = json.loads((AUDIT / (join["capture_key"] + ".json")).read_bytes())
        assert capture["url"] == join["provider_url"]
        assert capture["observed_utc"] == join["observed_utc"]
        assert join["observed_clause"] in capture["text"]
        assert hashlib.sha256(capture["text"].encode()).hexdigest() == join["captured_text_sha256"]
        assert not join["native_admission_changed"]
        assert not join["full_execution_certified"]


def test_later_ir_only_two_icon_fight_owners_change() -> None:
    preimages = json.loads((AUDIT / "base-later-ir-records.json").read_bytes())
    assert len(preimages) == 93
    shards = (
        ROOT
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "faction_pack_rule_ir/artifacts/shards"
    )
    records = {
        package_id + "/" + row_id: record
        for shard in shards.glob("*.json")
        for package_id, package in json.loads(shard.read_bytes())["source_packages"].items()
        for row_id, record in package["records"].items()
    }
    assert set(preimages) <= records.keys()
    changed: set[str] = set()
    for key, prior in preimages.items():
        current = records[key]
        if prior == current:
            continue
        changed.add(key.rsplit("/", 1)[1])
        expected = json.loads(json.dumps(prior))
        fight = expected["rule_ir"]["clauses"][1]
        params = fight["trigger"]["parameters"]
        assert {p["key"]: p["value"] for p in params}["phase"] == "fight"
        assert params[1] == {"key": "owner", "value": "active_player"}
        params[1]["value"] = "either_player"
        expected["rule_ir"]["ir_hash"] = current["rule_ir"]["ir_hash"]
        assert current == expected
        assert (
            current["rule_ir"]["clauses"][0]["trigger"]["parameters"][1]["value"] == "active_player"
        )
    assert changed == {"000004079:4", "000004080:4"}


def test_later_ir_versioned_ledger_preserves_all_unselected_rows() -> None:
    audit = json.loads((AUDIT / "source-only-audit.json").read_bytes())
    prior = ROOT / audit["prior_ledger"]["path"]
    assert hashlib.sha256(prior.read_bytes()).hexdigest() == audit["prior_ledger"]["sha256"]
    with prior.open(newline="") as stream:
        old = list(csv.DictReader(stream))
    with (AUDIT / "later-ir-residual-disposition.csv").open(newline="") as stream:
        new = list(csv.DictReader(stream))
    assert len(old) == len(new) == 93
    joins = json.loads((AUDIT / "selected-source-observations.json").read_bytes())
    selected = {(j["source_package_id"], j["source_row_id"]): j for j in joins}
    unchanged = 0
    for before, after in zip(old, new, strict=True):
        key = (before["source_package_id"], before["source_row_id"])
        if key not in selected:
            assert before == after
            unchanged += 1
        else:
            assert selected[key]["prior_disposition"] == before
            assert after["current_source_disposition"].startswith(
                "current_operative_clause_observed_"
            )
            assert (
                after["execution_qualification_this_task"]
                == "source_observation_only_no_full_execution_certification"
            )
            assert after["ir_hash"] == selected[key]["current_ir_hash"]
            assert after["in_current_native60"] == before["in_current_native60"]
    assert unchanged == 81
