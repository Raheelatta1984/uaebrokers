# Publishing a product update

ReconIQ's public **What's New** tab is available at `/#whats-new`, even before any
files are loaded. Switching tabs does not reset reconciliation work. Notes are
included in the app itself; there is no external release service or database.

## One source of truth

[`reconiq/releases.json`](../reconiq/releases.json) is the version-controlled
changelog. Its **first entry defines the current application version**. That same
version is used by the navigation badge, What's New screen, `/api/releases`,
`/api/health`, Python's `reconiq.__version__` and FastAPI's OpenAPI metadata.
Do not maintain a second version number elsewhere.

## Add a release

1. Prepend a new entry to `reconiq/releases.json`; keep all published entries.
2. Choose a three-part semantic version with no `v` prefix:
   - **Major** (`1.0.0`): breaking changes.
   - **Minor** (`0.3.0`): new features or improvements.
   - **Patch** (`0.2.1`): fixes or small refinements.
3. Set the publication date in `YYYY-MM-DD` format and write a short title,
   summary and at least one change. Use plain text, not HTML or Markdown.
4. Use `added`, `improved` or `fixed` for each change's type. Explain the user
   benefit, not just the internal implementation. Only describe shipped work.
5. Run the tests and include the changelog edit in the feature's pull request:

   ```bash
   ./.venv/bin/python -m pytest tests -q
   node --check app/static/app.js   # optional JavaScript syntax check
   ```

Example entry (place it before older releases):

```json
{
  "version": "0.2.1",
  "date": "2026-10-27",
  "title": "A more reliable export",
  "summary": "A short explanation of the shipped update.",
  "changes": [
    {
      "type": "fixed",
      "title": "Describe the resolved issue",
      "description": "Explain what users can now do successfully."
    }
  ]
}
```

Versions must be unique and strictly descending numerically. Dates must be valid
and newest first (multiple releases can share a date). The changelog validator
and tests check these rules, required fields and supported change types. CI runs
the full suite on pull requests and on `main`.

Deploy or restart the app after merging: release notes are loaded from the checked-in
file at process startup. Merging a pull request alone does not update an already
running deployment.
