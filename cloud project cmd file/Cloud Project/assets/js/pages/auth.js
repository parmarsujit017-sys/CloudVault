/* =========================================================================
   AUTH PAGES
   One controller for sign in, register and password reset. Each form talks
   to the real API and reports the server's own message on failure.
   ========================================================================= */

(function () {
    "use strict";

    var page = document.body.dataset.page;


    /* ---------------------------------------------------------------------
       Shared behaviour
       ------------------------------------------------------------------ */

    // Show / hide password
    document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
        button.addEventListener("click", function () {
            var input = document.getElementById(button.dataset.togglePassword);
            if (!input) { return; }

            var reveal = input.type === "password";
            input.type = reveal ? "text" : "password";
            button.setAttribute("aria-label", reveal ? "Hide password" : "Show password");
            UI.fill(button, UI.icon(reveal ? "eye-slash" : "eye"));
            input.focus();
        });
    });

    function fieldError(id, message) {
        var node = document.getElementById(id + "Error");
        var input = document.getElementById(id);

        if (node) {
            node.textContent = message || "";
            node.classList.toggle("is-hidden", !message);
        }
        if (input) {
            input.closest(".field").classList.toggle("has-error", Boolean(message));
            input.setAttribute("aria-invalid", message ? "true" : "false");
        }
    }

    function clearErrors(form) {
        form.querySelectorAll(".error-text").forEach(function (node) {
            node.textContent = "";
            node.classList.add("is-hidden");
        });
        form.querySelectorAll(".field").forEach(function (node) {
            node.classList.remove("has-error");
        });
    }

    function busy(button, isBusy, busyText) {
        button.disabled = isBusy;
        if (isBusy) {
            button.dataset.idleText = button.textContent;
            button.textContent = busyText;
        } else if (button.dataset.idleText) {
            button.textContent = button.dataset.idleText;
        }
    }

    /** Where to go after a successful sign-in. Only same-page names are honoured. */
    function nextPage() {
        var requested = new URLSearchParams(location.search).get("next") || "";
        return /^[a-z0-9_-]+\.html$/i.test(requested) ? requested : "dashboard.html";
    }

    /** If a valid session already exists, skip the form. */
    async function skipIfSignedIn() {
        if (!API.getToken()) { return; }
        try {
            await API.auth.me();
            location.replace(nextPage());
        } catch (e) {
            API.clearSession();
        }
    }


    /* ---------------------------------------------------------------------
       Sign in
       ------------------------------------------------------------------ */

    if (page === "login") {
        skipIfSignedIn();

        var loginForm = document.getElementById("loginForm");

        loginForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            clearErrors(loginForm);

            var identifier = document.getElementById("identifier").value.trim();
            var password = document.getElementById("password").value;
            var submit = document.getElementById("loginSubmit");

            if (!identifier) {
                fieldError("identifier", "Enter your username or email");
                return;
            }
            if (!password) {
                fieldError("password", "Enter your password");
                return;
            }

            busy(submit, true, "Signing in…");

            try {
                var result = await API.auth.login(identifier, password);
                API.setSession(result.access_token, result.user);
                location.href = nextPage();
            } catch (err) {
                busy(submit, false);

                // 401 is a wrong credential; 403 is a disabled account.
                if (err.status === 401) {
                    fieldError("password", err.message);
                    document.getElementById("password").focus();
                } else {
                    UI.toast(err.message, "error", 5000);
                }
            }
        });
    }


    /* ---------------------------------------------------------------------
       Register
       ------------------------------------------------------------------ */

    if (page === "register") {
        skipIfSignedIn();

        var registerForm = document.getElementById("registerForm");
        var pwInput = document.getElementById("password");
        var strength = document.getElementById("pwStrength");
        var strengthText = document.getElementById("pwStrengthText");

        var STRENGTH_LABEL = [
            "At least 6 characters.",
            "Weak password.",
            "Fair password.",
            "Good password.",
            "Strong password."
        ];

        function scorePassword(value) {
            if (!value) { return 0; }
            var score = 0;
            if (value.length >= 6) { score += 1; }
            if (value.length >= 10) { score += 1; }
            if (/[A-Z]/.test(value) && /[a-z]/.test(value)) { score += 1; }
            if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) { score += 1; }
            return Math.min(score, 4);
        }

        pwInput.addEventListener("input", function () {
            var score = scorePassword(pwInput.value);
            strength.dataset.score = String(score);
            strengthText.textContent = STRENGTH_LABEL[score];
        });

        registerForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            clearErrors(registerForm);

            var fullname = document.getElementById("fullname").value.trim();
            var username = document.getElementById("username").value.trim();
            var email = document.getElementById("email").value.trim();
            var password = pwInput.value;
            var confirm = document.getElementById("confirm").value;
            var submit = document.getElementById("registerSubmit");

            var valid = true;

            if (fullname.length < 2) {
                fieldError("fullname", "Enter your full name");
                valid = false;
            }
            if (!/^[A-Za-z0-9._-]{3,40}$/.test(username)) {
                fieldError("username", "3–40 characters: letters, numbers, dots, dashes, underscores");
                valid = false;
            }
            if (!/^\S+@\S+\.\S+$/.test(email)) {
                fieldError("email", "Enter a valid email address");
                valid = false;
            }
            if (password.length < 6) {
                fieldError("password", "Password must be at least 6 characters");
                valid = false;
            }
            if (password !== confirm) {
                fieldError("confirm", "Passwords do not match");
                valid = false;
            }

            if (!valid) {
                registerForm.querySelector(".has-error input").focus();
                return;
            }

            busy(submit, true, "Creating account…");

            try {
                var result = await API.auth.register({
                    fullname: fullname,
                    username: username,
                    email: email,
                    password: password
                });

                // Registration returns a token, so go straight in.
                API.setSession(result.access_token, result.user);
                location.href = "dashboard.html";
            } catch (err) {
                busy(submit, false);

                if (err.status === 409) {
                    // The server says which one collided.
                    var target = /email/i.test(err.message) ? "email" : "username";
                    fieldError(target, err.message);
                    document.getElementById(target).focus();
                } else {
                    UI.toast(err.message, "error", 5000);
                }
            }
        });
    }


    /* ---------------------------------------------------------------------
       Reset password
       ------------------------------------------------------------------ */

    if (page === "reset") {
        var resetForm = document.getElementById("resetForm");

        resetForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            clearErrors(resetForm);

            var username = document.getElementById("username").value.trim();
            var email = document.getElementById("email").value.trim();
            var password = document.getElementById("password").value;
            var confirm = document.getElementById("confirm").value;
            var submit = document.getElementById("resetSubmit");

            if (password.length < 6) {
                UI.toast("Password must be at least 6 characters", "error");
                return;
            }
            if (password !== confirm) {
                fieldError("confirm", "Passwords do not match");
                return;
            }

            busy(submit, true, "Resetting…");

            try {
                await API.auth.resetPassword({
                    username: username,
                    email: email,
                    new_password: password
                });

                UI.toast("Password updated. Redirecting to sign in…", "success");
                setTimeout(function () { location.href = "login.html"; }, 1000);
            } catch (err) {
                busy(submit, false);
                UI.toast(err.message, "error", 5000);
            }
        });
    }
}());
