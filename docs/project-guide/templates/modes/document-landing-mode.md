Implement the landing page (GitHub Pages) and extended documentation (MkDocs Material theme). You will create a custom landing page (`index.html`) as the home page combined with MkDocs Material theme built from markdown pages for additional documentation.

## Overview

**Architecture:**
- **Landing page**: Custom `index.html` with branded design, hero section, and quick start
- **Documentation**: MkDocs with Material theme for structured docs
- **Deployment**: GitHub Actions to GitHub Pages

**Benefits:**
- Beautiful, branded landing page with full design control
- Professional documentation with Material theme features (search, navigation, dark mode)
- Single deployment workflow
- Markdown-based documentation (easy to maintain)

## Prerequisites

- GitHub repository
- Python 3.11+ installed locally
- Basic knowledge of HTML/CSS (optional, if you want to customize the landing page)

## Step 1: Create Project Descriptions

Before creating the landing page and documentation, generate a `docs/specs/descriptions.md` file that serves as the canonical source of truth for all project descriptions, taglines, and marketing copy.

**Purpose:**
- Centralizes all descriptive language in one location
- Ensures consistency across README, landing page, package metadata, and GitHub settings
- Provides clear guidance on which description to use where

**Process:**

1. **Read the descriptions guide**: See `docs/guides/descriptions-guide.md` for complete instructions on generating this file
2. **Generate descriptions.md**: Create `docs/specs/descriptions.md` with the following sections:
   - Name (GitHub vs. package name if different)
   - Tagline (3-5 words)
   - Long Tagline (one sentence)
   - One-liner (single sentence)
   - Friendly Brief Description (2-3 sentences)
   - Two-clause Technical Description
   - Benefits (bulleted list of 5-10 features)
   - Technical Description (3-5 sentences)
   - Keywords (10-15 keywords)
   - Feature Cards (6-8 cards for landing page)
   - Usage Notes (mapping descriptions to consumer files)
3. **Present for approval**: Show the complete `descriptions.md` to the developer for review
4. **Wait for approval**: Do not proceed until the developer approves the descriptions

**After approval**, you will use these descriptions when creating:
- Landing page hero text and feature cards (Step 5)
- README.md updates
- Package metadata (pyproject.toml)

**Note:** The developer must manually update GitHub repository settings (description and topics) using the descriptions from this file.

## Step 2: Project Structure

Create the following directory structure (depending on the project stack, or adapt as needed):

```
your-repo/
├── docs/
│   └── site/
│       ├── index.html          # Custom landing page
│       ├── getting-started.md  # Documentation pages
│       ├── usage.md
│       ├── backends.md
│       ├── ci-cd.md
│       ├── images/             # Assets for landing page (provided by developer)
│       │   ├── <repo_name>-banner-landing.png
│       │   └── <repo_name>-header-readme.png
│       └── .gitignore
├── mkdocs.yml                  # MkDocs configuration
└── .github/
    └── workflows/
        └── deploy-docs.yml     # GitHub Actions deployment
```

## Step 3: Confirm Required Images are Produced

Before proceeding, you must have the following images prepared, which will include the tagline developed in `docs/specs/descriptions.md`:

- **Landing page banner**: `{{ web_root }}/images/<repo_name>-banner-landing.png` (1024×650 pixels)
- **README header**: `{{ web_root }}/images/<repo_name>-header-readme.png` (945×100 pixels)

**If these images are missing**, the LLM should:
1. Stop and notify the developer
2. Request that the developer provide these images
3. Wait for confirmation before proceeding with documentation setup

These images are essential for the branded landing page and README presentation.

## Step 4: Create MkDocs Configuration

Create `mkdocs.yml` in the repository root:

