/* =========================================================================
   BROWSE
   Shared controller for My Files, Recent and Starred. The three pages differ
   only in which query they run and whether folders are shown, so they share
   one grid/list renderer, one filter, one sort and one empty-state handler.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var VIEW_KEY = "Cloud_view";
    var SORT_KEY = "Cloud_sort";

    var mode = document.body.dataset.page;   // files | recent | starred

    var state = {
        view: "grid",
        sort: "modified-desc",
        folderId: null,
        breadcrumb: [],
        folders: [],
        files: [],
        filter: ""
    };

    var SORTS = [
        { key: "modified-desc", label: "Last modified" },
        { key: "modified-asc", label: "Oldest first" },
        { key: "name-asc", label: "Name (A–Z)" },
        { key: "name-desc", label: "Name (Z–A)" },
        { key: "size-desc", label: "Largest first" },
        { key: "size-asc", label: "Smallest first" }
    ];


    /* ---------------------------------------------------------------------
       Preferences
       ------------------------------------------------------------------ */

    function loadPrefs() {
        try {
            var view = localStorage.getItem(VIEW_KEY);
            if (view === "grid" || view === "list") { state.view = view; }

            var sort = localStorage.getItem(SORT_KEY);
            if (SORTS.some(function (s) { return s.key === sort; })) { state.sort = sort; }
        } catch (e) { /* storage blocked */ }
    }

    function savePref(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* storage blocked */ }
    }


    /* ---------------------------------------------------------------------
       Sorting + filtering
       ------------------------------------------------------------------ */

    function sortFiles(files) {
        var copy = files.slice();

        copy.sort(function (a, b) {
            switch (state.sort) {
                case "name-asc":
                    return a.original_name.localeCompare(b.original_name);
                case "name-desc":
                    return b.original_name.localeCompare(a.original_name);
                case "size-asc":
                    return a.file_size - b.file_size;
                case "size-desc":
                    return b.file_size - a.file_size;
                case "modified-asc":
                    return new Date(a.updated_at) - new Date(b.updated_at);
                default:
                    return new Date(b.updated_at) - new Date(a.updated_at);
            }
        });

        return copy;
    }

    function applyFilter(items, nameKey) {
        if (!state.filter) { return items; }
        var needle = state.filter.toLowerCase();
        return items.filter(function (item) {
            return String(item[nameKey]).toLowerCase().indexOf(needle) !== -1;
        });
    }


    /* ---------------------------------------------------------------------
       Rendering
       ------------------------------------------------------------------ */

    /**
     * Redraws folders and files together.
     *
     * Selection has to be rebuilt in one pass: the registry is what backs
     * shift-ranges and "select all", so rendering only half of the listing
     * would leave it describing a screen that no longer exists.
     */
    function renderAll() {
        Selection.configure({
            folderId: state.folderId,
            // Recent and Starred are views over folders, not a place, so there
            // is nowhere for a paste to land.
            canPaste: mode === "files"
        });

        renderFolders();
        renderFiles();

        Selection.reconcile();
    }

    function openFolder(id) {
        state.folderId = id;
        Shell.uploadFolderId = id;
        Selection.clear();

        var url = id ? ("files.html?folder=" + id) : "files.html";
        history.replaceState(null, "", url);

        load();
    }

    function renderBreadcrumb() {
        var host = document.getElementById("breadcrumb");
        if (!host) { return; }

        UI.clear(host);

        // At the root the page title already says "My Files"; a one-item
        // breadcrumb would just repeat it.
        host.classList.toggle("is-hidden", state.breadcrumb.length === 0);
        if (!state.breadcrumb.length) { return; }

        var root = el("button", "crumb", "My Files");
        root.type = "button";
        root.addEventListener("click", function () { openFolder(null); });
        host.appendChild(root);

        state.breadcrumb.forEach(function (crumb, index) {
            var sep = el("span", "sep");
            sep.appendChild(icon("chevron-right"));
            host.appendChild(sep);

            var last = index === state.breadcrumb.length - 1;
            var node = el("button", "crumb", crumb.folder_name);
            node.type = "button";
            node.title = crumb.folder_name;

            if (last) {
                node.setAttribute("aria-current", "page");
            } else {
                node.addEventListener("click", function () { openFolder(crumb.id); });
            }
            host.appendChild(node);
        });
    }

    function renderFolders() {
        var section = document.getElementById("foldersSection");
        var host = document.getElementById("folderHost");
        if (!section || !host) { return; }

        var folders = applyFilter(state.folders, "folder_name");
        folders.sort(function (a, b) { return a.folder_name.localeCompare(b.folder_name); });

        section.classList.toggle("is-hidden", folders.length === 0);
        UI.clear(host);
        if (!folders.length) { return; }

        var grid = el("div", "folder-grid");
        folders.forEach(function (folder) {
            grid.appendChild(Files.folderCard(folder, function () { openFolder(folder.id); }));
        });
        host.appendChild(grid);
    }

    function renderFiles() {
        var host = document.getElementById("fileHost");
        var heading = document.getElementById("filesHeading");
        var files = sortFiles(applyFilter(state.files, "original_name"));

        UI.clear(host);

        if (heading) {
            heading.textContent = files.length
                ? "Files (" + files.length + ")"
                : "Files";
        }

        if (!files.length) {
            host.appendChild(emptyForMode());
            return;
        }

        if (state.view === "list") {
            renderList(host, files);
        } else if (mode === "recent") {
            renderGroupedGrid(host, files);
        } else {
            renderGrid(host, files);
        }
    }

    function renderGrid(host, files) {
        var grid = el("div", "file-grid");
        files.forEach(function (file) { grid.appendChild(Files.fileCard(file)); });
        host.appendChild(grid);
    }

    /** Recent groups by Today / Yesterday / Earlier this week / Older. */
    function renderGroupedGrid(host, files) {
        var groups = {};
        files.forEach(function (file) {
            var bucket = UI.dayBucket(file.updated_at);
            (groups[bucket] = groups[bucket] || []).push(file);
        });

        UI.BUCKET_ORDER.forEach(function (bucket) {
            if (!groups[bucket]) { return; }

            var heading = el("div", "section-heading");
            heading.appendChild(el("h2", null, bucket));
            host.appendChild(heading);

            renderGrid(host, groups[bucket]);
        });
    }

    function renderList(host, files) {
        var headers = [
            { label: "Name", sortKey: "name" },
            { label: "Type" },
            { label: "Size", sortKey: "size" },
            { label: "Modified", sortKey: "modified" }
        ];

        if (mode !== "files") {
            headers.push({ label: "Location" });
        }
        headers.push({ label: "", className: "cell-actions" });

        var table = Files.fileTable(headers);

        var columns = ["type", "size", "modified"];
        if (mode !== "files") { columns.push("location"); }

        files.forEach(function (file) {
            table.tbody.appendChild(Files.fileRow(file, columns, {
                locationOf: function (item) {
                    return item.folder_id ? (folderNames[item.folder_id] || "Folder") : "My Files";
                }
            }));
        });

        // Header sorting
        table.thead.querySelectorAll(".sort-btn").forEach(function (button) {
            var key = button.dataset.sortKey;
            var active = state.sort.indexOf(key) === 0;

            if (active) {
                button.parentElement.setAttribute(
                    "aria-sort",
                    state.sort.indexOf("-asc") !== -1 ? "ascending" : "descending"
                );
                button.setAttribute("aria-sort", "true");
                UI.fill(button, [
                    document.createTextNode(button.textContent),
                    icon(state.sort.indexOf("-asc") !== -1 ? "arrow-up" : "arrow-down")
                ]);
            }

            button.addEventListener("click", function () {
                var ascending = state.sort === key + "-asc";
                setSort(key + (ascending ? "-desc" : "-asc"));
            });
        });

        host.appendChild(table.wrap);
    }

    var folderNames = {};

    function emptyForMode() {
        if (state.filter) {
            return UI.emptyState({
                icon: "search",
                title: "No matches",
                message: 'Nothing here matches "' + state.filter + '".'
            });
        }

        if (mode === "starred") {
            return UI.emptyState({
                icon: "star",
                title: "No starred files",
                message: "Star a file from its actions menu and it will appear here for quick access."
            });
        }

        if (mode === "recent") {
            return UI.emptyState({
                icon: "clock-history",
                title: "Nothing recent",
                message: "Files you upload or change will show up here.",
                actionLabel: "Upload files",
                actionIcon: "upload",
                onAction: function () { Upload.pickFiles(); }
            });
        }

        return UI.emptyState({
            icon: "folder2-open",
            title: state.folderId ? "This folder is empty" : "No files yet",
            message: "Drag files or whole folders anywhere on this page, " +
                "or use the button below. Dropped folders keep their structure.",
            actionLabel: "Upload files",
            actionIcon: "upload",
            onAction: function () { Upload.pickFiles(); }
        });
    }


    /* ---------------------------------------------------------------------
       Data
       ------------------------------------------------------------------ */

    function showLoading() {
        var fileHost = document.getElementById("fileHost");
        if (state.view === "list") {
            var wrap = el("div", "table-wrap");
            UI.skeletonRows(6, wrap);
            UI.fill(fileHost, wrap);
        } else {
            var grid = el("div", "file-grid");
            UI.skeletonCards(8, grid);
            UI.fill(fileHost, grid);
        }

        var folderHost = document.getElementById("folderHost");
        if (folderHost) {
            var fgrid = el("div", "folder-grid");
            UI.skeletonCards(3, fgrid);
            UI.fill(folderHost, fgrid);
        }
    }

    async function load() {
        showLoading();

        try {
            if (mode === "files") {
                if (state.folderId === null) {
                    state.breadcrumb = [];
                    state.folders = await API.folders.list(null);
                    state.files = await API.files.list({ root_only: true });
                    setTitle("My Files");
                } else {
                    var contents = await API.folders.open(state.folderId);
                    state.breadcrumb = contents.breadcrumb;
                    state.folders = contents.folders;
                    state.files = contents.files;
                    setTitle(contents.folder.folder_name);
                }
                renderBreadcrumb();
            } else if (mode === "recent") {
                state.files = await API.files.list({ recent: true, root_only: false, limit: 100 });
                await cacheFolderNames();
            } else if (mode === "starred") {
                state.files = await API.files.list({ starred: true, root_only: false });
                await cacheFolderNames();
            }

            renderAll();
        } catch (err) {
            UI.reportError(err);

            var host = document.getElementById("fileHost");
            UI.fill(host, UI.emptyState({
                icon: "wifi-off",
                title: "Could not load this page",
                message: err.message
            }));
        }
    }

    /** Recent and Starred show a Location column, so resolve folder names once. */
    async function cacheFolderNames() {
        if (Object.keys(folderNames).length) { return; }
        try {
            var all = await API.folders.listAll();
            all.forEach(function (folder) { folderNames[folder.id] = folder.folder_name; });
        } catch (e) { /* the column falls back to "Folder" */ }
    }

    function setTitle(text) {
        var node = document.getElementById("pageTitle");
        if (node) { node.textContent = text; }
        document.title = text + " · Cloud";
    }


    /* ---------------------------------------------------------------------
       Controls
       ------------------------------------------------------------------ */

    function setView(view) {
        state.view = view;
        savePref(VIEW_KEY, view);

        var grid = document.getElementById("viewGrid");
        var list = document.getElementById("viewList");
        if (grid) { grid.setAttribute("aria-pressed", String(view === "grid")); }
        if (list) { list.setAttribute("aria-pressed", String(view === "list")); }

        renderAll();
    }

    function setSort(sort) {
        state.sort = sort;
        savePref(SORT_KEY, sort);

        var label = document.getElementById("sortLabel");
        if (label) {
            var match = SORTS.filter(function (s) { return s.key === sort; })[0];
            label.textContent = match ? match.label : "Sort";
        }

        renderAll();
    }

    function buildSortMenu() {
        var menu = document.getElementById("sortMenu");
        if (!menu) { return; }

        UI.clear(menu);

        SORTS.forEach(function (spec) {
            var li = document.createElement("li");
            var button = el("button", "dropdown-item");
            button.type = "button";
            button.appendChild(icon(spec.key === state.sort ? "check2" : "dash"));
            button.appendChild(el("span", null, spec.label));
            button.addEventListener("click", function () {
                setSort(spec.key);
                buildSortMenu();
            });
            li.appendChild(button);
            menu.appendChild(li);
        });
    }


    /**
     * Adds the two controls that only make sense once multi-select exists: a
     * select-all box, and a Paste button that lights up whenever the clipboard
     * is holding something.
     */
    function buildSelectionControls() {
        var toolbar = document.querySelector(".toolbar");
        if (!toolbar) { return; }

        var wrap = el("label", "select-all-control");
        wrap.htmlFor = "selectAll";

        var box = document.createElement("input");
        box.type = "checkbox";
        box.id = "selectAll";
        box.className = "sel-box";
        wrap.appendChild(box);
        wrap.appendChild(el("span", null, "Select all"));

        box.addEventListener("change", function () {
            if (box.checked) {
                Selection.selectAll();
            } else {
                Selection.clear();
            }
        });

        toolbar.insertBefore(wrap, toolbar.firstChild);

        if (mode !== "files") { return; }

        var paste = el("button", "btn-app-ghost btn-sm-app");
        paste.type = "button";
        paste.id = "pasteBtn";
        paste.appendChild(icon("clipboard-check"));
        var pasteLabel = el("span", null, "Paste");
        paste.appendChild(pasteLabel);

        paste.addEventListener("click", function () {
            Clipboard.pasteInto(state.folderId);
        });

        var spacer = toolbar.querySelector(".spacer");
        if (spacer) {
            toolbar.insertBefore(paste, spacer.nextSibling);
        } else {
            toolbar.appendChild(paste);
        }

        function refreshPaste() {
            var held = Clipboard.peek();
            paste.classList.toggle("is-hidden", !held);
            if (held) {
                pasteLabel.textContent =
                    "Paste " + Clipboard.describe() + (held.op === "cut" ? "" : " (copy)");
                paste.title = "Paste into this folder (Ctrl+V)";
            }
        }

        document.addEventListener("Cloud:clipboard", refreshPaste);
        refreshPaste();
    }

    function wireControls() {
        var grid = document.getElementById("viewGrid");
        var list = document.getElementById("viewList");
        if (grid) { grid.addEventListener("click", function () { setView("grid"); }); }
        if (list) { list.addEventListener("click", function () { setView("list"); }); }

        var filter = document.getElementById("filterInput");
        if (filter) {
            filter.addEventListener("input", UI.debounce(function () {
                state.filter = filter.value.trim();
                renderAll();
            }, 180));
        }

        var upload = document.querySelector("[data-action=upload]");
        if (upload) { upload.addEventListener("click", function () { Upload.pickFiles(); }); }

        var newFolder = document.querySelector("[data-action=new-folder]");
        if (newFolder) {
            newFolder.addEventListener("click", function () {
                document.getElementById("menuNewFolder").click();
            });
        }
    }


    /* ---------------------------------------------------------------------
       Boot
       ------------------------------------------------------------------ */

    async function boot() {
        loadPrefs();

        var user = await Shell.mount({ active: mode });
        if (!user) { return; }

        var params = new URLSearchParams(location.search);

        if (mode === "files") {
            var folder = params.get("folder");
            state.folderId = folder ? Number(folder) : null;
            Shell.uploadFolderId = state.folderId;

            var query = params.get("q");
            if (query) {
                state.filter = query;
                var filterInput = document.getElementById("filterInput");
                if (filterInput) { filterInput.value = query; }
            }
        }

        buildSelectionControls();

        setView(state.view);
        setSort(state.sort);
        buildSortMenu();
        wireControls();

        document.addEventListener("Cloud:refresh", load);

        load();
    }

    boot();
}());
