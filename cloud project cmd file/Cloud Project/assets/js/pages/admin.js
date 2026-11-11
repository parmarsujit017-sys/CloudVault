/* =========================================================================
   ADMIN PANEL
   Served at /admin. One page with two states: a sign-in gate, and the panel
   behind it.

   The gate is not the security boundary - every endpoint under /api/admin is
   guarded server-side by the admin role. What the gate does is refuse to show
   a half-broken panel to somebody whose account cannot drive it.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var GB = 1024;                       // MB in a GB, since limits are stored in MB
    var THEME_KEY = "cloudvault_theme";

    var nodes = {};
    var state = {
        admin: null,
        view: "overview",
        plans: [],
        stats: null,
        users: { total: 0, page: 1, pages: 1, users: [] },
        query: "",
        planFilter: "",
        statusFilter: "",
        currency: "₹"
    };


    /* =====================================================================
       Small helpers
       ================================================================== */

    function money(value) {
        var amount = Number(value) || 0;
        // Whole rupees read better than trailing ".00" on a pricing table.
        var text = amount % 1 === 0 ? String(amount) : amount.toFixed(2);
        return state.currency + text.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    /** Storage limits are MB in the database but GB/TB in every conversation. */
    function storageLabel(mb) {
        return UI.formatMB(mb);
    }

    function kv(key, value) {
        var row = el("div", "kv-row");
        row.appendChild(el("span", "k", key));
        row.appendChild(el("span", "v", value));
        return row;
    }

    /**
     * `neutral` skips the amber/red thresholds. Those mean "running out of
     * room", which is the wrong thing to say about a share-of-subscribers bar -
     * there the largest plan would come out bright red for doing well.
     */
    function meter(percent, neutral) {
        var bar = el("div", "meter");
        var fill = el("div", "meter-fill");
        fill.style.width = Math.min(100, Math.max(0, percent)) + "%";

        if (!neutral) {
            if (percent >= 90) { fill.style.background = "var(--danger)"; }
            else if (percent >= 75) { fill.style.background = "var(--warning)"; }
        }

        bar.appendChild(fill);
        return bar;
    }

    function badge(text, tone) {
        return el("span", "badge-soft" + (tone ? " is-" + tone : ""), text);
    }

    function planBadge(user) {
        if (!user.plan_name) { return badge("No plan", "muted"); }
        if (user.plan_is_expired) { return badge(user.plan_name + " · expired", "danger"); }

        var tone = user.billing_cycle === "free" ? "muted" : "success";
        var suffix = user.billing_cycle && user.billing_cycle !== "free"
            ? " · " + user.billing_cycle
            : "";
        return badge(user.plan_name + suffix, tone);
    }

    function field(labelText, control, hint) {
        var wrap = el("div", "field");
        var label = el("label", null, labelText);
        label.htmlFor = control.id;
        wrap.appendChild(label);
        wrap.appendChild(control);
        if (hint) { wrap.appendChild(el("div", "hint", hint)); }
        return wrap;
    }

    function input(id, type, value, attrs) {
        var node = document.createElement("input");
        node.type = type || "text";
        node.id = id;
        if (value !== undefined && value !== null) { node.value = value; }
        Object.keys(attrs || {}).forEach(function (key) {
            node.setAttribute(key, attrs[key]);
        });
        return node;
    }

    function select(id, options, selected) {
        var node = document.createElement("select");
        node.id = id;
        options.forEach(function (option) {
            var item = document.createElement("option");
            item.value = String(option.value);
            item.textContent = option.label;
            if (String(option.value) === String(selected)) { item.selected = true; }
            node.appendChild(item);
        });
        return node;
    }

    /** A generic modal with a form body; resolves with the submitted values. */
    function formModal(options) {
        return new Promise(function (resolve) {
            var host = el("div", "modal fade");
            host.tabIndex = -1;

            var dialog = el("div", "modal-dialog modal-dialog-centered" +
                (options.wide ? " modal-lg" : ""));
            var content = el("div", "modal-content");
            var form = document.createElement("form");
            form.noValidate = true;

            var header = el("div", "modal-header");
            header.appendChild(el("h2", "modal-title", options.title));
            var close = el("button", "btn-close");
            close.type = "button";
            close.setAttribute("data-bs-dismiss", "modal");
            close.setAttribute("aria-label", "Close");
            header.appendChild(close);

            var body = el("div", "modal-body");
            if (options.intro) { body.appendChild(el("p", "text-dim", options.intro)); }
            options.build(body);

            var error = el("div", "error-text is-hidden");
            error.setAttribute("role", "alert");
            body.appendChild(error);

            var footer = el("div", "modal-footer");
            var cancel = el("button", "btn-app-ghost", "Cancel");
            cancel.type = "button";
            cancel.setAttribute("data-bs-dismiss", "modal");
            var submit = el(
                "button",
                options.danger ? "btn-app-danger" : "btn-app-primary",
                options.confirmText || "Save"
            );
            submit.type = "submit";
            footer.appendChild(cancel);
            footer.appendChild(submit);

            form.appendChild(header);
            form.appendChild(body);
            form.appendChild(footer);
            content.appendChild(form);
            dialog.appendChild(content);
            host.appendChild(dialog);
            document.body.appendChild(host);

            var modal = new bootstrap.Modal(host);
            var settled = false;

            form.addEventListener("submit", async function (e) {
                e.preventDefault();
                error.classList.add("is-hidden");

                var payload;
                try {
                    payload = options.read();
                } catch (validationError) {
                    error.textContent = validationError.message;
                    error.classList.remove("is-hidden");
                    return;
                }

                submit.disabled = true;
                try {
                    await options.submit(payload);
                    settled = true;
                    modal.hide();
                } catch (err) {
                    error.textContent = err.message || "That did not work";
                    error.classList.remove("is-hidden");
                } finally {
                    submit.disabled = false;
                }
            });

            host.addEventListener("hidden.bs.modal", function () {
                host.remove();
                resolve(settled);
            });

            modal.show();
        });
    }


    /* =====================================================================
       Sign in
       ================================================================== */

    function showGate(message) {
        nodes.gate.hidden = false;
        nodes.shell.hidden = true;

        if (message) {
            nodes.loginError.textContent = message;
            nodes.loginError.classList.remove("is-hidden");
        }
        nodes.username.focus();
    }

    function showPanel() {
        nodes.gate.hidden = true;
        nodes.shell.hidden = false;

        nodes.whoName.textContent = state.admin.fullname;
        nodes.whoUser.textContent = "@" + state.admin.username;
    }

    async function attempt(username, password) {
        nodes.loginError.classList.add("is-hidden");
        nodes.loginSubmit.disabled = true;

        try {
            var result = await API.auth.login(username, password);

            if (result.user.role !== "admin") {
                // Signed in fine, just not an administrator. Drop the session so
                // the page is not left half-authenticated.
                API.clearSession();
                showGate("That account is not an administrator.");
                return;
            }

            API.setSession(result.access_token, result.user);
            state.admin = result.user;
            showPanel();
            await boot();
        } catch (err) {
            showGate(err.status === 401 ? "Invalid username or password." : err.message);
        } finally {
            nodes.loginSubmit.disabled = false;
        }
    }

    function wireGate() {
        nodes.form.addEventListener("submit", function (e) {
            e.preventDefault();
            var username = nodes.username.value.trim();
            var password = nodes.password.value;

            if (!username || !password) {
                nodes.loginError.textContent = "Enter both a username and a password.";
                nodes.loginError.classList.remove("is-hidden");
                return;
            }
            attempt(username, password);
        });

        nodes.pwToggle.addEventListener("click", function () {
            var shown = nodes.password.type === "text";
            nodes.password.type = shown ? "password" : "text";
            UI.fill(nodes.pwToggle, icon(shown ? "eye" : "eye-slash"));
            nodes.pwToggle.setAttribute("aria-label", shown ? "Show password" : "Hide password");
            nodes.password.focus();
        });
    }


    /* =====================================================================
       Views
       ================================================================== */

    var VIEWS = {
        overview: {
            title: "Overview",
            sub: "Live figures across every account on this installation.",
            render: renderOverview
        },
        users: {
            title: "Users",
            sub: "Every account, what it is storing and which plan it is on.",
            render: renderUsers
        },
        plans: {
            title: "Plans",
            sub: "The packages you can assign. Prices are recorded for reference.",
            render: renderPlans
        }
    };

    function setView(name) {
        state.view = name;

        nodes.nav.querySelectorAll(".admin-nav-item").forEach(function (button) {
            button.classList.toggle("is-active", button.dataset.view === name);
        });

        var spec = VIEWS[name];
        nodes.title.textContent = spec.title;
        nodes.sub.textContent = spec.sub;

        UI.clear(nodes.headActions);
        UI.clear(nodes.body);

        spec.render();
    }


    /* ---------------------------------------------------------------------
       Overview
       ------------------------------------------------------------------ */

    /** Reuses the dashboard's `.stat` component so both screens look the same. */
    function statCard(label, value, iconName, note, tone) {
        var card = el("div", "stat");

        var chip = el("div", "stat-icon" + (tone ? " " + tone : ""));
        chip.appendChild(icon(iconName));
        card.appendChild(chip);

        var body = el("div");
        body.style.minWidth = "0";
        body.appendChild(el("div", "stat-label", label));
        body.appendChild(el("div", "stat-value", value));
        if (note) { body.appendChild(el("div", "stat-note", note)); }
        card.appendChild(body);

        return card;
    }

    async function renderOverview() {
        var skeleton = el("div", "stat-grid");
        UI.skeletonCards(6, skeleton);
        nodes.body.appendChild(skeleton);

        var stats;
        try {
            stats = await API.admin.stats();
        } catch (err) {
            UI.fill(nodes.body, UI.emptyState({
                icon: "wifi-off", title: "Could not load the overview", message: err.message
            }));
            return;
        }

        state.stats = stats;
        state.currency = stats.currency_symbol || state.currency;
        nodes.navUsers.textContent = stats.total_users;
        nodes.navPlans.textContent = stats.total_plans;

        UI.clear(nodes.body);

        var grid = el("div", "stat-grid");
        grid.appendChild(statCard(
            "Total users", String(stats.total_users), "people",
            stats.new_users_30d + " joined in the last 30 days"
        ));
        grid.appendChild(statCard(
            "Active accounts", String(stats.active_users), "person-check",
            stats.disabled_users ? stats.disabled_users + " disabled" : "None disabled",
            "is-green"
        ));
        grid.appendChild(statCard(
            "Storage used", storageLabel(stats.storage_used), "hdd",
            "of " + storageLabel(stats.storage_allocated) + " allocated",
            "is-purple"
        ));
        grid.appendChild(statCard(
            "Paid subscribers", String(stats.paid_subscribers), "gem",
            stats.free_subscribers + " on the free plan",
            "is-amber"
        ));
        grid.appendChild(statCard(
            "Monthly run rate", money(stats.monthly_revenue), "graph-up-arrow",
            "Yearly plans counted per month",
            "is-green"
        ));
        grid.appendChild(statCard(
            "Files stored", String(stats.total_files), "files",
            stats.total_folders + " folders",
            "is-purple"
        ));
        nodes.body.appendChild(grid);

        if (stats.expiring_soon) {
            var warn = el("div", "admin-alert");
            warn.appendChild(icon("exclamation-triangle-fill"));
            warn.appendChild(el("span", null,
                stats.expiring_soon + " paid subscription" +
                (stats.expiring_soon === 1 ? "" : "s") + " expire within 7 days."));
            nodes.body.appendChild(warn);
        }

        // ---- Plan breakdown -------------------------------------------
        var panel = el("div", "panel");
        var head = el("div", "panel-head");
        head.appendChild(el("h2", null, "Subscribers by plan"));
        panel.appendChild(head);

        var body = el("div", "panel-body is-flush");

        if (!stats.plan_breakdown.length) {
            body.appendChild(UI.emptyState({
                icon: "box-seam", title: "No plans yet",
                message: "Create a plan and it will show up here."
            }));
        } else {
            var wrap = el("div", "table-wrap");
            var scroll = el("div", "table-scroll");
            var table = el("table", "app-table");

            var thead = document.createElement("thead");
            var headRow = document.createElement("tr");
            ["Plan", "Subscribers", "Storage used", "Share"].forEach(function (text) {
                var th = document.createElement("th");
                th.textContent = text;
                headRow.appendChild(th);
            });
            thead.appendChild(headRow);
            table.appendChild(thead);

            var tbody = document.createElement("tbody");
            var maxSubs = Math.max.apply(null, stats.plan_breakdown.map(function (row) {
                return row.subscribers;
            }).concat([1]));

            stats.plan_breakdown.forEach(function (row) {
                var tr = document.createElement("tr");

                var nameCell = document.createElement("td");
                var wrapName = el("div", "cell-name");
                var chip = el("span", "ftype ftype-sm");
                if (row.is_free) { chip.dataset.type = "folder"; }
                chip.appendChild(icon(row.is_free ? "gift" : "gem"));
                wrapName.appendChild(chip);
                wrapName.appendChild(el("span", "n", row.name));
                nameCell.appendChild(wrapName);
                tr.appendChild(nameCell);

                var subs = document.createElement("td");
                subs.className = "num";
                subs.textContent = row.subscribers;
                tr.appendChild(subs);

                var used = document.createElement("td");
                used.className = "num";
                used.textContent = storageLabel(row.storage_used);
                tr.appendChild(used);

                var share = document.createElement("td");
                share.style.minWidth = "140px";
                share.appendChild(meter(row.subscribers / maxSubs * 100, true));
                tr.appendChild(share);

                tbody.appendChild(tr);
            });

            table.appendChild(tbody);
            scroll.appendChild(table);
            wrap.appendChild(scroll);
            body.appendChild(wrap);
        }

        panel.appendChild(body);
        nodes.body.appendChild(panel);
    }


    /* ---------------------------------------------------------------------
       Users
       ------------------------------------------------------------------ */

    function renderUsers() {
        var toolbar = el("div", "toolbar");

        var search = el("div", "header-search");
        search.style.maxWidth = "300px";
        search.style.flex = "0 1 300px";
        search.appendChild(icon("search"));
        var searchInput = input("adminUserSearch", "search", state.query, {
            placeholder: "Search name, username or email",
            "aria-label": "Search users",
            autocomplete: "off"
        });
        search.appendChild(searchInput);
        toolbar.appendChild(search);

        var planOptions = [{ value: "", label: "All plans" }].concat(
            state.plans.map(function (plan) {
                return { value: plan.code, label: plan.name };
            })
        );
        var planPicker = select("adminPlanFilter", planOptions, state.planFilter);
        planPicker.setAttribute("aria-label", "Filter by plan");
        planPicker.style.maxWidth = "180px";
        toolbar.appendChild(planPicker);

        var statusPicker = select("adminStatusFilter", [
            { value: "", label: "Any status" },
            { value: "active", label: "Active" },
            { value: "disabled", label: "Disabled" }
        ], state.statusFilter);
        statusPicker.setAttribute("aria-label", "Filter by status");
        statusPicker.style.maxWidth = "150px";
        toolbar.appendChild(statusPicker);

        toolbar.appendChild(el("div", "spacer"));

        var count = el("span", "text-meta");
        count.id = "adminUserTotal";
        toolbar.appendChild(count);

        nodes.body.appendChild(toolbar);

        var host = el("div");
        host.id = "adminUserHost";
        nodes.body.appendChild(host);

        searchInput.addEventListener("input", UI.debounce(function () {
            state.query = searchInput.value.trim();
            state.users.page = 1;
            loadUsers();
        }, 250));

        planPicker.addEventListener("change", function () {
            state.planFilter = planPicker.value;
            state.users.page = 1;
            loadUsers();
        });

        statusPicker.addEventListener("change", function () {
            state.statusFilter = statusPicker.value;
            state.users.page = 1;
            loadUsers();
        });

        loadUsers();
    }

    async function loadUsers() {
        var host = document.getElementById("adminUserHost");
        if (!host) { return; }

        var wrap = el("div", "table-wrap");
        UI.skeletonRows(6, wrap);
        UI.fill(host, wrap);

        var page;
        try {
            page = await API.admin.users({
                q: state.query,
                plan: state.planFilter,
                status: state.statusFilter,
                page: state.users.page
            });
        } catch (err) {
            UI.fill(host, UI.emptyState({
                icon: "wifi-off", title: "Could not load users", message: err.message
            }));
            return;
        }

        state.users = page;
        nodes.navUsers.textContent = state.stats ? state.stats.total_users : page.total;

        var total = document.getElementById("adminUserTotal");
        if (total) {
            total.textContent = page.total + (page.total === 1 ? " account" : " accounts");
        }

        UI.clear(host);

        if (!page.users.length) {
            host.appendChild(UI.emptyState({
                icon: "people",
                title: "No matching accounts",
                message: "Try a different search or clear the filters."
            }));
            return;
        }

        host.appendChild(userTable(page.users));

        if (page.pages > 1) {
            host.appendChild(pager(page));
        }
    }

    function userTable(users) {
        var wrap = el("div", "table-wrap");
        var scroll = el("div", "table-scroll");
        var table = el("table", "app-table");

        var thead = document.createElement("thead");
        var headRow = document.createElement("tr");
        ["User", "Plan", "Storage", "Status", "Joined", ""].forEach(function (text) {
            var th = document.createElement("th");
            if (text) { th.textContent = text; }
            else { th.className = "cell-actions"; th.setAttribute("aria-label", "Actions"); }
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        var tbody = document.createElement("tbody");

        users.forEach(function (user) {
            var row = document.createElement("tr");
            row.dataset.userId = user.id;

            // ---- identity ---------------------------------------------
            var nameCell = document.createElement("td");
            var wrapName = el("div", "cell-name");

            var chip = el("span", "ftype ftype-sm");
            if (user.role === "admin") { chip.dataset.type = "folder"; }
            chip.appendChild(icon(user.role === "admin" ? "shield-lock-fill" : "person-fill"));
            wrapName.appendChild(chip);

            var who = el("div");
            who.style.minWidth = "0";
            var name = el("div", "n", user.fullname);
            name.title = user.fullname;
            who.appendChild(name);
            who.appendChild(el("div", "text-meta truncate", user.email));
            wrapName.appendChild(who);

            nameCell.appendChild(wrapName);
            row.appendChild(nameCell);

            // ---- plan --------------------------------------------------
            var planCell = document.createElement("td");
            planCell.appendChild(planBadge(user));
            if (user.plan_ends_at) {
                planCell.appendChild(el("div", "text-meta",
                    (user.plan_is_expired ? "Expired " : "Renews ") +
                    UI.formatDate(user.plan_ends_at)));
            }
            row.appendChild(planCell);

            // ---- storage -----------------------------------------------
            var storageCell = document.createElement("td");
            storageCell.style.minWidth = "160px";
            storageCell.appendChild(el("div", "text-meta",
                storageLabel(user.storage_used) + " of " + storageLabel(user.storage_limit)));
            storageCell.appendChild(meter(user.used_percent));
            row.appendChild(storageCell);

            // ---- status ------------------------------------------------
            var statusCell = document.createElement("td");
            statusCell.appendChild(user.status === "active"
                ? badge("Active", "success")
                : badge("Disabled", "danger"));
            row.appendChild(statusCell);

            // ---- joined ------------------------------------------------
            var joined = document.createElement("td");
            joined.className = "num";
            joined.textContent = UI.formatDate(user.created_at);
            row.appendChild(joined);

            // ---- actions -----------------------------------------------
            var actionCell = document.createElement("td");
            actionCell.className = "cell-actions";

            var assign = el("button", "btn-app-ghost btn-sm-app");
            assign.type = "button";
            assign.appendChild(icon("box-seam"));
            assign.appendChild(el("span", null, "Assign plan"));
            assign.addEventListener("click", function () { assignPlanDialog(user); });
            actionCell.appendChild(assign);

            var more = Menu.dotTrigger("Actions for " + user.fullname, function () {
                return userMenuItems(user);
            });
            more.style.position = "static";
            more.style.opacity = "1";
            more.style.marginLeft = "4px";
            actionCell.appendChild(more);

            row.appendChild(actionCell);
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        scroll.appendChild(table);
        wrap.appendChild(scroll);
        return wrap;
    }

    function userMenuItems(user) {
        var self = state.admin && user.id === state.admin.id;

        return [
            { text: "View details", icon: "info-circle", onSelect: function () { userDetail(user); } },
            { text: "Assign plan", icon: "box-seam", onSelect: function () { assignPlanDialog(user); } },
            {
                text: "Revert to free plan",
                icon: "arrow-counterclockwise",
                disabled: user.billing_cycle === "free",
                onSelect: function () { revertPlan(user); }
            },
            { divider: true },
            {
                text: user.status === "active" ? "Disable account" : "Enable account",
                icon: user.status === "active" ? "pause-circle" : "play-circle",
                disabled: self,
                onSelect: function () { toggleStatus(user); }
            },
            {
                text: user.role === "admin" ? "Remove admin access" : "Make administrator",
                icon: "shield-lock",
                disabled: self,
                onSelect: function () { toggleRole(user); }
            },
            { divider: true },
            {
                text: "Delete account",
                icon: "trash3",
                danger: true,
                disabled: self,
                onSelect: function () { deleteUser(user); }
            }
        ];
    }

    function pager(page) {
        var bar = el("div", "admin-pager");

        var previous = el("button", "btn-app-ghost btn-sm-app", "Previous");
        previous.type = "button";
        previous.disabled = page.page <= 1;
        previous.addEventListener("click", function () {
            state.users.page = page.page - 1;
            loadUsers();
        });

        var next = el("button", "btn-app-ghost btn-sm-app", "Next");
        next.type = "button";
        next.disabled = page.page >= page.pages;
        next.addEventListener("click", function () {
            state.users.page = page.page + 1;
            loadUsers();
        });

        bar.appendChild(previous);
        bar.appendChild(el("span", "text-meta", "Page " + page.page + " of " + page.pages));
        bar.appendChild(next);
        return bar;
    }


    /* ---------------------------------------------------------------------
       User actions
       ------------------------------------------------------------------ */

    async function assignPlanDialog(user) {
        var assignable = state.plans.filter(function (plan) { return plan.is_active; });
        if (!assignable.length) {
            UI.toast("Create a plan first", "error");
            return;
        }

        var planPicker, cyclePicker, monthsInput, expiresBox, noteInput, preview;

        var done = await formModal({
            title: "Assign a plan to " + user.fullname,
            intro: "The storage allowance changes as soon as you save.",
            confirmText: "Assign plan",
            build: function (body) {
                planPicker = select("assignPlan", assignable.map(function (plan) {
                    return {
                        value: plan.id,
                        label: plan.name + " · " + storageLabel(plan.storage_mb)
                    };
                }), assignable[0].id);
                body.appendChild(field("Plan", planPicker));

                cyclePicker = select("assignCycle", [
                    { value: "monthly", label: "Monthly" },
                    { value: "yearly", label: "Yearly" }
                ], "monthly");
                body.appendChild(field("Billing cycle", cyclePicker));

                monthsInput = input("assignMonths", "number", 1, { min: "1", max: "120" });
                body.appendChild(field(
                    "Number of periods", monthsInput,
                    "How many months or years this grant covers."
                ));

                var expiresWrap = el("label", "admin-check");
                expiresBox = document.createElement("input");
                expiresBox.type = "checkbox";
                expiresBox.id = "assignExpires";
                expiresBox.checked = true;
                expiresWrap.appendChild(expiresBox);
                expiresWrap.appendChild(el("span", null, "This grant expires"));
                body.appendChild(expiresWrap);
                body.appendChild(el("div", "hint",
                    "Clear it for a comped account that should never lapse."));

                noteInput = input("assignNote", "text", "", {
                    placeholder: "Optional note, e.g. paid by invoice #142", maxlength: "255"
                });
                body.appendChild(field("Note", noteInput));

                preview = el("div", "admin-preview");
                body.appendChild(preview);

                function refresh() {
                    var plan = assignable.filter(function (item) {
                        return String(item.id) === planPicker.value;
                    })[0];
                    if (!plan) { return; }

                    var free = plan.is_free;
                    cyclePicker.disabled = free;
                    monthsInput.disabled = free || !expiresBox.checked;
                    expiresBox.disabled = free;

                    var price = cyclePicker.value === "yearly"
                        ? plan.price_yearly
                        : plan.price_monthly;
                    var periods = Math.max(1, Number(monthsInput.value) || 1);

                    UI.clear(preview);
                    preview.appendChild(el("strong", null, plan.name));
                    preview.appendChild(el("div", null,
                        "Storage becomes " + storageLabel(plan.storage_mb) +
                        " (was " + storageLabel(user.storage_limit) + ")"));

                    if (free) {
                        preview.appendChild(el("div", null, "Free plan · never expires"));
                    } else if (!expiresBox.checked) {
                        preview.appendChild(el("div", null,
                            money(price) + " per " + (cyclePicker.value === "yearly" ? "year" : "month") +
                            " · granted with no end date"));
                    } else {
                        preview.appendChild(el("div", null,
                            money(price * periods) + " total · " + periods + " " +
                            (cyclePicker.value === "yearly" ? "year" : "month") +
                            (periods === 1 ? "" : "s")));
                    }
                }

                [planPicker, cyclePicker, monthsInput, expiresBox].forEach(function (control) {
                    control.addEventListener("change", refresh);
                });
                monthsInput.addEventListener("input", refresh);
                refresh();
            },
            read: function () {
                var plan = assignable.filter(function (item) {
                    return String(item.id) === planPicker.value;
                })[0];
                if (!plan) { throw new Error("Choose a plan"); }

                var months = Number(monthsInput.value) || 1;
                if (months < 1 || months > 120) {
                    throw new Error("Number of periods must be between 1 and 120");
                }

                return {
                    plan_id: plan.id,
                    billing_cycle: plan.is_free ? "free" : cyclePicker.value,
                    months: months,
                    expires: plan.is_free ? true : expiresBox.checked,
                    note: noteInput.value.trim() || null
                };
            },
            submit: function (payload) {
                return API.admin.assignPlan(user.id, payload);
            }
        });

        if (done) {
            UI.toast("Plan assigned to " + user.fullname, "success");
            await refreshAll();
        }
    }

    async function revertPlan(user) {
        var yes = await UI.confirmDialog({
            title: "Move to the free plan?",
            message: user.fullname + " goes back to the free allowance. " +
                "Nothing is deleted, but they will not be able to upload more " +
                "until they are under it.",
            confirmText: "Revert to free",
            danger: true,
            icon: "arrow-counterclockwise"
        });
        if (!yes) { return; }

        try {
            await API.admin.revokePlan(user.id);
            UI.toast(user.fullname + " is back on the free plan", "success");
            await refreshAll();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function toggleStatus(user) {
        var disabling = user.status === "active";

        if (disabling) {
            var yes = await UI.confirmDialog({
                title: "Disable this account?",
                message: user.fullname + " will be signed out and refused entry until " +
                    "you enable the account again. Their files are kept.",
                confirmText: "Disable account",
                danger: true,
                icon: "pause-circle"
            });
            if (!yes) { return; }
        }

        try {
            await API.admin.updateUser(user.id, { status: disabling ? "disabled" : "active" });
            UI.toast(disabling ? "Account disabled" : "Account enabled", "success");
            await refreshAll();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function toggleRole(user) {
        var promoting = user.role !== "admin";

        var yes = await UI.confirmDialog({
            title: promoting ? "Make administrator?" : "Remove admin access?",
            message: promoting
                ? user.fullname + " will be able to see every account, change plans and " +
                  "delete users."
                : user.fullname + " will lose access to this panel.",
            confirmText: promoting ? "Make administrator" : "Remove access",
            danger: !promoting,
            icon: "shield-lock"
        });
        if (!yes) { return; }

        try {
            await API.admin.updateUser(user.id, { role: promoting ? "admin" : "user" });
            UI.toast(promoting ? "Administrator added" : "Admin access removed", "success");
            await refreshAll();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function deleteUser(user) {
        var typed;

        var done = await formModal({
            title: "Delete " + user.fullname + "?",
            intro: "This removes the account, every file and folder it owns, its shares " +
                "and the bytes on disk. It cannot be undone.",
            confirmText: "Delete permanently",
            danger: true,
            build: function (body) {
                typed = input("deleteConfirm", "text", "", {
                    placeholder: user.username, autocomplete: "off"
                });
                body.appendChild(field(
                    "Type the username to confirm", typed,
                    "Enter “" + user.username + "” exactly."
                ));
            },
            read: function () {
                if (typed.value.trim().toLowerCase() !== user.username.toLowerCase()) {
                    throw new Error("That does not match the username.");
                }
                return {};
            },
            submit: function () {
                return API.admin.deleteUser(user.id);
            }
        });

        if (done) {
            UI.toast("Account deleted", "success");
            await refreshAll();
        }
    }

    async function userDetail(user) {
        var detail;
        try {
            detail = await API.admin.user(user.id);
        } catch (err) {
            UI.reportError(err);
            return;
        }

        var host = el("div", "modal fade");
        host.tabIndex = -1;

        var dialog = el("div", "modal-dialog modal-dialog-centered modal-lg");
        var content = el("div", "modal-content");

        var header = el("div", "modal-header");
        header.appendChild(el("h2", "modal-title", detail.fullname));
        var close = el("button", "btn-close");
        close.type = "button";
        close.setAttribute("data-bs-dismiss", "modal");
        close.setAttribute("aria-label", "Close");
        header.appendChild(close);
        content.appendChild(header);

        var body = el("div", "modal-body");

        var summary = el("div", "admin-detail-grid");
        summary.appendChild(kv("Username", "@" + detail.username));
        summary.appendChild(kv("Email", detail.email));
        summary.appendChild(kv("Role", detail.role === "admin" ? "Administrator" : "User"));
        summary.appendChild(kv("Status", detail.status === "active" ? "Active" : "Disabled"));
        summary.appendChild(kv("Joined", UI.formatDateTime(detail.created_at)));
        summary.appendChild(kv("Last activity",
            detail.last_active ? UI.timeAgo(detail.last_active) : "Never"));
        summary.appendChild(kv("Files", String(detail.file_count)));
        summary.appendChild(kv("Folders", String(detail.folder_count)));
        summary.appendChild(kv("Shares created", String(detail.shared_out)));
        summary.appendChild(kv("In Trash", String(detail.trash_count)));
        body.appendChild(summary);

        var usage = el("div", "admin-usage");
        usage.appendChild(el("div", "field-label", "Storage"));
        usage.appendChild(el("div", "text-meta",
            storageLabel(detail.storage_used) + " of " + storageLabel(detail.storage_limit) +
            " · " + detail.used_percent + "%"));
        usage.appendChild(meter(detail.used_percent));
        body.appendChild(usage);

        body.appendChild(el("div", "field-label", "Plan history"));

        if (!detail.history.length) {
            body.appendChild(el("div", "text-meta", "No plan has ever been assigned."));
        } else {
            var list = el("div", "admin-history");
            detail.history.forEach(function (record) {
                var row = el("div", "admin-history-row");

                var left = el("div");
                left.style.minWidth = "0";
                var title = el("div", "ahr-name", record.plan_name || "Removed plan");
                left.appendChild(title);

                var bits = [];
                bits.push(record.billing_cycle === "free" ? "Free" : record.billing_cycle);
                if (record.price) { bits.push(money(record.price)); }
                bits.push(storageLabel(record.storage_mb));
                bits.push(UI.formatDate(record.starts_at) +
                    (record.ends_at ? " → " + UI.formatDate(record.ends_at) : " → no end date"));
                if (record.assigned_by_name) { bits.push("by " + record.assigned_by_name); }
                left.appendChild(el("div", "text-meta", bits.join(" · ")));

                if (record.note) { left.appendChild(el("div", "text-meta", record.note)); }
                row.appendChild(left);

                var tone = record.status === "active"
                    ? (record.is_expired ? "danger" : "success")
                    : "muted";
                row.appendChild(badge(record.is_expired && record.status === "active"
                    ? "expired" : record.status, tone));

                list.appendChild(row);
            });
            body.appendChild(list);
        }

        content.appendChild(body);

        var footer = el("div", "modal-footer");
        var closeBtn = el("button", "btn-app-ghost", "Close");
        closeBtn.type = "button";
        closeBtn.setAttribute("data-bs-dismiss", "modal");
        footer.appendChild(closeBtn);

        var assign = el("button", "btn-app-primary");
        assign.type = "button";
        assign.appendChild(icon("box-seam"));
        assign.appendChild(el("span", null, "Assign plan"));
        footer.appendChild(assign);
        content.appendChild(footer);

        dialog.appendChild(content);
        host.appendChild(dialog);
        document.body.appendChild(host);

        var modal = new bootstrap.Modal(host);
        host.addEventListener("hidden.bs.modal", function () { host.remove(); });

        assign.addEventListener("click", function () {
            modal.hide();
            assignPlanDialog(detail);
        });

        modal.show();
    }


    /* ---------------------------------------------------------------------
       Plans
       ------------------------------------------------------------------ */

    function renderPlans() {
        var create = el("button", "btn-app-primary");
        create.type = "button";
        create.appendChild(icon("plus-lg"));
        create.appendChild(el("span", null, "New plan"));
        create.addEventListener("click", function () { planDialog(null); });
        nodes.headActions.appendChild(create);

        var host = el("div");
        host.id = "adminPlanHost";
        nodes.body.appendChild(host);

        drawPlans();
    }

    function drawPlans() {
        var host = document.getElementById("adminPlanHost");
        if (!host) { return; }

        UI.clear(host);

        if (!state.plans.length) {
            host.appendChild(UI.emptyState({
                icon: "box-seam",
                title: "No plans yet",
                message: "Create the packages you want to offer, then assign them to users.",
                actionLabel: "New plan",
                actionIcon: "plus-lg",
                onAction: function () { planDialog(null); }
            }));
            return;
        }

        var grid = el("div", "plan-grid");
        state.plans.forEach(function (plan) { grid.appendChild(planCard(plan)); });
        host.appendChild(grid);
    }

    function planCard(plan) {
        var card = el("div", "plan-card" + (plan.is_active ? "" : " is-retired"));

        var head = el("div", "plan-card-head");

        var titles = el("div");
        titles.style.minWidth = "0";
        titles.appendChild(el("h3", "plan-name", plan.name));
        if (plan.description) {
            titles.appendChild(el("p", "plan-desc", plan.description));
        }
        head.appendChild(titles);

        var flags = el("div", "plan-flags");
        if (plan.is_free) { flags.appendChild(badge("Default", "success")); }
        if (!plan.is_active) { flags.appendChild(badge("Retired", "warning")); }
        head.appendChild(flags);

        card.appendChild(head);

        var price = el("div", "plan-price");
        if (plan.is_free || (!plan.price_monthly && !plan.price_yearly)) {
            price.appendChild(el("strong", null, "Free"));
        } else {
            price.appendChild(el("strong", null, money(plan.price_monthly)));
            price.appendChild(el("span", null, "/month"));
            price.appendChild(el("div", "plan-price-alt",
                money(plan.price_yearly) + " billed yearly"));
        }
        card.appendChild(price);

        var storage = el("div", "plan-storage");
        storage.appendChild(icon("hdd"));
        storage.appendChild(el("span", null, storageLabel(plan.storage_mb) + " of storage"));
        card.appendChild(storage);

        if (plan.feature_list.length) {
            var list = el("ul", "plan-features");
            plan.feature_list.forEach(function (feature) {
                var item = document.createElement("li");
                item.appendChild(icon("check2"));
                item.appendChild(el("span", null, feature));
                list.appendChild(item);
            });
            card.appendChild(list);
        }

        var foot = el("div", "plan-card-foot");
        foot.appendChild(el("span", "text-meta",
            plan.subscriber_count + (plan.subscriber_count === 1 ? " subscriber" : " subscribers")));

        var actions = el("div", "plan-actions");

        var edit = el("button", "btn-app-ghost btn-sm-app");
        edit.type = "button";
        edit.appendChild(icon("pencil"));
        edit.appendChild(el("span", null, "Edit"));
        edit.addEventListener("click", function () { planDialog(plan); });
        actions.appendChild(edit);

        var more = Menu.dotTrigger("Actions for " + plan.name, function () {
            return [
                {
                    text: plan.is_active ? "Retire this plan" : "Bring it back",
                    icon: plan.is_active ? "archive" : "arrow-counterclockwise",
                    disabled: plan.is_free,
                    onSelect: function () { togglePlanActive(plan); }
                },
                { divider: true },
                {
                    text: "Delete plan",
                    icon: "trash3",
                    danger: true,
                    disabled: plan.is_free || plan.subscriber_count > 0,
                    onSelect: function () { deletePlan(plan); }
                }
            ];
        });
        more.style.position = "static";
        more.style.opacity = "1";
        actions.appendChild(more);

        foot.appendChild(actions);
        card.appendChild(foot);

        return card;
    }

    async function planDialog(plan) {
        var editing = Boolean(plan);
        var nameInput, descInput, storageInput, unitPicker, monthlyInput, yearlyInput;
        var featuresInput, activeBox, freeBox, orderInput;

        // Storage is stored in MB but nobody thinks in MB at this size, so the
        // form takes a number plus a unit and converts.
        var initialUnit = plan && plan.storage_mb >= 1024 * 1024 ? "TB" : "GB";
        var initialSize = plan
            ? plan.storage_mb / (initialUnit === "TB" ? 1024 * 1024 : 1024)
            : 100;

        var done = await formModal({
            title: editing ? "Edit " + plan.name : "New plan",
            confirmText: editing ? "Save changes" : "Create plan",
            wide: true,
            build: function (body) {
                nameInput = input("planName", "text", plan ? plan.name : "", {
                    placeholder: "Professional", maxlength: "80", required: "required"
                });
                body.appendChild(field("Plan name", nameInput));

                descInput = input("planDesc", "text", plan ? (plan.description || "") : "", {
                    placeholder: "For heavy day-to-day use.", maxlength: "255"
                });
                body.appendChild(field("Short description", descInput));

                var sizeRow = el("div", "admin-row");
                storageInput = input("planStorage", "number", initialSize, {
                    min: "1", step: "any", required: "required"
                });
                unitPicker = select("planUnit", [
                    { value: "GB", label: "GB" },
                    { value: "TB", label: "TB" }
                ], initialUnit);
                sizeRow.appendChild(storageInput);
                sizeRow.appendChild(unitPicker);
                body.appendChild(field("Storage allowance", sizeRow,
                    "Editing this updates every subscriber's limit immediately."));

                var priceRow = el("div", "admin-row");
                monthlyInput = input("planMonthly", "number", plan ? plan.price_monthly : 0, {
                    min: "0", step: "any"
                });
                yearlyInput = input("planYearly", "number", plan ? plan.price_yearly : 0, {
                    min: "0", step: "any"
                });
                priceRow.appendChild(field("Price per month", monthlyInput));
                priceRow.appendChild(field("Price per year", yearlyInput));
                body.appendChild(priceRow);

                featuresInput = document.createElement("textarea");
                featuresInput.id = "planFeatures";
                featuresInput.rows = 5;
                featuresInput.placeholder = "One feature per line";
                featuresInput.value = plan ? (plan.features || "") : "";
                body.appendChild(field("Features", featuresInput, "One per line."));

                orderInput = input("planOrder", "number", plan ? plan.sort_order : 10, {
                    min: "0", max: "999"
                });
                body.appendChild(field("Display order", orderInput, "Lower numbers come first."));

                var activeWrap = el("label", "admin-check");
                activeBox = document.createElement("input");
                activeBox.type = "checkbox";
                activeBox.id = "planActive";
                activeBox.checked = plan ? plan.is_active : true;
                activeWrap.appendChild(activeBox);
                activeWrap.appendChild(el("span", null, "Available to assign"));
                body.appendChild(activeWrap);

                var freeWrap = el("label", "admin-check");
                freeBox = document.createElement("input");
                freeBox.type = "checkbox";
                freeBox.id = "planFree";
                freeBox.checked = plan ? plan.is_free : false;
                freeWrap.appendChild(freeBox);
                freeWrap.appendChild(el("span", null, "This is the free plan new accounts get"));
                body.appendChild(freeWrap);
                body.appendChild(el("div", "hint",
                    "Only one plan can be the default. Choosing this one moves the flag off " +
                    "whichever plan holds it now."));
            },
            read: function () {
                var name = nameInput.value.trim();
                if (name.length < 2) { throw new Error("Give the plan a name."); }

                var size = Number(storageInput.value);
                if (!size || size <= 0) { throw new Error("Storage must be more than zero."); }

                var mb = size * (unitPicker.value === "TB" ? 1024 * GB : GB);

                var monthly = Number(monthlyInput.value) || 0;
                var yearly = Number(yearlyInput.value) || 0;
                if (monthly < 0 || yearly < 0) { throw new Error("Prices cannot be negative."); }

                return {
                    name: name,
                    description: descInput.value.trim() || null,
                    storage_mb: mb,
                    price_monthly: monthly,
                    price_yearly: yearly,
                    features: featuresInput.value.trim() || null,
                    is_active: activeBox.checked,
                    is_free: freeBox.checked,
                    sort_order: Number(orderInput.value) || 0
                };
            },
            submit: function (payload) {
                return editing
                    ? API.admin.updatePlan(plan.id, payload)
                    : API.admin.createPlan(payload);
            }
        });

        if (done) {
            UI.toast(editing ? "Plan updated" : "Plan created", "success");
            await refreshAll();
        }
    }

    async function togglePlanActive(plan) {
        try {
            await API.admin.updatePlan(plan.id, { is_active: !plan.is_active });
            UI.toast(plan.is_active ? "Plan retired" : "Plan is available again", "success");
            await refreshAll();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function deletePlan(plan) {
        var yes = await UI.confirmDialog({
            title: "Delete " + plan.name + "?",
            message: "The plan and its history are removed. Retiring it instead keeps " +
                "the record and just stops it being assignable.",
            confirmText: "Delete plan",
            danger: true,
            icon: "trash3"
        });
        if (!yes) { return; }

        try {
            var result = await API.admin.deletePlan(plan.id);
            UI.toast(result.message, "success");
            await refreshAll();
        } catch (err) {
            UI.reportError(err);
        }
    }


    /* =====================================================================
       Loading
       ================================================================== */

    async function loadPlans() {
        try {
            state.plans = await API.admin.plans();
            nodes.navPlans.textContent = state.plans.length;
        } catch (err) {
            state.plans = [];
            if (err.status === 403) { throw err; }
        }
    }

    /** Re-reads everything, then redraws whichever view is on screen. */
    async function refreshAll() {
        await loadPlans();
        try {
            state.stats = await API.admin.stats();
            state.currency = state.stats.currency_symbol || state.currency;
            nodes.navUsers.textContent = state.stats.total_users;
        } catch (e) { /* the counters are not worth failing a redraw over */ }

        if (state.view === "users") {
            loadUsers();
        } else if (state.view === "plans") {
            drawPlans();
        } else {
            setView("overview");
        }
    }

    async function boot() {
        // Pick up the theme saved on the account, for the same reason: the panel
        // and the app have to agree about which one is in charge.
        try {
            var saved = await API.settings.get();
            if (saved && saved.theme) {
                try { localStorage.setItem(THEME_KEY, saved.theme); } catch (e) { /* ignore */ }
                applyTheme(saved.theme);
            }
        } catch (e) { /* the stored preference still applies */ }

        await loadPlans();
        setView(state.view);
    }


    /* =====================================================================
       Chrome
       ================================================================== */

    function applyTheme(mode) {
        var dark = mode === "dark" ||
            (mode === "system" && window.matchMedia &&
                window.matchMedia("(prefers-color-scheme: dark)").matches);
        document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
        document.documentElement.setAttribute("data-theme-mode", mode);
        UI.fill(nodes.themeToggle, icon(dark ? "sun" : "moon-stars"));
    }

    function storedTheme() {
        try { return localStorage.getItem(THEME_KEY) || "light"; } catch (e) { return "light"; }
    }

    function wireShell() {
        nodes.nav.addEventListener("click", function (e) {
            var button = e.target.closest(".admin-nav-item");
            if (button) { setView(button.dataset.view); }
        });

        nodes.themeToggle.addEventListener("click", function () {
            var next = document.documentElement.getAttribute("data-theme") === "dark"
                ? "light" : "dark";
            try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* private mode */ }
            applyTheme(next);

            // The app applies the theme stored on the account over the top of
            // localStorage, so a panel-only change would be undone the moment
            // the administrator clicked through to their drive.
            API.settings.update({ theme: next }).catch(function () {
                /* the local change still stands */
            });
        });

        nodes.logout.addEventListener("click", async function () {
            var yes = await UI.confirmDialog({
                title: "Sign out of the admin panel?",
                confirmText: "Sign out",
                icon: "box-arrow-right"
            });
            if (!yes) { return; }

            try { await API.auth.logout(); } catch (e) { /* the token goes either way */ }
            API.clearSession();
            state.admin = null;
            nodes.password.value = "";
            showGate();
        });

        applyTheme(storedTheme());
    }


    /* =====================================================================
       Start
       ================================================================== */

    async function start() {
        nodes = {
            gate: document.getElementById("adminGate"),
            shell: document.getElementById("adminShell"),
            form: document.getElementById("adminLoginForm"),
            username: document.getElementById("adminUsername"),
            password: document.getElementById("adminPassword"),
            pwToggle: document.getElementById("adminPwToggle"),
            loginError: document.getElementById("adminLoginError"),
            loginSubmit: document.getElementById("adminLoginSubmit"),
            nav: document.getElementById("adminNav"),
            navUsers: document.getElementById("navUserCount"),
            navPlans: document.getElementById("navPlanCount"),
            title: document.getElementById("adminViewTitle"),
            sub: document.getElementById("adminViewSub"),
            headActions: document.getElementById("adminHeadActions"),
            body: document.getElementById("adminBody"),
            whoName: document.getElementById("adminWhoName"),
            whoUser: document.getElementById("adminWhoUser"),
            themeToggle: document.getElementById("adminThemeToggle"),
            logout: document.getElementById("adminLogout")
        };

        wireGate();
        wireShell();

        // An existing session gets straight in, but only if it is an admin one.
        if (API.getToken()) {
            try {
                var me = await API.auth.me();
                if (me.role === "admin") {
                    state.admin = me;
                    showPanel();
                    await boot();
                    return;
                }
            } catch (e) { /* fall through to the sign-in gate */ }
        }

        showGate();
    }

    start();
}());
