Implement stories rapidly with direct commits to main. Focus on feature completion and iteration speed over process overhead.

{% include "modes/_header-cycle.md" %}

## Cycle Steps

For each story:

1. **Read** the story's checklist from `docs/specs/stories.md` — always re-fetch from disk with the `Read` tool at the start of each cycle. The developer may have edited the file since you last viewed it (added tasks, reworded scope, marked items done), so do not rely on prior conversation context for its contents.
2. **Implement** all tasks in the checklist
3. **Add copyright/license headers** to every new source file
4. **Run tests** -- `{{ test_invocation }}` (fix failures before continuing)
5. **Run linting** -- fix any issues immediately
6. **Mark tasks** as `[x]` in `stories.md` and change story suffix to `[Done]`
7. **Bump version** in package manifest and source (if the story has a version)
8. **Update CHANGELOG.md** with the version entry
9. **Present** the completed story concisely: what changed (files + line refs), verification results (test counts, lint status), and the suggested next story. Do not propose commits, pushes, or bundling options. Do not offer "want me to also…?" follow-ups.
10. **Wait** for the developer to say "go" before starting the next story

## Velocity Practices

**LLM's role in each cycle:**

- **Version bump per story** -- v0.1.0, v0.2.0, v0.3.0, etc. — bump in package manifest and source
- **Minimal process overhead** -- focus on making it work, not making it perfect
- **Tests run after every story** -- not after every file, but before presenting to developer
- **Fix linting immediately** -- small incremental fixes, not batch cleanup
- **Update CHANGELOG.md** with the version entry before presenting

**Developer's role (do NOT prompt for, offer, or initiate):**

- **Direct commits to main** -- no branches, no PRs, no code review (velocity convention)
- **Commit messages** reference story IDs: `"Story A.a: v0.1.0 Hello World"`
- **Decides when to commit** -- the LLM presents, the developer commits. Multiple stories may be bundled into one commit at the developer's discretion — that is not the LLM's call to make or suggest.

## Story Ordering

- Start with Story A.a (Hello World) if not yet implemented
- If unclear which story is next, ask: "Which story should I work on next?"
- Never skip ahead -- complete stories in order within each phase

## File Header Reminder

Every new source file must include the copyright and license header as the very first content (before code, docstrings, or imports).

## When to Switch Modes

Switch to **code_test_first** when:
- Working on a story with complex logic that benefits from TDD
- The developer requests test-first approach

Switch to **debug** when:
- A bug is discovered during implementation
- Tests are failing unexpectedly

Switch to **production mode** when:
- CI/CD phase is complete and branch protection is enabled
- The project is ready for public users
