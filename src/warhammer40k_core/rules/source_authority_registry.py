from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, cast

SourceAuthorityScope = Literal["warhammer_40000_11th_core_rules"]
AuditIdentityKind = Literal["legacy_inventory", "app_version", "observed_at"]

CORE_RULES_MAINTAINED_MIRROR_POLICY_ID = (
    "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
)
CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
CORE_RULES_SOURCE_AUTHORITY_SCOPE: SourceAuthorityScope = "warhammer_40000_11th_core_rules"
EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256 = (
    "edf13cf6091cd64450a5dd627eb727d626dc631f1b7b7dd6d55eec0c6a2b5c79"
)

_REGISTRY_PATH = Path(__file__).with_name("source_authority_registry.json")
_REGISTRY_SCHEMA = "core-v2-source-authority-registry-v1"
_REGISTRY_ID = "core-rules-source-authority-registry-2026-09-02"


class SourceAuthorityRegistryError(ValueError):
    """Raised when checked-in source-authority governance is missing or inconsistent."""


@dataclass(frozen=True, slots=True)
class AuditRowAuthorization:
    audit_id: str
    row_id: str
    source_observation_sha256: str
    provider_name: str
    source_url: str
    policy_id: str
    identity_kind: AuditIdentityKind
    identity_value: str | None


@dataclass(frozen=True, slots=True)
class LegacyObservationAuthorization:
    evidence_id: str
    rule_source_id: str
    observation_sha256: str


@dataclass(frozen=True, slots=True)
class SourcePackageAuthorization:
    namespace: str
    package_name: str
    version: str
    allowed_rule_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceAuthorityScopeRegistry:
    scope_id: SourceAuthorityScope
    edition: str
    corpus: str
    policy_ids: tuple[str, ...]
    audit_rows: tuple[AuditRowAuthorization, ...]
    legacy_observations: tuple[LegacyObservationAuthorization, ...]
    source_packages: tuple[SourcePackageAuthorization, ...]


