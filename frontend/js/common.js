// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TX_TYPE_PURCHASE = "purchase";
const TX_TYPE_TRANSFER = "transfer";
const TX_TYPE_OUTGOING_TRANSFER = "outgoing_transfer";

const QUARTER_MONTHS = {
    1: [0, 1, 2],
    2: [3, 4, 5],
    3: [6, 7, 8],
    4: [9, 10, 11],
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------
function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// API auth helper
// ---------------------------------------------------------------------------
// The hosted server requires a shared-secret bearer token on every /api/*
// request. The token is obtained via the /login page (POST /api/login),
// kept in localStorage, and attached to every API call via apiFetch(); on a
// 401 it's cleared and the user is sent back to /login.
const API_TOKEN_STORAGE_KEY = "financeTrackerApiToken";
const API_USER_STORAGE_KEY = "financeTrackerUsername";

function getApiToken() {
    return localStorage.getItem(API_TOKEN_STORAGE_KEY) || "";
}

function getLoggedUser() {
    return localStorage.getItem(API_USER_STORAGE_KEY) || "";
}

// Every page must be logged in before it renders/loads data. Call this as
// the very first step of a page's bootstrap, before any data fetch, and
// skip the rest of the bootstrap if it returns false.
function requireAuth() {
    if (!getApiToken()) {
        const next = encodeURIComponent(window.location.pathname);
        window.location.href = `/login?next=${next}`;
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem(API_TOKEN_STORAGE_KEY);
    localStorage.removeItem(API_USER_STORAGE_KEY);
    window.location.href = "/login";
}

// The "Log out" control lives in the shared header markup on every page;
// wire it here once instead of duplicating the listener per page script.
document.addEventListener("click", (e) => {
    if (e.target.closest(".btn-logout")) logout();
});

document.addEventListener("DOMContentLoaded", () => {
    const usernameEl = document.getElementById("logged-user");
    if (usernameEl) usernameEl.textContent = getLoggedUser();
});

async function apiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}), Authorization: `Bearer ${getApiToken()}` };
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
        localStorage.removeItem(API_TOKEN_STORAGE_KEY);
        localStorage.removeItem(API_USER_STORAGE_KEY);
        window.location.href = "/login";
    }
    return res;
}

async function fetchJSON(url) {
    const res = await apiFetch(url);
    if (!res.ok) {
        throw new Error(`Request failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
}

// ---------------------------------------------------------------------------
// Date & formatting helpers
// ---------------------------------------------------------------------------
function getCurrentQuarter() {
    return Math.floor(new Date().getMonth() / 3) + 1;
}

function formatAmount(amount) {
    return `$${amount.toLocaleString("en", { minimumFractionDigits: 2 })}`;
}

function getCurrentMonthStr() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function shiftMonth(monthStr, delta) {
    const [year, month] = monthStr.split("-").map(Number);
    const d = new Date(year, month - 1 + delta, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function getMonthDateRange(monthStr) {
    const [year, month] = monthStr.split("-").map(Number);
    const lastDay = new Date(year, month, 0).getDate();
    return {
        start: `${year}-${String(month).padStart(2, "0")}-01`,
        end: `${year}-${String(month).padStart(2, "0")}-${lastDay}`,
    };
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------
function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("toast-visible"));

    setTimeout(() => {
        toast.classList.remove("toast-visible");
        toast.addEventListener("transitionend", () => toast.remove());
    }, 3000);
}

function setButtonLoading(btn, loading) {
    if (loading) {
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "...";
    } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || btn.textContent;
        delete btn.dataset.originalText;
    }
}
