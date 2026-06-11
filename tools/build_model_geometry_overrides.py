from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.core.model_geometry_catalog import (
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
)


def load_model_geometry_overrides(path: Path) -> tuple[ModelGeometryCatalogRecord, ...]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if type(payload) is not list:
        raise ValueError("Model geometry override file must contain a list of records.")
    records_payload = cast(list[object], payload)
    return tuple(
        ModelGeometryCatalogRecord.from_payload(cast(ModelGeometryCatalogRecordPayload, record))
        for record in records_payload
    )


def write_model_geometry_overrides(
    *,
    path: Path,
    records: tuple[ModelGeometryCatalogRecord, ...],
) -> None:
    if type(records) is not tuple:
        raise ValueError("records must be a tuple.")
    payload = [
        record.to_payload() for record in sorted(records, key=lambda item: item.model_profile_id)
    ]
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phase 17B model geometry overrides.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = load_model_geometry_overrides(args.input)
    if args.output is not None:
        write_model_geometry_overrides(path=args.output, records=records)


if __name__ == "__main__":
    main()
