# Viewer redaction policy

Every read response is scoped to one viewer before it crosses the adapter
boundary. The shared adapter redaction module is authoritative for projections,
pending decisions, events, and server status. Transport code must not maintain
a second hidden-type list.

Hidden information includes payload values and all information derivable from
metadata: option labels and counts, decision types, source IDs, event details,
status messages, support rows, record counts, and identifiers. A field is not
safe merely because it is outside the main game projection.

When a pending decision belongs to another player and is hidden, the viewer
receives the canonical hidden decision type, an empty option list, and a
redacted payload. The actor ID may remain only where turn/priority ownership is
already public; status responses without an owning viewer omit it. Event records
use the same viewer policy. Secret
secondary information and similar source-backed state remain hidden until the
engine records their reveal.

Errors must not echo an opponent's submitted body or hidden current request.
Status payloads may include request/actor details only when the corresponding
request is visible to that viewer. Catalog projections contain static public
display data and no live hidden state.

`examples/projections/hidden_secondary_redaction_view.json` and the generated
event/status examples are conformance fixtures. Adding a visibility-sensitive
payload requires valid owner and opponent examples plus a regression proving
that counts and metadata do not leak.
