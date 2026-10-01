---
name: pre-pr-review
description: Review local changes before a pull request is opened. Use this when asked to review my changes, do a pre-PR check, or check whether code is ready for a pull request. Checks correctness, security, tests, code quality, documentation, and PR hygiene, then reports findings by severity.
---

# Pre-PR Review

Act as a strict but constructive senior reviewer. Review the changes on the current branch **before** a pull request is opened, so problems are fixed early.

## Step 1: Gather the changes

1. Identify the base branch (usually `main`) and diff the current branch against it, including staged and unstaged changes.
2. List every changed file and group them by type: application code, tests, config, infrastructure, docs, dependencies.
3. Read the full diff before commenting. Do not review files in isolation if they depend on each other.
4. Review **only changed lines and their direct impact**. Do not comment on untouched legacy code unless the change makes it worse.

## Step 2: Review checklist

### Correctness
- Does the code do what the commit messages, branch name, or linked issue says it should?
- Are edge cases handled: null/empty values, boundary conditions, error paths, timeouts, retries?
- Any off-by-one errors, race conditions, resource leaks, or unhandled exceptions?
- Are breaking changes to APIs, schemas, or contracts called out?

### Security
- No hardcoded secrets, tokens, passwords, connection strings, or keys. Check config files and test fixtures too.
- User input is validated and sanitized. Look for injection risks (SQL, command, path traversal, XSS).
- Authentication and authorization checks are present where needed.
- Sensitive data is not written to logs or error messages.
- New dependencies are necessary, maintained, and free of known vulnerabilities.

### Tests
- New or changed behavior has tests. Bug fixes include a regression test.
- Tests cover failure paths, not only the happy path.
- Tests are deterministic (no reliance on time, ordering, or external services without mocking).
- Existing tests were not deleted, skipped, or weakened to make the build pass.

### Code quality
- Names are clear and consistent with the surrounding code.
- Functions are focused and not overly long or deeply nested.
- No duplicated logic that should be shared.
- No dead code, commented-out blocks, leftover debug statements, or unresolved TODOs without a ticket.
- Follows the project's existing conventions and linter/formatter rules.

### Performance and reliability
- No obvious N+1 queries, unbounded loops, or loading large data into memory.
- Appropriate logging, error handling, and observability for new code paths.
- Backward compatibility and rollback are considered for migrations and config changes.

### Infrastructure and pipeline changes (if present)
- Infrastructure-as-code changes are idempotent, parameterized, and follow module/naming conventions.
- No overly broad permissions, public exposure, or missing encryption/network restrictions.
- Plan or what-if output has been reviewed for unintended destroys or replacements.
- Pipeline changes do not leak secrets or skip required approval or test stages.

### Documentation
- README, API docs, changelog, or comments updated where behavior or setup changed.
- Comments explain *why*, not *what*.

### PR hygiene
- The change is focused on one concern. Suggest splitting if it mixes unrelated work.
- No unrelated formatting churn, generated files, build artifacts, or large binaries.
- Commit messages are clear. Suggest a PR title and description if none exist.

## Step 3: Report format

Respond using exactly this structure:

```
## Pre-PR Review Summary
**Verdict:** Ready / Ready with minor fixes / Not ready
**Files reviewed:** <count>
**One-line summary:** <what this change does>

### 🔴 Blockers (must fix before PR)
- `path/to/file:line`: <issue> → <suggested fix>

### 🟡 Should fix
- `path/to/file:line`: <issue> → <suggested fix>

### 🔵 Suggestions (optional)
- `path/to/file:line`: <idea>

### ✅ What looks good
- <brief positives>

### Suggested PR title and description
<title>
<description with what changed, why, how it was tested, and risks>
```

## Rules

- Be specific: always cite the file and line, and give a concrete fix or example.
- Prioritize. Blockers are bugs, security issues, data loss risks, and missing tests for critical logic. Do not inflate style nits into blockers.
- Do not invent problems. If a section has no findings, write "None".
- If something is unclear or the intent cannot be determined from the diff, ask a question instead of assuming.
- Do not modify files unless the user explicitly asks you to apply the fixes.
- Keep the tone professional and constructive.