@dataclass(frozen=True, slots=True)
class SourceAuthorityRegistry:
    registry_id: str
    scopes: tuple[SourceAuthorityScopeRegistry, ...]

    def __post_init__(self) -> None:
        if self.registry_id != _REGISTRY_ID:
            raise SourceAuthorityRegistryError("Source-authority registry ID is unsupported.")
        if not self.scopes:
            raise SourceAuthorityRegistryError("Source-authority registry requires a scope.")
        scope_ids = tuple(scope.scope_id for scope in self.scopes)
        if len(scope_ids) != len(set(scope_ids)):
            raise SourceAuthorityRegistryError(
                "Source-authority registry scope IDs must be unique."
            )
        policy_ids = tuple(policy_id for scope in self.scopes for policy_id in scope.policy_ids)
        if len(policy_ids) != len(set(policy_ids)):
            raise SourceAuthorityRegistryError(
                "Source-authority registry policy IDs must belong to exactly one scope."
            )

    def scope(self, scope_id: SourceAuthorityScope) -> SourceAuthorityScopeRegistry:
        for scope in self.scopes:
            if scope.scope_id == scope_id:
                return scope
        raise SourceAuthorityRegistryError("Source-authority scope is not registered.")

    def scope_for_policy_id(self, policy_id: str) -> SourceAuthorityScopeRegistry:
        for scope in self.scopes:
            if policy_id in scope.policy_ids:
                return scope
        raise SourceAuthorityRegistryError("Source-authority policy ID is not registered.")

    def authorize_audit_reference(
        self,
        *,
        policy_id: str,
        audit_id: str,
        row_id: str,
        source_observation_sha256: str,
        provider_name: str,
        source_url: str,
        observed_at: str | None,
        app_version: str | None,
    ) -> SourceAuthorityScope:
        scope = self.scope_for_policy_id(policy_id)
        row = next(
            (
                candidate
                for candidate in scope.audit_rows
                if candidate.audit_id == audit_id and candidate.row_id == row_id
            ),
            None,
        )
        if row is None:
            raise SourceAuthorityRegistryError(
                "Maintained App-mirror audit ID or row ID is not registered."
            )
        if (
            row.source_observation_sha256 != source_observation_sha256
            or row.provider_name != provider_name
            or row.source_url != source_url
            or row.policy_id != policy_id
        ):
            raise SourceAuthorityRegistryError(
                "Maintained App-mirror audit reference does not match its registered row."
            )
        if row.identity_kind == "app_version" and app_version != row.identity_value:
            raise SourceAuthorityRegistryError(
                "Maintained App-mirror App-data version does not match its registered audit row."
            )
        if row.identity_kind == "app_version" and observed_at is not None:
            raise SourceAuthorityRegistryError(
                "A version-indexed audit row cannot authenticate an observation timestamp."
            )
        if row.identity_kind == "observed_at" and observed_at != row.identity_value:
            raise SourceAuthorityRegistryError(
                "Maintained App-mirror timestamp does not match its registered audit row."
            )
        if row.identity_kind == "observed_at" and app_version is not None:
            raise SourceAuthorityRegistryError(
                "A timestamp-indexed audit row cannot authenticate an App-data version."
            )
        return scope.scope_id

    def authorize_legacy_observation(
        self,
        *,
        scope_id: SourceAuthorityScope,
        evidence_id: str,
        rule_source_id: str,
        observation_sha256: str,
    ) -> None:
        scope = self.scope(scope_id)
        if not any(
            row.evidence_id == evidence_id
            and row.rule_source_id == rule_source_id
            and row.observation_sha256 == observation_sha256
            for row in scope.legacy_observations
        ):
            raise SourceAuthorityRegistryError(
                "The superseded 40k.app policy is restricted to its immutable observation "
                "inventory."
            )

    def authorize_source_package(
        self,
        *,
        scope_id: SourceAuthorityScope,
        namespace: str,
        package_name: str,
        version: str,
        rule_source_ids: tuple[str, ...],
    ) -> None:
        scope = self.scope(scope_id)
        package = next(
            (
                candidate
                for candidate in scope.source_packages
                if (
                    candidate.namespace,
                    candidate.package_name,
                    candidate.version,
                )
                == (namespace, package_name, version)
            ),
            None,
        )
        if package is None:
            raise SourceAuthorityRegistryError(
                "RuleSourcePackage identity is not authorized for its source scope."
            )
        supplied_source_ids = set(rule_source_ids)
        registered_source_ids = set(package.allowed_rule_source_ids)
        if supplied_source_ids == registered_source_ids:
            return
        if supplied_source_ids.difference(registered_source_ids):
            raise SourceAuthorityRegistryError(
                "RuleSourcePackage contains a rule source ID outside its authorized source scope."
            )
        raise SourceAuthorityRegistryError(
            "RuleSourcePackage omits a rule source ID from its registered source inventory."
        )


def load_source_authority_registry_from_json_bytes(raw: bytes) -> SourceAuthorityRegistry:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256:
        raise SourceAuthorityRegistryError(
            "Source-authority registry bytes drifted from their reviewed pin."
        )
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceAuthorityRegistryError("Source-authority registry is not valid JSON.") from exc
    root = _exact_dict(
        payload,
        {"registry_schema", "registry_id", "scopes"},
        context="root",
    )
    if _text(root, "registry_schema") != _REGISTRY_SCHEMA:
        raise SourceAuthorityRegistryError("Source-authority registry schema is unsupported.")
    registry = SourceAuthorityRegistry(
        registry_id=_text(root, "registry_id"),
        scopes=tuple(_scope(row) for row in _object_rows(root, "scopes", context="scopes")),
    )
    _validate_registry_contents(registry)
    return registry


@cache
def source_authority_registry() -> SourceAuthorityRegistry:
    try:
        raw = _REGISTRY_PATH.read_bytes()
    except OSError as exc:
        raise SourceAuthorityRegistryError(
            "Packaged source-authority registry could not be read."
        ) from exc
    return load_source_authority_registry_from_json_bytes(raw)


