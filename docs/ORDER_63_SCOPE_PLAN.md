# Order 63 / P20: reserve Transport cargo and Rapid Disembark

Status: implemented and locally validated on the scoped branch.
Base is `25ec75b643e0cac1276a6df84c4a4f85cbeefeeb`
(Order 62 merged). P09A, T-TRANSPORT and S-MIRRORS are present. No other roadmap
PR was open at discovery or the pre-publication remote refresh.

## Scope and authority

C20-01: a Strategic Reserve Transport ingresses as one reserve rules unit. Its
cargo stays embarked, contributes points to the reserve limit, and cannot ingress
independently. C18-06: every Rapid Disembark passenger model follows the effective
placement rules and restrictions used by its Transport's ingress.

The owner explicitly approved the scoped prerequisite on 2026-09-19: “Include the
scoped prerequisite in Order 63”. The prerequisite migrates existing arrival grant
providers to typed, replayable placement conditions. A scalar enemy distance alone
would lose Warp Rifts' qualifying region; evaluating the grant against passengers
would change source ownership. No new faction content or named handler is added.

The complete 20.01 and 20.04 text was observed in browser-visible
[40k.app Strategic Reserves](https://www.40k.app/rules/20-strategic-reserves).
Complete v946 18.04.01 was observed in the
[Game Datamissions changelog](https://game-datamissions.com/11th/rules/changelog).
The observation is dated 2026-09-19 at 19:06 UTC with minute precision. Neither
provider is official GW. The reviewed package, transcription hashes, individual
observation fingerprints and authority registrations are committed. Historical GW
PDF provenance remains
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.
There is no observed mirror conflict. The source package records 18.04.01 as
executable; 20.01/20.04 remain partial because this order does not recertify every
army-construction, deadline or post-arrival lifetime clause.

## Ownership and implementation

Declaration/cargo ownership -> finite movement or Stratagem choice -> placement
proposal -> reserve resolver and loaded hook providers -> battlefield and reserve
mutation -> arrival event -> passenger choice -> shared standard/attached Disembark
resolver -> atomic cargo removal and passenger setup -> events, restore and replay.

- Remove the obsolete blanket rejection of a reserve unit carrying cargo. Existing
  declaration and cargo-state owners retain points, physical identity and capacity;
  the arrival transition places only the Transport.
- Capture the accepted ingress edge distance, enemy distance, deployment-zone
  restriction and all source exclusion distances. Restriction providers now emit
  all applicable constraints; the shared registry selects actual violations.
- Existing distance grants carry explicit typed placement conditions. Warp Rifts
  records its qualifying zone union and Greater Daemon anchor alternatives, with
  source-selected anchor identity/pose. Denizens retains its source-linked
  unconditional distance grant. No generic code branches on faction names.
- Standard Disembark delegates to an extracted owner. Rapid after Ingress requires
  the policy and validates every model. Attached components use the complete rules
  unit for region conditions and mutate only after every component succeeds.
- Ingress status uses the actual turn's phase movement history. An opponent-turn
  arrival is not mistaken for an arrival in the owner's later Movement phase.
- A private pre-ingress root is captured before the first loaded-Transport ingress
  attempt and installed only after accepted submission. Restore re-executes from
  that root, authenticating derived policy, source conditions and later passenger
  placements. Ordinary cargo-less arrival retains its existing integrity owner.
  Shared lifecycle history wiring was extracted to keep the oversized lifecycle
  module on its existing responsibilities.
- Contract 29 versions replay/persistence and removes the obsolete unsupported
  diagnostic. No new decision family or proposal kind is introduced. Shared
  adapter redaction strips the private policy and historical root for both players.

## Scope and architecture audit

The bug-class search covered ordinary ingress, Stratagem ingress, all current
arrival-distance providers, source exclusion hooks, standard and attached
Disembark, actual-turn history, save/restore, replay and shared redaction. Runtime
changes stay within their existing engine/rules/adapters boundaries. New modules
stay below 1,500 lines. The implementation introduces no named handler, speculative
hook family, runtime text parsing, fallback or endpoint-only movement validation;
Disembark and Ingress use their explicit set-up placement proposals.

Order 64 owns Core arrival/deadline defaults and general ingress activity lifetimes.
Order 65 Firing Deck and new faction semantics remain separate. Full-game
performance is not certified by the component evidence.

## Validation

Focused facade tests cover cargo persistence, independent-ingress exclusion,
every-model enemy/edge/zone restrictions, both player IDs, attached cargo,
malformed/stale/wrong-context submissions, rule-invalid retry, policy tampering,
missing restore authority, deterministic replay, and viewer projections/events.
Existing loaded-provider tests cover retained Warp Rifts conditions and source
exclusion constraints outside the Transport's own violated region. Obsolete
post-arrival transport fixtures now use actual ingress decisions.

Matched base/head component evidence and the unpaired newly supported loaded
path are documented in [performance evidence](performance/order63/README.md).
The final behavioral suite passed all 8,430 tests with 85.11% coverage; all 535
code-quality tests passed. Required lint, type, import, pre-commit, shard,
source/build-identity, exact-base contract, package and TypeScript conformance
checks passed. Detailed outcomes and initial stale-expectation corrections are
recorded in [validation evidence](performance/order63/validation.json).
