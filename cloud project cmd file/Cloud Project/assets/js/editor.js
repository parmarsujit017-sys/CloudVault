(function () {
    "use strict";

    var fileId = null;
    var fileType = "word";
    var fileName = "Document";
    var blockSaving = false;
    var lastSaved = null;
    var currentData = null;
    var contentEditor = null;

    function param(name) {
        var params = new URLSearchParams(location.search);
        return params.get(name);
    }

    function setStatus(text, state) {
        var host = document.getElementById("editorStatus");
        if (!host) { return; }
        host.textContent = text;
        host.className = "text-meta" + (state === "saving" ? " is-warning" : state === "saved" ? " is-success" : "");
    }

    function buildWordEditor(content) {
        var host = document.getElementById("editorHost");
        if (!host) { return; }
        host.innerHTML = "";

        var editor = document.createElement("div");
        editor.id = "docEditor";
        editor.setAttribute("contenteditable", "true");
        editor.style.minHeight = "480px";
        editor.style.outline = "none";
        editor.style.lineHeight = "1.65";
        editor.style.fontSize = "15px";
        editor.style.padding = "18px 20px";
        editor.style.whiteSpace = "pre-wrap";
        editor.style.borderRadius = "12px";
        editor.innerHTML = content || "<p></p>";
        host.appendChild(editor);
        contentEditor = editor;

        editor.addEventListener("input", function () {
            currentData = editor.innerHTML;
            setStatus("Unsaved changes", "dirty");
            debounceSave();
        });
    }

    function buildSheetEditor(data) {
        var host = document.getElementById("editorHost");
        if (!host) { return; }
        host.innerHTML = "";

        var wrapper = document.createElement("div");
        wrapper.style.overflowX = "auto";
        wrapper.style.padding = "8px 0";

        var table = document.createElement("table");
        table.style.width = "100%";
        table.style.borderCollapse = "collapse";
        table.style.minWidth = "620px";
        table.style.background = "var(--surface)";

        var rows = ((data && data.sheets) || [{ name: "Sheet1", data: [["", "", ""]] }])[0].data || [];
        var maxCols = 6;
        rows.forEach(function (row, rIndex) {
            var tr = document.createElement("tr");
            var rowCells = row || [];
            for (var cIndex = 0; cIndex < maxCols; cIndex += 1) {
                var cell = document.createElement("td");
                var value = rowCells[cIndex] !== undefined && rowCells[cIndex] !== null ? rowCells[cIndex] : "";
                var input = document.createElement("input");
                input.type = "text";
                input.value = value;
                input.style.width = "100%";
                input.style.minWidth = "110px";
                input.style.border = "1px solid var(--border)";
                input.style.background = "transparent";
                input.style.padding = "8px 10px";
                input.style.color = "var(--text)";
                input.dataset.row = String(rIndex);
                input.dataset.col = String(cIndex);
                input.addEventListener("input", function () {
                    var rowIndex = Number(this.dataset.row);
                    var colIndex = Number(this.dataset.col);
                    var grid = ensureSheetGrid();
                    if (!grid[rowIndex]) { grid[rowIndex] = []; }
                    grid[rowIndex][colIndex] = this.value;
                    currentData = { sheets: [{ name: "Sheet1", data: grid }] };
                    setStatus("Unsaved changes", "dirty");
                    debounceSave();
                });
                cell.appendChild(input);
                tr.appendChild(cell);
            }
            table.appendChild(tr);
        });

        var addRowBtn = document.createElement("button");
        addRowBtn.type = "button";
        addRowBtn.className = "btn-app-ghost btn-sm-app";
        addRowBtn.textContent = "Add row";
        addRowBtn.style.marginTop = "12px";
        addRowBtn.addEventListener("click", function () {
            var grid = ensureSheetGrid();
            grid.push(Array(6).fill(""));
            buildSheetEditor({ sheets: [{ name: "Sheet1", data: grid }] });
        });

        var addColBtn = document.createElement("button");
        addColBtn.type = "button";
        addColBtn.className = "btn-app-ghost btn-sm-app";
        addColBtn.style.marginLeft = "8px";
        addColBtn.style.marginTop = "12px";
        addColBtn.textContent = "Add column";
        addColBtn.addEventListener("click", function () {
            var grid = ensureSheetGrid();
            grid.forEach(function (row) { row.push(""); });
            buildSheetEditor({ sheets: [{ name: "Sheet1", data: grid }] });
        });

        wrapper.appendChild(table);
        wrapper.appendChild(addRowBtn);
        wrapper.appendChild(addColBtn);
        host.appendChild(wrapper);
        currentData = { sheets: [{ name: "Sheet1", data: rows }] };
    }

    function ensureSheetGrid() {
        var host = document.getElementById("editorHost");
        if (!host) { return []; }
        var existing = currentData && currentData.sheets ? currentData.sheets[0].data : [["", "", ""]];
        return existing.map(function (row) { return row.slice ? row.slice() : [row]; });
    }

    function debounceSave() {
        clearTimeout(debounceSave.timer);
        debounceSave.timer = setTimeout(function () {
            saveCurrentDocument();
        }, 700);
    }

    async function saveCurrentDocument() {
        if (!fileId || blockSaving) { return; }
        blockSaving = true;
        setStatus("Saving…", "saving");

        try {
            var payload = {};
            if (fileType === "word") {
                payload.document_content = currentData || contentEditor.innerHTML;
            } else {
                payload.spreadsheet_data = currentData || { sheets: [{ name: "Sheet1", data: [["", ""]] }] };
            }
            var saved = await API.files.update(fileId, payload);
            lastSaved = saved;
            currentData = fileType === "word" ? saved.document_content : saved.spreadsheet_data;
            setStatus("Saved", "saved");
            document.title = fileName + " · Cloud";
            
            // Close the editor tab after successful save
            setTimeout(function () {
                window.close();
            }, 1000);
        } catch (err) {
            UI.reportError(err);
            setStatus("Save failed", "error");
        } finally {
            setTimeout(function () { blockSaving = false; }, 300);
        }
    }

    async function loadDocument() {
        if (!fileId) { return; }
        setStatus("Loading…", "loading");
        try {
            var record = await API.files.get(fileId);
            fileName = record.original_name;
            fileType = record.kind || record.type || fileType;
            if (fileType === "word") {
                buildWordEditor(record.document_content || "<p></p>");
                currentData = record.document_content || "<p></p>";
            } else {
                buildSheetEditor(record.spreadsheet_data || { sheets: [{ name: "Sheet1", data: [["", "", ""]] }] });
                currentData = record.spreadsheet_data || { sheets: [{ name: "Sheet1", data: [["", "", ""]] }] };
            }
            setStatus("Ready", "ready");
            document.getElementById("pageTitle").textContent = record.original_name;
        } catch (err) {
            UI.reportError(err);
            setStatus("Could not load file", "error");
        }
    }

    function wireToolbar() {
        document.querySelectorAll("[data-command]").forEach(function (button) {
            button.addEventListener("click", function () {
                var command = button.dataset.command;
                var value = button.dataset.value || null;
                if (command === "createLink") {
                    var url = prompt("Enter a link URL:", "https://");
                    if (url) {
                        document.execCommand("createLink", false, url);
                    }
                    return;
                }
                if (command === "formatBlock") {
                    document.execCommand(command, false, value || "p");
                } else {
                    document.execCommand(command, false, value);
                }
                if (contentEditor) {
                    currentData = contentEditor.innerHTML;
                    setStatus("Unsaved changes", "dirty");
                    debounceSave();
                }
            });
        });

        document.getElementById("saveBtn").addEventListener("click", function () {
            clearTimeout(debounceSave.timer);
            saveCurrentDocument();
        });

        document.getElementById("downloadBtn").addEventListener("click", function () {
            if (!fileId) { return; }
            API.files.save(fileId, fileName);
        });
    }

    async function createNewDocument() {
        var params = new URLSearchParams(location.search);
        var mode = params.get("type") || "word";
        var name = prompt("File name", mode === "word" ? "Untitled Document" : "Untitled Spreadsheet");
        if (!name) { return; }
        try {
            var created = await API.files.create({ name: name, type: mode });
            location.href = "editor.html?id=" + created.id + "&type=" + mode;
        } catch (err) {
            UI.reportError(err);
        }
    }

    async function boot() {
        var user = await Shell.mount({ active: "files" });
        if (!user) { return; }

        fileId = param("id");
        fileType = param("type") || "word";
        if (!fileId) {
            await createNewDocument();
            return;
        }

        wireToolbar();
        await loadDocument();
    }

    boot();
}());