def _scope(payload: dict[str, object]) -> SourceAuthorityScopeRegistry:
    row = _exact_dict(
        payload,
        {
            "scope_id",
            "edition",
            "corpus",
            "policy_ids",
            "audit_rows",
            "legacy_observations",
            "source_packages",
        },
        context="scope",
    )
    scope_id = _text(row, "scope_id")
    if scope_id != CORE_RULES_SOURCE_AUTHORITY_SCOPE:
        raise SourceAuthorityRegistryError("Source-authority scope ID is unsupported.")
    return SourceAuthorityScopeRegistry(
        scope_id=scope_id,
        edition=_text(row, "edition"),
        corpus=_text(row, "corpus"),
        policy_ids=_text_tuple(row, "policy_ids"),
        audit_rows=tuple(
            _audit_row(item) for item in _object_rows(row, "audit_rows", context="audit rows")
        ),
        legacy_observations=tuple(
            _legacy_observation(item)
            for item in _object_rows(row, "legacy_observations", context="legacy observations")
        ),
        source_packages=tuple(
            _source_package(item)
            for item in _object_rows(row, "source_packages", context="source packages")
        ),
    )


def _audit_row(payload: dict[str, object]) -> AuditRowAuthorization:
    row = _exact_dict(
        payload,
        {
            "audit_id",
            "row_id",
            "source_observation_sha256",
            "provider_name",
            "source_url",
            "policy_id",
            "identity_kind",
            "identity_value",
        },
        context="audit row",
    )
    identity_kind = _text(row, "identity_kind")
    if identity_kind not in {"legacy_inventory", "app_version", "observed_at"}:
        raise SourceAuthorityRegistryError("Audit-row identity kind is unsupported.")
    identity_value = _optional_text(row, "identity_value")
    if (identity_kind == "legacy_inventory") != (identity_value is None):
        raise SourceAuthorityRegistryError(
            "Audit-row identity value must be absent only for legacy inventory rows."
        )
    return AuditRowAuthorization(
        audit_id=_text(row, "audit_id"),
        row_id=_text(row, "row_id"),
        source_observation_sha256=_sha256(row, "source_observation_sha256"),
        provider_name=_text(row, "provider_name"),
        source_url=_text(row, "source_url"),
        policy_id=_text(row, "policy_id"),
        identity_kind=cast(AuditIdentityKind, identity_kind),
        identity_value=identity_value,
    )


def _legacy_observation(payload: dict[str, object]) -> LegacyObservationAuthorization:
    row = _exact_dict(
        payload,
        {"evidence_id", "rule_source_id", "observation_sha256"},
        context="legacy observation",
    )
    return LegacyObservationAuthorization(
        evidence_id=_text(row, "evidence_id"),
        rule_source_id=_text(row, "rule_source_id"),
        observation_sha256=_sha256(row, "observation_sha256"),
    )


def _source_package(payload: dict[str, object]) -> SourcePackageAuthorization:
    row = _exact_dict(
        payload,
        {"namespace", "package_name", "version", "allowed_rule_source_ids"},
        context="source package",
    )
    return SourcePackageAuthorization(
        namespace=_text(row, "namespace"),
        package_name=_text(row, "package_name"),
        version=_text(row, "version"),
        allowed_rule_source_ids=_text_tuple(row, "allowed_rule_source_ids"),
    )


