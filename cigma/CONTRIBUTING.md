# Contributing

This is currently a private author-controlled research repository.

1. Create a focused branch.
2. Add or update invariant tests before changing scientific behavior.
3. Run `PYTHONDONTWRITEBYTECODE=1 make verify`.
4. Do not update expected scientific values by copying numbers from a manuscript.
5. Commit regenerated outputs only when configuration, fixture, or implementation changes intentionally.
6. Explain any claim-affecting change in `CHANGELOG.md` and `docs/CLAIMS_BOUNDARY.md`.
7. Never mix evaluator truth into public adapter or prediction code.
