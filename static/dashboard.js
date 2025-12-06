document.addEventListener("DOMContentLoaded", () => {
    // Replace feather icons
    feather.replace();

    // Get elements
    const setupMenu = document.getElementById("menu-setup");
    const loadMenu = document.getElementById("menu-load");
    const bulkMenu = document.getElementById("menu-bulk");
    const aboutMenu = document.getElementById("menu-about");

    const setupSection = document.getElementById("setup-section");
    const loadSection = document.getElementById("load-section");
    const bulkSection = document.getElementById("bulk-section");
    const aboutSection = document.getElementById("about-section");

    const bulkForm = document.getElementById("bulkForm");
    const botForm = document.getElementById("botForm");
    const botform = document.getElementById("botform");

    // Unified form submission handler
    async function handleSubmit(e, endpoint, formId) {
        e.preventDefault();
        const submitButton = e.target.querySelector('button[type="submit"]') || e.target.querySelector('input[type="submit"]');
        let originalButtonText = submitButton.textContent || submitButton.value;

        submitButton.textContent = "Processing...";
        submitButton.disabled = true;

        let formData = new FormData(e.target);

        console.log(`---- ${formId} FORM DATA ----`);
        for (let [key, value] of formData.entries()) {
            if (value instanceof File) {
                console.log(`${key}: FILE -> ${value.name}`);
            } else {
                console.log(`${key}:`, value);
            }
        }
        console.log("----------------------------");

        try {
            let response = await fetch(endpoint, {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const responseText = await response.text();
                let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                
                if (responseText.startsWith('{') || responseText.startsWith('[')) {
                    try {
                        const errorResult = JSON.parse(responseText);
                        errorMessage = `HTTP ${response.status}: ${errorResult.detail || errorResult.message || response.statusText}`;
                    } catch (e) {
                        console.error("Failed to parse error response as JSON:", e);
                    }
                } else if (responseText.length > 0) {
                    errorMessage += ` | Server returned a non-JSON Error page. Check backend logs.`;
                }

                throw new Error(errorMessage);
            }
            
            let result = await response.json();
            console.log(`✅ Response from FastAPI (${formId}):`, result);

            let alertMessage = result.message || `${formId} successful.`;
            if (result.CODE) {
                alertMessage += `\nYour Bot ID (CODE) is: ${result.CODE}`;
            }
            
            alert("✅ " + alertMessage);

            setTimeout(() => {
                window.location.href = "/static/dashboard.html"; 
            }, 500); 

        } catch (err) {
            console.error(`❌ Error submitting ${formId} form:`, err);
            alert(`Error submitting ${formId} form: ` + err.message);
        } finally {
            submitButton.textContent = originalButtonText;
            submitButton.disabled = false;
        }
    }

    // Attach form handlers
    if (botForm) {
        botForm.addEventListener("submit", (e) => handleSubmit(e, "http://127.0.0.1:8000/submit_maytapi", "MAYTAPI"));
    }

    if (botform) {
        botform.addEventListener("submit", (e) => handleSubmit(e, "http://127.0.0.1:8000/load_bot", "LOAD BOT"));
    }

    // Handle bulk form submission
    if (bulkForm) {
        bulkForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            const message = document.getElementById("message").value;
            const start = document.getElementById("start").value;
            const end = document.getElementById("end").value;

            const submitButton = e.submitter; 
            const originalText = submitButton.textContent;

            submitButton.textContent = "Sending...";
            submitButton.disabled = true;

            const formData = new URLSearchParams();
            formData.append('message', message);
            formData.append('start', start);
            formData.append('end', end);

            try {
                const response = await fetch("http://127.0.0.1:8000/bulk_hi", {
                    method: "POST",
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded' 
                    },
                    body: formData
                });

                const result = await response.json();

                if (response.ok) {
                    alert(`✅ Bulk message triggered successfully!\nTotal messages sent: ${result.total_sent}\nRedirecting to success page...`);
                    window.location.href = "bulk.html"; 
                } else {
                    alert(`❌ Bulk Send Failed: ${result.message || 'Unknown Error'}`);
                    console.error("Bulk API Error:", result);
                }

            } catch (err) {
                alert(`❌ Network Error: Could not connect to the server or request failed.`);
                console.error("Bulk Network Error:", err);
                
            } finally {
                submitButton.innerText = "Triger Bulk";
                submitButton.disabled = false;
            }
        });
    }

    // Menu switching functions
    function showSection(activeMenu, activeSection) {
        // Remove active class from all menus
        if (setupMenu) setupMenu.classList.remove("active");
        if (loadMenu) loadMenu.classList.remove("active");
        if (bulkMenu) bulkMenu.classList.remove("active");
        if (aboutMenu) aboutMenu.classList.remove("active");

        // Add active class to clicked menu
        activeMenu.classList.add("active");

        // Hide all sections
        if (setupSection) setupSection.classList.add("hidden");
        if (loadSection) loadSection.classList.add("hidden");
        if (bulkSection) bulkSection.classList.add("hidden");
        if (aboutSection) aboutSection.classList.add("hidden");

        // Show active section
        activeSection.classList.remove("hidden");
    }

    // Menu event listeners
    if (setupMenu) {
        setupMenu.addEventListener("click", (e) => {
            e.preventDefault();
            showSection(setupMenu, setupSection);
        });
    }
    if (loadMenu) {
        loadMenu.addEventListener("click", (e) => {
            e.preventDefault();
            showSection(loadMenu, loadSection);
        });
    }
    if (bulkMenu) {
        bulkMenu.addEventListener("click", (e) => {
            e.preventDefault();
            showSection(bulkMenu, bulkSection);
        });
    }
    if (aboutMenu) {
        aboutMenu.addEventListener("click", (e) => {
            e.preventDefault();
            showSection(aboutMenu, aboutSection);
        });
    }

    // File name display for setup form
    function setupFileListener(inputId, spanId) {
        const fileInput = document.getElementById(inputId);
        const fileNameSpan = document.getElementById(spanId);
        if (fileInput) {
            fileInput.addEventListener("change", function () {
                if (this.files.length) {
                    const name = this.files[0].name;
                    alert("Excel File selected: " + name);
                    if (fileNameSpan) {
                        fileNameSpan.textContent = name;
                    }
                } else {
                    if (fileNameSpan) {
                        fileNameSpan.textContent = "";
                    }
                }
            });
        }
    }

    setupFileListener("upload_sheet", "file-name");
    setupFileListener("upload_sheet1", "file-name2");
});