def _validate_registry_contents(registry: SourceAuthorityRegistry) -> None:
    for scope in registry.scopes:
        if scope.edition != "warhammer_40000_11th" or scope.corpus != (
            "core_rules_categories_01_25"
        ):
            raise SourceAuthorityRegistryError(
                "Source-authority scope edition or corpus is unsupported."
            )
        if set(scope.policy_ids) != {
            CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID,
            CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
        }:
            raise SourceAuthorityRegistryError(
                "Core Rules source-authority policies are incomplete."
            )
        audit_keys = tuple((row.audit_id, row.row_id) for row in scope.audit_rows)
        if len(audit_keys) != len(set(audit_keys)):
            raise SourceAuthorityRegistryError("Audit registry row identities must be unique.")
        if {row.policy_id for row in scope.audit_rows} != set(scope.policy_ids):
            raise SourceAuthorityRegistryError(
                "Every source-authority policy requires registered audit rows."
            )
        if any(
            (row.policy_id == CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID)
            != (row.identity_kind == "legacy_inventory")
            for row in scope.audit_rows
        ):
            raise SourceAuthorityRegistryError(
                "Legacy and current audit-row identity kinds must remain policy-scoped."
            )
        legacy_ids = tuple(row.evidence_id for row in scope.legacy_observations)
        legacy_hashes = tuple(row.observation_sha256 for row in scope.legacy_observations)
        if len(legacy_ids) != len(set(legacy_ids)) or len(legacy_hashes) != len(set(legacy_hashes)):
            raise SourceAuthorityRegistryError(
                "Legacy observation identities and hashes must be unique."
            )
        package_ids = tuple(
            (row.namespace, row.package_name, row.version) for row in scope.source_packages
        )
        if len(package_ids) != len(set(package_ids)):
            raise SourceAuthorityRegistryError(
                "Source-authority package identities must be unique."
            )
        allowed_rule_source_ids = tuple(
            source_id
            for package in scope.source_packages
            for source_id in package.allowed_rule_source_ids
        )
        if len(allowed_rule_source_ids) != len(set(allowed_rule_source_ids)):
            raise SourceAuthorityRegistryError(
                "Rule source IDs must belong to exactly one authorized source package."
            )
        if not {row.rule_source_id for row in scope.legacy_observations}.issubset(
            allowed_rule_source_ids
        ):
            raise SourceAuthorityRegistryError(
                "Legacy observations must name an authorized Core Rules source ID."
            )


def _exact_dict(
    payload: object,
    expected_fields: set[str],
    *,
    context: str,
) -> dict[str, object]:
    if type(payload) is not dict:
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {context} must be an object."
        )
    row = cast(dict[str, object], payload)
    if set(row) != expected_fields:
        raise SourceAuthorityRegistryError(f"Source-authority registry {context} fields drifted.")
    return row


def _object_rows(
    payload: dict[str, object],
    field_name: str,
    *,
    context: str,
) -> tuple[dict[str, object], ...]:
    value = payload.get(field_name)
    if type(value) is not list or not value:
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {context} must be a non-empty list."
        )
    return tuple(_exact_object(item, context=context) for item in cast(list[object], value))


def _exact_object(payload: object, *, context: str) -> dict[str, object]:
    if type(payload) is not dict:
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {context} rows must be objects."
        )
    return cast(dict[str, object], payload)


def _text(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if type(value) is not str or not value or value != value.strip():
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {field_name} must be non-empty stripped text."
        )
    return value


def _optional_text(payload: dict[str, object], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    return _text(payload, field_name)


def _text_tuple(payload: dict[str, object], field_name: str) -> tuple[str, ...]:
    value = payload.get(field_name)
    if type(value) is not list or not value:
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {field_name} must be a non-empty list."
        )
    values = tuple(_text({field_name: item}, field_name) for item in cast(list[object], value))
    if len(values) != len(set(values)):
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {field_name} must contain unique values."
        )
    return values


def _sha256(payload: dict[str, object], field_name: str) -> str:
    value = _text(payload, field_name)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise SourceAuthorityRegistryError(
            f"Source-authority registry {field_name} must be a lowercase SHA-256 digest."
        )
    return value


__all__ = (
    "CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID",
    "CORE_RULES_MAINTAINED_MIRROR_POLICY_ID",
    "CORE_RULES_SOURCE_AUTHORITY_SCOPE",
    "EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256",
    "SourceAuthorityRegistry",
    "SourceAuthorityRegistryError",
    "SourceAuthorityScope",
    "load_source_authority_registry_from_json_bytes",
    "source_authority_registry",
)
