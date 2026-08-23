from __future__ import annotations

import hashlib
import importlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol, TypedDict, cast

RULE_IR_SHARD_ARTIFACT_SCHEMA = "core-v2-faction-pack-rule-ir-shard-v1"
WARHAMMER_40000_EDITION = 11

_SHARD_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_DATASHEET_FACTION_PROVENANCE_FIELDS = frozenset(
    {
        "source_snapshot_filename",
        "source_snapshot_sha256",
        "source_artifact_hash",
    }
)


class DatasheetFactionIdsProvenance(TypedDict):
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str


class _AggregateGenerator(Protocol):
    def __call__(
        self,
        *,
        shard_ids: Iterable[str],
        check: bool,
    ) -> None: ...


def build_rule_ir_shard_artifact(
    *,
    shard_id: str,
    source_packages: Iterable[Mapping[str, object]],
    datasheet_faction_ids: Mapping[str, str],
    datasheet_faction_ids_provenance: DatasheetFactionIdsProvenance,
) -> dict[str, object]:
    """Build one deterministic physical shard from complete source packages."""
    _validate_shard_id(shard_id)
    packages_by_id: dict[str, object] = {}
    source_row_owner_by_id: dict[str, str] = {}
    declared_datasheet_ids: set[str] = set()
    for source_package in source_packages:
        source_package_id = _validated_source_package_id(source_package)
        if source_package_id in packages_by_id:
            raise ValueError(f"RuleIR shard source package ID is duplicated: {source_package_id}.")
        _validate_legacy_package_hash(source_package_id, source_package)
        _validate_unique_source_rows(
            source_package_id=source_package_id,
            source_package=source_package,
            source_row_owner_by_id=source_row_owner_by_id,
        )
        declared_datasheet_ids.update(_datasheet_ids(source_package))
        packages_by_id[source_package_id] = dict(source_package)

    if not packages_by_id:
        raise ValueError("RuleIR shard artifact requires at least one source package.")
    validated_faction_ids = _validated_datasheet_faction_ids(
        datasheet_faction_ids,
        expected_datasheet_ids=declared_datasheet_ids,
    )
    validated_provenance = _validated_datasheet_faction_ids_provenance(
        datasheet_faction_ids_provenance
    )

    payload: dict[str, object] = {
        "artifact_schema": RULE_IR_SHARD_ARTIFACT_SCHEMA,
        "edition": WARHAMMER_40000_EDITION,
        "shard_id": shard_id,
        "datasheet_faction_ids": validated_faction_ids,
        "datasheet_faction_ids_provenance": validated_provenance,
        "source_packages": {
            source_package_id: packages_by_id[source_package_id]
            for source_package_id in sorted(packages_by_id)
        },
        "package_hash": "",
    }
    payload["package_hash"] = canonical_package_hash(payload)
    return payload


def datasheet_faction_ids_from_source_snapshot(
    *,
    source_snapshot_path: Path,
    datasheet_ids: Iterable[str],
    canonical_faction_id_by_source_id: Mapping[str, str],
) -> tuple[dict[str, str], DatasheetFactionIdsProvenance]:
    """Resolve exact datasheet faction ownership from a committed Datasheets.json."""
    requested_datasheet_ids = tuple(sorted(datasheet_ids))
    if not requested_datasheet_ids:
        raise ValueError("Datasheet faction identity requires at least one datasheet ID.")
    if len(set(requested_datasheet_ids)) != len(requested_datasheet_ids):
        raise ValueError("Datasheet faction identity contains duplicate datasheet IDs.")
    for source_faction_id, canonical_faction_id in canonical_faction_id_by_source_id.items():
        _validate_non_empty_string("source faction ID", source_faction_id)
        _validate_canonical_id("canonical faction ID", canonical_faction_id)

    raw = source_snapshot_path.read_bytes()
    try:
        decoded_object: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Datasheet faction source snapshot is invalid JSON: {source_snapshot_path}."
        ) from exc
    if not isinstance(decoded_object, dict):
        raise TypeError("Datasheet faction source snapshot must be a JSON object.")
    decoded = cast(dict[str, object], decoded_object)
    source_artifact_hash = _validated_sha256(
        "Datasheet faction source artifact_hash",
        decoded.get("artifact_hash"),
    )
    rows = decoded.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Datasheet faction source snapshot requires non-empty rows.")

    requested_id_set = set(requested_datasheet_ids)
    resolved: dict[str, str] = {}
    for row_value in cast(list[object], rows):
        if not isinstance(row_value, dict):
            raise TypeError("Datasheet faction source row must be an object.")
        row = cast(dict[str, object], row_value)
        source_row_id = _validate_non_empty_string(
            "Datasheet faction source_row_id",
            row.get("source_row_id"),
        )
        if source_row_id not in requested_id_set:
            continue
        if source_row_id in resolved:
            raise ValueError(f"Datasheet faction source row is duplicated: {source_row_id}.")
        fields_value = row.get("fields")
        if not isinstance(fields_value, dict):
            raise TypeError("Datasheet faction source row fields must be an object.")
        fields = cast(dict[str, object], fields_value)
        fields_datasheet_id = _validate_non_empty_string(
            "Datasheet faction fields.id",
            fields.get("id"),
        )
        if fields_datasheet_id != source_row_id:
            raise ValueError(
                f"Datasheet faction source_row_id does not match fields.id: {source_row_id}."
            )
        source_faction_id = _validate_non_empty_string(
            "Datasheet faction fields.faction_id",
            fields.get("faction_id"),
        )
        resolved_faction_id = canonical_faction_id_by_source_id.get(source_faction_id)
        if resolved_faction_id is None:
            raise ValueError(
                "Datasheet faction source row has an unknown source faction ID: "
                f"{source_faction_id} ({source_row_id})."
            )
        resolved[source_row_id] = resolved_faction_id

    missing_datasheet_ids = sorted(requested_id_set.difference(resolved))
    if missing_datasheet_ids:
        raise ValueError(
            f"Datasheet faction source snapshot is missing datasheet IDs: {missing_datasheet_ids}."
        )
    provenance: DatasheetFactionIdsProvenance = {
        "source_snapshot_filename": source_snapshot_path.name,
        "source_snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "source_artifact_hash": source_artifact_hash,
    }
    return dict(sorted(resolved.items())), provenance


