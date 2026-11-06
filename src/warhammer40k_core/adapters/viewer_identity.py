"""Schema-directed identities for an already redacted viewer history.

This module does not decide visibility. The shared redaction owner supplies only
visible records. Authoritative identities never change, including during replay.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError

# These are contract fields, not a replacement of arbitrary strings or entity IDs.
_IDENTITY_FIELDS = {
    "request_id": "request",
    "pending_request_id": "request",
    "source_request_id": "request",
    "decision_request_id": "request",
    "proposal_request_id": "request",
    "reroll_request_id": "request",
    "retained_request_id": "request",
    "source_decision_request_id": "request",
    "record_id": "record",
    "decision_record_id": "record",
    "source_record_id": "record",
    "event_id": "event",
    "source_event_id": "event",
    "anchor_event_ids": "event",
    "result_id": "result",
    "decision_id": "result",
    "resolving_decision_id": "result",
    "decision_ids": "result",
    "source_result_id": "result",
    "opportunity_id": "opportunity",
    "window_id": "window",
    "context_hash": "context",
    "state_hash": "state",
    "based_on_state_hash": "state",
    "legal_action_fingerprint": "legal-action",
    "source_context_id": "source-context",
}
_REFERENCE_FIELD = re.compile(r"(?:^|_)(request|record|event|result|roll|window|opportunity)_ids?$")
_DYNAMIC_REFERENCE_KEYS = frozenset({"source_key", "completion_key", "effect_key"})
_REFERENCE_TEXT_FIELDS = frozenset({"label", "message", "reason"})
_VISIBLE_REFERENCE = re.compile(r"view-(request|record|event|roll)-[a-f0-9]{64}")
_SEQUENCE_FIELDS = frozenset({"sequence_number", "created_sequence_number"})
_AUTHORITATIVE_ORDINAL_ID = re.compile(r"(?:decision-request|decision-record|event|roll)-[0-9]{6,}")
_CATALOG_RECORD_FIELDS = frozenset(
    {
        "catalog_record_id",
        "catalog_record_ids",
        "selected_catalog_record_id",
        "source_catalog_record_id",
        "mfm_unit_record_id",
    }
)
_PUBLIC_TEXT_FIELDS = frozenset({"label", "message", "unit_display_name", "model_display_name"})
_ENTITY_MAP_FIELDS = {
    "unit_display_by_id": "unit_instance_id",
    "model_display_by_id": "model_instance_id",
    "models_by_id": "model_instance_id",
    "terrain_features_by_id": "terrain_feature_id",
    "terrain_areas_by_id": "terrain_area_id",
    "objectives_by_id": "objective_id",
    "deployment_zones_by_id": "deployment_zone_id",
    "battlefield_regions_by_id": "region_id",
    "hit_regions_by_entity_id": "entity_id",
    "hints_by_entity_id": "entity_id",
}


def _stable_entity_field(key: str) -> bool:
    return key in {
        "game_id",
        "game_ids",
        "actor_id",
        "actor_ids",
        "player_id",
        "player_ids",
        "army_id",
        "army_ids",
    } or key.endswith(
        (
            "_game_id",
            "_game_ids",
            "_actor_id",
            "_actor_ids",
            "_player_id",
            "_player_ids",
            "_army_id",
            "_army_ids",
        )
    )


def _entity_field(key: str) -> bool:
    return (
        _stable_entity_field(key)
        or key
        in {
            "unit_instance_id",
            "model_instance_id",
        }
        or key.endswith(
            ("_unit_instance_id", "_unit_instance_ids", "_model_instance_id", "_model_instance_ids")
        )
    )


def _identity_family(key: str, value: str) -> str | None:
    if _stable_entity_field(key) or key in _CATALOG_RECORD_FIELDS:
        return None
    explicit = _IDENTITY_FIELDS.get(key)
    if explicit is not None:
        return explicit
    if key.endswith(("_id", "_ids")):
        reference = _REFERENCE_FIELD.search(key)
        if reference is not None:
            return reference.group(1)
    elif key not in _DYNAMIC_REFERENCE_KEYS:
        return None
    if _AUTHORITATIVE_ORDINAL_ID.search(value) or value.startswith("view-derived-"):
        return "derived"
    return None


class ViewerIdentityError(GameLifecycleError):
    """A proposal refers to an identity this viewer was never issued."""


@dataclass(slots=True)
class ViewerIdentityMap:
    """A reversible map built in visible-history order for one viewer domain."""

    domain: str
    _forward: dict[tuple[str, str], str] = field(
        default_factory=dict[tuple[str, str], str], init=False
    )
    _reverse: dict[tuple[str, str], str] = field(
        default_factory=dict[tuple[str, str], str], init=False
    )
    _counts: dict[str, int] = field(default_factory=dict[str, int], init=False)
    _sequence: dict[int, int] = field(default_factory=dict[int, int], init=False)
    _issued_sequences: dict[tuple[str, int], int] = field(
        default_factory=dict[tuple[str, int], int], init=False
    )

    def bind_sequence(self, authoritative: int, visible: int) -> None:
        self._sequence[authoritative] = visible

    def project(self, value: JsonValue, *, key: str = "", scope: str = "view") -> JsonValue:
        if isinstance(value, dict):
            request_id = value.get("request_id")
            if isinstance(request_id, str) and request_id != "hidden-request":
                projected_id = self.project(request_id, key="request_id")
                assert isinstance(projected_id, str)
                scope = projected_id
            elif isinstance(value.get("event_id"), str):
                projected_event = self.project(value["event_id"], key="event_id")
                assert isinstance(projected_event, str)
                scope = projected_event
            if key in _ENTITY_MAP_FIELDS:
                entity_key = _ENTITY_MAP_FIELDS[key]
                return {
                    str(self.project(name, key=entity_key)): self.project(item, scope=scope)
                    for name, item in sorted(value.items())
                }
            if any(_AUTHORITATIVE_ORDINAL_ID.search(name) for name in value):
                raise ViewerIdentityError(
                    f"Public payload has an undeclared identity-keyed mapping: {key}."
                )
            # JSON object order is not identity. Re-encoding a saved event with
            # sorted keys must preserve exactly the same issued aliases.
            return {
                name: self.project(item, key=name, scope=scope)
                for name, item in sorted(value.items())
            }
        if isinstance(value, list):
            return [self.project(item, key=key, scope=scope) for item in value]
        if key in _REFERENCE_TEXT_FIELDS and isinstance(value, str):
            return _AUTHORITATIVE_ORDINAL_ID.sub(self._project_text_reference, value)
        family = _identity_family(key, value) if isinstance(value, str) else None
        if (
            family is not None
            and isinstance(value, str)
            and value not in {"hidden-request", "hidden-result"}
        ):
            # Hash equality must not reveal whether hidden authority changed
            # between two otherwise equivalent public requests. Reference IDs
            # retain their stream joins; opaque authority hashes bind per request.
            authority_value = (
                canonical_json([scope, value])
                if family in {"context", "state", "legal-action"}
                else value
            )
            binding = (family, authority_value)
            if binding not in self._forward:
                count = self._counts.get(family, 0) + 1
                digest = hashlib.sha256(
                    f"viewer-identity-v1:{self.domain}:{family}:{count}".encode()
                )
                alias = digest.hexdigest()
                if family not in {"context", "state", "legal-action"}:
                    alias = f"view-{family}-{alias}"
                self._counts[family] = count
                self._forward[binding] = alias
                self._reverse[(family, alias)] = value
            return self._forward[binding]
        if key in _SEQUENCE_FIELDS and type(value) is int:
            if value not in self._sequence:
                raise GameLifecycleError("Viewer sequence has no authoritative history binding.")
            visible = self._sequence[value]
            self._issued_sequences[(key, visible)] = value
            return visible
        if (
            isinstance(value, str)
            and key not in _PUBLIC_TEXT_FIELDS
            and not _entity_field(key)
            and _AUTHORITATIVE_ORDINAL_ID.search(value)
        ):
            raise ViewerIdentityError(
                f"Public payload contains an undeclared authoritative identity field: {key}."
            )
        return value

    def resolve(self, value: JsonValue, *, key: str = "") -> JsonValue:
        if isinstance(value, dict):
            if key in _ENTITY_MAP_FIELDS:
                entity_key = _ENTITY_MAP_FIELDS[key]
                return {
                    str(self.resolve(name, key=entity_key)): self.resolve(item)
                    for name, item in value.items()
                }
            return {name: self.resolve(item, key=name) for name, item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item, key=key) for item in value]
        if key in _REFERENCE_TEXT_FIELDS and isinstance(value, str):
            return _VISIBLE_REFERENCE.sub(self._resolve_text_reference, value)
        family = _identity_family(key, value) if isinstance(value, str) else None
        if family is not None and isinstance(value, str):
            binding = (family, value)
            if binding not in self._reverse:
                raise ViewerIdentityError(
                    "Invalid submission contains an unissued viewer identity."
                )
            return self._reverse[binding]
        if key in _SEQUENCE_FIELDS and type(value) is int:
            sequence_binding = (key, value)
            if sequence_binding not in self._issued_sequences:
                raise ViewerIdentityError("Invalid submission viewer sequence was not issued.")
            return self._issued_sequences[sequence_binding]
        return value

    def _project_text_reference(self, match: re.Match[str]) -> str:
        token = match.group()
        kind = token.rsplit("-", 1)[0]
        key = {
            "decision-request": "request_id",
            "decision-record": "record_id",
            "event": "event_id",
            "roll": "roll_id",
        }[kind]
        alias = self.project(token, key=key)
        assert isinstance(alias, str)
        return alias

    def _resolve_text_reference(self, match: re.Match[str]) -> str:
        alias = self.resolve(match.group(), key=f"{match.group(1)}_id")
        assert isinstance(alias, str)
        return alias
