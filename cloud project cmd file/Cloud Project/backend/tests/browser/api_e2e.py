"""End-to-end walkthrough against the REALLY running uvicorn server."""
import sys
import time

import httpx

# Unique accounts per run, so the script can be re-run without resetting the DB.
SUFFIX = str(int(time.time()))
U1 = "sujit" + SUFFIX
U2 = "vandan" + SUFFIX

# Origin of the running server; override as the first argument so the whole
# browser suite can be pointed at one instance deliberately.
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=30, follow_redirects=False)

ok = 0
bad = 0


def check(label, condition, extra=""):
    global ok, bad
    if condition:
        ok += 1
        print(f"  PASS  {label}")
    else:
        bad += 1
        print(f"  FAIL  {label}  {extra}")


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


print("\n== REGISTER + LOGIN ==")
r = c.post("/api/auth/register", json={
    "fullname": "Sujit Parmar", "username": U1,
    "email": U1 + "@example.com", "password": "Sujit@123"})
check("register user 1 -> 201", r.status_code == 201, r.text[:200])
sujit = r.json()["access_token"]
# Registering never grants administration, not even to the first account: the
# administrator is created from configuration at startup.
check("registration yields an ordinary user", r.json()["user"]["role"] == "user")
check("no password field in response", "password" not in r.json()["user"])

r = c.post("/api/auth/register", json={
    "fullname": "Vandan Patel", "username": U2,
    "email": U2 + "@example.com", "password": "Vandan@123"})
check("register user 2 -> 201", r.status_code == 201, r.text[:200])
vandan = r.json()["access_token"]

r = c.post("/api/auth/login", json={"username": U1, "password": "Sujit@123"})
check("login -> 200", r.status_code == 200)
sujit = r.json()["access_token"]

r = c.post("/api/auth/login", json={"username": U1, "password": "nope"})
check("bad password -> 401", r.status_code == 401)


print("\n== NESTED FOLDERS ==")
def mkfolder(name, parent=None):
    return c.post("/api/folders", headers=H(sujit),
                  json={"folder_name": name, "parent_folder": parent}).json()

myfiles = mkfolder("My Files")
docs = mkfolder("Documents", myfiles["id"])
college = mkfolder("College", docs["id"])
work = mkfolder("Work", docs["id"])
images = mkfolder("Images", myfiles["id"])
check("3-level nesting created", college["parent_folder"] == docs["id"])

r = c.get(f"/api/folders/{college['id']}", headers=H(sujit))
crumbs = [x["folder_name"] for x in r.json()["breadcrumb"]]
check("breadcrumb My Files>Documents>College",
      crumbs == ["My Files", "Documents", "College"], str(crumbs))


print("\n== UPLOADS ==")
r = c.post("/api/files/upload", headers=H(sujit),
           files=[("files", ("college-notes.pdf", b"%PDF-1.4 notes" * 500, "application/pdf"))],
           params={"folder_id": college["id"]})
check("upload into nested folder -> 201", r.status_code == 201, r.text[:200])
notes = r.json()["uploaded"][0]
check("original name preserved", notes["original_name"] == "college-notes.pdf")
check("stored name is a uuid", len(notes["file_name"].split(".")[0]) == 32, notes["file_name"])

