/* =========================================================================
   FLOATING ACTION MENU
   Anchored menus rendered at body level so a card, table cell or scroll
   container can never clip them. Keyboard accessible: arrows move, Home/End
   jump, Escape closes and returns focus to the trigger.
   ========================================================================= */

(function (global) {
    "use strict";

    var el = UI.el;
    var icon = UI.icon;

    var open = null;   // { node, anchor, onClose }

    function close() {
        if (!open) { return; }

        var previous = open;
        open = null;

        previous.node.remove();
        previous.anchor.setAttribute("aria-expanded", "false");

        var actions = previous.anchor.closest(".row-actions");
        if (actions) { actions.classList.remove("show"); }

        if (previous.restoreFocus) { previous.anchor.focus(); }
    }

    function position(node, anchor) {
        var rect = anchor.getBoundingClientRect();
        var width = node.offsetWidth;
        var height = node.offsetHeight;
        var gap = 6;

        // Prefer below-right of the trigger, flip when there is no room.
        var left = rect.right - width;
        if (left < 8) { left = Math.min(rect.left, window.innerWidth - width - 8); }
        left = Math.max(8, left);

        var top = rect.bottom + gap;
        if (top + height > window.innerHeight - 8) {
            top = rect.top - height - gap;
        }
        top = Math.max(8, top);

        node.style.left = Math.round(left) + "px";
        node.style.top = Math.round(top) + "px";
    }

    /**
     * items: [{ text, icon, danger, disabled, onSelect } | { divider: true }
     *         | { header: "Label" }]
     */
    function openMenu(anchor, items) {
        if (open && open.anchor === anchor) {
            close();
            return;
        }
        close();

        var node = el("div", "dropdown-menu app-menu show");
        node.style.position = "fixed";
        node.style.margin = "0";
        node.style.zIndex = "2600";
        node.setAttribute("role", "menu");

        var buttons = [];

        items.forEach(function (item) {
            if (!item) { return; }

            if (item.divider) {
                node.appendChild(el("hr", "dropdown-divider"));
                return;
            }

            if (item.header) {
                node.appendChild(el("div", "dropdown-header", item.header));
                return;
            }

            var button = el("button", "dropdown-item" + (item.danger ? " is-danger" : ""));
            button.type = "button";
            button.setAttribute("role", "menuitem");

            if (item.icon) { button.appendChild(icon(item.icon)); }
            button.appendChild(el("span", null, item.text));

            if (item.disabled) {
                button.disabled = true;
                button.setAttribute("aria-disabled", "true");
            } else {
                button.addEventListener("click", function () {
                    close();
                    item.onSelect();
                });
                buttons.push(button);
            }

            node.appendChild(button);
        });

        document.body.appendChild(node);
        position(node, anchor);

        anchor.setAttribute("aria-expanded", "true");
        var actions = anchor.closest(".row-actions");
        if (actions) { actions.classList.add("show"); }

        open = { node: node, anchor: anchor, restoreFocus: false };

        var cursor = -1;

        function move(delta) {
            if (!buttons.length) { return; }
            cursor = (cursor + delta + buttons.length) % buttons.length;
            buttons[cursor].focus();
        }

        node.addEventListener("keydown", function (e) {
            if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
            else if (e.key === "Home") { e.preventDefault(); cursor = -1; move(1); }
            else if (e.key === "End") { e.preventDefault(); cursor = 0; move(-1); }
            else if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                if (open) { open.restoreFocus = true; }
                close();
            } else if (e.key === "Tab") {
                close();
            }
        });

        // Opening by keyboard should land on the first entry.
        if (anchor.dataset.viaKeyboard === "1") {
            delete anchor.dataset.viaKeyboard;
            setTimeout(function () { move(1); }, 0);
        }

        return node;
    }

    // Global dismissal
    document.addEventListener("mousedown", function (e) {
        if (open && !open.node.contains(e.target) && !open.anchor.contains(e.target)) {
            close();
        }
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && open) {
            open.restoreFocus = true;
            close();
        }
    });

    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);

    /** Builds the standard three-dot trigger wired to a menu factory. */
    function dotTrigger(label, itemsFactory) {
        var wrap = el("div", "row-actions");

        var button = el("button", "dot-btn");
        button.type = "button";
        button.setAttribute("aria-haspopup", "true");
        button.setAttribute("aria-expanded", "false");
        button.setAttribute("aria-label", label || "More actions");
        button.appendChild(icon("three-dots-vertical"));

        button.addEventListener("click", function (e) {
            e.stopPropagation();
            e.preventDefault();
            openMenu(button, itemsFactory());
        });

        button.addEventListener("keydown", function (e) {
            if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
                button.dataset.viaKeyboard = "1";
            }
        });

        wrap.appendChild(button);
        return wrap;
    }

    global.Menu = {
        open: openMenu,
        close: close,
        dotTrigger: dotTrigger
    };
}(window));
