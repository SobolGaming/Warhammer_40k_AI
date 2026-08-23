# Faction-pack RuleIR artifacts

## Package boundary

11th Edition datasheet RuleIR is stored in one runtime source package:

```text
warhammer_40000_11th/faction_pack_rule_ir/
  artifacts/package.json
  artifacts/shards/<shard>.json
```

The stable package is the registry boundary. A shard is a physical review and
generation boundary, not a semantic claim that every contained datasheet belongs
to the shard's label. A pull request that adds or updates a datasheet appends or
replaces a source-package record inside the appropriate shard; it does not add a
new Python package named after the faction, datasheets, work item, or date.

The registry retains each source component's original `source_package_id`,
`package_hash`, source provenance, source-row IDs, and RuleIR identities. Moving a
component into the registry therefore changes its physical package path and the
engine build fingerprint, but does not rewrite replay-visible rule identities.
The checked-in manifest uses `shard_artifacts` to pin the physical shard paths,
hashes, and inventories, and
the typed loader validates every shard eagerly.

Each shard records exact semantic ownership separately in
`datasheet_faction_ids`. The generator derives that mapping from the committed
Wahapedia `Datasheets.json` snapshot and records its filename, file SHA-256, and
source `artifact_hash` in the typed `datasheet_faction_ids_provenance` object. A
selected datasheet missing from that source or carrying an unregistered source
faction ID fails generation. In particular, the physical `chaos-daemons` shard
also contains the Thousand Sons Pink Horrors and Blue Horrors source records;
their exact faction identity remains `thousand-sons`.

Regenerate all shards and the manifest with:

```bash
uv run python tools/generate_faction_rule_ir_bundles.py
```

The fail-closed currentness check is:

```bash
uv run python tools/generate_faction_rule_ir_bundles.py --check
```

The aggregate generator owns the manifest. Running one of the retained
source-specific builder commands regenerates its complete physical shard and the
same aggregate manifest; it never recreates the old source-package directory.

Release and document packages remain separate when the publication is itself the
authoritative boundary. The Munitorum Field Manual, Rules Updates, Event
Companion, faction-pack source staging, and dated application-source captures are
examples. They are not datasheet work-batch packages and must not be folded into
this registry.

## Shared names are not shared datasheets

Runtime support is owned by stable source identities, not display names. Two
datasheets called `Maulerfiend` can share generic engine capabilities while still
having different characteristics, wargear profiles, faction keywords, abilities,
and source rows. A RuleIR record for one variant is never applied to another
variant by matching its name.

The current audited 11th Edition source contains four Maulerfiend variants:

| Faction | Datasheet ID | Faction-local ability |
| --- | --- | --- |
| Chaos Space Marines | `000000968` | Siege Crawler |
| Thousand Sons | `000001029` | Snarling Protector |
| World Eaters | `000002639` | The Scent of Blood; Savage Exaltation |
| Emperor's Children | `000004091` | Glutton for Punishment |

The current exhaustive Death Guard source review contains no Maulerfiend row.
That absence must not be filled by copying or aliasing another faction's
datasheet.

Generic counted-wargear replacement and deterministic weapon-copy identity apply
to all catalog records that present the same structured option shape. Full
datasheet support does not transfer: catalog loading, physical geometry, unique
RuleIR, faction-rule eligibility, and support reporting are all checked against
the exact faction and datasheet identities. The generated shared-datasheet support
report records those component-level results explicitly.
