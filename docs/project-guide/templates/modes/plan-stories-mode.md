Break the project into an ordered sequence of small, independently completable stories grouped into phases. Each story has a checklist of concrete tasks. Stories reference modules defined in `tech-spec.md`.

The high-level concept (why) should be captured in `concept.md`. The requirements and behavior (what) should be captured in `features.md`. The implementation details (how) should be written in `tech-spec.md`.

## Prerequisites

Before writing stories, the following must be approved:
- `docs/specs/concept.md`
- `docs/specs/features.md`
- `docs/specs/tech-spec.md`

Additionally, ask the developer:

> **Will this project need CI/CD automation?** For example: GitHub Actions for linting/testing on every push, dynamic code coverage badges (Codecov/Coveralls), and/or automated publishing to a package registry (PyPI, npm, etc.) on tagged releases?

If yes, include a CI/CD phase in the stories. If no, skip it.

## Steps

1. Read the approved concept, features, and tech-spec documents.

2. Generate `docs/specs/stories.md` using the artifact template at `templates/artifacts/stories.md`

3. Present the complete document to the developer for approval. Iterate as needed.

{% include "modes/_phase-letters.md" %}

## Story Writing Rules

- **Story ID**: see the Phase and Story ID Scheme above.
- **Version**: semver, bumped per story. Stories with no code changes omit the version.
- **Status suffix**: `[Planned]` initially, changed to `[Done]` when completed.
- **Checklist**: use `- [ ]` for planned tasks, `- [x]` for completed tasks. Subtasks indented with two spaces.
- **First story (A.a)**: Always Project Scaffolding — LICENSE, copyright header, package manifest, README, CHANGELOG, .gitignore. This story is executed in `scaffold_project` mode, not `{% if test_first %}code_test_first{% else %}code_direct{% endif %}`. It is marked `[Done]` by `scaffold_project` mode upon completion.
- **Second story (A.b)**: Always a minimal "Hello World" -- the smallest runnable artifact proving the environment is wired up.
- **Third story (A.c)**: An end-to-end stack spike -- a throwaway script (in `scripts/`, not the package) that wires the full critical path together before production modules.
- **Additional spikes**: Add as the first story of any phase introducing a major new integration boundary.
- **Each story**: Completable in a single session and independently verifiable.
- **Verification tasks**: Include where appropriate (e.g., "Verify: command prints version").
- **Version bump and changelog tasks**: Every versioned story must include these two tasks as the last items before any Verify tasks: `- [ ] Bump version to vX.Y.Z` (substituting the actual version) and `- [ ] Update CHANGELOG.md`.

## Recommended Phase Progression

| Phase | Name | Purpose |
|-------|------|---------|
| A | Foundation | Scaffolding (A.a), hello world (A.b), spike (A.c), core models, config, logging |
| B | Core Services | The main functional modules (one story per service) |
| C | Pipeline & Orchestration | Wiring services together, caching, concurrency, error handling |
| D | CLI & Library API | User-facing interfaces |
| E | Testing & Quality | Test suites, coverage, edge case tests |
| F | Documentation & Release | README, changelog, final testing, polish |
| G | CI/CD & Automation | GitHub Actions, coverage badges, release automation (if requested) |

Phases may be added, removed, or renamed to fit the project.

## Story Format

```markdown
### Story <Phase>.<letter>: v<version> <Title> [Planned]

<Optional one-line description.>

- [ ] Task 1
  - [ ] Subtask 1a
  - [ ] Subtask 1b
- [ ] Task 2
- [ ] Task 3
- [ ] Bump version to vX.Y.Z
- [ ] Update CHANGELOG.md
- [ ] Verify: <how to confirm the story is complete>
```

{% include "modes/_header-sequence.md" %}
