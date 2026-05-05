Define **what** the project does -- requirements, inputs, outputs, behavior -- without specifying **how** it is implemented. This is the source of truth for scope.

The high-level concept (why) should be captured in `concept.md`. The implementation details (how) should be written in `tech-spec.md`. The breakdown of the implementation plan (step-by-step tasks) should be written in `stories.md`.

## Prerequisites

The approved `docs/specs/concept.md` must exist before starting this mode. It is the primary source for almost every field below — read it first and treat it as authoritative.

These inputs may also be supplied directly by the developer, but in practice they are usually already implied by `concept.md` or by files in the repo:

1. **License preference** -- e.g. Apache-2.0, MIT, MPL-2.0, GPL-3.0. If a `LICENSE` file already exists in the project root, that license prevails. If `concept.md` names a license, use that.
2. **Target audience** -- CLI tool, library, web app, etc. Usually stated in `concept.md`.
3. **Constraints** -- no UI, no database, must run offline, etc. (if any). Usually stated in `concept.md`.

## Steps

1. **Read what already exists before asking anything.** Open `docs/specs/concept.md` in full, plus any sibling documents it references (e.g. dependency specs, design notes) and any `LICENSE` file in the project root. Do this *before* presenting the developer with a list of prerequisites or questions — the goal is to enter step 2 already knowing most of the answers.

2. Gather information, deriving as much as possible from the documents read in step 1. **Do not enumerate prerequisites or ask for items that `concept.md` already supplies** — silently fill them in. Ask the developer only about fields that are genuinely missing or ambiguous after reading, and ask in a single consolidated round rather than one at a time. Fields to populate:
   - project_name: The project name
   - programming_language: e.g., Python 3.11+, Node 22, Go 1.23
   - project_goal: One paragraph on what the project should accomplish
   - core_requirements: The essential functionality
   - operational_requirements: Error handling, logging, configuration, CLI interface, etc.
   - quality_requirements: Reliability, clarity, minimal dependencies, cross-platform, etc.
   - usability_requirements: Who uses it and how (CLI, library, web, etc.)
   - non_goals: What the project explicitly does NOT do
   - inputs: Required and optional inputs with examples (CLI args, config files, env vars)
   - outputs: File structures, console output, data formats
   - functional_requirements: Numbered list of features with behavior descriptions and edge cases
   - configuration: Config precedence, config file format/schema
   - testing_requirements: Minimum test coverage expectations
   - security_notes: Security and compliance considerations (if applicable)
   - performance_expectations: User-facing performance requirements (e.g., real-time processing, batch reports within 1 hour, response time under 200ms) (if applicable)
   - acceptance_criteria: Definition of done for the whole project

3. Generate `docs/specs/features.md` using the artifact template at `templates/artifacts/features.md`

4. Present the complete document to the developer for approval. Iterate as needed.

## Formats

### functional_requirements

```markdown
### FR-1: Feature Name

Description of the feature's purpose.

**Behavior:**
1. Step 1
2. Step 2
3. Step 3

**Edge Cases:**
- Edge case 1 -> How it's handled
- Edge case 2 -> How it's handled
```

{% include "modes/_header-sequence.md" %}
