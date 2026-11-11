// ======================================================
// Cloud DASHBOARD JAVASCRIPT
// ======================================================


// ======================================================
// 1. GET ELEMENTS
// ======================================================

const newBtn = document.getElementById("newBtn");
const dropdown = document.getElementById("dropdown");

const profile = document.getElementById("profile");
const headerProfileImg =
    document.getElementById("headerProfileImg");

const profileModal =
    document.getElementById("profileModal");

const closeProfile =
    document.getElementById("closeProfile");

const folderGrid =
    document.getElementById("folderGrid");

const fileGrid =
    document.getElementById("fileGrid");

const uploadFile =
    document.getElementById("uploadFile");

const uploadFolder =
    document.getElementById("uploadFolder");

const searchInput =
    document.getElementById("searchInput");


// ======================================================
// 2. SIDEBAR MENU
// ======================================================

const menuItems =
    document.querySelectorAll(".sidebar ul li");


menuItems.forEach(function (item) {

    item.addEventListener("click", function () {

        menuItems.forEach(function (menu) {

            menu.classList.remove("active");

        });

        this.classList.add("active");

    });

});


// ======================================================
// 3. NEW BUTTON DROPDOWN
// ======================================================

if (newBtn && dropdown) {

    newBtn.addEventListener("click", function (e) {

        e.stopPropagation();

        dropdown.classList.toggle("show");

    });


    dropdown.addEventListener("click", function (e) {

        e.stopPropagation();

    });


    document.addEventListener("click", function () {

        dropdown.classList.remove("show");

    });

}


// ======================================================
// 4. NEW FOLDER
// ======================================================

const newFolderBtn =
    document.getElementById("newFolderBtn");


if (newFolderBtn) {

    newFolderBtn.addEventListener("click", function () {

        dropdown.classList.remove("show");


        const folderName =
            prompt("Enter Folder Name");


        if (!folderName ||
            folderName.trim() === "") {

            return;

        }


        const card =
            document.createElement("div");


        card.className = "folder-card";


        card.innerHTML = `
            <i class="fa-solid fa-folder"></i>
            <span>${folderName}</span>
        `;


        card.addEventListener("click", function () {

            alert("Opening " + folderName);

        });


        if (folderGrid) {

            folderGrid.appendChild(card);

        }

    });

}


// ======================================================
// 5. UPLOAD FILE
// ======================================================

const uploadFileBtn =
    document.getElementById("uploadFileBtn");


if (uploadFileBtn) {

    uploadFileBtn.addEventListener("click", function () {

        dropdown.classList.remove("show");


        if (uploadFile) {

            uploadFile.click();

        }

    });

}


if (uploadFile) {

    uploadFile.addEventListener("change", function () {

        const files = [...this.files];


        files.forEach(function (file) {

            createFileCard(file);

        });


        this.value = "";

    });

}


// ======================================================
// 6. CREATE FILE CARD
// ======================================================

function createFileCard(file) {

    let icon = "fa-file";


    // PDF

    if (
        file.name
            .toLowerCase()
            .endsWith(".pdf")
    ) {

        icon = "fa-file-pdf";

    }


    // Word

    else if (
        file.name
            .toLowerCase()
            .endsWith(".doc") ||

        file.name
            .toLowerCase()
            .endsWith(".docx")
    ) {

        icon = "fa-file-word";

    }


    // Excel

    else if (
        file.name
            .toLowerCase()
            .endsWith(".xls") ||

        file.name
            .toLowerCase()
            .endsWith(".xlsx")
    ) {

        icon = "fa-file-excel";

    }


    // PowerPoint

    else if (
        file.name
            .toLowerCase()
            .endsWith(".ppt") ||

        file.name
            .toLowerCase()
            .endsWith(".pptx")
    ) {

        icon = "fa-file-powerpoint";

    }


    // Image

    else if (file.type.startsWith("image/")) {

        icon = "fa-file-image";

    }


    // Text

    else if (
        file.name
            .toLowerCase()
            .endsWith(".txt")
    ) {

        icon = "fa-file-lines";

    }


    // CREATE CARD

    const card =
        document.createElement("div");


    card.className = "file-card";


    card.innerHTML = `
        <i class="fa-solid ${icon}"></i>

        <h4>${file.name}</h4>

        <p>${formatFileSize(file.size)}</p>

        <button type="button">
            Open
        </button>
    `;


    const openButton =
        card.querySelector("button");


    if (openButton) {

        openButton.addEventListener(
            "click",
            function () {

                const fileURL =
                    URL.createObjectURL(file);

                window.open(
                    fileURL,
                    "_blank"
                );

            }
        );

    }


    if (fileGrid) {

        fileGrid.appendChild(card);

    }

}


