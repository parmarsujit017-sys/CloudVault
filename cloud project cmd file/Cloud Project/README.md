# Cloud File Management System (Cloud)

A working cloud file manager: the original static HTML/CSS/JS frontend, now backed by a
Python **FastAPI** REST API, a relational database, and real file storage on disk.

Authentication, nested folders, uploads, downloads, sharing, trash, storage accounting,
activity logging and settings are all real — there is no mock data anywhere in the app.

---

## Contents

```text
Cloud Project/
├── index.html            entry point - redirects to the drive or sign in
├── login.html            sign in
├── register.html         create account
├── reset.html            reset password
├── dashboard.html        overview: stats, recent files, recent activity
├── files.html            the file manager (folders, grid/list, sort, filter)
├── recent.html           recently changed files, grouped by day
├── starred.html          files you marked important
├── shared.html           Shared With Me
├── trash.html            restore / delete permanently / empty
├── activity.html         filterable activity timeline
├── storage.html          usage ring, breakdown by type, largest files
├── settings.html         appearance, notifications, language, security
├── share.html            public share-link landing page (no sign-in)
├── admin.html            the admin panel, served at /admin
├── assets/
│   ├── css/app.css       the whole design system + every component
│   ├── img/              profile.png, p2.jpg
│   └── js/
│       ├── api.js        API client (fetch wrapper + endpoint map)
│       ├── ui.js         toasts, dialogs, skeletons, empty states, formatters
│       ├── menu.js       floating, keyboard-accessible action menus
│       ├── shell.js      sidebar + header, theme, search, notifications, profile
│       ├── files.js      file/folder cards, rows, action menus, details drawer
│       ├── upload.js     upload panel + drag-and-drop (folders included)
│       ├── select.js     multi-select, and the cut/copy/paste clipboard
│       ├── sharing.js    share modal (files and folders)
│       └── pages/        one controller per screen
├── legacy/               pre-redesign files, kept for reference only
└── backend/
    ├── app/
    │   ├── main.py         FastAPI app, error envelope, CORS, static frontend
    │   ├── config.py       settings from .env
    │   ├── database.py     engine / session / Base / init_db
    │   ├── models/         the 8 specification tables, plus 3 additive ones
    │   ├── schemas/        Pydantic request + response models
    │   ├── routers/        auth, users, folders, files, trash, shares, storage,
    │   │                   activity, settings, dashboard, search, plans, admin
    │   ├── services/       storage backend, file/folder/share/plan/activity logic
    │   ├── auth/           password hashing, JWT, route dependencies
    │   └── utils/          filename sanitising, path-traversal guards, size helpers
    ├── uploads/            real file storage (git-ignored)
    ├── tests/              156 pytest tests + live-server scripts
    ├── seed.py             optional demo data (kept out of the app itself)
    ├── requirements.txt
    └── .env.example
```

---

## Installation

From the project root:

```bash
cd backend
python -m venv venv
```

Activate it.

Windows:

```bash
venv\Scripts\activate
```

macOS / Linux:

```bash
source venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

Then open `.env` and set `SECRET_KEY` to a long random value. Anything else can stay as-is
for local development.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Run

```bash
uvicorn app.main:app --reload
```

That single command serves **both** the API and the frontend:

| URL | What |
|---|---|
| http://127.0.0.1:8000/ | the app (start here) |
| http://127.0.0.1:8000/login.html | sign in directly |
| http://127.0.0.1:8000/docs | interactive Swagger API docs |
| http://127.0.0.1:8000/redoc | ReDoc API docs |
| http://127.0.0.1:8000/admin | the administration panel |
| http://127.0.0.1:8000/api/health | health check |

The database file (`backend/cloud_storage.db`) and every table are created automatically
on first start, along with the plan catalogue and the administrator account.

Sign in to `/admin` with the credentials from `.env` (`vandit77` / `123456@Vk` by
default — **change them**). Accounts you register through the normal sign-up are ordinary
users on the 25 GB Free plan; an administrator moves them to another plan from the panel.
See [Plans and administration](#plans-and-administration).

### Running the frontend separately (optional)

The pages are plain static files, so a separate static server also works — for example
VS Code Live Server on port 5500. `api.js` detects ports `5500`/`5501` and `file://` and
automatically points at `http://127.0.0.1:8000`. Those origins are already in
`CORS_ORIGINS` in `.env.example`; add any other origin you use.

To force a specific backend, set it before `api.js` loads:

```html
<script>window.Cloud_API_BASE = "http://127.0.0.1:8000";</script>
```

Serving the frontend from FastAPI is still the simplest option, because there is no CORS
involved at all.

### Demo data (optional)

```bash
python seed.py --reset
```