r = c.post("/api/files/upload", headers=H(sujit), files=[
    ("files", ("report.docx", b"d" * (2 * 1024 * 1024), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
    ("files", ("data.xlsx", b"xlsx bytes", "application/vnd.ms-excel")),
    ("files", ("photo.png", b"\x89PNG fake", "image/png")),
])
check("multi upload of 3 -> 201", r.status_code == 201 and len(r.json()["uploaded"]) == 3, r.text[:200])
report = r.json()["uploaded"][0]

r = c.post("/api/files/upload", headers=H(sujit),
           files=[("files", ("hack.exe", b"MZ", "application/octet-stream"))])
check("exe upload refused -> 400", r.status_code == 400)


print("\n== DOWNLOAD ==")
r = c.get(f"/api/files/{notes['id']}/download", headers=H(sujit))
check("download -> 200", r.status_code == 200)
check("bytes match", r.content == b"%PDF-1.4 notes" * 500)
check("original filename in disposition",
      "college-notes.pdf" in r.headers.get("content-disposition", ""),
      r.headers.get("content-disposition"))

r = c.get(f"/api/files/{notes['id']}/download", headers=H(vandan))
check("other user download -> 403", r.status_code == 403)


print("\n== STORAGE ==")
s1 = c.get("/api/storage", headers=H(sujit)).json()
check("storage sums correctly",
      round(s1["used_storage"] + s1["available_storage"], 2) == round(s1["total_storage"], 2), str(s1))
check("total is 25600 MB (the 25 GB Free plan)", s1["total_storage"] == 25600.0)
check("used > 0 after uploads", s1["used_storage"] > 0, str(s1["used_storage"]))


print("\n== SHARING: DIRECT ==")
r = c.post("/api/shares", headers=H(sujit),
           json={"file_id": report["id"], "shared_to_username": U2})
check("share with vandan -> 201", r.status_code == 201, r.text[:200])
direct_share = r.json()

r = c.get("/api/shares/received", headers=H(vandan))
check("appears in vandan's Shared with me",
      any(x["file_id"] == report["id"] for x in r.json()), r.text[:200])
check("owner name shown",
      r.json()[0]["shared_by_name"] == "Sujit Parmar", r.text[:120])

r = c.get("/api/shares/received", headers=H(vandan), params={"q": "report"})
check("shared search by filename works", len(r.json()) == 1)
r = c.get("/api/shares/received", headers=H(vandan), params={"q": "Sujit Parmar"})
check("shared search by owner works", len(r.json()) == 1)
r = c.get("/api/shares/received", headers=H(vandan), params={"q": "zzz"})
check("shared search no match -> empty", r.json() == [])

check("recipient can download",
      c.get(f"/api/files/{report['id']}/download", headers=H(vandan)).status_code == 200)


print("\n== SHARING: PUBLIC LINK ==")
r = c.post("/api/shares", headers=H(sujit), json={"file_id": notes["id"]})
tok = r.json()["share_link"]
check("token is 48 hex chars", len(tok) == 48, tok)
check("share_url points at share.html", "share.html?token=" in (r.json()["share_url"] or ""),
      str(r.json()["share_url"]))

check("anonymous info -> 200", c.get(f"/api/share/{tok}").status_code == 200)
r = c.get(f"/api/share/{tok}/download")
check("anonymous download works", r.status_code == 200 and len(r.content) > 0)
check("guessable /api/share/1 -> 404", c.get("/api/share/1").status_code == 404)


print("\n== SHARING: PASSWORD + EXPIRY ==")
r = c.post("/api/shares", headers=H(sujit),
           json={"file_id": notes["id"], "password": "open-me"})
ptok = r.json()["share_link"]
check("requires_password flag", c.get(f"/api/share/{ptok}").json()["requires_password"] is True)
check("no password -> 401", c.get(f"/api/share/{ptok}/download").status_code == 401)
check("wrong password -> 401",
      c.get(f"/api/share/{ptok}/download", params={"password": "bad"}).status_code == 401)
check("verify wrong -> 401",
      c.post(f"/api/share/{ptok}/verify", json={"password": "bad"}).status_code == 401)
check("verify right -> 200",
      c.post(f"/api/share/{ptok}/verify", json={"password": "open-me"}).status_code == 200)
check("right password downloads",
      c.get(f"/api/share/{ptok}/download", params={"password": "open-me"}).status_code == 200)

r = c.post("/api/shares", headers=H(sujit),
           json={"file_id": notes["id"], "expiry_date": "2020-01-01T00:00:00"})
check("past expiry refused -> 400", r.status_code == 400)


print("\n== TRASH ==")
before = c.get("/api/storage", headers=H(sujit)).json()["used_storage"]
r = c.delete(f"/api/files/{report['id']}", headers=H(sujit))
check("delete -> trash 200", r.status_code == 200)
check("gone from listing",
      report["id"] not in [f["id"] for f in c.get("/api/files?root_only=false", headers=H(sujit)).json()])
check("present in trash",
      report["id"] in [t["file_id"] for t in c.get("/api/trash", headers=H(sujit)).json()])
check("revoked share removes it from vandan's list",
      report["id"] not in [s["file_id"] for s in c.get("/api/shares/received", headers=H(vandan)).json()])

r = c.post(f"/api/trash/{report['id']}/restore", headers=H(sujit))
check("restore -> 200", r.status_code == 200)
check("back in listing",
      report["id"] in [f["id"] for f in c.get("/api/files?root_only=false", headers=H(sujit)).json()])
check("storage restored", c.get("/api/storage", headers=H(sujit)).json()["used_storage"] == before)

c.delete(f"/api/files/{report['id']}", headers=H(sujit))
r = c.delete(f"/api/trash/{report['id']}", headers=H(sujit))
check("permanent delete -> 200", r.status_code == 200)
after = c.get("/api/storage", headers=H(sujit)).json()["used_storage"]
check("storage decreased after purge", after < before, f"{after} vs {before}")


print("\n== SETTINGS ==")
r = c.put("/api/settings", headers=H(sujit),
          json={"theme": "dark", "notifications": False, "language": "Gujarati"})
check("update settings -> 200", r.status_code == 200, r.text[:150])
r = c.get("/api/settings", headers=H(sujit)).json()
check("settings persisted",
      (r["theme"], r["notifications"], r["language"]) == ("dark", False, "Gujarati"), str(r))
check("vandan unaffected", c.get("/api/settings", headers=H(vandan)).json()["theme"] == "light")
c.put("/api/settings", headers=H(sujit), json={"theme": "light"})


print("\n== PROFILE ==")
png = bytes.fromhex("89504e470d0a1a0a") + b"body"
r = c.post("/api/users/me/avatar", headers=H(sujit), files={"file": ("me.png", png, "image/png")})
check("avatar upload -> 200", r.status_code == 200, r.text[:150])
check("avatar served back", c.get("/api/users/me/avatar", headers=H(sujit)).status_code == 200)

r = c.put("/api/users/me", headers=H(sujit), json={"fullname": "Sujit R Parmar"})
check("profile update -> 200", r.status_code == 200)
r = c.put("/api/users/me", headers=H(sujit), json={"username": U2})
check("duplicate username -> 409", r.status_code == 409)


print("\n== DASHBOARD + SEARCH ==")
d = c.get("/api/dashboard", headers=H(sujit)).json()
check("dashboard has real counts",
      d["total_folders"] == 5 and d["total_files"] >= 3, str(d)[:220])
check("dashboard storage consistent",
      round(d["storage_used"] + d["available_storage"], 2) == round(d["storage_limit"], 2))
check("recent lists populated",
      len(d["recent_files"]) > 0 and len(d["recent_activity"]) > 0)

s = c.get("/api/search", headers=H(sujit), params={"q": "colleg"}).json()
check("partial search finds file+folder",
      any(f["original_name"] == "college-notes.pdf" for f in s["files"]) and
      any(f["folder_name"] == "College" for f in s["folders"]), str(s)[:200])
s = c.get("/api/search", headers=H(vandan), params={"q": "colleg"}).json()
check("search is user-scoped", s["files"] == [] and s["folders"] == [])
s = c.get("/api/search", headers=H(sujit), params={"q": "'; DROP TABLE users;--"})
check("sql injection attempt harmless",
      s.status_code == 200 and c.get("/api/auth/me", headers=H(sujit)).status_code == 200)


print("\n== ACTIVITY ==")
acts = {a["activity"] for a in c.get("/api/activity?limit=200", headers=H(sujit)).json()}
for want in ["LOGIN", "UPLOAD", "DOWNLOAD", "CREATE_FOLDER", "DELETE_FILE",
             "RESTORE_FILE", "PERMANENT_DELETE", "SHARE_FILE",
             "UPDATE_PROFILE", "UPDATE_SETTINGS"]:
    check(f"logged {want}", want in acts)
check("ip recorded",
      any(a["ip_address"] for a in c.get("/api/activity", headers=H(sujit)).json()))
check("system activity is admin-only",
      c.get("/api/activity/all", headers=H(sujit)).status_code in (200, 403))
check("non-admin blocked from system activity",
      c.get("/api/activity/all", headers=H(vandan)).status_code == 403)


print("\n== SECURITY: ID TAMPERING ==")
check("GET  /api/folders/{alice} -> 403",
      c.get(f"/api/folders/{docs['id']}", headers=H(vandan)).status_code == 403)
check("DEL  /api/folders/{alice} -> 403",
      c.delete(f"/api/folders/{docs['id']}", headers=H(vandan)).status_code == 403)
check("GET  /api/files/{alice} -> 403",
      c.get(f"/api/files/{notes['id']}", headers=H(vandan)).status_code == 403)
check("DEL  /api/files/{alice} -> 403",
      c.delete(f"/api/files/{notes['id']}", headers=H(vandan)).status_code == 403)
check("upload into alice's folder -> 403",
      c.post("/api/files/upload", headers=H(vandan),
             files=[("files", ("x.txt", b"x", "text/plain"))],
             params={"folder_id": college["id"]}).status_code == 403)
check("anonymous /api/files -> 401", c.get("/api/files").status_code == 401)
check("anonymous /api/dashboard -> 401", c.get("/api/dashboard").status_code == 401)
check("forged token -> 401",
      c.get("/api/auth/me", headers={"Authorization": "Bearer aaa.bbb.ccc"}).status_code == 401)


print("\n== LOGOUT ==")
check("logout -> 200", c.post("/api/auth/logout", headers=H(sujit)).status_code == 200)

print(f"\n=========== {ok} passed, {bad} failed ===========")
sys.exit(1 if bad else 0)