// ======================================================
// 7. FORMAT FILE SIZE
// ======================================================

function formatFileSize(bytes) {

    if (bytes === 0) {

        return "0 KB";

    }


    const kb = bytes / 1024;


    if (kb < 1024) {

        return kb.toFixed(2) + " KB";

    }


    const mb = kb / 1024;


    return mb.toFixed(2) + " MB";

}


// ======================================================
// 8. UPLOAD FOLDER
// ======================================================

const uploadFolderBtn =
    document.getElementById("uploadFolderBtn");


if (uploadFolderBtn) {

    uploadFolderBtn.addEventListener(
        "click",
        function () {

            dropdown.classList.remove("show");


            if (uploadFolder) {

                uploadFolder.click();

            }

        }
    );

}


if (uploadFolder) {

    uploadFolder.addEventListener(
        "change",
        function () {

            const files = [...this.files];


            files.forEach(function (file) {

                const card =
                    document.createElement("div");


                card.className = "file-card";


                card.innerHTML = `
                    <i class="fa-solid fa-folder-open"></i>

                    <h4>
                        ${file.webkitRelativePath ||
                        file.name}
                    </h4>

                    <p>
                        ${formatFileSize(file.size)}
                    </p>

                    <button type="button">
                        Open
                    </button>
                `;


                const openButton =
                    card.querySelector("button");


                if (openButton) {

                    openButton.addEventListener(
                        "click",
                        function () {

                            const fileURL =
                                URL.createObjectURL(file);

                            window.open(
                                fileURL,
                                "_blank"
                            );

                        }
                    );

                }


                if (fileGrid) {

                    fileGrid.appendChild(card);

                }

            });


            this.value = "";

        }
    );

}


// ======================================================
// 9. SEARCH
// ======================================================

if (searchInput) {

    searchInput.addEventListener(
        "keyup",
        function () {

            const value =
                this.value
                    .toLowerCase()
                    .trim();


            // SEARCH FOLDERS

            document
                .querySelectorAll(".folder-card")
                .forEach(function (card) {

                    const text =
                        card.innerText
                            .toLowerCase();


                    if (text.includes(value)) {

                        card.style.display =
                            "flex";

                    } else {

                        card.style.display =
                            "none";

                    }

                });


            // SEARCH FILES

            document
                .querySelectorAll(".file-card")
                .forEach(function (card) {

                    const text =
                        card.innerText
                            .toLowerCase();


                    if (text.includes(value)) {

                        card.style.display =
                            "flex";

                    } else {

                        card.style.display =
                            "none";

                    }

                });

        }
    );

}


// ======================================================
// 10. PROFILE MODAL
// ======================================================


// ------------------------------------------------------
// OPEN PROFILE
// ------------------------------------------------------

function openProfileModal() {

    if (!profileModal) {

        console.error(
            "ERROR: profileModal not found!"
        );

        return;
    }

    profileModal.classList.add("show");

    document.body.style.overflow = "hidden";

}


// ------------------------------------------------------
// CLOSE PROFILE
// ------------------------------------------------------

function closeProfileModal() {

    if (!profileModal) {
        return;
    }

    profileModal.classList.remove("show");

    document.body.style.overflow = "";

}


// ------------------------------------------------------
// SIDEBAR PROFILE CLICK
// ------------------------------------------------------

if (profile) {

    profile.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();

            openProfileModal();

        }
    );

}


// ------------------------------------------------------
// HEADER PROFILE CLICK
// ------------------------------------------------------

if (headerProfileImg) {

    headerProfileImg.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();

            openProfileModal();

        }
    );

}


// ------------------------------------------------------
// CLOSE X BUTTON
// ------------------------------------------------------

if (closeProfile) {

    closeProfile.addEventListener(
        "click",
        function (e) {

            e.preventDefault();

            closeProfileModal();

        }
    );

}


// ------------------------------------------------------
// CLICK OUTSIDE POPUP
// ------------------------------------------------------

