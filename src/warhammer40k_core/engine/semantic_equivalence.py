from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self, TypedDict, cast

from warhammer40k_core.rules.rule_ir import RuleIR

SEMANTIC_EQUIVALENCE_SCHEMA_VERSION = "cross-source-semantic-equivalence-v1"


class SemanticEquivalenceError(ValueError):
    """Raised when cross-source semantic-equivalence evidence is invalid."""


class SemanticContentKind(StrEnum):
    FACTION_RULE = "faction_rule"
    DATASHEET_ABILITY = "datasheet_ability"
    DETACHMENT_RULE = "detachment_rule"
    ENHANCEMENT = "enhancement"
    STRATAGEM = "stratagem"


class SemanticEquivalenceBasis(StrEnum):
    STRUCTURED_RULE_IR = "structured_rule_ir"
    EXACT_NORMALIZED_TEXT = "exact_normalized_text"
    SOURCE_TEXT_UNAVAILABLE = "source_text_unavailable"


class SemanticExecutionStatus(StrEnum):
    ENGINE_CONSUMED = "engine_consumed"
    GENERIC_IR_EXECUTABLE = "generic_ir_executable"
    NAMED_HANDLER_EXECUTABLE = "named_handler_executable"
    BLOCKED_STRUCTURED_SEMANTICS = "blocked_structured_semantics"
    SOURCE_ONLY = "source_only"


class SemanticSupportTransfer(StrEnum):
    CONTENT_NEUTRAL_GENERIC_IR = "content_neutral_generic_ir"
    NONE = "none"


class SemanticEquivalenceMemberPayload(TypedDict):
    member_id: str
    content_kind: str
    rules_surface: str
    faction_id: str
    faction_name: str
    owner_id: str
    owner_name: str
    rule_id: str
    rule_name: str
    source_row_ids: list[str]
    source_text_ids: list[str]
    normalized_text_hash: str | None
    semantic_hash: str | None
    semantic_context_hash: str
    equivalence_hash: str | None
    equivalence_basis: str
    execution_status: str
    runtime_consumer_ids: list[str]
    support_transfer: str
    diagnostic_reasons: list[str]


class SemanticEquivalenceGroupPayload(TypedDict):
    group_id: str
    equivalence_hash: str
    equivalence_basis: str
    content_kind: str
    rules_surface: str
    member_ids: list[str]
    faction_ids: list[str]
    execution_statuses: list[str]
    runtime_consumer_ids: list[str]
    support_transfer: str


class CrossSourceSemanticAuditPayload(TypedDict):
    schema_version: str
    generated_by: str
    upstream_execution_checksum_sha256: str
    source_artifact_hashes: dict[str, str]
    source_payload_checksum_sha256: str
    member_count: int
    structured_member_count: int
    exact_text_only_member_count: int
    source_text_unavailable_member_count: int
    equivalent_group_count: int
    cross_faction_group_count: int
    members: list[SemanticEquivalenceMemberPayload]
    equivalence_groups: list[SemanticEquivalenceGroupPayload]