```yaml
# MkDocs configuration
site_name: Your Project Name
site_description: Brief description of your project
site_url: https://yourusername.github.io/your-repo
repo_url: https://github.com/yourusername/your-repo
repo_name: yourusername/your-repo

theme:
  name: material
  palette:
    # Light mode
    - scheme: default
      primary: teal
      accent: cyan
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    # Dark mode
    - scheme: slate
      primary: teal
      accent: cyan
      toggle:
        icon: material/brightness-4
        name: Switch to light mode
  features:
    - navigation.instant
    - navigation.tracking
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - search.suggest
    - search.highlight
    - content.code.copy
    - content.code.annotate

# Documentation structure
docs_dir: {{ web_root }}
site_dir: site

nav:
  - Home: index.html
  - Getting Started: getting-started.md
  - Usage Guide: usage.md
  - Advanced Topics: advanced.md
  - API Reference: api.md

# Extensions
markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - pymdownx.snippets
  - pymdownx.tabbed:
      alternate_style: true
  - tables
  - toc:
      permalink: true

# Plugins
plugins:
  - search
  - git-revision-date-localized:
      enable_creation_date: true
```

**Customization:**
- Change `primary` and `accent` colors to match your brand
- Update `site_name`, `site_description`, `site_url`, `repo_url`
- Modify `nav` section to match your documentation structure

## Step 5: Create Landing Page

