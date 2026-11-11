/* =========================================================================
   DASHBOARD
   Every number, file and activity line on this page comes from
   GET /api/dashboard — nothing here is hardcoded.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var STATS = [
        { key: "total_files", label: "Total files", icon: "file-earmark", tone: "", href: "files.html" },
        { key: "total_folders", label: "Folders", icon: "folder2", tone: "is-amber", href: "files.html" },
        { key: "shared_files", label: "Shared with me", icon: "people", tone: "is-purple", href: "shared.html" },
        { key: "storage_used", label: "Storage used", icon: "hdd", tone: "is-green", href: "storage.html", isSize: true }
    ];

    function statCard(spec, data) {
        var card = el("a", "stat");
        card.href = spec.href;

        var badge = el("div", "stat-icon " + spec.tone);
        badge.appendChild(icon(spec.icon));
        card.appendChild(badge);

        var body = el("div");
        body.appendChild(el("div", "stat-label", spec.label));

        var raw = data[spec.key];
        body.appendChild(el("div", "stat-value", spec.isSize ? UI.formatMB(raw) : String(raw)));

        card.appendChild(body);
        return card;
    }

    function renderStats(data) {
        var host = document.getElementById("statGrid");
        UI.clear(host);
        STATS.forEach(function (spec) { host.appendChild(statCard(spec, data)); });
    }

    function renderRecentFiles(files) {
        var host = document.getElementById("recentFiles");
        UI.clear(host);

        if (!files.length) {
            var panel = el("div", "panel");
            panel.appendChild(UI.emptyState({
                icon: "cloud-arrow-up",
                title: "No files yet",
                message: "Upload your first file and it will show up here.",
                actionLabel: "Upload files",
                actionIcon: "upload",
                onAction: function () { Upload.pickFiles(); }
            }));
            host.appendChild(panel);
            return;
        }

        var table = Files.fileTable([
            { label: "Name" },
            { label: "Type" },
            { label: "Size" },
            { label: "Modified" },
            { label: "" , className: "cell-actions" }
        ]);

        files.forEach(function (file) {
            table.tbody.appendChild(Files.fileRow(file, ["type", "size", "modified"]));
        });

        host.appendChild(table.wrap);
    }

    var ACTIVITY = {
        LOGIN: { icon: "box-arrow-in-right", tone: "", verb: "Signed in" },
        LOGOUT: { icon: "box-arrow-right", tone: "", verb: "Signed out" },
        REGISTER: { icon: "person-plus", tone: "", verb: "Created the account" },
        UPLOAD: { icon: "cloud-arrow-up", tone: "is-upload", verb: "Uploaded" },
        DOWNLOAD: { icon: "download", tone: "is-download", verb: "Downloaded" },
        CREATE_FOLDER: { icon: "folder-plus", tone: "is-folder", verb: "Created folder" },
        RENAME_FOLDER: { icon: "pencil", tone: "is-folder", verb: "Renamed folder" },
        DELETE_FOLDER: { icon: "folder-minus", tone: "is-delete", verb: "Deleted folder" },
        DELETE_FILE: { icon: "trash3", tone: "is-delete", verb: "Moved to Trash" },
        RESTORE_FILE: { icon: "arrow-counterclockwise", tone: "is-upload", verb: "Restored" },
        PERMANENT_DELETE: { icon: "fire", tone: "is-delete", verb: "Permanently deleted" },
        SHARE_FILE: { icon: "share", tone: "is-share", verb: "Shared" },
        UNSHARE_FILE: { icon: "link-45deg", tone: "is-share", verb: "Revoked sharing on" },
        UPDATE_PROFILE: { icon: "person-gear", tone: "", verb: "Updated the profile" },
        UPDATE_SETTINGS: { icon: "gear", tone: "", verb: "Updated settings" }
    };

    function activityLine(entry) {
        var spec = ACTIVITY[entry.activity] || { icon: "dot", tone: "", verb: entry.activity };

        var row = el("li", "timeline-item");

        var badge = el("span", "tl-icon " + spec.tone);
        badge.appendChild(icon(spec.icon));
        row.appendChild(badge);

        var body = el("div", "tl-body");

        var text = el("div", "tl-text");
        text.appendChild(document.createTextNode(spec.verb));
        if (entry.file_name) {
            text.appendChild(document.createTextNode(" "));
            text.appendChild(el("span", "tl-file", entry.file_name));
        }
        body.appendChild(text);
        body.appendChild(el("div", "tl-time", UI.timeAgo(entry.activity_time)));

        row.appendChild(body);
        return row;
    }

    function renderActivity(entries) {
        var host = document.getElementById("recentActivity");
        UI.clear(host);

        if (!entries.length) {
            host.appendChild(UI.emptyState({
                icon: "clock-history",
                title: "No activity yet",
                message: "Uploads, downloads and shares are recorded here."
            }));
            return;
        }

        var list = el("ul", "timeline");
        entries.forEach(function (entry) { list.appendChild(activityLine(entry)); });
        host.appendChild(list);
    }

    function showSkeletons() {
        var grid = document.getElementById("statGrid");
        UI.clear(grid);
        for (var i = 0; i < 4; i += 1) {
            var card = el("div", "stat");
            var chip = el("div", "skeleton sk-chip");
            chip.style.width = "38px";
            chip.style.height = "38px";
            card.appendChild(chip);

            var stack = el("div");
            stack.style.flex = "1";
            var l1 = el("div", "skeleton sk-line");
            l1.style.width = "60%";
            var l2 = el("div", "skeleton sk-line");
            l2.style.width = "40%";
            l2.style.height = "15px";
            stack.appendChild(l1);
            stack.appendChild(l2);
            card.appendChild(stack);
            grid.appendChild(card);
        }

        var filesHost = document.getElementById("recentFiles");
        var panel = el("div", "table-wrap");
        UI.skeletonRows(4, panel);
        UI.fill(filesHost, panel);

        UI.skeletonRows(3, document.getElementById("recentActivity"));
    }

    async function load() {
        showSkeletons();

        try {
            var data = await API.dashboard.get();
            renderStats(data);
            renderRecentFiles(data.recent_files || []);
            renderActivity(data.recent_activity || []);
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function boot() {
        var user = await Shell.mount({ active: "dashboard" });
        if (!user) { return; }

        document.getElementById("greetingLine").textContent =
            UI.greeting() + ", " + user.fullname.split(" ")[0];

        // Head actions reuse the shell's own New-menu handlers.
        document.querySelector("[data-action=upload]")
            .addEventListener("click", function () { Upload.pickFiles(); });

        document.querySelector("[data-action=new-folder]")
            .addEventListener("click", function () {
                document.getElementById("menuNewFolder").click();
            });

        document.addEventListener("Cloud:refresh", load);

        load();
    }

    boot();
}());