@dataclass(frozen=True, slots=True)
class SemanticEquivalenceMember:
    member_id: str
    content_kind: SemanticContentKind
    rules_surface: str
    faction_id: str
    faction_name: str
    owner_id: str
    owner_name: str
    rule_id: str
    rule_name: str
    source_row_ids: tuple[str, ...]
    source_text_ids: tuple[str, ...]
    semantic_context_hash: str
    equivalence_basis: SemanticEquivalenceBasis
    execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]
    support_transfer: SemanticSupportTransfer
    normalized_text_hash: str | None = None
    semantic_hash: str | None = None
    equivalence_hash: str | None = None
    diagnostic_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "member_id", _text("member_id", self.member_id))
        object.__setattr__(
            self,
            "content_kind",
            _enum_value(SemanticContentKind, "content_kind", self.content_kind),
        )
        object.__setattr__(self, "rules_surface", _text("rules_surface", self.rules_surface))
        object.__setattr__(self, "faction_id", _text("faction_id", self.faction_id))
        object.__setattr__(self, "faction_name", _text("faction_name", self.faction_name))
        object.__setattr__(self, "owner_id", _text("owner_id", self.owner_id))
        object.__setattr__(self, "owner_name", _text("owner_name", self.owner_name))
        object.__setattr__(self, "rule_id", _text("rule_id", self.rule_id))
        object.__setattr__(self, "rule_name", _text("rule_name", self.rule_name))
        object.__setattr__(
            self,
            "source_row_ids",
            _text_tuple("source_row_ids", self.source_row_ids, allow_empty=True),
        )
        object.__setattr__(
            self,
            "source_text_ids",
            _text_tuple("source_text_ids", self.source_text_ids, allow_empty=True),
        )
        object.__setattr__(
            self,
            "semantic_context_hash",
            _sha256("semantic_context_hash", self.semantic_context_hash),
        )
        basis = _enum_value(
            SemanticEquivalenceBasis,
            "equivalence_basis",
            self.equivalence_basis,
        )
        object.__setattr__(self, "equivalence_basis", basis)
        status = _enum_value(
            SemanticExecutionStatus,
            "execution_status",
            self.execution_status,
        )
        object.__setattr__(self, "execution_status", status)
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _text_tuple(
                "runtime_consumer_ids",
                self.runtime_consumer_ids,
                allow_empty=True,
            ),
        )
        transfer = _enum_value(
            SemanticSupportTransfer,
            "support_transfer",
            self.support_transfer,
        )
        object.__setattr__(self, "support_transfer", transfer)
        object.__setattr__(
            self,
            "diagnostic_reasons",
            _text_tuple(
                "diagnostic_reasons",
                self.diagnostic_reasons,
                allow_empty=True,
            ),
        )
        if self.normalized_text_hash is not None:
            object.__setattr__(
                self,
                "normalized_text_hash",
                _sha256("normalized_text_hash", self.normalized_text_hash),
            )
        if self.semantic_hash is not None:
            object.__setattr__(
                self,
                "semantic_hash",
                _sha256("semantic_hash", self.semantic_hash),
            )
        if self.equivalence_hash is not None:
            object.__setattr__(
                self,
                "equivalence_hash",
                _sha256("equivalence_hash", self.equivalence_hash),
            )
        self._validate_evidence_shape()

    def _validate_evidence_shape(self) -> None:
        if self.equivalence_basis is SemanticEquivalenceBasis.SOURCE_TEXT_UNAVAILABLE:
            if self.source_text_ids:
                raise SemanticEquivalenceError(
                    "Source-unavailable members cannot include source_text_ids."
                )
            if any(
                value is not None
                for value in (
                    self.normalized_text_hash,
                    self.semantic_hash,
                    self.equivalence_hash,
                )
            ):
                raise SemanticEquivalenceError(
                    "Source-unavailable members cannot include semantic hashes."
                )
            return
        if not self.source_text_ids or self.normalized_text_hash is None:
            raise SemanticEquivalenceError(
                "Source-backed semantic members require source text evidence."
            )
        if self.equivalence_hash is None:
            raise SemanticEquivalenceError(
                "Source-backed semantic members require an equivalence_hash."
            )
        if self.equivalence_basis is SemanticEquivalenceBasis.STRUCTURED_RULE_IR:
            if self.semantic_hash is None:
                raise SemanticEquivalenceError("Structured semantic members require semantic_hash.")
        elif self.semantic_hash is not None:
            raise SemanticEquivalenceError(
                "Exact-text-only semantic members cannot include semantic_hash."
            )
        if self.support_transfer is SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR:
            if self.content_kind is not SemanticContentKind.DATASHEET_ABILITY:
                raise SemanticEquivalenceError(
                    "Content-neutral generic transfer is limited to datasheet abilities."
                )
            if self.equivalence_basis is not SemanticEquivalenceBasis.STRUCTURED_RULE_IR:
                raise SemanticEquivalenceError(
                    "Content-neutral generic transfer requires structured RuleIR."
                )
            if self.execution_status is not SemanticExecutionStatus.ENGINE_CONSUMED:
                raise SemanticEquivalenceError(
                    "Content-neutral generic transfer requires engine-consumed semantics."
                )
            if not self.runtime_consumer_ids:
                raise SemanticEquivalenceError(
                    "Content-neutral generic transfer requires runtime consumers."
                )

    def to_payload(self) -> SemanticEquivalenceMemberPayload:
        return {
            "member_id": self.member_id,
            "content_kind": self.content_kind.value,
            "rules_surface": self.rules_surface,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "source_row_ids": list(self.source_row_ids),
            "source_text_ids": list(self.source_text_ids),
            "normalized_text_hash": self.normalized_text_hash,
            "semantic_hash": self.semantic_hash,
            "semantic_context_hash": self.semantic_context_hash,
            "equivalence_hash": self.equivalence_hash,
            "equivalence_basis": self.equivalence_basis.value,
            "execution_status": self.execution_status.value,
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "support_transfer": self.support_transfer.value,
            "diagnostic_reasons": list(self.diagnostic_reasons),
        }

    @classmethod
    def from_payload(cls, payload: SemanticEquivalenceMemberPayload) -> Self:
        return cls(
            member_id=payload["member_id"],
            content_kind=_enum_value(
                SemanticContentKind,
                "content_kind",
                payload["content_kind"],
            ),
            rules_surface=payload["rules_surface"],
            faction_id=payload["faction_id"],
            faction_name=payload["faction_name"],
            owner_id=payload["owner_id"],
            owner_name=payload["owner_name"],
            rule_id=payload["rule_id"],
            rule_name=payload["rule_name"],
            source_row_ids=tuple(payload["source_row_ids"]),
            source_text_ids=tuple(payload["source_text_ids"]),
            normalized_text_hash=payload["normalized_text_hash"],
            semantic_hash=payload["semantic_hash"],
            semantic_context_hash=payload["semantic_context_hash"],
            equivalence_hash=payload["equivalence_hash"],
            equivalence_basis=_enum_value(
                SemanticEquivalenceBasis,
                "equivalence_basis",
                payload["equivalence_basis"],
            ),
            execution_status=_enum_value(
                SemanticExecutionStatus,
                "execution_status",
                payload["execution_status"],
            ),
            runtime_consumer_ids=tuple(payload["runtime_consumer_ids"]),
            support_transfer=_enum_value(
                SemanticSupportTransfer,
                "support_transfer",
                payload["support_transfer"],
            ),
            diagnostic_reasons=tuple(payload["diagnostic_reasons"]),
        )