if (profileModal) {

    profileModal.addEventListener(
        "click",
        function (e) {

            if (e.target === profileModal) {

                closeProfileModal();

            }

        }
    );

}


// ------------------------------------------------------
// ESC KEY
// ------------------------------------------------------

document.addEventListener(
    "keydown",
    function (e) {

        if (e.key === "Escape") {

            closeProfileModal();

        }

    }
);



// ======================================================
// 11. EDIT PROFILE
// ======================================================

const editProfileBtn =
    document.getElementById(
        "editProfileBtn"
    );


if (editProfileBtn) {

    editProfileBtn.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            const oldName =
                document
                    .querySelector(".profile-left h2")
                    ?.textContent
                    .trim() || "sujit parmar";


            const newName =
                prompt(
                    "Enter your new name:",
                    oldName
                );


            if (
                newName !== null &&
                newName.trim() !== ""
            ) {

                const nameElement =
                    document.querySelector(
                        ".profile-left h2"
                    );


                if (nameElement) {

                    nameElement.textContent =
                        newName.trim();

                }


                localStorage.setItem(
                    "profileName",
                    newName.trim()
                );


                alert(
                    "Profile updated successfully!"
                );

            }

        }
    );

}



// ======================================================
// 12. LOGOUT
// ======================================================

const profileLogoutBtn =
    document.getElementById(
        "profileLogoutBtn"
    );


if (profileLogoutBtn) {

    profileLogoutBtn.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            const confirmLogout =
                confirm(
                    "Are you sure you want to logout?"
                );


            if (confirmLogout) {

                window.location.href =
                    "login.html";

            }

        }
    );

}



// ======================================================
// 13. CAMERA BUTTON
// PROFILE IMAGE UPLOAD
// ======================================================


// Camera button
const cameraBtn =
    document.querySelector(
        ".camera-btn"
    );


// Profile avatar
const profileAvatar =
    document.querySelector(
        ".profile-avatar"
    );


if (cameraBtn && profileAvatar) {


    // --------------------------------------------------
    // CREATE FILE INPUT AUTOMATICALLY
    // --------------------------------------------------

    let profileFileInput =
        document.getElementById(
            "profileFileInput"
        );


    if (!profileFileInput) {

        profileFileInput =
            document.createElement(
                "input"
            );


        profileFileInput.type =
            "file";

        profileFileInput.id =
            "profileFileInput";

        profileFileInput.accept =
            "image/*";

        profileFileInput.style.display =
            "none";


        document.body.appendChild(
            profileFileInput
        );

    }



    // --------------------------------------------------
    // LOAD SAVED PROFILE PHOTO
    // --------------------------------------------------

    const savedProfilePhoto =
        localStorage.getItem(
            "profilePhoto"
        );


    if (savedProfilePhoto) {

        setProfileImage(
            savedProfilePhoto
        );

    }



    // --------------------------------------------------
    // CAMERA CLICK
    // --------------------------------------------------

    cameraBtn.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            // Open file chooser
            profileFileInput.click();

        }
    );



    // --------------------------------------------------
    // IMAGE SELECT
    // --------------------------------------------------

    profileFileInput.addEventListener(
        "change",
        function () {

            const file =
                this.files[0];


            if (!file) {
                return;
            }



            // Check image

            if (
                !file.type.startsWith(
                    "image/"
                )
            ) {

                alert(
                    "Please select an image file."
                );

                this.value = "";

                return;

            }



            // Check size

            if (
                file.size >
                5 * 1024 * 1024
            ) {

                alert(
                    "Image size must be less than 5 MB."
                );

                this.value = "";

                return;

            }



            // Read image

            const reader =
                new FileReader();


            reader.onload =
                function (event) {

                    const imageData =
                        event.target.result;


                    // Show profile image

                    setProfileImage(
                        imageData
                    );


                    // Save image

                    localStorage.setItem(
                        "profilePhoto",
                        imageData
                    );


                    alert(
                        "Profile photo updated successfully!"
                    );

                };


            reader.readAsDataURL(
                file
            );

        }
    );

}



// ------------------------------------------------------
// SET PROFILE IMAGE FUNCTION
// ------------------------------------------------------

