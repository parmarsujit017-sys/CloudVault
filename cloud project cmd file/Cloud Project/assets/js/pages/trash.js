/* =========================================================================
   TRASH
   Restore, permanently delete, or empty. Both destructive paths go through a
   confirmation dialog, and the auto-delete date comes straight from the
   trash table rather than being guessed in the browser.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var state = { entries: [] };


    function daysLeft(entry) {
        var when = UI.toDate(entry.auto_delete);
        if (!when) { return null; }
        return Math.max(0, Math.ceil((when.getTime() - Date.now()) / 86400000));
    }

    async function restore(entry) {
        try {
            var result = await API.trash.restore(entry.file_id);
            UI.toast(result.message, "success");
            load();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function purge(entry) {
        var yes = await UI.confirmDialog({
            title: "Delete permanently?",
            message: '"' + entry.original_name +
                '" will be removed from storage. This cannot be undone.',
            confirmText: "Delete permanently",
            danger: true,
            icon: "fire"
        });
        if (!yes) { return; }

        try {
            var result = await API.trash.purge(entry.file_id);
            UI.toast(result.message, "success");
            load();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function emptyTrash() {
        if (!state.entries.length) {
            UI.toast("Trash is already empty", "info");
            return;
        }

        var yes = await UI.confirmDialog({
            title: "Empty Trash?",
            message: "This permanently deletes all " + state.entries.length +
                " item(s) in Trash. This action cannot be undone.",
            confirmText: "Empty Trash",
            danger: true,
            icon: "trash3"
        });
        if (!yes) { return; }

        try {
            var result = await API.trash.empty();
            UI.toast(result.message, "success");
            load();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    function entryMenu(entry) {
        return [
            {
                text: "Restore",
                icon: "arrow-counterclockwise",
                onSelect: function () { restore(entry); }
            },
            { divider: true },
            {
                text: "Delete permanently",
                icon: "fire",
                danger: true,
                onSelect: function () { purge(entry); }
            }
        ];
    }

    function render() {
        var host = document.getElementById("trashHost");
        UI.clear(host);

        var emptyBtn = document.getElementById("emptyTrashBtn");
        emptyBtn.disabled = state.entries.length === 0;

        var subtitle = document.getElementById("trashSubtitle");
        subtitle.textContent = state.entries.length
            ? state.entries.length + " item(s) in Trash. " +
              "Items are deleted permanently on their auto-delete date."
            : "Items in Trash are deleted permanently after the retention period.";

        if (!state.entries.length) {
            host.appendChild(UI.emptyState({
                icon: "trash3",
                title: "Trash is empty",
                message: "Files you delete will wait here until you restore them or the retention period runs out."
            }));
            return;
        }

        var table = Files.fileTable([
            { label: "Name" },
            { label: "Size" },
            { label: "Deleted" },
            { label: "Auto delete" },
            { label: "", className: "cell-actions" }
        ]);

        state.entries.forEach(function (entry) {
            var row = document.createElement("tr");

            var nameCell = document.createElement("td");
            var wrap = el("div", "cell-name");
            wrap.appendChild(UI.typeChip(entry.original_name, entry.file_type, "sm"));
            var text = el("span", "n", entry.original_name);
            text.title = entry.original_name;
            wrap.appendChild(text);
            nameCell.appendChild(wrap);
            row.appendChild(nameCell);

            row.appendChild(cell(UI.formatSize(entry.file_size), "num"));
            row.appendChild(cell(UI.timeAgo(entry.deleted_at), "num"));

            var autoCell = document.createElement("td");
            var left = daysLeft(entry);
            var badge = el(
                "span",
                "badge-soft " + (left !== null && left <= 3 ? "is-danger" : "is-warning"),
                left === null
                    ? UI.formatDate(entry.auto_delete)
                    : (left === 0 ? "Today" : "in " + left + " day" + (left === 1 ? "" : "s"))
            );
            badge.title = UI.formatDateTime(entry.auto_delete);
            autoCell.appendChild(badge);
            row.appendChild(autoCell);

            var actionCell = document.createElement("td");
            actionCell.className = "cell-actions";

            var group = el("div");
            group.style.display = "flex";
            group.style.gap = "6px";
            group.style.justifyContent = "flex-end";

            var restoreBtn = el("button", "btn-app-ghost btn-sm-app");
            restoreBtn.type = "button";
            restoreBtn.title = "Restore";
            restoreBtn.setAttribute("aria-label", "Restore " + entry.original_name);
            restoreBtn.appendChild(icon("arrow-counterclockwise"));
            restoreBtn.addEventListener("click", function () { restore(entry); });
            group.appendChild(restoreBtn);

            var actions = Menu.dotTrigger("Actions for " + entry.original_name, function () {
                return entryMenu(entry);
            });
            actions.style.position = "static";
            actions.style.opacity = "1";
            group.appendChild(actions);

            actionCell.appendChild(group);
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

    async function load() {
        var host = document.getElementById("trashHost");
        var wrap = el("div", "table-wrap");
        UI.skeletonRows(4, wrap);
        UI.fill(host, wrap);

        try {
            state.entries = await API.trash.list();
            render();
        } catch (err) {
            UI.reportError(err);
            UI.fill(host, UI.emptyState({
                icon: "wifi-off",
                title: "Could not load Trash",
                message: err.message
            }));
        }
    }

    async function boot() {
        var user = await Shell.mount({ active: "trash" });
        if (!user) { return; }

        document.getElementById("emptyTrashBtn").addEventListener("click", emptyTrash);
        document.addEventListener("Cloud:refresh", load);

        load();
    }

    boot();
}());
