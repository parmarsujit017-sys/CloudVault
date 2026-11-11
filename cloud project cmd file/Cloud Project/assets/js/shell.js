/* =========================================================================
   APPLICATION SHELL
   Renders the sidebar and header on every signed-in page so the markup is
   defined once, and owns the cross-page concerns: theme, navigation, global
   search, notifications, the New menu and the profile modal.
   ========================================================================= */

(function (global) {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var THEME_KEY = "Cloud_theme";      // light | dark | system
    var READ_KEY = "Cloud_read_notifs";

    var state = {
        user: null,
        settings: null,
        stats: null,
        /** The plan the account is on, so the storage widget can name it. */
        plan: null,
        active: null,
        /** Pages that browse a folder set this so uploads land in the right place. */
        uploadFolderId: null
    };

    var nodes = {};


    /* ---------------------------------------------------------------------
       Theme
       ------------------------------------------------------------------ */

    function storedThemeMode() {
        try {
            return localStorage.getItem(THEME_KEY) || "light";
        } catch (e) {
            return "light";
        }
    }

    function systemPrefersDark() {
        return global.matchMedia && global.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    function resolveTheme(mode) {
        if (mode === "system") { return systemPrefersDark() ? "dark" : "light"; }
        return mode === "dark" ? "dark" : "light";
    }

    /** Paint the theme. Called by the inline head script too, to avoid a flash. */
    function applyTheme(mode) {
        document.documentElement.setAttribute("data-theme", resolveTheme(mode));
        document.documentElement.setAttribute("data-theme-mode", mode);
    }

    function setThemeMode(mode) {
        try { localStorage.setItem(THEME_KEY, mode); } catch (e) { /* private mode */ }
        applyTheme(mode);
    }

    // Follow the OS while the user is on "System".
    if (global.matchMedia) {
        global.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
            if (storedThemeMode() === "system") { applyTheme("system"); }
        });
    }


    /* ---------------------------------------------------------------------
       Navigation model
       ------------------------------------------------------------------ */

    var NAV = [
        {
            label: "Main",
            items: [
                { key: "dashboard", text: "Dashboard", icon: "grid-1x2", href: "dashboard.html" },
                { key: "files", text: "My Files", icon: "folder2-open", href: "files.html" },
                { key: "shared", text: "Shared With Me", icon: "people", href: "shared.html", count: "shared_files" },
                { key: "recent", text: "Recent", icon: "clock-history", href: "recent.html" },
                { key: "starred", text: "Starred", icon: "star", href: "starred.html" }
            ]
        },
        {
            label: "Library",
            items: [
                { key: "storage", text: "Storage", icon: "hdd", href: "storage.html" },
                { key: "trash", text: "Trash", icon: "trash3", href: "trash.html", count: "trash_files" }
            ]
        },
        {
            label: "System",
            items: [
                { key: "activity", text: "Activity", icon: "activity", href: "activity.html" },
                { key: "settings", text: "Settings", icon: "gear", href: "settings.html" }
            ]
        }
    ];


    /* ---------------------------------------------------------------------
       Sidebar
       ------------------------------------------------------------------ */

    function avatarSrc() {
        if (state.user && state.user.profile_image) {
            return API.users.avatarUrl() + "?v=" + encodeURIComponent(state.user.profile_image);
        }
        return "assets/img/profile.png";
    }

    function avatarImg(size) {
        var img = document.createElement("img");
        img.className = "avatar avatar-" + size;
        img.src = avatarSrc();
        img.alt = "";
        img.addEventListener("error", function () {
            this.src = "assets/img/profile.png";
        });
        return img;
    }

    function buildSidebar(host) {
        host.className = "sidebar";
        host.id = "appSidebar";
        UI.clear(host);

        // Brand
        var brand = el("a", "sidebar-brand");
        brand.href = "dashboard.html";
        var mark = el("span", "brand-mark");
        mark.appendChild(icon("cloud-fill"));
        brand.appendChild(mark);
        brand.appendChild(el("span", "brand-name", "Cloud"));
        host.appendChild(brand);

        // Scrollable middle
        var scroll = el("div", "sidebar-scroll");

        // New button + menu
        var newWrap = el("div", "dropdown");

        var newBtn = el("button", "new-btn");
        newBtn.type = "button";
        newBtn.id = "newBtn";
        newBtn.setAttribute("data-bs-toggle", "dropdown");
        newBtn.setAttribute("data-bs-offset", "0,6");
        newBtn.setAttribute("aria-expanded", "false");
        newBtn.appendChild(icon("plus-lg"));
        newBtn.appendChild(el("span", null, "New"));

        var newMenu = el("ul", "dropdown-menu app-menu");
        newMenu.setAttribute("aria-labelledby", "newBtn");

        [
            { id: "menuNewFolder", icon: "folder-plus", text: "New Folder" },
            { id: "menuNewWord", icon: "file-earmark-word", text: "New Word Document" },
            { id: "menuNewExcel", icon: "file-earmark-spreadsheet", text: "New Excel Spreadsheet" },
            { id: "menuUploadFiles", icon: "upload", text: "Upload Files" },
            { id: "menuUploadFolder", icon: "folder-symlink", text: "Upload Folder" }
        ].forEach(function (entry) {
            var li = document.createElement("li");
            var button = el("button", "dropdown-item");
            button.type = "button";
            button.id = entry.id;
            button.appendChild(icon(entry.icon));
            button.appendChild(el("span", null, entry.text));
            li.appendChild(button);
            newMenu.appendChild(li);
        });

        newWrap.appendChild(newBtn);
        newWrap.appendChild(newMenu);
        scroll.appendChild(newWrap);

        // Navigation groups
        NAV.forEach(function (group) {
            var section = el("div", "nav-group");
            section.appendChild(el("div", "nav-group-label", group.label));

            var list = el("nav");
            list.setAttribute("aria-label", group.label);

            group.items.forEach(function (item) {
                var link = el("a", "nav-item" + (item.key === state.active ? " active" : ""));
                link.href = item.href;
                if (item.key === state.active) { link.setAttribute("aria-current", "page"); }

                link.appendChild(icon(item.icon));
                link.appendChild(el("span", null, item.text));

                if (item.count) {
                    var badge = el("span", "nav-count is-hidden");
                    badge.dataset.count = item.count;
                    link.appendChild(badge);
                }

                list.appendChild(link);
            });

            section.appendChild(list);
            scroll.appendChild(section);
        });

        host.appendChild(scroll);

        // Storage + user
        var foot = el("div", "sidebar-foot");

        var storage = el("a", "storage-widget");
        storage.href = "storage.html";

        var sHead = el("div", "storage-widget-head");
        // The label doubles as the plan name once it is known, so the number
        // below it is never a quota without an explanation.
        var sLabel = el("span", null, "Storage");
        sLabel.id = "sidebarPlanName";
        sHead.appendChild(sLabel);
        var sPct = el("span", null, "—");
        sPct.id = "sidebarStoragePct";
        sHead.appendChild(sPct);
        storage.appendChild(sHead);

        var meter = el("div", "meter");
        var fill = el("div", "meter-fill");
        fill.id = "sidebarStorageBar";
        meter.appendChild(fill);
        storage.appendChild(meter);

        var sFoot = el("div", "storage-widget-foot", "Loading…");
        sFoot.id = "sidebarStorageText";
        storage.appendChild(sFoot);

        foot.appendChild(storage);

        var userBtn = el("button", "sidebar-user");
        userBtn.type = "button";
        userBtn.id = "sidebarUser";
        userBtn.setAttribute("aria-label", "Open your profile");
        userBtn.appendChild(avatarImg("md"));

        var who = el("div", "who");
        var name = el("strong", null, "—");
        name.id = "sidebarUserName";
        var mail = el("span", null, "");
        mail.id = "sidebarUserEmail";
        who.appendChild(name);
        who.appendChild(mail);
        userBtn.appendChild(who);
        userBtn.appendChild(icon("chevron-expand", "text-faint"));

        foot.appendChild(userBtn);
        host.appendChild(foot);

        nodes.sidebar = host;
    }


    /* ---------------------------------------------------------------------
       Header
       ------------------------------------------------------------------ */

    function buildHeader(host) {
        host.className = "app-header";
        UI.clear(host);

        var menuBtn = el("button", "header-menu-btn");
        menuBtn.type = "button";
        menuBtn.id = "sidebarToggle";
        menuBtn.setAttribute("aria-label", "Open navigation");
        menuBtn.setAttribute("aria-controls", "appSidebar");
        menuBtn.setAttribute("aria-expanded", "false");
        menuBtn.appendChild(icon("list"));
        host.appendChild(menuBtn);

        // Global search
        var search = el("div", "header-search");
        search.appendChild(icon("search"));

        var input = document.createElement("input");
        input.type = "search";
        input.id = "globalSearch";
        input.placeholder = "Search files, folders and shared items";
        input.setAttribute("aria-label", "Search files, folders and shared items");
        input.setAttribute("autocomplete", "off");
        input.setAttribute("role", "combobox");
        input.setAttribute("aria-expanded", "false");
        input.setAttribute("aria-controls", "searchResults");
        search.appendChild(input);

        var hint = el("div", "kbd-hint");
        hint.appendChild(el("span", "kbd", "Ctrl"));
        hint.appendChild(el("span", "kbd", "K"));
        search.appendChild(hint);

        var results = el("div", "search-results");
        results.id = "searchResults";
        results.setAttribute("role", "listbox");
        search.appendChild(results);

        host.appendChild(search);

        // Tools
        var tools = el("div", "header-tools");

        // Notifications
        var notifWrap = el("div", "dropdown");
        var notifBtn = el("button", "icon-btn");
        notifBtn.type = "button";
        notifBtn.id = "notifBtn";
        notifBtn.setAttribute("data-bs-toggle", "dropdown");
        notifBtn.setAttribute("data-bs-auto-close", "outside");
        notifBtn.setAttribute("aria-expanded", "false");
        notifBtn.setAttribute("aria-label", "Notifications");
        notifBtn.appendChild(icon("bell"));
        var dot = el("span", "dot is-hidden");
        dot.id = "notifDot";
        notifBtn.appendChild(dot);

        var notifMenu = el("div", "dropdown-menu dropdown-menu-end app-menu notif-menu");
        notifMenu.setAttribute("aria-labelledby", "notifBtn");

        var nHead = el("div", "notif-head");
        nHead.appendChild(el("h3", null, "Notifications"));
        var markAll = el("button", "btn-app-ghost btn-sm-app", "Mark all read");
        markAll.type = "button";
        markAll.id = "notifMarkAll";
        nHead.appendChild(markAll);
        notifMenu.appendChild(nHead);

        var nList = el("div", "notif-list");
        nList.id = "notifList";
        notifMenu.appendChild(nList);

        notifWrap.appendChild(notifBtn);
        notifWrap.appendChild(notifMenu);
        tools.appendChild(notifWrap);

        // Theme quick toggle
        var themeBtn = el("button", "icon-btn");
        themeBtn.type = "button";
        themeBtn.id = "themeToggle";
        themeBtn.setAttribute("aria-label", "Toggle light and dark theme");
        themeBtn.appendChild(icon(resolveTheme(storedThemeMode()) === "dark" ? "sun" : "moon-stars"));
        tools.appendChild(themeBtn);

        // Profile
        var profileWrap = el("div", "dropdown");
        var profileBtn = el("button", "avatar-btn");
        profileBtn.type = "button";
        profileBtn.id = "headerProfileBtn";
        profileBtn.setAttribute("data-bs-toggle", "dropdown");
        profileBtn.setAttribute("aria-expanded", "false");
        profileBtn.setAttribute("aria-label", "Account menu");
        profileBtn.appendChild(avatarImg("md"));

        var profileMenu = el("ul", "dropdown-menu dropdown-menu-end app-menu");
        profileMenu.setAttribute("aria-labelledby", "headerProfileBtn");

        var headerLi = document.createElement("li");
        var headerName = el("div", "dropdown-header", "Signed in");
        headerName.id = "menuUserLine";
        headerLi.appendChild(headerName);
        profileMenu.appendChild(headerLi);

        [
            { id: "menuProfile", icon: "person", text: "Profile" },
            { id: "menuStorageLink", icon: "hdd", text: "Storage", href: "storage.html" },
            { id: "menuSettingsLink", icon: "gear", text: "Settings", href: "settings.html" }
        ].forEach(function (entry) {
            var li = document.createElement("li");
            var node = entry.href ? el("a", "dropdown-item") : el("button", "dropdown-item");
            if (entry.href) { node.href = entry.href; } else { node.type = "button"; }
            node.id = entry.id;
            node.appendChild(icon(entry.icon));
            node.appendChild(el("span", null, entry.text));
            li.appendChild(node);
            profileMenu.appendChild(li);
        });

        // Only rendered for administrators; the endpoints behind it are guarded
        // server-side regardless, so this is signposting rather than security.
        if (state.user && state.user.role === "admin") {
            var adminLi = document.createElement("li");
            var adminLink = el("a", "dropdown-item");
            adminLink.href = "/admin";
            adminLink.id = "menuAdminLink";
            adminLink.appendChild(icon("shield-lock"));
            adminLink.appendChild(el("span", null, "Admin panel"));
            adminLi.appendChild(adminLink);
            profileMenu.appendChild(adminLi);
        }

        var divider = document.createElement("li");
        divider.appendChild(el("hr", "dropdown-divider"));
        profileMenu.appendChild(divider);

        var outLi = document.createElement("li");
        var logout = el("button", "dropdown-item is-danger");
        logout.type = "button";
        logout.id = "menuLogout";
        logout.appendChild(icon("box-arrow-right"));
        logout.appendChild(el("span", null, "Log out"));
        outLi.appendChild(logout);
        profileMenu.appendChild(outLi);

        profileWrap.appendChild(profileBtn);
        profileWrap.appendChild(profileMenu);
        tools.appendChild(profileWrap);

        host.appendChild(tools);
        nodes.header = host;
    }


    /* ---------------------------------------------------------------------
       Profile modal
       ------------------------------------------------------------------ */

    function buildProfileModal() {
        var host = el("div", "modal fade profile-modal");
        host.id = "profileModal";
        host.tabIndex = -1;
        host.setAttribute("aria-labelledby", "profileModalTitle");

        var dialog = el("div", "modal-dialog modal-dialog-centered");
        var content = el("div", "modal-content");

        var header = el("div", "modal-header");
        var title = el("h2", "modal-title", "Your account");
        title.id = "profileModalTitle";
        header.appendChild(title);
        var close = el("button", "btn-close");
        close.type = "button";
        close.setAttribute("data-bs-dismiss", "modal");
        close.setAttribute("aria-label", "Close");
        header.appendChild(close);
        content.appendChild(header);

        var body = el("div", "modal-body");

        // Photo + identity
        var top = el("div", "profile-top");
        var photo = el("div", "profile-photo");
        var img = avatarImg("lg");
        img.id = "profileModalAvatar";
        photo.appendChild(img);

        var cam = el("button", "cam-btn");
        cam.type = "button";
        cam.id = "profileAvatarBtn";
        cam.setAttribute("aria-label", "Change profile photo");
        cam.appendChild(icon("camera-fill"));
        photo.appendChild(cam);

        var fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.id = "profileAvatarInput";
        fileInput.accept = "image/png,image/jpeg,image/gif,image/webp";
        fileInput.hidden = true;
        photo.appendChild(fileInput);

        top.appendChild(photo);

        var ptBody = el("div", "pt-body");
        var pName = el("h3", null, "—");
        pName.id = "profileName";
        var pMail = el("div", "pt-mail", "");
        pMail.id = "profileEmail";
        ptBody.appendChild(pName);
        ptBody.appendChild(pMail);

        var roleBadge = el("span", "badge-soft is-primary", "User");
        roleBadge.id = "profileRole";
        roleBadge.style.marginTop = "6px";
        ptBody.appendChild(roleBadge);

        top.appendChild(ptBody);
        body.appendChild(top);

        // Tabs
        var tabs = el("div", "profile-tabs");
        tabs.setAttribute("role", "tablist");
        [
            { key: "profile", text: "Profile" },
            { key: "storage", text: "Storage" },
            { key: "security", text: "Security" }
        ].forEach(function (tab, index) {
            var button = el("button", null, tab.text);
            button.type = "button";
            button.dataset.tab = tab.key;
            button.setAttribute("role", "tab");
            button.setAttribute("aria-selected", index === 0 ? "true" : "false");
            tabs.appendChild(button);
        });
        body.appendChild(tabs);

        // Pane: profile
        var paneProfile = el("div", "profile-pane");
        paneProfile.dataset.pane = "profile";

        [
            ["Full name", "profileFullname"],
            ["Username", "profileUsername"],
            ["Email", "profileEmailValue"],
            ["Member since", "profileCreated"],
            ["Account status", "profileStatus"]
        ].forEach(function (pair) {
            var row = el("div", "kv-row");
            row.appendChild(el("span", "k", pair[0]));
            var value = el("span", "v", "—");
            value.id = pair[1];
            row.appendChild(value);
            paneProfile.appendChild(row);
        });

        var editBtn = el("button", "btn-app-ghost btn-block", "Edit profile");
        editBtn.type = "button";
        editBtn.id = "profileEditBtn";
        editBtn.style.marginTop = "16px";
        paneProfile.appendChild(editBtn);

        body.appendChild(paneProfile);

        // Pane: storage
        var paneStorage = el("div", "profile-pane is-hidden");
        paneStorage.dataset.pane = "storage";

        var storageHead = el("div");
        storageHead.style.display = "flex";
        storageHead.style.justifyContent = "space-between";
        storageHead.style.marginBottom = "8px";
        storageHead.style.fontSize = "13.5px";
        var sUsed = el("strong", null, "—");
        sUsed.id = "profileStorageUsed";
        storageHead.appendChild(sUsed);
        var sPct = el("span", "text-dim", "");
        sPct.id = "profileStoragePct";
        storageHead.appendChild(sPct);
        paneStorage.appendChild(storageHead);

        var sMeter = el("div", "meter");
        var sFill = el("div", "meter-fill");
        sFill.id = "profileStorageBar";
        sMeter.appendChild(sFill);
        paneStorage.appendChild(sMeter);

        var sNote = el("p", "text-meta", "");
        sNote.id = "profileStorageNote";
        sNote.style.marginTop = "8px";
        paneStorage.appendChild(sNote);

        var storageLink = el("a", "btn-app-ghost btn-block", "Storage details");
        storageLink.href = "storage.html";
        storageLink.style.marginTop = "16px";
        paneStorage.appendChild(storageLink);

        body.appendChild(paneStorage);

        // Pane: security
        var paneSecurity = el("div", "profile-pane is-hidden");
        paneSecurity.dataset.pane = "security";

        var pwForm = document.createElement("form");
        pwForm.id = "profilePasswordForm";
        pwForm.noValidate = true;

        [
            ["Current password", "pmCurrentPassword", "current-password"],
            ["New password", "pmNewPassword", "new-password"],
            ["Confirm new password", "pmConfirmPassword", "new-password"]
        ].forEach(function (spec) {
            var field = el("div", "field");
            var label = el("label", null, spec[0]);
            label.htmlFor = spec[1];
            var input = document.createElement("input");
            input.type = "password";
            input.id = spec[1];
            input.required = true;
            input.autocomplete = spec[2];
            if (spec[2] === "new-password") { input.minLength = 6; }
            field.appendChild(label);
            field.appendChild(input);
            pwForm.appendChild(field);
        });

        var pwSubmit = el("button", "btn-app-primary btn-block", "Update password");
        pwSubmit.type = "submit";
        pwSubmit.style.marginTop = "16px";
        pwForm.appendChild(pwSubmit);

        paneSecurity.appendChild(pwForm);
        body.appendChild(paneSecurity);

        content.appendChild(body);

        var footer = el("div", "modal-footer");
        var logoutBtn = el("button", "btn-app-ghost is-danger", "Log out");
        logoutBtn.type = "button";
        logoutBtn.id = "profileLogoutBtn";
        footer.appendChild(logoutBtn);
        content.appendChild(footer);

        dialog.appendChild(content);
        host.appendChild(dialog);
        document.body.appendChild(host);

        nodes.profileModal = host;
    }

    function buildEditProfileModal() {
        var host = el("div", "modal fade");
        host.id = "editProfileModal";
        host.tabIndex = -1;
        host.setAttribute("aria-labelledby", "editProfileTitle");

        var dialog = el("div", "modal-dialog modal-dialog-centered");
        var content = el("div", "modal-content");

        var form = document.createElement("form");
        form.id = "editProfileForm";
        form.noValidate = true;

        var header = el("div", "modal-header");
        var title = el("h2", "modal-title", "Edit profile");
        title.id = "editProfileTitle";
        header.appendChild(title);
        var close = el("button", "btn-close");
        close.type = "button";
        close.setAttribute("data-bs-dismiss", "modal");
        close.setAttribute("aria-label", "Close");
        header.appendChild(close);
        form.appendChild(header);

        var body = el("div", "modal-body");
        [
            ["Full name", "editFullname", "text"],
            ["Username", "editUsername", "text"],
            ["Email", "editEmail", "email"]
        ].forEach(function (spec) {
            var field = el("div", "field");
            var label = el("label", null, spec[0]);
            label.htmlFor = spec[1];
            var input = document.createElement("input");
            input.type = spec[2];
            input.id = spec[1];
            input.required = true;
            field.appendChild(label);
            field.appendChild(input);
            body.appendChild(field);
        });
        form.appendChild(body);

        var footer = el("div", "modal-footer");
        var cancel = el("button", "btn-app-ghost", "Cancel");
        cancel.type = "button";
        cancel.setAttribute("data-bs-dismiss", "modal");
        var save = el("button", "btn-app-primary", "Save changes");
        save.type = "submit";
        footer.appendChild(cancel);
        footer.appendChild(save);
        form.appendChild(footer);

        content.appendChild(form);
        dialog.appendChild(content);
        host.appendChild(dialog);
        document.body.appendChild(host);
    }


    /* ---------------------------------------------------------------------
       Rendering live data
       ------------------------------------------------------------------ */

    function renderUser() {
        var user = state.user;
        if (!user) { return; }

        var src = avatarSrc();
        document.querySelectorAll(".avatar").forEach(function (img) {
            if (img.tagName === "IMG") { img.src = src; }
        });

        setText("sidebarUserName", user.fullname);
        setText("sidebarUserEmail", user.email);
        setText("menuUserLine", user.fullname);

        setText("profileName", user.fullname);
        setText("profileEmail", user.email);
        setText("profileFullname", user.fullname);
        setText("profileUsername", user.username);
        setText("profileEmailValue", user.email);
        setText("profileCreated", UI.formatDate(user.created_at));
        setText("profileStatus", user.status === "active" ? "Active" : "Disabled");

        var role = document.getElementById("profileRole");
        if (role) {
            role.textContent = user.role === "admin" ? "Administrator" : "Standard user";
        }
    }

    function setText(id, value) {
        var node = document.getElementById(id);
        if (node) { node.textContent = value === null || value === undefined ? "—" : value; }
    }

    function renderStorage(stats) {
        if (!stats) { return; }

        var percent = Math.min(stats.used_percent || 0, 100);
        var tone = percent >= 90 ? "is-danger" : (percent >= 75 ? "is-warning" : "");

        [document.getElementById("sidebarStorageBar"),
         document.getElementById("profileStorageBar")].forEach(function (bar) {
            if (!bar) { return; }
            bar.style.width = percent + "%";
            bar.className = "meter-fill " + tone;
        });

        setText("sidebarStoragePct", Math.round(percent) + "%");

        var text = UI.formatMB(stats.storage_used !== undefined ? stats.storage_used : stats.used_storage) +
            " of " +
            UI.formatMB(stats.storage_limit !== undefined ? stats.storage_limit : stats.total_storage) +
            " used";
        setText("sidebarStorageText", text);

        if (state.plan) {
            setText("sidebarPlanName", state.plan.name);
        }

        setText("profileStorageUsed", text);
        setText("profileStoragePct", Math.round(percent) + "%");
        setText(
            "profileStorageNote",
            UI.formatMB(stats.available_storage) + " still available on your plan."
        );
    }

    function renderNavCounts(stats) {
        if (!stats) { return; }
        document.querySelectorAll(".nav-count").forEach(function (badge) {
            var value = stats[badge.dataset.count];
            badge.textContent = value;
            badge.classList.toggle("is-hidden", !value);
        });
    }


    /* ---------------------------------------------------------------------
       Notifications
       ------------------------------------------------------------------ */

    /**
     * There is no notifications table in the schema, so the list is derived
     * from real data the API already exposes: files shared with you, your own
     * recent activity and the live storage figure. Read state is per-browser.
     */
    function readIds() {
        try {
            return JSON.parse(localStorage.getItem(READ_KEY) || "[]");
        } catch (e) {
            return [];
        }
    }

    function markRead(ids) {
        try {
            var merged = readIds().concat(ids);
            localStorage.setItem(READ_KEY, JSON.stringify(merged.slice(-200)));
        } catch (e) { /* private mode */ }
    }

    var ACTIVITY_NOTIF = {
        UPLOAD: { icon: "cloud-arrow-up", text: "Uploaded" },
        DOWNLOAD: { icon: "download", text: "Downloaded" },
        SHARE_FILE: { icon: "share", text: "Shared" },
        DELETE_FILE: { icon: "trash3", text: "Moved to Trash" },
        PERMANENT_DELETE: { icon: "fire", text: "Permanently deleted" },
        RESTORE_FILE: { icon: "arrow-counterclockwise", text: "Restored" },
        CREATE_FOLDER: { icon: "folder-plus", text: "Created folder" }
    };

    async function loadNotifications() {
        var list = document.getElementById("notifList");
        if (!list) { return; }

        UI.skeletonRows(3, list);

        var items = [];

        try {
            var received = await API.shares.received();
            received.slice(0, 5).forEach(function (share) {
                items.push({
                    id: "share-" + share.id,
                    icon: "people-fill",
                    text: (share.shared_by_name || "Someone") + " shared " + share.file_name,
                    at: share.created_at,
                    href: "shared.html"
                });
            });
        } catch (e) { /* non-fatal: the panel degrades to activity only */ }

        try {
            var activity = await API.activity.list(8);
            activity.forEach(function (entry) {
                var spec = ACTIVITY_NOTIF[entry.activity];
                if (!spec || !entry.file_name) { return; }
                items.push({
                    id: "act-" + entry.id,
                    icon: spec.icon,
                    text: spec.text + " " + entry.file_name,
                    at: entry.activity_time,
                    href: "activity.html"
                });
            });
        } catch (e) { /* non-fatal */ }

        if (state.stats && state.stats.used_percent >= 80) {
            items.unshift({
                id: "storage-" + Math.round(state.stats.used_percent),
                icon: "exclamation-triangle-fill",
                text: "Storage is " + Math.round(state.stats.used_percent) + "% full",
                at: new Date().toISOString(),
                href: "storage.html"
            });
        }

        items.sort(function (a, b) {
            return (UI.toDate(b.at) || 0) - (UI.toDate(a.at) || 0);
        });
        items = items.slice(0, 12);

        var seen = readIds();
        var unread = items.filter(function (item) { return seen.indexOf(item.id) === -1; });

        var dot = document.getElementById("notifDot");
        if (dot) { dot.classList.toggle("is-hidden", unread.length === 0); }

        UI.clear(list);

        if (!items.length) {
            list.appendChild(UI.emptyState({
                icon: "bell-slash",
                title: "No notifications",
                message: "Activity on your account will show up here."
            }));
            return;
        }

        items.forEach(function (item) {
            var isUnread = seen.indexOf(item.id) === -1;

            var row = el("button", "notif-item" + (isUnread ? " is-unread" : ""));
            row.type = "button";

            var badge = el("span", "ni-icon");
            badge.appendChild(icon(item.icon));
            row.appendChild(badge);

            var body = el("div", "ni-body");
            body.appendChild(el("div", "ni-text", item.text));
            body.appendChild(el("div", "ni-time", UI.timeAgo(item.at)));
            row.appendChild(body);

            row.addEventListener("click", function () {
                markRead([item.id]);
                location.href = item.href;
            });

            list.appendChild(row);
        });

        state.notifIds = items.map(function (item) { return item.id; });
    }


    /* ---------------------------------------------------------------------
       Global search
       ------------------------------------------------------------------ */

    function wireSearch() {
        var input = document.getElementById("globalSearch");
        var panel = document.getElementById("searchResults");
        if (!input || !panel) { return; }

        var cursor = -1;

        function closePanel() {
            panel.classList.remove("show");
            input.setAttribute("aria-expanded", "false");
            cursor = -1;
        }

        function openPanel() {
            panel.classList.add("show");
            input.setAttribute("aria-expanded", "true");
        }

        function options() {
            return Array.prototype.slice.call(panel.querySelectorAll(".sr-item"));
        }

        function moveCursor(delta) {
            var list = options();
            if (!list.length) { return; }
            cursor = (cursor + delta + list.length) % list.length;
            list.forEach(function (node, index) {
                node.classList.toggle("is-cursor", index === cursor);
            });
            list[cursor].scrollIntoView({ block: "nearest" });
        }

        var run = UI.debounce(async function () {
            var term = input.value.trim();

            if (term.length < 2) {
                closePanel();
                return;
            }

            openPanel();
            UI.skeletonRows(3, panel);

            var results;
            try {
                results = await API.search(term);
            } catch (err) {
                UI.fill(panel, el("div", "sr-empty", err.message));
                return;
            }

            UI.clear(panel);

            var total = results.files.length + results.folders.length + results.shared.length;
            if (!total) {
                panel.appendChild(el("div", "sr-empty", 'No matches for "' + term + '"'));
                return;
            }

            function group(label, rows) {
                if (!rows.length) { return; }
                panel.appendChild(el("div", "sr-group-label", label));
                rows.forEach(function (row) { panel.appendChild(row); });
            }

            group("Folders", results.folders.slice(0, 5).map(function (folder) {
                return searchRow(UI.folderChip("sm"), folder.folder_name, "Folder", function () {
                    location.href = "files.html?folder=" + folder.id;
                });
            }));

            group("Files", results.files.slice(0, 6).map(function (file) {
                return searchRow(
                    UI.typeChip(file.original_name, file.file_type, "sm"),
                    file.original_name,
                    UI.formatSize(file.file_size),
                    function () { Files.openDetails(file); }
                );
            }));

            group("Shared with me", results.shared.slice(0, 4).map(function (share) {
                return searchRow(
                    UI.typeChip(share.file_name, share.file_type, "sm"),
                    share.file_name,
                    "from " + (share.shared_by_name || "someone"),
                    function () { location.href = "shared.html"; }
                );
            }));

            var seeAll = el("button", "sr-item");
            seeAll.type = "button";
            var allChip = el("span", "ftype ftype-sm");
            allChip.appendChild(icon("search"));
            seeAll.appendChild(allChip);
            seeAll.appendChild(el("span", "sr-name", 'See all results for "' + term + '"'));
            seeAll.addEventListener("click", function () {
                location.href = "files.html?q=" + encodeURIComponent(term);
            });
            panel.appendChild(seeAll);
        }, 260);

        function searchRow(chip, name, sub, onPick) {
            var row = el("button", "sr-item");
            row.type = "button";
            row.setAttribute("role", "option");
            row.appendChild(chip);
            row.appendChild(el("span", "sr-name", name));
            row.appendChild(el("span", "sr-sub", sub));
            row.addEventListener("click", function () {
                closePanel();
                onPick();
            });
            return row;
        }

        input.addEventListener("input", run);
        input.addEventListener("focus", function () {
            if (input.value.trim().length >= 2) { openPanel(); }
        });

        input.addEventListener("keydown", function (e) {
            if (e.key === "ArrowDown") { e.preventDefault(); moveCursor(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); moveCursor(-1); }
            else if (e.key === "Enter") {
                var list = options();
                if (cursor >= 0 && list[cursor]) {
                    e.preventDefault();
                    list[cursor].click();
                } else if (input.value.trim()) {
                    e.preventDefault();
                    location.href = "files.html?q=" + encodeURIComponent(input.value.trim());
                }
            } else if (e.key === "Escape") {
                closePanel();
                input.blur();
            }
        });

        document.addEventListener("click", function (e) {
            if (!panel.contains(e.target) && e.target !== input) { closePanel(); }
        });

        // Ctrl/Cmd + K focuses search from anywhere.
        document.addEventListener("keydown", function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                input.focus();
                input.select();
            }
        });
    }


    /* ---------------------------------------------------------------------
       Wiring
       ------------------------------------------------------------------ */

    function wireSidebarToggle() {
        var toggle = document.getElementById("sidebarToggle");
        var sidebar = document.getElementById("appSidebar");
        if (!toggle || !sidebar) { return; }

        var scrim = el("div", "sidebar-scrim");
        document.body.appendChild(scrim);

        function open(isOpen) {
            sidebar.classList.toggle("is-open", isOpen);
            scrim.classList.toggle("is-open", isOpen);
            toggle.setAttribute("aria-expanded", String(isOpen));
            document.body.style.overflow = isOpen ? "hidden" : "";
        }

        toggle.addEventListener("click", function () {
            open(!sidebar.classList.contains("is-open"));
        });
        scrim.addEventListener("click", function () { open(false); });

        sidebar.addEventListener("click", function (e) {
            if (e.target.closest(".nav-item")) { open(false); }
        });

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && sidebar.classList.contains("is-open")) { open(false); }
        });
    }

    function wireTheme() {
        var button = document.getElementById("themeToggle");
        if (!button) { return; }

        button.addEventListener("click", function () {
            var next = resolveTheme(storedThemeMode()) === "dark" ? "light" : "dark";
            setThemeMode(next);
            UI.fill(button, icon(next === "dark" ? "sun" : "moon-stars"));

            // Persist to the account so it follows the user to other devices.
            API.settings.update({ theme: next }).catch(function () { /* local still applied */ });
            document.dispatchEvent(new CustomEvent("Cloud:theme", { detail: next }));
        });
    }

    function wireNewMenu() {
        var folderBtn = document.getElementById("menuNewFolder");
        var wordBtn = document.getElementById("menuNewWord");
        var excelBtn = document.getElementById("menuNewExcel");
        var filesBtn = document.getElementById("menuUploadFiles");
        var dirBtn = document.getElementById("menuUploadFolder");

        if (folderBtn) {
            folderBtn.addEventListener("click", async function () {
                var name = await UI.promptDialog({
                    title: "New folder",
                    label: "Folder name",
                    placeholder: "Untitled folder",
                    confirmText: "Create"
                });
                if (!name) { return; }

                try {
                    await API.folders.create(name, state.uploadFolderId);
                    UI.toast("Folder created", "success");
                    document.dispatchEvent(new CustomEvent("Cloud:refresh"));
                    refreshStats();
                } catch (err) {
                    UI.reportError(err);
                }
            });
        }

        if (wordBtn) {
            wordBtn.addEventListener("click", async function () {
                var name = await UI.promptDialog({
                    title: "Create Word Document",
                    label: "File name",
                    placeholder: "Project Report",
                    confirmText: "Create"
                });
                if (!name) { return; }
                try {
                    var created = await API.files.create({ name: name, type: "word", folder_id: state.uploadFolderId });
                    location.href = "editor.html?id=" + created.id + "&type=word";
                } catch (err) {
                    UI.reportError(err);
                }
            });
        }

        if (excelBtn) {
            excelBtn.addEventListener("click", async function () {
                var name = await UI.promptDialog({
                    title: "Create Excel Spreadsheet",
                    label: "File name",
                    placeholder: "Sales Report",
                    confirmText: "Create"
                });
                if (!name) { return; }
                try {
                    var created = await API.files.create({ name: name, type: "excel", folder_id: state.uploadFolderId });
                    location.href = "editor.html?id=" + created.id + "&type=excel";
                } catch (err) {
                    UI.reportError(err);
                }
            });
        }

        if (filesBtn) {
            filesBtn.addEventListener("click", function () { Upload.pickFiles(); });
        }

        if (dirBtn) {
            dirBtn.addEventListener("click", function () { Upload.pickFolder(); });
        }
    }

    function wireProfile() {
        var modalHost = document.getElementById("profileModal");
        if (!modalHost) { return; }

        var modal = new bootstrap.Modal(modalHost);

        function openProfile() { modal.show(); }

        var sidebarUser = document.getElementById("sidebarUser");
        if (sidebarUser) { sidebarUser.addEventListener("click", openProfile); }

        var menuProfile = document.getElementById("menuProfile");
        if (menuProfile) { menuProfile.addEventListener("click", openProfile); }

        // Tabs
        modalHost.querySelectorAll(".profile-tabs button").forEach(function (tab) {
            tab.addEventListener("click", function () {
                modalHost.querySelectorAll(".profile-tabs button").forEach(function (other) {
                    other.setAttribute("aria-selected", String(other === tab));
                });
                modalHost.querySelectorAll(".profile-pane").forEach(function (pane) {
                    pane.classList.toggle("is-hidden", pane.dataset.pane !== tab.dataset.tab);
                });
            });
        });

        // Avatar upload
        var avatarBtn = document.getElementById("profileAvatarBtn");
        var avatarInput = document.getElementById("profileAvatarInput");

        if (avatarBtn && avatarInput) {
            avatarBtn.addEventListener("click", function () { avatarInput.click(); });

            avatarInput.addEventListener("change", async function () {
                var file = this.files[0];
                this.value = "";
                if (!file) { return; }

                try {
                    state.user = await API.users.uploadAvatar(file);
                    renderUser();
                    UI.toast("Profile photo updated", "success");
                } catch (err) {
                    UI.reportError(err);
                }
            });
        }

        // Edit profile
        var editBtn = document.getElementById("profileEditBtn");
        var editHost = document.getElementById("editProfileModal");
        var editModal = editHost ? new bootstrap.Modal(editHost) : null;

        if (editBtn && editModal) {
            editBtn.addEventListener("click", function () {
                document.getElementById("editFullname").value = state.user.fullname;
                document.getElementById("editUsername").value = state.user.username;
                document.getElementById("editEmail").value = state.user.email;
                modal.hide();
                editModal.show();
            });

            document.getElementById("editProfileForm").addEventListener("submit", async function (e) {
                e.preventDefault();

                var submit = this.querySelector("button[type=submit]");
                submit.disabled = true;

                try {
                    state.user = await API.users.updateProfile({
                        fullname: document.getElementById("editFullname").value.trim(),
                        username: document.getElementById("editUsername").value.trim(),
                        email: document.getElementById("editEmail").value.trim()
                    });
                    renderUser();
                    UI.toast("Profile updated", "success");
                    editModal.hide();
                } catch (err) {
                    UI.reportError(err);
                } finally {
                    submit.disabled = false;
                }
            });
        }

        // Password change
        var pwForm = document.getElementById("profilePasswordForm");
        if (pwForm) {
            pwForm.addEventListener("submit", async function (e) {
                e.preventDefault();

                var current = document.getElementById("pmCurrentPassword");
                var next = document.getElementById("pmNewPassword");
                var confirm = document.getElementById("pmConfirmPassword");

                if (next.value !== confirm.value) {
                    UI.toast("New passwords do not match", "error");
                    return;
                }
                if (next.value.length < 6) {
                    UI.toast("Password must be at least 6 characters", "error");
                    return;
                }

                var submit = this.querySelector("button[type=submit]");
                submit.disabled = true;

                try {
                    await API.users.changePassword({
                        current_password: current.value,
                        new_password: next.value
                    });
                    pwForm.reset();
                    UI.toast("Password updated", "success");
                } catch (err) {
                    UI.reportError(err);
                } finally {
                    submit.disabled = false;
                }
            });
        }

        // Logout
        [document.getElementById("menuLogout"),
         document.getElementById("profileLogoutBtn")].forEach(function (button) {
            if (!button) { return; }
            button.addEventListener("click", async function () {
                var yes = await UI.confirmDialog({
                    title: "Log out?",
                    message: "You will need to sign in again to reach your files.",
                    confirmText: "Log out"
                });
                if (!yes) { return; }

                try {
                    await API.auth.logout();
                } catch (e) {
                    // Clearing the local session matters more than the round trip.
                }
                API.clearSession();
                location.href = "login.html";
            });
        });
    }

    function wireNotifications() {
        var button = document.getElementById("notifBtn");
        if (button) {
            button.addEventListener("show.bs.dropdown", loadNotifications);
            button.parentElement.addEventListener("show.bs.dropdown", loadNotifications);
        }

        var markAll = document.getElementById("notifMarkAll");
        if (markAll) {
            markAll.addEventListener("click", function () {
                markRead(state.notifIds || []);
                document.querySelectorAll(".notif-item.is-unread").forEach(function (node) {
                    node.classList.remove("is-unread");
                });
                var dot = document.getElementById("notifDot");
                if (dot) { dot.classList.add("is-hidden"); }
            });
        }
    }


    /* ---------------------------------------------------------------------
       Boot
       ------------------------------------------------------------------ */

    async function refreshStats() {
        try {
            state.stats = await API.dashboard.get();

            // The plan is what the storage figure is measured against, so it is
            // fetched alongside rather than left to the Storage page.
            try {
                var mine = await API.plans.mine();
                state.plan = mine.plan;
            } catch (e) { /* the widget falls back to the word "Storage" */ }

            renderStorage(state.stats);
            renderNavCounts(state.stats);
            document.dispatchEvent(new CustomEvent("Cloud:stats", { detail: state.stats }));
        } catch (err) {
            if (err.status === 401) { UI.reportError(err); }
        }
    }

    /** Guard + shell render. Every signed-in page starts here. */
    async function mount(options) {
        options = options || {};
        state.active = options.active || null;

        applyTheme(storedThemeMode());

        if (!API.getToken()) {
            location.replace("login.html?next=" + encodeURIComponent(location.pathname.split("/").pop()));
            return null;
        }

        try {
            state.user = await API.auth.me();
        } catch (err) {
            API.clearSession();
            location.replace("login.html");
            return null;
        }

        var sidebarHost = document.getElementById("appSidebar");
        var headerHost = document.getElementById("appHeader");
        if (sidebarHost) { buildSidebar(sidebarHost); }
        if (headerHost) { buildHeader(headerHost); }

        buildProfileModal();
        buildEditProfileModal();

        renderUser();

        wireSidebarToggle();
        wireTheme();
        wireNewMenu();
        wireProfile();
        wireNotifications();
        wireSearch();

        if (global.Upload) { Upload.init(); }

        // Settings come from the account; local mode wins when it is "system".
        API.settings.get().then(function (settings) {
            state.settings = settings;
            if (storedThemeMode() !== "system" && settings.theme !== storedThemeMode()) {
                setThemeMode(settings.theme);
                var button = document.getElementById("themeToggle");
                if (button) {
                    UI.fill(button, icon(settings.theme === "dark" ? "sun" : "moon-stars"));
                }
            }
            document.dispatchEvent(new CustomEvent("Cloud:settings", { detail: settings }));
        }).catch(function () { /* the app works without it */ });

        refreshStats();

        return state.user;
    }

    global.Shell = {
        mount: mount,
        refreshStats: refreshStats,
        renderUser: renderUser,
        applyTheme: applyTheme,
        setThemeMode: setThemeMode,
        storedThemeMode: storedThemeMode,
        resolveTheme: resolveTheme,
        get user() { return state.user; },
        get stats() { return state.stats; },
        get uploadFolderId() { return state.uploadFolderId; },
        set uploadFolderId(value) { state.uploadFolderId = value; }
    };
}(window));
