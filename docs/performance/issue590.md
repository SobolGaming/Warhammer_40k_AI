# Issue 590: authoritative command responsiveness

The canonical public-command rejection and corrected one-inch movement now finish
within the original 3-second connect / 30-second total and remaining-read budget
on the measured development host. This is bounded prototype evidence, not a
full-game or production latency guarantee.

## Bounded repair

Trusted in-memory transaction forks copy the live adapter session, JSON ruleset
identity and journal/snapshot/history containers without rerunning construction
validation over every retained revision. Historical entries retain the same
read-only sharing as before. Creation, external restoration and persistence
export retain their complete integrity validation.

Terrain traversal constructs each unchanged terrain volume footprint once per
volume check and reuses the exact base-at-pose intersection predicate. It retains
every sampled pose, segment, diagnostic and result count. Nine regression cases
compare the complete prior results for circular, oval and rectangular bases
against traversable, blocked and nonintersecting rotated terrain. Fork regressions
cover no retained-history exports, live/container isolation, persistence integrity
and exact journal idempotency.

The existing adapter decision contract and Contract 45.0.0 already cover this
behavior; no player-facing shape or legal-rule change is introduced. Runtime
identity and its generated contract examples are regenerated together.

## Actual HTTP recipe

Exact base: `5657bf5f127466edeecf3259e0a53e29f6a9a352`.
Head runtime: `warhammer40k-core-v2:runtime-tree-sha256-v1:3bf79c73db5c5f28d8401fcf9f10298fae6aac5a349ef00cf4e79c9f7785bac7` (3,130 resources).
Both use Windows 11 Pro, Threadripper 3970X, CPython 3.14.5 and the same eight
locked runtime dependency versions. The candidate is a noneditable wheel using
the retained dependency runtime. Its SHA256 is `e5a986113892a1ca2053371f289aa997ec78302a8ccfeb7ceca45b49330594ec`.

The canonical session-create example is started under administrator authority,
then actor credentials select secondaries/reserves, deployment/redeployment and
both ordered Scout paths. Normal movement is reached at request/revision 19.
Missing, duplicate and unknown model inventories assert unchanged revision,
pending request, positions and decision history. Complete ordered three-pose
1,000-inch witnesses exercise recorded-invalid movement; each receipt must show
`accepted:false`, `committed:true`, unchanged positions and a fresh request.
A corrected one-inch witness must place all five models at their requested
XYZ/facing endpoints. Its identical command ID/envelope must return identical
receipt bytes with no second revision.
The reference launcher uses `AdapterGameServer()` without a persistence store;
SQLite is absent from these HTTP measurements.

| Operation | Before on current main | After, uninstrumented |
|---|---|---|
| Warm inventory rejection | n=5, median 24.019 s, range 23.625–24.498 s | n=6, median 1.932 s, range 1.675–2.310 s |
| Complete long-distance rejection | All 4 initial attempts timed out at 30 s | n=4, range 10.461–11.720 s |
| Corrected legal one-inch move | Initial attempt timed out at 30 s | n=2, 7.585 and 7.670 s |
| Exact accepted-command duplicate | Byte-identical after recovered receipt | Both byte-identical, unchanged revision, 0.029–0.038 s |

The observed inventory median is 12.4 times lower. Censored geometry/legal
before samples do not support a completed-latency speedup ratio. All final initial
receipts arrived without recovery. The first final session ends at revision 23
after three recorded-invalid attempts and a legal correction; the second ends at
revision 21 after one recorded-invalid attempt and a legal correction.

The two fresh host processes run serially. First normal-geometry calls took
10.894 and 11.720 s; consecutive warm repeats took 10.461 and 10.563 s. Normal
movement necessarily follows legal setup, so these are not cold-cache normal
moves. OS caches were not cleared. First session-start commands took 3.897 and
3.739 s. Both hosts exited zero and no owned Windows Python process remained.

The original unknown command remains unknown. These new successful sessions do
not supply its missing receipt. Raw failed and successful task evidence is
retained locally; sanitized per-command timings, state checks, source hashes and
environment details are committed in [issue590-http.json](issue590-http.json).

## Attribution and required component evidence

The original targeted inventory timer placed 23.307 of 23.890 server seconds in
the authoritative fork, including 21 retained-history exports. A fork-only
exploratory build reduced inventory rejection to about two seconds, but the long
rejection still took 37.375 server seconds: terrain validation alone took 30.336 s,
while the ordinary path-distance rejection took 0.000440 s. That measured result
required the second, exact-predicate terrain repair before claiming resolution.

The compact new command-fork family measures created and started canonical
authority states, three serial samples each, plus separate untimed work counts
and exact persistence/history checks. These early checkpoints do not establish
late-game scaling; the revision-19 HTTP recipe provides the retained-history
defect coverage. Existing geometry owner mappings additionally require their
visibility, movement and setup comparisons on the actual base/head. Only those
mapped current comparisons are refreshed; historical reports and the 260 deferred
controls retain their prior meaning.
These component comparisons run separately under native WSL/Linux on the same
physical host, with CPython 3.14.5 and the same installed locked dependency
versions in both arms. They are not mixed with the Windows HTTP samples.

Final delivery additionally requires both independent exact-head reviews, the
serial current-runtime smoke with its complete 180-second cap, focused local
static/contracts checks and all required hosted covered behavior/quality gates.
The coverage floor remains 64% with the complete package/branch denominator.
