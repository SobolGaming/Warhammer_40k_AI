# Supported Emperor's Children numeric profiles — 31 October 2026

The current component catalog retained stale numeric profiles in six already-supported Emperor's Children datasheets. A separately dated, preimage-bound overlay corrects 20 fields on 15 existing source rows. It changes no supported-unit set, ability, weapon keyword, attachment rule, geometry, faction, detachment or battlefield layout.

The preferred source is the [v981 App mirror](https://www.40k.app/981/factions/emperors-children/units/lord-exultant), inspected in an ordinary browser on 31 October. The [updates index](https://www.40k.app/factions/updates) lists Emperor's Children v981 dated 14 October and global v995 dated 16 October. Latest-faction status is an index-based inference. The mirror is not an official Games Workshop site; the user directed that its newer App data takes precedence over conflicting PDFs. Research retrieval returned403. No raw mirror payload hash is available or claimed. Retained June source and earlier PDF provenance remain historical.

| Existing sheet | Verified numeric correction |
|---|---|
| [Lord Exultant](https://www.40k.app/981/factions/emperors-children/units/lord-exultant) | Toughness4→5; bolt pistol Strength4→5 and AP0→−1; close combat weapon Strength4→5. |
| [Tormentors](https://www.40k.app/981/factions/emperors-children/units/tormentors) | Toughness4→5; bolt pistol and boltgun Strength4→5 and AP0→−1; close combat weapon Strength4→5. |
| [Infractors](https://www.40k.app/981/factions/emperors-children/units/infractors) | Toughness4→5; bolt pistol Strength4→5 and AP0→−1; duelling sabre Strength4→5. |
| [Lord Kakophonist](https://www.40k.app/981/factions/emperors-children/units/lord-kakophonist) | Toughness5→6; close combat weapon Strength4→5. |
| [Noise Marines](https://www.40k.app/981/factions/emperors-children/units/noise-marines) | Wounds2→3; close combat weapon Strength4→5. |
| [Flawless Blades](https://www.40k.app/981/factions/emperors-children/units/flawless-blades) | Bolt pistol Strength4→5 and AP0→−1. |

The Lord Exultant history explicitly records Toughness4→5 inv981. Other values above are observations of thev981 snapshot, not claims that they changed on14October. The mirror's Obsessionist and ordinary Tormentor/Infractor profiles share these characteristics; the existing single source model profile is retained. The Noise Marines profile similarly retains its existing Disharmonist/model construction. Observed base dimensions do not certify geometry. Matching current weapon keyword lists require no new semantic support.

The source consumer applies the new typed JSON overlay after the historical June Emperor's Children overlay and includes its bytes in selected-source index invalidation. Each operation requires the exact stable source-row ID and preimage hash. The canonical bridge, mustering and shared combat consumers receive the corrected descriptors. June source-package dates and bytes are preserved. Earlier power-sword and Blissblade corrections remain positive controls. Touched-row formatting metadata may be rebuilt by the existing overlay mechanism; the20-field count describes semantic runtime fields.

The regression first reproduces native catalog Toughness4 instead of5. Focused controls cover all six current profiles, stable identities, unchanged weapon keywords and nearby profiles, native state persistence/replay, the exact15-row/20-field source boundary, stale preimage rejection and malformed-artifact rejection. These component fixtures do not certify a full legal army or whole-faction playability.

Murdermind SUPPORT and Butcher Lord LEADER metadata remain blocked; Grimnar's Mark has no exact leader/execution match. Sorcerer000004085 is present in the raw source but absent from the existing59-sheet supported component catalog, so its newly observedT5 remains inventory only. Wider books, profiles and nonexecuting World Eaters detachments remain unaudited or inaccessible. See the [bounded audit](../data/source_audits/supported_rules_2026_10/ec-profiles.json).

Performance admission remains a separate pending scope decision: the changed source-loader owner requires the existing external-contract source-reuse family, while itsv4 evidence route admits exactbasebc9 only and rejects actualbase105b. No historical comparison is reused as current evidence. The checker, role specifications and sensitive mapping remain untouched. Full covered behavior at64%, all active quality through four strict ordered lanes, the180-second serial smoke, both type checkers, lint/generated/contracts/package gates, both independent exact-final-head reviews and complete hosted CI remain required. This preparation is not merge-ready qualification.


The unchanged active-edition guard separately rejects the new overlay's truthful historical base-package version. A finite hash-authenticated provenance registration and preserved predecessor proof are proposed; no guard has been weakened or changed. Prospective comparison specifications/reports also need narrowly authenticated historical-path contexts before measurement.

Corrected weapon descriptors alter the native decision/event payloads mixed into deterministic RNG history. Two existing seeded Icon outcomes therefore change. The tests retain explicit uncapped success, uncapped failure and capped-success cases and additionally check the original RNG source, recorded dice sum, modifier-free final total and Leadership6 threshold. No RNG or command-point rule code changes. The first seed's retained native checkpoint records3+6=9 and the correctly applied1CP; failed earlier attempts remain evidence, not passing gates.
