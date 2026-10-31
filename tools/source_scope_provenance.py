"""Exact reviewed historical provenance contexts for registered source scopes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools import performance_tool_inputs as inputs
from tools import performance_tool_inputs_v4 as scopes

EC_OVERLAY = (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "emperors_children_profiles_2026_10.overlay-pack.json"
)
EC_OVERLAY_SHA256 = "856706535c9d16c51832d700377105082191a340b0880498b4146cc683fbd451"


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
    scope = scopes.registered_scope(scopes.EC_BASE)
    if relative not in {EC_OVERLAY, scope.spec_path, scope.report_path}:
        return None
    if path.is_symlink():
        raise ValueError("Registered provenance must be a regular file.")
    value: dict[str, Any] = inputs.input_object(
        json.loads(raw, object_pairs_hook=inputs.unique_input_object)
    )
    if relative == EC_OVERLAY:
        if hashlib.sha256(raw).hexdigest() != EC_OVERLAY_SHA256:
            raise ValueError("Registered overlay requires its exact reviewed bytes.")
        if (
            value["schema_version"] != "phase17-source-overlay-v1"
            or value["target_edition"] != "warhammer-40000-11th"
            or value["base_source_package_id"]
            != {
                "namespace": "wahapedia",
                "package_name": "source-mirror",
                "version": "10th-edition-2026-06-14",
            }
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
