# Best Practices Guide — LLM-Assisted Development

This guide documents key learnings and best practices for LLM-assisted software development. Keep this minimal and focused on actionable principles.

---

## Development Modes

### Velocity Mode vs. Production Mode

**Problem:** Applying production-grade processes too early slows down initial development. Conversely, maintaining velocity practices in production projects creates security and quality risks.

**Best Practice:**

Recognize and adapt to two distinct development modes:

**Velocity Mode** (Early Development):
- **When:** Phases A-F (foundation through initial testing)
- **Practices:**
  - Direct commits to main branch
  - Minimal process overhead
  - Version bump per story (v0.1.0 → v0.2.0 → v0.3.0)
  - Focus on feature completion and iteration speed
  - Skip branch protection, PR reviews, security policies
- **Commit messages:** `"Story A.a: v0.1.0 Hello World"`

**Production Mode** (Mature Development):
- **When:** After CI/CD phase is complete and core functionality works
- **Practices:**
  - Branch protection enabled (PRs required)
  - CI checks mandatory before merge
  - Security hardening (Dependabot, SECURITY.md, CONTRIBUTING.md)
  - Bundled releases with multiple stories (v0.8.0 includes J.a-J.d)
  - Trusted publishers for package registries
  - Code review requirements
- **Commit messages:** `"Story J.c: Branch Protection & Repo Settings"`
- **Release process:** Tag-based automation with GitHub Releases

**The Switch:**
- Occurs when enabling branch protection (typically in the CI/CD phase)
- Marked by adding security and contribution policies
- From this point forward, all changes go through PRs
- Version numbers may skip (v0.7.1 → v0.8.0 bundling multiple stories)

**How to Audit:**
- Check if branch protection is enabled → should be ON for production projects
- Look for CONTRIBUTING.md and SECURITY.md → missing indicates velocity mode
- Review recent commits → direct to main = velocity, via PRs = production
- Check version history → incremental (v0.1→v0.2) = velocity, bundled releases = production

**Rationale:** Velocity mode maximizes learning and iteration speed when exploring solutions. Production mode maximizes stability and security when users depend on the project. Using the wrong mode at the wrong time either slows progress unnecessarily or creates technical debt.

---

## Hello World First — Spike Early, Spike Often

### Front-Load Integration Risk With Minimal End-to-End Spikes

**Problem:** Projects with multiple external dependencies (ML frameworks, cloud APIs,
hardware accelerators, async libraries) often discover a critical assumption doesn't
hold — wrong backend, incompatible library versions, missing system dependency —
only after significant production code has been written. This is the "jump off the
cliff YOLO" failure mode: everything looks fine until the very end, when it isn't.

**Best Practice:**

Before writing any production module code, create a **minimal throwaway spike** that
wires the full stack together end-to-end. The spike:

- Lives in `scripts/` or `notebooks/`, **not** in the installable package
- Is explicitly labelled throwaway (comment at the top: `# SPIKE — not production code`)
- Uses hardcoded values, no config, no abstraction
- Does exactly one thing: prove the critical path works

A project with multiple integration layers warrants **multiple spikes**, one per
major new integration boundary. Add a new spike story whenever you introduce:

- A new external service or API
- A new hardware accelerator (GPU, MPS, TPU)
- A new async or concurrency framework
- A new ML framework or model serving path

**Spike placement in `stories.md`:**

- **First spike (A.b):** Immediately after scaffolding (A.a), before any
  production modules. Validates the core technology stack.
- **Subsequent spikes:** As early as possible after the integration boundary
  is introduced — typically the first story in the phase that introduces it.
- Spikes get their own version bump and story ID.
- Once a spike passes, the production implementation that follows it can
  proceed with confidence.

**Example — the shape of a good spike:**

```
Script: scripts/spike_<integration_name>.py
───────────────────────────────────────────
1. Acquire the resource (connect to API, load dataset, initialize client)
2. Confirm the environment (log version, device, credentials, region, etc.)
3. Execute the critical path (one real operation end-to-end)
4. Assert the output is sane (type check, range check, non-empty)
5. Print a human-readable summary

If this script runs and produces sensible output, the integration is validated.
If it fails, you find out now — before writing the modules that depend on it.
```

**What a spike is NOT:**

- A prototype to keep and clean up — delete or clearly archive it after it passes
- A substitute for proper tests — it proves the path exists, not that it's correct
- An excuse to skip the production implementation — it's a gate, not a destination

**Rationale:** The cost of discovering a broken assumption at A.b (one story in) is
near zero. The cost of discovering it at D.b (ten stories in) is a potential
rewrite. Spikes are cheap insurance against the most expensive category of failure.

---

## CI/CD Setup

### Always Validate Locally Before Creating CI Infrastructure

**Problem:** Creating CI workflows before ensuring the codebase passes linting/formatting leads to immediate CI failures and wasted effort.

**Best Practice:**

1. **Run linting and formatting checks locally FIRST:**
   ```bash
   # Python projects
   ruff check .
   ruff format --check .
   pytest tests/
   
   # JavaScript projects
   npm run lint
   npm run format:check
   npm test
   
   # Go projects
   go fmt ./...
   go vet ./...
   go test ./...
   ```

2. **Fix all errors** before proceeding

3. **Then** create CI workflow files (`.github/workflows/ci.yml`, etc.)

4. **Then** create supporting configs (`codecov.yml`, etc.)

