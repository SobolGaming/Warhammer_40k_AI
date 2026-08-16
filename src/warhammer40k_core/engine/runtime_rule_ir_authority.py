from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    rule_ir_from_execution_payload,
    scoped_rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.stratagems_model import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
)
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle


@dataclass(frozen=True, order=True, slots=True)
class RuntimeRuleIRSourceKey:
    source_id: str
    rule_ir_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "rule_ir_hash",
            _sha256_digest("rule_ir_hash", self.rule_ir_hash),
        )


@dataclass(frozen=True, slots=True)
class RuntimeRuleIRAuthorityIndex:
    _rule_irs_by_key: Mapping[RuntimeRuleIRSourceKey, RuleIR]
    _player_ids_by_key: Mapping[RuntimeRuleIRSourceKey, tuple[str, ...]]
    _ability_records_by_player_key: Mapping[
        tuple[RuntimeRuleIRSourceKey, str], tuple[AbilityCatalogRecord, ...]
    ]
    _stratagem_records_by_player_key: Mapping[
        tuple[RuntimeRuleIRSourceKey, str], tuple[StratagemCatalogRecord, ...]
    ]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_rule_irs_by_key",
            _validated_rule_ir_mapping(self._rule_irs_by_key),
        )
        object.__setattr__(
            self,
            "_player_ids_by_key",
            _validated_player_ids_mapping(
                self._player_ids_by_key,
                rule_ir_keys=frozenset(self._rule_irs_by_key),
            ),
        )
        object.__setattr__(
            self,
            "_ability_records_by_player_key",
            _validated_provider_mapping(
                self._ability_records_by_player_key,
                record_type=AbilityCatalogRecord,
                player_ids_by_key=self._player_ids_by_key,
            ),
        )
        object.__setattr__(
            self,
            "_stratagem_records_by_player_key",
            _validated_provider_mapping(
                self._stratagem_records_by_player_key,
                record_type=StratagemCatalogRecord,
                player_ids_by_key=self._player_ids_by_key,
            ),
        )

    @classmethod
    def from_runtime_sources(
        cls,
        *,
        ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
        stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex],
        faction_rule_execution_registry: FactionRuleExecutionRegistry,
    ) -> RuntimeRuleIRAuthorityIndex:
        resolved: dict[RuntimeRuleIRSourceKey, RuleIR] = {}
        player_ids_by_key: dict[RuntimeRuleIRSourceKey, set[str]] = {}
        ability_records_by_player_key: dict[
            tuple[RuntimeRuleIRSourceKey, str], list[AbilityCatalogRecord]
        ] = {}
        stratagem_records_by_player_key: dict[
            tuple[RuntimeRuleIRSourceKey, str], list[StratagemCatalogRecord]
        ] = {}
        for player_id, ability_index in _ability_catalog_indexes(ability_indexes_by_player_id):
            for ability_record in ability_index.all_records():
                if ability_record.disabled or (
                    ability_record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID
                ):
                    continue
                registered_keys = _register_execution_payload_rule_irs(
                    resolved,
                    player_ids_by_key,
                    payload=ability_record.definition.replay_payload,
                    player_id=player_id,
                )
                for key in registered_keys:
                    ability_records_by_player_key.setdefault((key, player_id), []).append(
                        ability_record
                    )
        for player_id, stratagem_index in _stratagem_catalog_indexes(
            stratagem_indexes_by_player_id
        ):
            for stratagem_record in stratagem_index.all_records():
                if stratagem_record.disabled or (
                    stratagem_record.definition.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
                ):
                    continue
                registered_keys = _register_execution_payload_rule_irs(
                    resolved,
                    player_ids_by_key,
                    payload=stratagem_record.definition.effect_payload,
                    player_id=player_id,
                )
                for key in registered_keys:
                    stratagem_records_by_player_key.setdefault((key, player_id), []).append(
                        stratagem_record
                    )
        if type(faction_rule_execution_registry) is not FactionRuleExecutionRegistry:
            raise GameLifecycleError(
                "Runtime RuleIR authority requires FactionRuleExecutionRegistry."
            )
        for execution_record in faction_rule_execution_registry.all_records():
            if (
                execution_record.execution_status
                is not Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
            ):
                continue
            _register_rule_ir(
                resolved,
                player_ids_by_key,
                faction_rule_execution_registry.resolved_generic_rule_ir(
                    execution_record.execution_id
                ),
                player_id=None,
            )
        return cls(
            _rule_irs_by_key=MappingProxyType(resolved),
            _player_ids_by_key=MappingProxyType(
                {key: tuple(sorted(player_ids_by_key.get(key, set()))) for key in resolved}
            ),
            _ability_records_by_player_key=MappingProxyType(
                {
                    key: tuple(sorted(records, key=lambda record: record.record_id))
                    for key, records in ability_records_by_player_key.items()
                }
            ),
            _stratagem_records_by_player_key=MappingProxyType(
                {
                    key: tuple(sorted(records, key=lambda record: record.record_id))
                    for key, records in stratagem_records_by_player_key.items()
                }
            ),
        )

    def all_rule_irs(self) -> tuple[RuleIR, ...]:
        return tuple(self._rule_irs_by_key[key] for key in sorted(self._rule_irs_by_key))

    def all_keys(self) -> tuple[RuntimeRuleIRSourceKey, ...]:
        return tuple(sorted(self._rule_irs_by_key))

    def rule_ir_for(self, *, source_id: str, rule_ir_hash: str) -> RuleIR:
        key = RuntimeRuleIRSourceKey(source_id=source_id, rule_ir_hash=rule_ir_hash)
        rule_ir = self._rule_irs_by_key.get(key)
        if rule_ir is None:
            raise GameLifecycleError("Runtime RuleIR source is not authoritative for this bundle.")
        return rule_ir

    def rule_ir_for_player(
        self,
        *,
        source_id: str,
        rule_ir_hash: str,
        player_id: str,
    ) -> RuleIR:
        rule_ir = self.rule_ir_for(source_id=source_id, rule_ir_hash=rule_ir_hash)
        key = RuntimeRuleIRSourceKey(source_id=source_id, rule_ir_hash=rule_ir_hash)
        requested_player_id = _identifier("player_id", player_id)
        if requested_player_id not in self._player_ids_by_key[key]:
            raise GameLifecycleError("Runtime RuleIR source is not authoritative for this player.")
        return rule_ir

    def ability_records_for_player(
        self,
        *,
        source_id: str,
        rule_ir_hash: str,
        player_id: str,
    ) -> tuple[AbilityCatalogRecord, ...]:
        self.rule_ir_for_player(
            source_id=source_id,
            rule_ir_hash=rule_ir_hash,
            player_id=player_id,
        )
        key = RuntimeRuleIRSourceKey(source_id=source_id, rule_ir_hash=rule_ir_hash)
        return self._ability_records_by_player_key.get((key, player_id), ())

    def stratagem_records_for_player(
        self,
        *,
        source_id: str,
        rule_ir_hash: str,
        player_id: str,
    ) -> tuple[StratagemCatalogRecord, ...]:
        self.rule_ir_for_player(
            source_id=source_id,
            rule_ir_hash=rule_ir_hash,
            player_id=player_id,
        )
        key = RuntimeRuleIRSourceKey(source_id=source_id, rule_ir_hash=rule_ir_hash)
        return self._stratagem_records_by_player_key.get((key, player_id), ())


