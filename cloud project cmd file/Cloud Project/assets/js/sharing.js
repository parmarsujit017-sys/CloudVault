/* =========================================================================
   SHARING
   One modal covering both ways the API can share something: directly with a
   registered user, or through an unguessable public link with an optional
   password and expiry date.

   Files and folders share this modal because they share the mechanics - the
   only differences are which endpoint is called and the wording. Sharing a
   folder shares everything under it, evaluated live, so files added to it
   later are covered without re-sharing.
   ========================================================================= */

(function (global) {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var modal = null;
    var host = null;

    /** { kind: "file"|"folder", id, name } - whatever the modal is open on. */
    var current = null;

    function isFolder() { return current && current.kind === "folder"; }


    function build() {
        if (host) { return; }

        host = el("div", "modal fade");
        host.id = "shareModal";
        host.tabIndex = -1;
        host.setAttribute("aria-labelledby", "shareModalTitle");

        var dialog = el("div", "modal-dialog modal-dialog-centered");
        var content = el("div", "modal-content");

        // Header
        var header = el("div", "modal-header");
        var title = el("h2", "modal-title", "Share");
        title.id = "shareModalTitle";
        header.appendChild(title);

        var close = el("button", "btn-close");
        close.type = "button";
        close.setAttribute("data-bs-dismiss", "modal");
        close.setAttribute("aria-label", "Close");
        header.appendChild(close);
        content.appendChild(header);

        var body = el("div", "modal-body");

        // ---- People with access -------------------------------------
        body.appendChild(sectionLabel("People with access"));

        var peopleList = el("div", "stack-2");
        peopleList.id = "sharePeople";
        body.appendChild(peopleList);

        // ---- Add a person -------------------------------------------
        var addForm = document.createElement("form");
        addForm.id = "shareAddForm";
        addForm.noValidate = true;
        addForm.style.marginTop = "16px";

        var field = el("div", "field");
        field.style.overflow = "visible";
        var label = el("label", null, "Add a person");
        label.htmlFor = "shareRecipient";

        // Username input
        var input = document.createElement("input");
        input.type = "text";
        input.id = "shareRecipient";
        input.placeholder = "Username or email";
        input.autocomplete = "off";
        input.setAttribute("list", "shareUserOptions");
        input.style.width = "100%";
        input.style.marginBottom = "8px";

        var datalist = document.createElement("datalist");
        datalist.id = "shareUserOptions";

        // Permission and button row
        var permRow = el("div");
        permRow.style.display = "flex";
        permRow.style.gap = "8px";
        permRow.style.overflow = "visible";
        permRow.style.position = "relative";
        permRow.style.alignItems = "center";

        var permLabel = el("label", null, "Permission:");
        permLabel.style.fontSize = "12px";
        permLabel.style.fontWeight = "500";
        permLabel.style.color = "#64748b";
        permLabel.style.marginRight = "4px";
        permLabel.style.whiteSpace = "nowrap";

        var permSelect = document.createElement("select");
        permSelect.id = "sharePermission";
        permSelect.style.minWidth = "100px";
        permSelect.style.height = "36px";
        permSelect.style.padding = "6px 10px";
        permSelect.style.border = "1px solid #e6e9ef";
        permSelect.style.borderRadius = "4px";
        permSelect.style.backgroundColor = "#ffffff";
        permSelect.style.color = "#0f172a";
        permSelect.style.fontFamily = "inherit";
        permSelect.style.fontSize = "13px";
        permSelect.style.cursor = "pointer";
        
        var viewerOpt = document.createElement("option");
        viewerOpt.value = "viewer";
        viewerOpt.text = "Viewer (read-only)";
        var editorOpt = document.createElement("option");
        editorOpt.value = "editor";
        editorOpt.text = "Editor (can edit)";
        permSelect.appendChild(viewerOpt);
        permSelect.appendChild(editorOpt);

        var addBtn = el("button", "btn-app-primary", "Share");
        addBtn.type = "submit";
        addBtn.style.marginLeft = "auto";

        permRow.appendChild(permLabel);
        permRow.appendChild(permSelect);
        permRow.appendChild(addBtn);

        field.appendChild(label);
        field.appendChild(input);
        field.appendChild(datalist);
        field.appendChild(permRow);

        var note = el("div", "hint", "");
        note.id = "shareAccessHint";
        field.appendChild(note);

        addForm.appendChild(field);
        body.appendChild(addForm);

        body.appendChild(el("hr"));

        // ---- General access -----------------------------------------
        body.appendChild(sectionLabel("General access"));

        var linkArea = el("div");
        linkArea.id = "shareLinkArea";
        body.appendChild(linkArea);

        var linkForm = document.createElement("form");
        linkForm.id = "shareLinkForm";
        linkForm.noValidate = true;

        var pwField = el("div", "field");
        var pwLabel = el("label", null, "Password (optional)");
        pwLabel.htmlFor = "sharePassword";
        var pwInput = document.createElement("input");
        pwInput.type = "password";
        pwInput.id = "sharePassword";
        pwInput.placeholder = "Leave empty for no password";
        pwInput.autocomplete = "new-password";
        pwInput.minLength = 4;
        pwField.appendChild(pwLabel);
        pwField.appendChild(pwInput);
        linkForm.appendChild(pwField);

        var expField = el("div", "field");
        var expLabel = el("label", null, "Expires on (optional)");
        expLabel.htmlFor = "shareExpiry";
        var expInput = document.createElement("input");
        expInput.type = "datetime-local";
        expInput.id = "shareExpiry";
        expField.appendChild(expLabel);
        expField.appendChild(expInput);
        linkForm.appendChild(expField);

        var createBtn = el("button", "btn-app-ghost btn-block");
        createBtn.type = "submit";
        createBtn.appendChild(icon("link-45deg"));
        createBtn.appendChild(el("span", null, "Create link"));
        linkForm.appendChild(createBtn);

        body.appendChild(linkForm);
        content.appendChild(body);

        dialog.appendChild(content);
        host.appendChild(dialog);
        document.body.appendChild(host);

        modal = new bootstrap.Modal(host);

        // ---- Behaviour ----------------------------------------------

        addForm.addEventListener("submit", async function (e) {
            e.preventDefault();

            var value = input.value.trim();
            if (!value) {
                input.focus();
                return;
            }

            addBtn.disabled = true;
            try {
                var permission = permSelect.value || "viewer";
                if (isFolder()) {
                    await API.shares.createFolder({
                        folder_id: current.id,
                        shared_to_username: value,
                        permission: permission
                    });
                } else {
                    await API.shares.create({
                        file_id: current.id,
                        shared_to_username: value,
                        permission: permission
                    });
                }
                UI.toast("Shared with " + value + " (" + (permission === "editor" ? "can edit" : "can view") + ")", "success");
                input.value = "";
                await loadShares();
            } catch (err) {
                UI.reportError(err);
            } finally {
                addBtn.disabled = false;
            }
        });

        // Suggest real accounts as the user types.
        input.addEventListener("input", UI.debounce(async function () {
            var term = input.value.trim();
            if (term.length < 2) { return; }

            try {
                var people = await API.users.search(term);
                UI.clear(datalist);
                people.forEach(function (person) {
                    var option = document.createElement("option");
                    option.value = person.username;
                    option.label = person.fullname;
                    datalist.appendChild(option);
                });
            } catch (e) { /* suggestions are optional */ }
        }, 250));

        linkForm.addEventListener("submit", async function (e) {
            e.preventDefault();

            var payload = isFolder()
                ? { folder_id: current.id }
                : { file_id: current.id };

            if (pwInput.value) {
                if (pwInput.value.length < 4) {
                    UI.toast("Link password must be at least 4 characters", "error");
                    return;
                }
                payload.password = pwInput.value;
            }

            if (expInput.value) {
                var when = new Date(expInput.value);
                if (when.getTime() <= Date.now()) {
                    UI.toast("The expiry date must be in the future", "error");
                    return;
                }
                payload.expiry_date = when.toISOString();
            }

            createBtn.disabled = true;
            try {
                if (isFolder()) {
                    await API.shares.createFolder(payload);
                } else {
                    await API.shares.create(payload);
                }
                UI.toast("Public link created", "success");
                pwInput.value = "";
                expInput.value = "";
                await loadShares();
            } catch (err) {
                UI.reportError(err);
            } finally {
                createBtn.disabled = false;
            }
        });
    }

    function sectionLabel(text) {
        var node = el("div", "field-label", text);
        node.style.marginBottom = "10px";
        return node;
    }


    /* ---------------------------------------------------------------------
       Rendering existing shares
       ------------------------------------------------------------------ */

    function personRow(share) {
        var row = el("div");
        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.gap = "12px";

        var badge = el("span", "ftype ftype-sm");
        badge.appendChild(icon("person-fill"));
        row.appendChild(badge);

        var body = el("div");
        body.style.flex = "1";
        body.style.minWidth = "0";

        var name = el("div", "truncate", share.shared_to_name || "Unknown user");
        name.style.fontSize = "13.5px";
        name.style.fontWeight = "500";
        body.appendChild(name);
        var permText = "Can view";
        if (share.permission === "editor") {
            permText = "Can edit";
        }
        body.appendChild(el("div", "text-meta", permText + " · shared " + UI.timeAgo(share.created_at)));
        row.appendChild(body);

        row.appendChild(revokeButton(share, "Remove access"));
        return row;
    }

    function linkRow(share) {
        var row = el("div", "panel");
        row.style.padding = "12px";

        var top = el("div");
        top.style.display = "flex";
        top.style.alignItems = "center";
        top.style.gap = "12px";

        var badge = el("span", "ftype ftype-sm");
        badge.dataset.type = "folder";
        badge.appendChild(icon(share.has_password ? "shield-lock-fill" : "link-45deg"));
        top.appendChild(badge);

        var body = el("div");
        body.style.flex = "1";
        body.style.minWidth = "0";

        var title = el("div", null, "Anyone with the link");
        title.style.fontSize = "13.5px";
        title.style.fontWeight = "500";
        body.appendChild(title);

        var bits = [];
        bits.push(share.kind === "folder" ? "Can browse and download" : "Can view and download");
        bits.push(share.has_password ? "Password protected" : "No password");
        if (share.expiry_date) {
            bits.push(share.is_expired
                ? "Expired"
                : "Expires " + UI.formatDate(share.expiry_date));
        }
        body.appendChild(el("div", "text-meta", bits.join(" · ")));
        top.appendChild(body);

        top.appendChild(revokeButton(share, "Delete link"));
        row.appendChild(top);

        var url = share.share_url || (location.origin + "/share.html?token=" + share.share_link);

        var copyRow = el("div");
        copyRow.style.display = "flex";
        copyRow.style.gap = "8px";
        copyRow.style.marginTop = "10px";

        var field = document.createElement("input");
        field.type = "text";
        field.className = "input";
        field.readOnly = true;
        field.value = url;
        field.style.fontSize = "12px";
        field.setAttribute("aria-label", "Public share link");

        var copy = el("button", "btn-app-ghost");
        copy.type = "button";
        copy.appendChild(icon("clipboard"));
        copy.appendChild(el("span", null, "Copy"));
        copy.addEventListener("click", function () {
            field.select();
            UI.copyText(url).then(
                function () { UI.toast("Link copied", "success"); },
                function () { UI.toast("Could not copy the link", "error"); }
            );
        });

        copyRow.appendChild(field);
        copyRow.appendChild(copy);
        row.appendChild(copyRow);

        if (share.is_expired) {
            var warn = el("div", "badge-soft is-warning", "This link has expired");
            warn.style.marginTop = "8px";
            row.appendChild(warn);
        }

        return row;
    }

    function revokeButton(share, label) {
        var button = el("button", "icon-btn");
        button.type = "button";
        button.setAttribute("aria-label", label);
        button.title = label;
        button.appendChild(icon("x-lg"));

        button.addEventListener("click", async function () {
            var noun = share.kind === "folder" ? "folder" : "file";

            var yes = await UI.confirmDialog({
                title: label + "?",
                message: share.shared_to
                    ? (share.shared_to_name || "This person") + " will lose access to the " + noun +
                        (share.kind === "folder" ? " and everything inside it." : ".")
                    : "Anyone holding this link will no longer be able to open the " + noun + ".",
                confirmText: label,
                danger: true,
                icon: "x-octagon-fill"
            });
            if (!yes) { return; }

            try {
                if (share.kind === "folder") {
                    await API.shares.revokeFolder(share.id);
                } else {
                    await API.shares.revoke(share.id);
                }
                UI.toast("Access revoked", "success");
                await loadShares();
            } catch (err) {
                UI.reportError(err);
            }
        });

        return button;
    }

    async function loadShares() {
        var people = document.getElementById("sharePeople");
        var links = document.getElementById("shareLinkArea");

        UI.skeletonRows(1, people);
        UI.clear(links);

        var all;
        try {
            all = await API.shares.sent();
        } catch (err) {
            UI.fill(people, el("div", "text-meta", err.message));
            return;
        }

        var mine = all.filter(function (share) {
            return share.kind === current.kind &&
                (current.kind === "folder" ? share.folder_id : share.file_id) === current.id;
        });
        var direct = mine.filter(function (share) { return share.shared_to; });
        var publics = mine.filter(function (share) { return !share.shared_to; });

        UI.clear(people);
        if (!direct.length) {
            var owner = el("div", "text-meta", "Only you have access right now.");
            people.appendChild(owner);
        } else {
            direct.forEach(function (share) { people.appendChild(personRow(share)); });
        }

        UI.clear(links);
        if (publics.length) {
            publics.forEach(function (share) { links.appendChild(linkRow(share)); });
            links.style.marginBottom = "16px";
        } else {
            var none = el("div", "text-meta", "No public link yet. Create one below.");
            none.style.marginBottom = "16px";
            links.appendChild(none);
        }
    }


    /* ---------------------------------------------------------------------
       Public
       ------------------------------------------------------------------ */

    function show(descriptor, hint) {
        build();
        current = descriptor;

        document.getElementById("shareModalTitle").textContent = "Share “" + descriptor.name + "”";
        document.getElementById("shareAccessHint").textContent = hint;
        document.getElementById("shareRecipient").value = "";
        document.getElementById("sharePassword").value = "";
        document.getElementById("shareExpiry").value = "";

        modal.show();
        loadShares();
    }

    function open(file) {
        show(
            { kind: "file", id: file.id, name: file.original_name },
            "Recipients get read-only access: they can view and download this file."
        );
    }

    function openFolder(folder) {
        show(
            { kind: "folder", id: folder.id, name: folder.folder_name },
            "Recipients can browse this folder and download anything inside it, " +
                "including files you add later."
        );
    }

    global.Sharing = {
        open: open,
        openFolder: openFolder
    };
}(window));
