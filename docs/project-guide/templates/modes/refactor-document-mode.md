Update existing documentation files because of new features, improvements, or to migrate legacy formats into the v2.x structure. Covers README, brand descriptions, the landing page, and MkDocs configuration.

{% include "modes/_header-cycle.md" %}

## Targets

The following documents may need updating (in order):

1. `README.md` — project README at the repository root
2. `{{ spec_artifacts_path }}/brand-descriptions.md` — artifact template: `templates/artifacts/brand-descriptions.md`
3. `{{ web_root }}/index.html` — project landing page
4. MkDocs configuration (`mkdocs.yml`) and documentation pages (`{{ web_root }}/*.md`)

Skip any document that does not exist. If a document already reflects the current state of the project, confirm with the developer and skip.

**Note:** If the project has a legacy `{{ spec_artifacts_path }}/descriptions.md`, it should be migrated to `brand-descriptions.md` using the artifact template format.

## Cycle Steps (for each document)

### Step 1: Understand the Change

Ask the developer what needs updating and why. This could be:
- **New features or improvements** — documentation needs to reflect new capabilities, updated descriptions, or revised messaging
- **Legacy migration** — the document predates the v2.x format and needs restructuring (e.g., `descriptions.md` → `brand-descriptions.md`)

### Step 2: Backup

Copy the existing document to a backup before making changes:

```
README.md → README_old.md
docs/specs/brand-descriptions.md → docs/specs/brand-descriptions_old.md
docs/site/index.html → docs/site/index_old.html
```

For MkDocs configuration files, no backup is needed — they are updated in place.

This protects against uncommitted work being overwritten.

### Step 3: Read and Extract

Read the old document as the primary source of information. For documents with artifact templates, read the corresponding template to understand the target structure.

**For `README.md`:**
- Extract project description, installation instructions, usage examples, badges
- Update to reflect current features and version

**For `brand-descriptions.md`:**
- Map to artifact template sections: Name, Tagline, Long Tagline, One-liner, Friendly Brief Description, Two-clause Technical Description, Benefits, Technical Description, Keywords, Feature Cards, Usage Notes

**For `index.html`:**
- Extract hero text, feature cards, quick start content

**For MkDocs:**
- Review `mkdocs.yml` configuration and documentation pages for consistency

Note what needs to change based on the developer's instructions from Step 1.

### Step 4: Fill Gaps

If any sections required by the target format are missing or need new content:

1. Note which sections are missing or outdated
2. Ask the developer for the missing information
3. Wait for the developer's response before proceeding

Do not invent content — only use information from the old document or the developer.

### Step 5: Generate Updated Document

Write the updated document using the target format, incorporating:
- Existing content that is still accurate
- Updates based on the developer's instructions
- Any new information provided by the developer

### Step 6: Legacy Content

If any information from the old document does not fit into the target format sections, append it to the end:

```markdown
---

## Legacy Content

<content that didn't map to any target section>
```

For HTML files, add legacy content as an HTML comment at the bottom.

If all content mapped cleanly, omit this section.

### Step 7: Present for Approval

Present the completed document to the developer. Show:
- What changed and why
- Which sections were preserved, updated, or added
- Whether a Legacy Content section was added
- For legacy migrations: note any filename changes (e.g., `descriptions.md` → `brand-descriptions.md`)

Iterate as needed until the developer approves. Then proceed to the next document in the targets list.

### Step 8: Cleanup

After the developer approves, backup files (`_old.md`, `_old.html`) can be deleted at the developer's discretion. Do not delete them automatically.
