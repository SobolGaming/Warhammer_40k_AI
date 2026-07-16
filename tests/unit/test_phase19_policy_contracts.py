from __future__ import annotations

import pytest

from warhammer40k_core.ai.policy_contracts import (
    PolicyArtifactKind,
    PolicyCompatibilityRecord,
    PolicyProvenance,
    PolicyProvenanceError,
    TrainingFeature,
    TrainingFeatureSourceKind,
    TrainingRow,
    validate_training_row_payload,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)


def test_policy_provenance_round_trips_from_game_config() -> None:
    config = _game_config()
    provenance = PolicyProvenance.from_game_config(
        artifact_id="phase19-general-policy",
        artifact_kind=PolicyArtifactKind.GENERAL,
        game_config=config,
        reward_profile_version="phase19e-reward-v1",
    )

    payload = provenance.to_payload()
    round_tripped = PolicyProvenance.from_payload(payload)

    assert round_tripped.to_payload() == payload
    assert payload["catalog_packages"] == [
        {
            "catalog_id": config.army_catalog.catalog_id,
            "source_package_id": config.army_catalog.source_package_id,
            "catalog_hash": provenance.catalog_packages[0].catalog_hash,
        }
    ]
    assert payload["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash


def test_policy_provenance_rejects_catalog_or_ruleset_mismatch_without_override() -> None:
    provenance = PolicyProvenance.from_game_config(
        artifact_id="phase19-ranker",
        artifact_kind=PolicyArtifactKind.RANKER,
        game_config=_game_config(descriptor_version="phase19-policy-old-ruleset"),
        reward_profile_version="phase19e-reward-v1",
    )

    with pytest.raises(PolicyProvenanceError, match="ruleset_descriptor_hash"):
        provenance.require_compatible_game_config(
            game_config=_game_config(descriptor_version="phase19-policy-new-ruleset"),
            reward_profile_version="phase19e-reward-v1",
        )


def test_policy_provenance_override_records_cross_version_mismatch() -> None:
    provenance = PolicyProvenance.from_game_config(
        artifact_id="phase19-evaluator",
        artifact_kind=PolicyArtifactKind.EVALUATION_FUNCTION,
        game_config=_game_config(descriptor_version="phase19-policy-old-ruleset"),
        reward_profile_version="phase19e-reward-v1",
    )

    record = provenance.require_compatible_game_config(
        game_config=_game_config(descriptor_version="phase19-policy-new-ruleset"),
        reward_profile_version="phase19e-reward-v1",
        allow_cross_version=True,
    )

    assert record.has_mismatch
    assert set(record.mismatch_fields) == {"ruleset_id", "ruleset_descriptor_hash"}
    assert record.to_payload()["allow_cross_version"] is True


def test_policy_compatibility_record_rejects_false_negative_mismatch_fields() -> None:
    expected = PolicyProvenance.from_game_config(
        artifact_id="phase19-evaluator",
        artifact_kind=PolicyArtifactKind.EVALUATION_FUNCTION,
        game_config=_game_config(descriptor_version="phase19-policy-old-ruleset"),
        reward_profile_version="phase19e-reward-v1",
    )
    actual = PolicyProvenance.from_game_config(
        artifact_id=expected.artifact_id,
        artifact_kind=expected.artifact_kind,
        game_config=_game_config(descriptor_version="phase19-policy-new-ruleset"),
        reward_profile_version="phase19e-reward-v1",
    )

    with pytest.raises(PolicyProvenanceError, match="mismatch_fields must match"):
        PolicyCompatibilityRecord(
            policy_artifact_id=expected.artifact_id,
            allow_cross_version=True,
            mismatch_fields=(),
            expected=expected,
            actual=actual,
        )


def test_policy_compatibility_record_rejects_mismatch_without_override() -> None:
    expected = PolicyProvenance.from_game_config(
        artifact_id="phase19-evaluator",
        artifact_kind=PolicyArtifactKind.EVALUATION_FUNCTION,
        game_config=_game_config(descriptor_version="phase19-policy-old-ruleset"),
        reward_profile_version="phase19e-reward-v1",
    )
    actual = PolicyProvenance.from_game_config(
        artifact_id=expected.artifact_id,
        artifact_kind=expected.artifact_kind,
        game_config=_game_config(descriptor_version="phase19-policy-new-ruleset"),
        reward_profile_version="phase19e-reward-v1",
    )

    with pytest.raises(PolicyProvenanceError, match="requires cross-version override"):
        PolicyCompatibilityRecord(
            policy_artifact_id=expected.artifact_id,
            allow_cross_version=False,
            mismatch_fields=("ruleset_id", "ruleset_descriptor_hash"),
            expected=expected,
            actual=actual,
        )


def test_training_row_schema_allows_characteristics_not_identity_features() -> None:
    provenance = PolicyProvenance.from_game_config(
        artifact_id="phase19-commander",
        artifact_kind=PolicyArtifactKind.COMMANDER,
        game_config=_game_config(),
        reward_profile_version="phase19e-reward-v1",
    )
    row = TrainingRow(
        row_id="phase19-training-row-0001",
        game_id="phase19-policy-game",
        decision_record_id="decision-record-000001",
        policy_artifact_id=provenance.artifact_id,
        policy_provenance=provenance,
        reward_profile_version=provenance.reward_profile_version,
        input_features=(
            TrainingFeature(
                feature_id="model-statline-movement",
                source_kind=TrainingFeatureSourceKind.STATLINE,
                value={"movement_inches": 6, "toughness": 4, "save": 3},
                source_descriptor_ids=("datasheet:core-intercessor-like-infantry",),
            ),
            TrainingFeature(
                feature_id="weapon-profile-bolt-rifle",
                source_kind=TrainingFeatureSourceKind.WEAPON_PROFILE,
                value={"range_inches": 24, "attacks": 2, "strength": 4},
                source_descriptor_ids=("wargear:core-bolt-rifle",),
            ),
        ),
        legal_action_mask=(True, False, True),
        chosen_action_id="candidate-0001",
        target_value=0.25,
        debug_metadata={
            "datasheet_id": "core-intercessor-like-infantry",
            "faction_id": "core-marine-force",
        },
    )

    payload = row.to_payload()

    assert TrainingRow.from_payload(payload).to_payload() == payload
    assert validate_training_row_payload(payload) == payload


def test_training_row_schema_rejects_identity_feature_id() -> None:
    with pytest.raises(PolicyProvenanceError, match="identity IDs"):
        TrainingFeature(
            feature_id="datasheet_id:core-intercessor-like-infantry",
            source_kind=TrainingFeatureSourceKind.STATLINE,
            value={"movement_inches": 6},
            source_descriptor_ids=("datasheet:core-intercessor-like-infantry",),
        )


def test_training_row_schema_rejects_identity_feature_value_keys() -> None:
    with pytest.raises(PolicyProvenanceError, match="identity IDs"):
        TrainingFeature(
            feature_id="statline-with-identity-key",
            source_kind=TrainingFeatureSourceKind.STATLINE,
            value={"faction_id": "core-marine-force", "movement_inches": 6},
            source_descriptor_ids=("datasheet:core-intercessor-like-infantry",),
        )


def _game_config(
    *,
    descriptor_version: str = "phase19-policy-contract",
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version=descriptor_version
    )
    return GameConfig(
        game_id="phase19-policy-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="unit-alpha",
            ),
            _muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="unit-beta",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )
