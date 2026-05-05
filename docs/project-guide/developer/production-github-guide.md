# Production Mode Git Workflow

This guide provides concise instructions for the branch-based workflow used in production mode projects with branch protection enabled.

---

## Prerequisites

- Branch protection is enabled on `main` branch
- Pull requests are required before merging
- CI checks must pass before merge

---

## GitHub Repository Setup

Before using this workflow, configure your repository settings on GitHub. These settings enforce production-mode practices.

### Manual Tasks (GitHub Web UI)

Navigate to your repository's **Settings** tab and configure the following:

#### 1. Branch Protection Rules

**Settings → Branches → Branch protection rules → Add rule**

Target branch: `default` (typically `main` or `master`)

- [ ] **Do not add any bypass list items** (no one should bypass protection)
- [ ] **Restrict deletions** — Prevent branch deletion
- [ ] **Require pull request before merging**
  - [ ] Require 1 approval
  - [ ] Require conversation resolution before merging
- [ ] **Require status checks to pass before merging**
  - [ ] Require branches to be up to date before merging
  - [ ] Status checks required: `unit-tests`, `integration-tests` (or your CI job names)
- [ ] **Block force pushes** — Prevent force pushes to main

Click **Create** or **Save changes**

#### 2. Security Settings

**Settings → Security → Code security and analysis**

- [ ] **Dependency graph** — Enable (shows dependencies)
- [ ] **Dependabot alerts** — Enable (security vulnerability alerts)
- [ ] **Dependabot security updates** — Enable (automatic security PRs)
- [ ] **Grouped security updates** — Enable (reduces PR noise by grouping updates)

#### 3. GitHub Actions Permissions

**Settings → Actions → General → Workflow permissions**

- [ ] Set to **Read repository contents and packages permissions**
  - This prevents workflows from accidentally pushing to protected branches
  - Workflows that need write access must use explicit tokens

**Note:** If you need workflows to create releases or push tags, use repository secrets with fine-grained permissions instead of the default `GITHUB_TOKEN`.

---

## Workflow Overview

```
1. Create feature branch
2. Make changes and commit
3. Push branch to GitHub
4. Create pull request
5. Wait for CI checks to pass
6. Merge pull request
7. Delete branch
8. Pull latest main
```

---

## Step-by-Step Instructions

### 1. Ensure You're on Latest Main

```bash
git switch main
git pull origin main
```

### 2. Create Feature Branch

**Branch naming convention:**
- Feature: `feature/<short-description>`
- Bug fix: `fix/<short-description>`
- Documentation: `docs/<short-description>`
- Story: `story/<story-id>-<short-description>`

```bash
# Example: Story J.d implementation
git switch -c story/j.d-release-workflow

# Example: Bug fix
git switch -c fix/codecov-upload-error

# Example: Documentation update
git switch -c docs/update-readme
```

### 3. Make Changes and Commit

```bash
# Make your changes
# ...

# Stage changes
git add .

# Commit with descriptive message
git commit -m "Story J.d: Add release workflow for PyPI publishing"
```

**Commit message format:**
- Start with story ID if applicable: `Story J.d: <description>`
- Or use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
- Keep first line under 72 characters
- Add detailed description in body if needed

### 4. Push Branch to GitHub

**First push:**
```bash
git push -u origin story/j.d-release-workflow
```

**Subsequent pushes (after more commits):**
```bash
git push
```

### 5. Create Pull Request on GitHub

**Via GitHub CLI (if installed):**
```bash
gh pr create --title "Story J.d: Release Workflow" --body "Implements automated PyPI publishing on version tags"
```

**Via GitHub Web UI:**
1. Go to `https://github.com/username/repo-name`
2. Click "Compare & pull request" button (appears after push)
3. Fill in PR title and description
4. Click "Create pull request"

**PR Title Format:**
- `Story J.d: Release Workflow`
- `Fix: Codecov upload error on protected branch`
- `Docs: Update README with installation instructions`

**PR Description Template:**
```markdown
## Summary
Brief description of changes

## Changes
- Added `.github/workflows/release.yml`
- Configured PyPI trusted publisher
- Updated README with release process

## Testing
- [ ] CI checks pass
- [ ] Manual testing completed (if applicable)

## Related Issues
Closes #123 (if applicable)
```

### 6. Wait for CI Checks

**Monitor CI status:**
- GitHub will automatically run CI checks
- View status in the PR "Checks" tab
- All required checks must pass before merge

**If CI fails:**
```bash
# Fix the issue locally
# ...

# Commit the fix
git add .
git commit -m "Fix: Resolve linting errors"

# Push to update the PR
git push
```

### 7. Merge Pull Request

