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
        "--parent-faction-url",
        help="Required verified faction URL used to discover a detachment.",
    )
    parser.add_argument(
        "--reference-url",
        help="Optional complete observed result URL to validate for the requested kind.",
    )
    args = parser.parse_args()

    reference_kind = ExternalReferenceKind(args.reference_kind)
    if reference_kind is ExternalReferenceKind.DETACHMENT and args.parent_faction_url is None:
        parser.error("detachment lookups require --parent-faction-url")
    if (
        reference_kind is not ExternalReferenceKind.DETACHMENT
        and args.parent_faction_url is not None
    ):
        parser.error("--parent-faction-url is valid only for detachment lookups")

    lookup = build_thirty_nine_k_pro_reference_lookup(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        reference_kind=reference_kind,
        query=args.query,
        parent_faction_url=args.parent_faction_url,
    )
    payload: dict[str, object] = dict(lookup.to_payload())
    if args.reference_url is not None:
        payload["reference"] = lookup.verify_reference_url(args.reference_url).to_payload()
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
