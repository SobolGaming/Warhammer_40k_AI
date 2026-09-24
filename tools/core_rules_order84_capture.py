"""Fingerprint the observed public GDM page data without executing downloaded JS.

This is a fixed-observation audit extractor, not a runtime source loader. Text is
fingerprinted, not redistributed; it does not manufacture missing source wording.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from typing import Any

_TOKEN = re.compile(
    r"\s*(?:(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')|([a-zA-Z_$][\w$]*)|"
    r"(-?\d+(?:\.\d+)?)|(.))",
    re.S,
)


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def capture_literals(script: str) -> dict[str, Any]:
    """Accept literals only; unknown syntax, duplicate keys and missing markers fail."""

    def parse(offset: int) -> tuple[Any, int]:
        match = _TOKEN.match(script, offset)
        if match is None:
            raise ValueError("Audit capture ended inside a literal.")
        string, identifier, number, punctuation = match.groups()
        end = match.end()
        if string is not None:
            return ast.literal_eval(string), end
        if number is not None:
            return float(number) if "." in number else int(number), end
        if identifier is not None:
            constants = {"null": None, "true": True, "false": False}
            if identifier not in constants:
                raise ValueError("Audit capture contains non-literal JavaScript.")
            return constants[identifier], end
        if punctuation == "[":
            array: list[Any] = []
            if script[end] == "]":
                return array, end + 1
            while True:
                value, end = parse(end)
                array.append(value)
                if script[end] == "]":
                    return array, end + 1
                if script[end] != ",":
                    raise ValueError("Audit capture array delimiter drifted.")
                end += 1
        if punctuation == "{":
            result: dict[str, Any] = {}
            if script[end] == "}":
                return result, end + 1
            while True:
                key_match = _TOKEN.match(script, end)
                if key_match is None:
                    raise ValueError("Audit capture object key is missing.")
                literal_key, named_key, numeric_key, _ = key_match.groups()
                key = ast.literal_eval(literal_key) if literal_key else named_key or numeric_key
                end = key_match.end()
                if key is None or key in result or script[end] != ":":
                    raise ValueError("Audit capture object key is invalid or duplicated.")
                result[key], end = parse(end + 1)
                if script[end] == "}":
                    return result, end + 1
                if script[end] != ",":
                    raise ValueError("Audit capture object delimiter drifted.")
                end += 1
        raise ValueError("Audit capture contains unsupported literal syntax.")

    markers = {
        "categories": ("let x=", 6),
        "faqs": (",m=[{id:", 3),
        "stratagems": (",c={", 3),
        "tables": (",u={", 3),
        "callouts": (",f={", 3),
    }
    result: dict[str, Any] = {}
    for name, (marker, skip) in markers.items():
        if script.count(marker) != 1:
            raise ValueError(f"Audit capture marker drifted: {name}.")
        result[name], _ = parse(script.index(marker) + skip)
    return result


def source_inventory(capture: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep duplicate numbering and supplemental rendered blocks independently."""
    rows: list[dict[str, Any]] = []
    occurrences: Counter[str] = Counter()
    for category in capture["categories"]:
        for section in category["subsections"]:
            for item in (section, *section.get("accordions", [])):
                ref = item["ref"]
                occurrences[ref] += 1
                blocks = [("text", value) for value in item["text"]]
                blocks.extend(("table", value) for value in item.get("tables", []))
                blocks.extend(("stratagem", value) for value in capture["stratagems"].get(ref, []))
                blocks.extend(("callout", value) for value in capture["callouts"].get(ref, []))
                if ref in capture["tables"]:
                    blocks.append(("table_render_metadata", capture["tables"][ref]))
                rows.append(
                    {
                        "row_id": f"rule:{category['number']}:{ref}:{occurrences[ref]}",
                        "category": category["number"],
                        "locator": ref,
                        "title": item["title"],
                        "occurrence": occurrences[ref],
                        "source_sha256": fingerprint(
                            {key: value for key, value in item.items() if key != "accordions"}
                        ),
                        "blocks": [
                            {"ordinal": i, "kind": kind, "sha256": fingerprint(value)}
                            for i, (kind, value) in enumerate(blocks, 1)
                        ],
                    }
                )
    for i, faq in enumerate(capture["faqs"], 1):
        rows.append(
            {
                "row_id": f"faq:{faq['id']}",
                "category": "FAQ",
                "locator": faq["id"],
                "title": f"FAQ {i:02d}",
                "occurrence": 1,
                "source_sha256": fingerprint(faq),
                "blocks": [
                    {"ordinal": n, "kind": kind, "sha256": fingerprint(faq[kind])}
                    for n, kind in enumerate(("question", "answer"), 1)
                ],
            }
        )
    return rows
