# Issue 533: public Firing Deck history authority

The invariant is that a legal player declaration can be constructed from the
current viewer-scoped request. Previously `FiringDeckSelection` required the
entire exact phase `shot_unit_ids` tuple, while the request supplied no such
authority. A client that assumed an empty tuple failed as soon as an ordinary
friendly unit had shot earlier in the phase.

Contract 44.1 adds `firing_deck_already_shot_unit_instance_ids` to proposal requests
with a non-null `firing_deck_value`. In the current ordinary Shooting phase it is
the complete sorted phase shot history, including earlier non-Transport units.
Copy it unchanged into `firing_deck_selection.already_shot_unit_instance_ids`.
An empty list is authenticated empty history. Null means no current ordinary
Shooting authority: out-of-phase, absent, wrong-round, wrong-player or wrong-phase
contexts never substitute empty or stale history. This does not add a Firing Deck
reaction window or authorize borrowed weapons outside existing rules.

The engine request producer owns the snapshot. The existing selection validator
still compares the exact submitted tuple with current state before queue pop.
Existing actor, round, Transport, source, cargo, physical weapon-copy and profile
checks remain intact, as do restrictions for noncontributing cargo. Pending save
restoration checks the advertised snapshot alongside its existing cargo snapshot;
historical accepted records are not rewritten or newly reauthenticated.

Nonsecret Shooting requests and records already expose their accepted shooter
identities. The new snapshot uses that same public visibility policy for both
players and contains no private cargo eligibility or unrelated ranged history.
The shared secret-request redaction hides the entire request, including this
field, from other viewers in both projections and event deltas.

`test_public_firing_deck_history.py` constructs complete proposals exclusively
from the public facade, after a real earlier shot and with initially empty
history. It covers viewer switching, pending and accepted persistence, restored
continuation, exact replay, atomic invalid submissions with retry, secret
redaction, and contexts without usable authority. Existing Order 65 tests retain
the cargo and noncontributor restriction coverage. No historical pinned test or
evidence bytes are changed.

The bug-class trace covered ordinary and out-of-phase producers, declaration and
catalog validation, cargo restriction effects, shared adapter redaction and
pending restore. No engine validation was relaxed and no new rule support is
claimed. Complete-game performance and Core Rules certification remain separate.
