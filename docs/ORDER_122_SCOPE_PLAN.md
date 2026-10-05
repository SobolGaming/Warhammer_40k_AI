# Order122 / P01K / C01-11: default effect lifetimes

Selected immutable Core `rule:01:01.02.02:1` blocks 3 and 4 require a lasting
effect without an explicit duration to expire after its triggering period, or
after the phase in which it was given when no period is specified. The exact
selected row, hashes and permission are retained in
[the source audit](../data/source_audits/order122/source.audit.json).

Previously the generic RuleIR owner discarded every effect with duration=None.
The shared duration owner now derives expiry for lasting characteristic/roll/
movement modifiers, ability grants, rerolls, placement/transit permissions and
contextual status grants. Instant CP/VP, damage, healing, returns, forced tests
and other operation continuations retain their own owners. Explicit immediate,
conditional, permanent and endpoint lifetimes retain precedence. Source payloads
continue to record duration=None; the engine records a derived expiration rather
than rewriting compiled source metadata.

Typed phase triggers must match the current execution phase. A typed turn or
battle-round period expires at its corresponding end boundary. Phase and turn
defaults use the actual active turn player, independently of the grant owner.
Unqualified and noncalendar triggers use the given phase. Missing required
calendar/state inputs fail preflight before any preceding clause mutates state;
nonpersistent evaluation remains explicitly available. Live execution,
historical effect reconstruction and direct Objective Control boundary authority
use one derivation. Shared modifier consumers and boundary cleanup retain source,
model, attached-unit and replay ownership. The shared weapon query excludes typed
unit characteristics, so a compound default OC grant remains with its unit consumer
while its weapon modifiers reach the weapon profile.

The loaded canonical once-per-battle compound modifier fixture exercises the
existing finite activation and lifecycle path, retaining a second genuine source
activation to observe the live grant before phase cleanup. It demonstrates the selected Core
permission seam, not current named faction admission or official faction content.
No provider, source-policy extension, named handler, new choice/schema family,
or test reorganization belongs to this order. Existing deferred/load-only
scaffolds and F00 admission remain distinct from generic execution capability.
Existing adapter choice, effect, persistence and event envelopes cover the repair;
exact runtime identity remains required for old histories.

Acceptance includes real modifier output and expiration, explicit precedence,
source period and active-turn ownership, invalid atomicity, pending/full JSON
restore, attached source model scope, fork isolation, both viewers and exact
replay through complete lifecycle cycles and negative controls. Delivery retains
the complete disjoint 16 serial polygon plus remaining parallel correctness
inventory, appended branch coverage >=85%, quiet serial current-runtime smoke
before full quality, both type checkers, lint/imports/precommit, twelve-shard
inventory, generated contracts and identities, installed wheel and TypeScript
checks, two distinct exact-head CLEAN reviews and all protected hosted CI.
This is an ordinary rules repair with no intended performance change or full-game
performance certification. Stop after delivery and the Order123 handoff.
