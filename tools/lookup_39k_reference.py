from __future__ import annotations

import argparse
import json

from warhammer40k_core.rules.external_reference_lookup import (
    THIRTY_NINE_K_PRO_TARGET_EDITION,
    ExternalReferenceKind,
    build_thirty_nine_k_pro_reference_lookup,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a typed 39k PRO lookup for an 11th Edition reference."
    )
    parser.add_argument(
        "reference_kind",
        choices=tuple(kind.value for kind in ExternalReferenceKind),
    )
    parser.add_argument("query")
    parser.add_argument(
        "--reference-id",
        help="Optional 39k PRO result ID used to emit the typed direct reference URL.",
    )
    args = parser.parse_args()

    lookup = build_thirty_nine_k_pro_reference_lookup(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        reference_kind=ExternalReferenceKind(args.reference_kind),
        query=args.query,
    )
    payload: dict[str, str] = dict(lookup.to_payload())
    if args.reference_id is not None:
        payload["reference_url"] = lookup.reference_url(args.reference_id)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
