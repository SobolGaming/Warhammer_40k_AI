from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TypedDict, cast

type _JsonValue = None | bool | int | float | str | list[_JsonValue] | dict[str, _JsonValue]

ENGINE_BUILD_MANIFEST_SCHEMA_VERSION = "engine-build-manifest-v1"
ENGINE_BUILD_FINGERPRINT_ALGORITHM = "runtime-tree-sha256-v1"
ENGINE_BUILD_ID_PREFIX = f"warhammer40k-core-v2:{ENGINE_BUILD_FINGERPRINT_ALGORITHM}:"

_PACKAGE_NAME = "warhammer40k_core"
_MANIFEST_FILENAME = "_engine_build_manifest.json"
_MANIFEST_LOGICAL_PATH = f"{_PACKAGE_NAME}/{_MANIFEST_FILENAME}"
_CACHE_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)
_AUTHORITATIVE_SUFFIXES = frozenset({".json", ".py"})
_AUTHORITATIVE_EXACT_NAMES = frozenset({"py.typed"})
_PORTABLE_RESOURCE_PATH = re.compile(r"\A[A-Za-z0-9_./-]+\Z")
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")


class EngineBuildIdentityError(RuntimeError):
    """Raised when the authoritative runtime build cannot be identified exactly."""


class EngineBuildIdentityUnavailableError(EngineBuildIdentityError):
    """Raised when the authoritative runtime resource inventory is unavailable."""


class EngineBuildIdentityDriftError(EngineBuildIdentityError):
    """Raised when runtime resources differ from the generated build manifest."""


class EngineBuildResourcePayload(TypedDict):
    path: str
    byte_length: int
    sha256: str


class EngineBuildManifestPayload(TypedDict):
    schema_version: str
    algorithm: str
    fingerprint: str
    build_id: str
    resource_count: int
    resources: list[EngineBuildResourcePayload]


@dataclass(frozen=True, slots=True)
class EngineBuildIdentity:
    schema_version: str
    algorithm: str
    fingerprint: str
    build_id: str
    resource_count: int


@dataclass(frozen=True, slots=True)
class _AuthoritativeResource:
    logical_path: str
    content: bytes


def build_engine_manifest_payload() -> EngineBuildManifestPayload:
    """Build the deterministic manifest for every authoritative packaged resource."""

    resources = [
        EngineBuildResourcePayload(
            path=resource.logical_path,
            byte_length=len(resource.content),
            sha256=hashlib.sha256(resource.content).hexdigest(),
        )
        for resource in _authoritative_resources()
    ]
    fingerprint_input = {
        "schema_version": ENGINE_BUILD_MANIFEST_SCHEMA_VERSION,
        "algorithm": ENGINE_BUILD_FINGERPRINT_ALGORITHM,
        "resources": resources,
    }
    fingerprint = hashlib.sha256(_canonical_json_bytes(fingerprint_input)).hexdigest()
    return {
        "schema_version": ENGINE_BUILD_MANIFEST_SCHEMA_VERSION,
        "algorithm": ENGINE_BUILD_FINGERPRINT_ALGORITHM,
        "fingerprint": fingerprint,
        "build_id": f"{ENGINE_BUILD_ID_PREFIX}{fingerprint}",
        "resource_count": len(resources),
        "resources": resources,
    }


def canonical_engine_build_manifest_text(payload: EngineBuildManifestPayload) -> str:
    """Serialize a build manifest in its sole committed representation."""

    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


@cache
def verified_engine_build_identity() -> EngineBuildIdentity:
    """Load the generated manifest and verify the complete live resource tree."""

    manifest_resource = files(_PACKAGE_NAME).joinpath(_MANIFEST_FILENAME)
    if not manifest_resource.is_file():
        raise EngineBuildIdentityUnavailableError(
            "The generated engine build manifest is unavailable."
        )
    try:
        manifest_bytes = manifest_resource.read_bytes()
    except OSError as exc:
        raise EngineBuildIdentityUnavailableError(
            "The generated engine build manifest could not be read."
        ) from exc
    manifest = _decode_manifest(manifest_bytes)
    expected = build_engine_manifest_payload()
    if manifest != expected:
        raise EngineBuildIdentityDriftError(
            "Authoritative runtime resources drifted from the engine build manifest."
        )
    return EngineBuildIdentity(
        schema_version=manifest["schema_version"],
        algorithm=manifest["algorithm"],
        fingerprint=manifest["fingerprint"],
        build_id=manifest["build_id"],
        resource_count=manifest["resource_count"],
    )


