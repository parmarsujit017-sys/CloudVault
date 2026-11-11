/* =========================================================================
   ACTIVITY
   A timeline built from GET /api/activity, grouped by day and filterable by
   the kind of action. The API returns only the signed-in user's own rows.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

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

    var FILTERS = [
        { key: "all", label: "All", match: null },
        { key: "uploads", label: "Uploads", match: ["UPLOAD"] },
        { key: "downloads", label: "Downloads", match: ["DOWNLOAD"] },
        { key: "shares", label: "Shares", match: ["SHARE_FILE", "UNSHARE_FILE"] },
        { key: "deletes", label: "Deletes", match: ["DELETE_FILE", "PERMANENT_DELETE", "DELETE_FOLDER"] },
        { key: "folders", label: "Folders", match: ["CREATE_FOLDER", "RENAME_FOLDER", "DELETE_FOLDER"] },
        { key: "account", label: "Account", match: ["LOGIN", "LOGOUT", "REGISTER", "UPDATE_PROFILE", "UPDATE_SETTINGS"] }
    ];

    var state = { entries: [], filter: "all" };


    function buildFilters() {
        var host = document.getElementById("activityFilters");
        UI.clear(host);

        FILTERS.forEach(function (spec) {
            var chip = el("button", "chip", spec.label);
            chip.type = "button";
            chip.setAttribute("aria-pressed", String(spec.key === state.filter));
            chip.addEventListener("click", function () {
                state.filter = spec.key;
                buildFilters();
                render();
            });
            host.appendChild(chip);
        });
    }

    function visibleEntries() {
        var spec = FILTERS.filter(function (f) { return f.key === state.filter; })[0];
        if (!spec || !spec.match) { return state.entries; }

        return state.entries.filter(function (entry) {
            return spec.match.indexOf(entry.activity) !== -1;
        });
    }

    function timelineItem(entry) {
        var spec = ACTIVITY[entry.activity] || {
            icon: "dot",
            tone: "",
            verb: entry.activity.replace(/_/g, " ").toLowerCase()
        };

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

        var meta = UI.formatTime(entry.activity_time);
        if (entry.ip_address) { meta += " · " + entry.ip_address; }
        body.appendChild(el("div", "tl-time", meta));

        row.appendChild(body);
        return row;
    }

    function render() {
        var host = document.getElementById("activityHost");
        UI.clear(host);

        var entries = visibleEntries();

        if (!entries.length) {
            host.appendChild(UI.emptyState({
                icon: "clock-history",
                title: state.filter === "all" ? "No activity yet" : "Nothing in this category",
                message: state.filter === "all"
                    ? "Uploads, downloads, shares and deletions are recorded here."
                    : "Try a different filter to see more of your history."
            }));
            return;
        }

        // Group by day so a long history stays readable.
        var groups = {};
        entries.forEach(function (entry) {
            var bucket = UI.dayBucket(entry.activity_time);
            (groups[bucket] = groups[bucket] || []).push(entry);
        });

        UI.BUCKET_ORDER.forEach(function (bucket) {
            if (!groups[bucket]) { return; }

            host.appendChild(el("div", "timeline-day", bucket));

            var list = el("ul", "timeline");
            groups[bucket].forEach(function (entry) { list.appendChild(timelineItem(entry)); });
            host.appendChild(list);
        });
    }

    async function load() {
        var host = document.getElementById("activityHost");
        UI.skeletonRows(6, host);

        try {
            state.entries = await API.activity.list(100);
            render();
        } catch (err) {
            UI.reportError(err);
            UI.fill(host, UI.emptyState({
                icon: "wifi-off",
                title: "Could not load activity",
                message: err.message
            }));
        }
    }

    async function boot() {
        var user = await Shell.mount({ active: "activity" });
        if (!user) { return; }

        buildFilters();
        document.addEventListener("Cloud:refresh", load);

        load();
    }

    boot();
}());
