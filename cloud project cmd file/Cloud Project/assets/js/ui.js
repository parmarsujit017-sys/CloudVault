/* =========================================================================
   UI PRIMITIVES
   Toasts, confirmation dialogs, skeletons, empty states, formatters and the
   file-type visual system. Everything here is framework free; Bootstrap is
   used only for its Modal/Dropdown/Offcanvas behaviour.
   ========================================================================= */

(function (global) {
    "use strict";

    /* ---------------------------------------------------------------------
       DOM helpers
       ------------------------------------------------------------------ */

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined && text !== null) { node.textContent = text; }
        return node;
    }

    function icon(name, className) {
        var node = document.createElement("i");
        node.className = "bi bi-" + name + (className ? " " + className : "");
        node.setAttribute("aria-hidden", "true");
        return node;
    }

    function clear(node) {
        while (node && node.firstChild) { node.removeChild(node.firstChild); }
    }

    function frag() {
        return document.createDocumentFragment();
    }

    /** Replace a node's children in one shot. */
    function fill(node, children) {
        if (!node) { return; }
        clear(node);
        (Array.isArray(children) ? children : [children]).forEach(function (child) {
            if (child) { node.appendChild(child); }
        });
    }

    function show(node, visible) {
        if (node) { node.classList.toggle("is-hidden", !visible); }
    }


    /* ---------------------------------------------------------------------
       Formatting
       ------------------------------------------------------------------ */

    function formatSize(bytes) {
        var num = Number(bytes) || 0;
        var units = ["B", "KB", "MB", "GB", "TB"];
        var i = 0;
        while (num >= 1024 && i < units.length - 1) {
            num /= 1024;
            i += 1;
        }
        return (i === 0 ? num.toFixed(0) : num.toFixed(1)) + " " + units[i];
    }

    function formatMB(mb) {
        return formatSize((Number(mb) || 0) * 1024 * 1024);
    }

    /** The API returns naive UTC timestamps; mark them so Date parses correctly. */
    function toDate(value) {
        if (!value) { return null; }
        var text = String(value);
        var date = new Date(/Z|[+-]\d\d:?\d\d$/.test(text) ? text : text + "Z");
        return isNaN(date.getTime()) ? null : date;
    }

    function formatDate(value) {
        var date = toDate(value);
        if (!date) { return "—"; }
        return date.toLocaleDateString(undefined, {
            day: "2-digit", month: "short", year: "numeric"
        });
    }

    function formatDateTime(value) {
        var date = toDate(value);
        if (!date) { return "—"; }
        return date.toLocaleString(undefined, {
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit"
        });
    }

    function formatTime(value) {
        var date = toDate(value);
        if (!date) { return ""; }
        return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    }

    /** "2 minutes ago" / "Yesterday" / a date once it is far enough back. */
    function timeAgo(value) {
        var date = toDate(value);
        if (!date) { return "—"; }

        var seconds = Math.round((Date.now() - date.getTime()) / 1000);
        if (seconds < 45) { return "Just now"; }
        if (seconds < 90) { return "1 minute ago"; }

        var minutes = Math.round(seconds / 60);
        if (minutes < 60) { return minutes + " minutes ago"; }

        var hours = Math.round(minutes / 60);
        if (hours < 24) { return hours + (hours === 1 ? " hour ago" : " hours ago"); }

        var days = Math.round(hours / 24);
        if (days === 1) { return "Yesterday"; }
        if (days < 7) { return days + " days ago"; }

        return formatDate(value);
    }

    /** Groups used by the Recent page and the activity timeline. */
    function dayBucket(value) {
        var date = toDate(value);
        if (!date) { return "Older"; }

        var startOfToday = new Date();
        startOfToday.setHours(0, 0, 0, 0);

        var diffDays = Math.floor((startOfToday.getTime() - date.getTime()) / 86400000);
        if (diffDays < 0) { return "Today"; }
        if (diffDays === 0) { return "Today"; }
        if (diffDays === 1) { return "Yesterday"; }
        if (diffDays < 7) { return "Earlier this week"; }
        if (diffDays < 30) { return "Earlier this month"; }
        return "Older";
    }

    var BUCKET_ORDER = ["Today", "Yesterday", "Earlier this week", "Earlier this month", "Older"];


    /* ---------------------------------------------------------------------
       File-type visual system
       ------------------------------------------------------------------ */

    var EXT_MAP = {
        pdf: "pdf",
        doc: "word", docx: "word", odt: "word", rtf: "word",
        xls: "excel", xlsx: "excel", csv: "excel", ods: "excel",
        ppt: "ppt", pptx: "ppt", odp: "ppt",
        png: "image", jpg: "image", jpeg: "image", gif: "image",
        webp: "image", svg: "image", bmp: "image", avif: "image",
        mp4: "video", mkv: "video", mov: "video", avi: "video", webm: "video",
        mp3: "audio", wav: "audio", ogg: "audio", m4a: "audio", flac: "audio",
        zip: "zip", rar: "zip", "7z": "zip", tar: "zip", gz: "zip",
        js: "code", ts: "code", py: "code", java: "code", c: "code", cpp: "code",
        html: "code", css: "code", json: "code", php: "code", rb: "code", go: "code",
        txt: "text", md: "text", log: "text"
    };

    var TYPE_ICON = {
        pdf: "filetype-pdf",
        word: "file-earmark-word",
        excel: "file-earmark-spreadsheet",
        ppt: "file-earmark-slides",
        image: "file-earmark-image",
        video: "file-earmark-play",
        audio: "file-earmark-music",
        zip: "file-earmark-zip",
        code: "file-earmark-code",
        text: "file-earmark-text",
        generic: "file-earmark",
        folder: "folder-fill"
    };

    var TYPE_LABEL = {
        pdf: "PDF document",
        word: "Word document",
        excel: "Spreadsheet",
        ppt: "Presentation",
        image: "Image",
        video: "Video",
        audio: "Audio",
        zip: "Archive",
        code: "Code file",
        text: "Text document",
        generic: "File",
        folder: "Folder"
    };

    function extensionOf(name) {
        var parts = String(name || "").split(".");
        return parts.length > 1 ? parts.pop().toLowerCase() : "";
    }

    /** Resolve a file to one of the design system's type buckets. */
    function fileKind(name, mime) {
        var byExt = EXT_MAP[extensionOf(name)];
        if (byExt) { return byExt; }

        var type = String(mime || "");
        if (type.indexOf("image/") === 0) { return "image"; }
        if (type.indexOf("video/") === 0) { return "video"; }
        if (type.indexOf("audio/") === 0) { return "audio"; }
        if (type.indexOf("text/") === 0) { return "text"; }
        if (type.indexOf("pdf") !== -1) { return "pdf"; }
        return "generic";
    }

    function typeLabel(name, mime) {
        return TYPE_LABEL[fileKind(name, mime)] || "File";
    }

    /**
     * The single file/folder glyph used everywhere: cards, rows, drawers,
     * search results and the public share page.
     */
    function typeChip(name, mime, size) {
        var kind = name === null ? "folder" : fileKind(name, mime);
        var node = el("span", "ftype ftype-" + (size || "md"));
        node.dataset.type = kind;
        node.appendChild(icon(TYPE_ICON[kind] || TYPE_ICON.generic));
        return node;
    }

    function folderChip(size) {
        return typeChip(null, null, size);
    }


    /* ---------------------------------------------------------------------
       Toasts
       ------------------------------------------------------------------ */

    var TOAST_ICON = {
        success: "check-circle-fill",
        error: "exclamation-octagon-fill",
        warning: "exclamation-triangle-fill",
        info: "info-circle-fill"
    };

    function toastHost() {
        var host = document.getElementById("toastHost");
        if (!host) {
            host = el("div", "toast-host");
            host.id = "toastHost";
            host.setAttribute("role", "status");
            host.setAttribute("aria-live", "polite");
            document.body.appendChild(host);
        }
        return host;
    }

    function toast(message, kind, timeout) {
        kind = kind || "info";

        var node = el("div", "app-toast is-" + kind);
        node.appendChild(icon(TOAST_ICON[kind] || TOAST_ICON.info));
        node.appendChild(el("span", null, message));

        var close = el("button", "t-close");
        close.type = "button";
        close.setAttribute("aria-label", "Dismiss notification");
        close.innerHTML = "&times;";
        close.addEventListener("click", function () { dismiss(); });
        node.appendChild(close);

        toastHost().appendChild(node);
        requestAnimationFrame(function () { node.classList.add("show"); });

        var timer = setTimeout(dismiss, timeout || 4000);

        function dismiss() {
            clearTimeout(timer);
            node.classList.remove("show");
            setTimeout(function () { node.remove(); }, 220);
        }

        return dismiss;
    }

    /** Turns an API error into a toast, and bounces to login on 401. */
    function reportError(err) {
        var message = (err && err.message) || "Something went wrong";
        toast(message, "error", 5000);

        if (err && err.status === 401) {
            setTimeout(function () { location.href = "login.html"; }, 900);
        }
    }


    /* ---------------------------------------------------------------------
       Confirmation dialog (promise based, reusable)
       ------------------------------------------------------------------ */

    function confirmDialog(options) {
        options = options || {};

        return new Promise(function (resolve) {
            var host = el("div", "modal fade" + (options.danger ? " modal-danger" : ""));
            host.tabIndex = -1;
            host.setAttribute("aria-modal", "true");
            host.setAttribute("role", "dialog");

            var dialog = el("div", "modal-dialog modal-dialog-centered");
            var content = el("div", "modal-content");

            var body = el("div", "modal-body");
            if (options.danger) {
                var badge = el("div", "modal-icon");
                badge.appendChild(icon(options.icon || "exclamation-triangle-fill"));
                body.appendChild(badge);
            }

            var heading = el("h2", "section-title", options.title || "Are you sure?");
            heading.id = "confirmTitle" + Date.now();
            body.appendChild(heading);
            host.setAttribute("aria-labelledby", heading.id);

            if (options.message) {
                var text = el("p", "text-dim", options.message);
                text.style.marginTop = "6px";
                body.appendChild(text);
            }

            var footer = el("div", "modal-footer");

            var cancel = el("button", "btn-app-ghost", options.cancelText || "Cancel");
            cancel.type = "button";
            cancel.setAttribute("data-bs-dismiss", "modal");

            var accept = el(
                "button",
                options.danger ? "btn-app-danger" : "btn-app-primary",
                options.confirmText || "Confirm"
            );
            accept.type = "button";

            footer.appendChild(cancel);
            footer.appendChild(accept);

            content.appendChild(body);
            content.appendChild(footer);
            dialog.appendChild(content);
            host.appendChild(dialog);
            document.body.appendChild(host);

            var modal = new bootstrap.Modal(host);
            var answered = false;

            accept.addEventListener("click", function () {
                answered = true;
                modal.hide();
                resolve(true);
            });

            host.addEventListener("hidden.bs.modal", function () {
                host.remove();
                if (!answered) { resolve(false); }
            });

            modal.show();
            setTimeout(function () { accept.focus(); }, 180);
        });
    }

    /** Small single-field prompt, replacing window.prompt. */
    function promptDialog(options) {
        options = options || {};

        return new Promise(function (resolve) {
            var host = el("div", "modal fade");
            host.tabIndex = -1;

            var dialog = el("div", "modal-dialog modal-dialog-centered");
            var content = el("div", "modal-content");

            var form = document.createElement("form");
            form.noValidate = true;

            var header = el("div", "modal-header");
            header.appendChild(el("h2", "modal-title", options.title || "Enter a value"));
            var x = el("button", "btn-close");
            x.type = "button";
            x.setAttribute("data-bs-dismiss", "modal");
            x.setAttribute("aria-label", "Close");
            header.appendChild(x);

            var body = el("div", "modal-body");
            var field = el("div", "field");

            var labelId = "promptInput" + Date.now();
            var label = el("label", null, options.label || "Name");
            label.htmlFor = labelId;

            var input = document.createElement("input");
            input.type = "text";
            input.id = labelId;
            input.value = options.value || "";
            input.placeholder = options.placeholder || "";
            input.required = true;
            input.maxLength = 180;

            field.appendChild(label);
            field.appendChild(input);
            body.appendChild(field);

            var footer = el("div", "modal-footer");
            var cancel = el("button", "btn-app-ghost", "Cancel");
            cancel.type = "button";
            cancel.setAttribute("data-bs-dismiss", "modal");
            var accept = el("button", "btn-app-primary", options.confirmText || "Save");
            accept.type = "submit";
            footer.appendChild(cancel);
            footer.appendChild(accept);

            form.appendChild(header);
            form.appendChild(body);
            form.appendChild(footer);
            content.appendChild(form);
            dialog.appendChild(content);
            host.appendChild(dialog);
            document.body.appendChild(host);

            var modal = new bootstrap.Modal(host);
            var value = null;

            form.addEventListener("submit", function (e) {
                e.preventDefault();
                var trimmed = input.value.trim();
                if (!trimmed) {
                    input.focus();
                    return;
                }
                value = trimmed;
                modal.hide();
            });

            host.addEventListener("hidden.bs.modal", function () {
                host.remove();
                resolve(value);
            });

            host.addEventListener("shown.bs.modal", function () {
                input.focus();
                input.select();
            });

            modal.show();
        });
    }


    /* ---------------------------------------------------------------------
       Empty states + skeletons
       ------------------------------------------------------------------ */

    function emptyState(options) {
        options = options || {};

        var node = el("div", "empty-state");

        var badge = el("div", "es-icon");
        badge.appendChild(icon(options.icon || "inbox"));
        node.appendChild(badge);

        node.appendChild(el("h3", null, options.title || "Nothing here yet"));

        if (options.message) {
            node.appendChild(el("p", null, options.message));
        }

        if (options.actionLabel && options.onAction) {
            var button = el("button", "btn-app-primary");
            button.type = "button";
            if (options.actionIcon) { button.appendChild(icon(options.actionIcon)); }
            button.appendChild(el("span", null, options.actionLabel));
            button.addEventListener("click", options.onAction);
            node.appendChild(button);
        }

        return node;
    }

    function skeletonCards(count, host) {
        var box = frag();
        for (var i = 0; i < (count || 6); i += 1) {
            var card = el("div", "skeleton-card");

            var chip = el("div", "skeleton sk-chip");
            chip.style.width = "40px";
            chip.style.height = "40px";
            chip.style.marginBottom = "14px";
            card.appendChild(chip);

            var l1 = el("div", "skeleton sk-line");
            l1.style.width = "78%";
            var l2 = el("div", "skeleton sk-line");
            l2.style.width = "48%";

            card.appendChild(l1);
            card.appendChild(l2);
            box.appendChild(card);
        }
        if (host) { fill(host, []); host.appendChild(box); }
        return box;
    }

    function skeletonRows(count, host) {
        var box = frag();
        for (var i = 0; i < (count || 5); i += 1) {
            var row = el("div", "skeleton-row");

            var chip = el("div", "skeleton sk-chip");
            chip.style.width = "32px";
            chip.style.height = "32px";
            row.appendChild(chip);

            var stack = el("div");
            stack.style.flex = "1";

            var l1 = el("div", "skeleton sk-line");
            l1.style.width = (45 + (i % 3) * 12) + "%";
            var l2 = el("div", "skeleton sk-line");
            l2.style.width = "26%";
            l2.style.height = "9px";

            stack.appendChild(l1);
            stack.appendChild(l2);
            row.appendChild(stack);
            box.appendChild(row);
        }
        if (host) { fill(host, []); host.appendChild(box); }
        return box;
    }


    /* ---------------------------------------------------------------------
       Misc
       ------------------------------------------------------------------ */

    function debounce(fn, wait) {
        var timer = null;
        return function () {
            var args = arguments;
            var self = this;
            clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(self, args); }, wait || 250);
        };
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        // Fallback for non-secure origins.
        return new Promise(function (resolve, reject) {
            var area = document.createElement("textarea");
            area.value = text;
            area.setAttribute("readonly", "");
            area.style.position = "fixed";
            area.style.opacity = "0";
            document.body.appendChild(area);
            area.select();
            try {
                document.execCommand("copy");
                resolve();
            } catch (e) {
                reject(e);
            } finally {
                area.remove();
            }
        });
    }

    function greeting() {
        var hour = new Date().getHours();
        if (hour < 12) { return "Good morning"; }
        if (hour < 18) { return "Good afternoon"; }
        return "Good evening";
    }

    global.UI = {
        el: el,
        icon: icon,
        clear: clear,
        fill: fill,
        frag: frag,
        show: show,

        formatSize: formatSize,
        formatMB: formatMB,
        formatDate: formatDate,
        formatDateTime: formatDateTime,
        formatTime: formatTime,
        timeAgo: timeAgo,
        toDate: toDate,
        dayBucket: dayBucket,
        BUCKET_ORDER: BUCKET_ORDER,

        fileKind: fileKind,
        typeLabel: typeLabel,
        typeChip: typeChip,
        folderChip: folderChip,
        extensionOf: extensionOf,

        toast: toast,
        reportError: reportError,
        confirmDialog: confirmDialog,
        promptDialog: promptDialog,

        emptyState: emptyState,
        skeletonCards: skeletonCards,
        skeletonRows: skeletonRows,

        debounce: debounce,
        copyText: copyText,
        greeting: greeting
    };
}(window));
