/* =========================================================================
   SELECTION + CLIPBOARD
   Multi-select over the cards and rows a browsing page renders, and the
   cut / copy / paste that acts on it.

   Two objects live here because they are two halves of one gesture: you pick
   things with Selection, then Clipboard carries them to another folder. The
   clipboard is kept in localStorage rather than memory so a cut survives
   navigating into the folder you meant to paste into - which is, of course,
   the only way anybody ever uses it.
   ========================================================================= */

(function (global) {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var CLIPBOARD_KEY = "Cloud_clipboard";


    /* =====================================================================
       Clipboard
       ================================================================== */

    function readClipboard() {
        try {
            var raw = JSON.parse(localStorage.getItem(CLIPBOARD_KEY) || "null");
            if (!raw || (raw.op !== "cut" && raw.op !== "copy")) { return null; }
            raw.files = raw.files || [];
            raw.folders = raw.folders || [];
            if (!raw.files.length && !raw.folders.length) { return null; }
            return raw;
        } catch (e) {
            return null;
        }
    }

    function writeClipboard(value) {
        try {
            if (value) {
                localStorage.setItem(CLIPBOARD_KEY, JSON.stringify(value));
            } else {
                localStorage.removeItem(CLIPBOARD_KEY);
            }
        } catch (e) { /* private mode: the clipboard is just not persisted */ }
        document.dispatchEvent(new CustomEvent("Cloud:clipboard"));
    }

    function describe(payload) {
        var total = payload.files.length + payload.folders.length;
        if (total === 1) {
            var only = payload.files[0] || payload.folders[0];
            return '"' + only.name + '"';
        }
        return total + " items";
    }

    /** Normalises whatever the caller passed into flat {id, name} lists. */
    function toPayload(input) {
        return {
            files: (input.files || []).map(function (file) {
                return { id: file.id, name: file.original_name || file.name };
            }),
            folders: (input.folders || []).map(function (folder) {
                return { id: folder.id, name: folder.folder_name || folder.name };
            })
        };
    }

    function put(op, input) {
        var payload = toPayload(input);
        if (!payload.files.length && !payload.folders.length) { return; }

        payload.op = op;
        writeClipboard(payload);

        UI.toast(
            describe(payload) + (op === "cut" ? " ready to move" : " copied") +
                " · open a folder and press Ctrl+V",
            "success"
        );
        Selection.clear();
    }

    /**
     * Pastes into `folderId`. A cut becomes a move and a copy becomes a real
     * duplicate; both go through the batch endpoints so one bad item is
     * reported without losing the rest.
     */
    async function pasteInto(folderId) {
        var data = readClipboard();
        if (!data) {
            UI.toast("There is nothing to paste", "error");
            return;
        }

        var target = (folderId === undefined) ? null : folderId;

        // Moving something into the folder it already sits in is a no-op, but
        // pasting a *copy* there is a legitimate "duplicate here".
        if (data.op === "cut" && data.folders.some(function (f) { return f.id === target; })) {
            UI.toast("A folder cannot be pasted inside itself", "error");
            return;
        }

        var action = data.op === "cut" ? "move" : "copy";
        var verb = data.op === "cut" ? "Moving" : "Copying";
        UI.toast(verb + " " + describe(data) + "…", "success");

        var moved = 0;
        var problems = [];

        try {
            if (data.folders.length) {
                var folderResult = await API.folders.batch(
                    action, data.folders.map(function (f) { return f.id; }), target
                );
                moved += folderResult.succeeded.length;
                problems = problems.concat(folderResult.failed);
            }

            if (data.files.length) {
                var fileResult = await API.files.batch(
                    action, data.files.map(function (f) { return f.id; }), target
                );
                moved += fileResult.succeeded.length;
                problems = problems.concat(fileResult.failed);
            }
        } catch (err) {
            UI.reportError(err);
            return;
        }

        if (moved) {
            UI.toast(
                moved + " item" + (moved === 1 ? "" : "s") +
                    (data.op === "cut" ? " moved here" : " pasted here"),
                "success"
            );
        }

        problems.forEach(function (problem) {
            UI.toast((problem.name || "An item") + ": " + problem.message, "error", 6000);
        });

        // A cut is spent once it lands; a copy stays on the clipboard so the
        // same thing can be pasted into several folders.
        if (data.op === "cut" && moved) { writeClipboard(null); }

        document.dispatchEvent(new CustomEvent("Cloud:refresh"));
        Shell.refreshStats();
    }

    var Clipboard = {
        copy: function (input) { put("copy", input); },
        cut: function (input) { put("cut", input); },
        peek: readClipboard,
        isEmpty: function () { return readClipboard() === null; },
        clear: function () { writeClipboard(null); },
        describe: function () {
            var data = readClipboard();
            return data ? describe(data) : "";
        },
        pasteInto: pasteInto
    };


    /* =====================================================================
       Selection
       ================================================================== */

    var context = null;      // set by the page that is currently listing items
    var chosen = { file: {}, folder: {} };
    var registry = [];       // every decorated node, in the order it rendered
    var lastIndex = -1;      // anchor for shift-click ranges
    var bar = null;

    function key(kind, id) { return kind + ":" + id; }

    function count() {
        return Object.keys(chosen.file).length + Object.keys(chosen.folder).length;
    }

    function selectedFiles() {
        return Object.keys(chosen.file).map(function (id) { return chosen.file[id]; });
    }

    function selectedFolders() {
        return Object.keys(chosen.folder).map(function (id) { return chosen.folder[id]; });
    }

    function isChosen(kind, id) {
        return Object.prototype.hasOwnProperty.call(chosen[kind], String(id));
    }

    function paint() {
        registry.forEach(function (entry) {
            var on = isChosen(entry.kind, entry.item.id);
            entry.node.classList.toggle("is-selected", on);
            if (entry.box) { entry.box.checked = on; }
        });

        document.body.classList.toggle("has-selection", count() > 0);
        renderBar();

        var all = document.getElementById("selectAll");
        if (all) {
            var total = registry.length;
            var picked = registry.filter(function (entry) {
                return isChosen(entry.kind, entry.item.id);
            }).length;

            // An empty listing has nothing to select. Left enabled, the box
            // would tick and then untick itself as this same function ran, which
            // reads as a broken control rather than an empty folder.
            all.disabled = total === 0;
            all.checked = total > 0 && picked === total;
            all.indeterminate = picked > 0 && picked < total;

            var control = all.closest(".select-all-control");
            if (control) {
                control.classList.toggle("is-disabled", total === 0);
                control.title = total === 0
                    ? "Nothing here to select"
                    : "Select all " + total + " item" + (total === 1 ? "" : "s");
            }
        }

        if (context && context.onChange) { context.onChange(count()); }
    }

    function set(kind, item, on) {
        if (on) {
            chosen[kind][String(item.id)] = item;
        } else {
            delete chosen[kind][String(item.id)];
        }
    }

    function toggle(kind, item) {
        set(kind, item, !isChosen(kind, item.id));
        paint();
    }

    /** Shift-click: everything between the anchor and this node, inclusive. */
    function extendTo(index) {
        if (lastIndex < 0) { lastIndex = index; }

        var from = Math.min(lastIndex, index);
        var to = Math.max(lastIndex, index);

        for (var i = from; i <= to; i += 1) {
            set(registry[i].kind, registry[i].item, true);
        }
        paint();
    }

    function clear() {
        chosen = { file: {}, folder: {} };
        lastIndex = -1;
        paint();
    }

    function selectAll() {
        registry.forEach(function (entry) { set(entry.kind, entry.item, true); });
        paint();
    }

    /**
     * Called by every card and row as it is built. When no page has registered
     * a selection context - the dashboard, Trash, Shared with me - this does
     * nothing at all, so those screens keep their old behaviour.
     */
    function decorate(node, kind, item, host) {
        if (!context || !item || item.id === undefined) { return; }

        var index = registry.length;
        registry.push({ node: node, kind: kind, item: item, box: null });

        var wrap = el("label", "sel-check");
        wrap.title = "Select " + (item.original_name || item.folder_name || "item");

        var box = document.createElement("input");
        box.type = "checkbox";
        box.className = "sel-box";
        box.setAttribute("aria-label", wrap.title);
        wrap.appendChild(box);

        registry[index].box = box;

        box.addEventListener("click", function (e) {
            e.stopPropagation();
            if (e.shiftKey) {
                extendTo(index);
            } else {
                set(kind, item, box.checked);
                lastIndex = index;
                paint();
            }
        });

        // A row puts the checkbox inside the name cell; a card floats it in the
        // corner, where it only appears on hover until something is selected.
        (host || node).insertBefore(wrap, (host || node).firstChild);

        // Once a selection exists, a plain click extends it instead of opening
        // the item - otherwise picking a fifth file would navigate away.
        node.addEventListener("click", function (e) {
            if (e.target.closest(".row-actions") || e.target.closest(".sel-check")) { return; }

            if (e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                extendTo(index);
                return;
            }

            if (e.ctrlKey || e.metaKey || count() > 0) {
                e.preventDefault();
                e.stopPropagation();
                lastIndex = index;
                toggle(kind, item);
            }
        }, true);
    }

    /**
     * The page calls this before it renders a fresh listing. The registry is
     * rebuilt from scratch, and anything that is no longer on screen drops out
     * of the selection rather than lingering invisibly.
     */
    function configure(next) {
        context = next;
        registry = [];
        lastIndex = -1;
    }

    function reconcile() {
        var live = {};
        registry.forEach(function (entry) { live[key(entry.kind, entry.item.id)] = true; });

        ["file", "folder"].forEach(function (kind) {
            Object.keys(chosen[kind]).forEach(function (id) {
                if (!live[key(kind, id)]) { delete chosen[kind][id]; }
            });
        });

        paint();
    }


    /* ---------------------------------------------------------------------
       Action bar
       ------------------------------------------------------------------ */

    function barButton(label, iconName, handler, danger) {
        var button = el("button", "sel-action" + (danger ? " is-danger" : ""));
        button.type = "button";
        button.appendChild(icon(iconName));
        button.appendChild(el("span", null, label));
        button.addEventListener("click", handler);
        return button;
    }

    function ensureBar() {
        if (bar) { return bar; }

        bar = el("div", "selection-bar");
        bar.id = "selectionBar";
        bar.setAttribute("role", "region");
        bar.setAttribute("aria-label", "Selected items");
        document.body.appendChild(bar);
        return bar;
    }

    function renderBar() {
        var total = count();

        if (!total) {
            if (bar) { bar.classList.remove("show"); }
            return;
        }

        var host = ensureBar();
        UI.clear(host);

        var files = selectedFiles();
        var folders = selectedFolders();

        var close = el("button", "icon-btn");
        close.type = "button";
        close.setAttribute("aria-label", "Clear selection");
        close.appendChild(icon("x-lg"));
        close.addEventListener("click", clear);
        host.appendChild(close);

        var bits = [];
        if (folders.length) {
            bits.push(folders.length + (folders.length === 1 ? " folder" : " folders"));
        }
        if (files.length) {
            bits.push(files.length + (files.length === 1 ? " file" : " files"));
        }
        host.appendChild(el("strong", "sel-count", bits.join(" · ") + " selected"));

        var actions = el("div", "sel-actions");

        actions.appendChild(barButton("Download", "download", downloadSelection));

        // Sharing is a per-item conversation, so it only makes sense for one.
        if (total === 1) {
            actions.appendChild(barButton("Share", "share", function () {
                if (files.length) {
                    Sharing.open(files[0]);
                } else {
                    Sharing.openFolder(folders[0]);
                }
            }));
        }

        actions.appendChild(barButton("Cut", "scissors", function () {
            Clipboard.cut({ files: files, folders: folders });
        }));
        actions.appendChild(barButton("Copy", "files", function () {
            Clipboard.copy({ files: files, folders: folders });
        }));
        actions.appendChild(barButton("Move to…", "folder-symlink", moveSelection));

        if (files.length) {
            var allStarred = files.every(function (file) { return file.is_starred; });
            actions.appendChild(barButton(
                allStarred ? "Unstar" : "Star",
                allStarred ? "star-fill" : "star",
                function () { starSelection(!allStarred); }
            ));
        }

        actions.appendChild(barButton("Delete", "trash3", deleteSelection, true));

        host.appendChild(actions);
        host.classList.add("show");
    }


    /* ---------------------------------------------------------------------
       Bulk actions
       ------------------------------------------------------------------ */

    async function downloadSelection() {
        var files = selectedFiles();
        var folders = selectedFolders();

        UI.toast("Preparing " + (files.length + folders.length) + " download(s)…", "success");

        // One at a time: browsers throttle or silently drop a burst of saves.
        for (var i = 0; i < folders.length; i += 1) {
            try {
                await API.folders.download(folders[i].id, folders[i].folder_name);
            } catch (err) {
                UI.toast(folders[i].folder_name + ": " + err.message, "error", 6000);
            }
        }

        for (var j = 0; j < files.length; j += 1) {
            try {
                await API.files.save(files[j].id, files[j].original_name);
            } catch (err) {
                UI.toast(files[j].original_name + ": " + err.message, "error", 6000);
            }
        }
    }

    async function moveSelection() {
        var files = selectedFiles();
        var folders = selectedFolders();

        var target = await Files.pickDestination({
            name: (files.length + folders.length) + " item(s)",
            currentFolderId: context ? context.folderId : null,
            // Moving a folder into itself is the one destination that cannot work.
            excludeFolderId: folders.length === 1 ? folders[0].id : null
        });
        if (target === undefined) { return; }

        await runBatch("move", files, folders, target, "moved");
    }

    async function starSelection(value) {
        var files = selectedFiles();
        if (!files.length) { return; }

        try {
            var result = await API.files.batch(
                value ? "star" : "unstar", files.map(function (f) { return f.id; })
            );
            UI.toast(result.message, result.success ? "success" : "error");
            finish();
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function deleteSelection() {
        var files = selectedFiles();
        var folders = selectedFolders();

        var message = folders.length
            ? "Deleting " + folders.length + " folder(s) also moves every file inside them to Trash."
            : "These files will be moved to Trash. You can restore them later.";

        var yes = await UI.confirmDialog({
            title: "Delete " + (files.length + folders.length) + " item(s)?",
            message: message,
            confirmText: "Move to Trash",
            danger: true,
            icon: "trash3"
        });
        if (!yes) { return; }

        await runBatch("delete", files, folders, null, "deleted");
    }

    /** Shared tail for move and delete: two batch calls, one report. */
    async function runBatch(action, files, folders, target, verb) {
        var done = 0;
        var problems = [];

        try {
            if (folders.length) {
                var folderResult = await API.folders.batch(
                    action === "delete" ? "delete" : action,
                    folders.map(function (f) { return f.id; }),
                    target
                );
                done += folderResult.succeeded.length;
                problems = problems.concat(folderResult.failed);
            }

            if (files.length) {
                var fileResult = await API.files.batch(
                    action === "delete" ? "trash" : action,
                    files.map(function (f) { return f.id; }),
                    target
                );
                done += fileResult.succeeded.length;
                problems = problems.concat(fileResult.failed);
            }
        } catch (err) {
            UI.reportError(err);
            return;
        }

        if (done) {
            UI.toast(done + " item" + (done === 1 ? "" : "s") + " " + verb, "success");
        }
        problems.forEach(function (problem) {
            UI.toast((problem.name || "An item") + ": " + problem.message, "error", 6000);
        });

        finish();
    }

    function finish() {
        clear();
        document.dispatchEvent(new CustomEvent("Cloud:refresh"));
        Shell.refreshStats();
    }


    /* ---------------------------------------------------------------------
       Keyboard

       Only while a browsing page is mounted, and never while the user is
       typing into the filter box or a dialog.
       ------------------------------------------------------------------ */

    function typingInto(target) {
        if (!target) { return false; }
        var tag = target.tagName;
        return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
    }

    document.addEventListener("keydown", function (e) {
        if (!context || typingInto(e.target)) { return; }
        if (document.querySelector(".modal.show")) { return; }

        var accel = e.ctrlKey || e.metaKey;

        if (accel && (e.key === "a" || e.key === "A")) {
            e.preventDefault();
            selectAll();
            return;
        }

        if (accel && (e.key === "v" || e.key === "V")) {
            if (context.canPaste === false) { return; }
            e.preventDefault();
            Clipboard.pasteInto(context.folderId);
            return;
        }

        if (!count()) { return; }

        if (accel && (e.key === "c" || e.key === "C")) {
            e.preventDefault();
            Clipboard.copy({ files: selectedFiles(), folders: selectedFolders() });
        } else if (accel && (e.key === "x" || e.key === "X")) {
            e.preventDefault();
            Clipboard.cut({ files: selectedFiles(), folders: selectedFolders() });
        } else if (e.key === "Delete") {
            e.preventDefault();
            deleteSelection();
        } else if (e.key === "Escape") {
            clear();
        }
    });


    var Selection = {
        configure: configure,
        reconcile: reconcile,
        decorate: decorate,
        clear: clear,
        selectAll: selectAll,
        count: count,
        files: selectedFiles,
        folders: selectedFolders
    };

    global.Selection = Selection;
    global.Clipboard = Clipboard;
}(window));
