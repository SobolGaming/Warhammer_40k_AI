"""Operator-declared partitions over complete admitted deployment inventories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from warhammer40k_core.ai.player_policy import payload_digest
from warhammer40k_core.ai.runner_admission import DeploymentDatasetAdmission
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value


class DeploymentDatasetPartition(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrainingAdmissionError(message)


@dataclass(frozen=True, slots=True)
class DeploymentSplitAssignment:
    """One supplied run occurrence and its unverified operator group declarations."""

    dataset_occurrence: int
    run_occurrence: int
    partition: DeploymentDatasetPartition
    scenario_family: str
    geometry_group: str

    def __post_init__(self) -> None:
        _require(
            type(self.dataset_occurrence) is int
            and self.dataset_occurrence >= 0
            and type(self.run_occurrence) is int
            and self.run_occurrence >= 0
            and type(self.partition) is DeploymentDatasetPartition
            and all(
                type(label) is str and bool(label) and label == label.strip()
                for label in (self.scenario_family, self.geometry_group)
            ),
            "Split assignment requires exact occurrence indices, partition and group labels.",
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "dataset_occurrence": self.dataset_occurrence,
            "run_occurrence": self.run_occurrence,
            "partition": self.partition.value,
            "scenario_family": self.scenario_family,
            "geometry_group": self.geometry_group,
        }


def _counts(
    runs: list[dict[str, JsonValue]], choices: list[dict[str, JsonValue]]
) -> dict[str, JsonValue]:
    reports = [cast(dict[str, JsonValue], run["report"]) for run in runs]
    attempts = [
        attempt
        for report in reports
        for attempt in cast(list[dict[str, JsonValue]], report["decisions"])
    ]
    eligible = sum(choice["eligible_for_learning"] is True for choice in choices)
    return {
        "attempted_runs": len(runs),
        "failed_runs": sum(report["stop_reason"] == "error" for report in reports),
        "attempted_choices": len(attempts),
        "submission_outcomes": {
            outcome: sum(attempt["submission_outcome"] == outcome for attempt in attempts)
            for outcome in ("accepted", "rejected", "unverified", "not_submitted")
        },
        "admitted_rows": len(choices),
        "eligible_rows": eligible,
        "excluded_rows": len(choices) - eligible,
    }


@dataclass(frozen=True, slots=True, init=False)
class DeploymentDatasetSplit:
    """Keep whole startup-rooted trajectories and declared groups in one partition.

    The startup commitment conservatively groups alternate branches, prefixes and
    perspectives of the same verified initial state. Declared trajectory IDs also
    bind supplied slices together. Neither identity proves geometric equivalence.
    All source datasets, duplicate occurrences and excluded rows remain retained;
    completeness is relative to that inventory, never unreported external runs.
    """

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Split admitted datasets through complete assignments.")

    @classmethod
    def from_datasets(
        cls,
        datasets: tuple[DeploymentDatasetAdmission, ...],
        *,
        assignments: tuple[DeploymentSplitAssignment, ...],
    ) -> DeploymentDatasetSplit:
        _require(
            type(datasets) is tuple
            and bool(datasets)
            and all(type(dataset) is DeploymentDatasetAdmission for dataset in datasets)
            and type(assignments) is tuple
            and all(type(item) is DeploymentSplitAssignment for item in assignments),
            "Split requires typed admitted datasets and assignments.",
        )
        sources = [dataset.to_payload() for dataset in datasets]
        inventory = {
            (dataset_index, run_index): run
            for dataset_index, source in enumerate(sources)
            for run_index, run in enumerate(cast(list[dict[str, JsonValue]], source["runs"]))
        }
        assigned: dict[tuple[int, int], DeploymentSplitAssignment] = {}
        for item in assignments:
            key = (item.dataset_occurrence, item.run_occurrence)
            _require(key in inventory, "Split assignment names an unknown run occurrence.")
            _require(key not in assigned, "Split repeats an assignment for one run occurrence.")
            assigned[key] = item
        _require(set(assigned) == set(inventory), "Split is missing run occurrence assignments.")

        trajectories: dict[tuple[str, str], DeploymentSplitAssignment] = {}
        groups: dict[tuple[str, str], DeploymentDatasetPartition] = {}
        members: list[dict[str, JsonValue]] = []
        for key, run in inventory.items():
            item = assigned[key]
            origin = cast(dict[str, JsonValue], run["origin"])
            trajectory_key = payload_digest(
                {
                    "schema_version": "verified-startup-trajectory-group-v1",
                    "engine_build_id": origin["engine_build_id"],
                    "source_identity": origin["source_identity"],
                    "initial_checkpoint_hash": origin["initial_checkpoint_hash"],
                }
            )
            labels = sorted(
                {
                    cast(str, transition["trajectory_id"])
                    for transition in cast(list[dict[str, JsonValue]], run["transitions"])
                }
            )
            for identity in [("startup", trajectory_key), *(("declared", s) for s in labels)]:
                if identity in trajectories:
                    previous = trajectories[identity]
                    _require(
                        previous.partition is item.partition,
                        "Split trajectory leaks across partitions.",
                    )
                    _require(
                        (previous.scenario_family, previous.geometry_group)
                        == (item.scenario_family, item.geometry_group),
                        "Split trajectory has conflicting group declarations.",
                    )
                trajectories[identity] = item
            for group in (
                ("scenario_family", item.scenario_family),
                ("geometry_group", item.geometry_group),
            ):
                _require(
                    group not in groups or groups[group] is item.partition,
                    "Split declared group leaks across partitions.",
                )
                groups[group] = item.partition
            members.append(
                {
                    **item.to_payload(),
                    "startup_trajectory_hash": trajectory_key,
                    "declared_trajectory_ids": cast(JsonValue, labels),
                }
            )

        choices = [
            (dataset_index, choice_index, choice)
            for dataset_index, source in enumerate(sources)
            for choice_index, choice in enumerate(
                cast(list[dict[str, JsonValue]], source["choices"])
            )
        ]
        partitions: dict[str, JsonValue] = {}
        for partition in DeploymentDatasetPartition:
            run_keys = [key for key in inventory if assigned[key].partition is partition]
            partition_choices = [
                (dataset_index, choice_index, choice)
                for dataset_index, choice_index, choice in choices
                if assigned[(dataset_index, cast(int, choice["run_occurrence"]))].partition
                is partition
            ]
            partitions[partition.value] = {
                "run_occurrences": [
                    [dataset_index, run_index] for dataset_index, run_index in run_keys
                ],
                "choice_occurrences": [
                    [dataset_index, choice_index]
                    for dataset_index, choice_index, _ in partition_choices
                ],
                "counts": _counts(
                    [inventory[key] for key in run_keys],
                    [choice for _, _, choice in partition_choices],
                ),
            }
        result = object.__new__(cls)
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                validate_json_value(
                    {
                        "schema_version": "deployment-dataset-split-v1",
                        "scope": "operator-only-supplied-inventory",
                        "group_evidence": "declared-unverified",
                        "trajectory_grouping": "verified-startup-and-declared-ids-v1",
                        "datasets": sources,
                        "dataset_hashes": [dataset.content_hash for dataset in datasets],
                        "assignments": members,
                        "partitions": partitions,
                        "counts": _counts(
                            list(inventory.values()), [choice for _, _, choice in choices]
                        ),
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
        datasets: tuple[DeploymentDatasetAdmission, ...],
        assignments: tuple[DeploymentSplitAssignment, ...],
    ) -> DeploymentDatasetSplit:
        expected = cls.from_datasets(datasets, assignments=assignments)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Dataset split payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
