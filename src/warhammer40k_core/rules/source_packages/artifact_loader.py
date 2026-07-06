from __future__ import annotations

from importlib.resources import files
from typing import Final


class SourcePackageArtifactError(ValueError):
    """Raised when a committed generated-data artifact cannot be loaded."""


_JSON_SUFFIX: Final = ".json"


def package_artifact_bytes(package: str, relative_path: str) -> bytes:
    """Read a JSON artifact committed inside a Python package."""

    parts = _validated_relative_json_parts(relative_path)
    artifact = files(package)
    for part in parts:
        artifact = artifact.joinpath(part)
    if not artifact.is_file():
        raise SourcePackageArtifactError("Generated data artifact was not found.")
    return artifact.read_bytes()


def _validated_relative_json_parts(relative_path: str) -> tuple[str, ...]:
    if type(relative_path) is not str:
        raise SourcePackageArtifactError("Generated data artifact path must be a string.")
    if "\\" in relative_path:
        raise SourcePackageArtifactError("Generated data artifact path must use '/' separators.")
    if relative_path.startswith("/") or relative_path.endswith("/"):
        raise SourcePackageArtifactError("Generated data artifact path must be relative.")
    parts = tuple(part for part in relative_path.split("/") if part)
    if not parts or any(part == ".." for part in parts):
        raise SourcePackageArtifactError("Generated data artifact path must be normalized.")
    if not parts[-1].endswith(_JSON_SUFFIX):
        raise SourcePackageArtifactError("Generated data artifact path must reference JSON.")
    return parts
