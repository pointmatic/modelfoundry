**Production Mode** (typically starts with CI/CD phase):
- Branch protection enabled (PRs required)
- CI checks mandatory before merge
- Security hardening (Dependabot, SECURITY.md, CONTRIBUTING.md)
- Bundled releases with multiple stories (v0.8.0 includes Stories J.a-J.d)

**When to switch:** After core functionality is complete and CI/CD is configured.

**Production Mode Transition Checklist:**
- Enable branch protection (require PR reviews, require status checks to pass)
- Create `CONTRIBUTING.md` (development setup, code style, PR process, release process)
- Create `SECURITY.md` (vulnerability reporting instructions)
- Create `.github/dependabot.yml` (automated dependency updates for pip and github-actions)
- Configure trusted publishers for package registries (PyPI, npm, etc.)
- Switch to PR-based workflow (no more direct commits to main branch)

