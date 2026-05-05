# Descriptions Guide — Generating Project Descriptions

This guide provides instructions for creating a `docs/specs/descriptions.md` file that serves as the canonical source of truth for all descriptive language used across a project.

---

## Purpose

The `descriptions.md` file centralizes all project descriptions, taglines, and marketing copy in one location. This ensures consistency across:
- README.md
- Landing page (docs/index.html)
- Package metadata (pyproject.toml, package.json)
- Feature documentation (features.md)
- GitHub repository settings

**Benefits:**
- Single source of truth for all project descriptions
- Consistency across all consumer files
- Easy to update descriptions project-wide
- Clear guidance on which description to use where

---

## When to Create

Create `descriptions.md` as an **early step** in the documentation setup phase, specifically:

1. **After** the project has core functionality implemented
2. **Before** creating the landing page or final README
3. **During** the documentation phase (typically Phase H or F)

This allows you to finalize descriptions once and disseminate them to all consumer files.

---

## File Structure

Create `docs/specs/descriptions.md` with the following sections:

### Header

```markdown
# descriptions.md — <project-name>

Canonical source of truth for all descriptive language used across the project. All consumer files (README.md, docs/index.html, pyproject.toml, features.md) should draw from these definitions.

---
```

### Section 1: Name

```markdown
## Name

- <github-repo-name> (GitHub)
- <package-name> (PyPI/npm/crates.io)
```

**Example:**
```markdown
## Name

- yt-fetch (GitHub)
- tubefetch (PyPI)
```

**Note:** Include this section only if the GitHub repository name differs from the package name.

---

### Section 2: Tagline

```markdown
## Tagline

<3-5 word tagline>
```

**Guidelines:**
- 3-5 words maximum
- Action-oriented verb + key benefit
- No punctuation

**Examples:**
- "Fetch AI-ready YouTube content"
- "Resilient retry for Python"
- "Manage LLM project guides"

---

### Section 3: Long Tagline

```markdown
## Long Tagline

<One sentence expanding on the tagline>
```

**Guidelines:**
- One sentence, 10-15 words
- Expands on the tagline with more detail
- No period at the end

**Examples:**
- "Extract AI-ready YouTube content: metadata, transcripts, and media in structured formats."
- "Add resilient retry logic to any Python function with exponential backoff and circuit breakers."

---

### Section 4: One-liner

```markdown
## One-liner

<Single sentence describing what the project does>
```

**Guidelines:**
- One sentence, 8-12 words
- Complete sentence with period
- Focus on the core capability

**Examples:**
- "Fetch structured, AI-ready content from YouTube videos."
- "Add resilient retry logic to Python functions."

---

### Section 5: Friendly Brief Description

```markdown
### Friendly Brief Description (follows one-liner)

<2-3 sentence description for general audiences>
```

**Guidelines:**
- 2-3 sentences
- Accessible to non-technical users
- Mentions key features and benefits
- Follows naturally after the one-liner

**Example:**
```markdown
### Friendly Brief Description (follows one-liner)

yt-fetch fetches and extracts metadata, transcripts, and media from YouTube videos in formats optimized for AI/LLM pipelines — with batch processing, caching, retries, and rate limiting.
```

---

### Section 6: Two-clause Technical Description

```markdown
## Two-clause Technical Description

<Technical description in exactly two clauses separated by a comma>
```

**Guidelines:**
- Exactly two clauses separated by a comma
- First clause: what it does
- Second clause: how it works or key features
- Technical audience (developers)

**Example:**
```markdown
## Two-clause Technical Description

A Python CLI and library that fetches and extracts structured metadata and transcripts from YouTube videos, producing LLM-ready plain text, content hashes for change detection, and unified video bundles with batch processing, caching, and retry logic.
```

---

### Section 7: Benefits

```markdown
## Benefits

- **<Feature 1>** — <description>
- **<Feature 2>** — <description>
- **<Feature 3>** — <description>
...
```

**Guidelines:**
- Bulleted list of key features/benefits
- Each bullet: **Bold title** — description
- 5-10 items
- Focus on user-facing capabilities
- Order by importance or logical flow

**Example:**
```markdown
## Benefits

- **Metadata** — title, channel, duration, tags, upload date via yt-dlp
- **Transcripts** — fetched via youtube-transcript-api with language preference
- **Batch processing** — concurrent workers with per-video error isolation
- **Caching** — skip already-fetched data; selective `--force` overrides
- **CLI + Library** — use from the command line or import as a Python package
```

---

### Section 8: Technical Description

```markdown
## Technical Description

<3-5 sentence technical overview for developers>
```

**Guidelines:**
- 3-5 sentences
- Technical depth (architecture, key components, use cases)
- Mentions implementation details
- Suitable for README "About" section

**Example:**
```markdown
## Technical Description

yt-fetch is a Python tool that extracts structured, AI-ready content from YouTube videos. Given one or more video IDs, URLs, playlists, or channels, it produces normalized metadata, transcripts, and optional media in formats optimized for downstream AI/LLM pipelines. It provides content hashes for change detection, optional token count estimates, and unified video bundles. The tool supports both CLI and library usage with batch processing, intelligent caching, configurable retries via gentlify, and rate limiting.
```

---

### Section 9: Keywords

```markdown
## Keywords

`keyword1`, `keyword2`, `keyword3`, ...
```

**Guidelines:**
- Comma-separated list in backticks
- 10-15 keywords
- Include: technology stack, use cases, key features
- Suitable for package metadata and SEO

**Example:**
```markdown
## Keywords

`youtube`, `transcript`, `metadata`, `yt-dlp`, `video`, `ai`, `llm`, `content-extraction`, `batch-processing`, `cli`, `python`, `async`, `rate-limiting`, `retry`
```

