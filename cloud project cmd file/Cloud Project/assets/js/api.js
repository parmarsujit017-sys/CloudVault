/* ======================================================
   Cloud API CLIENT
   Shared by Login, Register, Reset, Dashboard and Share.
   Talks to the FastAPI backend - there is no mock data.
   ====================================================== */

(function (global) {
    "use strict";

    // The frontend is normally served by the backend itself, so a relative
    // origin is correct. Override with window.Cloud_API_BASE when the
    // pages are opened from a different port (e.g. Live Server on :5500).
    var API_BASE =
        global.Cloud_API_BASE ||
        (location.protocol === "file:" || location.port === "5500" || location.port === "5501"
            ? "http://127.0.0.1:8000"
            : "");

    var TOKEN_KEY = "Cloud_token";
    var USER_KEY = "Cloud_user";


    // --------------------------------------------------
    // Session storage
    // --------------------------------------------------

    function getToken() {
        try {
            return localStorage.getItem(TOKEN_KEY);
        } catch (e) {
            return null;
        }
    }

    function setSession(token, user) {
        try {
            localStorage.setItem(TOKEN_KEY, token);
            localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
        } catch (e) { /* private mode */ }
    }

    function getCachedUser() {
        try {
            return JSON.parse(localStorage.getItem(USER_KEY) || "null");
        } catch (e) {
            return null;
        }
    }

    function clearSession() {
        try {
            localStorage.removeItem(TOKEN_KEY);
            localStorage.removeItem(USER_KEY);
        } catch (e) { /* ignore */ }
    }


    // --------------------------------------------------
    // Core request helper
    // --------------------------------------------------

    function ApiError(message, status, body) {
        this.name = "ApiError";
        this.message = message;
        this.status = status;
        this.body = body;
    }
    ApiError.prototype = Object.create(Error.prototype);

    async function request(path, options) {
        options = options || {};

        var headers = Object.assign({}, options.headers || {});
        var token = getToken();

        if (token && !options.anonymous) {
            headers.Authorization = "Bearer " + token;
        }

        var body = options.body;
        if (body !== undefined && !(body instanceof FormData)) {
            headers["Content-Type"] = "application/json";
            body = JSON.stringify(body);
        }

        var response;
        try {
            response = await fetch(API_BASE + path, {
                method: options.method || "GET",
                headers: headers,
                body: body
            });
        } catch (networkError) {
            throw new ApiError(
                "Cannot reach the server. Is the backend running on port 8000?",
                0,
                null
            );
        }

        if (response.status === 204) {
            return null;
        }

        var contentType = response.headers.get("content-type") || "";
        var payload = contentType.indexOf("application/json") !== -1
            ? await response.json().catch(function () { return null; })
            : await response.text();

        if (!response.ok) {
            var message = (payload && payload.message) ||
                (typeof payload === "string" && payload) ||
                ("Request failed (" + response.status + ")");

            // The token is gone or expired: drop it so guards redirect cleanly.
            if (response.status === 401 && !options.anonymous) {
                clearSession();
            }

            throw new ApiError(message, response.status, payload);
        }

        return payload;
    }


    function buildQuery(params) {
        if (!params) { return ""; }
        var parts = [];
        Object.keys(params).forEach(function (key) {
            var value = params[key];
            if (value !== null && value !== undefined && value !== "") {
                parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
            }
        });
        return parts.length ? ("?" + parts.join("&")) : "";
    }


    /**
     * Uploads with real progress. XMLHttpRequest is used instead of fetch
     * because fetch still cannot report upload progress.
     */
    function uploadFiles(fileList, folderId, onProgress) {
        return new Promise(function (resolve, reject) {
            var form = new FormData();
            Array.prototype.forEach.call(fileList, function (file) {
                form.append("files", file, file.name);
            });

            var url = API_BASE + "/api/files/upload";
            if (folderId !== null && folderId !== undefined) {
                url += "?folder_id=" + folderId;
            }

            var xhr = new XMLHttpRequest();
            xhr.open("POST", url, true);

            var token = getToken();
            if (token) {
                xhr.setRequestHeader("Authorization", "Bearer " + token);
            }

            if (onProgress) {
                xhr.upload.onprogress = function (event) {
                    if (event.lengthComputable) {
                        onProgress(Math.round((event.loaded / event.total) * 100));
                    }
                };
            }

            xhr.onload = function () {
                var payload;
                try {
                    payload = JSON.parse(xhr.responseText);
                } catch (e) {
                    payload = null;
                }

                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(payload);
                } else {
                    if (xhr.status === 401) { clearSession(); }
                    reject(new ApiError(
                        (payload && (payload.message || payload.detail)) || "Upload failed",
                        xhr.status,
                        payload
                    ));
                }
            };

            xhr.onerror = function () {
                reject(new ApiError("Network error during upload", 0, null));
            };

            xhr.send(form);
        });
    }



    /**
     * Downloads through fetch so the Authorization header is sent - a plain
     * navigation to the download URL cannot carry a bearer token and would be
     * rejected with 401. The bytes come back as a blob and are handed to the
     * browser as a normal file save.
     */
    async function fetchFileBlob(path) {
        var headers = {};
        var token = getToken();
        if (token) { headers.Authorization = "Bearer " + token; }

        var response;
        try {
            response = await fetch(API_BASE + path, { headers: headers });
        } catch (e) {
            throw new ApiError("Cannot reach the server", 0, null);
        }

        if (!response.ok) {
            var message = "Download failed";
            try {
                var payload = await response.json();
                if (payload && payload.message) { message = payload.message; }
            } catch (e) { /* not JSON */ }

            if (response.status === 401) { clearSession(); }
            throw new ApiError(message, response.status, null);
        }

        return await response.blob();
    }

    /** Hands a blob to the browser as a normal "Save as" download. */
    function saveBlob(blob, filename) {
        var url = URL.createObjectURL(blob);

        var link = document.createElement("a");
        link.href = url;
        link.download = filename || "download";
        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    }

    async function saveFile(fileId, filename) {
        saveBlob(await fetchFileBlob("/api/files/" + fileId + "/download"), filename);
    }

    /**
     * Folders download as a .zip built by the server. It goes through fetch for
     * the same reason single files do: a plain link cannot carry the token.
     */
    async function saveFolder(folderId, folderName) {
        var blob = await fetchFileBlob("/api/folders/" + folderId + "/download");
        saveBlob(blob, (folderName || "folder") + ".zip");
    }

    /**
     * Opens a file in a new tab. The tab is opened synchronously (before the
     * await) so popup blockers do not swallow it.
     */
    async function openFile(fileId) {
        var tab = window.open("", "_blank");

        try {
            var blob = await fetchFileBlob("/api/files/" + fileId + "/download?inline=true");
            var url = URL.createObjectURL(blob);

            if (tab) {
                tab.location.href = url;
            } else {
                window.location.href = url;
            }

            setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
        } catch (err) {
            if (tab) { tab.close(); }
            throw err;
        }
    }


    // --------------------------------------------------
    // Endpoints
    // --------------------------------------------------

    var api = {
        base: API_BASE,
        ApiError: ApiError,
        request: request,
        getToken: getToken,
        getCachedUser: getCachedUser,
        setSession: setSession,
        clearSession: clearSession,

        auth: {
            register: function (data) {
                return request("/api/auth/register", { method: "POST", body: data, anonymous: true });
            },
            login: function (username, password) {
                return request("/api/auth/login", {
                    method: "POST",
                    body: { username: username, password: password },
                    anonymous: true
                });
            },
            logout: function () {
                return request("/api/auth/logout", { method: "POST" });
            },
            me: function () {
                return request("/api/auth/me");
            },
            resetPassword: function (data) {
                return request("/api/auth/reset-password", {
                    method: "POST", body: data, anonymous: true
                });
            }
        },

        users: {
            updateProfile: function (data) {
                return request("/api/users/me", { method: "PUT", body: data });
            },
            changePassword: function (data) {
                return request("/api/users/me/password", { method: "PUT", body: data });
            },
            uploadAvatar: function (file) {
                var form = new FormData();
                form.append("file", file);
                return request("/api/users/me/avatar", { method: "POST", body: form });
            },
            avatarUrl: function () {
                return API_BASE + "/api/users/me/avatar";
            },
            search: function (q) {
                return request("/api/users/search?q=" + encodeURIComponent(q));
            }
        },

        folders: {
            create: function (name, parent) {
                return request("/api/folders", {
                    method: "POST",
                    body: {
                        folder_name: name,
                        parent_folder: parent === undefined ? null : parent
                    }
                });
            },
            list: function (parent) {
                var q = (parent === null || parent === undefined) ? "" : ("?parent=" + parent);
                return request("/api/folders" + q);
            },
            listAll: function () {
                return request("/api/folders?all=true");
            },
            open: function (id) {
                return request("/api/folders/" + id);
            },
            update: function (id, data) {
                return request("/api/folders/" + id, { method: "PUT", body: data });
            },
            remove: function (id) {
                return request("/api/folders/" + id, { method: "DELETE" });
            },
            /**
             * Creates a whole directory tree in one round trip and returns
             * { created, folders: { "a/b": id } }. Used by folder uploads so the
             * structure exists before the first file is sent.
             */
            tree: function (parentId, paths) {
                return request("/api/folders/tree", {
                    method: "POST",
                    body: {
                        parent_folder: parentId === undefined ? null : parentId,
                        paths: paths
                    }
                });
            },
            copy: function (id, parentId) {
                return request("/api/folders/" + id + "/copy", {
                    method: "POST",
                    body: { parent_folder: parentId === undefined ? null : parentId }
                });
            },
            /** action: move | copy | delete */
            batch: function (action, folderIds, parentId) {
                return request("/api/folders/batch", {
                    method: "POST",
                    body: {
                        action: action,
                        folder_ids: folderIds,
                        parent_folder: parentId === undefined ? null : parentId
                    }
                });
            },
            download: saveFolder
        },

        files: {
            create: function (data) {
                return request("/api/files", { method: "POST", body: data });
            },
            update: function (id, data) {
                return request("/api/files/" + id, { method: "PUT", body: data });
            },
            list: function (params) {
                return request("/api/files" + buildQuery(params));
            },
            get: function (id) {
                return request("/api/files/" + id);
            },
            // NOTE: this URL needs an Authorization header, so it cannot be
            // used as a plain link target. Use save()/open() instead.
            downloadUrl: function (id, inline) {
                return API_BASE + "/api/files/" + id + "/download" + (inline ? "?inline=true" : "");
            },
            save: saveFile,
            open: openFile,
            rename: function (id, name) {
                return request("/api/files/" + id + "/rename", {
                    method: "PUT", body: { original_name: name }
                });
            },
            move: function (id, folderId) {
                return request("/api/files/" + id + "/move", {
                    method: "PUT", body: { folder_id: folderId }
                });
            },
            star: function (id, value) {
                return request("/api/files/" + id + "/star", {
                    method: "PUT", body: { is_starred: value }
                });
            },
            copy: function (id, folderId) {
                return request("/api/files/" + id + "/copy", {
                    method: "POST",
                    body: { folder_id: folderId === undefined ? null : folderId }
                });
            },
            /** action: move | copy | trash | star | unstar */
            batch: function (action, fileIds, folderId) {
                return request("/api/files/batch", {
                    method: "POST",
                    body: {
                        action: action,
                        file_ids: fileIds,
                        folder_id: folderId === undefined ? null : folderId
                    }
                });
            },
            remove: function (id) {
                return request("/api/files/" + id, { method: "DELETE" });
            },
            upload: uploadFiles
        },

        trash: {
            list: function () { return request("/api/trash"); },
            restore: function (fileId) {
                return request("/api/trash/" + fileId + "/restore", { method: "POST" });
            },
            purge: function (fileId) {
                return request("/api/trash/" + fileId, { method: "DELETE" });
            },
            empty: function () { return request("/api/trash", { method: "DELETE" }); }
        },

        shares: {
            create: function (data) {
                return request("/api/shares", { method: "POST", body: data });
            },
            createFolder: function (data) {
                return request("/api/shares/folder", { method: "POST", body: data });
            },
            revokeFolder: function (id) {
                return request("/api/shares/folder/" + id, { method: "DELETE" });
            },
            received: function (q) {
                return request("/api/shares/received" + (q ? ("?q=" + encodeURIComponent(q)) : ""));
            },
            sent: function () { return request("/api/shares/sent"); },
            revoke: function (id) {
                return request("/api/shares/" + id, { method: "DELETE" });
            },
            publicInfo: function (token) {
                return request("/api/share/" + encodeURIComponent(token), { anonymous: true });
            },
            verify: function (token, password) {
                return request("/api/share/" + encodeURIComponent(token) + "/verify", {
                    method: "POST", body: { password: password }, anonymous: true
                });
            },
            publicDownloadUrl: function (token, password, fileId) {
                return API_BASE + "/api/share/" + encodeURIComponent(token) + "/download" +
                    buildQuery({ password: password, file_id: fileId });
            },
            /** One level inside a publicly shared folder. */
            publicList: function (token, path, password) {
                return request(
                    "/api/share/" + encodeURIComponent(token) + "/list" +
                        buildQuery({ path: path, password: password }),
                    { anonymous: true }
                );
            },
            publicZipUrl: function (token, path, password) {
                return API_BASE + "/api/share/" + encodeURIComponent(token) + "/download-all" +
                    buildQuery({ path: path, password: password });
            }
        },

        storage: {
            get: function () { return request("/api/storage"); }
        },

        plans: {
            /** The catalogue a signed-in user is allowed to see. */
            list: function () { return request("/api/plans"); },
            mine: function () { return request("/api/plans/me"); },
            history: function () { return request("/api/plans/me/history"); }
        },

        /**
         * Administration. Every one of these is admin-only server-side, so a
         * normal account gets a 403 rather than a partial answer.
         */
        admin: {
            stats: function () { return request("/api/admin/stats"); },

            users: function (params) {
                return request("/api/admin/users" + buildQuery(params));
            },
            user: function (id) { return request("/api/admin/users/" + id); },
            updateUser: function (id, data) {
                return request("/api/admin/users/" + id, { method: "PUT", body: data });
            },
            deleteUser: function (id) {
                return request("/api/admin/users/" + id, { method: "DELETE" });
            },

            assignPlan: function (id, data) {
                return request("/api/admin/users/" + id + "/subscription", {
                    method: "POST", body: data
                });
            },
            revokePlan: function (id) {
                return request("/api/admin/users/" + id + "/subscription", { method: "DELETE" });
            },

            plans: function () { return request("/api/admin/plans"); },
            createPlan: function (data) {
                return request("/api/admin/plans", { method: "POST", body: data });
            },
            updatePlan: function (id, data) {
                return request("/api/admin/plans/" + id, { method: "PUT", body: data });
            },
            deletePlan: function (id) {
                return request("/api/admin/plans/" + id, { method: "DELETE" });
            }
        },

        activity: {
            list: function (limit) {
                return request("/api/activity?limit=" + (limit || 25));
            }
        },

        settings: {
            get: function () { return request("/api/settings"); },
            update: function (data) {
                return request("/api/settings", { method: "PUT", body: data });
            }
        },

        dashboard: {
            get: function () { return request("/api/dashboard"); }
        },

        search: function (q) {
            return request("/api/search?q=" + encodeURIComponent(q));
        }
    };

    global.API = api;
}(window));
