# Guides Directory

**IMPORTANT: Needs update**

This directory contains documentation for LLM-assisted development workflows and developer reference materials.

## Project Workflow Overview

The LLM creates or improves the following documents **in order**, waiting for developer approval after each one:

| Step | Document | Purpose |
|------|----------|---------|
| 1 | `docs/specs/features.md` | What the project does (requirements, not implementation) |
| 2 | `docs/specs/tech-spec.md` | How the project is built (architecture, modules, dependencies) |
| 3 | `docs/specs/stories.md` | Step-by-step implementation plan (phases, stories, checklists) |

After all three documents are approved, the LLM proceeds to scaffold the project and implement stories one by one.

## Development Mode – Focused LLM Prompts

Project-Guide provides structured instructions for LLMs to follow when working on projects focused on the subset of tasks that are needed, called a "mode":

- **`project_guide.md`** - Core workflow for LLM-assisted project creation from scratch. Read this at the start of every new project session.
- **`best_practices_guide.md`** - Diagnostic patterns and anti-patterns for evaluating project quality. Use for occasional audits.
- **`debug_guide.md`** - Test-driven debugging methodology for fixing bugs in existing projects.
- **`documentation-setup-guide.md`** - Step-by-step workflow for setting up GitHub Pages documentation with MkDocs and custom landing pages.

## Developer-Focused Guides

The `developer/` subdirectory contains manual setup instructions and troubleshooting guides for human developers:

- Manual service configuration (e.g., Codecov, PyPI trusted publishers)
- Troubleshooting references
- One-time setup procedures
- Production mode workflow and GitHub repository setup

These guides are primarily for manual setup tasks, but LLMs may reference excerpts when providing step-by-step instructions or documenting procedures in stories.

## Usage

**For LLMs:**
- Consult `go-project_guide.md` at the start of every project session

**???**
- Reference `debug_guide.md` when bugs are reported
- Use `documentation-setup-guide.md` when setting up public documentation
- Check `best_practices_guide.md` when auditing project quality

**For Developers:**
- Refer to `developer/` guides for manual setup tasks
- Use these guides as troubleshooting references
