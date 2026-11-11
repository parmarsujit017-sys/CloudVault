"""Development seed data.

This is DEMO data and is deliberately kept out of the application itself - the
app never ships fake files, folders or storage numbers. Run it only when you
want something to look at locally:

    python seed.py            # add demo users/folders/files
    python seed.py --reset    # wipe the database and uploads first

Accounts created:
    demo    / Demo@1234   (admin)
    rahul   / Rahul@1234  (on a paid plan, so the admin panel has something to show)

The real administrator for /admin is not created here - the application creates
it from configuration on startup (ADMIN_USERNAME / ADMIN_PASSWORD).
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
from datetime import datetime, timedelta

from sqlalchemy import select

from app.auth.security import hash_password
from app.config import settings
from app.database import Base, SessionLocal, engine, init_db
from app.models import FileShare, Folder, Plan, Setting, User
from app.services import file_service, plan_service, share_service, storage_service

DEMO_FILES = [
    ("Getting Started.pdf", b"%PDF-1.4 Cloud getting started guide\n" * 400),
    ("Project Report.docx", b"Project report body text\n" * 900),
    ("Student Data.xlsx", b"name,roll,marks\n" * 700),
    ("Semester Notes.txt", b"Semester notes\n" * 1200),
    ("Timetable.csv", b"day,subject,room\n" * 300),
]


def reset() -> None:
    print("Dropping tables and clearing uploads...")
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(settings.upload_path / "users", ignore_errors=True)


def make_user(db, fullname: str, username: str, email: str, password: str, role: str) -> User:
    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        print(f"  user {username} already exists, reusing")
        return existing

    user = User(
        fullname=fullname,
        username=username,
        email=email,
        password=hash_password(password),
        role=role,
        storage_limit=float(settings.DEFAULT_STORAGE_LIMIT_MB),
        status="active",
    )
    db.add(user)
    db.flush()

    db.add(Setting(user_id=user.id))
    storage_service.sync_user_storage(db, user)
    db.flush()

    # Every account belongs on a plan; without one the admin panel would list a
    # user it cannot describe.
    default = plan_service.free_plan(db)
    if default is not None:
        plan_service.assign(db, user, default, "free", note="Seeded account")

    print(f"  created {username} / {password} ({role})")
    return user


def make_folder(db, user: User, name: str, parent: Folder | None = None) -> Folder:
    folder = Folder(
        user_id=user.id,
        folder_name=name,
        parent_folder=parent.id if parent else None,
    )
    db.add(folder)
    db.flush()
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Cloud with demo data")
    parser.add_argument("--reset", action="store_true", help="wipe the database and uploads first")
    args = parser.parse_args()

    if args.reset:
        reset()

    init_db()
    db = SessionLocal()

    try:
        print("Plans:")
        created = plan_service.seed_catalogue(db)
        db.flush()
        print(f"  {created} plan(s) created" if created else "  catalogue already present")

        print("Users:")
        demo = make_user(db, "Demo User", "demo", "demo@example.com", "Demo@1234", "admin")
        rahul = make_user(db, "Rahul Shah", "rahul", "rahul@example.com", "Rahul@1234", "user")

        # One paid subscriber, so the admin overview is not all zeroes.
        personal = db.execute(
            select(Plan).where(Plan.code == "personal")
        ).scalar_one_or_none()
        if personal is not None:
            plan_service.assign(
                db, rahul, personal, "yearly", assigned_by=demo.id, note="Seeded subscription"
            )
            print(f"  {rahul.username} put on {personal.name} (yearly)")

        print("Folders:")
        my_files = make_folder(db, demo, "My Files")
        documents = make_folder(db, demo, "Documents", my_files)
        make_folder(db, demo, "College", documents)
        make_folder(db, demo, "Work", documents)
        make_folder(db, demo, "Images", my_files)
        print("  My Files > Documents > (College, Work), My Files > Images")

        print("Files:")
        stored = []
        for index, (name, payload) in enumerate(DEMO_FILES):
            target = documents.id if index % 2 == 0 else None
            record = file_service.store_upload(
                db=db,
                user=demo,
                upload_stream=io.BytesIO(payload),
                original_filename=name,
                content_type=None,
                folder_id=target,
                ip_address="127.0.0.1",
            )
            stored.append(record)
            print(f"  {name} ({len(payload)} bytes)")

        print("Shares:")
        share = FileShare(
            file_id=stored[1].id,
            shared_by=demo.id,
            shared_to=rahul.id,
            share_link=share_service.generate_token(db),
        )
        db.add(share)

        public = FileShare(
            file_id=stored[0].id,
            shared_by=demo.id,
            shared_to=None,
            share_link=share_service.generate_token(db),
            expiry_date=datetime.utcnow() + timedelta(days=7),
        )
        db.add(public)
        db.flush()

        print(f"  '{stored[1].original_name}' shared with rahul")
        print(f"  public link: /share.html?token={public.share_link}")

        storage_service.sync_user_storage(db, demo)
        storage_service.sync_user_storage(db, rahul)
        db.commit()

        print("\nDone. Log in at http://127.0.0.1:8000/login.html as demo / Demo@1234")
        return 0

    except Exception as exc:
        db.rollback()
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
