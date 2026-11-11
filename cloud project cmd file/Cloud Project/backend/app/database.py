"""SQLAlchemy engine / session / declarative base."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings

url = settings.DATABASE_URL
if url.startswith("sqlite:///./"):
    # Resolve relative sqlite paths against backend/ so the location does not
    # depend on the shell's working directory.
    url = "sqlite:///" + str((BASE_DIR / url.replace("sqlite:///./", "")).resolve())

connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}

engine = create_engine(url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_file_columns() -> None:
    """Backward-compatibility migration for older SQLite databases.

    Existing installs may not have the newer `files.kind`,
    `files.document_content` and `files.spreadsheet_data` columns yet. Add
    them the first time the app starts so the newer file APIs work without
    blowing up on older databases.
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'files'")
        ).fetchone()
        if table_exists is None:
            return

        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(files)")).fetchall()}

        if "kind" not in columns:
            conn.execute(text('ALTER TABLE files ADD COLUMN kind VARCHAR(32) DEFAULT "file" NOT NULL'))
        if "document_content" not in columns:
            conn.execute(text("ALTER TABLE files ADD COLUMN document_content TEXT"))
        if "spreadsheet_data" not in columns:
            conn.execute(text("ALTER TABLE files ADD COLUMN spreadsheet_data JSON"))

        conn.execute(text('UPDATE files SET kind = "file" WHERE kind IS NULL OR kind = ""'))


def _ensure_sqlite_share_permissions() -> None:
    """Backward-compatibility migration for share permission columns.

    Adds the `permission` column to file_sharing and folder_sharing tables
    for databases that don't have it yet. Defaults to "viewer".
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        # Check file_sharing table
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'file_sharing'")
        ).fetchone()
        if table_exists is not None:
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(file_sharing)")).fetchall()}
            if "permission" not in columns:
                conn.execute(text('ALTER TABLE file_sharing ADD COLUMN permission VARCHAR(32) DEFAULT "viewer" NOT NULL'))

        # Check folder_sharing table
        table_exists = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'folder_sharing'")
        ).fetchone()
        if table_exists is not None:
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(folder_sharing)")).fetchall()}
            if "permission" not in columns:
                conn.execute(text('ALTER TABLE folder_sharing ADD COLUMN permission VARCHAR(32) DEFAULT "viewer" NOT NULL'))


def init_db() -> None:
    """Create every table declared on Base. Safe to call repeatedly."""
    from app import models  # noqa: F401  (registers all mappers)

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_file_columns()
    _ensure_sqlite_share_permissions()
