"""Source authentication and assertion inventory, not semantic compliance credit."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize(
    "locator",
    [
        "13.01",
        "13.02",
        "13.02.01",
        "13.03",
        "13.04",
        "13.05",
        "13.06",
        "13.06.01",
        "13.07",
        "13.08",
        "13.09",
        "13.09.01",
        "13.10",
        "13.11",
        "13.11.01",
    ],
)
def test_every_adopted_subsection_and_block_matches_both_retained_sources(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    raw = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    identity = f"rule:13:{locator}:1"
    row = next(r for r in source_inventory(current) if r["row_id"] == identity)
    assert row == next(r for r in source_inventory(raw) if r["row_id"] == identity)
    adopted = next(s for s in mapping["sources"] if s["source_id"] == identity)
    assert adopted["source_sha256"] == row["source_sha256"]
    assert [{k: v for k, v in b.items() if k != "value"} for b in adopted["blocks"]] == row[
        "blocks"
    ]
    for b in adopted["blocks"]:
        assert (
            hashlib.sha256(
                json.dumps(
                    b["value"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode()
            ).hexdigest()
            == b["sha256"]
        )
    assert {
        i for q in adopted["requirements"] + adopted["context"] for i in q["source_blocks"]
    } == {b["ordinal"] for b in adopted["blocks"]}


def test_complete_hierarchy_faq_ownership_and_live_assertion_bindings() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    assert mapping["category_hierarchy"] == next(
        c for c in current["categories"] if c["number"] == "13"
    )
    assert {r["row_id"] for r in source_inventory(current) if r["category"] == "13"} == {
        s["source_id"] for s in mapping["sources"]
    }
    assert len(mapping["sources"]) == 15
    assert mapping["faq_ownership"]["reviewed_current_faq_count"] == len(current["faqs"]) == 64
    assert {f["ordinal"] for f in mapping["faq_ownership"]["locally_owned"]} == {34, 44}
    requirements = [q for s in mapping["sources"] for q in s["requirements"]]
    for f in mapping["faq_ownership"]["locally_owned"]:
        assert {k: f[k] for k in ("id", "question", "answer")} == current["faqs"][f["ordinal"] - 1]
        assert f["source_sha256"] == next(
            r["source_sha256"] for r in source_inventory(current) if r["row_id"] == "faq:" + f["id"]
        )
        requirements.extend(f["requirements"])
    assert mapping["semantic_assertions_missing"] == []
    for q in requirements:
        assert q["engine_owners"]
        assert q["semantic_assertions"]
        for binding in q["semantic_assertions"]:
            file, name = binding["node"].split("::")
            node = next(
                n
                for n in ast.parse((ROOT / file).read_text(encoding="utf8")).body
                if isinstance(n, ast.FunctionDef) and n.name == name
            )
            assert (
                hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                == binding["function_ast_sha256"]
            )
            assert [ast.unparse(n) for n in ast.walk(node) if isinstance(n, ast.Assert)] == binding[
                "assertions"
            ]
            assert binding["assertions"]
    for name, expected in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def test_authorized_descriptor_golden_and_d07_predecessor_are_exact() -> None:
    from tests.category_migration_preservation import verify_migrated_test
    from tests.support.section13_preservation import (
        ARCHIVE,
        GOLDEN_TEST,
        pre_section13_descriptor_bytes,
        preserved_section13_golden_bytes,
    )

    assert (
        pre_section13_descriptor_bytes(ROOT)
        == (ROOT / ARCHIVE / "ruleset-descriptor-before.py.txt").read_bytes()
    )
    current = (ROOT / GOLDEN_TEST).read_bytes()
    original, record = verify_migrated_test(ROOT, GOLDEN_TEST)
    assert hashlib.sha256(original).hexdigest() == record["original_sha256"]
    assert (
        preserved_section13_golden_bytes(ROOT, GOLDEN_TEST, current)
        == (ROOT / ARCHIVE / "descriptor-test-before.py.txt").read_bytes()
    )


@pytest.mark.parametrize("target", ["descriptor", "descriptor_archive", "golden", "golden_archive"])
def test_authorized_identity_maintenance_rejects_every_unapproved_byte(
    tmp_path: Path, target: str
) -> None:
    from tests.support.section13_preservation import (
        ARCHIVE,
        DESCRIPTOR,
        GOLDEN_TEST,
        pre_section13_descriptor_bytes,
        preserved_section13_golden_bytes,
    )

    paths = {
        "descriptor": DESCRIPTOR,
        "descriptor_archive": ARCHIVE + "/ruleset-descriptor-before.py.txt",
        "golden_archive": ARCHIVE + "/descriptor-test-before.py.txt",
    }
    for name in paths.values():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes())
    current = (ROOT / GOLDEN_TEST).read_bytes()
    if target == "golden":
        current += b"\n# drift\n"
    else:
        path = tmp_path / paths[target]
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
    if target.startswith("descriptor"):
        with pytest.raises(ValueError, match="drifted"):
            pre_section13_descriptor_bytes(tmp_path)
    else:
        with pytest.raises(ValueError, match="drifted"):
            preserved_section13_golden_bytes(tmp_path, GOLDEN_TEST, current)