def runtime_rule_ir_authority_index_from_bundle(
    bundle: RuntimeContentBundle,
) -> RuntimeRuleIRAuthorityIndex:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle

    if type(bundle) is not RuntimeContentBundle:
        raise GameLifecycleError("Runtime RuleIR authority requires RuntimeContentBundle.")
    return RuntimeRuleIRAuthorityIndex.from_runtime_sources(
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
        stratagem_indexes_by_player_id=bundle.stratagem_indexes_by_player_id,
        faction_rule_execution_registry=bundle.faction_rule_execution_registry,
    )


def _register_execution_payload_rule_irs(
    resolved: dict[RuntimeRuleIRSourceKey, RuleIR],
    player_ids_by_key: dict[RuntimeRuleIRSourceKey, set[str]],
    *,
    payload: JsonValue,
    player_id: str,
) -> tuple[RuntimeRuleIRSourceKey, ...]:
    full_rule_ir = rule_ir_from_execution_payload(payload)
    scoped_rule_ir = scoped_rule_ir_from_execution_payload(payload)
    _register_rule_ir(
        resolved,
        player_ids_by_key,
        full_rule_ir,
        player_id=player_id,
    )
    _register_rule_ir(
        resolved,
        player_ids_by_key,
        scoped_rule_ir,
        player_id=player_id,
    )
    return tuple(
        sorted(
            {
                RuntimeRuleIRSourceKey(full_rule_ir.source_id, full_rule_ir.ir_hash()),
                RuntimeRuleIRSourceKey(scoped_rule_ir.source_id, scoped_rule_ir.ir_hash()),
            }
        )
    )


