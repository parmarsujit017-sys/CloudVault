"""Real-browser check of /admin: sign-in, plans, and assigning one to a user.

Run the server first, then:  python tests/browser/admin_panel_check.py
Registers a fresh ordinary account each run, so it is safe to re-run.

Pass a different origin as argv[1] (default http://127.0.0.1:8000).
The administrator credentials come from the backend .env / config defaults.
"""
import sys
import time

from playwright.sync_api import sync_playwright

# Plan prices carry a currency symbol, which a cp1252 console cannot encode.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

ADMIN_USER = "vandit77"
ADMIN_PASS = "123456@Vk"

STAMP = str(int(time.time()))
USER = "planuser" + STAMP
PASS = "PlanUser@1234"

# Unique per run: plan codes are unique, so a leftover from an interrupted run
# would otherwise make the next one fail on a name clash.
PLAN = "Campus Pack " + STAMP

from pathlib import Path

SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)

ok, bad = 0, 0
page_errors = []


def check(label, condition, extra=""):
    global ok, bad
    if condition:
        ok += 1
        print(f"  PASS  {label}")
    else:
        bad += 1
        print(f"  FAIL  {label}  {extra}")


def section(name):
    print(f"\n== {name} ==")


def register(page, username, password):
    page.goto(f"{BASE}/register.html")
    page.fill("#fullname", "Plan Tester")
    page.fill("#username", username)
    page.fill("#email", username + "@example.com")
    page.fill("#password", password)
    page.fill("#confirm", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/dashboard.html", timeout=30000)


def admin_sign_in(page, username, password):
    page.goto(f"{BASE}/admin")
    page.wait_for_selector("#adminGate", state="visible", timeout=20000)
    page.fill("#adminUsername", username)
    page.fill("#adminPassword", password)
    page.click("#adminLoginSubmit")


def go(page, view):
    page.click(f".admin-nav-item[data-view={view}]")
    page.wait_for_timeout(1200)


def run(pw):
    browser = pw.chromium.launch()

    # ---------------------------------------------------------- ordinary user
    section("An ordinary account")
    user_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    user_page = user_ctx.new_page()
    user_page.set_default_timeout(20000)
    user_page.on("pageerror", lambda e: page_errors.append(f"{user_page.url}: {e}"))

    register(user_page, USER, PASS)
    check("registered a normal account", "/dashboard.html" in user_page.url)

    user_page.goto(f"{BASE}/storage.html")
    user_page.wait_for_selector("#myPlanHost .my-plan", timeout=20000)

    plan_name = user_page.locator("#myPlanHost .my-plan-name").inner_text().strip()
    check("a new account is shown on the Free plan", plan_name.startswith("Free"), plan_name)

    meta = user_page.locator("#myPlanHost .my-plan-meta").inner_text()
    check("the free plan states its 25 GB allowance", "25" in meta and "GB" in meta, meta)

    cards = user_page.locator("#catalogueHost .plan-card").count()
    check("the catalogue lists the paid plans too", cards >= 2, cards)
    check(
        "the current plan is marked in the catalogue",
        user_page.locator("#catalogueHost .plan-card.is-current").count() == 1
    )
    user_page.screenshot(path=str(SHOTS / "plan-user-free.png"), full_page=True)

    # ------------------------------------------------------- the gate refuses
    section("The panel refuses a non-admin")
    admin_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = admin_ctx.new_page()
    page.set_default_timeout(20000)
    page.on("pageerror", lambda e: page_errors.append(f"{page.url}: {e}"))

    admin_sign_in(page, USER, PASS)

    # Wait for the refusal rather than sleeping: bcrypt makes the round trip
    # slow enough that a fixed pause is a coin toss.
    page.wait_for_selector("#adminLoginError:not(.is-hidden)", timeout=30000)

    check("the panel stays closed", page.locator("#adminShell").is_hidden())
    message = page.locator("#adminLoginError").inner_text()
    check("and says why", "not an administrator" in message.lower(), message)
    page.screenshot(path=str(SHOTS / "admin-gate-refused.png"))

    # ------------------------------------------------------------- signing in
    section("Administrator sign in")
    page.fill("#adminUsername", ADMIN_USER)
    page.fill("#adminPassword", ADMIN_PASS)
    page.click("#adminLoginSubmit")

    page.wait_for_selector("#adminShell", state="visible", timeout=20000)
    page.wait_for_selector(".stat", timeout=20000)
    check("the panel opened", page.locator("#adminShell").is_visible())
    check("it names the signed-in administrator",
          "@" + ADMIN_USER in page.locator("#adminWhoUser").inner_text())

    stats = page.locator(".stat").count()
    check("the overview shows its stat cards", stats >= 6, stats)
    check("and the plan breakdown table",
          page.locator(".panel .app-table tbody tr").count() >= 4)
    page.screenshot(path=str(SHOTS / "admin-overview.png"), full_page=True)

    # ------------------------------------------------------------------ theme
    section("The theme toggle agrees with the rest of the app")

    def theme_of(target):
        return target.evaluate("document.documentElement.getAttribute('data-theme')")

    started_as = theme_of(page)
    page.click("#adminThemeToggle")
    page.wait_for_timeout(800)
    flipped = theme_of(page)
    check("the toggle flips the theme", flipped != started_as, f"{started_as} -> {flipped}")

    page.reload()
    page.wait_for_selector("#adminShell", state="visible", timeout=30000)
    page.wait_for_timeout(1200)
    check("it survives a reload of the panel", theme_of(page) == flipped,
          f"{flipped} -> {theme_of(page)}")

    # The app applies the theme stored on the account, so a panel-only change
    # would be undone the moment the administrator opened their own drive.
    user_page.goto(f"{BASE}/dashboard.html")
    user_page.wait_for_selector("#themeToggle", timeout=20000)
    user_page.wait_for_timeout(1200)

    page.goto(f"{BASE}/dashboard.html")
    page.wait_for_selector("#themeToggle", timeout=20000)
    page.wait_for_timeout(1200)
    check("and the app honours it", theme_of(page) == flipped,
          f"expected {flipped}, got {theme_of(page)}")

    page.goto(f"{BASE}/admin")
    page.wait_for_selector("#adminShell", state="visible", timeout=30000)
    page.wait_for_timeout(1000)
    page.click("#adminThemeToggle")
    page.wait_for_timeout(800)
    check("and it toggles back", theme_of(page) == started_as,
          f"{flipped} -> {theme_of(page)}")

    # ------------------------------------------------------------------ plans
    section("Plans")
    go(page, "plans")

    plan_cards = page.locator(".plan-card").count()
    check("the shipped catalogue is listed", plan_cards >= 4, plan_cards)
    check("the free plan is flagged as the default",
          page.locator(".plan-card:has-text('Free') .badge-soft:has-text('Default')").count() == 1)
    page.screenshot(path=str(SHOTS / "admin-plans.png"), full_page=True)

    # ---- create -------------------------------------------------------
    page.click("#adminHeadActions button:has-text('New plan')")
    page.wait_for_selector(".modal.show #planName", timeout=15000)

    page.fill("#planName", PLAN)
    page.fill("#planDesc", "A test plan created by the browser check.")
    page.fill("#planStorage", "750")
    page.select_option("#planUnit", "GB")
    page.fill("#planMonthly", "199")
    page.fill("#planYearly", "1990")
    page.fill("#planFeatures", "750 GB of storage\nCreated by a test")
    page.screenshot(path=str(SHOTS / "admin-plan-form.png"))

    page.click(".modal.show button[type=submit]")
    page.wait_for_selector(".modal.show", state="detached", timeout=20000)
    page.wait_for_timeout(1500)

    created = page.locator(f".plan-card:has-text('{PLAN}')")
    check("the new plan appears in the catalogue", created.count() == 1)
    check("with the storage it was given",
          "750.0 GB" in created.first.inner_text(), created.first.inner_text())
    check("and its price", "199" in created.first.inner_text())

    # ---- edit ---------------------------------------------------------
    created.first.locator("button:has-text('Edit')").click()
    page.wait_for_selector(".modal.show #planMonthly", timeout=15000)
    page.fill("#planMonthly", "149")
    page.click(".modal.show button[type=submit]")
    page.wait_for_selector(".modal.show", state="detached", timeout=20000)
    page.wait_for_timeout(1500)

    check("editing the price took effect",
          "149" in page.locator(f".plan-card:has-text('{PLAN}')").first.inner_text())

    # ------------------------------------------------------------------ users
    section("Assigning the plan to a user")
    go(page, "users")

    page.fill("#adminUserSearch", USER)
    page.wait_for_timeout(1600)

    row = page.locator(f"tr:has-text('{USER}')")
    check("the user is found", row.count() == 1, page.locator("tbody tr").count())
    check("their current plan is shown as Free", "Free" in row.first.inner_text(),
          row.first.inner_text())
    page.screenshot(path=str(SHOTS / "admin-users.png"), full_page=True)

    row.first.locator("button:has-text('Assign plan')").click()
    page.wait_for_selector(".modal.show #assignPlan", timeout=15000)

    options = page.locator("#assignPlan option").all_inner_texts()
    check("the new plan is assignable", any(PLAN in o for o in options), options)

    page.select_option("#assignPlan", label=[o for o in options if PLAN in o][0])
    page.select_option("#assignCycle", "yearly")
    page.wait_for_timeout(400)

    preview = page.locator(".admin-preview").inner_text()
    check("the dialog previews the new allowance", "750.0 GB" in preview, preview)
    check("and the price for the cycle", "1,990" in preview or "1990" in preview, preview)
    page.screenshot(path=str(SHOTS / "admin-assign-plan.png"))

    page.click(".modal.show button[type=submit]")
    page.wait_for_selector(".modal.show", state="detached", timeout=20000)
    page.wait_for_timeout(2000)

    row = page.locator(f"tr:has-text('{USER}')")
    text = row.first.inner_text()
    check("the user row now shows the assigned plan", PLAN in text, text)
    check("and the billing cycle", "yearly" in text, text)
    check("and the raised storage limit", "750.0 GB" in text, text)

    # -------------------------------------------------- the user sees it
    section("The user sees the plan the admin assigned")
    user_page.goto(f"{BASE}/storage.html")
    user_page.wait_for_selector("#myPlanHost .my-plan", timeout=20000)

    name = user_page.locator("#myPlanHost .my-plan-name").inner_text()
    meta = user_page.locator("#myPlanHost .my-plan-meta").inner_text()

    check("their plan panel names it", PLAN in name, name)
    check("marked as a yearly subscription", "yearly" in name.lower(), name)
    check("with the new allowance", "750.0 GB" in meta, meta)
    check("and a renewal date", "Renews" in meta, meta)

    ring = user_page.locator("#storageHero").inner_text()
    check("the storage ring uses the new limit", "750.0 GB" in ring, ring)

    sidebar = user_page.locator("#sidebarPlanName").inner_text()
    check("the sidebar names the plan too", PLAN in sidebar, sidebar)
    user_page.screenshot(path=str(SHOTS / "plan-user-assigned.png"), full_page=True)

    # ------------------------------------------------------------- tidy up
    section("Revert and clean up")
    row.first.locator(".dot-btn").click()
    page.wait_for_timeout(400)
    page.click(".app-menu.show button:has-text('Revert to free plan')")
    page.wait_for_selector(".modal.show", timeout=15000)
    page.click(".modal.show .btn-app-danger")
    page.wait_for_timeout(2000)

    text = page.locator(f"tr:has-text('{USER}')").first.inner_text()
    check("the user is back on Free", "Free" in text, text)

    user_page.goto(f"{BASE}/storage.html")
    user_page.wait_for_selector("#myPlanHost .my-plan", timeout=20000)
    meta = user_page.locator("#myPlanHost .my-plan-meta").inner_text()
    check("and their allowance dropped back to 25 GB", "25.0 GB" in meta, meta)

    # The test plan has no subscribers now, so it can be deleted.
    go(page, "plans")
    page.locator(f".plan-card:has-text('{PLAN}')").first.locator(".dot-btn").click()
    page.wait_for_timeout(400)
    page.click(".app-menu.show button:has-text('Delete plan')")
    page.wait_for_selector(".modal.show", timeout=15000)
    page.click(".modal.show .btn-app-danger")
    page.wait_for_timeout(2000)

    check("the test plan was deleted",
          page.locator(f".plan-card:has-text('{PLAN}')").count() == 0)

    browser.close()


with sync_playwright() as pw:
    run(pw)

print(f"\n{ok} passed, {bad} failed")
if page_errors:
    print("\nPage errors:")
    for entry in page_errors:
        print("  " + entry)

sys.exit(1 if (bad or page_errors) else 0)