Creates `demo / Demo@1234` (admin) and `rahul / Rahul@1234`, a nested folder tree, some
files, two shares, and puts `rahul` on a paid plan so the admin panel has something to
show. This is a **separate script** — the application never seeds demo content itself.

The plan catalogue and the `/admin` administrator are *not* demo data: the app creates
those on startup, because without them there is no way in and nothing to assign.

---

## Database

Eight tables exactly as specified, plus three additive tables (`folder_sharing`, `plans`
and `subscriptions`) documented below.

| Table | Purpose | Key columns |
|---|---|---|
| `users` | accounts | id, fullname, username, email, password, role, profile_image, storage_used, storage_limit, status, created_at |
| `folders` | nested folders | id, user_id, folder_name, parent_folder, created_at |
| `files` | file metadata | id, user_id, folder_id, file_name, original_name, file_type, file_size, file_path, uploaded_at, updated_at |
| `trash` | soft deletes | id, file_id, user_id, deleted_at, auto_delete |
| `file_sharing` | file shares + links | id, file_id, shared_by, shared_to, share_link, password, expiry_date, created_at |
| `folder_sharing` | folder shares + links | id, folder_id, shared_by, shared_to, share_link, password, expiry_date, created_at |
| `plans` | storage packages | id, code, name, description, storage_mb, price_monthly, price_yearly, is_free, is_active, features, sort_order, created_at, updated_at |
| `subscriptions` | who is on which plan | id, user_id, plan_id, billing_cycle, status, starts_at, ends_at, assigned_by, note, created_at |
| `storage` | per-user quota | id, user_id, total_storage, used_storage, available_storage, updated_at |
| `activity_logs` | audit trail | id, user_id, activity, file_name, ip_address, activity_time |
| `settings` | preferences | id, user_id, theme, notifications, language, updated_at |

Relationships:

```text
folders.user_id      -> users.id
folders.parent_folder-> folders.id      (self-referential, nesting)
files.user_id        -> users.id
files.folder_id      -> folders.id
trash.file_id        -> files.id
trash.user_id        -> users.id
file_sharing.file_id -> files.id
file_sharing.shared_by -> users.id
file_sharing.shared_to -> users.id      (NULL for a public link)
folder_sharing.folder_id -> folders.id
folder_sharing.shared_by -> users.id
folder_sharing.shared_to -> users.id    (NULL for a public link)
subscriptions.user_id    -> users.id
subscriptions.plan_id    -> plans.id
subscriptions.assigned_by-> users.id    (the admin who granted it; NULL if automatic)
storage.user_id      -> users.id        (1:1)
activity_logs.user_id-> users.id
settings.user_id     -> users.id        (1:1)
```

### Units, and four documented additions

Five implementation decisions worth stating explicitly, since they are not spelled out
in the specification:

1. **Storage is measured in MB**, as specified, and stored as a float so files smaller
   than 1 MB are still counted accurately. `files.file_size` is stored in **bytes**,
   which is the only lossless unit for an individual file; the MB figures in `users` and
   `storage` are derived from the byte totals.
2. **`files.is_deleted`** — a boolean flag marking a file as trashed. The `trash` table
   holds the deletion timestamps exactly as specified; this column is what lets a single
   indexed query separate live files from trashed ones.
3. **`files.is_starred`** — backs the "Starred" item that already existed in the sidebar.
4. **`folder_sharing`** — a table mirroring `file_sharing` column for column, so a whole
   folder can be shared the same way a file can. It is a separate table rather than a
   nullable `folder_id` on `file_sharing` because that would mean making the specified
   `file_id` column nullable, which SQLite cannot do without rebuilding the table.
   Access is evaluated live against the folder tree, so files added to a shared folder
   later are covered without re-sharing, and files moved out of it stop being reachable.

5. **`plans` and `subscriptions`** — the storage packages an administrator can assign,
   and the record of who is on which. They are additive because the specification fixes a
   single quota per user; these tables are what decides that quota. The link is
   deliberately narrow: assigning a plan sets `users.storage_limit`, and every quota check
   in the application keeps reading that one column exactly as it did before.

The extra columns and the extra tables are additive. No specified table or column was
removed or renamed.

### Migrations

Tables are created automatically at startup via `Base.metadata.create_all`, which is the
right fit for SQLite development and never drops or rewrites existing data. Alembic is not
configured; if you move to Postgres or start changing columns on a database that holds real
data, add it then — the models in `app/models/` are the source of truth for the schema.

---

## API

All endpoints return JSON. Errors always use the same envelope, never a stack trace:

```json
{ "success": false, "message": "Storage limit exceeded" }
```