def current_engine_build_id() -> str:
    """Return the verified immutable identity of the active runtime build."""

    return verified_engine_build_identity().build_id


def _authoritative_resources() -> tuple[_AuthoritativeResource, ...]:
    package_root = files(_PACKAGE_NAME)
    resources = list(_walk_resources(package_root, logical_prefix=(_PACKAGE_NAME,)))
    packaged_schema_root = package_root.joinpath("contracts", "schemas")
    if not packaged_schema_root.is_dir():
        source_schema_root = _source_checkout_schema_root(package_root)
        resources.extend(
            _walk_resources(
                source_schema_root,
                logical_prefix=(_PACKAGE_NAME, "contracts", "schemas"),
            )
        )
    resources.sort(key=lambda resource: resource.logical_path)
    seen_paths: set[str] = set()
    seen_casefolded_paths: set[str] = set()
    for resource in resources:
        if resource.logical_path in seen_paths:
            raise EngineBuildIdentityUnavailableError(
                "The authoritative runtime inventory contains a duplicate path."
            )
        casefolded = resource.logical_path.casefold()
        if casefolded in seen_casefolded_paths:
            raise EngineBuildIdentityUnavailableError(
                "The authoritative runtime inventory is not case-portable."
            )
        seen_paths.add(resource.logical_path)
        seen_casefolded_paths.add(casefolded)
    if not resources:
        raise EngineBuildIdentityUnavailableError("The authoritative runtime inventory is empty.")
    return tuple(resources)


def _walk_resources(
    root: Traversable,
    *,
    logical_prefix: tuple[str, ...],
) -> tuple[_AuthoritativeResource, ...]:
    if not root.is_dir():
        raise EngineBuildIdentityUnavailableError(
            "An authoritative runtime resource root is unavailable."
        )
    try:
        children = tuple(root.iterdir())
    except OSError as exc:
        raise EngineBuildIdentityUnavailableError(
            "An authoritative runtime resource root could not be enumerated."
        ) from exc
    resources: list[_AuthoritativeResource] = []
    for child in sorted(children, key=lambda entry: entry.name):
        _validate_resource_component(child.name)
        if isinstance(child, Path) and child.is_symlink():
            raise EngineBuildIdentityUnavailableError(
                "Authoritative runtime resources must not contain symbolic links."
            )
        if child.is_dir():
            if child.name in _CACHE_DIRECTORY_NAMES:
                continue
            resources.extend(_walk_resources(child, logical_prefix=(*logical_prefix, child.name)))
            continue
        if not child.is_file():
            raise EngineBuildIdentityUnavailableError(
                "The authoritative runtime inventory contains an unsupported entry."
            )
        logical_path = "/".join((*logical_prefix, child.name))
        if logical_path == _MANIFEST_LOGICAL_PATH:
            continue
        _validate_authoritative_file(logical_path, child.name)
        try:
            raw_content = child.read_bytes()
        except OSError as exc:
            raise EngineBuildIdentityUnavailableError(
                "An authoritative runtime resource could not be read."
            ) from exc
        resources.append(
            _AuthoritativeResource(
                logical_path=logical_path,
                content=_normalize_text_line_endings(raw_content),
            )
        )
    return tuple(resources)


