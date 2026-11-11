# Live-server tests

These five scripts are **not** part of `pytest -q`. They exercise the real
running application rather than an in-process test client, so they need the
server up first:

```bash
uvicorn app.main:app
```

Then, in another terminal:

```bash
# 1. Full HTTP walkthrough of every API workflow (no browser needed)
python tests/browser/api_e2e.py

# 2. Real Chromium walkthrough of the UI (needs: pip install playwright && playwright install chromium)
python tests/browser/ui_walkthrough.py

# 3. Shared-with-me page against seeded data (run `python seed.py` first)
python tests/browser/shared_page_check.py

# 4. Folder upload, multi-select, clipboard and folder sharing, end to end
python tests/browser/folder_features_check.py

# 5. The /admin panel: sign-in, plans, and assigning one to a user
python tests/browser/admin_panel_check.py
```

All four take the server origin as their first argument.

`ui_walkthrough.py` and `folder_features_check.py` register a fresh account on
every run, so they are safe to re-run without resetting the database. Both write
screenshots to `tests/browser/shots/`, and both take an alternative origin as
their first argument:

```bash
python tests/browser/folder_features_check.py http://127.0.0.1:8011
```

`folder_features_check.py` builds a real folder tree on disk, uploads it through
the browser's own folder picker, and checks that the nesting, the multi-select
clipboard and folder sharing all behave — including browsing a public folder link
from a separate anonymous browser context.