Status codes in use: `200`, `201`, `400`, `401`, `403`, `404`, `409`, `410`, `422`, `500`.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | – | create an account, returns a JWT |
| POST | `/api/auth/login` | – | log in with username **or** email |
| POST | `/api/auth/logout` | ✓ | log out (records the event) |
| GET | `/api/auth/me` | ✓ | current user |
| POST | `/api/auth/reset-password` | – | dev reset: username + email must match |
| GET/PUT | `/api/users/me` | ✓ | read / update profile |
| POST/GET | `/api/users/me/avatar` | ✓ | upload / fetch profile photo |
| PUT | `/api/users/me/password` | ✓ | change password |
| GET | `/api/users/search` | ✓ | find a share recipient (id/name/username only) |
| POST/GET | `/api/folders` | ✓ | create / list folders |
| POST | `/api/folders/tree` | ✓ | create a whole directory tree in one call |
| POST | `/api/folders/batch` | ✓ | move / copy / delete many folders |
| GET | `/api/folders/{id}` | ✓ | open a folder (children + files + breadcrumb) |
| PUT/DELETE | `/api/folders/{id}` | ✓ | rename or move / delete |
| POST | `/api/folders/{id}/copy` | ✓ | deep copy a folder and everything inside it |
| GET | `/api/folders/{id}/download` | ✓ | download a folder as a `.zip` |
| POST | `/api/files/upload` | ✓ | upload one or many files (`?folder_id=`) |
| POST | `/api/files/batch` | ✓ | move / copy / trash / star many files |
| GET | `/api/files` | ✓ | list files (`folder_id`, `starred`, `recent`) |
| GET | `/api/files/{id}` | ✓ | metadata |
| GET | `/api/files/{id}/download` | ✓ | download (`?inline=true` to preview) |
| PUT | `/api/files/{id}/rename\|move\|star` | ✓ | file actions |
| POST | `/api/files/{id}/copy` | ✓ | duplicate a file into a folder |
| DELETE | `/api/files/{id}` | ✓ | move to Trash |
| GET | `/api/trash` | ✓ | list trashed files |
| POST | `/api/trash/{id}/restore` | ✓ | restore |
| DELETE | `/api/trash/{id}` | ✓ | permanently delete |
| DELETE | `/api/trash` | ✓ | empty Trash |
| POST | `/api/shares` | ✓ | share a file with a user, or create a public link |
| POST | `/api/shares/folder` | ✓ | share a whole folder the same two ways |
| GET | `/api/shares/received` | ✓ | Shared with me, files and folders (`?q=` search) |
| GET | `/api/shares/sent` | ✓ | shares you created, of either kind |
| DELETE | `/api/shares/{id}` | ✓ | revoke a file share |
| DELETE | `/api/shares/folder/{id}` | ✓ | revoke a folder share |
| GET | `/api/share/{token}` | – | public link info; says which kind it is |
| POST | `/api/share/{token}/verify` | – | check a link password |
| GET | `/api/share/{token}/list` | – | browse inside a shared folder (`?path=`) |
| GET | `/api/share/{token}/download` | – | public download (`?password=`, `?file_id=`) |
| GET | `/api/share/{token}/download-all` | – | shared folder as a `.zip` (`?path=`) |
| GET | `/api/plans` | ✓ | the plan catalogue (active plans only) |
| GET | `/api/plans/me` | ✓ | the plan this account is on, and its usage |
| GET | `/api/plans/me/history` | ✓ | every plan this account has been on |
| GET | `/api/admin/stats` | admin | live counters across the installation |
| GET | `/api/admin/users` | admin | every account (`q`, `plan`, `status`, `page`) |
| GET | `/api/admin/users/{id}` | admin | one account in full, with plan history |
| PUT | `/api/admin/users/{id}` | admin | rename, enable/disable, promote, override quota |
| DELETE | `/api/admin/users/{id}` | admin | delete the account and all of its data |
| POST | `/api/admin/users/{id}/subscription` | admin | put the user on a plan |
| DELETE | `/api/admin/users/{id}/subscription` | admin | move them back to the free plan |
| GET/POST | `/api/admin/plans` | admin | list (retired ones included) / create |
| PUT/DELETE | `/api/admin/plans/{id}` | admin | edit / delete a plan |
| GET | `/api/storage` | ✓ | total / used / available MB |
| GET | `/api/activity` | ✓ | your own activity |
| GET | `/api/activity/all` | admin | system-wide activity |
| GET/PUT | `/api/settings` | ✓ | theme, notifications, language |
| GET | `/api/dashboard` | ✓ | live counters |
| GET | `/api/search` | ✓ | files, folders and shared files |

Full request/response schemas are at `/docs`.

---

## File and Folder Sharing

Files and folders can be shared in two ways: **directly with other registered users**, or
via **public links** with optional passwords and expiry dates.

### Direct User Shares with Permission Levels

When sharing with another user, you can grant one of two permission levels:

| Permission | Can Read | Can Edit | Can Delete |
|---|---|---|---|
| **Viewer** (default) | ✓ | ✗ | ✗ |
| **Editor** | ✓ | ✓ | ✗ |