**Rationale:** CI workflows should **verify** already-clean code, not be the **first discovery** of linting issues. This prevents false starts and ensures the first CI run will succeed.

---

## Code Quality

### Maintain Clean Code Throughout Development

**Problem:** Accumulating linting errors during feature development creates technical debt and blocks CI adoption.

**Best Practice:**

- Run linting checks after **every significant change** (not just at the end)
- Fix linting errors **immediately** rather than deferring them
- Use auto-fix options when safe: `ruff check . --fix`, `npm run lint -- --fix`
- Configure your editor to show linting errors in real-time

**Rationale:** Small, incremental fixes are easier than batch-fixing 100+ errors at once.

---

## Testing

### Test Changes Immediately After Implementation

**Problem:** Implementing multiple features before running tests makes it harder to isolate failures.

**Best Practice:**

- Run tests after completing **each story or sub-task**
- Verify tests pass before moving to the next feature
- If tests fail, fix immediately before continuing

**Rationale:** Faster feedback loops reduce debugging time and prevent cascading failures.

---

## Documentation

### Keep Documentation In Sync With Code

**Problem:** Outdated documentation misleads developers and wastes time.

**Best Practice:**

- Update relevant docs (README, tech specs, API docs) **in the same commit** as code changes
- Mark completed tasks in `stories.md` as `[Done]` immediately after verification
- Document breaking changes prominently

**Rationale:** Documentation drift is harder to fix retroactively than maintaining it continuously.

---

## Version Control

### Commit Logical Units of Work

**Problem:** Large, unfocused commits make code review difficult and rollbacks risky.

**Best Practice:**

- One story/feature per commit when possible
- Include both code and documentation changes in the same commit
- Write clear commit messages that reference story IDs: `"Story H.d: Service error classification and exception migration"`

**Rationale:** Atomic commits make history readable and enable selective rollbacks.

---

## Dependency Management

### Verify Dependencies Before Adding Them

**Problem:** Adding untested dependencies can introduce breaking changes or compatibility issues.

**Best Practice:**

- Test new dependencies locally before adding to `pyproject.toml`/`package.json`
- Check compatibility with existing dependencies
- Document why each dependency is needed (in comments or docs)
- Prefer well-maintained, widely-used libraries

**Rationale:** Dependency issues are easier to prevent than to debug after integration.

---

## Error Handling

### Design Error Handling Before Implementation

**Problem:** Retrofitting error handling into existing code is error-prone and incomplete.

**Best Practice:**

- Define error types and codes **before** implementing features
- Document which errors are retryable vs. permanent
- Test error paths explicitly, not just happy paths

**Rationale:** Error handling is a first-class concern, not an afterthought.

---

## Open Source Sustainability

### GitHub Sponsors & Funding

**Problem:** Open-source maintainers often struggle to sustain projects long-term without financial support, leading to burnout or project abandonment.

**Best Practice:**

For public open-source projects, consider setting up funding options to support ongoing maintenance and development.

**Why Enable Funding?**
- Supports maintainer time and effort
- Signals project value to the community
- Enables faster feature development and bug fixes
- Covers infrastructure costs (hosting, domains, CI minutes)
- Builds a sustainable open-source ecosystem

**Setup Steps:**

1. **Create `.github/FUNDING.yml`** in your repository root
2. **Choose funding platforms:**
   - **GitHub Sponsors** (integrated into GitHub, no fees)
   - **Patreon** (recurring monthly support)
   - **Ko-fi** (one-time or monthly donations)
   - **Buy Me a Coffee** (simple one-time donations)
   - **Open Collective** (transparent fund management)
   - **Custom URLs** (PayPal, Stripe, etc.)

3. **Add your usernames to the config:**
   ```yaml
   # .github/FUNDING.yml
   github: [your-github-username]
   patreon: your-patreon-username
   ko_fi: your-kofi-username
   custom: ["https://www.buymeacoffee.com/yourname"]
   ```

4. **GitHub displays a "Sponsor" button** on your repository page

**Best Practices:**
- **Be transparent** about how funds are used
- **Keep it optional** and non-intrusive (never paywall features)
- **Update sponsors** on progress and roadmap
- **Offer perks** (optional): early access, priority support, sponsor recognition
- **Set realistic goals** and communicate them clearly
- **Thank sponsors** publicly (with permission) or privately

**When to Enable:**
- **Early projects:** Wait until the project has proven value and users
- **Mature projects:** Enable when you're committed to long-term maintenance
- **Popular projects:** Essential for sustainability at scale

**Rationale:** Sustainable open-source development requires resources. Funding options allow users who benefit from your work to contribute back, creating a healthier ecosystem for everyone.

---

## General Principles

### Measure Twice, Cut Once

- **Validate assumptions** before implementing
- **Run checks locally** before creating CI
- **Test incrementally** rather than in large batches
- **Review changes** before marking stories complete

### Fail Fast, Fix Fast

- Don't defer error fixes to "later"
- Address linting/test failures immediately
- Small, frequent corrections beat large batch fixes

### Document As You Go

- Update docs in the same commit as code
- Record decisions and rationale
- Keep stories.md current with progress

---

## Adding New Best Practices

When you discover a new pattern or anti-pattern:

1. Document it here in a new section
2. Keep the description **minimal** (problem, practice, rationale)
3. Focus on **actionable** guidance, not theory
4. Use **concrete examples** when helpful

This guide should grow organically as the project evolves.