def canonical_package_hash(payload: Mapping[str, object]) -> str:
    hash_payload = dict(payload)
    hash_payload["package_hash"] = ""
    canonical = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_json_artifact(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def rendered_artifact_sha256(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(render_json_artifact(payload)).hexdigest()


def write_json_artifact(*, output_path: Path, payload: Mapping[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_json_artifact(payload))


def check_json_artifact(*, output_path: Path, payload: Mapping[str, object]) -> None:
    expected = render_json_artifact(payload)
    if not output_path.is_file():
        raise SystemExit(f"Generated RuleIR shard artifact is missing: {output_path}")
    if output_path.read_bytes() != expected:
        raise SystemExit(f"Generated RuleIR shard artifact is stale: {output_path}")


def committed_source_package_payload(
    shard_artifact_path: Path,
    source_package_id: str,
) -> dict[str, object]:
    """Load one complete source-package payload from a committed physical shard."""
    if type(source_package_id) is not str or not source_package_id:
        raise ValueError("Committed RuleIR source_package_id must be a non-empty string.")
    try:
        decoded_object: object = json.loads(shard_artifact_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Committed RuleIR shard artifact is invalid JSON: {shard_artifact_path}."
        ) from exc
    if not isinstance(decoded_object, dict):
        raise TypeError("Committed RuleIR shard artifact must be a JSON object.")
    decoded = cast(dict[str, object], decoded_object)
    artifact_schema = decoded.get("artifact_schema")
    if artifact_schema != RULE_IR_SHARD_ARTIFACT_SCHEMA:
        raise ValueError("Committed RuleIR shard artifact schema does not match.")
    package_hash = decoded.get("package_hash")
    if type(package_hash) is not str or canonical_package_hash(decoded) != package_hash:
        raise ValueError("Committed RuleIR shard artifact package_hash does not match.")
    source_packages = decoded.get("source_packages")
    if not isinstance(source_packages, dict):
        raise TypeError("Committed RuleIR shard artifact source_packages must be an object.")
    typed_source_packages = cast(dict[str, object], source_packages)
    source_package = typed_source_packages.get(source_package_id)
    if source_package is None:
        raise ValueError(f"Committed RuleIR shard source package is missing: {source_package_id}.")
    if not isinstance(source_package, dict):
        raise TypeError("Committed RuleIR shard source package must be an object.")
    typed_source_package = cast(dict[str, object], source_package)
    if _validated_source_package_id(typed_source_package) != source_package_id:
        raise ValueError("Committed RuleIR shard source package identity does not match its key.")
    _validate_legacy_package_hash(source_package_id, typed_source_package)
    return dict(typed_source_package)


def generate_registered_rule_ir_shard(*, shard_id: str, check: bool = False) -> None:
    """Delegate a source-specific command to its registered physical shard."""
    module_name = (
        "tools.generate_faction_rule_ir_bundles"
        if __package__
        else "generate_faction_rule_ir_bundles"
    )
    module = importlib.import_module(module_name)
    generate = cast(_AggregateGenerator, module.generate_rule_ir_shard_artifacts)
    generate(shard_ids=(shard_id,), check=check)


def _validate_shard_id(shard_id: object) -> str:
    if type(shard_id) is not str or _SHARD_ID_PATTERN.fullmatch(shard_id) is None:
        raise ValueError("RuleIR shard_id must be a canonical non-empty slug.")
    return shard_id


def _validated_source_package_id(source_package: Mapping[str, object]) -> str:
    source_package_id = source_package.get("source_package_id")
    if type(source_package_id) is not str or not source_package_id:
        raise ValueError("RuleIR shard source package requires a non-empty source_package_id.")
    return source_package_id


def _validate_legacy_package_hash(
    source_package_id: str,
    source_package: Mapping[str, object],
) -> None:
    package_hash = source_package.get("package_hash")
    if type(package_hash) is not str or _SHA256_PATTERN.fullmatch(package_hash) is None:
        raise ValueError(
            f"RuleIR shard source package {source_package_id} has an invalid package_hash."
        )
    if canonical_package_hash(source_package) != package_hash:
        raise ValueError(
            f"RuleIR shard source package {source_package_id} package_hash does not match."
        )


def _validate_unique_source_rows(
    *,
    source_package_id: str,
    source_package: Mapping[str, object],
    source_row_owner_by_id: dict[str, str],
) -> None:
    records = source_package.get("records")
    if not isinstance(records, dict) or not records:
        raise ValueError(
            f"RuleIR shard source package {source_package_id} requires non-empty records."
        )
    typed_records = cast(dict[str, object], records)
    for source_row_id in typed_records:
        if type(source_row_id) is not str or not source_row_id:
            raise ValueError(
                f"RuleIR shard source package {source_package_id} has an invalid source row ID."
            )
        existing_owner = source_row_owner_by_id.get(source_row_id)
        if existing_owner is not None:
            raise ValueError(
                "RuleIR shard source row ID is duplicated across source packages: "
                f"{source_row_id} ({existing_owner}, {source_package_id})."
            )
        source_row_owner_by_id[source_row_id] = source_package_id


def _datasheet_ids(source_package: Mapping[str, object]) -> tuple[str, ...]:
    datasheet_ids: set[str] = set()
    datasheet_id = source_package.get("datasheet_id")
    if type(datasheet_id) is str and datasheet_id:
        datasheet_ids.add(datasheet_id)
    datasheets = source_package.get("datasheets")
    if isinstance(datasheets, dict):
        for candidate in cast(dict[str, object], datasheets):
            datasheet_ids.add(_validate_non_empty_string("datasheet ID", candidate))
    elif isinstance(datasheets, list):
        for datasheet_value in cast(list[object], datasheets):
            if not isinstance(datasheet_value, dict):
                raise TypeError("RuleIR shard datasheet entry must be an object.")
            datasheet = cast(dict[str, object], datasheet_value)
            datasheet_ids.add(
                _validate_non_empty_string("datasheet ID", datasheet.get("datasheet_id"))
            )
    elif datasheets is not None:
        raise TypeError("RuleIR shard datasheets inventory must be an object or array.")
    if not datasheet_ids:
        raise ValueError("RuleIR shard source package has no datasheet inventory.")
    return tuple(sorted(datasheet_ids))


def _validated_datasheet_faction_ids(
    datasheet_faction_ids: Mapping[str, str],
    *,
    expected_datasheet_ids: set[str],
) -> dict[str, str]:
    validated = {
        _validate_non_empty_string("datasheet faction datasheet ID", datasheet_id): (
            _validate_canonical_id("datasheet faction ID", faction_id)
        )
        for datasheet_id, faction_id in datasheet_faction_ids.items()
    }
    actual_datasheet_ids = set(validated)
    if actual_datasheet_ids != expected_datasheet_ids:
        missing = sorted(expected_datasheet_ids.difference(actual_datasheet_ids))
        unexpected = sorted(actual_datasheet_ids.difference(expected_datasheet_ids))
        raise ValueError(
            "RuleIR shard datasheet_faction_ids inventory does not match its source packages: "
            f"missing={missing}, unexpected={unexpected}."
        )
    return {datasheet_id: validated[datasheet_id] for datasheet_id in sorted(validated)}


def _validated_datasheet_faction_ids_provenance(
    provenance: DatasheetFactionIdsProvenance,
) -> dict[str, str]:
    if frozenset(provenance) != _DATASHEET_FACTION_PROVENANCE_FIELDS:
        raise ValueError("RuleIR shard datasheet faction provenance fields do not match.")
    return {
        "source_snapshot_filename": _validate_non_empty_string(
            "datasheet faction source_snapshot_filename",
            provenance["source_snapshot_filename"],
        ),
        "source_snapshot_sha256": _validated_sha256(
            "datasheet faction source_snapshot_sha256",
            provenance["source_snapshot_sha256"],
        ),
        "source_artifact_hash": _validated_sha256(
            "datasheet faction source_artifact_hash",
            provenance["source_artifact_hash"],
        ),
    }


def _validate_canonical_id(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if _SHARD_ID_PATTERN.fullmatch(token) is None:
        raise ValueError(f"{field_name} must be a canonical slug.")
    return token


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty trimmed text.")
    return value


def _validated_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if _SHA256_PATTERN.fullmatch(token) is None:
        raise ValueError(f"{field_name} must be lowercase SHA-256.")
    return token