- **Viewer**: Can download and view the file or folder contents, but cannot make changes.
- **Editor**: Can download, view, and edit/update files within the shared folder. Cannot
  delete files or change permissions.

### Public Links

Public share links work for both files and folders and allow anonymous access with these
features:

- **Password protection**: Optionally require a password to access
- **Expiry dates**: Links automatically expire on a specified date
- **Live folder browsing**: Recipients can browse inside shared folders without
  downloading everything
- **No re-sharing needed**: Files added to a shared folder later are automatically
  accessible; files moved out become inaccessible

### How Sharing Works

When you share a folder with a user, they can see all files in it plus all subfolders.
Access is evaluated live against the current folder tree, not a static snapshot:

- Files and folders inside a shared folder are automatically accessible
- Moving a file into a shared folder makes it accessible to recipients
- Moving a file out of a shared folder stops it being accessible to recipients
- The "Shared" badge on files and folders indicates they are shared with others

### API Details

Sharing is handled by these endpoints:

- `POST /api/shares` — share a file with a user or create a public link
- `POST /api/shares/folder` — share a folder with a user or create a public link
- `GET /api/shares/received` — list files and folders shared with you
- `GET /api/shares/sent` — list shares you created
- `DELETE /api/shares/{id}` — revoke a file share
- `DELETE /api/shares/folder/{id}` — revoke a folder share

---

## Plans and administration

Storage is not a fixed number per account any more: it comes from a **plan**, and an
administrator decides who is on which. Nothing in the app bills anybody — prices are
recorded so the panel can state them, and an administrator grants the plan.

### The catalogue

Four plans are created on an empty database, and can be edited or replaced from the
panel:

| Plan | Storage | Monthly | Yearly |
|---|---|---|---|
| **Free** | 25 GB | — | — |
| **Personal** | 200 GB | ₹149 | ₹1,490 |
| **Professional** | 2 TB | ₹499 | ₹4,990 |
| **Business** | 5 TB | ₹1,299 | ₹12,990 |

The yearly price is ten months' worth, so a year costs two months less than paying
monthly. Currency is display-only and set by `CURRENCY_SYMBOL`.

Exactly one plan carries the `is_free` flag. That is the plan new accounts land on, and
the one an expired subscription falls back to; the panel refuses to delete it, retire it,
or leave the flag unset.

### How a plan becomes a quota

Assigning a plan sets `users.storage_limit` to the plan's allowance, and that is the only
connection. Every quota check, the storage ring, the dashboard and the upload guard keep
reading `storage_limit` exactly as they did before plans existed, so nothing else had to
learn about them.

Three consequences fall out of that, all of them handled:

- **Editing a plan's allowance** re-applies it to everybody currently on that plan, so
  the panel never advertises a limit the subscribers are not actually getting.
- **An expired paid plan** drops back to Free the next time the account is looked at.
  Nothing is deleted — the account simply cannot upload more until it is back under the
  free allowance.
- **Accounts created before plans existed** are put on the free plan once, at startup.
  Without that they would stay uncounted until their owner next signed in, and every
  figure in the panel would disagree with the user list.

Assignments are never overwritten. A new one supersedes the last, which is kept with
status `replaced`, so both the panel and the user can see what changed and when.

### The panel

Served at **`/admin`**, with its own sign-in. Signing in with an ordinary account is
refused with a plain message rather than a half-working screen — though the real boundary
is server-side: every route under `/api/admin` requires the admin role, so a normal
account gets a flat `403` whatever the browser does.

- **Overview** — users, active accounts, storage used against storage allocated, paid
  versus free subscribers, monthly run rate (a yearly plan counts as a twelfth per
  month), and subscribers broken down by plan. Every figure is computed live.
- **Users** — search by name, username or email, filter by plan or status. Each row
  shows the plan, billing cycle, renewal date and a storage bar. From here you can assign
  a plan, revert to free, enable or disable an account, grant or remove admin access,
  open a full detail view with plan history, or delete the account and its data.
- **Plans** — create, edit, retire and delete packages. The assign dialog previews what
  the change does before you commit it: the new allowance, the old one, and the price for
  the chosen cycle.

Assigning takes a billing cycle, a number of periods, and an optional "this grant
expires" toggle — clearing it grants the plan with no end date, which is what a comped or
internal account wants.

Some things the panel deliberately refuses: disabling your own account, removing your own
admin access, deleting yourself, removing the last administrator, and deleting a plan
somebody is on (retire it instead). Deleting a user asks you to type their username
first, because it takes their files and stored bytes with it.

### The administrator account

Created from configuration on first startup, so `/admin` is reachable on a fresh
database:

```env
ADMIN_USERNAME=vandit77
ADMIN_PASSWORD=123456@Vk
ADMIN_EMAIL=vandit77@example.com
```

**Change these before deploying anywhere real.** The account is keyed on the username and
an existing one is never silently re-passworded, so editing `ADMIN_PASSWORD` in `.env`
does not reset a live administrator — change that from the app.

Registration never grants administration, not even to the first account. That rule used
to exist and was removed when this panel was added: with a configured administrator, the
first person to sign up on a fresh deployment getting admin is a way in, not a
convenience.

### What the user sees

Their Storage page leads with a **Your plan** panel — the plan name, its allowance, the
price and cycle, the renewal date, and a usage bar — followed by the catalogue with their
current plan marked. The sidebar storage widget is labelled with the plan name rather
than the word "Storage", so the number under it is never a quota without an explanation.
Users cannot change their own plan; the page points them at the administrator.

---

## File storage

Uploads are written to disk and only their metadata goes in the database:

```text
backend/uploads/
    users/
        1/
            files/8f42d91a9b31...4e9f.pdf
            avatar/....png
        2/
            files/...
```

- The stored name is always a fresh UUID plus the original extension. The user's filename
  is never used as a path.
- `backend/uploads/` is **not** mounted as a static directory. Every byte is served through
  `/api/files/{id}/download` or `/api/share/{token}/download`, which check authorisation first.
- All storage access goes through the `StorageBackend` interface in
  `app/services/storage_backend.py`. Swapping in S3, R2 or Cloudinary means implementing
  that one class — the routers do not touch the filesystem.

Limits: `MAX_FILE_SIZE_MB` per file (default 100 MB), plus the per-user quota
(`DEFAULT_STORAGE_LIMIT_MB`, default 15360 MB = 15 GB). Executable extensions are refused.

---

## Security

- Passwords are bcrypt hashes. Plaintext is never stored, and the hash is never returned.
- JWT bearer tokens, signed with `SECRET_KEY`, expiring after `JWT_EXPIRE_MINUTES`.
- Disabled accounts (`status = 'disabled'`) cannot log in and their existing tokens stop working.
- **Every** file and folder id from the client is checked against the token's user. Ownership
  is never taken from the request body — passing someone else's id returns `403`.
- Share tokens are 48 hex characters from `secrets.token_hex`, so links are unguessable.
  Link passwords are bcrypt hashed; expired links return `410`.
- Filenames are sanitised to a basename and rewritten as UUIDs; resolved paths are checked
  to be inside the upload root before any read or write.
- All queries go through SQLAlchemy with bound parameters — no string-concatenated SQL.
- CORS origins, secret key and limits come from `.env`, which is git-ignored.
- The static file handler refuses to serve anything under `backend/`, so `.env`, the
  database and the uploads directory are unreachable over HTTP.
- Every route under `/api/admin` requires the admin role. The sign-in gate on `/admin` is
  a courtesy so an ordinary account is told why rather than shown a broken screen; the
  boundary itself is server-side, and returns a flat `403`.
- Registration never grants administration. The administrator comes from configuration,
  so signing up first is not a route to it.

---

## Frontend

Plain **HTML5 + CSS3 + vanilla JavaScript + Bootstrap 5**. No React, Vue, Angular,
Tailwind, TypeScript or jQuery — and no build step. Bootstrap supplies the grid,
dropdowns, modals, offcanvas and utilities; `assets/css/app.css` supplies the
product identity so it never reads as a stock Bootstrap template. Icons are
Bootstrap Icons.

### Design system

Everything is driven by CSS custom properties on `:root`, with a `[data-theme="dark"]`
block that redefines the same tokens — one stylesheet, two themes.

| Group | Tokens |
|---|---|
| Brand | `--primary #2563eb`, `--primary-hover`, `--primary-soft` |
| Surfaces | `--bg #f7f8fb`, `--surface`, `--surface-2`, `--surface-hover` |
| Text | `--text-primary #0f172a`, `--text-secondary`, `--text-muted` |
| Lines | `--border`, `--border-strong` |
| Status | `--success`, `--warning`, `--danger`, `--info` |
| File types | `--type-pdf`, `--type-word`, `--type-excel`, `--type-image`, … |
| Layout | `--sidebar-width 260px`, `--header-height 64px` |
| Radii | `--radius-sm 8px`, `--radius-md 12px`, `--radius-lg 16px` |
| Spacing | `--sp-1 4px` … `--sp-8 40px` (a strict 4/8 scale) |
| Elevation | `--shadow-xs` … `--shadow-lg`, deliberately restrained |

Typography: page titles 26px, section titles 17px, body 14px, metadata 11.5–12.5px.
Motion is 150–200ms and honours `prefers-reduced-motion`.

### Shell

