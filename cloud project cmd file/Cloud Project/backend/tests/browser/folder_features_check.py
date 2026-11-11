"""Real-browser check of folder upload, multi-select, clipboard and folder sharing.

Run the server first, then:  python tests/browser/folder_features_check.py
Registers a fresh account each run, so it is safe to re-run.

Pass a different origin as argv[1] (default http://127.0.0.1:8000).
"""
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
HERE = Path(__file__).parent
SHOTS = HERE / "shots"
SHOTS.mkdir(exist_ok=True)

STAMP = str(int(time.time()))
USER = "foldertest" + STAMP
PASS = "FolderTest@1234"

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


def build_tree() -> Path:
    """A folder three levels deep, with files at every level."""
    root = HERE / ("tree-" + STAMP)
    shutil.rmtree(root, ignore_errors=True)

    (root / "assets" / "icons").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)

    (root / "readme.txt").write_text("top level readme")
    (root / "assets" / "logo.txt").write_text("logo bytes")
    (root / "assets" / "icons" / "home.txt").write_text("home icon")
    (root / "docs" / "spec.txt").write_text("the spec")
    return root


def register(page):
    page.goto(f"{BASE}/register.html")
    page.fill("#fullname", "Folder Tester")
    page.fill("#username", USER)
    page.fill("#email", USER + "@example.com")
    page.fill("#password", PASS)
    page.fill("#confirm", PASS)
    page.click("button[type=submit]")
    page.wait_for_url("**/dashboard.html", timeout=30000)


def open_files(page, folder_id=None):
    url = f"{BASE}/files.html" + (f"?folder={folder_id}" if folder_id else "")
    page.goto(url)
    page.wait_for_selector("#fileHost", timeout=20000)
    page.wait_for_timeout(900)


def folder_named(page, name):
    return page.locator(".folder-card", has=page.locator(".fc-name", has_text=name)).first


def open_folder(page, name):
    folder_named(page, name).click()
    page.wait_for_timeout(1100)


def crumbs(page):
    return [c.strip() for c in page.locator("#breadcrumb .crumb").all_inner_texts()]


def names_on_page(page):
    folders = [n.strip() for n in page.locator(".folder-card .fc-name").all_inner_texts()]
    files = [n.strip() for n in page.locator(".file-card .fc-name").all_inner_texts()]
    return folders, files


def wait_for_card(page, name, timeout=60000):
    """Wait for a named card to show up in the current listing.

    A paste duplicates a whole subtree server-side, so how long it takes depends
    on what else the machine is doing - a fixed pause is a coin toss, and
    reloading instead would cancel the request that is still in flight. The page
    re-renders itself when the paste finishes, so wait on that.
    """
    page.wait_for_selector(f".fc-name:text-is('{name}')", timeout=timeout)
    page.wait_for_timeout(300)



DROP_SCRIPT = """
() => {
    // Minimal stand-ins for the FileSystemEntry objects a real folder drop
    // hands over. The uploader only ever touches these members.
    function fileEntry(name, text) {
        return {
            isFile: true,
            isDirectory: false,
            name: name,
            file: function (cb) { cb(new File([text], name, { type: "text/plain" })); }
        };
    }

    function dirEntry(name, children) {
        return {
            isFile: false,
            isDirectory: true,
            name: name,
            createReader: function () {
                // Real readers hand back children in batches and signal the end
                // with an empty one, so split the children to prove the loop
                // drains properly instead of reading once.
                var batches = children.length > 1
                    ? [children.slice(0, 1), children.slice(1), []]
                    : [children, []];
                var index = 0;
                return {
                    readEntries: function (cb) { cb(batches[index++] || []); }
                };
            }
        };
    }

    var tree = dirEntry("Dropped", [
        fileEntry("root.txt", "root"),
        dirEntry("nested", [
            fileEntry("inner.txt", "inner"),
            dirEntry("deeper", [fileEntry("bottom.txt", "bottom")])
        ]),
        dirEntry("empty", [])
    ]);

    var transfer = {
        types: ["Files"],
        files: [],
        items: [{ kind: "file", webkitGetAsEntry: function () { return tree; } }]
    };

    var event = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: transfer });
    window.dispatchEvent(event);
}
"""


