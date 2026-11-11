/* =========================================================================
   STORAGE
   The headline figures come from GET /api/storage. The breakdown by type and
   the largest-files list are computed in the browser from the real file
   listing, because the API exposes per-file sizes but no aggregate endpoint.
   ========================================================================= */

(function () {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var CATEGORY = [
        { key: "image", label: "Images", color: "#7c3aed" },
        { key: "video", label: "Videos", color: "#db2777" },
        { key: "audio", label: "Audio", color: "#0891b2" },
        { key: "pdf", label: "PDFs", color: "#dc2626" },
        { key: "word", label: "Documents", color: "#2563eb" },
        { key: "excel", label: "Spreadsheets", color: "#16a34a" },
        { key: "ppt", label: "Presentations", color: "#ea580c" },
        { key: "zip", label: "Archives", color: "#d97706" },
        { key: "code", label: "Code", color: "#475569" },
        { key: "text", label: "Text", color: "#64748b" },
        { key: "generic", label: "Other", color: "#94a3b8" }
    ];


    /* ---------------------------------------------------------------------
       Hero ring
       ------------------------------------------------------------------ */

    function renderHero(storage) {
        var host = document.getElementById("storageHero");
        UI.clear(host);

        var percent = Math.min(storage.used_percent || 0, 100);
        var tone = percent >= 90 ? "is-danger" : (percent >= 75 ? "is-warning" : "");

        // Ring
        var ring = el("div", "storage-ring");

        var radius = 62;
        var circumference = 2 * Math.PI * radius;

        var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 148 148");
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", percent.toFixed(0) + "% of your storage is used");

        function circle(className, offset) {
            var node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            node.setAttribute("class", className);
            node.setAttribute("cx", "74");
            node.setAttribute("cy", "74");
            node.setAttribute("r", String(radius));
            node.setAttribute("fill", "none");
            node.setAttribute("stroke-width", "12");
            node.setAttribute("stroke-dasharray", String(circumference));
            node.setAttribute("stroke-dashoffset", String(offset));
            return node;
        }

        svg.appendChild(circle("ring-track", 0));
        svg.appendChild(circle(
            "ring-value " + tone,
            circumference - (circumference * percent) / 100
        ));
        ring.appendChild(svg);

        var center = el("div", "ring-center");
        center.appendChild(el("div", "ring-pct", Math.round(percent) + "%"));
        center.appendChild(el("div", "ring-sub", "used"));
        ring.appendChild(center);

        host.appendChild(ring);

        // Figures
        var facts = el("div");
        facts.style.flex = "1";
        facts.style.minWidth = "220px";

        var headline = el("div");
        headline.style.fontSize = "22px";
        headline.style.fontWeight = "600";
        headline.style.letterSpacing = "-.02em";
        headline.textContent = UI.formatMB(storage.used_storage) + " used of " +
            UI.formatMB(storage.total_storage);
        facts.appendChild(headline);

        var sub = el("p", "text-dim", UI.formatMB(storage.available_storage) + " still available.");
        sub.style.marginTop = "4px";
        facts.appendChild(sub);

        if (percent >= 75) {
            var warn = el("div", "badge-soft " + (percent >= 90 ? "is-danger" : "is-warning"));
            warn.appendChild(icon("exclamation-triangle-fill"));
            warn.appendChild(el("span", null,
                percent >= 90 ? "Almost out of space" : "Storage is filling up"));
            warn.style.marginTop = "12px";
            facts.appendChild(warn);
        }

        var actions = el("div");
        actions.style.display = "flex";
        actions.style.gap = "8px";
        actions.style.marginTop = "16px";
        actions.style.flexWrap = "wrap";

        var trashLink = el("a", "btn-app-ghost", "Review Trash");
        trashLink.href = "trash.html";
        actions.appendChild(trashLink);

        var filesLink = el("a", "btn-app-ghost", "Browse files");
        filesLink.href = "files.html";
        actions.appendChild(filesLink);

        facts.appendChild(actions);
        host.appendChild(facts);
    }


    /* ---------------------------------------------------------------------
       Breakdown + largest files
       ------------------------------------------------------------------ */

    function renderBreakdown(files) {
        var host = document.getElementById("breakdownHost");
        UI.clear(host);

        if (!files.length) {
            host.appendChild(UI.emptyState({
                icon: "pie-chart",
                title: "Nothing stored yet",
                message: "Upload a file and the breakdown will appear here."
            }));
            return;
        }

        var totals = {};
        var grandTotal = 0;

        files.forEach(function (file) {
            var kind = UI.fileKind(file.original_name, file.file_type);
            totals[kind] = (totals[kind] || 0) + file.file_size;
            grandTotal += file.file_size;
        });

        var rows = CATEGORY
            .filter(function (spec) { return totals[spec.key]; })
            .map(function (spec) {
                return {
                    label: spec.label,
                    color: spec.color,
                    bytes: totals[spec.key],
                    share: grandTotal ? (totals[spec.key] / grandTotal) * 100 : 0
                };
            })
            .sort(function (a, b) { return b.bytes - a.bytes; });

        // Stacked bar
        var bar = el("div", "breakdown-bar");
        bar.setAttribute("role", "img");
        bar.setAttribute("aria-label", "Storage split by file type");

        rows.forEach(function (row) {
            var segment = el("span");
            segment.style.width = row.share + "%";
            segment.style.background = row.color;
            segment.title = row.label + " · " + UI.formatSize(row.bytes);
            bar.appendChild(segment);
        });
        host.appendChild(bar);

        rows.forEach(function (row) {
            var node = el("div", "breakdown-row");

            var dot = el("span", "bd-dot");
            dot.style.background = row.color;
            node.appendChild(dot);

            node.appendChild(el("span", "bd-name", row.label));
            node.appendChild(el("span", "bd-size",
                UI.formatSize(row.bytes) + "  ·  " + row.share.toFixed(0) + "%"));

            host.appendChild(node);
        });
    }

    function renderLargest(files) {
        var host = document.getElementById("largestHost");
        UI.clear(host);

        if (!files.length) {
            host.appendChild(UI.emptyState({
                icon: "file-earmark",
                title: "No files yet",
                message: "Your biggest files will be listed here."
            }));
            return;
        }

        var largest = files.slice()
            .sort(function (a, b) { return b.file_size - a.file_size; })
            .slice(0, 8);

        var table = Files.fileTable([
            { label: "Name" },
            { label: "Size" },
            { label: "", className: "cell-actions" }
        ]);

        largest.forEach(function (file) {
            table.tbody.appendChild(Files.fileRow(file, ["size"]));
        });

        table.wrap.style.border = "0";
        table.wrap.style.borderRadius = "0";
        host.appendChild(table.wrap);
    }


    /* ---------------------------------------------------------------------
       Load
       ------------------------------------------------------------------ */

    function showSkeletons() {
        var hero = document.getElementById("storageHero");
        UI.clear(hero);

        var ring = el("div", "skeleton");
        ring.style.width = "148px";
        ring.style.height = "148px";
        ring.style.borderRadius = "50%";
        hero.appendChild(ring);

        var stack = el("div");
        stack.style.flex = "1";
        var l1 = el("div", "skeleton sk-line");
        l1.style.width = "50%";
        l1.style.height = "20px";
        var l2 = el("div", "skeleton sk-line");
        l2.style.width = "34%";
        stack.appendChild(l1);
        stack.appendChild(l2);
        hero.appendChild(stack);

        UI.skeletonRows(4, document.getElementById("breakdownHost"));
        UI.skeletonRows(4, document.getElementById("largestHost"));
    }

    /* ---------------------------------------------------------------------
       Plan

       Users cannot change their own plan - an administrator assigns it - so
       this is a statement of what they have, not a checkout.
       ------------------------------------------------------------------ */

    function money(symbol, value) {
        var amount = Number(value) || 0;
        var text = amount % 1 === 0 ? String(amount) : amount.toFixed(2);
        return symbol + text.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    function renderMyPlan(data) {
        var host = document.getElementById("myPlanHost");
        if (!host) { return; }

        UI.clear(host);

        if (!data.plan) {
            host.appendChild(UI.emptyState({
                icon: "box-seam",
                title: "No plan assigned",
                message: "Ask your administrator to put this account on a plan."
            }));
            return;
        }

        var plan = data.plan;
        var sub = data.subscription || {};
        var wrap = el("div", "my-plan");

        var badge = el("div", "my-plan-badge");
        badge.appendChild(icon(plan.is_free ? "gift" : "gem"));
        wrap.appendChild(badge);

        var body = el("div", "my-plan-body");

        var name = el("div", "my-plan-name");
        name.appendChild(document.createTextNode(plan.name));

        if (sub.is_expired) {
            name.appendChild(el("span", "badge-soft is-danger", "Expired"));
        } else if (sub.billing_cycle && sub.billing_cycle !== "free") {
            name.appendChild(el("span", "badge-soft is-success", sub.billing_cycle));
        }
        body.appendChild(name);

        var bits = [UI.formatMB(plan.storage_mb) + " of storage"];

        if (sub.billing_cycle === "free") {
            bits.push("Free forever");
        } else if (sub.price) {
            bits.push(money(data.currency_symbol, sub.price) +
                " per " + (sub.billing_cycle === "yearly" ? "year" : "month"));
        }

        if (sub.ends_at) {
            bits.push((sub.is_expired ? "Expired " : "Renews ") + UI.formatDate(sub.ends_at));
        } else if (sub.billing_cycle !== "free") {
            bits.push("No end date");
        }

        body.appendChild(el("div", "my-plan-meta", bits.join(" · ")));

        if (sub.days_remaining !== null && sub.days_remaining !== undefined &&
            !sub.is_expired && sub.days_remaining <= 14) {
            var warn = el("span", "badge-soft is-warning",
                sub.days_remaining + " day" + (sub.days_remaining === 1 ? "" : "s") + " left");
            warn.style.marginTop = "6px";
            body.appendChild(warn);
        }

        wrap.appendChild(body);

        var usage = el("div", "my-plan-usage");
        usage.appendChild(el("div", "text-meta",
            UI.formatMB(data.storage_used) + " of " + UI.formatMB(data.storage_limit) +
            " used · " + data.used_percent + "%"));

        var bar = el("div", "meter");
        var fill = el("div", "meter-fill");
        fill.style.width = Math.min(100, data.used_percent) + "%";
        if (data.used_percent >= 90) { fill.style.background = "var(--danger)"; }
        else if (data.used_percent >= 75) { fill.style.background = "var(--warning)"; }
        bar.appendChild(fill);
        usage.appendChild(bar);

        wrap.appendChild(usage);
        host.appendChild(wrap);
    }

    function renderCatalogue(plans, current, symbol) {
        var section = document.getElementById("catalogueSection");
        var host = document.getElementById("catalogueHost");
        if (!host) { return; }

        UI.clear(host);

        if (!plans.length) {
            if (section) { section.classList.add("is-hidden"); }
            return;
        }
        if (section) { section.classList.remove("is-hidden"); }

        var grid = el("div", "plan-grid");

        plans.forEach(function (plan) {
            var mine = current && plan.id === current.id;
            var card = el("div", "plan-card" + (mine ? " is-current" : ""));

            var head = el("div", "plan-card-head");
            var titles = el("div");
            titles.style.minWidth = "0";
            titles.appendChild(el("h3", "plan-name", plan.name));
            if (plan.description) {
                titles.appendChild(el("p", "plan-desc", plan.description));
            }
            head.appendChild(titles);

            if (mine) {
                var flags = el("div", "plan-flags");
                flags.appendChild(el("span", "badge-soft is-success", "Current"));
                head.appendChild(flags);
            }
            card.appendChild(head);

            var price = el("div", "plan-price");
            if (plan.is_free || (!plan.price_monthly && !plan.price_yearly)) {
                price.appendChild(el("strong", null, "Free"));
            } else {
                price.appendChild(el("strong", null, money(symbol, plan.price_monthly)));
                price.appendChild(el("span", null, "/month"));
                price.appendChild(el("div", "plan-price-alt",
                    money(symbol, plan.price_yearly) + " billed yearly"));
            }
            card.appendChild(price);

            var storage = el("div", "plan-storage");
            storage.appendChild(icon("hdd"));
            storage.appendChild(el("span", null, UI.formatMB(plan.storage_mb) + " of storage"));
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

            grid.appendChild(card);
        });

        host.appendChild(grid);
    }

    async function loadPlan() {
        var host = document.getElementById("myPlanHost");
        if (host) { UI.skeletonRows(1, host); }

        try {
            var mine = await API.plans.mine();
            renderMyPlan(mine);

            var catalogue = await API.plans.list();
            renderCatalogue(catalogue, mine.plan, mine.currency_symbol);
        } catch (err) {
            if (host) {
                UI.fill(host, el("div", "text-meta", "Could not load your plan: " + err.message));
            }
        }
    }


    async function load() {
        showSkeletons();
        loadPlan();

        try {
            var storage = await API.storage.get();
            renderHero(storage);

            // root_only=false returns every live file the user owns.
            var files = await API.files.list({ root_only: false, limit: 500 });
            renderBreakdown(files);
            renderLargest(files);
        } catch (err) {
            UI.reportError(err);
            UI.fill(document.getElementById("storageHero"), UI.emptyState({
                icon: "wifi-off",
                title: "Could not load storage",
                message: err.message
            }));
        }
    }

    async function boot() {
        var user = await Shell.mount({ active: "storage" });
        if (!user) { return; }

        document.addEventListener("Cloud:refresh", load);
        load();
    }

    boot();
}());