`shell.js` renders the sidebar and header into every signed-in page, so that markup
is written once rather than copied into eleven files. It owns the concerns that span
pages: the auth guard, theme, global search, notifications, the New menu, the profile
modal and the storage widget.

Sidebar: brand, New button, then **Main** (Dashboard, My Files, Shared With Me, Recent,
Starred), **Library** (Storage, Trash) and **System** (Activity, Settings), then the live
storage meter and the user block.

### Components

Defined once and reused everywhere: `file-card`, `folder-card`, file table rows,
the floating action menu, the details drawer, toasts, confirm and prompt dialogs,
empty states, skeleton loaders, breadcrumbs, badges, the type chip, stat cards and
the upload panel.

The type chip is the single visual system for file types — the same colour and glyph
appear on cards, table rows, search results, the upload panel, the share modal and
the public share page.

### Screens

- **Dashboard** — greeting, four compact stat cards, a recent-files table and an
  activity timeline. Every figure comes from `GET /api/dashboard`.
- **My Files** — breadcrumbs into nested folders, folder and file grids, a working
  **grid/list toggle** (persisted in `localStorage`), sort (name/size/modified, both
  directions) and an in-folder filter. Sortable column headers in list view.
  Multi-select with select-all, and cut / copy / paste across folders.
- **Recent** — grouped Today / Yesterday / Earlier this week / Earlier this month / Older.
- **Starred**, **Shared With Me** (grid + list, backend search, expiry badges),
  **Trash** (restore, delete permanently, empty — each behind a confirmation),
  **Activity** (day-grouped timeline with seven filter chips),
  **Storage** (your plan, usage ring, breakdown by file type, largest files, catalogue),
  **Settings** (theme, notifications, language, password, account, storage).
- **Login / Register / Reset** — split layout with a brand panel on desktop, inline
  field validation, a password-strength meter and show/hide toggles.
- **share.html** — the public landing page, including the password gate and clean
  messages for expired or revoked links. A folder link renders a browsable listing
  instead of a single download button.
- **admin.html** (`/admin`) — the administration panel: overview, users and plans. It has
  its own sign-in and its own shell, because administering the system is a different job
  from using the drive.

### Uploads

A dockable panel in the bottom-right rather than a blocking modal: per-file progress,
size, success and failure states, cancel, collapse and close — and the rest of the app
stays usable while it runs. Dragging files anywhere over the window shows a drop
overlay. Files upload one at a time so one rejected file never cancels the batch.

**Folders keep their structure.** Whether a folder arrives through *New → Upload Folder*
or is dropped onto the page, it is uploaded whole — every subfolder, however deeply
nested, and every file in the right place:

1. The browser reads the folder first. A picked folder arrives with
   `webkitRelativePath` already filled in; a dropped one is walked recursively through
   `webkitGetAsEntry()`, which is the only way to see inside a dropped directory. Both
   produce the same list of *(file, folder path)* pairs, and empty folders are noted so
   they still exist afterwards.
2. Every distinct directory goes to `POST /api/folders/tree` in a **single** request,
   which creates the whole tree and returns a path → id map. Directories that already
   exist are reused, so re-uploading a folder merges into it instead of producing
   `Photos (2)`.
3. Each file is then uploaded straight into its own folder's id.

The queue shows the folder path under each file, which is how you can see at a glance
that the nesting was understood. Path segments are sanitised server-side one at a time
and `..` is discarded, so a crafted `webkitRelativePath` cannot escape your own tree —
the response echoes the original paths back so the uploader never has to guess how a
name was cleaned.

### Selecting, and cut / copy / paste

Hovering a card reveals a checkbox; the toolbar has **Select all** (or `Ctrl`/`Cmd`+`A`).
Click extends an existing selection instead of opening the item, `Shift`-click takes a
range, and `Esc` clears. Once anything is selected a bar appears with Download, Share,
Cut, Copy, Move to…, Star and Delete.

Cut and copy (`Ctrl`+`X` / `Ctrl`+`C`) put the selection on a clipboard held in
`localStorage`, so it survives navigating into the folder you meant to paste into —
which is the only way anyone actually uses it. Paste (`Ctrl`+`V`, or the toolbar button
that appears while the clipboard is loaded, or *Paste into this folder* on a folder's
menu) sends the whole selection through the batch endpoints:

- a **cut** becomes a move, and the clipboard is spent once it lands;
- a **copy** becomes a real duplicate — folders are recreated subfolder by subfolder and
  every file's bytes are copied, so the copy is independent of the original — and the
  clipboard is kept, so the same thing can be pasted into several folders.

Name clashes are resolved rather than refused, and the suffix says which happened: a
copy becomes `Reports (copy)`, while a *move* that collides becomes `Reports (2)`,
because calling a moved folder a copy would misdescribe what just happened. Failures are
reported per item — one file that runs the account out of quota does not roll back the
rest, because each item in a batch runs inside its own savepoint.

