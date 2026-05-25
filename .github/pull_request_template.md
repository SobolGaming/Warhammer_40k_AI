## Purpose

What invariant, module, or behavior does this PR introduce/change?

## Scope

- [ ] Core/domain model
- [ ] Geometry/pathing/LoS
- [ ] Decision/replay
- [ ] Rules/text normalization
- [ ] Tests only
- [ ] Docs only

## Invariants checked

- [ ] No broad `except`
- [ ] No silent fallback path
- [ ] No engine/UI import-boundary violation
- [ ] No partial stubs in engine integration tests
- [ ] No raw physical model access bypassing unit-group APIs
- [ ] No non-serializable state in core objects
- [ ] No runtime rule-text parsing outside normalization boundary

## Testing

Commands run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pyright
uv run pytest tests/
uv run lint-imports
```

## Stub usage

- [ ] No stubs used
- [ ] Stubs used only in pure-function tests
- [ ] Real domain fixtures used for engine behavior

Explain any stubs:

## Migration from legacy repo

Was any code copied/adapted from the old repo?

- [ ] No
- [ ] Yes, with review

If yes, what was changed to satisfy CORE V2 invariants?

## Reviewer notes

What should be scrutinized most carefully?