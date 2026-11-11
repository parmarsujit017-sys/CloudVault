"""Checks the Shared With Me page against seeded data.

Run `python seed.py` first, then start the server, then:
    python tests/browser/shared_page_check.py
Signs in as rahul, who has one file shared with them by demo.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)

ok = bad = 0
errs = []


def check(label, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        bad += 1
        print(f"  FAIL  {label}  {extra}")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    p = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    p.set_default_navigation_timeout(60000)
    p.set_default_timeout(20000)
    p.on("pageerror", lambda e: errs.append(str(e)))

    p.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
    p.fill("#identifier", "rahul")
    p.fill("#password", "Rahul@1234")
    p.click("#loginSubmit")
    p.wait_for_url("**/dashboard.html", timeout=30000, wait_until="domcontentloaded")

    p.goto(f"{BASE}/shared.html", wait_until="domcontentloaded")
    p.wait_for_selector(".shared-card")

    card = p.locator(".shared-card").first
    check("shared card rendered from the API", p.locator(".shared-card").count() == 1)
    check("file name shown",
          card.locator(".sc-name").inner_text() == "Project Report.docx",
          card.locator(".sc-name").inner_text())
    check("owner shown", "Demo User" in card.locator(".sc-meta").inner_text(),
          card.locator(".sc-meta").inner_text())
    check("word file uses the Word type colour",
          card.locator(".ftype[data-type=word]").count() == 1)
    check("size shown", "KB" in card.locator(".sc-meta").inner_text())
    p.screenshot(path=str(SHOTS / "27-shared-populated.png"), full_page=True)

    # Backend-side search
    p.fill("#sharedSearch", "demo")
    p.wait_for_timeout(700)
    check("search by owner keeps the card", p.locator(".shared-card").count() == 1)

    p.fill("#sharedSearch", "zzzz")
    p.wait_for_selector(".empty-state")
    check("no-match shows an empty state", p.is_visible(".empty-state"))

    p.fill("#sharedSearch", "")
    p.wait_for_selector(".shared-card")

    # List view
    p.click("#viewList")
    p.wait_for_selector(".app-table")
    headers = [h.strip().lower() for h in p.locator(".app-table thead th").all_inner_texts()]
    check("list view shows shared-by and expiry columns",
          "shared by" in headers and "expiry" in headers, str(headers))
    p.screenshot(path=str(SHOTS / "28-shared-list.png"), full_page=True)
    p.click("#viewGrid")
    p.wait_for_selector(".shared-card")

    # Download through the three-dot menu
    p.locator(".shared-card .dot-btn").click()
    p.wait_for_selector(".app-menu.show")
    with p.expect_download(timeout=25000) as dl:
        p.click(".app-menu.show .dropdown-item:has-text('Download')")
    check("download works for the recipient",
          dl.value.suggested_filename == "Project Report.docx", dl.value.suggested_filename)

    # Read-only details
    p.locator(".shared-card .dot-btn").click()
    p.click(".app-menu.show .dropdown-item:has-text('Details')")
    p.wait_for_selector(".modal.show")
    body = p.inner_text(".modal.show .modal-body")
    check("details show provenance", "Demo User" in body, body[:120])
    check("details state the access level", "View and download" in body, body[:200])
    p.screenshot(path=str(SHOTS / "29-shared-details.png"))
    p.click(".modal.show .btn-close")

    check("no JS errors", not errs, str(errs))
    b.close()

print(f"\n=========== {ok} passed, {bad} failed ===========")
raise SystemExit(1 if bad else 0)
