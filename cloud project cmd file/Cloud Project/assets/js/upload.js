/* =========================================================================
   UPLOAD
   A non-blocking upload panel plus a whole-window drag-and-drop target.
   Uploads run one file at a time so each row shows its own real progress
   and one rejected file never cancels the rest.

   Folders keep their shape. Whether a folder arrives through "Upload folder"
   or is dropped onto the page, every directory inside it is read first, the
   whole tree is created server-side in one call, and each file is then sent
   straight into the folder it came from - however deeply nested.
   ========================================================================= */

(function (global) {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var nodes = {};
    var queue = [];
    var running = false;
    var idSeed = 0;

    /** Refuse absurd drops rather than hanging the browser on them. */
    var MAX_ITEMS = 5000;


    /* ---------------------------------------------------------------------
       Panel
       ------------------------------------------------------------------ */

    function buildPanel() {
        var panel = el("div", "upload-panel");
        panel.id = "uploadPanel";
        panel.setAttribute("role", "region");
        panel.setAttribute("aria-label", "Uploads");

        var head = el("div", "upload-panel-head");

        var title = el("h3", null, "Uploading");
        title.id = "uploadPanelTitle";
        head.appendChild(title);

        var collapse = el("button", "icon-btn");
        collapse.type = "button";
        collapse.id = "uploadCollapse";
        collapse.setAttribute("aria-label", "Collapse uploads");
        collapse.appendChild(icon("chevron-down"));
        head.appendChild(collapse);

        var close = el("button", "icon-btn");
        close.type = "button";
        close.id = "uploadClose";
        close.setAttribute("aria-label", "Close uploads");
        close.appendChild(icon("x-lg"));
        head.appendChild(close);

        panel.appendChild(head);

        var summary = el("div", "upload-summary");
        var summaryLine = el("div", "upload-summary-line");
        var summaryText = el("strong", null, "Preparing uploads");
        summaryText.id = "uploadSummaryText";
        var summaryPercent = el("span", null, "0%");
        summaryPercent.id = "uploadSummaryPercent";
        summaryLine.appendChild(summaryText);
        summaryLine.appendChild(summaryPercent);
        summary.appendChild(summaryLine);

        var overallMeter = el("div", "meter upload-overall-meter");
        var overallFill = el("div", "meter-fill");
        overallFill.id = "uploadOverallFill";
        overallMeter.appendChild(overallFill);
        summary.appendChild(overallMeter);

        var summaryMeta = el("div", "upload-summary-meta", "0 of 0 complete");
        summaryMeta.id = "uploadSummaryMeta";
        summary.appendChild(summaryMeta);
        panel.appendChild(summary);

        var list = el("div", "upload-list");
        list.id = "uploadList";
        panel.appendChild(list);

        document.body.appendChild(panel);

        nodes.panel = panel;
        nodes.title = title;
        nodes.list = list;
        nodes.summaryText = summaryText;
        nodes.summaryPercent = summaryPercent;
        nodes.summaryMeta = summaryMeta;
        nodes.overallFill = overallFill;

        collapse.addEventListener("click", function () {
            var hidden = list.classList.toggle("is-hidden");
            UI.fill(collapse, icon(hidden ? "chevron-up" : "chevron-down"));
            collapse.setAttribute("aria-label", hidden ? "Expand uploads" : "Collapse uploads");
            publishPanelHeight();
        });

        close.addEventListener("click", function () {
            panel.classList.remove("show");
            publishPanelHeight();
        });
    }

    function buildHiddenInputs() {
        var files = document.createElement("input");
        files.type = "file";
        files.id = "uploadFilesInput";
        files.multiple = true;
        files.hidden = true;
        document.body.appendChild(files);

        var folder = document.createElement("input");
        folder.type = "file";
        folder.id = "uploadFolderInput";
        folder.multiple = true;
        folder.hidden = true;
        folder.setAttribute("webkitdirectory", "");
        folder.setAttribute("directory", "");
        document.body.appendChild(folder);

        files.addEventListener("change", function () {
            var picked = fromFileList(this.files);
            this.value = "";
            enqueue(picked);
        });

        folder.addEventListener("change", function () {
            var picked = fromFileList(this.files);
            this.value = "";
            enqueue(picked);
        });

        nodes.filesInput = files;
        nodes.folderInput = folder;
    }

    function buildDropOverlay() {
        var overlay = el("div", "drop-overlay");
        overlay.id = "dropOverlay";

        var inner = el("div", "drop-inner");
        inner.appendChild(icon("cloud-arrow-up"));
        inner.appendChild(el("h3", null, "Drop files or folders to upload"));
        inner.appendChild(el("p", null, "Folders keep their structure"));

        overlay.appendChild(inner);
        document.body.appendChild(overlay);
        nodes.overlay = overlay;
    }


    /* ---------------------------------------------------------------------
       Reading what the user gave us

       Two very different sources produce the same shape: a list of
       { file, dir } where `dir` is the path of the folder the file lived in,
       relative to whatever is being uploaded ("" for a loose file).
       ------------------------------------------------------------------ */

    function dirOf(relativePath) {
        if (!relativePath) { return ""; }
        var parts = relativePath.replace(/\\/g, "/").split("/");
        parts.pop();                                  // drop the file name
        return parts.filter(Boolean).join("/");
    }

    /** `<input webkitdirectory>` fills in webkitRelativePath; plain files do not. */
    function fromFileList(fileList) {
        return Array.prototype.map.call(fileList, function (file) {
            return { file: file, dir: dirOf(file.webkitRelativePath) };
        });
    }

    function readEntriesBatch(reader) {
        return new Promise(function (resolve, reject) {
            reader.readEntries(resolve, reject);
        });
    }

    function fileOfEntry(entry) {
        return new Promise(function (resolve, reject) {
            entry.file(resolve, reject);
        });
    }

    /**
     * Walks one dropped entry. Directory readers hand back their children in
     * batches and signal the end with an empty batch, so each one has to be
     * drained in a loop rather than read once.
     */
    async function walkEntry(entry, dir, collected) {
        if (collected.length >= MAX_ITEMS) { return; }

        if (entry.isFile) {
            try {
                collected.push({ file: await fileOfEntry(entry), dir: dir });
            } catch (e) { /* unreadable file: skip it, keep the rest */ }
            return;
        }

        if (!entry.isDirectory) { return; }

        var childDir = dir ? (dir + "/" + entry.name) : entry.name;
        var reader = entry.createReader();

        while (true) {
            var batch;
            try {
                batch = await readEntriesBatch(reader);
            } catch (e) {
                break;
            }
            if (!batch.length) { break; }

            for (var i = 0; i < batch.length; i += 1) {
                await walkEntry(batch[i], childDir, collected);
            }
        }

        // An empty folder still deserves to exist after the upload.
        if (!collected.some(function (item) { return item.dir === childDir; })) {
            collected.push({ file: null, dir: childDir });
        }
    }

    /**
     * Drops give us DataTransferItems. `webkitGetAsEntry()` is the only way to
     * see inside a dropped folder, and the items list is emptied as soon as the
     * event handler returns - so every entry is grabbed up front, before any
     * awaiting starts.
     */
    async function fromDataTransfer(dataTransfer) {
        var items = dataTransfer.items;
        var entries = [];

        if (items && items.length && items[0].webkitGetAsEntry) {
            for (var i = 0; i < items.length; i += 1) {
                if (items[i].kind !== "file") { continue; }
                var entry = items[i].webkitGetAsEntry();
                if (entry) { entries.push(entry); }
            }
        }

        if (!entries.length) {
            // Older browsers, or a drop with no directory support: plain files.
            return fromFileList(dataTransfer.files);
        }

        var collected = [];
        for (var j = 0; j < entries.length; j += 1) {
            await walkEntry(entries[j], "", collected);
        }
        return collected;
    }


    /* ---------------------------------------------------------------------
       Rows
       ------------------------------------------------------------------ */

    function buildRow(job) {
        var row = el("div", "upload-item");
        row.dataset.jobId = job.id;

        row.appendChild(UI.typeChip(job.name, job.file ? job.file.type : "", "sm"));

        var body = el("div", "ui-body");

        var name = el("div", "ui-name", job.name);
        name.title = job.dir ? (job.dir + "/" + job.name) : job.name;
        body.appendChild(name);

        // Showing the folder path is the whole point of a structured upload:
        // it is how the user can see the nesting was understood.
        if (job.dir) {
            var path = el("div", "ui-path", job.dir);
            path.title = job.dir;
            body.appendChild(path);
        }

        var meta = el("div", "ui-meta", "Waiting…");
        body.appendChild(meta);

        var meter = el("div", "meter");
        var fill = el("div", "meter-fill");
        meter.appendChild(fill);
        body.appendChild(meter);

        row.appendChild(body);

        var status = el("button", "ui-status icon-btn");
        status.type = "button";
        status.setAttribute("aria-label", "Remove from list");
        status.appendChild(icon("x"));
        row.appendChild(status);

        status.addEventListener("click", function () {
            if (job.state === "queued" || job.state === "done" || job.state === "error") {
                queue = queue.filter(function (item) { return item !== job; });
            }
            if (job.state === "uploading") {
                job.cancelled = true;
                if (job.xhr) { job.xhr.abort(); }
            }
            row.remove();
            updateTitle();
            publishPanelHeight();
        });

        job.nodes = { row: row, meta: meta, fill: fill, meter: meter, status: status };
        nodes.list.appendChild(row);
        publishPanelHeight();
    }

    function setRowState(job, kind, message) {
        var ui = job.nodes;
        if (!ui) { return; }

        ui.meta.textContent = message;

        if (kind === "done") {
            ui.meter.classList.add("is-hidden");
            UI.fill(ui.status, icon("check-circle-fill"));
            ui.status.className = "ui-status ok";
            ui.status.disabled = true;
        } else if (kind === "error") {
            ui.meter.classList.add("is-hidden");
            UI.fill(ui.status, icon("exclamation-circle-fill"));
            ui.status.className = "ui-status err";
            ui.status.disabled = true;
        }
    }

    function sizeOf(job) {
        return job.file ? job.file.size : 0;
    }

    function updateTitle() {
        if (!nodes.title) { return; }

        var active = queue.filter(function (job) {
            return job.state === "queued" || job.state === "preparing" || job.state === "uploading";
        }).length;

        var done = queue.filter(function (job) { return job.state === "done"; }).length;
        var failed = queue.filter(function (job) { return job.state === "error"; }).length;

        if (active) {
            nodes.title.textContent = "Uploading " + active + " item" + (active === 1 ? "" : "s");
        } else if (failed) {
            nodes.title.textContent = done + " uploaded · " + failed + " failed";
        } else {
            nodes.title.textContent = done + " upload" + (done === 1 ? "" : "s") + " complete";
        }

        var total = queue.length;
        var completed = done + failed;
        var remaining = Math.max(0, total - completed);
        var totalBytes = queue.reduce(function (sum, job) { return sum + sizeOf(job); }, 0);
        var uploadedBytes = queue.reduce(function (sum, job) {
            return sum + (job.state === "done" ? sizeOf(job) : sizeOf(job) * (job.progress || 0) / 100);
        }, 0);
        var percent = totalBytes ? Math.min(100, Math.round(uploadedBytes / totalBytes * 100)) : 0;

        nodes.summaryText.textContent = completed + " of " + total + " files complete";
        nodes.summaryPercent.textContent = percent + "%";
        nodes.summaryMeta.textContent = remaining
            ? remaining + " remaining · " + UI.formatSize(Math.max(0, totalBytes - uploadedBytes)) + " left"
            : (failed ? failed + " failed" : "All files uploaded");
        nodes.overallFill.style.width = percent + "%";
    }


    /* ---------------------------------------------------------------------
       Queue
       ------------------------------------------------------------------ */

    /** Toasts read this so they stack above the panel instead of behind it. */
    function publishPanelHeight() {
        var open = nodes.panel && nodes.panel.classList.contains("show");
        document.documentElement.style.setProperty(
            "--upload-panel-h",
            open ? (nodes.panel.offsetHeight + 12) + "px" : "0px"
        );
    }

    async function enqueue(items) {
        if (!items || !items.length) { return; }

        if (items.length > MAX_ITEMS) {
            UI.toast(
                "Only the first " + MAX_ITEMS + " items of that folder will be uploaded",
                "error",
                6000
            );
            items = items.slice(0, MAX_ITEMS);
        }

        if (queue.every(function (job) { return job.state === "done" || job.state === "error"; })) {
            queue = [];
            UI.clear(nodes.list);
        }

        nodes.panel.classList.add("show");
        nodes.list.classList.remove("is-hidden");
        requestAnimationFrame(publishPanelHeight);

        var batch = [];

        items.forEach(function (item) {
            // A folder placeholder carries no file: it only exists so that an
            // empty directory still gets created.
            if (!item.file) {
                batch.push({ id: 0, file: null, dir: item.dir, state: "folder-only" });
                return;
            }

            idSeed += 1;
            var job = {
                id: idSeed,
                file: item.file,
                dir: item.dir || "",
                name: item.file.name,
                baseFolderId: Shell.uploadFolderId,
                folderId: Shell.uploadFolderId,
                state: "preparing",
                cancelled: false,
                progress: 0
            };
            queue.push(job);
            batch.push(job);
            buildRow(job);
        });

        updateTitle();
        publishPanelHeight();

        await prepareFolders(batch);
        drain();
    }

    /**
     * Creates every directory the batch needs, in one request, then points each
     * job at the folder it belongs in. Files sitting at the top level skip this
     * entirely and go straight to the folder currently being browsed.
     */
    async function prepareFolders(batch) {
        var uploads = batch.filter(function (job) { return job.state === "preparing"; });
        var nested = batch.filter(function (job) { return job.dir; });

        if (!nested.length) {
            uploads.forEach(function (job) { job.state = "queued"; });
            return;
        }

        var seen = {};
        var paths = [];
        nested.forEach(function (job) {
            if (!seen[job.dir]) {
                seen[job.dir] = true;
                paths.push(job.dir);
            }
        });

        uploads.forEach(function (job) {
            if (job.dir) { setRowState(job, "progress", "Creating folders…"); }
        });

        var base = batch.length && batch[0].baseFolderId !== undefined
            ? batch[0].baseFolderId
            : Shell.uploadFolderId;

        try {
            var result = await API.folders.tree(base, paths);

            uploads.forEach(function (job) {
                if (!job.dir) {
                    job.state = "queued";
                    return;
                }

                var target = result.resolved[job.dir];
                if (target === undefined || target === null) {
                    job.state = "error";
                    setRowState(job, "error", "Could not create the folder for this file");
                    return;
                }

                job.folderId = target;
                job.state = "queued";
            });

            if (result.created) {
                UI.toast(
                    result.created + " folder" + (result.created === 1 ? "" : "s") + " created",
                    "success"
                );
                // Empty folders have nothing to upload, so refresh for them now.
                document.dispatchEvent(new CustomEvent("Cloud:refresh"));
            }
        } catch (err) {
            uploads.forEach(function (job) {
                if (!job.dir) {
                    job.state = "queued";
                    return;
                }
                job.state = "error";
                setRowState(job, "error", err.message || "Could not create folders");
            });
            if (err.status === 401) { UI.reportError(err); }
        }

        updateTitle();
    }

    async function drain() {
        if (running) { return; }
        running = true;

        while (true) {
            var job = queue.find(function (item) { return item.state === "queued"; });
            if (!job) { break; }

            job.state = "uploading";
            updateTitle();
            setRowState(job, "progress", "Starting…");

            try {
                var result = await API.files.upload([job.file], job.folderId, function (percent) {
                    job.progress = percent;
                    if (job.nodes) {
                        job.nodes.fill.style.width = percent + "%";
                        job.nodes.meta.textContent =
                            percent + "% · " + UI.formatSize(job.file.size);
                    }
                });

                if (result.failed && result.failed.length) {
                    job.state = "error";
                    setRowState(job, "error", result.failed[0].message);
                } else {
                    job.state = "done";
                    setRowState(job, "done", UI.formatSize(job.file.size) + " · Uploaded");
                }
            } catch (err) {
                job.state = "error";

                if (job.cancelled) {
                    setRowState(job, "error", "Cancelled");
                } else {
                    setRowState(job, "error", err.message || "Upload failed");
                    if (err.status === 401) { UI.reportError(err); }
                }
            }

            updateTitle();
        }

        running = false;

        var done = queue.filter(function (job) { return job.state === "done"; }).length;
        var failed = queue.filter(function (job) { return job.state === "error"; }).length;

        if (done) {
            UI.toast(
                done + " file" + (done === 1 ? "" : "s") + " uploaded",
                "success"
            );
        }
        if (failed) {
            UI.toast(
                failed + " upload" + (failed === 1 ? "" : "s") + " failed",
                "error",
                6000
            );
        }

        // Let the current page reload its listing, and refresh storage figures.
        document.dispatchEvent(new CustomEvent("Cloud:refresh"));
        Shell.refreshStats();
    }


    /* ---------------------------------------------------------------------
       Drag and drop
       ------------------------------------------------------------------ */

    function wireDragDrop() {
        var depth = 0;

        function hasFiles(event) {
            if (!event.dataTransfer) { return false; }
            return Array.prototype.indexOf.call(event.dataTransfer.types || [], "Files") !== -1;
        }

        window.addEventListener("dragenter", function (e) {
            if (!hasFiles(e)) { return; }
            e.preventDefault();
            depth += 1;
            nodes.overlay.classList.add("show");
        });

        window.addEventListener("dragover", function (e) {
            if (!hasFiles(e)) { return; }
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
        });

        window.addEventListener("dragleave", function (e) {
            if (!hasFiles(e)) { return; }
            depth = Math.max(0, depth - 1);
            if (depth === 0) { nodes.overlay.classList.remove("show"); }
        });

        window.addEventListener("drop", function (e) {
            if (!hasFiles(e)) { return; }
            e.preventDefault();
            depth = 0;
            nodes.overlay.classList.remove("show");

            // Read the drop synchronously enough to keep the entry handles, then
            // hand the collected items to the queue.
            fromDataTransfer(e.dataTransfer).then(enqueue, function (err) {
                UI.toast(err.message || "Could not read that drop", "error");
            });
        });
    }


    /* ---------------------------------------------------------------------
       Public
       ------------------------------------------------------------------ */

    var ready = false;

    function init() {
        if (ready) { return; }
        ready = true;

        buildPanel();
        buildHiddenInputs();
        buildDropOverlay();
        wireDragDrop();
    }

    global.Upload = {
        init: init,
        pickFiles: function () { init(); nodes.filesInput.click(); },
        pickFolder: function () { init(); nodes.folderInput.click(); },
        add: function (files) { init(); enqueue(fromFileList(files)); }
    };
}(window));
