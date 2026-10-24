# Selected-army source index

The source-backed selected catalog provider supports an explicit generated index.
Its default call still loads and validates every source and applies every overlay.
An indexed call validates the source/builder versions and loads selected dependency
rows, then uses the same bridge and canonical catalog validation.

Set `SOURCE_JSON_DIR` to the existing retained JSON snapshot directory recorded
by the authenticated input manifest. Keep that historical directory and its bytes
unchanged; the mandatory reviewed overlays establish current rule identity. The
index validates both input and builder versions.

Build once from the repository root, into a **new** directory:

```sh
uv run python -m tools.ability_support_sources "$SOURCE_JSON_DIR" .cache/selected-source/v1
```

The builder applies all mandatory overlays and publishes the manifest last. It
never overwrites an existing index. The two generated files are about **68.6 MB**
for the current inputs; keep them in ignored `.cache/` or outside the checkout.
They retain the complete validated source-row partition set so another supported
army selection can reuse the same index. Do not commit these local derived files.

The first supported test-kernel consumer is the existing mixed World Eaters /
Emperor's Children Maulerfiend runtime test. All its original assertions remain:

```sh
uv run pytest tests/integration/test_catalog_wargear_runtime.py::test_world_eaters_maulerfiend_exact_rule_ir_resolves_scent_and_savage_exaltation --selected-army-source-index=.cache/selected-source/v1 -q --no-cov
```

Omit the option to exercise the original full-loader path. The option affects only
opted-in kernels; it does not globally replace every source test or provider. The
underlying `_ability_support_catalog_package` accepts `source_index_dir=Path(...)`
alongside its existing selected `datasheet_ids`. Callers forming multiple armies
must form the selected ID union; the provider keeps its existing duplicate-ID
rejection. This is catalog construction, not army-legality certification.

Run the maintained focused regressions with:

```sh
uv run pytest tests/unit/test_phase17_source_overlays.py -k selected_source_index --selected-army-source-index=.cache/selected-source/v1 -q --no-cov
```

Without the option, these regressions explicitly build a temporary module-scoped
index. They always compare against a fresh full-loader reference. They cover
representative selections from both armies, supported mixed-faction dependencies,
fresh units, order/duplicates, reload isolation, invalid inputs, corruption,
version invalidation and explicit regeneration. Existing native units made from
one catalog can share mutable ability payloads; this change does not alter that
contract. Independent catalog loads and their units must not contaminate each
other or subsequent loads.

Missing, stale or corrupt index inputs fail explicitly. There is no automatic
rebuild, silent full-loader fallback, mtime shortcut or process-global row cache.
Source bytes, overlay inputs, rules/core builder code and its shared identifier
validator, lock/config files and Python
version are bound. Hashes are checked before and after loading. Absolute input
paths also require regeneration after relocating a checkout. After a source,
overlay or builder change, build into another new directory (for example `v2`),
then explicitly point the caller to it. Old indexes continue to fail.

The bounded Windows observation was 17.64 seconds for full preparation versus
2.48 seconds with a prebuilt index; warm reuse was 2.41 seconds. Building the index
cost 18.75 seconds, so build plus first load was slower than one full load. These
figures exclude imports, do not flush OS caches, and are not Linux or game-speed
certification. Exact measured source is retained in the task evidence. The integrated revision
also preserves original field order, normalizes IDs through the shared validator,
and binds that validator into invalidation. Integrated tests validate this final
code separately; the timing comparison was not repeated.

Full repository performance-policy, generated-identity, coverage, code-quality,
type and Linux gates remain required before publication. The source index does
not authorize bypassing those gates or weakening source/overlay validation.
