/* =========================================================================
   PUBLIC SHARE PAGE
   Anonymous landing page for /share.html?token=… — no session required.
   Handles the password gate and reports expired or missing links plainly.

   One token can point at either a single file or a whole folder. A folder
   link turns this page into a small read-only browser: the visitor walks the
   same structure the owner built, downloads any file in it, or takes the
   whole thing as a .zip.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var token = new URLSearchParams(location.search).get("token") || "";
    var stateBox = document.getElementById("shareState");
    var content = document.getElementById("shareContent");

    var info = null;

    /** Held in memory only, and only for the current visit. */
    var password = null;


    function showState(node) {
        UI.fill(stateBox, node);
        stateBox.classList.remove("is-hidden");
        content.classList.add("is-hidden");
    }

    function showContent() {
        stateBox.classList.add("is-hidden");
        content.classList.remove("is-hidden");
    }

    function showError(title, message, iconName) {
        showState(UI.emptyState({
            icon: iconName || "exclamation-triangle",
            title: title,
            message: message
        }));
    }

    function reportLinkError(err) {
        if (err.status === 410) {
            showError(
                "This link has expired",
                "Ask the person who shared it to send you a new one.",
                "hourglass-bottom"
            );
        } else if (err.status === 404) {
            showError(
                "Link not found",
                "The link may have been revoked, or the item is no longer available.",
                "link-45deg"
            );
        } else {
            showError("Something went wrong", err.message);
        }
    }


    async function load() {
        if (!token) {
            showError("Link is incomplete", "This share link is missing its token.", "link-45deg");
            return;
        }

        try {
            info = await API.shares.publicInfo(token);
        } catch (err) {
            reportLinkError(err);
            return;
        }

        document.title = info.file_name + " · Cloud";

        if (info.kind === "folder") {
            renderFolder();
        } else {
            renderFile();
        }
    }


    /* ---------------------------------------------------------------------
       Shared header
       ------------------------------------------------------------------ */

    function heading(host) {
        if (info.kind === "folder") {
            host.appendChild(UI.folderChip("lg"));
        } else {
            host.appendChild(UI.typeChip(info.file_name, info.file_type, "lg"));
        }

        host.appendChild(el("h1", null, info.file_name));

        var meta = el("p", "sp-meta");

        var summary = info.kind === "folder"
            ? info.item_count + (info.item_count === 1 ? " file" : " files") +
                (info.folder_count
                    ? " in " + info.folder_count + (info.folder_count === 1 ? " folder" : " folders")
                    : "") +
                " · " + UI.formatSize(info.file_size)
            : UI.typeLabel(info.file_name, info.file_type) + " · " + UI.formatSize(info.file_size);

        meta.appendChild(document.createTextNode(summary));
        meta.appendChild(document.createElement("br"));
        meta.appendChild(document.createTextNode("Shared by " + info.shared_by_name));

        if (info.expiry_date) {
            meta.appendChild(document.createElement("br"));
            meta.appendChild(document.createTextNode("Expires " + UI.formatDate(info.expiry_date)));
        }
        host.appendChild(meta);
    }

    /** The password field, returned so the caller can read and focus it. */
    function passwordField(host) {
        var lock = el("div", "badge-soft is-warning");
        lock.appendChild(icon("shield-lock-fill"));
        lock.appendChild(el("span", null, "Password protected"));
        lock.style.marginBottom = "14px";
        host.appendChild(lock);

        var field = el("div", "field");
        var label = el("label", "visually-hidden", "Link password");
        label.htmlFor = "sharePasswordInput";

        var input = document.createElement("input");
        input.type = "password";
        input.id = "sharePasswordInput";
        input.placeholder = "Enter the link password";
        input.autocomplete = "off";
        input.setAttribute("aria-label", "Link password");

        field.appendChild(label);
        field.appendChild(input);
        host.appendChild(field);

        return input;
    }


    /* ---------------------------------------------------------------------
       A single shared file
       ------------------------------------------------------------------ */

    function renderFile() {
        UI.clear(content);
        heading(content);

        var input = info.requires_password ? passwordField(content) : null;

        var button = el("button", "btn-app-primary btn-block");
        button.type = "button";
        button.id = "shareDownloadBtn";
        button.appendChild(icon("download"));
        button.appendChild(el("span", null, "Download"));
        content.appendChild(button);

        async function download() {
            var value = null;

            if (info.requires_password) {
                value = input.value;
                if (!value) {
                    UI.toast("Enter the link password", "error");
                    input.focus();
                    return;
                }
            }

            button.disabled = true;

            try {
                if (value) {
                    // Verified first so a wrong password gives a clean message
                    // instead of a broken download.
                    await API.shares.verify(token, value);
                }

                UI.toast("Starting download…", "success");
                location.href = API.shares.publicDownloadUrl(token, value);
            } catch (err) {
                if (err.status === 401) {
                    UI.toast("Incorrect password", "error");
                    input.value = "";
                    input.focus();
                } else if (err.status === 410) {
                    showError("This link has expired",
                        "Ask the person who shared it to send you a new one.",
                        "hourglass-bottom");
                } else {
                    UI.toast(err.message, "error", 5000);
                }
            } finally {
                button.disabled = false;
            }
        }

        button.addEventListener("click", download);

        if (input) {
            input.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    e.preventDefault();
                    download();
                }
            });
        }

        showContent();
    }


    /* ---------------------------------------------------------------------
       A shared folder
       ------------------------------------------------------------------ */

    function renderFolder() {
        if (info.requires_password && password === null) {
            renderFolderGate();
            return;
        }
        openPath("");
    }

    /** A folder listing needs the password up front, so ask before browsing. */
    function renderFolderGate() {
        UI.clear(content);
        heading(content);

        var input = passwordField(content);

        var button = el("button", "btn-app-primary btn-block");
        button.type = "button";
        button.appendChild(icon("unlock"));
        button.appendChild(el("span", null, "Open folder"));
        content.appendChild(button);

        async function unlock() {
            if (!input.value) {
                UI.toast("Enter the link password", "error");
                input.focus();
                return;
            }

            button.disabled = true;
            try {
                await API.shares.verify(token, input.value);
                password = input.value;
                openPath("");
            } catch (err) {
                if (err.status === 401) {
                    UI.toast("Incorrect password", "error");
                    input.value = "";
                    input.focus();
                } else {
                    reportLinkError(err);
                }
            } finally {
                button.disabled = false;
            }
        }

        button.addEventListener("click", unlock);
        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter") { e.preventDefault(); unlock(); }
        });

        showContent();
        input.focus();
    }

    async function openPath(path) {
        var listing;
        try {
            listing = await API.shares.publicList(token, path, password);
        } catch (err) {
            if (err.status === 401) {
                // The password was cleared or the link was re-protected.
                password = null;
                renderFolderGate();
                return;
            }
            reportLinkError(err);
            return;
        }

        renderListing(listing);
    }

    function renderListing(listing) {
        UI.clear(content);

        // A listing needs more room than a single-file card, and reads far
        // better left-aligned.
        var card = content.closest(".share-card");
        if (card) { card.classList.add("is-browsing"); }

        heading(content);

        // ---- Breadcrumb ------------------------------------------------
        // At the root the heading already carries the folder name, so a
        // one-item trail would only repeat it.
        var crumbs = el("nav", "app-breadcrumb sp-crumbs");
        crumbs.setAttribute("aria-label", "Folder path");
        crumbs.classList.toggle("is-hidden", !listing.breadcrumb.length);

        var root = el("button", "crumb", info.file_name);
        root.type = "button";
        root.addEventListener("click", function () { openPath(""); });
        crumbs.appendChild(root);

        listing.breadcrumb.forEach(function (name, index) {
            var sep = el("span", "sep");
            sep.appendChild(icon("chevron-right"));
            crumbs.appendChild(sep);

            var last = index === listing.breadcrumb.length - 1;
            var node = el("button", "crumb", name);
            node.type = "button";
            node.title = name;

            if (last) {
                node.setAttribute("aria-current", "page");
            } else {
                var target = listing.breadcrumb.slice(0, index + 1).join("/");
                node.addEventListener("click", function () { openPath(target); });
            }
            crumbs.appendChild(node);
        });

        content.appendChild(crumbs);

        // ---- Download the whole thing ----------------------------------
        var zip = el("button", "btn-app-primary btn-block");
        zip.type = "button";
        zip.appendChild(icon("file-earmark-zip"));
        zip.appendChild(el("span", null,
            listing.path ? "Download this folder as ZIP" : "Download everything as ZIP"));
        zip.addEventListener("click", function () {
            UI.toast("Preparing the archive…", "success");
            location.href = API.shares.publicZipUrl(token, listing.path, password);
        });
        content.appendChild(zip);

        // ---- Entries ---------------------------------------------------
        var list = el("div", "share-entries");

        if (!listing.entries.length) {
            list.appendChild(el("p", "text-meta", "This folder is empty."));
        }

        listing.entries.forEach(function (entry) {
            list.appendChild(
                entry.kind === "folder" ? folderEntry(entry) : fileEntry(entry)
            );
        });

        content.appendChild(list);
        showContent();
    }

    function entryShell(iconNode, name, meta) {
        var row = el("button", "share-entry");
        row.type = "button";

        row.appendChild(iconNode);

        var body = el("div", "se-body");
        var title = el("div", "se-name", name);
        title.title = name;
        body.appendChild(title);
        body.appendChild(el("div", "se-meta", meta));
        row.appendChild(body);

        return row;
    }

    function folderEntry(entry) {
        var row = entryShell(
            UI.folderChip("sm"),
            entry.name,
            entry.item_count + (entry.item_count === 1 ? " file" : " files")
        );
        row.appendChild(icon("chevron-right", "se-go"));
        row.setAttribute("aria-label", "Open folder " + entry.name);
        row.addEventListener("click", function () { openPath(entry.path); });
        return row;
    }

    function fileEntry(entry) {
        var row = entryShell(
            UI.typeChip(entry.name, entry.file_type, "sm"),
            entry.name,
            UI.formatSize(entry.file_size) + " · " + UI.timeAgo(entry.updated_at)
        );
        row.appendChild(icon("download", "se-go"));
        row.setAttribute("aria-label", "Download " + entry.name);
        
        row.addEventListener("dblclick", function () {
            // Double-click to open Word/Excel files in same tab
            if (entry.file_kind === "word" || /\.docx$/i.test(entry.name)) {
                var viewUrl = "editor.html?id=" + entry.file_id + "&type=word&shared=" + encodeURIComponent(token);
                if (password) { viewUrl += "&password=" + encodeURIComponent(password); }
                location.href = viewUrl;
            } else if (entry.file_kind === "excel" || /\.xlsx$/i.test(entry.name)) {
                var viewUrl = "editor.html?id=" + entry.file_id + "&type=excel&shared=" + encodeURIComponent(token);
                if (password) { viewUrl += "&password=" + encodeURIComponent(password); }
                location.href = viewUrl;
            } else {
                // For other files, show unsupported message
                UI.toast("This file type is not supported for opening in the editor", "warning");
            }
        });
        
        row.addEventListener("click", function () {
            UI.toast("Downloading " + entry.name, "success");
            location.href = API.shares.publicDownloadUrl(token, password, entry.file_id);
        });
        return row;
    }


    load();
}());