@dataclass(frozen=True, slots=True)
class SemanticEquivalenceGroup:
    group_id: str
    equivalence_hash: str
    equivalence_basis: SemanticEquivalenceBasis
    content_kind: SemanticContentKind
    rules_surface: str
    member_ids: tuple[str, ...]
    faction_ids: tuple[str, ...]
    execution_statuses: tuple[SemanticExecutionStatus, ...]
    runtime_consumer_ids: tuple[str, ...]
    support_transfer: SemanticSupportTransfer

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", _text("group_id", self.group_id))
        object.__setattr__(
            self,
            "equivalence_hash",
            _sha256("equivalence_hash", self.equivalence_hash),
        )
        object.__setattr__(
            self,
            "equivalence_basis",
            _enum_value(
                SemanticEquivalenceBasis,
                "equivalence_basis",
                self.equivalence_basis,
            ),
        )
        object.__setattr__(
            self,
            "content_kind",
            _enum_value(SemanticContentKind, "content_kind", self.content_kind),
        )
        object.__setattr__(self, "rules_surface", _text("rules_surface", self.rules_surface))
        object.__setattr__(
            self,
            "member_ids",
            _text_tuple("member_ids", self.member_ids, minimum=2),
        )
        object.__setattr__(
            self,
            "faction_ids",
            _text_tuple("faction_ids", self.faction_ids),
        )
        if type(self.execution_statuses) is not tuple or not self.execution_statuses:
            raise SemanticEquivalenceError("execution_statuses must be a non-empty tuple.")
        object.__setattr__(
            self,
            "execution_statuses",
            tuple(
                sorted(
                    {
                        _enum_value(
                            SemanticExecutionStatus,
                            "execution_status",
                            value,
                        )
                        for value in self.execution_statuses
                    },
                    key=lambda value: value.value,
                )
            ),
        )
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _text_tuple(
                "runtime_consumer_ids",
                self.runtime_consumer_ids,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "support_transfer",
            _enum_value(
                SemanticSupportTransfer,
                "support_transfer",
                self.support_transfer,
            ),
        )

    def to_payload(self) -> SemanticEquivalenceGroupPayload:
        return {
            "group_id": self.group_id,
            "equivalence_hash": self.equivalence_hash,
            "equivalence_basis": self.equivalence_basis.value,
            "content_kind": self.content_kind.value,
            "rules_surface": self.rules_surface,
            "member_ids": list(self.member_ids),
            "faction_ids": list(self.faction_ids),
            "execution_statuses": [status.value for status in self.execution_statuses],
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
            "support_transfer": self.support_transfer.value,
        }

    @classmethod
    def from_payload(cls, payload: SemanticEquivalenceGroupPayload) -> Self:
        return cls(
            group_id=payload["group_id"],
            equivalence_hash=payload["equivalence_hash"],
            equivalence_basis=_enum_value(
                SemanticEquivalenceBasis,
                "equivalence_basis",
                payload["equivalence_basis"],
            ),
            content_kind=_enum_value(
                SemanticContentKind,
                "content_kind",
                payload["content_kind"],
            ),
            rules_surface=payload["rules_surface"],
            member_ids=tuple(payload["member_ids"]),
            faction_ids=tuple(payload["faction_ids"]),
            execution_statuses=tuple(
                _enum_value(
                    SemanticExecutionStatus,
                    "execution_status",
                    value,
                )
                for value in payload["execution_statuses"]
            ),
            runtime_consumer_ids=tuple(payload["runtime_consumer_ids"]),
            support_transfer=_enum_value(
                SemanticSupportTransfer,
                "support_transfer",
                payload["support_transfer"],
            ),
        )