def _register_rule_ir(
    resolved: dict[RuntimeRuleIRSourceKey, RuleIR],
    player_ids_by_key: dict[RuntimeRuleIRSourceKey, set[str]],
    rule_ir: RuleIR,
    *,
    player_id: str | None,
) -> None:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Runtime RuleIR authority source is invalid.")
    key = RuntimeRuleIRSourceKey(
        source_id=rule_ir.source_id,
        rule_ir_hash=rule_ir.ir_hash(),
    )
    existing = resolved.get(key)
    if existing is not None and existing != rule_ir:
        raise GameLifecycleError("Runtime RuleIR authority has a source-hash collision.")
    resolved[key] = rule_ir
    if player_id is not None:
        player_ids_by_key.setdefault(key, set()).add(_identifier("player_id", player_id))


def _ability_catalog_indexes(
    values: object,
) -> tuple[tuple[str, AbilityCatalogIndex], ...]:
    field_name = "ability_indexes_by_player_id"
    if not isinstance(values, Mapping):
        raise GameLifecycleError(f"Runtime RuleIR authority {field_name} must be a mapping.")
    indexes: list[tuple[str, AbilityCatalogIndex]] = []
    raw_values = cast(Mapping[object, object], values)
    for player_id, index in sorted(raw_values.items(), key=lambda item: str(item[0])):
        validated_player_id = _identifier(f"{field_name} player_id", player_id)
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                f"Runtime RuleIR authority {field_name} contains an invalid index."
            )
        indexes.append((validated_player_id, index))
    return tuple(indexes)


def _stratagem_catalog_indexes(
    values: object,
) -> tuple[tuple[str, StratagemCatalogIndex], ...]:
    field_name = "stratagem_indexes_by_player_id"
    if not isinstance(values, Mapping):
        raise GameLifecycleError(f"Runtime RuleIR authority {field_name} must be a mapping.")
    indexes: list[tuple[str, StratagemCatalogIndex]] = []
    raw_values = cast(Mapping[object, object], values)
    for player_id, index in sorted(raw_values.items(), key=lambda item: str(item[0])):
        validated_player_id = _identifier(f"{field_name} player_id", player_id)
        if type(index) is not StratagemCatalogIndex:
            raise GameLifecycleError(
                f"Runtime RuleIR authority {field_name} contains an invalid index."
            )
        indexes.append((validated_player_id, index))
    return tuple(indexes)


def _validated_rule_ir_mapping(
    value: object,
) -> Mapping[RuntimeRuleIRSourceKey, RuleIR]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Runtime RuleIR authority index must be a mapping.")
    validated: dict[RuntimeRuleIRSourceKey, RuleIR] = {}
    for key, rule_ir in cast(Mapping[object, object], value).items():
        if type(key) is not RuntimeRuleIRSourceKey or type(rule_ir) is not RuleIR:
            raise GameLifecycleError("Runtime RuleIR authority index entry is invalid.")
        if key != RuntimeRuleIRSourceKey(rule_ir.source_id, rule_ir.ir_hash()):
            raise GameLifecycleError("Runtime RuleIR authority index key drifted.")
        validated[key] = rule_ir
    return MappingProxyType(validated)