def _source_checkout_schema_root(package_root: Traversable) -> Path:
    if not isinstance(package_root, Path):
        raise EngineBuildIdentityUnavailableError(
            "The installed runtime is missing its packaged contract schemas."
        )
    module_path = Path(__file__).resolve()
    source_package_root = module_path.parent
    if package_root.resolve() != source_package_root:
        raise EngineBuildIdentityUnavailableError(
            "The installed runtime is missing its packaged contract schemas."
        )
    repository_root = source_package_root.parents[1]
    if (
        source_package_root.parent.name != "src"
        or not (repository_root / "pyproject.toml").is_file()
    ):
        raise EngineBuildIdentityUnavailableError(
            "A trustworthy source-checkout contract schema root is unavailable."
        )
    schema_root = repository_root / "contracts" / "schemas"
    if not schema_root.is_dir():
        raise EngineBuildIdentityUnavailableError(
            "The source checkout is missing its canonical contract schemas."
        )
    return schema_root


def _validate_resource_component(component: str) -> None:
    if (
        not component
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
        or not _PORTABLE_RESOURCE_PATH.fullmatch(component)
    ):
        raise EngineBuildIdentityUnavailableError(
            "The authoritative runtime inventory contains a non-portable path."
        )


def _validate_authoritative_file(logical_path: str, file_name: str) -> None:
    suffix = Path(file_name).suffix
    if file_name not in _AUTHORITATIVE_EXACT_NAMES and suffix not in _AUTHORITATIVE_SUFFIXES:
        raise EngineBuildIdentityUnavailableError(
            f"Unclassified packaged runtime resource: {logical_path}."
        )


def _normalize_text_line_endings(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _decode_manifest(raw: bytes) -> EngineBuildManifestPayload:
    normalized = _normalize_text_line_endings(raw)
    try:
        text = normalized.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngineBuildIdentityDriftError(
            "The generated engine build manifest is not UTF-8."
        ) from exc
    try:
        value = cast(_JsonValue, json.loads(text))
    except json.JSONDecodeError as exc:
        raise EngineBuildIdentityDriftError(
            "The generated engine build manifest is not valid JSON."
        ) from exc
    manifest = _validated_manifest(value)
    if text != canonical_engine_build_manifest_text(manifest):
        raise EngineBuildIdentityDriftError(
            "The generated engine build manifest is not canonical JSON."
        )
    return manifest


def _validated_manifest(value: _JsonValue) -> EngineBuildManifestPayload:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "algorithm",
        "fingerprint",
        "build_id",
        "resource_count",
        "resources",
    }:
        raise EngineBuildIdentityDriftError("The generated engine build manifest shape is invalid.")
    if (
        value["schema_version"] != ENGINE_BUILD_MANIFEST_SCHEMA_VERSION
        or value["algorithm"] != ENGINE_BUILD_FINGERPRINT_ALGORITHM
        or type(value["fingerprint"]) is not str
        or _SHA256.fullmatch(value["fingerprint"]) is None
        or value["build_id"] != f"{ENGINE_BUILD_ID_PREFIX}{value['fingerprint']}"
        or type(value["resource_count"]) is not int
        or value["resource_count"] < 1
        or not isinstance(value["resources"], list)
        or value["resource_count"] != len(value["resources"])
    ):
        raise EngineBuildIdentityDriftError(
            "The generated engine build manifest identity is invalid."
        )
    previous_path: str | None = None
    casefolded_paths: set[str] = set()
    for item in value["resources"]:
        if not isinstance(item, dict) or set(item) != {"path", "byte_length", "sha256"}:
            raise EngineBuildIdentityDriftError(
                "A generated engine build manifest resource is invalid."
            )
        path = item["path"]
        byte_length = item["byte_length"]
        digest = item["sha256"]
        if (
            type(path) is not str
            or not path.startswith(f"{_PACKAGE_NAME}/")
            or _PORTABLE_RESOURCE_PATH.fullmatch(path) is None
            or type(byte_length) is not int
            or byte_length < 0
            or type(digest) is not str
            or _SHA256.fullmatch(digest) is None
            or (previous_path is not None and path <= previous_path)
            or path.casefold() in casefolded_paths
            or path == _MANIFEST_LOGICAL_PATH
        ):
            raise EngineBuildIdentityDriftError(
                "A generated engine build manifest resource identity is invalid."
            )
        previous_path = path
        casefolded_paths.add(path.casefold())
    return cast(EngineBuildManifestPayload, value)
