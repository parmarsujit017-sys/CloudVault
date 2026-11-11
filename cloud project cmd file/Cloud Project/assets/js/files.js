/* =========================================================================
   FILE + FOLDER COMPONENTS
   The single source of truth for how a file or folder looks and what you can
   do with it, reused by My Files, Recent, Starred, Dashboard, Trash and the
   search panel so every screen behaves identically.
   ========================================================================= */

(function (global) {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var detailsOffcanvas = null;


    /* ---------------------------------------------------------------------
       Actions - every one of these hits the real API
       ------------------------------------------------------------------ */

    function refreshPage() {
        document.dispatchEvent(new CustomEvent("Cloud:refresh"));
    }

    async function openFile(file) {
        try {
            var kind = (file && (file.kind || file.type || "")) || "";
            var name = (file && (file.original_name || "")) || "";
            if (kind === "word" || /\.docx$/i.test(name)) {
                location.href = "editor.html?id=" + file.id + "&type=word";
                return;
            }
            if (kind === "excel" || /\.xlsx$/i.test(name)) {
                location.href = "editor.html?id=" + file.id + "&type=excel";
                return;
            }
            // Unsupported file type
            UI.toast("This file type is not supported for opening in the editor", "warning");
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function downloadFile(file) {
        try {
            await API.files.save(file.id, file.original_name);
            UI.toast("Downloading " + file.original_name, "success");
        } catch (err) {
            UI.reportError(err);
        }
    }

    /** Folders come down as a .zip the server builds from the live tree. */
    async function downloadFolder(folder) {
        UI.toast("Preparing “" + folder.folder_name + "”…", "success");
        try {
            await API.folders.download(folder.id, folder.folder_name);
            UI.toast("Downloading " + folder.folder_name + ".zip", "success");
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function duplicateFile(file) {
        try {
            var copy = await API.files.copy(file.id, file.folder_id);
            UI.toast('Copied as "' + copy.original_name + '"', "success");
            refreshPage();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function duplicateFolder(folder) {
        UI.toast("Copying “" + folder.folder_name + "”…", "success");
        try {
            var copy = await API.folders.copy(folder.id, folder.parent_folder);
            UI.toast('Copied as "' + copy.folder_name + '"', "success");
            refreshPage();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function renameFile(file) {
        var name = await UI.promptDialog({
            title: "Rename file",
            label: "File name",
            value: file.original_name,
            confirmText: "Rename"
        });
        if (!name || name === file.original_name) { return; }

        try {
            await API.files.rename(file.id, name);
            UI.toast("File renamed", "success");
            refreshPage();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function renameFolder(folder) {
        var name = await UI.promptDialog({
            title: "Rename folder",
            label: "Folder name",
            value: folder.folder_name,
            confirmText: "Rename"
        });
        if (!name || name === folder.folder_name) { return; }

        try {
            await API.folders.update(folder.id, { folder_name: name });
            UI.toast("Folder renamed", "success");
            refreshPage();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function toggleStar(file) {
        try {
            await API.files.star(file.id, !file.is_starred);
            UI.toast(file.is_starred ? "Removed from Starred" : "Added to Starred", "success");
            refreshPage();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function trashFile(file) {
        var yes = await UI.confirmDialog({
            title: "Move to Trash?",
            message: '"' + file.original_name + '" will be moved to Trash. You can restore it later.',
            confirmText: "Move to Trash",
            danger: true,
            icon: "trash3"
        });
        if (!yes) { return; }

        try {
            await API.files.remove(file.id);
            UI.toast("Moved to Trash", "success");
            refreshPage();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function deleteFolder(folder) {
        var yes = await UI.confirmDialog({
            title: "Delete folder?",
            message: 'Deleting "' + folder.folder_name +
                '" also moves every file inside it to Trash.',
            confirmText: "Delete folder",
            danger: true,
            icon: "trash3"
        });
        if (!yes) { return; }

        try {
            var result = await API.folders.remove(folder.id);
            UI.toast(result.message, "success");
            refreshPage();
            Shell.refreshStats();
        } catch (err) {
            UI.reportError(err);
        }
    }

    /** Move dialog: a real folder picker built from the user's own tree. */
    async function moveDialog(options) {
        var folders;
        try {
            folders = await API.folders.listAll();
        } catch (err) {
            UI.reportError(err);
            return;
        }

        var excluded = options.excludeFolderId || null;
        var choices = [{ id: null, label: "My Files (root)" }].concat(
            folders
                .filter(function (folder) { return folder.id !== excluded; })
                .map(function (folder) { return { id: folder.id, label: folder.folder_name }; })
        );

        return new Promise(function (resolve) {
            var host = el("div", "modal fade");
            host.tabIndex = -1;

            var dialog = el("div", "modal-dialog modal-dialog-centered");
            var content = el("div", "modal-content");
            var form = document.createElement("form");

            var header = el("div", "modal-header");
            header.appendChild(el("h2", "modal-title", "Move " + options.name));
            var close = el("button", "btn-close");
            close.type = "button";
            close.setAttribute("data-bs-dismiss", "modal");
            close.setAttribute("aria-label", "Close");
            header.appendChild(close);

            var body = el("div", "modal-body");
            var field = el("div", "field");
            var label = el("label", null, "Destination folder");
            label.htmlFor = "moveTarget";

            var select = document.createElement("select");
            select.id = "moveTarget";
            choices.forEach(function (choice) {
                var option = document.createElement("option");
                option.value = choice.id === null ? "" : String(choice.id);
                option.textContent = choice.label;
                if (choice.id === options.currentFolderId) { option.selected = true; }
                select.appendChild(option);
            });

            field.appendChild(label);
            field.appendChild(select);
            body.appendChild(field);

            var footer = el("div", "modal-footer");
            var cancel = el("button", "btn-app-ghost", "Cancel");
            cancel.type = "button";
            cancel.setAttribute("data-bs-dismiss", "modal");
            var save = el("button", "btn-app-primary", "Move");
            save.type = "submit";
            footer.appendChild(cancel);
            footer.appendChild(save);

            form.appendChild(header);
            form.appendChild(body);
            form.appendChild(footer);
            content.appendChild(form);
            dialog.appendChild(content);
            host.appendChild(dialog);
            document.body.appendChild(host);

            var modal = new bootstrap.Modal(host);
            var picked;

            form.addEventListener("submit", function (e) {
                e.preventDefault();
                picked = select.value === "" ? null : Number(select.value);
                modal.hide();
            });

            host.addEventListener("hidden.bs.modal", function () {
                host.remove();
                resolve(picked === undefined ? undefined : picked);
            });

            modal.show();
        });
    }

    async function moveFile(file) {
        var target = await moveDialog({
            name: '"' + file.original_name + '"',
            currentFolderId: file.folder_id
        });
        if (target === undefined) { return; }

        try {
            await API.files.move(file.id, target);
            UI.toast("File moved", "success");
            refreshPage();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function moveFolder(folder) {
        var target = await moveDialog({
            name: '"' + folder.folder_name + '"',
            currentFolderId: folder.parent_folder,
            excludeFolderId: folder.id
        });
        if (target === undefined) { return; }

        try {
            await API.folders.update(folder.id, { parent_folder: target });
            UI.toast("Folder moved", "success");
            refreshPage();
        } catch (err) {
            UI.reportError(err);
        }
    }


    /* ---------------------------------------------------------------------
       Details drawer
       ------------------------------------------------------------------ */

    function ensureDetails() {
        if (detailsOffcanvas) { return detailsOffcanvas; }

        var host = el("div", "offcanvas offcanvas-end details-drawer");
        host.id = "detailsDrawer";
        host.tabIndex = -1;
        host.setAttribute("aria-labelledby", "detailsTitle");

        var header = el("div", "offcanvas-header");
        var title = el("h2", "offcanvas-title", "Details");
        title.id = "detailsTitle";
        header.appendChild(title);

        var close = el("button", "btn-close");
        close.type = "button";
        close.setAttribute("data-bs-dismiss", "offcanvas");
        close.setAttribute("aria-label", "Close");
        header.appendChild(close);

        var body = el("div", "offcanvas-body");
        body.id = "detailsBody";

        host.appendChild(header);
        host.appendChild(body);
        document.body.appendChild(host);

        detailsOffcanvas = new bootstrap.Offcanvas(host);
        return detailsOffcanvas;
    }

    function detailRow(key, value) {
        var row = el("div", "kv-row");
        row.appendChild(el("span", "k", key));
        row.appendChild(el("span", "v", value));
        return row;
    }

    async function openDetails(file) {
        var drawer = ensureDetails();
        var body = document.getElementById("detailsBody");
        UI.clear(body);

        var hero = el("div", "details-hero");
        hero.appendChild(UI.typeChip(file.original_name, file.file_type, "lg"));
        hero.appendChild(el("h3", null, file.original_name));
        hero.appendChild(el("div", "dh-type", UI.typeLabel(file.original_name, file.file_type)));
        body.appendChild(hero);

        var rows = el("div");
        rows.appendChild(detailRow("Owner", "You"));
        rows.appendChild(detailRow("Size", UI.formatSize(file.file_size)));
        rows.appendChild(detailRow("Type", file.file_type || "—"));
        rows.appendChild(detailRow("Location", "Loading…"));
        rows.appendChild(detailRow("Uploaded", UI.formatDateTime(file.uploaded_at)));
        rows.appendChild(detailRow("Modified", UI.formatDateTime(file.updated_at)));
        rows.appendChild(detailRow("Starred", file.is_starred ? "Yes" : "No"));
        body.appendChild(rows);

        var actions = el("div", "details-actions");

        var download = el("button", "btn-app-primary");
        download.type = "button";
        download.appendChild(icon("download"));
        download.appendChild(el("span", null, "Download"));
        download.addEventListener("click", function () { downloadFile(file); });

        var share = el("button", "btn-app-ghost");
        share.type = "button";
        share.appendChild(icon("share"));
        share.appendChild(el("span", null, "Share"));
        share.addEventListener("click", function () {
            drawer.hide();
            Sharing.open(file);
        });

        actions.appendChild(download);
        actions.appendChild(share);
        body.appendChild(actions);

        drawer.show();

        // Resolve the folder path for the Location row.
        var locationRow = rows.children[3].querySelector(".v");
        try {
            if (!file.folder_id) {
                locationRow.textContent = "My Files";
            } else {
                var contents = await API.folders.open(file.folder_id);
                locationRow.textContent = "My Files / " + contents.breadcrumb.map(function (crumb) {
                    return crumb.folder_name;
                }).join(" / ");
            }
        } catch (e) {
            locationRow.textContent = "—";
        }
    }


    /* ---------------------------------------------------------------------
       Menus
       ------------------------------------------------------------------ */

    function fileMenuItems(file) {
        return [
            { text: "Open", icon: "box-arrow-up-right", onSelect: function () { openFile(file); } },
            { text: "Download", icon: "download", onSelect: function () { downloadFile(file); } },
            { text: "Share", icon: "share", onSelect: function () { Sharing.open(file); } },
            { divider: true },
            {
                text: "Cut",
                icon: "scissors",
                onSelect: function () { Clipboard.cut({ files: [file], folders: [] }); }
            },
            {
                text: "Copy",
                icon: "files",
                onSelect: function () { Clipboard.copy({ files: [file], folders: [] }); }
            },
            { text: "Make a copy", icon: "file-earmark-plus", onSelect: function () { duplicateFile(file); } },
            { divider: true },
            { text: "Rename", icon: "pencil", onSelect: function () { renameFile(file); } },
            { text: "Move to…", icon: "folder-symlink", onSelect: function () { moveFile(file); } },
            {
                text: file.is_starred ? "Remove from Starred" : "Add to Starred",
                icon: file.is_starred ? "star-fill" : "star",
                onSelect: function () { toggleStar(file); }
            },
            { text: "Details", icon: "info-circle", onSelect: function () { openDetails(file); } },
            { divider: true },
            { text: "Move to Trash", icon: "trash3", danger: true, onSelect: function () { trashFile(file); } }
        ];
    }

    function folderMenuItems(folder, onOpen) {
        return [
            { text: "Open", icon: "box-arrow-up-right", onSelect: function () { onOpen(); } },
            {
                text: "Download as ZIP",
                icon: "file-earmark-zip",
                onSelect: function () { downloadFolder(folder); }
            },
            { text: "Share", icon: "share", onSelect: function () { Sharing.openFolder(folder); } },
            { divider: true },
            {
                text: "Cut",
                icon: "scissors",
                onSelect: function () { Clipboard.cut({ files: [], folders: [folder] }); }
            },
            {
                text: "Copy",
                icon: "files",
                onSelect: function () { Clipboard.copy({ files: [], folders: [folder] }); }
            },
            {
                text: "Paste into this folder",
                icon: "clipboard-check",
                disabled: Clipboard.isEmpty(),
                onSelect: function () { Clipboard.pasteInto(folder.id); }
            },
            { text: "Make a copy", icon: "folder-plus", onSelect: function () { duplicateFolder(folder); } },
            { divider: true },
            { text: "Rename", icon: "pencil", onSelect: function () { renameFolder(folder); } },
            { text: "Move to…", icon: "folder-symlink", onSelect: function () { moveFolder(folder); } },
            { divider: true },
            { text: "Delete", icon: "trash3", danger: true, onSelect: function () { deleteFolder(folder); } }
        ];
    }


    /* ---------------------------------------------------------------------
       Cards + rows
       ------------------------------------------------------------------ */

    function folderCard(folder, onOpen) {
        var card = el("div", "folder-card");
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute("aria-label", "Folder " + folder.folder_name);

        card.appendChild(UI.folderChip("md"));

        var text = el("div", "fc-text");
        var name = el("div", "fc-name", folder.folder_name);
        name.title = folder.folder_name;
        text.appendChild(name);

        var bits = [];
        bits.push(folder.file_count + (folder.file_count === 1 ? " file" : " files"));
        if (folder.subfolder_count) {
            bits.push(folder.subfolder_count + (folder.subfolder_count === 1 ? " folder" : " folders"));
        }
        text.appendChild(el("div", "fc-meta", bits.join(" · ")));
        card.appendChild(text);

        card.appendChild(Menu.dotTrigger("Actions for " + folder.folder_name, function () {
            return folderMenuItems(folder, onOpen);
        }));

        card.addEventListener("click", function (e) {
            if (e.target.closest(".row-actions")) { return; }
            onOpen();
        });

        card.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen();
            }
        });

        Selection.decorate(card, "folder", folder);
        return card;
    }

    function fileCard(file) {
        var card = el("div", "file-card");
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute("aria-label", file.original_name);

        card.appendChild(UI.typeChip(file.original_name, file.file_type, "md"));

        var name = el("div", "fc-name", file.original_name);
        name.title = file.original_name;
        if (file.is_starred) {
            name.appendChild(icon("star-fill", "star-flag"));
        }
        card.appendChild(name);

        card.appendChild(el(
            "div",
            "fc-meta",
            UI.formatSize(file.file_size) + " · " + UI.timeAgo(file.updated_at)
        ));

        card.appendChild(Menu.dotTrigger("Actions for " + file.original_name, function () {
            return fileMenuItems(file);
        }));

        card.addEventListener("dblclick", function () { openFile(file); });
        card.addEventListener("keydown", function (e) {
            if (e.key === "Enter") { e.preventDefault(); openFile(file); }
        });

        Selection.decorate(card, "file", file);
        return card;
    }

    /**
     * A table row. `columns` picks which cells appear so Recent can show a
     * Location column that My Files does not need.
     */
    function fileRow(file, columns, context) {
        columns = columns || ["size", "modified", "actions"];
        context = context || {};

        var row = document.createElement("tr");

        var nameCell = document.createElement("td");
        var nameWrap = el("div", "cell-name");
        nameWrap.appendChild(UI.typeChip(file.original_name, file.file_type, "sm"));

        var nameText = el("span", "n", file.original_name);
        nameText.title = file.original_name;
        nameWrap.appendChild(nameText);

        if (file.is_starred) { nameWrap.appendChild(icon("star-fill", "star-flag")); }
        nameCell.appendChild(nameWrap);
        row.appendChild(nameCell);

        if (columns.indexOf("type") !== -1) {
            row.appendChild(cell(UI.typeLabel(file.original_name, file.file_type)));
        }
        if (columns.indexOf("owner") !== -1) {
            row.appendChild(cell(file.owner_name || "You"));
        }
        if (columns.indexOf("size") !== -1) {
            row.appendChild(cell(UI.formatSize(file.file_size), "num"));
        }
        if (columns.indexOf("modified") !== -1) {
            row.appendChild(cell(UI.timeAgo(file.updated_at), "num"));
        }
        if (columns.indexOf("location") !== -1) {
            var location = cell(context.locationOf ? context.locationOf(file) : "—");
            location.classList.add("truncate");
            row.appendChild(location);
        }

        var actionCell = document.createElement("td");
        actionCell.className = "cell-actions";
        var actions = Menu.dotTrigger("Actions for " + file.original_name, function () {
            return fileMenuItems(file);
        });
        actions.style.position = "static";
        actions.style.opacity = "1";
        actionCell.appendChild(actions);
        row.appendChild(actionCell);

        row.addEventListener("dblclick", function () { openFile(file); });

        // The checkbox joins the name cell's flex row rather than the bare <td>,
        // so it lines up with the type chip instead of stacking above it.
        Selection.decorate(row, "file", file, nameWrap);
        return row;
    }

    function cell(text, className) {
        var node = document.createElement("td");
        node.textContent = text;
        if (className) { node.className = className; }
        return node;
    }

    /** Table shell with a caption-less header for the list view. */
    function fileTable(headers) {
        var wrap = el("div", "table-wrap");
        var scroll = el("div", "table-scroll");

        var table = el("table", "app-table");
        var thead = document.createElement("thead");
        var headRow = document.createElement("tr");

        headers.forEach(function (header) {
            var th = document.createElement("th");
            if (header.sortKey) {
                var button = el("button", "sort-btn");
                button.type = "button";
                button.dataset.sortKey = header.sortKey;
                button.appendChild(document.createTextNode(header.label));
                button.appendChild(icon("arrow-down"));
                th.appendChild(button);
            } else {
                th.textContent = header.label;
                if (header.label === "") { th.setAttribute("aria-label", "Actions"); }
            }
            if (header.className) { th.className = header.className; }
            headRow.appendChild(th);
        });

        thead.appendChild(headRow);
        table.appendChild(thead);

        var tbody = document.createElement("tbody");
        table.appendChild(tbody);

        scroll.appendChild(table);
        wrap.appendChild(scroll);

        return { wrap: wrap, table: table, tbody: tbody, thead: thead };
    }

    global.Files = {
        // actions
        openFile: openFile,
        downloadFile: downloadFile,
        renameFile: renameFile,
        renameFolder: renameFolder,
        toggleStar: toggleStar,
        trashFile: trashFile,
        deleteFolder: deleteFolder,
        moveFile: moveFile,
        moveFolder: moveFolder,
        downloadFolder: downloadFolder,
        duplicateFile: duplicateFile,
        duplicateFolder: duplicateFolder,
        openDetails: openDetails,

        /** The folder picker, reused by the multi-select "Move to…" action. */
        pickDestination: moveDialog,

        // menus
        fileMenuItems: fileMenuItems,
        folderMenuItems: folderMenuItems,

        // components
        folderCard: folderCard,
        fileCard: fileCard,
        fileRow: fileRow,
        fileTable: fileTable
    };
}(window));