@dataclass(frozen=True, slots=True)
class CrossSourceSemanticAudit:
    generated_by: str
    upstream_execution_checksum_sha256: str
    source_artifact_hashes: Mapping[str, str]
    members: tuple[SemanticEquivalenceMember, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "generated_by", _text("generated_by", self.generated_by))
        object.__setattr__(
            self,
            "upstream_execution_checksum_sha256",
            _sha256(
                "upstream_execution_checksum_sha256",
                self.upstream_execution_checksum_sha256,
            ),
        )
        object.__setattr__(
            self,
            "source_artifact_hashes",
            _hash_mapping("source_artifact_hashes", self.source_artifact_hashes),
        )
        object.__setattr__(self, "members", _members(self.members))

    def equivalence_groups(self) -> tuple[SemanticEquivalenceGroup, ...]:
        grouped: dict[str, list[SemanticEquivalenceMember]] = {}
        for member in self.members:
            if member.equivalence_hash is not None:
                grouped.setdefault(member.equivalence_hash, []).append(member)
        return tuple(
            _equivalence_group(equivalence_hash, tuple(members))
            for equivalence_hash, members in sorted(grouped.items())
            if len(members) > 1
        )

    def groups_for_faction(self, faction_id: str) -> tuple[SemanticEquivalenceGroup, ...]:
        faction = _text("faction_id", faction_id)
        return tuple(group for group in self.equivalence_groups() if faction in group.faction_ids)

    def members_for_group(
        self,
        group: SemanticEquivalenceGroup,
    ) -> tuple[SemanticEquivalenceMember, ...]:
        if type(group) is not SemanticEquivalenceGroup:
            raise SemanticEquivalenceError("members_for_group requires an equivalence group.")
        by_id = {member.member_id: member for member in self.members}
        return tuple(by_id[member_id] for member_id in group.member_ids)

    def member(
        self,
        *,
        content_kind: SemanticContentKind,
        owner_id: str,
        rule_name: str,
    ) -> SemanticEquivalenceMember:
        matches = tuple(
            member
            for member in self.members
            if member.content_kind is content_kind
            and member.owner_id == owner_id
            and member.rule_name == rule_name
        )
        if len(matches) != 1:
            raise SemanticEquivalenceError(
                "Semantic audit member lookup requires exactly one matching member."
            )
        return matches[0]

    def payload_without_checksum(self) -> CrossSourceSemanticAuditPayload:
        groups = self.equivalence_groups()
        structured_count = sum(
            member.equivalence_basis is SemanticEquivalenceBasis.STRUCTURED_RULE_IR
            for member in self.members
        )
        exact_text_count = sum(
            member.equivalence_basis is SemanticEquivalenceBasis.EXACT_NORMALIZED_TEXT
            for member in self.members
        )
        source_unavailable_count = sum(
            member.equivalence_basis is SemanticEquivalenceBasis.SOURCE_TEXT_UNAVAILABLE
            for member in self.members
        )
        return {
            "schema_version": SEMANTIC_EQUIVALENCE_SCHEMA_VERSION,
            "generated_by": self.generated_by,
            "upstream_execution_checksum_sha256": self.upstream_execution_checksum_sha256,
            "source_artifact_hashes": dict(self.source_artifact_hashes),
            "source_payload_checksum_sha256": "",
            "member_count": len(self.members),
            "structured_member_count": structured_count,
            "exact_text_only_member_count": exact_text_count,
            "source_text_unavailable_member_count": source_unavailable_count,
            "equivalent_group_count": len(groups),
            "cross_faction_group_count": sum(len(group.faction_ids) > 1 for group in groups),
            "members": [member.to_payload() for member in self.members],
            "equivalence_groups": [group.to_payload() for group in groups],
        }

    def source_payload_checksum_sha256(self) -> str:
        return _payload_hash(self.payload_without_checksum())

    def to_payload(self) -> CrossSourceSemanticAuditPayload:
        payload = self.payload_without_checksum()
        payload["source_payload_checksum_sha256"] = self.source_payload_checksum_sha256()
        return payload

    @classmethod
    def from_payload(cls, payload: CrossSourceSemanticAuditPayload) -> Self:
        if payload["schema_version"] != SEMANTIC_EQUIVALENCE_SCHEMA_VERSION:
            raise SemanticEquivalenceError(
                "Cross-source semantic audit schema version is unsupported."
            )
        audit = cls(
            generated_by=payload["generated_by"],
            upstream_execution_checksum_sha256=payload["upstream_execution_checksum_sha256"],
            source_artifact_hashes=payload["source_artifact_hashes"],
            members=tuple(
                SemanticEquivalenceMember.from_payload(member) for member in payload["members"]
            ),
        )
        if audit.to_payload() != payload:
            raise SemanticEquivalenceError("Cross-source semantic audit payload is stale.")
        return audit