def run(pw):
    tree = build_tree()

    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.set_default_timeout(20000)
    page.on("pageerror", lambda e: page_errors.append(f"{page.url}: {e}"))

    section("Sign up")
    register(page)
    check("registered and landed on the dashboard", "/dashboard.html" in page.url)

    # ------------------------------------------------------------ empty state
    section("Select-all with an empty folder")
    open_files(page)

    check("select-all is disabled when there is nothing to select",
          not page.is_enabled("#selectAll"))
    check("and the control says so rather than looking broken",
          "Nothing here to select" in
          (page.get_attribute(".select-all-control", "title") or ""),
          page.get_attribute(".select-all-control", "title"))

    # ---------------------------------------------------------------- upload
    section("Upload a whole folder")
    page.evaluate("Upload.init()")
    page.set_input_files("#uploadFolderInput", str(tree))

    # Four files, each one row, plus the folder-creation round trip.
    page.wait_for_selector("#uploadPanel.show", timeout=20000)
    page.wait_for_function(
        "document.querySelectorAll('#uploadList .ui-status.ok').length >= 4", timeout=60000
    )
    check("all four files reported as uploaded", True)

    paths = sorted(p.strip() for p in page.locator("#uploadList .ui-path").all_inner_texts())
    check(
        "queue rows show the folder each file came from",
        paths == sorted([tree.name, f"{tree.name}/assets", f"{tree.name}/assets/icons", f"{tree.name}/docs"]),
        paths,
    )
    page.screenshot(path=str(SHOTS / "folder-upload-panel.png"))

    # ------------------------------------------------------------- structure
    section("The tree survived the upload")
    open_files(page)

    folders, _ = names_on_page(page)
    check("the uploaded folder is at the root", tree.name in folders, folders)

    open_folder(page, tree.name)
    folders, files = names_on_page(page)
    check("level 1 holds its two subfolders", sorted(folders) == ["assets", "docs"], folders)
    check("level 1 holds its own file", files == ["readme.txt"], files)
    check("breadcrumb names the folder", crumbs(page) == ["My Files", tree.name], crumbs(page))

    open_folder(page, "assets")
    folders, files = names_on_page(page)
    check("level 2 holds the nested folder", folders == ["icons"], folders)
    check("level 2 holds its own file", files == ["logo.txt"], files)

    open_folder(page, "icons")
    folders, files = names_on_page(page)
    check("level 3 holds the deepest file", files == ["home.txt"], files)
    check(
        "breadcrumb shows the full path",
        crumbs(page) == ["My Files", tree.name, "assets", "icons"],
        crumbs(page),
    )
    page.screenshot(path=str(SHOTS / "folder-nested-path.png"))

    # ------------------------------------------------------------- selection
    section("Select all, then copy and paste")
    open_files(page)
    open_folder(page, tree.name)

    check("select-all is live once the folder has contents",
          page.is_enabled("#selectAll"))

    page.check("#selectAll")
    page.wait_for_timeout(400)

    check("checking it really does stay checked", page.is_checked("#selectAll"))
    check("the selection bar appeared", page.locator("#selectionBar.show").is_visible())
    label = page.locator("#selectionBar .sel-count").inner_text()
    check("it counts 2 folders and 1 file", "2 folders" in label and "1 file" in label, label)
    check(
        "every card is marked selected",
        page.locator(".folder-card.is-selected").count() == 2
        and page.locator(".file-card.is-selected").count() == 1,
    )
    page.screenshot(path=str(SHOTS / "folder-selection-bar.png"))

    page.click("#selectionBar .sel-action:has-text('Copy')")
    page.wait_for_timeout(600)

    open_files(page)
    check("the paste button offers the clipboard", page.locator("#pasteBtn").is_visible())

    page.click("#pasteBtn")
    wait_for_card(page, "readme.txt")

    folders, files = names_on_page(page)
    check("pasted folders landed at the root", "assets" in folders and "docs" in folders, folders)
    check("the pasted file landed at the root", "readme.txt" in files, files)
    check("the originals are still in place", tree.name in folders, folders)

    open_folder(page, "assets")
    folders, files = names_on_page(page)
    check("a pasted folder brought its subtree", folders == ["icons"] and files == ["logo.txt"],
          (folders, files))
    page.screenshot(path=str(SHOTS / "folder-pasted.png"))

    # ------------------------------------------------------------------ cut
    section("Cut and paste moves instead of copying")
    open_files(page)
    page.locator(".folder-card", has=page.locator(".fc-name", has_text="docs")).first \
        .locator(".dot-btn").click()
    page.wait_for_timeout(300)
    page.click(".app-menu.show button:has-text('Cut')")
    page.wait_for_timeout(500)

    open_folder(page, tree.name)
    page.click("#pasteBtn")

    # "docs" arriving here is what tells us the move finished.
    wait_for_card(page, "docs")

    open_files(page)
    folders, _ = names_on_page(page)
    check("the cut folder left the root", "docs" not in folders, folders)

    open_folder(page, tree.name)
    folders, _ = names_on_page(page)
    check("the cut folder arrived in the target", "docs" in folders, folders)

    # --------------------------------------------------------- dropped folder
    section("Dropping a folder keeps its structure too")
    open_files(page)

    page.evaluate(DROP_SCRIPT)
    page.wait_for_selector("#uploadPanel.show", timeout=20000)
    page.wait_for_function(
        "document.querySelectorAll('#uploadList .ui-status.ok').length >= 3", timeout=60000
    )

    dropped = sorted(p.strip() for p in page.locator("#uploadList .ui-path").all_inner_texts())
    check(
        "the drop was walked to the bottom",
        dropped == ["Dropped", "Dropped/nested", "Dropped/nested/deeper"],
        dropped,
    )

    open_files(page)
    open_folder(page, "Dropped")
    folders, files = names_on_page(page)
    check(
        "a dropped folder keeps its subfolders, empty ones included",
        sorted(folders) == ["empty", "nested"],
        folders,
    )
    check("and its own files", files == ["root.txt"], files)

    open_folder(page, "nested")
    folders, files = names_on_page(page)
    check("the second dropped level is intact", folders == ["deeper"] and files == ["inner.txt"],
          (folders, files))

    open_folder(page, "deeper")
    _, files = names_on_page(page)
    check("and the third", files == ["bottom.txt"], files)

    # --------------------------------------------------------------- sharing
    section("Share a folder as a public link")
    open_files(page)
    folder_named(page, tree.name).locator(".dot-btn").click()
    page.wait_for_timeout(300)
    page.click(".app-menu.show button:has-text('Share')")

    page.wait_for_selector("#shareModal.show", timeout=15000)
    title = page.locator("#shareModalTitle").inner_text()
    check("the share modal names the folder", tree.name in title, title)

    page.click("#shareLinkForm button[type=submit]")
    page.wait_for_selector("#shareLinkArea input", timeout=15000)
    link = page.locator("#shareLinkArea input").first.input_value()
    check("a public link was created", "share.html?token=" in link, link)
    page.screenshot(path=str(SHOTS / "folder-share-modal.png"))

    # ------------------------------------------------------- public browsing
    section("Browse the shared folder as an anonymous visitor")
    guest = ctx.browser.new_context(viewport={"width": 1100, "height": 900})
    visitor = guest.new_page()
    visitor.set_default_timeout(20000)
    visitor.on("pageerror", lambda e: page_errors.append(f"{visitor.url}: {e}"))

    token = link.split("token=")[1]
    visitor.goto(f"{BASE}/share.html?token={token}")
    visitor.wait_for_selector(".share-entries", timeout=20000)

    entries = [t.strip() for t in visitor.locator(".share-entry .se-name").all_inner_texts()]
    # "docs (2)" is the folder cut from the root a moment ago: a move that hits
    # a name clash is renamed, and deliberately not labelled a copy.
    check(
        "the link lists the folder's contents",
        sorted(entries) == ["assets", "docs", "docs (2)", "readme.txt"],
        entries,
    )
    visitor.screenshot(path=str(SHOTS / "folder-share-public.png"))

    visitor.locator(".share-entry", has_text="assets").first.click()
    visitor.wait_for_timeout(900)
    entries = [t.strip() for t in visitor.locator(".share-entry .se-name").all_inner_texts()]
    check("a visitor can walk into a subfolder", sorted(entries) == ["icons", "logo.txt"], entries)

    visitor.locator(".share-entry", has_text="icons").first.click()
    visitor.wait_for_timeout(900)
    entries = [t.strip() for t in visitor.locator(".share-entry .se-name").all_inner_texts()]
    check("and down to the deepest level", entries == ["home.txt"], entries)

    crumb_text = [c.strip() for c in visitor.locator(".sp-crumbs .crumb").all_inner_texts()]
    check("the public breadcrumb tracks the path", crumb_text == [tree.name, "assets", "icons"],
          crumb_text)
    visitor.screenshot(path=str(SHOTS / "folder-share-deep.png"))

    guest.close()
    browser.close()
    shutil.rmtree(tree, ignore_errors=True)


with sync_playwright() as pw:
    run(pw)

print(f"\n{ok} passed, {bad} failed")
if page_errors:
    print("\nPage errors:")
    for entry in page_errors:
        print("  " + entry)

sys.exit(1 if (bad or page_errors) else 0)
