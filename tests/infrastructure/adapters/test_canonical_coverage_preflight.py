from __future__ import annotations

from typing import cast

import pytest

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import reproduce_canonical_deployment
from warhammer40k_core.ai.canonical_deployment_coverage import (
    CanonicalDeploymentCoverage,
    _coverage_totals,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json


def _counts(value: int) -> dict[str, JsonValue]:
    return {
        "generated_count": value,
        "validation_attempts": value,
        "accepted_count": value,
        "rejected_count": 0,
        "unvalidated_count": 0,
        "reference_attempts": value,
        "legal_reference_count": value,
        "invalid_reference_probe_count": 0,
        "covered_legal_reference_count": value,
    }


def test_coverage_totals_derive_each_kind_without_fixed_fixture_counts() -> None:
    rows = [
        {"kind": "placement", "counts": _counts(7)},
        {"kind": "finite", "counts": _counts(2)},
        {"kind": "placement", "counts": _counts(11)},
    ]
    before = canonical_json(rows)
    assert _coverage_totals(rows) == {
        "finite": {"decision_occurrences": 1, **_counts(2)},
        "placement": {"decision_occurrences": 2, **_counts(18)},
    }
    assert _coverage_totals(list(reversed(rows))) == _coverage_totals(rows)
    assert canonical_json(rows) == before
    assert _coverage_totals([]) == {
        "finite": {"decision_occurrences": 0, **_counts(0)},
        "placement": {"decision_occurrences": 0, **_counts(0)},
    }


@pytest.mark.parametrize("invalid", [None, True, -1, 1.0, "1"])
def test_coverage_totals_reject_missing_or_noninteger_counts(invalid: object) -> None:
    counts: dict[str, object] = dict(_counts(1))
    counts["legal_reference_count"] = invalid
    with pytest.raises(TrainingAdmissionError, match="invalid row counts"):
        _coverage_totals([{"kind": "placement", "counts": counts}])
    del counts["legal_reference_count"]
    with pytest.raises(TrainingAdmissionError, match="invalid row counts"):
        _coverage_totals([{"kind": "placement", "counts": counts}])


@pytest.mark.parametrize(
    "rows",
    [None, {}, [None], [{"kind": "other", "counts": {}}], [{"kind": "finite"}]],
)
def test_coverage_totals_require_typed_rows(rows: object) -> None:
    with pytest.raises(TrainingAdmissionError, match="invalid row counts"):
        _coverage_totals(rows)


def test_consistent_tampering_still_reproduces_the_real_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _ = reproduce_canonical_deployment()
    report = CanonicalDeploymentCoverage.measure(session=session)
    checkpoint = canonical_json(session.to_persistence_payload())
    original = CanonicalDeploymentCoverage.measure
    measured_sessions: list[LocalGameSession] = []

    def measured(
        cls: type[CanonicalDeploymentCoverage], *, session: LocalGameSession
    ) -> CanonicalDeploymentCoverage:
        assert cls is CanonicalDeploymentCoverage
        measured_sessions.append(session)
        return original(session=session)

    monkeypatch.setattr(CanonicalDeploymentCoverage, "measure", classmethod(measured))
    inconsistent = report.to_payload()
    totals = cast(dict[str, dict[str, int]], inconsistent["totals"])
    totals["placement"]["legal_reference_count"] += 1
    with pytest.raises(TrainingAdmissionError, match="totals differ from row counts"):
        CanonicalDeploymentCoverage.from_payload(inconsistent, session=session)
    assert measured_sessions == []
    assert canonical_json(session.to_persistence_payload()) == checkpoint

    rows = cast(list[dict[str, JsonValue]], inconsistent["rows"])
    placement = next(row for row in rows if row["kind"] == "placement")
    counts = cast(dict[str, int], placement["counts"])
    counts["legal_reference_count"] += 1
    assert _coverage_totals(rows) == inconsistent["totals"]
    with pytest.raises(TrainingAdmissionError, match="payload drifted from reproduction"):
        CanonicalDeploymentCoverage.from_payload(inconsistent, session=session)
    assert measured_sessions == [session]
    assert canonical_json(session.to_persistence_payload()) == checkpoint