Create `{{ web_root }}/index.html` with this template structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Project — Tagline</title>
  <meta name="description" content="Brief description for SEO">
  <meta name="keywords" content="keyword1, keyword2, keyword3">
  <style>
    /* ── Reset & Base ─────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #e0e8f0;
      background: #0a0f14;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }
    a { color: #3ee8c8; text-decoration: none; }
    a:hover { text-decoration: underline; }
    
    /* ── Layout ───────────────────────────────────────── */
    .container { max-width: 1080px; margin: 0 auto; padding: 0 24px; }
    
    /* ── Nav ──────────────────────────────────────────── */
    nav {
      position: sticky; top: 0; z-index: 100;
      background: rgba(10, 15, 20, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(62, 232, 200, 0.12);
      padding: 14px 0;
    }
    nav .container { display: flex; align-items: center; justify-content: space-between; }
    nav .logo { font-size: 1.25rem; font-weight: 700; color: #3ee8c8; }
    nav .nav-links { display: flex; gap: 28px; }
    nav .nav-links a { color: #a0b0c0; font-size: 0.9rem; font-weight: 500; }
    nav .nav-links a:hover { color: #3ee8c8; text-decoration: none; }
    
    /* ── Hero ─────────────────────────────────────────── */
    .hero {
      text-align: center;
      padding: 64px 0 48px;
    }
    .hero h1 {
      font-size: clamp(1.8rem, 4vw, 2.8rem);
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 16px;
    }
    .hero h1 span { color: #3ee8c8; }
    .hero .subtitle {
      font-size: clamp(1rem, 2vw, 1.2rem);
      color: #8fa8be;
      max-width: 640px;
      margin: 0 auto 32px;
    }
    
    /* ── CTA Buttons ──────────────────────────────────── */
    .cta-group { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
    .btn {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: 600;
      transition: all 0.2s;
      text-decoration: none;
    }
    .btn-primary {
      background: linear-gradient(135deg, #3ee8c8 0%, #2db3a0 100%);
      color: #0a0f14;
    }
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(62, 232, 200, 0.3);
    }
    .btn-secondary {
      background: rgba(62, 232, 200, 0.1);
      color: #3ee8c8;
      border: 1px solid rgba(62, 232, 200, 0.3);
    }
    .btn-secondary:hover {
      background: rgba(62, 232, 200, 0.15);
      border-color: #3ee8c8;
    }
    
    /* ── Quick Start ──────────────────────────────────── */
    .quickstart {
      background: linear-gradient(180deg, #0a0f14 0%, #0f1419 100%);
      padding: 64px 0;
    }
    .quickstart-box {
      background: rgba(20, 30, 40, 0.6);
      border: 1px solid rgba(62, 232, 200, 0.15);
      border-radius: 12px;
      padding: 32px;
      max-width: 720px;
      margin: 0 auto;
    }
    .quickstart h3 {
      color: #3ee8c8;
      margin-bottom: 20px;
      font-size: 1.5rem;
    }
    pre {
      background: #0a0f14;
      border: 1px solid rgba(62, 232, 200, 0.2);
      border-radius: 8px;
      padding: 20px;
      overflow-x: auto;
      font-family: "SF Mono", "Fira Code", monospace;
      font-size: 0.9rem;
      line-height: 1.8;
      color: #c9d1d9;
    }
    .comment { color: #8b949e; }
    .cmd { color: #3ee8c8; font-weight: 600; }
  </style>
</head>
<body>

  <!-- Nav -->
  <nav>
    <div class="container">
      <div class="logo">Your Project</div>
      <div class="nav-links">
        <a href="#features">Features</a>
        <a href="#quickstart">Quick Start</a>
        <a href="getting-started/">Docs</a>
        <a href="https://github.com/yourusername/your-repo">GitHub</a>
      </div>
    </div>
  </nav>

  <!-- Hero -->
  <section class="hero">
    <div class="container">
      <h1><span>Your Project</span> Tagline</h1>
      <p class="subtitle">Brief description of what your project does and why it's useful.</p>
      <div class="cta-group">
        <a href="https://github.com/yourusername/your-repo" class="btn btn-primary">
          View on GitHub
        </a>
        <a href="#quickstart" class="btn btn-secondary">Get Started</a>
        <a href="getting-started/" class="btn btn-secondary">Documentation</a>
      </div>
    </div>
  </section>

  <!-- Quick Start -->
  <section class="quickstart" id="quickstart">
    <div class="container">
      <div class="quickstart-box">
        <h3>Quick Start</h3>
        <pre><span class="comment"># Install</span>
<span class="cmd">npm install</span> your-package
<span class="comment"># Or with pip</span>
<span class="cmd">pip install</span> your-package

<span class="comment"># Use it</span>
<span class="cmd">your-command</span> --help</pre>
      </div>
    </div>
  </section>

</body>
</html>
```

**Customization:**
- Theme/brand color (`#3ee8c8` teal accent)
- Update project name, tagline, description
- Add hero banner image (1024px x 650px)
- Add README header image (945px x 100px)
- Customize quick start commands
- Add features section, benefits, etc.

**Key points:**
- Links to MkDocs pages use relative paths: `getting-started/` (MkDocs generates `getting-started/index.html`)
- Nav "Docs" link points to your main documentation entry point
- CTA buttons link to GitHub and documentation

## Step 6: Create Documentation Pages

Create markdown files in `{{ web_root }}/`:

**`{{ web_root }}/getting-started.md`:**
```markdown
# Getting Started

Introduction to your project.

## Installation

### Package Manager

\`\`\`bash
npm install your-package
\`\`\`

### From Source

\`\`\`bash
git clone https://github.com/yourusername/your-repo.git
cd your-repo
npm install
\`\`\`

## Quick Start

1. Initialize your project
2. Configure settings
3. Run your first command

## Next Steps

- [Usage Guide](usage.md)
- [API Reference](api.md)
```

**`{{ web_root }}/usage.md`:**
```markdown
# Usage Guide

Detailed usage instructions.

## Commands

### `command-name`

Description of the command.

**Usage:**

\`\`\`bash
your-tool command-name [options]
\`\`\`

**Options:**

- `--option1` - Description
- `--option2` - Description

**Examples:**

\`\`\`bash
your-tool command-name --option1 value
\`\`\`
```

**Tips for markdown docs:**
- Use code blocks with language hints for syntax highlighting
- Use admonitions for notes/warnings: `!!! note` or `!!! warning`
- Cross-link between pages: `[Link text](other-page.md)`
- Use tables for structured data
- Add tabbed content with `=== "Tab 1"` syntax

## Step 7: Update .gitignore

Add to your main `.gitignore` file at the repository root:

```
# MkDocs build output (at repository root only)
/site/
```

**Note:** Use `/site/` (with leading slash) to only ignore the build output directory at the repository root, not the source files in `{{ web_root }}/`.

## Step 8: Create GitHub Actions Workflow

Create `.github/workflows/deploy-docs.yml`:

```yaml
name: Deploy MkDocs to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install mkdocs-material
          pip install mkdocs-git-revision-date-localized-plugin
      
      - name: Build MkDocs site
        run: mkdocs build --strict
      
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./site

  deploy:
    environment:
      name: github-pages
      url: ${% raw %}{{ steps.deployment.outputs.page_url }}{% endraw %}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Notes:**
- Triggers on push to `main` branch
- Can also be manually triggered via `workflow_dispatch`
- Uses `mkdocs build --strict` to fail on warnings

## Step 9: Configure GitHub Pages

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Pages**
3. Under **Source**, select **GitHub Actions**
4. Save

## Step 10: Local Development

### Install Dependencies

```bash
pip install mkdocs-material mkdocs-git-revision-date-localized-plugin
```

### Preview Locally

```bash
# From repository root
mkdocs serve
```

Visit `http://127.0.0.1:8000` to preview:
- Landing page at `/`
- Documentation pages at `/getting-started/`, `/usage/`, etc.

### Build Locally

```bash
mkdocs build
```

Output goes to `site/` directory.

## Step 11: Deploy

1. Commit all files:
   ```bash
   git add .
   git commit -m "Add documentation site"
   ```

2. Push to GitHub:
   ```bash
   git push origin main
   ```

3. GitHub Actions will automatically build and deploy

4. Visit `https://yourusername.github.io/your-repo`

## Customization Guide

### Colors and Branding

**MkDocs (mkdocs.yml):**
```yaml
theme:
  palette:
    - scheme: default
      primary: indigo      # Change to: red, pink, purple, deep-purple, indigo, blue, light-blue, cyan, teal, green, light-green, lime, yellow, amber, orange, deep-orange
      accent: indigo       # Same options as primary
```

**Landing Page (index.html):**
- Replace `#3ee8c8` (teal) with your brand color
- Update `#0a0f14` (dark background) if needed
- Modify gradient in `.btn-primary`: `linear-gradient(135deg, #yourcolor1 0%, #yourcolor2 100%)`

### Navigation

**Add more nav items (index.html):**
```html
<div class="nav-links">
  <a href="#features">Features</a>
  <a href="#quickstart">Quick Start</a>
  <a href="getting-started/">Docs</a>
  <a href="blog/">Blog</a>           <!-- Add this -->
  <a href="https://github.com/...">GitHub</a>
</div>
```

**Add more doc pages (mkdocs.yml):**
```yaml
nav:
  - Home: index.html
  - Getting Started: getting-started.md
  - Usage Guide: usage.md
  - Advanced:
      - Configuration: advanced/config.md
      - Plugins: advanced/plugins.md
  - API Reference: api.md
```

### Features Section

Add to `index.html` after Quick Start:

```html
<!-- Features -->
<section class="features" id="features">
  <div class="container">
    <h2>Features</h2>
    <div class="feature-grid">
      <div class="feature-card">
        <h3>⚡ Fast</h3>
        <p>Lightning-fast performance</p>
      </div>
      <div class="feature-card">
        <h3>🔧 Flexible</h3>
        <p>Highly configurable</p>
      </div>
      <div class="feature-card">
        <h3>📦 Simple</h3>
        <p>Easy to use</p>
      </div>
    </div>
  </div>
</section>
```

Add CSS:
```css
.features {
  padding: 64px 0;
  background: #0f1419;
}
.features h2 {
  text-align: center;
  font-size: 2rem;
  margin-bottom: 48px;
  color: #ffffff;
}
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 24px;
}
.feature-card {
  background: rgba(20, 30, 40, 0.6);
  border: 1px solid rgba(62, 232, 200, 0.15);
  border-radius: 12px;
  padding: 32px;
  text-align: center;
}
.feature-card h3 {
  font-size: 1.5rem;
  margin-bottom: 12px;
  color: #3ee8c8;
}
.feature-card p {
  color: #8fa8be;
}
```

### Hero Banner Image

Add image to `{{ web_root }}/images/banner.png`, then in `index.html`:

```html
<section class="hero">
  <div class="container">
    <img src="images/banner.png" alt="Project Banner" class="hero-banner">
    <h1><span>Your Project</span> Tagline</h1>
    <!-- ... -->
  </div>
</section>
```

Add CSS:
```css
.hero-banner {
  width: 100%;
  max-width: 820px;
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);
  margin-bottom: 40px;
}
```

## Advanced Features

### Search

MkDocs Material includes built-in search. No configuration needed.

### Dark/Light Mode Toggle

Already configured in `mkdocs.yml` theme palette. Users can toggle in the header.

### Code Annotations

Use in markdown:
```python
def hello():
    print("Hello")  # (1)!
```

1. This is an annotation

### Admonitions

```markdown
!!! note
    This is a note

!!! warning
    This is a warning

!!! tip
    This is a tip
```

### Tabbed Content

```markdown
=== "Tab 1"
    Content for tab 1

=== "Tab 2"
    Content for tab 2
```

### Version Selector

Add to `mkdocs.yml`:
```yaml
extra:
  version:
    provider: mike
```

Requires `mike` for versioning: `pip install mike`

## Troubleshooting

### MkDocs Build Fails

**Error: `Doc file 'page.md' contains a link '../file.md', but the target is not found`**

**Solution:** Ensure all links point to files within `{{ web_root }}/`. Use absolute GitHub URLs for files outside docs:
```markdown
[README](https://github.com/yourusername/your-repo)
```

### GitHub Pages Not Updating

1. Check GitHub Actions workflow ran successfully
2. Verify GitHub Pages source is set to "GitHub Actions"
3. Clear browser cache
4. Check `site_url` in `mkdocs.yml` matches your GitHub Pages URL

### Styles Not Loading

Ensure `index.html` styles are in `<style>` tags in `<head>`, not external CSS files (MkDocs won't process them).

### Navigation Not Working

- Landing page nav links to docs: use `getting-started/` (trailing slash)
- MkDocs nav between pages: use `page.md` or `[text](page.md)`
- External links: use full URLs `https://...`

## Example Repositories

Reference implementations:
- **Pyve**: https://github.com/pointmatic/pyve
  - Landing: https://pointmatic.github.io/pyve
  - Docs: https://pointmatic.github.io/pyve/getting-started/

## Summary

**What you get:**
- ✅ Beautiful custom landing page with full design control
- ✅ Professional documentation with Material theme
- ✅ Search, dark mode, navigation, mobile-responsive
- ✅ Markdown-based (easy to maintain)
- ✅ Single GitHub Actions deployment
- ✅ Free hosting on GitHub Pages

**File checklist:**
- [ ] `mkdocs.yml` - MkDocs configuration
- [ ] `{{ web_root }}/index.html` - Custom landing page
- [ ] `{{ web_root }}/*.md` - Documentation pages
- [ ] `{{ web_root }}/.gitignore` - Ignore build output
- [ ] `.github/workflows/deploy-docs.yml` - Deployment workflow
- [ ] GitHub Pages configured to use GitHub Actions

**Next steps:**
1. Customize colors and branding
2. Write your documentation content
3. Add features section, screenshots, examples
4. Test locally with `mkdocs serve`
5. Push and deploy

---

**Questions or issues?** Open an issue on the Pyve repository or consult:
- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)

{% include "modes/_header-sequence.md" %}