def semantic_member_from_rule_ir(
    *,
    member_id: str,
    content_kind: SemanticContentKind,
    rules_surface: str,
    faction_id: str,
    faction_name: str,
    owner_id: str,
    owner_name: str,
    rule_id: str,
    rule_name: str,
    source_row_ids: tuple[str, ...],
    source_text_ids: tuple[str, ...],
    semantic_context: Mapping[str, object],
    normalized_text: str,
    rule_ir: RuleIR,
    execution_status: SemanticExecutionStatus,
    runtime_consumer_ids: tuple[str, ...],
    support_transfer: SemanticSupportTransfer = SemanticSupportTransfer.NONE,
) -> SemanticEquivalenceMember:
    if type(rule_ir) is not RuleIR:
        raise SemanticEquivalenceError("Semantic member construction requires RuleIR.")
    normalized = _text("normalized_text", normalized_text)
    context_hash = _payload_hash(_json_mapping("semantic_context", semantic_context))
    text_hash = _text_hash(normalized)
    if rule_ir.is_supported:
        basis = SemanticEquivalenceBasis.STRUCTURED_RULE_IR
        semantic_hash = rule_ir.semantic_hash()
        evidence_hash = semantic_hash
        diagnostics: tuple[str, ...] = ()
    else:
        basis = SemanticEquivalenceBasis.EXACT_NORMALIZED_TEXT
        semantic_hash = None
        evidence_hash = text_hash
        diagnostics = tuple(sorted({diagnostic.reason.value for diagnostic in rule_ir.diagnostics}))
        if not diagnostics:
            diagnostics = tuple(
                sorted(
                    {
                        clause.unsupported_reason.value
                        for clause in rule_ir.clauses
                        if clause.unsupported_reason is not None
                    }
                )
            )
    equivalence_hash = _payload_hash(
        {
            "content_kind": content_kind.value,
            "rules_surface": rules_surface,
            "semantic_context_hash": context_hash,
            "equivalence_basis": basis.value,
            "evidence_hash": evidence_hash,
        }
    )
    return SemanticEquivalenceMember(
        member_id=member_id,
        content_kind=content_kind,
        rules_surface=rules_surface,
        faction_id=faction_id,
        faction_name=faction_name,
        owner_id=owner_id,
        owner_name=owner_name,
        rule_id=rule_id,
        rule_name=rule_name,
        source_row_ids=source_row_ids,
        source_text_ids=source_text_ids,
        normalized_text_hash=text_hash,
        semantic_hash=semantic_hash,
        semantic_context_hash=context_hash,
        equivalence_hash=equivalence_hash,
        equivalence_basis=basis,
        execution_status=execution_status,
        runtime_consumer_ids=runtime_consumer_ids,
        support_transfer=support_transfer,
        diagnostic_reasons=diagnostics,
    )


