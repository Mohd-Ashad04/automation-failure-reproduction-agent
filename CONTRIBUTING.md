# Development Workflow

## Working rules

1. Keep each change small and testable.
2. Do not claim a feature is complete until its acceptance criteria pass.
3. Add tests with behavior changes.
4. Keep the deterministic workflow working without an LLM.
5. Record material architecture changes in `docs/adr/`.
6. Update `docs/ROADMAP.md` when a milestone changes.
7. Never commit secrets or real user data.
8. Do not add dependencies without a specific need.

## Suggested branch names

- `docs/...`
- `feat/...`
- `fix/...`
- `test/...`

## Commit message examples

- `docs: define MVP scope and architecture`
- `feat: parse Playwright JSON report`
- `test: add reproduction comparison fixtures`
- `fix: reject unapproved experiment commands`

## Definition of done

A change is done when:
- It solves the stated problem.
- Relevant tests pass.
- Failure paths are handled.
- Documentation is updated.
- No secrets or generated private artifacts are included.
- Claims in reports are supported by observations.
