"""Real-browser walkthrough of the redesigned Cloud frontend.

Run the server first, then:  python tests/browser/ui_walkthrough.py
Registers a fresh account each run, so it is safe to re-run.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Origin of the running server; override as the first argument so the whole
# browser suite can be pointed at one instance deliberately.
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)
TMP = Path(__file__).parent / "tmpfiles"
TMP.mkdir(exist_ok=True)

STAMP = str(int(time.time()))
USER = "uitest" + STAMP
EMAIL = USER + "@example.com"
PASS = "UiTest@1234"

ok, bad = 0, 0
page_errors = []
console_errors = []
ignore_console_from = None


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


def watch(page):
    page.on("pageerror", lambda e: page_errors.append(f"{page.url}: {e}"))
    page.on(
        "console",
        lambda m: console_errors.append(f"{page.url}: {m.text}") if m.type == "error" else None,
    )


def run(pw):
    global ignore_console_from

    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.set_default_navigation_timeout(60000)
    page.set_default_timeout(20000)
    watch(page)

    goto = lambda url: page.goto(url, wait_until="domcontentloaded")

    # ---------------- TECH STACK ----------------
    section("TECH STACK")
    goto(f"{BASE}/login.html")
    check("Bootstrap 5 CSS loaded",
          page.evaluate("!!document.querySelector('link[href*=bootstrap]')"))
    check("Bootstrap JS bundle present", page.evaluate("typeof bootstrap === 'object'"))
    check("Bootstrap Icons loaded",
          page.evaluate("!!document.querySelector('link[href*=\"bootstrap-icons\"]')"))
    check("no React/Vue/Angular/jQuery on the page", page.evaluate(
        "!window.React && !window.Vue && !window.angular && !window.jQuery && !window.$"))

    # ---------------- REGISTER ----------------
    section("REGISTER")
    goto(f"{BASE}/register.html")
    page.fill("#fullname", "UI Tester")
    page.fill("#username", USER)
    page.fill("#email", EMAIL)

    page.fill("#password", "abcdef")
    weak = page.get_attribute("#pwStrength", "data-score")
    page.fill("#password", "Abcdef1!xyz")
    strong = page.get_attribute("#pwStrength", "data-score")
    check("password strength meter reacts and scales",
          weak != "0" and int(strong) > int(weak), f"weak={weak} strong={strong}")

    page.fill("#password", PASS)
    page.fill("#confirm", "different")
    page.click("#registerSubmit")
    check("mismatched confirm blocks submit and shows a field error",
          page.is_visible("#confirmError") and "dashboard" not in page.url)

    page.fill("#confirm", PASS)
    page.click("#registerSubmit")
    page.wait_for_url("**/dashboard.html", timeout=30000, wait_until="domcontentloaded")
    check("register lands on the dashboard", "dashboard.html" in page.url)

    # ---------------- SHELL ----------------
    section("APP SHELL")
    page.wait_for_selector("#sidebarUserName:not(:has-text('—'))")
    check("sidebar rendered", page.locator(".sidebar .nav-item").count() >= 9)
    check("sidebar shows the real user", page.inner_text("#sidebarUserName") == "UI Tester")
    check("header search present", page.is_visible("#globalSearch"))
    check("notification bell present", page.is_visible("#notifBtn"))
    check("nav groups present (Main/Library/System)",
          page.locator(".nav-group-label").count() == 3)
    check("active nav item marked",
          page.get_attribute(".nav-item.active", "aria-current") == "page")

    page.wait_for_function(
        "document.getElementById('sidebarStorageText').textContent.indexOf('of') !== -1")
    check("storage widget uses live figures",
          "25.0 GB" in page.inner_text("#sidebarStorageText"),
          page.inner_text("#sidebarStorageText"))

    # ---------------- DASHBOARD ----------------
    section("DASHBOARD")
    page.wait_for_selector(".stat")
    check("four summary cards", page.locator(".stat").count() == 4)
    check("greeting is personalised", "UI" in page.inner_text("#greetingLine"),
          page.inner_text("#greetingLine"))
    check("stats show real zeros for a new account",
          page.locator(".stat-value").first.inner_text() == "0")
    check("recent files empty state shown",
          page.locator("#recentFiles .empty-state").count() == 1)
    check("recent activity populated (register/login logged)",
          page.locator("#recentActivity .timeline-item").count() > 0)
    page.screenshot(path=str(SHOTS / "01-dashboard-empty.png"), full_page=True)

    # ---------------- NEW MENU + FOLDERS ----------------
    section("NEW MENU + FOLDERS")
    goto(f"{BASE}/files.html")
    page.wait_for_selector("#newBtn")

    page.click("#newBtn")
    page.wait_for_selector(".dropdown-menu.show")
    check("New dropdown opens", page.is_visible("#menuNewFolder"))
    check("New menu has the three documented entries",
          page.locator("#menuNewFolder").count() == 1
          and page.locator("#menuUploadFiles").count() == 1
          and page.locator("#menuUploadFolder").count() == 1)

    page.click("#menuNewFolder")
    page.wait_for_selector(".modal.show input#promptInput, .modal.show input")
    page.fill(".modal.show input", "Documents")
    page.click(".modal.show button[type=submit]")
    page.wait_for_selector(".folder-card")
    check("folder created from a real modal (no window.prompt)",
          page.locator(".folder-card", has_text="Documents").count() == 1)

    page.click(".folder-card:has-text('Documents')")
    page.wait_for_function(
        "document.querySelectorAll('#breadcrumb .crumb').length === 2")
    check("breadcrumb shows My Files / Documents",
          "My Files" in page.inner_text("#breadcrumb")
          and "Documents" in page.inner_text("#breadcrumb"))
    check("URL carries the folder", "folder=" in page.url, page.url)

    page.click("#newBtn")
    page.click("#menuNewFolder")
    page.wait_for_selector(".modal.show input")
    page.fill(".modal.show input", "College")
    page.click(".modal.show button[type=submit]")
    page.wait_for_selector(".folder-card:has-text('College')")

    page.click(".folder-card:has-text('College')")
    page.wait_for_function(
        "document.querySelectorAll('#breadcrumb .crumb').length === 3")
    check("three-level nesting with breadcrumb", True)
    page.screenshot(path=str(SHOTS / "02-files-nested.png"), full_page=True)

    # breadcrumb navigation
    page.click("#breadcrumb .crumb:has-text('My Files')")
    # At the root the page title already says "My Files", so the breadcrumb
    # collapses rather than repeating a single crumb.
    page.wait_for_selector("#breadcrumb.is-hidden", state="attached")
    check("breadcrumb navigates back to the root and collapses",
          page.inner_text("#pageTitle") == "My Files")

    # ---------------- UPLOAD ----------------
    section("UPLOAD")
    f1 = TMP / "report.pdf"
    f2 = TMP / "notes.txt"
    f3 = TMP / "sheet.csv"
    f1.write_bytes(b"%PDF-1.4 report body" * 400)
    f2.write_bytes(b"plain notes" * 300)
    f3.write_bytes(b"a,b,c\n" * 500)

    page.set_input_files("#uploadFilesInput", [str(f1), str(f2), str(f3)])
    page.wait_for_selector("#uploadPanel.show")
    check("upload panel appears (not a blocking modal)", page.is_visible("#uploadPanel"))
    check("app stays usable during upload", page.is_visible("#globalSearch"))

    page.wait_for_function(
        "document.querySelectorAll('#uploadList .ui-status.ok').length === 3", timeout=40000)
    check("all three uploads report success in the panel", True)
    page.screenshot(path=str(SHOTS / "03-upload-panel.png"))

    page.wait_for_selector(".file-card")
    page.wait_for_function("document.querySelectorAll('.file-card').length === 3")
    check("three file cards rendered", True)
    check("file type colours differ per type",
          page.evaluate("""() => {
              const types = [...document.querySelectorAll('.file-card .ftype')]
                  .map(n => n.dataset.type);
              return new Set(types).size === 3;
          }"""), "expected pdf/text/excel")

    page.wait_for_function(
        "!document.getElementById('sidebarStorageText').textContent.startsWith('0 B')")
    check("sidebar storage updated after upload",
          not page.inner_text("#sidebarStorageText").startswith("0 B"),
          page.inner_text("#sidebarStorageText"))
    page.screenshot(path=str(SHOTS / "04-files-grid.png"), full_page=True)

    # ---------------- GRID / LIST TOGGLE ----------------
    section("GRID / LIST TOGGLE")
    page.click("#viewList")
    page.wait_for_selector(".app-table")
    check("list view renders a table", page.locator(".app-table tbody tr").count() == 3)
    headers = [h.strip().lower() for h in page.locator(".app-table thead th").all_inner_texts()]
    check("list view has the documented columns",
          headers[:4] == ["name", "type", "size", "modified"], str(headers))
    page.screenshot(path=str(SHOTS / "05-files-list.png"), full_page=True)

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(".app-table")
    check("view preference persists across a reload (localStorage)",
          page.locator(".app-table").count() == 1)

    page.click("#viewGrid")
    page.wait_for_selector(".file-grid")
    check("switching back to grid works", page.locator(".file-card").count() == 3)

    # ---------------- SORT + FILTER ----------------
    section("SORT + FILTER")
    page.click("#sortBtn")
    page.wait_for_selector("#sortMenu .dropdown-item")
    page.click("#sortMenu .dropdown-item:has-text('Name (A–Z)')")
    page.wait_for_timeout(300)
    names = page.locator(".file-card .fc-name").all_inner_texts()
    check("sort by name works", names == sorted(names), str(names))

    page.fill("#filterInput", "notes")
    page.wait_for_function("document.querySelectorAll('.file-card').length === 1")
    check("filter narrows the grid", True)
    page.fill("#filterInput", "zzzz")
    page.wait_for_selector(".empty-state")
    check("no-match empty state shown", page.is_visible(".empty-state"))
    page.fill("#filterInput", "")
    page.wait_for_function("document.querySelectorAll('.file-card').length === 3")

    # ---------------- ACTION MENU ----------------
    section("ACTION MENU + DETAILS")
    card = page.locator(".file-card", has_text="report.pdf")
    card.locator(".dot-btn").click()
    page.wait_for_selector(".app-menu.show")
    items = page.locator(".app-menu.show .dropdown-item").all_inner_texts()
    for expected in ["Open", "Download", "Share", "Rename", "Move to…",
                     "Add to Starred", "Details", "Move to Trash"]:
        check(f"file menu has {expected}", any(expected in i for i in items), str(items))
    page.screenshot(path=str(SHOTS / "06-action-menu.png"))

    page.click(".app-menu.show .dropdown-item:has-text('Details')")
    page.wait_for_selector("#detailsDrawer.show")
    check("details drawer opens", page.is_visible("#detailsDrawer"))
    check("details show the real size",
          "KB" in page.inner_text("#detailsBody"), page.inner_text("#detailsBody")[:120])
    page.wait_for_function(
        "document.querySelector('#detailsBody').textContent.indexOf('Loading') === -1")
    check("location resolved", "My Files" in page.inner_text("#detailsBody"))
    page.screenshot(path=str(SHOTS / "07-details-drawer.png"))
    page.click("#detailsDrawer .btn-close")
    page.wait_for_selector("#detailsDrawer.show", state="hidden")

    # ---------------- DOWNLOAD ----------------
    section("DOWNLOAD")
    card.locator(".dot-btn").click()
    with page.expect_download(timeout=25000) as dl:
        page.click(".app-menu.show .dropdown-item:has-text('Download')")
    check("download uses the original filename",
          dl.value.suggested_filename == "report.pdf", dl.value.suggested_filename)
    saved = TMP / "roundtrip.pdf"
    dl.value.save_as(str(saved))
    check("downloaded bytes match the upload",
          saved.read_bytes() == b"%PDF-1.4 report body" * 400)

    # ---------------- STAR ----------------
    section("STARRED")
    card.locator(".dot-btn").click()
    page.click(".app-menu.show .dropdown-item:has-text('Add to Starred')")
    page.wait_for_selector(".app-toast.is-success")
    goto(f"{BASE}/starred.html")
    page.wait_for_selector(".file-card")
    check("starred page lists the starred file",
          page.locator(".file-card", has_text="report.pdf").count() == 1)
    page.screenshot(path=str(SHOTS / "08-starred.png"), full_page=True)

    # ---------------- RECENT ----------------
    section("RECENT")
    goto(f"{BASE}/recent.html")
    page.wait_for_selector(".file-card")
    check("recent groups by day",
          page.locator(".section-heading h2", has_text="Today").count() == 1)
    check("recent lists all three files", page.locator(".file-card").count() == 3)
    page.screenshot(path=str(SHOTS / "09-recent.png"), full_page=True)

    # ---------------- SHARING ----------------
    section("SHARING")
    goto(f"{BASE}/files.html")
    page.wait_for_selector(".file-card")
    page.locator(".file-card", has_text="notes.txt").locator(".dot-btn").click()
    page.click(".app-menu.show .dropdown-item:has-text('Share')")
    page.wait_for_selector("#shareModal.show")
    check("share modal opens", page.is_visible("#shareModal"))
    check("modal names the file", "notes.txt" in page.inner_text("#shareModalTitle"))
    page.wait_for_function(
        "document.querySelector('#sharePeople').textContent.indexOf('Only you') !== -1")
    check("shows who currently has access", True)

    page.click("#shareLinkForm button[type=submit]")
    page.wait_for_selector("#shareLinkArea .panel")
    link = page.input_value("#shareLinkArea input")
    check("public link created", "share.html?token=" in link, link)
    check("token is long and unguessable", len(link.split("token=")[1]) == 48)
    page.screenshot(path=str(SHOTS / "10-share-modal.png"))

    page.click("#shareModal .btn-close")
    page.wait_for_selector("#shareModal.show", state="hidden")

    # ---------------- PUBLIC SHARE PAGE ----------------
    section("PUBLIC SHARE PAGE")
    anon = browser.new_context()
    anon_page = anon.new_page()
    anon_page.set_default_navigation_timeout(60000)
    anon_errors = []
    anon_page.on("pageerror", lambda e: anon_errors.append(str(e)))

    anon_page.goto(link, wait_until="domcontentloaded")
    anon_page.wait_for_selector("#shareContent:not(.is-hidden)")
    check("anonymous visitor sees the file", "notes.txt" in anon_page.inner_text("#shareContent"))
    check("owner shown", "UI Tester" in anon_page.inner_text("#shareContent"))
    check("no JS errors on the share page", not anon_errors, str(anon_errors))
    anon_page.screenshot(path=str(SHOTS / "11-public-share.png"))

    anon_page.goto(f"{BASE}/share.html?token=deadbeef", wait_until="domcontentloaded")
    anon_page.wait_for_selector(".empty-state")
    check("bad token shows a clean empty state, not a traceback",
          "not found" in anon_page.inner_text(".empty-state").lower(),
          anon_page.inner_text(".empty-state"))
    anon.close()

    # ---------------- TRASH ----------------
    section("TRASH")
    goto(f"{BASE}/files.html")
    page.wait_for_selector(".file-card")
    page.locator(".file-card", has_text="sheet.csv").locator(".dot-btn").click()
    page.click(".app-menu.show .dropdown-item:has-text('Move to Trash')")
    page.wait_for_selector(".modal.show")
    check("trashing asks for confirmation first",
          "Move to Trash" in page.inner_text(".modal.show"))
    page.click(".modal.show .btn-app-danger")
    page.wait_for_function("document.querySelectorAll('.file-card').length === 2")
    check("file disappears from My Files", True)

    goto(f"{BASE}/trash.html")
    page.wait_for_selector(".app-table tbody tr")
    check("trash lists the deleted file",
          page.locator(".app-table tbody tr", has_text="sheet.csv").count() == 1)
    headers = [h.strip().lower() for h in page.locator(".app-table thead th").all_inner_texts()]
    check("trash shows deleted + auto-delete columns",
          "deleted" in headers and "auto delete" in headers, str(headers))
    check("auto-delete date rendered as a badge",
          page.locator(".app-table .badge-soft").count() >= 1)
    page.screenshot(path=str(SHOTS / "12-trash.png"), full_page=True)

    page.click(".app-table tbody tr .btn-app-ghost")
    page.wait_for_selector(".app-toast.is-success")
    page.wait_for_selector(".empty-state")
    check("restore empties the trash and shows an empty state", True)

    # empty-trash confirmation
    goto(f"{BASE}/files.html")
    page.wait_for_selector(".file-card")
    page.locator(".file-card", has_text="sheet.csv").locator(".dot-btn").click()
    page.click(".app-menu.show .dropdown-item:has-text('Move to Trash')")
    page.wait_for_selector(".modal.show .btn-app-danger")
    page.click(".modal.show .btn-app-danger")
    page.wait_for_selector(".app-toast.is-success")

    goto(f"{BASE}/trash.html")
    page.wait_for_selector(".app-table tbody tr")
    page.click("#emptyTrashBtn")
    page.wait_for_selector(".modal.show")
    check("Empty Trash asks for confirmation",
          "permanently" in page.inner_text(".modal.show").lower())
    page.click(".modal.show .btn-app-danger")
    page.wait_for_selector(".empty-state")
    check("empty trash clears the list", page.is_visible(".empty-state"))

    # ---------------- ACTIVITY ----------------
    section("ACTIVITY")
    goto(f"{BASE}/activity.html")
    page.wait_for_selector(".timeline-item")
    check("timeline populated", page.locator(".timeline-item").count() > 5)
    check("day headings present", page.locator(".timeline-day").count() >= 1)
    check("filter chips rendered", page.locator("#activityFilters .chip").count() == 7)

    page.click("#activityFilters .chip:has-text('Uploads')")
    page.wait_for_timeout(300)
    texts = page.locator(".timeline-item .tl-text").all_inner_texts()
    check("upload filter narrows the timeline",
          len(texts) > 0 and all("Uploaded" in t for t in texts), str(texts[:3]))
    page.screenshot(path=str(SHOTS / "13-activity.png"), full_page=True)
    page.click("#activityFilters .chip:has-text('All')")

    # ---------------- STORAGE ----------------
    section("STORAGE")
    goto(f"{BASE}/storage.html")
    page.wait_for_selector(".storage-ring svg")
    check("storage ring rendered", page.locator(".ring-pct").count() == 1)
    check("headline uses real figures",
          "of 25.0 GB" in page.inner_text("#storageHero"),
          page.inner_text("#storageHero")[:150])
    page.wait_for_selector(".breakdown-row")
    check("breakdown by type computed from real files",
          page.locator(".breakdown-row").count() >= 2)
    check("largest-files table populated",
          page.locator("#largestHost .app-table tbody tr").count() >= 2)
    page.screenshot(path=str(SHOTS / "14-storage.png"), full_page=True)

    # ---------------- SETTINGS + DARK MODE ----------------
    section("SETTINGS + DARK MODE")
    goto(f"{BASE}/settings.html")
    page.wait_for_selector(".theme-choice")
    check("three theme choices", page.locator(".theme-choice").count() == 3)
    # The General panel renders after GET /api/settings resolves.
    page.wait_for_selector("#notificationsToggle")
    check("notification switch rendered", page.is_visible("#notificationsToggle"))
    check("language select rendered", page.is_visible("#languageSelect"))
    check("password form rendered", page.is_visible("#passwordForm"))

    page.click(".theme-choice:has-text('Dark') .tc-box")
    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    check("dark mode applied", page.get_attribute("html", "data-theme") == "dark")
    page.wait_for_selector(".app-toast.is-success")
    page.screenshot(path=str(SHOTS / "15-settings-dark.png"), full_page=True)

    goto(f"{BASE}/dashboard.html")
    page.wait_for_selector(".stat")
    check("dark mode persists across pages",
          page.get_attribute("html", "data-theme") == "dark")
    page.screenshot(path=str(SHOTS / "16-dashboard-dark.png"), full_page=True)

    # verify it was stored server-side, not only locally
    stored_theme = page.evaluate("""async () => {
        const r = await fetch('/api/settings', {
            headers: { Authorization: 'Bearer ' + localStorage.getItem('Cloud_token') }
        });
        return (await r.json()).theme;
    }""")
    check("theme persisted to the account, not just localStorage",
          stored_theme == "dark", str(stored_theme))

    # language round trip
    goto(f"{BASE}/settings.html")
    page.wait_for_selector("#languageSelect")
    page.select_option("#languageSelect", "Hindi")
    page.wait_for_selector(".app-toast.is-success")
    stored_lang = page.evaluate("""async () => {
        const r = await fetch('/api/settings', {
            headers: { Authorization: 'Bearer ' + localStorage.getItem('Cloud_token') }
        });
        return (await r.json()).language;
    }""")
    check("language persisted to the database", stored_lang == "Hindi", str(stored_lang))

    page.click(".theme-choice:has-text('Light') .tc-box")
    page.wait_for_function("document.documentElement.dataset.theme === 'light'")

    # ---------------- HEADER THEME TOGGLE ----------------
    section("HEADER TOGGLE + NOTIFICATIONS")
    page.click("#themeToggle")
    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    check("header quick-toggle flips the theme", True)
    page.click("#themeToggle")
    page.wait_for_function("document.documentElement.dataset.theme === 'light'")

    page.click("#notifBtn")
    page.wait_for_selector(".notif-menu.show")
    page.wait_for_selector(".notif-item, .notif-list .empty-state")
    check("notifications panel populated from real activity",
          page.locator(".notif-item").count() > 0)
    page.screenshot(path=str(SHOTS / "17-notifications.png"))
    page.click("#notifMarkAll")
    check("mark all read clears the unread state",
          page.locator(".notif-item.is-unread").count() == 0)
    page.keyboard.press("Escape")

    # ---------------- SEARCH ----------------
    section("GLOBAL SEARCH")
    goto(f"{BASE}/dashboard.html")
    page.wait_for_selector("#globalSearch")
    page.keyboard.press("Control+k")
    check("Ctrl+K focuses search",
          page.evaluate("document.activeElement.id") == "globalSearch")

    page.fill("#globalSearch", "report")
    page.wait_for_selector(".search-results.show .sr-item")
    check("search shows grouped results",
          page.locator(".sr-group-label").count() >= 1)
    check("search finds the file",
          page.locator(".sr-item", has_text="report.pdf").count() == 1)
    page.screenshot(path=str(SHOTS / "18-search.png"))

    page.keyboard.press("ArrowDown")
    check("arrow keys move the search cursor",
          page.locator(".sr-item.is-cursor").count() == 1)
    page.keyboard.press("Escape")
    check("Escape closes the results",
          page.locator(".search-results.show").count() == 0)

    # ---------------- PROFILE ----------------
    section("PROFILE")
    page.click("#sidebarUser")
    page.wait_for_selector("#profileModal.show")
    check("profile modal opens", page.is_visible("#profileModal"))
    check("profile shows the real email", page.inner_text("#profileEmailValue") == EMAIL)
    check("profile tabs present", page.locator(".profile-tabs button").count() == 3)

    page.click(".profile-tabs button:has-text('Storage')")
    check("storage tab shows live usage",
          "of" in page.inner_text("#profileStorageUsed"),
          page.inner_text("#profileStorageUsed"))

    page.click(".profile-tabs button:has-text('Security')")
    check("security tab has the password form", page.is_visible("#profilePasswordForm"))
    page.screenshot(path=str(SHOTS / "19-profile.png"))

    page.click(".profile-tabs button:has-text('Profile')")
    page.click("#profileEditBtn")
    page.wait_for_selector("#editProfileModal.show")
    page.fill("#editFullname", "UI Tester Renamed")
    page.click("#editProfileForm button[type=submit]")
    page.wait_for_function(
        "document.getElementById('sidebarUserName').textContent === 'UI Tester Renamed'")
    check("edit profile saves and re-renders the shell", True)

    # ---------------- MOBILE ----------------
    section("MOBILE 390x844")
    mob = browser.new_context(viewport={"width": 390, "height": 844},
                              is_mobile=True, has_touch=True)
    mp = mob.new_page()
    mp.set_default_navigation_timeout(60000)
    mob_errors = []
    mp.on("pageerror", lambda e: mob_errors.append(str(e)))

    mp.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
    check("auth brand panel hidden on mobile",
          mp.evaluate("getComputedStyle(document.querySelector('.auth-aside')).display") == "none")
    mp.screenshot(path=str(SHOTS / "20-mobile-login.png"))

    mp.fill("#identifier", USER)
    mp.fill("#password", PASS)
    mp.click("#loginSubmit")
    mp.wait_for_url("**/dashboard.html", timeout=30000, wait_until="domcontentloaded")
    mp.wait_for_selector(".stat")

    check("hamburger visible", mp.is_visible("#sidebarToggle"))
    right = mp.evaluate("document.getElementById('appSidebar').getBoundingClientRect().right")
    check("sidebar collapsed off-canvas", right <= 0, str(right))

    mp.click("#sidebarToggle")
    mp.wait_for_timeout(400)
    right = mp.evaluate("document.getElementById('appSidebar').getBoundingClientRect().right")
    check("hamburger opens the sidebar", right > 100, str(right))
    mp.screenshot(path=str(SHOTS / "21-mobile-sidebar.png"))

    mp.click(".nav-item:has-text('My Files')")
    mp.wait_for_url("**/files.html", wait_until="domcontentloaded")
    mp.wait_for_selector(".file-card, .empty-state")
    right = mp.evaluate("document.getElementById('appSidebar').getBoundingClientRect().right")
    check("navigating closes the sidebar", right <= 0, str(right))

    check("no horizontal overflow", mp.evaluate("document.body.scrollWidth") <= 392,
          str(mp.evaluate("document.body.scrollWidth")))
    cols = mp.evaluate(
        "getComputedStyle(document.querySelector('.file-grid')).gridTemplateColumns.split(' ').length")
    check("file grid is single column at 390px", cols == 1, str(cols))

    mp.set_viewport_size({"width": 480, "height": 844})
    mp.wait_for_timeout(250)
    cols = mp.evaluate(
        "getComputedStyle(document.querySelector('.file-grid')).gridTemplateColumns.split(' ').length")
    check("file grid is two columns at 480px", cols == 2, str(cols))
    mp.set_viewport_size({"width": 390, "height": 844})
    mp.screenshot(path=str(SHOTS / "22-mobile-files.png"), full_page=True)

    # action menu must not be clipped on mobile
    mp.locator(".file-card").first.locator(".dot-btn").click()
    mp.wait_for_selector(".app-menu.show")
    box = mp.evaluate("""() => {
        const r = document.querySelector('.app-menu.show').getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    }""")
    check("action menu stays inside the viewport",
          box["left"] >= 0 and box["right"] <= 390 and box["top"] >= 0 and box["bottom"] <= 844,
          str(box))
    mp.keyboard.press("Escape")

    for path in ["dashboard", "shared", "trash", "activity", "storage", "settings"]:
        mp.goto(f"{BASE}/{path}.html", wait_until="domcontentloaded")
        mp.wait_for_selector(".app-content *")
        mp.wait_for_timeout(500)
        width = mp.evaluate("document.body.scrollWidth")
        check(f"{path} has no horizontal overflow on mobile", width <= 392, str(width))

    check("no JS errors on mobile", not mob_errors, str(mob_errors))
    mob.close()

    # ---------------- TABLET ----------------
    section("TABLET 768x1024")
    tab = browser.new_context(viewport={"width": 768, "height": 1024})
    tp = tab.new_page()
    tp.set_default_navigation_timeout(60000)
    tp.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
    tp.fill("#identifier", USER)
    tp.fill("#password", PASS)
    tp.click("#loginSubmit")
    tp.wait_for_url("**/dashboard.html", timeout=30000, wait_until="domcontentloaded")
    tp.wait_for_selector(".stat")
    check("tablet: stats reflow to two columns",
          tp.evaluate("getComputedStyle(document.querySelector('.stat-grid'))"
                      ".gridTemplateColumns.split(' ').length") == 2)
    check("tablet: no horizontal overflow",
          tp.evaluate("document.body.scrollWidth") <= 770)
    tp.screenshot(path=str(SHOTS / "23-tablet.png"), full_page=True)
    tab.close()

    # ---------------- ACCESSIBILITY ----------------
    section("ACCESSIBILITY")
    goto(f"{BASE}/files.html")
    page.wait_for_selector(".file-card")
    check("skip link present", page.locator("a.visually-hidden-focusable").count() == 1)
    check("every icon button has an accessible name", page.evaluate("""() => {
        return [...document.querySelectorAll('button')].every(b =>
            (b.textContent || '').trim() || b.getAttribute('aria-label'));
    }"""))
    check("search input is labelled",
          bool(page.get_attribute("#globalSearch", "aria-label")))
    check("nav landmarks present",
          page.locator("aside[aria-label]").count() >= 1
          and page.locator("main#mainContent").count() == 1)

    page.locator(".file-card").first.focus()
    check("file cards are keyboard focusable",
          page.evaluate("document.activeElement.classList.contains('file-card')"))

    # ---------------- LOGOUT + GUARD ----------------
    section("LOGOUT + GUARD")
    page.click("#headerProfileBtn")
    page.wait_for_selector(".dropdown-menu.show")
    page.click("#menuLogout")
    page.wait_for_selector(".modal.show")
    check("logout asks for confirmation", "Log out" in page.inner_text(".modal.show"))
    page.click(".modal.show .btn-app-primary")
    page.wait_for_url("**/login.html", timeout=30000, wait_until="domcontentloaded")
    check("logout returns to sign in", "login.html" in page.url)

    goto(f"{BASE}/files.html")
    page.wait_for_url("**/login.html*", timeout=30000, wait_until="domcontentloaded")
    check("signed-out users are redirected off app pages", "login.html" in page.url, page.url)
    check("redirect remembers where you were going", "next=files.html" in page.url, page.url)

    ignore_console_from = len(console_errors)
    page.fill("#identifier", USER)
    page.fill("#password", "wrong-password")
    page.click("#loginSubmit")
    page.wait_for_selector("#passwordError:not(.is-hidden)")
    check("wrong password shows an inline field error, not an alert()",
          "Invalid" in page.inner_text("#passwordError"), page.inner_text("#passwordError"))
    page.screenshot(path=str(SHOTS / "24-login-error.png"))

    browser.close()


with sync_playwright() as pw:
    run(pw)

section("CONSOLE")
real_console = [
    e for i, e in enumerate(console_errors)
    if "favicon" not in e.lower()
    and not (ignore_console_from is not None and i >= ignore_console_from and "401" in e)
]
check("no uncaught JS errors", not page_errors, str(page_errors[:3]))
check("no console errors", not real_console, str(real_console[:3]))

print(f"\n=========== {ok} passed, {bad} failed ===========")
print(f"screenshots: {SHOTS}")
sys.exit(1 if bad else 0)