**Via GitHub Web UI:**
1. Ensure all CI checks pass
2. Click "Merge pull request" button
3. Choose merge strategy:
   - **Squash and merge** (recommended for clean history)
   - **Create a merge commit** (preserves all commits)
   - **Rebase and merge** (linear history)
4. Click "Confirm merge"
5. Click "Delete branch" (cleanup)

**Via GitHub CLI:**
```bash
# Squash and merge
gh pr merge --squash --delete-branch

# Or merge with merge commit
gh pr merge --merge --delete-branch
```

### 8. Update Local Main Branch

```bash
# Switch back to main
git switch main

# Pull the merged changes
git pull origin main

# Delete local feature branch (if not auto-deleted)
git branch --delete story/j.d-release-workflow
```

---

## Common Scenarios

### Updating PR After Review Feedback

```bash
# Make requested changes
# ...

# Commit changes
git add .
git commit -m "Address review feedback: update error messages"

# Push to update PR
git push
```

### Syncing Branch with Latest Main

If `main` has been updated while you're working on your branch:

```bash
# Ensure you're on your feature branch
git switch story/j.d-release-workflow

# Fetch latest changes
git fetch origin

# Rebase on latest main
git rebase origin/main

# If conflicts occur, resolve them, then:
git add .
git rebase --continue

# Force push (rebase rewrites history)
git push --force-with-lease
```

**Note:** Use `--force-with-lease` instead of `--force` to avoid overwriting others' work.

### Abandoning a Branch

```bash
# Switch to main
git switch main

# Delete local branch
git branch --delete --force story/j.d-release-workflow

# Delete remote branch
git push origin --delete story/j.d-release-workflow
```

---

## Quick Reference

### Create and Push Branch
```bash
git switch main
git pull origin main
git switch -c feature/my-feature
# ... make changes ...
git add .
git commit -m "feat: add new feature"
git push -u origin feature/my-feature
```

### Update PR
```bash
# ... make changes ...
git add .
git commit -m "fix: address review feedback"
git push
```

### Merge and Cleanup
```bash
# After PR is merged on GitHub
git switch main
git pull origin main
git branch --delete feature/my-feature
```

---

## Best Practices

### Commit Messages
- ✅ `Story J.d: Add release workflow for PyPI publishing`
- ✅ `Fix: Resolve Codecov upload error on protected branch`
- ✅ `Docs: Update README with installation instructions`
- ❌ `fix stuff`
- ❌ `WIP`
- ❌ `asdf`

### Branch Names
- ✅ `story/j.d-release-workflow`
- ✅ `fix/codecov-upload-error`
- ✅ `docs/update-readme`
- ❌ `my-branch`
- ❌ `test`
- ❌ `fix`

### Pull Requests
- Write clear, descriptive titles
- Include summary of changes in description
- Reference related issues or stories
- Keep PRs focused (one feature/fix per PR)
- Respond to review feedback promptly

### CI Checks
- Always wait for CI to pass before merging
- Fix CI failures immediately
- Don't merge with failing tests
- Don't bypass required checks

---

## Troubleshooting

### "Push rejected" Error

**Problem:** Branch protection prevents direct push to `main`

**Solution:** Always work on a feature branch, never commit directly to `main`

```bash
# If you accidentally committed to main
git switch -c feature/my-changes  # Create branch from current state
git switch main
git reset --hard origin/main  # Reset main to remote state
git switch feature/my-changes
git push -u origin feature/my-changes
```

### "Diverged branches" Error

**Problem:** Local and remote branches have different histories

**Solution:** Pull with rebase or reset to remote

```bash
# Option 1: Rebase local changes on top of remote
git pull --rebase origin feature/my-branch

# Option 2: Reset to remote (loses local commits)
git reset --hard origin/feature/my-branch
```

### "CI checks failed" on PR

**Problem:** Tests or linting failed

**Solution:** Fix locally and push

```bash
# Run tests locally
pytest

# Run linting locally
ruff check .
ruff format --check .

# Fix issues, commit, and push
git add .
git commit -m "fix: resolve CI failures"
git push
```

---

## GitHub CLI Quick Setup

Install GitHub CLI for easier PR management:

```bash
# macOS
brew install gh

# Authenticate
gh auth login

# Create PR
gh pr create

# View PR status
gh pr status

# Merge PR
gh pr merge --squash --delete-branch
```

---

## Summary

**Production mode workflow:**
1. Always work on feature branches
2. Never commit directly to `main`
3. Create PR for all changes
4. Wait for CI checks to pass
5. Merge via GitHub UI or CLI
6. Keep `main` branch clean and stable

**Key commands:**
- `git switch -c feature/name` — Create branch
- `git push -u origin feature/name` — Push branch
- `gh pr create` — Create PR
- `git switch main && git pull` — Update main
