# Starfang ordinary keyword and shared Deep Strike source correction

Exact base: `79a27e4a26e180a28457712818d47e274df7c99a`.

The accepted source comparison found two bounded discrepancies. The ordinary
keyword for Starfangs 000004195 is **STARFANG**. The plural datasheet name,
model profile 000004195:starfangs and exact name keyword **STARFANGS** remain.
The existing schema makes keyword text part of row identity, so the correction
supersedes 000004195:Starfangs:global:false:15639 with its exact preimage and adds
000004195:Starfang:global:false:15639. The old row remains source history;
there is no singular/plural alias framework or relaxed identity check.

The shared Deep Strike 000008343 description is replaced in all 28 current
occurrences: native 17, inherited paired 6 and standalone Daemons 5, spanning 17
unique owners. Only complete prose and declared provenance change. Descriptor
IDs, source-row IDs, parameters, IR, timing and support statuses remain intact.
Native placement policy already requires more than 8 inches from enemies, with
no edge or enemy deployment-zone exclusion. This is not a repaired 9-inch
runtime bug or complete Deep Strike certification.

## Source authority

The retained complete [Starfangs page](https://www.40k.app/factions/aeldari/units/starfangs)
was observed 2026-11-03T17:06:02.983Z. Complete
[24.09 Deep Strike](https://www.40k.app/rules/24-core-abilities#24.09) was
observed 2026-11-03T17:17:33.254Z. Reviewed observations preserve exact section
URLs, complete rendered text and transfer checks. Typed Core evidence uses the
existing canonical rules-page URL boundary, with section identity recorded
separately. 40k.app is a project-authoritative maintained mirror, not official
primary evidence. The visible 995 update listing is neither an attested App build
nor a date for the keyword change.

The new complete 24.09 source package is loaded/not_certified with no runtime
consumers. Its explicit 20.04 dependency reuses the existing complete
`gw-11e-core-reserve-lifetimes:ingress` pin; prior four-rule Core source bytes
and historical source admissions remain unchanged. This does not upgrade the
dependency's execution status or certify all affected datasheets.

`tools/build_starfang_deep_strike_source.py --check` reproduces the five new
admission and successor artifacts from pinned reviewed observations and immutable existing
schema templates. `catalog-delta.json` in the new source-audit directory records
exact whole-package baseline/current hashes, reviewed descriptors and provenance.
The successor payload is package-owned JSON with an eager typed loader and exact byte pin.
The authenticated successor reverses only the approved deltas before retained
Core, Deadly Demise, Mandiblasters and Whispering Web preservation checks.
Standalone Daemons still reaches its original official-PDF validator after the
new exact Deep Strike and existing Deadly Demise projections.

## Regression and scope boundaries

Active regressions cover one/two-model native construction, ordinary singular
and exact plural generic membership, generated payload round trips, source row
supersession and identity rejection, indexed/non-indexed equality, complete
occurrence closure and malformed source/descriptor rejection. Existing native
reserve declaration and placement regressions retain gameplay coverage.

The old `tests/unit/test_aeldari_yriel_vypers_starfangs_datasheets.py` is a
quarantined historical test. Its bytes and old plural expectation are preserved;
the accepted implementation disposition places corrected current assertions in
the new active source regression module. No inactive test is reactivated, no
inactive-update allowlist is expanded and all 260 quality deferrals remain exact.

No new gameplay handler, unsupported unit, parser expansion, geometry change,
faction certification or performance claim is included. The 65% complete-package
branch floor, 12-minute CI goal and all exact-head gates remain unchanged.
