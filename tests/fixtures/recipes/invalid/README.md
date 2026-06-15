# Invalid recipe fixtures

One recipe per **file-expressible** FR-2 validator rejection — each is otherwise
valid and mutated to fail exactly one check. Consumed by Story E.b's validator
tests. Each file's header comment names the check it targets.

Checks **not** represented as files (they cannot be authored as a "loadable but
invalid" recipe, so E.b exercises them inline):

- **Checks 9 / 10 / 15** — `Optimization.sampler` / `pruner`, `Optimization.n_jobs`,
  and `Visualizations[].mode` are `Literal`/constrained pydantic fields, so an
  invalid value is rejected at *construction* time, not at validate time.
- **Check 17** — plugin op-param validation depends on the bound plugin's
  `OperationSpec.param_model`; exercised with a synthetic plugin in E.b.
- **Check 19** — DataRefinery schema-version coordination is a property of the
  *bound instance*, not the recipe text; exercised with a synthesized instance.

`invalid_schema_version.yml` is rejected by `recipe.loader` (the schema-version
gate) rather than by `validate()`; it is included for completeness of check 1.