### Sharing a folder

Folders share exactly the way files do — directly with a registered user, or through an
unguessable public link with an optional password and expiry — and sharing one shares
everything under it. Access is evaluated live against the tree, so files added later are
covered without re-sharing.

A folder link turns `share.html` into a small read-only browser: the visitor walks the
same structure the owner built, downloads any single file, or takes the folder (or any
subfolder) as a `.zip`. Visitors navigate by name rather than by id, so a link can never
be used to reach a folder outside the share, and a `file_id` that is not inside the
shared subtree is refused.

Owners can also download any of their own folders as a `.zip` from its menu; the archive
mirrors the tree, empty subfolders included.

### Dark mode

Implemented purely with the token block, not a second stylesheet. Light / Dark / System
are offered; the choice is stored in `localStorage` and the resolved value is also saved
to the `settings` table, so it follows the account to another browser. The theme is
painted by a tiny inline script in `<head>` before first paint, so there is no flash.

> The database column stores `light` or `dark` (per the specification), so the
> **System** option itself lives in the browser and what gets saved to the account is
> whichever theme System currently resolves to.

### Responsive

| Width | Behaviour |
|---|---|
| ≥1280px | full shell, multi-column grids |
| 1100–1280px | tighter padding, narrower sidebar |
| ≤992px | sidebar becomes an off-canvas drawer behind a hamburger, with a scrim |
| ≤768px | stats two-up, shared cards one-up, settings rows stack |
| ≤560px | files/folders two-up, modals become bottom sheets, toasts span the width |
| ≤400px | single-column files and folders |

Verified at 1440, 1280, 768, 480, 390 and 360px with no horizontal overflow.

### Accessibility

Semantic landmarks (`aside`/`header`/`main`/`nav`), a skip link, labelled inputs,
`aria-label` on every icon-only button, `aria-current` on the active nav item,
`aria-pressed` on toggles, `aria-sort` on sortable headers, visible focus rings,
keyboard-navigable action menus (arrows / Home / End / Escape) and search results
(arrows / Enter / Escape), and Ctrl/⌘+K to focus search.

### No fake functionality

Every control performs a real API call. Where the backend has no matching feature the
UI says so rather than pretending:

- Share recipients are labelled **Can view**, with no fake "Can edit" option, because
  the `file_sharing` table has no permission column.
- Notifications are derived from real data — files shared with you, your own activity
  and the live storage figure — since the schema has no notifications table. Read state
  is per-browser.

## Tests

```bash
cd backend
venv\Scripts\activate
pytest -q
```

156 tests run against a throwaway SQLite database and a temporary upload directory:

| File | Covers |
|---|---|
| `test_auth.py` | registration, bcrypt hashing, duplicate username/email, login by username and email, wrong password, disabled accounts, token guards, logout |
| `test_folders.py` | creation, 3-level nesting, breadcrumbs, duplicate names, rename, cycle prevention, cross-user access, traversal in folder names, deleting a folder trashes its files |
| `test_files.py` | single and multi upload, bytes landing on disk, UUID naming, folder targeting, blocked extensions, size limit, download contents and filename, rename/move/star, cross-user access |
| `test_trash_storage.py` | usage after upload/trash/purge, total = used + available, the delete→restore→purge cycle, bytes removed from disk, per-user isolation, empty trash, quota enforcement |
| `test_sharing.py` | user shares, Shared-with-me search, token randomness, public links, password protection and hashing, expiry (`410`), revocation, trashed files dropping out of shares |
| `test_misc.py` | settings persistence and isolation, profile updates and conflicts, password change, avatar validation, dashboard counters, search behaviour and SQL-injection safety, the full activity-log matrix, admin-only endpoints, error envelope |
| `test_security.py` | ID tampering across 11 endpoints, anonymous access to 13 endpoints, unreachable `uploads/` and `backend/`, forged and expired tokens, upload traversal, spoofed `user_id`/`shared_by` in request bodies |
| `test_folder_upload.py` | building a directory tree in one call, implied intermediate folders, re-upload merging instead of duplicating, `..` segments dropped, the depth limit, cross-user rejection, exact path echo-back, folder-to-`.zip` with empty folders preserved |
| `test_clipboard.py` | file and folder copy (bytes duplicated, original independent), copy-into-itself rejection, batch move/copy/trash/star, per-item failure reporting with the rest still applied, and the `(copy)` vs `(2)` suffix rule |
| `test_folder_sharing.py` | folder shares appearing for the recipient, access reaching nested files, strangers still refused, revocation withdrawing that access, public folder links, one-level browsing, traversal and out-of-share `file_id` refusal, `.zip` of a share, password gating, expiry (`410`) |
| `test_plans.py` | the seeded catalogue, one free default, yearly being a real discount, new accounts landing on Free with 25 GB, the backfill for pre-plan accounts, and every admin endpoint refusing an ordinary or anonymous caller |
| `test_admin.py` | live stats, user search and detail, assigning a plan moving the quota immediately, supersede-not-duplicate history, yearly pricing and dates, no-end-date grants, reverting to free, disabling locking a user out, the self-lockout guards, deleting a user with their files, plan create/edit/delete, allowance edits moving every subscriber, and the free-default protections |

