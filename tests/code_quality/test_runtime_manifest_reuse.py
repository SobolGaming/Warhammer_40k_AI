"""Live work and identity controls for build-local immutable manifest reuse."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from tests.charge_reroll_helpers import reroll_catalog
from tests.phase13b_shooting_declaration_helpers import _config, _mustered_armies
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusteringError
from warhammer40k_core.engine.faction_content import loader, runtime
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentManifest
from warhammer40k_core.engine.game_state import GameConfig


def test_bundle_build_reuses_its_resolved_manifest_without_cross_build_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(alpha_unit_ids=("alpha",), alpha_datasheets=None, enemy_datasheet=None)
    armies = _mustered_armies(config)
    original_manifest = runtime.runtime_content_manifest_for_ruleset
    original_load = loader.load_runtime_content_contributions
    manifests: list[RuntimeContentManifest] = []
    consumed: list[RuntimeContentManifest] = []

    def record_manifest(
        *, ruleset_descriptor: RulesetDescriptor, config: GameConfig
    ) -> RuntimeContentManifest:
        result = original_manifest(ruleset_descriptor=ruleset_descriptor, config=config)
        manifests.append(result)
        return result

    def record_load(
        *, activation: RuntimeContentActivation, manifest: RuntimeContentManifest
    ) -> tuple[RuntimeContentContribution, ...]:
        consumed.append(manifest)
        return original_load(activation=activation, manifest=manifest)

    monkeypatch.setattr(runtime, "runtime_content_manifest_for_ruleset", record_manifest)
    monkeypatch.setattr(runtime, "load_runtime_content_contributions", record_load)
    first = runtime.build_runtime_content_bundle_for_armies(config=config, armies=armies)
    second = runtime.build_runtime_content_bundle_for_armies(config=config, armies=armies)

    assert len(manifests) == len(consumed) == 2
    assert consumed[0] is manifests[0]
    assert consumed[1] is manifests[1]
    assert manifests[0] is not manifests[1]
    assert first is not second
    assert first.to_summary_payload() == second.to_summary_payload()
    assert first.activation == runtime.runtime_content_activation_for_armies(
        config=config, armies=armies
    )
    assert len(manifests) == 3


def test_manifest_reuse_keeps_fresh_catalog_source_identity_and_detached_payloads() -> None:
    config = _config(alpha_unit_ids=("alpha",), alpha_datasheets=None, enemy_datasheet=None)
    original_payload = config.to_payload()
    first = runtime.build_runtime_content_bundle(config)
    changed_catalog = replace(config.army_catalog, source_package_id="manifest-reuse-source")
    changed_config = replace(config, army_catalog=changed_catalog)
    with pytest.raises(ArmyMusteringError, match="source_package_id does not match catalog"):
        runtime.build_runtime_content_bundle(changed_config)
    changed_config = replace(
        changed_config,
        army_muster_requests=tuple(
            replace(request, source_package_id=changed_catalog.source_package_id)
            for request in config.army_muster_requests
        ),
    )
    changed = runtime.build_runtime_content_bundle(changed_config)

    assert first.activation.source_package_ids == (config.army_catalog.source_package_id,)
    assert changed.activation.source_package_ids == ("manifest-reuse-source",)
    assert changed.activation.activation_hash != first.activation.activation_hash
    assert config.to_payload() == original_payload
    summary = changed.to_summary_payload()
    summary["source_package_ids"].append("caller-mutation")
    assert changed.to_summary_payload()["source_package_ids"] == ["manifest-reuse-source"]
    assert first.to_summary_payload()["source_package_ids"] == [
        config.army_catalog.source_package_id
    ]


def test_manifest_descriptor_and_rows_reject_mutation() -> None:
    config = _config(alpha_unit_ids=("alpha",), alpha_datasheets=None, enemy_datasheet=None)
    manifest = runtime.runtime_content_manifest_for_ruleset(
        ruleset_descriptor=config.ruleset_descriptor, config=config
    )
    row = manifest.row_for_content_id("core-marine-force")
    for target, attribute, value in (
        (manifest, "rows", ()),
        (row, "source_package_id", "caller-mutation"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(target, attribute, value)
    assert row.source_package_id == config.army_catalog.source_package_id
    assert type(manifest.rows) is tuple
    assert type(row.source_ids) is tuple
    assert type(row.execution_record_ids) is tuple
    assert type(row.dependency_ids) is tuple


def test_same_catalog_labels_do_not_reuse_changed_source_rows() -> None:
    config = _config(alpha_unit_ids=("alpha",), alpha_datasheets=None, enemy_datasheet=None)
    catalog = config.army_catalog
    changed = replace(
        catalog,
        factions=tuple(
            replace(faction, source_ids=(*faction.source_ids, "test:manifest-source-change"))
            for faction in catalog.factions
        ),
    )
    assert changed.catalog_id == catalog.catalog_id
    assert changed.source_package_id == catalog.source_package_id
    manifests = tuple(
        runtime.runtime_content_manifest_for_ruleset(
            ruleset_descriptor=config.ruleset_descriptor,
            config=replace(config, army_catalog=current),
        )
        for current in (catalog, changed, catalog)
    )
    rows = tuple(manifest.row_for_content_id("core-marine-force") for manifest in manifests)
    assert "test:manifest-source-change" not in rows[0].source_ids
    assert "test:manifest-source-change" in rows[1].source_ids
    assert rows[2] == rows[0]
    assert manifests[2] is not manifests[0]


def test_separate_bundle_builds_do_not_share_mutable_ability_payloads() -> None:
    config = _config(
        alpha_unit_ids=("alpha",),
        alpha_datasheets=None,
        enemy_datasheet=None,
        catalog=reroll_catalog(),
    )
    first = runtime.build_runtime_content_bundle(config)
    second = runtime.build_runtime_content_bundle(config)
    first_records = first.ability_indexes_by_player_id["player-a"].all_records()
    second_records = {
        record.record_id: record
        for record in second.ability_indexes_by_player_id["player-a"].all_records()
    }
    mutable_records = [
        record
        for record in first_records
        if isinstance(record.definition.replay_payload, dict)
        and "rule_ir" in record.definition.replay_payload
    ]
    assert mutable_records
    for record in mutable_records:
        expected = deepcopy(second_records[record.record_id].definition.to_payload())
        exported = record.definition.to_payload()["replay_payload"]
        assert isinstance(exported, dict)
        exported["isolation_probe"] = "first-build-only"
        assert second_records[record.record_id].definition.to_payload() == expected
