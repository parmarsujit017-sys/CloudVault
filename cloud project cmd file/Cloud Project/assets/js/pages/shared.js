/* =========================================================================
   SHARED WITH ME
   Everything comes from GET /api/shares/received, including the search,
   which is executed by the backend rather than filtered in the browser.

   A share can be a single file or a whole folder. Folders open in the shared
   browser at share.html, which walks their structure without needing the
   recipient to own anything.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var VIEW_KEY = "Cloud_view";

    var state = {
        view: "grid",
        query: "",
        shares: []
    };


    function loadPrefs() {
        try {
            var view = localStorage.getItem(VIEW_KEY);
            if (view === "grid" || view === "list") { state.view = view; }
        } catch (e) { /* storage blocked */ }
    }


    /* ---------------------------------------------------------------------
       Actions available on a file someone shared with you
       ------------------------------------------------------------------ */

    function isFolder(share) { return share.kind === "folder"; }

    /** The shared-browser URL for a folder share, used by Open and dblclick. */
    function browseUrl(share) {
        return "share.html?token=" + encodeURIComponent(share.share_link);
    }

    function displayName(share) {
        return isFolder(share) ? (share.folder_name || share.file_name) : share.file_name;
    }

    function shareMenuItems(share) {
        if (isFolder(share)) {
            return [
                {
                    text: "Open folder",
                    icon: "box-arrow-up-right",
                    disabled: share.is_expired,
                    onSelect: function () { window.open(browseUrl(share), "_blank"); }
                },
                {
                    text: "Download as ZIP",
                    icon: "file-earmark-zip",
                    disabled: share.is_expired,
                    onSelect: function () {
                        UI.toast("Preparing the archive…", "success");
                        window.location.href = API.shares.publicZipUrl(share.share_link);
                    }
                },
                { divider: true },
                { text: "Details", icon: "info-circle", onSelect: function () { showDetails(share); } }
            ];
        }

        var asFile = {
            id: share.file_id,
            original_name: share.file_name,
            kind: share.file_kind,
            type: share.file_kind,
            file_type: share.file_type,
            file_size: share.file_size
        };

        return [
            {
                text: "Open",
                icon: "box-arrow-up-right",
                disabled: share.is_expired,
                onSelect: function () { Files.openFile(asFile); }
            },
            {
                text: "Download",
                icon: "download",
                disabled: share.is_expired,
                onSelect: function () { Files.downloadFile(asFile); }
            },
            { divider: true },
            { text: "Details", icon: "info-circle", onSelect: function () { showDetails(share); } }
        ];
    }

    /**
     * A read-only details view. The recipient does not own the file, so this
     * shows provenance rather than the owner's management actions.
     */
    function showDetails(share) {
        var host = el("div");

        var hero = el("div", "details-hero");
        hero.appendChild(isFolder(share)
            ? UI.folderChip("lg")
            : UI.typeChip(share.file_name, share.file_type, "lg"));
        hero.appendChild(el("h3", null, displayName(share)));
        hero.appendChild(el("div", "dh-type", isFolder(share)
            ? "Folder"
            : UI.typeLabel(share.file_name, share.file_type)));
        host.appendChild(hero);

        function row(key, value) {
            var node = el("div", "kv-row");
            node.appendChild(el("span", "k", key));
            node.appendChild(el("span", "v", value));
            return node;
        }

        host.appendChild(row("Shared by", share.shared_by_name || "Unknown"));
        if (isFolder(share)) {
            host.appendChild(row(
                "Contents",
                share.item_count + (share.item_count === 1 ? " file" : " files")
            ));
        }
        host.appendChild(row("Size", UI.formatSize(share.file_size)));
        host.appendChild(row("Type", isFolder(share) ? "Folder" : (share.file_type || "—")));
        host.appendChild(row("Shared on", UI.formatDateTime(share.created_at)));
        host.appendChild(row(
            "Expires",
            share.expiry_date
                ? (share.is_expired ? "Expired " + UI.formatDate(share.expiry_date)
                                    : UI.formatDate(share.expiry_date))
                : "Never"
        ));
        host.appendChild(row(
            "Your access",
            isFolder(share) ? "Browse and download everything inside" : "View and download"
        ));

        openDetailsModal(host, share);
    }

    function openDetailsModal(content, share) {
        var host = el("div", "modal fade");
        host.tabIndex = -1;

        var dialog = el("div", "modal-dialog modal-dialog-centered");
        var box = el("div", "modal-content");

        var header = el("div", "modal-header");
        header.appendChild(el("h2", "modal-title", isFolder(share) ? "Folder details" : "File details"));
        var close = el("button", "btn-close");
        close.type = "button";
        close.setAttribute("data-bs-dismiss", "modal");
        close.setAttribute("aria-label", "Close");
        header.appendChild(close);

        var body = el("div", "modal-body");
        body.appendChild(content);

        var footer = el("div", "modal-footer");
        var closeBtn = el("button", "btn-app-ghost", "Close");
        closeBtn.type = "button";
        closeBtn.setAttribute("data-bs-dismiss", "modal");
        footer.appendChild(closeBtn);

        if (!share.is_expired) {
            var download = el("button", "btn-app-primary");
            download.type = "button";

            if (isFolder(share)) {
                download.appendChild(icon("box-arrow-up-right"));
                download.appendChild(el("span", null, "Open folder"));
                download.addEventListener("click", function () {
                    window.open(browseUrl(share), "_blank");
                });
            } else {
                download.appendChild(icon("download"));
                download.appendChild(el("span", null, "Download"));
                download.addEventListener("click", function () {
                    Files.downloadFile({ id: share.file_id, original_name: share.file_name });
                });
            }
            footer.appendChild(download);
        }

        box.appendChild(header);
        box.appendChild(body);
        box.appendChild(footer);
        dialog.appendChild(box);
        host.appendChild(dialog);
        document.body.appendChild(host);

        var modal = new bootstrap.Modal(host);
        host.addEventListener("hidden.bs.modal", function () { host.remove(); });
        modal.show();
    }


    /* ---------------------------------------------------------------------
       Rendering
       ------------------------------------------------------------------ */

    function sharedCard(share) {
        var card = el("div", "shared-card");
        var name = displayName(share);

        card.appendChild(isFolder(share)
            ? UI.folderChip("md")
            : UI.typeChip(share.file_name, share.file_type, "md"));

        var body = el("div", "sc-body");

        var title = el("div", "sc-name", name);
        title.title = name;
        body.appendChild(title);

        var meta = el("div", "sc-meta");

        var owner = el("span");
        owner.appendChild(icon("person"));
        owner.appendChild(document.createTextNode(" " + (share.shared_by_name || "Unknown")));
        meta.appendChild(owner);

        if (isFolder(share)) {
            meta.appendChild(el("span", null, "·"));
            meta.appendChild(el(
                "span", null,
                share.item_count + (share.item_count === 1 ? " file" : " files")
            ));
        }

        meta.appendChild(el("span", null, "·"));
        meta.appendChild(el("span", null, UI.formatSize(share.file_size)));
        meta.appendChild(el("span", null, "·"));
        meta.appendChild(el("span", null, UI.timeAgo(share.created_at)));

        body.appendChild(meta);

        if (share.expiry_date) {
            var badge = el(
                "span",
                "badge-soft " + (share.is_expired ? "is-danger" : "is-warning"),
                share.is_expired ? "Expired" : "Expires " + UI.formatDate(share.expiry_date)
            );
            badge.style.marginTop = "6px";
            body.appendChild(badge);
        }

        card.appendChild(body);

        card.appendChild(Menu.dotTrigger("Actions for " + name, function () {
            return shareMenuItems(share);
        }));

        card.addEventListener("dblclick", function () {
            if (share.is_expired) { return; }
            if (isFolder(share)) {
                window.open(browseUrl(share), "_blank");
            } else {
                Files.openFile({ id: share.file_id, original_name: share.file_name });
            }
        });

        return card;
    }

    function renderList(host, shares) {
        var table = Files.fileTable([
            { label: "Name" },
            { label: "Shared by" },
            { label: "Size" },
            { label: "Shared" },
            { label: "Expiry" },
            { label: "", className: "cell-actions" }
        ]);

        shares.forEach(function (share) {
            var row = document.createElement("tr");
            var name = displayName(share);

            var nameCell = document.createElement("td");
            var wrap = el("div", "cell-name");
            wrap.appendChild(isFolder(share)
                ? UI.folderChip("sm")
                : UI.typeChip(share.file_name, share.file_type, "sm"));
            var text = el("span", "n", name);
            text.title = name;
            wrap.appendChild(text);
            nameCell.appendChild(wrap);
            row.appendChild(nameCell);

            row.appendChild(cell(share.shared_by_name || "Unknown"));
            row.appendChild(cell(UI.formatSize(share.file_size), "num"));
            row.appendChild(cell(UI.timeAgo(share.created_at), "num"));

            var expiryCell = document.createElement("td");
            if (!share.expiry_date) {
                expiryCell.textContent = "Never";
            } else {
                expiryCell.appendChild(el(
                    "span",
                    "badge-soft " + (share.is_expired ? "is-danger" : "is-warning"),
                    share.is_expired ? "Expired" : UI.formatDate(share.expiry_date)
                ));
            }
            row.appendChild(expiryCell);

            var actionCell = document.createElement("td");
            actionCell.className = "cell-actions";
            var actions = Menu.dotTrigger("Actions for " + name, function () {
                return shareMenuItems(share);
            });
            actions.style.position = "static";
            actions.style.opacity = "1";
            actionCell.appendChild(actions);
            row.appendChild(actionCell);

            table.tbody.appendChild(row);
        });

        host.appendChild(table.wrap);
    }

    function cell(text, className) {
        var node = document.createElement("td");
        node.textContent = text;
        if (className) { node.className = className; }
        return node;
    }

    function render() {
        var host = document.getElementById("sharedHost");
        UI.clear(host);

        if (!state.shares.length) {
            host.appendChild(UI.emptyState({
                icon: state.query ? "search" : "people",
                title: state.query ? "No matches" : "Nothing shared with you",
                message: state.query
                    ? 'Nothing shared with you matches "' + state.query + '".'
                    : "Files and folders other people share with you will appear here."
            }));
            return;
        }

        if (state.view === "list") {
            renderList(host, state.shares);
            return;
        }

        var grid = el("div", "shared-grid");
        state.shares.forEach(function (share) { grid.appendChild(sharedCard(share)); });
        host.appendChild(grid);
    }

    async function load() {
        var host = document.getElementById("sharedHost");

        if (state.view === "list") {
            var wrap = el("div", "table-wrap");
            UI.skeletonRows(5, wrap);
            UI.fill(host, wrap);
        } else {
            var grid = el("div", "shared-grid");
            UI.skeletonCards(4, grid);
            UI.fill(host, grid);
        }

        try {
            state.shares = await API.shares.received(state.query);
            render();
        } catch (err) {
            UI.reportError(err);
            UI.fill(host, UI.emptyState({
                icon: "wifi-off",
                title: "Could not load shared files",
                message: err.message
            }));
        }
    }

    function setView(view) {
        state.view = view;
        try { localStorage.setItem(VIEW_KEY, view); } catch (e) { /* storage blocked */ }

        document.getElementById("viewGrid").setAttribute("aria-pressed", String(view === "grid"));
        document.getElementById("viewList").setAttribute("aria-pressed", String(view === "list"));

        render();
    }

    async function boot() {
        loadPrefs();

        var user = await Shell.mount({ active: "shared" });
        if (!user) { return; }

        setView(state.view);

        document.getElementById("viewGrid")
            .addEventListener("click", function () { setView("grid"); });
        document.getElementById("viewList")
            .addEventListener("click", function () { setView("list"); });

        var search = document.getElementById("sharedSearch");
        search.addEventListener("input", UI.debounce(function () {
            state.query = search.value.trim();
            load();
        }, 260));

        document.addEventListener("Cloud:refresh", load);

        load();
    }

    boot();
}());
