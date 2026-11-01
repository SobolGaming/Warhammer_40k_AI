"""Exact reviewed historical provenance contexts for registered source scopes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools import performance_tool_inputs as inputs
from tools import performance_tool_inputs_v4 as scopes

EC_OVERLAY = (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "emperors_children_profiles_2026_10.overlay-pack.json"
)
EC_OVERLAY_SHA256 = "856706535c9d16c51832d700377105082191a340b0880498b4146cc683fbd451"


@dataclass(frozen=True)
class ProvenanceRecord:
    """One reviewed overlay and its exact registered comparison contexts."""

    scope_base: str
    overlay_path: str
    overlay_sha256: str
    schema: str
    target_edition: str
    historical_identity: tuple[tuple[str, str], ...]


PROVENANCE_RECORDS = (
    ProvenanceRecord(
        scopes.EC_BASE,
        EC_OVERLAY,
        EC_OVERLAY_SHA256,
        "phase17-source-overlay-v1",
        "warhammer-40000-11th",
        (
            ("namespace", "wahapedia"),
            ("package_name", "source-mirror"),
            ("version", "10th-edition-2026-06-14"),
        ),
    ),
)


# No overlay is added by the Acts timing repair. Only its exact comparison
# documents contain the independently authenticated historical input paths.
COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE, scopes.DEFILER_BASE)


def registered_provenance_context(
    relative: str,
) -> tuple[ProvenanceRecord, scopes.ReviewedScope] | None:
    """Resolve the closed table, rejecting ambiguous contexts before projection."""
    contexts: dict[str, tuple[ProvenanceRecord, scopes.ReviewedScope]] = {}
    for record in PROVENANCE_RECORDS:
        scope = scopes.registered_scope(record.scope_base)
        for context in (record.overlay_path, scope.spec_path, scope.report_path):
            if context in contexts:
                raise ValueError("Registered provenance contexts must be unique.")
            contexts[context] = (record, scope)
    for base in COMPARISON_ONLY_SCOPE_BASES:
        scope = scopes.registered_scope(base)
        record = ProvenanceRecord(base, "", "", "", "", ())
        for context in (scope.spec_path, scope.report_path):
            if context in contexts:
                raise ValueError("Registered provenance contexts must be unique.")
            contexts[context] = (record, scope)
    return contexts.get(relative)


def registered_provenance_text(
    root: Path,
    path: Path,
    raw: bytes,
    historical_inputs: Callable[[], dict[str, str]],
) -> str | None:
    """Project only authenticated historical fields; absence keeps normal scanning."""
    if not path.is_relative_to(root):
        return None
    relative = path.relative_to(root).as_posix()
    context = registered_provenance_context(relative)
    if context is None:
        return None
    record, scope = context
    if path.is_symlink():
        raise ValueError("Registered provenance must be a regular file.")
    value: dict[str, Any] = inputs.input_object(
        json.loads(raw, object_pairs_hook=inputs.unique_input_object)
    )
    if relative == record.overlay_path:
        if hashlib.sha256(raw).hexdigest() != record.overlay_sha256:
            raise ValueError("Registered overlay requires its exact reviewed bytes.")
        if (
            value["schema_version"] != record.schema
            or value["target_edition"] != record.target_edition
            or value["base_source_package_id"] != dict(record.historical_identity)
        ):
            raise ValueError("Registered overlay historical identity changed.")
        del value["base_source_package_id"]["version"]
    elif relative == scope.spec_path:
        if hashlib.sha256(raw).hexdigest() != scope.spec_raw_sha256:
            raise ValueError("Registered role provenance requires its exact reviewed bytes.")
        scopes.validate_spec(value, scope_base=scope.base)
        historical = historical_inputs()
        required = value["required_dependencies"]
        for reference in sorted(scope.required & historical.keys()):
            if required.count(reference) != 1:
                raise ValueError("Registered historical dependency path changed.")
            required.remove(reference)
    else:
        binding: dict[str, Any] = inputs.input_object(value["input_binding"])
        scopes.validate_scope_binding(str(value["base_revision"]), binding)
        if (
            value["policy"] != "rules-engine-performance-v3"
            or value["family"] != inputs.FAMILY
            or value["base_revision"] != scope.base
            or binding["family"] != inputs.FAMILY
            or binding["sides"]["base"]["revision"] != scope.base
        ):
            raise ValueError("Registered comparison historical context changed.")
        historical = historical_inputs()
        for inventory in (
            binding["common"],
            binding["sides"]["base"]["inventory"],
            binding["sides"]["head"]["inventory"],
        ):
            for reference, digest in historical.items():
                if inventory.get(reference) != digest:
                    raise ValueError("Registered historical inventory path/hash changed.")
                del inventory[reference]
    return json.dumps(value)