function setProfileImage(
    imageData
) {

    if (!profileAvatar) {
        return;
    }


    // Find existing image

    let image =
        profileAvatar.querySelector(
           (".profile-user-image")
        );


    // If image doesn't exist
    // create it

    if (!image) {

        image =
            document.createElement(
                "img"
            );


        image.className =
            "profile-user-image";


        image.alt =
            "Profile Photo";


        profileAvatar.insertBefore(
            image,
            profileAvatar.firstChild
        );


        // Hide old 👤 span

        const oldSpan =
            profileAvatar.querySelector(
                "span"
            );


        if (oldSpan) {

            oldSpan.style.display =
                "none";

        }

    }


    image.src =
        imageData;


    image.style.width =
        "100%";


    image.style.height =
        "100%";


    image.style.objectFit =
        "cover";


    image.style.borderRadius =
        "50%";

}



// ======================================================
// 14. SETTINGS BUTTON
// ======================================================

const settingsBtn =
    document.querySelector(
        ".settings-btn"
    );


if (settingsBtn) {

    settingsBtn.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            // Remove old settings popup

            const oldSettings =
                document.getElementById(
                    "profileSettingsPopup"
                );


            if (oldSettings) {

                oldSettings.remove();

            }



            // Create settings popup

            const settingsPopup =
                document.createElement(
                    "div"
                );


            settingsPopup.id =
                "profileSettingsPopup";


            settingsPopup.style.position =
                "fixed";

            settingsPopup.style.top =
                "50%";

            settingsPopup.style.left =
                "50%";

            settingsPopup.style.transform =
                "translate(-50%, -50%)";

            settingsPopup.style.width =
                "380px";

            settingsPopup.style.background =
                "white";

            settingsPopup.style.padding =
                "25px";

            settingsPopup.style.borderRadius =
                "18px";

            settingsPopup.style.boxShadow =
                "0 20px 60px rgba(0,0,0,0.3)";

            settingsPopup.style.zIndex =
                "99999";


            settingsPopup.innerHTML = `

                <button
                    id="closeSettingsPopup"
                    style="
                        float:right;
                        border:none;
                        background:none;
                        font-size:24px;
                        cursor:pointer;
                    ">
                    ×
                </button>


                <h2>⚙️ Account Settings</h2>

                <br>

                <p>
                    <strong>Account:</strong>
                    sujit@gmail.com
                </p>

                <br>

                <p>
                    <strong>Username:</strong>
                    admin
                </p>

                <br>

                <button
                    id="settingsDoneBtn"
                    style="
                        width:100%;
                        padding:12px;
                        border:none;
                        border-radius:8px;
                        background:#2867ed;
                        color:white;
                        cursor:pointer;
                    ">
                    Done
                </button>

            `;


            document.body.appendChild(
                settingsPopup
            );


            // Close X

            document
                .getElementById(
                    "closeSettingsPopup"
                )
                .addEventListener(
                    "click",
                    function () {

                        settingsPopup.remove();

                    }
                );


            // Done

            document
                .getElementById(
                    "settingsDoneBtn"
                )
                .addEventListener(
                    "click",
                    function () {

                        settingsPopup.remove();

                    }
                );

        }
    );

}



// ======================================================
// 15. PROFILE MENU
// ======================================================

const profileMenus =
    document.querySelectorAll(
        ".profile-menu"
    );


profileMenus.forEach(
    function (menu) {

        menu.addEventListener(
            "click",
            function (e) {

                e.preventDefault();
                e.stopPropagation();


                profileMenus.forEach(
                    function (item) {

                        item.classList.remove(
                            "active"
                        );

                    }
                );


                menu.classList.add(
                    "active"
                );


                const menuText =
                    menu
                        .querySelectorAll(
                            "span"
                        )[1]
                        ?.textContent
                        .trim();


                if (
                    menuText ===
                    "Security"
                ) {

                    alert(
                        "Security section selected."
                    );

                }


                if (
                    menuText ===
                    "Billing & Plan"
                ) {

                    alert(
                        "Billing & Plan section selected."
                    );

                }

            }
        );

    }
);



// ======================================================
// 16. UPGRADE BUTTON
// ======================================================

const upgradeBtn =
    document.querySelector(
        ".upgrade-btn"
    );