def _validated_player_ids_mapping(
    value: object,
    *,
    rule_ir_keys: frozenset[RuntimeRuleIRSourceKey],
) -> Mapping[RuntimeRuleIRSourceKey, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Runtime RuleIR player authority index must be a mapping.")
    raw = cast(Mapping[object, object], value)
    if set(raw) != set(rule_ir_keys):
        raise GameLifecycleError("Runtime RuleIR player authority inventory drifted.")
    validated: dict[RuntimeRuleIRSourceKey, tuple[str, ...]] = {}
    for key, player_ids in raw.items():
        if type(key) is not RuntimeRuleIRSourceKey or type(player_ids) is not tuple:
            raise GameLifecycleError("Runtime RuleIR player authority entry is invalid.")
        raw_player_ids = cast(tuple[object, ...], player_ids)
        canonical = tuple(
            sorted(_identifier("player_id", player_id) for player_id in raw_player_ids)
        )
        if canonical != player_ids or len(set(canonical)) != len(canonical):
            raise GameLifecycleError("Runtime RuleIR player authority entry drifted.")
        validated[key] = canonical
    return MappingProxyType(validated)


def _validated_provider_mapping[ProviderRecordT: (AbilityCatalogRecord, StratagemCatalogRecord)](
    value: object,
    *,
    record_type: type[ProviderRecordT],
    player_ids_by_key: Mapping[RuntimeRuleIRSourceKey, tuple[str, ...]],
) -> Mapping[tuple[RuntimeRuleIRSourceKey, str], tuple[ProviderRecordT, ...]]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Runtime RuleIR provider authority must be a mapping.")
    validated: dict[tuple[RuntimeRuleIRSourceKey, str], tuple[ProviderRecordT, ...]] = {}
    for raw_key, raw_records in cast(Mapping[object, object], value).items():
        if type(raw_key) is not tuple:
            raise GameLifecycleError("Runtime RuleIR provider authority entry is invalid.")
        key_items = cast(tuple[object, ...], raw_key)
        if (
            len(key_items) != 2
            or type(key_items[0]) is not RuntimeRuleIRSourceKey
            or type(key_items[1]) is not str
            or type(raw_records) is not tuple
        ):
            raise GameLifecycleError("Runtime RuleIR provider authority entry is invalid.")
        key = cast(tuple[RuntimeRuleIRSourceKey, str], key_items)
        if key[1] not in player_ids_by_key.get(key[0], ()):
            raise GameLifecycleError("Runtime RuleIR provider player authority drifted.")
        records = cast(tuple[object, ...], raw_records)
        if any(type(record) is not record_type for record in records):
            raise GameLifecycleError("Runtime RuleIR provider authority record is invalid.")
        typed_records = cast(tuple[ProviderRecordT, ...], records)
        canonical = tuple(sorted(typed_records, key=lambda record: record.record_id))
        if canonical != typed_records or len({record.record_id for record in canonical}) != len(
            canonical
        ):
            raise GameLifecycleError("Runtime RuleIR provider authority order drifted.")
        validated[key] = canonical
    return MappingProxyType(validated)


def _identifier(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Runtime RuleIR authority {field_name} must be an identifier.")
    return value


def _sha256_digest(field_name: str, value: object) -> str:
    digest = _identifier(field_name, value)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise GameLifecycleError(
            f"Runtime RuleIR authority {field_name} must be a lowercase SHA-256 digest."
        )
    return digest


__all__ = (
    "RuntimeRuleIRAuthorityIndex",
    "RuntimeRuleIRSourceKey",
    "runtime_rule_ir_authority_index_from_bundle",
)
