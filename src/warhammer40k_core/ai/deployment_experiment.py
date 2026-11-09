"""Operator-only experiment provenance for one accepted deployment choice."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.ai.deployment_geometry_features import DeploymentTrainingGeometry
from warhammer40k_core.ai.parameterized_training import RankedDeploymentTrainingLink
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.ai.training_admission import MixedEpisodeAdmission
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameConfig

DEPLOYMENT_EXPERIMENT_SCHEMA = "deployment-choice-experiment-provenance-v1"


class DeploymentExperimentError(PolicyProvenanceError):
    """Experiment components do not belong to the same reproduced choice."""


@dataclass(frozen=True, slots=True, init=False)
class DeploymentExperimentProvenance:
    """Join actual choice producers to reachable accepted episode/source evidence.

    This bounded scope has no arbitrary run identifier or caller-declared budgets.
    The retained receipts own generation offsets/formation seed, enforced count
    budgets, choice seed, ranker parameters and encoder semantics. Artifact IDs
    and deterministic behavior remain declarations; this does not authenticate
    scorer code/weights or prove the encoder was called inside an arbitrary scorer.
    Episode stop reasons remain declarations, not verified runner-limit enforcement.
    Private checkpoint/source evidence stays outside all actor inputs.
    """

    _payload_json: str

    def __init__(self) -> None:
        raise DeploymentExperimentError("Join experiment provenance through verified evidence.")

    @classmethod
    def from_episode(
        cls,
        link: RankedDeploymentTrainingLink,
        *,
        episode: MixedEpisodeAdmission,
        row: TrainingRow,
        context: PlayerDecisionContext,
        config: GameConfig,
        reward_profile_version: str,
    ) -> DeploymentExperimentProvenance:
        if (
            type(link) is not RankedDeploymentTrainingLink
            or type(episode) is not MixedEpisodeAdmission
            or type(row) is not TrainingRow
            or type(context) is not PlayerDecisionContext
            or type(config) is not GameConfig
        ):
            raise DeploymentExperimentError("Experiment provenance requires typed evidence.")
        try:
            geometry = DeploymentTrainingGeometry.from_link(link, row=row, context=context)
            row.policy_provenance.require_compatible_game_config(
                game_config=config, reward_profile_version=reward_profile_version
            )
        except (PolicyError, PolicyProvenanceError) as exc:
            raise DeploymentExperimentError("Experiment row, encoder or source drifted.") from exc
        boundary = episode.to_payload()
        origin = boundary["origin"]
        transition = link.candidate_link.transition
        item = transition.to_payload()
        ranking = link.ranking.to_payload()
        config_hash = payload_digest(config.to_payload())
        if (
            origin["engine_build_id"] != current_engine_build_id()
            or ranking["engine_build_id"] != origin["engine_build_id"]
            or origin["source_identity"]["game_config_hash"] != config_hash
            or ranking["game_config_hash"] != config_hash
            or transition.content_hash not in boundary["transition_hashes"]
            or item["origin_checkpoint_hash"] != origin["origin_checkpoint_hash"]
            or item["trajectory_id"] != boundary["trajectory_id"]
            or item["perspective_player_id"] != boundary["perspective_player_id"]
        ):
            raise DeploymentExperimentError(
                "Experiment episode, transition, build or config drifted."
            )
        result = object.__new__(cls)
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                validate_json_value(
                    {
                        "schema_version": DEPLOYMENT_EXPERIMENT_SCHEMA,
                        "scope": "single-accepted-deployment-choice",
                        "episode": boundary,
                        "accepted_transition": item,
                        "ranked_training_link": link.to_payload(),
                        "training_geometry": geometry.to_payload(),
                    }
                )
            ),
        )
        return result

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        link: RankedDeploymentTrainingLink,
        episode: MixedEpisodeAdmission,
        row: TrainingRow,
        context: PlayerDecisionContext,
        config: GameConfig,
        reward_profile_version: str,
    ) -> DeploymentExperimentProvenance:
        expected = cls.from_episode(
            link,
            episode=episode,
            row=row,
            context=context,
            config=config,
            reward_profile_version=reward_profile_version,
        )
        try:
            observed = canonical_json(validate_json_value(payload))
        except EventLogError as exc:
            raise DeploymentExperimentError("Experiment provenance must be JSON-safe.") from exc
        if observed != expected._payload_json:
            raise DeploymentExperimentError("Experiment provenance drifted from verified evidence.")
        return expected
