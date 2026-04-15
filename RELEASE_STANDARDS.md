# Release Standards

This document defines the repository release-quality baseline for tagged versions.

## Scope

These standards apply to all production Python modules in [autofiller/](autofiller/) and supporting scripts/tests when they affect release confidence.

## Documentation Standard

All Python docstrings should follow Google style conventions:

1. Start with a concise summary line.
2. Add `Args:` for non-trivial parameters.
3. Add `Returns:` when a value is returned.
4. Add `Raises:` for expected error paths.
5. Keep inline comments focused on non-obvious reasoning, not obvious assignments.

## Code And Quality Gates

A release should satisfy all of the following before creating a tag:

1. Working tree is clean after intended changes.
2. Tests pass locally (`make test` or equivalent).
3. Version markers and changelog are updated for the target release.
4. README references are aligned with current release/tag conventions.
5. Tag is annotated and points to the intended release commit.

## Release Procedure

1. Implement and validate changes.
2. Update [CHANGELOG.md](CHANGELOG.md).
3. Commit with a release-focused message.
4. Create annotated tag (for example: `v1.0.0`).
5. Push `main` and push the tag.
6. Verify CI workflows complete successfully.

## Post-Release Verification

After pushing the tag, verify:

1. Latest release appears on GitHub with the correct tag/notes.
2. CI status is green for tests and image workflows.
3. Container/image artifacts (if expected) are published and pullable.
