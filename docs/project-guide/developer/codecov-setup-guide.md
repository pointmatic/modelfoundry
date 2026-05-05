# Codecov Setup Guide

This guide explains how to set up Codecov integration for your GitHub repository.

## Prerequisites

- Repository must be on GitHub
- Codecov account (free for open source)
- GitHub Actions workflow that generates coverage reports

## Important: Public vs Private Repositories

**For Public Repositories:**
- ✅ **No token required!** Codecov uses GitHub's OIDC authentication automatically
- The workflow is already configured to work without a token
- Simply add the repository to your Codecov account and it will start receiving coverage data

**For Private Repositories:**
- 🔑 Token is required
- Follow the "Add Token to GitHub Secrets" section below

## Setup Steps (Public Repository)

### 1. Create Codecov Account

1. Go to [codecov.io](https://codecov.io)
2. Sign in with your GitHub account
3. Authorize Codecov to access your repositories

### 2. Add Repository to Codecov

1. In Codecov dashboard, click "Add new repository"
2. Find and select your repository (e.g., `username/repo-name`)
3. That's it! No token needed for public repos.

### 3. Verify Setup

After adding the repository:

1. Push a commit to trigger the GitHub Actions workflow
2. Wait for tests to complete
3. Check the Actions tab for successful codecov uploads
4. Visit `https://codecov.io/gh/username/repo-name` to see coverage reports
5. The README badge should now show coverage percentage instead of "unknown"

## Setup Steps (Private Repository Only)

### Add Token to GitHub Secrets

Only needed if the repository is private:

1. In Codecov dashboard, get the upload token for your repository
2. Go to your GitHub repository: `https://github.com/username/repo-name`
3. Navigate to **Settings** → **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. Name: `CODECOV_TOKEN`
6. Value: Paste the token from Codecov dashboard
7. Click **Add secret**

## Configuration

Create a `codecov.yml` configuration file at the repository root with your desired settings:

```yaml
coverage:
  status:
    project:
      default:
        target: 80%  # Minimum coverage target
        threshold: 2%  # Allow 2% drop before failing
    patch:
      default:
        target: 80%  # Coverage for new code

  precision: 2  # Decimal places in reports

ignore:
  - "tests/"
  - "docs/"
  - "__pycache__/"
  - "*.pyc"

comment:
  layout: "reach,diff,flags,tree"
  behavior: default
  require_changes: false
```

Adjust the configuration based on your project needs:
- **Target coverage**: Set your minimum acceptable coverage percentage
- **Ignored paths**: Exclude files/directories that shouldn't count toward coverage
- **Flags**: Use flags to track coverage for different test suites or components
- **Comment behavior**: Configure how Codecov comments on pull requests

## GitHub Actions Integration

Add the Codecov upload step to your CI workflow:

```yaml
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml  # Path to your coverage file
    flags: unittests  # Optional: flag name
    fail_ci_if_error: true  # Fail the build if upload fails
```

For Python projects using pytest-cov:
```yaml
- name: Run tests with coverage
  run: pytest --cov=your_package --cov-report=xml --cov-report=term-missing

- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml
```

## Troubleshooting

### Badge shows "unknown"

- Verify the repository is added to your Codecov account
- Check GitHub Actions logs for upload errors
- Ensure your test command generates a coverage report file
- Verify codecov-action@v4 is running successfully in your workflow
- For private repos, verify `CODECOV_TOKEN` is set in GitHub Secrets

### Upload fails

- Check that the token is correct (no extra spaces) for private repos
- Verify the repository is added to your Codecov account
- Check GitHub Actions logs for specific error messages
- Ensure the coverage file path in the workflow matches the actual file location

### Coverage not updating

- Verify the test job ran successfully and generated coverage data
- Check that the codecov upload step runs after test execution
- Ensure the coverage file path is correct
- Check Codecov dashboard for upload errors

## Coverage Badge

Add a coverage badge to your README:

```markdown
[![codecov](https://codecov.io/gh/username/repo-name/branch/main/graph/badge.svg)](https://codecov.io/gh/username/repo-name)
```

Replace `username/repo-name` with your actual repository path.

## Local Coverage

Generate coverage reports locally for debugging:

**Python (pytest-cov):**
```bash
pytest --cov=your_package --cov-report=html --cov-report=term-missing
open htmlcov/index.html
```

**JavaScript (Jest):**
```bash
npm test -- --coverage
open coverage/lcov-report/index.html
```

**Go:**
```bash
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

## References

- [Codecov Documentation](https://docs.codecov.com/)
- [codecov-action GitHub](https://github.com/codecov/codecov-action)
- [Coverage.py Documentation](https://coverage.readthedocs.io/) (Python)
- [Istanbul Documentation](https://istanbul.js.org/) (JavaScript)
- [Go Coverage](https://go.dev/blog/cover) (Go)