def semantic_member_without_source_text(
    *,
    member_id: str,
    content_kind: SemanticContentKind,
    rules_surface: str,
    faction_id: str,
    faction_name: str,
    owner_id: str,
    owner_name: str,
    rule_id: str,
    rule_name: str,
    source_row_ids: tuple[str, ...],
    semantic_context: Mapping[str, object],
    execution_status: SemanticExecutionStatus,
    runtime_consumer_ids: tuple[str, ...],
) -> SemanticEquivalenceMember:
    return SemanticEquivalenceMember(
        member_id=member_id,
        content_kind=content_kind,
        rules_surface=rules_surface,
        faction_id=faction_id,
        faction_name=faction_name,
        owner_id=owner_id,
        owner_name=owner_name,
        rule_id=rule_id,
        rule_name=rule_name,
        source_row_ids=source_row_ids,
        source_text_ids=(),
        normalized_text_hash=None,
        semantic_hash=None,
        semantic_context_hash=_payload_hash(_json_mapping("semantic_context", semantic_context)),
        equivalence_hash=None,
        equivalence_basis=SemanticEquivalenceBasis.SOURCE_TEXT_UNAVAILABLE,
        execution_status=execution_status,
        runtime_consumer_ids=runtime_consumer_ids,
        support_transfer=SemanticSupportTransfer.NONE,
        diagnostic_reasons=("source_text_unavailable",),
    )


