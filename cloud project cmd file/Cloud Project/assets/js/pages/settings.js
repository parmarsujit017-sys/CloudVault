/* =========================================================================
   SETTINGS
   Theme, notifications and language persist to the settings table through
   PUT /api/settings. The password form uses PUT /api/users/me/password.

   Note on "System": the database stores theme as light|dark, so the System
   choice is kept in this browser and the resolved value is what gets saved
   to the account.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var state = { settings: null };

    var LANGUAGES = ["English", "Hindi", "Gujarati"];


    /* ---------------------------------------------------------------------
       Appearance
       ------------------------------------------------------------------ */

    var THEMES = [
        { key: "light", label: "Light", preview: "tc-light" },
        { key: "dark", label: "Dark", preview: "tc-dark" },
        { key: "system", label: "System", preview: "tc-system" }
    ];

    function renderThemeChoices() {
        var host = document.getElementById("themeChoices");
        UI.clear(host);

        var current = Shell.storedThemeMode();

        THEMES.forEach(function (spec) {
            var label = el("label", "theme-choice");

            var input = document.createElement("input");
            input.type = "radio";
            input.name = "theme";
            input.value = spec.key;
            input.checked = spec.key === current;

            var box = el("div", "tc-box");

            var preview = el("div", "tc-preview " + spec.preview);
            preview.appendChild(el("div", "p-side"));
            preview.appendChild(el("div", "p-main"));
            box.appendChild(preview);

            box.appendChild(el("div", "tc-label", spec.label));

            label.appendChild(input);
            label.appendChild(box);

            input.addEventListener("change", async function () {
                Shell.setThemeMode(spec.key);

                var resolved = Shell.resolveTheme(spec.key);
                try {
                    state.settings = await API.settings.update({ theme: resolved });
                    UI.toast("Theme updated", "success");
                } catch (err) {
                    UI.reportError(err);
                }
            });

            host.appendChild(label);
        });
    }


    /* ---------------------------------------------------------------------
       General (notifications + language)
       ------------------------------------------------------------------ */

    function settingRow(title, description, control) {
        var row = el("div", "setting-row");

        var text = el("div", "sr-text");
        text.appendChild(el("strong", null, title));
        text.appendChild(el("span", null, description));
        row.appendChild(text);

        var wrap = el("div", "sr-control");
        wrap.appendChild(control);
        row.appendChild(wrap);

        return row;
    }

    async function save(patch, successMessage) {
        try {
            state.settings = await API.settings.update(patch);
            UI.toast(successMessage, "success");
            return true;
        } catch (err) {
            UI.reportError(err);
            return false;
        }
    }

    function renderGeneral() {
        var host = document.getElementById("generalHost");
        UI.clear(host);

        // Notifications
        var switchWrap = el("div", "form-check form-switch");
        switchWrap.style.display = "flex";
        switchWrap.style.justifyContent = "flex-end";
        switchWrap.style.margin = "0";

        var toggle = document.createElement("input");
        toggle.type = "checkbox";
        toggle.className = "form-check-input";
        toggle.id = "notificationsToggle";
        toggle.checked = Boolean(state.settings.notifications);
        toggle.setAttribute("role", "switch");
        toggle.setAttribute("aria-label", "Enable notifications");
        switchWrap.appendChild(toggle);

        toggle.addEventListener("change", async function () {
            var ok = await save(
                { notifications: toggle.checked },
                toggle.checked ? "Notifications enabled" : "Notifications disabled"
            );
            if (!ok) { toggle.checked = !toggle.checked; }
        });

        host.appendChild(settingRow(
            "Notifications",
            "Show share and upload notices in the header bell.",
            switchWrap
        ));

        // Language
        var select = document.createElement("select");
        select.id = "languageSelect";
        select.setAttribute("aria-label", "Language");

        LANGUAGES.forEach(function (language) {
            var option = document.createElement("option");
            option.value = language;
            option.textContent = language;
            option.selected = language === state.settings.language;
            select.appendChild(option);
        });

        select.addEventListener("change", async function () {
            var previous = state.settings.language;
            var ok = await save({ language: select.value }, "Language set to " + select.value);
            if (!ok) { select.value = previous; }
        });

        host.appendChild(settingRow(
            "Language",
            "The language stored on your account.",
            select
        ));
    }


    /* ---------------------------------------------------------------------
       Account + storage summaries
       ------------------------------------------------------------------ */

    function renderAccount(user) {
        var host = document.getElementById("accountHost");
        UI.clear(host);

        var top = el("div");
        top.style.display = "flex";
        top.style.alignItems = "center";
        top.style.gap = "12px";
        top.style.marginBottom = "16px";

        var img = document.createElement("img");
        img.className = "avatar avatar-lg";
        img.src = user.profile_image
            ? API.users.avatarUrl() + "?v=" + encodeURIComponent(user.profile_image)
            : "assets/img/profile.png";
        img.alt = "";
        img.addEventListener("error", function () { this.src = "assets/img/profile.png"; });
        top.appendChild(img);

        var who = el("div");
        who.style.minWidth = "0";
        var name = el("div", "truncate", user.fullname);
        name.style.fontWeight = "600";
        who.appendChild(name);
        who.appendChild(el("div", "text-meta truncate", user.email));
        top.appendChild(who);

        host.appendChild(top);

        function row(key, value) {
            var node = el("div", "kv-row");
            node.appendChild(el("span", "k", key));
            node.appendChild(el("span", "v", value));
            return node;
        }

        host.appendChild(row("Username", user.username));
        host.appendChild(row("Role", user.role === "admin" ? "Administrator" : "Standard user"));
        host.appendChild(row("Status", user.status === "active" ? "Active" : "Disabled"));
        host.appendChild(row("Member since", UI.formatDate(user.created_at)));

        var edit = el("button", "btn-app-ghost btn-block", "Edit profile");
        edit.type = "button";
        edit.style.marginTop = "16px";
        edit.addEventListener("click", function () {
            document.getElementById("sidebarUser").click();
        });
        host.appendChild(edit);
    }

    function renderStorageSummary(stats) {
        var host = document.getElementById("settingsStorageHost");
        UI.clear(host);

        if (!stats) {
            UI.skeletonRows(2, host);
            return;
        }

        var percent = Math.min(stats.used_percent || 0, 100);

        var head = el("div");
        head.style.display = "flex";
        head.style.justifyContent = "space-between";
        head.style.fontSize = "13.5px";
        head.style.marginBottom = "8px";
        head.appendChild(el("strong", null, UI.formatMB(stats.storage_used)));
        head.appendChild(el("span", "text-dim", "of " + UI.formatMB(stats.storage_limit)));
        host.appendChild(head);

        var meter = el("div", "meter");
        var fill = el("div", "meter-fill " +
            (percent >= 90 ? "is-danger" : (percent >= 75 ? "is-warning" : "")));
        fill.style.width = percent + "%";
        meter.appendChild(fill);
        host.appendChild(meter);

        var note = el("p", "text-meta", UI.formatMB(stats.available_storage) + " available.");
        note.style.marginTop = "8px";
        host.appendChild(note);

        var link = el("a", "btn-app-ghost btn-block", "Storage details");
        link.href = "storage.html";
        link.style.marginTop = "16px";
        host.appendChild(link);
    }


    /* ---------------------------------------------------------------------
       Password
       ------------------------------------------------------------------ */

    function wirePasswordForm() {
        var form = document.getElementById("passwordForm");

        form.addEventListener("submit", async function (e) {
            e.preventDefault();

            var current = document.getElementById("currentPassword");
            var next = document.getElementById("newPassword");
            var confirm = document.getElementById("confirmPassword");
            var submit = form.querySelector("button[type=submit]");

            if (next.value.length < 6) {
                UI.toast("New password must be at least 6 characters", "error");
                next.focus();
                return;
            }
            if (next.value !== confirm.value) {
                UI.toast("New passwords do not match", "error");
                confirm.focus();
                return;
            }

            submit.disabled = true;

            try {
                await API.users.changePassword({
                    current_password: current.value,
                    new_password: next.value
                });
                form.reset();
                UI.toast("Password updated", "success");
            } catch (err) {
                UI.reportError(err);
                if (err.status === 400) { current.focus(); }
            } finally {
                submit.disabled = false;
            }
        });
    }


    /* ---------------------------------------------------------------------
       Boot
       ------------------------------------------------------------------ */

    async function boot() {
        var user = await Shell.mount({ active: "settings" });
        if (!user) { return; }

        renderThemeChoices();
        renderAccount(user);
        renderStorageSummary(Shell.stats);
        wirePasswordForm();

        // The shell may already have the settings; otherwise fetch them.
        try {
            state.settings = await API.settings.get();
            renderGeneral();
        } catch (err) {
            UI.reportError(err);
        }

        document.addEventListener("Cloud:stats", function (e) {
            renderStorageSummary(e.detail);
        });

        // Keep the theme cards in step with the header quick-toggle.
        document.addEventListener("Cloud:theme", renderThemeChoices);
    }

    boot();
}());