if (upgradeBtn) {

    upgradeBtn.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            const oldUpgrade =
                document.getElementById(
                    "upgradePopup"
                );


            if (oldUpgrade) {

                oldUpgrade.remove();

            }



            const upgradePopup =
                document.createElement(
                    "div"
                );


            upgradePopup.id =
                "upgradePopup";


            upgradePopup.style.position =
                "fixed";

            upgradePopup.style.top =
                "50%";

            upgradePopup.style.left =
                "50%";

            upgradePopup.style.transform =
                "translate(-50%, -50%)";

            upgradePopup.style.width =
                "400px";

            upgradePopup.style.background =
                "white";

            upgradePopup.style.padding =
                "30px";

            upgradePopup.style.borderRadius =
                "18px";

            upgradePopup.style.boxShadow =
                "0 20px 60px rgba(0,0,0,0.3)";

            upgradePopup.style.zIndex =
                "99999";


            upgradePopup.innerHTML = `

                <button
                    id="closeUpgradePopup"
                    style="
                        float:right;
                        border:none;
                        background:none;
                        font-size:24px;
                        cursor:pointer;
                    ">
                    ×
                </button>


                <h2>☁️ Upgrade Plan</h2>

                <br>

                <h3>Pro Plan</h3>

                <p>
                    More storage and premium
                    cloud features.
                </p>

                <br>

                <p>✓ More Storage</p>
                <p>✓ File Versioning</p>
                <p>✓ Premium Features</p>

                <br>

                <button
                    id="upgradeNowBtn"
                    style="
                        width:100%;
                        padding:12px;
                        border:none;
                        border-radius:8px;
                        background:#2867ed;
                        color:white;
                        cursor:pointer;
                    ">
                    Upgrade Now
                </button>

            `;


            document.body.appendChild(
                upgradePopup
            );


            document
                .getElementById(
                    "closeUpgradePopup"
                )
                .addEventListener(
                    "click",
                    function () {

                        upgradePopup.remove();

                    }
                );


            document
                .getElementById(
                    "upgradeNowBtn"
                )
                .addEventListener(
                    "click",
                    function () {

                        alert(
                            "Upgrade process started!"
                        );

                    }
                );

        }
    );

}



// ======================================================
// 17. LANGUAGE SELECT
// ======================================================

const languageSelect =
    document.querySelector(
        ".language-select"
    );


if (languageSelect) {

    languageSelect.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            const languages = [
                "English",
                "Gujarati",
                "Hindi"
            ];


            const currentLanguage =
                languageSelect
                    .textContent
                    .trim()
                    .replace("⌄", "");


            const selectedLanguage =
                prompt(
                    "Select Language:\n\n" +
                    "1. English\n" +
                    "2. Gujarati\n" +
                    "3. Hindi",
                    currentLanguage
                );


            if (
                selectedLanguage !== null &&
                selectedLanguage.trim() !== ""
            ) {

                languageSelect.innerHTML =
                    selectedLanguage.trim() +
                    " <span>⌄</span>";


                localStorage.setItem(
                    "profileLanguage",
                    selectedLanguage.trim()
                );

            }

        }
    );

}

// ======================================================
// SHARED WITH ME
// ======================================================

const shared =
    document.getElementById("shared");

const sharedPage =
    document.getElementById("sharedPage");

const myDrive =
    document.getElementById("myDrive");

const myDrivePage =
    document.querySelector(".main > .content");


// ------------------------------------------------------
// SHARED WITH ME CLICK
// ------------------------------------------------------

if (shared && sharedPage) {

    shared.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            // Remove active from sidebar

            menuItems.forEach(
                function (item) {

                    item.classList.remove("active");

                }
            );


            // Shared active

            shared.classList.add("active");


            // Hide My Drive

            if (myDrivePage) {

                myDrivePage.style.display =
                    "none";

            }


            // Show Shared Page

            sharedPage.style.display =
                "block";

        }
    );

}


// ------------------------------------------------------
// MY DRIVE CLICK
// ------------------------------------------------------

if (myDrive) {

    myDrive.addEventListener(
        "click",
        function (e) {

            e.preventDefault();
            e.stopPropagation();


            // Remove active

            menuItems.forEach(
                function (item) {

                    item.classList.remove("active");

                }
            );


            // My Drive active

            myDrive.classList.add("active");


            // Hide Shared

            if (sharedPage) {

                sharedPage.style.display =
                    "none";

            }


            // Show My Drive

            if (myDrivePage) {

                myDrivePage.style.display =
                    "block";

            }

        }
    );

}