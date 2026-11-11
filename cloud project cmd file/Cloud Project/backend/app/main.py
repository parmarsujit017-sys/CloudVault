"""Cloud File Management System - FastAPI application entry point."""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.database import init_db
from app.routers import (
    activity,
    admin,
    auth,
    dashboard,
    files,
    folders,
    plans,
    search,
    settings as settings_router,
    shares,
    storage,
    trash,
    users,
)

logger = logging.getLogger("Cloud")
logging.basicConfig(level=logging.INFO)

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create tables, ensure the upload root exists and sweep expired trash."""
    init_db()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    logger.info("Database ready, uploads at %s", settings.upload_path)

    from app.database import SessionLocal
    from app.services import plan_service
    from app.services.file_service import purge_expired_trash

    db = SessionLocal()
    try:
        # The catalogue has to exist before the administrator, because the
        # administrator is put on a plan like everybody else.
        created = plan_service.seed_catalogue(db)
        if created:
            logger.info("Seeded %s default plan(s)", created)

        administrator = plan_service.ensure_admin(db)
        if administrator is not None:
            plan_service.grant_admin_allowance(db, administrator)
            logger.info("Administrator ready: /admin as '%s'", administrator.username)

        # Accounts that predate plans would otherwise have none until they next
        # signed in, which under-counts every figure in the admin panel.
        backfilled = plan_service.backfill_subscriptions(db)
        if backfilled:
            logger.info("Put %s existing account(s) on the free plan", backfilled)

        db.commit()

        removed = purge_expired_trash(db)
        if removed:
            logger.info("Purged %s expired trash file(s)", removed)
    finally:
        db.close()

    yield


app = FastAPI(
    title="Cloud File Management System API",
    version="1.0.0",
    description=(
        "REST API for the Cloud file manager: authentication, nested folders, "
        "real file storage, sharing, trash, storage accounting, activity logs and settings."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# ---------------------------------------------------------------------------
# Uniform JSON error envelope - the frontend never sees a Python traceback.
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "input"
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": f"{field}: {first.get('msg', 'invalid value')}",
            "details": [
                {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")}
                for e in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "message": "An unexpected server error occurred"},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(plans.router)
app.include_router(admin.router)
app.include_router(folders.router)
app.include_router(files.router)
app.include_router(trash.router)
app.include_router(shares.router)
app.include_router(shares.public_router)
app.include_router(storage.router)
app.include_router(activity.router)
app.include_router(settings_router.router)
app.include_router(dashboard.router)
app.include_router(search.router)


@app.get("/api/health", tags=["system"], summary="Health check")
def health():
    return {"success": True, "status": "ok", "env": settings.APP_ENV}


# ---------------------------------------------------------------------------
# Static frontend
#
# The existing HTML/CSS/JS lives in the project root next to backend/, so the
# handler below only serves known static file types and refuses to look inside
# backend/ (which holds .env, the database and uploads). The uploads directory
# is never mounted at all: files are reachable only through the authorised
# download endpoints.
# ---------------------------------------------------------------------------

STATIC_SUFFIXES = {
    ".html", ".css", ".js", ".mjs", ".map", ".json", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf",
}
PRIVATE_DIRS = {"backend", "venv", ".git", "__pycache__", "node_modules"}


if settings.SERVE_FRONTEND and settings.frontend_path.is_dir():

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(settings.frontend_path / "index.html")

    @app.get("/admin", include_in_schema=False)
    def admin_panel():
        """`/admin` is the address administrators are given, so it is a real
        route rather than a redirect to admin.html."""
        return FileResponse(settings.frontend_path / "admin.html")

    @app.get("/{asset_path:path}", include_in_schema=False)
    def frontend_asset(asset_path: str):
        root = settings.frontend_path
        candidate = (root / asset_path).resolve()

        if root != candidate and root not in candidate.parents:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

        parts = candidate.relative_to(root).parts
        if any(part in PRIVATE_DIRS or part.startswith(".") for part in parts):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

        if candidate.is_dir():
            candidate = candidate / "index.html"

        if candidate.suffix.lower() not in STATIC_SUFFIXES or not candidate.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

        return FileResponse(candidate)
