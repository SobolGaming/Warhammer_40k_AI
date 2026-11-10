"""Closed operator workload references over supplied deployment dataset splits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.ai.deployment_dataset_split import DeploymentDatasetSplit
from warhammer40k_core.ai.deployment_geometry_features import (
    DEPLOYMENT_GEOMETRY_FEATURES,
    DEPLOYMENT_GEOMETRY_REGISTRY,
)
from warhammer40k_core.ai.player_policy import PolicyRoute, payload_digest
from warhammer40k_core.ai.semantic_features import FEATURE_REGISTRY_VERSION, FINITE_FEATURE_REGISTRY
from warhammer40k_core.ai.training_admission import (
    COMMAND_POINT_BALANCE_TARGET,
    LOCAL_REFERENCE_PRODUCER,
    LOCAL_REFERENCE_SCHEMA_VERSION,
    MISSING_TARGET_PRODUCER,
    TrainingAdmissionError,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig

WORKLOAD_SCHEMA = "deployment-workload-contract-v1"
_ROUTE_FIELDS = (
    "actor_id",
    "decision_type",
    "stage",
    "setup_step",
    "battle_phase",
    "proposal_kind",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrainingAdmissionError(message)


def _route(route: PolicyRoute) -> list[JsonValue]:
    return [
        route.actor_id,
        route.decision_type,
        route.stage,
        route.setup_step,
        route.battle_phase,
        route.proposal_kind,
    ]


@dataclass(frozen=True, slots=True, init=False)
class DeploymentWorkloadContract:
    """Pin supplied configurations, declared routes, semantics and access boundaries.

    This is an operator contract audit, not measured workload qualification.
    Routes are declarations; actual attempts and absent route evidence are kept
    separately. The complete split preserves failures, duplicates and exclusions.
    No receipt or configuration commitment becomes an argument to a policy.
    """

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Bind a workload through its admitted split.")

    @classmethod
    def from_split(
        cls,
        split: DeploymentDatasetSplit,
        *,
        configs: tuple[GameConfig, ...],
        required_routes: tuple[PolicyRoute, ...],
    ) -> DeploymentWorkloadContract:
        _require(
            type(split) is DeploymentDatasetSplit
            and type(configs) is tuple
            and bool(configs)
            and all(type(config) is GameConfig for config in configs)
            and type(required_routes) is tuple
            and bool(required_routes)
            and all(type(route) is PolicyRoute for route in required_routes),
            "Workload requires a typed split, configurations and exact routes.",
        )
        _require(
            all(
                route.stage == "setup" and route.proposal_kind in (None, "deployment_placement")
                for route in required_routes
            ),
            "Workload supports setup finite choices and deployment placement only.",
        )
        config_hashes = sorted(payload_digest(config.to_payload()) for config in configs)
        route_keys = sorted(canonical_json(_route(route)) for route in required_routes)
        _require(
            len(set(config_hashes)) == len(config_hashes)
            and len(set(route_keys)) == len(route_keys),
            "Workload repeats a configuration or route declaration.",
        )
        source = split.to_payload()
        seen_configs: set[str] = set()
        observed_routes: set[str] = set()
        for dataset in cast(list[dict[str, JsonValue]], source["datasets"]):
            for run in cast(list[dict[str, JsonValue]], dataset["runs"]):
                origin = cast(dict[str, JsonValue], run["origin"])
                identity = cast(dict[str, JsonValue], origin["source_identity"])
                seen_configs.add(cast(str, identity["game_config_hash"]))
                report = cast(dict[str, JsonValue], run["report"])
                manifest = cast(dict[str, JsonValue], report["manifest"])
                for registration in cast(
                    list[dict[str, JsonValue]], manifest["declared_registrations"]
                ):
                    _require(
                        canonical_json(registration["route"]) in route_keys,
                        "Workload registration is outside declared routes.",
                    )
                for attempt in cast(list[dict[str, JsonValue]], report["decisions"]):
                    route = cast(dict[str, JsonValue], attempt["route"])
                    key = canonical_json([route[field] for field in _ROUTE_FIELDS])
                    _require(key in route_keys, "Workload attempt is outside declared routes.")
                    observed_routes.add(key)
            for choice in cast(list[dict[str, JsonValue]], dataset["choices"]):
                linked = cast(dict[str, JsonValue], choice["linked_target"])
                target = cast(dict[str, JsonValue], linked["target"])
                _require(
                    target["target_id"] == COMMAND_POINT_BALANCE_TARGET
                    and target["meaning"] == "local_reference"
                    and target["value_unit"] == "command_points"
                    and target["producer_id"]
                    in (LOCAL_REFERENCE_PRODUCER, MISSING_TARGET_PRODUCER),
                    "Workload requires the bounded endpoint CP reference.",
                )
        _require(
            seen_configs == set(config_hashes),
            "Workload configurations differ from the complete supplied run inventory.",
        )
        result = object.__new__(cls)
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                validate_json_value(
                    {
                        "schema_version": WORKLOAD_SCHEMA,
                        "scope": "operator-only-bounded-deployment-contract-audit",
                        "workload_kind": "setup-deployment-model-origins-and-endpoint-cp",
                        "split": source,
                        "split_hash": split.content_hash,
                        "game_config_hashes": config_hashes,
                        "required_routes": [json.loads(key) for key in route_keys],
                        "route_evidence": "declared-not-exhaustive-reachability",
                        "observed_routes": [json.loads(key) for key in sorted(observed_routes)],
                        "unobserved_routes": [
                            json.loads(key) for key in route_keys if key not in observed_routes
                        ],
                        "semantic_contracts": {
                            "finite": {
                                "registry_version": FEATURE_REGISTRY_VERSION,
                                "features": [item.to_payload() for item in FINITE_FEATURE_REGISTRY],
                            },
                            "deployment": {
                                "registry_version": DEPLOYMENT_GEOMETRY_REGISTRY,
                                "features": [
                                    item.to_payload() for item in DEPLOYMENT_GEOMETRY_FEATURES
                                ],
                            },
                        },
                        "reference_contract": {
                            "schema_version": LOCAL_REFERENCE_SCHEMA_VERSION,
                            "target_id": COMMAND_POINT_BALANCE_TARGET,
                            "producer_id": LOCAL_REFERENCE_PRODUCER,
                            "value_unit": "command_points",
                            "horizon": "exact-accepted-record-endpoint",
                            "missing_producer_id": MISSING_TARGET_PRODUCER,
                            "meaning": "local-resource-observation",
                        },
                        "information_access": {
                            "generator": "detached-actor-context-and-supplied-formation",
                            "ranker": (
                                "detached-actor-context-accepted-proposals-and-declared-parameters"
                            ),
                            "model_inputs": "versioned-numeric-semantic-values-only",
                            "opaque_references": "binding-only-not-semantic-inputs",
                            "operator_only": [
                                "checkpoints",
                                "private-rng-authority",
                                "rejected-proposal-diagnostics",
                                "source-build-config-commitments",
                                "targets",
                                "run-and-split-receipts",
                            ],
                            "enforcement": "cooperative-api-boundary-not-callback-sandbox",
                        },
                        "qualification": "contract-only-no-coverage-cost-or-playing-strength-claim",
                    }
                )
            ),
        )
        return result

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        split: DeploymentDatasetSplit,
        configs: tuple[GameConfig, ...],
        required_routes: tuple[PolicyRoute, ...],
    ) -> DeploymentWorkloadContract:
        expected = cls.from_split(split, configs=configs, required_routes=required_routes)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Workload contract payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
