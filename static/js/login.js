document.addEventListener("DOMContentLoaded", function () {
    initPasswordToggle();
    initBranchAutocomplete();
});

function initPasswordToggle() {
    const passwordInput = document.getElementById("password");
    const passwordToggle = document.getElementById("passwordToggle");

    if (!passwordInput || !passwordToggle) {
        return;
    }

    passwordToggle.addEventListener("click", function () {
        const isVisible = passwordInput.type === "text";
        passwordInput.type = isVisible ? "password" : "text";
        passwordToggle.textContent = isVisible ? "Show" : "Hide";
        passwordToggle.setAttribute("aria-label", isVisible ? "Show password" : "Hide password");
        passwordToggle.setAttribute("aria-pressed", String(!isVisible));
    });
}

function initBranchAutocomplete() {
    const wrapper = document.querySelector(".branch-autocomplete");
    const input = document.getElementById("branchInput");
    const list = document.getElementById("branchSuggestions");
    let branches = [];

    if (wrapper) {
        try {
            const parsed = JSON.parse(wrapper.dataset.branches || "[]");
            if (Array.isArray(parsed)) {
                branches = parsed;
            }
        } catch (error) {
            branches = [];
        }
    }

    if (!wrapper || !input || !list || !branches.length) {
        return;
    }

    let activeIndex = -1;
    let currentMatches = [];

    function hideSuggestions() {
        list.classList.remove("is-visible");
        list.innerHTML = "";
        input.setAttribute("aria-expanded", "false");
        activeIndex = -1;
        currentMatches = [];
    }

    function applyValue(value) {
        input.value = value;
        hideSuggestions();
    }

    function updateActiveSuggestion() {
        const items = list.querySelectorAll(".branch-suggestion");
        items.forEach(function (item, index) {
            if (index === activeIndex) {
                item.classList.add("is-active");
            } else {
                item.classList.remove("is-active");
            }
        });
    }

    function showSuggestions(matches) {
        list.innerHTML = "";
        currentMatches = matches;
        activeIndex = -1;

        if (!matches.length) {
            hideSuggestions();
            return;
        }

        matches.forEach(function (branchName) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "branch-suggestion";
            button.setAttribute("role", "option");
            button.textContent = branchName;
            button.addEventListener("mousedown", function (event) {
                event.preventDefault();
                applyValue(branchName);
            });
            list.appendChild(button);
        });

        list.classList.add("is-visible");
        input.setAttribute("aria-expanded", "true");
    }

    function filterBranches() {
        const typedValue = input.value.trim().toUpperCase();
        if (!typedValue) {
            hideSuggestions();
            return;
        }

        const matches = branches.filter(function (branchName) {
            return String(branchName || "").toUpperCase().includes(typedValue);
        }).slice(0, 8);

        showSuggestions(matches);
    }

    input.addEventListener("input", filterBranches);
    input.addEventListener("focus", function () {
        if (input.value.trim()) {
            filterBranches();
        }
    });

    input.addEventListener("keydown", function (event) {
        if (!currentMatches.length) {
            return;
        }

        if (event.key === "ArrowDown") {
            event.preventDefault();
            activeIndex = (activeIndex + 1) % currentMatches.length;
            updateActiveSuggestion();
            return;
        }

        if (event.key === "ArrowUp") {
            event.preventDefault();
            activeIndex = activeIndex <= 0 ? currentMatches.length - 1 : activeIndex - 1;
            updateActiveSuggestion();
            return;
        }

        if (event.key === "Enter" && activeIndex >= 0) {
            event.preventDefault();
            applyValue(currentMatches[activeIndex]);
            return;
        }

        if (event.key === "Escape") {
            hideSuggestions();
        }
    });

    document.addEventListener("click", function (event) {
        if (!event.target.closest(".branch-autocomplete")) {
            hideSuggestions();
        }
    });
}