---

### Section 10: Feature Cards

```markdown
## Feature Cards

Short blurbs for landing pages and feature grids. Each card has a title and a one-to-two sentence description.

| # | Title | Description |
|---|-------|-------------|
| 1 | <Feature 1 Title> | <1-2 sentence description> |
| 2 | <Feature 2 Title> | <1-2 sentence description> |
...
```

**Guidelines:**
- 6-8 feature cards
- Each card: number, title, 1-2 sentence description
- Title: 2-4 words, action-oriented
- Description: specific, benefit-focused
- Suitable for landing page feature grids

**Example:**
```markdown
| # | Title | Description |
|---|-------|-------------|
| 1 | Structured Metadata | Extract title, channel, duration, tags, and upload date via yt-dlp or YouTube Data API v3. |
| 2 | Multi-Format Transcripts | Fetch transcripts with language preference and fallback, export as JSON, plain text, WebVTT, or SubRip. |
| 3 | LLM-Ready Output | Produce plain text transcripts optimized for AI pipelines with content hashes and optional token counts. |
```

---

### Section 11: Usage Notes

```markdown
## Usage Notes

| File | Which descriptions to use |
|------|--------------------------|
| `README.md` line X | <Description type> |
| `docs/index.html` hero `<h1>` | <Description type> |
| `pyproject.toml` description | <Description type> |
| (GitHub Repository) | <Description type> |
...
```

**Guidelines:**
- Table mapping files to which descriptions to use
- Include line numbers or specific locations
- Cover all consumer files in the project

**Example:**
```markdown
## Usage Notes

| File | Which descriptions to use |
|------|--------------------------|
| `README.md` line 7 | Two-clause Technical Description |
| `README.md` line 13 | Benefits (inline) |
| `docs/index.html` hero `<h1>` | One-liner |
| `docs/index.html` hero `<p>` | Friendly Brief Description |
| `docs/index.html` feature grid | Feature Cards |
| `pyproject.toml` description | Long Tagline |
| (GitHub Repository) | One-liner + ":" + Long Tagline |
```

---

## LLM Instructions for Generating descriptions.md

When generating `descriptions.md` for a project, follow these steps:

### Step 1: Gather Context

Read the following files to understand the project:
- `docs/specs/features.md` — what the project does
- `docs/specs/tech-spec.md` — how it's built
- `README.md` — current descriptions (if any)
- Source code — key modules and capabilities

### Step 2: Generate Descriptions

Create each section in order:

1. **Name** — identify GitHub repo name and package name
2. **Tagline** — distill core value into 3-5 words
3. **Long Tagline** — expand tagline into one sentence
4. **One-liner** — single sentence describing what it does
5. **Friendly Brief Description** — 2-3 sentences for general audiences
6. **Two-clause Technical Description** — technical summary in two clauses
7. **Benefits** — list 5-10 key features with descriptions
8. **Technical Description** — 3-5 sentence technical overview
9. **Keywords** — 10-15 relevant keywords
10. **Feature Cards** — 6-8 feature cards for landing page
11. **Usage Notes** — map descriptions to consumer files

### Step 3: Present for Approval

Present the complete `descriptions.md` file to the developer for review and approval.

### Step 4: Disseminate Descriptions

After approval, update all consumer files with the appropriate descriptions:

**Automatic Updates (LLM can do):**
- `README.md` — update description sections
- `docs/index.html` — update hero text and feature cards
- `pyproject.toml` (or `package.json`) — update description field
- `docs/specs/features.md` — update header description

**Manual Updates (developer must do):**
- GitHub repository settings:
  - Description: One-liner + ":" + Long Tagline
  - Topics: Keywords (without backticks)
  - About section

---

## Integration with Documentation Setup

The `descriptions.md` file should be created as **Step 0.5** in the documentation setup workflow:

**Revised Documentation Setup Order:**

1. **Prerequisites** — Ensure required images exist
2. **Step 0.5: Create descriptions.md** — Generate canonical descriptions (this guide)
3. **Step 1: Create MkDocs Configuration** — Set up mkdocs.yml
4. **Step 2: Create Custom Landing Page** — Use descriptions from descriptions.md
5. **Step 3: Create Documentation Pages** — Reference descriptions as needed
6. **Step 4: Deploy to GitHub Pages** — Set up workflow

This ensures descriptions are finalized before being used in the landing page and documentation.

---

## Example Template

```markdown
# descriptions.md — <project-name>

Canonical source of truth for all descriptive language used across the project.

---

## Name

- <github-name> (GitHub)
- <package-name> (PyPI)

## Tagline

<3-5 words>

## Long Tagline

<One sentence>

## One-liner

<Single sentence>

### Friendly Brief Description (follows one-liner)

<2-3 sentences>

## Two-clause Technical Description

<Two clauses>

## Benefits

- **Feature 1** — description
- **Feature 2** — description

## Technical Description

<3-5 sentences>

## Keywords

`keyword1`, `keyword2`, `keyword3`

---

## Feature Cards

| # | Title | Description |
|---|-------|-------------|
| 1 | Title | Description |

---

## Usage Notes

| File | Which descriptions to use |
|------|--------------------------|
| `README.md` | <type> |
| `docs/index.html` | <type> |
```

---

## Summary

The `descriptions.md` file is a critical documentation artifact that:
- Centralizes all project descriptions in one place
- Ensures consistency across README, landing page, and package metadata
- Provides clear guidance on which description to use where
- Should be created early in the documentation phase
- Must be approved before disseminating to consumer files