def load_cross_source_semantic_audit(path: object) -> CrossSourceSemanticAudit:
    if not isinstance(path, Path):
        raise SemanticEquivalenceError("Semantic audit path must be pathlib.Path.")
    if not path.is_file():
        raise SemanticEquivalenceError(f"Semantic audit artifact is missing: {path}.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SemanticEquivalenceError("Semantic audit artifact is invalid JSON.") from exc
    if not isinstance(value, dict):
        raise SemanticEquivalenceError("Semantic audit artifact must be a JSON object.")
    return CrossSourceSemanticAudit.from_payload(cast(CrossSourceSemanticAuditPayload, value))


def _equivalence_group(
    equivalence_hash: str,
    members: tuple[SemanticEquivalenceMember, ...],
) -> SemanticEquivalenceGroup:
    first = members[0]
    if any(member.equivalence_hash != equivalence_hash for member in members):
        raise SemanticEquivalenceError("Equivalence group contains mismatched hashes.")
    if any(
        (member.content_kind, member.rules_surface, member.equivalence_basis)
        != (first.content_kind, first.rules_surface, first.equivalence_basis)
        for member in members
    ):
        raise SemanticEquivalenceError("Equivalence group contains mismatched semantic surfaces.")
    transfers = {member.support_transfer for member in members}
    consumer_evidence = {member.runtime_consumer_ids for member in members}
    has_common_consumer_evidence = len(consumer_evidence) == 1
    common_consumer_ids = first.runtime_consumer_ids if has_common_consumer_evidence else ()
    transfer = (
        SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR
        if transfers == {SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR}
        and has_common_consumer_evidence
        else SemanticSupportTransfer.NONE
    )
    return SemanticEquivalenceGroup(
        group_id=f"semantic-equivalence:{equivalence_hash}",
        equivalence_hash=equivalence_hash,
        equivalence_basis=first.equivalence_basis,
        content_kind=first.content_kind,
        rules_surface=first.rules_surface,
        member_ids=tuple(sorted(member.member_id for member in members)),
        faction_ids=tuple(sorted({member.faction_id for member in members})),
        execution_statuses=tuple(
            sorted({member.execution_status for member in members}, key=lambda value: value.value)
        ),
        runtime_consumer_ids=common_consumer_ids,
        support_transfer=transfer,
    )


def _members(
    values: tuple[SemanticEquivalenceMember, ...],
) -> tuple[SemanticEquivalenceMember, ...]:
    if type(values) is not tuple or not values:
        raise SemanticEquivalenceError("Semantic audit members must be a non-empty tuple.")
    seen: set[str] = set()
    validated: list[SemanticEquivalenceMember] = []
    for value in values:
        if type(value) is not SemanticEquivalenceMember:
            raise SemanticEquivalenceError(
                "Semantic audit members must contain semantic member values."
            )
        if value.member_id in seen:
            raise SemanticEquivalenceError("Semantic audit member IDs must be unique.")
        seen.add(value.member_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda member: member.member_id))


def _hash_mapping(field_name: str, values: object) -> Mapping[str, str]:
    if not isinstance(values, Mapping) or not values:
        raise SemanticEquivalenceError(f"{field_name} must be a non-empty mapping.")
    validated: dict[str, str] = {}
    for raw_key, raw_value in cast(Mapping[object, object], values).items():
        key = _text(f"{field_name} key", raw_key)
        if key in validated:
            raise SemanticEquivalenceError(f"{field_name} keys must be unique.")
        validated[key] = _sha256(f"{field_name}[{key}]", raw_value)
    return dict(sorted(validated.items()))


def _json_mapping(field_name: str, value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SemanticEquivalenceError(f"{field_name} must be a mapping.")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise SemanticEquivalenceError(f"{field_name} must encode to a JSON object.")
    return cast(Mapping[str, object], decoded)


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256(field_name: str, value: object) -> str:
    digest = _text(field_name, value)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SemanticEquivalenceError(f"{field_name} must be a lowercase SHA-256 digest.")
    return digest


def _text_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    allow_empty: bool = False,
    minimum: int = 1,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise SemanticEquivalenceError(f"{field_name} must be a tuple.")
    if not allow_empty and len(values) < minimum:
        raise SemanticEquivalenceError(f"{field_name} must contain at least {minimum} value(s).")
    validated = tuple(sorted({_text(f"{field_name} value", value) for value in values}))
    if len(validated) != len(values):
        raise SemanticEquivalenceError(f"{field_name} values must be unique.")
    return validated


def _text(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise SemanticEquivalenceError(f"{field_name} must be non-empty text.")
    return value.strip()


def _enum_value[T: StrEnum](
    enum_type: type[T],
    field_name: str,
    value: object,
) -> T:
    if type(value) is enum_type:
        return value
    if type(value) is not str:
        raise SemanticEquivalenceError(f"{field_name} must be a string enum value.")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise SemanticEquivalenceError(f"{field_name} has an unsupported value.") from exc
