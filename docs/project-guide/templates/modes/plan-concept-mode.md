Define the problem space (problem statement, why, pain points, target users, value criteria) and the solution space (solution statement, goals, scope, constraints), and pain point to solution mapping.

## Prerequisites

Before starting, the developer must provide (or the LLM must ask for):

1. **A project idea** -- a short description of what the project should do (a few sentences to a few paragraphs). This is often documented in a `docs/specs/idea.md` file.

## Steps

1. Define the problem space 
   - problem_statement: A few sentences describing the problem, plus any other useful context, examples, or references
   - problem_why: Root causes of the problem and why the problem persists
   - pain_points: A list of points 
   - target_users: A description of those impacted by the problem (positively/negatively, directly/indirectly)
   - value_criteria: How to measure solution value
2. Define the solution space 
   - one_liner: A catchy, benefit-oriented phrase starting with a verb that completes the sentence "This project <one_liner>."
   - solution_statement: A few sentences that describe the solution in action, benefitting the target users, with some hints at technical approach
   - goals: How the solution addresses the value criteria
   - scope: What the solution will and won't do
   - constraints: Technical, regulatory, or business limitations
3. Map pain points to solution
   - pain_point_to_solution_mapping: A mapping of pain point labels to descriptions on how the solution addresses the pain in the pain_point_to_solution_mapping format below.
4. Generate `docs/specs/concept.md` using the artifact template at `templates/artifacts/concept.md`.

## Formats

### pain_points

```markdown
- **<pain_point_label_1>**: <pain_point_description_1>
- **<pain_point_label_2>**: <pain_point_description_2>
- ...
```

### pain_point_to_solution_mapping

```markdown
**<pain_point_label_1>**: 
  - <solution_description_1>
  - <solution_description_2>
  ...
**<pain_point_label_2>**: 
  - <solution_description_1>
  - <solution_description_2>
  ...
...
```

{% include "modes/_header-sequence.md" %}