### Live-server tests

`backend/tests/browser/` holds four scripts that drive the **real** running
application instead of an in-process test client. They are deliberately not
collected by `pytest`; start the server first, then run them by hand:

```bash
uvicorn app.main:app                          # terminal 1

python tests/browser/api_e2e.py               # terminal 2 - 83 HTTP checks, no browser
python tests/browser/ui_walkthrough.py        # 132 checks in real Chromium
python tests/browser/shared_page_check.py     # Shared-with-me against seeded data
python tests/browser/folder_features_check.py # 36 checks: folders, clipboard, sharing
python tests/browser/admin_panel_check.py     # 38 checks: /admin, plans, assignment
```

All four take the server origin as their first argument, so the whole browser suite can
be pointed at one instance deliberately:

```bash
python tests/browser/ui_walkthrough.py http://127.0.0.1:8011
```

The browser walkthrough needs Playwright:

```bash
pip install playwright
playwright install chromium
```

`ui_walkthrough.py` runs **132 checks** in real Chromium: the tech stack (Bootstrap
present, no React/Vue/Angular/jQuery), registration with inline validation and the
strength meter, the shell, the dashboard, the New menu, nested folders and
breadcrumbs, multi-file upload through the panel, the grid/list toggle and its
persistence, sort and filter, the action menu and details drawer, authenticated
download with a byte-for-byte comparison, starring, Recent grouping, the share modal
and public share page, trash restore and empty (both confirmations), the activity
timeline and filters, the storage ring and breakdown, dark mode (including that it
persists to the database, not just `localStorage`), the header toggle, notifications,
global search with Ctrl+K and arrow keys, the profile modal, a 390×844 mobile pass, a
768px tablet pass, accessibility basics, and logout plus the auth guard. It asserts
zero uncaught JS errors and zero console errors, and writes screenshots to
`tests/browser/shots/`.

`admin_panel_check.py` runs **38 checks** covering the panel end to end: it registers an
ordinary account and confirms it lands on Free with the catalogue shown, checks the gate
refuses that account by name, signs in as the administrator, reads the overview, creates
a plan and edits its price, assigns it to the user with yearly billing, confirms the
preview and the user row, then switches back to the user's own browser context to see the
new plan on their Storage page, in the ring and in the sidebar — and finally reverts and
deletes what it made, so it is safe to re-run.

`folder_features_check.py` runs **36 checks** covering the folder work end to end. It
builds a real three-level folder on disk, uploads it through the browser's own folder
picker, confirms the queue shows each file's path, walks My Files down to the deepest
file checking the breadcrumb at every level, selects everything and copies and pastes
it, cuts and pastes a folder, drops a folder tree through a synthetic `webkitGetAsEntry`
transfer to exercise the recursive walk, then creates a public folder link and browses
it from a separate anonymous browser context. Both browser scripts register a fresh account per
run and accept an alternative origin as their first argument.

---

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | environment label |
| `SECRET_KEY` | – | **set this**; signs the JWTs |
| `DATABASE_URL` | `sqlite:///./cloud_storage.db` | any SQLAlchemy URL |
| `UPLOAD_DIR` | `uploads` | storage root, relative to `backend/` |
| `MAX_FILE_SIZE_MB` | `100` | per-file upload limit |
| `JWT_EXPIRE_MINUTES` | `1440` | token lifetime |
| `DEFAULT_STORAGE_LIMIT_MB` | `25600` | fallback quota before a plan applies (25 GB) |
| `TRASH_RETENTION_DAYS` | `30` | how long trashed files survive |
| `CORS_ORIGINS` | see `.env.example` | comma-separated, or `*` |
| `SERVE_FRONTEND` | `true` | serve the HTML/CSS/JS from FastAPI |
| `FRONTEND_DIR` | `..` | where those files live |
| `ADMIN_USERNAME` | `vandit77` | the administrator created on first startup |
| `ADMIN_PASSWORD` | `123456@Vk` | **change this**; only used when creating that account |
| `ADMIN_EMAIL` | `vandit77@example.com` | email for that account |
| `CURRENCY_CODE` | `INR` | currency plan prices are recorded in |
| `CURRENCY_SYMBOL` | `₹` | symbol shown next to a price |

`.env` is git-ignored. Never commit real secrets — and change `ADMIN_PASSWORD` before
this runs anywhere but your own machine.
